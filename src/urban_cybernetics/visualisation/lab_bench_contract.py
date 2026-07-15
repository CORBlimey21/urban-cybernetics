"""Versioned scientific-state contracts for the Validation Workbench Lab Bench."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


LAB_WORKSHEET_VERSION = "uc.lab_bench.worksheet.v1"
LAB_ORACLE_VERSION = "uc.lab_bench.oracle.v1"


class LabModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LabState(StrEnum):
    SCRATCH = "scratch"
    CANDIDATE = "candidate_reference"
    FROZEN = "frozen_oracle"


class ProvenanceClass(StrEnum):
    USER_HAND_DERIVATION = "user_hand_derivation"
    INDEPENDENT_ARITHMETIC = "independently_encoded_arithmetic"
    PUBLISHED_SOURCE = "published_source"
    EXTERNAL_IMPLEMENTATION = "external_implementation"
    MODEL_SUGGESTION = "model_suggestion"
    UC_DERIVED = "uc_derived_ineligible_as_oracle"
    IMPORTED = "imported"
    PRESENTATION_ONLY = "presentation_only"


class ColumnKind(StrEnum):
    MANUAL = "manual"
    FORMULA = "formula_derived"
    IMPORTED = "imported"
    CASE_LINKED = "case_linked"
    UC_OBSERVED = "uc_observed"


class LabVariable(LabModel):
    variable_id: str
    label: str
    value: float | int | str | tuple[float, ...] | tuple[str, ...]
    units: str
    source: str
    evidence_classification: str
    configuration_identity: str
    linked: bool = True


class Notebook(LabModel):
    markdown: str = ""
    origin: Literal["user_authored", "imported", "deterministic_tool_output", "model_suggestion"] = "user_authored"
    linked_references: tuple[str, ...] = ()


class LabColumn(LabModel):
    column_id: str
    label: str
    units: str
    kind: ColumnKind
    provenance: ProvenanceClass
    values: tuple[float, ...] = ()
    formula: str | None = None
    source_reference: str | None = None

    @model_validator(mode="after")
    def validate_column(self) -> "LabColumn":
        if self.kind == ColumnKind.FORMULA and not self.formula:
            raise ValueError("formula-derived columns require formula text")
        if self.kind != ColumnKind.FORMULA and self.formula is not None:
            raise ValueError("only formula-derived columns may carry formula text")
        return self


class TickTable(LabModel):
    tick_start: int
    tick_end: int
    evaluation_order: Literal["ascending_tick_then_declared_column"] = "ascending_tick_then_declared_column"
    out_of_range_values: dict[str, float] = Field(default_factory=dict)
    columns: tuple[LabColumn, ...] = ()

    @model_validator(mode="after")
    def validate_range(self) -> "TickTable":
        if self.tick_end < self.tick_start:
            raise ValueError("tick_end precedes tick_start")
        if self.tick_end - self.tick_start > 500:
            raise ValueError("Lab Bench tables are limited to 501 ticks")
        ids = [column.column_id for column in self.columns]
        if len(ids) != len(set(ids)):
            raise ValueError("column IDs must be unique")
        return self


class SeriesMapping(LabModel):
    expected_column_id: str
    observed_series_id: str
    time_alignment: Literal["same_tick", "offset"] = "same_tick"
    tick_offset: int = 0
    expected_units: str
    observed_units: str
    metric: Literal["exact", "pointwise_difference", "absolute_error"] = "exact"
    tolerance: float = Field(default=0.0, ge=0)


class LabWorksheet(LabModel):
    schema_version: Literal["uc.lab_bench.worksheet.v1"] = LAB_WORKSHEET_VERSION
    worksheet_id: str
    revision: int = Field(default=0, ge=0)
    title: str
    state: Literal[LabState.SCRATCH, LabState.CANDIDATE] = LabState.SCRATCH
    case_id: str | None
    case_version: str | None
    case_configuration_hash: str | None
    detached: bool = False
    author_source: ProvenanceClass = ProvenanceClass.USER_HAND_DERIVATION
    created_at: str
    updated_at: str
    notebook: Notebook = Notebook()
    variables: tuple[LabVariable, ...] = ()
    table: TickTable = TickTable(tick_start=0, tick_end=10)
    mappings: tuple[SeriesMapping, ...] = ()
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


class EvaluationRequest(LabModel):
    expression: str
    variables: tuple[LabVariable, ...] = ()
    target_units: str | None = None


class EvaluationResult(LabModel):
    expression: str
    substituted_expression: str
    value: float | bool
    units: str
    steps: tuple[str, ...]


class TableEvaluationRequest(LabModel):
    table: TickTable
    variables: tuple[LabVariable, ...] = ()


class TableEvaluationResult(LabModel):
    table: TickTable
    dependency_order: tuple[str, ...]
    diagnostics: tuple[str, ...] = ()


class ComparisonRequest(LabModel):
    mapping: SeriesMapping
    expected_ticks: tuple[int, ...]
    expected_values: tuple[float, ...]
    observed_ticks: tuple[int, ...]
    observed_values: tuple[float, ...]
    expected_state: Literal[LabState.SCRATCH, LabState.CANDIDATE, LabState.FROZEN]


class ComparisonResult(LabModel):
    formal: bool
    label: str
    exact: bool
    differences: tuple[float, ...]
    compared_ticks: tuple[int, ...]
    maximum_absolute_error: float
    mean_absolute_error: float
    first_mismatch_tick: int | None
    tick_offset: int
    cumulative_bound_violations: int
    mismatched_rows: int
    tolerance: float


class FreezeRequest(LabModel):
    worksheet_id: str
    approval_action: str = Field(min_length=3)
    author_source: ProvenanceClass
    notes: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


class FrozenOracle(LabModel):
    schema_version: Literal["uc.lab_bench.oracle.v1"] = LAB_ORACLE_VERSION
    oracle_id: str
    version: int = Field(ge=1)
    state: Literal[LabState.FROZEN] = LabState.FROZEN
    associated_case_id: str
    associated_case_version: str
    author_source: ProvenanceClass
    created_at: str
    formula_table_provenance: tuple[str, ...]
    units: tuple[str, ...]
    tick_convention: str
    input_references: tuple[str, ...]
    detached_literal_values: dict[str, float | int | str]
    artifact_hash: str
    approval_action: str
    notes: tuple[str, ...]
    limitations: tuple[str, ...]
    source_worksheet_revision: int
    dependency_hash: str
    worksheet: LabWorksheet
