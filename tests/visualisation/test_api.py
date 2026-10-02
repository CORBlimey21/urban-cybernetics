# SPDX-License-Identifier: MPL-2.0
"""Read-only API and schema boundary tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from urban_cybernetics.visualisation.server import create_app


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "fixtures/visualisation/v1"
RUN_ID = "v1:synthetic-strict-fifo-diverge"


def client() -> TestClient:
    return TestClient(
        create_app(
            artifact_directory=ARTIFACTS,
            web_distribution=ROOT / "web/nonexistent-test-dist",
        )
    )


def test_health_and_run_manifest_are_versioned_and_read_only() -> None:
    api = client()

    health = api.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "contract_version": "uc.visualisation.run.v1",
        "run_count": 1,
        "mode": "read_only_persisted_evidence",
    }
    assert api.post("/api/v1/runs").status_code == 405
    manifest = api.get(f"/api/v1/runs/{RUN_ID}/manifest")
    assert manifest.status_code == 200
    payload = manifest.json()
    assert payload["run"]["topology_hash"] == payload["topology"]["topology_hash"]
    assert payload["run"]["status"] == "complete"


def test_event_pagination_never_reorders_or_mutates_same_tick_events() -> None:
    api = client()
    all_events = api.get(
        f"/api/v1/runs/{RUN_ID}/events?start_sequence=0&limit=10000"
    ).json()["events"]
    page = api.get(
        f"/api/v1/runs/{RUN_ID}/events?start_sequence=4&limit=7"
    ).json()

    assert page["events"] == all_events[4:11]
    assert [event["sequence_number"] for event in page["events"]] == list(
        range(4, 11)
    )


def test_replay_seek_and_cumulative_curve_match_known_fixture_evidence() -> None:
    api = client()
    replay = api.get(
        f"/api/v1/runs/{RUN_ID}/replay?start_tick=1&end_tick=1"
    ).json()
    state = replay["states"][0]
    curve = api.get(
        f"/api/v1/runs/{RUN_ID}/links/L0/cumulative-counts"
    ).json()

    assert state["tick"] == 1
    assert state["counts"]["queued"] == 1
    assert state["queues"] == [
        {"boundary_id": "boundary:L0->L1", "packet_ids": ["P1"]}
    ]
    assert curve["descriptor"]["semantic_status"] == (
        "event_derived_scientific_projection"
    )
    assert curve["storage_packets"] == [2, 3, 3, 2, 1, 0, 0, 0]


def test_unknown_run_link_and_invalid_range_are_explicit() -> None:
    api = client()

    assert api.get("/api/v1/runs/missing/manifest").status_code == 404
    assert api.get(f"/api/v1/runs/{RUN_ID}/links/missing/cumulative-counts").status_code == 404
    assert api.get(f"/api/v1/runs/{RUN_ID}/replay?start_tick=3&end_tick=2").status_code == 422
