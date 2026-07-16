# M8 de Souza Figure 7(a) DT1 comparison v1

Status: observational reproduction complete without calibration. A formal
pass/fail threshold was not fixed before comparison, so no binary numerical
pass is assigned. The result is comparison-complete and internally valid, with
remaining differences classified below.

## Reference integrity and closure gate

The supplied WebPlotDigitizer files are preserved byte-for-byte and in raw
point order:

| Series | Points | SHA-256 | Raw non-increasing time pairs |
| --- | ---: | --- | ---: |
| `Gu` | 220 | `852e02f91f4c1e5b98dc1bd8958f64a3efafcd5eef71f0ed546d2a790a6c2124` | 47 |
| `F1` | 165 | `f1decc34b3baeaf24fc64d8f46fee8eea05dc9a02d563aec78e9c1e1cd81c3d6` | 22 |
| `F2` | 113 | `8c40ab91eb62c5ca44c4f5e5a7e5c746beb9fd974b1427551bfc7a06582144cd` | 26 |

Analysis uses a stable ascending time sort, retaining supplied order for equal
times. There are no duplicate times. No value is averaged, smoothed,
monotonicised, fitted, shifted, deleted, or supplemented with an origin.

On the shared 9–119 s integer grid, the digitisation closure residual
`Gu-F1-F2` is:

| Measure | Vehicles |
| --- | ---: |
| MAE | 0.495554 |
| RMSE | 0.653678 |
| Maximum absolute residual | 1.820014 at 20 s |
| Signed bias | -0.109943 |
| Endpoint residual | -0.397159 |

The reference curves therefore carry material extraction/sampling uncertainty
at roughly half a vehicle on average and occasionally nearly two vehicles.
Simulator differences are interpreted only after this closure limitation.

## UC comparison

Each reference is piecewise-linearly interpolated onto exact UC integer-second
observations over that reference's actual support. UC is not interpolated and
no extrapolation is performed. Difference means `UC - digitised reference`.

| Series | Support | Max abs. difference (time) | MAE | RMSE | First >0.5 / >1 / >2 s | Final signed difference | Signed slope veh/s |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| `Gu` | 9–119 s | 2.622989 (46 s) | 0.843911 | 1.080706 | 9 / 9 / 38 | -0.671649 | +0.000477 |
| `F1` | 7–119 s | 1.795374 (62 s) | 0.708540 | 0.852827 | 11 / 32 / never | -0.589341 | -0.003936 |
| `F2` | 9–119 s | 1.095461 (41 s) | 0.368183 | 0.495265 | 9 / 21 / never | -0.479466 | +0.000351 |

The near-zero whole-support slopes show bounded, oscillatory differences rather
than accumulating drift. `F2` is within the reference closure RMSE, while the
larger `Gu` and `F1` differences include both digitisation uncertainty and
timing/convention differences.

## Regional statistics

| Series / region | Max abs. | MAE | RMSE | Mean signed |
| --- | ---: | ---: | ---: | ---: |
| `Gu`, before change | 2.622989 | 0.790605 | 0.994474 | -0.591856 |
| `Gu`, after change | 2.622046 | 0.875134 | 1.128157 | -0.873771 |
| `F1`, before change | 1.703412 | 0.583660 | 0.716593 | -0.407014 |
| `F1`, after change | 1.795374 | 0.785252 | 0.926636 | -0.761722 |
| `F2`, before change | 1.095461 | 0.373725 | 0.492509 | -0.196278 |
| `F2`, after change | 1.091738 | 0.364937 | 0.496872 | -0.275557 |

“Before” ends at 49 s. “After” begins at 50 s and includes the existing
Figure 5-style 50–60 s transition window; the machine-readable summary also
reports that window and the 61 s onward region separately.

## Read-only first-divergence audit

- At 7 s, `P1` is the first UC upstream exit and enters `L2`, after its
  tick-2 admission and frozen five-tick free-flow lag. The `F1` reference at
  7 s is 1.416 vehicles versus UC 1, below the 0.5-vehicle threshold.
- At 9 s, UC closure is exactly `Gu=3=F1(3)+F2(0)`. The references are
  `Gu=4.028`, `F1=2.748`, and `F2=0.739`, with their own +0.541 closure
  residual. Thus the first `Gu`/`F2` threshold crossings are not a coherent
  conserved reference state and cannot identify a kernel divergence.
- At the maximum `Gu` difference at 46 s, UC has 26 upstream transfers versus
  28.623 interpolated. `P27` enters the strict-FIFO `L1→L2` boundary queue on
  that tick while `P23` exits `L2`. Reference closure is only +0.045 vehicles
  there, and the corresponding `F1`/`F2` differences sum to -2.578 vehicles.
  This is a genuine cross-model timing difference around branch-specific
  receiving availability, but the paper does not expose its departure phase,
  initial capacity credit, or same-tick ordering trace.
- The discrepancy later contracts: by 119 s UC/reference differences are
  -0.672 (`Gu`), -0.589 (`F1`), and -0.479 (`F2`). No persistent drift or
  conservation loss appears.

No parameter or kernel change is justified. The remaining difference is
classified as digitisation uncertainty plus implementation/unknown paper
timing conventions. A possible kernel discrepancy is not established.

## Exact UC gates

- `Gu=F1+F2` at every UC tick; maximum residual is exactly zero;
- all 68 packet routes preserve the exact repeating `L2,L2,L2,L3` sequence
  (51 packets to `L2`, 17 to `L3`);
- the 66-packet transferred prefix is exactly 50 to `L2` and 16 to `L3`;
- FIFO transfer order, packet identity, canonical event ordering, conservation,
  event-cache consistency, cumulative-count consistency, physical eligibility,
  and deterministic replay all pass;
- the frozen loading kernel is unchanged.

## Reproducible artifacts

Run `python scripts/compare_desouza_figure7a_dt1.py`. Ignored generated outputs
under `outputs/validation/m8_desouza_figure7a_dt1_comparison_v1/` are:

- `summary.json`;
- `digitisation_closure.csv`;
- `Gu_comparison_series.csv`, `F1_comparison_series.csv`, and
  `F2_comparison_series.csv`;
- `overlay.png` and `difference.png`.

The raw CSVs, comparison tool, focused tests, this report, and validation
register updates are source-controlled evidence. Generated plots and expanded
comparison series remain reproducible local outputs.
