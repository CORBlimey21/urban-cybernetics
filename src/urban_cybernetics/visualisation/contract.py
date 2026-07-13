"""Pydantic models for the V1 contract between Python evidence and the browser."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CONTRACT_VERSION = "uc.visualisation.run.v1"


class ContractModel(BaseModel):
    """Strict serialisable base for all public V-track records."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticStatus(StrEnum):
    CANONICAL_EVENT = "canonical_event_data"
    IMMUTABLE_TOPOLOGY = "immutable_topology_metadata"
    ENGINE_MATERIALISED = "engine_owned_materialised_state"
    EVENT_DERIVED = "event_derived_scientific_projection"
    VALIDATION = "validation_output"
    PROVENANCE = "provenance_configuration_metadata"
    PRESENTATION_ONLY = "presentation_only_interpolation"


class RunStatus(StrEnum):
    COMPLETE = "complete"
    BOUNDED = "bounded"
    TIMED_OUT = "timed_out"
    PARTIAL = "partial"


class PacketReplayStatus(StrEnum):
    NOT_YET_OBSERVED = "not_yet_observed"
    IN_TRANSIT = "in_transit"
    QUEUED = "queued"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class FieldAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE_IN_ARTIFACT = "unavailable_in_artifact"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"
    NOT_YET_OBSERVED = "not_yet_observed"
    OMITTED = "omitted_from_artifact"


class EvidenceDescriptor(ContractModel):
    semantic_status: SemanticStatus
    source: str
    units: str | None = None
    time_basis: str | None = None
    counting_basis: str | None = None
    boundary_direction: str | None = None
    aggregation_window_ticks: int | None = None


class VRunIdentity(ContractModel):
    run_id: str
    scenario_name: str
    status: RunStatus
    status_reason: str
    topology_id: str
    topology_hash: str
    configuration_id: str
    configuration_hash: str
    model_profile_id: str
    tick_duration_seconds: float = Field(gt=0)
    simulation_time_basis: Literal["integer_physical_tick"] = "integer_physical_tick"
    start_tick: int = Field(ge=0)
    end_tick: int = Field(ge=0)
    event_count: int = Field(ge=0)
    packet_count: int = Field(ge=0)
    created_at: str | None = None

    @model_validator(mode="after")
    def validate_tick_range(self) -> "VRunIdentity":
        if self.end_tick < self.start_tick:
            raise ValueError("end_tick must not precede start_tick")
        return self


class VProvenance(ContractModel):
    descriptor: EvidenceDescriptor
    code_version: str | None
    input_artifact_ids: tuple[str, ...]
    source_name: str
    source_format: str
    source_file_sha256: str
    interpretation_assumptions: tuple[str, ...]
    config_snapshot: dict[str, object]


class VNode(ContractModel):
    node_id: str
    source_node_id: str
    incoming_link_ids: tuple[str, ...]
    outgoing_link_ids: tuple[str, ...]
    movement_ids: tuple[str, ...]
    fifo_policy: str


class VLink(ContractModel):
    link_id: str
    tail_node_id: str
    head_node_id: str
    source_link_id: str
    length_m: float | None
    lane_count: int | None
    free_flow_speed_mps: float | None
    capacity_veh_per_hour_per_lane: float | None
    jam_density_veh_per_km_per_lane: float | None
    backward_wave_speed_mps: float | None
    field_availability: dict[str, FieldAvailability]


class VMovement(ContractModel):
    movement_id: str
    node_id: str
    upstream_link_id: str
    downstream_link_id: str
    priority_weight: int
    lane_group_ids: tuple[str, ...]
    conflict_resource_ids: tuple[str, ...]
    signal_group_id: str | None


class VTopology(ContractModel):
    descriptor: EvidenceDescriptor
    topology_id: str
    topology_hash: str
    nodes: tuple[VNode, ...]
    links: tuple[VLink, ...]
    movements: tuple[VMovement, ...]


class VPacket(ContractModel):
    packet_id: str
    demand_id: str
    origin_node_id: str | None
    destination_node_id: str | None
    route_id: str | None
    route_intent: tuple[str, ...]
    cohort_id: str | None
    authority_id: str | None
    packet_unit_weight: int
    field_availability: dict[str, FieldAvailability]


class VCanonicalEvent(ContractModel):
    sequence_number: int = Field(ge=0)
    packet_id: str
    event_type: Literal[
        "instantiated",
        "link_entry",
        "link_exit",
        "queue_entry",
        "queue_exit",
        "completed",
        "cancelled",
    ]
    entity_id: str
    physical_tick: int = Field(ge=0)


class VEventStream(ContractModel):
    descriptor: EvidenceDescriptor
    events: tuple[VCanonicalEvent, ...]

    @model_validator(mode="after")
    def validate_canonical_order(self) -> "VEventStream":
        expected = list(range(len(self.events)))
        actual = [event.sequence_number for event in self.events]
        if actual != expected:
            raise ValueError("canonical events must be contiguous sequence-number order")
        previous_tick = -1
        for event in self.events:
            if event.physical_tick < previous_tick:
                raise ValueError("canonical event ticks must not move backwards")
            previous_tick = event.physical_tick
        return self


class VPacketReplayState(ContractModel):
    packet_id: str
    status: PacketReplayStatus
    current_link_id: str | None
    queue_boundary_id: str | None
    realised_path: tuple[str, ...]
    last_event_sequence: int | None


class VLinkReplayState(ContractModel):
    link_id: str
    packet_ids: tuple[str, ...]
    queued_packet_ids: tuple[str, ...]
    occupancy_packets: int = Field(ge=0)
    cumulative_entries: int = Field(ge=0)
    cumulative_exits: int = Field(ge=0)


class VQueueReplayState(ContractModel):
    boundary_id: str
    packet_ids: tuple[str, ...]


class VRunCounts(ContractModel):
    not_yet_observed: int = Field(ge=0)
    in_transit: int = Field(ge=0)
    queued: int = Field(ge=0)
    completed: int = Field(ge=0)
    cancelled: int = Field(ge=0)


class VReplayState(ContractModel):
    descriptor: EvidenceDescriptor
    tick: int = Field(ge=0)
    applied_through_sequence: int | None
    packets: tuple[VPacketReplayState, ...]
    links: tuple[VLinkReplayState, ...]
    queues: tuple[VQueueReplayState, ...]
    counts: VRunCounts

    @model_validator(mode="after")
    def validate_scientific_state(self) -> "VReplayState":
        packet_ids = [packet.packet_id for packet in self.packets]
        if len(packet_ids) != len(set(packet_ids)):
            raise ValueError("replay packet IDs must be unique")
        status_counts = {status: 0 for status in PacketReplayStatus}
        for packet in self.packets:
            status_counts[packet.status] += 1
        if (
            self.counts.not_yet_observed
            != status_counts[PacketReplayStatus.NOT_YET_OBSERVED]
            or self.counts.in_transit != status_counts[PacketReplayStatus.IN_TRANSIT]
            or self.counts.queued != status_counts[PacketReplayStatus.QUEUED]
            or self.counts.completed != status_counts[PacketReplayStatus.COMPLETED]
            or self.counts.cancelled != status_counts[PacketReplayStatus.CANCELLED]
        ):
            raise ValueError("replay counts must equal packet lifecycle states")

        membership: dict[str, str] = {}
        for link in self.links:
            if link.occupancy_packets != len(link.packet_ids):
                raise ValueError("link occupancy must equal packet membership length")
            if link.cumulative_entries - link.cumulative_exits != link.occupancy_packets:
                raise ValueError("link occupancy must equal cumulative entries minus exits")
            if not set(link.queued_packet_ids).issubset(link.packet_ids):
                raise ValueError("queued link packets must remain in link membership")
            for packet_id in link.packet_ids:
                if packet_id in membership:
                    raise ValueError("packet cannot be a member of multiple links")
                membership[packet_id] = link.link_id

        queue_membership = {
            packet_id: queue.boundary_id
            for queue in self.queues
            for packet_id in queue.packet_ids
        }
        for packet in self.packets:
            if packet.current_link_id != membership.get(packet.packet_id):
                raise ValueError("packet current_link_id must match link membership")
            if packet.queue_boundary_id != queue_membership.get(packet.packet_id):
                raise ValueError("packet queue boundary must match queue membership")
            if packet.status == PacketReplayStatus.QUEUED and packet.queue_boundary_id is None:
                raise ValueError("queued packet must expose its canonical queue boundary")
        return self


class VCumulativeLinkSeries(ContractModel):
    descriptor: EvidenceDescriptor
    link_id: str
    ticks: tuple[int, ...]
    cumulative_entries: tuple[int, ...]
    cumulative_exits: tuple[int, ...]
    storage_packets: tuple[int, ...]

    @model_validator(mode="after")
    def validate_series_lengths(self) -> "VCumulativeLinkSeries":
        lengths = {
            len(self.ticks),
            len(self.cumulative_entries),
            len(self.cumulative_exits),
            len(self.storage_packets),
        }
        if len(lengths) != 1:
            raise ValueError("cumulative series arrays must have equal length")
        return self


class VValidationStatus(ContractModel):
    descriptor: EvidenceDescriptor
    overall_status: Literal["not_run", "passed", "failed"]
    checks: dict[str, Literal["not_run", "passed", "failed"]]
    notes: tuple[str, ...]


class VPresentationMetadata(ContractModel):
    descriptor: EvidenceDescriptor
    layout_kind: Literal["synthetic_declared", "synthetic_deterministic"]
    layout_note: str
    node_positions: dict[str, tuple[float, float]]
    interpolation_note: str


class VRunBundle(ContractModel):
    schema_version: Literal["uc.visualisation.run.v1"] = CONTRACT_VERSION
    run: VRunIdentity
    provenance: VProvenance
    topology: VTopology
    packets_descriptor: EvidenceDescriptor
    packets: tuple[VPacket, ...]
    event_stream: VEventStream
    replay_states: tuple[VReplayState, ...]
    cumulative_link_series: tuple[VCumulativeLinkSeries, ...]
    validation: VValidationStatus
    presentation: VPresentationMetadata

    @model_validator(mode="after")
    def validate_cross_references(self) -> "VRunBundle":
        if self.run.topology_id != self.topology.topology_id:
            raise ValueError("run topology_id must match topology artifact")
        if self.run.topology_hash != self.topology.topology_hash:
            raise ValueError("run topology_hash must match topology artifact")
        if self.run.event_count != len(self.event_stream.events):
            raise ValueError("run event_count must match canonical event stream")
        if self.run.packet_count != len(self.packets):
            raise ValueError("run packet_count must match packet metadata")
        packet_ids = {packet.packet_id for packet in self.packets}
        if any(event.packet_id not in packet_ids for event in self.event_stream.events):
            raise ValueError("canonical event references missing packet metadata")
        link_ids = {link.link_id for link in self.topology.links}
        if {series.link_id for series in self.cumulative_link_series} != link_ids:
            raise ValueError("cumulative series must cover every topology link")
        ticks = [state.tick for state in self.replay_states]
        expected_ticks = list(range(self.run.start_tick, self.run.end_tick + 1))
        if ticks != expected_ticks:
            raise ValueError("replay states must cover every run tick in order")
        if self.run.status == RunStatus.COMPLETE:
            final_counts = self.replay_states[-1].counts
            if (
                final_counts.not_yet_observed
                or final_counts.in_transit
                or final_counts.queued
            ):
                raise ValueError("complete run cannot end with unresolved packet state")
        return self
