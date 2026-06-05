# Recommended Next Steps

Audit date: 2026-05-28

Priority principle: semantic correctness before implementation speed. The next work should make the repository harder to misunderstand.

## Highest-Value Architectural Moves

1. Write the canonical ontology before writing the simulator.

Populate `docs/architecture/system_ontology.md` with the definitions of topology, packet, demand event, link state, node state, observation, authority, route intent, governance intervention, benchmark, experiment, and artifact. The key decision: static topology is not mutable truth; packet-LTM loading state owns physical dynamics.

2. Establish state ownership interfaces.

Create small, implementation-light contracts or docs for:

- immutable topology/link metadata,
- demand declarations,
- packet lifecycle state,
- loading-engine physical truth,
- authority-visible observation frames,
- routing decisions,
- governance/control actions.

Do not implement LTM mechanics yet. Define where each kind of truth will live.

3. Quarantine legacy BPR explicitly.

Populate `docs/benchmarks/legacy_bpr_role.md`. State that BPR/static assignment is provenance and benchmark reference only. Add a test that canonical packages do not import `legacy` or static BPR modules.

4. Fix migration import hygiene.

Resolve missing `config` imports and wrong relative imports. Prefer a small `urban_cybernetics.config` or `urban_cybernetics.paths` module only for repository paths and filenames. Avoid recreating old global simulation config.

5. Separate graph adapters from dynamic state.

Keep OSMnx/NetworkX in `network` as an adapter layer, but do not let `network` own `travel_time_seconds`, `simulated_volume`, or `live_occupancy_count` as canonical fields. Future dynamic state should live under `loading`.

6. Generalize observability.

Preserve delayed buffering, but change the conceptual target from `EdgeCostSnapshot` to an authority observation frame. Cost surfaces can be derived views, not the root physical observation.

7. Formalize artifact contracts.

Populate `docs/specifications/artifact_contracts.md` and add manifest schema validation. Define required fields, units, ID namespaces, seed/provenance fields, topology reference, and trip count.

8. Declare dependencies.

Add runtime and dev dependencies or optional extras to `pyproject.toml`. Keep packet/loading core light; put geospatial dependencies behind optional extras.

9. Clean first-commit hygiene.

Add `.gitignore` for `.DS_Store`, `__pycache__`, `*.pyc`, `.egg-info`, generated outputs, and local caches before the first commit.

10. Make experiments reproducible by construction.

Define `experiments/<run_id>/` contents before running serious experiments: config snapshot, input manifest hash, topology hash, seed registry, code version, metrics, observations, and logs.

## Next Invariant Tests

These tests should be written before packet-LTM implementation. Use tiny synthetic networks and avoid OSMnx/geopandas.

1. Manifest schema invariants

Every committed manifest must declare name, type, version, trip count, required trip fields, departure-time units, generation/provenance fields, and no mixed destination key names.

2. Demand-to-packet instantiation

A demand declaration can instantiate exactly one packet identity per requested trip. Packet IDs are stable and unique.

3. Packet lifecycle monotonicity

A packet cannot exit before entering, cannot occupy two links at once unless explicitly modeled as a transfer phase, and cannot return to an earlier lifecycle state.

4. Single-link conservation

For a one-link network, cumulative exits never exceed cumulative entries, and final exits equal entries after all packets clear.

5. FIFO on a homogeneous link

Two packets entering the same link in order must exit in order under identical class and no passing.

6. Downstream receiving constraint

In a two-link chain, downstream capacity constrains upstream releases without losing packets or creating negative queues.

7. Merge node conservation

At a merge, total transferred packets cannot exceed downstream receiving capacity and all untransferred packets remain queued on incoming links.

8. Diverge node route-intent preservation

At a diverge, packets follow their route intent or documented control override, and packet counts across outgoing links plus residual queue equal incoming count.

9. Delayed observation correctness

Given recorded observation frames at known times, an authority requesting delay `d` receives the expected older frame. Live physical state changes after snapshot do not mutate the stored frame.

10. Benchmark quarantine

Importing canonical dynamic packages must not import `legacy`, `bpr_reference`, `static_assignment`, or BPR cost helpers.

## Documentation Priorities

Populate these files in this order:

1. `docs/architecture/core_principles.md`

Record non-negotiables: cumulative-flow truth, topology immutability, explicit observability, packet conservation, benchmark quarantine, and reproducible artifacts.

2. `docs/architecture/system_ontology.md`

Define core nouns and ownership boundaries. This should be the anti-contamination document.

3. `docs/specifications/packet_semantics.md`

Define packet identity, lifecycle, demand instantiation, route intent, completion, cancellation, and conservation accounting.

4. `docs/specifications/timestep_semantics.md`

Define event ordering, discrete-time assumptions, tie-breaking, update phases, and when observations are sampled relative to physical updates.

5. `docs/specifications/observability_model.md`

Define physical truth, sensor observations, authority-visible frames, delay, aggregation, noise, prediction, and disclosure policy.

6. `docs/specifications/node_model_assumptions.md`

Define node transfer invariants before coding merge/diverge behavior.

7. `docs/specifications/routing_authorities.md`

Define authority types, information sets, routing outputs, compliance expectations, and asymmetric-information assumptions.

8. `docs/specifications/invariants.md`

Turn scientific invariants into testable claims.

9. `docs/specifications/artifact_contracts.md`

Define manifests, run outputs, observation logs, topology artifacts, validation reports, and hashes.

10. `docs/benchmarks/benchmark_policy.md`

Separate synthetic packet-LTM tests, Sioux Falls static reference, Cork demand scenarios, and historical BPR comparisons.

## Implementation Milestones

Milestone 0: Hygiene and contracts

- Add `.gitignore`.
- Fix imports or quarantine modules that cannot import.
- Add dependencies/extras.
- Add schema/invariant test scaffolding.
- Populate core docs.

Milestone 1: Canonical data models

- Define topology records independent of NetworkX.
- Define demand declaration records independent of route policy.
- Define packet identity/lifecycle records.
- Define observation frame records.
- Add serialization contracts and tests.

Milestone 2: Synthetic packet-LTM core

- Implement only a tiny deterministic single-link and two-link synthetic loading core.
- Prove conservation, FIFO, and delayed observability with tests.
- Avoid Cork and OSM dependencies.

Milestone 3: Node transfer models

- Add merge/diverge synthetic tests first.
- Implement node transfer rules with explicit capacity and priority assumptions.
- Keep governance/control hooks separate.

Milestone 4: Routing authority integration

- Implement route decision interfaces against delayed observation frames.
- Support baseline shortest-path only as one authority policy, not as the routing ontology.
- Add asymmetric-information tests.

Milestone 5: Behaviour and churn

- Add behavioural cohorts, compliance/adaptation state, and churn rules.
- Test that adaptation changes decisions without violating packet conservation.

Milestone 6: Cork adapter integration

- Adapt Cork topology and manifests into canonical topology/demand records.
- Validate output definitions against count data using cumulative crossing counts.
- Keep old BPR outputs as historical comparison, not acceptance truth.

## Immediate Do-Not-Do List

- Do not implement a congestion cost refresh loop as the dynamic model.
- Do not store packet-LTM physical truth on NetworkX edge dictionaries.
- Do not let BPR alpha/beta enter canonical link state.
- Do not treat `live_occupancy_count` as flow.
- Do not define validation `volume` without crossing window and boundary semantics.
- Do not make "selfish" a property of demand manifests.
- Do not revive archived static assignment tests as active framework tests without legacy labels.

## Short-Term Success Criteria

The repository is ready for substantive packet-LTM development when:

- all active modules import cleanly,
- at least the first five ontology tests pass,
- core ontology/spec docs are populated,
- dependencies are reproducible,
- generated files are ignored,
- BPR/static assignment is documented and test-quarantined,
- and no canonical dynamic package owns mutable graph edge cost as physical truth.

