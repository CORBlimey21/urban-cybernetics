# External pinned data

This directory is the default local install location for external inputs that
are intentionally excluded from the Git repository.

`cork_full_drive.graphml` is required for the Cork city-scale tests and
experiments. It is an 8,346,799-byte OSMnx 2.0.2 GraphML file with SHA-256:

```text
cc904d3c9107136fdf6fd24318c19c38958b63dc81c83441e8e5f855f41f5409
```

The dataset was published on 2026-10-02 at DOI
[10.5281/zenodo.22981344](https://doi.org/10.5281/zenodo.22981344),
under ODbL-1.0, © OpenStreetMap contributors. Obtain `cork_full_drive.graphml`
from that record and verify its identity before installation.
The canonical install path is `external/pinned/cork_full_drive.graphml`.

Install an author- or archive-supplied copy only after verification:

```bash
.venv/bin/python scripts/install_external_data.py \
  --cork-graphml /path/to/cork_full_drive.graphml
```

The GraphML is derived from OpenStreetMap. If it is distributed separately,
credit OpenStreetMap and its contributors, identify the Open Database License
(ODbL) 1.0, retain applicable notices, and distribute the database under the
ODbL or a compatible licence. See <https://www.openstreetmap.org/copyright>.
The software's MPL-2.0 licence does not replace the data licence.

The repository does not contain this file; acquire it from the published dataset.
Live OSM reacquisition is not byte-reproducible because the database changes over time. See
[the provenance record](../../docs/paper1/CORK_GRAPHML_PROVENANCE.md).
