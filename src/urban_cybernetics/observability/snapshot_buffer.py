# SPDX-License-Identifier: MPL-2.0
"""Delayed routing-information snapshots for legacy lifecycle simulations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


EdgeKey = tuple[int, int, int]
EdgeCostSnapshot = dict[EdgeKey, dict[str, float]]


@dataclass(frozen=True, slots=True)
class Snapshot:
    """One timestamped authority-visible routing-information snapshot."""

    timestamp_seconds: float
    edge_costs: EdgeCostSnapshot


class SnapshotBuffer:
    """Rolling history of cost-surface snapshots seen by the routing layer.

    The live graph remains the physical source of truth. This buffer only captures
    the cost surface used by departure-time route choice.
    """

    def __init__(
        self,
        graph: Any,
        snapshot_interval_seconds: float,
        max_history_seconds: float,
    ) -> None:
        self.graph = graph
        self.snapshot_interval_seconds = max(float(snapshot_interval_seconds), 0.0)
        self.max_history_seconds = max(float(max_history_seconds), self.snapshot_interval_seconds)
        self.current_time_seconds = 0.0
        self._snapshots: list[Snapshot] = []

    def record_if_due(self, timestamp_seconds: float) -> None:
        """Record an authority-visible cost-surface snapshot if the interval has elapsed."""

        self.current_time_seconds = float(timestamp_seconds)
        if (
            self._snapshots
            and self.snapshot_interval_seconds > 0.0
            and self.current_time_seconds - self._snapshots[-1].timestamp_seconds
            < self.snapshot_interval_seconds
        ):
            return

        self._snapshots.append(
            Snapshot(
                timestamp_seconds=self.current_time_seconds,
                edge_costs=self._collect_live_costs(self.current_time_seconds),
            )
        )
        self._discard_expired_snapshots()

    def get_costs_at_delay(self, delta_seconds: float) -> EdgeCostSnapshot:
        """Return costs from approximately ``delta_seconds`` before current time.

        A zero delay is the current authority-visible cost surface. Early in a simulation, when no
        snapshot is old enough, the oldest available snapshot is returned.
        """

        if float(delta_seconds) <= 0.0:
            return self._collect_live_costs(self.current_time_seconds)
        if not self._snapshots:
            self.record_if_due(self.current_time_seconds)

        target_time_seconds = self.current_time_seconds - float(delta_seconds)
        for snapshot in reversed(self._snapshots):
            if snapshot.timestamp_seconds <= target_time_seconds:
                return snapshot.edge_costs
        return self._snapshots[0].edge_costs

    def _discard_expired_snapshots(self) -> None:
        if not self._snapshots:
            return
        oldest_to_keep = self.current_time_seconds - self.max_history_seconds
        while len(self._snapshots) > 1 and self._snapshots[1].timestamp_seconds < oldest_to_keep:
            self._snapshots.pop(0)

    def _collect_live_costs(self, timestamp_seconds: float) -> EdgeCostSnapshot:
        edge_costs: EdgeCostSnapshot = {}
        for u, v, key, edge_data in self.graph.edges(keys=True, data=True):
            edge_costs[(int(u), int(v), int(key))] = {
                "penalised_travel_time_seconds": float(
                    edge_data.get("penalised_travel_time_seconds", 0.0)
                ),
                "penalised_marginal_cost_seconds": float(
                    edge_data.get("penalised_marginal_cost_seconds", 0.0)
                ),
                "live_occupancy_count": float(edge_data.get("live_occupancy_count", 0.0)),
                "simulated_volume": float(edge_data.get("simulated_volume", 0.0)),
                "snapshot_timestamp_seconds": float(timestamp_seconds),
            }
        return edge_costs
