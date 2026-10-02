# SPDX-License-Identifier: MPL-2.0
"""Focused contract tests for fixed-time-signal-extension-v1."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
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
from urban_cybernetics.extensions import (
    FIXED_TIME_SIGNAL_EXTENSION_VERSION,
    FixedTimeControllerPlan,
    FixedTimePlanValidationError,
    FixedTimeSignalControlMixin,
    FixedTimeSignalLoadingEngine,
    FixedTimeSignalPlanEvaluator,
    FixedTimeStage,
    ResolvedFixedTimeSignalPlan,
    ResolvedValueProvenance,
)
from urban_cybernetics.extensions.executable_routing import (
    ExecutableRoutingLoadingEngine,
)
from urban_cybernetics.loading import GeneralMovementAllocator, LoadingEngine
from urban_cybernetics.loading.lane_group_extension import (
    EXPLICIT_LANE_GROUP_FIFO,
    ExplicitLaneGroup,
    LaneGroupExtensionConfig,
    LaneGroupLoadingEngine,
    LaneGroupProvenance,
)
from urban_cybernetics.routing import RoutingInstruction


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures/fixed_time_signals/v1/alternating_plan_v1.json"
)
MOVEMENT_A = "movement:UA->OA"
MOVEMENT_B = "movement:UB->OB"
MOVEMENT_X = "movement:UX->OX"


def _link(link_id: str, *, capacity: int = 2) -> Link:
    return Link(
        link_id=link_id,
        free_flow_ticks=1,
        declared_sending_capacity_per_tick=capacity,
        declared_receiving_capacity_per_tick=capacity,
        declared_storage_capacity_packets=20,
        length_m=10.0,
        lane_count=1,
        free_flow_speed_mps=10.0,
        jam_density_veh_per_km_per_lane=100.0,
        backward_wave_speed_mps=5.0,
        capacity_veh_per_hour_per_lane=1200.0,
        tick_duration_seconds=1.0,
    )


def _alternating_node(*, manual_signal_on_x: bool = False) -> Node:
    return Node(
        "N",
        incoming_link_ids=("UA", "UB", "UX"),
        outgoing_link_ids=("OA", "OB", "OX"),
        junction_spec=JunctionSpec(
            node_id="N",
            incoming_link_ids=("UA", "UB", "UX"),
            outgoing_link_ids=("OA", "OB", "OX"),
            movement_specs=(
                MovementSpec("UA", "OA", signal_group_id="signal:A"),
                MovementSpec("UB", "OB", signal_group_id="signal:B"),
                MovementSpec(
                    "UX",
                    "OX",
                    signal_group_id=("signal:X" if manual_signal_on_x else None),
                ),
            ),
        ),
    )


def _fixture_payload() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _fixture_plan() -> ResolvedFixedTimeSignalPlan:
    return ResolvedFixedTimeSignalPlan.from_dict(_fixture_payload()["plan"])


def _provider(
    *,
    node: Node | None = None,
    plan: ResolvedFixedTimeSignalPlan | None = None,
) -> FixedTimeSignalPlanEvaluator:
    selected_node = node or _alternating_node()
    return FixedTimeSignalPlanEvaluator(plan or _fixture_plan(), (selected_node,))


def _links() -> dict[str, Link]:
    return {
        link_id: _link(link_id)
        for link_id in ("UA", "UB", "UX", "OA", "OB", "OX")
    }


def _engine(
    *,
    node: Node | None = None,
    plan: ResolvedFixedTimeSignalPlan | None = None,
) -> FixedTimeSignalLoadingEngine:
    selected_node = node or _alternating_node()
    return FixedTimeSignalLoadingEngine(
        links=_links(),
        nodes=(selected_node,),
        fixed_time_signal_provider=_provider(node=selected_node, plan=plan),
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
    )


def _entries(
    engine: LoadingEngine,
    link_id: str,
    tick: int,
) -> tuple[str, ...]:
    return tuple(
        event.packet_id
        for event in engine.event_log
        if event.event_type == EventType.LINK_ENTRY
        and event.entity_id == link_id
        and event.physical_tick == tick
    )


def _run_alternating_fixture() -> FixedTimeSignalLoadingEngine:
    engine = _engine()
    packet_a = engine.instantiate(DemandDeclaration("A-1", 0, ("UA", "OA")))
    packet_b = engine.instantiate(DemandDeclaration("B-1", 0, ("UB", "OB")))
    packet_x = engine.instantiate(DemandDeclaration("X-1", 0, ("UX", "OX")))
    assert packet_a is not None and packet_b is not None and packet_x is not None

    # Receiving supply proves that B's green is necessary but not sufficient.
    engine.set_receiving_open("OB", False)
    engine.step()  # t=1, A green; B red; X retains unsignalised behavior.
    assert _entries(engine, "OA", 1) == (packet_a.packet_id,)
    assert _entries(engine, "OB", 1) == ()
    assert _entries(engine, "OX", 1) == (packet_x.packet_id,)
    assert engine.packet_ids_in_queue("UB", "OB") == (packet_b.packet_id,)

    packet_a_repeat = engine.instantiate(
        DemandDeclaration("A-2", 1, ("UA", "OA"))
    )
    assert packet_a_repeat is not None
    engine.step()  # t=2, clearance.
    assert _entries(engine, "OA", 2) == ()
    assert engine.packet_ids_in_queue("UA", "OA") == (
        packet_a_repeat.packet_id,
    )
    assert engine.packet_ids_in_queue("UB", "OB") == (packet_b.packet_id,)

    engine.step()  # t=3, B green but receiving is still closed.
    assert _entries(engine, "OB", 3) == ()
    assert engine.packet_ids_in_queue("UB", "OB") == (packet_b.packet_id,)

    engine.set_receiving_open("OB", True)
    engine.step()  # t=4, B remains green and normal allocation releases its head.
    assert _entries(engine, "OB", 4) == (packet_b.packet_id,)
    assert engine.packet_ids_in_queue("UB", "OB") == ()

    engine.step()  # t=5, clearance.
    engine.step()  # t=6, cycle repeats at A's exact start boundary.
    assert _entries(engine, "OA", 6) == (packet_a_repeat.packet_id,)
    engine.step()  # complete final two-link packet.
    assert engine.check_conservation()
    return engine


def test_schema_is_immutable_versioned_hashed_and_round_trips_exactly() -> None:
    plan = _fixture_plan()
    assert plan.extension_version == FIXED_TIME_SIGNAL_EXTENSION_VERSION
    assert plan.controllers[0].extension_version == (
        FIXED_TIME_SIGNAL_EXTENSION_VERSION
    )
    assert len(plan.semantic_hash) == 64
    assert len(plan.configuration_hash) == 64
    assert plan == ResolvedFixedTimeSignalPlan.from_json(plan.to_json())
    assert plan.configuration_hash == ResolvedFixedTimeSignalPlan.from_dict(
        plan.to_dict()
    ).configuration_hash
    with pytest.raises(FrozenInstanceError):
        plan.controllers[0].cycle_ticks = 99  # type: ignore[misc]
    tampered = plan.to_dict()
    tampered["configuration_hash"] = "0" * 64
    with pytest.raises(FixedTimePlanValidationError, match="hash mismatch"):
        ResolvedFixedTimeSignalPlan.from_dict(tampered)


def test_half_open_boundaries_cycle_repeat_and_offset_are_exact() -> None:
    fixture = _fixture_payload()
    provider = _provider()
    for expectation in fixture["timing_expectations"]:
        tick = expectation["tick"]
        a = provider.evaluate(MOVEMENT_A, tick)
        b = provider.evaluate(MOVEMENT_B, tick)
        assert a is not None and b is not None
        assert a.stage_id == expectation["stage_id"]
        assert a.cycle_position == expectation["cycle_position"]
        assert {
            item.movement_id for item in (a, b) if item.baseline_is_open
        } == set(expectation["open_movement_ids"])

    offset_probe = fixture["offset_probe"]
    offset_controller = replace(
        _fixture_plan().controllers[0],
        offset_ticks=offset_probe["offset_ticks"] + 6,
    )
    assert offset_controller.offset_ticks == 2
    offset_plan = ResolvedFixedTimeSignalPlan((offset_controller,))
    offset_provider = _provider(plan=offset_plan)
    for expectation in offset_probe["expected"]:
        tick = expectation["tick"]
        a = offset_provider.evaluate(MOVEMENT_A, tick)
        b = offset_provider.evaluate(MOVEMENT_B, tick)
        assert a.stage_id == b.stage_id == expectation["stage_id"]
        assert {
            item.movement_id for item in (a, b) if item.baseline_is_open
        } == set(expectation["open_movement_ids"])


def test_single_universal_tick_starts_state_at_zero_and_allocation_at_one() -> None:
    clock_contract = _fixture_payload()["clock_contract"]
    assert clock_contract == {
        "first_allocation_tick": 1,
        "initial_state_tick": 0,
        "signal_tick_translation": "none",
        "tick_domain": "single_universal_simulation_tick",
    }
    engine = _engine()
    assert engine.current_tick == 0
    tick_zero = engine.signal_gate_state(MOVEMENT_A, 0)
    assert tick_zero is not None
    assert tick_zero.tick == tick_zero.cycle_position == 0
    assert tick_zero.stage_id == "stage:N:A"
    packet = engine.instantiate(DemandDeclaration("tick-contract", 0, ("UA", "OA")))
    assert packet is not None
    initial_events = tuple(
        event for event in engine.event_log if event.packet_id == packet.packet_id
    )
    assert tuple(event.physical_tick for event in initial_events) == (0, 0)
    assert engine.fixed_time_signal_evidence == ()

    engine.step()

    assert engine.current_tick == 1
    assert _entries(engine, "OA", 1) == (packet.packet_id,)
    assert engine.fixed_time_signal_evidence[-1].tick == 1
    transfer_events = tuple(
        event.physical_tick
        for event in engine.event_log
        if event.packet_id == packet.packet_id
        and event.event_type in (EventType.LINK_EXIT, EventType.LINK_ENTRY)
    )
    assert transfer_events[-2:] == (1, 1)


def test_movement_may_be_served_in_multiple_stages() -> None:
    controller = FixedTimeControllerPlan(
        controller_id="controller:multiple",
        node_id="N",
        cycle_ticks=2,
        offset_ticks=0,
        controlled_movement_ids=(MOVEMENT_A,),
        stages=(
            FixedTimeStage("stage:multiple:1", 1, (MOVEMENT_A,)),
            FixedTimeStage("stage:multiple:2", 1, (MOVEMENT_A,)),
        ),
    )
    provider = _provider(plan=ResolvedFixedTimeSignalPlan((controller,)))
    assert provider.evaluate(MOVEMENT_A, 0).baseline_is_open
    assert provider.evaluate(MOVEMENT_A, 1).baseline_is_open
    assert provider.evaluate(MOVEMENT_A, 2).baseline_is_open


def test_alternating_fixture_queues_physically_and_replays_exactly() -> None:
    first = _run_alternating_fixture()
    second = _run_alternating_fixture()
    assert first.event_log == second.event_log
    assert first.fixed_time_signal_evidence == second.fixed_time_signal_evidence
    assert (
        first.fixed_time_signal_evidence_hash
        == second.fixed_time_signal_evidence_hash
    )
    assert first.conservation_summary() == second.conservation_summary() == {
        "instantiated": 4,
        "in_flight": 0,
        "completed": 4,
        "cancelled": 0,
        "unresolved": 0,
    }
    queue_events = tuple(
        (event.packet_id, event.event_type, event.entity_id, event.physical_tick)
        for event in first.event_log
        if event.event_type in (EventType.QUEUE_ENTRY, EventType.QUEUE_EXIT)
    )
    assert queue_events == (
        ("P2", EventType.QUEUE_ENTRY, "boundary:UB->OB", 1),
        ("P4", EventType.QUEUE_ENTRY, "boundary:UA->OA", 2),
        ("P2", EventType.QUEUE_EXIT, "boundary:UB->OB", 4),
        ("P4", EventType.QUEUE_EXIT, "boundary:UA->OA", 6),
    )


def test_evidence_is_request_linked_and_query_does_not_persist() -> None:
    engine = _engine()
    assert engine.fixed_time_signal_evidence == ()
    query = engine.signal_gate_state(MOVEMENT_A, 2)
    assert query is not None
    assert query.controller_id == "controller:N:main"
    assert query.stage_id == "stage:N:clearance:A-to-B"
    assert query.cycle_position == 2
    assert query.movement_id == MOVEMENT_A
    assert query.baseline_is_open is False
    assert query.effective_is_open is False
    assert len(query.plan_configuration_hash) == 64
    assert engine.fixed_time_signal_evidence == ()
    packet = engine.instantiate(DemandDeclaration("A", 0, ("UA", "OA")))
    engine.step()
    assert packet is not None
    assert engine.fixed_time_signal_evidence == (
        replace(
            engine.signal_gate_state(MOVEMENT_A, 1),
            request_packet_ids=(packet.packet_id,),
        ),
    )


def test_uncontrolled_and_manually_signalled_movements_retain_legacy_gate() -> None:
    node = _alternating_node(manual_signal_on_x=True)
    engine = _engine(node=node)
    packet = engine.instantiate(DemandDeclaration("X", 0, ("UX", "OX")))
    assert packet is not None
    engine.step()
    assert engine.packet_ids_in_queue("UX", "OX") == (packet.packet_id,)
    assert engine.fixed_time_signal_evidence == ()
    engine.set_signal_group_open("signal:X", True)
    engine.step()
    assert _entries(engine, "OX", 2) == (packet.packet_id,)


def test_legacy_loader_is_identical_when_extension_has_no_controllers() -> None:
    node = Node(
        "N0",
        incoming_link_ids=("U",),
        outgoing_link_ids=("D",),
    )
    links = {"U": _link("U"), "D": _link("D")}
    baseline = LoadingEngine(
        links=links,
        nodes=(node,),
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
    )
    empty_plan = ResolvedFixedTimeSignalPlan(())
    extension = FixedTimeSignalLoadingEngine(
        links=links,
        nodes=(node,),
        fixed_time_signal_provider=FixedTimeSignalPlanEvaluator(
            empty_plan,
            (node,),
        ),
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
    )
    for engine in (baseline, extension):
        engine.instantiate(DemandDeclaration("D", 0, ("U", "D")))
        engine.step()
        engine.step()
    assert baseline.event_log == extension.event_log
    assert extension.fixed_time_signal_evidence == ()


@pytest.mark.parametrize("duration", (0, -1))
def test_zero_or_negative_stage_durations_are_rejected(duration: int) -> None:
    with pytest.raises(FixedTimePlanValidationError, match="positive"):
        FixedTimeStage("bad-stage", duration, ())


def test_duration_sums_duplicate_ids_and_ownership_are_rejected() -> None:
    stage = FixedTimeStage("stage:one", 1, (MOVEMENT_A,))
    with pytest.raises(FixedTimePlanValidationError, match="sum exactly"):
        FixedTimeControllerPlan(
            "controller:bad-sum",
            "N",
            2,
            0,
            (stage,),
            (MOVEMENT_A,),
        )
    with pytest.raises(FixedTimePlanValidationError, match="duplicate IDs"):
        replace(
            _fixture_plan().controllers[0],
            controlled_movement_ids=(MOVEMENT_A,) * 2,
        )
    first = FixedTimeControllerPlan(
        "controller:first",
        "N",
        1,
        0,
        (FixedTimeStage("stage:first", 1, (MOVEMENT_A,)),),
        (MOVEMENT_A,),
    )
    second = FixedTimeControllerPlan(
        "controller:second",
        "N",
        1,
        0,
        (FixedTimeStage("stage:second", 1, (MOVEMENT_A,)),),
        (MOVEMENT_A,),
    )
    with pytest.raises(FixedTimePlanValidationError, match="ambiguous"):
        ResolvedFixedTimeSignalPlan((first, second))
    with pytest.raises(FixedTimePlanValidationError, match="duplicate stage IDs"):
        ResolvedFixedTimeSignalPlan((first, replace(second, stages=first.stages)))
    with pytest.raises(FixedTimePlanValidationError, match="duplicate controller"):
        ResolvedFixedTimeSignalPlan((first, first))


def test_unknown_movement_stage_reference_and_gate_binding_are_rejected() -> None:
    with pytest.raises(FixedTimePlanValidationError, match="not controlled"):
        FixedTimeControllerPlan(
            "controller:bad-stage-ref",
            "N",
            1,
            0,
            (FixedTimeStage("stage:bad-ref", 1, ("movement:missing",)),),
            (MOVEMENT_A,),
        )
    unknown = FixedTimeControllerPlan(
        "controller:unknown",
        "N",
        1,
        0,
        (FixedTimeStage("stage:unknown", 1, ("movement:missing",)),),
        ("movement:missing",),
    )
    with pytest.raises(FixedTimePlanValidationError, match="unknown movement_id"):
        _provider(plan=ResolvedFixedTimeSignalPlan((unknown,)))
    no_gate_node = Node(
        "N",
        ("UA",),
        ("OA",),
        junction_spec=JunctionSpec(
            "N",
            ("UA",),
            ("OA",),
            movement_specs=(MovementSpec("UA", "OA"),),
        ),
    )
    one = FixedTimeControllerPlan(
        "controller:no-gate",
        "N",
        1,
        0,
        (FixedTimeStage("stage:no-gate", 1, (MOVEMENT_A,)),),
        (MOVEMENT_A,),
    )
    with pytest.raises(FixedTimePlanValidationError, match="no signal_group_id"):
        _provider(node=no_gate_node, plan=ResolvedFixedTimeSignalPlan((one,)))


def test_shared_signal_group_must_have_unambiguous_equivalent_ownership() -> None:
    node = Node(
        "N",
        ("UA", "UB"),
        ("OA", "OB"),
        junction_spec=JunctionSpec(
            "N",
            ("UA", "UB"),
            ("OA", "OB"),
            movement_specs=(
                MovementSpec("UA", "OA", signal_group_id="shared"),
                MovementSpec("UB", "OB", signal_group_id="shared"),
            ),
        ),
    )
    with pytest.raises(FixedTimePlanValidationError, match="sharing signal_group_id"):
        _provider(node=node)


def test_unresolved_and_malformed_executable_fields_are_rejected() -> None:
    payload = _fixture_plan().to_dict()
    controller = payload["controllers"][0]
    controller["offset_ticks"] = None
    with pytest.raises(FixedTimePlanValidationError, match="resolved integer"):
        ResolvedFixedTimeSignalPlan.from_dict(payload)
    missing = _fixture_plan().to_dict()
    del missing["controllers"][0]["cycle_ticks"]
    with pytest.raises(FixedTimePlanValidationError, match="unresolved/missing"):
        ResolvedFixedTimeSignalPlan.from_dict(missing)
    with pytest.raises(FixedTimePlanValidationError, match="malformed plan JSON"):
        ResolvedFixedTimeSignalPlan.from_json("{")
    malformed_nested = _fixture_plan().to_dict()
    malformed_nested["controllers"][0]["stages"][0] = "not-an-object"
    with pytest.raises(FixedTimePlanValidationError, match="must be an object"):
        ResolvedFixedTimeSignalPlan.from_dict(malformed_nested)
    malformed_metadata = _fixture_plan().to_dict()
    malformed_metadata["metadata"] = [1]
    with pytest.raises(FixedTimePlanValidationError, match="two-item lists"):
        ResolvedFixedTimeSignalPlan.from_dict(malformed_metadata)
    with pytest.raises(FixedTimePlanValidationError, match="resolution_status"):
        ResolvedValueProvenance("cycle_ticks", "unresolved")  # type: ignore[arg-type]


def test_executable_routing_request_waits_for_fixed_time_green() -> None:
    movement = "movement:U->A"
    node = Node(
        "N",
        ("U",),
        ("A",),
        junction_spec=JunctionSpec(
            "N",
            ("U",),
            ("A",),
            movement_specs=(
                MovementSpec("U", "A", signal_group_id="signal:routed"),
            ),
        ),
    )
    plan = ResolvedFixedTimeSignalPlan(
        (
            FixedTimeControllerPlan(
                "controller:routed",
                "N",
                4,
                0,
                (
                    FixedTimeStage("stage:routed:red", 3, ()),
                    FixedTimeStage("stage:routed:green", 1, (movement,)),
                ),
                (movement,),
            ),
        )
    )
    provider = FixedTimeSignalPlanEvaluator(plan, (node,))

    class RoutedFixedTimeEngine(
        FixedTimeSignalControlMixin,
        ExecutableRoutingLoadingEngine,
    ):
        pass

    engine = RoutedFixedTimeEngine(
        links={"U": _link("U"), "A": _link("A")},
        nodes=(node,),
        node_transfer_policy=GeneralMovementAllocator((node,)),
        fixed_time_signal_provider=provider,
    )
    packet = engine.instantiate(DemandDeclaration("D", 0, ("U", "A")))
    assert packet is not None
    engine.submit_instruction(
        RoutingInstruction(
            instruction_id="instruction:routed:1",
            packet_id=packet.packet_id,
            version=1,
            authority_id="authority:test",
            decision_artifact_id="artifact:routed:1",
            issue_tick=0,
            effective_tick=0,
            remaining_route=("U", "A"),
            policy_id="fixed-time-composition-test",
            provenance=(("fixture", "fixed-time-routing-composition"),),
            route_start_ordinal=0,
        )
    )
    engine.step()
    assert engine.packet_ids_in_queue("U", "A") == (packet.packet_id,)
    engine.step()
    assert _entries(engine, "A", 2) == ()
    engine.step()
    assert _entries(engine, "A", 3) == (packet.packet_id,)
    assert engine.movement_instruction_evidence[-1].instruction_id == (
        "instruction:routed:1"
    )
    assert engine.check_conservation()


def test_signal_mixin_composes_with_explicit_lane_group_partition() -> None:
    movement_a = "movement:U->A"
    movement_b = "movement:U->B"
    node = Node(
        "N",
        ("U",),
        ("A", "B"),
        junction_spec=JunctionSpec(
            "N",
            ("U",),
            ("A", "B"),
            movement_specs=(
                MovementSpec("U", "A", signal_group_id="signal:A"),
                MovementSpec("U", "B", signal_group_id="signal:B"),
            ),
        ),
    )
    plan = ResolvedFixedTimeSignalPlan(
        (
            FixedTimeControllerPlan(
                "controller:lane-composition",
                "N",
                2,
                0,
                (
                    FixedTimeStage("stage:lane:A", 1, (movement_a,)),
                    FixedTimeStage("stage:lane:B", 1, (movement_b,)),
                ),
                (movement_a, movement_b),
            ),
        )
    )
    groups = tuple(
        ExplicitLaneGroup(
            lane_group_id=f"group:{suffix}",
            node_id="N",
            incoming_link_id="U",
            allowed_movement_ids=(movement,),
            service_capacity_per_tick=1,
            provenance=LaneGroupProvenance(
                source="fixed-time-composition-test",
                confidence=1.0,
                status="declared",
            ),
        )
        for suffix, movement in (("A", movement_a), ("B", movement_b))
    )

    class FixedTimeLaneGroupEngine(
        FixedTimeSignalControlMixin,
        LaneGroupLoadingEngine,
    ):
        pass

    engine = FixedTimeLaneGroupEngine(
        links={"U": _link("U"), "A": _link("A"), "B": _link("B")},
        nodes=(node,),
        lane_group_config=LaneGroupExtensionConfig(
            representation_mode=EXPLICIT_LANE_GROUP_FIFO,
            lane_groups=groups,
        ),
        fixed_time_signal_provider=FixedTimeSignalPlanEvaluator(plan, (node,)),
    )
    first = engine.instantiate(DemandDeclaration("A", 0, ("U", "A")))
    second = engine.instantiate(DemandDeclaration("B", 0, ("U", "B")))
    assert first is not None and second is not None
    engine.step()  # t=1 is B green; B bypasses red A in its separate lane group.
    assert _entries(engine, "B", 1) == (second.packet_id,)
    assert engine.packet_ids_in_queue("U", "A") == (first.packet_id,)
