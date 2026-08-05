"""Deterministic staged compiler from imperfect evidence to executable artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil, floor
from typing import Callable, Iterable

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import Link, MovementSpec, Node
from urban_cybernetics.extensions.fixed_time_signals import (
    FixedTimeControllerPlan,
    FixedTimeSignalControlMixin,
    FixedTimeSignalPlanEvaluator,
    FixedTimeStage,
    ResolvedFixedTimeSignalPlan,
    ResolvedValueProvenance,
)
from urban_cybernetics.loading.lane_group_extension import (
    EXPLICIT_LANE_GROUP_FIFO,
    SHARED_LINK_FIFO,
    ExplicitLaneGroup,
    LaneGroupExtensionConfig,
    LaneGroupLoadingEngine,
    LaneGroupProvenance,
)
from urban_cybernetics.topology import (
    CanonicalNode,
    CanonicalTopology,
    CanonicalTopologyLink,
    TopologySourceMetadata,
)

from .adapter import normalize_source
from .model import (
    COMPILER_VERSION,
    DISCRETIZATION_POLICY_VERSION,
    EXECUTABLE_SEMANTIC_SCHEMA_VERSION,
    RULES,
    RULESET_VERSION,
    ROUND_CEIL_MIN_ONE,
    ROUND_FLOOR_MIN_ONE,
    ROUND_NONE,
    CompilationDisposition,
    CompilerConfig,
    CompilerDiagnostic,
    CompilerEvidenceBundle,
    CompilerOverride,
    DiagnosticSeverity,
    NormalizedField,
    NormalizedRecord,
    NormalizedSourceGraph,
    PhysicalDerivationRecord,
    ProvenanceClass,
    ProvenanceRecord,
    SourceNetworkEvidence,
    canonical_json,
    stable_hash,
)


MANDATORY_LINK_FIELDS = (
    "tail_node_id",
    "head_node_id",
    "travel_direction",
    "length_m",
    "lane_count",
    "free_flow_speed_mps",
    "capacity_veh_per_hour_per_lane",
    "jam_density_veh_per_km_per_lane",
    "backward_wave_speed_mps",
)


@dataclass(frozen=True, slots=True)
class ResolvedLink:
    """Resolved semantic link; optional values exist only before refusal."""

    link_id: str
    source_link_id: str
    tail_node_id: str | None
    head_node_id: str | None
    travel_direction: str | None
    road_class: str
    length_m: float | None
    lane_count: int | None
    free_flow_speed_mps: float | None
    capacity_veh_per_hour_per_lane: float | None
    jam_density_veh_per_km_per_lane: float | None
    backward_wave_speed_mps: float | None

    @property
    def is_executable(self) -> bool:
        return all(getattr(self, name) is not None for name in MANDATORY_LINK_FIELDS)

    @property
    def storage_capacity_packets(self) -> int | None:
        if self.length_m is None or self.lane_count is None or self.jam_density_veh_per_km_per_lane is None:
            return None
        return max(
            1,
            floor(
                self.length_m
                / 1000.0
                * self.lane_count
                * self.jam_density_veh_per_km_per_lane
            ),
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["storage_capacity_packets"] = self.storage_capacity_packets
        payload["semantic_hash"] = self.semantic_hash
        return payload

    @property
    def semantic_hash(self) -> str:
        return stable_hash(
            "resolved-link",
            {
                "compiler_version": COMPILER_VERSION,
                "ruleset_version": RULESET_VERSION,
                "value": asdict(self),
            },
        )


@dataclass(frozen=True, slots=True)
class ResolvedMovement:
    movement_id: str
    node_id: str
    upstream_link_id: str
    downstream_link_id: str
    permitted: bool | None
    priority_weight: int
    signal_group_id: str | None
    lane_indices: tuple[int, ...] = ()

    @property
    def semantic_hash(self) -> str:
        return stable_hash(
            "resolved-movement",
            {
                "compiler_version": COMPILER_VERSION,
                "ruleset_version": RULESET_VERSION,
                "value": asdict(self),
            },
        )

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "semantic_hash": self.semantic_hash}


@dataclass(frozen=True, slots=True)
class ResolvedSemanticGraph:
    links: tuple[ResolvedLink, ...]
    movements: tuple[ResolvedMovement, ...]

    @property
    def semantic_hash(self) -> str:
        return stable_hash(
            "resolved-semantic-graph",
            {
                "links": [item.to_dict() for item in self.links],
                "movements": [item.to_dict() for item in self.movements],
            },
        )


class CompiledNetworkLoadingEngine(FixedTimeSignalControlMixin, LaneGroupLoadingEngine):
    """Composition shell using existing signal and lane-group extension seams."""


@dataclass(frozen=True, slots=True)
class ExecutableNetwork:
    """Immutable artifacts accepted by the existing simulator extensions."""

    topology: CanonicalTopology
    signal_plan: ResolvedFixedTimeSignalPlan
    lane_group_config: LaneGroupExtensionConfig
    resolved_links: tuple[ResolvedLink, ...]
    physical_derivations: tuple[PhysicalDerivationRecord, ...]
    tick_duration_seconds: float

    def loading_links(self) -> dict[str, Link]:
        result: dict[str, Link] = {}
        for item in self.resolved_links:
            assert item.is_executable
            assert item.length_m is not None
            assert item.lane_count is not None
            assert item.free_flow_speed_mps is not None
            assert item.capacity_veh_per_hour_per_lane is not None
            assert item.jam_density_veh_per_km_per_lane is not None
            assert item.backward_wave_speed_mps is not None
            total_capacity = (
                item.capacity_veh_per_hour_per_lane
                * item.lane_count
                * self.tick_duration_seconds
                / 3600.0
            )
            integer_capacity = max(1, int(total_capacity))
            result[item.link_id] = Link(
                link_id=item.link_id,
                declared_sending_capacity_per_tick=integer_capacity,
                declared_receiving_capacity_per_tick=integer_capacity,
                declared_storage_capacity_packets=item.storage_capacity_packets,
                length_m=item.length_m,
                lane_count=item.lane_count,
                free_flow_speed_mps=item.free_flow_speed_mps,
                capacity_veh_per_hour_per_lane=item.capacity_veh_per_hour_per_lane,
                jam_density_veh_per_km_per_lane=item.jam_density_veh_per_km_per_lane,
                backward_wave_speed_mps=item.backward_wave_speed_mps,
                tick_duration_seconds=self.tick_duration_seconds,
            )
        return result

    def build_loading_engine(self) -> CompiledNetworkLoadingEngine:
        nodes = self.topology.as_loading_nodes()
        provider = FixedTimeSignalPlanEvaluator(self.signal_plan, nodes)
        return CompiledNetworkLoadingEngine(
            links=self.loading_links(),
            nodes=nodes,
            lane_group_config=self.lane_group_config,
            fixed_time_signal_provider=provider,
            model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        )

    @property
    def executable_topology_hash(self) -> str:
        """Hash only behaviour-consumed directed topology and loader link values."""

        return stable_hash("executable-topology", self.executable_topology_payload())

    def executable_topology_payload(self) -> dict[str, object]:
        return {
            "schema_version": EXECUTABLE_SEMANTIC_SCHEMA_VERSION,
            "discretization_policy_version": DISCRETIZATION_POLICY_VERSION,
            "model_profile_id": ACADEMIC_LTM_PARITY_PROFILE_ID,
            "tick_duration_seconds": self.tick_duration_seconds,
            "nodes": [
                _executable_node_payload(item)
                for item in sorted(self.topology.nodes, key=lambda value: value.node_id)
            ],
            "loading_links": [
                asdict(item)
                for item in sorted(
                    self.loading_links().values(), key=lambda value: value.link_id
                )
            ],
        }

    @property
    def executable_semantic_hash(self) -> str:
        """Compatibility identity for the complete behaviour-consumed network."""

        return stable_hash(
            "executable-network-semantics", self.executable_semantic_payload()
        )

    def executable_semantic_payload(self) -> dict[str, object]:
        return {
            "schema_version": EXECUTABLE_SEMANTIC_SCHEMA_VERSION,
            "executable_topology_hash": self.executable_topology_hash,
            "lane_group_semantics": _lane_group_semantic_payload(
                self.lane_group_config
            ),
            "signal_plan_semantic_hash": self.signal_plan.semantic_hash,
            "physical_derivation_semantics": [
                item.semantic_payload()
                for item in sorted(
                    self.physical_derivations,
                    key=lambda value: (value.artifact_id, value.target_field),
                )
            ],
        }

    @property
    def compatibility_hash(self) -> str:
        return self.executable_semantic_hash

    def to_dict(self) -> dict[str, object]:
        return {
            "canonical_topology_artifact_hash": self.topology.topology_hash,
            "executable_topology_hash": self.executable_topology_hash,
            "executable_semantic_hash": self.executable_semantic_hash,
            "executable_topology_payload": self.executable_topology_payload(),
            "executable_semantic_payload": self.executable_semantic_payload(),
            "links": [item.to_dict() for item in self.resolved_links],
            "nodes": [_canonical_node_payload(item) for item in self.topology.nodes],
            "signal_plan": self.signal_plan.to_dict(),
            "lane_group_config": asdict(self.lane_group_config),
            "loading_links": [
                asdict(item)
                for item in sorted(
                    self.loading_links().values(), key=lambda value: value.link_id
                )
            ],
            "physical_derivations": [
                item.to_dict() for item in self.physical_derivations
            ],
            "tick_duration_seconds": self.tick_duration_seconds,
        }


@dataclass(frozen=True, slots=True)
class CompilationResult:
    source_evidence: SourceNetworkEvidence
    normalized_graph: NormalizedSourceGraph
    resolved_graph: ResolvedSemanticGraph
    _executable: ExecutableNetwork | None
    diagnostics: tuple[CompilerDiagnostic, ...]
    provenance: tuple[ProvenanceRecord, ...]
    derivations: tuple[PhysicalDerivationRecord, ...]
    evidence_bundle: CompilerEvidenceBundle
    disposition: CompilationDisposition

    def __post_init__(self) -> None:
        successful = self.disposition in (
            CompilationDisposition.EXECUTABLE,
            CompilationDisposition.EXECUTABLE_WITH_WARNINGS,
        )
        if successful != (self._executable is not None):
            raise CompilationResultInvariantError(
                "successful disposition must be equivalent to executable artifact presence"
            )
        if self.evidence_bundle.disposition != self.disposition:
            raise CompilationResultInvariantError(
                "result disposition does not match its evidence bundle"
            )
        if self.evidence_bundle.diagnostics != self.diagnostics:
            raise CompilationResultInvariantError(
                "result diagnostics do not match its evidence bundle"
            )
        if self.evidence_bundle.provenance != self.provenance:
            raise CompilationResultInvariantError(
                "result provenance does not match its evidence bundle"
            )
        if self.evidence_bundle.derivations != self.derivations:
            raise CompilationResultInvariantError(
                "result derivations do not match its evidence bundle"
            )
        if self.source_evidence.evidence_hash != self.evidence_bundle.input_evidence_hash:
            raise CompilationResultInvariantError(
                "result source evidence does not match its evidence bundle"
            )
        if self.normalized_graph.normalized_hash != self.evidence_bundle.normalized_evidence_hash:
            raise CompilationResultInvariantError(
                "result normalized evidence does not match its evidence bundle"
            )
        if self._executable is not None and (
            self._executable.executable_topology_hash
            != self.evidence_bundle.executable_topology_hash
            or self._executable.executable_semantic_hash
            != self.evidence_bundle.executable_semantic_hash
        ):
            raise CompilationResultInvariantError(
                "executable hashes do not match the evidence bundle"
            )

    @property
    def is_executable(self) -> bool:
        return (
            self.disposition
            in (
                CompilationDisposition.EXECUTABLE,
                CompilationDisposition.EXECUTABLE_WITH_WARNINGS,
            )
            and self._executable is not None
        )

    def require_executable(self) -> ExecutableNetwork:
        """Return hash-validated output, or fail closed with compiler context."""

        if not self.is_executable or self._executable is None:
            raise CompilationNotExecutableError(
                self.disposition,
                tuple(sorted({item.code for item in self.diagnostics})),
            )
        if (
            self._executable.executable_semantic_hash
            != self.evidence_bundle.executable_semantic_hash
        ):
            raise CompilationResultInvariantError(
                "executable semantic hash no longer matches the evidence bundle"
            )
        return self._executable


class CompilationResultInvariantError(ValueError):
    """Raised when a compiler result is constructed in an unsafe state."""


class CompilationNotExecutableError(RuntimeError):
    """Raised when guarded executable access is requested for a refusal."""

    def __init__(
        self,
        disposition: CompilationDisposition,
        diagnostic_codes: tuple[str, ...],
    ) -> None:
        self.disposition = disposition
        self.diagnostic_codes = diagnostic_codes
        codes = ", ".join(diagnostic_codes) or "none"
        super().__init__(
            f"compilation disposition {disposition.value!r} is not executable; "
            f"diagnostic codes: {codes}"
        )


class _Context:
    def __init__(
        self,
        *,
        config: CompilerConfig,
        overrides: tuple[CompilerOverride, ...],
    ) -> None:
        self.config = config
        self.overrides = overrides
        self.diagnostics: list[CompilerDiagnostic] = []
        self.provenance: list[ProvenanceRecord] = []
        self.derivations: list[PhysicalDerivationRecord] = []
        self.used_override_ids: set[str] = set()
        self._overrides_by_target: dict[tuple[str, str], tuple[CompilerOverride, ...]] = {}
        for item in overrides:
            self._overrides_by_target.setdefault(
                (item.target_artifact_id, item.target_field), []
            )  # type: ignore[arg-type]
        for key in tuple(self._overrides_by_target):
            selected = tuple(
                sorted(
                    (item for item in overrides if (item.target_artifact_id, item.target_field) == key),
                    key=lambda item: (-item.precedence, item.override_id),
                )
            )
            self._overrides_by_target[key] = selected

    def diagnostic(
        self,
        severity: DiagnosticSeverity,
        code: str,
        message: str,
        *,
        artifact_id: str | None = None,
        field_path: str | None = None,
        evidence_refs: Iterable[str] = (),
    ) -> None:
        self.diagnostics.append(
            CompilerDiagnostic(
                severity=severity,
                code=code,
                message=message,
                artifact_id=artifact_id,
                field_path=field_path,
                evidence_refs=tuple(sorted(evidence_refs)),
            )
        )

    def selected_override(self, artifact_id: str, field_path: str) -> CompilerOverride | None:
        candidates = self._overrides_by_target.get((artifact_id, field_path), ())
        if not candidates:
            return None
        self.used_override_ids.update(item.override_id for item in candidates)
        top = candidates[0]
        tied = tuple(item for item in candidates if item.precedence == top.precedence)
        if len(tied) > 1 and len({item.replacement_value_json for item in tied}) > 1:
            self.diagnostic(
                DiagnosticSeverity.STRUCTURAL,
                "UC.COMPILER.OVERRIDE_CONFLICT",
                "multiple highest-precedence overrides provide different values",
                artifact_id=artifact_id,
                field_path=field_path,
                evidence_refs=tuple(item.override_id for item in tied),
            )
            return None
        return top

    def add_provenance(
        self,
        *,
        artifact_id: str,
        field_path: str,
        classification: ProvenanceClass,
        value: object | None,
        evidence: Iterable[NormalizedField] = (),
        evidence_refs: Iterable[str] = (),
        source_field: str | None = None,
        source_value: object | None = None,
        rule_id: str,
        reason: str,
        confidence: str,
        override: CompilerOverride | None = None,
        prior_value: object | None = None,
    ) -> None:
        evidence_tuple = tuple(sorted(evidence, key=lambda item: item.evidence_id))
        self.provenance.append(
            ProvenanceRecord.create(
                artifact_id=artifact_id,
                field_path=field_path,
                classification=classification,
                resolved_value=value,
                evidence_refs=tuple(item.evidence_id for item in evidence_tuple)
                + tuple(evidence_refs),
                source_field=source_field,
                source_value=(
                    source_value
                    if source_value is not None
                    else (
                        None
                        if not evidence_tuple
                        else [item.raw_value for item in evidence_tuple]
                    )
                ),
                rule_id=rule_id,
                rule_version="1",
                confidence_class=confidence,
                reason=reason,
                compiler_configuration_hash=self.config.config_hash,
                override_id=None if override is None else override.override_id,
                prior_value=prior_value,
            )
        )


def compile_network(
    source: SourceNetworkEvidence,
    *,
    config: CompilerConfig | None = None,
    overrides: tuple[CompilerOverride, ...] = (),
) -> CompilationResult:
    """Run all compiler stages and return artifacts plus sealed audit evidence."""

    selected_config = config or CompilerConfig()
    normalized = normalize_source(source)
    context = _Context(config=selected_config, overrides=overrides)
    _validate_source_structure(normalized, context)
    _report_malformed_fields(normalized, context)
    resolved_links = _resolve_links(normalized, context)
    resolved_movements = _resolve_movements(normalized, resolved_links, context)
    resolved = ResolvedSemanticGraph(resolved_links, resolved_movements)

    executable: ExecutableNetwork | None = None
    topology: CanonicalTopology | None = None
    signal_plan: ResolvedFixedTimeSignalPlan | None = None
    lane_config: LaneGroupExtensionConfig | None = None
    if not _has_blocking_diagnostics(context.diagnostics):
        try:
            topology, lane_config = _build_topology_and_lane_groups(
                normalized, resolved, context
            )
            signal_plan = _resolve_signals(normalized, topology, resolved, context)
        except Exception as exc:
            if not _has_blocking_diagnostics(context.diagnostics):
                context.diagnostic(
                    DiagnosticSeverity.INTERNAL,
                    "UC.COMPILER.INTERNAL_CONSISTENCY",
                    f"resolved output failed an existing immutable contract: {type(exc).__name__}: {exc}",
                )
    if (
        topology is not None
        and signal_plan is not None
        and lane_config is not None
        and not _has_blocking_diagnostics(context.diagnostics)
    ):
        try:
            executable = ExecutableNetwork(
                topology=topology,
                signal_plan=signal_plan,
                lane_group_config=lane_config,
                resolved_links=resolved_links,
                physical_derivations=tuple(
                    sorted(
                        context.derivations,
                        key=lambda item: (item.artifact_id, item.target_field),
                    )
                ),
                tick_duration_seconds=selected_config.tick_duration_seconds,
            )
            # Construction checks link numerics, movement continuity, signal binding,
            # lane-group locality, and topology ownership before execution is exposed.
            executable.loading_links()
            nodes = topology.as_loading_nodes()
            lane_config.validate_against_nodes(nodes)
            FixedTimeSignalPlanEvaluator(signal_plan, nodes)
        except Exception as exc:
            executable = None
            context.diagnostic(
                DiagnosticSeverity.INTERNAL,
                "UC.COMPILER.INTERNAL_EXECUTABLE_VALIDATION",
                f"executable artifact validation failed: {type(exc).__name__}: {exc}",
            )

    for item in overrides:
        if item.override_id not in context.used_override_ids:
            context.diagnostic(
                DiagnosticSeverity.STRUCTURAL,
                "UC.COMPILER.UNKNOWN_OVERRIDE_TARGET",
                "override target did not match a supported resolved artifact field",
                artifact_id=item.target_artifact_id,
                field_path=item.target_field,
                evidence_refs=(item.override_id,),
            )
            executable = None

    diagnostics = _sorted_diagnostics(context.diagnostics)
    provenance = _sorted_provenance(context.provenance)
    derivations = tuple(
        sorted(
            context.derivations,
            key=lambda item: (item.artifact_id, item.target_field),
        )
    )
    disposition = _disposition(executable, diagnostics, provenance)
    unresolved = tuple(
        sorted(
            f"{item.artifact_id}:{item.field_path}"
            for item in provenance
            if item.classification == ProvenanceClass.UNRESOLVED
        )
    )
    ruleset_hash = stable_hash(
        "resolution-ruleset",
        {
            "ruleset_version": RULESET_VERSION,
            "rules": [item.to_dict() for item in RULES],
        },
    )
    artifact_payload = None if executable is None else executable.to_dict()
    bundle = CompilerEvidenceBundle(
        input_evidence_hash=source.evidence_hash,
        normalized_evidence_hash=normalized.normalized_hash,
        compiler_configuration_json=canonical_json(selected_config.to_dict()),
        compiler_configuration_hash=selected_config.config_hash,
        ruleset_version=RULESET_VERSION,
        ruleset=RULES,
        ruleset_hash=ruleset_hash,
        canonical_topology_artifact_hash=(
            None if topology is None else topology.topology_hash
        ),
        executable_topology_hash=(
            None if executable is None else executable.executable_topology_hash
        ),
        executable_semantic_hash=(
            None if executable is None else executable.executable_semantic_hash
        ),
        signal_plan_hashes=(
            ()
            if signal_plan is None
            else tuple(
                (item.controller_id, item.semantic_hash)
                for item in signal_plan.controllers
            )
        ),
        lane_group_hashes=(
            () if lane_config is None else (("lane-group-config", lane_config.config_hash),)
        ),
        derivations=derivations,
        provenance=provenance,
        diagnostics=diagnostics,
        unresolved_items=unresolved,
        overrides=tuple(sorted(overrides, key=lambda item: item.override_id)),
        disposition=disposition,
        normalized_source_json=canonical_json(normalized.to_dict()),
        executable_artifacts_json=(
            None if artifact_payload is None else canonical_json(artifact_payload)
        ),
    )
    return CompilationResult(
        source_evidence=source,
        normalized_graph=normalized,
        resolved_graph=resolved,
        _executable=executable,
        diagnostics=diagnostics,
        provenance=provenance,
        derivations=derivations,
        evidence_bundle=bundle,
        disposition=disposition,
    )


def _validate_source_structure(graph: NormalizedSourceGraph, context: _Context) -> None:
    record_ids: set[str] = set()
    field_ids: set[str] = set()
    ids_by_type: dict[str, set[str]] = {}
    supported = {
        "node",
        "link",
        "turn",
        "lane_group",
        "signal_controller",
        "signal_stage",
        "signal_binding",
    }
    for record in graph.records:
        if record.evidence_id in record_ids:
            context.diagnostic(
                DiagnosticSeverity.STRUCTURAL,
                "UC.SOURCE.DUPLICATE_EVIDENCE_ID",
                "source record evidence IDs must be globally unique",
                artifact_id=record.evidence_id,
            )
        record_ids.add(record.evidence_id)
        typed = ids_by_type.setdefault(record.record_type, set())
        if record.source_id in typed:
            context.diagnostic(
                DiagnosticSeverity.STRUCTURAL,
                "UC.SOURCE.DUPLICATE_RECORD_ID",
                f"duplicate {record.record_type} source identity",
                artifact_id=record.source_id,
            )
        typed.add(record.source_id)
        if record.record_type not in supported:
            context.diagnostic(
                DiagnosticSeverity.WARNING,
                "UC.SOURCE.UNSUPPORTED_RECORD_TYPE",
                "record is preserved but ignored by this compiler slice",
                artifact_id=record.source_id,
                evidence_refs=(record.evidence_id,),
            )
        for field in record.fields:
            if field.evidence_id in field_ids or field.evidence_id in record_ids:
                context.diagnostic(
                    DiagnosticSeverity.STRUCTURAL,
                    "UC.SOURCE.DUPLICATE_EVIDENCE_ID",
                    "source field evidence IDs must be globally unique",
                    artifact_id=record.source_id,
                    field_path=field.name,
                    evidence_refs=(field.evidence_id,),
                )
            field_ids.add(field.evidence_id)
    override_ids = [item.override_id for item in context.overrides]
    if len(override_ids) != len(set(override_ids)):
        context.diagnostic(
            DiagnosticSeverity.STRUCTURAL,
            "UC.COMPILER.DUPLICATE_OVERRIDE_ID",
            "compiler override IDs must be unique",
        )


def _report_malformed_fields(graph: NormalizedSourceGraph, context: _Context) -> None:
    for record in graph.records:
        for field in record.fields:
            if field.parse_status == "malformed":
                context.diagnostic(
                    DiagnosticSeverity.WARNING,
                    "UC.SOURCE.MALFORMED_FIELD_RETAINED",
                    f"malformed source value retained and excluded from valid observations: {field.parse_note}",
                    artifact_id=f"{record.record_type}:{record.source_id}",
                    field_path=field.name,
                    evidence_refs=(field.evidence_id,),
                )


def _resolve_links(graph: NormalizedSourceGraph, context: _Context) -> tuple[ResolvedLink, ...]:
    result: list[ResolvedLink] = []
    for record in sorted(graph.records_of_type("link"), key=lambda item: item.source_id):
        artifact = f"link:{record.source_id}"
        road_class = _unique_value(record, "highway")[0] or "unknown"
        road_class = str(road_class)
        context.add_provenance(
            artifact_id=artifact,
            field_path="link_id",
            classification=ProvenanceClass.OBSERVED,
            value=record.source_id,
            evidence_refs=(record.evidence_id,),
            rule_id="link.identity.observed",
            reason="stable source link identity retained",
            confidence="certain",
        )
        tail = _resolve_simple_observed(
            context, record, artifact, "tail_node_id", str, "link.identity.observed"
        )
        head = _resolve_simple_observed(
            context, record, artifact, "head_node_id", str, "link.identity.observed"
        )
        direction = _resolve_simple_observed(
            context,
            record,
            artifact,
            "travel_direction",
            _forward_direction,
            "link.direction.observed",
        )
        length = _resolve_simple_observed(
            context, record, artifact, "length_m", _positive_float, "link.length.observed"
        )
        lanes = _resolve_lanes(context, record, artifact, road_class)
        speed = _resolve_speed(context, record, artifact, road_class)
        capacity = _resolve_capacity(context, record, artifact, road_class, lanes)
        jam = _resolve_observed_or_scalar_default(
            context=context,
            record=record,
            artifact=artifact,
            field_path="jam_density_veh_per_km_per_lane",
            default=context.config.jam_density_veh_per_km_per_lane_default,
            rule_id="link.storage.observed-or-default",
        )
        wave = _resolve_observed_or_scalar_default(
            context=context,
            record=record,
            artifact=artifact,
            field_path="backward_wave_speed_mps",
            default=context.config.backward_wave_speed_mps_default,
            rule_id="link.storage.observed-or-default",
        )
        resolved_link = ResolvedLink(
                link_id=record.source_id,
                source_link_id=record.source_id,
                tail_node_id=tail,
                head_node_id=head,
                travel_direction=direction,
                road_class=road_class,
                length_m=length,
                lane_count=lanes,
                free_flow_speed_mps=speed,
                capacity_veh_per_hour_per_lane=capacity,
                jam_density_veh_per_km_per_lane=jam,
                backward_wave_speed_mps=wave,
            )
        result.append(resolved_link)
        if resolved_link.is_executable:
            _record_link_physical_derivations(record, resolved_link, context)
    return tuple(result)


def _record_link_physical_derivations(
    record: NormalizedRecord,
    link: ResolvedLink,
    context: _Context,
) -> None:
    """Record continuous physics and the exact integer values used by Link."""

    assert link.length_m is not None
    assert link.lane_count is not None
    assert link.free_flow_speed_mps is not None
    assert link.capacity_veh_per_hour_per_lane is not None
    assert link.jam_density_veh_per_km_per_lane is not None
    assert link.backward_wave_speed_mps is not None
    tick = context.config.tick_duration_seconds
    artifact = f"link:{link.link_id}"

    speed_source, speed_source_unit, speed_formula = _resolved_speed_source(
        record, link, context
    )
    capacity_source, capacity_source_unit, capacity_formula = _resolved_capacity_source(
        record, link, context
    )
    jam_source, jam_source_unit = _resolved_scalar_source(
        record,
        "jam_density_veh_per_km_per_lane",
        link.jam_density_veh_per_km_per_lane,
        "vehicles_per_kilometre_per_lane",
        context,
    )
    wave_source, wave_source_unit = _resolved_scalar_source(
        record,
        "backward_wave_speed_mps",
        link.backward_wave_speed_mps,
        "metres_per_second",
        context,
    )
    length_source = _first_raw_value(record, ("length_m",), link.length_m)

    free_flow_seconds = link.length_m / link.free_flow_speed_mps
    free_flow_continuous_ticks = free_flow_seconds / tick
    free_flow_ticks = max(1, ceil(free_flow_continuous_ticks))
    backward_wave_seconds = link.length_m / link.backward_wave_speed_mps
    backward_wave_continuous_ticks = backward_wave_seconds / tick
    backward_wave_ticks = max(1, ceil(backward_wave_continuous_ticks))
    total_capacity_per_hour = link.capacity_veh_per_hour_per_lane * link.lane_count
    continuous_capacity_per_tick = total_capacity_per_hour * tick / 3600.0
    rounded_capacity = floor(continuous_capacity_per_tick)
    discrete_capacity = max(1, rounded_capacity)
    continuous_storage = (
        link.length_m
        / 1000.0
        * link.lane_count
        * link.jam_density_veh_per_km_per_lane
    )
    rounded_storage = floor(continuous_storage)
    discrete_storage = max(1, rounded_storage)

    records = (
        PhysicalDerivationRecord.create(
            artifact_id=artifact,
            target_field="length_m",
            source_value=length_source,
            source_unit="metres",
            normalized_value=link.length_m,
            normalized_unit="metres",
            executable_value=link.length_m,
            executable_unit="metres",
            formula_id="uc.formula.length.identity",
            formula_version="1",
            rounding_policy=ROUND_NONE,
            tick_duration_seconds=tick,
            reason="metric source length is retained without discretisation",
        ),
        PhysicalDerivationRecord.create(
            artifact_id=artifact,
            target_field="lane_count",
            source_value=link.lane_count,
            source_unit="lanes",
            normalized_value=link.lane_count,
            normalized_unit="lanes",
            executable_value=link.lane_count,
            executable_unit="lanes",
            formula_id="uc.formula.lane-count.resolved",
            formula_version="1",
            rounding_policy=ROUND_NONE,
            tick_duration_seconds=tick,
            reason="resolved directional lane count is already discrete evidence",
        ),
        PhysicalDerivationRecord.create(
            artifact_id=artifact,
            target_field="free_flow_speed_mps",
            source_value=speed_source,
            source_unit=speed_source_unit,
            normalized_value=link.free_flow_speed_mps,
            normalized_unit="metres_per_second",
            executable_value=link.free_flow_speed_mps,
            executable_unit="metres_per_second",
            formula_id=speed_formula,
            formula_version="1",
            rounding_policy=ROUND_NONE,
            tick_duration_seconds=tick,
            reason="source or configured speed is normalized to SI velocity",
        ),
        PhysicalDerivationRecord.create(
            artifact_id=artifact,
            target_field="free_flow_travel_time_seconds",
            source_value={"length_m": link.length_m, "speed_mps": link.free_flow_speed_mps},
            source_unit="metres_and_metres_per_second",
            normalized_value=free_flow_seconds,
            normalized_unit="seconds",
            executable_value=free_flow_seconds,
            executable_unit="seconds",
            formula_id="uc.formula.travel-time.length-over-speed",
            formula_version="1",
            rounding_policy=ROUND_NONE,
            tick_duration_seconds=tick,
            reason="continuous free-flow travel time equals length divided by speed",
        ),
        _discrete_derivation(
            artifact=artifact,
            field="free_flow_lag_ticks",
            source_value=free_flow_seconds,
            source_unit="seconds",
            continuous_value=free_flow_continuous_ticks,
            continuous_unit="ticks",
            discrete_value=free_flow_ticks,
            executable_unit="ticks",
            formula_id="uc.formula.lag.seconds-over-tick-duration",
            rounding_policy=ROUND_CEIL_MIN_ONE,
            tick=tick,
            lower_clamp=1,
            clamp_activated=ceil(free_flow_continuous_ticks) < 1,
            reason="frozen Link resolves free-flow lag with ceiling and a one-tick minimum",
        ),
        PhysicalDerivationRecord.create(
            artifact_id=artifact,
            target_field="backward_wave_speed_mps",
            source_value=wave_source,
            source_unit=wave_source_unit,
            normalized_value=link.backward_wave_speed_mps,
            normalized_unit="metres_per_second",
            executable_value=link.backward_wave_speed_mps,
            executable_unit="metres_per_second",
            formula_id="uc.formula.backward-wave-speed.resolved",
            formula_version="1",
            rounding_policy=ROUND_NONE,
            tick_duration_seconds=tick,
            reason="backward-wave speed is resolved in SI velocity",
        ),
        PhysicalDerivationRecord.create(
            artifact_id=artifact,
            target_field="backward_wave_travel_time_seconds",
            source_value={"length_m": link.length_m, "backward_wave_speed_mps": link.backward_wave_speed_mps},
            source_unit="metres_and_metres_per_second",
            normalized_value=backward_wave_seconds,
            normalized_unit="seconds",
            executable_value=backward_wave_seconds,
            executable_unit="seconds",
            formula_id="uc.formula.travel-time.length-over-backward-wave-speed",
            formula_version="1",
            rounding_policy=ROUND_NONE,
            tick_duration_seconds=tick,
            reason="continuous vacancy-wave time equals length divided by wave speed",
        ),
        _discrete_derivation(
            artifact=artifact,
            field="backward_wave_lag_ticks",
            source_value=backward_wave_seconds,
            source_unit="seconds",
            continuous_value=backward_wave_continuous_ticks,
            continuous_unit="ticks",
            discrete_value=backward_wave_ticks,
            executable_unit="ticks",
            formula_id="uc.formula.backward-wave-lag.seconds-over-tick-duration",
            rounding_policy=ROUND_CEIL_MIN_ONE,
            tick=tick,
            lower_clamp=1,
            clamp_activated=ceil(backward_wave_continuous_ticks) < 1,
            reason="frozen physical link contract uses ceiling and a one-tick minimum",
        ),
        PhysicalDerivationRecord.create(
            artifact_id=artifact,
            target_field="capacity_veh_per_hour_per_lane",
            source_value=capacity_source,
            source_unit=capacity_source_unit,
            normalized_value=link.capacity_veh_per_hour_per_lane,
            normalized_unit="vehicles_per_hour_per_lane",
            executable_value=link.capacity_veh_per_hour_per_lane,
            executable_unit="vehicles_per_hour_per_lane",
            formula_id=capacity_formula,
            formula_version="1",
            rounding_policy=ROUND_NONE,
            tick_duration_seconds=tick,
            reason="capacity evidence is resolved to the per-lane hourly contract",
        ),
        PhysicalDerivationRecord.create(
            artifact_id=artifact,
            target_field="total_capacity_vehicles_per_hour",
            source_value={"capacity_per_lane": link.capacity_veh_per_hour_per_lane, "lane_count": link.lane_count},
            source_unit="vehicles_per_hour_per_lane_and_lanes",
            normalized_value=total_capacity_per_hour,
            normalized_unit="vehicles_per_hour",
            executable_value=total_capacity_per_hour,
            executable_unit="vehicles_per_hour",
            formula_id="uc.formula.total-capacity.per-lane-times-lanes",
            formula_version="1",
            rounding_policy=ROUND_NONE,
            tick_duration_seconds=tick,
            reason="continuous total hourly capacity equals per-lane capacity times lanes",
        ),
        PhysicalDerivationRecord.create(
            artifact_id=artifact,
            target_field="continuous_capacity_vehicles_per_tick",
            source_value=total_capacity_per_hour,
            source_unit="vehicles_per_hour",
            normalized_value=continuous_capacity_per_tick,
            normalized_unit="vehicles_per_tick",
            executable_value=continuous_capacity_per_tick,
            executable_unit="vehicles_per_tick",
            formula_id="uc.formula.capacity-per-tick.hourly-times-tick-over-3600",
            formula_version="1",
            rounding_policy=ROUND_NONE,
            tick_duration_seconds=tick,
            reason="continuous capacity is retained before loader-compatible integer discretisation",
        ),
        _discrete_derivation(
            artifact=artifact,
            field="declared_sending_capacity_per_tick",
            source_value=continuous_capacity_per_tick,
            source_unit="vehicles_per_tick",
            continuous_value=continuous_capacity_per_tick,
            continuous_unit="vehicles_per_tick",
            discrete_value=discrete_capacity,
            executable_unit="unit_packets_per_tick",
            formula_id="uc.formula.loader-capacity.floor-minimum-one",
            rounding_policy=ROUND_FLOOR_MIN_ONE,
            tick=tick,
            lower_clamp=1,
            clamp_activated=rounded_capacity < 1,
            reason="numerical compatibility policy for the frozen integer loader; not a physical-capacity claim",
        ),
        _discrete_derivation(
            artifact=artifact,
            field="declared_receiving_capacity_per_tick",
            source_value=continuous_capacity_per_tick,
            source_unit="vehicles_per_tick",
            continuous_value=continuous_capacity_per_tick,
            continuous_unit="vehicles_per_tick",
            discrete_value=discrete_capacity,
            executable_unit="unit_packets_per_tick",
            formula_id="uc.formula.loader-capacity.floor-minimum-one",
            rounding_policy=ROUND_FLOOR_MIN_ONE,
            tick=tick,
            lower_clamp=1,
            clamp_activated=rounded_capacity < 1,
            reason="sending and receiving use the same frozen integer declaration",
        ),
        PhysicalDerivationRecord.create(
            artifact_id=artifact,
            target_field="jam_density_veh_per_km_per_lane",
            source_value=jam_source,
            source_unit=jam_source_unit,
            normalized_value=link.jam_density_veh_per_km_per_lane,
            normalized_unit="vehicles_per_kilometre_per_lane",
            executable_value=link.jam_density_veh_per_km_per_lane,
            executable_unit="vehicles_per_kilometre_per_lane",
            formula_id="uc.formula.jam-density.resolved",
            formula_version="1",
            rounding_policy=ROUND_NONE,
            tick_duration_seconds=tick,
            reason="jam density is resolved in the frozen physical metadata unit",
        ),
        PhysicalDerivationRecord.create(
            artifact_id=artifact,
            target_field="continuous_storage_vehicles",
            source_value={"length_m": link.length_m, "lane_count": link.lane_count, "jam_density": link.jam_density_veh_per_km_per_lane},
            source_unit="metres_lanes_and_vehicles_per_kilometre_per_lane",
            normalized_value=continuous_storage,
            normalized_unit="vehicles",
            executable_value=continuous_storage,
            executable_unit="vehicles",
            formula_id="uc.formula.storage.length-km-times-lanes-times-jam-density",
            formula_version="1",
            rounding_policy=ROUND_NONE,
            tick_duration_seconds=tick,
            reason="continuous finite storage is retained before packet discretisation",
        ),
        _discrete_derivation(
            artifact=artifact,
            field="declared_storage_capacity_packets",
            source_value=continuous_storage,
            source_unit="vehicles",
            continuous_value=continuous_storage,
            continuous_unit="vehicles",
            discrete_value=discrete_storage,
            executable_unit="unit_packets",
            formula_id="uc.formula.loader-storage.floor-minimum-one",
            rounding_policy=ROUND_FLOOR_MIN_ONE,
            tick=tick,
            lower_clamp=1,
            clamp_activated=rounded_storage < 1,
            reason="frozen unit-packet storage uses floor with a one-packet minimum",
        ),
        PhysicalDerivationRecord.create(
            artifact_id=artifact,
            target_field="tick_duration_seconds",
            source_value=tick,
            source_unit="seconds",
            normalized_value=tick,
            normalized_unit="seconds",
            executable_value=tick,
            executable_unit="seconds_per_tick",
            formula_id="uc.formula.tick-duration.configured",
            formula_version="1",
            rounding_policy=ROUND_NONE,
            tick_duration_seconds=tick,
            reason="hashed compiler tick duration is handed unchanged to the loader",
        ),
    )
    context.derivations.extend(records)
    existing_fields = {
        item.field_path for item in context.provenance if item.artifact_id == artifact
    }
    for derivation in records:
        if derivation.target_field not in existing_fields:
            context.add_provenance(
                artifact_id=artifact,
                field_path=derivation.target_field,
                classification=ProvenanceClass.INFERRED,
                value=derivation.executable_value,
                evidence_refs=(derivation.derivation_hash,),
                source_value=derivation.source_value,
                rule_id="link.loading-parameters.derived",
                reason=derivation.reason,
                confidence="deterministic",
            )
    _emit_discretization_diagnostics(records, context)


def _discrete_derivation(
    *,
    artifact: str,
    field: str,
    source_value: object,
    source_unit: str,
    continuous_value: float,
    continuous_unit: str,
    discrete_value: int,
    executable_unit: str,
    formula_id: str,
    rounding_policy: str,
    tick: float,
    lower_clamp: int,
    clamp_activated: bool,
    reason: str,
) -> PhysicalDerivationRecord:
    absolute_error = abs(float(discrete_value) - continuous_value)
    relative_error = (
        None if continuous_value == 0 else absolute_error / abs(continuous_value)
    )
    return PhysicalDerivationRecord.create(
        artifact_id=artifact,
        target_field=field,
        source_value=source_value,
        source_unit=source_unit,
        normalized_value=continuous_value,
        normalized_unit=continuous_unit,
        executable_value=discrete_value,
        executable_unit=executable_unit,
        formula_id=formula_id,
        formula_version="1",
        rounding_policy=rounding_policy,
        lower_clamp=lower_clamp,
        tick_duration_seconds=tick,
        reason=reason,
        absolute_discretization_error=absolute_error,
        relative_discretization_error=relative_error,
        clamp_activated=clamp_activated,
    )


def _emit_discretization_diagnostics(
    records: tuple[PhysicalDerivationRecord, ...],
    context: _Context,
) -> None:
    threshold = context.config.discretization_relative_error_warning_threshold
    for item in records:
        if item.clamp_activated:
            context.diagnostic(
                DiagnosticSeverity.WARNING,
                "UC.DISCRETIZATION.MINIMUM_ONE_CLAMP",
                "minimum-one numerical compatibility clamp changed the rounded value",
                artifact_id=item.artifact_id,
                field_path=item.target_field,
                evidence_refs=(item.derivation_hash,),
            )
        if (
            item.relative_discretization_error is not None
            and item.relative_discretization_error > threshold
        ):
            context.diagnostic(
                DiagnosticSeverity.WARNING,
                "UC.DISCRETIZATION.RELATIVE_ERROR",
                f"relative discretisation error {item.relative_discretization_error:.12g} exceeds configured threshold {threshold:.12g}",
                artifact_id=item.artifact_id,
                field_path=item.target_field,
                evidence_refs=(item.derivation_hash,),
            )


def _first_raw_value(
    record: NormalizedRecord,
    names: tuple[str, ...],
    fallback: object,
) -> object:
    fields = tuple(
        sorted(
            (field for name in names for field in record.values(name)),
            key=lambda item: item.evidence_id,
        )
    )
    return fallback if not fields else fields[0].raw_value


def _resolved_speed_source(
    record: NormalizedRecord,
    link: ResolvedLink,
    context: _Context,
) -> tuple[object, str, str]:
    provenance = next(
        item
        for item in context.provenance
        if item.artifact_id == f"link:{link.link_id}"
        and item.field_path == "free_flow_speed_mps"
    )
    if provenance.classification == ProvenanceClass.OVERRIDDEN:
        return link.free_flow_speed_mps, "metres_per_second", "uc.formula.speed.override-si"
    direct = record.values("speed_mps")
    if direct:
        return direct[0].raw_value, "metres_per_second", "uc.formula.speed.identity-si"
    maxspeed = record.values("maxspeed")
    if maxspeed:
        raw = maxspeed[0].raw_value
        if isinstance(raw, str) and raw.strip().lower().endswith("mph"):
            return raw, "miles_per_hour", "uc.formula.speed.mph-times-1.609344-over-3.6"
        return raw, "kilometres_per_hour", "uc.formula.speed.kph-over-3.6"
    kph = record.values("maxspeed_kph")
    if kph:
        return kph[0].raw_value, "kilometres_per_hour", "uc.formula.speed.kph-over-3.6"
    configured = dict(context.config.speed_kph_defaults)[link.road_class]
    return configured, "kilometres_per_hour", "uc.formula.speed.configured-kph-over-3.6"


def _resolved_capacity_source(
    record: NormalizedRecord,
    link: ResolvedLink,
    context: _Context,
) -> tuple[object, str, str]:
    provenance = next(
        item
        for item in context.provenance
        if item.artifact_id == f"link:{link.link_id}"
        and item.field_path == "capacity_veh_per_hour_per_lane"
    )
    if provenance.classification == ProvenanceClass.OVERRIDDEN:
        return link.capacity_veh_per_hour_per_lane, "vehicles_per_hour_per_lane", "uc.formula.capacity.override-per-lane"
    per_lane = record.values("capacity_veh_per_hour_per_lane")
    if per_lane:
        return per_lane[0].raw_value, "vehicles_per_hour_per_lane", "uc.formula.capacity.identity-per-lane"
    total = record.values("capacity_total_veh_per_hour")
    if total:
        return total[0].raw_value, "vehicles_per_hour", "uc.formula.capacity.total-divided-by-lanes"
    configured = dict(context.config.capacity_per_lane_defaults)[link.road_class]
    return configured, "vehicles_per_hour_per_lane", "uc.formula.capacity.configured-per-lane"


def _resolved_scalar_source(
    record: NormalizedRecord,
    field_name: str,
    resolved: float,
    unit: str,
    context: _Context,
) -> tuple[object, str]:
    del context
    fields = record.values(field_name)
    return (resolved if not fields else fields[0].raw_value, unit)


def _resolve_simple_observed(
    context: _Context,
    record: NormalizedRecord,
    artifact: str,
    field_path: str,
    validator: Callable[[object], object],
    rule_id: str,
) -> object | None:
    observations = record.values(field_path)
    override = context.selected_override(artifact, field_path)
    distinct = _distinct_values(observations)
    if override is not None:
        try:
            value = validator(override.replacement_value)
        except (TypeError, ValueError) as exc:
            context.diagnostic(
                DiagnosticSeverity.UNRESOLVED,
                "UC.OVERRIDE.INVALID_VALUE",
                f"override replacement is invalid: {exc}",
                artifact_id=artifact,
                field_path=field_path,
                evidence_refs=(override.override_id,),
            )
            context.add_provenance(
                artifact_id=artifact,
                field_path=field_path,
                classification=ProvenanceClass.UNRESOLVED,
                value=None,
                evidence=observations,
                rule_id="compiler.unresolved",
                reason="invalid override replacement",
                confidence="none",
                override=override,
                prior_value=distinct,
            )
            return None
        if len(distinct) > 1:
            context.diagnostic(
                DiagnosticSeverity.INFO,
                "UC.OVERRIDE.REPAIRED_CONFLICT",
                "explicit override repaired conflicting retained evidence",
                artifact_id=artifact,
                field_path=field_path,
                evidence_refs=tuple(item.evidence_id for item in observations) + (override.override_id,),
            )
        context.add_provenance(
            artifact_id=artifact,
            field_path=field_path,
            classification=ProvenanceClass.OVERRIDDEN,
            value=value,
            evidence=observations,
            source_field=field_path,
            rule_id="compiler.override",
            reason=override.reason,
            confidence="explicit",
            override=override,
            prior_value=distinct if len(distinct) != 1 else distinct[0],
        )
        return value
    if len(distinct) == 1:
        try:
            value = validator(distinct[0])
        except (TypeError, ValueError) as exc:
            return _unresolved_field(
                context, artifact, field_path, observations, f"invalid observed value: {exc}"
            )
        context.add_provenance(
            artifact_id=artifact,
            field_path=field_path,
            classification=ProvenanceClass.OBSERVED,
            value=value,
            evidence=observations,
            source_field=field_path,
            rule_id=rule_id,
            reason="one unambiguous valid source value",
            confidence="observed",
        )
        return value
    reason = "missing mandatory source value" if not distinct else "conflicting source values"
    return _unresolved_field(context, artifact, field_path, observations, reason)


def _resolve_lanes(
    context: _Context,
    record: NormalizedRecord,
    artifact: str,
    road_class: str,
) -> int | None:
    override = context.selected_override(artifact, "lane_count")
    direct = record.values("lane_count") + record.values("lanes:forward")
    direct_values = _distinct_values(direct)
    total = record.values("lanes")
    total_values = _distinct_values(total)
    if override is not None:
        return _apply_override(context, artifact, "lane_count", override, direct + total, _positive_int, direct_values or total_values)
    if len(direct_values) == 1:
        value = _positive_int(direct_values[0])
        context.add_provenance(
            artifact_id=artifact,
            field_path="lane_count",
            classification=ProvenanceClass.OBSERVED,
            value=value,
            evidence=direct,
            source_field=direct[0].name,
            rule_id="link.lanes.observed",
            reason="observed directional lane count",
            confidence="observed",
        )
        return value
    if len(direct_values) > 1 or len(total_values) > 1:
        return _unresolved_field(context, artifact, "lane_count", direct + total, "conflicting lane evidence")
    if len(total_values) == 1:
        total_value = _positive_int(total_values[0])
        oneway_value, _ = _unique_value(record, "oneway")
        if oneway_value is True:
            context.add_provenance(
                artifact_id=artifact,
                field_path="lane_count",
                classification=ProvenanceClass.OBSERVED,
                value=total_value,
                evidence=total,
                source_field="lanes",
                rule_id="link.lanes.observed",
                reason="total lanes are directional because oneway=yes",
                confidence="observed",
            )
            return total_value
        if oneway_value is False and total_value % 2 == 0:
            value = total_value // 2
            context.add_provenance(
                artifact_id=artifact,
                field_path="lane_count",
                classification=ProvenanceClass.INFERRED,
                value=value,
                evidence=total + record.values("oneway"),
                source_field="lanes",
                rule_id="link.lanes.directional-from-total",
                reason="even total lanes split equally across explicit two-way evidence",
                confidence="deterministic",
            )
            return value
        if oneway_value is not None:
            return _unresolved_field(context, artifact, "lane_count", total + record.values("oneway"), "total lane evidence cannot be split unambiguously")
    default = dict(context.config.lane_defaults).get(road_class)
    if context.config.allow_road_class_defaults and default is not None:
        context.add_provenance(
            artifact_id=artifact,
            field_path="lane_count",
            classification=ProvenanceClass.DEFAULTED,
            value=default,
            evidence=record.values("highway"),
            source_field="highway",
            rule_id="link.lanes.road-class-default",
            reason=f"configured {road_class} lane default",
            confidence="configured",
        )
        return default
    return _unresolved_field(context, artifact, "lane_count", direct + total, "no permitted lane-count rule applies")


def _resolve_speed(context: _Context, record: NormalizedRecord, artifact: str, road_class: str) -> float | None:
    override = context.selected_override(artifact, "free_flow_speed_mps")
    direct = record.values("speed_mps")
    kph = record.values("maxspeed") + record.values("maxspeed_kph")
    observations = direct + kph
    if override is not None:
        return _apply_override(context, artifact, "free_flow_speed_mps", override, observations, _positive_float, _distinct_values(observations))
    direct_values = _distinct_values(direct)
    kph_values = _distinct_values(kph)
    converted = tuple(float(value) / 3.6 for value in kph_values)
    values = direct_values + converted
    if len(set(values)) == 1 and values:
        value = float(values[0])
        context.add_provenance(
            artifact_id=artifact,
            field_path="free_flow_speed_mps",
            classification=ProvenanceClass.OBSERVED,
            value=value,
            evidence=observations,
            source_field=observations[0].name,
            rule_id="link.speed.observed",
            reason="observed speed normalized to metres per second",
            confidence="observed",
        )
        return value
    if len(set(values)) > 1:
        return _unresolved_field(context, artifact, "free_flow_speed_mps", observations, "conflicting speed evidence")
    default = dict(context.config.speed_kph_defaults).get(road_class)
    if context.config.allow_road_class_defaults and default is not None:
        value = float(default) / 3.6
        context.add_provenance(
            artifact_id=artifact,
            field_path="free_flow_speed_mps",
            classification=ProvenanceClass.DEFAULTED,
            value=value,
            evidence=record.values("highway"),
            source_field="highway",
            rule_id="link.speed.road-class-default",
            reason=f"configured {road_class} speed default",
            confidence="configured",
        )
        return value
    return _unresolved_field(context, artifact, "free_flow_speed_mps", observations, "no permitted speed rule applies")


def _resolve_capacity(
    context: _Context,
    record: NormalizedRecord,
    artifact: str,
    road_class: str,
    lanes: int | None,
) -> float | None:
    override = context.selected_override(artifact, "capacity_veh_per_hour_per_lane")
    per_lane = record.values("capacity_veh_per_hour_per_lane")
    total = record.values("capacity_total_veh_per_hour")
    observations = per_lane + total
    if override is not None:
        return _apply_override(context, artifact, "capacity_veh_per_hour_per_lane", override, observations, _positive_float, _distinct_values(observations))
    per_values = _distinct_values(per_lane)
    if len(per_values) == 1:
        value = _positive_float(per_values[0])
        context.add_provenance(
            artifact_id=artifact,
            field_path="capacity_veh_per_hour_per_lane",
            classification=ProvenanceClass.OBSERVED,
            value=value,
            evidence=per_lane,
            source_field="capacity_veh_per_hour_per_lane",
            rule_id="link.capacity.observed",
            reason="observed per-lane capacity",
            confidence="observed",
        )
        return value
    if len(per_values) > 1:
        return _unresolved_field(context, artifact, "capacity_veh_per_hour_per_lane", per_lane, "conflicting capacity evidence")
    total_values = _distinct_values(total)
    if len(total_values) == 1 and lanes is not None:
        value = _positive_float(total_values[0]) / lanes
        context.add_provenance(
            artifact_id=artifact,
            field_path="capacity_veh_per_hour_per_lane",
            classification=ProvenanceClass.INFERRED,
            value=value,
            evidence=total,
            source_field="capacity_total_veh_per_hour",
            rule_id="link.capacity.from-total",
            reason="observed total capacity divided by resolved directional lanes",
            confidence="deterministic",
        )
        return value
    if len(total_values) > 1:
        return _unresolved_field(context, artifact, "capacity_veh_per_hour_per_lane", total, "conflicting total capacity evidence")
    default = dict(context.config.capacity_per_lane_defaults).get(road_class)
    if context.config.allow_road_class_defaults and default is not None:
        context.add_provenance(
            artifact_id=artifact,
            field_path="capacity_veh_per_hour_per_lane",
            classification=ProvenanceClass.DEFAULTED,
            value=default,
            evidence=record.values("highway"),
            source_field="highway",
            rule_id="link.capacity.road-class-default",
            reason=f"configured {road_class} capacity default",
            confidence="configured",
        )
        return float(default)
    return _unresolved_field(context, artifact, "capacity_veh_per_hour_per_lane", observations, "no permitted capacity rule applies")


def _resolve_observed_or_scalar_default(
    *,
    context: _Context,
    record: NormalizedRecord,
    artifact: str,
    field_path: str,
    default: float,
    rule_id: str,
) -> float | None:
    override = context.selected_override(artifact, field_path)
    observations = record.values(field_path)
    if override is not None:
        return _apply_override(context, artifact, field_path, override, observations, _positive_float, _distinct_values(observations))
    values = _distinct_values(observations)
    if len(values) == 1:
        value = _positive_float(values[0])
        context.add_provenance(
            artifact_id=artifact,
            field_path=field_path,
            classification=ProvenanceClass.OBSERVED,
            value=value,
            evidence=observations,
            source_field=field_path,
            rule_id=rule_id,
            reason="one unambiguous observed physical value",
            confidence="observed",
        )
        return value
    if len(values) > 1:
        return _unresolved_field(context, artifact, field_path, observations, "conflicting physical evidence")
    context.add_provenance(
        artifact_id=artifact,
        field_path=field_path,
        classification=ProvenanceClass.DEFAULTED,
        value=default,
        rule_id=rule_id,
        reason="explicit compiler configuration physical default",
        confidence="configured",
    )
    return default


def _resolve_movements(
    graph: NormalizedSourceGraph,
    links: tuple[ResolvedLink, ...],
    context: _Context,
) -> tuple[ResolvedMovement, ...]:
    executable_links = {item.link_id: item for item in links if item.tail_node_id and item.head_node_id}
    turn_records = graph.records_of_type("turn")
    bindings = graph.records_of_type("signal_binding")
    result: list[ResolvedMovement] = []

    for turn in turn_records:
        upstream, _ = _unique_value(turn, "upstream_link_id")
        downstream, _ = _unique_value(turn, "downstream_link_id")
        if upstream not in executable_links or downstream not in executable_links:
            context.diagnostic(
                DiagnosticSeverity.STRUCTURAL,
                "UC.MOVEMENT.UNKNOWN_LINK_REFERENCE",
                "turn evidence references an unknown link",
                artifact_id=f"turn:{turn.source_id}",
                evidence_refs=(turn.evidence_id,),
            )
        elif executable_links[str(upstream)].head_node_id != executable_links[str(downstream)].tail_node_id:
            context.diagnostic(
                DiagnosticSeverity.STRUCTURAL,
                "UC.MOVEMENT.DISCONTINUOUS_REFERENCE",
                "turn evidence violates directed topology continuity",
                artifact_id=f"turn:{turn.source_id}",
                evidence_refs=(turn.evidence_id,),
            )

    candidates = sorted(
        (
            (upstream.link_id, downstream.link_id, upstream.head_node_id)
            for upstream in executable_links.values()
            for downstream in executable_links.values()
            if upstream.head_node_id == downstream.tail_node_id
            and upstream.link_id != downstream.link_id
        ),
        key=lambda item: (str(item[2]), item[0], item[1]),
    )
    for upstream_id, downstream_id, node_id_value in candidates:
        assert node_id_value is not None
        movement_id = f"movement:{upstream_id}->{downstream_id}"
        topology_evidence_refs = tuple(
            record.evidence_id
            for record in graph.records_of_type("link")
            if record.source_id in (upstream_id, downstream_id)
        )
        relevant = tuple(
            record
            for record in turn_records
            if _unique_value(record, "upstream_link_id")[0] == upstream_id
            and _unique_value(record, "downstream_link_id")[0] == downstream_id
        )
        permission_fields = tuple(
            field for record in relevant for field in record.values("permission")
        )
        permissions = tuple(str(value).lower() for value in _distinct_values(permission_fields))
        override = context.selected_override(movement_id, "permitted")
        if override is not None:
            permitted = _apply_override(
                context,
                movement_id,
                "permitted",
                override,
                permission_fields,
                _bool_value,
                permissions,
            )
            if len(set(permissions)) > 1:
                context.diagnostic(
                    DiagnosticSeverity.INFO,
                    "UC.OVERRIDE.REPAIRED_CONFLICT",
                    "explicit override repaired contradictory turn restrictions",
                    artifact_id=movement_id,
                    field_path="permitted",
                    evidence_refs=tuple(item.evidence_id for item in permission_fields) + (override.override_id,),
                )
        elif not permissions:
            permitted = True
            context.add_provenance(
                artifact_id=movement_id,
                field_path="permitted",
                classification=ProvenanceClass.INFERRED,
                value=True,
                rule_id="movement.permission.topology",
                reason="directed link continuity and no contradictory restriction",
                confidence="deterministic",
            )
        elif set(permissions) <= {"allow", "permitted", "yes"}:
            permitted = True
            context.add_provenance(
                artifact_id=movement_id,
                field_path="permitted",
                classification=ProvenanceClass.OBSERVED,
                value=True,
                evidence=permission_fields,
                source_field="permission",
                rule_id="movement.permission.observed",
                reason="explicit observed turn permission",
                confidence="observed",
            )
        elif set(permissions) <= {"prohibit", "prohibited", "no"}:
            permitted = False
            context.add_provenance(
                artifact_id=movement_id,
                field_path="permitted",
                classification=ProvenanceClass.OBSERVED,
                value=False,
                evidence=permission_fields,
                source_field="permission",
                rule_id="movement.permission.observed",
                reason="explicit observed turn prohibition",
                confidence="observed",
            )
        else:
            permitted = _unresolved_field(
                context,
                movement_id,
                "permitted",
                permission_fields,
                "contradictory or unsupported turn restrictions",
                code="UC.MOVEMENT.CONFLICTING_RESTRICTIONS",
            )

        lane_fields = tuple(field for record in relevant for field in record.values("lane_indices"))
        lane_indices: tuple[int, ...] = ()
        lane_values = _distinct_values(lane_fields)
        if len(lane_values) == 1 and isinstance(lane_values[0], list):
            lane_indices = tuple(sorted(int(value) for value in lane_values[0]))

        binding_fields: list[NormalizedField] = []
        group_values: list[str] = []
        for binding in bindings:
            bound_movement, _ = _unique_value(binding, "movement_id")
            if bound_movement != movement_id:
                continue
            group, fields = _unique_value(binding, "signal_group_id")
            if group is not None:
                group_values.append(str(group))
                binding_fields.extend(fields)
        signal_group: str | None
        if len(set(group_values)) > 1:
            signal_group = None
            _unresolved_field(
                context,
                movement_id,
                "signal_group_id",
                tuple(binding_fields),
                "conflicting signal-group membership",
                code="UC.SIGNAL.CONFLICTING_GROUP_MEMBERSHIP",
            )
        else:
            signal_group = group_values[0] if group_values else None
            if signal_group is not None:
                context.add_provenance(
                    artifact_id=movement_id,
                    field_path="signal_group_id",
                    classification=ProvenanceClass.OBSERVED,
                    value=signal_group,
                    evidence=tuple(binding_fields),
                    source_field="signal_group_id",
                    rule_id="signal.explicit-fixed-time",
                    reason="observed signal-group binding",
                    confidence="observed",
                )
        result.append(
            ResolvedMovement(
                movement_id=movement_id,
                node_id=node_id_value,
                upstream_link_id=upstream_id,
                downstream_link_id=downstream_id,
                permitted=permitted if isinstance(permitted, bool) else None,
                priority_weight=1,
                signal_group_id=signal_group,
                lane_indices=lane_indices,
            )
        )
        for field_path, value in (
            ("movement_id", movement_id),
            ("node_id", node_id_value),
            ("upstream_link_id", upstream_id),
            ("downstream_link_id", downstream_id),
        ):
            context.add_provenance(
                artifact_id=movement_id,
                field_path=field_path,
                classification=ProvenanceClass.INFERRED,
                value=value,
                evidence_refs=topology_evidence_refs,
                rule_id="movement.identity.topology",
                reason="continuous resolved directed topology determines movement identity",
                confidence="deterministic",
            )
        context.add_provenance(
            artifact_id=movement_id,
            field_path="priority_weight",
            classification=ProvenanceClass.DEFAULTED,
            value=1,
            rule_id="movement.priority.default",
            reason="v1 compiler declares unit priority absent explicit priority evidence",
            confidence="configured",
        )
    return tuple(result)


def _build_topology_and_lane_groups(
    graph: NormalizedSourceGraph,
    resolved: ResolvedSemanticGraph,
    context: _Context,
) -> tuple[CanonicalTopology, LaneGroupExtensionConfig]:
    if any(not item.is_executable for item in resolved.links):
        raise ValueError("mandatory link semantics remain unresolved")
    if any(item.permitted is None for item in resolved.movements):
        raise ValueError("mandatory movement permissions remain unresolved")
    node_ids = tuple(sorted(record.source_id for record in graph.records_of_type("node")))
    node_set = set(node_ids)
    for link in resolved.links:
        if link.tail_node_id not in node_set or link.head_node_id not in node_set:
            context.diagnostic(
                DiagnosticSeverity.STRUCTURAL,
                "UC.TOPOLOGY.UNKNOWN_ENDPOINT",
                "resolved link endpoint is not a declared node",
                artifact_id=f"link:{link.link_id}",
            )
    if _has_blocking_diagnostics(context.diagnostics):
        raise ValueError("source topology is structurally invalid")

    group_records = graph.records_of_type("lane_group")
    legacy_by_node: dict[str, list[NormalizedRecord]] = {}
    explicit_by_node_incoming: dict[tuple[str, str], list[NormalizedRecord]] = {}
    for record in group_records:
        node_id, _ = _unique_value(record, "node_id")
        incoming, _ = _unique_value(record, "incoming_link_id")
        partition, _ = _unique_value(record, "queue_partition")
        if not isinstance(node_id, str) or not isinstance(incoming, str):
            context.diagnostic(
                DiagnosticSeverity.STRUCTURAL,
                "UC.LANE_GROUP.MISSING_LOCALITY",
                "lane group requires node_id and incoming_link_id",
                artifact_id=f"lane-group:{record.source_id}",
                evidence_refs=(record.evidence_id,),
            )
            continue
        if partition is True:
            explicit_by_node_incoming.setdefault((node_id, incoming), []).append(record)
        else:
            legacy_by_node.setdefault(node_id, []).append(record)
    conflicting_modes = sorted(
        set(legacy_by_node)
        & {node_id for node_id, _ in explicit_by_node_incoming}
    )
    for node_id in conflicting_modes:
        context.diagnostic(
            DiagnosticSeverity.STRUCTURAL,
            "UC.LANE_GROUP.MODE_CONFLICT",
            "one junction cannot reinterpret frozen lane-group resources as explicit queue partitions",
            artifact_id=f"node:{node_id}",
        )

    permitted_movements = tuple(item for item in resolved.movements if item.permitted)
    explicit_groups: list[ExplicitLaneGroup] = []
    detailed_exists = bool(explicit_by_node_incoming) or any(item.lane_indices for item in permitted_movements)
    if context.config.enable_explicit_lane_group_partitions and detailed_exists:
        approaches = sorted(
            {
                (item.node_id, item.upstream_link_id)
                for item in permitted_movements
                if item.node_id not in legacy_by_node
            }
        )
        for node_id, incoming in approaches:
            movements = tuple(
                item
                for item in permitted_movements
                if item.node_id == node_id and item.upstream_link_id == incoming
            )
            declarations = explicit_by_node_incoming.get((node_id, incoming), [])
            if declarations:
                covered_movement_ids: set[str] = set()
                for declaration in sorted(declarations, key=lambda item: item.source_id):
                    allowed, allowed_fields = _unique_value(declaration, "allowed_movement_ids")
                    capacity, capacity_fields = _unique_value(declaration, "capacity_per_tick")
                    if not isinstance(allowed, list) or not allowed or not isinstance(capacity, int):
                        _unresolved_field(
                            context,
                            f"lane-group:{declaration.source_id}",
                            "declaration",
                            allowed_fields + capacity_fields,
                            "explicit lane group requires movement IDs and positive capacity",
                            code="UC.LANE_GROUP.INVALID_DECLARATION",
                        )
                        continue
                    movement_by_id = {item.movement_id: item for item in movements}
                    invalid_refs = tuple(
                        sorted(
                            movement_id
                            for movement_id in (str(item) for item in allowed)
                            if movement_id not in movement_by_id
                            or movement_by_id[movement_id].upstream_link_id != incoming
                        )
                    )
                    if invalid_refs:
                        context.diagnostic(
                            DiagnosticSeverity.STRUCTURAL,
                            "UC.LANE_GROUP.INVALID_MOVEMENT_REFERENCE",
                            f"lane group references unknown or non-local movements: {invalid_refs}",
                            artifact_id=f"lane-group:{declaration.source_id}",
                            field_path="allowed_movement_ids",
                            evidence_refs=tuple(item.evidence_id for item in allowed_fields),
                        )
                        continue
                    group = ExplicitLaneGroup(
                        lane_group_id=declaration.source_id,
                        node_id=node_id,
                        incoming_link_id=incoming,
                        allowed_movement_ids=tuple(sorted(str(item) for item in allowed)),
                        service_capacity_per_tick=capacity,
                        provenance=LaneGroupProvenance(
                            source=declaration.evidence_id,
                            confidence=1.0,
                            status="declared",
                            compiler_version=COMPILER_VERSION,
                        ),
                    )
                    explicit_groups.append(group)
                    covered_movement_ids.update(group.allowed_movement_ids)
                    context.add_provenance(
                        artifact_id=f"lane-group:{group.lane_group_id}",
                        field_path="allowed_movement_ids",
                        classification=ProvenanceClass.OBSERVED,
                        value=list(group.allowed_movement_ids),
                        evidence=allowed_fields,
                        source_field="allowed_movement_ids",
                        rule_id="lane-group.explicit",
                        reason="explicit queue-partition declaration",
                        confidence="observed",
                    )
                    for field_path, value in (
                        ("node_id", group.node_id),
                        ("incoming_link_id", group.incoming_link_id),
                        ("service_capacity_per_tick", group.service_capacity_per_tick),
                    ):
                        context.add_provenance(
                            artifact_id=f"lane-group:{group.lane_group_id}",
                            field_path=field_path,
                            classification=ProvenanceClass.OBSERVED,
                            value=value,
                            evidence_refs=(declaration.evidence_id,),
                            rule_id="lane-group.explicit",
                            reason="explicit queue-partition declaration",
                            confidence="observed",
                        )
                missing_coverage = tuple(
                    sorted(
                        {item.movement_id for item in movements}
                        - covered_movement_ids
                    )
                )
                if missing_coverage:
                    _unresolved_field(
                        context,
                        f"approach:{node_id}:{incoming}",
                        "lane_group_partition",
                        (),
                        f"explicit partition does not cover all permitted movements: {missing_coverage}",
                        code="UC.LANE_GROUP.INCOMPLETE_PARTITION",
                    )
            elif movements and all(item.lane_indices for item in movements):
                indices = sorted({index for item in movements for index in item.lane_indices})
                link = next(item for item in resolved.links if item.link_id == incoming)
                if indices and link.lane_count is not None and min(indices) >= 1 and max(indices) <= link.lane_count:
                    for index in indices:
                        allowed_ids = tuple(
                            item.movement_id for item in movements if index in item.lane_indices
                        )
                        group_id = f"inferred:{node_id}:{incoming}:lane:{index}"
                        explicit_groups.append(
                            ExplicitLaneGroup(
                                lane_group_id=group_id,
                                node_id=node_id,
                                incoming_link_id=incoming,
                                allowed_movement_ids=allowed_ids,
                                service_capacity_per_tick=1,
                                provenance=LaneGroupProvenance(
                                    source=f"lane-index-evidence:{incoming}",
                                    confidence=0.9,
                                    status="inferred",
                                    compiler_version=COMPILER_VERSION,
                                ),
                            )
                        )
                        context.add_provenance(
                            artifact_id=f"lane-group:{group_id}",
                            field_path="allowed_movement_ids",
                            classification=ProvenanceClass.INFERRED,
                            value=list(allowed_ids),
                            rule_id="lane-group.from-lane-index",
                            reason="complete movement lane-index evidence",
                            confidence="deterministic",
                        )
                        for field_path, value in (
                            ("node_id", node_id),
                            ("incoming_link_id", incoming),
                            ("service_capacity_per_tick", 1),
                        ):
                            context.add_provenance(
                                artifact_id=f"lane-group:{group_id}",
                                field_path=field_path,
                                classification=ProvenanceClass.INFERRED,
                                value=value,
                                rule_id="lane-group.from-lane-index",
                                reason="complete lane-index evidence determines local queue resource",
                                confidence="deterministic",
                            )
                else:
                    _unresolved_field(
                        context,
                        f"approach:{node_id}:{incoming}",
                        "lane_group_partition",
                        (),
                        "lane-index evidence exceeds resolved lane count",
                        code="UC.LANE_GROUP.UNSAFE_INFERENCE",
                    )
            elif context.config.allow_conservative_shared_lane_fallback and movements:
                group_id = f"shared:{node_id}:{incoming}"
                allowed_ids = tuple(item.movement_id for item in movements)
                explicit_groups.append(
                    ExplicitLaneGroup(
                        lane_group_id=group_id,
                        node_id=node_id,
                        incoming_link_id=incoming,
                        allowed_movement_ids=allowed_ids,
                        service_capacity_per_tick=1,
                        provenance=LaneGroupProvenance(
                            source="compiler-config:shared-lane-fallback",
                            confidence=1.0,
                            status="inferred",
                            fallback_reason="detailed lane-to-turn evidence unavailable",
                            compiler_version=COMPILER_VERSION,
                        ),
                    )
                )
                context.add_provenance(
                    artifact_id=f"lane-group:{group_id}",
                    field_path="allowed_movement_ids",
                    classification=ProvenanceClass.DEFAULTED,
                    value=list(allowed_ids),
                    rule_id="lane-group.shared-fallback",
                    reason="conservative shared queue preserves approach FIFO",
                    confidence="conservative",
                )
                for field_path, value in (
                    ("node_id", node_id),
                    ("incoming_link_id", incoming),
                    ("service_capacity_per_tick", 1),
                ):
                    context.add_provenance(
                        artifact_id=f"lane-group:{group_id}",
                        field_path=field_path,
                        classification=ProvenanceClass.DEFAULTED,
                        value=value,
                        rule_id="lane-group.shared-fallback",
                        reason="conservative shared approach resource",
                        confidence="conservative",
                    )
                context.diagnostic(
                    DiagnosticSeverity.WARNING,
                    "UC.LANE_GROUP.SHARED_FALLBACK",
                    "detailed grouping unavailable; compiled one shared approach queue",
                    artifact_id=f"approach:{node_id}:{incoming}",
                )
            elif movements:
                _unresolved_field(
                    context,
                    f"approach:{node_id}:{incoming}",
                    "lane_group_partition",
                    (),
                    "detailed grouping unavailable and conservative fallback disabled",
                    code="UC.LANE_GROUP.UNRESOLVED_PARTITION",
                )

    mode = EXPLICIT_LANE_GROUP_FIFO if explicit_groups else SHARED_LINK_FIFO
    lane_config = LaneGroupExtensionConfig(mode, tuple(explicit_groups))

    links_by_head: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    links_by_tail: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for link in resolved.links:
        assert link.head_node_id is not None and link.tail_node_id is not None
        links_by_head[link.head_node_id].append(link.link_id)
        links_by_tail[link.tail_node_id].append(link.link_id)

    canonical_nodes: list[CanonicalNode] = []
    for node_id in node_ids:
        legacy_records = legacy_by_node.get(node_id, [])
        legacy_ids: list[str] = []
        capacities: list[tuple[str, int]] = []
        mapping_by_movement: dict[str, list[str]] = {}
        for record in sorted(legacy_records, key=lambda item: item.source_id):
            incoming, _ = _unique_value(record, "incoming_link_id")
            allowed, allowed_fields = _unique_value(record, "allowed_movement_ids")
            capacity, capacity_fields = _unique_value(record, "capacity_per_tick")
            if not isinstance(incoming, str) or not isinstance(allowed, list) or not isinstance(capacity, int):
                _unresolved_field(
                    context,
                    f"lane-group:{record.source_id}",
                    "declaration",
                    allowed_fields + capacity_fields,
                    "legacy lane resource declaration is incomplete",
                    code="UC.LANE_GROUP.INVALID_DECLARATION",
                )
                continue
            node_movement_ids = {
                item.movement_id
                for item in permitted_movements
                if item.node_id == node_id and item.upstream_link_id == incoming
            }
            invalid_refs = tuple(
                sorted(str(item) for item in allowed if str(item) not in node_movement_ids)
            )
            if invalid_refs:
                context.diagnostic(
                    DiagnosticSeverity.STRUCTURAL,
                    "UC.LANE_GROUP.INVALID_MOVEMENT_REFERENCE",
                    f"legacy lane resource references unknown or non-local movements: {invalid_refs}",
                    artifact_id=f"lane-group-resource:{record.source_id}",
                    field_path="allowed_movement_ids",
                    evidence_refs=tuple(item.evidence_id for item in allowed_fields),
                )
                continue
            legacy_ids.append(record.source_id)
            capacities.append((record.source_id, capacity))
            for movement_id in allowed:
                mapping_by_movement.setdefault(str(movement_id), []).append(record.source_id)
            context.add_provenance(
                artifact_id=f"lane-group-resource:{record.source_id}",
                field_path="allowed_movement_ids",
                classification=ProvenanceClass.OBSERVED,
                value=allowed,
                evidence=allowed_fields,
                source_field="allowed_movement_ids",
                rule_id="lane-group.explicit",
                reason="existing frozen lane-group resource declaration retained",
                confidence="observed",
            )
            for field_path, value in (
                ("node_id", node_id),
                ("incoming_link_id", incoming),
                ("service_capacity_per_tick", capacity),
            ):
                context.add_provenance(
                    artifact_id=f"lane-group-resource:{record.source_id}",
                    field_path=field_path,
                    classification=ProvenanceClass.OBSERVED,
                    value=value,
                    evidence_refs=(record.evidence_id,),
                    rule_id="lane-group.explicit",
                    reason="existing frozen lane-group resource declaration retained",
                    confidence="observed",
                )
        movements = tuple(
            item
            for item in permitted_movements
            if item.node_id == node_id
        )
        specs = tuple(
            MovementSpec(
                upstream_link_id=item.upstream_link_id,
                downstream_link_id=item.downstream_link_id,
                movement_id=item.movement_id,
                priority_weight=item.priority_weight,
                lane_group_ids=tuple(sorted(mapping_by_movement.get(item.movement_id, ()))),
                signal_group_id=item.signal_group_id,
                provenance=(("compiler_version", COMPILER_VERSION),),
            )
            for item in movements
        )
        canonical_nodes.append(
            CanonicalNode(
                node_id=node_id,
                source_node_id=node_id,
                incoming_link_ids=tuple(sorted(links_by_head[node_id])),
                outgoing_link_ids=tuple(sorted(links_by_tail[node_id])),
                movement_specs=specs,
                lane_group_ids=tuple(sorted(legacy_ids)),
                movement_lane_group_mappings=tuple(
                    (movement_id, tuple(sorted(group_ids)))
                    for movement_id, group_ids in sorted(mapping_by_movement.items())
                ),
                lane_group_capacities=tuple(sorted(capacities)),
            )
        )
        node_record = next(
            item
            for item in graph.records_of_type("node")
            if item.source_id == node_id
        )
        for field_path, value, classification in (
            ("node_id", node_id, ProvenanceClass.OBSERVED),
            ("incoming_link_ids", sorted(links_by_head[node_id]), ProvenanceClass.INFERRED),
            ("outgoing_link_ids", sorted(links_by_tail[node_id]), ProvenanceClass.INFERRED),
        ):
            context.add_provenance(
                artifact_id=f"node:{node_id}",
                field_path=field_path,
                classification=classification,
                value=value,
                evidence_refs=(node_record.evidence_id,),
                rule_id="link.identity.observed" if classification == ProvenanceClass.OBSERVED else "movement.identity.topology",
                reason="source node identity retained" if classification == ProvenanceClass.OBSERVED else "resolved link endpoints determine node connectivity",
                confidence="observed" if classification == ProvenanceClass.OBSERVED else "deterministic",
            )

    canonical_links = tuple(
        CanonicalTopologyLink(
            link_id=item.link_id,
            tail_node_id=str(item.tail_node_id),
            head_node_id=str(item.head_node_id),
            source_link_id=item.source_link_id,
            source_tail_node_id=str(item.tail_node_id),
            source_head_node_id=str(item.head_node_id),
            length_m=item.length_m,
            lane_count=item.lane_count,
            free_flow_speed_mps=item.free_flow_speed_mps,
            capacity_veh_per_hour_per_lane=item.capacity_veh_per_hour_per_lane,
            jam_density_veh_per_km_per_lane=item.jam_density_veh_per_km_per_lane,
            backward_wave_speed_mps=item.backward_wave_speed_mps,
            source_length_value=item.length_m,
            source_length_unit="m",
            source_capacity_value=item.capacity_veh_per_hour_per_lane,
            source_capacity_unit="veh/hour/lane",
        )
        for item in resolved.links
    )
    topology = CanonicalTopology(
        topology_id=graph.network_id,
        nodes=tuple(canonical_nodes),
        links=canonical_links,
        source_metadata=TopologySourceMetadata(
            source_name=graph.network_id,
            source_format="uc.osm-like-source-network.v1",
            source_file_path="",
            source_file_sha256=graph.source_evidence_hash,
            source_metadata_items=(
                ("compiler_version", COMPILER_VERSION),
                ("normalized_evidence_hash", graph.normalized_hash),
            ),
        ),
        interpretation_assumptions=(
            f"compiler={COMPILER_VERSION}",
            f"configuration={context.config.config_hash}",
            f"ruleset={RULESET_VERSION}",
        ),
    )
    lane_config.validate_against_nodes(topology.as_loading_nodes())
    return topology, lane_config


def _resolve_signals(
    graph: NormalizedSourceGraph,
    topology: CanonicalTopology,
    resolved: ResolvedSemanticGraph,
    context: _Context,
) -> ResolvedFixedTimeSignalPlan | None:
    controllers: list[FixedTimeControllerPlan] = []
    owner_by_movement: dict[str, str] = {}
    stages_by_id = {item.source_id: item for item in graph.records_of_type("signal_stage")}
    movement_ids = {item.movement_id for item in resolved.movements if item.permitted}
    movement_by_id = {
        item.movement_id: item for item in resolved.movements if item.permitted
    }
    topology_node_ids = {item.node_id for item in topology.nodes}
    for record in sorted(graph.records_of_type("signal_controller"), key=lambda item: item.source_id):
        artifact = (
            record.source_id
            if record.source_id.startswith("controller:")
            else f"controller:{record.source_id}"
        )
        node_id, node_fields = _unique_value(record, "node_id")
        signalized, signalized_fields = _unique_value(record, "signalized")
        controlled, controlled_fields = _unique_value(record, "controlled_movement_ids")
        stage_ids, stage_id_fields = _unique_value(record, "stage_ids")
        cycle, cycle_fields = _unique_value(record, "cycle_ticks")
        offset, offset_fields = _unique_value(record, "offset_ticks")
        cycle_override = context.selected_override(artifact, "cycle_ticks")
        if cycle_override is not None:
            cycle = _apply_override(
                context,
                artifact,
                "cycle_ticks",
                cycle_override,
                cycle_fields,
                _positive_int,
                _distinct_values(cycle_fields),
            )
        offset_override = context.selected_override(artifact, "offset_ticks")
        if offset_override is not None:
            offset = _apply_override(
                context,
                artifact,
                "offset_ticks",
                offset_override,
                offset_fields,
                _nonnegative_int,
                _distinct_values(offset_fields),
            )
        if signalized is not True:
            context.diagnostic(
                DiagnosticSeverity.STRUCTURAL,
                "UC.SIGNAL.CONTROLLER_NOT_SIGNALIZED",
                "signal controller record must explicitly state signalized=true",
                artifact_id=artifact,
                evidence_refs=(record.evidence_id,),
            )
            continue
        if not isinstance(node_id, str) or not isinstance(controlled, list) or not controlled:
            _unresolved_field(
                context,
                artifact,
                "controller_binding",
                node_fields + controlled_fields,
                "signal controller requires node and controlled movements",
                code="UC.SIGNAL.UNRESOLVED_BINDING",
            )
            continue
        unknown = sorted(set(str(item) for item in controlled) - movement_ids)
        if unknown:
            context.diagnostic(
                DiagnosticSeverity.STRUCTURAL,
                "UC.SIGNAL.UNKNOWN_MOVEMENT",
                f"signal controller references unknown or prohibited movements: {unknown}",
                artifact_id=artifact,
                evidence_refs=tuple(item.evidence_id for item in controlled_fields),
            )
            continue
        if node_id not in topology_node_ids:
            context.diagnostic(
                DiagnosticSeverity.STRUCTURAL,
                "UC.SIGNAL.UNKNOWN_CONTROLLER_NODE",
                "signal controller references an unknown topology node",
                artifact_id=artifact,
                evidence_refs=tuple(item.evidence_id for item in node_fields),
            )
            continue
        wrong_node = tuple(
            sorted(
                movement_id
                for movement_id in (str(item) for item in controlled)
                if movement_by_id[movement_id].node_id != node_id
            )
        )
        if wrong_node:
            context.diagnostic(
                DiagnosticSeverity.STRUCTURAL,
                "UC.SIGNAL.NODE_OWNERSHIP",
                f"controlled movements do not belong to controller node: {wrong_node}",
                artifact_id=artifact,
                evidence_refs=tuple(item.evidence_id for item in controlled_fields),
            )
            continue
        missing_groups = tuple(
            sorted(
                movement_id
                for movement_id in (str(item) for item in controlled)
                if movement_by_id[movement_id].signal_group_id is None
            )
        )
        if missing_groups:
            for movement_id in missing_groups:
                _unresolved_field(
                    context,
                    movement_id,
                    "signal_group_id",
                    (),
                    "controlled movement requires an observed signal-group binding",
                    code="UC.SIGNAL.MISSING_GROUP_BINDING",
                )
            continue
        for movement_id in (str(item) for item in controlled):
            prior_owner = owner_by_movement.get(movement_id)
            if prior_owner is not None and prior_owner != record.source_id:
                context.diagnostic(
                    DiagnosticSeverity.STRUCTURAL,
                    "UC.SIGNAL.MULTIPLE_CONTROLLER_OWNERS",
                    f"movement is controlled by both {prior_owner} and {record.source_id}",
                    artifact_id=movement_id,
                    evidence_refs=(record.evidence_id,),
                )
            owner_by_movement[movement_id] = record.source_id

        complete_explicit = (
            isinstance(stage_ids, list)
            and bool(stage_ids)
            and isinstance(cycle, int)
            and isinstance(offset, int)
        )
        fixed_stages: list[FixedTimeStage] = []
        stage_evidence: list[NormalizedField] = []
        if complete_explicit:
            for stage_id in stage_ids:
                stage_record = stages_by_id.get(str(stage_id))
                if stage_record is None:
                    complete_explicit = False
                    continue
                owner, owner_fields = _unique_value(stage_record, "controller_id")
                duration, duration_fields = _unique_value(stage_record, "duration_ticks")
                permitted, permitted_fields = _unique_value(stage_record, "permitted_movement_ids")
                stage_evidence.extend(owner_fields + duration_fields + permitted_fields)
                if owner != record.source_id or not isinstance(duration, int) or not isinstance(permitted, list):
                    complete_explicit = False
                    continue
                invalid_permissions = sorted(
                    set(str(item) for item in permitted)
                    - set(str(item) for item in controlled)
                )
                if invalid_permissions:
                    context.diagnostic(
                        DiagnosticSeverity.STRUCTURAL,
                        "UC.SIGNAL.STAGE_PERMISSION_OUTSIDE_CONTROLLER",
                        f"stage permits movements outside controller ownership: {invalid_permissions}",
                        artifact_id=str(stage_id),
                        evidence_refs=tuple(item.evidence_id for item in permitted_fields),
                    )
                    complete_explicit = False
                    continue
                fixed_stages.append(
                    FixedTimeStage(
                        stage_id=str(stage_id),
                        duration_ticks=duration,
                        permitted_movement_ids=tuple(sorted(str(item) for item in permitted)),
                    )
                )
            if complete_explicit and sum(item.duration_ticks for item in fixed_stages) != cycle:
                complete_explicit = False

        if not complete_explicit and context.config.allow_default_signal_plans:
            if cycle_override is None:
                cycle = context.config.default_signal_cycle_ticks
            if offset_override is None:
                offset = 0
            if not isinstance(cycle, int) or not isinstance(offset, int):
                _unresolved_field(
                    context,
                    artifact,
                    "default_timing",
                    (),
                    "configured signal default plus overrides did not resolve integer timing",
                    code="UC.SIGNAL.UNRESOLVED_TIMING",
                )
                continue
            fixed_stages = [
                FixedTimeStage(
                    stage_id=f"default:{record.source_id}:all-green",
                    duration_ticks=cycle,
                    permitted_movement_ids=tuple(sorted(str(item) for item in controlled)),
                )
            ]
            classification = ProvenanceClass.DEFAULTED
            rule_id = "signal.configured-default"
            reason = "configuration explicitly permits the deterministic all-green default"
            evidence = signalized_fields + node_fields + controlled_fields
        elif complete_explicit:
            classification = ProvenanceClass.OBSERVED
            rule_id = "signal.explicit-fixed-time"
            reason = "complete fixed-time stages and exact cycle supplied"
            evidence = cycle_fields + offset_fields + stage_id_fields + tuple(stage_evidence)
        else:
            missing = []
            if not isinstance(cycle, int):
                missing.append("cycle_ticks")
            if not isinstance(offset, int):
                missing.append("offset_ticks")
            if not isinstance(stage_ids, list) or not stage_ids:
                missing.append("stage_ids")
            if isinstance(stage_ids, list):
                for stage_id in stage_ids:
                    stage = stages_by_id.get(str(stage_id))
                    if stage is None or not isinstance(_unique_value(stage, "duration_ticks")[0], int):
                        missing.append(f"stage:{stage_id}:duration_ticks")
            if not missing:
                missing.append("stage_duration_sum_or_permissions")
            for field_path in sorted(set(missing)):
                _unresolved_field(
                    context,
                    artifact,
                    field_path,
                    (),
                    "signal timing is mandatory and no configured default is permitted",
                    code="UC.SIGNAL.UNRESOLVED_TIMING",
                )
            context.diagnostic(
                DiagnosticSeverity.REFUSAL,
                "UC.SIGNAL.PLAN_REFUSED",
                "signalized controller remains signalized but has no executable fixed-time plan",
                artifact_id=artifact,
            )
            continue

        overridden_fields = {
            item.field_path
            for item in context.provenance
            if item.artifact_id == artifact
            and item.classification == ProvenanceClass.OVERRIDDEN
        }
        for field_path, value in (
            ("node_id", node_id),
            ("controlled_movement_ids", controlled),
            ("cycle_ticks", cycle),
            ("offset_ticks", offset),
            ("stages", [item.to_dict() for item in fixed_stages]),
        ):
            if field_path in overridden_fields:
                continue
            context.add_provenance(
                artifact_id=artifact,
                field_path=field_path,
                classification=classification,
                value=value,
                evidence=evidence,
                rule_id=rule_id,
                reason=reason,
                confidence="observed" if classification == ProvenanceClass.OBSERVED else "configured",
            )
        for stage in fixed_stages:
            stage_source = stages_by_id.get(stage.stage_id)
            for field_path, value in (
                ("stage_id", stage.stage_id),
                ("duration_ticks", stage.duration_ticks),
                ("permitted_movement_ids", list(stage.permitted_movement_ids)),
            ):
                context.add_provenance(
                    artifact_id=stage.stage_id,
                    field_path=field_path,
                    classification=classification,
                    value=value,
                    evidence_refs=(
                        () if stage_source is None else (stage_source.evidence_id,)
                    ),
                    rule_id=rule_id,
                    reason=reason,
                    confidence="observed" if classification == ProvenanceClass.OBSERVED else "configured",
                )
        provenance = tuple(
            ResolvedValueProvenance(
                field_path=item.field_path,
                resolution_status=item.classification.value,  # type: ignore[arg-type]
                source_ref=item.record_hash,
                metadata=(("compiler_provenance_hash", item.record_hash),),
            )
            for item in context.provenance
            if item.artifact_id == artifact and item.classification != ProvenanceClass.UNRESOLVED
        )
        controllers.append(
            FixedTimeControllerPlan(
                controller_id=record.source_id,
                node_id=node_id,
                cycle_ticks=cycle,
                offset_ticks=offset,
                stages=tuple(fixed_stages),
                controlled_movement_ids=tuple(sorted(str(item) for item in controlled)),
                provenance=provenance,
            )
        )
    group_owners: dict[str, set[str]] = {}
    controller_ids = {item.source_id for item in graph.records_of_type("signal_controller")}
    for binding in graph.records_of_type("signal_binding"):
        controller_id, controller_fields = _unique_value(binding, "controller_id")
        movement_id, movement_fields = _unique_value(binding, "movement_id")
        signal_group_id, group_fields = _unique_value(binding, "signal_group_id")
        if not isinstance(controller_id, str) or controller_id not in controller_ids:
            context.diagnostic(
                DiagnosticSeverity.STRUCTURAL,
                "UC.SIGNAL.BINDING_UNKNOWN_CONTROLLER",
                "signal-group binding references an unknown controller",
                artifact_id=f"signal-binding:{binding.source_id}",
                evidence_refs=tuple(item.evidence_id for item in controller_fields),
            )
            continue
        if isinstance(movement_id, str) and isinstance(signal_group_id, str):
            declared_owner = owner_by_movement.get(movement_id)
            if declared_owner != controller_id:
                context.diagnostic(
                    DiagnosticSeverity.STRUCTURAL,
                    "UC.SIGNAL.BINDING_OWNERSHIP_MISMATCH",
                    "signal-group binding controller does not own the movement",
                    artifact_id=movement_id,
                    evidence_refs=tuple(item.evidence_id for item in movement_fields),
                )
            group_owners.setdefault(signal_group_id, set()).add(controller_id)
    for group_id, owners in sorted(group_owners.items()):
        if len(owners) > 1:
            context.diagnostic(
                DiagnosticSeverity.STRUCTURAL,
                "UC.SIGNAL.GROUP_MULTIPLE_CONTROLLERS",
                f"signal group is owned by multiple controllers: {sorted(owners)}",
                artifact_id=f"signal-group:{group_id}",
            )

    plan = ResolvedFixedTimeSignalPlan(
        controllers=tuple(controllers),
        provenance_refs=tuple(
            item.record_hash
            for item in context.provenance
            if item.artifact_id.startswith("controller:")
            and item.classification != ProvenanceClass.UNRESOLVED
        ),
        metadata=(
            ("compiler_version", COMPILER_VERSION),
            ("compiler_configuration_hash", context.config.config_hash),
        ),
    )
    if _has_blocking_diagnostics(context.diagnostics):
        return None
    FixedTimeSignalPlanEvaluator(plan, topology.as_loading_nodes())
    return plan


def _apply_override(
    context: _Context,
    artifact: str,
    field_path: str,
    override: CompilerOverride,
    evidence: tuple[NormalizedField, ...],
    validator: Callable[[object], object],
    prior_value: object,
) -> object | None:
    try:
        value = validator(override.replacement_value)
    except (TypeError, ValueError) as exc:
        return _unresolved_field(
            context,
            artifact,
            field_path,
            evidence,
            f"invalid override replacement: {exc}",
            code="UC.OVERRIDE.INVALID_VALUE",
        )
    context.add_provenance(
        artifact_id=artifact,
        field_path=field_path,
        classification=ProvenanceClass.OVERRIDDEN,
        value=value,
        evidence=evidence,
        source_field=field_path,
        rule_id="compiler.override",
        reason=override.reason,
        confidence="explicit",
        override=override,
        prior_value=prior_value,
    )
    if isinstance(prior_value, (tuple, list)) and len(prior_value) > 1:
        context.diagnostic(
            DiagnosticSeverity.INFO,
            "UC.OVERRIDE.REPAIRED_CONFLICT",
            "explicit override replaced conflicting retained evidence",
            artifact_id=artifact,
            field_path=field_path,
            evidence_refs=tuple(item.evidence_id for item in evidence)
            + (override.override_id,),
        )
    return value


def _unresolved_field(
    context: _Context,
    artifact: str,
    field_path: str,
    evidence: tuple[NormalizedField, ...],
    reason: str,
    *,
    code: str = "UC.SEMANTIC.UNRESOLVED_MANDATORY",
) -> None:
    context.add_provenance(
        artifact_id=artifact,
        field_path=field_path,
        classification=ProvenanceClass.UNRESOLVED,
        value=None,
        evidence=evidence,
        source_field=field_path,
        rule_id="compiler.unresolved",
        reason=reason,
        confidence="none",
    )
    context.diagnostic(
        DiagnosticSeverity.UNRESOLVED,
        code,
        reason,
        artifact_id=artifact,
        field_path=field_path,
        evidence_refs=tuple(item.evidence_id for item in evidence),
    )
    return None


def _unique_value(record: NormalizedRecord, name: str) -> tuple[object | None, tuple[NormalizedField, ...]]:
    values = record.values(name)
    distinct = _distinct_values(values)
    return (distinct[0] if len(distinct) == 1 else None, values)


def _distinct_values(fields: Iterable[NormalizedField]) -> tuple[object, ...]:
    by_json = {
        canonical_json(item.normalized_value): item.normalized_value
        for item in fields
        if item.normalized_value is not None
    }
    return tuple(by_json[key] for key in sorted(by_json))


def _positive_float(value: object) -> float:
    if isinstance(value, bool):
        raise TypeError("boolean is not numeric")
    parsed = float(value)  # type: ignore[arg-type]
    if not parsed > 0:
        raise ValueError("value must be positive")
    return parsed


def _forward_direction(value: object) -> str:
    if value != "forward":
        raise ValueError("only explicit forward directed arcs are supported")
    return "forward"


def _positive_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("value must be an integer")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError("value must be integral")
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("value must be positive")
    return parsed


def _nonnegative_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("value must be an integer")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError("value must be integral")
    parsed = int(value)
    if parsed < 0:
        raise ValueError("value must be non-negative")
    return parsed


def _bool_value(value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError("value must be boolean")
    return value


def _has_blocking_diagnostics(diagnostics: Iterable[CompilerDiagnostic]) -> bool:
    return any(
        item.severity
        in (
            DiagnosticSeverity.UNRESOLVED,
            DiagnosticSeverity.STRUCTURAL,
            DiagnosticSeverity.INTERNAL,
            DiagnosticSeverity.REFUSAL,
        )
        for item in diagnostics
    )


def _sorted_diagnostics(items: Iterable[CompilerDiagnostic]) -> tuple[CompilerDiagnostic, ...]:
    return tuple(
        sorted(
            items,
            key=lambda item: (
                item.severity.value,
                item.code,
                item.artifact_id or "",
                item.field_path or "",
                item.message,
                item.evidence_refs,
            ),
        )
    )


def _sorted_provenance(items: Iterable[ProvenanceRecord]) -> tuple[ProvenanceRecord, ...]:
    return tuple(
        sorted(
            items,
            key=lambda item: (
                item.artifact_id,
                item.field_path,
                item.record_hash,
            ),
        )
    )


def _disposition(
    executable: ExecutableNetwork | None,
    diagnostics: tuple[CompilerDiagnostic, ...],
    provenance: tuple[ProvenanceRecord, ...],
) -> CompilationDisposition:
    if any(item.severity == DiagnosticSeverity.INTERNAL for item in diagnostics):
        return CompilationDisposition.INTERNALLY_INCONSISTENT
    if any(item.severity == DiagnosticSeverity.STRUCTURAL for item in diagnostics):
        return CompilationDisposition.STRUCTURALLY_INVALID
    if executable is None:
        return CompilationDisposition.UNRESOLVED
    if any(item.severity == DiagnosticSeverity.WARNING for item in diagnostics) or any(
        item.classification == ProvenanceClass.DEFAULTED for item in provenance
    ):
        return CompilationDisposition.EXECUTABLE_WITH_WARNINGS
    return CompilationDisposition.EXECUTABLE


def _canonical_node_payload(node: CanonicalNode) -> dict[str, object]:
    junction = node.junction_spec()
    return {
        "node_id": node.node_id,
        "source_node_id": node.source_node_id,
        "incoming_link_ids": list(node.incoming_link_ids),
        "outgoing_link_ids": list(node.outgoing_link_ids),
        "movements": [
            {
                "movement_id": item.movement_id,
                "upstream_link_id": item.upstream_link_id,
                "downstream_link_id": item.downstream_link_id,
                "priority_weight": item.priority_weight,
                "lane_group_ids": list(item.lane_group_ids),
                "signal_group_id": item.signal_group_id,
            }
            for item in junction.movement_specs
        ],
        "lane_group_ids": list(junction.lane_group_ids),
        "movement_lane_group_mappings": [
            [movement_id, list(group_ids)]
            for movement_id, group_ids in junction.movement_lane_group_mappings
        ],
        "lane_group_capacities": [list(item) for item in junction.lane_group_capacities],
    }


def _executable_node_payload(node: CanonicalNode) -> dict[str, object]:
    """Return all junction fields consumed by execution, excluding source identity."""

    junction = node.junction_spec()
    return {
        "node_id": node.node_id,
        "incoming_link_ids": list(junction.incoming_link_ids),
        "outgoing_link_ids": list(junction.outgoing_link_ids),
        "movements": [
            {
                "movement_id": item.movement_id,
                "upstream_link_id": item.upstream_link_id,
                "downstream_link_id": item.downstream_link_id,
                "priority_weight": item.priority_weight,
                "lane_group_ids": list(item.lane_group_ids),
                "conflict_resource_ids": list(item.conflict_resource_ids),
                "signal_group_id": item.signal_group_id,
            }
            for item in junction.movement_specs
        ],
        "lane_group_ids": list(junction.lane_group_ids),
        "movement_lane_group_mappings": [
            [movement_id, list(group_ids)]
            for movement_id, group_ids in junction.movement_lane_group_mappings
        ],
        "lane_group_capacities": [list(item) for item in junction.lane_group_capacities],
        "conflict_resource_ids": list(junction.conflict_resource_ids),
        "conflict_resource_capacities": [
            list(item) for item in junction.conflict_resource_capacities
        ],
        "governance_refs": list(junction.governance_refs),
        "fifo_policy": junction.fifo_policy,
    }


def _lane_group_semantic_payload(
    config: LaneGroupExtensionConfig,
) -> dict[str, object]:
    """Return loader-consumed lane-group semantics without audit provenance."""

    return {
        "schema_version": config.schema_version,
        "extension_version": config.extension_version,
        "representation_mode": config.representation_mode,
        "reassignment_policy": config.reassignment_policy,
        "lane_groups": [
            {
                "lane_group_id": item.lane_group_id,
                "node_id": item.node_id,
                "incoming_link_id": item.incoming_link_id,
                "allowed_movement_ids": list(item.allowed_movement_ids),
                "service_capacity_per_tick": item.service_capacity_per_tick,
            }
            for item in sorted(
                config.lane_groups,
                key=lambda value: (value.node_id, value.lane_group_id),
            )
        ],
    }
