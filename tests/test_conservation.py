"""Simplified whole-network conservation tests."""

from __future__ import annotations

import unittest
import sys
from dataclasses import replace
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import DemandDeclaration, LifecycleState, Link
from urban_cybernetics.loading import EventCacheConsistencyError, LoadingEngine


class ConservationTest(unittest.TestCase):
    def test_conservation_single_packet(self) -> None:
        engine = LoadingEngine(links={"L1": Link(link_id="L1", free_flow_ticks=3)})
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1",))
        )

        while engine.packets[packet.packet_id].lifecycle_state != LifecycleState.COMPLETED:
            engine.step()

        self.assertTrue(engine.check_conservation())
        self.assertEqual(
            engine.conservation_summary(),
            {
                "instantiated": 1,
                "in_flight": 0,
                "completed": 1,
                "cancelled": 0,
            },
        )

    def test_conservation_derived_from_events(self) -> None:
        engine = LoadingEngine(links={"L1": Link(link_id="L1", free_flow_ticks=3)})
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1",))
        )

        while engine.packets[packet.packet_id].lifecycle_state != LifecycleState.COMPLETED:
            engine.step()

        engine._packets[packet.packet_id] = replace(
            engine._packets[packet.packet_id],
            lifecycle_state=LifecycleState.IN_TRANSIT,
        )

        with self.assertRaises(EventCacheConsistencyError):
            engine.conservation_summary()


if __name__ == "__main__":
    unittest.main()
