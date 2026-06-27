"""Property-style invariant tests over many deterministic randomized cases."""

from __future__ import annotations

import pytest

from urban_cybernetics.core import EventType

from .helpers import (
    assert_core_invariants,
    count_boundary_ordinals,
    random_stress_scenario,
    run_scenario,
)


@pytest.mark.parametrize("seed", range(40))
def test_randomized_scenarios_preserve_fundamental_invariants(seed: int) -> None:
    scenario = random_stress_scenario(seed)
    try:
        engine = run_scenario(scenario)
    except Exception as exc:
        raise AssertionError(scenario.describe()) from exc

    assert engine.check_conservation(), scenario.describe()
    assert_core_invariants(engine)


@pytest.mark.parametrize("seed", range(40, 70))
def test_deterministic_replay_reproduces_identical_event_logs(seed: int) -> None:
    scenario = random_stress_scenario(seed)
    try:
        first = run_scenario(scenario)
        second = run_scenario(scenario)
    except Exception as exc:
        raise AssertionError(scenario.describe()) from exc

    assert first.event_log == second.event_log, scenario.describe()
    assert dict(first.packets) == dict(second.packets), scenario.describe()


@pytest.mark.parametrize("seed", range(70, 90))
def test_event_replay_matches_cumulative_boundary_ordinals(seed: int) -> None:
    scenario = random_stress_scenario(seed)
    try:
        engine = run_scenario(scenario)
    except Exception as exc:
        raise AssertionError(scenario.describe()) from exc

    for link_id in engine.links:
        entry_ordinals = count_boundary_ordinals(
            engine,
            boundary_type="entry",
            link_id=link_id,
        )
        exit_ordinals = count_boundary_ordinals(
            engine,
            boundary_type="exit",
            link_id=link_id,
        )
        entry_events = [
            event
            for event in engine.event_log
            if event.event_type == EventType.LINK_ENTRY and event.entity_id == link_id
        ]
        exit_events = [
            event
            for event in engine.event_log
            if event.event_type == EventType.LINK_EXIT and event.entity_id == link_id
        ]

        assert entry_ordinals == tuple(range(1, len(entry_events) + 1)), (
            scenario.describe(),
            link_id,
            entry_ordinals,
        )
        assert exit_ordinals == tuple(range(1, len(exit_events) + 1)), (
            scenario.describe(),
            link_id,
            exit_ordinals,
        )
