"""Architecture guardrails for the minimal loading engine."""

from __future__ import annotations

import unittest
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import DemandDeclaration, Event, EventType, LifecycleState, Link, Packet
from urban_cybernetics.loading import EventCacheConsistencyError, LoadingEngine


class EngineArchitectureTest(unittest.TestCase):
    def test_event_log_is_read_only_publicly(self) -> None:
        engine = LoadingEngine(links={"L1": Link(link_id="L1", free_flow_ticks=3)})
        engine.instantiate(DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1",)))

        self.assertIsInstance(engine.event_log, tuple)
        with self.assertRaises(AttributeError):
            engine.event_log.append(engine.event_log[0])

    def test_packet_registry_is_read_only_publicly(self) -> None:
        engine = LoadingEngine(links={"L1": Link(link_id="L1", free_flow_ticks=3)})
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1",))
        )

        with self.assertRaises(TypeError):
            engine.packets[packet.packet_id] = packet

    def test_lifecycle_cache_disagreement_is_detected(self) -> None:
        engine = LoadingEngine(links={"L1": Link(link_id="L1", free_flow_ticks=3)})
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1",))
        )

        engine.append_event(packet.packet_id, EventType.CANCELLED, "L1")

        with self.assertRaises(EventCacheConsistencyError):
            engine.check_event_cache_consistency()

    def test_packet_without_instantiation_event_is_detected(self) -> None:
        engine = LoadingEngine(links={"L1": Link(link_id="L1", free_flow_ticks=3)})
        engine._packets["P-missing"] = Packet(
            packet_id="P-missing",
            demand_id="D-missing",
            route_intent=("L1",),
            lifecycle_state=LifecycleState.IN_TRANSIT,
        )

        with self.assertRaises(EventCacheConsistencyError):
            engine.check_event_cache_consistency()

    def test_event_references_unknown_packet_is_detected(self) -> None:
        engine = LoadingEngine(links={"L1": Link(link_id="L1", free_flow_ticks=3)})
        engine._event_log.append(
            Event(
                sequence_number=0,
                packet_id="P-unknown",
                event_type=EventType.COMPLETED,
                entity_id="L1",
                physical_tick=0,
            )
        )

        with self.assertRaises(EventCacheConsistencyError):
            engine.check_event_cache_consistency()

    def test_sequence_numbers_monotonic(self) -> None:
        engine = LoadingEngine(links={"L1": Link(link_id="L1", free_flow_ticks=3)})
        packet = engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1",))
        )

        while engine.packets[packet.packet_id].lifecycle_state != LifecycleState.COMPLETED:
            engine.step()

        sequence_numbers = [event.sequence_number for event in engine.event_log]
        self.assertEqual(sequence_numbers, list(range(len(sequence_numbers))))
        self.assertTrue(engine.check_event_cache_consistency())

    def test_packet_is_frozen_or_externally_immutable(self) -> None:
        packet = Packet(
            packet_id="P1",
            demand_id="D1",
            route_intent=("L1",),
            lifecycle_state=LifecycleState.IN_TRANSIT,
        )

        with self.assertRaises(FrozenInstanceError):
            packet.lifecycle_state = LifecycleState.COMPLETED


if __name__ == "__main__":
    unittest.main()
