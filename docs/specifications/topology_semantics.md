**Status:** specification.
**Scope:** defines what topology is, what it is permitted to hold, how canonical IDs are assigned, and how topology equality is established across runs.
**Non-scope:** does not define loading mechanics, routing algorithms, governance state, or OSMnx import procedures.

---

### What Topology Is

Topology is the static directed graph of physical infrastructure that forms the substrate over which simulation dynamics occur. It answers exactly one question: what physically exists and how is it connected? It does not answer what is happening on it, how congested it is, or what constraints are currently in force.

Topology is fixed for the lifetime of an experiment run. If two runs use different topologies, their outputs are not directly comparable. Topology equality is determined by hash, not by visual similarity or shared OSM origin.

---

### Canonical IDs, Provenance IDs, and Adapter IDs

These are three distinct identifier types and must never be conflated.

**Canonical IDs** are assigned by the framework at topology import time. They are the primary keys used in all scientific outputs, artifact references, event logs, and cross-run comparisons. They are stable within a committed topology version.

**Provenance IDs** are OSM node and way IDs. They record where the topology data came from. They are stored as metadata on topology records and are useful for tracing back to source data, but they are not used as primary keys anywhere in the framework. OSM IDs may change between OSM snapshots; canonical IDs do not.

**Adapter IDs** are NetworkX node and edge keys assigned when a topology is loaded into a NetworkX graph for routing computation. They are ephemeral, local to the adapter, and must not appear in any canonical output or cross-run reference.

---

### Immutable Link Metadata

Every link record carries the following fields. All are immutable after the topology hash is computed.

- canonical link ID
- head node canonical ID
- tail node canonical ID
- length in metres
- declared static capacity metadata in vehicles per hour per lane
- free-flow speed in metres per second
- jam density in vehicles per kilometre per lane
- backward wave speed in metres per second
- lane count
- geometric polyline in WGS84 coordinates
- OSM way ID and OSM snapshot date as provenance metadata

**Declared static capacity metadata** is a calibrated physical parameter recorded at topology import time. It is not the effective capacity during a run. Effective capacity is a function of declared static capacity metadata plus governance state — signal timings, closures, access restrictions — and is computed by the loading engine at runtime. Governance interventions do not mutate the topology record; they create governance state entries that the loading engine reads alongside topology metadata.

The base packetised loading kernel may derive two static loading parameters from this metadata:

- packet storage capacity from length, lane count, and jam density
- free-flow traversal time in ticks from length, free-flow speed, and timestep duration

These derived values are immutable once the link record is built. They are not live occupancy, current density, observed speed, current travel time, active queue length, or effective runtime capacity. Dynamic quantities remain loading-engine-owned event records or derived views.

For academic LTM parity planning, canonical topology links also expose a lane-aware physical-capacity calculation and a static physical-parameter resolution path. This is distinct from the legacy loading adapter. The legacy adapter continues to produce the declared integer loading capacities used by current simulations; the parity-resolution path reports whether the physical metadata is sufficient and internally consistent for a future parity profile.

The M1 parity-resolution path is allowed to reject a link for missing physical metadata, triangular fundamental-diagram inconsistency, inconsistent explicit free-flow/storage overrides, or inadmissible timestep. It must not store live state on topology records, and it must not silently mutate the current loading kernel.

---

### Immutable Node Metadata

Every node record carries the following fields. All are immutable after the topology hash is computed.

- canonical node ID
- latitude and longitude in WGS84
- connectivity set: the set of canonical link IDs for which this node is head or tail
- immutable movement specifications for admissible incoming-to-outgoing transfers
- static movement priority weights and movement-level provenance, when declared
- OSM node ID and OSM snapshot date as provenance metadata

Topology owns admissible movement specifications because they describe what static
turning movements physically exist at a junction. A node with no explicit
movement specs is interpreted as allowing the Cartesian set of incoming-to-
outgoing movements. This default is still immutable topology interpretation.

Topology does not own runtime transfer decisions. Movement allocation, queues,
packet transfers, cumulative counts, and allocation traces remain loading state.
Signal phases, closures, and adaptive control programs remain governance state.
Lane groups and conflict-resource references may appear as immutable static
metadata, but any runtime service rule that uses them belongs to governance and
loading allocation, not to topology mutation.

---

### Topology Hash

The topology hash is computed over the canonical content of the topology record:
canonical node IDs, canonical directed link IDs, directed connectivity,
immutable movement specifications, immutable static physical metadata, source
IDs preserved as provenance, and declared source-interpretation assumptions.
OSM provenance fields, geometric polyline detail beyond node coordinates,
absolute local file paths, file read order, and NetworkX adapter state do not
affect the hash.

Two runs share the same topology if and only if their topology hashes match. Shared OSM origin, shared visual appearance, or shared approximate extent is not sufficient.

---

### T1 Canonical Topology Artifact

T1 introduces executable canonical topology artifacts. A canonical topology is an immutable record containing:

- canonical node IDs
- canonical directed link IDs
- immutable node and link records
- directed connectivity
- immutable junction movement specifications
- static physical metadata where available or explicitly interpreted
- source/provenance metadata
- deterministic topology hash

The first controlled benchmark-style topology is Sioux Falls when the separately acquired external TNTP files are present under `data/benchmarks/sioux_falls`. This is not Cork and not an OSM import. It is a narrow bridge from tiny hand-built synthetic graphs toward a recognised benchmark network.

The Sioux Falls TNTP loader treats external TNTP node IDs and directed endpoint pairs as provenance. Canonical IDs are assigned deterministically by the framework (`N###` for nodes and `L####` for directed links). The TNTP file is parsed into immutable canonical records; NetworkX is not used as canonical state.

Raw TNTP inputs are not bundled; see the
[benchmark acquisition instructions](../../data/benchmarks/sioux_falls/README.md)
for the upstream source, filenames and historical checksums.

For the separately acquired Sioux Falls TNTP network, the topology adapter declares these interpretation assumptions:

- TNTP length values are interpreted as miles.
- TNTP free-flow time values are interpreted as minutes.
- TNTP capacity values are interpreted as vehicles per hour.
- Lane count is fixed at one because the TNTP source does not provide lanes.
- Jam density and backward wave speed are not present in the source and remain absent.
- BPR alpha and beta are static-assignment reference parameters and are not canonical topology fields.

These assumptions are included in the topology hash payload. Changing static topology content or interpretation assumptions changes the hash.

T1 does not implement OSM import, Cork import, demand generation, route search, calibration, signal modelling, visualisation, experiment dashboards, or real-city realism.

---

### T2/T3 Canonical Path Realisation

T2/T3 introduces immutable route artifacts over canonical topology and a modest deterministic path-construction mechanism. A canonical route contains:

- route ID
- origin canonical node ID
- destination canonical node ID
- ordered canonical link IDs

Routes are packet intent artifacts. They are not stored on links or nodes, and they do not mutate topology. Route validation checks that the ordered links are non-empty, begin at the declared origin, end at the declared destination, and form a contiguous directed sequence.

The initial path builder uses deterministic breadth-first search over canonical outgoing link IDs and returns a shortest-link-count path. This is deliberately modest. It is intended to produce valid benchmark-topology movement routes, not realistic route choice, dynamic traffic assignment, congestion-aware routing, UE, SO, or route optimisation.

The Sioux Falls topology can now be adapted into loading-engine `Link` and
`Node` records. These records preserve static physical metadata, directed
connectivity, and immutable junction movement specifications while leaving all
dynamic packet movement, event history, storage, sending, receiving, allocation,
and queue state inside the loading engine.

This milestone supports Sioux Falls smoke runs in which packets traverse multi-link benchmark routes and complete under existing loading invariants. It does not implement calibrated demand, assignment algorithms, Cork or OSM import, visualisation, behaviour, governance, or dynamic costs.

---

### D1 Demand Boundary

D1 introduces immutable OD demand manifests and scheduled loading, but these remain outside topology records. A topology may validate that demand origins and destinations reference known canonical nodes. It does not own demand, volume, trips, live OD counts, scheduled departures, packet lifecycle, or realised movement.

Demand manifests reference `topology_id` and `topology_hash` so experiments can prove which immutable network they target. That reference does not make demand part of the topology hash.

---

### The Adapter Layer

NetworkX and OSMnx are adapter tools. They serve two legitimate purposes: topology import from OSM data, and routing computation convenience (shortest-path queries, graph traversal). They do not serve as canonical state stores.

The adapter layer is permitted to hold a NetworkX DiGraph with link and node attributes sufficient for routing queries. It is not permitted to write results of routing computation or simulation back to that graph as canonical truth. Any values written to NetworkX edge or node attributes during or after a run are derived adapter views, not physical state, and must not be read back as canonical input by any other subsystem.

---

### Forbidden Topology Fields

The following fields must never appear on a canonical link or node record. Their presence indicates legacy contamination.

- `travel_time_seconds` as a topology attribute
- `simulated_volume` in any form
- `live_occupancy_count` or any occupancy field
- `peak_simulated_volume` or any peak dynamic field
- `marginal_cost_seconds` or any cost field
- `bpr_alpha`, `bpr_beta`, or any BPR calibration parameter
- `signal_phase` as a topology attribute
- `effective_capacity` as a topology attribute
- Any field whose value changes during a simulation run

BPR parameters may appear in benchmark reference data structures under the `legacy/` namespace. They must not appear in canonical topology records even if the benchmark data was originally used to calibrate topology metadata.

---

### Topology Equality and Experiment Comparability

Two network artifacts represent the same experiment topology if and only if their topology hashes match. This is the only valid criterion for topology equality in scientific comparisons.

The following are not sufficient for topology equality: same OSM bounding box, same approximate node count, same city, same graph name, same import script version, or visual similarity of rendered maps.

The topology hash must be included in every experiment artifact. Comparisons between runs with different topology hashes must be explicitly justified and flagged as cross-topology comparisons in any output or report.

---

### Open Questions

- **Topology versioning.** If a topology is refined (re-calibrated capacity, corrected geometry), how are successive versions related? Should versioned topologies share a lineage record? → to be resolved before any topology update workflow is implemented.
- **Multi-modal topology.** If the framework is extended to model bus corridors, cycle lanes, or pedestrian routes, do these share the directed graph representation or require separate topology records? → to be resolved before multi-modal work begins.
- **Topology import provenance.** What OSM snapshot date, bounding box, filter parameters, and simplification settings must be recorded to make a topology import reproducible? → artifact_contracts.md.

---
