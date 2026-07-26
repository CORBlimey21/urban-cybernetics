"""Explicit consolidated validation for canonical loading-kernel runs."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from urban_cybernetics.core import EventType, LifecycleState
from urban_cybernetics.loading import LoadingEngine


@dataclass(frozen=True, slots=True)
class KernelValidationCheck:
    """One non-mutating loading-kernel validation result."""

    name: str
    passed: bool | None
    details: tuple[str, ...] = ()

    @property
    def was_run(self) -> bool:
        return self.passed is not None


@dataclass(frozen=True, slots=True)
class KernelValidationReport:
    """Structured result from the explicit post-run validation entry point."""

    current_tick: int
    event_count: int
    lifecycle_conservation: KernelValidationCheck
    event_cache_consistency: KernelValidationCheck
    cumulative_count_consistency: KernelValidationCheck
    packet_spatial_uniqueness: KernelValidationCheck
    queue_consistency: KernelValidationCheck
    event_fold_replay: KernelValidationCheck
    exact_deterministic_rerun: KernelValidationCheck

    @property
    def checks(self) -> tuple[KernelValidationCheck, ...]:
        return (
            self.lifecycle_conservation,
            self.event_cache_consistency,
            self.cumulative_count_consistency,
            self.packet_spatial_uniqueness,
            self.queue_consistency,
            self.event_fold_replay,
            self.exact_deterministic_rerun,
        )

    @property
    def is_valid(self) -> bool:
        return all(check.passed is not False for check in self.checks)


def validate_loading_kernel(
    engine: LoadingEngine,
    *,
    exact_rerun_factory: Callable[[], LoadingEngine] | None = None,
) -> KernelValidationReport:
    """Run explicit validation without adding work to ``LoadingEngine.step``.

    ``exact_rerun_factory`` is intentionally optional because reconstructing a
    complete run can be expensive. When supplied, it must build and execute the
    comparison engine through the intended terminal tick.
    """

    return KernelValidationReport(
        current_tick=engine.current_tick,
        event_count=len(engine.event_log),
        lifecycle_conservation=_boolean_check(
            "lifecycle_conservation",
            engine.check_conservation,
        ),
        event_cache_consistency=_boolean_check(
            "event_cache_consistency",
            engine.check_event_cache_consistency,
        ),
        cumulative_count_consistency=_count_consistency_check(engine),
        packet_spatial_uniqueness=_packet_spatial_uniqueness_check(engine),
        queue_consistency=_queue_consistency_check(engine),
        event_fold_replay=_event_fold_replay_check(engine),
        exact_deterministic_rerun=_exact_rerun_check(
            engine,
            exact_rerun_factory,
        ),
    )


def _boolean_check(
    name: str,
    operation: Callable[[], bool],
) -> KernelValidationCheck:
    try:
        passed = operation()
    except Exception as exc:
        return KernelValidationCheck(name, False, (_exception_detail(exc),))
    details = () if passed else (f"{name} returned false",)
    return KernelValidationCheck(name, passed, details)


def _count_consistency_check(engine: LoadingEngine) -> KernelValidationCheck:
    try:
        report = engine.count_consistency_report()
    except Exception as exc:
        return KernelValidationCheck(
            "cumulative_count_consistency",
            False,
            (_exception_detail(exc),),
        )
    return KernelValidationCheck(
        "cumulative_count_consistency",
        report.is_consistent,
        report.ineligibility_reasons,
    )


def _packet_spatial_uniqueness_check(
    engine: LoadingEngine,
) -> KernelValidationCheck:
    locations_by_packet_id: dict[str, list[str]] = {}
    for link_id in sorted(engine.links):
        for packet_id in engine.packet_ids_on_link(link_id):
            locations_by_packet_id.setdefault(packet_id, []).append(link_id)

    failures: list[str] = []
    known_packet_ids = set(engine.packets)
    for packet_id in sorted(set(locations_by_packet_id) - known_packet_ids):
        failures.append(f"unknown packet {packet_id} appears on a link")
    for packet_id, packet in sorted(engine.packets.items()):
        locations = tuple(locations_by_packet_id.get(packet_id, ()))
        expected_count = (
            1
            if packet.lifecycle_state
            in (LifecycleState.IN_TRANSIT, LifecycleState.QUEUED)
            else 0
        )
        if len(locations) != expected_count:
            failures.append(
                f"packet {packet_id} has {len(locations)} link memberships "
                f"for lifecycle {packet.lifecycle_state.value}: {locations}"
            )
    return KernelValidationCheck(
        "packet_spatial_uniqueness",
        not failures,
        tuple(failures),
    )


def _queue_consistency_check(engine: LoadingEngine) -> KernelValidationCheck:
    queues: dict[str, deque[str]] = {}
    boundary_by_packet_id: dict[str, str] = {}
    failures: list[str] = []
    for event in engine.event_log:
        if event.event_type == EventType.QUEUE_ENTRY:
            if event.packet_id in boundary_by_packet_id:
                failures.append(
                    f"packet {event.packet_id} enters more than one live queue"
                )
                continue
            queues.setdefault(event.entity_id, deque()).append(event.packet_id)
            boundary_by_packet_id[event.packet_id] = event.entity_id
        elif event.event_type == EventType.QUEUE_EXIT:
            queue = queues.setdefault(event.entity_id, deque())
            if not queue or queue[0] != event.packet_id:
                failures.append(
                    f"packet {event.packet_id} exits {event.entity_id} "
                    "without matching FIFO queue membership"
                )
                continue
            queue.popleft()
            boundary_by_packet_id.pop(event.packet_id, None)

    queued_lifecycle_packet_ids = {
        packet_id
        for packet_id, packet in engine.packets.items()
        if packet.lifecycle_state == LifecycleState.QUEUED
    }
    event_queued_packet_ids = set(boundary_by_packet_id)
    if event_queued_packet_ids != queued_lifecycle_packet_ids:
        failures.append(
            "event queue membership differs from queued lifecycle packets: "
            f"events={tuple(sorted(event_queued_packet_ids))}, "
            f"lifecycle={tuple(sorted(queued_lifecycle_packet_ids))}"
        )
    return KernelValidationCheck(
        "queue_consistency",
        not failures,
        tuple(failures),
    )


def _event_fold_replay_check(engine: LoadingEngine) -> KernelValidationCheck:
    try:
        from urban_cybernetics.visualisation.replay import build_replay_states

        final_state = build_replay_states(
            events=engine.event_log,
            packets=tuple(engine.packets.values()),
            link_ids=tuple(engine.links),
            start_tick=0,
            end_tick=engine.current_tick,
        )[-1]
        replay_packets = {
            packet.packet_id: packet for packet in final_state.packets
        }
        failures: list[str] = []
        for packet_id, packet in sorted(engine.packets.items()):
            replay_packet = replay_packets[packet_id]
            if replay_packet.status.value != packet.lifecycle_state.value:
                failures.append(
                    f"packet {packet_id} replay lifecycle "
                    f"{replay_packet.status.value} != {packet.lifecycle_state.value}"
                )
        for replay_link in final_state.links:
            live_packet_ids = engine.packet_ids_on_link(replay_link.link_id)
            if replay_link.packet_ids != live_packet_ids:
                failures.append(
                    f"link {replay_link.link_id} replay membership "
                    f"{replay_link.packet_ids} != {live_packet_ids}"
                )
    except Exception as exc:
        return KernelValidationCheck(
            "event_fold_replay",
            False,
            (_exception_detail(exc),),
        )
    return KernelValidationCheck(
        "event_fold_replay",
        not failures,
        tuple(failures),
    )


def _exact_rerun_check(
    engine: LoadingEngine,
    exact_rerun_factory: Callable[[], LoadingEngine] | None,
) -> KernelValidationCheck:
    if exact_rerun_factory is None:
        return KernelValidationCheck(
            "exact_deterministic_rerun",
            None,
            ("not requested; supply exact_rerun_factory to execute",),
        )
    try:
        rerun = exact_rerun_factory()
    except Exception as exc:
        return KernelValidationCheck(
            "exact_deterministic_rerun",
            False,
            (_exception_detail(exc),),
        )

    failures: list[str] = []
    if rerun.event_log != engine.event_log:
        failures.append("canonical event logs differ")
    if rerun.packets != engine.packets:
        failures.append("packet outcomes differ")
    if rerun.current_tick != engine.current_tick:
        failures.append(
            f"terminal ticks differ: {engine.current_tick} != {rerun.current_tick}"
        )
    return KernelValidationCheck(
        "exact_deterministic_rerun",
        not failures,
        tuple(failures),
    )


def _exception_detail(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"
