from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from urban_cybernetics.topology import load_sioux_falls_topology
from urban_cybernetics.visualisation.contract import (
    LayoutKind,
    LayoutOrigin,
    VNetworkLayout,
    VRunBundle,
)
from urban_cybernetics.visualisation.fixtures import build_synthetic_fixture
from urban_cybernetics.visualisation.layouts import (
    CIRCULAR_LAYOUT_ID,
    GENERATED_LAYOUT_ID,
    SIOUX_FALLS_LAYOUT_ID,
    SIOUX_FALLS_SCHEMATIC_COORDINATES,
    deterministic_generated_positions,
    layouts_for_topology,
)


def test_sioux_falls_layouts_are_complete_unique_and_prefer_published_schematic() -> None:
    topology = load_sioux_falls_topology()
    topology_hash_before = topology.topology_hash
    default_id, layouts = layouts_for_topology(topology)

    assert default_id == SIOUX_FALLS_LAYOUT_ID
    assert [layout.layout_id for layout in layouts] == [
        SIOUX_FALLS_LAYOUT_ID,
        GENERATED_LAYOUT_ID,
        CIRCULAR_LAYOUT_ID,
    ]
    assert len({layout.layout_id for layout in layouts}) == len(layouts)
    expected_nodes = {node.node_id for node in topology.nodes}
    assert set(SIOUX_FALLS_SCHEMATIC_COORDINATES) == expected_nodes
    assert all(set(layout.node_coordinates) == expected_nodes for layout in layouts)
    assert topology.topology_hash == topology_hash_before


def test_generated_layout_is_deterministic_and_declares_nonphysical_semantics() -> None:
    topology = load_sioux_falls_topology()
    first = deterministic_generated_positions(topology, seed=0)
    assert first == deterministic_generated_positions(topology, seed=0)
    _, layouts = layouts_for_topology(topology)
    generated = next(layout for layout in layouts if layout.layout_id == GENERATED_LAYOUT_ID)
    assert generated.origin == LayoutOrigin.GENERATED
    assert generated.deterministic_seed == 0
    assert not generated.is_geographic
    assert "not physical" in generated.distance_semantics


def test_geographic_and_generated_metadata_validation_is_explicit() -> None:
    common = {
        "layout_id": "geo-v1",
        "label": "Geographic",
        "kind": LayoutKind.GEOGRAPHIC,
        "version": "1",
        "is_geographic": True,
        "coordinate_basis": "projected planar",
        "coordinate_units": "metres",
        "source": "test",
        "provenance": "test",
        "origin": LayoutOrigin.IMPORTED,
        "node_coordinates": {"N1": (0.0, 0.0)},
        "distance_semantics": "Projected coordinate distances may be meaningful only under the declared CRS.",
        "angle_semantics": "Angles follow the declared projection.",
    }
    with pytest.raises(ValidationError, match="declare a CRS"):
        VNetworkLayout(**common)
    assert VNetworkLayout(**common, crs="EPSG:2157").crs == "EPSG:2157"

    with pytest.raises(ValidationError, match="deterministic seed"):
        VNetworkLayout(
            **{**common, "layout_id": "generated-v1", "kind": LayoutKind.GENERATED_SCHEMATIC,
               "is_geographic": False, "crs": None, "origin": LayoutOrigin.GENERATED,
               "generated_by": "test-generator"}
        )


def test_contract_rejects_missing_or_extra_layout_nodes_without_changing_evidence() -> None:
    bundle = build_synthetic_fixture()
    baseline_events = bundle.event_stream
    baseline_replay = bundle.replay_states
    baseline_validation = bundle.validation
    baseline_topology_hash = bundle.topology.topology_hash
    payload = bundle.model_dump(mode="python")
    coordinates = copy.deepcopy(payload["presentation"]["layouts"][0]["node_coordinates"])
    coordinates.pop(next(iter(coordinates)))
    coordinates["N-extra"] = (0.5, 0.5)
    payload["presentation"]["layouts"][0]["node_coordinates"] = coordinates
    payload["presentation"]["node_positions"] = coordinates

    with pytest.raises(ValidationError, match="cover each topology node exactly"):
        VRunBundle.model_validate(payload)
    assert bundle.event_stream == baseline_events
    assert bundle.replay_states == baseline_replay
    assert bundle.validation == baseline_validation
    assert bundle.topology.topology_hash == baseline_topology_hash


def test_contract_rejects_duplicate_layout_ids_and_nonfinite_coordinates() -> None:
    bundle = build_synthetic_fixture()
    payload = bundle.model_dump(mode="python")
    payload["presentation"]["layouts"] = [
        payload["presentation"]["layouts"][0],
        payload["presentation"]["layouts"][0],
    ]
    with pytest.raises(ValidationError, match="layout IDs must be unique"):
        VRunBundle.model_validate(payload)

    layout = bundle.presentation.layouts[0].model_dump(mode="python")
    layout["node_coordinates"][next(iter(layout["node_coordinates"]))] = (float("nan"), 0.0)
    with pytest.raises(ValidationError, match="coordinates must be finite"):
        VNetworkLayout.model_validate(layout)
