"""V2 gate-aware fractional service above the frozen loading kernel.

V1 remains a clock-driven transient-opportunity policy.  V2 owns one sending
account per physical link, accrues only while at least one currently relevant
discharge is uncontrolled or green, and preserves a bounded fractional
remainder through red and idle periods.  Receiving retains the existing
bounded de Souza recurrence and is never signal-gated.

The effective-rate evaluator is intentionally separate from accumulation:

    base allowance * control availability * dynamic multiplier

V2 supplies a constant-one multiplier.  A future policy may supply a dynamic
multiplier without changing account identity, accumulation, allocation, or
physical execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor
from typing import Mapping, Protocol, Self

from urban_cybernetics.compiler.model import stable_hash
from urban_cybernetics.core import EventType
from urban_cybernetics.loading.engine import LoadingEngine


GATE_AWARE_FRACTIONAL_SERVICE_VERSION = "uc.gate-aware-fractional-service.v2"
GATE_AWARE_FRACTIONAL_SERVICE_MODE = "gate_aware_fractional_service_v2"
CONSTANT_ONE_MULTIPLIER_ID = "constant_service_rate_multiplier:1.0:v1"
EFFECTIVE_RATE_SERVICE_EVIDENCE_VERSION = (
    "uc.effective-rate-fractional-service-evidence.v1"
)


class GateAwareFractionalServiceIntegrityError(ValueError):
    """Raised for malformed V2 configuration or evidence."""


@dataclass(frozen=True, slots=True)
class ServiceRateContext:
    """Policy-neutral inputs evaluated before fractional accumulation."""

    tick: int
    service_account_id: str
    service_domain_id: str
    service_domain_type: str
    base_continuous_rate_packets_per_tick: float
    control_gate_state: str
    control_availability_factor: float
    relevant_movement_ids: tuple[str, ...]
    relevant_packet_ids: tuple[str, ...]


class ServiceRateMultiplierProvider(Protocol):
    """Seam for a later time-varying effective-rate policy."""

    @property
    def provider_id(self) -> str: ...

    @property
    def configuration_hash(self) -> str: ...

    def multiplier(self, context: ServiceRateContext) -> float: ...


class EffectiveRateServiceConfig(Protocol):
    """Minimum policy contract consumed by the reusable accumulator."""

    @property
    def capacity_by_link(self) -> dict[str, float]: ...

    @property
    def config_hash(self) -> str: ...

    dynamic_multiplier_provider_id: str
    enabled_unused_whole_policy: str
    receiving_policy: str
    version: str


@dataclass(frozen=True, slots=True)
class ConstantServiceRateMultiplier:
    """V2 multiplier: control availability is the only rate modulation."""

    value: float = 1.0
    provider_id: str = CONSTANT_ONE_MULTIPLIER_ID

    def __post_init__(self) -> None:
        if self.value != 1.0 or self.provider_id != CONSTANT_ONE_MULTIPLIER_ID:
            raise GateAwareFractionalServiceIntegrityError(
                "V2 requires the constant-one dynamic multiplier"
            )

    @property
    def configuration_hash(self) -> str:
        return stable_hash(
            "service-rate-multiplier-provider",
            {"provider_id": self.provider_id, "value": self.value},
        )

    def multiplier(self, context: ServiceRateContext) -> float:
        del context
        return self.value


@dataclass(frozen=True, slots=True)
class EffectiveServiceRate:
    """One generic base×control×multiplier evaluation."""

    base_continuous_allowance: float
    control_availability_factor: float
    dynamic_rate_multiplier: float
    effective_continuous_allowance: float


def evaluate_effective_service_rate(
    context: ServiceRateContext,
    provider: ServiceRateMultiplierProvider,
) -> EffectiveServiceRate:
    multiplier = float(provider.multiplier(context))
    if not 0.0 <= multiplier <= 1.0:
        raise GateAwareFractionalServiceIntegrityError(
            "dynamic service-rate multiplier must be in [0, 1]"
        )
    availability = context.control_availability_factor
    if availability not in (0.0, 1.0):
        raise GateAwareFractionalServiceIntegrityError(
            "V2 control availability factor must be binary"
        )
    base = context.base_continuous_rate_packets_per_tick
    effective = base * availability * multiplier
    return EffectiveServiceRate(base, availability, multiplier, effective)


@dataclass(frozen=True, slots=True)
class GateAwareFractionalServiceConfig:
    """Immutable V2 link rates and account/retention interpretation."""

    continuous_capacity_by_link: tuple[tuple[str, float], ...]
    service_domain_ownership: str = "one_shared_sending_account_per_physical_link"
    enabling_policy: str = "any_relevant_uncontrolled_or_green_movement"
    demand_relevance_policy: str = "free_flow_eligible_packet_with_next_discharge"
    disabled_policy: str = "add_zero_preserve_fractional_remainder"
    idle_policy: str = "add_zero_preserve_bounded_fractional_remainder"
    enabled_unused_whole_policy: str = "expire_after_enabled_tick"
    receiving_policy: str = "ungated_desouza_bounded_credit"
    dynamic_multiplier_provider_id: str = CONSTANT_ONE_MULTIPLIER_ID
    version: str = GATE_AWARE_FRACTIONAL_SERVICE_VERSION

    def __post_init__(self) -> None:
        if self.version != GATE_AWARE_FRACTIONAL_SERVICE_VERSION:
            raise GateAwareFractionalServiceIntegrityError("unsupported V2 policy")
        expected = {
            "service_domain_ownership": "one_shared_sending_account_per_physical_link",
            "enabling_policy": "any_relevant_uncontrolled_or_green_movement",
            "demand_relevance_policy": "free_flow_eligible_packet_with_next_discharge",
            "disabled_policy": "add_zero_preserve_fractional_remainder",
            "idle_policy": "add_zero_preserve_bounded_fractional_remainder",
            "enabled_unused_whole_policy": "expire_after_enabled_tick",
            "receiving_policy": "ungated_desouza_bounded_credit",
            "dynamic_multiplier_provider_id": CONSTANT_ONE_MULTIPLIER_ID,
        }
        actual = {name: getattr(self, name) for name in expected}
        if actual != expected:
            raise GateAwareFractionalServiceIntegrityError(
                "V2 policy metadata must exactly describe implemented semantics"
            )
        normalised = tuple(
            sorted((str(link_id), float(rate)) for link_id, rate in self.continuous_capacity_by_link)
        )
        if any(not link_id or rate < 0 for link_id, rate in normalised):
            raise GateAwareFractionalServiceIntegrityError(
                "V2 link rates require non-empty IDs and non-negative values"
            )
        if len({link_id for link_id, _ in normalised}) != len(normalised):
            raise GateAwareFractionalServiceIntegrityError("duplicate V2 link rate")
        object.__setattr__(self, "continuous_capacity_by_link", normalised)

    @property
    def mode(self) -> str:
        return GATE_AWARE_FRACTIONAL_SERVICE_MODE

    @property
    def capacity_by_link(self) -> dict[str, float]:
        return dict(self.continuous_capacity_by_link)

    @property
    def config_hash(self) -> str:
        return stable_hash("gate-aware-fractional-service-config", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "mode": self.mode,
            "continuous_capacity_by_link": [list(item) for item in self.continuous_capacity_by_link],
            "service_domain_ownership": self.service_domain_ownership,
            "enabling_policy": self.enabling_policy,
            "demand_relevance_policy": self.demand_relevance_policy,
            "disabled_policy": self.disabled_policy,
            "idle_policy": self.idle_policy,
            "enabled_unused_whole_policy": self.enabled_unused_whole_policy,
            "receiving_policy": self.receiving_policy,
            "dynamic_multiplier_provider_id": self.dynamic_multiplier_provider_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        if payload.get("mode") != GATE_AWARE_FRACTIONAL_SERVICE_MODE:
            raise GateAwareFractionalServiceIntegrityError("V2 mode mismatch")
        return cls(
            continuous_capacity_by_link=tuple(
                (str(link_id), float(rate))
                for link_id, rate in payload["continuous_capacity_by_link"]  # type: ignore[misc]
            ),
            service_domain_ownership=str(payload["service_domain_ownership"]),
            enabling_policy=str(payload["enabling_policy"]),
            demand_relevance_policy=str(payload["demand_relevance_policy"]),
            disabled_policy=str(payload["disabled_policy"]),
            idle_policy=str(payload["idle_policy"]),
            enabled_unused_whole_policy=str(payload["enabled_unused_whole_policy"]),
            receiving_policy=str(payload["receiving_policy"]),
            dynamic_multiplier_provider_id=str(payload["dynamic_multiplier_provider_id"]),
            version=str(payload["version"]),
        )


@dataclass(frozen=True, slots=True)
class EffectiveRateFractionalServiceEvidence:
    """Policy-neutral evidence reusable by V2 and a later multiplier policy."""

    tick: int
    service_account_id: str
    service_domain_id: str
    service_domain_type: str
    base_continuous_rate_packets_per_tick: float
    tick_duration_seconds: float
    base_continuous_allowance: float
    control_gate_state: str
    control_availability_factor: float
    dynamic_rate_multiplier: float
    effective_continuous_allowance: float
    opening_credit: float
    opening_fractional_credit: float
    whole_service_exposed: int
    physically_consumed_service: int
    expired_unconsumed_whole_opportunity: int
    retained_unused_whole_credit: float
    closing_credit: float
    closing_fractional_credit: float
    credit_cap: float
    relevant_movement_ids: tuple[str, ...]
    relevant_packet_ids: tuple[str, ...]
    consumed_packet_ids: tuple[str, ...]
    retention_policy: str
    multiplier_provider_id: str
    multiplier_configuration_hash: str
    configuration_hash: str
    executable_semantic_hash: str
    policy_id: str = GATE_AWARE_FRACTIONAL_SERVICE_VERSION
    evidence_schema_version: str = EFFECTIVE_RATE_SERVICE_EVIDENCE_VERSION
    evidence_hash: str = ""

    def __post_init__(self) -> None:
        if not self.policy_id:
            raise GateAwareFractionalServiceIntegrityError("service policy ID is required")
        if self.evidence_schema_version != EFFECTIVE_RATE_SERVICE_EVIDENCE_VERSION:
            raise GateAwareFractionalServiceIntegrityError(
                "effective-rate evidence schema mismatch"
            )
        if self.service_domain_type not in ("link_sending", "link_receiving"):
            raise GateAwareFractionalServiceIntegrityError("unknown V2 service domain")
        if self.tick <= 0 or self.whole_service_exposed < 0:
            raise GateAwareFractionalServiceIntegrityError("invalid V2 evidence count")
        if not 0 <= self.physically_consumed_service <= self.whole_service_exposed:
            raise GateAwareFractionalServiceIntegrityError("V2 consumption exceeds exposure")
        if not 0.0 <= self.opening_fractional_credit < 1.0:
            raise GateAwareFractionalServiceIntegrityError("opening fraction is unbounded")
        if not 0.0 <= self.closing_fractional_credit < 1.0:
            raise GateAwareFractionalServiceIntegrityError("closing fraction is unbounded")
        for field_name in (
            "relevant_movement_ids",
            "relevant_packet_ids",
            "consumed_packet_ids",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        expected = stable_hash("effective-rate-fractional-service-evidence", self._payload())
        if self.evidence_hash and self.evidence_hash != expected:
            raise GateAwareFractionalServiceIntegrityError("V2 evidence hash mismatch")
        object.__setattr__(self, "evidence_hash", expected)

    @property
    def account_id(self) -> str:
        return self.service_account_id

    @property
    def resource_type(self) -> str:
        return self.service_domain_type

    @property
    def continuous_allowance_added(self) -> float:
        return self.effective_continuous_allowance

    @property
    def available_whole_service(self) -> int:
        return self.whole_service_exposed

    @property
    def consumed_service(self) -> int:
        return self.physically_consumed_service

    def _payload(self) -> dict[str, object]:
        return {
            "evidence_schema_version": self.evidence_schema_version,
            "policy_id": self.policy_id,
            "tick": self.tick,
            "service_account_id": self.service_account_id,
            "service_domain_id": self.service_domain_id,
            "service_domain_type": self.service_domain_type,
            "base_continuous_rate_packets_per_tick": self.base_continuous_rate_packets_per_tick,
            "tick_duration_seconds": self.tick_duration_seconds,
            "base_continuous_allowance": self.base_continuous_allowance,
            "control_gate_state": self.control_gate_state,
            "control_availability_factor": self.control_availability_factor,
            "dynamic_rate_multiplier": self.dynamic_rate_multiplier,
            "effective_continuous_allowance": self.effective_continuous_allowance,
            "opening_credit": self.opening_credit,
            "opening_fractional_credit": self.opening_fractional_credit,
            "whole_service_exposed": self.whole_service_exposed,
            "physically_consumed_service": self.physically_consumed_service,
            "expired_unconsumed_whole_opportunity": self.expired_unconsumed_whole_opportunity,
            "retained_unused_whole_credit": self.retained_unused_whole_credit,
            "closing_credit": self.closing_credit,
            "closing_fractional_credit": self.closing_fractional_credit,
            "credit_cap": self.credit_cap,
            "relevant_movement_ids": list(self.relevant_movement_ids),
            "relevant_packet_ids": list(self.relevant_packet_ids),
            "consumed_packet_ids": list(self.consumed_packet_ids),
            "retention_policy": self.retention_policy,
            "multiplier_provider_id": self.multiplier_provider_id,
            "multiplier_configuration_hash": self.multiplier_configuration_hash,
            "configuration_hash": self.configuration_hash,
            "executable_semantic_hash": self.executable_semantic_hash,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "evidence_hash": self.evidence_hash}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            tick=int(payload["tick"]),
            service_account_id=str(payload["service_account_id"]),
            service_domain_id=str(payload["service_domain_id"]),
            service_domain_type=str(payload["service_domain_type"]),
            base_continuous_rate_packets_per_tick=float(payload["base_continuous_rate_packets_per_tick"]),
            tick_duration_seconds=float(payload["tick_duration_seconds"]),
            base_continuous_allowance=float(payload["base_continuous_allowance"]),
            control_gate_state=str(payload["control_gate_state"]),
            control_availability_factor=float(payload["control_availability_factor"]),
            dynamic_rate_multiplier=float(payload["dynamic_rate_multiplier"]),
            effective_continuous_allowance=float(payload["effective_continuous_allowance"]),
            opening_credit=float(payload["opening_credit"]),
            opening_fractional_credit=float(payload["opening_fractional_credit"]),
            whole_service_exposed=int(payload["whole_service_exposed"]),
            physically_consumed_service=int(payload["physically_consumed_service"]),
            expired_unconsumed_whole_opportunity=int(payload["expired_unconsumed_whole_opportunity"]),
            retained_unused_whole_credit=float(payload["retained_unused_whole_credit"]),
            closing_credit=float(payload["closing_credit"]),
            closing_fractional_credit=float(payload["closing_fractional_credit"]),
            credit_cap=float(payload["credit_cap"]),
            relevant_movement_ids=tuple(str(item) for item in payload["relevant_movement_ids"]),  # type: ignore[index]
            relevant_packet_ids=tuple(str(item) for item in payload["relevant_packet_ids"]),  # type: ignore[index]
            consumed_packet_ids=tuple(str(item) for item in payload["consumed_packet_ids"]),  # type: ignore[index]
            retention_policy=str(payload["retention_policy"]),
            multiplier_provider_id=str(payload["multiplier_provider_id"]),
            multiplier_configuration_hash=str(payload["multiplier_configuration_hash"]),
            configuration_hash=str(payload["configuration_hash"]),
            executable_semantic_hash=str(payload["executable_semantic_hash"]),
            policy_id=str(payload["policy_id"]),
            evidence_schema_version=str(payload["evidence_schema_version"]),
            evidence_hash=str(payload.get("evidence_hash", "")),
        )


@dataclass(frozen=True, slots=True)
class _PreparedSendingAccount:
    context: ServiceRateContext
    rate: EffectiveServiceRate
    opening_fractional_credit: float
    whole_service_exposed: int
    closing_fractional_credit: float


class EffectiveRateFractionalServiceMixin:
    """Generic effective-rate accumulator used by V2 and intended for V3 reuse."""

    def __init__(
        self,
        *args: object,
        effective_rate_service_config: EffectiveRateServiceConfig,
        service_rate_multiplier_provider: ServiceRateMultiplierProvider | None = None,
        executable_semantic_hash: str = "unspecified",
        **kwargs: object,
    ) -> None:
        provider = service_rate_multiplier_provider or ConstantServiceRateMultiplier()
        if provider.provider_id != effective_rate_service_config.dynamic_multiplier_provider_id:
            raise GateAwareFractionalServiceIntegrityError(
                "effective-rate multiplier provider identity mismatch"
            )
        self.effective_rate_service_config = effective_rate_service_config
        self.service_rate_multiplier_provider = provider
        self.effective_rate_executable_semantic_hash = executable_semantic_hash
        self._effective_rate_service_evidence: list[
            EffectiveRateFractionalServiceEvidence
        ] = []
        self._prepared_effective_rate_sending_by_link: dict[
            str, _PreparedSendingAccount
        ] = {}
        rates = effective_rate_service_config.capacity_by_link
        for reserved in (
            "parity_sending_capacity_vehicles_per_tick_by_link",
            "parity_receiving_capacity_vehicles_per_tick_by_link",
        ):
            if reserved in kwargs:
                raise GateAwareFractionalServiceIntegrityError(f"V2 owns {reserved}")
        kwargs["parity_sending_capacity_vehicles_per_tick_by_link"] = rates
        kwargs["parity_receiving_capacity_vehicles_per_tick_by_link"] = rates
        super().__init__(*args, **kwargs)  # type: ignore[misc]
        if set(rates) != set(self.links):  # type: ignore[attr-defined]
            raise GateAwareFractionalServiceIntegrityError(
                "V2 continuous capacity must cover executable links exactly"
            )

    @property
    def effective_rate_fractional_service_evidence(
        self,
    ) -> tuple[EffectiveRateFractionalServiceEvidence, ...]:
        return tuple(self._effective_rate_service_evidence)

    @property
    def effective_rate_fractional_service_evidence_hash(self) -> str:
        return stable_hash(
            "effective-rate-fractional-service-run-evidence",
            {
                "configuration_hash": self.effective_rate_service_config.config_hash,
                "multiplier_configuration_hash": self.service_rate_multiplier_provider.configuration_hash,
                "executable_semantic_hash": self.effective_rate_executable_semantic_hash,
                "records": [
                    item.to_dict() for item in self._effective_rate_service_evidence
                ],
            },
        )

    # Compatibility shape lets existing forensic/replay machinery consume V2
    # without treating V2 records as V1 records or changing physical events.
    @property
    def fractional_service_credit_evidence(self) -> tuple[EffectiveRateFractionalServiceEvidence, ...]:
        return self.effective_rate_fractional_service_evidence

    @property
    def fractional_service_credit_evidence_hash(self) -> str:
        return self.effective_rate_fractional_service_evidence_hash

    def _record_effective_rate_service_evidence(
        self,
        records: tuple[EffectiveRateFractionalServiceEvidence, ...],
    ) -> None:
        """Policy hook for retention/digest modes; V2 retains every record."""

        self._effective_rate_service_evidence.extend(records)

    def _uses_parity_sending(self) -> bool:
        return True

    def _uses_parity_receiving(self) -> bool:
        return True

    def _prepare_parity_sending_capacity_for_tick(self) -> None:
        rates = self.effective_rate_service_config.capacity_by_link
        integers: dict[str, int] = {}
        opening_by_link: dict[str, float] = {}
        closing_by_link: dict[str, float] = {}
        prepared: dict[str, _PreparedSendingAccount] = {}
        for link_id in sorted(self.links):  # type: ignore[attr-defined]
            opening = self._parity_sending_capacity_carry_by_link_id[link_id]  # type: ignore[attr-defined]
            context = self._gate_aware_service_context(link_id, rates[link_id])
            evaluated = evaluate_effective_service_rate(
                context, self.service_rate_multiplier_provider
            )
            available = opening + evaluated.effective_continuous_allowance
            whole = floor(available)
            closing = available - whole
            if not 0.0 <= closing < 1.0:
                raise GateAwareFractionalServiceIntegrityError("V2 sending fraction escaped [0,1)")
            integers[link_id] = whole
            opening_by_link[link_id] = opening
            closing_by_link[link_id] = closing
            prepared[link_id] = _PreparedSendingAccount(
                context, evaluated, opening, whole, closing
            )
        self._parity_sending_integer_capacity_by_link_id = integers  # type: ignore[attr-defined]
        self._parity_sending_capacity_carry_in_by_link_id = opening_by_link  # type: ignore[attr-defined]
        self._parity_sending_capacity_carry_by_link_id = closing_by_link  # type: ignore[attr-defined]
        self._prepared_effective_rate_sending_by_link = prepared

    def _gate_aware_service_context(self, link_id: str, base_rate: float) -> ServiceRateContext:
        packet_ids = self._current_parity_eligible_packet_ids(link_id)  # type: ignore[attr-defined]
        movement_states: dict[str, str] = {}
        relevant_packets = []
        enabled = False
        saw_controlled = False
        saw_uncontrolled = False
        for packet_id in packet_ids:
            downstream = self._next_link_id(packet_id)  # type: ignore[attr-defined]
            relevant_packets.append(packet_id)
            if downstream is None:
                movement_id = f"completion:{link_id}"
                movement_states[movement_id] = "uncontrolled"
                saw_uncontrolled = True
                enabled = True
                continue
            movement_id = f"movement:{link_id}->{downstream}"
            state = self._gate_aware_movement_state(link_id, movement_id)
            movement_states[movement_id] = state
            if state == "uncontrolled":
                saw_uncontrolled = True
                enabled = True
            else:
                saw_controlled = True
                if state == "green":
                    enabled = True
        if not relevant_packets:
            gate_state = "no_eligible_demand"
        elif enabled and saw_controlled and saw_uncontrolled:
            gate_state = "enabled_mixed_controlled_and_uncontrolled"
        elif enabled and saw_controlled:
            gate_state = "enabled_at_least_one_green"
        elif enabled:
            gate_state = "enabled_uncontrolled"
        else:
            gate_state = "disabled_all_relevant_movements_red"
        return ServiceRateContext(
            tick=self.current_tick,  # type: ignore[attr-defined]
            service_account_id=f"effective-rate:sending:{link_id}",
            service_domain_id=link_id,
            service_domain_type="link_sending",
            base_continuous_rate_packets_per_tick=base_rate,
            control_gate_state=gate_state,
            control_availability_factor=1.0 if enabled else 0.0,
            relevant_movement_ids=tuple(sorted(movement_states)),
            relevant_packet_ids=tuple(relevant_packets),
        )

    def _gate_aware_movement_state(self, link_id: str, movement_id: str) -> str:
        signal_query = getattr(self, "signal_gate_state", None)
        if signal_query is not None:
            fixed_state = signal_query(movement_id, self.current_tick)  # type: ignore[attr-defined]
            if fixed_state is not None:
                return "green" if fixed_state.effective_is_open else "red"
        node = self._node_by_incoming_link_id.get(link_id)  # type: ignore[attr-defined]
        if node is None:
            return "uncontrolled"
        movement = node.junction_spec.movement_by_id.get(movement_id)
        if movement is None or movement.signal_group_id is None:
            return "uncontrolled"
        return (
            "green"
            if movement.signal_group_id in self._open_signal_group_ids  # type: ignore[attr-defined]
            else "red"
        )

    def step(self) -> None:
        receiving_open = dict(
            self._parity_receiving_capacity_carry_by_link_id  # type: ignore[attr-defined]
        )
        event_start = len(self.event_log)  # type: ignore[attr-defined]
        super().step()  # type: ignore[misc]
        new_events = self.event_log[event_start:]  # type: ignore[attr-defined]
        rates = self.effective_rate_service_config.capacity_by_link
        for link_id in sorted(self.links):  # type: ignore[attr-defined]
            exits = tuple(
                item.packet_id
                for item in new_events
                if item.event_type == EventType.LINK_EXIT and item.entity_id == link_id
            )
            entries = tuple(
                item.packet_id
                for item in new_events
                if item.event_type == EventType.LINK_ENTRY and item.entity_id == link_id
            )
            prepared = self._prepared_effective_rate_sending_by_link[link_id]
            receiving_close = self._parity_receiving_capacity_carry_by_link_id[link_id]  # type: ignore[attr-defined]
            receiving_whole = self._parity_receiving_integer_capacity_by_link_id[link_id]  # type: ignore[attr-defined]
            receiving_cap = float(ceil(rates[link_id]) + 1)
            self._record_effective_rate_service_evidence(
                (
                    EffectiveRateFractionalServiceEvidence(
                        tick=self.current_tick,  # type: ignore[attr-defined]
                        service_account_id=prepared.context.service_account_id,
                        service_domain_id=link_id,
                        service_domain_type="link_sending",
                        base_continuous_rate_packets_per_tick=rates[link_id],
                        tick_duration_seconds=self.links[link_id].tick_duration_seconds,  # type: ignore[attr-defined]
                        base_continuous_allowance=prepared.rate.base_continuous_allowance,
                        control_gate_state=prepared.context.control_gate_state,
                        control_availability_factor=prepared.rate.control_availability_factor,
                        dynamic_rate_multiplier=prepared.rate.dynamic_rate_multiplier,
                        effective_continuous_allowance=prepared.rate.effective_continuous_allowance,
                        opening_credit=prepared.opening_fractional_credit,
                        opening_fractional_credit=prepared.opening_fractional_credit,
                        whole_service_exposed=prepared.whole_service_exposed,
                        physically_consumed_service=len(exits),
                        expired_unconsumed_whole_opportunity=max(prepared.whole_service_exposed - len(exits), 0),
                        retained_unused_whole_credit=0.0,
                        closing_credit=prepared.closing_fractional_credit,
                        closing_fractional_credit=prepared.closing_fractional_credit,
                        credit_cap=1.0,
                        relevant_movement_ids=prepared.context.relevant_movement_ids,
                        relevant_packet_ids=prepared.context.relevant_packet_ids,
                        consumed_packet_ids=exits,
                        retention_policy=self.effective_rate_service_config.enabled_unused_whole_policy,
                        multiplier_provider_id=self.service_rate_multiplier_provider.provider_id,
                        multiplier_configuration_hash=self.service_rate_multiplier_provider.configuration_hash,
                        configuration_hash=self.effective_rate_service_config.config_hash,
                        executable_semantic_hash=self.effective_rate_executable_semantic_hash,
                        policy_id=self.effective_rate_service_config.version,
                    ),
                    EffectiveRateFractionalServiceEvidence(
                        tick=self.current_tick,  # type: ignore[attr-defined]
                        service_account_id=f"effective-rate:receiving:{link_id}",
                        service_domain_id=link_id,
                        service_domain_type="link_receiving",
                        base_continuous_rate_packets_per_tick=rates[link_id],
                        tick_duration_seconds=self.links[link_id].tick_duration_seconds,  # type: ignore[attr-defined]
                        base_continuous_allowance=rates[link_id],
                        control_gate_state="not_signal_gated",
                        control_availability_factor=1.0,
                        dynamic_rate_multiplier=1.0,
                        effective_continuous_allowance=rates[link_id],
                        opening_credit=receiving_open[link_id],
                        opening_fractional_credit=receiving_open[link_id] % 1.0,
                        whole_service_exposed=receiving_whole,
                        physically_consumed_service=len(entries),
                        expired_unconsumed_whole_opportunity=0,
                        retained_unused_whole_credit=floor(receiving_close),
                        closing_credit=receiving_close,
                        closing_fractional_credit=receiving_close % 1.0,
                        credit_cap=receiving_cap,
                        relevant_movement_ids=(),
                        relevant_packet_ids=(),
                        consumed_packet_ids=entries,
                        retention_policy=self.effective_rate_service_config.receiving_policy,
                        multiplier_provider_id=CONSTANT_ONE_MULTIPLIER_ID,
                        multiplier_configuration_hash=self.service_rate_multiplier_provider.configuration_hash,
                        configuration_hash=self.effective_rate_service_config.config_hash,
                        executable_semantic_hash=self.effective_rate_executable_semantic_hash,
                        policy_id=self.effective_rate_service_config.version,
                    ),
                )
            )


class GateAwareFractionalServiceMixin(EffectiveRateFractionalServiceMixin):
    """V2 name for the generic effective-rate accumulator."""

    def __init__(
        self,
        *args: object,
        gate_aware_fractional_service_config: GateAwareFractionalServiceConfig,
        **kwargs: object,
    ) -> None:
        self.gate_aware_fractional_service_config = (
            gate_aware_fractional_service_config
        )
        super().__init__(
            *args,
            effective_rate_service_config=gate_aware_fractional_service_config,
            **kwargs,
        )

    @property
    def gate_aware_fractional_service_evidence(
        self,
    ) -> tuple[EffectiveRateFractionalServiceEvidence, ...]:
        return self.effective_rate_fractional_service_evidence

    @property
    def gate_aware_fractional_service_evidence_hash(self) -> str:
        return self.effective_rate_fractional_service_evidence_hash


GateAwareFractionalServiceEvidence = EffectiveRateFractionalServiceEvidence


class GateAwareFractionalServiceLoadingEngine(
    GateAwareFractionalServiceMixin,
    LoadingEngine,
):
    """Standard loading engine with V2 gate-aware service."""


def gate_aware_service_config_for_executable(executable) -> GateAwareFractionalServiceConfig:
    """Consume compiler continuous capacities without changing compiler identity."""

    rates = []
    for link in executable.resolved_links:
        if link.capacity_veh_per_hour_per_lane is None or link.lane_count is None:
            raise GateAwareFractionalServiceIntegrityError(
                f"link {link.link_id} lacks continuous capacity semantics"
            )
        rates.append(
            (
                link.link_id,
                link.capacity_veh_per_hour_per_lane
                * link.lane_count
                * executable.tick_duration_seconds
                / 3600.0,
            )
        )
    return GateAwareFractionalServiceConfig(tuple(rates))
