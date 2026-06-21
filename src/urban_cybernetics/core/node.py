"""Immutable node connectivity records for synthetic junction tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Node:
    """Static node connectivity between directed links."""

    node_id: str
    incoming_link_ids: tuple[str, ...]
    outgoing_link_ids: tuple[str, ...]
