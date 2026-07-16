#!/usr/bin/env python3
"""Export frozen UC Figure 7 observables for later read-only comparison."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from urban_cybernetics.visualisation.validation_cases import CASES_BY_ID, execute_case


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data/validation/desouza_figure7_uc_observables_v1.csv"
DEFAULT_MANIFEST = ROOT / "data/validation/desouza_figure7_comparison_manifest_v1.json"
CASE_IDS = ("M8-PUB-DSOUZA-FIG7-DT1", "M8-PUB-DSOUZA-FIG7-DT3")
SERIES_IDS = (
    "upstream_cumulative_outflow",
    "downstream_1_cumulative_inflow",
    "downstream_2_cumulative_inflow",
    "upstream_outflow_per_tick",
    "downstream_1_inflow_per_tick",
    "downstream_2_inflow_per_tick",
)


def export(csv_path: Path, manifest_path: Path) -> None:
    rows: list[dict[str, int | float]] = []
    runs: list[dict[str, object]] = []
    for case_id in CASE_IDS:
        case = CASES_BY_ID[case_id]
        result, bundle = execute_case(
            case, result_id=f"{case_id.lower()}-comparison-preparation-v1",
            created_at="2026-07-16T00:00:00+00:00",
            completed_at="2026-07-16T00:00:00+00:00",
            code_commit="comparison-preparation-v1",
        )
        observed = {series.series_id: series.values for series in result.observed_series}
        if tuple(observed) != SERIES_IDS:
            raise AssertionError(f"unexpected Figure 7 observables for {case_id}: {tuple(observed)}")
        for tick in range(case.default_final_tick + 1):
            rows.append({
                "case_id": case_id,
                "dt_seconds": case.tick_duration_seconds,
                "tick": tick,
                "time_seconds": tick * case.tick_duration_seconds,
                **{series_id: observed[series_id][tick] for series_id in SERIES_IDS},
            })
        checks = bundle.validation.checks
        runs.append({
            "case_id": case_id,
            "dt_seconds": case.tick_duration_seconds,
            "final_tick": case.default_final_tick,
            "packet_count": bundle.run.packet_count,
            "event_count": bundle.run.event_count,
            "final_observables": {
                series_id: observed[series_id][-1] for series_id in SERIES_IDS
            },
            "internal_checks": checks,
        })

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=tuple(rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)

    try:
        csv_reference = str(csv_path.relative_to(ROOT))
    except ValueError:
        csv_reference = csv_path.name
    manifest = {
        "schema_version": "uc.validation.published-comparison-preparation.v1",
        "comparison_id": "m8-desouza-figure7-comparison-preparation-v1",
        "status": "dt1_observational_comparison_complete_dt3_reference_values_pending",
        "source": {
            "title": "A Mesoscopic Link-Transmission-Model Able to Track Individual Vehicles",
            "doi": "10.1016/j.simpat.2025.103088",
            "section": "4.2 Diverge Connections",
            "equation": "14",
            "figure": "7",
            "text_source_url": "https://www.osti.gov/servlets/purl/2569501",
        },
        "comparison_policy": {
            "dt1_reference_values_loaded": True,
            "dt3_reference_values_loaded": False,
            "dt1_paper_errors_computed": True,
            "parameter_tuning_permitted": False,
            "kernel_changes_made": False,
            "on_disagreement": "read-only first-divergence audit before any proposed change",
        },
        "dt1_reference_assets": {
            "Gu": "data/validation/desouza_figure7a_dt1_Gu_digitised_v1.csv",
            "F1": "data/validation/desouza_figure7a_dt1_F1_digitised_v1.csv",
            "F2": "data/validation/desouza_figure7a_dt1_F2_digitised_v1.csv",
            "comparison_report": "docs/validation/m8_desouza_figure7a_dt1_comparison_v1.md",
        },
        "observable_columns": list(SERIES_IDS),
        "uc_observations_csv": csv_reference,
        "runs": runs,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    export(args.csv, args.manifest)


if __name__ == "__main__":
    main()
