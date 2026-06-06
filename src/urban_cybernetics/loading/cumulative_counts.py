"""Event-derived cumulative link boundary count and storage views."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from urban_cybernetics.core import Event, EventType


@dataclass(frozen=True)
class CumulativeBoundaryCounts:
    """Packet-unit cumulative link entries and exits through one tick."""

    link_id: str
    tick: int
    entries: int
    exits: int


@dataclass(frozen=True)
class LinkStorageView:
    """Packet-unit link storage derived from cumulative boundary counts."""

    link_id: str
    tick: int
    storage: int


def cumulative_entries(events: Iterable[Event], link_id: str, tick: int) -> int:
    """Count LINK_ENTRY events for one link up to and including tick."""

    return sum(
        event.event_type == EventType.LINK_ENTRY
        and event.entity_id == link_id
        and event.physical_tick <= tick
        for event in events
    )


def cumulative_exits(events: Iterable[Event], link_id: str, tick: int) -> int:
    """Count LINK_EXIT events for one link up to and including tick."""

    return sum(
        event.event_type == EventType.LINK_EXIT
        and event.entity_id == link_id
        and event.physical_tick <= tick
        for event in events
    )


def cumulative_counts(
    events: Iterable[Event],
    link_id: str,
    tick: int,
) -> CumulativeBoundaryCounts:
    """Return cumulative entry and exit counts for one link and tick."""

    event_tuple = tuple(events)
    return CumulativeBoundaryCounts(
        link_id=link_id,
        tick=tick,
        entries=cumulative_entries(event_tuple, link_id, tick),
        exits=cumulative_exits(event_tuple, link_id, tick),
    )


def cumulative_count_series(
    events: Iterable[Event],
    link_id: str,
    max_tick: int,
) -> tuple[CumulativeBoundaryCounts, ...]:
    """Return cumulative boundary counts for ticks 0 through max_tick."""

    if max_tick < 0:
        return ()

    event_tuple = tuple(events)
    return tuple(
        CumulativeBoundaryCounts(
            link_id=link_id,
            tick=tick,
            entries=cumulative_entries(event_tuple, link_id, tick),
            exits=cumulative_exits(event_tuple, link_id, tick),
        )
        for tick in range(max_tick + 1)
    )


def link_storage(events: Iterable[Event], link_id: str, tick: int) -> LinkStorageView:
    """Return packet-unit storage derived from cumulative entries minus exits."""

    event_tuple = tuple(events)
    counts = cumulative_counts(event_tuple, link_id, tick)
    storage = counts.entries - counts.exits
    if storage < 0:
        raise ValueError(
            f"link storage is negative for {link_id} at tick {tick}: {storage}"
        )
    return LinkStorageView(link_id=link_id, tick=tick, storage=storage)


def link_storage_series(
    events: Iterable[Event],
    link_id: str,
    max_tick: int,
) -> tuple[LinkStorageView, ...]:
    """Return count-derived link storage for ticks 0 through max_tick."""

    if max_tick < 0:
        return ()

    event_tuple = tuple(events)
    return tuple(link_storage(event_tuple, link_id, tick) for tick in range(max_tick + 1))


def packet_ids_on_link_from_events(
    events: Iterable[Event],
    link_id: str,
    tick: int,
) -> tuple[str, ...]:
    """Return packet IDs physically on one link through an inclusive tick."""

    packet_ids: list[str] = []
    for event in events:
        if event.physical_tick > tick:
            continue
        if event.entity_id != link_id:
            continue
        if event.event_type == EventType.LINK_ENTRY:
            packet_ids.append(event.packet_id)
        elif event.event_type == EventType.LINK_EXIT:
            if event.packet_id not in packet_ids:
                raise ValueError(
                    f"packet_id {event.packet_id} exits {link_id} before entering"
                )
            packet_ids.remove(event.packet_id)
    return tuple(packet_ids)
