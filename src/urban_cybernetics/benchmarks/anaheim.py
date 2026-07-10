"""Anaheim TNTP benchmark loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import get_project_paths
from .sioux_falls import build_networkx_graph
from .tntp_parser import TntpLink, parse_tntp_network, parse_tntp_trips


ANAHEIM_DIR = get_project_paths().data / "benchmarks" / "anaheim"
ANAHEIM_NET_PATH = ANAHEIM_DIR / "Anaheim_net.tntp"
ANAHEIM_TRIPS_PATH = ANAHEIM_DIR / "Anaheim_trips.tntp"
ANAHEIM_FLOW_PATH = ANAHEIM_DIR / "Anaheim_flow.tntp"


@dataclass(frozen=True, slots=True)
class AnaheimBenchmark:
    """Loaded Anaheim benchmark data."""

    nodes: list[int]
    directed_links: list[TntpLink]
    od_demand: dict[tuple[int, int], float]
    total_od_demand: float
    graph: Any
    edge_records: list[dict[str, float | int]]


def load_anaheim(
    net_path: Path = ANAHEIM_NET_PATH,
    trips_path: Path = ANAHEIM_TRIPS_PATH,
) -> AnaheimBenchmark:
    """Load Anaheim TNTP network and OD demand files."""

    network = parse_tntp_network(net_path)
    trips = parse_tntp_trips(trips_path)
    graph = build_networkx_graph(network.links, network.nodes)

    return AnaheimBenchmark(
        nodes=network.nodes,
        directed_links=network.links,
        od_demand=trips.od_demand,
        total_od_demand=trips.total_demand,
        graph=graph,
        edge_records=[
            {
                "edge_id": link.edge_id,
                "tail": link.tail,
                "head": link.head,
                "capacity": link.capacity,
                "length": link.length,
                "free_flow_time": link.free_flow_time,
                "bpr_alpha": link.bpr_alpha,
                "bpr_beta": link.bpr_beta,
                "speed_limit": link.speed_limit or 0.0,
                "link_type": link.link_type or 0,
            }
            for link in network.links
        ],
    )
