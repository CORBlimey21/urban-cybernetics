"""Immutable link metadata for synthetic loading tests."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor


LEGACY_STORAGE_CAPACITY_PACKETS = 1_000_000
DEFAULT_FD_RELATIVE_TOLERANCE = 1e-6
DEFAULT_MINIMUM_TIMESTEP_LAG_TICKS = 1


@dataclass(frozen=True, slots=True)
class FundamentalDiagramConsistencyReport:
    """Static triangular-FD capacity consistency for one link."""

    link_id: str
    declared_capacity_veh_per_hour_per_lane: float
    expected_capacity_veh_per_hour_per_lane: float
    critical_density_veh_per_km_per_lane: float
    relative_error: float
    relative_tolerance: float
    is_consistent: bool


@dataclass(frozen=True, slots=True)
class TimestepAdmissibilityReport:
    """Static timestep admissibility report for free-flow and vacancy lags."""

    link_id: str
    tick_duration_seconds: float
    free_flow_travel_time_seconds: float
    backward_wave_travel_time_seconds: float
    free_flow_lag_ticks: int
    backward_wave_lag_ticks: int
    minimum_lag_ticks: int
    is_admissible: bool
    ineligibility_reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedPhysicalLinkParameters:
    """Resolved static physical interpretation for parity eligibility checks."""

    link_id: str
    tick_duration_seconds: float
    length_m: float | None
    lane_count: int | None
    free_flow_speed_mps: float | None
    backward_wave_speed_mps: float | None
    jam_density_veh_per_km_per_lane: float | None
    capacity_veh_per_hour_per_lane: float | None
    free_flow_travel_time_seconds: float | None
    backward_wave_travel_time_seconds: float | None
    free_flow_lag_ticks: int | None
    backward_wave_lag_ticks: int | None
    storage_capacity_packets: int | None
    total_capacity_vehicles_per_tick: float | None
    fd_report: FundamentalDiagramConsistencyReport | None
    timestep_report: TimestepAdmissibilityReport | None
    missing_physical_fields: tuple[str, ...] = ()
    parity_eligible: bool = False
    ineligibility_reasons: tuple[str, ...] = ()


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

    def resolved_physical_parameters(
        self,
        *,
        fd_relative_tolerance: float = DEFAULT_FD_RELATIVE_TOLERANCE,
        minimum_lag_ticks: int = DEFAULT_MINIMUM_TIMESTEP_LAG_TICKS,
    ) -> ResolvedPhysicalLinkParameters:
        """Return static parity-eligibility parameters without changing loading behaviour."""

        _validate_positive_float("fd_relative_tolerance", fd_relative_tolerance)
        self._validate_positive_int("minimum_lag_ticks", minimum_lag_ticks)
        missing_fields = self._missing_parity_physical_fields()
        if missing_fields:
            reasons = tuple(
                f"missing_physical_metadata:{field_name}"
                for field_name in missing_fields
            )
            return ResolvedPhysicalLinkParameters(
                link_id=self.link_id,
                tick_duration_seconds=self.tick_duration_seconds,
                length_m=self.length_m,
                lane_count=self.lane_count,
                free_flow_speed_mps=self.free_flow_speed_mps,
                backward_wave_speed_mps=self.backward_wave_speed_mps,
                jam_density_veh_per_km_per_lane=self.jam_density_veh_per_km_per_lane,
                capacity_veh_per_hour_per_lane=self.capacity_veh_per_hour_per_lane,
                free_flow_travel_time_seconds=None,
                backward_wave_travel_time_seconds=None,
                free_flow_lag_ticks=None,
                backward_wave_lag_ticks=None,
                storage_capacity_packets=None,
                total_capacity_vehicles_per_tick=None,
                fd_report=None,
                timestep_report=None,
                missing_physical_fields=missing_fields,
                parity_eligible=False,
                ineligibility_reasons=reasons,
            )

        length_m = self.length_m
        lane_count = self.lane_count
        free_flow_speed_mps = self.free_flow_speed_mps
        backward_wave_speed_mps = self.backward_wave_speed_mps
        jam_density = self.jam_density_veh_per_km_per_lane
        declared_capacity = self.capacity_veh_per_hour_per_lane
        assert length_m is not None
        assert lane_count is not None
        assert free_flow_speed_mps is not None
        assert backward_wave_speed_mps is not None
        assert jam_density is not None
        assert declared_capacity is not None

        free_flow_seconds = length_m / free_flow_speed_mps
        backward_wave_seconds = length_m / backward_wave_speed_mps
        free_flow_lag_ticks = max(
            1,
            ceil(free_flow_seconds / self.tick_duration_seconds),
        )
        backward_wave_lag_ticks = max(
            1,
            ceil(backward_wave_seconds / self.tick_duration_seconds),
        )
        storage_capacity_packets = max(
            1,
            floor((length_m / 1000.0) * lane_count * jam_density),
        )
        expected_capacity = _triangular_fd_capacity_veh_per_hour_per_lane(
            free_flow_speed_mps=free_flow_speed_mps,
            backward_wave_speed_mps=backward_wave_speed_mps,
            jam_density_veh_per_km_per_lane=jam_density,
        )
        relative_error = abs(declared_capacity - expected_capacity) / expected_capacity
        fd_report = FundamentalDiagramConsistencyReport(
            link_id=self.link_id,
            declared_capacity_veh_per_hour_per_lane=declared_capacity,
            expected_capacity_veh_per_hour_per_lane=expected_capacity,
            critical_density_veh_per_km_per_lane=(
                expected_capacity / 3600.0 / free_flow_speed_mps * 1000.0
            ),
            relative_error=relative_error,
            relative_tolerance=fd_relative_tolerance,
            is_consistent=relative_error <= fd_relative_tolerance,
        )
        timestep_report = _timestep_admissibility_report(
            link_id=self.link_id,
            tick_duration_seconds=self.tick_duration_seconds,
            free_flow_travel_time_seconds=free_flow_seconds,
            backward_wave_travel_time_seconds=backward_wave_seconds,
            free_flow_lag_ticks=free_flow_lag_ticks,
            backward_wave_lag_ticks=backward_wave_lag_ticks,
            minimum_lag_ticks=minimum_lag_ticks,
        )
        total_capacity_vehicles_per_tick = (
            declared_capacity * lane_count * self.tick_duration_seconds / 3600.0
        )

        ineligibility_reasons: list[str] = []
        if not fd_report.is_consistent:
            ineligibility_reasons.append("fundamental_diagram_inconsistent")
        if not timestep_report.is_admissible:
            ineligibility_reasons.extend(timestep_report.ineligibility_reasons)
        if self.free_flow_ticks != free_flow_lag_ticks:
            ineligibility_reasons.append("free_flow_ticks_inconsistent")
        if self.declared_storage_capacity_packets != storage_capacity_packets:
            ineligibility_reasons.append("storage_capacity_inconsistent")

        return ResolvedPhysicalLinkParameters(
            link_id=self.link_id,
            tick_duration_seconds=self.tick_duration_seconds,
            length_m=length_m,
            lane_count=lane_count,
            free_flow_speed_mps=free_flow_speed_mps,
            backward_wave_speed_mps=backward_wave_speed_mps,
            jam_density_veh_per_km_per_lane=jam_density,
            capacity_veh_per_hour_per_lane=declared_capacity,
            free_flow_travel_time_seconds=free_flow_seconds,
            backward_wave_travel_time_seconds=backward_wave_seconds,
            free_flow_lag_ticks=free_flow_lag_ticks,
            backward_wave_lag_ticks=backward_wave_lag_ticks,
            storage_capacity_packets=storage_capacity_packets,
            total_capacity_vehicles_per_tick=total_capacity_vehicles_per_tick,
            fd_report=fd_report,
            timestep_report=timestep_report,
            missing_physical_fields=(),
            parity_eligible=not ineligibility_reasons,
            ineligibility_reasons=tuple(ineligibility_reasons),
        )

    def require_parity_physical_parameters(
        self,
        *,
        fd_relative_tolerance: float = DEFAULT_FD_RELATIVE_TOLERANCE,
        minimum_lag_ticks: int = DEFAULT_MINIMUM_TIMESTEP_LAG_TICKS,
    ) -> ResolvedPhysicalLinkParameters:
        """Return resolved parameters or fail loudly when the link is not parity eligible."""

        resolved = self.resolved_physical_parameters(
            fd_relative_tolerance=fd_relative_tolerance,
            minimum_lag_ticks=minimum_lag_ticks,
        )
        if not resolved.parity_eligible:
            raise ValueError(
                f"link {self.link_id} is not parity-eligible: "
                f"{resolved.ineligibility_reasons}"
            )
        return resolved

    def _missing_parity_physical_fields(self) -> tuple[str, ...]:
        fields = (
            ("length_m", self.length_m),
            ("lane_count", self.lane_count),
            ("free_flow_speed_mps", self.free_flow_speed_mps),
            ("backward_wave_speed_mps", self.backward_wave_speed_mps),
            ("jam_density_veh_per_km_per_lane", self.jam_density_veh_per_km_per_lane),
            ("capacity_veh_per_hour_per_lane", self.capacity_veh_per_hour_per_lane),
        )
        return tuple(field_name for field_name, value in fields if value is None)

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


def _triangular_fd_capacity_veh_per_hour_per_lane(
    *,
    free_flow_speed_mps: float,
    backward_wave_speed_mps: float,
    jam_density_veh_per_km_per_lane: float,
) -> float:
    jam_density_veh_per_m_per_lane = jam_density_veh_per_km_per_lane / 1000.0
    capacity_veh_per_second_per_lane = (
        free_flow_speed_mps
        * backward_wave_speed_mps
        * jam_density_veh_per_m_per_lane
        / (free_flow_speed_mps + backward_wave_speed_mps)
    )
    return capacity_veh_per_second_per_lane * 3600.0


def _timestep_admissibility_report(
    *,
    link_id: str,
    tick_duration_seconds: float,
    free_flow_travel_time_seconds: float,
    backward_wave_travel_time_seconds: float,
    free_flow_lag_ticks: int,
    backward_wave_lag_ticks: int,
    minimum_lag_ticks: int,
) -> TimestepAdmissibilityReport:
    reasons: list[str] = []
    if free_flow_lag_ticks < minimum_lag_ticks:
        reasons.append("free_flow_lag_below_minimum")
    if backward_wave_lag_ticks < minimum_lag_ticks:
        reasons.append("backward_wave_lag_below_minimum")
    if tick_duration_seconds > free_flow_travel_time_seconds:
        reasons.append("tick_exceeds_free_flow_travel_time")
    if tick_duration_seconds > backward_wave_travel_time_seconds:
        reasons.append("tick_exceeds_backward_wave_travel_time")
    return TimestepAdmissibilityReport(
        link_id=link_id,
        tick_duration_seconds=tick_duration_seconds,
        free_flow_travel_time_seconds=free_flow_travel_time_seconds,
        backward_wave_travel_time_seconds=backward_wave_travel_time_seconds,
        free_flow_lag_ticks=free_flow_lag_ticks,
        backward_wave_lag_ticks=backward_wave_lag_ticks,
        minimum_lag_ticks=minimum_lag_ticks,
        is_admissible=not reasons,
        ineligibility_reasons=tuple(reasons),
    )


def _validate_positive_float(field_name: str, value: float) -> None:
    if not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be numeric")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
