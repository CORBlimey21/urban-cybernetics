**Status:** specification.
**Scope:** defines what behavioural state is, who owns it, what it may influence, and the base model for compliance and churn. Records open questions about update schedules, memory persistence, and calibration.
**Non-scope:** does not define loading mechanics, routing algorithms, governance interventions, or observation frame structure.

---

### Core Principle

Behaviour affects decisions, not conservation. This is P8 of core_principles.md. A packet that churns from one authority to another still completes its trip or is explicitly cancelled. Behavioural state shapes which routing decisions a packet follows and which authority's recommendations it acts on. It does not create, destroy, duplicate, or reposition packets.

---

### What Behavioural State Is

Behavioural state is a set of per-packet or per-cohort records maintained by the behaviour layer. It captures the accumulated experience and disposition of a demand unit with respect to routing authorities and route choices. Behavioural state is separate from physical state (owned by the loading engine) and from observation frames (owned by the observability layer). It is not canonical physical truth and does not affect conservation accounting.

Behavioural state fields in the base model:

- compliance_state: which authority's routing this packet is currently following (cooperative, commercial, background, or unassigned)
- experienced_excess_delay_history: a sequence of excess delay values from completed trips, ordered by trip completion time
- excess_delay_accumulator: running total or windowed average of excess delay, used as input to the churn function
- trust_score_per_authority: a per-authority scalar representing accumulated trust, updated at declared trigger events
- route_preference_distribution: a distribution over known route options, updated by experience

All fields are mutable-with-audit. The behaviour layer appends update events referencing the packet ID; it does not overwrite prior records.

---

### Ownership and Writers

Behavioural state is owned by the behaviour layer. The loading engine does not write to behavioural state; it produces the packet lifecycle events (link exits, completion events) that the behaviour layer reads as inputs. The routing authority does not write to behavioural state; it reads compliance_state to determine which packets are in its cohort.

The behaviour layer writes to behavioural state through audited events appended to the behaviour event log. Each event carries: packet_id, event_type, timestamp, updated field, prior value, new value, and trigger reference (the packet lifecycle event or information receipt event that caused the update).

---

### The Churn Mechanism

Churn is the process by which a packet switches its compliance_state from one authority to another. In the base model, churn is driven by accumulated excess delay.

[BASE MODEL] A logistic churn function governs the probability that a packet switches away from its current authority at a declared evaluation point:

P(Churn) = 1 / (1 + exp(−λ (ΔT_p − θ_p)))

where ΔT_p is the packet's current excess delay signal, θ_p is the packet's tolerance threshold, and λ governs sensitivity.

This is a base model specification. It is recorded here as the starting point. It is not an invariant. The logistic form and its parameters are empirical choices subject to calibration and revision. If a different churn model is adopted, this document is updated and the change is recorded in the run configuration for all subsequent experiments.

The parameters θ_p and λ are declared per cohort class in the experiment configuration. They are part of the reproducibility bundle.

---

### Churn Evaluation Triggers

[BASE MODEL] Churn is evaluated at trip completion: after a packet's final link exit event, before the next departure instantiation for the same demand unit (in multi-trip models). This means churn affects the next trip, not the current one. A packet mid-trip does not change compliance_state mid-journey in the base model.

[OPEN] Additional evaluation triggers: at re-route events, at information receipt events, at fixed tick intervals. These are extensions that require explicit declaration of evaluation timing and of how partial-trip excess delay is computed. → to be resolved before any intra-trip adaptation scenario is modelled.

---

### Behavioural Memory and Multi-Trip Models

[OPEN] In single-run, single-trip models, behavioural state is initialised from the experiment configuration and updated within the run. In multi-trip or multi-run models, whether behavioural state persists across runs is a scientific choice with significant consequences for calibration and reproducibility. If state persists, the initial state of each run must be declared as an artifact from the prior run and included in the reproducibility bundle. If state resets, the reset policy must be declared. Neither option is the default; both must be explicit.

---

### What Behaviour May Not Influence

Behavioural state must not alter: packet IDs, packet lifecycle states (those are owned by the loading engine), cumulative boundary counts, observation frames, topology records, governance intervention records, or conservation accounting.

Behavioural state influences exactly one thing: which routing authority's recommendations a packet follows, and therefore what route intent is assigned at the next instantiation or re-route event.

---

### Open Questions

- **Calibration of θ and λ.** What empirical basis justifies the tolerance and sensitivity parameters for Cork demand? → benchmark_policy.md, and requires stated sources before any policy-relevant experiment is reported.
- **Trust update function.** How does trust_score_per_authority update? After each trip, after each re-route, or after each information receipt? What is the functional form? → to be specified before any multi-authority trust dynamics are modelled.
- **Pricing and experienced delay.** If a governance pricing overlay increases the perceived cost of a route, is that cost included in the excess delay signal ΔT_p, or does ΔT_p measure only physical travel time above free-flow? → governance_model.md.
- **Cohort heterogeneity.** May packets within the same cohort class have different θ_p and λ values drawn from a distribution? If so, the distribution parameters and seed are part of the reproducibility bundle. → to be declared before any heterogeneous compliance scenario is modelled.
- **Authority market share dynamics.** How does the aggregate compliance_state distribution across all active packets feed back into routing authority decision inputs? → routing_authorities.md.

---
