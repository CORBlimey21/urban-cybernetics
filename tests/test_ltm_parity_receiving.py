"""M4 parity receiving and vacancy tests."""

from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MethodType


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import DemandDeclaration, EventType, LifecycleState, Link
from urban_cybernetics.loading import (
    LoadingEngine,
    ReceivingCause,
    bounded_integer_receiving_capacity_carry,
)


class LTMParityReceivingTest(unittest.TestCase):
    def test_parity_supply_uses_backward_wave_lagged_downstream_exits(self) -> None:
        engine = self.parity_engine(
            links={
                "L1": self.physical_link("L1", storage=5, receiving_capacity=5),
                "L2": self.physical_link("L2", storage=1, receiving_capacity=5),
            }
        )
        blocker = engine.instantiate(
            DemandDeclaration("D-BLOCKER", departure_tick=0, route_intent=("L2",))
        )
        upstream = engine.instantiate(
            DemandDeclaration("D-UP", departure_tick=0, route_intent=("L1", "L2"))
        )

        engine.step()
        tick_1_supply = engine.parity_link_supply_view("L2")
        engine.step()
        tick_2_supply = engine.parity_link_supply_view("L2")
        engine.step()

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_EXIT, "L2", 1),
            [blocker.packet_id],
        )
        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), ())
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 1),
            [],
        )
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 2),
            [],
        )
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 3),
            [upstream.packet_id],
        )
        self.assertEqual(tick_1_supply.vacancy.backward_wave_lag_ticks, 2)
        self.assertEqual(tick_1_supply.vacancy.lagged_downstream_exit_tick, -1)
        self.assertEqual(tick_1_supply.receiving_cause, ReceivingCause.PHYSICAL_SHORTAGE)
        self.assertEqual(tick_2_supply.vacancy.lagged_downstream_exit_tick, 0)
        self.assertEqual(tick_2_supply.receiving_cause, ReceivingCause.PHYSICAL_SHORTAGE)
        self.assertTrue(engine.check_conservation())

    def test_parity_supply_distinguishes_physical_shortage_from_governance_closure(
        self,
    ) -> None:
        engine = self.parity_engine(
            links={"L1": self.physical_link("L1", storage=1, receiving_capacity=5)}
        )
        engine.instantiate(
            DemandDeclaration("D1", departure_tick=0, route_intent=("L1",))
        )

        open_supply = engine.parity_link_supply_view("L1")
        engine.set_receiving_open("L1", False)
        closed_supply = engine.parity_link_supply_view("L1")

        self.assertEqual(open_supply.receiving_cause, ReceivingCause.PHYSICAL_SHORTAGE)
        self.assertEqual(
            closed_supply.receiving_cause,
            ReceivingCause.GOVERNANCE_CLOSED,
        )
        self.assertEqual(open_supply.available_receiving_slots, 0)
        self.assertEqual(closed_supply.available_receiving_slots, 0)

    def test_fractional_parity_receiving_capacity_uses_bounded_carry(self) -> None:
        carry = 0.0
        budgets: list[int] = []
        carries: list[float] = []
        for _ in range(4):
            integer_capacity, carry = bounded_integer_receiving_capacity_carry(
                link_id="L2",
                capacity_vehicles_per_tick=1.5,
                carry_in=carry,
            )
            budgets.append(integer_capacity)
            carries.append(carry)

        self.assertEqual(budgets, [1, 2, 1, 2])
        self.assertEqual(carries, [0.5, 0.0, 0.5, 0.0])

    def test_parity_engine_uses_fractional_receiving_capacity_for_transfers(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": self.physical_link("L1", storage=5, sending_capacity=5),
                "L2": self.physical_link("L2", storage=5, receiving_capacity=5),
            },
            model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
            parity_receiving_capacity_vehicles_per_tick_by_link={"L2": 1.5},
        )
        packets = [
            engine.instantiate(
                DemandDeclaration(
                    f"D{index}",
                    departure_tick=0,
                    route_intent=("L1", "L2"),
                )
            )
            for index in range(3)
        ]

        engine.step()
        first_tick_supply = engine.parity_link_supply_view("L2")
        engine.step()
        second_tick_supply = engine.parity_link_supply_view("L2")

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 1),
            [packets[0].packet_id],
        )
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 2),
            [packets[1].packet_id, packets[2].packet_id],
        )
        self.assertEqual(first_tick_supply.receiving_capacity_vehicles_per_tick, 1.5)
        self.assertEqual(first_tick_supply.receiving_capacity_carry_out, 0.5)
        self.assertEqual(second_tick_supply.integer_receiving_capacity, 2)
        self.assertEqual(second_tick_supply.receiving_capacity_carry_in, 0.5)
        self.assertTrue(engine.check_conservation())

    def test_parity_origin_admission_uses_lagged_vacancy_supply(self) -> None:
        engine = self.parity_engine(
            links={"L1": self.physical_link("L1", storage=1, receiving_capacity=5)}
        )
        first = engine.instantiate(
            DemandDeclaration("D1", departure_tick=0, route_intent=("L1",))
        )
        second = engine.instantiate(
            DemandDeclaration("D2", departure_tick=0, route_intent=("L1",))
        )

        self.assertIsNone(second)
        self.assertEqual(engine.pending_demands[0].demand_id, "D2")
        engine.step()
        engine.step()
        self.assertEqual(len(engine.pending_demands), 1)
        engine.step()

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_EXIT, "L1", 1),
            [first.packet_id],
        )
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L1", 3),
            ["P2"],
        )
        self.assertEqual(len(engine.pending_demands), 0)

    def test_pending_origin_admission_preserves_same_origin_order(self) -> None:
        engine = self.parity_engine(
            links={"L1": self.physical_link("L1", storage=2, receiving_capacity=2)}
        )
        first = engine.instantiate(
            DemandDeclaration("D1", departure_tick=0, route_intent=("L1",))
        )
        second = engine.instantiate(
            DemandDeclaration("D2", departure_tick=0, route_intent=("L1",))
        )
        self.assertIsNone(
            engine.instantiate(
                DemandDeclaration("D3", departure_tick=0, route_intent=("L1",))
            )
        )
        self.assertIsNone(
            engine.instantiate(
                DemandDeclaration("D4", departure_tick=0, route_intent=("L1",))
            )
        )

        for _ in range(3):
            engine.step()

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_EXIT, "L1", 1),
            [first.packet_id, second.packet_id],
        )
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L1", 3),
            ["P3", "P4"],
        )
        self.assertEqual(engine.pending_demands, ())

    def test_pending_origin_admission_preserves_global_order_across_origins(self) -> None:
        engine = self.parity_engine(
            links={
                "L1": self.physical_link("L1", storage=1, receiving_capacity=1),
                "L2": self.physical_link("L2", storage=1, receiving_capacity=1),
            }
        )
        engine.instantiate(DemandDeclaration("D-fill-1", 0, ("L1",)))
        engine.instantiate(DemandDeclaration("D-fill-2", 0, ("L2",)))
        for demand_id, link_id in (
            ("D1", "L1"),
            ("D2", "L2"),
            ("D3", "L1"),
            ("D4", "L2"),
        ):
            self.assertIsNone(
                engine.instantiate(
                    DemandDeclaration(demand_id, 0, (link_id,)),
                )
            )

        for _ in range(3):
            engine.step()

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L1", 3),
            ["P3"],
        )
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 3),
            ["P4"],
        )
        self.assertEqual(
            tuple(demand.demand_id for demand in engine.pending_demands),
            ("D3", "D4"),
        )
        self.assertEqual(
            [
                event.packet_id
                for event in engine.event_log
                if event.event_type == EventType.LINK_ENTRY
                and event.physical_tick == 3
            ],
            ["P3", "P4"],
        )

    def test_batched_pending_origin_admission_matches_naive_one_by_one(self) -> None:
        batched = self.parity_engine(
            links={
                "L1": self.physical_link("L1", storage=2, receiving_capacity=2),
                "L2": self.physical_link("L2", storage=1, receiving_capacity=1),
            }
        )
        naive = self.parity_engine(
            links={
                "L1": self.physical_link("L1", storage=2, receiving_capacity=2),
                "L2": self.physical_link("L2", storage=1, receiving_capacity=1),
            }
        )
        naive._instantiate_pending_departures = MethodType(  # noqa: SLF001
            type(self)._naive_instantiate_pending_departures,
            naive,
        )
        demands = (
            DemandDeclaration("D-fill-1a", 0, ("L1",)),
            DemandDeclaration("D-fill-1b", 0, ("L1",)),
            DemandDeclaration("D-fill-2", 0, ("L2",)),
            DemandDeclaration("D1", 0, ("L1",)),
            DemandDeclaration("D2", 0, ("L2",)),
            DemandDeclaration("D3", 0, ("L1",)),
            DemandDeclaration("D4", 0, ("L2",)),
        )
        for demand in demands:
            batched.instantiate(demand)
            naive.instantiate(demand)

        for _ in range(6):
            batched.step()
            naive.step()

        self.assertEqual(batched.event_log, naive.event_log)
        self.assertEqual(tuple(batched.packets), tuple(naive.packets))
        self.assertEqual(batched.pending_demands, naive.pending_demands)

    def test_pending_origin_admission_honours_receiving_slot_exhaustion(self) -> None:
        engine = self.parity_engine(
            links={"L1": self.physical_link("L1", storage=10, receiving_capacity=1)}
        )
        engine.instantiate(DemandDeclaration("D1", 0, ("L1",)))
        self.assertIsNone(engine.instantiate(DemandDeclaration("D2", 0, ("L1",))))
        self.assertIsNone(engine.instantiate(DemandDeclaration("D3", 0, ("L1",))))

        engine.step()

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L1", 1),
            ["P2"],
        )
        self.assertEqual(
            tuple(demand.demand_id for demand in engine.pending_demands),
            ("D3",),
        )

    def test_parity_receiving_preserves_fifo_and_same_tick_event_order(self) -> None:
        engine = self.parity_engine(
            links={
                "L1": self.physical_link("L1", storage=5, sending_capacity=5),
                "L2": self.physical_link("L2", storage=5, receiving_capacity=5),
            }
        )
        engine.set_receiving_open("L2", False)
        packets = [
            engine.instantiate(
                DemandDeclaration(
                    f"D{index}",
                    departure_tick=0,
                    route_intent=("L1", "L2"),
                )
            )
            for index in range(2)
        ]
        engine.step()
        engine.set_receiving_open("L2", True)
        engine.step()

        self.assertEqual(
            self.queue_exit_packet_ids(engine, 2),
            [packet.packet_id for packet in packets],
        )
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 2),
            [packet.packet_id for packet in packets],
        )
        for packet in packets:
            event_order = [
                event.event_type
                for event in engine.event_log
                if event.packet_id == packet.packet_id and event.physical_tick == 2
            ]
            self.assertEqual(
                event_order,
                [EventType.QUEUE_EXIT, EventType.LINK_EXIT, EventType.LINK_ENTRY],
            )
        self.assertTrue(engine.check_conservation())

    def test_parity_receiving_keeps_sendable_packet_upstream_when_supply_is_short(
        self,
    ) -> None:
        engine = self.parity_engine(
            links={
                "L1": self.physical_link("L1", storage=5, sending_capacity=5),
                "L2": self.physical_link("L2", storage=1, receiving_capacity=5),
            }
        )
        blocker = engine.instantiate(
            DemandDeclaration("D-BLOCKER", departure_tick=0, route_intent=("L2",))
        )
        upstream = engine.instantiate(
            DemandDeclaration("D-UP", departure_tick=0, route_intent=("L1", "L2"))
        )

        engine.step()
        sending_trace = engine.parity_link_sending_trace(
            "L1",
            excluded_packet_ids=engine.packet_ids_in_queue("L1", "L2"),
        )

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_EXIT, "L2", 1),
            [blocker.packet_id],
        )
        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), (upstream.packet_id,))
        self.assertIn(upstream.packet_id, engine.packet_ids_on_link("L1"))
        self.assertNotIn(upstream.packet_id, sending_trace.sendable_packet_ids)
        self.assertEqual(engine.packets[upstream.packet_id].lifecycle_state, LifecycleState.QUEUED)

    def test_parity_receiving_view_is_frozen(self) -> None:
        engine = self.parity_engine(
            links={"L1": self.physical_link("L1", storage=5, receiving_capacity=5)}
        )

        supply = engine.parity_link_supply_view("L1")

        with self.assertRaises(FrozenInstanceError):
            supply.available_receiving_slots = 99

    def test_missing_backward_wave_metadata_is_rejected_for_parity_receiving(self) -> None:
        engine = LoadingEngine(
            links={"L1": Link("L1", free_flow_ticks=1)},
            model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        )

        with self.assertRaises(ValueError):
            engine.parity_link_supply_view("L1")

    def test_legacy_profile_does_not_require_backward_wave_metadata(self) -> None:
        engine = LoadingEngine(links={"L1": Link("L1", free_flow_ticks=1)})
        packet = engine.instantiate(
            DemandDeclaration("D1", departure_tick=0, route_intent=("L1",))
        )

        engine.step()

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_EXIT, "L1", 1),
            [packet.packet_id],
        )

    def test_invalid_parity_receiving_capacity_config_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            LoadingEngine(
                links={"L1": self.physical_link("L1")},
                model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
                parity_receiving_capacity_vehicles_per_tick_by_link={"L2": 1.0},
            )
        with self.assertRaises(ValueError):
            LoadingEngine(
                links={"L1": self.physical_link("L1")},
                model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
                parity_receiving_capacity_vehicles_per_tick_by_link={"L1": -0.1},
            )

    def parity_engine(self, *, links: dict[str, Link]) -> LoadingEngine:
        return LoadingEngine(
            links=links,
            model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        )

    def _naive_instantiate_pending_departures(self: LoadingEngine) -> None:
        if not self._pending_demands:  # noqa: SLF001
            return

        still_pending = []
        self._pending_demand_ids.clear()  # noqa: SLF001
        for demand in self._pending_demands:  # noqa: SLF001
            if demand.departure_tick > self.current_tick:
                still_pending.append(demand)
                self._pending_demand_ids.add(demand.demand_id)  # noqa: SLF001
                continue

            first_link_id = demand.route_intent[0]
            if self._origin_link_has_storage_for_entry(first_link_id):  # noqa: SLF001
                self._instantiate_now(demand)  # noqa: SLF001
            else:
                still_pending.append(demand)
                self._pending_demand_ids.add(demand.demand_id)  # noqa: SLF001
        self._pending_demands = still_pending  # noqa: SLF001

    def physical_link(
        self,
        link_id: str,
        *,
        storage: int = 5,
        sending_capacity: int = 5,
        receiving_capacity: int = 5,
    ) -> Link:
        return Link(
            link_id=link_id,
            free_flow_ticks=1,
            declared_sending_capacity_per_tick=sending_capacity,
            declared_receiving_capacity_per_tick=receiving_capacity,
            declared_storage_capacity_packets=storage,
            length_m=10.0,
            lane_count=1,
            free_flow_speed_mps=10.0,
            jam_density_veh_per_km_per_lane=100.0,
            backward_wave_speed_mps=5.0,
            capacity_veh_per_hour_per_lane=1200.0,
            tick_duration_seconds=1.0,
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

    def queue_exit_packet_ids(self, engine: LoadingEngine, tick: int) -> list[str]:
        return [
            event.packet_id
            for event in engine.event_log
            if event.event_type == EventType.QUEUE_EXIT
            and event.physical_tick == tick
        ]


if __name__ == "__main__":
    unittest.main()
