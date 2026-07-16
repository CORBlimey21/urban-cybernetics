from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from urban_cybernetics.visualisation.lab_bench import LabBenchRepository, compare_series, declared_case_variables, starter_worksheet
from urban_cybernetics.visualisation.lab_bench_contract import (
    ColumnKind, ComparisonRequest, EvaluationRequest, FreezeRequest, LabColumn,
    LabState, LabVariable, ProvenanceClass, SeriesMapping, TableEvaluationRequest,
    TickTable,
)
from urban_cybernetics.visualisation.lab_bench_evaluator import LabExpressionError, evaluate_expression, evaluate_table
from urban_cybernetics.visualisation.server import create_app


ROOT = Path(__file__).resolve().parents[2]


def scalar(variable_id: str, value: float, units: str = "1") -> LabVariable:
    return LabVariable(variable_id=variable_id, label=variable_id, value=value, units=units, source="test literal", evidence_classification="test", configuration_identity="test")


def test_bounded_calculator_shows_substitution_units_and_tick_conversion() -> None:
    metadata = LabVariable(variable_id="route", label="Route", value=("L1",), units="link IDs", source="declared", evidence_classification="test", configuration_identity="test")
    variables = (scalar("length", 150, "m"), scalar("speed", 30, "m/s"), scalar("timestep", 1, "s"), metadata)
    result = evaluate_expression(EvaluationRequest(expression="ceil(length / speed / timestep)", variables=variables, target_units="1"))
    assert result.value == 5
    assert result.units == "1"
    assert "length=150" in result.substituted_expression
    ticks = evaluate_expression(EvaluationRequest(expression="ticks(length / speed, timestep)", variables=variables, target_units="ticks"))
    assert ticks.value == 5


@pytest.mark.parametrize("expression", (
    "__import__('os')", "open('/tmp/x')", "value.__class__", "[x for x in (1,2)]", "(lambda: 1)()", "series[0]",
))
def test_bounded_calculator_rejects_execution_and_unsupported_syntax(expression: str) -> None:
    with pytest.raises(LabExpressionError):
        evaluate_expression(EvaluationRequest(expression=expression, variables=(scalar("value", 1),)))


def test_calculator_rejects_dimensional_inconsistency() -> None:
    with pytest.raises(LabExpressionError, match="compatible units"):
        evaluate_expression(EvaluationRequest(expression="length + timestep", variables=(scalar("length", 1, "m"), scalar("timestep", 1, "s"))))


def test_table_evaluation_is_deterministic_and_declares_dependency_order() -> None:
    worksheet = starter_worksheet("M8-LINK-01", "starter")
    first = evaluate_table(TableEvaluationRequest(table=worksheet.table, variables=worksheet.variables))
    second = evaluate_table(TableEvaluationRequest(table=worksheet.table, variables=worksheet.variables))
    assert first == second
    values = {column.column_id: column.values for column in first.table.columns}
    assert values == {
        "arrivals": (3.0, 0.0, 0.0, 0.0),
        "cumulative_entries": (3.0, 3.0, 3.0, 3.0),
        "cumulative_exits": (0.0, 0.0, 3.0, 3.0),
        "storage": (3.0, 3.0, 0.0, 0.0),
    }
    assert first.dependency_order == ("arrivals", "cumulative_entries", "cumulative_exits", "storage")


def test_starter_artifact_regeneration_is_byte_deterministic() -> None:
    timestamp = "2026-07-15T12:00:00+00:00"
    first = starter_worksheet("M8-LINK-01", "deterministic", created_at=timestamp)
    second = starter_worksheet("M8-LINK-01", "deterministic", created_at=timestamp)
    first_table = evaluate_table(TableEvaluationRequest(table=first.table, variables=first.variables)).table
    second_table = evaluate_table(TableEvaluationRequest(table=second.table, variables=second.variables)).table
    assert first.model_copy(update={"table": first_table}).model_dump_json() == second.model_copy(update={"table": second_table}).model_dump_json()


def test_table_rejects_circular_missing_initial_and_ambiguous_tick_references() -> None:
    circular = TickTable(tick_start=0, tick_end=0, columns=(
        LabColumn(column_id="a", label="A", units="1", kind=ColumnKind.FORMULA, provenance=ProvenanceClass.INDEPENDENT_ARITHMETIC, formula="b[t]"),
        LabColumn(column_id="b", label="B", units="1", kind=ColumnKind.FORMULA, provenance=ProvenanceClass.INDEPENDENT_ARITHMETIC, formula="a[t]"),
    ))
    with pytest.raises(LabExpressionError, match="circular"):
        evaluate_table(TableEvaluationRequest(table=circular))
    missing = TickTable(tick_start=0, tick_end=0, columns=(
        LabColumn(column_id="a", label="A", units="1", kind=ColumnKind.FORMULA, provenance=ProvenanceClass.INDEPENDENT_ARITHMETIC, formula="a[t - 1] + 1"),
    ))
    with pytest.raises(LabExpressionError, match="missing initial"):
        evaluate_table(TableEvaluationRequest(table=missing))
    current = missing.model_copy(update={"columns": (missing.columns[0].model_copy(update={"formula": "a[t] + 1"}),), "out_of_range_values": {"a": 0}})
    with pytest.raises(LabExpressionError, match="current/future"):
        evaluate_table(TableEvaluationRequest(table=current))


def test_table_converts_formula_results_to_declared_column_units() -> None:
    table = TickTable(tick_start=0, tick_end=0, columns=(
        LabColumn(column_id="speed", label="Speed", units="km/h", kind=ColumnKind.FORMULA, provenance=ProvenanceClass.INDEPENDENT_ARITHMETIC, formula="distance / duration"),
    ))
    result = evaluate_table(TableEvaluationRequest(table=table, variables=(scalar("distance", 1000, "m"), scalar("duration", 100, "s"))))
    assert result.table.columns[0].values == pytest.approx((36.0,))


def test_declared_case_variables_retain_source_units_and_configuration_identity() -> None:
    variables = declared_case_variables("M8-LINK-01")
    by_id = {item.variable_id: item for item in variables}
    assert by_id["length"].value == 200
    assert by_id["length"].units == "m"
    assert by_id["free_flow_lag"].value == 2
    assert by_id["demand_schedule"].source == "declared validation case input"
    assert len({item.configuration_identity for item in variables}) == 1


def test_desouza_preparation_starter_exposes_inputs_without_paper_outputs() -> None:
    case_id = "M8-PUB-DSOUZA-FIG5-DT3"
    variables = {item.variable_id: item for item in declared_case_variables(case_id)}
    assert variables["upstream_capacity"].value == 1.0
    assert variables["downstream_capacity"].value == 0.5
    assert variables["integrated_demand"].value == 70
    worksheet = starter_worksheet(
        case_id, "desouza-lab", created_at="2026-07-15T00:00:00+00:00"
    )
    assert worksheet.table.tick_end == 50
    assert sum(worksheet.table.columns[0].values) == 70
    assert "No published Figure 5 curve" in worksheet.notebook.markdown
    assert all(column.kind.value != "uc_observed" for column in worksheet.table.columns)


def test_scratch_candidate_frozen_lifecycle_is_explicit_append_only_and_versioned(tmp_path: Path) -> None:
    repository = LabBenchRepository(tmp_path)
    worksheet = starter_worksheet("M8-LINK-01", "manual-one")
    evaluated = evaluate_table(TableEvaluationRequest(table=worksheet.table, variables=worksheet.variables))
    saved = repository.save(worksheet.model_copy(update={"table": evaluated.table}), record_history=True)
    assert saved.state == LabState.SCRATCH
    candidate = repository.promote(saved.worksheet_id)
    assert candidate.state == LabState.CANDIDATE
    request = FreezeRequest(worksheet_id=candidate.worksheet_id, approval_action="Reviewed formula and table row by row", author_source=ProvenanceClass.USER_HAND_DERIVATION, notes=("Manual review complete.",))
    first = repository.freeze(request)
    assert first.state == LabState.FROZEN and first.version == 1 and len(first.artifact_hash) == 64
    edited = repository.save(candidate.model_copy(update={"title": "Edited candidate for version two"}), record_history=True)
    second = repository.freeze(request)
    assert edited.revision > candidate.revision
    assert second.version == 2
    assert repository.list_oracles("M8-LINK-01") == (first, second)
    with pytest.raises(FileExistsError):
        repository._write(tmp_path / "oracles" / first.oracle_id / "version-000001.json", first, exclusive=True)


def test_freeze_rejects_uc_derived_and_changed_linked_dependencies(tmp_path: Path) -> None:
    repository = LabBenchRepository(tmp_path)
    worksheet = starter_worksheet("M8-LINK-01", "unsafe")
    unsafe_column = LabColumn(column_id="observed", label="Observed", units="packets", kind=ColumnKind.UC_OBSERVED, provenance=ProvenanceClass.UC_DERIVED, values=(0, 0, 3, 3), source_reference="canonical events")
    unsafe = worksheet.model_copy(update={"state": LabState.CANDIDATE, "table": worksheet.table.model_copy(update={"columns": worksheet.table.columns + (unsafe_column,)})})
    repository.save(unsafe)
    with pytest.raises(ValueError, match="ineligible"):
        repository.freeze(FreezeRequest(worksheet_id="unsafe", approval_action="Attempted review", author_source=ProvenanceClass.USER_HAND_DERIVATION))
    changed_variables = (worksheet.variables[0].model_copy(update={"configuration_identity": "stale"}),) + worksheet.variables[1:]
    changed = worksheet.model_copy(update={"worksheet_id": "changed", "state": LabState.CANDIDATE, "case_configuration_hash": "stale", "variables": changed_variables})
    repository.save(changed)
    with pytest.raises(ValueError, match="configuration changed"):
        repository.freeze(FreezeRequest(worksheet_id="changed", approval_action="Reviewed stale inputs", author_source=ProvenanceClass.USER_HAND_DERIVATION))
    detached = changed.model_copy(update={"worksheet_id": "detached", "variables": tuple(item.model_copy(update={"linked": False}) for item in changed.variables)})
    repository.save(detached)
    assert repository.freeze(FreezeRequest(worksheet_id="detached", approval_action="Reviewed detached literals", author_source=ProvenanceClass.USER_HAND_DERIVATION)).input_references == ()


def test_python_comparison_is_explicit_and_marks_provisional_evidence() -> None:
    mapping = SeriesMapping(expected_column_id="cumulative_exits", observed_series_id="exits", expected_units="packets", observed_units="packets", time_alignment="offset", tick_offset=1, tolerance=0)
    result = compare_series(ComparisonRequest(mapping=mapping, expected_ticks=(0, 1, 2), expected_values=(0, 0, 3), observed_ticks=(1, 2, 3), observed_values=(0, 1, 3), expected_state=LabState.CANDIDATE))
    assert not result.formal
    assert result.label == "Informal comparison — not formal validation evidence."
    assert result.differences == (0, -1, 0)
    assert result.first_mismatch_tick == 1
    assert result.maximum_absolute_error == 1
    assert result.mean_absolute_error == pytest.approx(1 / 3)
    assert result.mismatched_rows == 1


def test_lab_bench_api_persists_starter_evaluates_and_freezes(tmp_path: Path) -> None:
    repository = LabBenchRepository(tmp_path / "lab")
    api = TestClient(create_app(
        artifact_directory=ROOT / "fixtures" / "visualisation" / "v1",
        v2_artifact_directory=tmp_path / "v2",
        web_distribution=ROOT / "web" / "nonexistent-test-dist",
        lab_bench_repository=repository,
    ))
    variables = api.get("/api/v4/lab-bench/cases/M8-LINK-01/variables")
    assert variables.status_code == 200
    starter = api.post("/api/v4/lab-bench/cases/M8-LINK-01/starter")
    assert starter.status_code == 200
    worksheet = starter.json()
    assert worksheet["state"] == "scratch"
    assert {column["column_id"] for column in worksheet["table"]["columns"]} == {"arrivals", "cumulative_entries", "cumulative_exits", "storage"}
    promoted = api.post(f"/api/v4/lab-bench/worksheets/{worksheet['worksheet_id']}/promote")
    assert promoted.status_code == 200
    frozen = api.post("/api/v4/lab-bench/oracles/freeze", json={"worksheet_id": worksheet["worksheet_id"], "approval_action": "Reviewed manually", "author_source": "user_hand_derivation", "notes": [], "limitations": []})
    assert frozen.status_code == 200
    assert frozen.json()["schema_version"] == "uc.lab_bench.oracle.v1"
    assert api.get("/api/v4/lab-bench/oracles?case_id=M8-LINK-01").json()[0]["version"] == 1


def test_loading_kernel_does_not_import_lab_bench() -> None:
    loading_sources = tuple((ROOT / "src" / "urban_cybernetics" / "loading").rglob("*.py"))
    assert loading_sources
    assert all("lab_bench" not in path.read_text(encoding="utf-8") for path in loading_sources)
