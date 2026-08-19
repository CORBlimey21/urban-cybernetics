# Maryville--Blackrock Road real unsignalised junction v1

## Source identity

The second Paper 1 real-data case is the manually supplied pinned file
`maryville_brr_junction.osm`. No live OSM service was consulted.

- byte length: 106,424;
- SHA-256: `c6e23f6b00fbf3abb07eebd97c7afdedf731ac0e50e1fc46bde5b749f659308b`;
- parsed-content hash:
  `da9a43e752d19e9e472abf2c7c31aab73afdd5a6d81a0df78d24e487ff178b27`;
- inventory: 387 nodes, 31 ways, and 3 relations;
- declared bounds: latitude 51.895382--51.895748, longitude
  -8.434153---8.433461;
- generator: `openstreetmap-cgimap 2.1.0`.

The full export is retained as immutable test evidence. Raw records outside
the operational boundary remain inspectable.

## Operational boundary

The junction is the ordinary two-way T-junction where Maryville, OSM way
`5317316`, terminates on Blackrock Road, OSM way `477599192`, at node
`7842268`. Both ways directly report:

- `highway=tertiary`;
- `lanes=2`;
- `maxspeed=50` km/h;
- named road and local-reference identity;
- asphalt surface.

The source Blackrock Road way continues east to a separate signalised
crossing. Retaining the whole way would incorrectly make the bounded
T-junction signalised. The extraction configuration therefore uses explicit
source-ordered way-node intervals:

- Maryville: node `10980457806` to junction node `7842268`;
- Blackrock Road: node `7842270` through junction node `7842268` to node
  `10979271057`.

This is deterministic clipping of executable geometry, not rewriting of raw
source evidence. The previously existing extraction hash domain is unchanged
when no interval is configured.

The retained graph contains 12 geometry nodes and six directed links forming
three two-way approaches. Continuous approach lengths are 40.976, 54.187,
and 57.590 metres. The two signal heads and signalised crossing farther east
remain in the source package but are classified outside the operational
boundary. No signal node or crossing participates in the executable graph.

Extraction configuration hash:
`c3bcf0ee042e2c8a23514c355649eb5d9713265a954f357006b6cb038c8f5f55`.

Extraction hash:
`d67fe690b33bc1e05f7808c407ac903eeca43b8482dd378c793c0835355ff55f`.

## Source-strict audit

The source-strict result is structurally non-executable. Geometry, two-way
directionality, one lane per direction, 50 km/h speed, ordinary topology, and
the six non-reversing T-junction movements are source-supported or safely
derived.

The unresolved executable semantics are:

- capacity for each directed link;
- jam density for each directed link;
- backward-wave speed for each directed link;
- whether each of the six immediate reversals should be treated as a U-turn.

No signal timing or control field is unresolved because the operational graph
is genuinely unsignalised. OSM observations are not relabelled as model
defaults.

## Reviewed executable candidate

The reviewed candidate adds explicit, uncalibrated model configuration:

- tertiary-road capacity: 1,500 vehicles/hour/lane;
- jam density: 150 vehicles/km/lane;
- backward-wave speed: 5 m/s;
- tick duration: 1 second;
- conservative shared-link FIFO representation;
- six explicit no-U-turn review overrides.

The lane count and speed remain OSM observations; they are not defaults. The
shared representation is selected because total lanes are observed but
lane-to-turn allocation is absent.

At one second per tick, continuous link capacity is approximately 0.4167
vehicles/tick. The frozen loader-compatible minimum-one rule therefore emits
the expected clamp and relative-distortion warnings. This is numerical
compatibility evidence, not a physical capacity claim.

The reviewed candidate is executable with warnings. Executable semantic hash:
`be77c859070f0096ba526bc38df978d6f207a2dcf2327795d6ba61c2e45a48d7`.

## Deterministic smoke run

Synthetic smoke demand introduces one packet for each of the six legal
non-U-turn movements. It is explicitly classified as synthetic demand on real
OSM-derived geometry.

- demand/completed packets: 6/6;
- canonical physical events: 36;
- event hash:
  `f23a1d52ba8a8d269f9a8dd89a42a992ff816f9a2ae141267937c625beb3ae96`;
- replay: exact;
- conservation, event-cache, and cumulative-count checks: passed.

Only shared-link FIFO is claimed as source-honest here. Movement-partial FIFO
or explicit lane groups would add representation semantics not established by
this export.

Package deterministic hash:
`47a59c312b87aaf5675a2777b617731d44374671d04bce5a1482e8054ecb2fb2`.

Generated package file SHA-256:
`53f2238f523446d0ec9f2985971bd0b0ceaee331dabc9d2120c3b60cbe5acd20`.

## Importer finding

The only importer gap exposed by this second case was reviewed clipping of a
retained source way to a source-node interval. That capability is now narrow,
versioned through extraction configuration, deterministic, and backward
compatible with the Boreenmanna extraction identity.

No further importer feature is currently required by the two selected real
networks. Subject to the final regression and frozen-kernel checks, this case
supports freezing the Paper 1 importer scope.
