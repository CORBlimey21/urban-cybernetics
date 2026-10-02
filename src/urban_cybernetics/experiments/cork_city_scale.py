# SPDX-License-Identifier: MPL-2.0
"""Instrumented first-pass physical loading experiment on full Cork topology."""

from __future__ import annotations

import cProfile
import gc
import hashlib
import json
import os
import resource
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from time import perf_counter, process_time
from typing import Any

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import Event, EventType, LifecycleState
from urban_cybernetics.demand.cork_synthetic import (
    DEFAULT_CORK_DEMAND_SEED,
    build_cork_synthetic_demand,
    resolve_cork_weighted_routes,
)
from urban_cybernetics.demand.scheduled_loading import ScheduledDemandLoader
from urban_cybernetics.extensions.city_scale_v2 import (
    CITY_SCALE_V2_EVIDENCE_MODE,
    CityScaleSummaryMovementAllocator,
    CityScaleV2LoadingEngine,
)
from urban_cybernetics.extensions.gate_aware_fractional_service import (
    GateAwareFractionalServiceConfig,
)
from urban_cybernetics.topology.cork import (
    CORK_TICK_DURATION_SECONDS,
    CorkCanonicalNetwork,
    load_cork_canonical_network,
)


CORK_EXPERIMENT_VERSION = "uc.cork-city-scale-physical-loading.v1"
DEFAULT_TICK_LIMIT = 75_000
DEFAULT_RUNTIME_GUARD_SECONDS = 600.0
DEFAULT_REPLAY_PACKET_LIMIT = 1_000


class CorkExperimentFailure(RuntimeError):
    pass


def run_cork_scale_rung(
    packet_count: int,
    *,
    graph_path: Path | None = None,
    seed: int = DEFAULT_CORK_DEMAND_SEED,
    tick_limit: int = DEFAULT_TICK_LIMIT,
    runtime_guard_seconds: float = DEFAULT_RUNTIME_GUARD_SECONDS,
    run_replay: bool | None = None,
    profile_output: Path | None = None,
) -> dict[str, Any]:
    """Execute one rung and return a JSON-ready reproducibility report."""

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
    load_wall_start = perf_counter()
    load_cpu_start = process_time()
    last_progress_wall = load_wall_start
    stop_reason: str | None = None
    while len(engine.completed_packet_ids) < packet_count:
        loader.submit_due_departures(engine)
        engine.step()
        if engine.current_tick >= tick_limit:
            stop_reason = (
                f"tick_limit:{tick_limit}:completed:"
                f"{len(engine.completed_packet_ids)}:requested:{packet_count}"
            )
            break
        now = perf_counter()
        if now - load_wall_start > runtime_guard_seconds:
            stop_reason = (
                f"runtime_guard_seconds:{runtime_guard_seconds}:tick:"
                f"{engine.current_tick}:completed:{len(engine.completed_packet_ids)}:"
                f"requested:{packet_count}"
            )
            break
        # Avoid calling the clock on every loop except for a cheap periodic gate.
        if engine.current_tick % 1_000 == 0:
            last_progress_wall = now
    del last_progress_wall
    load_wall = perf_counter() - load_wall_start
    load_cpu = process_time() - load_cpu_start
    if profiler is not None:
        profiler.disable()
        profile_output.parent.mkdir(parents=True, exist_ok=True)
        profiler.dump_stats(profile_output)
    phase["physical_loading_wall_seconds"] = load_wall
    phase["physical_loading_cpu_seconds"] = load_cpu

    started = perf_counter()
    engine.materialize_all_receiving_credit()
    validation = _validate_run_state(
        engine,
        routes.resolved_manifest,
        network.topology,
        require_complete=stop_reason is None,
    )
    phase["validation_seconds"] = perf_counter() - started

    started = perf_counter()
    event_identity = _event_stream_identity(engine.event_log)
    phase["event_serialization_and_hashing_seconds"] = perf_counter() - started

    primary = _primary_summary(
        engine,
        packet_count=packet_count,
        event_identity=event_identity,
        phase=phase,
        routes=routes,
        demand=demand,
        validation=validation,
        load_wall=load_wall,
        load_cpu=load_cpu,
        stop_reason=stop_reason,
        loader=loader,
    )
    replay_policy = _replay_policy(
        packet_count=packet_count,
        run_replay=run_replay,
        primary=primary,
    )
    replay: dict[str, Any]
    if replay_policy["execute"] and stop_reason is None:
        expected_event_hash = event_identity["event_stream_sha256"]
        del engine
        gc.collect()
        replay_started = perf_counter()
        replay_engine = _build_engine(network)
        replay_loader = ScheduledDemandLoader(routes.resolved_manifest)
        while len(replay_engine.completed_packet_ids) < packet_count:
            replay_loader.submit_due_departures(replay_engine)
            replay_engine.step()
            if replay_engine.current_tick >= tick_limit:
                raise CorkExperimentFailure("replay tick limit reached")
            if perf_counter() - replay_started > runtime_guard_seconds:
                raise CorkExperimentFailure("replay runtime guard reached")
        replay_engine.materialize_all_receiving_credit()
        replay_identity = _event_stream_identity(replay_engine.event_log)
        replay_seconds = perf_counter() - replay_started
        replay = {
            "status": (
                "passed_exact_replay"
                if replay_identity["event_stream_sha256"] == expected_event_hash
                else "failed_exact_replay_mismatch"
            ),
            "runtime_seconds": replay_seconds,
            "event_stream_sha256": replay_identity["event_stream_sha256"],
            "event_count": replay_identity["event_count"],
            "policy": replay_policy,
        }
    else:
        replay = {
            "status": (
                "skipped_incomplete_bounded_run"
                if stop_reason is not None
                else "skipped_by_explicit_cost_policy"
            ),
            "runtime_seconds": None,
            "event_stream_sha256": None,
            "event_count": None,
            "policy": replay_policy,
        }

    run_identity = _stable_hash(
        "cork-city-scale-run",
        {
            "experiment_version": CORK_EXPERIMENT_VERSION,
            "topology_hash": network.topology_hash,
            "physical_profile_hash": network.physical_profile_hash,
            "manifest_hash": demand.manifest.manifest_hash,
            "route_resolution_hash": routes.route_resolution_hash,
            "event_stream_sha256": event_identity["event_stream_sha256"],
            "packet_count": packet_count,
            "seed": seed,
        },
    )
    return {
        "experiment_version": CORK_EXPERIMENT_VERSION,
        "run_identity_hash": run_identity,
        "packet_count": packet_count,
        "seed": seed,
        "process_id": os.getpid(),
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
            "scalability_and_internal_correctness_only; no calibrated Cork "
            "operations or empirical traffic claim"
        ),
    }


def _build_engine(network: CorkCanonicalNetwork) -> CityScaleV2LoadingEngine:
    nodes = network.topology.as_loading_nodes()
    rates = network.capacity_rates_by_link()
    return CityScaleV2LoadingEngine(
        links=network.as_loading_links(),
        nodes=nodes,
        node_transfer_policy=CityScaleSummaryMovementAllocator(nodes),
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        gate_aware_fractional_service_config=GateAwareFractionalServiceConfig(
            tuple(rates.items())
        ),
        executable_semantic_hash=network.physical_profile_hash,
        use_active_work_frontier=True,
    )


def _validate_run_state(
    engine, resolved_manifest, topology, *, require_complete: bool
) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    events = engine.event_log
    if any(event.sequence_number != index for index, event in enumerate(events)):
        raise CorkExperimentFailure("canonical event sequence ordering invalid")
    if any(a.physical_tick > b.physical_tick for a, b in zip(events, events[1:])):
        raise CorkExperimentFailure("canonical physical tick ordering invalid")
    lifecycle = engine._lifecycle_states_implied_by_events()
    if require_complete and any(
        state != LifecycleState.COMPLETED for state in lifecycle.values()
    ):
        raise CorkExperimentFailure("unresolved packet lifecycle state remains")
    packet_count = len(engine.packets)
    if len(lifecycle) != packet_count:
        raise CorkExperimentFailure("packet conservation mismatch")
    event_types_by_packet: dict[str, Counter[EventType]] = {}
    for event in events:
        event_types_by_packet.setdefault(event.packet_id, Counter())[event.event_type] += 1
    for packet_id, counts in event_types_by_packet.items():
        if counts[EventType.INSTANTIATED] != 1:
            raise CorkExperimentFailure(f"terminal lifecycle count mismatch: {packet_id}")
        if require_complete and counts[EventType.COMPLETED] != 1:
            raise CorkExperimentFailure(f"terminal lifecycle count mismatch: {packet_id}")
        if counts[EventType.LINK_ENTRY] != counts[EventType.LINK_EXIT]:
            if lifecycle[packet_id] == LifecycleState.COMPLETED:
                raise CorkExperimentFailure(
                    f"link boundary conservation mismatch: {packet_id}"
                )
            if counts[EventType.LINK_ENTRY] != counts[EventType.LINK_EXIT] + 1:
                raise CorkExperimentFailure(
                    f"active link boundary conservation mismatch: {packet_id}"
                )
    engine._check_live_queue_membership_consistent()
    if require_complete and (
        any(engine._queues.values())
        or engine._queue_entry_metadata_by_packet_id
        or engine._queued_downstream_by_packet_id
    ):
        raise CorkExperimentFailure("stale queue state remains after completion")
    for resolved in resolved_manifest.resolved_routes:
        resolved.route.validate_for_topology(topology)
    completed = len(engine.completed_packet_ids)
    in_flight = sum(
        state in (LifecycleState.IN_TRANSIT, LifecycleState.QUEUED)
        for state in lifecycle.values()
    )
    cancelled = len(engine._cancelled_packet_ids)
    if packet_count != completed + in_flight + cancelled:
        raise CorkExperimentFailure("exact conservation ledger does not close")
    return {
        "status": "passed",
        "exact_conservation": True,
        "unresolved_lifecycle_state_count": 0,
        "all_admitted_packets_completed": in_flight == 0,
        "all_admitted_packets_explicitly_accounted": True,
        "canonical_event_ordering_valid": True,
        "stale_queue_membership_count": 0,
        "invalid_route_count": 0,
        "instantiated_packet_count": packet_count,
        "completed_packet_count": completed,
        "in_flight_packet_count": in_flight,
        "cancelled_packet_count": cancelled,
    }


def _primary_summary(
    engine,
    *,
    packet_count: int,
    event_identity: dict[str, Any],
    phase: dict[str, float],
    routes,
    demand,
    validation: dict[str, Any],
    load_wall: float,
    load_cpu: float,
    stop_reason: str | None,
    loader,
) -> dict[str, Any]:
    completion_tick = engine.current_tick
    loading_end_tick = demand.loading_window_end_tick
    drain_ticks = max(completion_tick - loading_end_tick, 0)
    route_links = routes.route_link_counts
    route_times = routes.route_free_flow_times_seconds
    frontier = dict(engine.active_work_frontier_metrics)
    summary = asdict(engine.city_scale_v2_summary)
    completed_count = len(engine.completed_packet_ids)
    instantiated_count = len(engine.packets)
    pending_count = len(engine.pending_demands)
    completed_ticks = [
        event.physical_tick
        for event in engine.event_log
        if event.event_type == EventType.COMPLETED
    ]
    return {
        "requested_packet_count": packet_count,
        "submitted_packet_count": len(loader.submitted_loading_demand_ids),
        "instantiated_packet_count": instantiated_count,
        "pending_origin_admission_count": pending_count,
        "completed_packet_count": completed_count,
        "unresolved_packet_count": 0,
        "active_in_flight_packet_count": instantiated_count - completed_count,
        "all_requested_packets_explicitly_accounted": (
            packet_count == instantiated_count + pending_count
        ),
        "run_status": "completed" if stop_reason is None else "bounded_stop",
        "stop_reason": stop_reason,
        "unique_od_count": demand.unique_od_count,
        "canonical_event_count": event_identity["event_count"],
        "events_per_packet": event_identity["event_count"] / packet_count,
        "events_per_instantiated_packet": (
            event_identity["event_count"] / instantiated_count
        ),
        "event_stream_sha256": event_identity["event_stream_sha256"],
        "event_serialized_bytes": event_identity["serialized_bytes"],
        "event_serialized_bytes_per_packet": event_identity["serialized_bytes"] / packet_count,
        "mean_route_links": sum(route_links) / len(route_links),
        "median_route_links": _median(route_links),
        "mean_route_free_flow_time_seconds": sum(route_times) / len(route_times),
        "median_route_free_flow_time_seconds": _median(route_times),
        "simulated_loading_duration_seconds": demand.loading_window_seconds,
        "loading_window_end_tick": loading_end_tick,
        "final_completion_tick": completion_tick,
        "last_completed_packet_tick": max(completed_ticks, default=None),
        "bounded_stop_tick": completion_tick if stop_reason is not None else None,
        "final_completion_time_seconds": completion_tick * CORK_TICK_DURATION_SECONDS,
        "drain_ticks": drain_ticks,
        "drain_duration_seconds": drain_ticks * CORK_TICK_DURATION_SECONDS,
        "physical_loading_wall_seconds": load_wall,
        "physical_loading_cpu_seconds": load_cpu,
        "packets_per_second": completed_count / load_wall,
        "requested_packets_per_second": packet_count / load_wall,
        "events_per_second": event_identity["event_count"] / load_wall,
        "validation": validation,
        "active_work_frontier": frontier,
        "city_scale_v2_summary": summary,
        "phase_seconds": dict(phase),
    }


def _event_stream_identity(events: tuple[Event, ...]) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    for event in events:
        payload = {
            "sequence_number": event.sequence_number,
            "packet_id": event.packet_id,
            "event_type": event.event_type.value,
            "entity_id": event.entity_id,
            "physical_tick": event.physical_tick,
        }
        encoded = (
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        digest.update(encoded)
        size += len(encoded)
    return {
        "event_count": len(events),
        "serialized_bytes": size,
        "event_stream_sha256": digest.hexdigest(),
    }


def _replay_policy(
    *, packet_count: int, run_replay: bool | None, primary: dict[str, Any]
) -> dict[str, Any]:
    if run_replay is not None:
        execute = run_replay
        reason = "explicit_runner_override"
    elif packet_count <= DEFAULT_REPLAY_PACKET_LIMIT:
        execute = True
        reason = "mandatory_exact_replay_at_or_below_1000_packets"
    else:
        cheap = (
            primary["physical_loading_wall_seconds"] <= 60.0
            and primary["event_serialized_bytes"] <= 256 * 1024 * 1024
            and _peak_rss_bytes() <= 2 * 1024 * 1024 * 1024
        )
        execute = cheap
        reason = (
            "10000_replay_cost_guard_passed"
            if cheap
            else "10000_replay_skipped_when_runtime_gt_60s_or_events_gt_256MiB_or_rss_gt_2GiB"
        )
    return {
        "execute": execute,
        "reason": reason,
        "mandatory_packet_limit": DEFAULT_REPLAY_PACKET_LIMIT,
        "ten_thousand_cost_guards": {
            "primary_runtime_seconds_max": 60.0,
            "serialized_event_bytes_max": 256 * 1024 * 1024,
            "peak_rss_bytes_max": 2 * 1024 * 1024 * 1024,
        },
    }


def _median(values: tuple[float | int, ...]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return float(
        ordered[middle]
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / 2
    )


def _peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # macOS reports bytes, Linux reports KiB.
    return value if os.uname().sysname == "Darwin" else value * 1024


def _stable_hash(domain: str, payload: object) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": payload},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
