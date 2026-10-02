# SPDX-License-Identifier: MPL-2.0
"""General route progression tests without new traffic physics."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import DemandDeclaration, EventType, LifecycleState, Link
from urban_cybernetics.loading import EventCacheConsistencyError, LoadingEngine


class RouteProgressionTest(unittest.TestCase):
    def test_three_link_route_completes(self) -> None:
        engine = self.build_engine("L1", "L2", "L3")
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1", "L2", "L3"))
        )

        self.run_to_completion(engine)

        self.assertEqual(
            [(event.event_type, event.entity_id) for event in engine.event_log],
            [
                (EventType.INSTANTIATED, "L1"),
                (EventType.LINK_ENTRY, "L1"),
                (EventType.LINK_EXIT, "L1"),
                (EventType.LINK_ENTRY, "L2"),
                (EventType.LINK_EXIT, "L2"),
                (EventType.LINK_ENTRY, "L3"),
                (EventType.LINK_EXIT, "L3"),
                (EventType.COMPLETED, "L3"),
            ],
        )
        self.assertEqual({event.packet_id for event in engine.event_log}, {packet.packet_id})
        self.assertTrue(engine.check_conservation())

    def test_three_link_route_respects_one_boundary_per_tick(self) -> None:
        engine = self.build_engine("L1", "L2", "L3")
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1", "L2", "L3"))
        )

        self.run_to_completion(engine)

        link_exits_by_tick: dict[int, list[str]] = {}
        for event in engine.event_log:
            if event.event_type == EventType.LINK_EXIT:
                link_exits_by_tick.setdefault(event.physical_tick, []).append(event.entity_id)

        self.assertTrue(
            all(len(link_ids) <= 1 for link_ids in link_exits_by_tick.values())
        )
        l2_entry_tick = self.event_tick(engine, packet.packet_id, EventType.LINK_ENTRY, "L2")
        self.assertNotIn(
            ("L2", l2_entry_tick),
            [
                (event.entity_id, event.physical_tick)
                for event in engine.event_log
                if event.event_type == EventType.LINK_EXIT
            ],
        )

    def test_queue_on_middle_boundary_of_three_link_route(self) -> None:
        engine = self.build_engine("L1", "L2", "L3")
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1", "L2", "L3"))
        )

        engine.step()
        engine.set_receiving_open("L3", False)
        engine.step()
        engine.step()

        blocked_tick = engine.current_tick
        self.assertEqual(engine.packet_ids_in_queue("L2", "L3"), (packet.packet_id,))
        self.assertIn(packet.packet_id, engine.packet_ids_on_link("L2"))
        self.assertNotIn(packet.packet_id, engine.packet_ids_on_link("L3"))
        self.assertFalse(
            [
                event
                for event in engine.event_log
                if event.event_type == EventType.LINK_EXIT
                and event.entity_id == "L2"
                and event.physical_tick <= blocked_tick
            ]
        )
        self.assertFalse(
            [
                event
                for event in engine.event_log
                if event.event_type == EventType.LINK_ENTRY
                and event.entity_id == "L3"
                and event.physical_tick <= blocked_tick
            ]
        )

        engine.set_receiving_open("L3", True)
        engine.step()

        ordered_transfer_events = [
            (event.event_type, event.entity_id)
            for event in engine.event_log
            if event.packet_id == packet.packet_id
            and (
                event.entity_id == "boundary:L2->L3"
                or event.entity_id in ("L2", "L3")
            )
        ]
        queue_exit_index = ordered_transfer_events.index(
            (EventType.QUEUE_EXIT, "boundary:L2->L3")
        )
        link_exit_index = ordered_transfer_events.index((EventType.LINK_EXIT, "L2"))
        link_entry_index = ordered_transfer_events.index((EventType.LINK_ENTRY, "L3"))
        self.assertLess(queue_exit_index, link_exit_index)
        self.assertLess(link_exit_index, link_entry_index)

        self.run_to_completion(engine)
        self.assertEqual(
            engine.packets[packet.packet_id].lifecycle_state,
            LifecycleState.COMPLETED,
        )
        self.assertTrue(engine.check_conservation())

    def test_four_link_route_completes_without_route_length_special_case(self) -> None:
        engine = self.build_engine("L1", "L2", "L3", "L4")
        packet = engine.instantiate(
            DemandDeclaration(
                demand_id="D1",
                departure_tick=0,
                route_intent=("L1", "L2", "L3", "L4"),
            )
        )

        self.run_to_completion(engine)

        link_events = [
            (event.event_type, event.entity_id)
            for event in engine.event_log
            if event.event_type in (EventType.LINK_ENTRY, EventType.LINK_EXIT)
        ]
        self.assertEqual(
            link_events,
            [
                (EventType.LINK_ENTRY, "L1"),
                (EventType.LINK_EXIT, "L1"),
                (EventType.LINK_ENTRY, "L2"),
                (EventType.LINK_EXIT, "L2"),
                (EventType.LINK_ENTRY, "L3"),
                (EventType.LINK_EXIT, "L3"),
                (EventType.LINK_ENTRY, "L4"),
                (EventType.LINK_EXIT, "L4"),
            ],
        )
        self.assertEqual(
            engine.packets[packet.packet_id].lifecycle_state,
            LifecycleState.COMPLETED,
        )

    def test_route_index_cache_consistency(self) -> None:
        engine = self.build_engine("L1", "L2", "L3")
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1", "L2", "L3"))
        )

        self.run_to_completion(engine)

        self.assertEqual(engine._packet_route_index[packet.packet_id], 2)
        self.assertTrue(engine.check_event_cache_consistency())

        engine._packet_route_index[packet.packet_id] = 0
        with self.assertRaises(EventCacheConsistencyError):
            engine.check_event_cache_consistency()

    def build_engine(self, *link_ids: str) -> LoadingEngine:
        return LoadingEngine(
            links={
                link_id: Link(link_id=link_id, free_flow_ticks=1)
                for link_id in link_ids
            }
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

    def event_tick(
        self,
        engine: LoadingEngine,
        packet_id: str,
        event_type: EventType,
        entity_id: str,
    ) -> int:
        return next(
            event.physical_tick
            for event in engine.event_log
            if event.packet_id == packet_id
            and event.event_type == event_type
            and event.entity_id == entity_id
        )


if __name__ == "__main__":
    unittest.main()
