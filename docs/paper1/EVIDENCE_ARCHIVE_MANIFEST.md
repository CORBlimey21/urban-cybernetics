# Publication evidence archive scope

Archive version: **1.0.0**. Evidence DOI:
[10.5281/zenodo.23000309](https://doi.org/10.5281/zenodo.23000309).
The bundle was published on 2026-10-02. This DOI identifies supporting evidence,
not the software.

Project-generated evidence is distributed under **CC BY 4.0** (`CC-BY-4.0`)
unless otherwise stated. The following three packages contain normalized
OpenStreetMap-derived database records; those embedded database portions remain
subject to **ODbL 1.0** (`ODbL-1.0`) and **© OpenStreetMap contributors**:

- `outputs/evidence/boreenmanna_south_link_junction_milestone_v1.json`
- `outputs/evidence/maryville_blackrock_real_junction_v1/maryville_blackrock_real_junction_v1.json`
- `outputs/evidence/boreenmanna_experiment_v1/boreenmanna_experiment_compilation_v1.json`

CC BY does not override ODbL rights in these files. Retained OSM contributor
usernames/IDs and mapped address tags are source provenance. Third-party source
material not licensed for redistribution is excluded: no TNTP raw data,
de Souza paper/PDF or digitised reference input files are in this bundle.
Original OSM XML exports and the Cork GraphML are also excluded; the embedded
normalized OSM records above remain present with their notices.

The published `urban-cybernetics-paper1-evidence-v1.0.0.zip` contains 24 files:
the 18 evidence files below, README.txt, this manifest's archive copy,
the unchanged evidence_manifest_v1.json, LICENSE-CC-BY-4.0.txt,
LICENSE-ODbL-1.0.txt and SHA256SUMS.txt (23 checksum entries; no self-hash).
It is a retained-output subset, not every paper result: no separate
cybernetic-composition result file is among these 18 files.

The published archive README and manifest copy record the DOI above;
SHA256SUMS.txt covers its evidence and accompanying files except itself.
Documentation changes in this repository do not rebuild or alter the published ZIP.

This manifest classifies the 18 ignored files hash-recorded in
`evidence_manifest_v1.json`. None is a primary source/input and none is a
temporary cache. Sixteen are frozen paper/supporting evidence that should be
preserved; two are readily regenerated summaries/packages but are retained in
the manifest. Do not add them wholesale to Git.

Archival location: the published Zenodo evidence record above, associated with the
software release and paper. Preserve the paths below inside the deposit, include
the JSON evidence manifest at its root, and have Zenodo plus the manifest expose
checksums. The exact Cork GraphML belongs in the separate ODbL-1.0 dataset
at DOI [10.5281/zenodo.22981344](https://doi.org/10.5281/zenodo.22981344).
Any other source archive needs its own documented scope and licence notices.

| Path | Bytes | Role | Classification | Regeneration/provenance | Recommended location |
| --- | ---: | --- | --- | --- | --- |
| `outputs/evidence/boreenmanna_south_link_junction_milestone_v1.json` | 6,027,911 | Full-source compiler milestone | Frozen evidence to archive | Requires the external full Boreenmanna OSM export; no complete release command is recorded | Separate Zenodo evidence/data record |
| `outputs/evidence/maryville_blackrock_real_junction_v1/maryville_blackrock_real_junction_v1.json` | 1,398,470 | Maryville compiler package | Derived output, regenerable | Tracked `maryville_brr_junction.osm`; exact command and expected hash are in `REPRODUCIBILITY.md` | Regenerated on demand; optional in Zenodo bundle for exact manifest completeness |
| `outputs/evidence/boreenmanna_experiment_v1/boreenmanna_experiment_compilation_v1.json` | 9,564,525 | Full-source synthetic compilation | Frozen evidence to archive | Requires full Boreenmanna OSM; `run_boreenmanna_experiment_matrix` plus `write_boreenmanna_experiment_outputs` | Separate Zenodo evidence/data record |
| `outputs/evidence/boreenmanna_experiment_v1/boreenmanna_representation_matrix_v1.json` | 177,302 | Full-source 12-case matrix | Frozen evidence to archive | Same runner; physics deterministic, performance fields machine-dependent | Separate Zenodo evidence/data record |
| `outputs/evidence/boreenmanna_integrity_audit_v1/boreenmanna_integrity_audit_v1.json` | 1,419,033 | Integrity-audit parent package | Frozen evidence to archive | Parent-chain API exists; no complete clean-clone command is recorded | Separate Zenodo evidence/data record |
| `outputs/evidence/boreenmanna_gate_aware_v2_comparison_v1/boreenmanna_gate_aware_v2_comparison_v1.json` | 857,086 | Gate-aware v2 package | Frozen evidence to archive | Requires matching v1 parent; deterministic hash excludes performance | Separate Zenodo evidence/data record |
| `outputs/evidence/boreenmanna_discharge_readiness_v3_v1/boreenmanna_discharge_readiness_v3_v1.json` | 1,795,097 | Discharge-readiness v3 package | Frozen evidence to archive | Requires matching v2 parent; deterministic hash excludes performance | Separate Zenodo evidence/data record |
| `outputs/cork_fixed_horizon_v1/cork_fixed_horizon_ladder_v1.json` | 72,000 | Reported Cork fixed-horizon ladder | Frozen evidence to archive | `scripts/run_cork_fixed_horizon.py --packets 100 1000 2500 5000 10000`; exact GraphML required; timings vary | Separate Zenodo evidence/data record |
| `outputs/cork_fixed_horizon_v1/cork_fixed_horizon_ladder_v1.md` | 2,540 | Human-readable Cork ladder report | Derived output, regenerable | Generated with the preceding ladder JSON; contains machine timing | Regenerated on demand; retain in Zenodo bundle for the archived run |
| `outputs/cork_fixed_horizon_v1/cork_fixed_horizon_rung_100_v1.json` | 11,832 | Cork 100-packet rung | Frozen evidence to archive | Fixed-horizon runner; deterministic identities plus machine timing | Separate Zenodo evidence/data record |
| `outputs/cork_fixed_horizon_v1/cork_fixed_horizon_rung_1000_v1.json` | 11,889 | Cork 1,000-packet rung | Frozen evidence to archive | Fixed-horizon runner; deterministic identities plus machine timing | Separate Zenodo evidence/data record |
| `outputs/cork_fixed_horizon_v1/cork_fixed_horizon_rung_2500_v1.json` | 11,860 | Cork 2,500-packet rung | Frozen evidence to archive | Fixed-horizon runner; deterministic identities plus machine timing | Separate Zenodo evidence/data record |
| `outputs/cork_fixed_horizon_v1/cork_fixed_horizon_rung_5000_v1.json` | 11,823 | Cork 5,000-packet rung | Frozen evidence to archive | Fixed-horizon runner; deterministic identities plus machine timing | Separate Zenodo evidence/data record |
| `outputs/cork_fixed_horizon_v1/cork_fixed_horizon_rung_10000_v1.json` | 11,829 | Cork 10,000-packet rung | Frozen evidence to archive | Fixed-horizon runner; deterministic identities plus machine timing | Separate Zenodo evidence/data record |
| `outputs/cork_city_scale/cork_scale_ladder_v1.json` | 34,114 | Earlier drain/bounded-run ladder | Frozen supporting evidence to archive | `scripts/run_cork_city_scale.py`; exact GraphML required | Separate Zenodo evidence/data record, labelled supporting/earlier protocol |
| `outputs/cork_city_scale/cork_rung_100_v1.json` | 10,002 | Earlier exact-drain 100 rung | Frozen supporting evidence to archive | `scripts/run_cork_city_scale.py --single-rung 100`; exact replay evidence | Separate Zenodo evidence/data record, labelled supporting/earlier protocol |
| `outputs/cork_city_scale/cork_rung_1000_v1.json` | 10,004 | Earlier exact-drain 1,000 rung | Frozen supporting evidence to archive | `scripts/run_cork_city_scale.py --single-rung 1000`; exact replay evidence | Separate Zenodo evidence/data record, labelled supporting/earlier protocol |
| `outputs/cork_city_scale/cork_rung_10000_v1.json` | 10,048 | Earlier bounded-drain 10,000 rung | Frozen supporting evidence to archive | `scripts/run_cork_city_scale.py --single-rung 10000`; not drain completion | Separate Zenodo evidence/data record, labelled supporting/earlier protocol |

The 18 files total 21,437,365 bytes. The GraphML and full Boreenmanna export are
external **source/input required for reproduction**, not members of this list.
The GraphML has the separate published dataset DOI above; the full Boreenmanna
source still needs a confirmed archival location with ODbL attribution.
The de Souza reference PDF is provenance material, not required to execute the
committed comparisons; link to its DOI/preprint rather than redistributing a
publisher PDF unless its redistribution terms are confirmed.
