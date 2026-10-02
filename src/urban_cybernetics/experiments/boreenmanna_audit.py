# SPDX-License-Identifier: MPL-2.0
"""Scientific-integrity audit for the synthetic Boreenmanna experiment.

This module is deliberately versioned separately from the v1 experiment.  It
adds drain outcomes, phase sensitivity, representation parity proofs, and
evidence-volume accounting without changing the frozen loading kernel or the
previously generated v1 evidence.
"""

from __future__ import annotations

import json
import tracemalloc
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from math import floor
from pathlib import Path
from time import perf_counter, process_time
from typing import Mapping, Self

from urban_cybernetics.compiler.model import canonical_json, stable_hash
from urban_cybernetics.compiler.osm_experiment import (
    BoreenmannaExperimentCompilation,
    compile_boreenmanna_experiment,
)
from urban_cybernetics.core import (
    DemandDeclaration,
    EventType,
    JunctionSpec,
    LifecycleState,
    Link,
    MovementSpec,
    Node,
)
from urban_cybernetics.extensions.fixed_time_signals import (
    FixedTimeControllerPlan,
    FixedTimeSignalControlMixin,
    FixedTimeSignalPlanEvaluator,
    FixedTimeStage,
    ResolvedFixedTimeSignalPlan,
)
from urban_cybernetics.extensions.fractional_service_credit import (
    FRACTIONAL_CREDIT,
    LEGACY_INTEGER_CLAMPED,
    FractionalServiceCreditConfig,
    FractionalServiceCreditMixin,
    service_credit_config_for_executable,
)
from urban_cybernetics.extensions.gate_aware_fractional_service import (
    GATE_AWARE_FRACTIONAL_SERVICE_MODE,
    GateAwareFractionalServiceConfig,
    GateAwareFractionalServiceMixin,
    gate_aware_service_config_for_executable,
)
from urban_cybernetics.extensions.discharge_readiness_fractional_service import (
    DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE,
    DischargeReadinessConfig,
    DischargeReadinessFractionalServiceMixin,
    discharge_readiness_config_for_executable,
)
from urban_cybernetics.loading import GeneralMovementAllocator, LoadingEngine
from urban_cybernetics.loading.lane_group_extension import (
    EXPLICIT_LANE_GROUP_FIFO,
    MOVEMENT_PARTIAL_FIFO,
    SHARED_LINK_FIFO,
    LaneGroupExtensionConfig,
    LaneGroupLoadingEngine,
)

from .boreenmanna import (
    REPRESENTATION_MODES,
    SERVICE_MODES,
    BoreenmannaExperimentIntegrityError,
    SyntheticDemandScenario,
    _BoreenmannaEngine,
    _demand_scenario,
    _deterministic_metrics,
    _principal_routes,
    _replay_payload,
    build_boreenmanna_demand_scenarios,
)


BOREENMANNA_DRAIN_POLICY_VERSION = "uc.boreenmanna-drain-policy.v1"
BOREENMANNA_PARITY_MANIFEST_VERSION = "uc.representation-parity-manifest.v1"
BOREENMANNA_AUDITED_RUN_VERSION = "uc.boreenmanna-audited-run.v2"
BOREENMANNA_INTEGRITY_AUDIT_VERSION = "uc.boreenmanna-integrity-audit.v1"
DEFAULT_PHASE_OFFSETS = (0, 1, 2, 5, 10)


class BoreenmannaAuditIntegrityError(ValueError):
    """Raised when audit evidence or parity claims are inconsistent."""


@dataclass(frozen=True, slots=True)
class DrainPolicy:
    """No-new-demand continuation policy after an evaluation horizon."""

    maximum_drain_ticks: int = 1_200
    pending_demand_policy: str = "retain_eligible_pending_declared_demand"
    empty_condition: str = (
        "no_pending_demand_and_all_instantiated_packets_completed_or_cancelled"
    )
    extension_state_policy: str = "nonphysical_credit_does_not_prevent_emptiness"
    version: str = BOREENMANNA_DRAIN_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.maximum_drain_ticks <= 0:
            raise BoreenmannaAuditIntegrityError(
                "maximum_drain_ticks must be positive"
            )
        if self.pending_demand_policy != "retain_eligible_pending_declared_demand":
            raise BoreenmannaAuditIntegrityError("unsupported pending-demand policy")
        if self.empty_condition != (
            "no_pending_demand_and_all_instantiated_packets_completed_or_cancelled"
        ):
            raise BoreenmannaAuditIntegrityError("unsupported empty-network condition")
        if self.extension_state_policy != (
            "nonphysical_credit_does_not_prevent_emptiness"
        ):
            raise BoreenmannaAuditIntegrityError("unsupported extension-state policy")

    @property
    def policy_hash(self) -> str:
        return stable_hash("boreenmanna-drain-policy", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "maximum_drain_ticks": self.maximum_drain_ticks,
            "pending_demand_policy": self.pending_demand_policy,
            "empty_condition": self.empty_condition,
            "extension_state_policy": self.extension_state_policy,
        }


@dataclass(frozen=True, slots=True)
class DrainOutcome:
    """Deterministic clearance outcome following a fixed evaluation horizon."""

    evaluation_horizon_tick: int
    completed_at_evaluation: int
    pending_demand_at_evaluation: int
    physically_active_at_evaluation: int
    residual_vehicle_storage_at_evaluation: int
    eventually_completed: int
    residual_pending_demand: int
    residual_active_packets: int
    final_completion_tick: int | None
    drain_duration_ticks: int
    maximum_queue_during_drain: int
    reached_empty_condition: bool
    reached_maximum_drain_horizon: bool
    terminal_tick: int
    clearance_tick_by_origin_link: tuple[tuple[str, int | None], ...]
    unresolved_ids: tuple[str, ...]
    policy_hash: str
    outcome_hash: str = ""

    def __post_init__(self) -> None:
        ordered_clearance = tuple(sorted(self.clearance_tick_by_origin_link))
        unresolved = tuple(sorted(self.unresolved_ids))
        object.__setattr__(self, "clearance_tick_by_origin_link", ordered_clearance)
        object.__setattr__(self, "unresolved_ids", unresolved)
        expected = stable_hash("boreenmanna-drain-outcome", self._payload())
        if self.outcome_hash and self.outcome_hash != expected:
            raise BoreenmannaAuditIntegrityError("drain outcome hash mismatch")
        object.__setattr__(self, "outcome_hash", expected)

    def _payload(self) -> dict[str, object]:
        return {
            "evaluation_horizon_tick": self.evaluation_horizon_tick,
            "completed_at_evaluation": self.completed_at_evaluation,
            "pending_demand_at_evaluation": self.pending_demand_at_evaluation,
            "physically_active_at_evaluation": self.physically_active_at_evaluation,
            "residual_vehicle_storage_at_evaluation": (
                self.residual_vehicle_storage_at_evaluation
            ),
            "eventually_completed": self.eventually_completed,
            "eventual_completion_fraction": (
                self.eventually_completed
                / (
                    self.eventually_completed
                    + self.residual_pending_demand
                    + self.residual_active_packets
                )
                if (
                    self.eventually_completed
                    + self.residual_pending_demand
                    + self.residual_active_packets
                )
                else 1.0
            ),
            "residual_pending_demand": self.residual_pending_demand,
            "residual_active_packets": self.residual_active_packets,
            "final_completion_tick": self.final_completion_tick,
            "drain_duration_ticks": self.drain_duration_ticks,
            "maximum_queue_during_drain": self.maximum_queue_during_drain,
            "reached_empty_condition": self.reached_empty_condition,
            "reached_maximum_drain_horizon": self.reached_maximum_drain_horizon,
            "terminal_tick": self.terminal_tick,
            "clearance_tick_by_origin_link": [
                [link_id, tick] for link_id, tick in self.clearance_tick_by_origin_link
            ],
            "unresolved_ids": list(self.unresolved_ids),
            "policy_hash": self.policy_hash,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "outcome_hash": self.outcome_hash}


@dataclass(frozen=True, slots=True)
class RepresentationVariantManifest:
    representation_mode: str
    common_input_json: str
    representation_input_json: str
    version: str = BOREENMANNA_PARITY_MANIFEST_VERSION
    common_input_hash: str = ""
    representation_input_hash: str = ""

    def __post_init__(self) -> None:
        if self.representation_mode not in REPRESENTATION_MODES:
            raise BoreenmannaAuditIntegrityError("unknown representation mode")
        common = canonical_json(json.loads(self.common_input_json))
        specific = canonical_json(json.loads(self.representation_input_json))
        object.__setattr__(self, "common_input_json", common)
        object.__setattr__(self, "representation_input_json", specific)
        expected_common = stable_hash("representation-common-input", json.loads(common))
        expected_specific = stable_hash(
            "representation-specific-input", json.loads(specific)
        )
        if self.common_input_hash and self.common_input_hash != expected_common:
            raise BoreenmannaAuditIntegrityError("common-input hash mismatch")
        if (
            self.representation_input_hash
            and self.representation_input_hash != expected_specific
        ):
            raise BoreenmannaAuditIntegrityError("representation-input hash mismatch")
        object.__setattr__(self, "common_input_hash", expected_common)
        object.__setattr__(self, "representation_input_hash", expected_specific)

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "representation_mode": self.representation_mode,
            "common_input": json.loads(self.common_input_json),
            "representation_input": json.loads(self.representation_input_json),
            "common_input_hash": self.common_input_hash,
            "representation_input_hash": self.representation_input_hash,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            representation_mode=str(payload["representation_mode"]),
            common_input_json=canonical_json(payload["common_input"]),
            representation_input_json=canonical_json(
                payload["representation_input"]
            ),
            version=str(payload["version"]),
            common_input_hash=str(payload.get("common_input_hash", "")),
            representation_input_hash=str(
                payload.get("representation_input_hash", "")
            ),
        )


@dataclass(frozen=True, slots=True)
class RepresentationParityManifest:
    family_id: str
    variants: tuple[RepresentationVariantManifest, ...]
    version: str = BOREENMANNA_PARITY_MANIFEST_VERSION
    manifest_hash: str = ""

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.variants, key=lambda item: item.representation_mode))
        object.__setattr__(self, "variants", ordered)
        if {item.representation_mode for item in ordered} != set(REPRESENTATION_MODES):
            raise BoreenmannaAuditIntegrityError(
                "parity family must contain exactly the three representations"
            )
        common_payloads = {item.common_input_json for item in ordered}
        common_hashes = {item.common_input_hash for item in ordered}
        if len(common_payloads) != 1 or len(common_hashes) != 1:
            raise BoreenmannaAuditIntegrityError(
                "representation parity failed: a supposedly common input differs"
            )
        expected = stable_hash(
            "representation-parity-manifest",
            {
                "version": self.version,
                "family_id": self.family_id,
                "common_input_hash": ordered[0].common_input_hash,
                "representation_input_hashes": [
                    [item.representation_mode, item.representation_input_hash]
                    for item in ordered
                ],
            },
        )
        if self.manifest_hash and self.manifest_hash != expected:
            raise BoreenmannaAuditIntegrityError("parity manifest hash mismatch")
        object.__setattr__(self, "manifest_hash", expected)

    @property
    def common_input_hash(self) -> str:
        return self.variants[0].common_input_hash

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "family_id": self.family_id,
            "variants": [item.to_dict() for item in self.variants],
            "common_input_hash": self.common_input_hash,
            "manifest_hash": self.manifest_hash,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        result = cls(
            family_id=str(payload["family_id"]),
            variants=tuple(
                RepresentationVariantManifest.from_dict(item)
                for item in payload["variants"]  # type: ignore[index]
            ),
            version=str(payload["version"]),
            manifest_hash=str(payload.get("manifest_hash", "")),
        )
        if payload.get("common_input_hash") != result.common_input_hash:
            raise BoreenmannaAuditIntegrityError("parity common hash mismatch")
        return result


@dataclass(frozen=True, slots=True)
class AuditedRunManifest:
    deterministic_payload_json: str
    performance_payload_json: str
    version: str = BOREENMANNA_AUDITED_RUN_VERSION
    deterministic_hash: str = ""
    manifest_hash: str = ""

    def __post_init__(self) -> None:
        deterministic = canonical_json(json.loads(self.deterministic_payload_json))
        performance = canonical_json(json.loads(self.performance_payload_json))
        object.__setattr__(self, "deterministic_payload_json", deterministic)
        object.__setattr__(self, "performance_payload_json", performance)
        expected_deterministic = stable_hash(
            "boreenmanna-audited-run", json.loads(deterministic)
        )
        if self.deterministic_hash and self.deterministic_hash != expected_deterministic:
            raise BoreenmannaAuditIntegrityError("audited run hash mismatch")
        object.__setattr__(self, "deterministic_hash", expected_deterministic)
        expected_manifest = stable_hash(
            "boreenmanna-audited-run-manifest",
            {
                "deterministic_hash": expected_deterministic,
                "performance": json.loads(performance),
            },
        )
        if self.manifest_hash and self.manifest_hash != expected_manifest:
            raise BoreenmannaAuditIntegrityError("audited run manifest hash mismatch")
        object.__setattr__(self, "manifest_hash", expected_manifest)

    @property
    def deterministic(self) -> dict[str, object]:
        return json.loads(self.deterministic_payload_json)

    @property
    def performance(self) -> dict[str, object]:
        return json.loads(self.performance_payload_json)

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "deterministic": self.deterministic,
            "performance": self.performance,
            "deterministic_hash": self.deterministic_hash,
            "manifest_hash": self.manifest_hash,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            deterministic_payload_json=canonical_json(payload["deterministic"]),
            performance_payload_json=canonical_json(payload["performance"]),
            version=str(payload["version"]),
            deterministic_hash=str(payload.get("deterministic_hash", "")),
            manifest_hash=str(payload.get("manifest_hash", "")),
        )


@dataclass(frozen=True, slots=True)
class BoreenmannaIntegrityAuditPackage:
    compilation_package_hash: str
    original_matrix_hash: str
    core_runs: tuple[AuditedRunManifest, ...]
    parity_manifests: tuple[RepresentationParityManifest, ...]
    phase_results_json: str
    scaling_results_json: str
    periodic_gating_json: str
    performance_json: str
    version: str = BOREENMANNA_INTEGRITY_AUDIT_VERSION
    deterministic_hash: str = ""
    package_hash: str = ""

    def __post_init__(self) -> None:
        core = tuple(
            sorted(
                self.core_runs,
                key=lambda item: (
                    str(item.deterministic["scenario_id"]),
                    str(item.deterministic["service_credit_mode"]),
                    str(item.deterministic["representation_mode"]),
                ),
            )
        )
        parity = tuple(sorted(self.parity_manifests, key=lambda item: item.family_id))
        object.__setattr__(self, "core_runs", core)
        object.__setattr__(self, "parity_manifests", parity)
        for name in (
            "phase_results_json",
            "scaling_results_json",
            "periodic_gating_json",
            "performance_json",
        ):
            object.__setattr__(self, name, canonical_json(json.loads(getattr(self, name))))
        deterministic_payload = self._deterministic_payload()
        expected_deterministic = stable_hash(
            "boreenmanna-integrity-audit", deterministic_payload
        )
        if self.deterministic_hash and self.deterministic_hash != expected_deterministic:
            raise BoreenmannaAuditIntegrityError("integrity-audit hash mismatch")
        object.__setattr__(self, "deterministic_hash", expected_deterministic)
        expected_package = stable_hash(
            "boreenmanna-integrity-audit-package",
            {
                "deterministic_hash": expected_deterministic,
                "performance": json.loads(self.performance_json),
            },
        )
        if self.package_hash and self.package_hash != expected_package:
            raise BoreenmannaAuditIntegrityError("integrity package hash mismatch")
        object.__setattr__(self, "package_hash", expected_package)

    def _deterministic_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "compilation_package_hash": self.compilation_package_hash,
            "original_matrix_hash": self.original_matrix_hash,
            "core_run_hashes": [item.deterministic_hash for item in self.core_runs],
            "parity_manifests": [item.to_dict() for item in self.parity_manifests],
            "phase_results": json.loads(self.phase_results_json),
            "scaling_results": json.loads(self.scaling_results_json),
            "periodic_gating": json.loads(self.periodic_gating_json),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self._deterministic_payload(),
            "core_runs": [item.to_dict() for item in self.core_runs],
            "performance": json.loads(self.performance_json),
            "deterministic_hash": self.deterministic_hash,
            "package_hash": self.package_hash,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        result = cls(
            compilation_package_hash=str(payload["compilation_package_hash"]),
            original_matrix_hash=str(payload["original_matrix_hash"]),
            core_runs=tuple(
                AuditedRunManifest.from_dict(item)
                for item in payload["core_runs"]  # type: ignore[index]
            ),
            parity_manifests=tuple(
                RepresentationParityManifest.from_dict(item)
                for item in payload["parity_manifests"]  # type: ignore[index]
            ),
            phase_results_json=canonical_json(payload["phase_results"]),
            scaling_results_json=canonical_json(payload["scaling_results"]),
            periodic_gating_json=canonical_json(payload["periodic_gating"]),
            performance_json=canonical_json(payload["performance"]),
            version=str(payload["version"]),
            deterministic_hash=str(payload.get("deterministic_hash", "")),
            package_hash=str(payload.get("package_hash", "")),
        )
        declared_hashes = payload.get("core_run_hashes")
        if declared_hashes != [item.deterministic_hash for item in result.core_runs]:
            raise BoreenmannaAuditIntegrityError("core-run hash index mismatch")
        return result

    @classmethod
    def from_json(cls, serialised: str) -> Self:
        payload = json.loads(serialised)
        if not isinstance(payload, dict):
            raise BoreenmannaAuditIntegrityError("audit package must be an object")
        return cls.from_dict(payload)


def engine_is_empty(engine: LoadingEngine) -> bool:
    """Return the explicit drain terminal condition.

    Fractional balances and other extension-owned nonphysical state do not keep
    an otherwise empty network alive.
    """

    if engine.pending_demands:
        return False
    return all(
        packet.lifecycle_state in (LifecycleState.COMPLETED, LifecycleState.CANCELLED)
        for packet in engine.packets.values()
    )


def drain_engine(
    engine: LoadingEngine,
    *,
    evaluation_horizon_tick: int,
    declared_demand_count: int,
    demand_origin_by_id: Mapping[str, str],
    policy: DrainPolicy,
    allocation_history: list[tuple[object, ...]] | None = None,
    lane_history: list[tuple[object, ...]] | None = None,
) -> DrainOutcome:
    """Continue ordinary loading with no new declarations until empty or capped."""

    if engine.current_tick != evaluation_horizon_tick:
        raise BoreenmannaAuditIntegrityError("drain must begin at evaluation horizon")
    if any(demand.departure_tick > evaluation_horizon_tick for demand in engine.pending_demands):
        raise BoreenmannaAuditIntegrityError(
            "drain contract cannot introduce post-evaluation demand"
        )
    completed_at_evaluation = len(engine.completed_packet_ids)
    pending_at_evaluation = len(engine.pending_demands)
    active_at_evaluation = sum(
        packet.lifecycle_state in (LifecycleState.IN_TRANSIT, LifecycleState.QUEUED)
        for packet in engine.packets.values()
    )
    residual_storage = sum(
        engine.link_storage(link_id).storage for link_id in engine.links
    )
    maximum_queue = sum(
        packet.lifecycle_state == LifecycleState.QUEUED
        for packet in engine.packets.values()
    )
    for _ in range(policy.maximum_drain_ticks):
        if engine_is_empty(engine):
            break
        engine.step()
        if allocation_history is not None:
            allocation_history.append(engine.node_transfer_traces())
        if lane_history is not None:
            allocator = getattr(engine, "lane_group_allocator", None)
            lane_history.append(
                ()
                if allocator is None
                else allocator.last_lane_group_allocation_traces
            )
        maximum_queue = max(
            maximum_queue,
            sum(
                packet.lifecycle_state == LifecycleState.QUEUED
                for packet in engine.packets.values()
            ),
        )
    reached_empty = engine_is_empty(engine)
    completion_tick_by_packet = {
        event.packet_id: event.physical_tick
        for event in engine.event_log
        if event.event_type == EventType.COMPLETED
    }
    demand_by_packet = {
        packet.demand_id: packet_id for packet_id, packet in engine.packets.items()
    }
    clearance: dict[str, list[int | None]] = defaultdict(list)
    for demand_id, origin_link in demand_origin_by_id.items():
        packet_id = demand_by_packet.get(demand_id)
        clearance[origin_link].append(
            None if packet_id is None else completion_tick_by_packet.get(packet_id)
        )
    clearance_by_origin = tuple(
        (
            origin,
            (
                max(tick for tick in ticks if tick is not None)
                if ticks and all(tick is not None for tick in ticks)
                else None
            ),
        )
        for origin, ticks in sorted(clearance.items())
    )
    active_ids = tuple(
        sorted(
            packet_id
            for packet_id, packet in engine.packets.items()
            if packet.lifecycle_state in (LifecycleState.IN_TRANSIT, LifecycleState.QUEUED)
        )
    )
    pending_ids = tuple(
        sorted(f"demand:{item.demand_id}" for item in engine.pending_demands)
    )
    eventual_completed = len(engine.completed_packet_ids)
    if eventual_completed + len(active_ids) + len(pending_ids) != declared_demand_count:
        raise BoreenmannaAuditIntegrityError("drain demand ledger does not close")
    final_completion_tick = (
        max(completion_tick_by_packet.values()) if completion_tick_by_packet else None
    )
    return DrainOutcome(
        evaluation_horizon_tick=evaluation_horizon_tick,
        completed_at_evaluation=completed_at_evaluation,
        pending_demand_at_evaluation=pending_at_evaluation,
        physically_active_at_evaluation=active_at_evaluation,
        residual_vehicle_storage_at_evaluation=residual_storage,
        eventually_completed=eventual_completed,
        residual_pending_demand=len(pending_ids),
        residual_active_packets=len(active_ids),
        final_completion_tick=final_completion_tick,
        drain_duration_ticks=engine.current_tick - evaluation_horizon_tick,
        maximum_queue_during_drain=maximum_queue,
        reached_empty_condition=reached_empty,
        reached_maximum_drain_horizon=not reached_empty,
        terminal_tick=engine.current_tick,
        clearance_tick_by_origin_link=clearance_by_origin,
        unresolved_ids=(*pending_ids, *active_ids),
        policy_hash=policy.policy_hash,
    )


def shifted_signal_plan(
    plan: ResolvedFixedTimeSignalPlan,
    offset_delta_ticks: int,
) -> ResolvedFixedTimeSignalPlan:
    return ResolvedFixedTimeSignalPlan(
        controllers=tuple(
            replace(controller, offset_ticks=controller.offset_ticks + offset_delta_ticks)
            for controller in plan.controllers
        ),
        provenance_refs=plan.provenance_refs,
        metadata=(*plan.metadata, ("audit_offset_delta_ticks", str(offset_delta_ticks))),
    )


def _service_config_for_mode(executable, service_mode: str):
    if service_mode == DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE:
        return discharge_readiness_config_for_executable(executable)
    if service_mode == GATE_AWARE_FRACTIONAL_SERVICE_MODE:
        return gate_aware_service_config_for_executable(executable)
    if service_mode not in SERVICE_MODES:
        raise BoreenmannaAuditIntegrityError(
            f"unsupported Boreenmanna service policy: {service_mode}"
        )
    return service_credit_config_for_executable(executable, mode=service_mode)


def build_representation_parity_manifest(
    compilation: BoreenmannaExperimentCompilation,
    scenario: SyntheticDemandScenario,
    service_mode: str,
    *,
    offset_ticks: int,
    drain_policy: DrainPolicy,
    service_config_override=None,
) -> RepresentationParityManifest:
    executable = compilation.synthetic_result.require_executable()
    plan = shifted_signal_plan(executable.signal_plan, offset_ticks)
    service_config = service_config_override or _service_config_for_mode(
        executable, service_mode
    )
    nodes = executable.topology.as_loading_nodes()
    common_topology = {
        "links": [item.to_dict() for item in executable.resolved_links],
        "nodes": [
            {
                "node_id": node.node_id,
                "incoming_link_ids": list(node.incoming_link_ids),
                "outgoing_link_ids": list(node.outgoing_link_ids),
                "movements": [
                    {
                        "movement_id": movement.movement_id,
                        "upstream_link_id": movement.upstream_link_id,
                        "downstream_link_id": movement.downstream_link_id,
                        "priority_weight": movement.priority_weight,
                        "conflict_resource_ids": list(movement.conflict_resource_ids),
                        "signal_group_id": movement.signal_group_id,
                    }
                    for movement in node.junction_spec.movement_specs
                ],
                "conflict_resource_ids": list(node.junction_spec.conflict_resource_ids),
            }
            for node in nodes
        ],
    }
    common = {
        "source_file_sha256": compilation.base.package.source.file_sha256,
        "extraction_hash": compilation.base.package.extraction.extraction_hash,
        "normalized_topology_evidence_hash": (
            compilation.synthetic_result.evidence_bundle.normalized_evidence_hash
        ),
        "reviewed_physical_assumptions_hash": stable_hash(
            "reviewed-assumptions",
            [item.to_dict() for item in compilation.base.package.reviewed_assumptions],
        ),
        "synthetic_controller_dossier_hash": compilation.dossier.dossier_hash,
        "signal_plan_semantic_hash": plan.semantic_hash,
        "signal_plan_configuration_hash": plan.configuration_hash,
        "demand_scenario_hash": scenario.scenario_hash,
        "route_and_departure_hash": stable_hash(
            "route-and-departure",
            [item.to_dict() for item in scenario.demands],
        ),
        "fixed_seed": scenario.fixed_seed,
        "tick_duration_seconds": executable.tick_duration_seconds,
        "continuous_capacity_configuration": service_config.to_dict(),
        "service_credit_configuration_hash": service_config.config_hash,
        "evaluation_horizon_ticks": scenario.horizon_ticks,
        "drain_policy": drain_policy.to_dict(),
        "drain_policy_hash": drain_policy.policy_hash,
        "routing_configuration": "immutable_declared_route_intent:v1",
        "governance_state": "baseline_open_except_fixed_time_signal_gates",
        "common_topology_hash": stable_hash(
            "representation-common-topology", common_topology
        ),
        "executable_semantic_hash": executable.executable_semantic_hash,
    }
    variants = []
    for representation in REPRESENTATION_MODES:
        lane_config = LaneGroupExtensionConfig(
            representation_mode=representation,
            lane_groups=executable.lane_group_config.lane_groups,
        )
        specific: dict[str, object] = {
            "representation_mode": representation,
            "representation_configuration_hash": lane_config.config_hash,
        }
        if representation == SHARED_LINK_FIFO:
            specific.update(
                fifo_policy="strict_shared_link_fifo",
                queue_partition="one_conservative_shared_approach_queue",
            )
        elif representation == MOVEMENT_PARTIAL_FIFO:
            specific.update(
                fifo_policy="movement_partial_fifo",
                queue_partition="experimental_movement_coupling_without_lane_claim",
            )
        else:
            specific.update(
                fifo_policy="explicit_lane_group_fifo",
                queue_partition="synthetic_lane_group_queues",
                lane_group_declarations=[
                    asdict(item) for item in executable.lane_group_config.lane_groups
                ],
                packet_group_assignment_policy="route_next_movement_to_declared_group",
            )
        variants.append(
            RepresentationVariantManifest(
                representation_mode=representation,
                common_input_json=canonical_json(common),
                representation_input_json=canonical_json(specific),
            )
        )
    return RepresentationParityManifest(
        family_id=(
            f"{scenario.scenario_id}:{service_mode}:offset-{offset_ticks}:"
            f"drain-{drain_policy.maximum_drain_ticks}"
        ),
        variants=tuple(variants),
    )


def run_audited_case(
    compilation: BoreenmannaExperimentCompilation,
    scenario: SyntheticDemandScenario,
    representation: str,
    service_mode: str,
    *,
    offset_ticks: int = 0,
    drain_policy: DrainPolicy | None = None,
    verify_replay: bool = True,
    service_config_override=None,
) -> AuditedRunManifest:
    policy = drain_policy or DrainPolicy()
    tracemalloc.start()
    wall_start = perf_counter()
    cpu_start = process_time()
    first = _execute_audited_case(
        compilation,
        scenario,
        representation,
        service_mode,
        offset_ticks=offset_ticks,
        drain_policy=policy,
        service_config_override=service_config_override,
    )
    cpu_seconds = process_time() - cpu_start
    wall_seconds = perf_counter() - wall_start
    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    replay_seconds = 0.0
    if verify_replay:
        replay_start = perf_counter()
        replay = _execute_audited_case(
            compilation,
            scenario,
            representation,
            service_mode,
            offset_ticks=offset_ticks,
            drain_policy=policy,
            service_config_override=service_config_override,
        )
        replay_seconds = perf_counter() - replay_start
        if first["replay_payload"] != replay["replay_payload"]:
            raise BoreenmannaAuditIntegrityError("audited run exact replay mismatch")
        if first.get("extension_replay") != replay.get("extension_replay"):
            raise BoreenmannaAuditIntegrityError(
                "audited runtime-extension exact replay mismatch"
            )
    deterministic = dict(first["summary"])
    deterministic["replay_passed"] = verify_replay
    return AuditedRunManifest(
        deterministic_payload_json=canonical_json(deterministic),
        performance_payload_json=canonical_json(
            {
                "measurement_class": "machine_dependent",
                "wall_clock_seconds": wall_seconds,
                "cpu_seconds": cpu_seconds,
                "peak_memory_bytes": peak_memory,
                "replay_wall_clock_seconds": replay_seconds,
            }
        ),
    )


def _execute_audited_case(
    compilation: BoreenmannaExperimentCompilation,
    scenario: SyntheticDemandScenario,
    representation: str,
    service_mode: str,
    *,
    offset_ticks: int,
    drain_policy: DrainPolicy,
    service_config_override=None,
) -> dict[str, object]:
    executable = compilation.synthetic_result.require_executable()
    nodes = executable.topology.as_loading_nodes()
    lane_config = LaneGroupExtensionConfig(
        representation_mode=representation,
        lane_groups=executable.lane_group_config.lane_groups,
    )
    service_config = service_config_override or _service_config_for_mode(
        executable, service_mode
    )
    plan = shifted_signal_plan(executable.signal_plan, offset_ticks)
    provider = FixedTimeSignalPlanEvaluator(plan, nodes)
    if service_mode == DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE:
        engine = _BoreenmannaV3Engine(
            links=executable.loading_links(),
            nodes=nodes,
            lane_group_config=lane_config,
            fixed_time_signal_provider=provider,
            discharge_readiness_config=service_config,
            executable_semantic_hash=executable.executable_semantic_hash,
        )
    elif service_mode == GATE_AWARE_FRACTIONAL_SERVICE_MODE:
        engine = _BoreenmannaV2Engine(
            links=executable.loading_links(),
            nodes=nodes,
            lane_group_config=lane_config,
            fixed_time_signal_provider=provider,
            gate_aware_fractional_service_config=service_config,
            executable_semantic_hash=executable.executable_semantic_hash,
        )
    else:
        engine = _BoreenmannaEngine(
            links=executable.loading_links(),
            nodes=nodes,
            lane_group_config=lane_config,
            fixed_time_signal_provider=provider,
            fractional_service_credit_config=service_config,
            executable_semantic_hash=executable.executable_semantic_hash,
        )
    for demand in scenario.demands:
        engine.instantiate(demand.declaration())
    allocation_history: list[tuple[object, ...]] = []
    lane_history: list[tuple[object, ...]] = []
    for _ in range(scenario.horizon_ticks):
        engine.step()
        allocation_history.append(engine.node_transfer_traces())
        lane_history.append(
            engine.lane_group_allocator.last_lane_group_allocation_traces
        )
    evaluation_metrics = _deterministic_metrics(
        engine, allocation_history, scenario, provider
    )
    evaluation_readiness_summary = (
        engine.discharge_readiness_summary
        if service_mode == DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE
        else None
    )
    evaluation_payload = _replay_payload(engine, allocation_history, lane_history)
    demand_origins = {
        item.demand_id: item.route_intent[0] for item in scenario.demands
    }
    drain = drain_engine(
        engine,
        evaluation_horizon_tick=scenario.horizon_ticks,
        declared_demand_count=len(scenario.demands),
        demand_origin_by_id=demand_origins,
        policy=drain_policy,
        allocation_history=allocation_history,
        lane_history=lane_history,
    )
    full_metrics = _deterministic_metrics(engine, allocation_history, scenario, provider)
    replay_payload = _replay_payload(engine, allocation_history, lane_history)
    extension_replay: dict[str, object] = {}
    if service_mode == DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE:
        replay_payload["readiness_evidence"] = [
            item.to_dict() for item in engine.discharge_readiness_evidence
        ]
        replay_payload["logical_evidence_digest"] = engine.logical_evidence_digest
        replay_payload["readiness_summary"] = engine.discharge_readiness_summary
        extension_replay = {
            "logical_evidence_digest": engine.logical_evidence_digest,
            "logical_evidence_record_count": engine.logical_evidence_record_count,
            "readiness_summary": engine.discharge_readiness_summary,
            "physical_config_hash": service_config.config_hash,
            "recording_config_hash": service_config.recording_config_hash,
        }
    volume = _evidence_volume(
        compilation=compilation,
        scenario=scenario,
        engine=engine,
        replay_payload=replay_payload,
        allocation_history=allocation_history,
    )
    parity = build_representation_parity_manifest(
        compilation,
        scenario,
        service_mode,
        offset_ticks=offset_ticks,
        drain_policy=drain_policy,
        service_config_override=service_config,
    )
    summary = {
        "scenario_id": scenario.scenario_id,
        "service_credit_mode": service_mode,
        "representation_mode": representation,
        "offset_ticks": offset_ticks,
        "evaluation_horizon_ticks": scenario.horizon_ticks,
        "evaluation_metrics": evaluation_metrics,
        "evaluation_replay_hash": stable_hash(
            "boreenmanna-evaluation-replay", evaluation_payload
        ),
        "drain_outcome": drain.to_dict(),
        "eventual_metrics": {
            "completed_throughput": full_metrics["completed_throughput"],
            "incomplete_packets": full_metrics["incomplete_packets"],
            "terminal_tick": full_metrics["terminal_tick"],
            "canonical_event_count": full_metrics["canonical_event_count"],
            "blocked_transfer_requests_by_reason": full_metrics[
                "blocked_transfer_requests_by_reason"
            ],
            "spillback_occurrence": full_metrics["spillback_occurrence"],
            "spillback_duration_ticks": full_metrics["spillback_duration_ticks"],
            "movement_throughput": full_metrics["movement_throughput"],
        },
        "evidence_volume": volume,
        "parity_family_id": parity.family_id,
        "parity_common_input_hash": parity.common_input_hash,
        "representation_input_hash": next(
            item.representation_input_hash
            for item in parity.variants
            if item.representation_mode == representation
        ),
        "signal_plan_semantic_hash": plan.semantic_hash,
        "service_credit_configuration_hash": service_config.config_hash,
        "drain_policy_hash": drain_policy.policy_hash,
        "physical_event_log_hash": stable_hash(
            "boreenmanna-audited-events", replay_payload["events"]
        ),
        "credit_evidence_hash": engine.fractional_service_credit_evidence_hash,
        "signal_evidence_hash": engine.fixed_time_signal_evidence_hash,
        "replay_payload_hash": stable_hash(
            "boreenmanna-audited-replay", replay_payload
        ),
        "conservation_passed": engine.check_conservation(),
        "event_cache_consistency_passed": engine.check_event_cache_consistency(),
        "count_consistency_passed": engine.count_consistency_report().is_consistent,
    }
    if service_mode == DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE:
        summary.update(
            {
                "readiness_physical_config_hash": service_config.config_hash,
                "readiness_recording_config_hash": service_config.recording_config_hash,
                "readiness_evidence_mode": service_config.evidence_mode,
                "readiness_logical_evidence_digest": engine.logical_evidence_digest,
                "readiness_logical_evidence_record_count": (
                    engine.logical_evidence_record_count
                ),
                "readiness_retained_record_count": (
                    engine.retained_logical_evidence_record_count
                ),
                "readiness_summary": engine.discharge_readiness_summary,
                "evaluation_readiness_summary": evaluation_readiness_summary,
            }
        )
    return {
        "summary": summary,
        "replay_payload": replay_payload,
        "extension_replay": extension_replay,
    }


def _evidence_volume(
    *,
    compilation: BoreenmannaExperimentCompilation,
    scenario: SyntheticDemandScenario,
    engine,
    replay_payload: Mapping[str, object],
    allocation_history: list[tuple[object, ...]],
) -> dict[str, object]:
    event_count = len(engine.event_log)
    credit_count = len(engine.fractional_service_credit_evidence)
    readiness_count = len(getattr(engine, "discharge_readiness_evidence", ()))
    signal_count = len(engine.fixed_time_signal_evidence)
    allocation_count = sum(len(item) for item in allocation_history)
    allocation_bytes = len(
        canonical_json(
            [[asdict(trace) for trace in traces] for traces in allocation_history]
        ).encode("utf-8")
    )
    compiler_bytes = len(compilation.package.to_json().encode("utf-8"))
    replay_bytes = len(canonical_json(replay_payload).encode("utf-8"))
    demand_bytes = len(canonical_json(scenario.to_dict()).encode("utf-8"))
    deterministic_total = compiler_bytes + replay_bytes + demand_bytes
    evidence_records = credit_count + signal_count + len(scenario.demands) + allocation_count
    return {
        "simulation_ticks": engine.current_tick,
        "link_count": len(engine.links),
        "packet_count": len(scenario.demands),
        "physical_event_count": event_count,
        "fractional_credit_evidence_count": credit_count,
        "readiness_evidence_count": readiness_count,
        "logical_credit_evidence_count": getattr(
            engine, "logical_evidence_record_count", credit_count
        ),
        "retained_logical_evidence_count": getattr(
            engine, "retained_logical_evidence_record_count", credit_count
        ),
        "signal_evidence_count": signal_count,
        "routing_evidence_count": len(scenario.demands),
        "allocation_trace_count": allocation_count,
        "allocation_trace_bytes": allocation_bytes,
        "compiler_evidence_bytes": compiler_bytes,
        "replay_artifact_bytes": replay_bytes,
        "run_evidence_bytes": replay_bytes,
        "total_deterministic_artifact_bytes": deterministic_total,
        "bytes_per_packet": deterministic_total / len(scenario.demands),
        "bytes_per_physical_event": (
            deterministic_total / event_count if event_count else None
        ),
        "credit_records_per_tick": credit_count / engine.current_tick,
        "evidence_record_to_physical_event_ratio": (
            evidence_records / event_count if event_count else None
        ),
    }


def periodic_gating_validation(
    *,
    rate: float = 0.25,
    cycle_ticks: int = 4,
    green_ticks: int = 2,
    horizon_ticks: int = 32,
    offsets: tuple[int, ...] = (0, 2),
) -> dict[str, object]:
    """Compare the v1 recurrence with a saturated signal-gated two-link fixture."""

    results = []
    for offset in offsets:
        engine, movement_id, provider = _periodic_fixture_engine(
            rate=rate,
            cycle_ticks=cycle_ticks,
            green_ticks=green_ticks,
            offset_ticks=offset,
        )
        demand_count = max(16, horizon_ticks * 2)
        for index in range(demand_count):
            engine.instantiate(DemandDeclaration(f"periodic:{index}", 0, ("U", "D")))
        for _ in range(horizon_ticks):
            engine.step()
        observed = tuple(
            item.physical_tick
            for item in engine.event_log
            if item.event_type == EventType.LINK_ENTRY and item.entity_id == "D"
        )
        carry = 0.0
        expected = []
        opportunity_ticks = []
        for tick in range(1, horizon_ticks + 1):
            available = carry + rate
            whole = floor(available)
            carry = available - whole
            if whole:
                opportunity_ticks.extend((tick,) * whole)
                state = provider.evaluate(movement_id, tick)
                if state is not None and state.baseline_is_open:
                    expected.extend((tick,) * whole)
        if observed != tuple(expected):
            raise BoreenmannaAuditIntegrityError(
                "periodic-gating implementation does not match recurrence"
            )
        results.append(
            {
                "offset_ticks": offset,
                "opportunity_ticks": opportunity_ticks,
                "expected_service_ticks": expected,
                "observed_service_ticks": list(observed),
                "service_count": len(observed),
            }
        )
    payload = {
        "fixture": "saturated_two_link_periodic_gate",
        "rate_packets_per_tick": rate,
        "cycle_ticks": cycle_ticks,
        "green_ticks": green_ticks,
        "horizon_ticks": horizon_ticks,
        "sending_interpretation": (
            "per_tick_service_opportunity; unused whole opportunity expires while "
            "fractional phase continues"
        ),
        "results": results,
    }
    return {**payload, "validation_hash": stable_hash("periodic-gating-audit", payload)}


class _PeriodicEngine(
    FixedTimeSignalControlMixin,
    FractionalServiceCreditMixin,
    LoadingEngine,
):
    pass


class _PeriodicV2Engine(
    FixedTimeSignalControlMixin,
    GateAwareFractionalServiceMixin,
    LoadingEngine,
):
    pass


class _PeriodicV3Engine(
    FixedTimeSignalControlMixin,
    DischargeReadinessFractionalServiceMixin,
    LoadingEngine,
):
    pass


class _BoreenmannaV2Engine(
    FixedTimeSignalControlMixin,
    GateAwareFractionalServiceMixin,
    LaneGroupLoadingEngine,
):
    pass


class _BoreenmannaV3Engine(
    FixedTimeSignalControlMixin,
    DischargeReadinessFractionalServiceMixin,
    LaneGroupLoadingEngine,
):
    pass


def _periodic_fixture_engine(
    *,
    rate: float,
    cycle_ticks: int,
    green_ticks: int,
    offset_ticks: int,
    service_mode: str = FRACTIONAL_CREDIT,
    v3_config: DischargeReadinessConfig | None = None,
):
    links = {
        link_id: Link(
            link_id=link_id,
            free_flow_ticks=1,
            declared_sending_capacity_per_tick=1,
            declared_receiving_capacity_per_tick=1,
            declared_storage_capacity_packets=200,
            length_m=10.0,
            lane_count=1,
            free_flow_speed_mps=10.0,
            jam_density_veh_per_km_per_lane=20_000.0,
            backward_wave_speed_mps=10.0,
            capacity_veh_per_hour_per_lane=(rate if link_id == "U" else 10.0) * 3600,
            tick_duration_seconds=1.0,
        )
        for link_id in ("U", "D")
    }
    movement = MovementSpec("U", "D", signal_group_id="signal:periodic")
    movement_id = movement.movement_id
    node = Node(
        "N",
        incoming_link_ids=("U",),
        outgoing_link_ids=("D",),
        junction_spec=JunctionSpec(
            node_id="N",
            incoming_link_ids=("U",),
            outgoing_link_ids=("D",),
            movement_specs=(movement,),
        ),
    )
    stages = (
        (FixedTimeStage("stage:green", green_ticks, (movement_id,)),)
        if green_ticks == cycle_ticks
        else (
            FixedTimeStage("stage:green", green_ticks, (movement_id,)),
            FixedTimeStage("stage:red", cycle_ticks - green_ticks, ()),
        )
    )
    plan = ResolvedFixedTimeSignalPlan(
        controllers=(
            FixedTimeControllerPlan(
                controller_id="controller:periodic",
                node_id="N",
                cycle_ticks=cycle_ticks,
                offset_ticks=offset_ticks,
                stages=stages,
                controlled_movement_ids=(movement_id,),
            ),
        )
    )
    provider = FixedTimeSignalPlanEvaluator(plan, (node,))
    common = {
        "links": links,
        "nodes": (node,),
        "node_transfer_policy": GeneralMovementAllocator((node,)),
        "fixed_time_signal_provider": provider,
        "executable_semantic_hash": "periodic-gating-fixture",
    }
    if service_mode == DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE:
        engine = _PeriodicV3Engine(
            **common,
            discharge_readiness_config=v3_config
            or DischargeReadinessConfig(
                continuous_capacity_by_link=(("U", rate), ("D", 10.0)),
                tick_duration_seconds_by_link=(("U", 1.0), ("D", 1.0)),
                controlled_readiness_link_ids=("U",),
                tau_green_seconds=2.0,
                tau_red_seconds=10.0,
                initial_readiness_by_domain=(("U", 1.0),),
            ),
        )
    elif service_mode == GATE_AWARE_FRACTIONAL_SERVICE_MODE:
        engine = _PeriodicV2Engine(
            **common,
            gate_aware_fractional_service_config=GateAwareFractionalServiceConfig(
                (("U", rate), ("D", 10.0))
            ),
        )
    elif service_mode == FRACTIONAL_CREDIT:
        engine = _PeriodicEngine(
            **common,
            fractional_service_credit_config=FractionalServiceCreditConfig(
                mode=FRACTIONAL_CREDIT,
                continuous_capacity_by_link=(("U", rate), ("D", 10.0)),
            ),
        )
    else:
        raise BoreenmannaAuditIntegrityError(
            f"unsupported periodic fixture service mode: {service_mode}"
        )
    return engine, movement_id, provider


def run_boreenmanna_integrity_audit(
    source_path: str | Path,
    *,
    original_matrix_hash: str,
    phase_offsets: tuple[int, ...] = DEFAULT_PHASE_OFFSETS,
    drain_policy: DrainPolicy | None = None,
) -> tuple[
    BoreenmannaExperimentCompilation,
    tuple[SyntheticDemandScenario, ...],
    BoreenmannaIntegrityAuditPackage,
]:
    policy = drain_policy or DrainPolicy()
    compilation = compile_boreenmanna_experiment(source_path)
    scenarios = build_boreenmanna_demand_scenarios(compilation)
    audit_start = perf_counter()
    core_runs = tuple(
        run_audited_case(
            compilation,
            scenario,
            representation,
            service_mode,
            drain_policy=policy,
            verify_replay=True,
        )
        for scenario in scenarios
        for service_mode in SERVICE_MODES
        for representation in REPRESENTATION_MODES
    )
    phase_runs = []
    parity_manifests = []
    for scenario in scenarios:
        for service_mode in SERVICE_MODES:
            for offset in phase_offsets:
                parity_manifests.append(
                    build_representation_parity_manifest(
                        compilation,
                        scenario,
                        service_mode,
                        offset_ticks=offset,
                        drain_policy=policy,
                    )
                )
                for representation in REPRESENTATION_MODES:
                    run = run_audited_case(
                        compilation,
                        scenario,
                        representation,
                        service_mode,
                        offset_ticks=offset,
                        drain_policy=policy,
                        verify_replay=False,
                    )
                    deterministic = run.deterministic
                    evaluation = deterministic["evaluation_metrics"]
                    drain = deterministic["drain_outcome"]
                    volume = deterministic["evidence_volume"]
                    phase_runs.append(
                        {
                            "scenario_id": scenario.scenario_id,
                            "service_credit_mode": service_mode,
                            "representation_mode": representation,
                            "offset_ticks": offset,
                            "completed_at_evaluation": evaluation["completed_throughput"],
                            "eventually_completed": drain["eventually_completed"],
                            "mean_queue_delay_ticks": evaluation[
                                "mean_queue_delay_ticks"
                            ],
                            "peak_queue": evaluation["peak_queue"],
                            "movement_throughput": evaluation["movement_throughput"],
                            "final_completion_tick": drain["final_completion_tick"],
                            "fractional_credit_evidence_count": volume[
                                "fractional_credit_evidence_count"
                            ],
                            "blocked_transfer_requests_by_reason": evaluation[
                                "blocked_transfer_requests_by_reason"
                            ],
                            "deterministic_run_hash": run.deterministic_hash,
                        }
                    )
    phase_payload = {
        "offsets_ticks": list(phase_offsets),
        "runs": phase_runs,
        "sensitivity_summary": _phase_sensitivity_summary(phase_runs),
    }
    scaling_payload = _run_scaling_audit(compilation, policy)
    periodic_payload = periodic_gating_validation()
    elapsed = perf_counter() - audit_start
    package = BoreenmannaIntegrityAuditPackage(
        compilation_package_hash=compilation.package.package_hash,
        original_matrix_hash=original_matrix_hash,
        core_runs=core_runs,
        parity_manifests=tuple(parity_manifests),
        phase_results_json=canonical_json(phase_payload),
        scaling_results_json=canonical_json(scaling_payload),
        periodic_gating_json=canonical_json(periodic_payload),
        performance_json=canonical_json(
            {
                "measurement_class": "machine_dependent",
                "complete_audit_wall_clock_seconds": elapsed,
            }
        ),
    )
    return compilation, scenarios, package


def _phase_sensitivity_summary(runs: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for run in runs:
        grouped[
            (
                str(run["scenario_id"]),
                str(run["service_credit_mode"]),
                str(run["representation_mode"]),
            )
        ].append(run)
    summary = []
    for key, values in sorted(grouped.items()):
        completions = [int(item["completed_at_evaluation"]) for item in values]
        clearance = [int(item["final_completion_tick"]) for item in values]
        delays = [float(item["mean_queue_delay_ticks"]) for item in values]
        summary.append(
            {
                "scenario_id": key[0],
                "service_credit_mode": key[1],
                "representation_mode": key[2],
                "evaluation_completion_range": max(completions) - min(completions),
                "clearance_tick_range": max(clearance) - min(clearance),
                "mean_queue_delay_range": max(delays) - min(delays),
            }
        )
    return summary


def _run_scaling_audit(
    compilation: BoreenmannaExperimentCompilation,
    policy: DrainPolicy,
) -> dict[str, object]:
    executable = compilation.synthetic_result.require_executable()
    routes = _principal_routes(executable.resolved_links, executable.topology.nodes)
    cases = []
    for multiplier in (1, 2, 4):
        scenario = _demand_scenario(
            f"scaling-{multiplier}x",
            routes,
            copies=multiplier,
            horizon=120,
        )
        run = run_audited_case(
            compilation,
            scenario,
            EXPLICIT_LANE_GROUP_FIFO,
            FRACTIONAL_CREDIT,
            drain_policy=policy,
            verify_replay=False,
        )
        cases.append(
            {
                "demand_multiplier": multiplier,
                "demand_packet_count": len(scenario.demands),
                **run.deterministic["evidence_volume"],
            }
        )
    return {
        "controlled_topology": "Boreenmanna explicit-lane-group fractional mode",
        "cases": cases,
        "interpretation": (
            "credit evidence is dominated by ticks times two link accounts; packet-"
            "dependent physical and routing evidence grows with demand"
        ),
    }


def write_boreenmanna_integrity_audit_outputs(
    package: BoreenmannaIntegrityAuditPackage,
    output_directory: str | Path,
) -> tuple[Path, ...]:
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    package_path = directory / "boreenmanna_integrity_audit_v1.json"
    core_csv = directory / "boreenmanna_audited_core_matrix_v2.csv"
    phase_csv = directory / "boreenmanna_phase_sensitivity_v1.csv"
    package_path.write_text(package.to_json(), encoding="utf-8")
    core_columns = (
        "scenario_id",
        "service_credit_mode",
        "representation_mode",
        "completed_at_evaluation",
        "incomplete_at_evaluation",
        "pending_at_evaluation",
        "physically_active_at_evaluation",
        "eventually_completed",
        "drain_duration_ticks",
        "final_completion_tick",
        "residual_unresolved",
        "mean_queue_delay_ticks",
        "peak_queue",
        "canonical_event_count_at_evaluation",
        "total_canonical_event_count",
        "deterministic_evidence_bytes",
        "deterministic_hash",
    )
    rows = [",".join(core_columns)]
    for run in package.core_runs:
        data = run.deterministic
        evaluation = data["evaluation_metrics"]
        drain = data["drain_outcome"]
        eventual = data["eventual_metrics"]
        volume = data["evidence_volume"]
        rows.append(
            ",".join(
                str(item)
                for item in (
                    data["scenario_id"],
                    data["service_credit_mode"],
                    data["representation_mode"],
                    evaluation["completed_throughput"],
                    evaluation["incomplete_packets"],
                    drain["pending_demand_at_evaluation"],
                    drain["physically_active_at_evaluation"],
                    drain["eventually_completed"],
                    drain["drain_duration_ticks"],
                    drain["final_completion_tick"],
                    drain["residual_pending_demand"] + drain["residual_active_packets"],
                    evaluation["mean_queue_delay_ticks"],
                    evaluation["peak_queue"],
                    evaluation["canonical_event_count"],
                    eventual["canonical_event_count"],
                    volume["total_deterministic_artifact_bytes"],
                    run.deterministic_hash,
                )
            )
        )
    core_csv.write_text("\n".join(rows) + "\n", encoding="utf-8")
    phase = json.loads(package.phase_results_json)
    phase_columns = (
        "scenario_id",
        "service_credit_mode",
        "representation_mode",
        "offset_ticks",
        "completed_at_evaluation",
        "eventually_completed",
        "mean_queue_delay_ticks",
        "peak_queue",
        "final_completion_tick",
        "fractional_credit_evidence_count",
        "deterministic_run_hash",
    )
    rows = [",".join(phase_columns)]
    for run in phase["runs"]:
        rows.append(",".join(str(run[column]) for column in phase_columns))
    phase_csv.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return package_path, core_csv, phase_csv
