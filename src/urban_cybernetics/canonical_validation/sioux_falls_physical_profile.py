# SPDX-License-Identifier: MPL-2.0
"""Engineering-assumption physical profiles for Sioux Falls parity runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from math import floor
from statistics import mean
from typing import Any

from urban_cybernetics.core import Link
from urban_cybernetics.topology import CanonicalTopologyLink, load_sioux_falls_topology
from urban_cybernetics.topology.canonical import CanonicalTopology


SIOUX_FALLS_UC_DEFAULT_PROFILE_ID = "SiouxFallsPhysicalProfile_UC_Default_v1"
SIOUX_FALLS_UC_DEFAULT_PROFILE_VERSION = "v1"
SIOUX_FALLS_UC_DEFAULT_GENERATED_AT_UTC = "2026-06-28T00:00:00Z"
SIOUX_FALLS_UC_DEFAULT_BACKWARD_WAVE_SPEED_MPS = 5.0
ENGINEERING_ASSUMPTION_NOT_CALIBRATION = (
    "engineering_assumption_profile_not_empirical_calibration"
)
JAM_DENSITY_EQUATION = "kj = q(v + w) / (v * w)"
STORAGE_CAPACITY_EQUATION = "storage = floor(length_km * lane_count * kj)"


@dataclass(frozen=True, slots=True)
class SiouxFallsProfileAssumption:
    """One declared profile-level assumption."""

    field_name: str
    value: str
    provenance_label: str
    note: str


@dataclass(frozen=True, slots=True)
class SiouxFallsDerivedLinkParameters:
    """Per-link physical parameters derived by a Sioux Falls profile."""

    link_id: str
    source_link_id: str
    length_m: float
    lane_count: int
    free_flow_speed_mps: float
    capacity_veh_per_hour_per_lane: float
    backward_wave_speed_mps: float
    jam_density_veh_per_km_per_lane: float
    declared_storage_capacity_packets: int

    def hash_payload(self) -> dict[str, Any]:
        """Return deterministic content used for the profile hash."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class SiouxFallsPhysicalProfileSummary:
    """Reader-facing statistics for a generated physical profile."""

    link_count: int
    backward_wave_speed_mps: float
    min_jam_density_veh_per_km_per_lane: float
    mean_jam_density_veh_per_km_per_lane: float
    max_jam_density_veh_per_km_per_lane: float
    min_storage_capacity_packets: int
    mean_storage_capacity_packets: float
    max_storage_capacity_packets: int
    min_capacity_veh_per_hour_per_lane: float
    mean_capacity_veh_per_hour_per_lane: float
    max_capacity_veh_per_hour_per_lane: float


@dataclass(frozen=True, slots=True)
class SiouxFallsPhysicalProfile:
    """Versioned Sioux Falls physical profile that owns assumptions."""

    profile_id: str
    version: str
    generated_at_utc: str
    topology_id: str
    topology_hash: str
    source_file_sha256: str
    statement: str
    assumptions: tuple[SiouxFallsProfileAssumption, ...]
    derivation_equations: tuple[str, ...]
    derived_fields: tuple[str, ...]
    derived_links: tuple[SiouxFallsDerivedLinkParameters, ...]
    profile_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "assumptions", tuple(self.assumptions))
        object.__setattr__(self, "derivation_equations", tuple(self.derivation_equations))
        object.__setattr__(self, "derived_fields", tuple(self.derived_fields))
        object.__setattr__(self, "derived_links", tuple(self.derived_links))
        object.__setattr__(self, "profile_hash", self.compute_hash())

    def compute_hash(self) -> str:
        """Return a stable hash for reproducibility checks."""

        serialised = json.dumps(
            self.hash_payload(),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialised.encode("utf-8")).hexdigest()

    def hash_payload(self) -> dict[str, Any]:
        """Return deterministic profile content, excluding the hash itself."""

        return {
            "profile_id": self.profile_id,
            "version": self.version,
            "generated_at_utc": self.generated_at_utc,
            "topology_id": self.topology_id,
            "topology_hash": self.topology_hash,
            "source_file_sha256": self.source_file_sha256,
            "statement": self.statement,
            "assumptions": [asdict(assumption) for assumption in self.assumptions],
            "derivation_equations": list(self.derivation_equations),
            "derived_fields": list(self.derived_fields),
            "derived_links": [
                derived_link.hash_payload()
                for derived_link in sorted(
                    self.derived_links,
                    key=lambda item: item.link_id,
                )
            ],
        }

    def status_payload(self) -> dict[str, Any]:
        """Return a JSON-ready payload including the profile hash."""

        payload = self.hash_payload()
        payload["profile_hash"] = self.profile_hash
        payload["summary"] = asdict(self.summary())
        return payload

    def summary(self) -> SiouxFallsPhysicalProfileSummary:
        """Return basic statistics over derived physical fields."""

        jam_densities = [
            link.jam_density_veh_per_km_per_lane for link in self.derived_links
        ]
        storage_capacities = [
            link.declared_storage_capacity_packets for link in self.derived_links
        ]
        capacities = [
            link.capacity_veh_per_hour_per_lane for link in self.derived_links
        ]
        return SiouxFallsPhysicalProfileSummary(
            link_count=len(self.derived_links),
            backward_wave_speed_mps=SIOUX_FALLS_UC_DEFAULT_BACKWARD_WAVE_SPEED_MPS,
            min_jam_density_veh_per_km_per_lane=min(jam_densities),
            mean_jam_density_veh_per_km_per_lane=mean(jam_densities),
            max_jam_density_veh_per_km_per_lane=max(jam_densities),
            min_storage_capacity_packets=min(storage_capacities),
            mean_storage_capacity_packets=mean(storage_capacities),
            max_storage_capacity_packets=max(storage_capacities),
            min_capacity_veh_per_hour_per_lane=min(capacities),
            mean_capacity_veh_per_hour_per_lane=mean(capacities),
            max_capacity_veh_per_hour_per_lane=max(capacities),
        )

    def as_loading_links(self, *, tick_duration_seconds: float = 60.0) -> dict[str, Link]:
        """Return parity-ready loading links without mutating topology."""

        return {
            link.link_id: Link(
                link_id=link.link_id,
                declared_sending_capacity_per_tick=max(
                    1,
                    int(
                        link.capacity_veh_per_hour_per_lane
                        * link.lane_count
                        * tick_duration_seconds
                        / 3600.0
                    ),
                ),
                declared_receiving_capacity_per_tick=max(
                    1,
                    int(
                        link.capacity_veh_per_hour_per_lane
                        * link.lane_count
                        * tick_duration_seconds
                        / 3600.0
                    ),
                ),
                declared_storage_capacity_packets=(
                    link.declared_storage_capacity_packets
                ),
                length_m=link.length_m,
                lane_count=link.lane_count,
                free_flow_speed_mps=link.free_flow_speed_mps,
                jam_density_veh_per_km_per_lane=(
                    link.jam_density_veh_per_km_per_lane
                ),
                backward_wave_speed_mps=link.backward_wave_speed_mps,
                capacity_veh_per_hour_per_lane=(
                    link.capacity_veh_per_hour_per_lane
                ),
                tick_duration_seconds=tick_duration_seconds,
            )
            for link in self.derived_links
        }

    def parity_capacity_rates_by_link(
        self,
        *,
        tick_duration_seconds: float = 60.0,
    ) -> dict[str, float]:
        """Return lane-aware physical capacity rates in vehicles per tick."""

        return {
            link.link_id: (
                link.capacity_veh_per_hour_per_lane
                * link.lane_count
                * tick_duration_seconds
                / 3600.0
            )
            for link in self.derived_links
        }


def build_sioux_falls_uc_default_physical_profile(
    *,
    topology: CanonicalTopology | None = None,
    generated_at_utc: str = SIOUX_FALLS_UC_DEFAULT_GENERATED_AT_UTC,
) -> SiouxFallsPhysicalProfile:
    """Build the first UC engineering-assumption Sioux Falls physical profile."""

    resolved_topology = topology or load_sioux_falls_topology()
    derived_links = tuple(
        _derive_link_parameters(link) for link in resolved_topology.links
    )
    return SiouxFallsPhysicalProfile(
        profile_id=SIOUX_FALLS_UC_DEFAULT_PROFILE_ID,
        version=SIOUX_FALLS_UC_DEFAULT_PROFILE_VERSION,
        generated_at_utc=generated_at_utc,
        topology_id=resolved_topology.topology_id,
        topology_hash=resolved_topology.topology_hash,
        source_file_sha256=resolved_topology.source_metadata.source_file_sha256,
        statement=(
            "This is a reproducible UC engineering-assumption physical profile. "
            "It is not empirical calibration and does not assert true Sioux "
            "Falls physical parameters."
        ),
        assumptions=_profile_assumptions(),
        derivation_equations=(
            JAM_DENSITY_EQUATION,
            STORAGE_CAPACITY_EQUATION,
        ),
        derived_fields=(
            "backward_wave_speed_mps",
            "jam_density_veh_per_km_per_lane",
            "declared_storage_capacity_packets",
        ),
        derived_links=derived_links,
    )


def derive_jam_density_veh_per_km_per_lane(
    *,
    capacity_veh_per_hour_per_lane: float,
    free_flow_speed_mps: float,
    backward_wave_speed_mps: float,
) -> float:
    """Derive triangular-FD jam density from capacity and wave speeds."""

    _require_positive("capacity_veh_per_hour_per_lane", capacity_veh_per_hour_per_lane)
    _require_positive("free_flow_speed_mps", free_flow_speed_mps)
    _require_positive("backward_wave_speed_mps", backward_wave_speed_mps)
    return (
        capacity_veh_per_hour_per_lane
        * (free_flow_speed_mps + backward_wave_speed_mps)
        / (3600.0 * free_flow_speed_mps * backward_wave_speed_mps)
        * 1000.0
    )


def derive_storage_capacity_packets(
    *,
    length_m: float,
    lane_count: int,
    jam_density_veh_per_km_per_lane: float,
) -> int:
    """Derive integer packet storage from length, lanes, and jam density."""

    _require_positive("length_m", length_m)
    if lane_count <= 0:
        raise ValueError("lane_count must be positive")
    _require_positive("jam_density_veh_per_km_per_lane", jam_density_veh_per_km_per_lane)
    return max(
        1,
        floor((length_m / 1000.0) * lane_count * jam_density_veh_per_km_per_lane),
    )


def _derive_link_parameters(
    link: CanonicalTopologyLink,
) -> SiouxFallsDerivedLinkParameters:
    required = {
        "length_m": link.length_m,
        "lane_count": link.lane_count,
        "free_flow_speed_mps": link.free_flow_speed_mps,
        "capacity_veh_per_hour_per_lane": link.capacity_veh_per_hour_per_lane,
    }
    missing = tuple(name for name, value in required.items() if value is None)
    if missing:
        raise ValueError(f"{link.link_id} missing source fields: {missing}")
    assert link.length_m is not None
    assert link.lane_count is not None
    assert link.free_flow_speed_mps is not None
    assert link.capacity_veh_per_hour_per_lane is not None

    jam_density = derive_jam_density_veh_per_km_per_lane(
        capacity_veh_per_hour_per_lane=link.capacity_veh_per_hour_per_lane,
        free_flow_speed_mps=link.free_flow_speed_mps,
        backward_wave_speed_mps=SIOUX_FALLS_UC_DEFAULT_BACKWARD_WAVE_SPEED_MPS,
    )
    storage_capacity = derive_storage_capacity_packets(
        length_m=link.length_m,
        lane_count=link.lane_count,
        jam_density_veh_per_km_per_lane=jam_density,
    )
    return SiouxFallsDerivedLinkParameters(
        link_id=link.link_id,
        source_link_id=link.source_link_id,
        length_m=link.length_m,
        lane_count=link.lane_count,
        free_flow_speed_mps=link.free_flow_speed_mps,
        capacity_veh_per_hour_per_lane=link.capacity_veh_per_hour_per_lane,
        backward_wave_speed_mps=SIOUX_FALLS_UC_DEFAULT_BACKWARD_WAVE_SPEED_MPS,
        jam_density_veh_per_km_per_lane=jam_density,
        declared_storage_capacity_packets=storage_capacity,
    )


def _profile_assumptions() -> tuple[SiouxFallsProfileAssumption, ...]:
    return (
        SiouxFallsProfileAssumption(
            field_name="topology",
            value="published_sioux_falls_tntp_v1",
            provenance_label="source_retained",
            note="Published Sioux Falls TNTP topology, free-flow times, lengths, and capacities are retained.",
        ),
        SiouxFallsProfileAssumption(
            field_name="lane_count",
            value="1",
            provenance_label="topology_interpretation_assumption",
            note="The current canonical Sioux Falls loader fixes lane count at one because the TNTP source does not provide lanes.",
        ),
        SiouxFallsProfileAssumption(
            field_name="backward_wave_speed_mps",
            value=f"{SIOUX_FALLS_UC_DEFAULT_BACKWARD_WAVE_SPEED_MPS}",
            provenance_label=ENGINEERING_ASSUMPTION_NOT_CALIBRATION,
            note="Global engineering assumption used only to exercise the parity kernel.",
        ),
        SiouxFallsProfileAssumption(
            field_name="jam_density_veh_per_km_per_lane",
            value="derived_per_link",
            provenance_label=ENGINEERING_ASSUMPTION_NOT_CALIBRATION,
            note="Derived from each link's published capacity and free-flow speed plus the global backward-wave-speed assumption.",
        ),
        SiouxFallsProfileAssumption(
            field_name="declared_storage_capacity_packets",
            value="derived_per_link",
            provenance_label="derived_not_manual_storage",
            note="Derived from length, lane count, and jam density; no manual storage values are specified.",
        ),
    )


def _require_positive(field_name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
