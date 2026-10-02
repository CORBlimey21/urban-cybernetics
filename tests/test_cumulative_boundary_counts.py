# SPDX-License-Identifier: MPL-2.0
"""Cumulative boundary count tests for event-derived loading views."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import (
    DemandDeclaration,
    EventType,
    LifecycleState,
    Link,
    Node,
)
from urban_cybernetics.loading import LoadingEngine


class CumulativeBoundaryCountsTest(unittest.TestCase):
    def test_single_link_counts_match_events(self) -> None:
        engine = LoadingEngine(links={"L1": Link(link_id="L1", free_flow_ticks=1)})
        engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1",))
        )

        self.assertEqual(engine.cumulative_entries("L1"), 1)
        self.assertEqual(engine.cumulative_exits("L1"), 0)
        self.assert_counts_match_raw_events(engine, ("L1",))

        engine.step()

        counts = engine.cumulative_counts("L1")
        self.assertEqual(counts.link_id, "L1")
        self.assertEqual(counts.tick, engine.current_tick)
        self.assertEqual(counts.entries, 1)
        self.assertEqual(counts.exits, 1)
        self.assert_counts_match_raw_events(engine, ("L1",))

    def test_counts_are_monotonic(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
                "L2": Link(link_id="L2", free_flow_ticks=1),
                "L3": Link(link_id="L3", free_flow_ticks=1),
            }
        )
        engine.instantiate(
            DemandDeclaration(
                demand_id="D1",
                departure_tick=0,
                route_intent=("L1", "L2", "L3"),
            )
        )
        engine.instantiate(
            DemandDeclaration(
                demand_id="D2",
                departure_tick=0,
                route_intent=("L1", "L2", "L3"),
            )
        )
        self.run_to_completion(engine)

        for link_id in ("L1", "L2", "L3"):
            series = engine.cumulative_count_series(link_id)
            for previous_counts, next_counts in zip(series, series[1:]):
                self.assertGreaterEqual(next_counts.entries, previous_counts.entries)
                self.assertGreaterEqual(next_counts.exits, previous_counts.exits)

    def test_exits_never_exceed_entries(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
                "L2": Link(link_id="L2", free_flow_ticks=1),
                "L3": Link(link_id="L3", free_flow_ticks=1),
            }
        )
        engine.instantiate(
            DemandDeclaration(
                demand_id="D1",
                departure_tick=0,
                route_intent=("L1", "L2", "L3"),
            )
        )
        self.run_to_completion(engine)

        for link_id in ("L1", "L2", "L3"):
            for tick in range(engine.current_tick + 1):
                self.assertLessEqual(
                    engine.cumulative_exits(link_id, tick),
                    engine.cumulative_entries(link_id, tick),
                )

    def test_queued_packet_does_not_increment_boundary_counts(self) -> None:
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
        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), (packet.packet_id,))
        self.assertEqual(engine.cumulative_entries("L1"), 1)
        self.assertEqual(engine.cumulative_exits("L1"), 0)
        self.assertEqual(engine.cumulative_entries("L2"), 0)
        self.assertEqual(engine.cumulative_exits("L2"), 0)

        engine.set_receiving_open("L2", True)
        engine.step()

        self.assertEqual(engine.cumulative_exits("L1"), 1)
        self.assertEqual(engine.cumulative_entries("L2"), 1)

    def test_merge_counts_respect_shared_downstream_receiving_capacity(self) -> None:
        engine = self.build_merge_engine(l3_receiving_capacity=1)
        engine.instantiate(
            DemandDeclaration(demand_id="D-L1", departure_tick=0, route_intent=("L1", "L3"))
        )
        engine.instantiate(
            DemandDeclaration(demand_id="D-L2", departure_tick=0, route_intent=("L2", "L3"))
        )

        before_tick_entries = engine.cumulative_entries("L3", 0)
        engine.step()
        after_tick_entries = engine.cumulative_entries("L3", 1)

        self.assertLessEqual(after_tick_entries - before_tick_entries, 1)
        self.assertEqual(engine.cumulative_entries("L3", 1), 1)

    def test_counts_match_event_log_after_diverge_and_merge(self) -> None:
        diverge_engine = self.build_diverge_engine()
        diverge_engine.instantiate(
            DemandDeclaration(demand_id="D-L2", departure_tick=0, route_intent=("L1", "L2"))
        )
        diverge_engine.instantiate(
            DemandDeclaration(demand_id="D-L3", departure_tick=0, route_intent=("L1", "L3"))
        )
        self.run_to_completion(diverge_engine)

        merge_engine = self.build_merge_engine(l3_receiving_capacity=1)
        merge_engine.instantiate(
            DemandDeclaration(demand_id="D-L1", departure_tick=0, route_intent=("L1", "L3"))
        )
        merge_engine.instantiate(
            DemandDeclaration(demand_id="D-L2", departure_tick=0, route_intent=("L2", "L3"))
        )
        self.run_to_completion(merge_engine)

        self.assert_counts_match_raw_events(diverge_engine, ("L1", "L2", "L3"))
        self.assert_counts_match_raw_events(merge_engine, ("L1", "L2", "L3"))

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

    def run_to_completion(self, engine: LoadingEngine) -> None:
        for _ in range(20):
            if all(
                packet.lifecycle_state == LifecycleState.COMPLETED
                for packet in engine.packets.values()
            ):
                return
            engine.step()
        self.fail("packets did not complete within expected synthetic test horizon")

    def assert_counts_match_raw_events(
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


if __name__ == "__main__":
    unittest.main()
