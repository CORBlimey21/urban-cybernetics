# V2 network layouts

Urban Cybernetics treats network layout as versioned presentation metadata. A
layout can move nodes, route screen edges, place labels, and determine viewport
fit. It cannot change canonical topology, topology hashes, physical link
metadata, routes, events, replay state, allocation evidence, validation, or
scientific projections.

## Contract

`uc.visualisation.layout.v1` records:

- stable layout ID, label, kind, version, and preferred status;
- geographic status, coordinate basis and units, optional CRS;
- source, provenance, and declared/imported/generated origin;
- generator identity and deterministic seed when generated;
- complete node-coordinate coverage and optional declared edge routes;
- warnings plus explicit distance and angle semantics.

The run presentation record declares all available layouts and one default. Its
legacy `node_positions` view mirrors the default so persisted V1 clients and
artifacts remain readable. Backend validation requires unique layout IDs and
exactly the canonical node set. Layout metadata is outside `VTopology`, so it
does not participate in topology identity.

## Default precedence

The stable preference order is:

1. explicitly preferred declared benchmark/fixture schematic;
2. valid geographic layout with declared CRS;
3. deterministic generated schematic;
4. deterministic circular fallback.

Only layouts actually included in an artifact are offered by the browser. A
previous selection is retained across artifact changes when that layout ID is
available; otherwise the artifact default is selected.

## Sioux Falls

`sioux_falls_published_schematic_v1` supplies normalized coordinates for all 24
canonical nodes. The placement was visually reconstructed from the canonical
Sioux Falls diagram supplied with the V2 layout task. The image was used only to
place nodes. Link incidence and IDs continue to come exclusively from the
repository's TNTP-backed `CanonicalTopology`; no topology was OCR'd or inferred.

The arrangement preserves the familiar upper 1–2 corridor, central 10–16
corridor, eastern 7–18 branch, lower 14–15–19 and 23–22 layers, and 13–24–21–20
boundary. It is explicitly non-geographic. Screen distances do not encode TNTP
link length, and screen angles have no physical meaning.

## Generated and geographic foundations

The generated schematic uses deterministic undirected hop layers with a stable
generator version and seed. Coordinates are persisted in the artifact, so the
layout cannot jump between sessions. It is an inspection aid, not a physical
embedding. Circular placement remains an explicit last-resort alternative.

Geographic layout records are supported by the schema but none are claimed for
Sioux Falls. A geographic layout must declare a CRS and coordinate units. The
renderer fits it as presentation coordinates; it does not treat longitude and
latitude as planar physical distance or replace canonical link lengths.

## Directed edges, labels, and view state

Opposing directed links receive a small symmetric screen-space offset and their
own arrows and hit paths. This is not lane geometry or road geometry. Link IDs
are hidden by default and remain visible for the selected link; node IDs are
shown inside nodes. Optional node, link, and activity layers can be toggled.

Wheel zoom, drag pan, fit, reset, selected layout, and layer toggles are browser
presentation state. Layout changes preserve replay tick and selected scientific
evidence. They do not trigger a replay fold or projection request.

## Known limitations

- The supplied Sioux Falls diagram does not establish a more specific source
  provenance than visual reconstruction from the task reference.
- Generated hop-layer layouts prioritize determinism and maintainability over
  sophisticated crossing minimization.
- Edge routing currently uses shallow screen-space offsets; persisted edge-route
  control points are reserved by the contract but not yet authored.
- Geographic import and projection tooling are extension points, not part of
  this milestone.
