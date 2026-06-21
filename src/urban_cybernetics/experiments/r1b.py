"""R1b receipt-delay sensitivity sweep."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from urban_cybernetics.experiments.r1a import (
    R1aAuthorityCycleResult,
    R1aExperimentRun,
    run_repeated_fresh_vs_stale_authority_experiment,
)
from urban_cybernetics.provenance import RunMetadata, RunRecorder, RunSummary


DEFAULT_STALE_DELAY_VALUES = (0, 1, 2, 3, 5)


@dataclass(frozen=True, slots=True)
class R1bAuthorityVisibleFrames:
    """Visible frame IDs for one authority in one sweep case."""

    authority_id: str
    frame_ids_by_decision_tick: tuple[tuple[int, tuple[str, ...]], ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.authority_id, "authority_id")
        object.__setattr__(
            self,
            "frame_ids_by_decision_tick",
            tuple(
                (tick, _normalise_id_tuple(frame_ids, "frame_ids"))
                for tick, frame_ids in self.frame_ids_by_decision_tick
            ),
        )


@dataclass(frozen=True, slots=True)
class R1bAuthorityRouteSequence:
    """Selected routes for one authority in one sweep case."""

    authority_id: str
    selected_routes_by_decision_tick: tuple[tuple[int, tuple[str, ...]], ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.authority_id, "authority_id")
        object.__setattr__(
            self,
            "selected_routes_by_decision_tick",
            tuple(
                (tick, tuple(route))
                for tick, route in self.selected_routes_by_decision_tick
            ),
        )


@dataclass(frozen=True, slots=True)
class R1bPacketPathSummary:
    """Realised packet path summary copied from one R1a case result."""

    packet_id: str
    authority_id: str
    decision_tick: int
    selected_route: tuple[str, ...]
    realised_path: tuple[str, ...]
    completion_tick: int | None

    def __post_init__(self) -> None:
        _require_non_empty(self.packet_id, "packet_id")
        _require_non_empty(self.authority_id, "authority_id")
        object.__setattr__(self, "selected_route", tuple(self.selected_route))
        object.__setattr__(self, "realised_path", tuple(self.realised_path))


@dataclass(frozen=True, slots=True)
class R1bCaseMetrics:
    """Simple deterministic metrics for one receipt-delay case."""

    decision_count_by_authority: tuple[tuple[str, int], ...]
    visible_frame_count_by_authority: tuple[tuple[str, int], ...]
    route_divergence_count: int
    completed_packet_count: int
    completion_ticks_by_authority: tuple[tuple[str, tuple[int, ...]], ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_count_by_authority",
            _normalise_count_pairs(
                self.decision_count_by_authority,
                "decision_count_by_authority",
            ),
        )
        object.__setattr__(
            self,
            "visible_frame_count_by_authority",
            _normalise_count_pairs(
                self.visible_frame_count_by_authority,
                "visible_frame_count_by_authority",
            ),
        )
        if self.route_divergence_count < 0:
            raise ValueError("route_divergence_count must be non-negative")
        if self.completed_packet_count < 0:
            raise ValueError("completed_packet_count must be non-negative")
        object.__setattr__(
            self,
            "completion_ticks_by_authority",
            tuple(
                (authority_id, tuple(completion_ticks))
                for authority_id, completion_ticks in self.completion_ticks_by_authority
            ),
        )


@dataclass(frozen=True, slots=True)
class R1bDelaySweepCaseResult:
    """One stale-delay case in the R1b sensitivity sweep."""

    case_result_id: str
    source_result_id: str
    stale_receipt_delay_ticks: int
    authority_ids: tuple[str, ...]
    decision_ids: tuple[str, ...]
    packet_ids: tuple[str, ...]
    visible_frames_by_authority: tuple[R1bAuthorityVisibleFrames, ...]
    selected_routes_by_authority: tuple[R1bAuthorityRouteSequence, ...]
    packet_path_summaries: tuple[R1bPacketPathSummary, ...]
    metrics: R1bCaseMetrics
    schema_version: str = "r1b.delay_sweep_case.v1"

    def __post_init__(self) -> None:
        _require_non_empty(self.case_result_id, "case_result_id")
        _require_non_empty(self.source_result_id, "source_result_id")
        if self.stale_receipt_delay_ticks < 0:
            raise ValueError("stale_receipt_delay_ticks must be non-negative")
        object.__setattr__(
            self,
            "authority_ids",
            _normalise_id_tuple(self.authority_ids, "authority_ids"),
        )
        object.__setattr__(
            self,
            "decision_ids",
            _normalise_id_tuple(self.decision_ids, "decision_ids"),
        )
        object.__setattr__(
            self,
            "packet_ids",
            _normalise_id_tuple(self.packet_ids, "packet_ids"),
        )
        object.__setattr__(
            self,
            "visible_frames_by_authority",
            tuple(self.visible_frames_by_authority),
        )
        object.__setattr__(
            self,
            "selected_routes_by_authority",
            tuple(self.selected_routes_by_authority),
        )
        object.__setattr__(
            self,
            "packet_path_summaries",
            tuple(self.packet_path_summaries),
        )


@dataclass(frozen=True, slots=True)
class R1bDelaySweepResult:
    """Focused immutable result artifact for the R1b delay sweep."""

    sweep_result_id: str
    run_id: str
    stale_delay_values: tuple[int, ...]
    case_result_ids: tuple[str, ...]
    case_results: tuple[R1bDelaySweepCaseResult, ...]
    schema_version: str = "r1b.delay_sweep_result.v1"

    def __post_init__(self) -> None:
        _require_non_empty(self.sweep_result_id, "sweep_result_id")
        _require_non_empty(self.run_id, "run_id")
        object.__setattr__(self, "stale_delay_values", tuple(self.stale_delay_values))
        if any(delay < 0 for delay in self.stale_delay_values):
            raise ValueError("stale_delay_values must be non-negative")
        object.__setattr__(
            self,
            "case_result_ids",
            _normalise_id_tuple(self.case_result_ids, "case_result_ids"),
        )
        object.__setattr__(self, "case_results", tuple(self.case_results))


@dataclass(frozen=True, slots=True)
class R1bDelaySweepRun:
    """Completed R1b sweep result plus generic P1 provenance summary."""

    result: R1bDelaySweepResult
    run_summary: RunSummary


def run_r1b_delay_sensitivity_sweep(
    *,
    run_id: str = "run:r1b:delay-sensitivity",
    stale_delay_values: tuple[int, ...] = DEFAULT_STALE_DELAY_VALUES,
    decision_ticks: tuple[int, ...] = (3, 4, 5),
) -> R1bDelaySweepRun:
    """Run the repeated authority experiment across stale receipt delays."""

    if not stale_delay_values:
        raise ValueError("stale_delay_values must be non-empty")
    if any(delay < 0 for delay in stale_delay_values):
        raise ValueError("stale_delay_values must be non-negative")

    recorder = RunRecorder(
        RunMetadata(run_id=run_id, scenario_name="R1b receipt-delay sweep")
    )
    recorder.record_config(
        {
            "experiment": "R1b receipt-delay sensitivity sweep",
            "stale_delay_values": stale_delay_values,
            "fresh_receipt_delay_ticks": 0,
            "decision_ticks": decision_ticks,
        }
    )

    case_runs = tuple(
        run_repeated_fresh_vs_stale_authority_experiment(
            run_id=f"{run_id}:case:stale-delay:{stale_delay}",
            decision_ticks=decision_ticks,
            stale_receipt_delay_ticks=stale_delay,
        )
        for stale_delay in stale_delay_values
    )
    case_results = tuple(
        _case_result(stale_delay, case_run)
        for stale_delay, case_run in zip(stale_delay_values, case_runs, strict=True)
    )
    result = R1bDelaySweepResult(
        sweep_result_id=f"result:{run_id}",
        run_id=run_id,
        stale_delay_values=tuple(stale_delay_values),
        case_result_ids=tuple(case.case_result_id for case in case_results),
        case_results=case_results,
    )

    recorder.record_output_artifact_ids(
        (
            result.sweep_result_id,
            *result.case_result_ids,
        )
    )
    recorder.record_input_artifact_ids(
        case.source_result_id for case in case_results
    )
    _record_case_artifacts(recorder, case_runs)
    summary = recorder.seal(validation_status="passed")

    return R1bDelaySweepRun(result=result, run_summary=summary)


def _case_result(
    stale_delay: int,
    case_run: R1aExperimentRun,
) -> R1bDelaySweepCaseResult:
    result = case_run.result
    return R1bDelaySweepCaseResult(
        case_result_id=f"result:{result.run_id}:r1b-case",
        source_result_id=result.result_id,
        stale_receipt_delay_ticks=stale_delay,
        authority_ids=result.authority_ids,
        decision_ids=result.decision_ids,
        packet_ids=result.packet_ids,
        visible_frames_by_authority=_visible_frames_by_authority(result.cycle_results),
        selected_routes_by_authority=_selected_routes_by_authority(
            result.cycle_results
        ),
        packet_path_summaries=_packet_path_summaries(result.cycle_results),
        metrics=_case_metrics(result.cycle_results),
    )


def _record_case_artifacts(
    recorder: RunRecorder,
    case_runs: Iterable[R1aExperimentRun],
) -> None:
    total_event_count = 0
    for case_run in case_runs:
        index = case_run.run_summary.artifact_index
        recorder.record_frames(_id_artifacts(index.frame_ids, "frame_id"))
        recorder.record_receipts(_id_artifacts(index.receipt_ids, "receipt_id"))
        recorder.record_decisions(_id_artifacts(index.decision_ids, "decision_id"))
        recorder.record_packet_ids(index.packet_ids)
        total_event_count += index.event_count
    recorder.record_event_count(total_event_count)


def _visible_frames_by_authority(
    cycles: tuple[R1aAuthorityCycleResult, ...],
) -> tuple[R1bAuthorityVisibleFrames, ...]:
    return tuple(
        R1bAuthorityVisibleFrames(
            authority_id=authority_id,
            frame_ids_by_decision_tick=tuple(
                (cycle.decision_tick, cycle.visible_frame_ids)
                for cycle in cycles
                if cycle.authority_id == authority_id
            ),
        )
        for authority_id in _authority_ids(cycles)
    )


def _selected_routes_by_authority(
    cycles: tuple[R1aAuthorityCycleResult, ...],
) -> tuple[R1bAuthorityRouteSequence, ...]:
    return tuple(
        R1bAuthorityRouteSequence(
            authority_id=authority_id,
            selected_routes_by_decision_tick=tuple(
                (cycle.decision_tick, cycle.selected_route)
                for cycle in cycles
                if cycle.authority_id == authority_id
            ),
        )
        for authority_id in _authority_ids(cycles)
    )


def _packet_path_summaries(
    cycles: tuple[R1aAuthorityCycleResult, ...],
) -> tuple[R1bPacketPathSummary, ...]:
    summaries: list[R1bPacketPathSummary] = []
    for cycle in cycles:
        for outcome in cycle.packet_outcomes:
            summaries.append(
                R1bPacketPathSummary(
                    packet_id=outcome.packet_id,
                    authority_id=cycle.authority_id,
                    decision_tick=cycle.decision_tick,
                    selected_route=outcome.selected_route,
                    realised_path=outcome.realised_path,
                    completion_tick=outcome.completion_tick,
                )
            )
    return tuple(summaries)


def _case_metrics(
    cycles: tuple[R1aAuthorityCycleResult, ...],
) -> R1bCaseMetrics:
    authority_ids = _authority_ids(cycles)
    return R1bCaseMetrics(
        decision_count_by_authority=tuple(
            (
                authority_id,
                sum(cycle.authority_id == authority_id for cycle in cycles),
            )
            for authority_id in authority_ids
        ),
        visible_frame_count_by_authority=tuple(
            (
                authority_id,
                sum(
                    len(cycle.visible_frame_ids)
                    for cycle in cycles
                    if cycle.authority_id == authority_id
                ),
            )
            for authority_id in authority_ids
        ),
        route_divergence_count=_route_divergence_count(cycles),
        completed_packet_count=sum(
            outcome.completion_tick is not None
            for cycle in cycles
            for outcome in cycle.packet_outcomes
        ),
        completion_ticks_by_authority=tuple(
            (
                authority_id,
                tuple(
                    outcome.completion_tick
                    for cycle in cycles
                    for outcome in cycle.packet_outcomes
                    if cycle.authority_id == authority_id
                    and outcome.completion_tick is not None
                ),
            )
            for authority_id in authority_ids
        ),
    )


def _route_divergence_count(cycles: tuple[R1aAuthorityCycleResult, ...]) -> int:
    fresh_routes = {
        cycle.decision_tick: cycle.selected_route
        for cycle in cycles
        if cycle.authority_id == "fresh"
    }
    stale_routes = {
        cycle.decision_tick: cycle.selected_route
        for cycle in cycles
        if cycle.authority_id == "stale"
    }
    return sum(
        fresh_routes[tick] != stale_routes[tick]
        for tick in sorted(set(fresh_routes) & set(stale_routes))
    )


def _authority_ids(cycles: tuple[R1aAuthorityCycleResult, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    authority_ids: list[str] = []
    for cycle in cycles:
        if cycle.authority_id in seen:
            continue
        seen.add(cycle.authority_id)
        authority_ids.append(cycle.authority_id)
    return tuple(authority_ids)


@dataclass(frozen=True, slots=True)
class _IdArtifact:
    artifact_id: str
    attribute_name: str

    @property
    def frame_id(self) -> str:
        return self._value_for("frame_id")

    @property
    def receipt_id(self) -> str:
        return self._value_for("receipt_id")

    @property
    def decision_id(self) -> str:
        return self._value_for("decision_id")

    def _value_for(self, attribute_name: str) -> str:
        if self.attribute_name != attribute_name:
            raise AttributeError(attribute_name)
        return self.artifact_id


def _id_artifacts(
    artifact_ids: Iterable[str],
    attribute_name: str,
) -> tuple[_IdArtifact, ...]:
    return tuple(
        _IdArtifact(artifact_id=artifact_id, attribute_name=attribute_name)
        for artifact_id in artifact_ids
    )


def _normalise_count_pairs(
    value: object,
    field_name: str,
) -> tuple[tuple[str, int], ...]:
    try:
        pairs = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError(f"{field_name} must be an iterable of pairs") from exc
    normalised: list[tuple[str, int]] = []
    for authority_id, count in pairs:
        if not isinstance(authority_id, str) or not authority_id:
            raise ValueError(f"{field_name} authority IDs must be non-empty strings")
        if not isinstance(count, int):
            raise TypeError(f"{field_name} counts must be ints")
        if count < 0:
            raise ValueError(f"{field_name} counts must be non-negative")
        normalised.append((authority_id, count))
    return tuple(normalised)


def _normalise_id_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        raise TypeError(f"{field_name} must be an iterable of string IDs, not a string")
    try:
        ids = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError(f"{field_name} must be an iterable of string IDs") from exc
    for artifact_id in ids:
        if not isinstance(artifact_id, str):
            raise TypeError(f"{field_name} must contain only string IDs")
        if not artifact_id:
            raise ValueError(f"{field_name} must not contain empty IDs")
    return ids


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must be non-empty")
