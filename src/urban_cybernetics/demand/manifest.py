"""Immutable pre-packet demand declarations and deterministic hashing."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class DepartureSchedule(Protocol):
    """A deterministic schedule that can expand quantity into departure ticks."""

    def expand_departure_ticks(self, quantity_packets: int) -> tuple[int, ...]:
        """Return one scheduled departure tick per unit packet."""

    def hash_payload(self) -> dict[str, Any]:
        """Return deterministic schedule content for manifest hashing."""


@dataclass(frozen=True)
class FixedDepartureSchedule:
    """All declared packets become due at one tick."""

    departure_tick: int

    def __post_init__(self) -> None:
        if self.departure_tick < 0:
            raise ValueError("departure_tick cannot be negative")

    def expand_departure_ticks(self, quantity_packets: int) -> tuple[int, ...]:
        _validate_quantity(quantity_packets)
        return (self.departure_tick,) * quantity_packets

    def hash_payload(self) -> dict[str, Any]:
        return {
            "schedule_type": "fixed_tick",
            "departure_tick": self.departure_tick,
        }


@dataclass(frozen=True)
class UniformWindowDepartureSchedule:
    """Deterministically spread departures over an inclusive tick window."""

    start_tick: int
    end_tick: int

    def __post_init__(self) -> None:
        if self.start_tick < 0:
            raise ValueError("start_tick cannot be negative")
        if self.end_tick < self.start_tick:
            raise ValueError("end_tick must be greater than or equal to start_tick")

    def expand_departure_ticks(self, quantity_packets: int) -> tuple[int, ...]:
        _validate_quantity(quantity_packets)
        tick_count = self.end_tick - self.start_tick + 1
        base_count = quantity_packets // tick_count
        remainder = quantity_packets % tick_count
        ticks: list[int] = []
        for offset in range(tick_count):
            departures_at_tick = base_count + (1 if offset < remainder else 0)
            ticks.extend([self.start_tick + offset] * departures_at_tick)
        return tuple(ticks)

    def hash_payload(self) -> dict[str, Any]:
        return {
            "schedule_type": "uniform_window",
            "start_tick": self.start_tick,
            "end_tick": self.end_tick,
        }


@dataclass(frozen=True)
class GlobalUniformDepartureSchedule:
    """Spread all manifest departures over one inclusive global tick window."""

    start_tick: int
    end_tick: int

    def __post_init__(self) -> None:
        if self.start_tick < 0:
            raise ValueError("start_tick cannot be negative")
        if self.end_tick < self.start_tick:
            raise ValueError("end_tick must be greater than or equal to start_tick")

    def expand_departure_ticks(self, quantity_packets: int) -> tuple[int, ...]:
        _validate_quantity(quantity_packets)
        raise ValueError(
            "GlobalUniformDepartureSchedule requires manifest-level expansion"
        )

    def expand_manifest_departure_ticks(
        self,
        declaration_quantities: tuple[tuple[str, int], ...],
    ) -> dict[str, tuple[int, ...]]:
        """Return departure ticks by demand_id using the full manifest quantity."""

        for demand_id, quantity_packets in declaration_quantities:
            if not demand_id:
                raise ValueError("demand_id is required")
            _validate_quantity(quantity_packets)

        tick_count = self.end_tick - self.start_tick + 1
        total_quantity = sum(quantity for _, quantity in declaration_quantities)
        ticks = self._global_ticks(total_quantity, tick_count)
        ticks_by_demand_id: dict[str, list[int]] = {
            demand_id: [] for demand_id, _ in declaration_quantities
        }
        tick_index = 0
        for demand_id, quantity_packets in declaration_quantities:
            for _ in range(quantity_packets):
                ticks_by_demand_id[demand_id].append(ticks[tick_index])
                tick_index += 1
        return {
            demand_id: tuple(departure_ticks)
            for demand_id, departure_ticks in ticks_by_demand_id.items()
        }

    def hash_payload(self) -> dict[str, Any]:
        return {
            "schedule_type": "global_uniform_window",
            "start_tick": self.start_tick,
            "end_tick": self.end_tick,
        }

    def _global_ticks(self, total_quantity: int, tick_count: int) -> tuple[int, ...]:
        base_count = total_quantity // tick_count
        remainder = total_quantity % tick_count
        ticks: list[int] = []
        for offset in range(tick_count):
            departures_at_tick = base_count + (1 if offset < remainder else 0)
            ticks.extend([self.start_tick + offset] * departures_at_tick)
        return tuple(ticks)


@dataclass(frozen=True)
class DemandManifestSourceMetadata:
    """Immutable provenance and interpretation metadata for a demand manifest."""

    source_name: str
    source_format: str
    source_file_path: str | None = None
    source_file_sha256: str | None = None
    source_metadata_items: tuple[tuple[str, str], ...] = ()
    interpretation_assumptions: tuple[str, ...] = ()
    scaling_assumptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_metadata_items",
            tuple(sorted(self.source_metadata_items)),
        )

    @classmethod
    def from_path(
        cls,
        *,
        source_name: str,
        source_format: str,
        source_file_path: Path,
        source_metadata_items: tuple[tuple[str, str], ...] = (),
        interpretation_assumptions: tuple[str, ...] = (),
        scaling_assumptions: tuple[str, ...] = (),
    ) -> "DemandManifestSourceMetadata":
        source_bytes = source_file_path.read_bytes()
        return cls(
            source_name=source_name,
            source_format=source_format,
            source_file_path=str(source_file_path),
            source_file_sha256=hashlib.sha256(source_bytes).hexdigest(),
            source_metadata_items=source_metadata_items,
            interpretation_assumptions=interpretation_assumptions,
            scaling_assumptions=scaling_assumptions,
        )

    def hash_payload(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_format": self.source_format,
            "source_file_sha256": self.source_file_sha256,
            "source_metadata_items": list(self.source_metadata_items),
            "interpretation_assumptions": list(self.interpretation_assumptions),
            "scaling_assumptions": list(self.scaling_assumptions),
        }


@dataclass(frozen=True)
class ODDemandDeclaration:
    """An immutable OD demand record that exists before any packet exists."""

    demand_id: str
    origin_node_id: str
    destination_node_id: str
    quantity_packets: int
    departure_schedule: DepartureSchedule
    cohort_id: str | None = None
    authority_id: str | None = None
    source_origin_zone_id: str | None = None
    source_destination_zone_id: str | None = None
    source_quantity_value: float | None = None
    source_metadata_items: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.demand_id:
            raise ValueError("demand_id is required")
        if not self.origin_node_id:
            raise ValueError("origin_node_id is required")
        if not self.destination_node_id:
            raise ValueError("destination_node_id is required")
        if self.origin_node_id == self.destination_node_id:
            raise ValueError("origin_node_id and destination_node_id must differ")
        _validate_quantity(self.quantity_packets)
        if not hasattr(self.departure_schedule, "expand_departure_ticks"):
            raise TypeError("departure_schedule must expand departure ticks")
        object.__setattr__(
            self,
            "source_metadata_items",
            tuple(sorted(self.source_metadata_items)),
        )

    def expand_departure_ticks(self) -> tuple[int, ...]:
        """Return one scheduled departure tick per declared unit packet."""

        return self.departure_schedule.expand_departure_ticks(self.quantity_packets)

    def hash_payload(self) -> dict[str, Any]:
        return {
            "demand_id": self.demand_id,
            "origin_node_id": self.origin_node_id,
            "destination_node_id": self.destination_node_id,
            "quantity_packets": self.quantity_packets,
            "departure_schedule": self.departure_schedule.hash_payload(),
            "cohort_id": self.cohort_id,
            "authority_id": self.authority_id,
            "source_origin_zone_id": self.source_origin_zone_id,
            "source_destination_zone_id": self.source_destination_zone_id,
            "source_quantity_value": self.source_quantity_value,
            "source_metadata_items": list(self.source_metadata_items),
        }


@dataclass(frozen=True)
class DemandManifest:
    """A deterministic, hashable collection of pre-packet demand declarations."""

    manifest_id: str
    topology_id: str
    topology_hash: str
    declarations: tuple[ODDemandDeclaration, ...]
    source_metadata: DemandManifestSourceMetadata | None = None
    manifest_hash: str = ""

    def __post_init__(self) -> None:
        if not self.manifest_id:
            raise ValueError("manifest_id is required")
        if not self.topology_id:
            raise ValueError("topology_id is required")
        if not self.topology_hash:
            raise ValueError("topology_hash is required")
        demand_ids = [declaration.demand_id for declaration in self.declarations]
        if len(demand_ids) != len(set(demand_ids)):
            raise ValueError("demand_id values must be unique within a manifest")
        object.__setattr__(self, "manifest_hash", self.compute_hash())

    @property
    def total_declared_quantity_packets(self) -> int:
        """Return total pre-packet unit demand declared by the manifest."""

        return sum(
            declaration.quantity_packets for declaration in self.declarations
        )

    def compute_hash(self) -> str:
        """Return a stable hash over meaningful demand content."""

        serialised = json.dumps(
            self._hash_payload(),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialised.encode("utf-8")).hexdigest()

    def validate_for_topology_nodes(self, node_ids: set[str]) -> bool:
        """Validate that all OD endpoints reference canonical topology nodes."""

        for declaration in self.declarations:
            if declaration.origin_node_id not in node_ids:
                raise KeyError(
                    f"demand {declaration.demand_id} references unknown origin "
                    f"{declaration.origin_node_id}"
                )
            if declaration.destination_node_id not in node_ids:
                raise KeyError(
                    f"demand {declaration.demand_id} references unknown destination "
                    f"{declaration.destination_node_id}"
                )
        return True

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "topology_id": self.topology_id,
            "topology_hash": self.topology_hash,
            "source_metadata": (
                self.source_metadata.hash_payload()
                if self.source_metadata is not None
                else None
            ),
            "declarations": [
                declaration.hash_payload()
                for declaration in sorted(
                    self.declarations,
                    key=lambda item: item.demand_id,
                )
            ],
        }


def _validate_quantity(quantity_packets: int) -> None:
    if not isinstance(quantity_packets, int):
        raise TypeError("quantity_packets must be an int")
    if quantity_packets <= 0:
        raise ValueError("quantity_packets must be positive")
