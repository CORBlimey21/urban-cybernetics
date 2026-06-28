"""Canonical immutable topology records and deterministic hashing."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from urban_cybernetics.core import (
    DEFAULT_FD_RELATIVE_TOLERANCE,
    DEFAULT_MINIMUM_TIMESTEP_LAG_TICKS,
    JunctionSpec,
    Link,
    MovementSpec,
    Node,
    ResolvedPhysicalLinkParameters,
)


LEGACY_LOADING_STORAGE_CAPACITY_PACKETS = 1_000_000


@dataclass(frozen=True, slots=True)
class TopologySourceMetadata:
    """Immutable provenance for a topology source artifact."""

    source_name: str
    source_format: str
    source_file_path: str
    source_file_sha256: str
    source_metadata_items: tuple[tuple[str, str], ...] = ()

    @classmethod
    def from_path(
        cls,
        *,
        source_name: str,
        source_format: str,
        source_file_path: Path,
        source_metadata_items: tuple[tuple[str, str], ...] = (),
    ) -> "TopologySourceMetadata":
        source_bytes = source_file_path.read_bytes()
        return cls(
            source_name=source_name,
            source_format=source_format,
            source_file_path=str(source_file_path),
            source_file_sha256=hashlib.sha256(source_bytes).hexdigest(),
            source_metadata_items=tuple(sorted(source_metadata_items)),
        )

    def hash_payload(self) -> dict[str, Any]:
        """Return source fields that affect scientific topology identity."""

        return {
            "source_name": self.source_name,
            "source_format": self.source_format,
            "source_metadata_items": list(self.source_metadata_items),
        }


@dataclass(frozen=True, slots=True)
class CanonicalNode:
    """Immutable canonical topology node."""

    node_id: str
    source_node_id: str
    incoming_link_ids: tuple[str, ...] = ()
    outgoing_link_ids: tuple[str, ...] = ()
    movement_specs: tuple[MovementSpec, ...] = ()
    lane_group_ids: tuple[str, ...] = ()
    movement_lane_group_mappings: tuple[tuple[str, tuple[str, ...]], ...] = ()
    lane_group_capacities: tuple[tuple[str, int], ...] = ()
    conflict_resource_ids: tuple[str, ...] = ()
    conflict_resource_capacities: tuple[tuple[str, int], ...] = ()
    governance_refs: tuple[str, ...] = ()
    fifo_policy: str = "strict"

    def junction_spec(self) -> JunctionSpec:
        """Return the immutable movement specification for this topology node."""

        return JunctionSpec(
            node_id=self.node_id,
            incoming_link_ids=self.incoming_link_ids,
            outgoing_link_ids=self.outgoing_link_ids,
            movement_specs=self.movement_specs,
            lane_group_ids=self.lane_group_ids,
            movement_lane_group_mappings=self.movement_lane_group_mappings,
            lane_group_capacities=self.lane_group_capacities,
            conflict_resource_ids=self.conflict_resource_ids,
            conflict_resource_capacities=self.conflict_resource_capacities,
            governance_refs=self.governance_refs,
            provenance=(("source_node_id", self.source_node_id),),
            fifo_policy=self.fifo_policy,
        )


@dataclass(frozen=True, slots=True)
class CanonicalTopologyLink:
    """Immutable canonical directed link with static physical metadata."""

    link_id: str
    tail_node_id: str
    head_node_id: str
    source_link_id: str
    source_tail_node_id: str
    source_head_node_id: str
    length_m: float | None = None
    lane_count: int | None = None
    free_flow_speed_mps: float | None = None
    capacity_veh_per_hour_per_lane: float | None = None
    jam_density_veh_per_km_per_lane: float | None = None
    backward_wave_speed_mps: float | None = None
    source_length_value: float | None = None
    source_length_unit: str | None = None
    source_free_flow_time_value: float | None = None
    source_free_flow_time_unit: str | None = None
    source_capacity_value: float | None = None
    source_capacity_unit: str | None = None

    def to_loading_link(
        self,
        *,
        tick_duration_seconds: float = 60.0,
        declared_storage_capacity_packets: int = LEGACY_LOADING_STORAGE_CAPACITY_PACKETS,
    ) -> Link:
        """Return an L1-compatible loading link carrying static metadata."""

        sending_capacity = self._capacity_packets_per_tick(tick_duration_seconds)
        return Link(
            link_id=self.link_id,
            declared_sending_capacity_per_tick=sending_capacity,
            declared_receiving_capacity_per_tick=sending_capacity,
            declared_storage_capacity_packets=declared_storage_capacity_packets,
            length_m=self.length_m,
            lane_count=self.lane_count,
            free_flow_speed_mps=self.free_flow_speed_mps,
            jam_density_veh_per_km_per_lane=self.jam_density_veh_per_km_per_lane,
            backward_wave_speed_mps=self.backward_wave_speed_mps,
            capacity_veh_per_hour_per_lane=self.capacity_veh_per_hour_per_lane,
            tick_duration_seconds=tick_duration_seconds,
        )

    def physical_capacity_vehicles_per_tick(
        self,
        *,
        tick_duration_seconds: float,
    ) -> float | None:
        """Return lane-aware physical capacity for parity checks, not legacy loading."""

        if self.capacity_veh_per_hour_per_lane is None or self.lane_count is None:
            return None
        if tick_duration_seconds <= 0:
            raise ValueError("tick_duration_seconds must be positive")
        return (
            self.capacity_veh_per_hour_per_lane
            * self.lane_count
            * tick_duration_seconds
            / 3600.0
        )

    def resolved_physical_parameters(
        self,
        *,
        tick_duration_seconds: float,
        fd_relative_tolerance: float = DEFAULT_FD_RELATIVE_TOLERANCE,
        minimum_lag_ticks: int = DEFAULT_MINIMUM_TIMESTEP_LAG_TICKS,
    ) -> ResolvedPhysicalLinkParameters:
        """Resolve static physical metadata without creating dynamic topology state."""

        free_flow_ticks = (
            0
            if self.length_m is None or self.free_flow_speed_mps is None
            else None
        )
        declared_storage_capacity_packets = (
            0
            if (
                self.length_m is None
                or self.lane_count is None
                or self.jam_density_veh_per_km_per_lane is None
            )
            else None
        )
        return Link(
            link_id=self.link_id,
            free_flow_ticks=free_flow_ticks,
            declared_storage_capacity_packets=declared_storage_capacity_packets,
            length_m=self.length_m,
            lane_count=self.lane_count,
            free_flow_speed_mps=self.free_flow_speed_mps,
            jam_density_veh_per_km_per_lane=self.jam_density_veh_per_km_per_lane,
            backward_wave_speed_mps=self.backward_wave_speed_mps,
            capacity_veh_per_hour_per_lane=self.capacity_veh_per_hour_per_lane,
            tick_duration_seconds=tick_duration_seconds,
        ).resolved_physical_parameters(
            fd_relative_tolerance=fd_relative_tolerance,
            minimum_lag_ticks=minimum_lag_ticks,
        )

    def require_parity_physical_parameters(
        self,
        *,
        tick_duration_seconds: float,
        fd_relative_tolerance: float = DEFAULT_FD_RELATIVE_TOLERANCE,
        minimum_lag_ticks: int = DEFAULT_MINIMUM_TIMESTEP_LAG_TICKS,
    ) -> ResolvedPhysicalLinkParameters:
        """Resolve physical metadata or fail when the static link is not parity eligible."""

        resolved = self.resolved_physical_parameters(
            tick_duration_seconds=tick_duration_seconds,
            fd_relative_tolerance=fd_relative_tolerance,
            minimum_lag_ticks=minimum_lag_ticks,
        )
        if not resolved.parity_eligible:
            raise ValueError(
                f"canonical link {self.link_id} is not parity-eligible: "
                f"{resolved.ineligibility_reasons}"
            )
        return resolved

    def _capacity_packets_per_tick(self, tick_duration_seconds: float) -> int:
        if self.capacity_veh_per_hour_per_lane is None:
            return 1
        packets_per_tick = self.capacity_veh_per_hour_per_lane * tick_duration_seconds / 3600.0
        return max(1, int(packets_per_tick))


@dataclass(frozen=True, slots=True)
class CanonicalTopology:
    """Immutable canonical topology artifact."""

    topology_id: str
    nodes: tuple[CanonicalNode, ...]
    links: tuple[CanonicalTopologyLink, ...]
    source_metadata: TopologySourceMetadata
    interpretation_assumptions: tuple[str, ...] = ()
    topology_hash: str = ""

    def __post_init__(self) -> None:
        self.validate()
        object.__setattr__(self, "topology_hash", self.compute_hash())

    def validate(self) -> bool:
        """Validate structural topology invariants."""

        node_ids = [node.node_id for node in self.nodes]
        link_ids = [link.link_id for link in self.links]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("canonical node IDs must be unique")
        if len(link_ids) != len(set(link_ids)):
            raise ValueError("canonical link IDs must be unique")

        node_id_set = set(node_ids)
        for link in self.links:
            if link.tail_node_id not in node_id_set:
                raise ValueError(f"link {link.link_id} references unknown tail node")
            if link.head_node_id not in node_id_set:
                raise ValueError(f"link {link.link_id} references unknown head node")

        incoming_by_node = {node_id: [] for node_id in node_ids}
        outgoing_by_node = {node_id: [] for node_id in node_ids}
        for link in self.links:
            outgoing_by_node[link.tail_node_id].append(link.link_id)
            incoming_by_node[link.head_node_id].append(link.link_id)

        for node in self.nodes:
            if node.incoming_link_ids != tuple(sorted(incoming_by_node[node.node_id])):
                raise ValueError(f"incoming connectivity mismatch for {node.node_id}")
            if node.outgoing_link_ids != tuple(sorted(outgoing_by_node[node.node_id])):
                raise ValueError(f"outgoing connectivity mismatch for {node.node_id}")
            node.junction_spec()

        return True

    def compute_hash(self) -> str:
        """Return a deterministic hash of canonical static topology content."""

        payload = self._hash_payload()
        serialised = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialised.encode("utf-8")).hexdigest()

    def as_loading_links(
        self,
        *,
        tick_duration_seconds: float = 60.0,
        declared_storage_capacity_packets: int = LEGACY_LOADING_STORAGE_CAPACITY_PACKETS,
    ) -> dict[str, Link]:
        """Map canonical links into L1 loading-link metadata records."""

        return {
            link.link_id: link.to_loading_link(
                tick_duration_seconds=tick_duration_seconds,
                declared_storage_capacity_packets=declared_storage_capacity_packets,
            )
            for link in self.links
        }

    def as_loading_nodes(self) -> tuple[Node, ...]:
        """Map canonical static connectivity into loading-engine node records."""

        return tuple(
            Node(
                node_id=node.node_id,
                incoming_link_ids=node.incoming_link_ids,
                outgoing_link_ids=node.outgoing_link_ids,
                junction_spec=node.junction_spec(),
            )
            for node in self.nodes
        )

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "topology_id": self.topology_id,
            "source_metadata": self.source_metadata.hash_payload(),
            "interpretation_assumptions": list(self.interpretation_assumptions),
            "nodes": [
                {
                    "node_id": node.node_id,
                    "source_node_id": node.source_node_id,
                    "incoming_link_ids": list(node.incoming_link_ids),
                    "outgoing_link_ids": list(node.outgoing_link_ids),
                    "movement_specs": [
                        {
                            "movement_id": movement.movement_id,
                            "upstream_link_id": movement.upstream_link_id,
                            "downstream_link_id": movement.downstream_link_id,
                            "priority_weight": movement.priority_weight,
                            "lane_group_ids": list(movement.lane_group_ids),
                            "conflict_resource_ids": list(
                                movement.conflict_resource_ids
                            ),
                            "signal_group_id": movement.signal_group_id,
                            "provenance": list(movement.provenance),
                        }
                        for movement in node.junction_spec().movement_specs
                    ],
                    "lane_group_ids": list(node.junction_spec().lane_group_ids),
                    "movement_lane_group_mappings": [
                        (movement_id, list(lane_group_ids))
                        for movement_id, lane_group_ids in (
                            node.junction_spec().movement_lane_group_mappings
                        )
                    ],
                    "lane_group_capacities": list(
                        node.junction_spec().lane_group_capacities
                    ),
                    "conflict_resource_ids": list(
                        node.junction_spec().conflict_resource_ids
                    ),
                    "conflict_resource_capacities": list(
                        node.junction_spec().conflict_resource_capacities
                    ),
                    "governance_refs": list(node.junction_spec().governance_refs),
                    "fifo_policy": node.junction_spec().fifo_policy,
                }
                for node in sorted(self.nodes, key=lambda item: item.node_id)
            ],
            "links": [
                {
                    "link_id": link.link_id,
                    "tail_node_id": link.tail_node_id,
                    "head_node_id": link.head_node_id,
                    "source_link_id": link.source_link_id,
                    "source_tail_node_id": link.source_tail_node_id,
                    "source_head_node_id": link.source_head_node_id,
                    "length_m": link.length_m,
                    "lane_count": link.lane_count,
                    "free_flow_speed_mps": link.free_flow_speed_mps,
                    "capacity_veh_per_hour_per_lane": (
                        link.capacity_veh_per_hour_per_lane
                    ),
                    "jam_density_veh_per_km_per_lane": (
                        link.jam_density_veh_per_km_per_lane
                    ),
                    "backward_wave_speed_mps": link.backward_wave_speed_mps,
                    "source_length_value": link.source_length_value,
                    "source_length_unit": link.source_length_unit,
                    "source_free_flow_time_value": link.source_free_flow_time_value,
                    "source_free_flow_time_unit": link.source_free_flow_time_unit,
                    "source_capacity_value": link.source_capacity_value,
                    "source_capacity_unit": link.source_capacity_unit,
                }
                for link in sorted(self.links, key=lambda item: item.link_id)
            ],
        }
