"""M8 link fixtures with independently specified analytical oracles.

Expected tables in this module are literal fixture data.  They are not built
with UC loading, cumulative-count, spillback, or validation helpers.  UC is
used only to execute the physical case; observed series are folded directly
from the canonical event log.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

import pytest

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import DemandDeclaration, Event, EventType, Link
from urban_cybernetics.loading import LoadingEngine


EXACT_COUNT_TOLERANCE_PACKETS = 0
EXACT_TICK_TOLERANCE_TICKS = 0
FLOAT_TOLERANCE = 1e-12


@dataclass(frozen=True, slots=True)
class LinkFixture:
    """Physical inputs for a triangular-FD-consistent unit-packet link."""

    link_id: str
    length_m: float
    free_flow_speed_mps: float
    backward_wave_speed_mps: float
    jam_density_veh_per_km_per_lane: float
    capacity_veh_per_hour_per_lane: float
    tick_duration_seconds: float
    receiving_capacity_per_tick: int

    @property
    def free_flow_lag_ticks(self) -> int:
        return ceil(
            self.length_m
            / self.free_flow_speed_mps
            / self.tick_duration_seconds
        )

    @property
    def backward_wave_lag_ticks(self) -> int:
        return ceil(
            self.length_m
            / self.backward_wave_speed_mps
            / self.tick_duration_seconds
        )

    @property
    def integer_capacity_per_tick(self) -> int:
        value = (
            self.capacity_veh_per_hour_per_lane
            * self.tick_duration_seconds
            / 3600.0
        )
        assert value.is_integer()
        return int(value)

    def as_uc_link(self) -> Link:
        return Link(
            link_id=self.link_id,
            length_m=self.length_m,
            lane_count=1,
            free_flow_speed_mps=self.free_flow_speed_mps,
            backward_wave_speed_mps=self.backward_wave_speed_mps,
            jam_density_veh_per_km_per_lane=self.jam_density_veh_per_km_per_lane,
            capacity_veh_per_hour_per_lane=self.capacity_veh_per_hour_per_lane,
            tick_duration_seconds=self.tick_duration_seconds,
            declared_sending_capacity_per_tick=self.integer_capacity_per_tick,
            # Origin admission also provides the fixture's explicit initial
            # pulse/preload.  It is separate from downstream sending capacity.
            declared_receiving_capacity_per_tick=self.receiving_capacity_per_tick,
        )


# q = 3.6*v*w*kj/(v+w).  With v=10 m/s and w=5 m/s, kj=120 gives
# q=1,440 veh/h (four packets per ten-second tick); kj=30 gives 360
# veh/h (one packet per ten-second tick).
UNCONGESTED_LINK = LinkFixture(
    "L1", 200.0, 10.0, 5.0, 120.0, 1440.0, 10.0, 4
)
BOTTLENECK_LINK = LinkFixture(
    "L1", 200.0, 10.0, 5.0, 30.0, 360.0, 10.0, 5
)

# q=900 veh/h is one packet per four-second tick and kj=75 veh/km.
# A 40 m link therefore stores floor(0.04*75)=3 unit packets.
VACANCY_UPSTREAM = LinkFixture(
    "L1", 40.0, 10.0, 5.0, 75.0, 900.0, 4.0, 3
)
VACANCY_DOWNSTREAM = LinkFixture(
    "L2", 40.0, 10.0, 5.0, 75.0, 900.0, 4.0, 3
)


def _engine(*fixtures: LinkFixture) -> LoadingEngine:
    links = {fixture.link_id: fixture.as_uc_link() for fixture in fixtures}
    return LoadingEngine(
        links=links,
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
    )


def _submit(engine: LoadingEngine, demand_id: str, route: tuple[str, ...]) -> str:
    packet = engine.instantiate(DemandDeclaration(demand_id, 0, route))
    assert packet is not None
    return packet.packet_id


def _run_to_tick(engine: LoadingEngine, final_tick: int) -> None:
    while engine.current_tick < final_tick:
        engine.step()


def _event_count_series(
    events: tuple[Event, ...],
    *,
    event_type: EventType,
    entity_id: str,
    final_tick: int,
) -> tuple[int, ...]:
    """Inclusive cumulative event count folded without UC count helpers."""

    return tuple(
        sum(
            event.event_type == event_type
            and event.entity_id == entity_id
            and event.physical_tick <= tick
            for event in events
        )
        for tick in range(final_tick + 1)
    )


def _event_tick_by_packet(
    events: tuple[Event, ...],
    event_type: EventType,
    entity_id: str,
) -> dict[str, int]:
    return {
        event.packet_id: event.physical_tick
        for event in events
        if event.event_type == event_type and event.entity_id == entity_id
    }


def _point_queue(
    cumulative_entries: tuple[int, ...],
    cumulative_exits: tuple[int, ...],
    free_flow_lag_ticks: int,
) -> tuple[int, ...]:
    """Exit-boundary vertical queue Q(t)=max(Nin(t-tau)-Nout(t), 0)."""

    return tuple(
        max(
            (
                cumulative_entries[tick - free_flow_lag_ticks]
                if tick >= free_flow_lag_ticks
                else 0
            )
            - cumulative_exits[tick],
            0,
        )
        for tick in range(len(cumulative_exits))
    )


def _assert_exact_series(observed: tuple[int, ...], expected: tuple[int, ...]) -> None:
    assert len(observed) == len(expected)
    assert max((abs(a - b) for a, b in zip(observed, expected)), default=0) <= (
        EXACT_COUNT_TOLERANCE_PACKETS
    )


def test_m8_uncongested_single_link_translation() -> None:
    """M8-LINK-01: a below-capacity pulse translates by exactly L/v."""

    expected_entries = (3, 3, 3, 3)
    expected_exits = (0, 0, 3, 3)
    expected_point_queue = (0, 0, 0, 0)
    expected_exit_ticks = (2, 2, 2)

    engine = _engine(UNCONGESTED_LINK)
    packet_ids = tuple(
        _submit(engine, f"D{index}", ("L1",)) for index in range(3)
    )
    _run_to_tick(engine, 3)

    events = engine.event_log
    entries = _event_count_series(
        events,
        event_type=EventType.LINK_ENTRY,
        entity_id="L1",
        final_tick=3,
    )
    exits = _event_count_series(
        events,
        event_type=EventType.LINK_EXIT,
        entity_id="L1",
        final_tick=3,
    )
    exit_tick_by_packet = _event_tick_by_packet(events, EventType.LINK_EXIT, "L1")

    assert UNCONGESTED_LINK.free_flow_lag_ticks == 2
    assert UNCONGESTED_LINK.integer_capacity_per_tick == 4
    _assert_exact_series(entries, expected_entries)
    _assert_exact_series(exits, expected_exits)
    _assert_exact_series(
        _point_queue(entries, exits, UNCONGESTED_LINK.free_flow_lag_ticks),
        expected_point_queue,
    )
    assert tuple(exit_tick_by_packet[packet_id] for packet_id in packet_ids) == (
        expected_exit_ticks
    )
    assert not any(event.event_type == EventType.QUEUE_ENTRY for event in events)
    assert entries[-1] - exits[-1] == 0
    assert len(engine.completed_packet_ids) == len(packet_ids)


def test_m8_capacity_constrained_single_link() -> None:
    """M8-LINK-02: a five-packet pulse discharges at one packet per tick."""

    expected_entries = (5, 5, 5, 5, 5, 5, 5)
    expected_exits = (0, 0, 1, 2, 3, 4, 5)
    expected_point_queue = (0, 0, 4, 3, 2, 1, 0)
    expected_exit_ticks = (2, 3, 4, 5, 6)
    expected_experienced_delay_ticks = (0, 1, 2, 3, 4)

    engine = _engine(BOTTLENECK_LINK)
    packet_ids = tuple(
        _submit(engine, f"D{index}", ("L1",)) for index in range(5)
    )
    _run_to_tick(engine, 6)

    events = engine.event_log
    entries = _event_count_series(
        events,
        event_type=EventType.LINK_ENTRY,
        entity_id="L1",
        final_tick=6,
    )
    exits = _event_count_series(
        events,
        event_type=EventType.LINK_EXIT,
        entity_id="L1",
        final_tick=6,
    )
    entry_tick_by_packet = _event_tick_by_packet(events, EventType.LINK_ENTRY, "L1")
    exit_tick_by_packet = _event_tick_by_packet(events, EventType.LINK_EXIT, "L1")
    experienced_delay_ticks = tuple(
        exit_tick_by_packet[packet_id]
        - entry_tick_by_packet[packet_id]
        - BOTTLENECK_LINK.free_flow_lag_ticks
        for packet_id in packet_ids
    )

    assert BOTTLENECK_LINK.free_flow_lag_ticks == 2
    assert BOTTLENECK_LINK.integer_capacity_per_tick == 1
    _assert_exact_series(entries, expected_entries)
    _assert_exact_series(exits, expected_exits)
    _assert_exact_series(
        _point_queue(entries, exits, BOTTLENECK_LINK.free_flow_lag_ticks),
        expected_point_queue,
    )
    assert tuple(exit_tick_by_packet[packet_id] for packet_id in packet_ids) == (
        expected_exit_ticks
    )
    assert experienced_delay_ticks == expected_experienced_delay_ticks
    assert sum(experienced_delay_ticks) / len(experienced_delay_ticks) == pytest.approx(
        2.0,
        abs=FLOAT_TOLERANCE,
    )
    assert max(expected_point_queue) == 4
    assert expected_point_queue[-1] == 0
    assert entries[-1] - exits[-1] == 0
    assert len(engine.completed_packet_ids) == len(packet_ids)


def test_m8_backward_wave_vacancy_propagation() -> None:
    """M8-LINK-03: vacancy released at tick 1 reaches upstream at tick 3."""

    expected_l2_entries = (3, 3, 3, 4)
    expected_l2_exits = (0, 1, 2, 3)
    expected_boundary_queue_entries = (0, 1, 1, 1)
    expected_boundary_queue_exits = (0, 0, 0, 1)
    expected_pre_accept_vacancy = (0, 0, 0, 1)

    engine = _engine(VACANCY_UPSTREAM, VACANCY_DOWNSTREAM)
    for index in range(3):
        _submit(engine, f"D-blocker-{index}", ("L2",))
    upstream_packet_id = _submit(engine, "D-upstream", ("L1", "L2"))

    assert engine.parity_link_supply_view("L2").available_receiving_slots == 0
    engine.step()
    assert engine.parity_link_supply_view("L2").available_receiving_slots == 0
    engine.step()
    assert engine.parity_link_supply_view("L2").available_receiving_slots == 0
    engine.step()

    events = engine.event_log
    l2_entries = _event_count_series(
        events,
        event_type=EventType.LINK_ENTRY,
        entity_id="L2",
        final_tick=3,
    )
    l2_exits = _event_count_series(
        events,
        event_type=EventType.LINK_EXIT,
        entity_id="L2",
        final_tick=3,
    )
    queue_entries = _event_count_series(
        events,
        event_type=EventType.QUEUE_ENTRY,
        entity_id="boundary:L1->L2",
        final_tick=3,
    )
    queue_exits = _event_count_series(
        events,
        event_type=EventType.QUEUE_EXIT,
        entity_id="boundary:L1->L2",
        final_tick=3,
    )

    # Independent pre-accept supply: R(t)=min(q*dt,
    # K+Nout(t-lag)-Nin(t before the candidate is accepted)).
    l2_entries_before_candidate = (3, 3, 3, 3)
    pre_accept_vacancy = tuple(
        max(
            3
            + (
                l2_exits[tick - VACANCY_DOWNSTREAM.backward_wave_lag_ticks]
                if tick >= VACANCY_DOWNSTREAM.backward_wave_lag_ticks
                else 0
            )
            - l2_entries_before_candidate[tick],
            0,
        )
        for tick in range(4)
    )

    assert VACANCY_DOWNSTREAM.backward_wave_lag_ticks == 2
    assert VACANCY_DOWNSTREAM.as_uc_link().declared_storage_capacity_packets == 3
    _assert_exact_series(l2_entries, expected_l2_entries)
    _assert_exact_series(l2_exits, expected_l2_exits)
    _assert_exact_series(queue_entries, expected_boundary_queue_entries)
    _assert_exact_series(queue_exits, expected_boundary_queue_exits)
    _assert_exact_series(pre_accept_vacancy, expected_pre_accept_vacancy)

    upstream_l2_entry = next(
        event
        for event in events
        if event.packet_id == upstream_packet_id
        and event.event_type == EventType.LINK_ENTRY
        and event.entity_id == "L2"
    )
    assert abs(upstream_l2_entry.physical_tick - 3) <= EXACT_TICK_TOLERANCE_TICKS
    assert l2_exits[1] == 1
    assert pre_accept_vacancy[1:3] == (0, 0)
    assert pre_accept_vacancy[3] == 1
    assert queue_entries[-1] - queue_exits[-1] == 0
    assert all(entries >= exits for entries, exits in zip(l2_entries, l2_exits))
