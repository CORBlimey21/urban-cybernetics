"""Analytical and integration tests for discharge-readiness V3."""

from __future__ import annotations

from copy import deepcopy
from math import ceil, exp

import pytest

from urban_cybernetics.core import (
    DemandDeclaration,
    EventType,
    JunctionSpec,
    Link,
    MovementSpec,
    Node,
)
from urban_cybernetics.extensions.discharge_readiness_fractional_service import (
    COMPACT_EVIDENCE,
    FORENSIC_EVIDENCE,
    GREEN_RECOVERY,
    RED_DECAY,
    SUMMARY_EVIDENCE,
    DischargeReadinessConfig,
    DischargeReadinessEvidence,
    DischargeReadinessFractionalServiceLoadingEngine,
    DischargeReadinessFractionalServiceMixin,
    DischargeReadinessIntegrityError,
    ExponentialDischargeReadinessProvider,
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
    GateAwareFractionalServiceConfig,
    GateAwareFractionalServiceMixin,
    ServiceRateContext,
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


def _link(
    link_id: str,
    rate: float,
    *,
    dt: float = 1.0,
    storage: int = 500,
    lag: int = 1,
) -> Link:
    return Link(
        link_id=link_id,
        free_flow_ticks=lag,
        declared_sending_capacity_per_tick=max(1, ceil(rate)),
        declared_receiving_capacity_per_tick=max(1, ceil(rate)),
        declared_storage_capacity_packets=storage,
        length_m=10.0,
        lane_count=1,
        free_flow_speed_mps=10.0,
        jam_density_veh_per_km_per_lane=50_000.0,
        backward_wave_speed_mps=10.0,
        capacity_veh_per_hour_per_lane=rate / dt * 3_600.0,
        tick_duration_seconds=dt,
    )


def _config(
    rates: tuple[tuple[str, float], ...],
    *,
    controlled: tuple[str, ...],
    dt: float = 1.0,
    tau_green: float = 2.0,
    tau_red: float | None = 10.0,
    initial: float = 1.0,
    evidence_mode: str = FORENSIC_EVIDENCE,
) -> DischargeReadinessConfig:
    return DischargeReadinessConfig(
        continuous_capacity_by_link=rates,
        tick_duration_seconds_by_link=tuple((link_id, dt) for link_id, _ in rates),
        controlled_readiness_link_ids=controlled,
        tau_green_seconds=tau_green,
        tau_red_seconds=tau_red,
        default_initial_readiness=initial,
        initial_readiness_by_domain=tuple((link_id, initial) for link_id in controlled),
        evidence_mode=evidence_mode,
        compact_checkpoint_interval_ticks=5,
    )


@pytest.mark.parametrize("rate", (0.25, 0.4, 0.5, 0.75, 1.0, 1.5))
def test_permanent_green_initial_one_exactly_matches_v2(rate: float) -> None:
    v2_engine = type(
        "V2Single",
        (GateAwareFractionalServiceMixin, LoadingEngine),
        {},
    )(
        links={"L": _link("L", rate)},
        gate_aware_fractional_service_config=GateAwareFractionalServiceConfig(
            (("L", rate),)
        ),
    )
    v3_engine = DischargeReadinessFractionalServiceLoadingEngine(
        links={"L": _link("L", rate)},
        discharge_readiness_config=_config(
            (("L", rate),), controlled=("L",), tau_red=None, initial=1.0
        ),
    )
    for index in range(200):
        demand = DemandDeclaration(f"D{index}", 0, ("L",))
        v2_engine.instantiate(demand)
        v3_engine.instantiate(demand)
    for _ in range(80):
        v2_engine.step()
        v3_engine.step()
    assert v3_engine.event_log == v2_engine.event_log
    assert len(v3_engine.completed_packet_ids) == int(rate * 80)
    assert v3_engine.check_conservation()


class _V1SignalEngine(FixedTimeSignalControlMixin, FractionalServiceCreditMixin, LoadingEngine):
    pass


class _V2SignalEngine(FixedTimeSignalControlMixin, GateAwareFractionalServiceMixin, LoadingEngine):
    pass


class _V3SignalEngine(
    FixedTimeSignalControlMixin,
    DischargeReadinessFractionalServiceMixin,
    LoadingEngine,
):
    pass


def _signal_engine(
    policy: str,
    *,
    rate: float = 0.25,
    dt: float = 1.0,
    cycle_ticks: int = 4,
    green_ticks: int = 2,
    offset: int = 0,
    tau_green: float = 2.0,
    tau_red: float | None = 10.0,
    initial: float = 1.0,
    evidence_mode: str = FORENSIC_EVIDENCE,
):
    links = {"U": _link("U", rate, dt=dt), "D": _link("D", 10.0 * dt, dt=dt)}
    movement = MovementSpec("U", "D", signal_group_id="signal:test")
    node = Node(
        "N",
        ("U",),
        ("D",),
        junction_spec=JunctionSpec("N", ("U",), ("D",), movement_specs=(movement,)),
    )
    stages = (
        (FixedTimeStage("green", green_ticks, (movement.movement_id,)),)
        if green_ticks == cycle_ticks
        else (
            FixedTimeStage("green", green_ticks, (movement.movement_id,)),
            FixedTimeStage("red", cycle_ticks - green_ticks, ()),
        )
    )
    plan = ResolvedFixedTimeSignalPlan(
        controllers=(
            FixedTimeControllerPlan(
                "controller:test",
                "N",
                cycle_ticks,
                offset,
                stages,
                (movement.movement_id,),
            ),
        )
    )
    common = dict(
        links=links,
        nodes=(node,),
        node_transfer_policy=GeneralMovementAllocator((node,)),
        fixed_time_signal_provider=FixedTimeSignalPlanEvaluator(plan, (node,)),
        executable_semantic_hash="v3-analytical-fixture",
    )
    rates = (("U", rate), ("D", 10.0 * dt))
    if policy == "v1":
        return _V1SignalEngine(
            **common,
            fractional_service_credit_config=FractionalServiceCreditConfig(
                FRACTIONAL_CREDIT, rates
            ),
        )
    if policy == "v2":
        return _V2SignalEngine(
            **common,
            gate_aware_fractional_service_config=GateAwareFractionalServiceConfig(rates),
        )
    return _V3SignalEngine(
        **common,
        discharge_readiness_config=_config(
            rates,
            controlled=("U",),
            dt=dt,
            tau_green=tau_green,
            tau_red=tau_red,
            initial=initial,
            evidence_mode=evidence_mode,
        ),
    )


def _run_signal(engine, ticks: int, *, demand_count: int = 300) -> tuple[int, ...]:
    for index in range(demand_count):
        engine.instantiate(DemandDeclaration(f"D{index}", 0, ("U", "D")))
    for _ in range(ticks):
        engine.step()
    return tuple(
        event.physical_tick
        for event in engine.event_log
        if event.event_type == EventType.LINK_ENTRY and event.entity_id == "D"
    )


@pytest.mark.parametrize("offset", (0, 1, 2, 3, 5, 10))
def test_infinite_red_memory_collapses_v3_physical_events_to_v2(offset: int) -> None:
    v2 = _signal_engine("v2", offset=offset)
    v3 = _signal_engine("v3", offset=offset, tau_red=None, initial=1.0)
    _run_signal(v2, 160)
    _run_signal(v3, 160)
    assert v3.event_log == v2.event_log
    assert all(
        item.opening_readiness == item.closing_readiness == 1.0
        for item in v3.discharge_readiness_evidence
    )


def _context(tick: int, gate: float, *, demand: bool = True) -> ServiceRateContext:
    return ServiceRateContext(
        tick=tick,
        service_account_id="effective-rate:sending:L",
        service_domain_id="L",
        service_domain_type="link_sending",
        base_continuous_rate_packets_per_tick=1.0,
        control_gate_state="green" if gate else "red",
        control_availability_factor=gate,
        relevant_movement_ids=("movement:L->D",) if demand else (),
        relevant_packet_ids=("P",) if demand else (),
    )


def test_exact_green_recovery_and_startup_lost_time_approach_tau() -> None:
    provider = ExponentialDischargeReadinessProvider(
        _config((("L", 1.0),), controlled=("L",), tau_green=2.0, initial=0.0)
    )
    means = []
    closings = []
    for tick in range(1, 41):
        means.append(provider.multiplier(_context(tick, 1.0)))
        closings.append(provider.readiness_by_domain["L"])
    assert closings == sorted(closings)
    assert all(0.0 <= value <= 1.0 for value in (*means, *closings))
    assert closings[-1] == pytest.approx(1.0 - exp(-20.0), abs=1e-12)
    integrated_lost_seconds = sum(1.0 - value for value in means)
    assert integrated_lost_seconds == pytest.approx(2.0 * (1.0 - exp(-20.0)))


@pytest.mark.parametrize("initial", (0.0, 0.3, 1.0))
def test_initial_readiness_is_explicit_and_deterministic(initial: float) -> None:
    config = _config((("L", 1.0),), controlled=("L",), initial=initial)
    provider = ExponentialDischargeReadinessProvider(config)
    assert provider.readiness_by_domain == {"L": initial}
    provider.multiplier(_context(1, 1.0))
    assert provider.transition("L").opening_readiness == initial


def test_red_decay_is_exact_monotone_bounded_and_generates_no_credit() -> None:
    engine = _signal_engine(
        "v3", rate=1.0, cycle_ticks=20, green_ticks=1, offset=1, tau_red=5.0
    )
    _run_signal(engine, 10, demand_count=20)
    red = [
        item
        for item in engine.discharge_readiness_evidence
        if item.transition_mode == RED_DECAY
    ]
    assert red
    closings = [item.closing_readiness for item in red]
    assert closings == sorted(closings, reverse=True)
    assert closings[-1] == pytest.approx(exp(-len(red) / 5.0))
    assert all(item.effective_continuous_allowance == 0.0 for item in red)
    assert all(item.whole_service_exposed == 0 for item in red)


def test_short_red_retains_more_readiness_and_has_less_restart_loss() -> None:
    def restart(red_ticks: int) -> tuple[float, float]:
        provider = ExponentialDischargeReadinessProvider(
            _config((("L", 1.0),), controlled=("L",), tau_green=2.0, tau_red=5.0)
        )
        for tick in range(1, red_ticks + 1):
            provider.multiplier(_context(tick, 0.0))
        mean = provider.multiplier(_context(red_ticks + 1, 1.0))
        return provider.transition("L").opening_readiness, 1.0 - mean

    short = restart(1)
    medium = restart(5)
    long = restart(20)
    assert short[0] > medium[0] > long[0]
    assert short[1] < medium[1] < long[1]


def test_v3_ggrr_avoids_v1_aliasing_and_adds_restart_loss_to_v2() -> None:
    counts = {}
    for policy in ("v1", "v2", "v3"):
        engine = _signal_engine(policy, offset=2, tau_green=2.0, tau_red=10.0)
        counts[policy] = len(_run_signal(engine, 320))
    assert counts["v1"] == 0
    assert counts["v2"] == 40
    assert 0 < counts["v3"] < counts["v2"]


def test_no_demand_red_resets_to_one_then_new_demand_is_deterministic() -> None:
    provider = ExponentialDischargeReadinessProvider(
        _config((("L", 1.0),), controlled=("L",), initial=0.2, tau_red=2.0)
    )
    for tick in range(1, 11):
        provider.multiplier(_context(tick, 0.0, demand=False))
    assert provider.readiness_by_domain["L"] == 1.0
    provider.multiplier(_context(11, 0.0, demand=True))
    assert provider.transition("L").opening_readiness == 1.0
    assert provider.readiness_by_domain["L"] == pytest.approx(exp(-0.5))


def test_receiving_closure_does_not_fabricate_supply_or_bank_sending_burst() -> None:
    movement = MovementSpec("U", "D", signal_group_id=None)
    node = Node(
        "N",
        ("U",),
        ("D",),
        junction_spec=JunctionSpec("N", ("U",), ("D",), movement_specs=(movement,)),
    )
    engine = DischargeReadinessFractionalServiceLoadingEngine(
        links={
            "U": _link("U", 0.75),
            "D": _link("D", 0.75, storage=1, lag=100),
        },
        nodes=(node,),
        node_transfer_policy=GeneralMovementAllocator((node,)),
        discharge_readiness_config=_config(
            (("U", 0.75), ("D", 0.75)), controlled=("U",), initial=0.0
        ),
    )
    engine.instantiate(DemandDeclaration("blocker", 0, ("D",)))
    engine.instantiate(DemandDeclaration("flow", 0, ("U", "D")))
    for _ in range(20):
        engine.step()
    assert not any(
        event.packet_id == "flow"
        and event.event_type == EventType.LINK_ENTRY
        and event.entity_id == "D"
        for event in engine.event_log
    )
    sending = [
        item
        for item in engine.fractional_service_credit_evidence
        if item.service_domain_type == "link_sending" and item.service_domain_id == "U"
    ]
    assert max(item.whole_service_exposed for item in sending) <= 1
    assert all(item.closing_fractional_credit < 1.0 for item in sending)
    assert engine.check_conservation()


class _MixedV3Engine(DischargeReadinessFractionalServiceMixin, LaneGroupLoadingEngine):
    pass


@pytest.mark.parametrize(
    ("representation", "green_moves"),
    (
        (SHARED_LINK_FIFO, False),
        (MOVEMENT_PARTIAL_FIFO, True),
        (EXPLICIT_LANE_GROUP_FIFO, True),
    ),
)
def test_mixed_movements_share_one_readiness_and_capacity_account(
    representation: str, green_moves: bool
) -> None:
    links = {name: _link(name, 2.0) for name in ("U", "G", "R")}
    green = MovementSpec("U", "G", signal_group_id="green")
    red = MovementSpec("U", "R", signal_group_id="red")
    node = Node(
        "N",
        ("U",),
        ("G", "R"),
        junction_spec=JunctionSpec("N", ("U",), ("G", "R"), movement_specs=(green, red)),
    )
    provenance = LaneGroupProvenance("v3-mixed-synthetic", 1.0, "declared")
    groups = (
        ExplicitLaneGroup("green-group", "N", "U", (green.movement_id,), 1, provenance),
        ExplicitLaneGroup("red-group", "N", "U", (red.movement_id,), 1, provenance),
    )
    engine = _MixedV3Engine(
        links=links,
        nodes=(node,),
        lane_group_config=LaneGroupExtensionConfig(representation, groups),
        discharge_readiness_config=_config(
            (("U", 2.0), ("G", 2.0), ("R", 2.0)),
            controlled=("U",),
            tau_red=None,
        ),
    )
    engine.set_signal_group_open("green", True)
    engine.set_signal_group_open("red", False)
    engine.instantiate(DemandDeclaration("red-first", 0, ("U", "R")))
    engine.instantiate(DemandDeclaration("green-second", 0, ("U", "G")))
    engine.step()
    green_entries = [
        event for event in engine.event_log
        if event.event_type == EventType.LINK_ENTRY and event.entity_id == "G"
    ]
    red_entries = [
        event for event in engine.event_log
        if event.event_type == EventType.LINK_ENTRY and event.entity_id == "R"
    ]
    assert bool(green_entries) is green_moves
    assert not red_entries
    u_records = [
        item for item in engine.fractional_service_credit_evidence
        if item.service_domain_type == "link_sending" and item.service_domain_id == "U"
    ]
    assert {item.service_account_id for item in u_records} == {"effective-rate:sending:U"}
    assert u_records[0].whole_service_exposed == 2


def test_exact_continuous_dynamics_are_timestep_invariant_up_to_packetisation() -> None:
    results = []
    for dt in (0.5, 1.0, 2.0):
        provider = ExponentialDischargeReadinessProvider(
            _config(
                (("L", 0.75 * dt),),
                controlled=("L",),
                dt=dt,
                tau_green=2.0,
                initial=0.0,
            )
        )
        means = []
        ticks = int(20 / dt)
        for tick in range(1, ticks + 1):
            means.append(provider.multiplier(_context(tick, 1.0)))
        integrated_readiness = sum(means) * dt
        results.append((provider.readiness_by_domain["L"], integrated_readiness))
    for closing, integral in results:
        assert closing == pytest.approx(1.0 - exp(-10.0), abs=1e-12)
        assert integral == pytest.approx(20.0 - 2.0 * (1.0 - exp(-10.0)), abs=1e-12)


def test_evidence_modes_preserve_physics_and_logical_digest() -> None:
    engines = []
    for mode in (FORENSIC_EVIDENCE, COMPACT_EVIDENCE, SUMMARY_EVIDENCE):
        engine = _signal_engine("v3", evidence_mode=mode, tau_red=10.0)
        _run_signal(engine, 80, demand_count=100)
        engines.append(engine)
    assert engines[0].event_log == engines[1].event_log == engines[2].event_log
    assert len({engine.logical_evidence_digest for engine in engines}) == 1
    assert len({engine.logical_evidence_record_count for engine in engines}) == 1
    retained = [engine.retained_logical_evidence_record_count for engine in engines]
    assert retained[0] > retained[1] > retained[2] == 0
    assert len({engine.discharge_readiness_config.config_hash for engine in engines}) == 1
    assert len(
        {engine.discharge_readiness_config.recording_config_hash for engine in engines}
    ) == 3


def test_configuration_and_readiness_evidence_round_trip_and_tamper() -> None:
    config = _config((("U", 0.25), ("D", 10.0)), controlled=("U",))
    assert DischargeReadinessConfig.from_dict(config.to_dict()) == config
    engine = _signal_engine("v3")
    _run_signal(engine, 4, demand_count=4)
    record = engine.discharge_readiness_evidence[0]
    assert DischargeReadinessEvidence.from_dict(record.to_dict()) == record
    tampered = deepcopy(record.to_dict())
    tampered["closing_readiness"] = 0.123
    with pytest.raises(DischargeReadinessIntegrityError, match="hash mismatch"):
        DischargeReadinessEvidence.from_dict(tampered)
