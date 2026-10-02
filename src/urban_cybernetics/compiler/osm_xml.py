# SPDX-License-Identifier: MPL-2.0
"""Pinned OSM XML evidence, bounded extraction, and Cork-junction audit support."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Mapping, Self
from xml.etree import ElementTree

from .adapter import adapt_osm_like, normalize_source
from .model import (
    CompilerConfig,
    CompilerEvidenceBundle,
    CompilerOverride,
    NormalizedSourceGraph,
    SourceNetworkEvidence,
    canonical_json,
    stable_hash,
)
from .pipeline import CompilationResult, compile_network


OSM_XML_PARSER_VERSION = "uc.osm-xml-parser.v1"
OSM_XML_EVIDENCE_SCHEMA_VERSION = "uc.osm-xml-evidence.v1"
OSM_EXTRACTION_CONFIG_SCHEMA_VERSION = "uc.osm-junction-extraction-config.v1"
OSM_EXTRACTION_SCHEMA_VERSION = "uc.osm-junction-extraction.v1"
OSM_SEGMENT_SCHEMA_VERSION = "uc.osm-way-segment.v1"
CORK_JUNCTION_PACKAGE_SCHEMA_VERSION = "uc.cork-junction-evidence-package.v1"
GEOMETRY_FORMULA_ID = "uc.geometry.haversine-polyline"
GEOMETRY_FORMULA_VERSION = "1"
EARTH_RADIUS_METRES = 6_371_008.8

RETAINED_EXECUTABLE = "retained_executable_road_evidence"
RETAINED_CONTROL = "retained_control_or_restriction_evidence"
RETAINED_CONTEXT = "retained_contextual_evidence"
EXCLUDED_NON_VEHICLE = "excluded_non_vehicle_feature"
EXCLUDED_OUTSIDE = "excluded_outside_operational_boundary"
EXCLUDED_UNSUPPORTED = "excluded_unsupported_feature"
UNRESOLVED_RELEVANCE = "unresolved_relevance"

BOREENMANNA_CORE_WAY_IDS = (
    "32670070",
    "32670121",
    "96385702",
    "110781522",
    "1242275936",
    "279050194",
    "279050199",
    "279054332",
    "279054333",
    "477791936",
)


class OSMXMLValidationError(ValueError):
    """Raised when pinned XML cannot be represented without losing integrity."""


class CorkJunctionPackageIntegrityError(ValueError):
    """Raised when a serialized Cork-junction evidence package was altered."""


def _tags(element: ElementTree.Element) -> tuple[tuple[str, str], ...]:
    values = [(item.attrib["k"], item.attrib["v"]) for item in element.findall("tag")]
    if len(values) != len(set(name for name, _ in values)):
        raise OSMXMLValidationError(
            f"duplicate tag keys on {element.tag}:{element.attrib.get('id', '')}"
        )
    return tuple(sorted(values))


def _attrs(
    element: ElementTree.Element, excluded: frozenset[str]
) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted((name, value) for name, value in element.attrib.items() if name not in excluded)
    )


def _mapping(items: tuple[tuple[str, str], ...]) -> dict[str, str]:
    return dict(items)


@dataclass(frozen=True, slots=True)
class OSMBounds:
    min_latitude: float
    min_longitude: float
    max_latitude: float
    max_longitude: float

    def __post_init__(self) -> None:
        if self.min_latitude > self.max_latitude or self.min_longitude > self.max_longitude:
            raise OSMXMLValidationError("OSM bounds are inverted")

    def contains(self, latitude: float, longitude: float) -> bool:
        return (
            self.min_latitude <= latitude <= self.max_latitude
            and self.min_longitude <= longitude <= self.max_longitude
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "min_latitude": self.min_latitude,
            "min_longitude": self.min_longitude,
            "max_latitude": self.max_latitude,
            "max_longitude": self.max_longitude,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            float(payload["min_latitude"]),
            float(payload["min_longitude"]),
            float(payload["max_latitude"]),
            float(payload["max_longitude"]),
        )


@dataclass(frozen=True, slots=True)
class OSMNodeEvidence:
    osm_id: str
    latitude: float
    longitude: float
    attributes: tuple[tuple[str, str], ...] = ()
    tags: tuple[tuple[str, str], ...] = ()

    @property
    def stable_id(self) -> str:
        return f"osm:node:{self.osm_id}"

    def to_dict(self) -> dict[str, object]:
        return {
            "osm_id": self.osm_id,
            "stable_id": self.stable_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "attributes": [list(item) for item in self.attributes],
            "tags": [list(item) for item in self.tags],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            osm_id=str(payload["osm_id"]),
            latitude=float(payload["latitude"]),
            longitude=float(payload["longitude"]),
            attributes=tuple((str(a), str(b)) for a, b in payload.get("attributes", [])),
            tags=tuple((str(a), str(b)) for a, b in payload.get("tags", [])),
        )


@dataclass(frozen=True, slots=True)
class OSMWayEvidence:
    osm_id: str
    node_refs: tuple[str, ...]
    attributes: tuple[tuple[str, str], ...] = ()
    tags: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if len(self.node_refs) < 2:
            raise OSMXMLValidationError(f"OSM way {self.osm_id} has fewer than two nodes")

    @property
    def stable_id(self) -> str:
        return f"osm:way:{self.osm_id}"

    def to_dict(self) -> dict[str, object]:
        return {
            "osm_id": self.osm_id,
            "stable_id": self.stable_id,
            "node_refs": list(self.node_refs),
            "attributes": [list(item) for item in self.attributes],
            "tags": [list(item) for item in self.tags],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            osm_id=str(payload["osm_id"]),
            node_refs=tuple(str(item) for item in payload["node_refs"]),  # type: ignore[index]
            attributes=tuple((str(a), str(b)) for a, b in payload.get("attributes", [])),
            tags=tuple((str(a), str(b)) for a, b in payload.get("tags", [])),
        )


@dataclass(frozen=True, slots=True)
class OSMRelationMemberEvidence:
    member_type: str
    ref: str
    role: str

    def to_dict(self) -> dict[str, str]:
        return {"type": self.member_type, "ref": self.ref, "role": self.role}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(str(payload["type"]), str(payload["ref"]), str(payload["role"]))


@dataclass(frozen=True, slots=True)
class OSMRelationEvidence:
    osm_id: str
    members: tuple[OSMRelationMemberEvidence, ...]
    attributes: tuple[tuple[str, str], ...] = ()
    tags: tuple[tuple[str, str], ...] = ()

    @property
    def stable_id(self) -> str:
        return f"osm:relation:{self.osm_id}"

    def to_dict(self) -> dict[str, object]:
        return {
            "osm_id": self.osm_id,
            "stable_id": self.stable_id,
            "members": [item.to_dict() for item in self.members],
            "attributes": [list(item) for item in self.attributes],
            "tags": [list(item) for item in self.tags],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            osm_id=str(payload["osm_id"]),
            members=tuple(
                OSMRelationMemberEvidence.from_dict(item)
                for item in payload.get("members", [])  # type: ignore[arg-type]
            ),
            attributes=tuple((str(a), str(b)) for a, b in payload.get("attributes", [])),
            tags=tuple((str(a), str(b)) for a, b in payload.get("tags", [])),
        )


@dataclass(frozen=True, slots=True)
class OSMFileEvidence:
    source_filename: str
    byte_length: int
    file_sha256: str
    root_attributes: tuple[tuple[str, str], ...]
    bounds: tuple[OSMBounds, ...]
    nodes: tuple[OSMNodeEvidence, ...]
    ways: tuple[OSMWayEvidence, ...]
    relations: tuple[OSMRelationEvidence, ...]
    timestamp_min: str | None
    timestamp_max: str | None
    parser_version: str = OSM_XML_PARSER_VERSION
    schema_version: str = OSM_XML_EVIDENCE_SCHEMA_VERSION
    parsed_content_hash: str = ""
    file_evidence_hash: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != OSM_XML_EVIDENCE_SCHEMA_VERSION:
            raise OSMXMLValidationError(f"unsupported OSM evidence schema {self.schema_version}")
        if self.parser_version != OSM_XML_PARSER_VERSION:
            raise OSMXMLValidationError(f"unsupported OSM parser {self.parser_version}")
        for label, values in (
            ("node", tuple(item.osm_id for item in self.nodes)),
            ("way", tuple(item.osm_id for item in self.ways)),
            ("relation", tuple(item.osm_id for item in self.relations)),
        ):
            if len(values) != len(set(values)):
                raise OSMXMLValidationError(f"duplicate OSM {label} IDs")
        node_ids = {item.osm_id for item in self.nodes}
        missing = tuple(
            sorted(
                (way.osm_id, ref)
                for way in self.ways
                for ref in way.node_refs
                if ref not in node_ids
            )
        )
        if missing:
            raise OSMXMLValidationError(f"ways contain missing node references: {missing[:5]}")
        expected_parsed = stable_hash("osm-parsed-content", self._parsed_payload())
        if self.parsed_content_hash and self.parsed_content_hash != expected_parsed:
            raise OSMXMLValidationError("OSM parsed_content_hash mismatch")
        object.__setattr__(self, "parsed_content_hash", expected_parsed)
        expected_file = stable_hash("osm-file-evidence", self._file_payload())
        if self.file_evidence_hash and self.file_evidence_hash != expected_file:
            raise OSMXMLValidationError("OSM file_evidence_hash mismatch")
        object.__setattr__(self, "file_evidence_hash", expected_file)

    @property
    def node_by_id(self) -> dict[str, OSMNodeEvidence]:
        return {item.osm_id: item for item in self.nodes}

    @property
    def way_by_id(self) -> dict[str, OSMWayEvidence]:
        return {item.osm_id: item for item in self.ways}

    @property
    def source_format(self) -> str:
        return "application/xml; profile=osm-0.6"

    def _parsed_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "root_attributes": [list(item) for item in self.root_attributes],
            "bounds": [item.to_dict() for item in self.bounds],
            "nodes": [item.to_dict() for item in sorted(self.nodes, key=lambda value: int(value.osm_id))],
            "ways": [item.to_dict() for item in sorted(self.ways, key=lambda value: int(value.osm_id))],
            "relations": [
                item.to_dict() for item in sorted(self.relations, key=lambda value: int(value.osm_id))
            ],
        }

    def _file_payload(self) -> dict[str, object]:
        return {
            "source_filename": self.source_filename,
            "source_format": self.source_format,
            "byte_length": self.byte_length,
            "file_sha256": self.file_sha256,
            "parser_version": self.parser_version,
            "parsed_content_hash": self.parsed_content_hash,
            "timestamp_min": self.timestamp_min,
            "timestamp_max": self.timestamp_max,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self._file_payload(),
            **self._parsed_payload(),
            "counts": {
                "nodes": len(self.nodes),
                "ways": len(self.ways),
                "relations": len(self.relations),
            },
            "file_evidence_hash": self.file_evidence_hash,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            source_filename=str(payload["source_filename"]),
            byte_length=int(payload["byte_length"]),
            file_sha256=str(payload["file_sha256"]),
            root_attributes=tuple((str(a), str(b)) for a, b in payload["root_attributes"]),  # type: ignore[index]
            bounds=tuple(OSMBounds.from_dict(item) for item in payload.get("bounds", [])),  # type: ignore[arg-type]
            nodes=tuple(OSMNodeEvidence.from_dict(item) for item in payload.get("nodes", [])),  # type: ignore[arg-type]
            ways=tuple(OSMWayEvidence.from_dict(item) for item in payload.get("ways", [])),  # type: ignore[arg-type]
            relations=tuple(
                OSMRelationEvidence.from_dict(item)
                for item in payload.get("relations", [])  # type: ignore[arg-type]
            ),
            timestamp_min=(None if payload.get("timestamp_min") is None else str(payload["timestamp_min"])),
            timestamp_max=(None if payload.get("timestamp_max") is None else str(payload["timestamp_max"])),
            parser_version=str(payload["parser_version"]),
            schema_version=str(payload["schema_version"]),
            parsed_content_hash=str(payload.get("parsed_content_hash", "")),
            file_evidence_hash=str(payload.get("file_evidence_hash", "")),
        )


def parse_osm_xml(path: str | Path) -> OSMFileEvidence:
    """Parse one pinned OSM XML file without downloading or rewriting it."""

    source_path = Path(path)
    source_bytes = source_path.read_bytes()
    try:
        root = ElementTree.fromstring(source_bytes)
    except ElementTree.ParseError as exc:
        raise OSMXMLValidationError(f"malformed OSM XML: {exc}") from exc
    if root.tag != "osm" or root.attrib.get("version") != "0.6":
        raise OSMXMLValidationError("adapter requires an OSM 0.6 <osm> document")

    nodes = tuple(
        OSMNodeEvidence(
            osm_id=item.attrib["id"],
            latitude=float(item.attrib["lat"]),
            longitude=float(item.attrib["lon"]),
            attributes=_attrs(item, frozenset(("id", "lat", "lon"))),
            tags=_tags(item),
        )
        for item in root.findall("node")
    )
    ways = tuple(
        OSMWayEvidence(
            osm_id=item.attrib["id"],
            node_refs=tuple(nd.attrib["ref"] for nd in item.findall("nd")),
            attributes=_attrs(item, frozenset(("id",))),
            tags=_tags(item),
        )
        for item in root.findall("way")
    )
    relations = tuple(
        OSMRelationEvidence(
            osm_id=item.attrib["id"],
            members=tuple(
                OSMRelationMemberEvidence(
                    member.attrib["type"],
                    member.attrib["ref"],
                    member.attrib.get("role", ""),
                )
                for member in item.findall("member")
            ),
            attributes=_attrs(item, frozenset(("id",))),
            tags=_tags(item),
        )
        for item in root.findall("relation")
    )
    bounds = tuple(
        OSMBounds(
            min_latitude=float(item.attrib["minlat"]),
            min_longitude=float(item.attrib["minlon"]),
            max_latitude=float(item.attrib["maxlat"]),
            max_longitude=float(item.attrib["maxlon"]),
        )
        for item in root.findall("bounds")
    )
    timestamps = sorted(
        value
        for element in (*nodes, *ways, *relations)
        for name, value in element.attributes
        if name == "timestamp"
    )
    return OSMFileEvidence(
        source_filename=source_path.name,
        byte_length=len(source_bytes),
        file_sha256=hashlib.sha256(source_bytes).hexdigest(),
        root_attributes=tuple(sorted(root.attrib.items())),
        bounds=bounds,
        nodes=nodes,
        ways=ways,
        relations=relations,
        timestamp_min=None if not timestamps else timestamps[0],
        timestamp_max=None if not timestamps else timestamps[-1],
    )


@dataclass(frozen=True, slots=True)
class OSMJunctionExtractionConfig:
    boundary_id: str
    seed_way_ids: tuple[str, ...]
    included_highway_classes: tuple[str, ...]
    explicit_include_way_ids: tuple[str, ...] = ()
    explicit_exclude_way_ids: tuple[str, ...] = ()
    explicit_boundary_node_ids: tuple[str, ...] = ()
    explicit_way_node_intervals: tuple[tuple[str, str, str], ...] = ()
    include_service_roads: bool = False
    retain_crossings_for_audit: bool = True
    split_at_crossings: bool = False
    minimum_approach_length_metres: float = 50.0
    approach_depth_hops: int = 0
    schema_version: str = OSM_EXTRACTION_CONFIG_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != OSM_EXTRACTION_CONFIG_SCHEMA_VERSION:
            raise OSMXMLValidationError("unsupported extraction configuration schema")
        if not self.boundary_id or not self.seed_way_ids:
            raise OSMXMLValidationError("extraction requires a boundary ID and seed ways")
        if self.minimum_approach_length_metres <= 0 or self.approach_depth_hops < 0:
            raise OSMXMLValidationError("invalid extraction depth or approach length")
        for name in (
            "seed_way_ids",
            "included_highway_classes",
            "explicit_include_way_ids",
            "explicit_exclude_way_ids",
            "explicit_boundary_node_ids",
        ):
            object.__setattr__(self, name, tuple(sorted(set(getattr(self, name)))))
        intervals = tuple(
            sorted(
                {
                    (str(way_id), str(start_node_id), str(end_node_id))
                    for way_id, start_node_id, end_node_id in self.explicit_way_node_intervals
                }
            )
        )
        if len({way_id for way_id, _, _ in intervals}) != len(intervals):
            raise OSMXMLValidationError(
                "extraction permits at most one explicit node interval per way"
            )
        object.__setattr__(self, "explicit_way_node_intervals", intervals)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "boundary_id": self.boundary_id,
            "seed_way_ids": list(self.seed_way_ids),
            "included_highway_classes": list(self.included_highway_classes),
            "explicit_include_way_ids": list(self.explicit_include_way_ids),
            "explicit_exclude_way_ids": list(self.explicit_exclude_way_ids),
            "explicit_boundary_node_ids": list(self.explicit_boundary_node_ids),
            "include_service_roads": self.include_service_roads,
            "retain_crossings_for_audit": self.retain_crossings_for_audit,
            "split_at_crossings": self.split_at_crossings,
            "minimum_approach_length_metres": self.minimum_approach_length_metres,
            "approach_depth_hops": self.approach_depth_hops,
        }
        # Preserve the established v1 hash domain when clipping is unused.
        if self.explicit_way_node_intervals:
            payload["explicit_way_node_intervals"] = [
                list(item) for item in self.explicit_way_node_intervals
            ]
        return payload

    @property
    def config_hash(self) -> str:
        return stable_hash("osm-junction-extraction-config", self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            boundary_id=str(payload["boundary_id"]),
            seed_way_ids=tuple(str(item) for item in payload["seed_way_ids"]),  # type: ignore[index]
            included_highway_classes=tuple(
                str(item) for item in payload["included_highway_classes"]  # type: ignore[index]
            ),
            explicit_include_way_ids=tuple(
                str(item) for item in payload.get("explicit_include_way_ids", [])
            ),
            explicit_exclude_way_ids=tuple(
                str(item) for item in payload.get("explicit_exclude_way_ids", [])
            ),
            explicit_boundary_node_ids=tuple(
                str(item) for item in payload.get("explicit_boundary_node_ids", [])
            ),
            explicit_way_node_intervals=tuple(
                (str(way_id), str(start_node_id), str(end_node_id))
                for way_id, start_node_id, end_node_id in payload.get(
                    "explicit_way_node_intervals", []
                )
            ),
            include_service_roads=bool(payload.get("include_service_roads", False)),
            retain_crossings_for_audit=bool(payload.get("retain_crossings_for_audit", True)),
            split_at_crossings=bool(payload.get("split_at_crossings", False)),
            minimum_approach_length_metres=float(payload["minimum_approach_length_metres"]),
            approach_depth_hops=int(payload.get("approach_depth_hops", 0)),
            schema_version=str(payload["schema_version"]),
        )


def boreenmanna_extraction_config() -> OSMJunctionExtractionConfig:
    """Return the reviewed, ID-explicit operational boundary for this milestone."""

    return OSMJunctionExtractionConfig(
        boundary_id="boreenmanna-south-link-operational-complex-v1",
        seed_way_ids=BOREENMANNA_CORE_WAY_IDS,
        explicit_include_way_ids=BOREENMANNA_CORE_WAY_IDS,
        included_highway_classes=("secondary", "trunk", "trunk_link"),
        include_service_roads=False,
        retain_crossings_for_audit=True,
        split_at_crossings=False,
        minimum_approach_length_metres=50.0,
        approach_depth_hops=0,
    )


@dataclass(frozen=True, slots=True)
class OSMExtractionDecision:
    entity_type: str
    osm_id: str
    classification: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "entity_type": self.entity_type,
            "osm_id": self.osm_id,
            "classification": self.classification,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            str(payload["entity_type"]),
            str(payload["osm_id"]),
            str(payload["classification"]),
            str(payload["reason"]),
        )


@dataclass(frozen=True, slots=True)
class OSMAuditDiagnostic:
    severity: str
    code: str
    message: str
    entity_refs: tuple[str, ...] = ()
    diagnostic_hash: str = ""

    def __post_init__(self) -> None:
        expected = stable_hash(
            "osm-extraction-diagnostic",
            {
                "severity": self.severity,
                "code": self.code,
                "message": self.message,
                "entity_refs": list(self.entity_refs),
            },
        )
        if self.diagnostic_hash and self.diagnostic_hash != expected:
            raise OSMXMLValidationError("OSM extraction diagnostic hash mismatch")
        object.__setattr__(self, "diagnostic_hash", expected)

    def to_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "entity_refs": list(self.entity_refs),
            "diagnostic_hash": self.diagnostic_hash,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            severity=str(payload["severity"]),
            code=str(payload["code"]),
            message=str(payload["message"]),
            entity_refs=tuple(str(item) for item in payload.get("entity_refs", [])),
            diagnostic_hash=str(payload.get("diagnostic_hash", "")),
        )


@dataclass(frozen=True, slots=True)
class OSMSplitWaySegment:
    segment_id: str
    source_way_id: str
    split_ordinal: int
    direction: str
    tail_node_id: str
    head_node_id: str
    source_node_refs: tuple[str, ...]
    source_tags: tuple[tuple[str, str], ...]
    length_metres: float
    coordinate_source: str = "osm-node-latitude-longitude-wgs84"
    distance_formula_id: str = GEOMETRY_FORMULA_ID
    distance_formula_version: str = GEOMETRY_FORMULA_VERSION
    geometry_simplification: str = "none; intermediate shape nodes retained in polyline"
    schema_version: str = OSM_SEGMENT_SCHEMA_VERSION
    geometry_derivation_hash: str = ""
    segment_hash: str = ""

    def __post_init__(self) -> None:
        if self.direction not in ("forward", "reverse") or self.length_metres <= 0:
            raise OSMXMLValidationError(f"invalid split segment {self.segment_id}")
        expected_geometry = stable_hash(
            "osm-segment-geometry",
            {
                "source_way_id": self.source_way_id,
                "source_node_refs": list(self.source_node_refs),
                "coordinate_source": self.coordinate_source,
                "distance_formula_id": self.distance_formula_id,
                "distance_formula_version": self.distance_formula_version,
                "length_metres": self.length_metres,
                "geometry_simplification": self.geometry_simplification,
            },
        )
        if self.geometry_derivation_hash and self.geometry_derivation_hash != expected_geometry:
            raise OSMXMLValidationError("segment geometry derivation hash mismatch")
        object.__setattr__(self, "geometry_derivation_hash", expected_geometry)
        expected_segment = stable_hash("osm-way-segment", self._hash_payload())
        if self.segment_hash and self.segment_hash != expected_segment:
            raise OSMXMLValidationError("OSM segment hash mismatch")
        object.__setattr__(self, "segment_hash", expected_segment)

    def _hash_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "segment_id": self.segment_id,
            "source_way_id": self.source_way_id,
            "split_ordinal": self.split_ordinal,
            "direction": self.direction,
            "tail_node_id": self.tail_node_id,
            "head_node_id": self.head_node_id,
            "source_node_refs": list(self.source_node_refs),
            "source_tags": [list(item) for item in self.source_tags],
            "length_metres": self.length_metres,
            "coordinate_source": self.coordinate_source,
            "distance_formula_id": self.distance_formula_id,
            "distance_formula_version": self.distance_formula_version,
            "geometry_simplification": self.geometry_simplification,
            "geometry_derivation_hash": self.geometry_derivation_hash,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._hash_payload(), "segment_hash": self.segment_hash}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            segment_id=str(payload["segment_id"]),
            source_way_id=str(payload["source_way_id"]),
            split_ordinal=int(payload["split_ordinal"]),
            direction=str(payload["direction"]),
            tail_node_id=str(payload["tail_node_id"]),
            head_node_id=str(payload["head_node_id"]),
            source_node_refs=tuple(str(item) for item in payload["source_node_refs"]),  # type: ignore[index]
            source_tags=tuple((str(a), str(b)) for a, b in payload["source_tags"]),  # type: ignore[index]
            length_metres=float(payload["length_metres"]),
            coordinate_source=str(payload["coordinate_source"]),
            distance_formula_id=str(payload["distance_formula_id"]),
            distance_formula_version=str(payload["distance_formula_version"]),
            geometry_simplification=str(payload["geometry_simplification"]),
            schema_version=str(payload["schema_version"]),
            geometry_derivation_hash=str(payload.get("geometry_derivation_hash", "")),
            segment_hash=str(payload.get("segment_hash", "")),
        )


@dataclass(frozen=True, slots=True)
class OSMRestrictionFinding:
    relation_id: str
    restriction: str | None
    from_way_ids: tuple[str, ...]
    via_members: tuple[tuple[str, str], ...]
    to_way_ids: tuple[str, ...]
    missing_member_refs: tuple[tuple[str, str], ...]
    touches_operational_evidence: bool
    status: str
    finding_hash: str = ""

    def __post_init__(self) -> None:
        expected = stable_hash("osm-restriction-finding", self._payload())
        if self.finding_hash and self.finding_hash != expected:
            raise OSMXMLValidationError("restriction finding hash mismatch")
        object.__setattr__(self, "finding_hash", expected)

    def _payload(self) -> dict[str, object]:
        return {
            "relation_id": self.relation_id,
            "restriction": self.restriction,
            "from_way_ids": list(self.from_way_ids),
            "via_members": [list(item) for item in self.via_members],
            "to_way_ids": list(self.to_way_ids),
            "missing_member_refs": [list(item) for item in self.missing_member_refs],
            "touches_operational_evidence": self.touches_operational_evidence,
            "status": self.status,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "finding_hash": self.finding_hash}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            relation_id=str(payload["relation_id"]),
            restriction=(None if payload.get("restriction") is None else str(payload["restriction"])),
            from_way_ids=tuple(str(item) for item in payload.get("from_way_ids", [])),
            via_members=tuple((str(a), str(b)) for a, b in payload.get("via_members", [])),
            to_way_ids=tuple(str(item) for item in payload.get("to_way_ids", [])),
            missing_member_refs=tuple(
                (str(a), str(b)) for a, b in payload.get("missing_member_refs", [])
            ),
            touches_operational_evidence=bool(payload["touches_operational_evidence"]),
            status=str(payload["status"]),
            finding_hash=str(payload.get("finding_hash", "")),
        )


@dataclass(frozen=True, slots=True)
class OSMReviewedAssumption:
    assumption_id: str
    target_scope: str
    target_field: str
    selected_value_json: str
    unit: str
    actor: str
    source: str
    reason: str
    rule_id: str
    assumption_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "selected_value_json",
            canonical_json(json.loads(self.selected_value_json)),
        )
        expected = stable_hash("osm-reviewed-assumption", self._payload())
        if self.assumption_hash and self.assumption_hash != expected:
            raise OSMXMLValidationError("reviewed assumption hash mismatch")
        object.__setattr__(self, "assumption_hash", expected)

    @classmethod
    def create(
        cls,
        *,
        assumption_id: str,
        target_scope: str,
        target_field: str,
        selected_value: object,
        unit: str,
        actor: str,
        source: str,
        reason: str,
        rule_id: str,
    ) -> Self:
        return cls(
            assumption_id=assumption_id,
            target_scope=target_scope,
            target_field=target_field,
            selected_value_json=canonical_json(selected_value),
            unit=unit,
            actor=actor,
            source=source,
            reason=reason,
            rule_id=rule_id,
        )

    @property
    def selected_value(self) -> object:
        return json.loads(self.selected_value_json)

    def _payload(self) -> dict[str, object]:
        return {
            "assumption_id": self.assumption_id,
            "target_scope": self.target_scope,
            "target_field": self.target_field,
            "selected_value": self.selected_value,
            "unit": self.unit,
            "actor": self.actor,
            "source": self.source,
            "reason": self.reason,
            "rule_id": self.rule_id,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "assumption_hash": self.assumption_hash}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            assumption_id=str(payload["assumption_id"]),
            target_scope=str(payload["target_scope"]),
            target_field=str(payload["target_field"]),
            selected_value_json=canonical_json(payload["selected_value"]),
            unit=str(payload["unit"]),
            actor=str(payload["actor"]),
            source=str(payload["source"]),
            reason=str(payload["reason"]),
            rule_id=str(payload["rule_id"]),
            assumption_hash=str(payload.get("assumption_hash", "")),
        )


@dataclass(frozen=True, slots=True)
class OSMJunctionExtraction:
    source_parsed_content_hash: str
    extraction_config_hash: str
    decisions: tuple[OSMExtractionDecision, ...]
    retained_way_ids: tuple[str, ...]
    retained_node_ids: tuple[str, ...]
    segments: tuple[OSMSplitWaySegment, ...]
    restrictions: tuple[OSMRestrictionFinding, ...]
    signal_node_ids: tuple[str, ...]
    crossing_node_ids: tuple[str, ...]
    lane_evidence_json: str
    signal_evidence_json: str
    representation_assessment_json: str
    diagnostics: tuple[OSMAuditDiagnostic, ...]
    schema_version: str = OSM_EXTRACTION_SCHEMA_VERSION
    extraction_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "lane_evidence_json", canonical_json(json.loads(self.lane_evidence_json)))
        object.__setattr__(
            self,
            "signal_evidence_json",
            canonical_json(json.loads(self.signal_evidence_json)),
        )
        object.__setattr__(
            self,
            "representation_assessment_json",
            canonical_json(json.loads(self.representation_assessment_json)),
        )
        expected = stable_hash("osm-junction-extraction", self._payload())
        if self.extraction_hash and self.extraction_hash != expected:
            raise OSMXMLValidationError("OSM extraction hash mismatch")
        object.__setattr__(self, "extraction_hash", expected)

    @property
    def lane_evidence(self) -> object:
        return json.loads(self.lane_evidence_json)

    @property
    def signal_evidence(self) -> object:
        return json.loads(self.signal_evidence_json)

    @property
    def representation_assessment(self) -> object:
        return json.loads(self.representation_assessment_json)

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_parsed_content_hash": self.source_parsed_content_hash,
            "extraction_config_hash": self.extraction_config_hash,
            "decisions": [item.to_dict() for item in self.decisions],
            "retained_way_ids": list(self.retained_way_ids),
            "retained_node_ids": list(self.retained_node_ids),
            "segments": [item.to_dict() for item in self.segments],
            "restrictions": [item.to_dict() for item in self.restrictions],
            "signal_node_ids": list(self.signal_node_ids),
            "crossing_node_ids": list(self.crossing_node_ids),
            "lane_evidence": self.lane_evidence,
            "signal_evidence": self.signal_evidence,
            "representation_assessment": self.representation_assessment,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "extraction_hash": self.extraction_hash}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            source_parsed_content_hash=str(payload["source_parsed_content_hash"]),
            extraction_config_hash=str(payload["extraction_config_hash"]),
            decisions=tuple(
                OSMExtractionDecision.from_dict(item)
                for item in payload.get("decisions", [])  # type: ignore[arg-type]
            ),
            retained_way_ids=tuple(str(item) for item in payload.get("retained_way_ids", [])),
            retained_node_ids=tuple(str(item) for item in payload.get("retained_node_ids", [])),
            segments=tuple(
                OSMSplitWaySegment.from_dict(item)
                for item in payload.get("segments", [])  # type: ignore[arg-type]
            ),
            restrictions=tuple(
                OSMRestrictionFinding.from_dict(item)
                for item in payload.get("restrictions", [])  # type: ignore[arg-type]
            ),
            signal_node_ids=tuple(str(item) for item in payload.get("signal_node_ids", [])),
            crossing_node_ids=tuple(str(item) for item in payload.get("crossing_node_ids", [])),
            lane_evidence_json=canonical_json(payload.get("lane_evidence", [])),
            signal_evidence_json=canonical_json(payload.get("signal_evidence", [])),
            representation_assessment_json=canonical_json(
                payload.get("representation_assessment", [])
            ),
            diagnostics=tuple(
                OSMAuditDiagnostic.from_dict(item)
                for item in payload.get("diagnostics", [])  # type: ignore[arg-type]
            ),
            schema_version=str(payload["schema_version"]),
            extraction_hash=str(payload.get("extraction_hash", "")),
        )


def _haversine_metres(first: OSMNodeEvidence, second: OSMNodeEvidence) -> float:
    lat1 = radians(first.latitude)
    lat2 = radians(second.latitude)
    delta_lat = lat2 - lat1
    delta_lon = radians(second.longitude - first.longitude)
    value = sin(delta_lat / 2.0) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_METRES * asin(sqrt(value))


def _polyline_length(refs: tuple[str, ...], nodes: Mapping[str, OSMNodeEvidence]) -> float:
    return sum(_haversine_metres(nodes[a], nodes[b]) for a, b in zip(refs, refs[1:]))


def _oneway_directions(tags: Mapping[str, str]) -> tuple[str, ...]:
    value = tags.get("oneway", "").strip().lower()
    if value in ("yes", "true", "1"):
        return ("forward",)
    if value == "-1":
        return ("reverse",)
    return ("forward", "reverse")


def _restriction_findings(
    source: OSMFileEvidence,
    retained_way_ids: set[str],
    retained_node_ids: set[str],
) -> tuple[OSMRestrictionFinding, ...]:
    present = {
        "node": {item.osm_id for item in source.nodes},
        "way": {item.osm_id for item in source.ways},
        "relation": {item.osm_id for item in source.relations},
    }
    findings = []
    for relation in source.relations:
        tags = _mapping(relation.tags)
        if tags.get("type") != "restriction":
            continue
        from_ids = tuple(sorted(item.ref for item in relation.members if item.role == "from" and item.member_type == "way"))
        to_ids = tuple(sorted(item.ref for item in relation.members if item.role == "to" and item.member_type == "way"))
        vias = tuple(sorted((item.member_type, item.ref) for item in relation.members if item.role == "via"))
        missing = tuple(
            sorted(
                (item.member_type, item.ref)
                for item in relation.members
                if item.ref not in present.get(item.member_type, set())
            )
        )
        touches = bool(
            set(from_ids + to_ids) & retained_way_ids
            or any(kind == "node" and ref in retained_node_ids for kind, ref in vias)
        )
        roles_valid = len(from_ids) == 1 and len(to_ids) == 1 and len(vias) == 1
        status = (
            "valid_and_operationally_relevant"
            if roles_valid and not missing and touches
            else "valid_but_outside_operational_boundary"
            if roles_valid and not missing
            else "incomplete_export_member_references"
            if missing
            else "invalid_restriction_roles"
        )
        findings.append(
            OSMRestrictionFinding(
                relation_id=relation.osm_id,
                restriction=tags.get("restriction"),
                from_way_ids=from_ids,
                via_members=vias,
                to_way_ids=to_ids,
                missing_member_refs=missing,
                touches_operational_evidence=touches,
                status=status,
            )
        )
    return tuple(sorted(findings, key=lambda item: int(item.relation_id)))


def extract_operational_junction(
    source: OSMFileEvidence,
    config: OSMJunctionExtractionConfig,
) -> OSMJunctionExtraction:
    """Extract and split the explicitly reviewed operational road complex."""

    way_by_id = source.way_by_id
    node_by_id = source.node_by_id
    retained_way_ids = set(config.seed_way_ids) | set(config.explicit_include_way_ids)
    retained_way_ids -= set(config.explicit_exclude_way_ids)
    missing_seed = sorted(retained_way_ids - set(way_by_id))
    if missing_seed:
        raise OSMXMLValidationError(f"extraction references missing ways: {missing_seed}")
    for way_id in retained_way_ids:
        highway = _mapping(way_by_id[way_id].tags).get("highway")
        if highway not in config.included_highway_classes and not (
            config.include_service_roads and highway == "service"
        ):
            raise OSMXMLValidationError(
                f"explicit way {way_id} has excluded highway class {highway!r}"
            )

    retained_ways = tuple(sorted((way_by_id[item] for item in retained_way_ids), key=lambda item: int(item.osm_id)))
    configured_intervals = {
        way_id: (start_node_id, end_node_id)
        for way_id, start_node_id, end_node_id in config.explicit_way_node_intervals
    }
    unknown_interval_ways = sorted(set(configured_intervals) - retained_way_ids)
    if unknown_interval_ways:
        raise OSMXMLValidationError(
            f"way-node intervals reference non-retained ways: {unknown_interval_ways}"
        )
    operational_refs_by_way: dict[str, tuple[str, ...]] = {}
    for way in retained_ways:
        interval = configured_intervals.get(way.osm_id)
        if interval is None:
            operational_refs_by_way[way.osm_id] = way.node_refs
            continue
        start_node_id, end_node_id = interval
        if start_node_id not in way.node_refs or end_node_id not in way.node_refs:
            raise OSMXMLValidationError(
                f"way-node interval for {way.osm_id} references a node outside the source way"
            )
        start_index = way.node_refs.index(start_node_id)
        end_index = way.node_refs.index(end_node_id)
        if start_index >= end_index:
            raise OSMXMLValidationError(
                f"way-node interval for {way.osm_id} must follow source-way order"
            )
        operational_refs_by_way[way.osm_id] = way.node_refs[start_index : end_index + 1]
    retained_node_ids = {
        ref for refs in operational_refs_by_way.values() for ref in refs
    }
    shared_counts: dict[str, int] = {}
    for way in retained_ways:
        for ref in set(operational_refs_by_way[way.osm_id]):
            shared_counts[ref] = shared_counts.get(ref, 0) + 1
    signal_node_ids = tuple(
        sorted(
            (
                ref
                for ref in retained_node_ids
                if _mapping(node_by_id[ref].tags).get("highway") == "traffic_signals"
                or "traffic_signals" in _mapping(node_by_id[ref].tags)
            ),
            key=int,
        )
    )
    crossing_node_ids = tuple(
        sorted(
            (
                ref
                for ref in retained_node_ids
                if _mapping(node_by_id[ref].tags).get("highway") == "crossing"
                or "crossing" in _mapping(node_by_id[ref].tags)
            ),
            key=int,
        )
    )
    restrictions = _restriction_findings(source, retained_way_ids, retained_node_ids)
    via_nodes = {
        ref
        for finding in restrictions
        if finding.touches_operational_evidence
        for kind, ref in finding.via_members
        if kind == "node" and ref in retained_node_ids
    }

    segments: list[OSMSplitWaySegment] = []
    diagnostics: list[OSMAuditDiagnostic] = []
    for way in retained_ways:
        operational_refs = operational_refs_by_way[way.osm_id]
        split_refs = {operational_refs[0], operational_refs[-1]}
        split_refs.update(ref for ref in operational_refs if shared_counts.get(ref, 0) > 1)
        split_refs.update(ref for ref in operational_refs if ref in signal_node_ids)
        split_refs.update(ref for ref in operational_refs if ref in via_nodes)
        split_refs.update(ref for ref in operational_refs if ref in config.explicit_boundary_node_ids)
        if config.split_at_crossings:
            split_refs.update(ref for ref in operational_refs if ref in crossing_node_ids)
        split_indices = sorted(operational_refs.index(ref) for ref in split_refs)
        spans = tuple(
            operational_refs[start : end + 1]
            for start, end in zip(split_indices, split_indices[1:])
            if end > start
        )
        tags = _mapping(way.tags)
        for ordinal, original_refs in enumerate(spans):
            length = _polyline_length(original_refs, node_by_id)
            if length < config.minimum_approach_length_metres:
                diagnostics.append(
                    OSMAuditDiagnostic(
                        "warning",
                        "UC.OSM.EXTRACTION.SHORT_CONTROL_SEGMENT",
                        "control/topology splitting produced a segment shorter than the configured approach-storage target",
                        (f"osm:way:{way.osm_id}", original_refs[0], original_refs[-1]),
                    )
                )
            for direction in _oneway_directions(tags):
                travel_refs = original_refs if direction == "forward" else tuple(reversed(original_refs))
                segment_id = (
                    f"osm-way:{way.osm_id}:segment:{ordinal:03d}:"
                    f"{travel_refs[0]}-to-{travel_refs[-1]}:{direction}"
                )
                segments.append(
                    OSMSplitWaySegment(
                        segment_id=segment_id,
                        source_way_id=way.osm_id,
                        split_ordinal=ordinal,
                        direction=direction,
                        tail_node_id=travel_refs[0],
                        head_node_id=travel_refs[-1],
                        source_node_refs=travel_refs,
                        source_tags=way.tags,
                        length_metres=length,
                    )
                )

    decisions: list[OSMExtractionDecision] = []
    signal_set = set(signal_node_ids)
    crossing_set = set(crossing_node_ids)
    for node in sorted(source.nodes, key=lambda item: int(item.osm_id)):
        if node.osm_id in signal_set:
            classification, reason = RETAINED_CONTROL, "signal head lies on a retained operational way"
        elif node.osm_id in crossing_set and config.retain_crossings_for_audit:
            classification, reason = RETAINED_CONTEXT, "crossing evidence lies on a retained operational way"
        elif node.osm_id in retained_node_ids:
            classification, reason = RETAINED_EXECUTABLE, "ordered geometry node of an explicitly retained way"
        else:
            classification, reason = EXCLUDED_OUTSIDE, "node is not referenced by the explicit operational-way boundary"
        decisions.append(OSMExtractionDecision("node", node.osm_id, classification, reason))
    for way in sorted(source.ways, key=lambda item: int(item.osm_id)):
        tags = _mapping(way.tags)
        highway = tags.get("highway")
        if way.osm_id in retained_way_ids:
            classification, reason = RETAINED_EXECUTABLE, "way ID is explicitly included by reviewed extraction configuration"
        elif highway in ("footway", "path", "steps", "cycleway", "pedestrian"):
            classification, reason = EXCLUDED_NON_VEHICLE, f"highway={highway} is not part of the vehicle graph"
        elif highway == "service" and not config.include_service_roads:
            classification, reason = EXCLUDED_OUTSIDE, "service/local access participation is disabled"
        elif highway is not None:
            classification, reason = EXCLUDED_OUTSIDE, "vehicle way is outside the explicit operational-way ID boundary"
        else:
            classification, reason = EXCLUDED_UNSUPPORTED, "way has no supported executable highway classification"
        decisions.append(OSMExtractionDecision("way", way.osm_id, classification, reason))
    restriction_by_id = {item.relation_id: item for item in restrictions}
    for relation in sorted(source.relations, key=lambda item: int(item.osm_id)):
        finding = restriction_by_id.get(relation.osm_id)
        if finding is not None and finding.touches_operational_evidence:
            classification, reason = RETAINED_CONTROL, "restriction relation touches retained source evidence"
        elif finding is not None:
            classification, reason = EXCLUDED_OUTSIDE, "restriction relation does not affect retained ways"
        else:
            classification, reason = EXCLUDED_UNSUPPORTED, "non-restriction relation is outside the vehicle compiler slice"
        decisions.append(OSMExtractionDecision("relation", relation.osm_id, classification, reason))

    for finding in restrictions:
        if finding.missing_member_refs:
            diagnostics.append(
                OSMAuditDiagnostic(
                    "unresolved",
                    "UC.OSM.RESTRICTION.INCOMPLETE_EXPORT",
                    "restriction relation references members absent from the pinned map export",
                    (f"osm:relation:{finding.relation_id}",),
                )
            )
    if signal_node_ids:
        diagnostics.append(
            OSMAuditDiagnostic(
                "unresolved",
                "UC.OSM.SIGNAL.TIMING_ABSENT",
                "signal heads are observed but controller ownership, movement groups, phases, durations, and offsets are absent",
                tuple(f"osm:node:{item}" for item in signal_node_ids),
            )
        )
    lane_evidence = [
        {
            "source_way_id": way.osm_id,
            "lanes": _mapping(way.tags).get("lanes"),
            "lanes_forward": _mapping(way.tags).get("lanes:forward"),
            "lanes_backward": _mapping(way.tags).get("lanes:backward"),
            "turn_lanes": _mapping(way.tags).get("turn:lanes"),
            "turn_lanes_forward": _mapping(way.tags).get("turn:lanes:forward"),
            "turn_lanes_backward": _mapping(way.tags).get("turn:lanes:backward"),
        }
        for way in retained_ways
    ]
    signal_evidence = [
        {
            "source_node_id": node_id,
            "evidence_kind": (
                "signal_head" if node_id in signal_node_ids else "crossing"
            ),
            "tags": _mapping(node_by_id[node_id].tags),
            "controller_ownership": None,
            "movement_assignment": None,
            "phase_timing": None,
        }
        for node_id in (*signal_node_ids, *crossing_node_ids)
    ]
    representation_assessment = [
        {
            "representation": "shared_link_strict_fifo",
            "status": "conditionally_supportable_after_physical_review",
            "source_support": "directed topology is available; detailed lane allocation is not required",
            "review_requirement": "capacity, density, wave speed, missing lane count, and signals remain external to OSM",
        },
        {
            "representation": "movement_partial_fifo",
            "status": "not_source_supported",
            "source_support": "candidate movements can be derived from topology",
            "review_requirement": "no retained way supplies turn:lanes or movement-specific queue allocation",
        },
        {
            "representation": "explicit_lane_group_queues",
            "status": "not_source_supported",
            "source_support": "total lane counts exist on nine of ten retained ways",
            "review_requirement": "microscopic lane-to-turn connectivity and signal-group-compatible lane groups are absent",
        },
    ]
    return OSMJunctionExtraction(
        source_parsed_content_hash=source.parsed_content_hash,
        extraction_config_hash=config.config_hash,
        decisions=tuple(
            sorted(decisions, key=lambda item: (item.entity_type, int(item.osm_id)))
        ),
        retained_way_ids=tuple(sorted(retained_way_ids, key=int)),
        retained_node_ids=tuple(sorted(retained_node_ids, key=int)),
        segments=tuple(sorted(segments, key=lambda item: item.segment_id)),
        restrictions=restrictions,
        signal_node_ids=signal_node_ids,
        crossing_node_ids=crossing_node_ids,
        lane_evidence_json=canonical_json(lane_evidence),
        signal_evidence_json=canonical_json(signal_evidence),
        representation_assessment_json=canonical_json(representation_assessment),
        diagnostics=tuple(
            sorted(diagnostics, key=lambda item: (item.code, item.entity_refs))
        ),
    )


def extraction_to_source_evidence(
    source: OSMFileEvidence,
    extraction: OSMJunctionExtraction,
    *,
    network_id: str = "osm:boreenmanna-south-link-operational-complex-v1",
) -> tuple[SourceNetworkEvidence, tuple[str, ...]]:
    """Adapt split OSM evidence to the existing compiler source contract."""

    node_by_id = source.node_by_id
    records: list[dict[str, object]] = []
    endpoint_ids = {
        value
        for segment in extraction.segments
        for value in (segment.tail_node_id, segment.head_node_id)
    }
    for node_id in sorted(endpoint_ids, key=int):
        node = node_by_id[node_id]
        records.append(
            {
                "evidence_id": f"osm-node-evidence:{node_id}",
                "type": "node",
                "id": node_id,
                "fields": {
                    "osm_node_id": node_id,
                    "latitude": node.latitude,
                    "longitude": node.longitude,
                    "osm_tags": _mapping(node.tags),
                },
            }
        )
    for segment in extraction.segments:
        tags = _mapping(segment.source_tags)
        fields: dict[str, object] = {
            "tail_node_id": segment.tail_node_id,
            "head_node_id": segment.head_node_id,
            "travel_direction": "forward",
            "highway": tags["highway"],
            "length_m": segment.length_metres,
            "oneway": tags.get("oneway", "no") not in ("no", "false", "0", ""),
            "source_way_id": segment.source_way_id,
            "source_node_refs": list(segment.source_node_refs),
            "source_segment_hash": segment.segment_hash,
            "geometry_derivation_hash": segment.geometry_derivation_hash,
            "osm_tags": tags,
        }
        if "lanes" in tags:
            fields["lanes"] = tags["lanes"]
        if "lanes:forward" in tags:
            fields["lanes:forward"] = tags["lanes:forward"]
        if "maxspeed" in tags:
            fields["maxspeed"] = tags["maxspeed"]
        if "access" in tags:
            fields["access"] = tags["access"]
        records.append(
            {
                "evidence_id": f"osm-segment-evidence:{segment.segment_hash}",
                "type": "link",
                "id": segment.segment_id,
                "fields": fields,
            }
        )
    for node_id in extraction.signal_node_ids:
        node = node_by_id[node_id]
        records.append(
            {
                "evidence_id": f"osm-signal-evidence:{node_id}",
                "type": "signal_observation",
                "id": node_id,
                "fields": {
                    "node_id": node_id,
                    "signalized": True,
                    "osm_tags": _mapping(node.tags),
                },
            }
        )
    for finding in extraction.restrictions:
        records.append(
            {
                "evidence_id": f"osm-restriction-evidence:{finding.relation_id}",
                "type": "osm_restriction_observation",
                "id": finding.relation_id,
                "fields": finding.to_dict(),
            }
        )

    uturn_ids: list[str] = []
    for upstream in extraction.segments:
        for downstream in extraction.segments:
            if (
                upstream.head_node_id == downstream.tail_node_id
                and upstream.source_way_id == downstream.source_way_id
                and upstream.source_node_refs == tuple(reversed(downstream.source_node_refs))
            ):
                movement_id = f"movement:{upstream.segment_id}->{downstream.segment_id}"
                uturn_ids.append(movement_id)
                records.append(
                    {
                        "evidence_id": f"osm-uturn-audit:{stable_hash('osm-uturn', movement_id)[:20]}",
                        "type": "turn",
                        "id": f"uturn:{stable_hash('osm-uturn', movement_id)[:20]}",
                        "fields": {
                            "upstream_link_id": upstream.segment_id,
                            "downstream_link_id": downstream.segment_id,
                            "permission": "unresolved",
                            "osm_evidence_status": "no explicit U-turn restriction or permission",
                        },
                    }
                )
    return (
        adapt_osm_like(
            {
                "network_id": network_id,
                "records": records,
            }
        ),
        tuple(sorted(set(uturn_ids))),
    )


def source_strict_config() -> CompilerConfig:
    return CompilerConfig(
        allow_road_class_defaults=False,
        allow_conservative_shared_lane_fallback=False,
        enable_explicit_lane_group_partitions=False,
        allow_default_signal_plans=False,
        allow_jam_density_default=False,
        allow_backward_wave_speed_default=False,
    )


def reviewed_candidate_config() -> CompilerConfig:
    """Return explicit uncalibrated priors for topology/control-boundary inspection."""

    return CompilerConfig(
        allow_road_class_defaults=True,
        allow_conservative_shared_lane_fallback=True,
        enable_explicit_lane_group_partitions=False,
        allow_default_signal_plans=False,
        allow_jam_density_default=True,
        allow_backward_wave_speed_default=True,
        lane_defaults=(
            ("primary", 1),
            ("residential", 1),
            ("secondary", 1),
            ("service", 1),
            ("trunk", 2),
            ("trunk_link", 1),
        ),
        speed_kph_defaults=(
            ("primary", 50.0),
            ("residential", 30.0),
            ("secondary", 40.0),
            ("service", 20.0),
            ("trunk", 60.0),
            ("trunk_link", 60.0),
        ),
        capacity_per_lane_defaults=(
            ("primary", 1800.0),
            ("residential", 1200.0),
            ("secondary", 1500.0),
            ("service", 900.0),
            ("trunk", 1800.0),
            ("trunk_link", 1800.0),
        ),
        jam_density_veh_per_km_per_lane_default=150.0,
        backward_wave_speed_mps_default=5.0,
    )


def _reviewed_assumptions() -> tuple[OSMReviewedAssumption, ...]:
    common = {
        "actor": "milestone-reviewed-policy",
        "source": "urban-cybernetics compiler prior table v1",
    }
    return (
        OSMReviewedAssumption.create(
            assumption_id="reviewed-prior:secondary:missing-lane-count",
            target_scope="road_class:secondary",
            target_field="lane_count",
            selected_value=1,
            unit="lanes_per_direction",
            reason="permit road-topology validation where OSM way 32670070 lacks lanes; requires field review",
            rule_id="link.lanes.road-class-default",
            **common,
        ),
        OSMReviewedAssumption.create(
            assumption_id="reviewed-prior:secondary:capacity",
            target_scope="road_class:secondary",
            target_field="capacity_veh_per_hour_per_lane",
            selected_value=1500.0,
            unit="vehicles_per_hour_per_lane",
            reason="reuse the existing uncalibrated compiler prior for topology-candidate inspection",
            rule_id="link.capacity.road-class-default",
            **common,
        ),
        OSMReviewedAssumption.create(
            assumption_id="reviewed-prior:trunk:capacity",
            target_scope="road_class:trunk",
            target_field="capacity_veh_per_hour_per_lane",
            selected_value=1800.0,
            unit="vehicles_per_hour_per_lane",
            reason="extend the existing primary-road compiler prior to retained trunk links for an uncalibrated candidate",
            rule_id="link.capacity.road-class-default",
            **common,
        ),
        OSMReviewedAssumption.create(
            assumption_id="reviewed-prior:trunk-link:capacity",
            target_scope="road_class:trunk_link",
            target_field="capacity_veh_per_hour_per_lane",
            selected_value=1800.0,
            unit="vehicles_per_hour_per_lane",
            reason="extend the existing primary-road compiler prior to the retained connector for an uncalibrated candidate",
            rule_id="link.capacity.road-class-default",
            **common,
        ),
        OSMReviewedAssumption.create(
            assumption_id="reviewed-prior:all-links:jam-density",
            target_scope="all_retained_links",
            target_field="jam_density_veh_per_km_per_lane",
            selected_value=150.0,
            unit="vehicles_per_kilometre_per_lane",
            reason="existing compiler prior used only to inspect finite-storage and topology contracts",
            rule_id="link.storage.observed-or-default",
            **common,
        ),
        OSMReviewedAssumption.create(
            assumption_id="reviewed-prior:all-links:backward-wave-speed",
            target_scope="all_retained_links",
            target_field="backward_wave_speed_mps",
            selected_value=5.0,
            unit="metres_per_second",
            reason="existing compiler prior used only to inspect wave-lag and topology contracts",
            rule_id="link.storage.observed-or-default",
            **common,
        ),
        OSMReviewedAssumption.create(
            assumption_id="reviewed-policy:queue-representation:shared-link-fifo",
            target_scope="operational_complex",
            target_field="queue_representation",
            selected_value="shared_link_fifo",
            unit="representation_mode",
            reason="conservative executable representation selected because detailed lane allocation is insufficiently supported by evidence",
            rule_id="lane-group.shared-fallback",
            **common,
        ),
        OSMReviewedAssumption.create(
            assumption_id="reviewed-policy:signal-defaults:disabled",
            target_scope="operational_complex",
            target_field="allow_default_signal_plans",
            selected_value=False,
            unit="boolean_policy",
            reason="preserve observed signalisation without inventing control timing",
            rule_id="signal.osm-observation-unresolved",
            **common,
        ),
    )


def _reviewed_uturn_overrides(movement_ids: tuple[str, ...]) -> tuple[CompilerOverride, ...]:
    return tuple(
        CompilerOverride.create(
            override_id=f"reviewed:no-uturn:{stable_hash('reviewed-no-uturn', movement_id)[:20]}",
            target_artifact_id=movement_id,
            target_field="permitted",
            replacement_value=False,
            actor="milestone-reviewed-policy",
            source="boreenmanna-south-link-operational-boundary-v1",
            reason="exclude immediate reversal on the same physical OSM way; OSM provides no affirmative U-turn allocation",
            precedence=100,
        )
        for movement_id in movement_ids
    )


@dataclass(frozen=True, slots=True)
class CorkJunctionEvidencePackage:
    source: OSMFileEvidence
    extraction_config: OSMJunctionExtractionConfig
    extraction: OSMJunctionExtraction
    normalized_source_json: str
    source_strict_bundle: CompilerEvidenceBundle
    reviewed_candidate_bundle: CompilerEvidenceBundle
    reviewed_assumptions: tuple[OSMReviewedAssumption, ...]
    reviewed_overrides: tuple[CompilerOverride, ...]
    schema_version: str = CORK_JUNCTION_PACKAGE_SCHEMA_VERSION
    package_hash: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != CORK_JUNCTION_PACKAGE_SCHEMA_VERSION:
            raise CorkJunctionPackageIntegrityError("unsupported Cork junction package schema")
        object.__setattr__(
            self,
            "normalized_source_json",
            canonical_json(json.loads(self.normalized_source_json)),
        )
        if self.extraction.source_parsed_content_hash != self.source.parsed_content_hash:
            raise CorkJunctionPackageIntegrityError("source and extraction parsed hashes disagree")
        if self.extraction.extraction_config_hash != self.extraction_config.config_hash:
            raise CorkJunctionPackageIntegrityError("extraction configuration hash mismatch")
        normalized_hash = stable_hash(
            "normalized-source-graph", json.loads(self.normalized_source_json)
        )
        for bundle in (self.source_strict_bundle, self.reviewed_candidate_bundle):
            if bundle.normalized_evidence_hash != normalized_hash:
                raise CorkJunctionPackageIntegrityError(
                    "compiler bundle normalized evidence does not match package"
                )
        expected = stable_hash("cork-junction-evidence-package", self._payload())
        if self.package_hash and self.package_hash != expected:
            raise CorkJunctionPackageIntegrityError("Cork junction package hash mismatch")
        object.__setattr__(self, "package_hash", expected)

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source": self.source.to_dict(),
            "extraction_config": self.extraction_config.to_dict(),
            "extraction_config_hash": self.extraction_config.config_hash,
            "extraction": self.extraction.to_dict(),
            "normalized_source": json.loads(self.normalized_source_json),
            "source_strict_bundle": self.source_strict_bundle.to_dict(),
            "reviewed_candidate_bundle": self.reviewed_candidate_bundle.to_dict(),
            "reviewed_assumptions": [
                item.to_dict() for item in self.reviewed_assumptions
            ],
            "reviewed_overrides": [item.to_dict() for item in self.reviewed_overrides],
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "package_hash": self.package_hash}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            source=OSMFileEvidence.from_dict(payload["source"]),  # type: ignore[arg-type]
            extraction_config=OSMJunctionExtractionConfig.from_dict(
                payload["extraction_config"]  # type: ignore[arg-type]
            ),
            extraction=OSMJunctionExtraction.from_dict(payload["extraction"]),  # type: ignore[arg-type]
            normalized_source_json=canonical_json(payload["normalized_source"]),
            source_strict_bundle=CompilerEvidenceBundle.from_dict(
                payload["source_strict_bundle"]  # type: ignore[arg-type]
            ),
            reviewed_candidate_bundle=CompilerEvidenceBundle.from_dict(
                payload["reviewed_candidate_bundle"]  # type: ignore[arg-type]
            ),
            reviewed_assumptions=tuple(
                OSMReviewedAssumption.from_dict(item)
                for item in payload.get("reviewed_assumptions", [])  # type: ignore[arg-type]
            ),
            reviewed_overrides=tuple(
                CompilerOverride.from_dict(item)
                for item in payload.get("reviewed_overrides", [])  # type: ignore[arg-type]
            ),
            schema_version=str(payload["schema_version"]),
            package_hash=str(payload.get("package_hash", "")),
        )

    @classmethod
    def from_json(cls, serialised: str) -> Self:
        payload = json.loads(serialised)
        if not isinstance(payload, dict):
            raise CorkJunctionPackageIntegrityError("package JSON must be an object")
        return cls.from_dict(payload)


@dataclass(frozen=True, slots=True)
class CorkJunctionMilestoneRun:
    package: CorkJunctionEvidencePackage
    compiler_source: SourceNetworkEvidence
    normalized_source: NormalizedSourceGraph
    source_strict_result: CompilationResult
    reviewed_candidate_result: CompilationResult


def compile_boreenmanna_milestone(
    path: str | Path,
    *,
    extraction_config: OSMJunctionExtractionConfig | None = None,
) -> CorkJunctionMilestoneRun:
    source = parse_osm_xml(path)
    config = extraction_config or boreenmanna_extraction_config()
    extraction = extract_operational_junction(source, config)
    compiler_source, uturn_ids = extraction_to_source_evidence(source, extraction)
    normalized = normalize_source(compiler_source)
    strict = compile_network(compiler_source, config=source_strict_config())
    overrides = _reviewed_uturn_overrides(uturn_ids)
    reviewed = compile_network(
        compiler_source,
        config=reviewed_candidate_config(),
        overrides=overrides,
    )
    package = CorkJunctionEvidencePackage(
        source=source,
        extraction_config=config,
        extraction=extraction,
        normalized_source_json=canonical_json(normalized.to_dict()),
        source_strict_bundle=strict.evidence_bundle,
        reviewed_candidate_bundle=reviewed.evidence_bundle,
        reviewed_assumptions=_reviewed_assumptions(),
        reviewed_overrides=overrides,
    )
    return CorkJunctionMilestoneRun(
        package=package,
        compiler_source=compiler_source,
        normalized_source=normalized,
        source_strict_result=strict,
        reviewed_candidate_result=reviewed,
    )


def write_cork_junction_package(
    run: CorkJunctionMilestoneRun, path: str | Path
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(run.package.to_json(), encoding="utf-8")
    return output
