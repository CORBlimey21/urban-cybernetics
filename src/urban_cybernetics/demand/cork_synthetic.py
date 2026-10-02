# SPDX-License-Identifier: MPL-2.0
"""Seeded synthetic OD generation and weighted route resolution for Cork."""

from __future__ import annotations

import hashlib
import heapq
import json
import math
import random
from dataclasses import dataclass
from time import perf_counter

from urban_cybernetics.demand.manifest import (
    DemandManifest,
    DemandManifestSourceMetadata,
    GlobalUniformDepartureSchedule,
    ODDemandDeclaration,
)
from urban_cybernetics.demand.resolution import (
    ResolvedDemandManifest,
    ResolvedDemandRoute,
)
from urban_cybernetics.topology.cork import CorkCanonicalNetwork
from urban_cybernetics.topology.routes import CanonicalRoute


CORK_SYNTHETIC_DEMAND_POLICY_VERSION = "uc.cork-synthetic-scc-od.v1"
CORK_WEIGHTED_ROUTING_POLICY_VERSION = "uc.cork-free-flow-dijkstra.v1"
DEFAULT_CORK_DEMAND_SEED = 20260819
DEFAULT_LOADING_WINDOW_SECONDS = 300.0
DEFAULT_MINIMUM_STRAIGHT_LINE_DISTANCE_M = 1_500.0
DEFAULT_MAXIMUM_UNIQUE_OD_PAIRS = 1_000


@dataclass(frozen=True, slots=True)
class EvenlySpacedGlobalDepartureSchedule(GlobalUniformDepartureSchedule):
    """Place the first and last packet at the physical window boundaries."""

    def hash_payload(self) -> dict[str, object]:
        return {
            "schedule_type": "global_evenly_spaced_window",
            "start_tick": self.start_tick,
            "end_tick": self.end_tick,
        }

    def _global_ticks(self, total_quantity: int, tick_count: int) -> tuple[int, ...]:
        if total_quantity == 1:
            return (self.start_tick,)
        span = tick_count - 1
        return tuple(
            self.start_tick + (index * span // (total_quantity - 1))
            for index in range(total_quantity)
        )


@dataclass(frozen=True, slots=True)
class CorkSyntheticDemand:
    manifest: DemandManifest
    seed: int
    requested_packet_count: int
    unique_od_count: int
    loading_window_seconds: float
    loading_window_start_tick: int
    loading_window_end_tick: int
    minimum_straight_line_distance_m: float
    policy_version: str = CORK_SYNTHETIC_DEMAND_POLICY_VERSION

    def status_payload(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "seed": self.seed,
            "requested_packet_count": self.requested_packet_count,
            "unique_od_count": self.unique_od_count,
            "largest_scc_only": True,
            "self_pairs_excluded": True,
            "minimum_straight_line_distance_m": self.minimum_straight_line_distance_m,
            "loading_window_seconds": self.loading_window_seconds,
            "loading_window_start_tick": self.loading_window_start_tick,
            "loading_window_end_tick": self.loading_window_end_tick,
            "departure_schedule": "global_evenly_spaced_inclusive_tick_window",
            "manifest_hash": self.manifest.manifest_hash,
        }


@dataclass(frozen=True, slots=True)
class CorkRouteResolution:
    resolved_manifest: ResolvedDemandManifest
    route_resolution_seconds: float
    route_resolution_hash: str
    route_link_counts: tuple[int, ...]
    route_free_flow_times_seconds: tuple[float, ...]
    cache_hit_count: int
    policy_version: str = CORK_WEIGHTED_ROUTING_POLICY_VERSION

    def status_payload(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "route_count": len(self.resolved_manifest.resolved_routes),
            "unique_od_count": len(self.resolved_manifest.resolved_routes),
            "cache_hit_count": self.cache_hit_count,
            "route_resolution_seconds": self.route_resolution_seconds,
            "route_resolution_hash": self.route_resolution_hash,
            "route_link_count_distribution": _distribution(self.route_link_counts),
            "route_free_flow_time_seconds_distribution": _distribution(
                self.route_free_flow_times_seconds
            ),
            "tie_breaking": (
                "minimum free-flow seconds; then lexicographically smallest full "
                "canonical link-ID sequence, including parallel-edge IDs"
            ),
        }


def build_cork_synthetic_demand(
    network: CorkCanonicalNetwork,
    *,
    packet_count: int,
    seed: int = DEFAULT_CORK_DEMAND_SEED,
    maximum_unique_od_pairs: int = DEFAULT_MAXIMUM_UNIQUE_OD_PAIRS,
    minimum_straight_line_distance_m: float = DEFAULT_MINIMUM_STRAIGHT_LINE_DISTANCE_M,
    loading_window_seconds: float = DEFAULT_LOADING_WINDOW_SECONDS,
) -> CorkSyntheticDemand:
    """Create reproducible aggregated OD demand inside the largest SCC."""

    if packet_count <= 0:
        raise ValueError("packet_count must be positive")
    if maximum_unique_od_pairs <= 0:
        raise ValueError("maximum_unique_od_pairs must be positive")
    coordinates = _coordinates(network)
    candidate_nodes = tuple(
        node_id for node_id in network.largest_scc_node_ids if node_id in coordinates
    )
    target = min(packet_count, maximum_unique_od_pairs)
    rng = random.Random(seed)
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    attempts = 0
    maximum_attempts = target * 1_000
    while len(pairs) < target and attempts < maximum_attempts:
        attempts += 1
        origin, destination = rng.sample(candidate_nodes, 2)
        pair = (origin, destination)
        if pair in seen:
            continue
        if _haversine_metres(coordinates[origin], coordinates[destination]) < minimum_straight_line_distance_m:
            continue
        seen.add(pair)
        pairs.append(pair)
    if len(pairs) != target:
        raise ValueError(f"could not generate {target} distinct Cork OD pairs")

    start_tick = 0
    end_tick = max(0, round(loading_window_seconds / 0.04) - 1)
    schedule = EvenlySpacedGlobalDepartureSchedule(start_tick, end_tick)
    base, remainder = divmod(packet_count, target)
    declarations = tuple(
        ODDemandDeclaration(
            demand_id=f"cork-synthetic-od:{index:06d}",
            origin_node_id=origin,
            destination_node_id=destination,
            quantity_packets=base + (1 if index <= remainder else 0),
            departure_schedule=schedule,
            cohort_id="cork-synthetic-city-scale-v1",
            authority_id="deterministic-free-flow-shortest-path-v1",
            source_metadata_items=(
                ("generator_seed", str(seed)),
                ("generator_policy", CORK_SYNTHETIC_DEMAND_POLICY_VERSION),
            ),
        )
        for index, (origin, destination) in enumerate(pairs, start=1)
    )
    source = DemandManifestSourceMetadata(
        source_name="seeded_synthetic_cork_largest_scc",
        source_format="generated_aggregated_od_pairs",
        source_metadata_items=(
            ("generator_policy", CORK_SYNTHETIC_DEMAND_POLICY_VERSION),
            ("generator_seed", str(seed)),
            ("largest_scc_node_count", str(len(network.largest_scc_node_ids))),
            ("maximum_unique_od_pairs", str(maximum_unique_od_pairs)),
            ("minimum_straight_line_distance_m", str(minimum_straight_line_distance_m)),
        ),
        interpretation_assumptions=(
            "synthetic_scaling_demand_not_saps_or_gravity",
            "routability_guaranteed_by_largest_strongly_connected_component",
            "straight_line_distance_filter_avoids_local_trivial_pairs",
        ),
        scaling_assumptions=(
            "repeated_od_pairs_are_aggregated_before_route_resolution",
            "same_five_minute_physical_departure_window_at_every_rung",
        ),
    )
    manifest = DemandManifest(
        manifest_id=f"cork-synthetic-{packet_count}-seed-{seed}-v1",
        topology_id=network.topology.topology_id,
        topology_hash=network.topology_hash,
        declarations=declarations,
        source_metadata=source,
    )
    return CorkSyntheticDemand(
        manifest=manifest,
        seed=seed,
        requested_packet_count=packet_count,
        unique_od_count=target,
        loading_window_seconds=loading_window_seconds,
        loading_window_start_tick=start_tick,
        loading_window_end_tick=end_tick,
        minimum_straight_line_distance_m=minimum_straight_line_distance_m,
    )


def resolve_cork_weighted_routes(
    network: CorkCanonicalNetwork,
    demand: CorkSyntheticDemand,
) -> CorkRouteResolution:
    """Resolve each unique OD once with deterministic free-flow Dijkstra."""

    if demand.manifest.topology_hash != network.topology_hash:
        raise ValueError("demand/topology hash mismatch")
    started = perf_counter()
    adjacency: dict[str, list[tuple[str, str, float]]] = {
        node.node_id: [] for node in network.topology.nodes
    }
    physical_by_id = {item.link_id: item for item in network.physical_links}
    for link in network.topology.links:
        adjacency[link.tail_node_id].append(
            (
                link.head_node_id,
                link.link_id,
                physical_by_id[link.link_id].free_flow_travel_time_seconds,
            )
        )
    for values in adjacency.values():
        values.sort(key=lambda item: (item[2], item[1], item[0]))

    cache: dict[tuple[str, str], CanonicalRoute] = {}
    cache_hits = 0
    resolved: list[ResolvedDemandRoute] = []
    link_counts: list[int] = []
    free_flow_times: list[float] = []
    for declaration in demand.manifest.declarations:
        key = (declaration.origin_node_id, declaration.destination_node_id)
        route = cache.get(key)
        if route is None:
            route = _weighted_route(
                network,
                adjacency,
                origin=key[0],
                destination=key[1],
            )
            cache[key] = route
        else:
            cache_hits += 1
        resolved.append(ResolvedDemandRoute(declaration.demand_id, route))
        link_counts.append(len(route.ordered_link_ids))
        free_flow_times.append(
            sum(
                physical_by_id[link_id].free_flow_travel_time_seconds
                for link_id in route.ordered_link_ids
            )
        )
    resolved_manifest = ResolvedDemandManifest(
        demand_manifest=demand.manifest,
        resolved_routes=tuple(resolved),
        route_resolution_method=CORK_WEIGHTED_ROUTING_POLICY_VERSION,
    )
    route_hash = _stable_hash(
        "cork-route-resolution",
        {
            "policy": CORK_WEIGHTED_ROUTING_POLICY_VERSION,
            "resolved_manifest_hash": resolved_manifest.resolved_manifest_hash,
            "routes": [item.hash_payload() for item in resolved],
        },
    )
    return CorkRouteResolution(
        resolved_manifest=resolved_manifest,
        route_resolution_seconds=perf_counter() - started,
        route_resolution_hash=route_hash,
        route_link_counts=tuple(link_counts),
        route_free_flow_times_seconds=tuple(free_flow_times),
        cache_hit_count=cache_hits,
    )


def _weighted_route(
    network: CorkCanonicalNetwork,
    adjacency: dict[str, list[tuple[str, str, float]]],
    *,
    origin: str,
    destination: str,
) -> CanonicalRoute:
    queue: list[tuple[float, tuple[str, ...], str]] = [(0.0, (), origin)]
    best: dict[str, tuple[float, tuple[str, ...]]] = {origin: (0.0, ())}
    while queue:
        cost, path, node_id = heapq.heappop(queue)
        if best.get(node_id) != (cost, path):
            continue
        if node_id == destination:
            digest = hashlib.sha256(
                "|".join((network.topology_hash, origin, destination, *path)).encode()
            ).hexdigest()[:12]
            route = CanonicalRoute(
                route_id=f"route:{origin}->{destination}:{digest}",
                origin_node_id=origin,
                destination_node_id=destination,
                ordered_link_ids=path,
            )
            route.validate_for_topology(network.topology)
            return route
        for next_node, link_id, weight in adjacency[node_id]:
            candidate = (cost + weight, (*path, link_id))
            previous = best.get(next_node)
            if previous is None or candidate < previous:
                best[next_node] = candidate
                heapq.heappush(queue, (candidate[0], candidate[1], next_node))
    raise ValueError(f"no weighted directed path from {origin} to {destination}")


def _coordinates(network: CorkCanonicalNetwork) -> dict[str, tuple[float, float]]:
    result = {}
    for item in network.source_nodes:
        metadata = dict(item.source_metadata_items)
        if "x" in metadata and "y" in metadata:
            result[item.canonical_node_id] = (
                float(json.loads(metadata["y"])),
                float(json.loads(metadata["x"])),
            )
    return result


def _haversine_metres(
    first: tuple[float, float], second: tuple[float, float]
) -> float:
    lat1, lon1 = map(math.radians, first)
    lat2, lon2 = map(math.radians, second)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_008.8 * 2 * math.asin(math.sqrt(a))


def _distribution(values: tuple[float | int, ...]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "median": None, "mean": None, "max": None}
    ordered = sorted(values)
    middle = len(ordered) // 2
    median = (
        ordered[middle]
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / 2
    )
    return {
        "count": len(ordered),
        "min": ordered[0],
        "median": median,
        "mean": sum(ordered) / len(ordered),
        "max": ordered[-1],
    }


def _stable_hash(domain: str, payload: object) -> str:
    text = json.dumps(
        {"domain": domain, "value": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(text.encode()).hexdigest()
