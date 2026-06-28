"""Sioux Falls parity-readiness gates for canonical validation Phase II."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from math import floor

from urban_cybernetics.config import (
    ACADEMIC_LTM_PARITY_PROFILE_ID,
    LEGACY_LOADING_PROFILE_ID,
)
from urban_cybernetics.core import DemandDeclaration, EventType, Link, Node
from urban_cybernetics.demand import (
    FixedDepartureSchedule,
    ScheduledDemandLoader,
    load_sioux_falls_demand_manifest,
    resolve_demand_routes,
)
from urban_cybernetics.demand.resolution import ResolvedDemandManifest
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.topology import CanonicalTopologyLink, load_sioux_falls_topology
from urban_cybernetics.validation import (
    CommodityParityValidationReport,
    PhysicalParameterEligibilityReport,
    SpillbackValidationReport,
    assess_physical_parameter_eligibility,
    build_commodity_parity_validation_report,
    build_spillback_validation_report,
)


PASS_STATUS = "pass"
FAIL_STATUS = "fail"
NOT_RUN_STATUS = "not_run"
READINESS_STRESS_LABEL = "sioux_falls_readiness_stress_only"
PARITY_VALIDATION_LABEL = "sioux_falls_parity_validation"
SUBNETWORK_READINESS_LABEL = "sioux_falls_supported_movement_subnetwork_parity_ready"
SUBNETWORK_BACKWARD_WAVE_SPEED_MPS = 5.0
SUBNETWORK_LINK_IDS = (
    "L0001",
    "L0002",
    "L0003",
    "L0004",
    "L0006",
    "L0009",
    "L0012",
    "L0016",
)
SUBNETWORK_ROUTES = (
    ("route:N001->N008:via-N002", ("L0001", "L0004", "L0016")),
    ("route:N001->N001:return-via-N002", ("L0001", "L0003")),
    ("route:N001->N008:via-N003-N006", ("L0002", "L0006", "L0009", "L0012", "L0016")),
)


@dataclass(frozen=True, slots=True)
class SiouxFallsReadinessGate:
    """One executable readiness gate and its current status."""

    gate_id: str
    status: str
    reason: str
    detail_count: int = 0
    details: tuple[str, ...] = ()

    @property
    def is_pass(self) -> bool:
        """Return whether this gate currently passes."""

        return self.status == PASS_STATUS


@dataclass(frozen=True, slots=True)
class SiouxFallsReadinessReport:
    """Machine-readable Sioux Falls parity-readiness status."""

    benchmark_id: str
    requested_model_profile_id: str
    evidence_label: str
    can_run_as_parity_ltm_v1: bool
    topology_hash: str
    demand_hash: str
    resolved_manifest_hash: str
    topology_node_count: int
    topology_link_count: int
    od_pair_count: int
    scheduled_departure_count: int
    instantiated_packet_count: int
    completed_packet_count: int
    event_count: int
    ticks_run: int
    gates: tuple[SiouxFallsReadinessGate, ...]
    kernel_bug_found: bool = False

    @property
    def failed_gate_ids(self) -> tuple[str, ...]:
        """Return failed gate IDs in report order."""

        return tuple(gate.gate_id for gate in self.gates if gate.status == FAIL_STATUS)

    @property
    def not_run_gate_ids(self) -> tuple[str, ...]:
        """Return gate IDs skipped because an earlier gate failed."""

        return tuple(gate.gate_id for gate in self.gates if gate.status == NOT_RUN_STATUS)

    def status_payload(self) -> dict[str, object]:
        """Return a JSON-ready provenance and status payload."""

        payload = asdict(self)
        payload["failed_gate_ids"] = self.failed_gate_ids
        payload["not_run_gate_ids"] = self.not_run_gate_ids
        return payload


@dataclass(frozen=True, slots=True)
class SiouxFallsSubnetworkMetadataAssumption:
    """One provenance-labelled physical metadata assumption for the subnetwork."""

    field_name: str
    value: str
    provenance_label: str
    note: str


@dataclass(frozen=True, slots=True)
class SiouxFallsSubnetworkReadinessReport:
    """Machine-readable readiness status for the supported Sioux Falls subnetwork."""

    subnetwork_id: str
    parent_benchmark_id: str
    requested_model_profile_id: str
    evidence_label: str
    is_ready_for_parity_validation: bool
    topology_hash: str
    selected_source_nodes: tuple[str, ...]
    selected_link_ids: tuple[str, ...]
    selected_source_links: tuple[str, ...]
    unsupported_advanced_full_network_node_ids: tuple[str, ...]
    adapted_supported_node_ids: tuple[str, ...]
    movement_specs: tuple[tuple[str, tuple[tuple[str, str, int], ...]], ...]
    route_intents: tuple[tuple[str, tuple[str, ...]], ...]
    metadata_assumptions: tuple[SiouxFallsSubnetworkMetadataAssumption, ...]
    instantiated_packet_count: int
    completed_packet_count: int
    event_count: int
    ticks_run: int
    gates: tuple[SiouxFallsReadinessGate, ...]
    kernel_bug_found: bool = False

    @property
    def failed_gate_ids(self) -> tuple[str, ...]:
        """Return failed gate IDs in report order."""

        return tuple(gate.gate_id for gate in self.gates if gate.status == FAIL_STATUS)

    def status_payload(self) -> dict[str, object]:
        """Return a JSON-ready provenance and status payload."""

        payload = asdict(self)
        payload["failed_gate_ids"] = self.failed_gate_ids
        return payload


def build_sioux_falls_parity_readiness_report(
    *,
    scale_factor: float = 0.01,
    max_pairs: int = 3,
    max_total_quantity_packets: int = 6,
    tick_limit: int = 30,
    storage_capacity_packets: int = 1000,
    tick_duration_seconds: float = 60.0,
) -> SiouxFallsReadinessReport:
    """Run executable Sioux Falls readiness gates without claiming validation."""

    topology = load_sioux_falls_topology()
    manifest = load_sioux_falls_demand_manifest(
        topology=topology,
        scale_factor=scale_factor,
        max_pairs=max_pairs,
        max_total_quantity_packets=max_total_quantity_packets,
        departure_schedule=FixedDepartureSchedule(departure_tick=0),
    )
    resolved = resolve_demand_routes(manifest, topology)
    scheduled_departure_count = len(ScheduledDemandLoader(resolved).scheduled_requests)
    links = topology.as_loading_links(
        tick_duration_seconds=tick_duration_seconds,
        declared_storage_capacity_packets=storage_capacity_packets,
    )
    nodes = topology.as_loading_nodes()

    physical_report = assess_physical_parameter_eligibility(
        links.values(),
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
    )
    gates: list[SiouxFallsReadinessGate] = [
        _pass_gate(
            "benchmark_loader",
            "Sioux Falls topology, demand, and route-resolution artifacts loaded.",
            details=(
                f"topology_hash={topology.topology_hash}",
                f"demand_hash={manifest.manifest_hash}",
                f"resolved_manifest_hash={resolved.resolved_manifest_hash}",
            ),
        ),
        _physical_gate(physical_report),
    ]

    parity_engine: LoadingEngine | None = None
    parity_error: str | None = None
    try:
        parity_engine = LoadingEngine(
            links=links,
            nodes=nodes,
            model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        )
    except ValueError as exc:
        parity_error = f"{type(exc).__name__}: {exc}"

    if parity_error is None:
        gates.append(
            _pass_gate(
                "parity_profile_full_topology_initialization",
                "Full Sioux Falls topology initialized with the movement allocator.",
            )
        )
        if physical_report.is_parity_eligible:
            assert parity_engine is not None
            _run_scheduled_slice(parity_engine, resolved, tick_limit=tick_limit)
            commodity_report = build_commodity_parity_validation_report(parity_engine)
            spillback_report = build_spillback_validation_report(parity_engine)
            gates.extend(
                (
                    _commodity_gate(commodity_report),
                    _spillback_gate(spillback_report),
                )
            )
        else:
            gates.extend(
                (
                    _not_run_gate(
                        "parity_commodity_evidence",
                        "Skipped because full-topology physical metadata is not parity-eligible.",
                    ),
                    _not_run_gate(
                        "parity_spillback_evidence",
                        "Skipped because full-topology physical metadata is not parity-eligible.",
                    ),
                )
            )
    else:
        gates.extend(
            (
                _fail_gate(
                    "parity_profile_full_topology_initialization",
                    "Full Sioux Falls topology cannot currently initialize under "
                    "the movement-allocation parity path.",
                    details=(parity_error,),
                ),
                _not_run_gate(
                    "parity_commodity_evidence",
                    "Skipped because parity_ltm_v1 full-topology initialization failed.",
                ),
                _not_run_gate(
                    "parity_spillback_evidence",
                    "Skipped because parity_ltm_v1 full-topology initialization failed.",
                ),
            )
        )

    legacy_engine, legacy_gate = _legacy_readiness_stress_gate(
        links=links,
        nodes=nodes,
        resolved_manifest=resolved,
        tick_limit=tick_limit,
    )
    gates.append(legacy_gate)

    can_run_as_parity = all(gate.is_pass for gate in gates[:-1])
    return SiouxFallsReadinessReport(
        benchmark_id="sioux_falls_tntp_v1",
        requested_model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        evidence_label=(
            PARITY_VALIDATION_LABEL
            if can_run_as_parity
            else READINESS_STRESS_LABEL
        ),
        can_run_as_parity_ltm_v1=can_run_as_parity,
        topology_hash=topology.topology_hash,
        demand_hash=manifest.manifest_hash,
        resolved_manifest_hash=resolved.resolved_manifest_hash,
        topology_node_count=len(topology.nodes),
        topology_link_count=len(topology.links),
        od_pair_count=len(manifest.declarations),
        scheduled_departure_count=scheduled_departure_count,
        instantiated_packet_count=len(legacy_engine.packets),
        completed_packet_count=len(legacy_engine.completed_packet_ids),
        event_count=len(legacy_engine.event_log),
        ticks_run=legacy_engine.current_tick,
        gates=tuple(gates),
        kernel_bug_found=False,
    )


def build_sioux_falls_supported_subnetwork_readiness_report(
    *,
    tick_limit: int = 30,
    tick_duration_seconds: float = 60.0,
) -> SiouxFallsSubnetworkReadinessReport:
    """Run a supported Sioux Falls subnetwork under parity_ltm_v1."""

    topology = load_sioux_falls_topology()
    canonical_links = {link.link_id: link for link in topology.links}
    selected_canonical_links = tuple(
        canonical_links[link_id] for link_id in SUBNETWORK_LINK_IDS
    )
    links = _subnetwork_loading_links(
        selected_canonical_links,
        tick_duration_seconds=tick_duration_seconds,
    )
    nodes = _subnetwork_nodes()
    engine = _run_subnetwork_engine(
        links=links,
        nodes=nodes,
        tick_limit=tick_limit,
    )
    replay_engine = _run_subnetwork_engine(
        links=links,
        nodes=nodes,
        tick_limit=tick_limit,
    )

    physical_report = assess_physical_parameter_eligibility(
        links.values(),
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
    )
    commodity_report = build_commodity_parity_validation_report(engine)
    spillback_report = build_spillback_validation_report(engine)
    count_report = engine.count_consistency_report()
    gates = (
        _subnetwork_structure_gate(nodes),
        _physical_gate(physical_report),
        _pass_gate(
            "parity_profile_initialization",
            "Supported Sioux Falls subnetwork initialized under parity_ltm_v1.",
        ),
        _commodity_gate(commodity_report),
        _spillback_gate(spillback_report),
        _count_gate(count_report),
        _conservation_gate(engine),
        _deterministic_replay_gate(engine, replay_engine),
    )
    is_ready = all(gate.is_pass for gate in gates)

    return SiouxFallsSubnetworkReadinessReport(
        subnetwork_id="sioux_falls_supported_movement_subnetwork_v1",
        parent_benchmark_id="sioux_falls_tntp_v1",
        requested_model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        evidence_label=(
            SUBNETWORK_READINESS_LABEL
            if is_ready
            else "sioux_falls_supported_subnetwork_readiness_blocked"
        ),
        is_ready_for_parity_validation=is_ready,
        topology_hash=topology.topology_hash,
        selected_source_nodes=("1", "2", "3", "4", "5", "6", "8"),
        selected_link_ids=SUBNETWORK_LINK_IDS,
        selected_source_links=tuple(
            link.source_link_id for link in selected_canonical_links
        ),
        unsupported_advanced_full_network_node_ids=(
            _unsupported_advanced_full_network_node_ids(topology)
        ),
        adapted_supported_node_ids=tuple(node.node_id for node in nodes),
        movement_specs=tuple(
            (
                node.node_id,
                tuple(
                    (
                        movement.upstream_link_id,
                        movement.downstream_link_id,
                        movement.priority_weight,
                    )
                    for movement in node.junction_spec.movement_specs
                ),
            )
            for node in nodes
        ),
        route_intents=SUBNETWORK_ROUTES,
        metadata_assumptions=_subnetwork_metadata_assumptions(),
        instantiated_packet_count=len(engine.packets),
        completed_packet_count=len(engine.completed_packet_ids),
        event_count=len(engine.event_log),
        ticks_run=engine.current_tick,
        gates=gates,
        kernel_bug_found=False,
    )


def _legacy_readiness_stress_gate(
    *,
    links: dict[str, Link],
    nodes: tuple[Node, ...],
    resolved_manifest: ResolvedDemandManifest,
    tick_limit: int,
) -> tuple[LoadingEngine, SiouxFallsReadinessGate]:
    engine = LoadingEngine(
        links=links,
        nodes=nodes,
        model_profile_id=LEGACY_LOADING_PROFILE_ID,
    )
    _run_scheduled_slice(engine, resolved_manifest, tick_limit=tick_limit)
    count_report = engine.count_consistency_report()
    if count_report.is_consistent and len(engine.packets) > 0:
        return engine, _pass_gate(
            "legacy_profile_readiness_stress_run",
            "Small Sioux Falls slice runs as readiness/stress evidence only.",
            details=(
                f"model_profile_id={LEGACY_LOADING_PROFILE_ID}",
                f"ticks_run={engine.current_tick}",
                f"instantiated_packets={len(engine.packets)}",
                f"completed_packets={len(engine.completed_packet_ids)}",
                f"events={len(engine.event_log)}",
            ),
        )
    return engine, _fail_gate(
        "legacy_profile_readiness_stress_run",
        "Small Sioux Falls readiness/stress slice did not preserve count consistency.",
        details=count_report.ineligibility_reasons,
    )


def _run_scheduled_slice(
    engine: LoadingEngine,
    resolved_manifest: ResolvedDemandManifest,
    *,
    tick_limit: int,
) -> None:
    loader = ScheduledDemandLoader(resolved_manifest)
    loader.submit_due_departures(engine)
    for _ in range(tick_limit):
        engine.step()
        loader.submit_due_departures(engine)


def _run_subnetwork_engine(
    *,
    links: dict[str, Link],
    nodes: tuple[Node, ...],
    tick_limit: int,
) -> LoadingEngine:
    engine = LoadingEngine(
        links=links,
        nodes=nodes,
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        parity_sending_capacity_vehicles_per_tick_by_link={
            link_id: link.resolved_physical_parameters().total_capacity_vehicles_per_tick
            for link_id, link in links.items()
        },
        parity_receiving_capacity_vehicles_per_tick_by_link={
            link_id: link.resolved_physical_parameters().total_capacity_vehicles_per_tick
            for link_id, link in links.items()
        },
    )
    for demand in _subnetwork_demands():
        engine.instantiate(demand)
    for _ in range(tick_limit):
        engine.step()
    return engine


def _subnetwork_loading_links(
    canonical_links: Iterable[CanonicalTopologyLink],
    *,
    tick_duration_seconds: float,
) -> dict[str, Link]:
    return {
        canonical_link.link_id: _subnetwork_loading_link(
            canonical_link,
            tick_duration_seconds=tick_duration_seconds,
        )
        for canonical_link in canonical_links
    }


def _subnetwork_loading_link(
    canonical_link: CanonicalTopologyLink,
    *,
    tick_duration_seconds: float,
) -> Link:
    if canonical_link.free_flow_speed_mps is None:
        raise ValueError(f"{canonical_link.link_id} missing free-flow speed")
    if canonical_link.capacity_veh_per_hour_per_lane is None:
        raise ValueError(f"{canonical_link.link_id} missing source capacity")
    jam_density = _jam_density_for_assumed_backward_wave_speed(
        free_flow_speed_mps=canonical_link.free_flow_speed_mps,
        capacity_veh_per_hour_per_lane=canonical_link.capacity_veh_per_hour_per_lane,
        backward_wave_speed_mps=SUBNETWORK_BACKWARD_WAVE_SPEED_MPS,
    )
    storage_capacity = max(
        1,
        floor(
            ((canonical_link.length_m or 0.0) / 1000.0)
            * (canonical_link.lane_count or 1)
            * jam_density
        ),
    )
    return Link(
        link_id=canonical_link.link_id,
        declared_sending_capacity_per_tick=1,
        declared_receiving_capacity_per_tick=1,
        declared_storage_capacity_packets=storage_capacity,
        length_m=canonical_link.length_m,
        lane_count=canonical_link.lane_count,
        free_flow_speed_mps=canonical_link.free_flow_speed_mps,
        jam_density_veh_per_km_per_lane=jam_density,
        backward_wave_speed_mps=SUBNETWORK_BACKWARD_WAVE_SPEED_MPS,
        capacity_veh_per_hour_per_lane=canonical_link.capacity_veh_per_hour_per_lane,
        tick_duration_seconds=tick_duration_seconds,
    )


def _jam_density_for_assumed_backward_wave_speed(
    *,
    free_flow_speed_mps: float,
    capacity_veh_per_hour_per_lane: float,
    backward_wave_speed_mps: float,
) -> float:
    return (
        capacity_veh_per_hour_per_lane
        * (free_flow_speed_mps + backward_wave_speed_mps)
        / (3600.0 * free_flow_speed_mps * backward_wave_speed_mps)
        * 1000.0
    )


def _subnetwork_nodes() -> tuple[Node, ...]:
    return (
        Node(
            node_id="N002",
            incoming_link_ids=("L0001",),
            outgoing_link_ids=("L0003", "L0004"),
        ),
        Node(
            node_id="N003",
            incoming_link_ids=("L0002",),
            outgoing_link_ids=("L0006",),
        ),
        Node(
            node_id="N004",
            incoming_link_ids=("L0006",),
            outgoing_link_ids=("L0009",),
        ),
        Node(
            node_id="N005",
            incoming_link_ids=("L0009",),
            outgoing_link_ids=("L0012",),
        ),
        Node(
            node_id="N006",
            incoming_link_ids=("L0004", "L0012"),
            outgoing_link_ids=("L0016",),
            merge_priorities=(("L0004", 1), ("L0012", 1)),
        ),
    )


def _subnetwork_demands() -> tuple[DemandDeclaration, ...]:
    demands: list[DemandDeclaration] = []
    for route_index, (_, route_intent) in enumerate(SUBNETWORK_ROUTES, start=1):
        for unit_index in range(1, 3):
            demands.append(
                DemandDeclaration(
                    demand_id=f"sioux-subnetwork-r{route_index}-u{unit_index}",
                    departure_tick=0,
                    route_intent=route_intent,
                )
            )
    return tuple(demands)


def _subnetwork_metadata_assumptions() -> tuple[SiouxFallsSubnetworkMetadataAssumption, ...]:
    return (
        SiouxFallsSubnetworkMetadataAssumption(
            field_name="backward_wave_speed_mps",
            value=f"{SUBNETWORK_BACKWARD_WAVE_SPEED_MPS}",
            provenance_label="benchmark_assumption_not_empirical_calibration",
            note=(
                "Fixed for the supported subnetwork because the Sioux Falls TNTP "
                "network does not provide backward-wave speed."
            ),
        ),
        SiouxFallsSubnetworkMetadataAssumption(
            field_name="jam_density_veh_per_km_per_lane",
            value="derived_per_link_from_TNTP_capacity_free_flow_speed_and_assumed_backward_wave_speed",
            provenance_label="benchmark_assumption_not_empirical_calibration",
            note=(
                "Derived so each selected link is triangular-FD consistent with "
                "its TNTP capacity under the fixed assumed backward-wave speed."
            ),
        ),
        SiouxFallsSubnetworkMetadataAssumption(
            field_name="declared_storage_capacity_packets",
            value="derived_from_length_lane_count_and_assumed_jam_density",
            provenance_label="benchmark_assumption_not_legacy_storage_override",
            note=(
                "The subnetwork adapter does not use the legacy synthetic storage "
                "override as parity evidence."
            ),
        ),
    )


def _physical_gate(
    report: PhysicalParameterEligibilityReport,
) -> SiouxFallsReadinessGate:
    if report.is_parity_eligible:
        return _pass_gate(
            "physical_metadata",
            "All Sioux Falls loading links have parity-eligible physical metadata.",
        )
    return _fail_gate(
        "physical_metadata",
        "Sioux Falls TNTP topology is missing physical metadata required for "
        "true parity evidence.",
        detail_count=len(report.ineligibility_reasons),
        details=report.ineligibility_reasons[:12],
    )


def _commodity_gate(
    report: CommodityParityValidationReport,
) -> SiouxFallsReadinessGate:
    if report.is_valid:
        return _pass_gate(
            "parity_commodity_evidence",
            "Packet, route-count, and travel-time evidence is valid for the run.",
        )
    return _fail_gate(
        "parity_commodity_evidence",
        "Packet, route-count, or travel-time evidence is not parity-valid.",
        detail_count=len(report.invariant_violations),
        details=report.invariant_violations[:12],
    )


def _spillback_gate(
    report: SpillbackValidationReport,
) -> SiouxFallsReadinessGate:
    if report.is_valid:
        return _pass_gate(
            "parity_spillback_evidence",
            "Spillback evidence is internally valid for the run.",
        )
    return _fail_gate(
        "parity_spillback_evidence",
        "Spillback evidence is not parity-valid for the run.",
        detail_count=len(report.invariant_violations),
        details=report.invariant_violations[:12],
    )


def _count_gate(report: object) -> SiouxFallsReadinessGate:
    if report.is_consistent:
        return _pass_gate(
            "count_evidence",
            "Aggregate counts, route counts, packet ordinals, and travel-time curves are consistent.",
        )
    return _fail_gate(
        "count_evidence",
        "Count evidence is inconsistent.",
        detail_count=len(report.ineligibility_reasons),
        details=report.ineligibility_reasons[:12],
    )


def _conservation_gate(engine: LoadingEngine) -> SiouxFallsReadinessGate:
    instantiated_event_count = sum(
        event.event_type == EventType.INSTANTIATED for event in engine.event_log
    )
    completed_event_count = sum(
        event.event_type == EventType.COMPLETED for event in engine.event_log
    )
    if (
        instantiated_event_count == len(engine.packets)
        and completed_event_count == len(engine.completed_packet_ids)
        and completed_event_count == len(engine.packets)
        and not engine.pending_demands
    ):
        return _pass_gate(
            "packet_conservation",
            "All instantiated subnetwork packets are represented exactly once and complete.",
        )
    return _fail_gate(
        "packet_conservation",
        "Subnetwork packet conservation failed.",
        details=(
            f"instantiated_events={instantiated_event_count}",
            f"packet_records={len(engine.packets)}",
            f"completed_events={completed_event_count}",
            f"completed_packets={len(engine.completed_packet_ids)}",
            f"pending_demands={len(engine.pending_demands)}",
        ),
    )


def _deterministic_replay_gate(
    first: LoadingEngine,
    second: LoadingEngine,
) -> SiouxFallsReadinessGate:
    if first.event_log == second.event_log:
        return _pass_gate(
            "deterministic_replay",
            "Repeated subnetwork parity runs produce identical canonical events.",
        )
    return _fail_gate(
        "deterministic_replay",
        "Repeated subnetwork parity runs produced different canonical events.",
        details=(
            f"first_event_count={len(first.event_log)}",
            f"second_event_count={len(second.event_log)}",
        ),
    )


def _subnetwork_structure_gate(nodes: tuple[Node, ...]) -> SiouxFallsReadinessGate:
    details = tuple(
        f"{node.node_id}:movements="
        + ",".join(
            f"{movement.upstream_link_id}->{movement.downstream_link_id}"
            for movement in node.junction_spec.movement_specs
        )
        for node in nodes
    )
    return _pass_gate(
        "supported_subnetwork_structure",
        "Selected Sioux Falls subnetwork uses Stage 1 movement-allocation semantics.",
        details=details,
    )


def _unsupported_advanced_full_network_node_ids(topology: object) -> tuple[str, ...]:
    unsupported: list[str] = []
    for node in topology.nodes:
        junction_spec = Node(
            node.node_id,
            incoming_link_ids=node.incoming_link_ids,
            outgoing_link_ids=node.outgoing_link_ids,
        ).junction_spec
        if (
            junction_spec.lane_group_ids
            or junction_spec.movement_lane_group_mappings
            or junction_spec.conflict_resource_ids
            or junction_spec.governance_refs
            or any(
                movement.lane_group_ids
                or movement.conflict_resource_ids
                or movement.signal_group_id is not None
                for movement in junction_spec.movement_specs
            )
        ):
            unsupported.append(node.node_id)
    return tuple(unsupported)


def _pass_gate(
    gate_id: str,
    reason: str,
    *,
    details: tuple[str, ...] = (),
) -> SiouxFallsReadinessGate:
    return SiouxFallsReadinessGate(
        gate_id=gate_id,
        status=PASS_STATUS,
        reason=reason,
        detail_count=len(details),
        details=details,
    )


def _fail_gate(
    gate_id: str,
    reason: str,
    *,
    detail_count: int | None = None,
    details: tuple[str, ...] = (),
) -> SiouxFallsReadinessGate:
    return SiouxFallsReadinessGate(
        gate_id=gate_id,
        status=FAIL_STATUS,
        reason=reason,
        detail_count=len(details) if detail_count is None else detail_count,
        details=details,
    )


def _not_run_gate(gate_id: str, reason: str) -> SiouxFallsReadinessGate:
    return SiouxFallsReadinessGate(
        gate_id=gate_id,
        status=NOT_RUN_STATUS,
        reason=reason,
    )


def main() -> None:
    """Print the current Sioux Falls readiness report as JSON."""

    parser = argparse.ArgumentParser(
        description="Run Sioux Falls canonical parity-readiness gates."
    )
    parser.add_argument("--tick-limit", type=int, default=30)
    parser.add_argument("--scale-factor", type=float, default=0.01)
    parser.add_argument("--max-pairs", type=int, default=3)
    parser.add_argument("--max-total-quantity-packets", type=int, default=6)
    parser.add_argument(
        "--subnetwork",
        action="store_true",
        help="Run the supported M6 Sioux Falls subnetwork readiness gates.",
    )
    args = parser.parse_args()
    if args.subnetwork:
        subnetwork_report = build_sioux_falls_supported_subnetwork_readiness_report(
            tick_limit=args.tick_limit,
        )
        print(json.dumps(subnetwork_report.status_payload(), indent=2, sort_keys=True))
        return
    report = build_sioux_falls_parity_readiness_report(
        scale_factor=args.scale_factor,
        max_pairs=args.max_pairs,
        max_total_quantity_packets=args.max_total_quantity_packets,
        tick_limit=args.tick_limit,
    )
    print(json.dumps(report.status_payload(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
