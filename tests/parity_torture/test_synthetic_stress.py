# SPDX-License-Identifier: MPL-2.0
"""Small synthetic stress tests for impossible-state discovery."""

from __future__ import annotations

import pytest

from urban_cybernetics.core import LifecycleState

from .helpers import random_stress_scenario, run_scenario


@pytest.mark.parametrize("seed", range(90, 140))
def test_small_random_networks_do_not_create_impossible_states(seed: int) -> None:
    scenario = random_stress_scenario(seed)
    try:
        engine = run_scenario(scenario)
    except Exception as exc:
        raise AssertionError(scenario.describe()) from exc

    packet_ids = tuple(engine.packets)
    assert len(packet_ids) == len(set(packet_ids)), scenario.describe()

    terminal_packets = {
        packet_id
        for packet_id, packet in engine.packets.items()
        if packet.lifecycle_state
        in (LifecycleState.COMPLETED, LifecycleState.CANCELLED)
    }
    queued_packets = {
        packet_id
        for link_id in engine.links
        for downstream_id in engine.links
        for packet_id in engine.packet_ids_in_queue(link_id, downstream_id)
    }
    assert terminal_packets.isdisjoint(queued_packets), scenario.describe()

    active_packets = {
        packet_id
        for link_id in engine.links
        for packet_id in engine.packet_ids_on_link(link_id)
    }
    assert terminal_packets.isdisjoint(active_packets), scenario.describe()


@pytest.mark.parametrize("seed", range(140, 160))
def test_small_random_networks_make_progress_or_explain_residual_blockage(seed: int) -> None:
    scenario = random_stress_scenario(seed)
    try:
        engine = run_scenario(scenario)
    except Exception as exc:
        raise AssertionError(scenario.describe()) from exc

    unfinished = [
        packet.packet_id
        for packet in engine.packets.values()
        if packet.lifecycle_state != LifecycleState.COMPLETED
    ]
    if not unfinished:
        return

    open_links = {link_id for link_id in engine.links if engine.is_receiving_open(link_id)}
    has_active_queue = any(
        engine.packet_ids_in_queue(upstream_id, downstream_id)
        for upstream_id in engine.links
        for downstream_id in engine.links
    )
    has_pending_origin_demand = bool(engine.pending_demands)
    has_storage_bottleneck = any(
        engine.link_storage(link_id).storage
        >= engine.links[link_id].declared_storage_capacity_packets
        for link_id in open_links
    )
    assert has_active_queue or has_pending_origin_demand or has_storage_bottleneck, (
        scenario.describe(),
        unfinished,
    )
