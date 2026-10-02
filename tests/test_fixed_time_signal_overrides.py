# SPDX-License-Identifier: MPL-2.0
"""Focused manual-override tests for fixed-time-signal-extension-v1."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from urban_cybernetics.core import (
    DemandDeclaration,
    EventType,
    JUNCTION_FIFO_STRICT,
    JunctionSpec,
    Link,
    MovementSpec,
    Node,
)
from urban_cybernetics.extensions import (
    CLEAR,
    FORCE_CLOSED,
    FORCE_OPEN,
    SIGNAL_OVERRIDE_REJECTED,
    TARGET_CONTROLLER,
    TARGET_SIGNAL_GROUP,
    FixedTimeControllerPlan,
    FixedTimeSignalLoadingEngine,
    FixedTimeSignalPlanEvaluator,
    FixedTimeStage,
    ResolvedFixedTimeSignalPlan,
    SignalOverrideCommand,
    SignalOverrideStore,
    SignalOverrideStoreConfig,
    SignalOverrideValidationError,
)
from urban_cybernetics.extensions.fixed_time_signal_overrides import (
    REJECTED_AFTER_TERMINAL,
    REJECTED_DUPLICATE_ID,
    REJECTED_DUPLICATE_TARGET_VERSION,
    REJECTED_EFFECTIVE_AFTER_TERMINAL,
    REJECTED_INVALID_CLEAR_REFERENCE,
    REJECTED_RECEIPT_PRECEDES_ISSUE,
    REJECTED_UNKNOWN_TARGET,
)


MOVEMENT_A = "movement:UA->OA"
MOVEMENT_B = "movement:UB->OB"
CONTROLLER_ID = "controller:N"
SIGNAL_A = "signal:A"
SIGNAL_B = "signal:B"


def _link(link_id: str, *, receiving: int = 2) -> Link:
    return Link(
        link_id=link_id,
        free_flow_ticks=1,
        declared_sending_capacity_per_tick=2,
        declared_receiving_capacity_per_tick=receiving,
        declared_storage_capacity_packets=20,
    )


def _node() -> Node:
    return Node(
        "N",
        ("UA", "UB"),
        ("OA", "OB"),
        junction_spec=JunctionSpec(
            "N",
            ("UA", "UB"),
            ("OA", "OB"),
            movement_specs=(
                MovementSpec("UA", "OA", signal_group_id=SIGNAL_A),
                MovementSpec("UB", "OB", signal_group_id=SIGNAL_B),
            ),
        ),
    )


def _plan() -> ResolvedFixedTimeSignalPlan:
    return ResolvedFixedTimeSignalPlan(
        (
            FixedTimeControllerPlan(
                CONTROLLER_ID,
                "N",
                6,
                0,
                (
                    FixedTimeStage("stage:A", 2, (MOVEMENT_A,)),
                    FixedTimeStage("stage:clear:A-B", 1, ()),
                    FixedTimeStage("stage:B", 2, (MOVEMENT_B,)),
                    FixedTimeStage("stage:clear:B-A", 1, ()),
                ),
                (MOVEMENT_A, MOVEMENT_B),
            ),
        )
    )


def _engine() -> FixedTimeSignalLoadingEngine:
    node = _node()
    return FixedTimeSignalLoadingEngine(
        links={
            link_id: _link(link_id)
            for link_id in ("UA", "UB", "OA", "OB")
        },
        nodes=(node,),
        fixed_time_signal_provider=FixedTimeSignalPlanEvaluator(_plan(), (node,)),
    )


def _command(
    override_id: str,
    action: str,
    *,
    target_kind: str = TARGET_SIGNAL_GROUP,
    target_id: str = SIGNAL_A,
    issue_tick: int = 0,
    effective_tick: int = 1,
    expiry_tick: int | None = None,
    priority: int = 0,
    version: int = 0,
    withdrawn_override_ids: tuple[str, ...] = (),
) -> SignalOverrideCommand:
    return SignalOverrideCommand(
        override_id=override_id,
        target_kind=target_kind,
        target_id=target_id,
        action=action,
        actor_id="operator:test",
        issue_tick=issue_tick,
        effective_tick=effective_tick,
        expiry_tick=expiry_tick,
        priority=priority,
        version=version,
        reason_code="test-intervention",
        withdrawn_override_ids=withdrawn_override_ids,
        metadata=(("policy", "manual-test-v1"),),
    )


def _entries(
    engine: FixedTimeSignalLoadingEngine,
    link_id: str,
    tick: int,
) -> tuple[str, ...]:
    return tuple(
        event.packet_id
        for event in engine.event_log
        if event.event_type == EventType.LINK_ENTRY
        and event.entity_id == link_id
        and event.physical_tick == tick
    )


def test_force_closed_overrides_planned_green_and_queues_upstream() -> None:
    engine = _engine()
    packet = engine.instantiate(DemandDeclaration("A", 0, ("UA", "OA")))
    receipt = engine.submit_signal_override(
        _command("override:close-A", FORCE_CLOSED)
    )
    assert receipt.participates_in_resolution
    engine.step()
    assert packet is not None
    assert _entries(engine, "OA", 1) == ()
    assert engine.packet_ids_in_queue("UA", "OA") == (packet.packet_id,)
    evidence = engine.fixed_time_signal_evidence[-1]
    assert evidence.tick == 1
    assert evidence.baseline_is_open is True
    assert evidence.considered_override_ids == ("override:close-A",)
    assert evidence.selected_override_id == "override:close-A"
    assert evidence.selected_override_action == FORCE_CLOSED
    assert evidence.effective_is_open is False
    assert len(evidence.plan_hash) == 64
    assert len(evidence.override_store_config_hash) == 64
    assert len(evidence.override_store_hash) == 64


def test_force_open_overrides_planned_red() -> None:
    engine = _engine()
    packet = engine.instantiate(DemandDeclaration("B", 0, ("UB", "OB")))
    engine.submit_signal_override(
        _command(
            "override:open-B",
            FORCE_OPEN,
            target_id=SIGNAL_B,
        )
    )
    engine.step()
    assert packet is not None
    assert _entries(engine, "OB", 1) == (packet.packet_id,)
    evidence = engine.fixed_time_signal_evidence[-1]
    assert evidence.baseline_is_open is False
    assert evidence.effective_is_open is True


def test_force_open_does_not_bypass_closed_receiving_supply() -> None:
    engine = _engine()
    packet = engine.instantiate(DemandDeclaration("B", 0, ("UB", "OB")))
    engine.set_receiving_open("OB", False)
    engine.submit_signal_override(
        _command("override:open-B", FORCE_OPEN, target_id=SIGNAL_B)
    )
    engine.step()
    assert packet is not None
    assert _entries(engine, "OB", 1) == ()
    assert engine.packet_ids_in_queue("UB", "OB") == (packet.packet_id,)
    assert engine.fixed_time_signal_evidence[-1].effective_is_open is True


def test_force_open_does_not_bypass_strict_fifo() -> None:
    movement_a = "movement:U->A"
    movement_b = "movement:U->B"
    node = Node(
        "N",
        ("U",),
        ("A", "B"),
        junction_spec=JunctionSpec(
            "N",
            ("U",),
            ("A", "B"),
            fifo_policy=JUNCTION_FIFO_STRICT,
            movement_specs=(
                MovementSpec("U", "A", signal_group_id=SIGNAL_A),
                MovementSpec("U", "B", signal_group_id=SIGNAL_B),
            ),
        ),
    )
    plan = ResolvedFixedTimeSignalPlan(
        (
            FixedTimeControllerPlan(
                CONTROLLER_ID,
                "N",
                3,
                0,
                (
                    FixedTimeStage("stage:fifo:A", 2, (movement_a,)),
                    FixedTimeStage("stage:fifo:B", 1, (movement_b,)),
                ),
                (movement_a, movement_b),
            ),
        )
    )
    engine = FixedTimeSignalLoadingEngine(
        links={key: _link(key) for key in ("U", "A", "B")},
        nodes=(node,),
        fixed_time_signal_provider=FixedTimeSignalPlanEvaluator(plan, (node,)),
    )
    head = engine.instantiate(DemandDeclaration("head", 0, ("U", "A")))
    tail = engine.instantiate(DemandDeclaration("tail", 0, ("U", "B")))
    engine.set_receiving_open("A", False)
    engine.submit_signal_override(
        _command("override:open-B", FORCE_OPEN, target_id=SIGNAL_B)
    )
    engine.step()
    assert head is not None and tail is not None
    assert _entries(engine, "B", 1) == ()
    assert tail.packet_id in engine.packet_ids_on_link("U")
    assert engine.packet_ids_in_queue("U", "A") == (head.packet_id,)


def test_tick_zero_override_query_uses_the_same_untranslated_clock() -> None:
    engine = _engine()
    receipt = engine.submit_signal_override(
        _command(
            "override:tick-zero-close",
            FORCE_CLOSED,
            effective_tick=0,
        )
    )
    assert receipt.recorded_tick == receipt.command.issue_tick == 0
    state = engine.signal_gate_state(MOVEMENT_A, 0)
    assert state.tick == 0
    assert state.cycle_position == 0
    assert state.baseline_is_open is True
    assert state.selected_override_id == "override:tick-zero-close"
    assert state.effective_is_open is False


def test_expiry_and_future_effective_ticks_return_to_baseline_exactly() -> None:
    engine = _engine()
    engine.submit_signal_override(
        _command(
            "override:future-close-B",
            FORCE_CLOSED,
            target_id=SIGNAL_B,
            effective_tick=3,
            expiry_tick=4,
        )
    )
    before = engine.signal_gate_state(MOVEMENT_B, 1)
    active = engine.signal_gate_state(MOVEMENT_B, 3)
    expired = engine.signal_gate_state(MOVEMENT_B, 4)
    assert before.baseline_is_open is before.effective_is_open is False
    assert before.considered_override_ids == ()
    assert active.baseline_is_open is True
    assert active.effective_is_open is False
    assert active.selected_override_id == "override:future-close-B"
    assert expired.selected_override_id is None
    assert expired.considered_override_ids == ()
    assert expired.effective_is_open is expired.baseline_is_open is True


def test_explicit_clear_withdraws_force_and_returns_to_baseline() -> None:
    engine = _engine()
    engine.submit_signal_override(
        _command("override:close-A", FORCE_CLOSED, effective_tick=1, version=0)
    )
    engine.submit_signal_override(
        _command(
            "override:clear-close-A",
            CLEAR,
            effective_tick=2,
            version=1,
            withdrawn_override_ids=("override:close-A",),
        )
    )
    forced = engine.signal_gate_state(MOVEMENT_A, 1)
    cleared = engine.signal_gate_state(MOVEMENT_A, 6)
    assert forced.effective_is_open is False
    assert forced.selected_override_id == "override:close-A"
    assert cleared.baseline_is_open is cleared.effective_is_open is True
    assert cleared.selected_override_id is None
    assert cleared.cleared_override_ids == ("override:close-A",)
    assert cleared.considered_override_ids == (
        "override:clear-close-A",
        "override:close-A",
    )


def test_precedence_is_specificity_then_priority_then_version() -> None:
    engine = _engine()
    commands = (
        _command(
            "override:controller-close",
            FORCE_CLOSED,
            target_kind=TARGET_CONTROLLER,
            target_id=CONTROLLER_ID,
            priority=100,
            version=0,
        ),
        _command(
            "override:group-open-v0",
            FORCE_OPEN,
            priority=0,
            version=0,
        ),
        _command(
            "override:group-close-v1",
            FORCE_CLOSED,
            priority=1,
            version=1,
        ),
        _command(
            "override:group-open-v2",
            FORCE_OPEN,
            priority=1,
            version=2,
        ),
    )
    for command in commands:
        assert engine.submit_signal_override(command).participates_in_resolution
    state = engine.signal_gate_state(MOVEMENT_A, 1)
    assert state.selected_override_id == "override:group-open-v2"
    assert state.selected_override_target_kind == TARGET_SIGNAL_GROUP
    assert state.effective_is_open is True
    higher_priority = _command(
        "override:group-close-high",
        FORCE_CLOSED,
        priority=2,
        version=3,
    )
    engine.submit_signal_override(higher_priority)
    state = engine.signal_gate_state(MOVEMENT_A, 1)
    assert state.selected_override_id == "override:group-close-high"
    assert state.effective_is_open is False


def test_equal_precedence_contradiction_is_rejected_explicitly() -> None:
    engine = _engine()
    accepted = engine.submit_signal_override(
        _command("override:open", FORCE_OPEN, priority=5, version=7)
    )
    rejected = engine.submit_signal_override(
        _command("override:closed", FORCE_CLOSED, priority=5, version=7)
    )
    assert accepted.participates_in_resolution
    assert rejected.disposition == SIGNAL_OVERRIDE_REJECTED
    assert rejected.reason == REJECTED_DUPLICATE_TARGET_VERSION
    assert rejected.participates_in_resolution is False
    state = engine.signal_gate_state(MOVEMENT_A, 1)
    assert state.selected_override_id == "override:open"
    assert "override:closed" not in state.considered_override_ids


def test_rejections_duplicates_unknown_targets_terminal_and_clear_references() -> None:
    store = SignalOverrideStore(
        controller_ids=(CONTROLLER_ID,),
        signal_group_ids=(SIGNAL_A,),
        config=SignalOverrideStoreConfig(terminal_tick=2),
    )
    accepted = store.submit(
        _command("override:accepted", FORCE_OPEN),
        recorded_tick=0,
    )
    duplicate = store.submit(
        replace(accepted.command, action=FORCE_CLOSED),
        recorded_tick=0,
    )
    unknown = store.submit(
        _command(
            "override:unknown",
            FORCE_OPEN,
            target_id="signal:missing",
        ),
        recorded_tick=0,
    )
    terminal = store.submit(
        _command(
            "override:late",
            FORCE_OPEN,
            issue_tick=3,
            effective_tick=3,
            version=1,
        ),
        recorded_tick=3,
    )
    beyond = store.submit(
        _command(
            "override:beyond",
            FORCE_OPEN,
            effective_tick=3,
            version=2,
        ),
        recorded_tick=0,
    )
    bad_clear = store.submit(
        _command(
            "override:bad-clear",
            CLEAR,
            version=3,
            withdrawn_override_ids=("override:missing",),
        ),
        recorded_tick=0,
    )
    premature = store.submit(
        _command(
            "override:premature-receipt",
            FORCE_OPEN,
            issue_tick=1,
            effective_tick=1,
            version=4,
        ),
        recorded_tick=0,
    )
    assert duplicate.reason == REJECTED_DUPLICATE_ID
    assert unknown.reason == REJECTED_UNKNOWN_TARGET
    assert terminal.reason == REJECTED_AFTER_TERMINAL
    assert beyond.reason == REJECTED_EFFECTIVE_AFTER_TERMINAL
    assert bad_clear.reason == REJECTED_INVALID_CLEAR_REFERENCE
    assert premature.reason == REJECTED_RECEIPT_PRECEDES_ISSUE
    assert all(
        not item.participates_in_resolution
        for item in (
            duplicate,
            unknown,
            terminal,
            beyond,
            bad_clear,
            premature,
        )
    )


def test_rejected_receipts_remain_nonparticipating_after_round_trip() -> None:
    store = SignalOverrideStore(
        controller_ids=(CONTROLLER_ID,),
        signal_group_ids=(SIGNAL_A,),
    )
    store.submit(_command("override:open", FORCE_OPEN), recorded_tick=0)
    rejected = store.submit(
        _command("override:conflict", FORCE_CLOSED, version=0),
        recorded_tick=0,
    )
    assert not rejected.participates_in_resolution
    snapshot = json.loads(json.dumps(store.to_snapshot(), sort_keys=True))
    restored = SignalOverrideStore.from_snapshot(snapshot)
    assert restored.history == store.history
    assert restored.store_hash == store.store_hash
    assert restored.history[-1].reason == REJECTED_DUPLICATE_TARGET_VERSION
    assert not restored.history[-1].participates_in_resolution
    resolution = restored.resolve(
        controller_id=CONTROLLER_ID,
        signal_group_id=SIGNAL_A,
        tick=1,
        baseline_is_open=True,
    )
    assert resolution.considered_override_ids == ("override:open",)


def test_malformed_commands_and_corrupt_snapshots_are_rejected() -> None:
    with pytest.raises(SignalOverrideValidationError, match="cannot precede"):
        _command(
            "override:malformed",
            FORCE_OPEN,
            issue_tick=2,
            effective_tick=1,
        )
    with pytest.raises(SignalOverrideValidationError, match="explicit"):
        _command("override:empty-clear", CLEAR)
    command = _command("override:hash", FORCE_OPEN)
    payload = command.to_dict()
    payload["command_hash"] = "0" * 64
    with pytest.raises(SignalOverrideValidationError, match="hash mismatch"):
        SignalOverrideCommand.from_dict(payload)


def _run_override_replay() -> FixedTimeSignalLoadingEngine:
    engine = _engine()
    packet_a = engine.instantiate(DemandDeclaration("A", 0, ("UA", "OA")))
    packet_b = engine.instantiate(DemandDeclaration("B", 0, ("UB", "OB")))
    assert packet_a is not None and packet_b is not None
    engine.submit_signal_override(
        _command("override:close-A", FORCE_CLOSED, expiry_tick=2)
    )
    engine.submit_signal_override(
        _command("override:open-B", FORCE_OPEN, target_id=SIGNAL_B)
    )
    engine.step()
    engine.step()
    engine.step()
    engine.step()
    assert engine.check_conservation()
    return engine


def test_override_execution_replays_evidence_queues_events_and_conservation() -> None:
    first = _run_override_replay()
    second = _run_override_replay()
    assert first.signal_override_receipts == second.signal_override_receipts
    assert first.fixed_time_signal_evidence == second.fixed_time_signal_evidence
    assert (
        first.fixed_time_signal_evidence_hash
        == second.fixed_time_signal_evidence_hash
    )
    assert first.event_log == second.event_log
    assert first.conservation_summary() == second.conservation_summary()
    assert first.check_conservation() and second.check_conservation()


def test_plan_controlled_groups_reject_unaudited_legacy_manual_gate() -> None:
    engine = _engine()
    with pytest.raises(ValueError, match="submit_signal_override"):
        engine.set_signal_group_open(SIGNAL_A, True)
