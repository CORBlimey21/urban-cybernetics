"""M7 packet and multi-commodity parity validation artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import EventType, Packet
from urban_cybernetics.loading.cumulative_counts import (
    CumulativeCountProjection,
    RouteTravelTimeCurve,
    route_key_for_packet,
)


COMMODITY_MODEL_ID = "immutable_route_intent_unit_packet_v1"


@dataclass(frozen=True, slots=True)
class CommodityDefinition:
    """Current UC commodity: a unit-packet route-intent class."""

    commodity_key: str
    route_link_ids: tuple[str, ...]
    packet_count: int
    completed_packet_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_link_ids", tuple(self.route_link_ids))


@dataclass(frozen=True, slots=True)
class CommodityParityValidationReport:
    """Read-only M7 validation report for unit-packet route commodities."""

    model_profile_id: str
    commodity_model_id: str
    unit_packet_weight: int
    commodity_definitions: tuple[CommodityDefinition, ...]
    route_travel_time_curves: tuple[RouteTravelTimeCurve, ...]
    checked_packet_count: int
    completed_packet_count: int
    invariant_violations: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "commodity_definitions",
            tuple(self.commodity_definitions),
        )
        object.__setattr__(
            self,
            "route_travel_time_curves",
            tuple(self.route_travel_time_curves),
        )
        object.__setattr__(
            self,
            "invariant_violations",
            tuple(self.invariant_violations),
        )

    @property
    def is_valid(self) -> bool:
        """Return whether the run is valid M7 parity evidence."""

        return not self.invariant_violations


def build_commodity_parity_validation_report(
    engine: Any,
) -> CommodityParityValidationReport:
    """Validate M7 packet and multi-commodity parity evidence without mutation."""

    packets = dict(engine.packets)
    projection = engine.cumulative_count_projection()
    reasons: list[str] = []
    if engine.model_profile_id != ACADEMIC_LTM_PARITY_PROFILE_ID:
        reasons.append("model_profile_not_parity_ltm_v1")

    _check_unit_packet_weights(packets, reasons)
    _check_count_projection(engine, projection, reasons)
    _check_packet_route_ordinal_correspondence(packets, projection, reasons)
    _check_realised_paths_do_not_imply_rerouting(engine, packets, reasons)
    _check_route_travel_time_curves(projection, reasons)

    completed_packet_ids = {
        event.packet_id
        for event in engine.event_log
        if event.event_type == EventType.COMPLETED
    }
    return CommodityParityValidationReport(
        model_profile_id=engine.model_profile_id,
        commodity_model_id=COMMODITY_MODEL_ID,
        unit_packet_weight=1,
        commodity_definitions=_commodity_definitions(packets, completed_packet_ids),
        route_travel_time_curves=projection.route_travel_time_curves,
        checked_packet_count=len(packets),
        completed_packet_count=len(completed_packet_ids),
        invariant_violations=tuple(reasons),
    )


def _check_unit_packet_weights(
    packets: dict[str, Packet],
    reasons: list[str],
) -> None:
    weights_by_packet_id = {
        packet_id: getattr(packet, "packet_unit_weight", 1)
        for packet_id, packet in packets.items()
    }
    weights = set(weights_by_packet_id.values())
    if len(weights) > 1:
        reasons.append("mixed_packet_granularity_not_parity_evidence")
    for packet_id, weight in sorted(weights_by_packet_id.items()):
        if weight != 1:
            reasons.append(f"{packet_id}:weighted_packet_not_parity_evidence")


def _check_count_projection(
    engine: Any,
    projection: CumulativeCountProjection,
    reasons: list[str],
) -> None:
    report = engine.count_consistency_report()
    if not report.is_consistent:
        reasons.extend(
            f"count_consistency:{reason}" for reason in report.ineligibility_reasons
        )
    if not projection.route_counts_supported:
        reasons.append("route_disaggregated_counts_not_supported")


def _check_packet_route_ordinal_correspondence(
    packets: dict[str, Packet],
    projection: CumulativeCountProjection,
    reasons: list[str],
) -> None:
    seen_packet_boundaries: set[tuple[str, str, str]] = set()
    max_route_ordinal_by_boundary: dict[tuple[str, str, str], int] = {}
    for ordinal in projection.packet_ordinals:
        packet = packets.get(ordinal.packet_id)
        if packet is None:
            reasons.append(f"{ordinal.packet_id}:ordinal_missing_packet_metadata")
            continue
        expected_route_key = route_key_for_packet(packet)
        if ordinal.route_key != expected_route_key:
            reasons.append(f"{ordinal.packet_id}:ordinal_route_key_mismatch")
        if ordinal.route_link_ids != packet.route_intent:
            reasons.append(f"{ordinal.packet_id}:ordinal_route_links_mismatch")
        if ordinal.route_ordinal is None:
            reasons.append(f"{ordinal.packet_id}:ordinal_missing_route_ordinal")
            continue
        packet_boundary = (
            ordinal.packet_id,
            ordinal.boundary_type,
            ordinal.link_id,
        )
        if packet_boundary in seen_packet_boundaries:
            reasons.append(f"{ordinal.packet_id}:duplicate_packet_boundary_ordinal")
        seen_packet_boundaries.add(packet_boundary)

        route_boundary = (
            ordinal.link_id,
            ordinal.boundary_type,
            ordinal.route_key or "",
        )
        max_route_ordinal_by_boundary[route_boundary] = max(
            max_route_ordinal_by_boundary.get(route_boundary, 0),
            ordinal.route_ordinal,
        )

    final_counts_by_route_boundary = {}
    for counts in projection.route_counts:
        if counts.tick != projection.max_tick:
            continue
        final_counts_by_route_boundary[(counts.link_id, "entry", counts.route_key)] = (
            counts.entries
        )
        final_counts_by_route_boundary[(counts.link_id, "exit", counts.route_key)] = (
            counts.exits
        )
    for route_boundary, max_ordinal in max_route_ordinal_by_boundary.items():
        if final_counts_by_route_boundary.get(route_boundary, 0) != max_ordinal:
            link_id, boundary_type, route_key = route_boundary
            reasons.append(
                f"{link_id}:{boundary_type}:{route_key}:route_ordinal_count_mismatch"
            )


def _check_realised_paths_do_not_imply_rerouting(
    engine: Any,
    packets: dict[str, Packet],
    reasons: list[str],
) -> None:
    entries_by_packet: dict[str, list[str]] = {packet_id: [] for packet_id in packets}
    for event in engine.event_log:
        if event.event_type == EventType.LINK_ENTRY:
            entries_by_packet.setdefault(event.packet_id, []).append(event.entity_id)
    for packet_id, realised_path in sorted(entries_by_packet.items()):
        packet = packets.get(packet_id)
        if packet is None:
            continue
        route_prefix = packet.route_intent[: len(realised_path)]
        if tuple(realised_path) != route_prefix:
            reasons.append(f"{packet_id}:rerouting_not_supported_by_m7")


def _check_route_travel_time_curves(
    projection: CumulativeCountProjection,
    reasons: list[str],
) -> None:
    final_exit_ordinal_by_packet_id = {
        ordinal.packet_id: ordinal.route_ordinal
        for ordinal in projection.packet_ordinals
        if ordinal.boundary_type == "exit"
        and ordinal.route_link_ids
        and ordinal.link_id == ordinal.route_link_ids[-1]
    }
    seen_curve_packets: set[str] = set()
    for curve in projection.route_travel_time_curves:
        previous_completion: tuple[int, int] | None = None
        for point in curve.points:
            if point.packet_id in seen_curve_packets:
                reasons.append(f"{point.packet_id}:duplicate_route_travel_time_point")
            seen_curve_packets.add(point.packet_id)
            if point.route_key != curve.route_key:
                reasons.append(f"{point.packet_id}:travel_time_route_key_mismatch")
            if point.route_link_ids != curve.route_link_ids:
                reasons.append(f"{point.packet_id}:travel_time_route_links_mismatch")
            if point.travel_time_ticks != point.completion_tick - point.departure_tick:
                reasons.append(f"{point.packet_id}:travel_time_tick_mismatch")
            if (
                final_exit_ordinal_by_packet_id.get(point.packet_id)
                != point.final_link_exit_route_ordinal
            ):
                reasons.append(f"{point.packet_id}:travel_time_final_ordinal_mismatch")
            completion_key = (
                point.completion_tick,
                point.completion_sequence_number,
            )
            if previous_completion is not None and completion_key < previous_completion:
                reasons.append(f"{curve.route_key}:travel_time_curve_not_ordered")
            previous_completion = completion_key


def _commodity_definitions(
    packets: dict[str, Packet],
    completed_packet_ids: set[str],
) -> tuple[CommodityDefinition, ...]:
    packet_ids_by_route: dict[str, list[str]] = {}
    route_link_ids_by_route: dict[str, tuple[str, ...]] = {}
    for packet_id, packet in packets.items():
        route_key = route_key_for_packet(packet)
        packet_ids_by_route.setdefault(route_key, []).append(packet_id)
        route_link_ids_by_route.setdefault(route_key, packet.route_intent)

    return tuple(
        CommodityDefinition(
            commodity_key=route_key,
            route_link_ids=route_link_ids_by_route[route_key],
            packet_count=len(packet_ids_by_route[route_key]),
            completed_packet_count=sum(
                packet_id in completed_packet_ids
                for packet_id in packet_ids_by_route[route_key]
            ),
        )
        for route_key in sorted(packet_ids_by_route)
    )
