"""Synthetic system validation for the packetised LTM-style loading kernel."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import (
    DemandDeclaration,
    Event,
    EventType,
    LifecycleState,
    Link,
    Node,
    Packet,
)
from urban_cybernetics.loading import LoadingEngine, packet_ids_on_link_from_events


class SyntheticLTMValidationSuiteTest(unittest.TestCase):
    def test_single_link_free_flow_validation(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(
                    link_id="L1",
                    free_flow_ticks=2,
                    declared_sending_capacity_per_tick=2,
                )
            }
        )
        packets = [
            engine.instantiate(
                DemandDeclaration(
                    demand_id=f"D{demand_number}",
                    departure_tick=0,
                    route_intent=("L1",),
                )
            )
            for demand_number in range(3)
        ]

        self.assertEqual(
            self.link_entry_packet_ids(engine, "L1", 0),
            self.packet_ids(packets),
        )
        self.assertEqual(engine.link_storage("L1", 0).storage, 3)

        engine.step()

        self.assertEqual(engine.current_tick, 1)
        self.assertEqual(self.link_exit_packet_ids(engine, "L1", 1), [])
        self.assertEqual(engine.link_storage("L1", 1).storage, 3)

        engine.step()

        self.assertEqual(self.link_exit_packet_ids(engine, "L1", 2), ["P1", "P2"])
        self.assertEqual(self.completed_packet_ids(engine, 2), ["P1", "P2"])
        self.assertEqual(engine.link_storage("L1", 2).storage, 1)

        engine.step()

        self.assertEqual(self.link_exit_packet_ids(engine, "L1", 3), ["P3"])
        self.assertEqual(self.completed_packet_ids(engine, 3), ["P3"])
        self.assertEqual(engine.link_storage("L1", 3).storage, 0)
        self.assert_per_tick_event_count_at_most(engine, EventType.LINK_EXIT, "L1", 2)
        self.assert_per_tick_event_count_at_most(engine, EventType.COMPLETED, "L1", 2)
        self.assert_synthetic_kernel_consistent(engine, ("L1",))

    def test_sending_capacity_bottleneck_validation(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(
                    link_id="L1",
                    free_flow_ticks=1,
                    declared_sending_capacity_per_tick=1,
                )
            }
        )
        packets = [
            engine.instantiate(
                DemandDeclaration(
                    demand_id=f"D{demand_number}",
                    departure_tick=0,
                    route_intent=("L1",),
                )
            )
            for demand_number in range(4)
        ]

        storage_by_tick = [engine.link_storage("L1", 0).storage]
        while any(
            packet.lifecycle_state != LifecycleState.COMPLETED
            for packet in engine.packets.values()
        ):
            engine.step()
            storage_by_tick.append(engine.link_storage("L1").storage)

        self.assertEqual(
            [
                event.packet_id
                for event in self.link_events(engine, EventType.LINK_EXIT, "L1")
            ],
            self.packet_ids(packets),
        )
        self.assert_per_tick_event_count_at_most(engine, EventType.LINK_EXIT, "L1", 1)
        self.assert_per_tick_event_count_at_most(engine, EventType.COMPLETED, "L1", 1)
        for previous_storage, next_storage in zip(storage_by_tick, storage_by_tick[1:]):
            self.assertLessEqual(previous_storage - next_storage, 1)
        self.assert_synthetic_kernel_consistent(engine, ("L1",))

    def test_receiving_capacity_bottleneck_validation(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(
                    link_id="L1",
                    free_flow_ticks=1,
                    declared_sending_capacity_per_tick=5,
                ),
                "L2": Link(
                    link_id="L2",
                    free_flow_ticks=1,
                    declared_sending_capacity_per_tick=5,
                    declared_receiving_capacity_per_tick=1,
                    declared_storage_capacity_packets=10,
                ),
            }
        )
        packets = [
            engine.instantiate(
                DemandDeclaration(
                    demand_id=f"D{demand_number}",
                    departure_tick=0,
                    route_intent=("L1", "L2"),
                )
            )
            for demand_number in range(3)
        ]

        engine.step()

        self.assertEqual(self.link_entry_packet_ids(engine, "L2", 1), ["P1"])
        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), ("P2", "P3"))
        self.assertEqual(
            packet_ids_on_link_from_events(engine.event_log, "L1", 1),
            ("P2", "P3"),
        )
        self.assert_link_exit_entry_pair_for_transfers(engine, "L1", "L2")

        self.run_to_completion(engine)

        self.assertEqual(
            [
                event.packet_id
                for event in self.link_events(engine, EventType.LINK_ENTRY, "L2")
            ],
            self.packet_ids(packets),
        )
        self.assert_per_tick_event_count_at_most(engine, EventType.LINK_ENTRY, "L2", 1)
        self.assert_link_exit_entry_pair_for_transfers(engine, "L1", "L2")
        self.assert_synthetic_kernel_consistent(engine, ("L1", "L2"))

    def test_storage_spillback_validation(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
                "L2": Link(
                    link_id="L2",
                    free_flow_ticks=2,
                    declared_receiving_capacity_per_tick=5,
                    declared_storage_capacity_packets=1,
                ),
            }
        )
        existing_packet = engine.instantiate(
            DemandDeclaration(demand_id="D-existing", departure_tick=0, route_intent=("L2",))
        )
        blocked_packet = engine.instantiate(
            DemandDeclaration(
                demand_id="D-blocked",
                departure_tick=0,
                route_intent=("L1", "L2"),
            )
        )

        engine.step()

        self.assertEqual(engine.link_receiving_view("L2").available_receiving_slots, 0)
        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), (blocked_packet.packet_id,))
        self.assertEqual(
            self.queue_event_packet_ids(engine, EventType.QUEUE_ENTRY, "boundary:L1->L2"),
            [blocked_packet.packet_id],
        )
        self.assertFalse(
            self.has_packet_event(engine, blocked_packet.packet_id, EventType.LINK_EXIT, "L1")
        )
        self.assertFalse(
            self.has_packet_event(engine, blocked_packet.packet_id, EventType.LINK_ENTRY, "L2")
        )
        self.assertIn(blocked_packet.packet_id, engine.packet_ids_on_link("L1"))
        self.assertEqual(engine.link_storage("L1", 1).storage, 1)
        self.assertEqual(engine.link_storage("L2", 1).storage, 1)
        self.assert_storage_never_exceeds_capacity(engine, ("L2",))

        engine.step()

        self.assertEqual(
            self.link_exit_packet_ids(engine, "L2", 2),
            [existing_packet.packet_id],
        )
        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), ())
        self.assert_queued_transfer_release_order(
            engine,
            blocked_packet.packet_id,
            "boundary:L1->L2",
            "L1",
            "L2",
        )
        self.assertEqual(engine.link_storage("L1", 2).storage, 0)
        self.assertEqual(engine.link_storage("L2", 2).storage, 1)
        self.assert_storage_never_exceeds_capacity(engine, ("L2",))
        self.assert_synthetic_kernel_consistent(engine, ("L1", "L2"))

    def test_merge_with_receiving_bottleneck_validation(self) -> None:
        engine = self.build_merge_engine(
            l3_receiving_capacity=1,
            l3_storage_capacity=10,
        )
        packet_l1 = engine.instantiate(
            DemandDeclaration(demand_id="D-L1", departure_tick=0, route_intent=("L1", "L3"))
        )
        packet_l2 = engine.instantiate(
            DemandDeclaration(demand_id="D-L2", departure_tick=0, route_intent=("L2", "L3"))
        )

        engine.step()

        self.assertEqual(self.link_entry_packet_ids(engine, "L3", 1), [packet_l1.packet_id])
        self.assertEqual(engine.packet_ids_in_queue("L2", "L3"), (packet_l2.packet_id,))
        self.assertIn(packet_l2.packet_id, engine.packet_ids_on_link("L2"))
        self.assertEqual(engine.link_storage("L3", 1).storage, 1)
        self.assertEqual(engine.links["L3"].declared_receiving_capacity_per_tick, 1)
        self.assert_link_exit_entry_pair_for_transfers(engine, "L1", "L3")
        self.assert_link_exit_entry_pair_for_transfers(engine, "L2", "L3")
        self.assert_synthetic_kernel_consistent(engine, ("L1", "L2", "L3"))

    def test_merge_with_storage_bottleneck_validation(self) -> None:
        engine = self.build_merge_engine(
            l3_receiving_capacity=10,
            l3_storage_capacity=1,
            l3_free_flow_ticks=10,
        )
        packet_l1 = engine.instantiate(
            DemandDeclaration(demand_id="D-L1", departure_tick=0, route_intent=("L1", "L3"))
        )
        packet_l2 = engine.instantiate(
            DemandDeclaration(demand_id="D-L2", departure_tick=0, route_intent=("L2", "L3"))
        )

        engine.step()

        l3_receiving_view = engine.link_receiving_view("L3")
        self.assertEqual(self.link_entry_packet_ids(engine, "L3", 1), [packet_l1.packet_id])
        self.assertEqual(engine.links["L3"].declared_receiving_capacity_per_tick, 10)
        self.assertEqual(l3_receiving_view.storage_capacity, 1)
        self.assertEqual(l3_receiving_view.available_storage_space, 0)
        self.assertEqual(l3_receiving_view.available_receiving_slots, 0)
        self.assertEqual(engine.packet_ids_in_queue("L2", "L3"), (packet_l2.packet_id,))
        self.assertIn(packet_l2.packet_id, engine.packet_ids_on_link("L2"))
        self.assertLessEqual(engine.link_storage("L3", 1).storage, 1)
        self.assert_storage_never_exceeds_capacity(engine, ("L3",))
        self.assert_synthetic_kernel_consistent(engine, ("L1", "L2", "L3"))

    def test_diverge_with_blocked_branch_validation(self) -> None:
        engine = self.build_diverge_engine(l1_sending_capacity=2)
        engine.set_receiving_open("L2", False)
        packet_a = engine.instantiate(
            DemandDeclaration(demand_id="D-A", departure_tick=0, route_intent=("L1", "L2"))
        )
        packet_b = engine.instantiate(
            DemandDeclaration(demand_id="D-B", departure_tick=0, route_intent=("L1", "L3"))
        )

        engine.step()

        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), (packet_a.packet_id,))
        self.assertEqual(engine.packet_ids_in_queue("L1", "L3"), ())
        self.assertIn(packet_a.packet_id, engine.packet_ids_on_link("L1"))
        self.assertIn(packet_b.packet_id, engine.packet_ids_on_link("L1"))
        self.assertFalse(
            self.has_packet_event(engine, packet_a.packet_id, EventType.LINK_EXIT, "L1")
        )
        self.assertFalse(
            self.has_packet_event(engine, packet_a.packet_id, EventType.LINK_ENTRY, "L2")
        )
        self.assertFalse(
            self.has_packet_event(engine, packet_b.packet_id, EventType.LINK_ENTRY, "L3")
        )
        self.assertEqual(engine.link_storage("L1", 1).storage, 2)
        self.assert_synthetic_kernel_consistent(engine, ("L1", "L2", "L3"))

        engine.set_receiving_open("L2", True)
        engine.step()

        self.assert_queued_transfer_release_order(
            engine,
            packet_a.packet_id,
            "boundary:L1->L2",
            "L1",
            "L2",
        )
        packet_a_l2_entry_tick = self.event(
            engine,
            packet_a.packet_id,
            EventType.LINK_ENTRY,
            "L2",
        ).physical_tick
        self.assertIn(packet_b.packet_id, engine.packet_ids_on_link("L1"))
        self.assertFalse(
            [
                event
                for event in self.events_for_packet(engine, packet_b.packet_id)
                if event.event_type == EventType.LINK_ENTRY
                and event.entity_id == "L3"
                and event.physical_tick <= packet_a_l2_entry_tick
            ]
        )

        engine.step()

        packet_b_l1_exit = self.event(
            engine,
            packet_b.packet_id,
            EventType.LINK_EXIT,
            "L1",
        )
        packet_b_l3_entry = self.event(
            engine,
            packet_b.packet_id,
            EventType.LINK_ENTRY,
            "L3",
        )
        self.assertEqual(packet_b_l1_exit.physical_tick, packet_b_l3_entry.physical_tick)
        self.assertGreater(packet_b_l1_exit.physical_tick, packet_a_l2_entry_tick)

        self.run_to_completion(engine)

        self.assertEqual(self.realised_path(engine, packet_a.packet_id), ("L1", "L2"))
        self.assertEqual(self.realised_path(engine, packet_b.packet_id), ("L1", "L3"))
        self.assert_synthetic_kernel_consistent(engine, ("L1", "L2", "L3"))

    def test_multi_link_route_consistency_validation(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
                "L2": Link(link_id="L2", free_flow_ticks=1),
                "L3": Link(link_id="L3", free_flow_ticks=1),
                "L4": Link(
                    link_id="L4",
                    free_flow_ticks=1,
                    declared_sending_capacity_per_tick=1,
                ),
            }
        )
        packet = engine.instantiate(
            DemandDeclaration(
                demand_id="D1",
                departure_tick=0,
                route_intent=("L1", "L2", "L3", "L4"),
            )
        )

        self.run_to_completion(engine)

        self.assertEqual(
            self.realised_path(engine, packet.packet_id),
            ("L1", "L2", "L3", "L4"),
        )
        self.assert_link_exit_entry_pair_for_transfers(engine, "L1", "L2")
        self.assert_link_exit_entry_pair_for_transfers(engine, "L2", "L3")
        self.assert_link_exit_entry_pair_for_transfers(engine, "L3", "L4")
        self.assert_packet_crosses_at_most_one_boundary_per_tick(engine, packet.packet_id)
        self.assertEqual(
            self.storage_vector(engine, ("L1", "L2", "L3", "L4"), 0),
            (1, 0, 0, 0),
        )
        self.assertEqual(
            self.storage_vector(engine, ("L1", "L2", "L3", "L4"), 1),
            (0, 1, 0, 0),
        )
        self.assertEqual(
            self.storage_vector(engine, ("L1", "L2", "L3", "L4"), 2),
            (0, 0, 1, 0),
        )
        self.assertEqual(
            self.storage_vector(engine, ("L1", "L2", "L3", "L4"), 3),
            (0, 0, 0, 1),
        )
        self.assertEqual(
            self.storage_vector(engine, ("L1", "L2", "L3", "L4"), 4),
            (0, 0, 0, 0),
        )
        self.assertEqual(self.link_exit_packet_ids(engine, "L4", 4), [packet.packet_id])
        self.assertEqual(self.completed_packet_ids(engine, 4), [packet.packet_id])
        self.assert_synthetic_kernel_consistent(engine, ("L1", "L2", "L3", "L4"))

    def build_merge_engine(
        self,
        *,
        l3_receiving_capacity: int,
        l3_storage_capacity: int,
        l3_free_flow_ticks: int = 1,
    ) -> LoadingEngine:
        return LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
                "L2": Link(link_id="L2", free_flow_ticks=1),
                "L3": Link(
                    link_id="L3",
                    free_flow_ticks=l3_free_flow_ticks,
                    declared_receiving_capacity_per_tick=l3_receiving_capacity,
                    declared_storage_capacity_packets=l3_storage_capacity,
                ),
            },
            nodes=(
                Node(
                    node_id="N",
                    incoming_link_ids=("L1", "L2"),
                    outgoing_link_ids=("L3",),
                ),
            ),
        )

    def build_diverge_engine(self, *, l1_sending_capacity: int) -> LoadingEngine:
        return LoadingEngine(
            links={
                "L1": Link(
                    link_id="L1",
                    free_flow_ticks=1,
                    declared_sending_capacity_per_tick=l1_sending_capacity,
                ),
                "L2": Link(link_id="L2", free_flow_ticks=1),
                "L3": Link(link_id="L3", free_flow_ticks=1),
            },
            nodes=(
                Node(
                    node_id="N",
                    incoming_link_ids=("L1",),
                    outgoing_link_ids=("L2", "L3"),
                ),
            ),
        )

    def run_to_completion(self, engine: LoadingEngine, horizon: int = 30) -> None:
        for _ in range(horizon):
            if all(
                packet.lifecycle_state == LifecycleState.COMPLETED
                for packet in engine.packets.values()
            ):
                return
            engine.step()
        self.fail("packets did not complete within expected synthetic test horizon")

    def assert_synthetic_kernel_consistent(
        self,
        engine: LoadingEngine,
        link_ids: tuple[str, ...],
    ) -> None:
        self.assert_conservation_holds(engine)
        self.assert_counts_match_events(engine, link_ids)
        self.assert_storage_matches_counts(engine, link_ids)
        self.assert_storage_matches_membership(engine, link_ids)
        self.assert_no_exits_without_entries(engine, link_ids)
        self.assert_storage_never_exceeds_capacity(engine, link_ids)

    def assert_conservation_holds(self, engine: LoadingEngine) -> None:
        self.assertTrue(engine.check_conservation())
        for tick in range(engine.current_tick + 1):
            instantiated_packet_ids = {
                event.packet_id
                for event in engine.event_log
                if event.event_type == EventType.INSTANTIATED
                and event.physical_tick <= tick
            }
            completed_packet_ids = {
                event.packet_id
                for event in engine.event_log
                if event.event_type == EventType.COMPLETED
                and event.physical_tick <= tick
            }
            cancelled_packet_ids = {
                event.packet_id
                for event in engine.event_log
                if event.event_type == EventType.CANCELLED
                and event.physical_tick <= tick
            }
            in_flight = len(
                instantiated_packet_ids - completed_packet_ids - cancelled_packet_ids
            )
            self.assertEqual(
                len(instantiated_packet_ids),
                in_flight + len(completed_packet_ids) + len(cancelled_packet_ids),
            )

    def assert_counts_match_events(
        self,
        engine: LoadingEngine,
        link_ids: tuple[str, ...],
    ) -> None:
        for link_id in link_ids:
            for tick in range(engine.current_tick + 1):
                self.assertEqual(
                    engine.cumulative_entries(link_id, tick),
                    self.raw_event_count(engine, link_id, tick, EventType.LINK_ENTRY),
                )
                self.assertEqual(
                    engine.cumulative_exits(link_id, tick),
                    self.raw_event_count(engine, link_id, tick, EventType.LINK_EXIT),
                )

    def assert_storage_matches_counts(
        self,
        engine: LoadingEngine,
        link_ids: tuple[str, ...],
    ) -> None:
        for link_id in link_ids:
            for tick in range(engine.current_tick + 1):
                counts = engine.cumulative_counts(link_id, tick)
                self.assertLessEqual(counts.exits, counts.entries)
                self.assertEqual(
                    engine.link_storage(link_id, tick).storage,
                    counts.entries - counts.exits,
                )

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

    def assert_no_exits_without_entries(
        self,
        engine: LoadingEngine,
        link_ids: tuple[str, ...],
    ) -> None:
        for link_id in link_ids:
            packet_ids_on_link: set[str] = set()
            for event in engine.event_log:
                if event.entity_id != link_id:
                    continue
                if event.event_type == EventType.LINK_ENTRY:
                    packet_ids_on_link.add(event.packet_id)
                elif event.event_type == EventType.LINK_EXIT:
                    self.assertIn(event.packet_id, packet_ids_on_link)
                    packet_ids_on_link.remove(event.packet_id)

    def assert_link_exit_entry_pair_for_transfers(
        self,
        engine: LoadingEngine,
        upstream: str,
        downstream: str,
    ) -> None:
        for exit_event in self.link_events(engine, EventType.LINK_EXIT, upstream):
            packet = engine.packets[exit_event.packet_id]
            if not self.route_has_adjacent_pair(packet.route_intent, upstream, downstream):
                continue
            packet_events = self.events_for_packet(engine, exit_event.packet_id)
            exit_index = packet_events.index(exit_event)
            self.assertLess(exit_index + 1, len(packet_events))
            entry_event = packet_events[exit_index + 1]
            self.assertEqual(entry_event.event_type, EventType.LINK_ENTRY)
            self.assertEqual(entry_event.entity_id, downstream)
            self.assertEqual(entry_event.physical_tick, exit_event.physical_tick)
            self.assertLess(exit_event.sequence_number, entry_event.sequence_number)

        for entry_event in self.link_events(engine, EventType.LINK_ENTRY, downstream):
            packet = engine.packets[entry_event.packet_id]
            if not self.route_has_adjacent_pair(packet.route_intent, upstream, downstream):
                continue
            packet_events = self.events_for_packet(engine, entry_event.packet_id)
            entry_index = packet_events.index(entry_event)
            self.assertGreater(entry_index, 0)
            exit_event = packet_events[entry_index - 1]
            self.assertEqual(exit_event.event_type, EventType.LINK_EXIT)
            self.assertEqual(exit_event.entity_id, upstream)
            self.assertEqual(exit_event.physical_tick, entry_event.physical_tick)
            self.assertLess(exit_event.sequence_number, entry_event.sequence_number)
            boundary_id = f"boundary:{upstream}->{downstream}"
            if entry_index >= 2 and packet_events[entry_index - 2].entity_id == boundary_id:
                queue_exit_event = packet_events[entry_index - 2]
                self.assertEqual(queue_exit_event.event_type, EventType.QUEUE_EXIT)
                self.assertEqual(queue_exit_event.physical_tick, entry_event.physical_tick)
                self.assertLess(queue_exit_event.sequence_number, exit_event.sequence_number)

    def route_has_adjacent_pair(
        self,
        route_intent: tuple[str, ...],
        upstream: str,
        downstream: str,
    ) -> bool:
        return any(
            first_link_id == upstream and second_link_id == downstream
            for first_link_id, second_link_id in zip(route_intent, route_intent[1:])
        )

    def assert_storage_never_exceeds_capacity(
        self,
        engine: LoadingEngine,
        link_ids: tuple[str, ...],
    ) -> None:
        for link_id in link_ids:
            storage_capacity = engine.links[link_id].declared_storage_capacity_packets
            for tick in range(engine.current_tick + 1):
                self.assertLessEqual(
                    engine.link_storage(link_id, tick).storage,
                    storage_capacity,
                )

    def assert_queued_transfer_release_order(
        self,
        engine: LoadingEngine,
        packet_id: str,
        boundary_id: str,
        upstream_link_id: str,
        downstream_link_id: str,
    ) -> None:
        packet_events = self.events_for_packet(engine, packet_id)
        queue_exit = self.event(engine, packet_id, EventType.QUEUE_EXIT, boundary_id)
        link_exit = self.event(engine, packet_id, EventType.LINK_EXIT, upstream_link_id)
        link_entry = self.event(engine, packet_id, EventType.LINK_ENTRY, downstream_link_id)
        self.assertLess(packet_events.index(queue_exit), packet_events.index(link_exit))
        self.assertLess(packet_events.index(link_exit), packet_events.index(link_entry))
        self.assertEqual(queue_exit.physical_tick, link_exit.physical_tick)
        self.assertEqual(link_exit.physical_tick, link_entry.physical_tick)

    def assert_packet_crosses_at_most_one_boundary_per_tick(
        self,
        engine: LoadingEngine,
        packet_id: str,
    ) -> None:
        link_exits_by_tick: dict[int, int] = {}
        for event in self.events_for_packet(engine, packet_id):
            if event.event_type != EventType.LINK_EXIT:
                continue
            link_exits_by_tick[event.physical_tick] = (
                link_exits_by_tick.get(event.physical_tick, 0) + 1
            )
        self.assertTrue(
            all(exit_count <= 1 for exit_count in link_exits_by_tick.values())
        )

    def assert_per_tick_event_count_at_most(
        self,
        engine: LoadingEngine,
        event_type: EventType,
        entity_id: str,
        maximum_count: int,
    ) -> None:
        for tick in range(engine.current_tick + 1):
            self.assertLessEqual(
                len(
                    [
                        event
                        for event in engine.event_log
                        if event.event_type == event_type
                        and event.entity_id == entity_id
                        and event.physical_tick == tick
                    ]
                ),
                maximum_count,
            )

    def raw_event_count(
        self,
        engine: LoadingEngine,
        link_id: str,
        tick: int,
        event_type: EventType,
    ) -> int:
        return sum(
            event.event_type == event_type
            and event.entity_id == link_id
            and event.physical_tick <= tick
            for event in engine.event_log
        )

    def packet_ids(self, packets: list[Packet]) -> list[str]:
        return [packet.packet_id for packet in packets]

    def events_for_packet(self, engine: LoadingEngine, packet_id: str) -> list[Event]:
        return [event for event in engine.event_log if event.packet_id == packet_id]

    def link_events(
        self,
        engine: LoadingEngine,
        event_type: EventType,
        link_id: str,
    ) -> list[Event]:
        return [
            event
            for event in engine.event_log
            if event.event_type == event_type and event.entity_id == link_id
        ]

    def link_entry_packet_ids(
        self,
        engine: LoadingEngine,
        link_id: str,
        tick: int,
    ) -> list[str]:
        return [
            event.packet_id
            for event in self.link_events(engine, EventType.LINK_ENTRY, link_id)
            if event.physical_tick == tick
        ]

    def link_exit_packet_ids(
        self,
        engine: LoadingEngine,
        link_id: str,
        tick: int,
    ) -> list[str]:
        return [
            event.packet_id
            for event in self.link_events(engine, EventType.LINK_EXIT, link_id)
            if event.physical_tick == tick
        ]

    def queue_event_packet_ids(
        self,
        engine: LoadingEngine,
        event_type: EventType,
        boundary_id: str,
    ) -> list[str]:
        return [
            event.packet_id
            for event in engine.event_log
            if event.event_type == event_type and event.entity_id == boundary_id
        ]

    def completed_packet_ids(self, engine: LoadingEngine, tick: int) -> list[str]:
        return [
            event.packet_id
            for event in engine.event_log
            if event.event_type == EventType.COMPLETED and event.physical_tick == tick
        ]

    def has_packet_event(
        self,
        engine: LoadingEngine,
        packet_id: str,
        event_type: EventType,
        entity_id: str,
    ) -> bool:
        return any(
            event.packet_id == packet_id
            and event.event_type == event_type
            and event.entity_id == entity_id
            for event in engine.event_log
        )

    def event(
        self,
        engine: LoadingEngine,
        packet_id: str,
        event_type: EventType,
        entity_id: str,
    ) -> Event:
        for event in engine.event_log:
            if (
                event.packet_id == packet_id
                and event.event_type == event_type
                and event.entity_id == entity_id
            ):
                return event
        self.fail(
            f"missing event for packet_id={packet_id}, "
            f"event_type={event_type.name}, entity_id={entity_id}"
        )

    def realised_path(self, engine: LoadingEngine, packet_id: str) -> tuple[str, ...]:
        return tuple(
            event.entity_id
            for event in self.events_for_packet(engine, packet_id)
            if event.event_type == EventType.LINK_ENTRY
        )

    def storage_vector(
        self,
        engine: LoadingEngine,
        link_ids: tuple[str, ...],
        tick: int,
    ) -> tuple[int, ...]:
        return tuple(
            engine.link_storage(link_id, tick).storage for link_id in link_ids
        )


if __name__ == "__main__":
    unittest.main()
