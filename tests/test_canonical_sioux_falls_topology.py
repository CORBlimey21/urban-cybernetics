"""Canonical Sioux Falls topology artifact tests."""

from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.benchmarks.sioux_falls import SIOUX_FALLS_NET_PATH
from urban_cybernetics.core import Link
from urban_cybernetics.topology import (
    CanonicalNode,
    CanonicalTopology,
    CanonicalTopologyLink,
    SIOUX_FALLS_INTERPRETATION_ASSUMPTIONS,
    TopologySourceMetadata,
    load_sioux_falls_topology,
)


FORBIDDEN_DYNAMIC_FIELDS = (
    "current_occupancy",
    "current_density",
    "current_speed",
    "current_travel_time",
    "queue_length",
    "live_volume",
    "observed_flow",
)


class CanonicalSiouxFallsTopologyTest(unittest.TestCase):
    def test_sioux_falls_source_file_exists(self) -> None:
        self.assertTrue(SIOUX_FALLS_NET_PATH.exists())

    def test_loader_parses_real_sioux_falls_topology(self) -> None:
        topology = load_sioux_falls_topology()

        self.assertEqual(len(topology.nodes), 24)
        self.assertEqual(len(topology.links), 76)
        self.assertEqual(topology.source_metadata.source_name, "Sioux Falls")
        self.assertEqual(topology.source_metadata.source_format, "TNTP network")
        self.assertIn(
            "TNTP Sioux Falls length values are interpreted as miles for this benchmark topology.",
            topology.interpretation_assumptions,
        )
        self.assertTrue(topology.validate())

    def test_canonical_ids_are_deterministic_and_external_ids_are_provenance(self) -> None:
        first = load_sioux_falls_topology()
        second = load_sioux_falls_topology()

        self.assertEqual(
            [node.node_id for node in first.nodes],
            [node.node_id for node in second.nodes],
        )
        self.assertEqual(
            [link.link_id for link in first.links],
            [link.link_id for link in second.links],
        )
        self.assertEqual(first.nodes[0].node_id, "N001")
        self.assertEqual(first.nodes[0].source_node_id, "1")
        self.assertNotEqual(first.nodes[0].node_id, first.nodes[0].source_node_id)

        first_link = first.links[0]
        self.assertEqual(first_link.link_id, "L0001")
        self.assertEqual(first_link.source_link_id, "1->2")
        self.assertEqual(first_link.source_tail_node_id, "1")
        self.assertEqual(first_link.source_head_node_id, "2")
        self.assertNotEqual(first_link.link_id, first_link.source_link_id)

    def test_directed_connectivity_is_preserved(self) -> None:
        topology = load_sioux_falls_topology()
        first_link = topology.links[0]
        tail_node = self.node_by_id(topology, first_link.tail_node_id)
        head_node = self.node_by_id(topology, first_link.head_node_id)

        self.assertIn(first_link.link_id, tail_node.outgoing_link_ids)
        self.assertIn(first_link.link_id, head_node.incoming_link_ids)
        self.assertNotIn(first_link.link_id, tail_node.incoming_link_ids)

    def test_topology_hash_is_deterministic(self) -> None:
        first = load_sioux_falls_topology()
        second = load_sioux_falls_topology()

        self.assertEqual(first.topology_hash, second.topology_hash)
        self.assertEqual(first.topology_hash, first.compute_hash())

    def test_topology_hash_changes_when_static_link_metadata_changes(self) -> None:
        topology = load_sioux_falls_topology()
        edited_first_link = replace(
            topology.links[0],
            capacity_veh_per_hour_per_lane=(
                topology.links[0].capacity_veh_per_hour_per_lane + 1.0
            ),
        )
        edited_topology = CanonicalTopology(
            topology_id=topology.topology_id,
            nodes=topology.nodes,
            links=(edited_first_link, *topology.links[1:]),
            source_metadata=topology.source_metadata,
            interpretation_assumptions=topology.interpretation_assumptions,
        )

        self.assertNotEqual(topology.topology_hash, edited_topology.topology_hash)

    def test_topology_hash_changes_when_interpretation_assumptions_change(self) -> None:
        topology = load_sioux_falls_topology()
        edited_topology = CanonicalTopology(
            topology_id=topology.topology_id,
            nodes=topology.nodes,
            links=topology.links,
            source_metadata=topology.source_metadata,
            interpretation_assumptions=(
                *SIOUX_FALLS_INTERPRETATION_ASSUMPTIONS,
                "test-only altered interpretation",
            ),
        )

        self.assertNotEqual(topology.topology_hash, edited_topology.topology_hash)

    def test_validation_rejects_duplicate_node_ids(self) -> None:
        with self.assertRaises(ValueError):
            self.tiny_topology(
                nodes=(
                    CanonicalNode("N001", "1", outgoing_link_ids=("L0001",)),
                    CanonicalNode("N001", "2", incoming_link_ids=("L0001",)),
                ),
                links=(self.tiny_link(),),
            )

    def test_validation_rejects_duplicate_link_ids(self) -> None:
        with self.assertRaises(ValueError):
            self.tiny_topology(
                links=(
                    self.tiny_link(),
                    replace(
                        self.tiny_link(),
                        source_link_id="2->1",
                        tail_node_id="N002",
                        head_node_id="N001",
                        source_tail_node_id="2",
                        source_head_node_id="1",
                    ),
                )
            )

    def test_validation_rejects_links_referencing_missing_nodes(self) -> None:
        with self.assertRaises(ValueError):
            self.tiny_topology(
                links=(
                    replace(
                        self.tiny_link(),
                        head_node_id="N999",
                    ),
                )
            )

    def test_topology_records_are_immutable(self) -> None:
        topology = load_sioux_falls_topology()

        with self.assertRaises(FrozenInstanceError):
            topology.topology_id = "changed"
        with self.assertRaises(FrozenInstanceError):
            topology.nodes[0].node_id = "changed"
        with self.assertRaises(FrozenInstanceError):
            topology.links[0].length_m = 1.0

    def test_topology_records_do_not_expose_dynamic_fields(self) -> None:
        topology = load_sioux_falls_topology()

        for record in (topology, topology.nodes[0], topology.links[0]):
            for field_name in FORBIDDEN_DYNAMIC_FIELDS:
                self.assertFalse(hasattr(record, field_name), field_name)

    def test_l1_loading_link_mapping_preserves_static_metadata(self) -> None:
        topology = load_sioux_falls_topology()
        canonical_link = topology.links[0]

        loading_links = topology.as_loading_links(
            tick_duration_seconds=60.0,
            declared_storage_capacity_packets=500,
        )
        loading_link = loading_links[canonical_link.link_id]

        self.assertIsInstance(loading_link, Link)
        self.assertEqual(loading_link.link_id, canonical_link.link_id)
        self.assertEqual(loading_link.length_m, canonical_link.length_m)
        self.assertEqual(loading_link.lane_count, canonical_link.lane_count)
        self.assertEqual(
            loading_link.free_flow_speed_mps,
            canonical_link.free_flow_speed_mps,
        )
        self.assertEqual(
            loading_link.capacity_veh_per_hour_per_lane,
            canonical_link.capacity_veh_per_hour_per_lane,
        )
        self.assertEqual(loading_link.declared_storage_capacity_packets, 500)
        self.assertEqual(loading_link.free_flow_ticks, 6)

    def node_by_id(self, topology: CanonicalTopology, node_id: str):
        for node in topology.nodes:
            if node.node_id == node_id:
                return node
        self.fail(f"missing node {node_id}")

    def tiny_topology(
        self,
        *,
        nodes: tuple[CanonicalNode, ...] | None = None,
        links: tuple[CanonicalTopologyLink, ...] | None = None,
    ) -> CanonicalTopology:
        return CanonicalTopology(
            topology_id="tiny",
            nodes=nodes
            or (
                CanonicalNode("N001", "1", outgoing_link_ids=("L0001",)),
                CanonicalNode("N002", "2", incoming_link_ids=("L0001",)),
            ),
            links=links or (self.tiny_link(),),
            source_metadata=TopologySourceMetadata(
                source_name="tiny",
                source_format="fixture",
                source_file_path="tests",
                source_file_sha256="fixture",
            ),
            interpretation_assumptions=("fixture units",),
        )

    def tiny_link(self) -> CanonicalTopologyLink:
        return CanonicalTopologyLink(
            link_id="L0001",
            tail_node_id="N001",
            head_node_id="N002",
            source_link_id="1->2",
            source_tail_node_id="1",
            source_head_node_id="2",
            length_m=100.0,
            lane_count=1,
            free_flow_speed_mps=10.0,
            capacity_veh_per_hour_per_lane=1000.0,
        )


if __name__ == "__main__":
    unittest.main()
