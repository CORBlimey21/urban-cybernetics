# SPDX-License-Identifier: MPL-2.0
"""Memory-hardening invariants for canonical loading records."""

from __future__ import annotations

import unittest

from urban_cybernetics.core import (
    DemandDeclaration,
    Event,
    EventType,
    LifecycleState,
    Link,
    Packet,
)
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.loading.cumulative_counts import (
    cumulative_entries,
    cumulative_exits,
)


class EventMemoryHardeningTest(unittest.TestCase):
    def test_event_records_preserve_equality_and_hashing_without_instance_dict(
        self,
    ) -> None:
        event_a = Event(
            sequence_number=1,
            packet_id="P1",
            event_type=EventType.LINK_ENTRY,
            entity_id="L1",
            physical_tick=3,
        )
        event_b = Event(
            sequence_number=1,
            packet_id="P1",
            event_type=EventType.LINK_ENTRY,
            entity_id="L1",
            physical_tick=3,
        )

        self.assertEqual(event_a, event_b)
        self.assertEqual(hash(event_a), hash(event_b))
        self.assertFalse(hasattr(event_a, "__dict__"))

    def test_packet_records_preserve_equality_and_hashing_without_instance_dict(
        self,
    ) -> None:
        packet_a = Packet("P1", "D1", ("L1", "L2"), LifecycleState.IN_TRANSIT)
        packet_b = Packet("P1", "D1", ("L1", "L2"), LifecycleState.IN_TRANSIT)

        self.assertEqual(packet_a, packet_b)
        self.assertEqual(hash(packet_a), hash(packet_b))
        self.assertFalse(hasattr(packet_a, "__dict__"))

    def test_event_log_iteration_and_indexing_semantics_are_preserved(self) -> None:
        engine = LoadingEngine(links={"L1": Link("L1", free_flow_ticks=1)})
        engine.instantiate(
            DemandDeclaration(
                demand_id="D1",
                departure_tick=0,
                route_intent=("L1",),
            )
        )

        event_log = engine.event_log

        self.assertIsInstance(event_log, tuple)
        self.assertEqual(event_log[0].event_type, EventType.INSTANTIATED)
        self.assertEqual(
            [event.event_type for event in event_log],
            [EventType.INSTANTIATED, EventType.LINK_ENTRY],
        )

    def test_materialised_cumulative_counts_match_event_log_truth(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link("L1", free_flow_ticks=1),
            }
        )
        engine.instantiate(
            DemandDeclaration(
                demand_id="D1",
                departure_tick=0,
                route_intent=("L1",),
            )
        )
        engine.step()

        self.assertTrue(engine.check_event_cache_consistency())
        for tick in range(engine.current_tick + 1):
            self.assertEqual(
                engine._cumulative_link_entries("L1", tick),
                cumulative_entries(engine.event_log, "L1", tick),
            )
            self.assertEqual(
                engine._cumulative_link_exits("L1", tick),
                cumulative_exits(engine.event_log, "L1", tick),
            )


if __name__ == "__main__":
    unittest.main()
