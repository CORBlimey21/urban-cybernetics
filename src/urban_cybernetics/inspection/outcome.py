"""Run-level outcome summaries derived from canonical loading history."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import floor

from urban_cybernetics.core import Event, EventType, LifecycleState, Link, Packet
from urban_cybernetics.loading import LoadingEngine


@dataclass(frozen=True, slots=True)
class TravelTimeMetrics:
    """Travel-time metrics for packets completed in canonical event history."""

    completed_packet_count: int
    total_system_travel_time_ticks: int
    average_travel_time_ticks: float | None
    median_travel_time_ticks: float | None
    p95_travel_time_ticks: float | None
    max_travel_time_ticks: int | None


@dataclass(frozen=True, slots=True)
class CompletionMetrics:
    """Run completion counts from event and loading-engine packet state."""

    instantiated_packets: int
    completed_packets: int
    completion_percentage: float
    remaining_active_packets: int
    remaining_queued_packets: int
    pending_demand_count: int


@dataclass(frozen=True, slots=True)
class LinkUtilisationMetrics:
    """Canonical link boundary event counts for one link."""

    link_id: str
    link_entry_count: int
    link_exit_count: int

    def __post_init__(self) -> None:
        _require_non_empty(self.link_id, "link_id")
        if self.link_entry_count < 0:
            raise ValueError("link_entry_count must be non-negative")
        if self.link_exit_count < 0:
            raise ValueError("link_exit_count must be non-negative")


@dataclass(frozen=True, slots=True)
class FreeFlowComparisonMetrics:
    """Experienced/free-flow travel-time ratios for completed packets."""

    packet_count_with_free_flow: int
    unavailable_packet_count: int
    unavailable_packet_ids: tuple[str, ...]
    average_ratio: float | None
    median_ratio: float | None
    p95_ratio: float | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unavailable_packet_ids",
            _normalise_string_tuple(
                self.unavailable_packet_ids,
                "unavailable_packet_ids",
            ),
        )


@dataclass(frozen=True, slots=True)
class RunOutcomeSummary:
    """Immutable I1 artifact describing what happened in one run."""

    summary_id: str
    run_id: str
    travel_time: TravelTimeMetrics
    completion: CompletionMetrics
    link_utilisation: tuple[LinkUtilisationMetrics, ...]
    free_flow_comparison: FreeFlowComparisonMetrics
    input_artifact_ids: tuple[str, ...] = ()
    event_count: int = 0
    derivation_basis: tuple[str, ...] = (
        "packet lifecycle event log",
        "packet history",
        "run artifact references",
    )
    schema_version: str = "i1.run_outcome_summary.v1"

    def __post_init__(self) -> None:
        _require_non_empty(self.summary_id, "summary_id")
        _require_non_empty(self.run_id, "run_id")
        object.__setattr__(self, "link_utilisation", tuple(self.link_utilisation))
        object.__setattr__(
            self,
            "input_artifact_ids",
            _normalise_string_tuple(self.input_artifact_ids, "input_artifact_ids"),
        )
        object.__setattr__(
            self,
            "derivation_basis",
            _normalise_string_tuple(self.derivation_basis, "derivation_basis"),
        )
        if self.event_count < 0:
            raise ValueError("event_count must be non-negative")


def inspect_loading_engine_run(
    *,
    run_id: str,
    engine: LoadingEngine,
    input_artifact_ids: Iterable[str] = (),
    summary_id: str | None = None,
) -> RunOutcomeSummary:
    """Build a run outcome summary from read-only loading-engine surfaces."""

    return build_run_outcome_summary(
        run_id=run_id,
        events=engine.event_log,
        packets=engine.packets,
        links=engine.links,
        pending_demand_count=len(engine.pending_demands),
        input_artifact_ids=input_artifact_ids,
        summary_id=summary_id,
    )


def build_run_outcome_summary(
    *,
    run_id: str,
    events: Iterable[Event],
    packets: Mapping[str, Packet],
    links: Mapping[str, Link] | None = None,
    pending_demand_count: int = 0,
    input_artifact_ids: Iterable[str] = (),
    summary_id: str | None = None,
) -> RunOutcomeSummary:
    """Derive immutable I1 metrics from canonical history and packet state."""

    _require_non_empty(run_id, "run_id")
    event_history = tuple(events)
    if pending_demand_count < 0:
        raise ValueError("pending_demand_count must be non-negative")

    completed_travel_times = _completed_travel_times(event_history)
    return RunOutcomeSummary(
        summary_id=summary_id or f"inspection:{run_id}:outcome-summary",
        run_id=run_id,
        travel_time=_travel_time_metrics(completed_travel_times),
        completion=_completion_metrics(
            event_history,
            packets,
            pending_demand_count,
        ),
        link_utilisation=_link_utilisation_metrics(event_history, links or {}),
        free_flow_comparison=_free_flow_comparison(
            completed_travel_times,
            packets,
            links,
        ),
        input_artifact_ids=tuple(input_artifact_ids),
        event_count=len(event_history),
    )


def _completed_travel_times(events: tuple[Event, ...]) -> dict[str, int]:
    instantiation_ticks: dict[str, int] = {}
    completed_ticks: dict[str, int] = {}
    for event in events:
        if event.event_type == EventType.INSTANTIATED:
            instantiation_ticks.setdefault(event.packet_id, event.physical_tick)
        elif event.event_type == EventType.COMPLETED:
            completed_ticks[event.packet_id] = event.physical_tick

    travel_times: dict[str, int] = {}
    for packet_id, completed_tick in completed_ticks.items():
        if packet_id not in instantiation_ticks:
            raise ValueError(
                f"completed packet {packet_id} has no instantiation event"
            )
        travel_time = completed_tick - instantiation_ticks[packet_id]
        if travel_time < 0:
            raise ValueError(
                f"completed packet {packet_id} has negative travel time"
            )
        travel_times[packet_id] = travel_time
    return travel_times


def _travel_time_metrics(travel_times_by_packet_id: Mapping[str, int]) -> TravelTimeMetrics:
    values = tuple(sorted(travel_times_by_packet_id.values()))
    total = sum(values)
    return TravelTimeMetrics(
        completed_packet_count=len(values),
        total_system_travel_time_ticks=total,
        average_travel_time_ticks=(total / len(values)) if values else None,
        median_travel_time_ticks=_percentile(values, 0.5),
        p95_travel_time_ticks=_percentile(values, 0.95),
        max_travel_time_ticks=max(values) if values else None,
    )


def _completion_metrics(
    events: tuple[Event, ...],
    packets: Mapping[str, Packet],
    pending_demand_count: int,
) -> CompletionMetrics:
    instantiated_packet_ids = {
        event.packet_id
        for event in events
        if event.event_type == EventType.INSTANTIATED
    }
    completed_packet_ids = {
        event.packet_id for event in events if event.event_type == EventType.COMPLETED
    }
    instantiated_packets = len(instantiated_packet_ids)
    return CompletionMetrics(
        instantiated_packets=instantiated_packets,
        completed_packets=len(completed_packet_ids),
        completion_percentage=(
            (len(completed_packet_ids) / instantiated_packets) * 100.0
            if instantiated_packets
            else 0.0
        ),
        remaining_active_packets=sum(
            packet.lifecycle_state == LifecycleState.IN_TRANSIT
            for packet in packets.values()
        ),
        remaining_queued_packets=sum(
            packet.lifecycle_state == LifecycleState.QUEUED
            for packet in packets.values()
        ),
        pending_demand_count=pending_demand_count,
    )


def _link_utilisation_metrics(
    events: tuple[Event, ...],
    links: Mapping[str, Link],
) -> tuple[LinkUtilisationMetrics, ...]:
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

    return tuple(
        LinkUtilisationMetrics(
            link_id=link_id,
            link_entry_count=entry_counts.get(link_id, 0),
            link_exit_count=exit_counts.get(link_id, 0),
        )
        for link_id in sorted(link_ids)
    )


def _free_flow_comparison(
    completed_travel_times: Mapping[str, int],
    packets: Mapping[str, Packet],
    links: Mapping[str, Link] | None,
) -> FreeFlowComparisonMetrics:
    ratios: list[float] = []
    unavailable_packet_ids: list[str] = []
    for packet_id, experienced_travel_time in completed_travel_times.items():
        packet = packets.get(packet_id)
        if packet is None or links is None:
            unavailable_packet_ids.append(packet_id)
            continue
        free_flow_ticks = _free_flow_ticks(packet.route_intent, links)
        if free_flow_ticks is None or free_flow_ticks <= 0:
            unavailable_packet_ids.append(packet_id)
            continue
        ratios.append(experienced_travel_time / free_flow_ticks)

    sorted_ratios = tuple(sorted(ratios))
    return FreeFlowComparisonMetrics(
        packet_count_with_free_flow=len(sorted_ratios),
        unavailable_packet_count=len(unavailable_packet_ids),
        unavailable_packet_ids=tuple(sorted(unavailable_packet_ids)),
        average_ratio=(
            sum(sorted_ratios) / len(sorted_ratios) if sorted_ratios else None
        ),
        median_ratio=_percentile(sorted_ratios, 0.5),
        p95_ratio=_percentile(sorted_ratios, 0.95),
    )


def _free_flow_ticks(
    route_intent: tuple[str, ...],
    links: Mapping[str, Link],
) -> int | None:
    total = 0
    for link_id in route_intent:
        link = links.get(link_id)
        if link is None or link.free_flow_ticks is None:
            return None
        total += link.free_flow_ticks
    return total


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


def _normalise_string_tuple(value: Iterable[str], field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        raise TypeError(f"{field_name} must be an iterable of strings, not a string")
    strings = tuple(value)
    for item in strings:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} must contain only strings")
        if not item:
            raise ValueError(f"{field_name} must not contain empty strings")
    return strings


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must be non-empty")
