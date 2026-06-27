"""Read-only M5 spillback validation artifacts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import Event, EventType


@dataclass(frozen=True, slots=True)
class QueueCurvePoint:
    """Cumulative queue-event state for one boundary and tick."""

    boundary_id: str
    tick: int
    cumulative_queue_entries: int
    cumulative_queue_exits: int
    queue_length: int


@dataclass(frozen=True, slots=True)
class BoundarySpillbackTrace:
    """Read-only spillback trace for one upstream/downstream boundary."""

    boundary_id: str
    upstream_link_id: str
    downstream_link_id: str
    queue_curve: tuple[QueueCurvePoint, ...]
    queue_entry_count: int
    queue_exit_count: int
    max_queue_length: int
    active_queue_length_from_events: int
    active_queue_length_from_engine: int | None
    first_queue_tick: int | None
    last_queue_tick: int | None
    downstream_receiving_causes: tuple[str, ...]
    is_queue_consistent_with_engine: bool


@dataclass(frozen=True, slots=True)
class SpillbackValidationReport:
    """M5 validation report derived from canonical events and read-only views."""

    model_profile_id: str
    max_tick: int
    boundary_traces: tuple[BoundarySpillbackTrace, ...]
    invariant_violations: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        """Return whether the event-derived spillback evidence is internally valid."""

        return not self.invariant_violations


def build_spillback_validation_report(
    engine: Any,
    *,
    boundary_ids: Iterable[str] | None = None,
    max_tick: int | None = None,
) -> SpillbackValidationReport:
    """Build M5 spillback validation evidence without mutating loading state."""

    report_max_tick = engine.current_tick if max_tick is None else max_tick
    if report_max_tick < 0:
        raise ValueError("max_tick cannot be negative")
    selected_boundary_ids = (
        tuple(boundary_ids)
        if boundary_ids is not None
        else _queue_boundary_ids(engine.event_log)
    )
    invariant_violations: list[str] = []
    if engine.model_profile_id != ACADEMIC_LTM_PARITY_PROFILE_ID:
        invariant_violations.append("model_profile_not_parity_ltm_v1")

    traces: list[BoundarySpillbackTrace] = []
    for boundary_id in selected_boundary_ids:
        upstream_link_id, downstream_link_id = _parse_boundary_id(boundary_id)
        if upstream_link_id not in engine.links:
            invariant_violations.append(f"{boundary_id}:unknown_upstream_link")
        if downstream_link_id not in engine.links:
            invariant_violations.append(f"{boundary_id}:unknown_downstream_link")
        if upstream_link_id not in engine.links or downstream_link_id not in engine.links:
            continue

        trace = _boundary_spillback_trace(
            engine,
            boundary_id=boundary_id,
            upstream_link_id=upstream_link_id,
            downstream_link_id=downstream_link_id,
            max_tick=report_max_tick,
        )
        traces.append(trace)
        if not trace.is_queue_consistent_with_engine:
            invariant_violations.append(f"{boundary_id}:queue_events_do_not_match_engine")
        if any(point.queue_length < 0 for point in trace.queue_curve):
            invariant_violations.append(f"{boundary_id}:negative_queue_length")

    return SpillbackValidationReport(
        model_profile_id=engine.model_profile_id,
        max_tick=report_max_tick,
        boundary_traces=tuple(traces),
        invariant_violations=tuple(invariant_violations),
    )


def _boundary_spillback_trace(
    engine: Any,
    *,
    boundary_id: str,
    upstream_link_id: str,
    downstream_link_id: str,
    max_tick: int,
) -> BoundarySpillbackTrace:
    queue_curve = _queue_curve(engine.event_log, boundary_id, max_tick)
    queue_entry_count = queue_curve[-1].cumulative_queue_entries if queue_curve else 0
    queue_exit_count = queue_curve[-1].cumulative_queue_exits if queue_curve else 0
    event_active_queue_length = queue_curve[-1].queue_length if queue_curve else 0
    engine_active_queue_length = (
        len(engine.packet_ids_in_queue(upstream_link_id, downstream_link_id))
        if max_tick == engine.current_tick
        else None
    )
    queued_ticks = tuple(point.tick for point in queue_curve if point.queue_length > 0)
    causes = _downstream_receiving_causes(
        engine,
        downstream_link_id=downstream_link_id,
        max_tick=max_tick,
    )
    return BoundarySpillbackTrace(
        boundary_id=boundary_id,
        upstream_link_id=upstream_link_id,
        downstream_link_id=downstream_link_id,
        queue_curve=queue_curve,
        queue_entry_count=queue_entry_count,
        queue_exit_count=queue_exit_count,
        max_queue_length=max((point.queue_length for point in queue_curve), default=0),
        active_queue_length_from_events=event_active_queue_length,
        active_queue_length_from_engine=engine_active_queue_length,
        first_queue_tick=queued_ticks[0] if queued_ticks else None,
        last_queue_tick=queued_ticks[-1] if queued_ticks else None,
        downstream_receiving_causes=causes,
        is_queue_consistent_with_engine=(
            engine_active_queue_length is None
            or event_active_queue_length == engine_active_queue_length
        ),
    )


def _queue_curve(
    events: Iterable[Event],
    boundary_id: str,
    max_tick: int,
) -> tuple[QueueCurvePoint, ...]:
    event_tuple = tuple(events)
    points: list[QueueCurvePoint] = []
    for tick in range(max_tick + 1):
        cumulative_entries = _queue_event_count(
            event_tuple,
            boundary_id,
            EventType.QUEUE_ENTRY,
            tick,
        )
        cumulative_exits = _queue_event_count(
            event_tuple,
            boundary_id,
            EventType.QUEUE_EXIT,
            tick,
        )
        points.append(
            QueueCurvePoint(
                boundary_id=boundary_id,
                tick=tick,
                cumulative_queue_entries=cumulative_entries,
                cumulative_queue_exits=cumulative_exits,
                queue_length=cumulative_entries - cumulative_exits,
            )
        )
    return tuple(points)


def _downstream_receiving_causes(
    engine: Any,
    *,
    downstream_link_id: str,
    max_tick: int,
) -> tuple[str, ...]:
    causes: list[str] = []
    for tick in range(max_tick + 1):
        try:
            cause = engine.receiving_decision_trace(
                downstream_link_id,
                tick=tick,
            ).supply_view.receiving_cause
        except ValueError:
            continue
        cause_value = getattr(cause, "value", str(cause))
        if cause_value not in causes:
            causes.append(cause_value)
    return tuple(causes)


def _queue_boundary_ids(events: Iterable[Event]) -> tuple[str, ...]:
    boundary_ids = {
        event.entity_id
        for event in events
        if event.event_type in {EventType.QUEUE_ENTRY, EventType.QUEUE_EXIT}
    }
    return tuple(sorted(boundary_ids))


def _queue_event_count(
    events: Iterable[Event],
    boundary_id: str,
    event_type: EventType,
    tick: int,
) -> int:
    return sum(
        event.event_type == event_type
        and event.entity_id == boundary_id
        and event.physical_tick <= tick
        for event in events
    )


def _parse_boundary_id(boundary_id: str) -> tuple[str, str]:
    if not boundary_id.startswith("boundary:"):
        raise ValueError(f"unsupported boundary_id: {boundary_id}")
    upstream_link_id, downstream_link_id = boundary_id.removeprefix("boundary:").split(
        "->",
        1,
    )
    return upstream_link_id, downstream_link_id
