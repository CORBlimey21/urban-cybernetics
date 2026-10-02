# SPDX-License-Identifier: MPL-2.0
"""Single-packet lifecycle and timestep semantics tests."""

from __future__ import annotations

import unittest
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import DemandDeclaration, EventType, LifecycleState, Link
from urban_cybernetics.loading import LoadingEngine


class SinglePacketCompletionTest(unittest.TestCase):
    def test_single_packet_completion(self) -> None:
        engine = LoadingEngine(links={"L1": Link(link_id="L1", free_flow_ticks=3)})
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1",))
        )

        engine.step()
        engine.step()
        self.assertEqual(
            engine.packets[packet.packet_id].lifecycle_state,
            LifecycleState.IN_TRANSIT,
        )

        engine.step()
        self.assertEqual(
            engine.packets[packet.packet_id].lifecycle_state,
            LifecycleState.COMPLETED,
        )
        self.assertEqual(
            [event.event_type for event in engine.event_log],
            [
                EventType.INSTANTIATED,
                EventType.LINK_ENTRY,
                EventType.LINK_EXIT,
                EventType.COMPLETED,
            ],
        )


if __name__ == "__main__":
    unittest.main()
