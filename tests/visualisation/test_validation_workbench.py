from __future__ import annotations

import time
from pathlib import Path
from threading import Barrier, Lock, Thread

import pytest
from fastapi.testclient import TestClient

from urban_cybernetics.visualisation.server import create_app
from urban_cybernetics.visualisation.validation_cases import CASES, execute_case
from urban_cybernetics.visualisation.validation_contract import (
    ComparisonStatus, EvidenceSource, ValidationCase, ValidationResult,
)
from urban_cybernetics.visualisation.validation_fixtures import write_validation_fixtures
from urban_cybernetics.visualisation.validation_store import ValidationOrchestrator, ValidationRepository


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "visualisation" / "validation"


def test_case_contract_is_versioned_and_expected_evidence_is_independent() -> None:
    for case in CASES:
        assert ValidationCase.model_validate_json(case.model_dump_json()).schema_version == "uc.validation.case.v1"
        if case.comparison_status == ComparisonStatus.NOT_COMPARABLE:
            assert case.expected_series == ()
            assert case.metrics == ()
            assert any("curves were not inspected" in note.lower() for note in case.provenance)
        else:
            assert case.expected_series
            assert {series.evidence_source for series in case.expected_series} == {EvidenceSource.ANALYTICAL_REFERENCE}
            assert all("literal fixture data" in note.lower() for note in case.provenance)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_declared_case_execution_matches_exact_oracle_and_exports_replay(case: ValidationCase) -> None:
    result, bundle = execute_case(case, result_id=f"test-{case.case_id.lower()}", created_at="2026-07-14T00:00:00+00:00", completed_at="2026-07-14T00:00:00+00:00", code_commit="test")
    if case.comparison_status == ComparisonStatus.NOT_COMPARABLE:
        assert result.status.value == "not_run"
        assert result.metric_results == ()
        assert result.difference_series == ()
        assert "comparison withheld" in result.headline_metric
        expected_packets = 68 if "FIG7" in case.case_id else 70
        assert bundle.run.packet_count == expected_packets
    else:
        assert result.status.value == "passed"
        assert all(metric.passed and metric.value == 0 for metric in result.metric_results)
    assert result.schema_version == "uc.validation.result.v1"
    assert result.expected_evidence_hash != result.configuration_hash
    assert [state.tick for state in bundle.replay_states] == list(range(case.default_final_tick + 1))
    assert [event.sequence_number for event in bundle.event_stream.events] == list(range(len(bundle.event_stream.events)))


def test_fixture_regeneration_is_byte_deterministic(tmp_path: Path) -> None:
    generated = tmp_path / "validation"
    write_validation_fixtures(generated)
    expected_paths = sorted(path.relative_to(FIXTURES) for path in FIXTURES.rglob("*.json"))
    assert expected_paths
    for relative in expected_paths:
        assert (generated / relative).read_bytes() == (FIXTURES / relative).read_bytes()


def test_history_appends_without_overwriting_prior_failure_or_pass(tmp_path: Path) -> None:
    repository = ValidationRepository(tmp_path)
    orchestrator = ValidationOrchestrator(repository, execution_yield_seconds=0)
    first = orchestrator.start("M8-LINK-01", result_id="history-one")
    orchestrator.wait(first.result_id, 2)
    second = orchestrator.start("M8-LINK-01", result_id="history-two")
    orchestrator.wait(second.result_id, 2)
    history = repository.list_results("M8-LINK-01")
    assert [item.result_id for item in history] == ["history-one", "history-two"]
    with pytest.raises(FileExistsError):
        repository.append_result(repository.result("history-one"), repository.bundle("history-one"))


def test_cancel_retains_partial_result_and_replay_evidence(tmp_path: Path) -> None:
    repository = ValidationRepository(tmp_path)
    orchestrator = ValidationOrchestrator(repository, execution_yield_seconds=0.03)
    started = orchestrator.start("M8-LINK-02", result_id="cancelled-case")
    time.sleep(0.04)
    orchestrator.cancel(started.result_id)
    terminal = orchestrator.wait(started.result_id, 2)
    result = repository.result(started.result_id)
    bundle = repository.bundle(started.result_id)
    assert terminal.lifecycle.value == "cancelled"
    assert result.status.value == "cancelled"
    assert result.metric_results == ()
    assert bundle.run.status.value == "partial"
    assert bundle.event_stream.events


def test_status_writes_are_serialized_with_result_persistence(tmp_path: Path, monkeypatch) -> None:
    """Concurrent status/result writes must not share a live temporary file."""

    repository = ValidationRepository(tmp_path)
    original_write_text = Path.write_text
    start = Barrier(3)
    counter_lock = Lock()
    active_writes = 0
    maximum_active_writes = 0

    def observed_write_text(path: Path, *args, **kwargs):
        nonlocal active_writes, maximum_active_writes
        with counter_lock:
            active_writes += 1
            maximum_active_writes = max(maximum_active_writes, active_writes)
        try:
            time.sleep(0.01)
            return original_write_text(path, *args, **kwargs)
        finally:
            with counter_lock:
                active_writes -= 1

    monkeypatch.setattr(Path, "write_text", observed_write_text)
    errors: list[BaseException] = []

    def write(name: str) -> None:
        try:
            start.wait()
            repository._write_json(tmp_path / f"{name}.json", {"name": name})
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    threads = [Thread(target=write, args=(name,)) for name in ("status", "result")]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join()

    assert errors == []
    assert maximum_active_writes == 1


def test_api_discovers_cases_loads_history_and_runs_sanctioned_case(tmp_path: Path) -> None:
    repository = ValidationRepository(tmp_path / "runtime", read_only_roots=(FIXTURES,))
    orchestrator = ValidationOrchestrator(repository, execution_yield_seconds=0)
    api = TestClient(create_app(
        artifact_directory=ROOT / "fixtures" / "visualisation" / "v1",
        v2_artifact_directory=tmp_path / "v2",
        web_distribution=ROOT / "web" / "nonexistent-test-dist",
        validation_orchestrator=orchestrator,
    ))
    library = api.get("/api/v3/validation/cases")
    assert library.status_code == 200
    assert [item["case"]["case_id"] for item in library.json()] == [
        "M8-LINK-01", "M8-LINK-02", "M8-LINK-03", "M8-LINK-04",
        "M8-LINK-05", "M8-LINK-06", "M8-LINK-07",
        "M8-NODE-01-DEMAND", "M8-NODE-01-SUPPLY", "M8-NODE-01-EQUAL",
        "M8-NODE-01-ZERO-DEMAND", "M8-NODE-01-ZERO-SUPPLY",
        "M8-NODE-01-REOPEN", "M8-NODE-01-FRACTIONAL",
        "M8-PUB-DSOUZA-FIG5-DT1", "M8-PUB-DSOUZA-FIG5-DT3",
        "M8-PUB-DSOUZA-FIG5-DT6",
        "M8-PUB-DSOUZA-FIG7-DT1", "M8-PUB-DSOUZA-FIG7-DT3",
    ]
    assert all(
        item["latest_result"]["status"] == (
            "not_run" if item["case"]["comparison_status"] == "not_comparable" else "passed"
        )
        for item in library.json()
    )
    history_before = api.get("/api/v3/validation/cases/M8-LINK-01/history").json()
    started = api.post("/api/v3/validation/cases/M8-LINK-01/runs")
    assert started.status_code == 202
    result_id = started.json()["result_id"]
    orchestrator.wait(result_id, 2)
    assert api.get(f"/api/v3/validation/results/{result_id}").json()["status"] == "passed"
    assert len(api.get("/api/v3/validation/cases/M8-LINK-01/history").json()) == len(history_before) + 1
    assert api.post("/api/v3/validation/cases/not-declared/runs").status_code == 404


def test_published_preparation_persists_movement_and_vacancy_evidence(tmp_path: Path) -> None:
    repository = ValidationRepository(tmp_path / "runtime")
    orchestrator = ValidationOrchestrator(repository, execution_yield_seconds=0)
    status = orchestrator.start(
        "M8-PUB-DSOUZA-FIG5-DT3", result_id="desouza-preparation"
    )
    terminal = orchestrator.wait(status.result_id, 3)
    evidence = repository.execution_evidence(status.result_id)
    result = repository.result(status.result_id)
    assert terminal.lifecycle.value == "complete"
    assert result.status.value == "not_run"
    assert evidence.movement_evidence
    assert evidence.observed_overlays
    assert {item.kind for item in evidence.observed_overlays} == {"reference_wave"}
    api = TestClient(create_app(
        artifact_directory=ROOT / "fixtures" / "visualisation" / "v1",
        v2_artifact_directory=tmp_path / "v2",
        web_distribution=ROOT / "web" / "nonexistent-test-dist",
        validation_orchestrator=orchestrator,
    ))
    response = api.get(
        f"/api/v3/validation/results/{status.result_id}/execution-evidence"
    )
    assert response.status_code == 200
    assert response.json()["movement_evidence"]
    assert response.json()["observed_overlays"]


def test_loading_kernel_does_not_import_validation_workbench() -> None:
    loading_sources = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "src" / "urban_cybernetics" / "loading").rglob("*.py"))
    assert "visualisation.validation" not in loading_sources
