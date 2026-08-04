"""Deterministic fixed-time signal control above the frozen loading kernel.

The extension owns no physical state and emits no canonical events.  It binds a
resolved, immutable plan to immutable topology movements, evaluates Boolean
permission at integer loading ticks, and supplies the resulting signal-group
set through the frozen allocator's existing signal-gate input.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from typing import Literal, Protocol, Self

from urban_cybernetics.core import Node
from urban_cybernetics.loading.engine import LoadingEngine
from urban_cybernetics.loading.transfer_policy import (
    GeneralMovementAllocator,
    JunctionAllocationInput,
)
from urban_cybernetics.extensions.fixed_time_signal_overrides import (
    SignalOverrideCommand,
    SignalOverrideReceipt,
    SignalOverrideResolution,
    SignalOverrideStore,
)


FIXED_TIME_SIGNAL_EXTENSION_VERSION = "fixed-time-signal-extension-v1"
FIXED_TIME_SIGNAL_SCHEMA_VERSION = "uc.resolved-fixed-time-signal-plan.v1"
FIXED_TIME_SIGNAL_CONFIG_SCHEMA_VERSION = "uc.fixed-time-signal-config.v1"
FIXED_TIME_OWNS_CONTROLLED_GROUPS = "fixed_time_owns_controlled_groups"
RESOLUTION_STATUSES = frozenset(
    ("observed", "inferred", "defaulted", "overridden")
)
ResolutionStatus = Literal["observed", "inferred", "defaulted", "overridden"]


class FixedTimePlanValidationError(ValueError):
    """Reject a malformed, unresolved, or topology-incompatible plan."""

    def __init__(self, diagnostics: str | Iterable[str]) -> None:
        items = (
            (diagnostics,)
            if isinstance(diagnostics, str)
            else tuple(str(item) for item in diagnostics)
        )
        self.diagnostics = items
        super().__init__("; ".join(items))


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise FixedTimePlanValidationError(
            f"{field_name} must be a resolved non-empty string"
        )
    return value


def _require_int(value: object, field_name: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FixedTimePlanValidationError(
            f"{field_name} must be a resolved integer"
        )
    if positive and value <= 0:
        raise FixedTimePlanValidationError(f"{field_name} must be positive")
    return value


def _normalise_strings(values: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise FixedTimePlanValidationError(f"{field_name} must be a tuple")
    normalised = tuple(_require_string(value, field_name) for value in values)
    if len(normalised) != len(set(normalised)):
        raise FixedTimePlanValidationError(f"{field_name} contains duplicate IDs")
    return normalised


def _normalise_metadata(
    values: object,
    field_name: str,
) -> tuple[tuple[str, str], ...]:
    if not isinstance(values, tuple):
        raise FixedTimePlanValidationError(f"{field_name} must be a tuple")
    normalised: list[tuple[str, str]] = []
    keys: set[str] = set()
    for item in values:
        if not isinstance(item, tuple) or len(item) != 2:
            raise FixedTimePlanValidationError(
                f"{field_name} must contain (key, value) tuples"
            )
        key = _require_string(item[0], f"{field_name} key")
        value = _require_string(item[1], f"{field_name} value")
        if key in keys:
            raise FixedTimePlanValidationError(
                f"{field_name} contains duplicate key: {key}"
            )
        keys.add(key)
        normalised.append((key, value))
    return tuple(sorted(normalised))


def _canonical_hash(payload: object) -> str:
    serialised = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def _check_keys(
    payload: object,
    *,
    required: frozenset[str],
    optional: frozenset[str],
    context: str,
) -> None:
    if not isinstance(payload, Mapping):
        raise FixedTimePlanValidationError(f"{context} must be an object")
    missing = sorted(required - payload.keys())
    unknown = sorted(payload.keys() - required - optional)
    diagnostics: list[str] = []
    if missing:
        diagnostics.append(f"{context} has unresolved/missing fields: {missing}")
    if unknown:
        diagnostics.append(f"{context} has unknown fields: {unknown}")
    if diagnostics:
        raise FixedTimePlanValidationError(diagnostics)


def _metadata_from_json(
    values: object,
    field_name: str,
) -> tuple[tuple[object, object], ...]:
    if not isinstance(values, list):
        raise FixedTimePlanValidationError(f"{field_name} must be a list")
    if any(not isinstance(item, list) or len(item) != 2 for item in values):
        raise FixedTimePlanValidationError(
            f"{field_name} must contain two-item lists"
        )
    return tuple((item[0], item[1]) for item in values)


@dataclass(frozen=True, slots=True)
class ResolvedValueProvenance:
    """Compiler-facing origin record for one resolved executable value."""

    field_path: str
    resolution_status: ResolutionStatus
    source_ref: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _require_string(self.field_path, "provenance field_path")
        if self.resolution_status not in RESOLUTION_STATUSES:
            raise FixedTimePlanValidationError(
                "provenance resolution_status must be observed, inferred, "
                "defaulted, or overridden"
            )
        if self.source_ref is not None:
            _require_string(self.source_ref, "provenance source_ref")
        object.__setattr__(
            self,
            "metadata",
            _normalise_metadata(self.metadata, "provenance metadata"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "field_path": self.field_path,
            "resolution_status": self.resolution_status,
            "source_ref": self.source_ref,
            "metadata": [list(item) for item in self.metadata],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        _check_keys(
            payload,
            required=frozenset(("field_path", "resolution_status")),
            optional=frozenset(("source_ref", "metadata")),
            context="resolved provenance",
        )
        metadata = payload.get("metadata", [])
        return cls(
            field_path=payload["field_path"],  # type: ignore[arg-type]
            resolution_status=payload["resolution_status"],  # type: ignore[arg-type]
            source_ref=payload.get("source_ref"),  # type: ignore[arg-type]
            metadata=_metadata_from_json(  # type: ignore[arg-type]
                metadata,
                "provenance metadata",
            ),
        )


@dataclass(frozen=True, slots=True)
class FixedTimeStage:
    """One ordered half-open interval in a resolved controller cycle."""

    stage_id: str
    duration_ticks: int
    permitted_movement_ids: tuple[str, ...]
    classification: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _require_string(self.stage_id, "stage_id")
        _require_int(self.duration_ticks, "stage duration_ticks", positive=True)
        object.__setattr__(
            self,
            "permitted_movement_ids",
            _normalise_strings(
                self.permitted_movement_ids,
                f"stage {self.stage_id} permitted_movement_ids",
            ),
        )
        if self.classification is not None:
            _require_string(self.classification, "stage classification")
        object.__setattr__(
            self,
            "metadata",
            _normalise_metadata(self.metadata, f"stage {self.stage_id} metadata"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "stage_id": self.stage_id,
            "duration_ticks": self.duration_ticks,
            "permitted_movement_ids": list(self.permitted_movement_ids),
            "classification": self.classification,
            "metadata": [list(item) for item in self.metadata],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        _check_keys(
            payload,
            required=frozenset(
                ("stage_id", "duration_ticks", "permitted_movement_ids")
            ),
            optional=frozenset(("classification", "metadata")),
            context="fixed-time stage",
        )
        movements = payload["permitted_movement_ids"]
        metadata = payload.get("metadata", [])
        if not isinstance(movements, list):
            raise FixedTimePlanValidationError(
                "stage permitted_movement_ids must be a list"
            )
        return cls(
            stage_id=payload["stage_id"],  # type: ignore[arg-type]
            duration_ticks=payload["duration_ticks"],  # type: ignore[arg-type]
            permitted_movement_ids=tuple(movements),  # type: ignore[arg-type]
            classification=payload.get("classification"),  # type: ignore[arg-type]
            metadata=_metadata_from_json(  # type: ignore[arg-type]
                metadata,
                "stage metadata",
            ),
        )


@dataclass(frozen=True, slots=True)
class FixedTimeControllerPlan:
    """Resolved executable plan for one fixed-time controller."""

    controller_id: str
    node_id: str
    cycle_ticks: int
    offset_ticks: int
    stages: tuple[FixedTimeStage, ...]
    controlled_movement_ids: tuple[str, ...]
    provenance: tuple[ResolvedValueProvenance, ...] = ()
    schema_version: str = FIXED_TIME_SIGNAL_SCHEMA_VERSION
    extension_version: str = FIXED_TIME_SIGNAL_EXTENSION_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != FIXED_TIME_SIGNAL_SCHEMA_VERSION:
            raise FixedTimePlanValidationError(
                f"unsupported controller schema_version: {self.schema_version}"
            )
        if self.extension_version != FIXED_TIME_SIGNAL_EXTENSION_VERSION:
            raise FixedTimePlanValidationError(
                f"unsupported controller extension_version: {self.extension_version}"
            )
        _require_string(self.controller_id, "controller_id")
        _require_string(self.node_id, "controller node_id")
        cycle_ticks = _require_int(self.cycle_ticks, "cycle_ticks", positive=True)
        offset_ticks = _require_int(self.offset_ticks, "offset_ticks")
        object.__setattr__(self, "offset_ticks", offset_ticks % cycle_ticks)
        if not isinstance(self.stages, tuple) or not self.stages:
            raise FixedTimePlanValidationError(
                f"controller {self.controller_id} stages must be a non-empty tuple"
            )
        if any(not isinstance(stage, FixedTimeStage) for stage in self.stages):
            raise FixedTimePlanValidationError(
                f"controller {self.controller_id} stages must be FixedTimeStage records"
            )
        stage_ids = tuple(stage.stage_id for stage in self.stages)
        if len(stage_ids) != len(set(stage_ids)):
            raise FixedTimePlanValidationError(
                f"controller {self.controller_id} has duplicate stage IDs"
            )
        movements = _normalise_strings(
            self.controlled_movement_ids,
            f"controller {self.controller_id} controlled_movement_ids",
        )
        if not movements:
            raise FixedTimePlanValidationError(
                f"controller {self.controller_id} controls no movements"
            )
        object.__setattr__(self, "controlled_movement_ids", movements)
        if sum(stage.duration_ticks for stage in self.stages) != cycle_ticks:
            raise FixedTimePlanValidationError(
                f"controller {self.controller_id} stage durations must sum exactly "
                f"to cycle_ticks={cycle_ticks}"
            )
        controlled = set(movements)
        for stage in self.stages:
            unknown = sorted(set(stage.permitted_movement_ids) - controlled)
            if unknown:
                raise FixedTimePlanValidationError(
                    f"stage {stage.stage_id} references movements not controlled by "
                    f"{self.controller_id}: {unknown}"
                )
        if not isinstance(self.provenance, tuple) or any(
            not isinstance(item, ResolvedValueProvenance)
            for item in self.provenance
        ):
            raise FixedTimePlanValidationError(
                "controller provenance must contain ResolvedValueProvenance records"
            )

    @property
    def semantic_hash(self) -> str:
        """Hash only executable timing and movement permission semantics."""

        return _canonical_hash(
            {
                "controller_id": self.controller_id,
                "schema_version": self.schema_version,
                "extension_version": self.extension_version,
                "node_id": self.node_id,
                "cycle_ticks": self.cycle_ticks,
                "offset_ticks": self.offset_ticks,
                "controlled_movement_ids": list(self.controlled_movement_ids),
                "stages": [
                    {
                        "stage_id": stage.stage_id,
                        "duration_ticks": stage.duration_ticks,
                        "permitted_movement_ids": list(
                            stage.permitted_movement_ids
                        ),
                    }
                    for stage in self.stages
                ],
            }
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "controller_id": self.controller_id,
            "schema_version": self.schema_version,
            "extension_version": self.extension_version,
            "node_id": self.node_id,
            "cycle_ticks": self.cycle_ticks,
            "offset_ticks": self.offset_ticks,
            "stages": [stage.to_dict() for stage in self.stages],
            "controlled_movement_ids": list(self.controlled_movement_ids),
            "provenance": [item.to_dict() for item in self.provenance],
            "semantic_hash": self.semantic_hash,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        _check_keys(
            payload,
            required=frozenset(
                (
                    "controller_id",
                    "schema_version",
                    "extension_version",
                    "node_id",
                    "cycle_ticks",
                    "offset_ticks",
                    "stages",
                    "controlled_movement_ids",
                )
            ),
            optional=frozenset(("provenance", "semantic_hash")),
            context="fixed-time controller",
        )
        stages = payload["stages"]
        controlled = payload["controlled_movement_ids"]
        provenance = payload.get("provenance", [])
        if not isinstance(stages, list):
            raise FixedTimePlanValidationError("controller stages must be a list")
        if not isinstance(controlled, list):
            raise FixedTimePlanValidationError(
                "controller controlled_movement_ids must be a list"
            )
        if not isinstance(provenance, list):
            raise FixedTimePlanValidationError("controller provenance must be a list")
        controller = cls(
            controller_id=payload["controller_id"],  # type: ignore[arg-type]
            schema_version=payload["schema_version"],  # type: ignore[arg-type]
            extension_version=payload["extension_version"],  # type: ignore[arg-type]
            node_id=payload["node_id"],  # type: ignore[arg-type]
            cycle_ticks=payload["cycle_ticks"],  # type: ignore[arg-type]
            offset_ticks=payload["offset_ticks"],  # type: ignore[arg-type]
            stages=tuple(
                FixedTimeStage.from_dict(item)  # type: ignore[arg-type]
                for item in stages
            ),
            controlled_movement_ids=tuple(controlled),  # type: ignore[arg-type]
            provenance=tuple(
                ResolvedValueProvenance.from_dict(item)  # type: ignore[arg-type]
                for item in provenance
            ),
        )
        declared_hash = payload.get("semantic_hash")
        if declared_hash is not None and declared_hash != controller.semantic_hash:
            raise FixedTimePlanValidationError(
                f"controller {controller.controller_id} semantic_hash mismatch"
            )
        return controller


@dataclass(frozen=True, slots=True)
class ResolvedFixedTimeSignalPlan:
    """Versioned set of resolved fixed-time controller plans."""

    controllers: tuple[FixedTimeControllerPlan, ...]
    provenance_refs: tuple[str, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()
    schema_version: str = FIXED_TIME_SIGNAL_SCHEMA_VERSION
    extension_version: str = FIXED_TIME_SIGNAL_EXTENSION_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != FIXED_TIME_SIGNAL_SCHEMA_VERSION:
            raise FixedTimePlanValidationError(
                f"unsupported fixed-time schema_version: {self.schema_version}"
            )
        if self.extension_version != FIXED_TIME_SIGNAL_EXTENSION_VERSION:
            raise FixedTimePlanValidationError(
                f"unsupported fixed-time extension_version: {self.extension_version}"
            )
        if not isinstance(self.controllers, tuple) or any(
            not isinstance(item, FixedTimeControllerPlan)
            for item in self.controllers
        ):
            raise FixedTimePlanValidationError(
                "controllers must be a tuple of FixedTimeControllerPlan records"
            )
        controller_ids = tuple(item.controller_id for item in self.controllers)
        if len(controller_ids) != len(set(controller_ids)):
            raise FixedTimePlanValidationError("duplicate controller IDs")
        stage_ids = tuple(
            stage.stage_id
            for controller in self.controllers
            for stage in controller.stages
        )
        if len(stage_ids) != len(set(stage_ids)):
            raise FixedTimePlanValidationError("duplicate stage IDs across plan")
        owner_by_movement: dict[str, str] = {}
        for controller in self.controllers:
            for movement_id in controller.controlled_movement_ids:
                prior = owner_by_movement.get(movement_id)
                if prior is not None:
                    raise FixedTimePlanValidationError(
                        f"ambiguous controller ownership for {movement_id}: "
                        f"{prior}, {controller.controller_id}"
                    )
                owner_by_movement[movement_id] = controller.controller_id
        object.__setattr__(
            self,
            "provenance_refs",
            _normalise_strings(self.provenance_refs, "plan provenance_refs"),
        )
        object.__setattr__(
            self,
            "metadata",
            _normalise_metadata(self.metadata, "plan metadata"),
        )

    @property
    def semantic_hash(self) -> str:
        return _canonical_hash(
            {
                "schema_version": self.schema_version,
                "extension_version": self.extension_version,
                "controllers": [
                    {
                        "controller_id": item.controller_id,
                        "semantic_hash": item.semantic_hash,
                    }
                    for item in self.controllers
                ],
            }
        )

    @property
    def configuration_hash(self) -> str:
        """Hash the complete resolved plan, including stable provenance."""

        return _canonical_hash(self.to_dict(include_hashes=False))

    def to_dict(self, *, include_hashes: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "extension_version": self.extension_version,
            "controllers": [item.to_dict() for item in self.controllers],
            "provenance_refs": list(self.provenance_refs),
            "metadata": [list(item) for item in self.metadata],
        }
        if not include_hashes:
            for controller in payload["controllers"]:  # type: ignore[union-attr]
                controller.pop("semantic_hash", None)
            return payload
        payload["semantic_hash"] = self.semantic_hash
        payload["configuration_hash"] = self.configuration_hash
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        _check_keys(
            payload,
            required=frozenset(
                ("schema_version", "extension_version", "controllers")
            ),
            optional=frozenset(
                (
                    "provenance_refs",
                    "metadata",
                    "semantic_hash",
                    "configuration_hash",
                )
            ),
            context="resolved fixed-time plan",
        )
        controllers = payload["controllers"]
        provenance_refs = payload.get("provenance_refs", [])
        metadata = payload.get("metadata", [])
        if not isinstance(controllers, list):
            raise FixedTimePlanValidationError("plan controllers must be a list")
        if not isinstance(provenance_refs, list):
            raise FixedTimePlanValidationError("plan provenance_refs must be a list")
        plan = cls(
            controllers=tuple(
                FixedTimeControllerPlan.from_dict(item)  # type: ignore[arg-type]
                for item in controllers
            ),
            provenance_refs=tuple(provenance_refs),  # type: ignore[arg-type]
            metadata=_metadata_from_json(  # type: ignore[arg-type]
                metadata,
                "plan metadata",
            ),
            schema_version=payload["schema_version"],  # type: ignore[arg-type]
            extension_version=payload["extension_version"],  # type: ignore[arg-type]
        )
        if payload.get("semantic_hash") not in (None, plan.semantic_hash):
            raise FixedTimePlanValidationError("plan semantic_hash mismatch")
        if payload.get("configuration_hash") not in (
            None,
            plan.configuration_hash,
        ):
            raise FixedTimePlanValidationError("plan configuration_hash mismatch")
        return plan

    @classmethod
    def from_json(cls, serialised: str) -> Self:
        try:
            payload = json.loads(serialised)
        except (TypeError, json.JSONDecodeError) as exc:
            raise FixedTimePlanValidationError(f"malformed plan JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise FixedTimePlanValidationError("resolved plan JSON must be an object")
        return cls.from_dict(payload)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"


@dataclass(frozen=True, slots=True)
class FixedTimeSignalConfig:
    """Versioned execution and manual-gate composition policy."""

    manual_gate_policy: str = FIXED_TIME_OWNS_CONTROLLED_GROUPS
    schema_version: str = FIXED_TIME_SIGNAL_CONFIG_SCHEMA_VERSION
    extension_version: str = FIXED_TIME_SIGNAL_EXTENSION_VERSION

    def __post_init__(self) -> None:
        if self.manual_gate_policy != FIXED_TIME_OWNS_CONTROLLED_GROUPS:
            raise FixedTimePlanValidationError(
                f"unsupported manual_gate_policy: {self.manual_gate_policy}"
            )
        if self.schema_version != FIXED_TIME_SIGNAL_CONFIG_SCHEMA_VERSION:
            raise FixedTimePlanValidationError(
                f"unsupported fixed-time config schema: {self.schema_version}"
            )
        if self.extension_version != FIXED_TIME_SIGNAL_EXTENSION_VERSION:
            raise FixedTimePlanValidationError(
                f"unsupported fixed-time extension: {self.extension_version}"
            )

    @property
    def config_hash(self) -> str:
        return _canonical_hash(asdict(self))


@dataclass(frozen=True, slots=True)
class FixedTimeSignalBaselineState:
    """Pure baseline programme state for one controlled movement."""

    tick: int
    controller_id: str
    stage_id: str
    stage_start_cycle_position: int
    stage_end_cycle_position: int
    cycle_position: int
    movement_id: str
    signal_group_id: str
    baseline_is_open: bool
    plan_hash: str
    plan_configuration_hash: str


@dataclass(frozen=True, slots=True)
class FixedTimeSignalGateEvidence:
    """Request-linked baseline, override resolution, and effective gate state."""

    tick: int
    controller_id: str
    stage_id: str
    stage_start_cycle_position: int
    stage_end_cycle_position: int
    cycle_position: int
    movement_id: str
    signal_group_id: str
    baseline_is_open: bool
    considered_override_ids: tuple[str, ...]
    cleared_override_ids: tuple[str, ...]
    selected_override_id: str | None
    selected_override_action: str | None
    selected_override_target_kind: str | None
    effective_is_open: bool
    plan_hash: str
    plan_configuration_hash: str
    override_store_config_hash: str
    override_store_hash: str
    request_packet_ids: tuple[str, ...] = ()


class FixedTimeSignalControlProvider(Protocol):
    """Interface consumed by the loading integration shell."""

    @property
    def configuration_hash(self) -> str: ...

    def assert_compatible_nodes(self, nodes: Iterable[Node]) -> None: ...

    def evaluate(
        self, movement_id: str, tick: int
    ) -> FixedTimeSignalBaselineState | None: ...

    def controlled_signal_group_ids(self, node_id: str) -> frozenset[str]: ...

    def controlled_movement_ids(self, node_id: str) -> tuple[str, ...]: ...

    @property
    def controller_ids(self) -> tuple[str, ...]: ...

    @property
    def signal_group_ids(self) -> tuple[str, ...]: ...


class FixedTimeSignalPlanEvaluator:
    """Pure evaluator for resolved fixed-time plans bound to immutable topology."""

    def __init__(
        self,
        plan: ResolvedFixedTimeSignalPlan,
        nodes: Iterable[Node],
        config: FixedTimeSignalConfig | None = None,
    ) -> None:
        if not isinstance(plan, ResolvedFixedTimeSignalPlan):
            raise TypeError("plan must be ResolvedFixedTimeSignalPlan")
        self.plan = plan
        self.config = config or FixedTimeSignalConfig()
        node_tuple = tuple(nodes)
        self._validate_and_bind(node_tuple)

    def _validate_and_bind(self, nodes: tuple[Node, ...]) -> None:
        diagnostics: list[str] = []
        node_by_id: dict[str, Node] = {}
        movement_locations: dict[str, tuple[str, str | None]] = {}
        signal_users: dict[str, list[tuple[str, str]]] = {}
        for node in nodes:
            if node.node_id in node_by_id:
                diagnostics.append(f"duplicate topology node_id: {node.node_id}")
            node_by_id[node.node_id] = node
            for movement in node.junction_spec.movement_specs:
                if movement.movement_id in movement_locations:
                    diagnostics.append(
                        f"duplicate topology movement_id: {movement.movement_id}"
                    )
                movement_locations[movement.movement_id] = (
                    node.node_id,
                    movement.signal_group_id,
                )
                if movement.signal_group_id is not None:
                    signal_users.setdefault(movement.signal_group_id, []).append(
                        (node.node_id, movement.movement_id)
                    )

        owner_by_movement: dict[str, str] = {}
        controller_by_id = {
            controller.controller_id: controller
            for controller in self.plan.controllers
        }
        movement_to_group: dict[str, str] = {}
        groups_by_node: dict[str, set[str]] = {}
        for controller in self.plan.controllers:
            node = node_by_id.get(controller.node_id)
            if node is None:
                diagnostics.append(
                    f"controller {controller.controller_id} references unknown "
                    f"node_id: {controller.node_id}"
                )
            for movement_id in controller.controlled_movement_ids:
                location = movement_locations.get(movement_id)
                if location is None:
                    diagnostics.append(
                        f"controller {controller.controller_id} references unknown "
                        f"movement_id: {movement_id}"
                    )
                    continue
                node_id, signal_group_id = location
                if node_id != controller.node_id:
                    diagnostics.append(
                        f"movement {movement_id} belongs to node {node_id}, not "
                        f"controller node {controller.node_id}"
                    )
                if signal_group_id is None:
                    diagnostics.append(
                        f"controlled movement {movement_id} has no signal_group_id "
                        "for the existing signal gate"
                    )
                    continue
                owner_by_movement[movement_id] = controller.controller_id
                movement_to_group[movement_id] = signal_group_id
                groups_by_node.setdefault(controller.node_id, set()).add(
                    signal_group_id
                )

        for signal_group_id, users in signal_users.items():
            controlled_users = [
                (node_id, movement_id, owner_by_movement.get(movement_id))
                for node_id, movement_id in users
                if movement_id in owner_by_movement
            ]
            if not controlled_users:
                continue
            owners = {owner for _, _, owner in controlled_users}
            if len(controlled_users) != len(users) or len(owners) != 1:
                diagnostics.append(
                    f"signal_group_id {signal_group_id} is shared across fixed-time "
                    "and uncontrolled or differently owned movements"
                )
                continue
            owner = next(iter(owners))
            assert owner is not None
            controller = controller_by_id[owner]
            movements = tuple(item[1] for item in controlled_users)
            for stage in controller.stages:
                permissions = {
                    movement_id in stage.permitted_movement_ids
                    for movement_id in movements
                }
                if len(permissions) > 1:
                    diagnostics.append(
                        f"stage {stage.stage_id} gives inconsistent permission to "
                        f"movements sharing signal_group_id {signal_group_id}"
                    )

        if diagnostics:
            raise FixedTimePlanValidationError(diagnostics)

        self._node_ids = frozenset(node_by_id)
        self._controller_by_id = controller_by_id
        self._controller_by_movement = {
            movement_id: controller_by_id[controller_id]
            for movement_id, controller_id in owner_by_movement.items()
        }
        self._signal_group_by_movement = movement_to_group
        self._controlled_groups_by_node = {
            node_id: frozenset(groups)
            for node_id, groups in groups_by_node.items()
        }
        self._topology_binding_payload = tuple(
            sorted(
                (
                    movement_id,
                    controller.controller_id,
                    controller.node_id,
                    movement_to_group[movement_id],
                )
                for movement_id, controller in self._controller_by_movement.items()
            )
        )
        self._topology_binding_hash = _canonical_hash(self._topology_binding_payload)

    @property
    def configuration_hash(self) -> str:
        return _canonical_hash(
            {
                "plan_configuration_hash": self.plan.configuration_hash,
                "execution_config_hash": self.config.config_hash,
                "topology_binding_hash": self._topology_binding_hash,
            }
        )

    def assert_compatible_nodes(self, nodes: Iterable[Node]) -> None:
        rebound = FixedTimeSignalPlanEvaluator(self.plan, tuple(nodes), self.config)
        if rebound._topology_binding_payload != self._topology_binding_payload:
            raise FixedTimePlanValidationError(
                "signal provider topology binding does not match loading topology"
            )

    @staticmethod
    def _validate_tick(tick: int) -> None:
        _require_int(tick, "loading tick")
        if tick < 0:
            raise FixedTimePlanValidationError("loading tick must be non-negative")

    def _active_stage(
        self,
        controller: FixedTimeControllerPlan,
        tick: int,
    ) -> tuple[FixedTimeStage, int, int, int]:
        self._validate_tick(tick)
        cycle_position = (tick - controller.offset_ticks) % controller.cycle_ticks
        start = 0
        for stage in controller.stages:
            end = start + stage.duration_ticks
            if start <= cycle_position < end:
                return stage, cycle_position, start, end
            start = end
        raise RuntimeError("validated fixed-time cycle has no active stage")

    def active_stage(
        self,
        controller_id: str,
        tick: int,
    ) -> tuple[FixedTimeStage, int, int, int]:
        controller = self._controller_by_id.get(controller_id)
        if controller is None:
            raise KeyError(f"unknown fixed-time controller_id: {controller_id}")
        return self._active_stage(controller, tick)

    def evaluate(
        self,
        movement_id: str,
        tick: int,
    ) -> FixedTimeSignalBaselineState | None:
        self._validate_tick(tick)
        controller = self._controller_by_movement.get(movement_id)
        if controller is None:
            return None
        stage, cycle_position, start, end = self._active_stage(controller, tick)
        return FixedTimeSignalBaselineState(
            tick=tick,
            controller_id=controller.controller_id,
            stage_id=stage.stage_id,
            stage_start_cycle_position=start,
            stage_end_cycle_position=end,
            cycle_position=cycle_position,
            movement_id=movement_id,
            signal_group_id=self._signal_group_by_movement[movement_id],
            baseline_is_open=movement_id in stage.permitted_movement_ids,
            plan_hash=self.plan.configuration_hash,
            plan_configuration_hash=self.configuration_hash,
        )

    def controlled_signal_group_ids(self, node_id: str) -> frozenset[str]:
        return self._controlled_groups_by_node.get(node_id, frozenset())

    def controlled_movement_ids(self, node_id: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                movement_id
                for movement_id, controller in self._controller_by_movement.items()
                if controller.node_id == node_id
            )
        )

    @property
    def controller_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._controller_by_id))

    @property
    def signal_group_ids(self) -> tuple[str, ...]:
        return tuple(sorted(set(self._signal_group_by_movement.values())))


class FixedTimeSignalControlMixin:
    """Composable loading shell that injects plan state into the frozen gate."""

    fixed_time_signal_provider: FixedTimeSignalControlProvider

    def __init__(
        self,
        *args: object,
        fixed_time_signal_provider: FixedTimeSignalControlProvider,
        fixed_time_signal_override_store: SignalOverrideStore | None = None,
        **kwargs: object,
    ) -> None:
        self.fixed_time_signal_provider = fixed_time_signal_provider
        self.fixed_time_signal_override_store = (
            fixed_time_signal_override_store
            or SignalOverrideStore(
                controller_ids=fixed_time_signal_provider.controller_ids,
                signal_group_ids=fixed_time_signal_provider.signal_group_ids,
            )
        )
        self._fixed_time_signal_evidence: list[FixedTimeSignalGateEvidence] = []
        super().__init__(*args, **kwargs)  # type: ignore[misc]
        allocator = self.movement_allocator  # type: ignore[attr-defined]
        if not hasattr(allocator, "allocate"):
            raise ValueError(
                "fixed-time signals require a movement allocator that consumes "
                "JunctionAllocationInput signal gates"
            )
        self.fixed_time_signal_provider.assert_compatible_nodes(
            self.nodes.values()  # type: ignore[attr-defined]
        )
        if (
            self.fixed_time_signal_override_store.controller_ids
            != self.fixed_time_signal_provider.controller_ids
            or self.fixed_time_signal_override_store.signal_group_ids
            != self.fixed_time_signal_provider.signal_group_ids
        ):
            raise ValueError(
                "override-store targets must exactly match the fixed-time provider"
            )

    @property
    def fixed_time_signal_evidence(self) -> tuple[FixedTimeSignalGateEvidence, ...]:
        return tuple(self._fixed_time_signal_evidence)

    @property
    def fixed_time_signal_evidence_hash(self) -> str:
        return _canonical_hash(
            {
                "provider_configuration_hash": (
                    self.fixed_time_signal_provider.configuration_hash
                ),
                "override_store_hash": (
                    self.fixed_time_signal_override_store.store_hash
                ),
                "evaluations": [
                    asdict(item) for item in self._fixed_time_signal_evidence
                ],
            }
        )

    @property
    def signal_override_receipts(self) -> tuple[SignalOverrideReceipt, ...]:
        return self.fixed_time_signal_override_store.history

    def submit_signal_override(
        self,
        command: SignalOverrideCommand,
    ) -> SignalOverrideReceipt:
        """Append a replayable override receipt without moving any packet."""

        return self.fixed_time_signal_override_store.submit(
            command,
            recorded_tick=self.current_tick,  # type: ignore[attr-defined]
        )

    def baseline_signal_gate_state(
        self,
        movement_id: str,
        tick: int | None = None,
    ) -> FixedTimeSignalBaselineState | None:
        """Query the immutable programme without applying runtime overrides."""

        return self.fixed_time_signal_provider.evaluate(
            movement_id,
            self.current_tick if tick is None else tick,  # type: ignore[attr-defined]
        )

    def signal_gate_state(
        self,
        movement_id: str,
        tick: int | None = None,
    ) -> FixedTimeSignalGateEvidence | None:
        """Query effective state without appending request-linked evidence."""

        return self._effective_gate_state(
            movement_id,
            self.current_tick if tick is None else tick,  # type: ignore[attr-defined]
        )

    def _effective_gate_state(
        self,
        movement_id: str,
        tick: int,
    ) -> FixedTimeSignalGateEvidence | None:
        baseline = self.fixed_time_signal_provider.evaluate(movement_id, tick)
        if baseline is None:
            return None
        resolution: SignalOverrideResolution = (
            self.fixed_time_signal_override_store.resolve(
                controller_id=baseline.controller_id,
                signal_group_id=baseline.signal_group_id,
                tick=tick,
                baseline_is_open=baseline.baseline_is_open,
            )
        )
        return FixedTimeSignalGateEvidence(
            tick=baseline.tick,
            controller_id=baseline.controller_id,
            stage_id=baseline.stage_id,
            stage_start_cycle_position=baseline.stage_start_cycle_position,
            stage_end_cycle_position=baseline.stage_end_cycle_position,
            cycle_position=baseline.cycle_position,
            movement_id=baseline.movement_id,
            signal_group_id=baseline.signal_group_id,
            baseline_is_open=baseline.baseline_is_open,
            considered_override_ids=resolution.considered_override_ids,
            cleared_override_ids=resolution.cleared_override_ids,
            selected_override_id=resolution.selected_override_id,
            selected_override_action=resolution.selected_override_action,
            selected_override_target_kind=resolution.selected_target_kind,
            effective_is_open=resolution.effective_is_open,
            plan_hash=baseline.plan_hash,
            plan_configuration_hash=baseline.plan_configuration_hash,
            override_store_config_hash=resolution.override_store_config_hash,
            override_store_hash=resolution.override_store_hash,
        )

    def set_signal_group_open(self, signal_group_id: str, is_open: bool) -> None:
        """Retain legacy gates only for groups outside fixed-time ownership."""

        if signal_group_id in self.fixed_time_signal_provider.signal_group_ids:
            raise ValueError(
                "plan-controlled signal groups require submit_signal_override; "
                "ad hoc set_signal_group_open is not an audited override"
            )
        super().set_signal_group_open(signal_group_id, is_open)  # type: ignore[misc]

    def _junction_allocation_inputs(
        self,
        *,
        transfer_requests,
        receiving_slots_by_downstream_link,
        packet_ids_by_upstream_link,
        queued_downstream_by_packet_id,
    ) -> tuple[JunctionAllocationInput, ...]:
        allocation_inputs = super()._junction_allocation_inputs(  # type: ignore[misc]
            transfer_requests=transfer_requests,
            receiving_slots_by_downstream_link=receiving_slots_by_downstream_link,
            packet_ids_by_upstream_link=packet_ids_by_upstream_link,
            queued_downstream_by_packet_id=queued_downstream_by_packet_id,
        )
        effective_inputs: list[JunctionAllocationInput] = []
        for allocation_input in allocation_inputs:
            controlled_groups = (
                self.fixed_time_signal_provider.controlled_signal_group_ids(
                    allocation_input.node_id
                )
            )
            effective_by_movement = {
                movement_id: self._effective_gate_state(
                    movement_id,
                    self.current_tick,  # type: ignore[attr-defined]
                )
                for movement_id in (
                    self.fixed_time_signal_provider.controlled_movement_ids(
                        allocation_input.node_id
                    )
                )
            }
            fixed_open_groups = frozenset(
                evidence.signal_group_id
                for evidence in effective_by_movement.values()
                if evidence is not None and evidence.effective_is_open
            )
            effective_open_groups = (
                allocation_input.open_signal_group_ids - controlled_groups
            ) | fixed_open_groups
            effective_inputs.append(
                replace(
                    allocation_input,
                    open_signal_group_ids=frozenset(effective_open_groups),
                )
            )
            movement_requests: dict[str, list[str]] = {}
            for request in allocation_input.transfer_requests:
                movement_requests.setdefault(request.movement_id, []).append(
                    request.packet_id
                )
            for movement_id, packet_ids in movement_requests.items():
                evidence = effective_by_movement.get(movement_id)
                if evidence is not None:
                    self._fixed_time_signal_evidence.append(
                        replace(
                            evidence,
                            request_packet_ids=tuple(packet_ids),
                        )
                    )
        return tuple(effective_inputs)


class FixedTimeSignalLoadingEngine(FixedTimeSignalControlMixin, LoadingEngine):
    """Standard loader shell with opt-in deterministic fixed-time control."""

    def __init__(
        self,
        *,
        links,
        nodes: tuple[Node, ...],
        fixed_time_signal_provider: FixedTimeSignalControlProvider,
        fixed_time_signal_override_store: SignalOverrideStore | None = None,
        node_transfer_policy=None,
        **engine_kwargs,
    ) -> None:
        allocator = node_transfer_policy or GeneralMovementAllocator(nodes)
        super().__init__(
            links=links,
            nodes=nodes,
            node_transfer_policy=allocator,
            fixed_time_signal_provider=fixed_time_signal_provider,
            fixed_time_signal_override_store=fixed_time_signal_override_store,
            **engine_kwargs,
        )
