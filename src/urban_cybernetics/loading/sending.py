"""Event-derived LTM-style link sending views."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from urban_cybernetics.core import Event, EventType, Link


@dataclass(frozen=True, slots=True)
class LinkSendingView:
    """Packets a link can offer for downstream transfer at one tick."""

    link_id: str
    tick: int
    eligible_packet_ids: tuple[str, ...]
    sending_capacity: int
    sendable_packet_ids: tuple[str, ...]


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
