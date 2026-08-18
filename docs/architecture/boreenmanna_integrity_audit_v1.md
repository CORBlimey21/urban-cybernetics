# Boreenmanna experiment integrity audit v1

## Claim boundary and parent evidence

This audit asks whether the existing controlled representation comparison is
internally strong enough to cite as manuscript evidence. It remains a study on
real OSM-derived geometry with review-supplied physical parameters, synthetic
control, synthetic lane assignments, and synthetic demand. It is not a
calibration or validation of traffic at the real Boreenmanna junction.

The audit is a child of, and does not replace, the v1 matrix with deterministic
hash `3d493f7306f4a7766393fe41cb83f26d4dd0b83e233456f9ccb50b4f7d61920f`.
The original OSM milestone JSON remains byte-identical at SHA-256
`18340a74742ee28bb28cd71e5f8896d225bedfc7edfeee54a29682ea1026075a` and
the original v1 matrix JSON remains byte-identical at SHA-256
`b5a688fa7868060f514689163e892d85b389690e9eb21a3cbec252031b19d661`.

Audit deterministic hash:
`b047b4638ea61184b393adc374e18bd36504ff88b5e952dfe0ff408ad3d8375c`.
The complete package hash, which also covers machine-dependent performance,
is `a8c653572297a6e9746bf6ccb6e355cc129486b977e7e9e6833bc59f9c11a13e`.

## Evaluation and drain contracts

The evaluation horizon remains exactly 120 ticks for moderate demand and 180
ticks for stress demand. No original metric is redefined. At that tick the
audit snapshots completed packets, physically active packets, demand still
waiting for origin storage, queues, and link storage.

The separate drain phase declares no new demand. All already-declared demand
whose departure is eligible at the evaluation horizon remains in scope. The
same engine instance continues with the same signal phase, queues, allocator
state, capacities, and fractional balances. It stops only when:

1. no declared demand remains pending; and
2. every instantiated packet is completed or cancelled.

Nonphysical extension balances do not keep an empty network alive. One idle
tick is not a terminal condition. The deterministic safety cap is 1,200 drain
ticks; none of the twelve core cases reaches it. Tests include both a case
which clears during drain and a permanently closed movement which correctly
terminates at the cap as unresolved.

## Core matrix with eventual clearance

| Demand | Capacity | Representation | Complete at evaluation | Pending demand | Physically active | Eventual complete | Drain ticks | Final completion tick |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Moderate | Fractional | Explicit groups | 28 | 0 | 0 | 28 | 0 | 109 |
| Moderate | Fractional | Movement partial | 28 | 0 | 0 | 28 | 0 | 109 |
| Moderate | Fractional | Shared strict | 17 | 0 | 11 | 28 | 69 | 189 |
| Moderate | Legacy | Explicit groups | 23 | 0 | 5 | 28 | 48 | 168 |
| Moderate | Legacy | Movement partial | 23 | 0 | 5 | 28 | 48 | 168 |
| Moderate | Legacy | Shared strict | 17 | 0 | 11 | 28 | 69 | 189 |
| Stress | Fractional | Explicit groups | 60 | 0 | 24 | 84 | 89 | 269 |
| Stress | Fractional | Movement partial | 60 | 0 | 24 | 84 | 89 | 269 |
| Stress | Fractional | Shared strict | 35 | 5 | 44 | 84 | 329 | 509 |
| Stress | Legacy | Explicit groups | 48 | 0 | 36 | 84 | 308 | 488 |
| Stress | Legacy | Movement partial | 48 | 0 | 36 | 84 | 308 | 488 |
| Stress | Legacy | Shared strict | 35 | 5 | 44 | 84 | 329 | 509 |

All packets eventually complete. The original incomplete counts are therefore
horizon-limited residuals, not permanent non-clearance. They are still genuine
congestion outcomes at the declared evaluation horizon: they correspond to
physical storage and queues, and in stress shared FIFO five declarations have
not yet entered because origin storage is full. Representation and numerical
policy remain consequential through clearance time even though eventual
throughput converges to 100%.

Shared strict FIFO takes 69 moderate drain ticks versus 0--48 for partitioned
representations, and 329 stress drain ticks versus 89--308. Fractional service
reduces partitioned stress clearance from tick 488 to 269. Shared strict FIFO
is unchanged in completion and clearance between the two capacity modes in
these authored scenarios.

## Fractional service-credit state order

The audit retains `uc.fractional-service-credit.v1`; no numerical recurrence is
silently changed. Configuration construction now rejects policy labels which
do not describe the implemented recurrence.

Sending account for rate `c`:

1. open with fractional carry `f` in `[0,1)`;
2. add `c` before allocation;
3. expose `floor(f+c)` whole per-link sending opportunities;
4. let the existing movement/signal/conflict/receiving allocator decide actual flow;
5. retain `(f+c) mod 1`; unused whole opportunities expire.

Thus no-demand, red, receiving-closed, conflict-blocked, and FIFO-blocked ticks
consume the clock opportunity but retain the fractional phase. This is an
explicit *per-tick saturation opportunity* interpretation, not a banked token
interpretation. It prevents arbitrary bursts after long idle/red periods.

Receiving account:

1. initial credit is preloaded with one allowance `c`;
2. expose `floor(opening_credit)` before allocation;
3. consume only physically executed entries;
4. add `c` after execution;
5. cap closing credit at `ceil(c)+1`.

The preload means receiving and sending expose their first whole service on
the same tick; there is no accidental one-tick phase lag. The cap is the
existing de Souza parity recurrence bound used by the frozen loader, not a new
Cork-specific heuristic. It retains limited unused downstream supply while
preventing an unbounded reopening burst. Static-rate saturated, closure,
idle, routing, signal and shared-downstream merge tests confirm conservation,
deterministic competition, and long-run service. Time-varying capacity is not
supported in v1, so no variable-rate claim is made.

## Periodic gating and phase sensitivity

An analytical saturated two-link fixture uses `c=0.25` packet/tick, a four-tick
cycle, and two green ticks. Whole sending opportunities occur at ticks
`4,8,...,32`. At offset zero they coincide with green and the implementation
serves eight packets, exactly matching the recurrence. At offset two they all
coincide with red and service is zero, again exactly matching the recurrence.

This is a real phase-aliasing limitation of the chosen expiring-opportunity
interpretation for small rational rates and periodic gates. It is not a
sending/receiving update-order bug. Replacing it with token retention or
green-only accrual would be a different, versioned physical convention and is
not smuggled into this audit.

The Cork audit uses offsets 0, 1, 2, 5 and 10 ticks for every scenario,
capacity mode and representation. Evaluation completion ranges are:

| Demand | Capacity | Explicit | Movement partial | Shared strict |
| --- | --- | ---: | ---: | ---: |
| Moderate | Fractional | 0 | 0 | 1 |
| Moderate | Legacy | 1 | 1 | 1 |
| Stress | Fractional | 3 | 3 | 0 |
| Stress | Legacy | 3 | 3 | 0 |

Mean-delay ranges are 1.30--2.12 ticks in fractional cases and 0.12--2.90 in
legacy cases. Final-completion tick ranges are 10--15 ticks. Fractional mode is
not more phase-sensitive than legacy mode on this matrix: the largest
completion range is three packets for both. The theoretical resonance remains
a limitation outside the tested Cork rates and long green windows.

## Representation parity proof

Twenty parity families cover two demands, two capacity modes, and five signal
offsets. Each family has one canonical common-input payload and three separate
representation payloads. Construction fails if any common payload or hash
differs; a perturbation test changes a seed and proves rejection.

Common payloads cover source and extraction hashes, normalized evidence,
reviewed assumptions, synthetic dossier, complete shifted signal plan, demand
records/routes/departures, seed, tick duration, continuous capacities,
service-credit configuration, evaluation/drain horizons, routing, baseline
governance, conflict resources, common topology, and executable semantic hash.

Only these fields differ:

* shared strict FIFO: strict shared-link policy and conservative common queue;
* movement partial FIFO: experimental movement-coupling policy;
* explicit groups: synthetic lane-group declarations, queue partition, and
  route-next-movement assignment policy.

All 20 families validate; no unintended non-representation difference was
found.

## Evidence scaling

The controlled scaling fixture holds topology, 120 ticks, explicit groups and
fractional mode fixed while using 7, 14 and 28 packets.

| Packets | Physical events | Credit records | Signal records | Allocation traces | Replay bytes | Total deterministic bytes |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 7 | 112 | 5,280 | 83 | 96 | 4,397,608 | 13,968,268 |
| 14 | 228 | 5,280 | 139 | 165 | 4,615,502 | 14,192,085 |
| 28 | 458 | 5,280 | 307 | 334 | 5,173,980 | 14,762,409 |

Physical events are approximately linear in packets. Credit evidence is
exactly `22 links × 2 accounts × 120 ticks = 5,280` and is independent of
demand. The 9.56 MB compiler dossier is a fixed per-run cost in the reported
total. Consequently bytes per physical event fall from about 124,717 to
32,232 as demand increases. Across drained core runs, deterministic artefact
size is 10.7--32.9 MB and credit logging remains exactly 44 records per tick.

Full forensic evidence is tractable for this small matrix but expensive for
sweeps: the complete audit took 728.8 seconds on the recording machine.
Recommended future modes are:

* full forensic: current per-account/per-tick records and exact replay payload;
* compact publication: hash-anchored event/evidence streams plus selected
  records and deterministic aggregates;
* aggregate runtime: counters only, explicitly unsuitable for forensic replay.

No current replay evidence is removed by this milestone.

## Supportable conclusions and limitations

The controlled evidence supports these narrow claims:

* shared strict FIFO materially lowers evaluation-horizon throughput and
  materially delays clearance on this pinned geometry under the authored
  scenarios;
* explicit synthetic lane partitioning has lower evaluation-window queue delay
  than movement-partial FIFO here, although both have identical eventual
  completion and clearance ticks;
* fractional execution materially improves partitioned throughput and
  clearance relative to integer flooring in this two-second configuration;
* these distinctions are congestion and clearance-time effects rather than
  permanent loss, because all twelve core cases drain completely;
* tested Cork outcomes have modest and comparable legacy/fractional phase
  sensitivity, while a low-rate resonant analytical case exposes a genuine v1
  aliasing boundary;
* evidence volume is manageable for twelve runs but resource×tick logging, not
  physical events, dominates fractional sweeps.

The evidence does not support real Boreenmanna accuracy, calibration quality,
real signal timing, real lane allocation, superiority against field traffic,
or cross-junction generality. The smaller junction remains a synthetic
OSM-like compiler fixture. A second pinned real unsignalised `.osm` export is
still required before any cross-junction real-data claim.

Before a publication-scale experiment, choose and preregister whether the v1
clock-opportunity policy or a new bounded gate-aware credit convention is the
scientific object of study, then add measured demand/control evidence and run
sensitivity bands rather than one deterministic synthetic demand.

The follow-on `gate_aware_fractional_service_v2.md` implements that convention
as a separately versioned comparator. It does not revise this V1 evidence.
