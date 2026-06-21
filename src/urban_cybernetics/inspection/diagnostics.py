"""Run bottleneck diagnostics derived from canonical loading history."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import floor
from typing import Any

from urban_cybernetics.core import Event, EventType, Link, Packet
from urban_cybernetics.loading import LoadingEngine


@dataclass(frozen=True, slots=True)
class PacketDiagnosticMetadata:
    """Optional run-artifact metadata for enriching packet diagnostics."""

    demand_id: str | None = None
    route_id: str | None = None
    origin_node_id: str | None = None
    destination_node_id: str | None = None
    route_link_sequence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "route_link_sequence",
            _normalise_string_tuple(
                self.route_link_sequence,
                "route_link_sequence",
                allow_empty=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class CompletedPacketDiagnostics:
    """Diagnostics for one completed packet/trip."""

    packet_id: str
    loading_demand_id: str
    demand_id: str
    route_id: str | None
    origin_node_id: str | None
    destination_node_id: str | None
    route_link_sequence: tuple[str, ...]
    entry_tick: int
    completion_tick: int
    travel_time_ticks: int
    free_flow_time_ticks: int | None
    delay_over_free_flow_ticks: int | None
    free_flow_ratio: float | None

    def __post_init__(self) -> None:
        _require_non_empty(self.packet_id, "packet_id")
        _require_non_empty(self.loading_demand_id, "loading_demand_id")
        _require_non_empty(self.demand_id, "demand_id")
        object.__setattr__(
            self,
            "route_link_sequence",
            _normalise_string_tuple(
                self.route_link_sequence,
                "route_link_sequence",
                allow_empty=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class ODBottleneckDiagnostics:
    """Aggregate diagnostics for an OD or demand group."""

    group_id: str
    demand_ids: tuple[str, ...]
    route_ids: tuple[str, ...]
    origin_node_id: str | None
    destination_node_id: str | None
    completed_count: int
    average_travel_time_ticks: float
    p95_travel_time_ticks: float
    max_travel_time_ticks: int
    average_delay_over_free_flow_ticks: float | None
    average_free_flow_ratio: float | None

    def __post_init__(self) -> None:
        _require_non_empty(self.group_id, "group_id")
        object.__setattr__(
            self,
            "demand_ids",
            _normalise_string_tuple(self.demand_ids, "demand_ids"),
        )
        object.__setattr__(
            self,
            "route_ids",
            _normalise_string_tuple(self.route_ids, "route_ids", allow_empty=True),
        )


@dataclass(frozen=True, slots=True)
class RouteBottleneckDiagnostics:
    """Aggregate diagnostics for a realised route group."""

    route_id: str
    route_link_sequence: tuple[str, ...]
    completed_count: int
    average_travel_time_ticks: float
    p95_travel_time_ticks: float
    max_travel_time_ticks: int
    average_delay_over_free_flow_ticks: float | None
    average_free_flow_ratio: float | None

    def __post_init__(self) -> None:
        _require_non_empty(self.route_id, "route_id")
        object.__setattr__(
            self,
            "route_link_sequence",
            _normalise_string_tuple(
                self.route_link_sequence,
                "route_link_sequence",
                allow_empty=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class LinkBottleneckDiagnostics:
    """Canonical link entry/exit counts and net occupancy contribution."""

    link_id: str
    link_entry_count: int
    link_exit_count: int
    net_occupancy_contribution: int

    def __post_init__(self) -> None:
        _require_non_empty(self.link_id, "link_id")


@dataclass(frozen=True, slots=True)
class QueueLocationDiagnostics:
    """Queue persistence diagnostics for one upstream/downstream boundary."""

    boundary_id: str
    upstream_link_id: str
    downstream_link_id: str
    queue_entry_count: int
    queue_exit_count: int
    max_observed_queue_length: int
    total_queued_packet_ticks: int
    longest_individual_queue_wait_ticks: int | None
    active_queued_packets: int

    def __post_init__(self) -> None:
        _require_non_empty(self.boundary_id, "boundary_id")
        _require_non_empty(self.upstream_link_id, "upstream_link_id")
        _require_non_empty(self.downstream_link_id, "downstream_link_id")


@dataclass(frozen=True, slots=True)
class LinkDelayContributionDiagnostics:
    """Approximate link delay contribution from realised link entry/exit events."""

    link_id: str
    completed_traversal_count: int
    total_traversal_time_ticks: int
    total_free_flow_time_ticks: int | None
    total_delay_over_free_flow_ticks: int | None
    average_delay_over_free_flow_ticks: float | None

    def __post_init__(self) -> None:
        _require_non_empty(self.link_id, "link_id")


@dataclass(frozen=True, slots=True)
class RunBottleneckDiagnostics:
    """Immutable I2 artifact describing where delay and queues came from."""

    diagnostics_id: str
    run_id: str
    worst_packets_by_travel_time: tuple[CompletedPacketDiagnostics, ...]
    worst_packets_by_delay: tuple[CompletedPacketDiagnostics, ...]
    worst_packets_by_free_flow_ratio: tuple[CompletedPacketDiagnostics, ...]
    worst_od_groups: tuple[ODBottleneckDiagnostics, ...]
    worst_routes: tuple[RouteBottleneckDiagnostics, ...]
    busiest_links: tuple[LinkBottleneckDiagnostics, ...]
    most_delayed_links: tuple[LinkDelayContributionDiagnostics, ...]
    persistent_queues: tuple[QueueLocationDiagnostics, ...]
    input_artifact_ids: tuple[str, ...] = ()
    event_count: int = 0
    derivation_basis: tuple[str, ...] = (
        "packet lifecycle event log",
        "queue lifecycle event log",
        "packet history",
        "optional demand and route artifact metadata",
    )
    delay_attribution_note: str = (
        "Link delay is estimated from realised link entry/exit duration minus "
        "static free-flow ticks where link metadata exists. Queue waiting is "
        "reported separately from queue events; no map, speed, or assignment "
        "model is inferred."
    )
    schema_version: str = "i2.run_bottleneck_diagnostics.v1"

    def __post_init__(self) -> None:
        _require_non_empty(self.diagnostics_id, "diagnostics_id")
        _require_non_empty(self.run_id, "run_id")
        for field_name in (
            "worst_packets_by_travel_time",
            "worst_packets_by_delay",
            "worst_packets_by_free_flow_ratio",
            "worst_od_groups",
            "worst_routes",
            "busiest_links",
            "most_delayed_links",
            "persistent_queues",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        object.__setattr__(
            self,
            "input_artifact_ids",
            _normalise_string_tuple(
                self.input_artifact_ids,
                "input_artifact_ids",
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "derivation_basis",
            _normalise_string_tuple(self.derivation_basis, "derivation_basis"),
        )
        if self.event_count < 0:
            raise ValueError("event_count must be non-negative")


def inspect_loading_engine_bottlenecks(
    *,
    run_id: str,
    engine: LoadingEngine,
    packet_metadata_by_loading_demand_id: Mapping[str, PacketDiagnosticMetadata] | None = None,
    input_artifact_ids: Iterable[str] = (),
    diagnostics_id: str | None = None,
    top_n: int = 10,
) -> RunBottleneckDiagnostics:
    """Build bottleneck diagnostics from read-only loading-engine surfaces."""

    return build_run_bottleneck_diagnostics(
        run_id=run_id,
        events=engine.event_log,
        packets=engine.packets,
        links=engine.links,
        current_tick=engine.current_tick,
        packet_metadata_by_loading_demand_id=packet_metadata_by_loading_demand_id,
        input_artifact_ids=input_artifact_ids,
        diagnostics_id=diagnostics_id,
        top_n=top_n,
    )


def build_run_bottleneck_diagnostics(
    *,
    run_id: str,
    events: Iterable[Event],
    packets: Mapping[str, Packet],
    links: Mapping[str, Link] | None = None,
    current_tick: int | None = None,
    packet_metadata_by_loading_demand_id: Mapping[str, PacketDiagnosticMetadata] | None = None,
    input_artifact_ids: Iterable[str] = (),
    diagnostics_id: str | None = None,
    top_n: int = 10,
) -> RunBottleneckDiagnostics:
    """Derive bottleneck diagnostics from canonical history and packet state."""

    _require_non_empty(run_id, "run_id")
    if top_n < 1:
        raise ValueError("top_n must be positive")
    event_history = tuple(events)
    run_end_tick = (
        current_tick
        if current_tick is not None
        else max((event.physical_tick for event in event_history), default=0)
    )
    if run_end_tick < 0:
        raise ValueError("current_tick cannot be negative")

    completed_packets = _completed_packet_diagnostics(
        event_history,
        packets,
        links or {},
        packet_metadata_by_loading_demand_id or {},
    )
    link_bottlenecks = _link_bottlenecks(event_history, links or {})
    link_delays = _link_delay_contributions(event_history, links or {})

    return RunBottleneckDiagnostics(
        diagnostics_id=diagnostics_id or f"inspection:{run_id}:bottleneck-diagnostics",
        run_id=run_id,
        worst_packets_by_travel_time=tuple(
            _top_by_optional_metric(
                completed_packets,
                lambda item: item.travel_time_ticks,
                top_n,
            )
        ),
        worst_packets_by_delay=tuple(
            _top_by_optional_metric(
                completed_packets,
                lambda item: item.delay_over_free_flow_ticks,
                top_n,
            )
        ),
        worst_packets_by_free_flow_ratio=tuple(
            _top_by_optional_metric(
                completed_packets,
                lambda item: item.free_flow_ratio,
                top_n,
            )
        ),
        worst_od_groups=tuple(_worst_od_groups(completed_packets, top_n)),
        worst_routes=tuple(_worst_routes(completed_packets, top_n)),
        busiest_links=tuple(link_bottlenecks[:top_n]),
        most_delayed_links=tuple(link_delays[:top_n]),
        persistent_queues=tuple(
            _queue_location_diagnostics(event_history, run_end_tick)[:top_n]
        ),
        input_artifact_ids=tuple(input_artifact_ids),
        event_count=len(event_history),
    )


def packet_metadata_from_scheduled_requests(
    scheduled_requests: Iterable[object],
    *,
    demand_manifest: object | None = None,
) -> dict[str, PacketDiagnosticMetadata]:
    """Build packet diagnostic metadata from D1/D2 scheduled request artifacts."""

    declarations_by_demand_id: dict[str, object] = {}
    if demand_manifest is not None:
        declarations_by_demand_id = {
            getattr(declaration, "demand_id"): declaration
            for declaration in getattr(demand_manifest, "declarations", ())
        }

    metadata: dict[str, PacketDiagnosticMetadata] = {}
    for request in scheduled_requests:
        loading_demand_id = getattr(request, "loading_demand_id")
        od_demand_id = getattr(request, "od_demand_id", None)
        declaration = declarations_by_demand_id.get(od_demand_id)
        metadata[loading_demand_id] = PacketDiagnosticMetadata(
            demand_id=od_demand_id,
            route_id=getattr(request, "route_id", None),
            origin_node_id=(
                getattr(declaration, "origin_node_id", None)
                if declaration is not None
                else None
            ),
            destination_node_id=(
                getattr(declaration, "destination_node_id", None)
                if declaration is not None
                else None
            ),
            route_link_sequence=tuple(getattr(request, "route_intent", ())),
        )
    return metadata


def _completed_packet_diagnostics(
    events: tuple[Event, ...],
    packets: Mapping[str, Packet],
    links: Mapping[str, Link],
    metadata_by_loading_demand_id: Mapping[str, PacketDiagnosticMetadata],
) -> tuple[CompletedPacketDiagnostics, ...]:
    instantiation_ticks: dict[str, int] = {}
    first_link_entry_ticks: dict[str, int] = {}
    completion_ticks: dict[str, int] = {}
    for event in events:
        if event.event_type == EventType.INSTANTIATED:
            instantiation_ticks.setdefault(event.packet_id, event.physical_tick)
        elif event.event_type == EventType.LINK_ENTRY:
            first_link_entry_ticks.setdefault(event.packet_id, event.physical_tick)
        elif event.event_type == EventType.COMPLETED:
            completion_ticks[event.packet_id] = event.physical_tick

    diagnostics: list[CompletedPacketDiagnostics] = []
    for packet_id, completion_tick in completion_ticks.items():
        packet = packets.get(packet_id)
        if packet is None:
            continue
        start_tick = instantiation_ticks.get(packet_id)
        if start_tick is None:
            raise ValueError(f"completed packet {packet_id} has no instantiation event")
        travel_time = completion_tick - start_tick
        if travel_time < 0:
            raise ValueError(f"completed packet {packet_id} has negative travel time")

        metadata = metadata_by_loading_demand_id.get(packet.demand_id)
        route_link_sequence = (
            metadata.route_link_sequence
            if metadata is not None and metadata.route_link_sequence
            else packet.route_intent
        )
        free_flow_time = _free_flow_ticks(route_link_sequence, links)
        delay = (
            travel_time - free_flow_time
            if free_flow_time is not None
            else None
        )
        ratio = (
            travel_time / free_flow_time
            if free_flow_time is not None and free_flow_time > 0
            else None
        )
        demand_id = (
            metadata.demand_id
            if metadata is not None and metadata.demand_id is not None
            else packet.demand_id
        )
        diagnostics.append(
            CompletedPacketDiagnostics(
                packet_id=packet_id,
                loading_demand_id=packet.demand_id,
                demand_id=demand_id,
                route_id=metadata.route_id if metadata is not None else None,
                origin_node_id=(
                    metadata.origin_node_id if metadata is not None else None
                ),
                destination_node_id=(
                    metadata.destination_node_id if metadata is not None else None
                ),
                route_link_sequence=route_link_sequence,
                entry_tick=first_link_entry_ticks.get(packet_id, start_tick),
                completion_tick=completion_tick,
                travel_time_ticks=travel_time,
                free_flow_time_ticks=free_flow_time,
                delay_over_free_flow_ticks=delay,
                free_flow_ratio=ratio,
            )
        )
    return tuple(diagnostics)


def _worst_od_groups(
    completed_packets: tuple[CompletedPacketDiagnostics, ...],
    top_n: int,
) -> list[ODBottleneckDiagnostics]:
    groups: dict[str, list[CompletedPacketDiagnostics]] = {}
    for packet in completed_packets:
        if packet.origin_node_id is not None and packet.destination_node_id is not None:
            group_id = f"OD:{packet.origin_node_id}->{packet.destination_node_id}"
        else:
            group_id = f"demand:{packet.demand_id}"
        groups.setdefault(group_id, []).append(packet)

    diagnostics = [
        _od_group_diagnostics(group_id, packets)
        for group_id, packets in groups.items()
    ]
    return sorted(
        diagnostics,
        key=lambda item: (
            -_optional_sort_value(item.average_delay_over_free_flow_ticks),
            -item.average_travel_time_ticks,
            item.group_id,
        ),
    )[:top_n]


def _od_group_diagnostics(
    group_id: str,
    packets: list[CompletedPacketDiagnostics],
) -> ODBottleneckDiagnostics:
    travel_times = tuple(sorted(packet.travel_time_ticks for packet in packets))
    delays = tuple(
        packet.delay_over_free_flow_ticks
        for packet in packets
        if packet.delay_over_free_flow_ticks is not None
    )
    ratios = tuple(
        packet.free_flow_ratio
        for packet in packets
        if packet.free_flow_ratio is not None
    )
    return ODBottleneckDiagnostics(
        group_id=group_id,
        demand_ids=tuple(sorted({packet.demand_id for packet in packets})),
        route_ids=tuple(
            sorted({packet.route_id for packet in packets if packet.route_id})
        ),
        origin_node_id=packets[0].origin_node_id,
        destination_node_id=packets[0].destination_node_id,
        completed_count=len(packets),
        average_travel_time_ticks=sum(travel_times) / len(travel_times),
        p95_travel_time_ticks=_percentile(travel_times, 0.95) or 0.0,
        max_travel_time_ticks=max(travel_times),
        average_delay_over_free_flow_ticks=(
            sum(delays) / len(delays) if delays else None
        ),
        average_free_flow_ratio=sum(ratios) / len(ratios) if ratios else None,
    )


def _worst_routes(
    completed_packets: tuple[CompletedPacketDiagnostics, ...],
    top_n: int,
) -> list[RouteBottleneckDiagnostics]:
    groups: dict[str, list[CompletedPacketDiagnostics]] = {}
    for packet in completed_packets:
        route_id = packet.route_id or "route:" + ">".join(packet.route_link_sequence)
        groups.setdefault(route_id, []).append(packet)

    diagnostics = [
        _route_group_diagnostics(route_id, packets)
        for route_id, packets in groups.items()
    ]
    return sorted(
        diagnostics,
        key=lambda item: (
            -_optional_sort_value(item.average_delay_over_free_flow_ticks),
            -item.average_travel_time_ticks,
            item.route_id,
        ),
    )[:top_n]


def _route_group_diagnostics(
    route_id: str,
    packets: list[CompletedPacketDiagnostics],
) -> RouteBottleneckDiagnostics:
    travel_times = tuple(sorted(packet.travel_time_ticks for packet in packets))
    delays = tuple(
        packet.delay_over_free_flow_ticks
        for packet in packets
        if packet.delay_over_free_flow_ticks is not None
    )
    ratios = tuple(
        packet.free_flow_ratio
        for packet in packets
        if packet.free_flow_ratio is not None
    )
    return RouteBottleneckDiagnostics(
        route_id=route_id,
        route_link_sequence=packets[0].route_link_sequence,
        completed_count=len(packets),
        average_travel_time_ticks=sum(travel_times) / len(travel_times),
        p95_travel_time_ticks=_percentile(travel_times, 0.95) or 0.0,
        max_travel_time_ticks=max(travel_times),
        average_delay_over_free_flow_ticks=(
            sum(delays) / len(delays) if delays else None
        ),
        average_free_flow_ratio=sum(ratios) / len(ratios) if ratios else None,
    )


def _link_bottlenecks(
    events: tuple[Event, ...],
    links: Mapping[str, Link],
) -> list[LinkBottleneckDiagnostics]:
    link_ids = set(links)
    entry_counts: dict[str, int] = {}
    exit_counts: dict[str, int] = {}
    for event in events:
        if event.event_type == EventType.LINK_ENTRY:
            link_ids.add(event.entity_id)
            entry_counts[event.entity_id] = entry_counts.get(event.entity_id, 0) + 1
        elif event.event_type == EventType.LINK_EXIT:
            link_ids.add(event.entity_id)
            exit_counts[event.entity_id] = exit_counts.get(event.entity_id, 0) + 1

    diagnostics = [
        LinkBottleneckDiagnostics(
            link_id=link_id,
            link_entry_count=entry_counts.get(link_id, 0),
            link_exit_count=exit_counts.get(link_id, 0),
            net_occupancy_contribution=(
                entry_counts.get(link_id, 0) - exit_counts.get(link_id, 0)
            ),
        )
        for link_id in link_ids
    ]
    return sorted(
        diagnostics,
        key=lambda item: (
            -item.link_entry_count,
            -item.link_exit_count,
            -abs(item.net_occupancy_contribution),
            item.link_id,
        ),
    )


def _link_delay_contributions(
    events: tuple[Event, ...],
    links: Mapping[str, Link],
) -> list[LinkDelayContributionDiagnostics]:
    open_entries: dict[str, tuple[str, int]] = {}
    traversal_count: dict[str, int] = {}
    traversal_ticks: dict[str, int] = {}
    free_flow_ticks: dict[str, int] = {}
    delay_ticks: dict[str, int] = {}

    for event in events:
        if event.event_type == EventType.LINK_ENTRY:
            open_entries[event.packet_id] = (event.entity_id, event.physical_tick)
        elif event.event_type == EventType.LINK_EXIT:
            entry = open_entries.pop(event.packet_id, None)
            if entry is None:
                continue
            link_id, entry_tick = entry
            if link_id != event.entity_id:
                raise ValueError(
                    f"packet {event.packet_id} exits {event.entity_id} after "
                    f"entering {link_id}"
                )
            duration = event.physical_tick - entry_tick
            if duration < 0:
                raise ValueError(
                    f"packet {event.packet_id} has negative traversal time"
                )
            traversal_count[link_id] = traversal_count.get(link_id, 0) + 1
            traversal_ticks[link_id] = traversal_ticks.get(link_id, 0) + duration
            link = links.get(link_id)
            if link is not None and link.free_flow_ticks is not None:
                free_flow_ticks[link_id] = (
                    free_flow_ticks.get(link_id, 0) + link.free_flow_ticks
                )
                delay_ticks[link_id] = (
                    delay_ticks.get(link_id, 0)
                    + max(duration - link.free_flow_ticks, 0)
                )

    diagnostics = [
        LinkDelayContributionDiagnostics(
            link_id=link_id,
            completed_traversal_count=traversal_count[link_id],
            total_traversal_time_ticks=traversal_ticks[link_id],
            total_free_flow_time_ticks=free_flow_ticks.get(link_id),
            total_delay_over_free_flow_ticks=delay_ticks.get(link_id),
            average_delay_over_free_flow_ticks=(
                delay_ticks[link_id] / traversal_count[link_id]
                if link_id in delay_ticks
                else None
            ),
        )
        for link_id in traversal_count
    ]
    return sorted(
        diagnostics,
        key=lambda item: (
            -_optional_sort_value(item.total_delay_over_free_flow_ticks),
            -item.total_traversal_time_ticks,
            item.link_id,
        ),
    )


@dataclass(slots=True)
class _MutableQueueStats:
    boundary_id: str
    upstream_link_id: str
    downstream_link_id: str
    entries: int = 0
    exits: int = 0
    max_length: int = 0
    total_packet_ticks: int = 0
    longest_wait: int | None = None
    last_tick: int | None = None


def _queue_location_diagnostics(
    events: tuple[Event, ...],
    run_end_tick: int,
) -> list[QueueLocationDiagnostics]:
    queues: dict[str, deque[tuple[str, int]]] = {}
    stats: dict[str, _MutableQueueStats] = {}

    for event in events:
        if event.event_type not in {EventType.QUEUE_ENTRY, EventType.QUEUE_EXIT}:
            continue
        boundary_id = event.entity_id
        upstream_link_id, downstream_link_id = _parse_boundary_id(boundary_id)
        queue = queues.setdefault(boundary_id, deque())
        boundary_stats = stats.setdefault(
            boundary_id,
            _MutableQueueStats(
                boundary_id=boundary_id,
                upstream_link_id=upstream_link_id,
                downstream_link_id=downstream_link_id,
                last_tick=event.physical_tick,
            ),
        )
        _advance_queue_area(boundary_stats, len(queue), event.physical_tick)

        if event.event_type == EventType.QUEUE_ENTRY:
            queue.append((event.packet_id, event.physical_tick))
            boundary_stats.entries += 1
            boundary_stats.max_length = max(boundary_stats.max_length, len(queue))
        elif event.event_type == EventType.QUEUE_EXIT:
            if not queue or queue[0][0] != event.packet_id:
                raise ValueError(
                    f"packet {event.packet_id} exits queue {boundary_id} "
                    "out of FIFO order or without queue entry"
                )
            _, entry_tick = queue.popleft()
            wait = event.physical_tick - entry_tick
            if wait < 0:
                raise ValueError(f"packet {event.packet_id} has negative queue wait")
            boundary_stats.exits += 1
            boundary_stats.longest_wait = max(
                boundary_stats.longest_wait or 0,
                wait,
            )

    for boundary_id, queue in queues.items():
        boundary_stats = stats[boundary_id]
        _advance_queue_area(boundary_stats, len(queue), run_end_tick)
        for _, entry_tick in queue:
            wait_so_far = run_end_tick - entry_tick
            if wait_so_far < 0:
                raise ValueError(f"active queue wait is negative for {boundary_id}")
            boundary_stats.longest_wait = max(
                boundary_stats.longest_wait or 0,
                wait_so_far,
            )

    diagnostics = [
        QueueLocationDiagnostics(
            boundary_id=boundary_id,
            upstream_link_id=boundary_stats.upstream_link_id,
            downstream_link_id=boundary_stats.downstream_link_id,
            queue_entry_count=boundary_stats.entries,
            queue_exit_count=boundary_stats.exits,
            max_observed_queue_length=boundary_stats.max_length,
            total_queued_packet_ticks=boundary_stats.total_packet_ticks,
            longest_individual_queue_wait_ticks=boundary_stats.longest_wait,
            active_queued_packets=len(queues.get(boundary_id, ())),
        )
        for boundary_id, boundary_stats in stats.items()
    ]
    return sorted(
        diagnostics,
        key=lambda item: (
            -item.total_queued_packet_ticks,
            -_optional_sort_value(item.longest_individual_queue_wait_ticks),
            -item.max_observed_queue_length,
            item.boundary_id,
        ),
    )


def _advance_queue_area(
    stats: _MutableQueueStats,
    queue_length: int,
    tick: int,
) -> None:
    if stats.last_tick is None:
        stats.last_tick = tick
        return
    elapsed = tick - stats.last_tick
    if elapsed < 0:
        raise ValueError(f"queue events for {stats.boundary_id} are out of order")
    stats.total_packet_ticks += queue_length * elapsed
    stats.last_tick = tick


def _parse_boundary_id(boundary_id: str) -> tuple[str, str]:
    boundary = boundary_id.removeprefix("boundary:")
    upstream_link_id, downstream_link_id = boundary.split("->", 1)
    return upstream_link_id, downstream_link_id


def _free_flow_ticks(
    route_link_sequence: tuple[str, ...],
    links: Mapping[str, Link],
) -> int | None:
    if not route_link_sequence:
        return None
    total = 0
    for link_id in route_link_sequence:
        link = links.get(link_id)
        if link is None or link.free_flow_ticks is None:
            return None
        total += link.free_flow_ticks
    return total


def _top_by_optional_metric(
    items: tuple[CompletedPacketDiagnostics, ...],
    metric: Any,
    top_n: int,
) -> list[CompletedPacketDiagnostics]:
    return sorted(
        items,
        key=lambda item: (
            -_optional_sort_value(metric(item)),
            item.packet_id,
        ),
    )[:top_n]


def _optional_sort_value(value: int | float | None) -> float:
    return float(value) if value is not None else float("-inf")


def _percentile(values: tuple[int, ...] | tuple[float, ...], percentile: float) -> float | None:
    if not values:
        return None
    if not 0 <= percentile <= 1:
        raise ValueError("percentile must be between 0 and 1")
    if len(values) == 1:
        return float(values[0])

    index = (len(values) - 1) * percentile
    lower_index = floor(index)
    upper_index = min(lower_index + 1, len(values) - 1)
    fraction = index - lower_index
    return values[lower_index] + (values[upper_index] - values[lower_index]) * fraction


def _normalise_string_tuple(
    value: Iterable[str],
    field_name: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if isinstance(value, str):
        raise TypeError(f"{field_name} must be an iterable of strings, not a string")
    strings = tuple(value)
    if not allow_empty and not strings:
        raise ValueError(f"{field_name} must not be empty")
    for item in strings:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} must contain only strings")
        if not item:
            raise ValueError(f"{field_name} must not contain empty strings")
    return strings


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must be non-empty")
