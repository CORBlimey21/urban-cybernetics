# SPDX-License-Identifier: MPL-2.0
"""Deterministic adversarial regression scenarios for the parity kernel."""

from __future__ import annotations

from urban_cybernetics.core import (
    EventType,
    Node,
)

from .helpers import (
    assert_boundary_event_order,
    assert_core_invariants,
    boundary_event_packet_ids,
    demand,
    instantiate_demands,
    link_event_packet_ids,
    parity_engine,
    physical_link,
    queue_lengths_by_tick,
    realised_path,
    run_ticks,
)


def test_empty_link_has_zero_counts_and_no_queue_artifacts() -> None:
    engine = parity_engine(links={"L1": physical_link("L1")})

    run_ticks(engine, 3)

    assert engine.cumulative_counts("L1").entries == 0
    assert engine.cumulative_counts("L1").exits == 0
    assert engine.link_storage("L1").storage == 0
    assert engine.event_log == ()


def test_single_packet_free_flow_and_destination_completion_are_coherent() -> None:
    engine = parity_engine(links={"L1": physical_link("L1", free_flow_ticks=2)})
    packet = engine.instantiate(demand("D1", ("L1",)))

    run_ticks(engine, 2)

    assert link_event_packet_ids(engine, EventType.LINK_ENTRY, "L1", 0) == [
        packet.packet_id
    ]
    assert link_event_packet_ids(engine, EventType.LINK_EXIT, "L1", 2) == [
        packet.packet_id
    ]
    assert realised_path(engine, packet.packet_id) == ("L1",)
    assert_boundary_event_order(engine, packet.packet_id)


def test_capacity_saturation_and_fractional_carry_preserve_fifo_prefixes() -> None:
    engine = parity_engine(
        links={"L1": physical_link("L1", sending_capacity=99, storage=8)},
        sending_rates={"L1": 1.5},
    )
    packets = [
        engine.instantiate(demand(f"D{index}", ("L1",)))
        for index in range(4)
    ]

    run_ticks(engine, 3)

    assert link_event_packet_ids(engine, EventType.LINK_EXIT, "L1", 1) == [
        packets[0].packet_id
    ]
    assert link_event_packet_ids(engine, EventType.LINK_EXIT, "L1", 2) == [
        packets[1].packet_id,
        packets[2].packet_id,
    ]
    assert link_event_packet_ids(engine, EventType.LINK_EXIT, "L1", 3) == [
        packets[3].packet_id
    ]


def test_storage_limit_origin_admission_waits_for_backward_wave_vacancy() -> None:
    engine = parity_engine(links={"L1": physical_link("L1", storage=1)})
    first = engine.instantiate(demand("D1", ("L1",)))
    second = engine.instantiate(demand("D2", ("L1",)))

    assert second is None
    assert tuple(demand.demand_id for demand in engine.pending_demands) == ("D2",)

    run_ticks(engine, 3)

    assert link_event_packet_ids(engine, EventType.LINK_EXIT, "L1", 1) == [
        first.packet_id
    ]
    assert link_event_packet_ids(engine, EventType.LINK_ENTRY, "L1", 3) == ["P2"]
    assert engine.pending_demands == ()


def test_receiving_limit_creates_grows_releases_fifo_queue_with_count_agreement() -> None:
    engine = parity_engine(
        links={
            "L1": physical_link("L1", sending_capacity=5, storage=8),
            "L2": physical_link("L2", receiving_capacity=1, storage=8),
        },
        nodes=(
            Node(
                "N",
                incoming_link_ids=("L1",),
                outgoing_link_ids=("L2",),
            ),
        ),
    )
    packets = [engine.instantiate(demand(f"D{index}", ("L1", "L2"))) for index in range(4)]

    run_ticks(engine, 5)

    assert link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 1) == [
        packets[0].packet_id
    ]
    assert boundary_event_packet_ids(engine, EventType.QUEUE_ENTRY, "boundary:L1->L2", 1) == [
        packets[1].packet_id,
        packets[2].packet_id,
        packets[3].packet_id,
    ]
    assert boundary_event_packet_ids(engine, EventType.QUEUE_EXIT, "boundary:L1->L2") == [
        packets[1].packet_id,
        packets[2].packet_id,
        packets[3].packet_id,
    ]
    assert queue_lengths_by_tick(engine, "boundary:L1->L2") == (0, 3, 2, 1, 0, 0)


def test_blocked_diverge_head_prevents_tail_from_bypassing_to_open_branch() -> None:
    engine = parity_engine(
        links={
            "L1": physical_link("L1", sending_capacity=2, storage=8),
            "L2": physical_link("L2", receiving_capacity=1, storage=4),
            "L3": physical_link("L3", receiving_capacity=1, storage=4),
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
    head = engine.instantiate(demand("D-head", ("L1", "L2")))
    tail = engine.instantiate(demand("D-tail", ("L1", "L3")))

    run_ticks(engine, 1)

    assert engine.packet_ids_in_queue("L1", "L2") == (head.packet_id,)
    assert link_event_packet_ids(engine, EventType.LINK_ENTRY, "L3", 1) == []
    assert tail.packet_id in engine.packet_ids_on_link("L1")

    engine.set_receiving_open("L2", True)
    run_ticks(engine, 2)

    assert realised_path(engine, head.packet_id) == ("L1", "L2")
    assert realised_path(engine, tail.packet_id) == ("L1", "L3")


def test_three_link_spillback_propagates_and_then_dissipates() -> None:
    engine = parity_engine(
        links={
            "L1": physical_link("L1", storage=4, receiving_capacity=4),
            "L2": physical_link("L2", storage=1, receiving_capacity=4),
            "L3": physical_link("L3", storage=1, receiving_capacity=4),
        }
    )
    instantiate_demands(
        engine,
        (
            demand("D-blocker", ("L3",)),
            demand("D-middle", ("L2", "L3")),
            demand("D-upstream", ("L1", "L2", "L3")),
        ),
    )

    run_ticks(engine, 5)

    assert link_event_packet_ids(engine, EventType.LINK_ENTRY, "L3", 3) == ["P2"]
    assert link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 5) == ["P3"]
    assert engine.packet_ids_in_queue("L1", "L2") == ()
    assert engine.packet_ids_in_queue("L2", "L3") == ()


def test_lane_drop_spillback_releases_at_downstream_rate() -> None:
    engine = parity_engine(
        links={
            "L1": physical_link("L1", sending_capacity=4, storage=8),
            "L2": physical_link("L2", receiving_capacity=1, storage=8),
        },
        receiving_rates={"L2": 1.0},
    )
    packets = [engine.instantiate(demand(f"D{index}", ("L1", "L2"))) for index in range(4)]

    run_ticks(engine, 4)

    assert link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2") == [
        packet.packet_id for packet in packets
    ]
    assert queue_lengths_by_tick(engine, "boundary:L1->L2") == (0, 3, 2, 1, 0)


def test_priority_merge_fairness_unused_share_and_ordering_invariance() -> None:
    first = _priority_merge_engine(("L1", "L2", "L3"))
    second = _priority_merge_engine(("L3", "L2", "L1"))
    for engine in (first, second):
        instantiate_demands(
            engine,
            tuple(demand(f"D-L1-{index}", ("L1", "L3")) for index in range(4))
            + tuple(demand(f"D-L2-{index}", ("L2", "L3")) for index in range(2)),
        )
        run_ticks(engine, 6)

    expected = ["L1", "L2", "L1", "L1", "L2", "L1"]
    assert _l3_entry_source_sequence(first) == expected
    assert _l3_entry_source_sequence(second) == expected

    unused_share_engine = _priority_merge_engine(
        ("L1", "L2", "L3"),
        weights=(("L1", 3), ("L2", 1)),
        l3_receiving_capacity=2,
        l2_sending_capacity=2,
    )
    instantiate_demands(
        unused_share_engine,
        tuple(demand(f"D-only-L2-{index}", ("L2", "L3")) for index in range(3)),
    )
    run_ticks(unused_share_engine, 1)

    assert link_event_packet_ids(unused_share_engine, EventType.LINK_ENTRY, "L3", 1) == [
        "P1",
        "P2",
    ]
    assert_core_invariants(unused_share_engine)


def _priority_merge_engine(
    link_order: tuple[str, str, str],
    *,
    weights: tuple[tuple[str, int], ...] = (("L1", 2), ("L2", 1)),
    l3_receiving_capacity: int = 1,
    l2_sending_capacity: int = 1,
):
    link_by_id = {
        "L1": physical_link("L1", sending_capacity=1, storage=12),
        "L2": physical_link("L2", sending_capacity=l2_sending_capacity, storage=12),
        "L3": physical_link("L3", receiving_capacity=l3_receiving_capacity, storage=12),
    }
    return parity_engine(
        links={link_id: link_by_id[link_id] for link_id in link_order},
        nodes=(
            Node(
                "N",
                incoming_link_ids=("L1", "L2"),
                outgoing_link_ids=("L3",),
                merge_priorities=weights,
            ),
        ),
    )


def _l3_entry_source_sequence(engine) -> list[str]:
    return [
        engine.packets[event.packet_id].route_intent[0]
        for event in engine.event_log
        if event.event_type == EventType.LINK_ENTRY and event.entity_id == "L3"
    ]
