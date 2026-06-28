"""General movement-allocation parity tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import (
    DemandDeclaration,
    Event,
    EventType,
    JUNCTION_FIFO_PARTIAL_BY_MOVEMENT,
    JunctionSpec,
    Link,
    MovementSpec,
    Node,
)
from urban_cybernetics.loading import (
    GeneralMovementAllocator,
    GlobalFIFOMergePolicy,
    LoadingEngine,
)


class LTMParityMovementAllocatorTest(unittest.TestCase):
    def test_one_to_one_transfer_is_bounded_by_sending_and_receiving(self) -> None:
        engine = self.parity_engine(
            links={
                "L1": self.physical_link("L1", sending_capacity=3, storage=10),
                "L2": self.physical_link("L2", receiving_capacity=2, storage=10),
            },
            nodes=(
                Node(
                    "N",
                    incoming_link_ids=("L1",),
                    outgoing_link_ids=("L2",),
                ),
            ),
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

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 1),
            [packets[0].packet_id, packets[1].packet_id],
        )
        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), (packets[2].packet_id,))
        trace = engine.node_transfer_traces()[0]
        self.assertEqual(trace.node_id, "N")
        self.assertEqual(trace.allocator_id, "uc_movement_allocator_stage2_v1")
        self.assertEqual(len(trace.candidate_packet_ids), 3)
        self.assertEqual(len(trace.approved_packet_ids), 2)
        self.assertEqual(
            trace.movement_flow_summaries[0].movement_id,
            "movement:L1->L2",
        )
        self.assertTrue(engine.check_conservation())

    def test_strict_route_diverge_blocks_tail_when_fifo_head_branch_is_closed(
        self,
    ) -> None:
        engine = self.parity_engine(
            links={
                "L1": self.physical_link("L1", sending_capacity=2, storage=10),
                "L2": self.physical_link("L2", receiving_capacity=1, storage=10),
                "L3": self.physical_link("L3", receiving_capacity=1, storage=10),
            },
            nodes=(
                Node(
                    "N",
                    incoming_link_ids=("L1",),
                    outgoing_link_ids=("L2", "L3"),
                ),
            ),
        )
        engine.set_receiving_open("L2", False)
        packet_l2 = engine.instantiate(
            DemandDeclaration("D-L2", departure_tick=0, route_intent=("L1", "L2"))
        )
        packet_l3 = engine.instantiate(
            DemandDeclaration("D-L3", departure_tick=0, route_intent=("L1", "L3"))
        )

        engine.step()

        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), (packet_l2.packet_id,))
        self.assertEqual(engine.packet_ids_in_queue("L1", "L3"), ())
        self.assertEqual(self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L3", 1), [])
        self.assertIn(packet_l3.packet_id, engine.packet_ids_on_link("L1"))

        engine.set_receiving_open("L2", True)
        engine.step()

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 2),
            [packet_l2.packet_id],
        )
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L3", 2),
            [],
        )
        engine.step()

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L3", 3),
            [packet_l3.packet_id],
        )
        self.assertEqual(
            self.realised_path(engine, packet_l2.packet_id),
            ("L1", "L2"),
        )
        self.assertEqual(
            self.realised_path(engine, packet_l3.packet_id),
            ("L1", "L3"),
        )
        self.assertTrue(engine.check_conservation())

    def test_declared_priority_merge_achieves_long_horizon_share(self) -> None:
        engine = self.priority_merge_engine()
        for index in range(4):
            engine.instantiate(
                DemandDeclaration(
                    f"D-L1-{index}",
                    departure_tick=0,
                    route_intent=("L1", "L3"),
                )
            )
        for index in range(2):
            engine.instantiate(
                DemandDeclaration(
                    f"D-L2-{index}",
                    departure_tick=0,
                    route_intent=("L2", "L3"),
                )
            )

        for _ in range(6):
            engine.step()

        source_sequence = self.l3_entry_source_sequence(engine)

        self.assertEqual(source_sequence, ["L1", "L2", "L1", "L1", "L2", "L1"])
        self.assertEqual(source_sequence.count("L1"), 4)
        self.assertEqual(source_sequence.count("L2"), 2)
        self.assertTrue(engine.check_conservation())

    def test_unused_merge_share_is_reassigned_to_available_demand(self) -> None:
        engine = self.priority_merge_engine(
            priority_weights=(("L1", 3), ("L2", 1)),
            l3_receiving_capacity=2,
            l2_sending_capacity=2,
        )
        packets = [
            engine.instantiate(
                DemandDeclaration(
                    f"D-L2-{index}",
                    departure_tick=0,
                    route_intent=("L2", "L3"),
                )
            )
            for index in range(3)
        ]

        engine.step()

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L3", 1),
            [packets[0].packet_id, packets[1].packet_id],
        )
        self.assertEqual(engine.packet_ids_in_queue("L2", "L3"), ())
        self.assertIn(packets[2].packet_id, engine.packet_ids_on_link("L2"))
        self.assertTrue(engine.check_conservation())

    def test_priority_merge_is_invariant_to_irrelevant_link_dictionary_order(self) -> None:
        first_engine = self.priority_merge_engine(link_order=("L1", "L2", "L3"))
        second_engine = self.priority_merge_engine(link_order=("L3", "L2", "L1"))
        for engine in (first_engine, second_engine):
            for index in range(4):
                engine.instantiate(
                    DemandDeclaration(
                        f"D-L1-{index}",
                        departure_tick=0,
                        route_intent=("L1", "L3"),
                    )
                )
            for index in range(2):
                engine.instantiate(
                    DemandDeclaration(
                        f"D-L2-{index}",
                        departure_tick=0,
                        route_intent=("L2", "L3"),
                    )
                )
            for _ in range(6):
                engine.step()

        self.assertEqual(
            self.l3_entry_source_sequence(first_engine),
            self.l3_entry_source_sequence(second_engine),
        )

    def test_simple_mimo_junction_runs_through_movement_allocator(self) -> None:
        engine = self.parity_engine(
            links={
                "L1": self.physical_link("L1"),
                "L2": self.physical_link("L2"),
                "L3": self.physical_link("L3", receiving_capacity=1),
                "L4": self.physical_link("L4", receiving_capacity=1),
            },
            nodes=(
                Node(
                    "N",
                    incoming_link_ids=("L1", "L2"),
                    outgoing_link_ids=("L3", "L4"),
                ),
            ),
        )
        packet_l1_l4 = engine.instantiate(
            DemandDeclaration("D-L1-L4", departure_tick=0, route_intent=("L1", "L4"))
        )
        packet_l2_l3 = engine.instantiate(
            DemandDeclaration("D-L2-L3", departure_tick=0, route_intent=("L2", "L3"))
        )

        engine.step()

        self.assertEqual(
            self.realised_path(engine, packet_l1_l4.packet_id),
            ("L1", "L4"),
        )
        self.assertEqual(
            self.realised_path(engine, packet_l2_l3.packet_id),
            ("L2", "L3"),
        )
        trace = engine.allocation_traces()[0]
        self.assertEqual(trace.node_id, "N")
        self.assertEqual(
            {summary.movement_id for summary in trace.movement_flow_summaries},
            {"movement:L1->L4", "movement:L2->L3"},
        )
        self.assertTrue(engine.check_conservation())

    def test_conflict_resources_limit_mutually_incompatible_movements(self) -> None:
        engine = self.stage2_crossing_engine()
        packet_l1_l3 = engine.instantiate(
            DemandDeclaration("D-L1-L3", departure_tick=0, route_intent=("L1", "L3"))
        )
        packet_l2_l4 = engine.instantiate(
            DemandDeclaration("D-L2-L4", departure_tick=0, route_intent=("L2", "L4"))
        )

        engine.step()

        self.assertEqual(
            self.realised_path(engine, packet_l1_l3.packet_id),
            ("L1", "L3"),
        )
        self.assertEqual(
            self.realised_path(engine, packet_l2_l4.packet_id),
            ("L2",),
        )
        trace = engine.allocation_traces()[0]
        self.assertEqual(trace.conflict_resource_capacity_by_id, (("crossing", 1),))
        self.assertIn(
            (packet_l2_l4.packet_id, "conflict_resource_capacity_unavailable"),
            trace.rejected_transfer_reasons,
        )
        self.assertTrue(engine.check_conservation())

    def test_shared_lane_group_capacity_limits_parallel_movements(self) -> None:
        engine = self.stage2_crossing_engine(conflict_capacity=2, lane_capacity=1)
        first_packet = engine.instantiate(
            DemandDeclaration("D-L1-L3", departure_tick=0, route_intent=("L1", "L3"))
        )
        second_packet = engine.instantiate(
            DemandDeclaration("D-L2-L4", departure_tick=0, route_intent=("L2", "L4"))
        )

        engine.step()

        self.assertEqual(
            self.realised_path(engine, first_packet.packet_id),
            ("L1", "L3"),
        )
        self.assertEqual(self.realised_path(engine, second_packet.packet_id), ("L2",))
        trace = engine.allocation_traces()[0]
        self.assertEqual(trace.lane_group_capacity_by_id, (("shared-through", 1),))
        self.assertIn(
            (second_packet.packet_id, "lane_group_capacity_unavailable"),
            trace.rejected_transfer_reasons,
        )
        self.assertTrue(engine.check_conservation())

    def test_partial_fifo_allows_disjoint_open_movement_to_bypass_blocked_head(
        self,
    ) -> None:
        engine = self.parity_engine(
            links={
                "L1": self.physical_link("L1", sending_capacity=2, storage=10),
                "L2": self.physical_link("L2", receiving_capacity=1, storage=10),
                "L3": self.physical_link("L3", receiving_capacity=1, storage=10),
            },
            nodes=(
                Node(
                    "N",
                    incoming_link_ids=("L1",),
                    outgoing_link_ids=("L2", "L3"),
                    junction_spec=JunctionSpec(
                        node_id="N",
                        incoming_link_ids=("L1",),
                        outgoing_link_ids=("L2", "L3"),
                        lane_group_ids=("left", "right"),
                        fifo_policy=JUNCTION_FIFO_PARTIAL_BY_MOVEMENT,
                        movement_specs=(
                            MovementSpec(
                                "L1",
                                "L2",
                                lane_group_ids=("left",),
                                signal_group_id="red",
                            ),
                            MovementSpec(
                                "L1",
                                "L3",
                                lane_group_ids=("right",),
                                signal_group_id="green",
                            ),
                        ),
                    ),
                ),
            ),
        )
        engine.set_signal_group_open("green", True)
        blocked_head = engine.instantiate(
            DemandDeclaration("D-L2", departure_tick=0, route_intent=("L1", "L2"))
        )
        bypass_tail = engine.instantiate(
            DemandDeclaration("D-L3", departure_tick=0, route_intent=("L1", "L3"))
        )

        engine.step()

        self.assertEqual(self.realised_path(engine, blocked_head.packet_id), ("L1",))
        self.assertEqual(self.realised_path(engine, bypass_tail.packet_id), ("L1", "L3"))
        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), (blocked_head.packet_id,))
        trace = engine.allocation_traces()[0]
        self.assertIn(
            (blocked_head.packet_id, "signal_gate_closed"),
            trace.rejected_transfer_reasons,
        )
        self.assertTrue(engine.check_conservation())

    def test_signal_phase_gate_blocks_declared_signal_movement(self) -> None:
        engine = self.stage2_signal_engine()
        packet = engine.instantiate(
            DemandDeclaration("D-L1-L2", departure_tick=0, route_intent=("L1", "L2"))
        )

        engine.step()

        self.assertEqual(self.realised_path(engine, packet.packet_id), ("L1",))
        self.assertEqual(
            engine.allocation_traces()[0].rejected_transfer_reasons,
            ((packet.packet_id, "signal_gate_closed"),),
        )
        engine.set_signal_group_open("phase-a", True)
        engine.step()
        self.assertEqual(self.realised_path(engine, packet.packet_id), ("L1", "L2"))
        self.assertTrue(engine.check_conservation())

    def test_governance_closure_is_distinct_from_downstream_physical_shortage(
        self,
    ) -> None:
        governance_engine = self.stage2_signal_engine(signal_open=True)
        packet = governance_engine.instantiate(
            DemandDeclaration("D-governance", departure_tick=0, route_intent=("L1", "L2"))
        )
        governance_engine.set_movement_governance_open(
            "N",
            "movement:L1->L2",
            False,
        )
        governance_engine.step()

        physical_engine = self.stage2_signal_engine(signal_open=True, receiving_open=False)
        physical_packet = physical_engine.instantiate(
            DemandDeclaration("D-physical", departure_tick=0, route_intent=("L1", "L2"))
        )
        physical_engine.step()

        self.assertEqual(
            governance_engine.allocation_traces()[0].rejected_transfer_reasons,
            ((packet.packet_id, "governance_gate_closed"),),
        )
        self.assertEqual(
            physical_engine.allocation_traces()[0].rejected_transfer_reasons,
            ((physical_packet.packet_id, "downstream_supply_unavailable"),),
        )

    def test_stage2_ordering_invariance_and_deterministic_replay(self) -> None:
        first_engine = self.stage2_crossing_engine(link_order=("L1", "L2", "L3", "L4"))
        second_engine = self.stage2_crossing_engine(link_order=("L4", "L3", "L2", "L1"))
        for engine in (first_engine, second_engine):
            engine.instantiate(
                DemandDeclaration("D-L1-L3", departure_tick=0, route_intent=("L1", "L3"))
            )
            engine.instantiate(
                DemandDeclaration("D-L2-L4", departure_tick=0, route_intent=("L2", "L4"))
            )
            engine.step()

        self.assertEqual(first_engine.event_log, second_engine.event_log)
        self.assertTrue(first_engine.check_conservation())
        self.assertTrue(second_engine.check_conservation())

    def test_unsupported_stage2_adaptive_control_fails_explicitly(self) -> None:
        with self.assertRaisesRegex(ValueError, "adaptive_control_unsupported"):
            self.parity_engine(
                links={
                    "L1": self.physical_link("L1"),
                    "L2": self.physical_link("L2"),
                },
                nodes=(
                    Node(
                        "N",
                        incoming_link_ids=("L1",),
                        outgoing_link_ids=("L2",),
                        junction_spec=JunctionSpec(
                            node_id="N",
                            incoming_link_ids=("L1",),
                            outgoing_link_ids=("L2",),
                            governance_refs=("adaptive_control",),
                        ),
                    ),
                ),
            )

    def test_explicit_junction_spec_cannot_share_legacy_node_metadata(self) -> None:
        junction_spec = JunctionSpec(
            node_id="N",
            incoming_link_ids=("L1",),
            outgoing_link_ids=("L2",),
        )

        with self.assertRaisesRegex(ValueError, "merge_priorities"):
            Node(
                "N",
                incoming_link_ids=("L1",),
                outgoing_link_ids=("L2",),
                merge_priorities=(("L1", 2),),
                junction_spec=junction_spec,
            )

    def test_removed_specialised_node_model_labels_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "specialised node_model labels"):
            Node(
                "N",
                incoming_link_ids=("L1",),
                outgoing_link_ids=("L2",),
                node_model="one_to_one",
            )

    def test_legacy_profile_keeps_global_fifo_default_policy(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link("L1", free_flow_ticks=1),
                "L2": Link("L2", free_flow_ticks=1),
            },
            nodes=(
                Node(
                    "N",
                    incoming_link_ids=("L1",),
                    outgoing_link_ids=("L2",),
                ),
            ),
        )

        self.assertIsInstance(engine.node_transfer_policy, GlobalFIFOMergePolicy)

    def test_parity_profile_uses_general_movement_allocator(self) -> None:
        engine = self.parity_engine(
            links={
                "L1": self.physical_link("L1"),
                "L2": self.physical_link("L2"),
            },
            nodes=(Node("N", incoming_link_ids=("L1",), outgoing_link_ids=("L2",)),),
        )

        self.assertIsInstance(engine.movement_allocator, GeneralMovementAllocator)

    def test_movement_allocator_identity_and_spec_hash_are_provenance_visible(
        self,
    ) -> None:
        links = {
            "L1": self.physical_link("L1"),
            "L2": self.physical_link("L2"),
        }
        default_engine = self.parity_engine(
            links=links,
            nodes=(Node("N", incoming_link_ids=("L1",), outgoing_link_ids=("L2",)),),
        )
        weighted_engine = self.parity_engine(
            links=links,
            nodes=(
                Node(
                    "N",
                    incoming_link_ids=("L1",),
                    outgoing_link_ids=("L2",),
                    junction_spec=JunctionSpec(
                        node_id="N",
                        incoming_link_ids=("L1",),
                        outgoing_link_ids=("L2",),
                        movement_specs=(
                            MovementSpec("L1", "L2", priority_weight=2),
                        ),
                    ),
                ),
            ),
        )

        self.assertEqual(
            default_engine.movement_allocator_id,
            "uc_movement_allocator_stage2_v1",
        )
        self.assertEqual(len(default_engine.movement_spec_hash), 64)
        self.assertNotEqual(
            default_engine.movement_spec_hash,
            weighted_engine.movement_spec_hash,
        )

    def priority_merge_engine(
        self,
        *,
        priority_weights: tuple[tuple[str, int], ...] = (("L1", 2), ("L2", 1)),
        l3_receiving_capacity: int = 1,
        l1_sending_capacity: int = 1,
        l2_sending_capacity: int = 1,
        link_order: tuple[str, ...] = ("L1", "L2", "L3"),
    ) -> LoadingEngine:
        link_by_id = {
            "L1": self.physical_link(
                "L1",
                sending_capacity=l1_sending_capacity,
                storage=10,
            ),
            "L2": self.physical_link(
                "L2",
                sending_capacity=l2_sending_capacity,
                storage=10,
            ),
            "L3": self.physical_link(
                "L3",
                receiving_capacity=l3_receiving_capacity,
                storage=20,
            ),
        }
        return self.parity_engine(
            links={link_id: link_by_id[link_id] for link_id in link_order},
            nodes=(
                Node(
                    "N",
                    incoming_link_ids=("L1", "L2"),
                    outgoing_link_ids=("L3",),
                    merge_priorities=priority_weights,
                ),
            ),
        )

    def stage2_crossing_engine(
        self,
        *,
        conflict_capacity: int = 1,
        lane_capacity: int = 2,
        link_order: tuple[str, ...] = ("L1", "L2", "L3", "L4"),
    ) -> LoadingEngine:
        link_by_id = {
            "L1": self.physical_link("L1"),
            "L2": self.physical_link("L2"),
            "L3": self.physical_link("L3", receiving_capacity=2),
            "L4": self.physical_link("L4", receiving_capacity=2),
        }
        return self.parity_engine(
            links={link_id: link_by_id[link_id] for link_id in link_order},
            nodes=(
                Node(
                    "N",
                    incoming_link_ids=("L1", "L2"),
                    outgoing_link_ids=("L3", "L4"),
                    junction_spec=JunctionSpec(
                        node_id="N",
                        incoming_link_ids=("L1", "L2"),
                        outgoing_link_ids=("L3", "L4"),
                        lane_group_ids=("shared-through",),
                        lane_group_capacities=(("shared-through", lane_capacity),),
                        conflict_resource_ids=("crossing",),
                        conflict_resource_capacities=(("crossing", conflict_capacity),),
                        movement_specs=(
                            MovementSpec(
                                "L1",
                                "L3",
                                lane_group_ids=("shared-through",),
                                conflict_resource_ids=("crossing",),
                            ),
                            MovementSpec(
                                "L2",
                                "L4",
                                lane_group_ids=("shared-through",),
                                conflict_resource_ids=("crossing",),
                            ),
                        ),
                    ),
                ),
            ),
        )

    def stage2_signal_engine(
        self,
        *,
        signal_open: bool = False,
        receiving_open: bool = True,
    ) -> LoadingEngine:
        engine = self.parity_engine(
            links={
                "L1": self.physical_link("L1", storage=10),
                "L2": self.physical_link("L2", receiving_capacity=1, storage=10),
            },
            nodes=(
                Node(
                    "N",
                    incoming_link_ids=("L1",),
                    outgoing_link_ids=("L2",),
                    junction_spec=JunctionSpec(
                        node_id="N",
                        incoming_link_ids=("L1",),
                        outgoing_link_ids=("L2",),
                        movement_specs=(
                            MovementSpec("L1", "L2", signal_group_id="phase-a"),
                        ),
                    ),
                ),
            ),
        )
        engine.set_signal_group_open("phase-a", signal_open)
        engine.set_receiving_open("L2", receiving_open)
        return engine

    def parity_engine(
        self,
        *,
        links: dict[str, Link],
        nodes: tuple[Node, ...],
    ) -> LoadingEngine:
        return LoadingEngine(
            links=links,
            nodes=nodes,
            model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        )

    def physical_link(
        self,
        link_id: str,
        *,
        storage: int = 20,
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

    def l3_entry_source_sequence(self, engine: LoadingEngine) -> list[str]:
        return [
            engine.packets[event.packet_id].route_intent[0]
            for event in self.link_events(engine, EventType.LINK_ENTRY, "L3")
        ]

    def realised_path(self, engine: LoadingEngine, packet_id: str) -> tuple[str, ...]:
        return tuple(
            event.entity_id
            for event in engine.event_log
            if event.packet_id == packet_id and event.event_type == EventType.LINK_ENTRY
        )

    def link_events(
        self,
        engine: LoadingEngine,
        event_type: EventType,
        link_id: str,
    ) -> list[Event]:
        return [
            event
            for event in engine.event_log
            if event.event_type == event_type and event.entity_id == link_id
        ]


if __name__ == "__main__":
    unittest.main()
