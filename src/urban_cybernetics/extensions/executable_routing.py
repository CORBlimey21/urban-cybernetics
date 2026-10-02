# SPDX-License-Identifier: MPL-2.0
"""Opt-in executable-routing shell above the frozen loading kernel."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from types import MappingProxyType

from urban_cybernetics.core import (
    DemandDeclaration,
    EventType,
    LifecycleState,
    Packet,
)
from urban_cybernetics.loading.engine import (
    EventCacheConsistencyError,
    LoadingEngine,
)
from urban_cybernetics.loading.transfer_policy import TransferRequest
from urban_cybernetics.routing.instruction import (
    INAPPLICABLE_TERMINAL_PACKET,
    REJECTED_TERMINAL_PACKET,
    ApplicableInstructionResolver,
    InstructionHistoryRecord,
    InstructionResolution,
    RoutingInstruction,
    RoutingInstructionStore,
    legacy_route_intent_instruction,
)


EXECUTABLE_ROUTING_EXTENSION_VERSION = "executable-routing-extension-v1"
EXECUTABLE_ROUTING_SCHEMA_VERSION = "uc.executable-routing-extension.v1"


@dataclass(frozen=True, slots=True)
class ExecutableRoutingConfig:
    """Versioned switch and compatibility policy for executable routing."""

    compatibility_route_intent_adapter: bool = True
    extension_version: str = EXECUTABLE_ROUTING_EXTENSION_VERSION
    schema_version: str = EXECUTABLE_ROUTING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.extension_version != EXECUTABLE_ROUTING_EXTENSION_VERSION:
            raise ValueError(
                f"unsupported executable-routing extension: {self.extension_version}"
            )
        if self.schema_version != EXECUTABLE_ROUTING_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported executable-routing schema: {self.schema_version}"
            )

    @property
    def config_hash(self) -> str:
        serialised = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MovementInstructionEvidence:
    """Derived link between policy authority and canonical physical movement."""

    packet_id: str
    decision_tick: int
    upstream_link_id: str
    downstream_link_id: str
    link_exit_event_sequence: int
    link_entry_event_sequence: int
    resolution_id: str
    instruction_id: str
    instruction_version: int
    decision_artifact_id: str
    matches_original_route_intent: bool
    superseded_instruction_ids: tuple[str, ...]
    rejected_instruction_ids: tuple[str, ...]
    rejected_record_ids: tuple[str, ...]
    skipped_instruction_reasons: tuple[tuple[str, str], ...]
    selection_source: str


class ExecutableRoutingLoadingEngine(LoadingEngine):
    """Frozen physical loading with versioned instruction resolution at boundaries."""

    def __init__(
        self,
        *args: object,
        executable_routing_config: ExecutableRoutingConfig | None = None,
        instruction_store: RoutingInstructionStore | None = None,
        **kwargs: object,
    ) -> None:
        self.executable_routing_config = (
            executable_routing_config or ExecutableRoutingConfig()
        )
        self._instruction_store = instruction_store or RoutingInstructionStore()
        self._instruction_resolutions: list[InstructionResolution] = []
        self._resolution_cache: dict[
            tuple[str, int, str, int], InstructionResolution
        ] = {}
        self._movement_instruction_evidence: list[MovementInstructionEvidence] = []
        self._realised_route_by_packet_id: dict[str, list[str]] = {}
        super().__init__(*args, **kwargs)
        transitions = {
            (movement.upstream_link_id, movement.downstream_link_id)
            for node in self.nodes.values()
            for movement in node.junction_spec.movement_specs
        }
        self._instruction_resolver = ApplicableInstructionResolver(
            link_ids=self.links,
            supported_transitions=transitions,
        )

    @property
    def instruction_store(self) -> RoutingInstructionStore:
        return self._instruction_store

    @property
    def instruction_history(self) -> tuple[InstructionHistoryRecord, ...]:
        return self._instruction_store.history

    @property
    def instruction_resolutions(self) -> tuple[InstructionResolution, ...]:
        return tuple(self._instruction_resolutions)

    @property
    def movement_instruction_evidence(
        self,
    ) -> tuple[MovementInstructionEvidence, ...]:
        return tuple(self._movement_instruction_evidence)

    @property
    def executable_routing_evidence_hash(self) -> str:
        payload = {
            "schema_version": EXECUTABLE_ROUTING_SCHEMA_VERSION,
            "config_hash": self.executable_routing_config.config_hash,
            "instruction_history_hash": self._instruction_store.history_hash,
            "resolutions": [asdict(item) for item in self._instruction_resolutions],
            "movements": [
                asdict(item) for item in self._movement_instruction_evidence
            ],
        }
        serialised = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialised.encode("utf-8")).hexdigest()

    def submit_instruction(
        self,
        instruction: RoutingInstruction,
    ) -> InstructionHistoryRecord:
        """Receive an authority instruction without granting physical execution."""

        if instruction.packet_id not in self._packets:
            raise KeyError(f"unknown packet_id: {instruction.packet_id}")
        state = self._packets[instruction.packet_id].lifecycle_state
        rejection_reason = (
            REJECTED_TERMINAL_PACKET
            if state in (LifecycleState.COMPLETED, LifecycleState.CANCELLED)
            else None
        )
        record = self._instruction_store.record(
            instruction,
            recorded_tick=self.current_tick,
            rejection_reason=rejection_reason,
        )
        self._discard_cached_resolutions(instruction.packet_id)
        if rejection_reason is not None:
            self._record_terminal_inapplicability(instruction)
        return record

    def _instantiate_now(self, demand: DemandDeclaration) -> Packet:
        packet = super()._instantiate_now(demand)
        self._realised_route_by_packet_id[packet.packet_id] = [demand.route_intent[0]]
        if self.executable_routing_config.compatibility_route_intent_adapter:
            self._instruction_store.record(
                legacy_route_intent_instruction(
                    packet_id=packet.packet_id,
                    route_intent=packet.route_intent,
                    issue_tick=self.current_tick,
                ),
                recorded_tick=self.current_tick,
            )
        return packet

    def _discard_cached_resolutions(self, packet_id: str) -> None:
        self._resolution_cache = {
            key: value
            for key, value in self._resolution_cache.items()
            if key[0] != packet_id
        }

    def _record_terminal_inapplicability(
        self,
        instruction: RoutingInstruction,
    ) -> None:
        current_link_id = self._terminal_link_id(instruction.packet_id)
        resolution = self._instruction_resolver.resolve(
            store=self._instruction_store,
            packet_id=instruction.packet_id,
            decision_tick=self.current_tick,
            current_link_id=current_link_id,
            realised_route=tuple(
                self._realised_route_by_packet_id.get(instruction.packet_id, ())
            ),
            original_route_intent=self._packets[instruction.packet_id].route_intent,
            terminal=True,
            allow_route_intent_adapter=(
                self.executable_routing_config.compatibility_route_intent_adapter
            ),
        )
        if resolution.reason != INAPPLICABLE_TERMINAL_PACKET:
            raise EventCacheConsistencyError("terminal instruction resolved as active")
        self._instruction_resolutions.append(resolution)

    def _terminal_link_id(self, packet_id: str) -> str:
        realised = self._realised_route_by_packet_id.get(packet_id, ())
        return realised[-1] if realised else "__terminal__"

    def _resolution_for_boundary(self, packet_id: str) -> InstructionResolution:
        current_link_id = self._current_link_ids[packet_id]
        realised_route = tuple(self._realised_route_by_packet_id[packet_id])
        key = (packet_id, self.current_tick, current_link_id, len(realised_route))
        cached = self._resolution_cache.get(key)
        if cached is not None:
            return cached
        resolution = self._instruction_resolver.resolve(
            store=self._instruction_store,
            packet_id=packet_id,
            decision_tick=self.current_tick,
            current_link_id=current_link_id,
            realised_route=realised_route,
            original_route_intent=self._packets[packet_id].route_intent,
            allow_route_intent_adapter=(
                self.executable_routing_config.compatibility_route_intent_adapter
            ),
        )
        self._resolution_cache[key] = resolution
        self._instruction_resolutions.append(resolution)
        return resolution

    def _next_link_id(self, packet_id: str) -> str | None:
        resolution = self._resolution_for_boundary(packet_id)
        if not resolution.is_applicable:
            return None
        return resolution.intended_next_link_id

    def _final_completion_packet_ids_by_link(
        self,
        *,
        passable_transfer_packet_ids: frozenset[str] = frozenset(),
    ) -> dict[str, tuple[str, ...]]:
        completion_packet_ids_by_link: dict[str, tuple[str, ...]] = {}
        for link_id in self._upstream_work_link_ids():
            sending_view = self._current_link_sending_view(link_id)
            packet_ids: list[str] = []
            for packet_id in sending_view.sendable_packet_ids:
                if packet_id in self._queued_downstream_by_packet_id:
                    if packet_id in passable_transfer_packet_ids:
                        continue
                    break
                resolution = self._resolution_for_boundary(packet_id)
                if not resolution.is_applicable:
                    break
                if resolution.intended_next_link_id is not None:
                    if packet_id in passable_transfer_packet_ids:
                        continue
                    break
                packet_ids.append(packet_id)
            if packet_ids:
                completion_packet_ids_by_link[link_id] = tuple(packet_ids)
        return completion_packet_ids_by_link

    def _transfer_candidates(
        self,
        consumed_sending_slots_by_link: dict[str, int],
        *,
        final_completion_packet_ids_by_link: Mapping[str, tuple[str, ...]] | None = None,
    ) -> tuple[TransferRequest, ...]:
        self._reconcile_queued_instruction_updates()
        candidates = super()._transfer_candidates(
            consumed_sending_slots_by_link,
            final_completion_packet_ids_by_link=final_completion_packet_ids_by_link,
        )
        return tuple(
            candidate
            for candidate in candidates
            if (
                (resolution := self._resolution_for_boundary(candidate.packet_id))
            ).is_applicable
            and resolution.intended_next_link_id == candidate.downstream_link_id
        )

    def _reconcile_queued_instruction_updates(self) -> None:
        """Release only FIFO heads whose executable movement has changed."""

        for upstream_link_id in sorted(self._queued_packet_ids_by_upstream_link):
            upstream_queue = self._queued_packet_ids_by_upstream_link[upstream_link_id]
            while upstream_queue:
                packet_id = upstream_queue[0]
                resolution = self._resolution_for_boundary(packet_id)
                if not resolution.is_applicable:
                    break
                old_downstream = self._queued_downstream_by_packet_id[packet_id]
                if resolution.intended_next_link_id == old_downstream:
                    break
                old_boundary = self._boundary_id(upstream_link_id, old_downstream)
                self.append_event(packet_id, EventType.QUEUE_EXIT, old_boundary)
                self._set_lifecycle_state(packet_id, LifecycleState.IN_TRANSIT)

    def _prevalidate_link_to_link_transfer(
        self,
        *,
        packet_id: str,
        upstream_link_id: str,
        downstream_link_id: str,
        queue_boundary_id: str | None = None,
    ) -> None:
        """Apply frozen physical checks against the resolved instruction."""

        packet_index = self._prevalidate_active_link_departure(
            packet_id, upstream_link_id
        )
        if downstream_link_id not in self.links:
            raise KeyError(f"unknown downstream link_id: {downstream_link_id}")
        resolution = self._resolution_for_boundary(packet_id)
        if not resolution.is_applicable:
            raise EventCacheConsistencyError(
                f"packet_id {packet_id} has no applicable routing instruction: "
                f"{resolution.reason}"
            )
        if resolution.intended_next_link_id != downstream_link_id:
            raise EventCacheConsistencyError(
                f"packet_id {packet_id} instruction expects downstream link "
                f"{resolution.intended_next_link_id}, not {downstream_link_id}"
            )
        queued_boundary_id = self._queue_boundary_for_packet(packet_id)
        if queue_boundary_id is None:
            if queued_boundary_id is not None:
                raise EventCacheConsistencyError(
                    f"queued packet_id {packet_id} requires queue-aware transfer"
                )
            if self._packets[packet_id].lifecycle_state != LifecycleState.IN_TRANSIT:
                raise EventCacheConsistencyError(
                    f"packet_id {packet_id} is not in transit before transfer"
                )
            self._prevalidated_link_exit_indices[
                (packet_id, upstream_link_id)
            ] = packet_index
            return

        expected_boundary_id = self._boundary_id(
            upstream_link_id, downstream_link_id
        )
        if queue_boundary_id != expected_boundary_id:
            raise EventCacheConsistencyError(
                f"packet_id {packet_id} queue boundary is {queue_boundary_id}, "
                f"expected {expected_boundary_id}"
            )
        if queued_boundary_id != queue_boundary_id:
            raise EventCacheConsistencyError(
                f"packet_id {packet_id} queue cache does not match {queue_boundary_id}"
            )
        queue = self._queues.get(queue_boundary_id)
        if not queue or queue[0] != packet_id:
            raise EventCacheConsistencyError(
                f"packet_id {packet_id} is not first in queue {queue_boundary_id}"
            )
        upstream_queue = self._queued_packet_ids_by_upstream_link.get(
            upstream_link_id
        )
        if not upstream_queue or upstream_queue[0] != packet_id:
            raise EventCacheConsistencyError(
                f"packet_id {packet_id} is not first in upstream queue "
                f"{upstream_link_id}"
            )
        if self._packets[packet_id].lifecycle_state != LifecycleState.QUEUED:
            raise EventCacheConsistencyError(
                f"packet_id {packet_id} is not queued before queued transfer"
            )
        self._prevalidated_link_exit_indices[
            (packet_id, upstream_link_id)
        ] = packet_index

    def _transfer_packet_between_links(
        self,
        packet_id: str,
        upstream_link_id: str,
        downstream_link_id: str,
        *,
        prevalidated: bool = False,
    ) -> None:
        resolution = self._resolution_for_boundary(packet_id)
        event_count_before = len(self._event_log)
        super()._transfer_packet_between_links(
            packet_id,
            upstream_link_id,
            downstream_link_id,
            prevalidated=prevalidated,
        )
        self._realised_route_by_packet_id[packet_id].append(downstream_link_id)
        assert resolution.instruction_id is not None
        assert resolution.instruction_version is not None
        assert resolution.decision_artifact_id is not None
        assert resolution.matches_original_route_intent is not None
        assert resolution.selection_source is not None
        self._movement_instruction_evidence.append(
            MovementInstructionEvidence(
                packet_id=packet_id,
                decision_tick=self.current_tick,
                upstream_link_id=upstream_link_id,
                downstream_link_id=downstream_link_id,
                link_exit_event_sequence=event_count_before,
                link_entry_event_sequence=event_count_before + 1,
                resolution_id=resolution.resolution_id,
                instruction_id=resolution.instruction_id,
                instruction_version=resolution.instruction_version,
                decision_artifact_id=resolution.decision_artifact_id,
                matches_original_route_intent=(
                    resolution.matches_original_route_intent
                ),
                superseded_instruction_ids=(
                    resolution.superseded_instruction_ids
                ),
                rejected_instruction_ids=resolution.rejected_instruction_ids,
                rejected_record_ids=resolution.rejected_record_ids,
                skipped_instruction_reasons=(
                    resolution.skipped_instruction_reasons
                ),
                selection_source=resolution.selection_source,
            )
        )
        self._discard_cached_resolutions(packet_id)

    def _prevalidate_cancellation(self, packet_id: str) -> None:
        """Validate physical cancellation without consulting route policy."""

        if packet_id not in self._packets:
            raise KeyError(f"unknown packet_id: {packet_id}")
        state = self._packets[packet_id].lifecycle_state
        if state in (LifecycleState.COMPLETED, LifecycleState.CANCELLED):
            raise ValueError(f"packet_id {packet_id} is already terminal: {state.value}")
        link_id = self._current_link_ids.get(packet_id)
        if link_id is None:
            raise EventCacheConsistencyError(
                f"active packet_id {packet_id} has no current link"
            )
        boundary_id = self._queue_boundary_for_packet(packet_id)
        if state == LifecycleState.QUEUED:
            if boundary_id is None:
                raise EventCacheConsistencyError(
                    f"queued packet_id {packet_id} has no queue boundary"
                )
            packet_index = self._prevalidate_active_link_departure(packet_id, link_id)
            queue = self._queues.get(boundary_id)
            upstream_queue = self._queued_packet_ids_by_upstream_link.get(link_id)
            if not queue or queue[0] != packet_id:
                raise EventCacheConsistencyError(
                    f"packet_id {packet_id} is not first in queue {boundary_id}"
                )
            if not upstream_queue or upstream_queue[0] != packet_id:
                raise EventCacheConsistencyError(
                    f"packet_id {packet_id} is not first in upstream queue {link_id}"
                )
        else:
            packet_index = self._prevalidate_active_link_departure(packet_id, link_id)
            if boundary_id is not None:
                raise EventCacheConsistencyError(
                    f"in-transit packet_id {packet_id} remains in a queue"
                )
        self._prevalidated_link_exit_indices[(packet_id, link_id)] = packet_index

    def _route_indices_implied_by_events(self) -> dict[str, int]:
        """Use realised entry order; declared route intent is not rewritten."""

        route_entry_counts: dict[str, int] = {}
        route_indices: dict[str, int] = {}
        for event in self._event_log:
            if event.event_type != EventType.LINK_ENTRY:
                continue
            index = route_entry_counts.get(event.packet_id, 0)
            if index == 0 and event.entity_id != self._packets[
                event.packet_id
            ].route_intent[0]:
                raise EventCacheConsistencyError(
                    f"packet_id {event.packet_id} did not enter its declared origin link"
                )
            route_indices[event.packet_id] = index
            route_entry_counts[event.packet_id] = index + 1
        return route_indices

    def check_event_cache_consistency(self) -> bool:
        """Extend frozen cache checks to realised-route and audit evidence caches."""

        super().check_event_cache_consistency()
        event_routes: dict[str, list[str]] = {}
        transfer_entry_sequences: set[int] = set()
        for event in self._event_log:
            if event.event_type != EventType.LINK_ENTRY:
                continue
            if event.packet_id in event_routes:
                transfer_entry_sequences.add(event.sequence_number)
            event_routes.setdefault(event.packet_id, []).append(event.entity_id)
        if event_routes != self._realised_route_by_packet_id:
            raise EventCacheConsistencyError(
                "realised-route cache does not match canonical link-entry events"
            )

        evidence_entry_sequences: set[int] = set()
        for evidence in self._movement_instruction_evidence:
            try:
                exit_event = self._event_log[evidence.link_exit_event_sequence]
                entry_event = self._event_log[evidence.link_entry_event_sequence]
            except IndexError as exc:
                raise EventCacheConsistencyError(
                    "movement-instruction evidence references a missing event"
                ) from exc
            if (
                exit_event.event_type != EventType.LINK_EXIT
                or entry_event.event_type != EventType.LINK_ENTRY
                or exit_event.packet_id != evidence.packet_id
                or entry_event.packet_id != evidence.packet_id
                or exit_event.entity_id != evidence.upstream_link_id
                or entry_event.entity_id != evidence.downstream_link_id
            ):
                raise EventCacheConsistencyError(
                    "movement-instruction evidence disagrees with physical events"
                )
            evidence_entry_sequences.add(evidence.link_entry_event_sequence)
        if evidence_entry_sequences != transfer_entry_sequences:
            raise EventCacheConsistencyError(
                "not every realised link-to-link movement has instruction evidence"
            )
        return True

    @property
    def realised_routes(self) -> Mapping[str, tuple[str, ...]]:
        return MappingProxyType(
            {
                packet_id: tuple(route)
                for packet_id, route in self._realised_route_by_packet_id.items()
            }
        )
