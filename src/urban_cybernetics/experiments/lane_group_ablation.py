"""Structured three-mode ablation runner for the Paper 1 lane-group extension."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Literal

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import DemandDeclaration, Link, Node
from urban_cybernetics.loading.engine import LoadingEngine
from urban_cybernetics.loading.lane_group_extension import (
    EXPLICIT_LANE_GROUP_FIFO,
    MOVEMENT_PARTIAL_FIFO,
    SHARED_LINK_FIFO,
    ExplicitLaneGroup,
    LaneGroupExtensionConfig,
    LaneGroupLoadingEngine,
)


ABLATION_RESULT_VERSION = "paper1-lane-group-ablation-v1"


@dataclass(frozen=True, slots=True)
class AblationControl:
    """One deterministic exogenous control applied before a loading tick."""

    tick: int
    control_type: Literal[
        "receiving_open",
        "signal_group_open",
        "movement_governance_open",
        "conflict_resource_capacity",
    ]
    target_id: str
    value: bool | int
    node_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tick, int) or self.tick <= 0:
            raise ValueError("control tick must be a positive int")
        if not self.target_id:
            raise ValueError("control target_id must be non-empty")


@dataclass(frozen=True, slots=True)
class RepresentationRunResult:
    """Reader-ready metrics and integrity gates for one representation mode."""

    representation_mode: str
    extension_version: str
    config_hash: str
    throughput_packets_per_tick: float
    total_queue_delay_ticks: int
    blocked_packet_count: int
    per_movement_service: tuple[tuple[str, int], ...]
    completion_time_tick: int
    completed_packet_count: int
    event_count: int
    runtime_seconds: float
    conservation_passed: bool
    replay_passed: bool
    event_cache_consistency_passed: bool
    cumulative_count_consistency_passed: bool
    terminal_packet_outcomes: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class LaneGroupAblationResult:
    """Structured comparison suitable for plotting or manuscript tables."""

    result_version: str
    demand_count: int
    max_ticks: int
    runs: tuple[RepresentationRunResult, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class _ReplayEvidence:
    event_log: tuple[object, ...]
    allocation_traces_by_tick: tuple[tuple[object, ...], ...]
    extension_traces_by_tick: tuple[tuple[object, ...], ...]
    packet_outcomes: tuple[tuple[str, str], ...]
    terminal_tick: int


def run_lane_group_ablation(
    *,
    links: dict[str, Link],
    nodes: tuple[Node, ...],
    lane_groups: tuple[ExplicitLaneGroup, ...],
    demands: tuple[DemandDeclaration, ...],
    controls: tuple[AblationControl, ...] = (),
    max_ticks: int = 100,
) -> LaneGroupAblationResult:
    """Run identical topology, demand, and controls under all three modes."""

    if not isinstance(max_ticks, int) or max_ticks <= 0:
        raise ValueError("max_ticks must be a positive int")
    if len({demand.demand_id for demand in demands}) != len(demands):
        raise ValueError("ablation demand IDs must be unique")
    runs = tuple(
        _run_mode(
            mode=mode,
            links=links,
            nodes=nodes,
            lane_groups=lane_groups,
            demands=demands,
            controls=controls,
            max_ticks=max_ticks,
        )
        for mode in (
            SHARED_LINK_FIFO,
            MOVEMENT_PARTIAL_FIFO,
            EXPLICIT_LANE_GROUP_FIFO,
        )
    )
    return LaneGroupAblationResult(
        result_version=ABLATION_RESULT_VERSION,
        demand_count=len(demands),
        max_ticks=max_ticks,
        runs=runs,
    )


def _run_mode(
    *,
    mode: str,
    links: dict[str, Link],
    nodes: tuple[Node, ...],
    lane_groups: tuple[ExplicitLaneGroup, ...],
    demands: tuple[DemandDeclaration, ...],
    controls: tuple[AblationControl, ...],
    max_ticks: int,
) -> RepresentationRunResult:
    started = perf_counter()
    engine, allocation_history, extension_history = _execute(
        mode=mode,
        links=links,
        nodes=nodes,
        lane_groups=lane_groups,
        demands=demands,
        controls=controls,
        max_ticks=max_ticks,
    )
    runtime_seconds = perf_counter() - started
    replay_engine, replay_allocations, replay_extensions = _execute(
        mode=mode,
        links=links,
        nodes=nodes,
        lane_groups=lane_groups,
        demands=demands,
        controls=controls,
        max_ticks=max_ticks,
    )
    evidence = _replay_evidence(
        engine,
        allocation_history,
        extension_history,
    )
    replay = _replay_evidence(
        replay_engine,
        replay_allocations,
        replay_extensions,
    )
    movement_service: dict[str, int] = {}
    for tick_traces in allocation_history:
        for trace in tick_traces:
            for summary in trace.movement_flow_summaries:
                movement_service[summary.movement_id] = (
                    movement_service.get(summary.movement_id, 0)
                    + summary.approved_count
                )
    queue_delay, blocked_count = _queue_metrics(allocation_history)
    completed = len(engine.completed_packet_ids)
    return RepresentationRunResult(
        representation_mode=mode,
        extension_version=engine.movement_allocator.extension_config.extension_version,
        config_hash=engine.movement_allocator.extension_config.config_hash,
        throughput_packets_per_tick=(
            completed / engine.current_tick if engine.current_tick else 0.0
        ),
        total_queue_delay_ticks=queue_delay,
        blocked_packet_count=blocked_count,
        per_movement_service=tuple(sorted(movement_service.items())),
        completion_time_tick=engine.current_tick,
        completed_packet_count=completed,
        event_count=len(engine.event_log),
        runtime_seconds=runtime_seconds,
        conservation_passed=engine.check_conservation(),
        replay_passed=evidence == replay,
        event_cache_consistency_passed=engine.check_event_cache_consistency(),
        cumulative_count_consistency_passed=(
            engine.count_consistency_report().is_consistent
        ),
        terminal_packet_outcomes=evidence.packet_outcomes,
    )


def _execute(
    *,
    mode: str,
    links: dict[str, Link],
    nodes: tuple[Node, ...],
    lane_groups: tuple[ExplicitLaneGroup, ...],
    demands: tuple[DemandDeclaration, ...],
    controls: tuple[AblationControl, ...],
    max_ticks: int,
) -> tuple[
    LoadingEngine,
    tuple[tuple[object, ...], ...],
    tuple[tuple[object, ...], ...],
]:
    config = LaneGroupExtensionConfig(
        representation_mode=mode,
        lane_groups=lane_groups,
    )
    engine = LaneGroupLoadingEngine(
        links=links,
        nodes=nodes,
        lane_group_config=config,
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
    )
    allocator = engine.lane_group_allocator
    for demand in demands:
        engine.instantiate(demand)
    controls_by_tick: dict[int, list[AblationControl]] = {}
    for control in controls:
        controls_by_tick.setdefault(control.tick, []).append(control)
    allocation_history: list[tuple[object, ...]] = []
    extension_history: list[tuple[object, ...]] = []
    while engine.current_tick < max_ticks:
        next_tick = engine.current_tick + 1
        for control in controls_by_tick.get(next_tick, ()):
            _apply_control(engine, control)
        engine.step()
        allocation_history.append(engine.node_transfer_traces())
        extension_history.append(allocator.last_lane_group_allocation_traces)
        if (
            len(engine.completed_packet_ids) == len(demands)
            and not engine.pending_demands
        ):
            break
    return engine, tuple(allocation_history), tuple(extension_history)


def _apply_control(engine: LoadingEngine, control: AblationControl) -> None:
    if control.control_type == "receiving_open":
        engine.set_receiving_open(control.target_id, bool(control.value))
    elif control.control_type == "signal_group_open":
        engine.set_signal_group_open(control.target_id, bool(control.value))
    elif control.control_type == "movement_governance_open":
        if control.node_id is None:
            raise ValueError("movement governance controls require node_id")
        engine.set_movement_governance_open(
            control.node_id,
            control.target_id,
            bool(control.value),
        )
    elif control.control_type == "conflict_resource_capacity":
        if control.node_id is None:
            raise ValueError("conflict resource controls require node_id")
        if not isinstance(control.value, int):
            raise TypeError("conflict resource capacity control must be an int")
        engine.set_conflict_resource_capacity(
            control.node_id,
            control.target_id,
            control.value,
        )
    else:  # pragma: no cover - Literal plus constructor use prevents this.
        raise ValueError(f"unsupported control_type: {control.control_type}")


def _queue_metrics(
    allocation_history: tuple[tuple[object, ...], ...],
) -> tuple[int, int]:
    """Count service-eligible rejected packet-ticks and distinct packets."""

    delay = 0
    blocked: set[str] = set()
    for tick_traces in allocation_history:
        for trace in tick_traces:
            for packet_id, reason in trace.rejected_transfer_reasons:
                if reason == "not_selected_this_tick":
                    continue
                delay += 1
                blocked.add(packet_id)
    return delay, len(blocked)


def _replay_evidence(
    engine: LoadingEngine,
    allocation_history: tuple[tuple[object, ...], ...],
    extension_history: tuple[tuple[object, ...], ...],
) -> _ReplayEvidence:
    return _ReplayEvidence(
        event_log=engine.event_log,
        allocation_traces_by_tick=allocation_history,
        extension_traces_by_tick=extension_history,
        packet_outcomes=tuple(
            sorted(
                (
                    packet_id,
                    packet.lifecycle_state.value,
                )
                for packet_id, packet in engine.packets.items()
            )
        ),
        terminal_tick=engine.current_tick,
    )
