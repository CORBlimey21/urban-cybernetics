# SPDX-License-Identifier: MPL-2.0
"""Sparse, summary-evidence V2 execution for city-scale 25 Hz experiments.

The frozen :class:`LoadingEngine` remains untouched.  This extension replaces
only execution indexes whose dense all-link/all-tick representation is
observationally equivalent to sparse cumulative histories and lazily advanced
receiving credit.  Canonical physical events remain owned by the base engine.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import ceil, floor
from types import MappingProxyType

from urban_cybernetics.core import Event, EventType
from urban_cybernetics.extensions.gate_aware_fractional_service import (
    GateAwareFractionalServiceIntegrityError,
    GateAwareFractionalServiceLoadingEngine,
    _PreparedSendingAccount,
    evaluate_effective_service_rate,
)
from urban_cybernetics.loading.engine import LoadingEngine
from urban_cybernetics.loading.receiving import (
    bounded_integer_receiving_capacity_carry,
)
from urban_cybernetics.loading.transfer_policy import (
    GeneralMovementAllocator,
    JunctionAllocationDecision,
    JunctionAllocationInput,
    TransferRequest,
)


CITY_SCALE_V2_EXECUTION_VERSION = "uc.city-scale-sparse-v2-execution.v1"
CITY_SCALE_V2_EVIDENCE_MODE = "summary_canonical_events_only"


@dataclass(frozen=True, slots=True)
class CityScaleV2Summary:
    ticks: int
    sending_domains_prepared: int
    receiving_domains_prepared: int
    canonical_events_observed: int
    max_sending_domains_per_tick: int
    max_receiving_domains_per_tick: int
    total_physical_links: int
    evidence_mode: str = CITY_SCALE_V2_EVIDENCE_MODE
    execution_version: str = CITY_SCALE_V2_EXECUTION_VERSION


class CityScaleSummaryMovementAllocator(GeneralMovementAllocator):
    """Suppress a full static movement-deficit snapshot on every empty tick."""

    allocator_id = "uc.city-scale-summary-general-movement-allocator.v1"

    def _allocate_one_junction(
        self,
        allocation_input: JunctionAllocationInput,
        *,
        remaining_slots: dict[str, int],
        approved_packet_ids: set[str],
    ) -> JunctionAllocationDecision:
        if allocation_input.junction_spec is None:
            return super()._allocate_one_junction(
                allocation_input,
                remaining_slots=remaining_slots,
                approved_packet_ids=approved_packet_ids,
            )
        approved = self._choose_movement_transfers(
            allocation_input=allocation_input,
            remaining_slots=remaining_slots,
            approved_packet_ids=approved_packet_ids,
        )
        rejected = self._rejected_transfers(
            allocation_input.transfer_requests,
            approved,
            remaining_slots,
            allocation_input.packet_ids_by_upstream_link,
            allocation_input.queued_downstream_by_packet_id,
            approved_packet_ids,
            junction_spec=allocation_input.junction_spec,
            allocation_input=allocation_input,
        )
        summaries = self._movement_flow_summaries(
            allocation_input.transfer_requests, approved
        )
        trace = self._allocation_trace(
            allocation_input=allocation_input,
            approved_transfers=approved,
            rejected_transfers=rejected,
            remaining_slots=remaining_slots,
            movement_flow_summaries=summaries,
        )
        active_state = tuple(
            (
                movement.movement_id,
                self._movement_deficit_by_node_movement[
                    (allocation_input.node_id, movement.movement_id)
                ],
            )
            for movement in allocation_input.junction_spec.movement_specs
        )
        return JunctionAllocationDecision(
            approved_transfers=approved,
            rejected_transfers=rejected,
            movement_flow_summaries=summaries,
            updated_allocator_state=active_state,
            allocation_traces=(trace,),
        )

    def allocate(
        self,
        *,
        allocation_inputs: tuple[JunctionAllocationInput, ...],
    ) -> JunctionAllocationDecision:
        approved = []
        rejected = []
        summaries = []
        traces = []
        approved_packet_ids: set[str] = set()
        remaining_slots = (
            dict(allocation_inputs[0].receiving_slots_by_downstream_link)
            if allocation_inputs
            else {}
        )
        active_state_keys: set[tuple[str, str]] = set()
        for allocation_input in allocation_inputs:
            decision = self._allocate_one_junction(
                allocation_input,
                remaining_slots=remaining_slots,
                approved_packet_ids=approved_packet_ids,
            )
            approved.extend(decision.approved_transfers)
            rejected.extend(decision.rejected_transfers)
            summaries.extend(decision.movement_flow_summaries)
            traces.extend(decision.allocation_traces)
            for transfer in decision.approved_transfers:
                approved_packet_ids.add(transfer.packet_id)
            if allocation_input.junction_spec is not None:
                active_state_keys.update(
                    (allocation_input.node_id, movement.movement_id)
                    for movement in allocation_input.junction_spec.movement_specs
                )
        self._last_allocation_traces = tuple(traces)
        return JunctionAllocationDecision(
            approved_transfers=tuple(approved),
            rejected_transfers=tuple(rejected),
            movement_flow_summaries=tuple(summaries),
            updated_allocator_state=tuple(
                (f"{node_id}:{movement_id}", self._movement_deficit_by_node_movement[(node_id, movement_id)])
                for node_id, movement_id in sorted(active_state_keys)
            ),
            allocation_traces=tuple(traces),
        )


class CityScaleV2LoadingEngine(GateAwareFractionalServiceLoadingEngine):
    """V2 engine with active-domain service and sparse count indexes."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._city_rates = self.effective_rate_service_config.capacity_by_link
        self._city_sparse_entries: dict[str, tuple[list[int], list[int]]] = {
            link_id: ([], []) for link_id in self.links
        }
        self._city_sparse_exits: dict[str, tuple[list[int], list[int]]] = {
            link_id: ([], []) for link_id in self.links
        }
        self._city_same_tick_touched: set[str] = set()
        self._city_receiving_last_finalized_tick: dict[str, int] = {
            link_id: 0 for link_id in self.links
        }
        self._city_receiving_active_this_tick: set[str] = set()
        self._city_eligible_work_link_ids: set[str] = set()
        self._city_eligibility_links_by_tick: dict[int, set[str]] = {}
        self._city_summary_ticks = 0
        self._city_summary_sending_total = 0
        self._city_summary_receiving_total = 0
        self._city_summary_event_total = 0
        self._city_summary_sending_max = 0
        self._city_summary_receiving_max = 0

    @property
    def city_scale_v2_summary(self) -> CityScaleV2Summary:
        return CityScaleV2Summary(
            ticks=self._city_summary_ticks,
            sending_domains_prepared=self._city_summary_sending_total,
            receiving_domains_prepared=self._city_summary_receiving_total,
            canonical_events_observed=self._city_summary_event_total,
            max_sending_domains_per_tick=self._city_summary_sending_max,
            max_receiving_domains_per_tick=self._city_summary_receiving_max,
            total_physical_links=len(self.links),
        )

    def materialize_all_receiving_credit(self) -> None:
        """Advance every lazy receiving account to the completed run tick once."""

        for link_id in self.links:
            last_tick = self._city_receiving_last_finalized_tick[link_id]
            elapsed = self.current_tick - last_tick
            if elapsed <= 0:
                continue
            rate = self._city_rates[link_id]
            carry = self._parity_receiving_capacity_carry_by_link_id[link_id]
            self._parity_receiving_capacity_carry_by_link_id[link_id] = min(
                carry + elapsed * rate,
                float(ceil(rate) + 1),
            )
            self._city_receiving_last_finalized_tick[link_id] = self.current_tick

    def _record_effective_rate_service_evidence(self, records) -> None:  # type: ignore[no-untyped-def]
        del records
        # The declared city-scale mode retains canonical physical events and a
        # deterministic aggregate service summary, not per-domain tick records.

    def _junction_allocation_inputs(
        self,
        *,
        transfer_requests: tuple[TransferRequest, ...],
        receiving_slots_by_downstream_link: Mapping[str, int],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
    ) -> tuple[JunctionAllocationInput, ...]:
        requests_by_node_id: dict[str, list[TransferRequest]] = {}
        fallback: list[TransferRequest] = []
        for request in transfer_requests:
            node = self._node_by_incoming_link_id.get(request.upstream_link_id)
            if node is None:
                fallback.append(request)
            else:
                requests_by_node_id.setdefault(node.node_id, []).append(request)
        result = [
            JunctionAllocationInput(
                node_id=node_id,
                junction_spec=self.nodes[node_id].junction_spec,
                transfer_requests=tuple(requests_by_node_id[node_id]),
                receiving_slots_by_downstream_link=receiving_slots_by_downstream_link,
                packet_ids_by_upstream_link=packet_ids_by_upstream_link,
                queued_downstream_by_packet_id=queued_downstream_by_packet_id,
                conflict_resource_capacity_by_id=MappingProxyType(
                    dict(self._conflict_resource_capacity_by_node_id.get(node_id, {}))
                ),
                lane_group_capacity_by_id=MappingProxyType(
                    dict(self._lane_group_capacity_by_node_id.get(node_id, {}))
                ),
                open_signal_group_ids=frozenset(self._open_signal_group_ids),
                closed_movement_ids=frozenset(
                    self._closed_movement_ids_by_node_id.get(node_id, set())
                ),
            )
            for node_id in sorted(requests_by_node_id)
        ]
        if fallback:
            result.append(
                JunctionAllocationInput(
                    node_id="__implicit_junction__",
                    junction_spec=None,
                    transfer_requests=tuple(fallback),
                    receiving_slots_by_downstream_link=receiving_slots_by_downstream_link,
                    packet_ids_by_upstream_link=packet_ids_by_upstream_link,
                    queued_downstream_by_packet_id=queued_downstream_by_packet_id,
                )
            )
        return tuple(result)

    def _extend_cumulative_boundary_count_views_to_current_tick(self) -> None:
        return

    def _increment_cumulative_boundary_count(
        self,
        counts_by_tick: dict[str, list[int]],
        link_id: str,
        tick: int,
    ) -> None:
        target = (
            self._city_sparse_entries
            if counts_by_tick is self._cumulative_link_entries_by_tick
            else self._city_sparse_exits
        )
        ticks, counts = target[link_id]
        if ticks and ticks[-1] == tick:
            counts[-1] += 1
        else:
            ticks.append(tick)
            counts.append((counts[-1] if counts else 0) + 1)

    def _cumulative_link_boundary_count(
        self,
        counts_by_tick: dict[str, list[int]],
        link_id: str,
        tick: int,
    ) -> int:
        if tick < 0:
            return 0
        target = (
            self._city_sparse_entries
            if counts_by_tick is self._cumulative_link_entries_by_tick
            else self._city_sparse_exits
        )
        ticks, counts = target[link_id]
        index = bisect_right(ticks, tick) - 1
        return 0 if index < 0 else counts[index]

    def _reset_same_tick_receiving_acceptance_counts(self) -> None:
        for link_id in self._city_same_tick_touched:
            self._same_tick_link_entries_by_link_id[link_id] = 0
        self._city_same_tick_touched.clear()

    def _apply_event_to_materialised_views(self, event: Event) -> None:
        super()._apply_event_to_materialised_views(event)
        if event.event_type == EventType.LINK_ENTRY:
            self._city_same_tick_touched.add(event.entity_id)
            eligibility_tick = event.physical_tick + self.links[event.entity_id].free_flow_ticks
            self._city_eligibility_links_by_tick.setdefault(
                eligibility_tick, set()
            ).add(event.entity_id)
        elif event.event_type == EventType.LINK_EXIT:
            link_id = event.entity_id
            if not self._packet_ids_by_link_id[link_id]:
                self._city_eligible_work_link_ids.discard(link_id)
            else:
                next_eligibility_tick = (
                    self._packet_entry_ticks_by_link_id[link_id][0]
                    + self.links[link_id].free_flow_ticks
                )
                if next_eligibility_tick > self.current_tick:
                    self._city_eligible_work_link_ids.discard(link_id)
                    self._city_eligibility_links_by_tick.setdefault(
                        next_eligibility_tick, set()
                    ).add(link_id)

    def _upstream_work_link_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._city_eligible_work_link_ids))

    def _prepare_parity_sending_capacity_for_tick(self) -> None:
        due_link_ids = self._city_eligibility_links_by_tick.pop(
            self.current_tick, set()
        )
        for link_id in due_link_ids:
            if self._packet_ids_by_link_id[link_id]:
                first_entry_tick = self._packet_entry_ticks_by_link_id[link_id][0]
                if first_entry_tick + self.links[link_id].free_flow_ticks <= self.current_tick:
                    self._city_eligible_work_link_ids.add(link_id)
        active_link_ids = tuple(sorted(self._city_eligible_work_link_ids))
        prepared: dict[str, _PreparedSendingAccount] = {}
        for link_id in active_link_ids:
            opening = self._parity_sending_capacity_carry_by_link_id[link_id]
            # V2's declared no-eligible-demand rule is add-zero/preserve-credit.
            # Avoid constructing a context/rate/evidence object for that exact
            # no-op state; canonical sending capacity is still explicitly zero.
            if not self._current_parity_eligible_packet_ids(link_id):
                self._parity_sending_integer_capacity_by_link_id[link_id] = 0
                self._parity_sending_capacity_carry_in_by_link_id[link_id] = opening
                continue
            context = self._gate_aware_service_context(link_id, self._city_rates[link_id])
            evaluated = evaluate_effective_service_rate(
                context, self.service_rate_multiplier_provider
            )
            available = opening + evaluated.effective_continuous_allowance
            whole = floor(available)
            closing = available - whole
            if not 0.0 <= closing < 1.0:
                raise GateAwareFractionalServiceIntegrityError(
                    "V2 sending fraction escaped [0,1)"
                )
            self._parity_sending_integer_capacity_by_link_id[link_id] = whole
            self._parity_sending_capacity_carry_in_by_link_id[link_id] = opening
            self._parity_sending_capacity_carry_by_link_id[link_id] = closing
            prepared[link_id] = _PreparedSendingAccount(
                context, evaluated, opening, whole, closing
            )
        self._prepared_effective_rate_sending_by_link = prepared

    def _prepare_parity_receiving_capacity_for_tick(self) -> None:
        self._city_receiving_active_this_tick.clear()

    def _receiving_slots_by_link(
        self,
        *,
        final_completion_counts_by_link: Mapping[str, int] | None = None,
        link_ids: Iterable[str] | None = None,
    ) -> dict[str, int]:
        selected = tuple(self.links if link_ids is None else sorted(set(link_ids)))
        for link_id in selected:
            self._city_prepare_receiving_link(link_id)
        return super()._receiving_slots_by_link(
            final_completion_counts_by_link=final_completion_counts_by_link,
            link_ids=selected,
        )

    def _city_prepare_receiving_link(self, link_id: str) -> None:
        if link_id in self._city_receiving_active_this_tick:
            return
        last_tick = self._city_receiving_last_finalized_tick[link_id]
        carry = self._parity_receiving_capacity_carry_by_link_id[link_id]
        skipped_ticks = max(self.current_tick - last_tick - 1, 0)
        if skipped_ticks:
            rate = self._city_rates[link_id]
            carry = min(carry + skipped_ticks * rate, float(ceil(rate) + 1))
        integer, _ = bounded_integer_receiving_capacity_carry(
            link_id=link_id,
            capacity_vehicles_per_tick=self._city_rates[link_id],
            carry_in=carry,
        )
        self._parity_receiving_capacity_carry_by_link_id[link_id] = carry
        self._parity_receiving_capacity_carry_in_by_link_id[link_id] = carry
        self._parity_receiving_capacity_carry_in_by_link_tick[
            (link_id, self.current_tick)
        ] = carry
        self._parity_receiving_integer_capacity_by_link_id[link_id] = integer
        self._city_receiving_active_this_tick.add(link_id)

    def _finalize_parity_receiving_capacity_for_tick(self) -> None:
        for link_id in self._city_receiving_active_this_tick:
            _, carry_out = bounded_integer_receiving_capacity_carry(
                link_id=link_id,
                capacity_vehicles_per_tick=self._city_rates[link_id],
                carry_in=self._parity_receiving_capacity_carry_in_by_link_id[link_id],
                actual_flow_packets=self._same_tick_link_entries_by_link_id[link_id],
            )
            self._parity_receiving_capacity_carry_by_link_id[link_id] = carry_out
            self._city_receiving_last_finalized_tick[link_id] = self.current_tick

    def step(self) -> None:
        event_start = len(self._event_log)
        LoadingEngine.step(self)
        sending_count = len(self._prepared_effective_rate_sending_by_link)
        receiving_count = len(self._city_receiving_active_this_tick)
        self._city_summary_ticks += 1
        self._city_summary_sending_total += sending_count
        self._city_summary_receiving_total += receiving_count
        self._city_summary_event_total += len(self._event_log) - event_start
        self._city_summary_sending_max = max(
            self._city_summary_sending_max, sending_count
        )
        self._city_summary_receiving_max = max(
            self._city_summary_receiving_max, receiving_count
        )
