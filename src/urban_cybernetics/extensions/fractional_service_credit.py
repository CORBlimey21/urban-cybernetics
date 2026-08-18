"""Opt-in deterministic fractional service credit above the frozen loader.

The shell delegates capacity arithmetic, packet selection, allocation, and all
physical events to existing loading-engine hooks.  It owns only versioned mode
configuration and replayable account evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import ceil
from typing import Mapping, Self

from urban_cybernetics.compiler.model import canonical_json, stable_hash
from urban_cybernetics.core import EventType
from urban_cybernetics.loading.engine import LoadingEngine


FRACTIONAL_SERVICE_CREDIT_VERSION = "uc.fractional-service-credit.v1"
LEGACY_INTEGER_CLAMPED = "legacy_integer_clamped"
FRACTIONAL_CREDIT = "fractional_credit"
SUPPORTED_SERVICE_CREDIT_MODES = frozenset(
    (LEGACY_INTEGER_CLAMPED, FRACTIONAL_CREDIT)
)
SENDING_RETENTION_POLICY = "fractional_remainder_only"
RECEIVING_RETENTION_POLICY = "bounded_unused_credit"
EMPTY_QUEUE_POLICY = "no_unused_whole_sending_burst"
RED_SIGNAL_POLICY = "sending_whole_credit_expires_fraction_remainder_continues"
RECEIVING_CREDIT_CAP_FORMULA = "ceil(rate)+1"


class FractionalServiceCreditIntegrityError(ValueError):
    """Raised for malformed or hash-inconsistent extension evidence."""


@dataclass(frozen=True, slots=True)
class FractionalServiceCreditConfig:
    """Immutable continuous link rates and bounded-retention policy."""

    mode: str
    continuous_capacity_by_link: tuple[tuple[str, float], ...]
    sending_retention_policy: str = SENDING_RETENTION_POLICY
    receiving_retention_policy: str = RECEIVING_RETENTION_POLICY
    empty_queue_policy: str = EMPTY_QUEUE_POLICY
    red_signal_policy: str = RED_SIGNAL_POLICY
    receiving_credit_cap_formula: str = RECEIVING_CREDIT_CAP_FORMULA
    version: str = FRACTIONAL_SERVICE_CREDIT_VERSION

    def __post_init__(self) -> None:
        if self.mode not in SUPPORTED_SERVICE_CREDIT_MODES:
            raise FractionalServiceCreditIntegrityError(
                f"unsupported service-credit mode: {self.mode}"
            )
        if self.version != FRACTIONAL_SERVICE_CREDIT_VERSION:
            raise FractionalServiceCreditIntegrityError(
                "unsupported fractional service-credit version"
            )
        declared_policies = {
            "sending_retention_policy": self.sending_retention_policy,
            "receiving_retention_policy": self.receiving_retention_policy,
            "empty_queue_policy": self.empty_queue_policy,
            "red_signal_policy": self.red_signal_policy,
            "receiving_credit_cap_formula": self.receiving_credit_cap_formula,
        }
        required_policies = {
            "sending_retention_policy": SENDING_RETENTION_POLICY,
            "receiving_retention_policy": RECEIVING_RETENTION_POLICY,
            "empty_queue_policy": EMPTY_QUEUE_POLICY,
            "red_signal_policy": RED_SIGNAL_POLICY,
            "receiving_credit_cap_formula": RECEIVING_CREDIT_CAP_FORMULA,
        }
        if declared_policies != required_policies:
            raise FractionalServiceCreditIntegrityError(
                "service-credit policy metadata must describe the implemented v1 recurrence"
            )
        normalised = tuple(
            sorted(
                (str(link_id), float(rate))
                for link_id, rate in self.continuous_capacity_by_link
            )
        )
        if any(not link_id or rate < 0 for link_id, rate in normalised):
            raise FractionalServiceCreditIntegrityError(
                "continuous capacity IDs must be non-empty and rates non-negative"
            )
        if len({item[0] for item in normalised}) != len(normalised):
            raise FractionalServiceCreditIntegrityError(
                "continuous capacities contain duplicate link IDs"
            )
        object.__setattr__(self, "continuous_capacity_by_link", normalised)

    @property
    def enabled(self) -> bool:
        return self.mode == FRACTIONAL_CREDIT

    @property
    def capacity_by_link(self) -> dict[str, float]:
        return dict(self.continuous_capacity_by_link)

    @property
    def config_hash(self) -> str:
        return stable_hash("fractional-service-credit-config", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "mode": self.mode,
            "continuous_capacity_by_link": [
                [link_id, rate]
                for link_id, rate in self.continuous_capacity_by_link
            ],
            "sending_retention_policy": self.sending_retention_policy,
            "receiving_retention_policy": self.receiving_retention_policy,
            "empty_queue_policy": self.empty_queue_policy,
            "red_signal_policy": self.red_signal_policy,
            "receiving_credit_cap_formula": self.receiving_credit_cap_formula,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            mode=str(payload["mode"]),
            continuous_capacity_by_link=tuple(
                (str(link_id), float(rate))
                for link_id, rate in payload.get(  # type: ignore[misc]
                    "continuous_capacity_by_link", []
                )
            ),
            sending_retention_policy=str(payload["sending_retention_policy"]),
            receiving_retention_policy=str(payload["receiving_retention_policy"]),
            empty_queue_policy=str(payload["empty_queue_policy"]),
            red_signal_policy=str(payload["red_signal_policy"]),
            receiving_credit_cap_formula=str(
                payload["receiving_credit_cap_formula"]
            ),
            version=str(payload["version"]),
        )


@dataclass(frozen=True, slots=True)
class FractionalServiceCreditEvidence:
    """One tick of one sending or receiving account."""

    account_id: str
    resource_type: str
    link_id: str
    tick: int
    continuous_allowance_added: float
    opening_credit: float
    available_whole_service: int
    consumed_service: int
    closing_credit: float
    credit_cap: float
    saturated_at_cap: bool
    linked_packet_ids: tuple[str, ...]
    retention_policy: str
    configuration_hash: str
    executable_semantic_hash: str
    version: str = FRACTIONAL_SERVICE_CREDIT_VERSION
    evidence_hash: str = ""

    def __post_init__(self) -> None:
        if self.resource_type not in ("link_sending", "link_receiving"):
            raise FractionalServiceCreditIntegrityError("unknown credit resource type")
        if self.tick <= 0 or self.available_whole_service < 0 or self.consumed_service < 0:
            raise FractionalServiceCreditIntegrityError("invalid credit tick/count")
        if self.consumed_service > self.available_whole_service:
            raise FractionalServiceCreditIntegrityError(
                "consumed service exceeds available whole service"
            )
        if self.opening_credit < 0 or self.closing_credit < 0:
            raise FractionalServiceCreditIntegrityError("credit cannot be negative")
        object.__setattr__(self, "linked_packet_ids", tuple(self.linked_packet_ids))
        expected = stable_hash("fractional-service-credit-evidence", self._payload())
        if self.evidence_hash and self.evidence_hash != expected:
            raise FractionalServiceCreditIntegrityError("credit evidence hash mismatch")
        object.__setattr__(self, "evidence_hash", expected)

    def _payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "account_id": self.account_id,
            "resource_type": self.resource_type,
            "link_id": self.link_id,
            "tick": self.tick,
            "continuous_allowance_added": self.continuous_allowance_added,
            "opening_credit": self.opening_credit,
            "available_whole_service": self.available_whole_service,
            "consumed_service": self.consumed_service,
            "closing_credit": self.closing_credit,
            "credit_cap": self.credit_cap,
            "saturated_at_cap": self.saturated_at_cap,
            "linked_packet_ids": list(self.linked_packet_ids),
            "retention_policy": self.retention_policy,
            "configuration_hash": self.configuration_hash,
            "executable_semantic_hash": self.executable_semantic_hash,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "evidence_hash": self.evidence_hash}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            account_id=str(payload["account_id"]),
            resource_type=str(payload["resource_type"]),
            link_id=str(payload["link_id"]),
            tick=int(payload["tick"]),
            continuous_allowance_added=float(payload["continuous_allowance_added"]),
            opening_credit=float(payload["opening_credit"]),
            available_whole_service=int(payload["available_whole_service"]),
            consumed_service=int(payload["consumed_service"]),
            closing_credit=float(payload["closing_credit"]),
            credit_cap=float(payload["credit_cap"]),
            saturated_at_cap=bool(payload["saturated_at_cap"]),
            linked_packet_ids=tuple(
                str(item) for item in payload.get("linked_packet_ids", [])
            ),
            retention_policy=str(payload["retention_policy"]),
            configuration_hash=str(payload["configuration_hash"]),
            executable_semantic_hash=str(payload["executable_semantic_hash"]),
            version=str(payload["version"]),
            evidence_hash=str(payload.get("evidence_hash", "")),
        )


class FractionalServiceCreditMixin:
    """Composable shell enabling existing bounded continuous-capacity hooks."""

    def __init__(
        self,
        *args: object,
        fractional_service_credit_config: FractionalServiceCreditConfig,
        executable_semantic_hash: str = "unspecified",
        **kwargs: object,
    ) -> None:
        if not isinstance(
            fractional_service_credit_config, FractionalServiceCreditConfig
        ):
            raise TypeError(
                "fractional_service_credit_config must be FractionalServiceCreditConfig"
            )
        self.fractional_service_credit_config = fractional_service_credit_config
        self.fractional_service_executable_semantic_hash = executable_semantic_hash
        self._fractional_service_credit_evidence: list[
            FractionalServiceCreditEvidence
        ] = []
        if fractional_service_credit_config.enabled:
            for reserved in (
                "parity_sending_capacity_vehicles_per_tick_by_link",
                "parity_receiving_capacity_vehicles_per_tick_by_link",
            ):
                if reserved in kwargs:
                    raise ValueError(
                        f"fractional service-credit extension owns {reserved}"
                    )
            rates = fractional_service_credit_config.capacity_by_link
            kwargs["parity_sending_capacity_vehicles_per_tick_by_link"] = rates
            kwargs["parity_receiving_capacity_vehicles_per_tick_by_link"] = rates
        super().__init__(*args, **kwargs)  # type: ignore[misc]
        if set(fractional_service_credit_config.capacity_by_link) != set(
            self.links  # type: ignore[attr-defined]
        ):
            raise FractionalServiceCreditIntegrityError(
                "continuous capacity config must cover every executable link exactly"
            )

    @property
    def fractional_service_credit_evidence(
        self,
    ) -> tuple[FractionalServiceCreditEvidence, ...]:
        return tuple(self._fractional_service_credit_evidence)

    @property
    def fractional_service_credit_evidence_hash(self) -> str:
        return stable_hash(
            "fractional-service-credit-run-evidence",
            {
                "configuration_hash": self.fractional_service_credit_config.config_hash,
                "executable_semantic_hash": self.fractional_service_executable_semantic_hash,
                "records": [
                    item.to_dict()
                    for item in self._fractional_service_credit_evidence
                ],
            },
        )

    def _uses_parity_sending(self) -> bool:
        return self.fractional_service_credit_config.enabled or super()._uses_parity_sending()  # type: ignore[misc]

    def _uses_parity_receiving(self) -> bool:
        return self.fractional_service_credit_config.enabled or super()._uses_parity_receiving()  # type: ignore[misc]

    def step(self) -> None:
        if not self.fractional_service_credit_config.enabled:
            return super().step()  # type: ignore[misc]
        sending_open = dict(
            self._parity_sending_capacity_carry_by_link_id  # type: ignore[attr-defined]
        )
        receiving_open = dict(
            self._parity_receiving_capacity_carry_by_link_id  # type: ignore[attr-defined]
        )
        event_start = len(self.event_log)  # type: ignore[attr-defined]
        super().step()  # type: ignore[misc]
        new_events = self.event_log[event_start:]  # type: ignore[attr-defined]
        rates = self.fractional_service_credit_config.capacity_by_link
        for link_id in sorted(self.links):  # type: ignore[attr-defined]
            exits = tuple(
                item.packet_id
                for item in new_events
                if item.event_type == EventType.LINK_EXIT
                and item.entity_id == link_id
            )
            entries = tuple(
                item.packet_id
                for item in new_events
                if item.event_type == EventType.LINK_ENTRY
                and item.entity_id == link_id
            )
            sending_close = self._parity_sending_capacity_carry_by_link_id[link_id]  # type: ignore[attr-defined]
            receiving_close = self._parity_receiving_capacity_carry_by_link_id[link_id]  # type: ignore[attr-defined]
            self._fractional_service_credit_evidence.extend(
                (
                    FractionalServiceCreditEvidence(
                        account_id=f"fractional-credit:sending:{link_id}",
                        resource_type="link_sending",
                        link_id=link_id,
                        tick=self.current_tick,  # type: ignore[attr-defined]
                        continuous_allowance_added=rates[link_id],
                        opening_credit=sending_open[link_id],
                        available_whole_service=(
                            self._parity_sending_integer_capacity_by_link_id[link_id]  # type: ignore[attr-defined]
                        ),
                        consumed_service=len(exits),
                        closing_credit=sending_close,
                        credit_cap=1.0,
                        saturated_at_cap=False,
                        linked_packet_ids=exits,
                        retention_policy=(
                            self.fractional_service_credit_config.sending_retention_policy
                        ),
                        configuration_hash=(
                            self.fractional_service_credit_config.config_hash
                        ),
                        executable_semantic_hash=(
                            self.fractional_service_executable_semantic_hash
                        ),
                    ),
                    FractionalServiceCreditEvidence(
                        account_id=f"fractional-credit:receiving:{link_id}",
                        resource_type="link_receiving",
                        link_id=link_id,
                        tick=self.current_tick,  # type: ignore[attr-defined]
                        continuous_allowance_added=rates[link_id],
                        opening_credit=receiving_open[link_id],
                        available_whole_service=(
                            self._parity_receiving_integer_capacity_by_link_id[link_id]  # type: ignore[attr-defined]
                        ),
                        consumed_service=len(entries),
                        closing_credit=receiving_close,
                        credit_cap=float(ceil(rates[link_id]) + 1),
                        saturated_at_cap=(
                            receiving_close >= ceil(rates[link_id]) + 1
                        ),
                        linked_packet_ids=entries,
                        retention_policy=(
                            self.fractional_service_credit_config.receiving_retention_policy
                        ),
                        configuration_hash=(
                            self.fractional_service_credit_config.config_hash
                        ),
                        executable_semantic_hash=(
                            self.fractional_service_executable_semantic_hash
                        ),
                    ),
                )
            )


class FractionalServiceCreditLoadingEngine(
    FractionalServiceCreditMixin,
    LoadingEngine,
):
    """Standard loader plus opt-in continuous service-credit realization."""


def service_credit_config_for_executable(
    executable,
    *,
    mode: str,
) -> FractionalServiceCreditConfig:
    """Adapt compiler continuous capacities without altering loader declarations."""

    rates = []
    for link in executable.resolved_links:
        if link.capacity_veh_per_hour_per_lane is None or link.lane_count is None:
            raise FractionalServiceCreditIntegrityError(
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
    return FractionalServiceCreditConfig(
        mode=mode,
        continuous_capacity_by_link=tuple(rates),
    )
