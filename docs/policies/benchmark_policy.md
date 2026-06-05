**Status:** policy document.
**Scope:** defines the taxonomy of benchmarks used in the framework, what each type of benchmark establishes scientifically, and what artifact requirements apply to each.
**Non-scope:** does not define packet-LTM mechanics, routing algorithms, or data collection methods.

---

### Benchmark Taxonomy

The framework uses four categories of benchmark. They are not interchangeable. Passing a benchmark from one category does not imply anything about another category.

---

### Category 1: Synthetic Invariant Tests

**What they establish.** That the implementation satisfies the framework's conservation, FIFO, observability, and quarantine invariants on minimal synthetic networks.

**Scientific status.** Necessary condition for any result produced by the implementation to be trusted. A failure here invalidates all other results.

**Artifact requirements.** Synthetic network definition (inline, no external files), demand manifest (inline), seed registry, code version, pass/fail result, and invariant reference (I1 through I15 as defined in invariants.md).

**These are tests, not experiments.** Their purpose is to verify that the implementation is correct, not to generate scientific findings.

**Benchmark list.** I1 through I15 from invariants.md.

---

### Category 2: Sioux Falls Static Reference

**What they establish.** That the benchmark tooling (TNTP parser, static assignment solver) loads the Sioux Falls network correctly and produces assignment results consistent with published values in the static assignment literature.

**Scientific status.** Smoke test. Confirms plumbing. Does not validate any property of the dynamic model.

**Artifact requirements.** Sioux Falls TNTP input files with provenance (source URL, download date), static assignment run configuration, output link flow vector with bpr_ref_ prefix, comparison against published reference values, and a validity statement declaring that this benchmark tests only static assignment tooling.

**These must not be cited as validation of packet-LTM dynamics.** A passing Sioux Falls reference run says nothing about whether cumulative counts, queue propagation, or delayed observability are correctly implemented.

---

### Category 3: Cork Demand Scenarios

**What they establish.** That the dynamic model produces plausible outputs under realistic Cork demand and topology, as judged by comparison with cordon count observations and by internal consistency.

**Scientific status.** Calibration evidence. Establishes that the model is in a reasonable empirical range. Does not establish that the model's dynamic mechanisms (churn, asymmetric information, queue propagation) are correctly specified.

**Artifact requirements.** Cork topology artifact with topology_hash, demand manifest with manifest_hash, cordon count reference data with provenance (collection date, collection method, spatial scope), GEH or RMSE statistics against count data with full derivation documentation, a validity statement declaring the comparison scope (aggregate link flows over a declared time window, not packet-level dynamics), and a declaration that BPR comparison outputs are stored separately under outputs/legacy_reference/.

**GEH is a calibration metric, not a dynamic model validator.** A good GEH score means the model's aggregate outputs are in the right ballpark. It does not mean the queue dynamics, information asymmetry, or churn mechanics are correct.

---

### Category 4: Asymmetric Information Experiments

**What they establish.** Scientific findings about how competing routing authorities interact under asymmetric information, how behavioural churn affects authority market share, and how infrastructure-mediated control shapes equilibrium outcomes.

**Scientific status.** Primary scientific evidence for the framework's research claims.

**Artifact requirements.** Full run bundle (topology_hash, manifest_hash, config_snapshot, seed_registry, code_version), complete raw event logs, observation frame archive, routing decision log, governance intervention log, all derived summaries with derivation documentation, a stated hypothesis, a declared comparison (experimental vs control run with documented difference), a validity statement, and a limitations statement.

**These results must only be reported after Category 1 invariant tests pass.** An asymmetric information experiment run on an implementation that fails I4 (single-link conservation) is not a scientific result.

---

### Oracle Baseline Policy

If an oracle routing authority (with access to physical truth rather than observation frames) is included in an experiment, the following requirements apply:

The oracle's outputs must be reported in a separate section of the experiment artifact, labelled as theoretical upper bound. Oracle outputs must not be averaged with or used to calibrate empirical authority outputs. The validity statement must declare that oracle results represent a bound achievable only with perfect instantaneous information and are not achievable by any real routing system.

---

### Smoke Test vs Scientific Evidence

A result is a smoke test if it establishes only that the tooling runs and produces output in an expected format and range. A result is scientific evidence if it tests a stated hypothesis about the model's dynamics using a declared comparison with declared validity conditions.

Smoke tests are useful and necessary. They are not scientific evidence and must not be labelled as such.
