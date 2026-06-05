**Status:** specification.
**Scope:** defines governance actors, intervention types, the constraint and information environment they control, and how governance actions become visible to other subsystems.
**Non-scope:** does not define routing authority decision logic, loading mechanics, or behavioural update functions.

---

### Governance vs Routing

Governance and routing are distinct roles even when held by the same actor. A municipal authority may simultaneously operate as a governance actor (setting signal timings, closing links, controlling information release) and as a routing authority (issuing route recommendations to cooperative participants). These two roles are implemented as separate interfaces and must not share mutable state directly.

Governance asks: what rules and constraints are currently in force?
Routing asks: given those rules and my information, what route should this packet follow?

---

### Governance Actors

A governance actor is any entity with the authority to alter the constraint environment or the information environment. In the base model, a single municipal governance actor is assumed. Multi-actor governance (competing municipal authorities, regional versus local governance) is an [OPEN] extension.

---

### Intervention Types

**Link closure.** Marks a canonical link as infeasible from a declared visibility_time. The loading engine reads closure status in Phase 0 of each tick and excludes closed links from feasible transfer targets. A closure does not alter the topology record; the link remains in the topology with its immutable metadata. The closure is a governance state entry.

**Signal retiming.** Updates the effective capacity function for one or more canonical links by altering the declared green-time fraction or cycle parameters. The loading engine reads signal state in Phase 2. Signal state is governance state, not topology.

**Access restriction.** Restricts link access to a declared set of packet cohort classes. The loading engine evaluates access eligibility per packet at node transfer. Access restrictions are governance state entries with declared scope (cohort class set) and visibility_time.

**Pricing overlay.** Attaches a cost signal to one or more canonical links, visible to routing authorities through a declared information release channel. Pricing overlays do not alter physical capacity; they alter the cost surface that routing authorities observe. The loading engine does not read pricing overlays; they are purely informational.

**Information release policy.** Declares which observation frames are published to which routing authorities, at what delay, and with what aggregation or suppression rules. This is the mechanism through which governance creates observation access asymmetry between authority types.

**Information withholding.** A special case of information release policy in which governance delays, aggregates, or suppresses specific observation streams. This is a modelled mechanism: the governance layer does not falsify observations; it controls publication timing and access. All withholding actions are logged as governance interventions with type `INFORMATION_RELEASE_POLICY` and full parameters.

---

### Intervention Record

Every governance intervention is recorded as an append-only entry in the governance intervention log. Each entry carries: intervention_id, type, target entity (canonical link ID, node ID, sensor ID, or authority ID as appropriate), parameter values, action_time (when the governance actor issued the intervention), and visibility_time (when the intervention becomes visible to other subsystems).

The gap between action_time and visibility_time models implementation lag, political delay, or deliberate phasing. An intervention with visibility_time = action_time takes effect immediately. An intervention with visibility_time > action_time is recorded in the log but does not affect loading or observability until its visibility_time tick is reached (Phase 0).

---

### What Governance Cannot Do

Governance cannot move packets. It cannot alter packet IDs, lifecycle states, or cumulative count records. It cannot alter topology records. It cannot directly assign routes to packets; that is the routing authority's role. It cannot produce observation frames; that is the observability layer's role.

The constraint is stated in P7 of core_principles.md. It is repeated here because governance_model.md is where its operational consequences are worked out: every governance mechanism listed above operates by altering what the loading engine reads as feasibility constraints, or by controlling what information the observability layer publishes to which authorities. Neither mechanism touches packets or physical records directly.

---

### Infrastructure-Mediated Control

The research framework proposes that governance may influence commercial routing authority behaviour indirectly, by altering the physical conditions those authorities observe. Signal retiming that degrades travel time on a rat-run will cause commercial authorities to route away from it without any direct coordination. Access restrictions that favour cooperative participants will alter the cost surface commercial authorities measure.

This indirect mechanism is not a special case in the governance model; it is the natural consequence of governance controlling constraints and information while commercial authorities optimise over observed conditions. The framework models it by: (a) governance interventions altering effective capacity or travel time signals on specific links; (b) the observability layer sampling the resulting physical state; (c) commercial authority routing decisions responding to the altered observations.

No additional mechanism is needed. The separation of governance state, physical loading, observability, and routing authority decision logic makes this indirect control chain explicit.

---

### Open Questions

- **Multi-actor governance.** If multiple governance actors exist with overlapping jurisdiction, how are conflicting interventions resolved? Priority ordering, first-writer-wins, or explicit conflict resolution? → to be resolved before any multi-actor governance scenario is modelled.
- **Governance observation access.** Does the governance actor have direct read access to physical truth, or does it observe through the same observability pipeline as routing authorities? An oracle governance actor is a special case with the same concerns as an oracle routing authority. → routing_authorities.md, benchmark_policy.md.
- **Pricing and behaviour interaction.** If a pricing overlay increases the perceived cost of a route, does this affect the behaviour layer's experienced delay calculation, or only the routing authority's cost surface? → behaviour_adaptation.md.
- **Intervention reversibility.** Can a governance actor rescind or modify an active intervention? If so, is the modification a new intervention entry or an update to the existing entry? The base model should declare append-only semantics (a rescission is a new entry of type `RESCISSION` referencing the original intervention_id). → to be confirmed before any dynamic governance scenario is implemented.

---
