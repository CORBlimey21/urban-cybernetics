# SPDX-License-Identifier: MPL-2.0
"""Authority-visible observation frame filtering and receipt artifacts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


class ObservationFrameLike(Protocol):
    """Common visibility fields shared by immutable observation artifacts."""

    frame_id: str
    sensor_id: str
    measurement_tick: int
    publication_tick: int


@dataclass(frozen=True, slots=True)
class AuthorityVisibilityConfig:
    """Static M14 visibility configuration for one routing authority."""

    authority_id: str
    receipt_delay_ticks: int
    accessible_sensor_ids: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not self.authority_id:
            raise ValueError("authority_id must be non-empty")
        if self.receipt_delay_ticks < 0:
            raise ValueError("receipt_delay_ticks must be non-negative")
        if self.accessible_sensor_ids is not None:
            object.__setattr__(
                self,
                "accessible_sensor_ids",
                tuple(self.accessible_sensor_ids),
            )


@dataclass(frozen=True, slots=True)
class FrameReceipt:
    """Immutable artifact recording first authority visibility for one frame."""

    receipt_id: str
    authority_id: str
    frame_id: str
    receipt_tick: int
    publication_tick: int
    measurement_tick: int
    sensor_id: str
    schema_version: str = "m14.frame_receipt.v1"

    def __post_init__(self) -> None:
        if not self.receipt_id:
            raise ValueError("receipt_id must be non-empty")
        if not self.authority_id:
            raise ValueError("authority_id must be non-empty")
        if not self.frame_id:
            raise ValueError("frame_id must be non-empty")
        if not self.sensor_id:
            raise ValueError("sensor_id must be non-empty")
        if self.receipt_tick < self.publication_tick:
            raise ValueError("receipt_tick must not precede publication_tick")
        if self.publication_tick < self.measurement_tick:
            raise ValueError("publication_tick must not precede measurement_tick")


class AuthorityVisibleStateResolver:
    """Resolve authority-visible frames from immutable observation artifacts."""

    def __init__(self, configs: Iterable[AuthorityVisibilityConfig]) -> None:
        config_tuple = tuple(configs)
        self._configs = {config.authority_id: config for config in config_tuple}
        if len(self._configs) != len(config_tuple):
            raise ValueError("duplicate authority_id values are not allowed")

    def visible_frames(
        self,
        *,
        authority_id: str,
        frames: Iterable[ObservationFrameLike],
        decision_tick: int,
    ) -> tuple[ObservationFrameLike, ...]:
        """Return frames visible to one authority by one decision tick."""

        config = self._config_for(authority_id)
        visible = [
            frame
            for frame in frames
            if self._is_accessible(config, frame)
            and self._receipt_tick(config, frame) <= decision_tick
        ]
        return tuple(sorted(visible, key=lambda frame: self._sort_key(config, frame)))

    def receipts_available_by(
        self,
        *,
        authority_id: str,
        frames: Iterable[ObservationFrameLike],
        decision_tick: int,
    ) -> tuple[FrameReceipt, ...]:
        """Return receipt artifacts for frames visible by one decision tick."""

        config = self._config_for(authority_id)
        receipts = [
            self._receipt_for(config, frame)
            for frame in frames
            if self._is_accessible(config, frame)
            and self._receipt_tick(config, frame) <= decision_tick
        ]
        return tuple(
            sorted(
                receipts,
                key=lambda receipt: (
                    receipt.receipt_tick,
                    receipt.publication_tick,
                    receipt.measurement_tick,
                    receipt.sensor_id,
                    receipt.frame_id,
                ),
            )
        )

    def _config_for(self, authority_id: str) -> AuthorityVisibilityConfig:
        try:
            return self._configs[authority_id]
        except KeyError as exc:
            raise KeyError(f"unknown authority_id: {authority_id}") from exc

    def _is_accessible(
        self,
        config: AuthorityVisibilityConfig,
        frame: ObservationFrameLike,
    ) -> bool:
        if config.accessible_sensor_ids is None:
            return True
        return frame.sensor_id in config.accessible_sensor_ids

    def _receipt_tick(
        self,
        config: AuthorityVisibilityConfig,
        frame: ObservationFrameLike,
    ) -> int:
        return frame.publication_tick + config.receipt_delay_ticks

    def _receipt_for(
        self,
        config: AuthorityVisibilityConfig,
        frame: ObservationFrameLike,
    ) -> FrameReceipt:
        receipt_tick = self._receipt_tick(config, frame)
        return FrameReceipt(
            receipt_id=f"receipt:{config.authority_id}:{frame.frame_id}:{receipt_tick}",
            authority_id=config.authority_id,
            frame_id=frame.frame_id,
            receipt_tick=receipt_tick,
            publication_tick=frame.publication_tick,
            measurement_tick=frame.measurement_tick,
            sensor_id=frame.sensor_id,
        )

    def _sort_key(
        self,
        config: AuthorityVisibilityConfig,
        frame: ObservationFrameLike,
    ) -> tuple[int, int, int, str, str]:
        return (
            self._receipt_tick(config, frame),
            frame.publication_tick,
            frame.measurement_tick,
            frame.sensor_id,
            frame.frame_id,
        )
