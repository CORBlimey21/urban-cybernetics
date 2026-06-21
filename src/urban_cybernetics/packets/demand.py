"""Demand and preset-node helpers for Cork Collective Routing.

This module turns human-readable named places into stable graph nodes and provides the lightweight
trip-request structures used by routing and simulation code.

Why this file exists:
- to keep snapping logic separate from routing logic
- to make demand generation easy to audit without reading graph internals
- to support both exploratory randomised demand and fixed benchmark scenarios

Key design decisions:
- named graph points store both the original human coordinate and the snapped node coordinate so any
  mismatch is inspectable
- trip requests are plain dataclasses because the current simulation pipeline benefits more from
  transparency than from a heavier domain model
- destinations are snapped once and then reused to avoid simulation drift across runs
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from random import Random
from typing import Any

from ..config import CITY_CENTRE_DESTINATIONS, RESIDENTIAL_ORIGINS, SIMULATION_ORIGINS
from ..network.graph_pipeline import nearest_graph_node


@dataclass(frozen=True, slots=True)
class NamedGraphPoint:
    """A named place snapped onto a graph node.

    Parameters:
    - name: Human-readable label for the place.
    - latitude: Original requested latitude before snapping.
    - longitude: Original requested longitude before snapping.
    - node_id: Graph node ID chosen as the snapped representation.
    - node_latitude: Latitude of the snapped node in the graph.
    - node_longitude: Longitude of the snapped node in the graph.

    Returns:
    - A frozen dataclass that keeps both the requested point and the snapped graph node together.
    """

    name: str
    latitude: float
    longitude: float
    node_id: int
    node_latitude: float
    node_longitude: float


@dataclass(frozen=True, slots=True)
class TripRequest:
    """A single routing request used by batch experiments.

    Parameters:
    - trip_id: Stable identifier for the trip inside an experiment.
    - origin_name: Human-readable origin label.
    - origin_latitude: Origin latitude in decimal degrees.
    - origin_longitude: Origin longitude in decimal degrees.
    - destination_name: Human-readable destination label.
    - destination_latitude: Destination latitude in decimal degrees.
    - destination_longitude: Destination longitude in decimal degrees.
    - departure_minute: Minute-of-day used to label the departure bucket.
    - origin_node: Snapped graph node used as the route origin.
    - destination_node: Snapped graph node used as the route destination.

    Returns:
    - A frozen dataclass that can be written directly into manifests and experiment outputs.
    """

    trip_id: str
    origin_name: str
    origin_latitude: float
    origin_longitude: float
    destination_name: str
    destination_latitude: float
    destination_longitude: float
    departure_minute: int
    origin_node: int
    destination_node: int


def _jitter_coordinate(value: float, jitter_degrees: float, rng: Random) -> float:
    """Apply symmetric random jitter to a coordinate.

    Parameters:
    - value: The original latitude or longitude.
    - jitter_degrees: The maximum absolute offset to apply in decimal degrees.
    - rng: The seeded random number generator controlling reproducibility.

    Returns:
    - The original coordinate with a random offset applied.

    Why this helper exists:
    - Exploratory demand needs small spatial variation without changing the broader neighbourhood.
    - Keeping the jitter logic isolated makes it easy to remove for fixed benchmark scenarios.
    """

    return value + rng.uniform(-jitter_degrees, jitter_degrees)


def build_named_destinations(
    graph: Any,
    destinations: tuple[Any, ...] = CITY_CENTRE_DESTINATIONS,
) -> list[NamedGraphPoint]:
    """Snap named destination presets onto the graph once.

    Parameters:
    - graph: The NetworkX road graph used for routing.
    - destinations: Human-readable destination landmarks that should be snapped to graph nodes.

    Returns:
    - A list of `NamedGraphPoint` objects, one per destination preset.

    Why this approach was chosen:
    - Snapping once and reusing node IDs makes experiment inputs stable.
    - Storing both requested and snapped coordinates makes mis-snaps visible during review.
    """

    named_destinations: list[NamedGraphPoint] = []
    for destination in destinations:
        node_id = nearest_graph_node(graph, destination.latitude, destination.longitude)
        named_destinations.append(
            NamedGraphPoint(
                name=destination.name,
                latitude=destination.latitude,
                longitude=destination.longitude,
                node_id=node_id,
                node_latitude=float(graph.nodes[node_id]["y"]),
                node_longitude=float(graph.nodes[node_id]["x"]),
            )
        )
    return named_destinations


def build_named_origins(
    graph: Any,
    origins: tuple[Any, ...] = SIMULATION_ORIGINS,
) -> list[NamedGraphPoint]:
    """Snap the validated simulation origins onto the graph.

    Parameters:
    - graph: The NetworkX road graph used for routing.
    - origins: Human-readable origin landmarks that should be snapped to graph nodes.

    Returns:
    - A list of `NamedGraphPoint` objects representing the benchmark simulation origins.

    Why this approach was chosen:
    - The benchmark simulation should use fixed graph nodes rather than fresh coordinate snapping on every run.
    - This keeps origin behaviour reproducible while still exposing the original intended place.
    """

    named_origins: list[NamedGraphPoint] = []
    for origin in origins:
        node_id = nearest_graph_node(graph, origin.latitude, origin.longitude)
        named_origins.append(
            NamedGraphPoint(
                name=origin.name,
                latitude=origin.latitude,
                longitude=origin.longitude,
                node_id=node_id,
                node_latitude=float(graph.nodes[node_id]["y"]),
                node_longitude=float(graph.nodes[node_id]["x"]),
            )
        )
    return named_origins


def build_morning_rush_demand(
    graph: Any,
    trip_count: int = 75,
    seed: int = 20260306,
    start_minute: int = 450,
    end_minute: int = 540,
    origin_jitter_degrees: float = 0.004,
    origins: tuple[Any, ...] = RESIDENTIAL_ORIGINS,
    named_destinations: list[NamedGraphPoint] | None = None,
) -> list[TripRequest]:
    """Generate exploratory morning-rush demand with jittered residential origins.

    Parameters:
    - graph: The NetworkX road graph used for snapping nodes.
    - trip_count: Number of trips to generate.
    - seed: Seed controlling reproducible random choices.
    - start_minute: Earliest departure minute-of-day.
    - end_minute: Latest departure minute-of-day.
    - origin_jitter_degrees: Maximum random coordinate offset applied to origin landmarks.
    - origins: Residential landmarks that can act as origin neighbourhoods.
    - named_destinations: Optional pre-snapped destination points. If omitted, they are built from the graph.

    Returns:
    - A list of `TripRequest` objects representing exploratory demand.

    Why this approach was chosen:
    - This generator remains useful for experimentation even though the benchmark comparison now uses
      a fixed manifest.
    - Origins are jittered to avoid every trip collapsing onto one exact residential node, while destinations
      remain fixed to keep the city-centre targets interpretable.
    """

    rng = Random(seed)
    demand: list[TripRequest] = []
    resolved_destinations = named_destinations or build_named_destinations(graph)

    for trip_index in range(trip_count):
        origin_landmark = rng.choice(origins)
        destination = rng.choice(resolved_destinations)

        # A small spatial jitter gives exploratory demand some neighbourhood spread without moving it
        # into a completely different corridor. The benchmark scenario intentionally does not do this.
        origin_latitude = _jitter_coordinate(
            origin_landmark.latitude,
            origin_jitter_degrees,
            rng,
        )
        origin_longitude = _jitter_coordinate(
            origin_landmark.longitude,
            origin_jitter_degrees,
            rng,
        )

        demand.append(
            TripRequest(
                trip_id=f"morning-rush-{trip_index + 1:03d}",
                origin_name=origin_landmark.name,
                origin_latitude=origin_latitude,
                origin_longitude=origin_longitude,
                destination_name=destination.name,
                destination_latitude=destination.node_latitude,
                destination_longitude=destination.node_longitude,
                departure_minute=rng.randint(start_minute, end_minute),
                origin_node=nearest_graph_node(graph, origin_latitude, origin_longitude),
                destination_node=destination.node_id,
            )
        )

    return demand


def demand_summary(
    demand: list[TripRequest],
    named_destinations: list[NamedGraphPoint] | None = None,
) -> dict[str, Any]:
    """Summarise a trip list for inspection and debugging.

    Parameters:
    - demand: The trip requests to summarise.
    - named_destinations: Optional snapped destinations to include in the summary output.

    Returns:
    - A plain dictionary containing trip counts, departure range, origin counts, destination counts,
      and a small sample of trips.

    Why this approach was chosen:
    - A plain JSON-friendly summary is easier to inspect from the CLI than a richer object model.
    """

    origins: dict[str, int] = {}
    destinations: dict[str, int] = {}
    departures = [trip.departure_minute for trip in demand]

    for trip in demand:
        origins[trip.origin_name] = origins.get(trip.origin_name, 0) + 1
        destinations[trip.destination_name] = destinations.get(trip.destination_name, 0) + 1

    return {
        "trip_count": len(demand),
        "departure_minute_range": [min(departures), max(departures)] if departures else [],
        "origin_counts": origins,
        "destination_counts": destinations,
        "named_destinations": [asdict(destination) for destination in named_destinations or []],
        "sample_trips": [asdict(trip) for trip in demand[:5]],
    }
