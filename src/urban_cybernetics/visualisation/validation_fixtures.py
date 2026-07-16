"""Deterministic persisted baseline results for the M8 validation library."""

from __future__ import annotations

import json
from pathlib import Path

from .validation_cases import CASES, execute_case
from .validation_contract import (
    ValidationExecutionEvidence, ValidationLifecycle, ValidationRunStatus,
)


FIXTURE_TIME = "2026-07-14T00:00:00+00:00"


def write_validation_fixtures(root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for case in CASES:
        case_path = root / "cases" / f"{case.case_id.lower()}.json"
        case_path.parent.mkdir(parents=True, exist_ok=True)
        case_path.write_text(json.dumps(case.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        paths.append(case_path)
        result_id = f"{case.case_id.lower()}-baseline-v1"
        movements = []
        overlays = []
        result, bundle = execute_case(
            case, result_id=result_id, created_at=FIXTURE_TIME,
            completed_at=FIXTURE_TIME, code_commit="fixture-baseline",
            movement_evidence=movements.append, observed_overlay=overlays.append,
        )
        directory = root / "runs" / result_id
        directory.mkdir(parents=True, exist_ok=True)
        status = ValidationRunStatus(result_id=result_id, case_id=case.case_id, lifecycle=ValidationLifecycle.COMPLETE, physical_tick=case.default_final_tick, final_tick=case.default_final_tick, detail=result.observed_result_summary, terminal=True)
        for name, payload in (("status.json", status.model_dump(mode="json")), ("result.json", result.model_dump(mode="json")), ("replay_bundle.json", bundle.model_dump(mode="json"))):
            path = directory / name
            path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
            paths.append(path)
        if movements or overlays:
            evidence = ValidationExecutionEvidence(
                result_id=result_id, movement_evidence=tuple(movements),
                observed_overlays=tuple(overlays),
            )
            path = directory / "execution_evidence.json"
            path.write_text(
                json.dumps(
                    evidence.model_dump(mode="json"), indent=2,
                    sort_keys=True, ensure_ascii=False,
                ) + "\n",
                encoding="utf-8",
            )
            paths.append(path)
    return tuple(paths)
