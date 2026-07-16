"""Composition-level regression for the frozen base loading kernel."""

from __future__ import annotations

from urban_cybernetics.core import EventType, LifecycleState
from urban_cybernetics.canonical_validation import (
    COMPOSITION_BOUNDARIES,
    COMPOSITION_CASE_ID,
    COMPOSITION_CASE_VERSION,
    COMPOSITION_FINAL_TICK,
    COMPOSITION_LINK_IDS,
    COMPOSITION_ROUTES,
    run_composition_validation_case,
)
from urban_cybernetics.validation import (
    ValidationContext,
    assess_physical_parameter_eligibility,
)


EXPECTED_STORAGE = {
    "L1": (3, 3, 2, 1, 1, 0, 0, 0, 0, 0, 0),
    "L2": (3, 3, 2, 1, 1, 1, 0, 0, 0, 0, 0),
    "L3": (0, 2, 2, 4, 3, 3, 3, 2, 1, 0, 0),
    "L4": (0, 0, 2, 1, 1, 1, 1, 1, 1, 1, 0),
}
EXPECTED_QUEUES = {
    ("L1", "L3"): (0, 2, 2, 1, 1, 0, 0, 0, 0, 0, 0),
    ("L2", "L3"): (0, 2, 2, 1, 1, 1, 0, 0, 0, 0, 0),
    ("L3", "L4"): (0, 0, 0, 2, 1, 1, 1, 1, 1, 0, 0),
}


def test_composed_case_declares_minimal_physical_merge_network() -> None:
    engine = run_composition_validation_case()

    assert COMPOSITION_CASE_ID == "M8-COMP-NET-01"
    assert COMPOSITION_CASE_VERSION == "1"
    assert tuple(engine.links) == COMPOSITION_LINK_IDS
    assert {packet.route_intent for packet in engine.packets.values()} == set(
        COMPOSITION_ROUTES
    )
    assert len(engine.packets) == 8
    assert tuple(node.node_id for node in engine.nodes.values()) == (
        "N-MERGE",
        "N-BOTTLENECK",
    )
    physical = assess_physical_parameter_eligibility(
        engine.links.values(), model_profile_id=engine.model_profile_id
    )
    assert physical.is_parity_eligible
    assert physical.ineligibility_reasons == ()


def test_composed_case_forms_multilink_spillback_then_clears() -> None:
    engine = run_composition_validation_case()

    for link_id, expected in EXPECTED_STORAGE.items():
        observed = tuple(
            point.storage
            for point in engine.link_storage_series(
                link_id, max_tick=COMPOSITION_FINAL_TICK
            )
        )
        assert observed == expected
        assert max(observed) <= engine.links[link_id].declared_storage_capacity_packets

    for boundary, expected in EXPECTED_QUEUES.items():
        observed = tuple(
            sum(
                event.event_type == EventType.QUEUE_ENTRY
                and event.entity_id == f"boundary:{boundary[0]}->{boundary[1]}"
                and event.physical_tick <= tick
                for event in engine.event_log
            )
            - sum(
                event.event_type == EventType.QUEUE_EXIT
                and event.entity_id == f"boundary:{boundary[0]}->{boundary[1]}"
                and event.physical_tick <= tick
                for event in engine.event_log
            )
            for tick in range(COMPOSITION_FINAL_TICK + 1)
        )
        assert observed == expected

    # At tick 3 the intermediate link is full, its downstream queue is active,
    # and both origin links retain queued packets. All three queues later clear.
    assert EXPECTED_STORAGE["L3"][3] == 4
    assert all(EXPECTED_QUEUES[boundary][3] > 0 for boundary in COMPOSITION_BOUNDARIES)
    assert all(EXPECTED_QUEUES[boundary][-1] == 0 for boundary in COMPOSITION_BOUNDARIES)
    assert all(
        packet.lifecycle_state == LifecycleState.COMPLETED
        for packet in engine.packets.values()
    )


def test_composed_case_preserves_counts_fifo_conservation_and_replay() -> None:
    engine = run_composition_validation_case()
    replay = run_composition_validation_case()
    context = ValidationContext.from_engine(engine, nodes=tuple(engine.nodes.values()))

    assert engine.event_log == replay.event_log
    assert engine.packets == replay.packets
    assert engine.check_conservation()
    assert engine.check_event_cache_consistency()
    assert context.count_consistency_report.is_consistent
    assert context.count_consistency_report.route_counts_supported

    expected_final_counts = {
        "L1": (4, 4),
        "L2": (4, 4),
        "L3": (8, 8),
        "L4": (8, 8),
    }
    for link_id, (entries, exits) in expected_final_counts.items():
        assert engine.cumulative_entries(link_id) == entries
        assert engine.cumulative_exits(link_id) == exits
        entry_order = tuple(
            event.packet_id
            for event in engine.event_log
            if event.event_type == EventType.LINK_ENTRY
            and event.entity_id == link_id
        )
        exit_order = tuple(
            event.packet_id
            for event in engine.event_log
            if event.event_type == EventType.LINK_EXIT
            and event.entity_id == link_id
        )
        assert exit_order == entry_order

    for packet_id in engine.packets:
        packet_events = context.events_by_packet_id[packet_id]
        event_types = tuple(event.event_type for event in packet_events)
        assert event_types[0] == EventType.INSTANTIATED
        assert event_types[-1] == EventType.COMPLETED
        assert tuple(
            event.entity_id
            for event in packet_events
            if event.event_type == EventType.LINK_ENTRY
        ) == engine.packets[packet_id].route_intent
