"""Canonical route artifacts and deterministic topology path construction."""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass

from urban_cybernetics.topology.canonical import (
    CanonicalTopology,
    CanonicalTopologyLink,
)


@dataclass(frozen=True, slots=True)
class CanonicalRoute:
    """Immutable route intent over canonical topology links."""

    route_id: str
    origin_node_id: str
    destination_node_id: str
    ordered_link_ids: tuple[str, ...]

    def validate_for_topology(self, topology: CanonicalTopology) -> bool:
        """Validate that this route is contiguous on the supplied topology."""

        _validate_route(self, topology)
        return True


def build_shortest_link_count_route(
    topology: CanonicalTopology,
    *,
    origin_node_id: str,
    destination_node_id: str,
) -> CanonicalRoute:
    """Build a deterministic breadth-first route over canonical directed links."""

    if origin_node_id == destination_node_id:
        raise ValueError("route origin and destination must differ")
    node_ids = {node.node_id for node in topology.nodes}
    if origin_node_id not in node_ids:
        raise KeyError(f"unknown route origin node_id: {origin_node_id}")
    if destination_node_id not in node_ids:
        raise KeyError(f"unknown route destination node_id: {destination_node_id}")

    links_by_id = _links_by_id(topology)
    outgoing_link_ids_by_node = {
        node.node_id: tuple(sorted(node.outgoing_link_ids)) for node in topology.nodes
    }
    queue: deque[tuple[str, tuple[str, ...]]] = deque([(origin_node_id, ())])
    visited_node_ids = {origin_node_id}

    while queue:
        node_id, path_link_ids = queue.popleft()
        for link_id in outgoing_link_ids_by_node.get(node_id, ()):
            link = links_by_id[link_id]
            next_path = (*path_link_ids, link_id)
            if link.head_node_id == destination_node_id:
                return _route_from_link_ids(
                    origin_node_id=origin_node_id,
                    destination_node_id=destination_node_id,
                    ordered_link_ids=next_path,
                    topology=topology,
                )
            if link.head_node_id in visited_node_ids:
                continue
            visited_node_ids.add(link.head_node_id)
            queue.append((link.head_node_id, next_path))

    raise ValueError(f"no directed path from {origin_node_id} to {destination_node_id}")


def _route_from_link_ids(
    *,
    origin_node_id: str,
    destination_node_id: str,
    ordered_link_ids: tuple[str, ...],
    topology: CanonicalTopology,
) -> CanonicalRoute:
    digest = hashlib.sha256(
        "|".join((topology.topology_hash, origin_node_id, destination_node_id, *ordered_link_ids)).encode(
            "utf-8"
        )
    ).hexdigest()[:12]
    route = CanonicalRoute(
        route_id=f"route:{origin_node_id}->{destination_node_id}:{digest}",
        origin_node_id=origin_node_id,
        destination_node_id=destination_node_id,
        ordered_link_ids=ordered_link_ids,
    )
    route.validate_for_topology(topology)
    return route


def _validate_route(route: CanonicalRoute, topology: CanonicalTopology) -> None:
    if not route.ordered_link_ids:
        raise ValueError(f"route {route.route_id} must contain at least one link")

    node_ids = {node.node_id for node in topology.nodes}
    if route.origin_node_id not in node_ids:
        raise KeyError(f"route {route.route_id} references unknown origin node")
    if route.destination_node_id not in node_ids:
        raise KeyError(f"route {route.route_id} references unknown destination node")

    links_by_id = _links_by_id(topology)
    route_links: list[CanonicalTopologyLink] = []
    for link_id in route.ordered_link_ids:
        try:
            route_links.append(links_by_id[link_id])
        except KeyError as exc:
            raise KeyError(f"route {route.route_id} references unknown link {link_id}") from exc

    if route_links[0].tail_node_id != route.origin_node_id:
        raise ValueError(f"route {route.route_id} does not start at its origin node")
    if route_links[-1].head_node_id != route.destination_node_id:
        raise ValueError(f"route {route.route_id} does not end at its destination node")

    for upstream, downstream in zip(route_links, route_links[1:]):
        if upstream.head_node_id != downstream.tail_node_id:
            raise ValueError(
                f"route {route.route_id} is not contiguous at "
                f"{upstream.link_id}->{downstream.link_id}"
            )


def _links_by_id(topology: CanonicalTopology) -> dict[str, CanonicalTopologyLink]:
    return {link.link_id: link for link in topology.links}
