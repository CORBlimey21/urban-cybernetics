"""Deterministic read-only replay projection over canonical event evidence."""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Iterable, Sequence

from urban_cybernetics.core import Event, EventType

from .contract import (
    EvidenceDescriptor,
    PacketReplayStatus,
    SemanticStatus,
    VLinkReplayState,
    VPacket,
    VPacketReplayState,
    VQueueReplayState,
    VReplayState,
    VRunCounts,
)


REPLAY_DESCRIPTOR = EvidenceDescriptor(
    semantic_status=SemanticStatus.EVENT_DERIVED,
    source="deterministic Python fold over canonical event sequence",
    units="packets",
    time_basis="inclusive integer physical tick; state after all same-tick events",
    counting_basis="unit packet identity",
)


class ReplayIntegrityError(ValueError):
    """Raised when canonical evidence cannot produce a valid replay state."""


def build_replay_states(
    *,
    events: Iterable[Event],
    packets: Sequence[VPacket],
    link_ids: Iterable[str],
    start_tick: int,
    end_tick: int,
) -> tuple[VReplayState, ...]:
    """Fold canonical events once and snapshot deterministic end-of-tick state."""

    if start_tick < 0 or end_tick < start_tick:
        raise ValueError("invalid replay tick range")
    event_tuple = tuple(events)
    _validate_event_order(event_tuple)
    packet_ids = tuple(packet.packet_id for packet in packets)
    if len(packet_ids) != len(set(packet_ids)):
        raise ReplayIntegrityError("packet metadata IDs must be unique")
    known_packet_ids = set(packet_ids)
    ordered_link_ids = tuple(sorted(link_ids))
    known_link_ids = set(ordered_link_ids)

    status = {
        packet_id: PacketReplayStatus.NOT_YET_OBSERVED for packet_id in packet_ids
    }
    current_link: dict[str, str | None] = {packet_id: None for packet_id in packet_ids}
    queue_boundary: dict[str, str | None] = {
        packet_id: None for packet_id in packet_ids
    }
    realised_path: dict[str, list[str]] = {packet_id: [] for packet_id in packet_ids}
    last_sequence: dict[str, int | None] = {packet_id: None for packet_id in packet_ids}
    packet_ids_by_link = {link_id: [] for link_id in ordered_link_ids}
    queues: dict[str, deque[str]] = {}
    cumulative_entries = Counter({link_id: 0 for link_id in ordered_link_ids})
    cumulative_exits = Counter({link_id: 0 for link_id in ordered_link_ids})

    event_index = 0
    states: list[VReplayState] = []
    for tick in range(start_tick, end_tick + 1):
        while (
            event_index < len(event_tuple)
            and event_tuple[event_index].physical_tick <= tick
        ):
            event = event_tuple[event_index]
            if event.physical_tick < start_tick:
                raise ReplayIntegrityError("event precedes declared replay start_tick")
            if event.packet_id not in known_packet_ids:
                raise ReplayIntegrityError(
                    f"event references unknown packet {event.packet_id}"
                )
            _apply_event(
                event,
                known_link_ids=known_link_ids,
                status=status,
                current_link=current_link,
                queue_boundary=queue_boundary,
                realised_path=realised_path,
                packet_ids_by_link=packet_ids_by_link,
                queues=queues,
                cumulative_entries=cumulative_entries,
                cumulative_exits=cumulative_exits,
            )
            last_sequence[event.packet_id] = event.sequence_number
            event_index += 1

        states.append(
            _snapshot(
                tick=tick,
                applied_through_sequence=(
                    event_tuple[event_index - 1].sequence_number
                    if event_index
                    else None
                ),
                packet_ids=packet_ids,
                ordered_link_ids=ordered_link_ids,
                status=status,
                current_link=current_link,
                queue_boundary=queue_boundary,
                realised_path=realised_path,
                last_sequence=last_sequence,
                packet_ids_by_link=packet_ids_by_link,
                queues=queues,
                cumulative_entries=cumulative_entries,
                cumulative_exits=cumulative_exits,
            )
        )

    if event_index != len(event_tuple):
        raise ReplayIntegrityError("event occurs after declared replay end_tick")
    return tuple(states)


def resume_replay_from_checkpoint(
    *,
    checkpoint: VReplayState,
    events: Iterable[Event],
    packets: Sequence[VPacket],
    link_ids: Iterable[str],
    target_tick: int,
) -> VReplayState:
    """Reconstruct exactly from a sealed state plus subsequent canonical events."""

    if target_tick < checkpoint.tick:
        raise ValueError("target_tick precedes checkpoint")
    event_tuple = tuple(events)
    expected_sequence = (
        0
        if checkpoint.applied_through_sequence is None
        else checkpoint.applied_through_sequence + 1
    )
    previous_tick = checkpoint.tick
    for offset, event in enumerate(event_tuple):
        if event.sequence_number != expected_sequence + offset:
            raise ReplayIntegrityError("checkpoint continuation is not contiguous")
        if event.physical_tick < previous_tick:
            raise ReplayIntegrityError("checkpoint continuation tick moved backwards")
        if event.physical_tick > target_tick:
            raise ReplayIntegrityError("continuation event exceeds target_tick")
        previous_tick = event.physical_tick

    packet_ids = tuple(packet.packet_id for packet in packets)
    checkpoint_packet_ids = tuple(packet.packet_id for packet in checkpoint.packets)
    if not set(checkpoint_packet_ids).issubset(packet_ids):
        raise ReplayIntegrityError("checkpoint references absent packet metadata")
    ordered_link_ids = tuple(sorted(link_ids))
    if ordered_link_ids != tuple(link.link_id for link in checkpoint.links):
        raise ReplayIntegrityError("checkpoint topology links do not match")

    status = {packet.packet_id: packet.status for packet in checkpoint.packets}
    current_link = {
        packet.packet_id: packet.current_link_id for packet in checkpoint.packets
    }
    queue_boundary = {
        packet.packet_id: packet.queue_boundary_id for packet in checkpoint.packets
    }
    realised_path = {
        packet.packet_id: list(packet.realised_path) for packet in checkpoint.packets
    }
    last_sequence = {
        packet.packet_id: packet.last_event_sequence for packet in checkpoint.packets
    }
    for packet_id in set(packet_ids) - set(checkpoint_packet_ids):
        status[packet_id] = PacketReplayStatus.NOT_YET_OBSERVED
        current_link[packet_id] = None
        queue_boundary[packet_id] = None
        realised_path[packet_id] = []
        last_sequence[packet_id] = None
    packet_ids_by_link = {
        link.link_id: list(link.packet_ids) for link in checkpoint.links
    }
    queues = {
        queue.boundary_id: deque(queue.packet_ids) for queue in checkpoint.queues
    }
    cumulative_entries = Counter(
        {link.link_id: link.cumulative_entries for link in checkpoint.links}
    )
    cumulative_exits = Counter(
        {link.link_id: link.cumulative_exits for link in checkpoint.links}
    )
    known_link_ids = set(ordered_link_ids)
    known_packet_ids = set(packet_ids)
    applied_sequence = checkpoint.applied_through_sequence
    for event in event_tuple:
        if event.packet_id not in known_packet_ids:
            raise ReplayIntegrityError(f"event references unknown packet {event.packet_id}")
        _apply_event(
            event,
            known_link_ids=known_link_ids,
            status=status,
            current_link=current_link,
            queue_boundary=queue_boundary,
            realised_path=realised_path,
            packet_ids_by_link=packet_ids_by_link,
            queues=queues,
            cumulative_entries=cumulative_entries,
            cumulative_exits=cumulative_exits,
        )
        last_sequence[event.packet_id] = event.sequence_number
        applied_sequence = event.sequence_number
    return _snapshot(
        tick=target_tick,
        applied_through_sequence=applied_sequence,
        packet_ids=packet_ids,
        ordered_link_ids=ordered_link_ids,
        status=status,
        current_link=current_link,
        queue_boundary=queue_boundary,
        realised_path=realised_path,
        last_sequence=last_sequence,
        packet_ids_by_link=packet_ids_by_link,
        queues=queues,
        cumulative_entries=cumulative_entries,
        cumulative_exits=cumulative_exits,
    )


def _validate_event_order(events: tuple[Event, ...]) -> None:
    previous_tick = -1
    for expected_sequence, event in enumerate(events):
        if event.sequence_number != expected_sequence:
            raise ReplayIntegrityError(
                "events must be in contiguous canonical sequence-number order"
            )
        if event.physical_tick < previous_tick:
            raise ReplayIntegrityError("event physical ticks must not move backwards")
        previous_tick = event.physical_tick


def _apply_event(
    event: Event,
    *,
    known_link_ids: set[str],
    status: dict[str, PacketReplayStatus],
    current_link: dict[str, str | None],
    queue_boundary: dict[str, str | None],
    realised_path: dict[str, list[str]],
    packet_ids_by_link: dict[str, list[str]],
    queues: dict[str, deque[str]],
    cumulative_entries: Counter[str],
    cumulative_exits: Counter[str],
) -> None:
    packet_id = event.packet_id
    if event.event_type == EventType.INSTANTIATED:
        if status[packet_id] != PacketReplayStatus.NOT_YET_OBSERVED:
            raise ReplayIntegrityError(f"packet {packet_id} instantiated more than once")
        status[packet_id] = PacketReplayStatus.IN_TRANSIT
        return

    if status[packet_id] == PacketReplayStatus.NOT_YET_OBSERVED:
        raise ReplayIntegrityError(f"packet {packet_id} has event before instantiation")
    if status[packet_id] in {
        PacketReplayStatus.COMPLETED,
        PacketReplayStatus.CANCELLED,
    }:
        raise ReplayIntegrityError(f"packet {packet_id} has event after terminal state")

    if event.event_type in {EventType.LINK_ENTRY, EventType.LINK_EXIT}:
        if event.entity_id not in known_link_ids:
            raise ReplayIntegrityError(
                f"event references unknown topology link {event.entity_id}"
            )
    if event.event_type == EventType.LINK_ENTRY:
        if current_link[packet_id] is not None:
            raise ReplayIntegrityError(f"packet {packet_id} enters while already on a link")
        current_link[packet_id] = event.entity_id
        packet_ids_by_link[event.entity_id].append(packet_id)
        realised_path[packet_id].append(event.entity_id)
        cumulative_entries[event.entity_id] += 1
        status[packet_id] = PacketReplayStatus.IN_TRANSIT
    elif event.event_type == EventType.LINK_EXIT:
        if current_link[packet_id] != event.entity_id:
            raise ReplayIntegrityError(
                f"packet {packet_id} exits {event.entity_id} without matching membership"
            )
        packet_ids_by_link[event.entity_id].remove(packet_id)
        current_link[packet_id] = None
        cumulative_exits[event.entity_id] += 1
    elif event.event_type == EventType.QUEUE_ENTRY:
        if queue_boundary[packet_id] is not None:
            raise ReplayIntegrityError(f"packet {packet_id} enters a second queue")
        boundary_queue = queues.setdefault(event.entity_id, deque())
        boundary_queue.append(packet_id)
        queue_boundary[packet_id] = event.entity_id
        status[packet_id] = PacketReplayStatus.QUEUED
    elif event.event_type == EventType.QUEUE_EXIT:
        boundary_queue = queues.setdefault(event.entity_id, deque())
        if not boundary_queue or boundary_queue[0] != packet_id:
            raise ReplayIntegrityError(
                f"packet {packet_id} exits queue out of canonical FIFO order"
            )
        boundary_queue.popleft()
        queue_boundary[packet_id] = None
        status[packet_id] = PacketReplayStatus.IN_TRANSIT
    elif event.event_type == EventType.COMPLETED:
        if current_link[packet_id] is not None:
            raise ReplayIntegrityError(
                f"packet {packet_id} completes before its final link exit"
            )
        status[packet_id] = PacketReplayStatus.COMPLETED
    elif event.event_type == EventType.CANCELLED:
        status[packet_id] = PacketReplayStatus.CANCELLED


def _snapshot(
    *,
    tick: int,
    applied_through_sequence: int | None,
    packet_ids: tuple[str, ...],
    ordered_link_ids: tuple[str, ...],
    status: dict[str, PacketReplayStatus],
    current_link: dict[str, str | None],
    queue_boundary: dict[str, str | None],
    realised_path: dict[str, list[str]],
    last_sequence: dict[str, int | None],
    packet_ids_by_link: dict[str, list[str]],
    queues: dict[str, deque[str]],
    cumulative_entries: Counter[str],
    cumulative_exits: Counter[str],
) -> VReplayState:
    queued_by_link: dict[str, list[str]] = {link_id: [] for link_id in ordered_link_ids}
    for packet_id, boundary_id in queue_boundary.items():
        if boundary_id is None:
            continue
        link_id = current_link[packet_id]
        if link_id is not None:
            queued_by_link[link_id].append(packet_id)
    counts = Counter(status.values())
    return VReplayState(
        descriptor=REPLAY_DESCRIPTOR,
        tick=tick,
        applied_through_sequence=applied_through_sequence,
        packets=tuple(
            VPacketReplayState(
                packet_id=packet_id,
                status=status[packet_id],
                current_link_id=current_link[packet_id],
                queue_boundary_id=queue_boundary[packet_id],
                realised_path=tuple(realised_path[packet_id]),
                last_event_sequence=last_sequence[packet_id],
            )
            for packet_id in sorted(packet_ids)
        ),
        links=tuple(
            VLinkReplayState(
                link_id=link_id,
                packet_ids=tuple(packet_ids_by_link[link_id]),
                queued_packet_ids=tuple(queued_by_link[link_id]),
                occupancy_packets=len(packet_ids_by_link[link_id]),
                cumulative_entries=cumulative_entries[link_id],
                cumulative_exits=cumulative_exits[link_id],
            )
            for link_id in ordered_link_ids
        ),
        queues=tuple(
            VQueueReplayState(boundary_id=boundary_id, packet_ids=tuple(queue))
            for boundary_id, queue in sorted(queues.items())
            if queue
        ),
        counts=VRunCounts(
            not_yet_observed=counts[PacketReplayStatus.NOT_YET_OBSERVED],
            in_transit=counts[PacketReplayStatus.IN_TRANSIT],
            queued=counts[PacketReplayStatus.QUEUED],
            completed=counts[PacketReplayStatus.COMPLETED],
            cancelled=counts[PacketReplayStatus.CANCELLED],
        ),
    )
