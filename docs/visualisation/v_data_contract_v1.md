# V1 data contract

## Identity and versioning

Every bundle validates as `uc.visualisation.run.v1`. The run record includes
run, topology, configuration, and model-profile identities; topology and config
SHA-256 hashes; tick duration; time basis; run bounds; event and packet counts;
status; and a status reason. A bundle is rejected if topology IDs or hashes do
not agree, events reference unknown packets, cumulative series do not cover the
topology, or replay ticks are not complete and ordered.

The JSON file contains only declared serialisable records. No Python object,
enum object, mapping proxy, or engine instance crosses the boundary.

## Evidence categories

Each major payload has an `EvidenceDescriptor.semantic_status` drawn from:

1. `canonical_event_data`
2. `immutable_topology_metadata`
3. `engine_owned_materialised_state`
4. `event_derived_scientific_projection`
5. `validation_output`
6. `provenance_configuration_metadata`
7. `presentation_only_interpolation`

Descriptions also name the source and, where relevant, units, time basis,
counting basis, boundary direction, and aggregation window. Optional values use
explicit field-availability labels, so unavailable, not applicable, unknown,
not-yet-observed, omitted, and numeric zero remain distinct.

## Records

- `run`: identity, completion boundary, time basis, and scale.
- `provenance`: code label, input artifacts, source digest, assumptions, config.
- `topology`: canonical nodes, directed links, movements, static SI metadata.
- `packets`: packet and demand IDs, declared route intent, optional enrichment.
- `event_stream`: canonical sequence number, packet, event type, entity, tick.
- `replay_states`: complete Python-derived end-of-tick scientific states.
- `cumulative_link_series`: entry, exit, and storage curves from the existing
  Python cumulative-count projection.
- `validation`: explicit status, checks, and limitations.
- `presentation`: non-scientific layout coordinates and interpolation warning.

Canonical event entity semantics remain those of `core.event.Event`. V1 does
not invent movement decisions where the canonical event schema does not contain
them. Static movement IDs are exposed from immutable topology, but allocation
traces are not claimed by the fixture.

## Traffic terminology

V1's chart is not an ambiguous “flow” chart. It reports cumulative unit-packet
entries at the upstream link boundary and exits at the downstream link boundary,
through an inclusive physical tick. Storage is entries minus exits, in packets.
The window is one tick and the source is Python's
`cumulative_count_projection`.

The API endpoints are:

- `GET /api/v1/health`
- `GET /api/v1/contract`
- `GET /api/v1/runs`
- `GET /api/v1/runs/{run_id}/manifest`
- `GET /api/v1/runs/{run_id}/events`
- `GET /api/v1/runs/{run_id}/replay`
- `GET /api/v1/runs/{run_id}/links/{link_id}/cumulative-counts`

There are no POST, PUT, PATCH, or DELETE simulation routes.
