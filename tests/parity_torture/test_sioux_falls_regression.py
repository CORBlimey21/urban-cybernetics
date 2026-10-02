# SPDX-License-Identifier: MPL-2.0
"""Sioux Falls regression-only checks for parity-kernel bookkeeping."""

from __future__ import annotations

from dataclasses import replace

from urban_cybernetics.core import DemandDeclaration, EventType
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.topology import build_shortest_link_count_route, load_sioux_falls_topology
from urban_cybernetics.validation import build_spillback_validation_report

from .helpers import (
    assert_core_invariants,
    assert_same_events,
    link_event_packet_ids,
)


def test_sioux_falls_small_route_replay_is_byte_for_byte_deterministic() -> None:
    first = _sioux_engine()
    second = _sioux_engine()
    route = _sioux_route().ordered_link_ids
    for index in range(3):
        declaration = DemandDeclaration(
            demand_id=f"D{index}",
            departure_tick=index % 2,
            route_intent=route,
        )
        first.instantiate(declaration)
        second.instantiate(declaration)

    _run_ticks(first, 30)
    _run_ticks(second, 30)

    assert_same_events(first, second)
    assert_core_invariants(first)


def test_sioux_falls_spillback_regression_has_no_impossible_states() -> None:
    topology = load_sioux_falls_topology()
    route = _sioux_route().ordered_link_ids
    links = topology.as_loading_links(
        tick_duration_seconds=60.0,
        declared_storage_capacity_packets=1000,
    )
    first_link_id, second_link_id = route[:2]
    links[second_link_id] = replace(
        links[second_link_id],
        free_flow_ticks=10,
        declared_storage_capacity_packets=1,
    )
    engine = LoadingEngine(links=links, nodes=topology.as_loading_nodes())
    blocker = engine.instantiate(
        DemandDeclaration("D-blocker", departure_tick=0, route_intent=(second_link_id,))
    )
    blocked = engine.instantiate(
        DemandDeclaration(
            "D-blocked",
            departure_tick=0,
            route_intent=(first_link_id, second_link_id),
        )
    )

    _run_ticks(engine, 12)
    report = build_spillback_validation_report(
        engine,
        boundary_ids=(f"boundary:{first_link_id}->{second_link_id}",),
    )

    assert report.invariant_violations == ("model_profile_not_parity_ltm_v1",)
    assert link_event_packet_ids(engine, EventType.LINK_EXIT, second_link_id) == [
        blocker.packet_id
    ]
    assert all(
        point.queue_length >= 0
        for trace in report.boundary_traces
        for point in trace.queue_curve
    )
    assert all(trace.is_queue_consistent_with_engine for trace in report.boundary_traces)
    assert blocked.packet_id in {
        event.packet_id
        for event in engine.event_log
        if event.event_type == EventType.LINK_ENTRY and event.entity_id == second_link_id
    }
    assert_core_invariants(engine)


def _sioux_route():
    topology = load_sioux_falls_topology()
    return build_shortest_link_count_route(
        topology,
        origin_node_id="N001",
        destination_node_id="N024",
    )


def _sioux_engine() -> LoadingEngine:
    topology = load_sioux_falls_topology()
    return LoadingEngine(
        links=topology.as_loading_links(
            tick_duration_seconds=60.0,
            declared_storage_capacity_packets=1000,
        ),
        nodes=topology.as_loading_nodes(),
    )


def _run_ticks(engine: LoadingEngine, ticks: int) -> None:
    for _ in range(ticks):
        engine.step()
