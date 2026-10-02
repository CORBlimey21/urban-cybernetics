# SPDX-License-Identifier: MPL-2.0
"""Append-only manual override artifacts for fixed-time signal control."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Literal, Self


SIGNAL_OVERRIDE_SCHEMA_VERSION = "uc.fixed-time-signal-override.v1"
SIGNAL_OVERRIDE_STORE_SCHEMA_VERSION = "uc.fixed-time-signal-override-store.v1"
SIGNAL_OVERRIDE_EXTENSION_VERSION = "fixed-time-signal-extension-v1"

TARGET_CONTROLLER = "controller"
TARGET_SIGNAL_GROUP = "signal_group"
SUPPORTED_TARGET_KINDS = frozenset((TARGET_CONTROLLER, TARGET_SIGNAL_GROUP))
OverrideTargetKind = Literal["controller", "signal_group"]

FORCE_OPEN = "force_open"
FORCE_CLOSED = "force_closed"
CLEAR = "clear"
SUPPORTED_OVERRIDE_ACTIONS = frozenset((FORCE_OPEN, FORCE_CLOSED, CLEAR))
OverrideAction = Literal["force_open", "force_closed", "clear"]

ACCEPTED = "accepted"
REJECTED = "rejected"
ReceiptDisposition = Literal["accepted", "rejected"]

REJECTED_DUPLICATE_ID = "duplicate_override_id"
REJECTED_UNKNOWN_TARGET = "unknown_override_target"
REJECTED_DUPLICATE_TARGET_VERSION = "duplicate_target_version"
REJECTED_RECEIPT_PRECEDES_ISSUE = "receipt_precedes_issue"
REJECTED_AFTER_TERMINAL = "submission_after_terminal_tick"
REJECTED_EFFECTIVE_AFTER_TERMINAL = "effective_after_terminal_tick"
REJECTED_INVALID_CLEAR_REFERENCE = "invalid_clear_reference"


class SignalOverrideValidationError(ValueError):
    """Reject malformed schemas or corrupted replay snapshots."""


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise SignalOverrideValidationError(f"{field_name} must be non-empty")
    return value


def _require_int(
    value: object,
    field_name: str,
    *,
    non_negative: bool = True,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SignalOverrideValidationError(f"{field_name} must be an integer")
    if non_negative and value < 0:
        raise SignalOverrideValidationError(f"{field_name} must be non-negative")
    return value


def _normalise_strings(values: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise SignalOverrideValidationError(f"{field_name} must be a tuple")
    normalised = tuple(_require_string(item, field_name) for item in values)
    if len(normalised) != len(set(normalised)):
        raise SignalOverrideValidationError(f"{field_name} contains duplicates")
    return normalised


def _normalise_metadata(
    values: object,
    field_name: str,
) -> tuple[tuple[str, str], ...]:
    if not isinstance(values, tuple):
        raise SignalOverrideValidationError(f"{field_name} must be a tuple")
    result: list[tuple[str, str]] = []
    keys: set[str] = set()
    for item in values:
        if not isinstance(item, tuple) or len(item) != 2:
            raise SignalOverrideValidationError(
                f"{field_name} must contain (key, value) tuples"
            )
        key = _require_string(item[0], f"{field_name} key")
        value = _require_string(item[1], f"{field_name} value")
        if key in keys:
            raise SignalOverrideValidationError(
                f"{field_name} contains duplicate key: {key}"
            )
        keys.add(key)
        result.append((key, value))
    return tuple(sorted(result))


def _metadata_from_json(
    value: object,
    field_name: str,
) -> tuple[tuple[object, object], ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, list) or len(item) != 2 for item in value
    ):
        raise SignalOverrideValidationError(
            f"{field_name} must contain two-item lists"
        )
    return tuple((item[0], item[1]) for item in value)


def _check_keys(
    payload: object,
    *,
    required: frozenset[str],
    optional: frozenset[str],
    context: str,
) -> None:
    if not isinstance(payload, Mapping):
        raise SignalOverrideValidationError(f"{context} must be an object")
    missing = sorted(required - payload.keys())
    unknown = sorted(payload.keys() - required - optional)
    if missing or unknown:
        raise SignalOverrideValidationError(
            f"{context} fields invalid; missing={missing}, unknown={unknown}"
        )


def _hash(payload: object) -> str:
    serialised = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SignalOverrideCommand:
    """One immutable force or explicit withdrawal request."""

    override_id: str
    target_kind: OverrideTargetKind
    target_id: str
    action: OverrideAction
    actor_id: str
    issue_tick: int
    effective_tick: int
    priority: int
    version: int
    reason_code: str
    expiry_tick: int | None = None
    withdrawn_override_ids: tuple[str, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()
    schema_version: str = SIGNAL_OVERRIDE_SCHEMA_VERSION
    extension_version: str = SIGNAL_OVERRIDE_EXTENSION_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SIGNAL_OVERRIDE_SCHEMA_VERSION:
            raise SignalOverrideValidationError(
                f"unsupported override schema: {self.schema_version}"
            )
        if self.extension_version != SIGNAL_OVERRIDE_EXTENSION_VERSION:
            raise SignalOverrideValidationError(
                f"unsupported override extension: {self.extension_version}"
            )
        _require_string(self.override_id, "override_id")
        if self.target_kind not in SUPPORTED_TARGET_KINDS:
            raise SignalOverrideValidationError(
                f"unsupported target_kind: {self.target_kind}"
            )
        _require_string(self.target_id, "target_id")
        if self.action not in SUPPORTED_OVERRIDE_ACTIONS:
            raise SignalOverrideValidationError(
                f"unsupported override action: {self.action}"
            )
        _require_string(self.actor_id, "actor_id")
        issue_tick = _require_int(self.issue_tick, "issue_tick")
        effective_tick = _require_int(self.effective_tick, "effective_tick")
        if effective_tick < issue_tick:
            raise SignalOverrideValidationError(
                "effective_tick cannot precede issue_tick"
            )
        _require_int(self.priority, "priority")
        _require_int(self.version, "version")
        _require_string(self.reason_code, "reason_code")
        if self.expiry_tick is not None:
            expiry_tick = _require_int(self.expiry_tick, "expiry_tick")
            if expiry_tick <= effective_tick:
                raise SignalOverrideValidationError(
                    "expiry_tick must be greater than effective_tick"
                )
        withdrawn = _normalise_strings(
            self.withdrawn_override_ids,
            "withdrawn_override_ids",
        )
        object.__setattr__(self, "withdrawn_override_ids", withdrawn)
        object.__setattr__(
            self,
            "metadata",
            _normalise_metadata(self.metadata, "override metadata"),
        )
        if self.action == CLEAR:
            if not withdrawn:
                raise SignalOverrideValidationError(
                    "clear requires explicit withdrawn_override_ids"
                )
            if self.expiry_tick is not None:
                raise SignalOverrideValidationError("clear cannot expire")
        elif withdrawn:
            raise SignalOverrideValidationError(
                "force commands cannot withdraw override IDs"
            )

    @property
    def command_hash(self) -> str:
        return _hash(self.to_dict(include_hash=False))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "override_id": self.override_id,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "action": self.action,
            "actor_id": self.actor_id,
            "issue_tick": self.issue_tick,
            "effective_tick": self.effective_tick,
            "priority": self.priority,
            "version": self.version,
            "reason_code": self.reason_code,
            "expiry_tick": self.expiry_tick,
            "withdrawn_override_ids": list(self.withdrawn_override_ids),
            "metadata": [list(item) for item in self.metadata],
            "schema_version": self.schema_version,
            "extension_version": self.extension_version,
        }
        if include_hash:
            payload["command_hash"] = self.command_hash
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        _check_keys(
            payload,
            required=frozenset(
                (
                    "override_id",
                    "target_kind",
                    "target_id",
                    "action",
                    "actor_id",
                    "issue_tick",
                    "effective_tick",
                    "priority",
                    "version",
                    "reason_code",
                    "schema_version",
                    "extension_version",
                )
            ),
            optional=frozenset(
                (
                    "expiry_tick",
                    "withdrawn_override_ids",
                    "metadata",
                    "command_hash",
                )
            ),
            context="signal override command",
        )
        withdrawn = payload.get("withdrawn_override_ids", [])
        if not isinstance(withdrawn, list):
            raise SignalOverrideValidationError(
                "withdrawn_override_ids must be a list"
            )
        command = cls(
            override_id=payload["override_id"],  # type: ignore[arg-type]
            target_kind=payload["target_kind"],  # type: ignore[arg-type]
            target_id=payload["target_id"],  # type: ignore[arg-type]
            action=payload["action"],  # type: ignore[arg-type]
            actor_id=payload["actor_id"],  # type: ignore[arg-type]
            issue_tick=payload["issue_tick"],  # type: ignore[arg-type]
            effective_tick=payload["effective_tick"],  # type: ignore[arg-type]
            priority=payload["priority"],  # type: ignore[arg-type]
            version=payload["version"],  # type: ignore[arg-type]
            reason_code=payload["reason_code"],  # type: ignore[arg-type]
            expiry_tick=payload.get("expiry_tick"),  # type: ignore[arg-type]
            withdrawn_override_ids=tuple(withdrawn),  # type: ignore[arg-type]
            metadata=_metadata_from_json(  # type: ignore[arg-type]
                payload.get("metadata", []),
                "override metadata",
            ),
            schema_version=payload["schema_version"],  # type: ignore[arg-type]
            extension_version=payload["extension_version"],  # type: ignore[arg-type]
        )
        if payload.get("command_hash") not in (None, command.command_hash):
            raise SignalOverrideValidationError("override command_hash mismatch")
        return command


@dataclass(frozen=True, slots=True)
class SignalOverrideStoreConfig:
    """Versioned execution policy and optional terminal run boundary."""

    terminal_tick: int | None = None
    schema_version: str = SIGNAL_OVERRIDE_STORE_SCHEMA_VERSION
    extension_version: str = SIGNAL_OVERRIDE_EXTENSION_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SIGNAL_OVERRIDE_STORE_SCHEMA_VERSION:
            raise SignalOverrideValidationError(
                f"unsupported override store schema: {self.schema_version}"
            )
        if self.extension_version != SIGNAL_OVERRIDE_EXTENSION_VERSION:
            raise SignalOverrideValidationError(
                f"unsupported override store extension: {self.extension_version}"
            )
        if self.terminal_tick is not None:
            _require_int(self.terminal_tick, "terminal_tick")

    @property
    def config_hash(self) -> str:
        return _hash(asdict(self))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        _check_keys(
            payload,
            required=frozenset(("schema_version", "extension_version")),
            optional=frozenset(("terminal_tick",)),
            context="signal override store config",
        )
        return cls(
            terminal_tick=payload.get("terminal_tick"),  # type: ignore[arg-type]
            schema_version=payload["schema_version"],  # type: ignore[arg-type]
            extension_version=payload["extension_version"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class SignalOverrideReceipt:
    """Append-only disposition for one structurally valid submission."""

    receipt_id: str
    sequence_number: int
    recorded_tick: int
    command: SignalOverrideCommand
    command_hash: str
    disposition: ReceiptDisposition
    reason: str | None
    participates_in_resolution: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "receipt_id": self.receipt_id,
            "sequence_number": self.sequence_number,
            "recorded_tick": self.recorded_tick,
            "command": self.command.to_dict(),
            "command_hash": self.command_hash,
            "disposition": self.disposition,
            "reason": self.reason,
            "participates_in_resolution": self.participates_in_resolution,
        }


@dataclass(frozen=True, slots=True)
class SignalOverrideResolution:
    """Pure resolution result for one controlled signal group and tick."""

    tick: int
    controller_id: str
    signal_group_id: str
    baseline_is_open: bool
    considered_override_ids: tuple[str, ...]
    cleared_override_ids: tuple[str, ...]
    selected_override_id: str | None
    selected_override_action: str | None
    selected_target_kind: str | None
    effective_is_open: bool
    override_store_config_hash: str
    override_store_hash: str


class SignalOverrideStore:
    """Validated append-only receipts and deterministic temporal resolution."""

    def __init__(
        self,
        *,
        controller_ids: tuple[str, ...],
        signal_group_ids: tuple[str, ...],
        config: SignalOverrideStoreConfig | None = None,
    ) -> None:
        self.controller_ids = tuple(
            sorted(_normalise_strings(controller_ids, "controller_ids"))
        )
        self.signal_group_ids = tuple(
            sorted(_normalise_strings(signal_group_ids, "signal_group_ids"))
        )
        self.config = config or SignalOverrideStoreConfig()
        self._history: list[SignalOverrideReceipt] = []
        self._seen_override_ids: set[str] = set()
        self._accepted_by_id: dict[str, SignalOverrideReceipt] = {}
        self._accepted_versions: set[tuple[str, str, int]] = set()

    @property
    def history(self) -> tuple[SignalOverrideReceipt, ...]:
        return tuple(self._history)

    @property
    def accepted_history(self) -> tuple[SignalOverrideReceipt, ...]:
        return tuple(
            item for item in self._history if item.participates_in_resolution
        )

    @property
    def store_hash(self) -> str:
        return _hash(
            {
                "config_hash": self.config.config_hash,
                "controller_ids": list(self.controller_ids),
                "signal_group_ids": list(self.signal_group_ids),
                "history": [item.to_dict() for item in self._history],
            }
        )

    def submit(
        self,
        command: SignalOverrideCommand,
        *,
        recorded_tick: int,
    ) -> SignalOverrideReceipt:
        if not isinstance(command, SignalOverrideCommand):
            raise TypeError("command must be SignalOverrideCommand")
        _require_int(recorded_tick, "recorded_tick")
        reason = self._rejection_reason(command, recorded_tick)
        disposition: ReceiptDisposition = REJECTED if reason else ACCEPTED
        sequence = len(self._history)
        receipt_payload = {
            "sequence_number": sequence,
            "recorded_tick": recorded_tick,
            "command_hash": command.command_hash,
            "disposition": disposition,
            "reason": reason,
        }
        receipt = SignalOverrideReceipt(
            receipt_id=(
                f"signal-override-receipt:{sequence}:"
                f"{_hash(receipt_payload)[:16]}"
            ),
            sequence_number=sequence,
            recorded_tick=recorded_tick,
            command=command,
            command_hash=command.command_hash,
            disposition=disposition,
            reason=reason,
            participates_in_resolution=reason is None,
        )
        self._history.append(receipt)
        self._seen_override_ids.add(command.override_id)
        if reason is None:
            self._accepted_by_id[command.override_id] = receipt
            self._accepted_versions.add(
                (command.target_kind, command.target_id, command.version)
            )
        return receipt

    def _rejection_reason(
        self,
        command: SignalOverrideCommand,
        recorded_tick: int,
    ) -> str | None:
        if command.override_id in self._seen_override_ids:
            return REJECTED_DUPLICATE_ID
        supported_targets = (
            self.controller_ids
            if command.target_kind == TARGET_CONTROLLER
            else self.signal_group_ids
        )
        if command.target_id not in supported_targets:
            return REJECTED_UNKNOWN_TARGET
        if recorded_tick < command.issue_tick:
            return REJECTED_RECEIPT_PRECEDES_ISSUE
        terminal_tick = self.config.terminal_tick
        if terminal_tick is not None:
            if recorded_tick > terminal_tick:
                return REJECTED_AFTER_TERMINAL
            if command.effective_tick > terminal_tick:
                return REJECTED_EFFECTIVE_AFTER_TERMINAL
        version_key = (command.target_kind, command.target_id, command.version)
        if version_key in self._accepted_versions:
            return REJECTED_DUPLICATE_TARGET_VERSION
        if command.action == CLEAR:
            for override_id in command.withdrawn_override_ids:
                prior = self._accepted_by_id.get(override_id)
                if prior is None:
                    return REJECTED_INVALID_CLEAR_REFERENCE
                prior_command = prior.command
                if (
                    prior_command.action == CLEAR
                    or prior_command.target_kind != command.target_kind
                    or prior_command.target_id != command.target_id
                ):
                    return REJECTED_INVALID_CLEAR_REFERENCE
        return None

    def resolve(
        self,
        *,
        controller_id: str,
        signal_group_id: str,
        tick: int,
        baseline_is_open: bool,
    ) -> SignalOverrideResolution:
        _require_int(tick, "resolution tick")
        relevant = tuple(
            receipt
            for receipt in self.accepted_history
            if (
                receipt.recorded_tick <= tick
                and receipt.command.issue_tick <= tick
                and receipt.command.effective_tick <= tick
                and (
                    receipt.command.action == CLEAR
                    or receipt.command.expiry_tick is None
                    or tick < receipt.command.expiry_tick
                )
                and (
                    (
                        receipt.command.target_kind == TARGET_CONTROLLER
                        and receipt.command.target_id == controller_id
                    )
                    or (
                        receipt.command.target_kind == TARGET_SIGNAL_GROUP
                        and receipt.command.target_id == signal_group_id
                    )
                )
            )
        )
        clears = tuple(
            receipt for receipt in relevant if receipt.command.action == CLEAR
        )
        cleared_ids = frozenset(
            override_id
            for receipt in clears
            for override_id in receipt.command.withdrawn_override_ids
        )
        forces = tuple(
            receipt
            for receipt in relevant
            if (
                receipt.command.action != CLEAR
                and receipt.command.override_id not in cleared_ids
            )
        )
        group_forces = tuple(
            item
            for item in forces
            if item.command.target_kind == TARGET_SIGNAL_GROUP
        )
        candidates = group_forces or tuple(
            item
            for item in forces
            if item.command.target_kind == TARGET_CONTROLLER
        )
        selected = (
            max(
                candidates,
                key=lambda item: (item.command.priority, item.command.version),
            )
            if candidates
            else None
        )
        action = selected.command.action if selected is not None else None
        effective = baseline_is_open
        if action == FORCE_OPEN:
            effective = True
        elif action == FORCE_CLOSED:
            effective = False
        return SignalOverrideResolution(
            tick=tick,
            controller_id=controller_id,
            signal_group_id=signal_group_id,
            baseline_is_open=baseline_is_open,
            considered_override_ids=tuple(
                sorted(receipt.command.override_id for receipt in relevant)
            ),
            cleared_override_ids=tuple(sorted(cleared_ids)),
            selected_override_id=(
                selected.command.override_id if selected is not None else None
            ),
            selected_override_action=action,
            selected_target_kind=(
                selected.command.target_kind if selected is not None else None
            ),
            effective_is_open=effective,
            override_store_config_hash=self.config.config_hash,
            override_store_hash=self.store_hash,
        )

    def to_snapshot(self) -> dict[str, object]:
        return {
            "schema_version": SIGNAL_OVERRIDE_STORE_SCHEMA_VERSION,
            "extension_version": SIGNAL_OVERRIDE_EXTENSION_VERSION,
            "config": self.config.to_dict(),
            "controller_ids": list(self.controller_ids),
            "signal_group_ids": list(self.signal_group_ids),
            "history": [item.to_dict() for item in self._history],
            "store_hash": self.store_hash,
        }

    @classmethod
    def from_snapshot(cls, payload: Mapping[str, object]) -> Self:
        _check_keys(
            payload,
            required=frozenset(
                (
                    "schema_version",
                    "extension_version",
                    "config",
                    "controller_ids",
                    "signal_group_ids",
                    "history",
                    "store_hash",
                )
            ),
            optional=frozenset(),
            context="signal override store snapshot",
        )
        if payload["schema_version"] != SIGNAL_OVERRIDE_STORE_SCHEMA_VERSION:
            raise SignalOverrideValidationError("snapshot schema_version mismatch")
        if payload["extension_version"] != SIGNAL_OVERRIDE_EXTENSION_VERSION:
            raise SignalOverrideValidationError("snapshot extension_version mismatch")
        config_payload = payload["config"]
        if not isinstance(config_payload, Mapping):
            raise SignalOverrideValidationError("snapshot config must be an object")
        config = SignalOverrideStoreConfig.from_dict(config_payload)
        controller_ids = payload["controller_ids"]
        signal_group_ids = payload["signal_group_ids"]
        history = payload["history"]
        if not isinstance(controller_ids, list) or not isinstance(
            signal_group_ids, list
        ):
            raise SignalOverrideValidationError("snapshot target IDs must be lists")
        if not isinstance(history, list):
            raise SignalOverrideValidationError("snapshot history must be a list")
        store = cls(
            controller_ids=tuple(controller_ids),  # type: ignore[arg-type]
            signal_group_ids=tuple(signal_group_ids),  # type: ignore[arg-type]
            config=config,
        )
        for expected in history:
            if not isinstance(expected, Mapping):
                raise SignalOverrideValidationError(
                    "snapshot receipt must be an object"
                )
            command_payload = expected.get("command")
            if not isinstance(command_payload, Mapping):
                raise SignalOverrideValidationError(
                    "snapshot receipt command must be an object"
                )
            command = SignalOverrideCommand.from_dict(command_payload)
            receipt = store.submit(
                command,
                recorded_tick=expected.get("recorded_tick"),  # type: ignore[arg-type]
            )
            if receipt.to_dict() != dict(expected):
                raise SignalOverrideValidationError(
                    f"override receipt replay mismatch at {receipt.sequence_number}"
                )
        if payload["store_hash"] != store.store_hash:
            raise SignalOverrideValidationError("override store_hash mismatch")
        return store
