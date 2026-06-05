**Status:** specification.
**Scope:** defines what a routing authority is, what information it is permitted to use, how it interacts with the loading engine, and the open questions governing authority types and competition.
**Non-scope:** does not define loading mechanics, observation frame structure, governance interventions, or behavioural update functions. Does not specify routing algorithms; those are policy choices within the authority interface defined here.

---

### What a Routing Authority Is

A routing authority is an agent that produces route intent for packets within its cohort. It operates on information available to it at decision time. It does not touch physical state. It does not observe physical truth directly.

This definition deliberately excludes algorithm specifics. A cooperative municipal authority and a commercial selfish authority are both routing authorities. They differ in their information sets, objectives, decision algorithms, and cohort membership — not in their structural relationship to the framework.

---

### Information Set

A routing authority's information set at decision time consists of:

**Received observation frames.** Frames published by the observability layer and received by this authority up to and including the current tick, subject to the authority's receipt delay model. Frames are immutable artifacts; the authority reads but does not alter them.

**Own decision history.** The authority's append-only log of prior routing decisions, including which frames were used and what routes were assigned.

**Authority-specific memory or belief state.** An authority may maintain an internal model of network conditions derived from accumulated frames and its own predictive logic. This belief state is private to the authority. It is not a canonical record and is not directly observable by other authorities unless explicitly published.

**Governance-released information.** Any information explicitly released to this authority by the governance layer through a declared information release mechanism. This is distinct from observation frames; it is a direct communication channel from governance to authority, subject to the access policy defined in governance_model.md.

An authority may not access: current physical truth from the loading engine; another authority's belief state or decision log unless explicitly published; observation frames not in its permitted access set; future simulation state.

---

### Authority Receipt Delay

Each authority has a declared receipt delay: the number of ticks between a frame's publication_time and the earliest tick at which the authority may consume it. Receipt delay is part of the experiment configuration and is immutable for the run.

The base model default is a receipt delay of one tick. An observation frame published in Phase 3 of tick k is available to a standard authority in Phase 4 of tick k+1. Zero-tick receipt delay — where a frame published in Phase 3 of tick k is consumed in Phase 4 of the same tick — is a permitted experiment configuration but must be explicitly declared in the config snapshot and flagged in any report that uses it, since it represents a best-case information latency not achievable in real deployments.

Receipt delay of zero means the authority may consume a frame in the same tick it was published (Phase 4 of the same tick as Phase 3 publication). This is the minimum delay. It does not mean the authority sees current physical state; the frame itself captures state from Phase 2 of that tick.

A longer receipt delay models communication latency, processing overhead, or deliberate information throttling.

---

### Route Intent Assignment

At departure instantiation (Phase 1 of each tick), the routing authority for each new packet's cohort assigns an initial route intent. The route intent is an ordered sequence of canonical link IDs from origin to destination.

The routing authority writes route intent to the packet record through an audited event appended by the loading engine. The authority proposes; the loading engine records. The routing authority does not write directly to loading state.

At a re-route event (triggered by governance intervention, by a node-level infeasibility, or by a behavioural update), the relevant routing authority may propose a new route intent for the affected packet. The loading engine records the re-route event and the updated intent.

[OPEN] Priority ordering when multiple subsystems propose a re-route for the same packet in the same tick. → to be resolved before multi-authority re-route scenarios are implemented.

---

### Authority Types

The base model includes three authority types. Each is a policy choice implemented within the routing authority interface; the framework does not prescribe routing algorithms, only information set constraints.

**Cooperative municipal authority.** Operates on its own information set with the objective of optimising a system-wide metric (total delay, equity, emissions, or a combination). Issues route recommendations. Compliance is not guaranteed; the behaviour layer determines whether a packet follows the recommendation.

**Commercial selfish authority.** Operates on its own information set with the objective of minimising individual travel time for its cohort. Issues route assignments that its cohort is assumed to follow unless the behaviour layer triggers defection. The commercial authority's internal algorithm is [OPEN]; it must be declared before any asymmetric-information experiment is designed.

**Background demand.** Packets not associated with either authority. They follow a declared default routing policy (typically static shortest-path or a fixed distribution over known routes). Background demand introduces stochastic urban friction without requiring a full authority model.

[OPEN] Hybrid authority types, partially cooperative authorities, and dynamic market-share models are reserved as extensions.

---

### Oracle Baseline

[OPEN] An oracle authority has access to current physical truth rather than observation frames. It represents a theoretical performance ceiling: the best routing any authority could achieve with perfect, instantaneous information.

An oracle baseline is potentially valuable as a benchmark comparator. However, it must be clearly isolated from empirical authority comparisons: an oracle is not a realistic authority type. If included in an experiment, its outputs must be reported separately and must not be used to calibrate empirical authority parameters.

The conditions under which an oracle authority is permitted in an experiment, and the reporting requirements that govern it, must be declared in benchmark_policy.md before the oracle is implemented.

---

### Asymmetric Information

The core research premise is that routing authorities operate under asymmetric information. This asymmetry has several dimensions in the framework.

**Delay asymmetry.** Different authorities may have different receipt delays, meaning they operate on observation frames of different ages.

**Access asymmetry.** Governance may release different observation streams to different authorities, or withhold certain streams entirely. This is modelled as a governance intervention of type `INFORMATION_RELEASE_POLICY`. → governance_model.md.

**Resolution asymmetry.** Different authorities may have access to sensors with different aggregation windows, noise levels, or spatial coverage.

**Belief asymmetry.** Different authorities may form different beliefs from the same observation frame, depending on their internal predictive models and memory.

None of these asymmetries are anomalies to be corrected. They are the scientific subject matter of the framework.

---

### Baseline Shortest-Path Policy

The framework includes a baseline routing policy in which an authority assigns each new packet the shortest path from origin to destination under a declared link cost surface derived from the authority's most recent observation frame. This policy exists as a reference implementation, not as the canonical definition of routing. It demonstrates that the routing authority interface works and provides a reproducible baseline for comparison.

Using shortest-path as the only available routing policy would reduce routing authorities to scalar edge-cost consumers, which the contamination report specifically identifies as a contamination risk. The baseline policy must be named and scoped as a policy option, not embedded as the framework's routing ontology.

---

### Decision Log

Every routing authority maintains an append-only decision log for the run. Each entry records: decision_id, authority_id, decision_time (tick), frame_ids_used (list of frame IDs that informed the decision), cohort_id or packet_id, route_assigned (canonical link ID sequence), and any declared policy parameters used.

The decision log is part of the run artifact. It enables complete reconstruction of the causal chain from physical event to routing decision.

---

### Open Questions

- **Commercial authority algorithm.** What routing algorithm does the commercial authority use? Shortest path under observed cost, iterative best-response, or other? Must be declared before any multi-authority experiment. → to be resolved before Milestone 4 in recommended_next_steps.md.
- **Re-route priority ordering.** If governance, routing authority, and behaviour layer all propose a re-route for the same packet in the same tick, what is the resolution order? → governance_model.md, node_model_assumptions.md.
- **Authority belief representation.** Is belief state a structured artifact or opaque internal state? If structured, does it need to be included in the run artifact for reproducibility? → to be resolved before any authority that maintains non-trivial predictive models is implemented.
- **Authority market share dynamics.** In multi-trip models, how does packet cohort membership change as packets churn between authorities? → behaviour_adaptation.md.
- **Observation access policy.** Symmetric or asymmetric by default? Which authority receives which sensor streams? → governance_model.md.
- **Oracle baseline governance.** Under what experimental conditions is an oracle authority permitted, and what reporting requirements apply? → benchmark_policy.md.

---
