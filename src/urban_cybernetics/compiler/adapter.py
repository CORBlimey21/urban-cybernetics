# SPDX-License-Identifier: MPL-2.0
"""Narrow OSM-like fixture adapter and deterministic source normalization."""

from __future__ import annotations

from collections.abc import Mapping

from .model import (
    NormalizedField,
    NormalizedRecord,
    NormalizedSourceGraph,
    SourceField,
    SourceNetworkEvidence,
    SourceRecord,
    canonical_json,
    stable_hash,
)


_FLOAT_FIELDS = frozenset(
    (
        "length_m",
        "speed_mps",
        "maxspeed_kph",
        "capacity_veh_per_hour_per_lane",
        "capacity_total_veh_per_hour",
        "jam_density_veh_per_km_per_lane",
        "backward_wave_speed_mps",
    )
)
_INT_FIELDS = frozenset(
    (
        "lanes",
        "lanes:forward",
        "lane_count",
        "capacity_per_tick",
        "cycle_ticks",
        "offset_ticks",
        "duration_ticks",
        "priority_weight",
    )
)
_BOOL_FIELDS = frozenset(("oneway", "queue_partition", "signalized"))
_STRING_LIST_FIELDS = frozenset(
    (
        "allowed_movement_ids",
        "controlled_movement_ids",
        "stage_ids",
        "permitted_movement_ids",
        "lane_indices",
    )
)


def adapt_osm_like(payload: Mapping[str, object]) -> SourceNetworkEvidence:
    """Adapt explicit fixture records into the canonical source-evidence schema.

    The adapter intentionally performs no semantic defaults. A fixture may use a
    ``fields`` mapping for normal values or a list of ``{name, value, evidence_id}``
    objects when duplicate/conflicting evidence must be retained.
    """

    network_id = payload.get("network_id")
    records_payload = payload.get("records")
    if not isinstance(network_id, str) or not network_id:
        raise ValueError("OSM-like payload requires a non-empty network_id")
    if not isinstance(records_payload, list):
        raise ValueError("OSM-like payload records must be a list")

    records: list[SourceRecord] = []
    for index, record_payload in enumerate(records_payload):
        if not isinstance(record_payload, Mapping):
            raise ValueError(f"record {index} must be an object")
        evidence_id = record_payload.get("evidence_id")
        record_type = record_payload.get("record_type", record_payload.get("type"))
        source_id = record_payload.get("source_id", record_payload.get("id"))
        if not all(isinstance(item, str) and item for item in (evidence_id, record_type, source_id)):
            raise ValueError(
                f"record {index} requires non-empty evidence_id, record_type/type, and source_id/id"
            )
        fields_payload = record_payload.get("fields", record_payload.get("tags", {}))
        fields = _adapt_fields(str(evidence_id), fields_payload)
        records.append(
            SourceRecord(
                evidence_id=str(evidence_id),
                record_type=str(record_type),
                source_id=str(source_id),
                fields=fields,
            )
        )
    return SourceNetworkEvidence(network_id=network_id, records=tuple(records))


def _adapt_fields(record_evidence_id: str, payload: object) -> tuple[SourceField, ...]:
    items: list[tuple[str, object, str | None]] = []
    if isinstance(payload, Mapping):
        items.extend((str(name), value, None) for name, value in payload.items())
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            if not isinstance(item, Mapping) or "name" not in item or "value" not in item:
                raise ValueError(
                    f"field {index} for {record_evidence_id} requires name and value"
                )
            explicit_id = item.get("evidence_id")
            if explicit_id is not None and (not isinstance(explicit_id, str) or not explicit_id):
                raise ValueError("field evidence_id must be a non-empty string")
            items.append((str(item["name"]), item["value"], explicit_id))
    else:
        raise ValueError(f"fields for {record_evidence_id} must be an object or list")

    # Generated IDs depend on semantic field content, never incidental input order.
    ranked = sorted(
        enumerate(items),
        key=lambda pair: (pair[1][0], canonical_json(pair[1][1]), pair[1][2] or ""),
    )
    occurrence: dict[tuple[str, str], int] = {}
    generated_by_index: dict[int, str] = {}
    for original_index, (name, value, explicit_id) in ranked:
        if explicit_id is not None:
            generated_by_index[original_index] = explicit_id
            continue
        key = (name, canonical_json(value))
        rank = occurrence.get(key, 0)
        occurrence[key] = rank + 1
        suffix = stable_hash("source-field-id", {"name": name, "value": value, "rank": rank})[:16]
        generated_by_index[original_index] = f"{record_evidence_id}:field:{suffix}"
    return tuple(
        SourceField.create(generated_by_index[index], name, value)
        for index, (name, value, _) in enumerate(items)
    )


def normalize_source(source: SourceNetworkEvidence) -> NormalizedSourceGraph:
    """Parse source fields without selecting authoritative simulation semantics."""

    records = tuple(
        NormalizedRecord(
            evidence_id=record.evidence_id,
            record_type=record.record_type,
            source_id=record.source_id,
            fields=tuple(_normalize_field(item) for item in record.fields),
        )
        for record in source.records
    )
    return NormalizedSourceGraph(
        network_id=source.network_id,
        source_evidence_hash=source.evidence_hash,
        records=records,
    )


def _normalize_field(field: SourceField) -> NormalizedField:
    raw = field.raw_value
    try:
        if field.name == "maxspeed":
            value = _parse_maxspeed_kph(raw)
        elif field.name in _FLOAT_FIELDS:
            value = _parse_float(raw)
        elif field.name in _INT_FIELDS:
            value = _parse_int(raw, allow_zero=field.name == "offset_ticks")
        elif field.name in _BOOL_FIELDS:
            value = _parse_bool(raw)
        elif field.name in _STRING_LIST_FIELDS:
            value = _parse_list(field.name, raw)
        else:
            value = _parse_scalar_or_list(raw)
    except (TypeError, ValueError) as exc:
        return NormalizedField(
            evidence_id=field.evidence_id,
            name=field.name,
            raw_value_json=field.raw_value_json,
            normalized_value_json=None,
            parse_status="malformed",
            parse_note=str(exc),
        )
    return NormalizedField(
        evidence_id=field.evidence_id,
        name=field.name,
        raw_value_json=field.raw_value_json,
        normalized_value_json=canonical_json(value),
        parse_status="valid",
    )


def _parse_float(value: object) -> float:
    if isinstance(value, bool):
        raise TypeError("boolean is not numeric evidence")
    parsed = float(value)  # type: ignore[arg-type]
    if not parsed > 0:
        raise ValueError("numeric evidence must be positive")
    return parsed


def _parse_int(value: object, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool):
        raise TypeError("boolean is not integer evidence")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError("integer evidence must be integral")
    parsed = int(value)  # type: ignore[arg-type]
    if parsed < 0 or (parsed == 0 and not allow_zero):
        raise ValueError(
            "integer evidence must be non-negative"
            if allow_zero
            else "integer evidence must be positive"
        )
    return parsed


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("yes", "true", "1"):
            return True
        if lowered in ("no", "false", "0"):
            return False
    raise ValueError("boolean evidence must be yes/no, true/false, or 1/0")


def _parse_list(name: str, value: object) -> list[object]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{name} must be a list")
    if name == "lane_indices":
        parsed = [_parse_int(item) for item in value]
    else:
        parsed = [str(item) for item in value]
        if any(not item for item in parsed):
            raise ValueError(f"{name} must contain non-empty strings")
    return parsed


def _parse_scalar_or_list(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_parse_scalar_or_list(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _parse_scalar_or_list(item) for key, item in value.items()}
    raise TypeError(f"unsupported source value type: {type(value).__name__}")


def _parse_maxspeed_kph(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _parse_float(value)
    if not isinstance(value, str):
        raise TypeError("maxspeed must be numeric text")
    text = value.strip().lower()
    if text.endswith("mph"):
        return _parse_float(text[:-3].strip()) * 1.609344
    if text.endswith("km/h"):
        text = text[:-4].strip()
    return _parse_float(text)
