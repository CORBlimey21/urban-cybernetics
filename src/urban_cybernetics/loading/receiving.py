"""Event-derived LTM-style link receiving views."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from urban_cybernetics.core import Event, EventType, Link
from urban_cybernetics.loading.cumulative_counts import link_storage


@dataclass(frozen=True)
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
