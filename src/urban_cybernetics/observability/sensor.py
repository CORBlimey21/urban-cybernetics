# SPDX-License-Identifier: MPL-2.0
"""Immutable sensor configuration for observation-frame sampling."""

from __future__ import annotations

from dataclasses import dataclass

from urban_cybernetics.core import EventType


BOUNDARY_EVENT_TYPES = frozenset((EventType.LINK_ENTRY, EventType.LINK_EXIT))
SUPPORTED_NOISE_MODELS = frozenset(("none",))


@dataclass(frozen=True, slots=True)
class SensorConfig:
    """Declared boundary-count sensor configuration for one simulation run."""

    sensor_id: str
    observed_link_id: str
    boundary_event_type: EventType
    aggregation_window_ticks: int
    publication_delay_ticks: int = 0
    noise_model: str = "none"

    def __post_init__(self) -> None:
        if self.boundary_event_type not in BOUNDARY_EVENT_TYPES:
            raise ValueError(
                "M12 sensors may observe only LINK_ENTRY or LINK_EXIT events"
            )
        if self.aggregation_window_ticks <= 0:
            raise ValueError("aggregation_window_ticks must be positive")
        if self.publication_delay_ticks < 0:
            raise ValueError("publication_delay_ticks must be non-negative")
        if self.noise_model not in SUPPORTED_NOISE_MODELS:
            raise ValueError("M12 supports only noise_model='none'")


@dataclass(frozen=True, slots=True)
class LinkTraversalTimeSensorConfig:
    """Declared probe-style traversal-time sensor configuration."""

    sensor_id: str
    observed_link_id: str
    aggregation_window_ticks: int
    publication_delay_ticks: int = 0
    noise_model: str = "none"

    def __post_init__(self) -> None:
        if not self.sensor_id:
            raise ValueError("sensor_id must be non-empty")
        if not self.observed_link_id:
            raise ValueError("observed_link_id must be non-empty")
        if self.aggregation_window_ticks <= 0:
            raise ValueError("aggregation_window_ticks must be positive")
        if self.publication_delay_ticks < 0:
            raise ValueError("publication_delay_ticks must be non-negative")
        if self.noise_model not in SUPPORTED_NOISE_MODELS:
            raise ValueError("O1 supports only noise_model='none'")
