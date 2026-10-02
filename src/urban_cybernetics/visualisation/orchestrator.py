# SPDX-License-Identifier: MPL-2.0
"""Python-owned local V2 run orchestration outside the loading kernel."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
import uuid
from pathlib import Path
from threading import Condition, RLock, Thread

from urban_cybernetics.canonical_validation import build_sioux_falls_uc_default_physical_profile
from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID, LEGACY_LOADING_PROFILE_ID
from urban_cybernetics.core import DemandDeclaration, Event, EventType, LifecycleState, Link
from urban_cybernetics.demand import FixedDepartureSchedule, ScheduledDemandLoader, load_sioux_falls_demand_manifest, resolve_demand_routes
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.validation import ValidationContext

from .catalogue import SIOUX_TOPOLOGY_ID, SYNTHETIC_TOPOLOGY_ID, ResolvedResources, resolve_resources
from .contract import RunStatus, VCanonicalEvent
from .export import build_run_bundle, packet_records, topology_record
from .lifecycle import IllegalLifecycleTransition, RunLifecycle
from .persistence import ArtifactRepository, event_payload_sha256, utc_now
from .replay import build_replay_states
from .v2_contract import (
    EventChunk, FrozenRunRequest, LiveMessage, LiveMessageType,
    MovementAllocationEvidence, MovementFlowEvidence, ReplayCheckpoint,
    ResolutionRecord, RunArtifactSummary, RunCommand, RunCommandAcknowledgement,
    RunCommandAction, RunCountsV2, RunLifecycleState, RunRequestV2,
)


TERMINAL_STATES = frozenset({RunLifecycleState.COMPLETE, RunLifecycleState.CANCELLED, RunLifecycleState.TIMED_OUT, RunLifecycleState.FAILED})


class RunNotActive(KeyError):
    pass


class _Runtime:
    def __init__(self, frozen: FrozenRunRequest, resolved: ResolvedResources, summary: RunArtifactSummary) -> None:
        self.frozen = frozen
        self.resolved = resolved
        self.summary = summary
        self.lifecycle = RunLifecycle()
        self.condition = Condition(RLock())
        self.command_acks: dict[str, RunCommandAcknowledgement] = {}
        self.message_id = 0
        self.thread: Thread | None = None
        self.engine: LoadingEngine | None = None


class RunOrchestrator:
    """Executes only declared resources and persists every sealed evidence boundary."""

    def __init__(self, repository: ArtifactRepository, *, execution_yield_seconds: float = 0.0, checkpoint_interval_ticks: int = 10) -> None:
        self.repository = repository
        self.execution_yield_seconds = execution_yield_seconds
        self.checkpoint_interval_ticks = checkpoint_interval_ticks
        self._lock = RLock()
        self._runtimes: dict[str, _Runtime] = {}

    def create_run(self, request: RunRequestV2, *, _fixture_run_id: str | None = None) -> RunArtifactSummary:
        resolved = resolve_resources(request)
        run_id = _fixture_run_id or f"v2-{uuid.uuid4().hex}"
        created = utc_now()
        frozen = FrozenRunRequest(
            run_id=run_id, request=request, created_at=created,
            resolved_topology_hash=resolved.topology_hash,
            resolved_profile_hash=resolved.profile_hash,
            resolved_demand_hash=resolved.demand_hash,
            resolved_tick_duration_seconds=resolved.tick_duration_seconds,
            code_commit=_code_commit(), seed_registry={"demand_selection": request.seed, "engine": request.seed},
            resolution_records=(ResolutionRecord(field="tick_duration_seconds", requested=request.requested_tick_duration_seconds, resolved=resolved.tick_duration_seconds, rule="exact declared policy default; no rounding"),),
        )
        summary = RunArtifactSummary(
            run_id=run_id, title=request.run_label or _default_title(request.topology_id), description=request.note or "Sanctioned browser-launched simulation.",
            contract_version="uc.visualisation.evidence.v2", topology_id=request.topology_id,
            topology_hash=resolved.topology_hash, physical_profile_id=request.physical_profile_id,
            profile_hash=resolved.profile_hash, demand_source_id=request.demand_source_id,
            demand_hash=resolved.demand_hash, seed=request.seed, status=RunLifecycleState.CREATED,
            stop_reason=None, created_at=created, updated_at=created, validation_status="pending",
            configuration_hash=_sha(request.model_dump(mode="json")), event_count=0, final_tick=0,
            counts=RunCountsV2(requested=request.requested_packet_count, instantiated=0, completed=0, unresolved=request.requested_packet_count, cancelled=0),
            assumption_warnings=resolved.assumption_warnings,
        )
        runtime = _Runtime(frozen, resolved, summary)
        self.repository.create(frozen, summary)
        self.repository.write_document(run_id, "topology.json", topology_record(resolved.topology).model_dump(mode="json"))
        with self._lock:
            self._runtimes[run_id] = runtime
        self._emit(runtime, LiveMessageType.LIFECYCLE, {"transition": runtime.lifecycle.history[-1].model_dump(mode="json")})
        runtime.thread = Thread(target=self._execute, args=(runtime,), name=f"uc-v2-{run_id}", daemon=True)
        runtime.thread.start()
        return summary

    def command(self, run_id: str, command: RunCommand) -> RunCommandAcknowledgement:
        runtime = self._runtime(run_id)
        with runtime.condition:
            existing = runtime.command_acks.get(command.command_id)
            if existing is not None:
                return existing.model_copy(update={"duplicate": True})
            target: RunLifecycleState
            if command.action == RunCommandAction.PAUSE:
                target = RunLifecycleState.PAUSE_REQUESTED
            elif command.action == RunCommandAction.RESUME:
                target = RunLifecycleState.RESUME_REQUESTED
            else:
                target = RunLifecycleState.CANCEL_REQUESTED
            try:
                self._transition(runtime, target, f"accepted {command.action.value} command {command.command_id}")
                accepted, detail = True, "command accepted; acknowledgement state is persisted"
            except IllegalLifecycleTransition as exc:
                accepted, detail = False, str(exc)
            acknowledgement = RunCommandAcknowledgement(command_id=command.command_id, action=command.action, accepted=accepted, duplicate=False, lifecycle_state=runtime.lifecycle.state, detail=detail)
            runtime.command_acks[command.command_id] = acknowledgement
            runtime.condition.notify_all()
            return acknowledgement

    def summary(self, run_id: str) -> RunArtifactSummary:
        return self.repository.get_summary(run_id)

    def wait(self, run_id: str, timeout: float | None = None) -> RunArtifactSummary:
        runtime = self._runtime(run_id)
        if runtime.thread is not None:
            runtime.thread.join(timeout)
        return self.repository.get_summary(run_id)

    def _runtime(self, run_id: str) -> _Runtime:
        with self._lock:
            try:
                return self._runtimes[run_id]
            except KeyError as exc:
                raise RunNotActive(run_id) from exc

    def _execute(self, runtime: _Runtime) -> None:
        started = time.perf_counter()
        request = runtime.frozen.request
        loader: ScheduledDemandLoader | None = None
        declarations: tuple[DemandDeclaration, ...] = ()
        try:
            self._transition(runtime, RunLifecycleState.RESOLVING, "declared resource IDs resolved")
            self._transition(runtime, RunLifecycleState.SETTING_UP, "constructing sanctioned Python engine")
            engine, loader, declarations = self._build_engine(runtime)
            runtime.engine = engine
            self._emit(runtime, LiveMessageType.SETUP, {"stage": "engine_ready", "topology_hash": runtime.resolved.topology_hash})
            if runtime.lifecycle.state == RunLifecycleState.CANCEL_REQUESTED:
                self._finalise(runtime, engine, started, cancelled=True)
                return
            self._transition(runtime, RunLifecycleState.RUNNING, "engine setup complete")
            if loader is not None:
                loader.submit_due_departures(engine)
            else:
                for declaration in declarations:
                    engine.instantiate(declaration)
            event_offset = 0
            chunk_index = 0
            if engine.event_log:
                initial_chunk = _event_chunk(runtime.frozen.run_id, chunk_index, engine.event_log)
                self.repository.append_event_chunk(initial_chunk)
                event_offset = initial_chunk.end_sequence + 1
                chunk_index += 1
                self._emit(runtime, LiveMessageType.EVENT_RANGE, {"start_sequence": initial_chunk.start_sequence, "end_sequence": initial_chunk.end_sequence, "tick": engine.current_tick})
            checkpoint_index = 0
            while True:
                with runtime.condition:
                    if runtime.lifecycle.state == RunLifecycleState.PAUSE_REQUESTED:
                        self._transition(runtime, RunLifecycleState.PAUSED, "engine paused at safe between-tick boundary")
                    while runtime.lifecycle.state == RunLifecycleState.PAUSED:
                        runtime.condition.wait(timeout=0.25)
                    if runtime.lifecycle.state == RunLifecycleState.RESUME_REQUESTED:
                        self._transition(runtime, RunLifecycleState.RUNNING, "engine resume acknowledged at safe boundary")
                    if runtime.lifecycle.state == RunLifecycleState.CANCEL_REQUESTED:
                        self._finalise(runtime, engine, started, cancelled=True)
                        return
                requested_count = request.requested_packet_count
                submitted = (len(loader.submitted_loading_demand_ids) if loader is not None else len(declarations))
                if len(engine.completed_packet_ids) == requested_count and submitted == requested_count:
                    break
                if engine.current_tick >= request.tick_limit or time.perf_counter() - started >= request.runtime_limit_seconds:
                    self._finalise(runtime, engine, started, timed_out=True)
                    return
                before = len(engine.event_log)
                engine.step()
                if loader is not None:
                    loader.submit_due_departures(engine)
                new_events = engine.event_log[before:]
                if new_events:
                    chunk = _event_chunk(runtime.frozen.run_id, chunk_index, new_events)
                    self.repository.append_event_chunk(chunk)
                    event_offset = chunk.end_sequence + 1
                    chunk_index += 1
                    self._emit(runtime, LiveMessageType.EVENT_RANGE, {"start_sequence": chunk.start_sequence, "end_sequence": chunk.end_sequence, "tick": engine.current_tick})
                self._persist_movements(runtime, engine, new_events)
                self.repository.write_document(runtime.frozen.run_id, "packets.json", [packet.model_dump(mode="json") for packet in packet_records(engine.packets, runtime.resolved.topology, {})])
                if engine.current_tick % self.checkpoint_interval_ticks == 0:
                    checkpoint = self._checkpoint(runtime, engine, checkpoint_index)
                    self.repository.append_checkpoint(checkpoint)
                    checkpoint_index += 1
                    self._emit(runtime, LiveMessageType.CHECKPOINT, {"tick": engine.current_tick, "applied_through_sequence": checkpoint.state.applied_through_sequence})
                self._update_summary(runtime, engine, validation_status="pending")
                self._emit(runtime, LiveMessageType.TICK_SEALED, self._progress_payload(engine, requested_count, started, event_offset))
                if self.execution_yield_seconds:
                    time.sleep(self.execution_yield_seconds)
            self._finalise(runtime, engine, started)
        except Exception as exc:
            self._fail(runtime, exc)

    def _build_engine(self, runtime: _Runtime) -> tuple[LoadingEngine, ScheduledDemandLoader | None, tuple[DemandDeclaration, ...]]:
        request = runtime.frozen.request
        topology = runtime.resolved.topology
        if request.topology_id == SYNTHETIC_TOPOLOGY_ID:
            links = {item.link_id: Link(link_id=item.link_id, free_flow_ticks=1, declared_sending_capacity_per_tick=1, declared_receiving_capacity_per_tick=1, declared_storage_capacity_packets=max(8, request.requested_packet_count), tick_duration_seconds=1.0) for item in topology.links}
            engine = LoadingEngine(links=links, nodes=topology.as_loading_nodes(), model_profile_id=LEGACY_LOADING_PROFILE_ID)
            routes = (("L0", "L1", "L3"), ("L0", "L2", "L4"))
            declarations = tuple(DemandDeclaration(f"v2-synthetic-{index:06d}", departure_tick=index // 2, route_intent=routes[index % 2]) for index in range(request.requested_packet_count))
            return engine, None, declarations
        if request.topology_id == SIOUX_TOPOLOGY_ID:
            profile = build_sioux_falls_uc_default_physical_profile(topology=topology)
            manifest = load_sioux_falls_demand_manifest(topology=topology, scale_factor=0.01, max_total_quantity_packets=request.requested_packet_count, departure_schedule=FixedDepartureSchedule(departure_tick=0))
            resolved_manifest = resolve_demand_routes(manifest, topology)
            loader = ScheduledDemandLoader(resolved_manifest)
            if len(loader.scheduled_requests) != request.requested_packet_count:
                raise RuntimeError(f"declared packet selection resolved {len(loader.scheduled_requests)} packets, expected {request.requested_packet_count}")
            links = profile.as_loading_links(tick_duration_seconds=runtime.resolved.tick_duration_seconds)
            rates = profile.parity_capacity_rates_by_link(tick_duration_seconds=runtime.resolved.tick_duration_seconds)
            engine = LoadingEngine(links=links, nodes=topology.as_loading_nodes(), model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID, parity_sending_capacity_vehicles_per_tick_by_link=rates, parity_receiving_capacity_vehicles_per_tick_by_link=rates, use_active_work_frontier=True)
            return engine, loader, ()
        raise RuntimeError("undeclared topology")

    def _checkpoint(self, runtime: _Runtime, engine: LoadingEngine, index: int) -> ReplayCheckpoint:
        packets = packet_records(engine.packets, runtime.resolved.topology, {})
        state = build_replay_states(events=engine.event_log, packets=packets, link_ids=engine.links, start_tick=0, end_tick=engine.current_tick)[-1]
        return ReplayCheckpoint(run_id=runtime.frozen.run_id, checkpoint_index=index, state=state, source_event_sha256=event_payload_sha256(tuple(_event_dict(event) for event in engine.event_log)))

    def _persist_movements(self, runtime: _Runtime, engine: LoadingEngine, new_events: tuple[Event, ...]) -> None:
        event_sequences = tuple(event.sequence_number for event in new_events if event.event_type in {EventType.LINK_EXIT, EventType.LINK_ENTRY})
        specs = {movement.movement_id: movement for node in runtime.resolved.topology.nodes for movement in node.junction_spec().movement_specs}
        for trace in engine.allocation_traces():
            rejected = dict(trace.rejected_transfer_reasons)
            receiving = dict(trace.receiving_slots_by_downstream_link)
            lane = dict(trace.lane_group_capacity_by_id)
            conflict = dict(trace.conflict_resource_capacity_by_id)
            flows: list[MovementFlowEvidence] = []
            for summary in trace.movement_flow_summaries:
                spec = specs.get(summary.movement_id)
                if spec is None:
                    continue
                approved = tuple(packet_id for packet_id in trace.approved_packet_ids if _packet_transfer_matches(packet_id, spec.upstream_link_id, spec.downstream_link_id, new_events))
                candidates = tuple(packet_id for packet_id in trace.candidate_packet_ids if _route_contains_movement(engine.packets[packet_id].route_intent, spec.upstream_link_id, spec.downstream_link_id))
                flows.append(MovementFlowEvidence(movement_id=summary.movement_id, upstream_link_id=summary.upstream_link_id, downstream_link_id=summary.downstream_link_id, request_packet_ids=candidates, upstream_fifo_packet_ids=candidates, approved_packet_ids=approved, rejected_packet_reasons=tuple((packet_id, rejected[packet_id]) for packet_id in candidates if packet_id in rejected), receiving_supply_packets=receiving.get(summary.downstream_link_id), movement_capacity_packets=None, lane_group_constraints={key: value for key, value in lane.items() if key in spec.lane_group_ids}, conflict_resource_constraints={key: value for key, value in conflict.items() if key in spec.conflict_resource_ids}, signal_state="not_declared" if spec.signal_group_id is None else "open" if spec.signal_group_id in trace.open_signal_group_ids else "closed", governance_state="closed" if summary.movement_id in trace.closed_movement_ids else "open", resulting_canonical_event_sequences=tuple(sequence for sequence in event_sequences if any(event.sequence_number == sequence and event.packet_id in approved for event in new_events))))
            if flows:
                self.repository.append_movement_evidence(MovementAllocationEvidence(run_id=runtime.frozen.run_id, tick=engine.current_tick, junction_id=trace.node_id, allocator_id=trace.allocator_id, movement_spec_hash=engine.movement_spec_hash, semantic_sources={"requests": "engine_owned_materialised_trace", "movement_spec": "immutable_topology_metadata", "approvals": "engine_owned_materialised_trace", "resulting_events": "canonical_event_data"}, movements=tuple(flows)))

    def _finalise(self, runtime: _Runtime, engine: LoadingEngine, started: float, *, cancelled: bool = False, timed_out: bool = False) -> None:
        if runtime.lifecycle.state not in {RunLifecycleState.CANCEL_REQUESTED, RunLifecycleState.RUNNING}:
            raise RuntimeError("finalisation requested from unsafe lifecycle state")
        self._transition(runtime, RunLifecycleState.FINALISING, "sealing final persisted evidence")
        final_checkpoint = self._checkpoint(runtime, engine, len(self.repository.checkpoints(runtime.frozen.run_id)))
        existing = self.repository.checkpoints(runtime.frozen.run_id)
        if not existing or existing[-1].state.tick != final_checkpoint.state.tick:
            self.repository.append_checkpoint(final_checkpoint)
        self.repository.write_document(runtime.frozen.run_id, "packets.json", [packet.model_dump(mode="json") for packet in packet_records(engine.packets, runtime.resolved.topology, {})])
        if cancelled:
            terminal = RunLifecycleState.CANCELLED
            status = RunStatus.PARTIAL
            reason = "Explicit cancellation acknowledged at a safe between-tick boundary."
            validation_status = "not_requested"
        elif timed_out:
            terminal = RunLifecycleState.TIMED_OUT
            status = RunStatus.TIMED_OUT
            reason = "Declared tick or wall-time limit reached."
            validation_status = "pending"
        else:
            terminal = RunLifecycleState.COMPLETE
            status = RunStatus.COMPLETE
            reason = "All requested packets reached canonical terminal events."
            validation_status = "pending"
        self._transition(runtime, RunLifecycleState.VALIDATING, "running declared Python integrity validation")
        context = ValidationContext.from_engine(engine, nodes=runtime.resolved.topology.as_loading_nodes(), run_config=runtime.frozen.request.model_dump(mode="json"))
        replay_status = "not_run_for_partial_artifact"
        replay_passed = True
        if not cancelled and not timed_out:
            replay_engine, replay_loader, replay_declarations = self._build_engine(runtime)
            if replay_loader is not None:
                replay_loader.submit_due_departures(replay_engine)
            else:
                for declaration in replay_declarations:
                    replay_engine.instantiate(declaration)
            while len(replay_engine.completed_packet_ids) < runtime.frozen.request.requested_packet_count and replay_engine.current_tick < runtime.frozen.request.tick_limit:
                replay_engine.step()
                if replay_loader is not None:
                    replay_loader.submit_due_departures(replay_engine)
            replay_passed = replay_engine.event_log == engine.event_log
            replay_status = "passed_exact_replay" if replay_passed else "failed_exact_replay_mismatch"
        validation_passed = engine.check_conservation() and engine.check_event_cache_consistency() and context.count_consistency_report.is_consistent and replay_passed
        validation_status = "passed" if validation_passed else "failed"
        bundle = build_run_bundle(run_id=runtime.frozen.run_id, scenario_name=runtime.summary.title, topology=runtime.resolved.topology, context=context, status=status, status_reason=reason, tick_duration_seconds=runtime.resolved.tick_duration_seconds, config_snapshot=runtime.frozen.model_dump(mode="json"), configuration_id="v2.frozen_run_request", validation_status=validation_status, validation_notes=("Core Python conservation, event-cache, and cumulative-count checks executed.", f"deterministic_replay={replay_status}"), code_version=runtime.frozen.code_commit, created_at=runtime.frozen.created_at.isoformat())
        self.repository.write_document(runtime.frozen.run_id, "final_bundle.json", bundle.model_dump(mode="json"))
        self.repository.write_document(runtime.frozen.run_id, "validation.json", bundle.validation.model_dump(mode="json"))
        self._transition(runtime, terminal, reason)
        self._update_summary(runtime, engine, validation_status=validation_status, stop_reason=reason)
        self.repository.write_document(runtime.frozen.run_id, "lifecycle.json", [item.model_dump(mode="json") for item in runtime.lifecycle.history])
        self._emit(runtime, LiveMessageType.TERMINAL, {**self._progress_payload(engine, runtime.frozen.request.requested_packet_count, started, len(engine.event_log)), "validation_status": validation_status})

    def _fail(self, runtime: _Runtime, exc: Exception) -> None:
        try:
            self._transition(runtime, RunLifecycleState.FAILED, f"{type(exc).__name__}: {exc}")
        except IllegalLifecycleTransition:
            pass
        summary = runtime.summary.model_copy(update={"status": RunLifecycleState.FAILED, "stop_reason": f"{type(exc).__name__}: {exc}", "updated_at": utc_now(), "validation_status": "failed"})
        runtime.summary = summary
        self.repository.write_summary(summary)
        self.repository.write_document(runtime.frozen.run_id, "lifecycle.json", [item.model_dump(mode="json") for item in runtime.lifecycle.history])
        self._emit(runtime, LiveMessageType.TERMINAL, {"error_type": type(exc).__name__, "detail": str(exc)})

    def _transition(self, runtime: _Runtime, state: RunLifecycleState, reason: str) -> None:
        transition = runtime.lifecycle.transition(state, reason)
        runtime.summary = runtime.summary.model_copy(update={"status": state, "updated_at": utc_now()})
        self.repository.write_summary(runtime.summary)
        self._emit(runtime, LiveMessageType.LIFECYCLE, {"transition": transition.model_dump(mode="json")})

    def _emit(self, runtime: _Runtime, message_type: LiveMessageType, payload: dict[str, object]) -> None:
        message = LiveMessage(message_id=runtime.message_id, run_id=runtime.frozen.run_id, message_type=message_type, occurred_at=utc_now(), lifecycle_state=runtime.lifecycle.state, payload=payload)
        runtime.message_id += 1
        self.repository.append_live_message(message)
        with runtime.condition:
            runtime.condition.notify_all()

    def _update_summary(self, runtime: _Runtime, engine: LoadingEngine, *, validation_status: str, stop_reason: str | None = None) -> None:
        instantiated = len(engine.packets)
        completed = len(engine.completed_packet_ids)
        cancelled = sum(packet.lifecycle_state == LifecycleState.CANCELLED for packet in engine.packets.values())
        runtime.summary = runtime.summary.model_copy(update={"updated_at": utc_now(), "stop_reason": stop_reason, "validation_status": validation_status, "event_count": len(engine.event_log), "final_tick": engine.current_tick, "counts": RunCountsV2(requested=runtime.frozen.request.requested_packet_count, instantiated=instantiated, completed=completed, unresolved=max(runtime.frozen.request.requested_packet_count - completed - cancelled, 0), cancelled=cancelled)})
        self.repository.write_summary(runtime.summary)

    @staticmethod
    def _progress_payload(engine: LoadingEngine, requested: int, started: float, event_offset: int) -> dict[str, object]:
        return {"physical_tick": engine.current_tick, "simulation_time_seconds": engine.current_tick * next(iter(engine.links.values())).tick_duration_seconds, "elapsed_wall_seconds": time.perf_counter() - started, "requested": requested, "instantiated": len(engine.packets), "completed": len(engine.completed_packet_ids), "unresolved": max(requested - len(engine.completed_packet_ids), 0), "event_count": event_offset, "active_frontier": dict(engine.active_work_frontier_metrics)}


def _event_chunk(run_id: str, index: int, events: tuple[Event, ...]) -> EventChunk:
    records = tuple(VCanonicalEvent(sequence_number=event.sequence_number, packet_id=event.packet_id, event_type=event.event_type.value, entity_id=event.entity_id, physical_tick=event.physical_tick) for event in events)
    return EventChunk(run_id=run_id, chunk_index=index, start_sequence=records[0].sequence_number, end_sequence=records[-1].sequence_number, start_tick=records[0].physical_tick, end_tick=records[-1].physical_tick, events=records, content_sha256=event_payload_sha256(tuple(record.model_dump(mode="json") for record in records)))


def _packet_transfer_matches(packet_id: str, upstream: str, downstream: str, events: tuple[Event, ...]) -> bool:
    event_pairs = {(event.packet_id, event.event_type, event.entity_id) for event in events}
    return (packet_id, EventType.LINK_EXIT, upstream) in event_pairs and (packet_id, EventType.LINK_ENTRY, downstream) in event_pairs


def _route_contains_movement(route: tuple[str, ...], upstream: str, downstream: str) -> bool:
    return any(left == upstream and right == downstream for left, right in zip(route, route[1:]))


def _event_dict(event: Event) -> dict[str, object]:
    return {"sequence_number": event.sequence_number, "packet_id": event.packet_id, "event_type": event.event_type.value, "entity_id": event.entity_id, "physical_tick": event.physical_tick}


def _sha(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _code_commit() -> str:
    try:
        return subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=Path(__file__).resolve().parents[3], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _default_title(topology_id: str) -> str:
    return "Sioux Falls bounded workbench run" if topology_id == SIOUX_TOPOLOGY_ID else "Synthetic workbench run"
