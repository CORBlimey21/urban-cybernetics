# SPDX-License-Identifier: MPL-2.0
"""Engineering-assumption physical profiles for Anaheim parity runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any

from urban_cybernetics.canonical_validation.sioux_falls_physical_profile import (
    ENGINEERING_ASSUMPTION_NOT_CALIBRATION,
    JAM_DENSITY_EQUATION,
    STORAGE_CAPACITY_EQUATION,
    derive_jam_density_veh_per_km_per_lane,
    derive_storage_capacity_packets,
)
from urban_cybernetics.core import Link
from urban_cybernetics.topology.anaheim import load_anaheim_topology
from urban_cybernetics.topology.canonical import CanonicalTopology, CanonicalTopologyLink


ANAHEIM_UC_DEFAULT_PROFILE_ID = "AnaheimPhysicalProfile_UC_Default_v1"
ANAHEIM_UC_DEFAULT_PROFILE_VERSION = "v1"
ANAHEIM_UC_DEFAULT_GENERATED_AT_UTC = "2026-07-03T00:00:00Z"
ANAHEIM_UC_DEFAULT_BACKWARD_WAVE_SPEED_MPS = 5.0


@dataclass(frozen=True, slots=True)
class AnaheimProfileAssumption:
    """One declared Anaheim profile-level assumption."""

    field_name: str
    value: str
    provenance_label: str
    note: str


@dataclass(frozen=True, slots=True)
class AnaheimDerivedLinkParameters:
    """Per-link physical parameters derived by the Anaheim profile."""

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
class AnaheimPhysicalProfileSummary:
    """Reader-facing statistics for a generated Anaheim physical profile."""

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
class AnaheimPhysicalProfile:
    """Versioned Anaheim physical profile that owns assumptions."""

    profile_id: str
    version: str
    generated_at_utc: str
    topology_id: str
    topology_hash: str
    source_file_sha256: str
    statement: str
    assumptions: tuple[AnaheimProfileAssumption, ...]
    derivation_equations: tuple[str, ...]
    derived_fields: tuple[str, ...]
    derived_links: tuple[AnaheimDerivedLinkParameters, ...]
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

    def summary(self) -> AnaheimPhysicalProfileSummary:
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
        return AnaheimPhysicalProfileSummary(
            link_count=len(self.derived_links),
            backward_wave_speed_mps=ANAHEIM_UC_DEFAULT_BACKWARD_WAVE_SPEED_MPS,
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


def build_anaheim_uc_default_physical_profile(
    *,
    topology: CanonicalTopology | None = None,
    generated_at_utc: str = ANAHEIM_UC_DEFAULT_GENERATED_AT_UTC,
) -> AnaheimPhysicalProfile:
    """Build the first UC engineering-assumption Anaheim physical profile."""

    resolved_topology = topology or load_anaheim_topology()
    derived_links = tuple(
        _derive_link_parameters(link) for link in resolved_topology.links
    )
    return AnaheimPhysicalProfile(
        profile_id=ANAHEIM_UC_DEFAULT_PROFILE_ID,
        version=ANAHEIM_UC_DEFAULT_PROFILE_VERSION,
        generated_at_utc=generated_at_utc,
        topology_id=resolved_topology.topology_id,
        topology_hash=resolved_topology.topology_hash,
        source_file_sha256=resolved_topology.source_metadata.source_file_sha256,
        statement=(
            "This is a reproducible UC engineering-assumption physical profile. "
            "It is not empirical calibration and does not assert true Anaheim "
            "physical parameters."
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


def _derive_link_parameters(
    link: CanonicalTopologyLink,
) -> AnaheimDerivedLinkParameters:
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
        backward_wave_speed_mps=ANAHEIM_UC_DEFAULT_BACKWARD_WAVE_SPEED_MPS,
    )
    storage_capacity = derive_storage_capacity_packets(
        length_m=link.length_m,
        lane_count=link.lane_count,
        jam_density_veh_per_km_per_lane=jam_density,
    )
    return AnaheimDerivedLinkParameters(
        link_id=link.link_id,
        source_link_id=link.source_link_id,
        length_m=link.length_m,
        lane_count=link.lane_count,
        free_flow_speed_mps=link.free_flow_speed_mps,
        capacity_veh_per_hour_per_lane=link.capacity_veh_per_hour_per_lane,
        backward_wave_speed_mps=ANAHEIM_UC_DEFAULT_BACKWARD_WAVE_SPEED_MPS,
        jam_density_veh_per_km_per_lane=jam_density,
        declared_storage_capacity_packets=storage_capacity,
    )


def _profile_assumptions() -> tuple[AnaheimProfileAssumption, ...]:
    return (
        AnaheimProfileAssumption(
            field_name="topology",
            value="published_anaheim_tntp_v1",
            provenance_label="source_retained",
            note="Published Anaheim TNTP topology, free-flow times, lengths, speeds, and capacities are retained.",
        ),
        AnaheimProfileAssumption(
            field_name="length_unit",
            value="foot",
            provenance_label="source_header_retained",
            note="The Anaheim source header labels network length values as feet.",
        ),
        AnaheimProfileAssumption(
            field_name="lane_count",
            value="1",
            provenance_label="topology_interpretation_assumption",
            note="The current canonical Anaheim loader fixes lane count at one because the TNTP source does not provide lanes.",
        ),
        AnaheimProfileAssumption(
            field_name="backward_wave_speed_mps",
            value=f"{ANAHEIM_UC_DEFAULT_BACKWARD_WAVE_SPEED_MPS}",
            provenance_label=ENGINEERING_ASSUMPTION_NOT_CALIBRATION,
            note="Global engineering assumption used only to exercise the parity kernel.",
        ),
        AnaheimProfileAssumption(
            field_name="jam_density_veh_per_km_per_lane",
            value="derived_per_link",
            provenance_label=ENGINEERING_ASSUMPTION_NOT_CALIBRATION,
            note="Derived from each link's published capacity and free-flow speed plus the global backward-wave-speed assumption.",
        ),
        AnaheimProfileAssumption(
            field_name="declared_storage_capacity_packets",
            value="derived_per_link",
            provenance_label="derived_not_manual_storage",
            note="Derived from length, lane count, and jam density; no manual storage values are specified.",
        ),
    )
