"""Reusable adversarial fixtures and invariant checks for parity torture tests."""

from __future__ import annotations

from dataclasses import dataclass
from random import Random

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import DemandDeclaration, EventType, Link, Node
from urban_cybernetics.loading import (
    ENTRY_BOUNDARY,
    EXIT_BOUNDARY,
    LoadingEngine,
    packet_ids_on_link_from_events,
)
from urban_cybernetics.validation import build_spillback_validation_report
from urban_cybernetics.validation import build_commodity_parity_validation_report


@dataclass(frozen=True, slots=True)
class StressScenario:
    """Small reproducible randomized case for parity-kernel falsification."""

    seed: int
    topology_kind: str
    links: dict[str, Link]
    nodes: tuple[Node, ...]
    demands: tuple[DemandDeclaration, ...]
    closures_by_tick: tuple[tuple[int, str, bool], ...] = ()
    sending_rates: dict[str, float] | None = None
    receiving_rates: dict[str, float] | None = None
    horizon: int = 18

    def build_engine(self) -> LoadingEngine:
        return parity_engine(
            links=self.links,
            nodes=self.nodes,
            sending_rates=self.sending_rates,
            receiving_rates=self.receiving_rates,
        )

    def describe(self) -> str:
        closure_items = ",".join(
            f"{tick}:{link_id}:{is_open}"
            for tick, link_id, is_open in self.closures_by_tick
        )
        demand_items = ",".join(
            f"{demand.demand_id}@{demand.departure_tick}:{'->'.join(demand.route_intent)}"
            for demand in self.demands
        )
        link_items = ",".join(
            f"{link_id}(ff={link.free_flow_ticks},s={link.declared_sending_capacity_per_tick},"
            f"r={link.declared_receiving_capacity_per_tick},k={link.declared_storage_capacity_packets})"
            for link_id, link in sorted(self.links.items())
        )
        return (
            f"seed={self.seed};kind={self.topology_kind};links={link_items};"
            f"demands={demand_items};closures={closure_items};"
            f"sending_rates={self.sending_rates};receiving_rates={self.receiving_rates};"
            f"horizon={self.horizon}"
        )


def physical_link(
    link_id: str,
    *,
    storage: int = 8,
    sending_capacity: int = 4,
    receiving_capacity: int = 4,
    free_flow_ticks: int | None = 1,
    backward_wave_speed_mps: float = 5.0,
) -> Link:
    return Link(
        link_id=link_id,
        free_flow_ticks=free_flow_ticks,
        declared_sending_capacity_per_tick=sending_capacity,
        declared_receiving_capacity_per_tick=receiving_capacity,
        declared_storage_capacity_packets=storage,
        length_m=10.0,
        lane_count=1,
        free_flow_speed_mps=10.0,
        jam_density_veh_per_km_per_lane=100.0,
        backward_wave_speed_mps=backward_wave_speed_mps,
        capacity_veh_per_hour_per_lane=1200.0,
        tick_duration_seconds=1.0,
    )


def parity_engine(
    *,
    links: dict[str, Link],
    nodes: tuple[Node, ...] = (),
    sending_rates: dict[str, float] | None = None,
    receiving_rates: dict[str, float] | None = None,
) -> LoadingEngine:
    return LoadingEngine(
        links=links,
        nodes=nodes,
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        parity_sending_capacity_vehicles_per_tick_by_link=sending_rates,
        parity_receiving_capacity_vehicles_per_tick_by_link=receiving_rates,
    )


def demand(
    demand_id: str,
    route_intent: tuple[str, ...],
    *,
    departure_tick: int = 0,
) -> DemandDeclaration:
    return DemandDeclaration(
        demand_id=demand_id,
        departure_tick=departure_tick,
        route_intent=route_intent,
    )


def instantiate_demands(
    engine: LoadingEngine,
    demands: tuple[DemandDeclaration, ...],
) -> None:
    for declaration in demands:
        engine.instantiate(declaration)


def run_ticks(
    engine: LoadingEngine,
    ticks: int,
    *,
    closures_by_tick: tuple[tuple[int, str, bool], ...] = (),
) -> None:
    closures = {}
    for tick, link_id, is_open in closures_by_tick:
        closures.setdefault(tick, []).append((link_id, is_open))

    for _ in range(ticks):
        for link_id, is_open in closures.get(engine.current_tick, ()):
            engine.set_receiving_open(link_id, is_open)
        engine.step()
        assert_core_invariants(engine)


def run_scenario(scenario: StressScenario) -> LoadingEngine:
    engine = scenario.build_engine()
    instantiate_demands(engine, scenario.demands)
    assert_core_invariants(engine)
    run_ticks(
        engine,
        scenario.horizon,
        closures_by_tick=scenario.closures_by_tick,
    )
    return engine


def link_event_packet_ids(
    engine: LoadingEngine,
    event_type: EventType,
    link_id: str,
    tick: int | None = None,
) -> list[str]:
    return [
        event.packet_id
        for event in engine.event_log
        if event.event_type == event_type
        and event.entity_id == link_id
        and (tick is None or event.physical_tick == tick)
    ]


def boundary_event_packet_ids(
    engine: LoadingEngine,
    event_type: EventType,
    boundary_id: str,
    tick: int | None = None,
) -> list[str]:
    return [
        event.packet_id
        for event in engine.event_log
        if event.event_type == event_type
        and event.entity_id == boundary_id
        and (tick is None or event.physical_tick == tick)
    ]


def realised_path(engine: LoadingEngine, packet_id: str) -> tuple[str, ...]:
    return tuple(
        event.entity_id
        for event in engine.event_log
        if event.packet_id == packet_id and event.event_type == EventType.LINK_ENTRY
    )


def queue_lengths_by_tick(
    engine: LoadingEngine,
    boundary_id: str,
) -> tuple[int, ...]:
    report = build_spillback_validation_report(
        engine,
        boundary_ids=(boundary_id,),
    )
    return tuple(point.queue_length for point in report.boundary_traces[0].queue_curve)


def assert_core_invariants(engine: LoadingEngine) -> None:
    assert engine.check_event_cache_consistency()
    assert engine.check_conservation()
    assert engine.count_consistency_report().is_consistent
    assert_monotone_counts_and_storage_bounds(engine)
    assert_route_counts_sum_to_aggregate(engine)
    assert_packet_ordinals_are_unique(engine)
    assert_link_fifo(engine)
    assert_queue_consistency(engine)
    assert_trace_bounds(engine)
    assert_commodity_parity(engine)


def assert_monotone_counts_and_storage_bounds(engine: LoadingEngine) -> None:
    for link_id, link in engine.links.items():
        previous_entries = 0
        previous_exits = 0
        for tick in range(engine.current_tick + 1):
            counts = engine.cumulative_counts(link_id, tick)
            assert counts.entries >= previous_entries, (link_id, tick, counts)
            assert counts.exits >= previous_exits, (link_id, tick, counts)
            assert counts.exits <= counts.entries, (link_id, tick, counts)
            storage = engine.link_storage(link_id, tick).storage
            assert storage == counts.entries - counts.exits, (link_id, tick, storage)
            assert storage >= 0, (link_id, tick, storage)
            assert storage <= link.declared_storage_capacity_packets, (
                link_id,
                tick,
                storage,
                link.declared_storage_capacity_packets,
            )
            previous_entries = counts.entries
            previous_exits = counts.exits


def assert_route_counts_sum_to_aggregate(engine: LoadingEngine) -> None:
    projection = engine.cumulative_count_projection()
    if not projection.route_counts_supported:
        return

    route_counts_by_link_tick: dict[tuple[str, int], tuple[int, int]] = {}
    for counts in projection.route_counts:
        key = (counts.link_id, counts.tick)
        current_entries, current_exits = route_counts_by_link_tick.get(key, (0, 0))
        route_counts_by_link_tick[key] = (
            current_entries + counts.entries,
            current_exits + counts.exits,
        )

    for counts in projection.aggregate_counts:
        assert route_counts_by_link_tick.get(
            (counts.link_id, counts.tick),
            (0, 0),
        ) == (counts.entries, counts.exits), counts


def assert_packet_ordinals_are_unique(engine: LoadingEngine) -> None:
    aggregate_keys = set()
    route_keys = set()
    packet_boundary_keys = set()
    for ordinal in engine.packet_boundary_ordinals():
        aggregate_key = (
            ordinal.boundary_type,
            ordinal.link_id,
            ordinal.aggregate_ordinal,
        )
        assert aggregate_key not in aggregate_keys, ordinal
        aggregate_keys.add(aggregate_key)

        route_key = (
            ordinal.boundary_type,
            ordinal.link_id,
            ordinal.route_key,
            ordinal.route_ordinal,
        )
        assert route_key not in route_keys, ordinal
        route_keys.add(route_key)

        packet_boundary_key = (
            ordinal.packet_id,
            ordinal.boundary_type,
            ordinal.link_id,
        )
        assert packet_boundary_key not in packet_boundary_keys, ordinal
        packet_boundary_keys.add(packet_boundary_key)


def assert_link_fifo(engine: LoadingEngine) -> None:
    for link_id in engine.links:
        entries = link_event_packet_ids(engine, EventType.LINK_ENTRY, link_id)
        exits = link_event_packet_ids(engine, EventType.LINK_EXIT, link_id)
        entry_positions = {packet_id: index for index, packet_id in enumerate(entries)}
        exit_positions = [entry_positions[packet_id] for packet_id in exits]
        assert exit_positions == sorted(exit_positions), (link_id, entries, exits)


def assert_queue_consistency(engine: LoadingEngine) -> None:
    queue_by_boundary: dict[str, list[str]] = {}
    for event in engine.event_log:
        if event.event_type == EventType.QUEUE_ENTRY:
            queue_by_boundary.setdefault(event.entity_id, []).append(event.packet_id)
        elif event.event_type == EventType.QUEUE_EXIT:
            queue = queue_by_boundary.setdefault(event.entity_id, [])
            assert queue, (event.entity_id, event.packet_id)
            assert queue[0] == event.packet_id, (event.entity_id, queue, event.packet_id)
            queue.pop(0)

    for boundary_id, queued_ids in queue_by_boundary.items():
        upstream_link_id, downstream_link_id = parse_boundary_id(boundary_id)
        assert tuple(queued_ids) == engine.packet_ids_in_queue(
            upstream_link_id,
            downstream_link_id,
        )

    for link_id in engine.links:
        assert engine.link_storage(link_id).storage == len(
            packet_ids_on_link_from_events(
                engine.event_log,
                link_id,
                engine.current_tick,
            )
        )


def assert_trace_bounds(engine: LoadingEngine) -> None:
    if engine.model_profile_id != ACADEMIC_LTM_PARITY_PROFILE_ID:
        return

    for link_id in engine.links:
        for tick in range(engine.current_tick + 1):
            sending_trace = engine.parity_link_sending_trace(link_id, tick=tick)
            assert len(sending_trace.sendable_packet_ids) <= len(
                sending_trace.eligible_packet_ids
            ), sending_trace
            assert len(sending_trace.sendable_packet_ids) <= max(
                sending_trace.integer_capacity,
                0,
            ), sending_trace

            receiving_view = engine.parity_link_supply_view(link_id, tick=tick)
            assert receiving_view.available_receiving_slots >= 0, receiving_view
            assert receiving_view.available_receiving_slots <= max(
                receiving_view.vacancy.available_physical_vacancy,
                0,
            ), receiving_view
            assert receiving_view.available_receiving_slots <= max(
                receiving_view.available_receiving_capacity,
                0,
            ), receiving_view


def assert_commodity_parity(engine: LoadingEngine) -> None:
    if engine.model_profile_id != ACADEMIC_LTM_PARITY_PROFILE_ID:
        return

    report = build_commodity_parity_validation_report(engine)
    assert report.is_valid, report.invariant_violations


def assert_same_events(first: LoadingEngine, second: LoadingEngine) -> None:
    assert first.event_log == second.event_log
    assert dict(first.packets) == dict(second.packets)
    assert first.conservation_summary() == second.conservation_summary()


def parse_boundary_id(boundary_id: str) -> tuple[str, str]:
    return tuple(boundary_id.removeprefix("boundary:").split("->", 1))  # type: ignore[return-value]


def random_stress_scenario(seed: int) -> StressScenario:
    rng = Random(seed)
    topology_kind = rng.choice(("chain", "diverge", "merge"))
    if topology_kind == "chain":
        return _random_chain_scenario(seed, rng)
    if topology_kind == "diverge":
        return _random_diverge_scenario(seed, rng)
    return _random_merge_scenario(seed, rng)


def _random_link(link_id: str, rng: Random) -> Link:
    return physical_link(
        link_id,
        storage=rng.randint(1, 5),
        sending_capacity=rng.randint(1, 3),
        receiving_capacity=rng.randint(1, 3),
        free_flow_ticks=rng.randint(1, 2),
        backward_wave_speed_mps=rng.choice((2.5, 5.0, 10.0)),
    )


def _random_chain_scenario(seed: int, rng: Random) -> StressScenario:
    link_count = rng.randint(1, 4)
    link_ids = tuple(f"L{index}" for index in range(1, link_count + 1))
    links = {link_id: _random_link(link_id, rng) for link_id in link_ids}
    nodes = tuple(
        Node(
            f"N{index}",
            incoming_link_ids=(link_ids[index],),
            outgoing_link_ids=(link_ids[index + 1],),
        )
        for index in range(link_count - 1)
    )
    demands = tuple(
        demand(f"D{index}", link_ids, departure_tick=rng.randint(0, 4))
        for index in range(rng.randint(1, 8))
    )
    return StressScenario(
        seed=seed,
        topology_kind="chain",
        links=links,
        nodes=nodes,
        demands=demands,
        receiving_rates=_random_fractional_rates(link_ids, rng),
    )


def _random_diverge_scenario(seed: int, rng: Random) -> StressScenario:
    links = {link_id: _random_link(link_id, rng) for link_id in ("L1", "L2", "L3")}
    nodes = (
        Node(
            "N-diverge",
            incoming_link_ids=("L1",),
            outgoing_link_ids=("L2", "L3"),
        ),
    )
    routes = (("L1", "L2"), ("L1", "L3"))
    demands = tuple(
        demand(f"D{index}", rng.choice(routes), departure_tick=rng.randint(0, 4))
        for index in range(rng.randint(2, 9))
    )
    closures = _random_closures(("L2", "L3"), rng)
    return StressScenario(
        seed=seed,
        topology_kind="diverge",
        links=links,
        nodes=nodes,
        demands=demands,
        closures_by_tick=closures,
        sending_rates=_random_fractional_rates(("L1",), rng),
    )


def _random_merge_scenario(seed: int, rng: Random) -> StressScenario:
    links = {link_id: _random_link(link_id, rng) for link_id in ("L1", "L2", "L3")}
    nodes = (
        Node(
            "N-merge",
            incoming_link_ids=("L1", "L2"),
            outgoing_link_ids=("L3",),
            merge_priorities=(("L1", rng.randint(1, 3)), ("L2", rng.randint(1, 3))),
        ),
    )
    routes = (("L1", "L3"), ("L2", "L3"))
    demands = tuple(
        demand(f"D{index}", rng.choice(routes), departure_tick=rng.randint(0, 4))
        for index in range(rng.randint(2, 10))
    )
    closures = _random_closures(("L3",), rng)
    return StressScenario(
        seed=seed,
        topology_kind="merge",
        links=links,
        nodes=nodes,
        demands=demands,
        closures_by_tick=closures,
        receiving_rates=_random_fractional_rates(("L3",), rng),
    )


def _random_fractional_rates(
    link_ids: tuple[str, ...],
    rng: Random,
) -> dict[str, float] | None:
    if rng.random() > 0.4:
        return None
    return {link_id: rng.choice((0.5, 1.0, 1.5, 2.0)) for link_id in link_ids}


def _random_closures(
    link_ids: tuple[str, ...],
    rng: Random,
) -> tuple[tuple[int, str, bool], ...]:
    if rng.random() > 0.45:
        return ()
    link_id = rng.choice(link_ids)
    close_tick = rng.randint(0, 5)
    reopen_tick = close_tick + rng.randint(1, 4)
    return ((close_tick, link_id, False), (reopen_tick, link_id, True))


def assert_boundary_event_order(engine: LoadingEngine, packet_id: str) -> None:
    packet_events = [
        event for event in engine.event_log if event.packet_id == packet_id
    ]
    for index, event in enumerate(packet_events):
        if event.event_type != EventType.LINK_EXIT:
            continue
        next_event = packet_events[index + 1]
        if next_event.event_type == EventType.COMPLETED:
            continue
        assert next_event.event_type == EventType.LINK_ENTRY
        assert next_event.physical_tick == event.physical_tick
        assert event.sequence_number < next_event.sequence_number


def count_boundary_ordinals(
    engine: LoadingEngine,
    *,
    boundary_type: str,
    link_id: str,
) -> tuple[int, ...]:
    assert boundary_type in (ENTRY_BOUNDARY, EXIT_BOUNDARY)
    return tuple(
        ordinal.aggregate_ordinal
        for ordinal in engine.packet_boundary_ordinals()
        if ordinal.boundary_type == boundary_type and ordinal.link_id == link_id
    )
