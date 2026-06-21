"""Executable smoke runner for full Sioux Falls demand through loading."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import time
import tracemalloc
from dataclasses import asdict, dataclass
from typing import Any

from urban_cybernetics.demand import (
    FixedDepartureSchedule,
    ScheduledDemandLoader,
    load_sioux_falls_demand_manifest,
    resolve_demand_routes,
)
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.topology import load_sioux_falls_topology


@dataclass(frozen=True, slots=True)
class SiouxFallsDemandSmokeResult:
    """Summary metrics for one Sioux Falls demand loading smoke run."""

    scale_factor: float
    status: str
    ticks_run: int
    tick_limit: int
    runtime_seconds: float
    peak_memory_mb: float | None
    topology_hash: str | None
    demand_hash: str | None
    od_pairs: int
    total_declared_demand: int
    resolved_routes: int
    scheduled_departures: int
    instantiated_packets: int
    completed_packets: int
    pending_demand: int
    event_count: int
    failure: str | None = None


def run_sioux_falls_demand_smoke(
    *,
    scale_factor: float,
    tick_limit: int,
    storage_capacity_packets: int,
) -> SiouxFallsDemandSmokeResult:
    """Run one scale of Sioux Falls demand through today's loading engine."""

    started_at = time.perf_counter()
    tracemalloc.start()
    topology_hash: str | None = None
    demand_hash: str | None = None
    od_pairs = 0
    total_declared_demand = 0
    resolved_routes = 0
    scheduled_departures = 0
    instantiated_packets = 0
    completed_packets = 0
    pending_demand = 0
    event_count = 0
    ticks_run = 0

    try:
        topology = load_sioux_falls_topology()
        topology_hash = topology.topology_hash
        manifest = load_sioux_falls_demand_manifest(
            topology=topology,
            scale_factor=scale_factor,
            departure_schedule=FixedDepartureSchedule(departure_tick=0),
        )
        demand_hash = manifest.manifest_hash
        od_pairs = len(manifest.declarations)
        total_declared_demand = manifest.total_declared_quantity_packets
        resolved = resolve_demand_routes(manifest, topology)
        resolved_routes = len(resolved.resolved_routes)
        loader = ScheduledDemandLoader(resolved)
        scheduled_departures = len(loader.scheduled_requests)
        engine = LoadingEngine(
            links=topology.as_loading_links(
                tick_duration_seconds=60.0,
                declared_storage_capacity_packets=storage_capacity_packets,
            ),
            nodes=topology.as_loading_nodes(),
        )

        loader.submit_due_departures(engine)
        instantiated_packets = len(engine.packets)
        pending_demand = len(engine.pending_demands)
        completed_packets = _completed_packets(engine)
        event_count = len(engine.event_log)

        while ticks_run < tick_limit:
            if (
                instantiated_packets == scheduled_departures
                and completed_packets == instantiated_packets
                and pending_demand == 0
            ):
                return _result(
                    scale_factor=scale_factor,
                    status="completed",
                    ticks_run=ticks_run,
                    tick_limit=tick_limit,
                    started_at=started_at,
                    topology_hash=topology_hash,
                    demand_hash=demand_hash,
                    od_pairs=od_pairs,
                    total_declared_demand=total_declared_demand,
                    resolved_routes=resolved_routes,
                    scheduled_departures=scheduled_departures,
                    instantiated_packets=instantiated_packets,
                    completed_packets=completed_packets,
                    pending_demand=pending_demand,
                    event_count=event_count,
                )

            engine.step()
            ticks_run = engine.current_tick
            loader.submit_due_departures(engine)
            instantiated_packets = len(engine.packets)
            pending_demand = len(engine.pending_demands)
            completed_packets = _completed_packets(engine)
            event_count = len(engine.event_log)

        return _result(
            scale_factor=scale_factor,
            status="tick_limit",
            ticks_run=ticks_run,
            tick_limit=tick_limit,
            started_at=started_at,
            topology_hash=topology_hash,
            demand_hash=demand_hash,
            od_pairs=od_pairs,
            total_declared_demand=total_declared_demand,
            resolved_routes=resolved_routes,
            scheduled_departures=scheduled_departures,
            instantiated_packets=instantiated_packets,
            completed_packets=completed_packets,
            pending_demand=pending_demand,
            event_count=event_count,
        )
    except MemoryError as exc:
        return _result(
            scale_factor=scale_factor,
            status="memory_error",
            ticks_run=ticks_run,
            tick_limit=tick_limit,
            started_at=started_at,
            topology_hash=topology_hash,
            demand_hash=demand_hash,
            od_pairs=od_pairs,
            total_declared_demand=total_declared_demand,
            resolved_routes=resolved_routes,
            scheduled_departures=scheduled_departures,
            instantiated_packets=instantiated_packets,
            completed_packets=completed_packets,
            pending_demand=pending_demand,
            event_count=event_count,
            failure=repr(exc),
        )
    except Exception as exc:  # pragma: no cover - benchmark diagnostics path.
        return _result(
            scale_factor=scale_factor,
            status="failure",
            ticks_run=ticks_run,
            tick_limit=tick_limit,
            started_at=started_at,
            topology_hash=topology_hash,
            demand_hash=demand_hash,
            od_pairs=od_pairs,
            total_declared_demand=total_declared_demand,
            resolved_routes=resolved_routes,
            scheduled_departures=scheduled_departures,
            instantiated_packets=instantiated_packets,
            completed_packets=completed_packets,
            pending_demand=pending_demand,
            event_count=event_count,
            failure=f"{type(exc).__name__}: {exc}",
        )
    finally:
        tracemalloc.stop()


def run_scale_sweep(
    *,
    scale_factors: tuple[float, ...],
    tick_limit: int,
    timeout_seconds: float,
    storage_capacity_packets: int,
) -> tuple[SiouxFallsDemandSmokeResult, ...]:
    """Run scale factors in isolated processes with per-scale timeout."""

    results: list[SiouxFallsDemandSmokeResult] = []
    for scale_factor in scale_factors:
        queue: mp.Queue[dict[str, Any]] = mp.Queue()
        process = mp.Process(
            target=_worker,
            kwargs={
                "queue": queue,
                "scale_factor": scale_factor,
                "tick_limit": tick_limit,
                "storage_capacity_packets": storage_capacity_packets,
            },
        )
        started_at = time.perf_counter()
        process.start()
        process.join(timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join()
            results.append(
                SiouxFallsDemandSmokeResult(
                    scale_factor=scale_factor,
                    status="timeout",
                    ticks_run=0,
                    tick_limit=tick_limit,
                    runtime_seconds=time.perf_counter() - started_at,
                    peak_memory_mb=None,
                    topology_hash=None,
                    demand_hash=None,
                    od_pairs=0,
                    total_declared_demand=0,
                    resolved_routes=0,
                    scheduled_departures=0,
                    instantiated_packets=0,
                    completed_packets=0,
                    pending_demand=0,
                    event_count=0,
                    failure=f"exceeded {timeout_seconds:.1f}s wall-clock limit",
                )
            )
            continue

        if queue.empty():
            results.append(
                SiouxFallsDemandSmokeResult(
                    scale_factor=scale_factor,
                    status="failure",
                    ticks_run=0,
                    tick_limit=tick_limit,
                    runtime_seconds=time.perf_counter() - started_at,
                    peak_memory_mb=None,
                    topology_hash=None,
                    demand_hash=None,
                    od_pairs=0,
                    total_declared_demand=0,
                    resolved_routes=0,
                    scheduled_departures=0,
                    instantiated_packets=0,
                    completed_packets=0,
                    pending_demand=0,
                    event_count=0,
                    failure=f"worker exited with code {process.exitcode}",
                )
            )
            continue

        results.append(SiouxFallsDemandSmokeResult(**queue.get()))
    return tuple(results)


def _worker(
    *,
    queue: mp.Queue[dict[str, Any]],
    scale_factor: float,
    tick_limit: int,
    storage_capacity_packets: int,
) -> None:
    result = run_sioux_falls_demand_smoke(
        scale_factor=scale_factor,
        tick_limit=tick_limit,
        storage_capacity_packets=storage_capacity_packets,
    )
    queue.put(asdict(result))


def _completed_packets(engine: LoadingEngine) -> int:
    return len(engine.completed_packet_ids)


def _result(
    *,
    scale_factor: float,
    status: str,
    ticks_run: int,
    tick_limit: int,
    started_at: float,
    topology_hash: str | None,
    demand_hash: str | None,
    od_pairs: int,
    total_declared_demand: int,
    resolved_routes: int,
    scheduled_departures: int,
    instantiated_packets: int,
    completed_packets: int,
    pending_demand: int,
    event_count: int,
    failure: str | None = None,
) -> SiouxFallsDemandSmokeResult:
    _, peak_bytes = tracemalloc.get_traced_memory()
    return SiouxFallsDemandSmokeResult(
        scale_factor=scale_factor,
        status=status,
        ticks_run=ticks_run,
        tick_limit=tick_limit,
        runtime_seconds=time.perf_counter() - started_at,
        peak_memory_mb=peak_bytes / 1_000_000,
        topology_hash=topology_hash,
        demand_hash=demand_hash,
        od_pairs=od_pairs,
        total_declared_demand=total_declared_demand,
        resolved_routes=resolved_routes,
        scheduled_departures=scheduled_departures,
        instantiated_packets=instantiated_packets,
        completed_packets=completed_packets,
        pending_demand=pending_demand,
        event_count=event_count,
        failure=failure,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Sioux Falls full-OD demand through today's loading engine.",
    )
    parser.add_argument(
        "--scales",
        nargs="+",
        type=float,
        default=(0.001, 0.01, 0.1, 1.0),
        help="Demand scale factors to run.",
    )
    parser.add_argument(
        "--tick-limit",
        type=int,
        default=200,
        help="Maximum loading ticks per scale.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="Wall-clock timeout per scale.",
    )
    parser.add_argument(
        "--storage-capacity-packets",
        type=int,
        default=1_000_000,
        help="Origin/link storage capacity passed to topology loading links.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a markdown table.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    results = run_scale_sweep(
        scale_factors=tuple(args.scales),
        tick_limit=args.tick_limit,
        timeout_seconds=args.timeout_seconds,
        storage_capacity_packets=args.storage_capacity_packets,
    )
    if args.json:
        print(json.dumps([asdict(result) for result in results], indent=2))
    else:
        print(_markdown_table(results))


def _markdown_table(results: tuple[SiouxFallsDemandSmokeResult, ...]) -> str:
    lines = [
        "| scale | status | runtime_s | peak_mb | ticks | OD pairs | demand | routes | instantiated | completed | pending | events |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        peak_memory = (
            f"{result.peak_memory_mb:.1f}"
            if result.peak_memory_mb is not None
            else ""
        )
        lines.append(
            "| "
            f"{result.scale_factor:g} | "
            f"{result.status} | "
            f"{result.runtime_seconds:.3f} | "
            f"{peak_memory} | "
            f"{result.ticks_run}/{result.tick_limit} | "
            f"{result.od_pairs} | "
            f"{result.total_declared_demand} | "
            f"{result.resolved_routes} | "
            f"{result.instantiated_packets} | "
            f"{result.completed_packets} | "
            f"{result.pending_demand} | "
            f"{result.event_count} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
