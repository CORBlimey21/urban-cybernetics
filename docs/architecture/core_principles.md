Status: constitutional document. These rules constrain all other design decisions.
Non-scope: does not define algorithms, equations, schemas, or implementation methods.

P0. Ownership Rule. Every canonical state variable must declare: owner, source of truth, time basis, units, mutability, readers, writers, and derivation status. If a variable cannot answer all eight, it is not yet defined.
P1. [INVARIANT] The loading engine owns canonical physical truth.
No other subsystem — topology, routing authority, observability layer, governance layer, behaviour layer, or adapter — holds or mutates canonical physical state during a run.
P2. [INVARIANT] Topology is immutable during a run.
Topology defines static directed connectivity and physical metadata. Nothing that changes during simulation may be stored on a topology record. Closures, signal states, pricing overlays, and capacity restrictions are governance state, not topology mutations.
P3. [INVARIANT] Observations are not physical truth.
An observation frame is a sampled, delayed, potentially noisy artifact derived from physical truth at a past measurement time. It is not the current state of the network. Calling any observation "truth" is a terminology error.
P4. [INVARIANT] Observation frames are immutable after publication.
A published frame may not be altered. Corrections are new frames with new identifiers. The original is preserved.
P5. [INVARIANT] Packets are conserved.
Every packet instantiated from a demand declaration must exit, be explicitly cancelled, or be accounted for at run termination. Silent disappearance is a bug, not a model event.
P6. [INVARIANT] Routing authorities do not mutate physical state.
An authority issues route recommendations or assignments. It does not move packets, alter cumulative counts, or modify topology. The loading engine alone executes physical movement.
P7. [INVARIANT] Governance mutates constraints and information, not packet positions.
A governance intervention may close a link, retime a signal, alter pricing, or withhold an observation. It does not directly reposition or remove packets.
P8. [INVARIANT] Behaviour affects decisions, not conservation.
Behavioural state — compliance, churn, trust, route preference — influences which routing decisions a packet follows. It does not create, destroy, or duplicate packets.
P9. [INVARIANT] Derived summaries are not canonical state.
Travel time, density, speed, volume, and cost are derived from primary physical records. They may be cached and published as views, but they are not canonical state and must not be stored as primary outputs.
P10. [INVARIANT] Legacy BPR and static assignment are comparators only.
BPR functions and static equilibrium outputs may be used as provenance references or benchmark comparators. They are not dynamic model components, not loading physics, and not canonical link state.
P11. [INVARIANT] Every artifact must be reproducible.
Every experiment output must carry enough metadata — topology hash, manifest hash, configuration snapshot, seed registry, code version — for an independent party to reproduce the run.
P12. [INVARIANT] Ambiguous traffic terms must be qualified.
The terms volume, flow, occupancy, travel time, cost, capacity, delay, demand, route, and state must never appear in an output schema, test assertion, or canonical data structure without qualifiers as applicable: aggregation window, boundary direction, counting basis, and units. Unqualified use of these terms in canonical interfaces is a specification error.
