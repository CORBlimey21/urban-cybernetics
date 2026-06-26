"""Static physical-parameter validation for academic LTM parity."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from urban_cybernetics.config import (
    ACADEMIC_LTM_PARITY_PROFILE_ID,
    LEGACY_LOADING_PROFILE_ID,
    SUPPORTED_LOADING_PROFILE_IDS,
)
from urban_cybernetics.core import (
    DEFAULT_FD_RELATIVE_TOLERANCE,
    DEFAULT_MINIMUM_TIMESTEP_LAG_TICKS,
    Link,
    ResolvedPhysicalLinkParameters,
)


@dataclass(frozen=True, slots=True)
class PhysicalParameterEligibilityReport:
    """Aggregate M1 parity-eligibility report for static loading links."""

    model_profile_id: str
    link_reports: tuple[ResolvedPhysicalLinkParameters, ...]
    is_parity_eligible: bool
    ineligibility_reasons: tuple[str, ...]


def assess_physical_parameter_eligibility(
    links: Iterable[Link],
    *,
    model_profile_id: str = ACADEMIC_LTM_PARITY_PROFILE_ID,
    fd_relative_tolerance: float = DEFAULT_FD_RELATIVE_TOLERANCE,
    minimum_lag_ticks: int = DEFAULT_MINIMUM_TIMESTEP_LAG_TICKS,
) -> PhysicalParameterEligibilityReport:
    """Assess static physical metadata without running or mutating loading."""

    if model_profile_id not in SUPPORTED_LOADING_PROFILE_IDS:
        raise ValueError(f"unsupported loading profile: {model_profile_id}")
    link_tuple = tuple(links)
    link_reports = tuple(
        link.resolved_physical_parameters(
            fd_relative_tolerance=fd_relative_tolerance,
            minimum_lag_ticks=minimum_lag_ticks,
        )
        for link in link_tuple
    )
    reasons: list[str] = []
    if model_profile_id == LEGACY_LOADING_PROFILE_ID:
        reasons.append("legacy_profile_not_parity_evidence")
    for report in link_reports:
        for reason in report.ineligibility_reasons:
            reasons.append(f"{report.link_id}:{reason}")
    return PhysicalParameterEligibilityReport(
        model_profile_id=model_profile_id,
        link_reports=link_reports,
        is_parity_eligible=(
            model_profile_id == ACADEMIC_LTM_PARITY_PROFILE_ID
            and bool(link_reports)
            and all(report.parity_eligible for report in link_reports)
        ),
        ineligibility_reasons=tuple(reasons),
    )


def require_physical_parameter_eligibility(
    links: Iterable[Link],
    *,
    model_profile_id: str = ACADEMIC_LTM_PARITY_PROFILE_ID,
    fd_relative_tolerance: float = DEFAULT_FD_RELATIVE_TOLERANCE,
    minimum_lag_ticks: int = DEFAULT_MINIMUM_TIMESTEP_LAG_TICKS,
) -> PhysicalParameterEligibilityReport:
    """Return an aggregate report or fail loudly for non-eligible physical metadata."""

    report = assess_physical_parameter_eligibility(
        links,
        model_profile_id=model_profile_id,
        fd_relative_tolerance=fd_relative_tolerance,
        minimum_lag_ticks=minimum_lag_ticks,
    )
    if not report.is_parity_eligible:
        raise ValueError(
            "static physical parameters are not parity-eligible: "
            f"{report.ineligibility_reasons}"
        )
    return report
