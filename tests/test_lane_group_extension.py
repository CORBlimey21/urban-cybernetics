"""Focused tests for the versioned Paper 1 lane-group extension."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import (
    DemandDeclaration,
    EventType,
    JunctionSpec,
    Link,
    MovementSpec,
    Node,
)
from urban_cybernetics.loading.engine import LoadingEngine
from urban_cybernetics.experiments.lane_group_ablation import (
    AblationControl,
    run_lane_group_ablation,
)
from urban_cybernetics.loading.lane_group_extension import (
    EXPLICIT_LANE_GROUP_FIFO,
    EXPLICIT_LANE_GROUP_SCHEMA_VERSION,
    MOVEMENT_PARTIAL_FIFO,
    SHARED_LINK_FIFO,
    ExplicitLaneGroup,
    LaneGroupExtensionConfig,
    LaneGroupLoadingEngine,
    LaneGroupProvenance,
)


def _link(
    link_id: str,
    *,
    sending: int = 4,
    receiving: int = 4,
) -> Link:
    return Link(
        link_id,
        free_flow_ticks=1,
        declared_sending_capacity_per_tick=sending,
        declared_receiving_capacity_per_tick=receiving,
        declared_storage_capacity_packets=20,
        length_m=10.0,
        lane_count=1,
        free_flow_speed_mps=10.0,
        jam_density_veh_per_km_per_lane=100.0,
        backward_wave_speed_mps=5.0,
        capacity_veh_per_hour_per_lane=1200.0,
        tick_duration_seconds=1.0,
    )


def _node(*, signal: bool = False, conflict: bool = False) -> Node:
    conflict_ids = ("crossing",) if conflict else ()
    return Node(
        "N",
        incoming_link_ids=("U",),
        outgoing_link_ids=("L", "R"),
        junction_spec=JunctionSpec(
            node_id="N",
            incoming_link_ids=("U",),
            outgoing_link_ids=("L", "R"),
            conflict_resource_ids=conflict_ids,
            conflict_resource_capacities=(
                (("crossing", 1),) if conflict else ()
            ),
            movement_specs=(
                MovementSpec(
                    "U",
                    "L",
                    signal_group_id=("left-phase" if signal else None),
                    conflict_resource_ids=conflict_ids,
                ),
                MovementSpec(
                    "U",
                    "R",
                    conflict_resource_ids=conflict_ids,
                ),
            ),
        ),
    )


def _group(
    group_id: str,
    *downstream_ids: str,
    capacity: int = 1,
) -> ExplicitLaneGroup:
    return ExplicitLaneGroup(
        lane_group_id=group_id,
        node_id="N",
        incoming_link_id="U",
        allowed_movement_ids=tuple(
            f"movement:U->{downstream_id}" for downstream_id in downstream_ids
        ),
        service_capacity_per_tick=capacity,
        provenance=LaneGroupProvenance(
            source="canonical-test-fixture",
            confidence=1.0,
            status="declared",
            compiler_version="manual-v1",
        ),
    )


def _config(
    mode: str,
    groups: tuple[ExplicitLaneGroup, ...],
) -> LaneGroupExtensionConfig:
    return LaneGroupExtensionConfig(
        representation_mode=mode,
        lane_groups=groups,
    )


def _engine(
    config: LaneGroupExtensionConfig,
    *,
    node: Node | None = None,
) -> LoadingEngine:
    selected_node = node or _node()
    return LaneGroupLoadingEngine(
        links={"U": _link("U"), "L": _link("L"), "R": _link("R")},
        nodes=(selected_node,),
        lane_group_config=config,
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
    )


def _add_left_right(engine: LoadingEngine) -> tuple[str, str]:
    left = engine.instantiate(
        DemandDeclaration("left", 0, ("U", "L"))
    ).packet_id
    right = engine.instantiate(
        DemandDeclaration("right", 0, ("U", "R"))
    ).packet_id
    return left, right


def _entries(engine: LoadingEngine, link_id: str, tick: int) -> tuple[str, ...]:
    return tuple(
        event.packet_id
        for event in engine.event_log
        if event.event_type == EventType.LINK_ENTRY
        and event.entity_id == link_id
        and event.physical_tick == tick
    )


def test_schema_validates_version_locality_capacity_coverage_and_provenance() -> None:
    node = _node()
    groups = (_group("all", "L", "R"),)
    config = _config(EXPLICIT_LANE_GROUP_FIFO, groups)
    config.validate_against_nodes((node,))
    assert config.schema_version == EXPLICIT_LANE_GROUP_SCHEMA_VERSION
    assert len(config.config_hash) == 64
    with pytest.raises(ValueError, match="positive"):
        replace(groups[0], service_capacity_per_tick=0)
    with pytest.raises(ValueError, match="every movement"):
        _config(
            EXPLICIT_LANE_GROUP_FIFO,
            (_group("left", "L"),),
        ).validate_against_nodes((node,))
    with pytest.raises(ValueError, match="unknown incoming"):
        _config(
            EXPLICIT_LANE_GROUP_FIFO,
            (replace(groups[0], incoming_link_id="missing"),),
        ).validate_against_nodes((node,))


def test_canonical_fixture_artifact_declares_all_required_cases() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures/lane_groups/v1/canonical_lane_group_cases_v1.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert payload["extension_version"] == "paper1-lane-group-extension-v1"
    assert payload["schema_version"] == EXPLICIT_LANE_GROUP_SCHEMA_VERSION
    assert {case["case_id"] for case in payload["cases"]} == {
        "shared-single-group",
        "separated-groups",
        "partially-shared-alternative",
        "signal-interaction",
        "downstream-blockage",
        "conflict-coupling",
    }
    assert payload["global_gates"]["determinism"].startswith("exact_")


def test_shared_single_group_head_blocks_other_movement() -> None:
    engine = _engine(
        _config(
            EXPLICIT_LANE_GROUP_FIFO,
            (_group("shared", "L", "R", capacity=2),),
        )
    )
    left, right = _add_left_right(engine)
    engine.set_receiving_open("L", False)
    engine.step()
    assert engine.packet_ids_in_queue("U", "L") == (left,)
    assert _entries(engine, "R", 1) == ()
    assert right in engine.packet_ids_on_link("U")


def test_positive_integer_group_capacity_limits_indivisible_service() -> None:
    engine = _engine(
        _config(
            EXPLICIT_LANE_GROUP_FIFO,
            (_group("shared", "L", "R", capacity=1),),
        )
    )
    packet_ids = tuple(
        engine.instantiate(
            DemandDeclaration(f"right-{index}", 0, ("U", "R"))
        ).packet_id
        for index in range(3)
    )
    engine.step()
    assert _entries(engine, "R", 1) == (packet_ids[0],)
    assert engine.movement_allocator.last_lane_group_allocation_traces[
        0
    ].approved_packet_lane_groups == ((packet_ids[0], "shared"),)


def test_separated_groups_allow_independent_service_and_retain_upstream_state() -> None:
    engine = _engine(
        _config(
            EXPLICIT_LANE_GROUP_FIFO,
            (_group("left", "L"), _group("right", "R")),
        )
    )
    left, right = _add_left_right(engine)
    engine.set_receiving_open("L", False)
    engine.step()
    assert engine.packet_ids_in_queue("U", "L") == (left,)
    assert left in engine.packet_ids_on_link("U")
    assert _entries(engine, "R", 1) == (right,)
    trace = engine.movement_allocator.last_lane_group_allocation_traces[0]
    assert trace.packet_assignments == ((left, "left"), (right, "right"))
    assert trace.approved_packet_lane_groups == ((right, "right"),)


def test_alternative_group_uses_shortest_queue_then_retains_assignment() -> None:
    engine = _engine(
        _config(
            EXPLICIT_LANE_GROUP_FIFO,
            (
                _group("shared", "L", "R"),
                _group("right-alternative", "R"),
            ),
        )
    )
    left, right = _add_left_right(engine)
    engine.set_receiving_open("L", False)
    engine.step()
    trace = engine.movement_allocator.last_lane_group_allocation_traces[0]
    assert trace.packet_assignments == (
        (left, "shared"),
        (right, "right-alternative"),
    )
    assert _entries(engine, "R", 1) == (right,)
    engine.step()
    assert engine.movement_allocator._assignment_by_node_packet[
        ("N", left)
    ] == "shared"


def test_signal_red_blocks_one_group_while_other_group_serves() -> None:
    engine = _engine(
        _config(
            EXPLICIT_LANE_GROUP_FIFO,
            (_group("left", "L"), _group("right", "R")),
        ),
        node=_node(signal=True),
    )
    left, right = _add_left_right(engine)
    engine.step()
    assert engine.packet_ids_in_queue("U", "L") == (left,)
    assert _entries(engine, "R", 1) == (right,)


def test_downstream_blockage_is_independent_between_groups() -> None:
    engine = _engine(
        _config(
            EXPLICIT_LANE_GROUP_FIFO,
            (_group("left", "L"), _group("right", "R")),
        )
    )
    _add_left_right(engine)
    engine.set_receiving_open("L", False)
    engine.step()
    assert len(_entries(engine, "R", 1)) == 1


def test_conflict_resource_still_couples_separate_lane_groups() -> None:
    engine = _engine(
        _config(
            EXPLICIT_LANE_GROUP_FIFO,
            (_group("left", "L"), _group("right", "R")),
        ),
        node=_node(conflict=True),
    )
    _add_left_right(engine)
    engine.step()
    assert len(_entries(engine, "L", 1)) + len(_entries(engine, "R", 1)) == 1
    reasons = dict(
        engine.node_transfer_traces()[0].rejected_transfer_reasons
    )
    assert "conflict_resource_capacity_unavailable" in reasons.values()


def test_fifo_queue_entry_exit_and_all_integrity_checks() -> None:
    engine = _engine(
        _config(
            EXPLICIT_LANE_GROUP_FIFO,
            (_group("left", "L"), _group("right", "R")),
        )
    )
    left, _ = _add_left_right(engine)
    engine.set_receiving_open("L", False)
    engine.step()
    engine.set_receiving_open("L", True)
    engine.step()
    queue_events = tuple(
        event.event_type
        for event in engine.event_log
        if event.packet_id == left
        and event.event_type in (EventType.QUEUE_ENTRY, EventType.QUEUE_EXIT)
    )
    assert queue_events == (EventType.QUEUE_ENTRY, EventType.QUEUE_EXIT)
    assert engine.check_conservation()
    assert engine.check_event_cache_consistency()
    assert engine.count_consistency_report().is_consistent


def test_persistent_separate_group_queues_can_exit_independently() -> None:
    engine = _engine(
        _config(
            EXPLICIT_LANE_GROUP_FIFO,
            (_group("left", "L"), _group("right", "R")),
        )
    )
    left, right = _add_left_right(engine)
    engine.set_receiving_open("L", False)
    engine.set_receiving_open("R", False)
    engine.step()
    assert engine.packet_ids_in_queue("U", "L") == (left,)
    assert engine.packet_ids_in_queue("U", "R") == (right,)

    engine.set_receiving_open("R", True)
    engine.step()
    assert engine.packet_ids_in_queue("U", "L") == (left,)
    assert engine.packet_ids_in_queue("U", "R") == ()
    assert _entries(engine, "R", 2) == (right,)
    assert engine.check_event_cache_consistency()

    engine.set_receiving_open("L", True)
    engine.step()
    assert _entries(engine, "L", 3) == (left,)
    assert engine.check_conservation()
    assert engine.count_consistency_report().is_consistent


def test_three_representation_modes_and_exact_deterministic_rerun() -> None:
    groups = (_group("left", "L"), _group("right", "R"))
    outcomes = {}
    for mode in (
        SHARED_LINK_FIFO,
        MOVEMENT_PARTIAL_FIFO,
        EXPLICIT_LANE_GROUP_FIFO,
    ):
        pair = []
        for _ in range(2):
            engine = _engine(_config(mode, groups))
            _add_left_right(engine)
            engine.set_receiving_open("L", False)
            engine.step()
            pair.append(
                (
                    engine.event_log,
                    engine.node_transfer_traces(),
                    getattr(
                        engine.movement_allocator,
                        "last_lane_group_allocation_traces",
                    ),
                )
            )
        assert pair[0] == pair[1]
        outcomes[mode] = pair[0]
    assert len(_entries(_engine_after_one_step(SHARED_LINK_FIFO, groups), "R", 1)) == 0
    assert len(
        _entries(_engine_after_one_step(MOVEMENT_PARTIAL_FIFO, groups), "R", 1)
    ) == 1
    assert len(
        _entries(_engine_after_one_step(EXPLICIT_LANE_GROUP_FIFO, groups), "R", 1)
    ) == 1


def _engine_after_one_step(
    mode: str,
    groups: tuple[ExplicitLaneGroup, ...],
) -> LoadingEngine:
    engine = _engine(_config(mode, groups))
    _add_left_right(engine)
    engine.set_receiving_open("L", False)
    engine.step()
    return engine


def test_disabled_extension_leaves_frozen_baseline_exact() -> None:
    node = _node()

    def run() -> tuple[object, ...]:
        engine = LoadingEngine(
            links={"U": _link("U"), "L": _link("L"), "R": _link("R")},
            nodes=(node,),
            model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        )
        _add_left_right(engine)
        engine.set_receiving_open("L", False)
        engine.step()
        return (
            engine.event_log,
            engine.node_transfer_traces(),
            tuple(engine.packets.items()),
            engine.completed_packet_ids,
            engine.current_tick,
            engine.conservation_summary(),
            engine.count_consistency_report(),
        )

    assert run() == run()


def test_ablation_result_is_structured_complete_and_replay_clean() -> None:
    node = _node()
    result = run_lane_group_ablation(
        links={"U": _link("U"), "L": _link("L"), "R": _link("R")},
        nodes=(node,),
        lane_groups=(_group("left", "L"), _group("right", "R")),
        demands=(
            DemandDeclaration("left", 0, ("U", "L")),
            DemandDeclaration("right", 0, ("U", "R")),
        ),
        controls=(
            AblationControl(1, "receiving_open", "L", False),
            AblationControl(2, "receiving_open", "L", True),
        ),
        max_ticks=10,
    )
    assert tuple(run.representation_mode for run in result.runs) == (
        SHARED_LINK_FIFO,
        MOVEMENT_PARTIAL_FIFO,
        EXPLICIT_LANE_GROUP_FIFO,
    )
    assert all(run.completed_packet_count == 2 for run in result.runs)
    assert all(run.replay_passed for run in result.runs)
    assert all(run.conservation_passed for run in result.runs)
    assert all(run.event_cache_consistency_passed for run in result.runs)
    assert all(run.cumulative_count_consistency_passed for run in result.runs)
    assert result.as_dict()["result_version"] == "paper1-lane-group-ablation-v1"
