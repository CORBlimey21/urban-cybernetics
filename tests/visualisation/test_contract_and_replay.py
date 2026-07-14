"""Integrity tests for the detached V1 evidence contract and replay fold."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from urban_cybernetics.core import Event, EventType
from urban_cybernetics.visualisation.contract import (
    FieldAvailability,
    LayoutKind,
    LayoutOrigin,
    PacketReplayStatus,
    RunStatus,
    SemanticStatus,
    VEventStream,
    VPacket,
    VRunBundle,
)
from urban_cybernetics.visualisation.export import load_run_bundle
from urban_cybernetics.visualisation.fixtures import build_synthetic_fixture
from urban_cybernetics.visualisation.replay import ReplayIntegrityError, build_replay_states


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures/visualisation/v1/synthetic_strict_fifo_diverge_v1.json"


def test_persisted_bundle_validates_and_preserves_identity_and_provenance() -> None:
    bundle = load_run_bundle(FIXTURE)

    assert bundle.schema_version == "uc.visualisation.run.v1"
    assert bundle.run.topology_id == bundle.topology.topology_id
    assert bundle.run.topology_hash == bundle.topology.topology_hash
    assert len(bundle.run.topology_hash) == 64
    assert bundle.provenance.source_name == "UC V1 deterministic synthetic fixture"
    assert len(bundle.provenance.source_file_sha256) == 64
    assert bundle.provenance.config_snapshot["tick_duration_seconds"] == 1.0
    assert bundle.presentation.descriptor.semantic_status == SemanticStatus.PRESENTATION_ONLY


def test_sanctioned_fixture_export_is_deterministic() -> None:
    assert build_synthetic_fixture() == load_run_bundle(FIXTURE)


def test_contract_rejects_reordered_canonical_events() -> None:
    bundle = load_run_bundle(FIXTURE)
    first, second, *remaining = bundle.event_stream.events

    with pytest.raises(ValidationError, match="contiguous sequence-number order"):
        VEventStream(
            descriptor=bundle.event_stream.descriptor,
            events=(second, first, *remaining),
        )


def test_same_tick_sequence_is_preserved_by_persistence_and_api_contract() -> None:
    bundle = load_run_bundle(FIXTURE)
    same_tick = [
        event.sequence_number
        for event in bundle.event_stream.events
        if event.physical_tick == 3
    ]

    assert same_tick == sorted(same_tick)
    assert len(same_tick) > 1
    assert same_tick == list(range(same_tick[0], same_tick[-1] + 1))


def test_every_seek_state_equals_raw_prefix_replay() -> None:
    bundle = load_run_bundle(FIXTURE)
    core_events = tuple(
        Event(
            sequence_number=event.sequence_number,
            packet_id=event.packet_id,
            event_type=EventType(event.event_type),
            entity_id=event.entity_id,
            physical_tick=event.physical_tick,
        )
        for event in bundle.event_stream.events
    )
    link_ids = tuple(link.link_id for link in bundle.topology.links)

    for expected in bundle.replay_states:
        prefix = tuple(event for event in core_events if event.physical_tick <= expected.tick)
        rebuilt = build_replay_states(
            events=prefix,
            packets=bundle.packets,
            link_ids=link_ids,
            start_tick=0,
            end_tick=expected.tick,
        )[-1]
        assert rebuilt == expected


def test_completed_unresolved_and_cancelled_states_remain_distinct() -> None:
    packets = tuple(_packet(packet_id) for packet_id in ("P1", "P2", "P3"))
    events = (
        Event(0, "P1", EventType.INSTANTIATED, "L1", 0),
        Event(1, "P1", EventType.LINK_ENTRY, "L1", 0),
        Event(2, "P2", EventType.INSTANTIATED, "L1", 0),
        Event(3, "P2", EventType.LINK_ENTRY, "L1", 0),
        Event(4, "P3", EventType.INSTANTIATED, "L1", 0),
        Event(5, "P3", EventType.LINK_ENTRY, "L1", 0),
        Event(6, "P1", EventType.LINK_EXIT, "L1", 1),
        Event(7, "P1", EventType.COMPLETED, "L1", 1),
        Event(8, "P3", EventType.CANCELLED, "L1", 1),
    )

    final = build_replay_states(
        events=events,
        packets=packets,
        link_ids=("L1",),
        start_tick=0,
        end_tick=1,
    )[-1]
    statuses = {packet.packet_id: packet.status for packet in final.packets}

    assert statuses == {
        "P1": PacketReplayStatus.COMPLETED,
        "P2": PacketReplayStatus.IN_TRANSIT,
        "P3": PacketReplayStatus.CANCELLED,
    }
    assert final.counts.completed == 1
    assert final.counts.in_transit == 1
    assert final.counts.cancelled == 1


def test_partial_run_status_round_trips_without_completing_unresolved_packets() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["run"]["status"] = RunStatus.PARTIAL.value
    payload["run"]["status_reason"] = "Stopped at an explicit inspection bound."
    final_packet = payload["replay_states"][-1]["packets"][0]
    final_packet["status"] = PacketReplayStatus.IN_TRANSIT.value
    payload["replay_states"][-1]["counts"]["completed"] -= 1
    payload["replay_states"][-1]["counts"]["in_transit"] += 1

    partial = VRunBundle.model_validate(payload)

    assert partial.run.status == RunStatus.PARTIAL
    assert partial.replay_states[-1].packets[0].status == PacketReplayStatus.IN_TRANSIT


def test_complete_run_rejects_unresolved_final_state() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    final_packet = payload["replay_states"][-1]["packets"][0]
    final_packet["status"] = PacketReplayStatus.IN_TRANSIT.value
    payload["replay_states"][-1]["counts"]["completed"] -= 1
    payload["replay_states"][-1]["counts"]["in_transit"] += 1

    with pytest.raises(ValidationError, match="complete run cannot end"):
        VRunBundle.model_validate(payload)


def test_replay_rejects_noncanonical_same_tick_reordering() -> None:
    packets = (_packet("P1"),)
    events = (
        Event(0, "P1", EventType.LINK_ENTRY, "L1", 0),
        Event(1, "P1", EventType.INSTANTIATED, "L1", 0),
    )

    with pytest.raises(ReplayIntegrityError, match="before instantiation"):
        build_replay_states(
            events=events,
            packets=packets,
            link_ids=("L1",),
            start_tick=0,
            end_tick=0,
        )


def test_frontend_and_backend_enums_are_compatible() -> None:
    frontend = json.loads(
        (ROOT / "web/src/contract-enums.json").read_text(encoding="utf-8")
    )

    assert frontend["semantic_status"] == [item.value for item in SemanticStatus]
    assert frontend["run_status"] == [item.value for item in RunStatus]
    assert frontend["packet_replay_status"] == [
        item.value for item in PacketReplayStatus
    ]
    assert frontend["field_availability"] == [
        item.value for item in FieldAvailability
    ]
    assert frontend["layout_kind"] == [item.value for item in LayoutKind]
    assert frontend["layout_origin"] == [item.value for item in LayoutOrigin]


def _packet(packet_id: str) -> VPacket:
    return VPacket(
        packet_id=packet_id,
        demand_id=f"D-{packet_id}",
        origin_node_id=None,
        destination_node_id=None,
        route_id=None,
        route_intent=("L1",),
        cohort_id=None,
        authority_id=None,
        packet_unit_weight=1,
        field_availability={
            "origin_node_id": FieldAvailability.UNAVAILABLE_IN_ARTIFACT,
            "destination_node_id": FieldAvailability.UNAVAILABLE_IN_ARTIFACT,
            "route_id": FieldAvailability.UNAVAILABLE_IN_ARTIFACT,
            "cohort_id": FieldAvailability.UNAVAILABLE_IN_ARTIFACT,
            "authority_id": FieldAvailability.UNAVAILABLE_IN_ARTIFACT,
        },
    )
