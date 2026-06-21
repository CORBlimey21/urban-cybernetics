
Urban Cybernetics

A packet-based urban traffic simulation framework for studying how information, behaviour, and infrastructure interact in transportation systems, developed as part of ongoing research into cybernetic urban traffic systems.

The framework models traffic as a dynamic system in which physical network conditions are observed through delayed and imperfect information, interpreted by routing authorities, acted upon by travellers, and fed back into the network itself.

Core Loop

Physical State
→ Observation
→ Belief
→ Routing Decision
→ Behavioural Response
→ Physical State

Current Status

The architectural and specification phase is complete, and implementation is now
moving through focused milestones.

Defined components include:

* System ontology and ownership boundaries
* Packet semantics and conservation rules
* Loading-state architecture
* Observability and information-delay model
* Routing authority framework
* Governance and intervention model
* Behavioural adaptation model
* Reproducibility and artifact contracts
* Synthetic invariant test suite
* Pre-packet OD demand, scheduling, scaling, and benchmark loading smoke runs
* Run outcome inspection summaries

Implementation is currently focused on synthetic-network validation and
benchmark-demand execution before any real-world deployment or calibration.

Repository Structure

docs/
├── architecture/
├── specifications/
├── policies/
├── audits/
└── benchmarks/
src/
tests/

Reading Order

1. docs/architecture/core_principles.md
2. docs/architecture/system_ontology.md
3. docs/specifications/loading_state.md
4. docs/specifications/timestep_semantics.md
5. docs/specifications/invariants.md

Track shorthand:

* P = what was used and whether a run can be reproduced and audited
* D = what demand was declared, scheduled, scaled, generated, or loaded
* I = what happened in a run
* R = what claim was tested

Real-world networks, calibration, dashboards, and authority/governance analytics
are to come.
