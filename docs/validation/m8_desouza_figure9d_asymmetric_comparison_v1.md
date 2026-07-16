# de Souza Figure 9(d–f): asymmetric-priority merge validation

## Technical summary

The frozen Urban Cybernetics loading kernel observationally reproduces the
paper's higher-priority-link-1 merge behaviour and passes every exact internal
gate. The intended convention is `α1=0.75`, not `0.25`: the printed panel
labels, stated higher-priority behaviour, merge algorithm, and later freeway
example all pair the sequence `x=[0,0,0,1]` with a three-to-one link-1 share.
The conflicting `0.25` mentions in the section body and caption are recorded
as a paper transcription inconsistency in both machine-readable artifacts.

While both approaches are constrained through `t=40`, UC allocates 8 of 11
indivisible service packets to link 1 (72.7%, within one packet of 75%). The
disadvantaged link-2 eligible queue reaches five packets versus two on link 1.
After link-2 demand falls, both retained queues discharge by the horizon.
Closure `F3(t)=G1(t)+G2(t)` holds exactly for all 121 ticks, and conservation,
FIFO, identity, physical eligibility, event ordering, and replay all pass.

## Priority interpretation is resolved before simulation

The paper is internally inconsistent. Two prose locations print `α1=0.25`,
but the following independent signals establish the intended convention:

- Figure 9(d–f) itself labels the case `α1=0.75`, `x=[0,0,0,1]`;
- the accompanying prose says link 1 has higher priority and explicitly uses
  `α1=0.75` when describing the result;
- Equation (5) uses `αp` as approach `p`'s downstream-supply share, so `α1`
  denotes link 1's share rather than link 2's;
- the merge algorithm defines repeated entries in `x` as repeated priority
  opportunities, making `[0,0,0,1]` a 3:1 allocation to zero-based link 0;
- the later freeway case again pairs a 0.75 mainline share with
  `[0,0,0,1]`.

UC therefore maps the paper sequence to `(L1,L1,L1,L2)` and the frozen
kernel's existing merge weights to `L1:L2 = 3:1`. No probability, priority,
demand, timing, capacity, reference point, or loading semantic was tuned.

## Cumulative curves reproduce the asymmetric regime with phase residuals

The thick curves below are the supplied raw digitisation after stable sorting
by time for analysis only; thin staircases are event-derived UC counts. Both
show link 1 receiving the greater cumulative service and link 2 retaining the
larger backlog.

![Asymmetric-priority cumulative overlay](../../outputs/validation/m8_desouza_figure9d_asymmetric_v1/overlay.png)

| Series | Support (s) | Max abs. difference (time) | MAE | RMSE | First >0.5 / >1 / >2 (s) | Final signed difference | Signed-difference slope |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| `G1` | 10–119 | 3.104 (41) | 1.212 | 1.351 | 10 / 15 / 38 | -1.290 | -0.00010 veh/s |
| `G2` | 8–118 | 3.480 (83) | 1.691 | 1.925 | 8 / 13 / 47 | -0.355 | -0.01710 veh/s |

The difference plot is descriptive. The published paper declares no numerical
tolerance for digitised pixels, so no threshold was fitted as a pass rule.

![Asymmetric-priority signed differences](../../outputs/validation/m8_desouza_figure9d_asymmetric_v1/difference.png)

## The t=40 regional split captures queue redistribution

| Series/region | Samples | Max abs. | MAE | RMSE | Final signed | Slope (veh/s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `G1`, before `t=40` | 30 | 2.479 | 1.004 | 1.156 | -2.479 | -0.02953 |
| `G1`, after `t=40` | 80 | 3.104 | 1.290 | 1.417 | -1.290 | +0.01175 |
| `G2`, before `t=40` | 32 | 1.356 | 0.615 | 0.738 | -0.330 | +0.01220 |
| `G2`, after `t=40` | 79 | 3.480 | 2.127 | 2.233 | -0.355 | -0.00054 |

The link-1 residual peaks just after the demand transition and then recovers.
The link-2 residual peaks later while its disadvantaged queue is being served,
then recovers from -3.480 vehicles to -0.355 at the final comparable tick.

## Exact allocation, queue, and closure evidence passes

The fixture uses three 150 m links, `V=30 m/s`, `W=6 m/s`,
`K1=K2=K3=0.1 veh/m`, `dt=1 s`, and a 120 s horizon. The triangular
fundamental diagram gives `C=0.5 veh/s`. Tick-end floored demand creates 36
link-1 and 20 link-2 packets.

| Evidence | Result |
| --- | --- |
| Constrained service through `t=40` | L1 8, L2 3; 72.7% to L1, within one unit packet of 75% |
| Peak eligible queue before/at `t=40` | L1 2 packets; disadvantaged L2 3 packets |
| Peak eligible queue after `t=40` | L1 2 packets; disadvantaged L2 5 packets |
| Final eligible queues | L1 0; L2 0 |
| Final cumulative counts | `G1=34`, `G2=19`, `F3=53` |
| Downstream closure | `F3(t)=G1(t)+G2(t)` exactly for 121/121 ticks |
| Conservation, FIFO, identity, eligibility | pass |
| Canonical event ordering and replay | pass; 364 events; identical event digest |

The finite 8:3 constrained count reflects indivisible packets and the frozen
bounded-deficit allocator. The absolute deviation from the declared 75% share
is 0.25 packet, satisfying the unit-packet allocation bound. Link 2 retains
the larger queue as expected, while unused service after its demand reduction
allows both approaches to clear without violating FIFO.

## Read-only first-divergence audit

Material differences above two vehicles trigger the required read-only audit.
For `G1`, the first occurs at 38 s and the maximum at 41 s; UC has a retained
queue of one and two packets respectively, exact closure, and no transfer on
those ticks. For `G2`, the first occurs at 47 s with five eligible packets and
the maximum occurs at 83 s with three. These are queue-service phase
differences, not loss or identity failures.

The reference geometry is itself approximate:

- raw `G1` contains four non-increasing adjacent time pairs, retained exactly
  and stable-sorted only for analysis;
- both stable-sorted cumulative traces contain four decreasing segments;
- five `G1` and four `G2` local segments exceed the physical 0.5 veh/s link
  capacity;
- neither trace defines the paper's fractional packet-release phase, initial
  receiving credit, or within-tick priority cursor.

Classification: `digitisation uncertainty` for non-monotone and locally
above-capacity geometry; `unknown paper convention` for departure, credit, and
priority phase; and `implementation convention` for UC's already-frozen
tick-end flooring and bounded-deficit realization of the paper's 3:1 sequence.
There is no evidence of a kernel discrepancy: every exact physical and semantic
invariant passes, the qualitative priority/queue transition is correct, and
both residuals recover. The audit changed nothing.

## Method and artifacts

Both raw CSVs are committed byte-for-byte from the supplied archive. Analysis
stable-sorts by time, retaining duplicate-time order, then linearly
interpolates the reference onto exact integer-second UC observations only over
each trace's actual support. It does not smooth, average, fit, shift,
monotonicise, remove points, add an origin, interpolate UC, or extrapolate.

Machine-readable artifacts are:

- `data/validation/desouza_figure9d_asymmetric_uc_evidence_v1.json`;
- `data/validation/desouza_figure9d_asymmetric_comparison_summary_v1.json`;
- both untouched asymmetric digitised CSVs under `data/validation/`;
- per-series comparison CSVs and both PNGs under ignored
  `outputs/validation/m8_desouza_figure9d_asymmetric_v1/`.

Regenerate with `python scripts/run_desouza_figure9_asymmetric.py`. Focused
tests fix the ambiguity resolution, declared priority, raw hashes, numerical
metrics, allocation and queue evidence, closure, conservation, FIFO, identity,
physical eligibility, canonical ordering, and replay.

## Validation conclusion

Figure 9(d–f) is observationally reproduced under the internally supported
`α1=0.75`, 3:1 convention. This is validation of the named benchmark, not a
claim that digitised pixels form an exact numerical oracle or that all merge
models use the same sub-tick initialization and priority phase.
