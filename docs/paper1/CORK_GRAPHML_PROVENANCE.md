# Cork GraphML provenance and external-data contract

## Frozen identity

| Field | Value |
| --- | --- |
| Reserved dataset DOI | [10.5281/zenodo.22981344](https://doi.org/10.5281/zenodo.22981344) |
| Publication status | Reserved; public download not yet confirmed |
| Expected filename | `cork_full_drive.graphml` |
| Default local path | `external/pinned/cork_full_drive.graphml` |
| Size | 8,346,799 bytes |
| SHA-256 | `cc904d3c9107136fdf6fd24318c19c38958b63dc81c83441e8e5f855f41f5409` |
| Licence | ODbL-1.0 |
| Attribution | © OpenStreetMap contributors |
| Graph metadata | `created_with=OSMnx 2.0.2`, WGS 84, simplified directed multigraph |
| Topology | 5,891 nodes, 13,111 directed edges |
| Local file timestamp retained by all four audited copies | 2026-03-06 21:57:44 UTC |

Four byte-identical copies were located in the author's companion Cork routing
and preserved SciFest workspaces. The file first appears as a regular file in
the companion `constrained-system-optimal-routing` repository's initial commit
`a4dfea3d3f5020551d66bd2d8a6cda74a598647b`; an earlier companion commit used a
symlink to the shared copy. The companion pipeline records this acquisition:

```python
ox.graph_from_place(
    query="Cork City, County Cork, Ireland",
    network_type="drive",
    simplify=True,
)
ox.truncate.largest_component(graph, strongly=False)
ox.save_graphml(largest, cache_path)
```

This is enough to explain how the file was constructed, but not to reconstruct
the same bytes from today's OpenStreetMap. The GraphML does not retain an OSM
snapshot timestamp or Overpass response identity. A commit-pinned raw URL in
the companion GitHub repository returned HTTP 404 during the release audit, so
it is not a documented public acquisition source for third parties.

## Consumers

`tests/test_cork_city_scale.py` contains five data-dependent tests and
`tests/test_cork_fixed_horizon.py` contains one. They cover GraphML identity,
parallel-edge/source provenance, the engineering physical profile, deterministic
synthetic demand and weighted routing, seeded OD-prefix behaviour, and the
15,000-tick fixed-horizon protocol. `scripts/run_cork_city_scale.py` and
`scripts/run_cork_fixed_horizon.py` use the same source. All consumers resolve
an explicit argument first, then `UC_CORK_GRAPHML`, then the default path above.

In a clone without the file, these six tests are reported as external-data
skips. They run automatically when the verified file exists at the default path
or `UC_CORK_GRAPHML` points to it. A wrong file is not skipped: checksum or
identity validation fails.

## Distribution status

The file is an OpenStreetMap-derived database licensed under ODbL-1.0,
© OpenStreetMap contributors. Preserve attribution and applicable notices;
the software's MPL-2.0 licence does not replace these data terms. See
[OpenStreetMap attribution](https://www.openstreetmap.org/copyright) and
[ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/).

The dataset has reserved DOI
[10.5281/zenodo.22981344](https://doi.org/10.5281/zenodo.22981344).
The exact file must be deposited and the public download checked after
publication. Reservation alone does not establish availability. Until then,
use the verified author-supplied local file with
`scripts/install_external_data.py`. No direct download URL is assumed.

The separate Paper 1 evidence archive version 1.0.0 has reserved DOI
[10.5281/zenodo.23000309](https://doi.org/10.5281/zenodo.23000309);
it does not contain this GraphML. See `EVIDENCE_ARCHIVE_MANIFEST.md`.
