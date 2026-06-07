"""Small in-memory recorder for generic run provenance."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from urban_cybernetics.provenance.run import (
    RunArtifactIndex,
    RunConfigSnapshot,
    RunMetadata,
    RunSummary,
    _normalise_id_tuple,
)


class RunRecorder:
    """Collect run-level references until sealing a frozen summary."""

    def __init__(self, metadata: RunMetadata) -> None:
        self._metadata = metadata
        self._config_snapshot: RunConfigSnapshot | None = None
        self._input_artifact_ids: list[str] = []
        self._output_artifact_ids: list[str] = []
        self._frame_ids: list[str] = []
        self._receipt_ids: list[str] = []
        self._decision_ids: list[str] = []
        self._packet_ids: list[str] = []
        self._event_count = 0
        self._sealed_summary: RunSummary | None = None

    @property
    def metadata(self) -> RunMetadata:
        """Return the immutable metadata for this recorder."""

        return self._metadata

    def record_config(self, config: Mapping[str, object]) -> None:
        self._ensure_open()
        self._config_snapshot = RunConfigSnapshot(
            run_id=self._metadata.run_id,
            config=config,
        )

    def record_input_artifact_ids(self, artifact_ids: Iterable[str]) -> None:
        self._ensure_open()
        self._input_artifact_ids.extend(
            _normalise_id_tuple(artifact_ids, "input_artifact_ids")
        )

    def record_output_artifact_ids(self, artifact_ids: Iterable[str]) -> None:
        self._ensure_open()
        self._output_artifact_ids.extend(
            _normalise_id_tuple(artifact_ids, "output_artifact_ids")
        )

    def record_frames(self, frames: Iterable[object]) -> None:
        self._ensure_open()
        self._frame_ids.extend(_ids_from_attribute(frames, "frame_id"))

    def record_receipts(self, receipts: Iterable[object]) -> None:
        self._ensure_open()
        self._receipt_ids.extend(_ids_from_attribute(receipts, "receipt_id"))

    def record_decisions(self, decisions: Iterable[object]) -> None:
        self._ensure_open()
        self._decision_ids.extend(_ids_from_attribute(decisions, "decision_id"))

    def record_packet_ids(self, packet_ids: Iterable[str]) -> None:
        self._ensure_open()
        self._packet_ids.extend(_normalise_id_tuple(packet_ids, "packet_ids"))

    def record_event_count(self, event_count: int) -> None:
        self._ensure_open()
        if event_count < 0:
            raise ValueError("event_count must be non-negative")
        self._event_count = event_count

    def seal(
        self,
        *,
        validation_status: str = "not_run",
        notes: Iterable[str] = (),
    ) -> RunSummary:
        if self._sealed_summary is not None:
            return self._sealed_summary
        artifact_index = RunArtifactIndex(
            run_id=self._metadata.run_id,
            input_artifact_ids=tuple(self._input_artifact_ids),
            output_artifact_ids=tuple(self._output_artifact_ids),
            frame_ids=tuple(self._frame_ids),
            receipt_ids=tuple(self._receipt_ids),
            decision_ids=tuple(self._decision_ids),
            packet_ids=tuple(self._packet_ids),
            event_count=self._event_count,
        )
        self._sealed_summary = RunSummary(
            metadata=self._metadata,
            config_snapshot=self._config_snapshot,
            artifact_index=artifact_index,
            validation_status=validation_status,
            notes=tuple(notes),
        )
        return self._sealed_summary

    def _ensure_open(self) -> None:
        if self._sealed_summary is not None:
            raise RuntimeError("RunRecorder is sealed")


def _ids_from_attribute(items: Iterable[object], attribute_name: str) -> tuple[str, ...]:
    ids: list[str] = []
    for item in items:
        try:
            artifact_id = getattr(item, attribute_name)
        except AttributeError as exc:
            raise TypeError(f"artifact does not expose .{attribute_name}") from exc
        if not isinstance(artifact_id, str):
            raise TypeError(f".{attribute_name} must be a string")
        if not artifact_id:
            raise ValueError(f".{attribute_name} must be non-empty")
        ids.append(artifact_id)
    return tuple(ids)
