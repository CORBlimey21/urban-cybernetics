# SPDX-License-Identifier: MPL-2.0
"""Count-derived link storage view tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import DemandDeclaration, EventType, LifecycleState, Link, Node
from urban_cybernetics.loading import LoadingEngine, packet_ids_on_link_from_events


class LinkStorageViewsTest(unittest.TestCase):
    def test_single_link_storage_lifecycle(self) -> None:
        engine = LoadingEngine(links={"L1": Link(link_id="L1", free_flow_ticks=2)})
        engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1",))
        )

        self.assert_storage_equals_counts(engine, "L1", 0)
        self.assertEqual(engine.link_storage("L1", 0).storage, 1)

        engine.step()

        self.assert_storage_equals_counts(engine, "L1", 1)
        self.assertEqual(engine.link_storage("L1", 1).storage, 1)

        engine.step()

        self.assert_storage_equals_counts(engine, "L1", 2)
        self.assertEqual(engine.link_storage("L1", 2).storage, 0)

    def test_storage_is_non_negative_across_ticks(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
                "L2": Link(link_id="L2", free_flow_ticks=1),
                "L3": Link(link_id="L3", free_flow_ticks=1),
            }
        )
        for demand_number in range(3):
            engine.instantiate(
                DemandDeclaration(
                    demand_id=f"D{demand_number}",
                    departure_tick=0,
                    route_intent=("L1", "L2", "L3"),
                )
            )

        self.run_to_completion(engine)

        for link_id in ("L1", "L2", "L3"):
            for tick in range(engine.current_tick + 1):
                self.assertGreaterEqual(engine.link_storage(link_id, tick).storage, 0)

    def test_storage_equals_event_derived_packet_membership(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
                "L2": Link(link_id="L2", free_flow_ticks=1),
                "L3": Link(link_id="L3", free_flow_ticks=1),
            }
        )
        engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1", "L2", "L3"))
        )
        engine.instantiate(
            DemandDeclaration(demand_id="D2", departure_tick=0, route_intent=("L1", "L2", "L3"))
        )

        engine.step()

        for link_id in ("L1", "L2", "L3"):
            self.assertEqual(
                engine.link_storage(link_id).storage,
                len(engine.packet_ids_on_link(link_id)),
            )

        self.run_to_completion(engine)

        for link_id in ("L1", "L2", "L3"):
            for tick in range(engine.current_tick + 1):
                self.assertEqual(
                    engine.link_storage(link_id, tick).storage,
                    len(packet_ids_on_link_from_events(engine.event_log, link_id, tick)),
                )

    def test_queued_packet_remains_in_upstream_storage(self) -> None:
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

        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), (packet.packet_id,))
        self.assertEqual(engine.link_storage("L1", 1).storage, 1)
        self.assertEqual(engine.link_storage("L2", 1).storage, 0)
        self.assertFalse(self.has_event(engine, EventType.LINK_EXIT, "L1", 1))
        self.assertFalse(self.has_event(engine, EventType.LINK_ENTRY, "L2", 1))

        engine.set_receiving_open("L2", True)
        engine.step()

        self.assertEqual(engine.link_storage("L1", 2).storage, 0)
        self.assertEqual(engine.link_storage("L2", 2).storage, 1)

        engine.step()

        self.assertEqual(engine.link_storage("L2", 3).storage, 0)

    def test_diverge_storage_follows_realised_path(self) -> None:
        engine = self.build_diverge_engine()
        engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1", "L3"))
        )

        self.assertEqual(engine.link_storage("L1", 0).storage, 1)
        self.assertEqual(engine.link_storage("L2", 0).storage, 0)
        self.assertEqual(engine.link_storage("L3", 0).storage, 0)

        engine.step()

        self.assertEqual(engine.link_storage("L1", 1).storage, 0)
        self.assertEqual(engine.link_storage("L2", 1).storage, 0)
        self.assertEqual(engine.link_storage("L3", 1).storage, 1)

        self.run_to_completion(engine)

        for tick in range(engine.current_tick + 1):
            self.assertEqual(engine.link_storage("L2", tick).storage, 0)
        self.assertFalse(
            [
                event
                for event in engine.event_log
                if event.event_type == EventType.LINK_ENTRY and event.entity_id == "L2"
            ]
        )

    def test_merge_storage_respects_shared_downstream_capacity(self) -> None:
        engine = self.build_merge_engine(l3_receiving_capacity=1)
        packet_l1 = engine.instantiate(
            DemandDeclaration(demand_id="D-L1", departure_tick=0, route_intent=("L1", "L3"))
        )
        packet_l2 = engine.instantiate(
            DemandDeclaration(demand_id="D-L2", departure_tick=0, route_intent=("L2", "L3"))
        )

        l3_storage_before = engine.link_storage("L3", 0).storage
        engine.step()
        l3_packet_ids = packet_ids_on_link_from_events(engine.event_log, "L3", 1)
        l3_storage_after = engine.link_storage("L3", 1).storage

        self.assertLessEqual(l3_storage_after - l3_storage_before, 1)
        self.assertEqual(l3_storage_after, 1)

        non_admitted_packet_ids = {packet_l1.packet_id, packet_l2.packet_id} - set(
            l3_packet_ids
        )
        self.assertEqual(non_admitted_packet_ids, {packet_l2.packet_id})
        self.assertEqual(engine.link_storage("L2", 1).storage, 1)
        self.assertEqual(
            packet_ids_on_link_from_events(engine.event_log, "L2", 1),
            (packet_l2.packet_id,),
        )

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

    def assert_storage_equals_counts(
        self,
        engine: LoadingEngine,
        link_id: str,
        tick: int,
    ) -> None:
        counts = engine.cumulative_counts(link_id, tick)
        self.assertEqual(
            engine.link_storage(link_id, tick).storage,
            counts.entries - counts.exits,
        )

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

    def run_to_completion(self, engine: LoadingEngine) -> None:
        for _ in range(20):
            if all(
                packet.lifecycle_state == LifecycleState.COMPLETED
                for packet in engine.packets.values()
            ):
                return
            engine.step()
        self.fail("packets did not complete within expected synthetic test horizon")


if __name__ == "__main__":
    unittest.main()
