"""Immutable link metadata for synthetic loading tests."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor


LEGACY_STORAGE_CAPACITY_PACKETS = 1_000_000


@dataclass(frozen=True, slots=True)
class Link:
    """Single directed link with declared static loading metadata."""

    link_id: str
    free_flow_ticks: int | None = None
    # Static declared sending metadata, not mutable current flow, effective capacity, or BPR capacity.
    declared_sending_capacity_per_tick: int = 1
    # Static declared receiving metadata, not mutable current capacity, traversal capacity, or BPR capacity.
    declared_receiving_capacity_per_tick: int = 1
    # Static packet storage metadata, not mutable current storage or occupancy.
    declared_storage_capacity_packets: int | None = None
    # Immutable physical metadata. These are not dynamic loading state.
    length_m: float | None = None
    lane_count: int | None = None
    free_flow_speed_mps: float | None = None
    jam_density_veh_per_km_per_lane: float | None = None
    backward_wave_speed_mps: float | None = None
    capacity_veh_per_hour_per_lane: float | None = None
    tick_duration_seconds: float = 1.0

    def __post_init__(self) -> None:
        self._validate_positive_int(
            "declared_sending_capacity_per_tick",
            self.declared_sending_capacity_per_tick,
            allow_zero=True,
        )
        self._validate_positive_int(
            "declared_receiving_capacity_per_tick",
            self.declared_receiving_capacity_per_tick,
            allow_zero=True,
        )
        self._validate_physical_metadata()
        object.__setattr__(self, "free_flow_ticks", self._resolved_free_flow_ticks())
        object.__setattr__(
            self,
            "declared_storage_capacity_packets",
            self._resolved_storage_capacity_packets(),
        )

    def _validate_physical_metadata(self) -> None:
        if self.length_m is not None and self.length_m <= 0:
            raise ValueError(f"length_m must be positive for {self.link_id}")
        if self.lane_count is not None:
            self._validate_positive_int("lane_count", self.lane_count)
        if self.free_flow_speed_mps is not None and self.free_flow_speed_mps <= 0:
            raise ValueError(f"free_flow_speed_mps must be positive for {self.link_id}")
        if (
            self.jam_density_veh_per_km_per_lane is not None
            and self.jam_density_veh_per_km_per_lane <= 0
        ):
            raise ValueError(
                f"jam_density_veh_per_km_per_lane must be positive for {self.link_id}"
            )
        if self.backward_wave_speed_mps is not None and self.backward_wave_speed_mps <= 0:
            raise ValueError(f"backward_wave_speed_mps must be positive for {self.link_id}")
        if (
            self.capacity_veh_per_hour_per_lane is not None
            and self.capacity_veh_per_hour_per_lane <= 0
        ):
            raise ValueError(
                f"capacity_veh_per_hour_per_lane must be positive for {self.link_id}"
            )
        if self.tick_duration_seconds <= 0:
            raise ValueError(f"tick_duration_seconds must be positive for {self.link_id}")

    def _resolved_free_flow_ticks(self) -> int:
        if self.free_flow_ticks is not None:
            self._validate_positive_int(
                "free_flow_ticks",
                self.free_flow_ticks,
                allow_zero=True,
            )
            return self.free_flow_ticks
        if self.length_m is None or self.free_flow_speed_mps is None:
            raise ValueError(
                "free_flow_ticks must be declared unless length_m and "
                f"free_flow_speed_mps are available for {self.link_id}"
            )
        free_flow_seconds = self.length_m / self.free_flow_speed_mps
        return max(1, ceil(free_flow_seconds / self.tick_duration_seconds))

    def _resolved_storage_capacity_packets(self) -> int:
        if self.declared_storage_capacity_packets is not None:
            self._validate_positive_int(
                "declared_storage_capacity_packets",
                self.declared_storage_capacity_packets,
                allow_zero=True,
            )
            return self.declared_storage_capacity_packets

        storage_inputs = (
            self.length_m,
            self.lane_count,
            self.jam_density_veh_per_km_per_lane,
        )
        if all(value is None for value in storage_inputs):
            return LEGACY_STORAGE_CAPACITY_PACKETS
        if any(value is None for value in storage_inputs):
            raise ValueError(
                "derived storage requires length_m, lane_count, and "
                f"jam_density_veh_per_km_per_lane for {self.link_id}"
            )

        length_km = self.length_m / 1000.0
        storage_packets = floor(
            length_km * self.lane_count * self.jam_density_veh_per_km_per_lane
        )
        return max(1, storage_packets)

    @staticmethod
    def _validate_positive_int(
        field_name: str,
        value: int,
        *,
        allow_zero: bool = False,
    ) -> None:
        if not isinstance(value, int):
            raise TypeError(f"{field_name} must be an int")
        if allow_zero:
            if value < 0:
                raise ValueError(f"{field_name} cannot be negative")
        elif value <= 0:
            raise ValueError(f"{field_name} must be positive")
