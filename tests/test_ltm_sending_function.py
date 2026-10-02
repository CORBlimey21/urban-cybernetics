# SPDX-License-Identifier: MPL-2.0
"""LTM-style upstream sending function tests."""

from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import DemandDeclaration, EventType, LifecycleState, Link
from urban_cybernetics.loading import LoadingEngine, packet_ids_on_link_from_events


class LTMSendingFunctionTest(unittest.TestCase):
    def test_packet_is_not_sendable_before_free_flow_time(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(
                    link_id="L1",
                    free_flow_ticks=3,
                    declared_sending_capacity_per_tick=1,
                )
            }
        )
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1",))
        )

        for tick in range(3):
            sending_view = engine.link_sending_view("L1", tick)
            self.assertNotIn(packet.packet_id, sending_view.eligible_packet_ids)
            self.assertNotIn(packet.packet_id, sending_view.sendable_packet_ids)

        sending_view = engine.link_sending_view("L1", 3)

        self.assertIn(packet.packet_id, sending_view.eligible_packet_ids)
        self.assertEqual(sending_view.sendable_packet_ids, (packet.packet_id,))

    def test_sending_capacity_limits_sendable_packets(self) -> None:
        engine = self.build_single_link_engine(sending_capacity=1)
        for demand_number in range(3):
            engine.instantiate(
                DemandDeclaration(
                    demand_id=f"D{demand_number}",
                    departure_tick=0,
                    route_intent=("L1",),
                )
            )

        sending_view = engine.link_sending_view("L1", 1)

        self.assertGreater(len(sending_view.eligible_packet_ids), 1)
        self.assertEqual(len(sending_view.sendable_packet_ids), 1)

    def test_sending_preserves_fifo_order(self) -> None:
        engine = self.build_single_link_engine(sending_capacity=2)
        packet_a = engine.instantiate(
            DemandDeclaration(demand_id="D-A", departure_tick=0, route_intent=("L1",))
        )
        packet_b = engine.instantiate(
            DemandDeclaration(demand_id="D-B", departure_tick=0, route_intent=("L1",))
        )
        packet_c = engine.instantiate(
            DemandDeclaration(demand_id="D-C", departure_tick=0, route_intent=("L1",))
        )

        sending_view = engine.link_sending_view("L1", 1)

        self.assertEqual(
            sending_view.eligible_packet_ids,
            (packet_a.packet_id, packet_b.packet_id, packet_c.packet_id),
        )
        self.assertEqual(
            sending_view.sendable_packet_ids,
            (packet_a.packet_id, packet_b.packet_id),
        )

    def test_engine_candidate_collection_respects_sending_capacity(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(
                    link_id="L1",
                    free_flow_ticks=1,
                    declared_sending_capacity_per_tick=1,
                ),
                "L2": Link(
                    link_id="L2",
                    free_flow_ticks=1,
                    declared_receiving_capacity_per_tick=3,
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
            self.link_event_packet_ids(engine, EventType.LINK_EXIT, "L1", 1),
            [packets[0].packet_id],
        )
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 1),
            [packets[0].packet_id],
        )
        self.assertEqual(
            packet_ids_on_link_from_events(engine.event_log, "L1", 1),
            (packets[1].packet_id, packets[2].packet_id),
        )
        self.assertTrue(engine.check_conservation())

    def test_queued_packets_retain_upstream_semantics(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(
                    link_id="L1",
                    free_flow_ticks=1,
                    declared_sending_capacity_per_tick=1,
                ),
                "L2": Link(
                    link_id="L2",
                    free_flow_ticks=1,
                    declared_receiving_capacity_per_tick=1,
                ),
            }
        )
        engine.set_receiving_open("L2", False)
        packet_a = engine.instantiate(
            DemandDeclaration(demand_id="D-A", departure_tick=0, route_intent=("L1", "L2"))
        )
        packet_b = engine.instantiate(
            DemandDeclaration(demand_id="D-B", departure_tick=0, route_intent=("L1", "L2"))
        )

        engine.step()
        engine.step()
        engine.step()

        self.assertEqual(
            engine.packet_ids_in_queue("L1", "L2"),
            (packet_a.packet_id,),
        )
        self.assertEqual(engine.link_storage("L1").storage, 2)
        self.assertEqual(engine.link_storage("L2").storage, 0)
        self.assertEqual(
            self.queue_entry_packet_ids(engine, "boundary:L1->L2"),
            [packet_a.packet_id],
        )
        self.assertIn(packet_b.packet_id, engine.packet_ids_on_link("L1"))

        engine.set_receiving_open("L2", True)
        engine.step()

        packet_a_events = self.events_for_packet(engine, packet_a.packet_id)
        self.assertLess(
            packet_a_events.index(
                self.event(engine, packet_a.packet_id, EventType.QUEUE_EXIT, "boundary:L1->L2")
            ),
            packet_a_events.index(
                self.event(engine, packet_a.packet_id, EventType.LINK_EXIT, "L1")
            ),
        )
        self.assertLess(
            packet_a_events.index(
                self.event(engine, packet_a.packet_id, EventType.LINK_EXIT, "L1")
            ),
            packet_a_events.index(
                self.event(engine, packet_a.packet_id, EventType.LINK_ENTRY, "L2")
            ),
        )
        self.assertEqual(engine.link_storage("L1").storage, 1)
        self.assertEqual(engine.link_storage("L2").storage, 1)
        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), ())
        self.assertIn(packet_b.packet_id, engine.packet_ids_on_link("L1"))

    def test_public_sending_view_excludes_already_queued_packets(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(
                    link_id="L1",
                    free_flow_ticks=1,
                    declared_sending_capacity_per_tick=2,
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
        sending_view = engine.link_sending_view("L1")
        self.assertNotIn(packet.packet_id, sending_view.eligible_packet_ids)
        self.assertNotIn(packet.packet_id, sending_view.sendable_packet_ids)

    def test_final_link_completion_respects_sending_capacity(self) -> None:
        engine = self.build_single_link_engine(sending_capacity=1)
        packet_a = engine.instantiate(
            DemandDeclaration(demand_id="D-A", departure_tick=0, route_intent=("L1",))
        )
        packet_b = engine.instantiate(
            DemandDeclaration(demand_id="D-B", departure_tick=0, route_intent=("L1",))
        )

        engine.step()

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_EXIT, "L1", 1),
            [packet_a.packet_id],
        )
        self.assertEqual(
            engine.packets[packet_a.packet_id].lifecycle_state,
            LifecycleState.COMPLETED,
        )
        self.assertEqual(
            engine.packets[packet_b.packet_id].lifecycle_state,
            LifecycleState.IN_TRANSIT,
        )
        self.assertEqual(
            packet_ids_on_link_from_events(engine.event_log, "L1", 1),
            (packet_b.packet_id,),
        )

    def test_two_mature_final_packets_with_capacity_one_do_not_both_complete(self) -> None:
        engine = self.build_single_link_engine(sending_capacity=1)
        packet_a = engine.instantiate(
            DemandDeclaration(demand_id="D-A", departure_tick=0, route_intent=("L1",))
        )
        packet_b = engine.instantiate(
            DemandDeclaration(demand_id="D-B", departure_tick=0, route_intent=("L1",))
        )

        self.assertEqual(
            engine.link_sending_view("L1", 1).sendable_packet_ids,
            (packet_a.packet_id,),
        )

        engine.step()

        completed_packet_ids = [
            packet_id
            for packet_id, packet in engine.packets.items()
            if packet.lifecycle_state == LifecycleState.COMPLETED
        ]
        self.assertEqual(completed_packet_ids, [packet_a.packet_id])
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_EXIT, "L1", 1),
            [packet_a.packet_id],
        )
        self.assertNotIn(
            packet_b.packet_id,
            self.link_event_packet_ids(engine, EventType.LINK_EXIT, "L1", 1),
        )

    def test_sending_view_is_event_derived(self) -> None:
        engine = self.build_single_link_engine(sending_capacity=1)
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1",))
        )
        engine._packets[packet.packet_id] = replace(
            engine.packets[packet.packet_id],
            lifecycle_state=LifecycleState.COMPLETED,
        )

        sending_view = engine.link_sending_view("L1", 1)

        self.assertEqual(sending_view.sendable_packet_ids, (packet.packet_id,))
        self.assertEqual(
            sending_view.sendable_packet_ids,
            packet_ids_on_link_from_events(engine.event_log, "L1", 1),
        )

    def test_sending_view_is_frozen(self) -> None:
        engine = self.build_single_link_engine(sending_capacity=1)
        engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1",))
        )

        sending_view = engine.link_sending_view("L1", 1)

        with self.assertRaises(FrozenInstanceError):
            sending_view.sending_capacity = 99

    def build_single_link_engine(self, *, sending_capacity: int) -> LoadingEngine:
        return LoadingEngine(
            links={
                "L1": Link(
                    link_id="L1",
                    free_flow_ticks=1,
                    declared_sending_capacity_per_tick=sending_capacity,
                )
            }
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

    def events_for_packet(self, engine: LoadingEngine, packet_id: str):
        return [event for event in engine.event_log if event.packet_id == packet_id]

    def event(
        self,
        engine: LoadingEngine,
        packet_id: str,
        event_type: EventType,
        entity_id: str,
    ):
        return next(
            event
            for event in engine.event_log
            if event.packet_id == packet_id
            and event.event_type == event_type
            and event.entity_id == entity_id
        )


if __name__ == "__main__":
    unittest.main()
