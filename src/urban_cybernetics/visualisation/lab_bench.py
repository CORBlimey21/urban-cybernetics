"""Persisted Lab Bench service; never imported by the loading kernel."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from .lab_bench_contract import (
    ColumnKind, ComparisonRequest, ComparisonResult, FreezeRequest, FrozenOracle,
    LabColumn, LabState, LabVariable, LabWorksheet, Notebook, ProvenanceClass,
    TickTable,
)
from .lab_bench_evaluator import LabExpressionError, _quantity
from .validation_cases import (
    BOTTLENECK, CASES_BY_ID, FRACTIONAL_SENDING, NODE_SPECS, NODE_UPSTREAM,
    QUEUE_GROWTH, SUSTAINED_FREE_FLOW, UNCONGESTED, VACANCY_L1, VACANCY_L2,
)


class LabArtifactNotFound(KeyError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_hash(value: object) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _case_link_input(case_id: str):
    if case_id == "M8-LINK-01": return (UNCONGESTED,)
    if case_id == "M8-LINK-02": return (BOTTLENECK,)
    if case_id in {"M8-LINK-03", "M8-LINK-06"}: return (VACANCY_L1, VACANCY_L2)
    if case_id == "M8-LINK-04": return (SUSTAINED_FREE_FLOW,)
    if case_id == "M8-LINK-05": return (QUEUE_GROWTH,)
    if case_id == "M8-LINK-07": return (FRACTIONAL_SENDING,)
    if case_id.startswith("M8-NODE-01-"):
        spec = next(item for item in NODE_SPECS if item.case_id == case_id)
        downstream = NODE_UPSTREAM.__class__("L2", 10.0, 10.0, 5.0, 1800.0, 21600.0, 1.0, spec.receiving_supply)
        return (NODE_UPSTREAM, downstream)
    raise LabArtifactNotFound(case_id)


def declared_case_variables(case_id: str) -> tuple[LabVariable, ...]:
    case = CASES_BY_ID.get(case_id)
    if case is None: raise LabArtifactNotFound(case_id)
    links = _case_link_input(case_id)
    config_seed = {
        "case_id": case.case_id, "case_version": case.version,
        "topology_reference": case.topology_reference, "profile_reference": case.profile_reference,
        "demand_reference": case.demand_reference,
        "links": [asdict(item) for item in links],
    }
    identity = _canonical_hash(config_seed)
    first = links[0]
    storage = int(first.jam_density_veh_per_km_per_lane * first.length_m / 1000)
    values: list[LabVariable] = [
        LabVariable(variable_id="timestep", label="Timestep", value=first.tick_duration_seconds, units="s", source="declared validation case input", evidence_classification="configuration_metadata", configuration_identity=identity),
        LabVariable(variable_id="length", label="Link length", value=first.length_m, units="m", source=f"declared {first.link_id} input", evidence_classification="configuration_metadata", configuration_identity=identity),
        LabVariable(variable_id="lane_count", label="Lane count", value=1, units="1", source=f"declared {first.link_id} input", evidence_classification="configuration_metadata", configuration_identity=identity),
        LabVariable(variable_id="capacity", label="Sending capacity", value=first.sending_rate_per_tick or first.capacity_per_tick, units="packets/tick", source=f"declared {first.link_id} input", evidence_classification="configuration_metadata", configuration_identity=identity),
        LabVariable(variable_id="storage", label="Storage", value=storage, units="packets", source="declared triangular-FD inputs; floor(kj*L*lanes)", evidence_classification="deterministic_tool_output", configuration_identity=identity),
        LabVariable(variable_id="free_flow_speed", label="Free-flow speed", value=first.free_flow_speed_mps, units="m/s", source=f"declared {first.link_id} input", evidence_classification="configuration_metadata", configuration_identity=identity),
        LabVariable(variable_id="backward_wave_speed", label="Backward-wave speed", value=first.backward_wave_speed_mps, units="m/s", source=f"declared {first.link_id} input", evidence_classification="configuration_metadata", configuration_identity=identity),
        LabVariable(variable_id="free_flow_lag", label="Free-flow lag", value=first.free_flow_lag_ticks, units="1", source="ceil(length/free_flow_speed/timestep)", evidence_classification="deterministic_tool_output", configuration_identity=identity),
        LabVariable(variable_id="backward_wave_lag", label="Backward-wave lag", value=first.backward_wave_lag_ticks, units="1", source="ceil(length/backward_wave_speed/timestep)", evidence_classification="deterministic_tool_output", configuration_identity=identity),
        LabVariable(variable_id="demand_schedule", label="Demand schedule", value=case.demand_reference, units="packets by declared tick", source="declared validation case input", evidence_classification="configuration_metadata", configuration_identity=identity),
        LabVariable(variable_id="route_sequence", label="Route sequence", value=case.route_sequences[0] if case.route_sequences else (), units="link IDs", source="declared validation case input", evidence_classification="configuration_metadata", configuration_identity=identity),
        LabVariable(variable_id="transition_markers", label="Expected transition markers", value=tuple(f"tick {item.active_from_tick}: {item.label}" for item in case.overlays), units="ticks", source="authored validation metadata", evidence_classification="analytical_reference", configuration_identity=identity),
    ]
    if case_id.startswith("M8-NODE-01-"):
        spec = next(item for item in NODE_SPECS if item.case_id == case_id)
        values.extend((
            LabVariable(variable_id="node_demand", label="Node demand", value=spec.demand, units="packets", source="declared NODE-01 input", evidence_classification="configuration_metadata", configuration_identity=identity),
            LabVariable(variable_id="node_receiving_supply", label="Node receiving supply", value=spec.receiving_supply, units="packets/tick", source="declared NODE-01 input", evidence_classification="configuration_metadata", configuration_identity=identity),
        ))
    return tuple(values)


def starter_worksheet(case_id: str, worksheet_id: str | None = None, *, created_at: str | None = None) -> LabWorksheet:
    if case_id != "M8-LINK-01":
        raise LabExpressionError("the first slice provides a complete starter only for M8-LINK-01")
    now = created_at or _now(); variables = declared_case_variables(case_id)
    config_hash = variables[0].configuration_identity
    return LabWorksheet(
        worksheet_id=worksheet_id or f"lab-{uuid.uuid4().hex}", title="M8-LINK-01 manual free-flow derivation",
        case_id=case_id, case_version=CASES_BY_ID[case_id].version, case_configuration_hash=config_hash,
        created_at=now, updated_at=now, variables=variables,
        notebook=Notebook(markdown=(
            "# Free-flow derivation\n\n"
            "Declared inputs only: $L = 200\\,m$, $v_f = 10\\,m/s$, and $\\Delta t = 10\\,s$.\n\n"
            "$$t_f = L / v_f$$\n\n"
            "$$\\tau_f = \\lceil t_f / \\Delta t \\rceil$$\n\n"
            "The entry pulse below is manually transcribed from the declared demand schedule. "
            "Cumulative curves and storage are then evaluated deterministically; no fixture expected values are imported."
        ), linked_references=("length", "free_flow_speed", "timestep", "demand_schedule")),
        table=TickTable(tick_start=0, tick_end=3, out_of_range_values={"cumulative_entries": 0, "cumulative_exits": 0}, columns=(
            LabColumn(column_id="arrivals", label="Arrivals during tick", units="packets", kind=ColumnKind.MANUAL, provenance=ProvenanceClass.USER_HAND_DERIVATION, values=(3, 0, 0, 0), source_reference="manual transcription of declared demand schedule"),
            LabColumn(column_id="cumulative_entries", label="Cumulative entries", units="packets", kind=ColumnKind.FORMULA, provenance=ProvenanceClass.INDEPENDENT_ARITHMETIC, formula="cumulative_entries[t - 1] + arrivals[t]", source_reference="user-reviewed deterministic formula"),
            LabColumn(column_id="cumulative_exits", label="Cumulative exits", units="packets", kind=ColumnKind.FORMULA, provenance=ProvenanceClass.INDEPENDENT_ARITHMETIC, formula="cumulative_entries[t - free_flow_lag]", source_reference="free-flow translation formula"),
            LabColumn(column_id="storage", label="Storage", units="packets", kind=ColumnKind.FORMULA, provenance=ProvenanceClass.INDEPENDENT_ARITHMETIC, formula="cumulative_entries[t] - cumulative_exits[t]", source_reference="conservation identity"),
        )),
        assumptions=("Inclusive integer physical ticks.", "Out-of-range cumulative counts are explicitly zero.", "Unit packets; no queue under declared capacity."),
        limitations=("Manual derivation for one declared case only.", "Does not replace the existing independently encoded fixture."),
    )


class LabBenchRepository:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(); self.root.mkdir(parents=True, exist_ok=True); self._lock = RLock()

    def _write(self, path: Path, value: object, *, exclusive: bool = False) -> None:
        payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            if exclusive and path.exists(): raise FileExistsError(f"append-only artifact already exists: {path.name}")
            temporary = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
            temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
            temporary.replace(path)

    def save(self, worksheet: LabWorksheet, *, record_history: bool = False) -> LabWorksheet:
        current = self.get(worksheet.worksheet_id, required=False)
        if current and current.created_at != worksheet.created_at: raise ValueError("worksheet creation identity cannot change")
        revision = (current.revision + 1) if record_history and current else worksheet.revision
        saved = worksheet.model_copy(update={"revision": revision, "updated_at": _now()})
        self._write(self.root / "worksheets" / f"{saved.worksheet_id}.json", saved)
        if record_history:
            self._write(self.root / "history" / saved.worksheet_id / f"revision-{revision:06d}.json", saved, exclusive=True)
        return saved

    def get(self, worksheet_id: str, *, required: bool = True) -> LabWorksheet | None:
        if not worksheet_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-" for char in worksheet_id): raise LabArtifactNotFound(worksheet_id)
        path = self.root / "worksheets" / f"{worksheet_id}.json"
        if not path.is_file():
            if required: raise LabArtifactNotFound(worksheet_id)
            return None
        return LabWorksheet.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self, case_id: str | None = None) -> tuple[LabWorksheet, ...]:
        values = tuple(LabWorksheet.model_validate_json(path.read_text(encoding="utf-8")) for path in sorted((self.root / "worksheets").glob("*.json")))
        return tuple(item for item in values if case_id is None or item.case_id == case_id)

    def promote(self, worksheet_id: str) -> LabWorksheet:
        current = self.get(worksheet_id); assert current is not None
        if current.state != LabState.SCRATCH: raise ValueError("only scratch material may be promoted to candidate reference")
        return self.save(current.model_copy(update={"state": LabState.CANDIDATE}), record_history=True)

    def freeze(self, request: FreezeRequest) -> FrozenOracle:
        worksheet = self.get(request.worksheet_id); assert worksheet is not None
        if worksheet.state != LabState.CANDIDATE: raise ValueError("only a candidate reference may be frozen")
        if not worksheet.case_id or not worksheet.case_version: raise ValueError("a frozen oracle must be associated with a validation case")
        if request.author_source in {ProvenanceClass.UC_DERIVED, ProvenanceClass.MODEL_SUGGESTION, ProvenanceClass.PRESENTATION_ONLY}:
            raise ValueError("this provenance classification is ineligible for formal oracle freezing")
        forbidden = [column.column_id for column in worksheet.table.columns if column.kind == ColumnKind.UC_OBSERVED or column.provenance in {ProvenanceClass.UC_DERIVED, ProvenanceClass.MODEL_SUGGESTION, ProvenanceClass.PRESENTATION_ONLY}]
        if forbidden: raise ValueError(f"UC-derived or non-authoritative columns are ineligible for freezing: {', '.join(forbidden)}")
        current_variables = declared_case_variables(worksheet.case_id)
        current_by_id = {item.variable_id: item for item in current_variables}
        linked_variables = tuple(item for item in worksheet.variables if item.linked)
        changed_dependencies = tuple(
            item.variable_id for item in linked_variables
            if item.variable_id not in current_by_id
            or item.value != current_by_id[item.variable_id].value
            or item.units != current_by_id[item.variable_id].units
            or item.configuration_identity != current_by_id[item.variable_id].configuration_identity
        )
        if changed_dependencies:
            raise ValueError(f"linked case configuration changed for {', '.join(changed_dependencies)}; detach literals or reapprove against current inputs")
        dependency_hash = _canonical_hash(tuple((item.variable_id, item.value, item.units, item.configuration_identity) for item in linked_variables))
        oracle_id = f"oracle-{worksheet.case_id.lower()}-{worksheet.worksheet_id}"
        versions = self.list_oracles(worksheet.case_id, oracle_id=oracle_id)
        version = max((item.version for item in versions), default=0) + 1
        formulas = tuple(f"{column.column_id}: {column.formula}" for column in worksheet.table.columns if column.formula)
        references = tuple(variable.variable_id for variable in worksheet.variables if variable.linked)
        detached = {variable.variable_id: variable.value for variable in worksheet.variables if not variable.linked and isinstance(variable.value, (int, float, str))}
        prehash = {
            "oracle_id": oracle_id, "version": version, "worksheet": worksheet.model_dump(mode="json"),
            "approval": request.approval_action, "author": request.author_source.value,
        }
        oracle = FrozenOracle(
            oracle_id=oracle_id, version=version, associated_case_id=worksheet.case_id,
            associated_case_version=worksheet.case_version, author_source=request.author_source,
            created_at=_now(), formula_table_provenance=formulas, units=tuple(sorted({column.units for column in worksheet.table.columns})),
            tick_convention=f"inclusive integer ticks {worksheet.table.tick_start}..{worksheet.table.tick_end}; {worksheet.table.evaluation_order}",
            input_references=references, detached_literal_values=detached, artifact_hash=_canonical_hash(prehash),
            approval_action=request.approval_action, notes=request.notes, limitations=request.limitations,
            source_worksheet_revision=worksheet.revision, dependency_hash=dependency_hash, worksheet=worksheet,
        )
        self._write(self.root / "oracles" / oracle_id / f"version-{version:06d}.json", oracle, exclusive=True)
        return oracle

    def list_oracles(self, case_id: str | None = None, *, oracle_id: str | None = None) -> tuple[FrozenOracle, ...]:
        root = self.root / "oracles"
        paths = sorted((root / oracle_id).glob("version-*.json")) if oracle_id else sorted(root.glob("*/version-*.json"))
        values = tuple(FrozenOracle.model_validate_json(path.read_text(encoding="utf-8")) for path in paths)
        return tuple(item for item in values if case_id is None or item.associated_case_id == case_id)


def compare_series(request: ComparisonRequest) -> ComparisonResult:
    mapping = request.mapping
    expected_unit = _quantity(1, mapping.expected_units); observed_unit = _quantity(1, mapping.observed_units)
    if expected_unit.dimensions != observed_unit.dimensions: raise LabExpressionError("expected and observed units are incompatible")
    observed = {tick - mapping.tick_offset: value * observed_unit.value / expected_unit.value for tick, value in zip(request.observed_ticks, request.observed_values)}
    compared_ticks: list[int] = []; differences: list[float] = []
    for tick, expected in zip(request.expected_ticks, request.expected_values):
        if tick not in observed: continue
        compared_ticks.append(tick); differences.append(expected - observed[tick])
    if not differences: raise LabExpressionError("the selected series have no aligned ticks")
    absolute = [abs(value) for value in differences]; tolerance = mapping.tolerance
    mismatch = [index for index, value in enumerate(absolute) if value > tolerance]
    formal = request.expected_state == LabState.FROZEN
    return ComparisonResult(
        formal=formal, label="Formal frozen-oracle comparison" if formal else "Informal comparison — not formal validation evidence.",
        exact=not mismatch, differences=tuple(differences), compared_ticks=tuple(compared_ticks),
        maximum_absolute_error=max(absolute), mean_absolute_error=sum(absolute) / len(absolute),
        first_mismatch_tick=compared_ticks[mismatch[0]] if mismatch else None, tick_offset=mapping.tick_offset,
        cumulative_bound_violations=len(mismatch), mismatched_rows=len(mismatch), tolerance=tolerance,
    )
