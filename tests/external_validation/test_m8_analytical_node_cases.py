# SPDX-License-Identifier: MPL-2.0
"""M8 NODE-01 fixtures with allocator-independent arithmetic oracles."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import DemandDeclaration, EventType, Link, Node
from urban_cybernetics.loading import LoadingEngine


@dataclass(frozen=True, slots=True)
class NodeCase:
    name: str
    demand: int
    supplies: tuple[int, ...]
    initially_closed: bool = False
    reopen_tick: int | None = None
    fractional_rate: float | None = None


CASES = (
    NodeCase("demand_limited", 1, (3, 3)),
    NodeCase("supply_limited", 3, (1, 1, 1)),
    NodeCase("equal_demand_supply", 2, (2, 2)),
    NodeCase("zero_demand", 0, (3,)),
    NodeCase("zero_supply", 2, (0, 0)),
    NodeCase("reopening", 2, (0, 2, 2), initially_closed=True, reopen_tick=2),
    NodeCase("fractional", 6, (1, 2, 1, 2), fractional_rate=1.5),
)


def _link(link_id: str, *, receiving: int) -> Link:
    return Link(
        link_id=link_id,
        length_m=10.0,
        lane_count=1,
        free_flow_speed_mps=10.0,
        backward_wave_speed_mps=5.0,
        jam_density_veh_per_km_per_lane=1800.0,
        capacity_veh_per_hour_per_lane=21600.0,
        tick_duration_seconds=1.0,
        declared_sending_capacity_per_tick=6,
        declared_receiving_capacity_per_tick=receiving,
    )


def _independent_oracle(demand: int, supplies: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    """Return candidates, approvals, and queue using only F=min(D,S)."""

    remaining = demand
    candidates = []
    approvals = []
    queue = []
    for supply in supplies:
        candidates.append(remaining)
        approved = min(remaining, supply)
        approvals.append(approved)
        remaining -= approved
        queue.append(remaining)
    return tuple(candidates), tuple(approvals), tuple(queue)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_m8_node_01_matches_independent_min_demand_supply_oracle(case: NodeCase) -> None:
    expected_candidates, expected_approvals, expected_queue = _independent_oracle(case.demand, case.supplies)
    expected_transfer_ticks = tuple(
        tick
        for tick, count in enumerate(expected_approvals, start=1)
        for _ in range(count)
    )
    engine = LoadingEngine(
        links={"L1": _link("L1", receiving=6), "L2": _link("L2", receiving=max(case.supplies))},
        nodes=(Node("N1", incoming_link_ids=("L1",), outgoing_link_ids=("L2",)),),
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        parity_receiving_capacity_vehicles_per_tick_by_link={"L2": case.fractional_rate} if case.fractional_rate is not None else None,
    )
    for index in range(case.demand):
        engine.instantiate(DemandDeclaration(f"D{index}", 0, ("L1", "L2")))
    if case.initially_closed:
        engine.set_receiving_open("L2", False)

    observed_candidates = []
    observed_approvals = []
    observed_queue = []
    for tick in range(1, len(case.supplies) + 1):
        if case.reopen_tick == tick:
            engine.set_receiving_open("L2", True)
        engine.step()
        traces = engine.node_transfer_traces()
        observed_candidates.append(sum(len(trace.candidate_packet_ids) for trace in traces))
        observed_approvals.append(sum(len(trace.approved_packet_ids) for trace in traces))
        queue_entries = sum(event.event_type == EventType.QUEUE_ENTRY for event in engine.event_log)
        queue_exits = sum(event.event_type == EventType.QUEUE_EXIT for event in engine.event_log)
        observed_queue.append(queue_entries - queue_exits)

    transfer_ticks = tuple(
        event.physical_tick
        for event in engine.event_log
        if event.event_type == EventType.LINK_ENTRY and event.entity_id == "L2"
    )
    assert tuple(observed_candidates) == expected_candidates
    assert tuple(observed_approvals) == expected_approvals
    assert tuple(observed_queue) == expected_queue
    assert transfer_ticks == expected_transfer_ticks
    assert engine.check_conservation()
