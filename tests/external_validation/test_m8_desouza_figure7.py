# SPDX-License-Identifier: MPL-2.0
"""Focused invariants for the de Souza Figure 7 preparation fixture."""

from __future__ import annotations

import pytest

from urban_cybernetics.core import EventType
from urban_cybernetics.visualisation.validation_cases import CASES_BY_ID, execute_case


CASE_IDS = ("M8-PUB-DSOUZA-FIG7-DT1", "M8-PUB-DSOUZA-FIG7-DT3")
OBSERVABLE_IDS = {
    "upstream_cumulative_outflow",
    "downstream_1_cumulative_inflow",
    "downstream_2_cumulative_inflow",
    "upstream_outflow_per_tick",
    "downstream_1_inflow_per_tick",
    "downstream_2_inflow_per_tick",
}


def _run(case_id: str):
    return execute_case(
        CASES_BY_ID[case_id], result_id=f"test-{case_id.lower()}",
        created_at="2026-07-16T00:00:00+00:00",
        completed_at="2026-07-16T00:00:00+00:00", code_commit="test",
    )


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_figure7_declared_parameters_and_routes_are_exact(case_id: str) -> None:
    result, bundle = _run(case_id)
    config = bundle.provenance.config_snapshot

    assert config["paper_declared"]["length_m_by_link"] == {
        "L1": 150.0, "L2": 150.0, "L3": 150.0,
    }
    assert config["paper_declared"]["free_flow_speed_mps_by_link"] == {
        "L1": 30.0, "L2": 30.0, "L3": 30.0,
    }
    assert config["paper_declared"]["backward_wave_speed_mps_by_link"] == {
        "L1": 6.0, "L2": 6.0, "L3": 6.0,
    }
    assert config["paper_declared"]["jam_density_veh_per_m_by_link"] == {
        "L1": 0.2, "L2": 0.1, "L3": 0.1,
    }
    assert config["paper_declared"]["deterministic_outbound_route_sequence"] == [
        "L2", "L2", "L2", "L3",
    ]
    assert bundle.run.packet_count == 68
    assert result.status.value == "not_run"

    packet_routes = [
        packet.route_intent[-1]
        for packet in sorted(bundle.packets, key=lambda packet: int(packet.packet_id[1:]))
    ]
    assert packet_routes == ["L2", "L2", "L2", "L3"] * 17


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_figure7_observables_are_event_derived_and_node_conservative(case_id: str) -> None:
    result, _ = _run(case_id)
    observed = {series.series_id: series.values for series in result.observed_series}

    assert set(observed) == OBSERVABLE_IDS
    assert observed["upstream_cumulative_outflow"] == tuple(
        first + second
        for first, second in zip(
            observed["downstream_1_cumulative_inflow"],
            observed["downstream_2_cumulative_inflow"],
        )
    )
    for cumulative_id, tick_id in (
        ("upstream_cumulative_outflow", "upstream_outflow_per_tick"),
        ("downstream_1_cumulative_inflow", "downstream_1_inflow_per_tick"),
        ("downstream_2_cumulative_inflow", "downstream_2_inflow_per_tick"),
    ):
        cumulative = observed[cumulative_id]
        assert observed[tick_id] == (cumulative[0],) + tuple(
            current - previous
            for previous, current in zip(cumulative, cumulative[1:])
        )


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_figure7_fifo_transfer_order_and_replay_are_exact(case_id: str) -> None:
    result, bundle = _run(case_id)
    events = bundle.event_stream.events
    upstream_order = [
        event.packet_id for event in events
        if event.event_type == EventType.LINK_EXIT.value and event.entity_id == "L1"
    ]
    downstream_order = [
        event.packet_id for event in events
        if event.event_type == EventType.LINK_ENTRY.value and event.entity_id in {"L2", "L3"}
    ]

    assert upstream_order == downstream_order
    assert upstream_order == sorted(upstream_order, key=lambda packet_id: int(packet_id[1:]))
    scalars = {item.scalar_id: item.value for item in result.observed_scalars}
    assert scalars["conservation_check"] is True
    assert scalars["event_cache_consistency_check"] is True
    assert scalars["cumulative_count_consistency_check"] is True
    assert scalars["deterministic_replay_exact"] is True
