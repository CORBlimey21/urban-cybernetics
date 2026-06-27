"""M3 parity sending tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.config import (
    ACADEMIC_LTM_PARITY_PROFILE_ID,
    DEFAULT_LOADING_PROFILE_ID,
    LEGACY_LOADING_PROFILE_ID,
)
from urban_cybernetics.core import DemandDeclaration, EventType, LifecycleState, Link
from urban_cybernetics.loading import (
    LoadingEngine,
    bounded_integer_capacity_carry,
)


class LTMParitySendingTest(unittest.TestCase):
    def test_legacy_profile_remains_default(self) -> None:
        engine = LoadingEngine(links={"L1": Link("L1", free_flow_ticks=1)})

        self.assertEqual(DEFAULT_LOADING_PROFILE_ID, LEGACY_LOADING_PROFILE_ID)
        self.assertEqual(engine.model_profile_id, LEGACY_LOADING_PROFILE_ID)

    def test_parity_sending_trace_uses_lagged_cumulative_entries(self) -> None:
        engine = self.parity_engine(
            links={"L1": Link("L1", free_flow_ticks=2, declared_sending_capacity_per_tick=2)}
        )
        packet = engine.instantiate(
            DemandDeclaration("D1", departure_tick=0, route_intent=("L1",))
        )

        trace_tick_1 = engine.parity_link_sending_trace("L1", tick=1)
        trace_tick_2 = engine.parity_link_sending_trace("L1", tick=2)

        self.assertEqual(trace_tick_1.lagged_entry_tick, -1)
        self.assertEqual(trace_tick_1.lagged_entry_count, 0)
        self.assertEqual(trace_tick_1.sendable_packet_ids, ())
        self.assertEqual(trace_tick_2.lagged_entry_tick, 0)
        self.assertEqual(trace_tick_2.lagged_entry_count, 1)
        self.assertEqual(trace_tick_2.ltm_sending_demand, 1)
        self.assertEqual(trace_tick_2.sendable_packet_ids, (packet.packet_id,))

    def test_parity_sending_selects_fifo_prefix_from_boundary_ordinals(self) -> None:
        engine = self.parity_engine(
            links={"L1": Link("L1", free_flow_ticks=1, declared_sending_capacity_per_tick=2)}
        )
        packets = [
            engine.instantiate(
                DemandDeclaration(
                    f"D{index}",
                    departure_tick=0,
                    route_intent=("L1",),
                )
            )
            for index in range(3)
        ]

        trace = engine.parity_link_sending_trace("L1", tick=1)

        self.assertEqual(
            trace.eligible_packet_ids,
            tuple(packet.packet_id for packet in packets),
        )
        self.assertEqual(
            trace.sendable_packet_ids,
            (packets[0].packet_id, packets[1].packet_id),
        )
        self.assertEqual(
            [ordinal.aggregate_ordinal for ordinal in trace.sendable_ordinals],
            [1, 2],
        )

    def test_parity_final_link_completion_uses_parity_sending(self) -> None:
        engine = self.parity_engine(
            links={"L1": Link("L1", free_flow_ticks=1, declared_sending_capacity_per_tick=1)}
        )
        packet_a = engine.instantiate(
            DemandDeclaration("D-A", departure_tick=0, route_intent=("L1",))
        )
        packet_b = engine.instantiate(
            DemandDeclaration("D-B", departure_tick=0, route_intent=("L1",))
        )

        engine.step()

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_EXIT, "L1", 1),
            [packet_a.packet_id],
        )
        self.assertEqual(
            engine.packets[packet_a.packet_id].lifecycle_state,
            LifecycleState.COMPLETED,
        )
        self.assertEqual(
            engine.packets[packet_b.packet_id].lifecycle_state,
            LifecycleState.IN_TRANSIT,
        )

    def test_bounded_integer_capacity_carry_preserves_long_horizon_capacity(self) -> None:
        carry = 0.0
        budgets: list[int] = []
        carries: list[float] = []

        for _ in range(4):
            state = bounded_integer_capacity_carry(
                link_id="L1",
                capacity_vehicles_per_tick=1.5,
                carry_in=carry,
            )
            budgets.append(state.integer_capacity)
            carries.append(state.carry_out)
            carry = state.carry_out

        self.assertEqual(budgets, [1, 2, 1, 2])
        self.assertEqual(sum(budgets), 6)
        self.assertEqual(carries, [0.5, 0.0, 0.5, 0.0])

    def test_parity_engine_uses_bounded_capacity_carry_for_fractional_rate(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(
                    "L1",
                    free_flow_ticks=1,
                    declared_sending_capacity_per_tick=99,
                )
            },
            model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
            parity_sending_capacity_vehicles_per_tick_by_link={"L1": 1.5},
        )
        packets = [
            engine.instantiate(
                DemandDeclaration(
                    f"D{index}",
                    departure_tick=0,
                    route_intent=("L1",),
                )
            )
            for index in range(3)
        ]

        engine.step()
        first_tick_trace = engine.parity_link_sending_trace("L1")
        engine.step()
        second_tick_trace = engine.parity_link_sending_trace("L1")

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_EXIT, "L1", 1),
            [packets[0].packet_id],
        )
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_EXIT, "L1", 2),
            [packets[1].packet_id, packets[2].packet_id],
        )
        self.assertEqual(first_tick_trace.capacity_vehicles_per_tick, 1.5)
        self.assertEqual(first_tick_trace.capacity_carry_out, 0.5)
        self.assertEqual(second_tick_trace.integer_capacity, 2)
        self.assertEqual(second_tick_trace.capacity_carry_in, 0.5)

    def test_parity_transfer_preserves_same_tick_exit_entry_order(self) -> None:
        engine = self.parity_engine(
            links={
                "L1": Link("L1", free_flow_ticks=1),
                "L2": Link("L2", free_flow_ticks=1),
            }
        )
        packet = engine.instantiate(
            DemandDeclaration("D1", departure_tick=0, route_intent=("L1", "L2"))
        )

        engine.step()

        packet_events = [
            event
            for event in engine.event_log
            if event.packet_id == packet.packet_id
        ]
        l1_exit = next(
            event
            for event in packet_events
            if event.event_type == EventType.LINK_EXIT and event.entity_id == "L1"
        )
        l2_entry = next(
            event
            for event in packet_events
            if event.event_type == EventType.LINK_ENTRY and event.entity_id == "L2"
        )
        self.assertEqual(l1_exit.physical_tick, l2_entry.physical_tick)
        self.assertLess(l1_exit.sequence_number, l2_entry.sequence_number)

    def test_parity_sending_does_not_change_receiving_blockage_semantics(self) -> None:
        engine = self.parity_engine(
            links={
                "L1": Link("L1", free_flow_ticks=1, declared_sending_capacity_per_tick=2),
                "L2": Link("L2", free_flow_ticks=1, declared_receiving_capacity_per_tick=1),
            }
        )
        engine.set_receiving_open("L2", False)
        packet = engine.instantiate(
            DemandDeclaration("D1", departure_tick=0, route_intent=("L1", "L2"))
        )

        engine.step()

        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), (packet.packet_id,))
        self.assertEqual(self.link_event_packet_ids(engine, EventType.LINK_EXIT, "L1", 1), [])
        self.assertEqual(self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 1), [])
        self.assertIn(packet.packet_id, engine.packet_ids_on_link("L1"))

    def test_parity_sending_trace_excludes_queued_packets(self) -> None:
        engine = self.parity_engine(
            links={
                "L1": Link("L1", free_flow_ticks=1, declared_sending_capacity_per_tick=2),
                "L2": Link("L2", free_flow_ticks=1),
            }
        )
        engine.set_receiving_open("L2", False)
        packet = engine.instantiate(
            DemandDeclaration("D1", departure_tick=0, route_intent=("L1", "L2"))
        )

        engine.step()
        trace = engine.parity_link_sending_trace(
            "L1",
            excluded_packet_ids=engine.packet_ids_in_queue("L1", "L2"),
        )

        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), (packet.packet_id,))
        self.assertNotIn(packet.packet_id, trace.eligible_packet_ids)
        self.assertNotIn(packet.packet_id, trace.sendable_packet_ids)

    def test_unsupported_loading_profile_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            LoadingEngine(
                links={"L1": Link("L1", free_flow_ticks=1)},
                model_profile_id="unknown",
            )

    def test_invalid_parity_sending_capacity_config_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            LoadingEngine(
                links={"L1": Link("L1", free_flow_ticks=1)},
                model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
                parity_sending_capacity_vehicles_per_tick_by_link={"L2": 1.0},
            )
        with self.assertRaises(ValueError):
            LoadingEngine(
                links={"L1": Link("L1", free_flow_ticks=1)},
                model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
                parity_sending_capacity_vehicles_per_tick_by_link={"L1": -0.1},
            )

    def parity_engine(self, *, links: dict[str, Link]) -> LoadingEngine:
        return LoadingEngine(
            links=links,
            model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        )

    def link_event_packet_ids(
        self,
        engine: LoadingEngine,
        event_type: EventType,
        link_id: str,
        tick: int,
    ) -> list[str]:
        return [
            event.packet_id
            for event in engine.event_log
            if event.event_type == event_type
            and event.entity_id == link_id
            and event.physical_tick == tick
        ]


if __name__ == "__main__":
    unittest.main()
