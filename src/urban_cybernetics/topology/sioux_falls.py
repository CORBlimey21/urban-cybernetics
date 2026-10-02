# SPDX-License-Identifier: MPL-2.0
"""Canonical topology builder for the committed Sioux Falls TNTP network."""

from __future__ import annotations

from pathlib import Path

from urban_cybernetics.benchmarks.sioux_falls import SIOUX_FALLS_NET_PATH
from urban_cybernetics.benchmarks.tntp_parser import TntpLink, parse_tntp_network
from urban_cybernetics.topology.canonical import (
    CanonicalNode,
    CanonicalTopology,
    CanonicalTopologyLink,
    TopologySourceMetadata,
)


MILES_TO_METRES = 1609.344
MINUTES_TO_SECONDS = 60.0
SIOUX_FALLS_INTERPRETATION_ASSUMPTIONS = (
    "TNTP Sioux Falls length values are interpreted as miles for this benchmark topology.",
    "TNTP Sioux Falls free_flow_time values are interpreted as minutes.",
    "TNTP Sioux Falls capacity values are interpreted as vehicles per hour.",
    "Lane count is fixed at one where the TNTP source does not provide lanes.",
    "Jam density and backward wave speed are not present in the source and are left absent.",
    "BPR alpha and beta remain static-assignment reference parameters and are not canonical topology fields.",
)


def load_sioux_falls_topology(
    net_path: Path = SIOUX_FALLS_NET_PATH,
) -> CanonicalTopology:
    """Load the committed Sioux Falls TNTP network as a canonical topology."""

    network = parse_tntp_network(net_path)
    source_node_to_canonical = {
        source_node_id: f"N{index:03d}"
        for index, source_node_id in enumerate(sorted(network.nodes), start=1)
    }
    sorted_links = sorted(network.links, key=lambda link: (link.tail, link.head))
    canonical_links = tuple(
        _canonical_link(
            link,
            link_index=index,
            source_node_to_canonical=source_node_to_canonical,
        )
        for index, link in enumerate(sorted_links, start=1)
    )
    canonical_nodes = _canonical_nodes(network.nodes, canonical_links, source_node_to_canonical)
    source_metadata = TopologySourceMetadata.from_path(
        source_name="Sioux Falls",
        source_format="TNTP network",
        source_file_path=net_path,
        source_metadata_items=tuple(
            (str(key), str(value)) for key, value in network.metadata.items()
        ),
    )
    return CanonicalTopology(
        topology_id="sioux_falls_tntp_v1",
        nodes=canonical_nodes,
        links=canonical_links,
        source_metadata=source_metadata,
        interpretation_assumptions=SIOUX_FALLS_INTERPRETATION_ASSUMPTIONS,
    )


def _canonical_link(
    link: TntpLink,
    *,
    link_index: int,
    source_node_to_canonical: dict[int, str],
) -> CanonicalTopologyLink:
    source_link_id = f"{link.tail}->{link.head}"
    length_m = link.length * MILES_TO_METRES
    free_flow_seconds = link.free_flow_time * MINUTES_TO_SECONDS
    free_flow_speed_mps = length_m / free_flow_seconds
    return CanonicalTopologyLink(
        link_id=f"L{link_index:04d}",
        tail_node_id=source_node_to_canonical[link.tail],
        head_node_id=source_node_to_canonical[link.head],
        source_link_id=source_link_id,
        source_tail_node_id=str(link.tail),
        source_head_node_id=str(link.head),
        length_m=length_m,
        lane_count=1,
        free_flow_speed_mps=free_flow_speed_mps,
        capacity_veh_per_hour_per_lane=link.capacity,
        jam_density_veh_per_km_per_lane=None,
        backward_wave_speed_mps=None,
        source_length_value=link.length,
        source_length_unit="mile",
        source_free_flow_time_value=link.free_flow_time,
        source_free_flow_time_unit="minute",
        source_capacity_value=link.capacity,
        source_capacity_unit="vehicle_per_hour",
    )


def _canonical_nodes(
    source_nodes: list[int],
    links: tuple[CanonicalTopologyLink, ...],
    source_node_to_canonical: dict[int, str],
) -> tuple[CanonicalNode, ...]:
    incoming_by_node = {canonical_id: [] for canonical_id in source_node_to_canonical.values()}
    outgoing_by_node = {canonical_id: [] for canonical_id in source_node_to_canonical.values()}
    for link in links:
        outgoing_by_node[link.tail_node_id].append(link.link_id)
        incoming_by_node[link.head_node_id].append(link.link_id)

    return tuple(
        CanonicalNode(
            node_id=source_node_to_canonical[source_node_id],
            source_node_id=str(source_node_id),
            incoming_link_ids=tuple(sorted(incoming_by_node[source_node_to_canonical[source_node_id]])),
            outgoing_link_ids=tuple(sorted(outgoing_by_node[source_node_to_canonical[source_node_id]])),
        )
        for source_node_id in sorted(source_nodes)
    )
