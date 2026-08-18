# Discharge-readiness fractional service V3

## Scientific scope

`uc.discharge-readiness-fractional-service.v3` is an opt-in mesoscopic
runtime policy above the unchanged loading kernel. It reuses V2's service
accounts, fractional accumulator, whole-opportunity expiry, allocator,
physical execution, replay path, and generic effective-rate evidence. V1 and
V2 remain unchanged comparators.

V3 separates three quantities that must not be conflated:

1. the Boolean signal/control gate;
2. bounded discharge readiness `r` in `[0, 1]`;
3. fractional service credit.

Readiness describes whether a queued discharge stream retains established
saturation-flow conditions. It is neither signal permission nor stored
capacity. The policy is an experimental first-order approximation grounded in
startup-loss concepts; it is not field-calibrated for Boreenmanna.

## Ownership and eligible demand

Readiness belongs to the existing physical upstream-link sending account.
That is the finest current domain that does not manufacture a full capacity
copy per movement. A controlled link recovers when at least one currently
relevant movement is green or uncontrolled and decays when all relevant
movements are red. The ordinary FIFO, lane-group, signal, conflict,
governance, and allocation machinery still decides which request can consume
the one shared budget.

This loses distinct restart histories for differently controlled movements
sharing a link. Finer ownership would require evidenced lane-group or
movement saturation-flow shares and corresponding non-duplicating resource
accounts. V3 does not invent them.

Eligible demand means a packet at the link's downstream decision boundary,
free-flow eligible at the current tick, with a next discharge movement. It is
evaluated before allocation to avoid circular dependence. If no such demand
exists, readiness resets deterministically to `1.0`: there is no standing
queue whose stopped state should be remembered. This immediate reset is
deliberate and contains no hidden hysteresis.

Uncontrolled domains use multiplier `1.0` and retain no V3 readiness state.

## Exact continuous-time recurrence

For tick duration `dt`, opening readiness `r0`, green recovery time `tau_g`,
and red decay time `tau_r`:

During a demanded red interval:

```text
r1 = r0 exp(-dt / tau_r)
gate = 0
effective allowance = 0
```

For infinite `tau_r`, `r1 = r0`. Existing fractional credit is preserved,
but red creates no new entitlement.

During a demanded green interval:

```text
r1 = 1 - (1 - r0) exp(-dt / tau_g)
mean_r = 1 - (1 - r0) (tau_g / dt) (1 - exp(-dt / tau_g))
effective allowance = base allowance × mean_r
```

`mean_r` is the exact interval mean, not the end-of-tick value. Transition
factors and the green integral coefficient are precomputed for each fixed
tick-duration/parameter combination.

The unchanged V2 accumulator then applies:

```text
available = opening_fraction + effective_allowance
whole_exposed = floor(available)
closing_fraction = available - whole_exposed
expired_whole = whole_exposed - physically_consumed
```

Unused whole opportunity expires after an enabled tick. Thus receiving
closure, conflict, FIFO blockage, an empty queue, or a losing shared request
cannot bank an unlimited reopening burst. Receiving credit is not multiplied
by signals or readiness; downstream supply keeps its separate bounded V1/V2
recurrence.

Initial readiness is explicit in the physical runtime configuration, either
per controlled link or through a deterministic default. Boreenmanna uses
`1.0`.

## Parameters and startup loss

Parameters are seconds, not per-tick percentages. The Boreenmanna baseline is
`tau_green_seconds = 2.0` and illustrative
`tau_red_seconds = 10.0`. Neither is OSM-derived, observed, or calibrated.
The experiment tests green values 1, 2, and 3 seconds, plus red values 2, 5,
10, 20, and 40 seconds and infinity.

For a fully stopped stream under continuous green, integrated lost readiness
after duration `T` is `tau_g (1 - exp(-T/tau_g))`, approaching `tau_g` seconds
as `T` grows. Exact tests at 0.5, 1, and 2 second ticks reproduce the same
continuous trajectory at common physical times; residual service-count
differences are whole-packet quantisation, not readiness integration error.

Permanent green with initial readiness 1 exactly matches V2 for 0.25, 0.40,
0.50, 0.75, 1.00, and 1.50 packets/tick. Infinite red memory with initial
readiness 1 also matches V2 physical events across tested signal offsets.

For 0.25 packets/tick under GGRR over 320 ticks, V1 retains its legitimate
clock-phase alternatives (0 or 80 services), V2 serves 40 at every cycle
offset, and baseline V3 serves 33 at every cycle offset. V3 therefore retains
gate-aware accrual, adds restart loss, and does not reintroduce V1's
zero-service rational phase lock.

## Boreenmanna controlled ablation

All runs use the same pinned OSM geometry, reviewed physical assumptions,
synthetic controller, synthetic demands, routes, seeds, tick duration,
horizons, drain policy, and representation parity manifests. Only the runtime
policy/parameters differ. This is not validation of actual Boreenmanna
traffic.

| Demand | Representation | V2 eval | V3 eval | V2 delay | V3 delay | V2/V3 eventual | V2 final | V3 final |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Moderate | Explicit groups | 28 | 28 | 10.690 | 11.107 | 28 | 109 | 110 |
| Moderate | Movement partial | 28 | 28 | 13.450 | 13.762 | 28 | 109 | 110 |
| Moderate | Shared strict | 17 | 17 | 17.217 | 17.850 | 28 | 189 | 189 |
| Stress | Explicit groups | 60 | 60 | 11.897 | 13.042 | 84 | 269 | 270 |
| Stress | Movement partial | 60 | 60 | 15.158 | 15.286 | 84 | 269 | 270 |
| Stress | Shared strict | 35 | 35 | 17.682 | 18.333 | 84 | 509 | 510 |

The baseline adds modest delay and at most one clearance tick while preserving
evaluation completions, eventual completions, and representation ordering.
Across the bounded sensitivity sweep, all packets eventually clear. Shared
strict FIFO completion and clearance are unchanged. The explicit lane-group
case is most sensitive: fast red decay can reduce evaluation completions by
one moderate packet or two stress packets and extend final clearance by up to
18 ticks. Infinite red memory reproduces V2 readiness and outcomes.

Thus V3 earns a clearer restart-loss interpretation and analytical behavior,
but it does not overturn the controlled representation conclusion. Its
parameter sensitivity remains experimental evidence, not calibration.

## Evidence modes and performance

The physical configuration hash includes policy version, ownership, time
constants, initial state, eligibility rule, integration convention,
accumulator/expiry rule, receiving rule, and tick duration. Recording mode has
a separate hash and cannot change physical identity.

- `forensic` retains every generic service and readiness transition record.
- `compact` retains checkpoints, transition changes, and
  exposure/consumption/expiry activity.
- `summary` retains aggregate per-domain statistics only.

All modes compute the same streaming SHA-256 digest over the complete logical
evidence sequence. Exact reruns reproduce both this digest and physical
events. For the explicit-lane-group benchmark, moderate replay artefacts were
10.04 MB forensic, 2.43 MB compact, and 0.70 MB summary; stress artefacts were
23.84 MB, 7.79 MB, and 2.51 MB. Peak traced memory fell from 45.1 to 24.7 MB
moderate and from 99.4 to 30.2 MB stress between forensic and summary.

On the recording machine after the two memoization patches, V3
forensic/compact/summary wall times were 3.33/2.26/2.06 seconds moderate and
7.70/5.57/4.87 seconds stress. V2 forensic was 3.17 and 7.14 seconds. These are
machine-dependent. Summary mode
still evaluates and hashes the full logical stream, so it measures reduced
retention/serialization rather than physics alone.

Profiling before optimization showed repeated immutable signal-plan hashing,
not readiness arithmetic, dominated representative V2 runs. Memoizing those
unchanged hashes reduced profiled time from 1.050 to 0.584 seconds moderate
and 8.345 to 2.400 seconds stress, without changing event hashes. Remaining
profiling then exposed the same avoidable repetition in V3 configuration
hashes; memoizing those reduced V3 profiled time from 0.949 to 0.627 seconds
moderate and 2.240 to 1.537 seconds stress. Readiness multiplier evaluation
itself consumed only 0.004 and 0.009 seconds, while JSON encoding consumed
0.275 and 0.633 seconds. Remaining cost is dominated by deterministic
JSON/hashing and experiment evidence orchestration. No frozen or canonical
event code changed.

## Limitations

The shared-link readiness domain approximates multi-movement discharge.
Immediate no-demand reset can discard stop history after a one-tick absence;
that is transparent and deterministic but not empirically validated. Time
constants and the exponential form are uncalibrated. Packet quantisation,
synthetic signals/demand, and representation assumptions remain. Evidence
modes reduce retained volume but summary mode is not a no-audit physics
benchmark because it still hashes logical evidence.

V3 adds no microscopic acceleration, reaction-time distribution, stochastic
headway, lane changing, adaptive control, or field calibration.
