
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

The architectural and specification phase is complete.

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

Implementation is currently focused on synthetic-network validation before any real-world deployment or calibration.

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

Immediate Goals

Implement a minimal loading engine capable of passing the synthetic invariant suite:

* Packet identity stability
* Demand-to-packet uniqueness
* Lifecycle monotonicity
* Conservation
* FIFO preservation
* Queue propagation

Real-world networks, calibration, and multi-authority experiments are to come.
