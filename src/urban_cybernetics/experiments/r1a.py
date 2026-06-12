"""R1a repeated fresh-vs-stale authority experiment."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from urban_cybernetics.core import DemandDeclaration, EventType, LifecycleState, Link, Node
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.observability import (
    LinkTraversalTimeObservationFrame,
    LinkTraversalTimeSensorConfig,
    ProbeObservabilityEngine,
)
from urban_cybernetics.provenance import RunMetadata, RunRecorder, RunSummary
from urban_cybernetics.routing import (
    AuthorityVisibilityConfig,
    AuthorityVisibleStateResolver,
    FrameReceipt,
    LowestObservedTraversalTimeRoutePolicy,
    RouteChoiceRequest,
    RouteDecision,
    RoutingAuthority,
    RoutingAuthorityConfig,
)


ROUTE_A = ("A1", "A2")
ROUTE_B = ("B1", "B2")
SENSOR_A = "probe:A1"
SENSOR_B = "probe:B1"


@dataclass(frozen=True)
class R1aPacketOutcome:
    """Realised loading outcome for one packet created from one decision."""

    packet_id: str
    demand_id: str
    decision_id: str
    selected_route: tuple[str, ...]
    realised_path: tuple[str, ...]
    completion_tick: int | None

    def __post_init__(self) -> None:
        _require_non_empty(self.packet_id, "packet_id")
        _require_non_empty(self.demand_id, "demand_id")
        _require_non_empty(self.decision_id, "decision_id")
        object.__setattr__(self, "selected_route", tuple(self.selected_route))
        object.__setattr__(self, "realised_path", tuple(self.realised_path))


@dataclass(frozen=True)
class R1aAuthorityCycleResult:
    """One authority's visible information, decision, and packet outcome."""

    cycle_index: int
    authority_id: str
    decision_tick: int
    visible_frame_ids: tuple[str, ...]
    receipt_ids: tuple[str, ...]
    decision_id: str
    selected_route: tuple[str, ...]
    packet_ids: tuple[str, ...]
    packet_outcomes: tuple[R1aPacketOutcome, ...]

    def __post_init__(self) -> None:
        if self.cycle_index < 0:
            raise ValueError("cycle_index must be non-negative")
        _require_non_empty(self.authority_id, "authority_id")
        _require_non_empty(self.decision_id, "decision_id")
        object.__setattr__(
            self,
            "visible_frame_ids",
            _normalise_id_tuple(self.visible_frame_ids, "visible_frame_ids"),
        )
        object.__setattr__(
            self,
            "receipt_ids",
            _normalise_id_tuple(self.receipt_ids, "receipt_ids"),
        )
        object.__setattr__(self, "selected_route", tuple(self.selected_route))
        object.__setattr__(
            self,
            "packet_ids",
            _normalise_id_tuple(self.packet_ids, "packet_ids"),
        )
        object.__setattr__(self, "packet_outcomes", tuple(self.packet_outcomes))


@dataclass(frozen=True)
class R1aExperimentResult:
    """Focused immutable result artifact for the repeated authority experiment."""

    result_id: str
    run_id: str
    authority_ids: tuple[str, ...]
    decision_ticks: tuple[int, ...]
    observation_frame_ids: tuple[str, ...]
    receipt_ids: tuple[str, ...]
    decision_ids: tuple[str, ...]
    packet_ids: tuple[str, ...]
    cycle_results: tuple[R1aAuthorityCycleResult, ...]
    schema_version: str = "r1a.repeated_authority_result.v1"

    def __post_init__(self) -> None:
        _require_non_empty(self.result_id, "result_id")
        _require_non_empty(self.run_id, "run_id")
        object.__setattr__(
            self,
            "authority_ids",
            _normalise_id_tuple(self.authority_ids, "authority_ids"),
        )
        object.__setattr__(self, "decision_ticks", tuple(self.decision_ticks))
        object.__setattr__(
            self,
            "observation_frame_ids",
            _normalise_id_tuple(
                self.observation_frame_ids,
                "observation_frame_ids",
            ),
        )
        object.__setattr__(
            self,
            "receipt_ids",
            _normalise_id_tuple(self.receipt_ids, "receipt_ids"),
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
        object.__setattr__(self, "cycle_results", tuple(self.cycle_results))


@dataclass(frozen=True)
class R1aExperimentRun:
    """Completed experiment result plus generic P1 provenance summary."""

    result: R1aExperimentResult
    run_summary: RunSummary


@dataclass(frozen=True)
class _PendingCycleRecord:
    cycle_index: int
    authority_id: str
    decision_tick: int
    visible_frame_ids: tuple[str, ...]
    receipt_ids: tuple[str, ...]
    decision: RouteDecision
    packet_ids: tuple[str, ...]


def run_repeated_fresh_vs_stale_authority_experiment(
    *,
    run_id: str = "run:r1a:fresh-vs-stale",
    decision_ticks: tuple[int, ...] = (3, 4, 5),
    stale_receipt_delay_ticks: int = 2,
) -> R1aExperimentRun:
    """Run the first repeated asymmetric-information experiment."""

    if not decision_ticks:
        raise ValueError("decision_ticks must be non-empty")
    if tuple(sorted(decision_ticks)) != tuple(decision_ticks):
        raise ValueError("decision_ticks must be sorted")
    if stale_receipt_delay_ticks < 0:
        raise ValueError("stale_receipt_delay_ticks must be non-negative")

    engine = _build_engine()
    _seed_background_demand(engine)
    sampler = ProbeObservabilityEngine(
        (
            LinkTraversalTimeSensorConfig(
                sensor_id=SENSOR_A,
                observed_link_id="A1",
                aggregation_window_ticks=3,
            ),
            LinkTraversalTimeSensorConfig(
                sensor_id=SENSOR_B,
                observed_link_id="B1",
                aggregation_window_ticks=3,
            ),
        )
    )
    resolver = AuthorityVisibleStateResolver(
        (
            AuthorityVisibilityConfig("fresh", receipt_delay_ticks=0),
            AuthorityVisibilityConfig(
                "stale",
                receipt_delay_ticks=stale_receipt_delay_ticks,
            ),
        )
    )
    authorities = {
        authority_id: _build_authority(authority_id)
        for authority_id in ("fresh", "stale")
    }
    recorder = RunRecorder(
        RunMetadata(run_id=run_id, scenario_name="R1a repeated fresh-vs-stale")
    )
    recorder.record_config(
        {
            "experiment": "R1a repeated fresh-vs-stale authority experiment",
            "decision_ticks": decision_ticks,
            "fresh_receipt_delay_ticks": 0,
            "stale_receipt_delay_ticks": stale_receipt_delay_ticks,
            "candidate_routes": (ROUTE_A, ROUTE_B),
            "probe_sensors": (SENSOR_A, SENSOR_B),
        }
    )

    observation_frames: list[LinkTraversalTimeObservationFrame] = []
    receipt_artifacts: list[FrameReceipt] = []
    decisions: list[RouteDecision] = []
    packet_ids: list[str] = []
    pending_cycle_records: list[_PendingCycleRecord] = []

    for cycle_index, decision_tick in enumerate(decision_ticks):
        _advance_to_tick(engine, decision_tick)
        new_frames = sampler.sample(
            events=engine.event_log,
            measurement_tick=engine.current_tick,
            link_metadata=engine.links,
        )
        observation_frames.extend(new_frames)

        for authority_id, authority in authorities.items():
            visible_frames = resolver.visible_frames(
                authority_id=authority_id,
                frames=observation_frames,
                decision_tick=engine.current_tick,
            )
            receipts = resolver.receipts_available_by(
                authority_id=authority_id,
                frames=observation_frames,
                decision_tick=engine.current_tick,
            )
            request = _build_request(
                authority_id=authority_id,
                cycle_index=cycle_index,
                departure_tick=engine.current_tick,
            )
            decision = authority.decide(
                request=request,
                frames=visible_frames,
                decision_tick=engine.current_tick,
            )
            packet = engine.instantiate(
                DemandDeclaration(
                    demand_id=decision.demand_id,
                    departure_tick=engine.current_tick,
                    route_intent=decision.selected_route,
                )
            )

            receipt_artifacts.extend(receipts)
            decisions.append(decision)
            packet_ids.append(packet.packet_id)
            pending_cycle_records.append(
                _PendingCycleRecord(
                    cycle_index=cycle_index,
                    authority_id=authority_id,
                    decision_tick=engine.current_tick,
                    visible_frame_ids=tuple(
                        frame.frame_id for frame in visible_frames
                    ),
                    receipt_ids=tuple(receipt.receipt_id for receipt in receipts),
                    decision=decision,
                    packet_ids=(packet.packet_id,),
                )
            )
        engine.step()

    _run_to_completion(engine)

    cycle_results = tuple(
        R1aAuthorityCycleResult(
            cycle_index=record.cycle_index,
            authority_id=record.authority_id,
            decision_tick=record.decision_tick,
            visible_frame_ids=record.visible_frame_ids,
            receipt_ids=record.receipt_ids,
            decision_id=record.decision.decision_id,
            selected_route=record.decision.selected_route,
            packet_ids=record.packet_ids,
            packet_outcomes=tuple(
                _packet_outcome(engine, packet_id, record.decision)
                for packet_id in record.packet_ids
            ),
        )
        for record in pending_cycle_records
    )
    result = R1aExperimentResult(
        result_id=f"result:{run_id}",
        run_id=run_id,
        authority_ids=tuple(authorities),
        decision_ticks=tuple(decision_ticks),
        observation_frame_ids=_unique_ids(
            frame.frame_id for frame in observation_frames
        ),
        receipt_ids=_unique_ids(receipt.receipt_id for receipt in receipt_artifacts),
        decision_ids=tuple(decision.decision_id for decision in decisions),
        packet_ids=tuple(packet_ids),
        cycle_results=cycle_results,
    )

    recorder.record_output_artifact_ids((result.result_id,))
    recorder.record_frames(observation_frames)
    recorder.record_receipts(_unique_receipts(receipt_artifacts))
    recorder.record_decisions(decisions)
    recorder.record_packet_ids(packet_ids)
    recorder.record_event_count(len(engine.event_log))
    summary = recorder.seal(validation_status="passed")

    return R1aExperimentRun(result=result, run_summary=summary)


def _build_engine() -> LoadingEngine:
    return LoadingEngine(
        links={
            "A1": Link(
                link_id="A1",
                free_flow_ticks=3,
                declared_sending_capacity_per_tick=10,
            ),
            "A2": Link(
                link_id="A2",
                free_flow_ticks=1,
                declared_receiving_capacity_per_tick=10,
                declared_storage_capacity_packets=20,
            ),
            "B1": Link(
                link_id="B1",
                free_flow_ticks=1,
                declared_sending_capacity_per_tick=10,
            ),
            "B2": Link(
                link_id="B2",
                free_flow_ticks=1,
                declared_receiving_capacity_per_tick=10,
                declared_storage_capacity_packets=20,
            ),
        },
        nodes=(
            Node(
                node_id="route-a-transfer",
                incoming_link_ids=("A1",),
                outgoing_link_ids=("A2",),
            ),
            Node(
                node_id="route-b-transfer",
                incoming_link_ids=("B1",),
                outgoing_link_ids=("B2",),
            ),
        ),
    )


def _seed_background_demand(engine: LoadingEngine) -> None:
    for demand_id, route in (
        ("background-route-a", ROUTE_A),
        ("background-route-b", ROUTE_B),
    ):
        engine.instantiate(
            DemandDeclaration(
                demand_id=demand_id,
                departure_tick=engine.current_tick,
                route_intent=route,
            )
        )


def _build_authority(authority_id: str) -> RoutingAuthority:
    return RoutingAuthority(
        RoutingAuthorityConfig(
            authority_id=authority_id,
            authority_type="candidate_route",
            policy_name="lowest_observed_traversal_time",
        ),
        policy=LowestObservedTraversalTimeRoutePolicy(
            {
                ROUTE_A: (SENSOR_A,),
                ROUTE_B: (SENSOR_B,),
            }
        ),
    )


def _build_request(
    *,
    authority_id: str,
    cycle_index: int,
    departure_tick: int,
) -> RouteChoiceRequest:
    demand_id = f"demand:{authority_id}:cycle:{cycle_index}"
    return RouteChoiceRequest(
        request_id=f"request:{authority_id}:cycle:{cycle_index}",
        demand_id=demand_id,
        origin_node_id="origin",
        destination_node_id="destination",
        departure_tick=departure_tick,
        candidate_routes=(ROUTE_A, ROUTE_B),
    )


def _advance_to_tick(engine: LoadingEngine, tick: int) -> None:
    if tick < engine.current_tick:
        raise ValueError("decision_ticks must not move backwards in loading time")
    while engine.current_tick < tick:
        engine.step()


def _run_to_completion(engine: LoadingEngine) -> None:
    for _ in range(20):
        if all(
            packet.lifecycle_state == LifecycleState.COMPLETED
            for packet in engine.packets.values()
        ):
            return
        engine.step()
    raise RuntimeError("R1a packets did not complete within expected horizon")


def _packet_outcome(
    engine: LoadingEngine,
    packet_id: str,
    decision: RouteDecision,
) -> R1aPacketOutcome:
    return R1aPacketOutcome(
        packet_id=packet_id,
        demand_id=decision.demand_id,
        decision_id=decision.decision_id,
        selected_route=decision.selected_route,
        realised_path=tuple(
            event.entity_id
            for event in engine.event_log
            if event.packet_id == packet_id
            and event.event_type == EventType.LINK_ENTRY
        ),
        completion_tick=_completion_tick(engine, packet_id),
    )


def _completion_tick(engine: LoadingEngine, packet_id: str) -> int | None:
    for event in engine.event_log:
        if event.packet_id == packet_id and event.event_type == EventType.COMPLETED:
            return event.physical_tick
    return None


def _unique_ids(ids: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for artifact_id in ids:
        if artifact_id in seen:
            continue
        seen.add(artifact_id)
        unique.append(artifact_id)
    return tuple(unique)


def _unique_receipts(receipts: Iterable[FrameReceipt]) -> tuple[FrameReceipt, ...]:
    receipt_by_id: dict[str, FrameReceipt] = {}
    for receipt in receipts:
        receipt_by_id.setdefault(receipt.receipt_id, receipt)
    return tuple(receipt_by_id.values())


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
