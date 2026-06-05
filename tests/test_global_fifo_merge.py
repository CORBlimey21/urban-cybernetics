"""Global-FIFO merge allocation tests for the minimal loading engine."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import DemandDeclaration, Event, EventType, LifecycleState, Link, Node
from urban_cybernetics.loading import GlobalFIFOMergePolicy, LoadingEngine


class GlobalFIFOMergeTest(unittest.TestCase):
    def test_merge_admits_from_both_incoming_links_when_capacity_allows(self) -> None:
        engine = self.build_merge_engine(l3_receiving_capacity=2)
        packet_l1 = engine.instantiate(
            DemandDeclaration(demand_id="D-L1", departure_tick=0, route_intent=("L1", "L3"))
        )
        packet_l2 = engine.instantiate(
            DemandDeclaration(demand_id="D-L2", departure_tick=0, route_intent=("L2", "L3"))
        )

        engine.step()

        l3_entries = self.link_entries(engine, "L3")
        self.assertEqual(
            [event.packet_id for event in l3_entries],
            [packet_l1.packet_id, packet_l2.packet_id],
        )
        self.assertEqual({event.physical_tick for event in l3_entries}, {1})
        self.assert_packet_uses_only_route_links(engine, packet_l1.packet_id, ("L1", "L3"))
        self.assert_packet_uses_only_route_links(engine, packet_l2.packet_id, ("L2", "L3"))

        self.run_to_completion(engine)
        self.assertTrue(
            all(
                packet.lifecycle_state == LifecycleState.COMPLETED
                for packet in engine.packets.values()
            )
        )
        self.assertTrue(engine.check_conservation())

    def test_merge_capacity_is_shared_across_incoming_links(self) -> None:
        engine = self.build_merge_engine(l3_receiving_capacity=1)
        packet_l1 = engine.instantiate(
            DemandDeclaration(demand_id="D-L1", departure_tick=0, route_intent=("L1", "L3"))
        )
        packet_l2 = engine.instantiate(
            DemandDeclaration(demand_id="D-L2", departure_tick=0, route_intent=("L2", "L3"))
        )

        engine.step()

        l3_entries = self.link_entries(engine, "L3")
        self.assertEqual(len(l3_entries), 1)
        self.assertEqual(l3_entries[0].packet_id, packet_l1.packet_id)
        self.assertEqual(l3_entries[0].physical_tick, 1)
        self.assertIn(packet_l2.packet_id, engine.packet_ids_on_link("L2"))
        self.assertFalse(
            [
                event
                for event in self.events_for_packet(engine, packet_l2.packet_id)
                if event.event_type == EventType.LINK_EXIT and event.entity_id == "L2"
            ]
        )
        self.assertTrue(engine.check_conservation())

    def test_global_fifo_chooses_earliest_eligible_packet_not_link_order(self) -> None:
        engine = self.build_merge_engine(
            l1_free_flow_ticks=2,
            l2_free_flow_ticks=1,
            l3_receiving_capacity=1,
        )
        engine.set_receiving_open("L3", False)
        packet_l1 = engine.instantiate(
            DemandDeclaration(demand_id="D-L1", departure_tick=0, route_intent=("L1", "L3"))
        )
        packet_l2 = engine.instantiate(
            DemandDeclaration(demand_id="D-L2", departure_tick=0, route_intent=("L2", "L3"))
        )

        engine.step()
        engine.step()
        engine.set_receiving_open("L3", True)
        engine.step()

        l3_entries = self.link_entries(engine, "L3")
        self.assertEqual(l3_entries[0].packet_id, packet_l2.packet_id)
        self.assertEqual(engine.packet_ids_in_queue("L1", "L3"), (packet_l1.packet_id,))
        self.assertTrue(engine.check_conservation())

    def test_merge_tie_break_is_event_sequence_number(self) -> None:
        engine = self.build_merge_engine(l3_receiving_capacity=1)
        packet_l1 = engine.instantiate(
            DemandDeclaration(demand_id="D-L1", departure_tick=0, route_intent=("L1", "L3"))
        )
        packet_l2 = engine.instantiate(
            DemandDeclaration(demand_id="D-L2", departure_tick=0, route_intent=("L2", "L3"))
        )

        engine.step()

        l3_entries = self.link_entries(engine, "L3")
        self.assertEqual(l3_entries[0].packet_id, packet_l1.packet_id)
        self.assertEqual(engine.packet_ids_in_queue("L2", "L3"), (packet_l2.packet_id,))

    def test_blocked_merge_packet_remains_on_upstream_link(self) -> None:
        engine = self.build_merge_engine(l3_receiving_capacity=1)
        engine.instantiate(
            DemandDeclaration(demand_id="D-L1", departure_tick=0, route_intent=("L1", "L3"))
        )
        packet_l2 = engine.instantiate(
            DemandDeclaration(demand_id="D-L2", departure_tick=0, route_intent=("L2", "L3"))
        )

        engine.step()

        self.assertEqual(engine.packet_ids_in_queue("L2", "L3"), (packet_l2.packet_id,))
        self.assertIn(packet_l2.packet_id, engine.packet_ids_on_link("L2"))
        self.assertFalse(
            [
                event
                for event in self.events_for_packet(engine, packet_l2.packet_id)
                if event.event_type == EventType.LINK_EXIT and event.entity_id == "L2"
            ]
        )
        self.assertFalse(
            [
                event
                for event in self.events_for_packet(engine, packet_l2.packet_id)
                if event.event_type == EventType.LINK_ENTRY and event.entity_id == "L3"
            ]
        )
        self.assertTrue(engine.check_conservation())

    def test_queue_release_preserves_global_fifo_across_incoming_links(self) -> None:
        engine = self.build_merge_engine(
            l1_free_flow_ticks=2,
            l2_free_flow_ticks=1,
            l3_receiving_capacity=1,
        )
        engine.set_receiving_open("L3", False)
        packet_l1 = engine.instantiate(
            DemandDeclaration(demand_id="D-L1", departure_tick=0, route_intent=("L1", "L3"))
        )
        packet_l2 = engine.instantiate(
            DemandDeclaration(demand_id="D-L2", departure_tick=0, route_intent=("L2", "L3"))
        )

        engine.step()
        engine.step()
        self.assertEqual(engine.packet_ids_in_queue("L2", "L3"), (packet_l2.packet_id,))
        self.assertEqual(engine.packet_ids_in_queue("L1", "L3"), (packet_l1.packet_id,))

        engine.set_receiving_open("L3", True)
        engine.step()
        engine.step()

        queue_exit_packet_ids = [
            event.packet_id
            for event in engine.event_log
            if event.event_type == EventType.QUEUE_EXIT
            and event.entity_id in ("boundary:L1->L3", "boundary:L2->L3")
        ]
        l3_entry_packet_ids = [event.packet_id for event in self.link_entries(engine, "L3")]
        self.assertEqual(queue_exit_packet_ids, [packet_l2.packet_id, packet_l1.packet_id])
        self.assertEqual(l3_entry_packet_ids, [packet_l2.packet_id, packet_l1.packet_id])
        self.assertTrue(engine.check_conservation())

    def test_merge_policy_is_explicit(self) -> None:
        engine = self.build_merge_engine(l3_receiving_capacity=1)

        self.assertIsInstance(engine.node_transfer_policy, GlobalFIFOMergePolicy)
        self.assertTrue(hasattr(engine.node_transfer_policy, "choose_transfers"))

    def build_merge_engine(
        self,
        *,
        l1_free_flow_ticks: int = 1,
        l2_free_flow_ticks: int = 1,
        l3_receiving_capacity: int,
    ) -> LoadingEngine:
        return LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=l1_free_flow_ticks),
                "L2": Link(link_id="L2", free_flow_ticks=l2_free_flow_ticks),
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

    def run_to_completion(self, engine: LoadingEngine) -> None:
        for _ in range(20):
            if all(
                packet.lifecycle_state == LifecycleState.COMPLETED
                for packet in engine.packets.values()
            ):
                return
            engine.step()
        self.fail("packets did not complete within expected synthetic test horizon")

    def link_entries(self, engine: LoadingEngine, link_id: str) -> list[Event]:
        return [
            event
            for event in engine.event_log
            if event.event_type == EventType.LINK_ENTRY and event.entity_id == link_id
        ]

    def events_for_packet(self, engine: LoadingEngine, packet_id: str) -> list[Event]:
        return [event for event in engine.event_log if event.packet_id == packet_id]

    def assert_packet_uses_only_route_links(
        self,
        engine: LoadingEngine,
        packet_id: str,
        route_intent: tuple[str, ...],
    ) -> None:
        link_entries = [
            event.entity_id
            for event in self.events_for_packet(engine, packet_id)
            if event.event_type == EventType.LINK_ENTRY
        ]
        self.assertEqual(link_entries, list(route_intent))


if __name__ == "__main__":
    unittest.main()
