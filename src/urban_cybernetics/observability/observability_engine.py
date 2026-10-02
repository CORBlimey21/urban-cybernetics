# SPDX-License-Identifier: MPL-2.0
"""Observation-frame sampler for loading-engine physical event history."""

from __future__ import annotations

from collections.abc import Iterable

from urban_cybernetics.core import Event
from urban_cybernetics.observability.frame import ObservationFrame
from urban_cybernetics.observability.sensor import SensorConfig


class ObservabilityEngine:
    """Samples immutable observation frames from physical event history."""

    def __init__(self, sensors: Iterable[SensorConfig]) -> None:
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
    def sensors(self) -> tuple[SensorConfig, ...]:
        """Read-only sensor configuration tuple."""

        return self._sensors

    def sample(
        self,
        *,
        events: Iterable[Event],
        measurement_tick: int,
    ) -> tuple[ObservationFrame, ...]:
        """Sample all configured sensors at one completed loading tick."""

        event_tuple = tuple(events)
        return tuple(
            self._sample_sensor(
                sensor,
                event_tuple,
                measurement_tick,
            )
            for sensor in self._sensors
        )

    def _sample_sensor(
        self,
        sensor: SensorConfig,
        events: tuple[Event, ...],
        measurement_tick: int,
    ) -> ObservationFrame:
        window_start_tick_exclusive = (
            measurement_tick - sensor.aggregation_window_ticks
        )
        window_end_tick_inclusive = measurement_tick
        primary_count = sum(
            event.event_type == sensor.boundary_event_type
            and event.entity_id == sensor.observed_link_id
            and window_start_tick_exclusive
            < event.physical_tick
            <= window_end_tick_inclusive
            for event in events
        )
        return ObservationFrame(
            frame_id=f"frame:{sensor.sensor_id}:{measurement_tick}",
            sensor_id=sensor.sensor_id,
            observed_link_id=sensor.observed_link_id,
            boundary_event_type=sensor.boundary_event_type,
            measurement_tick=measurement_tick,
            aggregation_window_ticks=sensor.aggregation_window_ticks,
            window_start_tick_exclusive=window_start_tick_exclusive,
            window_end_tick_inclusive=window_end_tick_inclusive,
            publication_tick=measurement_tick + sensor.publication_delay_ticks,
            primary_count=primary_count,
            noise_model=sensor.noise_model,
        )
