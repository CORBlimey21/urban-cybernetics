# SPDX-License-Identifier: MPL-2.0
"""Declared V2 simulation resource catalogue and strict resolver."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from urban_cybernetics.canonical_validation import build_sioux_falls_uc_default_physical_profile
from urban_cybernetics.demand import load_sioux_falls_demand_manifest
from urban_cybernetics.topology import CanonicalTopology, load_sioux_falls_topology

from .fixtures import build_synthetic_topology
from .v2_contract import (
    CatalogueParameter,
    CatalogueResource,
    ResourceCatalogue,
    ResourceClassification,
    ResourceKind,
    RunRequestV2,
)


SYNTHETIC_TOPOLOGY_ID = "uc_synthetic_diverge_v1"
SYNTHETIC_PROFILE_ID = "UCSyntheticPhysicalProfile_v1"
SYNTHETIC_DEMAND_ID = "uc_synthetic_alternating_demand_v1"
SIOUX_TOPOLOGY_ID = "sioux_falls_tntp_v1"
SIOUX_PROFILE_ID = "SiouxFallsPhysicalProfile_UC_Default_v1"
SIOUX_DEMAND_ID = "sioux_falls_canonical_od_v1"


class ResourceResolutionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedResources:
    topology: CanonicalTopology
    topology_hash: str
    profile_hash: str
    demand_hash: str
    tick_duration_seconds: float
    assumption_warnings: tuple[str, ...]


def build_resource_catalogue() -> ResourceCatalogue:
    packet_count = CatalogueParameter(
        parameter_id="requested_packet_count", name="Packet count",
        description="Maximum number of canonical demand declarations selected.",
        units="unit packets", default=24, minimum=1, maximum=1000,
    )
    resources = (
        CatalogueResource(resource_id=SYNTHETIC_TOPOLOGY_ID, kind=ResourceKind.TOPOLOGY, name="UC deterministic diverge", description="Five-node deterministic inspection topology.", provenance="Declared V1 acceptance fixture.", classification=ResourceClassification.SYNTHETIC),
        CatalogueResource(resource_id=SIOUX_TOPOLOGY_ID, kind=ResourceKind.TOPOLOGY, name="Sioux Falls TNTP", description="Canonical directed topology loaded from TNTP benchmark evidence.", provenance="Transportation Networks for Research Core Team TNTP source.", classification=ResourceClassification.CANONICAL_SOURCE, warnings=("Diagram coordinates are non-geographic.",)),
        CatalogueResource(resource_id=SYNTHETIC_PROFILE_ID, kind=ResourceKind.PHYSICAL_PROFILE, name="Synthetic unit profile", description="One-second illustrative unit-packet loading parameters.", provenance="UC deterministic fixture declaration.", classification=ResourceClassification.SYNTHETIC, compatible_topology_ids=(SYNTHETIC_TOPOLOGY_ID,)),
        CatalogueResource(resource_id=SIOUX_PROFILE_ID, kind=ResourceKind.PHYSICAL_PROFILE, name="Sioux Falls UC default assumption profile", description="Complete LTM parameterisation derived from TNTP fields plus declared UC assumptions.", provenance="UC assumption profile; not empirical calibration.", classification=ResourceClassification.ASSUMPTION, compatible_topology_ids=(SIOUX_TOPOLOGY_ID,), warnings=("Assumption-based physical profile; not empirically calibrated.",)),
        CatalogueResource(resource_id=SYNTHETIC_DEMAND_ID, kind=ResourceKind.DEMAND_SOURCE, name="Alternating synthetic demand", description="Deterministic declarations alternating over the two fixture routes.", provenance="UC V2 sanctioned synthetic demand generator.", classification=ResourceClassification.SYNTHETIC, parameters=(packet_count,), compatible_topology_ids=(SYNTHETIC_TOPOLOGY_ID,), compatible_profile_ids=(SYNTHETIC_PROFILE_ID,)),
        CatalogueResource(resource_id=SIOUX_DEMAND_ID, kind=ResourceKind.DEMAND_SOURCE, name="Sioux Falls canonical OD", description="Canonical-prefix selection from resolved Sioux Falls OD demand.", provenance="TNTP Sioux Falls trips source and UC canonical route resolution.", classification=ResourceClassification.CANONICAL_SOURCE, parameters=(packet_count,), compatible_topology_ids=(SIOUX_TOPOLOGY_ID,), compatible_profile_ids=(SIOUX_PROFILE_ID,)),
        CatalogueResource(resource_id="canonical_prefix_v1", kind=ResourceKind.PACKET_SELECTION, name="Canonical prefix", description="Select declarations in persisted canonical manifest order.", provenance="UC declared selection policy.", classification=ResourceClassification.CANONICAL_SOURCE),
        CatalogueResource(resource_id="synthetic_one_second_v1", kind=ResourceKind.TICK_POLICY, name="One-second fixture tick", description="Fixed one-second physical tick.", provenance="UC synthetic fixture.", classification=ResourceClassification.SYNTHETIC, compatible_topology_ids=(SYNTHETIC_TOPOLOGY_ID,)),
        CatalogueResource(resource_id="sioux_profile_default_v1", kind=ResourceKind.TICK_POLICY, name="Sioux profile default tick", description="Fixed 60-second physical tick used by the certified benchmark runner.", provenance="UC benchmark run policy.", classification=ResourceClassification.ASSUMPTION, compatible_topology_ids=(SIOUX_TOPOLOGY_ID,)),
        CatalogueResource(resource_id="all_instantiated_packets_terminal_v1", kind=ResourceKind.COMPLETION_POLICY, name="All packets terminal", description="Complete only after every instantiated packet is terminal.", provenance="UC loading lifecycle.", classification=ResourceClassification.CANONICAL_SOURCE),
        CatalogueResource(resource_id="bounded_tick_or_wall_time_v1", kind=ResourceKind.STOP_POLICY, name="Bounded tick or wall time", description="Stop at completion, tick bound, wall-time bound, or explicit cancellation.", provenance="UC V2 orchestrator.", classification=ResourceClassification.CANONICAL_SOURCE),
        CatalogueResource(resource_id="core_integrity_v1", kind=ResourceKind.VALIDATION_POLICY, name="Core integrity", description="Conservation, event/materialised cache, and Python replay integrity.", provenance="UC Python validation layer.", classification=ResourceClassification.CANONICAL_SOURCE),
        CatalogueResource(resource_id="exact_if_complete_v1", kind=ResourceKind.REPLAY_POLICY, name="Exact replay if complete", description="Run an exact Python rerun for completed bounded runs.", provenance="UC deterministic replay policy.", classification=ResourceClassification.CANONICAL_SOURCE),
        CatalogueResource(resource_id="retain_all_evidence_v1", kind=ResourceKind.PERSISTENCE_POLICY, name="Retain all evidence", description="Retain canonical chunks, sealed checkpoints, provenance, and partial terminal evidence.", provenance="UC V2 evidence plane.", classification=ResourceClassification.CANONICAL_SOURCE),
    )
    return ResourceCatalogue(resources=resources)


def resolve_resources(request: RunRequestV2) -> ResolvedResources:
    catalogue = build_resource_catalogue()
    ids = {resource.resource_id for resource in catalogue.resources}
    selected = (
        request.topology_id, request.physical_profile_id, request.demand_source_id,
        request.packet_selection_policy_id, request.tick_policy_id,
        request.completion_policy_id, request.stop_policy_id,
        request.validation_policy_id, request.replay_policy_id,
        request.persistence_policy_id,
    )
    missing = [resource_id for resource_id in selected if resource_id not in ids]
    if missing:
        raise ResourceResolutionError(f"unknown declared resource IDs: {', '.join(missing)}")
    profile = catalogue.by_id(request.physical_profile_id)
    demand = catalogue.by_id(request.demand_source_id)
    tick = catalogue.by_id(request.tick_policy_id)
    for resource in (profile, demand, tick):
        if resource.compatible_topology_ids and request.topology_id not in resource.compatible_topology_ids:
            raise ResourceResolutionError(f"{resource.resource_id} is incompatible with {request.topology_id}")
    if demand.compatible_profile_ids and request.physical_profile_id not in demand.compatible_profile_ids:
        raise ResourceResolutionError(f"{request.demand_source_id} is incompatible with {request.physical_profile_id}")

    if request.topology_id == SYNTHETIC_TOPOLOGY_ID:
        expected = (SYNTHETIC_PROFILE_ID, SYNTHETIC_DEMAND_ID, "synthetic_one_second_v1")
        if (request.physical_profile_id, request.demand_source_id, request.tick_policy_id) != expected:
            raise ResourceResolutionError("synthetic resources must be selected as a compatible set")
        topology = build_synthetic_topology()
        profile_hash = _hash({"id": SYNTHETIC_PROFILE_ID, "tick_seconds": 1.0, "capacity": 1, "storage": 8})
        demand_hash = _hash({"id": SYNTHETIC_DEMAND_ID, "count": request.requested_packet_count, "selection": request.packet_selection_policy_id, "seed": request.seed})
        duration = 1.0
        warnings = ("Synthetic parameters are illustrative and not empirical calibration.",)
    elif request.topology_id == SIOUX_TOPOLOGY_ID:
        expected = (SIOUX_PROFILE_ID, SIOUX_DEMAND_ID, "sioux_profile_default_v1")
        if (request.physical_profile_id, request.demand_source_id, request.tick_policy_id) != expected:
            raise ResourceResolutionError("Sioux Falls resources must be selected as a compatible set")
        topology = load_sioux_falls_topology()
        physical_profile = build_sioux_falls_uc_default_physical_profile(topology=topology)
        manifest = load_sioux_falls_demand_manifest(
            topology=topology,
            scale_factor=0.01,
            max_total_quantity_packets=request.requested_packet_count,
        )
        profile_hash = physical_profile.profile_hash
        demand_hash = manifest.manifest_hash
        duration = 60.0
        warnings = ("Physical profile is assumption-based and not empirically calibrated.", "TNTP diagram coordinates must not be interpreted as geography.")
    else:
        raise ResourceResolutionError("topology resolver is not declared")
    if request.requested_tick_duration_seconds is not None and request.requested_tick_duration_seconds != duration:
        raise ResourceResolutionError(f"requested tick duration must exactly equal declared policy value {duration}")
    return ResolvedResources(topology=topology, topology_hash=topology.topology_hash, profile_hash=profile_hash, demand_hash=demand_hash, tick_duration_seconds=duration, assumption_warnings=warnings)


def _hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()
