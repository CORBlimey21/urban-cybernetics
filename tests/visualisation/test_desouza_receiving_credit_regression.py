from __future__ import annotations

from urban_cybernetics.visualisation.validation_cases import CASES_BY_ID, execute_case


CASE_ID = "M8-PUB-DSOUZA-FIG5-DT1"


def _execute_dt1():
    return execute_case(
        CASES_BY_ID[CASE_ID],
        result_id="test-m8-dsouza-dt1-receiving-credit",
        created_at="2026-07-16T00:00:00+00:00",
        completed_at="2026-07-16T00:00:00+00:00",
        code_commit="test",
    )


def test_dt1_tick_2_retains_unused_l2_receiving_credit() -> None:
    result, _ = _execute_dt1()
    series_by_id = {series.series_id: series for series in result.observed_series}

    assert series_by_id["l2_receiving_budget"].values[2] == 0.0
    assert series_by_id["l2_receiving_carry"].values[1] == 0.5
    assert series_by_id["l2_receiving_carry"].values[2] == 1.0


def test_dt1_p2_uses_retained_l2_credit_at_tick_7() -> None:
    _, bundle = _execute_dt1()
    p2_l2_entries = [
        event
        for event in bundle.event_stream.events
        if event.packet_id == "P2"
        and event.event_type == "link_entry"
        and event.entity_id == "L2"
    ]

    assert len(p2_l2_entries) == 1
    assert p2_l2_entries[0].physical_tick == 7
