# SPDX-License-Identifier: MPL-2.0
"""Sioux Falls TNTP benchmark loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import get_project_paths
from .tntp_parser import TntpLink, parse_tntp_network, parse_tntp_trips


SIOUX_FALLS_DIR = get_project_paths().data / "benchmarks" / "sioux_falls"
SIOUX_FALLS_NET_PATH = SIOUX_FALLS_DIR / "SiouxFalls_net.tntp"
SIOUX_FALLS_TRIPS_PATH = SIOUX_FALLS_DIR / "SiouxFalls_trips.tntp"


@dataclass(frozen=True, slots=True)
class SiouxFallsBenchmark:
    """Loaded Sioux Falls benchmark data ready for future assignment code."""

    nodes: list[int]
    directed_links: list[TntpLink]
    od_demand: dict[tuple[int, int], float]
    total_od_demand: float
    graph: Any
    edge_records: list[dict[str, float | int]]


def build_networkx_graph(links: list[TntpLink], nodes: list[int]) -> Any:
    """Build a directed NetworkX graph with stable edge IDs as attributes."""

    nx = __import__("networkx")
    graph = nx.DiGraph()
    graph.add_nodes_from(nodes)

    for link in links:
        if graph.has_edge(link.tail, link.head):
            raise ValueError(f"Duplicate directed link {link.tail}->{link.head}")
        graph.add_edge(
            link.tail,
            link.head,
            edge_id=link.edge_id,
            tail=link.tail,
            head=link.head,
            capacity=link.capacity,
            free_flow_time=link.free_flow_time,
            bpr_alpha=link.bpr_alpha,
            bpr_beta=link.bpr_beta,
        )

    return graph


def _edge_record(link: TntpLink) -> dict[str, float | int]:
    return {
        "edge_id": link.edge_id,
        "tail": link.tail,
        "head": link.head,
        "capacity": link.capacity,
        "free_flow_time": link.free_flow_time,
        "bpr_alpha": link.bpr_alpha,
        "bpr_beta": link.bpr_beta,
    }


def load_sioux_falls(
    net_path: Path = SIOUX_FALLS_NET_PATH,
    trips_path: Path = SIOUX_FALLS_TRIPS_PATH,
) -> SiouxFallsBenchmark:
    """Load Sioux Falls TNTP network and OD demand files."""

    network = parse_tntp_network(net_path)
    trips = parse_tntp_trips(trips_path)
    graph = build_networkx_graph(network.links, network.nodes)

    return SiouxFallsBenchmark(
        nodes=network.nodes,
        directed_links=network.links,
        od_demand=trips.od_demand,
        total_od_demand=trips.total_demand,
        graph=graph,
        edge_records=[_edge_record(link) for link in network.links],
    )


def _debug_summary() -> str:
    benchmark = load_sioux_falls()
    nx = __import__("networkx")
    shortest_path = nx.shortest_path(benchmark.graph, 1, 24, weight="free_flow_time")
    shortest_path_time = nx.shortest_path_length(benchmark.graph, 1, 24, weight="free_flow_time")
    return "\n".join(
        [
            "Sioux Falls benchmark",
            f"nodes: {len(benchmark.nodes)}",
            f"directed_links: {len(benchmark.directed_links)}",
            f"total_od_demand: {benchmark.total_od_demand:.1f}",
            f"free_flow_shortest_path_1_to_24: {shortest_path}",
            f"free_flow_shortest_path_time_1_to_24: {shortest_path_time:.3f}",
        ]
    )


if __name__ == "__main__":
    print(_debug_summary())
