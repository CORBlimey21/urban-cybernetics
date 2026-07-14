# M8 Analytical Link Cases v1

Status: first independent-oracle fixtures for M8 external scientific
validation. These cases are implemented and executable, but they are not by
themselves an external cross-implementation validation.

Executable fixtures:
`tests/external_validation/test_m8_analytical_link_cases.py`.

## Oracle Independence

Expected cumulative curves, exit ticks, queue curves, delays, and vacancy
availability are literal fixture tables in the test module. They are not
generated with UC loading, cumulative-count, spillback, or validation helpers.
UC executes each case. Observations are then folded directly from the
engine-owned canonical event log. Existing materialised counts, queues, caches,
and indexes may be checked separately, but none serves as the expected oracle.

## Equations and Convention

All cases use unit packets, one lane, SI physical units, and a triangular
fundamental diagram:

```text
q = 3.6*v*w*kj/(v+w)
c = q*dt/3600
tau = ceil((L/v)/dt)
omega = ceil((L/w)/dt)
K = floor((L/1000)*lanes*kj)
Q(t) = max(Nin(t-tau) - Nout(t), 0)
R(t) = min(c, K + Nout(t-omega) - Nin(t))
delay_i = exit_tick_i - entry_tick_i - tau
```

Here `L` is metres, `v` and `w` are metres/second, `kj` is
vehicles/kilometre/lane, `q` is vehicles/hour/lane, `c` is unit packets per
tick, and `dt` is seconds/tick. `Nin(t)` and `Nout(t)` include events at
physical tick `t`. Negative-time cumulative counts are zero. Lag rounding is
ceiling division; storage is rounded down. All count and tick comparisons are
exact (`0` packet and `0` tick tolerance). The only floating comparison is a
reported mean delay, with absolute tolerance `1e-12` ticks.

The tick-0 pulses are explicit fixture initial conditions admitted through the
origin boundary. Their origin admission budgets are declared separately from
the link's downstream sending capacity: 4 for M8-LINK-01, 5 for M8-LINK-02,
and 3 for the initial downstream preload in M8-LINK-03. This distinction is an
input convention, not a UC-derived oracle.

For a single link, `Q(t)` is the exit-boundary point queue implied by cumulative
curves. It is not a second physical state. Canonical `QUEUE_ENTRY` and
`QUEUE_EXIT` events describe failed inter-link transfers and are therefore
expected only in the two-link vacancy case.

## M8-LINK-01 — Uncongested Single-Link Translation

Inputs: `L=200 m`, `v=10 m/s`, `w=5 m/s`, `dt=10 s`, `kj=120
veh/km/lane`, `q=1440 veh/h/lane = 4 packets/tick`, `K=24 packets`, and
three packets entering at tick 0 through a four-packet origin admission budget.
Thus `tau=2` and `omega=4`.

| Tick | 0 | 1 | 2 | 3 |
| --- | ---: | ---: | ---: | ---: |
| Expected cumulative entries | 3 | 3 | 3 | 3 |
| Expected cumulative exits | 0 | 0 | 3 | 3 |
| Expected point queue | 0 | 0 | 0 | 0 |

Expected packet exit ticks are `(2, 2, 2)`. The finite inflow pulse is below
the four-packet/tick capacity. The case checks exact free-flow translation, no
queue events, no point queue, final conservation, and completion.

## M8-LINK-02 — Capacity-Constrained Single Link

Inputs: `L=200 m`, `v=10 m/s`, `w=5 m/s`, `dt=10 s`, `kj=30
veh/km/lane`, `q=360 veh/h/lane = 1 packet/tick`, `K=6 packets`, and five
packets entering as an explicit tick-0 initial pulse through a five-packet
origin admission budget. Thus `tau=2` and `omega=4`.

| Tick | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Expected cumulative entries | 5 | 5 | 5 | 5 | 5 | 5 | 5 |
| Expected cumulative exits | 0 | 0 | 1 | 2 | 3 | 4 | 5 |
| Expected point queue | 0 | 0 | 4 | 3 | 2 | 1 | 0 |

Expected exit ticks are `(2, 3, 4, 5, 6)` and experienced delays above free
flow are `(0, 1, 2, 3, 4)` ticks, with mean `2.0` ticks. The case checks
queue formation, one-packet/tick discharge, complete queue dissipation,
cumulative curves, delay, conservation, and completion.

## M8-LINK-03 — Backward-Wave Vacancy Propagation

Inputs for both links: `L=40 m`, `v=10 m/s`, `w=5 m/s`, `dt=4 s`,
`kj=75 veh/km/lane`, `q=900 veh/h/lane = 1 packet/tick`, `K=3 packets`,
`tau=1`, and `omega=2`. Three packets fill downstream link `L2` at tick 0;
the preload uses a three-packet origin admission budget. One packet on `L1`
requests transfer to `L2`.

| Tick | 0 | 1 | 2 | 3 |
| --- | ---: | ---: | ---: | ---: |
| Expected L2 cumulative entries | 3 | 3 | 3 | 4 |
| Expected L2 cumulative exits | 0 | 1 | 2 | 3 |
| Expected pre-accept vacancy | 0 | 0 | 0 | 1 |
| Expected cumulative boundary queue entries | 0 | 1 | 1 | 1 |
| Expected cumulative boundary queue exits | 0 | 0 | 0 | 1 |

The first downstream exit occurs at tick 1. With `omega=2`, that vacancy is
not available at the upstream boundary at ticks 1 or 2 and becomes available
at tick 3. The upstream packet must enter `L2` at tick 3 exactly. The case
checks public receiving supply while blocked, independently calculated
pre-accept vacancy, canonical boundary queue events, resumed movement timing,
and conservation inequalities.

## Claim Boundary

Passing these fixtures supports the narrow claim that the current discrete
unit-packet kernel matches these three independently specified analytical
tables under the declared UC timestep convention. It does not establish
academic LTM parity, empirical realism, calibration, node-model validity,
network-scale numerical agreement, or production readiness.
