# SPDX-License-Identifier: MPL-2.0
"""Authority-visible frame state tests for M14."""

from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import EventType
from urban_cybernetics.observability import ObservationFrame
from urban_cybernetics.routing import (
    AuthorityVisibilityConfig,
    AuthorityVisibleStateResolver,
    CandidateRoutePolicy,
    FrameReceipt,
    RouteChoiceRequest,
    RoutingAuthority,
    RoutingAuthorityConfig,
)


class AuthorityVisibleStateTest(unittest.TestCase):
    def test_visibility_config_validates_fields(self) -> None:
        with self.assertRaises(ValueError):
            AuthorityVisibilityConfig(authority_id="", receipt_delay_ticks=0)
        with self.assertRaises(ValueError):
            AuthorityVisibilityConfig(authority_id="A1", receipt_delay_ticks=-1)

        all_sensors_config = AuthorityVisibilityConfig(
            authority_id="A1",
            receipt_delay_ticks=1,
            accessible_sensor_ids=None,
        )
        no_sensors_config = AuthorityVisibilityConfig(
            authority_id="A2",
            receipt_delay_ticks=1,
            accessible_sensor_ids=(),
        )
        selected_sensors_config = AuthorityVisibilityConfig(
            authority_id="A3",
            receipt_delay_ticks=1,
            accessible_sensor_ids=["S1", "S2"],
        )

        self.assertIsNone(all_sensors_config.accessible_sensor_ids)
        self.assertEqual(no_sensors_config.accessible_sensor_ids, ())
        self.assertEqual(selected_sensors_config.accessible_sensor_ids, ("S1", "S2"))

    def test_receipt_record_is_frozen(self) -> None:
        receipt = FrameReceipt(
            receipt_id="receipt:A1:frame:S1:5:7",
            authority_id="A1",
            frame_id="frame:S1:5",
            receipt_tick=7,
            publication_tick=5,
            measurement_tick=5,
            sensor_id="S1",
        )

        with self.assertRaises(FrozenInstanceError):
            receipt.receipt_tick = 8

    def test_frame_not_visible_before_receipt_tick(self) -> None:
        frame = self.frame("frame:S1:5", sensor_id="S1", publication_tick=5)
        resolver = AuthorityVisibleStateResolver(
            (AuthorityVisibilityConfig("A1", receipt_delay_ticks=2),)
        )

        self.assertEqual(
            resolver.visible_frames(
                authority_id="A1",
                frames=(frame,),
                decision_tick=6,
            ),
            (),
        )
        self.assertEqual(
            resolver.visible_frames(
                authority_id="A1",
                frames=(frame,),
                decision_tick=7,
            ),
            (frame,),
        )

    def test_publication_delay_plus_receipt_delay(self) -> None:
        frame = self.frame(
            "frame:S1:3",
            sensor_id="S1",
            measurement_tick=3,
            publication_tick=5,
        )
        resolver = AuthorityVisibleStateResolver(
            (AuthorityVisibilityConfig("A1", receipt_delay_ticks=2),)
        )

        receipts = resolver.receipts_available_by(
            authority_id="A1",
            frames=(frame,),
            decision_tick=7,
        )

        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].measurement_tick, 3)
        self.assertEqual(receipts[0].publication_tick, 5)
        self.assertEqual(receipts[0].receipt_tick, 7)

    def test_sensor_access_filter(self) -> None:
        frames = (
            self.frame("frame:S1:5", sensor_id="S1"),
            self.frame("frame:S2:5", sensor_id="S2"),
        )
        resolver = AuthorityVisibleStateResolver(
            (
                AuthorityVisibilityConfig(
                    "A-s1",
                    receipt_delay_ticks=0,
                    accessible_sensor_ids=("S1",),
                ),
                AuthorityVisibilityConfig(
                    "A-none",
                    receipt_delay_ticks=0,
                    accessible_sensor_ids=(),
                ),
                AuthorityVisibilityConfig(
                    "A-all",
                    receipt_delay_ticks=0,
                    accessible_sensor_ids=None,
                ),
            )
        )

        self.assertEqual(
            resolver.visible_frames(
                authority_id="A-s1",
                frames=frames,
                decision_tick=5,
            ),
            (frames[0],),
        )
        self.assertEqual(
            resolver.visible_frames(
                authority_id="A-none",
                frames=frames,
                decision_tick=5,
            ),
            (),
        )
        self.assertEqual(
            resolver.visible_frames(
                authority_id="A-all",
                frames=frames,
                decision_tick=5,
            ),
            frames,
        )

    def test_different_authorities_see_same_frame_at_different_times(self) -> None:
        frame = self.frame("frame:S1:5", sensor_id="S1", publication_tick=5)
        resolver = AuthorityVisibleStateResolver(
            (
                AuthorityVisibilityConfig("A0", receipt_delay_ticks=0),
                AuthorityVisibilityConfig("A3", receipt_delay_ticks=3),
            )
        )

        self.assertEqual(
            resolver.visible_frames(authority_id="A0", frames=(frame,), decision_tick=5),
            (frame,),
        )
        self.assertEqual(
            resolver.visible_frames(authority_id="A3", frames=(frame,), decision_tick=7),
            (),
        )
        self.assertEqual(
            resolver.visible_frames(authority_id="A3", frames=(frame,), decision_tick=8),
            (frame,),
        )

    def test_visible_frame_output_order_is_deterministic(self) -> None:
        frames = (
            self.frame(
                "frame:S2:4",
                sensor_id="S2",
                measurement_tick=4,
                publication_tick=5,
            ),
            self.frame(
                "frame:S1:5",
                sensor_id="S1",
                measurement_tick=5,
                publication_tick=5,
            ),
            self.frame(
                "frame:S1:3",
                sensor_id="S1",
                measurement_tick=3,
                publication_tick=4,
            ),
        )
        resolver = AuthorityVisibleStateResolver(
            (AuthorityVisibilityConfig("A1", receipt_delay_ticks=1),)
        )

        first = resolver.visible_frames(
            authority_id="A1",
            frames=frames,
            decision_tick=6,
        )
        second = resolver.visible_frames(
            authority_id="A1",
            frames=tuple(reversed(frames)),
            decision_tick=6,
        )

        self.assertEqual(first, second)
        self.assertEqual(
            tuple(frame.frame_id for frame in first),
            ("frame:S1:3", "frame:S2:4", "frame:S1:5"),
        )

    def test_receipts_available_by_decision_tick(self) -> None:
        visible_frame = self.frame("frame:S1:5", sensor_id="S1", publication_tick=5)
        hidden_frame = self.frame("frame:S1:7", sensor_id="S1", publication_tick=7)
        resolver = AuthorityVisibleStateResolver(
            (AuthorityVisibilityConfig("A1", receipt_delay_ticks=2),)
        )

        receipts = resolver.receipts_available_by(
            authority_id="A1",
            frames=(hidden_frame, visible_frame),
            decision_tick=7,
        )

        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].frame_id, "frame:S1:5")
        self.assertEqual(receipts[0].receipt_tick, 7)
        self.assertEqual(
            receipts[0].receipt_id,
            "receipt:A1:frame:S1:5:7",
        )

    def test_routing_decision_uses_only_visible_frames(self) -> None:
        visible_frame = self.frame("frame:S1:5", sensor_id="S1", publication_tick=5)
        hidden_frame = self.frame("frame:S2:5", sensor_id="S2", publication_tick=5)
        resolver = AuthorityVisibleStateResolver(
            (
                AuthorityVisibilityConfig(
                    "A1",
                    receipt_delay_ticks=0,
                    accessible_sensor_ids=("S1",),
                ),
            )
        )
        authority = RoutingAuthority(
            RoutingAuthorityConfig(
                authority_id="A1",
                authority_type="candidate_route",
                policy_name="candidate_route",
            ),
            policy=CandidateRoutePolicy(),
        )
        request = RouteChoiceRequest(
            request_id="R1",
            demand_id="D1",
            origin_node_id="N1",
            destination_node_id="N2",
            departure_tick=5,
            candidate_routes=(("L1",),),
        )

        visible_frames = resolver.visible_frames(
            authority_id="A1",
            frames=(hidden_frame, visible_frame),
            decision_tick=5,
        )
        decision = authority.decide(
            request=request,
            frames=visible_frames,
            decision_tick=5,
        )

        self.assertEqual(visible_frames, (visible_frame,))
        self.assertEqual(decision.frame_ids_used, ("frame:S1:5",))

    def test_unknown_authority_fails_loudly(self) -> None:
        resolver = AuthorityVisibleStateResolver(
            (AuthorityVisibilityConfig("A1", receipt_delay_ticks=0),)
        )

        with self.assertRaisesRegex(KeyError, "unknown authority_id"):
            resolver.visible_frames(authority_id="missing", frames=(), decision_tick=0)

    def test_loading_does_not_import_routing_or_visibility(self) -> None:
        loading_dir = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "urban_cybernetics"
            / "loading"
        )
        offenders = []
        forbidden_imports = (
            "urban_cybernetics.routing",
            "AuthorityVisibleStateResolver",
            "AuthorityVisibilityConfig",
            "FrameReceipt",
        )
        for path in loading_dir.glob("*.py"):
            text = path.read_text()
            if any(forbidden in text for forbidden in forbidden_imports):
                offenders.append(path.name)

        self.assertEqual(offenders, [])

    def test_observation_frame_has_no_receipt_fields(self) -> None:
        frame = self.frame("frame:S1:5", sensor_id="S1")

        self.assertFalse(hasattr(frame, "receipt_tick"))
        self.assertFalse(hasattr(frame, "receipt_id"))
        self.assertFalse(hasattr(frame, "authority_id"))

    def frame(
        self,
        frame_id: str,
        *,
        sensor_id: str,
        measurement_tick: int = 5,
        publication_tick: int = 5,
    ) -> ObservationFrame:
        return ObservationFrame(
            frame_id=frame_id,
            sensor_id=sensor_id,
            observed_link_id="L1",
            boundary_event_type=EventType.LINK_ENTRY,
            measurement_tick=measurement_tick,
            aggregation_window_ticks=1,
            window_start_tick_exclusive=measurement_tick - 1,
            window_end_tick_inclusive=measurement_tick,
            publication_tick=publication_tick,
            primary_count=1,
        )


if __name__ == "__main__":
    unittest.main()
