# SPDX-License-Identifier: MPL-2.0
"""Focused tests for deterministic fractional service credit above the kernel."""

from __future__ import annotations

from copy import deepcopy

import pytest

from urban_cybernetics.core import DemandDeclaration, JunctionSpec, Link, MovementSpec, Node
from urban_cybernetics.extensions.executable_routing import ExecutableRoutingLoadingEngine
from urban_cybernetics.extensions.fractional_service_credit import (
    FRACTIONAL_CREDIT,
    LEGACY_INTEGER_CLAMPED,
    FractionalServiceCreditConfig,
    FractionalServiceCreditEvidence,
    FractionalServiceCreditIntegrityError,
    FractionalServiceCreditLoadingEngine,
    FractionalServiceCreditMixin,
)
from urban_cybernetics.loading import GeneralMovementAllocator, LoadingEngine


class _FractionalRoutingEngine(
    FractionalServiceCreditMixin,
    ExecutableRoutingLoadingEngine,
):
    pass


def _link(rate: float, *, declared: int = 1) -> Link:
    return Link(
        "L",
        free_flow_ticks=1,
        declared_sending_capacity_per_tick=declared,
        declared_receiving_capacity_per_tick=declared,
        declared_storage_capacity_packets=40,
        length_m=10.0,
        lane_count=1,
        free_flow_speed_mps=10.0,
        jam_density_veh_per_km_per_lane=4000.0,
        backward_wave_speed_mps=10.0,
        capacity_veh_per_hour_per_lane=rate * 3600.0,
        tick_duration_seconds=1.0,
    )


def _engine(rate: float, *, mode: str = FRACTIONAL_CREDIT, declared: int = 1):
    return FractionalServiceCreditLoadingEngine(
        links={"L": _link(rate, declared=declared)},
        fractional_service_credit_config=FractionalServiceCreditConfig(
            mode=mode,
            continuous_capacity_by_link=(("L", rate),),
        ),
        executable_semantic_hash="test-semantic-hash",
    )


@pytest.mark.parametrize(
    ("rate", "expected_ticks"),
    (
        (0.25, (4, 8, 12, 16)),
        (0.4, (3, 5, 8, 10)),
        (0.5, (2, 4, 6, 8)),
        (0.75, (2, 3, 4, 6)),
        (1.0, (1, 2, 3, 4)),
        (1.5, (1, 2, 2, 3)),
    ),
)
def test_fractional_rates_have_exact_saturated_service_patterns(
    rate: float,
    expected_ticks: tuple[int, ...],
) -> None:
    engine = _engine(rate, declared=2)
    for index in range(4):
        engine.instantiate(DemandDeclaration(f"D{index}", 0, ("L",)))
    completion_ticks = []
    prior = 0
    while len(engine.completed_packet_ids) < 4:
        engine.step()
        count = len(engine.completed_packet_ids)
        completion_ticks.extend((engine.current_tick,) * (count - prior))
        prior = count
    assert tuple(completion_ticks) == expected_ticks
    assert engine.check_conservation()


def test_idle_period_cannot_bank_unbounded_sending_burst() -> None:
    engine = _engine(0.25)
    for _ in range(20):
        engine.step()
    for index in range(3):
        engine.instantiate(DemandDeclaration(f"idle-{index}", 20, ("L",)))
    engine.step()
    assert not engine.completed_packet_ids
    for _ in range(3):
        engine.step()
    assert len(engine.completed_packet_ids) == 1
    sending = [
        item
        for item in engine.fractional_service_credit_evidence
        if item.resource_type == "link_sending"
    ]
    assert all(0 <= item.closing_credit < 1 for item in sending)
    receiving = [
        item
        for item in engine.fractional_service_credit_evidence
        if item.resource_type == "link_receiving"
    ]
    assert max(item.closing_credit for item in receiving) <= 2.0


def test_legacy_mode_is_event_identical_to_unextended_loader() -> None:
    link = _link(0.25, declared=1)
    baseline = LoadingEngine(links={"L": link})
    extended = _engine(0.25, mode=LEGACY_INTEGER_CLAMPED)
    for index in range(3):
        demand = DemandDeclaration(f"legacy-{index}", 0, ("L",))
        baseline.instantiate(demand)
        extended.instantiate(demand)
    for _ in range(5):
        baseline.step()
        extended.step()
    assert baseline.event_log == extended.event_log
    assert not extended.fractional_service_credit_evidence
    assert baseline.conservation_summary() == extended.conservation_summary()


def test_credit_configuration_and_evidence_round_trip_and_detect_tampering() -> None:
    config = FractionalServiceCreditConfig(
        FRACTIONAL_CREDIT,
        (("B", 0.5), ("A", 0.25)),
    )
    assert FractionalServiceCreditConfig.from_dict(config.to_dict()) == config
    engine = _engine(0.5)
    engine.instantiate(DemandDeclaration("one", 0, ("L",)))
    engine.step()
    evidence = engine.fractional_service_credit_evidence[0]
    assert FractionalServiceCreditEvidence.from_dict(evidence.to_dict()) == evidence
    tampered = deepcopy(evidence.to_dict())
    tampered["closing_credit"] = 0.99
    with pytest.raises(FractionalServiceCreditIntegrityError, match="hash mismatch"):
        FractionalServiceCreditEvidence.from_dict(tampered)


def test_policy_metadata_cannot_claim_semantics_the_v1_recurrence_does_not_use() -> None:
    with pytest.raises(FractionalServiceCreditIntegrityError, match="implemented v1 recurrence"):
        FractionalServiceCreditConfig(
            mode=FRACTIONAL_CREDIT,
            continuous_capacity_by_link=(("L", 0.25),),
            sending_retention_policy="bank_all_unused_service",
        )


def test_receiving_preload_aligns_first_service_tick_with_sending_addition() -> None:
    engine = _engine(0.25)
    engine.instantiate(DemandDeclaration("phase", 0, ("L",)))
    for _ in range(4):
        engine.step()
    sending = [
        item
        for item in engine.fractional_service_credit_evidence
        if item.resource_type == "link_sending"
    ]
    receiving = [
        item
        for item in engine.fractional_service_credit_evidence
        if item.resource_type == "link_receiving"
    ]
    assert [item.available_whole_service for item in sending] == [0, 0, 0, 1]
    assert [item.available_whole_service for item in receiving] == [0, 0, 0, 1]
    assert receiving[0].opening_credit == pytest.approx(0.25)
    assert sending[0].opening_credit == pytest.approx(0.0)
    assert engine.completed_packet_ids


def test_fractional_credit_composes_with_executable_routing() -> None:
    links = {
        link_id: Link(
            link_id,
            free_flow_ticks=1,
            declared_sending_capacity_per_tick=1,
            declared_receiving_capacity_per_tick=1,
            declared_storage_capacity_packets=20,
            length_m=10.0,
            lane_count=1,
            free_flow_speed_mps=10.0,
            jam_density_veh_per_km_per_lane=2000.0,
            backward_wave_speed_mps=10.0,
            capacity_veh_per_hour_per_lane=1800.0,
            tick_duration_seconds=1.0,
        )
        for link_id in ("U", "D")
    }
    node = Node(
        "N",
        incoming_link_ids=("U",),
        outgoing_link_ids=("D",),
        junction_spec=JunctionSpec(
            "N",
            ("U",),
            ("D",),
            movement_specs=(MovementSpec("U", "D"),),
        ),
    )
    engine = _FractionalRoutingEngine(
        links=links,
        nodes=(node,),
        fractional_service_credit_config=FractionalServiceCreditConfig(
            FRACTIONAL_CREDIT,
            (("U", 0.5), ("D", 0.5)),
        ),
    )
    engine.instantiate(DemandDeclaration("route", 0, ("U", "D")))
    for _ in range(8):
        engine.step()
    assert len(engine.completed_packet_ids) == 1
    assert engine.movement_instruction_evidence
    assert engine.fractional_service_credit_evidence
    assert engine.check_conservation()


def test_receiving_closure_preserves_physical_authority_and_bounds_reopening() -> None:
    links = {
        link_id: Link(
            link_id,
            free_flow_ticks=1,
            declared_sending_capacity_per_tick=1,
            declared_receiving_capacity_per_tick=1,
            declared_storage_capacity_packets=20,
            length_m=10.0,
            lane_count=1,
            free_flow_speed_mps=10.0,
            jam_density_veh_per_km_per_lane=2000.0,
            backward_wave_speed_mps=10.0,
            capacity_veh_per_hour_per_lane=1800.0,
            tick_duration_seconds=1.0,
        )
        for link_id in ("U", "D")
    }
    node = Node(
        "N",
        incoming_link_ids=("U",),
        outgoing_link_ids=("D",),
        junction_spec=JunctionSpec(
            "N",
            ("U",),
            ("D",),
            movement_specs=(MovementSpec("U", "D"),),
        ),
    )
    engine = FractionalServiceCreditLoadingEngine(
        links=links,
        nodes=(node,),
        fractional_service_credit_config=FractionalServiceCreditConfig(
            FRACTIONAL_CREDIT,
            (("U", 0.5), ("D", 0.5)),
        ),
    )
    for index in range(3):
        engine.instantiate(DemandDeclaration(f"closed-{index}", 0, ("U", "D")))
    engine.set_receiving_open("D", False)
    for _ in range(6):
        engine.step()
    assert not any(
        event.entity_id == "D" and event.event_type.value == "link_entry"
        for event in engine.event_log
    )
    engine.set_receiving_open("D", True)
    engine.step()
    entries = [
        item
        for item in engine.event_log
        if item.entity_id == "D"
        and item.event_type.value == "link_entry"
        and item.physical_tick == engine.current_tick
    ]
    assert len(entries) <= 1
    for _ in range(12):
        engine.step()
    assert len(engine.completed_packet_ids) == 3
    assert engine.check_conservation()


def test_shared_downstream_credit_is_one_deterministic_merge_competition_domain() -> None:
    links = {
        link_id: Link(
            link_id,
            free_flow_ticks=1,
            declared_sending_capacity_per_tick=1,
            declared_receiving_capacity_per_tick=1,
            declared_storage_capacity_packets=20,
            length_m=10.0,
            lane_count=1,
            free_flow_speed_mps=10.0,
            jam_density_veh_per_km_per_lane=2000.0,
            backward_wave_speed_mps=10.0,
            capacity_veh_per_hour_per_lane=1800.0,
            tick_duration_seconds=1.0,
        )
        for link_id in ("U1", "U2", "D")
    }
    node = Node(
        "N",
        incoming_link_ids=("U1", "U2"),
        outgoing_link_ids=("D",),
        junction_spec=JunctionSpec(
            "N",
            ("U1", "U2"),
            ("D",),
            movement_specs=(MovementSpec("U1", "D"), MovementSpec("U2", "D")),
        ),
    )

    def execute():
        engine = FractionalServiceCreditLoadingEngine(
            links=links,
            nodes=(node,),
            node_transfer_policy=GeneralMovementAllocator((node,)),
            fractional_service_credit_config=FractionalServiceCreditConfig(
                FRACTIONAL_CREDIT,
                (("U1", 1.0), ("U2", 1.0), ("D", 0.5)),
            ),
        )
        engine.instantiate(DemandDeclaration("one", 0, ("U1", "D")))
        engine.instantiate(DemandDeclaration("two", 0, ("U2", "D")))
        for _ in range(8):
            engine.step()
        entries = tuple(
            (item.packet_id, item.physical_tick)
            for item in engine.event_log
            if item.event_type.value == "link_entry" and item.entity_id == "D"
        )
        return engine, entries

    first, first_entries = execute()
    replay, replay_entries = execute()
    assert first_entries == replay_entries
    assert tuple(tick for _, tick in first_entries) == (2, 4)
    assert first.event_log == replay.event_log
    assert first.check_conservation()
