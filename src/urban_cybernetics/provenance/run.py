"""Generic in-memory run provenance records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must be non-empty")


def _freeze_config_value(value: object) -> object:
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, tuple | list):
        return tuple(_freeze_config_value(item) for item in value)
    if isinstance(value, Mapping):
        frozen: dict[str, object] = {}
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise TypeError("config mappings must use string keys")
            frozen[key] = _freeze_config_value(nested_value)
        return MappingProxyType(frozen)
    raise TypeError(
        "config values must be JSON-like: strings, ints, floats, booleans, "
        "None, lists/tuples, or dicts with string keys"
    )


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


def _normalise_string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        raise TypeError(f"{field_name} must be an iterable of strings, not a string")
    try:
        strings = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError(f"{field_name} must be an iterable of strings") from exc
    if not all(isinstance(item, str) for item in strings):
        raise TypeError(f"{field_name} must contain only strings")
    return strings


@dataclass(frozen=True, slots=True)
class RunMetadata:
    """Stable identity and optional reproducibility labels for one run."""

    run_id: str
    scenario_name: str
    created_at: str | None = None
    code_version: str | None = None
    schema_version: str = "p1.run_metadata.v1"

    def __post_init__(self) -> None:
        _require_non_empty(self.run_id, "run_id")
        _require_non_empty(self.scenario_name, "scenario_name")


@dataclass(frozen=True, slots=True)
class RunConfigSnapshot:
    """Detached, read-only snapshot of a run configuration."""

    run_id: str
    config: Mapping[str, object]
    schema_version: str = "p1.run_config_snapshot.v1"

    def __post_init__(self) -> None:
        _require_non_empty(self.run_id, "run_id")
        if not isinstance(self.config, Mapping):
            raise TypeError("config must be a mapping")
        object.__setattr__(self, "config", _freeze_config_value(self.config))


@dataclass(frozen=True, slots=True)
class RunArtifactIndex:
    """Run-level references to input and output artifacts."""

    run_id: str
    input_artifact_ids: tuple[str, ...] = ()
    output_artifact_ids: tuple[str, ...] = ()
    frame_ids: tuple[str, ...] = ()
    receipt_ids: tuple[str, ...] = ()
    decision_ids: tuple[str, ...] = ()
    packet_ids: tuple[str, ...] = ()
    event_count: int = 0
    schema_version: str = "p1.run_artifact_index.v1"

    def __post_init__(self) -> None:
        _require_non_empty(self.run_id, "run_id")
        for field_name in (
            "input_artifact_ids",
            "output_artifact_ids",
            "frame_ids",
            "receipt_ids",
            "decision_ids",
            "packet_ids",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalise_id_tuple(getattr(self, field_name), field_name),
            )
        if self.event_count < 0:
            raise ValueError("event_count must be non-negative")


@dataclass(frozen=True, slots=True)
class RunSummary:
    """A frozen provenance artifact summarising one completed or inspected run."""

    metadata: RunMetadata
    config_snapshot: RunConfigSnapshot | None
    artifact_index: RunArtifactIndex
    validation_status: str = "not_run"
    notes: tuple[str, ...] = ()
    schema_version: str = "p1.run_summary.v1"

    def __post_init__(self) -> None:
        if self.config_snapshot is not None:
            if self.config_snapshot.run_id != self.metadata.run_id:
                raise ValueError("config_snapshot run_id must match metadata run_id")
        if self.artifact_index.run_id != self.metadata.run_id:
            raise ValueError("artifact_index run_id must match metadata run_id")
        if self.validation_status not in {"not_run", "passed", "failed"}:
            raise ValueError("unsupported validation_status")
        object.__setattr__(
            self,
            "notes",
            _normalise_string_tuple(self.notes, "notes"),
        )
