"""Analytical and mixed-domain tests for gate-aware fractional service V2."""

from __future__ import annotations

from copy import deepcopy
from math import ceil

import pytest

from urban_cybernetics.core import (
    DemandDeclaration,
    EventType,
    JunctionSpec,
    Link,
    MovementSpec,
    Node,
)
from urban_cybernetics.extensions.fixed_time_signals import (
    FixedTimeControllerPlan,
    FixedTimeSignalControlMixin,
    FixedTimeSignalPlanEvaluator,
    FixedTimeStage,
    ResolvedFixedTimeSignalPlan,
)
from urban_cybernetics.extensions.fractional_service_credit import (
    FRACTIONAL_CREDIT,
    FractionalServiceCreditConfig,
    FractionalServiceCreditMixin,
)
from urban_cybernetics.extensions.gate_aware_fractional_service import (
    GATE_AWARE_FRACTIONAL_SERVICE_MODE,
    ConstantServiceRateMultiplier,
    GateAwareFractionalServiceConfig,
    GateAwareFractionalServiceEvidence,
    GateAwareFractionalServiceIntegrityError,
    GateAwareFractionalServiceLoadingEngine,
    GateAwareFractionalServiceMixin,
    ServiceRateContext,
    evaluate_effective_service_rate,
)
from urban_cybernetics.loading import GeneralMovementAllocator, LoadingEngine
from urban_cybernetics.loading.lane_group_extension import (
    EXPLICIT_LANE_GROUP_FIFO,
    MOVEMENT_PARTIAL_FIFO,
    SHARED_LINK_FIFO,
    ExplicitLaneGroup,
    LaneGroupExtensionConfig,
    LaneGroupLoadingEngine,
    LaneGroupProvenance,
)


def _link(link_id: str, rate: float, *, storage: int = 300) -> Link:
    return Link(
        link_id=link_id,
        free_flow_ticks=1,
        declared_sending_capacity_per_tick=max(1, ceil(rate)),
        declared_receiving_capacity_per_tick=max(1, ceil(rate)),
        declared_storage_capacity_packets=storage,
        length_m=10.0,
        lane_count=1,
        free_flow_speed_mps=10.0,
        jam_density_veh_per_km_per_lane=30_000.0,
        backward_wave_speed_mps=10.0,
        capacity_veh_per_hour_per_lane=rate * 3_600.0,
        tick_duration_seconds=1.0,
    )


@pytest.mark.parametrize(
    ("rate", "expected_ticks"),
    (
        (0.25, (4, 8, 12, 16)),
        (0.4, (3, 5, 8, 10)),
        (0.5, (2, 4, 6, 8)),
        (0.75, (2, 3, 4, 6)),
        (1.0, (1, 2, 3, 4)),
        (1.5, (1, 2, 2, 3)),
    ),
)
def test_permanently_green_or_uncontrolled_v2_matches_fractional_rate(
    rate: float,
    expected_ticks: tuple[int, ...],
) -> None:
    engine = GateAwareFractionalServiceLoadingEngine(
        links={"L": _link("L", rate)},
        gate_aware_fractional_service_config=GateAwareFractionalServiceConfig(
            (("L", rate),)
        ),
        executable_semantic_hash="v2-permanently-green",
    )
    for index in range(4):
        engine.instantiate(DemandDeclaration(f"D{index}", 0, ("L",)))
    ticks = []
    prior = 0
    while len(engine.completed_packet_ids) < 4:
        engine.step()
        current = len(engine.completed_packet_ids)
        ticks.extend((engine.current_tick,) * (current - prior))
        prior = current
    assert tuple(ticks) == expected_ticks
    sending = [
        item
        for item in engine.gate_aware_fractional_service_evidence
        if item.service_domain_type == "link_sending"
    ]
    assert all(item.control_availability_factor == 1.0 for item in sending)
    assert all(item.dynamic_rate_multiplier == 1.0 for item in sending)
    assert engine.check_conservation()


class _V1SignalEngine(
    FixedTimeSignalControlMixin,
    FractionalServiceCreditMixin,
    LoadingEngine,
):
    pass


class _V2SignalEngine(
    FixedTimeSignalControlMixin,
    GateAwareFractionalServiceMixin,
    LoadingEngine,
):
    pass


def _ggrr_engine(*, version: str, offset: int, rate: float = 0.25):
    links = {"U": _link("U", rate), "D": _link("D", 10.0)}
    movement = MovementSpec("U", "D", signal_group_id="signal:ggrr")
    node = Node(
        "N",
        incoming_link_ids=("U",),
        outgoing_link_ids=("D",),
        junction_spec=JunctionSpec(
            "N", ("U",), ("D",), movement_specs=(movement,)
        ),
    )
    plan = ResolvedFixedTimeSignalPlan(
        controllers=(
            FixedTimeControllerPlan(
                controller_id="controller:ggrr",
                node_id="N",
                cycle_ticks=4,
                offset_ticks=offset,
                stages=(
                    FixedTimeStage("green", 2, (movement.movement_id,)),
                    FixedTimeStage("red", 2, ()),
                ),
                controlled_movement_ids=(movement.movement_id,),
            ),
        )
    )
    common = {
        "links": links,
        "nodes": (node,),
        "node_transfer_policy": GeneralMovementAllocator((node,)),
        "fixed_time_signal_provider": FixedTimeSignalPlanEvaluator(plan, (node,)),
        "executable_semantic_hash": "ggrr-fixture",
    }
    if version == "v1":
        return _V1SignalEngine(
            **common,
            fractional_service_credit_config=FractionalServiceCreditConfig(
                FRACTIONAL_CREDIT, (("U", rate), ("D", 10.0))
            ),
        )
    return _V2SignalEngine(
        **common,
        gate_aware_fractional_service_config=GateAwareFractionalServiceConfig(
            (("U", rate), ("D", 10.0))
        ),
    )


def _run_ggrr(*, version: str, offset: int, horizon: int = 80):
    engine = _ggrr_engine(version=version, offset=offset)
    for index in range(100):
        engine.instantiate(DemandDeclaration(f"{version}:{offset}:{index}", 0, ("U", "D")))
    for _ in range(horizon):
        engine.step()
    service_ticks = tuple(
        item.physical_tick
        for item in engine.event_log
        if item.event_type == EventType.LINK_ENTRY and item.entity_id == "D"
    )
    return engine, service_ticks


def test_v2_eliminates_original_quarter_rate_ggrr_zero_service_alias() -> None:
    v1, v1_ticks = _run_ggrr(version="v1", offset=2)
    v2, v2_ticks = _run_ggrr(version="v2", offset=2)
    assert v1_ticks == ()
    assert len(v2_ticks) == 10
    assert len(v2_ticks) / 80 == pytest.approx(0.125)
    assert v2_ticks[:4] == (7, 15, 23, 31)
    assert v1.check_conservation() and v2.check_conservation()
    assert (
        v1.fractional_service_credit_config.config_hash
        != v2.gate_aware_fractional_service_config.config_hash
    )


@pytest.mark.parametrize("offset", (0, 1, 2, 3, 5, 10))
def test_v2_ggrr_offsets_do_not_phase_lock_to_zero(offset: int) -> None:
    _, service_ticks = _run_ggrr(version="v2", offset=offset, horizon=160)
    assert 19 <= len(service_ticks) <= 20
    assert service_ticks


def _manual_gate_engine(rate: float = 0.25):
    links = {"U": _link("U", rate), "D": _link("D", 10.0)}
    movement = MovementSpec("U", "D", signal_group_id="manual")
    node = Node(
        "N",
        ("U",),
        ("D",),
        junction_spec=JunctionSpec("N", ("U",), ("D",), movement_specs=(movement,)),
    )
    engine = GateAwareFractionalServiceLoadingEngine(
        links=links,
        nodes=(node,),
        node_transfer_policy=GeneralMovementAllocator((node,)),
        gate_aware_fractional_service_config=GateAwareFractionalServiceConfig(
            (("U", rate), ("D", 10.0))
        ),
        executable_semantic_hash="manual-gate-fixture",
    )
    engine.instantiate(DemandDeclaration("packet", 0, ("U", "D")))
    return engine


def _sending_records(engine, link_id: str = "U"):
    return [
        item
        for item in engine.gate_aware_fractional_service_evidence
        if item.service_domain_type == "link_sending" and item.service_domain_id == link_id
    ]


def test_long_red_adds_nothing_preserves_fraction_and_has_no_reopening_burst() -> None:
    engine = _manual_gate_engine()
    engine.set_signal_group_open("manual", True)
    engine.step()  # +0.25
    engine.set_signal_group_open("manual", False)
    for _ in range(20):
        engine.step()
    red = _sending_records(engine)[1:]
    assert all(item.effective_continuous_allowance == 0.0 for item in red)
    assert all(item.closing_fractional_credit == pytest.approx(0.25) for item in red)
    engine.set_signal_group_open("manual", True)
    engine.step()
    engine.step()
    assert not any(
        event.entity_id == "D" and event.event_type == EventType.LINK_ENTRY
        for event in engine.event_log
    )
    engine.step()
    entries = [
        item
        for item in engine.event_log
        if item.entity_id == "D" and item.event_type == EventType.LINK_ENTRY
    ]
    assert len(entries) == 1
    assert entries[0].physical_tick == 24


def test_short_red_interruption_preserves_partial_fraction_without_reset() -> None:
    engine = _manual_gate_engine()
    engine.set_signal_group_open("manual", True)
    engine.step()
    engine.step()
    assert _sending_records(engine)[-1].closing_fractional_credit == pytest.approx(0.5)
    engine.set_signal_group_open("manual", False)
    engine.step()
    red = _sending_records(engine)[-1]
    assert red.effective_continuous_allowance == 0.0
    assert red.closing_fractional_credit == pytest.approx(0.5)
    engine.set_signal_group_open("manual", True)
    engine.step()
    assert _sending_records(engine)[-1].closing_fractional_credit == pytest.approx(0.75)


def test_idle_green_does_not_bank_capacity_but_preserves_existing_fraction() -> None:
    engine = GateAwareFractionalServiceLoadingEngine(
        links={"L": _link("L", 0.25)},
        gate_aware_fractional_service_config=GateAwareFractionalServiceConfig(
            (("L", 0.25),)
        ),
    )
    for _ in range(20):
        engine.step()
    assert all(item.effective_continuous_allowance == 0.0 for item in _sending_records(engine, "L"))
    engine.instantiate(DemandDeclaration("late", 20, ("L",)))
    for _ in range(3):
        engine.step()
    assert not engine.completed_packet_ids
    engine.step()
    assert engine.completed_packet_ids


class _MixedRepresentationEngine(
    GateAwareFractionalServiceMixin,
    LaneGroupLoadingEngine,
):
    pass


def _mixed_engine(representation: str):
    links = {
        "U": _link("U", 2.0),
        "G": _link("G", 2.0),
        "R": _link("R", 2.0),
    }
    green = MovementSpec("U", "G", signal_group_id="signal:green")
    red = MovementSpec("U", "R", signal_group_id="signal:red")
    node = Node(
        "N",
        ("U",),
        ("G", "R"),
        junction_spec=JunctionSpec(
            "N", ("U",), ("G", "R"), movement_specs=(green, red)
        ),
    )
    provenance = LaneGroupProvenance("synthetic-mixed-test", 1.0, "declared")
    groups = (
        ExplicitLaneGroup("group:green", "N", "U", (green.movement_id,), 1, provenance),
        ExplicitLaneGroup("group:red", "N", "U", (red.movement_id,), 1, provenance),
    )
    engine = _MixedRepresentationEngine(
        links=links,
        nodes=(node,),
        lane_group_config=LaneGroupExtensionConfig(representation, groups),
        gate_aware_fractional_service_config=GateAwareFractionalServiceConfig(
            (("U", 2.0), ("G", 2.0), ("R", 2.0))
        ),
        executable_semantic_hash="mixed-movement-fixture",
    )
    engine.set_signal_group_open("signal:green", True)
    engine.set_signal_group_open("signal:red", False)
    engine.instantiate(DemandDeclaration("red-first", 0, ("U", "R")))
    engine.instantiate(DemandDeclaration("green-second", 0, ("U", "G")))
    engine.step()
    return engine


@pytest.mark.parametrize(
    ("representation", "green_moves"),
    (
        (SHARED_LINK_FIFO, False),
        (MOVEMENT_PARTIAL_FIFO, True),
        (EXPLICIT_LANE_GROUP_FIFO, True),
    ),
)
def test_mixed_green_red_link_uses_one_enabled_account_without_duplication(
    representation: str,
    green_moves: bool,
) -> None:
    first = _mixed_engine(representation)
    replay = _mixed_engine(representation)
    assert first.event_log == replay.event_log
    entries_green = [
        item
        for item in first.event_log
        if item.event_type == EventType.LINK_ENTRY and item.entity_id == "G"
    ]
    entries_red = [
        item
        for item in first.event_log
        if item.event_type == EventType.LINK_ENTRY and item.entity_id == "R"
    ]
    assert bool(entries_green) is green_moves
    assert not entries_red
    sending = _sending_records(first)[0]
    assert sending.service_account_id == "effective-rate:sending:U"
    assert sending.control_gate_state == "enabled_at_least_one_green"
    assert sending.whole_service_exposed == 2
    assert sending.physically_consumed_service <= 1
    assert len(
        {
            item.service_account_id
            for item in first.gate_aware_fractional_service_evidence
            if item.service_domain_type == "link_sending" and item.service_domain_id == "U"
        }
    ) == 1
    assert first.check_conservation()


def test_v2_evidence_and_configuration_round_trip_tamper_and_v3_seam() -> None:
    config = GateAwareFractionalServiceConfig((('L', 0.25),))
    assert GateAwareFractionalServiceConfig.from_dict(config.to_dict()) == config
    context = ServiceRateContext(
        tick=1,
        service_account_id="A",
        service_domain_id="L",
        service_domain_type="link_sending",
        base_continuous_rate_packets_per_tick=0.25,
        control_gate_state="enabled_uncontrolled",
        control_availability_factor=1.0,
        relevant_movement_ids=("completion:L",),
        relevant_packet_ids=("P1",),
    )
    evaluated = evaluate_effective_service_rate(context, ConstantServiceRateMultiplier())
    assert evaluated.effective_continuous_allowance == 0.25

    engine = GateAwareFractionalServiceLoadingEngine(
        links={"L": _link("L", 0.25)},
        gate_aware_fractional_service_config=config,
    )
    engine.instantiate(DemandDeclaration("evidence", 0, ("L",)))
    engine.step()
    record = engine.gate_aware_fractional_service_evidence[0]
    assert GateAwareFractionalServiceEvidence.from_dict(record.to_dict()) == record
    tampered = deepcopy(record.to_dict())
    tampered["dynamic_rate_multiplier"] = 0.5
    with pytest.raises(GateAwareFractionalServiceIntegrityError, match="hash mismatch"):
        GateAwareFractionalServiceEvidence.from_dict(tampered)
    assert config.mode == GATE_AWARE_FRACTIONAL_SERVICE_MODE
