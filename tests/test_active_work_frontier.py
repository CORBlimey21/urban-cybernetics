from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.validation import (
    ValidationContext,
    build_commodity_parity_validation_report,
    build_spillback_validation_report,
)

from parity_torture.helpers import (
    instantiate_demands,
    random_stress_scenario,
    run_ticks,
)


def _build_engine(scenario, *, frontier: bool) -> LoadingEngine:
    return LoadingEngine(
        links=scenario.links,
        nodes=scenario.nodes,
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        parity_sending_capacity_vehicles_per_tick_by_link=scenario.sending_rates,
        parity_receiving_capacity_vehicles_per_tick_by_link=scenario.receiving_rates,
        use_active_work_frontier=frontier,
    )


def _run_pair(seed: int):
    scenario = random_stress_scenario(seed)
    frontier = _build_engine(scenario, frontier=True)
    exhaustive = _build_engine(scenario, frontier=False)
    for engine in (frontier, exhaustive):
        instantiate_demands(engine, scenario.demands)
        run_ticks(
            engine,
            scenario.horizon,
            closures_by_tick=scenario.closures_by_tick,
        )
    return scenario, frontier, exhaustive


def test_frontier_matches_exhaustive_fixed_seed_torture() -> None:
    for seed in range(24):
        scenario, frontier, exhaustive = _run_pair(seed)
        assert frontier.event_log == exhaustive.event_log, seed
        assert dict(frontier.packets) == dict(exhaustive.packets), seed
        assert frontier.pending_demands == exhaustive.pending_demands, seed
        assert frontier.completed_packet_ids == exhaustive.completed_packet_ids, seed
        assert frontier.conservation_summary() == exhaustive.conservation_summary(), seed
        assert frontier.cumulative_count_projection() == exhaustive.cumulative_count_projection(), seed
        assert frontier.node_transfer_traces() == exhaustive.node_transfer_traces(), seed
        assert frontier._parity_sending_capacity_carry_by_link_id == exhaustive._parity_sending_capacity_carry_by_link_id, seed
        assert frontier._parity_receiving_capacity_carry_by_link_id == exhaustive._parity_receiving_capacity_carry_by_link_id, seed

        frontier_context = ValidationContext.from_engine(frontier, nodes=scenario.nodes)
        exhaustive_context = ValidationContext.from_engine(exhaustive, nodes=scenario.nodes)
        assert frontier_context.count_consistency_report == exhaustive_context.count_consistency_report, seed
        assert build_commodity_parity_validation_report(frontier, validation_context=frontier_context) == build_commodity_parity_validation_report(exhaustive, validation_context=exhaustive_context), seed
        assert build_spillback_validation_report(frontier) == build_spillback_validation_report(exhaustive), seed
