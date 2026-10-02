# SPDX-License-Identifier: MPL-2.0
"""M7 packet and multi-commodity parity torture tests."""

from __future__ import annotations

import pytest

from urban_cybernetics.core import DemandDeclaration, EventType, LifecycleState, Node, Packet
from urban_cybernetics.loading import LoadingEngine, route_key_for_packet
from urban_cybernetics.validation import (
    COMMODITY_MODEL_ID,
    ValidationContext,
    build_commodity_parity_validation_report,
)

from .helpers import (
    assert_core_invariants,
    demand,
    instantiate_demands,
    link_event_packet_ids,
    parity_engine,
    physical_link,
    run_ticks,
)


def test_unit_packet_contract_rejects_weighted_packets_explicitly() -> None:
    with pytest.raises(TypeError, match="packet_unit_weight must be an int"):
        DemandDeclaration(
            "D-bool",
            departure_tick=0,
            route_intent=("L1",),
            packet_unit_weight=True,
        )

    with pytest.raises(ValueError, match="weighted packets"):
        DemandDeclaration(
            "D-weighted",
            departure_tick=0,
            route_intent=("L1",),
            packet_unit_weight=2,
        )

    with pytest.raises(ValueError, match="weighted packets"):
        Packet(
            "P-weighted",
            "D-weighted",
            ("L1",),
            LifecycleState.IN_TRANSIT,
            packet_unit_weight=2,
        )


def test_m7_commodity_is_immutable_route_intent_and_route_counts_sum_to_aggregate() -> None:
    engine = parity_engine(
        links={
            "L1": physical_link("L1", sending_capacity=4, storage=8),
            "L2": physical_link("L2", receiving_capacity=4, storage=8),
            "L3": physical_link("L3", receiving_capacity=4, storage=8),
        },
        nodes=(
            Node(
                "N-diverge",
                incoming_link_ids=("L1",),
                outgoing_link_ids=("L2", "L3"),
            ),
        ),
    )
    instantiate_demands(
        engine,
        (
            demand("D-L2-a", ("L1", "L2")),
            demand("D-L2-b", ("L1", "L2")),
            demand("D-L3", ("L1", "L3")),
        ),
    )

    run_ticks(engine, 3)
    report = build_commodity_parity_validation_report(engine)

    assert report.is_valid
    assert report.commodity_model_id == COMMODITY_MODEL_ID
    assert {
        (definition.commodity_key, definition.route_link_ids, definition.packet_count)
        for definition in report.commodity_definitions
    } == {
        ("route:L1->L2", ("L1", "L2"), 2),
        ("route:L1->L3", ("L1", "L3"), 1),
    }

    projection = engine.cumulative_count_projection()
    l1_final_route_entries = sum(
        counts.entries
        for counts in projection.route_counts
        if counts.link_id == "L1" and counts.tick == projection.max_tick
    )
    assert l1_final_route_entries == engine.cumulative_counts("L1").entries


def test_commodity_validation_context_preserves_direct_validation_semantics() -> None:
    engine = parity_engine(
        links={
            "L1": physical_link("L1", sending_capacity=4, storage=8),
            "L2": physical_link("L2", receiving_capacity=4, storage=8),
            "L3": physical_link("L3", receiving_capacity=4, storage=8),
        },
        nodes=(
            Node(
                "N-diverge",
                incoming_link_ids=("L1",),
                outgoing_link_ids=("L2", "L3"),
            ),
        ),
    )
    instantiate_demands(
        engine,
        (
            demand("D-L2-a", ("L1", "L2")),
            demand("D-L2-b", ("L1", "L2")),
            demand("D-L3", ("L1", "L3")),
        ),
    )

    run_ticks(engine, 3)
    direct_report = build_commodity_parity_validation_report(engine)
    context_report = build_commodity_parity_validation_report(
        engine,
        validation_context=ValidationContext.from_engine(engine),
    )

    assert context_report == direct_report


def test_route_travel_time_curve_points_match_final_link_exit_route_ordinals() -> None:
    engine = parity_engine(
        links={"L1": physical_link("L1", sending_capacity=1, storage=4)}
    )
    packets = [
        engine.instantiate(demand(f"D{index}", ("L1",)))
        for index in range(3)
    ]

    run_ticks(engine, 3)
    curve = engine.route_travel_time_curves()[0]
    projection = engine.cumulative_count_projection()
    final_exit_ordinal_by_packet = {
        ordinal.packet_id: ordinal.route_ordinal
        for ordinal in projection.packet_ordinals
        if ordinal.boundary_type == "exit" and ordinal.link_id == "L1"
    }

    assert curve.route_key == route_key_for_packet(engine.packets[packets[0].packet_id])
    assert [point.packet_id for point in curve.points] == [
        packet.packet_id for packet in packets
    ]
    assert [point.travel_time_ticks for point in curve.points] == [1, 2, 3]
    assert [
        point.final_link_exit_route_ordinal for point in curve.points
    ] == [
        final_exit_ordinal_by_packet[packet.packet_id] for packet in packets
    ]
    assert_core_invariants(engine)


def test_high_commodity_fixture_preserves_correctness_and_slotted_packet_memory() -> None:
    commodity_count = 80
    links = {
        f"L{index:03d}": physical_link(f"L{index:03d}", storage=2)
        for index in range(commodity_count)
    }
    engine = parity_engine(links=links)
    for index, link_id in enumerate(links):
        engine.instantiate(demand(f"D{index:03d}", (link_id,)))

    run_ticks(engine, 1)
    report = build_commodity_parity_validation_report(engine)

    assert report.is_valid
    assert report.checked_packet_count == commodity_count
    assert len(report.commodity_definitions) == commodity_count
    assert len(report.route_travel_time_curves) == commodity_count
    assert len(engine.event_log) == commodity_count * 4
    assert all(not hasattr(packet, "__dict__") for packet in engine.packets.values())


def test_legacy_profile_still_moves_packets_but_is_not_m7_parity_evidence() -> None:
    engine = LoadingEngine(
        links={"L1": physical_link("L1", sending_capacity=1, storage=2)}
    )
    packet = engine.instantiate(demand("D1", ("L1",)))

    engine.step()
    report = build_commodity_parity_validation_report(engine)

    assert link_event_packet_ids(engine, EventType.LINK_EXIT, "L1", 1) == [
        packet.packet_id
    ]
    assert not report.is_valid
    assert report.invariant_violations == ("model_profile_not_parity_ltm_v1",)
