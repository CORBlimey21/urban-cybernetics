# SPDX-License-Identifier: MPL-2.0
from collections import Counter

import pytest

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import DemandDeclaration, Link, Node
from urban_cybernetics.demand.cork_synthetic import (
    CorkSyntheticDemand,
    EvenlySpacedGlobalDepartureSchedule,
    build_cork_synthetic_demand,
    resolve_cork_weighted_routes,
)
from urban_cybernetics.demand.manifest import DemandManifest, ODDemandDeclaration
from urban_cybernetics.extensions.city_scale_v2 import (
    CityScaleSummaryMovementAllocator,
    CityScaleV2LoadingEngine,
)
from urban_cybernetics.extensions.gate_aware_fractional_service import (
    GateAwareFractionalServiceConfig,
    GateAwareFractionalServiceLoadingEngine,
)
from urban_cybernetics.topology.cork import (
    CORK_EXPECTED_EDGE_COUNT,
    CORK_EXPECTED_NODE_COUNT,
    CORK_GRAPH_SHA256,
    CORK_TICK_DURATION_SECONDS,
    load_cork_canonical_network,
    resolve_cork_graph_path,
)


requires_cork_graphml = pytest.mark.skipif(
    not resolve_cork_graph_path().is_file(),
    reason=(
        "external Cork GraphML is not installed; run "
        "scripts/install_external_data.py --cork-graphml PATH"
    ),
)


@requires_cork_graphml
def test_cork_adapter_preserves_identity_parallel_edges_and_provenance() -> None:
    first = load_cork_canonical_network()
    second = load_cork_canonical_network()
    assert first.topology_hash == second.topology_hash
    assert first.physical_profile_hash == second.physical_profile_hash
    assert first.source_provenance_hash == second.source_provenance_hash
    assert first.topology.source_metadata.source_file_sha256 == CORK_GRAPH_SHA256
    assert len(first.topology.nodes) == CORK_EXPECTED_NODE_COUNT
    assert len(first.topology.links) == CORK_EXPECTED_EDGE_COUNT
    assert {node.source_node_id for node in first.topology.nodes} == {
        node.source_node_id for node in first.source_nodes
    }
    pair_counts = Counter((edge.source_u, edge.source_v) for edge in first.source_edges)
    parallel_pairs = {pair for pair, count in pair_counts.items() if count > 1}
    assert parallel_pairs
    for pair in parallel_pairs:
        retained = [
            edge for edge in first.source_edges if (edge.source_u, edge.source_v) == pair
        ]
        assert len({edge.canonical_link_id for edge in retained}) == len(retained)
        assert len({edge.source_key for edge in retained}) == len(retained)
    assert all(dict(edge.source_metadata_items).get("osmid") for edge in first.source_edges)
    assert any(edge.geometry_sha256 for edge in first.source_edges)


@requires_cork_graphml
def test_cork_physical_profile_is_strictly_eligible_at_frozen_timestep() -> None:
    network = load_cork_canonical_network()
    assert all(
        link.tick_duration_seconds == CORK_TICK_DURATION_SECONDS
        and link.resolved_physical_parameters().parity_eligible
        for link in network.as_loading_links().values()
    )
    assert min(
        item.free_flow_travel_time_seconds for item in network.physical_links
    ) >= CORK_TICK_DURATION_SECONDS


@requires_cork_graphml
def test_cork_synthetic_demand_and_weighted_routes_are_deterministic() -> None:
    network = load_cork_canonical_network()
    first = build_cork_synthetic_demand(network, packet_count=20)
    second = build_cork_synthetic_demand(network, packet_count=20)
    assert first.manifest.manifest_hash == second.manifest.manifest_hash
    assert first.unique_od_count == 20
    assert all(
        item.origin_node_id != item.destination_node_id
        for item in first.manifest.declarations
    )
    first_routes = resolve_cork_weighted_routes(network, first)
    second_routes = resolve_cork_weighted_routes(network, second)
    assert first_routes.route_resolution_hash == second_routes.route_resolution_hash
    assert first_routes.resolved_manifest == second_routes.resolved_manifest
    assert min(first_routes.route_link_counts) > 1


@requires_cork_graphml
def test_cork_weighted_routing_selects_fastest_parallel_edge() -> None:
    network = load_cork_canonical_network()
    declaration = ODDemandDeclaration(
        "parallel-edge-probe",
        "osm-node:441871",
        "osm-node:348513134",
        1,
        EvenlySpacedGlobalDepartureSchedule(0, 0),
    )
    manifest = DemandManifest(
        "parallel-edge-probe",
        network.topology.topology_id,
        network.topology_hash,
        (declaration,),
    )
    demand = CorkSyntheticDemand(
        manifest=manifest,
        seed=1,
        requested_packet_count=1,
        unique_od_count=1,
        loading_window_seconds=0.04,
        loading_window_start_tick=0,
        loading_window_end_tick=0,
        minimum_straight_line_distance_m=0.0,
    )
    route = resolve_cork_weighted_routes(
        network, demand
    ).resolved_manifest.resolved_routes[0].route
    assert route.ordered_link_ids == (
        "osm-link:u=441871:v=348513134:key=1",
    )


def test_sparse_city_v2_matches_stock_v2_canonical_events() -> None:
    links = {
        link_id: Link(
            link_id,
            length_m=10.0,
            lane_count=1,
            free_flow_speed_mps=10.0,
            jam_density_veh_per_km_per_lane=180.0,
            backward_wave_speed_mps=5.0,
            capacity_veh_per_hour_per_lane=3_600.0,
            tick_duration_seconds=1.0,
        )
        for link_id in ("L1", "L2")
    }
    nodes = (Node("N", incoming_link_ids=("L1",), outgoing_link_ids=("L2",)),)
    config = GateAwareFractionalServiceConfig((("L1", 1.0), ("L2", 1.0)))
    common = {
        "links": links,
        "nodes": nodes,
        "model_profile_id": ACADEMIC_LTM_PARITY_PROFILE_ID,
        "gate_aware_fractional_service_config": config,
        "use_active_work_frontier": True,
    }
    stock = GateAwareFractionalServiceLoadingEngine(**common)
    sparse = CityScaleV2LoadingEngine(
        **common,
        node_transfer_policy=CityScaleSummaryMovementAllocator(nodes),
    )
    for engine in (stock, sparse):
        for index in range(5):
            engine.instantiate(DemandDeclaration(f"D{index}", 0, ("L1", "L2")))
        for _ in range(15):
            engine.step()
    sparse.materialize_all_receiving_credit()
    assert sparse.event_log == stock.event_log
    assert dict(sparse.packets) == dict(stock.packets)
    assert (
        sparse._parity_sending_capacity_carry_by_link_id
        == stock._parity_sending_capacity_carry_by_link_id
    )
    assert (
        sparse._parity_receiving_capacity_carry_by_link_id
        == stock._parity_receiving_capacity_carry_by_link_id
    )


@requires_cork_graphml
def test_cork_lower_rungs_share_seeded_od_family_prefix() -> None:
    network = load_cork_canonical_network()
    demand_100 = build_cork_synthetic_demand(network, packet_count=100)
    demand_1000 = build_cork_synthetic_demand(network, packet_count=1_000)
    demand_2500 = build_cork_synthetic_demand(network, packet_count=2_500)
    pairs_100 = tuple(
        (item.origin_node_id, item.destination_node_id)
        for item in demand_100.manifest.declarations
    )
    pairs_1000 = tuple(
        (item.origin_node_id, item.destination_node_id)
        for item in demand_1000.manifest.declarations
    )
    pairs_2500 = tuple(
        (item.origin_node_id, item.destination_node_id)
        for item in demand_2500.manifest.declarations
    )
    assert pairs_100 == pairs_1000[:100]
    assert pairs_1000 == pairs_2500
