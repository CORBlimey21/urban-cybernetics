# Boreenmanna Road–South Link Road OSM ingestion milestone v1

## Status and evidence boundary

This milestone ingests one pinned local export and does not fetch or consult live OSM data. The original file is never rewritten.

| Field | Value |
| --- | --- |
| Source filename | `Boreenmanna -South Link Junction.osm` |
| Source format | OpenStreetMap XML 0.6 |
| Generator | `openstreetmap-cgimap 2.1.0 (908582 spike-06.openstreetmap.org)` |
| Byte length | 905,366 |
| Whole-file SHA-256 | `7b879dea3298adffc4c264bdca3836b5ec62536d8b6450d8602a482f97088d77` |
| Parsed-content hash | `447fa3a3359c473ea2f1c9c56e61d54d1f093bee57686e61e5717d26f0256f5a` |
| OSM file-evidence hash | `078f536ef4e8a190ffcb527f7f9a24216d39e47f91e03d6247d6d3e842966ea8` |
| Bounds | `51.8910440,-8.4634530` to `51.8930000,-8.4590650` |
| Record timestamp range | `2011-04-03T20:57:43Z` to `2026-08-03T17:29:34Z` |
| Inventory | 3,321 nodes; 615 ways; 12 relations |
| Parser | `uc.osm-xml-parser.v1` |
| Evidence schema | `uc.osm-xml-evidence.v1` |

The parsed-content hash canonicalizes top-level record ordering while preserving ordered way-node references and ordered relation members. The byte hash deliberately remains sensitive to the exact pinned serialization. All node/way/relation attributes, tags, coordinates, node references, and relation memberships remain in the source-evidence object, including unsupported records and incomplete relation membership.

The repository test fixture `tests/fixtures/osm/boreenmanna_south_link_compact.osm` is a deterministic 25,357-byte derivative containing the ten retained ways, their 83 referenced nodes, and the restriction relation. Its SHA-256 is `9eb6a0c8408ebe5e84a33458103867e64fbb4965b3cc1a899a4dee76ee362e64`. It is not represented as the original export and is used only to keep tests independent of a user-specific path.

## Adapter support

The narrow XML adapter supports OSM 0.6 nodes, WGS84 coordinates, ways, ordered node references, relations, typed members and roles, record metadata, bounds, arbitrary tags, highway/access/service classification, `oneway`, lane tags, speed tags, restriction relations, traffic-signal heads, and crossings. Missing way-node references, duplicate tag keys, duplicate IDs, malformed XML, or unsupported root/version combinations are rejected.

Incomplete relation members are not treated like missing way geometry. Map exports routinely contain partial long relations: absent relation members are retained and diagnosed, never fabricated. The adapter does not download data, follow relation references, or implement replication/Overpass.

## Reviewed operational boundary

Boundary `boreenmanna-south-link-operational-complex-v1` uses stable explicit way IDs rather than a centroid or visual heuristic:

- South Link Road carriageways and southbound ramp: `110781522`, `279050194`, `279050199`, `96385702`;
- Boreenmanna Road approach/carriageway chain: `1242275936`, `32670121`, `279054333`, `32670070`, `477791936`, `279054332`.

Extraction configuration hash: `0cecba801b35f4c6c8ac2e56868c63c911489e5a2949613c9d0e4aeab85f5327`.

Service roads and local accesses do not participate. Footways and other non-vehicle features are excluded from the vehicle graph. Signal heads and crossings lying on retained ways remain control/context evidence. Other vehicle roads, buildings, routes, administrative boundaries, residential streets, driveways, and distant ways are classified rather than silently discarded.

Classification counts for the complete export are:

| Classification | Count |
| --- | ---: |
| Retained executable road evidence | 85 (75 ordinary geometry nodes plus 10 ways) |
| Retained control/restriction evidence | 7 (six signal nodes and one restriction relation) |
| Retained contextual evidence | 2 signalised crossing nodes |
| Excluded outside operational boundary | 3,332 |
| Excluded non-vehicle feature | 23 |
| Excluded unsupported feature | 499 |

Extraction hash: `e2a952a553cbcdb781c27921c4c8dc189dae199b2353762e66a40e9625ebf869`.

The boundary contains 83 source nodes, ten source ways, 21 physical spans, and 22 directed segments. The physical polylines total 1,543.632 m; the directed representation totals 1,930.588 m because the 386.955 m two-way eastern approach is represented in both directions.

## Way splitting and geometry

A retained way is split only at:

1. its endpoints;
2. nodes shared by multiple retained vehicle ways;
3. retained OSM signal/control nodes;
4. relevant restriction via-nodes;
5. explicit boundary cut nodes, if configured;
6. crossings only when `split_at_crossings=true` (false here).

Intermediate shape nodes remain in each segment polyline and do not create meaningless loader links. Relevant tag changes already imply separate OSM ways and therefore natural endpoints. Segment identity is:

`osm-way:{way-id}:segment:{ordered-split-ordinal}:{tail}-to-{head}:{direction}`.

The `-to-` token deliberately avoids the frozen loader's reserved `->` queue-boundary delimiter. This distinction became executable-contract-relevant when the synthetic experiment pass began materialising queues.

Input record ordering cannot change way-node order, split ordinal, segment identity, geometry hash, or segment hash. Every segment retains the source way ID, exact source node interval, source tags, direction, coordinate source, and geometry derivation.

Length uses the ordered WGS84 coordinates and a spherical Haversine polyline with radius 6,371,008.8 m (`uc.geometry.haversine-polyline`, version 1). No geometry simplification or visual/manual length estimate is applied. Fourteen control-created spans are below the configured 50 m approach-storage target and emit `UC.OSM.EXTRACTION.SHORT_CONTROL_SEGMENT`; this is evidence about numerical/network resolution, not a reason to merge away control points.

## Observed road semantics

| OSM way | Highway | Direction | Lanes | Maxspeed | Role |
| --- | --- | --- | --- | --- | --- |
| `110781522` | trunk | one-way | 2 | 60 km/h | northbound South Link approach/departure |
| `279050194` | trunk | one-way | 2 | 60 km/h | southbound South Link through carriageway |
| `279050199` | trunk | one-way | 2 | 100 km/h | northbound South Link approach |
| `96385702` | trunk_link | one-way | 1 | 60 km/h | channelised South Link connector/ramp |
| `1242275936` | secondary | two-way | 2 total | 50 km/h | eastern Boreenmanna approach |
| `32670121` | secondary | one-way | 2 | 50 km/h | westbound Boreenmanna approach segment |
| `279054333` | secondary | one-way | 2 | 60 km/h | westbound internal/connector chain |
| `32670070` | secondary | one-way | missing | 60 km/h | eastbound internal/connector chain |
| `477791936` | secondary | one-way | 1 | 50 km/h | eastbound channelised connector |
| `279054332` | secondary | one-way | 1 | 50 km/h | eastbound Boreenmanna departure |

All retained lengths are geometrically inferred, not observed OSM length tags. Speed and nine way-level lane values are observed. The missing `32670070` lane count requires a configured default or review. No retained way supplies capacity, jam density, backward-wave speed, or `turn:lanes`. Continuous storage, capacity/tick, travel times, and executable integer lags/capacities/storage therefore cannot be source-supported until the upstream physical values are supplied.

No retained way contains `access`, `vehicle`, `motor_vehicle`, or `motorcar` restrictions. The four retained trunk/trunk-link ways record `foot=no` and `bicycle=yes`; these tags remain raw source evidence but do not establish any missing motor-vehicle permission. For this narrow slice, motor-vehicle participation is bounded by the explicitly reviewed vehicle-highway IDs, not inferred from a complete OSM access hierarchy.

## Movements and restrictions

Directed continuity produces 26 candidate movements. Ordinary continuous movements are compiler inferences. Two immediate reversals on the two-way eastern approach are explicitly marked unresolved during the strict pass: topology alone does not demonstrate affirmative U-turn allocation.

The export contains restriction relation `17071174`, `no_right_turn`, via node `11543659169`. Its `from` way `477599183` and `to` way `1242275930` are absent from the pinned export. The via-node touches retained way `1242275936`, so the relation is retained as relevant control evidence, but it cannot be mapped to a valid retained movement. Diagnostic: `UC.OSM.RESTRICTION.INCOMPLETE_EXPORT`. No prohibited movement is invented from this partial relation.

## Lane and queue representation audit

No retained way has `turn:lanes`, `turn:lanes:forward`, or `turn:lanes:backward`. Total/directional lane counts do not establish microscopic lane connectivity, merge/diverge allocation, movement-specific queues, or signal-compatible lane groups.

- Shared-link strict FIFO is conditionally supportable after physical review because it needs directed links but no lane-to-turn mapping.
- Movement-partial FIFO is not source-supported: candidate movements exist, but movement-specific queue allocation does not.
- Explicit lane-group queues are not source-supported: lane-to-turn connectivity and signal-group-compatible lane groups are absent.

The reviewed candidate enables the shared-link representation only as **a conservative executable representation selected because detailed lane allocation is insufficiently supported by evidence**. This is not a claim that the physical junction has a single shared lane group. No ablation or comparative scientific result is claimed.

## Signal audit

Six retained nodes are tagged as traffic-signal heads: `367554868`, `1116982191`, `10218634801`, `10218634802`, `10218634803`, and `13900917292`. Crossing nodes `367552448` and `13900917293` are retained context. Direction tags exist on the signal heads, but the export supplies no controller identity/ownership, movement-to-signal group binding, phase/stage plan, duration, cycle, offset, or stop-line/controller relation.

Consequently the export cannot emit `uc.resolved-fixed-time-signal-plan.v1`. The compiler preserves signalisation and emits `UC.SIGNAL.OSM_EVIDENCE_UNRESOLVED` for controller ownership, movement assignment, and fixed-time plan at every signal head, followed by `UC.SIGNAL.PLAN_REFUSED`. It does not treat the complex as unsignalised and does not create a default or synthetic plan.

## Pass 1: source-strict audit

Road-class lane/speed/capacity defaults, jam-density defaults, backward-wave defaults, signal defaults, detailed lane grouping, and shared-FIFO fallback are disabled. The existing unit movement-priority convention remains visible as compiler-default provenance; it is not OSM observation.

Disposition: `unresolved_non_executable`.

Unresolved mandatory fields:

- 22 per-lane capacities;
- 22 jam densities;
- 22 backward-wave speeds;
- one lane count (`32670070` segment);
- two U-turn permissions.

There are 69 unresolved targets. No physical executable derivations are emitted because no link is complete. No canonical executable topology, fixed-time plan, or executable semantic hash is exposed.

Compilation identity: `faef44452a0b073b38571a53e1f2027068afcb7a2b41c8cf895065666c3d34b4`.

Evidence-bundle hash: `7a0a2729e41bbb8245d911f87319c3184c8ae82bbf0df40982a6f4b81adbf98a`.

## Pass 2: reviewed road candidate

This pass is an audit candidate, not a calibrated model. It adds only explicit, hash-bound reviewed policy:

- missing secondary lane count: 1 lane;
- per-lane capacity priors: secondary 1,500 veh/h/lane; trunk/trunk_link 1,800 veh/h/lane;
- jam density prior: 150 veh/km/lane;
- backward-wave speed prior: 5 m/s;
- two same-way immediate reversals overridden to prohibited by stable review records;
- shared-link representation enabled;
- no signal timing default or synthetic demonstration plan.

These values are defaulted/overridden provenance, never source observations, and are explicitly uncalibrated. Continuous/discrete derivations record their numerical effects. With a one-second tick, low hourly capacities trigger the loader-compatible floor/minimum-one policy; 28 minimum-one warnings and 32 relative-error warnings quantify the distortion.

Each reviewed prior is also represented by an immutable assumption record containing a stable ID, selected value and unit, actor, source, rule ID, reason, and deterministic hash. The two movement repairs remain separate immutable compiler overrides so the original unresolved U-turn evidence is retained.

The road topology validates and produces canonical topology artefact hash `7e7d925c9028b6d78350fc31a9f9f76b07bdc2ae59fc879c5f4228874ccb8c14`. Signal control remains unresolved, so the final disposition is still `unresolved_non_executable`, `require_executable()` refuses, and there is no executable semantic hash.

Compilation identity: `4a746c15a74a30f5c75c62ee89e4e493b7c50438a216dc42adb5f8d1f8957296`.

Evidence-bundle hash: `a7e50e8145ad4d64cf38b8096e0f77a8fcba72baa22b12f2a708508dfa17da9a`.

## Evidence output

The generated package is `outputs/evidence/boreenmanna_south_link_junction_milestone_v1.json` (`uc.cork-junction-evidence-package.v1`). It contains the full parsed source evidence, extraction configuration/decisions, split segments and source mappings, restriction/signal/lane inventories, representation assessment, normalized compiler graph, strict and reviewed bundles, assumptions, overrides, provenance, physical derivations, diagnostics, dispositions, and all nested hashes.

Package hash: `c3bcb16a830945b6a8ce2ece0ba7d4e5c2ddb2b44e2ecedb7067c0530ea0661c`.

Serialized file SHA-256: `18340a74742ee28bb28cd71e5f8896d225bedfc7edfeee54a29682ea1026075a`.

Round-trip constructors recompute source parsed/file evidence, extraction configuration, geometry/segment, restriction, diagnostics, compiler evidence, compilation identity, evidence-bundle, and enclosing package hashes. The output directory is intentionally ignored by Git; the compact test fixture and source-hash documentation make the repository suite self-contained.

## Limitations and next step

This is not yet a faithful executable junction model. Capacity/density/wave priors are uncalibrated; `turn:lanes` and lane-to-movement evidence are absent; the restriction export is incomplete; U-turn policy is review-supplied; signal controller ownership, grouping, and timing are absent; short control spans may provide poor queue storage; access/conditional restriction semantics remain narrow; and no route demand or empirical movement validation has been performed.

The next smallest defensible step is a field-reviewed control and movement dossier for these exact 22 segments: confirm the missing lane count, legal/illegal turn matrix (including U-turns), stop lines and controller grouping, movement-to-signal groups, and one observed fixed-time timing sheet. Add those facts as immutable review evidence/overrides, rerun with the uncalibrated physical priors still clearly separated, and execute one deterministic low-demand conservation/replay smoke test under shared-link FIFO. Lane-group comparisons should wait for defensible lane-to-turn allocation evidence.
