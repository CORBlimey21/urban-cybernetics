# SPDX-License-Identifier: MPL-2.0
"""Canonical topology artifacts and benchmark topology loaders."""

from .canonical import (
    CanonicalNode,
    CanonicalTopology,
    CanonicalTopologyLink,
    TopologySourceMetadata,
)
from .routes import CanonicalRoute, build_shortest_link_count_route
from .sioux_falls import (
    SIOUX_FALLS_INTERPRETATION_ASSUMPTIONS,
    load_sioux_falls_topology,
)
from .anaheim import ANAHEIM_INTERPRETATION_ASSUMPTIONS, load_anaheim_topology

__all__ = [
    "ANAHEIM_INTERPRETATION_ASSUMPTIONS",
    "CanonicalNode",
    "CanonicalRoute",
    "CanonicalTopology",
    "CanonicalTopologyLink",
    "SIOUX_FALLS_INTERPRETATION_ASSUMPTIONS",
    "TopologySourceMetadata",
    "build_shortest_link_count_route",
    "load_anaheim_topology",
    "load_sioux_falls_topology",
]
