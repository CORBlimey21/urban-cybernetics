"""Deliberately mixed-quality fixtures for the first compiler vertical slice."""

from __future__ import annotations

from copy import deepcopy

from .adapter import adapt_osm_like
from .model import CompilerOverride, SourceNetworkEvidence


def fixture_a_payload() -> dict[str, object]:
    """Mixed provenance, warnings, legacy resources, partitions, and signals."""

    records: list[dict[str, object]] = [
        {"evidence_id": f"node-evidence:{node}", "type": "node", "id": node}
        for node in ("A", "B", "J1", "C", "D", "J2", "E", "F")
    ]
    records.extend(
        (
            _link(
                "U1",
                "A",
                "J1",
                highway="primary",
                length_m=10.0,
                lane_count=1,
                speed_mps=10.0,
                capacity_veh_per_hour_per_lane=3600.0,
                jam_density_veh_per_km_per_lane=200.0,
                backward_wave_speed_mps=5.0,
            ),
            _link(
                "U2",
                "B",
                "J1",
                highway="residential",
                length_m=10.0,
                speed_mps=10.0,
                capacity_veh_per_hour_per_lane=1200.0,
            ),
            _link(
                "M",
                "J1",
                "J2",
                highway="secondary",
                length_m=10.0,
                lanes=2,
                oneway=False,
                maxspeed=36,
                capacity_total_veh_per_hour=3000.0,
            ),
            _link(
                "X",
                "J1",
                "C",
                highway="residential",
                length_m=10.0,
                lanes=1,
                maxspeed="signals",
            ),
            _link(
                "V",
                "D",
                "J2",
                highway="service",
                length_m=10.0,
                lanes=1,
                maxspeed_kph=36.0,
            ),
            _link(
                "O1",
                "J2",
                "E",
                highway="primary",
                length_m=10.0,
                lane_count=1,
                speed_mps=5.0,
                capacity_veh_per_hour_per_lane=3600.0,
                jam_density_veh_per_km_per_lane=200.0,
                backward_wave_speed_mps=5.0,
            ),
            _link(
                "O2",
                "J2",
                "F",
                highway="secondary",
                length_m=10.0,
                lanes=1,
                maxspeed_kph=36.0,
            ),
        )
    )
    records.extend(
        (
            {
                "evidence_id": "turn-evidence:U2-X:prohibit",
                "type": "turn",
                "id": "U2-X-prohibition",
                "fields": {
                    "upstream_link_id": "U2",
                    "downstream_link_id": "X",
                    "permission": "prohibit",
                },
            },
            {
                "evidence_id": "lane-evidence:J1:U1:shared",
                "type": "lane_group",
                "id": "partition:J1:U1:shared",
                "fields": {
                    "node_id": "J1",
                    "incoming_link_id": "U1",
                    "allowed_movement_ids": ["movement:U1->M", "movement:U1->X"],
                    "capacity_per_tick": 1,
                    "queue_partition": True,
                },
            },
            {
                "evidence_id": "lane-evidence:J2:M:legacy",
                "type": "lane_group",
                "id": "resource:J2:M:shared",
                "fields": {
                    "node_id": "J2",
                    "incoming_link_id": "M",
                    "allowed_movement_ids": ["movement:M->O1", "movement:M->O2"],
                    "capacity_per_tick": 1,
                    "queue_partition": False,
                },
            },
            {
                "evidence_id": "lane-evidence:J2:V:legacy",
                "type": "lane_group",
                "id": "resource:J2:V:shared",
                "fields": {
                    "node_id": "J2",
                    "incoming_link_id": "V",
                    "allowed_movement_ids": ["movement:V->O1", "movement:V->O2"],
                    "capacity_per_tick": 1,
                    "queue_partition": False,
                },
            },
            {
                "evidence_id": "signal-evidence:controller:J1",
                "type": "signal_controller",
                "id": "controller:J1",
                "fields": {
                    "node_id": "J1",
                    "signalized": True,
                    "controlled_movement_ids": [
                        "movement:U1->M",
                        "movement:U1->X",
                        "movement:U2->M",
                    ],
                    "stage_ids": ["stage:J1:go", "stage:J1:clear"],
                    "cycle_ticks": 3,
                    "offset_ticks": 0,
                },
            },
            {
                "evidence_id": "signal-evidence:stage:J1:go",
                "type": "signal_stage",
                "id": "stage:J1:go",
                "fields": {
                    "controller_id": "controller:J1",
                    "duration_ticks": 2,
                    "permitted_movement_ids": [
                        "movement:U1->M",
                        "movement:U1->X",
                        "movement:U2->M",
                    ],
                },
            },
            {
                "evidence_id": "signal-evidence:stage:J1:clear",
                "type": "signal_stage",
                "id": "stage:J1:clear",
                "fields": {
                    "controller_id": "controller:J1",
                    "duration_ticks": 1,
                    "permitted_movement_ids": [],
                },
            },
        )
    )
    for movement_id, group_id in (
        ("movement:U1->M", "signal:J1:U1-M"),
        ("movement:U1->X", "signal:J1:U1-X"),
        ("movement:U2->M", "signal:J1:U2-M"),
    ):
        records.append(
            {
                "evidence_id": f"signal-binding-evidence:{movement_id}",
                "type": "signal_binding",
                "id": f"binding:{movement_id}",
                "fields": {
                    "controller_id": "controller:J1",
                    "movement_id": movement_id,
                    "signal_group_id": group_id,
                },
            }
        )
    return {"network_id": "compiler-fixture-a", "records": records}


def fixture_a_source() -> SourceNetworkEvidence:
    return adapt_osm_like(fixture_a_payload())


def fixture_a_overrides() -> tuple[CompilerOverride, ...]:
    return (
        CompilerOverride.create(
            override_id="override:O1:speed",
            target_artifact_id="link:O1",
            target_field="free_flow_speed_mps",
            replacement_value=10.0,
            actor="fixture-author",
            source="fixture-a-review",
            reason="replace stale observed speed after an explicit evidence review",
            precedence=100,
        ),
    )


def fixture_b_source() -> SourceNetworkEvidence:
    """Signalized controller with one exact unresolved stage duration."""

    payload = deepcopy(fixture_a_payload())
    payload["network_id"] = "compiler-fixture-b"
    for record in payload["records"]:  # type: ignore[index]
        if record.get("id") == "stage:J1:clear":  # type: ignore[union-attr]
            record["fields"].pop("duration_ticks")  # type: ignore[index,union-attr]
    return adapt_osm_like(payload)


def fixture_c_source() -> SourceNetworkEvidence:
    """Contradictory observed turn semantics."""

    payload = deepcopy(fixture_a_payload())
    payload["network_id"] = "compiler-fixture-c"
    payload["records"].append(  # type: ignore[union-attr]
        {
            "evidence_id": "turn-evidence:U2-X:allow",
            "type": "turn",
            "id": "U2-X-permission",
            "fields": {
                "upstream_link_id": "U2",
                "downstream_link_id": "X",
                "permission": "allow",
            },
        }
    )
    return adapt_osm_like(payload)


def fixture_d_source() -> SourceNetworkEvidence:
    """A lane conflict that becomes executable only through an override."""

    payload = deepcopy(fixture_a_payload())
    payload["network_id"] = "compiler-fixture-d"
    for record in payload["records"]:  # type: ignore[index]
        if record.get("id") == "U2":  # type: ignore[union-attr]
            fields = record["fields"]  # type: ignore[index]
            record["fields"] = [  # type: ignore[index]
                {"name": name, "value": value}
                for name, value in fields.items()  # type: ignore[union-attr]
            ] + [
                {"name": "lane_count", "value": 1},
                {"name": "lane_count", "value": 2},
            ]
    return adapt_osm_like(payload)


def fixture_d_overrides() -> tuple[CompilerOverride, ...]:
    return (
        CompilerOverride.create(
            override_id="override:U2:lane-conflict-repair",
            target_artifact_id="link:U2",
            target_field="lane_count",
            replacement_value=1,
            actor="fixture-reviewer",
            source="field-survey-note-1",
            reason="field review confirms one directional lane",
            precedence=100,
        ),
        *fixture_a_overrides(),
    )


def fixture_e_source() -> SourceNetworkEvidence:
    """Fixture A with record and field order reversed."""

    payload = deepcopy(fixture_a_payload())
    records = list(reversed(payload["records"]))  # type: ignore[arg-type]
    for record in records:
        fields = record.get("fields")
        if isinstance(fields, dict):
            record["fields"] = dict(reversed(tuple(fields.items())))
        elif isinstance(fields, list):
            record["fields"] = list(reversed(fields))
    payload["records"] = records
    return adapt_osm_like(payload)


def _link(
    link_id: str,
    tail: str,
    head: str,
    **tags: object,
) -> dict[str, object]:
    fields = {
        "tail_node_id": tail,
        "head_node_id": head,
        "travel_direction": "forward",
        "oneway": True,
        **tags,
    }
    return {
        "evidence_id": f"link-evidence:{link_id}",
        "type": "link",
        "id": link_id,
        "fields": fields,
    }
