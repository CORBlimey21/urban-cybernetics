# SPDX-License-Identifier: MPL-2.0
"""Stable adapter from immutable run evidence into the V1 browser contract."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from urban_cybernetics.core import Event, Packet
from urban_cybernetics.inspection import PacketDiagnosticMetadata
from urban_cybernetics.topology import CanonicalTopology
from urban_cybernetics.validation import ValidationContext

from .contract import (
    EvidenceDescriptor,
    FieldAvailability,
    RunStatus,
    SemanticStatus,
    VCumulativeLinkSeries,
    VCanonicalEvent,
    VEventStream,
    VLink,
    VMovement,
    VNode,
    VPacket,
    VPresentationMetadata,
    VProvenance,
    VRunBundle,
    VRunIdentity,
    VTopology,
    VValidationStatus,
)
from .replay import build_replay_states
from .layouts import circular_positions, layouts_for_topology


def build_run_bundle(
    *,
    run_id: str,
    scenario_name: str,
    topology: CanonicalTopology,
    context: ValidationContext,
    status: RunStatus,
    status_reason: str,
    tick_duration_seconds: float,
    config_snapshot: Mapping[str, object],
    configuration_id: str,
    packet_metadata_by_demand_id: Mapping[str, PacketDiagnosticMetadata] | None = None,
    validation_status: str = "not_run",
    validation_notes: Sequence[str] = (),
    input_artifact_ids: Sequence[str] = (),
    code_version: str | None = None,
    created_at: str | None = None,
    node_positions: Mapping[str, tuple[float, float]] | None = None,
) -> VRunBundle:
    """Build and validate a detached run bundle without importing the engine."""

    if tick_duration_seconds <= 0:
        raise ValueError("tick_duration_seconds must be positive")
    if validation_status not in {"not_run", "passed", "failed"}:
        raise ValueError("unsupported validation_status")
    events = tuple(context.event_log)
    packets = packet_records(
        context.packets,
        topology,
        packet_metadata_by_demand_id or {},
    )
    configuration_hash = _json_hash(config_snapshot)
    topology_contract = topology_record(topology)
    replay_states = build_replay_states(
        events=events,
        packets=packets,
        link_ids=context.link_ids,
        start_tick=0,
        end_tick=context.current_tick,
    )
    count_report = context.count_consistency_report
    checks = {
        "canonical_count_consistency": (
            "passed" if count_report.is_consistent else "failed"
        )
    }
    default_layout_id, layouts = layouts_for_topology(
        topology, declared_positions=node_positions
    )
    default_layout = next(
        layout for layout in layouts if layout.layout_id == default_layout_id
    )
    resolved_positions = default_layout.node_coordinates

    return VRunBundle(
        run=VRunIdentity(
            run_id=run_id,
            scenario_name=scenario_name,
            status=status,
            status_reason=status_reason,
            topology_id=topology.topology_id,
            topology_hash=topology.topology_hash,
            configuration_id=configuration_id,
            configuration_hash=configuration_hash,
            model_profile_id=context.model_profile_id,
            tick_duration_seconds=tick_duration_seconds,
            start_tick=0,
            end_tick=context.current_tick,
            event_count=len(events),
            packet_count=len(packets),
            created_at=created_at,
        ),
        provenance=VProvenance(
            descriptor=EvidenceDescriptor(
                semantic_status=SemanticStatus.PROVENANCE,
                source="run metadata, immutable configuration, and topology source metadata",
            ),
            code_version=code_version,
            input_artifact_ids=tuple(input_artifact_ids),
            source_name=topology.source_metadata.source_name,
            source_format=topology.source_metadata.source_format,
            source_file_sha256=topology.source_metadata.source_file_sha256,
            interpretation_assumptions=topology.interpretation_assumptions,
            config_snapshot=dict(config_snapshot),
        ),
        topology=topology_contract,
        packets_descriptor=EvidenceDescriptor(
            semantic_status=SemanticStatus.PROVENANCE,
            source="immutable packet metadata snapshot and declared route intent",
            units="unit packets",
            counting_basis="one conserved packet identity per record",
        ),
        packets=packets,
        event_stream=VEventStream(
            descriptor=EvidenceDescriptor(
                semantic_status=SemanticStatus.CANONICAL_EVENT,
                source="append-only loading-engine event history",
                units="unit packet lifecycle events",
                time_basis="integer physical tick",
                counting_basis="canonical sequence number",
            ),
            events=tuple(
                VCanonicalEvent(
                    sequence_number=event.sequence_number,
                    packet_id=event.packet_id,
                    event_type=event.event_type.value,
                    entity_id=event.entity_id,
                    physical_tick=event.physical_tick,
                )
                for event in events
            ),
        ),
        replay_states=replay_states,
        cumulative_link_series=_cumulative_series(context),
        validation=VValidationStatus(
            descriptor=EvidenceDescriptor(
                semantic_status=SemanticStatus.VALIDATION,
                source="Python validation layer",
            ),
            overall_status=validation_status,
            checks=checks,
            notes=tuple(validation_notes),
        ),
        presentation=VPresentationMetadata(
            descriptor=EvidenceDescriptor(
                semantic_status=SemanticStatus.PRESENTATION_ONLY,
                source="viewer layout adapter",
                units="layout-specific; see layout coordinate_units",
            ),
            layout_schema_version="uc.visualisation.layout.v1",
            default_layout_id=default_layout_id,
            layouts=layouts,
            layout_kind=(
                "synthetic_declared"
                if default_layout.kind.value == "declared_schematic"
                else "synthetic_deterministic"
            ),
            layout_note=default_layout.label,
            node_positions=resolved_positions,
            interpolation_note=(
                "Animated markers are presentation-only interpolation. They are never "
                "stored as packet positions or used in scientific calculations."
            ),
        ),
    )


def write_run_bundle(bundle: VRunBundle, path: Path) -> None:
    """Persist a validated V1 bundle as deterministic JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        bundle.model_dump_json(indent=2, exclude_none=False) + "\n",
        encoding="utf-8",
    )


def load_run_bundle(path: Path) -> VRunBundle:
    """Load and validate a persisted V1 bundle."""

    return VRunBundle.model_validate_json(path.read_text(encoding="utf-8"))


def packet_records(
    packets: Mapping[str, Packet],
    topology: CanonicalTopology,
    metadata_by_demand_id: Mapping[str, PacketDiagnosticMetadata],
) -> tuple[VPacket, ...]:
    topology_links = {link.link_id: link for link in topology.links}
    records: list[VPacket] = []
    for packet in sorted(packets.values(), key=lambda item: item.packet_id):
        metadata = metadata_by_demand_id.get(packet.demand_id)
        route_links = [topology_links.get(link_id) for link_id in packet.route_intent]
        route_is_known = bool(route_links) and all(link is not None for link in route_links)
        derived_origin = route_links[0].tail_node_id if route_is_known else None
        derived_destination = route_links[-1].head_node_id if route_is_known else None
        origin = metadata.origin_node_id if metadata and metadata.origin_node_id else derived_origin
        destination = (
            metadata.destination_node_id
            if metadata and metadata.destination_node_id
            else derived_destination
        )
        route_id = metadata.route_id if metadata else None
        records.append(
            VPacket(
                packet_id=packet.packet_id,
                demand_id=packet.demand_id,
                origin_node_id=origin,
                destination_node_id=destination,
                route_id=route_id,
                route_intent=packet.route_intent,
                cohort_id=None,
                authority_id=None,
                packet_unit_weight=packet.packet_unit_weight,
                field_availability={
                    "origin_node_id": (
                        FieldAvailability.AVAILABLE
                        if origin is not None
                        else FieldAvailability.UNAVAILABLE_IN_ARTIFACT
                    ),
                    "destination_node_id": (
                        FieldAvailability.AVAILABLE
                        if destination is not None
                        else FieldAvailability.UNAVAILABLE_IN_ARTIFACT
                    ),
                    "route_id": (
                        FieldAvailability.AVAILABLE
                        if route_id is not None
                        else FieldAvailability.UNAVAILABLE_IN_ARTIFACT
                    ),
                    "cohort_id": FieldAvailability.UNAVAILABLE_IN_ARTIFACT,
                    "authority_id": FieldAvailability.UNAVAILABLE_IN_ARTIFACT,
                },
            )
        )
    return tuple(records)


def topology_record(topology: CanonicalTopology) -> VTopology:
    movements: list[VMovement] = []
    nodes: list[VNode] = []
    for node in sorted(topology.nodes, key=lambda item: item.node_id):
        junction = node.junction_spec()
        nodes.append(
            VNode(
                node_id=node.node_id,
                source_node_id=node.source_node_id,
                incoming_link_ids=node.incoming_link_ids,
                outgoing_link_ids=node.outgoing_link_ids,
                movement_ids=tuple(movement.movement_id for movement in junction.movement_specs),
                fifo_policy=junction.fifo_policy,
            )
        )
        movements.extend(
            VMovement(
                movement_id=movement.movement_id,
                node_id=node.node_id,
                upstream_link_id=movement.upstream_link_id,
                downstream_link_id=movement.downstream_link_id,
                priority_weight=movement.priority_weight,
                lane_group_ids=movement.lane_group_ids,
                conflict_resource_ids=movement.conflict_resource_ids,
                signal_group_id=movement.signal_group_id,
            )
            for movement in junction.movement_specs
        )

    return VTopology(
        descriptor=EvidenceDescriptor(
            semantic_status=SemanticStatus.IMMUTABLE_TOPOLOGY,
            source="canonical topology artifact",
            units="SI static link metadata where declared",
        ),
        topology_id=topology.topology_id,
        topology_hash=topology.topology_hash,
        nodes=tuple(nodes),
        links=tuple(
            VLink(
                link_id=link.link_id,
                tail_node_id=link.tail_node_id,
                head_node_id=link.head_node_id,
                source_link_id=link.source_link_id,
                length_m=link.length_m,
                lane_count=link.lane_count,
                free_flow_speed_mps=link.free_flow_speed_mps,
                capacity_veh_per_hour_per_lane=link.capacity_veh_per_hour_per_lane,
                jam_density_veh_per_km_per_lane=link.jam_density_veh_per_km_per_lane,
                backward_wave_speed_mps=link.backward_wave_speed_mps,
                field_availability={
                    field_name: (
                        FieldAvailability.AVAILABLE
                        if getattr(link, field_name) is not None
                        else FieldAvailability.UNAVAILABLE_IN_ARTIFACT
                    )
                    for field_name in (
                        "length_m",
                        "lane_count",
                        "free_flow_speed_mps",
                        "capacity_veh_per_hour_per_lane",
                        "jam_density_veh_per_km_per_lane",
                        "backward_wave_speed_mps",
                    )
                },
            )
            for link in sorted(topology.links, key=lambda item: item.link_id)
        ),
        movements=tuple(sorted(movements, key=lambda item: item.movement_id)),
    )


def _cumulative_series(context: ValidationContext) -> tuple[VCumulativeLinkSeries, ...]:
    projection = context.cumulative_count_projection
    counts_by_link_tick = {
        (count.link_id, count.tick): count for count in projection.aggregate_counts
    }
    ticks = tuple(range(context.current_tick + 1))
    descriptor = EvidenceDescriptor(
        semantic_status=SemanticStatus.EVENT_DERIVED,
        source="Python cumulative_count_projection over canonical boundary events",
        units="unit packets",
        time_basis=projection.tick_convention,
        counting_basis="cumulative canonical LINK_ENTRY and LINK_EXIT events",
        boundary_direction="entries at upstream link boundary; exits at downstream link boundary",
        aggregation_window_ticks=1,
    )
    series: list[VCumulativeLinkSeries] = []
    for link_id in sorted(context.link_ids):
        entries = tuple(counts_by_link_tick[(link_id, tick)].entries for tick in ticks)
        exits = tuple(counts_by_link_tick[(link_id, tick)].exits for tick in ticks)
        series.append(
            VCumulativeLinkSeries(
                descriptor=descriptor,
                link_id=link_id,
                ticks=ticks,
                cumulative_entries=entries,
                cumulative_exits=exits,
                storage_packets=tuple(entry - exit for entry, exit in zip(entries, exits)),
            )
        )
    return tuple(series)


def deterministic_positions(topology: CanonicalTopology) -> dict[str, tuple[float, float]]:
    """Compatibility alias for the original deterministic circular fallback."""

    return circular_positions(topology)


def _json_hash(value: Mapping[str, object]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
