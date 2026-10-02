# SPDX-License-Identifier: MPL-2.0
"""Focused tests for executable-routing-extension-v1."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import (
    DemandDeclaration,
    EventType,
    JUNCTION_FIFO_PARTIAL_BY_MOVEMENT,
    JunctionSpec,
    LifecycleState,
    Link,
    MovementSpec,
    Node,
)
from urban_cybernetics.extensions import (
    EXECUTABLE_ROUTING_EXTENSION_VERSION,
    ExecutableRoutingConfig,
    ExecutableRoutingLoadingEngine,
)
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.routing import (
    ApplicableInstructionResolver,
    RoutingAuthority,
    RoutingAuthorityConfig,
    RoutingInstruction,
    RoutingInstructionStore,
)
from urban_cybernetics.routing.instruction import (
    ACCEPTED,
    INAPPLICABLE_CURRENT_LINK_MISMATCH,
    INAPPLICABLE_DISCONNECTED_ROUTE,
    INAPPLICABLE_NO_INSTRUCTION,
    INAPPLICABLE_UNKNOWN_LINK,
    SELECTION_EXPLICIT_INSTRUCTION,
    SELECTION_ROUTE_INTENT_ADAPTER,
    REJECTED_DUPLICATE_INSTRUCTION_ID,
    REJECTED_DUPLICATE_VERSION,
    REJECTED_STALE_VERSION,
    REJECTED_TERMINAL_PACKET,
)


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures/executable_routing/v1/deterministic_reroute_v1.json"
)
QUEUED_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures/executable_routing/v1/queued_reroute_v1.json"
)


def _link(link_id: str, *, receiving: int = 2) -> Link:
    return Link(
        link_id,
        free_flow_ticks=1,
        declared_sending_capacity_per_tick=2,
        declared_receiving_capacity_per_tick=receiving,
        declared_storage_capacity_packets=20,
    )


def _parity_link(link_id: str) -> Link:
    return Link(
        link_id,
        free_flow_ticks=1,
        declared_sending_capacity_per_tick=2,
        declared_receiving_capacity_per_tick=2,
        declared_storage_capacity_packets=20,
        length_m=10.0,
        lane_count=1,
        free_flow_speed_mps=10.0,
        jam_density_veh_per_km_per_lane=100.0,
        backward_wave_speed_mps=5.0,
        capacity_veh_per_hour_per_lane=1200.0,
        tick_duration_seconds=1.0,
    )


def _node(node_id: str, upstream: str, downstream: tuple[str, ...]) -> Node:
    return Node(
        node_id,
        incoming_link_ids=(upstream,),
        outgoing_link_ids=downstream,
        junction_spec=JunctionSpec(
            node_id=node_id,
            incoming_link_ids=(upstream,),
            outgoing_link_ids=downstream,
            movement_specs=tuple(
                MovementSpec(upstream, link_id) for link_id in downstream
            ),
        ),
    )


def _resource_node() -> Node:
    return Node(
        "N",
        incoming_link_ids=("U",),
        outgoing_link_ids=("A", "B"),
        junction_spec=JunctionSpec(
            node_id="N",
            incoming_link_ids=("U",),
            outgoing_link_ids=("A", "B"),
            lane_group_ids=("old-lane", "new-lane"),
            conflict_resource_ids=("old-conflict", "new-conflict"),
            fifo_policy=JUNCTION_FIFO_PARTIAL_BY_MOVEMENT,
            movement_specs=(
                MovementSpec(
                    "U",
                    "A",
                    lane_group_ids=("old-lane",),
                    conflict_resource_ids=("old-conflict",),
                    signal_group_id="old-signal",
                ),
                MovementSpec(
                    "U",
                    "B",
                    lane_group_ids=("new-lane",),
                    conflict_resource_ids=("new-conflict",),
                ),
            ),
        ),
    )


def _fixture_engine() -> ExecutableRoutingLoadingEngine:
    return ExecutableRoutingLoadingEngine(
        links={link_id: _link(link_id) for link_id in ("O", "U", "A", "B", "T")},
        nodes=(
            _node("N0", "O", ("U",)),
            _node("N1", "U", ("A", "B")),
            _node("NA", "A", ("T",)),
            _node("NB", "B", ("T",)),
        ),
    )


def _instruction(
    packet_id: str,
    version: int,
    remaining_route: tuple[str, ...],
    *,
    issue_tick: int = 0,
    effective_tick: int = 0,
    instruction_id: str | None = None,
    route_start_ordinal: int = 0,
    authority_id: str = "test-authority",
) -> RoutingInstruction:
    return RoutingInstruction(
        instruction_id=instruction_id or f"instruction:test:{packet_id}:{version}",
        packet_id=packet_id,
        version=version,
        authority_id=authority_id,
        decision_artifact_id=f"artifact:test:{packet_id}:{version}",
        issue_tick=issue_tick,
        effective_tick=effective_tick,
        remaining_route=remaining_route,
        policy_id="test-policy",
        provenance=(("config_hash", "fixture-config-v1"),),
        route_start_ordinal=route_start_ordinal,
    )


def _run_fixture() -> ExecutableRoutingLoadingEngine:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    engine = _fixture_engine()
    packet = engine.instantiate(
        DemandDeclaration("D1", 0, tuple(fixture["initial_route_intent"]))
    )
    assert packet is not None
    engine.step()
    reroute = fixture["reroute"]
    engine.submit_instruction(
        RoutingInstruction(
            instruction_id=reroute["instruction_id"],
            packet_id=packet.packet_id,
            version=reroute["version"],
            authority_id=reroute["authority_id"],
            decision_artifact_id=reroute["decision_artifact_id"],
            issue_tick=reroute["issue_tick"],
            effective_tick=reroute["effective_tick"],
            remaining_route=tuple(reroute["remaining_route"]),
            policy_id=reroute["policy_id"],
            provenance=(("fixture_id", fixture["fixture_id"]),),
            route_start_ordinal=reroute["route_start_ordinal"],
        )
    )
    for _ in range(3):
        engine.step()
    terminal = fixture["terminal_instruction"]
    engine.submit_instruction(
        RoutingInstruction(
            instruction_id=terminal["instruction_id"],
            packet_id=packet.packet_id,
            version=terminal["version"],
            authority_id="fixture-authority",
            decision_artifact_id=terminal["decision_artifact_id"],
            issue_tick=engine.current_tick,
            effective_tick=0,
            remaining_route=tuple(terminal["remaining_route"]),
            policy_id=terminal["policy_id"],
            provenance=(("fixture_id", fixture["fixture_id"]),),
        )
    )
    return engine


def _run_queued_fixture() -> ExecutableRoutingLoadingEngine:
    fixture = json.loads(QUEUED_FIXTURE_PATH.read_text(encoding="utf-8"))
    engine = ExecutableRoutingLoadingEngine(
        links={link_id: _parity_link(link_id) for link_id in ("U", "A", "B")},
        nodes=(_resource_node(),),
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
    )
    packet = engine.instantiate(
        DemandDeclaration("D1", 0, tuple(fixture["initial_route_intent"]))
    )
    assert packet is not None
    engine.step()
    assert engine.packet_ids_in_queue("U", "A") == (packet.packet_id,)
    reroute = fixture["reroute"]
    engine.submit_instruction(
        RoutingInstruction(
            instruction_id=reroute["instruction_id"],
            packet_id=packet.packet_id,
            version=reroute["version"],
            authority_id="queued-fixture-authority",
            decision_artifact_id="queued-fixture-artifact:P1:1",
            issue_tick=reroute["issue_tick"],
            effective_tick=reroute["effective_tick"],
            remaining_route=tuple(reroute["remaining_route"]),
            policy_id="queued-resource-reroute",
            provenance=(("fixture_id", fixture["fixture_id"]),),
            route_start_ordinal=reroute["route_start_ordinal"],
        )
    )
    engine.set_conflict_resource_capacity("N", "old-conflict", 0)
    engine.set_lane_group_capacity("N", "old-lane", 0)
    engine.set_conflict_resource_capacity("N", "new-conflict", 0)
    engine.set_lane_group_capacity("N", "new-lane", 0)
    engine.step()
    assert engine.packet_ids_in_queue("U", "A") == ()
    assert engine.packet_ids_in_queue("U", "B") == (packet.packet_id,)
    assert engine.packet_ids_on_link("U") == (packet.packet_id,)
    engine.set_conflict_resource_capacity("N", "new-conflict", 1)
    engine.set_lane_group_capacity("N", "new-lane", 1)
    engine.step()
    return engine


def test_schema_is_frozen_and_authority_issues_linked_artifacts() -> None:
    authority = RoutingAuthority(
        RoutingAuthorityConfig("A1", "cooperative", "fixture-policy")
    )
    artifact, instruction = authority.issue_instruction(
        packet_id="P1",
        version=1,
        decision_tick=3,
        effective_tick=4,
        remaining_route=("U", "B"),
        route_start_ordinal=0,
        reason="incident-reroute",
        provenance=(("config_hash", "abc"),),
    )
    assert instruction.decision_artifact_id == artifact.artifact_id
    assert instruction.authority_id == artifact.authority_id
    assert instruction.remaining_route == artifact.proposed_remaining_route
    assert instruction.route_start_ordinal == artifact.route_start_ordinal == 0
    assert authority.instruction_decision_log == (artifact,)
    with pytest.raises(FrozenInstanceError):
        instruction.remaining_route = ("U", "A")
    with pytest.raises(ValueError, match="provenance"):
        RoutingInstruction(
            instruction_id="missing-provenance",
            packet_id="P1",
            version=2,
            authority_id="A1",
            decision_artifact_id="artifact:missing-provenance",
            issue_tick=3,
            effective_tick=3,
            remaining_route=("U", "B"),
            policy_id="test",
            provenance=(),
        )


def test_store_rejects_duplicate_and_stale_versions_explicitly() -> None:
    store = RoutingInstructionStore()
    accepted = store.record(_instruction("P1", 2, ("U", "B")), recorded_tick=0)
    duplicate_id = store.record(
        _instruction("P2", 1, ("U", "B"), instruction_id=accepted.instruction.instruction_id),
        recorded_tick=0,
    )
    duplicate_version = store.record(
        _instruction("P1", 2, ("U", "A"), instruction_id="other-id"),
        recorded_tick=0,
    )
    stale = store.record(_instruction("P1", 1, ("U", "A")), recorded_tick=0)
    terminal = store.record(
        _instruction("P1", 3, ("U", "B")),
        recorded_tick=0,
        rejection_reason=REJECTED_TERMINAL_PACKET,
    )
    assert accepted.disposition == ACCEPTED
    assert duplicate_id.reason == REJECTED_DUPLICATE_INSTRUCTION_ID
    assert duplicate_version.reason == REJECTED_DUPLICATE_VERSION
    assert stale.reason == REJECTED_STALE_VERSION
    assert terminal.reason == REJECTED_TERMINAL_PACKET
    assert terminal.instruction.packet_id == "P1"
    assert terminal.instruction.instruction_id == "instruction:test:P1:3"
    assert terminal.instruction.version == 3
    assert terminal.recorded_tick == 0
    assert terminal.instruction.issue_tick == 0
    assert terminal.instruction.effective_tick == 0
    assert terminal.instruction.decision_artifact_id == "artifact:test:P1:3"
    assert terminal.instruction.authority_id == "test-authority"
    assert len(store.history) == 5
    assert len(store.history_hash) == 64
    for record in store.history:
        assert record.record_id.startswith("instruction-receipt:")
        assert record.instruction_hash == record.instruction.instruction_hash
        assert record.participates_in_resolution == (
            record.disposition == ACCEPTED
        )

    snapshot = json.loads(json.dumps(store.to_payload(), sort_keys=True))
    replayed = RoutingInstructionStore.from_payload(snapshot)
    assert replayed.history == store.history
    assert replayed.history_hash == store.history_hash
    assert all(
        not record.participates_in_resolution
        for record in replayed.history
        if record.disposition != ACCEPTED
    )
    tampered = json.loads(json.dumps(snapshot))
    tampered["records"][-1]["participates_in_resolution"] = True
    with pytest.raises(ValueError, match="participate"):
        RoutingInstructionStore.from_payload(tampered)
    resolver = ApplicableInstructionResolver(
        link_ids=("U", "A", "B"),
        supported_transitions=(("U", "A"), ("U", "B")),
    )
    resolution = resolver.resolve(
        store=replayed,
        packet_id="P1",
        decision_tick=0,
        current_link_id="U",
        realised_route=("U",),
        original_route_intent=("U", "A"),
        allow_route_intent_adapter=False,
    )
    assert resolution.instruction_version == 2
    assert terminal.instruction.instruction_id in resolution.rejected_instruction_ids
    assert terminal.record_id in resolution.rejected_record_ids


def test_resolver_orders_issue_and_effective_ticks_without_early_application() -> None:
    store = RoutingInstructionStore()
    store.record(_instruction("P1", 0, ("U", "A")), recorded_tick=0)
    store.record(
        _instruction("P1", 1, ("U", "B"), issue_tick=0, effective_tick=2),
        recorded_tick=0,
    )
    resolver = ApplicableInstructionResolver(
        link_ids=("U", "A", "B"),
        supported_transitions=(("U", "A"), ("U", "B")),
    )
    before = resolver.resolve(
        store=store,
        packet_id="P1",
        decision_tick=1,
        current_link_id="U",
        realised_route=("U",),
        original_route_intent=("U", "A"),
    )
    after = resolver.resolve(
        store=store,
        packet_id="P1",
        decision_tick=2,
        current_link_id="U",
        realised_route=("U",),
        original_route_intent=("U", "A"),
    )
    assert before.instruction_version == 0
    assert after.instruction_version == 1
    assert after.superseded_instruction_ids == (before.instruction_id,)


def test_late_issued_instruction_becomes_applicable_at_issue_not_retroactively() -> None:
    store = RoutingInstructionStore()
    late = _instruction("P1", 1, ("U", "B"), issue_tick=3, effective_tick=1)
    store.record(late, recorded_tick=3)
    resolver = ApplicableInstructionResolver(
        link_ids=("U", "B"), supported_transitions=(("U", "B"),)
    )
    unavailable = resolver.resolve(
        store=store,
        packet_id="P1",
        decision_tick=2,
        current_link_id="U",
        realised_route=("U",),
        original_route_intent=("U", "B"),
    )
    applicable = resolver.resolve(
        store=store,
        packet_id="P1",
        decision_tick=3,
        current_link_id="U",
        realised_route=("U",),
        original_route_intent=("U", "B"),
    )
    assert unavailable.reason == INAPPLICABLE_NO_INSTRUCTION
    assert applicable.instruction_id == late.instruction_id


def test_packet_global_version_precedence_ignores_issue_order_and_authority() -> None:
    store = RoutingInstructionStore()
    lower = _instruction(
        "P1", 1, ("U", "A"), issue_tick=1, authority_id="authority-later"
    )
    higher = _instruction(
        "P1", 2, ("U", "B"), issue_tick=0, authority_id="authority-earlier"
    )
    store.record(lower, recorded_tick=1)
    store.record(higher, recorded_tick=1)
    resolver = ApplicableInstructionResolver(
        link_ids=("U", "A", "B"),
        supported_transitions=(("U", "A"), ("U", "B")),
    )
    resolution = resolver.resolve(
        store=store,
        packet_id="P1",
        decision_tick=1,
        current_link_id="U",
        realised_route=("U",),
        original_route_intent=("U", "A"),
        allow_route_intent_adapter=False,
    )
    assert resolution.instruction_id == higher.instruction_id
    assert resolution.instruction_version == 2


def test_deterministic_fixture_reroutes_without_rewriting_realised_history() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["extension_version"] == EXECUTABLE_ROUTING_EXTENSION_VERSION
    engine = _run_fixture()
    packet = engine.packets["P1"]
    assert packet.route_intent == ("O", "U", "A", "T")
    assert engine.realised_routes["P1"] == ("O", "U", "B", "T")
    assert packet.lifecycle_state == LifecycleState.COMPLETED
    movements = engine.movement_instruction_evidence
    assert tuple(
        (item.upstream_link_id, item.downstream_link_id) for item in movements
    ) == (("O", "U"), ("U", "B"), ("B", "T"))
    assert movements[0].instruction_version == 0
    assert movements[0].matches_original_route_intent is True
    assert movements[1].instruction_version == 1
    assert movements[1].matches_original_route_intent is False
    assert movements[1].superseded_instruction_ids == (
        "instruction:legacy-route-intent:P1:0",
    )
    assert engine.instruction_history[-1].reason == REJECTED_TERMINAL_PACKET
    assert engine.instruction_resolutions[-1].reason == "terminal_packet"
    assert engine.check_conservation()
    assert engine.conservation_summary()["unresolved"] == 0
    assert engine.check_event_cache_consistency()


def test_fixture_exact_replay_matches_policy_and_physical_evidence() -> None:
    first = _run_fixture()
    second = _run_fixture()
    assert first.event_log == second.event_log
    assert first.instruction_history == second.instruction_history
    assert first.instruction_resolutions == second.instruction_resolutions
    assert first.movement_instruction_evidence == second.movement_instruction_evidence
    assert first.executable_routing_evidence_hash == second.executable_routing_evidence_hash


def test_all_explicit_invalid_falls_back_to_route_intent_adapter_with_audit() -> None:
    engine = ExecutableRoutingLoadingEngine(
        links={link_id: _link(link_id) for link_id in ("U", "A")},
        nodes=(_node("N", "U", ("A",)),),
    )
    packet = engine.instantiate(DemandDeclaration("D1", 0, ("U", "A")))
    assert packet is not None
    engine.submit_instruction(_instruction(packet.packet_id, 1, ("U", "X")))
    engine.step()
    assert engine.packet_ids_on_link("A") == (packet.packet_id,)
    resolution = engine.instruction_resolutions[-1]
    assert resolution.instruction_version == 0
    assert resolution.selection_source == SELECTION_ROUTE_INTENT_ADAPTER
    assert resolution.skipped_instruction_reasons == (
        ("instruction:test:P1:1", INAPPLICABLE_UNKNOWN_LINK),
    )
    assert engine.movement_instruction_evidence[-1].skipped_instruction_reasons == (
        ("instruction:test:P1:1", INAPPLICABLE_UNKNOWN_LINK),
    )


def test_version_one_valid_version_two_invalid_selects_version_one() -> None:
    engine = ExecutableRoutingLoadingEngine(
        links={link_id: _link(link_id) for link_id in ("U", "A")},
        nodes=(_node("N", "U", ("A",)),),
        executable_routing_config=ExecutableRoutingConfig(
            compatibility_route_intent_adapter=False
        ),
    )
    packet = engine.instantiate(DemandDeclaration("D1", 0, ("U", "A")))
    assert packet is not None
    engine.submit_instruction(_instruction(packet.packet_id, 1, ("U", "A")))
    engine.submit_instruction(_instruction(packet.packet_id, 2, ("U", "X")))
    engine.step()
    resolution = engine.instruction_resolutions[-1]
    assert engine.packet_ids_on_link("A") == (packet.packet_id,)
    assert resolution.instruction_version == 1
    assert resolution.selection_source == SELECTION_EXPLICIT_INSTRUCTION
    assert resolution.skipped_instruction_reasons == (
        ("instruction:test:P1:2", INAPPLICABLE_UNKNOWN_LINK),
    )


def test_latest_valid_fallback_chain_replays_exactly() -> None:
    def run() -> ExecutableRoutingLoadingEngine:
        engine = ExecutableRoutingLoadingEngine(
            links={link_id: _link(link_id) for link_id in ("U", "A")},
            nodes=(_node("N", "U", ("A",)),),
            executable_routing_config=ExecutableRoutingConfig(
                compatibility_route_intent_adapter=False
            ),
        )
        packet = engine.instantiate(DemandDeclaration("D1", 0, ("U", "A")))
        assert packet is not None
        engine.submit_instruction(_instruction(packet.packet_id, 1, ("U", "A")))
        engine.submit_instruction(_instruction(packet.packet_id, 2, ("U", "X")))
        engine.step()
        return engine

    first = run()
    second = run()
    assert first.instruction_resolutions[-1].skipped_instruction_reasons == (
        ("instruction:test:P1:2", INAPPLICABLE_UNKNOWN_LINK),
    )
    assert first.instruction_resolutions[-1].instruction_version == 1
    assert first.event_log == second.event_log
    assert first.instruction_history == second.instruction_history
    assert first.instruction_resolutions == second.instruction_resolutions
    assert first.movement_instruction_evidence == second.movement_instruction_evidence


def test_versions_one_two_valid_version_three_invalid_selects_version_two() -> None:
    engine = ExecutableRoutingLoadingEngine(
        links={link_id: _link(link_id) for link_id in ("U", "A", "B")},
        nodes=(_node("N", "U", ("A", "B")),),
        executable_routing_config=ExecutableRoutingConfig(
            compatibility_route_intent_adapter=False
        ),
    )
    packet = engine.instantiate(DemandDeclaration("D1", 0, ("U", "A")))
    assert packet is not None
    engine.submit_instruction(_instruction(packet.packet_id, 1, ("U", "A")))
    engine.submit_instruction(_instruction(packet.packet_id, 2, ("U", "B")))
    engine.submit_instruction(_instruction(packet.packet_id, 3, ("U", "X")))
    engine.step()
    resolution = engine.instruction_resolutions[-1]
    assert engine.packet_ids_on_link("B") == (packet.packet_id,)
    assert resolution.instruction_version == 2
    assert resolution.skipped_instruction_reasons == (
        ("instruction:test:P1:3", INAPPLICABLE_UNKNOWN_LINK),
    )


def test_invalid_fifo_head_cannot_be_misclassified_as_completion_or_bypassed() -> None:
    engine = ExecutableRoutingLoadingEngine(
        links={link_id: _link(link_id) for link_id in ("U", "A")},
        nodes=(_node("N", "U", ("A",)),),
        executable_routing_config=ExecutableRoutingConfig(
            compatibility_route_intent_adapter=False
        ),
    )
    head = engine.instantiate(DemandDeclaration("D1", 0, ("U", "A")))
    follower = engine.instantiate(DemandDeclaration("D2", 0, ("U",)))
    assert head is not None and follower is not None
    engine.submit_instruction(_instruction(head.packet_id, 1, ("U", "X")))
    engine.step()
    assert engine.packet_ids_on_link("U") == (head.packet_id, follower.packet_id)
    assert engine.completed_packet_ids == frozenset()


def test_disconnected_latest_instruction_is_explicitly_inapplicable() -> None:
    engine = ExecutableRoutingLoadingEngine(
        links={link_id: _link(link_id) for link_id in ("U", "A", "B")},
        nodes=(_node("N", "U", ("A",)),),
        executable_routing_config=ExecutableRoutingConfig(
            compatibility_route_intent_adapter=False
        ),
    )
    packet = engine.instantiate(DemandDeclaration("D1", 0, ("U", "A")))
    assert packet is not None
    engine.submit_instruction(_instruction(packet.packet_id, 1, ("U", "B")))
    engine.step()
    assert engine.packet_ids_on_link("U") == (packet.packet_id,)
    assert engine.instruction_resolutions[-1].reason == (
        INAPPLICABLE_DISCONNECTED_ROUTE
    )
    assert engine.instruction_resolutions[-1].selection_source is None
    assert engine.instruction_resolutions[-1].skipped_instruction_reasons == (
        ("instruction:test:P1:1", INAPPLICABLE_DISCONNECTED_ROUTE),
    )


def test_instruction_cannot_rewrite_realised_prefix() -> None:
    engine = _fixture_engine()
    packet = engine.instantiate(DemandDeclaration("D1", 0, ("O", "U", "A", "T")))
    assert packet is not None
    engine.step()
    engine.submit_instruction(
        _instruction(packet.packet_id, 1, ("O", "A", "T"), issue_tick=1)
    )
    engine.step()
    assert engine.realised_routes[packet.packet_id] == ("O", "U", "A")
    resolution = engine.instruction_resolutions[-1]
    assert resolution.instruction_version == 0
    assert resolution.selection_source == SELECTION_ROUTE_INTENT_ADAPTER
    assert resolution.skipped_instruction_reasons == (
        ("instruction:test:P1:1", INAPPLICABLE_CURRENT_LINK_MISMATCH),
    )


def test_looping_route_uses_explicit_ordinal_not_ambiguous_current_link() -> None:
    resolver = ApplicableInstructionResolver(
        link_ids=("A", "B", "C", "D", "X"),
        supported_transitions=(
            ("A", "B"),
            ("B", "C"),
            ("C", "B"),
            ("B", "D"),
            ("B", "X"),
            ("X", "B"),
        ),
    )
    realised = ("A", "B", "C", "B")

    valid_store = RoutingInstructionStore()
    valid_store.record(
        _instruction("P1", 1, ("A", "B", "C", "B", "D")),
        recorded_tick=0,
    )
    valid = resolver.resolve(
        store=valid_store,
        packet_id="P1",
        decision_tick=0,
        current_link_id="B",
        realised_route=realised,
        original_route_intent=("A", "B", "C", "B", "D"),
        allow_route_intent_adapter=False,
    )
    assert valid.intended_next_link_id == "D"
    assert valid.remaining_route == ("B", "D")

    wrong_occurrence_store = RoutingInstructionStore()
    wrong_occurrence_store.record(
        _instruction("P1", 1, ("B", "D"), route_start_ordinal=1),
        recorded_tick=0,
    )
    wrong_occurrence = resolver.resolve(
        store=wrong_occurrence_store,
        packet_id="P1",
        decision_tick=0,
        current_link_id="B",
        realised_route=realised,
        original_route_intent=("A", "B", "C", "B", "D"),
        allow_route_intent_adapter=False,
    )
    assert wrong_occurrence.reason == "realised_prefix_mismatch"

    diverged_store = RoutingInstructionStore()
    diverged_store.record(
        _instruction("P1", 1, ("A", "B", "X", "B", "D")),
        recorded_tick=0,
    )
    diverged = resolver.resolve(
        store=diverged_store,
        packet_id="P1",
        decision_tick=0,
        current_link_id="B",
        realised_route=realised,
        original_route_intent=("A", "B", "C", "B", "D"),
        allow_route_intent_adapter=False,
    )
    assert diverged.reason == "realised_prefix_mismatch"

    aligned_suffix_store = RoutingInstructionStore()
    aligned_suffix_store.record(
        _instruction("P1", 1, ("C", "B", "D"), route_start_ordinal=2),
        recorded_tick=0,
    )
    aligned = resolver.resolve(
        store=aligned_suffix_store,
        packet_id="P1",
        decision_tick=0,
        current_link_id="B",
        realised_route=realised,
        original_route_intent=("A", "B", "C", "B", "D"),
        allow_route_intent_adapter=False,
    )
    replayed = resolver.resolve(
        store=RoutingInstructionStore.from_payload(
            json.loads(json.dumps(aligned_suffix_store.to_payload()))
        ),
        packet_id="P1",
        decision_tick=0,
        current_link_id="B",
        realised_route=realised,
        original_route_intent=("A", "B", "C", "B", "D"),
        allow_route_intent_adapter=False,
    )
    assert aligned.intended_next_link_id == "D"
    assert replayed == aligned


def test_queued_packet_rebinds_at_fifo_head_without_teleportation() -> None:
    engine = ExecutableRoutingLoadingEngine(
        links={link_id: _link(link_id) for link_id in ("U", "A", "B")},
        nodes=(_node("N", "U", ("A", "B")),),
    )
    packet = engine.instantiate(DemandDeclaration("D1", 0, ("U", "A")))
    assert packet is not None
    engine.set_receiving_open("A", False)
    engine.step()
    assert engine.packet_ids_in_queue("U", "A") == (packet.packet_id,)
    assert engine.packet_ids_on_link("U") == (packet.packet_id,)
    engine.submit_instruction(
        _instruction(packet.packet_id, 1, ("U", "B"), issue_tick=1, effective_tick=1)
    )
    assert engine.packet_ids_in_queue("U", "A") == (packet.packet_id,)
    assert engine.packet_ids_on_link("U") == (packet.packet_id,)
    engine.set_receiving_open("B", False)
    engine.step()
    assert engine.packet_ids_in_queue("U", "A") == ()
    assert engine.packet_ids_in_queue("U", "B") == (packet.packet_id,)
    assert engine.packet_ids_on_link("U") == (packet.packet_id,)
    assert not any(
        event.event_type == EventType.LINK_EXIT for event in engine.event_log
    )
    engine.set_receiving_open("B", True)
    engine.step()
    assert engine.packet_ids_on_link("B") == (packet.packet_id,)
    queue_exits = tuple(
        event for event in engine.event_log if event.event_type == EventType.QUEUE_EXIT
    )
    link_exit = next(
        event for event in engine.event_log if event.event_type == EventType.LINK_EXIT
    )
    assert tuple(event.entity_id for event in queue_exits) == (
        "boundary:U->A",
        "boundary:U->B",
    )
    assert queue_exits[0].physical_tick == 2
    assert link_exit.physical_tick == 3
    assert engine.check_event_cache_consistency()
    assert engine.check_conservation()


def test_queued_fixture_rebuilds_movement_resources_and_replays_exactly() -> None:
    fixture = json.loads(QUEUED_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["extension_version"] == EXECUTABLE_ROUTING_EXTENSION_VERSION
    first = _run_queued_fixture()
    second = _run_queued_fixture()
    assert first.packet_ids_on_link("B") == ("P1",)
    assert first.packet_ids_in_queue("U", "A") == ()
    assert first.packet_ids_in_queue("U", "B") == ()
    assert first.realised_routes["P1"] == ("U", "B")
    queue_events = tuple(
        (event.event_type, event.entity_id, event.physical_tick)
        for event in first.event_log
        if event.event_type in (EventType.QUEUE_ENTRY, EventType.QUEUE_EXIT)
    )
    assert queue_events == (
        (EventType.QUEUE_ENTRY, "boundary:U->A", 1),
        (EventType.QUEUE_EXIT, "boundary:U->A", 2),
        (EventType.QUEUE_ENTRY, "boundary:U->B", 2),
        (EventType.QUEUE_EXIT, "boundary:U->B", 3),
    )
    evidence = first.movement_instruction_evidence[-1]
    assert evidence.upstream_link_id == "U"
    assert evidence.downstream_link_id == "B"
    assert evidence.instruction_version == 1
    trace = first.node_transfer_traces()[0]
    assert trace.candidate_packet_ids == ("P1",)
    assert trace.approved_packet_ids == ("P1",)
    assert tuple(
        summary.movement_id for summary in trace.movement_flow_summaries
    ) == ("movement:U->B",)
    assert dict(trace.conflict_resource_capacity_by_id) == {
        "new-conflict": 1,
        "old-conflict": 0,
    }
    assert dict(trace.lane_group_capacity_by_id) == {
        "new-lane": 1,
        "old-lane": 0,
    }
    assert first.event_log == second.event_log
    assert first.instruction_resolutions == second.instruction_resolutions
    assert first.movement_instruction_evidence == second.movement_instruction_evidence
    assert first.check_event_cache_consistency()
    assert first.check_conservation()


def test_queued_instruction_terminating_at_current_link_completes_safely() -> None:
    def run() -> ExecutableRoutingLoadingEngine:
        engine = ExecutableRoutingLoadingEngine(
            links={link_id: _link(link_id) for link_id in ("U", "A")},
            nodes=(_node("N", "U", ("A",)),),
        )
        packet = engine.instantiate(DemandDeclaration("D1", 0, ("U", "A")))
        assert packet is not None
        engine.set_receiving_open("A", False)
        engine.step()
        assert engine.packet_ids_in_queue("U", "A") == (packet.packet_id,)
        engine.submit_instruction(
            _instruction(
                packet.packet_id,
                1,
                ("U",),
                issue_tick=1,
                effective_tick=1,
            )
        )
        assert packet.packet_id not in engine.completed_packet_ids
        assert engine.packet_ids_on_link("U") == (packet.packet_id,)
        engine.step()
        return engine

    first = run()
    second = run()
    assert first.completed_packet_ids == frozenset(("P1",))
    terminal_events = tuple(
        (event.event_type, event.entity_id, event.physical_tick)
        for event in first.event_log
        if event.event_type in (EventType.LINK_EXIT, EventType.COMPLETED)
    )
    assert terminal_events == (
        (EventType.LINK_EXIT, "U", 2),
        (EventType.COMPLETED, "U", 2),
    )
    assert first.event_log == second.event_log
    assert first.instruction_resolutions == second.instruction_resolutions
    assert first.check_event_cache_consistency()
    assert first.check_conservation()

    cancelled = ExecutableRoutingLoadingEngine(
        links={link_id: _link(link_id) for link_id in ("U", "A")},
        nodes=(_node("N", "U", ("A",)),),
    )
    packet = cancelled.instantiate(DemandDeclaration("D1", 0, ("U", "A")))
    assert packet is not None
    cancelled.cancel_packet(packet.packet_id)
    rejection = cancelled.submit_instruction(
        _instruction(packet.packet_id, 1, ("U",))
    )
    cancelled.step()
    assert rejection.reason == REJECTED_TERMINAL_PACKET
    assert rejection.participates_in_resolution is False
    restored = RoutingInstructionStore.from_payload(
        json.loads(json.dumps(cancelled.instruction_store.to_payload()))
    )
    assert restored.history == cancelled.instruction_history
    assert restored.history[-1].participates_in_resolution is False
    assert cancelled.completed_packet_ids == frozenset()
    assert cancelled.packets[packet.packet_id].lifecycle_state == LifecycleState.CANCELLED
    assert cancelled.check_conservation()


def test_compatibility_adapter_matches_legacy_physical_events() -> None:
    links = {link_id: _link(link_id) for link_id in ("U", "A")}
    nodes = (_node("N", "U", ("A",)),)
    legacy = LoadingEngine(links=links, nodes=nodes)
    extended = ExecutableRoutingLoadingEngine(links=links, nodes=nodes)
    demand = DemandDeclaration("D1", 0, ("U", "A"))
    legacy.instantiate(demand)
    extended.instantiate(demand)
    legacy.step()
    extended.step()
    legacy.step()
    extended.step()
    assert legacy.event_log == extended.event_log
    assert extended.instruction_history[0].instruction.version == 0


def test_adapter_can_be_disabled_and_terminal_cancel_rejects_instruction() -> None:
    engine = ExecutableRoutingLoadingEngine(
        links={link_id: _link(link_id) for link_id in ("U", "A")},
        nodes=(_node("N", "U", ("A",)),),
        executable_routing_config=ExecutableRoutingConfig(
            compatibility_route_intent_adapter=False
        ),
    )
    packet = engine.instantiate(DemandDeclaration("D1", 0, ("U", "A")))
    assert packet is not None
    engine.step()
    assert engine.packet_ids_on_link("U") == (packet.packet_id,)
    assert engine.instruction_resolutions[-1].reason == INAPPLICABLE_NO_INSTRUCTION
    engine.cancel_packet(packet.packet_id)
    record = engine.submit_instruction(
        _instruction(packet.packet_id, 1, ("U", "A"), issue_tick=1)
    )
    assert record.reason == REJECTED_TERMINAL_PACKET
