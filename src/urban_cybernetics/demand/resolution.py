# SPDX-License-Identifier: MPL-2.0
"""Resolve OD demand declarations to canonical routes without mutating demand."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from urban_cybernetics.demand.manifest import DemandManifest
from urban_cybernetics.topology.canonical import CanonicalTopology
from urban_cybernetics.topology.routes import (
    CanonicalRoute,
    build_shortest_link_count_route,
)


@dataclass(frozen=True, slots=True)
class ResolvedDemandRoute:
    """A route resolution record for one raw OD demand declaration."""

    demand_id: str
    route: CanonicalRoute

    def hash_payload(self) -> dict[str, Any]:
        return {
            "demand_id": self.demand_id,
            "route_id": self.route.route_id,
            "origin_node_id": self.route.origin_node_id,
            "destination_node_id": self.route.destination_node_id,
            "ordered_link_ids": list(self.route.ordered_link_ids),
        }


@dataclass(frozen=True, slots=True)
class ResolvedDemandManifest:
    """A demand manifest plus a separate deterministic route mapping."""

    demand_manifest: DemandManifest
    resolved_routes: tuple[ResolvedDemandRoute, ...]
    route_resolution_method: str = "shortest_link_count_bfs"
    resolved_manifest_hash: str = ""

    def __post_init__(self) -> None:
        demand_ids = {
            declaration.demand_id
            for declaration in self.demand_manifest.declarations
        }
        resolved_ids = [resolved.demand_id for resolved in self.resolved_routes]
        if set(resolved_ids) != demand_ids:
            raise ValueError(
                "resolved routes must cover every demand declaration exactly once"
            )
        if len(resolved_ids) != len(set(resolved_ids)):
            raise ValueError("resolved demand_id values must be unique")
        object.__setattr__(self, "resolved_manifest_hash", self.compute_hash())

    @property
    def route_by_demand_id(self) -> dict[str, CanonicalRoute]:
        """Return a lookup from raw demand declaration ID to canonical route."""

        return {resolved.demand_id: resolved.route for resolved in self.resolved_routes}

    def compute_hash(self) -> str:
        """Return a stable hash over manifest hash and resolved route content."""

        payload = {
            "demand_manifest_hash": self.demand_manifest.manifest_hash,
            "route_resolution_method": self.route_resolution_method,
            "resolved_routes": [
                resolved.hash_payload()
                for resolved in sorted(
                    self.resolved_routes,
                    key=lambda item: item.demand_id,
                )
            ],
        }
        serialised = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def resolve_demand_routes(
    demand_manifest: DemandManifest,
    topology: CanonicalTopology,
) -> ResolvedDemandManifest:
    """Resolve OD demand with deterministic BFS routes over canonical topology."""

    if demand_manifest.topology_hash != topology.topology_hash:
        raise ValueError("demand manifest topology_hash does not match topology")
    demand_manifest.validate_for_topology_nodes({node.node_id for node in topology.nodes})

    resolved_routes = tuple(
        ResolvedDemandRoute(
            demand_id=declaration.demand_id,
            route=build_shortest_link_count_route(
                topology,
                origin_node_id=declaration.origin_node_id,
                destination_node_id=declaration.destination_node_id,
            ),
        )
        for declaration in demand_manifest.declarations
    )
    return ResolvedDemandManifest(
        demand_manifest=demand_manifest,
        resolved_routes=resolved_routes,
    )
