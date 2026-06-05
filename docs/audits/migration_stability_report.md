# Migration Stability Report

Audit date: 2026-05-28

Scope: assessment of whether the selective migration from the legacy Cork assignment codebase produced a coherent, migration-clean base for future packet-LTM cybernetic development.

## Executive Assessment

The migration was partially successful. It successfully avoided placing the full old BPR/static assignment lifecycle in the active core and it introduced a future-facing package layout. It also retained valuable provenance data, manifests, Sioux Falls inputs, and Cork demand artifacts. However, it is not yet migration-stable: active imports are broken, active tests are absent, documentation files are empty, dependencies are undeclared, and several active modules still encode legacy edge-cost and mutable-graph semantics.

The repository is ready for an architecture-hardening pass. It is not ready for substantive simulator implementation.

## What Improved

The migration created several useful separations:

- Static assignment code now lives under `legacy/bpr_reference`, which is the right quarantine direction.
- Archived tests are not under active `tests`, reducing risk that old behavior becomes the default acceptance suite.
- TNTP parsing was moved into `src/urban_cybernetics/benchmarks`, where benchmark data can be handled separately from Cork-specific scripts.
- Observability exists as a named package rather than being buried inside routing or simulation code.
- Empty packages for `loading`, `nodes`, `routing`, `governance`, `behaviour`, `validation`, and `provenance` reserve appropriate subsystem boundaries.
- Scenario manifests are committed as data artifacts rather than generated implicitly at runtime.

These are real gains. They show that the migration intent was not "copy the old app"; it was to preserve data and reference machinery while opening space for a new framework.

## What Is Not Stable

### Broken Active Imports

Several active modules cannot import:

- `urban_cybernetics.benchmarks.sioux_falls` imports missing `urban_cybernetics.config`.
- `urban_cybernetics.network.graph_pipeline` imports missing `urban_cybernetics.network.config`.
- `urban_cybernetics.packets.demand` imports missing `urban_cybernetics.packets.config` and missing `urban_cybernetics.packets.graph_pipeline`.
- `urban_cybernetics.packets.scenario_manifest` imports missing `urban_cybernetics.packets.config`.

This is a migration integrity issue, not a modeling issue. Before any scientific development, the repository needs a stable import baseline.

### Active Tests Are Gone

`tests` contains cache artifacts but no active test source. `legacy/archived tests` contains useful historical tests, but they point to modules no longer present in the active package. `pytest` was also not installed in the current environment, so test execution could not verify even an empty collection.

This means there is no current executable contract for migration stability.

### Documentation Skeleton Is Empty

The following intended documents existed but had zero lines:

- `docs/architecture/core_principles.md`
- `docs/architecture/system_ontology.md`
- `docs/specifications/packet_semantics.md`
- `docs/specifications/timestep_semantics.md`
- `docs/specifications/invariants.md`
- `docs/specifications/observability_model.md`
- `docs/specifications/artifact_contracts.md`
- `docs/specifications/node_model_assumptions.md`
- `docs/specifications/routing_authorities.md`
- `docs/benchmarks/benchmark_policy.md`
- `docs/benchmarks/legacy_bpr_role.md`
- `docs/migration/legacy_repository_migration_report.md`

This is the largest migration-stability gap. The repository has reserved the right documentation surfaces, but no written contract prevents semantic drift.

### Dependency Metadata Is Incomplete

`pyproject.toml` declares package metadata and Python `>=3.13`, but no runtime or development dependencies. Current code and scripts require packages including `networkx`, `numpy`, `osmnx`, `pandas`, `geopandas`, `scipy`, `shapely`, `pyproj`, `folium`, and `pytest`.

Scientific reproducibility requires dependency declarations or environment locks. At present, new contributors cannot recreate the audit environment from repository metadata alone.

### Generated And Local Artifacts Are Mixed Into Source Tree

The tree includes `.DS_Store`, `__pycache__`, and `.egg-info` artifacts. Some were present at audit start; additional cache artifacts may appear when compiling or importing. These should be excluded by `.gitignore` before the first commit. The current git state has no commits and all files are untracked, so the first commit is an opportunity to keep generated artifacts out of history.

## File Classification

### Foundational

`src/urban_cybernetics/benchmarks/tntp_parser.py`

Reason: clean parser for benchmark input files with immutable dataclasses, stable edge IDs, metadata validation, and no dependency on the old assignment solver. It is reusable for benchmark ingestion.

`data/benchmarks/sioux_falls/SiouxFalls_net.tntp` and `data/benchmarks/sioux_falls/SiouxFalls_trips.tntp`

Reason: standard benchmark inputs. They are appropriate committed data for comparative reference, provided BPR semantics are documented as benchmark-specific.

`data/counts/cordon_counts_2024.csv`

Reason: useful observed-count input. Needs provenance metadata, but the CSV itself is a reasonable validation artifact.

`pyproject.toml`

Reason: basic package scaffold. Needs dependency expansion.

### Provisional

`src/urban_cybernetics/benchmarks/sioux_falls.py`

Reason: useful loader, but currently imports missing config and attaches BPR fields directly to a NetworkX graph. Keep, but split neutral benchmark loading from static-reference attributes.

`src/urban_cybernetics/packets/demand.py`

Reason: useful demand input dataclasses and snapping helpers, but package name overpromises packet semantics. Imports are broken. Treat as demand input, not packet lifecycle.

`src/urban_cybernetics/packets/scenario_manifest.py`

Reason: the load-only manifest principle is good. Broken config import and "selfish" policy naming need correction.

`src/urban_cybernetics/observability/snapshot_buffer.py`

Reason: delayed snapshot idea is architecturally valuable, but content is a legacy edge-cost surface pulled from live graph state. Generalize before treating as canonical observability.

`data/manifests/*.json`

Reason: valuable committed scenario inputs. Need formal schema, provenance fields, and consistent naming/units before becoming canonical experiment inputs.

`data/manifests/od_matrix.npy`, `data/manifests/od_zone_index.csv`, `data/manifests/od_summary.csv`

Reason: useful demand artifacts. Need generator provenance and schema.

### Legacy Reference

`legacy/bpr_reference/network_costs.py`

Reason: minimal BPR helper functions. Correctly belongs outside active dynamic ontology.

`legacy/bpr_reference/static_assignment.py`

Reason: static UE/SO/CSO assignment solver. Valuable for provenance and historical comparison, not for packet-LTM implementation.

`legacy/archived tests/*.py`

Reason: historical acceptance tests for static assignment. Useful only if restored under a clearly named legacy-reference test suite.

### Quarantined

All BPR/static assignment material should remain quarantined until a benchmark policy defines how legacy reference outputs are compared to dynamic packet-LTM outputs. The quarantine boundary should prohibit imports from `legacy` into canonical model packages.

### Risky

`src/urban_cybernetics/network/graph_pipeline.py`

Reason: large active module with mutable graph state, BPR language, route helpers, map rendering, OSMnx IO, and old demo artifacts. It is useful as provenance/adapter code but risky as core architecture.

`scripts/02_build_od_matrix.py`

Reason: combines demand estimation, calibration, geospatial processing, graph snapping, random sampling, and manifest writing in one script. Emits schema fields that do not match active `TripRequest`. Contains vehicle/person/occupancy ambiguity.

`scripts/05_calibrate_validate.py`

Reason: useful validation intention, but assumes edge-volume exports without cumulative-flow semantics and relies on paths not aligned with current committed data.

Empty docs under `docs/architecture`, `docs/specifications`, `docs/benchmarks`, and `docs/migration`

Reason: not risky because of content, but risky because their absence allows code to become the ontology by accident.

## Migration Cleanliness

Clean aspects:

- Legacy solver not copied into active package.
- Static assignment tests not active by default.
- Data and source are separated.
- Future subsystem names are present.
- Several docs filenames express the right conceptual concerns.

Unclean aspects:

- Active code imports missing migrated `config` modules.
- Active source comments and attributes still speak BPR and mutable edge-state language.
- Cached/generated files are present in source/data/test directories.
- Existing tests are only archived and stale.
- The empty docs create a mismatch between intended architecture and implemented semantics.

## Stability Gate Before Simulator Development

Before implementing packet-LTM logic, the repository should pass these gates:

1. Import baseline: all active `src/urban_cybernetics` modules either import cleanly or are explicitly moved/quarantined.
2. Dependency baseline: `pyproject.toml` declares runtime/dev extras sufficient to run tests.
3. Documentation baseline: core ontology, packet semantics, observability model, artifact contracts, and legacy BPR role are populated.
4. Test baseline: at least 5 ontology/invariant tests exist and run without geospatial dependencies.
5. Data baseline: manifest schema validation covers committed JSON manifests.
6. Quarantine baseline: canonical packages cannot import BPR/static-assignment reference code.
7. Git hygiene baseline: generated artifacts are ignored before first commit.

## Migration Verdict

The migration clarified intent but did not yet produce a stable scientific substrate.

Future development can proceed cleanly only after a short hardening phase. That phase should not be large or feature-heavy. It should establish import hygiene, documentation, invariant tests, and state-ownership contracts. After that, packet-LTM implementation can proceed without being pulled back into the old BPR assignment lifecycle.

