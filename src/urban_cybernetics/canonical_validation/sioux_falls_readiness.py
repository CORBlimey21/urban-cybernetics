"""Sioux Falls parity-readiness gates for canonical validation Phase II."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass

from urban_cybernetics.config import (
    ACADEMIC_LTM_PARITY_PROFILE_ID,
    LEGACY_LOADING_PROFILE_ID,
)
from urban_cybernetics.core import Link, Node
from urban_cybernetics.demand import (
    FixedDepartureSchedule,
    ScheduledDemandLoader,
    load_sioux_falls_demand_manifest,
    resolve_demand_routes,
)
from urban_cybernetics.demand.resolution import ResolvedDemandManifest
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.topology import load_sioux_falls_topology
from urban_cybernetics.validation import (
    CommodityParityValidationReport,
    PhysicalParameterEligibilityReport,
    SpillbackValidationReport,
    assess_physical_parameter_eligibility,
    build_commodity_parity_validation_report,
    build_spillback_validation_report,
)


PASS_STATUS = "pass"
FAIL_STATUS = "fail"
NOT_RUN_STATUS = "not_run"
READINESS_STRESS_LABEL = "sioux_falls_readiness_stress_only"
PARITY_VALIDATION_LABEL = "sioux_falls_parity_validation"


@dataclass(frozen=True, slots=True)
class SiouxFallsReadinessGate:
    """One executable readiness gate and its current status."""

    gate_id: str
    status: str
    reason: str
    detail_count: int = 0
    details: tuple[str, ...] = ()

    @property
    def is_pass(self) -> bool:
        """Return whether this gate currently passes."""

        return self.status == PASS_STATUS


@dataclass(frozen=True, slots=True)
class SiouxFallsReadinessReport:
    """Machine-readable Sioux Falls parity-readiness status."""

    benchmark_id: str
    requested_model_profile_id: str
    evidence_label: str
    can_run_as_parity_ltm_v1: bool
    topology_hash: str
    demand_hash: str
    resolved_manifest_hash: str
    topology_node_count: int
    topology_link_count: int
    od_pair_count: int
    scheduled_departure_count: int
    instantiated_packet_count: int
    completed_packet_count: int
    event_count: int
    ticks_run: int
    gates: tuple[SiouxFallsReadinessGate, ...]
    kernel_bug_found: bool = False

    @property
    def failed_gate_ids(self) -> tuple[str, ...]:
        """Return failed gate IDs in report order."""

        return tuple(gate.gate_id for gate in self.gates if gate.status == FAIL_STATUS)

    @property
    def not_run_gate_ids(self) -> tuple[str, ...]:
        """Return gate IDs skipped because an earlier gate failed."""

        return tuple(gate.gate_id for gate in self.gates if gate.status == NOT_RUN_STATUS)

    def status_payload(self) -> dict[str, object]:
        """Return a JSON-ready provenance and status payload."""

        payload = asdict(self)
        payload["failed_gate_ids"] = self.failed_gate_ids
        payload["not_run_gate_ids"] = self.not_run_gate_ids
        return payload


def build_sioux_falls_parity_readiness_report(
    *,
    scale_factor: float = 0.01,
    max_pairs: int = 3,
    max_total_quantity_packets: int = 6,
    tick_limit: int = 30,
    storage_capacity_packets: int = 1000,
    tick_duration_seconds: float = 60.0,
) -> SiouxFallsReadinessReport:
    """Run executable Sioux Falls readiness gates without claiming validation."""

    topology = load_sioux_falls_topology()
    manifest = load_sioux_falls_demand_manifest(
        topology=topology,
        scale_factor=scale_factor,
        max_pairs=max_pairs,
        max_total_quantity_packets=max_total_quantity_packets,
        departure_schedule=FixedDepartureSchedule(departure_tick=0),
    )
    resolved = resolve_demand_routes(manifest, topology)
    scheduled_departure_count = len(ScheduledDemandLoader(resolved).scheduled_requests)
    links = topology.as_loading_links(
        tick_duration_seconds=tick_duration_seconds,
        declared_storage_capacity_packets=storage_capacity_packets,
    )
    nodes = topology.as_loading_nodes()

    physical_report = assess_physical_parameter_eligibility(
        links.values(),
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
    )
    gates: list[SiouxFallsReadinessGate] = [
        _pass_gate(
            "benchmark_loader",
            "Sioux Falls topology, demand, and route-resolution artifacts loaded.",
            details=(
                f"topology_hash={topology.topology_hash}",
                f"demand_hash={manifest.manifest_hash}",
                f"resolved_manifest_hash={resolved.resolved_manifest_hash}",
            ),
        ),
        _physical_gate(physical_report),
    ]

    parity_engine: LoadingEngine | None = None
    parity_error: str | None = None
    try:
        parity_engine = LoadingEngine(
            links=links,
            nodes=nodes,
            model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        )
    except ValueError as exc:
        parity_error = f"{type(exc).__name__}: {exc}"

    if parity_error is None:
        gates.append(
            _pass_gate(
                "parity_profile_full_topology_initialization",
                "Full Sioux Falls topology initialized under parity_ltm_v1.",
            )
        )
        assert parity_engine is not None
        _run_scheduled_slice(parity_engine, resolved, tick_limit=tick_limit)
        commodity_report = build_commodity_parity_validation_report(parity_engine)
        spillback_report = build_spillback_validation_report(parity_engine)
        gates.extend(
            (
                _commodity_gate(commodity_report),
                _spillback_gate(spillback_report),
            )
        )
    else:
        gates.extend(
            (
                _fail_gate(
                    "parity_profile_full_topology_initialization",
                    "Full Sioux Falls topology cannot currently initialize under "
                    "parity_ltm_v1.",
                    details=(parity_error,),
                ),
                _not_run_gate(
                    "parity_commodity_evidence",
                    "Skipped because parity_ltm_v1 full-topology initialization failed.",
                ),
                _not_run_gate(
                    "parity_spillback_evidence",
                    "Skipped because parity_ltm_v1 full-topology initialization failed.",
                ),
            )
        )

    legacy_engine, legacy_gate = _legacy_readiness_stress_gate(
        links=links,
        nodes=nodes,
        resolved_manifest=resolved,
        tick_limit=tick_limit,
    )
    gates.append(legacy_gate)

    can_run_as_parity = all(gate.is_pass for gate in gates[:-1])
    return SiouxFallsReadinessReport(
        benchmark_id="sioux_falls_tntp_v1",
        requested_model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        evidence_label=(
            PARITY_VALIDATION_LABEL
            if can_run_as_parity
            else READINESS_STRESS_LABEL
        ),
        can_run_as_parity_ltm_v1=can_run_as_parity,
        topology_hash=topology.topology_hash,
        demand_hash=manifest.manifest_hash,
        resolved_manifest_hash=resolved.resolved_manifest_hash,
        topology_node_count=len(topology.nodes),
        topology_link_count=len(topology.links),
        od_pair_count=len(manifest.declarations),
        scheduled_departure_count=scheduled_departure_count,
        instantiated_packet_count=len(legacy_engine.packets),
        completed_packet_count=len(legacy_engine.completed_packet_ids),
        event_count=len(legacy_engine.event_log),
        ticks_run=legacy_engine.current_tick,
        gates=tuple(gates),
        kernel_bug_found=False,
    )


def _legacy_readiness_stress_gate(
    *,
    links: dict[str, Link],
    nodes: tuple[Node, ...],
    resolved_manifest: ResolvedDemandManifest,
    tick_limit: int,
) -> tuple[LoadingEngine, SiouxFallsReadinessGate]:
    engine = LoadingEngine(
        links=links,
        nodes=nodes,
        model_profile_id=LEGACY_LOADING_PROFILE_ID,
    )
    _run_scheduled_slice(engine, resolved_manifest, tick_limit=tick_limit)
    count_report = engine.count_consistency_report()
    if count_report.is_consistent and len(engine.packets) > 0:
        return engine, _pass_gate(
            "legacy_profile_readiness_stress_run",
            "Small Sioux Falls slice runs as readiness/stress evidence only.",
            details=(
                f"model_profile_id={LEGACY_LOADING_PROFILE_ID}",
                f"ticks_run={engine.current_tick}",
                f"instantiated_packets={len(engine.packets)}",
                f"completed_packets={len(engine.completed_packet_ids)}",
                f"events={len(engine.event_log)}",
            ),
        )
    return engine, _fail_gate(
        "legacy_profile_readiness_stress_run",
        "Small Sioux Falls readiness/stress slice did not preserve count consistency.",
        details=count_report.ineligibility_reasons,
    )


def _run_scheduled_slice(
    engine: LoadingEngine,
    resolved_manifest: ResolvedDemandManifest,
    *,
    tick_limit: int,
) -> None:
    loader = ScheduledDemandLoader(resolved_manifest)
    loader.submit_due_departures(engine)
    for _ in range(tick_limit):
        engine.step()
        loader.submit_due_departures(engine)


def _physical_gate(
    report: PhysicalParameterEligibilityReport,
) -> SiouxFallsReadinessGate:
    if report.is_parity_eligible:
        return _pass_gate(
            "physical_metadata",
            "All Sioux Falls loading links have parity-eligible physical metadata.",
        )
    return _fail_gate(
        "physical_metadata",
        "Sioux Falls TNTP topology is missing physical metadata required for "
        "true parity evidence.",
        detail_count=len(report.ineligibility_reasons),
        details=report.ineligibility_reasons[:12],
    )


def _commodity_gate(
    report: CommodityParityValidationReport,
) -> SiouxFallsReadinessGate:
    if report.is_valid:
        return _pass_gate(
            "parity_commodity_evidence",
            "Packet, route-count, and travel-time evidence is valid for the run.",
        )
    return _fail_gate(
        "parity_commodity_evidence",
        "Packet, route-count, or travel-time evidence is not parity-valid.",
        detail_count=len(report.invariant_violations),
        details=report.invariant_violations[:12],
    )


def _spillback_gate(
    report: SpillbackValidationReport,
) -> SiouxFallsReadinessGate:
    if report.is_valid:
        return _pass_gate(
            "parity_spillback_evidence",
            "Spillback evidence is internally valid for the run.",
        )
    return _fail_gate(
        "parity_spillback_evidence",
        "Spillback evidence is not parity-valid for the run.",
        detail_count=len(report.invariant_violations),
        details=report.invariant_violations[:12],
    )


def _pass_gate(
    gate_id: str,
    reason: str,
    *,
    details: tuple[str, ...] = (),
) -> SiouxFallsReadinessGate:
    return SiouxFallsReadinessGate(
        gate_id=gate_id,
        status=PASS_STATUS,
        reason=reason,
        detail_count=len(details),
        details=details,
    )


def _fail_gate(
    gate_id: str,
    reason: str,
    *,
    detail_count: int | None = None,
    details: tuple[str, ...] = (),
) -> SiouxFallsReadinessGate:
    return SiouxFallsReadinessGate(
        gate_id=gate_id,
        status=FAIL_STATUS,
        reason=reason,
        detail_count=len(details) if detail_count is None else detail_count,
        details=details,
    )


def _not_run_gate(gate_id: str, reason: str) -> SiouxFallsReadinessGate:
    return SiouxFallsReadinessGate(
        gate_id=gate_id,
        status=NOT_RUN_STATUS,
        reason=reason,
    )


def main() -> None:
    """Print the current Sioux Falls readiness report as JSON."""

    parser = argparse.ArgumentParser(
        description="Run Sioux Falls canonical parity-readiness gates."
    )
    parser.add_argument("--tick-limit", type=int, default=30)
    parser.add_argument("--scale-factor", type=float, default=0.01)
    parser.add_argument("--max-pairs", type=int, default=3)
    parser.add_argument("--max-total-quantity-packets", type=int, default=6)
    args = parser.parse_args()
    report = build_sioux_falls_parity_readiness_report(
        scale_factor=args.scale_factor,
        max_pairs=args.max_pairs,
        max_total_quantity_packets=args.max_total_quantity_packets,
        tick_limit=args.tick_limit,
    )
    print(json.dumps(report.status_payload(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
