"""Canonical de Souza Figure 9 merge-priority validation fixtures.

The fixture configures the frozen loading kernel; it does not implement a
second merge allocator or modify loading semantics.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import DemandDeclaration, Event, EventType, Link, Node
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.validation import ValidationContext
from urban_cybernetics.validation.physical import assess_physical_parameter_eligibility


FIGURE9_FINAL_TICK = 120
FIGURE9_FREE_FLOW_TICKS = 5
FIGURE9_LINK_LENGTH_M = 150.0
FIGURE9_FREE_FLOW_SPEED_MPS = 30.0
FIGURE9_BACKWARD_WAVE_SPEED_MPS = 6.0
FIGURE9_JAM_DENSITY_VEH_PER_M = 0.1
FIGURE9_CAPACITY_VEH_PER_SECOND = 0.5
FIGURE9_EQUAL_CASE_ID = "M8-PUB-DSOUZA-FIG9-EQUAL-DT1"
FIGURE9_EQUAL_PRIORITY_SEQUENCE = ("L1", "L2")
FIGURE9_EQUAL_PRIORITY_WEIGHTS = (("L1", 1), ("L2", 1))
FIGURE9_ASYMMETRIC_CASE_ID = "M8-PUB-DSOUZA-FIG9-ASYMMETRIC-DT1"
FIGURE9_ASYMMETRIC_ALPHA_1 = 0.75
FIGURE9_ASYMMETRIC_PRIORITY_SEQUENCE = ("L1", "L1", "L1", "L2")
FIGURE9_ASYMMETRIC_PRIORITY_WEIGHTS = (("L1", 3), ("L2", 1))


@dataclass(frozen=True, slots=True)
class Figure9Result:
    """Complete replayable evidence for one Figure 9 merge case."""

    case_id: str
    alpha_1: float
    priority_sequence: tuple[str, ...]
    priority_weights: tuple[tuple[str, int], ...]
    declared_departures_l1: tuple[int, ...]
    declared_departures_l2: tuple[int, ...]
    cumulative_outflow_l1: tuple[int, ...]
    cumulative_outflow_l2: tuple[int, ...]
    cumulative_inflow_l3: tuple[int, ...]
    outflow_per_tick_l1: tuple[int, ...]
    outflow_per_tick_l2: tuple[int, ...]
    inflow_per_tick_l3: tuple[int, ...]
    eligible_queue_l1: tuple[int, ...]
    eligible_queue_l2: tuple[int, ...]
    transfer_source_by_tick: tuple[tuple[int, tuple[str, ...]], ...]
    constrained_service_sources_through_t40: tuple[str, ...]
    constrained_service_count_l1_through_t40: int
    constrained_service_count_l2_through_t40: int
    event_count: int
    event_log_sha256: str
    conservation_check: bool
    downstream_closure_check: bool
    fifo_check: bool
    queue_retention_check: bool
    post_change_discharge_check: bool
    priority_allocation_check: bool
    identity_check: bool
    physical_eligibility_check: bool
    canonical_event_ordering_check: bool
    replay_check: bool

    @property
    def all_checks_pass(self) -> bool:
        return all((
            self.conservation_check,
            self.downstream_closure_check,
            self.fifo_check,
            self.queue_retention_check,
            self.post_change_discharge_check,
            self.priority_allocation_check,
            self.identity_check,
            self.physical_eligibility_check,
            self.canonical_event_ordering_check,
            self.replay_check,
        ))


def figure9_departures_l1() -> tuple[int, ...]:
    """Resolve d1=0.3 veh/s through the 120-second horizon."""

    return _floored_departures(lambda time: 0.3 * time)


def figure9_departures_l2() -> tuple[int, ...]:
    """Resolve d2=0.3 veh/s before 40 s and 0.1 veh/s afterwards."""

    return _floored_departures(
        lambda time: 0.3 * time if time <= 40 else 12 + 0.1 * (time - 40)
    )


def run_figure9_equal_priority() -> Figure9Result:
    """Run Figure 9(a-c) with equal 1:1 merge priorities."""

    return _run_case(
        case_id=FIGURE9_EQUAL_CASE_ID,
        alpha_1=0.5,
        priority_sequence=FIGURE9_EQUAL_PRIORITY_SEQUENCE,
        priority_weights=FIGURE9_EQUAL_PRIORITY_WEIGHTS,
    )


def run_figure9_asymmetric_priority() -> Figure9Result:
    """Run Figure 9(d-f) with the intended 3:1 merge priority for link 1."""

    return _run_case(
        case_id=FIGURE9_ASYMMETRIC_CASE_ID,
        alpha_1=FIGURE9_ASYMMETRIC_ALPHA_1,
        priority_sequence=FIGURE9_ASYMMETRIC_PRIORITY_SEQUENCE,
        priority_weights=FIGURE9_ASYMMETRIC_PRIORITY_WEIGHTS,
    )


def _run_case(
    *,
    case_id: str,
    alpha_1: float,
    priority_sequence: tuple[str, ...],
    priority_weights: tuple[tuple[str, int], ...],
) -> Figure9Result:
    departures_l1 = figure9_departures_l1()
    departures_l2 = figure9_departures_l2()
    engine, traces = _run_engine(priority_weights, departures_l1, departures_l2)
    replay, replay_traces = _run_engine(priority_weights, departures_l1, departures_l2)
    events = engine.event_log
    g1 = _cumulative(events, EventType.LINK_EXIT, "L1")
    g2 = _cumulative(events, EventType.LINK_EXIT, "L2")
    f3 = _cumulative(events, EventType.LINK_ENTRY, "L3")
    entries_l1 = _cumulative(events, EventType.LINK_ENTRY, "L1")
    entries_l2 = _cumulative(events, EventType.LINK_ENTRY, "L2")
    queue_l1 = _eligible_queue(entries_l1, g1)
    queue_l2 = _eligible_queue(entries_l2, g2)
    source_by_tick = _transfer_sources(events)
    l1_exit_order = _event_packet_ids(events, EventType.LINK_EXIT, "L1")
    l2_exit_order = _event_packet_ids(events, EventType.LINK_EXIT, "L2")
    l1_entry_order = _event_packet_ids(events, EventType.LINK_ENTRY, "L1")
    l2_entry_order = _event_packet_ids(events, EventType.LINK_ENTRY, "L2")
    instantiated = _event_packet_ids(events, EventType.INSTANTIATED, None)
    context = ValidationContext.from_engine(
        engine,
        nodes=tuple(engine.nodes.values()),
        run_config={"case_id": case_id, "alpha_1": alpha_1},
    )
    physical = assess_physical_parameter_eligibility(tuple(engine.links.values()))
    constrained_sources = _constrained_approval_sources(traces, end_tick=40)
    event_digest = hashlib.sha256(
        repr(tuple((event.physical_tick, event.sequence_number, event.event_type.value,
                    event.packet_id, event.entity_id) for event in events)).encode("utf-8")
    ).hexdigest()
    return Figure9Result(
        case_id=case_id,
        alpha_1=alpha_1,
        priority_sequence=priority_sequence,
        priority_weights=priority_weights,
        declared_departures_l1=departures_l1,
        declared_departures_l2=departures_l2,
        cumulative_outflow_l1=g1,
        cumulative_outflow_l2=g2,
        cumulative_inflow_l3=f3,
        outflow_per_tick_l1=_per_tick(g1),
        outflow_per_tick_l2=_per_tick(g2),
        inflow_per_tick_l3=_per_tick(f3),
        eligible_queue_l1=queue_l1,
        eligible_queue_l2=queue_l2,
        transfer_source_by_tick=source_by_tick,
        constrained_service_sources_through_t40=constrained_sources,
        constrained_service_count_l1_through_t40=constrained_sources.count("L1"),
        constrained_service_count_l2_through_t40=constrained_sources.count("L2"),
        event_count=len(events),
        event_log_sha256=event_digest,
        conservation_check=engine.check_conservation(),
        downstream_closure_check=all(total == first + second for total, first, second in zip(f3, g1, g2)),
        fifo_check=(
            l1_exit_order == l1_entry_order[:len(l1_exit_order)]
            and l2_exit_order == l2_entry_order[:len(l2_exit_order)]
        ),
        queue_retention_check=(
            max(queue_l1[:41]) > 0
            and max(queue_l2[:41]) > 0
            and (alpha_1 == 0.5 or max(queue_l2[:41]) > max(queue_l1[:41]))
        ),
        post_change_discharge_check=(
            max(queue_l1[40:]) > 0 and queue_l1[-1] == 0
            and max(queue_l2[40:]) > queue_l2[-1]
        ),
        priority_allocation_check=(
            len(constrained_sources) >= len(priority_sequence)
            and abs(
                constrained_sources.count("L1")
                - alpha_1 * len(constrained_sources)
            ) <= 1.0
        ),
        identity_check=(
            len(instantiated) == len(departures_l1) + len(departures_l2)
            and len(set(instantiated)) == len(instantiated)
            and context.count_consistency_report.is_consistent
            and engine.check_event_cache_consistency()
        ),
        physical_eligibility_check=physical.is_parity_eligible,
        canonical_event_ordering_check=_canonical_event_order(events),
        replay_check=(replay.event_log == events and replay_traces == traces),
    )


def _run_engine(
    priority_weights: tuple[tuple[str, int], ...],
    departures_l1: tuple[int, ...],
    departures_l2: tuple[int, ...],
) -> tuple[LoadingEngine, tuple[tuple[object, ...], ...]]:
    links = {link_id: _link(link_id) for link_id in ("L1", "L2", "L3")}
    engine = LoadingEngine(
        links=links,
        nodes=(Node(
            "N1",
            incoming_link_ids=("L1", "L2"),
            outgoing_link_ids=("L3",),
            merge_priorities=priority_weights,
        ),),
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        parity_sending_capacity_vehicles_per_tick_by_link={
            "L1": 0.5, "L2": 0.5, "L3": 0.5,
        },
        parity_receiving_capacity_vehicles_per_tick_by_link={
            "L1": 0.5, "L2": 0.5, "L3": 0.5,
        },
        parity_initial_receiving_credit_by_link={"L3": 0.0},
    )
    for index, departure in enumerate(departures_l1, start=1):
        engine.instantiate(DemandDeclaration(
            f"DESOUZA-FIG9-L1-D{index:03d}", departure, ("L1", "L3")
        ))
    for index, departure in enumerate(departures_l2, start=1):
        engine.instantiate(DemandDeclaration(
            f"DESOUZA-FIG9-L2-D{index:03d}", departure, ("L2", "L3")
        ))
    traces: list[tuple[object, ...]] = []
    while engine.current_tick < FIGURE9_FINAL_TICK:
        engine.step()
        traces.append(tuple(engine.allocation_traces()))
    return engine, tuple(traces)


def _link(link_id: str) -> Link:
    return Link(
        link_id=link_id,
        length_m=FIGURE9_LINK_LENGTH_M,
        lane_count=1,
        free_flow_speed_mps=FIGURE9_FREE_FLOW_SPEED_MPS,
        backward_wave_speed_mps=FIGURE9_BACKWARD_WAVE_SPEED_MPS,
        jam_density_veh_per_km_per_lane=FIGURE9_JAM_DENSITY_VEH_PER_M * 1000,
        capacity_veh_per_hour_per_lane=FIGURE9_CAPACITY_VEH_PER_SECOND * 3600,
        tick_duration_seconds=1.0,
        declared_sending_capacity_per_tick=0,
        declared_receiving_capacity_per_tick=0,
    )


def _floored_departures(cumulative_at_time) -> tuple[int, ...]:
    departures: list[int] = []
    previous = 0
    for tick in range(1, FIGURE9_FINAL_TICK + 1):
        target = math.floor(cumulative_at_time(tick) + 1e-12)
        departures.extend(tick for _ in range(previous, target))
        previous = target
    return tuple(departures)


def _cumulative(
    events: tuple[Event, ...], event_type: EventType, entity_id: str,
) -> tuple[int, ...]:
    counts = [0] * (FIGURE9_FINAL_TICK + 1)
    for event in events:
        if event.event_type == event_type and event.entity_id == entity_id:
            counts[event.physical_tick] += 1
    running = 0
    values = []
    for count in counts:
        running += count
        values.append(running)
    return tuple(values)


def _per_tick(cumulative: tuple[int, ...]) -> tuple[int, ...]:
    return (cumulative[0],) + tuple(
        current - previous for previous, current in zip(cumulative, cumulative[1:])
    )


def _eligible_queue(
    cumulative_entries: tuple[int, ...], cumulative_exits: tuple[int, ...],
) -> tuple[int, ...]:
    return tuple(
        cumulative_entries[max(0, tick - FIGURE9_FREE_FLOW_TICKS)] - cumulative_exits[tick]
        for tick in range(FIGURE9_FINAL_TICK + 1)
    )


def _transfer_sources(events: tuple[Event, ...]) -> tuple[tuple[int, tuple[str, ...]], ...]:
    by_tick: list[list[str]] = [[] for _ in range(FIGURE9_FINAL_TICK + 1)]
    packet_source = {
        event.packet_id: event.entity_id
        for event in events
        if event.event_type == EventType.LINK_ENTRY and event.entity_id in {"L1", "L2"}
    }
    for event in events:
        if event.event_type == EventType.LINK_ENTRY and event.entity_id == "L3":
            by_tick[event.physical_tick].append(packet_source[event.packet_id])
    return tuple((tick, tuple(sources)) for tick, sources in enumerate(by_tick))


def _event_packet_ids(
    events: tuple[Event, ...], event_type: EventType, entity_id: str | None,
) -> tuple[str, ...]:
    return tuple(
        event.packet_id for event in events
        if event.event_type == event_type
        and (entity_id is None or event.entity_id == entity_id)
    )


def _canonical_event_order(events: tuple[Event, ...]) -> bool:
    return all(
        current.sequence_number < following.sequence_number
        and current.physical_tick <= following.physical_tick
        for current, following in zip(events, events[1:])
    )


def _constrained_approval_sources(
    traces: tuple[tuple[object, ...], ...], *, end_tick: int,
) -> tuple[str, ...]:
    sources: list[str] = []
    for tick, tick_traces in enumerate(traces, start=1):
        if tick > end_tick:
            break
        for trace in tick_traces:
            summaries = trace.movement_flow_summaries
            if len(summaries) != 2 or not all(item.requested_count for item in summaries):
                continue
            for summary in summaries:
                sources.extend(summary.upstream_link_id for _ in range(summary.approved_count))
    return tuple(sources)
