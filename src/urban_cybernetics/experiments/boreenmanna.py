"""Controlled representation comparison on real OSM-derived Cork geometry."""

from __future__ import annotations

import json
import tracemalloc
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter, process_time
from typing import Mapping, Self

from urban_cybernetics.compiler.model import canonical_json, stable_hash
from urban_cybernetics.compiler.osm_experiment import (
    BoreenmannaExperimentCompilation,
    compile_boreenmanna_experiment,
)
from urban_cybernetics.core import DemandDeclaration, EventType
from urban_cybernetics.extensions.fixed_time_signals import (
    FixedTimeSignalControlMixin,
    FixedTimeSignalPlanEvaluator,
)
from urban_cybernetics.extensions.fractional_service_credit import (
    FRACTIONAL_CREDIT,
    LEGACY_INTEGER_CLAMPED,
    FractionalServiceCreditConfig,
    FractionalServiceCreditMixin,
    service_credit_config_for_executable,
)
from urban_cybernetics.loading.lane_group_extension import (
    EXPLICIT_LANE_GROUP_FIFO,
    MOVEMENT_PARTIAL_FIFO,
    SHARED_LINK_FIFO,
    LaneGroupExtensionConfig,
    LaneGroupLoadingEngine,
)


BOREENMANNA_DEMAND_SCHEMA_VERSION = "uc.boreenmanna-synthetic-demand.v1"
BOREENMANNA_RUN_MANIFEST_VERSION = "uc.boreenmanna-run-manifest.v1"
BOREENMANNA_MATRIX_VERSION = "uc.boreenmanna-representation-matrix.v1"
REPRESENTATION_MODES = (
    SHARED_LINK_FIFO,
    MOVEMENT_PARTIAL_FIFO,
    EXPLICIT_LANE_GROUP_FIFO,
)
SERVICE_MODES = (LEGACY_INTEGER_CLAMPED, FRACTIONAL_CREDIT)


class BoreenmannaExperimentIntegrityError(ValueError):
    """Raised for malformed demand, run, or matrix evidence."""


@dataclass(frozen=True, slots=True)
class SyntheticDemandItem:
    demand_id: str
    route_name: str
    departure_tick: int
    route_intent: tuple[str, ...]
    actor_source_id: str = "urban-cybernetics:synthetic-demand-policy:v1"
    reason: str = "controlled uncalibrated representation-comparison demand"
    classification: str = "synthetic_experiment"
    unit: str = "unit_packet"
    schema_version: str = BOREENMANNA_DEMAND_SCHEMA_VERSION
    item_hash: str = ""

    def __post_init__(self) -> None:
        if not self.demand_id or not self.route_name or self.departure_tick < 0:
            raise BoreenmannaExperimentIntegrityError("invalid synthetic demand item")
        if not self.route_intent:
            raise BoreenmannaExperimentIntegrityError("demand route cannot be empty")
        if self.classification != "synthetic_experiment":
            raise BoreenmannaExperimentIntegrityError(
                "demand must remain classified synthetic_experiment"
            )
        expected = stable_hash("boreenmanna-synthetic-demand-item", self._payload())
        if self.item_hash and self.item_hash != expected:
            raise BoreenmannaExperimentIntegrityError("demand item hash mismatch")
        object.__setattr__(self, "item_hash", expected)

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "demand_id": self.demand_id,
            "route_name": self.route_name,
            "departure_tick": self.departure_tick,
            "route_intent": list(self.route_intent),
            "actor_source_id": self.actor_source_id,
            "reason": self.reason,
            "classification": self.classification,
            "unit": self.unit,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "item_hash": self.item_hash}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            demand_id=str(payload["demand_id"]),
            route_name=str(payload["route_name"]),
            departure_tick=int(payload["departure_tick"]),
            route_intent=tuple(str(item) for item in payload["route_intent"]),  # type: ignore[index]
            actor_source_id=str(payload["actor_source_id"]),
            reason=str(payload["reason"]),
            classification=str(payload["classification"]),
            unit=str(payload["unit"]),
            schema_version=str(payload["schema_version"]),
            item_hash=str(payload.get("item_hash", "")),
        )

    def declaration(self) -> DemandDeclaration:
        return DemandDeclaration(
            demand_id=self.demand_id,
            departure_tick=self.departure_tick,
            route_intent=self.route_intent,
        )


@dataclass(frozen=True, slots=True)
class SyntheticDemandScenario:
    scenario_id: str
    horizon_ticks: int
    fixed_seed: int
    demands: tuple[SyntheticDemandItem, ...]
    schema_version: str = BOREENMANNA_DEMAND_SCHEMA_VERSION
    scenario_hash: str = ""

    def __post_init__(self) -> None:
        if not self.scenario_id or self.horizon_ticks <= 0 or self.fixed_seed < 0:
            raise BoreenmannaExperimentIntegrityError("invalid demand scenario")
        ordered = tuple(sorted(self.demands, key=lambda item: item.demand_id))
        if len({item.demand_id for item in ordered}) != len(ordered):
            raise BoreenmannaExperimentIntegrityError("duplicate demand IDs")
        object.__setattr__(self, "demands", ordered)
        expected = stable_hash("boreenmanna-demand-scenario", self._payload())
        if self.scenario_hash and self.scenario_hash != expected:
            raise BoreenmannaExperimentIntegrityError("demand scenario hash mismatch")
        object.__setattr__(self, "scenario_hash", expected)

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "scenario_id": self.scenario_id,
            "horizon_ticks": self.horizon_ticks,
            "fixed_seed": self.fixed_seed,
            "demands": [item.to_dict() for item in self.demands],
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "scenario_hash": self.scenario_hash}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            scenario_id=str(payload["scenario_id"]),
            horizon_ticks=int(payload["horizon_ticks"]),
            fixed_seed=int(payload["fixed_seed"]),
            demands=tuple(
                SyntheticDemandItem.from_dict(item)
                for item in payload["demands"]  # type: ignore[index]
            ),
            schema_version=str(payload["schema_version"]),
            scenario_hash=str(payload.get("scenario_hash", "")),
        )


@dataclass(frozen=True, slots=True)
class BoreenmannaRunManifest:
    """Deterministic outputs plus separately identified machine measurements."""

    deterministic_payload_json: str
    performance_payload_json: str
    version: str = BOREENMANNA_RUN_MANIFEST_VERSION
    deterministic_hash: str = ""
    manifest_hash: str = ""

    def __post_init__(self) -> None:
        deterministic = canonical_json(json.loads(self.deterministic_payload_json))
        performance = canonical_json(json.loads(self.performance_payload_json))
        object.__setattr__(self, "deterministic_payload_json", deterministic)
        object.__setattr__(self, "performance_payload_json", performance)
        expected_deterministic = stable_hash(
            "boreenmanna-run-deterministic", json.loads(deterministic)
        )
        if self.deterministic_hash and self.deterministic_hash != expected_deterministic:
            raise BoreenmannaExperimentIntegrityError("run deterministic hash mismatch")
        object.__setattr__(self, "deterministic_hash", expected_deterministic)
        expected_manifest = stable_hash(
            "boreenmanna-run-manifest",
            {
                "version": self.version,
                "deterministic_hash": expected_deterministic,
                "performance": json.loads(performance),
            },
        )
        if self.manifest_hash and self.manifest_hash != expected_manifest:
            raise BoreenmannaExperimentIntegrityError("run manifest hash mismatch")
        object.__setattr__(self, "manifest_hash", expected_manifest)

    @property
    def deterministic(self) -> dict[str, object]:
        return json.loads(self.deterministic_payload_json)

    @property
    def performance(self) -> dict[str, object]:
        return json.loads(self.performance_payload_json)

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "deterministic": self.deterministic,
            "performance": self.performance,
            "deterministic_hash": self.deterministic_hash,
            "manifest_hash": self.manifest_hash,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            deterministic_payload_json=canonical_json(payload["deterministic"]),
            performance_payload_json=canonical_json(payload["performance"]),
            version=str(payload["version"]),
            deterministic_hash=str(payload.get("deterministic_hash", "")),
            manifest_hash=str(payload.get("manifest_hash", "")),
        )


@dataclass(frozen=True, slots=True)
class BoreenmannaExperimentMatrix:
    compilation_package_hash: str
    runs: tuple[BoreenmannaRunManifest, ...]
    version: str = BOREENMANNA_MATRIX_VERSION
    matrix_hash: str = ""

    def __post_init__(self) -> None:
        ordered = tuple(
            sorted(
                self.runs,
                key=lambda item: (
                    str(item.deterministic["scenario_id"]),
                    str(item.deterministic["service_credit_mode"]),
                    str(item.deterministic["representation_mode"]),
                ),
            )
        )
        object.__setattr__(self, "runs", ordered)
        expected = stable_hash(
            "boreenmanna-experiment-matrix",
            {
                "version": self.version,
                "compilation_package_hash": self.compilation_package_hash,
                "run_deterministic_hashes": [
                    item.deterministic_hash for item in ordered
                ],
            },
        )
        if self.matrix_hash and self.matrix_hash != expected:
            raise BoreenmannaExperimentIntegrityError("matrix hash mismatch")
        object.__setattr__(self, "matrix_hash", expected)

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "compilation_package_hash": self.compilation_package_hash,
            "runs": [item.to_dict() for item in self.runs],
            "matrix_hash": self.matrix_hash,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            compilation_package_hash=str(payload["compilation_package_hash"]),
            runs=tuple(
                BoreenmannaRunManifest.from_dict(item)
                for item in payload["runs"]  # type: ignore[index]
            ),
            version=str(payload["version"]),
            matrix_hash=str(payload.get("matrix_hash", "")),
        )

    @classmethod
    def from_json(cls, serialised: str) -> Self:
        payload = json.loads(serialised)
        if not isinstance(payload, dict):
            raise BoreenmannaExperimentIntegrityError("matrix JSON must be an object")
        return cls.from_dict(payload)


class _BoreenmannaEngine(
    FixedTimeSignalControlMixin,
    FractionalServiceCreditMixin,
    LaneGroupLoadingEngine,
):
    pass


def build_boreenmanna_demand_scenarios(
    compilation: BoreenmannaExperimentCompilation,
) -> tuple[SyntheticDemandScenario, SyntheticDemandScenario]:
    executable = compilation.synthetic_result.require_executable()
    routes = _principal_routes(executable.resolved_links, executable.topology.nodes)
    return (
        _demand_scenario("moderate", routes, copies=4, horizon=120),
        _demand_scenario("stress", routes, copies=12, horizon=180),
    )


def run_boreenmanna_experiment_matrix(
    source_path: str | Path,
) -> tuple[BoreenmannaExperimentCompilation, tuple[SyntheticDemandScenario, ...], BoreenmannaExperimentMatrix]:
    compilation = compile_boreenmanna_experiment(source_path)
    scenarios = build_boreenmanna_demand_scenarios(compilation)
    runs = tuple(
        _run_case(compilation, scenario, representation, service_mode)
        for scenario in scenarios
        for service_mode in SERVICE_MODES
        for representation in REPRESENTATION_MODES
    )
    return (
        compilation,
        scenarios,
        BoreenmannaExperimentMatrix(
            compilation_package_hash=compilation.package.package_hash,
            runs=runs,
        ),
    )


def write_boreenmanna_experiment_outputs(
    *,
    compilation: BoreenmannaExperimentCompilation,
    scenarios: tuple[SyntheticDemandScenario, ...],
    matrix: BoreenmannaExperimentMatrix,
    output_directory: str | Path,
) -> tuple[Path, ...]:
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    compilation_path = directory / "boreenmanna_experiment_compilation_v1.json"
    demand_path = directory / "boreenmanna_synthetic_demand_v1.json"
    matrix_path = directory / "boreenmanna_representation_matrix_v1.json"
    csv_path = directory / "boreenmanna_representation_summary_v1.csv"
    compilation_path.write_text(compilation.package.to_json(), encoding="utf-8")
    demand_path.write_text(
        json.dumps(
            {"schema_version": BOREENMANNA_DEMAND_SCHEMA_VERSION, "scenarios": [item.to_dict() for item in scenarios]},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    matrix_path.write_text(matrix.to_json(), encoding="utf-8")
    columns = (
        "scenario_id",
        "service_credit_mode",
        "representation_mode",
        "completed_throughput",
        "incomplete_packets",
        "mean_queue_delay_ticks",
        "peak_queue",
        "event_count",
        "credit_evidence_count",
        "wall_clock_seconds",
        "peak_memory_bytes",
        "deterministic_hash",
    )
    rows = [",".join(columns)]
    for run in matrix.runs:
        deterministic = run.deterministic
        performance = run.performance
        rows.append(
            ",".join(
                str(value)
                for value in (
                    deterministic["scenario_id"],
                    deterministic["service_credit_mode"],
                    deterministic["representation_mode"],
                    deterministic["completed_throughput"],
                    deterministic["incomplete_packets"],
                    deterministic["mean_queue_delay_ticks"],
                    deterministic["peak_queue"],
                    deterministic["canonical_event_count"],
                    deterministic["credit_evidence_count"],
                    performance["wall_clock_seconds"],
                    performance["peak_memory_bytes"],
                    run.deterministic_hash,
                )
            )
        )
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return compilation_path, demand_path, matrix_path, csv_path


def _run_case(
    compilation: BoreenmannaExperimentCompilation,
    scenario: SyntheticDemandScenario,
    representation: str,
    service_mode: str,
) -> BoreenmannaRunManifest:
    tracemalloc.start()
    wall_start = perf_counter()
    cpu_start = process_time()
    first = _execute_case(compilation, scenario, representation, service_mode)
    cpu_seconds = process_time() - cpu_start
    wall_seconds = perf_counter() - wall_start
    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    replay_start = perf_counter()
    replay = _execute_case(compilation, scenario, representation, service_mode)
    replay_seconds = perf_counter() - replay_start
    if first["replay_payload"] != replay["replay_payload"]:
        raise BoreenmannaExperimentIntegrityError(
            "exact replay mismatch for Boreenmanna experiment case"
        )
    deterministic = dict(first["summary"])
    deterministic["replay_passed"] = True
    performance = {
        "measurement_class": "machine_dependent",
        "wall_clock_seconds": wall_seconds,
        "cpu_seconds": cpu_seconds,
        "peak_memory_bytes": peak_memory,
        "replay_wall_clock_seconds": replay_seconds,
    }
    return BoreenmannaRunManifest(
        deterministic_payload_json=canonical_json(deterministic),
        performance_payload_json=canonical_json(performance),
    )


def _execute_case(
    compilation: BoreenmannaExperimentCompilation,
    scenario: SyntheticDemandScenario,
    representation: str,
    service_mode: str,
) -> dict[str, object]:
    executable = compilation.synthetic_result.require_executable()
    nodes = executable.topology.as_loading_nodes()
    lane_config = LaneGroupExtensionConfig(
        representation_mode=representation,
        lane_groups=executable.lane_group_config.lane_groups,
    )
    service_config = service_credit_config_for_executable(
        executable, mode=service_mode
    )
    provider = FixedTimeSignalPlanEvaluator(executable.signal_plan, nodes)
    engine = _BoreenmannaEngine(
        links=executable.loading_links(),
        nodes=nodes,
        lane_group_config=lane_config,
        fixed_time_signal_provider=provider,
        fractional_service_credit_config=service_config,
        executable_semantic_hash=executable.executable_semantic_hash,
    )
    for demand in scenario.demands:
        engine.instantiate(demand.declaration())
    allocation_history = []
    lane_history = []
    for _ in range(scenario.horizon_ticks):
        engine.step()
        allocation_history.append(engine.node_transfer_traces())
        lane_history.append(engine.lane_group_allocator.last_lane_group_allocation_traces)
    replay_payload = _replay_payload(engine, allocation_history, lane_history)
    metrics = _deterministic_metrics(
        engine,
        allocation_history,
        scenario,
        provider,
    )
    allocation_payload = [
        [asdict(trace) for trace in traces] for traces in allocation_history
    ]
    serialized_evidence_size = len(canonical_json(replay_payload).encode("utf-8"))
    summary = {
        "source_file_sha256": compilation.base.package.source.file_sha256,
        "extraction_hash": compilation.base.package.extraction.extraction_hash,
        "reviewed_physical_assumptions_hash": stable_hash(
            "reviewed-assumptions",
            [item.to_dict() for item in compilation.base.package.reviewed_assumptions],
        ),
        "synthetic_control_dossier_hash": compilation.dossier.dossier_hash,
        "demand_scenario_hash": scenario.scenario_hash,
        "scenario_id": scenario.scenario_id,
        "fixed_seed": scenario.fixed_seed,
        "horizon_ticks": scenario.horizon_ticks,
        "fractional_credit_configuration_hash": service_config.config_hash,
        "service_credit_mode": service_mode,
        "representation_configuration_hash": lane_config.config_hash,
        "representation_mode": representation,
        "representation_evidence_status": {
            SHARED_LINK_FIFO: "conservative_fallback",
            MOVEMENT_PARTIAL_FIFO: "synthetic_experimental_representation",
            EXPLICIT_LANE_GROUP_FIFO: "synthetic_lane_to_movement_assignments",
        }[representation],
        "executable_semantic_hash": executable.executable_semantic_hash,
        "compiler_compilation_identity_hash": (
            compilation.synthetic_result.evidence_bundle.compilation_identity_hash
        ),
        "run_configuration_hash": stable_hash(
            "boreenmanna-run-config",
            {
                "scenario_hash": scenario.scenario_hash,
                "service_config_hash": service_config.config_hash,
                "representation_config_hash": lane_config.config_hash,
                "executable_semantic_hash": executable.executable_semantic_hash,
                "horizon": scenario.horizon_ticks,
                "seed": scenario.fixed_seed,
            },
        ),
        **metrics,
        "allocation_trace_serialized_bytes": len(
            canonical_json(allocation_payload).encode("utf-8")
        ),
        "serialized_evidence_bytes": serialized_evidence_size,
        "event_log_hash": stable_hash("boreenmanna-event-log", replay_payload["events"]),
        "credit_evidence_hash": engine.fractional_service_credit_evidence_hash,
        "signal_evidence_hash": engine.fixed_time_signal_evidence_hash,
    }
    return {"summary": summary, "replay_payload": replay_payload}


def _deterministic_metrics(engine, allocation_history, scenario, provider) -> dict[str, object]:
    events = engine.event_log
    event_counts = Counter(item.event_type.value for item in events)
    queue_entry_tick: dict[tuple[str, str], int] = {}
    queue_delays = []
    queue_delays_by_boundary: dict[str, list[int]] = defaultdict(list)
    queue_lengths: dict[str, int] = defaultdict(int)
    peak_queue_by_boundary: dict[str, int] = defaultdict(int)
    occupancy: dict[str, int] = defaultdict(int)
    peak_occupancy: dict[str, int] = defaultdict(int)
    instantiated: dict[str, int] = {}
    completed: dict[str, int] = {}
    for event in events:
        if event.event_type == EventType.INSTANTIATED:
            instantiated[event.packet_id] = event.physical_tick
        elif event.event_type == EventType.COMPLETED:
            completed[event.packet_id] = event.physical_tick
        elif event.event_type == EventType.QUEUE_ENTRY:
            queue_entry_tick[(event.packet_id, event.entity_id)] = event.physical_tick
            queue_lengths[event.entity_id] += 1
            peak_queue_by_boundary[event.entity_id] = max(
                peak_queue_by_boundary[event.entity_id], queue_lengths[event.entity_id]
            )
        elif event.event_type == EventType.QUEUE_EXIT:
            start = queue_entry_tick.pop((event.packet_id, event.entity_id))
            delay = event.physical_tick - start
            queue_delays.append(delay)
            queue_delays_by_boundary[event.entity_id].append(delay)
            queue_lengths[event.entity_id] -= 1
        elif event.event_type == EventType.LINK_ENTRY:
            occupancy[event.entity_id] += 1
            peak_occupancy[event.entity_id] = max(
                peak_occupancy[event.entity_id], occupancy[event.entity_id]
            )
        elif event.event_type == EventType.LINK_EXIT:
            occupancy[event.entity_id] -= 1
    for (_, boundary_id), start in queue_entry_tick.items():
        delay = engine.current_tick - start
        queue_delays.append(delay)
        queue_delays_by_boundary[boundary_id].append(delay)
    blocked = Counter()
    movement_throughput = Counter()
    signal_stage_discharge = Counter()
    spillback_ticks = set()
    for tick, traces in enumerate(allocation_history, start=1):
        for trace in traces:
            blocked.update(reason for _, reason in trace.rejected_transfer_reasons)
            if any(
                reason == "downstream_supply_unavailable"
                for _, reason in trace.rejected_transfer_reasons
            ):
                spillback_ticks.add(tick)
            for movement in trace.movement_flow_summaries:
                movement_throughput[movement.movement_id] += movement.approved_count
                if movement.approved_count:
                    state = provider.evaluate(movement.movement_id, tick)
                    if state is not None:
                        signal_stage_discharge[
                            f"{state.controller_id}:{state.stage_id}"
                        ] += movement.approved_count
    travel_times = tuple(
        sorted(
            completed[packet_id] - start
            for packet_id, start in instantiated.items()
            if packet_id in completed
        )
    )
    completed_count = len(engine.completed_packet_ids)
    conservation = engine.conservation_summary()
    return {
        "demand_packet_count": len(scenario.demands),
        "completed_throughput": completed_count,
        "incomplete_packets": len(scenario.demands) - completed_count,
        "queue_entry_count": event_counts["queue_entry"],
        "queue_exit_count": event_counts["queue_exit"],
        "peak_queue": max(peak_queue_by_boundary.values(), default=0),
        "peak_queue_by_boundary": sorted(peak_queue_by_boundary.items()),
        "total_queue_delay_ticks": sum(queue_delays),
        "mean_queue_delay_ticks": (
            sum(queue_delays) / len(queue_delays) if queue_delays else 0.0
        ),
        "queue_delay_by_boundary": [
            {
                "boundary_id": boundary_id,
                "total_delay_ticks": sum(values),
                "mean_delay_ticks": sum(values) / len(values),
                "observation_count": len(values),
            }
            for boundary_id, values in sorted(queue_delays_by_boundary.items())
        ],
        "blocked_transfer_requests_by_reason": sorted(blocked.items()),
        "spillback_occurrence": bool(spillback_ticks),
        "spillback_duration_ticks": len(spillback_ticks),
        "peak_link_occupancy": sorted(peak_occupancy.items()),
        "packet_travel_time_ticks": list(travel_times),
        "mean_packet_travel_time_ticks": (
            sum(travel_times) / len(travel_times) if travel_times else None
        ),
        "movement_throughput": sorted(movement_throughput.items()),
        "signal_stage_discharge": sorted(signal_stage_discharge.items()),
        "terminal_tick": engine.current_tick,
        "conservation_summary": conservation,
        "conservation_passed": engine.check_conservation(),
        "event_cache_consistency_passed": engine.check_event_cache_consistency(),
        "count_consistency_passed": engine.count_consistency_report().is_consistent,
        "canonical_event_count": len(events),
        "routing_evidence_count": len(scenario.demands),
        "signal_evidence_count": len(engine.fixed_time_signal_evidence),
        "credit_evidence_count": len(engine.fractional_service_credit_evidence),
        "allocation_trace_count": sum(len(item) for item in allocation_history),
    }


def _replay_payload(engine, allocation_history, lane_history) -> dict[str, object]:
    return {
        "events": [
            {
                "sequence_number": item.sequence_number,
                "packet_id": item.packet_id,
                "event_type": item.event_type.value,
                "entity_id": item.entity_id,
                "physical_tick": item.physical_tick,
            }
            for item in engine.event_log
        ],
        "allocations": [
            [asdict(trace) for trace in traces] for traces in allocation_history
        ],
        "lane_group_evidence": [
            [asdict(trace) for trace in traces] for traces in lane_history
        ],
        "signal_evidence": [
            asdict(item) for item in engine.fixed_time_signal_evidence
        ],
        "credit_evidence": [
            item.to_dict() for item in engine.fractional_service_credit_evidence
        ],
        "packet_outcomes": sorted(
            (packet_id, packet.lifecycle_state.value)
            for packet_id, packet in engine.packets.items()
        ),
        "terminal_tick": engine.current_tick,
        "conservation": engine.conservation_summary(),
    }


def _demand_scenario(
    scenario_id: str,
    routes: Mapping[str, tuple[str, ...]],
    *,
    copies: int,
    horizon: int,
) -> SyntheticDemandScenario:
    demands = []
    for departure in range(copies):
        for route_name, route in sorted(routes.items()):
            demands.append(
                SyntheticDemandItem(
                    demand_id=f"synthetic-demand:{scenario_id}:{departure:03d}:{route_name}",
                    route_name=route_name,
                    departure_tick=departure,
                    route_intent=route,
                )
            )
    return SyntheticDemandScenario(
        scenario_id=scenario_id,
        horizon_ticks=horizon,
        fixed_seed=0,
        demands=tuple(demands),
    )


def _principal_routes(resolved_links, topology_nodes) -> dict[str, tuple[str, ...]]:
    link_by_id = {item.link_id: item for item in resolved_links}
    outgoing: dict[str, list[str]] = defaultdict(list)
    downstream_ids = set()
    upstream_ids = set()
    for node in topology_nodes:
        for movement in node.movement_specs:
            outgoing[movement.upstream_link_id].append(movement.downstream_link_id)
            upstream_ids.add(movement.upstream_link_id)
            downstream_ids.add(movement.downstream_link_id)
    origins = sorted(set(link_by_id) - downstream_ids)
    sinks = set(link_by_id) - upstream_ids
    paths = []

    def visit(path: tuple[str, ...]) -> None:
        if path[-1] in sinks:
            paths.append(path)
            return
        for downstream in sorted(outgoing[path[-1]]):
            if downstream not in path:
                visit((*path, downstream))

    for origin in origins:
        visit((origin,))

    def way_signature(path: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(item.split(":", 2)[1] for item in path)

    required = {
        "east_to_south": ("1242275936", "32670121", "32670121", "279054333", "279054333", "279054333", "279050194", "279050194"),
        "east_to_north": ("1242275936", "32670121", "32670121", "279054333", "279054333", "279054333", "279054333", "110781522"),
        "east_via_slip_to_south": ("1242275936", "32670121", "32670121", "279054333", "96385702", "96385702", "279050194"),
        "south_link_through": ("279050194", "279050194", "279050194", "279050194", "279050194"),
        "south_to_north": ("279050194", "279050194", "279050194", "279054333", "110781522"),
        "south_to_east": ("279050194", "32670070", "477791936", "279054332", "279054332", "1242275936"),
        "north_link_through": ("279050199", "279050199", "110781522"),
    }
    by_signature = {way_signature(path): path for path in paths}
    missing = sorted(name for name, signature in required.items() if signature not in by_signature)
    if missing:
        raise BoreenmannaExperimentIntegrityError(
            f"principal synthetic routes unavailable: {missing}"
        )
    return {name: by_signature[signature] for name, signature in required.items()}
