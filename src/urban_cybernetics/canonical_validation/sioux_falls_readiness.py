"""Sioux Falls parity-readiness gates for canonical validation Phase II."""

from __future__ import annotations

import argparse
import hashlib
import json
import signal
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from math import floor
from pathlib import Path
from time import perf_counter

from urban_cybernetics.config import (
    ACADEMIC_LTM_PARITY_PROFILE_ID,
    LEGACY_LOADING_PROFILE_ID,
)
from urban_cybernetics.core import DemandDeclaration, EventType, Link, Node
from urban_cybernetics.core.node import movement_id
from urban_cybernetics.demand import (
    FixedDepartureSchedule,
    ScheduledDemandLoader,
    load_sioux_falls_demand_manifest,
    resolve_demand_routes,
)
from urban_cybernetics.demand.resolution import ResolvedDemandManifest
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.topology import CanonicalTopologyLink, load_sioux_falls_topology
from urban_cybernetics.validation import (
    CommodityParityValidationReport,
    PhysicalParameterEligibilityReport,
    SpillbackValidationReport,
    ValidationContext,
    assess_physical_parameter_eligibility,
    build_commodity_parity_validation_report,
    build_spillback_validation_report,
)
from urban_cybernetics.canonical_validation.sioux_falls_physical_profile import (
    SIOUX_FALLS_UC_DEFAULT_PROFILE_ID,
    SiouxFallsPhysicalProfile,
    build_sioux_falls_uc_default_physical_profile,
)


PASS_STATUS = "pass"
FAIL_STATUS = "fail"
NOT_RUN_STATUS = "not_run"
READINESS_STRESS_LABEL = "sioux_falls_readiness_stress_only"
PARITY_VALIDATION_LABEL = "sioux_falls_parity_validation"
SUBNETWORK_READINESS_LABEL = "sioux_falls_supported_movement_subnetwork_parity_ready"
SUBNETWORK_BACKWARD_WAVE_SPEED_MPS = 5.0
SUBNETWORK_LINK_IDS = (
    "L0001",
    "L0002",
    "L0003",
    "L0004",
    "L0006",
    "L0009",
    "L0012",
    "L0016",
)
SUBNETWORK_ROUTES = (
    ("route:N001->N008:via-N002", ("L0001", "L0004", "L0016")),
    ("route:N001->N001:return-via-N002", ("L0001", "L0003")),
    ("route:N001->N008:via-N003-N006", ("L0002", "L0006", "L0009", "L0012", "L0016")),
)
ASSUMPTION_PROFILE_EVIDENCE_LABEL = "sioux_falls_uc_default_assumption_profile_run"
REPLAY_PASSED_EXACT = "passed_exact_replay"
REPLAY_SKIPPED_AFTER_CERTIFICATION = "skipped_by_policy_after_determinism_certification"
REPLAY_TIMEOUT = "timeout"
REPLAY_FAILED_MISMATCH = "failed_mismatch"
REPLAY_NOT_RUN = "not_run"
SCALE_PASSED = "passed"
SCALE_FAILED_INTERNAL_VALIDATION = "failed_internal_validation"
SCALE_FAILED_REPLAY_MISMATCH = "failed_deterministic_mismatch"
SCALE_FAILED_REPLAY_TIMEOUT = "failed_replay_timeout"
SCALE_FAILED_RUNTIME = "failed_runtime"
SCALE_FAILED_MEMORY = "failed_memory"


class ScaleLadderRuntimeLimitExceeded(RuntimeError):
    """Raised when a scale-ladder rung exceeds its configured runtime budget."""


@dataclass(frozen=True, slots=True)
class SiouxFallsReplayPolicy:
    """Policy deciding whether an exact replay must be run for a scale rung."""

    exact_replay_packet_limit: int = 1_000
    determinism_certified_packet_count: int | None = None

    def should_run_exact_replay(self, requested_packet_count: int) -> bool:
        """Return whether the rung needs an exact rerun under this policy."""

        if requested_packet_count <= self.exact_replay_packet_limit:
            return True
        return self.determinism_certified_packet_count is None

    def skip_reason(self, requested_packet_count: int) -> str | None:
        """Return a replay skip reason when policy allows skipping."""

        if self.should_run_exact_replay(requested_packet_count):
            return None
        if (
            self.determinism_certified_packet_count is not None
            and requested_packet_count > self.exact_replay_packet_limit
        ):
            return REPLAY_SKIPPED_AFTER_CERTIFICATION
        return REPLAY_NOT_RUN


@dataclass(frozen=True, slots=True)
class SiouxFallsDeterminismComparisonReport:
    """Repeated-run determinism evidence for one Sioux Falls packet count."""

    requested_packet_count: int
    matches: bool
    replay_status: str
    first_divergence: str | None
    classification: str | None
    event_count_first: int
    event_count_second: int
    event_log_fingerprint_first: str
    event_log_fingerprint_second: str
    packet_lifecycle_matches: bool
    conservation_matches: bool
    validation_summary_matches: bool
    completed_packet_set_matches: bool

    def status_payload(self) -> dict[str, object]:
        """Return a JSON-ready determinism payload."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class SiouxFallsValidationStatus:
    """One validation category from a full-network assumption-profile run."""

    category: str
    status: str
    reason: str
    detail_count: int = 0
    details: tuple[str, ...] = ()

    @property
    def is_pass(self) -> bool:
        """Return whether this validation category passed."""

        return self.status == PASS_STATUS


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


@dataclass(frozen=True, slots=True)
class SiouxFallsSubnetworkMetadataAssumption:
    """One provenance-labelled physical metadata assumption for the subnetwork."""

    field_name: str
    value: str
    provenance_label: str
    note: str


@dataclass(frozen=True, slots=True)
class SiouxFallsSubnetworkReadinessReport:
    """Machine-readable readiness status for the supported Sioux Falls subnetwork."""

    subnetwork_id: str
    parent_benchmark_id: str
    requested_model_profile_id: str
    evidence_label: str
    is_ready_for_parity_validation: bool
    topology_hash: str
    selected_source_nodes: tuple[str, ...]
    selected_link_ids: tuple[str, ...]
    selected_source_links: tuple[str, ...]
    unsupported_advanced_full_network_node_ids: tuple[str, ...]
    adapted_supported_node_ids: tuple[str, ...]
    movement_specs: tuple[tuple[str, tuple[tuple[str, str, int], ...]], ...]
    route_intents: tuple[tuple[str, tuple[str, ...]], ...]
    metadata_assumptions: tuple[SiouxFallsSubnetworkMetadataAssumption, ...]
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

    def status_payload(self) -> dict[str, object]:
        """Return a JSON-ready provenance and status payload."""

        payload = asdict(self)
        payload["failed_gate_ids"] = self.failed_gate_ids
        return payload


@dataclass(frozen=True, slots=True)
class SiouxFallsAssumptionProfileRunReport:
    """Full-topology parity-kernel run under a versioned physical profile."""

    benchmark_id: str
    requested_model_profile_id: str
    evidence_label: str
    physical_profile_id: str
    physical_profile_version: str
    physical_profile_hash: str
    topology_hash: str
    demand_hash: str
    resolved_manifest_hash: str
    topology_node_count: int
    topology_link_count: int
    od_pair_count: int
    requested_packet_count: int
    scheduled_departure_count: int
    submitted_departure_count: int
    instantiated_packet_count: int
    completed_packet_count: int
    unresolved_packet_count: int
    event_count: int
    ticks_run: int
    runtime_seconds: float
    primary_engine_runtime_seconds: float
    validation_projection_runtime_seconds: float
    validator_runtime_seconds: float
    replay_runtime_seconds: float | None
    total_runtime_seconds: float
    run_completed: bool
    packet_conservation_passed: bool
    count_consistency_passed: bool
    fifo_validation_passed: bool
    spillback_validation_passed: bool
    commodity_validation_passed: bool
    node_validation_passed: bool
    deterministic_replay_passed: bool
    replay_status: str
    parity_readiness_status: str
    kernel_execution_status: str
    internal_validation_status: str
    validation_status: str
    validation_results: tuple[SiouxFallsValidationStatus, ...]
    warnings: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()
    kernel_bug_found: bool = False
    setup_runtime_seconds: float = 0.0

    @property
    def failed_validation_categories(self) -> tuple[str, ...]:
        """Return failed validation categories."""

        return tuple(
            result.category
            for result in self.validation_results
            if result.status == FAIL_STATUS
        )

    def status_payload(self) -> dict[str, object]:
        """Return a JSON-ready provenance and status payload."""

        payload = asdict(self)
        payload["failed_validation_categories"] = self.failed_validation_categories
        return payload


@dataclass(frozen=True, slots=True)
class SiouxFallsAssumptionProfileScaleRungReport:
    """One deterministic assumption-profile scale-ladder rung."""

    rung_label: str
    requested_packet_count: int
    submitted_packet_count: int
    instantiated_packet_count: int
    completed_packet_count: int
    unresolved_packet_count: int
    ticks_run: int
    runtime_seconds: float
    primary_engine_runtime_seconds: float
    validation_projection_runtime_seconds: float
    validator_runtime_seconds: float
    replay_runtime_seconds: float | None
    total_runtime_seconds: float
    event_count: int
    run_completed: bool
    packet_conservation_passed: bool
    count_consistency_passed: bool
    fifo_validation_passed: bool
    spillback_validation_passed: bool
    commodity_validation_passed: bool
    node_validation_passed: bool
    deterministic_replay_passed: bool
    replay_status: str
    internal_validation_status: str
    scale_status: str
    validation_status: str
    failure_reason: str | None = None
    warnings: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()
    setup_runtime_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class SiouxFallsAssumptionProfileScaleLadderReport:
    """Structured Sioux Falls assumption-profile scale-ladder results."""

    benchmark_id: str
    requested_model_profile_id: str
    evidence_label: str
    physical_profile_id: str
    physical_profile_version: str
    physical_profile_hash: str
    topology_hash: str
    bounded_packet_rungs: tuple[int, ...]
    full_demand_requested_packet_count: int
    full_demand_run_attempted: bool
    rung_reports: tuple[SiouxFallsAssumptionProfileScaleRungReport, ...]
    stopped_early: bool
    stop_reason: str | None = None

    def status_payload(self) -> dict[str, object]:
        """Return a JSON-ready ladder payload."""

        return asdict(self)


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
        _junction_metadata_gate(nodes),
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
                "allocator_capability",
                "Full Sioux Falls topology initialized with the Stage 2 movement allocator.",
            )
        )
        if physical_report.is_parity_eligible and gates[-2].is_pass:
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
                    _not_run_gate(
                        "parity_commodity_evidence",
                        "Skipped because full-topology physical or junction metadata is not parity-eligible.",
                    ),
                    _not_run_gate(
                        "parity_spillback_evidence",
                        "Skipped because full-topology physical or junction metadata is not parity-eligible.",
                    ),
                )
            )
    else:
        gates.extend(
            (
                _fail_gate(
                    "allocator_capability",
                    "Full Sioux Falls topology cannot currently initialize under "
                    "the Stage 2 movement-allocation parity path.",
                    details=(parity_error,),
                ),
                _not_run_gate(
                    "parity_commodity_evidence",
                    "Skipped because Stage 2 allocator capability failed.",
                ),
                _not_run_gate(
                    "parity_spillback_evidence",
                    "Skipped because Stage 2 allocator capability failed.",
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


def build_sioux_falls_supported_subnetwork_readiness_report(
    *,
    tick_limit: int = 30,
    tick_duration_seconds: float = 60.0,
) -> SiouxFallsSubnetworkReadinessReport:
    """Run a supported Sioux Falls subnetwork under parity_ltm_v1."""

    topology = load_sioux_falls_topology()
    canonical_links = {link.link_id: link for link in topology.links}
    selected_canonical_links = tuple(
        canonical_links[link_id] for link_id in SUBNETWORK_LINK_IDS
    )
    links = _subnetwork_loading_links(
        selected_canonical_links,
        tick_duration_seconds=tick_duration_seconds,
    )
    nodes = _subnetwork_nodes()
    engine = _run_subnetwork_engine(
        links=links,
        nodes=nodes,
        tick_limit=tick_limit,
    )
    replay_engine = _run_subnetwork_engine(
        links=links,
        nodes=nodes,
        tick_limit=tick_limit,
    )

    physical_report = assess_physical_parameter_eligibility(
        links.values(),
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
    )
    commodity_report = build_commodity_parity_validation_report(engine)
    spillback_report = build_spillback_validation_report(engine)
    count_report = engine.count_consistency_report()
    gates = (
        _subnetwork_structure_gate(nodes),
        _physical_gate(physical_report),
        _pass_gate(
            "parity_profile_initialization",
            "Supported Sioux Falls subnetwork initialized under parity_ltm_v1.",
        ),
        _commodity_gate(commodity_report),
        _spillback_gate(spillback_report),
        _count_gate(count_report),
        _conservation_gate(engine),
        _deterministic_replay_gate(engine, replay_engine),
    )
    is_ready = all(gate.is_pass for gate in gates)

    return SiouxFallsSubnetworkReadinessReport(
        subnetwork_id="sioux_falls_supported_movement_subnetwork_v1",
        parent_benchmark_id="sioux_falls_tntp_v1",
        requested_model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        evidence_label=(
            SUBNETWORK_READINESS_LABEL
            if is_ready
            else "sioux_falls_supported_subnetwork_readiness_blocked"
        ),
        is_ready_for_parity_validation=is_ready,
        topology_hash=topology.topology_hash,
        selected_source_nodes=("1", "2", "3", "4", "5", "6", "8"),
        selected_link_ids=SUBNETWORK_LINK_IDS,
        selected_source_links=tuple(
            link.source_link_id for link in selected_canonical_links
        ),
        unsupported_advanced_full_network_node_ids=(
            _unsupported_advanced_full_network_node_ids(topology)
        ),
        adapted_supported_node_ids=tuple(node.node_id for node in nodes),
        movement_specs=tuple(
            (
                node.node_id,
                tuple(
                    (
                        movement.upstream_link_id,
                        movement.downstream_link_id,
                        movement.priority_weight,
                    )
                    for movement in node.junction_spec.movement_specs
                ),
            )
            for node in nodes
        ),
        route_intents=SUBNETWORK_ROUTES,
        metadata_assumptions=_subnetwork_metadata_assumptions(),
        instantiated_packet_count=len(engine.packets),
        completed_packet_count=len(engine.completed_packet_ids),
        event_count=len(engine.event_log),
        ticks_run=engine.current_tick,
        gates=gates,
        kernel_bug_found=False,
    )


def build_sioux_falls_assumption_profile_run_report(
    *,
    physical_profile: SiouxFallsPhysicalProfile | None = None,
    scale_factor: float = 0.01,
    max_pairs: int | None = 12,
    max_total_quantity_packets: int = 24,
    tick_limit: int = 600,
    tick_duration_seconds: float = 60.0,
    replay_policy: SiouxFallsReplayPolicy | None = None,
) -> SiouxFallsAssumptionProfileRunReport:
    """Run full Sioux Falls topology under the UC default physical profile."""

    total_started_at = perf_counter()
    setup_started_at = total_started_at
    topology = load_sioux_falls_topology()
    profile = physical_profile or build_sioux_falls_uc_default_physical_profile(
        topology=topology
    )
    manifest = load_sioux_falls_demand_manifest(
        topology=topology,
        scale_factor=scale_factor,
        max_pairs=max_pairs,
        max_total_quantity_packets=max_total_quantity_packets,
        departure_schedule=FixedDepartureSchedule(departure_tick=0),
    )
    resolved = resolve_demand_routes(manifest, topology)
    scheduled_departure_count = len(ScheduledDemandLoader(resolved).scheduled_requests)
    links = profile.as_loading_links(tick_duration_seconds=tick_duration_seconds)
    nodes = topology.as_loading_nodes()
    capacity_rates = profile.parity_capacity_rates_by_link(
        tick_duration_seconds=tick_duration_seconds
    )

    physical_report = assess_physical_parameter_eligibility(
        links.values(),
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
    )
    junction_gate = _junction_metadata_gate(nodes)

    setup_runtime_seconds = perf_counter() - setup_started_at
    primary_started_at = perf_counter()
    engine = _run_full_profile_engine(
        links=links,
        nodes=nodes,
        resolved_manifest=resolved,
        capacity_rates=capacity_rates,
        tick_limit=tick_limit,
    )
    primary_engine_runtime_seconds = perf_counter() - primary_started_at

    projection_started_at = perf_counter()
    validation_context = ValidationContext.from_engine(
        engine,
        nodes=nodes,
        run_config={
            "benchmark_id": "sioux_falls_tntp_v1",
            "physical_profile_id": profile.profile_id,
            "tick_limit": tick_limit,
        },
    )
    count_report = validation_context.count_consistency_report
    validation_projection_runtime_seconds = perf_counter() - projection_started_at

    validator_started_at = perf_counter()
    commodity_report = build_commodity_parity_validation_report(
        engine,
        validation_context=validation_context,
    )
    spillback_report = build_spillback_validation_report(engine)
    submitted_departure_count = scheduled_departure_count - _unsubmitted_count(
        resolved,
        engine,
    )
    run_completed = _run_completed(
        engine,
        scheduled_departure_count=scheduled_departure_count,
        submitted_departure_count=submitted_departure_count,
    )
    unresolved_packet_count = max(scheduled_departure_count - len(engine.completed_packet_ids), 0)
    fifo_reasons = _fifo_validation_failures(engine, validation_context=validation_context)
    node_reasons = _node_validation_failures(
        engine,
        nodes,
        validation_context=validation_context,
    )
    validator_runtime_seconds = perf_counter() - validator_started_at

    requested_packet_count = scheduled_departure_count
    policy = replay_policy or SiouxFallsReplayPolicy()
    replay_runtime_seconds: float | None = None
    replay_passed = False
    replay_status = REPLAY_NOT_RUN
    if policy.should_run_exact_replay(requested_packet_count):
        replay_started_at = perf_counter()
        replay_engine = _run_full_profile_engine(
            links=links,
            nodes=nodes,
            resolved_manifest=resolved,
            capacity_rates=capacity_rates,
            tick_limit=tick_limit,
        )
        replay_runtime_seconds = perf_counter() - replay_started_at
        replay_passed = engine.event_log == replay_engine.event_log
        replay_status = REPLAY_PASSED_EXACT if replay_passed else REPLAY_FAILED_MISMATCH
    else:
        replay_status = policy.skip_reason(requested_packet_count) or REPLAY_NOT_RUN

    conservation_passed = engine.check_conservation() and _packet_conservation_gate(
        engine,
        scheduled_departure_count=scheduled_departure_count,
        submitted_departure_count=submitted_departure_count,
    ).is_pass

    replay_validation_status = (
        PASS_STATUS
        if replay_status == REPLAY_PASSED_EXACT
        else NOT_RUN_STATUS
        if replay_status == REPLAY_SKIPPED_AFTER_CERTIFICATION
        else FAIL_STATUS
    )
    validation_results = (
        _status_from_bool(
            "physical_metadata",
            physical_report.is_parity_eligible,
            "Assumption profile physical metadata is parity-eligible.",
            "Assumption profile physical metadata is not parity-eligible.",
            physical_report.ineligibility_reasons,
        ),
        _status_from_bool(
            "kernel_execution",
            run_completed,
            "Full-topology bounded parity run completed.",
            "Full-topology bounded parity run did not complete.",
            (
                f"submitted_departures={submitted_departure_count}",
                f"scheduled_departures={scheduled_departure_count}",
                f"instantiated_packets={len(engine.packets)}",
                f"completed_packets={len(engine.completed_packet_ids)}",
                f"pending_demands={len(engine.pending_demands)}",
                f"ticks_run={engine.current_tick}",
            ),
        ),
        _status_from_bool(
            "packet_conservation",
            conservation_passed,
            "Packet conservation passed for the run.",
            "Packet conservation failed for the run.",
            _packet_conservation_details(
                engine,
                scheduled_departure_count=scheduled_departure_count,
                submitted_departure_count=submitted_departure_count,
            ),
        ),
        _status_from_bool(
            "count_consistency",
            count_report.is_consistent,
            "Aggregate, route, ordinal, and travel-time count evidence is consistent.",
            "Count consistency failed.",
            count_report.ineligibility_reasons,
        ),
        _status_from_bool(
            "fifo_validation",
            not fifo_reasons,
            "Per-link exit order preserves entry FIFO order.",
            "Per-link FIFO validation failed.",
            fifo_reasons,
        ),
        _status_from_bool(
            "spillback_validation",
            spillback_report.is_valid,
            "Spillback evidence is internally valid for the run.",
            "Spillback evidence failed validation.",
            spillback_report.invariant_violations,
        ),
        _status_from_bool(
            "commodity_validation",
            commodity_report.is_valid,
            "M7 commodity evidence is valid for the run.",
            "M7 commodity evidence failed validation.",
            commodity_report.invariant_violations,
        ),
        _status_from_bool(
            "node_validation",
            not node_reasons,
            "Observed transfers are covered by Stage 2 node movement specs.",
            "Observed transfers failed Stage 2 node validation.",
            node_reasons,
        ),
        SiouxFallsValidationStatus(
            category="deterministic_replay",
            status=replay_validation_status,
            reason=(
                "Repeated full-topology parity runs produced identical events."
                if replay_status == REPLAY_PASSED_EXACT
                else "Exact replay skipped by explicit policy after determinism certification."
                if replay_status == REPLAY_SKIPPED_AFTER_CERTIFICATION
                else "Full-topology parity replay did not produce exact match evidence."
            ),
            detail_count=2,
            details=(
                f"replay_status={replay_status}",
                f"first_event_count={len(engine.event_log)}",
            ),
        ),
    )
    failures = tuple(
        detail
        for result in validation_results
        if result.status == FAIL_STATUS
        for detail in (f"{result.category}:{result.reason}", *result.details)
    )
    warnings = _assumption_profile_warnings(junction_gate)
    internal_results = tuple(
        result
        for result in validation_results
        if result.category != "deterministic_replay"
    )
    internal_validation_passed = all(result.is_pass for result in internal_results)
    validation_passed = internal_validation_passed and replay_status in (
        REPLAY_PASSED_EXACT,
        REPLAY_SKIPPED_AFTER_CERTIFICATION,
    )
    total_runtime_seconds = perf_counter() - total_started_at

    return SiouxFallsAssumptionProfileRunReport(
        benchmark_id="sioux_falls_tntp_v1",
        requested_model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        evidence_label=ASSUMPTION_PROFILE_EVIDENCE_LABEL,
        physical_profile_id=profile.profile_id,
        physical_profile_version=profile.version,
        physical_profile_hash=profile.profile_hash,
        topology_hash=topology.topology_hash,
        demand_hash=manifest.manifest_hash,
        resolved_manifest_hash=resolved.resolved_manifest_hash,
        topology_node_count=len(topology.nodes),
        topology_link_count=len(topology.links),
        od_pair_count=len(manifest.declarations),
        requested_packet_count=requested_packet_count,
        scheduled_departure_count=scheduled_departure_count,
        submitted_departure_count=submitted_departure_count,
        instantiated_packet_count=len(engine.packets),
        completed_packet_count=len(engine.completed_packet_ids),
        unresolved_packet_count=unresolved_packet_count,
        event_count=len(engine.event_log),
        ticks_run=engine.current_tick,
        runtime_seconds=primary_engine_runtime_seconds,
        primary_engine_runtime_seconds=primary_engine_runtime_seconds,
        validation_projection_runtime_seconds=validation_projection_runtime_seconds,
        validator_runtime_seconds=validator_runtime_seconds,
        replay_runtime_seconds=replay_runtime_seconds,
        total_runtime_seconds=total_runtime_seconds,
        setup_runtime_seconds=setup_runtime_seconds,
        run_completed=run_completed,
        packet_conservation_passed=conservation_passed,
        count_consistency_passed=count_report.is_consistent,
        fifo_validation_passed=not fifo_reasons,
        spillback_validation_passed=spillback_report.is_valid,
        commodity_validation_passed=commodity_report.is_valid,
        node_validation_passed=not node_reasons,
        deterministic_replay_passed=replay_passed,
        replay_status=replay_status,
        parity_readiness_status=(
            "engineering_assumption_profile_ready"
            if physical_report.is_parity_eligible
            else "engineering_assumption_profile_blocked"
        ),
        kernel_execution_status="completed" if run_completed else "incomplete",
        internal_validation_status=(
            "passed" if internal_validation_passed else "failed"
        ),
        validation_status="passed" if validation_passed else "failed",
        validation_results=validation_results,
        warnings=warnings,
        failures=failures,
        kernel_bug_found=bool(failures),
    )


def build_sioux_falls_assumption_profile_scale_ladder_report(
    *,
    physical_profile: SiouxFallsPhysicalProfile | None = None,
    bounded_packet_rungs: tuple[int, ...] = (
        24,
        100,
        1_000,
        5_000,
        10_000,
        25_000,
        50_000,
        100_000,
    ),
    tick_limit: int = 20_000,
    tick_duration_seconds: float = 60.0,
    include_full_demand_run: bool = True,
    max_runtime_seconds_per_rung: float | None = None,
    replay_policy: SiouxFallsReplayPolicy | None = None,
) -> SiouxFallsAssumptionProfileScaleLadderReport:
    """Run a deterministic Sioux Falls assumption-profile scale ladder."""

    topology = load_sioux_falls_topology()
    profile = physical_profile or build_sioux_falls_uc_default_physical_profile(
        topology=topology
    )
    full_manifest = load_sioux_falls_demand_manifest(
        topology=topology,
        scale_factor=1.0,
        max_pairs=None,
        max_total_quantity_packets=None,
        departure_schedule=FixedDepartureSchedule(departure_tick=0),
    )
    full_demand_requested_packet_count = full_manifest.total_declared_quantity_packets

    rung_reports: list[SiouxFallsAssumptionProfileScaleRungReport] = []
    stopped_early = False
    stop_reason: str | None = None
    active_replay_policy = replay_policy or SiouxFallsReplayPolicy()

    for packet_cap in bounded_packet_rungs:
        rung_report = _build_scale_ladder_rung_report(
            rung_label=str(packet_cap),
            physical_profile=profile,
            scale_factor=1.0,
            max_pairs=None,
            max_total_quantity_packets=packet_cap,
            tick_limit=tick_limit,
            tick_duration_seconds=tick_duration_seconds,
            max_runtime_seconds=max_runtime_seconds_per_rung,
            replay_policy=active_replay_policy,
            expected_requested_packet_count=packet_cap,
        )
        rung_reports.append(rung_report)
        if rung_report.failure_reason is not None:
            stopped_early = True
            stop_reason = f"{rung_report.rung_label}:{rung_report.failure_reason}"
            break

    full_demand_run_attempted = include_full_demand_run and not stopped_early
    if full_demand_run_attempted:
        full_rung_report = _build_scale_ladder_rung_report(
            rung_label="full_demand",
            physical_profile=profile,
            scale_factor=1.0,
            max_pairs=None,
            max_total_quantity_packets=None,
            tick_limit=tick_limit,
            tick_duration_seconds=tick_duration_seconds,
            max_runtime_seconds=max_runtime_seconds_per_rung,
            replay_policy=active_replay_policy,
            expected_requested_packet_count=full_demand_requested_packet_count,
        )
        rung_reports.append(full_rung_report)
        if full_rung_report.failure_reason is not None:
            stopped_early = True
            stop_reason = f"{full_rung_report.rung_label}:{full_rung_report.failure_reason}"

    return SiouxFallsAssumptionProfileScaleLadderReport(
        benchmark_id="sioux_falls_tntp_v1",
        requested_model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        evidence_label="sioux_falls_uc_default_assumption_profile_scale_ladder",
        physical_profile_id=profile.profile_id,
        physical_profile_version=profile.version,
        physical_profile_hash=profile.profile_hash,
        topology_hash=topology.topology_hash,
        bounded_packet_rungs=bounded_packet_rungs,
        full_demand_requested_packet_count=full_demand_requested_packet_count,
        full_demand_run_attempted=full_demand_run_attempted,
        rung_reports=tuple(rung_reports),
        stopped_early=stopped_early,
        stop_reason=stop_reason,
    )


def build_sioux_falls_assumption_profile_determinism_report(
    *,
    physical_profile: SiouxFallsPhysicalProfile | None = None,
    max_total_quantity_packets: int = 24,
    tick_limit: int = 20_000,
    tick_duration_seconds: float = 60.0,
) -> SiouxFallsDeterminismComparisonReport:
    """Run two identical Sioux Falls assumption-profile executions and compare them."""

    topology = load_sioux_falls_topology()
    profile = physical_profile or build_sioux_falls_uc_default_physical_profile(
        topology=topology
    )
    manifest = load_sioux_falls_demand_manifest(
        topology=topology,
        scale_factor=1.0,
        max_pairs=None,
        max_total_quantity_packets=max_total_quantity_packets,
        departure_schedule=FixedDepartureSchedule(departure_tick=0),
    )
    resolved = resolve_demand_routes(manifest, topology)
    links = profile.as_loading_links(tick_duration_seconds=tick_duration_seconds)
    nodes = topology.as_loading_nodes()
    capacity_rates = profile.parity_capacity_rates_by_link(
        tick_duration_seconds=tick_duration_seconds
    )
    first = _run_full_profile_engine(
        links=links,
        nodes=nodes,
        resolved_manifest=resolved,
        capacity_rates=capacity_rates,
        tick_limit=tick_limit,
    )
    second = _run_full_profile_engine(
        links=links,
        nodes=nodes,
        resolved_manifest=resolved,
        capacity_rates=capacity_rates,
        tick_limit=tick_limit,
    )
    first_context = ValidationContext.from_engine(first, nodes=nodes)
    second_context = ValidationContext.from_engine(second, nodes=nodes)
    packet_lifecycle_matches = (
        _packet_lifecycle_summary(first) == _packet_lifecycle_summary(second)
    )
    conservation_matches = (
        _conservation_summary(first, resolved)
        == _conservation_summary(second, resolved)
    )
    validation_summary_matches = (
        _validation_summary(first, nodes, first_context)
        == _validation_summary(second, nodes, second_context)
    )
    completed_packet_set_matches = (
        tuple(sorted(first.completed_packet_ids))
        == tuple(sorted(second.completed_packet_ids))
    )
    events_match = first.event_log == second.event_log
    matches = (
        events_match
        and len(first.event_log) == len(second.event_log)
        and packet_lifecycle_matches
        and conservation_matches
        and validation_summary_matches
        and completed_packet_set_matches
    )
    first_divergence = None if matches else _first_determinism_divergence(first, second)
    return SiouxFallsDeterminismComparisonReport(
        requested_packet_count=max_total_quantity_packets,
        matches=matches,
        replay_status=REPLAY_PASSED_EXACT if matches else REPLAY_FAILED_MISMATCH,
        first_divergence=first_divergence,
        classification=None if matches else _classify_determinism_divergence(first_divergence),
        event_count_first=len(first.event_log),
        event_count_second=len(second.event_log),
        event_log_fingerprint_first=_event_log_fingerprint(first.event_log),
        event_log_fingerprint_second=_event_log_fingerprint(second.event_log),
        packet_lifecycle_matches=packet_lifecycle_matches,
        conservation_matches=conservation_matches,
        validation_summary_matches=validation_summary_matches,
        completed_packet_set_matches=completed_packet_set_matches,
    )


def _event_log_fingerprint(event_log: tuple[object, ...]) -> str:
    event_payload = [
        {
            "sequence_number": event.sequence_number,
            "packet_id": event.packet_id,
            "event_type": event.event_type.value,
            "entity_id": event.entity_id,
            "physical_tick": event.physical_tick,
        }
        for event in event_log
    ]
    return hashlib.sha256(
        json.dumps(event_payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _packet_lifecycle_summary(engine: LoadingEngine) -> tuple[tuple[str, tuple[str, ...]], ...]:
    events_by_packet: dict[str, list[str]] = {}
    for event in engine.event_log:
        events_by_packet.setdefault(event.packet_id, []).append(
            f"{event.sequence_number}:{event.physical_tick}:"
            f"{event.event_type.value}:{event.entity_id}"
        )
    return tuple(
        (packet_id, tuple(events))
        for packet_id, events in sorted(events_by_packet.items())
    )


def _conservation_summary(
    engine: LoadingEngine,
    resolved_manifest: ResolvedDemandManifest,
) -> dict[str, object]:
    scheduled_departure_count = len(
        ScheduledDemandLoader(resolved_manifest).scheduled_requests
    )
    submitted_departure_count = scheduled_departure_count - _unsubmitted_count(
        resolved_manifest,
        engine,
    )
    return {
        "engine_check_conservation": engine.check_conservation(),
        "scheduled_departures": scheduled_departure_count,
        "submitted_departures": submitted_departure_count,
        "packet_records": len(engine.packets),
        "completed_packets": len(engine.completed_packet_ids),
        "pending_demands": len(engine.pending_demands),
    }


def _validation_summary(
    engine: LoadingEngine,
    nodes: tuple[Node, ...],
    validation_context: ValidationContext,
) -> dict[str, object]:
    commodity_report = build_commodity_parity_validation_report(
        engine,
        validation_context=validation_context,
    )
    spillback_report = build_spillback_validation_report(engine)
    return {
        "count_consistency": validation_context.count_consistency_report.is_consistent,
        "fifo": not _fifo_validation_failures(
            engine,
            validation_context=validation_context,
        ),
        "spillback": spillback_report.is_valid,
        "commodity": commodity_report.is_valid,
        "node": not _node_validation_failures(
            engine,
            nodes,
            validation_context=validation_context,
        ),
    }


def _first_determinism_divergence(
    first: LoadingEngine,
    second: LoadingEngine,
) -> str:
    for index, (first_event, second_event) in enumerate(
        zip(first.event_log, second.event_log)
    ):
        if first_event != second_event:
            return (
                f"event_index={index}:first={first_event!r}:"
                f"second={second_event!r}"
            )
    if len(first.event_log) != len(second.event_log):
        return (
            "event_count_mismatch:"
            f"first={len(first.event_log)}:second={len(second.event_log)}"
        )
    if tuple(sorted(first.completed_packet_ids)) != tuple(
        sorted(second.completed_packet_ids)
    ):
        return "completed_packet_set_mismatch"
    return "derived_summary_mismatch"


def _classify_determinism_divergence(first_divergence: str | None) -> str:
    if first_divergence is None:
        return "none"
    if "physical_tick" in first_divergence or "sequence_number" in first_divergence:
        return "timestamp_or_sequence_instability"
    if "completed_packet_set_mismatch" in first_divergence:
        return "packet_lifecycle_instability"
    if "event_count_mismatch" in first_divergence:
        return "event_count_instability"
    return "another_cause"


def _run_full_profile_engine(
    *,
    links: dict[str, Link],
    nodes: tuple[Node, ...],
    resolved_manifest: ResolvedDemandManifest,
    capacity_rates: dict[str, float],
    tick_limit: int,
) -> LoadingEngine:
    engine = LoadingEngine(
        links=links,
        nodes=nodes,
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        parity_sending_capacity_vehicles_per_tick_by_link=capacity_rates,
        parity_receiving_capacity_vehicles_per_tick_by_link=capacity_rates,
    )
    loader = ScheduledDemandLoader(resolved_manifest)
    loader.submit_due_departures(engine)
    for _ in range(tick_limit):
        if _run_completed(
            engine,
            scheduled_departure_count=len(loader.scheduled_requests),
            submitted_departure_count=(
                len(engine.packets) + len(engine.pending_demands)
            ),
        ):
            break
        engine.step()
        loader.submit_due_departures(engine)
    return engine


def _build_scale_ladder_rung_report(
    *,
    rung_label: str,
    physical_profile: SiouxFallsPhysicalProfile,
    scale_factor: float,
    max_pairs: int | None,
    max_total_quantity_packets: int | None,
    tick_limit: int,
    tick_duration_seconds: float,
    max_runtime_seconds: float | None,
    replay_policy: SiouxFallsReplayPolicy,
    expected_requested_packet_count: int,
) -> SiouxFallsAssumptionProfileScaleRungReport:
    try:
        run_report = _time_limited_assumption_profile_run_report(
            physical_profile=physical_profile,
            scale_factor=scale_factor,
            max_pairs=max_pairs,
            max_total_quantity_packets=max_total_quantity_packets,
            tick_limit=tick_limit,
            tick_duration_seconds=tick_duration_seconds,
            max_runtime_seconds=max_runtime_seconds,
            replay_policy=replay_policy,
        )
    except MemoryError as exc:
        return SiouxFallsAssumptionProfileScaleRungReport(
            rung_label=rung_label,
            requested_packet_count=expected_requested_packet_count,
            submitted_packet_count=0,
            instantiated_packet_count=0,
            completed_packet_count=0,
            unresolved_packet_count=expected_requested_packet_count,
            ticks_run=0,
            runtime_seconds=0.0,
            primary_engine_runtime_seconds=0.0,
            validation_projection_runtime_seconds=0.0,
            validator_runtime_seconds=0.0,
            replay_runtime_seconds=None,
            total_runtime_seconds=0.0,
            event_count=0,
            run_completed=False,
            packet_conservation_passed=False,
            count_consistency_passed=False,
            fifo_validation_passed=False,
            spillback_validation_passed=False,
            commodity_validation_passed=False,
            node_validation_passed=False,
            deterministic_replay_passed=False,
            replay_status=REPLAY_NOT_RUN,
            internal_validation_status="failed",
            scale_status=SCALE_FAILED_MEMORY,
            validation_status="failed",
            failure_reason=f"memory_error:{exc}",
            failures=(f"memory_error:{exc}",),
        )
    except ScaleLadderRuntimeLimitExceeded as exc:
        requested_packet_count = expected_requested_packet_count
        return SiouxFallsAssumptionProfileScaleRungReport(
            rung_label=rung_label,
            requested_packet_count=requested_packet_count,
            submitted_packet_count=0,
            instantiated_packet_count=0,
            completed_packet_count=0,
            unresolved_packet_count=requested_packet_count,
            ticks_run=0,
            runtime_seconds=max_runtime_seconds or 0.0,
            primary_engine_runtime_seconds=0.0,
            validation_projection_runtime_seconds=0.0,
            validator_runtime_seconds=0.0,
            replay_runtime_seconds=None,
            total_runtime_seconds=max_runtime_seconds or 0.0,
            event_count=0,
            run_completed=False,
            packet_conservation_passed=False,
            count_consistency_passed=False,
            fifo_validation_passed=False,
            spillback_validation_passed=False,
            commodity_validation_passed=False,
            node_validation_passed=False,
            deterministic_replay_passed=False,
            replay_status=REPLAY_TIMEOUT,
            internal_validation_status="failed",
            scale_status=SCALE_FAILED_RUNTIME,
            validation_status="failed",
            failure_reason=str(exc),
            failures=(str(exc),),
        )

    failure_reason = None
    scale_status = SCALE_PASSED
    if run_report.internal_validation_status != "passed":
        failure_reason = run_report.failures[0] if run_report.failures else "validation_failed"
        scale_status = SCALE_FAILED_INTERNAL_VALIDATION
    elif run_report.replay_status == REPLAY_FAILED_MISMATCH:
        failure_reason = "deterministic_replay_mismatch"
        scale_status = SCALE_FAILED_REPLAY_MISMATCH
    elif run_report.replay_status == REPLAY_TIMEOUT:
        failure_reason = "deterministic_replay_timeout"
        scale_status = SCALE_FAILED_REPLAY_TIMEOUT
    elif not run_report.run_completed:
        failure_reason = "run_incomplete"
        scale_status = SCALE_FAILED_RUNTIME

    return SiouxFallsAssumptionProfileScaleRungReport(
        rung_label=rung_label,
        requested_packet_count=run_report.requested_packet_count,
        submitted_packet_count=run_report.submitted_departure_count,
        instantiated_packet_count=run_report.instantiated_packet_count,
        completed_packet_count=run_report.completed_packet_count,
        unresolved_packet_count=run_report.unresolved_packet_count,
        ticks_run=run_report.ticks_run,
        runtime_seconds=run_report.runtime_seconds,
        primary_engine_runtime_seconds=run_report.primary_engine_runtime_seconds,
        validation_projection_runtime_seconds=(
            run_report.validation_projection_runtime_seconds
        ),
        validator_runtime_seconds=run_report.validator_runtime_seconds,
        replay_runtime_seconds=run_report.replay_runtime_seconds,
        total_runtime_seconds=run_report.total_runtime_seconds,
        setup_runtime_seconds=run_report.setup_runtime_seconds,
        event_count=run_report.event_count,
        run_completed=run_report.run_completed,
        packet_conservation_passed=run_report.packet_conservation_passed,
        count_consistency_passed=run_report.count_consistency_passed,
        fifo_validation_passed=run_report.fifo_validation_passed,
        spillback_validation_passed=run_report.spillback_validation_passed,
        commodity_validation_passed=run_report.commodity_validation_passed,
        node_validation_passed=run_report.node_validation_passed,
        deterministic_replay_passed=run_report.deterministic_replay_passed,
        replay_status=run_report.replay_status,
        internal_validation_status=run_report.internal_validation_status,
        scale_status=scale_status,
        validation_status=run_report.validation_status,
        failure_reason=failure_reason,
        warnings=run_report.warnings,
        failures=run_report.failures,
    )


def _time_limited_assumption_profile_run_report(
    *,
    physical_profile: SiouxFallsPhysicalProfile,
    scale_factor: float,
    max_pairs: int | None,
    max_total_quantity_packets: int | None,
    tick_limit: int,
    tick_duration_seconds: float,
    max_runtime_seconds: float | None,
    replay_policy: SiouxFallsReplayPolicy,
) -> SiouxFallsAssumptionProfileRunReport:
    if max_runtime_seconds is None:
        return build_sioux_falls_assumption_profile_run_report(
            physical_profile=physical_profile,
            scale_factor=scale_factor,
            max_pairs=max_pairs,
            max_total_quantity_packets=max_total_quantity_packets,
            tick_limit=tick_limit,
            tick_duration_seconds=tick_duration_seconds,
            replay_policy=replay_policy,
        )

    def _handle_timeout(_signum: int, _frame: object) -> None:
        raise ScaleLadderRuntimeLimitExceeded(
            f"runtime_limit_exceeded:{max_runtime_seconds}s"
        )

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _handle_timeout)
    signal.setitimer(signal.ITIMER_REAL, max_runtime_seconds)
    try:
        return build_sioux_falls_assumption_profile_run_report(
            physical_profile=physical_profile,
            scale_factor=scale_factor,
            max_pairs=max_pairs,
            max_total_quantity_packets=max_total_quantity_packets,
            tick_limit=tick_limit,
            tick_duration_seconds=tick_duration_seconds,
            replay_policy=replay_policy,
        )
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous_handler)


def _unsubmitted_count(
    resolved_manifest: ResolvedDemandManifest,
    engine: LoadingEngine,
) -> int:
    scheduled_count = len(ScheduledDemandLoader(resolved_manifest).scheduled_requests)
    return max(scheduled_count - len(engine.packets) - len(engine.pending_demands), 0)


def _run_completed(
    engine: LoadingEngine,
    *,
    scheduled_departure_count: int,
    submitted_departure_count: int,
) -> bool:
    return (
        submitted_departure_count == scheduled_departure_count
        and len(engine.packets) == scheduled_departure_count
        and len(engine.completed_packet_ids) == scheduled_departure_count
        and not engine.pending_demands
    )


def _packet_conservation_gate(
    engine: LoadingEngine,
    *,
    scheduled_departure_count: int,
    submitted_departure_count: int,
) -> SiouxFallsValidationStatus:
    passed = (
        submitted_departure_count == scheduled_departure_count
        and len(engine.packets) == scheduled_departure_count
        and len(engine.completed_packet_ids) == len(engine.packets)
        and not engine.pending_demands
    )
    return _status_from_bool(
        "packet_conservation",
        passed,
        "All scheduled packets are represented exactly once and complete.",
        "Packet conservation failed.",
        _packet_conservation_details(
            engine,
            scheduled_departure_count=scheduled_departure_count,
            submitted_departure_count=submitted_departure_count,
        ),
    )


def _packet_conservation_details(
    engine: LoadingEngine,
    *,
    scheduled_departure_count: int,
    submitted_departure_count: int,
) -> tuple[str, ...]:
    instantiated_event_count = sum(
        event.event_type == EventType.INSTANTIATED for event in engine.event_log
    )
    completed_event_count = sum(
        event.event_type == EventType.COMPLETED for event in engine.event_log
    )
    return (
        f"scheduled_departures={scheduled_departure_count}",
        f"submitted_departures={submitted_departure_count}",
        f"packet_records={len(engine.packets)}",
        f"instantiated_events={instantiated_event_count}",
        f"completed_events={completed_event_count}",
        f"completed_packets={len(engine.completed_packet_ids)}",
        f"pending_demands={len(engine.pending_demands)}",
    )


def _fifo_validation_failures(
    engine: LoadingEngine,
    *,
    validation_context: ValidationContext | None = None,
) -> tuple[str, ...]:
    context = validation_context or ValidationContext.from_engine(engine)
    failures: list[str] = []
    for link_id in sorted(context.link_ids):
        entry_order = context.link_boundary_packet_order(
            link_id=link_id,
            event_type=EventType.LINK_ENTRY,
        )
        exit_order = context.link_boundary_packet_order(
            link_id=link_id,
            event_type=EventType.LINK_EXIT,
        )
        exited_packet_ids = set(exit_order)
        exited_entry_order = [
            packet_id for packet_id in entry_order if packet_id in exited_packet_ids
        ]
        if exit_order != tuple(exited_entry_order):
            failures.append(f"{link_id}:link_fifo_exit_order_mismatch")
    return tuple(failures)


def _node_validation_failures(
    engine: LoadingEngine,
    nodes: tuple[Node, ...],
    *,
    validation_context: ValidationContext | None = None,
) -> tuple[str, ...]:
    context = validation_context or ValidationContext.from_engine(engine, nodes=nodes)
    movement_ids_by_node = {
        node.node_id: {
            movement.movement_id for movement in node.junction_spec.movement_specs
        }
        for node in nodes
    }
    node_by_incoming_link_id = {
        incoming_link_id: node
        for node in nodes
        for incoming_link_id in node.incoming_link_ids
    }
    failures: list[str] = []

    for packet_id, packet_events in sorted(context.events_by_packet_id.items()):
        for index, event in enumerate(packet_events[:-1]):
            if event.event_type != EventType.LINK_EXIT:
                continue
            next_event = packet_events[index + 1]
            if next_event.event_type == EventType.COMPLETED:
                continue
            if next_event.event_type != EventType.LINK_ENTRY:
                failures.append(f"{packet_id}:link_exit_not_followed_by_entry")
                continue
            node = node_by_incoming_link_id.get(event.entity_id)
            if node is None:
                failures.append(f"{packet_id}:{event.entity_id}:missing_transfer_node")
                continue
            movement_id_value = movement_id(event.entity_id, next_event.entity_id)
            if movement_id_value not in movement_ids_by_node[node.node_id]:
                failures.append(
                    f"{packet_id}:{node.node_id}:{movement_id_value}:undeclared_movement"
                )
    if engine.movement_allocator_id != "uc_movement_allocator_stage2_v1":
        failures.append(f"unexpected_allocator:{engine.movement_allocator_id}")
    return tuple(failures)


def _status_from_bool(
    category: str,
    passed: bool,
    pass_reason: str,
    fail_reason: str,
    details: tuple[str, ...],
) -> SiouxFallsValidationStatus:
    return SiouxFallsValidationStatus(
        category=category,
        status=PASS_STATUS if passed else FAIL_STATUS,
        reason=pass_reason if passed else fail_reason,
        detail_count=len(details),
        details=details[:12],
    )


def _assumption_profile_warnings(
    junction_gate: SiouxFallsReadinessGate,
) -> tuple[str, ...]:
    warnings = [
        "engineering_assumption_profile_not_empirical_calibration",
        "bounded_demand_slice_not_full_od_demand_validation",
        "not_external_canonical_sioux_falls_validation",
    ]
    if not junction_gate.is_pass:
        warnings.append(
            "full_network_junction_metadata_not_reviewed:"
            f"{junction_gate.detail_count}_nodes"
        )
    return tuple(warnings)


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


def _run_subnetwork_engine(
    *,
    links: dict[str, Link],
    nodes: tuple[Node, ...],
    tick_limit: int,
) -> LoadingEngine:
    engine = LoadingEngine(
        links=links,
        nodes=nodes,
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        parity_sending_capacity_vehicles_per_tick_by_link={
            link_id: link.resolved_physical_parameters().total_capacity_vehicles_per_tick
            for link_id, link in links.items()
        },
        parity_receiving_capacity_vehicles_per_tick_by_link={
            link_id: link.resolved_physical_parameters().total_capacity_vehicles_per_tick
            for link_id, link in links.items()
        },
    )
    for demand in _subnetwork_demands():
        engine.instantiate(demand)
    for _ in range(tick_limit):
        engine.step()
    return engine


def _subnetwork_loading_links(
    canonical_links: Iterable[CanonicalTopologyLink],
    *,
    tick_duration_seconds: float,
) -> dict[str, Link]:
    return {
        canonical_link.link_id: _subnetwork_loading_link(
            canonical_link,
            tick_duration_seconds=tick_duration_seconds,
        )
        for canonical_link in canonical_links
    }


def _subnetwork_loading_link(
    canonical_link: CanonicalTopologyLink,
    *,
    tick_duration_seconds: float,
) -> Link:
    if canonical_link.free_flow_speed_mps is None:
        raise ValueError(f"{canonical_link.link_id} missing free-flow speed")
    if canonical_link.capacity_veh_per_hour_per_lane is None:
        raise ValueError(f"{canonical_link.link_id} missing source capacity")
    jam_density = _jam_density_for_assumed_backward_wave_speed(
        free_flow_speed_mps=canonical_link.free_flow_speed_mps,
        capacity_veh_per_hour_per_lane=canonical_link.capacity_veh_per_hour_per_lane,
        backward_wave_speed_mps=SUBNETWORK_BACKWARD_WAVE_SPEED_MPS,
    )
    storage_capacity = max(
        1,
        floor(
            ((canonical_link.length_m or 0.0) / 1000.0)
            * (canonical_link.lane_count or 1)
            * jam_density
        ),
    )
    return Link(
        link_id=canonical_link.link_id,
        declared_sending_capacity_per_tick=1,
        declared_receiving_capacity_per_tick=1,
        declared_storage_capacity_packets=storage_capacity,
        length_m=canonical_link.length_m,
        lane_count=canonical_link.lane_count,
        free_flow_speed_mps=canonical_link.free_flow_speed_mps,
        jam_density_veh_per_km_per_lane=jam_density,
        backward_wave_speed_mps=SUBNETWORK_BACKWARD_WAVE_SPEED_MPS,
        capacity_veh_per_hour_per_lane=canonical_link.capacity_veh_per_hour_per_lane,
        tick_duration_seconds=tick_duration_seconds,
    )


def _jam_density_for_assumed_backward_wave_speed(
    *,
    free_flow_speed_mps: float,
    capacity_veh_per_hour_per_lane: float,
    backward_wave_speed_mps: float,
) -> float:
    return (
        capacity_veh_per_hour_per_lane
        * (free_flow_speed_mps + backward_wave_speed_mps)
        / (3600.0 * free_flow_speed_mps * backward_wave_speed_mps)
        * 1000.0
    )


def _subnetwork_nodes() -> tuple[Node, ...]:
    return (
        Node(
            node_id="N002",
            incoming_link_ids=("L0001",),
            outgoing_link_ids=("L0003", "L0004"),
        ),
        Node(
            node_id="N003",
            incoming_link_ids=("L0002",),
            outgoing_link_ids=("L0006",),
        ),
        Node(
            node_id="N004",
            incoming_link_ids=("L0006",),
            outgoing_link_ids=("L0009",),
        ),
        Node(
            node_id="N005",
            incoming_link_ids=("L0009",),
            outgoing_link_ids=("L0012",),
        ),
        Node(
            node_id="N006",
            incoming_link_ids=("L0004", "L0012"),
            outgoing_link_ids=("L0016",),
            merge_priorities=(("L0004", 1), ("L0012", 1)),
        ),
    )


def _subnetwork_demands() -> tuple[DemandDeclaration, ...]:
    demands: list[DemandDeclaration] = []
    for route_index, (_, route_intent) in enumerate(SUBNETWORK_ROUTES, start=1):
        for unit_index in range(1, 3):
            demands.append(
                DemandDeclaration(
                    demand_id=f"sioux-subnetwork-r{route_index}-u{unit_index}",
                    departure_tick=0,
                    route_intent=route_intent,
                )
            )
    return tuple(demands)


def _subnetwork_metadata_assumptions() -> tuple[SiouxFallsSubnetworkMetadataAssumption, ...]:
    return (
        SiouxFallsSubnetworkMetadataAssumption(
            field_name="backward_wave_speed_mps",
            value=f"{SUBNETWORK_BACKWARD_WAVE_SPEED_MPS}",
            provenance_label="benchmark_assumption_not_empirical_calibration",
            note=(
                "Fixed for the supported subnetwork because the Sioux Falls TNTP "
                "network does not provide backward-wave speed."
            ),
        ),
        SiouxFallsSubnetworkMetadataAssumption(
            field_name="jam_density_veh_per_km_per_lane",
            value="derived_per_link_from_TNTP_capacity_free_flow_speed_and_assumed_backward_wave_speed",
            provenance_label="benchmark_assumption_not_empirical_calibration",
            note=(
                "Derived so each selected link is triangular-FD consistent with "
                "its TNTP capacity under the fixed assumed backward-wave speed."
            ),
        ),
        SiouxFallsSubnetworkMetadataAssumption(
            field_name="declared_storage_capacity_packets",
            value="derived_from_length_lane_count_and_assumed_jam_density",
            provenance_label="benchmark_assumption_not_legacy_storage_override",
            note=(
                "The subnetwork adapter does not use the legacy synthetic storage "
                "override as parity evidence."
            ),
        ),
    )


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


def _junction_metadata_gate(nodes: tuple[Node, ...]) -> SiouxFallsReadinessGate:
    missing_metadata_node_ids = tuple(
        node.node_id
        for node in nodes
        if _node_needs_reviewed_stage2_junction_metadata(node)
        and not _node_has_stage2_junction_metadata(node)
    )
    if not missing_metadata_node_ids:
        return _pass_gate(
            "junction_semantics_metadata",
            "All full-topology junctions have reviewed Stage 2 junction metadata or do not require it.",
        )
    return _fail_gate(
        "junction_semantics_metadata",
        "Full Sioux Falls contains complex junctions without reviewed conflict, lane-group, or signal metadata.",
        detail_count=len(missing_metadata_node_ids),
        details=missing_metadata_node_ids[:12],
    )


def _node_needs_reviewed_stage2_junction_metadata(node: Node) -> bool:
    return len(node.incoming_link_ids) > 1 and len(node.outgoing_link_ids) > 1


def _node_has_stage2_junction_metadata(node: Node) -> bool:
    junction_spec = node.junction_spec
    return bool(
        junction_spec.lane_group_ids
        or junction_spec.movement_lane_group_mappings
        or junction_spec.conflict_resource_ids
        or any(movement.signal_group_id is not None for movement in junction_spec.movement_specs)
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


def _count_gate(report: object) -> SiouxFallsReadinessGate:
    if report.is_consistent:
        return _pass_gate(
            "count_evidence",
            "Aggregate counts, route counts, packet ordinals, and travel-time curves are consistent.",
        )
    return _fail_gate(
        "count_evidence",
        "Count evidence is inconsistent.",
        detail_count=len(report.ineligibility_reasons),
        details=report.ineligibility_reasons[:12],
    )


def _conservation_gate(engine: LoadingEngine) -> SiouxFallsReadinessGate:
    instantiated_event_count = sum(
        event.event_type == EventType.INSTANTIATED for event in engine.event_log
    )
    completed_event_count = sum(
        event.event_type == EventType.COMPLETED for event in engine.event_log
    )
    if (
        instantiated_event_count == len(engine.packets)
        and completed_event_count == len(engine.completed_packet_ids)
        and completed_event_count == len(engine.packets)
        and not engine.pending_demands
    ):
        return _pass_gate(
            "packet_conservation",
            "All instantiated subnetwork packets are represented exactly once and complete.",
        )
    return _fail_gate(
        "packet_conservation",
        "Subnetwork packet conservation failed.",
        details=(
            f"instantiated_events={instantiated_event_count}",
            f"packet_records={len(engine.packets)}",
            f"completed_events={completed_event_count}",
            f"completed_packets={len(engine.completed_packet_ids)}",
            f"pending_demands={len(engine.pending_demands)}",
        ),
    )


def _deterministic_replay_gate(
    first: LoadingEngine,
    second: LoadingEngine,
) -> SiouxFallsReadinessGate:
    if first.event_log == second.event_log:
        return _pass_gate(
            "deterministic_replay",
            "Repeated subnetwork parity runs produce identical canonical events.",
        )
    return _fail_gate(
        "deterministic_replay",
        "Repeated subnetwork parity runs produced different canonical events.",
        details=(
            f"first_event_count={len(first.event_log)}",
            f"second_event_count={len(second.event_log)}",
        ),
    )


def _subnetwork_structure_gate(nodes: tuple[Node, ...]) -> SiouxFallsReadinessGate:
    details = tuple(
        f"{node.node_id}:movements="
        + ",".join(
            f"{movement.upstream_link_id}->{movement.downstream_link_id}"
            for movement in node.junction_spec.movement_specs
        )
        for node in nodes
    )
    return _pass_gate(
        "supported_subnetwork_structure",
        "Selected Sioux Falls subnetwork uses Stage 2 movement-allocation semantics.",
        details=details,
    )


def _unsupported_advanced_full_network_node_ids(topology: object) -> tuple[str, ...]:
    unsupported: list[str] = []
    for node in topology.nodes:
        junction_spec = Node(
            node.node_id,
            incoming_link_ids=node.incoming_link_ids,
            outgoing_link_ids=node.outgoing_link_ids,
        ).junction_spec
        if (
            junction_spec.lane_group_ids
            or junction_spec.movement_lane_group_mappings
            or junction_spec.conflict_resource_ids
            or junction_spec.governance_refs
            or any(
                movement.lane_group_ids
                or movement.conflict_resource_ids
                or movement.signal_group_id is not None
                for movement in junction_spec.movement_specs
            )
        ):
            unsupported.append(node.node_id)
    return tuple(unsupported)


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
    parser.add_argument(
        "--max-runtime-seconds-per-rung",
        type=float,
        default=None,
        help="Optional per-rung runtime budget for the assumption-profile scale ladder.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path for writing the emitted JSON payload.",
    )
    parser.add_argument(
        "--subnetwork",
        action="store_true",
        help="Run the supported movement-allocation Sioux Falls subnetwork readiness gates.",
    )
    parser.add_argument(
        "--assumption-profile",
        action="store_true",
        help="Run the full topology under SiouxFallsPhysicalProfile_UC_Default_v1.",
    )
    parser.add_argument(
        "--assumption-profile-scale-ladder",
        action="store_true",
        help="Run bounded Sioux Falls assumption-profile packet scales and then a full-demand run if all bounded rungs pass.",
    )
    args = parser.parse_args()

    if args.assumption_profile_scale_ladder:
        payload = build_sioux_falls_assumption_profile_scale_ladder_report(
            tick_limit=args.tick_limit,
            max_runtime_seconds_per_rung=args.max_runtime_seconds_per_rung,
        ).status_payload()
    elif args.assumption_profile:
        payload = build_sioux_falls_assumption_profile_run_report(
            scale_factor=args.scale_factor,
            max_pairs=args.max_pairs,
            max_total_quantity_packets=args.max_total_quantity_packets,
            tick_limit=args.tick_limit,
        ).status_payload()
    elif args.subnetwork:
        payload = build_sioux_falls_supported_subnetwork_readiness_report(
            tick_limit=args.tick_limit,
        ).status_payload()
    else:
        payload = build_sioux_falls_parity_readiness_report(
            scale_factor=args.scale_factor,
            max_pairs=args.max_pairs,
            max_total_quantity_packets=args.max_total_quantity_packets,
            tick_limit=args.tick_limit,
        ).status_payload()

    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output_json is not None:
        args.output_json.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
