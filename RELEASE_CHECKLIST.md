# Archival release preparation: 1.0.0

Status: **v1.0.0 published**, with release date 2026-10-02. The public GitHub
repository has the published Latest release v1.0.0, and Zenodo software ingestion
is complete. The release tag remains at
`a9f521ed14e05b24cf1af39291df8259ce34b423`; DOI metadata is added in a follow-up
commit without moving that tag. The private development repository is separate.
See [public-history provenance](docs/provenance/PUBLIC_HISTORY_PROVENANCE.md).

| Resource | Identifier | Licence/status |
| --- | --- | --- |
| Software 1.0.0 | [10.5281/zenodo.23111562](https://doi.org/10.5281/zenodo.23111562) | MPL-2.0; published |
| Software all versions | [10.5281/zenodo.23111561](https://doi.org/10.5281/zenodo.23111561) | Concept DOI |
| Cork GraphML dataset | [10.5281/zenodo.22981344](https://doi.org/10.5281/zenodo.22981344) | ODbL-1.0; © OpenStreetMap contributors; published 2026-10-02 |
| Paper 1 evidence archive 1.0.0 | [10.5281/zenodo.23000309](https://doi.org/10.5281/zenodo.23000309) | CC BY 4.0 unless otherwise stated; embedded OSM database portions remain ODbL 1.0; published 2026-10-02 |

## Review gates

- [x] Add the unmodified MPL-2.0 text in LICENSE; align README, Python and web
  package metadata, and CITATION.cff. Project-authored source files carry SPDX
  identifiers except the 25 checksum-controlled sources, covered by the notice
  in THIRD_PARTY.md without changing their bytes. Third-party and data terms
  remain separately documented there. No Exhibit B designation is applied.
- [x] Use the author metadata present in the repository: Cillian Ó Ríordáin,
  ORCID https://orcid.org/0009-0006-2831-5380. Store the supplied ORCID in the
  CFF author entry. No affiliation or additional author is inferred.
- [x] Set the release date to 2026-10-02 in CITATION.cff.
- [ ] Add paper citation/DOI only if verified.
- [x] Obtain the software DOI after Zenodo ingestion and add it to CITATION.cff
  and release/reproduction documentation.
- [x] Remove five raw TNTP benchmark files and twelve digitised de Souza
  reference CSVs from the release tree; document separate acquisition,
  exact known identities and explicit test skips. Keep OSM-derived data under
  ODbL notices regardless of the software licence selected.
- [ ] Decide whether retained UC-generated comparison summaries containing
  extracted de Souza reference values may be redistributed. The historical
  freeze manifest records ten omitted CSVs; full historical verification needs
  separately supplied exact inputs and a full-history clone.
- [x] Record both published supporting DOIs in release documentation and the CFF citation
  message without treating either as a software or paper DOI.
- [x] Publish the Cork dataset at DOI 10.5281/zenodo.22981344 on 2026-10-02;
  retain the exact filename, byte size, checksum, ODbL-1.0 and OSM attribution.
- [x] Publish the 18 manifest-listed outputs in the 24-file evidence bundle at
  DOI 10.5281/zenodo.23000309 on 2026-10-02, with CC BY 4.0/ODbL mapping,
  official licence texts and SHA256SUMS.txt. Third-party source material not
  licensed for redistribution remains excluded. No extra lane-drop evidence
  is implied; its historical reproduction gap remains below.
- [ ] Confirm downloaded supporting-record files against their frozen identities
  as part of final release review; do not indiscriminately add outputs to Git.
- [ ] Resolve/accept explicitly the historical lane-drop and full Boreenmanna
  chain gaps in REPRODUCIBILITY.md; confirm the composition case against the paper.
- [x] Apply reviewed non-breaking npm lockfile fixes. Six transitive advisory
  packages were updated; no direct version range or major version changed.
- [ ] Decide when to upgrade Vitest across its major-version boundary. The one
  remaining advisory appears twice (direct Vitest and transitive mocker), is
  moderate, and affects the local test runner rather than production bundles.
  See `docs/release/NPM_ADVISORY_TRIAGE.md`.
- [x] Replace macOS-only plot fonts with constrained Pillow's embedded Aileron;
  retain an explicit Arial opt-in for archived PNG typography.
- [x] Record a clean full-suite run without the Cork source (six explicit
  skips), and run all Cork test modules with the verified source installed.
- [ ] Publication commands/configurations checked; record which expensive scale
  runs were not rerun. Verify deterministic identities separately from timing/RSS.
- [x] Record a clean ordinary suite run with external-input skips, plus the
  historical kernel verifier's expected unavailable-input result and Paper 1
  evidence identities. Do not mark the full kernel verifier passed unless its
  ten omitted reference CSVs were separately supplied.
- [x] CITATION.cff validates (`cffconvert --validate -i CITATION.cff`) with the
  supplied author metadata, related published DOIs and date-released 2026-10-02.
  The exact software DOI is recorded; no paper DOI is inferred.
- [x] Package version, web package/lock metadata and CFF agree at 1.0.0. Leave
  loading-kernel-v1.0.1, compiler/schema/profile IDs and historical 0.1.0 evidence
  metadata unchanged.
- [x] Review current tracked paths and leave the three absolute paths in the
  frozen Anaheim profile unchanged as historical provenance. Active font/runtime
  dependencies no longer contain machine paths; no credential patterns found.
- [x] Keep excluded workspace, legacy, OD-generation and calibration material
  outside the sanitised public repository; no private untracked files were cloned.
- [x] Commit the four release-preparation changes and public-history provenance;
  confirm clean sanitised and fresh-clone working trees at the validation HEAD.
- [x] Review/commit approved pre-release documentation changes and confirm
  the final public working tree is clean before tagging.
- [x] Record the tagged release commit above; the inspected starting revision was
  original development-history ID `95c84313c2f826255a70b573674da28d1a4851a6`.
  Resolve its public equivalent through the
  [commit mapping](docs/provenance/public-commit-map.tsv).
- [x] Make the sanitised GitHub repository public after final approval.
- [x] Enable the repository in Zenodo's GitHub integration.
- [ ] Independently review archived creator/licence metadata and file checksums.
- [x] Create/push tag `v1.0.0` after review.
- [x] Publish the GitHub release v1.0.0 (Latest).
- [x] Confirm Zenodo software ingestion and obtain the exact version DOI.
- [ ] After publication, check Zenodo ingest status, version/commit, creators,
  licence, files and checksums, related paper metadata, and assigned DOI. Confirm
  separately that the intended evidence bundle is archived; do not assume ignored
  files or arbitrary release assets are included automatically.
- [x] Add the verified DOI to the repository citation metadata in a follow-up
  commit; do not move the published tag to add it.

## Fresh sanitised-public-clone validation (2026-10-02)

Validation HEAD: `ed44462493bb688a0b0f91296ff7df5d87ca3800` (before subsequent
documentation-only changes). CPython 3.13.3; documented constrained editable
installation; external TNTP/de Souza inputs deliberately absent.

- Python suite without Cork: 850 passed, 74 expected skips, 88 subtests passed.
- Cork installed through the checksum-verifying installer: full suite 856 passed,
  68 expected skips, 88 subtests passed. Both runs had one dependency deprecation warning.
- `pip check`, wheel/sdist build and metadata checks passed: version 1.0.0,
  MPL-2.0 and identical LICENSE bytes. CFF validated against 1.2.0.
- Web tests/build/lint passed: 26 tests in seven files; existing bundle-size
  warning and two moderate npm advisory entries remain.
- Public freeze adapter resolved all four historical commits, then reported the
  expected missing digitised input. Separate checks: 54 available frozen files
  match their checksums; four summary checks pass; ten reference CSVs are absent.
- Paper 1 verifier passed for ten tracked artifacts and exact Cork identity.
  `--include-ignored` is unavailable in a fresh clone until the separate evidence
  archive is acquired; the 18 retained outputs are not Git contents.
- `git diff --check`, clean working-tree checks and `git fsck` passed. All 17
  excluded input paths are absent from public history and HEAD. No expensive
  experiment regeneration was performed.

The preparation records below describe earlier development-repository checks
and environments, not the current public clone's available-input coverage.

## Preparation checks (2026-09-19)

Checks ran with CPython 3.13.3 on macOS arm64. `PY` below denotes the fresh
validation environment's Python; the editable package points to a disposable
full-history clone with the proposed package metadata and release constraints.

| Check | Result |
| --- | --- |
| `python3.13 -m venv …`; `python -m pip install -c constraints-release.txt -e '.[dev,visualisation,publication]'` | Passed in a new environment from a disposable full-history clone. |
| `$PY -m pip check` | Passed. |
| `$PY -m pytest -q` without external data | **908 passed, 6 explicitly skipped, 88 subtests passed**, 82.13 seconds; one Starlette deprecation warning. |
| `scripts/install_external_data.py --cork-graphml SOURCE --destination /tmp/…` | Passed: verified 8,346,799 bytes and the frozen SHA-256 before copying. |
| Cork modules plus portability tests with `UC_CORK_GRAPHML` set | **9 passed** in 10.67 seconds, including all six Cork tests. |
| `python scripts/verify_loading_kernel_freeze.py` | Passed: 64 files, five regeneration commands, 101 focused tests. |
| `python scripts/verify_paper1_evidence.py --include-ignored --cork-graphml SOURCE` | Passed locally: 10 tracked, 18 retained ignored files, and the external Cork source. |
| `cffconvert --validate -i CITATION.cff` (2.0.0) | Valid against CFF 1.2.0 at this historical check; author placeholder was subsequently replaced from repository-supplied metadata. |
| README analytical smoke | All six cases passed. |
| REPRODUCIBILITY.md Sioux Falls 24-packet command | 24 completed; validation and exact replay passed. |
| Figure 8 ensemble with all four redirected output paths from REPRODUCIBILITY.md | Passed: both CSVs byte-identical to tracked evidence; summary differences limited to redirected artifact paths. |
| Figure 7 comparison, both Figure 9 runners, lane-group ablation | All exited 0 in the disposable clone; tracked paper hashes still passed after exports. |
| Portable Figure 5/7/8 rendering without Arial | Six non-empty PNGs generated with constrained Pillow's embedded Aileron; Figure 5/7 comparison CSVs and both Figure 8 CSVs were byte-identical to retained/tracked evidence. |
| `$PY -m build --no-isolation` (build 1.6.1, setuptools 84.0.0) | 1.0.0 wheel and sdist built. Publication data/fixtures are not wheel contents; use the Git checkout. |
| `npm ci`, `npm test`, `npm run build`, `npm run lint` (Node 26.0.0, npm 11.12.1) | Passed: seven test files, 26 tests. Build warns about bundle size. Browser E2E not run. |
| `npm audit fix --package-lock-only`; tests/build/lint; `npm audit --json` | Non-breaking in-range lock updates fixed brace-expansion, browserslist/baseline mapping, js-yaml, nanoid and postcss findings. Two moderate entries remain for one Vitest redirect-mock advisory; fixing requires Vitest 5.0.1, a major upgrade. |
| `git diff --check`; version/link/path/credential-pattern scans | Passed whitespace, five-way 1.0.0 consistency, local links and credential patterns. Only the three documented historical paths in the frozen Anaheim profile remain. No tracked cache/build tree found. |

No full high-packet Sioux Falls or Cork benchmark ladder was rerun. Browser E2E
was not run. Frozen scientific files, validation results and manifest hashes
remain unchanged.

## Final metadata checks (2026-09-27)

Only release documentation and CITATION.cff were edited. Both dataset/evidence
DOIs are recorded as reserved; no software DOI, paper DOI or release date was
invented. The supplied author name and ORCID are now valid CFF author metadata.
The existing environment was used for tests; build/CFF tools were installed in
a disposable environment outside the repository. Dependencies were not changed.

| Check | Result |
| --- | --- |
| `UC_CORK_GRAPHML=SOURCE PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q` | 914 passed, 88 subtests passed, no skips, 90.76 seconds; one existing Starlette/httpx deprecation warning. |
| `.venv/bin/python -B -m pip check` | Passed. |
| `.venv/bin/python -B scripts/verify_loading_kernel_freeze.py --skip-regeneration` | Passed: 64 recorded files, four parsed summaries, 65 text scans and 101 focused tests; zero regeneration commands. |
| `.venv/bin/python -B scripts/verify_paper1_evidence.py --include-ignored --cork-graphml SOURCE` | Passed: 10 tracked and 18 ignored evidence files, plus exact external Cork source identity. |
| `cffconvert --validate -i CITATION.cff` (2.0.0) | Valid CFF 1.2.0 after correcting the supplied ORCID's YAML placement. Dataset creator metadata is not inferred; reserved resource links are in the citation message. |
| `python -B -m build --no-isolation BUILD_COPY --outdir /tmp/uc-final-metadata-dist` | Passed in a temporary source copy with build 1.6.1/setuptools 84.0.0. Wheel/sdist report version 1.0.0, `License-Expression: MPL-2.0`, `License-File: LICENSE`, and contain the exact root licence bytes. |
| `npm test && npm run build && npm run lint` in `web/` | Passed: 26 tests in seven files; existing bundle-size warning only. |
| `git diff --check`; local link/path/placeholder/credential and metadata scans | Passed for current release-facing documentation; historical evidence identifiers and provenance paths remain unchanged. Both reserved DOI identifiers are consistent. |

External DOI/GitHub page checks could not confirm public availability; reservation
is not described as publication. The evidence ZIP's staged DOI text/checksums
still need a packaging-only refresh before deposit. The existing lane-drop,
full Boreenmanna chain, input-rights and final manuscript-mapping review gates
remain open. No scientific regeneration, expensive scaling or browser E2E ran.

## Distribution-input cleanup checks (2026-09-28)

The proposed release tree now omits five TNTP raw files and twelve digitised
de Souza reference CSVs. The 18 separate Paper 1 evidence-archive files and
historical freeze manifest were not edited. The ordinary suite gives explicit
external-input skips, while the historical verifier remains unavailable without
its ten separately supplied reference CSVs. The earlier successful verifier
results above describe the prior local-input state, not the release tree.

| Check | Result |
| --- | --- |
| `pytest -q` without Cork/TNTP/de Souza inputs | 840 passed, 74 skipped, 88 subtests passed; one existing Starlette warning. |
| `UC_CORK_GRAPHML=SOURCE pytest -q` | 846 passed, 68 skipped, 88 subtests passed; same warning. |
| `verify_loading_kernel_freeze.py --skip-regeneration` | Unavailable as expected: first missing reference is Figure 5(a) v2 inflow CSV. Separate read-only hash check: 54/54 present recorded files match; 10 missing reference CSVs, zero mismatches. |
| `verify_paper1_evidence.py --include-ignored --cork-graphml SOURCE` | Passed: ten tracked and 18 ignored evidence files plus exact Cork source. |
| `pip check`; Python sdist/wheel build; CFF validation | Passed; wheel/sdist include exact MPL-2.0 licence bytes and wheel metadata identifies version 1.0.0. |
| Web tests, build and lint; `git diff --check` | Passed: 26 web tests; existing bundle-size warning. No whitespace errors. |

No scaling runs or scientific outputs were regenerated. Review retained
UC-generated comparisons containing extracted reference values before public
distribution, as noted in THIRD_PARTY.md.

## Proposed commit and release notes

### Earlier MPL-2.0 licensing validation

- Official Mozilla plain-text LICENSE verified byte-for-byte; no Exhibit B
  designation applied. Its original whitespace is retained without editing.
- 244 source notices: 208 Python, 34 JavaScript/TypeScript, one CSS and one HTML.
  The 25 checksum-controlled source files are unchanged and covered by the
  software-scope notice in THIRD_PARTY.md.
- Python, web package/lock root and CFF metadata agree on MPL-2.0 and 1.0.0.
  The existing setuptools backend requires >=77 for SPDX licence expressions
  and licence-file metadata; runtime dependencies are unchanged.
- `python -m pytest -q`: 908 passed, six external-Cork skips, 88 subtests passed
  in 76.84 seconds; one existing Starlette deprecation warning.
- `npm test`, `npm run build`, `npm run lint`: passed (26 tests); existing
  bundle-size warning only. Lock dependency entries are unchanged.
- `python -m build --no-isolation`: passed using setuptools 84.0.0. Wheel and
  sdist contain the exact LICENSE and `License-Expression: MPL-2.0` metadata.
- `cffconvert --validate -i CITATION.cff`: valid CFF 1.2.0; placeholders unchanged.
- Kernel verifier `--metadata-only`: all 64 recorded files pass. Paper verifier
  `--include-ignored`: all 10 tracked and 18 ignored evidence files pass.
- Conflicting current software-licence scan and `git diff --check`: passed.

### Historical proposed release text

Commit message:

```text
chore(release): prepare 1.0.0 archival research software metadata and reproduction guide
```

GitHub release title: **Urban Cybernetics v1.0.0 — research software**

Proposed release notes (review and complete before publishing):

> First archival research-software release accompanying the Urban Cybernetics
> paper. Includes the packet-based loading implementation, analytical and
> digitised reference validation, junction representation and fractional-service
> experiments, OSM compiler cases, synthetic demand scaling, and bounded
> information/routing composition experiments.
>
> See README.md for setup and REPRODUCIBILITY.md for exact entry points, expected
> evidence boundaries, and external data requirements. Cork experiments use
> synthetic demand and uncalibrated engineering parameters. Runtime and memory
> measurements are machine-dependent; replay policies are reported explicitly.
>
> This release packages the existing scientific implementation; the release
> preparation changes documentation, dependency declarations and version metadata.
> The loading-kernel and evidence identifiers retain their original versions.
>
> Project-authored software is licensed under MPL-2.0; third-party data retains
> its separately documented terms.
>
> Published supporting records (2026-10-02): Cork GraphML dataset, 10.5281/zenodo.22981344
> (ODbL-1.0; © OpenStreetMap contributors), and Paper 1 evidence archive 1.0.0,
> 10.5281/zenodo.23000309 (CC BY 4.0 unless otherwise stated; embedded OSM
> database portions remain ODbL 1.0). These supporting DOIs do not identify
> the software release; its Zenodo DOI will follow software ingestion.
>
> Before publishing, insert: confirmed creators, final commit SHA,
> final validation results, verified paper reference if available, and the location
> and checksums of the archived evidence/external-source bundle.

## Historical publication procedure (completed for v1.0.0)

The procedure below records the pre-release publication plan; do not rerun it
for the existing v1.0.0 release or move its tag.

Use only the sanitised public derivative. Create/configure its separate public
GitHub remote before following these recommendations: both fetch and push URLs
for `origin` must name `CORBlimey21/urban-cybernetics`, never the private
development repository or a local clone. No mirror push is intended.

First close the gates above, review/commit the selected files, and leave a clean
working tree. Save the completed release notes to a file outside the repository,
for example `/tmp/uc-v1.0.0-release-notes.md`, including the final commit hash.
The commands below are recommendations only; none were executed in this pass.
They intentionally stop if a tag/release already exists or the worktree is dirty.

```bash
set -e
# Run from the reviewed sanitised public repository on main.
test "$(git branch --show-current)" = main
for UC_PUBLIC_ORIGIN_URL in "$(git remote get-url origin)" "$(git remote get-url --push origin)"; do
  case "$UC_PUBLIC_ORIGIN_URL" in
    https://github.com/CORBlimey21/urban-cybernetics|https://github.com/CORBlimey21/urban-cybernetics.git|git@github.com:CORBlimey21/urban-cybernetics.git) ;;
    *) echo "origin must be the separate public GitHub repository" >&2; exit 1 ;;
  esac
done
test -z "$(git status --porcelain)"
: "${UC_CORK_GRAPHML:?Set this to the verified pinned Cork GraphML}"
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
.venv/bin/python scripts/verify_paper1_evidence.py --include-ignored \
  --cork-graphml "$UC_CORK_GRAPHML"
# The public adapter scripts/verify_public_loading_kernel_freeze.py --metadata-only
# needs ten omitted de Souza CSVs as well as mapped public Git history.
# Review its recorded unavailable-input result or run it in an authorized
# public-history checkout containing those exact separately obtained inputs.
# cffconvert must be installed in a separate validation environment/on PATH.
cffconvert --validate -i CITATION.cff
(cd web && npm ci && npm test && npm run build && npm run lint)
git diff --check
test -z "$(git status --porcelain)"
git rev-parse HEAD
# Record the printed hash in the completed release notes and inspect those notes.
test -s /tmp/uc-v1.0.0-release-notes.md
git tag -a v1.0.0 -m "Urban Cybernetics 1.0.0"
git show --no-patch v1.0.0
git push origin HEAD
git push origin refs/tags/v1.0.0
gh release create v1.0.0 --verify-tag \
  --repo CORBlimey21/urban-cybernetics \
  --title "Urban Cybernetics v1.0.0 — research software" \
  --notes-file /tmp/uc-v1.0.0-release-notes.md
```

GitHub CLI authentication and Zenodo integration are manual prerequisites.
Check [Zenodo's repository integration guide](https://help.zenodo.org/docs/github/enable-repository/)
and inspect the resulting ingest after publication. If publication fails after
pushing the tag, inspect remote state before retrying; do not recreate/move it.
