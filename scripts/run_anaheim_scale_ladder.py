#!/usr/bin/env python3
"""Run the Anaheim UC-default assumption-profile scale ladder."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from urban_cybernetics.canonical_validation.anaheim_physical_profile import (
    build_anaheim_uc_default_physical_profile,
)
from urban_cybernetics.canonical_validation.anaheim_readiness import (
    build_anaheim_assumption_profile_scale_ladder_report,
    build_anaheim_readiness_report,
)
from urban_cybernetics.canonical_validation.sioux_falls_readiness import (
    SiouxFallsReplayPolicy,
)


DEFAULT_BOUNDED_RUNGS = (
    1_000,
    5_000,
    10_000,
    25_000,
    50_000,
    100_000,
)
DEFAULT_JSON_OUTPUT = Path(
    "docs/validation/anaheim_scale_ladder_profile_v1.json"
)
DEFAULT_MARKDOWN_OUTPUT = Path(
    "docs/validation/anaheim_scale_ladder_profile_v1.md"
)
DEFAULT_PROFILE_MARKDOWN_OUTPUT = Path(
    "docs/validation/anaheim_uc_default_physical_profile_v1.md"
)


def main() -> None:
    """Run the scale ladder and write JSON and Markdown artifacts."""

    parser = argparse.ArgumentParser(
        description=(
            "Run bounded Anaheim demand scales under "
            "AnaheimPhysicalProfile_UC_Default_v1."
        )
    )
    parser.add_argument("--tick-limit", type=int, default=20_000)
    parser.add_argument(
        "--tick-duration-seconds",
        type=float,
        default=2.0,
        help=(
            "Anaheim defaults to a 2-second parity tick because the shortest "
            "feet-based free-flow travel time is about 3.27 seconds."
        ),
    )
    parser.add_argument(
        "--max-runtime-seconds-per-rung",
        type=float,
        default=180.0,
        help=(
            "Severe-runtime guard per rung. Use 0 to disable the guard and run "
            "until validation completion or process interruption."
        ),
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_MARKDOWN_OUTPUT)
    parser.add_argument(
        "--profile-markdown",
        type=Path,
        default=DEFAULT_PROFILE_MARKDOWN_OUTPUT,
    )
    parser.add_argument("--packets", type=int, nargs="+", default=list(DEFAULT_BOUNDED_RUNGS))
    parser.add_argument(
        "--skip-full-demand",
        action="store_true",
        help="Do not append the canonical full-demand rung after bounded rungs.",
    )
    parser.add_argument(
        "--determinism-certified-packet-count",
        type=int,
        default=10_000,
        help=(
            "Largest packet count with repeated exact-run determinism evidence. "
            "When set, larger rungs may skip exact replay by explicit policy."
        ),
    )
    parser.add_argument(
        "--exact-replay-packet-limit",
        type=int,
        default=10_000,
        help="Packet rungs at or below this size always run exact replay.",
    )
    args = parser.parse_args()

    runtime_guard = (
        None
        if args.max_runtime_seconds_per_rung == 0
        else args.max_runtime_seconds_per_rung
    )
    profile = build_anaheim_uc_default_physical_profile()
    readiness = build_anaheim_readiness_report(
        physical_profile=profile,
        tick_duration_seconds=args.tick_duration_seconds,
    )
    report = build_anaheim_assumption_profile_scale_ladder_report(
        physical_profile=profile,
        bounded_packet_rungs=tuple(args.packets),
        tick_limit=args.tick_limit,
        tick_duration_seconds=args.tick_duration_seconds,
        include_full_demand_run=not args.skip_full_demand,
        max_runtime_seconds_per_rung=runtime_guard,
        replay_policy=SiouxFallsReplayPolicy(
            exact_replay_packet_limit=args.exact_replay_packet_limit,
            determinism_certified_packet_count=(
                args.determinism_certified_packet_count
            ),
        ),
    )
    payload: dict[str, Any] = report.status_payload()
    payload["artifact_generated_at_utc"] = datetime.now(UTC).isoformat()
    payload["runner"] = {
        "script": "scripts/run_anaheim_scale_ladder.py",
        "tick_limit": args.tick_limit,
        "tick_duration_seconds": args.tick_duration_seconds,
        "max_runtime_seconds_per_rung": runtime_guard,
        "determinism_certified_packet_count": (
            args.determinism_certified_packet_count
        ),
        "exact_replay_packet_limit": args.exact_replay_packet_limit,
        "include_full_demand_run": not args.skip_full_demand,
    }
    payload["readiness_report"] = readiness.status_payload()
    payload["physical_profile_summary"] = asdict(profile.summary())
    payload["rung_reports"] = [_enrich_rung(rung) for rung in payload["rung_reports"]]

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.write_text(
        _render_ladder_markdown(payload),
        encoding="utf-8",
    )
    args.profile_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.profile_markdown.write_text(
        _render_profile_markdown(profile.status_payload(), readiness.status_payload()),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


def _enrich_rung(rung: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(rung)
    primary_seconds = float(enriched["primary_engine_runtime_seconds"])
    event_count = int(enriched["event_count"])
    completed = int(enriched["completed_packet_count"])
    enriched["canonical_events"] = event_count
    enriched["setup_wall_clock_seconds"] = 0.0
    enriched["primary_stepping_wall_clock_seconds"] = primary_seconds
    enriched["validation_wall_clock_seconds"] = (
        float(enriched["validation_projection_runtime_seconds"])
        + float(enriched["validator_runtime_seconds"])
    )
    enriched["events_per_sec_primary"] = (
        event_count / primary_seconds if primary_seconds > 0 else None
    )
    enriched["packets_per_sec_primary"] = (
        completed / primary_seconds if primary_seconds > 0 else None
    )
    enriched["events_per_packet"] = (
        event_count / completed if completed > 0 else None
    )
    enriched["stop_reason"] = enriched["failure_reason"] or "completed"
    return enriched


def _render_ladder_markdown(payload: dict[str, Any]) -> str:
    readiness = payload["readiness_report"]
    rungs = payload["rung_reports"]
    lines = [
        "# Anaheim UC Default Scale Ladder Profile v1",
        "",
        "Status: executable engineering-assumption scale ladder evidence.",
        "",
        "This artifact records bounded Anaheim demand-scale runs using "
        "`AnaheimPhysicalProfile_UC_Default_v1`. It is not empirical "
        "calibration and does not claim external canonical Anaheim validation.",
        "",
        "## Readiness",
        "",
        f"- Topology load: `{readiness['topology_load_status']['status']}`",
        f"- Demand load: `{readiness['demand_load_status']['status']}`",
        f"- Physical metadata: `{readiness['physical_metadata_status']['status']}`",
        "- Movement/junction support: "
        f"`{readiness['movement_junction_support_status']['status']}`",
        "- Parity initialization: "
        f"`{readiness['parity_initialization_status']['status']}`",
        f"- Nodes: `{readiness['topology_node_count']}`",
        f"- Links: `{readiness['topology_link_count']}`",
        f"- OD pairs: `{readiness['od_pair_count']}`",
        f"- Full demand requested packets: "
        f"`{readiness['full_demand_requested_packet_count']}`",
        "",
        "## Runner",
        "",
        f"- Profile: `{payload['physical_profile_id']}`",
        f"- Profile version: `{payload['physical_profile_version']}`",
        f"- Profile hash: `{payload['physical_profile_hash']}`",
        f"- Topology hash: `{payload['topology_hash']}`",
        f"- Exact replay packet limit: "
        f"`{payload['runner']['exact_replay_packet_limit']}`",
        f"- Tick duration: `{payload['runner']['tick_duration_seconds']}` seconds",
        f"- Determinism certified packet count: "
        f"`{payload['runner']['determinism_certified_packet_count']}`",
        f"- Full demand run attempted: `{_yes_no(payload['full_demand_run_attempted'])}`",
        f"- Stopped early: `{_yes_no(payload['stopped_early'])}`",
        f"- Stop reason: `{payload['stop_reason'] or 'none'}`",
        "",
        "## Results Table",
        "",
        "| Rung | Requested | Submitted | Instantiated | Completed | "
        "Unresolved | Ticks | Events | Primary s | Validation s | Total s | "
        "Events/s | Packets/s | Events/packet | Validation | Replay | Stop reason |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        "---: | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for rung in rungs:
        lines.append(
            "| {rung_label} | {requested_packet_count} | "
            "{submitted_packet_count} | {instantiated_packet_count} | "
            "{completed_packet_count} | {unresolved_packet_count} | "
            "{ticks_run} | {canonical_events} | "
            "{primary_stepping_wall_clock_seconds:.3f} | "
            "{validation_wall_clock_seconds:.3f} | "
            "{total_runtime_seconds:.3f} | {events_per_sec_primary} | "
            "{packets_per_sec_primary} | {events_per_packet} | "
            "{internal_validation_status} | {replay_status} | "
            "{stop_reason} |".format(**_format_rung(rung))
        )
    lines.extend(
        [
            "",
            "## Claim Boundary",
            "",
            "Safe claim: these are internal engineering-assumption Anaheim runs. "
            "`passed_exact_replay` means an actual rerun matched; "
            "`skipped_by_policy_after_determinism_certification` is not an "
            "exact replay pass.",
            "",
            "Not safe: this is not empirical calibration, not a benchmark "
            "assignment comparison, and not a claim that Anaheim junction "
            "semantics have been externally reviewed.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_profile_markdown(
    profile_payload: dict[str, Any],
    readiness_payload: dict[str, Any],
) -> str:
    summary = profile_payload["summary"]
    lines = [
        "# Anaheim UC Default Physical Profile v1",
        "",
        "Status: reproducible engineering-assumption profile, not empirical calibration.",
        "",
        "## Identity",
        "",
        f"- Profile: `{profile_payload['profile_id']}`",
        f"- Version: `{profile_payload['version']}`",
        f"- Profile hash: `{profile_payload['profile_hash']}`",
        f"- Topology hash: `{profile_payload['topology_hash']}`",
        f"- Source network SHA-256: `{profile_payload['source_file_sha256']}`",
        "",
        "## Source Units",
        "",
        "- Length: `feet` in the TNTP source, converted to metres internally.",
        "- Time: `minutes` in the TNTP source, converted to seconds internally.",
        "- Capacity: `vehicles_per_hour` retained as the per-link capacity field.",
        "- Parity tick: `2` seconds by default for Anaheim because the shortest feet-based free-flow time is about 3.27 seconds.",
        "- Lane count: `1` as an engineering interpretation because the TNTP file does not provide lanes.",
        "",
        "## Assumptions",
        "",
    ]
    for assumption in profile_payload["assumptions"]:
        lines.append(
            f"- `{assumption['field_name']}` = `{assumption['value']}` "
            f"({assumption['provenance_label']}): {assumption['note']}"
        )
    lines.extend(
        [
            "",
            "## Derived Metadata",
            "",
            f"- Backward wave speed: `{summary['backward_wave_speed_mps']}` m/s",
            "- Jam density: triangular FD consistency, `kj = q(v + w) / (v * w)`.",
            "- Storage: `floor(length_km * lane_count * kj)`.",
            f"- Links: `{summary['link_count']}`",
            f"- Jam density range: "
            f"`{summary['min_jam_density_veh_per_km_per_lane']:.6f}` to "
            f"`{summary['max_jam_density_veh_per_km_per_lane']:.6f}` veh/km/lane",
            f"- Storage range: `{summary['min_storage_capacity_packets']}` to "
            f"`{summary['max_storage_capacity_packets']}` packets",
            "",
            "## Readiness Boundary",
            "",
            f"- Topology load: `{readiness_payload['topology_load_status']['status']}`",
            f"- Demand load: `{readiness_payload['demand_load_status']['status']}`",
            f"- Physical metadata: `{readiness_payload['physical_metadata_status']['status']}`",
            "- Movement/junction support: "
            f"`{readiness_payload['movement_junction_support_status']['status']}`",
            "- Parity initialization: "
            f"`{readiness_payload['parity_initialization_status']['status']}`",
            "",
        ]
    )
    return "\n".join(lines)


def _format_rung(rung: dict[str, Any]) -> dict[str, Any]:
    formatted = dict(rung)
    for key in (
        "events_per_sec_primary",
        "packets_per_sec_primary",
        "events_per_packet",
    ):
        formatted[key] = (
            "n/a" if formatted[key] is None else f"{float(formatted[key]):.3f}"
        )
    formatted["stop_reason"] = formatted["stop_reason"] or "none"
    return formatted


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    main()
