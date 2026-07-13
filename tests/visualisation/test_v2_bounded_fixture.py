from __future__ import annotations

from pathlib import Path

from urban_cybernetics.core import Event, EventType
from urban_cybernetics.visualisation.contract import VPacket
from urban_cybernetics.visualisation.persistence import ArtifactRepository, event_payload_sha256
from urban_cybernetics.visualisation.replay import build_replay_states, resume_replay_from_checkpoint


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "fixtures/visualisation/v2"
RUN_ID = "v2-sioux-falls-bounded-100-v1"


def evidence():
    repository = ArtifactRepository(FIXTURE_ROOT)
    summary = repository.get_summary(RUN_ID)
    topology = repository.read_document(RUN_ID, "topology.json")
    packets = tuple(VPacket.model_validate(item) for item in repository.read_document(RUN_ID, "packets.json"))
    events = tuple(
        Event(event.sequence_number, event.packet_id, EventType(event.event_type), event.entity_id, event.physical_tick)
        for chunk in repository.event_chunks(RUN_ID)
        for event in chunk.events
    )
    return repository, summary, topology, packets, events


def test_bounded_sioux_falls_fixture_is_complete_validated_and_exact_replay_certified() -> None:
    repository, summary, _, _, events = evidence()
    bundle = repository.read_document(RUN_ID, "final_bundle.json")
    assert summary.status.value == "complete"
    assert summary.validation_status == "passed"
    assert summary.counts.completed == summary.counts.requested == 100
    assert summary.counts.unresolved == summary.counts.cancelled == 0
    assert summary.event_count == len(events) == 926
    assert summary.final_tick == 32
    assert "deterministic_replay=passed_exact_replay" in bundle["validation"]["notes"]
    assert any("not empirically calibrated" in warning for warning in summary.assumption_warnings)


def test_every_checkpoint_reconstructs_same_final_state_as_raw_replay() -> None:
    repository, summary, topology, packets, events = evidence()
    link_ids = tuple(link["link_id"] for link in topology["links"])
    raw_final = build_replay_states(events=events, packets=packets, link_ids=link_ids, start_tick=0, end_tick=summary.final_tick)[-1]
    for checkpoint in repository.checkpoints(RUN_ID):
        continuation = tuple(event for event in events if checkpoint.state.applied_through_sequence is None or event.sequence_number > checkpoint.state.applied_through_sequence)
        rebuilt = resume_replay_from_checkpoint(checkpoint=checkpoint.state, events=continuation, packets=packets, link_ids=link_ids, target_tick=summary.final_tick)
        assert rebuilt == raw_final


def test_chunks_are_contiguous_and_boundaries_do_not_change_replay() -> None:
    repository, summary, topology, packets, events = evidence()
    chunks = repository.event_chunks(RUN_ID)
    assert [event.sequence_number for event in events] == list(range(summary.event_count))
    assert all(left.end_sequence + 1 == right.start_sequence for left, right in zip(chunks, chunks[1:]))
    link_ids = tuple(link["link_id"] for link in topology["links"])
    for chunk in chunks:
        assert chunk.content_sha256 == event_payload_sha256(tuple(event.model_dump(mode="json") for event in chunk.events))
        prefix = tuple(event for event in events if event.sequence_number <= chunk.end_sequence)
        state = build_replay_states(events=prefix, packets=packets, link_ids=link_ids, start_tick=0, end_tick=chunk.end_tick)[-1]
        assert state.applied_through_sequence == chunk.end_sequence


def test_movement_projection_points_back_to_canonical_transfer_events() -> None:
    repository, _, _, _, events = evidence()
    events_by_sequence = {event.sequence_number: event for event in events}
    movement_evidence = repository.movement_evidence(RUN_ID)
    assert movement_evidence
    approved_count = 0
    for trace in movement_evidence:
        assert trace.semantic_sources["approvals"] == "engine_owned_materialised_trace"
        assert trace.semantic_sources["resulting_events"] == "canonical_event_data"
        for movement in trace.movements:
            approved_count += len(movement.approved_packet_ids)
            for sequence in movement.resulting_canonical_event_sequences:
                event = events_by_sequence[sequence]
                assert event.physical_tick == trace.tick
                assert event.packet_id in movement.approved_packet_ids
                assert event.event_type in {EventType.LINK_EXIT, EventType.LINK_ENTRY}
    assert approved_count > 0
