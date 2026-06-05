"""Minimal node transfer policy abstractions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TransferContext:
    """Event-derived context for one requested node transfer attempt."""

    packet_id: str
    upstream_link_id: str
    downstream_link_id: str
    packet_ids_on_upstream_link: tuple[str, ...]
    queued_downstream_by_packet_id: Mapping[str, str]


class NodeTransferPolicy(Protocol):
    """Policy interface for deciding whether a transfer attempt may proceed."""

    def permits_transfer_attempt(self, context: TransferContext) -> bool:
        """Return whether the engine may attempt this transfer."""


class StrictFIFOJunctionPolicy:
    """Base policy that forbids bypassing packets ahead on the upstream link."""

    def permits_transfer_attempt(self, context: TransferContext) -> bool:
        try:
            packet_position = context.packet_ids_on_upstream_link.index(context.packet_id)
        except ValueError:
            return False

        for packet_id_ahead in context.packet_ids_on_upstream_link[:packet_position]:
            queued_downstream = context.queued_downstream_by_packet_id.get(packet_id_ahead)
            if queued_downstream is None:
                return False
            if queued_downstream != context.downstream_link_id:
                return False
        return True
