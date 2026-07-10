#!/usr/bin/env python3
"""Run the Sioux Falls UC-default assumption-profile scale ladder."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from urban_cybernetics.canonical_validation.sioux_falls_readiness import (
    SiouxFallsReplayPolicy,
    build_sioux_falls_assumption_profile_scale_ladder_report,
)


DEFAULT_BOUNDED_RUNGS = (
    24,
    100,
    1_000,
    5_000,
    10_000,
    25_000,
    50_000,
    100_000,
)
DEFAULT_JSON_OUTPUT = Path(
    "docs/validation/sioux_falls_uc_default_scale_ladder_v1.json"
)
DEFAULT_MARKDOWN_OUTPUT = Path(
    "docs/validation/sioux_falls_uc_default_scale_ladder_v1.md"
)


def main() -> None:
    """Run the scale ladder and write reproducible JSON and Markdown artifacts."""

    parser = argparse.ArgumentParser(
        description=(
            "Run bounded Sioux Falls demand scales under "
            "SiouxFallsPhysicalProfile_UC_Default_v1."
        )
    )
    parser.add_argument("--tick-limit", type=int, default=20_000)
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
    parser.add_argument("--packets", type=int, nargs="+", default=list(DEFAULT_BOUNDED_RUNGS))
    parser.add_argument(
        "--skip-full-demand",
        action="store_true",
        help="Do not append the canonical full-demand rung after bounded rungs.",
    )
    parser.add_argument(
        "--determinism-certified-packet-count",
        type=int,
        default=None,
        help=(
            "Largest packet count with repeated exact-run determinism evidence. "
            "When set, larger rungs may skip exact replay by explicit policy."
        ),
    )
    parser.add_argument(
        "--exact-replay-packet-limit",
        type=int,
        default=1_000,
        help="Packet rungs at or below this size always run exact replay.",
    )
    args = parser.parse_args()

    runtime_guard = (
        None
        if args.max_runtime_seconds_per_rung == 0
        else args.max_runtime_seconds_per_rung
    )
    report = build_sioux_falls_assumption_profile_scale_ladder_report(
        bounded_packet_rungs=tuple(args.packets),
        tick_limit=args.tick_limit,
        max_runtime_seconds_per_rung=runtime_guard,
        replay_policy=SiouxFallsReplayPolicy(
            exact_replay_packet_limit=args.exact_replay_packet_limit,
            determinism_certified_packet_count=(
                args.determinism_certified_packet_count
            ),
        ),
        include_full_demand_run=not args.skip_full_demand,
    )
    payload: dict[str, Any] = report.status_payload()
    payload["artifact_generated_at_utc"] = datetime.now(UTC).isoformat()
    payload["runner"] = {
        "script": "scripts/run_sioux_falls_scale_ladder.py",
        "tick_limit": args.tick_limit,
        "max_runtime_seconds_per_rung": runtime_guard,
        "determinism_certified_packet_count": (
            args.determinism_certified_packet_count
        ),
        "exact_replay_packet_limit": args.exact_replay_packet_limit,
        "include_full_demand_run": not args.skip_full_demand,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.write_text(
        _render_markdown(payload),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


def _render_markdown(payload: dict[str, Any]) -> str:
    rungs = payload["rung_reports"]
    lines = [
        "# Sioux Falls UC Default Scale Ladder v1",
        "",
        "Status: executable assumption-profile scale ladder evidence.",
        "",
        "This artifact records bounded Sioux Falls demand-scale runs using "
        "`SiouxFallsPhysicalProfile_UC_Default_v1`. It is not empirical "
        "calibration and does not claim canonical Sioux Falls validation.",
        "",
        "## Runner",
        "",
        "- Command: "
        "`.venv/bin/python scripts/run_sioux_falls_scale_ladder.py "
        "--tick-limit {tick_limit} --max-runtime-seconds-per-rung {runtime_guard}`".format(
            tick_limit=payload["runner"]["tick_limit"],
            runtime_guard=payload["runner"]["max_runtime_seconds_per_rung"],
        ),
        f"- Profile: `{payload['physical_profile_id']}`",
        f"- Profile version: `{payload['physical_profile_version']}`",
        f"- Profile hash: `{payload['physical_profile_hash']}`",
        f"- Topology hash: `{payload['topology_hash']}`",
        f"- Full demand requested packet count: "
        f"`{payload['full_demand_requested_packet_count']}`",
        f"- Determinism certified packet count: "
        f"`{payload['runner']['determinism_certified_packet_count']}`",
        f"- Exact replay packet limit: "
        f"`{payload['runner']['exact_replay_packet_limit']}`",
        f"- Full demand run attempted: `{_yes_no(payload['full_demand_run_attempted'])}`",
        f"- Stopped early: `{_yes_no(payload['stopped_early'])}`",
        f"- Stop reason: `{payload['stop_reason'] or 'none'}`",
        "",
        "## Results Table",
        "",
        "| Rung | Requested | Submitted | Instantiated | Completed | "
        "Unresolved | Ticks | Primary s | Projection s | Validators s | "
        "Replay s | Total s | Events | Internal validation | Replay status | "
        "Scale status | Failure reason |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        "---: | ---: | ---: | --- | --- | --- | --- |",
    ]
    for rung in rungs:
        lines.append(
            "| {rung_label} | {requested_packet_count} | "
            "{submitted_packet_count} | {instantiated_packet_count} | "
            "{completed_packet_count} | {unresolved_packet_count} | "
            "{ticks_run} | {primary_engine_runtime_seconds:.3f} | "
            "{validation_projection_runtime_seconds:.3f} | "
            "{validator_runtime_seconds:.3f} | {replay_runtime_seconds} | "
            "{total_runtime_seconds:.3f} | {event_count} | "
            "{internal_validation_status} | {replay_status} | "
            "{scale_status} | {failure_reason} |".format(
                **_format_rung(rung)
            )
        )
    lines.extend(
        [
            "",
            "## Claim Boundary",
            "",
            "Safe claim: the listed rungs are internal engineering-assumption "
            "runs with internal validation and replay evidence reported as "
            "separate statuses. `passed_exact_replay` means an actual rerun "
            "matched; `skipped_by_policy_after_determinism_certification` is "
            "not an exact replay pass.",
            "",
            "Not safe: this is not an empirical calibration, canonical Sioux "
            "Falls validation, or external reference comparison.",
            "",
        ]
    )
    return "\n".join(lines)


def _format_rung(rung: dict[str, Any]) -> dict[str, Any]:
    formatted = dict(rung)
    formatted["runtime_seconds"] = float(formatted["runtime_seconds"])
    formatted["primary_engine_runtime_seconds"] = float(
        formatted["primary_engine_runtime_seconds"]
    )
    formatted["validation_projection_runtime_seconds"] = float(
        formatted["validation_projection_runtime_seconds"]
    )
    formatted["validator_runtime_seconds"] = float(
        formatted["validator_runtime_seconds"]
    )
    formatted["total_runtime_seconds"] = float(formatted["total_runtime_seconds"])
    replay_seconds = formatted["replay_runtime_seconds"]
    formatted["replay_runtime_seconds"] = (
        "n/a" if replay_seconds is None else f"{float(replay_seconds):.3f}"
    )
    formatted["failure_reason"] = formatted["failure_reason"] or "none"
    for key, value in tuple(formatted.items()):
        if isinstance(value, bool):
            formatted[key] = _yes_no(value)
    return formatted


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    main()
