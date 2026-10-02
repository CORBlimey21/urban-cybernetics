# SPDX-License-Identifier: MPL-2.0
"""Minimal deterministic composed loading-kernel validation case."""

from __future__ import annotations

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import (
    DemandDeclaration,
    JunctionSpec,
    Link,
    MovementSpec,
    Node,
)
from urban_cybernetics.loading import LoadingEngine


COMPOSITION_CASE_ID = "M8-COMP-NET-01"
COMPOSITION_CASE_VERSION = "1"
COMPOSITION_FINAL_TICK = 10
COMPOSITION_LINK_IDS = ("L1", "L2", "L3", "L4")
COMPOSITION_BOUNDARIES = (("L1", "L3"), ("L2", "L3"), ("L3", "L4"))
COMPOSITION_ROUTES = (("L1", "L3", "L4"), ("L2", "L3", "L4"))


def build_composition_validation_engine() -> LoadingEngine:
    """Instantiate the fixed two-origin merge and downstream bottleneck case."""

    links = {
        "L1": _physical_link("L1", jam_density=600.0),
        "L2": _physical_link("L2", jam_density=600.0),
        "L3": _physical_link("L3", jam_density=400.0),
        "L4": _physical_link("L4", jam_density=200.0),
    }
    nodes = (
        Node(
            node_id="N-MERGE",
            incoming_link_ids=("L1", "L2"),
            outgoing_link_ids=("L3",),
            junction_spec=JunctionSpec(
                node_id="N-MERGE",
                incoming_link_ids=("L1", "L2"),
                outgoing_link_ids=("L3",),
                movement_specs=(
                    MovementSpec("L1", "L3", priority_weight=1),
                    MovementSpec("L2", "L3", priority_weight=1),
                ),
                provenance=(("case_id", COMPOSITION_CASE_ID),),
            ),
        ),
        Node(
            node_id="N-BOTTLENECK",
            incoming_link_ids=("L3",),
            outgoing_link_ids=("L4",),
            junction_spec=JunctionSpec(
                node_id="N-BOTTLENECK",
                incoming_link_ids=("L3",),
                outgoing_link_ids=("L4",),
                movement_specs=(MovementSpec("L3", "L4"),),
                provenance=(("case_id", COMPOSITION_CASE_ID),),
            ),
        ),
    )
    engine = LoadingEngine(
        links=links,
        nodes=nodes,
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
    )
    for route_index, route in enumerate(COMPOSITION_ROUTES, start=1):
        for packet_index in range(4):
            engine.instantiate(
                DemandDeclaration(
                    demand_id=f"OD{route_index}-{packet_index + 1}",
                    departure_tick=0,
                    route_intent=route,
                )
            )
    return engine


def run_composition_validation_case() -> LoadingEngine:
    """Run the fixed case through its declared complete-clearance horizon."""

    engine = build_composition_validation_engine()
    while engine.current_tick < COMPOSITION_FINAL_TICK:
        engine.step()
    return engine


def _physical_link(link_id: str, *, jam_density: float) -> Link:
    """Return one FD-consistent 10 m link with an integer per-tick capacity."""

    capacity_per_hour = 18.0 * jam_density
    capacity_per_tick = int(capacity_per_hour / 3600.0)
    return Link(
        link_id=link_id,
        length_m=10.0,
        lane_count=1,
        free_flow_speed_mps=10.0,
        backward_wave_speed_mps=10.0,
        jam_density_veh_per_km_per_lane=jam_density,
        capacity_veh_per_hour_per_lane=capacity_per_hour,
        tick_duration_seconds=1.0,
        declared_sending_capacity_per_tick=capacity_per_tick,
        declared_receiving_capacity_per_tick=capacity_per_tick,
    )
