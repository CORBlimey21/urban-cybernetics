# de Souza Figure 9(a–c): equal-priority merge validation

## Technical summary

The frozen Urban Cybernetics loading kernel reproduces the paper's qualitative
equal-priority merge behaviour and passes every exact internal gate. With
`α1=0.5` and priority sequence `[0,1]`, the two constrained upstream approaches
receive equal service to unit-packet precision (7 versus 6 approved packets
through `t=40`), downstream closure is exact at every tick, both upstream
queues are retained and later discharged, FIFO and packet identity hold, and
canonical replay is byte-for-byte identical.

The four requested scalar comparison families are reported below for the two
Figure 9(a) digitised traces. Differences are material: maximum absolute
differences are 4.112 vehicles for `G1` and 3.136 for `G2`. A read-only
first-divergence audit therefore ran before any change was considered. It finds
an unknown published departure/initial-credit phase at the start of support and
substantial digitisation artifacts, including seven decreasing `G2` segments.
No demand, priority, capacity, timing, reference point, or kernel semantic was
changed.

## The equal merge is observationally aligned but phase-shifted

The thick curves below are the untouched digitised references after stable
time sorting for analysis only; thin staircases are event-derived UC counts.
The curves show the same equal-service regime and post-change redistribution,
but UC begins later and trails during queue discharge.

![Equal-priority cumulative overlay](../../outputs/validation/m8_desouza_figure9a_equal_v1/overlay.png)

| Series | Support (s) | Max abs. difference (time) | MAE | RMSE | First >0.5 / >1 / >2 (s) | Final signed difference | Signed-difference slope |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| `G1` | 10–118 | 4.112 (79) | 1.560 | 1.951 | 10 / 43 / 62 | -1.237 | -0.02954 veh/s |
| `G2` | 5–118 | 3.136 (41) | 1.243 | 1.366 | 5 / 5 / 39 | -0.705 | -0.00182 veh/s |

The difference plot exposes the initial phase mismatch, the larger transition
residuals, and the later recovery. Threshold guides are descriptive only; no
threshold was fitted or declared as a pass criterion.

![Equal-priority signed differences](../../outputs/validation/m8_desouza_figure9a_equal_v1/difference.png)

## The t=40 split localizes the larger differences

| Series/region | Samples | Max abs. | MAE | RMSE | Final signed | Slope (veh/s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `G1`, before `t=40` | 30 | 0.909 | 0.363 | 0.462 | +0.066 | +0.02848 |
| `G1`, after `t=40` | 79 | 4.112 | 2.015 | 2.274 | -1.237 | -0.01578 |
| `G2`, before `t=40` | 35 | 2.218 | 0.917 | 1.009 | -2.218 | -0.02199 |
| `G2`, after `t=40` | 79 | 3.136 | 1.388 | 1.498 | -0.705 | +0.01255 |

The `G1` late-after-change mean absolute difference is 2.490 vehicles, but its
signed-difference slope turns positive (`+0.02789 veh/s`), so the discrepancy
recovers rather than growing without bound. The `G2` after-change residual also
recovers from its 41 s maximum toward -0.705 vehicles at the final comparable
tick.

## Exact queue, priority, and closure evidence passes

The fixture inherits the previous validation cases' 150 m link length and uses
the paper-declared `V=30 m/s`, `W=6 m/s`, `K=0.1 veh/m`, `dt=1 s`, and 120 s
horizon. The triangular fundamental diagram gives `C=0.5 veh/s` on every link.
Tick-end floored demand creates 36 link-1 and 20 link-2 packets.

| Evidence | Result |
| --- | --- |
| Constrained service through `t=40` | L1 7, L2 6; equal within one indivisible packet |
| Peak eligible queue before/at `t=40` | L1 2 packets; L2 3 packets |
| Peak eligible queue after `t=40` | L1 4 packets; L2 4 packets |
| Final eligible queues | L1 0; L2 0 |
| Final cumulative counts | `G1=34`, `G2=19`, `F3=53` |
| Downstream closure | `F3(t)=G1(t)+G2(t)` exactly for 121/121 ticks |
| Conservation, FIFO, identity, eligibility | pass |
| Canonical event ordering and replay | pass; 388 events |

After link-2 demand falls, retained link-2 demand continues receiving service
until its backlog reduces. Unused downstream service is then reassigned to
link 1, whose queue also clears by the horizon. This matches the paper's stated
qualitative transition without bypassing FIFO.

## Read-only first-divergence audit finds convention and digitisation effects

The earliest `|difference|>0.5` occurs at 5 s for `G2`: the digitised reference
is 1.015 vehicles while UC has no physically eligible packet. Under UC's
unchanged tick-end floor convention the first 0.3 veh/s packet is released at
tick 4 and becomes eligible after the inherited five-second free-flow lag. The
paper does not state its fractional-demand release phase or initial packet
placement, so this is an unknown paper convention.

The first differences above two vehicles occur at 39 s (`G2`) and 62 s (`G1`).
At both ticks UC has retained upstream queues and exact downstream closure; the
selected source simply receives the next permitted integer service. Reference
quality also limits interpretation:

- the `G2` trace has seven decreasing segments despite being cumulative;
- both traces contain one local segment steeper than the physical 0.5 veh/s
  link capacity;
- `G2` falls from 10.358 to 9.512 vehicles across two nearby 41 s points;
- the raw references contain no synthetic origin or explicit packet-release
  phase, as required.

Classification: `unknown paper convention` for initial fractional-demand and
capacity-credit phase, plus `digitisation uncertainty` for locally nonphysical
reference geometry. The audit finds no evidence of a kernel discrepancy because
all physical and semantic invariants pass and the residuals recover.

## Method and preserved evidence

Each raw CSV is committed byte-for-byte from the supplied archive. Analysis
uses a stable ascending time sort and piecewise-linear interpolation of the
reference onto integer-second UC observations. UC is never interpolated and no
extrapolation is allowed. Each series is compared only on its own support. Raw
duplicate-time order would be retained; this pair has no duplicate times.

Machine-readable artifacts are:

- `data/validation/desouza_figure9a_equal_uc_evidence_v1.json`;
- `data/validation/desouza_figure9a_equal_comparison_summary_v1.json`;
- the two untouched digitised CSVs under `data/validation/`;
- per-series comparison CSVs and both PNGs under the ignored
  `outputs/validation/m8_desouza_figure9a_equal_v1/` directory.

Regenerate with `python scripts/run_desouza_figure9_equal.py`. Focused tests
fix the paper parameters, priority contract, raw hashes, numerical metrics,
queue/service evidence, closure, conservation, identity, event ordering, and
replay.

## Limitations and next step

This is an observational reproduction, not a fitted numerical pass. It
validates one equal-priority merge under UC's already frozen packet-release and
bounded-deficit allocation conventions. It does not establish equivalence for
every merge model or resolve paper-silent initialization details.

The next bounded step is Figure 9(d–f) using the independently resolved
`α1=0.75`, `[0,0,0,1]` interpretation. Any distinct discrepancy will receive
the same read-only audit before semantic changes are considered.
