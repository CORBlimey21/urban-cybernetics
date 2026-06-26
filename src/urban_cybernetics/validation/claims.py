"""Academic LTM parity claim and evidence vocabulary.

These records label evidence; they do not validate loading mechanics.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from urban_cybernetics.config import (
    ACADEMIC_LTM_PARITY_PROFILE_ID,
    LEGACY_LOADING_PROFILE_ID,
    SUPPORTED_LOADING_PROFILE_IDS,
)


PARITY_SPEC_VERSION = "academic_ltm_parity_v1"

PARITY_CLAIM_TIERS = frozenset(
    (
        "none",
        "t0_architecture_compatible",
        "t1_link_parity",
        "t2_minimal_network_parity",
        "t3_packet_multi_commodity_parity",
    )
)

PARITY_EVIDENCE_STATUSES = frozenset(
    (
        "not_assessed",
        "not_parity_evidence",
        "passed",
        "failed",
    )
)

PARITY_FAILURE_REASONS = frozenset(
    (
        "none",
        "partial_run",
        "interrupted_run",
        "timed_out",
        "inconsistent_state",
        "unsupported_profile",
        "validation_failed",
    )
)


def parity_profile_status(model_profile_id: str) -> str:
    """Return the parity classification for a supported loading profile."""

    if model_profile_id == ACADEMIC_LTM_PARITY_PROFILE_ID:
        return "parity_eligible"
    if model_profile_id == LEGACY_LOADING_PROFILE_ID:
        return "legacy_compatible"
    raise ValueError(f"unsupported loading profile: {model_profile_id}")


@dataclass(frozen=True, slots=True)
class ParityEvidenceContract:
    """Frozen description of the evidence contract used to label a run."""

    contract_id: str
    spec_version: str = PARITY_SPEC_VERSION
    required_model_profile_id: str = ACADEMIC_LTM_PARITY_PROFILE_ID
    accepted_claim_tiers: tuple[str, ...] = (
        "t0_architecture_compatible",
        "t1_link_parity",
        "t2_minimal_network_parity",
        "t3_packet_multi_commodity_parity",
    )
    failure_statuses: tuple[str, ...] = (
        "not_parity_evidence",
        "failed",
    )

    def __post_init__(self) -> None:
        _require_non_empty(self.contract_id, "contract_id")
        _require_non_empty(self.spec_version, "spec_version")
        _validate_profile_id(self.required_model_profile_id)
        object.__setattr__(
            self,
            "accepted_claim_tiers",
            _normalise_allowed_tuple(
                self.accepted_claim_tiers,
                "accepted_claim_tiers",
                PARITY_CLAIM_TIERS - {"none"},
            ),
        )
        object.__setattr__(
            self,
            "failure_statuses",
            _normalise_allowed_tuple(
                self.failure_statuses,
                "failure_statuses",
                PARITY_EVIDENCE_STATUSES - {"not_assessed", "passed"},
            ),
        )


@dataclass(frozen=True, slots=True)
class ParityRunEvidence:
    """Frozen parity-evidence label for one run summary."""

    run_id: str
    claim_tier: str
    model_profile_id: str
    evidence_status: str
    failure_reason: str = "none"
    contract_id: str = "academic-ltm-parity-v1"
    spec_version: str = PARITY_SPEC_VERSION
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.run_id, "run_id")
        _require_allowed(self.claim_tier, "claim_tier", PARITY_CLAIM_TIERS)
        _validate_profile_id(self.model_profile_id)
        _require_allowed(
            self.evidence_status,
            "evidence_status",
            PARITY_EVIDENCE_STATUSES,
        )
        _require_allowed(
            self.failure_reason,
            "failure_reason",
            PARITY_FAILURE_REASONS,
        )
        _require_non_empty(self.contract_id, "contract_id")
        _require_non_empty(self.spec_version, "spec_version")
        object.__setattr__(self, "notes", _normalise_string_tuple(self.notes, "notes"))
        if self.evidence_status == "passed" and self.failure_reason != "none":
            raise ValueError("passed parity evidence cannot record a failure_reason")
        if self.evidence_status == "not_assessed" and self.failure_reason != "none":
            raise ValueError("not_assessed parity evidence cannot record a failure_reason")
        if self.evidence_status == "failed" and self.failure_reason == "none":
            raise ValueError("failed parity evidence must record a failure_reason")
        if self.claim_tier == "none" and self.evidence_status == "passed":
            raise ValueError("passed parity evidence must claim a concrete tier")
        if (
            self.model_profile_id != ACADEMIC_LTM_PARITY_PROFILE_ID
            and self.evidence_status == "passed"
        ):
            raise ValueError("only the academic LTM parity profile can pass parity evidence")


def _validate_profile_id(model_profile_id: str) -> None:
    _require_allowed(
        model_profile_id,
        "model_profile_id",
        SUPPORTED_LOADING_PROFILE_IDS,
    )


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value:
        raise ValueError(f"{field_name} must be non-empty")


def _require_allowed(value: str, field_name: str, allowed: frozenset[str]) -> None:
    _require_non_empty(value, field_name)
    if value not in allowed:
        raise ValueError(f"unsupported {field_name}: {value}")


def _normalise_allowed_tuple(
    values: Iterable[str],
    field_name: str,
    allowed: frozenset[str],
) -> tuple[str, ...]:
    value_tuple = _normalise_string_tuple(values, field_name)
    if not value_tuple:
        raise ValueError(f"{field_name} must not be empty")
    for value in value_tuple:
        _require_allowed(value, field_name, allowed)
    return value_tuple


def _normalise_string_tuple(values: Iterable[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, str):
        raise TypeError(f"{field_name} must be an iterable of strings, not a string")
    value_tuple = tuple(values)
    if not all(isinstance(value, str) for value in value_tuple):
        raise TypeError(f"{field_name} must contain only strings")
    return value_tuple
