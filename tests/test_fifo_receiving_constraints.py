"""FIFO and receiving-constraint tests for the minimal loading engine."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import DemandDeclaration, EventType, LifecycleState, Link
from urban_cybernetics.loading import LoadingEngine


class FifoAndReceivingConstraintTest(unittest.TestCase):
    def test_fifo_same_link(self) -> None:
        engine = LoadingEngine(links={"L1": Link(link_id="L1", free_flow_ticks=1)})
        packet_a = engine.instantiate(
            DemandDeclaration(demand_id="D-A", departure_tick=0, route_intent=("L1",))
        )
        packet_b = engine.instantiate(
            DemandDeclaration(demand_id="D-B", departure_tick=0, route_intent=("L1",))
        )

        engine.step()
        engine.step()

        link_exit_packet_ids = [
            event.packet_id
            for event in engine.event_log
            if event.event_type == EventType.LINK_EXIT and event.entity_id == "L1"
        ]
        self.assertEqual(link_exit_packet_ids, [packet_a.packet_id, packet_b.packet_id])

    def test_downstream_receiving_constraint(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
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

        for _ in range(3):
            engine.step()

        blocked_tick = engine.current_tick
        self.assertEqual(
            engine.packet_ids_in_queue("L1", "L2"),
            (packet_a.packet_id, packet_b.packet_id),
        )
        self.assertFalse(
            [
                event
                for event in engine.event_log
                if event.event_type == EventType.LINK_EXIT
                and event.entity_id == "L1"
                and event.physical_tick <= blocked_tick
            ]
        )
        self.assertFalse(
            [
                event
                for event in engine.event_log
                if event.event_type == EventType.LINK_ENTRY
                and event.entity_id == "L2"
                and event.physical_tick <= blocked_tick
            ]
        )

        engine.set_receiving_open("L2", True)
        while any(
            packet.lifecycle_state != LifecycleState.COMPLETED
            for packet in engine.packets.values()
        ):
            engine.step()

        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), ())
        queue_exit_packet_ids = [
            event.packet_id
            for event in engine.event_log
            if event.event_type == EventType.QUEUE_EXIT
        ]
        transfer_exit_packet_ids = [
            event.packet_id
            for event in engine.event_log
            if event.event_type == EventType.LINK_EXIT and event.entity_id == "L1"
        ]
        transfer_entry_packet_ids = [
            event.packet_id
            for event in engine.event_log
            if event.event_type == EventType.LINK_ENTRY and event.entity_id == "L2"
        ]
        self.assertEqual(queue_exit_packet_ids, [packet_a.packet_id, packet_b.packet_id])
        self.assertEqual(transfer_exit_packet_ids, [packet_a.packet_id, packet_b.packet_id])
        self.assertEqual(transfer_entry_packet_ids, [packet_a.packet_id, packet_b.packet_id])
        self.assertTrue(
            all(packet.lifecycle_state == LifecycleState.COMPLETED for packet in engine.packets.values())
        )

    def test_queue_event_ordering(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
                "L2": Link(link_id="L2", free_flow_ticks=1),
            }
        )
        engine.set_receiving_open("L2", False)
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1", "L2"))
        )

        engine.step()
        engine.set_receiving_open("L2", True)
        engine.step()

        queue_entry_index = next(
            index
            for index, event in enumerate(engine.event_log)
            if event.packet_id == packet.packet_id
            and event.event_type == EventType.QUEUE_ENTRY
            and event.entity_id == "boundary:L1->L2"
        )
        queue_exit_index = next(
            index
            for index, event in enumerate(engine.event_log)
            if event.packet_id == packet.packet_id
            and event.event_type == EventType.QUEUE_EXIT
            and event.entity_id == "boundary:L1->L2"
        )
        link_exit_index = next(
            index
            for index, event in enumerate(engine.event_log)
            if event.packet_id == packet.packet_id
            and event.event_type == EventType.LINK_EXIT
            and event.entity_id == "L1"
        )
        link_entry_index = next(
            index
            for index, event in enumerate(engine.event_log)
            if event.packet_id == packet.packet_id
            and event.event_type == EventType.LINK_ENTRY
            and event.entity_id == "L2"
        )

        self.assertLess(queue_entry_index, queue_exit_index)
        self.assertLess(queue_exit_index, link_exit_index)
        self.assertLess(link_exit_index, link_entry_index)

    def test_conservation_with_queue(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
                "L2": Link(link_id="L2", free_flow_ticks=1),
            }
        )
        engine.set_receiving_open("L2", False)
        engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1", "L2"))
        )

        self.assert_conserved(engine)
        engine.step()
        self.assert_conserved(engine)
        engine.step()
        self.assert_conserved(engine)

        engine.set_receiving_open("L2", True)
        while any(
            packet.lifecycle_state != LifecycleState.COMPLETED
            for packet in engine.packets.values()
        ):
            engine.step()
            self.assert_conserved(engine)

    def test_queued_packet_remains_counted_on_upstream_link(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
                "L2": Link(link_id="L2", free_flow_ticks=1),
            }
        )
        engine.set_receiving_open("L2", False)
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1", "L2"))
        )

        engine.step()

        self.assertEqual(
            engine.packets[packet.packet_id].lifecycle_state,
            LifecycleState.QUEUED,
        )
        self.assertIn(packet.packet_id, engine.packet_ids_on_link("L1"))
        self.assertNotIn(packet.packet_id, engine.packet_ids_on_link("L2"))
        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), (packet.packet_id,))

    def test_receiving_state_belongs_to_engine(self) -> None:
        link = Link(link_id="L2", free_flow_ticks=1)
        engine = LoadingEngine(links={"L2": link})

        self.assertFalse(hasattr(link, "can_receive"))
        engine.set_receiving_open("L2", False)

        self.assertFalse(engine.is_receiving_open("L2"))
        self.assertEqual(link, engine.links["L2"])

    def test_closing_receiving_does_not_mutate_link_record(self) -> None:
        l2 = Link(link_id="L2", free_flow_ticks=1)
        engine = LoadingEngine(links={"L2": l2})
        stored_l2 = engine.links["L2"]

        engine.set_receiving_open("L2", False)

        self.assertEqual(stored_l2, engine.links["L2"])
        self.assertIs(stored_l2, engine.links["L2"])
        self.assertFalse(engine.is_receiving_open("L2"))

    def test_failed_transfer_queues_only_once(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
                "L2": Link(link_id="L2", free_flow_ticks=1),
            }
        )
        engine.set_receiving_open("L2", False)
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1", "L2"))
        )

        for _ in range(4):
            engine.step()

        queue_entry_events = [
            event
            for event in engine.event_log
            if event.packet_id == packet.packet_id
            and event.event_type == EventType.QUEUE_ENTRY
            and event.entity_id == "boundary:L1->L2"
        ]
        self.assertEqual(len(queue_entry_events), 1)

    def test_released_packet_cannot_exit_l2_in_same_tick(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
                "L2": Link(link_id="L2", free_flow_ticks=1),
            }
        )
        engine.set_receiving_open("L2", False)
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1", "L2"))
        )

        engine.step()
        engine.set_receiving_open("L2", True)
        engine.step()

        l2_entry_tick = next(
            event.physical_tick
            for event in engine.event_log
            if event.packet_id == packet.packet_id
            and event.event_type == EventType.LINK_ENTRY
            and event.entity_id == "L2"
        )
        self.assertFalse(
            [
                event
                for event in engine.event_log
                if event.packet_id == packet.packet_id
                and event.event_type == EventType.LINK_EXIT
                and event.entity_id == "L2"
                and event.physical_tick == l2_entry_tick
            ]
        )

        engine.step()
        self.assertTrue(
            [
                event
                for event in engine.event_log
                if event.packet_id == packet.packet_id
                and event.event_type == EventType.LINK_EXIT
                and event.entity_id == "L2"
                and event.physical_tick > l2_entry_tick
            ]
        )

    def assert_conserved(self, engine: LoadingEngine) -> None:
        summary = engine.conservation_summary()
        self.assertEqual(
            summary["instantiated"],
            summary["in_flight"]
            + summary["completed"]
            + summary["cancelled"]
            + summary["unresolved"],
        )


if __name__ == "__main__":
    unittest.main()
