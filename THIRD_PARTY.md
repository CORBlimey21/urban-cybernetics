# Third-party code and data findings

Project-authored Urban Cybernetics software is licensed under Mozilla Public
License 2.0 (`MPL-2.0`). That licence applies only to material the project can
license; it does not relicense the separately identified data or external
material below.

## Reserved data and evidence records

- Cork GraphML: [10.5281/zenodo.22981344](https://doi.org/10.5281/zenodo.22981344),
  ODbL-1.0, © OpenStreetMap contributors. The exact filename, install path and
  checksum are in [the provenance record](docs/paper1/CORK_GRAPHML_PROVENANCE.md).
- Paper 1 evidence, archive version 1.0.0:
  [10.5281/zenodo.23000309](https://doi.org/10.5281/zenodo.23000309).
  Project-generated evidence is CC BY 4.0 unless otherwise stated. The three
  compiler packages listed in [the archive manifest](docs/paper1/EVIDENCE_ARCHIVE_MANIFEST.md)
  retain embedded OpenStreetMap-derived database portions under ODbL 1.0,
  © OpenStreetMap contributors; CC BY does not override those rights.

Both DOIs are reserved and publication is pending. Third-party source material
not licensed for redistribution is excluded from the evidence bundle. Raw TNTP
benchmark files and digitised de Souza reference CSVs are also omitted from
the proposed software release.

## Data requiring separate treatment

- The compact Boreenmanna and Maryville OSM XML fixtures identify OpenStreetMap
  and contributors and declare ODbL 1.0 in their file headers. The external Cork
  GraphML is an OSMnx extraction of OpenStreetMap and should be treated as an
  ODbL database. Distribution requires OpenStreetMap attribution, an ODbL notice,
  retention of notices, and share-alike treatment for the database. Keep these
  data outside any blanket statement that everything is MPL-2.0.
- The Sioux Falls and Anaheim TNTP files trace to Transportation
  Networks for Research/Bar-Gera. That repository says the donated datasets are
  for academic research only and requires source acknowledgement, but does not
  provide a standard open-data licence. The five raw `.tntp` files are therefore
  removed from the release tree. The [Anaheim](data/benchmarks/anaheim/README.md)
  and [Sioux Falls](data/benchmarks/sioux_falls/README.md) READMEs provide exact
  filenames, historical checksums, upstream acquisition and attribution.
- Twelve digitised de Souza figure CSVs derive from published reference figures
  (DOI [10.1016/j.simpat.2025.103088](https://doi.org/10.1016/j.simpat.2025.103088)).
  No express redistribution right is recorded. They are removed from the
  release tree; ten remain named and hashed in the immutable historical
  `data/validation/loading_kernel_freeze_manifest_v1.json`. Comparison runners
  require these inputs separately and stop clearly if they are absent. Retained
  UC-generated comparison summaries may contain extracted comparison values;
  review their redistribution scope separately before publication.
- The external de Souza PDF is not in the release tree. Continue linking to the
  DOI or lawful preprint; do not add a publisher PDF without confirmed rights.

## Code and generated assets

No vendored third-party Python or JavaScript source tree was found. Python and
npm packages are installed dependencies with their own licences; the lockfile is
metadata, not a vendored `node_modules` tree. Generated replay/evidence JSON is
project output, though records derived from third-party data retain the source
data's attribution and licence obligations.

## Scope of the software licence

MPL-2.0 applies to the project-authored source code. It does not alter the
licences, attribution requirements, or redistribution status of material listed
above.

The project-authored software, including the checksum-controlled source listed
in `data/validation/loading_kernel_freeze_manifest_v1.json`, is subject to the
terms of the Mozilla Public License, v. 2.0. A copy is provided in [LICENSE](LICENSE).
Those 25 frozen source files retain their exact bytes instead of receiving
inline SPDX comments. Other project-authored release source carries
`SPDX-License-Identifier: MPL-2.0`. No Exhibit B designation is applied.

The pre-existing untracked `legacy/` code and `scripts/02_build_od_matrix.py`
and `scripts/05_calibrate_validate.py` were left untouched: their authorship and
inclusion in this release have not been established. Manuscripts, papers,
datasets, frozen evidence and generated outputs receive no MPL grant through
this software-licensing pass.

The TNTP and digitised-reference rights are data-distribution issues
independent of the software licence. ODbL share-alike applies to the OSM-derived
database/fixtures, not automatically to independent simulator code collected
beside them. Use explicit path-level notices and a third-party/data section in
the release record rather than representing the entire archive as governed only
by MPL-2.0.
