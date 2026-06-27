**Status:** specification.
**Scope:** defines how the loading engine represents canonical physical state, what the primary physical records are, and what is and is not permitted to be stored as loading state.
**Non-scope:** does not define node transfer algorithms, timestep event ordering, routing algorithms, or observability mechanics. Does not commit to a specific LTM implementation variant.

---

### The Loading Engine as Owner of Physical Truth

The loading engine is the sole owner of canonical physical state during a run. No other subsystem writes to or supersedes the loading engine's records. Routing authorities, governance interventions, and behavioural updates all eventually influence what the loading engine does, but they do so through declared interfaces: route intent records, governance state entries, and behavioural state events. They do not write directly to loading state.

This ownership boundary is the primary architectural invariant of the framework. It is stated in P1 of core_principles.md and is repeated here because loading_state.md is the document where its consequences are worked out.

---

### Primary Physical Records

The framework's physical truth is defined abstractly as whatever canonical records the loading engine maintains. The representation of those records is an implementation decision, not an ontological one. In the base packet-LTM implementation, the canonical representation is the packet lifecycle event log: an append-only sequence of typed events, each carrying packet_id, event_type, entity_id, physical_timestamp, and sequence_number. This is the primary record from which all other physical quantities are derived or verified against.

Cumulative boundary count functions N(x, t) are maintained explicitly by the loading engine as a derived-but-materialised accounting structure. They are updated from the event log, not independently. If a cumulative count value conflicts with what the event log implies, the event log is authoritative. This distinction matters: it means the framework's physical accounting primitive is the event, not the count function, even though LTM mechanics operate on the counts. Future implementations using different loading representations (agent-based, cell-based) may replace the count functions while preserving the event log contract.

The loading engine maintains the following record types. These are the canonical physical truth of the simulation. All other representations of network state are derived from these.

**Packet lifecycle event log.** An append-only log of all packet lifecycle events: instantiation, link entry, link exit, node transfer, queue entry, queue exit, re-route, completion, cancellation. Each event carries: packet ID, event type, canonical link or node ID, physical timestamp, and a sequence number within the run. This is the atomic unit of physical truth.

**Link storage state.** For each canonical link, the set of packet IDs currently in storage on that link, ordered by entry time. This is a derived materialisation of the packet lifecycle event log, maintained by the loading engine for computational efficiency. It is not an independent source of truth; if it diverges from the event log, the event log wins.

**Queue state.** For each canonical link boundary, the ordered list of packet IDs waiting to cross that boundary, ordered by arrival time subject to applicable priority rules. Queue state is a derived materialisation maintained for computational efficiency and is subordinate to the packet event log.

**Node transfer state.** For each node, the record of in-progress and recently completed transfers: which packets were received from which incoming links, which were assigned to which outgoing links, and which remain queued. Node transfer state is append-only during a run.

**[BASE MODEL] Cumulative boundary count functions.** In the packet-LTM implementation, the loading engine additionally maintains cumulative count functions N(x, t) at each link boundary: the total number of packets that have crossed boundary x up to and including time t. These are the materialised accounting structure used by LTM-derived travel time and flow calculations. They are derived from the packet lifecycle event log but are maintained explicitly for efficiency and for LTM mechanics.

M2 defines the read-only parity convention for these count functions. A cumulative query at tick `t` is inclusive: it counts every matching `LINK_ENTRY` or `LINK_EXIT` event whose `physical_tick <= t`. Within one tick, `sequence_number` is the canonical total order. A same-tick transfer is interpreted according to the event log order emitted by the loading engine: upstream `LINK_EXIT` precedes downstream `LINK_ENTRY`; completion emits `LINK_EXIT` before `COMPLETED`. Counts at tick `t` include all same-tick boundary events, while packet boundary ordinals preserve their sequence order.

M2 count projections are not physical state. Aggregate cumulative counts, route-disaggregated counts, packet boundary ordinals, prefix replay projections, and consistency reports are deterministic projections of the event log plus immutable packet route intent. If packet route metadata is not available, route-disaggregated counts are explicitly unsupported rather than inferred. If a count projection conflicts with the event log, the event log remains canonical and the projection is invalid evidence.

M3 adds a profile-gated parity sending interpretation for `parity_ltm_v1`. The parity sending trace derives link demand from lagged cumulative entries and cumulative exits, then selects the FIFO packet prefix using M2 boundary ordinals. Capacity is converted to an integer sending budget through a bounded carry structure so long-horizon integer discharge can preserve the declared rate. The parity profile may declare an explicit per-link parity sending rate; otherwise it uses the link's declared sending capacity. It does not use M1 physical capacity as a movement rule. This changes only sending under the parity profile. Legacy loading keeps the existing declared integer sending capacity and membership-based sending view.

M4 adds a profile-gated parity receiving interpretation for `parity_ltm_v1`.
The parity supply view computes upstream receiving availability from static
packet storage, cumulative downstream exits lagged by the link's backward-wave
travel time, and cumulative upstream entries through the query tick. A
downstream exit does not create upstream receiving supply until the
backward-wave lag has elapsed. The resulting vacancy is bounded by a receiving
capacity budget with the same bounded integer carry convention used by parity
sending. Governance closure and physical shortage are reported as distinct
receiving causes.

M4 changes receiving only under the parity profile. Legacy loading keeps the
existing immediate-storage receiving view. M4 does not implement M5 spillback
validation or M6 node-model changes; any upstream queueing caused by zero
parity receiving slots follows from the existing queue and transfer machinery.

M5 adds read-only spillback validation artifacts for the parity profile. These
artifacts fold canonical queue events into cumulative queue curves and compare
the final event-derived queue length with the loading engine's read-only queue
view. They may also record downstream parity receiving causes. They do not
create another physical state store, and they do not change packet movement.
The current M5 claim covers simple one-to-one boundary spillback, downstream
receiving bottlenecks, backward-wave vacancy delays, three-link propagation,
and declared governance blockage. Loop/gridlock behavior that depends on
node-model semantics remains outside scope until later milestones.

M6 adds minimal parity node semantics for `parity_ltm_v1`. Immutable node
records may label one-to-one, strict route-encoded diverge, and declared
priority-merge nodes. Legacy loading continues to use the existing global FIFO
merge policy by default. In parity loading, one-to-one and diverge allocation
preserve strict upstream FIFO, while priority merges use declared incoming-link
weights with bounded deficit accounting for indivisible packets. The loading
engine still owns all transfer decisions and lifecycle events; node labels and
priorities are static metadata, not physical state. Multi-input/multi-output
urban nodes are rejected for parity evidence until a later node model exists.

The distinction between the packet event log as primary record and cumulative counts as derived-but-maintained is deliberate. It preserves the option to use a different loading representation in future variants while keeping the base model's physical accounting explicit.

---

### What Loading State Is Not

Loading state is not topology. Link length, declared static capacity metadata, and free-flow speed are topology records. The loading engine reads topology but does not write to it.

Loading state is not observation state. The loading engine does not publish observation frames. It maintains physical records; the observability layer samples those records to produce frames.

Loading state is not routing state. The loading engine does not decide routes. It reads route intent from packet records and executes physically feasible movement according to it, subject to capacity and queue constraints.

Loading state is not governance state. Signal phase, link closure status, and pricing overlays are governance state entries. The loading engine reads these when evaluating link feasibility and effective capacity, but it does not own them.

---

### Effective Capacity

Effective capacity is not a topology field. It is a function computed by the loading engine at each timestep for each link, combining:

- declared static capacity metadata from the topology record
- any active governance state entries affecting that link (closures, signal phase, access restrictions)

The result is used internally by the loading engine for queue mechanics and receiving flow calculations. It is not stored as a named field on any canonical record; it is recomputed as needed from its inputs.

---

### L2 Materialised Loading Views

L2 adds engine-owned materialised views for frequently queried current loading state. The performance motivation came from the Sioux Falls demand smoke runner: topology loading, OD manifest loading, route resolution, and scheduled departure expansion were fast, while physical loading execution scaled poorly because current storage, sending, receiving, queue, and membership views repeatedly scanned the full event log.

The event log remains canonical. Materialised views are acceleration structures updated from lifecycle events as those events are appended. They are not independent scientific truth, and they are checked by recomputing selected views from event history in debug/test validation.

The loading engine may maintain the following derived current views for computational efficiency:

- current link storage count by link ID;
- current packet membership by link ID, in link-entry order;
- current packet link and current link-entry metadata by packet ID;
- completed packet IDs;
- queue membership and queue-entry metadata by boundary;
- queued downstream link by packet ID;
- same-tick receiving acceptance counts;
- pending demand bookkeeping for pre-packet origin blocking.

These views belong only inside the loading engine. They must not be stored on `Link`, `Node`, topology records, route artifacts, demand artifacts, observation frames, or routing authorities. Routing authorities do not read these caches. Observability may continue to sample physical truth through existing engine-facing interfaces, but observation artifacts remain immutable sampled outputs.

Historical storage and cumulative count queries remain event-derived. Current hot-path loading decisions may use materialised views, but if a materialised view conflicts with the primary event log, the event log is authoritative.

L3 tightens the queue hot path without changing queue semantics. The loading
engine maintains FIFO queue deques by boundary and by upstream link, plus queued
downstream-link metadata by packet ID. Normal stepping reads those live
engine-owned structures rather than reconstructing queue state from the event
log. Debug and test consistency checks still reconstruct queue state from
QUEUE_ENTRY and QUEUE_EXIT events and compare it to the materialised views.

Strict FIFO remains strict: if an upstream queue head is blocked, packets behind
it cannot bypass it. When capacity permits, stepping considers only the FIFO
prefix that could transfer this tick, bounded by upstream sending capacity and
downstream receiving availability. It does not scan blocked queue tails.

L4 hardens memory use without changing the physical ontology. Immutable loading
records, including lifecycle events and packet records, use compact slotted
dataclass layouts where safe. This reduces Python object overhead while
preserving equality, hashing, append order, iteration, indexing, and full
canonical history retention. The default event retention mode remains full
in-memory history; inspection and provenance continue to consume the same
canonical artifacts and IDs.

---

### What Must Not Be Stored as Loading State

The following must not appear as named fields in canonical loading state records. Their presence indicates contamination.

- `travel_time_seconds` as a mutable loading attribute (travel time is derived)
- `live_occupancy_count` as a canonical flow proxy
- `simulated_volume` without a declared aggregation window and boundary direction
- `marginal_cost_seconds` in any form
- `peak_live_occupancy_count` or any peak dynamic field computed outside a declared window
- Any BPR-derived field

---

### Sending and Receiving Functions

[BASE MODEL] In the packet-LTM implementation, link dynamics are governed by sending and receiving flow functions derived from cumulative boundary counts and link capacity. The sending function determines the maximum flow that can exit a link's downstream boundary. The receiving function determines the maximum flow that can enter a link's upstream boundary. These functions are the mechanism by which queue spillback propagates upstream.

The precise formulations belong in a separate packet_ltm_mechanics document if one is created. What belongs here is the ownership claim: sending and receiving functions are computed by the loading engine from its own cumulative count records and from topology metadata. No other subsystem provides inputs to these functions except through governance state (effective capacity modifiers) and packet route intent (which boundary packets are headed toward).

---

### Traffic Kinematics Foundation

[BASE MODEL] The loading kernel remains a packetised, event-owned loading model, but link records may now carry immutable physical metadata with explicit units:

- length in metres (`length_m`)
- lane count (`lane_count`)
- free-flow speed in metres per second (`free_flow_speed_mps`)
- jam density in vehicles per kilometre per lane (`jam_density_veh_per_km_per_lane`)
- backward wave speed in metres per second (`backward_wave_speed_mps`)
- capacity in vehicles per hour per lane (`capacity_veh_per_hour_per_lane`)

These fields are topology metadata, not dynamic simulation state. The loading engine reads them when constructing static loading parameters, but it does not write physical state back to the link record.

Storage capacity may be declared directly in packet units or derived from physical metadata as:

`storage_capacity_packets = floor(length_km * lane_count * jam_density_veh_per_km_per_lane)`

Because the base model uses unit-weight packets, the derived storage value is interpreted as a packet count. This is a deterministic static calculation performed when the immutable link record is built. It does not depend on live occupancy, density, speed, or queue state. Existing synthetic links without physical metadata retain the legacy large storage capacity unless an explicit packet storage capacity is declared.

Free-flow traversal time may be declared directly in ticks or derived from:

`free_flow_ticks = ceil((length_m / free_flow_speed_mps) / tick_duration_seconds)`

This derived value is a static physical baseline. Congestion effects still emerge only through sending capacity, receiving capacity, storage constraints, queues, and spillback. The derived free-flow value is not a live travel time estimate.

M1 adds explicit static parity-eligibility reports for this metadata. These reports resolve:

- free-flow travel time and lag in ticks;
- backward-wave travel time and lag in ticks;
- jam-storage capacity in unit packets;
- lane-aware physical capacity in vehicles per tick;
- triangular fundamental-diagram capacity consistency;
- timestep admissibility relative to free-flow and backward-wave travel times.

These reports do not move packets and do not change the legacy loading profile. Existing declared sending and receiving capacities remain the values used by current movement logic. A parity profile or validation harness may reject a link whose physical metadata is incomplete or internally inconsistent, but the `Link` constructor continues to accept legacy-compatible synthetic links.

Origin departure loading now respects origin-link storage. If the first link in a demand declaration has no available packet storage at the attempted departure tick, the demand remains pending and no packet is instantiated. Pending demand is pre-instantiation demand state, not packet physical state and not part of the conservation ledger until the packet actually exists.

This improves:

- origin-loading realism
- physically meaningful immutable link metadata
- storage capacity interpretation
- free-flow travel-time baseline derivation

This does not implement:

- full LTM fidelity
- Newell cumulative-curve consistency
- vacancy propagation
- shockwave propagation
- CTM equivalence
- city-scale traffic realism
- parity-profile movement semantics

---

### Benchmark Topology Loading

T2/T3 allows a canonical benchmark topology, initially Sioux Falls, to provide static loading inputs. Canonical topology links may be converted to immutable loading `Link` records, and canonical topology nodes may be converted to immutable loading `Node` connectivity records. These are static inputs only.

Routes over the canonical topology are supplied to packets as ordered link IDs in `route_intent`. The loading engine then owns the realised movement: packet lifecycle, link-entry and link-exit events, queues, storage, sending, receiving, and completion. Route artifacts do not become topology state, and topology records do not acquire live travel time, current storage, live volume, or queue fields.

The benchmark loading smoke capability proves that packets can traverse a recognised non-trivial topology under the existing packetised loading invariants. It is not traffic assignment, calibrated demand, dynamic route optimisation, or congestion-aware path search.

---

### Open Questions

- **FIFO within a link.** FIFO is assumed for packets of the same class on a homogeneous link. Passing, overtaking, and heterogeneous class priority within a link are not defined in the base model and must be declared as extensions. → to be resolved in packet_ltm_mechanics or a future extension spec.
- **Timestep duration and CFL analogue.** Packet-LTM does not have a CFL stability condition in the same sense as CTM, but there may be stability considerations relating timestep duration to link free-flow travel time. → timestep_semantics.md.
- **Event log storage.** For large runs, the full packet event log may be expensive to retain in memory. What is the minimum event log that must be preserved to satisfy conservation and reproducibility requirements? → artifact_contracts.md.
- **Experienced delay definition.** See packet_semantics.md open question on free-flow reference path.

---
