**Status:** specification.
**Scope:** defines packet identity, lifecycle, instantiation, conservation, and the rules governing split, merge, cancel, reroute, and completion. Defines the relationship between demand declarations and packets.
**Non-scope:** does not define LTM loading mechanics, node transfer algorithms, or behavioural update functions.

---

### Demand Declaration vs Packet

A demand declaration is a committed input record. It describes a trip that is intended to occur: origin, destination, departure time, cohort class. It exists before the simulation begins, in the demand manifest. It has no lifecycle, no physical presence, and no conservation obligation. It does not move.

A packet is instantiated from a demand declaration at the declared departure time if the origin link can physically accept the departure. If origin storage is full, the demand declaration remains pending and the packet does not yet exist. From instantiation onward, the packet is a conserved entity with a stable identity, a lifecycle, and a conservation accounting entry. The packet is the unit of conservation. The demand declaration is the unit of input.

One demand declaration produces exactly one packet once it is admitted to the loading kernel. There is no mechanism by which a single demand declaration produces more than one packet in the base model. A pending demand that has not yet been admitted is not a zero-packet trip; it is a pre-instantiation demand awaiting origin storage.

D1 adds a first-class OD demand layer before this loading-kernel admission boundary. `ODDemandDeclaration` records may contain `quantity_packets`; scheduled loading expands those quantities into one-unit loading admission requests. Those admission requests still do not become packets until `LoadingEngine.instantiate` accepts them onto the origin link.

---

### Packet Identity

A packet's canonical ID is assigned by the loading engine at instantiation and is immutable for the lifetime of the run. The ID does not change on reroute, on queue entry, on node transfer, or on any other lifecycle event. The demand manifest reference and demand event index are stored alongside the packet ID as provenance, but they are not the packet ID.

Two packets with different IDs are distinct regardless of whether they share origin, destination, departure time, cohort class, or route.

---

### Packet Granularity

What a packet represents is a modelling choice declared in the experiment configuration. The options are:

**Individual.** One packet represents one traveller or one vehicle. Conservation counts are in packets, which correspond directly to persons or vehicles as declared.

**Cohort.** One packet represents a behaviourally homogeneous group. Conservation counts are in packets; the cohort size is metadata on the packet record, not a multiplier applied to conservation accounting unless the experiment explicitly declares vehicle-equivalent weighting.

**[OPEN] Weighted packets.** If a packet carries a weight greater than one for computational efficiency, FIFO ordering, queue position semantics, and boundary count aggregation all require explicit re-specification. This is not resolved in the base model and must be declared and justified before use.

The selected granularity must be declared in the experiment configuration and must be consistent throughout a single conservation ledger. Mixed granularity within one run is not permitted unless explicitly modelled with separate conservation ledgers.

M7 makes the current parity-evidence boundary explicit: the base loading model
admits unit packets only. `packet_unit_weight` is fixed at `1` on demand and
packet records, and non-unit values are rejected rather than interpreted as
vehicle-equivalent weights. This is not weighted-packet support; it is an
explicit guard against accidentally treating weighted or mixed-granularity runs
as academic LTM parity evidence.

For M7 parity evidence, a commodity is the immutable route-intent class:
`route:<link_1>->...-><link_n>`. All packets with the same ordered route-intent
link sequence belong to the same current UC commodity. There is no separate OD,
vehicle-class, cohort-size, or behavioural-class commodity dimension in the
current loading kernel. Those dimensions may exist upstream as demand metadata,
but they are not part of the current packet-LTM commodity ledger.

---

### Lifecycle States

A packet occupies exactly one lifecycle state at any moment. Transitions are recorded as append-only events; no state is overwritten.

**Pending.** The demand declaration has been committed to the manifest and may be waiting for its declared departure tick or for origin-link storage. The packet does not yet exist. (This is a pre-instantiation state of the demand declaration, not a packet state.)

**In transit.** The packet has been instantiated and is actively traversing its current link.

**Queued.** The packet is in storage on a link, waiting for downstream receiving capacity to allow transfer to the next link or node.

**Transferring.** The packet is at a node boundary, in the process of being assigned to an outgoing link. This is a transient state; its duration and whether it is explicitly modelled depend on timestep semantics.

**Completed.** The packet has crossed the final boundary on its route intent. The completion event records timestamp, total experienced delay, and final cohort state.

**Cancelled.** The packet has been explicitly removed from the simulation with a reason code. The cancellation event records the reason, the timestamp, and the packet's last known state.

Transitions are monotonic with one exception: a packet may cycle between in-transit and queued as it progresses through successive links. It may not return to an earlier lifecycle state in any other sense: a completed or cancelled packet cannot become in-transit again.

---

### Conservation Accounting

Every packet instantiated from a demand declaration appears in the conservation ledger for that run. The ledger has four registers at any point during a run:

- **In flight:** in-transit plus queued plus transferring packets.
- **Completed:** packets that have crossed their final boundary.
- **Cancelled:** packets explicitly removed with a reason code.
- **Unresolved:** packets present at run termination that are neither completed nor cancelled. These are flagged, not silently discarded.

At all times: total instantiated = in flight + completed + cancelled + unresolved.

At clean run termination, in flight should be zero and unresolved should be zero. Non-zero unresolved at termination is a reportable condition requiring explanation in the run record.

Conservation is checkable locally at three granularities:

**Link boundary.** Cumulative exits never exceed cumulative entries. After all packets on a link have cleared, exits equal entries.

**Node transfer.** Packets transferred to outgoing links plus packets held in queue equals packets received from all incoming links since the last accounting checkpoint.

**Whole network.** The ledger equation holds at all times.

---

### Route Intent and Realised Path

**Route intent** is the ordered sequence of canonical link IDs assigned to a packet at instantiation by the routing authority. It is the packet's plan.

**Realised path** is the sequence of canonical link IDs the packet actually traverses, recorded as link-entry events by the loading engine.

These may differ. If a governance intervention closes a link on the packet's intended route after instantiation, or if a re-route event updates the intent mid-journey, the realised path diverges from the original intent. The loading engine records both: the current route intent and the accumulated realised path events. Divergence between intent and realised path is a recordable event, not an error.

[OPEN] What happens when a packet reaches a node and its intended outgoing link is infeasible at that moment — closed, at receiving capacity, or removed by a governance intervention? The options are: the packet queues on the incoming link until the outgoing link becomes feasible; the packet triggers a re-route event; or the packet is cancelled with reason code `NO_VALID_PATH`. The resolution rule must be declared in the experiment configuration and specified in node_model_assumptions.md.

---

### Split and Merge

**Split:** not permitted in the base model. A packet entering a diverge node follows exactly one outgoing link according to its route intent or a re-route decision. It does not divide.

**Merge:** not permitted in the base model. Two distinct packets always remain two distinct packets. They may queue behind each other, but they do not combine into one.

Both operations are reserved as explicit extensions requiring their own conservation semantics and are marked [EXTENSION] if introduced.

---

### Cancel

The implemented base-kernel cancellation operation applies only to an
instantiated active packet in `IN_TRANSIT` or `QUEUED`. Pending demand is not a
packet and cannot be cancelled through this operation; a `COMPLETED` or already
`CANCELLED` packet cannot be cancelled again.

`LoadingEngine.cancel_packet(packet_id)` removes the packet from every live
spatial index before making it terminal. An in-transit cancellation emits
`LINK_EXIT` followed by `CANCELLED`. A queued cancellation emits `QUEUE_EXIT`,
`LINK_EXIT`, then `CANCELLED`. The `CANCELLED` event's `entity_id` is the last
link ID. The same packet ID is retained, queue membership is cleared, and the
packet remains in the conservation ledger's cancelled register.

The current canonical `Event` schema has no cancellation-reason field. Reason
codes such as `NO_VALID_PATH`, `DEMAND_WITHDRAWN`, `RUN_TERMINATED`, or
`EXPERIMENT_DEFINED` therefore remain a deferred provenance extension rather
than part of the frozen physical event contract.

---

### Reroute

A packet may have its route intent updated mid-journey. A re-route event records: packet ID, re-route timestamp, triggering subsystem (routing authority, governance, behaviour), prior route intent snapshot, new route intent, and the canonical link ID at which the reroute took effect.

The loading engine appends the re-route event. Prior route intent is archived, not deleted. The packet ID does not change.

[OPEN] Priority ordering when multiple subsystems propose a re-route simultaneously. → routing_authorities.md, governance_model.md.

M7 does not implement rerouting. Route-disaggregated counts, packet boundary
ordinals, and route travel-time curves are valid parity evidence only while the
realised link-entry sequence is the prefix of immutable route intent. Any
future reroute event semantics must define how route keys, commodity counts,
and travel-time curves split before those runs can be labelled M7 evidence.

---

### Packet Event Log

Every packet has an append-only event log maintained by the loading engine. The log records in order: instantiation, each link entry, each node transfer, each queue entry and exit, each re-route, completion or cancellation. This log is the primary audit trail for packet conservation and the primary source for per-packet experienced delay calculation.

---

### Open Questions

- **Weighted packets.** If cohort packets carry a weight > 1, are boundary counts in weighted vehicle-equivalents or in packet units? How does FIFO apply to packets of different weights? → to be resolved before cohort-weighted runs are implemented.
- **Route intent binding.** Is a packet permitted to traverse a link not on its current route intent under any circumstance, or is divergence always a re-route event? → node_model_assumptions.md.
- **Experienced delay definition.** Is experienced delay defined as total elapsed time minus free-flow time for the realised path, or minus free-flow time for the intended route? These differ if the realised path is longer than intended. → loading_state.md.
- **Packet memory across runs.** In multi-run experiments modelling repeated daily travel, does a packet carry its behavioural state from a prior run? → behaviour_adaptation.md.

---
