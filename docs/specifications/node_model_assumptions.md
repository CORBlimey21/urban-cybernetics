# Node Model Assumptions

**Status:** specification.
**Scope:** defines UC's general junction architecture, movement allocation
semantics, Stage 2 supported cases, and explicit rejection boundaries.
**Non-scope:** does not implement adaptive signal control, signal timing
optimisation, pedestrian interaction, gap acceptance, roundabout-specific
logic, weighted packets, rerouting, real-city import semantics, cybernetics
experiments, or empirical calibration.

---

## Primitive

The primitive is `MovementSpec`, not a specialised node class.

A node is an immutable junction identity plus connectivity. It says which
canonical links meet at a junction. It is not a merge algorithm, diverge
algorithm, signal controller, cross-node controller, or roundabout model.

A movement is an admissible directed transfer from one incoming link to one
outgoing link at a junction. Scientific node behaviour is expressed by
declarative movement specifications plus constraints over those movements.

Specialised architectural concepts such as `MergeNode`, `DivergeNode`,
`SignalNode`, `CrossNode`, and `RoundaboutNode` are intentionally not part of
the long-term ontology. Those cases are represented as different movement sets
and constraint sets.

---

## Static Model

Topology owns immutable junction specifications:

- `JunctionSpec.node_id`
- incoming canonical link IDs
- outgoing canonical link IDs
- `MovementSpec` records
- static lane-group metadata, when available
- movement-to-lane-group mappings, when available
- static priority weights
- static conflict-resource references
- governance references
- provenance metadata

If a junction does not declare explicit movement specs, UC constructs the
Cartesian set of incoming-to-outgoing movements. This default is a static
topology interpretation, not runtime discovery.

Movement specs are part of topology identity. A change to movement admissibility
or static priority metadata changes the topology hash or the loading
movement-spec fingerprint used for provenance.

Legacy node labels may remain only as compatibility metadata for old tests,
fixtures, or regression comparisons. They are not architecture.

---

## Runtime Model

Loading owns runtime execution. The runtime flow is:

```text
TransferRequest
  -> JunctionAllocationInput
  -> MovementAllocator
  -> JunctionAllocationDecision
  -> Loading emits canonical lifecycle events
```

`TransferRequest` is packet-level demand to traverse one movement at the current
tick. It carries packet identity, upstream link, downstream link, movement ID,
route position, FIFO eligibility metadata, and whether it was already queued.

`JunctionAllocationInput` is the complete per-junction allocation problem for a
tick: immutable junction spec, packet movement demand, upstream sending
eligibility, downstream receiving slots, FIFO state as exposed by loading, and
governance constraints currently supported by loading.

`MovementAllocator` decides which movement requests are approved. It does not
move packets, update queues, mutate topology, or emit canonical events.

`JunctionAllocationDecision` records approved transfers, rejected transfers with
reason codes, movement flow summaries, allocator state, and deterministic
allocation trace.

Loading alone executes approved transfers and emits `LINK_EXIT`, `LINK_ENTRY`,
`QUEUE_ENTRY`, `QUEUE_EXIT`, completion, and related canonical events.

---

## Ownership Boundaries

Topology owns immutable geometry, connectivity, movement specifications, static
metadata, topology provenance, and topology hashes.

Loading owns packet lifecycle, queues, storage, sending, receiving, allocation,
packet transfer execution, cumulative counts, materialised hot-path views,
allocation traces, allocator identity, and movement-spec replay fingerprints.

Routing owns route intent only. It chooses or records ordered link IDs. It does
not decide whether a physical movement is feasible at a tick.

Governance owns active constraints, closures, signal programs, and future
adaptive control state. Loading may read governance state when constructing an
allocation problem, but governance does not mutate loading records.

Observability remains read-only. It samples or derives views from canonical
records and does not participate in allocation.

Validation remains evidence only. It verifies conservation, FIFO, counts,
demand/supply compliance, spillback compatibility, commodity consistency,
deterministic replay, provenance, and parity claims; it does not own model
state.

Provenance records topology hashes, demand/manifest hashes, static movement-spec
identity, allocator identity, code/config identity, assumptions, and replay
metadata.

---

## Stage 1 Supported Semantics

The Stage 1 production allocator supports:

- one-to-one junctions;
- strict route-encoded diverges;
- declared-priority merges through movement priority weights;
- simple arbitrary multi-input/multi-output junctions whose behaviour can be
  represented by independent admissible movements, FIFO packet prefixes,
  upstream sending limits, downstream receiving slots, and deterministic
  priority/tie-break rules.

The allocator may solve at movement/count level first, then select deterministic
FIFO packet prefixes. Packet identity remains preserved in the emitted event
log.

Priority is static movement metadata in Stage 1. Equal weights mean equal
long-horizon opportunity when competing movements are continuously active. When
one movement has no eligible demand, unused capacity can be reassigned to other
eligible movements subject to FIFO and receiving constraints.

Strict FIFO is upstream-link FIFO. A packet behind a queued or blocked head
packet on the same upstream link cannot bypass the head by choosing another
movement.

Ordering is deterministic. Input dictionary order, source file read order, and
adapter traversal order must not affect allocation decisions.

---

## Stage 2 Supported Semantics

Stage 2 keeps `MovementSpec` and `JunctionSpec` as the only junction
abstractions and adds executable constraint layers over them:

- conflict resources: movements that declare the same conflict resource consume
  shared per-tick resource capacity;
- lane groups: movements consume declared lane-group capacity through direct
  movement lane groups or movement-to-lane-group mappings;
- partial FIFO: junctions may declare `partial_by_movement` FIFO, allowing a
  later packet to use a disjoint open movement when a packet ahead is blocked by
  a non-coupled movement constraint;
- signal gates: a movement with a signal group is eligible only when loading is
  given that signal group as open for the tick;
- governance gates: loading may close individual movements through runtime
  governance state without mutating topology;
- rejection reasons: allocation traces distinguish downstream physical supply,
  conflict-resource capacity, lane-group capacity, signal closure, governance
  closure, undeclared movement, FIFO blockage, and non-selection.

Conflict-resource and lane-group capacities are integer packet capacities for
the allocation tick. They may be declared statically on the junction spec and
overridden at runtime by loading/governance inputs. A declared resource without
an explicit capacity defaults to one packet per allocation tick.

Signal support is deliberately a gate, not a controller. Stage 2 consumes the
current set of open signal groups supplied by loading. It does not compute phase
plans, cycle offsets, adaptive timings, saturation flow, or lost time.

Governance support is likewise a gate. Governance may close a movement or set a
runtime resource capacity. Loading reads that state when assembling allocation
inputs. Governance does not move packets, mutate topology, or write canonical
events.

Partial FIFO is only allowed where the junction declares it. Two movements are
coupled, and therefore cannot bypass each other, if they are the same movement,
share the same downstream link, share a conflict resource, or share a lane
group. Otherwise, a packet may bypass a blocked packet ahead on the same
upstream link when its own movement is open and resource-feasible.

---

## Explicit Rejection Boundaries

If a junction requires any of the following semantics for scientific
correctness, Stage 2 must reject it explicitly:

- lane-changing or lane-use assignment;
- adaptive signal or metering control;
- pedestrian, bicycle, transit-priority, or multimodal interaction;
- gap acceptance;
- roundabout circulation/yield logic;
- weighted packets or mixed-granularity flow units;
- rerouting within allocation;
- empirical calibration of movement capacities.

Unsupported semantics must not be silently simplified into independent movement
allocation. A rejection is better scientific evidence than a fake pass.

---

## Relationship to Tampere-Style Node Requirements

The Stage 1 movement allocator is designed to align with the generic node-model
requirements that matter for UC's current parity kernel:

- conservation: approved transfers consume upstream demand and downstream
  receiving slots exactly once;
- demand and supply compliance: allocation is bounded by sending eligibility
  and receiving availability;
- invariance: results do not depend on incidental ordering of records;
- FIFO consistency: upstream packet order is preserved under the declared FIFO
  model;
- priority handling: competing movements use declared static priorities rather
  than hidden node-class behaviour;
- determinism and reproducibility: decisions are traceable and replayable.

Stage 1 does not claim the full Tampere generic-node space. In particular,
conflict constraints, lane groups, signal phases, and richer supply interaction
belong to deferred constraint layers over the same movement abstraction.

Stage 2 implements the first of those deferred constraint layers while
preserving the same requirements: conservation, demand/supply compliance,
invariance, FIFO consistency under declared FIFO policy, priority handling,
determinism, and replayable allocation traces.

---

## Relationship to de Souza-Style General Cross Nodes

UC's architecture intentionally converges toward a general movement-allocation
solver compatible with cross-node ideas: arbitrary inbound/outbound movement
demand, movement-level admissibility, constraints, and deterministic allocation.

The current implementation is a second production slice of that architecture.
It supports independent MIMO movements plus conflict resources, lane groups,
runtime signal/governance gates, and declared partial FIFO. It still rejects
adaptive control, lane-changing, gap acceptance, roundabout-specific behaviour,
weighted packets, rerouting, and empirical calibration.

This keeps the ontology stable while allowing future de Souza-style behaviour
to be added as solver inputs rather than new node subclasses.

---

## Migration Rule

The parity kernel must run through movement allocation. Existing one-to-one,
diverge, and priority-merge behaviour is preserved as movement-allocation
semantics, not as specialised node classes.

Tests should assert intended scientific behaviour: conservation, event-log
canonicality, FIFO, demand/supply compliance, deterministic replay, and
provenance. Tests should not assert obsolete internal node-family structure.

---
