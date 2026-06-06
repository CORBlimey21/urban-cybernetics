"""Storage-constrained receiving and basic spillback tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import DemandDeclaration, Event, EventType, Link, Node
from urban_cybernetics.loading import (
    LoadingEngine,
    link_receiving_view,
    packet_ids_on_link_from_events,
)


class StorageConstrainedReceivingTest(unittest.TestCase):
    def test_receiving_view_reports_zero_slots_when_storage_full(self) -> None:
        engine = LoadingEngine(
            links={
                "L2": Link(
                    link_id="L2",
                    free_flow_ticks=10,
                    declared_receiving_capacity_per_tick=5,
                    declared_storage_capacity_packets=1,
                )
            }
        )
        engine.instantiate(
            DemandDeclaration(demand_id="D-existing", departure_tick=0, route_intent=("L2",))
        )
        engine.step()

        receiving_view = engine.link_receiving_view("L2")

        self.assertTrue(receiving_view.receiving_open)
        self.assertEqual(receiving_view.current_storage, 1)
        self.assertEqual(receiving_view.storage_capacity, 1)
        self.assertEqual(receiving_view.available_storage_space, 0)
        self.assertEqual(receiving_view.available_receiving_slots, 0)

    def test_receiving_view_reports_storage_limited_slots(self) -> None:
        engine = LoadingEngine(
            links={
                "L2": Link(
                    link_id="L2",
                    free_flow_ticks=10,
                    declared_receiving_capacity_per_tick=5,
                    declared_storage_capacity_packets=3,
                )
            }
        )
        for demand_number in range(2):
            engine.instantiate(
                DemandDeclaration(
                    demand_id=f"D-existing-{demand_number}",
                    departure_tick=0,
                    route_intent=("L2",),
                )
            )
        engine.step()

        receiving_view = engine.link_receiving_view("L2")

        self.assertEqual(receiving_view.receiving_capacity, 5)
        self.assertEqual(receiving_view.current_storage, 2)
        self.assertEqual(receiving_view.storage_capacity, 3)
        self.assertEqual(receiving_view.available_storage_space, 1)
        self.assertEqual(receiving_view.available_receiving_slots, 1)

    def test_same_tick_accepted_entries_consume_storage_space(self) -> None:
        link = Link(
            link_id="L2",
            free_flow_ticks=10,
            declared_receiving_capacity_per_tick=5,
            declared_storage_capacity_packets=3,
        )
        events = (
            Event(0, "P1", EventType.LINK_ENTRY, "L2", 0),
            Event(1, "P2", EventType.LINK_ENTRY, "L2", 0),
            Event(2, "P3", EventType.LINK_ENTRY, "L2", 5),
        )

        receiving_view = link_receiving_view(events, link, 5, receiving_open=True)

        self.assertEqual(receiving_view.current_storage, 2)
        self.assertEqual(receiving_view.already_accepted_count, 1)
        self.assertEqual(receiving_view.available_storage_space, 0)
        self.assertEqual(receiving_view.available_receiving_slots, 0)

    def test_downstream_full_blocks_upstream_transfer(self) -> None:
        engine, _, blocked_packet_id = self.build_spillback_engine_after_queue()

        self.assertEqual(
            self.queue_event_packet_ids(engine, EventType.QUEUE_ENTRY, "boundary:L1->L2"),
            [blocked_packet_id],
        )
        self.assertFalse(
            self.has_packet_event(engine, blocked_packet_id, EventType.LINK_EXIT, "L1")
        )
        self.assertFalse(
            self.has_packet_event(engine, blocked_packet_id, EventType.LINK_ENTRY, "L2")
        )
        self.assertEqual(engine.link_storage("L1", 1).storage, 1)
        self.assertEqual(engine.link_storage("L2", 1).storage, 1)
        self.assertEqual(
            packet_ids_on_link_from_events(engine.event_log, "L1", 1),
            (blocked_packet_id,),
        )

    def test_freeing_storage_releases_queued_upstream_packet(self) -> None:
        engine, existing_packet_id, blocked_packet_id = (
            self.build_spillback_engine_after_queue()
        )

        engine.step()

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_EXIT, "L2", 2),
            [existing_packet_id],
        )
        blocked_events = self.events_for_packet(engine, blocked_packet_id)
        self.assertLess(
            blocked_events.index(
                self.event(engine, blocked_packet_id, EventType.QUEUE_EXIT, "boundary:L1->L2")
            ),
            blocked_events.index(
                self.event(engine, blocked_packet_id, EventType.LINK_EXIT, "L1")
            ),
        )
        self.assertLess(
            blocked_events.index(
                self.event(engine, blocked_packet_id, EventType.LINK_EXIT, "L1")
            ),
            blocked_events.index(
                self.event(engine, blocked_packet_id, EventType.LINK_ENTRY, "L2")
            ),
        )
        self.assertEqual(engine.link_storage("L1", 2).storage, 0)
        self.assertEqual(engine.link_storage("L2", 2).storage, 1)
        self.assertTrue(engine.check_conservation())

    def test_same_tick_entries_share_one_storage_slot(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
                "L2": Link(link_id="L2", free_flow_ticks=1),
                "L3": Link(
                    link_id="L3",
                    free_flow_ticks=10,
                    declared_receiving_capacity_per_tick=5,
                    declared_storage_capacity_packets=1,
                ),
            }
        )
        packet_l1 = engine.instantiate(
            DemandDeclaration(demand_id="D-L1", departure_tick=0, route_intent=("L1", "L3"))
        )
        packet_l2 = engine.instantiate(
            DemandDeclaration(demand_id="D-L2", departure_tick=0, route_intent=("L2", "L3"))
        )

        engine.step()

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L3", 1),
            [packet_l1.packet_id],
        )
        self.assertEqual(engine.packet_ids_in_queue("L2", "L3"), (packet_l2.packet_id,))
        self.assertEqual(engine.link_storage("L2", 1).storage, 1)
        self.assertEqual(engine.link_storage("L3", 1).storage, 1)
        self.assertTrue(engine.check_conservation())

    def test_merge_storage_capacity_is_shared_across_incoming_links(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
                "L2": Link(link_id="L2", free_flow_ticks=1),
                "L3": Link(
                    link_id="L3",
                    free_flow_ticks=10,
                    declared_receiving_capacity_per_tick=10,
                    declared_storage_capacity_packets=1,
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
        packet_l1 = engine.instantiate(
            DemandDeclaration(demand_id="D-L1", departure_tick=0, route_intent=("L1", "L3"))
        )
        packet_l2 = engine.instantiate(
            DemandDeclaration(demand_id="D-L2", departure_tick=0, route_intent=("L2", "L3"))
        )

        engine.step()

        l3_entries = self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L3", 1)
        self.assertLessEqual(len(l3_entries), 1)
        self.assertEqual(l3_entries, [packet_l1.packet_id])
        self.assertEqual(
            packet_ids_on_link_from_events(engine.event_log, "L2", 1),
            (packet_l2.packet_id,),
        )
        self.assertTrue(engine.check_conservation())

    def test_queued_packet_remains_upstream_under_storage_spillback(self) -> None:
        engine, _, blocked_packet_id = self.build_spillback_engine_after_queue()

        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), (blocked_packet_id,))
        self.assertEqual(engine.link_storage("L1", 1).storage, 1)
        self.assertEqual(engine.link_storage("L2", 1).storage, 1)

        engine.step()

        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), ())
        self.assertEqual(engine.link_storage("L1", 2).storage, 0)
        self.assertEqual(engine.link_storage("L2", 2).storage, 1)

    def build_spillback_engine_after_queue(self) -> tuple[LoadingEngine, str, str]:
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
            DemandDeclaration(demand_id="D-blocked", departure_tick=0, route_intent=("L1", "L2"))
        )

        engine.step()

        return engine, existing_packet.packet_id, blocked_packet.packet_id

    def link_event_packet_ids(
        self,
        engine: LoadingEngine,
        event_type: EventType,
        link_id: str,
        tick: int,
    ) -> list[str]:
        return [
            event.packet_id
            for event in engine.event_log
            if event.event_type == event_type
            and event.entity_id == link_id
            and event.physical_tick == tick
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

    def events_for_packet(self, engine: LoadingEngine, packet_id: str) -> list[Event]:
        return [event for event in engine.event_log if event.packet_id == packet_id]

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


if __name__ == "__main__":
    unittest.main()
