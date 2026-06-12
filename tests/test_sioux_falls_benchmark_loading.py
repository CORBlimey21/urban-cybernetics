"""Sioux Falls canonical-route construction and loading smoke tests."""

from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import DemandDeclaration, EventType, LifecycleState
from urban_cybernetics.loading import LoadingEngine, packet_ids_on_link_from_events
from urban_cybernetics.topology import (
    CanonicalRoute,
    build_shortest_link_count_route,
    load_sioux_falls_topology,
)


class SiouxFallsBenchmarkLoadingTest(unittest.TestCase):
    def test_path_construction_produces_valid_benchmark_route(self) -> None:
        topology = load_sioux_falls_topology()
        route = self.sioux_falls_route()

        self.assertEqual(route.origin_node_id, "N001")
        self.assertEqual(route.destination_node_id, "N024")
        self.assertEqual(route.ordered_link_ids, ("L0002", "L0007", "L0037", "L0039"))
        self.assertTrue(route.validate_for_topology(topology))

    def test_route_artifact_is_immutable(self) -> None:
        route = self.sioux_falls_route()

        with self.assertRaises(FrozenInstanceError):
            route.ordered_link_ids = ()

    def test_route_validation_rejects_empty_route(self) -> None:
        topology = load_sioux_falls_topology()
        route = CanonicalRoute(
            route_id="empty",
            origin_node_id="N001",
            destination_node_id="N024",
            ordered_link_ids=(),
        )

        with self.assertRaises(ValueError):
            route.validate_for_topology(topology)

    def test_route_validation_rejects_inconsistent_origin(self) -> None:
        topology = load_sioux_falls_topology()
        route = replace(self.sioux_falls_route(), origin_node_id="N002")

        with self.assertRaises(ValueError):
            route.validate_for_topology(topology)

    def test_route_validation_rejects_inconsistent_destination(self) -> None:
        topology = load_sioux_falls_topology()
        route = replace(self.sioux_falls_route(), destination_node_id="N023")

        with self.assertRaises(ValueError):
            route.validate_for_topology(topology)

    def test_route_validation_rejects_non_contiguous_links(self) -> None:
        topology = load_sioux_falls_topology()
        route = CanonicalRoute(
            route_id="broken",
            origin_node_id="N001",
            destination_node_id="N024",
            ordered_link_ids=("L0002", "L0001", "L0039"),
        )

        with self.assertRaises(ValueError):
            route.validate_for_topology(topology)

    def test_path_construction_is_deterministic(self) -> None:
        first = self.sioux_falls_route()
        second = self.sioux_falls_route()

        self.assertEqual(first.route_id, second.route_id)
        self.assertEqual(first.ordered_link_ids, second.ordered_link_ids)

    def test_multi_link_benchmark_packet_completes(self) -> None:
        topology = load_sioux_falls_topology()
        route = self.sioux_falls_route()
        engine = self.loading_engine(topology)
        packet = engine.instantiate(
            DemandDeclaration(
                demand_id="D-benchmark",
                departure_tick=0,
                route_intent=route.ordered_link_ids,
            )
        )

        self.assertIsNotNone(packet)
        self.run_to_completion(engine)

        self.assertEqual(
            engine.packets[packet.packet_id].lifecycle_state,
            LifecycleState.COMPLETED,
        )
        self.assertEqual(self.realised_path(engine, packet.packet_id), route.ordered_link_ids)
        self.assertEqual(len(route.ordered_link_ids), 4)
        self.assert_packet_transfer_events_are_coherent(engine, packet.packet_id)
        self.assert_storage_matches_membership(engine, route.ordered_link_ids)
        self.assertTrue(engine.check_conservation())

    def test_multiple_packets_traverse_benchmark_route_fifo(self) -> None:
        topology = load_sioux_falls_topology()
        route = self.sioux_falls_route()
        engine = self.loading_engine(topology)
        packets = [
            engine.instantiate(
                DemandDeclaration(
                    demand_id=f"D-benchmark-{index}",
                    departure_tick=0,
                    route_intent=route.ordered_link_ids,
                )
            )
            for index in range(3)
        ]

        self.run_to_completion(engine)

        packet_ids = [packet.packet_id for packet in packets]
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_EXIT, route.ordered_link_ids[0]),
            packet_ids,
        )
        self.assertEqual(
            [
                packet.packet_id
                for packet in engine.packets.values()
                if packet.lifecycle_state == LifecycleState.COMPLETED
            ],
            packet_ids,
        )
        self.assertTrue(engine.check_conservation())

    def test_benchmark_spillback_queues_packet_on_upstream_link(self) -> None:
        topology = load_sioux_falls_topology()
        route = self.sioux_falls_route()
        loading_links = topology.as_loading_links(
            tick_duration_seconds=60.0,
            declared_storage_capacity_packets=1000,
        )
        first_link_id, second_link_id = route.ordered_link_ids[:2]
        loading_links[second_link_id] = replace(
            loading_links[second_link_id],
            free_flow_ticks=10,
            declared_storage_capacity_packets=1,
        )
        engine = LoadingEngine(links=loading_links, nodes=topology.as_loading_nodes())
        existing_packet = engine.instantiate(
            DemandDeclaration(
                demand_id="D-existing",
                departure_tick=0,
                route_intent=(second_link_id,),
            )
        )
        blocked_packet = engine.instantiate(
            DemandDeclaration(
                demand_id="D-blocked",
                departure_tick=0,
                route_intent=(first_link_id, second_link_id),
            )
        )

        self.run_until_tick(engine, 4)

        self.assertEqual(
            engine.packet_ids_in_queue(first_link_id, second_link_id),
            (blocked_packet.packet_id,),
        )
        self.assertEqual(engine.link_storage(first_link_id).storage, 1)
        self.assertEqual(engine.link_storage(second_link_id).storage, 1)
        self.assertEqual(
            packet_ids_on_link_from_events(engine.event_log, first_link_id, engine.current_tick),
            (blocked_packet.packet_id,),
        )

        self.run_to_completion(engine)

        self.assertEqual(
            engine.packets[existing_packet.packet_id].lifecycle_state,
            LifecycleState.COMPLETED,
        )
        self.assertEqual(
            engine.packets[blocked_packet.packet_id].lifecycle_state,
            LifecycleState.COMPLETED,
        )
        self.assertTrue(engine.check_conservation())

    def sioux_falls_route(self) -> CanonicalRoute:
        topology = load_sioux_falls_topology()
        return build_shortest_link_count_route(
            topology,
            origin_node_id="N001",
            destination_node_id="N024",
        )

    def loading_engine(self, topology) -> LoadingEngine:
        return LoadingEngine(
            links=topology.as_loading_links(
                tick_duration_seconds=60.0,
                declared_storage_capacity_packets=1000,
            ),
            nodes=topology.as_loading_nodes(),
        )

    def run_to_completion(self, engine: LoadingEngine, horizon: int = 100) -> None:
        for _ in range(horizon):
            if all(
                packet.lifecycle_state == LifecycleState.COMPLETED
                for packet in engine.packets.values()
            ):
                return
            engine.step()
        self.fail("benchmark packets did not complete within expected horizon")

    def run_until_tick(self, engine: LoadingEngine, tick: int) -> None:
        while engine.current_tick < tick:
            engine.step()

    def realised_path(self, engine: LoadingEngine, packet_id: str) -> tuple[str, ...]:
        return tuple(
            event.entity_id
            for event in engine.event_log
            if event.packet_id == packet_id and event.event_type == EventType.LINK_ENTRY
        )

    def assert_packet_transfer_events_are_coherent(
        self,
        engine: LoadingEngine,
        packet_id: str,
    ) -> None:
        packet_events = [
            event for event in engine.event_log if event.packet_id == packet_id
        ]
        for index, event in enumerate(packet_events):
            if event.event_type != EventType.LINK_EXIT:
                continue
            next_event = packet_events[index + 1]
            if next_event.event_type == EventType.COMPLETED:
                continue
            self.assertEqual(next_event.event_type, EventType.LINK_ENTRY)
            self.assertEqual(next_event.physical_tick, event.physical_tick)
            self.assertLess(event.sequence_number, next_event.sequence_number)

    def assert_storage_matches_membership(
        self,
        engine: LoadingEngine,
        link_ids: tuple[str, ...],
    ) -> None:
        for link_id in link_ids:
            for tick in range(engine.current_tick + 1):
                self.assertEqual(
                    engine.link_storage(link_id, tick).storage,
                    len(packet_ids_on_link_from_events(engine.event_log, link_id, tick)),
                )

    def link_event_packet_ids(
        self,
        engine: LoadingEngine,
        event_type: EventType,
        link_id: str,
    ) -> list[str]:
        return [
            event.packet_id
            for event in engine.event_log
            if event.event_type == event_type and event.entity_id == link_id
        ]


if __name__ == "__main__":
    unittest.main()
