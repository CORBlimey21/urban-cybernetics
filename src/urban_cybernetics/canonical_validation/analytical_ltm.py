"""Executable analytical LTM validation fixtures.

The fixtures in this module are deliberately small. They compare the frozen
packetised parity kernel against exact cumulative-count, queue, and travel-time
series for textbook LTM behaviours: free-flow translation, capacity saturation,
downstream receiving bottlenecks, delayed spillback, strict diverges, and
priority merges.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import DemandDeclaration, EventType, Link, Node
from urban_cybernetics.core.node import (
    PARITY_NODE_MODEL_PRIORITY_MERGE,
    PARITY_NODE_MODEL_STRICT_DIVERGE,
)
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.validation import build_spillback_validation_report


SeriesValue: TypeAlias = int | str
PASS_STATUS = "pass"
FAIL_STATUS = "fail"
REFERENCE_ID = "analytical_textbook_ltm"


@dataclass(frozen=True, slots=True)
class ReferenceSeriesComparison:
    """One exact expected-vs-observed series comparison."""

    name: str
    observed: tuple[SeriesValue, ...]
    expected: tuple[SeriesValue, ...]
    unit: str

    @property
    def is_match(self) -> bool:
        """Return whether the observed series exactly matches the reference."""

        return self.observed == self.expected


@dataclass(frozen=True, slots=True)
class CanonicalScenarioResult:
    """Pass/fail status and evidence for one canonical validation scenario."""

    reference_id: str
    scenario_id: str
    status: str
    source_ids: tuple[str, ...]
    comparisons: tuple[ReferenceSeriesComparison, ...]
    assumptions: tuple[str, ...]
    classifications: tuple[str, ...]
    notes: tuple[str, ...] = ()

    @property
    def is_pass(self) -> bool:
        """Return whether every comparison passed."""

        return self.status == PASS_STATUS


def analytical_validation_results() -> tuple[CanonicalScenarioResult, ...]:
    """Run all currently reproduced analytical/textbook LTM scenarios."""

    return (
        analytical_free_flow_shift_result(),
        analytical_capacity_saturation_result(),
        analytical_receiving_bottleneck_result(),
        analytical_delayed_spillback_result(),
        analytical_strict_diverge_result(),
        analytical_priority_merge_result(),
    )


def analytical_free_flow_shift_result() -> CanonicalScenarioResult:
    """Free-flow translation: exit curve is the entry curve delayed by tau."""

    engine = _parity_engine({"L1": _link("L1", free_flow_ticks=2, sending_capacity=3)})
    _instantiate_many(engine, 3, ("L1",))
    _run_ticks(engine, 3)

    return _result(
        "single_link_free_flow_shift",
        _assumptions("single link", "free_flow_ticks=2", "sending capacity is nonbinding"),
        (
            _compare("L1 cumulative entries", _entries(engine, "L1"), (3, 3, 3, 3)),
            _compare("L1 cumulative exits", _exits(engine, "L1"), (0, 0, 3, 3)),
            _compare("L1 storage", _storage(engine, "L1"), (3, 3, 0, 0)),
            _compare("route:L1 travel times", _travel_times(engine, "route:L1"), (2, 2, 2)),
        ),
        source_ids=("newell_1993_simplified_kinematic_waves",),
    )


def analytical_capacity_saturation_result() -> CanonicalScenarioResult:
    """Sending saturation: one eligible packet exits per tick under capacity one."""

    engine = _parity_engine({"L1": _link("L1", sending_capacity=1, storage=8)})
    _instantiate_many(engine, 4, ("L1",))
    _run_ticks(engine, 4)

    return _result(
        "single_link_sending_capacity_saturation",
        _assumptions("single link", "free_flow_ticks=1", "sending capacity=1 packet/tick"),
        (
            _compare("L1 cumulative entries", _entries(engine, "L1"), (4, 4, 4, 4, 4)),
            _compare("L1 cumulative exits", _exits(engine, "L1"), (0, 1, 2, 3, 4)),
            _compare("L1 storage", _storage(engine, "L1"), (4, 3, 2, 1, 0)),
            _compare("route:L1 travel times", _travel_times(engine, "route:L1"), (1, 2, 3, 4)),
        ),
        source_ids=(
            "newell_1993_simplified_kinematic_waves",
            "daganzo_1994_cell_transmission_model",
        ),
    )


def analytical_receiving_bottleneck_result() -> CanonicalScenarioResult:
    """Downstream receiving bottleneck: transfer and queue release are one per tick."""

    engine = _parity_engine(
        {
            "L1": _link("L1", sending_capacity=5, storage=8),
            "L2": _link("L2", sending_capacity=5, receiving_capacity=1, storage=10),
        }
    )
    _instantiate_many(engine, 4, ("L1", "L2"))
    _run_ticks(engine, 6)

    return _result(
        "two_link_receiving_bottleneck",
        _assumptions("two-link chain", "downstream receiving capacity=1 packet/tick"),
        (
            _compare("L1 cumulative exits", _exits(engine, "L1"), (0, 1, 2, 3, 4, 4, 4)),
            _compare("L2 cumulative entries", _entries(engine, "L2"), (0, 1, 2, 3, 4, 4, 4)),
            _compare(
                "boundary:L1->L2 queue length",
                _queue_lengths(engine, "boundary:L1->L2"),
                (0, 3, 2, 1, 0, 0, 0),
            ),
            _compare(
                "route:L1->L2 travel times",
                _travel_times(engine, "route:L1->L2"),
                (2, 3, 4, 5),
            ),
        ),
        source_ids=(
            "newell_1993_freeway_bottlenecks",
            "daganzo_1995_cell_transmission_networks",
        ),
    )


def analytical_delayed_spillback_result() -> CanonicalScenarioResult:
    """Storage spillback: downstream vacancy returns only after backward-wave lag."""

    engine = _parity_engine(
        {
            "L1": _link("L1", sending_capacity=4, storage=4),
            "L2": _link("L2", receiving_capacity=4, storage=1),
        }
    )
    engine.instantiate(DemandDeclaration("D-blocker", 0, ("L2",)))
    engine.instantiate(DemandDeclaration("D-upstream", 0, ("L1", "L2")))
    _run_ticks(engine, 3)

    return _result(
        "two_link_delayed_vacancy_spillback",
        _assumptions(
            "two-link chain",
            "downstream storage=1 packet",
            "backward-wave vacancy lag delays upstream release",
        ),
        (
            _compare("L1 cumulative exits", _exits(engine, "L1"), (0, 0, 0, 1)),
            _compare("L2 cumulative entries", _entries(engine, "L2"), (1, 1, 1, 2)),
            _compare("L2 cumulative exits", _exits(engine, "L2"), (0, 1, 1, 1)),
            _compare(
                "boundary:L1->L2 queue length",
                _queue_lengths(engine, "boundary:L1->L2"),
                (0, 1, 1, 0),
            ),
            _compare("route:L1->L2 completed travel times", _travel_times(engine, "route:L1->L2"), ()),
        ),
        source_ids=(
            "newell_1993_freeway_bottlenecks",
            "daganzo_1995_cell_transmission_networks",
        ),
        classifications=("pass", "spillback", "discretisation artefact: one-tick event boundary convention"),
    )


def analytical_strict_diverge_result() -> CanonicalScenarioResult:
    """Strict FIFO diverge: blocked head prevents tail bypass to an open branch."""

    engine = _parity_engine(
        {
            "L1": _link("L1", sending_capacity=2, storage=8),
            "L2": _link("L2", receiving_capacity=1, storage=4),
            "L3": _link("L3", receiving_capacity=1, storage=4),
        },
        nodes=(
            Node(
                "N-diverge",
                incoming_link_ids=("L1",),
                outgoing_link_ids=("L2", "L3"),
                node_model=PARITY_NODE_MODEL_STRICT_DIVERGE,
            ),
        ),
    )
    engine.set_receiving_open("L2", False)
    engine.instantiate(DemandDeclaration("D-head", 0, ("L1", "L2")))
    engine.instantiate(DemandDeclaration("D-tail", 0, ("L1", "L3")))
    engine.step()
    engine.set_receiving_open("L2", True)
    _run_ticks(engine, 2)

    return _result(
        "strict_fifo_diverge_blocked_head",
        _assumptions("strict diverge", "head route branch initially closed"),
        (
            _compare("L1 cumulative exits", _exits(engine, "L1"), (0, 0, 1, 2)),
            _compare("L2 cumulative entries", _entries(engine, "L2"), (0, 0, 1, 1)),
            _compare("L3 cumulative entries", _entries(engine, "L3"), (0, 0, 0, 1)),
            _compare(
                "boundary:L1->L2 queue length",
                _queue_lengths(engine, "boundary:L1->L2"),
                (0, 1, 0, 0),
            ),
            _compare("route:L1->L2 travel times", _travel_times(engine, "route:L1->L2"), (3,)),
        ),
        source_ids=("tampere_2011_generic_node_models",),
        classifications=("pass", "diverge", "modelling choice: strict upstream FIFO"),
    )


def analytical_priority_merge_result() -> CanonicalScenarioResult:
    """Priority merge: declared 2:1 long-horizon share with unused-share release."""

    engine = _parity_engine(
        {
            "L1": _link("L1", sending_capacity=1, storage=12),
            "L2": _link("L2", sending_capacity=1, storage=12),
            "L3": _link("L3", receiving_capacity=1, storage=12),
        },
        nodes=(
            Node(
                "N-merge",
                incoming_link_ids=("L1", "L2"),
                outgoing_link_ids=("L3",),
                node_model=PARITY_NODE_MODEL_PRIORITY_MERGE,
                merge_priorities=(("L1", 2), ("L2", 1)),
            ),
        ),
    )
    for index in range(4):
        engine.instantiate(DemandDeclaration(f"D-L1-{index}", 0, ("L1", "L3")))
    for index in range(2):
        engine.instantiate(DemandDeclaration(f"D-L2-{index}", 0, ("L2", "L3")))
    _run_ticks(engine, 6)

    return _result(
        "priority_merge_declared_share",
        _assumptions("two-to-one merge", "declared priority L1:L2 = 2:1"),
        (
            _compare("L3 cumulative entries", _entries(engine, "L3"), (0, 1, 2, 3, 4, 5, 6)),
            _compare("L3 entry source sequence", _l3_entry_sources(engine), ("L1", "L2", "L1", "L1", "L2", "L1")),
            _compare("route:L1->L3 travel times", _travel_times(engine, "route:L1->L3"), (2, 4, 5)),
            _compare("route:L2->L3 travel times", _travel_times(engine, "route:L2->L3"), (3, 6)),
        ),
        source_ids=("tampere_2011_generic_node_models",),
        classifications=("pass", "merge", "modelling choice: bounded deficit priority merge"),
    )


def render_series_comparison_svg(comparison: ReferenceSeriesComparison) -> str:
    """Render a compact SVG overlay for a numeric expected/observed comparison."""

    if not comparison.expected or any(
        not isinstance(value, int) for value in comparison.expected + comparison.observed
    ):
        raise ValueError("SVG rendering requires non-empty integer series")
    width = 520
    height = 180
    pad = 24
    max_value = max(comparison.expected + comparison.observed)
    x_count = max(len(comparison.expected), len(comparison.observed)) - 1

    def points(series: tuple[SeriesValue, ...]) -> str:
        coords = []
        for index, raw_value in enumerate(series):
            value = int(raw_value)
            x = pad + (width - 2 * pad) * index / max(x_count, 1)
            y = height - pad - (height - 2 * pad) * value / max(max_value, 1)
            coords.append(f"{x:.1f},{y:.1f}")
        return " ".join(coords)

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" fill="#fff"/>'
        f'<text x="{pad}" y="18" font-size="13" font-family="monospace">'
        f"{comparison.name}</text>"
        f'<polyline points="{points(comparison.expected)}" fill="none" '
        'stroke="#1f77b4" stroke-width="3"/>'
        f'<polyline points="{points(comparison.observed)}" fill="none" '
        'stroke="#d62728" stroke-width="2" stroke-dasharray="5 4"/>'
        f'<text x="{pad}" y="{height - 6}" font-size="11" font-family="monospace">'
        "blue=expected red=observed</text>"
        "</svg>"
    )


def _result(
    scenario_id: str,
    assumptions: tuple[str, ...],
    comparisons: tuple[ReferenceSeriesComparison, ...],
    *,
    source_ids: tuple[str, ...],
    classifications: tuple[str, ...] = ("pass",),
    notes: tuple[str, ...] = (),
) -> CanonicalScenarioResult:
    status = PASS_STATUS if all(comparison.is_match for comparison in comparisons) else FAIL_STATUS
    return CanonicalScenarioResult(
        reference_id=REFERENCE_ID,
        scenario_id=scenario_id,
        status=status,
        source_ids=source_ids,
        comparisons=comparisons,
        assumptions=assumptions,
        classifications=classifications if status == PASS_STATUS else ("unresolved discrepancy",),
        notes=notes,
    )


def _parity_engine(
    links: dict[str, Link],
    nodes: tuple[Node, ...] = (),
) -> LoadingEngine:
    return LoadingEngine(
        links=links,
        nodes=nodes,
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
    )


def _link(
    link_id: str,
    *,
    free_flow_ticks: int = 1,
    sending_capacity: int = 4,
    receiving_capacity: int = 4,
    storage: int = 8,
) -> Link:
    return Link(
        link_id=link_id,
        free_flow_ticks=free_flow_ticks,
        declared_sending_capacity_per_tick=sending_capacity,
        declared_receiving_capacity_per_tick=receiving_capacity,
        declared_storage_capacity_packets=storage,
        length_m=10.0,
        lane_count=1,
        free_flow_speed_mps=10.0,
        jam_density_veh_per_km_per_lane=100.0,
        backward_wave_speed_mps=5.0,
        capacity_veh_per_hour_per_lane=1200.0,
        tick_duration_seconds=1.0,
    )


def _instantiate_many(
    engine: LoadingEngine,
    packet_count: int,
    route_intent: tuple[str, ...],
) -> None:
    for index in range(packet_count):
        engine.instantiate(DemandDeclaration(f"D{index}", 0, route_intent))


def _run_ticks(engine: LoadingEngine, ticks: int) -> None:
    for _ in range(ticks):
        engine.step()


def _compare(
    name: str,
    observed: tuple[SeriesValue, ...],
    expected: tuple[SeriesValue, ...],
    unit: str = "packets",
) -> ReferenceSeriesComparison:
    return ReferenceSeriesComparison(
        name=name,
        observed=observed,
        expected=expected,
        unit=unit,
    )


def _assumptions(*items: str) -> tuple[str, ...]:
    return (
        "integer time ticks",
        "unit packets",
        "inclusive cumulative-count convention",
        *items,
    )


def _entries(engine: LoadingEngine, link_id: str) -> tuple[int, ...]:
    return tuple(
        engine.cumulative_counts(link_id, tick).entries
        for tick in range(engine.current_tick + 1)
    )


def _exits(engine: LoadingEngine, link_id: str) -> tuple[int, ...]:
    return tuple(
        engine.cumulative_counts(link_id, tick).exits
        for tick in range(engine.current_tick + 1)
    )


def _storage(engine: LoadingEngine, link_id: str) -> tuple[int, ...]:
    return tuple(
        engine.link_storage(link_id, tick).storage
        for tick in range(engine.current_tick + 1)
    )


def _queue_lengths(engine: LoadingEngine, boundary_id: str) -> tuple[int, ...]:
    report = build_spillback_validation_report(engine, boundary_ids=(boundary_id,))
    return tuple(point.queue_length for point in report.boundary_traces[0].queue_curve)


def _travel_times(engine: LoadingEngine, route_key: str) -> tuple[int, ...]:
    curves = {curve.route_key: curve for curve in engine.route_travel_time_curves()}
    curve = curves.get(route_key)
    if curve is None:
        return ()
    return tuple(point.travel_time_ticks for point in curve.points)


def _l3_entry_sources(engine: LoadingEngine) -> tuple[str, ...]:
    return tuple(
        engine.packets[event.packet_id].route_intent[0]
        for event in engine.event_log
        if event.event_type == EventType.LINK_ENTRY and event.entity_id == "L3"
    )
