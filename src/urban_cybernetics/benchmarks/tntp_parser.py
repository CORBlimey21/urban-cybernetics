"""Parsers for Transportation Networks for Research Core Team TNTP files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_METADATA_PATTERN = re.compile(r"^<([^>]+)>\s*(.*)$")
_ORIGIN_PATTERN = re.compile(r"^Origin\s+(\d+)\s*$", re.IGNORECASE)
_DEMAND_PATTERN = re.compile(r"(\d+)\s*:\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))")


@dataclass(frozen=True)
class TntpLink:
    """One directed TNTP network link with a stable file-order edge ID."""

    edge_id: int
    tail: int
    head: int
    capacity: float
    length: float
    free_flow_time: float
    bpr_alpha: float
    bpr_beta: float
    speed_limit: float | None = None
    toll: float | None = None
    link_type: int | None = None


@dataclass(frozen=True)
class TntpNetwork:
    """Parsed TNTP network data."""

    metadata: dict[str, Any]
    links: list[TntpLink]
    nodes: list[int]


@dataclass(frozen=True)
class TntpTrips:
    """Parsed TNTP OD demand data."""

    metadata: dict[str, Any]
    od_demand: dict[tuple[int, int], float]
    total_demand: float
    origins: list[int]


def _coerce_metadata_value(value: str) -> Any:
    text = value.strip()
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    return int(number) if number.is_integer() else number


def _metadata_key(raw_key: str) -> str:
    return raw_key.strip().lower().replace(" ", "_")


def _parse_metadata_line(line: str) -> tuple[str, Any] | None:
    match = _METADATA_PATTERN.match(line.strip())
    if not match:
        return None
    return _metadata_key(match.group(1)), _coerce_metadata_value(match.group(2))


def _strip_record(line: str) -> str:
    return line.split("~", 1)[0].replace(";", " ").strip()


def parse_tntp_network(path: Path) -> TntpNetwork:
    """Parse a TNTP network file into directed link records."""

    metadata: dict[str, Any] = {}
    links: list[TntpLink] = []
    in_records = False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        metadata_item = _parse_metadata_line(line)
        if metadata_item:
            key, value = metadata_item
            metadata[key] = value
            if key == "end_of_metadata":
                in_records = True
            continue

        if not in_records or line.startswith("~"):
            continue

        fields = _strip_record(line).split()
        if len(fields) < 7:
            continue

        edge_id = len(links)
        link_type = int(float(fields[9])) if len(fields) > 9 else None
        links.append(
            TntpLink(
                edge_id=edge_id,
                tail=int(fields[0]),
                head=int(fields[1]),
                capacity=float(fields[2]),
                length=float(fields[3]),
                free_flow_time=float(fields[4]),
                bpr_alpha=float(fields[5]),
                bpr_beta=float(fields[6]),
                speed_limit=float(fields[7]) if len(fields) > 7 else None,
                toll=float(fields[8]) if len(fields) > 8 else None,
                link_type=link_type,
            )
        )

    nodes = sorted({node for link in links for node in (link.tail, link.head)})
    expected_links = metadata.get("number_of_links")
    if expected_links is not None and int(expected_links) != len(links):
        raise ValueError(f"Expected {expected_links} links in {path}, parsed {len(links)}")

    return TntpNetwork(metadata=metadata, links=links, nodes=nodes)


def parse_tntp_trips(path: Path, include_zero_demand: bool = False) -> TntpTrips:
    """Parse a TNTP trip table into an OD demand mapping."""

    metadata: dict[str, Any] = {}
    od_demand: dict[tuple[int, int], float] = {}
    origins: set[int] = set()
    current_origin: int | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        metadata_item = _parse_metadata_line(line)
        if metadata_item:
            key, value = metadata_item
            metadata[key] = value
            continue

        origin_match = _ORIGIN_PATTERN.match(line)
        if origin_match:
            current_origin = int(origin_match.group(1))
            origins.add(current_origin)
            continue

        if current_origin is None:
            continue

        for destination_text, demand_text in _DEMAND_PATTERN.findall(line):
            destination = int(destination_text)
            demand = float(demand_text)
            if include_zero_demand or demand != 0.0:
                od_demand[(current_origin, destination)] = demand

    total_demand = sum(od_demand.values())
    expected_total = metadata.get("total_od_flow")
    if expected_total is not None and abs(float(expected_total) - total_demand) > 1e-6:
        raise ValueError(f"Expected total OD flow {expected_total} in {path}, parsed {total_demand}")

    return TntpTrips(
        metadata=metadata,
        od_demand=od_demand,
        total_demand=total_demand,
        origins=sorted(origins),
    )
