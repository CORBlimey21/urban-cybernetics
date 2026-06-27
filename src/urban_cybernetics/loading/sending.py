"""Event-derived LTM-style link sending views."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import floor

from urban_cybernetics.core import Event, EventType, Link, Packet
from urban_cybernetics.loading.cumulative_counts import (
    ENTRY_BOUNDARY,
    PacketBoundaryOrdinal,
    cumulative_entries,
    cumulative_exits,
    packet_boundary_ordinals,
)


@dataclass(frozen=True, slots=True)
class LinkSendingView:
    """Packets a link can offer for downstream transfer at one tick."""

    link_id: str
    tick: int
    eligible_packet_ids: tuple[str, ...]
    sending_capacity: int
    sendable_packet_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BoundedIntegerCapacityCarry:
    """Bounded integer sending budget derived from a fractional capacity rate."""

    link_id: str
    capacity_vehicles_per_tick: float
    carry_in: float
    integer_capacity: int
    carry_out: float


@dataclass(frozen=True, slots=True)
class ParityLinkSendingTrace:
    """M3 parity sending trace derived from counts and packet ordinals."""

    link_id: str
    tick: int
    free_flow_lag_ticks: int
    lagged_entry_tick: int
    lagged_entry_count: int
    current_exit_count: int
    ltm_sending_demand: int
    capacity_vehicles_per_tick: float
    capacity_carry_in: float
    integer_capacity: int
    capacity_carry_out: float
    already_consumed_count: int
    available_sending_slots: int
    eligible_ordinals: tuple[PacketBoundaryOrdinal, ...]
    sendable_ordinals: tuple[PacketBoundaryOrdinal, ...]

    @property
    def eligible_packet_ids(self) -> tuple[str, ...]:
        """Packet IDs eligible by lagged cumulative entry ordinal."""

        return tuple(ordinal.packet_id for ordinal in self.eligible_ordinals)

    @property
    def sendable_packet_ids(self) -> tuple[str, ...]:
        """Packet IDs selected for discharge by parity sending semantics."""

        return tuple(ordinal.packet_id for ordinal in self.sendable_ordinals)

    def as_legacy_view(self) -> LinkSendingView:
        """Return the existing public sending-view shape."""

        return LinkSendingView(
            link_id=self.link_id,
            tick=self.tick,
            eligible_packet_ids=self.eligible_packet_ids,
            sending_capacity=self.integer_capacity,
            sendable_packet_ids=self.sendable_packet_ids,
        )


def link_sending_view(
    events: Iterable[Event],
    link: Link,
    tick: int,
    excluded_packet_ids: Iterable[str] = (),
) -> LinkSendingView:
    """Return event-derived sending supply for one link and tick."""

    sending_capacity = link.declared_sending_capacity_per_tick
    if sending_capacity < 0:
        raise ValueError(
            f"declared sending capacity cannot be negative for {link.link_id}: "
            f"{sending_capacity}"
        )

    excluded_packet_id_set = set(excluded_packet_ids)
    link_entry_metadata = _current_link_entry_metadata(events, link.link_id, tick)
    eligible_packet_metadata = sorted(
        (
            (packet_id, entry_tick, sequence_number)
            for packet_id, (entry_tick, sequence_number) in link_entry_metadata.items()
            if packet_id not in excluded_packet_id_set
            and tick - entry_tick >= link.free_flow_ticks
        ),
        key=lambda item: (item[1], item[2], item[0]),
    )
    eligible_packet_ids = tuple(
        packet_id for packet_id, _, _ in eligible_packet_metadata
    )
    return LinkSendingView(
        link_id=link.link_id,
        tick=tick,
        eligible_packet_ids=eligible_packet_ids,
        sending_capacity=sending_capacity,
        sendable_packet_ids=eligible_packet_ids[:sending_capacity],
    )


def bounded_integer_capacity_carry(
    *,
    link_id: str,
    capacity_vehicles_per_tick: float,
    carry_in: float,
) -> BoundedIntegerCapacityCarry:
    """Return the integer sending budget and bounded carry for one tick."""

    if capacity_vehicles_per_tick < 0:
        raise ValueError(
            f"capacity_vehicles_per_tick cannot be negative for {link_id}: "
            f"{capacity_vehicles_per_tick}"
        )
    if carry_in < 0 or carry_in >= 1:
        raise ValueError(f"carry_in must be in [0, 1) for {link_id}: {carry_in}")
    available_capacity = carry_in + capacity_vehicles_per_tick
    integer_capacity = floor(available_capacity)
    carry_out = available_capacity - integer_capacity
    if carry_out >= 1:
        raise ValueError(f"carry_out is not bounded for {link_id}: {carry_out}")
    return BoundedIntegerCapacityCarry(
        link_id=link_id,
        capacity_vehicles_per_tick=capacity_vehicles_per_tick,
        carry_in=carry_in,
        integer_capacity=integer_capacity,
        carry_out=carry_out,
    )


def parity_link_sending_trace(
    events: Iterable[Event],
    packets: Mapping[str, Packet],
    link: Link,
    tick: int,
    *,
    capacity_carry_in: float = 0.0,
    already_consumed_count: int = 0,
    excluded_packet_ids: Iterable[str] = (),
    capacity_vehicles_per_tick: float | None = None,
) -> ParityLinkSendingTrace:
    """Return count-derived parity sending demand and FIFO packet selection."""

    if already_consumed_count < 0:
        raise ValueError("already_consumed_count cannot be negative")
    capacity_rate = (
        float(link.declared_sending_capacity_per_tick)
        if capacity_vehicles_per_tick is None
        else capacity_vehicles_per_tick
    )
    capacity = bounded_integer_capacity_carry(
        link_id=link.link_id,
        capacity_vehicles_per_tick=capacity_rate,
        carry_in=capacity_carry_in,
    )
    event_tuple = tuple(events)
    lagged_entry_tick = tick - link.free_flow_ticks
    lagged_entry_count = (
        0
        if lagged_entry_tick < 0
        else cumulative_entries(event_tuple, link.link_id, lagged_entry_tick)
    )
    current_exit_count = cumulative_exits(event_tuple, link.link_id, tick)
    ltm_sending_demand = max(lagged_entry_count - current_exit_count, 0)
    available_sending_slots = max(
        min(capacity.integer_capacity, ltm_sending_demand) - already_consumed_count,
        0,
    )

    excluded_packet_id_set = set(excluded_packet_ids)
    current_entry_metadata = _current_link_entry_metadata(event_tuple, link.link_id, tick)
    current_entry_sequence_by_packet_id = {
        packet_id: sequence_number
        for packet_id, (_, sequence_number) in current_entry_metadata.items()
    }
    eligible_ordinals = tuple(
        ordinal
        for ordinal in packet_boundary_ordinals(
            event_tuple,
            packets=packets,
            link_ids=(link.link_id,),
            max_tick=tick,
        )
        if ordinal.boundary_type == ENTRY_BOUNDARY
        and ordinal.aggregate_ordinal <= lagged_entry_count
        and ordinal.packet_id not in excluded_packet_id_set
        and current_entry_sequence_by_packet_id.get(ordinal.packet_id)
        == ordinal.sequence_number
    )
    return ParityLinkSendingTrace(
        link_id=link.link_id,
        tick=tick,
        free_flow_lag_ticks=link.free_flow_ticks,
        lagged_entry_tick=lagged_entry_tick,
        lagged_entry_count=lagged_entry_count,
        current_exit_count=current_exit_count,
        ltm_sending_demand=ltm_sending_demand,
        capacity_vehicles_per_tick=capacity.capacity_vehicles_per_tick,
        capacity_carry_in=capacity.carry_in,
        integer_capacity=capacity.integer_capacity,
        capacity_carry_out=capacity.carry_out,
        already_consumed_count=already_consumed_count,
        available_sending_slots=available_sending_slots,
        eligible_ordinals=eligible_ordinals,
        sendable_ordinals=eligible_ordinals[:available_sending_slots],
    )


def _current_link_entry_metadata(
    events: Iterable[Event],
    link_id: str,
    tick: int,
) -> dict[str, tuple[int, int]]:
    packet_entry_metadata: dict[str, tuple[int, int]] = {}
    for event in events:
        if event.physical_tick > tick:
            continue
        if event.entity_id != link_id:
            continue
        if event.event_type == EventType.LINK_ENTRY:
            packet_entry_metadata[event.packet_id] = (
                event.physical_tick,
                event.sequence_number,
            )
        elif event.event_type == EventType.LINK_EXIT:
            if event.packet_id not in packet_entry_metadata:
                raise ValueError(
                    f"packet_id {event.packet_id} exits {link_id} before entering"
                )
            del packet_entry_metadata[event.packet_id]
    return packet_entry_metadata
