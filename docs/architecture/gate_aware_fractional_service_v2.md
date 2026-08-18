# Gate-aware fractional service V2

## Scientific scope

`uc.gate-aware-fractional-service.v2` is an opt-in runtime policy above the
unchanged loading kernel. It consumes compiler continuous link capacities
without changing compiler evidence, integer loader declarations, or canonical
physical events. V1 remains available and unchanged.

- V1 is a clock-driven sequence of transient service opportunities. Its
  fractional phase advances every tick and unused whole opportunities expire.
- V2 treats nominal saturation capacity as an active-discharge rate. Red
  contributes zero new entitlement while an existing fractional remainder
  survives the interruption.

V2 does not add startup lost time, acceleration, stochastic headways,
calibration, or field-observed controller semantics.

## Architecture and ownership

The reusable path is:

`base allowance × control availability × dynamic multiplier → fractional
accumulator → whole exposure → existing allocator → physical flow`.

There is one sending account per physical upstream link, never one per
movement. V2 inspects the free-flow-eligible packets on that link. The account
is enabled when at least one relevant next movement is uncontrolled or green;
it is disabled when every relevant movement is red or no demand is eligible.
This pre-allocation test avoids a circular dependency on allocator selection.

A mixed green/red link receives one shared budget. Shared strict FIFO can
still block a green packet behind a red packet; movement-partial and explicit
lane groups can use the same budget differently. The red movement cannot
consume it, and capacity is not duplicated per movement. This is the narrowest
coherent approximation supported by current link-level capacity evidence, not
a claim about independent movement saturation flows.

## Exact V2 recurrence

For link `l` and tick `t`, let `c` be base packets/tick, `a` binary control
availability, `m` the dynamic multiplier (exactly `1.0` in V2), and `f` the
opening fraction in `[0,1)`:

```text
e = c × a × m
x = f + e
k = floor(x)
f_next = x - k
0 <= physical_flow <= k
expired = k - physical_flow
```

When every relevant movement is red, `a=0`: no allowance is added, no whole
service is exposed, and the existing fraction is preserved. When the link has
no free-flow-eligible packet, `a=0`, so empty green time cannot bank future
capacity. Uncontrolled or permanently green service uses `a=1`.

Only the sub-unit remainder persists. If a whole opportunity is exposed but
receiving, FIFO, conflict, lane-group, governance, or competing allocation
prevents use, it expires after that enabled tick. This keeps V1's bounded
no-burst convention for non-signal constraints while correcting red accrual.
Only physical execution is reported as consumed.

## Receiving service

V2 does not signal-gate receiving accounts. Downstream supply retains the
existing de Souza-compatible recurrence: expose `floor(opening_credit)` before
allocation, consume actual entries, add continuous allowance after execution,
and cap at `ceil(c)+1`. Upstream red therefore does not become downstream
incapacity.

## Evidence and identities

`uc.effective-rate-fractional-service-evidence.v1` records the account/domain,
base rate and allowance, tick duration, gate state, availability, dynamic
multiplier, effective allowance, opening and closing fractions, whole exposure,
physical consumption, expired opportunity, cap, relevant movements/packets,
consumed packets, policies, and configuration/executable hashes.

Evidence remains separate from canonical events. Account IDs are
policy-neutral (`effective-rate:sending:<link>` and
`effective-rate:receiving:<link>`); policy/configuration identities still
distinguish V2 and a future policy. V1 and V2 use the same compiler package and
executable semantic hash, so runtime choice does not rewrite provenance.

## Analytical validation

Under saturated permanent green, V1 and V2 both produce 20, 32, 40, 60, 80,
and 120 packets over 80 ticks at 0.25, 0.40, 0.50, 0.75, 1.00, and 1.50
packets/tick.

For 0.25 packets/tick under GGRR, V1 retains phase-dependent results of 0 or
40 services over 160 ticks. V2 produces exactly 20 at every tested offset
`0,1,2,3,5,10`, or 0.125 packets/tick. The rational phase-lock collapse is
eliminated, with zero finite-horizon count variation in this fixture.

Long-red and short-red tests prove that red adds nothing, creates no reopening
burst, and does not reset a partial fraction. Idle-green testing proves that no
eligible demand adds nothing. Mixed-movement tests across all representations
prove one-account ownership and red exclusion. The unchanged V1 GGRR
physical/evidence fingerprint is
`1f5c54c89b67e922adf82a4737df2e9bcd924fcdbf1ed2116340acb0ef7d5b19`.

## Controlled Boreenmanna comparison

The V1/V2 comparison holds pinned OSM, compilation, physical assumptions,
synthetic controller/demand, seed, representation, horizons, and drain policy
fixed. Executable semantic hash:
`db59ef926cebf67e32090a31955c6cd8471b545e4bace571f56031998173f3aa`.
This remains a synthetic experiment on real OSM-derived geometry, not real
junction validation.

| Demand | Representation | V1 complete | V2 complete | V1 delay | V2 delay | Eventual | Final tick |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Moderate | Explicit groups | 28 | 28 | 11.455 | 10.690 | 28 | 109 |
| Moderate | Movement partial | 28 | 28 | 12.897 | 13.450 | 28 | 109 |
| Moderate | Shared strict | 17 | 17 | 17.000 | 17.217 | 28 | 189 |
| Stress | Explicit groups | 60 | 60 | 13.071 | 11.897 | 84 | 269 |
| Stress | Movement partial | 60 | 60 | 15.338 | 15.158 | 84 | 269 |
| Stress | Shared strict | 35 | 35 | 18.245 | 17.682 | 84 | 509 |

V2 changes timing and mean delay modestly, but not zero-offset evaluation
completion, eventual completion, or clearance. All packets clear, so original
incompleteness remains genuine evaluation-horizon congestion rather than loss.

Across offsets `0,1,2,5,10`, V2 completion ranges are 0, 0, and 1 packet for
moderate explicit, partial, and shared cases; stress ranges are 3, 3, and 0.
Clearance ranges are 10--15 ticks and mean-delay ranges are 0.76--2.32 ticks.
V2 removes analytical rational phase lock, not ordinary finite-horizon signal
offset sensitivity. All ten parity families validate with only representation
fields differing.

## Performance and forensic cost

Core first-run wall time was 6.77--63.98 seconds, replay 0.82--6.97 seconds,
and peak Python memory 39.4--149.1 MB on the recording machine. The six-core
plus 30-offset sweep took 919.6 seconds. These measurements are machine
dependent and excluded from deterministic identities.

Core evidence contains 5,280--22,396 credit records and 17.9--47.0 MB of
deterministic forensic artefacts per run. Like V1, it scales primarily with
`ticks × links × two accounts`; V2 records are wider because they expose the
generic effective-rate components. A future compact publication mode can
hash-anchor streams and retain selected records/aggregates. Current forensic
records remain required for exact validation.

Comparison deterministic hash:
`76a812ad0a1000ba4abf8f7e2de4fae122dff2b6c341df7385676a25b26a4db7`.
Package hash including performance:
`4491ca670237f3ea00898dedbcca07cf3738def8c1369a4ca9c872cd960152ac`.

## V3 readiness compatibility

V3 can reuse V2's service domain/account identity, effective-rate evaluator,
fractional accumulator, whole exposure/expiry, allocator and physical path,
generic evidence shape, replay integration, and manifest structure. It needs
to add only:

- versioned readiness parameters and configuration;
- per-service-domain readiness state;
- deterministic red-decay/green-recovery transitions;
- a multiplier provider returning the current value in `[0,1]`;
- readiness-transition evidence linked to the generic rate record.

The accumulator consumes an `EffectiveRateServiceConfig` protocol and a
`ServiceRateMultiplierProvider`; V2 is a thin constant-one adapter. V3 does not
need to replace accumulation or execution machinery. It must still justify
whether empirical readiness belongs at link, lane-group, or another domain;
V2 deliberately does not invent that state.

The implemented V3 architecture and validation are documented in
`discharge_readiness_fractional_service_v3.md`.

## Limitations

Demand relevance is a link-level approximation where capacity is link-level
but signal permission is movement-level. Cork control, demand, and detailed
lane bindings remain synthetic. Static rates only are tested. The smaller
junction remains synthetic OSM-like evidence; a second pinned real
unsignalised export is still required. Nothing here supports field accuracy,
calibration, or representation superiority at real Boreenmanna.
