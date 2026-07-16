"""Seeded Figure 8 stochastic extension of the frozen Figure 7 diverge.

All stochasticity is confined to validation-fixture route assignment. The
loading engine receives ordinary immutable route intents and is unchanged.
"""

from __future__ import annotations

import hashlib
import math
import random
import statistics
from dataclasses import dataclass

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import DemandDeclaration, Event, EventType, Link, Node
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.validation import ValidationContext
from urban_cybernetics.validation.physical import assess_physical_parameter_eligibility


FIGURE8_REPLICATION_COUNT = 100
FIGURE8_SEEDS = tuple(range(FIGURE8_REPLICATION_COUNT))
FIGURE8_ROUTE_PROBABILITY_L2 = 0.75
FIGURE8_ROUTE_PROBABILITY_L3 = 0.25
FIGURE8_FINAL_TICK = 120
FIGURE8_PACKET_COUNT = 68
FIGURE8_SERIES_IDS = (
    "upstream_cumulative_outflow",
    "downstream_1_cumulative_inflow",
    "downstream_2_cumulative_inflow",
)


@dataclass(frozen=True, slots=True)
class Figure8ReplicationResult:
    """Complete compact evidence for one exactly replayable seeded run."""

    seed: int
    route_sequence: tuple[str, ...]
    route_sequence_sha256: str
    route_count_l2: int
    route_count_l3: int
    route_share_l2: float
    route_share_l3: float
    upstream_cumulative_outflow: tuple[int, ...]
    downstream_1_cumulative_inflow: tuple[int, ...]
    downstream_2_cumulative_inflow: tuple[int, ...]
    event_count: int
    conservation_check: bool
    fifo_check: bool
    identity_check: bool
    cumulative_closure_check: bool
    physical_eligibility_check: bool
    replay_check: bool

    @property
    def all_checks_pass(self) -> bool:
        return all((
            self.conservation_check,
            self.fifo_check,
            self.identity_check,
            self.cumulative_closure_check,
            self.physical_eligibility_check,
            self.replay_check,
        ))


def figure8_route_sequence(seed: int) -> tuple[str, ...]:
    """Draw 68 independent routes from a local, explicitly seeded RNG."""

    rng = random.Random(seed)
    return tuple(
        "L2" if rng.random() < FIGURE8_ROUTE_PROBABILITY_L2 else "L3"
        for _ in range(FIGURE8_PACKET_COUNT)
    )


def figure8_departures() -> tuple[int, ...]:
    """Return the Figure 7(a) tick-end floored Equation 14 departures."""

    departures: list[int] = []
    previous_total = 0
    for tick in range(1, FIGURE8_FINAL_TICK + 1):
        cumulative = 0.8 * tick if tick <= 50 else 40 + 0.4 * (tick - 50)
        target_total = math.floor(cumulative + 1e-12)
        departures.extend(tick for _ in range(previous_total, target_total))
        previous_total = target_total
    if len(departures) != FIGURE8_PACKET_COUNT:
        raise AssertionError(f"Figure 8 demand resolved {len(departures)} packets")
    return tuple(departures)


def run_figure8_replication(seed: int) -> Figure8ReplicationResult:
    """Execute and independently replay one seeded Figure 8 replication."""

    routes = figure8_route_sequence(seed)
    engine = _run_engine(routes)
    replay = _run_engine(figure8_route_sequence(seed))
    events = engine.event_log
    upstream = _cumulative(events, EventType.LINK_EXIT, "L1")
    downstream_1 = _cumulative(events, EventType.LINK_ENTRY, "L2")
    downstream_2 = _cumulative(events, EventType.LINK_ENTRY, "L3")
    upstream_order = tuple(
        event.packet_id for event in events
        if event.event_type == EventType.LINK_EXIT and event.entity_id == "L1"
    )
    downstream_order = tuple(
        event.packet_id for event in events
        if event.event_type == EventType.LINK_ENTRY and event.entity_id in {"L2", "L3"}
    )
    instantiated = tuple(
        event.packet_id for event in events if event.event_type == EventType.INSTANTIATED
    )
    route_bytes = ",".join(routes).encode("ascii")
    count_l2 = routes.count("L2")
    count_l3 = routes.count("L3")
    physical = assess_physical_parameter_eligibility(tuple(engine.links.values()))
    context = ValidationContext.from_engine(
        engine, nodes=tuple(engine.nodes.values()),
        run_config={"case_id": "M8-PUB-DSOUZA-FIG8-DT1", "seed": seed},
    )
    return Figure8ReplicationResult(
        seed=seed,
        route_sequence=routes,
        route_sequence_sha256=hashlib.sha256(route_bytes).hexdigest(),
        route_count_l2=count_l2,
        route_count_l3=count_l3,
        route_share_l2=count_l2 / FIGURE8_PACKET_COUNT,
        route_share_l3=count_l3 / FIGURE8_PACKET_COUNT,
        upstream_cumulative_outflow=upstream,
        downstream_1_cumulative_inflow=downstream_1,
        downstream_2_cumulative_inflow=downstream_2,
        event_count=len(events),
        conservation_check=engine.check_conservation(),
        fifo_check=upstream_order == downstream_order,
        identity_check=(
            len(instantiated) == FIGURE8_PACKET_COUNT
            and len(set(instantiated)) == FIGURE8_PACKET_COUNT
            and instantiated == tuple(f"P{index}" for index in range(1, 69))
            and context.count_consistency_report.is_consistent
            and engine.check_event_cache_consistency()
        ),
        cumulative_closure_check=all(
            gu == f1 + f2 for gu, f1, f2 in zip(upstream, downstream_1, downstream_2)
        ),
        physical_eligibility_check=physical.is_parity_eligible,
        replay_check=(
            replay.event_log == events
            and tuple(packet.route_intent[-1] for packet in replay.packets.values()) == routes
        ),
    )


def run_figure8_ensemble(
    seeds: tuple[int, ...] = FIGURE8_SEEDS,
) -> tuple[Figure8ReplicationResult, ...]:
    """Run the declared ordered seed ensemble."""

    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("Figure 8 seeds must be a non-empty unique sequence")
    return tuple(run_figure8_replication(seed) for seed in seeds)


def summarise_figure8_ensemble(
    replications: tuple[Figure8ReplicationResult, ...],
    deterministic: dict[str, tuple[float, ...]],
) -> dict[str, object]:
    """Return pointwise bands, endpoint distributions, and deterministic coverage."""

    if not replications:
        raise ValueError("Figure 8 ensemble cannot be empty")
    if not all(replication.all_checks_pass for replication in replications):
        raise ValueError("Figure 8 ensemble contains a failed validation gate")
    pointwise: dict[str, list[dict[str, float | int]]] = {}
    deterministic_coverage: dict[str, dict[str, object]] = {}
    mean_deviation: dict[str, dict[str, float | int]] = {}
    for series_id in FIGURE8_SERIES_IDS:
        rows: list[dict[str, float | int]] = []
        values_by_replication = [_series(replication, series_id) for replication in replications]
        reference = deterministic[series_id]
        for tick in range(FIGURE8_FINAL_TICK + 1):
            values = sorted(series[tick] for series in values_by_replication)
            rows.append({
                "tick": tick,
                "time_seconds": tick,
                "mean": statistics.fmean(values),
                "median": statistics.median(values),
                "minimum": values[0],
                "maximum": values[-1],
                "p05": _quantile(values, 0.05),
                "p95": _quantile(values, 0.95),
                "deterministic": reference[tick],
            })
        pointwise[series_id] = rows
        envelope_outside = [
            row["tick"] for row in rows
            if not row["minimum"] <= row["deterministic"] <= row["maximum"]
        ]
        percentile_outside = [
            row["tick"] for row in rows
            if not row["p05"] <= row["deterministic"] <= row["p95"]
        ]
        deterministic_coverage[series_id] = {
            "within_envelope_every_tick": not envelope_outside,
            "envelope_coverage_tick_count": len(rows) - len(envelope_outside),
            "envelope_coverage_fraction": (len(rows) - len(envelope_outside)) / len(rows),
            "first_tick_outside_envelope": envelope_outside[0] if envelope_outside else None,
            "within_p05_p95_every_tick": not percentile_outside,
            "p05_p95_coverage_tick_count": len(rows) - len(percentile_outside),
            "p05_p95_coverage_fraction": (len(rows) - len(percentile_outside)) / len(rows),
            "first_tick_outside_p05_p95": percentile_outside[0] if percentile_outside else None,
        }
        differences = [row["mean"] - row["deterministic"] for row in rows]
        absolute = [abs(value) for value in differences]
        mean_deviation[series_id] = {
            "mean_absolute_difference_packets": statistics.fmean(absolute),
            "rmse_packets": math.sqrt(statistics.fmean(value * value for value in differences)),
            "maximum_absolute_difference_packets": max(absolute),
            "maximum_absolute_difference_tick": absolute.index(max(absolute)),
            "final_signed_difference_packets": differences[-1],
        }

    endpoints = {
        series_id: _distribution(
            [_series(replication, series_id)[-1] for replication in replications]
        )
        for series_id in (
            "downstream_1_cumulative_inflow", "downstream_2_cumulative_inflow"
        )
    }
    route_counts_l2 = [replication.route_count_l2 for replication in replications]
    route_counts_l3 = [replication.route_count_l3 for replication in replications]
    route_shares_l2 = [replication.route_share_l2 for replication in replications]
    route_shares_l3 = [replication.route_share_l3 for replication in replications]
    return {
        "replication_count": len(replications),
        "seeds": [replication.seed for replication in replications],
        "seed_policy": "ordered integer seeds 0 through 99; random.Random(seed)",
        "route_draw_policy": "68 independent draws; L2 when U[0,1)<0.75, otherwise L3",
        "pointwise": pointwise,
        "deterministic_coverage": deterministic_coverage,
        "ensemble_mean_deviation_from_deterministic": mean_deviation,
        "endpoint_distributions": endpoints,
        "route_distribution": {
            "L2_count": _distribution(route_counts_l2),
            "L3_count": _distribution(route_counts_l3),
            "L2_share": _distribution(route_shares_l2),
            "L3_share": _distribution(route_shares_l3),
            "mean_L2_share_minus_0_75": statistics.fmean(route_shares_l2) - 0.75,
            "mean_L3_share_minus_0_25": statistics.fmean(route_shares_l3) - 0.25,
        },
        "validation_gates": {
            "all_replications_pass": all(replication.all_checks_pass for replication in replications),
            "conservation_pass_count": sum(r.conservation_check for r in replications),
            "fifo_pass_count": sum(r.fifo_check for r in replications),
            "identity_pass_count": sum(r.identity_check for r in replications),
            "cumulative_closure_pass_count": sum(r.cumulative_closure_check for r in replications),
            "physical_eligibility_pass_count": sum(r.physical_eligibility_check for r in replications),
            "replay_pass_count": sum(r.replay_check for r in replications),
        },
    }


def _run_engine(routes: tuple[str, ...]) -> LoadingEngine:
    if len(routes) != FIGURE8_PACKET_COUNT or set(routes) - {"L2", "L3"}:
        raise ValueError("Figure 8 requires exactly 68 L2/L3 route destinations")
    links = {
        "L1": _link("L1", jam_density=0.2, capacity=1.0),
        "L2": _link("L2", jam_density=0.1, capacity=0.5),
        "L3": _link("L3", jam_density=0.1, capacity=0.5),
    }
    engine = LoadingEngine(
        links=links,
        nodes=(Node("N1", incoming_link_ids=("L1",), outgoing_link_ids=("L2", "L3")),),
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        parity_sending_capacity_vehicles_per_tick_by_link={"L1": 1.0, "L2": 0.5, "L3": 0.5},
        parity_receiving_capacity_vehicles_per_tick_by_link={"L1": 1.0, "L2": 0.5, "L3": 0.5},
        parity_initial_receiving_credit_by_link={"L2": 0.0, "L3": 0.0},
    )
    for index, (departure, downstream) in enumerate(
        zip(figure8_departures(), routes), start=1
    ):
        engine.instantiate(DemandDeclaration(
            f"DESOUZA-FIG8-S{index:03d}", departure, ("L1", downstream)
        ))
    while engine.current_tick < FIGURE8_FINAL_TICK:
        engine.step()
    return engine


def _link(link_id: str, *, jam_density: float, capacity: float) -> Link:
    return Link(
        link_id=link_id, length_m=150.0, lane_count=1,
        free_flow_speed_mps=30.0, backward_wave_speed_mps=6.0,
        jam_density_veh_per_km_per_lane=jam_density * 1000,
        capacity_veh_per_hour_per_lane=capacity * 3600,
        tick_duration_seconds=1.0,
        declared_sending_capacity_per_tick=math.floor(capacity),
        declared_receiving_capacity_per_tick=math.floor(capacity),
    )


def _cumulative(
    events: tuple[Event, ...], event_type: EventType, entity_id: str,
) -> tuple[int, ...]:
    counts = [0] * (FIGURE8_FINAL_TICK + 1)
    for event in events:
        if event.event_type == event_type and event.entity_id == entity_id:
            counts[event.physical_tick] += 1
    running = 0
    cumulative = []
    for count in counts:
        running += count
        cumulative.append(running)
    return tuple(cumulative)


def _series(
    replication: Figure8ReplicationResult, series_id: str,
) -> tuple[int, ...]:
    return getattr(replication, series_id)


def _quantile(sorted_values: list[float | int], probability: float) -> float:
    """Linear Type-7 quantile, matching common NumPy/Python conventions."""

    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(sorted_values[lower])
    weight = position - lower
    return float(sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight)


def _distribution(values: list[float | int]) -> dict[str, float | int]:
    ordered = sorted(values)
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "population_standard_deviation": statistics.pstdev(values),
        "minimum": ordered[0],
        "p05": _quantile(ordered, 0.05),
        "p25": _quantile(ordered, 0.25),
        "median": statistics.median(ordered),
        "p75": _quantile(ordered, 0.75),
        "p95": _quantile(ordered, 0.95),
        "maximum": ordered[-1],
    }
