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
from math import ceil, floor

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import DemandDeclaration, Event, EventType, Link, Node
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.topology import CanonicalNode, CanonicalTopology, CanonicalTopologyLink, TopologySourceMetadata
from urban_cybernetics.validation import ValidationContext
from urban_cybernetics.validation.physical import assess_physical_parameter_eligibility

from .contract import RunStatus, VRunBundle
from .export import build_run_bundle
from .validation_contract import (
    Citation, ComparisonStatus, EvidenceClass, EvidenceSource, InputCompleteness,
    MetricDefinition, MetricResult, PacketWaitExplanation, ReferenceAsset,
    ScalarExpectation, ValidationCase, ValidationLifecycle, ValidationOverlay,
    ValidationResult, ValidationSeries, ValidationStatus,
)
from .v2_contract import MovementAllocationEvidence, MovementFlowEvidence


DESOUZA_FIGURE5_SOURCE_SHA256 = (
    "ae898b06f336e78b17d53edab7326cd1346863ff3328cdf86952886852a0c903"
)
DESOUZA_FIGURE5_CASE_PREFIX = "M8-PUB-DSOUZA-FIG5-DT"


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
    sending_rate_per_tick: float | None = None

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
SUSTAINED_FREE_FLOW = _LinkInput("L1", 200.0, 10.0, 5.0, 60.0, 720.0, 10.0, 2)
QUEUE_GROWTH = _LinkInput("L1", 200.0, 10.0, 5.0, 30.0, 360.0, 10.0, 2)
FRACTIONAL_SENDING = _LinkInput("L1", 20.0, 10.0, 5.0, 450.0, 5400.0, 1.0, 6, 1.5)
NODE_UPSTREAM = _LinkInput("L1", 10.0, 10.0, 5.0, 1800.0, 21600.0, 1.0, 6)


def _desouza_inputs(tick_duration_seconds: float) -> tuple[_LinkInput, _LinkInput]:
    return (
        _LinkInput(
            "L1", 150.0, 30.0, 6.0, 200.0, 3600.0,
            tick_duration_seconds, floor(1.0 * tick_duration_seconds),
            1.0 * tick_duration_seconds,
        ),
        _LinkInput(
            "L2", 150.0, 30.0, 6.0, 100.0, 1800.0,
            tick_duration_seconds, floor(0.5 * tick_duration_seconds),
            0.5 * tick_duration_seconds,
        ),
    )


DESOUZA_INPUTS_BY_TIMESTEP = {
    timestep: _desouza_inputs(timestep) for timestep in (1.0, 3.0, 6.0)
}


@dataclass(frozen=True, slots=True)
class _TickEvidence:
    candidate_count: int = 0
    approval_count: int = 0
    rejection_count: int = 0
    receiving_supply: int = 0
    sending_budget: int = 0
    sending_carry: float = 0.0
    sending_budget_by_link: tuple[tuple[str, int], ...] = ()
    sending_carry_by_link: tuple[tuple[str, float], ...] = ()
    receiving_budget_by_link: tuple[tuple[str, int], ...] = ()
    receiving_carry_by_link: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class _NodeCaseSpec:
    case_id: str
    title: str
    demand: int
    receiving_supply: int
    final_tick: int
    candidates: tuple[float, ...]
    approvals: tuple[float, ...]
    rejections: tuple[float, ...]
    receiving: tuple[float, ...]
    cumulative_transfers: tuple[float, ...]
    boundary_queue: tuple[float, ...]
    transfer_ticks: str
    initial_closed: bool = False
    reopen_tick: int | None = None
    fractional_receiving_rate: float | None = None


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

DESOUZA_CITATION = Citation(
    source_id="desouza-packetised-ltm-preprint-2025",
    citation_text=(
        "Felipe de Souza, Omer Verbas, Joshua Auld, and Chris M.J. Tampere, "
        "A Mesoscopic Link-Transmission-Model Able to Track Individual Vehicles, "
        "preprint dated 4 June 2025."
    ),
    source_section="Section 4.1, One-to-One Connections",
    figure="Figure 5 (text declarations only; numerical curves withheld)",
    equation="Equation 13",
)
DESOUZA_REFERENCE = ReferenceAsset(
    asset_id="desouza-figure5-text-declarations-v1",
    source_id=DESOUZA_CITATION.source_id,
    label="Figure 5 lane-drop declared inputs (text only)",
    citation_text=DESOUZA_CITATION.citation_text,
    figure_table_equation="Section 4.1 and Equation 13; Figure 5 output curves excluded",
    rights_provenance_note=(
        "Only parameter declarations and surrounding prose were transcribed. "
        "No published curve, table, digitised value, or expected numerical result is embedded."
    ),
    comparison_suitability="context_only",
    missing_input_notes=(
        "Initial conditions are not explicitly declared.",
        "The downstream sink boundary is not explicitly declared.",
        "The packet departure boundary convention is not explicitly declared.",
        "The simulation stop rule is not explicitly declared.",
    ),
)


def _desouza_cases() -> tuple[ValidationCase, ...]:
    cases: list[ValidationCase] = []
    for timestep in (1.0, 3.0, 6.0):
        suffix = str(int(timestep))
        final_tick = int(150 / timestep)
        timestep_note = (
            "The declared 6 s timestep exceeds the 5 s free-flow travel time and is "
            "expected to remain visibly ineligible under UC static physical validation."
            if timestep == 6.0 else
            "The timestep satisfies UC's static free-flow and backward-wave admissibility checks."
        )
        cases.append(ValidationCase(
            case_id=f"{DESOUZA_FIGURE5_CASE_PREFIX}{suffix}", version="1",
            group_id="m8-published-desouza-figure5-preparation-v1",
            title=f"de Souza Figure 5 lane drop - {suffix} s preparation",
            short_explanation=(
                "Runs UC on the paper-declared two-link lane drop and exports observations "
                "without loading or comparing any published numerical result."
            ),
            claim_ids=("M8-VAL-09-PREPARATION", f"DESOUZA-FIG5-DT{suffix}"),
            evidence_class=EvidenceClass.PUBLISHED_NUMERICAL,
            citations=(DESOUZA_CITATION,), reference_assets=(DESOUZA_REFERENCE,),
            input_completeness=InputCompleteness.PARTIAL,
            comparison_status=ComparisonStatus.NOT_COMPARABLE,
            topology_reference="desouza-figure5-two-successive-links-v1",
            profile_reference=ACADEMIC_LTM_PARITY_PROFILE_ID,
            demand_reference=(
                "paper-declared d(t)=1.0 veh/s for t<=50 s and 0.2 veh/s for "
                "50<t<=150 s; deterministic unit-packet conversion documented separately"
            ),
            route_sequences=(("L1", "L2"),), tick_duration_seconds=timestep,
            initial_state_reference=(
                "implementation assumption: both links empty at t=0; no paper-declared "
                "initial packet placement was found"
            ),
            expected_physical_sequence=(
                "Apply only the declared two-link physical parameters and upstream demand schedule.",
                "Convert integrated boundary demand to UC unit-packet departures using the declared preparation convention.",
                "Execute the unchanged parity_ltm_v1 loading engine through the 150 s demand-support boundary.",
                "Persist canonical events, replay states, cumulative counts, storage, queues, movement traces, and internal validation outputs.",
            ),
            expected_result_summary=(
                "No expected numerical result is encoded in this preparation slice; published "
                "curves, errors, and agreement metrics remain withheld."
            ),
            why_it_matters=(
                "This freezes the first published-case input transcription and UC evidence before "
                "any paper comparison, parameter fitting, or interpretation is permitted."
            ),
            limits_on_interpretation=(
                "The result is an observed UC run, not a published numerical reproduction claim.",
                "No paper curve, table, or expected value is loaded or compared.",
                "The 150 s run boundary is derived from the end of the declared demand support; the paper does not explicitly declare a stop rule.",
                "Empty initial links, a single L1-to-L2 route, a free terminal sink, and departure event ordering are explicit implementation assumptions.",
                timestep_note,
            ),
            expected_series=(), expected_scalars=(), metrics=(),
            overlays=(
                ValidationOverlay(
                    overlay_id=f"desouza-dt{suffix}-upstream", kind="relevant_link",
                    label="Declared upstream link", link_id="L1", active_from_tick=0,
                    active_through_tick=final_tick, direction="forward",
                    evidence_source=EvidenceSource.ANALYTICAL_REFERENCE,
                    note="Topology/parameter cue only; no expected traffic state is asserted.",
                ),
                ValidationOverlay(
                    overlay_id=f"desouza-dt{suffix}-downstream", kind="relevant_link",
                    label="Declared lower-capacity downstream link", link_id="L2",
                    active_from_tick=0, active_through_tick=final_tick, direction="forward",
                    evidence_source=EvidenceSource.ANALYTICAL_REFERENCE,
                    note="The 0.5 veh/s capacity is paper-declared; no expected queue or curve is asserted.",
                ),
            ),
            known_model_differences=(
                "UC uses ceiling-rounded positive travel lags; the paper's general LTM text prints floor-based T1/T2 formulas.",
                "UC unit-packet departure conversion and same-tick event ordering are implementation conventions because Figure 5 does not declare them.",
            ),
            safe_claim=(
                "UC executed the declared physical scenario plus the listed explicit assumptions "
                "and exported internally checked evidence; no agreement or disagreement with the paper is claimed."
            ),
            provenance=(
                "Declared inputs transcribed from paper text only; Figure 5 curves were not inspected or digitised.",
                f"Source PDF SHA-256: {DESOUZA_FIGURE5_SOURCE_SHA256}.",
                "Structured transcription: docs/validation/m8_desouza_figure5_preparation_v1.json.",
            ),
            reproducibility_notes=(
                "paper-declared: two successive 150 m links; shared V=30 m/s and W=6 m/s; K1=0.2 veh/m, K2=0.1 veh/m; C1=1.0 veh/s, C2=0.5 veh/s.",
                "paper-declared: upstream d(t)=1.0 veh/s for t<=50 s and 0.2 veh/s for 50<t<=150 s.",
                f"paper-declared: discrete timestep {timestep:g} s.",
                "paper-declared reference only: the continuous LTM uses a 1 s timestep; no continuous reference run is executed in this slice.",
                "derived mathematically: 30 and 15 vehicle storage under one-lane UC SI metadata; 70 vehicles of integrated demand through 150 s.",
                "implementation assumption: one lane per link because the paper declares aggregate jam density/capacity but no lane count.",
                "implementation assumption: integrate demand over [0,t] and admit floor(cumulative demand) at tick endpoints; no random inputs.",
                "implementation assumption: empty links, fixed route L1-to-L2, deterministic FIFO, free terminal sink, and a 150 s bounded observation horizon.",
                "blocked for later comparison: published-output transcription, tolerance selection, and error computation.",
            ),
            default_final_tick=final_tick,
        ))
    return tuple(cases)


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
        provenance=("Expected tables are literal fixture data independent of UC projections.",), reproducibility_notes=("Assumption: unit packets on one triangular-FD lane.", "Assumption: inclusive integer ticks and ceiling-rounded travel lag.", "No random inputs.", "Origin admission budget is distinct from downstream sending capacity."), default_final_tick=3,
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
        known_model_differences=(), safe_claim="The kernel matches the exact single-link capacity and delay tables for this pulse.", provenance=("Expected tables are literal fixture data independent of UC projections.",), reproducibility_notes=("Assumption: unit packets on one triangular-FD lane.", "Assumption: FIFO order and exact integer sending capacity.", "No random inputs."), default_final_tick=6,
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
        known_model_differences=("Queue events describe failed inter-link transfer, unlike the single-link point-queue projection.",), safe_claim="The kernel matches this exact two-link backward-vacancy timing table.", provenance=("Expected tables are literal fixture data independent of UC projections.",), reproducibility_notes=("Assumption: unit packets and the authored full-downstream initial state.", "Assumption: backward-wave lag uses ceiling-rounded integer ticks.", "No random inputs."), default_final_tick=3,
    ),
)


def _remaining_link_cases() -> tuple[ValidationCase, ...]:
    common = {
        "version": "1",
        "group_id": "m8-analytical-links",
        "evidence_class": EvidenceClass.ANALYTICAL,
        "citations": (COMMON_CITATION,),
        "reference_assets": (REFERENCE_PLACEHOLDER,),
        "input_completeness": InputCompleteness.COMPLETE,
        "comparison_status": ComparisonStatus.EXACT,
        "profile_reference": ACADEMIC_LTM_PARITY_PROFILE_ID,
        "route_sequences": (("L1",),),
        "initial_state_reference": "empty link before authored demand",
        "limits_on_interpretation": ("Internal analytical agreement only.", "Unit-packet discrete-time case; no empirical claim."),
        "known_model_differences": (),
        "provenance": ("Expected tables are literal fixture data independent of UC projections.",),
    }
    return (
        ValidationCase(
            **common, case_id="M8-LINK-04", title="Sustained uncongested flow",
            short_explanation="One packet per tick remains below a two-packet sending capacity and translates without queueing.",
            claim_ids=("M8-VAL-LINK-SUSTAINED-FREE-FLOW",), topology_reference="m8-single-link-200m-v2",
            demand_reference="one unit packet at each tick 0 through 4", tick_duration_seconds=10.0,
            expected_physical_sequence=("One packet enters at every tick from 0 through 4.", "Each packet becomes sendable two ticks after entry.", "One packet exits at every tick from 2 through 6 and no queue forms."),
            expected_result_summary="Entries rise 1,2,3,4,5 and exits reproduce that cadence after two ticks; point queue is always zero.",
            why_it_matters="Separates sustained free-flow behaviour from the finite pulse already covered by M8-LINK-01.",
            expected_series=(_series("entries", "Expected cumulative entries", (1,2,3,4,5,5,5)), _series("exits", "Expected cumulative exits", (0,0,1,2,3,4,5)), _series("point_queue", "Expected point queue", (0,0,0,0,0,0,0))),
            expected_scalars=(_scalar("exit_ticks", "Expected packet exit ticks", "2,3,4,5,6", "ticks"),),
            metrics=(_metric("entries_max_error", "Entry curve maximum error", "entries"), _metric("exits_max_error", "Exit curve maximum error", "exits"), _metric("queue_max_error", "Queue curve maximum error", "point_queue"), _metric("exit_tick_sequence", "Exit tick sequence", "exit_ticks", "exact", "exact_sequence")),
            overlays=(ValidationOverlay(overlay_id="sustained-free-flow", kind="relevant_link", label="Sustained free-flow interval", link_id="L1", active_from_tick=0, active_through_tick=6, direction="forward", evidence_source=EvidenceSource.ANALYTICAL_REFERENCE, note="Whole-link cadence cue; not continuous packet position."),),
            safe_claim="The kernel matches this exact sustained sub-capacity translation table.", reproducibility_notes=("Assumption: unit packets, one per tick from 0 through 4.", "Assumption: two-packet sending capacity and two-tick free-flow lag.", "No random inputs; expected values are authored before execution."), default_final_tick=6,
        ),
        ValidationCase(
            **common, case_id="M8-LINK-05", title="Queue growth and clearance",
            short_explanation="Two packets per tick arrive for three ticks while the link can discharge only one packet per tick.",
            claim_ids=("M8-VAL-LINK-QUEUE-GROWTH", "M8-VAL-LINK-QUEUE-CLEARANCE"), topology_reference="m8-single-link-200m-v3",
            demand_reference="two unit packets at each tick 0 through 2", tick_duration_seconds=10.0,
            expected_physical_sequence=("Six packets enter over ticks 0 through 2.", "One packet exits per tick from tick 2.", "The point queue grows to three packets, then clears to zero at tick 7."),
            expected_result_summary="The queue series is 0,0,1,2,3,2,1,0 while discharge stays saturated until all six packets exit.",
            why_it_matters="Adds queue growth under sustained excess inflow; M8-LINK-02 only starts from a finite pulse.",
            expected_series=(_series("entries", "Expected cumulative entries", (2,4,6,6,6,6,6,6)), _series("exits", "Expected cumulative exits", (0,0,1,2,3,4,5,6)), _series("point_queue", "Expected point queue", (0,0,1,2,3,2,1,0))),
            expected_scalars=(_scalar("exit_ticks", "Expected packet exit ticks", "2,3,4,5,6,7", "ticks"), _scalar("peak_queue", "Expected peak queue", 3, "packets")),
            metrics=(_metric("entries_max_error", "Entry curve maximum error", "entries"), _metric("exits_max_error", "Exit curve maximum error", "exits"), _metric("queue_max_error", "Queue curve maximum error", "point_queue"), _metric("exit_tick_sequence", "Exit tick sequence", "exit_ticks", "exact", "exact_sequence"), _metric("peak_queue_error", "Peak queue error", "peak_queue", "packets", "absolute_error")),
            overlays=(ValidationOverlay(overlay_id="growing-queue", kind="queued_region", label="Queue growth and clearance", link_id="L1", active_from_tick=2, active_through_tick=6, direction="none", evidence_source=EvidenceSource.VALIDATION_OUTPUT, note="Magnitude comes from the Python comparison series."),),
            safe_claim="The kernel matches this exact queue-growth, saturated-discharge, and clearance table.", reproducibility_notes=("Assumption: two unit packets enter at ticks 0, 1, and 2.", "Assumption: one-packet sending capacity and two-tick free-flow lag.", "No random inputs; expected values are authored before execution."), default_final_tick=7,
        ),
        ValidationCase(
            **{**common, "route_sequences": (("L2",), ("L1", "L2")), "initial_state_reference": "L2 full with three unit packets; L1 holds three transfer candidates"},
            case_id="M8-LINK-06", title="Repeated backward vacancy releases",
            short_explanation="Three downstream exits release three vacancies that reach the upstream boundary on successive lagged ticks.",
            claim_ids=("M8-VAL-LINK-MULTIPLE-VACANCIES",), topology_reference="m8-two-link-vacancy-v2",
            demand_reference="three-packet L2 preload plus three L1-to-L2 candidates", tick_duration_seconds=4.0,
            expected_physical_sequence=("Three L2 packets exit at ticks 1, 2, and 3.", "Their vacancies reach the upstream boundary at ticks 3, 4, and 5.", "Exactly one queued candidate enters L2 at each release tick."),
            expected_result_summary="L2 entries rise at ticks 3,4,5 and the boundary queue falls from three packets to zero one packet at a time.",
            why_it_matters="Extends the single-vacancy evidence in M8-LINK-03 to repeated releases without adding a new wave model.",
            expected_series=(_series("l2_entries", "Expected L2 cumulative entries", (3,3,3,4,5,6)), _series("l2_exits", "Expected L2 cumulative exits", (0,1,2,3,4,5)), _series("queue_entries", "Expected cumulative canonical boundary queue entries", (0,1,1,1,1,1)), _series("queue_exits", "Expected cumulative canonical boundary queue exits", (0,0,0,1,1,1)), _series("boundary_queue", "Expected canonical boundary queue", (0,1,1,0,0,0)), _series("blocked_candidates", "Expected blocked transfer candidates", (0,3,3,2,1,0))),
            expected_scalars=(_scalar("candidate_release_ticks", "Expected candidate L2 entry ticks", "3,4,5", "ticks"),),
            metrics=(_metric("l2_entry_error", "L2 entry curve maximum error", "l2_entries"), _metric("l2_exit_error", "L2 exit curve maximum error", "l2_exits"), _metric("queue_entry_error", "Boundary queue-entry maximum error", "queue_entries"), _metric("queue_exit_error", "Boundary queue-exit maximum error", "queue_exits"), _metric("boundary_queue_error", "Boundary queue maximum error", "boundary_queue"), _metric("blocked_candidate_error", "Blocked-candidate maximum error", "blocked_candidates"), _metric("release_tick_sequence", "Release tick sequence", "candidate_release_ticks", "exact", "exact_sequence")),
            overlays=(ValidationOverlay(overlay_id="repeated-vacancy-wave", kind="reference_wave", label="Repeated backward vacancy releases", link_id="L2", active_from_tick=1, active_through_tick=5, direction="backward", evidence_source=EvidenceSource.ANALYTICAL_REFERENCE, note="Authored lag timing; no continuous shock position is claimed."),),
            safe_claim="The kernel matches the exact repeated-vacancy release sequence for this full downstream link.", reproducibility_notes=("Assumption: L2 stores exactly three unit packets and begins full.", "Assumption: each exit releases one vacancy after a two-tick backward lag.", "No random inputs; expected values are authored before execution."), default_final_tick=5,
        ),
        ValidationCase(
            **common, case_id="M8-LINK-07", title="Fractional sending capacity",
            short_explanation="A 1.5-packet-per-tick sending rate is realised by bounded integer carry over a multi-tick discharge.",
            claim_ids=("M8-VAL-LINK-FRACTIONAL-SENDING",), topology_reference="m8-single-link-fractional-v1",
            demand_reference="six unit packets admitted at tick 0", tick_duration_seconds=1.0,
            expected_physical_sequence=("The sending carry alternates 0.5 and 0.0.", "Integer budgets alternate one and two packets from tick 1.", "Once packets are eligible, releases follow budgets 2,1,2,1 and total six."),
            expected_result_summary="Cumulative exits are 0,0,2,3,5,6; capacity carry remains bounded in [0,1).",
            why_it_matters="Validates non-integer physical capacity before a published case uses fractional per-tick rates.",
            expected_series=(_series("entries", "Expected cumulative entries", (6,6,6,6,6,6)), _series("exits", "Expected cumulative exits", (0,0,2,3,5,6)), _series("sending_budget", "Expected integer sending budget", (0,1,2,1,2,1)), _series("sending_carry", "Expected sending carry", (0,0.5,0,0.5,0,0.5), units="packets")),
            expected_scalars=(_scalar("exit_ticks", "Expected packet exit ticks", "2,2,3,4,4,5", "ticks"), _scalar("total_exits", "Expected total exits", 6, "packets")),
            metrics=(_metric("entries_max_error", "Entry curve maximum error", "entries"), _metric("exits_max_error", "Exit curve maximum error", "exits"), _metric("sending_budget_error", "Sending budget maximum error", "sending_budget"), _metric("sending_carry_error", "Sending carry maximum error", "sending_carry"), _metric("exit_tick_sequence", "Exit tick sequence", "exit_ticks", "exact", "exact_sequence"), _metric("total_exit_error", "Total exit error", "total_exits", "packets", "absolute_error")),
            overlays=(ValidationOverlay(overlay_id="fractional-release", kind="released_storage", label="Fractional-capacity packet release", link_id="L1", active_from_tick=2, active_through_tick=5, direction="forward", evidence_source=EvidenceSource.ENGINE_EXPORTED, note="Integer budget and carry are exported by Python for comparison."),),
            safe_claim="The kernel matches this exact bounded-carry sequence and six-packet long-horizon total.", reproducibility_notes=("Assumption: six unit packets enter at tick 0.", "Assumption: 1.5-packet rate, zero initial carry, and two-tick free-flow lag.", "No random inputs; expected values are authored before execution."), default_final_tick=5,
        ),
    )


NODE_SPECS = (
    _NodeCaseSpec("M8-NODE-01-DEMAND", "NODE-01 demand-limited", 1, 3, 2, (0,1,0), (0,1,0), (0,0,0), (0,3,0), (0,1,1), (0,0,0), "1"),
    _NodeCaseSpec("M8-NODE-01-SUPPLY", "NODE-01 supply-limited", 3, 1, 3, (0,3,2,1), (0,1,1,1), (0,2,1,0), (0,1,1,1), (0,1,2,3), (0,2,1,0), "1,2,3"),
    _NodeCaseSpec("M8-NODE-01-EQUAL", "NODE-01 equal demand and supply", 2, 2, 2, (0,2,0), (0,2,0), (0,0,0), (0,2,0), (0,2,2), (0,0,0), "1,1"),
    _NodeCaseSpec("M8-NODE-01-ZERO-DEMAND", "NODE-01 zero demand", 0, 3, 1, (0,0), (0,0), (0,0), (0,0), (0,0), (0,0), ""),
    _NodeCaseSpec("M8-NODE-01-ZERO-SUPPLY", "NODE-01 zero supply", 2, 0, 2, (0,2,2), (0,0,0), (0,2,2), (0,0,0), (0,0,0), (0,2,2), ""),
    _NodeCaseSpec("M8-NODE-01-REOPEN", "NODE-01 reopening after blockage", 2, 2, 3, (0,2,2,0), (0,0,2,0), (0,2,0,0), (0,0,3,0), (0,0,2,2), (0,2,0,0), "2,2", initial_closed=True, reopen_tick=2),
    _NodeCaseSpec("M8-NODE-01-FRACTIONAL", "NODE-01 fractional receiving transfer", 6, 6, 4, (0,6,5,3,2), (0,1,2,1,2), (0,5,3,2,0), (0,1,2,1,2), (0,1,3,4,6), (0,5,3,2,0), "1,2,2,3,4,4", fractional_receiving_rate=1.5),
)


def _node_cases() -> tuple[ValidationCase, ...]:
    cases = []
    for spec in NODE_SPECS:
        blocked = spec.initial_closed or spec.receiving_supply == 0
        cases.append(ValidationCase(
            case_id=spec.case_id, version="1", group_id="m8-analytical-node-01", title=spec.title,
            short_explanation="One upstream movement is resolved by independently authored min(demand, supply) arithmetic.",
            claim_ids=("M8-VAL-NODE-ONE-TO-ONE", spec.case_id), evidence_class=EvidenceClass.ANALYTICAL,
            citations=(Citation(source_id="m8-analytical-node-01-v1", citation_text="Urban Cybernetics M8 NODE-01 independently authored arithmetic tables.", source_section=spec.title),),
            reference_assets=(ReferenceAsset(asset_id=f"{spec.case_id.lower()}-table", source_id="m8-analytical-node-01-v1", label="Authored NODE-01 arithmetic table", citation_text="Repository-authored min(demand, supply) table.", figure_table_equation="F=min(D,S)", rights_provenance_note="Repository-authored numerical reference; no external image embedded.", comparison_suitability="suitable"),),
            input_completeness=InputCompleteness.COMPLETE, comparison_status=ComparisonStatus.EXACT,
            topology_reference="m8-node-one-to-one-v1", profile_reference=ACADEMIC_LTM_PARITY_PROFILE_ID,
            demand_reference=f"{spec.demand} unit packets on L1 at tick 0", route_sequences=(("L1","L2"),), tick_duration_seconds=1.0,
            initial_state_reference="empty links; downstream receiving closed initially" if spec.initial_closed else "empty links and declared downstream supply",
            expected_physical_sequence=("Packets become eligible at the L1 downstream boundary after one tick.", "The authored oracle computes approvals as min(eligible demand, downstream supply).", "Unapproved packets remain in the boundary queue without reordering.", "Downstream receiving reopens before tick 2." if spec.reopen_tick else "The same arithmetic is repeated independently at each tick."),
            expected_result_summary=f"Per-tick approvals are {tuple(int(v) for v in spec.approvals)}; cumulative transfers are {tuple(int(v) for v in spec.cumulative_transfers)}.",
            why_it_matters="Establishes the elementary node constraint used by the later lane-drop reproduction before any merge or diverge complexity.",
            limits_on_interpretation=("Only one upstream and one downstream movement is covered.", "Internal analytical agreement, not published reproduction."),
            expected_series=(_series("movement_candidates", "Expected eligible movement candidates", spec.candidates), _series("movement_approvals", "Expected movement approvals", spec.approvals), _series("movement_rejections", "Expected movement rejections", spec.rejections), _series("receiving_supply", "Expected downstream receiving supply", spec.receiving), _series("cumulative_transfers", "Expected cumulative L2 entries", spec.cumulative_transfers), _series("boundary_queue", "Expected boundary queue", spec.boundary_queue)),
            expected_scalars=(_scalar("transfer_ticks", "Expected L2 entry ticks", spec.transfer_ticks, "ticks"), _scalar("total_transfers", "Expected total transfers", spec.demand if not blocked or spec.reopen_tick else 0, "packets")),
            metrics=(_metric("candidate_error", "Candidate-count maximum error", "movement_candidates"), _metric("approval_error", "Approval-count maximum error", "movement_approvals"), _metric("rejection_error", "Rejection-count maximum error", "movement_rejections"), _metric("receiving_error", "Receiving-supply maximum error", "receiving_supply"), _metric("transfer_error", "Cumulative-transfer maximum error", "cumulative_transfers"), _metric("boundary_queue_error", "Boundary-queue maximum error", "boundary_queue"), _metric("transfer_tick_sequence", "Transfer tick sequence", "transfer_ticks", "exact", "exact_sequence"), _metric("total_transfer_error", "Total transfer error", "total_transfers", "packets", "absolute_error")),
            overlays=(ValidationOverlay(overlay_id=f"{spec.case_id.lower()}-movement", kind="blocked_boundary" if blocked else "event_marker", label="One-to-one movement boundary", link_id="L1", boundary_id="boundary:L1->L2", active_from_tick=1, active_through_tick=spec.final_tick, direction="forward" if not blocked else "none", evidence_source=EvidenceSource.ENGINE_EXPORTED, note="Movement approvals and rejections come from engine-exported allocation traces and are compared in Python."),),
            known_model_differences=(), safe_claim=f"The one-to-one allocator matches the exact authored arithmetic for {spec.title.lower()}.",
            provenance=("Expected tables are literal fixture data independent of allocator code; observed approvals come from read-only traces.",),
            reproducibility_notes=("Assumption: unit packets and one admissible L1-to-L2 movement.", "Assumption: no merge, diverge, signal, lane-group, or conflict-resource competition.", "Expected approvals use only min(eligible demand, receiving supply); no allocator helper constructs them.", "No random inputs."), default_final_tick=spec.final_tick,
        ))
    return tuple(cases)


CASES += _remaining_link_cases() + _node_cases() + _desouza_cases()

CASES_BY_ID = {case.case_id: case for case in CASES}


def execute_case(
    case: ValidationCase,
    *,
    result_id: str,
    created_at: str | None = None,
    completed_at: str | None = None,
    code_commit: str | None = None,
    cancelled: Callable[[], bool] = lambda: False,
    progress: Callable[[ValidationLifecycle, int, str], None] = lambda *_: None,
    movement_evidence: Callable[[MovementAllocationEvidence], None] = lambda *_: None,
    observed_overlay: Callable[[ValidationOverlay], None] = lambda *_: None,
) -> tuple[ValidationResult, VRunBundle]:
    created_at = created_at or datetime.now(UTC).isoformat()
    lifecycle = [ValidationLifecycle.CREATED, ValidationLifecycle.SETTING_UP]
    progress(ValidationLifecycle.SETTING_UP, 0, "Constructing declared validation case")
    engine, topology = _setup(case.case_id)
    tick_evidence = [_TickEvidence()]
    lifecycle.append(ValidationLifecycle.EXECUTING)
    progress(ValidationLifecycle.EXECUTING, engine.current_tick, "Python loading engine owns execution")
    recorded_movements: list[MovementAllocationEvidence] = []
    while engine.current_tick < case.default_final_tick and not cancelled():
        if case.case_id == "M8-NODE-01-REOPEN" and engine.current_tick + 1 == 2:
            engine.set_receiving_open("L2", True)
        before = len(engine.event_log)
        engine.step()
        new_events = engine.event_log[before:]
        if _is_desouza_case(case.case_id):
            for evidence in _movement_allocation_evidence(
                result_id=result_id, topology=topology, engine=engine,
                new_events=new_events,
            ):
                recorded_movements.append(evidence)
                movement_evidence(evidence)
        tick_evidence.append(_tick_evidence(engine))
        progress(ValidationLifecycle.EXECUTING, engine.current_tick, "Exact physical tick sealed")
    was_cancelled = cancelled()
    lifecycle.append(ValidationLifecycle.CANCELLED if was_cancelled else ValidationLifecycle.COMPARING)
    packet_ids = tuple(engine.packets)
    observed_series, observed_scalars, waits = _observed(
        case, engine, packet_ids, tuple(tick_evidence), tuple(recorded_movements)
    )
    comparison_withheld = case.comparison_status == ComparisonStatus.NOT_COMPARABLE
    internal_checks: dict[str, bool | str] = {}
    if not was_cancelled and comparison_withheld:
        internal_checks = _published_internal_checks(case, engine)
        observed_scalars += tuple(
            _scalar(
                key, key.replace("_", " ").title(), value,
                None if isinstance(value, bool) else "status",
                source=EvidenceSource.VALIDATION_OUTPUT,
            )
            for key, value in internal_checks.items()
        )
        for overlay in _observed_vacancy_overlays(case, engine):
            observed_overlay(overlay)
    metric_results, differences = (
        _compare(case, observed_series, observed_scalars)
        if not was_cancelled and not comparison_withheld else ((), ())
    )
    passed = bool(metric_results) and all(metric.passed for metric in metric_results)
    status = (
        ValidationStatus.CANCELLED if was_cancelled
        else ValidationStatus.NOT_RUN if comparison_withheld
        else ValidationStatus.PASSED if passed
        else ValidationStatus.FAILED
    )
    lifecycle.extend(
        () if was_cancelled else (
            ValidationLifecycle.PERSISTING,
            ValidationLifecycle.COMPLETE if passed or comparison_withheld else ValidationLifecycle.FAILED,
        )
    )
    config = _validation_config(case)
    expected_hash = _hash({"series": [item.model_dump(mode="json") for item in case.expected_series], "scalars": [item.model_dump(mode="json") for item in case.expected_scalars]})
    configuration_hash = _hash(config)
    replay_run_id = f"validation:{result_id}"
    context = ValidationContext.from_engine(
        engine, nodes=tuple(engine.nodes.values()), run_config=config
    )
    internal_passed = all(
        value for value in internal_checks.values() if isinstance(value, bool)
    ) if internal_checks else True
    validation_status = (
        "not_run" if was_cancelled else
        "passed" if comparison_withheld and internal_passed else
        "failed" if comparison_withheld else
        "passed" if passed else "failed"
    )
    validation_notes = (
        (
            "Core conservation, event-cache consistency, cumulative-count consistency, exact deterministic rerun, and static physical eligibility were evaluated internally.",
            "Published Figure 5 numerical outputs were not loaded or compared; this validation status is not a paper-agreement result.",
        ) if comparison_withheld else
        (case.safe_claim if passed else "Comparison did not satisfy the declared exact oracle.",)
    )
    bundle = build_run_bundle(
        run_id=replay_run_id, scenario_name=f"{case.case_id} · {case.title}", topology=topology,
        context=context, status=RunStatus.PARTIAL if was_cancelled else RunStatus.BOUNDED,
        status_reason="Validation execution cancelled; partial canonical evidence retained." if was_cancelled else "Declared validation execution completed.",
        tick_duration_seconds=case.tick_duration_seconds, config_snapshot=config,
        configuration_id="uc.validation.case.v1", validation_status=validation_status,
        validation_notes=validation_notes,
        input_artifact_ids=(case.case_id,), code_version=code_commit, created_at=created_at,
        node_positions=_node_positions(topology),
    )
    if comparison_withheld and not was_cancelled:
        bundle = bundle.model_copy(update={
            "validation": bundle.validation.model_copy(update={
                "checks": {
                    **bundle.validation.checks,
                    **{
                        key: "passed" if value else "failed"
                        for key, value in internal_checks.items()
                        if isinstance(value, bool)
                    },
                    "published_numerical_comparison": "not_run",
                }
            })
        })
    max_error = max((metric.value for metric in metric_results), default=0.0)
    observed_summary = (
        "Partial evidence retained; comparison not performed." if was_cancelled else
        "UC observation completed and the evidence bundle was exported; the published comparison remains deliberately withheld."
        if comparison_withheld else
        "Observed Python projections match all declared expectations." if passed else
        "One or more observed projections differ from the declared oracle."
    )
    difference_summary = (
        "Not comparable after cancellation." if was_cancelled else
        "No paper difference series or errors were computed in this preparation slice."
        if comparison_withheld else
        "All declared differences are zero." if passed else
        "See failed metric rows and difference series."
    )
    result = ValidationResult(
        result_id=result_id, case_id=case.case_id, case_version=case.version, status=status,
        lifecycle=tuple(lifecycle), created_at=created_at,
        completed_at=completed_at or datetime.now(UTC).isoformat(), code_commit=code_commit,
        configuration_hash=configuration_hash, expected_evidence_hash=expected_hash,
        replay_run_id=replay_run_id, observed_series=observed_series,
        observed_scalars=observed_scalars, difference_series=differences,
        metric_results=metric_results,
        headline_metric=(
            "cancelled before comparison" if was_cancelled else
            "UC evidence exported; paper comparison withheld" if comparison_withheld else
            f"maximum declared error {max_error:g}"
        ),
        observed_result_summary=observed_summary,
        difference_summary=difference_summary,
        packet_wait_explanations=waits, stop_reason="cancel_requested" if was_cancelled else None,
        provenance=(
            "Observed series folded in Python from canonical events.",
            "No published numerical output was loaded." if comparison_withheld
            else "Expected evidence loaded from immutable authored case definition.",
        ),
    )
    return result, bundle


def _is_desouza_case(case_id: str) -> bool:
    return case_id.startswith(DESOUZA_FIGURE5_CASE_PREFIX)


def _validation_config(case: ValidationCase) -> dict[str, object]:
    config: dict[str, object] = {
        "case_id": case.case_id,
        "case_version": case.version,
        "tick_duration_seconds": case.tick_duration_seconds,
        "final_tick": case.default_final_tick,
        "profile": case.profile_reference,
    }
    if not _is_desouza_case(case.case_id):
        return config
    config.update({
        "source": {
            "source_id": DESOUZA_CITATION.source_id,
            "pdf_sha256": DESOUZA_FIGURE5_SOURCE_SHA256,
            "source_section": "4.1 One-to-One Connections",
            "source_equation": "13",
            "published_output_access": "withheld_not_loaded",
        },
        "paper_declared": {
            "topology": "two successive directed links L1 -> L2",
            "length_m_by_link": {"L1": 150.0, "L2": 150.0},
            "free_flow_speed_mps_by_link": {"L1": 30.0, "L2": 30.0},
            "backward_wave_speed_mps_by_link": {"L1": 6.0, "L2": 6.0},
            "jam_density_veh_per_m_by_link": {"L1": 0.2, "L2": 0.1},
            "capacity_veh_per_s_by_link": {"L1": 1.0, "L2": 0.5},
            "demand_schedule": [
                {"rate_veh_per_s": 1.0, "condition": "t <= 50 s"},
                {"rate_veh_per_s": 0.2, "condition": "50 s < t <= 150 s"},
            ],
            "tested_timestep_seconds": case.tick_duration_seconds,
            "continuous_reference_timestep_seconds_not_run": 1.0,
            "model_assumptions": (
                "triangular fundamental diagram",
                "one-to-one node flow is min(upstream demand, downstream supply)",
                "integer vehicle flows and FIFO vehicle association",
                "CFL condition max(V,W)*dt <= L stated in the paper",
            ),
        },
        "derived_mathematically": {
            "capacity_formula": "C=K*V*W/(V+W)",
            "storage_packets_by_link_under_uc_one_lane_mapping": {"L1": 30, "L2": 15},
            "integrated_demand_packets_through_150_seconds": 70,
            "observation_horizon_seconds": 150.0,
        },
        "implementation_assumptions": (
            "one lane per link for UC SI metadata",
            "both links empty before the first departure",
            "all unit packets follow the fixed route L1 -> L2",
            "the terminal boundary after L2 is a free sink governed by current UC completion semantics",
            "integrate demand over [0,t], floor cumulative vehicles at tick endpoints, and admit new unit packets at that endpoint tick",
            "stop at 150 seconds, the end of declared demand support",
            "use current UC ceiling-rounded positive travel lags and current deterministic event ordering",
        ),
        "blocked_unknowns": (
            "paper-declared initial conditions",
            "paper-declared downstream sink boundary rule",
            "paper-declared packet departure boundary and tie-breaking convention",
            "paper-declared simulation stop rule",
            "published numerical outputs and comparison tolerances intentionally withheld",
        ),
    })
    return config


def _published_internal_checks(
    case: ValidationCase, engine: LoadingEngine
) -> dict[str, bool | str]:
    replay_engine, _ = _setup(case.case_id)
    while replay_engine.current_tick < case.default_final_tick:
        replay_engine.step()
    physical = assess_physical_parameter_eligibility(tuple(engine.links.values()))
    context = ValidationContext.from_engine(
        engine, nodes=tuple(engine.nodes.values()), run_config=_validation_config(case)
    )
    return {
        "conservation_check": engine.check_conservation(),
        "event_cache_consistency_check": engine.check_event_cache_consistency(),
        "cumulative_count_consistency_check": context.count_consistency_report.is_consistent,
        "deterministic_replay_exact": replay_engine.event_log == engine.event_log,
        "physical_parameter_parity_eligible": physical.is_parity_eligible,
        "physical_ineligibility_reasons": ",".join(physical.ineligibility_reasons),
    }


def _observed_vacancy_overlays(
    case: ValidationCase, engine: LoadingEngine
) -> tuple[ValidationOverlay, ...]:
    if not _is_desouza_case(case.case_id):
        return ()
    lag = engine.links["L2"].resolved_physical_parameters().backward_wave_lag_ticks
    assert lag is not None
    exits = (
        event for event in engine.event_log
        if event.event_type == EventType.LINK_EXIT and event.entity_id == "L2"
    )
    return tuple(
        ValidationOverlay(
            overlay_id=f"{case.case_id.lower()}-observed-vacancy-{event.sequence_number}",
            kind="reference_wave", label="Observed L2 exit vacancy propagation",
            link_id="L2", active_from_tick=event.physical_tick,
            active_through_tick=min(event.physical_tick + lag, engine.current_tick),
            direction="backward", evidence_source=EvidenceSource.VALIDATION_OUTPUT,
            note=(
                f"Canonical L2 exit at tick {event.physical_tick}; presentation window uses "
                f"UC's declared backward-wave lag of {lag} ticks. Screen position is presentation-only."
            ),
        )
        for event in exits
    )


def _setup(case_id: str) -> tuple[LoadingEngine, CanonicalTopology]:
    nodes: tuple[Node, ...] = ()
    sending_rates: dict[str, float] | None = None
    receiving_rates: dict[str, float] | None = None
    initial_receiving_credit: dict[str, float] | None = None
    if case_id == "M8-LINK-01":
        inputs, demands = (UNCONGESTED,), tuple((f"D{i}", ("L1",)) for i in range(3))
    elif case_id == "M8-LINK-02":
        inputs, demands = (BOTTLENECK,), tuple((f"D{i}", ("L1",)) for i in range(5))
    elif case_id == "M8-LINK-03":
        inputs = (VACANCY_L1, VACANCY_L2)
        demands = tuple((f"D-blocker-{i}", ("L2",)) for i in range(3)) + (("D-upstream", ("L1","L2")),)
    elif case_id == "M8-LINK-04":
        inputs = (SUSTAINED_FREE_FLOW,)
        demands = tuple((f"D{i}", ("L1",), i) for i in range(5))
    elif case_id == "M8-LINK-05":
        inputs = (QUEUE_GROWTH,)
        demands = tuple((f"D{tick}-{index}", ("L1",), tick) for tick in range(3) for index in range(2))
    elif case_id == "M8-LINK-06":
        inputs = (VACANCY_L1, VACANCY_L2)
        demands = tuple((f"D-blocker-{i}", ("L2",)) for i in range(3)) + tuple((f"D-upstream-{i}", ("L1","L2")) for i in range(3))
    elif case_id == "M8-LINK-07":
        inputs = (FRACTIONAL_SENDING,)
        demands = tuple((f"D{i}", ("L1",)) for i in range(6))
        sending_rates = {"L1": 1.5}
    elif case_id.startswith("M8-NODE-01-"):
        spec = next(item for item in NODE_SPECS if item.case_id == case_id)
        downstream = _LinkInput("L2", 10.0, 10.0, 5.0, 1800.0, 21600.0, 1.0, spec.receiving_supply)
        inputs = (NODE_UPSTREAM, downstream)
        demands = tuple((f"D{i}", ("L1", "L2")) for i in range(spec.demand))
        nodes = (Node("N1", incoming_link_ids=("L1",), outgoing_link_ids=("L2",)),)
        if spec.fractional_receiving_rate is not None:
            receiving_rates = {"L2": spec.fractional_receiving_rate}
    elif _is_desouza_case(case_id):
        timestep = float(case_id.removeprefix(DESOUZA_FIGURE5_CASE_PREFIX))
        inputs = DESOUZA_INPUTS_BY_TIMESTEP[timestep]
        demands = _desouza_demands(timestep)
        nodes = (Node("N1", incoming_link_ids=("L1",), outgoing_link_ids=("L2",)),)
        sending_rates = {item.link_id: float(item.sending_rate_per_tick) for item in inputs}
        receiving_rates = dict(sending_rates)
        initial_receiving_credit = {"L2": 0.0}
    else:
        raise KeyError(case_id)
    engine = LoadingEngine(
        links={item.link_id: item.link() for item in inputs},
        nodes=nodes,
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        parity_sending_capacity_vehicles_per_tick_by_link=sending_rates,
        parity_receiving_capacity_vehicles_per_tick_by_link=receiving_rates,
        parity_initial_receiving_credit_by_link=initial_receiving_credit,
    )
    for demand in demands:
        demand_id, route, *departure = demand
        engine.instantiate(DemandDeclaration(demand_id, departure[0] if departure else 0, route))
    if case_id == "M8-NODE-01-REOPEN":
        engine.set_receiving_open("L2", False)
    return engine, _topology(case_id, inputs)


def _desouza_demands(timestep: float) -> tuple[tuple[str, tuple[str, ...], int], ...]:
    """Convert the declared continuous boundary demand into deterministic unit requests."""

    requests: list[tuple[str, tuple[str, ...], int]] = []
    previous_total = 0
    final_tick = int(150 / timestep)
    for tick in range(1, final_tick + 1):
        time_seconds = tick * timestep
        cumulative = (
            time_seconds if time_seconds <= 50
            else 50 + (time_seconds - 50) * 0.2
        )
        target_total = floor(cumulative + 1e-12)
        for _ in range(previous_total, target_total):
            requests.append((
                f"DESOUZA-FIG5-D{len(requests) + 1:03d}", ("L1", "L2"), tick
            ))
        previous_total = target_total
    if len(requests) != 70:
        raise AssertionError(f"de Souza integrated demand resolved {len(requests)} packets")
    return tuple(requests)


def _topology(case_id: str, inputs: tuple[_LinkInput, ...]) -> CanonicalTopology:
    node_ids = tuple(f"N{i}" for i in range(len(inputs) + 1))
    links = tuple(CanonicalTopologyLink(link_id=item.link_id, tail_node_id=node_ids[index], head_node_id=node_ids[index+1], source_link_id=item.link_id, source_tail_node_id=str(index), source_head_node_id=str(index+1), length_m=item.length_m, lane_count=1, free_flow_speed_mps=item.free_flow_speed_mps, capacity_veh_per_hour_per_lane=item.capacity_veh_per_hour_per_lane, jam_density_veh_per_km_per_lane=item.jam_density_veh_per_km_per_lane, backward_wave_speed_mps=item.backward_wave_speed_mps) for index, item in enumerate(inputs))
    nodes = tuple(CanonicalNode(node_id=node_id, source_node_id=str(index), incoming_link_ids=tuple(link.link_id for link in links if link.head_node_id == node_id), outgoing_link_ids=tuple(link.link_id for link in links if link.tail_node_id == node_id)) for index, node_id in enumerate(node_ids))
    published = _is_desouza_case(case_id)
    return CanonicalTopology(
        topology_id=f"validation:{case_id.lower()}:v1", nodes=nodes, links=links,
        source_metadata=TopologySourceMetadata(
            source_name=(
                "de Souza et al. Figure 5 text declarations"
                if published else "M8 authored analytical fixture"
            ),
            source_format=(
                "published_text_transcription" if published else "declared_python_contract"
            ),
            source_file_path=(
                "de Souza - Packetised LTM.pdf" if published else "validation_cases.py"
            ),
            source_file_sha256=(
                DESOUZA_FIGURE5_SOURCE_SHA256 if published
                else hashlib.sha256(case_id.encode()).hexdigest()
            ),
        ),
        interpretation_assumptions=(
            (
                "Schematic coordinates are non-geographic.",
                "Paper text declares two successive links but no lane count; one lane is the explicit UC metadata mapping.",
                "Empty initial links, fixed L1-to-L2 routing, free terminal sink, and tick-end unit departures are implementation assumptions.",
                "Published numerical outputs are intentionally absent.",
            ) if published else (
                "Schematic coordinates are non-geographic.",
                "Unit packets; SI link metadata; declared discrete timestep.",
            )
        ),
    )


def _node_positions(topology: CanonicalTopology) -> dict[str, tuple[float, float]]:
    return {node.node_id: (0.15 + index * (0.7 / max(len(topology.nodes)-1, 1)), 0.5) for index, node in enumerate(topology.nodes)}


def _count(events: tuple[Event, ...], event_type: EventType, entity: str, final_tick: int) -> tuple[float, ...]:
    return tuple(float(sum(event.event_type == event_type and event.entity_id == entity and event.physical_tick <= tick for event in events)) for tick in range(final_tick + 1))


def _ticks_by_packet(events: tuple[Event, ...], event_type: EventType, entity: str, packet_ids: tuple[str, ...]) -> tuple[int, ...]:
    values = {event.packet_id: event.physical_tick for event in events if event.event_type == event_type and event.entity_id == entity}
    return tuple(values[packet_id] for packet_id in packet_ids if packet_id in values)


def _tick_evidence(engine: LoadingEngine) -> _TickEvidence:
    traces = engine.node_transfer_traces()
    candidates = sum(len(trace.candidate_packet_ids) for trace in traces)
    approvals = sum(len(trace.approved_packet_ids) for trace in traces)
    rejections = sum(len(trace.rejected_transfer_reasons) for trace in traces)
    receiving = sum(
        dict(trace.receiving_slots_by_downstream_link).get("L2", 0)
        + len(trace.approved_packet_ids)
        for trace in traces
    )
    sending = engine.parity_link_sending_trace("L1") if "L1" in engine.links else None
    sending_by_link = {
        link_id: engine.parity_link_sending_trace(link_id)
        for link_id in engine.links
    }
    receiving_by_link = {
        link_id: engine.parity_link_supply_view(link_id)
        for link_id in engine.links
    }
    return _TickEvidence(
        candidate_count=candidates,
        approval_count=approvals,
        rejection_count=rejections,
        receiving_supply=receiving,
        sending_budget=0 if sending is None else sending.integer_capacity,
        sending_carry=0.0 if sending is None else sending.capacity_carry_out,
        sending_budget_by_link=tuple(
            (link_id, trace.integer_capacity)
            for link_id, trace in sending_by_link.items()
        ),
        sending_carry_by_link=tuple(
            (link_id, trace.capacity_carry_out)
            for link_id, trace in sending_by_link.items()
        ),
        receiving_budget_by_link=tuple(
            (link_id, trace.integer_receiving_capacity)
            for link_id, trace in receiving_by_link.items()
        ),
        receiving_carry_by_link=tuple(
            (link_id, trace.receiving_capacity_carry_out)
            for link_id, trace in receiving_by_link.items()
        ),
    )


def _observed(
    case: ValidationCase,
    engine: LoadingEngine,
    packet_ids: tuple[str, ...],
    tick_evidence: tuple[_TickEvidence, ...],
    movement_evidence: tuple[MovementAllocationEvidence, ...] = (),
) -> tuple[tuple[ValidationSeries, ...], tuple[ScalarExpectation, ...], tuple[PacketWaitExplanation, ...]]:
    events = engine.event_log
    final = engine.current_tick
    source = EvidenceSource.EVENT_DERIVED
    if _is_desouza_case(case.case_id):
        series: list[ValidationSeries] = []
        for link_id in ("L1", "L2"):
            entries = _count(events, EventType.LINK_ENTRY, link_id, final)
            exits = _count(events, EventType.LINK_EXIT, link_id, final)
            storage = tuple(entry - exit for entry, exit in zip(entries, exits))
            series.extend((
                _series(
                    f"{link_id.lower()}_cumulative_inflow",
                    f"Observed {link_id} cumulative inflow", entries, source=source,
                ),
                _series(
                    f"{link_id.lower()}_cumulative_outflow",
                    f"Observed {link_id} cumulative outflow", exits, source=source,
                ),
                _series(
                    f"{link_id.lower()}_storage", f"Observed {link_id} storage",
                    storage, source=EvidenceSource.EVENT_DERIVED,
                ),
                _series(
                    f"{link_id.lower()}_sending_budget",
                    f"Observed {link_id} integer sending budget",
                    tuple(float(dict(item.sending_budget_by_link).get(link_id, 0)) for item in tick_evidence),
                    source=EvidenceSource.ENGINE_EXPORTED,
                ),
                _series(
                    f"{link_id.lower()}_sending_carry",
                    f"Observed {link_id} sending carry",
                    tuple(dict(item.sending_carry_by_link).get(link_id, 0.0) for item in tick_evidence),
                    units="packets", source=EvidenceSource.ENGINE_EXPORTED,
                ),
                _series(
                    f"{link_id.lower()}_receiving_budget",
                    f"Observed {link_id} integer receiving budget",
                    tuple(float(dict(item.receiving_budget_by_link).get(link_id, 0)) for item in tick_evidence),
                    source=EvidenceSource.ENGINE_EXPORTED,
                ),
                _series(
                    f"{link_id.lower()}_receiving_carry",
                    f"Observed {link_id} receiving carry",
                    tuple(dict(item.receiving_carry_by_link).get(link_id, 0.0) for item in tick_evidence),
                    units="packets", source=EvidenceSource.ENGINE_EXPORTED,
                ),
            ))
        queue_entries = _count(events, EventType.QUEUE_ENTRY, "boundary:L1->L2", final)
        queue_exits = _count(events, EventType.QUEUE_EXIT, "boundary:L1->L2", final)
        boundary_queue = tuple(entry - exit for entry, exit in zip(queue_entries, queue_exits))
        series.extend((
            _series(
                "boundary_queue", "Observed canonical L1-to-L2 boundary queue",
                boundary_queue, source=EvidenceSource.CANONICAL,
            ),
            _series(
                "queue_entries", "Observed cumulative canonical queue entries",
                queue_entries, source=EvidenceSource.CANONICAL,
            ),
            _series(
                "queue_exits", "Observed cumulative canonical queue exits",
                queue_exits, source=EvidenceSource.CANONICAL,
            ),
        ))
        rejected: dict[str, tuple[int, str, int | None]] = {}
        for allocation in movement_evidence:
            for movement in allocation.movements:
                for packet_id, reason in movement.rejected_packet_reasons:
                    rejected.setdefault(
                        packet_id,
                        (allocation.tick, reason, movement.receiving_supply_packets),
                    )
        queue_exit_tick = {
            event.packet_id: event.physical_tick
            for event in events
            if event.event_type == EventType.QUEUE_EXIT
            and event.entity_id == "boundary:L1->L2"
        }
        waits = tuple(
            PacketWaitExplanation(
                packet_id=event.packet_id,
                active_from_tick=event.physical_tick,
                active_through_tick=queue_exit_tick.get(event.packet_id, final),
                current_link_id="L1", fifo_position=None, head_packet_id=None,
                intended_movement="boundary:L1->L2",
                blocking_reason=rejected.get(event.packet_id, (0, None, None))[1],
                receiving_supply_packets=rejected.get(event.packet_id, (0, None, None))[2],
                signal_or_governance_constraint=None,
                expected_next_release_tick=None,
                evidence_sources=(EvidenceSource.CANONICAL, EvidenceSource.ENGINE_EXPORTED),
                unavailable_fields=(
                    "paper-declared release tick", "published comparison expectation"
                ),
            )
            for event in events
            if event.event_type == EventType.QUEUE_ENTRY
            and event.entity_id == "boundary:L1->L2"
        )
        scalars = (
            _scalar("declared_demand_packets", "Integrated declared demand", 70, "packets", source=EvidenceSource.VALIDATION_OUTPUT),
            _scalar("instantiated_packets", "Packets instantiated by horizon", len(engine.packets), "packets", source=EvidenceSource.CANONICAL),
            _scalar("completed_packets", "Packets completed by horizon", len(engine.completed_packet_ids), "packets", source=EvidenceSource.CANONICAL),
            _scalar("event_count", "Canonical event count", len(events), "events", source=EvidenceSource.CANONICAL),
            _scalar("observation_horizon", "Bounded observation horizon", final * case.tick_duration_seconds, "s", source=EvidenceSource.VALIDATION_OUTPUT),
        )
        return tuple(series), scalars, waits
    if case.case_id.startswith("M8-NODE-01-"):
        transfers = _count(events, EventType.LINK_ENTRY, "L2", final)
        queue_entries = _count(events, EventType.QUEUE_ENTRY, "boundary:L1->L2", final)
        queue_exits = _count(events, EventType.QUEUE_EXIT, "boundary:L1->L2", final)
        boundary_queue = tuple(entry - exit for entry, exit in zip(queue_entries, queue_exits))
        transfer_ticks = _ticks_by_packet(events, EventType.LINK_ENTRY, "L2", packet_ids)
        spec = next(item for item in NODE_SPECS if item.case_id == case.case_id)
        queued_ids = tuple(event.packet_id for event in events if event.event_type == EventType.QUEUE_ENTRY and event.entity_id == "boundary:L1->L2")
        waits = ()
        if queued_ids:
            waits = (PacketWaitExplanation(
                packet_id=queued_ids[0], active_from_tick=1,
                active_through_tick=1 if spec.reopen_tick else final,
                current_link_id="L1", fifo_position=0, head_packet_id=queued_ids[0],
                intended_movement="boundary:L1->L2", blocking_reason="downstream_receiving_supply_zero" if spec.initial_closed or spec.receiving_supply == 0 else "downstream_receiving_supply_exhausted",
                receiving_supply_packets=0 if spec.initial_closed or spec.receiving_supply == 0 else spec.receiving_supply,
                signal_or_governance_constraint="downstream receiving closed" if spec.initial_closed else None,
                expected_next_release_tick=spec.reopen_tick,
                evidence_sources=(EvidenceSource.CANONICAL, EvidenceSource.ENGINE_EXPORTED, EvidenceSource.ANALYTICAL_REFERENCE),
                unavailable_fields=(),
            ),)
        return (
            (
                _series("movement_candidates", "Observed eligible movement candidates", tuple(float(item.candidate_count) for item in tick_evidence), source=EvidenceSource.ENGINE_EXPORTED),
                _series("movement_approvals", "Observed movement approvals", tuple(float(item.approval_count) for item in tick_evidence), source=EvidenceSource.ENGINE_EXPORTED),
                _series("movement_rejections", "Observed movement rejections", tuple(float(item.rejection_count) for item in tick_evidence), source=EvidenceSource.ENGINE_EXPORTED),
                _series("receiving_supply", "Observed downstream receiving supply", tuple(float(item.receiving_supply) for item in tick_evidence), source=EvidenceSource.ENGINE_EXPORTED),
                _series("cumulative_transfers", "Observed cumulative L2 entries", transfers, source=source),
                _series("boundary_queue", "Observed boundary queue", boundary_queue, source=EvidenceSource.CANONICAL),
            ),
            (
                _scalar("transfer_ticks", "Observed L2 entry ticks", ",".join(map(str, transfer_ticks)), "ticks", source=source),
                _scalar("total_transfers", "Observed total transfers", int(transfers[-1]) if transfers else 0, "packets", source=source),
            ),
            waits,
        )
    if case.case_id in {"M8-LINK-01", "M8-LINK-02", "M8-LINK-04", "M8-LINK-05", "M8-LINK-07"}:
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
        elif case.case_id == "M8-LINK-02":
            entry_ticks = _ticks_by_packet(events, EventType.LINK_ENTRY, "L1", packet_ids)
            delays = tuple(float(exit_tick-entry_tick-lag) for entry_tick, exit_tick in zip(entry_ticks, exit_ticks))
            series.append(ValidationSeries(series_id="packet_delay", label="Observed delay by packet ordinal", quantity="packet_delay", units="ticks", time_basis="packet ordinal", ticks=tuple(range(len(delays))), values=delays, evidence_source=source))
            scalars.append(_scalar("mean_delay", "Observed mean delay", sum(delays)/len(delays) if delays else 0.0, "ticks", source=EvidenceSource.VALIDATION_OUTPUT))
        elif case.case_id == "M8-LINK-05":
            scalars.append(_scalar("peak_queue", "Observed peak queue", max(queue), "packets", source=EvidenceSource.VALIDATION_OUTPUT))
        elif case.case_id == "M8-LINK-07":
            series.extend((
                _series("sending_budget", "Observed integer sending budget", tuple(float(item.sending_budget) for item in tick_evidence), source=EvidenceSource.ENGINE_EXPORTED),
                _series("sending_carry", "Observed sending carry", tuple(item.sending_carry for item in tick_evidence), source=EvidenceSource.ENGINE_EXPORTED),
            ))
            scalars.append(_scalar("total_exits", "Observed total exits", int(exits[-1]), "packets", source=source))
        return tuple(series), tuple(scalars), ()
    if case.case_id == "M8-LINK-06":
        l2_entries = _count(events, EventType.LINK_ENTRY, "L2", final)
        l2_exits = _count(events, EventType.LINK_EXIT, "L2", final)
        queue_entries = _count(events, EventType.QUEUE_ENTRY, "boundary:L1->L2", final)
        queue_exits = _count(events, EventType.QUEUE_EXIT, "boundary:L1->L2", final)
        boundary_queue = tuple(entry - exit for entry, exit in zip(queue_entries, queue_exits))
        l1_entries = _count(events, EventType.LINK_ENTRY, "L1", final)
        l1_exits = _count(events, EventType.LINK_EXIT, "L1", final)
        blocked_candidates = tuple(0.0 if tick == 0 else l1_entries[tick] - l1_exits[tick] for tick in range(final + 1))
        release_ticks = _ticks_by_packet(events, EventType.LINK_ENTRY, "L2", packet_ids[3:])
        return (
            (_series("l2_entries", "Observed L2 cumulative entries", l2_entries, source=source), _series("l2_exits", "Observed L2 cumulative exits", l2_exits, source=source), _series("queue_entries", "Observed cumulative boundary queue entries", queue_entries, source=EvidenceSource.CANONICAL), _series("queue_exits", "Observed cumulative boundary queue exits", queue_exits, source=EvidenceSource.CANONICAL), _series("boundary_queue", "Observed boundary queue", boundary_queue, source=EvidenceSource.CANONICAL), _series("blocked_candidates", "Observed blocked transfer candidates", blocked_candidates, source=EvidenceSource.VALIDATION_OUTPUT)),
            (_scalar("candidate_release_ticks", "Observed candidate L2 entry ticks", ",".join(map(str, release_ticks)), "ticks", source=source),),
            (),
        )
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


def _movement_allocation_evidence(
    *,
    result_id: str,
    topology: CanonicalTopology,
    engine: LoadingEngine,
    new_events: tuple[Event, ...],
) -> tuple[MovementAllocationEvidence, ...]:
    specs = {
        movement.movement_id: movement
        for node in topology.nodes
        for movement in node.junction_spec().movement_specs
    }
    evidence: list[MovementAllocationEvidence] = []
    for trace in engine.allocation_traces():
        rejected = dict(trace.rejected_transfer_reasons)
        receiving = dict(trace.receiving_slots_by_downstream_link)
        lane = dict(trace.lane_group_capacity_by_id)
        conflict = dict(trace.conflict_resource_capacity_by_id)
        flows: list[MovementFlowEvidence] = []
        for summary in trace.movement_flow_summaries:
            spec = specs.get(summary.movement_id)
            if spec is None:
                continue
            approved = tuple(
                packet_id for packet_id in trace.approved_packet_ids
                if _packet_transfer_matches(
                    packet_id, spec.upstream_link_id, spec.downstream_link_id, new_events
                )
            )
            candidates = tuple(
                packet_id for packet_id in trace.candidate_packet_ids
                if _route_contains_movement(
                    engine.packets[packet_id].route_intent,
                    spec.upstream_link_id,
                    spec.downstream_link_id,
                )
            )
            flows.append(MovementFlowEvidence(
                movement_id=summary.movement_id,
                upstream_link_id=summary.upstream_link_id,
                downstream_link_id=summary.downstream_link_id,
                request_packet_ids=candidates,
                upstream_fifo_packet_ids=candidates,
                approved_packet_ids=approved,
                rejected_packet_reasons=tuple(
                    (packet_id, rejected[packet_id])
                    for packet_id in candidates if packet_id in rejected
                ),
                receiving_supply_packets=receiving.get(summary.downstream_link_id),
                movement_capacity_packets=None,
                lane_group_constraints={
                    key: value for key, value in lane.items()
                    if key in spec.lane_group_ids
                },
                conflict_resource_constraints={
                    key: value for key, value in conflict.items()
                    if key in spec.conflict_resource_ids
                },
                signal_state=(
                    "not_declared" if spec.signal_group_id is None
                    else "open" if spec.signal_group_id in trace.open_signal_group_ids
                    else "closed"
                ),
                governance_state=(
                    "closed" if summary.movement_id in trace.closed_movement_ids else "open"
                ),
                resulting_canonical_event_sequences=tuple(
                    event.sequence_number for event in new_events
                    if event.packet_id in approved
                    and event.event_type in {EventType.LINK_EXIT, EventType.LINK_ENTRY}
                ),
            ))
        if flows:
            evidence.append(MovementAllocationEvidence(
                run_id=result_id, tick=engine.current_tick,
                junction_id=trace.node_id, allocator_id=trace.allocator_id,
                movement_spec_hash=engine.movement_spec_hash,
                semantic_sources={
                    "requests": "engine_owned_materialised_trace",
                    "movement_spec": "immutable_topology_metadata",
                    "approvals": "engine_owned_materialised_trace",
                    "resulting_events": "canonical_event_data",
                },
                movements=tuple(flows),
            ))
    return tuple(evidence)


def _packet_transfer_matches(
    packet_id: str, upstream: str, downstream: str, events: tuple[Event, ...]
) -> bool:
    event_pairs = {
        (event.packet_id, event.event_type, event.entity_id) for event in events
    }
    return (
        (packet_id, EventType.LINK_EXIT, upstream) in event_pairs
        and (packet_id, EventType.LINK_ENTRY, downstream) in event_pairs
    )


def _route_contains_movement(
    route: tuple[str, ...], upstream: str, downstream: str
) -> bool:
    return any(
        left == upstream and right == downstream
        for left, right in zip(route, route[1:])
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
