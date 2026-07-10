"""Anaheim parity-readiness and scale-ladder reports."""

from __future__ import annotations

import hashlib
import signal
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

from urban_cybernetics.benchmarks.anaheim import (
    ANAHEIM_FLOW_PATH,
    ANAHEIM_NET_PATH,
    ANAHEIM_TRIPS_PATH,
)
from urban_cybernetics.canonical_validation.anaheim_physical_profile import (
    AnaheimPhysicalProfile,
    build_anaheim_uc_default_physical_profile,
)
from urban_cybernetics.canonical_validation.sioux_falls_readiness import (
    FAIL_STATUS,
    NOT_RUN_STATUS,
    PASS_STATUS,
    REPLAY_FAILED_MISMATCH,
    REPLAY_NOT_RUN,
    REPLAY_PASSED_EXACT,
    REPLAY_SKIPPED_AFTER_CERTIFICATION,
    REPLAY_TIMEOUT,
    SCALE_FAILED_INTERNAL_VALIDATION,
    SCALE_FAILED_MEMORY,
    SCALE_FAILED_REPLAY_MISMATCH,
    SCALE_FAILED_REPLAY_TIMEOUT,
    SCALE_FAILED_RUNTIME,
    SCALE_PASSED,
    ScaleLadderRuntimeLimitExceeded,
    SiouxFallsAssumptionProfileRunReport,
    SiouxFallsAssumptionProfileScaleLadderReport,
    SiouxFallsAssumptionProfileScaleRungReport,
    SiouxFallsReplayPolicy,
    SiouxFallsValidationStatus,
    _fifo_validation_failures,
    _junction_metadata_gate,
    _node_validation_failures,
    _packet_conservation_gate,
    _run_completed,
    _run_full_profile_engine,
    _status_from_bool,
    _unsubmitted_count,
)
from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.demand import (
    FixedDepartureSchedule,
    ScheduledDemandLoader,
    resolve_demand_routes,
)
from urban_cybernetics.demand.anaheim import load_anaheim_demand_manifest
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.topology.anaheim import load_anaheim_topology
from urban_cybernetics.validation import (
    ValidationContext,
    assess_physical_parameter_eligibility,
    build_commodity_parity_validation_report,
    build_spillback_validation_report,
)


ASSUMPTION_PROFILE_EVIDENCE_LABEL = "anaheim_uc_default_assumption_profile_run"
SCALE_LADDER_EVIDENCE_LABEL = "anaheim_uc_default_assumption_profile_scale_ladder"


@dataclass(frozen=True, slots=True)
class AnaheimReadinessStatus:
    """One Anaheim readiness category."""

    category: str
    status: str
    reason: str
    detail_count: int = 0
    details: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AnaheimReadinessReport:
    """Machine-readable Anaheim readiness status."""

    benchmark_id: str
    requested_model_profile_id: str
    topology_load_status: AnaheimReadinessStatus
    demand_load_status: AnaheimReadinessStatus
    physical_metadata_status: AnaheimReadinessStatus
    movement_junction_support_status: AnaheimReadinessStatus
    parity_initialization_status: AnaheimReadinessStatus
    assumption_profile_warnings: tuple[str, ...]
    topology_hash: str
    demand_hash: str
    physical_profile_hash: str
    topology_node_count: int
    topology_link_count: int
    od_pair_count: int
    full_demand_requested_packet_count: int
    source_file_hashes: tuple[tuple[str, str], ...]

    def status_payload(self) -> dict[str, object]:
        """Return a JSON-ready readiness payload."""

        return asdict(self)


def build_anaheim_readiness_report(
    *,
    physical_profile: AnaheimPhysicalProfile | None = None,
    tick_duration_seconds: float = 2.0,
) -> AnaheimReadinessReport:
    """Build Anaheim topology, demand, metadata, and initialization readiness."""

    topology = load_anaheim_topology()
    profile = physical_profile or build_anaheim_uc_default_physical_profile(
        topology=topology
    )
    manifest = load_anaheim_demand_manifest(
        topology=topology,
        scale_factor=1.0,
        max_pairs=None,
        max_total_quantity_packets=None,
        departure_schedule=FixedDepartureSchedule(departure_tick=0),
    )
    links = profile.as_loading_links(tick_duration_seconds=tick_duration_seconds)
    nodes = topology.as_loading_nodes()
    physical_report = assess_physical_parameter_eligibility(
        links.values(),
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
    )
    junction_gate = _junction_metadata_gate(nodes)
    parity_initialization_error = None
    try:
        LoadingEngine(
            links=links,
            nodes=nodes,
            model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
            parity_sending_capacity_vehicles_per_tick_by_link=(
                profile.parity_capacity_rates_by_link(
                    tick_duration_seconds=tick_duration_seconds
                )
            ),
            parity_receiving_capacity_vehicles_per_tick_by_link=(
                profile.parity_capacity_rates_by_link(
                    tick_duration_seconds=tick_duration_seconds
                )
            ),
        )
    except ValueError as exc:
        parity_initialization_error = f"{type(exc).__name__}: {exc}"

    return AnaheimReadinessReport(
        benchmark_id="anaheim_tntp_v1",
        requested_model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        topology_load_status=AnaheimReadinessStatus(
            category="topology_load",
            status=PASS_STATUS,
            reason="Anaheim TNTP topology loaded as canonical topology.",
            detail_count=3,
            details=(
                f"topology_hash={topology.topology_hash}",
                f"nodes={len(topology.nodes)}",
                f"links={len(topology.links)}",
            ),
        ),
        demand_load_status=AnaheimReadinessStatus(
            category="demand_load",
            status=PASS_STATUS,
            reason="Anaheim TNTP trips loaded as an OD demand manifest.",
            detail_count=3,
            details=(
                f"demand_hash={manifest.manifest_hash}",
                f"od_pairs={len(manifest.declarations)}",
                f"declared_packets={manifest.total_declared_quantity_packets}",
            ),
        ),
        physical_metadata_status=AnaheimReadinessStatus(
            category="physical_metadata",
            status=PASS_STATUS if physical_report.is_parity_eligible else FAIL_STATUS,
            reason=(
                "Anaheim UC default profile physical metadata is parity-eligible."
                if physical_report.is_parity_eligible
                else "Anaheim UC default profile physical metadata is not parity-eligible."
            ),
            detail_count=len(physical_report.ineligibility_reasons),
            details=physical_report.ineligibility_reasons[:12],
        ),
        movement_junction_support_status=AnaheimReadinessStatus(
            category="movement_junction_support",
            status=junction_gate.status,
            reason=(
                "All Anaheim junctions have reviewed Stage 2 metadata or do not require it."
                if junction_gate.status == PASS_STATUS
                else "Anaheim contains complex junctions without reviewed conflict, lane-group, or signal metadata."
            ),
            detail_count=junction_gate.detail_count,
            details=junction_gate.details,
        ),
        parity_initialization_status=AnaheimReadinessStatus(
            category="parity_initialization",
            status=PASS_STATUS if parity_initialization_error is None else FAIL_STATUS,
            reason=(
                "Anaheim topology initialized under parity_ltm_v1."
                if parity_initialization_error is None
                else "Anaheim topology failed parity_ltm_v1 initialization."
            ),
            detail_count=0 if parity_initialization_error is None else 1,
            details=() if parity_initialization_error is None else (parity_initialization_error,),
        ),
        assumption_profile_warnings=_anaheim_assumption_profile_warnings(
            junction_detail_count=junction_gate.detail_count
        ),
        topology_hash=topology.topology_hash,
        demand_hash=manifest.manifest_hash,
        physical_profile_hash=profile.profile_hash,
        topology_node_count=len(topology.nodes),
        topology_link_count=len(topology.links),
        od_pair_count=len(manifest.declarations),
        full_demand_requested_packet_count=manifest.total_declared_quantity_packets,
        source_file_hashes=_source_file_hashes(),
    )


def build_anaheim_assumption_profile_run_report(
    *,
    physical_profile: AnaheimPhysicalProfile | None = None,
    scale_factor: float = 1.0,
    max_pairs: int | None = None,
    max_total_quantity_packets: int | None = 1_000,
    tick_limit: int = 20_000,
    tick_duration_seconds: float = 2.0,
    replay_policy: SiouxFallsReplayPolicy | None = None,
) -> SiouxFallsAssumptionProfileRunReport:
    """Run full Anaheim topology under the UC default physical profile."""

    topology = load_anaheim_topology()
    profile = physical_profile or build_anaheim_uc_default_physical_profile(
        topology=topology
    )
    manifest = load_anaheim_demand_manifest(
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

    total_started_at = perf_counter()
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
            "benchmark_id": "anaheim_tntp_v1",
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
            (
                f"scheduled_departures={scheduled_departure_count}",
                f"submitted_departures={submitted_departure_count}",
                f"packet_records={len(engine.packets)}",
                f"completed_packets={len(engine.completed_packet_ids)}",
                f"pending_demands={len(engine.pending_demands)}",
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
    warnings = _anaheim_assumption_profile_warnings(
        junction_detail_count=junction_gate.detail_count
    )
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
        benchmark_id="anaheim_tntp_v1",
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


def build_anaheim_assumption_profile_scale_ladder_report(
    *,
    physical_profile: AnaheimPhysicalProfile | None = None,
    bounded_packet_rungs: tuple[int, ...] = (
        1_000,
        5_000,
        10_000,
        25_000,
        50_000,
        100_000,
    ),
    tick_limit: int = 20_000,
    tick_duration_seconds: float = 2.0,
    include_full_demand_run: bool = True,
    max_runtime_seconds_per_rung: float | None = None,
    replay_policy: SiouxFallsReplayPolicy | None = None,
) -> SiouxFallsAssumptionProfileScaleLadderReport:
    """Run a deterministic Anaheim assumption-profile scale ladder."""

    topology = load_anaheim_topology()
    profile = physical_profile or build_anaheim_uc_default_physical_profile(
        topology=topology
    )
    full_manifest = load_anaheim_demand_manifest(
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
    active_replay_policy = replay_policy or SiouxFallsReplayPolicy(
        exact_replay_packet_limit=10_000,
        determinism_certified_packet_count=10_000,
    )

    for packet_cap in bounded_packet_rungs:
        rung_report = _build_anaheim_scale_ladder_rung_report(
            rung_label=str(packet_cap),
            physical_profile=profile,
            max_total_quantity_packets=packet_cap,
            tick_limit=tick_limit,
            tick_duration_seconds=tick_duration_seconds,
            max_runtime_seconds=max_runtime_seconds_per_rung,
            replay_policy=active_replay_policy,
        )
        rung_reports.append(rung_report)
        if rung_report.failure_reason is not None:
            stopped_early = True
            stop_reason = f"{rung_report.rung_label}:{rung_report.failure_reason}"
            break

    full_demand_run_attempted = include_full_demand_run and not stopped_early
    if full_demand_run_attempted:
        full_rung_report = _build_anaheim_scale_ladder_rung_report(
            rung_label="full_demand",
            physical_profile=profile,
            max_total_quantity_packets=None,
            tick_limit=tick_limit,
            tick_duration_seconds=tick_duration_seconds,
            max_runtime_seconds=max_runtime_seconds_per_rung,
            replay_policy=active_replay_policy,
        )
        rung_reports.append(full_rung_report)
        if full_rung_report.failure_reason is not None:
            stopped_early = True
            stop_reason = f"{full_rung_report.rung_label}:{full_rung_report.failure_reason}"

    return SiouxFallsAssumptionProfileScaleLadderReport(
        benchmark_id="anaheim_tntp_v1",
        requested_model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        evidence_label=SCALE_LADDER_EVIDENCE_LABEL,
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


def _build_anaheim_scale_ladder_rung_report(
    *,
    rung_label: str,
    physical_profile: AnaheimPhysicalProfile,
    max_total_quantity_packets: int | None,
    tick_limit: int,
    tick_duration_seconds: float,
    max_runtime_seconds: float | None,
    replay_policy: SiouxFallsReplayPolicy,
) -> SiouxFallsAssumptionProfileScaleRungReport:
    try:
        run_report = _time_limited_anaheim_assumption_profile_run_report(
            physical_profile=physical_profile,
            max_total_quantity_packets=max_total_quantity_packets,
            tick_limit=tick_limit,
            tick_duration_seconds=tick_duration_seconds,
            max_runtime_seconds=max_runtime_seconds,
            replay_policy=replay_policy,
        )
    except MemoryError as exc:
        return _failed_rung(
            rung_label=rung_label,
            requested_packet_count=max_total_quantity_packets or 0,
            scale_status=SCALE_FAILED_MEMORY,
            replay_status=REPLAY_NOT_RUN,
            failure_reason=f"memory_error:{exc}",
        )
    except ScaleLadderRuntimeLimitExceeded as exc:
        return _failed_rung(
            rung_label=rung_label,
            requested_packet_count=max_total_quantity_packets or 0,
            scale_status=SCALE_FAILED_RUNTIME,
            replay_status=REPLAY_TIMEOUT,
            failure_reason=str(exc),
            runtime_seconds=max_runtime_seconds or 0.0,
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


def _time_limited_anaheim_assumption_profile_run_report(
    *,
    physical_profile: AnaheimPhysicalProfile,
    max_total_quantity_packets: int | None,
    tick_limit: int,
    tick_duration_seconds: float,
    max_runtime_seconds: float | None,
    replay_policy: SiouxFallsReplayPolicy,
) -> SiouxFallsAssumptionProfileRunReport:
    if max_runtime_seconds is None:
        return build_anaheim_assumption_profile_run_report(
            physical_profile=physical_profile,
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
        return build_anaheim_assumption_profile_run_report(
            physical_profile=physical_profile,
            max_total_quantity_packets=max_total_quantity_packets,
            tick_limit=tick_limit,
            tick_duration_seconds=tick_duration_seconds,
            replay_policy=replay_policy,
        )
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous_handler)


def _failed_rung(
    *,
    rung_label: str,
    requested_packet_count: int,
    scale_status: str,
    replay_status: str,
    failure_reason: str,
    runtime_seconds: float = 0.0,
) -> SiouxFallsAssumptionProfileScaleRungReport:
    return SiouxFallsAssumptionProfileScaleRungReport(
        rung_label=rung_label,
        requested_packet_count=requested_packet_count,
        submitted_packet_count=0,
        instantiated_packet_count=0,
        completed_packet_count=0,
        unresolved_packet_count=requested_packet_count,
        ticks_run=0,
        runtime_seconds=runtime_seconds,
        primary_engine_runtime_seconds=0.0,
        validation_projection_runtime_seconds=0.0,
        validator_runtime_seconds=0.0,
        replay_runtime_seconds=None,
        total_runtime_seconds=runtime_seconds,
        event_count=0,
        run_completed=False,
        packet_conservation_passed=False,
        count_consistency_passed=False,
        fifo_validation_passed=False,
        spillback_validation_passed=False,
        commodity_validation_passed=False,
        node_validation_passed=False,
        deterministic_replay_passed=False,
        replay_status=replay_status,
        internal_validation_status="failed",
        scale_status=scale_status,
        validation_status="failed",
        failure_reason=failure_reason,
        failures=(failure_reason,),
    )


def _anaheim_assumption_profile_warnings(
    *,
    junction_detail_count: int,
) -> tuple[str, ...]:
    warnings = [
        "engineering_assumption_profile_not_empirical_calibration",
        "bounded_demand_slice_not_full_od_demand_validation",
        "not_external_canonical_anaheim_validation",
    ]
    if junction_detail_count:
        warnings.append(
            "full_network_junction_metadata_not_reviewed:"
            f"{junction_detail_count}_nodes"
        )
    return tuple(warnings)


def _source_file_hashes() -> tuple[tuple[str, str], ...]:
    paths = (ANAHEIM_NET_PATH, ANAHEIM_TRIPS_PATH, ANAHEIM_FLOW_PATH)
    hashes: list[tuple[str, str]] = []
    for path in paths:
        if path.exists():
            hashes.append((str(path), hashlib.sha256(path.read_bytes()).hexdigest()))
    return tuple(hashes)
