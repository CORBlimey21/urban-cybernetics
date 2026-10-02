#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Generate and compare the canonical Figure 9 asymmetric-priority fixture."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from urban_cybernetics.canonical_validation.desouza_figure9 import (
    FIGURE9_ASYMMETRIC_CASE_ID,
    run_figure9_asymmetric_priority,
)
from urban_cybernetics.canonical_validation.desouza_figure9_comparison import (
    compare_figure9_case,
)
from urban_cybernetics.publication import require_reference_inputs


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/validation"
EVIDENCE = DATA / "desouza_figure9d_asymmetric_uc_evidence_v1.json"
SUMMARY = DATA / "desouza_figure9d_asymmetric_comparison_summary_v1.json"
OUTPUT = ROOT / "outputs/validation/m8_desouza_figure9d_asymmetric_v1"
REFERENCES = {
    "G1": DATA / "desouza_figure9d_asymmetric_priority_G1_digitised_v1.csv",
    "G2": DATA / "desouza_figure9d_asymmetric_priority_G2_digitised_v1.csv",
}
AMBIGUITY_RESOLUTION = {
    "selected_alpha_1": 0.75,
    "rejected_textual_value": 0.25,
    "paper_priority_sequence_zero_based": [0, 0, 0, 1],
    "uc_priority_sequence": ["L1", "L1", "L1", "L2"],
    "interpretation": (
        "alpha_1 denotes link 1's share; x=[0,0,0,1] therefore encodes "
        "three link-1 opportunities for each link-2 opportunity"
    ),
    "evidence": [
        "Figure 9(d-f) panel labels print alpha_1=0.75 with x=[0,0,0,1].",
        "The accompanying behaviour prose identifies link 1 as higher priority and states alpha_1=0.75.",
        "Equation (5) defines alpha_p as approach p's downstream-supply share, so alpha_1 is link 1's share.",
        "The merge algorithm defines repeated entries in x as repeated priority opportunities.",
        "The later freeway example pairs alpha_freeway=0.75 with x=[0,0,0,1].",
        "The two alpha_1=0.25 mentions in the section body and caption conflict with all five signals above.",
    ],
    "classification": "paper transcription inconsistency resolved by internal evidence",
}


def main() -> None:
    require_reference_inputs(REFERENCES.values())
    result = run_figure9_asymmetric_priority()
    evidence = asdict(result)
    evidence["paper_priority_ambiguity_resolution"] = AMBIGUITY_RESOLUTION
    EVIDENCE.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = compare_figure9_case(
        case_id=FIGURE9_ASYMMETRIC_CASE_ID,
        panel_id="d",
        evidence_path=EVIDENCE,
        reference_paths=REFERENCES,
        summary_path=SUMMARY,
        output_dir=OUTPUT,
    )
    print(json.dumps({
        "case_id": FIGURE9_ASYMMETRIC_CASE_ID,
        "all_checks_pass": result.all_checks_pass,
        "paper_priority_ambiguity_resolution": AMBIGUITY_RESOLUTION,
        "series": summary["series"],
        "artifacts": {
            "evidence": str(EVIDENCE.relative_to(ROOT)),
            "summary": str(SUMMARY.relative_to(ROOT)),
            "plots": str(OUTPUT.relative_to(ROOT)),
        },
    }, indent=2))


if __name__ == "__main__":
    main()
