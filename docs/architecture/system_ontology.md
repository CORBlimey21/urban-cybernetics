system_ontology.md
Status: architectural contract.
Scope: defines what exists in the simulation universe, who owns it, and what each entity is forbidden to hold.
Non-scope: does not define LTM equations, loading algorithms, node transfer rules, behavioural update functions, routing policies, or artifact schemas. Those belong in the relevant specification documents.

Core Categories
Before defining entities, these four categories apply throughout the framework. Conflating them is a source of contamination.
Entity. Something that exists within the simulation universe: a packet, a link, a node, an authority, a sensor, a governance actor.
State. A value associated with an entity at a time. State may be immutable, append-only, or mutable-with-audit. State that cannot declare its owner and mutability is not yet defined.
Event. An append-only record that something happened. Events are never mutated after recording. Packet instantiation, link boundary crossing, node transfer, observation publication, governance intervention, and packet completion are events, not state updates.
Artifact. A persistent file or structured output record produced before, during, or after a run. Artifacts must be reproducible. Observation frames, experiment manifests, routing decision logs, and governance intervention logs are artifacts.
Derived view. A value recomputable from primary events or state. Travel time, density, speed, and aggregate volume are derived views. They must not become canonical state.

Model Layer Hierarchy
This hierarchy is conceptual: it expresses what each layer is responsible for and what it is permitted to read or influence. It is not a strict import order or dependency graph. A routing authority may read observation frames produced by the observability layer without the routing module importing from the observability module; the constraint is semantic ownership, not package structure.
LayerNameResponsibility0Topology and ProvenanceStatic physical structure1DemandTrip declarations before instantiation2LoadingPacket instantiation and physical dynamics3ObservabilitySampling, publication, and observation frames4RoutingRoute recommendations and assignments5BehaviourCompliance, churn, trust, adaptation6GovernanceConstraints, interventions, information release7Validation and BenchmarksEvidence, comparators, reproducibility

The Central Information Loop
The framework's scientific subject matter is not routing algorithms or traffic assignment. It is what happens when physical reality passes through an imperfect, delayed, asymmetric information pipeline before reaching the agents whose decisions shape that reality. The central loop is:
Loading engine produces physical truth → observability layer samples and seals observation frames → routing authorities form beliefs from delayed frames → authorities issue routing decisions → behaviour layer determines compliance → loading engine executes movement → loading engine produces physical truth.
Every interesting phenomenon in the framework — oscillatory congestion, authority market share dynamics, infrastructure-mediated control, cooperative instability — lives somewhere in the gap between physical truth and authority belief. The specification suite exists to make that gap precise, measurable, and reproducible.

Core Entities
Topology.
The static directed graph of physical infrastructure. Topology records are immutable after the topology hash is computed. A topology is identified by its hash, not by OSM IDs or NetworkX keys.

Owner: topology record
Mutability: immutable
Forbidden to hold: travel time, simulated volume, occupancy, signal state, pricing, BPR parameters, any quantity that changes during a run

Link.
A directed edge in the topology. Carries immutable physical metadata: canonical ID, length, declared static capacity metadata, free-flow speed, lane count, geometric polyline, directed connectivity, OSM provenance reference.

Owner: topology record
Mutability: immutable
Forbidden to hold: current travel time, live occupancy, marginal cost, effective capacity as modified by governance or loading, dynamic loading state of any kind

Node.
A point of directed connectivity in the topology. Carries immutable metadata: canonical ID, geographic coordinate, connectivity set, OSM provenance reference. Node transfer rules are specified separately; they are not topology.

Owner: topology record
Mutability: immutable
Forbidden to hold: signal phase as topology attribute (signal phase is governance state)

Canonical ID / Provenance ID / Adapter ID.
Three distinct identifier types. OSM IDs are provenance IDs: external references stored as metadata, not used as primary keys in outputs. NetworkX IDs are adapter IDs: used for routing computation convenience, not canonical. The framework assigns canonical IDs at topology import; these are the primary keys in all scientific outputs and artifact references.
Demand Declaration.
A trip request record produced by the demand pipeline before simulation begins. Carries origin node, destination node, declared departure time, cohort class, and manifest provenance. A demand declaration has no lifecycle, no conservation obligation, and no physical presence. It becomes a packet only at instantiation.

Owner: demand layer / manifest artifact
Mutability: immutable once committed to manifest
Not a packet

Packet.
The conserved movement unit instantiated from a demand declaration. A packet has stable identity, a lifecycle, route intent, and a conservation accounting entry. What a packet represents — an individual traveller, a vehicle, or a behaviourally homogeneous cohort — is declared by the experiment configuration and is a modelling choice, not an ontological commitment. Packet granularity must be consistent within a conservation ledger.

Primary owner: loading engine, which holds all physical and lifecycle state and is the sole authority on where a packet is and what has happened to it
Associated writers: the routing authority writes route intent at instantiation and at sanctioned re-route events, appended as audited events in the loading engine's record; the behaviour layer writes behavioural state through audited events referencing the packet ID
Packet ID: immutable after instantiation
Lifecycle state: append-only via events; no subsystem may directly overwrite a lifecycle record
Route intent: mutable only at documented re-route events; prior intent is archived, not deleted
[OPEN] Packet granularity: individual, vehicle, or cohort. Weighted packets raise additional FIFO and conservation questions. See packet_semantics.md.

Physical State.
The canonical record of what has physically happened in the simulation: where packets are, what has crossed which boundaries, what is queued where. Owned exclusively by the loading engine.

Owner: loading engine
Source of truth: loading engine's internal records for the active run
[BASE MODEL] In the packet-LTM implementation, physical state is expected to be represented through cumulative boundary counts, packet lifecycle events, link storage state, queue state, and node transfer events. The specific representation belongs in loading_state.md.
Forbidden: no other subsystem writes to physical state

Observation Frame.
An immutable artifact published by the observability layer, recording a sampled view of physical state at a defined measurement time, over a defined aggregation window, with declared noise and aggregation parameters. An observation frame is not physical truth. It is a record of what was measured, when, and how.

Owner: observability layer produces and publishes; any authority may receive and read
Mutability: immutable after publication
Timestamps: measurement_time (when physical state was sampled); publication_time (when the frame was published and became immutable)
Per-authority receipt: each authority records its own receipt_time as a separate receipt event referencing the frame ID; receipt_time is not a field on the frame itself
Forbidden: no subsystem may alter a published frame

Routing Authority.
An agent that issues route recommendations or route assignments to packets within its cohort. An authority operates on the information available to it at decision time: received observation frames, its own prior decision log, any authority-specific memory or belief state, and any information explicitly released to it by the governance layer. An authority cannot see physical truth directly. It cannot mutate physical state. It cannot observe another authority's internal state unless that state has been explicitly published.

Owner: routing layer
Types: [OPEN] cooperative municipal, commercial selfish, background/unrouted, hybrid. Classification belongs in routing_authorities.md.
Information set: received observation frames, own decision history, authority-specific belief or memory state, governance-released information. Scope and access policy for each authority type belong in routing_authorities.md.

Governance Intervention.
A deliberate action by a governance actor that alters the constraint environment or the information environment: signal retiming, link closure, access restriction, pricing change, or observation release policy. Governance interventions do not move packets. They become visible to other agents at a declared visibility_time, which may differ from the action_time.

Owner: governance layer records and executes; loading engine reads governance state when evaluating feasibility
Mutability: append-only log
Forbidden: governance may not alter packet identities, cumulative count records, or topology records

Behavioural State.
Per-packet or per-cohort records of compliance history, experienced excess delay, trust scores per authority, and route preference. Behavioural state influences future routing decisions. It does not alter conservation accounting.

Owner: behaviour layer
Mutability: mutable-with-audit; updated at declared behavioural update events via audited writes referencing packet ID
[OPEN] Update schedule: at trip completion, at re-route event, at information receipt, or at fixed intervals. Belongs in behaviour_adaptation.md.
[BASE MODEL] A logistic churn function driven by excess delay is the initial behavioural model. The function and its parameters belong in behaviour_adaptation.md, not here.

Experiment Run.
A complete, reproducible execution instance. Identified by its run ID. All outputs carry the run ID and a reproducibility bundle.

Owner: experiment orchestrator
Mutability: configuration is immutable after run begins; outputs are append-only during run
Required metadata: run_id, topology_hash, manifest_hash, config_snapshot, seed_registry, code_version. Detail belongs in artifact_contracts.md.

Artifact.
Any persistent structured output: a topology file, demand manifest, observation frame archive, routing decision log, governance intervention log, raw event log, derived summary, or validation report. Every artifact must be traceable to a run ID and reproducibility bundle.
Benchmark.
A defined comparison between a framework output and a reference value, with an explicit scientific claim, declared input artifacts, declared comparison scope, and declared validity conditions. A benchmark is not valid simply because it uses familiar methods.
Legacy Reference.
Static assignment outputs, BPR equilibrium results, and archived test outputs from the pre-migration codebase. These are provenance records and comparators. They are not dynamic model outputs, not canonical state, and not validation evidence for the packet-LTM framework. Import restrictions are defined in legacy_bpr_role.md.

Forbidden Ownership Summary
EntityForbidden to ownTopology / Link / NodeAny dynamic simulation state, BPR parameters, signal phase as topology attribute, effective capacity as modified by governanceDemand DeclarationLifecycle state, conservation obligations, physical position of any kindNetworkX graphCanonical state of any kindRouting authorityPhysical state, packet positions, another authority's internal stateObservability layerPhysical truth (it samples, does not own)Governance layerPacket identities or cumulative count recordsBehaviour layerConservation accountingLegacy referenceDynamic model state, canonical link physics
