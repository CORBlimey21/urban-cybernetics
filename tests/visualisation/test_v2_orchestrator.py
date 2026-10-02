# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from urban_cybernetics.visualisation.orchestrator import RunOrchestrator
from urban_cybernetics.visualisation.persistence import ArtifactRepository
from urban_cybernetics.visualisation.server import create_app
from urban_cybernetics.visualisation.v2_contract import (
    RunCommand,
    RunCommandAction,
    RunLifecycleState,
    RunRequestV2,
)


ROOT = Path(__file__).resolve().parents[2]
V1_ARTIFACTS = ROOT / "fixtures/visualisation/v1"


def request(packet_count: int = 12, *, tick_limit: int = 200) -> RunRequestV2:
    return RunRequestV2(
        topology_id="uc_synthetic_diverge_v1",
        physical_profile_id="UCSyntheticPhysicalProfile_v1",
        demand_source_id="uc_synthetic_alternating_demand_v1",
        requested_packet_count=packet_count,
        tick_policy_id="synthetic_one_second_v1",
        tick_limit=tick_limit,
    )


def wait_for_state(repository: ArtifactRepository, run_id: str, states: set[RunLifecycleState], timeout: float = 5) -> RunLifecycleState:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = repository.get_summary(run_id).status
        if state in states:
            return state
        time.sleep(0.005)
    raise AssertionError(f"run did not reach {states}")


def test_run_freezes_provenance_and_live_chunks_equal_final_artifact(tmp_path: Path) -> None:
    repository = ArtifactRepository(tmp_path)
    orchestrator = RunOrchestrator(repository)
    created = orchestrator.create_run(request(18))
    final = orchestrator.wait(created.run_id, 10)

    assert final.status == RunLifecycleState.COMPLETE
    assert final.counts.completed == final.counts.requested == 18
    frozen = repository.read_document(created.run_id, "request.json")
    assert frozen["request"]["requested_packet_count"] == 18
    assert len(frozen["resolved_topology_hash"]) == 64
    assert len(frozen["resolved_profile_hash"]) == 64
    assert len(frozen["resolved_demand_hash"]) == 64
    chunks = repository.event_chunks(created.run_id)
    sequences = [event.sequence_number for chunk in chunks for event in chunk.events]
    assert sequences == list(range(final.event_count))
    bundle = repository.read_document(created.run_id, "final_bundle.json")
    assert [event["sequence_number"] for event in bundle["event_stream"]["events"]] == sequences
    assert "deterministic_replay=passed_exact_replay" in bundle["validation"]["notes"]


def test_pause_resume_and_duplicate_commands_are_safe_between_ticks(tmp_path: Path) -> None:
    repository = ArtifactRepository(tmp_path)
    orchestrator = RunOrchestrator(repository, execution_yield_seconds=0.003)
    created = orchestrator.create_run(request(100, tick_limit=500))
    wait_for_state(repository, created.run_id, {RunLifecycleState.RUNNING})
    command = RunCommand(command_id="pause-1", action=RunCommandAction.PAUSE)
    first = orchestrator.command(created.run_id, command)
    duplicate = orchestrator.command(created.run_id, command)
    assert first.accepted and duplicate.accepted and duplicate.duplicate
    wait_for_state(repository, created.run_id, {RunLifecycleState.PAUSED})
    paused_tick = repository.get_summary(created.run_id).final_tick
    time.sleep(0.02)
    assert repository.get_summary(created.run_id).final_tick == paused_tick
    resumed = orchestrator.command(created.run_id, RunCommand(command_id="resume-1", action=RunCommandAction.RESUME))
    assert resumed.accepted
    assert orchestrator.wait(created.run_id, 10).status == RunLifecycleState.COMPLETE


def test_cancel_retains_partial_canonical_evidence(tmp_path: Path) -> None:
    repository = ArtifactRepository(tmp_path)
    orchestrator = RunOrchestrator(repository, execution_yield_seconds=0.005)
    created = orchestrator.create_run(request(200, tick_limit=1000))
    wait_for_state(repository, created.run_id, {RunLifecycleState.RUNNING})
    acknowledgement = orchestrator.command(created.run_id, RunCommand(command_id="cancel-1", action=RunCommandAction.CANCEL))
    assert acknowledgement.accepted
    final = orchestrator.wait(created.run_id, 10)
    assert final.status == RunLifecycleState.CANCELLED
    assert final.counts.unresolved > 0
    assert final.event_count > 0
    bundle = repository.read_document(created.run_id, "final_bundle.json")
    assert bundle["run"]["status"] == "partial"
    assert "not_run_for_partial_artifact" in bundle["validation"]["notes"][-1]


def test_api_browses_v1_launches_v2_and_exactly_seeks(tmp_path: Path) -> None:
    repository = ArtifactRepository(tmp_path)
    orchestrator = RunOrchestrator(repository)
    api = TestClient(create_app(artifact_directory=V1_ARTIFACTS, v2_artifact_directory=tmp_path, web_distribution=ROOT / "web/nonexistent-test-dist", orchestrator=orchestrator))
    catalogue = api.get("/api/v2/catalogue")
    assert catalogue.status_code == 200
    assert catalogue.json()["schema_version"] == "uc.visualisation.control.v2"
    assert any(item["artifact_format"] == "v1_bundle" for item in api.get("/api/v2/artifacts").json())
    response = api.post("/api/v2/runs", json=request(8).model_dump(mode="json"))
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    final = orchestrator.wait(run_id, 10)
    assert final.status == RunLifecycleState.COMPLETE
    artifacts = api.get("/api/v2/artifacts").json()
    assert any(item["run_id"] == run_id and item["artifact_format"] == "v2_chunked" for item in artifacts)
    sought = api.get(f"/api/v2/runs/{run_id}/replay/{final.final_tick}")
    assert sought.status_code == 200
    assert sought.json()["state"]["counts"]["completed"] == 8
    events = api.get(f"/api/v2/runs/{run_id}/events?start_sequence=3&limit=5").json()["events"]
    assert [event["sequence_number"] for event in events] == list(range(3, 8))
    stream = api.get(f"/api/v2/runs/{run_id}/stream", headers={"Last-Event-ID": "2"})
    assert stream.status_code == 200
    streamed_ids = [int(line.removeprefix("id: ")) for line in stream.text.splitlines() if line.startswith("id: ")]
    assert streamed_ids and min(streamed_ids) > 2


def test_browser_disconnect_is_not_part_of_run_lifecycle(tmp_path: Path) -> None:
    repository = ArtifactRepository(tmp_path)
    orchestrator = RunOrchestrator(repository, execution_yield_seconds=0.001)
    created = orchestrator.create_run(request(40))
    # No stream consumer is ever connected; durable execution still completes.
    final = orchestrator.wait(created.run_id, 10)
    assert final.status == RunLifecycleState.COMPLETE
    messages = repository.live_messages(created.run_id)
    assert messages
    midpoint = messages[len(messages) // 2].message_id
    resumed = repository.live_messages(created.run_id, after=midpoint)
    assert resumed == tuple(message for message in messages if message.message_id > midpoint)
    assert resumed[-1].message_type.value == "terminal_result"


def test_live_cumulative_projection_uses_latest_sealed_event_tick_when_summary_lags(tmp_path: Path) -> None:
    repository = ArtifactRepository(tmp_path)
    orchestrator = RunOrchestrator(repository)
    created = orchestrator.create_run(request(8))
    final = orchestrator.wait(created.run_id, 10)
    assert final.final_tick > 0
    repository.write_summary(final.model_copy(update={"final_tick": 0}))
    api = TestClient(create_app(
        artifact_directory=V1_ARTIFACTS,
        v2_artifact_directory=tmp_path,
        web_distribution=ROOT / "web/nonexistent-test-dist",
        orchestrator=orchestrator,
    ))
    topology = repository.read_document(created.run_id, "topology.json")
    link_id = topology["links"][0]["link_id"]
    response = api.get(f"/api/v2/runs/{created.run_id}/links/{link_id}/cumulative-counts")

    assert response.status_code == 200
    maximum_event_tick = max(
        event.physical_tick
        for chunk in repository.event_chunks(created.run_id)
        for event in chunk.events
    )
    assert response.json()["ticks"][-1] == maximum_event_tick


def test_tick_bound_retains_timed_out_unresolved_state(tmp_path: Path) -> None:
    repository = ArtifactRepository(tmp_path)
    orchestrator = RunOrchestrator(repository)
    created = orchestrator.create_run(request(20, tick_limit=1))
    final = orchestrator.wait(created.run_id, 10)
    assert final.status == RunLifecycleState.TIMED_OUT
    assert final.counts.unresolved > 0
    bundle = repository.read_document(created.run_id, "final_bundle.json")
    assert bundle["run"]["status"] == "timed_out"
    assert bundle["replay_states"][-1]["counts"]["completed"] < 20
