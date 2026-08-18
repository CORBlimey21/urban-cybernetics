"""Immutable schemas and deterministic identities for network compilation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from enum import Enum
from typing import Mapping, Self


COMPILER_VERSION = "uc-network-compiler-v0.4.0"
SOURCE_SCHEMA_VERSION = "uc.osm-like-source-network.v1"
NORMALIZED_SCHEMA_VERSION = "uc.normalized-source-network.v1"
EVIDENCE_BUNDLE_SCHEMA_VERSION = "uc.compiler-evidence-bundle.v2"
RULESET_VERSION = "uc.network-resolution-rules.v4"
PHYSICAL_DERIVATION_SCHEMA_VERSION = "uc.physical-derivation.v1"
EXECUTABLE_SEMANTIC_SCHEMA_VERSION = "uc.executable-network-semantics.v1"
DISCRETIZATION_POLICY_VERSION = "uc.loader-discretization.v1"

ROUND_NONE = "none"
ROUND_CEIL = "ceil"
ROUND_FLOOR = "floor"
ROUND_FLOOR_MIN_ONE = "floor_then_minimum_one"
ROUND_CEIL_MIN_ONE = "ceil_then_minimum_one"
ROUNDING_POLICIES = frozenset(
    (ROUND_NONE, ROUND_CEIL, ROUND_FLOOR, ROUND_FLOOR_MIN_ONE, ROUND_CEIL_MIN_ONE)
)


def canonical_json(value: object) -> str:
    """Return the one JSON encoding used for compiler identity."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_hash(domain: str, value: object) -> str:
    """Hash a domain-separated canonical JSON value."""

    payload = {"domain": domain, "value": value}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _json_value(serialised: str | None) -> object | None:
    return None if serialised is None else json.loads(serialised)


def _require_non_empty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class SourceField:
    """One retained raw source field with stable field identity."""

    evidence_id: str
    name: str
    raw_value_json: str

    def __post_init__(self) -> None:
        _require_non_empty(self.evidence_id, "source field evidence_id")
        _require_non_empty(self.name, "source field name")
        try:
            canonical = canonical_json(json.loads(self.raw_value_json))
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"raw_value_json must contain valid JSON: {exc}") from exc
        object.__setattr__(self, "raw_value_json", canonical)

    @classmethod
    def create(cls, evidence_id: str, name: str, raw_value: object) -> Self:
        return cls(evidence_id, name, canonical_json(raw_value))

    @property
    def raw_value(self) -> object:
        return json.loads(self.raw_value_json)

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "name": self.name,
            "raw_value": self.raw_value,
        }


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """One OSM-like record; values remain raw and may conflict or be malformed."""

    evidence_id: str
    record_type: str
    source_id: str
    fields: tuple[SourceField, ...]

    def __post_init__(self) -> None:
        for name in ("evidence_id", "record_type", "source_id"):
            _require_non_empty(getattr(self, name), f"source record {name}")
        if not isinstance(self.fields, tuple) or any(
            not isinstance(item, SourceField) for item in self.fields
        ):
            raise TypeError("source record fields must be a tuple of SourceField")

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "record_type": self.record_type,
            "source_id": self.source_id,
            "fields": [
                item.to_dict()
                for item in sorted(
                    self.fields,
                    key=lambda value: (value.name, value.evidence_id, value.raw_value_json),
                )
            ],
        }


@dataclass(frozen=True, slots=True)
class SourceNetworkEvidence:
    """Immutable source evidence before normalization or interpretation."""

    network_id: str
    records: tuple[SourceRecord, ...]
    schema_version: str = SOURCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(self.network_id, "network_id")
        if self.schema_version != SOURCE_SCHEMA_VERSION:
            raise ValueError(f"unsupported source schema: {self.schema_version}")
        if not isinstance(self.records, tuple) or any(
            not isinstance(item, SourceRecord) for item in self.records
        ):
            raise TypeError("source records must be a tuple of SourceRecord")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "network_id": self.network_id,
            "records": [
                item.to_dict()
                for item in sorted(
                    self.records,
                    key=lambda value: (
                        value.record_type,
                        value.source_id,
                        value.evidence_id,
                    ),
                )
            ],
        }

    @property
    def evidence_hash(self) -> str:
        return stable_hash("source-evidence", self.to_dict())


@dataclass(frozen=True, slots=True)
class NormalizedField:
    """Raw evidence plus its deterministic, non-authoritative parse result."""

    evidence_id: str
    name: str
    raw_value_json: str
    normalized_value_json: str | None
    parse_status: str
    parse_note: str = ""

    def __post_init__(self) -> None:
        if self.parse_status not in ("valid", "malformed", "unsupported"):
            raise ValueError(f"unsupported parse_status: {self.parse_status}")
        canonical_json(json.loads(self.raw_value_json))
        if self.normalized_value_json is not None:
            canonical_json(json.loads(self.normalized_value_json))

    @property
    def raw_value(self) -> object:
        return json.loads(self.raw_value_json)

    @property
    def normalized_value(self) -> object | None:
        return _json_value(self.normalized_value_json)

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "name": self.name,
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "parse_status": self.parse_status,
            "parse_note": self.parse_note,
        }


@dataclass(frozen=True, slots=True)
class NormalizedRecord:
    """Normalized view of one source record without mutating its evidence."""

    evidence_id: str
    record_type: str
    source_id: str
    fields: tuple[NormalizedField, ...]

    def values(self, name: str, *, valid_only: bool = True) -> tuple[NormalizedField, ...]:
        return tuple(
            item
            for item in self.fields
            if item.name == name and (not valid_only or item.parse_status == "valid")
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "record_type": self.record_type,
            "source_id": self.source_id,
            "fields": [
                item.to_dict()
                for item in sorted(
                    self.fields,
                    key=lambda value: (value.name, value.evidence_id, value.raw_value_json),
                )
            ],
        }


@dataclass(frozen=True, slots=True)
class NormalizedSourceGraph:
    """Order-independent normalized graph supplied to semantic resolution."""

    network_id: str
    source_evidence_hash: str
    records: tuple[NormalizedRecord, ...]
    schema_version: str = NORMALIZED_SCHEMA_VERSION

    def records_of_type(self, record_type: str) -> tuple[NormalizedRecord, ...]:
        return tuple(item for item in self.records if item.record_type == record_type)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "network_id": self.network_id,
            "source_evidence_hash": self.source_evidence_hash,
            "records": [
                item.to_dict()
                for item in sorted(
                    self.records,
                    key=lambda value: (
                        value.record_type,
                        value.source_id,
                        value.evidence_id,
                    ),
                )
            ],
        }

    @property
    def normalized_hash(self) -> str:
        return stable_hash("normalized-source-graph", self.to_dict())


class ProvenanceClass(str, Enum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    DEFAULTED = "defaulted"
    OVERRIDDEN = "overridden"
    SYNTHETIC_EXPERIMENT = "synthetic_experiment"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    """Field-level explanation for one resolved or unresolved semantic value."""

    artifact_id: str
    field_path: str
    classification: ProvenanceClass
    resolved_value_json: str | None
    evidence_refs: tuple[str, ...]
    source_field: str | None
    source_value_json: str | None
    rule_id: str
    rule_version: str
    confidence_class: str
    reason: str
    compiler_version: str
    compiler_configuration_hash: str
    override_id: str | None = None
    prior_value_json: str | None = None
    record_hash: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.classification, ProvenanceClass):
            object.__setattr__(self, "classification", ProvenanceClass(self.classification))
        expected = stable_hash("field-provenance", self._hash_payload())
        if self.record_hash and self.record_hash != expected:
            raise EvidenceBundleIntegrityError(
                f"provenance record hash mismatch for {self.artifact_id}:{self.field_path}"
            )
        object.__setattr__(self, "record_hash", expected)

    @classmethod
    def create(
        cls,
        *,
        artifact_id: str,
        field_path: str,
        classification: ProvenanceClass,
        resolved_value: object | None,
        evidence_refs: tuple[str, ...],
        source_field: str | None,
        source_value: object | None,
        rule_id: str,
        rule_version: str,
        confidence_class: str,
        reason: str,
        compiler_configuration_hash: str,
        override_id: str | None = None,
        prior_value: object | None = None,
    ) -> Self:
        return cls(
            artifact_id=artifact_id,
            field_path=field_path,
            classification=classification,
            resolved_value_json=(
                None if resolved_value is None else canonical_json(resolved_value)
            ),
            evidence_refs=tuple(sorted(evidence_refs)),
            source_field=source_field,
            source_value_json=(None if source_value is None else canonical_json(source_value)),
            rule_id=rule_id,
            rule_version=rule_version,
            confidence_class=confidence_class,
            reason=reason,
            compiler_version=COMPILER_VERSION,
            compiler_configuration_hash=compiler_configuration_hash,
            override_id=override_id,
            prior_value_json=(None if prior_value is None else canonical_json(prior_value)),
        )

    @property
    def resolved_value(self) -> object | None:
        return _json_value(self.resolved_value_json)

    def _hash_payload(self) -> dict[str, object]:
        return {
            field.name: (
                getattr(self, field.name).value
                if isinstance(getattr(self, field.name), Enum)
                else getattr(self, field.name)
            )
            for field in fields(self)
            if field.name != "record_hash"
        }

    def to_dict(self) -> dict[str, object]:
        payload = self._hash_payload()
        payload.pop("resolved_value_json")
        payload.pop("source_value_json")
        payload.pop("prior_value_json")
        payload["classification"] = self.classification.value
        payload["evidence_refs"] = list(self.evidence_refs)
        payload["resolved_value"] = _json_value(self.resolved_value_json)
        payload["source_value"] = _json_value(self.source_value_json)
        payload["prior_value"] = _json_value(self.prior_value_json)
        payload["record_hash"] = self.record_hash
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            artifact_id=str(payload["artifact_id"]),
            field_path=str(payload["field_path"]),
            classification=ProvenanceClass(str(payload["classification"])),
            resolved_value_json=(
                None
                if payload.get("resolved_value") is None
                else canonical_json(payload["resolved_value"])
            ),
            evidence_refs=tuple(str(item) for item in payload.get("evidence_refs", [])),
            source_field=(
                None if payload.get("source_field") is None else str(payload["source_field"])
            ),
            source_value_json=(
                None
                if payload.get("source_value") is None
                else canonical_json(payload["source_value"])
            ),
            rule_id=str(payload["rule_id"]),
            rule_version=str(payload["rule_version"]),
            confidence_class=str(payload["confidence_class"]),
            reason=str(payload["reason"]),
            compiler_version=str(payload["compiler_version"]),
            compiler_configuration_hash=str(payload["compiler_configuration_hash"]),
            override_id=(
                None if payload.get("override_id") is None else str(payload["override_id"])
            ),
            prior_value_json=(
                None
                if payload.get("prior_value") is None
                else canonical_json(payload["prior_value"])
            ),
            record_hash=str(payload.get("record_hash", "")),
        )


@dataclass(frozen=True, slots=True)
class PhysicalDerivationRecord:
    """Unit-explicit continuous-to-executable physical derivation evidence."""

    artifact_id: str
    target_field: str
    source_value_json: str | None
    source_unit: str
    normalized_value_json: str
    normalized_unit: str
    executable_value_json: str
    executable_unit: str
    formula_id: str
    formula_version: str
    rounding_policy: str
    lower_clamp_json: str | None
    upper_clamp_json: str | None
    tick_duration_seconds: float | None
    reason: str
    absolute_discretization_error: float | None = None
    relative_discretization_error: float | None = None
    clamp_activated: bool = False
    schema_version: str = PHYSICAL_DERIVATION_SCHEMA_VERSION
    derivation_hash: str = ""

    def __post_init__(self) -> None:
        for name in (
            "artifact_id",
            "target_field",
            "source_unit",
            "normalized_unit",
            "executable_unit",
            "formula_id",
            "formula_version",
            "reason",
        ):
            _require_non_empty(getattr(self, name), f"derivation {name}")
        if self.schema_version != PHYSICAL_DERIVATION_SCHEMA_VERSION:
            raise EvidenceBundleIntegrityError(
                f"unsupported physical derivation schema: {self.schema_version}"
            )
        if self.rounding_policy not in ROUNDING_POLICIES:
            raise ValueError(f"unsupported rounding policy: {self.rounding_policy}")
        if self.tick_duration_seconds is not None and self.tick_duration_seconds <= 0:
            raise ValueError("derivation tick_duration_seconds must be positive")
        for name in (
            "source_value_json",
            "normalized_value_json",
            "executable_value_json",
            "lower_clamp_json",
            "upper_clamp_json",
        ):
            serialised = getattr(self, name)
            if serialised is not None:
                object.__setattr__(self, name, canonical_json(json.loads(serialised)))
        for name in (
            "absolute_discretization_error",
            "relative_discretization_error",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")
        expected = stable_hash("physical-derivation", self._hash_payload())
        if self.derivation_hash and self.derivation_hash != expected:
            raise EvidenceBundleIntegrityError(
                f"physical derivation hash mismatch for {self.artifact_id}:{self.target_field}"
            )
        object.__setattr__(self, "derivation_hash", expected)

    @classmethod
    def create(
        cls,
        *,
        artifact_id: str,
        target_field: str,
        source_value: object | None,
        source_unit: str,
        normalized_value: object,
        normalized_unit: str,
        executable_value: object,
        executable_unit: str,
        formula_id: str,
        formula_version: str,
        rounding_policy: str,
        lower_clamp: object | None = None,
        upper_clamp: object | None = None,
        tick_duration_seconds: float | None = None,
        reason: str,
        absolute_discretization_error: float | None = None,
        relative_discretization_error: float | None = None,
        clamp_activated: bool = False,
    ) -> Self:
        return cls(
            artifact_id=artifact_id,
            target_field=target_field,
            source_value_json=(
                None if source_value is None else canonical_json(source_value)
            ),
            source_unit=source_unit,
            normalized_value_json=canonical_json(normalized_value),
            normalized_unit=normalized_unit,
            executable_value_json=canonical_json(executable_value),
            executable_unit=executable_unit,
            formula_id=formula_id,
            formula_version=formula_version,
            rounding_policy=rounding_policy,
            lower_clamp_json=(
                None if lower_clamp is None else canonical_json(lower_clamp)
            ),
            upper_clamp_json=(
                None if upper_clamp is None else canonical_json(upper_clamp)
            ),
            tick_duration_seconds=tick_duration_seconds,
            reason=reason,
            absolute_discretization_error=absolute_discretization_error,
            relative_discretization_error=relative_discretization_error,
            clamp_activated=clamp_activated,
        )

    @property
    def source_value(self) -> object | None:
        return _json_value(self.source_value_json)

    @property
    def normalized_value(self) -> object:
        return json.loads(self.normalized_value_json)

    @property
    def executable_value(self) -> object:
        return json.loads(self.executable_value_json)

    def _hash_payload(self) -> dict[str, object]:
        return {
            field.name: getattr(self, field.name)
            for field in fields(self)
            if field.name != "derivation_hash"
        }

    def semantic_payload(self) -> dict[str, object]:
        """Return only behaviour-relevant unit and discretisation semantics."""

        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "target_field": self.target_field,
            "normalized_value": self.normalized_value,
            "normalized_unit": self.normalized_unit,
            "executable_value": self.executable_value,
            "executable_unit": self.executable_unit,
            "rounding_policy": self.rounding_policy,
            "lower_clamp": _json_value(self.lower_clamp_json),
            "upper_clamp": _json_value(self.upper_clamp_json),
            "tick_duration_seconds": self.tick_duration_seconds,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self.semantic_payload(),
            "source_value": self.source_value,
            "source_unit": self.source_unit,
            "formula_id": self.formula_id,
            "formula_version": self.formula_version,
            "reason": self.reason,
            "absolute_discretization_error": self.absolute_discretization_error,
            "relative_discretization_error": self.relative_discretization_error,
            "clamp_activated": self.clamp_activated,
            "derivation_hash": self.derivation_hash,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            artifact_id=str(payload["artifact_id"]),
            target_field=str(payload["target_field"]),
            source_value_json=(
                None
                if payload.get("source_value") is None
                else canonical_json(payload["source_value"])
            ),
            source_unit=str(payload["source_unit"]),
            normalized_value_json=canonical_json(payload["normalized_value"]),
            normalized_unit=str(payload["normalized_unit"]),
            executable_value_json=canonical_json(payload["executable_value"]),
            executable_unit=str(payload["executable_unit"]),
            formula_id=str(payload["formula_id"]),
            formula_version=str(payload["formula_version"]),
            rounding_policy=str(payload["rounding_policy"]),
            lower_clamp_json=(
                None
                if payload.get("lower_clamp") is None
                else canonical_json(payload["lower_clamp"])
            ),
            upper_clamp_json=(
                None
                if payload.get("upper_clamp") is None
                else canonical_json(payload["upper_clamp"])
            ),
            tick_duration_seconds=(
                None
                if payload.get("tick_duration_seconds") is None
                else float(payload["tick_duration_seconds"])
            ),
            reason=str(payload["reason"]),
            absolute_discretization_error=(
                None
                if payload.get("absolute_discretization_error") is None
                else float(payload["absolute_discretization_error"])
            ),
            relative_discretization_error=(
                None
                if payload.get("relative_discretization_error") is None
                else float(payload["relative_discretization_error"])
            ),
            clamp_activated=bool(payload.get("clamp_activated", False)),
            schema_version=str(payload["schema_version"]),
            derivation_hash=str(payload.get("derivation_hash", "")),
        )


class DiagnosticSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    UNRESOLVED = "unresolved"
    STRUCTURAL = "structural_error"
    INTERNAL = "internal_consistency_error"
    REFUSAL = "refusal"


@dataclass(frozen=True, slots=True)
class CompilerDiagnostic:
    """Stable compiler diagnostic with machine-readable severity and code."""

    severity: DiagnosticSeverity
    code: str
    message: str
    artifact_id: str | None = None
    field_path: str | None = None
    evidence_refs: tuple[str, ...] = ()
    diagnostic_hash: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.severity, DiagnosticSeverity):
            object.__setattr__(self, "severity", DiagnosticSeverity(self.severity))
        expected = stable_hash("compiler-diagnostic", self._hash_payload())
        if self.diagnostic_hash and self.diagnostic_hash != expected:
            raise EvidenceBundleIntegrityError(
                f"diagnostic hash mismatch for {self.code}:{self.artifact_id}"
            )
        object.__setattr__(self, "diagnostic_hash", expected)

    def _hash_payload(self) -> dict[str, object]:
        return {
            "compiler_version": COMPILER_VERSION,
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "artifact_id": self.artifact_id,
            "field_path": self.field_path,
            "evidence_refs": list(self.evidence_refs),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._hash_payload(), "diagnostic_hash": self.diagnostic_hash}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            severity=DiagnosticSeverity(str(payload["severity"])),
            code=str(payload["code"]),
            message=str(payload["message"]),
            artifact_id=(
                None if payload.get("artifact_id") is None else str(payload["artifact_id"])
            ),
            field_path=(
                None if payload.get("field_path") is None else str(payload["field_path"])
            ),
            evidence_refs=tuple(str(item) for item in payload.get("evidence_refs", [])),
            diagnostic_hash=str(payload.get("diagnostic_hash", "")),
        )


@dataclass(frozen=True, slots=True)
class CompilerOverride:
    """Immutable compiler-time override; never a runtime control command."""

    override_id: str
    target_artifact_id: str
    target_field: str
    replacement_value_json: str
    actor: str
    source: str
    reason: str
    precedence: int = 0

    def __post_init__(self) -> None:
        for name in (
            "override_id",
            "target_artifact_id",
            "target_field",
            "actor",
            "source",
            "reason",
        ):
            _require_non_empty(getattr(self, name), f"override {name}")
        if isinstance(self.precedence, bool) or not isinstance(self.precedence, int):
            raise TypeError("override precedence must be an integer")
        object.__setattr__(
            self,
            "replacement_value_json",
            canonical_json(json.loads(self.replacement_value_json)),
        )

    @classmethod
    def create(
        cls,
        *,
        override_id: str,
        target_artifact_id: str,
        target_field: str,
        replacement_value: object,
        actor: str,
        source: str,
        reason: str,
        precedence: int = 0,
    ) -> Self:
        return cls(
            override_id,
            target_artifact_id,
            target_field,
            canonical_json(replacement_value),
            actor,
            source,
            reason,
            precedence,
        )

    @property
    def replacement_value(self) -> object:
        return json.loads(self.replacement_value_json)

    def to_dict(self) -> dict[str, object]:
        return {
            "override_id": self.override_id,
            "target_artifact_id": self.target_artifact_id,
            "target_field": self.target_field,
            "replacement_value": self.replacement_value,
            "actor": self.actor,
            "source": self.source,
            "reason": self.reason,
            "precedence": self.precedence,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls.create(
            override_id=str(payload["override_id"]),
            target_artifact_id=str(payload["target_artifact_id"]),
            target_field=str(payload["target_field"]),
            replacement_value=payload["replacement_value"],
            actor=str(payload["actor"]),
            source=str(payload["source"]),
            reason=str(payload["reason"]),
            precedence=int(payload.get("precedence", 0)),
        )


@dataclass(frozen=True, slots=True)
class CompilerConfig:
    """Versioned, hash-bound policy for all permitted compiler assumptions."""

    allow_road_class_defaults: bool = True
    allow_conservative_shared_lane_fallback: bool = True
    enable_explicit_lane_group_partitions: bool = True
    allow_default_signal_plans: bool = False
    allow_jam_density_default: bool = True
    allow_backward_wave_speed_default: bool = True
    tick_duration_seconds: float = 1.0
    lane_defaults: tuple[tuple[str, int], ...] = (
        ("primary", 1),
        ("secondary", 1),
        ("residential", 1),
        ("service", 1),
    )
    speed_kph_defaults: tuple[tuple[str, float], ...] = (
        ("primary", 50.0),
        ("secondary", 40.0),
        ("residential", 30.0),
        ("service", 20.0),
    )
    capacity_per_lane_defaults: tuple[tuple[str, float], ...] = (
        ("primary", 1800.0),
        ("secondary", 1500.0),
        ("residential", 1200.0),
        ("service", 900.0),
    )
    jam_density_veh_per_km_per_lane_default: float = 150.0
    backward_wave_speed_mps_default: float = 5.0
    default_signal_cycle_ticks: int = 4
    discretization_relative_error_warning_threshold: float = 0.25
    schema_version: str = "uc.network-compiler-config.v1"

    def __post_init__(self) -> None:
        if self.tick_duration_seconds <= 0:
            raise ValueError("tick_duration_seconds must be positive")
        if self.jam_density_veh_per_km_per_lane_default <= 0:
            raise ValueError("jam density default must be positive")
        if self.backward_wave_speed_mps_default <= 0:
            raise ValueError("backward wave speed default must be positive")
        if self.default_signal_cycle_ticks <= 0:
            raise ValueError("default signal cycle must be positive")
        if self.discretization_relative_error_warning_threshold < 0:
            raise ValueError("discretization warning threshold must be non-negative")
        for table_name in (
            "lane_defaults",
            "speed_kph_defaults",
            "capacity_per_lane_defaults",
        ):
            table = getattr(self, table_name)
            keys = tuple(item[0] for item in table)
            if len(keys) != len(set(keys)):
                raise ValueError(f"{table_name} contains duplicate road classes")
            object.__setattr__(self, table_name, tuple(sorted(table)))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "allow_road_class_defaults": self.allow_road_class_defaults,
            "allow_conservative_shared_lane_fallback": (
                self.allow_conservative_shared_lane_fallback
            ),
            "enable_explicit_lane_group_partitions": (
                self.enable_explicit_lane_group_partitions
            ),
            "allow_default_signal_plans": self.allow_default_signal_plans,
            "allow_jam_density_default": self.allow_jam_density_default,
            "allow_backward_wave_speed_default": (
                self.allow_backward_wave_speed_default
            ),
            "tick_duration_seconds": self.tick_duration_seconds,
            "lane_defaults": [list(item) for item in self.lane_defaults],
            "speed_kph_defaults": [list(item) for item in self.speed_kph_defaults],
            "capacity_per_lane_defaults": [
                list(item) for item in self.capacity_per_lane_defaults
            ],
            "jam_density_veh_per_km_per_lane_default": (
                self.jam_density_veh_per_km_per_lane_default
            ),
            "backward_wave_speed_mps_default": self.backward_wave_speed_mps_default,
            "default_signal_cycle_ticks": self.default_signal_cycle_ticks,
            "discretization_relative_error_warning_threshold": (
                self.discretization_relative_error_warning_threshold
            ),
        }

    @property
    def config_hash(self) -> str:
        return stable_hash("compiler-configuration", self.to_dict())


@dataclass(frozen=True, slots=True)
class ResolutionRule:
    rule_id: str
    version: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {
            "rule_id": self.rule_id,
            "version": self.version,
            "description": self.description,
        }


RULES: tuple[ResolutionRule, ...] = (
    ResolutionRule("link.identity.observed", "1", "Retain stable source identity and endpoints."),
    ResolutionRule("link.direction.observed", "1", "Use an explicit permitted directed-arc direction."),
    ResolutionRule("link.length.observed", "1", "Use one valid observed metric length."),
    ResolutionRule("link.length.geometry-derived", "1", "Derive metric polyline length from ordered OSM WGS84 node coordinates using the versioned Haversine formula."),
    ResolutionRule("link.lanes.observed", "1", "Use one valid observed directional lane count."),
    ResolutionRule("link.lanes.directional-from-total", "1", "Split an even total lane count across a two-way road."),
    ResolutionRule("link.lanes.road-class-default", "1", "Use the configured road-class lane default."),
    ResolutionRule("link.speed.observed", "1", "Use one valid observed maximum speed."),
    ResolutionRule("link.speed.road-class-default", "1", "Use the configured road-class speed default."),
    ResolutionRule("link.capacity.observed", "1", "Use one valid observed per-lane capacity."),
    ResolutionRule("link.capacity.from-total", "1", "Divide observed total capacity by resolved lanes."),
    ResolutionRule("link.capacity.road-class-default", "1", "Use the configured road-class capacity default."),
    ResolutionRule("link.storage.observed-or-default", "1", "Use observed or configured jam density and wave speed."),
    ResolutionRule("link.loading-parameters.derived", "2", "Retain unit-explicit continuous physics and derive loader-compatible lag, storage, and integer per-tick capacities with named rounding and clamp policies."),
    ResolutionRule("movement.identity.topology", "1", "Derive movement identity and continuity from resolved directed topology."),
    ResolutionRule("movement.priority.default", "1", "Use the declared v1 unit movement priority when no priority evidence exists."),
    ResolutionRule("movement.permission.observed", "1", "Apply one explicit turn permission or prohibition."),
    ResolutionRule("movement.permission.synthetic-experiment", "1", "Apply one explicit synthetic experimental turn declaration without treating it as source observation."),
    ResolutionRule("movement.permission.topology", "1", "Infer a legal continuous movement absent a restriction."),
    ResolutionRule("lane-group.explicit", "1", "Compile an explicit lane-group declaration."),
    ResolutionRule("lane-group.synthetic-experiment", "1", "Compile an explicit synthetic experimental queue partition."),
    ResolutionRule("lane-group.from-lane-index", "1", "Infer groups only from complete, valid lane-index evidence."),
    ResolutionRule("lane-group.shared-fallback", "1", "Use one conservative shared approach resource."),
    ResolutionRule("signal.explicit-fixed-time", "1", "Compile complete observed fixed-time timing."),
    ResolutionRule("signal.synthetic-experiment", "1", "Compile complete synthetic experimental timing without treating it as observed control data."),
    ResolutionRule("signal.configured-default", "1", "Build a deterministic default only when configuration permits."),
    ResolutionRule("signal.osm-observation-unresolved", "1", "Retain OSM signal-head evidence and refuse control-plan execution until controller ownership, movement assignment, and timing are supplied."),
    ResolutionRule("compiler.override", "1", "Apply the unique highest-precedence immutable compiler override."),
    ResolutionRule("compiler.unresolved", "1", "Refuse unresolved mandatory executable semantics."),
)


class CompilationDisposition(str, Enum):
    EXECUTABLE = "executable"
    EXECUTABLE_WITH_WARNINGS = "executable_with_warnings_or_defaults"
    UNRESOLVED = "unresolved_non_executable"
    STRUCTURALLY_INVALID = "structurally_invalid_source"
    INTERNALLY_INCONSISTENT = "internally_inconsistent_resolved_output"


class EvidenceBundleIntegrityError(ValueError):
    """Raised when serialized compiler evidence no longer matches its hashes."""


@dataclass(frozen=True, slots=True)
class CompilerEvidenceBundle:
    """Serializable, hash-sealed evidence for one complete compiler result."""

    input_evidence_hash: str
    normalized_evidence_hash: str
    compiler_configuration_json: str
    compiler_configuration_hash: str
    ruleset_version: str
    ruleset: tuple[ResolutionRule, ...]
    ruleset_hash: str
    canonical_topology_artifact_hash: str | None
    executable_topology_hash: str | None
    executable_semantic_hash: str | None
    signal_plan_hashes: tuple[tuple[str, str], ...]
    lane_group_hashes: tuple[tuple[str, str], ...]
    derivations: tuple[PhysicalDerivationRecord, ...]
    provenance: tuple[ProvenanceRecord, ...]
    diagnostics: tuple[CompilerDiagnostic, ...]
    unresolved_items: tuple[str, ...]
    overrides: tuple[CompilerOverride, ...]
    disposition: CompilationDisposition
    normalized_source_json: str
    executable_artifacts_json: str | None
    compiler_version: str = COMPILER_VERSION
    source_schema_version: str = SOURCE_SCHEMA_VERSION
    schema_version: str = EVIDENCE_BUNDLE_SCHEMA_VERSION
    derivation_bundle_hash: str = ""
    provenance_bundle_hash: str = ""
    diagnostics_bundle_hash: str = ""
    compilation_identity_hash: str = ""
    evidence_bundle_hash: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != EVIDENCE_BUNDLE_SCHEMA_VERSION:
            raise EvidenceBundleIntegrityError(
                f"unsupported evidence bundle schema: {self.schema_version}"
            )
        if self.compiler_version != COMPILER_VERSION:
            raise EvidenceBundleIntegrityError(
                f"unsupported compiler version: {self.compiler_version}"
            )
        if self.source_schema_version != SOURCE_SCHEMA_VERSION:
            raise EvidenceBundleIntegrityError(
                f"unsupported source schema: {self.source_schema_version}"
            )
        if not isinstance(self.disposition, CompilationDisposition):
            object.__setattr__(self, "disposition", CompilationDisposition(self.disposition))
        expected_configuration = stable_hash(
            "compiler-configuration", json.loads(self.compiler_configuration_json)
        )
        if self.compiler_configuration_hash != expected_configuration:
            raise EvidenceBundleIntegrityError("compiler_configuration_hash mismatch")
        expected_ruleset = stable_hash(
            "resolution-ruleset",
            {
                "ruleset_version": self.ruleset_version,
                "rules": [item.to_dict() for item in self.ruleset],
            },
        )
        if self.ruleset_hash != expected_ruleset:
            raise EvidenceBundleIntegrityError("ruleset_hash mismatch")
        expected_normalized = stable_hash(
            "normalized-source-graph", json.loads(self.normalized_source_json)
        )
        if self.normalized_evidence_hash != expected_normalized:
            raise EvidenceBundleIntegrityError("normalized_evidence_hash mismatch")
        successful = self.disposition in (
            CompilationDisposition.EXECUTABLE,
            CompilationDisposition.EXECUTABLE_WITH_WARNINGS,
        )
        if successful != (self.executable_artifacts_json is not None):
            raise EvidenceBundleIntegrityError(
                "successful disposition must be equivalent to executable artifact presence"
            )
        if self.executable_artifacts_json is not None:
            artifacts = json.loads(self.executable_artifacts_json)
            topology_payload = artifacts.get("executable_topology_payload")
            semantic_payload = artifacts.get("executable_semantic_payload")
            if not isinstance(topology_payload, dict) or not isinstance(
                semantic_payload, dict
            ):
                raise EvidenceBundleIntegrityError(
                    "executable semantic payloads must be JSON objects"
                )
            if stable_hash("executable-topology", topology_payload) != self.executable_topology_hash:
                raise EvidenceBundleIntegrityError(
                    "executable_topology_hash does not validate its semantic payload"
                )
            if (
                stable_hash("executable-network-semantics", semantic_payload)
                != self.executable_semantic_hash
            ):
                raise EvidenceBundleIntegrityError(
                    "executable_semantic_hash does not validate its semantic payload"
                )
            if (
                semantic_payload.get("executable_topology_hash")
                != self.executable_topology_hash
            ):
                raise EvidenceBundleIntegrityError(
                    "executable semantic payload references a different topology hash"
                )
            if topology_payload.get("loading_links") != artifacts.get("loading_links"):
                raise EvidenceBundleIntegrityError(
                    "executable topology payload does not match loader links"
                )
            if topology_payload.get("tick_duration_seconds") != artifacts.get(
                "tick_duration_seconds"
            ):
                raise EvidenceBundleIntegrityError(
                    "executable topology payload does not match tick duration"
                )
            expected_derivation_semantics = [
                item.semantic_payload() for item in self.derivations
            ]
            if (
                semantic_payload.get("physical_derivation_semantics")
                != expected_derivation_semantics
            ):
                raise EvidenceBundleIntegrityError(
                    "executable semantic payload does not match physical derivations"
                )
            if (
                artifacts.get("canonical_topology_artifact_hash")
                != self.canonical_topology_artifact_hash
            ):
                raise EvidenceBundleIntegrityError(
                    "canonical_topology_artifact_hash does not match executable artifacts"
                )
            if artifacts.get("executable_topology_hash") != self.executable_topology_hash:
                raise EvidenceBundleIntegrityError(
                    "executable_topology_hash does not match executable artifacts"
                )
            if artifacts.get("executable_semantic_hash") != self.executable_semantic_hash:
                raise EvidenceBundleIntegrityError(
                    "executable_semantic_hash does not match executable artifacts"
                )
            if artifacts.get("physical_derivations") != [
                item.to_dict() for item in self.derivations
            ]:
                raise EvidenceBundleIntegrityError(
                    "physical derivations do not match executable artifacts"
                )
            signal_plan = artifacts.get("signal_plan", {})
            controller_hashes = tuple(
                sorted(
                    (
                        str(item["controller_id"]),
                        str(item["semantic_hash"]),
                    )
                    for item in signal_plan.get("controllers", [])
                )
            )
            if controller_hashes != tuple(sorted(self.signal_plan_hashes)):
                raise EvidenceBundleIntegrityError(
                    "signal_plan_hashes do not match executable artifacts"
                )
            lane_payload = canonical_json(artifacts.get("lane_group_config", {}))
            lane_hash = hashlib.sha256(lane_payload.encode("utf-8")).hexdigest()
            if self.lane_group_hashes != (("lane-group-config", lane_hash),):
                raise EvidenceBundleIntegrityError(
                    "lane_group_hashes do not match executable artifacts"
                )
        elif self.executable_topology_hash is not None or self.executable_semantic_hash is not None:
            raise EvidenceBundleIntegrityError(
                "non-executable disposition cannot declare executable semantic hashes"
            )
        expected_derivations = stable_hash(
            "physical-derivation-bundle", [item.to_dict() for item in self.derivations]
        )
        expected_provenance = stable_hash(
            "provenance-bundle", [item.to_dict() for item in self.provenance]
        )
        expected_diagnostics = stable_hash(
            "diagnostics-bundle", [item.to_dict() for item in self.diagnostics]
        )
        for name, declared, expected in (
            ("derivation_bundle_hash", self.derivation_bundle_hash, expected_derivations),
            ("provenance_bundle_hash", self.provenance_bundle_hash, expected_provenance),
            ("diagnostics_bundle_hash", self.diagnostics_bundle_hash, expected_diagnostics),
        ):
            if declared and declared != expected:
                raise EvidenceBundleIntegrityError(f"{name} mismatch")
            object.__setattr__(self, name, expected)
        expected_identity = stable_hash("compilation-identity", self._result_payload())
        if self.compilation_identity_hash and self.compilation_identity_hash != expected_identity:
            raise EvidenceBundleIntegrityError("compilation_identity_hash mismatch")
        object.__setattr__(self, "compilation_identity_hash", expected_identity)
        expected_bundle = stable_hash(
            "compiler-evidence-bundle",
            {
                "result": self._result_payload(),
                "derivations": [item.to_dict() for item in self.derivations],
                "provenance": [item.to_dict() for item in self.provenance],
                "diagnostics": [item.to_dict() for item in self.diagnostics],
                "compilation_identity_hash": self.compilation_identity_hash,
            },
        )
        if self.evidence_bundle_hash and self.evidence_bundle_hash != expected_bundle:
            raise EvidenceBundleIntegrityError("evidence_bundle_hash mismatch")
        object.__setattr__(self, "evidence_bundle_hash", expected_bundle)

    @property
    def complete_result_hash(self) -> str:
        """Backward-compatible alias for the compilation audit identity."""

        return self.compilation_identity_hash

    def _result_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "compiler_version": self.compiler_version,
            "source_schema_version": self.source_schema_version,
            "input_evidence_hash": self.input_evidence_hash,
            "normalized_evidence_hash": self.normalized_evidence_hash,
            "compiler_configuration": json.loads(self.compiler_configuration_json),
            "compiler_configuration_hash": self.compiler_configuration_hash,
            "ruleset_version": self.ruleset_version,
            "ruleset": [item.to_dict() for item in self.ruleset],
            "ruleset_hash": self.ruleset_hash,
            "canonical_topology_artifact_hash": self.canonical_topology_artifact_hash,
            "executable_topology_hash": self.executable_topology_hash,
            "executable_semantic_hash": self.executable_semantic_hash,
            "signal_plan_hashes": [list(item) for item in self.signal_plan_hashes],
            "lane_group_hashes": [list(item) for item in self.lane_group_hashes],
            "derivation_bundle_hash": self.derivation_bundle_hash,
            "provenance_bundle_hash": self.provenance_bundle_hash,
            "diagnostics_bundle_hash": self.diagnostics_bundle_hash,
            "unresolved_items": list(self.unresolved_items),
            "overrides": [item.to_dict() for item in self.overrides],
            "disposition": self.disposition.value,
            "normalized_source": json.loads(self.normalized_source_json),
            "executable_artifacts": (
                None
                if self.executable_artifacts_json is None
                else json.loads(self.executable_artifacts_json)
            ),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self._result_payload(),
            "provenance": [item.to_dict() for item in self.provenance],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "derivations": [item.to_dict() for item in self.derivations],
            "compilation_identity_hash": self.compilation_identity_hash,
            "evidence_bundle_hash": self.evidence_bundle_hash,
            "complete_result_hash": self.compilation_identity_hash,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        declared_identity = payload.get("compilation_identity_hash")
        legacy_identity = payload.get("complete_result_hash")
        if (
            declared_identity is not None
            and legacy_identity is not None
            and str(declared_identity) != str(legacy_identity)
        ):
            raise EvidenceBundleIntegrityError(
                "complete_result_hash alias does not match compilation_identity_hash"
            )
        return cls(
            input_evidence_hash=str(payload["input_evidence_hash"]),
            normalized_evidence_hash=str(payload["normalized_evidence_hash"]),
            compiler_configuration_json=canonical_json(payload["compiler_configuration"]),
            compiler_configuration_hash=str(payload["compiler_configuration_hash"]),
            ruleset_version=str(payload["ruleset_version"]),
            ruleset=tuple(
                ResolutionRule(
                    str(item["rule_id"]),
                    str(item["version"]),
                    str(item["description"]),
                )
                for item in payload["ruleset"]  # type: ignore[union-attr]
            ),
            ruleset_hash=str(payload["ruleset_hash"]),
            canonical_topology_artifact_hash=(
                None
                if payload.get("canonical_topology_artifact_hash") is None
                else str(payload["canonical_topology_artifact_hash"])
            ),
            executable_topology_hash=(
                None
                if payload.get("executable_topology_hash") is None
                else str(payload["executable_topology_hash"])
            ),
            executable_semantic_hash=(
                None
                if payload.get("executable_semantic_hash") is None
                else str(payload["executable_semantic_hash"])
            ),
            signal_plan_hashes=tuple(
                (str(item[0]), str(item[1]))
                for item in payload.get("signal_plan_hashes", [])  # type: ignore[union-attr]
            ),
            lane_group_hashes=tuple(
                (str(item[0]), str(item[1]))
                for item in payload.get("lane_group_hashes", [])  # type: ignore[union-attr]
            ),
            derivations=tuple(
                PhysicalDerivationRecord.from_dict(item)
                for item in payload.get("derivations", [])  # type: ignore[union-attr]
            ),
            provenance=tuple(
                ProvenanceRecord.from_dict(item)
                for item in payload.get("provenance", [])  # type: ignore[union-attr]
            ),
            diagnostics=tuple(
                CompilerDiagnostic.from_dict(item)
                for item in payload.get("diagnostics", [])  # type: ignore[union-attr]
            ),
            unresolved_items=tuple(str(item) for item in payload.get("unresolved_items", [])),
            overrides=tuple(
                CompilerOverride.from_dict(item)
                for item in payload.get("overrides", [])  # type: ignore[union-attr]
            ),
            disposition=CompilationDisposition(str(payload["disposition"])),
            normalized_source_json=canonical_json(payload["normalized_source"]),
            executable_artifacts_json=(
                None
                if payload.get("executable_artifacts") is None
                else canonical_json(payload["executable_artifacts"])
            ),
            compiler_version=str(payload["compiler_version"]),
            source_schema_version=str(payload["source_schema_version"]),
            schema_version=str(payload["schema_version"]),
            derivation_bundle_hash=str(payload.get("derivation_bundle_hash", "")),
            provenance_bundle_hash=str(payload.get("provenance_bundle_hash", "")),
            diagnostics_bundle_hash=str(payload.get("diagnostics_bundle_hash", "")),
            compilation_identity_hash=str(
                payload.get(
                    "compilation_identity_hash",
                    payload.get("complete_result_hash", ""),
                )
            ),
            evidence_bundle_hash=str(payload.get("evidence_bundle_hash", "")),
        )

    @classmethod
    def from_json(cls, serialised: str) -> Self:
        payload = json.loads(serialised)
        if not isinstance(payload, dict):
            raise EvidenceBundleIntegrityError("evidence bundle JSON must be an object")
        return cls.from_dict(payload)
