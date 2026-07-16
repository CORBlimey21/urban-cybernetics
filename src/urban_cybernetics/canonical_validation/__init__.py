"""Reusable canonical LTM validation fixtures."""

from .analytical_ltm import (
    CanonicalScenarioResult,
    ReferenceSeriesComparison,
    analytical_capacity_saturation_result,
    analytical_delayed_spillback_result,
    analytical_free_flow_shift_result,
    analytical_priority_merge_result,
    analytical_receiving_bottleneck_result,
    analytical_strict_diverge_result,
    analytical_validation_results,
    render_series_comparison_svg,
)
from .composition import (
    COMPOSITION_BOUNDARIES,
    COMPOSITION_CASE_ID,
    COMPOSITION_CASE_VERSION,
    COMPOSITION_FINAL_TICK,
    COMPOSITION_LINK_IDS,
    COMPOSITION_ROUTES,
    build_composition_validation_engine,
    run_composition_validation_case,
)
from .literature_sources import (
    LiteratureReferenceStatus,
    literature_reference_statuses,
)
from .report import (
    CanonicalValidationSummary,
    build_canonical_validation_summary,
)
from .sioux_falls_physical_profile import (
    SiouxFallsPhysicalProfile,
    SiouxFallsPhysicalProfileSummary,
    build_sioux_falls_uc_default_physical_profile,
    derive_jam_density_veh_per_km_per_lane,
    derive_storage_capacity_packets,
)
from .sioux_falls_readiness import (
    SiouxFallsReplayPolicy,
    build_sioux_falls_assumption_profile_determinism_report,
    build_sioux_falls_assumption_profile_scale_ladder_report,
)

__all__ = [
    "CanonicalScenarioResult",
    "CanonicalValidationSummary",
    "COMPOSITION_BOUNDARIES",
    "COMPOSITION_CASE_ID",
    "COMPOSITION_CASE_VERSION",
    "COMPOSITION_FINAL_TICK",
    "COMPOSITION_LINK_IDS",
    "COMPOSITION_ROUTES",
    "LiteratureReferenceStatus",
    "ReferenceSeriesComparison",
    "SiouxFallsPhysicalProfile",
    "SiouxFallsPhysicalProfileSummary",
    "SiouxFallsReplayPolicy",
    "analytical_capacity_saturation_result",
    "analytical_delayed_spillback_result",
    "analytical_free_flow_shift_result",
    "analytical_priority_merge_result",
    "analytical_receiving_bottleneck_result",
    "analytical_strict_diverge_result",
    "analytical_validation_results",
    "build_canonical_validation_summary",
    "build_composition_validation_engine",
    "build_sioux_falls_assumption_profile_determinism_report",
    "build_sioux_falls_assumption_profile_scale_ladder_report",
    "build_sioux_falls_uc_default_physical_profile",
    "derive_jam_density_veh_per_km_per_lane",
    "derive_storage_capacity_packets",
    "literature_reference_statuses",
    "render_series_comparison_svg",
    "run_composition_validation_case",
]
