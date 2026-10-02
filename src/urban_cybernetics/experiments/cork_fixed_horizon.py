# SPDX-License-Identifier: MPL-2.0
"""Fixed-physical-horizon scalability experiment on the pinned Cork graph."""

from __future__ import annotations

import cProfile
import gc
import os
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from time import perf_counter, process_time
from typing import Any

from urban_cybernetics.core import EventType, LifecycleState
from urban_cybernetics.demand.cork_synthetic import (
    DEFAULT_CORK_DEMAND_SEED,
    DEFAULT_LOADING_WINDOW_SECONDS,
    DEFAULT_MAXIMUM_UNIQUE_OD_PAIRS,
    build_cork_synthetic_demand,
    resolve_cork_weighted_routes,
)
from urban_cybernetics.demand.scheduled_loading import ScheduledDemandLoader
from urban_cybernetics.experiments.cork_city_scale import (
    CorkExperimentFailure,
    _build_engine,
    _event_stream_identity,
    _median,
    _peak_rss_bytes,
    _stable_hash,
)
from urban_cybernetics.extensions.city_scale_v2 import CITY_SCALE_V2_EVIDENCE_MODE
from urban_cybernetics.loading.transfer_policy import (
    REJECTED_DOWNSTREAM_SUPPLY,
    REJECTED_UPSTREAM_FIFO,
)
from urban_cybernetics.topology.cork import (
    CORK_TICK_DURATION_SECONDS,
    CorkCanonicalNetwork,
    load_cork_canonical_network,
)


CORK_FIXED_HORIZON_EXPERIMENT_VERSION = "uc.cork-fixed-horizon.v1"
CORK_FIXED_HORIZON_ARTIFACT_VERSION = "uc.cork-fixed-horizon-rung.v1"
LOADING_WINDOW_SECONDS = DEFAULT_LOADING_WINDOW_SECONDS
POST_LOADING_OBSERVATION_SECONDS = 300.0
TOTAL_HORIZON_SECONDS = LOADING_WINDOW_SECONDS + POST_LOADING_OBSERVATION_SECONDS
TOTAL_HORIZON_TICKS = round(TOTAL_HORIZON_SECONDS / CORK_TICK_DURATION_SECONDS)
DEFAULT_RUNTIME_GUARD_SECONDS = 600.0
MANDATORY_REPLAY_PACKET_LIMIT = 1_000
OPTIONAL_REPLAY_PACKET_COUNT = 2_500

if TOTAL_HORIZON_TICKS != 15_000:  # pragma: no cover - frozen protocol guard
    raise AssertionError("Cork fixed horizon must be exactly 15,000 ticks")


def run_cork_fixed_horizon_rung(
    packet_count: int,
    *,
    graph_path: Path | None = None,
    seed: int = DEFAULT_CORK_DEMAND_SEED,
    runtime_guard_seconds: float = DEFAULT_RUNTIME_GUARD_SECONDS,
    run_replay: bool | None = None,
    profile_output: Path | None = None,
) -> dict[str, Any]:
    """Run one Cork demand rung for exactly the declared physical horizon."""

    if packet_count <= 0:
        raise ValueError("packet_count must be positive")
    if runtime_guard_seconds <= 0:
        raise ValueError("runtime_guard_seconds must be positive")

    total_wall_start = perf_counter()
    total_cpu_start = process_time()
    phase: dict[str, float] = {}

    started = perf_counter()
    network = load_cork_canonical_network(graph_path)
    phase["topology_adapter_and_physical_build_seconds"] = perf_counter() - started

    started = perf_counter()
    demand = build_cork_synthetic_demand(
        network,
        packet_count=packet_count,
        seed=seed,
        maximum_unique_od_pairs=DEFAULT_MAXIMUM_UNIQUE_OD_PAIRS,
        loading_window_seconds=LOADING_WINDOW_SECONDS,
    )
    phase["synthetic_demand_build_seconds"] = perf_counter() - started

    routes = resolve_cork_weighted_routes(network, demand)
    phase["route_resolution_seconds"] = routes.route_resolution_seconds

    started = perf_counter()
    loader = ScheduledDemandLoader(routes.resolved_manifest)
    phase["schedule_expansion_seconds"] = perf_counter() - started

    started = perf_counter()
    engine = _build_engine(network)
    phase["engine_build_seconds"] = perf_counter() - started

    profiler = cProfile.Profile() if profile_output is not None else None
    if profiler is not None:
        profiler.enable()
    evolution_wall_start = perf_counter()
    evolution_cpu_start = process_time()
    evolution = _evolve_to_horizon(
        engine,
        loader,
        runtime_guard_seconds=runtime_guard_seconds,
        wall_start=evolution_wall_start,
    )
    evolution_wall = perf_counter() - evolution_wall_start
    evolution_cpu = process_time() - evolution_cpu_start
    if profiler is not None:
        profiler.disable()
        profile_output.parent.mkdir(parents=True, exist_ok=True)
        profiler.dump_stats(profile_output)
    phase["loading_and_evolution_wall_seconds"] = evolution_wall
    phase["loading_and_evolution_cpu_seconds"] = evolution_cpu

    started = perf_counter()
    engine.materialize_all_receiving_credit()
    validation = _validate_horizon_state(
        engine,
        loader,
        routes.resolved_manifest,
        network,
        requested_packet_count=packet_count,
        require_full_horizon=evolution["full_horizon_executed"],
    )
    phase["validation_seconds"] = perf_counter() - started

    started = perf_counter()
    event_identity = _event_stream_identity(engine.event_log)
    phase["event_serialization_and_hashing_seconds"] = perf_counter() - started

    horizon_state = _horizon_state_summary(
        engine,
        loader,
        requested_packet_count=packet_count,
        evolution=evolution,
    )
    horizon_state_hash = _stable_hash("cork-fixed-horizon-state", horizon_state)
    primary = _primary_summary(
        engine=engine,
        packet_count=packet_count,
        event_identity=event_identity,
        horizon_state=horizon_state,
        horizon_state_hash=horizon_state_hash,
        phase=phase,
        routes=routes,
        demand=demand,
        validation=validation,
        evolution_wall=evolution_wall,
        evolution_cpu=evolution_cpu,
        evolution=evolution,
    )

    replay_policy = _fixed_horizon_replay_policy(
        packet_count=packet_count,
        run_replay=run_replay,
        primary=primary,
    )
    if replay_policy["execute"] and evolution["full_horizon_executed"]:
        expected_event_hash = event_identity["event_stream_sha256"]
        expected_state_hash = horizon_state_hash
        del engine
        gc.collect()
        replay_started = perf_counter()
        replay_engine = _build_engine(network)
        replay_loader = ScheduledDemandLoader(routes.resolved_manifest)
        replay_evolution = _evolve_to_horizon(
            replay_engine,
            replay_loader,
            runtime_guard_seconds=runtime_guard_seconds,
            wall_start=replay_started,
        )
        if not replay_evolution["full_horizon_executed"]:
            raise CorkExperimentFailure("fixed-horizon replay hit runtime guard")
        replay_engine.materialize_all_receiving_credit()
        replay_identity = _event_stream_identity(replay_engine.event_log)
        replay_state = _horizon_state_summary(
            replay_engine,
            replay_loader,
            requested_packet_count=packet_count,
            evolution=replay_evolution,
        )
        replay_state_hash = _stable_hash("cork-fixed-horizon-state", replay_state)
        exact = (
            replay_identity["event_stream_sha256"] == expected_event_hash
            and replay_state_hash == expected_state_hash
        )
        replay = {
            "status": "passed_exact_replay" if exact else "failed_exact_replay_mismatch",
            "runtime_seconds": perf_counter() - replay_started,
            "event_stream_sha256": replay_identity["event_stream_sha256"],
            "event_count": replay_identity["event_count"],
            "horizon_state_hash": replay_state_hash,
            "policy": replay_policy,
        }
        if not exact:
            raise CorkExperimentFailure("fixed-horizon replay identity mismatch")
    else:
        replay = {
            "status": (
                "skipped_incomplete_guarded_run"
                if not evolution["full_horizon_executed"]
                else "skipped_by_explicit_cost_policy"
            ),
            "runtime_seconds": None,
            "event_stream_sha256": None,
            "event_count": None,
            "horizon_state_hash": None,
            "policy": replay_policy,
        }

    run_identity = _stable_hash(
        "cork-fixed-horizon-run",
        {
            "experiment_version": CORK_FIXED_HORIZON_EXPERIMENT_VERSION,
            "topology_hash": network.topology_hash,
            "physical_profile_hash": network.physical_profile_hash,
            "manifest_hash": demand.manifest.manifest_hash,
            "route_resolution_hash": routes.route_resolution_hash,
            "event_stream_sha256": event_identity["event_stream_sha256"],
            "horizon_state_hash": horizon_state_hash,
            "packet_count": packet_count,
            "seed": seed,
            "horizon_ticks": TOTAL_HORIZON_TICKS,
        },
    )
    return {
        "artifact_version": CORK_FIXED_HORIZON_ARTIFACT_VERSION,
        "experiment_version": CORK_FIXED_HORIZON_EXPERIMENT_VERSION,
        "run_identity_hash": run_identity,
        "packet_count": packet_count,
        "seed": seed,
        "process_id": os.getpid(),
        "protocol": {
            "loading_window_seconds": LOADING_WINDOW_SECONDS,
            "post_loading_observation_seconds": POST_LOADING_OBSERVATION_SECONDS,
            "total_horizon_seconds": TOTAL_HORIZON_SECONDS,
            "tick_duration_seconds": CORK_TICK_DURATION_SECONDS,
            "required_tick_count": TOTAL_HORIZON_TICKS,
            "drain_to_empty_required": False,
            "maximum_unique_od_pairs": DEFAULT_MAXIMUM_UNIQUE_OD_PAIRS,
            "same_physical_horizon_at_every_rung": True,
        },
        "network": network.status_payload(),
        "demand": demand.status_payload(),
        "routing": routes.status_payload(),
        "service_policy": {
            "policy": "gate_aware_fractional_service_v2",
            "uncontrolled_domains": "normal_uncontrolled_service",
            "signal_phases_fabricated": False,
            "v3_readiness_active": False,
            "evidence_mode": CITY_SCALE_V2_EVIDENCE_MODE,
            "city_scale_execution_summary": primary["city_scale_v2_summary"],
        },
        "primary": primary,
        "replay": replay,
        "phase_seconds": phase,
        "total_wall_clock_seconds": perf_counter() - total_wall_start,
        "total_cpu_seconds": process_time() - total_cpu_start,
        "peak_rss_bytes": _peak_rss_bytes(),
        "peak_python_memory_bytes": None,
        "peak_python_memory_status": "not_collected_to_avoid_tracemalloc_scale_distortion",
        "profile_output": str(profile_output) if profile_output is not None else None,
        "claim_boundary": (
            "computational_scalability_and_internal_state_only; horizon queue and "
            "occupancy measures are not calibrated Cork congestion claims"
        ),
    }


def _evolve_to_horizon(
    engine,  # type: ignore[no-untyped-def]
    loader: ScheduledDemandLoader,
    *,
    runtime_guard_seconds: float,
    wall_start: float,
) -> dict[str, Any]:
    blocked_reasons: Counter[str] = Counter()
    peak_queued = 0
    peak_pending = 0
    origin_blocked_packet_ticks = 0
    stop_reason: str | None = None
    while engine.current_tick < TOTAL_HORIZON_TICKS:
        loader.submit_due_departures(engine)
        engine.step()
        for trace in engine.allocation_traces():
            blocked_reasons.update(
                reason for _, reason in trace.rejected_transfer_reasons
            )
        queued = len(engine._queued_downstream_by_packet_id)
        pending = len(engine.pending_demands)
        peak_queued = max(peak_queued, queued)
        peak_pending = max(peak_pending, pending)
        origin_blocked_packet_ticks += pending
        if engine.current_tick % 100 == 0 and perf_counter() - wall_start > runtime_guard_seconds:
            stop_reason = (
                f"runtime_guard_seconds:{runtime_guard_seconds}:"
                f"tick:{engine.current_tick}:required:{TOTAL_HORIZON_TICKS}"
            )
            break
    return {
        "ticks_executed": engine.current_tick,
        "required_ticks": TOTAL_HORIZON_TICKS,
        "full_horizon_executed": engine.current_tick == TOTAL_HORIZON_TICKS,
        "stop_reason": stop_reason,
        "peak_queued_packet_count": peak_queued,
        "peak_pending_origin_admission_count": peak_pending,
        "origin_admission_blocked_packet_ticks": origin_blocked_packet_ticks,
        "rejected_transfer_requests_by_reason": dict(sorted(blocked_reasons.items())),
        "fifo_blocked_packet_ticks": blocked_reasons[REJECTED_UPSTREAM_FIFO],
        "receiving_storage_blocked_packet_ticks": blocked_reasons[
            REJECTED_DOWNSTREAM_SUPPLY
        ],
        "block_count_definition": (
            "cumulative rejected packet-transfer opportunities across ticks; "
            "a persistently blocked packet can contribute on multiple ticks"
        ),
        "origin_block_definition": (
            "sum of still-pending origin admissions after each executed tick"
        ),
    }


def _validate_horizon_state(
    engine,  # type: ignore[no-untyped-def]
    loader: ScheduledDemandLoader,
    resolved_manifest,
    network: CorkCanonicalNetwork,
    *,
    requested_packet_count: int,
    require_full_horizon: bool,
) -> dict[str, Any]:
    events = engine.event_log
    if any(event.sequence_number != index for index, event in enumerate(events)):
        raise CorkExperimentFailure("canonical event sequence ordering invalid")
    if any(a.physical_tick > b.physical_tick for a, b in zip(events, events[1:])):
        raise CorkExperimentFailure("canonical physical tick ordering invalid")
    if any(event.physical_tick > engine.current_tick for event in events):
        raise CorkExperimentFailure("event lies beyond executed physical horizon")

    lifecycle = engine._lifecycle_states_implied_by_events()
    if len(lifecycle) != len(engine.packets):
        raise CorkExperimentFailure("admitted packet lifecycle conservation mismatch")
    allowed = {
        LifecycleState.IN_TRANSIT,
        LifecycleState.QUEUED,
        LifecycleState.COMPLETED,
        LifecycleState.CANCELLED,
    }
    if set(lifecycle.values()) - allowed:
        raise CorkExperimentFailure("unresolved lifecycle state at horizon")

    event_counts: dict[str, Counter[EventType]] = {}
    for event in events:
        event_counts.setdefault(event.packet_id, Counter())[event.event_type] += 1
    for packet_id, state in lifecycle.items():
        counts = event_counts[packet_id]
        if counts[EventType.INSTANTIATED] != 1:
            raise CorkExperimentFailure(f"instantiation count mismatch: {packet_id}")
        if counts[EventType.COMPLETED] != (state == LifecycleState.COMPLETED):
            raise CorkExperimentFailure(f"completion count mismatch: {packet_id}")
        if counts[EventType.CANCELLED] != (state == LifecycleState.CANCELLED):
            raise CorkExperimentFailure(f"cancellation count mismatch: {packet_id}")
        active = state in (LifecycleState.IN_TRANSIT, LifecycleState.QUEUED)
        if counts[EventType.LINK_ENTRY] != counts[EventType.LINK_EXIT] + int(active):
            raise CorkExperimentFailure(f"link boundary count mismatch: {packet_id}")

    engine._check_live_queue_membership_consistent()
    queued_states = {
        packet_id
        for packet_id, state in lifecycle.items()
        if state == LifecycleState.QUEUED
    }
    if queued_states != set(engine._queued_downstream_by_packet_id):
        raise CorkExperimentFailure("queued lifecycle and live queue membership differ")

    for resolved in resolved_manifest.resolved_routes:
        resolved.route.validate_for_topology(network.topology)

    submitted = len(loader.submitted_loading_demand_ids)
    admitted = len(engine.packets)
    pending = len(engine.pending_demands)
    completed = sum(state == LifecycleState.COMPLETED for state in lifecycle.values())
    cancelled = sum(state == LifecycleState.CANCELLED for state in lifecycle.values())
    active = sum(
        state in (LifecycleState.IN_TRANSIT, LifecycleState.QUEUED)
        for state in lifecycle.values()
    )
    if admitted != completed + active + cancelled:
        raise CorkExperimentFailure("admitted packet conservation ledger does not close")
    if submitted != admitted + pending:
        raise CorkExperimentFailure("submitted demand conservation ledger does not close")
    if require_full_horizon and submitted != requested_packet_count:
        raise CorkExperimentFailure("not all scheduled departures submitted by horizon")
    if require_full_horizon and engine.current_tick != TOTAL_HORIZON_TICKS:
        raise CorkExperimentFailure("full fixed horizon was not executed")
    if require_full_horizon and requested_packet_count != pending + admitted:
        raise CorkExperimentFailure("requested demand conservation ledger does not close")

    return {
        "status": "passed",
        "exact_conservation": True,
        "valid_lifecycle_accounting": True,
        "canonical_event_ordering_valid": True,
        "stale_queue_membership_count": 0,
        "invalid_route_count": 0,
        "requested_packet_count": requested_packet_count,
        "submitted_packet_count": submitted,
        "admitted_packet_count": admitted,
        "pending_origin_admission_count": pending,
        "active_or_queued_packet_count": active,
        "completed_packet_count": completed,
        "cancelled_packet_count": cancelled,
        "full_horizon_executed": engine.current_tick == TOTAL_HORIZON_TICKS,
    }


def _horizon_state_summary(
    engine,  # type: ignore[no-untyped-def]
    loader: ScheduledDemandLoader,
    *,
    requested_packet_count: int,
    evolution: dict[str, Any],
) -> dict[str, Any]:
    lifecycle = engine._lifecycle_states_implied_by_events()
    completed = sum(state == LifecycleState.COMPLETED for state in lifecycle.values())
    cancelled = sum(state == LifecycleState.CANCELLED for state in lifecycle.values())
    queued = sum(state == LifecycleState.QUEUED for state in lifecycle.values())
    in_transit = sum(state == LifecycleState.IN_TRANSIT for state in lifecycle.values())
    admitted = len(lifecycle)
    pending = len(engine.pending_demands)
    unsubmitted = requested_packet_count - len(loader.submitted_loading_demand_ids)
    return {
        "physical_tick": engine.current_tick,
        "requested_packet_count": requested_packet_count,
        "submitted_packet_count": len(loader.submitted_loading_demand_ids),
        "unsubmitted_scheduled_packet_count": unsubmitted,
        "admitted_packet_count": admitted,
        "pending_origin_admission_count": pending,
        "active_or_queued_packet_count": in_transit + queued,
        "in_transit_packet_count": in_transit,
        "queued_packet_count": queued,
        "completed_packet_count": completed,
        "cancelled_packet_count": cancelled,
        "admission_fraction": admitted / requested_packet_count,
        "completion_fraction": completed / requested_packet_count,
        "completion_fraction_of_admitted": completed / admitted if admitted else 0.0,
        "non_empty_link_count": len(engine._occupied_link_ids),
        "non_empty_queue_count": sum(bool(queue) for queue in engine._queues.values()),
        "total_queued_packets": len(engine._queued_downstream_by_packet_id),
        "peak_queued_packets": evolution["peak_queued_packet_count"],
        "peak_pending_origin_admission": evolution[
            "peak_pending_origin_admission_count"
        ],
        "fifo_block_count": evolution["fifo_blocked_packet_ticks"],
        "receiving_storage_block_count": evolution[
            "receiving_storage_blocked_packet_ticks"
        ],
        "origin_admission_blocking_packet_ticks": evolution[
            "origin_admission_blocked_packet_ticks"
        ],
        "total_physical_storage_occupancy_packets": sum(
            engine._current_link_storage_by_link_id.values()
        ),
        "rejected_transfer_requests_by_reason": evolution[
            "rejected_transfer_requests_by_reason"
        ],
        "block_count_definition": evolution["block_count_definition"],
        "origin_block_definition": evolution["origin_block_definition"],
    }


def _primary_summary(
    *,
    engine,  # type: ignore[no-untyped-def]
    packet_count: int,
    event_identity: dict[str, Any],
    horizon_state: dict[str, Any],
    horizon_state_hash: str,
    phase: dict[str, float],
    routes,
    demand,
    validation: dict[str, Any],
    evolution_wall: float,
    evolution_cpu: float,
    evolution: dict[str, Any],
) -> dict[str, Any]:
    route_links = routes.route_link_counts
    route_times = routes.route_free_flow_times_seconds
    admitted = horizon_state["admitted_packet_count"]
    completed = horizon_state["completed_packet_count"]
    return {
        "run_status": (
            "fixed_horizon_complete"
            if evolution["full_horizon_executed"]
            else "runtime_guard_before_fixed_horizon"
        ),
        "stop_reason": evolution["stop_reason"],
        "requested_packet_count": packet_count,
        "admitted_by_horizon": admitted,
        "completed_by_horizon": completed,
        "active_or_queued_by_horizon": horizon_state[
            "active_or_queued_packet_count"
        ],
        "pending_origin_admission_by_horizon": horizon_state[
            "pending_origin_admission_count"
        ],
        "cancelled_by_horizon": horizon_state["cancelled_packet_count"],
        "admission_fraction": horizon_state["admission_fraction"],
        "completion_fraction": horizon_state["completion_fraction"],
        "completion_fraction_of_admitted": horizon_state[
            "completion_fraction_of_admitted"
        ],
        "unique_od_count": demand.unique_od_count,
        "canonical_event_count": event_identity["event_count"],
        "events_per_admitted_packet": (
            event_identity["event_count"] / admitted if admitted else 0.0
        ),
        "event_stream_sha256": event_identity["event_stream_sha256"],
        "event_serialized_bytes": event_identity["serialized_bytes"],
        "event_serialized_bytes_per_admitted_packet": (
            event_identity["serialized_bytes"] / admitted if admitted else 0.0
        ),
        "horizon_state_hash": horizon_state_hash,
        "ticks_executed": engine.current_tick,
        "required_ticks": TOTAL_HORIZON_TICKS,
        "simulated_duration_seconds": engine.current_tick * CORK_TICK_DURATION_SECONDS,
        "simulated_loading_duration_seconds": demand.loading_window_seconds,
        "post_loading_observation_seconds": POST_LOADING_OBSERVATION_SECONDS,
        "loading_and_evolution_wall_seconds": evolution_wall,
        "loading_and_evolution_cpu_seconds": evolution_cpu,
        "admitted_packets_per_wall_second": admitted / evolution_wall,
        "completed_packets_per_wall_second": completed / evolution_wall,
        "events_per_wall_second": event_identity["event_count"] / evolution_wall,
        "mean_route_links": sum(route_links) / len(route_links),
        "median_route_links": _median(route_links),
        "mean_route_free_flow_time_seconds": sum(route_times) / len(route_times),
        "median_route_free_flow_time_seconds": _median(route_times),
        "horizon_traffic_state": horizon_state,
        "validation": validation,
        "active_work_frontier": dict(engine.active_work_frontier_metrics),
        "city_scale_v2_summary": asdict(engine.city_scale_v2_summary),
        "phase_seconds": dict(phase),
    }


def _fixed_horizon_replay_policy(
    *, packet_count: int, run_replay: bool | None, primary: dict[str, Any]
) -> dict[str, Any]:
    if run_replay is not None:
        execute = run_replay
        reason = "explicit_runner_override"
    elif packet_count <= MANDATORY_REPLAY_PACKET_LIMIT:
        execute = True
        reason = "mandatory_exact_replay_at_or_below_1000_packets"
    elif packet_count == OPTIONAL_REPLAY_PACKET_COUNT:
        execute = (
            primary["loading_and_evolution_wall_seconds"] <= 90.0
            and primary["event_serialized_bytes"] <= 256 * 1024 * 1024
            and _peak_rss_bytes() <= 2 * 1024 * 1024 * 1024
        )
        reason = (
            "2500_exact_replay_cost_guard_passed"
            if execute
            else "2500_replay_skipped_by_explicit_runtime_memory_evidence_guard"
        )
    else:
        execute = False
        reason = "replay_not_requested_above_2500_packets"
    return {
        "execute": execute,
        "reason": reason,
        "mandatory_packet_limit": MANDATORY_REPLAY_PACKET_LIMIT,
        "optional_2500_cost_guards": {
            "primary_runtime_seconds_max": 90.0,
            "serialized_event_bytes_max": 256 * 1024 * 1024,
            "peak_rss_bytes_max": 2 * 1024 * 1024 * 1024,
        },
    }
