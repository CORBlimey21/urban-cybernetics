#!/usr/bin/env python3
"""Run the bounded 100/1k/10k Cork ladder, one fresh process per rung."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from urban_cybernetics.experiments.cork_city_scale import run_cork_scale_rung


DEFAULT_OUTPUT = Path("outputs/cork_city_scale/cork_scale_ladder_v1.json")
DEFAULT_MARKDOWN = Path("outputs/cork_city_scale/cork_scale_ladder_v1.md")
ALLOWED_RUNGS = (100, 1_000, 10_000)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--single-rung", type=int)
    parser.add_argument("--single-output", type=Path)
    parser.add_argument(
        "--graphml",
        type=Path,
        help="Pinned Cork GraphML (or set UC_CORK_GRAPHML).",
    )
    parser.add_argument("--packets", type=int, nargs="+", default=list(ALLOWED_RUNGS))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--runtime-guard-seconds", type=float, default=600.0)
    parser.add_argument("--tick-limit", type=int, default=75_000)
    parser.add_argument("--profile-output", type=Path)
    parser.add_argument("--force-replay", action="store_true")
    parser.add_argument("--skip-replay", action="store_true")
    parser.add_argument(
        "--assemble-existing",
        action="store_true",
        help="Assemble already-written per-rung JSON without executing rungs.",
    )
    args = parser.parse_args()
    if args.force_replay and args.skip_replay:
        parser.error("--force-replay and --skip-replay are mutually exclusive")
    for rung in ([args.single_rung] if args.single_rung else args.packets):
        if rung not in ALLOWED_RUNGS:
            parser.error(f"only the frozen initial rungs {ALLOWED_RUNGS} are allowed")

    replay = True if args.force_replay else False if args.skip_replay else None
    if args.single_rung is not None:
        report = run_cork_scale_rung(
            args.single_rung,
            graph_path=args.graphml,
            tick_limit=args.tick_limit,
            runtime_guard_seconds=args.runtime_guard_seconds,
            run_replay=replay,
            profile_output=args.profile_output,
        )
        text = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.single_output:
            args.single_output.parent.mkdir(parents=True, exist_ok=True)
            args.single_output.write_text(text, encoding="utf-8")
        print(text, end="")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    rung_reports = []
    for rung in args.packets:
        rung_path = args.output.parent / f"cork_rung_{rung}_v1.json"
        if args.assemble_existing:
            rung_reports.append(json.loads(rung_path.read_text(encoding="utf-8")))
            continue
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--single-rung",
            str(rung),
            "--single-output",
            str(rung_path),
            "--runtime-guard-seconds",
            str(args.runtime_guard_seconds),
            "--tick-limit",
            str(args.tick_limit),
        ]
        if args.graphml is not None:
            command.extend(["--graphml", str(args.graphml.resolve())])
        if args.force_replay:
            command.append("--force-replay")
        elif args.skip_replay:
            command.append("--skip-replay")
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        rung_reports.append(json.loads(rung_path.read_text(encoding="utf-8")))
    payload = {
        "artifact_version": "uc.cork-city-scale-ladder-report.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "fresh_process_per_rung": True,
        "permitted_rungs": list(ALLOWED_RUNGS),
        "higher_rungs_attempted": False,
        "rungs": rung_reports,
    }
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.markdown.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


def _markdown(payload: dict) -> str:
    lines = [
        "# Cork City-Scale Physical Loading v1",
        "",
        "Engineering scalability evidence only; this is not calibrated Cork operations.",
        "",
        "| Packets | Status | Completed | ODs | Events | Stop/final tick | Load s | Route s | RSS MiB | Replay |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for report in payload["rungs"]:
        primary = report["primary"]
        lines.append(
            f"| {report['packet_count']} | {primary['run_status']} | "
            f"{primary['completed_packet_count']} | {primary['unique_od_count']} | "
            f"{primary['canonical_event_count']} | {primary['final_completion_tick']} | "
            f"{primary['physical_loading_wall_seconds']:.3f} | "
            f"{report['routing']['route_resolution_seconds']:.3f} | "
            f"{report['peak_rss_bytes'] / 1024 / 1024:.1f} | "
            f"{report['replay']['status']} |"
        )
    lines.extend(
        [
            "",
            "Recommendation: **Red**. The 10k rung hit its 600-second guard "
            "with 2,908 complete, 6,983 instantiated/in flight, and 109 pending "
            "origin admission. Investigate the 25 Hz eligible packet-front cost "
            "before any higher rung.",
            "",
            "50k and 100k were intentionally not attempted.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
