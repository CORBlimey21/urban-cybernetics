"""Synthetic experiment semantics layered over pinned Boreenmanna OSM evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping, Self

from .adapter import adapt_osm_like
from .model import (
    CompilerEvidenceBundle,
    SourceField,
    SourceNetworkEvidence,
    SourceRecord,
    canonical_json,
    stable_hash,
)
from .osm_xml import (
    CorkJunctionEvidencePackage,
    CorkJunctionMilestoneRun,
    compile_boreenmanna_milestone,
    reviewed_candidate_config,
)
from .pipeline import CompilationResult, compile_network


SYNTHETIC_EXPERIMENT_SCHEMA_VERSION = "uc.synthetic-junction-experiment.v1"
BOREENMANNA_EXPERIMENT_PACKAGE_VERSION = "uc.boreenmanna-experiment-compilation.v1"
SYNTHETIC_ACTOR_SOURCE_ID = "urban-cybernetics:synthetic-boreenmanna-policy:v1"


class SyntheticExperimentIntegrityError(ValueError):
    """Raised when authored experiment evidence fails deterministic validation."""


@dataclass(frozen=True, slots=True)
class SyntheticExperimentItem:
    """One explicitly synthetic compiler source record and its audit boundary."""

    artifact_id: str
    record_type: str
    scope: str
    target_field: str
    value_json: str
    unit: str
    actor_source_id: str
    reason: str
    target_movement_id: str | None = None
    classification: str = "synthetic_experiment"
    schema_version: str = SYNTHETIC_EXPERIMENT_SCHEMA_VERSION
    item_hash: str = ""

    def __post_init__(self) -> None:
        for name in (
            "artifact_id",
            "record_type",
            "scope",
            "target_field",
            "unit",
            "actor_source_id",
            "reason",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise SyntheticExperimentIntegrityError(f"{name} must be non-empty")
        if self.classification != "synthetic_experiment":
            raise SyntheticExperimentIntegrityError(
                "synthetic item classification must be synthetic_experiment"
            )
        if self.schema_version != SYNTHETIC_EXPERIMENT_SCHEMA_VERSION:
            raise SyntheticExperimentIntegrityError("unsupported synthetic item schema")
        object.__setattr__(self, "value_json", canonical_json(json.loads(self.value_json)))
        expected = stable_hash("synthetic-experiment-item", self._payload())
        if self.item_hash and self.item_hash != expected:
            raise SyntheticExperimentIntegrityError("synthetic item hash mismatch")
        object.__setattr__(self, "item_hash", expected)

    @classmethod
    def create(
        cls,
        *,
        artifact_id: str,
        record_type: str,
        scope: str,
        target_field: str,
        value: object,
        unit: str,
        reason: str,
        target_movement_id: str | None = None,
        actor_source_id: str = SYNTHETIC_ACTOR_SOURCE_ID,
    ) -> Self:
        return cls(
            artifact_id=artifact_id,
            record_type=record_type,
            scope=scope,
            target_field=target_field,
            value_json=canonical_json(value),
            unit=unit,
            actor_source_id=actor_source_id,
            reason=reason,
            target_movement_id=target_movement_id,
        )

    @property
    def value(self) -> object:
        return json.loads(self.value_json)

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "record_type": self.record_type,
            "scope": self.scope,
            "target_field": self.target_field,
            "value": self.value,
            "unit": self.unit,
            "actor_source_id": self.actor_source_id,
            "reason": self.reason,
            "target_movement_id": self.target_movement_id,
            "classification": self.classification,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "item_hash": self.item_hash}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            artifact_id=str(payload["artifact_id"]),
            record_type=str(payload["record_type"]),
            scope=str(payload["scope"]),
            target_field=str(payload["target_field"]),
            value_json=canonical_json(payload["value"]),
            unit=str(payload["unit"]),
            actor_source_id=str(payload["actor_source_id"]),
            reason=str(payload["reason"]),
            target_movement_id=(
                None
                if payload.get("target_movement_id") is None
                else str(payload["target_movement_id"])
            ),
            classification=str(payload["classification"]),
            schema_version=str(payload["schema_version"]),
            item_hash=str(payload.get("item_hash", "")),
        )

    def source_record_payload(self) -> dict[str, object]:
        fields = self.value
        if not isinstance(fields, dict):
            raise SyntheticExperimentIntegrityError(
                "compiler-backed synthetic items must contain an object value"
            )
        return {
            "evidence_id": f"synthetic-evidence:{self.item_hash}",
            "type": self.record_type,
            "id": self.artifact_id,
            "fields": {
                **fields,
                "evidence_origin": "synthetic_experiment",
                "synthetic_item_hash": self.item_hash,
                "synthetic_actor_source_id": self.actor_source_id,
                "synthetic_schema_version": self.schema_version,
            },
        }


@dataclass(frozen=True, slots=True)
class SyntheticBoreenmannaDossier:
    """Hash-bound synthetic control and queue semantics, never OSM evidence."""

    source_file_sha256: str
    source_parsed_content_hash: str
    extraction_hash: str
    reviewed_road_compilation_identity_hash: str
    items: tuple[SyntheticExperimentItem, ...]
    schema_version: str = SYNTHETIC_EXPERIMENT_SCHEMA_VERSION
    dossier_hash: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SYNTHETIC_EXPERIMENT_SCHEMA_VERSION:
            raise SyntheticExperimentIntegrityError("unsupported dossier schema")
        ordered = tuple(sorted(self.items, key=lambda item: item.artifact_id))
        if len({item.artifact_id for item in ordered}) != len(ordered):
            raise SyntheticExperimentIntegrityError("duplicate synthetic artifact ID")
        object.__setattr__(self, "items", ordered)
        expected = stable_hash("synthetic-boreenmanna-dossier", self._payload())
        if self.dossier_hash and self.dossier_hash != expected:
            raise SyntheticExperimentIntegrityError("synthetic dossier hash mismatch")
        object.__setattr__(self, "dossier_hash", expected)

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_file_sha256": self.source_file_sha256,
            "source_parsed_content_hash": self.source_parsed_content_hash,
            "extraction_hash": self.extraction_hash,
            "reviewed_road_compilation_identity_hash": (
                self.reviewed_road_compilation_identity_hash
            ),
            "items": [item.to_dict() for item in self.items],
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "dossier_hash": self.dossier_hash}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            source_file_sha256=str(payload["source_file_sha256"]),
            source_parsed_content_hash=str(payload["source_parsed_content_hash"]),
            extraction_hash=str(payload["extraction_hash"]),
            reviewed_road_compilation_identity_hash=str(
                payload["reviewed_road_compilation_identity_hash"]
            ),
            items=tuple(
                SyntheticExperimentItem.from_dict(item)
                for item in payload.get("items", [])  # type: ignore[arg-type]
            ),
            schema_version=str(payload["schema_version"]),
            dossier_hash=str(payload.get("dossier_hash", "")),
        )

    def source_records(self) -> tuple[SourceRecord, ...]:
        compiler_record_types = {
            "turn",
            "lane_group",
            "signal_controller",
            "signal_stage",
            "signal_binding",
        }
        payload = {
            "network_id": f"synthetic-boreenmanna:{self.dossier_hash}",
            "records": [
                item.source_record_payload()
                for item in self.items
                if item.record_type in compiler_record_types
            ],
        }
        return adapt_osm_like(payload).records


@dataclass(frozen=True, slots=True)
class BoreenmannaExperimentCompilationPackage:
    """Round-trip package preserving all three compiler dispositions."""

    base_package: CorkJunctionEvidencePackage
    dossier: SyntheticBoreenmannaDossier
    synthetic_source: SourceNetworkEvidence
    synthetic_bundle: CompilerEvidenceBundle
    schema_version: str = BOREENMANNA_EXPERIMENT_PACKAGE_VERSION
    package_hash: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != BOREENMANNA_EXPERIMENT_PACKAGE_VERSION:
            raise SyntheticExperimentIntegrityError(
                "unsupported Boreenmanna experiment package schema"
            )
        if self.dossier.source_file_sha256 != self.base_package.source.file_sha256:
            raise SyntheticExperimentIntegrityError("dossier source file mismatch")
        if self.dossier.extraction_hash != self.base_package.extraction.extraction_hash:
            raise SyntheticExperimentIntegrityError("dossier extraction mismatch")
        if self.synthetic_bundle.input_evidence_hash != self.synthetic_source.evidence_hash:
            raise SyntheticExperimentIntegrityError("synthetic source/bundle mismatch")
        expected = stable_hash("boreenmanna-experiment-compilation", self._payload())
        if self.package_hash and self.package_hash != expected:
            raise SyntheticExperimentIntegrityError(
                "Boreenmanna experiment package hash mismatch"
            )
        object.__setattr__(self, "package_hash", expected)

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "base_package": self.base_package.to_dict(),
            "dossier": self.dossier.to_dict(),
            "synthetic_source": self.synthetic_source.to_dict(),
            "synthetic_bundle": self.synthetic_bundle.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "package_hash": self.package_hash}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            base_package=CorkJunctionEvidencePackage.from_dict(
                payload["base_package"]  # type: ignore[arg-type]
            ),
            dossier=SyntheticBoreenmannaDossier.from_dict(
                payload["dossier"]  # type: ignore[arg-type]
            ),
            synthetic_source=_source_network_from_dict(
                payload["synthetic_source"]  # type: ignore[arg-type]
            ),
            synthetic_bundle=CompilerEvidenceBundle.from_dict(
                payload["synthetic_bundle"]  # type: ignore[arg-type]
            ),
            schema_version=str(payload["schema_version"]),
            package_hash=str(payload.get("package_hash", "")),
        )

    @classmethod
    def from_json(cls, serialised: str) -> Self:
        payload = json.loads(serialised)
        if not isinstance(payload, dict):
            raise SyntheticExperimentIntegrityError("experiment package must be an object")
        return cls.from_dict(payload)


@dataclass(frozen=True, slots=True)
class BoreenmannaExperimentCompilation:
    base: CorkJunctionMilestoneRun
    dossier: SyntheticBoreenmannaDossier
    synthetic_source: SourceNetworkEvidence
    synthetic_result: CompilationResult
    package: BoreenmannaExperimentCompilationPackage


def build_boreenmanna_synthetic_dossier(
    base: CorkJunctionMilestoneRun,
) -> SyntheticBoreenmannaDossier:
    """Author a simple synchronized plan and explicit two-lane partitions."""

    reviewed = base.reviewed_candidate_result
    graph = reviewed.resolved_graph
    permitted = tuple(item for item in graph.movements if item.permitted)
    link_by_id = {item.link_id: item for item in graph.links}
    control_node_ids = set(base.package.extraction.signal_node_ids)
    for node_id in {item.node_id for item in permitted}:
        node_movements = tuple(item for item in permitted if item.node_id == node_id)
        downstream_classes = {
            link_by_id[item.downstream_link_id].road_class
            for item in node_movements
        }
        if len(node_movements) >= 2 and len(downstream_classes) >= 2:
            control_node_ids.add(node_id)
    movement_by_node = {
        node_id: tuple(
            sorted(
                (item for item in permitted if item.node_id == node_id),
                key=lambda item: item.movement_id,
            )
        )
        for node_id in sorted(control_node_ids, key=int)
    }
    items: list[SyntheticExperimentItem] = []
    items.append(
        SyntheticExperimentItem.create(
            artifact_id="synthetic-experiment-config:tick-duration",
            record_type="experiment_configuration",
            scope="synthetic_boreenmanna_experiment",
            target_field="tick_duration_seconds",
            value={"tick_duration_seconds": 2.0},
            unit="seconds_per_tick",
            reason="two-second experimental tick exposes both multi-packet two-lane service and sub-unit one-lane service without altering the frozen kernel",
        )
    )
    for node_id in sorted(control_node_ids, key=int):
        movements = movement_by_node[node_id]
        if not movements:
            raise SyntheticExperimentIntegrityError(
                f"signal node {node_id} has no executable movement"
            )
        controller_id = f"synthetic-controller:{node_id}"
        stage_ids = tuple(
            f"synthetic-stage:{node_id}:{name}"
            for name in (
                "south-link-green",
                "clearance-one",
                "boreenmanna-green",
                "clearance-two",
            )
        )
        controlled = tuple(item.movement_id for item in movements)
        items.append(
            SyntheticExperimentItem.create(
                artifact_id=controller_id,
                record_type="signal_controller",
                scope=f"control_point:{node_id}",
                target_field="fixed_time_controller",
                value={
                    "node_id": node_id,
                    "signalized": True,
                    "controlled_movement_ids": list(controlled),
                    "stage_ids": list(stage_ids),
                    "cycle_ticks": 40,
                    "offset_ticks": 0,
                },
                unit="ticks",
                reason="synchronized architecture-exercise controller; not observed OSM timing",
            )
        )
        south_link_movements = tuple(
            item.movement_id
            for item in movements
            if link_by_id[item.downstream_link_id].road_class
            in {"trunk", "trunk_link"}
        )
        boreenmanna_movements = tuple(
            item.movement_id
            for item in movements
            if item.movement_id not in south_link_movements
        )
        stage_definitions = (
            (stage_ids[0], 18, south_link_movements),
            (stage_ids[1], 2, ()),
            (stage_ids[2], 15, boreenmanna_movements),
            (stage_ids[3], 5, ()),
        )
        for stage_id, duration, open_movements in stage_definitions:
            items.append(
                SyntheticExperimentItem.create(
                    artifact_id=stage_id,
                    record_type="signal_stage",
                    scope=f"controller:{controller_id}",
                    target_field="ordered_stage",
                    value={
                        "controller_id": controller_id,
                        "duration_ticks": duration,
                        "permitted_movement_ids": list(open_movements),
                    },
                    unit="ticks",
                    reason="simple two-road fixed-time programme with explicit clearance intervals",
                )
            )
        for movement in movements:
            group_id = (
                f"synthetic-signal-group:{node_id}:"
                f"{stable_hash('signal-movement', movement.movement_id)[:12]}"
            )
            items.append(
                SyntheticExperimentItem.create(
                    artifact_id=f"synthetic-binding:{node_id}:{stable_hash('movement', movement.movement_id)[:16]}",
                    record_type="signal_binding",
                    scope=f"controller:{controller_id}",
                    target_field="movement_to_signal_group",
                    value={
                        "controller_id": controller_id,
                        "movement_id": movement.movement_id,
                        "signal_group_id": group_id,
                    },
                    unit="binding",
                    reason="synthetic movement-to-head association required by the executable signal gate",
                    target_movement_id=movement.movement_id,
                )
            )

    movements_by_approach: dict[tuple[str, str], list[object]] = {}
    for movement in permitted:
        movements_by_approach.setdefault(
            (movement.node_id, movement.upstream_link_id), []
        ).append(movement)
    for (node_id, incoming), movements in sorted(movements_by_approach.items()):
        link = link_by_id[incoming]
        if len(movements) != 2 or link.lane_count is None or link.lane_count < 2:
            continue
        for ordinal, movement in enumerate(
            sorted(movements, key=lambda item: item.movement_id), start=1
        ):
            group_id = f"synthetic-lane-group:{node_id}:{stable_hash('incoming', incoming)[:10]}:{ordinal}"
            items.append(
                SyntheticExperimentItem.create(
                    artifact_id=group_id,
                    record_type="lane_group",
                    scope=f"approach:{node_id}:{incoming}",
                    target_field="lane_to_movement_queue_partition",
                    value={
                        "node_id": node_id,
                        "incoming_link_id": incoming,
                        "allowed_movement_ids": [movement.movement_id],
                        "capacity_per_tick": 1,
                        "queue_partition": True,
                    },
                    unit="unit_packets_per_tick",
                    reason="synthetic one-lane-per-movement partition used only for representation comparison",
                    target_movement_id=movement.movement_id,
                )
            )
    return SyntheticBoreenmannaDossier(
        source_file_sha256=base.package.source.file_sha256,
        source_parsed_content_hash=base.package.source.parsed_content_hash,
        extraction_hash=base.package.extraction.extraction_hash,
        reviewed_road_compilation_identity_hash=(
            base.reviewed_candidate_result.evidence_bundle.compilation_identity_hash
        ),
        items=tuple(items),
    )


def compile_boreenmanna_experiment(
    path: str | Path,
) -> BoreenmannaExperimentCompilation:
    """Retain both refusals and add a separately authored executable third pass."""

    base = compile_boreenmanna_milestone(path)
    dossier = build_boreenmanna_synthetic_dossier(base)
    synthetic_source = SourceNetworkEvidence(
        network_id=f"{base.compiler_source.network_id}:synthetic-experiment-v1",
        records=base.compiler_source.records + dossier.source_records(),
    )
    config = replace(
        reviewed_candidate_config(),
        enable_explicit_lane_group_partitions=True,
        tick_duration_seconds=2.0,
    )
    result = compile_network(
        synthetic_source,
        config=config,
        overrides=base.package.reviewed_overrides,
    )
    package = BoreenmannaExperimentCompilationPackage(
        base_package=base.package,
        dossier=dossier,
        synthetic_source=synthetic_source,
        synthetic_bundle=result.evidence_bundle,
    )
    return BoreenmannaExperimentCompilation(
        base=base,
        dossier=dossier,
        synthetic_source=synthetic_source,
        synthetic_result=result,
        package=package,
    )


def _source_network_from_dict(payload: Mapping[str, object]) -> SourceNetworkEvidence:
    records = []
    for record in payload.get("records", []):  # type: ignore[assignment]
        records.append(
            SourceRecord(
                evidence_id=str(record["evidence_id"]),
                record_type=str(record["record_type"]),
                source_id=str(record["source_id"]),
                fields=tuple(
                    SourceField.create(
                        str(field["evidence_id"]),
                        str(field["name"]),
                        field["raw_value"],
                    )
                    for field in record.get("fields", [])
                ),
            )
        )
    return SourceNetworkEvidence(
        network_id=str(payload["network_id"]),
        records=tuple(records),
        schema_version=str(payload["schema_version"]),
    )
