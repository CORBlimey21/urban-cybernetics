"""Graph loading, weighting, routing, and map-rendering utilities.

This module is the bridge between OpenStreetMap-derived road data and the higher-level simulation code.
It handles downloading or loading the Cork road graph, assigning free-flow travel times, routing between
nodes or coordinates, and rendering lightweight Folium map outputs.

Why this file exists:
- to isolate OSMnx and NetworkX graph operations from experiment logic
- to keep graph mutation rules in one place so routing and simulation stay consistent
- to make free-flow travel times and mutable simulation travel times explicit rather than implicit

Key design decisions:
- the graph keeps both `free_flow_time_seconds` and `travel_time_seconds`
  - free-flow time is the baseline derived from length and assumed speed
  - current travel time is the mutable value used by routing during simulation
- the graph also keeps `marginal_cost_seconds`
  - this starts equal to free-flow time
  - later System Optimum routing uses it as the routing cost without overwriting experienced travel time
- the graph also records live occupancy and peak congestion state during vehicle-lifecycle runs
  - `live_occupancy_count` captures how many vehicles are currently traversing the edge
  - `peak_live_occupancy_count` captures the worst simultaneous occupancy observed
  - `peak_simulated_volume` captures the worst effective hourly flow proxy inferred from occupancy
  - `peak_travel_time_seconds` captures the worst travel time observed on the edge
- cached GraphML files are used to avoid re-downloading Cork every run
- route helpers return edge-level detail so experiment code can accumulate loads without duplicating path logic
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import (
    CORK_PLACE_QUERY,
    DEFAULT_SPEED_KPH_BY_HIGHWAY,
    DESTINATION_LANDMARK,
    FALLBACK_ROUTING_WEIGHT_MULTIPLIER,
    FALLBACK_SPEED_KPH,
    MAIN_ROAD_FILTER,
    ORIGIN_LANDMARK,
    ROUTING_WEIGHT_MULTIPLIER_BY_HIGHWAY,
    get_project_paths,
)


class MissingDependencyError(RuntimeError):
    """Error raised when an expected Python dependency has not been installed."""


def _require_module(name: str) -> Any:
    """Import a module lazily and raise a clearer project-specific error if missing.

    Parameters:
    - name: The import name of the required module.

    Returns:
    - The imported module object.

    Why this approach was chosen:
    - The project should fail with a readable message when geospatial dependencies are missing,
      rather than exposing a raw `ModuleNotFoundError` from deep inside the stack.
    """

    try:
        return __import__(name)
    except ModuleNotFoundError as exc:
        raise MissingDependencyError(
            f"Missing required dependency '{name}'. Install project dependencies first."
        ) from exc


def ensure_output_dirs() -> Path:
    """Create the output and cache directories used by the project.

    Parameters:
    - None.

    Returns:
    - The maps output directory path for convenience.

    Why this approach was chosen:
    - The project should create its own working directories deterministically rather than assuming they exist.
    """

    paths = get_project_paths()
    paths.maps.mkdir(parents=True, exist_ok=True)
    paths.experiments.mkdir(parents=True, exist_ok=True)
    paths.graphs.mkdir(parents=True, exist_ok=True)
    paths.scenarios.mkdir(parents=True, exist_ok=True)
    return paths.maps


def graph_cache_path(main_roads_only: bool = False) -> Path:
    """Return the cache path for the requested Cork graph variant.

    Parameters:
    - main_roads_only: If true, return the reduced major-road graph cache path. If false, return the full-drive graph path.

    Returns:
    - The GraphML path for the requested cache variant.
    """

    suffix = "main_roads" if main_roads_only else "full_drive"
    return get_project_paths().graphs / f"cork_{suffix}.graphml"


def load_cork_graph(main_roads_only: bool = False, use_cache: bool = True) -> Any:
    """Load the Cork road graph, optionally from cache.

    Parameters:
    - main_roads_only: If true, load the reduced major-road graph used for early debugging.
    - use_cache: If true, prefer an existing local GraphML cache over a fresh download.

    Returns:
    - A NetworkX MultiDiGraph representing the Cork drivable network.

    Why this approach was chosen:
    - Full-city graph download is expensive enough to justify local caching.
    - The reduced graph is still useful for fast experiments, but the full drivable graph is the project default.
    """

    ox = _require_module("osmnx")
    ensure_output_dirs()

    cache_path = graph_cache_path(main_roads_only=main_roads_only)
    if use_cache and cache_path.exists():
        return ox.load_graphml(cache_path)

    graph_from_place_kwargs: dict[str, Any] = {
        "query": CORK_PLACE_QUERY,
        "network_type": "drive",
        "simplify": True,
    }
    if main_roads_only:
        graph_from_place_kwargs["custom_filter"] = MAIN_ROAD_FILTER

    graph = ox.graph_from_place(**graph_from_place_kwargs)
    largest = ox.truncate.largest_component(graph, strongly=False)
    ox.save_graphml(largest, cache_path)
    return largest


def _coerce_highway_values(highway: Any) -> list[str]:
    """Normalise an OSM highway value into a list of strings.

    Parameters:
    - highway: The raw `highway` attribute from an OSM edge, which may be a string, list, or missing.

    Returns:
    - A list of highway-class strings.

    Why this helper exists:
    - OSM data sometimes stores multiple classifications on one edge, and downstream logic expects a uniform shape.
    """

    if isinstance(highway, list):
        return [str(value) for value in highway]
    if highway is None:
        return []
    return [str(highway)]


def primary_highway_class(edge_data: dict[str, Any]) -> str:
    """Pick the road class that should drive modelling assumptions for an edge.

    Parameters:
    - edge_data: The attribute dictionary for one graph edge.

    Returns:
    - A single highway-class string to use for speed and capacity heuristics.

    Why this approach was chosen:
    - OSM edges can carry multiple road labels. The simulation needs one primary class so assumptions are stable.
    - The code prefers classes that already exist in the project's speed table, because those are the classes we model.
    """

    highway_values = _coerce_highway_values(edge_data.get("highway"))
    for highway in highway_values:
        if highway in DEFAULT_SPEED_KPH_BY_HIGHWAY:
            return highway
    return highway_values[0] if highway_values else "unknown"


def assumed_speed_kph_for_edge(edge_data: dict[str, Any]) -> float:
    """Return the free-flow speed assumption for an edge.

    Parameters:
    - edge_data: The attribute dictionary for one graph edge.

    Returns:
    - A speed in kilometres per hour.

    Why this approach was chosen:
    - The project currently needs a transparent heuristic that can be inspected and changed easily.
    - A road-class lookup is simpler and more defensible at this stage than inventing pseudo-precision.
    """

    highway = primary_highway_class(edge_data)
    if highway in DEFAULT_SPEED_KPH_BY_HIGHWAY:
        return DEFAULT_SPEED_KPH_BY_HIGHWAY[highway]
    return FALLBACK_SPEED_KPH


def routing_weight_multiplier_for_edge(edge_data: dict[str, Any]) -> float:
    """Return the routing-weight penalty multiplier for one edge.

    Parameters:
    - edge_data: The attribute dictionary for one graph edge.

    Returns:
    - A multiplier >= 1.0 that inflates routing costs for low-grade road classes.

    Why this approach was chosen:
    - Through-traffic must be deterred from unclassified and residential feeder edges whose
      low capacity causes extreme BPR blowup under high demand.
    - The multiplier affects only route-choice costs, not BPR physical travel times or artifact metrics.
    """

    highway = primary_highway_class(edge_data)
    return ROUTING_WEIGHT_MULTIPLIER_BY_HIGHWAY.get(highway, FALLBACK_ROUTING_WEIGHT_MULTIPLIER)


def add_travel_time_weights(graph: Any) -> Any:
    """Assign free-flow and current travel-time weights to every edge in the graph.

    Parameters:
    - graph: The NetworkX MultiDiGraph to update in place.

    Returns:
    - The same graph object, updated with speed, travel-time, and penalised routing-weight attributes.

    Why this approach was chosen:
    - The routing code needs a stable free-flow baseline and a mutable current travel time for simulation.
    - Keeping both values on the edge lets later algorithms apply congestion feedback without losing the original baseline.
    - Penalised routing weights apply a road-class multiplier so Dijkstra avoids low-grade feeder roads,
      while the underlying BPR travel times used for metrics remain unaffected.
    """

    for _, _, _, edge_data in graph.edges(keys=True, data=True):
        speed_kph = assumed_speed_kph_for_edge(edge_data)
        length_m = float(edge_data.get("length", 0.0))
        meters_per_second = speed_kph * 1000.0 / 3600.0
        free_flow_time_seconds = length_m / meters_per_second if meters_per_second else 0.0

        # Travel time starts at the free-flow baseline. Later simulation layers mutate
        # `travel_time_seconds`, and SO routing mutates `marginal_cost_seconds`, but they should
        # never overwrite the baseline itself.
        edge_data["assumed_speed_kph"] = speed_kph
        edge_data["free_flow_time_seconds"] = free_flow_time_seconds
        edge_data["travel_time_seconds"] = free_flow_time_seconds
        edge_data["marginal_cost_seconds"] = free_flow_time_seconds
        edge_data["simulated_volume"] = 0.0
        edge_data["live_occupancy_count"] = 0
        edge_data["peak_live_occupancy_count"] = 0
        edge_data["peak_simulated_volume"] = 0.0
        edge_data["peak_travel_time_seconds"] = free_flow_time_seconds

        # Penalised routing weights inflate the cost seen by Dijkstra for low-grade road classes.
        # The multiplier is stored once per edge so the BPR cost-refresh loop can recompute
        # the penalised field without repeating the highway-class lookup.
        multiplier = routing_weight_multiplier_for_edge(edge_data)
        edge_data["routing_weight_multiplier"] = multiplier
        edge_data["penalised_travel_time_seconds"] = free_flow_time_seconds * multiplier
        edge_data["penalised_marginal_cost_seconds"] = free_flow_time_seconds * multiplier
    return graph


def reset_simulation_edge_state(graph: Any) -> Any:
    """Reset mutable edge state back to the free-flow baseline.

    Parameters:
    - graph: The NetworkX MultiDiGraph to reset in place.

    Returns:
    - The same graph object with volume counters cleared and current, marginal, penalised, and peak state restored.

    Why this approach was chosen:
    - Static and congestion-aware simulations should both start from the same baseline.
    - Resetting in place avoids reloading the graph from disk every time an experiment runs.
    """

    for _, _, _, edge_data in graph.edges(keys=True, data=True):
        free_flow_time_seconds = float(edge_data.get("free_flow_time_seconds", edge_data.get("travel_time_seconds", 0.0)))
        multiplier = float(edge_data.get("routing_weight_multiplier", FALLBACK_ROUTING_WEIGHT_MULTIPLIER))
        edge_data["travel_time_seconds"] = free_flow_time_seconds
        edge_data["marginal_cost_seconds"] = free_flow_time_seconds
        edge_data["simulated_volume"] = 0.0
        edge_data["live_occupancy_count"] = 0
        edge_data["peak_live_occupancy_count"] = 0
        edge_data["peak_simulated_volume"] = 0.0
        edge_data["peak_travel_time_seconds"] = free_flow_time_seconds
        edge_data["penalised_travel_time_seconds"] = free_flow_time_seconds * multiplier
        edge_data["penalised_marginal_cost_seconds"] = free_flow_time_seconds * multiplier
    return graph


def graph_summary(graph: Any) -> dict[str, int]:
    """Return a minimal node/edge summary for a graph.

    Parameters:
    - graph: The NetworkX graph to summarise.

    Returns:
    - A dictionary containing node and edge counts.
    """

    return {
        "nodes": int(graph.number_of_nodes()),
        "edges": int(graph.number_of_edges()),
    }


def render_graph_map(
    graph: Any,
    route_info: dict[str, Any] | None = None,
    output_path: Path | None = None,
) -> Path:
    """Render the road graph, and optionally one route, as a Folium HTML map.

    Parameters:
    - graph: The road graph to render.
    - route_info: Optional route dictionary from `route_between_nodes` or `route_between_points`.
    - output_path: Optional explicit HTML output path.

    Returns:
    - The path to the written HTML file.

    Why this approach was chosen:
    - Folium gives a fast path to browser-inspectable maps without adding a frontend build system.
    - Rendering the whole network in muted styling makes it easier to spot whether a route makes intuitive sense.
    """

    ox = _require_module("osmnx")
    folium = _require_module("folium")
    output = output_path or ensure_output_dirs() / "cork_drive_graph.html"

    nodes_gdf, edges_gdf = ox.graph_to_gdfs(graph, nodes=True, edges=True)
    center_lat = float(nodes_gdf["y"].mean())
    center_lon = float(nodes_gdf["x"].mean())

    graph_map = folium.Map(location=[center_lat, center_lon], zoom_start=12, tiles="CartoDB positron")
    folium.GeoJson(
        data=edges_gdf[["geometry"]].to_json(),
        style_function=lambda _: {
            "color": "#1a1a1a",
            "weight": 2,
            "opacity": 0.55,
        },
        name="drive-network",
    ).add_to(graph_map)

    if route_info is not None:
        folium.PolyLine(
            locations=route_info["route_coordinates"],
            color="#0b8f3d",
            weight=6,
            opacity=0.95,
            tooltip=(
                f'{route_info["origin_name"]} -> {route_info["destination_name"]} '
                f'({route_info["route_node_count"]} nodes)'
            ),
        ).add_to(graph_map)
        folium.Marker(
            location=route_info["route_coordinates"][0],
            tooltip=route_info["origin_name"],
            icon=folium.Icon(color="green", icon="play"),
        ).add_to(graph_map)
        folium.Marker(
            location=route_info["route_coordinates"][-1],
            tooltip=route_info["destination_name"],
            icon=folium.Icon(color="red", icon="flag"),
        ).add_to(graph_map)

    graph_map.save(str(output))
    return output


def nearest_graph_node(graph: Any, latitude: float, longitude: float) -> int:
    """Snap a latitude/longitude pair to the closest graph node.

    Parameters:
    - graph: The NetworkX road graph used for snapping.
    - latitude: Latitude in decimal degrees.
    - longitude: Longitude in decimal degrees.

    Returns:
    - The integer node ID of the nearest graph node.

    Why this approach was chosen:
    - Node-based routing is simpler and faster than trying to route directly from arbitrary coordinates.
    """

    ox = _require_module("osmnx")
    return int(ox.distance.nearest_nodes(graph, X=longitude, Y=latitude))


def route_between_nodes(
    graph: Any,
    origin_node: int,
    destination_node: int,
    origin_name: str,
    destination_name: str,
    weight: str = "travel_time_seconds",
) -> dict[str, Any]:
    """Route between two already-snapped graph nodes.

    Parameters:
    - graph: The NetworkX road graph used for routing.
    - origin_node: Graph node ID used as the route origin.
    - destination_node: Graph node ID used as the route destination.
    - origin_name: Human-readable label for the origin.
    - destination_name: Human-readable label for the destination.
    - weight: Edge attribute used as the routing cost. By default this is current travel time.

    Returns:
    - A dictionary containing route geometry, edge list, node count, total length, and total travel time.

    Why this approach was chosen:
    - The experiment layer needs edge-level detail, not just a polyline, so it can accumulate loads and rerank roads.
    - This helper keeps the route-detail format consistent across debug tools and simulations.
    """

    nx = _require_module("networkx")

    route = nx.shortest_path(graph, origin_node, destination_node, weight=weight)
    route_coordinates = [[graph.nodes[node]["y"], graph.nodes[node]["x"]] for node in route]

    total_length_m = 0.0
    total_travel_time_seconds = 0.0
    route_edges: list[dict[str, Any]] = []
    for start, end in zip(route, route[1:]):
        edge_bundle = graph.get_edge_data(start, end)

        # A MultiDiGraph can contain parallel edges between the same nodes. We choose the edge with the
        # lowest current routing weight because that is the option Dijkstra effectively used at this step.
        chosen_key, chosen = min(
            edge_bundle.items(),
            key=lambda item: float(item[1].get(weight, 0.0)),
        )
        total_length_m += float(chosen.get("length", 0.0))
        total_travel_time_seconds += float(chosen.get("travel_time_seconds", 0.0))
        route_edges.append(
            {
                "u": int(start),
                "v": int(end),
                "key": int(chosen_key),
                "name": chosen.get("name"),
                "highway": chosen.get("highway"),
                "length_m": round(float(chosen.get("length", 0.0)), 1),
                "travel_time_seconds": round(float(chosen.get("travel_time_seconds", 0.0)), 3),
            }
        )

    return {
        "origin_name": origin_name,
        "destination_name": destination_name,
        "origin_node": int(origin_node),
        "destination_node": int(destination_node),
        "route_node_count": len(route),
        "route_coordinates": route_coordinates,
        "route_edges": route_edges,
        "total_length_m": round(total_length_m, 1),
        "total_travel_time_seconds": round(total_travel_time_seconds, 1),
    }


def route_between_nodes_with_cost_snapshot(
    graph: Any,
    origin_node: int,
    destination_node: int,
    origin_name: str,
    destination_name: str,
    weight: str,
    edge_costs: dict[tuple[int, int, int], dict[str, float]],
) -> dict[str, Any]:
    """Route using an authority-visible cost snapshot without mutating the physical graph state."""

    nx = _require_module("networkx")

    def snapshot_weight(start: Any, end: Any, edge_bundle: dict[Any, dict[str, Any]]) -> float:
        return min(
            float(
                edge_costs.get((int(start), int(end), int(edge_key)), {}).get(
                    weight,
                    edge_data.get(weight, 0.0),
                )
            )
            for edge_key, edge_data in edge_bundle.items()
        )

    route = nx.shortest_path(graph, origin_node, destination_node, weight=snapshot_weight)
    route_coordinates = [[graph.nodes[node]["y"], graph.nodes[node]["x"]] for node in route]

    total_length_m = 0.0
    total_travel_time_seconds = 0.0
    route_edges: list[dict[str, Any]] = []
    for start, end in zip(route, route[1:]):
        edge_bundle = graph.get_edge_data(start, end)
        chosen_key, chosen = min(
            edge_bundle.items(),
            key=lambda item: (
                float(
                    edge_costs.get((int(start), int(end), int(item[0])), {}).get(
                        weight,
                        item[1].get(weight, 0.0),
                    )
                ),
                float(item[1].get("travel_time_seconds", 0.0)),
                int(item[0]),
            ),
        )
        total_length_m += float(chosen.get("length", 0.0))
        total_travel_time_seconds += float(chosen.get("travel_time_seconds", 0.0))
        route_edges.append(
            {
                "u": int(start),
                "v": int(end),
                "key": chosen_key,
                "name": chosen.get("name"),
                "highway": chosen.get("highway"),
                "length_m": round(float(chosen.get("length", 0.0)), 1),
                "travel_time_seconds": round(float(chosen.get("travel_time_seconds", 0.0)), 3),
            }
        )

    return {
        "origin_name": origin_name,
        "destination_name": destination_name,
        "origin_node": int(origin_node),
        "destination_node": int(destination_node),
        "route_node_count": len(route),
        "route_coordinates": route_coordinates,
        "route_edges": route_edges,
        "total_length_m": round(total_length_m, 1),
        "total_travel_time_seconds": round(total_travel_time_seconds, 1),
    }


def route_between_points(
    graph: Any,
    origin_name: str,
    origin_latitude: float,
    origin_longitude: float,
    destination_name: str,
    destination_latitude: float,
    destination_longitude: float,
    weight: str = "travel_time_seconds",
) -> dict[str, Any]:
    """Route between two raw coordinate pairs by snapping them to graph nodes first.

    Parameters:
    - graph: The NetworkX road graph used for routing.
    - origin_name: Human-readable label for the origin.
    - origin_latitude: Origin latitude in decimal degrees.
    - origin_longitude: Origin longitude in decimal degrees.
    - destination_name: Human-readable label for the destination.
    - destination_latitude: Destination latitude in decimal degrees.
    - destination_longitude: Destination longitude in decimal degrees.
    - weight: Edge attribute used as the routing cost.

    Returns:
    - The same route-detail dictionary produced by `route_between_nodes`.

    Why this approach was chosen:
    - Debugging and ad hoc testing often start from coordinates rather than pre-snapped node IDs.
    """

    origin = nearest_graph_node(graph, origin_latitude, origin_longitude)
    destination = nearest_graph_node(graph, destination_latitude, destination_longitude)
    return route_between_nodes(
        graph=graph,
        origin_node=origin,
        destination_node=destination,
        origin_name=origin_name,
        destination_name=destination_name,
        weight=weight,
    )


def sample_route(graph: Any, weight: str = "travel_time_seconds") -> dict[str, Any]:
    """Build the sample route used by the basic graph demo.

    Parameters:
    - graph: The NetworkX road graph used for routing.
    - weight: Edge attribute used as the routing cost.

    Returns:
    - A route-detail dictionary for the sample origin and destination configured in `config.py`.
    """

    return route_between_points(
        graph=graph,
        origin_name=ORIGIN_LANDMARK.name,
        origin_latitude=ORIGIN_LANDMARK.latitude,
        origin_longitude=ORIGIN_LANDMARK.longitude,
        destination_name=DESTINATION_LANDMARK.name,
        destination_latitude=DESTINATION_LANDMARK.latitude,
        destination_longitude=DESTINATION_LANDMARK.longitude,
        weight=weight,
    )


def build_week1_artifacts() -> dict[str, Any]:
    """Build the original single-route graph smoke-test artifacts.

    Parameters:
    - None.

    Returns:
    - A dictionary containing graph summary data, output path, and one sample route.

    Why this helper remains:
    - It still provides a fast smoke test for the graph and route pipeline.
    """

    ensure_output_dirs()
    graph = add_travel_time_weights(load_cork_graph(main_roads_only=False))
    summary = graph_summary(graph)
    route_info = sample_route(graph)
    map_path = render_graph_map(graph, route_info=route_info)
    return {
        "graph": summary,
        "map_path": str(map_path),
        "sample_route": route_info,
    }
