"""Local read-only FastAPI surface for V1 run evidence."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .contract import CONTRACT_VERSION
from .store import RunNotFoundError, RunStore


def create_app(
    *,
    artifact_directory: Path | None = None,
    web_distribution: Path | None = None,
) -> FastAPI:
    """Create an app whose simulation-facing operations are all read-only."""

    project_root = Path(__file__).resolve().parents[3]
    artifact_directory = artifact_directory or (
        project_root / "fixtures" / "visualisation" / "v1"
    )
    web_distribution = web_distribution or (project_root / "web" / "dist")
    store = RunStore(artifact_directory)
    app = FastAPI(
        title="Urban Cybernetics V",
        version="1.0.0",
        description="Read-only local API for persisted simulation evidence.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET"],
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
