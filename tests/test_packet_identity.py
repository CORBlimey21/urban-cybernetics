"""Packet identity stability invariant tests."""

from __future__ import annotations

import unittest
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import DemandDeclaration, LifecycleState, Link
from urban_cybernetics.loading import LoadingEngine


class PacketIdentityTest(unittest.TestCase):
    def test_packet_identity_stable(self) -> None:
        engine = LoadingEngine(links={"L1": Link(link_id="L1", free_flow_ticks=3)})
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1",))
        )
        original_packet_id = packet.packet_id

        while engine.packets[original_packet_id].lifecycle_state != LifecycleState.COMPLETED:
            engine.step()

        self.assertEqual(engine.packets[original_packet_id].packet_id, original_packet_id)
        self.assertEqual({event.packet_id for event in engine.event_log}, {original_packet_id})


if __name__ == "__main__":
    unittest.main()
