# SPDX-License-Identifier: MPL-2.0
"""Explicit, thread-safe V2 run lifecycle state machine."""

from __future__ import annotations

from datetime import UTC, datetime
from threading import RLock

from .v2_contract import LifecycleTransition, RunLifecycleState


class IllegalLifecycleTransition(RuntimeError):
    pass


LEGAL_TRANSITIONS: dict[RunLifecycleState, frozenset[RunLifecycleState]] = {
    RunLifecycleState.CREATED: frozenset({RunLifecycleState.RESOLVING, RunLifecycleState.FAILED}),
    RunLifecycleState.RESOLVING: frozenset({RunLifecycleState.SETTING_UP, RunLifecycleState.FAILED}),
    RunLifecycleState.SETTING_UP: frozenset({RunLifecycleState.RUNNING, RunLifecycleState.CANCEL_REQUESTED, RunLifecycleState.FAILED}),
    RunLifecycleState.RUNNING: frozenset({RunLifecycleState.PAUSE_REQUESTED, RunLifecycleState.CANCEL_REQUESTED, RunLifecycleState.FINALISING, RunLifecycleState.TIMED_OUT, RunLifecycleState.FAILED}),
    RunLifecycleState.PAUSE_REQUESTED: frozenset({RunLifecycleState.PAUSED, RunLifecycleState.CANCEL_REQUESTED, RunLifecycleState.FAILED}),
    RunLifecycleState.PAUSED: frozenset({RunLifecycleState.RESUME_REQUESTED, RunLifecycleState.CANCEL_REQUESTED, RunLifecycleState.FAILED}),
    RunLifecycleState.RESUME_REQUESTED: frozenset({RunLifecycleState.RUNNING, RunLifecycleState.CANCEL_REQUESTED, RunLifecycleState.FAILED}),
    RunLifecycleState.CANCEL_REQUESTED: frozenset({RunLifecycleState.FINALISING, RunLifecycleState.FAILED}),
    RunLifecycleState.FINALISING: frozenset({RunLifecycleState.VALIDATING, RunLifecycleState.CANCELLED, RunLifecycleState.TIMED_OUT, RunLifecycleState.FAILED}),
    RunLifecycleState.VALIDATING: frozenset({RunLifecycleState.COMPLETE, RunLifecycleState.CANCELLED, RunLifecycleState.TIMED_OUT, RunLifecycleState.FAILED}),
    RunLifecycleState.COMPLETE: frozenset(),
    RunLifecycleState.CANCELLED: frozenset(),
    RunLifecycleState.TIMED_OUT: frozenset(),
    RunLifecycleState.FAILED: frozenset(),
}


class RunLifecycle:
    def __init__(self) -> None:
        self._lock = RLock()
        self._state = RunLifecycleState.CREATED
        self._history = [LifecycleTransition(sequence=0, occurred_at=datetime.now(UTC), previous_state=None, state=self._state, reason="run accepted")]

    @property
    def state(self) -> RunLifecycleState:
        with self._lock:
            return self._state

    @property
    def history(self) -> tuple[LifecycleTransition, ...]:
        with self._lock:
            return tuple(self._history)

    def transition(self, state: RunLifecycleState, reason: str) -> LifecycleTransition:
        with self._lock:
            if state not in LEGAL_TRANSITIONS[self._state]:
                raise IllegalLifecycleTransition(f"illegal lifecycle transition {self._state} -> {state}")
            previous = self._state
            self._state = state
            transition = LifecycleTransition(sequence=len(self._history), occurred_at=datetime.now(UTC), previous_state=previous, state=state, reason=reason)
            self._history.append(transition)
            return transition
