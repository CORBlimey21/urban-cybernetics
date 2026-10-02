# SPDX-License-Identifier: MPL-2.0
"""Traffic kinematics foundation tests for static link metadata and origin loading."""

from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import DemandDeclaration, EventType, LifecycleState, Link
from urban_cybernetics.loading import LoadingEngine


class TrafficKinematicsFoundationTest(unittest.TestCase):
    def test_full_origin_link_blocks_entry(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(
                    link_id="L1",
                    free_flow_ticks=10,
                    declared_storage_capacity_packets=1,
                )
            }
        )
        existing_packet = engine.instantiate(
            DemandDeclaration(demand_id="D-existing", departure_tick=0, route_intent=("L1",))
        )
        blocked_packet = engine.instantiate(
            DemandDeclaration(demand_id="D-blocked", departure_tick=0, route_intent=("L1",))
        )

        self.assertIsNone(blocked_packet)
        self.assertEqual(len(engine.pending_demands), 1)
        self.assertEqual(engine.pending_demands[0].demand_id, "D-blocked")
        self.assertEqual(engine.link_storage("L1", 0).storage, 1)
        self.assertEqual(engine.packet_ids_on_link("L1"), (existing_packet.packet_id,))
        self.assertFalse(self.has_demand_event(engine, "D-blocked", EventType.INSTANTIATED))
        self.assertFalse(self.has_demand_event(engine, "D-blocked", EventType.LINK_ENTRY))

    def test_storage_release_permits_later_origin_departure(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(
                    link_id="L1",
                    free_flow_ticks=1,
                    declared_storage_capacity_packets=1,
                )
            }
        )
        existing_packet = engine.instantiate(
            DemandDeclaration(demand_id="D-existing", departure_tick=0, route_intent=("L1",))
        )

        self.assertIsNone(
            engine.instantiate(
                DemandDeclaration(demand_id="D-blocked", departure_tick=0, route_intent=("L1",))
            )
        )

        engine.step()

        self.assertEqual(
            engine.packets[existing_packet.packet_id].lifecycle_state,
            LifecycleState.COMPLETED,
        )
        self.assertEqual(len(engine.pending_demands), 1)
        self.assertFalse(self.has_demand_event(engine, "D-blocked", EventType.INSTANTIATED))

        engine.step()

        blocked_packets = [
            packet
            for packet in engine.packets.values()
            if packet.demand_id == "D-blocked"
        ]
        self.assertEqual(len(blocked_packets), 1)
        self.assertEqual(blocked_packets[0].lifecycle_state, LifecycleState.IN_TRANSIT)
        self.assertEqual(engine.pending_demands, ())
        self.assertEqual(engine.link_storage("L1").storage, 1)
        self.assertTrue(self.has_demand_event(engine, "D-blocked", EventType.LINK_ENTRY))

    def test_physical_metadata_is_immutable(self) -> None:
        link = self.physical_link(link_id="L1")

        with self.assertRaises(FrozenInstanceError):
            link.length_m = 250.0
        with self.assertRaises(FrozenInstanceError):
            link.lane_count = 3

    def test_physical_metadata_validation(self) -> None:
        with self.assertRaises(ValueError):
            self.physical_link(link_id="bad-length", length_m=-1.0)
        with self.assertRaises(ValueError):
            self.physical_link(link_id="bad-lanes", lane_count=0)
        with self.assertRaises(ValueError):
            self.physical_link(link_id="bad-speed", free_flow_speed_mps=0.0)
        with self.assertRaises(ValueError):
            Link(
                link_id="partial-storage",
                free_flow_ticks=1,
                length_m=100.0,
                lane_count=1,
            )

    def test_unit_consistent_physical_construction(self) -> None:
        link = self.physical_link(
            link_id="L1",
            length_m=100.0,
            lane_count=2,
            free_flow_speed_mps=10.0,
            jam_density_veh_per_km_per_lane=150.0,
            tick_duration_seconds=5.0,
        )

        self.assertEqual(link.free_flow_ticks, 2)
        self.assertEqual(link.declared_storage_capacity_packets, 30)
        self.assertEqual(link.length_m, 100.0)
        self.assertEqual(link.free_flow_speed_mps, 10.0)

    def test_longer_links_store_more_packets(self) -> None:
        short_link = self.physical_link(link_id="short", length_m=100.0)
        long_link = self.physical_link(link_id="long", length_m=300.0)

        self.assertLess(
            short_link.declared_storage_capacity_packets,
            long_link.declared_storage_capacity_packets,
        )

    def test_more_lanes_increase_storage(self) -> None:
        one_lane = self.physical_link(link_id="one-lane", lane_count=1)
        two_lanes = self.physical_link(link_id="two-lanes", lane_count=2)

        self.assertLess(
            one_lane.declared_storage_capacity_packets,
            two_lanes.declared_storage_capacity_packets,
        )

    def test_higher_jam_density_increases_storage(self) -> None:
        lower_density = self.physical_link(
            link_id="lower-density",
            jam_density_veh_per_km_per_lane=100.0,
        )
        higher_density = self.physical_link(
            link_id="higher-density",
            jam_density_veh_per_km_per_lane=200.0,
        )

        self.assertLess(
            lower_density.declared_storage_capacity_packets,
            higher_density.declared_storage_capacity_packets,
        )

    def test_explicit_storage_capacity_is_preserved(self) -> None:
        link = self.physical_link(
            link_id="explicit",
            length_m=1000.0,
            lane_count=3,
            jam_density_veh_per_km_per_lane=200.0,
            declared_storage_capacity_packets=7,
        )

        self.assertEqual(link.declared_storage_capacity_packets, 7)

    def test_longer_links_produce_larger_free_flow_times(self) -> None:
        short_link = self.physical_link(link_id="short", length_m=100.0)
        long_link = self.physical_link(link_id="long", length_m=300.0)

        self.assertLess(short_link.free_flow_ticks, long_link.free_flow_ticks)

    def test_faster_links_produce_smaller_free_flow_times(self) -> None:
        slow_link = self.physical_link(link_id="slow", free_flow_speed_mps=5.0)
        fast_link = self.physical_link(link_id="fast", free_flow_speed_mps=20.0)

        self.assertGreater(slow_link.free_flow_ticks, fast_link.free_flow_ticks)

    def test_derived_free_flow_values_remain_stable(self) -> None:
        link = self.physical_link(link_id="stable", length_m=120.0, free_flow_speed_mps=10.0)
        first_value = link.free_flow_ticks

        for _ in range(3):
            self.assertEqual(link.free_flow_ticks, first_value)

    def test_triangular_fd_metadata_is_available_without_dynamic_state(self) -> None:
        link = self.physical_link(link_id="fd")

        self.assertEqual(link.free_flow_speed_mps, 10.0)
        self.assertEqual(link.capacity_veh_per_hour_per_lane, 1800.0)
        self.assertEqual(link.jam_density_veh_per_km_per_lane, 150.0)
        self.assertEqual(link.backward_wave_speed_mps, 5.0)
        self.assertFalse(hasattr(link, "current_occupancy"))
        self.assertFalse(hasattr(link, "current_density"))
        self.assertFalse(hasattr(link, "current_speed"))

    def physical_link(
        self,
        *,
        link_id: str,
        length_m: float = 100.0,
        lane_count: int = 1,
        free_flow_speed_mps: float = 10.0,
        jam_density_veh_per_km_per_lane: float = 150.0,
        backward_wave_speed_mps: float = 5.0,
        capacity_veh_per_hour_per_lane: float = 1800.0,
        declared_storage_capacity_packets: int | None = None,
        tick_duration_seconds: float = 1.0,
    ) -> Link:
        return Link(
            link_id=link_id,
            length_m=length_m,
            lane_count=lane_count,
            free_flow_speed_mps=free_flow_speed_mps,
            jam_density_veh_per_km_per_lane=jam_density_veh_per_km_per_lane,
            backward_wave_speed_mps=backward_wave_speed_mps,
            capacity_veh_per_hour_per_lane=capacity_veh_per_hour_per_lane,
            declared_storage_capacity_packets=declared_storage_capacity_packets,
            tick_duration_seconds=tick_duration_seconds,
        )

    def has_demand_event(
        self,
        engine: LoadingEngine,
        demand_id: str,
        event_type: EventType,
    ) -> bool:
        packet_ids = {
            packet.packet_id
            for packet in engine.packets.values()
            if packet.demand_id == demand_id
        }
        return any(
            event.packet_id in packet_ids and event.event_type == event_type
            for event in engine.event_log
        )


if __name__ == "__main__":
    unittest.main()
