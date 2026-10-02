# SPDX-License-Identifier: MPL-2.0
"""Immutable observation frame artifacts."""

from __future__ import annotations

from dataclasses import dataclass

from urban_cybernetics.core import EventType
from urban_cybernetics.observability.sensor import (
    BOUNDARY_EVENT_TYPES,
    SUPPORTED_NOISE_MODELS,
)


@dataclass(frozen=True, slots=True)
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


@dataclass(frozen=True, slots=True)
class LinkTraversalTimeObservationFrame:
    """Sealed probe-style link traversal-time observation."""

    frame_id: str
    sensor_id: str
    observed_link_id: str
    measurement_tick: int
    aggregation_window_ticks: int
    window_start_tick_exclusive: int
    window_end_tick_inclusive: int
    publication_tick: int
    sample_count: int
    mean_traversal_time_ticks: float | None
    min_traversal_time_ticks: int | None = None
    max_traversal_time_ticks: int | None = None
    mean_delay_ticks: float | None = None
    delay_ratio: float | None = None
    source_type: str = "probe"
    observable_type: str = "link_traversal_time"
    noise_model: str = "none"
    schema_version: str = "o1.link_traversal_time_frame.v1"

    def __post_init__(self) -> None:
        if not self.frame_id:
            raise ValueError("frame_id must be non-empty")
        if not self.sensor_id:
            raise ValueError("sensor_id must be non-empty")
        if not self.observed_link_id:
            raise ValueError("observed_link_id must be non-empty")
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
        if self.sample_count < 0:
            raise ValueError("sample_count must be non-negative")
        if self.source_type != "probe":
            raise ValueError("O1 traversal-time frames must use source_type='probe'")
        if self.observable_type != "link_traversal_time":
            raise ValueError(
                "O1 traversal-time frames must use "
                "observable_type='link_traversal_time'"
            )
        if self.noise_model not in SUPPORTED_NOISE_MODELS:
            raise ValueError("O1 supports only noise_model='none'")
        self._validate_empty_or_sampled_fields()

    def _validate_empty_or_sampled_fields(self) -> None:
        traversal_fields = (
            self.mean_traversal_time_ticks,
            self.min_traversal_time_ticks,
            self.max_traversal_time_ticks,
            self.mean_delay_ticks,
            self.delay_ratio,
        )
        if self.sample_count == 0:
            if any(value is not None for value in traversal_fields):
                raise ValueError("empty traversal-time samples must use None metrics")
            return

        if self.mean_traversal_time_ticks is None:
            raise ValueError("mean_traversal_time_ticks is required when sampled")
        if self.min_traversal_time_ticks is None:
            raise ValueError("min_traversal_time_ticks is required when sampled")
        if self.max_traversal_time_ticks is None:
            raise ValueError("max_traversal_time_ticks is required when sampled")
        if self.mean_traversal_time_ticks < 0:
            raise ValueError("mean_traversal_time_ticks must be non-negative")
        if self.min_traversal_time_ticks < 0:
            raise ValueError("min_traversal_time_ticks must be non-negative")
        if self.max_traversal_time_ticks < self.min_traversal_time_ticks:
            raise ValueError(
                "max_traversal_time_ticks must not be less than "
                "min_traversal_time_ticks"
            )
        if self.delay_ratio is not None and self.delay_ratio < 0:
            raise ValueError("delay_ratio must be non-negative")
