"""Immutable junction and movement records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self


JUNCTION_FIFO_STRICT = "strict"
JUNCTION_FIFO_PARTIAL_BY_MOVEMENT = "partial_by_movement"
SUPPORTED_JUNCTION_FIFO_POLICIES = frozenset(
    (JUNCTION_FIFO_STRICT, JUNCTION_FIFO_PARTIAL_BY_MOVEMENT)
)

# Legacy comparison labels. MovementSpec/JunctionSpec are the architecture.
PARITY_NODE_MODEL_AUTO = "auto"
PARITY_NODE_MODEL_LEGACY_GLOBAL_FIFO = "legacy_global_fifo"
REMOVED_SPECIALISED_NODE_MODEL_IDS = frozenset(
    ("one_to_one", "strict_route_diverge", "priority_merge")
)
SUPPORTED_NODE_MODEL_IDS = frozenset(
    (
        PARITY_NODE_MODEL_AUTO,
        PARITY_NODE_MODEL_LEGACY_GLOBAL_FIFO,
    )
)


def movement_id(upstream_link_id: str, downstream_link_id: str) -> str:
    """Return the canonical movement identifier for one link-to-link movement."""

    _require_non_empty_string(upstream_link_id, "movement upstream_link_id")
    _require_non_empty_string(downstream_link_id, "movement downstream_link_id")
    return f"movement:{upstream_link_id}->{downstream_link_id}"


@dataclass(frozen=True, slots=True)
class MovementSpec:
    """Static admissible movement through a junction."""

    upstream_link_id: str
    downstream_link_id: str
    movement_id: str = ""
    priority_weight: int = 1
    lane_group_ids: tuple[str, ...] = ()
    conflict_resource_ids: tuple[str, ...] = ()
    signal_group_id: str | None = None
    provenance: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty_string(self.upstream_link_id, "movement upstream_link_id")
        _require_non_empty_string(self.downstream_link_id, "movement downstream_link_id")
        if not self.movement_id:
            object.__setattr__(
                self,
                "movement_id",
                movement_id(self.upstream_link_id, self.downstream_link_id),
            )
        else:
            _require_non_empty_string(self.movement_id, "movement_id")
        _validate_positive_int(self.priority_weight, "movement priority_weight")
        object.__setattr__(
            self,
            "lane_group_ids",
            _normalise_string_tuple(self.lane_group_ids, "lane_group_ids"),
        )
        object.__setattr__(
            self,
            "conflict_resource_ids",
            _normalise_string_tuple(
                self.conflict_resource_ids,
                "conflict_resource_ids",
            ),
        )
        if self.signal_group_id is not None:
            _require_non_empty_string(self.signal_group_id, "signal_group_id")
        object.__setattr__(
            self,
            "provenance",
            _normalise_metadata_tuple(self.provenance, "movement provenance"),
        )


@dataclass(frozen=True, slots=True)
class JunctionSpec:
    """Declarative static movement model for one topology node."""

    node_id: str
    incoming_link_ids: tuple[str, ...]
    outgoing_link_ids: tuple[str, ...]
    movement_specs: tuple[MovementSpec, ...] = ()
    lane_group_ids: tuple[str, ...] = ()
    movement_lane_group_mappings: tuple[tuple[str, tuple[str, ...]], ...] = ()
    lane_group_capacities: tuple[tuple[str, int], ...] = ()
    conflict_resource_ids: tuple[str, ...] = ()
    conflict_resource_capacities: tuple[tuple[str, int], ...] = ()
    governance_refs: tuple[str, ...] = ()
    provenance: tuple[tuple[str, str], ...] = ()
    fifo_policy: str = JUNCTION_FIFO_STRICT

    def __post_init__(self) -> None:
        _require_non_empty_string(self.node_id, "node_id")
        if self.fifo_policy not in SUPPORTED_JUNCTION_FIFO_POLICIES:
            raise ValueError(f"unsupported junction fifo_policy: {self.fifo_policy}")
        object.__setattr__(
            self,
            "incoming_link_ids",
            _normalise_string_tuple(self.incoming_link_ids, "incoming_link_ids"),
        )
        object.__setattr__(
            self,
            "outgoing_link_ids",
            _normalise_string_tuple(self.outgoing_link_ids, "outgoing_link_ids"),
        )
        movement_specs = self.movement_specs or _default_movement_specs(
            self.incoming_link_ids,
            self.outgoing_link_ids,
        )
        object.__setattr__(
            self,
            "movement_specs",
            _normalise_movement_specs(
                movement_specs,
                incoming_link_ids=set(self.incoming_link_ids),
                outgoing_link_ids=set(self.outgoing_link_ids),
            ),
        )
        object.__setattr__(
            self,
            "lane_group_ids",
            _normalise_string_tuple(self.lane_group_ids, "lane_group_ids"),
        )
        object.__setattr__(
            self,
            "movement_lane_group_mappings",
            _normalise_movement_lane_group_mappings(
                self.movement_lane_group_mappings,
                movement_ids={movement.movement_id for movement in self.movement_specs},
                declared_lane_group_ids=set(self.lane_group_ids),
            ),
        )
        object.__setattr__(
            self,
            "lane_group_capacities",
            _normalise_capacity_tuple(
                self.lane_group_capacities,
                "lane_group_capacities",
                supported_ids=set(self.lane_group_ids),
            ),
        )
        object.__setattr__(
            self,
            "conflict_resource_ids",
            _normalise_string_tuple(
                self.conflict_resource_ids,
                "conflict_resource_ids",
            ),
        )
        object.__setattr__(
            self,
            "conflict_resource_capacities",
            _normalise_capacity_tuple(
                self.conflict_resource_capacities,
                "conflict_resource_capacities",
                supported_ids=set(self.conflict_resource_ids),
            ),
        )
        object.__setattr__(
            self,
            "governance_refs",
            _normalise_string_tuple(self.governance_refs, "governance_refs"),
        )
        object.__setattr__(
            self,
            "provenance",
            _normalise_metadata_tuple(self.provenance, "junction provenance"),
        )
        _validate_movement_resource_references(self.movement_specs, self)

    @classmethod
    def from_node_connectivity(
        cls,
        *,
        node_id: str,
        incoming_link_ids: tuple[str, ...],
        outgoing_link_ids: tuple[str, ...],
        priority_by_upstream_link_id: dict[str, int] | None = None,
    ) -> Self:
        """Build default Cartesian movements from immutable node connectivity."""

        priority_by_link = priority_by_upstream_link_id or {}
        return cls(
            node_id=node_id,
            incoming_link_ids=incoming_link_ids,
            outgoing_link_ids=outgoing_link_ids,
            movement_specs=tuple(
                MovementSpec(
                    upstream_link_id=incoming_link_id,
                    downstream_link_id=outgoing_link_id,
                    priority_weight=priority_by_link.get(incoming_link_id, 1),
                )
                for incoming_link_id in incoming_link_ids
                for outgoing_link_id in outgoing_link_ids
            ),
        )

    @property
    def movement_by_id(self) -> dict[str, MovementSpec]:
        """Return declared movements keyed by movement ID."""

        return {movement.movement_id: movement for movement in self.movement_specs}

    @property
    def movement_by_links(self) -> dict[tuple[str, str], MovementSpec]:
        """Return declared movements keyed by upstream and downstream link."""

        return {
            (movement.upstream_link_id, movement.downstream_link_id): movement
            for movement in self.movement_specs
        }

    @property
    def lane_group_capacity_by_id(self) -> dict[str, int]:
        """Return declared lane-group capacities, defaulting declared groups to one."""

        explicit = dict(self.lane_group_capacities)
        return {lane_group_id: explicit.get(lane_group_id, 1) for lane_group_id in self.lane_group_ids}

    @property
    def conflict_resource_capacity_by_id(self) -> dict[str, int]:
        """Return declared conflict-resource capacities, defaulting resources to one."""

        explicit = dict(self.conflict_resource_capacities)
        return {
            resource_id: explicit.get(resource_id, 1)
            for resource_id in self.conflict_resource_ids
        }

    @property
    def lane_group_ids_by_movement_id(self) -> dict[str, tuple[str, ...]]:
        """Return lane groups used by each movement."""

        mapped = dict(self.movement_lane_group_mappings)
        return {
            movement.movement_id: tuple(
                dict.fromkeys(
                    (
                        *mapped.get(movement.movement_id, ()),
                        *movement.lane_group_ids,
                    )
                )
            )
            for movement in self.movement_specs
        }


@dataclass(frozen=True, slots=True)
class Node:
    """Immutable junction identity and directed connectivity."""

    node_id: str
    incoming_link_ids: tuple[str, ...]
    outgoing_link_ids: tuple[str, ...]
    node_model: str = PARITY_NODE_MODEL_AUTO
    merge_priorities: tuple[tuple[str, int], ...] = ()
    junction_spec: JunctionSpec | None = None

    def __post_init__(self) -> None:
        _require_non_empty_string(self.node_id, "node_id")
        object.__setattr__(
            self,
            "incoming_link_ids",
            _normalise_string_tuple(self.incoming_link_ids, "incoming_link_ids"),
        )
        object.__setattr__(
            self,
            "outgoing_link_ids",
            _normalise_string_tuple(self.outgoing_link_ids, "outgoing_link_ids"),
        )
        if self.node_model not in SUPPORTED_NODE_MODEL_IDS:
            if self.node_model in REMOVED_SPECIALISED_NODE_MODEL_IDS:
                raise ValueError(
                    "specialised node_model labels were removed; use junction_spec "
                    f"movement specifications for {self.node_id}"
                )
            raise ValueError(f"unsupported node_model for {self.node_id}: {self.node_model}")
        if self.junction_spec is not None:
            if self.node_model != PARITY_NODE_MODEL_AUTO:
                raise ValueError(
                    "legacy node_model labels cannot be combined with junction_spec"
                )
            if self.merge_priorities:
                raise ValueError(
                    "legacy merge_priorities cannot be combined with junction_spec"
                )
        _validate_merge_priorities(self.merge_priorities)
        priority_by_link = dict(self.merge_priorities)
        junction_spec = self.junction_spec or JunctionSpec.from_node_connectivity(
            node_id=self.node_id,
            incoming_link_ids=self.incoming_link_ids,
            outgoing_link_ids=self.outgoing_link_ids,
            priority_by_upstream_link_id=priority_by_link,
        )
        if junction_spec.node_id != self.node_id:
            raise ValueError("junction_spec node_id must match node_id")
        if junction_spec.incoming_link_ids != self.incoming_link_ids:
            raise ValueError("junction_spec incoming links must match node connectivity")
        if junction_spec.outgoing_link_ids != self.outgoing_link_ids:
            raise ValueError("junction_spec outgoing links must match node connectivity")
        object.__setattr__(self, "junction_spec", junction_spec)


def _validate_merge_priorities(
    merge_priorities: tuple[tuple[str, int], ...],
) -> None:
    if not isinstance(merge_priorities, tuple):
        raise TypeError("merge_priorities must be a tuple")
    seen_link_ids: set[str] = set()
    for link_id, weight in merge_priorities:
        _require_non_empty_string(link_id, "merge priority link_id")
        if link_id in seen_link_ids:
            raise ValueError(f"duplicate merge priority for {link_id}")
        seen_link_ids.add(link_id)
        if not isinstance(weight, int):
            raise TypeError("merge priority weight must be an int")
        if weight <= 0:
            raise ValueError("merge priority weight must be positive")


def _default_movement_specs(
    incoming_link_ids: tuple[str, ...],
    outgoing_link_ids: tuple[str, ...],
) -> tuple[MovementSpec, ...]:
    return tuple(
        MovementSpec(
            upstream_link_id=incoming_link_id,
            downstream_link_id=outgoing_link_id,
        )
        for incoming_link_id in incoming_link_ids
        for outgoing_link_id in outgoing_link_ids
    )


def _normalise_movement_specs(
    movement_specs: tuple[MovementSpec, ...],
    *,
    incoming_link_ids: set[str],
    outgoing_link_ids: set[str],
) -> tuple[MovementSpec, ...]:
    if not isinstance(movement_specs, tuple):
        raise TypeError("movement_specs must be a tuple")
    seen_movement_ids: set[str] = set()
    seen_link_pairs: set[tuple[str, str]] = set()
    for movement in movement_specs:
        if not isinstance(movement, MovementSpec):
            raise TypeError("movement_specs must contain MovementSpec records")
        if movement.upstream_link_id not in incoming_link_ids:
            raise ValueError(
                f"movement {movement.movement_id} references unknown incoming link"
            )
        if movement.downstream_link_id not in outgoing_link_ids:
            raise ValueError(
                f"movement {movement.movement_id} references unknown outgoing link"
            )
        if movement.movement_id in seen_movement_ids:
            raise ValueError(f"duplicate movement_id: {movement.movement_id}")
        seen_movement_ids.add(movement.movement_id)
        link_pair = (movement.upstream_link_id, movement.downstream_link_id)
        if link_pair in seen_link_pairs:
            raise ValueError(
                "duplicate movement link pair: "
                f"{movement.upstream_link_id}->{movement.downstream_link_id}"
            )
        seen_link_pairs.add(link_pair)
    return movement_specs


def _normalise_movement_lane_group_mappings(
    mappings: tuple[tuple[str, tuple[str, ...]], ...],
    *,
    movement_ids: set[str],
    declared_lane_group_ids: set[str],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if not isinstance(mappings, tuple):
        raise TypeError("movement_lane_group_mappings must be a tuple")
    normalised: list[tuple[str, tuple[str, ...]]] = []
    seen_movement_ids: set[str] = set()
    for movement_id_value, mapped_lane_group_ids in mappings:
        _require_non_empty_string(movement_id_value, "movement lane-group movement_id")
        if movement_id_value not in movement_ids:
            raise ValueError(
                f"lane-group mapping references unknown movement_id: {movement_id_value}"
            )
        if movement_id_value in seen_movement_ids:
            raise ValueError(
                f"duplicate lane-group mapping for movement_id: {movement_id_value}"
            )
        seen_movement_ids.add(movement_id_value)
        normalised_lane_group_ids = _normalise_string_tuple(
            mapped_lane_group_ids,
            "mapping lane_group_ids",
        )
        for lane_group_id in normalised_lane_group_ids:
            if lane_group_id not in declared_lane_group_ids:
                raise ValueError(
                    f"lane-group mapping references unknown lane_group_id: {lane_group_id}"
                )
        normalised.append(
            (
                movement_id_value,
                normalised_lane_group_ids,
            )
        )
    return tuple(normalised)


def _normalise_capacity_tuple(
    values: tuple[tuple[str, int], ...],
    field_name: str,
    *,
    supported_ids: set[str],
) -> tuple[tuple[str, int], ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    seen_ids: set[str] = set()
    normalised: list[tuple[str, int]] = []
    for resource_id, capacity in values:
        _require_non_empty_string(resource_id, f"{field_name} resource_id")
        if resource_id not in supported_ids:
            raise ValueError(f"{field_name} references unknown id: {resource_id}")
        if resource_id in seen_ids:
            raise ValueError(f"{field_name} contains duplicate id: {resource_id}")
        seen_ids.add(resource_id)
        _validate_positive_int(capacity, f"{field_name} capacity")
        normalised.append((resource_id, capacity))
    return tuple(normalised)


def _validate_movement_resource_references(
    movement_specs: tuple[MovementSpec, ...],
    junction_spec: JunctionSpec,
) -> None:
    lane_group_ids = set(junction_spec.lane_group_ids)
    conflict_resource_ids = set(junction_spec.conflict_resource_ids)
    for movement in movement_specs:
        for lane_group_id in movement.lane_group_ids:
            if lane_group_id not in lane_group_ids:
                raise ValueError(
                    f"movement {movement.movement_id} references unknown lane_group_id: "
                    f"{lane_group_id}"
                )
        for resource_id in movement.conflict_resource_ids:
            if resource_id not in conflict_resource_ids:
                raise ValueError(
                    f"movement {movement.movement_id} references unknown "
                    f"conflict_resource_id: {resource_id}"
                )


def _normalise_metadata_tuple(
    values: tuple[tuple[str, str], ...],
    field_name: str,
) -> tuple[tuple[str, str], ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    normalised: list[tuple[str, str]] = []
    for key, value in values:
        _require_non_empty_string(key, f"{field_name} key")
        if not isinstance(value, str):
            raise TypeError(f"{field_name} values must be strings")
        normalised.append((key, value))
    return tuple(normalised)


def _normalise_string_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    seen_values: set[str] = set()
    for value in values:
        _require_non_empty_string(value, field_name)
        if value in seen_values:
            raise ValueError(f"{field_name} must not contain duplicates: {value}")
        seen_values.add(value)
    return values


def _validate_positive_int(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_non_empty_string(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value:
        raise ValueError(f"{field_name} must be non-empty")
