"""Disposable read-only validation context derived from completed runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from urban_cybernetics.core import Event, EventType, Node, Packet
from urban_cybernetics.loading.cumulative_counts import (
    CountConsistencyReport,
    CumulativeCountProjection,
    count_consistency_report_from_projection,
    cumulative_count_projection,
)


@dataclass(frozen=True, slots=True)
class ValidationContext:
    """Deterministic derived evidence cache for post-run validators."""

    event_log: tuple[Event, ...]
    link_ids: tuple[str, ...]
    packets: dict[str, Packet]
    model_profile_id: str
    current_tick: int
    nodes: tuple[Node, ...] = ()
    run_config: dict[str, Any] = field(default_factory=dict)
    _projection: CumulativeCountProjection | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _count_report: CountConsistencyReport | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _events_by_packet_id: dict[str, tuple[Event, ...]] | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_log", tuple(self.event_log))
        object.__setattr__(self, "link_ids", tuple(self.link_ids))
        object.__setattr__(self, "packets", dict(self.packets))
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "run_config", dict(self.run_config))

    @classmethod
    def from_engine(
        cls,
        engine: Any,
        *,
        nodes: tuple[Node, ...] = (),
        run_config: dict[str, Any] | None = None,
    ) -> "ValidationContext":
        """Snapshot canonical run evidence after simulation has completed."""

        return cls(
            event_log=tuple(engine.event_log),
            link_ids=tuple(engine.links),
            packets=dict(engine.packets),
            model_profile_id=engine.model_profile_id,
            current_tick=engine.current_tick,
            nodes=nodes,
            run_config={} if run_config is None else dict(run_config),
        )

    @property
    def cumulative_count_projection(self) -> CumulativeCountProjection:
        """Return the shared count projection, building it at most once."""

        if self._projection is None:
            object.__setattr__(
                self,
                "_projection",
                cumulative_count_projection(
                    self.event_log,
                    link_ids=self.link_ids,
                    packets=self.packets,
                    max_tick=self.current_tick,
                ),
            )
        assert self._projection is not None
        return self._projection

    @property
    def count_consistency_report(self) -> CountConsistencyReport:
        """Return the shared count consistency report."""

        if self._count_report is None:
            object.__setattr__(
                self,
                "_count_report",
                count_consistency_report_from_projection(
                    self.cumulative_count_projection,
                    events=self.event_log,
                ),
            )
        assert self._count_report is not None
        return self._count_report

    @property
    def events_by_packet_id(self) -> dict[str, tuple[Event, ...]]:
        """Return packet-keyed canonical event histories."""

        if self._events_by_packet_id is None:
            events_by_packet_id: dict[str, list[Event]] = {}
            for event in self.event_log:
                events_by_packet_id.setdefault(event.packet_id, []).append(event)
            object.__setattr__(
                self,
                "_events_by_packet_id",
                {
                    packet_id: tuple(events)
                    for packet_id, events in events_by_packet_id.items()
                },
            )
        assert self._events_by_packet_id is not None
        return self._events_by_packet_id

    def link_boundary_packet_order(
        self,
        *,
        link_id: str,
        event_type: EventType,
    ) -> tuple[str, ...]:
        """Return packet order for one link boundary event type."""

        return tuple(
            event.packet_id
            for event in self.event_log
            if event.event_type == event_type and event.entity_id == link_id
        )
