from urban_cybernetics.core import Event, EventType
from urban_cybernetics.validation import ValidationContext


def test_link_boundary_packet_orders_share_one_event_log_projection() -> None:
    context = ValidationContext(
        event_log=(
            Event(0, "p1", EventType.INSTANTIATED, "d1", 0),
            Event(1, "p1", EventType.LINK_ENTRY, "l1", 0),
            Event(2, "p2", EventType.LINK_ENTRY, "l1", 0),
            Event(3, "p1", EventType.LINK_EXIT, "l1", 1),
            Event(4, "p1", EventType.LINK_ENTRY, "l2", 1),
            Event(5, "p2", EventType.LINK_EXIT, "l1", 2),
        ),
        link_ids=("l1", "l2", "unused"),
        packets={},
        model_profile_id="parity_ltm_v1",
        current_tick=2,
    )

    assert context.link_boundary_packet_order(
        link_id="l1", event_type=EventType.LINK_ENTRY
    ) == ("p1", "p2")
    projection = context._packet_order_by_link_boundary
    assert projection is not None
    assert context.link_boundary_packet_order(
        link_id="l1", event_type=EventType.LINK_EXIT
    ) == ("p1", "p2")
    assert context.link_boundary_packet_order(
        link_id="l2", event_type=EventType.LINK_ENTRY
    ) == ("p1",)
    assert context.link_boundary_packet_order(
        link_id="unused", event_type=EventType.LINK_EXIT
    ) == ()
    assert context._packet_order_by_link_boundary is projection
