"""Scheduled demand admission adapter for the loading engine."""

from __future__ import annotations

from dataclasses import dataclass

from urban_cybernetics.core import DemandDeclaration as LoadingDemandDeclaration
from urban_cybernetics.core import Packet
from urban_cybernetics.demand.resolution import ResolvedDemandManifest
from urban_cybernetics.loading import LoadingEngine


@dataclass(frozen=True)
class ScheduledLoadingRequest:
    """One due unit-packet request derived from resolved pre-packet demand."""

    loading_demand_id: str
    od_demand_id: str
    route_id: str
    departure_tick: int
    route_intent: tuple[str, ...]
    cohort_id: str | None = None
    authority_id: str | None = None

    def to_loading_demand(self) -> LoadingDemandDeclaration:
        """Return the loading-engine admission request for this scheduled unit."""

        return LoadingDemandDeclaration(
            demand_id=self.loading_demand_id,
            departure_tick=self.departure_tick,
            route_intent=self.route_intent,
        )


class ScheduledDemandLoader:
    """Submit resolved scheduled demand to loading without creating packets itself."""

    def __init__(self, resolved_manifest: ResolvedDemandManifest) -> None:
        self.resolved_manifest = resolved_manifest
        self._requests = self._build_requests(resolved_manifest)
        self._submitted_loading_demand_ids: set[str] = set()

    @property
    def scheduled_requests(self) -> tuple[ScheduledLoadingRequest, ...]:
        """Return all unit loading requests implied by the resolved manifest."""

        return self._requests

    @property
    def submitted_loading_demand_ids(self) -> frozenset[str]:
        """Return requests already handed to the loading engine."""

        return frozenset(self._submitted_loading_demand_ids)

    def submit_due_departures(self, engine: LoadingEngine) -> tuple[Packet, ...]:
        """Submit all unsubmitted requests due at or before the engine tick.

        The loading engine decides whether each request becomes a physical packet.
        If origin storage is full, the engine records the request as pending and no
        packet is created by this adapter.
        """

        admitted_packets: list[Packet] = []
        for request in self._requests:
            if request.departure_tick > engine.current_tick:
                break
            if request.loading_demand_id in self._submitted_loading_demand_ids:
                continue
            packet = engine.instantiate(request.to_loading_demand())
            self._submitted_loading_demand_ids.add(request.loading_demand_id)
            if packet is not None:
                admitted_packets.append(packet)
        return tuple(admitted_packets)

    @staticmethod
    def _build_requests(
        resolved_manifest: ResolvedDemandManifest,
    ) -> tuple[ScheduledLoadingRequest, ...]:
        route_by_demand_id = resolved_manifest.route_by_demand_id
        requests: list[ScheduledLoadingRequest] = []
        for declaration in sorted(
            resolved_manifest.demand_manifest.declarations,
            key=lambda item: item.demand_id,
        ):
            route = route_by_demand_id[declaration.demand_id]
            for unit_index, departure_tick in enumerate(
                declaration.expand_departure_ticks(),
                start=1,
            ):
                requests.append(
                    ScheduledLoadingRequest(
                        loading_demand_id=(
                            f"{declaration.demand_id}:unit:{unit_index:06d}"
                        ),
                        od_demand_id=declaration.demand_id,
                        route_id=route.route_id,
                        departure_tick=departure_tick,
                        route_intent=route.ordered_link_ids,
                        cohort_id=declaration.cohort_id,
                        authority_id=declaration.authority_id,
                    )
                )
        return tuple(
            sorted(
                requests,
                key=lambda item: (
                    item.departure_tick,
                    item.od_demand_id,
                    item.loading_demand_id,
                ),
            )
        )
