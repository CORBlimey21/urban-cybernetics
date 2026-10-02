# Reproducibility for the 1.0.0 release

Run from the repository root using the README environment. This index supplements
[the paper guide](docs/paper1/REPRODUCIBILITY.md) and its
[evidence manifest](docs/paper1/evidence_manifest_v1.json); it does not replace
frozen identities. Software 1.0.0 and loading-kernel-v1.0.1 are different version
namespaces. The manifest's software 0.1.0 is historical capture metadata.

Project-authored software is licensed under [MPL-2.0](LICENSE). Data, external
references and frozen evidence retain the scope and terms in
[THIRD_PARTY.md](THIRD_PARTY.md); citation guidance is unchanged.

The public release omits five raw TNTP benchmark files and twelve digitised
de Souza reference CSVs whose redistribution rights have not been established.
The ordinary test suite skips only cases requiring absent inputs. Obtain TNTP
files directly from [Sioux Falls](data/benchmarks/sioux_falls/README.md) or
[Anaheim](data/benchmarks/anaheim/README.md) upstream using the exact filenames
and checksums there. De Souza comparisons require separately sourced reference
CSV inputs under their source terms; see THIRD_PARTY.md. No public acquisition
package for the historical digitisation has been identified.

Published supporting records (2026-10-02):

- Cork GraphML: [10.5281/zenodo.22981344](https://doi.org/10.5281/zenodo.22981344),
  ODbL-1.0, © OpenStreetMap contributors.
- Paper 1 evidence archive version 1.0.0:
  [10.5281/zenodo.23000309](https://doi.org/10.5281/zenodo.23000309).
  Project-generated evidence is CC BY 4.0 unless otherwise stated; embedded
  OpenStreetMap-derived database portions remain ODbL 1.0. Third-party source
  material not licensed for redistribution is excluded from this bundle.

These public supporting records are separate from the software release; their
DOIs identify data and evidence, not the software.

## Small checks and result map

Commands below execute existing cases. Tests establish only their asserted
scope; they do not regenerate every historical report or certify every paper
claim. Run exporters in a disposable full-history clone: some overwrite tracked
JSON/CSV evidence. Use `publication` dependencies. Figure 5/7/8 PNG exporters
use Pillow's embedded Aileron font by default. Set `UC_PUBLICATION_ARIAL_DIR` to
a directory containing `Arial.ttf` and `Arial Bold.ttf` only when reproducing
the typography of archived macOS PNGs. Font choice does not alter numerical
CSV/JSON evidence.

| Result family | Existing command from repository root | Evidence/configuration and boundary |
| --- | --- | --- |
| Canonical analytical loading and lane drop | `.venv/bin/python -m pytest -q tests/canonical_validation/test_analytical_ltm.py tests/external_validation/test_m8_analytical_link_cases.py tests/visualisation/test_desouza_receiving_credit_regression.py` | Analytical cases plus `M8-PUB-DSOUZA-FIG5-DT1`; dt=1 receiving-credit regression. Figure 5 UC fixture remains tracked; digitised reference inputs are separate. See lane-drop caveat below. |
| Deterministic diverge | `.venv/bin/python -m pytest -q tests/external_validation/test_m8_desouza_figure7.py tests/external_validation/test_m8_desouza_figure7_comparison.py` | Figure 7 dt=1/dt=3; `scripts/compare_desouza_figure7a_dt1.py --output /tmp/uc-fig7` consumes retained observables. |
| Stochastic diverge | `.venv/bin/python -m pytest -q tests/external_validation/test_m8_desouza_figure8.py` | Figure 8, 100 replications in `scripts/run_desouza_figure8_ensemble.py`; seeds/configuration live in `canonical_validation/desouza_figure8.py`. Export command below. |
| Equal/asymmetric merge | `.venv/bin/python -m pytest -q tests/external_validation/test_m8_desouza_figure9_equal.py tests/external_validation/test_m8_desouza_figure9_asymmetric.py` | `scripts/run_desouza_figure9_equal.py` and `scripts/run_desouza_figure9_asymmetric.py` regenerate dt=1 evidence/comparisons; both overwrite tracked `data/validation/` files and ignored plots. |
| Junction representation | `.venv/bin/python -m pytest -q tests/test_osm_junction_experiment.py tests/test_lane_group_extension.py tests/test_boreenmanna_integrity_audit.py` | Compact Boreenmanna OSM, 12-case matrix; exact regeneration and hashes are in the paper guide. `scripts/run_lane_group_ablation.py --output /tmp/uc-lane-group.json` regenerates the separate ablation. |
| Fractional service/gates | `.venv/bin/python -m pytest -q tests/test_fractional_service_credit.py tests/test_gate_aware_fractional_service.py tests/test_discharge_readiness_fractional_service.py tests/test_boreenmanna_gate_aware_v2.py tests/test_boreenmanna_discharge_readiness_v3.py` | Analytical offset/gate cases and compact integrations for v1/v2/v3. Complete historical packages require parent evidence, as described below. |
| Cork provenance/compiler | `.venv/bin/python -m pytest -q tests/test_network_compiler.py tests/test_osm_junction_ingestion.py tests/test_maryville_real_junction.py` | Tracked compact Boreenmanna/Maryville XML. Paper guide includes Maryville writer and expected hash. Source-strict refusals and reviewed/synthetic execution remain distinct. |
| Sioux Falls scaling | `.venv/bin/python scripts/profile_sioux_falls_scale_ladder.py --packets 24 --tick-limit 20000 --timeout-seconds 180 --exact-replay-packet-limit 10000 --output-json /tmp/uc-sioux-smoke.json --output-markdown /tmp/uc-sioux-smoke.md` | Lightweight entry-point check only, after installing the exact TNTP network and trips files. Published ladder configuration below; raw TNTP inputs are omitted. |
| Cork city scale | `.venv/bin/python scripts/run_cork_fixed_horizon.py --graphml /absolute/path/to/cork_full_drive.graphml --single-rung 100 --single-output /tmp/uc-cork-100.json --force-replay` | External source required. 15,000 ticks/600 seconds. The paper guide gives the 100–10,000 packet ladder and expected identities. Not a routine smoke test. |
| Cybernetic composition | `.venv/bin/python -m pytest -q tests/test_first_asymmetric_information_experiment.py tests/test_authority_visible_state.py tests/test_observation_channel_expansion.py tests/test_repeated_authority_experiment.py tests/test_receipt_delay_sensitivity_sweep.py` | Bounded synthetic information/routing separation; `experiments/r1a.py` and `r1b.py` implement repeated decisions and receipt-delay sweep. No standalone frozen paper result table is indexed in the evidence manifest. Confirm which case supports the final manuscript. |

For Figure 8, redirect all outputs (not just plots):

```bash
mkdir -p /tmp/uc-fig8
.venv/bin/python scripts/run_desouza_figure8_ensemble.py \
  --summary /tmp/uc-fig8/summary.json \
  --pointwise /tmp/uc-fig8/pointwise.csv \
  --replications /tmp/uc-fig8/replications.csv \
  --output /tmp/uc-fig8/plots
```

The recorded high-packet Sioux Falls runner is
`scripts/profile_sioux_falls_scale_ladder.py`, not the older scale-ladder wrapper.
The exact configuration in
`docs/validation/sioux_falls_post_option_c_scale_ladder_profile.json` is:

```bash
# Expensive: explicit reproduction only, not ordinary release checks.
.venv/bin/python scripts/profile_sioux_falls_scale_ladder.py \
  --packets 10000 25000 50000 100000 200000 360600 \
  --tick-limit 20000 --timeout-seconds 600 --exact-replay-packet-limit 10000 \
  --output-json /tmp/uc-sioux-paper.json \
  --output-markdown /tmp/uc-sioux-paper.md
```

The 360,600-packet rung stopped at the runtime guard; it is not a completed
validation. Exact replay ran at 10,000 only. Timings/RSS are machine-dependent.
Profiling uses Unix facilities (`resource`, process signals); Windows is unverified.

## Release gaps and evidence boundaries

- **External Cork source:** `cork_full_drive.graphml` is absent from Git and
  matched by `*.graphml` in `.gitignore`. A new OSM download is not equivalent.
  Six tests skip explicitly when the file is absent. Obtain the exact
  8,346,799-byte source with SHA-256
  `cc904d3c9107136fdf6fd24318c19c38958b63dc81c83441e8e5f855f41f5409`
  from the published dataset DOI
  [10.5281/zenodo.22981344](https://doi.org/10.5281/zenodo.22981344), then run:

  ```bash
  .venv/bin/python scripts/install_external_data.py \
    --cork-graphml /path/to/cork_full_drive.graphml
  ```

  The installer verifies bytes before copying to
  `external/pinned/cork_full_drive.graphml`. See
  `docs/paper1/CORK_GRAPHML_PROVENANCE.md` for the original OSMnx query and why
  it cannot recreate the historical snapshot. The published dataset supplies
  the pinned file; the installer verifies its identity before installation.
- **Retained evidence:** the manifest names 18 ignored output files. A GitHub
  source archive will not contain them. The version 1.0.0 evidence bundle was
  published on 2026-10-02 at
  [10.5281/zenodo.23000309](https://doi.org/10.5281/zenodo.23000309).
  The verifier's default checks only 10 tracked artifacts; `--include-ignored`
  checks the additional 18, and `--cork-graphml PATH` checks the external source.
  `docs/paper1/EVIDENCE_ARCHIVE_MANIFEST.md` classifies every file in
  this separate Zenodo evidence record. The frozen JSON manifest's historical
  versions and archive fields are retained unchanged; current DOI status is here.
- **Boreenmanna chain:** the compact source reproduces manuscript-facing physical
  event identities, but not the full-source package bytes. The external full OSM
  export and parent packages are required for the preserved integrity/v2/v3 chain.
  `run_boreenmanna_gate_aware_v2_comparison(source_path, parent_v1_audit_path)` and
  `run_boreenmanna_discharge_readiness_v3(source_path, parent_v2_path)` enforce
  matching compilation identity. Do not combine compact input with full-source
  parents. A single clean-clone command rebuilding the complete historical chain
  is not currently documented; compact tests are not a substitute for it.
- **Lane-drop before/after:** `scripts/compare_desouza_figure5a_dt1.py` consumes
  stored UC results; it does not execute the simulator. Its defaults use v1 inflow
  digitisation. The reported Equation (6) before/after results instead use v2
  inflow/outflow inputs and the storage sort convention described in
  `docs/validation/m8_desouza_figure5a_dt1_eq6_before_after_v1.md`. The complete
  before/after JSON/overlays are ignored, and no complete one-command regeneration
  of both historical states is supplied. Do not label the default exporter as
  reproducing that table. Preserve the historical evidence or document both
  revisions/configurations before release.
- **Public history and source archives:** use
  `.venv/bin/python scripts/verify_public_loading_kernel_freeze.py --metadata-only`
  in a full-history public clone. The adapter resolves the frozen manifest's
  original Git commit IDs through the
  [public commit mapping](docs/provenance/public-commit-map.tsv) and reports both
  original and public IDs; artifact checksums remain unchanged. See the
  [public-history provenance note](docs/provenance/PUBLIC_HISTORY_PROVENANCE.md).
  Verification remains unavailable until the ten exact digitised reference CSVs
  omitted from the release are separately installed under their source terms.
  A GitHub/Zenodo source ZIP has no Git history and cannot satisfy this check.
  The checksum-pinned original verifier remains unchanged and uses original
  development-history IDs; it is not the public-clone entry point. The ordinary
  suite skips its historical verifier test when reference inputs are absent.
  `verify_paper1_evidence.py` verifies file hashes without Git history.
- **Environment:** Python versions are constrained for core/tests/workbench and
  Pillow, but build tooling and optional non-paper `geo` dependencies are not
  locked; dependency file hashes and other platforms are not certified. Portable
  PNG regeneration uses Pillow's embedded Aileron. Archived PNGs used macOS Arial
  and may differ typographically; preserve numerical inputs independently.
- **Historical local paths:** the tracked frozen Anaheim profile contains three
  author-home source-path strings. They are historical provenance inside a
  hash-recorded artifact, not runtime dependencies, and are intentionally left
  unchanged. Current scripts, tests, configuration, and release documentation do
  not require those paths.
- **Publication scope:** the reproduction map reflects repository evidence, not
  a new comparison with the final manuscript.

Cork fixed-horizon evidence must not be substituted with the earlier
`scripts/run_cork_city_scale.py` drain/bounded-run experiment. Both use seeded
synthetic demand and uncalibrated engineering profiles, not observed Cork demand
or validated real-world congestion.
