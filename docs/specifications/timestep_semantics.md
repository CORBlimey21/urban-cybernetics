**Status:** specification.
**Scope:** defines the simulation clock, event ordering within a timestep, tie-breaking rules, and the conditions under which a run is deterministic and replayable.
**Non-scope:** does not define LTM equations, node transfer algorithms, or routing policy.

---

### Why Timestep Semantics Matter

Two implementations using identical equations and identical inputs can produce different outputs if their event ordering differs. A packet that exits a link in the same timestep that a governance intervention closes the downstream link will behave differently depending on whether link exit is processed before or after governance updates. An observation frame sampled at the boundary of a timestep will capture different physical state depending on whether sampling occurs before or after loading updates.

These are not implementation details. They are scientific decisions. This document records them so that results are reproducible and so that any two compliant implementations produce identical outputs given identical inputs and seeds.

---

### Simulation Clock

The simulation runs on a discrete clock. Each tick advances the simulation by one timestep of fixed duration Δt, declared in the experiment configuration and immutable for the run. The current simulation time at tick k is t_k = t_0 + k·Δt, where t_0 is the declared run start time.

All events within a single tick are assigned the timestamp t_k. Events are ordered within a tick by phase (see below), not by sub-tick time. There is no sub-tick time in the base model.

---

### Phase Ordering Within a Timestep

The following phases execute in strict order within each tick. No phase may read state that belongs to a later phase in the same tick. Each phase reads the state left by the previous phase.

**Phase 0: Governance update.**
Governance state entries whose action_time ≤ t_k and visibility_time ≤ t_k become active. The loading engine reads the updated governance state from this tick onward. Governance entries whose visibility_time > t_k are not yet visible to any other subsystem.

**Phase 1: Departure instantiation.**
All demand declarations with departure_time within (t_{k-1}, t_k] become eligible for packet instantiation. Each eligible demand is instantiated only if its origin link has available storage. If origin storage is full, the demand remains pending and no packet event is appended. Each admitted packet is assigned an ID, placed in the in-transit state on its origin link, and appended to the packet event log. Route intent is assigned by the routing authority before or during this phase (see routing_authorities.md for decision timing detail).

**Phase 2: Loading update.**
The loading engine processes link dynamics for all active links: evaluates sending and receiving functions, advances packets along links, computes queue states, and records link exit events for packets that cross a boundary this tick. Node transfer is processed within this phase (see node_model_assumptions.md for node transfer ordering detail relative to link updates).

Within Phase 2, processing occurs in two sub-steps. First, link dynamics: for all active links, sending and receiving functions are evaluated, packets advance along links, and link exit events are appended for all packets that reach a downstream boundary this tick. Second, node transfer: for all nodes with packets queued or newly arrived at their incoming boundaries, transfer eligibility is evaluated against receiving capacity and governance state, packets are assigned to outgoing links according to route intent and applicable priority rules, and transfer events are appended. A packet that reaches a link's downstream boundary in the link dynamics sub-step is eligible for node transfer in the node transfer sub-step of the same tick. A packet may not cross two link boundaries in a single tick.

**Phase 3: Observation sampling.**
The observability layer samples the loading engine's physical records to produce observation frames for all sensors whose next scheduled sampling time falls within this tick. Frames are published immediately after sampling. Physical state sampled is the state at the end of Phase 2 for this tick.

**Phase 4: Routing authority decisions.**
Each routing authority consumes available observation frames (those published in Phase 3 of this or any prior tick, subject to the authority's receipt delay model) and produces route recommendations or assignments for the next departure wave. Routing decisions do not alter physical state in this tick; they update route intent records that take effect at the next departure instantiation or re-route event.

**Phase 5: Behavioural update.**
The behaviour layer processes completed packets and any other declared trigger events, updating behavioural state records. Behavioural state changes recorded here take effect from the next instantiation.

**Phase 6: Audit and conservation check.**
The conservation ledger is reconciled. Any discrepancy between total instantiated and the sum of in-flight, completed, cancelled, and unresolved is a reportable invariant violation. Derived views (per-link occupancy, experienced delay accumulators) are updated.

---

### Tie-Breaking

Within a single phase, events affecting multiple packets or multiple links are processed in a deterministic order derived from the run's seed registry. The tie-breaking rule must be declared in the experiment configuration. The base model uses canonical link ID order for link updates and packet ID order (by instantiation sequence number) for packets competing for the same resource.

Any implementation that introduces a different tie-breaking rule produces a different run, even if the equations are identical. Tie-breaking rules are part of the reproducibility bundle.

---

### Observation Sampling Relative to Physical State

Observation frames sampled in Phase 3 capture physical state as it exists after Phase 2 of the same tick. They do not capture mid-tick states or states from a future tick. An authority receiving a frame published at tick k is observing state from Phase 2 of tick k, not the state at the end of tick k's Phase 4 or Phase 5.

This is a scientific commitment: authorities always operate on past physical state, even in the minimal-delay case where the frame is produced and received within the same tick. The minimum observable delay is one full phase cycle.

---

### Determinism and Replay

A run is deterministic if: the experiment configuration is identical (including Δt, all seed values, all tie-breaking rules, all authority decision algorithms, all behavioural update schedules), the topology hash matches, and the demand manifest hash matches.

A run is replayable if: all of the above conditions hold and the full phase-ordered event log is preserved in the run artifact. Replay means re-executing the loading engine from the event log rather than from scratch; it produces identical outputs by construction.

Stochastic elements — noise in observation frames, behavioural thresholds drawn from distributions, background demand perturbations — are deterministic given the seed registry. Adding any stochastic element that is not seeded through the seed registry breaks determinism and is a reproducibility violation.

---

### Open Questions

- **Variable timestep.** The base model uses fixed Δt. Variable timestep (event-driven simulation) is a possible extension that would change phase ordering semantics substantially. → to be resolved before any event-driven variant is implemented.
- **Simultaneous governance and loading events.** If a link closure governance entry has visibility_time = t_k and a packet is scheduled to enter that link in Phase 2 of tick k, Phase 0 processes the closure first, making the link infeasible before Phase 2 runs. This is the intended behaviour and follows from the phase ordering above. It should be confirmed as correct by the first node-model invariant tests.
- **Sub-tick node transfer ordering.** Phase 2 processes link dynamics and node transfers together. The ordering of link updates relative to node transfers within Phase 2 must be specified in node_model_assumptions.md.
- **Observation delay model.** The receipt delay between frame publication (Phase 3) and authority consumption (Phase 4) may be zero ticks, one tick, or a configurable number of ticks. The base model should declare a default. → routing_authorities.md.

---
