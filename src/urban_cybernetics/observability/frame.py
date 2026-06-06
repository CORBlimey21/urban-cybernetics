"""Immutable observation frame artifacts."""

from __future__ import annotations

from dataclasses import dataclass

from urban_cybernetics.core import EventType
from urban_cybernetics.observability.sensor import (
    BOUNDARY_EVENT_TYPES,
    SUPPORTED_NOISE_MODELS,
)


@dataclass(frozen=True)
class ObservationFrame:
    """Sealed boundary-count measurement derived from physical event history."""

    frame_id: str
    sensor_id: str
    observed_link_id: str
    boundary_event_type: EventType
    measurement_tick: int
    aggregation_window_ticks: int
    window_start_tick_exclusive: int
    window_end_tick_inclusive: int
    publication_tick: int
    primary_count: int
    noise_model: str = "none"
    schema_version: str = "m12.observation_frame.v1"

    def __post_init__(self) -> None:
        if self.boundary_event_type not in BOUNDARY_EVENT_TYPES:
            raise ValueError(
                "M12 observation frames may record only LINK_ENTRY or LINK_EXIT events"
            )
        if self.aggregation_window_ticks <= 0:
            raise ValueError("aggregation_window_ticks must be positive")
        if self.window_end_tick_inclusive != self.measurement_tick:
            raise ValueError("window_end_tick_inclusive must equal measurement_tick")
        expected_start_tick = self.measurement_tick - self.aggregation_window_ticks
        if self.window_start_tick_exclusive != expected_start_tick:
            raise ValueError(
                "window_start_tick_exclusive must equal measurement_tick - "
                "aggregation_window_ticks"
            )
        if self.publication_tick < self.measurement_tick:
            raise ValueError("publication_tick must not precede measurement_tick")
        if self.primary_count < 0:
            raise ValueError("primary_count must be non-negative")
        if self.noise_model not in SUPPORTED_NOISE_MODELS:
            raise ValueError("M12 supports only noise_model='none'")
