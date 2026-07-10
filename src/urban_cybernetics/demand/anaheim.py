"""Anaheim TNTP OD demand loader for pre-packet manifests."""

from __future__ import annotations

from pathlib import Path

from urban_cybernetics.benchmarks.anaheim import ANAHEIM_TRIPS_PATH
from urban_cybernetics.benchmarks.tntp_parser import parse_tntp_trips
from urban_cybernetics.demand.manifest import (
    DemandManifest,
    DemandManifestSourceMetadata,
    DepartureSchedule,
    FixedDepartureSchedule,
    ODDemandDeclaration,
)
from urban_cybernetics.topology.anaheim import load_anaheim_topology
from urban_cybernetics.topology.canonical import CanonicalTopology


ANAHEIM_DEMAND_INTERPRETATION_ASSUMPTIONS = (
    "TNTP Anaheim trip-table values are interpreted as unit vehicle-equivalent packet counts before optional scaling.",
    "Only nonzero OD pairs are converted into demand declarations.",
    "Source zone IDs are mapped to canonical Anaheim node IDs through topology node provenance.",
    "Raw OD demand remains route-free until a separate route-resolution step.",
)


def load_anaheim_demand_manifest(
    *,
    topology: CanonicalTopology | None = None,
    trips_path: Path = ANAHEIM_TRIPS_PATH,
    scale_factor: float = 1.0,
    max_pairs: int | None = None,
    min_quantity_packets: int = 1,
    max_total_quantity_packets: int | None = None,
    departure_schedule: DepartureSchedule | None = None,
    cohort_id: str | None = None,
    authority_id: str | None = None,
) -> DemandManifest:
    """Load Anaheim OD demand as immutable pre-packet declarations."""

    if scale_factor <= 0:
        raise ValueError("scale_factor must be positive")
    if max_pairs is not None and max_pairs <= 0:
        raise ValueError("max_pairs must be positive when supplied")
    if min_quantity_packets <= 0:
        raise ValueError("min_quantity_packets must be positive")
    if max_total_quantity_packets is not None and max_total_quantity_packets <= 0:
        raise ValueError("max_total_quantity_packets must be positive when supplied")

    resolved_topology = topology or load_anaheim_topology()
    source_zone_to_canonical = {
        int(node.source_node_id): node.node_id for node in resolved_topology.nodes
    }
    trips = parse_tntp_trips(trips_path)
    schedule = departure_schedule or FixedDepartureSchedule(departure_tick=0)
    declarations: list[ODDemandDeclaration] = []
    total_quantity = 0

    for source_pair_index, ((origin_zone, destination_zone), source_quantity) in enumerate(
        sorted(trips.od_demand.items()),
        start=1,
    ):
        if max_pairs is not None and len(declarations) >= max_pairs:
            break
        quantity_packets = round(source_quantity * scale_factor)
        if quantity_packets < min_quantity_packets:
            continue
        if max_total_quantity_packets is not None:
            remaining_quantity = max_total_quantity_packets - total_quantity
            if remaining_quantity <= 0:
                break
            quantity_packets = min(quantity_packets, remaining_quantity)

        try:
            origin_node_id = source_zone_to_canonical[origin_zone]
            destination_node_id = source_zone_to_canonical[destination_zone]
        except KeyError as exc:
            raise KeyError(
                f"Anaheim OD zone {exc.args[0]} has no canonical node mapping"
            ) from exc

        declarations.append(
            ODDemandDeclaration(
                demand_id=(
                    f"anaheim-od:{origin_zone:03d}->{destination_zone:03d}:"
                    f"{source_pair_index:04d}"
                ),
                origin_node_id=origin_node_id,
                destination_node_id=destination_node_id,
                quantity_packets=quantity_packets,
                departure_schedule=schedule,
                cohort_id=cohort_id,
                authority_id=authority_id,
                source_origin_zone_id=str(origin_zone),
                source_destination_zone_id=str(destination_zone),
                source_quantity_value=source_quantity,
            )
        )
        total_quantity += quantity_packets

    source_metadata = DemandManifestSourceMetadata.from_path(
        source_name="Anaheim",
        source_format="TNTP trips",
        source_file_path=trips_path,
        source_metadata_items=tuple(
            sorted(
                (
                    ("parsed_nonzero_od_pairs", str(len(trips.od_demand))),
                    ("parsed_total_od_flow", str(trips.total_demand)),
                    *(
                        (str(key), str(value))
                        for key, value in trips.metadata.items()
                    ),
                )
            )
        ),
        interpretation_assumptions=ANAHEIM_DEMAND_INTERPRETATION_ASSUMPTIONS,
        scaling_assumptions=(
            f"scale_factor={scale_factor}",
            f"min_quantity_packets={min_quantity_packets}",
            f"max_pairs={max_pairs}",
            f"max_total_quantity_packets={max_total_quantity_packets}",
            "scaled source quantities are rounded to the nearest integer unit packet",
        ),
    )
    return DemandManifest(
        manifest_id="anaheim_od_demand_v1",
        topology_id=resolved_topology.topology_id,
        topology_hash=resolved_topology.topology_hash,
        declarations=tuple(declarations),
        source_metadata=source_metadata,
    )
