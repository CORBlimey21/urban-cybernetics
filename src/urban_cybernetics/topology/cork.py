"""Deterministic city-scale adapter for the pinned Cork OSMnx GraphML.

This is deliberately an engineered adapter, not the provenance-aware OSM
compiler.  It preserves the source multigraph one node/edge at a time while
binding the explicit Paper 1 engineering assumptions needed by the packet LTM.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from math import ceil, floor
from pathlib import Path
from typing import Any, Mapping

import networkx as nx

from urban_cybernetics.canonical_validation.sioux_falls_physical_profile import (
    derive_jam_density_veh_per_km_per_lane,
)
from urban_cybernetics.config import DEFAULT_SPEED_KPH_BY_HIGHWAY, FALLBACK_SPEED_KPH
from urban_cybernetics.core import Link
from urban_cybernetics.topology.canonical import (
    CanonicalNode,
    CanonicalTopology,
    CanonicalTopologyLink,
    TopologySourceMetadata,
)


CORK_GRAPH_ENVIRONMENT_VARIABLE = "UC_CORK_GRAPHML"
CORK_DEFAULT_GRAPH_PATH = Path("external/pinned/cork_full_drive.graphml")
CORK_GRAPH_SHA256 = "cc904d3c9107136fdf6fd24318c19c38958b63dc81c83441e8e5f855f41f5409"
CORK_EXPECTED_NODE_COUNT = 5_891
CORK_EXPECTED_EDGE_COUNT = 13_111
CORK_EXPECTED_OSMNX_VERSION = "2.0.2"
CORK_TICK_DURATION_SECONDS = 0.04
CORK_BACKWARD_WAVE_SPEED_MPS = 5.0
CORK_PROFILE_ID = "CorkPhysicalProfile_UC_RoadClass_v1"
CORK_PROFILE_VERSION = "v1"
CORK_ADAPTER_VERSION = "uc.cork-osmnx-canonical-adapter.v1"
CORK_SPEED_POLICY_VERSION = "uc.cork-road-class-speed-policy.v1"
CORK_CAPACITY_POLICY_VERSION = "uc.cork-road-class-capacity-policy.v1"
CORK_LANE_POLICY_VERSION = "uc.cork-directional-lane-policy.v1"

# Executable free-flow speeds are the existing repository road-class values.
CORK_SPEED_KPH_BY_HIGHWAY = tuple(sorted(DEFAULT_SPEED_KPH_BY_HIGHWAY.items()))

# Explicit uncalibrated per-lane engineering capacities.  These extend the
# repository compiler priors mechanically across matching *_link classes.
CORK_CAPACITY_PER_LANE_BY_HIGHWAY = tuple(
    sorted(
        {
            "motorway": 1_800.0,
            "motorway_link": 1_800.0,
            "trunk": 1_800.0,
            "trunk_link": 1_800.0,
            "primary": 1_800.0,
            "primary_link": 1_800.0,
            "secondary": 1_500.0,
            "secondary_link": 1_500.0,
            "tertiary": 1_500.0,
            "tertiary_link": 1_500.0,
            "residential": 1_200.0,
            "unclassified": 1_200.0,
            "living_street": 900.0,
            "service": 900.0,
        }.items()
    )
)

_HIGHWAY_PRECEDENCE = (
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "unclassified",
    "residential",
    "living_street",
    "service",
)
_PROVENANCE_EDGE_FIELDS = (
    "osmid",
    "geometry",
    "highway",
    "name",
    "ref",
    "lanes",
    "maxspeed",
    "oneway",
    "junction",
    "access",
    "bridge",
    "tunnel",
    "reversed",
    "width",
)
_PROVENANCE_NODE_FIELDS = (
    "x",
    "y",
    "street_count",
    "highway",
    "junction",
    "traffic_signals",
    "crossing",
)


@dataclass(frozen=True, slots=True)
class CorkSourceNode:
    canonical_node_id: str
    source_node_id: str
    source_metadata_items: tuple[tuple[str, str], ...]

    def payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CorkSourceEdge:
    canonical_link_id: str
    source_u: str
    source_v: str
    source_key: str
    geometry_sha256: str | None
    source_metadata_items: tuple[tuple[str, str], ...]

    def payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CorkPhysicalLink:
    link_id: str
    road_class: str
    length_m: float
    lane_count: int
    free_flow_speed_mps: float
    capacity_veh_per_hour_per_lane: float
    backward_wave_speed_mps: float
    jam_density_veh_per_km_per_lane: float
    storage_capacity_packets: int
    free_flow_travel_time_seconds: float
    free_flow_lag_ticks: int
    backward_wave_lag_ticks: int

    def payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CorkCanonicalNetwork:
    topology: CanonicalTopology
    source_nodes: tuple[CorkSourceNode, ...]
    source_edges: tuple[CorkSourceEdge, ...]
    physical_links: tuple[CorkPhysicalLink, ...]
    source_provenance_hash: str
    physical_profile_hash: str
    largest_scc_node_ids: tuple[str, ...]

    @property
    def topology_hash(self) -> str:
        return self.topology.topology_hash

    def as_loading_links(self) -> dict[str, Link]:
        return {
            item.link_id: Link(
                link_id=item.link_id,
                declared_sending_capacity_per_tick=max(
                    1,
                    floor(
                        item.capacity_veh_per_hour_per_lane
                        * item.lane_count
                        * CORK_TICK_DURATION_SECONDS
                        / 3600.0
                    ),
                ),
                declared_receiving_capacity_per_tick=max(
                    1,
                    floor(
                        item.capacity_veh_per_hour_per_lane
                        * item.lane_count
                        * CORK_TICK_DURATION_SECONDS
                        / 3600.0
                    ),
                ),
                declared_storage_capacity_packets=item.storage_capacity_packets,
                length_m=item.length_m,
                lane_count=item.lane_count,
                free_flow_speed_mps=item.free_flow_speed_mps,
                jam_density_veh_per_km_per_lane=item.jam_density_veh_per_km_per_lane,
                backward_wave_speed_mps=item.backward_wave_speed_mps,
                capacity_veh_per_hour_per_lane=item.capacity_veh_per_hour_per_lane,
                tick_duration_seconds=CORK_TICK_DURATION_SECONDS,
            )
            for item in self.physical_links
        }

    def capacity_rates_by_link(self) -> dict[str, float]:
        return {
            item.link_id: (
                item.capacity_veh_per_hour_per_lane
                * item.lane_count
                * CORK_TICK_DURATION_SECONDS
                / 3600.0
            )
            for item in self.physical_links
        }

    def status_payload(self) -> dict[str, object]:
        return {
            "adapter_version": CORK_ADAPTER_VERSION,
            "topology_id": self.topology.topology_id,
            "topology_hash": self.topology_hash,
            "physical_profile_id": CORK_PROFILE_ID,
            "physical_profile_version": CORK_PROFILE_VERSION,
            "physical_profile_hash": self.physical_profile_hash,
            "source_provenance_hash": self.source_provenance_hash,
            "source_file_sha256": self.topology.source_metadata.source_file_sha256,
            "node_count": len(self.topology.nodes),
            "directed_edge_count": len(self.topology.links),
            "largest_scc_node_count": len(self.largest_scc_node_ids),
            "tick_duration_seconds": CORK_TICK_DURATION_SECONDS,
            "speed_policy_version": CORK_SPEED_POLICY_VERSION,
            "capacity_policy_version": CORK_CAPACITY_POLICY_VERSION,
            "lane_policy_version": CORK_LANE_POLICY_VERSION,
            "backward_wave_speed_mps": CORK_BACKWARD_WAVE_SPEED_MPS,
            "speed_kph_by_highway": [list(item) for item in CORK_SPEED_KPH_BY_HIGHWAY],
            "fallback_speed_kph": FALLBACK_SPEED_KPH,
            "capacity_per_lane_by_highway": [
                list(item) for item in CORK_CAPACITY_PER_LANE_BY_HIGHWAY
            ],
            "fallback_capacity_veh_per_hour_per_lane": 900.0,
            "lane_policy": (
                "parse observed lanes; select maximum when simplified-edge source "
                "values conflict; halve total lanes with ceil for non-oneway edges; "
                "default missing lanes to one directional lane"
            ),
            "jam_density_equation": "kj = q(v + w) / (v * w)",
            "storage_equation": "max(1, floor(length_km * lanes * kj))",
            "claim_boundary": "uncalibrated_city_scale_engineering_experiment",
        }


def canonical_cork_node_id(source_node_id: object) -> str:
    return f"osm-node:{source_node_id}"


def canonical_cork_link_id(u: object, v: object, key: object) -> str:
    # Canonical boundary IDs use ``->`` as their own delimiter, so link IDs
    # must encode the source tuple without that reserved token.
    return f"osm-link:u={u}:v={v}:key={key}"


def load_cork_canonical_network(
    path: Path | None = None,
) -> CorkCanonicalNetwork:
    """Load, preserve, physicalise, and strictly validate the pinned graph."""

    path = resolve_cork_graph_path(path)
    source_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if source_sha != CORK_GRAPH_SHA256:
        raise ValueError(f"Cork GraphML SHA-256 mismatch: {source_sha}")
    graph = nx.read_graphml(path, node_type=int, force_multigraph=True)
    if not isinstance(graph, nx.MultiDiGraph):
        raise TypeError("Cork source must load as a directed multigraph")
    if len(graph) != CORK_EXPECTED_NODE_COUNT or graph.number_of_edges() != CORK_EXPECTED_EDGE_COUNT:
        raise ValueError("Cork GraphML node/edge identity mismatch")
    created_with = str(graph.graph.get("created_with", ""))
    if created_with != f"OSMnx {CORK_EXPECTED_OSMNX_VERSION}":
        raise ValueError(f"unexpected Cork GraphML creator: {created_with}")

    source_nodes = tuple(
        CorkSourceNode(
            canonical_node_id=canonical_cork_node_id(node_id),
            source_node_id=str(node_id),
            source_metadata_items=_metadata_items(data, _PROVENANCE_NODE_FIELDS),
        )
        for node_id, data in sorted(graph.nodes(data=True), key=lambda item: item[0])
    )
    edge_rows = sorted(
        graph.edges(keys=True, data=True),
        key=lambda item: (item[0], item[1], _sort_key(item[2])),
    )
    source_edges: list[CorkSourceEdge] = []
    physical_links: list[CorkPhysicalLink] = []
    canonical_links: list[CanonicalTopologyLink] = []
    for u, v, key, data in edge_rows:
        link_id = canonical_cork_link_id(u, v, key)
        geometry = data.get("geometry")
        geometry_hash = (
            hashlib.sha256(str(geometry).encode("utf-8")).hexdigest()
            if geometry is not None
            else None
        )
        metadata = _metadata_items(data, _PROVENANCE_EDGE_FIELDS)
        if geometry_hash is not None:
            metadata = tuple(sorted((*metadata, ("geometry_sha256", geometry_hash))))
        source_edges.append(
            CorkSourceEdge(link_id, str(u), str(v), str(key), geometry_hash, metadata)
        )
        physical = _physical_link(link_id, data)
        physical_links.append(physical)
        canonical_links.append(
            CanonicalTopologyLink(
                link_id=link_id,
                tail_node_id=canonical_cork_node_id(u),
                head_node_id=canonical_cork_node_id(v),
                source_link_id=f"({u},{v},{key})",
                source_tail_node_id=str(u),
                source_head_node_id=str(v),
                length_m=physical.length_m,
                lane_count=physical.lane_count,
                free_flow_speed_mps=physical.free_flow_speed_mps,
                capacity_veh_per_hour_per_lane=physical.capacity_veh_per_hour_per_lane,
                jam_density_veh_per_km_per_lane=physical.jam_density_veh_per_km_per_lane,
                backward_wave_speed_mps=physical.backward_wave_speed_mps,
                source_length_value=physical.length_m,
                source_length_unit="metre",
                source_free_flow_time_value=None,
                source_free_flow_time_unit=None,
                source_capacity_value=None,
                source_capacity_unit=None,
            )
        )

    provenance_payload = {
        "nodes": [item.payload() for item in source_nodes],
        "edges": [item.payload() for item in source_edges],
    }
    provenance_hash = _stable_hash("cork-source-provenance", provenance_payload)
    incoming: dict[str, list[str]] = {
        canonical_cork_node_id(node_id): [] for node_id in graph.nodes
    }
    outgoing = {node_id: [] for node_id in incoming}
    for link in canonical_links:
        outgoing[link.tail_node_id].append(link.link_id)
        incoming[link.head_node_id].append(link.link_id)
    nodes = tuple(
        CanonicalNode(
            node_id=item.canonical_node_id,
            source_node_id=item.source_node_id,
            incoming_link_ids=tuple(sorted(incoming[item.canonical_node_id])),
            outgoing_link_ids=tuple(sorted(outgoing[item.canonical_node_id])),
            fifo_policy="strict",
        )
        for item in source_nodes
    )
    source_metadata = TopologySourceMetadata.from_path(
        source_name="pinned_cork_full_drive_osmnx_2_0_2",
        source_format="OSMnx GraphML MultiDiGraph",
        source_file_path=path,
        source_metadata_items=(
            ("adapter_version", CORK_ADAPTER_VERSION),
            ("created_with", created_with),
            ("crs", str(graph.graph.get("crs", ""))),
            ("simplified", str(graph.graph.get("simplified", ""))),
        ),
    )
    topology = CanonicalTopology(
        topology_id="cork-full-drive-pinned-v1",
        nodes=nodes,
        links=tuple(canonical_links),
        source_metadata=source_metadata,
        interpretation_assumptions=(
            f"source_file_sha256:{source_sha}",
            f"source_provenance_hash:{provenance_hash}",
            f"speed_policy:{CORK_SPEED_POLICY_VERSION}",
            f"lane_policy:{CORK_LANE_POLICY_VERSION}",
            f"capacity_policy:{CORK_CAPACITY_POLICY_VERSION}",
            "no_node_or_edge_contraction",
            "parallel_edges_preserved_by_source_u_v_key",
            "default_unsignalised_equal_priority_shared_strict_fifo",
            "not_calibrated_cork_operations",
        ),
    )
    physical_payload = {
        "profile_id": CORK_PROFILE_ID,
        "version": CORK_PROFILE_VERSION,
        "topology_hash": topology.topology_hash,
        "tick_duration_seconds": CORK_TICK_DURATION_SECONDS,
        "backward_wave_speed_mps": CORK_BACKWARD_WAVE_SPEED_MPS,
        "speed_policy": list(CORK_SPEED_KPH_BY_HIGHWAY),
        "capacity_policy": list(CORK_CAPACITY_PER_LANE_BY_HIGHWAY),
        "lane_policy_version": CORK_LANE_POLICY_VERSION,
        "links": [item.payload() for item in physical_links],
    }
    physical_hash = _stable_hash("cork-physical-profile", physical_payload)
    loading_links = {
        item.link_id: _loading_link(item) for item in physical_links
    }
    inadmissible = tuple(
        (link_id, link.resolved_physical_parameters().ineligibility_reasons)
        for link_id, link in loading_links.items()
        if not link.resolved_physical_parameters().parity_eligible
    )
    if inadmissible:
        raise ValueError(f"Cork physical/timestep eligibility failed: {inadmissible[:10]}")

    largest_scc = max(nx.strongly_connected_components(graph), key=len)
    return CorkCanonicalNetwork(
        topology=topology,
        source_nodes=source_nodes,
        source_edges=tuple(source_edges),
        physical_links=tuple(physical_links),
        source_provenance_hash=provenance_hash,
        physical_profile_hash=physical_hash,
        largest_scc_node_ids=tuple(
            canonical_cork_node_id(item) for item in sorted(largest_scc)
        ),
    )


def resolve_cork_graph_path(path: Path | None = None) -> Path:
    """Resolve the external pinned graph without embedding a machine path."""

    if path is not None:
        return path.expanduser()
    configured = os.environ.get(CORK_GRAPH_ENVIRONMENT_VARIABLE)
    if configured:
        return Path(configured).expanduser()
    return CORK_DEFAULT_GRAPH_PATH


def _physical_link(link_id: str, data: Mapping[str, Any]) -> CorkPhysicalLink:
    road_class = _road_class(data.get("highway"))
    speed_kph = dict(CORK_SPEED_KPH_BY_HIGHWAY).get(road_class, FALLBACK_SPEED_KPH)
    capacity = dict(CORK_CAPACITY_PER_LANE_BY_HIGHWAY).get(road_class, 900.0)
    lanes = _directional_lane_count(data.get("lanes"), _as_bool(data.get("oneway")))
    length = float(data["length"])
    speed_mps = speed_kph / 3.6
    jam_density = derive_jam_density_veh_per_km_per_lane(
        capacity_veh_per_hour_per_lane=capacity,
        free_flow_speed_mps=speed_mps,
        backward_wave_speed_mps=CORK_BACKWARD_WAVE_SPEED_MPS,
    )
    storage = max(1, floor(length / 1000.0 * lanes * jam_density))
    ff_seconds = length / speed_mps
    return CorkPhysicalLink(
        link_id=link_id,
        road_class=road_class,
        length_m=length,
        lane_count=lanes,
        free_flow_speed_mps=speed_mps,
        capacity_veh_per_hour_per_lane=capacity,
        backward_wave_speed_mps=CORK_BACKWARD_WAVE_SPEED_MPS,
        jam_density_veh_per_km_per_lane=jam_density,
        storage_capacity_packets=storage,
        free_flow_travel_time_seconds=ff_seconds,
        free_flow_lag_ticks=max(1, ceil(ff_seconds / CORK_TICK_DURATION_SECONDS)),
        backward_wave_lag_ticks=max(
            1,
            ceil(
                length
                / CORK_BACKWARD_WAVE_SPEED_MPS
                / CORK_TICK_DURATION_SECONDS
            ),
        ),
    )


def _loading_link(item: CorkPhysicalLink) -> Link:
    return Link(
        link_id=item.link_id,
        declared_sending_capacity_per_tick=1,
        declared_receiving_capacity_per_tick=1,
        declared_storage_capacity_packets=item.storage_capacity_packets,
        length_m=item.length_m,
        lane_count=item.lane_count,
        free_flow_speed_mps=item.free_flow_speed_mps,
        jam_density_veh_per_km_per_lane=item.jam_density_veh_per_km_per_lane,
        backward_wave_speed_mps=item.backward_wave_speed_mps,
        capacity_veh_per_hour_per_lane=item.capacity_veh_per_hour_per_lane,
        tick_duration_seconds=CORK_TICK_DURATION_SECONDS,
    )


def _road_class(raw: object) -> str:
    values = _source_list(raw)
    rank = {name: index for index, name in enumerate(_HIGHWAY_PRECEDENCE)}
    return min((str(item) for item in values), key=lambda item: (rank.get(item, 999), item))


def _directional_lane_count(raw: object, oneway: bool) -> int:
    values = []
    for item in _source_list(raw) if raw is not None else ():
        try:
            values.append(max(1, int(float(item))))
        except (TypeError, ValueError):
            continue
    total = max(values, default=1)
    return total if oneway else max(1, ceil(total / 2))


def _source_list(raw: object) -> tuple[object, ...]:
    if isinstance(raw, (list, tuple)):
        return tuple(raw)
    if isinstance(raw, str) and raw.startswith("["):
        try:
            parsed = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return (raw,)
        if isinstance(parsed, (list, tuple)):
            return tuple(parsed)
    return (raw,)


def _as_bool(raw: object) -> bool:
    return raw is True or str(raw).strip().lower() in {"true", "yes", "1"}


def _metadata_items(
    data: Mapping[str, Any], fields: tuple[str, ...]
) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (name, json.dumps(data[name], sort_keys=True, ensure_ascii=False))
            for name in fields
            if name in data
        )
    )


def _stable_hash(domain: str, payload: object) -> str:
    text = json.dumps(
        {"domain": domain, "value": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sort_key(value: object) -> tuple[str, str]:
    return type(value).__name__, str(value)
