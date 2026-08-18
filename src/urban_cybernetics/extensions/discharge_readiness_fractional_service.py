"""V3 exponential discharge readiness over the V2 effective-rate machinery.

Readiness belongs to the existing shared physical-link sending account.  It
modulates service accrual but never signal permission, receiving supply,
fractional credit, allocation, or canonical physical execution.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from math import exp, floor, isfinite
from typing import Mapping, Self

from urban_cybernetics.compiler.model import canonical_json, stable_hash
from urban_cybernetics.loading.engine import LoadingEngine

from .gate_aware_fractional_service import (
    EffectiveRateFractionalServiceEvidence,
    EffectiveRateFractionalServiceMixin,
    ServiceRateContext,
    ServiceRateMultiplierProvider,
)


DISCHARGE_READINESS_FRACTIONAL_SERVICE_VERSION = (
    "uc.discharge-readiness-fractional-service.v3"
)
DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE = (
    "discharge_readiness_fractional_service_v3"
)
DISCHARGE_READINESS_EVIDENCE_VERSION = "uc.discharge-readiness-evidence.v1"
DISCHARGE_READINESS_MULTIPLIER_PROVIDER_ID = (
    "exponential_interval_mean_discharge_readiness:v1"
)

FORENSIC_EVIDENCE = "forensic"
COMPACT_EVIDENCE = "compact"
SUMMARY_EVIDENCE = "summary"
SUPPORTED_EVIDENCE_MODES = frozenset(
    (FORENSIC_EVIDENCE, COMPACT_EVIDENCE, SUMMARY_EVIDENCE)
)

NO_DEMAND = "no_demand"
RED_DECAY = "red_decay"
GREEN_RECOVERY = "green_recovery"
UNCONTROLLED_FULL_READINESS = "uncontrolled_full_readiness"


class DischargeReadinessIntegrityError(ValueError):
    """Raised for malformed V3 configuration or evidence."""


def _normalise_pairs(
    values: tuple[tuple[str, float], ...],
    *,
    positive: bool,
) -> tuple[tuple[str, float], ...]:
    result = tuple(sorted((str(key), float(value)) for key, value in values))
    if any(
        not key or not isfinite(value) or (value <= 0 if positive else value < 0)
        for key, value in result
    ):
        raise DischargeReadinessIntegrityError("invalid V3 keyed numerical value")
    if len({key for key, _ in result}) != len(result):
        raise DischargeReadinessIntegrityError("duplicate V3 keyed value")
    return result


@dataclass(frozen=True, slots=True)
class DischargeReadinessConfig:
    """Immutable physical V3 policy plus separately identified recording mode."""

    continuous_capacity_by_link: tuple[tuple[str, float], ...]
    tick_duration_seconds_by_link: tuple[tuple[str, float], ...]
    controlled_readiness_link_ids: tuple[str, ...]
    tau_green_seconds: float
    tau_red_seconds: float | None
    default_initial_readiness: float = 1.0
    initial_readiness_by_domain: tuple[tuple[str, float], ...] = ()
    evidence_mode: str = FORENSIC_EVIDENCE
    compact_checkpoint_interval_ticks: int = 20
    readiness_domain_policy: str = "shared_physical_link_sending_account"
    eligible_demand_policy: str = "free_flow_eligible_packet_with_next_discharge"
    no_demand_policy: str = "reset_to_established_readiness_one"
    green_transition_policy: str = "exact_exponential_interval_mean"
    red_transition_policy: str = "exact_exponential_decay_zero_accrual"
    enabled_unused_whole_policy: str = "expire_after_enabled_tick"
    receiving_policy: str = "ungated_desouza_bounded_credit"
    dynamic_multiplier_provider_id: str = DISCHARGE_READINESS_MULTIPLIER_PROVIDER_ID
    version: str = DISCHARGE_READINESS_FRACTIONAL_SERVICE_VERSION
    _config_hash: str = field(init=False, repr=False, compare=False)
    _recording_config_hash: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.version != DISCHARGE_READINESS_FRACTIONAL_SERVICE_VERSION:
            raise DischargeReadinessIntegrityError("unsupported V3 policy version")
        capacities = _normalise_pairs(
            self.continuous_capacity_by_link, positive=False
        )
        durations = _normalise_pairs(
            self.tick_duration_seconds_by_link, positive=True
        )
        if {key for key, _ in capacities} != {key for key, _ in durations}:
            raise DischargeReadinessIntegrityError(
                "V3 capacity and tick-duration domains must match"
            )
        controlled = tuple(sorted(str(item) for item in self.controlled_readiness_link_ids))
        if len(set(controlled)) != len(controlled) or not set(controlled) <= {
            key for key, _ in capacities
        }:
            raise DischargeReadinessIntegrityError(
                "V3 controlled readiness domains must be unique executable links"
            )
        if not isfinite(self.tau_green_seconds) or self.tau_green_seconds <= 0:
            raise DischargeReadinessIntegrityError("tau_green_seconds must be positive")
        if self.tau_red_seconds is not None and (
            not isfinite(self.tau_red_seconds) or self.tau_red_seconds <= 0
        ):
            raise DischargeReadinessIntegrityError(
                "tau_red_seconds must be positive or None for infinity"
            )
        if not 0.0 <= self.default_initial_readiness <= 1.0:
            raise DischargeReadinessIntegrityError(
                "default initial readiness must be in [0,1]"
            )
        initial = _normalise_pairs(self.initial_readiness_by_domain, positive=False)
        if any(value > 1.0 for _, value in initial) or not {
            key for key, _ in initial
        } <= set(controlled):
            raise DischargeReadinessIntegrityError(
                "explicit initial readiness must be in [0,1] on controlled domains"
            )
        if self.evidence_mode not in SUPPORTED_EVIDENCE_MODES:
            raise DischargeReadinessIntegrityError("unsupported V3 evidence mode")
        if self.compact_checkpoint_interval_ticks <= 0:
            raise DischargeReadinessIntegrityError(
                "compact checkpoint interval must be positive"
            )
        expected = {
            "readiness_domain_policy": "shared_physical_link_sending_account",
            "eligible_demand_policy": "free_flow_eligible_packet_with_next_discharge",
            "no_demand_policy": "reset_to_established_readiness_one",
            "green_transition_policy": "exact_exponential_interval_mean",
            "red_transition_policy": "exact_exponential_decay_zero_accrual",
            "enabled_unused_whole_policy": "expire_after_enabled_tick",
            "receiving_policy": "ungated_desouza_bounded_credit",
            "dynamic_multiplier_provider_id": DISCHARGE_READINESS_MULTIPLIER_PROVIDER_ID,
        }
        if {key: getattr(self, key) for key in expected} != expected:
            raise DischargeReadinessIntegrityError(
                "V3 metadata must exactly describe implemented semantics"
            )
        object.__setattr__(self, "continuous_capacity_by_link", capacities)
        object.__setattr__(self, "tick_duration_seconds_by_link", durations)
        object.__setattr__(self, "controlled_readiness_link_ids", controlled)
        object.__setattr__(self, "initial_readiness_by_domain", initial)
        object.__setattr__(self, "tau_green_seconds", float(self.tau_green_seconds))
        object.__setattr__(
            self,
            "tau_red_seconds",
            None if self.tau_red_seconds is None else float(self.tau_red_seconds),
        )
        object.__setattr__(
            self, "default_initial_readiness", float(self.default_initial_readiness)
        )
        physical_hash = stable_hash(
            "discharge-readiness-physical-config", self.physical_policy_dict()
        )
        object.__setattr__(self, "_config_hash", physical_hash)
        object.__setattr__(
            self,
            "_recording_config_hash",
            stable_hash(
                "discharge-readiness-recording-config",
                {
                    "physical_config_hash": physical_hash,
                    "evidence_mode": self.evidence_mode,
                    "compact_checkpoint_interval_ticks": (
                        self.compact_checkpoint_interval_ticks
                    ),
                },
            ),
        )

    @property
    def mode(self) -> str:
        return DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE

    @property
    def capacity_by_link(self) -> dict[str, float]:
        return dict(self.continuous_capacity_by_link)

    @property
    def tick_duration_by_link(self) -> dict[str, float]:
        return dict(self.tick_duration_seconds_by_link)

    @property
    def initial_readiness(self) -> dict[str, float]:
        explicit = dict(self.initial_readiness_by_domain)
        return {
            domain_id: explicit.get(domain_id, self.default_initial_readiness)
            for domain_id in self.controlled_readiness_link_ids
        }

    def physical_policy_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "mode": self.mode,
            "continuous_capacity_by_link": [list(item) for item in self.continuous_capacity_by_link],
            "tick_duration_seconds_by_link": [list(item) for item in self.tick_duration_seconds_by_link],
            "controlled_readiness_link_ids": list(self.controlled_readiness_link_ids),
            "tau_green_seconds": self.tau_green_seconds,
            "tau_red_seconds": (
                "infinite" if self.tau_red_seconds is None else self.tau_red_seconds
            ),
            "default_initial_readiness": self.default_initial_readiness,
            "initial_readiness_by_domain": [list(item) for item in self.initial_readiness_by_domain],
            "readiness_domain_policy": self.readiness_domain_policy,
            "eligible_demand_policy": self.eligible_demand_policy,
            "no_demand_policy": self.no_demand_policy,
            "green_transition_policy": self.green_transition_policy,
            "red_transition_policy": self.red_transition_policy,
            "enabled_unused_whole_policy": self.enabled_unused_whole_policy,
            "receiving_policy": self.receiving_policy,
            "dynamic_multiplier_provider_id": self.dynamic_multiplier_provider_id,
        }

    @property
    def config_hash(self) -> str:
        """Physical runtime identity; deliberately excludes recording verbosity."""

        return self._config_hash

    @property
    def recording_config_hash(self) -> str:
        return self._recording_config_hash

    def to_dict(self) -> dict[str, object]:
        return {
            **self.physical_policy_dict(),
            "evidence_mode": self.evidence_mode,
            "compact_checkpoint_interval_ticks": self.compact_checkpoint_interval_ticks,
            "physical_config_hash": self.config_hash,
            "recording_config_hash": self.recording_config_hash,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        tau_red = payload["tau_red_seconds"]
        result = cls(
            continuous_capacity_by_link=tuple(
                (str(key), float(value))
                for key, value in payload["continuous_capacity_by_link"]  # type: ignore[misc]
            ),
            tick_duration_seconds_by_link=tuple(
                (str(key), float(value))
                for key, value in payload["tick_duration_seconds_by_link"]  # type: ignore[misc]
            ),
            controlled_readiness_link_ids=tuple(
                str(item) for item in payload["controlled_readiness_link_ids"]  # type: ignore[index]
            ),
            tau_green_seconds=float(payload["tau_green_seconds"]),
            tau_red_seconds=None if tau_red == "infinite" else float(tau_red),
            default_initial_readiness=float(payload["default_initial_readiness"]),
            initial_readiness_by_domain=tuple(
                (str(key), float(value))
                for key, value in payload["initial_readiness_by_domain"]  # type: ignore[misc]
            ),
            evidence_mode=str(payload["evidence_mode"]),
            compact_checkpoint_interval_ticks=int(
                payload["compact_checkpoint_interval_ticks"]
            ),
            readiness_domain_policy=str(payload["readiness_domain_policy"]),
            eligible_demand_policy=str(payload["eligible_demand_policy"]),
            no_demand_policy=str(payload["no_demand_policy"]),
            green_transition_policy=str(payload["green_transition_policy"]),
            red_transition_policy=str(payload["red_transition_policy"]),
            enabled_unused_whole_policy=str(payload["enabled_unused_whole_policy"]),
            receiving_policy=str(payload["receiving_policy"]),
            dynamic_multiplier_provider_id=str(payload["dynamic_multiplier_provider_id"]),
            version=str(payload["version"]),
        )
        if payload.get("physical_config_hash") not in (None, result.config_hash):
            raise DischargeReadinessIntegrityError("V3 physical config hash mismatch")
        if payload.get("recording_config_hash") not in (
            None,
            result.recording_config_hash,
        ):
            raise DischargeReadinessIntegrityError("V3 recording config hash mismatch")
        return result


@dataclass(frozen=True, slots=True)
class _ReadinessTransition:
    tick: int
    domain_id: str
    transition_mode: str
    opening_readiness: float
    interval_mean_readiness: float
    closing_readiness: float
    gate_availability: float
    eligible_demand_count: int


@dataclass(frozen=True, slots=True)
class DischargeReadinessEvidence:
    """One controlled sending-domain readiness/service evaluation."""

    tick: int
    service_account_id: str
    service_domain_id: str
    readiness_domain_id: str
    transition_mode: str
    opening_readiness: float
    interval_mean_readiness_multiplier: float
    closing_readiness: float
    gate_availability_factor: float
    tau_green_seconds: float
    tau_red_seconds: float | None
    tick_duration_seconds: float
    base_continuous_allowance: float
    effective_continuous_allowance: float
    opening_fractional_credit: float
    whole_service_exposed: int
    physically_consumed_service: int
    expired_unconsumed_whole_service: int
    closing_fractional_credit: float
    eligible_demand_count: int
    relevant_movement_ids: tuple[str, ...]
    relevant_packet_ids: tuple[str, ...]
    consumed_packet_ids: tuple[str, ...]
    policy_id: str
    physical_config_hash: str
    version: str = DISCHARGE_READINESS_EVIDENCE_VERSION
    evidence_hash: str = ""

    def __post_init__(self) -> None:
        if self.version != DISCHARGE_READINESS_EVIDENCE_VERSION:
            raise DischargeReadinessIntegrityError("V3 evidence version mismatch")
        if self.policy_id != DISCHARGE_READINESS_FRACTIONAL_SERVICE_VERSION:
            raise DischargeReadinessIntegrityError("V3 evidence policy mismatch")
        if self.transition_mode not in (
            NO_DEMAND,
            RED_DECAY,
            GREEN_RECOVERY,
            UNCONTROLLED_FULL_READINESS,
        ):
            raise DischargeReadinessIntegrityError("unknown V3 readiness transition")
        for value in (
            self.opening_readiness,
            self.interval_mean_readiness_multiplier,
            self.closing_readiness,
            self.gate_availability_factor,
            self.opening_fractional_credit,
            self.closing_fractional_credit,
        ):
            if not 0.0 <= value <= 1.0:
                raise DischargeReadinessIntegrityError("V3 evidence value outside [0,1]")
        object.__setattr__(self, "relevant_movement_ids", tuple(self.relevant_movement_ids))
        object.__setattr__(self, "relevant_packet_ids", tuple(self.relevant_packet_ids))
        object.__setattr__(self, "consumed_packet_ids", tuple(self.consumed_packet_ids))
        expected = stable_hash("discharge-readiness-evidence", self._payload())
        if self.evidence_hash and self.evidence_hash != expected:
            raise DischargeReadinessIntegrityError("V3 evidence hash mismatch")
        object.__setattr__(self, "evidence_hash", expected)

    def _payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "tick": self.tick,
            "service_account_id": self.service_account_id,
            "service_domain_id": self.service_domain_id,
            "readiness_domain_id": self.readiness_domain_id,
            "transition_mode": self.transition_mode,
            "opening_readiness": self.opening_readiness,
            "interval_mean_readiness_multiplier": self.interval_mean_readiness_multiplier,
            "closing_readiness": self.closing_readiness,
            "gate_availability_factor": self.gate_availability_factor,
            "tau_green_seconds": self.tau_green_seconds,
            "tau_red_seconds": (
                "infinite" if self.tau_red_seconds is None else self.tau_red_seconds
            ),
            "tick_duration_seconds": self.tick_duration_seconds,
            "base_continuous_allowance": self.base_continuous_allowance,
            "effective_continuous_allowance": self.effective_continuous_allowance,
            "opening_fractional_credit": self.opening_fractional_credit,
            "whole_service_exposed": self.whole_service_exposed,
            "physically_consumed_service": self.physically_consumed_service,
            "expired_unconsumed_whole_service": self.expired_unconsumed_whole_service,
            "closing_fractional_credit": self.closing_fractional_credit,
            "eligible_demand_count": self.eligible_demand_count,
            "relevant_movement_ids": list(self.relevant_movement_ids),
            "relevant_packet_ids": list(self.relevant_packet_ids),
            "consumed_packet_ids": list(self.consumed_packet_ids),
            "policy_id": self.policy_id,
            "physical_config_hash": self.physical_config_hash,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "evidence_hash": self.evidence_hash}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        tau_red = payload["tau_red_seconds"]
        return cls(
            tick=int(payload["tick"]),
            service_account_id=str(payload["service_account_id"]),
            service_domain_id=str(payload["service_domain_id"]),
            readiness_domain_id=str(payload["readiness_domain_id"]),
            transition_mode=str(payload["transition_mode"]),
            opening_readiness=float(payload["opening_readiness"]),
            interval_mean_readiness_multiplier=float(
                payload["interval_mean_readiness_multiplier"]
            ),
            closing_readiness=float(payload["closing_readiness"]),
            gate_availability_factor=float(payload["gate_availability_factor"]),
            tau_green_seconds=float(payload["tau_green_seconds"]),
            tau_red_seconds=None if tau_red == "infinite" else float(tau_red),
            tick_duration_seconds=float(payload["tick_duration_seconds"]),
            base_continuous_allowance=float(payload["base_continuous_allowance"]),
            effective_continuous_allowance=float(payload["effective_continuous_allowance"]),
            opening_fractional_credit=float(payload["opening_fractional_credit"]),
            whole_service_exposed=int(payload["whole_service_exposed"]),
            physically_consumed_service=int(payload["physically_consumed_service"]),
            expired_unconsumed_whole_service=int(
                payload["expired_unconsumed_whole_service"]
            ),
            closing_fractional_credit=float(payload["closing_fractional_credit"]),
            eligible_demand_count=int(payload["eligible_demand_count"]),
            relevant_movement_ids=tuple(str(x) for x in payload["relevant_movement_ids"]),  # type: ignore[index]
            relevant_packet_ids=tuple(str(x) for x in payload["relevant_packet_ids"]),  # type: ignore[index]
            consumed_packet_ids=tuple(str(x) for x in payload["consumed_packet_ids"]),  # type: ignore[index]
            policy_id=str(payload["policy_id"]),
            physical_config_hash=str(payload["physical_config_hash"]),
            version=str(payload["version"]),
            evidence_hash=str(payload.get("evidence_hash", "")),
        )


class ExponentialDischargeReadinessProvider(ServiceRateMultiplierProvider):
    """Exact per-tick exponential state transition and interval mean."""

    def __init__(self, config: DischargeReadinessConfig) -> None:
        self.config = config
        self._readiness_by_domain = config.initial_readiness
        self._controlled = frozenset(config.controlled_readiness_link_ids)
        self._transition_by_domain: dict[str, _ReadinessTransition] = {}
        self._green_decay: dict[str, float] = {}
        self._green_integral_factor: dict[str, float] = {}
        self._red_decay: dict[str, float] = {}
        self._red_integral_factor: dict[str, float] = {}
        for domain_id, dt in config.tick_duration_seconds_by_link:
            green_decay = exp(-dt / config.tau_green_seconds)
            self._green_decay[domain_id] = green_decay
            self._green_integral_factor[domain_id] = (
                config.tau_green_seconds / dt * (1.0 - green_decay)
            )
            if config.tau_red_seconds is None:
                self._red_decay[domain_id] = 1.0
                self._red_integral_factor[domain_id] = 1.0
            else:
                red_decay = exp(-dt / config.tau_red_seconds)
                self._red_decay[domain_id] = red_decay
                self._red_integral_factor[domain_id] = (
                    config.tau_red_seconds / dt * (1.0 - red_decay)
                )

    @property
    def provider_id(self) -> str:
        return DISCHARGE_READINESS_MULTIPLIER_PROVIDER_ID

    @property
    def configuration_hash(self) -> str:
        return self.config.config_hash

    @property
    def readiness_by_domain(self) -> dict[str, float]:
        return dict(self._readiness_by_domain)

    def transition(self, domain_id: str) -> _ReadinessTransition:
        return self._transition_by_domain[domain_id]

    def multiplier(self, context: ServiceRateContext) -> float:
        domain_id = context.service_domain_id
        eligible_count = len(context.relevant_packet_ids)
        if domain_id not in self._controlled:
            transition = _ReadinessTransition(
                context.tick,
                domain_id,
                UNCONTROLLED_FULL_READINESS,
                1.0,
                1.0,
                1.0,
                context.control_availability_factor,
                eligible_count,
            )
            self._transition_by_domain[domain_id] = transition
            return 1.0

        opening = self._readiness_by_domain[domain_id]
        if eligible_count == 0:
            mean = closing = 1.0
            mode = NO_DEMAND
        elif context.control_availability_factor == 0.0:
            closing = opening * self._red_decay[domain_id]
            mean = opening * self._red_integral_factor[domain_id]
            mode = RED_DECAY
        else:
            closing = 1.0 - (1.0 - opening) * self._green_decay[domain_id]
            mean = 1.0 - (1.0 - opening) * self._green_integral_factor[domain_id]
            mode = GREEN_RECOVERY
        closing = min(max(closing, 0.0), 1.0)
        mean = min(max(mean, 0.0), 1.0)
        self._readiness_by_domain[domain_id] = closing
        self._transition_by_domain[domain_id] = _ReadinessTransition(
            context.tick,
            domain_id,
            mode,
            opening,
            mean,
            closing,
            context.control_availability_factor,
            eligible_count,
        )
        return mean


class DischargeReadinessFractionalServiceMixin(EffectiveRateFractionalServiceMixin):
    """V3 policy adapter, evidence retention, digest, and aggregates."""

    def __init__(
        self,
        *args: object,
        discharge_readiness_config: DischargeReadinessConfig,
        **kwargs: object,
    ) -> None:
        self.discharge_readiness_config = discharge_readiness_config
        provider = ExponentialDischargeReadinessProvider(discharge_readiness_config)
        self.discharge_readiness_provider = provider
        self._discharge_readiness_evidence: list[DischargeReadinessEvidence] = []
        self._logical_evidence_hasher = hashlib.sha256()
        self._logical_evidence_hasher.update(
            b"uc.discharge-readiness-logical-evidence.v1\0"
        )
        self._logical_evidence_count = 0
        self._retained_logical_evidence_count = 0
        self._last_transition_mode_by_domain: dict[str, str] = {}
        self._readiness_aggregate_by_domain: dict[str, dict[str, object]] = {}
        super().__init__(
            *args,
            effective_rate_service_config=discharge_readiness_config,
            service_rate_multiplier_provider=provider,
            **kwargs,
        )

    @property
    def discharge_readiness_evidence(self) -> tuple[DischargeReadinessEvidence, ...]:
        return tuple(self._discharge_readiness_evidence)

    @property
    def logical_evidence_digest(self) -> str:
        return self._logical_evidence_hasher.copy().hexdigest()

    @property
    def logical_evidence_record_count(self) -> int:
        return self._logical_evidence_count

    @property
    def retained_logical_evidence_record_count(self) -> int:
        return self._retained_logical_evidence_count

    def _digest_record(self, record_kind: str, payload: Mapping[str, object]) -> None:
        encoded = canonical_json(
            {"record_kind": record_kind, "payload": payload}
        ).encode("utf-8")
        self._logical_evidence_hasher.update(len(encoded).to_bytes(8, "big"))
        self._logical_evidence_hasher.update(encoded)
        self._logical_evidence_count += 1

    def _retain_tick_record(
        self,
        service: EffectiveRateFractionalServiceEvidence,
        transition: _ReadinessTransition | None,
    ) -> bool:
        mode = self.discharge_readiness_config.evidence_mode
        if mode == FORENSIC_EVIDENCE:
            return True
        if mode == SUMMARY_EVIDENCE:
            return False
        checkpoint = (
            service.tick == 1
            or service.tick
            % self.discharge_readiness_config.compact_checkpoint_interval_ticks
            == 0
        )
        activity = (
            service.whole_service_exposed > 0
            or service.physically_consumed_service > 0
            or service.expired_unconsumed_whole_opportunity > 0
        )
        transition_change = False
        if transition is not None:
            transition_change = self._last_transition_mode_by_domain.get(
                transition.domain_id
            ) != transition.transition_mode
        return checkpoint or activity or transition_change

    def _record_effective_rate_service_evidence(
        self,
        records: tuple[EffectiveRateFractionalServiceEvidence, ...],
    ) -> None:
        sending, receiving = records
        domain_id = sending.service_domain_id
        transition = self.discharge_readiness_provider.transition(domain_id)
        controlled = domain_id in self.discharge_readiness_config.controlled_readiness_link_ids
        readiness_record = None
        if controlled:
            readiness_record = DischargeReadinessEvidence(
                tick=sending.tick,
                service_account_id=sending.service_account_id,
                service_domain_id=domain_id,
                readiness_domain_id=domain_id,
                transition_mode=transition.transition_mode,
                opening_readiness=transition.opening_readiness,
                interval_mean_readiness_multiplier=transition.interval_mean_readiness,
                closing_readiness=transition.closing_readiness,
                gate_availability_factor=transition.gate_availability,
                tau_green_seconds=self.discharge_readiness_config.tau_green_seconds,
                tau_red_seconds=self.discharge_readiness_config.tau_red_seconds,
                tick_duration_seconds=sending.tick_duration_seconds,
                base_continuous_allowance=sending.base_continuous_allowance,
                effective_continuous_allowance=sending.effective_continuous_allowance,
                opening_fractional_credit=sending.opening_fractional_credit,
                whole_service_exposed=sending.whole_service_exposed,
                physically_consumed_service=sending.physically_consumed_service,
                expired_unconsumed_whole_service=(
                    sending.expired_unconsumed_whole_opportunity
                ),
                closing_fractional_credit=sending.closing_fractional_credit,
                eligible_demand_count=transition.eligible_demand_count,
                relevant_movement_ids=sending.relevant_movement_ids,
                relevant_packet_ids=sending.relevant_packet_ids,
                consumed_packet_ids=sending.consumed_packet_ids,
                policy_id=self.discharge_readiness_config.version,
                physical_config_hash=self.discharge_readiness_config.config_hash,
            )
        self._digest_record("effective_rate_service", sending.to_dict())
        if readiness_record is not None:
            self._digest_record("discharge_readiness", readiness_record.to_dict())
        self._digest_record("effective_rate_service", receiving.to_dict())
        retain = self._retain_tick_record(sending, transition if controlled else None)
        if retain:
            self._effective_rate_service_evidence.extend(records)
            self._retained_logical_evidence_count += 2
            if readiness_record is not None:
                self._discharge_readiness_evidence.append(readiness_record)
                self._retained_logical_evidence_count += 1
        if controlled:
            self._update_readiness_aggregate(readiness_record)  # type: ignore[arg-type]
            self._last_transition_mode_by_domain[domain_id] = transition.transition_mode

    def _update_readiness_aggregate(
        self, record: DischargeReadinessEvidence
    ) -> None:
        aggregate = self._readiness_aggregate_by_domain.setdefault(
            record.readiness_domain_id,
            {
                "domain_id": record.readiness_domain_id,
                "green_ticks": 0,
                "red_ticks": 0,
                "no_demand_ticks": 0,
                "sum_green_mean_readiness": 0.0,
                "nominal_enabled_allowance": 0.0,
                "effective_allowance": 0.0,
                "startup_lost_service": 0.0,
                "whole_service_exposed": 0,
                "physically_consumed_service": 0,
                "expired_whole_service": 0,
                "minimum_readiness": 1.0,
                "red_to_green_opening_readiness": [],
            },
        )
        prior_mode = self._last_transition_mode_by_domain.get(record.readiness_domain_id)
        if record.transition_mode == GREEN_RECOVERY:
            aggregate["green_ticks"] = int(aggregate["green_ticks"]) + 1
            aggregate["sum_green_mean_readiness"] = float(
                aggregate["sum_green_mean_readiness"]
            ) + record.interval_mean_readiness_multiplier
            if prior_mode == RED_DECAY:
                aggregate["red_to_green_opening_readiness"].append(  # type: ignore[union-attr]
                    record.opening_readiness
                )
        elif record.transition_mode == RED_DECAY:
            aggregate["red_ticks"] = int(aggregate["red_ticks"]) + 1
        elif record.transition_mode == NO_DEMAND:
            aggregate["no_demand_ticks"] = int(aggregate["no_demand_ticks"]) + 1
        nominal = record.base_continuous_allowance * record.gate_availability_factor
        aggregate["nominal_enabled_allowance"] = float(
            aggregate["nominal_enabled_allowance"]
        ) + nominal
        aggregate["effective_allowance"] = float(aggregate["effective_allowance"]) + (
            record.effective_continuous_allowance
        )
        aggregate["startup_lost_service"] = float(aggregate["startup_lost_service"]) + (
            nominal - record.effective_continuous_allowance
        )
        aggregate["whole_service_exposed"] = int(aggregate["whole_service_exposed"]) + (
            record.whole_service_exposed
        )
        aggregate["physically_consumed_service"] = int(
            aggregate["physically_consumed_service"]
        ) + record.physically_consumed_service
        aggregate["expired_whole_service"] = int(aggregate["expired_whole_service"]) + (
            record.expired_unconsumed_whole_service
        )
        aggregate["minimum_readiness"] = min(
            float(aggregate["minimum_readiness"]), record.closing_readiness
        )

    @property
    def discharge_readiness_summary(self) -> dict[str, object]:
        domains = []
        for domain_id, raw in sorted(self._readiness_aggregate_by_domain.items()):
            item = dict(raw)
            green_ticks = int(item["green_ticks"])
            item["mean_readiness_during_green"] = (
                float(item.pop("sum_green_mean_readiness")) / green_ticks
                if green_ticks
                else None
            )
            item["red_to_green_opening_readiness"] = list(
                item["red_to_green_opening_readiness"]
            )
            domains.append(item)
        payload = {
            "policy_id": self.discharge_readiness_config.version,
            "physical_config_hash": self.discharge_readiness_config.config_hash,
            "recording_config_hash": self.discharge_readiness_config.recording_config_hash,
            "evidence_mode": self.discharge_readiness_config.evidence_mode,
            "logical_evidence_digest": self.logical_evidence_digest,
            "logical_evidence_record_count": self.logical_evidence_record_count,
            "retained_logical_evidence_record_count": (
                self.retained_logical_evidence_record_count
            ),
            "domains": domains,
        }
        return {
            **payload,
            "summary_hash": stable_hash("discharge-readiness-summary", payload),
        }

    @property
    def fractional_service_credit_evidence_hash(self) -> str:
        return stable_hash(
            "discharge-readiness-recorded-evidence",
            {
                "recording_config_hash": self.discharge_readiness_config.recording_config_hash,
                "logical_evidence_digest": self.logical_evidence_digest,
                "retained_service_records": [
                    item.to_dict() for item in self._effective_rate_service_evidence
                ],
                "retained_readiness_records": [
                    item.to_dict() for item in self._discharge_readiness_evidence
                ],
            },
        )


class DischargeReadinessFractionalServiceLoadingEngine(
    DischargeReadinessFractionalServiceMixin,
    LoadingEngine,
):
    """Standard loading engine with V3 readiness-modulated sending."""


def discharge_readiness_config_for_executable(
    executable,
    *,
    tau_green_seconds: float = 2.0,
    tau_red_seconds: float | None = 10.0,
    initial_readiness: float = 1.0,
    evidence_mode: str = FORENSIC_EVIDENCE,
    compact_checkpoint_interval_ticks: int = 20,
) -> DischargeReadinessConfig:
    """Adapt compiler continuous capacities without altering compiler identity."""

    rates = []
    durations = []
    for link in executable.resolved_links:
        if link.capacity_veh_per_hour_per_lane is None or link.lane_count is None:
            raise DischargeReadinessIntegrityError(
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
        durations.append((link.link_id, executable.tick_duration_seconds))
    controlled_movements = {
        movement_id
        for controller in executable.signal_plan.controllers
        for movement_id in controller.controlled_movement_ids
    }
    controlled_links = tuple(
        sorted(
            {
                movement.upstream_link_id
                for node in executable.topology.nodes
                for movement in node.movement_specs
                if movement.movement_id in controlled_movements
            }
        )
    )
    return DischargeReadinessConfig(
        continuous_capacity_by_link=tuple(rates),
        tick_duration_seconds_by_link=tuple(durations),
        controlled_readiness_link_ids=controlled_links,
        tau_green_seconds=tau_green_seconds,
        tau_red_seconds=tau_red_seconds,
        default_initial_readiness=initial_readiness,
        initial_readiness_by_domain=tuple(
            (link_id, initial_readiness) for link_id in controlled_links
        ),
        evidence_mode=evidence_mode,
        compact_checkpoint_interval_ticks=compact_checkpoint_interval_ticks,
    )
