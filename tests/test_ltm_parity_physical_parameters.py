"""M1 static physical-parameter and timestep parity checks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.config import (
    ACADEMIC_LTM_PARITY_PROFILE_ID,
    LEGACY_LOADING_PROFILE_ID,
)
from urban_cybernetics.core import Link
from urban_cybernetics.topology import CanonicalTopologyLink
from urban_cybernetics.validation import (
    assess_physical_parameter_eligibility,
    require_physical_parameter_eligibility,
)


class LTMParityPhysicalParametersTest(unittest.TestCase):
    def test_resolved_parameters_accept_consistent_triangular_fd_link(self) -> None:
        link = self.parity_link(link_id="L1", lane_count=2, tick_duration_seconds=5.0)

        resolved = link.resolved_physical_parameters()

        self.assertTrue(resolved.parity_eligible)
        self.assertEqual(resolved.ineligibility_reasons, ())
        self.assertEqual(resolved.free_flow_lag_ticks, 2)
        self.assertEqual(resolved.backward_wave_lag_ticks, 4)
        self.assertEqual(resolved.storage_capacity_packets, 30)
        self.assertAlmostEqual(resolved.total_capacity_vehicles_per_tick, 5.0)
        self.assertIsNotNone(resolved.fd_report)
        self.assertTrue(resolved.fd_report.is_consistent)  # type: ignore[union-attr]
        self.assertAlmostEqual(
            resolved.fd_report.expected_capacity_veh_per_hour_per_lane,  # type: ignore[union-attr]
            1800.0,
        )
        self.assertAlmostEqual(
            resolved.fd_report.critical_density_veh_per_km_per_lane,  # type: ignore[union-attr]
            50.0,
        )
        self.assertIsNotNone(resolved.timestep_report)
        self.assertTrue(resolved.timestep_report.is_admissible)  # type: ignore[union-attr]

    def test_missing_physical_metadata_is_not_parity_eligible(self) -> None:
        link = Link(link_id="legacy", free_flow_ticks=1)

        resolved = link.resolved_physical_parameters()

        self.assertFalse(resolved.parity_eligible)
        self.assertIn("length_m", resolved.missing_physical_fields)
        self.assertIn(
            "missing_physical_metadata:backward_wave_speed_mps",
            resolved.ineligibility_reasons,
        )
        with self.assertRaises(ValueError):
            link.require_parity_physical_parameters()

    def test_fd_capacity_mismatch_is_reported_without_rewriting_declared_caps(self) -> None:
        link = self.parity_link(
            link_id="bad-capacity",
            capacity_veh_per_hour_per_lane=2200.0,
        )

        resolved = link.resolved_physical_parameters()

        self.assertFalse(resolved.parity_eligible)
        self.assertEqual(link.declared_sending_capacity_per_tick, 1)
        self.assertIn(
            "fundamental_diagram_inconsistent",
            resolved.ineligibility_reasons,
        )
        self.assertIsNotNone(resolved.fd_report)
        self.assertFalse(resolved.fd_report.is_consistent)  # type: ignore[union-attr]

    def test_explicit_free_flow_override_must_match_physical_lag_for_parity(self) -> None:
        link = self.parity_link(link_id="bad-ff", free_flow_ticks=99)

        resolved = link.resolved_physical_parameters()

        self.assertFalse(resolved.parity_eligible)
        self.assertEqual(link.free_flow_ticks, 99)
        self.assertIn("free_flow_ticks_inconsistent", resolved.ineligibility_reasons)

    def test_explicit_storage_override_must_match_physical_storage_for_parity(self) -> None:
        link = self.parity_link(
            link_id="bad-storage",
            declared_storage_capacity_packets=99,
        )

        resolved = link.resolved_physical_parameters()

        self.assertFalse(resolved.parity_eligible)
        self.assertEqual(link.declared_storage_capacity_packets, 99)
        self.assertIn("storage_capacity_inconsistent", resolved.ineligibility_reasons)

    def test_timestep_report_rejects_ticks_longer_than_physical_lags(self) -> None:
        link = self.parity_link(link_id="bad-timestep", tick_duration_seconds=20.0)

        resolved = link.resolved_physical_parameters()

        self.assertFalse(resolved.parity_eligible)
        self.assertIsNotNone(resolved.timestep_report)
        self.assertFalse(resolved.timestep_report.is_admissible)  # type: ignore[union-attr]
        self.assertIn("tick_exceeds_free_flow_travel_time", resolved.ineligibility_reasons)

    def test_aggregate_physical_eligibility_report_is_profile_aware(self) -> None:
        link = self.parity_link(link_id="L1")

        parity_report = assess_physical_parameter_eligibility(
            (link,),
            model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        )
        legacy_report = assess_physical_parameter_eligibility(
            (link,),
            model_profile_id=LEGACY_LOADING_PROFILE_ID,
        )

        self.assertTrue(parity_report.is_parity_eligible)
        self.assertEqual(parity_report.ineligibility_reasons, ())
        self.assertFalse(legacy_report.is_parity_eligible)
        self.assertIn(
            "legacy_profile_not_parity_evidence",
            legacy_report.ineligibility_reasons,
        )
        with self.assertRaises(ValueError):
            require_physical_parameter_eligibility(
                (link,),
                model_profile_id=LEGACY_LOADING_PROFILE_ID,
            )

    def test_empty_physical_eligibility_report_is_not_parity_evidence(self) -> None:
        report = assess_physical_parameter_eligibility(())

        self.assertFalse(report.is_parity_eligible)
        self.assertEqual(report.link_reports, ())

    def test_unsupported_physical_eligibility_profile_is_rejected(self) -> None:
        link = self.parity_link(link_id="L1")

        with self.assertRaises(ValueError):
            assess_physical_parameter_eligibility(
                (link,),
                model_profile_id="unknown-profile",
            )

    def test_canonical_topology_link_exposes_lane_aware_physical_capacity(self) -> None:
        canonical_link = self.canonical_link(lane_count=2)

        loading_link = canonical_link.to_loading_link(tick_duration_seconds=10.0)
        physical_capacity = canonical_link.physical_capacity_vehicles_per_tick(
            tick_duration_seconds=10.0
        )

        self.assertEqual(loading_link.declared_sending_capacity_per_tick, 5)
        self.assertAlmostEqual(physical_capacity, 10.0)

    def test_canonical_topology_link_resolves_physical_parameters_without_dynamic_state(self) -> None:
        canonical_link = self.canonical_link(lane_count=2)

        resolved = canonical_link.resolved_physical_parameters(
            tick_duration_seconds=5.0,
        )

        self.assertTrue(resolved.parity_eligible)
        self.assertEqual(resolved.link_id, canonical_link.link_id)
        self.assertAlmostEqual(resolved.total_capacity_vehicles_per_tick, 5.0)
        self.assertFalse(hasattr(canonical_link, "current_storage"))
        self.assertFalse(hasattr(canonical_link, "queue_length"))

    def test_canonical_topology_link_reports_missing_physical_metadata(self) -> None:
        canonical_link = self.canonical_link(jam_density_veh_per_km_per_lane=None)

        resolved = canonical_link.resolved_physical_parameters(
            tick_duration_seconds=5.0,
        )

        self.assertFalse(resolved.parity_eligible)
        self.assertIn("jam_density_veh_per_km_per_lane", resolved.missing_physical_fields)
        with self.assertRaises(ValueError):
            canonical_link.require_parity_physical_parameters(
                tick_duration_seconds=5.0,
            )

    def parity_link(
        self,
        *,
        link_id: str,
        length_m: float = 100.0,
        lane_count: int = 1,
        free_flow_speed_mps: float = 10.0,
        backward_wave_speed_mps: float = 5.0,
        jam_density_veh_per_km_per_lane: float = 150.0,
        capacity_veh_per_hour_per_lane: float = 1800.0,
        tick_duration_seconds: float = 5.0,
        free_flow_ticks: int | None = None,
        declared_storage_capacity_packets: int | None = None,
    ) -> Link:
        return Link(
            link_id=link_id,
            free_flow_ticks=free_flow_ticks,
            length_m=length_m,
            lane_count=lane_count,
            free_flow_speed_mps=free_flow_speed_mps,
            backward_wave_speed_mps=backward_wave_speed_mps,
            jam_density_veh_per_km_per_lane=jam_density_veh_per_km_per_lane,
            capacity_veh_per_hour_per_lane=capacity_veh_per_hour_per_lane,
            tick_duration_seconds=tick_duration_seconds,
            declared_storage_capacity_packets=declared_storage_capacity_packets,
        )

    def canonical_link(
        self,
        *,
        lane_count: int = 1,
        jam_density_veh_per_km_per_lane: float | None = 150.0,
    ) -> CanonicalTopologyLink:
        return CanonicalTopologyLink(
            link_id="L0001",
            tail_node_id="N001",
            head_node_id="N002",
            source_link_id="1->2",
            source_tail_node_id="1",
            source_head_node_id="2",
            length_m=100.0,
            lane_count=lane_count,
            free_flow_speed_mps=10.0,
            capacity_veh_per_hour_per_lane=1800.0,
            jam_density_veh_per_km_per_lane=jam_density_veh_per_km_per_lane,
            backward_wave_speed_mps=5.0,
        )


if __name__ == "__main__":
    unittest.main()
