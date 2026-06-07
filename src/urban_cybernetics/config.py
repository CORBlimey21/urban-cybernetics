"""Shared repository paths and Cork graph-adapter constants."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    """Filesystem locations used by migrated scripts and adapters."""

    root: Path
    data: Path
    outputs: Path
    maps: Path
    experiments: Path
    graphs: Path
    scenarios: Path


@dataclass(frozen=True)
class Landmark:
    """Named WGS84 coordinate used by migrated Cork graph helpers."""

    name: str
    latitude: float
    longitude: float


def get_project_paths() -> ProjectPaths:
    """Return repository paths relative to the installed source tree."""

    root = Path(__file__).resolve().parents[2]
    data = root / "data"
    outputs = root / "outputs"
    return ProjectPaths(
        root=root,
        data=data,
        outputs=outputs,
        maps=outputs / "maps",
        experiments=root / "experiments",
        graphs=data / "graphs",
        scenarios=data / "manifests",
    )


CORK_PLACE_QUERY = "Cork, County Cork, Ireland"
MAIN_ROAD_FILTER = (
    '["highway"~"motorway|trunk|primary|secondary|tertiary|motorway_link|'
    'trunk_link|primary_link|secondary_link|tertiary_link"]'
)

FALLBACK_SPEED_KPH = 35.0
DEFAULT_SPEED_KPH_BY_HIGHWAY = {
    "motorway": 100.0,
    "motorway_link": 60.0,
    "trunk": 80.0,
    "trunk_link": 50.0,
    "primary": 60.0,
    "primary_link": 45.0,
    "secondary": 50.0,
    "secondary_link": 40.0,
    "tertiary": 40.0,
    "tertiary_link": 35.0,
    "residential": 30.0,
    "unclassified": 30.0,
    "living_street": 20.0,
    "service": 15.0,
}

FALLBACK_ROUTING_WEIGHT_MULTIPLIER = 1.35
ROUTING_WEIGHT_MULTIPLIER_BY_HIGHWAY = {
    "motorway": 1.0,
    "motorway_link": 1.0,
    "trunk": 1.0,
    "trunk_link": 1.0,
    "primary": 1.0,
    "primary_link": 1.0,
    "secondary": 1.05,
    "secondary_link": 1.05,
    "tertiary": 1.15,
    "tertiary_link": 1.15,
    "residential": 1.35,
    "unclassified": 1.35,
    "living_street": 1.6,
    "service": 1.8,
}

ORIGIN_LANDMARK = Landmark("Bishopstown", 51.8857, -8.5312)
DESTINATION_LANDMARK = Landmark("Patrick Street / Opera Lane", 51.8987, -8.4711)

SIMULATION_ORIGINS = (
    Landmark("Bishopstown", 51.8857, -8.5312),
    Landmark("CUH", 51.8850, -8.4947),
    Landmark("UCC", 51.8929, -8.4924),
    Landmark("Douglas", 51.8836, -8.4328),
    Landmark("Togher", 51.8796, -8.4957),
    Landmark("Airport Road", 51.8493, -8.4911),
    Landmark("Blackpool", 51.9102, -8.4765),
    Landmark("Mayfield", 51.9108, -8.4382),
)
RESIDENTIAL_ORIGINS = SIMULATION_ORIGINS

CITY_CENTRE_DESTINATIONS = (
    Landmark("Patrick Street / Opera Lane", 51.8987, -8.4711),
    Landmark("Grand Parade / Washington Street", 51.8978, -8.4756),
    Landmark("South Mall / Parnell Place", 51.8975, -8.4692),
    Landmark("Merchant's Quay / St Patrick's Quay", 51.9001, -8.4677),
)

CANONICAL_SELFISH_MANIFEST_FILENAME = "canonical_selfish_batch_manifest_v1.json"

