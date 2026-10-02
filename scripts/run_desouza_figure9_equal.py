#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Generate and compare the canonical Figure 9 equal-priority fixture."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from urban_cybernetics.canonical_validation.desouza_figure9 import (
    FIGURE9_EQUAL_CASE_ID,
    run_figure9_equal_priority,
)
from urban_cybernetics.canonical_validation.desouza_figure9_comparison import (
    compare_figure9_case,
)
from urban_cybernetics.publication import require_reference_inputs


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/validation"
EVIDENCE = DATA / "desouza_figure9a_equal_uc_evidence_v1.json"
SUMMARY = DATA / "desouza_figure9a_equal_comparison_summary_v1.json"
OUTPUT = ROOT / "outputs/validation/m8_desouza_figure9a_equal_v1"
REFERENCES = {
    "G1": DATA / "desouza_figure9a_equal_priority_G1_digitised_v1.csv",
    "G2": DATA / "desouza_figure9a_equal_priority_G2_digitised_v1.csv",
}


def main() -> None:
    require_reference_inputs(REFERENCES.values())
    result = run_figure9_equal_priority()
    EVIDENCE.write_text(
        json.dumps(asdict(result), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = compare_figure9_case(
        case_id=FIGURE9_EQUAL_CASE_ID,
        panel_id="a",
        evidence_path=EVIDENCE,
        reference_paths=REFERENCES,
        summary_path=SUMMARY,
        output_dir=OUTPUT,
    )
    print(json.dumps({
        "case_id": FIGURE9_EQUAL_CASE_ID,
        "all_checks_pass": result.all_checks_pass,
        "series": summary["series"],
        "artifacts": {
            "evidence": str(EVIDENCE.relative_to(ROOT)),
            "summary": str(SUMMARY.relative_to(ROOT)),
            "plots": str(OUTPUT.relative_to(ROOT)),
        },
    }, indent=2))


if __name__ == "__main__":
    main()
