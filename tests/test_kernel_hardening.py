"""Focused regressions for failure-safe packet lifecycle transitions."""

from __future__ import annotations

import pytest

from urban_cybernetics.canonical_validation.composition import (
    run_composition_validation_case,
)
from urban_cybernetics.core import (
    DemandDeclaration,
    EventType,
    LifecycleState,
    Link,
)
from urban_cybernetics.loading import EventCacheConsistencyError, LoadingEngine
from urban_cybernetics.canonical_validation import validate_loading_kernel


def test_ordinary_transfer_preserves_pairing_identity_and_spatial_uniqueness() -> None:
    engine, packet_id = _two_link_engine()

    engine.step()

    assert _packet_event_types(engine, packet_id)[-2:] == (
        EventType.LINK_EXIT,
        EventType.LINK_ENTRY,
    )
    assert _packet_event_entities(engine, packet_id)[-2:] == ("L1", "L2")
    assert _link_memberships(engine, packet_id) == ("L2",)
    assert engine.check_event_cache_consistency()
    assert engine.check_conservation()


def test_queued_transfer_preserves_queue_exit_then_boundary_pairing() -> None:
    engine, packet_id = _two_link_engine()
    engine.set_receiving_open("L2", False)
    engine.step()
    assert engine.packets[packet_id].lifecycle_state == LifecycleState.QUEUED

    engine.set_receiving_open("L2", True)
    engine.step()

    assert _packet_event_types(engine, packet_id)[-3:] == (
        EventType.QUEUE_EXIT,
        EventType.LINK_EXIT,
        EventType.LINK_ENTRY,
    )
    assert _link_memberships(engine, packet_id) == ("L2",)
    assert engine.packet_ids_in_queue("L1", "L2") == ()
    assert engine.check_event_cache_consistency()
    assert engine.check_conservation()


def test_final_link_completion_preserves_exit_then_completed_pairing() -> None:
    engine = LoadingEngine(links={"L1": _link("L1")})
    packet = engine.instantiate(
        DemandDeclaration("D1", departure_tick=0, route_intent=("L1",))
    )
    assert packet is not None

    engine.step()

    assert _packet_event_types(engine, packet.packet_id)[-2:] == (
        EventType.LINK_EXIT,
        EventType.COMPLETED,
    )
    assert _link_memberships(engine, packet.packet_id) == ()
    assert engine.packets[packet.packet_id].lifecycle_state == LifecycleState.COMPLETED
    assert engine.check_event_cache_consistency()
    assert engine.check_conservation()


def test_pre_execution_transfer_failure_leaves_events_and_state_unchanged() -> None:
    engine = LoadingEngine(
        links={link_id: _link(link_id) for link_id in ("L1", "L2", "L3")}
    )
    packet = engine.instantiate(
        DemandDeclaration("D1", departure_tick=0, route_intent=("L1", "L2"))
    )
    assert packet is not None
    before_events = engine.event_log
    before_packets = dict(engine.packets)
    before_memberships = {
        link_id: engine.packet_ids_on_link(link_id) for link_id in engine.links
    }
    before_storage = {
        link_id: engine.link_storage(link_id).storage for link_id in engine.links
    }

    with pytest.raises(EventCacheConsistencyError, match="expects downstream link"):
        engine._transfer_packet_between_links(packet.packet_id, "L1", "L3")

    assert engine.event_log == before_events
    assert dict(engine.packets) == before_packets
    assert {
        link_id: engine.packet_ids_on_link(link_id) for link_id in engine.links
    } == before_memberships
    assert {
        link_id: engine.link_storage(link_id).storage for link_id in engine.links
    } == before_storage
    assert _link_memberships(engine, packet.packet_id) == ("L1",)
    assert engine.check_event_cache_consistency()


def test_cancel_in_transit_exits_link_before_terminal_event() -> None:
    engine = LoadingEngine(links={"L1": _link("L1", free_flow_ticks=3)})
    packet = engine.instantiate(
        DemandDeclaration("D1", departure_tick=0, route_intent=("L1",))
    )
    assert packet is not None

    cancelled = engine.cancel_packet(packet.packet_id)

    assert cancelled.lifecycle_state == LifecycleState.CANCELLED
    assert _packet_event_types(engine, packet.packet_id)[-2:] == (
        EventType.LINK_EXIT,
        EventType.CANCELLED,
    )
    assert _link_memberships(engine, packet.packet_id) == ()
    assert engine.conservation_summary() == {
        "instantiated": 1,
        "in_flight": 0,
        "completed": 0,
        "cancelled": 1,
        "unresolved": 0,
    }
    assert engine.check_event_cache_consistency()

    before_events = engine.event_log
    with pytest.raises(ValueError, match="already terminal"):
        engine.cancel_packet(packet.packet_id)
    assert engine.event_log == before_events


def test_cancel_queued_packet_clears_queue_and_link_before_terminal_event() -> None:
    engine, packet_id = _two_link_engine()
    engine.set_receiving_open("L2", False)
    engine.step()

    engine.cancel_packet(packet_id)

    assert _packet_event_types(engine, packet_id)[-3:] == (
        EventType.QUEUE_EXIT,
        EventType.LINK_EXIT,
        EventType.CANCELLED,
    )
    assert engine.packet_ids_in_queue("L1", "L2") == ()
    assert _link_memberships(engine, packet_id) == ()
    assert engine.check_event_cache_consistency()
    assert engine.check_conservation()
    assert validate_loading_kernel(engine).is_valid


def test_consolidated_validation_report_and_exact_rerun_are_explicit() -> None:
    engine = run_composition_validation_case()

    report_without_rerun = validate_loading_kernel(engine)
    assert report_without_rerun.is_valid
    assert report_without_rerun.exact_deterministic_rerun.passed is None
    assert all(
        check.passed
        for check in report_without_rerun.checks
        if check.was_run
    )

    report_with_rerun = validate_loading_kernel(
        engine,
        exact_rerun_factory=run_composition_validation_case,
    )
    assert report_with_rerun.is_valid
    assert report_with_rerun.exact_deterministic_rerun.passed is True
    assert report_with_rerun.event_count == len(engine.event_log)
    assert report_with_rerun.current_tick == engine.current_tick


def _two_link_engine() -> tuple[LoadingEngine, str]:
    engine = LoadingEngine(links={"L1": _link("L1"), "L2": _link("L2")})
    packet = engine.instantiate(
        DemandDeclaration("D1", departure_tick=0, route_intent=("L1", "L2"))
    )
    assert packet is not None
    return engine, packet.packet_id


def _link(link_id: str, *, free_flow_ticks: int = 1) -> Link:
    return Link(
        link_id=link_id,
        free_flow_ticks=free_flow_ticks,
        declared_sending_capacity_per_tick=1,
        declared_receiving_capacity_per_tick=1,
        declared_storage_capacity_packets=4,
    )


def _packet_event_types(
    engine: LoadingEngine,
    packet_id: str,
) -> tuple[EventType, ...]:
    return tuple(
        event.event_type
        for event in engine.event_log
        if event.packet_id == packet_id
    )


def _packet_event_entities(
    engine: LoadingEngine,
    packet_id: str,
) -> tuple[str, ...]:
    return tuple(
        event.entity_id
        for event in engine.event_log
        if event.packet_id == packet_id
    )


def _link_memberships(
    engine: LoadingEngine,
    packet_id: str,
) -> tuple[str, ...]:
    return tuple(
        link_id
        for link_id in sorted(engine.links)
        if packet_id in engine.packet_ids_on_link(link_id)
    )
