"""Minimal node transfer policy abstractions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TransferCandidate:
    """Immutable candidate for one physical transfer across a node boundary."""

    packet_id: str
    upstream_link_id: str
    downstream_link_id: str
    boundary_id: str
    eligibility_tick: int
    eligibility_sequence_number: int
    queued: bool = False


class NodeTransferPolicy(Protocol):
    """Policy interface for allocating candidate node transfers."""

    def choose_transfers(
        self,
        *,
        candidates: tuple[TransferCandidate, ...],
        receiving_slots_by_downstream_link: Mapping[str, int],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
    ) -> tuple[TransferCandidate, ...]:
        """Return immutable candidates the engine may execute this tick."""


class StrictFIFOJunctionPolicy:
    """Base policy that forbids bypassing packets ahead on an upstream link."""

    def choose_transfers(
        self,
        *,
        candidates: tuple[TransferCandidate, ...],
        receiving_slots_by_downstream_link: Mapping[str, int],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
    ) -> tuple[TransferCandidate, ...]:
        approved_candidates: list[TransferCandidate] = []
        approved_packet_ids: set[str] = set()
        blocked_upstream_link_ids: set[str] = set()
        remaining_slots = dict(receiving_slots_by_downstream_link)

        for candidate in sorted(candidates, key=self._candidate_sort_key):
            if candidate.upstream_link_id in blocked_upstream_link_ids:
                continue
            if not self._respects_upstream_fifo(
                candidate,
                approved_packet_ids,
                packet_ids_by_upstream_link,
                queued_downstream_by_packet_id,
            ):
                continue
            if remaining_slots.get(candidate.downstream_link_id, 0) <= 0:
                blocked_upstream_link_ids.add(candidate.upstream_link_id)
                continue

            approved_candidates.append(candidate)
            approved_packet_ids.add(candidate.packet_id)
            remaining_slots[candidate.downstream_link_id] -= 1

        return tuple(approved_candidates)

    @staticmethod
    def _candidate_sort_key(candidate: TransferCandidate) -> tuple[int, int, str]:
        return (
            candidate.eligibility_tick,
            candidate.eligibility_sequence_number,
            candidate.packet_id,
        )

    def _respects_upstream_fifo(
        self,
        candidate: TransferCandidate,
        approved_packet_ids: set[str],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
    ) -> bool:
        packet_ids_on_upstream_link = packet_ids_by_upstream_link.get(
            candidate.upstream_link_id,
            (),
        )
        try:
            packet_position = packet_ids_on_upstream_link.index(candidate.packet_id)
        except ValueError:
            return False

        for packet_id_ahead in packet_ids_on_upstream_link[:packet_position]:
            if packet_id_ahead in approved_packet_ids:
                continue
            queued_downstream = queued_downstream_by_packet_id.get(packet_id_ahead)
            if queued_downstream is not None:
                return False
            return False
        return True


class GlobalFIFOMergePolicy(StrictFIFOJunctionPolicy):
    """Global FIFO allocation policy for candidates competing for receiving slots."""
