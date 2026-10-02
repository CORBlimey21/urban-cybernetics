# SPDX-License-Identifier: MPL-2.0
"""Versioned executable-routing artifacts and deterministic history resolution."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from types import MappingProxyType


ROUTING_INSTRUCTION_SCHEMA_VERSION = "uc.routing-instruction.v1"
ROUTING_DECISION_ARTIFACT_SCHEMA_VERSION = "uc.routing-decision-artifact.v1"
INSTRUCTION_HISTORY_SCHEMA_VERSION = "uc.routing-instruction-history.v1"

ACCEPTED = "accepted"
REJECTED_DUPLICATE_INSTRUCTION_ID = "duplicate_instruction_id"
REJECTED_DUPLICATE_VERSION = "duplicate_packet_version"
REJECTED_STALE_VERSION = "stale_packet_version"
REJECTED_TERMINAL_PACKET = "terminal_packet"

APPLICABLE = "applicable"
INAPPLICABLE_NO_INSTRUCTION = "no_applicable_instruction"
INAPPLICABLE_CURRENT_LINK_MISMATCH = "current_link_mismatch"
INAPPLICABLE_REALISED_PREFIX_MISMATCH = "realised_prefix_mismatch"
INAPPLICABLE_UNKNOWN_LINK = "unknown_route_link"
INAPPLICABLE_DISCONNECTED_ROUTE = "disconnected_remaining_route"
INAPPLICABLE_TERMINAL_PACKET = "terminal_packet"

SELECTION_EXPLICIT_INSTRUCTION = "explicit_instruction"
SELECTION_ROUTE_INTENT_ADAPTER = "route_intent_adapter"
CONSIDERATION_SELECTED = "selected"
CONSIDERATION_INAPPLICABLE = "inapplicable"


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be non-empty")


def _require_tick(value: int, field_name: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _normalise_metadata(
    metadata: Iterable[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    result = tuple((str(key), str(value)) for key, value in metadata)
    if any(not key for key, _ in result):
        raise ValueError("provenance keys must be non-empty")
    if len({key for key, _ in result}) != len(result):
        raise ValueError("provenance keys must be unique")
    return tuple(sorted(result))


@dataclass(frozen=True, slots=True)
class RoutingDecisionArtifact:
    """Authority-produced proposal from which an instruction is issued."""

    artifact_id: str
    authority_id: str
    packet_id: str
    decision_tick: int
    proposed_remaining_route: tuple[str, ...]
    route_start_ordinal: int
    policy_id: str
    provenance: tuple[tuple[str, str], ...]
    source_decision_id: str | None = None
    schema_version: str = ROUTING_DECISION_ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(self.artifact_id, "artifact_id")
        _require_non_empty(self.authority_id, "authority_id")
        _require_non_empty(self.packet_id, "packet_id")
        _require_tick(self.decision_tick, "decision_tick")
        _require_tick(self.route_start_ordinal, "route_start_ordinal")
        _require_non_empty(self.policy_id, "policy_id")
        route = tuple(self.proposed_remaining_route)
        if not route or any(not link_id for link_id in route):
            raise ValueError("proposed_remaining_route must contain link IDs")
        object.__setattr__(self, "proposed_remaining_route", route)
        provenance = _normalise_metadata(self.provenance)
        if not provenance:
            raise ValueError("routing decision provenance must be non-empty")
        object.__setattr__(self, "provenance", provenance)
        if self.source_decision_id is not None:
            _require_non_empty(self.source_decision_id, "source_decision_id")
        if self.schema_version != ROUTING_DECISION_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported routing decision artifact schema: {self.schema_version}"
            )


@dataclass(frozen=True, slots=True)
class RoutingInstruction:
    """Immutable, versioned executable instruction for one packet."""

    instruction_id: str
    packet_id: str
    version: int
    authority_id: str
    decision_artifact_id: str
    issue_tick: int
    effective_tick: int
    remaining_route: tuple[str, ...]
    policy_id: str
    provenance: tuple[tuple[str, str], ...]
    route_start_ordinal: int = 0
    schema_version: str = ROUTING_INSTRUCTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(self.instruction_id, "instruction_id")
        _require_non_empty(self.packet_id, "packet_id")
        _require_tick(self.version, "version")
        _require_non_empty(self.authority_id, "authority_id")
        _require_non_empty(self.decision_artifact_id, "decision_artifact_id")
        _require_tick(self.issue_tick, "issue_tick")
        _require_tick(self.effective_tick, "effective_tick")
        _require_non_empty(self.policy_id, "policy_id")
        _require_tick(self.route_start_ordinal, "route_start_ordinal")
        route = tuple(self.remaining_route)
        if not route or any(not link_id for link_id in route):
            raise ValueError("remaining_route must contain link IDs")
        object.__setattr__(self, "remaining_route", route)
        provenance = _normalise_metadata(self.provenance)
        if not provenance:
            raise ValueError("routing instruction provenance must be non-empty")
        object.__setattr__(self, "provenance", provenance)
        if self.schema_version != ROUTING_INSTRUCTION_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported routing instruction schema: {self.schema_version}"
            )

    @property
    def availability_tick(self) -> int:
        """Earliest tick at which issue and effectiveness constraints both hold."""

        return max(self.issue_tick, self.effective_tick)

    @property
    def instruction_hash(self) -> str:
        """Canonical hash of the complete submitted instruction payload."""

        serialised = json.dumps(
            self.to_payload(), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(serialised.encode("utf-8")).hexdigest()

    def to_payload(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "RoutingInstruction":
        values = dict(payload)
        values["remaining_route"] = tuple(values["remaining_route"])
        values["provenance"] = tuple(
            tuple(item) for item in values["provenance"]
        )
        return cls(**values)


@dataclass(frozen=True, slots=True)
class InstructionHistoryRecord:
    """Append-only receipt or rejection record in instruction-history order."""

    history_sequence: int
    record_id: str
    instruction: RoutingInstruction
    instruction_hash: str
    recorded_tick: int
    disposition: str
    reason: str
    participates_in_resolution: bool

    def __post_init__(self) -> None:
        _require_non_empty(self.record_id, "record_id")
        if self.instruction_hash != self.instruction.instruction_hash:
            raise ValueError("instruction history payload hash mismatch")
        if self.participates_in_resolution != (self.disposition == ACCEPTED):
            raise ValueError(
                "only accepted instruction receipts may participate in resolution"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "history_sequence": self.history_sequence,
            "record_id": self.record_id,
            "instruction": self.instruction.to_payload(),
            "instruction_hash": self.instruction_hash,
            "recorded_tick": self.recorded_tick,
            "disposition": self.disposition,
            "reason": self.reason,
            "participates_in_resolution": self.participates_in_resolution,
        }


@dataclass(frozen=True, slots=True)
class InstructionConsideration:
    """One eligible instruction examined in descending version order."""

    instruction_id: str
    instruction_version: int
    decision_artifact_id: str
    authority_id: str
    outcome: str
    reason: str


@dataclass(frozen=True, slots=True)
class InstructionResolution:
    """Deterministic result at one explicit physical decision boundary."""

    resolution_id: str
    packet_id: str
    decision_tick: int
    current_link_id: str
    realised_route: tuple[str, ...]
    status: str
    reason: str
    instruction_id: str | None
    decision_artifact_id: str | None
    instruction_version: int | None
    remaining_route: tuple[str, ...]
    intended_next_link_id: str | None
    superseded_instruction_ids: tuple[str, ...]
    rejected_instruction_ids: tuple[str, ...]
    rejected_record_ids: tuple[str, ...]
    matches_original_route_intent: bool | None
    selection_source: str | None
    considered_instructions: tuple[InstructionConsideration, ...]
    skipped_instruction_reasons: tuple[tuple[str, str], ...]

    @property
    def is_applicable(self) -> bool:
        return self.status == APPLICABLE


class RoutingInstructionStore:
    """Append-only deterministic store for accepted and rejected instructions."""

    def __init__(self) -> None:
        self._history: list[InstructionHistoryRecord] = []
        self._instruction_ids: set[str] = set()
        self._accepted_by_packet_and_version: dict[
            tuple[str, int], RoutingInstruction
        ] = {}
        self._highest_accepted_version_by_packet: dict[str, int] = {}

    @property
    def history(self) -> tuple[InstructionHistoryRecord, ...]:
        return tuple(self._history)

    @property
    def accepted_instructions(self) -> tuple[RoutingInstruction, ...]:
        return tuple(
            record.instruction
            for record in self._history
            if record.disposition == ACCEPTED
        )

    def record(
        self,
        instruction: RoutingInstruction,
        *,
        recorded_tick: int,
        rejection_reason: str | None = None,
    ) -> InstructionHistoryRecord:
        """Append one receipt deterministically; never silently discard it."""

        _require_tick(recorded_tick, "recorded_tick")
        if recorded_tick < instruction.issue_tick:
            raise ValueError("recorded_tick cannot precede instruction issue_tick")

        disposition = ACCEPTED
        reason = ACCEPTED
        packet_version = (instruction.packet_id, instruction.version)
        if rejection_reason is not None:
            disposition = "rejected"
            reason = rejection_reason
        elif instruction.instruction_id in self._instruction_ids:
            disposition = "rejected"
            reason = REJECTED_DUPLICATE_INSTRUCTION_ID
        elif packet_version in self._accepted_by_packet_and_version:
            disposition = "rejected"
            reason = REJECTED_DUPLICATE_VERSION
        elif instruction.version < self._highest_accepted_version_by_packet.get(
            instruction.packet_id, -1
        ):
            disposition = "rejected"
            reason = REJECTED_STALE_VERSION

        history_sequence = len(self._history)
        instruction_hash = instruction.instruction_hash
        record = InstructionHistoryRecord(
            history_sequence=history_sequence,
            record_id=(
                f"instruction-receipt:{history_sequence}:"
                f"{instruction_hash[:16]}"
            ),
            instruction=instruction,
            instruction_hash=instruction_hash,
            recorded_tick=recorded_tick,
            disposition=disposition,
            reason=reason,
            participates_in_resolution=(disposition == ACCEPTED),
        )
        self._history.append(record)
        self._instruction_ids.add(instruction.instruction_id)
        if disposition == ACCEPTED:
            self._accepted_by_packet_and_version[packet_version] = instruction
            self._highest_accepted_version_by_packet[instruction.packet_id] = max(
                instruction.version,
                self._highest_accepted_version_by_packet.get(
                    instruction.packet_id, -1
                ),
            )
        return record

    def records_for_packet(
        self,
        packet_id: str,
        *,
        through_tick: int | None = None,
    ) -> tuple[InstructionHistoryRecord, ...]:
        return tuple(
            record
            for record in self._history
            if record.instruction.packet_id == packet_id
            and (through_tick is None or record.recorded_tick <= through_tick)
        )

    @property
    def history_hash(self) -> str:
        """Stable hash of the complete accepted/rejected receipt history."""

        payload = self.to_payload()
        serialised = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialised.encode("utf-8")).hexdigest()

    def to_payload(self) -> dict[str, object]:
        """Return a canonical JSON-like append-only history snapshot."""

        return {
            "schema_version": INSTRUCTION_HISTORY_SCHEMA_VERSION,
            "records": [record.to_payload() for record in self._history],
        }

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, object],
    ) -> "RoutingInstructionStore":
        """Reconstruct history while preserving rejection non-participation."""

        if payload.get("schema_version") != INSTRUCTION_HISTORY_SCHEMA_VERSION:
            raise ValueError("unsupported instruction-history snapshot schema")
        store = cls()
        raw_records = payload.get("records")
        if not isinstance(raw_records, list):
            raise TypeError("instruction-history records must be a list")
        for expected_sequence, raw_record in enumerate(raw_records):
            if not isinstance(raw_record, Mapping):
                raise TypeError("instruction-history record must be a mapping")
            instruction_payload = raw_record.get("instruction")
            if not isinstance(instruction_payload, Mapping):
                raise TypeError("instruction-history instruction must be a mapping")
            instruction = RoutingInstruction.from_payload(instruction_payload)
            disposition = raw_record.get("disposition")
            reason = raw_record.get("reason")
            rejection_reason = (
                str(reason)
                if disposition != ACCEPTED and reason == REJECTED_TERMINAL_PACKET
                else None
            )
            reconstructed = store.record(
                instruction,
                recorded_tick=int(raw_record["recorded_tick"]),
                rejection_reason=rejection_reason,
            )
            expected_record = InstructionHistoryRecord(
                history_sequence=int(raw_record["history_sequence"]),
                record_id=str(raw_record["record_id"]),
                instruction=instruction,
                instruction_hash=str(raw_record["instruction_hash"]),
                recorded_tick=int(raw_record["recorded_tick"]),
                disposition=str(disposition),
                reason=str(reason),
                participates_in_resolution=bool(
                    raw_record["participates_in_resolution"]
                ),
            )
            if expected_sequence != expected_record.history_sequence:
                raise ValueError("instruction-history sequence is not contiguous")
            if reconstructed != expected_record:
                raise ValueError(
                    "instruction-history snapshot does not replay deterministically"
                )
        return store


class ApplicableInstructionResolver:
    """Resolve the latest valid packet-global version with explicit fallback."""

    def __init__(
        self,
        *,
        link_ids: Iterable[str],
        supported_transitions: Iterable[tuple[str, str]],
    ) -> None:
        self._link_ids = frozenset(link_ids)
        self._supported_transitions = frozenset(supported_transitions)

    def resolve(
        self,
        *,
        store: RoutingInstructionStore,
        packet_id: str,
        decision_tick: int,
        current_link_id: str,
        realised_route: tuple[str, ...],
        original_route_intent: tuple[str, ...],
        terminal: bool = False,
        allow_route_intent_adapter: bool = True,
    ) -> InstructionResolution:
        _require_tick(decision_tick, "decision_tick")
        records = store.records_for_packet(packet_id, through_tick=decision_tick)
        rejected_records = tuple(
            record for record in records if record.disposition != ACCEPTED
        )
        rejected_ids = tuple(
            record.instruction.instruction_id for record in rejected_records
        )
        rejected_record_ids = tuple(record.record_id for record in rejected_records)
        eligible = tuple(
            record.instruction
            for record in records
            if record.participates_in_resolution
            and record.instruction.issue_tick <= decision_tick
            and record.instruction.effective_tick <= decision_tick
        )
        resolution_id = (
            f"resolution:{packet_id}:{decision_tick}:{current_link_id}:"
            f"{len(realised_route)}"
        )

        if terminal:
            return self._inapplicable(
                resolution_id, packet_id, decision_tick, current_link_id,
                realised_route, INAPPLICABLE_TERMINAL_PACKET, None,
                (), rejected_ids, rejected_record_ids, (), (),
            )
        if not realised_route or realised_route[-1] != current_link_id:
            return self._inapplicable(
                resolution_id,
                packet_id,
                decision_tick,
                current_link_id,
                realised_route,
                INAPPLICABLE_CURRENT_LINK_MISMATCH,
                None,
                (),
                rejected_ids,
                rejected_record_ids,
                (),
                (),
            )

        ordered = tuple(sorted(eligible, key=lambda item: item.version, reverse=True))
        explicit = tuple(
            instruction
            for instruction in ordered
            if not _is_route_intent_adapter(instruction)
        )
        adapters = tuple(
            instruction
            for instruction in ordered
            if _is_route_intent_adapter(instruction)
        )
        considerations: list[InstructionConsideration] = []
        skipped: list[tuple[str, str]] = []
        selected: RoutingInstruction | None = None
        executable_remaining_route: tuple[str, ...] = ()
        selection_source: str | None = None

        for instruction in explicit:
            reason, remaining = self._validate_instruction(
                instruction=instruction,
                realised_route=realised_route,
            )
            if reason == APPLICABLE:
                selected = instruction
                executable_remaining_route = remaining
                selection_source = SELECTION_EXPLICIT_INSTRUCTION
                considerations.append(
                    _consideration(instruction, CONSIDERATION_SELECTED, APPLICABLE)
                )
                break
            considerations.append(
                _consideration(instruction, CONSIDERATION_INAPPLICABLE, reason)
            )
            skipped.append((instruction.instruction_id, reason))

        if selected is None and allow_route_intent_adapter:
            for instruction in adapters:
                reason, remaining = self._validate_instruction(
                    instruction=instruction,
                    realised_route=realised_route,
                )
                if reason == APPLICABLE:
                    selected = instruction
                    executable_remaining_route = remaining
                    selection_source = SELECTION_ROUTE_INTENT_ADAPTER
                    considerations.append(
                        _consideration(
                            instruction, CONSIDERATION_SELECTED, APPLICABLE
                        )
                    )
                    break
                considerations.append(
                    _consideration(
                        instruction, CONSIDERATION_INAPPLICABLE, reason
                    )
                )
                skipped.append((instruction.instruction_id, reason))

        if selected is None:
            final_reason = (
                skipped[-1][1]
                if skipped
                else INAPPLICABLE_NO_INSTRUCTION
            )
            return self._inapplicable(
                resolution_id, packet_id, decision_tick, current_link_id,
                realised_route, final_reason, None, (), rejected_ids,
                rejected_record_ids,
                tuple(considerations), tuple(skipped),
            )

        intended_next = (
            executable_remaining_route[1]
            if len(executable_remaining_route) > 1
            else None
        )
        return InstructionResolution(
            resolution_id=resolution_id,
            packet_id=packet_id,
            decision_tick=decision_tick,
            current_link_id=current_link_id,
            realised_route=tuple(realised_route),
            status=APPLICABLE,
            reason=APPLICABLE,
            instruction_id=selected.instruction_id,
            decision_artifact_id=selected.decision_artifact_id,
            instruction_version=selected.version,
            remaining_route=executable_remaining_route,
            intended_next_link_id=intended_next,
            superseded_instruction_ids=tuple(
                instruction.instruction_id
                for instruction in ordered
                if instruction.version < selected.version
            ),
            rejected_instruction_ids=rejected_ids,
            rejected_record_ids=rejected_record_ids,
            matches_original_route_intent=_matches_original_remaining_route(
                realised_route=realised_route,
                original_route_intent=original_route_intent,
                remaining_route=executable_remaining_route,
            ),
            selection_source=selection_source,
            considered_instructions=tuple(considerations),
            skipped_instruction_reasons=tuple(skipped),
        )

    def _validate_instruction(
        self,
        *,
        instruction: RoutingInstruction,
        realised_route: tuple[str, ...],
    ) -> tuple[str, tuple[str, ...]]:
        position = _current_instruction_position(
            realised_route=realised_route,
            instruction_route=instruction.remaining_route,
            route_start_ordinal=instruction.route_start_ordinal,
        )
        if position is None:
            if realised_route and realised_route[-1] not in instruction.remaining_route:
                return INAPPLICABLE_CURRENT_LINK_MISMATCH, ()
            return INAPPLICABLE_REALISED_PREFIX_MISMATCH, ()
        if any(link_id not in self._link_ids for link_id in instruction.remaining_route):
            return INAPPLICABLE_UNKNOWN_LINK, ()
        if any(
            transition not in self._supported_transitions
            for transition in zip(
                instruction.remaining_route,
                instruction.remaining_route[1:],
                strict=False,
            )
        ):
            return INAPPLICABLE_DISCONNECTED_ROUTE, ()
        return APPLICABLE, instruction.remaining_route[position:]

    @staticmethod
    def _inapplicable(
        resolution_id: str,
        packet_id: str,
        decision_tick: int,
        current_link_id: str,
        realised_route: tuple[str, ...],
        reason: str,
        selected: RoutingInstruction | None,
        superseded: tuple[str, ...],
        rejected_ids: tuple[str, ...],
        rejected_record_ids: tuple[str, ...],
        considerations: tuple[InstructionConsideration, ...],
        skipped: tuple[tuple[str, str], ...],
    ) -> InstructionResolution:
        return InstructionResolution(
            resolution_id=resolution_id,
            packet_id=packet_id,
            decision_tick=decision_tick,
            current_link_id=current_link_id,
            realised_route=tuple(realised_route),
            status="inapplicable",
            reason=reason,
            instruction_id=(selected.instruction_id if selected else None),
            decision_artifact_id=(
                selected.decision_artifact_id if selected else None
            ),
            instruction_version=(selected.version if selected else None),
            remaining_route=(selected.remaining_route if selected else ()),
            intended_next_link_id=None,
            superseded_instruction_ids=superseded,
            rejected_instruction_ids=rejected_ids,
            rejected_record_ids=rejected_record_ids,
            matches_original_route_intent=None,
            selection_source=None,
            considered_instructions=considerations,
            skipped_instruction_reasons=skipped,
        )


def instruction_from_artifact(
    artifact: RoutingDecisionArtifact,
    *,
    instruction_id: str,
    version: int,
    effective_tick: int,
    provenance: Iterable[tuple[str, str]] = (),
) -> RoutingInstruction:
    """Seal an executable instruction linked to an authority artifact."""

    return RoutingInstruction(
        instruction_id=instruction_id,
        packet_id=artifact.packet_id,
        version=version,
        authority_id=artifact.authority_id,
        decision_artifact_id=artifact.artifact_id,
        issue_tick=artifact.decision_tick,
        effective_tick=effective_tick,
        remaining_route=artifact.proposed_remaining_route,
        policy_id=artifact.policy_id,
        provenance=tuple((*artifact.provenance, *tuple(provenance))),
        route_start_ordinal=artifact.route_start_ordinal,
    )


def legacy_route_intent_instruction(
    *,
    packet_id: str,
    route_intent: tuple[str, ...],
    issue_tick: int,
) -> RoutingInstruction:
    """Adapt an immutable declared route to the version-zero instruction contract."""

    return RoutingInstruction(
        instruction_id=f"instruction:legacy-route-intent:{packet_id}:0",
        packet_id=packet_id,
        version=0,
        authority_id="legacy-route-intent-adapter",
        decision_artifact_id=f"decision:legacy-route-intent:{packet_id}:0",
        issue_tick=issue_tick,
        effective_tick=issue_tick,
        remaining_route=route_intent,
        policy_id="immutable-route-intent",
        provenance=(
            ("adapter", "immutable-route-intent-v0"),
            ("source", "packet.route_intent"),
        ),
        route_start_ordinal=0,
    )


def _matches_original_remaining_route(
    *,
    realised_route: tuple[str, ...],
    original_route_intent: tuple[str, ...],
    remaining_route: tuple[str, ...],
) -> bool:
    realised_prefix_length = len(realised_route)
    prefix_matches = original_route_intent[:realised_prefix_length] == realised_route
    return (
        prefix_matches
        and original_route_intent[realised_prefix_length - 1 :] == remaining_route
    )


def _current_instruction_position(
    *,
    realised_route: tuple[str, ...],
    instruction_route: tuple[str, ...],
    route_start_ordinal: int,
) -> int | None:
    """Align one route cursor to the complete canonical realised history."""

    current_ordinal = len(realised_route) - 1
    if route_start_ordinal > current_ordinal:
        return None
    position = current_ordinal - route_start_ordinal
    if position >= len(instruction_route):
        return None
    realised_instruction_prefix = realised_route[
        route_start_ordinal : current_ordinal + 1
    ]
    if instruction_route[: position + 1] != realised_instruction_prefix:
        return None
    return position


def _is_route_intent_adapter(instruction: RoutingInstruction) -> bool:
    return (
        instruction.version == 0
        and instruction.authority_id == "legacy-route-intent-adapter"
        and instruction.policy_id == "immutable-route-intent"
    )


def _consideration(
    instruction: RoutingInstruction,
    outcome: str,
    reason: str,
) -> InstructionConsideration:
    return InstructionConsideration(
        instruction_id=instruction.instruction_id,
        instruction_version=instruction.version,
        decision_artifact_id=instruction.decision_artifact_id,
        authority_id=instruction.authority_id,
        outcome=outcome,
        reason=reason,
    )


def decision_artifact_index(
    artifacts: Iterable[RoutingDecisionArtifact],
) -> Mapping[str, RoutingDecisionArtifact]:
    """Build an immutable ID index and reject ambiguous artifact identity."""

    indexed: dict[str, RoutingDecisionArtifact] = {}
    for artifact in artifacts:
        if artifact.artifact_id in indexed:
            raise ValueError(f"duplicate routing artifact ID: {artifact.artifact_id}")
        indexed[artifact.artifact_id] = artifact
    return MappingProxyType(indexed)
