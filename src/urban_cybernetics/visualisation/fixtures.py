"""Rerunnable small deterministic V1 acceptance fixtures."""

from __future__ import annotations

import hashlib
from pathlib import Path

from urban_cybernetics.config import LEGACY_LOADING_PROFILE_ID
from urban_cybernetics.core import DemandDeclaration, LifecycleState, Link
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.topology import (
    CanonicalNode,
    CanonicalTopology,
    CanonicalTopologyLink,
    TopologySourceMetadata,
)
from urban_cybernetics.validation import ValidationContext

from .contract import RunStatus, VRunBundle
from .export import build_run_bundle, write_run_bundle


SYNTHETIC_RUN_ID = "v1:synthetic-strict-fifo-diverge"


def build_synthetic_fixture() -> VRunBundle:
    """Execute a sanctioned kernel run and detach its replay evidence."""

    topology = build_synthetic_topology()
    links = {
        link.link_id: Link(
            link_id=link.link_id,
            free_flow_ticks=1,
            declared_sending_capacity_per_tick=1,
            declared_receiving_capacity_per_tick=1,
            declared_storage_capacity_packets=8,
            tick_duration_seconds=1.0,
        )
        for link in topology.links
    }
    engine = LoadingEngine(
        links=links,
        nodes=topology.as_loading_nodes(),
        model_profile_id=LEGACY_LOADING_PROFILE_ID,
    )
    engine.set_receiving_open("L1", False)
    engine.instantiate(
        DemandDeclaration("D-north", departure_tick=0, route_intent=("L0", "L1", "L3"))
    )
    engine.instantiate(
        DemandDeclaration("D-south", departure_tick=0, route_intent=("L0", "L2", "L4"))
    )
    engine.instantiate(
        DemandDeclaration("D-follow", departure_tick=1, route_intent=("L0", "L1", "L3"))
    )
    engine.step()
    engine.step()
    engine.set_receiving_open("L1", True)
    for _ in range(24):
        if all(
            packet.lifecycle_state == LifecycleState.COMPLETED
            for packet in engine.packets.values()
        ):
            break
        engine.step()
    else:
        raise RuntimeError("synthetic V1 fixture failed to complete")
    if not engine.check_event_cache_consistency() or not engine.check_conservation():
        raise RuntimeError("synthetic V1 fixture failed engine integrity checks")

    config = {
        "model_kernel_profile_id": engine.model_profile_id,
        "tick_duration_seconds": 1.0,
        "fixture": "strict FIFO diverge with a temporarily closed receiving link",
        "receiving_gate_schedule": {"L1": {"closed_ticks": [0, 1, 2], "opened_before_tick": 3}},
        "declared_packet_capacity_basis": "one unit packet per tick",
    }
    context = ValidationContext.from_engine(
        engine,
        nodes=topology.as_loading_nodes(),
        run_config=config,
    )
    return build_run_bundle(
        run_id=SYNTHETIC_RUN_ID,
        scenario_name="Strict-FIFO diverge inspection fixture",
        topology=topology,
        context=context,
        status=RunStatus.COMPLETE,
        status_reason="All instantiated packets reached canonical COMPLETED events.",
        tick_duration_seconds=1.0,
        config_snapshot=config,
        configuration_id="v1.synthetic.strict_fifo_diverge.config.v1",
        validation_status="passed",
        validation_notes=(
            "Engine event/materialised-state cache consistency passed.",
            "Packet conservation passed.",
            "Python cumulative-count consistency passed.",
            "This legacy-compatible fixture demonstrates viewer integrity, not parity calibration.",
        ),
        input_artifact_ids=(topology.topology_id,),
        node_positions={
            "N0": (0.08, 0.5),
            "N1": (0.31, 0.5),
            "N2": (0.57, 0.23),
            "N3": (0.57, 0.77),
            "N4": (0.9, 0.5),
        },
    )


def write_synthetic_fixture(path: Path) -> VRunBundle:
    bundle = build_synthetic_fixture()
    write_run_bundle(bundle, path)
    return bundle


def build_synthetic_topology() -> CanonicalTopology:
    source_payload = b"uc-v1-strict-fifo-diverge-topology-v1"
    return CanonicalTopology(
        topology_id="topology:v1:strict-fifo-diverge",
        nodes=(
            CanonicalNode("N0", "synthetic:origin", outgoing_link_ids=("L0",)),
            CanonicalNode(
                "N1",
                "synthetic:diverge",
                incoming_link_ids=("L0",),
                outgoing_link_ids=("L1", "L2"),
            ),
            CanonicalNode(
                "N2",
                "synthetic:north",
                incoming_link_ids=("L1",),
                outgoing_link_ids=("L3",),
            ),
            CanonicalNode(
                "N3",
                "synthetic:south",
                incoming_link_ids=("L2",),
                outgoing_link_ids=("L4",),
            ),
            CanonicalNode(
                "N4",
                "synthetic:destination",
                incoming_link_ids=("L3", "L4"),
            ),
        ),
        links=tuple(
            CanonicalTopologyLink(
                link_id=link_id,
                tail_node_id=tail,
                head_node_id=head,
                source_link_id=f"synthetic:{link_id}",
                source_tail_node_id=f"synthetic:{tail}",
                source_head_node_id=f"synthetic:{head}",
                length_m=10.0,
                lane_count=1,
                free_flow_speed_mps=10.0,
                capacity_veh_per_hour_per_lane=1200.0,
                jam_density_veh_per_km_per_lane=100.0,
                backward_wave_speed_mps=5.0,
            )
            for link_id, tail, head in (
                ("L0", "N0", "N1"),
                ("L1", "N1", "N2"),
                ("L2", "N1", "N3"),
                ("L3", "N2", "N4"),
                ("L4", "N3", "N4"),
            )
        ),
        source_metadata=TopologySourceMetadata(
            source_name="UC V1 deterministic synthetic fixture",
            source_format="declared_in_python",
            source_file_path="src/urban_cybernetics/visualisation/fixtures.py",
            source_file_sha256=hashlib.sha256(source_payload).hexdigest(),
            source_metadata_items=(("layout", "non_geographic_declared_diagram"),),
        ),
        interpretation_assumptions=(
            "Diagram coordinates are presentation-only and non-geographic.",
            "One packet is one conserved loading unit.",
            "Static physical metadata is illustrative fixture metadata, not empirical calibration.",
        ),
    )
