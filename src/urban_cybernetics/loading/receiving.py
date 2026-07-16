"""Event-derived LTM-style link receiving views."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from math import ceil, floor

from urban_cybernetics.core import Event, EventType, Link
from urban_cybernetics.loading.cumulative_counts import (
    cumulative_entries,
    cumulative_exits,
    link_storage,
)


@dataclass(frozen=True, slots=True)
class LinkReceivingView:
    """Receiving slots one downstream link can accept at one tick."""

    link_id: str
    tick: int
    receiving_open: bool
    receiving_capacity: int
    already_accepted_count: int
    current_storage: int
    storage_capacity: int
    available_storage_space: int
    available_receiving_slots: int


class ReceivingCause(Enum):
    """Auditable cause for a parity receiving decision."""

    OPEN = "open"
    GOVERNANCE_CLOSED = "governance_closed"
    PHYSICAL_SHORTAGE = "physical_shortage"
    RECEIVING_CAPACITY_EXHAUSTED = "receiving_capacity_exhausted"


@dataclass(frozen=True, slots=True)
class VacancyLagState:
    """Backward-wave vacancy state for one link and tick."""

    link_id: str
    tick: int
    backward_wave_lag_ticks: int
    lagged_downstream_exit_tick: int
    lagged_downstream_exit_count: int
    current_upstream_entry_count: int
    storage_capacity: int
    raw_physical_vacancy: int
    available_physical_vacancy: int


@dataclass(frozen=True, slots=True)
class LinkSupplyView:
    """Parity receiving supply at a link upstream boundary."""

    link_id: str
    tick: int
    receiving_open: bool
    receiving_cause: ReceivingCause
    receiving_capacity_vehicles_per_tick: float
    receiving_capacity_carry_in: float
    integer_receiving_capacity: int
    receiving_capacity_carry_out: float
    already_accepted_count: int
    available_receiving_capacity: int
    vacancy: VacancyLagState
    available_receiving_slots: int


@dataclass(frozen=True, slots=True)
class ReceivingDecisionTrace:
    """M4 parity receiving decision trace for validation and provenance."""

    link_id: str
    tick: int
    supply_view: LinkSupplyView


def link_receiving_view(
    events: Iterable[Event],
    link: Link,
    tick: int,
    receiving_open: bool,
    already_accepted_count: int = 0,
) -> LinkReceivingView:
    """Return event-derived receiving availability for one link and tick."""

    event_tuple = tuple(events)
    receiving_capacity = link.declared_receiving_capacity_per_tick
    storage_capacity = link.declared_storage_capacity_packets
    if receiving_capacity < 0:
        raise ValueError(
            f"declared receiving capacity cannot be negative for {link.link_id}: "
            f"{receiving_capacity}"
        )
    if storage_capacity < 0:
        raise ValueError(
            f"declared storage capacity cannot be negative for {link.link_id}: "
            f"{storage_capacity}"
        )
    if already_accepted_count < 0:
        raise ValueError(
            f"already accepted count cannot be negative for {link.link_id}: "
            f"{already_accepted_count}"
        )

    same_tick_accepted_count = _same_tick_link_entries(
        event_tuple,
        link.link_id,
        tick,
    )
    accepted_count = already_accepted_count + same_tick_accepted_count
    current_storage = (
        link_storage(event_tuple, link.link_id, tick).storage
        - same_tick_accepted_count
    )
    if current_storage < 0:
        raise ValueError(
            f"link storage before same-tick entries is negative for {link.link_id} "
            f"at tick {tick}: {current_storage}"
        )

    available_receiving_capacity = max(receiving_capacity - accepted_count, 0)
    available_storage_space = max(
        storage_capacity - current_storage - accepted_count,
        0,
    )
    if receiving_open:
        available_receiving_slots = min(
            available_receiving_capacity,
            available_storage_space,
        )
    else:
        available_receiving_slots = 0

    return LinkReceivingView(
        link_id=link.link_id,
        tick=tick,
        receiving_open=receiving_open,
        receiving_capacity=receiving_capacity,
        already_accepted_count=accepted_count,
        current_storage=current_storage,
        storage_capacity=storage_capacity,
        available_storage_space=available_storage_space,
        available_receiving_slots=available_receiving_slots,
    )


def bounded_integer_receiving_capacity_carry(
    *,
    link_id: str,
    capacity_vehicles_per_tick: float,
    carry_in: float,
    actual_flow_packets: int = 0,
) -> tuple[int, float]:
    """Return de Souza integer supply and retained credit after one tick.

    Equation (6) retains unused whole-packet credit, subtracts realised flow,
    and caps the credit at ``ceil(C * dt) + 1``.  Equation (7) exposes only
    the integer floor of the credit available before the tick.
    """

    if capacity_vehicles_per_tick < 0:
        raise ValueError(
            f"capacity_vehicles_per_tick cannot be negative for {link_id}: "
            f"{capacity_vehicles_per_tick}"
        )
    if actual_flow_packets < 0:
        raise ValueError(
            f"actual_flow_packets cannot be negative for {link_id}: "
            f"{actual_flow_packets}"
        )
    credit_bound = ceil(capacity_vehicles_per_tick) + 1
    if carry_in < 0 or carry_in > credit_bound:
        raise ValueError(
            f"carry_in must be in [0, {credit_bound}] for {link_id}: {carry_in}"
        )
    integer_capacity = floor(carry_in)
    if actual_flow_packets > integer_capacity:
        raise ValueError(
            f"actual flow exceeds available receiving credit for {link_id}: "
            f"{actual_flow_packets} > {integer_capacity}"
        )
    carry_out = min(
        carry_in + capacity_vehicles_per_tick - actual_flow_packets,
        float(credit_bound),
    )
    return integer_capacity, carry_out


def parity_link_supply_view(
    events: Iterable[Event],
    link: Link,
    tick: int,
    *,
    receiving_open: bool,
    receiving_capacity_carry_in: float = 0.0,
    already_accepted_count: int = 0,
    capacity_vehicles_per_tick: float | None = None,
) -> LinkSupplyView:
    """Return parity receiving supply from lagged downstream vacancy."""

    if already_accepted_count < 0:
        raise ValueError("already_accepted_count cannot be negative")
    backward_wave_lag_ticks = _backward_wave_lag_ticks(link)
    event_tuple = tuple(events)
    lagged_downstream_exit_tick = tick - backward_wave_lag_ticks
    lagged_downstream_exit_count = (
        0
        if lagged_downstream_exit_tick < 0
        else cumulative_exits(event_tuple, link.link_id, lagged_downstream_exit_tick)
    )
    current_upstream_entry_count = cumulative_entries(event_tuple, link.link_id, tick)
    raw_physical_vacancy = (
        link.declared_storage_capacity_packets
        + lagged_downstream_exit_count
        - current_upstream_entry_count
    )
    available_physical_vacancy = max(
        raw_physical_vacancy - already_accepted_count,
        0,
    )
    capacity_rate = (
        float(link.declared_receiving_capacity_per_tick)
        if capacity_vehicles_per_tick is None
        else capacity_vehicles_per_tick
    )
    same_tick_accepted_count = _same_tick_link_entries(event_tuple, link.link_id, tick)
    integer_capacity, carry_out = bounded_integer_receiving_capacity_carry(
        link_id=link.link_id,
        capacity_vehicles_per_tick=capacity_rate,
        carry_in=receiving_capacity_carry_in,
        # Tick zero is the pre-step initial state; its authored entries are
        # initial conditions rather than flow in an executed recurrence tick.
        actual_flow_packets=(same_tick_accepted_count if tick > 0 else 0),
    )
    total_accepted_count = same_tick_accepted_count + already_accepted_count
    available_receiving_capacity = max(integer_capacity - total_accepted_count, 0)
    if not receiving_open:
        available_receiving_slots = 0
        cause = ReceivingCause.GOVERNANCE_CLOSED
    elif available_physical_vacancy <= 0:
        available_receiving_slots = 0
        cause = ReceivingCause.PHYSICAL_SHORTAGE
    elif available_receiving_capacity <= 0:
        available_receiving_slots = 0
        cause = ReceivingCause.RECEIVING_CAPACITY_EXHAUSTED
    else:
        available_receiving_slots = min(
            available_physical_vacancy,
            available_receiving_capacity,
        )
        cause = ReceivingCause.OPEN

    vacancy = VacancyLagState(
        link_id=link.link_id,
        tick=tick,
        backward_wave_lag_ticks=backward_wave_lag_ticks,
        lagged_downstream_exit_tick=lagged_downstream_exit_tick,
        lagged_downstream_exit_count=lagged_downstream_exit_count,
        current_upstream_entry_count=current_upstream_entry_count,
        storage_capacity=link.declared_storage_capacity_packets,
        raw_physical_vacancy=raw_physical_vacancy,
        available_physical_vacancy=available_physical_vacancy,
    )
    return LinkSupplyView(
        link_id=link.link_id,
        tick=tick,
        receiving_open=receiving_open,
        receiving_cause=cause,
        receiving_capacity_vehicles_per_tick=capacity_rate,
        receiving_capacity_carry_in=receiving_capacity_carry_in,
        integer_receiving_capacity=integer_capacity,
        receiving_capacity_carry_out=carry_out,
        already_accepted_count=total_accepted_count,
        available_receiving_capacity=available_receiving_capacity,
        vacancy=vacancy,
        available_receiving_slots=available_receiving_slots,
    )


def receiving_decision_trace(
    events: Iterable[Event],
    link: Link,
    tick: int,
    *,
    receiving_open: bool,
    receiving_capacity_carry_in: float = 0.0,
    already_accepted_count: int = 0,
    capacity_vehicles_per_tick: float | None = None,
) -> ReceivingDecisionTrace:
    """Return a parity receiving decision trace for one link and tick."""

    supply_view = parity_link_supply_view(
        events,
        link,
        tick,
        receiving_open=receiving_open,
        receiving_capacity_carry_in=receiving_capacity_carry_in,
        already_accepted_count=already_accepted_count,
        capacity_vehicles_per_tick=capacity_vehicles_per_tick,
    )
    return ReceivingDecisionTrace(
        link_id=link.link_id,
        tick=tick,
        supply_view=supply_view,
    )


def parity_supply_as_receiving_view(
    events: Iterable[Event],
    link: Link,
    tick: int,
    *,
    receiving_open: bool,
    receiving_capacity_carry_in: float = 0.0,
    already_accepted_count: int = 0,
    capacity_vehicles_per_tick: float | None = None,
) -> LinkReceivingView:
    """Return parity receiving supply in the existing public view shape."""

    event_tuple = tuple(events)
    supply_view = parity_link_supply_view(
        event_tuple,
        link,
        tick,
        receiving_open=receiving_open,
        receiving_capacity_carry_in=receiving_capacity_carry_in,
        already_accepted_count=already_accepted_count,
        capacity_vehicles_per_tick=capacity_vehicles_per_tick,
    )
    current_storage = link_storage(event_tuple, link.link_id, tick).storage
    return LinkReceivingView(
        link_id=link.link_id,
        tick=tick,
        receiving_open=receiving_open,
        receiving_capacity=supply_view.integer_receiving_capacity,
        already_accepted_count=supply_view.already_accepted_count,
        current_storage=current_storage,
        storage_capacity=link.declared_storage_capacity_packets,
        available_storage_space=supply_view.vacancy.available_physical_vacancy,
        available_receiving_slots=supply_view.available_receiving_slots,
    )


def _same_tick_link_entries(
    events: Iterable[Event],
    link_id: str,
    tick: int,
) -> int:
    return sum(
        event.event_type == EventType.LINK_ENTRY
        and event.entity_id == link_id
        and event.physical_tick == tick
        for event in events
    )


def _backward_wave_lag_ticks(link: Link) -> int:
    if link.length_m is None or link.backward_wave_speed_mps is None:
        raise ValueError(
            "parity receiving requires length_m and backward_wave_speed_mps "
            f"for {link.link_id}"
        )
    backward_wave_seconds = link.length_m / link.backward_wave_speed_mps
    return max(1, ceil(backward_wave_seconds / link.tick_duration_seconds))
