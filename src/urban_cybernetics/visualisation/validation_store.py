"""Append-only validation history and sanctioned background execution."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Event, RLock, Thread

from .contract import VRunBundle
from .validation_cases import CASES, CASES_BY_ID, current_code_commit, execute_case
from .validation_contract import ValidationCase, ValidationLifecycle, ValidationLibraryRecord, ValidationResult, ValidationRunStatus


class ValidationArtifactNotFound(KeyError):
    pass


class ValidationRepository:
    """Writable history plus immutable repository fixtures."""

    def __init__(self, root: Path, *, read_only_roots: tuple[Path, ...] = ()) -> None:
        self.root = root.resolve()
        self.read_only_roots = tuple(path.resolve() for path in read_only_roots)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def create_run(self, status: ValidationRunStatus) -> None:
        directory = self.root / "runs" / status.result_id
        directory.mkdir(parents=True, exist_ok=False)
        self.write_status(status)

    def write_status(self, status: ValidationRunStatus) -> None:
        self._write_json(self.root / "runs" / status.result_id / "status.json", status.model_dump(mode="json"))

    def append_result(self, result: ValidationResult, bundle: VRunBundle) -> None:
        directory = self.root / "runs" / result.result_id
        result_path = directory / "result.json"
        if result_path.exists():
            raise FileExistsError(f"validation result is append-only: {result.result_id}")
        self._write_json(result_path, result.model_dump(mode="json"))
        self._write_json(directory / "replay_bundle.json", bundle.model_dump(mode="json"))

    def list_results(self, case_id: str | None = None) -> tuple[ValidationResult, ...]:
        results: list[ValidationResult] = []
        for root in (*self.read_only_roots, self.root):
            for path in sorted((root / "runs").glob("*/result.json")):
                result = ValidationResult.model_validate_json(path.read_text(encoding="utf-8"))
                if case_id is None or result.case_id == case_id:
                    results.append(result)
        return tuple(sorted(results, key=lambda item: (item.created_at, item.result_id)))

    def result(self, result_id: str) -> ValidationResult:
        return ValidationResult.model_validate_json(self._find(result_id, "result.json").read_text(encoding="utf-8"))

    def bundle(self, result_id: str) -> VRunBundle:
        return VRunBundle.model_validate_json(self._find(result_id, "replay_bundle.json").read_text(encoding="utf-8"))

    def status(self, result_id: str) -> ValidationRunStatus:
        return ValidationRunStatus.model_validate_json(self._find(result_id, "status.json").read_text(encoding="utf-8"))

    def _find(self, result_id: str, name: str) -> Path:
        if not result_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-" for char in result_id):
            raise ValidationArtifactNotFound(result_id)
        for root in (self.root, *self.read_only_roots):
            path = root / "runs" / result_id / name
            if path.is_file():
                return path
        raise ValidationArtifactNotFound(result_id)

    def _write_json(self, path: Path, value: object) -> None:
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
            temporary.replace(path)


@dataclass
class _Runtime:
    case: ValidationCase
    status: ValidationRunStatus
    cancel: Event
    thread: Thread | None = None


class ValidationOrchestrator:
    """Runs only declared case IDs; browser disconnects do not own execution."""

    def __init__(self, repository: ValidationRepository, *, execution_yield_seconds: float = 0.035) -> None:
        self.repository = repository
        self.execution_yield_seconds = execution_yield_seconds
        self._lock = RLock()
        self._runtimes: dict[str, _Runtime] = {}

    def library(self) -> tuple[ValidationLibraryRecord, ...]:
        records = []
        for case in CASES:
            history = self.repository.list_results(case.case_id)
            records.append(ValidationLibraryRecord(case=case, latest_result=history[-1] if history else None, history_count=len(history)))
        return tuple(records)

    def start(self, case_id: str, *, result_id: str | None = None) -> ValidationRunStatus:
        case = CASES_BY_ID[case_id]
        result_id = result_id or f"validation-{uuid.uuid4().hex}"
        status = ValidationRunStatus(result_id=result_id, case_id=case_id, lifecycle=ValidationLifecycle.CREATED, physical_tick=0, final_tick=case.default_final_tick, detail="Validation run accepted.", terminal=False)
        runtime = _Runtime(case=case, status=status, cancel=Event())
        self.repository.create_run(status)
        with self._lock:
            self._runtimes[result_id] = runtime
        runtime.thread = Thread(target=self._execute, args=(runtime,), name=f"uc-validation-{result_id}", daemon=True)
        runtime.thread.start()
        return status

    def start_group(self, group_id: str) -> tuple[ValidationRunStatus, ...]:
        cases = tuple(case for case in CASES if case.group_id == group_id)
        if not cases:
            raise KeyError(group_id)
        return tuple(self.start(case.case_id) for case in cases)

    def cancel(self, result_id: str) -> ValidationRunStatus:
        runtime = self._runtime(result_id)
        runtime.cancel.set()
        self._update(runtime, ValidationLifecycle.CANCEL_REQUESTED, runtime.status.physical_tick, "Cancellation requested; partial evidence will be retained.")
        return runtime.status

    def status(self, result_id: str) -> ValidationRunStatus:
        try:
            return self._runtime(result_id).status
        except ValidationArtifactNotFound:
            return self.repository.status(result_id)

    def wait(self, result_id: str, timeout: float | None = None) -> ValidationRunStatus:
        runtime = self._runtime(result_id)
        if runtime.thread:
            runtime.thread.join(timeout)
        return runtime.status

    def _runtime(self, result_id: str) -> _Runtime:
        with self._lock:
            try:
                return self._runtimes[result_id]
            except KeyError as exc:
                raise ValidationArtifactNotFound(result_id) from exc

    def _execute(self, runtime: _Runtime) -> None:
        try:
            def progress(lifecycle: ValidationLifecycle, tick: int, detail: str) -> None:
                self._update(runtime, lifecycle, tick, detail)
                if lifecycle == ValidationLifecycle.EXECUTING and self.execution_yield_seconds:
                    time.sleep(self.execution_yield_seconds)

            result, bundle = execute_case(runtime.case, result_id=runtime.status.result_id, code_commit=current_code_commit(), cancelled=runtime.cancel.is_set, progress=progress)
            self.repository.append_result(result, bundle)
            terminal = ValidationLifecycle.CANCELLED if result.status.value == "cancelled" else ValidationLifecycle.COMPLETE if result.status.value == "passed" else ValidationLifecycle.FAILED
            self._update(runtime, terminal, bundle.run.end_tick, result.observed_result_summary, terminal=True)
        except Exception as exc:
            self._update(runtime, ValidationLifecycle.FAILED, runtime.status.physical_tick, f"Validation execution failed: {exc}", terminal=True)

    def _update(self, runtime: _Runtime, lifecycle: ValidationLifecycle, tick: int, detail: str, *, terminal: bool = False) -> None:
        runtime.status = runtime.status.model_copy(update={"lifecycle": lifecycle, "physical_tick": tick, "detail": detail, "terminal": terminal})
        self.repository.write_status(runtime.status)
