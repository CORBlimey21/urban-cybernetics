from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from urban_cybernetics.core import Event, EventType
from urban_cybernetics.visualisation.catalogue import (
    ResourceResolutionError,
    build_resource_catalogue,
    resolve_resources,
)
from urban_cybernetics.visualisation.fixtures import build_synthetic_fixture
from urban_cybernetics.visualisation.lifecycle import (
    IllegalLifecycleTransition,
    RunLifecycle,
)
from urban_cybernetics.visualisation.replay import resume_replay_from_checkpoint
from urban_cybernetics.visualisation.v2_contract import (
    EventChunk,
    RunArtifactSummary,
    RunCountsV2,
    RunLifecycleState,
    RunRequestV2,
)


def synthetic_request(**overrides: object) -> RunRequestV2:
    values: dict[str, object] = {
        "topology_id": "uc_synthetic_diverge_v1",
        "physical_profile_id": "UCSyntheticPhysicalProfile_v1",
        "demand_source_id": "uc_synthetic_alternating_demand_v1",
        "requested_packet_count": 12,
        "tick_policy_id": "synthetic_one_second_v1",
    }
    values.update(overrides)
    return RunRequestV2.model_validate(values)


def test_resource_catalogue_is_versioned_and_ids_are_unique() -> None:
    catalogue = build_resource_catalogue()
    assert catalogue.schema_version == "uc.visualisation.control.v2"
    ids = [resource.resource_id for resource in catalogue.resources]
    assert len(ids) == len(set(ids))
    assert {resource.kind.value for resource in catalogue.resources} >= {
        "topology", "physical_profile", "demand_source", "replay_policy"
    }


def test_invalid_resource_combinations_and_tick_coercion_are_rejected() -> None:
    with pytest.raises(ResourceResolutionError, match="incompatible"):
        resolve_resources(synthetic_request(physical_profile_id="SiouxFallsPhysicalProfile_UC_Default_v1"))
    with pytest.raises(ResourceResolutionError, match="exactly equal"):
        resolve_resources(synthetic_request(requested_tick_duration_seconds=0.5))


def test_run_request_is_strict_and_bounded() -> None:
    with pytest.raises(ValidationError):
        synthetic_request(requested_packet_count=1001)
    with pytest.raises(ValidationError):
        RunRequestV2.model_validate({**synthetic_request().model_dump(), "python_class": "danger"})


def test_lifecycle_accepts_legal_and_rejects_illegal_transitions() -> None:
    lifecycle = RunLifecycle()
    for state in (
        RunLifecycleState.RESOLVING,
        RunLifecycleState.SETTING_UP,
        RunLifecycleState.RUNNING,
        RunLifecycleState.PAUSE_REQUESTED,
        RunLifecycleState.PAUSED,
        RunLifecycleState.RESUME_REQUESTED,
        RunLifecycleState.RUNNING,
        RunLifecycleState.FINALISING,
        RunLifecycleState.VALIDATING,
        RunLifecycleState.COMPLETE,
    ):
        lifecycle.transition(state, "test")
    assert lifecycle.state == RunLifecycleState.COMPLETE
    with pytest.raises(IllegalLifecycleTransition):
        lifecycle.transition(RunLifecycleState.RUNNING, "illegal")


def test_checkpoint_continuation_equals_raw_replay() -> None:
    bundle = build_synthetic_fixture()
    checkpoint = bundle.replay_states[3]
    continuation = tuple(
        Event(
            event.sequence_number,
            event.packet_id,
            EventType(event.event_type),
            event.entity_id,
            event.physical_tick,
        )
        for event in bundle.event_stream.events
        if event.sequence_number > (checkpoint.applied_through_sequence or -1)
    )
    final = resume_replay_from_checkpoint(
        checkpoint=checkpoint,
        events=continuation,
        packets=bundle.packets,
        link_ids=(link.link_id for link in bundle.topology.links),
        target_tick=bundle.run.end_tick,
    )
    assert final == bundle.replay_states[-1]


def test_event_chunk_rejects_sequence_gaps() -> None:
    bundle = build_synthetic_fixture()
    events = bundle.event_stream.events[:2]
    valid = EventChunk(
        run_id="test-run",
        chunk_index=0,
        start_sequence=0,
        end_sequence=1,
        start_tick=events[0].physical_tick,
        end_tick=events[-1].physical_tick,
        events=events,
        content_sha256="0" * 64,
    )
    assert valid.events == events
    with pytest.raises(ValidationError, match="sequence range"):
        EventChunk.model_validate({**valid.model_dump(), "start_sequence": 1})


def test_frontend_backend_v2_enums_are_compatible() -> None:
    root = Path(__file__).resolve().parents[2]
    frontend = json.loads((root / "web/src/v2-contract-enums.json").read_text(encoding="utf-8"))
    assert frontend["run_lifecycle_state"] == [item.value for item in RunLifecycleState]


def test_complete_v2_artifact_cannot_hide_unresolved_packets() -> None:
    with pytest.raises(ValidationError, match="every requested packet"):
        RunArtifactSummary(
            run_id="bad-complete", title="bad", description="bad",
            contract_version="uc.visualisation.evidence.v2", topology_id="t", topology_hash="0" * 64,
            physical_profile_id="p", profile_hash="1" * 64, demand_source_id="d", demand_hash="2" * 64,
            seed=0, status=RunLifecycleState.COMPLETE, stop_reason=None,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC), validation_status="passed",
            configuration_hash="3" * 64, event_count=0, final_tick=0,
            counts=RunCountsV2(requested=1, instantiated=1, completed=0, unresolved=1, cancelled=0),
        )
