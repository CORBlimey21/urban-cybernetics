"""Versioned V1/V2 service-policy comparison on Boreenmanna geometry.

The package references the immutable V1 integrity audit, executes V2 in a
separate namespace, and keeps compiler identity independent of runtime policy.
It is evidence for a controlled synthetic experiment, not junction validation.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from time import perf_counter
from typing import Mapping, Self

from urban_cybernetics.compiler.model import canonical_json, stable_hash
from urban_cybernetics.compiler.osm_experiment import (
    BoreenmannaExperimentCompilation,
    compile_boreenmanna_experiment,
)
from urban_cybernetics.core import DemandDeclaration, EventType, Link
from urban_cybernetics.extensions.fractional_service_credit import (
    FRACTIONAL_CREDIT,
    FractionalServiceCreditConfig,
    FractionalServiceCreditLoadingEngine,
)
from urban_cybernetics.extensions.gate_aware_fractional_service import (
    GATE_AWARE_FRACTIONAL_SERVICE_MODE,
    GateAwareFractionalServiceConfig,
    GateAwareFractionalServiceLoadingEngine,
)
from .boreenmanna import (
    REPRESENTATION_MODES,
    SyntheticDemandScenario,
    build_boreenmanna_demand_scenarios,
)
from .boreenmanna_audit import (
    DEFAULT_PHASE_OFFSETS,
    AuditedRunManifest,
    BoreenmannaAuditIntegrityError,
    BoreenmannaIntegrityAuditPackage,
    DrainPolicy,
    RepresentationParityManifest,
    _periodic_fixture_engine,
    build_representation_parity_manifest,
    run_audited_case,
)


BOREENMANNA_GATE_AWARE_V2_COMPARISON_VERSION = (
    "uc.boreenmanna-gate-aware-v2-comparison.v1"
)
ANALYTICAL_SERVICE_POLICY_COMPARISON_VERSION = (
    "uc.fractional-service-policy-analytical-comparison.v1"
)


class BoreenmannaGateAwareV2IntegrityError(ValueError):
    """Raised for inconsistent V2 comparison evidence."""


@dataclass(frozen=True, slots=True)
class BoreenmannaGateAwareV2ComparisonPackage:
    """Tamper-detectable deterministic V2 results plus performance metadata."""

    compilation_package_hash: str
    executable_semantic_hash: str
    parent_v1_audit_file_sha256: str
    parent_v1_audit_deterministic_hash: str
    v1_baseline_json: str
    v2_core_runs: tuple[AuditedRunManifest, ...]
    parity_manifests: tuple[RepresentationParityManifest, ...]
    analytical_results_json: str
    phase_results_json: str
    performance_json: str
    version: str = BOREENMANNA_GATE_AWARE_V2_COMPARISON_VERSION
    deterministic_hash: str = ""
    package_hash: str = ""

    def __post_init__(self) -> None:
        if self.version != BOREENMANNA_GATE_AWARE_V2_COMPARISON_VERSION:
            raise BoreenmannaGateAwareV2IntegrityError(
                "unsupported gate-aware comparison version"
            )
        core = tuple(
            sorted(
                self.v2_core_runs,
                key=lambda item: (
                    str(item.deterministic["scenario_id"]),
                    str(item.deterministic["representation_mode"]),
                ),
            )
        )
        parity = tuple(sorted(self.parity_manifests, key=lambda item: item.family_id))
        object.__setattr__(self, "v2_core_runs", core)
        object.__setattr__(self, "parity_manifests", parity)
        for name in (
            "v1_baseline_json",
            "analytical_results_json",
            "phase_results_json",
            "performance_json",
        ):
            object.__setattr__(self, name, canonical_json(json.loads(getattr(self, name))))
        if any(
            item.deterministic["service_credit_mode"]
            != GATE_AWARE_FRACTIONAL_SERVICE_MODE
            for item in core
        ):
            raise BoreenmannaGateAwareV2IntegrityError(
                "V2 package contains a non-V2 core run"
            )
        expected_deterministic = stable_hash(
            "boreenmanna-gate-aware-v2-comparison",
            self._deterministic_payload(),
        )
        if self.deterministic_hash and self.deterministic_hash != expected_deterministic:
            raise BoreenmannaGateAwareV2IntegrityError(
                "V2 comparison deterministic hash mismatch"
            )
        object.__setattr__(self, "deterministic_hash", expected_deterministic)
        expected_package = stable_hash(
            "boreenmanna-gate-aware-v2-comparison-package",
            {
                "deterministic_hash": expected_deterministic,
                "performance": json.loads(self.performance_json),
            },
        )
        if self.package_hash and self.package_hash != expected_package:
            raise BoreenmannaGateAwareV2IntegrityError(
                "V2 comparison package hash mismatch"
            )
        object.__setattr__(self, "package_hash", expected_package)

    def _deterministic_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "compilation_package_hash": self.compilation_package_hash,
            "executable_semantic_hash": self.executable_semantic_hash,
            "parent_v1_audit_file_sha256": self.parent_v1_audit_file_sha256,
            "parent_v1_audit_deterministic_hash": self.parent_v1_audit_deterministic_hash,
            "v1_baseline": json.loads(self.v1_baseline_json),
            "v2_core_run_hashes": [item.deterministic_hash for item in self.v2_core_runs],
            "parity_manifests": [item.to_dict() for item in self.parity_manifests],
            "analytical_results": json.loads(self.analytical_results_json),
            "phase_results": json.loads(self.phase_results_json),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self._deterministic_payload(),
            "v2_core_runs": [item.to_dict() for item in self.v2_core_runs],
            "performance": json.loads(self.performance_json),
            "deterministic_hash": self.deterministic_hash,
            "package_hash": self.package_hash,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        result = cls(
            compilation_package_hash=str(payload["compilation_package_hash"]),
            executable_semantic_hash=str(payload["executable_semantic_hash"]),
            parent_v1_audit_file_sha256=str(payload["parent_v1_audit_file_sha256"]),
            parent_v1_audit_deterministic_hash=str(
                payload["parent_v1_audit_deterministic_hash"]
            ),
            v1_baseline_json=canonical_json(payload["v1_baseline"]),
            v2_core_runs=tuple(
                AuditedRunManifest.from_dict(item)
                for item in payload["v2_core_runs"]  # type: ignore[index]
            ),
            parity_manifests=tuple(
                RepresentationParityManifest.from_dict(item)
                for item in payload["parity_manifests"]  # type: ignore[index]
            ),
            analytical_results_json=canonical_json(payload["analytical_results"]),
            phase_results_json=canonical_json(payload["phase_results"]),
            performance_json=canonical_json(payload["performance"]),
            version=str(payload["version"]),
            deterministic_hash=str(payload.get("deterministic_hash", "")),
            package_hash=str(payload.get("package_hash", "")),
        )
        declared = tuple(str(item) for item in payload["v2_core_run_hashes"])  # type: ignore[index]
        if declared != tuple(item.deterministic_hash for item in result.v2_core_runs):
            raise BoreenmannaGateAwareV2IntegrityError("V2 core hash list mismatch")
        return result

    @classmethod
    def from_json(cls, payload: str) -> Self:
        return cls.from_dict(json.loads(payload))


def _physical_service_ticks(engine) -> tuple[int, ...]:
    return tuple(
        event.physical_tick
        for event in engine.event_log
        if event.event_type == EventType.LINK_ENTRY and event.entity_id == "D"
    )


def analytical_v1_v2_service_comparison(
    *,
    saturated_horizon_ticks: int = 80,
    gated_horizon_ticks: int = 160,
    offsets: tuple[int, ...] = (0, 1, 2, 3, 5, 10),
) -> dict[str, object]:
    """Execute compact analytical policies before any Cork comparison."""

    always_green = []
    for rate in (0.25, 0.4, 0.5, 0.75, 1.0, 1.5):
        row: dict[str, object] = {
            "rate_packets_per_tick": rate,
            "horizon_ticks": saturated_horizon_ticks,
            "expected_service": int(rate * saturated_horizon_ticks),
        }
        for label, mode in (
            ("v1", FRACTIONAL_CREDIT),
            ("v2", GATE_AWARE_FRACTIONAL_SERVICE_MODE),
        ):
            link = Link(
                link_id="L",
                free_flow_ticks=1,
                declared_sending_capacity_per_tick=max(1, ceil(rate)),
                declared_receiving_capacity_per_tick=max(1, ceil(rate)),
                declared_storage_capacity_packets=500,
                length_m=10.0,
                lane_count=1,
                free_flow_speed_mps=10.0,
                jam_density_veh_per_km_per_lane=50_000.0,
                backward_wave_speed_mps=10.0,
                capacity_veh_per_hour_per_lane=rate * 3_600.0,
                tick_duration_seconds=1.0,
            )
            if mode == FRACTIONAL_CREDIT:
                engine = FractionalServiceCreditLoadingEngine(
                    links={"L": link},
                    fractional_service_credit_config=FractionalServiceCreditConfig(
                        FRACTIONAL_CREDIT, (("L", rate),)
                    ),
                    executable_semantic_hash="saturated-single-link",
                )
            else:
                engine = GateAwareFractionalServiceLoadingEngine(
                    links={"L": link},
                    gate_aware_fractional_service_config=GateAwareFractionalServiceConfig(
                        (("L", rate),)
                    ),
                    executable_semantic_hash="saturated-single-link",
                )
            for index in range(200):
                engine.instantiate(
                    DemandDeclaration(f"green:{label}:{rate}:{index}", 0, ("L",))
                )
            for _ in range(saturated_horizon_ticks):
                engine.step()
            ticks = tuple(
                event.physical_tick
                for event in engine.event_log
                if event.event_type == EventType.LINK_EXIT and event.entity_id == "L"
            )
            row[label] = {
                "service_count": len(ticks),
                "realized_rate_packets_per_tick": len(ticks) / saturated_horizon_ticks,
                "first_service_ticks": list(ticks[:12]),
                "configuration_hash": (
                    engine.fractional_service_credit_config.config_hash
                    if label == "v1"
                    else engine.gate_aware_fractional_service_config.config_hash
                ),
                "evidence_hash": engine.fractional_service_credit_evidence_hash,
            }
        always_green.append(row)

    gated = []
    for offset in offsets:
        for label, mode in (
            ("v1", FRACTIONAL_CREDIT),
            ("v2", GATE_AWARE_FRACTIONAL_SERVICE_MODE),
        ):
            engine, _, _ = _periodic_fixture_engine(
                rate=0.25,
                cycle_ticks=4,
                green_ticks=2,
                offset_ticks=offset,
                service_mode=mode,
            )
            for index in range(200):
                engine.instantiate(
                    DemandDeclaration(f"ggrr:{label}:{offset}:{index}", 0, ("U", "D"))
                )
            for _ in range(gated_horizon_ticks):
                engine.step()
            ticks = _physical_service_ticks(engine)
            gated.append(
                {
                    "policy": label,
                    "offset_ticks": offset,
                    "service_count": len(ticks),
                    "realized_rate_packets_per_tick": len(ticks) / gated_horizon_ticks,
                    "expected_v2_asymptotic_rate_packets_per_tick": 0.125,
                    "first_service_ticks": list(ticks[:12]),
                    "queue_growth": 200 - len(ticks),
                    "configuration_hash": (
                        engine.fractional_service_credit_config.config_hash
                        if label == "v1"
                        else engine.gate_aware_fractional_service_config.config_hash
                    ),
                    "evidence_hash": engine.fractional_service_credit_evidence_hash,
                    "conservation_passed": engine.check_conservation(),
                }
            )
    payload = {
        "version": ANALYTICAL_SERVICE_POLICY_COMPARISON_VERSION,
        "permanently_green": always_green,
        "quarter_rate_ggrr": gated,
        "interpretations": {
            "v1": "clock_driven_transient_whole_opportunities_expire",
            "v2": "gate_aware_accumulation_red_adds_zero_fraction_remainder_preserved",
        },
    }
    return {
        **payload,
        "analytical_hash": stable_hash("fractional-policy-analytical-comparison", payload),
    }


def _phase_sensitivity(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["scenario_id"]), str(row["representation_mode"]))].append(row)
    result = []
    for (scenario_id, representation), values in sorted(grouped.items()):
        completions = [int(item["completed_at_evaluation"]) for item in values]
        clearance = [int(item["final_completion_tick"]) for item in values]
        delays = [float(item["mean_queue_delay_ticks"]) for item in values]
        result.append(
            {
                "scenario_id": scenario_id,
                "representation_mode": representation,
                "evaluation_completion_range": max(completions) - min(completions),
                "clearance_tick_range": max(clearance) - min(clearance),
                "mean_queue_delay_range": max(delays) - min(delays),
            }
        )
    return result


def run_boreenmanna_gate_aware_v2_comparison(
    source_path: str | Path,
    parent_v1_audit_path: str | Path,
    *,
    phase_offsets: tuple[int, ...] = DEFAULT_PHASE_OFFSETS,
    drain_policy: DrainPolicy | None = None,
) -> tuple[
    BoreenmannaExperimentCompilation,
    tuple[SyntheticDemandScenario, ...],
    BoreenmannaGateAwareV2ComparisonPackage,
]:
    """Run six replay-checked V2 cores plus a compact offset sweep."""

    policy = drain_policy or DrainPolicy()
    parent_path = Path(parent_v1_audit_path)
    parent_bytes = parent_path.read_bytes()
    parent_sha = hashlib.sha256(parent_bytes).hexdigest()
    parent = BoreenmannaIntegrityAuditPackage.from_json(parent_bytes.decode("utf-8"))
    compilation = compile_boreenmanna_experiment(source_path)
    if compilation.package.package_hash != parent.compilation_package_hash:
        raise BoreenmannaGateAwareV2IntegrityError(
            "V2 compilation identity differs from the parent V1 audit"
        )
    executable = compilation.synthetic_result.require_executable()
    scenarios = build_boreenmanna_demand_scenarios(compilation)
    started = perf_counter()
    core = tuple(
        run_audited_case(
            compilation,
            scenario,
            representation,
            GATE_AWARE_FRACTIONAL_SERVICE_MODE,
            drain_policy=policy,
            verify_replay=True,
        )
        for scenario in scenarios
        for representation in REPRESENTATION_MODES
    )
    phase_rows = []
    parity = []
    for scenario in scenarios:
        for offset in phase_offsets:
            parity.append(
                build_representation_parity_manifest(
                    compilation,
                    scenario,
                    GATE_AWARE_FRACTIONAL_SERVICE_MODE,
                    offset_ticks=offset,
                    drain_policy=policy,
                )
            )
            for representation in REPRESENTATION_MODES:
                run = run_audited_case(
                    compilation,
                    scenario,
                    representation,
                    GATE_AWARE_FRACTIONAL_SERVICE_MODE,
                    offset_ticks=offset,
                    drain_policy=policy,
                    verify_replay=False,
                )
                deterministic = run.deterministic
                evaluation = deterministic["evaluation_metrics"]
                drain = deterministic["drain_outcome"]
                phase_rows.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "representation_mode": representation,
                        "offset_ticks": offset,
                        "completed_at_evaluation": evaluation["completed_throughput"],
                        "eventually_completed": drain["eventually_completed"],
                        "mean_queue_delay_ticks": evaluation["mean_queue_delay_ticks"],
                        "peak_queue": evaluation["peak_queue"],
                        "movement_throughput": evaluation["movement_throughput"],
                        "final_completion_tick": drain["final_completion_tick"],
                        "fractional_credit_evidence_count": deterministic[
                            "evidence_volume"
                        ]["fractional_credit_evidence_count"],
                        "blocked_transfer_requests_by_reason": evaluation[
                            "blocked_transfer_requests_by_reason"
                        ],
                        "deterministic_run_hash": run.deterministic_hash,
                    }
                )
    baseline = [
        item.deterministic
        for item in parent.core_runs
        if item.deterministic["service_credit_mode"] == FRACTIONAL_CREDIT
    ]
    phase_payload = {
        "policy": GATE_AWARE_FRACTIONAL_SERVICE_MODE,
        "offsets_ticks": list(phase_offsets),
        "runs": phase_rows,
        "sensitivity_summary": _phase_sensitivity(phase_rows),
    }
    package = BoreenmannaGateAwareV2ComparisonPackage(
        compilation_package_hash=compilation.package.package_hash,
        executable_semantic_hash=executable.executable_semantic_hash,
        parent_v1_audit_file_sha256=parent_sha,
        parent_v1_audit_deterministic_hash=parent.deterministic_hash,
        v1_baseline_json=canonical_json(baseline),
        v2_core_runs=core,
        parity_manifests=tuple(parity),
        analytical_results_json=canonical_json(analytical_v1_v2_service_comparison()),
        phase_results_json=canonical_json(phase_payload),
        performance_json=canonical_json(
            {
                "measurement_class": "machine_dependent",
                "complete_v2_comparison_wall_clock_seconds": perf_counter() - started,
                "v2_core_performance": [item.performance for item in core],
            }
        ),
    )
    return compilation, scenarios, package


def write_boreenmanna_gate_aware_v2_outputs(
    package: BoreenmannaGateAwareV2ComparisonPackage,
    output_directory: str | Path,
) -> tuple[Path, ...]:
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    package_path = directory / "boreenmanna_gate_aware_v2_comparison_v1.json"
    core_path = directory / "boreenmanna_gate_aware_v2_core_v1.csv"
    phase_path = directory / "boreenmanna_gate_aware_v2_phase_v1.csv"
    analytical_path = directory / "fractional_service_v1_v2_analytical_v1.json"
    package_path.write_text(package.to_json(), encoding="utf-8")
    analytical_path.write_text(
        json.dumps(json.loads(package.analytical_results_json), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    core_fields = (
        "scenario_id",
        "representation_mode",
        "completed_at_evaluation",
        "incomplete_at_evaluation",
        "eventually_completed",
        "drain_duration_ticks",
        "final_completion_tick",
        "mean_queue_delay_ticks",
        "peak_queue",
        "canonical_event_count",
        "credit_evidence_count",
        "wall_clock_seconds",
        "replay_wall_clock_seconds",
        "peak_memory_bytes",
        "deterministic_evidence_bytes",
        "deterministic_hash",
    )
    with core_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=core_fields)
        writer.writeheader()
        for run in package.v2_core_runs:
            data = run.deterministic
            evaluation = data["evaluation_metrics"]
            drain = data["drain_outcome"]
            volume = data["evidence_volume"]
            writer.writerow(
                {
                    "scenario_id": data["scenario_id"],
                    "representation_mode": data["representation_mode"],
                    "completed_at_evaluation": evaluation["completed_throughput"],
                    "incomplete_at_evaluation": evaluation["incomplete_packets"],
                    "eventually_completed": drain["eventually_completed"],
                    "drain_duration_ticks": drain["drain_duration_ticks"],
                    "final_completion_tick": drain["final_completion_tick"],
                    "mean_queue_delay_ticks": evaluation["mean_queue_delay_ticks"],
                    "peak_queue": evaluation["peak_queue"],
                    "canonical_event_count": evaluation["canonical_event_count"],
                    "credit_evidence_count": volume["fractional_credit_evidence_count"],
                    "wall_clock_seconds": run.performance["wall_clock_seconds"],
                    "replay_wall_clock_seconds": run.performance[
                        "replay_wall_clock_seconds"
                    ],
                    "peak_memory_bytes": run.performance["peak_memory_bytes"],
                    "deterministic_evidence_bytes": volume[
                        "total_deterministic_artifact_bytes"
                    ],
                    "deterministic_hash": run.deterministic_hash,
                }
            )
    phase = json.loads(package.phase_results_json)
    phase_fields = (
        "scenario_id",
        "representation_mode",
        "offset_ticks",
        "completed_at_evaluation",
        "eventually_completed",
        "mean_queue_delay_ticks",
        "peak_queue",
        "final_completion_tick",
        "fractional_credit_evidence_count",
        "deterministic_run_hash",
    )
    with phase_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=phase_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(phase["runs"])
    return package_path, core_path, phase_path, analytical_path
