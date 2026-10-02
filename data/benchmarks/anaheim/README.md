# Anaheim Network

## Source
The Anaheim network for 1992 has been provided by Jeff Ban and Ray Jayakrishnan.
Via: http://www.bgu.ac.il/~bargera/tntp/

The current [Transportation Networks for Research Anaheim folder](https://github.com/bstabler/TransportationNetworks/tree/master/Anaheim)
describes donated datasets as for academic research only and requires source
acknowledgement. Urban Cybernetics does not redistribute the raw benchmark
files. Obtain these files from that folder using its Raw links or an upstream
clone, then place them here under these exact names:

| File | SHA-256 of the historical UC input |
| --- | --- |
| `Anaheim_net.tntp` | `99933b415e9500b13907829c37a43cfa9141714fad5af279081e28e5f9356f9a` |
| `Anaheim_trips.tntp` | `906893854cd0db4479c0b5f07678ce5616fa8e42e2b997f918c378309c66a94e` |
| `Anaheim_flow.tntp` | `eecd21c2a908b6a1c6729045ea260e96df1de026f05281d341fc281f2552cebe` |

Run `shasum -a 256 data/benchmarks/anaheim/*.tntp` from the repository root
and compare all three values. A different upstream revision is not the frozen
benchmark input. These files are ignored locally; do not add them to the UC
release. Cite the upstream dataset under its terms. MPL-2.0 does not license
these data.

Map by Marco Nie.

## Scenario
1992

## Contents

 - `Anaheim_net.tntp` Network
 - `Anaheim_trips.tntp` Demand
 - `AnaheimNetwork.pdf` Upstream picture; not a UC release file
 - `Anaheim_flow.tntp` Best known flow solution

## Dimensions
Zones: 38
Nodes: 416
Links: 914
Trips: 104,694.40

## Units
Time: minutes
Distance: feet
Speed: feet per minute
Cost:

## Generalized Cost Weights
Toll: 0
Distance: 0

## Solutions
`Anaheim_flow.tntp` with Average Excess Cost of less than 1E-15.
