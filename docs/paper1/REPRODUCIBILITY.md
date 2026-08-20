# Paper 1 reproduction

Run commands from the repository root with CPython 3.13. The freeze was checked
with Python 3.13.3, NetworkX 3.6.1, NumPy 2.4.6, and pytest 9.0.3. Install the
declared environment with:

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

When reusing a virtual environment whose editable install points at a different
checkout, prefix clean-worktree commands with `PYTHONPATH=src` (or reinstall
the editable package from the clean worktree). This prevents subprocesses from
silently importing the original checkout.

The frozen revision is the local annotated tag `paper1-evidence-freeze-v1`.
Resolve its exact commit with:

```bash
git rev-parse 'paper1-evidence-freeze-v1^{commit}'
```

## Identity and frozen-kernel gates

```bash
.venv/bin/python scripts/verify_loading_kernel_freeze.py
.venv/bin/python scripts/verify_paper1_evidence.py
.venv/bin/python -m pytest -q tests/validation/test_loading_kernel_freeze_manifest.py
```

To also verify the retained ignored files and the external Cork source:

```bash
.venv/bin/python scripts/verify_paper1_evidence.py \
  --include-ignored \
  --cork-graphml /absolute/path/to/cork_full_drive.graphml
```

Expected results are `status: passed`, frozen manifest SHA-256
`3d6a77588bb8e14c48ca6bca7dbc010699d9caf05e409545bfe47be6c0864ef5`,
and Cork source SHA-256
`cc904d3c9107136fdf6fd24318c19c38958b63dc81c83441e8e5f855f41f5409`.

## Compact physical and representation evidence

The focused deterministic gate is:

```bash
.venv/bin/python -m pytest -q \
  tests/validation/test_composed_loading_kernel_case.py \
  tests/test_lane_group_extension.py \
  tests/test_osm_junction_experiment.py \
  tests/test_boreenmanna_integrity_audit.py \
  tests/test_boreenmanna_gate_aware_v2.py \
  tests/test_boreenmanna_discharge_readiness_v3.py
```

Regenerate the clean-checkout Boreenmanna compact compilation and 12-case
representation matrix under a temporary directory:

```bash
PAPER1_REGEN_DIR=$(mktemp -d /tmp/uc-paper1-boreenmanna.XXXXXX)
PAPER1_REGEN_DIR="$PAPER1_REGEN_DIR" .venv/bin/python -c \
'import os; from pathlib import Path; from urban_cybernetics.experiments.boreenmanna import run_boreenmanna_experiment_matrix, write_boreenmanna_experiment_outputs; source=Path("tests/fixtures/osm/boreenmanna_south_link_compact.osm"); compilation, scenarios, matrix=run_boreenmanna_experiment_matrix(source); write_boreenmanna_experiment_outputs(compilation=compilation, scenarios=scenarios, matrix=matrix, output_directory=Path(os.environ["PAPER1_REGEN_DIR"])); print(compilation.package.package_hash); print(matrix.matrix_hash)'
```

Expected compact identities are compilation package
`9511409b044b479c750ea5ca5b58877176a6adbf787b834974c11e03182ac617`
and matrix
`b2f1be3f69ee271cf6b7db2a260207816d49fbbfc7d1f1f2c82ec269e366ebcf`.
The regenerated `boreenmanna_experiment_compilation_v1.json` file SHA-256 is
`18f269b51b2668eec75c0877295f32540207d45d80eb26b98cc9f88ccc7cde9c`.
The preserved ignored full-export chain instead uses package
`c3740a2a658ae613b672fbc446f454ae9a0d98ac6715b2730cdcee925364ce60`
and matrix
`3d493f7306f4a7766393fe41cb83f26d4dd0b83e233456f9ccb50b4f7d61920f`.
That difference is source-inventory identity: all 12 physical event hashes and
outcomes match. Byte-for-byte regeneration of the preserved chain requires the
external 905,366-byte full OSM export named
`Boreenmanna -South Link Junction.osm`, SHA-256
`7b879dea3298adffc4c264bdca3836b5ec62536d8b6450d8602a482f97088d77`.

The published-comparison runners accept output paths, for example:

```bash
.venv/bin/python scripts/compare_desouza_figure7a_dt1.py --output /tmp/uc-fig7
.venv/bin/python scripts/run_desouza_figure8_ensemble.py --output /tmp/uc-fig8
.venv/bin/python scripts/run_desouza_figure9_equal.py
.venv/bin/python scripts/run_desouza_figure9_asymmetric.py
```

These comparisons, their digitised inputs, and expected summary hashes are
recorded in `evidence_manifest_v1.json`. The Figure 9 scripts write under the
ignored `outputs/validation/` boundary and should be run only in a disposable
clean checkout; do not overwrite retained historical output during ordinary
verification.

## Maryville real unsignalised junction

```bash
PAPER1_MARYVILLE_OUT=/tmp/maryville_blackrock_real_junction_v1.json \
.venv/bin/python -c \
'import os; from urban_cybernetics.compiler.maryville_junction import compile_maryville_junction, write_maryville_junction_package; run=compile_maryville_junction("tests/fixtures/osm/maryville_brr_junction.osm"); write_maryville_junction_package(run, os.environ["PAPER1_MARYVILLE_OUT"]); print(run.package.deterministic_hash)'
shasum -a 256 /tmp/maryville_blackrock_real_junction_v1.json
```

Expected deterministic hash is
`47a59c312b87aaf5675a2777b617731d44374671d04bce5a1482e8054ecb2fb2`;
the generated file SHA-256 is
`53f2238f523446d0ec9f2985971bd0b0ceaee331dabc9d2120c3b60cbe5acd20`.

## Cork city-scale evidence

The external GraphML is not committed. Supply it with `--graphml PATH` or
`UC_CORK_GRAPHML=PATH`. Verify the adapter identity without running demand:

```bash
UC_CORK_GRAPHML=/absolute/path/to/cork_full_drive.graphml \
.venv/bin/python -c \
'from urban_cybernetics.topology.cork import load_cork_canonical_network; n=load_cork_canonical_network(); print(n.topology_hash); print(n.physical_profile_hash); print(n.source_provenance_hash)'
```

Expected hashes, in order, are:

```text
18c519fb1d69e374fe5a42931da3c4b7072cb423346fc14f1583f2e726f1b198
76dd209880628f5ab1cc798e1ff53a1f8ca9fefc76e61a3071b53375893455bd
bb93db90070af38fa455bd9f91d8e55c483b64b4b4d02ae415b998c49a87aa78
```

Representative deterministic fixed-horizon regeneration with exact replay:

```bash
.venv/bin/python scripts/run_cork_fixed_horizon.py \
  --graphml /absolute/path/to/cork_full_drive.graphml \
  --single-rung 100 \
  --single-output /tmp/cork_fixed_horizon_100.json \
  --force-replay
```

Expected run identity is
`ae95466df6a07c53127eebfd2b24ac2f7c47d784117900574a0264e92aa1c011`,
event hash `51e09210aa96dcee6dc98d10e3afa10986caf8a87901792421128804ed0b088c`,
and horizon-state hash
`efeb0096925650266cbe9fe5a86acdf634ef60e19e81b250dd6af5609a2e40d0`.

The manuscript ladder is exactly 100, 1,000, 2,500, 5,000, and 10,000
packets over 15,000 ticks (600 seconds):

```bash
.venv/bin/python scripts/run_cork_fixed_horizon.py \
  --graphml /absolute/path/to/cork_full_drive.graphml \
  --packets 100 1000 2500 5000 10000
```

Large output is written under ignored `outputs/cork_fixed_horizon_v1/`.
Wall/CPU time, RSS, profiles, generation timestamps, and any full-file hash
containing those values are machine-dependent. Topology, demand, route,
canonical-event, horizon-state, and run identity hashes are deterministic.
Cork demand is seeded synthetic demand and the physical profile is an
uncalibrated engineering profile; these runs do not support calibrated Cork
traffic, delay, queue, or congestion claims.

## Optional composition proof

The already-implemented observation/information/authority separation remains a
small proof of capability, not a Paper 1 experiment programme:

```bash
.venv/bin/python -m pytest -q \
  tests/test_first_asymmetric_information_experiment.py \
  tests/test_authority_visible_state.py \
  tests/test_observation_channel_expansion.py
```

The fixture proves that different visible information can select different
authority routes while the loading engine separately governs physical
execution. It makes no real-network behavioural or policy-effect claim.
