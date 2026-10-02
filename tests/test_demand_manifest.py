# SPDX-License-Identifier: MPL-2.0
"""D1 pre-packet demand, route resolution, and scheduled loading tests."""

from __future__ import annotations

import sys
import tempfile
import unittest
from collections import Counter
from dataclasses import FrozenInstanceError, replace
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.benchmarks.sioux_falls import SIOUX_FALLS_TRIPS_PATH
from urban_cybernetics.core import DemandDeclaration as LoadingDemandDeclaration
from urban_cybernetics.demand import (
    DemandManifest,
    DemandManifestSourceMetadata,
    FixedDepartureSchedule,
    GlobalUniformDepartureSchedule,
    ODDemandDeclaration,
    ScheduledDemandLoader,
    UniformWindowDepartureSchedule,
    load_sioux_falls_demand_manifest,
    resolve_demand_routes,
)
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.topology import load_sioux_falls_topology


FORBIDDEN_TOPOLOGY_DEMAND_FIELDS = (
    "demand",
    "od_demand",
    "trips",
    "scheduled_departures",
    "live_od_counts",
    "quantity_packets",
)


class DemandManifestTest(unittest.TestCase):
    def test_demand_declarations_and_manifests_are_immutable(self) -> None:
        declaration = self.raw_declaration()
        manifest = self.manifest(declaration)

        with self.assertRaises(FrozenInstanceError):
            declaration.quantity_packets = 99
        with self.assertRaises(FrozenInstanceError):
            manifest.manifest_id = "changed"

    def test_fixed_departure_schedule_expands_to_expected_ticks(self) -> None:
        schedule = FixedDepartureSchedule(departure_tick=5)

        self.assertEqual(schedule.expand_departure_ticks(4), (5, 5, 5, 5))

    def test_uniform_window_schedule_expands_deterministically(self) -> None:
        schedule = UniformWindowDepartureSchedule(start_tick=2, end_tick=4)

        self.assertEqual(schedule.expand_departure_ticks(8), (2, 2, 2, 3, 3, 3, 4, 4))

    def test_global_uniform_schedule_uses_full_manifest_window(self) -> None:
        topology = load_sioux_falls_topology()
        schedule = GlobalUniformDepartureSchedule(start_tick=0, end_tick=9)
        manifest = self.manifest(
            self.raw_declaration(
                demand_id="D-OD-1",
                origin_node_id="N001",
                destination_node_id="N002",
                quantity_packets=10,
                departure_schedule=schedule,
            ),
            self.raw_declaration(
                demand_id="D-OD-2",
                origin_node_id="N001",
                destination_node_id="N002",
                quantity_packets=10,
                departure_schedule=schedule,
            ),
            self.raw_declaration(
                demand_id="D-OD-3",
                origin_node_id="N001",
                destination_node_id="N002",
                quantity_packets=10,
                departure_schedule=schedule,
            ),
            topology_id=topology.topology_id,
            topology_hash=topology.topology_hash,
        )
        resolved = resolve_demand_routes(manifest, topology)
        loader = ScheduledDemandLoader(resolved)

        departure_counts = Counter(
            request.departure_tick for request in loader.scheduled_requests
        )

        self.assertIn(0, departure_counts)
        self.assertIn(5, departure_counts)
        self.assertIn(9, departure_counts)
        self.assertEqual(len(departure_counts), 10)
        self.assertEqual(set(departure_counts.values()), {3})

    def test_global_uniform_schedule_balances_departure_counts(self) -> None:
        topology = load_sioux_falls_topology()
        schedule = GlobalUniformDepartureSchedule(start_tick=2, end_tick=6)
        manifest = self.manifest(
            self.raw_declaration(
                demand_id="D-OD-1",
                origin_node_id="N001",
                destination_node_id="N002",
                quantity_packets=8,
                departure_schedule=schedule,
            ),
            self.raw_declaration(
                demand_id="D-OD-2",
                origin_node_id="N001",
                destination_node_id="N002",
                quantity_packets=7,
                departure_schedule=schedule,
            ),
            self.raw_declaration(
                demand_id="D-OD-3",
                origin_node_id="N001",
                destination_node_id="N002",
                quantity_packets=8,
                departure_schedule=schedule,
            ),
            topology_id=topology.topology_id,
            topology_hash=topology.topology_hash,
        )
        resolved = resolve_demand_routes(manifest, topology)
        loader = ScheduledDemandLoader(resolved)

        departure_counts = Counter(
            request.departure_tick for request in loader.scheduled_requests
        )

        self.assertEqual(set(departure_counts), {2, 3, 4, 5, 6})
        self.assertLessEqual(
            max(departure_counts.values()) - min(departure_counts.values()),
            1,
        )
        self.assertEqual(sum(departure_counts.values()), 23)

    def test_declaration_uniform_schedule_remains_per_declaration(self) -> None:
        topology = load_sioux_falls_topology()
        schedule = UniformWindowDepartureSchedule(start_tick=0, end_tick=4)
        manifest = self.manifest(
            self.raw_declaration(
                demand_id="D-OD-1",
                origin_node_id="N001",
                destination_node_id="N002",
                quantity_packets=2,
                departure_schedule=schedule,
            ),
            self.raw_declaration(
                demand_id="D-OD-2",
                origin_node_id="N001",
                destination_node_id="N002",
                quantity_packets=2,
                departure_schedule=schedule,
            ),
            topology_id=topology.topology_id,
            topology_hash=topology.topology_hash,
        )
        resolved = resolve_demand_routes(manifest, topology)
        loader = ScheduledDemandLoader(resolved)

        self.assertEqual(
            tuple(request.departure_tick for request in loader.scheduled_requests),
            (0, 0, 1, 1),
        )

    def test_manifest_hash_is_deterministic_and_content_sensitive(self) -> None:
        declaration = self.raw_declaration(quantity_packets=2)
        manifest = self.manifest(declaration)
        reordered_metadata_manifest = self.manifest(
            replace(
                declaration,
                source_metadata_items=(("b", "2"), ("a", "1")),
            )
        )
        changed_quantity_manifest = self.manifest(
            replace(declaration, quantity_packets=3)
        )
        changed_schedule_manifest = self.manifest(
            replace(
                declaration,
                departure_schedule=UniformWindowDepartureSchedule(0, 1),
            )
        )
        changed_source_manifest = DemandManifest(
            manifest_id=manifest.manifest_id,
            topology_id=manifest.topology_id,
            topology_hash=manifest.topology_hash,
            declarations=manifest.declarations,
            source_metadata=DemandManifestSourceMetadata(
                source_name="fixture",
                source_format="fixture",
                interpretation_assumptions=("changed",),
            ),
        )

        self.assertEqual(manifest.manifest_hash, manifest.compute_hash())
        self.assertEqual(manifest.manifest_hash, reordered_metadata_manifest.manifest_hash)
        self.assertNotEqual(manifest.manifest_hash, changed_quantity_manifest.manifest_hash)
        self.assertNotEqual(manifest.manifest_hash, changed_schedule_manifest.manifest_hash)
        self.assertNotEqual(manifest.manifest_hash, changed_source_manifest.manifest_hash)

    def test_sioux_falls_od_loader_parses_real_or_fixture_matrix(self) -> None:
        topology = load_sioux_falls_topology()
        if SIOUX_FALLS_TRIPS_PATH.exists():
            manifest = load_sioux_falls_demand_manifest(
                topology=topology,
                scale_factor=0.01,
                max_pairs=3,
            )
            source_path = str(SIOUX_FALLS_TRIPS_PATH)
        else:
            with tempfile.TemporaryDirectory() as temp_dir:
                trips_path = Path(temp_dir) / "tiny_trips.tntp"
                trips_path.write_text(
                    "\n".join(
                        [
                            "<NUMBER OF ZONES> 2",
                            "<TOTAL OD FLOW> 100.0",
                            "<END OF METADATA>",
                            "Origin 1",
                            "1 : 0.0; 2 : 100.0;",
                            "Origin 2",
                            "1 : 0.0; 2 : 0.0;",
                        ]
                    ),
                    encoding="utf-8",
                )
                manifest = load_sioux_falls_demand_manifest(
                    topology=topology,
                    trips_path=trips_path,
                    scale_factor=0.01,
                )
                source_path = str(trips_path)

        self.assertGreater(len(manifest.declarations), 0)
        self.assertGreater(manifest.total_declared_quantity_packets, 0)
        self.assertEqual(manifest.manifest_hash, manifest.compute_hash())
        self.assertEqual(manifest.source_metadata.source_file_path, source_path)

        first_declaration = manifest.declarations[0]
        canonical_node_ids = {node.node_id for node in topology.nodes}
        self.assertIn(first_declaration.origin_node_id, canonical_node_ids)
        self.assertIn(first_declaration.destination_node_id, canonical_node_ids)
        self.assertIsNotNone(first_declaration.source_origin_zone_id)
        self.assertIsNotNone(first_declaration.source_destination_zone_id)

    def test_route_resolution_keeps_routes_separate_from_raw_demand(self) -> None:
        topology = load_sioux_falls_topology()
        manifest = self.manifest(
            self.raw_declaration(origin_node_id="N001", destination_node_id="N024"),
            topology_id=topology.topology_id,
            topology_hash=topology.topology_hash,
        )

        resolved = resolve_demand_routes(manifest, topology)

        self.assertFalse(hasattr(manifest.declarations[0], "route_intent"))
        self.assertFalse(hasattr(manifest.declarations[0], "route_id"))
        self.assertEqual(len(resolved.resolved_routes), 1)
        self.assertEqual(resolved.resolved_routes[0].demand_id, "D-OD")
        self.assertGreater(len(resolved.resolved_routes[0].route.ordered_link_ids), 0)
        self.assertEqual(resolved.resolved_manifest_hash, resolved.compute_hash())

    def test_scheduled_loading_realises_small_sioux_falls_demand(self) -> None:
        topology = load_sioux_falls_topology()
        manifest = load_sioux_falls_demand_manifest(
            topology=topology,
            scale_factor=0.01,
            max_pairs=1,
            departure_schedule=FixedDepartureSchedule(0),
        )
        resolved = resolve_demand_routes(manifest, topology)
        loader = ScheduledDemandLoader(resolved)
        engine = LoadingEngine(
            links=topology.as_loading_links(
                tick_duration_seconds=60.0,
                declared_storage_capacity_packets=1000,
            ),
            nodes=topology.as_loading_nodes(),
        )

        admitted_packets = loader.submit_due_departures(engine)

        self.assertGreaterEqual(len(admitted_packets), 1)
        self.assertEqual(len(engine.packets), len(admitted_packets))
        self.run_to_completion(engine)
        self.assertTrue(engine.check_conservation())

    def test_origin_blocked_demand_remains_pending_until_loading_admits_it(self) -> None:
        topology = load_sioux_falls_topology()
        route_manifest = self.manifest(
            self.raw_declaration(
                demand_id="D-blocked-od",
                origin_node_id="N001",
                destination_node_id="N002",
                quantity_packets=1,
            ),
            topology_id=topology.topology_id,
            topology_hash=topology.topology_hash,
        )
        resolved = resolve_demand_routes(route_manifest, topology)
        route = resolved.resolved_routes[0].route
        loading_links = topology.as_loading_links(
            tick_duration_seconds=60.0,
            declared_storage_capacity_packets=1000,
        )
        first_link_id = route.ordered_link_ids[0]
        loading_links[first_link_id] = replace(
            loading_links[first_link_id],
            free_flow_ticks=1,
            declared_storage_capacity_packets=1,
        )
        engine = LoadingEngine(links=loading_links, nodes=topology.as_loading_nodes())
        loader = ScheduledDemandLoader(resolved)
        existing_packet = engine.instantiate(
            LoadingDemandDeclaration(
                demand_id="D-existing-loading-request",
                departure_tick=0,
                route_intent=(first_link_id,),
            )
        )

        admitted_packets = loader.submit_due_departures(engine)

        self.assertEqual(admitted_packets, ())
        self.assertEqual(len(engine.packets), 1)
        self.assertEqual(tuple(engine.packets), (existing_packet.packet_id,))
        self.assertEqual(len(engine.pending_demands), 1)
        self.assertEqual(engine.pending_demands[0].demand_id, "D-blocked-od:unit:000001")

        engine.step()
        self.assertEqual(len(engine.packets), 1)
        self.assertEqual(len(engine.pending_demands), 1)

        engine.step()
        self.assertEqual(len(engine.packets), 2)
        self.assertEqual(len(engine.pending_demands), 0)

    def test_topology_records_do_not_contain_demand_fields(self) -> None:
        topology = load_sioux_falls_topology()

        for record in (topology, topology.nodes[0], topology.links[0]):
            for field_name in FORBIDDEN_TOPOLOGY_DEMAND_FIELDS:
                self.assertFalse(hasattr(record, field_name), field_name)

    def test_raw_demand_does_not_create_packet_ids(self) -> None:
        topology = load_sioux_falls_topology()
        declaration = self.raw_declaration(
            origin_node_id="N001",
            destination_node_id="N024",
            quantity_packets=1,
        )
        manifest = self.manifest(
            declaration,
            topology_id=topology.topology_id,
            topology_hash=topology.topology_hash,
        )
        resolved = resolve_demand_routes(manifest, topology)
        loader = ScheduledDemandLoader(resolved)
        engine = LoadingEngine(
            links=topology.as_loading_links(
                tick_duration_seconds=60.0,
                declared_storage_capacity_packets=1000,
            ),
            nodes=topology.as_loading_nodes(),
        )

        self.assertFalse(hasattr(declaration, "packet_id"))
        self.assertEqual(engine.packets, {})

        admitted_packets = loader.submit_due_departures(engine)

        self.assertEqual(len(admitted_packets), 1)
        self.assertEqual(admitted_packets[0].packet_id, "P1")

    def raw_declaration(
        self,
        *,
        demand_id: str = "D-OD",
        origin_node_id: str = "N001",
        destination_node_id: str = "N002",
        quantity_packets: int = 1,
        departure_schedule=None,
    ) -> ODDemandDeclaration:
        return ODDemandDeclaration(
            demand_id=demand_id,
            origin_node_id=origin_node_id,
            destination_node_id=destination_node_id,
            quantity_packets=quantity_packets,
            departure_schedule=departure_schedule
            or FixedDepartureSchedule(departure_tick=0),
            cohort_id="cohort:test",
            authority_id="authority:test",
            source_origin_zone_id="1",
            source_destination_zone_id="2",
            source_quantity_value=100.0,
            source_metadata_items=(("a", "1"), ("b", "2")),
        )

    def manifest(
        self,
        *declarations: ODDemandDeclaration,
        topology_id: str = "topology:test",
        topology_hash: str = "hash:test",
    ) -> DemandManifest:
        return DemandManifest(
            manifest_id="manifest:test",
            topology_id=topology_id,
            topology_hash=topology_hash,
            declarations=tuple(declarations),
            source_metadata=DemandManifestSourceMetadata(
                source_name="fixture",
                source_format="fixture",
                interpretation_assumptions=("unit packets",),
                scaling_assumptions=("none",),
            ),
        )

    def run_to_completion(self, engine: LoadingEngine, horizon: int = 100) -> None:
        for _ in range(horizon):
            if engine.packets and all(
                packet.lifecycle_state.name == "COMPLETED"
                for packet in engine.packets.values()
            ):
                return
            engine.step()
        self.fail("scheduled demand packets did not complete within expected horizon")


if __name__ == "__main__":
    unittest.main()
