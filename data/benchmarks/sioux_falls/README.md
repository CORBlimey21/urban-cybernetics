# Sioux Falls network

The network and trips files come from Transportation Networks for Research,
the successor to Hillel Bar-Gera's TNTP site:

<https://github.com/bstabler/TransportationNetworks/tree/master/SiouxFalls>

That repository describes donated datasets as for academic research only,
requires users to indicate the dataset source in publications, and disclaims
responsibility for results. It does not state a standard open-data licence.
Urban Cybernetics does not redistribute these raw benchmark files. Obtain them
from the upstream `SiouxFalls/` folder, using its Raw links or an upstream clone,
and place them here with these exact names and historical SHA-256 checksums:

| File | SHA-256 |
| --- | --- |
| `SiouxFalls_net.tntp` | `ace99b24cec69c273ff0cf3d6d074110177f0cc0ae24b0c7a9f4f4cb5e27635c` |
| `SiouxFalls_trips.tntp` | `56f9566857f3f66730fd5c4232258d7ee3ac2931a476526331afd062f4958de7` |

After installation, run `shasum -a 256 data/benchmarks/sioux_falls/*.tntp`
from the repository root and compare both values. A different upstream revision
is not the frozen benchmark input. The files are ignored locally; do not add
them to the UC release. Cite the upstream dataset under its terms. MPL-2.0
applies to UC software, not these data.
