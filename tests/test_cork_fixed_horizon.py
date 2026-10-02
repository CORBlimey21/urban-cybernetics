# SPDX-License-Identifier: MPL-2.0
from urban_cybernetics.experiments.cork_fixed_horizon import (
    TOTAL_HORIZON_SECONDS,
    TOTAL_HORIZON_TICKS,
    run_cork_fixed_horizon_rung,
)


def test_cork_fixed_horizon_protocol_executes_exactly_15000_ticks() -> None:
    assert TOTAL_HORIZON_SECONDS == 600.0
    assert TOTAL_HORIZON_TICKS == 15_000
    report = run_cork_fixed_horizon_rung(5, run_replay=False)
    primary = report["primary"]
    assert primary["run_status"] == "fixed_horizon_complete"
    assert primary["ticks_executed"] == 15_000
    assert primary["validation"]["exact_conservation"] is True
    assert (
        primary["admitted_by_horizon"]
        + primary["pending_origin_admission_by_horizon"]
        == 5
    )
    assert (
        primary["completed_by_horizon"]
        + primary["active_or_queued_by_horizon"]
        + primary["cancelled_by_horizon"]
        == primary["admitted_by_horizon"]
    )
