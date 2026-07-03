#!/usr/bin/env python3
"""Profile Sioux Falls assumption-profile scale-ladder phases."""

from __future__ import annotations

import argparse
import json
import resource
import signal
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterator

from urban_cybernetics.canonical_validation.sioux_falls_physical_profile import (
    build_sioux_falls_uc_default_physical_profile,
)
from urban_cybernetics.canonical_validation.sioux_falls_readiness import (
    _fifo_validation_failures,
    _junction_metadata_gate,
    _node_validation_failures,
    _run_completed,
)
from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.demand import (
    FixedDepartureSchedule,
    ScheduledDemandLoader,
    load_sioux_falls_demand_manifest,
    resolve_demand_routes,
)
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.topology import load_sioux_falls_topology
from urban_cybernetics.validation import (
    ValidationContext,
    assess_physical_parameter_eligibility,
    build_commodity_parity_validation_report,
    build_spillback_validation_report,
)


DEFAULT_OUTPUT_JSON = Path(
    "docs/validation/sioux_falls_uc_default_scale_ladder_profile_v1.json"
)
DEFAULT_OUTPUT_MARKDOWN = Path(
    "docs/validation/sioux_falls_uc_default_scale_ladder_profile_v1.md"
)


class ProfileTimeout(RuntimeError):
    """Raised when the active profiling phase exceeds the runtime guard."""

    def __init__(self, active_phase: str, timeout_seconds: float) -> None:
        super().__init__(f"runtime_limit_exceeded:{timeout_seconds}s:{active_phase}")
        self.active_phase = active_phase
        self.timeout_seconds = timeout_seconds


@dataclass(frozen=True, slots=True)
class PhaseTiming:
    """One measured phase in a rung profile."""

    phase: str
    seconds: float
    status: str
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RungProfile:
    """Measured phase timings and final state for one packet cap."""

    requested_packet_count: int
    status: str
    failure_reason: str | None
    submitted_packet_count: int
    instantiated_packet_count: int
    completed_packet_count: int
    unresolved_packet_count: int
    ticks_run: int
    event_count: int
    setup_preloading_seconds: float
    primary_engine_stepping_seconds: float
    validation_seconds: float
    replay_seconds: float | None
    total_wall_clock_seconds: float
    primary_events_per_second: float | None
    primary_packets_per_second: float | None
    total_events_per_second: float | None
    total_packets_per_second: float | None
    max_rss_bytes: int
    replay_status: str
    phase_timings: tuple[PhaseTiming, ...]
    validations: dict[str, bool | None]


class RungProfiler:
    """Run one Sioux Falls packet cap with phase-level timing."""

    def __init__(
        self,
        *,
        packet_count: int,
        tick_limit: int,
        exact_replay_packet_limit: int,
    ) -> None:
        self.packet_count = packet_count
        self.tick_limit = tick_limit
        self.exact_replay_packet_limit = exact_replay_packet_limit
        self.phase_timings: list[PhaseTiming] = []
        self.active_phase = "not_started"
        self.engine: LoadingEngine | None = None
        self.loader: ScheduledDemandLoader | None = None
        self.scheduled_departure_count = 0
        self.validations: dict[str, bool | None] = {
            "packet_conservation": None,
            "count_consistency": None,
            "fifo": None,
            "spillback": None,
            "commodity": None,
            "node": None,
            "deterministic_replay": None,
        }
        self.replay_status = "not_run"

    def profile(self) -> RungProfile:
        failure_reason: str | None = None
        started_at = perf_counter()
        try:
            self._run()
        except ProfileTimeout as exc:
            failure_reason = str(exc)
        total_wall_clock_seconds = perf_counter() - started_at
        status = "passed" if failure_reason is None and all(
            value is True
            for key, value in self.validations.items()
            if key != "deterministic_replay"
        ) else "failed"
        if (
            status == "passed"
            and self.packet_count <= self.exact_replay_packet_limit
            and self.validations["deterministic_replay"] is not True
        ):
            status = "failed"
        engine = self.engine
        submitted = (
            len(self.loader.submitted_loading_demand_ids)
            if self.loader is not None
            else 0
        )
        instantiated = len(engine.packets) if engine is not None else 0
        completed = len(engine.completed_packet_ids) if engine is not None else 0
        event_count = len(engine.event_log) if engine is not None else 0
        setup_preloading_seconds = sum(
            phase.seconds
            for phase in self.phase_timings
            if phase.phase
            in {
                "tntp_topology_loading",
                "physical_profile_build",
                "physical_profile_application",
                "od_pair_selection_and_demand_manifest_creation",
                "route_resolution",
                "scheduled_loading_expansion",
                "parity_readiness_checks",
                "engine_initialisation",
                "initial_departure_submission",
            }
        )
        primary_engine_stepping_seconds = self._phase_seconds(
            "engine_stepping_primary"
        )
        validation_seconds = sum(
            phase.seconds
            for phase in self.phase_timings
            if phase.phase
            in {
                "validation_context_snapshot",
                "validation_setup_packet_conservation",
                "shared_projection_build",
                "validation_setup_count_consistency",
                "validation_setup_fifo",
                "validation_setup_spillback",
                "validation_setup_commodity",
                "validation_setup_node",
            }
        )
        replay_seconds = (
            self._phase_seconds("deterministic_replay_engine_stepping")
            + self._phase_seconds("validation_setup_replay_compare")
            if self.replay_status in {"passed_exact_replay", "failed_mismatch"}
            else None
        )
        return RungProfile(
            requested_packet_count=self.packet_count,
            status=status,
            failure_reason=failure_reason,
            submitted_packet_count=submitted,
            instantiated_packet_count=instantiated,
            completed_packet_count=completed,
            unresolved_packet_count=max(self.scheduled_departure_count - completed, 0),
            ticks_run=engine.current_tick if engine is not None else 0,
            event_count=event_count,
            setup_preloading_seconds=setup_preloading_seconds,
            primary_engine_stepping_seconds=primary_engine_stepping_seconds,
            validation_seconds=validation_seconds,
            replay_seconds=replay_seconds,
            total_wall_clock_seconds=total_wall_clock_seconds,
            primary_events_per_second=_rate(event_count, primary_engine_stepping_seconds),
            primary_packets_per_second=_rate(completed, primary_engine_stepping_seconds),
            total_events_per_second=_rate(event_count, total_wall_clock_seconds),
            total_packets_per_second=_rate(completed, total_wall_clock_seconds),
            max_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            replay_status=self.replay_status,
            phase_timings=tuple(self.phase_timings),
            validations=self.validations,
        )

    def _run(self) -> None:
        topology = self._phase("tntp_topology_loading", load_sioux_falls_topology)
        profile = self._phase(
            "physical_profile_build",
            lambda: build_sioux_falls_uc_default_physical_profile(topology=topology),
        )
        links, nodes, capacity_rates = self._phase(
            "physical_profile_application",
            lambda: (
                profile.as_loading_links(),
                topology.as_loading_nodes(),
                profile.parity_capacity_rates_by_link(),
            ),
            details=lambda result: {
                "links": len(result[0]),
                "nodes": len(result[1]),
            },
        )
        manifest = self._phase(
            "od_pair_selection_and_demand_manifest_creation",
            lambda: load_sioux_falls_demand_manifest(
                topology=topology,
                scale_factor=1.0,
                max_pairs=None,
                max_total_quantity_packets=self.packet_count,
                departure_schedule=FixedDepartureSchedule(departure_tick=0),
            ),
            details=lambda result: {
                "od_pairs": len(result.declarations),
                "declared_packets": result.total_declared_quantity_packets,
            },
        )
        resolved = self._phase(
            "route_resolution",
            lambda: resolve_demand_routes(manifest, topology),
            details=lambda result: {
                "resolved_routes": len(result.resolved_routes),
            },
        )
        self.loader = self._phase(
            "scheduled_loading_expansion",
            lambda: ScheduledDemandLoader(resolved),
            details=lambda result: {
                "scheduled_requests": len(result.scheduled_requests),
            },
        )
        self.scheduled_departure_count = len(self.loader.scheduled_requests)
        self._phase(
            "parity_readiness_checks",
            lambda: (
                assess_physical_parameter_eligibility(
                    links.values(),
                    model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
                ),
                _junction_metadata_gate(nodes),
            ),
            details=lambda result: {
                "physical_passed": result[0].is_parity_eligible,
                "junction_passed": result[1].is_pass,
            },
        )
        self.engine = self._phase(
            "engine_initialisation",
            lambda: LoadingEngine(
                links=links,
                nodes=nodes,
                model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
                parity_sending_capacity_vehicles_per_tick_by_link=capacity_rates,
                parity_receiving_capacity_vehicles_per_tick_by_link=capacity_rates,
            ),
            details=lambda result: {
                "links": len(result.links),
                "nodes": len(result.nodes),
            },
        )
        self._phase(
            "initial_departure_submission",
            lambda: self.loader.submit_due_departures(self.engine),
            details=lambda _result: self._engine_details(),
        )
        self._phase("engine_stepping_primary", self._step_primary_engine)
        self._phase("validation_setup_packet_conservation", self._packet_conservation)
        validation_context = self._phase(
            "validation_context_snapshot",
            lambda: ValidationContext.from_engine(
                self.engine,
                nodes=nodes,
                run_config={
                    "packet_count": self.packet_count,
                    "tick_limit": self.tick_limit,
                },
            ),
            details=lambda result: {
                "events": len(result.event_log),
                "packets": len(result.packets),
                "links": len(result.link_ids),
                "nodes": len(result.nodes),
            },
        )
        self._phase(
            "shared_projection_build",
            lambda: validation_context.cumulative_count_projection,
            details=lambda result: {
                "aggregate_counts": len(result.aggregate_counts),
                "route_counts": len(result.route_counts),
                "packet_ordinals": len(result.packet_ordinals),
                "route_travel_time_curves": len(result.route_travel_time_curves),
            },
        )
        self._phase(
            "validation_setup_count_consistency",
            lambda: self._count_consistency(validation_context),
        )
        self._phase(
            "validation_setup_fifo",
            lambda: self._fifo_validation(validation_context),
        )
        self._phase("validation_setup_spillback", self._spillback_validation)
        self._phase(
            "validation_setup_commodity",
            lambda: self._commodity_validation(validation_context),
        )
        self._phase(
            "validation_setup_node",
            lambda: self._node_validation(nodes, validation_context),
        )
        if self.packet_count <= self.exact_replay_packet_limit:
            replay_engine = self._phase(
                "deterministic_replay_engine_stepping",
                lambda: self._run_replay_engine(links, nodes, resolved, capacity_rates),
                details=lambda result: {
                    "ticks": result.current_tick,
                    "events": len(result.event_log),
                    "completed_packets": len(result.completed_packet_ids),
                },
            )
            self._phase(
                "validation_setup_replay_compare",
                lambda: self._replay_compare(replay_engine),
            )
        else:
            self.replay_status = (
                "skipped_by_policy_after_determinism_certification"
            )
            self.validations["deterministic_replay"] = None
        self._phase(
            "artifact_serialisation",
            lambda: json.dumps(
                {
                    "phase_timings": [
                        asdict(phase_timing)
                        for phase_timing in self.phase_timings
                    ],
                    "validations": self.validations,
                },
                sort_keys=True,
            ),
        )

    def _step_primary_engine(self) -> None:
        assert self.engine is not None
        assert self.loader is not None
        for _ in range(self.tick_limit):
            if _run_completed(
                self.engine,
                scheduled_departure_count=self.scheduled_departure_count,
                submitted_departure_count=len(self.loader.submitted_loading_demand_ids),
            ):
                break
            self.engine.step()
            self.loader.submit_due_departures(self.engine)

    def _run_replay_engine(
        self,
        links: dict[str, Any],
        nodes: tuple[Any, ...],
        resolved: Any,
        capacity_rates: dict[str, float],
    ) -> LoadingEngine:
        replay_engine = LoadingEngine(
            links=links,
            nodes=nodes,
            model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
            parity_sending_capacity_vehicles_per_tick_by_link=capacity_rates,
            parity_receiving_capacity_vehicles_per_tick_by_link=capacity_rates,
        )
        replay_loader = ScheduledDemandLoader(resolved)
        replay_loader.submit_due_departures(replay_engine)
        for _ in range(self.tick_limit):
            if _run_completed(
                replay_engine,
                scheduled_departure_count=len(replay_loader.scheduled_requests),
                submitted_departure_count=len(
                    replay_loader.submitted_loading_demand_ids
                ),
            ):
                break
            replay_engine.step()
            replay_loader.submit_due_departures(replay_engine)
        return replay_engine

    def _count_consistency(self, context: ValidationContext) -> None:
        self.validations["count_consistency"] = (
            context.count_consistency_report.is_consistent
        )

    def _fifo_validation(self, context: ValidationContext) -> None:
        assert self.engine is not None
        self.validations["fifo"] = not _fifo_validation_failures(
            self.engine,
            validation_context=context,
        )

    def _spillback_validation(self) -> None:
        assert self.engine is not None
        report = build_spillback_validation_report(self.engine)
        self.validations["spillback"] = report.is_valid

    def _commodity_validation(self, context: ValidationContext) -> None:
        assert self.engine is not None
        report = build_commodity_parity_validation_report(
            self.engine,
            validation_context=context,
        )
        self.validations["commodity"] = report.is_valid

    def _node_validation(
        self,
        nodes: tuple[Any, ...],
        context: ValidationContext,
    ) -> None:
        assert self.engine is not None
        self.validations["node"] = not _node_validation_failures(
            self.engine,
            nodes,
            validation_context=context,
        )

    def _replay_compare(self, replay_engine: LoadingEngine) -> None:
        assert self.engine is not None
        self.validations["deterministic_replay"] = (
            self.engine.event_log == replay_engine.event_log
        )
        self.replay_status = (
            "passed_exact_replay"
            if self.validations["deterministic_replay"]
            else "failed_mismatch"
        )

    def _packet_conservation(self) -> None:
        assert self.engine is not None
        self.validations["packet_conservation"] = (
            len(self.engine.packets) == self.scheduled_departure_count
            and len(self.engine.completed_packet_ids) == self.scheduled_departure_count
            and not self.engine.pending_demands
        )

    def _phase(
        self,
        phase: str,
        operation: Callable[[], Any],
        *,
        details: Callable[[Any], dict[str, Any]] | None = None,
    ) -> Any:
        self.active_phase = phase
        started_at = perf_counter()
        result: Any = None
        status = "completed"
        phase_details: dict[str, Any] = {}
        try:
            result = operation()
            if details is not None:
                phase_details = details(result)
            return result
        except ProfileTimeout:
            status = "timeout"
            phase_details = self._engine_details()
            raise
        finally:
            self.phase_timings.append(
                PhaseTiming(
                    phase=phase,
                    seconds=perf_counter() - started_at,
                    status=status,
                    details=phase_details,
                )
            )

    def _engine_details(self) -> dict[str, Any]:
        engine = self.engine
        loader = self.loader
        if engine is None:
            return {}
        return {
            "submitted": (
                len(loader.submitted_loading_demand_ids)
                if loader is not None
                else None
            ),
            "instantiated": len(engine.packets),
            "completed": len(engine.completed_packet_ids),
            "pending": len(engine.pending_demands),
            "tick": engine.current_tick,
            "events": len(engine.event_log),
        }

    def _phase_seconds(self, phase_name: str) -> float:
        return sum(
            phase.seconds
            for phase in self.phase_timings
            if phase.phase == phase_name
        )

    @contextmanager
    def profile_timeout(self, timeout_seconds: float | None) -> Iterator[None]:
        if timeout_seconds is None:
            yield
            return

        def _handle_timeout(_signum: int, _frame: object) -> None:
            raise ProfileTimeout(self.active_phase, timeout_seconds)

        previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, _handle_timeout)
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        try:
            yield
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            signal.signal(signal.SIGALRM, previous_handler)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Profile Sioux Falls UC-default scale-ladder phase timings."
    )
    parser.add_argument("--packets", type=int, nargs="+", default=[1_000, 5_000])
    parser.add_argument("--tick-limit", type=int, default=20_000)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--exact-replay-packet-limit", type=int, default=10_000)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_OUTPUT_MARKDOWN)
    args = parser.parse_args()

    profiles: list[RungProfile] = []
    for packet_count in args.packets:
        profiler = RungProfiler(
            packet_count=packet_count,
            tick_limit=args.tick_limit,
            exact_replay_packet_limit=args.exact_replay_packet_limit,
        )
        with profiler.profile_timeout(args.timeout_seconds):
            profiles.append(profiler.profile())

    payload = {
        "artifact_generated_at_utc": datetime.now(UTC).isoformat(),
        "runner": {
            "script": "scripts/profile_sioux_falls_scale_ladder.py",
            "packet_counts": args.packets,
            "tick_limit": args.tick_limit,
            "timeout_seconds_per_rung": args.timeout_seconds,
            "exact_replay_packet_limit": args.exact_replay_packet_limit,
        },
        "profiles": [asdict(profile) for profile in profiles],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    started_at = perf_counter()
    args.output_json.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    artifact_seconds = perf_counter() - started_at
    payload["artifact_writing_seconds"] = artifact_seconds
    args.output_json.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.output_markdown.write_text(_render_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Post-Option-C Sioux Falls Scale Ladder Profile",
        "",
        "This artifact profiles wall-clock phase timings for Sioux Falls "
        "UC-default assumption-profile rungs after the Option C unified "
        "queue/active FIFO allocator fix. It does not change model semantics "
        "and does not relax validation.",
        "",
        "| Requested | Submitted | Instantiated | Completed | Unresolved | Ticks | "
        "Events | Setup/preload s | Primary s | Validation s | Replay s | Total s | "
        "Primary events/s | Primary packets/s | Total events/s | Total packets/s | "
        "Max RSS bytes | Validation | Replay | Failure |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        "---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for profile in payload["profiles"]:
        validations = {
            key: value
            for key, value in profile["validations"].items()
            if key != "deterministic_replay"
        }
        validation_status = (
            "passed" if all(value is True for value in validations.values()) else "failed"
        )
        row = {
            **profile,
            "replay_seconds": _format_optional_float(profile["replay_seconds"]),
            "primary_events_per_second": _format_optional_float(
                profile["primary_events_per_second"]
            ),
            "primary_packets_per_second": _format_optional_float(
                profile["primary_packets_per_second"]
            ),
            "total_events_per_second": _format_optional_float(
                profile["total_events_per_second"]
            ),
            "total_packets_per_second": _format_optional_float(
                profile["total_packets_per_second"]
            ),
            "validation_status": validation_status,
            "rendered_failure_reason": profile["failure_reason"] or "none",
        }
        lines.append(
            "| {requested_packet_count} | {submitted_packet_count} | "
            "{instantiated_packet_count} | {completed_packet_count} | "
            "{unresolved_packet_count} | {ticks_run} | {event_count} | "
            "{setup_preloading_seconds:.3f} | "
            "{primary_engine_stepping_seconds:.3f} | "
            "{validation_seconds:.3f} | {replay_seconds} | "
            "{total_wall_clock_seconds:.3f} | {primary_events_per_second} | "
            "{primary_packets_per_second} | {total_events_per_second} | "
            "{total_packets_per_second} | {max_rss_bytes} | "
            "{validation_status} | `{replay_status}` | {rendered_failure_reason} |".format(
                **row,
            )
        )
        lines.extend(
            [
                f"## {profile['requested_packet_count']} Packets",
                "",
                f"- Status: `{profile['status']}`",
                f"- Failure reason: `{profile['failure_reason'] or 'none'}`",
                f"- Submitted / instantiated / completed / unresolved: "
                f"`{profile['submitted_packet_count']} / "
                f"{profile['instantiated_packet_count']} / "
                f"{profile['completed_packet_count']} / "
                f"{profile['unresolved_packet_count']}`",
                f"- Ticks / events: `{profile['ticks_run']} / "
                f"{profile['event_count']}`",
                f"- Wall-clock setup / primary / validation / replay / total seconds: "
                f"`{profile['setup_preloading_seconds']:.3f} / "
                f"{profile['primary_engine_stepping_seconds']:.3f} / "
                f"{profile['validation_seconds']:.3f} / "
                f"{_format_optional_float(profile['replay_seconds'])} / "
                f"{profile['total_wall_clock_seconds']:.3f}`",
                f"- Throughput, primary events/s / primary packets/s / total events/s / "
                f"total packets/s: "
                f"`{_format_optional_float(profile['primary_events_per_second'])} / "
                f"{_format_optional_float(profile['primary_packets_per_second'])} / "
                f"{_format_optional_float(profile['total_events_per_second'])} / "
                f"{_format_optional_float(profile['total_packets_per_second'])}`",
                f"- Max RSS bytes: `{profile['max_rss_bytes']}`",
                f"- Replay status: `{profile['replay_status']}`",
                "",
                "| Phase | Seconds | Status | Details |",
                "| --- | ---: | --- | --- |",
            ]
        )
        for phase in profile["phase_timings"]:
            lines.append(
                "| {phase} | {seconds:.6f} | {status} | `{details}` |".format(
                    phase=phase["phase"],
                    seconds=phase["seconds"],
                    status=phase["status"],
                    details=json.dumps(phase["details"], sort_keys=True),
                )
            )
        lines.append("")
    lines.append(
        f"Artifact writing seconds: `{payload.get('artifact_writing_seconds', 0.0):.6f}`"
    )
    lines.append("")
    return "\n".join(lines)


def _rate(numerator: int, seconds: float) -> float | None:
    if seconds <= 0.0:
        return None
    return numerator / seconds


def _format_optional_float(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


if __name__ == "__main__":
    main()
