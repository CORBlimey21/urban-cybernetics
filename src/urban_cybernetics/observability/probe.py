"""Probe-style observation sampling from packet event history."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from urban_cybernetics.core import Event, EventType
from urban_cybernetics.observability.frame import LinkTraversalTimeObservationFrame
from urban_cybernetics.observability.sensor import LinkTraversalTimeSensorConfig


class ProbeObservabilityEngine:
    """Samples probe-style observation frames from physical event history."""

    def __init__(self, sensors: Iterable[LinkTraversalTimeSensorConfig]) -> None:
        sensor_tuple = tuple(sensors)
        sensor_ids = [sensor.sensor_id for sensor in sensor_tuple]
        duplicate_sensor_ids = {
            sensor_id for sensor_id in sensor_ids if sensor_ids.count(sensor_id) > 1
        }
        if duplicate_sensor_ids:
            raise ValueError(
                "duplicate sensor_id values are not allowed: "
                f"{tuple(sorted(duplicate_sensor_ids))}"
            )
        self._sensors = sensor_tuple

    @property
    def sensors(self) -> tuple[LinkTraversalTimeSensorConfig, ...]:
        """Read-only probe sensor configuration tuple."""

        return self._sensors

    def sample(
        self,
        *,
        events: Iterable[Event],
        measurement_tick: int,
        link_metadata: Mapping[str, object] | None = None,
    ) -> tuple[LinkTraversalTimeObservationFrame, ...]:
        """Sample all configured probe sensors at one completed loading tick."""

        event_tuple = tuple(events)
        return tuple(
            sample_link_traversal_time_frame(
                sensor=sensor,
                events=event_tuple,
                measurement_tick=measurement_tick,
                link_metadata=link_metadata,
            )
            for sensor in self._sensors
        )


def sample_link_traversal_time_frame(
    *,
    sensor: LinkTraversalTimeSensorConfig,
    events: Iterable[Event],
    measurement_tick: int,
    link_metadata: Mapping[str, object] | None = None,
) -> LinkTraversalTimeObservationFrame:
    """Sample one link traversal-time frame from completed entry/exit pairs."""

    window_start_tick_exclusive = measurement_tick - sensor.aggregation_window_ticks
    window_end_tick_inclusive = measurement_tick
    traversal_times = _completed_traversal_times(
        events=events,
        link_id=sensor.observed_link_id,
        window_start_tick_exclusive=window_start_tick_exclusive,
        window_end_tick_inclusive=window_end_tick_inclusive,
    )
    sample_count = len(traversal_times)
    mean_traversal_time_ticks: float | None = None
    min_traversal_time_ticks: int | None = None
    max_traversal_time_ticks: int | None = None
    mean_delay_ticks: float | None = None
    delay_ratio: float | None = None

    if traversal_times:
        mean_traversal_time_ticks = sum(traversal_times) / sample_count
        min_traversal_time_ticks = min(traversal_times)
        max_traversal_time_ticks = max(traversal_times)
        free_flow_ticks = _free_flow_ticks_for(
            sensor.observed_link_id,
            link_metadata,
        )
        if free_flow_ticks is not None:
            mean_delay_ticks = mean_traversal_time_ticks - free_flow_ticks
            if free_flow_ticks > 0:
                delay_ratio = mean_traversal_time_ticks / free_flow_ticks

    return LinkTraversalTimeObservationFrame(
        frame_id=f"frame:{sensor.sensor_id}:link_traversal_time:{measurement_tick}",
        sensor_id=sensor.sensor_id,
        observed_link_id=sensor.observed_link_id,
        measurement_tick=measurement_tick,
        aggregation_window_ticks=sensor.aggregation_window_ticks,
        window_start_tick_exclusive=window_start_tick_exclusive,
        window_end_tick_inclusive=window_end_tick_inclusive,
        publication_tick=measurement_tick + sensor.publication_delay_ticks,
        sample_count=sample_count,
        mean_traversal_time_ticks=mean_traversal_time_ticks,
        min_traversal_time_ticks=min_traversal_time_ticks,
        max_traversal_time_ticks=max_traversal_time_ticks,
        mean_delay_ticks=mean_delay_ticks,
        delay_ratio=delay_ratio,
        noise_model=sensor.noise_model,
    )


def _completed_traversal_times(
    *,
    events: Iterable[Event],
    link_id: str,
    window_start_tick_exclusive: int,
    window_end_tick_inclusive: int,
) -> tuple[int, ...]:
    unmatched_entries_by_packet: dict[str, list[Event]] = {}
    traversal_times: list[int] = []

    for event in sorted(events, key=lambda item: item.sequence_number):
        if event.entity_id != link_id:
            continue
        if event.event_type == EventType.LINK_ENTRY:
            unmatched_entries_by_packet.setdefault(event.packet_id, []).append(event)
            continue
        if event.event_type != EventType.LINK_EXIT:
            continue

        packet_entries = unmatched_entries_by_packet.get(event.packet_id)
        if not packet_entries:
            continue
        entry_event = packet_entries.pop()
        if not packet_entries:
            del unmatched_entries_by_packet[event.packet_id]
        if window_start_tick_exclusive < event.physical_tick <= window_end_tick_inclusive:
            traversal_times.append(event.physical_tick - entry_event.physical_tick)

    return tuple(traversal_times)


def _free_flow_ticks_for(
    link_id: str,
    link_metadata: Mapping[str, object] | None,
) -> int | None:
    if link_metadata is None or link_id not in link_metadata:
        return None

    link_record = link_metadata[link_id]
    if isinstance(link_record, int):
        return link_record
    free_flow_ticks = getattr(link_record, "free_flow_ticks", None)
    if isinstance(free_flow_ticks, int):
        return free_flow_ticks
    return None
