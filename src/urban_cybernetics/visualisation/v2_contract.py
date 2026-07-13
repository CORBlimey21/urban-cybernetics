"""Versioned V2 control- and evidence-plane contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from .contract import ContractModel, VCanonicalEvent, VReplayState


CONTROL_CONTRACT_VERSION = "uc.visualisation.control.v2"
EVIDENCE_CONTRACT_VERSION = "uc.visualisation.evidence.v2"
CHECKPOINT_SCHEMA_VERSION = "uc.visualisation.checkpoint.v1"
EVENT_CHUNK_SCHEMA_VERSION = "uc.visualisation.event-chunk.v1"
MOVEMENT_TRACE_SCHEMA_VERSION = "uc.visualisation.movement-trace.v1"

StableId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]


class ResourceClassification(StrEnum):
    CANONICAL_SOURCE = "canonical_source_based"
    ASSUMPTION = "assumption_based"
    SYNTHETIC = "synthetic"
    CALIBRATED = "calibrated"


class ResourceKind(StrEnum):
    TOPOLOGY = "topology"
    PHYSICAL_PROFILE = "physical_profile"
    DEMAND_SOURCE = "demand_source"
    PACKET_SELECTION = "packet_selection_policy"
    TICK_POLICY = "tick_policy"
    COMPLETION_POLICY = "completion_policy"
    STOP_POLICY = "stop_policy"
    VALIDATION_POLICY = "validation_policy"
    REPLAY_POLICY = "replay_policy"
    PERSISTENCE_POLICY = "persistence_policy"


class CatalogueParameter(ContractModel):
    parameter_id: StableId
    name: str
    description: str
    units: str | None = None
    default: int | float | str | bool | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None


class CatalogueResource(ContractModel):
    resource_id: StableId
    kind: ResourceKind
    name: str
    description: str
    provenance: str
    classification: ResourceClassification
    parameters: tuple[CatalogueParameter, ...] = ()
    compatible_topology_ids: tuple[StableId, ...] = ()
    compatible_profile_ids: tuple[StableId, ...] = ()
    warnings: tuple[str, ...] = ()


class ResourceCatalogue(ContractModel):
    schema_version: Literal["uc.visualisation.control.v2"] = CONTROL_CONTRACT_VERSION
    resources: tuple[CatalogueResource, ...]

    def by_id(self, resource_id: str) -> CatalogueResource:
        for resource in self.resources:
            if resource.resource_id == resource_id:
                return resource
        raise KeyError(resource_id)


class RunLifecycleState(StrEnum):
    CREATED = "created"
    RESOLVING = "resolving"
    SETTING_UP = "setting_up"
    RUNNING = "running"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    RESUME_REQUESTED = "resume_requested"
    CANCEL_REQUESTED = "cancel_requested"
    FINALISING = "finalising"
    VALIDATING = "validating"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    FAILED = "failed"


class RunRequestV2(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal["uc.visualisation.control.v2"] = CONTROL_CONTRACT_VERSION
    topology_id: StableId
    physical_profile_id: StableId
    demand_source_id: StableId
    requested_packet_count: int = Field(ge=1, le=1000)
    packet_selection_policy_id: StableId = "canonical_prefix_v1"
    seed: int = Field(default=0, ge=0, le=2**32 - 1)
    tick_policy_id: StableId
    requested_tick_duration_seconds: float | None = Field(default=None, gt=0)
    runtime_limit_seconds: float = Field(default=60.0, gt=0, le=3600)
    tick_limit: int = Field(default=600, ge=1, le=100_000)
    completion_policy_id: StableId = "all_instantiated_packets_terminal_v1"
    stop_policy_id: StableId = "bounded_tick_or_wall_time_v1"
    validation_policy_id: StableId = "core_integrity_v1"
    replay_policy_id: StableId = "exact_if_complete_v1"
    persistence_policy_id: StableId = "retain_all_evidence_v1"
    run_label: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=1000)


class ResolutionRecord(ContractModel):
    field: str
    requested: int | float | str | bool | None
    resolved: int | float | str | bool | None
    rule: str


class FrozenRunRequest(ContractModel):
    schema_version: Literal["uc.visualisation.control.v2"] = CONTROL_CONTRACT_VERSION
    run_id: StableId
    request: RunRequestV2
    created_at: datetime
    resolved_topology_hash: str
    resolved_profile_hash: str
    resolved_demand_hash: str
    resolved_tick_duration_seconds: float = Field(gt=0)
    code_commit: str
    seed_registry: dict[str, int]
    resolution_records: tuple[ResolutionRecord, ...]


class RunCountsV2(ContractModel):
    requested: int = Field(ge=0)
    instantiated: int = Field(ge=0)
    completed: int = Field(ge=0)
    unresolved: int = Field(ge=0)
    cancelled: int = Field(ge=0)


class RunArtifactSummary(ContractModel):
    run_id: StableId
    title: str
    description: str
    contract_version: str
    topology_id: StableId
    topology_hash: str
    physical_profile_id: StableId
    profile_hash: str
    demand_source_id: StableId
    demand_hash: str
    seed: int
    status: RunLifecycleState
    stop_reason: str | None
    created_at: datetime
    updated_at: datetime
    validation_status: Literal["pending", "passed", "failed", "not_requested"]
    configuration_hash: str
    event_count: int = Field(ge=0)
    final_tick: int = Field(ge=0)
    counts: RunCountsV2
    assumption_warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_terminal_counts(self) -> "RunArtifactSummary":
        if self.status == RunLifecycleState.COMPLETE and (
            self.counts.unresolved
            or self.counts.cancelled
            or self.counts.completed != self.counts.requested
            or self.counts.instantiated != self.counts.requested
        ):
            raise ValueError("complete artifact requires every requested packet to be instantiated and completed")
        if self.counts.completed + self.counts.cancelled > self.counts.instantiated:
            raise ValueError("terminal packet counts cannot exceed instantiated count")
        return self


class LifecycleTransition(ContractModel):
    sequence: int = Field(ge=0)
    occurred_at: datetime
    previous_state: RunLifecycleState | None
    state: RunLifecycleState
    reason: str


class RunCommandAction(StrEnum):
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"


class RunCommand(ContractModel):
    schema_version: Literal["uc.visualisation.control.v2"] = CONTROL_CONTRACT_VERSION
    command_id: StableId
    action: RunCommandAction


class RunCommandAcknowledgement(ContractModel):
    command_id: StableId
    action: RunCommandAction
    accepted: bool
    duplicate: bool
    lifecycle_state: RunLifecycleState
    detail: str


class LiveMessageType(StrEnum):
    LIFECYCLE = "lifecycle_transition"
    SETUP = "setup_progress"
    TICK_SEALED = "tick_batch_sealed"
    EVENT_RANGE = "canonical_event_range_appended"
    CHECKPOINT = "checkpoint_sealed"
    PROGRESS = "progress"
    VALIDATION = "validation_progress"
    WARNING = "warning"
    TERMINAL = "terminal_result"


class LiveMessage(ContractModel):
    schema_version: Literal["uc.visualisation.control.v2"] = CONTROL_CONTRACT_VERSION
    message_id: int = Field(ge=0)
    run_id: StableId
    message_type: LiveMessageType
    occurred_at: datetime
    lifecycle_state: RunLifecycleState
    payload: dict[str, object]


class EventChunk(ContractModel):
    schema_version: Literal["uc.visualisation.event-chunk.v1"] = EVENT_CHUNK_SCHEMA_VERSION
    run_id: StableId
    chunk_index: int = Field(ge=0)
    start_sequence: int = Field(ge=0)
    end_sequence: int = Field(ge=0)
    start_tick: int = Field(ge=0)
    end_tick: int = Field(ge=0)
    events: tuple[VCanonicalEvent, ...]
    content_sha256: str

    @model_validator(mode="after")
    def validate_order(self) -> "EventChunk":
        if not self.events:
            raise ValueError("sealed event chunk cannot be empty")
        sequences = [event.sequence_number for event in self.events]
        if sequences != list(range(self.start_sequence, self.end_sequence + 1)):
            raise ValueError("event chunk sequence range is not exact")
        if self.events[0].physical_tick != self.start_tick:
            raise ValueError("event chunk start_tick mismatch")
        if self.events[-1].physical_tick != self.end_tick:
            raise ValueError("event chunk end_tick mismatch")
        return self


class ReplayCheckpoint(ContractModel):
    schema_version: Literal["uc.visualisation.checkpoint.v1"] = CHECKPOINT_SCHEMA_VERSION
    run_id: StableId
    checkpoint_index: int = Field(ge=0)
    state: VReplayState
    source_event_sha256: str


class MovementFlowEvidence(ContractModel):
    movement_id: str
    upstream_link_id: str
    downstream_link_id: str
    request_packet_ids: tuple[str, ...]
    upstream_fifo_packet_ids: tuple[str, ...]
    approved_packet_ids: tuple[str, ...]
    rejected_packet_reasons: tuple[tuple[str, str], ...]
    receiving_supply_packets: int | None
    movement_capacity_packets: int | None
    lane_group_constraints: dict[str, int]
    conflict_resource_constraints: dict[str, int]
    signal_state: Literal["open", "closed", "not_declared"]
    governance_state: str | None
    resulting_canonical_event_sequences: tuple[int, ...]


class MovementAllocationEvidence(ContractModel):
    schema_version: Literal["uc.visualisation.movement-trace.v1"] = MOVEMENT_TRACE_SCHEMA_VERSION
    run_id: StableId
    tick: int = Field(ge=0)
    junction_id: str
    allocator_id: str
    movement_spec_hash: str | None
    semantic_sources: dict[str, str]
    movements: tuple[MovementFlowEvidence, ...]
