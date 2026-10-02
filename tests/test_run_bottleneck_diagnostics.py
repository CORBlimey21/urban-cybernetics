# SPDX-License-Identifier: MPL-2.0
"""I2 bottleneck and queue diagnostics tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import (
    DemandDeclaration,
    Event,
    EventType,
    LifecycleState,
    Link,
    Packet,
)
from urban_cybernetics.inspection import (
    PacketDiagnosticMetadata,
    RunBottleneckDiagnostics,
    build_run_bottleneck_diagnostics,
    inspect_loading_engine_bottlenecks,
)
from urban_cybernetics.loading import LoadingEngine


class RunBottleneckDiagnosticsTest(unittest.TestCase):
    def test_worst_packet_rankings_use_travel_time_delay_and_ratio(self) -> None:
        diagnostics = build_run_bottleneck_diagnostics(
            run_id="run:i2:packets",
            events=(
                *self.completed_packet_events("P1", "L1", 0, 10),
                *self.completed_packet_events("P2", "L2", 1, 21),
                *self.completed_packet_events("P3", "L3", 2, 14),
            ),
            packets={
                "P1": Packet("P1", "LD1", ("L1",), LifecycleState.COMPLETED),
                "P2": Packet("P2", "LD2", ("L2",), LifecycleState.COMPLETED),
                "P3": Packet("P3", "LD3", ("L3",), LifecycleState.COMPLETED),
            },
            links={
                "L1": Link("L1", free_flow_ticks=5),
                "L2": Link("L2", free_flow_ticks=4),
                "L3": Link("L3", free_flow_ticks=2),
            },
            packet_metadata_by_loading_demand_id={
                "LD1": PacketDiagnosticMetadata(demand_id="OD1", route_id="R1"),
                "LD2": PacketDiagnosticMetadata(demand_id="OD2", route_id="R2"),
                "LD3": PacketDiagnosticMetadata(demand_id="OD3", route_id="R3"),
            },
            top_n=2,
        )

        self.assertIsInstance(diagnostics, RunBottleneckDiagnostics)
        self.assertEqual(
            [item.packet_id for item in diagnostics.worst_packets_by_travel_time],
            ["P2", "P3"],
        )
        self.assertEqual(
            [item.packet_id for item in diagnostics.worst_packets_by_delay],
            ["P2", "P3"],
        )
        self.assertEqual(
            [item.packet_id for item in diagnostics.worst_packets_by_free_flow_ratio],
            ["P3", "P2"],
        )
        self.assertEqual(
            diagnostics.worst_packets_by_delay[0].delay_over_free_flow_ticks,
            16,
        )

    def test_worst_od_and_route_groups_aggregate_completed_packets(self) -> None:
        diagnostics = build_run_bottleneck_diagnostics(
            run_id="run:i2:groups",
            events=(
                *self.completed_packet_events("P1", "L1", 0, 10),
                *self.completed_packet_events("P2", "L1", 1, 16),
                *self.completed_packet_events("P3", "L2", 2, 8),
            ),
            packets={
                "P1": Packet("P1", "LD1", ("L1",), LifecycleState.COMPLETED),
                "P2": Packet("P2", "LD2", ("L1",), LifecycleState.COMPLETED),
                "P3": Packet("P3", "LD3", ("L2",), LifecycleState.COMPLETED),
            },
            links={
                "L1": Link("L1", free_flow_ticks=5),
                "L2": Link("L2", free_flow_ticks=4),
            },
            packet_metadata_by_loading_demand_id={
                "LD1": PacketDiagnosticMetadata(
                    demand_id="OD-A",
                    route_id="R-A",
                    origin_node_id="N1",
                    destination_node_id="N2",
                    route_link_sequence=("L1",),
                ),
                "LD2": PacketDiagnosticMetadata(
                    demand_id="OD-A",
                    route_id="R-A",
                    origin_node_id="N1",
                    destination_node_id="N2",
                    route_link_sequence=("L1",),
                ),
                "LD3": PacketDiagnosticMetadata(
                    demand_id="OD-B",
                    route_id="R-B",
                    origin_node_id="N3",
                    destination_node_id="N4",
                    route_link_sequence=("L2",),
                ),
            },
            top_n=2,
        )

        od_group = diagnostics.worst_od_groups[0]
        self.assertEqual(od_group.group_id, "OD:N1->N2")
        self.assertEqual(od_group.completed_count, 2)
        self.assertEqual(od_group.average_travel_time_ticks, 12.5)
        self.assertEqual(od_group.average_delay_over_free_flow_ticks, 7.5)

        route_group = diagnostics.worst_routes[0]
        self.assertEqual(route_group.route_id, "R-A")
        self.assertEqual(route_group.completed_count, 2)
        self.assertEqual(route_group.route_link_sequence, ("L1",))

    def test_queue_duration_and_max_length_from_queue_events(self) -> None:
        diagnostics = build_run_bottleneck_diagnostics(
            run_id="run:i2:queues",
            events=(
                self.event(0, "P1", EventType.QUEUE_ENTRY, "boundary:L1->L2", 2),
                self.event(1, "P2", EventType.QUEUE_ENTRY, "boundary:L1->L2", 3),
                self.event(2, "P1", EventType.QUEUE_EXIT, "boundary:L1->L2", 5),
            ),
            packets={
                "P1": Packet("P1", "D1", ("L1", "L2"), LifecycleState.COMPLETED),
                "P2": Packet("P2", "D2", ("L1", "L2"), LifecycleState.QUEUED),
            },
            current_tick=7,
        )

        queue = diagnostics.persistent_queues[0]
        self.assertEqual(queue.boundary_id, "boundary:L1->L2")
        self.assertEqual(queue.queue_entry_count, 2)
        self.assertEqual(queue.queue_exit_count, 1)
        self.assertEqual(queue.max_observed_queue_length, 2)
        self.assertEqual(queue.total_queued_packet_ticks, 7)
        self.assertEqual(queue.longest_individual_queue_wait_ticks, 4)
        self.assertEqual(queue.active_queued_packets, 1)

    def test_link_bottleneck_counts_and_delay_contribution(self) -> None:
        diagnostics = build_run_bottleneck_diagnostics(
            run_id="run:i2:links",
            events=(
                *self.completed_packet_events("P1", "L1", 0, 5),
                *self.completed_packet_events("P2", "L1", 1, 8),
                self.event(8, "P3", EventType.INSTANTIATED, "L2", 2),
                self.event(9, "P3", EventType.LINK_ENTRY, "L2", 2),
            ),
            packets={
                "P1": Packet("P1", "D1", ("L1",), LifecycleState.COMPLETED),
                "P2": Packet("P2", "D2", ("L1",), LifecycleState.COMPLETED),
                "P3": Packet("P3", "D3", ("L2",), LifecycleState.IN_TRANSIT),
            },
            links={
                "L1": Link("L1", free_flow_ticks=2),
                "L2": Link("L2", free_flow_ticks=2),
            },
        )

        busiest = diagnostics.busiest_links[0]
        self.assertEqual(busiest.link_id, "L1")
        self.assertEqual(busiest.link_entry_count, 2)
        self.assertEqual(busiest.link_exit_count, 2)
        self.assertEqual(busiest.net_occupancy_contribution, 0)

        delayed = diagnostics.most_delayed_links[0]
        self.assertEqual(delayed.link_id, "L1")
        self.assertEqual(delayed.completed_traversal_count, 2)
        self.assertEqual(delayed.total_delay_over_free_flow_ticks, 8)
        self.assertEqual(delayed.average_delay_over_free_flow_ticks, 4.0)

    def test_partial_runs_are_supported(self) -> None:
        diagnostics = build_run_bottleneck_diagnostics(
            run_id="run:i2:partial",
            events=(
                *self.completed_packet_events("P1", "L1", 0, 4),
                self.event(4, "P2", EventType.INSTANTIATED, "L1", 1),
                self.event(5, "P2", EventType.LINK_ENTRY, "L1", 1),
                self.event(6, "P2", EventType.QUEUE_ENTRY, "boundary:L1->L2", 3),
            ),
            packets={
                "P1": Packet("P1", "D1", ("L1",), LifecycleState.COMPLETED),
                "P2": Packet("P2", "D2", ("L1", "L2"), LifecycleState.QUEUED),
            },
            links={"L1": Link("L1", free_flow_ticks=1)},
            current_tick=6,
        )

        self.assertEqual(len(diagnostics.worst_packets_by_travel_time), 1)
        self.assertEqual(diagnostics.worst_packets_by_travel_time[0].packet_id, "P1")
        self.assertEqual(diagnostics.persistent_queues[0].active_queued_packets, 1)
        self.assertEqual(
            diagnostics.persistent_queues[0].longest_individual_queue_wait_ticks,
            3,
        )

    def test_engine_inspection_is_read_only(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link("L1", free_flow_ticks=1),
                "L2": Link("L2", free_flow_ticks=1),
            }
        )
        engine.set_receiving_open("L2", False)
        engine.instantiate(
            DemandDeclaration("D1", departure_tick=0, route_intent=("L1", "L2"))
        )
        engine.step()
        before_events = engine.event_log
        before_packets = dict(engine.packets)
        before_queue = engine.packet_ids_in_queue("L1", "L2")

        inspect_loading_engine_bottlenecks(run_id="run:i2:readonly", engine=engine)

        self.assertEqual(engine.event_log, before_events)
        self.assertEqual(dict(engine.packets), before_packets)
        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), before_queue)

    def completed_packet_events(
        self,
        packet_id: str,
        link_id: str,
        start_tick: int,
        completion_tick: int,
    ) -> tuple[Event, ...]:
        sequence_base = int(packet_id.removeprefix("P")) * 10
        return (
            self.event(
                sequence_base,
                packet_id,
                EventType.INSTANTIATED,
                link_id,
                start_tick,
            ),
            self.event(
                sequence_base + 1,
                packet_id,
                EventType.LINK_ENTRY,
                link_id,
                start_tick,
            ),
            self.event(
                sequence_base + 2,
                packet_id,
                EventType.LINK_EXIT,
                link_id,
                completion_tick,
            ),
            self.event(
                sequence_base + 3,
                packet_id,
                EventType.COMPLETED,
                link_id,
                completion_tick,
            ),
        )

    def event(
        self,
        sequence_number: int,
        packet_id: str,
        event_type: EventType,
        entity_id: str,
        physical_tick: int,
    ) -> Event:
        return Event(
            sequence_number=sequence_number,
            packet_id=packet_id,
            event_type=event_type,
            entity_id=entity_id,
            physical_tick=physical_tick,
        )


if __name__ == "__main__":
    unittest.main()
