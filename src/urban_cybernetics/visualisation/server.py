"""Local V1 evidence API and narrow V2 workbench control/evidence surface."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .contract import CONTRACT_VERSION
from .catalogue import ResourceResolutionError, build_resource_catalogue
from .orchestrator import RunNotActive, RunOrchestrator, TERMINAL_STATES
from .persistence import ArtifactRepository, V2ArtifactNotFound
from .replay import build_replay_states, resume_replay_from_checkpoint
from .store import RunNotFoundError, RunStore
from .export import deterministic_positions
from .contract import VPacket, VTopology
from urban_cybernetics.topology import CanonicalNode, CanonicalTopology, CanonicalTopologyLink, TopologySourceMetadata
from .v2_contract import RunCommand, RunRequestV2
from urban_cybernetics.core import Event, EventType


def create_app(
    *,
    artifact_directory: Path | None = None,
    v2_artifact_directory: Path | None = None,
    web_distribution: Path | None = None,
    orchestrator: RunOrchestrator | None = None,
) -> FastAPI:
    """Create the local app; V2 writes are limited to typed run commands."""

    project_root = Path(__file__).resolve().parents[3]
    artifact_directory = artifact_directory or (
        project_root / "fixtures" / "visualisation" / "v1"
    )
    web_distribution = web_distribution or (project_root / "web" / "dist")
    store = RunStore(artifact_directory)
    v2_artifact_directory = v2_artifact_directory or (
        project_root / "outputs" / "visualisation" / "runs"
    )
    repository = orchestrator.repository if orchestrator is not None else ArtifactRepository(
        v2_artifact_directory,
        read_only_roots=(project_root / "fixtures" / "visualisation" / "v2",),
    )
    orchestrator = orchestrator or RunOrchestrator(repository, execution_yield_seconds=0.01)
    app = FastAPI(
        title="Urban Cybernetics V",
        version="1.0.0",
        description="Read-only local API for persisted simulation evidence.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    def bundle_for(run_id: str):
        try:
            return store.get(run_id)
        except RunNotFoundError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc

    @app.get("/api/v1/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "contract_version": CONTRACT_VERSION,
            "run_count": len(store.list_bundles()),
            "mode": "read_only_persisted_evidence",
        }

    @app.get("/api/v1/contract")
    def contract() -> dict[str, object]:
        from .contract import (
            FieldAvailability,
            PacketReplayStatus,
            RunStatus,
            SemanticStatus,
        )

        return {
            "schema_version": CONTRACT_VERSION,
            "semantic_status": [item.value for item in SemanticStatus],
            "run_status": [item.value for item in RunStatus],
            "packet_replay_status": [item.value for item in PacketReplayStatus],
            "field_availability": [item.value for item in FieldAvailability],
        }

    @app.get("/api/v1/runs")
    def runs() -> list[dict[str, object]]:
        return [
            {
                **bundle.run.model_dump(mode="json"),
                "validation_status": bundle.validation.overall_status,
            }
            for bundle in store.list_bundles()
        ]

    @app.get("/api/v1/runs/{run_id}/manifest")
    def manifest(run_id: str) -> dict[str, object]:
        bundle = bundle_for(run_id)
        return {
            "schema_version": bundle.schema_version,
            "run": bundle.run.model_dump(mode="json"),
            "provenance": bundle.provenance.model_dump(mode="json"),
            "topology": bundle.topology.model_dump(mode="json"),
            "packets_descriptor": bundle.packets_descriptor.model_dump(mode="json"),
            "packets": [packet.model_dump(mode="json") for packet in bundle.packets],
            "validation": bundle.validation.model_dump(mode="json"),
            "presentation": bundle.presentation.model_dump(mode="json"),
        }

    @app.get("/api/v1/runs/{run_id}/events")
    def events(
        run_id: str,
        start_sequence: int = Query(default=0, ge=0),
        limit: int = Query(default=5000, ge=1, le=10000),
    ) -> dict[str, object]:
        bundle = bundle_for(run_id)
        source = bundle.event_stream.events
        selected = source[start_sequence : start_sequence + limit]
        next_sequence = start_sequence + len(selected)
        return {
            "descriptor": bundle.event_stream.descriptor.model_dump(mode="json"),
            "events": [event.model_dump(mode="json") for event in selected],
            "start_sequence": start_sequence,
            "next_sequence": next_sequence if next_sequence < len(source) else None,
            "total_event_count": len(source),
        }

    @app.get("/api/v1/runs/{run_id}/replay")
    def replay(
        run_id: str,
        start_tick: int = Query(default=0, ge=0),
        end_tick: int | None = Query(default=None, ge=0),
    ) -> dict[str, object]:
        bundle = bundle_for(run_id)
        resolved_end_tick = min(
            end_tick if end_tick is not None else start_tick + 499,
            bundle.run.end_tick,
        )
        if resolved_end_tick < start_tick:
            raise HTTPException(status_code=422, detail="end_tick precedes start_tick")
        states = tuple(
            state
            for state in bundle.replay_states
            if start_tick <= state.tick <= resolved_end_tick
        )
        return {
            "states": [state.model_dump(mode="json") for state in states],
            "start_tick": start_tick,
            "end_tick": resolved_end_tick,
            "run_end_tick": bundle.run.end_tick,
        }

    @app.get("/api/v1/runs/{run_id}/links/{link_id}/cumulative-counts")
    def cumulative_counts(run_id: str, link_id: str) -> dict[str, object]:
        bundle = bundle_for(run_id)
        for series in bundle.cumulative_link_series:
            if series.link_id == link_id:
                return series.model_dump(mode="json")
        raise HTTPException(status_code=404, detail="link not found")

    @app.get("/api/v2/catalogue")
    def v2_catalogue() -> dict[str, object]:
        return build_resource_catalogue().model_dump(mode="json")

    @app.get("/api/v2/artifacts")
    def v2_artifacts(
        topology_id: str | None = None,
        status: str | None = None,
        profile_id: str | None = None,
    ) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        for bundle in store.list_bundles():
            records.append({
                "artifact_format": "v1_bundle",
                "run_id": bundle.run.run_id,
                "title": bundle.run.scenario_name,
                "description": bundle.run.status_reason,
                "contract_version": bundle.schema_version,
                "topology_id": bundle.run.topology_id,
                "topology_hash": bundle.run.topology_hash,
                "physical_profile_id": bundle.run.model_profile_id,
                "profile_hash": bundle.run.configuration_hash,
                "demand_source_id": bundle.provenance.input_artifact_ids[0] if bundle.provenance.input_artifact_ids else "unavailable_in_artifact",
                "demand_hash": bundle.provenance.source_file_sha256,
                "seed": bundle.provenance.config_snapshot.get("seed", 0),
                "status": bundle.run.status.value,
                "stop_reason": bundle.run.status_reason,
                "created_at": bundle.run.created_at,
                "updated_at": bundle.run.created_at,
                "validation_status": bundle.validation.overall_status,
                "configuration_hash": bundle.run.configuration_hash,
                "event_count": bundle.run.event_count,
                "final_tick": bundle.run.end_tick,
                "counts": bundle.replay_states[-1].counts.model_dump(mode="json"),
                "assumption_warnings": list(bundle.provenance.interpretation_assumptions),
            })
        records.extend({"artifact_format": "v2_chunked", **summary.model_dump(mode="json")} for summary in repository.list_summaries())
        if topology_id is not None:
            records = [record for record in records if record["topology_id"] == topology_id]
        if status is not None:
            records = [record for record in records if record["status"] == status]
        if profile_id is not None:
            records = [record for record in records if record["physical_profile_id"] == profile_id]
        return records

    @app.post("/api/v2/runs", status_code=202)
    def create_v2_run(request: RunRequestV2) -> dict[str, object]:
        try:
            return orchestrator.create_run(request).model_dump(mode="json")
        except ResourceResolutionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/v2/runs/{run_id}")
    def v2_run(run_id: str) -> dict[str, object]:
        try:
            return repository.get_summary(run_id).model_dump(mode="json")
        except V2ArtifactNotFound as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc

    @app.get("/api/v2/runs/{run_id}/bundle")
    def v2_bundle(run_id: str) -> object:
        try:
            return repository.read_document(run_id, "final_bundle.json")
        except V2ArtifactNotFound as exc:
            raise HTTPException(status_code=409, detail="final bundle is not sealed") from exc

    @app.get("/api/v2/runs/{run_id}/live-manifest")
    def v2_live_manifest(run_id: str) -> dict[str, object]:
        try:
            summary = repository.get_summary(run_id)
            topology_payload = repository.read_document(run_id, "topology.json")
            request_payload = repository.read_document(run_id, "request.json")
            packets = repository.read_document(run_id, "packets.json")
        except V2ArtifactNotFound as exc:
            raise HTTPException(status_code=409, detail="live evidence is not sealed yet") from exc
        topology = VTopology.model_validate(topology_payload)
        canonical = _canonical_topology_for_layout(topology)
        return {
            "schema_version": "uc.visualisation.run.v1",
            "run": {
                "run_id": run_id, "scenario_name": summary.title,
                "status": "timed_out" if summary.status.value == "timed_out" else "complete" if summary.status.value == "complete" else "partial",
                "status_reason": summary.stop_reason or f"Live lifecycle state: {summary.status.value}.",
                "topology_id": summary.topology_id, "topology_hash": summary.topology_hash,
                "configuration_id": "v2.frozen_run_request", "configuration_hash": summary.configuration_hash,
                "model_profile_id": summary.physical_profile_id,
                "tick_duration_seconds": request_payload["resolved_tick_duration_seconds"],
                "simulation_time_basis": "integer_physical_tick", "start_tick": 0,
                "end_tick": summary.final_tick, "event_count": summary.event_count,
                "packet_count": len(packets), "created_at": summary.created_at.isoformat(),
            },
            "provenance": {
                "descriptor": _descriptor("provenance_configuration_metadata", "frozen V2 run request"),
                "code_version": request_payload["code_commit"], "input_artifact_ids": [summary.demand_source_id],
                "source_name": summary.topology_id, "source_format": "V2 declared resource catalogue",
                "source_file_sha256": summary.demand_hash, "interpretation_assumptions": list(summary.assumption_warnings),
                "config_snapshot": request_payload,
            },
            "topology": topology_payload,
            "packets_descriptor": _descriptor("provenance_configuration_metadata", "immutable packet metadata snapshot", units="unit packets", counting_basis="one conserved packet identity per record"),
            "packets": packets,
            "validation": {"descriptor": _descriptor("validation_output", "Python validation layer"), "overall_status": "not_run" if summary.validation_status == "pending" else summary.validation_status, "checks": {}, "notes": ["Validation remains pending until finalisation."]},
            "presentation": {"descriptor": _descriptor("presentation_only_interpolation", "viewer layout adapter", units="normalised canvas coordinates"), "layout_kind": "synthetic_deterministic", "layout_note": "Deterministic topology layout; not geographic or physical geometry.", "node_positions": deterministic_positions(canonical), "interpolation_note": "Animated markers are presentation-only and never scientific state."},
        }

    @app.post("/api/v2/runs/{run_id}/commands")
    def v2_command(run_id: str, command: RunCommand) -> dict[str, object]:
        try:
            return orchestrator.command(run_id, command).model_dump(mode="json")
        except (RunNotActive, V2ArtifactNotFound) as exc:
            raise HTTPException(status_code=404, detail="active run not found") from exc

    @app.get("/api/v2/runs/{run_id}/stream")
    async def v2_stream(run_id: str, request: Request, after: int = Query(default=-1, ge=-1)) -> StreamingResponse:
        try:
            repository.get_summary(run_id)
        except V2ArtifactNotFound as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc

        last_event_id = request.headers.get("last-event-id")
        resume_after = after
        if last_event_id is not None:
            try:
                resume_after = max(resume_after, int(last_event_id))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="invalid Last-Event-ID") from exc

        async def messages():
            cursor = resume_after
            while True:
                emitted = False
                for message in repository.live_messages(run_id, cursor):
                    emitted = True
                    cursor = message.message_id
                    data = message.model_dump_json()
                    yield f"id: {cursor}\nevent: {message.message_type.value}\ndata: {data}\n\n"
                summary = repository.get_summary(run_id)
                if summary.status in TERMINAL_STATES and not emitted:
                    return
                if await request.is_disconnected():
                    return
                if not emitted:
                    yield ": keepalive\n\n"
                await asyncio.sleep(0.15)

        return StreamingResponse(messages(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/v2/runs/{run_id}/events")
    def v2_events(run_id: str, start_sequence: int = Query(default=0, ge=0), limit: int = Query(default=5000, ge=1, le=10000)) -> dict[str, object]:
        try:
            chunks = repository.event_chunks(run_id, start_sequence=start_sequence, end_sequence=start_sequence + limit - 1)
        except V2ArtifactNotFound as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        events = [event for chunk in chunks for event in chunk.events if start_sequence <= event.sequence_number < start_sequence + limit]
        summary = repository.get_summary(run_id)
        next_sequence = start_sequence + len(events)
        return {"events": [event.model_dump(mode="json") for event in events], "start_sequence": start_sequence, "next_sequence": next_sequence if next_sequence < summary.event_count else None, "total_event_count": summary.event_count}

    @app.get("/api/v2/runs/{run_id}/replay/{tick}")
    def v2_replay(run_id: str, tick: int) -> dict[str, object]:
        try:
            summary = repository.get_summary(run_id)
            topology = repository.read_document(run_id, "topology.json")
            packets_payload = repository.read_document(run_id, "packets.json")
        except V2ArtifactNotFound as exc:
            raise HTTPException(status_code=404, detail="evidence not yet available") from exc
        if tick < 0 or tick > summary.final_tick:
            raise HTTPException(status_code=422, detail="tick outside sealed evidence")
        packets = tuple(VPacket.model_validate(item) for item in packets_payload)
        link_ids = tuple(link["link_id"] for link in topology["links"])
        checkpoints = tuple(checkpoint for checkpoint in repository.checkpoints(run_id) if checkpoint.state.tick <= tick)
        all_events = tuple(_core_event(event) for chunk in repository.event_chunks(run_id) for event in chunk.events if event.physical_tick <= tick)
        if checkpoints:
            checkpoint = checkpoints[-1]
            continuation = tuple(event for event in all_events if checkpoint.state.applied_through_sequence is None or event.sequence_number > checkpoint.state.applied_through_sequence)
            state = resume_replay_from_checkpoint(checkpoint=checkpoint.state, events=continuation, packets=packets, link_ids=link_ids, target_tick=tick)
            source = {"kind": "sealed_checkpoint_plus_canonical_events", "checkpoint_tick": checkpoint.state.tick}
        else:
            state = build_replay_states(events=all_events, packets=packets, link_ids=link_ids, start_tick=0, end_tick=tick)[-1]
            source = {"kind": "canonical_events_from_tick_zero", "checkpoint_tick": None}
        return {"state": state.model_dump(mode="json"), "source": source}

    @app.get("/api/v2/runs/{run_id}/movements")
    def v2_movements(run_id: str, tick: int | None = Query(default=None, ge=0), node_id: str | None = None) -> list[dict[str, object]]:
        try:
            evidence = repository.movement_evidence(run_id, tick)
        except V2ArtifactNotFound as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        if node_id is not None:
            evidence = tuple(item for item in evidence if item.junction_id == node_id)
        return [item.model_dump(mode="json") for item in evidence]

    @app.get("/api/v2/runs/{run_id}/links/{link_id}/cumulative-counts")
    def v2_cumulative(run_id: str, link_id: str) -> dict[str, object]:
        try:
            summary = repository.get_summary(run_id)
            topology = repository.read_document(run_id, "topology.json")
            packets_payload = repository.read_document(run_id, "packets.json")
        except V2ArtifactNotFound as exc:
            raise HTTPException(status_code=404, detail="evidence not yet available") from exc
        link_ids = tuple(link["link_id"] for link in topology["links"])
        if link_id not in link_ids:
            raise HTTPException(status_code=404, detail="link not found")
        packets = tuple(VPacket.model_validate(item) for item in packets_payload)
        all_events = tuple(_core_event(event) for chunk in repository.event_chunks(run_id) for event in chunk.events)
        states = build_replay_states(events=all_events, packets=packets, link_ids=link_ids, start_tick=0, end_tick=summary.final_tick)
        link_states = [next(item for item in state.links if item.link_id == link_id) for state in states]
        return {"descriptor": _descriptor("event_derived_scientific_projection", "Python replay fold over canonical event chunks", units="unit packets", time_basis="inclusive integer physical tick", counting_basis="cumulative canonical LINK_ENTRY and LINK_EXIT events", boundary_direction="entries at upstream link boundary; exits at downstream link boundary", aggregation_window_ticks=1), "link_id": link_id, "ticks": [state.tick for state in states], "cumulative_entries": [item.cumulative_entries for item in link_states], "cumulative_exits": [item.cumulative_exits for item in link_states], "storage_packets": [item.occupancy_packets for item in link_states]}

    @app.get("/api/v2/compare")
    def v2_compare(run_id: list[str] = Query()) -> dict[str, object]:
        if len(run_id) != 2:
            raise HTTPException(status_code=422, detail="exactly two run_id values are required")
        records = {record["run_id"]: record for record in v2_artifacts()}
        try:
            left, right = (records[item] for item in run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="comparison run not found") from exc
        return {"runs": [left, right], "compatibility": {"same_topology": left["topology_hash"] == right["topology_hash"], "same_profile": left["profile_hash"] == right["profile_hash"], "same_demand": left["demand_hash"] == right["demand_hash"]}}

    if web_distribution.is_dir():
        assets = web_distribution / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def browser_app(path: str) -> FileResponse:
            candidate = web_distribution / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(web_distribution / "index.html")

    return app


def _core_event(event) -> Event:
    return Event(sequence_number=event.sequence_number, packet_id=event.packet_id, event_type=EventType(event.event_type), entity_id=event.entity_id, physical_tick=event.physical_tick)


def _descriptor(semantic_status: str, source: str, **values: object) -> dict[str, object]:
    return {"semantic_status": semantic_status, "source": source, "units": values.get("units"), "time_basis": values.get("time_basis"), "counting_basis": values.get("counting_basis"), "boundary_direction": values.get("boundary_direction"), "aggregation_window_ticks": values.get("aggregation_window_ticks")}


def _canonical_topology_for_layout(topology: VTopology) -> CanonicalTopology:
    return CanonicalTopology(
        topology_id=topology.topology_id,
        nodes=tuple(CanonicalNode(node.node_id, node.source_node_id, tuple(node.incoming_link_ids), tuple(node.outgoing_link_ids)) for node in topology.nodes),
        links=tuple(CanonicalTopologyLink(link_id=link.link_id, tail_node_id=link.tail_node_id, head_node_id=link.head_node_id, source_link_id=link.source_link_id, source_tail_node_id=link.tail_node_id, source_head_node_id=link.head_node_id, length_m=link.length_m, lane_count=link.lane_count, free_flow_speed_mps=link.free_flow_speed_mps, capacity_veh_per_hour_per_lane=link.capacity_veh_per_hour_per_lane, jam_density_veh_per_km_per_lane=link.jam_density_veh_per_km_per_lane, backward_wave_speed_mps=link.backward_wave_speed_mps) for link in topology.links),
        source_metadata=TopologySourceMetadata(source_name="V2 persisted topology", source_format="VTopology", source_file_path="topology.json", source_file_sha256=topology.topology_hash),
        interpretation_assumptions=("Layout reconstruction is presentation-only.",),
    )
