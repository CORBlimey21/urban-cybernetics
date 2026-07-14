"""Presentation-only network layouts for the V application.

This module consumes immutable topology metadata. It is never imported by the
loading kernel and its coordinates never participate in physical calculations.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Mapping

from urban_cybernetics.topology import CanonicalTopology

from .contract import LayoutKind, LayoutOrigin, VNetworkLayout


SIOUX_FALLS_LAYOUT_ID = "sioux_falls_published_schematic_v1"
GENERATED_LAYOUT_ID = "uc_deterministic_layered_schematic_v1"
CIRCULAR_LAYOUT_ID = "uc_circular_fallback_v1"

# Visually reconstructed from the canonical benchmark diagram supplied for the
# V2 layout task. Connectivity continues to come solely from CanonicalTopology.
SIOUX_FALLS_SCHEMATIC_COORDINATES: dict[str, tuple[float, float]] = {
    "N001": (0.05, 0.04), "N002": (0.72, 0.04),
    "N003": (0.05, 0.17), "N004": (0.25, 0.17), "N005": (0.48, 0.17), "N006": (0.72, 0.17),
    "N009": (0.48, 0.29), "N008": (0.72, 0.29), "N007": (0.95, 0.29),
    "N012": (0.05, 0.42), "N011": (0.25, 0.42), "N010": (0.48, 0.42), "N016": (0.72, 0.42), "N018": (0.95, 0.42),
    "N017": (0.72, 0.54),
    "N014": (0.25, 0.67), "N015": (0.48, 0.67), "N019": (0.72, 0.67),
    "N023": (0.25, 0.79), "N022": (0.48, 0.79),
    "N013": (0.05, 0.95), "N024": (0.25, 0.95), "N021": (0.48, 0.95), "N020": (0.72, 0.95),
}


def layouts_for_topology(
    topology: CanonicalTopology,
    *,
    declared_positions: Mapping[str, tuple[float, float]] | None = None,
) -> tuple[str, tuple[VNetworkLayout, ...]]:
    """Return the preferred layout and deterministic alternatives."""

    layouts: list[VNetworkLayout] = []
    node_ids = {node.node_id for node in topology.nodes}
    if topology.topology_id == "sioux_falls_tntp_v1":
        if set(SIOUX_FALLS_SCHEMATIC_COORDINATES) != node_ids:
            raise ValueError("Sioux Falls schematic coordinates do not match canonical nodes")
        layouts.append(_sioux_falls_layout())
    elif declared_positions is not None:
        if set(declared_positions) != node_ids:
            raise ValueError("declared positions must cover each topology node exactly")
        layouts.append(_declared_layout(topology, declared_positions))

    layouts.extend((_generated_layout(topology), _circular_layout(topology)))
    default = select_default_layout(layouts)
    return default.layout_id, tuple(layouts)


def select_default_layout(layouts: list[VNetworkLayout] | tuple[VNetworkLayout, ...]) -> VNetworkLayout:
    """Apply stable declared/geographic/generated/circular precedence."""

    if not layouts:
        raise ValueError("at least one layout is required")
    precedence = {
        LayoutKind.DECLARED_SCHEMATIC: 0,
        LayoutKind.GEOGRAPHIC: 1,
        LayoutKind.GENERATED_SCHEMATIC: 2,
        LayoutKind.CIRCULAR_FALLBACK: 3,
    }
    return min(layouts, key=lambda layout: (not layout.preferred, precedence[layout.kind], layout.layout_id))


def deterministic_generated_positions(topology: CanonicalTopology, seed: int = 0) -> dict[str, tuple[float, float]]:
    """Create a stable layered schematic from undirected hop distance."""

    ordered = sorted(node.node_id for node in topology.nodes)
    if not ordered:
        return {}
    adjacency = {node_id: set() for node_id in ordered}
    for link in topology.links:
        adjacency[link.tail_node_id].add(link.head_node_id)
        adjacency[link.head_node_id].add(link.tail_node_id)
    start = ordered[seed % len(ordered)]
    distances = {start: 0}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for neighbour in sorted(adjacency[current]):
            if neighbour not in distances:
                distances[neighbour] = distances[current] + 1
                queue.append(neighbour)
    max_known = max(distances.values(), default=0)
    for node_id in ordered:
        distances.setdefault(node_id, max_known + 1)
    layers: dict[int, list[str]] = {}
    for node_id in ordered:
        layers.setdefault(distances[node_id], []).append(node_id)
    max_layer = max(layers, default=0)
    positions: dict[str, tuple[float, float]] = {}
    for layer, node_ids in sorted(layers.items()):
        x = 0.5 if max_layer == 0 else 0.08 + 0.84 * layer / max_layer
        for index, node_id in enumerate(node_ids):
            y = 0.5 if len(node_ids) == 1 else 0.08 + 0.84 * index / (len(node_ids) - 1)
            positions[node_id] = (round(x, 6), round(y, 6))
    return positions


def circular_positions(topology: CanonicalTopology) -> dict[str, tuple[float, float]]:
    ordered = sorted(node.node_id for node in topology.nodes)
    count = max(len(ordered), 1)
    return {
        node_id: (
            round(0.5 + 0.4 * math.cos((2 * math.pi * index / count) - math.pi / 2), 6),
            round(0.5 + 0.4 * math.sin((2 * math.pi * index / count) - math.pi / 2), 6),
        )
        for index, node_id in enumerate(ordered)
    }


def _sioux_falls_layout() -> VNetworkLayout:
    return VNetworkLayout(
        layout_id=SIOUX_FALLS_LAYOUT_ID,
        label="Published benchmark schematic",
        kind=LayoutKind.DECLARED_SCHEMATIC,
        version="1",
        preferred=True,
        is_geographic=False,
        coordinate_basis="normalised schematic canvas",
        coordinate_units="normalised [0,1]",
        source="Supplied canonical Sioux Falls benchmark diagram used as a visual placement reference",
        provenance="Visually reconstructed from the supplied diagram; UC TNTP topology remains connectivity truth.",
        origin=LayoutOrigin.DECLARED,
        node_coordinates=SIOUX_FALLS_SCHEMATIC_COORDINATES,
        warnings=("Non-geographic layout.", "Distances and angles are not physical."),
        distance_semantics="Screen distances have no physical meaning and do not encode link length.",
        angle_semantics="Screen angles are schematic and have no physical meaning.",
    )


def _declared_layout(topology: CanonicalTopology, positions: Mapping[str, tuple[float, float]]) -> VNetworkLayout:
    return VNetworkLayout(
        layout_id=f"{topology.topology_id}:declared_schematic_v1",
        label="Declared fixture schematic",
        kind=LayoutKind.DECLARED_SCHEMATIC,
        version="1",
        preferred=True,
        is_geographic=False,
        coordinate_basis="normalised schematic canvas",
        coordinate_units="normalised [0,1]",
        source="UC declared fixture layout",
        provenance="Declared alongside the visualisation fixture; detached from canonical topology identity.",
        origin=LayoutOrigin.DECLARED,
        node_coordinates=dict(positions),
        warnings=("Non-geographic layout.",),
        distance_semantics="Screen distances are presentation-only.",
        angle_semantics="Screen angles are presentation-only.",
    )


def _generated_layout(topology: CanonicalTopology) -> VNetworkLayout:
    return VNetworkLayout(
        layout_id=GENERATED_LAYOUT_ID,
        label="Auto schematic",
        kind=LayoutKind.GENERATED_SCHEMATIC,
        version="1",
        is_geographic=False,
        coordinate_basis="normalised deterministic hop layers",
        coordinate_units="normalised [0,1]",
        source="UC deterministic topology layout generator",
        provenance="Derived only from immutable node/link incidence for visual placement.",
        origin=LayoutOrigin.GENERATED,
        generated_by="urban_cybernetics.visualisation.layouts:hop_layers_v1",
        deterministic_seed=0,
        node_coordinates=deterministic_generated_positions(topology),
        warnings=("Generated non-geographic layout.",),
        distance_semantics="Layer spacing represents visual hop grouping, not physical distance.",
        angle_semantics="Screen angles are generated and non-physical.",
    )


def _circular_layout(topology: CanonicalTopology) -> VNetworkLayout:
    return VNetworkLayout(
        layout_id=CIRCULAR_LAYOUT_ID,
        label="Circular fallback",
        kind=LayoutKind.CIRCULAR_FALLBACK,
        version="1",
        is_geographic=False,
        coordinate_basis="normalised deterministic circle",
        coordinate_units="normalised [0,1]",
        source="UC circular fallback",
        provenance="Deterministic lexicographic node ordering; presentation fallback only.",
        origin=LayoutOrigin.GENERATED,
        generated_by="urban_cybernetics.visualisation.layouts:circular_v1",
        deterministic_seed=0,
        node_coordinates=circular_positions(topology),
        warnings=("Fallback non-geographic layout.",),
        distance_semantics="Screen distances are presentation-only.",
        angle_semantics="Equal angular spacing is presentation-only.",
    )
