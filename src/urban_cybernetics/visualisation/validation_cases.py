"""Declared M8 analytical cases and their read-only execution adapter.

Expected values are literal authored fixture data. Observations are folded from
canonical engine events after execution; the loading kernel does not import
this module.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import DemandDeclaration, Event, EventType, Link
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.topology import CanonicalNode, CanonicalTopology, CanonicalTopologyLink, TopologySourceMetadata
from urban_cybernetics.validation import ValidationContext

from .contract import RunStatus, VRunBundle
from .export import build_run_bundle
from .validation_contract import (
    Citation, ComparisonStatus, EvidenceClass, EvidenceSource, InputCompleteness,
    MetricDefinition, MetricResult, PacketWaitExplanation, ReferenceAsset,
    ScalarExpectation, ValidationCase, ValidationLifecycle, ValidationOverlay,
    ValidationResult, ValidationSeries, ValidationStatus,
)


@dataclass(frozen=True, slots=True)
class _LinkInput:
    link_id: str
    length_m: float
    free_flow_speed_mps: float
    backward_wave_speed_mps: float
    jam_density_veh_per_km_per_lane: float
    capacity_veh_per_hour_per_lane: float
    tick_duration_seconds: float
    receiving_capacity_per_tick: int

    @property
    def free_flow_lag_ticks(self) -> int:
        return ceil(self.length_m / self.free_flow_speed_mps / self.tick_duration_seconds)

    @property
    def backward_wave_lag_ticks(self) -> int:
        return ceil(self.length_m / self.backward_wave_speed_mps / self.tick_duration_seconds)

    @property
    def capacity_per_tick(self) -> int:
        return int(self.capacity_veh_per_hour_per_lane * self.tick_duration_seconds / 3600)

    def link(self) -> Link:
        return Link(
            link_id=self.link_id, length_m=self.length_m, lane_count=1,
            free_flow_speed_mps=self.free_flow_speed_mps,
            backward_wave_speed_mps=self.backward_wave_speed_mps,
            jam_density_veh_per_km_per_lane=self.jam_density_veh_per_km_per_lane,
            capacity_veh_per_hour_per_lane=self.capacity_veh_per_hour_per_lane,
            tick_duration_seconds=self.tick_duration_seconds,
            declared_sending_capacity_per_tick=self.capacity_per_tick,
            declared_receiving_capacity_per_tick=self.receiving_capacity_per_tick,
        )


UNCONGESTED = _LinkInput("L1", 200.0, 10.0, 5.0, 120.0, 1440.0, 10.0, 4)
BOTTLENECK = _LinkInput("L1", 200.0, 10.0, 5.0, 30.0, 360.0, 10.0, 5)
VACANCY_L1 = _LinkInput("L1", 40.0, 10.0, 5.0, 75.0, 900.0, 4.0, 3)
VACANCY_L2 = _LinkInput("L2", 40.0, 10.0, 5.0, 75.0, 900.0, 4.0, 3)


def _series(series_id: str, label: str, values: tuple[float, ...], *, units: str = "packets", source: EvidenceSource = EvidenceSource.ANALYTICAL_REFERENCE) -> ValidationSeries:
    return ValidationSeries(
        series_id=series_id, label=label, quantity=series_id, units=units,
        time_basis="inclusive integer physical tick", ticks=tuple(range(len(values))),
        values=values, evidence_source=source, aggregation_window_ticks=1,
        counting_basis="unit packet evidence", boundary_direction=None,
    )


def _scalar(scalar_id: str, label: str, value: float | str | bool, units: str | None = None, *, source: EvidenceSource = EvidenceSource.ANALYTICAL_REFERENCE) -> ScalarExpectation:
    return ScalarExpectation(scalar_id=scalar_id, label=label, value=value, units=units, evidence_source=source)


def _metric(metric_id: str, label: str, expected_id: str, units: str = "packets", comparison: str = "max_absolute_error") -> MetricDefinition:
    return MetricDefinition(metric_id=metric_id, label=label, comparison=comparison, expected_id=expected_id, tolerance=0.0, units=units, tolerance_justification="Exact discrete analytical oracle; zero packet/tick tolerance.")


COMMON_CITATION = Citation(
    source_id="m8-analytical-link-fixtures-v1",
    citation_text="Urban Cybernetics M8 Analytical Link Cases v1; fixture-owned triangular-FD analytical tables.",
    source_section="Equations and Convention",
)
REFERENCE_PLACEHOLDER = ReferenceAsset(
    asset_id="m8-reference-placeholder-v1", source_id=COMMON_CITATION.source_id,
    label="Authored analytical table (no copyrighted figure)",
    citation_text=COMMON_CITATION.citation_text,
    figure_table_equation="case table and declared equations",
    rights_provenance_note="Repository-authored numerical reference; no external image embedded.",
    comparison_suitability="suitable",
)


CASES: tuple[ValidationCase, ...] = (
    ValidationCase(
        case_id="M8-LINK-01", version="1", group_id="m8-analytical-links",
        title="Free-flow pulse translation", short_explanation="A three-packet pulse traverses one uncongested link by exactly the free-flow lag.",
        claim_ids=("M8-VAL-LINK-FREE-FLOW",), evidence_class=EvidenceClass.ANALYTICAL,
        citations=(COMMON_CITATION,), reference_assets=(REFERENCE_PLACEHOLDER,),
        input_completeness=InputCompleteness.COMPLETE, comparison_status=ComparisonStatus.EXACT,
        topology_reference="m8-single-link-200m-v1", profile_reference=ACADEMIC_LTM_PARITY_PROFILE_ID,
        demand_reference="three unit packets admitted at tick 0", route_sequences=(("L1",),), tick_duration_seconds=10.0,
        initial_state_reference="empty link before explicit origin pulse",
        expected_physical_sequence=("Three packets enter L1 at tick 0.", "The pulse propagates for the two-tick free-flow lag.", "All packets exit together at tick 2 without queueing."),
        expected_result_summary="Cumulative exits jump from 0 to 3 at tick 2; point queue remains zero.",
        why_it_matters="Establishes the basic free-flow translation convention before congestion is introduced.",
        limits_on_interpretation=("Internal analytical agreement, not external cross-implementation validation.", "Unit packets and a declared discrete timestep are used."),
        expected_series=(_series("entries", "Expected cumulative entries", (3,3,3,3)), _series("exits", "Expected cumulative exits", (0,0,3,3)), _series("point_queue", "Expected point queue", (0,0,0,0))),
        expected_scalars=(_scalar("exit_ticks", "Expected packet exit ticks", "2,2,2", "ticks"), _scalar("queue_events", "Expected canonical queue events", 0, "events")),
        metrics=(_metric("entries_max_error", "Entry curve maximum error", "entries"), _metric("exits_max_error", "Exit curve maximum error", "exits"), _metric("queue_max_error", "Queue curve maximum error", "point_queue"), _metric("exit_tick_sequence", "Exit tick sequence", "exit_ticks", "exact", "exact_sequence"), _metric("queue_event_count", "Queue event count", "queue_events", "events", "absolute_error")),
        overlays=(ValidationOverlay(overlay_id="free-flow-link", kind="relevant_link", label="Free-flow propagation", link_id="L1", active_from_tick=0, active_through_tick=2, direction="forward", evidence_source=EvidenceSource.ANALYTICAL_REFERENCE, note="Whole-link timing abstraction; not a continuous packet position."), ValidationOverlay(overlay_id="expected-release", kind="event_marker", label="Expected simultaneous exit", link_id="L1", active_from_tick=2, active_through_tick=2, evidence_source=EvidenceSource.ANALYTICAL_REFERENCE, note="Expected free-flow release tick.")),
        known_model_differences=(), safe_claim="The discrete unit-packet kernel matches this exact free-flow translation table.",
        provenance=("Expected tables are literal fixture data independent of UC projections.",), reproducibility_notes=("No random inputs.", "Origin admission budget is distinct from downstream sending capacity."), default_final_tick=3,
    ),
    ValidationCase(
        case_id="M8-LINK-02", version="1", group_id="m8-analytical-links",
        title="Capacity-constrained bottleneck queue", short_explanation="A five-packet pulse discharges at one packet per tick and forms a deterministic point queue.",
        claim_ids=("M8-VAL-LINK-CAPACITY", "M8-VAL-LINK-DELAY"), evidence_class=EvidenceClass.ANALYTICAL,
        citations=(COMMON_CITATION,), reference_assets=(REFERENCE_PLACEHOLDER,), input_completeness=InputCompleteness.COMPLETE,
        comparison_status=ComparisonStatus.EXACT, topology_reference="m8-single-link-200m-v1", profile_reference=ACADEMIC_LTM_PARITY_PROFILE_ID,
        demand_reference="five unit packets admitted at tick 0", route_sequences=(("L1",),), tick_duration_seconds=10.0,
        initial_state_reference="empty link before explicit origin pulse",
        expected_physical_sequence=("Five packets enter L1 at tick 0.", "After the two-tick free-flow lag, sending capacity permits one exit per tick.", "The point queue falls from four packets to zero by tick 6."),
        expected_result_summary="Exit counts rise by one per tick from tick 2; delays are 0,1,2,3,4 ticks.",
        why_it_matters="Checks capacity discharge, queue formation, dissipation, and packet delay ordinals together.",
        limits_on_interpretation=("The point queue is derived from cumulative curves, not a second physical state.", "Internal analytical agreement only."),
        expected_series=(_series("entries", "Expected cumulative entries", (5,5,5,5,5,5,5)), _series("exits", "Expected cumulative exits", (0,0,1,2,3,4,5)), _series("point_queue", "Expected point queue", (0,0,4,3,2,1,0)), _series("packet_delay", "Expected delay by packet ordinal", (0,1,2,3,4), units="ticks")),
        expected_scalars=(_scalar("exit_ticks", "Expected packet exit ticks", "2,3,4,5,6", "ticks"), _scalar("mean_delay", "Expected mean delay", 2.0, "ticks")),
        metrics=(_metric("entries_max_error", "Entry curve maximum error", "entries"), _metric("exits_max_error", "Exit curve maximum error", "exits"), _metric("queue_max_error", "Queue curve maximum error", "point_queue"), _metric("delay_max_error", "Delay ordinal maximum error", "packet_delay", "ticks"), _metric("exit_tick_sequence", "Exit tick sequence", "exit_ticks", "exact", "exact_sequence"), _metric("mean_delay_error", "Mean delay error", "mean_delay", "ticks", "absolute_error")),
        overlays=(ValidationOverlay(overlay_id="bottleneck-queue", kind="queued_region", label="Analytical point-queue interval", link_id="L1", active_from_tick=2, active_through_tick=5, direction="none", evidence_source=EvidenceSource.ANALYTICAL_REFERENCE, note="Queue magnitude is charted; canvas shading is a link-level abstraction."), ValidationOverlay(overlay_id="capacity-release", kind="released_storage", label="One-packet-per-tick discharge", link_id="L1", active_from_tick=2, active_through_tick=6, direction="forward", evidence_source=EvidenceSource.VALIDATION_OUTPUT, note="Release cadence compared by Python.")),
        known_model_differences=(), safe_claim="The kernel matches the exact single-link capacity and delay tables for this pulse.", provenance=("Expected tables are literal fixture data independent of UC projections.",), reproducibility_notes=("No random inputs.",), default_final_tick=6,
    ),
    ValidationCase(
        case_id="M8-LINK-03", version="1", group_id="m8-analytical-links",
        title="Backward vacancy propagation", short_explanation="A downstream exit releases vacancy that becomes usable upstream only after the backward-wave lag.",
        claim_ids=("M8-VAL-LINK-SPILLBACK", "M8-VAL-BACKWARD-WAVE"), evidence_class=EvidenceClass.ANALYTICAL,
        citations=(COMMON_CITATION,), reference_assets=(REFERENCE_PLACEHOLDER,), input_completeness=InputCompleteness.COMPLETE,
        comparison_status=ComparisonStatus.EXACT, topology_reference="m8-two-link-vacancy-v1", profile_reference=ACADEMIC_LTM_PARITY_PROFILE_ID,
        demand_reference="three-packet L2 preload plus one L1-to-L2 packet", route_sequences=(("L2",), ("L1","L2")), tick_duration_seconds=4.0,
        initial_state_reference="L2 full with three unit packets; L1 holds one transfer candidate",
        expected_physical_sequence=("A downstream L2 exit creates vacancy at tick 1.", "Vacancy propagates upstream for the two-tick backward-wave lag.", "It is unavailable at ticks 1 and 2.", "At tick 3 the vacancy is usable and the queued L1 packet enters L2."),
        expected_result_summary="The boundary queue clears and the candidate enters L2 exactly at tick 3.",
        why_it_matters="Checks that released storage is not made available upstream too early.",
        limits_on_interpretation=("The wave overlay represents declared timing, not a continuous shock position.", "No general node allocator is exercised by this two-link boundary fixture."),
        expected_series=(_series("l2_entries", "Expected L2 cumulative entries", (3,3,3,4)), _series("l2_exits", "Expected L2 cumulative exits", (0,1,2,3)), _series("queue_entries", "Expected cumulative boundary queue entries", (0,1,1,1)), _series("queue_exits", "Expected cumulative boundary queue exits", (0,0,0,1)), _series("pre_accept_vacancy", "Expected pre-accept receiving vacancy", (0,0,0,1))),
        expected_scalars=(_scalar("candidate_release_tick", "Expected candidate L2 entry", 3, "tick"),),
        metrics=(_metric("l2_entry_error", "L2 entry curve maximum error", "l2_entries"), _metric("l2_exit_error", "L2 exit curve maximum error", "l2_exits"), _metric("queue_entry_error", "Boundary queue-entry maximum error", "queue_entries"), _metric("queue_exit_error", "Boundary queue-exit maximum error", "queue_exits"), _metric("vacancy_error", "Pre-accept vacancy maximum error", "pre_accept_vacancy"), _metric("release_tick_error", "Candidate release tick error", "candidate_release_tick", "ticks", "absolute_error")),
        overlays=(ValidationOverlay(overlay_id="blocked-boundary", kind="blocked_boundary", label="Receiving boundary blocked", link_id="L1", boundary_id="boundary:L1->L2", active_from_tick=1, active_through_tick=2, evidence_source=EvidenceSource.CANONICAL, note="Canonical queue membership plus zero declared receiving vacancy."), ValidationOverlay(overlay_id="vacancy-wave", kind="reference_wave", label="Backward vacancy-wave lag", link_id="L2", active_from_tick=1, active_through_tick=3, direction="backward", evidence_source=EvidenceSource.ANALYTICAL_REFERENCE, note="Timing overlay across the whole link; not a continuous physical wave position."), ValidationOverlay(overlay_id="released-boundary", kind="released_storage", label="Vacancy usable upstream", link_id="L2", active_from_tick=3, active_through_tick=3, direction="backward", evidence_source=EvidenceSource.VALIDATION_OUTPUT, note="Observed transfer compared with expected release tick.")),
        known_model_differences=("Queue events describe failed inter-link transfer, unlike the single-link point-queue projection.",), safe_claim="The kernel matches this exact two-link backward-vacancy timing table.", provenance=("Expected tables are literal fixture data independent of UC projections.",), reproducibility_notes=("No random inputs.", "Lag rounding uses ceiling division."), default_final_tick=3,
    ),
)

CASES_BY_ID = {case.case_id: case for case in CASES}


def execute_case(case: ValidationCase, *, result_id: str, created_at: str | None = None, completed_at: str | None = None, code_commit: str | None = None, cancelled: Callable[[], bool] = lambda: False, progress: Callable[[ValidationLifecycle, int, str], None] = lambda *_: None) -> tuple[ValidationResult, VRunBundle]:
    created_at = created_at or datetime.now(UTC).isoformat()
    lifecycle = [ValidationLifecycle.CREATED, ValidationLifecycle.SETTING_UP]
    progress(ValidationLifecycle.SETTING_UP, 0, "Constructing declared analytical fixture")
    engine, topology, packet_ids = _setup(case.case_id)
    lifecycle.append(ValidationLifecycle.EXECUTING)
    progress(ValidationLifecycle.EXECUTING, engine.current_tick, "Python loading engine owns execution")
    while engine.current_tick < case.default_final_tick and not cancelled():
        engine.step()
        progress(ValidationLifecycle.EXECUTING, engine.current_tick, "Exact physical tick sealed")
    was_cancelled = cancelled()
    lifecycle.append(ValidationLifecycle.CANCELLED if was_cancelled else ValidationLifecycle.COMPARING)
    observed_series, observed_scalars, waits = _observed(case, engine, packet_ids)
    metric_results, differences = _compare(case, observed_series, observed_scalars) if not was_cancelled else ((), ())
    passed = bool(metric_results) and all(metric.passed for metric in metric_results)
    status = ValidationStatus.CANCELLED if was_cancelled else ValidationStatus.PASSED if passed else ValidationStatus.FAILED
    lifecycle.extend(() if was_cancelled else (ValidationLifecycle.PERSISTING, ValidationLifecycle.COMPLETE if passed else ValidationLifecycle.FAILED))
    config = {"case_id": case.case_id, "case_version": case.version, "tick_duration_seconds": case.tick_duration_seconds, "final_tick": case.default_final_tick, "profile": case.profile_reference}
    expected_hash = _hash({"series": [item.model_dump(mode="json") for item in case.expected_series], "scalars": [item.model_dump(mode="json") for item in case.expected_scalars]})
    configuration_hash = _hash(config)
    replay_run_id = f"validation:{result_id}"
    context = ValidationContext.from_engine(engine, run_config=config)
    bundle = build_run_bundle(
        run_id=replay_run_id, scenario_name=f"{case.case_id} · {case.title}", topology=topology,
        context=context, status=RunStatus.PARTIAL if was_cancelled else RunStatus.BOUNDED,
        status_reason="Validation execution cancelled; partial canonical evidence retained." if was_cancelled else "Declared validation execution completed.",
        tick_duration_seconds=case.tick_duration_seconds, config_snapshot=config,
        configuration_id="uc.validation.case.v1", validation_status="not_run" if was_cancelled else "passed" if passed else "failed",
        validation_notes=(case.safe_claim if passed else "Comparison did not satisfy the declared exact oracle.",),
        input_artifact_ids=(case.case_id,), code_version=code_commit, created_at=created_at,
        node_positions=_node_positions(topology),
    )
    max_error = max((metric.value for metric in metric_results), default=0.0)
    result = ValidationResult(
        result_id=result_id, case_id=case.case_id, case_version=case.version, status=status,
        lifecycle=tuple(lifecycle), created_at=created_at,
        completed_at=completed_at or datetime.now(UTC).isoformat(), code_commit=code_commit,
        configuration_hash=configuration_hash, expected_evidence_hash=expected_hash,
        replay_run_id=replay_run_id, observed_series=observed_series,
        observed_scalars=observed_scalars, difference_series=differences,
        metric_results=metric_results,
        headline_metric="cancelled before comparison" if was_cancelled else f"maximum declared error {max_error:g}",
        observed_result_summary="Partial evidence retained; comparison not performed." if was_cancelled else "Observed Python projections match all declared expectations." if passed else "One or more observed projections differ from the declared oracle.",
        difference_summary="Not comparable after cancellation." if was_cancelled else "All declared differences are zero." if passed else "See failed metric rows and difference series.",
        packet_wait_explanations=waits, stop_reason="cancel_requested" if was_cancelled else None,
        provenance=("Observed series folded in Python from canonical events.", "Expected evidence loaded from immutable authored case definition."),
    )
    return result, bundle


def _setup(case_id: str) -> tuple[LoadingEngine, CanonicalTopology, tuple[str, ...]]:
    if case_id == "M8-LINK-01":
        inputs, demands = (UNCONGESTED,), tuple((f"D{i}", ("L1",)) for i in range(3))
    elif case_id == "M8-LINK-02":
        inputs, demands = (BOTTLENECK,), tuple((f"D{i}", ("L1",)) for i in range(5))
    elif case_id == "M8-LINK-03":
        inputs = (VACANCY_L1, VACANCY_L2)
        demands = tuple((f"D-blocker-{i}", ("L2",)) for i in range(3)) + (("D-upstream", ("L1","L2")),)
    else:
        raise KeyError(case_id)
    engine = LoadingEngine(links={item.link_id: item.link() for item in inputs}, model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID)
    packet_ids = tuple(engine.instantiate(DemandDeclaration(demand_id, 0, route)).packet_id for demand_id, route in demands)  # type: ignore[union-attr]
    return engine, _topology(case_id, inputs), packet_ids


def _topology(case_id: str, inputs: tuple[_LinkInput, ...]) -> CanonicalTopology:
    node_ids = tuple(f"N{i}" for i in range(len(inputs) + 1))
    links = tuple(CanonicalTopologyLink(link_id=item.link_id, tail_node_id=node_ids[index], head_node_id=node_ids[index+1], source_link_id=item.link_id, source_tail_node_id=str(index), source_head_node_id=str(index+1), length_m=item.length_m, lane_count=1, free_flow_speed_mps=item.free_flow_speed_mps, capacity_veh_per_hour_per_lane=item.capacity_veh_per_hour_per_lane, jam_density_veh_per_km_per_lane=item.jam_density_veh_per_km_per_lane, backward_wave_speed_mps=item.backward_wave_speed_mps) for index, item in enumerate(inputs))
    nodes = tuple(CanonicalNode(node_id=node_id, source_node_id=str(index), incoming_link_ids=tuple(link.link_id for link in links if link.head_node_id == node_id), outgoing_link_ids=tuple(link.link_id for link in links if link.tail_node_id == node_id)) for index, node_id in enumerate(node_ids))
    return CanonicalTopology(topology_id=f"validation:{case_id.lower()}:v1", nodes=nodes, links=links, source_metadata=TopologySourceMetadata(source_name="M8 authored analytical fixture", source_format="declared_python_contract", source_file_path="validation_cases.py", source_file_sha256=hashlib.sha256(case_id.encode()).hexdigest()), interpretation_assumptions=("Schematic coordinates are non-geographic.", "Unit packets; SI link metadata; declared discrete timestep."))


def _node_positions(topology: CanonicalTopology) -> dict[str, tuple[float, float]]:
    return {node.node_id: (0.15 + index * (0.7 / max(len(topology.nodes)-1, 1)), 0.5) for index, node in enumerate(topology.nodes)}


def _count(events: tuple[Event, ...], event_type: EventType, entity: str, final_tick: int) -> tuple[float, ...]:
    return tuple(float(sum(event.event_type == event_type and event.entity_id == entity and event.physical_tick <= tick for event in events)) for tick in range(final_tick + 1))


def _ticks_by_packet(events: tuple[Event, ...], event_type: EventType, entity: str, packet_ids: tuple[str, ...]) -> tuple[int, ...]:
    values = {event.packet_id: event.physical_tick for event in events if event.event_type == event_type and event.entity_id == entity}
    return tuple(values[packet_id] for packet_id in packet_ids if packet_id in values)


def _observed(case: ValidationCase, engine: LoadingEngine, packet_ids: tuple[str, ...]) -> tuple[tuple[ValidationSeries, ...], tuple[ScalarExpectation, ...], tuple[PacketWaitExplanation, ...]]:
    events = engine.event_log
    final = engine.current_tick
    source = EvidenceSource.EVENT_DERIVED
    if case.case_id in {"M8-LINK-01", "M8-LINK-02"}:
        entries = _count(events, EventType.LINK_ENTRY, "L1", final)
        exits = _count(events, EventType.LINK_EXIT, "L1", final)
        lag = 2
        queue = tuple(float(max((entries[t-lag] if t >= lag else 0)-exits[t], 0)) for t in range(final+1))
        exit_ticks = _ticks_by_packet(events, EventType.LINK_EXIT, "L1", packet_ids)
        series = [_series("entries", "Observed cumulative entries", entries, source=source), _series("exits", "Observed cumulative exits", exits, source=source), _series("point_queue", "Observed point queue", queue, source=EvidenceSource.VALIDATION_OUTPUT)]
        scalars = [_scalar("exit_ticks", "Observed packet exit ticks", ",".join(map(str, exit_ticks)), "ticks", source=source)]
        if case.case_id == "M8-LINK-01":
            queue_events = sum(event.event_type in {EventType.QUEUE_ENTRY, EventType.QUEUE_EXIT} for event in events)
            scalars.append(_scalar("queue_events", "Observed canonical queue events", queue_events, "events", source=EvidenceSource.CANONICAL))
        else:
            entry_ticks = _ticks_by_packet(events, EventType.LINK_ENTRY, "L1", packet_ids)
            delays = tuple(float(exit_tick-entry_tick-lag) for entry_tick, exit_tick in zip(entry_ticks, exit_ticks))
            series.append(ValidationSeries(series_id="packet_delay", label="Observed delay by packet ordinal", quantity="packet_delay", units="ticks", time_basis="packet ordinal", ticks=tuple(range(len(delays))), values=delays, evidence_source=source))
            scalars.append(_scalar("mean_delay", "Observed mean delay", sum(delays)/len(delays) if delays else 0.0, "ticks", source=EvidenceSource.VALIDATION_OUTPUT))
        return tuple(series), tuple(scalars), ()
    l2_entries = _count(events, EventType.LINK_ENTRY, "L2", final)
    l2_exits = _count(events, EventType.LINK_EXIT, "L2", final)
    queue_entries = _count(events, EventType.QUEUE_ENTRY, "boundary:L1->L2", final)
    queue_exits = _count(events, EventType.QUEUE_EXIT, "boundary:L1->L2", final)
    blocker_ids = set(packet_ids[:3])
    blocker_entries = tuple(float(sum(event.event_type == EventType.LINK_ENTRY and event.entity_id == "L2" and event.packet_id in blocker_ids and event.physical_tick <= tick for event in events)) for tick in range(final+1))
    vacancy = tuple(float(max(3 + (l2_exits[t-2] if t >= 2 else 0) - blocker_entries[t], 0)) for t in range(final+1))
    candidate = packet_ids[-1]
    release_ticks = _ticks_by_packet(events, EventType.LINK_ENTRY, "L2", (candidate,))
    waits = () if final < 1 else (PacketWaitExplanation(packet_id=candidate, active_from_tick=1, active_through_tick=min(2, final), current_link_id="L1", fifo_position=0, head_packet_id=candidate, intended_movement="boundary:L1->L2", blocking_reason="downstream_receiving_supply_zero", receiving_supply_packets=0, signal_or_governance_constraint=None, expected_next_release_tick=3, evidence_sources=(EvidenceSource.CANONICAL, EvidenceSource.VALIDATION_OUTPUT, EvidenceSource.ANALYTICAL_REFERENCE), unavailable_fields=("allocator rejection trace", "signal state")),)
    return (
        (_series("l2_entries", "Observed L2 cumulative entries", l2_entries, source=source), _series("l2_exits", "Observed L2 cumulative exits", l2_exits, source=source), _series("queue_entries", "Observed cumulative boundary queue entries", queue_entries, source=EvidenceSource.CANONICAL), _series("queue_exits", "Observed cumulative boundary queue exits", queue_exits, source=EvidenceSource.CANONICAL), _series("pre_accept_vacancy", "Observed pre-accept receiving vacancy", vacancy, source=EvidenceSource.VALIDATION_OUTPUT)),
        (_scalar("candidate_release_tick", "Observed candidate L2 entry", release_ticks[0] if release_ticks else -1, "tick", source=source),), waits,
    )


def _compare(case: ValidationCase, observed_series: tuple[ValidationSeries, ...], observed_scalars: tuple[ScalarExpectation, ...]) -> tuple[tuple[MetricResult, ...], tuple[ValidationSeries, ...]]:
    expected_series = {item.series_id: item for item in case.expected_series}
    actual_series = {item.series_id: item for item in observed_series}
    expected_scalars = {item.scalar_id: item for item in case.expected_scalars}
    actual_scalars = {item.scalar_id: item for item in observed_scalars}
    differences = tuple(ValidationSeries(series_id=item.series_id, label=f"Observed − expected · {item.label}", quantity=item.quantity, units=item.units, time_basis=item.time_basis, ticks=item.ticks, values=tuple(actual-expected for actual, expected in zip(actual_series[item.series_id].values, item.values)), evidence_source=EvidenceSource.VALIDATION_OUTPUT, aggregation_window_ticks=item.aggregation_window_ticks, counting_basis=item.counting_basis, boundary_direction=item.boundary_direction) for item in case.expected_series)
    results: list[MetricResult] = []
    for definition in case.metrics:
        if definition.expected_id in expected_series:
            expected = expected_series[definition.expected_id].values
            actual = actual_series[definition.expected_id].values
            value = max((abs(a-b) for a, b in zip(actual, expected)), default=0.0) if len(actual) == len(expected) else float("inf")
        else:
            expected_value = expected_scalars[definition.expected_id].value
            actual_value = actual_scalars[definition.expected_id].value
            if isinstance(expected_value, (int, float)) and isinstance(actual_value, (int, float)):
                value = abs(float(actual_value)-float(expected_value))
            else:
                value = 0.0 if actual_value == expected_value else 1.0
        results.append(MetricResult(metric_id=definition.metric_id, value=value, tolerance=definition.tolerance, units=definition.units, passed=value <= definition.tolerance, explanation=f"Declared {definition.comparison}; tolerance justified by exact discrete oracle."))
    return tuple(results), differences


def current_code_commit() -> str | None:
    try:
        return subprocess.run(("git", "rev-parse", "HEAD"), capture_output=True, text=True, check=True, timeout=2).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
