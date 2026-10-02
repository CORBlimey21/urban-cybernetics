# SPDX-License-Identifier: MPL-2.0
"""LTM-style downstream receiving function tests."""

from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import DemandDeclaration, Event, EventType, LifecycleState, Link, Node
from urban_cybernetics.loading import (
    LoadingEngine,
    link_receiving_view,
    packet_ids_on_link_from_events,
)


class LTMReceivingFunctionTest(unittest.TestCase):
    def test_receiving_view_reports_zero_slots_when_closed(self) -> None:
        engine = LoadingEngine(
            links={
                "L2": Link(
                    link_id="L2",
                    free_flow_ticks=1,
                    declared_receiving_capacity_per_tick=3,
                )
            }
        )
        engine.set_receiving_open("L2", False)

        receiving_view = engine.link_receiving_view("L2")

        self.assertFalse(receiving_view.receiving_open)
        self.assertEqual(receiving_view.receiving_capacity, 3)
        self.assertEqual(receiving_view.available_receiving_slots, 0)

    def test_receiving_view_reports_declared_slots_when_open(self) -> None:
        engine = LoadingEngine(
            links={
                "L2": Link(
                    link_id="L2",
                    free_flow_ticks=1,
                    declared_receiving_capacity_per_tick=3,
                )
            }
        )

        receiving_view = engine.link_receiving_view("L2")

        self.assertTrue(receiving_view.receiving_open)
        self.assertEqual(receiving_view.receiving_capacity, 3)
        self.assertEqual(receiving_view.available_receiving_slots, 3)

    def test_already_accepted_entries_consume_receiving_slots(self) -> None:
        engine = LoadingEngine(
            links={
                "L2": Link(
                    link_id="L2",
                    free_flow_ticks=1,
                    declared_receiving_capacity_per_tick=3,
                )
            }
        )

        self.assertEqual(
            engine.link_receiving_view("L2", already_accepted_count=2)
            .available_receiving_slots,
            1,
        )
        self.assertEqual(
            engine.link_receiving_view("L2", already_accepted_count=3)
            .available_receiving_slots,
            0,
        )
        self.assertEqual(
            engine.link_receiving_view("L2", already_accepted_count=4)
            .available_receiving_slots,
            0,
        )

    def test_same_tick_link_entries_consume_receiving_slots(self) -> None:
        link = Link(
            link_id="L2",
            free_flow_ticks=1,
            declared_receiving_capacity_per_tick=3,
        )
        events = (
            Event(
                sequence_number=0,
                packet_id="P1",
                event_type=EventType.LINK_ENTRY,
                entity_id="L2",
                physical_tick=5,
            ),
            Event(
                sequence_number=1,
                packet_id="P2",
                event_type=EventType.LINK_ENTRY,
                entity_id="L2",
                physical_tick=5,
            ),
        )

        receiving_view = link_receiving_view(events, link, 5, receiving_open=True)

        self.assertEqual(receiving_view.already_accepted_count, 2)
        self.assertEqual(receiving_view.available_receiving_slots, 1)

    def test_receiving_view_is_frozen(self) -> None:
        engine = LoadingEngine(
            links={
                "L2": Link(
                    link_id="L2",
                    free_flow_ticks=1,
                    declared_receiving_capacity_per_tick=3,
                )
            }
        )

        receiving_view = engine.link_receiving_view("L2")

        with self.assertRaises(FrozenInstanceError):
            receiving_view.available_receiving_slots = 99

    def test_engine_transfer_respects_receiving_view(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(
                    link_id="L1",
                    free_flow_ticks=1,
                    declared_sending_capacity_per_tick=3,
                ),
                "L2": Link(
                    link_id="L2",
                    free_flow_ticks=1,
                    declared_receiving_capacity_per_tick=1,
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

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 1),
            [packets[0].packet_id],
        )
        self.assertEqual(
            packet_ids_on_link_from_events(engine.event_log, "L1", 1),
            (packets[1].packet_id, packets[2].packet_id),
        )
        self.assertEqual(
            engine.packet_ids_in_queue("L1", "L2"),
            (packets[1].packet_id, packets[2].packet_id),
        )
        self.assertTrue(engine.check_conservation())

    def test_sending_open_but_receiving_closed_queues_upstream(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(
                    link_id="L1",
                    free_flow_ticks=1,
                    declared_sending_capacity_per_tick=1,
                ),
                "L2": Link(link_id="L2", free_flow_ticks=1),
            }
        )
        engine.set_receiving_open("L2", False)
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1", "L2"))
        )

        engine.step()

        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), (packet.packet_id,))
        self.assertEqual(
            self.queue_entry_packet_ids(engine, "boundary:L1->L2"),
            [packet.packet_id],
        )
        self.assertFalse(self.has_event(engine, EventType.LINK_EXIT, "L1", 1))
        self.assertFalse(self.has_event(engine, EventType.LINK_ENTRY, "L2", 1))
        self.assertEqual(engine.link_storage("L1").storage, 1)
        self.assertEqual(engine.link_storage("L2").storage, 0)
        self.assertEqual(engine.cumulative_exits("L1"), 0)
        self.assertEqual(engine.cumulative_entries("L2"), 0)

    def test_queued_release_consumes_receiving_capacity(self) -> None:
        engine = self.build_merge_engine(l3_receiving_capacity=1)
        engine.set_receiving_open("L3", False)
        packet_l1 = engine.instantiate(
            DemandDeclaration(demand_id="D-L1", departure_tick=0, route_intent=("L1", "L3"))
        )
        packet_l2 = engine.instantiate(
            DemandDeclaration(demand_id="D-L2", departure_tick=0, route_intent=("L2", "L3"))
        )

        engine.step()

        self.assertEqual(engine.packet_ids_in_queue("L1", "L3"), (packet_l1.packet_id,))
        self.assertEqual(engine.packet_ids_in_queue("L2", "L3"), (packet_l2.packet_id,))

        engine.set_receiving_open("L3", True)
        engine.step()

        self.assertEqual(
            self.queue_exit_packet_ids(engine, 2),
            [packet_l1.packet_id],
        )
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L3", 2),
            [packet_l1.packet_id],
        )
        self.assertEqual(engine.packet_ids_in_queue("L1", "L3"), ())
        self.assertEqual(engine.packet_ids_in_queue("L2", "L3"), (packet_l2.packet_id,))
        self.assertEqual(
            packet_ids_on_link_from_events(engine.event_log, "L2", 2),
            (packet_l2.packet_id,),
        )
        self.assertTrue(engine.check_conservation())

    def test_sending_and_receiving_must_both_permit_transfer(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(
                    link_id="L1",
                    free_flow_ticks=3,
                    declared_sending_capacity_per_tick=1,
                ),
                "L2": Link(
                    link_id="L2",
                    free_flow_ticks=1,
                    declared_receiving_capacity_per_tick=1,
                ),
            }
        )
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1", "L2"))
        )

        engine.step()

        self.assertFalse(self.has_event(engine, EventType.LINK_EXIT, "L1", 1))
        self.assertFalse(self.has_event(engine, EventType.LINK_ENTRY, "L2", 1))
        self.assertIn(packet.packet_id, engine.packet_ids_on_link("L1"))

        engine.step()
        engine.step()

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_EXIT, "L1", 3),
            [packet.packet_id],
        )
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 3),
            [packet.packet_id],
        )
        self.assertTrue(engine.check_conservation())

    def build_merge_engine(self, *, l3_receiving_capacity: int) -> LoadingEngine:
        return LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
                "L2": Link(link_id="L2", free_flow_ticks=1),
                "L3": Link(
                    link_id="L3",
                    free_flow_ticks=1,
                    declared_receiving_capacity_per_tick=l3_receiving_capacity,
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

    def queue_entry_packet_ids(
        self,
        engine: LoadingEngine,
        boundary_id: str,
    ) -> list[str]:
        return [
            event.packet_id
            for event in engine.event_log
            if event.event_type == EventType.QUEUE_ENTRY
            and event.entity_id == boundary_id
        ]

    def queue_exit_packet_ids(self, engine: LoadingEngine, tick: int) -> list[str]:
        return [
            event.packet_id
            for event in engine.event_log
            if event.event_type == EventType.QUEUE_EXIT
            and event.physical_tick == tick
        ]

    def has_event(
        self,
        engine: LoadingEngine,
        event_type: EventType,
        entity_id: str,
        tick: int,
    ) -> bool:
        return any(
            event.event_type == event_type
            and event.entity_id == entity_id
            and event.physical_tick <= tick
            for event in engine.event_log
        )


if __name__ == "__main__":
    unittest.main()
