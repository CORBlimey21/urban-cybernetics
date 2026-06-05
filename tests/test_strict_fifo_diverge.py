"""Strict-FIFO diverge policy tests for the minimal loading engine."""

from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import (
    DemandDeclaration,
    Event,
    EventType,
    LifecycleState,
    Link,
    Node,
)
from urban_cybernetics.loading import (
    GlobalFIFOMergePolicy,
    LoadingEngine,
    StrictFIFOJunctionPolicy,
    TransferCandidate,
)


class StrictFIFODivergeTest(unittest.TestCase):
    def test_diverge_follows_route_intent_to_first_outgoing_link(self) -> None:
        engine = self.build_diverge_engine()
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1", "L2"))
        )

        self.run_to_completion(engine)

        link_entries = [
            event.entity_id
            for event in self.events_for_packet(engine, packet.packet_id)
            if event.event_type == EventType.LINK_ENTRY
        ]
        self.assertEqual(link_entries, ["L1", "L2"])
        self.assertNotIn("L3", link_entries)
        self.assertEqual(
            engine.packets[packet.packet_id].lifecycle_state,
            LifecycleState.COMPLETED,
        )
        self.assertTrue(engine.check_conservation())

    def test_diverge_follows_route_intent_to_second_outgoing_link(self) -> None:
        engine = self.build_diverge_engine()
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1", "L3"))
        )

        self.run_to_completion(engine)

        link_entries = [
            event.entity_id
            for event in self.events_for_packet(engine, packet.packet_id)
            if event.event_type == EventType.LINK_ENTRY
        ]
        self.assertEqual(link_entries, ["L1", "L3"])
        self.assertNotIn("L2", link_entries)
        self.assertEqual(
            engine.packets[packet.packet_id].lifecycle_state,
            LifecycleState.COMPLETED,
        )
        self.assertTrue(engine.check_conservation())

    def test_closed_outgoing_link_queues_only_intended_packet(self) -> None:
        engine = self.build_diverge_engine()
        engine.set_receiving_open("L2", False)
        packet_a = engine.instantiate(
            DemandDeclaration(demand_id="D-A", departure_tick=0, route_intent=("L1", "L2"))
        )
        packet_b = engine.instantiate(
            DemandDeclaration(demand_id="D-B", departure_tick=0, route_intent=("L1", "L3"))
        )

        for _ in range(3):
            engine.step()

        blocked_tick = engine.current_tick
        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), (packet_a.packet_id,))
        self.assertEqual(engine.packet_ids_in_queue("L1", "L3"), ())
        self.assertFalse(
            [
                event
                for event in self.events_for_packet(engine, packet_a.packet_id)
                if event.event_type == EventType.LINK_EXIT
                and event.entity_id == "L1"
                and event.physical_tick <= blocked_tick
            ]
        )
        self.assertFalse(
            [
                event
                for event in self.events_for_packet(engine, packet_a.packet_id)
                if event.event_type == EventType.LINK_ENTRY
                and event.entity_id == "L2"
                and event.physical_tick <= blocked_tick
            ]
        )
        self.assertFalse(
            [
                event
                for event in self.events_for_packet(engine, packet_b.packet_id)
                if event.event_type == EventType.LINK_ENTRY
                and event.entity_id == "L3"
                and event.physical_tick <= blocked_tick
            ]
        )
        self.assertIn(packet_b.packet_id, engine.packet_ids_on_link("L1"))
        self.assertTrue(engine.check_conservation())

    def test_fifo_diverge_releases_blocked_packet_before_following_packet(self) -> None:
        engine = self.build_diverge_engine()
        engine.set_receiving_open("L2", False)
        packet_a = engine.instantiate(
            DemandDeclaration(demand_id="D-A", departure_tick=0, route_intent=("L1", "L2"))
        )
        packet_b = engine.instantiate(
            DemandDeclaration(demand_id="D-B", departure_tick=0, route_intent=("L1", "L3"))
        )

        engine.step()
        engine.set_receiving_open("L2", True)
        engine.step()

        packet_a_events = self.events_for_packet(engine, packet_a.packet_id)
        queue_exit_index = packet_a_events.index(
            self.event(engine, packet_a.packet_id, EventType.QUEUE_EXIT, "boundary:L1->L2")
        )
        link_exit_index = packet_a_events.index(
            self.event(engine, packet_a.packet_id, EventType.LINK_EXIT, "L1")
        )
        link_entry_index = packet_a_events.index(
            self.event(engine, packet_a.packet_id, EventType.LINK_ENTRY, "L2")
        )
        self.assertLess(queue_exit_index, link_exit_index)
        self.assertLess(link_exit_index, link_entry_index)

        a_l2_entry_tick = packet_a_events[link_entry_index].physical_tick
        self.assertFalse(
            [
                event
                for event in self.events_for_packet(engine, packet_b.packet_id)
                if event.event_type == EventType.LINK_ENTRY
                and event.entity_id == "L3"
                and event.physical_tick <= a_l2_entry_tick
            ]
        )

        engine.step()
        packet_b_l1_exit = self.event(engine, packet_b.packet_id, EventType.LINK_EXIT, "L1")
        packet_b_l3_entry = self.event(engine, packet_b.packet_id, EventType.LINK_ENTRY, "L3")
        self.assertGreater(packet_b_l1_exit.physical_tick, a_l2_entry_tick)
        self.assertEqual(packet_b_l1_exit.physical_tick, packet_b_l3_entry.physical_tick)

        self.run_to_completion(engine)
        self.assertEqual(
            engine.packets[packet_a.packet_id].lifecycle_state,
            LifecycleState.COMPLETED,
        )
        self.assertEqual(
            engine.packets[packet_b.packet_id].lifecycle_state,
            LifecycleState.COMPLETED,
        )
        self.assertTrue(engine.check_conservation())

    def test_diverge_policy_is_explicit(self) -> None:
        engine = self.build_diverge_engine()

        self.assertIsInstance(engine.node_transfer_policy, GlobalFIFOMergePolicy)
        self.assertIsInstance(engine.node_transfer_policy, StrictFIFOJunctionPolicy)
        self.assertTrue(hasattr(engine.node_transfer_policy, "choose_transfers"))

    def test_transfer_policy_batch_inputs_are_read_only(self) -> None:
        class CapturingPolicy:
            def __init__(self) -> None:
                self.candidates: tuple[TransferCandidate, ...] = ()
                self.receiving_slots_by_downstream_link = {}
                self.packet_ids_by_upstream_link = {}
                self.queued_downstream_by_packet_id = {}

            def choose_transfers(
                self,
                *,
                candidates,
                receiving_slots_by_downstream_link,
                packet_ids_by_upstream_link,
                queued_downstream_by_packet_id,
            ):
                self.candidates = candidates
                self.receiving_slots_by_downstream_link = receiving_slots_by_downstream_link
                self.packet_ids_by_upstream_link = packet_ids_by_upstream_link
                self.queued_downstream_by_packet_id = queued_downstream_by_packet_id
                return ()

        policy = CapturingPolicy()
        engine = LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
                "L2": Link(link_id="L2", free_flow_ticks=1),
            },
            node_transfer_policy=policy,
        )
        engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1", "L2"))
        )

        engine.step()

        self.assertEqual(len(policy.candidates), 1)
        with self.assertRaises(AttributeError):
            policy.candidates.append(policy.candidates[0])
        with self.assertRaises(FrozenInstanceError):
            policy.candidates[0].packet_id = "P-new"
        with self.assertRaises(TypeError):
            policy.receiving_slots_by_downstream_link["L2"] = 0
        with self.assertRaises(TypeError):
            policy.packet_ids_by_upstream_link["L1"] = ()
        with self.assertRaises(TypeError):
            policy.queued_downstream_by_packet_id["P-new"] = "L2"

    def build_diverge_engine(self) -> LoadingEngine:
        return LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
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

    def run_to_completion(self, engine: LoadingEngine) -> None:
        for _ in range(20):
            if all(
                packet.lifecycle_state == LifecycleState.COMPLETED
                for packet in engine.packets.values()
            ):
                return
            engine.step()
        self.fail("packet did not complete within expected synthetic test horizon")

    def events_for_packet(self, engine: LoadingEngine, packet_id: str) -> list[Event]:
        return [event for event in engine.event_log if event.packet_id == packet_id]

    def event(
        self,
        engine: LoadingEngine,
        packet_id: str,
        event_type: EventType,
        entity_id: str,
    ) -> Event:
        return next(
            event
            for event in engine.event_log
            if event.packet_id == packet_id
            and event.event_type == event_type
            and event.entity_id == entity_id
        )


if __name__ == "__main__":
    unittest.main()
