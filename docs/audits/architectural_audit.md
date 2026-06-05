# Architectural Audit Report

Audit date: 2026-05-28

Repository: `urban-cybernetics`

Scope: inaugural architecture audit after selective migration from the legacy Cork traffic-assignment codebase. This report evaluates repository coherence, package boundaries, scientific semantics, reproducibility surfaces, dependency topology, and scalability toward a packet-based mesoscopic cybernetic urban mobility framework. It does not specify or implement simulator logic.

## Executive Assessment

The repository has the beginnings of the right architecture, but it is not yet a coherent scientific framework. It currently resembles an early research scaffold: promising directory names, useful migrated artifacts, and several good instincts around provenance and immutable scenario inputs, but with incomplete package migration, empty specifications, no active tests, undeclared dependencies, and visible legacy ontology still embedded in import paths and source semantics.

The main architectural success is separation by future subsystem: `network`, `packets`, `loading`, `nodes`, `routing`, `observability`, `governance`, `behaviour`, `validation`, `benchmarks`, and `provenance` exist as named packages. That is the correct vocabulary for the intended framework. The main architectural failure is that most of these packages are empty, while the non-empty code still carries old static routing, mutable edge-state, BPR, and route-demo assumptions. As a result, architecture is currently implied more by filenames than by executable contracts.

The migration is directionally clean because the static BPR solver has been moved to `legacy/bpr_reference`, and active source does not include the full old assignment engine. However, the active source still includes BPR-shaped benchmark attributes, a mutable OSM/NetworkX graph pipeline, delayed cost-surface snapshots, and demand manifests named around "selfish" routing. These can be useful, but only if explicitly quarantined as benchmark/provenance surfaces and kept out of canonical loading semantics.

## Repository Structure

Current top-level layout:

- `src/urban_cybernetics`: installable package namespace.
- `docs`: intended architecture, benchmark, migration, and specification documentation.
- `data`: committed benchmark, manifest, OD, and count artifacts.
- `legacy`: migrated BPR/static-assignment reference code and archived tests.
- `scripts`: migrated OD-building and validation scripts.
- `tests`: nominal active test directory, currently containing only cache artifacts.
- `experiments`: empty top-level experiment area.
- `benchmarks`: empty top-level benchmark area except metadata artifacts.

This split is conceptually appropriate. It already distinguishes canonical package code from scripts, data, and legacy material. The weakness is that important semantics have not been written into the intended documentation files. All files under `docs/architecture`, `docs/specifications`, `docs/benchmarks`, and `docs/migration` were zero bytes at audit time. The repository therefore lacks a durable ontology despite having ontology-themed filenames.

## Package Boundaries

Observed active packages:

- `urban_cybernetics.network`: OSMnx/NetworkX graph loading, free-flow travel times, mutable edge weights, routing helpers, and Folium map rendering.
- `urban_cybernetics.packets`: currently demand and manifest helpers, not packet lifecycle entities.
- `urban_cybernetics.observability`: delayed cost-surface snapshot buffer.
- `urban_cybernetics.benchmarks`: TNTP parsing and Sioux Falls benchmark loading.
- `urban_cybernetics.loading`, `nodes`, `routing`, `governance`, `behaviour`, `validation`, `provenance`: empty namespace placeholders.

Good separation exists at the directory level. Graph IO is isolated from demand helpers; benchmark parsing is separate from Cork manifests; observability has its own package. The problem is that executable responsibilities do not yet match the intended package names. For example, `packets/demand.py` defines `TripRequest`, not packet state; `network/graph_pipeline.py` owns routing and mutable simulation fields; `observability/snapshot_buffer.py` knows about edge cost fields and live occupancy. State ownership is therefore already ambiguous even before packet-LTM code exists.

The highest-risk boundary is between `network`, `loading`, and `observability`. In a packet-LTM framework, static topology and geometry should not be the canonical mutable state. The loading engine should own cumulative counts, queues, link sending/receiving constraints, and packet position/lifecycle. Observability should own sampled or delayed views of that state. The current active `network` module instead mutates edge dictionaries with `travel_time_seconds`, `marginal_cost_seconds`, `simulated_volume`, and `live_occupancy_count`. That is convenient for legacy lifecycle simulation but conflicts with a cumulative-flow ontology.

## Import Topology

The import graph is small and not circular, but it is currently broken:

- `urban_cybernetics.benchmarks.sioux_falls` imports `urban_cybernetics.config`, which does not exist.
- `urban_cybernetics.network.graph_pipeline` imports `urban_cybernetics.network.config`, which does not exist.
- `urban_cybernetics.packets.demand` imports `urban_cybernetics.packets.config` and `urban_cybernetics.packets.graph_pipeline`, neither of which exists.
- `urban_cybernetics.packets.scenario_manifest` imports `urban_cybernetics.packets.config`, which does not exist.
- Archived tests import `urban_cybernetics.benchmarks.network_costs` and `urban_cybernetics.benchmarks.static_assignment`, but those files now live under `legacy/bpr_reference`.

This is not a deep dependency problem yet; it is a selective migration incompleteness problem. The package can compile, but several modules cannot import with `src` on `sys.path`.

Recommended dependency direction for the next architecture pass:

- `network` should define static topology records and graph import/export adapters.
- `packets` should define packet identity, demand declarations, and immutable request inputs.
- `loading` should depend on topology and packets, and own dynamic link/node state.
- `observability` should depend on loading state views or public state protocols, not on live NetworkX edge dictionaries.
- `routing` should depend on topology plus observable authority views, not mutate topology.
- `governance` should depend on routing/control abstractions and observability, not on raw NetworkX.
- `benchmarks` should depend on parsers and benchmark data only; BPR-specific utilities should remain under `legacy` or a clearly named `benchmarks/static_assignment_reference` namespace.

## Data And Experiment Organization

The `data` directory contains meaningful committed artifacts:

- Sioux Falls TNTP network and trips.
- Cork scenario manifests ranging from 200 trips to more than 120k trips.
- OD matrix and zone index artifacts.
- Count data for cordon and a small TII-style sample.

This is stronger than a toy repository because it contains benchmark and calibration inputs. However, the artifact strategy is not yet research-grade:

- Large generated manifests are committed without a manifest schema or provenance digest.
- `data/manifests/*.json` includes several related schema variants, but no formal contract defines required fields, units, ID namespace, or generator.
- `canonical_selfish_batch_manifest_v1.json` lacks an explicit `trip_count` field while later scaled manifests include one.
- Manifest departure semantics are mixed between minute-of-day values in active package dataclasses and second-of-day values in the migrated generation script.
- `experiments` is empty, so there is no current convention for run metadata, seeds, input hashes, code version, or output layout.
- Top-level `benchmarks` is empty while `src/urban_cybernetics/benchmarks` and `data/benchmarks` are meaningful, creating mild namespace ambiguity.

For a serious scientific framework, every run should become a reproducible artifact bundle with input manifest hash, topology hash, code version, model settings, random seeds, and validation metrics. The current repository has some ingredients, but not the contract.

## Scientific Semantics

The intended system is packet-based, mesoscopic, dynamic, and cybernetic. Current active code is mostly static, route-based, and edge-cost oriented.

Current active semantic primitives:

- `TripRequest`: a routing request with origin/destination nodes and departure minute.
- `NamedGraphPoint`: a snapped named coordinate.
- `TntpLink`: static link with capacity, free-flow time, and BPR parameters.
- `SnapshotBuffer`: time-indexed dictionary of edge-cost fields from a live graph.
- `NetworkX graph edge attributes`: free-flow time, current travel time, marginal cost, simulated volume, live occupancy, peak state.

Missing canonical primitives:

- Packet identity, class, departure event, lifecycle phase, and ownership.
- Link cumulative counts: `N_up(t)`, `N_down(t)`, sending/receiving functions, queue state, and FIFO constraints.
- Node transfer model with merge/diverge allocation and capacity rules.
- Authority-visible observations distinct from physical truth.
- Information delay, sampling, noise, aggregation, and disclosure policy as first-class concepts.
- Behavioural adaptation/churn state.
- Governance/control interventions and infrastructure-mediated actuation.

The current primitives are not wrong for provenance, but they should not become the canonical ontology. The most important architectural move is to write down canonical truth ownership before adding dynamic simulation code.

## Observability Readiness

`observability/snapshot_buffer.py` is one of the most useful migrated ideas. It separates delayed authority-visible information from current live state and explicitly represents snapshots. This aligns with asymmetric-information routing authorities.

The risk is that the snapshot content is a legacy cost surface. It captures `penalised_travel_time_seconds`, `penalised_marginal_cost_seconds`, `live_occupancy_count`, and `simulated_volume` from graph edge dictionaries. In a packet-LTM design, authority-visible state should be a view over cumulative counts, predicted link exit times, queue length estimates, incident/control state, and measurement uncertainty. Cost surfaces may be derived from that view, but should not be the root observable.

Recommended reframing:

- Keep the idea of a rolling delayed buffer.
- Rename/generalize from `EdgeCostSnapshot` to an `ObservationFrame` or equivalent.
- Make the input a state-view protocol rather than a raw graph.
- Include snapshot metadata: source, sampling interval, delay model, aggregation window, noise/rounding policy, and units.

## Benchmark Readiness

Sioux Falls TNTP parsing is foundational for benchmark data handling. The parser is clean and small. It validates expected link count and total OD flow, assigns stable edge IDs, and produces immutable dataclasses. This is reusable.

The Sioux Falls loader is more provisional. It constructs a NetworkX graph with BPR attributes and describes the benchmark as ready for "future assignment code". That is acceptable if the benchmark package is explicitly split into:

- `benchmarks.tntp`: neutral TNTP data parsing.
- `benchmarks.static_reference`: BPR/static-assignment reference adapters.
- `benchmarks.dynamic`: future synthetic packet-LTM benchmarks.

The BPR attributes should not leak from static reference benchmarks into the canonical dynamic topology model.

## Test Philosophy

The active `tests` tree contains no test source files at audit time, only `__pycache__`. Archived tests exist under `legacy/archived tests`, but they target the old static assignment ontology. `python -m pytest -q` could not run because `pytest` is not installed in the current environment, and even if installed, the active test path would collect no current tests.

This means the repository is not currently testing future ontology. It is also not actively preserving legacy benchmark behavior in a runnable way. The test posture is therefore weaker than the directory layout suggests.

The next tests should be synthetic, small, ontology-first, and independent of Cork geospatial dependencies. Recommended initial invariant tests:

1. Manifest schema invariants: every manifest has stable ID, version, declared trip count, uniform origin/destination key names, departure units, seed/provenance fields, and no missing required fields.
2. Packet lifecycle identity: a packet can be created from demand once; packet ID remains stable; lifecycle transitions are monotone; no packet is duplicated or destroyed without terminal accounting.
3. Link conservation on a single-link network: cumulative exits never exceed cumulative entries; final exits equal entries after sufficient time.
4. FIFO preservation on one link: two packets entering the same homogeneous link exit in entry order.
5. Receiving constraint on a two-link chain: downstream capacity limits upstream exits without violating conservation.
6. Node transfer correctness at a merge: allocated receiving capacity never exceeds downstream receiving function; incoming queues remain conserved.
7. Node transfer correctness at a diverge: turning proportions or packet route intents conserve packet counts across outgoing links.
8. Delayed observability: an authority querying delay `d` receives the correct earlier observation frame and not live truth.
9. Observation isolation: mutating physical state after a snapshot does not mutate the stored snapshot.
10. Benchmark quarantine: importing canonical packet/loading packages does not import BPR/static-assignment reference modules.

These tests should precede simulator implementation because they define the ontology guardrails.

## Dependency And Environment Readiness

`pyproject.toml` declares Python `>=3.13`, `setuptools`, pytest config, and source package discovery. It does not declare runtime dependencies such as `networkx`, `numpy`, `osmnx`, `pandas`, `geopandas`, `scipy`, `shapely`, `pyproj`, or `folium`, even though source and scripts require them.

This is not reproducible enough for scientific computing. The repository needs either:

- explicit project dependencies and optional extras, or
- environment lock files plus documented setup commands.

Suggested extras:

- `core`: lightweight dynamic model dependencies, preferably standard library plus `numpy`.
- `graph`: `networkx`, OSM/geometry dependencies.
- `geo`: `osmnx`, `geopandas`, `shapely`, `pyproj`, `folium`.
- `benchmarks`: `networkx`, `numpy`.
- `dev`: `pytest`, formatting/linting, type checking.

The future packet-LTM core should avoid depending on OSMnx/geopandas. Those should remain adapter-layer dependencies.

## Reproducibility Surfaces

Positive signs:

- Manifest files are committed rather than generated at runtime.
- Several manifest files include `generation_seed`.
- OD summary and zone index artifacts are committed.
- Sioux Falls data is committed as benchmark input.
- Count data is committed in simple CSV form.

Weaknesses:

- No artifact contract is populated in docs.
- No schema validation exists for manifests.
- No input hashes or code-version fields exist in committed manifests.
- No run output convention exists under `experiments`.
- Data provenance is partly embedded in comments inside scripts rather than in machine-readable metadata.
- The current package cannot import several active modules.
- `pyproject.toml` does not declare dependencies.

## Architectural Pressure Points

1. State ownership: `network/graph_pipeline.py` currently treats NetworkX edge dictionaries as mutable simulation state. Packet-LTM should instead keep topology immutable and dynamic state in the loading engine.
2. Cost ontology: route choice defaults to scalar edge costs (`travel_time_seconds`). Future cybernetic routing may consume delayed observations, predictions, reliability, governance signals, or information policies.
3. Demand ontology: `TripRequest` is close to a route request, not a packet demand event. It lacks packet class, value-of-time, authority assignment, behavioural cohort, route intent, and departure-time units beyond minutes.
4. Observability ontology: `SnapshotBuffer` captures cost fields rather than physical cumulative-flow measurements or authority observation frames.
5. Benchmark quarantine: BPR fields in active `benchmarks` are useful but should not define canonical link state.
6. Documentation vacuum: empty ontology/specification files make future drift likely.
7. Dependency drift: scripts rely on heavy geospatial dependencies outside declared project requirements.
8. Test absence: no active invariant tests protect the intended architecture.

## Readiness Classification

Current maturity: early research scaffold, not yet a serious scientific framework.

It is above a toy prototype because it has real data, benchmark artifacts, a package namespace, and correct future subsystem names. It is below a serious framework because semantics are undocumented, imports are broken, tests are inactive, dependencies are undeclared, and active code still centers scalar edge costs and mutable graph state.

The repository can become scientifically scalable if the next pass focuses on ontology contracts before simulation. The correct next move is not a packet-LTM implementation; it is a small set of canonical interfaces, invariant tests, and documentation that determine where truth lives.

