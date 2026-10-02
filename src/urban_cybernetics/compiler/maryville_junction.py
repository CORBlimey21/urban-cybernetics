# SPDX-License-Identifier: MPL-2.0
"""Pinned real unsignalised Maryville--Blackrock Road Paper 1 case."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping, Self

from urban_cybernetics.core import DemandDeclaration

from .adapter import normalize_source
from .model import CompilerOverride, SourceNetworkEvidence, canonical_json, stable_hash
from .osm_xml import (
    CorkJunctionEvidencePackage,
    OSMJunctionExtraction,
    OSMJunctionExtractionConfig,
    OSMReviewedAssumption,
    extraction_to_source_evidence,
    extract_operational_junction,
    parse_osm_xml,
    reviewed_candidate_config,
    source_strict_config,
)
from .pipeline import CompilationResult, compile_network


MARYVILLE_JUNCTION_PACKAGE_VERSION = "uc.maryville-blackrock-road-junction.v1"
MARYVILLE_NETWORK_ID = "osm:maryville-blackrock-road-t-junction-v1"
MARYVILLE_JUNCTION_NODE_ID = "7842268"
MARYVILLE_WAY_ID = "5317316"
BLACKROCK_ROAD_WAY_ID = "477599192"


class MaryvilleJunctionIntegrityError(ValueError):
    """Raised when the pinned real-junction package is inconsistent."""


def maryville_extraction_config() -> OSMJunctionExtractionConfig:
    """Return the reviewed three-approach operational boundary.

    The source Blackrock Road way continues east through an unrelated
    signalised crossing. The explicit source-node intervals preserve the raw
    way while retaining only the unsignalised T-junction approaches.
    """

    return OSMJunctionExtractionConfig(
        boundary_id="maryville-blackrock-road-t-junction-v1",
        seed_way_ids=(MARYVILLE_WAY_ID, BLACKROCK_ROAD_WAY_ID),
        explicit_include_way_ids=(MARYVILLE_WAY_ID, BLACKROCK_ROAD_WAY_ID),
        included_highway_classes=("tertiary",),
        explicit_way_node_intervals=(
            (MARYVILLE_WAY_ID, "10980457806", MARYVILLE_JUNCTION_NODE_ID),
            (BLACKROCK_ROAD_WAY_ID, "7842270", "10979271057"),
        ),
        include_service_roads=False,
        retain_crossings_for_audit=True,
        split_at_crossings=False,
        minimum_approach_length_metres=35.0,
        approach_depth_hops=0,
    )


def maryville_reviewed_config():
    """Add only explicit model priors missing from this real OSM source."""

    base = reviewed_candidate_config()
    return replace(
        base,
        lane_defaults=tuple(sorted((*base.lane_defaults, ("tertiary", 1)))),
        speed_kph_defaults=tuple(
            sorted((*base.speed_kph_defaults, ("tertiary", 50.0)))
        ),
        capacity_per_lane_defaults=tuple(
            sorted((*base.capacity_per_lane_defaults, ("tertiary", 1500.0)))
        ),
    )


def _reviewed_assumptions() -> tuple[OSMReviewedAssumption, ...]:
    common = {
        "actor": "paper1-reviewed-maryville-policy:v1",
        "source": "explicit uncalibrated model configuration",
    }
    return (
        OSMReviewedAssumption.create(
            assumption_id="maryville-review:tertiary-capacity",
            target_scope="road_class:tertiary",
            target_field="capacity_veh_per_hour_per_lane",
            selected_value=1500.0,
            unit="vehicles_per_hour_per_lane",
            reason="OSM does not encode model saturation capacity",
            rule_id="link.capacity.road-class-default",
            **common,
        ),
        OSMReviewedAssumption.create(
            assumption_id="maryville-review:jam-density",
            target_scope="all_retained_links",
            target_field="jam_density_veh_per_km_per_lane",
            selected_value=150.0,
            unit="vehicles_per_kilometre_per_lane",
            reason="OSM does not encode model jam density",
            rule_id="link.storage.observed-or-default",
            **common,
        ),
        OSMReviewedAssumption.create(
            assumption_id="maryville-review:backward-wave-speed",
            target_scope="all_retained_links",
            target_field="backward_wave_speed_mps",
            selected_value=5.0,
            unit="metres_per_second",
            reason="OSM does not encode backward kinematic-wave speed",
            rule_id="link.storage.observed-or-default",
            **common,
        ),
        OSMReviewedAssumption.create(
            assumption_id="maryville-review:shared-fifo",
            target_scope=f"junction:{MARYVILLE_JUNCTION_NODE_ID}",
            target_field="lane_group_representation",
            selected_value="shared_link_fifo",
            unit="representation_policy",
            reason=(
                "total lanes are observed but lane-to-turn allocation is absent; "
                "use the conservative shared representation"
            ),
            rule_id="lane-group.shared-fallback",
            **common,
        ),
        OSMReviewedAssumption.create(
            assumption_id="maryville-review:tick-duration",
            target_scope="runtime",
            target_field="tick_duration_seconds",
            selected_value=1.0,
            unit="seconds",
            reason="model discretisation is configured rather than observed in OSM",
            rule_id="compiler.config.tick-duration",
            **common,
        ),
    )


def _uturn_overrides(movement_ids: tuple[str, ...]) -> tuple[CompilerOverride, ...]:
    return tuple(
        CompilerOverride.create(
            override_id=f"maryville-review:no-uturn:{ordinal:02d}",
            target_artifact_id=movement_id,
            target_field="permitted",
            replacement_value=False,
            actor="paper1-reviewed-maryville-policy:v1",
            source="explicit reviewed movement policy",
            reason=(
                "prohibit immediate reversal for this ordinary T-junction experiment "
                "because OSM supplies no affirmative U-turn semantics"
            ),
            precedence=100,
        )
        for ordinal, movement_id in enumerate(movement_ids)
    )


@dataclass(frozen=True, slots=True)
class MaryvilleJunctionPackage:
    audit_package: CorkJunctionEvidencePackage
    smoke_summary_json: str
    version: str = MARYVILLE_JUNCTION_PACKAGE_VERSION
    deterministic_hash: str = ""

    def __post_init__(self) -> None:
        if self.version != MARYVILLE_JUNCTION_PACKAGE_VERSION:
            raise MaryvilleJunctionIntegrityError("unsupported Maryville package version")
        object.__setattr__(
            self,
            "smoke_summary_json",
            canonical_json(json.loads(self.smoke_summary_json)),
        )
        expected = stable_hash("maryville-junction-package", self._payload())
        if self.deterministic_hash and self.deterministic_hash != expected:
            raise MaryvilleJunctionIntegrityError("Maryville package hash mismatch")
        object.__setattr__(self, "deterministic_hash", expected)

    def _payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "audit_package": self.audit_package.to_dict(),
            "smoke_summary": json.loads(self.smoke_summary_json),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "deterministic_hash": self.deterministic_hash}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            audit_package=CorkJunctionEvidencePackage.from_dict(
                payload["audit_package"]  # type: ignore[arg-type]
            ),
            smoke_summary_json=canonical_json(payload["smoke_summary"]),
            version=str(payload["version"]),
            deterministic_hash=str(payload.get("deterministic_hash", "")),
        )

    @classmethod
    def from_json(cls, serialised: str) -> Self:
        payload = json.loads(serialised)
        if not isinstance(payload, dict):
            raise MaryvilleJunctionIntegrityError("package JSON must be an object")
        return cls.from_dict(payload)


@dataclass(frozen=True, slots=True)
class MaryvilleJunctionRun:
    package: MaryvilleJunctionPackage
    compiler_source: SourceNetworkEvidence
    extraction: OSMJunctionExtraction
    source_strict_result: CompilationResult
    reviewed_candidate_result: CompilationResult


def compile_maryville_junction(path: str | Path) -> MaryvilleJunctionRun:
    source = parse_osm_xml(path)
    extraction_config = maryville_extraction_config()
    extraction = extract_operational_junction(source, extraction_config)
    compiler_source, uturn_ids = extraction_to_source_evidence(
        source,
        extraction,
        network_id=MARYVILLE_NETWORK_ID,
    )
    strict = compile_network(compiler_source, config=source_strict_config())
    overrides = _uturn_overrides(uturn_ids)
    reviewed = compile_network(
        compiler_source,
        config=maryville_reviewed_config(),
        overrides=overrides,
    )
    executable = reviewed.require_executable()
    smoke = _run_smoke(executable)
    audit = CorkJunctionEvidencePackage(
        source=source,
        extraction_config=extraction_config,
        extraction=extraction,
        normalized_source_json=canonical_json(normalize_source(compiler_source).to_dict()),
        source_strict_bundle=strict.evidence_bundle,
        reviewed_candidate_bundle=reviewed.evidence_bundle,
        reviewed_assumptions=_reviewed_assumptions(),
        reviewed_overrides=overrides,
    )
    package = MaryvilleJunctionPackage(audit, canonical_json(smoke))
    return MaryvilleJunctionRun(package, compiler_source, extraction, strict, reviewed)


def _run_smoke(executable) -> dict[str, object]:
    junction = next(
        node
        for node in executable.topology.nodes
        if node.source_node_id == MARYVILLE_JUNCTION_NODE_ID
    )
    permitted = tuple(
        sorted(
            (
                movement.upstream_link_id,
                movement.downstream_link_id,
                movement.movement_id,
            )
            for movement in junction.movement_specs
        )
    )
    demands = tuple(
        DemandDeclaration(
            demand_id=f"maryville-smoke:{ordinal:02d}",
            departure_tick=ordinal * 2,
            route_intent=(upstream, downstream),
        )
        for ordinal, (upstream, downstream, _) in enumerate(permitted)
    )

    def execute():
        engine = executable.build_loading_engine()
        for demand in demands:
            engine.instantiate(demand)
        for _ in range(160):
            engine.step()
        events = tuple(
            (
                event.sequence_number,
                event.packet_id,
                event.event_type.value,
                event.entity_id,
                event.physical_tick,
            )
            for event in engine.event_log
        )
        return engine, events

    engine, events = execute()
    replay, replay_events = execute()
    return {
        "scenario_id": "maryville-unsignalised-all-permitted-movements-smoke-v1",
        "classification": "synthetic_demand_on_real_osm_derived_geometry",
        "representation": "shared_link_fifo",
        "demand_count": len(demands),
        "demand_declarations": [
            {
                "demand_id": demand.demand_id,
                "departure_tick": demand.departure_tick,
                "route_intent": list(demand.route_intent),
            }
            for demand in demands
        ],
        "permitted_movements": [movement_id for _, _, movement_id in permitted],
        "completed_count": len(engine.completed_packet_ids),
        "terminal_tick": engine.current_tick,
        "canonical_event_count": len(events),
        "event_log_hash": stable_hash("maryville-smoke-events", events),
        "replay_exact": events == replay_events,
        "conservation_passed": engine.check_conservation(),
        "replay_conservation_passed": replay.check_conservation(),
        "event_cache_consistency_passed": engine.check_event_cache_consistency(),
        "count_consistency_passed": engine.count_consistency_report().is_consistent,
    }


def write_maryville_junction_package(
    run: MaryvilleJunctionRun, path: str | Path
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(run.package.to_json(), encoding="utf-8")
    return output
