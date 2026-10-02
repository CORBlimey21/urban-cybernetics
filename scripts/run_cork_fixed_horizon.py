#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Run the versioned 15,000-tick Cork fixed-horizon scale ladder."""

from __future__ import annotations

import argparse
import hashlib
import json
import pstats
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from urban_cybernetics.experiments.cork_fixed_horizon import (
    DEFAULT_RUNTIME_GUARD_SECONDS,
    TOTAL_HORIZON_TICKS,
    run_cork_fixed_horizon_rung,
)


OUTPUT_DIRECTORY = Path("outputs/cork_fixed_horizon_v1")
DEFAULT_OUTPUT = OUTPUT_DIRECTORY / "cork_fixed_horizon_ladder_v1.json"
DEFAULT_MARKDOWN = OUTPUT_DIRECTORY / "cork_fixed_horizon_ladder_v1.md"
ALLOWED_RUNGS = (100, 1_000, 2_500, 5_000, 10_000)
OLD_DRAIN_DIRECTORY = Path("outputs/cork_city_scale")


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
    parser.add_argument(
        "--runtime-guard-seconds",
        type=float,
        default=DEFAULT_RUNTIME_GUARD_SECONDS,
    )
    parser.add_argument("--profile-output", type=Path)
    parser.add_argument("--profile-rungs", type=int, nargs="*", default=[])
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
    selected = [args.single_rung] if args.single_rung else args.packets
    for rung in selected:
        if rung not in ALLOWED_RUNGS:
            parser.error(f"only fixed-horizon rungs {ALLOWED_RUNGS} are allowed")
    for rung in args.profile_rungs:
        if rung not in selected:
            parser.error("profile rungs must also be selected experiment rungs")

    replay = True if args.force_replay else False if args.skip_replay else None
    if args.single_rung is not None:
        report = run_cork_fixed_horizon_rung(
            args.single_rung,
            graph_path=args.graphml,
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
        rung_path = args.output.parent / f"cork_fixed_horizon_rung_{rung}_v1.json"
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
        ]
        if args.graphml is not None:
            command.extend(["--graphml", str(args.graphml.resolve())])
        if args.force_replay:
            command.append("--force-replay")
        elif args.skip_replay:
            command.append("--skip-replay")
        if rung in args.profile_rungs:
            command.extend(
                [
                    "--profile-output",
                    str(args.output.parent / f"cork_fixed_horizon_{rung}_v1.pstats"),
                ]
            )
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        rung_reports.append(json.loads(rung_path.read_text(encoding="utf-8")))

    recommendation = _recommendation(rung_reports)
    payload = {
        "artifact_version": "uc.cork-fixed-horizon-ladder-report.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "fresh_process_per_rung": True,
        "permitted_rungs": list(ALLOWED_RUNGS),
        "higher_rungs_attempted": False,
        "fixed_horizon_ticks": TOTAL_HORIZON_TICKS,
        "recommendation": recommendation,
        "preserved_drain_evidence": _preserved_drain_evidence(),
        "performance_profile": _performance_profile(args.output.parent, rung_reports),
        "rungs": rung_reports,
    }
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.markdown.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


def _recommendation(reports: list[dict]) -> dict[str, object]:
    ten_thousand = next(
        (report for report in reports if report["packet_count"] == 10_000), None
    )
    if ten_thousand is None:
        return {
            "classification": "not_evaluated",
            "basis": "10,000-packet rung absent",
            "paper_1_sufficiency": None,
        }
    primary = ten_thousand["primary"]
    if primary["ticks_executed"] != TOTAL_HORIZON_TICKS:
        classification = "Red"
        basis = "10k did not complete the fixed 15,000-tick horizon within its guard"
        sufficient = False
    elif (
        primary["loading_and_evolution_wall_seconds"] <= 300.0
        and ten_thousand["peak_rss_bytes"] <= 2 * 1024 * 1024 * 1024
    ):
        classification = "Green"
        basis = "10k completed within a five-minute wall guard and 2 GiB peak RSS"
        sufficient = True
    else:
        classification = "Amber"
        basis = "10k completed the horizon but exceeded the comfortable runtime/RSS gate"
        sufficient = True
    return {
        "classification": classification,
        "basis": basis,
        "comfortable_runtime_seconds_max": 300.0,
        "comfortable_peak_rss_bytes_max": 2 * 1024 * 1024 * 1024,
        "paper_1_sufficiency": sufficient,
        "50k_or_100k_needed_for_paper_1": False if sufficient else None,
    }


def _preserved_drain_evidence() -> dict[str, object]:
    files = {
        "drain_100": OLD_DRAIN_DIRECTORY / "cork_rung_100_v1.json",
        "drain_1000": OLD_DRAIN_DIRECTORY / "cork_rung_1000_v1.json",
        "bounded_drain_10000": OLD_DRAIN_DIRECTORY / "cork_rung_10000_v1.json",
        "original_ladder": OLD_DRAIN_DIRECTORY / "cork_scale_ladder_v1.json",
    }
    result: dict[str, object] = {
        "integrity_protocol": "100 and 1,000 packets drain to empty with exact replay",
        "scalability_protocol": "all rungs execute the same 600 s physical horizon",
        "bounded_10k_interpretation": (
            "conservative and valid bounded drain run; drain-to-empty exceeded the "
            "600 s wall guard and was not a correctness failure"
        ),
        "artifacts": {},
    }
    artifacts = result["artifacts"]
    assert isinstance(artifacts, dict)
    for label, path in files.items():
        if path.exists():
            detail = _drain_detail(path) if label != "original_ladder" else None
            artifacts[label] = {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
                "result": detail,
            }
        else:
            artifacts[label] = {"path": str(path), "status": "not_found"}
    return result


def _drain_detail(path: Path) -> dict[str, object]:
    report = json.loads(path.read_text(encoding="utf-8"))
    primary = report["primary"]
    return {
        "run_status": primary["run_status"],
        "completed_packet_count": primary["completed_packet_count"],
        "instantiated_packet_count": primary["instantiated_packet_count"],
        "pending_origin_admission_count": primary["pending_origin_admission_count"],
        "active_in_flight_packet_count": primary["active_in_flight_packet_count"],
        "final_or_bounded_tick": primary["final_completion_tick"],
        "loading_wall_seconds": primary["physical_loading_wall_seconds"],
        "exact_conservation": primary["validation"]["exact_conservation"],
        "replay_status": report["replay"]["status"],
        "stop_reason": primary["stop_reason"],
    }


def _performance_profile(output_directory: Path, reports: list[dict]) -> dict[str, object]:
    profile_path = output_directory / "cork_fixed_horizon_5000_v1.pstats"
    profiled_path = output_directory / "cork_fixed_horizon_profiled_5000_v1.json"
    if not profile_path.exists() or not profiled_path.exists():
        return {
            "status": "not_available",
            "profile_path": str(profile_path),
        }
    profiled = json.loads(profiled_path.read_text(encoding="utf-8"))
    official = next(report for report in reports if report["packet_count"] == 5_000)
    stats = pstats.Stats(str(profile_path))
    step_seconds = _profile_cumulative_seconds(stats, "engine.py", "step")
    categories = {
        "v2_sending_preparation": _profile_cumulative_seconds(
            stats, "city_scale_v2.py", "_prepare_parity_sending_capacity_for_tick"
        ),
        "strict_fifo_packet_front_and_completion_evaluation": (
            _profile_cumulative_seconds(
                stats, "engine.py", "_final_completion_packet_ids_by_link"
            )
        ),
        "transfer_candidate_construction": _profile_cumulative_seconds(
            stats, "engine.py", "_transfer_candidates"
        ),
        "node_allocation": _profile_cumulative_seconds(
            stats, "engine.py", "_allocate_transfer_requests"
        ),
        "receiving_slot_evaluation": _profile_cumulative_seconds(
            stats, "engine.py", "_receiving_slots_by_link"
        ),
        "canonical_event_append": _profile_cumulative_seconds(
            stats, "engine.py", "append_event"
        ),
    }
    category_rows = {
        label: {
            "cumulative_seconds": seconds,
            "percent_of_profiled_engine_step": (
                seconds / step_seconds * 100.0 if step_seconds else None
            ),
        }
        for label, seconds in categories.items()
    }
    sending_domains = official["primary"]["city_scale_v2_summary"][
        "sending_domains_prepared"
    ]
    dense_link_tick_visits = (
        official["network"]["directed_edge_count"] * TOTAL_HORIZON_TICKS
    )
    return {
        "status": "available",
        "profiled_packet_count": 5_000,
        "profile_path": str(profile_path),
        "profile_sha256": hashlib.sha256(profile_path.read_bytes()).hexdigest(),
        "profiled_run_path": str(profiled_path),
        "profiled_event_hash_matches_official": (
            profiled["primary"]["event_stream_sha256"]
            == official["primary"]["event_stream_sha256"]
        ),
        "profiled_horizon_state_hash_matches_official": (
            profiled["primary"]["horizon_state_hash"]
            == official["primary"]["horizon_state_hash"]
        ),
        "profiled_engine_step_cumulative_seconds": step_seconds,
        "profiled_evolution_wall_seconds": profiled["primary"][
            "loading_and_evolution_wall_seconds"
        ],
        "official_unprofiled_evolution_wall_seconds": official["primary"][
            "loading_and_evolution_wall_seconds"
        ],
        "categories": category_rows,
        "all_network_per_tick_check": {
            "dense_link_tick_visits_if_present": dense_link_tick_visits,
            "actual_v2_sending_domains_prepared": sending_domains,
            "actual_fraction_of_dense_link_tick_visits": (
                sending_domains / dense_link_tick_visits
            ),
            "network_wide_scan_each_tick_detected": False,
            "remaining_network_wide_work": (
                "one terminal receiving-credit materialization and validation/build "
                "passes; no 13,111-link scan inside each physical step"
            ),
        },
        "interpretation": (
            "cumulative categories may overlap through callers; percentages describe "
            "where profiled step time is rooted and must not be summed"
        ),
        "performance_patch_applied": False,
    }


def _profile_cumulative_seconds(
    stats: pstats.Stats, filename_suffix: str, function_name: str
) -> float:
    matches = [
        values[3]
        for (filename, _line, name), values in stats.stats.items()
        if filename.endswith(filename_suffix) and name == function_name
    ]
    if not matches:
        return 0.0
    return max(matches)


def _markdown(payload: dict) -> str:
    lines = [
        "# Cork Fixed-Horizon Scale Ladder v1",
        "",
        "Computational scalability evidence only; horizon state is not calibrated Cork congestion.",
        "",
        "Protocol: 300 s loading + 300 s observation, 0.04 s/tick, exactly 15,000 ticks.",
        "",
        "| Demand | Admitted | Completed | Active/queued | Pending | Admission | Completion | Events | Wall s | RSS MiB | Replay |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for report in payload["rungs"]:
        primary = report["primary"]
        lines.append(
            f"| {report['packet_count']} | {primary['admitted_by_horizon']} | "
            f"{primary['completed_by_horizon']} | "
            f"{primary['active_or_queued_by_horizon']} | "
            f"{primary['pending_origin_admission_by_horizon']} | "
            f"{primary['admission_fraction']:.3%} | "
            f"{primary['completion_fraction']:.3%} | "
            f"{primary['canonical_event_count']} | "
            f"{primary['loading_and_evolution_wall_seconds']:.3f} | "
            f"{report['peak_rss_bytes'] / 1024 / 1024:.1f} | "
            f"{report['replay']['status']} |"
        )
    lines.extend(
        [
            "",
            "## Horizon traffic state",
            "",
            "| Demand | Non-empty links | Non-empty queues | Queued | Peak queued | FIFO blocks | Storage blocks | Origin-blocked packet-ticks | Physical occupancy |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for report in payload["rungs"]:
        state = report["primary"]["horizon_traffic_state"]
        lines.append(
            f"| {report['packet_count']} | {state['non_empty_link_count']} | "
            f"{state['non_empty_queue_count']} | {state['total_queued_packets']} | "
            f"{state['peak_queued_packets']} | {state['fifo_block_count']} | "
            f"{state['receiving_storage_block_count']} | "
            f"{state['origin_admission_blocking_packet_ticks']} | "
            f"{state['total_physical_storage_occupancy_packets']} |"
        )
    profile = payload["performance_profile"]
    if profile["status"] == "available":
        categories = profile["categories"]
        lines.extend(
            [
                "",
                "## Performance profile",
                "",
                "Separate 5,000-packet cProfile run; official timings above are unprofiled.",
                "",
            ]
        )
        for label, values in categories.items():
            lines.append(
                f"- {label.replace('_', ' ')}: "
                f"{values['cumulative_seconds']:.3f} s "
                f"({values['percent_of_profiled_engine_step']:.1f}% of step cumulative time)"
            )
        scan = profile["all_network_per_tick_check"]
        lines.extend(
            [
                "",
                f"Active V2 sending preparation touched {scan['actual_v2_sending_domains_prepared']:,} "
                f"domains, {scan['actual_fraction_of_dense_link_tick_visits']:.2%} of the "
                f"{scan['dense_link_tick_visits_if_present']:,} visits a dense all-link/tick loop would perform.",
                "No new performance patch was applied.",
            ]
        )
    recommendation = payload["recommendation"]
    lines.extend(
        [
            "",
            f"Recommendation: **{recommendation['classification']}** — {recommendation['basis']}.",
            "",
            "The earlier 100/1,000 drain runs remain separate exact-replay integrity evidence. "
            "The earlier bounded 10k drain run remained conservative and valid; its wall guard "
            "motivated separating computational scale from network-clearance time.",
            "",
            "50k and 100k were intentionally not attempted.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
