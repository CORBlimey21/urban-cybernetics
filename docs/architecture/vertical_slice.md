

Vertical Slice Status: M1–M15

Status

The initial Urban Cybernetics vertical slice is now implemented and passing.

The current repository contains a working synthetic end-to-end loop:

packetised loading kernel
→ physical event history
→ cumulative counts and storage
→ immutable observation frames
→ delayed authority-visible frame sets
→ routing authority decisions
→ selected route intents
→ realised packet movement

The full test suite currently passes under both unittest and pytest.

unittest: 129 tests OK
pytest:   129 passed

This marks the first point at which the project is more than a collection of traffic-model components. It now has a complete, synthetic, auditable cybernetic loop.

⸻

What Has Been Built

Physical Loading Kernel

The physical kernel is a simplified packetised LTM-style dynamic loading model.

It includes:

* immutable packet records;
* append-only packet lifecycle events;
* engine-owned physical state;
* route intent and realised path tracking;
* upstream-boundary queues;
* strict FIFO link behaviour;
* explicit node transfer policy;
* diverge handling;
* global-FIFO merge allocation;
* event-derived cumulative boundary counts;
* count-derived link storage;
* explicit sending function / upstream supply;
* explicit receiving function / downstream acceptance;
* storage-constrained receiving;
* basic spillback;
* synthetic validation scenarios covering the kernel as a system.

Physical truth is owned by the loading engine and recorded through event history. Link records remain frozen/static metadata. Dynamic quantities such as storage, counts, sending, receiving, and packet membership are derived views, not topology state.

Observability Layer

The observability layer turns physical event history into immutable observation frames.

M12 introduced:

* frozen sensor configurations;
* frozen observation frames;
* boundary-count sensors for LINK_ENTRY and LINK_EXIT;
* start-exclusive/end-inclusive aggregation windows;
* publication ticks;
* deterministic frame IDs;
* noise metadata, currently "none";
* tests proving sampling does not mutate loading state.

Observation frames are artifacts. They are not physical truth and are not owned by routing authorities.

Routing and Visibility Layer

The routing layer introduces authorities as decision-making agents that consume observation artifacts.

M13 introduced:

* frozen routing authority configuration;
* frozen route-choice requests;
* frozen route-decision artifacts;
* private, append-only authority decision logs;
* candidate-route policies;
* tests proving routing authorities do not read loading truth or mutate physical state.

M14 introduced delayed authority-visible state:

* frozen authority visibility configurations;
* frozen frame receipt artifacts;
* authority-specific receipt delays;
* static sensor access filtering;
* deterministic visible-frame ordering;
* tests proving authorities only decide from supplied visible frames.

First Asymmetric-Information Experiment

M15 introduced the first synthetic asymmetric-information routing experiment.

The experiment demonstrates that:

* two authorities can be given the same observation archive;
* different receipt delays produce different visible frame sets;
* a fresh authority can see recent congestion information;
* a stale authority cannot yet see that information;
* route decisions differ because of visible information;
* selected route decisions can be applied as packet route intents;
* packets then follow those selected routes through the loading kernel.

This is the first working demonstration of the project’s central idea: routing decisions are shaped not only by physical traffic state, but by what information an authority can observe, when it can observe it, and what route policy it applies.

Repeated Fresh-vs-Stale Authority Experiment

R1a extends the M15 proof from a single decision opportunity to a small repeated
experiment.

The experiment deliberately remains a milestone-specific implementation, not a
generic experiment engine. It demonstrates:

* repeated demand waves over several decision ticks;
* repeated O1 traversal-time observation generation;
* M14 visibility resolution for fresh and stale authorities;
* repeated route decisions by identical authority policy under different receipt delays;
* packet instantiation from those decisions;
* realised path comparison against selected routes;
* P1 recording of observation frame IDs, receipt IDs, decision IDs, packet IDs, and the focused R1a result artifact ID.

The only meaningful difference between the two authorities is observation
availability. Both authorities consume supplied frames only; neither authority
inspects loading events, packets, cumulative counts, storage, queues, sending,
receiving, or loading internals.

R1a does not add behaviour, churn, market share, governance intervention,
route-search, databases, dashboards, statistics, OSM import, or Cork networks.
It is a compact repeatability proof for asymmetric-information routing over
multiple decision cycles.

⸻

What This Does Prove

The current system proves that the architecture can support a complete synthetic cybernetic traffic loop.

Specifically, it proves:

1. Physical loading can be represented through event-led packet dynamics.
2. Cumulative counts, storage, sending, receiving, and spillback can be derived from event history without contaminating topology.
3. Observation frames can be sampled from physical truth without becoming physical truth.
4. Authorities can be restricted to authority-visible observation frames.
5. Receipt delay and sensor access can create information asymmetry.
6. Routing decisions can be audited through frame IDs used, authority ID, request ID, selected route, and policy name.
7. Different visible information can produce different route decisions.
8. Selected route decisions can be applied to packet movement through the existing loading kernel.
9. The full chain remains deterministic and testable on synthetic networks.

This is a valid first vertical slice of the Urban Cybernetics research framework.

⸻

What This Does Not Yet Prove

The current system should not be overclaimed.

It does not yet prove:

* full academic LTM fidelity;
* kinematic-wave consistency;
* triangular fundamental diagram behaviour;
* backward-wave or vacancy propagation;
* Newell-style travel-time consistency;
* empirical realism on Cork or any real city;
* realistic demand generation;
* realistic signal timing;
* lane-level behaviour;
* roundabout or priority-junction behaviour;
* commercial routing-platform realism;
* behavioural churn;
* governance-mediated intervention;
* calibrated policy relevance.

The current loading kernel is best described as:

a simplified packetised LTM-style dynamic loading kernel

not as a complete LTM solver or city-scale traffic simulator.

The current asymmetric-information experiment is best described as:

a synthetic proof of the cybernetic loop

not as an empirical transport-policy result.

⸻

Architectural Invariants Preserved

The implementation has preserved the main architectural boundaries:

* The loading engine owns physical truth.
* The packet event log is canonical.
* Topology records are static.
* Dynamic quantities are derived views or engine-owned materialisations.
* Observation frames are immutable artifacts.
* Observation frames do not contain authority receipt state.
* Authority visibility is separate from observation publication.
* Routing authorities consume supplied frames only.
* Routing decisions are artifacts, not physical mutations.
* Loading does not import routing.
* Routing does not import the loading engine.
* Policies choose routes but do not mutate packets or events.

These boundaries are the reason the system has been able to grow quickly without collapsing into legacy-style contamination.

⸻

Current Test Coverage

The current suite includes tests for:

* packet identity stability;
* conservation from events;
* lifecycle/cache consistency;
* FIFO link behaviour;
* receiving constraints;
* queue semantics;
* route progression;
* strict-FIFO diverge;
* global-FIFO merge;
* cumulative boundary counts;
* count-derived storage;
* sending function;
* receiving function;
* storage-constrained receiving;
* basic spillback;
* synthetic LTM validation scenarios;
* observation frame immutability and timing;
* routing authority interface;
* delayed authority-visible state;
* first asymmetric-information routing experiment;
* import and legacy quarantine guardrails.

The suite currently reports:

129 tests passing

under both unittest and pytest.

⸻

Recommended Next Directions

The project now has several viable next tracks. These should be treated as deliberate tracks, not random feature additions.

Track A — Experiment Artifacts and Provenance

Turn the M15 test into a reusable experiment artifact.

Possible additions:

* ExperimentConfig;
* ExperimentResult;
* run ID;
* authority config references;
* sensor config references;
* frame IDs;
* receipt IDs;
* decision IDs;
* selected routes;
* realised paths;
* basic outcome metrics.

This would make the vertical slice reportable and reproducible outside a test file.

Track B — Cybernetic Experiment Depth

Expand from one synthetic decision to repeated decision cycles.

Possible additions:

* multiple demand waves;
* repeated authority decisions;
* fresh vs stale authority over several ticks;
* route-choice outcome summaries;
* experienced delay comparison;
* authority frame-usage summaries.

This deepens the core research idea without needing real-city data yet.

Track C — Observability Depth

Add more observation types while keeping frames immutable.

Possible additions:

* storage/occupancy frames;
* queue-length frames;
* node-transfer count frames;
* derived speed/travel-time frames later;
* noisy sensor models;
* sensor dropout;
* frame supersession/correction.

This would strengthen the information layer.

Track D — Physical LTM Fidelity

Improve the physical kernel toward stricter LTM/kinematic-wave behaviour.

Possible additions:

* triangular fundamental diagram metadata;
* jam-density-derived storage capacity;
* backward wave speed;
* vacancy propagation;
* Newell-style travel-time consistency;
* CTM/LTM benchmark comparison scenarios.

This should be done carefully and tested against known synthetic traffic-flow cases.

Track E — Governance and Behaviour

Introduce the feedback layers that make the system more distinct.

Possible additions:

* governance-controlled sensor access;
* information withholding;
* link closures;
* signal retiming;
* pricing overlays;
* compliance state;
* experienced-delay-based churn;
* authority market share.

This is likely where the project becomes most scientifically distinctive.

Track F — Real Networks and Visualisation

Begin moving beyond toy graphs.

Possible additions:

* tiny synthetic grid;
* small Cork subnetwork;
* OSM import artifact;
* canonical topology IDs;
* replay visualisation;
* interactive scenario viewer.

This track is valuable, but it should not be rushed before experiment artifacts and provenance are cleaner.

------------------------------------------------------------------------

Summary

The project now has its first complete vertical slice.

It is not yet a realistic city simulator and not yet a full academic LTM solver. But it is now a coherent, tested, synthetic cybernetic traffic framework: physical traffic generates observations; observations become authority-visible information; authorities make audited route decisions; decisions become route intents; packets move through the loading kernel; and the resulting event history remains reproducible.

That is the core research machine.
