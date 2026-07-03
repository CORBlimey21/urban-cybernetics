"""Event-derived cumulative link boundary count and storage views."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from urban_cybernetics.core import Event, EventType, Packet


ENTRY_BOUNDARY = "entry"
EXIT_BOUNDARY = "exit"
BOUNDARY_TYPES = frozenset((ENTRY_BOUNDARY, EXIT_BOUNDARY))
COUNT_TICK_CONVENTION = "inclusive_physical_tick"
COUNT_ORDERING_CONVENTION = "physical_tick_then_sequence_number"


@dataclass(frozen=True, slots=True)
class CumulativeBoundaryCounts:
    """Packet-unit cumulative link entries and exits through one tick."""

    link_id: str
    tick: int
    entries: int
    exits: int


@dataclass(frozen=True, slots=True)
class LinkStorageView:
    """Packet-unit link storage derived from cumulative boundary counts."""

    link_id: str
    tick: int
    storage: int


@dataclass(frozen=True, slots=True)
class PacketBoundaryOrdinal:
    """Packet identity for one cumulative boundary-count increment."""

    link_id: str
    boundary_type: str
    packet_id: str
    physical_tick: int
    sequence_number: int
    aggregate_ordinal: int
    route_key: str | None = None
    route_link_ids: tuple[str, ...] = ()
    route_ordinal: int | None = None

    def __post_init__(self) -> None:
        if self.boundary_type not in BOUNDARY_TYPES:
            raise ValueError(f"unsupported boundary_type: {self.boundary_type}")
        if self.aggregate_ordinal < 1:
            raise ValueError("aggregate_ordinal must be positive")
        if self.route_ordinal is not None and self.route_ordinal < 1:
            raise ValueError("route_ordinal must be positive")
        object.__setattr__(self, "route_link_ids", tuple(self.route_link_ids))


@dataclass(frozen=True, slots=True)
class RouteCumulativeBoundaryCounts:
    """Route-disaggregated packet-unit cumulative boundary counts."""

    link_id: str
    route_key: str
    route_link_ids: tuple[str, ...]
    tick: int
    entries: int
    exits: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_link_ids", tuple(self.route_link_ids))


@dataclass(frozen=True, slots=True)
class RouteTravelTimePoint:
    """Completed packet travel-time observation for one route commodity."""

    route_key: str
    route_link_ids: tuple[str, ...]
    packet_id: str
    departure_tick: int
    completion_tick: int
    travel_time_ticks: int
    completion_sequence_number: int
    final_link_id: str
    final_link_exit_route_ordinal: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_link_ids", tuple(self.route_link_ids))
        if self.travel_time_ticks < 0:
            raise ValueError("travel_time_ticks cannot be negative")
        if self.final_link_exit_route_ordinal < 1:
            raise ValueError("final_link_exit_route_ordinal must be positive")


@dataclass(frozen=True, slots=True)
class RouteTravelTimeCurve:
    """Route-keyed completed-packet travel-time curve."""

    route_key: str
    route_link_ids: tuple[str, ...]
    points: tuple[RouteTravelTimePoint, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_link_ids", tuple(self.route_link_ids))
        object.__setattr__(self, "points", tuple(self.points))


@dataclass(frozen=True, slots=True)
class CumulativeCountProjection:
    """Complete read-only M2 event-to-count projection for a prefix."""

    link_ids: tuple[str, ...]
    max_tick: int
    checked_event_count: int
    tick_convention: str
    ordering_convention: str
    aggregate_counts: tuple[CumulativeBoundaryCounts, ...]
    packet_ordinals: tuple[PacketBoundaryOrdinal, ...]
    route_counts: tuple[RouteCumulativeBoundaryCounts, ...] = ()
    route_travel_time_curves: tuple[RouteTravelTimeCurve, ...] = ()
    route_counts_supported: bool = False
    route_count_support_reason: str = "packet_route_intent_unavailable"

    def __post_init__(self) -> None:
        object.__setattr__(self, "link_ids", tuple(self.link_ids))
        object.__setattr__(self, "aggregate_counts", tuple(self.aggregate_counts))
        object.__setattr__(self, "packet_ordinals", tuple(self.packet_ordinals))
        object.__setattr__(self, "route_counts", tuple(self.route_counts))
        object.__setattr__(
            self,
            "route_travel_time_curves",
            tuple(self.route_travel_time_curves),
        )


@dataclass(frozen=True, slots=True)
class CountConsistencyReport:
    """Validation/provenance-ready report for M2 count projection consistency."""

    link_ids: tuple[str, ...]
    max_tick: int
    checked_event_count: int
    tick_convention: str
    ordering_convention: str
    is_consistent: bool
    ineligibility_reasons: tuple[str, ...] = ()
    route_counts_supported: bool = False
    route_count_support_reason: str = "packet_route_intent_unavailable"

    def __post_init__(self) -> None:
        object.__setattr__(self, "link_ids", tuple(self.link_ids))
        object.__setattr__(
            self,
            "ineligibility_reasons",
            tuple(self.ineligibility_reasons),
        )


def cumulative_entries(events: Iterable[Event], link_id: str, tick: int) -> int:
    """Count LINK_ENTRY events for one link up to and including tick."""

    return sum(
        event.event_type == EventType.LINK_ENTRY
        and event.entity_id == link_id
        and event.physical_tick <= tick
        for event in events
    )


def cumulative_exits(events: Iterable[Event], link_id: str, tick: int) -> int:
    """Count LINK_EXIT events for one link up to and including tick."""

    return sum(
        event.event_type == EventType.LINK_EXIT
        and event.entity_id == link_id
        and event.physical_tick <= tick
        for event in events
    )


def cumulative_counts(
    events: Iterable[Event],
    link_id: str,
    tick: int,
) -> CumulativeBoundaryCounts:
    """Return cumulative entry and exit counts for one link and tick."""

    event_tuple = tuple(events)
    return CumulativeBoundaryCounts(
        link_id=link_id,
        tick=tick,
        entries=cumulative_entries(event_tuple, link_id, tick),
        exits=cumulative_exits(event_tuple, link_id, tick),
    )


def cumulative_count_series(
    events: Iterable[Event],
    link_id: str,
    max_tick: int,
) -> tuple[CumulativeBoundaryCounts, ...]:
    """Return cumulative boundary counts for ticks 0 through max_tick."""

    if max_tick < 0:
        return ()

    event_tuple = tuple(events)
    return tuple(
        CumulativeBoundaryCounts(
            link_id=link_id,
            tick=tick,
            entries=cumulative_entries(event_tuple, link_id, tick),
            exits=cumulative_exits(event_tuple, link_id, tick),
        )
        for tick in range(max_tick + 1)
    )


def link_storage(events: Iterable[Event], link_id: str, tick: int) -> LinkStorageView:
    """Return packet-unit storage derived from cumulative entries minus exits."""

    event_tuple = tuple(events)
    counts = cumulative_counts(event_tuple, link_id, tick)
    storage = counts.entries - counts.exits
    if storage < 0:
        raise ValueError(
            f"link storage is negative for {link_id} at tick {tick}: {storage}"
        )
    return LinkStorageView(link_id=link_id, tick=tick, storage=storage)


def link_storage_series(
    events: Iterable[Event],
    link_id: str,
    max_tick: int,
) -> tuple[LinkStorageView, ...]:
    """Return count-derived link storage for ticks 0 through max_tick."""

    if max_tick < 0:
        return ()

    event_tuple = tuple(events)
    return tuple(link_storage(event_tuple, link_id, tick) for tick in range(max_tick + 1))


def packet_ids_on_link_from_events(
    events: Iterable[Event],
    link_id: str,
    tick: int,
) -> tuple[str, ...]:
    """Return packet IDs physically on one link through an inclusive tick."""

    packet_ids: list[str] = []
    for event in events:
        if event.physical_tick > tick:
            continue
        if event.entity_id != link_id:
            continue
        if event.event_type == EventType.LINK_ENTRY:
            packet_ids.append(event.packet_id)
        elif event.event_type == EventType.LINK_EXIT:
            if event.packet_id not in packet_ids:
                raise ValueError(
                    f"packet_id {event.packet_id} exits {link_id} before entering"
                )
            packet_ids.remove(event.packet_id)
    return tuple(packet_ids)


def route_key_for_packet(packet: Packet) -> str:
    """Return a deterministic route key from immutable packet route intent."""

    return "route:" + "->".join(packet.route_intent)


def packet_boundary_ordinals(
    events: Iterable[Event],
    *,
    packets: Mapping[str, Packet] | None = None,
    link_ids: Iterable[str] | None = None,
    max_tick: int | None = None,
) -> tuple[PacketBoundaryOrdinal, ...]:
    """Return packet ordinals for LINK_ENTRY and LINK_EXIT count increments."""

    link_id_filter = None if link_ids is None else set(link_ids)
    aggregate_counts_by_boundary: dict[tuple[str, str], int] = {}
    route_counts_by_boundary: dict[tuple[str, str, str], int] = {}
    ordinals: list[PacketBoundaryOrdinal] = []
    for event in _ordered_events(events):
        if max_tick is not None and event.physical_tick > max_tick:
            continue
        boundary_type = _boundary_type_for_event(event)
        if boundary_type is None:
            continue
        if link_id_filter is not None and event.entity_id not in link_id_filter:
            continue

        aggregate_key = (event.entity_id, boundary_type)
        aggregate_ordinal = aggregate_counts_by_boundary.get(aggregate_key, 0) + 1
        aggregate_counts_by_boundary[aggregate_key] = aggregate_ordinal

        route_key: str | None = None
        route_link_ids: tuple[str, ...] = ()
        route_ordinal: int | None = None
        if packets is not None:
            packet = packets.get(event.packet_id)
            if packet is None:
                raise ValueError(
                    f"event references packet_id {event.packet_id} without packet metadata"
                )
            if event.entity_id not in packet.route_intent:
                raise ValueError(
                    f"event for packet_id {event.packet_id} references link "
                    f"{event.entity_id} outside route_intent"
                )
            route_key = route_key_for_packet(packet)
            route_link_ids = packet.route_intent
            route_count_key = (event.entity_id, boundary_type, route_key)
            route_ordinal = route_counts_by_boundary.get(route_count_key, 0) + 1
            route_counts_by_boundary[route_count_key] = route_ordinal

        ordinals.append(
            PacketBoundaryOrdinal(
                link_id=event.entity_id,
                boundary_type=boundary_type,
                packet_id=event.packet_id,
                physical_tick=event.physical_tick,
                sequence_number=event.sequence_number,
                aggregate_ordinal=aggregate_ordinal,
                route_key=route_key,
                route_link_ids=route_link_ids,
                route_ordinal=route_ordinal,
            )
        )
    return tuple(ordinals)


def route_cumulative_counts(
    events: Iterable[Event],
    packets: Mapping[str, Packet],
    *,
    link_id: str,
    route_key: str,
    tick: int,
) -> RouteCumulativeBoundaryCounts:
    """Return route-disaggregated counts for one link, route key, and tick."""

    route_link_ids_by_key = _route_link_ids_by_key(packets)
    if route_key not in route_link_ids_by_key:
        raise KeyError(f"unknown route_key for cumulative counts: {route_key}")
    event_tuple = tuple(events)
    entries = 0
    exits = 0
    for event in event_tuple:
        if event.physical_tick > tick or event.entity_id != link_id:
            continue
        packet = packets.get(event.packet_id)
        if packet is None or route_key_for_packet(packet) != route_key:
            continue
        if event.event_type == EventType.LINK_ENTRY:
            entries += 1
        elif event.event_type == EventType.LINK_EXIT:
            exits += 1
    return RouteCumulativeBoundaryCounts(
        link_id=link_id,
        route_key=route_key,
        route_link_ids=route_link_ids_by_key[route_key],
        tick=tick,
        entries=entries,
        exits=exits,
    )


def route_cumulative_count_series(
    events: Iterable[Event],
    packets: Mapping[str, Packet],
    *,
    link_id: str,
    route_key: str,
    max_tick: int,
) -> tuple[RouteCumulativeBoundaryCounts, ...]:
    """Return route-disaggregated counts for ticks 0 through max_tick."""

    if max_tick < 0:
        return ()
    event_tuple = tuple(events)
    return tuple(
        route_cumulative_counts(
            event_tuple,
            packets,
            link_id=link_id,
            route_key=route_key,
            tick=tick,
        )
        for tick in range(max_tick + 1)
    )


def route_travel_time_curves(
    events: Iterable[Event],
    packets: Mapping[str, Packet],
    *,
    max_tick: int | None = None,
) -> tuple[RouteTravelTimeCurve, ...]:
    """Return route-keyed completed-packet travel-time curves.

    Curves are currently supported only for immutable route intent with no
    reroute event semantics. Each point is tied to the packet's final-link exit
    route ordinal, so completed-packet travel time remains auditable against the
    cumulative boundary-count projection.
    """

    event_tuple = tuple(events)
    instantiation_tick_by_packet_id: dict[str, int] = {}
    completion_events: list[Event] = []
    for event in event_tuple:
        if max_tick is not None and event.physical_tick > max_tick:
            continue
        if event.event_type == EventType.INSTANTIATED:
            instantiation_tick_by_packet_id[event.packet_id] = event.physical_tick
        elif event.event_type == EventType.COMPLETED:
            completion_events.append(event)

    final_exit_ordinal_by_packet_id = _final_link_exit_route_ordinals(
        event_tuple,
        packets,
        max_tick=max_tick,
    )
    points_by_route_key: dict[str, list[RouteTravelTimePoint]] = {}
    route_link_ids_by_key = _route_link_ids_by_key(packets)
    for completion in sorted(
        completion_events,
        key=lambda event: (event.physical_tick, event.sequence_number),
    ):
        packet = packets.get(completion.packet_id)
        if packet is None:
            raise ValueError(
                f"completion references packet_id {completion.packet_id} "
                "without packet metadata"
            )
        if not packet.route_intent:
            raise ValueError(f"packet_id {packet.packet_id} has empty route_intent")
        if completion.packet_id not in instantiation_tick_by_packet_id:
            raise ValueError(
                f"packet_id {completion.packet_id} completes without instantiation"
            )
        route_key = route_key_for_packet(packet)
        final_link_id = packet.route_intent[-1]
        final_exit_ordinal = final_exit_ordinal_by_packet_id.get(packet.packet_id)
        if final_exit_ordinal is None:
            raise ValueError(
                f"packet_id {packet.packet_id} completes without final-link exit ordinal"
            )
        departure_tick = instantiation_tick_by_packet_id[packet.packet_id]
        points_by_route_key.setdefault(route_key, []).append(
            RouteTravelTimePoint(
                route_key=route_key,
                route_link_ids=route_link_ids_by_key[route_key],
                packet_id=packet.packet_id,
                departure_tick=departure_tick,
                completion_tick=completion.physical_tick,
                travel_time_ticks=completion.physical_tick - departure_tick,
                completion_sequence_number=completion.sequence_number,
                final_link_id=final_link_id,
                final_link_exit_route_ordinal=final_exit_ordinal,
            )
        )

    return tuple(
        RouteTravelTimeCurve(
            route_key=route_key,
            route_link_ids=route_link_ids_by_key[route_key],
            points=tuple(points_by_route_key.get(route_key, ())),
        )
        for route_key in sorted(route_link_ids_by_key)
    )


def cumulative_count_projection(
    events: Iterable[Event],
    *,
    link_ids: Iterable[str],
    packets: Mapping[str, Packet] | None = None,
    max_tick: int | None = None,
    prefix_event_count: int | None = None,
) -> CumulativeCountProjection:
    """Build a complete read-only count and ordinal projection from events."""

    event_tuple = _event_prefix(events, prefix_event_count)
    link_id_tuple = tuple(link_ids)
    projection_max_tick = _projection_max_tick(event_tuple, max_tick)
    aggregate = _aggregate_cumulative_count_grid(
        event_tuple,
        link_ids=link_id_tuple,
        max_tick=projection_max_tick,
    )
    ordinals = packet_boundary_ordinals(
        event_tuple,
        packets=packets,
        link_ids=link_id_tuple,
        max_tick=projection_max_tick,
    )
    route_counts_supported = packets is not None
    route_support_reason = (
        "packet_route_intent"
        if route_counts_supported
        else "packet_route_intent_unavailable"
    )
    route_counts: tuple[RouteCumulativeBoundaryCounts, ...] = ()
    travel_time_curves: tuple[RouteTravelTimeCurve, ...] = ()
    if packets is not None:
        route_counts = _route_cumulative_count_grid(
            event_tuple,
            packets,
            link_ids=link_id_tuple,
            max_tick=projection_max_tick,
        )
        travel_time_curves = route_travel_time_curves(
            event_tuple,
            packets,
            max_tick=projection_max_tick,
        )
    return CumulativeCountProjection(
        link_ids=link_id_tuple,
        max_tick=projection_max_tick,
        checked_event_count=len(event_tuple),
        tick_convention=COUNT_TICK_CONVENTION,
        ordering_convention=COUNT_ORDERING_CONVENTION,
        aggregate_counts=aggregate,
        packet_ordinals=ordinals,
        route_counts=route_counts,
        route_travel_time_curves=travel_time_curves,
        route_counts_supported=route_counts_supported,
        route_count_support_reason=route_support_reason,
    )


def count_consistency_report(
    events: Iterable[Event],
    *,
    link_ids: Iterable[str],
    packets: Mapping[str, Packet] | None = None,
    max_tick: int | None = None,
    prefix_event_count: int | None = None,
) -> CountConsistencyReport:
    """Check M2 count projection invariants without mutating loading state."""

    event_source_tuple = tuple(events)
    link_id_tuple = tuple(link_ids)
    if prefix_event_count is not None and prefix_event_count < 0:
        return CountConsistencyReport(
            link_ids=link_id_tuple,
            max_tick=_projection_max_tick(event_source_tuple, max_tick),
            checked_event_count=0,
            tick_convention=COUNT_TICK_CONVENTION,
            ordering_convention=COUNT_ORDERING_CONVENTION,
            is_consistent=False,
            ineligibility_reasons=("prefix_event_count cannot be negative",),
            route_counts_supported=packets is not None,
            route_count_support_reason=(
                "packet_route_intent"
                if packets is not None
                else "packet_route_intent_unavailable"
            ),
        )

    reasons: list[str] = []
    try:
        projection = cumulative_count_projection(
            event_source_tuple,
            link_ids=link_id_tuple,
            packets=packets,
            max_tick=max_tick,
            prefix_event_count=prefix_event_count,
        )
        return count_consistency_report_from_projection(
            projection,
            events=_event_prefix(event_source_tuple, prefix_event_count),
        )
    except (KeyError, TypeError, ValueError) as exc:
        event_tuple = _event_prefix(event_source_tuple, prefix_event_count)
        return CountConsistencyReport(
            link_ids=link_id_tuple,
            max_tick=_projection_max_tick(event_tuple, max_tick),
            checked_event_count=len(event_tuple),
            tick_convention=COUNT_TICK_CONVENTION,
            ordering_convention=COUNT_ORDERING_CONVENTION,
            is_consistent=False,
            ineligibility_reasons=(str(exc),),
            route_counts_supported=packets is not None,
            route_count_support_reason=(
                "packet_route_intent"
                if packets is not None
                else "packet_route_intent_unavailable"
            ),
        )


def count_consistency_report_from_projection(
    projection: CumulativeCountProjection,
    *,
    events: Iterable[Event],
) -> CountConsistencyReport:
    """Check count projection invariants without rebuilding the projection."""

    reasons: list[str] = []
    try:
        _check_event_order(tuple(events), reasons)
        _check_aggregate_counts(projection.aggregate_counts, reasons)
        _check_packet_ordinals(projection.packet_ordinals, reasons)
        if projection.route_counts_supported:
            _check_route_counts_sum_to_aggregate(projection, reasons)
            _check_route_travel_time_curves(projection, reasons)
    except (KeyError, TypeError, ValueError) as exc:
        reasons.append(str(exc))
    return CountConsistencyReport(
        link_ids=projection.link_ids,
        max_tick=projection.max_tick,
        checked_event_count=projection.checked_event_count,
        tick_convention=projection.tick_convention,
        ordering_convention=projection.ordering_convention,
        is_consistent=not reasons,
        ineligibility_reasons=tuple(reasons),
        route_counts_supported=projection.route_counts_supported,
        route_count_support_reason=projection.route_count_support_reason,
    )


def _event_prefix(
    events: Iterable[Event],
    prefix_event_count: int | None,
) -> tuple[Event, ...]:
    event_tuple = tuple(events)
    if prefix_event_count is None:
        return event_tuple
    if prefix_event_count < 0:
        raise ValueError("prefix_event_count cannot be negative")
    return event_tuple[:prefix_event_count]


def _ordered_events(events: Iterable[Event]) -> tuple[Event, ...]:
    return tuple(
        sorted(events, key=lambda event: (event.physical_tick, event.sequence_number))
    )


def _projection_max_tick(events: tuple[Event, ...], max_tick: int | None) -> int:
    if max_tick is not None:
        return max_tick
    return max((event.physical_tick for event in events), default=0)


def _boundary_type_for_event(event: Event) -> str | None:
    if event.event_type == EventType.LINK_ENTRY:
        return ENTRY_BOUNDARY
    if event.event_type == EventType.LINK_EXIT:
        return EXIT_BOUNDARY
    return None


def _route_link_ids_by_key(packets: Mapping[str, Packet]) -> dict[str, tuple[str, ...]]:
    route_link_ids_by_key: dict[str, tuple[str, ...]] = {}
    for packet in packets.values():
        route_key = route_key_for_packet(packet)
        route_link_ids = route_link_ids_by_key.setdefault(route_key, packet.route_intent)
        if route_link_ids != packet.route_intent:
            raise ValueError(f"route_key collision for {route_key}")
    return route_link_ids_by_key


def _route_cumulative_count_grid(
    events: tuple[Event, ...],
    packets: Mapping[str, Packet],
    *,
    link_ids: tuple[str, ...],
    max_tick: int,
) -> tuple[RouteCumulativeBoundaryCounts, ...]:
    """Return route counts for all requested links/routes without rescanning."""

    if max_tick < 0:
        return ()

    route_link_ids_by_key = _route_link_ids_by_key(packets)
    route_keys = tuple(sorted(route_link_ids_by_key))
    increments_by_tick: dict[tuple[int, str, str], tuple[int, int]] = {}
    for event in events:
        if event.physical_tick > max_tick:
            continue
        boundary_type = _boundary_type_for_event(event)
        if boundary_type is None:
            continue
        packet = packets.get(event.packet_id)
        if packet is None:
            continue
        route_key = route_key_for_packet(packet)
        key = (event.physical_tick, event.entity_id, route_key)
        entries, exits = increments_by_tick.get(key, (0, 0))
        if boundary_type == ENTRY_BOUNDARY:
            entries += 1
        else:
            exits += 1
        increments_by_tick[key] = (entries, exits)

    route_counts: list[RouteCumulativeBoundaryCounts] = []
    for link_id in link_ids:
        for route_key in route_keys:
            entries = 0
            exits = 0
            route_link_ids = route_link_ids_by_key[route_key]
            for tick in range(max_tick + 1):
                entry_increment, exit_increment = increments_by_tick.get(
                    (tick, link_id, route_key),
                    (0, 0),
                )
                entries += entry_increment
                exits += exit_increment
                route_counts.append(
                    RouteCumulativeBoundaryCounts(
                        link_id=link_id,
                        route_key=route_key,
                        route_link_ids=route_link_ids,
                        tick=tick,
                        entries=entries,
                        exits=exits,
                    )
                )
    return tuple(route_counts)


def _aggregate_cumulative_count_grid(
    events: tuple[Event, ...],
    *,
    link_ids: tuple[str, ...],
    max_tick: int,
) -> tuple[CumulativeBoundaryCounts, ...]:
    """Return aggregate counts for all requested links without rescanning events."""

    if max_tick < 0:
        return ()

    link_id_set = set(link_ids)
    increments_by_tick: dict[tuple[int, str], tuple[int, int]] = {}
    for event in events:
        if event.physical_tick > max_tick or event.entity_id not in link_id_set:
            continue
        boundary_type = _boundary_type_for_event(event)
        if boundary_type is None:
            continue
        key = (event.physical_tick, event.entity_id)
        entries, exits = increments_by_tick.get(key, (0, 0))
        if boundary_type == ENTRY_BOUNDARY:
            entries += 1
        else:
            exits += 1
        increments_by_tick[key] = (entries, exits)

    aggregate_counts: list[CumulativeBoundaryCounts] = []
    for link_id in link_ids:
        entries = 0
        exits = 0
        for tick in range(max_tick + 1):
            entry_increment, exit_increment = increments_by_tick.get(
                (tick, link_id),
                (0, 0),
            )
            entries += entry_increment
            exits += exit_increment
            aggregate_counts.append(
                CumulativeBoundaryCounts(
                    link_id=link_id,
                    tick=tick,
                    entries=entries,
                    exits=exits,
                )
            )
    return tuple(aggregate_counts)


def _final_link_exit_route_ordinals(
    events: tuple[Event, ...],
    packets: Mapping[str, Packet],
    *,
    max_tick: int | None,
) -> dict[str, int]:
    final_exit_ordinal_by_packet_id: dict[str, int] = {}
    for ordinal in packet_boundary_ordinals(
        events,
        packets=packets,
        max_tick=max_tick,
    ):
        packet = packets[ordinal.packet_id]
        if (
            ordinal.boundary_type == EXIT_BOUNDARY
            and packet.route_intent
            and ordinal.link_id == packet.route_intent[-1]
        ):
            if ordinal.route_ordinal is None:
                raise ValueError(
                    f"packet_id {packet.packet_id} final exit has no route ordinal"
                )
            final_exit_ordinal_by_packet_id[packet.packet_id] = ordinal.route_ordinal
    return final_exit_ordinal_by_packet_id


def _check_event_order(events: tuple[Event, ...], reasons: list[str]) -> None:
    for expected_sequence_number, event in enumerate(events):
        if event.sequence_number != expected_sequence_number:
            reasons.append(
                "event_sequence_not_prefix_contiguous:"
                f"expected_{expected_sequence_number}:actual_{event.sequence_number}"
            )
    ordered = _ordered_events(events)
    if events != ordered:
        reasons.append("events_not_ordered_by_tick_then_sequence")


def _check_aggregate_counts(
    aggregate_counts: tuple[CumulativeBoundaryCounts, ...],
    reasons: list[str],
) -> None:
    previous_by_link: dict[str, CumulativeBoundaryCounts] = {}
    for counts in aggregate_counts:
        previous = previous_by_link.get(counts.link_id)
        if previous is not None:
            if counts.entries < previous.entries:
                reasons.append(
                    f"{counts.link_id}:entries_not_monotone_at_tick_{counts.tick}"
                )
            if counts.exits < previous.exits:
                reasons.append(
                    f"{counts.link_id}:exits_not_monotone_at_tick_{counts.tick}"
                )
        if counts.exits > counts.entries:
            reasons.append(f"{counts.link_id}:exits_exceed_entries_at_tick_{counts.tick}")
        previous_by_link[counts.link_id] = counts


def _check_packet_ordinals(
    ordinals: tuple[PacketBoundaryOrdinal, ...],
    reasons: list[str],
) -> None:
    expected_by_boundary: dict[tuple[str, str], int] = {}
    expected_by_route_boundary: dict[tuple[str, str, str], int] = {}
    for ordinal in ordinals:
        boundary_key = (ordinal.link_id, ordinal.boundary_type)
        expected_aggregate = expected_by_boundary.get(boundary_key, 0) + 1
        if ordinal.aggregate_ordinal != expected_aggregate:
            reasons.append(
                f"{ordinal.link_id}:{ordinal.boundary_type}:aggregate_ordinal_gap"
            )
        expected_by_boundary[boundary_key] = expected_aggregate

        if ordinal.route_key is not None:
            if ordinal.route_ordinal is None:
                reasons.append(
                    f"{ordinal.link_id}:{ordinal.boundary_type}:missing_route_ordinal"
                )
                continue
            route_boundary_key = (
                ordinal.link_id,
                ordinal.boundary_type,
                ordinal.route_key,
            )
            expected_route = expected_by_route_boundary.get(route_boundary_key, 0) + 1
            if ordinal.route_ordinal != expected_route:
                reasons.append(
                    f"{ordinal.link_id}:{ordinal.boundary_type}:route_ordinal_gap"
                )
            expected_by_route_boundary[route_boundary_key] = expected_route


def _check_route_counts_sum_to_aggregate(
    projection: CumulativeCountProjection,
    reasons: list[str],
) -> None:
    aggregate_by_link_tick = {
        (counts.link_id, counts.tick): counts
        for counts in projection.aggregate_counts
    }
    route_sum_by_link_tick: dict[tuple[str, int], tuple[int, int]] = {}
    for counts in projection.route_counts:
        key = (counts.link_id, counts.tick)
        entries, exits = route_sum_by_link_tick.get(key, (0, 0))
        route_sum_by_link_tick[key] = (
            entries + counts.entries,
            exits + counts.exits,
        )

    for key, aggregate_counts in aggregate_by_link_tick.items():
        route_entries, route_exits = route_sum_by_link_tick.get(key, (0, 0))
        if route_entries != aggregate_counts.entries:
            reasons.append(f"{key[0]}:route_entries_do_not_sum_at_tick_{key[1]}")
        if route_exits != aggregate_counts.exits:
            reasons.append(f"{key[0]}:route_exits_do_not_sum_at_tick_{key[1]}")


def _check_route_travel_time_curves(
    projection: CumulativeCountProjection,
    reasons: list[str],
) -> None:
    completion_keys: set[tuple[str, int]] = set()
    for curve in projection.route_travel_time_curves:
        previous_completion: tuple[int, int] | None = None
        for point in curve.points:
            if point.route_key != curve.route_key:
                reasons.append(f"{curve.route_key}:travel_time_point_route_key_mismatch")
            if point.route_link_ids != curve.route_link_ids:
                reasons.append(f"{curve.route_key}:travel_time_point_route_links_mismatch")
            completion_key = (point.packet_id, point.completion_sequence_number)
            if completion_key in completion_keys:
                reasons.append(f"{curve.route_key}:duplicate_travel_time_packet")
            completion_keys.add(completion_key)
            current_completion = (
                point.completion_tick,
                point.completion_sequence_number,
            )
            if previous_completion is not None and current_completion < previous_completion:
                reasons.append(f"{curve.route_key}:travel_time_curve_not_ordered")
            previous_completion = current_completion
