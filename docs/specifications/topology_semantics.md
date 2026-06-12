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

---

### Immutable Node Metadata

Every node record carries the following fields. All are immutable after the topology hash is computed.

- canonical node ID
- latitude and longitude in WGS84
- connectivity set: the set of canonical link IDs for which this node is head or tail
- OSM node ID and OSM snapshot date as provenance metadata

Node transfer rules — merge priority, diverge logic, signal phases — are not topology. They are specified in node_model_assumptions.md and instantiated as governance or loading state during a run.

---

### Topology Hash

The topology hash is computed over the canonical content of the topology record: the ordered set of link tuples (canonical_link_id, head_node, tail_node, length, declared_static_capacity, free_flow_speed, lane_count) and the ordered set of node tuples (canonical_node_id, latitude, longitude). OSM provenance fields, geometric polyline detail beyond node coordinates, and NetworkX adapter state do not affect the hash.

Two runs share the same topology if and only if their topology hashes match. Shared OSM origin, shared visual appearance, or shared approximate extent is not sufficient.

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
