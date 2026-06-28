"""Summary report for canonical LTM validation readiness."""

from __future__ import annotations

from dataclasses import dataclass

from .analytical_ltm import CanonicalScenarioResult, analytical_validation_results
from .literature_sources import LiteratureReferenceStatus, literature_reference_statuses


@dataclass(frozen=True, slots=True)
class CanonicalValidationSummary:
    """Current canonical-validation status across reproduced and blocked sources."""

    scenario_results: tuple[CanonicalScenarioResult, ...]
    literature_statuses: tuple[LiteratureReferenceStatus, ...]

    @property
    def reproduced_scenario_ids(self) -> tuple[str, ...]:
        """Return scenario IDs whose expected and observed series match."""

        return tuple(
            result.scenario_id
            for result in self.scenario_results
            if result.is_pass
        )

    @property
    def failed_scenario_ids(self) -> tuple[str, ...]:
        """Return reproduced scenarios with an unresolved mismatch."""

        return tuple(
            result.scenario_id
            for result in self.scenario_results
            if not result.is_pass
        )

    @property
    def blocked_reference_ids(self) -> tuple[str, ...]:
        """Return requested literature references still missing reproducible scenarios."""

        return tuple(
            status.reference_id
            for status in self.literature_statuses
            if (
                status.status != "reproduced"
                and status.is_blocking_current_readiness
            )
        )

    @property
    def deferred_reference_ids(self) -> tuple[str, ...]:
        """Return requested literature references parked for a later validation pass."""

        return tuple(
            status.reference_id
            for status in self.literature_statuses
            if not status.is_blocking_current_readiness
        )

    @property
    def covered_source_ids(self) -> tuple[str, ...]:
        """Return recognised source IDs covered by reproduced scenarios."""

        return tuple(
            sorted(
                {
                    source_id
                    for result in self.scenario_results
                    if result.is_pass
                    for source_id in result.source_ids
                }
            )
        )

    @property
    def is_ready_for_sioux_falls_parity_validation(self) -> bool:
        """Return whether prerequisite canonical validation is complete."""

        return not self.failed_scenario_ids and not self.blocked_reference_ids


def build_canonical_validation_summary() -> CanonicalValidationSummary:
    """Build the current canonical-validation summary without mutating the kernel."""

    return CanonicalValidationSummary(
        scenario_results=analytical_validation_results(),
        literature_statuses=literature_reference_statuses(),
    )
