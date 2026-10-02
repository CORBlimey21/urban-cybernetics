# Urban Cybernetics

Urban Cybernetics is a research framework for packet-based traffic simulation,
with explicit loading rules, network provenance, observations, routing
information, and deterministic replay evidence.

Urban Cybernetics **1.0.0** is the archival research-software release
accompanying the Urban Cybernetics paper.
It preserves the current scientific implementation: analytical and digitised
reference comparisons, junction representation and fractional-service
experiments, OSM compiler cases, synthetic demand scaling, and bounded
information/routing composition experiments.

## Setup

Use **CPython 3.13** (the paper evidence used 3.13.3). Package metadata permits
Python >=3.13; later versions and other platforms are not certified by the paper
freeze. Core dependencies are NetworkX and NumPy. Run from a source checkout:

```bash
git clone https://github.com/CORBlimey21/urban-cybernetics.git
cd urban-cybernetics
python3.13 -m venv .venv
.venv/bin/python -m pip install -c constraints-release.txt -e '.[dev,visualisation,publication]'
```

`visualisation` is required for the full Python test suite, including API tests;
it is optional for the core simulator. `constraints-release.txt` records the
observed Python core/test/workbench environment, including transitive versions.
It is a version constraint set, not a hash-locked or cross-platform environment.
The optional `geo` extra supports geographic data preparation and is not needed
for committed compact OSM cases or the pinned Cork GraphML adapter; it is not
covered by these constraints. It is also not required by any paper experiment:
compact OSM compiler cases use the standard library and the pinned GraphML
adapter uses NetworkX. The `publication` extra supplies the constrained Pillow
version used for comparison plots. Exporters default to Pillow's embedded
Aileron font on every platform.

Keep the checkout: publication scripts, data, and fixtures live outside the
Python package and are not bundled in its wheel.

## Tests and smoke run

A fresh clone runs the ordinary suite without private machine state. Tests
requiring the separately acquired Cork GraphML, Sioux Falls/Anaheim TNTP files,
or digitised de Souza reference CSVs are explicit external-input skips; UC-only
and synthetic tests still execute. The historical kernel verifier additionally
requires ten separately supplied de Souza CSVs and full Git history. It reports
unavailable inputs in the public release tree; see [REPRODUCIBILITY.md](REPRODUCIBILITY.md).
The [public-history provenance note](docs/provenance/PUBLIC_HISTORY_PROVENANCE.md)
explains the sanitised history, historical commit mapping and public verifier adapter.

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/verify_paper1_evidence.py
```

To enable the six Cork tests and Cork experiments, obtain the exact dataset
published at DOI
[10.5281/zenodo.22981344](https://doi.org/10.5281/zenodo.22981344).
[The provenance record](docs/paper1/CORK_GRAPHML_PROVENANCE.md) specifies the
filename, size and checksum. Verify and install it at the ignored default path
`external/pinned/cork_full_drive.graphml`:

```bash
.venv/bin/python scripts/install_external_data.py \
  --cork-graphml /path/to/cork_full_drive.graphml
.venv/bin/python -m pytest -q tests/test_cork_city_scale.py \
  tests/test_cork_fixed_horizon.py
```

The raw [Sioux Falls](data/benchmarks/sioux_falls/README.md) and
[Anaheim](data/benchmarks/anaheim/README.md) TNTP files are deliberately not
redistributed. Those READMEs give upstream acquisition, filenames and historical
checksums. Digitised de Souza reference CSVs are also absent; see
[THIRD_PARTY.md](THIRD_PARTY.md) for their source and identity. Publication
comparisons requiring them are unavailable until independently supplied inputs
matching the recorded checksums are installed.

A small analytical simulation, requiring no external data:

```bash
.venv/bin/python -c 'from urban_cybernetics.canonical_validation import analytical_validation_results; results = analytical_validation_results(); print([(r.scenario_id, r.is_pass) for r in results]); assert all(r.is_pass for r in results)'
```

## Publication reproduction

Start with [REPRODUCIBILITY.md](REPRODUCIBILITY.md), which maps result families
to commands and identifies release gaps. The detailed
[paper evidence guide](docs/paper1/REPRODUCIBILITY.md) records expected hashes;
[the evidence manifest](docs/paper1/evidence_manifest_v1.json) inventories
tracked evidence, retained ignored outputs, and external pinned sources. The
[archive recommendation](docs/paper1/EVIDENCE_ARCHIVE_MANIFEST.md) classifies
all 18 ignored evidence files.

## Code and data availability

The source repository is [Urban Cybernetics on GitHub](https://github.com/CORBlimey21/urban-cybernetics).
Software version: **1.0.0**. Release date: **2026-10-02**.
The following supporting records were published on 2026-10-02 and are publicly
available; their DOIs identify data and evidence, not the software:

- Cork GraphML dataset: [10.5281/zenodo.22981344](https://doi.org/10.5281/zenodo.22981344),
  `cork_full_drive.graphml`, under ODbL-1.0, © OpenStreetMap contributors.
- Paper 1 publication evidence, archive version 1.0.0:
  [10.5281/zenodo.23000309](https://doi.org/10.5281/zenodo.23000309).
  Project-generated evidence is CC BY 4.0 unless otherwise stated. Embedded
  OpenStreetMap-derived database portions remain subject to ODbL 1.0;
  CC BY does not override those rights. Third-party source material not licensed
  for redistribution is excluded from the evidence bundle.

See [the evidence archive manifest](docs/paper1/EVIDENCE_ARCHIVE_MANIFEST.md)
for the precise scope and licence mapping. Verify downloaded inputs and evidence
against their recorded checksums.

Runners are in `scripts/`; experiment implementations are in
`src/urban_cybernetics/experiments/`; validation cases are in `tests/` and
`fixtures/visualisation/validation/`. Architecture and claim boundaries are in
`docs/architecture/` and `docs/paper1/`.

Cork demand and physical parameters are synthetic/uncalibrated. Digitised
comparisons are observational comparisons, not independent empirical
calibration. Replay checks and skipped replay policies are distinct. Timing and
memory measurements depend on the machine. Information/routing composition is
a bounded synthetic demonstration, not evidence of real-network policy benefits.
Some archived result chains require external sources or ignored files that a
fresh clone does not contain; see the reproduction gaps before making claims.

## Optional local workbench

Release audit: non-breaking lockfile updates resolved all high-severity npm
advisories. One Vitest issue remains as two moderate audit entries and requires
a major test-tool upgrade; its disposition is recorded in the release checklist.

The browser replay workbench uses a FastAPI adapter and the locked npm dependency
tree. Use Node.js 22.12+ (Vite 7 also supports Node 20.19+):

```bash
cd web
npm ci
npm test
npm run build
cd ..
.venv/bin/uc-visualisation serve
```

Open <http://127.0.0.1:8000>. The workbench persists local runs in ignored
`outputs/visualisation/runs/`. See
[the workbench guide](docs/visualisation/v2_workbench_architecture.md).

## Citation and licence

[CITATION.cff](CITATION.cff) records the software author, supplied ORCID and
related published data/evidence DOIs, version 1.0.0 and release date 2026-10-02.
No software DOI or paper DOI is asserted. The software licence does not replace
scholarly citation.

Project-authored Urban Cybernetics software is licensed under the
[Mozilla Public License 2.0](LICENSE) (`MPL-2.0`). This licence does not
relicense bundled or associated third-party material. OSM-derived data remains
subject to ODbL notices. TNTP and digitised de Souza inputs are not redistributed;
their source terms and reproduction gaps are documented separately. See
[THIRD_PARTY.md](THIRD_PARTY.md) and [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).
