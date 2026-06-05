# Legacy Contamination Report

Audit date: 2026-05-28

Scope: focused audit for lingering BPR, static-assignment, scalar-cost, occupancy-derived-flow, mutable edge-state, and app/demo/product assumptions after selective migration.

## Executive Assessment

Legacy contamination is present but mostly visible. That is good news: the old BPR lifecycle engine has not silently returned wholesale, and the strongest static-assignment material is under `legacy/bpr_reference`. The risk is that several active modules still encode the old ontology in names, attributes, defaults, and comments. If these are allowed to become the basis of the packet-LTM implementation, the future simulator will inherit static scalar-cost assumptions before its physical model exists.

The most serious contamination vector is active mutable NetworkX edge state in `src/urban_cybernetics/network/graph_pipeline.py`. The second is delayed observability framed as edge-cost snapshots. The third is active benchmark code exposing BPR parameters in source package space. The fourth is demand/manifest naming around selfish routing and route requests rather than packet demand events.

## Contamination Inventory

### Mutable NetworkX Edge State

Location: `src/urban_cybernetics/network/graph_pipeline.py`

Evidence:

- Module purpose says it keeps "graph mutation rules" centralized.
- Edge attributes include `travel_time_seconds`, `marginal_cost_seconds`, `simulated_volume`, `live_occupancy_count`, `peak_live_occupancy_count`, `peak_simulated_volume`, and `peak_travel_time_seconds`.
- `reset_simulation_edge_state` mutates edge dictionaries back to a free-flow baseline.
- Route helpers read scalar weights from graph edges and return aggregate travel time.

Why it matters scientifically:

Packet-LTM should make cumulative counts, queue state, link receiving/sending constraints, and packet lifecycle the source of truth. A mutable NetworkX edge dictionary is an adapter-friendly representation, but it is not an adequate canonical physical state. If edge attributes become canonical, the simulator will tend toward "update link cost from volume/occupancy" instead of "derive experienced times from cumulative flow and node transfer."

Recommended status: risky/provisional. Keep as an OSM import/routing adapter or legacy smoke-test tool. Do not use it as loading state.

### BPR Cost Language In Active Network Code

Location: `src/urban_cybernetics/network/graph_pipeline.py`

Evidence:

- Routing-weight multiplier documentation refers to avoiding "extreme BPR blowup under high demand".
- `add_travel_time_weights` says penalized routing weights leave "underlying BPR travel times" unaffected.
- Comments refer to a "BPR cost-refresh loop".
- The module tracks marginal costs for system optimum routing.

Why it matters scientifically:

BPR is a static link performance function. Packet-LTM uses time-dependent cumulative flows, capacity constraints, link travel times, and FIFO-compatible propagation. Retaining BPR as benchmark reference is fine. Using BPR language in active network preparation makes future developers reach for scalar cost refreshes rather than packet/cumulative-flow mechanics.

Recommended status: risky. Remove or quarantine BPR terminology from active non-benchmark modules before implementing loading.

### Scalar Edge Cost As Routing Ontology

Locations:

- `src/urban_cybernetics/network/graph_pipeline.py`
- `src/urban_cybernetics/observability/snapshot_buffer.py`
- `legacy/bpr_reference/static_assignment.py`

Evidence:

- Route helpers default to `weight="travel_time_seconds"`.
- Snapshot routing receives a dictionary of edge-key to cost fields.
- Static assignment uses edge-cost vectors and shortest paths.

Why it matters scientifically:

A routing authority under asymmetric information should not be reduced to "pick shortest path under one scalar edge cost" as the canonical interface. Authorities may operate on delayed observations, policy constraints, predictive beliefs, compliance expectations, information disclosure strategies, infrastructure control state, and behavioural cohorts. A scalar edge cost can be a derived benchmark view, but should not define the authority protocol.

Recommended status: provisional in active graph routing, legacy-reference in BPR solver.

### Occupancy-Derived Flow And Vehicle Lifecycle Semantics

Locations:

- `src/urban_cybernetics/network/graph_pipeline.py`
- `src/urban_cybernetics/observability/snapshot_buffer.py`
- `scripts/05_calibrate_validate.py`

Evidence:

- Active graph state stores `live_occupancy_count` and `peak_simulated_volume`.
- Snapshot buffer records live occupancy and simulated volume.
- Validation script expects link-level AM volume as "trips using each edge".

Why it matters scientifically:

Live occupancy is not flow. In packet-LTM, flow is measured through boundary crossing rates and cumulative counts. Occupancy can be a state or observable, but deriving peak hourly flow from occupancy risks violating conservation and temporal semantics, especially under queues, spillback, and heterogeneous link lengths.

Recommended status: risky if canonical; acceptable as a legacy diagnostic if explicitly labelled.

### Static Assignment Solver In Legacy

Location: `legacy/bpr_reference/static_assignment.py`

Evidence:

- Implements UE, SO, and C-SO MSA assignment.
- Uses BPR travel time and marginal cost vectors.
- Assigns OD demand to shortest paths.
- Evaluates total system travel time from static flow vectors.

Why it matters scientifically:

The solver is useful as provenance and benchmark reference, but it models equilibrium over static flow, not time-dependent packet loading. Its "C-SO" constrained system optimum has conceptual overlap with asymmetric routing authorities, but the mathematics and state model are not the same. If copied forward, it would reintroduce static assignment thinking into a dynamic cybernetic framework.

Recommended status: legacy-reference/quarantined. Preserve for historical comparison, but keep outside active package imports.

### Static Assignment Tests In Archive

Location: `legacy/archived tests`

Evidence:

- Tests assert BPR helper behavior, UE/SO/CSO outcomes, static flow vector shapes, and Sioux Falls assignment properties.
- Imports refer to active `urban_cybernetics.benchmarks.network_costs` and `urban_cybernetics.benchmarks.static_assignment`, which no longer exist.

Why it matters scientifically:

These tests protect old behavior, not the future ontology. Their imports are stale, which is useful evidence that migration did not fully preserve executable legacy reference. Reviving them under active `tests` would pull the repository back toward static assignment unless they are renamed and scoped as explicit legacy reference tests.

Recommended status: archived/quarantined.

### Active Sioux Falls Loader Carries BPR Fields

Location: `src/urban_cybernetics/benchmarks/sioux_falls.py`

Evidence:

- Builds a NetworkX `DiGraph` with `capacity`, `free_flow_time`, `bpr_alpha`, and `bpr_beta`.
- Describes benchmark data as ready for "future assignment code".

Why it matters scientifically:

Sioux Falls is valuable, but its TNTP fields are static-assignment fields. If active benchmark objects expose BPR parameters as normal link attributes without a quarantine label, future dynamic code may treat BPR capacity/free-flow tuples as canonical link physics. For packet-LTM, capacity and free-flow time may remain relevant, but alpha/beta should be benchmark-reference metadata, not dynamic model state.

Recommended status: provisional. Split neutral TNTP parsing from static-reference adapters.

### Manifest Naming Around "Selfish" Batches

Locations:

- `data/manifests/canonical_selfish_batch_manifest_v1.json`
- `src/urban_cybernetics/packets/scenario_manifest.py`

Evidence:

- Canonical path helper is named `canonical_selfish_manifest_path`.
- Loader is named `load_canonical_selfish_manifest`.
- Manifest notes freeze a "selfish benchmark input".

Why it matters scientifically:

"Selfish" is a route-choice policy, not a demand input property. A trip manifest should describe demand events. The routing authority, compliance model, or control layer should determine whether those packets follow selfish, advised, constrained, habitual, or adaptive policies. Encoding "selfish" in canonical demand loaders blurs demand with behavioural/routing policy.

Recommended status: provisional/risky. Rename conceptually to canonical Cork demand input or benchmark demand manifest; keep selfish policy in experiment/control configuration.

### Demand As Trip Requests, Not Packets

Location: `src/urban_cybernetics/packets/demand.py`

Evidence:

- `TripRequest` contains origin/destination nodes, coordinates, names, and `departure_minute`.
- Module says it provides structures used by routing and simulation code.
- No packet identity, lifecycle, class, cohort, behavioural attributes, or authority assignment exists.

Why it matters scientifically:

Trip requests are pre-packet demand declarations. Packets are simulation entities with lifecycle and conservation obligations. Treating a trip request as a packet risks losing distinction between input demand, packet instantiation, route intent, and observed movement through the network.

Recommended status: foundational as demand input, not as packet model. Rename or split before implementing lifecycle logic.

### OD Matrix Script Encodes Legacy Planning Semantics

Location: `scripts/02_build_od_matrix.py`

Evidence:

- Builds a gravity model from SAPS and employment attraction.
- Converts drivers plus passengers into car commuters with comment "both occupy road space".
- Calibrates to feeder targets and cordon counts.
- Emits a trip manifest after snapping ED centroids to graph nodes.
- Uses `dest_node` in emitted trip dictionaries, while active package dataclass expects `destination_node`.
- Uses departure time in seconds from midnight, while active `TripRequest` uses departure minute.

Why it matters scientifically:

The script is useful as provenance for Cork demand generation, but it mixes planning-model calibration, graph snapping, manifest generation, and simulator-facing schema. It also contains a scientifically questionable occupancy statement: passengers do not independently occupy road space in the same way as driver-vehicle units unless the model explicitly counts vehicle occupancy. This matters because the future packet ontology must distinguish person trips, vehicle trips, packets, and occupancy.

Recommended status: provisional/risky. Keep as provenance until rewritten as a reproducible demand-generation pipeline with explicit units and schema.

### Validation Script Assumes Edge Volumes

Location: `scripts/05_calibrate_validate.py`

Evidence:

- Expects `outputs/sim_link_volumes.csv` with `am_volume = trips using that edge`.
- Computes GEH against observed vehicle counts.
- Loads `outputs/cork_metro_graph.graphml`, while OD script uses `data/graphs/cork_full_drive.graphml`.

Why it matters scientifically:

For packet-LTM validation, link counts should be defined by boundary crossings over an aggregation window, not by "trips using an edge." "Used edge" can mean path membership, entry count, exit count, occupancy at a time, or completed traversal. GEH validation is useful, but the export contract must use precise cumulative-flow semantics.

Recommended status: provisional. Rewrite once packet-LTM output semantics are specified.

### App/Demo Framing

Location: `src/urban_cybernetics/network/graph_pipeline.py`

Evidence:

- Mentions "basic graph demo" and "Week1 artifacts".
- Renders Folium map outputs as smoke-test artifacts.

Why it matters scientifically:

This is low severity but relevant. Demo/map helpers are useful for inspection, but they should not shape core architecture. A research framework should distinguish visualization adapters from the model core.

Recommended status: low-risk provisional. Move to scripts or visualization adapter later.

## Missing Quarantine Mechanisms

The repository has a `legacy` directory, but does not yet have formal guardrails:

- No docs state what legacy code may import from active source.
- No active test enforces that canonical packages avoid legacy BPR modules.
- No benchmark policy distinguishes static BPR reference from dynamic packet-LTM benchmarks.
- No package-level deprecation/quarantine notes exist.

Recommended guardrail tests:

- Importing `urban_cybernetics.loading`, `packets`, `routing`, `observability`, `governance`, or `behaviour` must not import `legacy` or BPR reference modules.
- Canonical topology/link state types must not include `bpr_alpha` or `bpr_beta`.
- Packet/loading output contracts must not use ambiguous `volume` without a crossing-window definition.

## Overall Risk Rating

Legacy contamination risk: high if development proceeds immediately into simulator implementation; moderate if ontology documents and invariant tests are written first.

The contamination is not subtle enough to be invisible, but it is pervasive enough in active module comments and attributes to influence future code. The remedy is not wholesale deletion. The remedy is explicit quarantine, renaming, and a small canonical model layer whose names make the intended science harder to accidentally violate.

