# SPDX-License-Identifier: MPL-2.0
"""Versioned V2/V3 readiness ablation on synthetic Boreenmanna controls."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from math import exp, floor
from pathlib import Path
from time import perf_counter
from typing import Mapping, Self

from urban_cybernetics.compiler.model import canonical_json, stable_hash
from urban_cybernetics.compiler.osm_experiment import (
    BoreenmannaExperimentCompilation,
    compile_boreenmanna_experiment,
)
from urban_cybernetics.core import DemandDeclaration, EventType
from urban_cybernetics.extensions.discharge_readiness_fractional_service import (
    COMPACT_EVIDENCE,
    DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE,
    FORENSIC_EVIDENCE,
    SUMMARY_EVIDENCE,
    DischargeReadinessConfig,
    ExponentialDischargeReadinessProvider,
    discharge_readiness_config_for_executable,
)
from urban_cybernetics.extensions.fractional_service_credit import FRACTIONAL_CREDIT
from urban_cybernetics.extensions.gate_aware_fractional_service import (
    GATE_AWARE_FRACTIONAL_SERVICE_MODE,
    ServiceRateContext,
)

from .boreenmanna import (
    REPRESENTATION_MODES,
    SyntheticDemandScenario,
    build_boreenmanna_demand_scenarios,
)
from .boreenmanna_audit import (
    AuditedRunManifest,
    BoreenmannaAuditIntegrityError,
    DrainPolicy,
    RepresentationParityManifest,
    _periodic_fixture_engine,
    build_representation_parity_manifest,
    run_audited_case,
)
from .boreenmanna_gate_aware_v2 import BoreenmannaGateAwareV2ComparisonPackage


BOREENMANNA_DISCHARGE_READINESS_V3_VERSION = (
    "uc.boreenmanna-discharge-readiness-v3-experiment.v1"
)
V3_ANALYTICAL_VALIDATION_VERSION = "uc.discharge-readiness-analytical-validation.v1"
V3_BASELINE_TAU_GREEN_SECONDS = 2.0
V3_BASELINE_TAU_RED_SECONDS = 10.0
V3_GREEN_SENSITIVITY_SECONDS = (1.0, 2.0, 3.0)
V3_RED_SENSITIVITY_SECONDS = (2.0, 5.0, 10.0, 20.0, 40.0, None)


# Captured before the immutable signal-hash memoization patch. Cumulative
# categories overlap and therefore must not be summed as percentages.
V2_PROFILE_BEFORE_PATCH = {
    "measurement_class": "machine_dependent_cprofile",
    "cases": [
        {
            "scenario": "moderate",
            "representation": "explicit_lane_group_fifo",
            "profiled_seconds": 1.050,
            "function_calls": 2_079_313,
            "json_encoding_cumulative_seconds": 0.594,
            "fixed_time_evaluation_cumulative_seconds": 0.494,
            "signal_configuration_hash_cumulative_seconds": 0.474,
            "v2_step_cumulative_seconds": 0.704,
            "evidence_object_construction_cumulative_seconds": 0.060,
        },
        {
            "scenario": "stress",
            "representation": "shared_link_fifo",
            "profiled_seconds": 8.345,
            "function_calls": 13_964_575,
            "json_encoding_cumulative_seconds": 5.143,
            "fixed_time_evaluation_cumulative_seconds": 6.065,
            "signal_configuration_hash_cumulative_seconds": 5.829,
            "v2_step_cumulative_seconds": 7.452,
            "evidence_object_construction_cumulative_seconds": 0.259,
        },
    ],
    "interpretation": (
        "repeated immutable fixed-time configuration hashing dominated the profile; "
        "wide evidence construction was a smaller CPU share but a major retention and "
        "serialization cost"
    ),
    "non_additive_cumulative_categories": True,
}

V2_PROFILE_AFTER_PATCH = {
    "measurement_class": "machine_dependent_cprofile",
    "cases": [
        {
            "scenario": "moderate",
            "representation": "explicit_lane_group_fifo",
            "profiled_seconds": 0.583964,
            "function_calls": 1_437_859,
            "json_encoding_cumulative_seconds": 0.259328,
            "fixed_time_evaluation_cumulative_seconds": 0.004783,
            "signal_configuration_hash_cumulative_seconds": 0.000598,
            "v2_step_cumulative_seconds": 0.282229,
            "physical_event_log_hash": "d6acf47afe6efabab5ad590a4649d44e46d321273a8204969b61423dea54c55b",
        },
        {
            "scenario": "stress",
            "representation": "shared_link_fifo",
            "profiled_seconds": 2.399880,
            "function_calls": 5_981_244,
            "json_encoding_cumulative_seconds": 0.981544,
            "fixed_time_evaluation_cumulative_seconds": 0.055901,
            "signal_configuration_hash_cumulative_seconds": 0.000605,
            "v2_step_cumulative_seconds": 1.580536,
            "physical_event_log_hash": "a06edc991693e3becf81bd9dd4e6799114202f6658f4781a8b421355daa453f1",
        },
    ],
    "patch": "memoize immutable fixed-time signal-plan configuration hashes",
    "non_additive_cumulative_categories": True,
}

V3_PROFILE_AFTER_PATCHES = {
    "measurement_class": "machine_dependent_cprofile",
    "cases": [
        {
            "scenario": "moderate",
            "representation": "explicit_lane_group_fifo",
            "profiled_seconds": 0.626574,
            "function_calls": 1_466_500,
            "json_encoding_cumulative_seconds": 0.275399,
            "v3_step_cumulative_seconds": 0.285740,
            "loading_step_cumulative_seconds": 0.093779,
            "readiness_multiplier_cumulative_seconds": 0.004079,
            "readiness_evidence_construction_cumulative_seconds": 0.013196,
            "logical_digest_cumulative_seconds": 0.064011,
            "physical_config_hash_cumulative_seconds": 0.000547,
        },
        {
            "scenario": "stress",
            "representation": "explicit_lane_group_fifo",
            "profiled_seconds": 1.537171,
            "function_calls": 3_691_286,
            "json_encoding_cumulative_seconds": 0.632755,
            "v3_step_cumulative_seconds": 0.832453,
            "loading_step_cumulative_seconds": 0.391064,
            "readiness_multiplier_cumulative_seconds": 0.009318,
            "readiness_evidence_construction_cumulative_seconds": 0.031146,
            "logical_digest_cumulative_seconds": 0.147308,
            "physical_config_hash_cumulative_seconds": 0.001268,
        },
    ],
    "patches": [
        "memoize immutable fixed-time signal-plan configuration hashes",
        "memoize immutable V3 physical and recording configuration hashes",
    ],
    "non_additive_cumulative_categories": True,
}


class BoreenmannaV3IntegrityError(ValueError):
    """Raised for inconsistent V3 experiment evidence."""


@dataclass(frozen=True, slots=True)
class BoreenmannaDischargeReadinessV3Package:
    compilation_package_hash: str
    executable_semantic_hash: str
    parent_v2_file_sha256: str
    parent_v2_deterministic_hash: str
    v2_baseline_json: str
    v3_core_runs: tuple[AuditedRunManifest, ...]
    parity_manifests: tuple[RepresentationParityManifest, ...]
    analytical_results_json: str
    sensitivity_results_json: str
    benchmark_deterministic_json: str
    performance_json: str
    version: str = BOREENMANNA_DISCHARGE_READINESS_V3_VERSION
    deterministic_hash: str = ""
    package_hash: str = ""

    def __post_init__(self) -> None:
        if self.version != BOREENMANNA_DISCHARGE_READINESS_V3_VERSION:
            raise BoreenmannaV3IntegrityError("unsupported V3 package version")
        core = tuple(
            sorted(
                self.v3_core_runs,
                key=lambda item: (
                    str(item.deterministic["scenario_id"]),
                    str(item.deterministic["representation_mode"]),
                ),
            )
        )
        parity = tuple(sorted(self.parity_manifests, key=lambda item: item.family_id))
        object.__setattr__(self, "v3_core_runs", core)
        object.__setattr__(self, "parity_manifests", parity)
        for name in (
            "v2_baseline_json",
            "analytical_results_json",
            "sensitivity_results_json",
            "benchmark_deterministic_json",
            "performance_json",
        ):
            object.__setattr__(self, name, canonical_json(json.loads(getattr(self, name))))
        if any(
            item.deterministic["service_credit_mode"]
            != DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE
            for item in core
        ):
            raise BoreenmannaV3IntegrityError("V3 core contains another policy")
        expected = stable_hash(
            "boreenmanna-discharge-readiness-v3",
            self._deterministic_payload(),
        )
        if self.deterministic_hash and self.deterministic_hash != expected:
            raise BoreenmannaV3IntegrityError("V3 deterministic hash mismatch")
        object.__setattr__(self, "deterministic_hash", expected)
        package_hash = stable_hash(
            "boreenmanna-discharge-readiness-v3-package",
            {
                "deterministic_hash": expected,
                "performance": json.loads(self.performance_json),
            },
        )
        if self.package_hash and self.package_hash != package_hash:
            raise BoreenmannaV3IntegrityError("V3 package hash mismatch")
        object.__setattr__(self, "package_hash", package_hash)

    def _deterministic_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "compilation_package_hash": self.compilation_package_hash,
            "executable_semantic_hash": self.executable_semantic_hash,
            "parent_v2_file_sha256": self.parent_v2_file_sha256,
            "parent_v2_deterministic_hash": self.parent_v2_deterministic_hash,
            "v2_baseline": json.loads(self.v2_baseline_json),
            "v3_core_run_hashes": [item.deterministic_hash for item in self.v3_core_runs],
            "parity_manifests": [item.to_dict() for item in self.parity_manifests],
            "analytical_results": json.loads(self.analytical_results_json),
            "sensitivity_results": json.loads(self.sensitivity_results_json),
            "benchmark_deterministic": json.loads(self.benchmark_deterministic_json),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self._deterministic_payload(),
            "v3_core_runs": [item.to_dict() for item in self.v3_core_runs],
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
            parent_v2_file_sha256=str(payload["parent_v2_file_sha256"]),
            parent_v2_deterministic_hash=str(payload["parent_v2_deterministic_hash"]),
            v2_baseline_json=canonical_json(payload["v2_baseline"]),
            v3_core_runs=tuple(
                AuditedRunManifest.from_dict(item)
                for item in payload["v3_core_runs"]  # type: ignore[index]
            ),
            parity_manifests=tuple(
                RepresentationParityManifest.from_dict(item)
                for item in payload["parity_manifests"]  # type: ignore[index]
            ),
            analytical_results_json=canonical_json(payload["analytical_results"]),
            sensitivity_results_json=canonical_json(payload["sensitivity_results"]),
            benchmark_deterministic_json=canonical_json(
                payload["benchmark_deterministic"]
            ),
            performance_json=canonical_json(payload["performance"]),
            version=str(payload["version"]),
            deterministic_hash=str(payload.get("deterministic_hash", "")),
            package_hash=str(payload.get("package_hash", "")),
        )
        declared = tuple(str(item) for item in payload["v3_core_run_hashes"])  # type: ignore[index]
        if declared != tuple(item.deterministic_hash for item in result.v3_core_runs):
            raise BoreenmannaV3IntegrityError("V3 core hash list mismatch")
        return result

    @classmethod
    def from_json(cls, payload: str) -> Self:
        return cls.from_dict(json.loads(payload))


def _context(tick: int, gate: float, *, demand: bool = True) -> ServiceRateContext:
    return ServiceRateContext(
        tick=tick,
        service_account_id="effective-rate:sending:L",
        service_domain_id="L",
        service_domain_type="link_sending",
        base_continuous_rate_packets_per_tick=1.0,
        control_gate_state="green" if gate else "red",
        control_availability_factor=gate,
        relevant_movement_ids=("movement:L->D",) if demand else (),
        relevant_packet_ids=("P",) if demand else (),
    )


def _analytical_config(
    *,
    dt: float,
    tau_green: float,
    tau_red: float | None,
    initial: float,
) -> DischargeReadinessConfig:
    return DischargeReadinessConfig(
        continuous_capacity_by_link=(("L", 1.0),),
        tick_duration_seconds_by_link=(("L", dt),),
        controlled_readiness_link_ids=("L",),
        tau_green_seconds=tau_green,
        tau_red_seconds=tau_red,
        default_initial_readiness=initial,
        initial_readiness_by_domain=(("L", initial),),
        evidence_mode=SUMMARY_EVIDENCE,
    )


def _service_ticks(engine, horizon: int, label: str) -> tuple[int, ...]:
    for index in range(max(300, horizon * 2)):
        engine.instantiate(DemandDeclaration(f"{label}:{index}", 0, ("U", "D")))
    for _ in range(horizon):
        engine.step()
    return tuple(
        event.physical_tick
        for event in engine.event_log
        if event.event_type == EventType.LINK_ENTRY and event.entity_id == "D"
    )


def analytical_v3_validation() -> dict[str, object]:
    startup = []
    for tau_green in V3_GREEN_SENSITIVITY_SECONDS:
        for dt in (0.5, 1.0, 2.0):
            provider = ExponentialDischargeReadinessProvider(
                _analytical_config(
                    dt=dt, tau_green=tau_green, tau_red=10.0, initial=0.0
                )
            )
            duration = 40.0
            means = [
                provider.multiplier(_context(tick, 1.0))
                for tick in range(1, int(duration / dt) + 1)
            ]
            integrated_lost = sum(1.0 - value for value in means) * dt
            exact_lost = tau_green * (1.0 - exp(-duration / tau_green))
            integrated_readiness = duration - integrated_lost
            startup.append(
                {
                    "tau_green_seconds": tau_green,
                    "tick_duration_seconds": dt,
                    "closing_readiness": provider.readiness_by_domain["L"],
                    "integrated_startup_lost_seconds": integrated_lost,
                    "exact_startup_lost_seconds": exact_lost,
                    "absolute_integration_error_seconds": abs(integrated_lost - exact_lost),
                    "whole_packets_at_0_75_veh_per_second": floor(
                        0.75 * integrated_readiness
                    ),
                }
            )
    red_decay = []
    for tau_red in V3_RED_SENSITIVITY_SECONDS:
        for duration in (2, 10, 40):
            provider = ExponentialDischargeReadinessProvider(
                _analytical_config(
                    dt=1.0, tau_green=2.0, tau_red=tau_red, initial=1.0
                )
            )
            for tick in range(1, duration + 1):
                provider.multiplier(_context(tick, 0.0))
            red_decay.append(
                {
                    "tau_red_seconds": "infinite" if tau_red is None else tau_red,
                    "red_duration_seconds": duration,
                    "closing_readiness": provider.readiness_by_domain["L"],
                    "expected_readiness": (
                        1.0 if tau_red is None else exp(-duration / tau_red)
                    ),
                }
            )
    ggrr = []
    for offset in (0, 1, 2, 3):
        for policy in (
            FRACTIONAL_CREDIT,
            GATE_AWARE_FRACTIONAL_SERVICE_MODE,
            DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE,
        ):
            v3_config = None
            if policy == DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE:
                v3_config = DischargeReadinessConfig(
                    continuous_capacity_by_link=(("U", 0.25), ("D", 10.0)),
                    tick_duration_seconds_by_link=(("U", 1.0), ("D", 1.0)),
                    controlled_readiness_link_ids=("U",),
                    tau_green_seconds=2.0,
                    tau_red_seconds=10.0,
                    initial_readiness_by_domain=(("U", 1.0),),
                    evidence_mode=SUMMARY_EVIDENCE,
                )
            engine, _, _ = _periodic_fixture_engine(
                rate=0.25,
                cycle_ticks=4,
                green_ticks=2,
                offset_ticks=offset,
                service_mode=policy,
                v3_config=v3_config,
            )
            ticks = _service_ticks(engine, 320, f"ggrr:{policy}:{offset}")
            ggrr.append(
                {
                    "policy": policy,
                    "offset_ticks": offset,
                    "service_count": len(ticks),
                    "realized_rate": len(ticks) / 320,
                    "first_service_ticks": list(ticks[:12]),
                }
            )
    collapse = []
    for offset in (0, 1, 2, 3):
        v2, _, _ = _periodic_fixture_engine(
            rate=0.25,
            cycle_ticks=4,
            green_ticks=2,
            offset_ticks=offset,
            service_mode=GATE_AWARE_FRACTIONAL_SERVICE_MODE,
        )
        v3_config = DischargeReadinessConfig(
            continuous_capacity_by_link=(("U", 0.25), ("D", 10.0)),
            tick_duration_seconds_by_link=(("U", 1.0), ("D", 1.0)),
            controlled_readiness_link_ids=("U",),
            tau_green_seconds=2.0,
            tau_red_seconds=None,
            initial_readiness_by_domain=(("U", 1.0),),
            evidence_mode=SUMMARY_EVIDENCE,
        )
        v3, _, _ = _periodic_fixture_engine(
            rate=0.25,
            cycle_ticks=4,
            green_ticks=2,
            offset_ticks=offset,
            service_mode=DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE,
            v3_config=v3_config,
        )
        _service_ticks(v2, 160, f"collapse:v2:{offset}")
        _service_ticks(v3, 160, f"collapse:v3:{offset}")
        event_payload = lambda engine: [
            [e.sequence_number, e.packet_id, e.event_type.value, e.entity_id, e.physical_tick]
            for e in engine.event_log
        ]
        collapse.append(
            {
                "offset_ticks": offset,
                "physical_events_identical": v2.event_log == v3.event_log,
                "v2_event_hash": stable_hash("collapse-events", event_payload(v2)),
                "v3_event_hash": stable_hash("collapse-events", event_payload(v3)),
            }
        )
    payload = {
        "version": V3_ANALYTICAL_VALIDATION_VERSION,
        "startup_lost_time": startup,
        "red_decay": red_decay,
        "ggrr": ggrr,
        "collapse_to_v2": collapse,
    }
    return {**payload, "analytical_hash": stable_hash("v3-analytical-validation", payload)}


def _readiness_totals(deterministic: Mapping[str, object], *, evaluation: bool) -> dict[str, object]:
    key = "evaluation_readiness_summary" if evaluation else "readiness_summary"
    summary = deterministic[key]  # type: ignore[index]
    domains = summary["domains"]  # type: ignore[index]
    green_ticks = sum(int(item["green_ticks"]) for item in domains)
    weighted_mean = sum(
        float(item["mean_readiness_during_green"]) * int(item["green_ticks"])
        for item in domains
        if item["mean_readiness_during_green"] is not None
    )
    transitions = [
        float(value)
        for item in domains
        for value in item["red_to_green_opening_readiness"]
    ]
    return {
        "startup_lost_service": sum(float(item["startup_lost_service"]) for item in domains),
        "nominal_enabled_allowance": sum(
            float(item["nominal_enabled_allowance"]) for item in domains
        ),
        "effective_allowance": sum(float(item["effective_allowance"]) for item in domains),
        "mean_readiness_during_green": weighted_mean / green_ticks if green_ticks else None,
        "mean_red_to_green_opening_readiness": (
            sum(transitions) / len(transitions) if transitions else None
        ),
        "red_to_green_transition_count": len(transitions),
        "physically_consumed_service": sum(
            int(item["physically_consumed_service"]) for item in domains
        ),
        "expired_whole_service": sum(int(item["expired_whole_service"]) for item in domains),
    }


def _sensitivity_row(
    label: str,
    tau_green: float,
    tau_red: float | None,
    run: AuditedRunManifest,
) -> dict[str, object]:
    data = run.deterministic
    evaluation = data["evaluation_metrics"]
    drain = data["drain_outcome"]
    blocked = dict(evaluation["blocked_transfer_requests_by_reason"])
    return {
        "parameter_case_id": label,
        "tau_green_seconds": tau_green,
        "tau_red_seconds": "infinite" if tau_red is None else tau_red,
        "scenario_id": data["scenario_id"],
        "representation_mode": data["representation_mode"],
        "completed_at_evaluation": evaluation["completed_throughput"],
        "eventually_completed": drain["eventually_completed"],
        "final_completion_tick": drain["final_completion_tick"],
        "mean_queue_delay_ticks": evaluation["mean_queue_delay_ticks"],
        "queue_delay_by_boundary": evaluation["queue_delay_by_boundary"],
        "peak_queue": evaluation["peak_queue"],
        "movement_throughput": evaluation["movement_throughput"],
        "signal_blocks": blocked.get("signal_gate_closed", 0),
        "fifo_blocks": blocked.get("upstream_fifo_blocked", 0),
        "spillback_duration_ticks": evaluation["spillback_duration_ticks"],
        "canonical_event_count": evaluation["canonical_event_count"],
        "physical_event_log_hash": data["physical_event_log_hash"],
        "logical_evidence_digest": data["readiness_logical_evidence_digest"],
        "readiness": _readiness_totals(data, evaluation=True),
        "deterministic_run_hash": run.deterministic_hash,
    }


def _parameter_cases() -> tuple[tuple[str, float, float | None], ...]:
    cases = [
        (f"tau-green-{value:g}-tau-red-10", value, 10.0)
        for value in V3_GREEN_SENSITIVITY_SECONDS
    ]
    cases.extend(
        (
            f"tau-green-2-tau-red-{'infinite' if value is None else f'{value:g}'}",
            2.0,
            value,
        )
        for value in V3_RED_SENSITIVITY_SECONDS
        if value != 10.0
    )
    return tuple(cases)


def run_boreenmanna_discharge_readiness_v3(
    source_path: str | Path,
    parent_v2_path: str | Path,
    *,
    drain_policy: DrainPolicy | None = None,
) -> tuple[
    BoreenmannaExperimentCompilation,
    tuple[SyntheticDemandScenario, ...],
    BoreenmannaDischargeReadinessV3Package,
]:
    policy = drain_policy or DrainPolicy()
    parent_bytes = Path(parent_v2_path).read_bytes()
    parent_sha = hashlib.sha256(parent_bytes).hexdigest()
    parent = BoreenmannaGateAwareV2ComparisonPackage.from_json(
        parent_bytes.decode("utf-8")
    )
    compilation = compile_boreenmanna_experiment(source_path)
    if compilation.package.package_hash != parent.compilation_package_hash:
        raise BoreenmannaV3IntegrityError("V3 compiler identity differs from V2")
    executable = compilation.synthetic_result.require_executable()
    if executable.executable_semantic_hash != parent.executable_semantic_hash:
        raise BoreenmannaV3IntegrityError("V3 executable semantics differ from V2")
    scenarios = build_boreenmanna_demand_scenarios(compilation)
    started = perf_counter()
    baseline_config = discharge_readiness_config_for_executable(
        executable,
        tau_green_seconds=V3_BASELINE_TAU_GREEN_SECONDS,
        tau_red_seconds=V3_BASELINE_TAU_RED_SECONDS,
        initial_readiness=1.0,
        evidence_mode=FORENSIC_EVIDENCE,
    )
    core = tuple(
        run_audited_case(
            compilation,
            scenario,
            representation,
            DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE,
            drain_policy=policy,
            verify_replay=True,
            service_config_override=baseline_config,
        )
        for scenario in scenarios
        for representation in REPRESENTATION_MODES
    )
    core_by_key = {
        (
            str(run.deterministic["scenario_id"]),
            str(run.deterministic["representation_mode"]),
        ): run
        for run in core
    }
    sensitivity_rows = []
    parity = []
    for label, tau_green, tau_red in _parameter_cases():
        for scenario in scenarios:
            config = discharge_readiness_config_for_executable(
                executable,
                tau_green_seconds=tau_green,
                tau_red_seconds=tau_red,
                initial_readiness=1.0,
                evidence_mode=(
                    FORENSIC_EVIDENCE
                    if tau_green == 2.0 and tau_red == 10.0
                    else SUMMARY_EVIDENCE
                ),
            )
            parity.append(
                build_representation_parity_manifest(
                    compilation,
                    scenario,
                    DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE,
                    offset_ticks=0,
                    drain_policy=policy,
                    service_config_override=config,
                )
            )
            for representation in REPRESENTATION_MODES:
                if tau_green == 2.0 and tau_red == 10.0:
                    run = core_by_key[(scenario.scenario_id, representation)]
                else:
                    run = run_audited_case(
                        compilation,
                        scenario,
                        representation,
                        DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE,
                        drain_policy=policy,
                        verify_replay=False,
                        service_config_override=config,
                    )
                sensitivity_rows.append(
                    _sensitivity_row(label, tau_green, tau_red, run)
                )

    benchmark_rows = []
    benchmark_performance = []
    for scenario in scenarios:
        v2 = run_audited_case(
            compilation,
            scenario,
            "explicit_lane_group_fifo",
            GATE_AWARE_FRACTIONAL_SERVICE_MODE,
            drain_policy=policy,
            verify_replay=False,
        )
        benchmark_candidates = [("v2", FORENSIC_EVIDENCE, v2)]
        for evidence_mode in (FORENSIC_EVIDENCE, COMPACT_EVIDENCE, SUMMARY_EVIDENCE):
            config = discharge_readiness_config_for_executable(
                executable,
                tau_green_seconds=2.0,
                tau_red_seconds=10.0,
                evidence_mode=evidence_mode,
            )
            run = run_audited_case(
                compilation,
                scenario,
                "explicit_lane_group_fifo",
                DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE,
                drain_policy=policy,
                verify_replay=False,
                service_config_override=config,
            )
            benchmark_candidates.append(("v3", evidence_mode, run))
        v3_physical_hashes = {
            run.deterministic["physical_event_log_hash"]
            for policy_id, _, run in benchmark_candidates
            if policy_id == "v3"
        }
        v3_logical_hashes = {
            run.deterministic["readiness_logical_evidence_digest"]
            for policy_id, _, run in benchmark_candidates
            if policy_id == "v3"
        }
        if len(v3_physical_hashes) != 1 or len(v3_logical_hashes) != 1:
            raise BoreenmannaV3IntegrityError(
                "V3 evidence mode changed physical or logical evidence"
            )
        for policy_id, evidence_mode, run in benchmark_candidates:
            data = run.deterministic
            volume = data["evidence_volume"]
            benchmark_rows.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "policy": policy_id,
                    "evidence_mode": evidence_mode,
                    "physical_event_log_hash": data["physical_event_log_hash"],
                    "canonical_event_count": data["eventual_metrics"][
                        "canonical_event_count"
                    ],
                    "retained_service_records": volume[
                        "fractional_credit_evidence_count"
                    ],
                    "retained_readiness_records": volume["readiness_evidence_count"],
                    "logical_evidence_records": volume[
                        "logical_credit_evidence_count"
                    ],
                    "serialized_replay_bytes": volume["replay_artifact_bytes"],
                    "deterministic_run_hash": run.deterministic_hash,
                }
            )
            benchmark_performance.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "policy": policy_id,
                    "evidence_mode": evidence_mode,
                    **run.performance,
                }
            )
    sensitivity_payload = {
        "parameter_cases": [
            {"case_id": label, "tau_green_seconds": green, "tau_red_seconds": red}
            for label, green, red in _parameter_cases()
        ],
        "runs": sensitivity_rows,
    }
    package = BoreenmannaDischargeReadinessV3Package(
        compilation_package_hash=compilation.package.package_hash,
        executable_semantic_hash=executable.executable_semantic_hash,
        parent_v2_file_sha256=parent_sha,
        parent_v2_deterministic_hash=parent.deterministic_hash,
        v2_baseline_json=canonical_json(
            [item.deterministic for item in parent.v2_core_runs]
        ),
        v3_core_runs=core,
        parity_manifests=tuple(parity),
        analytical_results_json=canonical_json(analytical_v3_validation()),
        sensitivity_results_json=canonical_json(sensitivity_payload),
        benchmark_deterministic_json=canonical_json({"runs": benchmark_rows}),
        performance_json=canonical_json(
            {
                "measurement_class": "machine_dependent",
                "profile_before_patch": V2_PROFILE_BEFORE_PATCH,
                "profile_after_patch": V2_PROFILE_AFTER_PATCH,
                "v3_profile_after_patches": V3_PROFILE_AFTER_PATCHES,
                "benchmark_runs": benchmark_performance,
                "complete_experiment_wall_clock_seconds": perf_counter() - started,
            }
        ),
    )
    return compilation, scenarios, package


def write_boreenmanna_discharge_readiness_v3_outputs(
    package: BoreenmannaDischargeReadinessV3Package,
    output_directory: str | Path,
) -> tuple[Path, ...]:
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    package_path = directory / "boreenmanna_discharge_readiness_v3_v1.json"
    core_path = directory / "boreenmanna_v3_core_v1.csv"
    sensitivity_path = directory / "boreenmanna_v3_sensitivity_v1.csv"
    performance_path = directory / "boreenmanna_v3_evidence_performance_v1.csv"
    analytical_path = directory / "discharge_readiness_v3_analytical_v1.json"
    profile_path = directory / "v2_forensic_profile_before_patch_v1.json"
    profile_after_path = directory / "v2_forensic_profile_after_patch_v1.json"
    v3_profile_path = directory / "v3_forensic_profile_after_patches_v1.json"
    package_path.write_text(package.to_json(), encoding="utf-8")
    analytical_path.write_text(
        json.dumps(json.loads(package.analytical_results_json), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    profile_path.write_text(
        json.dumps(V2_PROFILE_BEFORE_PATCH, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    profile_after_path.write_text(
        json.dumps(V2_PROFILE_AFTER_PATCH, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    v3_profile_path.write_text(
        json.dumps(V3_PROFILE_AFTER_PATCHES, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    core_fields = (
        "scenario_id",
        "representation_mode",
        "completed_at_evaluation",
        "eventually_completed",
        "final_completion_tick",
        "mean_queue_delay_ticks",
        "peak_queue",
        "startup_lost_service",
        "mean_readiness_during_green",
        "mean_red_to_green_opening_readiness",
        "canonical_event_count",
        "deterministic_hash",
    )
    with core_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=core_fields)
        writer.writeheader()
        for run in package.v3_core_runs:
            data = run.deterministic
            readiness = _readiness_totals(data, evaluation=True)
            writer.writerow(
                {
                    "scenario_id": data["scenario_id"],
                    "representation_mode": data["representation_mode"],
                    "completed_at_evaluation": data["evaluation_metrics"][
                        "completed_throughput"
                    ],
                    "eventually_completed": data["drain_outcome"][
                        "eventually_completed"
                    ],
                    "final_completion_tick": data["drain_outcome"][
                        "final_completion_tick"
                    ],
                    "mean_queue_delay_ticks": data["evaluation_metrics"][
                        "mean_queue_delay_ticks"
                    ],
                    "peak_queue": data["evaluation_metrics"]["peak_queue"],
                    "startup_lost_service": readiness["startup_lost_service"],
                    "mean_readiness_during_green": readiness[
                        "mean_readiness_during_green"
                    ],
                    "mean_red_to_green_opening_readiness": readiness[
                        "mean_red_to_green_opening_readiness"
                    ],
                    "canonical_event_count": data["evaluation_metrics"][
                        "canonical_event_count"
                    ],
                    "deterministic_hash": run.deterministic_hash,
                }
            )
    sensitivity = json.loads(package.sensitivity_results_json)["runs"]
    sensitivity_fields = (
        "parameter_case_id",
        "tau_green_seconds",
        "tau_red_seconds",
        "scenario_id",
        "representation_mode",
        "completed_at_evaluation",
        "eventually_completed",
        "final_completion_tick",
        "mean_queue_delay_ticks",
        "peak_queue",
        "signal_blocks",
        "fifo_blocks",
        "spillback_duration_ticks",
        "canonical_event_count",
        "deterministic_run_hash",
    )
    with sensitivity_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=sensitivity_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sensitivity)
    benchmark = {
        (item["scenario_id"], item["policy"], item["evidence_mode"]): item
        for item in json.loads(package.benchmark_deterministic_json)["runs"]
    }
    performance_fields = (
        "scenario_id",
        "policy",
        "evidence_mode",
        "wall_clock_seconds",
        "cpu_seconds",
        "peak_memory_bytes",
        "retained_service_records",
        "retained_readiness_records",
        "logical_evidence_records",
        "serialized_replay_bytes",
        "canonical_event_count",
    )
    with performance_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=performance_fields)
        writer.writeheader()
        for perf in json.loads(package.performance_json)["benchmark_runs"]:
            deterministic = benchmark[
                (perf["scenario_id"], perf["policy"], perf["evidence_mode"])
            ]
            writer.writerow({key: perf.get(key, deterministic.get(key)) for key in performance_fields})
    return (
        package_path,
        core_path,
        sensitivity_path,
        performance_path,
        analytical_path,
        profile_path,
        profile_after_path,
        v3_profile_path,
    )
