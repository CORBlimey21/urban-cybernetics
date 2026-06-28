"""Canonical analytical LTM validation fixtures."""

from __future__ import annotations

from urban_cybernetics.canonical_validation import (
    analytical_validation_results,
    build_canonical_validation_summary,
    literature_reference_statuses,
    render_series_comparison_svg,
)


def test_analytical_ltm_scenarios_match_reference_series() -> None:
    results = analytical_validation_results()

    assert {result.scenario_id for result in results} == {
        "single_link_free_flow_shift",
        "single_link_sending_capacity_saturation",
        "two_link_receiving_bottleneck",
        "two_link_delayed_vacancy_spillback",
        "strict_fifo_diverge_blocked_head",
        "priority_merge_declared_share",
    }
    assert all(result.is_pass for result in results), {
        result.scenario_id: [
            comparison.name
            for comparison in result.comparisons
            if not comparison.is_match
        ]
        for result in results
    }


def test_analytical_ltm_results_expose_assumptions_and_classifications() -> None:
    for result in analytical_validation_results():
        assert result.reference_id == "analytical_textbook_ltm"
        assert result.source_ids
        assert result.assumptions
        assert result.classifications
        assert result.comparisons


def test_series_comparison_svg_is_reviewable_for_numeric_curves() -> None:
    result = analytical_validation_results()[0]
    svg = render_series_comparison_svg(result.comparisons[1])

    assert svg.startswith("<svg ")
    assert "blue=expected red=observed" in svg
    assert result.comparisons[1].name in svg


def test_requested_literature_references_have_explicit_reproducibility_status() -> None:
    statuses = {
        status.reference_id: status
        for status in literature_reference_statuses()
    }

    assert set(statuses) == {
        "yperman_2007_thesis",
        "de_souza_2025_mesoscopic_ltm",
    }
    assert statuses["yperman_2007_thesis"].priority == 2
    assert statuses["de_souza_2025_mesoscopic_ltm"].priority == 3
    assert all(status.source_url.startswith("https://doi.org/") for status in statuses.values())
    assert all(status.status == "deferred_by_user" for status in statuses.values())
    assert not any(status.is_blocking_current_readiness for status in statuses.values())
    assert all(status.blocker for status in statuses.values())
    assert all(status.next_step for status in statuses.values())
    assert all(status.access_evidence for status in statuses.values())


def test_canonical_validation_summary_reports_sioux_falls_readiness() -> None:
    summary = build_canonical_validation_summary()

    assert summary.reproduced_scenario_ids == (
        "single_link_free_flow_shift",
        "single_link_sending_capacity_saturation",
        "two_link_receiving_bottleneck",
        "two_link_delayed_vacancy_spillback",
        "strict_fifo_diverge_blocked_head",
        "priority_merge_declared_share",
    )
    assert summary.failed_scenario_ids == ()
    assert summary.covered_source_ids == (
        "daganzo_1994_cell_transmission_model",
        "daganzo_1995_cell_transmission_networks",
        "newell_1993_freeway_bottlenecks",
        "newell_1993_simplified_kinematic_waves",
        "tampere_2011_generic_node_models",
    )
    assert summary.blocked_reference_ids == ()
    assert summary.deferred_reference_ids == (
        "yperman_2007_thesis",
        "de_souza_2025_mesoscopic_ltm",
    )
    assert summary.is_ready_for_sioux_falls_parity_validation
