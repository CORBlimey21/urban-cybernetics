"""Versioned contracts for the local M8 validation workbench."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


VALIDATION_CASE_CONTRACT_VERSION = "uc.validation.case.v1"
VALIDATION_RESULT_CONTRACT_VERSION = "uc.validation.result.v1"


class ValidationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceClass(StrEnum):
    ANALYTICAL = "analytical"
    PUBLISHED_NUMERICAL = "published_numerical_reproduction"
    STRUCTURAL = "structural_requirement"
    CROSS_IMPLEMENTATION = "cross_implementation"
    BENCHMARK = "benchmark"


class ComparisonStatus(StrEnum):
    EXACT = "exact"
    CONVERTED = "converted"
    BOUNDED = "bounded"
    STATISTICAL = "statistical"
    STRUCTURAL = "structural"
    BLOCKED = "blocked"
    NOT_COMPARABLE = "not_comparable"


class ValidationStatus(StrEnum):
    NOT_RUN = "not_run"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class InputCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"


class EvidenceSource(StrEnum):
    CANONICAL = "canonical"
    EVENT_DERIVED = "event_derived"
    ENGINE_EXPORTED = "engine_exported"
    ANALYTICAL_REFERENCE = "analytical_reference"
    VALIDATION_OUTPUT = "validation_output"
    PRESENTATION_ONLY = "presentation_only"


class ValidationLifecycle(StrEnum):
    CREATED = "created"
    SETTING_UP = "setting_up"
    EXECUTING = "executing"
    COMPARING = "comparing"
    PERSISTING = "persisting"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"


class Citation(ValidationModel):
    source_id: str
    citation_text: str
    source_section: str | None = None
    figure: str | None = None
    equation: str | None = None
    table: str | None = None
    url: str | None = None


class ReferenceAsset(ValidationModel):
    asset_id: str
    source_id: str
    label: str
    citation_text: str
    figure_table_equation: str | None = None
    local_asset_path: str | None = None
    digitised_series_id: str | None = None
    rights_provenance_note: str
    transformation_metadata: tuple[str, ...] = ()
    comparison_suitability: Literal["suitable", "context_only", "blocked", "not_assessed"]
    missing_input_notes: tuple[str, ...] = ()


class ValidationSeries(ValidationModel):
    series_id: str
    label: str
    quantity: str
    units: str
    time_basis: str
    ticks: tuple[int, ...]
    values: tuple[float, ...]
    evidence_source: EvidenceSource
    aggregation_window_ticks: int | None = None
    counting_basis: str | None = None
    boundary_direction: str | None = None

    @model_validator(mode="after")
    def validate_lengths(self) -> "ValidationSeries":
        if len(self.ticks) != len(self.values):
            raise ValueError("validation series ticks and values must have equal length")
        return self


class ScalarExpectation(ValidationModel):
    scalar_id: str
    label: str
    value: float | str | bool
    units: str | None
    evidence_source: EvidenceSource


class MetricDefinition(ValidationModel):
    metric_id: str
    label: str
    comparison: Literal["max_absolute_error", "absolute_error", "exact_sequence", "exact_boolean"]
    expected_id: str
    tolerance: float
    units: str
    tolerance_justification: str


class MetricResult(ValidationModel):
    metric_id: str
    value: float
    tolerance: float
    units: str
    passed: bool
    explanation: str


class ValidationOverlay(ValidationModel):
    overlay_id: str
    kind: Literal["relevant_link", "queued_region", "blocked_boundary", "reference_wave", "event_marker", "released_storage"]
    label: str
    link_id: str | None = None
    boundary_id: str | None = None
    active_from_tick: int
    active_through_tick: int
    direction: Literal["forward", "backward", "none"] = "none"
    evidence_source: EvidenceSource
    note: str


class PacketWaitExplanation(ValidationModel):
    packet_id: str
    active_from_tick: int
    active_through_tick: int
    current_link_id: str | None
    fifo_position: int | None
    head_packet_id: str | None
    intended_movement: str | None
    blocking_reason: str | None
    receiving_supply_packets: int | None
    signal_or_governance_constraint: str | None
    expected_next_release_tick: int | None
    evidence_sources: tuple[EvidenceSource, ...]
    unavailable_fields: tuple[str, ...] = ()


class ValidationCase(ValidationModel):
    schema_version: Literal["uc.validation.case.v1"] = VALIDATION_CASE_CONTRACT_VERSION
    case_id: str
    version: str
    group_id: str
    title: str
    short_explanation: str
    claim_ids: tuple[str, ...]
    evidence_class: EvidenceClass
    citations: tuple[Citation, ...]
    reference_assets: tuple[ReferenceAsset, ...] = ()
    input_completeness: InputCompleteness
    comparison_status: ComparisonStatus
    topology_reference: str
    profile_reference: str
    demand_reference: str
    route_sequences: tuple[tuple[str, ...], ...]
    tick_duration_seconds: float = Field(gt=0)
    initial_state_reference: str
    expected_physical_sequence: tuple[str, ...]
    expected_result_summary: str
    why_it_matters: str
    limits_on_interpretation: tuple[str, ...]
    expected_series: tuple[ValidationSeries, ...]
    expected_scalars: tuple[ScalarExpectation, ...]
    metrics: tuple[MetricDefinition, ...]
    overlays: tuple[ValidationOverlay, ...]
    known_model_differences: tuple[str, ...]
    safe_claim: str
    provenance: tuple[str, ...]
    reproducibility_notes: tuple[str, ...]
    default_final_tick: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_independent_expectations(self) -> "ValidationCase":
        if any(series.evidence_source != EvidenceSource.ANALYTICAL_REFERENCE for series in self.expected_series):
            raise ValueError("expected case series must be analytical/reference evidence")
        return self


class ValidationResult(ValidationModel):
    schema_version: Literal["uc.validation.result.v1"] = VALIDATION_RESULT_CONTRACT_VERSION
    result_id: str
    case_id: str
    case_version: str
    status: ValidationStatus
    lifecycle: tuple[ValidationLifecycle, ...]
    created_at: str
    completed_at: str | None
    code_commit: str | None
    configuration_hash: str
    expected_evidence_hash: str
    replay_run_id: str | None
    observed_series: tuple[ValidationSeries, ...]
    observed_scalars: tuple[ScalarExpectation, ...]
    difference_series: tuple[ValidationSeries, ...]
    metric_results: tuple[MetricResult, ...]
    headline_metric: str
    observed_result_summary: str
    difference_summary: str
    packet_wait_explanations: tuple[PacketWaitExplanation, ...] = ()
    stop_reason: str | None = None
    linked_issue: str | None = None
    linked_fix_commit: str | None = None
    provenance: tuple[str, ...] = ()


class ValidationRunStatus(ValidationModel):
    result_id: str
    case_id: str
    lifecycle: ValidationLifecycle
    physical_tick: int
    final_tick: int
    detail: str
    terminal: bool


class ValidationLibraryRecord(ValidationModel):
    case: ValidationCase
    latest_result: ValidationResult | None
    history_count: int


class ValidationRunCommand(ValidationModel):
    schema_version: Literal["uc.validation.control.v1"] = "uc.validation.control.v1"
    command_id: str
    action: Literal["cancel"]
