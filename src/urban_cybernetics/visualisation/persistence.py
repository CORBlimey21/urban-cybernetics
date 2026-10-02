# SPDX-License-Identifier: MPL-2.0
"""Durable, path-confined V2 evidence-plane storage."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from .v2_contract import (
    EventChunk,
    FrozenRunRequest,
    LiveMessage,
    MovementAllocationEvidence,
    ReplayCheckpoint,
    RunArtifactSummary,
)


class V2ArtifactNotFound(KeyError):
    pass


class ArtifactRepository:
    """Registry rooted at a backend-declared directory; callers only supply run IDs."""

    def __init__(self, root: Path, *, read_only_roots: tuple[Path, ...] = ()) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.read_only_roots = tuple(path.resolve() for path in read_only_roots if path.resolve() != self.root)
        self._lock = RLock()

    def create(self, frozen: FrozenRunRequest, summary: RunArtifactSummary) -> None:
        with self._lock:
            directory = self._run_directory(frozen.run_id, must_exist=False)
            directory.mkdir(parents=False, exist_ok=False)
            for child in ("events", "checkpoints", "movements"):
                (directory / child).mkdir()
            self._write_json(directory / "request.json", frozen.model_dump(mode="json"))
            self.write_summary(summary)

    def list_summaries(self) -> tuple[RunArtifactSummary, ...]:
        summaries: list[RunArtifactSummary] = []
        with self._lock:
            seen: set[str] = set()
            for root in (self.root, *self.read_only_roots):
                for path in sorted(root.glob("*/summary.json")):
                    summary = RunArtifactSummary.model_validate_json(path.read_text(encoding="utf-8"))
                    if summary.run_id in seen:
                        raise ValueError(f"duplicate V2 run_id across artifact roots: {summary.run_id}")
                    seen.add(summary.run_id)
                    summaries.append(summary)
        return tuple(sorted(summaries, key=lambda item: item.created_at, reverse=True))

    def get_summary(self, run_id: str) -> RunArtifactSummary:
        path = self._run_directory(run_id) / "summary.json"
        return RunArtifactSummary.model_validate_json(path.read_text(encoding="utf-8"))

    def write_summary(self, summary: RunArtifactSummary) -> None:
        with self._lock:
            self._write_json(self._run_directory(summary.run_id) / "summary.json", summary.model_dump(mode="json"))

    def write_document(self, run_id: str, filename: str, payload: object) -> None:
        if filename not in {"topology.json", "packets.json", "validation.json", "final_bundle.json", "lifecycle.json"}:
            raise ValueError("undeclared artifact document")
        with self._lock:
            self._write_json(self._run_directory(run_id) / filename, payload)

    def read_document(self, run_id: str, filename: str) -> object:
        if filename not in {"topology.json", "packets.json", "validation.json", "final_bundle.json", "lifecycle.json", "request.json"}:
            raise ValueError("undeclared artifact document")
        path = self._run_directory(run_id) / filename
        if not path.is_file():
            raise V2ArtifactNotFound(f"{run_id}/{filename}")
        return json.loads(path.read_text(encoding="utf-8"))

    def append_event_chunk(self, chunk: EventChunk) -> None:
        with self._lock:
            path = self._run_directory(chunk.run_id) / "events" / f"{chunk.chunk_index:08d}.json"
            if path.exists():
                existing = EventChunk.model_validate_json(path.read_text(encoding="utf-8"))
                if existing != chunk:
                    raise ValueError("sealed event chunk is immutable")
                return
            self._write_json(path, chunk.model_dump(mode="json"))

    def event_chunks(self, run_id: str, *, start_sequence: int = 0, end_sequence: int | None = None) -> tuple[EventChunk, ...]:
        chunks: list[EventChunk] = []
        for path in sorted((self._run_directory(run_id) / "events").glob("*.json")):
            chunk = EventChunk.model_validate_json(path.read_text(encoding="utf-8"))
            if chunk.end_sequence < start_sequence:
                continue
            if end_sequence is not None and chunk.start_sequence > end_sequence:
                break
            chunks.append(chunk)
        return tuple(chunks)

    def append_checkpoint(self, checkpoint: ReplayCheckpoint) -> None:
        with self._lock:
            path = self._run_directory(checkpoint.run_id) / "checkpoints" / f"{checkpoint.checkpoint_index:08d}.json"
            if path.exists():
                existing = ReplayCheckpoint.model_validate_json(path.read_text(encoding="utf-8"))
                if existing != checkpoint:
                    raise ValueError("sealed checkpoint is immutable")
                return
            self._write_json(path, checkpoint.model_dump(mode="json"))

    def checkpoints(self, run_id: str) -> tuple[ReplayCheckpoint, ...]:
        return tuple(ReplayCheckpoint.model_validate_json(path.read_text(encoding="utf-8")) for path in sorted((self._run_directory(run_id) / "checkpoints").glob("*.json")))

    def append_movement_evidence(self, evidence: MovementAllocationEvidence) -> None:
        with self._lock:
            safe_node = hashlib.sha256(evidence.junction_id.encode()).hexdigest()[:12]
            path = self._run_directory(evidence.run_id) / "movements" / f"{evidence.tick:08d}-{safe_node}.json"
            if path.exists():
                existing = MovementAllocationEvidence.model_validate_json(path.read_text(encoding="utf-8"))
                if existing != evidence:
                    raise ValueError("sealed movement evidence is immutable")
                return
            self._write_json(path, evidence.model_dump(mode="json"))

    def movement_evidence(self, run_id: str, tick: int | None = None) -> tuple[MovementAllocationEvidence, ...]:
        pattern = f"{tick:08d}-*.json" if tick is not None else "*.json"
        return tuple(MovementAllocationEvidence.model_validate_json(path.read_text(encoding="utf-8")) for path in sorted((self._run_directory(run_id) / "movements").glob(pattern)))

    def append_live_message(self, message: LiveMessage) -> None:
        with self._lock:
            path = self._run_directory(message.run_id) / "progress.jsonl"
            with path.open("a", encoding="utf-8") as handle:
                handle.write(message.model_dump_json() + "\n")

    def live_messages(self, run_id: str, after: int = -1) -> tuple[LiveMessage, ...]:
        with self._lock:
            path = self._run_directory(run_id) / "progress.jsonl"
            if not path.exists():
                return ()
            return tuple(message for line in path.read_text(encoding="utf-8").splitlines() if (message := LiveMessage.model_validate_json(line)).message_id > after)

    def artifact_size_bytes(self, run_id: str) -> int:
        return sum(path.stat().st_size for path in self._run_directory(run_id).rglob("*") if path.is_file())

    def _run_directory(self, run_id: str, *, must_exist: bool = True) -> Path:
        if not run_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-" for character in run_id):
            raise V2ArtifactNotFound(run_id)
        roots = (self.root, *self.read_only_roots) if must_exist else (self.root,)
        for root in roots:
            path = (root / run_id).resolve()
            if path.parent == root and (not must_exist or path.is_dir()):
                return path
        raise V2ArtifactNotFound(run_id)

    @staticmethod
    def _write_json(path: Path, payload: object) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, separators=(",", ": "), ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(path)


def event_payload_sha256(events: tuple[object, ...]) -> str:
    payload = json.dumps(events, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def utc_now() -> datetime:
    return datetime.now(UTC)
