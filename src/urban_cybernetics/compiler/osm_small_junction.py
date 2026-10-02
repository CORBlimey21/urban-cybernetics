# SPDX-License-Identifier: MPL-2.0
"""Fixture-backed unsignalised-junction selection and compiler smoke slice."""

from __future__ import annotations

import json
import tracemalloc
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter, process_time
from typing import Mapping, Self

from urban_cybernetics.core import DemandDeclaration

from .model import CompilerEvidenceBundle, canonical_json, stable_hash
from .osm_xml import (
    OSMFileEvidence,
    OSMJunctionExtraction,
    OSMJunctionExtractionConfig,
    extract_operational_junction,
    extraction_to_source_evidence,
    parse_osm_xml,
    reviewed_candidate_config,
    source_strict_config,
)
from .pipeline import CompilationResult, compile_network


SMALL_JUNCTION_SELECTION_SCHEMA = "uc.small-osm-junction-selection.v1"
SMALL_JUNCTION_PACKAGE_SCHEMA = "uc.small-osm-junction-package.v1"


class SmallJunctionIntegrityError(ValueError):
    """Raised for malformed selection or package evidence."""


@dataclass(frozen=True, slots=True)
class SmallJunctionSelectionContract:
    selection_id: str = "simple-unsignalized-diverge-v1"
    required_characteristics: tuple[str, ...] = (
        "one incoming and two outgoing vehicle ways",
        "complete oneway directionality",
        "lane counts and maxspeed on every retained way",
        "no traffic signals or fixed-time controller",
        "no roundabout, conditional access, or reversible lanes",
        "approach geometry long enough for finite storage",
    )
    source_status: str = "synthetic_osm_fixture_pending_second_pinned_real_export"
    current_export_finding: str = (
        "the attached Boreenmanna export has no self-contained multi-movement "
        "junction whose retained approaches avoid signal-control evidence"
    )
    schema_version: str = SMALL_JUNCTION_SELECTION_SCHEMA

    @property
    def selection_hash(self) -> str:
        return stable_hash("small-junction-selection", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "selection_id": self.selection_id,
            "required_characteristics": list(self.required_characteristics),
            "source_status": self.source_status,
            "current_export_finding": self.current_export_finding,
        }


@dataclass(frozen=True, slots=True)
class SmallJunctionPackage:
    selection: SmallJunctionSelectionContract
    source: OSMFileEvidence
    extraction: OSMJunctionExtraction
    strict_bundle: CompilerEvidenceBundle
    reviewed_bundle: CompilerEvidenceBundle
    smoke_summary_json: str
    performance_summary_json: str
    schema_version: str = SMALL_JUNCTION_PACKAGE_SCHEMA
    package_hash: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SMALL_JUNCTION_PACKAGE_SCHEMA:
            raise SmallJunctionIntegrityError("unsupported small-junction package")
        object.__setattr__(
            self,
            "smoke_summary_json",
            canonical_json(json.loads(self.smoke_summary_json)),
        )
        object.__setattr__(
            self,
            "performance_summary_json",
            canonical_json(json.loads(self.performance_summary_json)),
        )
        if self.extraction.source_parsed_content_hash != self.source.parsed_content_hash:
            raise SmallJunctionIntegrityError("small-junction source mismatch")
        expected = stable_hash(
            "small-junction-package",
            self._deterministic_payload(),
        )
        if self.package_hash and self.package_hash != expected:
            raise SmallJunctionIntegrityError("small-junction package hash mismatch")
        object.__setattr__(self, "package_hash", expected)

    @property
    def smoke_summary(self) -> dict[str, object]:
        return json.loads(self.smoke_summary_json)

    @property
    def performance_summary(self) -> dict[str, object]:
        return json.loads(self.performance_summary_json)

    def _deterministic_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "selection": self.selection.to_dict(),
            "selection_hash": self.selection.selection_hash,
            "source": self.source.to_dict(),
            "extraction": self.extraction.to_dict(),
            "strict_bundle": self.strict_bundle.to_dict(),
            "reviewed_bundle": self.reviewed_bundle.to_dict(),
            "smoke_summary": self.smoke_summary,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self._deterministic_payload(),
            "performance_summary": self.performance_summary,
            "package_hash": self.package_hash,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        selection_payload = payload["selection"]  # type: ignore[assignment]
        selection = SmallJunctionSelectionContract(
            selection_id=str(selection_payload["selection_id"]),
            required_characteristics=tuple(
                str(item) for item in selection_payload["required_characteristics"]
            ),
            source_status=str(selection_payload["source_status"]),
            current_export_finding=str(selection_payload["current_export_finding"]),
            schema_version=str(selection_payload["schema_version"]),
        )
        if payload.get("selection_hash") != selection.selection_hash:
            raise SmallJunctionIntegrityError("small-junction selection hash mismatch")
        return cls(
            selection=selection,
            source=OSMFileEvidence.from_dict(payload["source"]),  # type: ignore[arg-type]
            extraction=OSMJunctionExtraction.from_dict(
                payload["extraction"]  # type: ignore[arg-type]
            ),
            strict_bundle=CompilerEvidenceBundle.from_dict(
                payload["strict_bundle"]  # type: ignore[arg-type]
            ),
            reviewed_bundle=CompilerEvidenceBundle.from_dict(
                payload["reviewed_bundle"]  # type: ignore[arg-type]
            ),
            smoke_summary_json=canonical_json(payload["smoke_summary"]),
            performance_summary_json=canonical_json(payload["performance_summary"]),
            schema_version=str(payload["schema_version"]),
            package_hash=str(payload.get("package_hash", "")),
        )

    @classmethod
    def from_json(cls, serialised: str) -> Self:
        payload = json.loads(serialised)
        if not isinstance(payload, dict):
            raise SmallJunctionIntegrityError("small-junction JSON must be an object")
        return cls.from_dict(payload)


@dataclass(frozen=True, slots=True)
class SmallJunctionRun:
    strict_result: CompilationResult
    reviewed_result: CompilationResult
    package: SmallJunctionPackage


def compile_small_unsignalized_fixture(path: str | Path) -> SmallJunctionRun:
    source = parse_osm_xml(path)
    config = OSMJunctionExtractionConfig(
        boundary_id="simple-unsignalized-diverge-fixture-v1",
        seed_way_ids=("1001", "1002", "1003"),
        explicit_include_way_ids=("1001", "1002", "1003"),
        included_highway_classes=("secondary",),
        retain_crossings_for_audit=False,
        minimum_approach_length_metres=50.0,
    )
    extraction = extract_operational_junction(source, config)
    compiler_source, uturn_ids = extraction_to_source_evidence(
        source,
        extraction,
        network_id="osm-fixture:simple-unsignalized-diverge-v1",
    )
    if uturn_ids:
        raise SmallJunctionIntegrityError("simple diverge unexpectedly contains U-turns")
    strict = compile_network(compiler_source, config=source_strict_config())
    reviewed = compile_network(
        compiler_source,
        config=reviewed_candidate_config(),
    )
    executable = reviewed.require_executable()
    incoming = next(
        item.link_id for item in executable.resolved_links if item.tail_node_id == "100"
    )
    north = next(
        item.link_id for item in executable.resolved_links if item.head_node_id == "300"
    )
    south = next(
        item.link_id for item in executable.resolved_links if item.head_node_id == "400"
    )
    demands = (
        DemandDeclaration("small-fixture:north:1", 0, (incoming, north)),
        DemandDeclaration("small-fixture:south:1", 0, (incoming, south)),
        DemandDeclaration("small-fixture:north:2", 1, (incoming, north)),
        DemandDeclaration("small-fixture:south:2", 1, (incoming, south)),
    )
    tracemalloc.start()
    wall_start = perf_counter()
    cpu_start = process_time()
    engine, event_payload = _execute_small_smoke(executable, demands)
    cpu_seconds = process_time() - cpu_start
    wall_seconds = perf_counter() - wall_start
    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    replay_start = perf_counter()
    replay_engine, replay_payload = _execute_small_smoke(executable, demands)
    replay_seconds = perf_counter() - replay_start
    smoke = {
        "demand_count": len(demands),
        "completed_count": len(engine.completed_packet_ids),
        "terminal_tick": engine.current_tick,
        "event_count": len(engine.event_log),
        "event_log_hash": stable_hash("small-junction-events", event_payload),
        "serialized_evidence_bytes": len(canonical_json(event_payload).encode("utf-8")),
        "replay_passed": event_payload == replay_payload,
        "conservation_passed": engine.check_conservation(),
        "event_cache_consistency_passed": engine.check_event_cache_consistency(),
        "count_consistency_passed": engine.count_consistency_report().is_consistent,
        "replay_conservation_passed": replay_engine.check_conservation(),
        "representation": "shared_link_fifo",
        "representation_reason": (
            "OSM-like fixture provides total lanes but no lane-to-turn allocation; "
            "only the conservative shared representation is claimed"
        ),
    }
    package = SmallJunctionPackage(
        selection=SmallJunctionSelectionContract(),
        source=source,
        extraction=extraction,
        strict_bundle=strict.evidence_bundle,
        reviewed_bundle=reviewed.evidence_bundle,
        smoke_summary_json=canonical_json(smoke),
        performance_summary_json=canonical_json(
            {
                "measurement_class": "machine_dependent",
                "wall_clock_seconds": wall_seconds,
                "cpu_seconds": cpu_seconds,
                "peak_memory_bytes": peak_memory,
                "replay_wall_clock_seconds": replay_seconds,
            }
        ),
    )
    return SmallJunctionRun(strict, reviewed, package)


def write_small_junction_package(
    run: SmallJunctionRun,
    output_path: str | Path,
) -> Path:
    """Write the validated package without changing its deterministic identity."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run.package.to_json(), encoding="utf-8")
    return path


def _execute_small_smoke(executable, demands):
    engine = executable.build_loading_engine()
    for demand in demands:
        engine.instantiate(demand)
    for _ in range(80):
        engine.step()
    event_payload = [
        (
            item.sequence_number,
            item.packet_id,
            item.event_type.value,
            item.entity_id,
            item.physical_tick,
        )
        for item in engine.event_log
    ]
    return engine, event_payload
