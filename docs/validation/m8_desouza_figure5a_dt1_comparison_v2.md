# M8 de Souza Figure 5(a) DT=1 comparison v2

Status: observational retry completed using the second supplied digitisation.
The UC evidence, comparison definitions, and 2-145 s evaluation grid are
identical to v1. No simulation was rerun or modified.

## Source integrity and method

The 71 supplied v2 points are preserved verbatim in
`data/validation/desouza_figure5a_cumulative_inflow_digitised_v2.csv`. Their
times are strictly increasing and their cumulative values contain no decrease.

As in v1, the digitised curve is piecewise-linearly interpolated onto UC's
exact integer-second observations. UC is not interpolated and no extrapolation
is performed. Although v2 extends beyond the old support, the comparison is
fixed to 2-145 s so its 144 samples are directly comparable with v1.

## Results

| Measure | v2 | v1 | v2 minus v1 |
| --- | ---: | ---: | ---: |
| Maximum absolute difference | 2.160546 | 1.799111 | +0.361435 |
| Mean absolute difference | 1.125466 | 0.861127 | +0.264339 |
| RMSE | 1.304916 | 0.988138 | +0.316778 |
| Final difference at 145 s | -1.352852 | -0.790447 | -0.562406 |

Threshold crossings in v2 are 32 s for 0.5 packets, 34 s for 1 packet, and
68 s for 2 packets. The maximum occurs at 144 s.

The second digitisation is not quantitatively closer to the unchanged UC
series under the same comparison method. Its first 0.5-packet threshold is
later, but every aggregate error measure is larger and it introduces
greater-than-two-packet differences.

## Regional observations

| Region | Max abs. difference | MAE | RMSE | Mean signed difference |
| --- | ---: | ---: | ---: | ---: |
| Initial, 2-49 s | 1.505761 | 0.425079 | 0.565195 | -0.251500 |
| Transition, 50-60 s | 1.030475 | 0.551914 | 0.641690 | -0.522006 |
| Low demand, 61-145 s | 2.160546 | 1.595202 | 1.628211 | -1.595202 |

After 61 s, the signed-difference slope is -0.003801 packets/s and its endpoint
change is -0.248879 packets. The difference remains bounded and sawtoothed,
with a modest negative trend rather than unbounded accumulation.

## Evidence trace

- At 32 s, the first 0.5-packet exceedance coincides with `P14` transferring
  from L1 to L2 and no new origin entry. L1 cumulative inflow remains 31.
- At 34 s, the first 1-packet exceedance coincides with `P15` transferring and
  no new origin entry. L1 cumulative inflow remains 32; `P33` enters at 35 s.
- At 68 s, the first 2-packet exceedance occurs with 48 L1 entries. The only
  events are `P28` exiting L2 and completing; `P49` enters L1 at 69 s.
- At 144 s, the maximum difference occurs with 68 L1 entries. `P66` transfers
  to L2 and `P63` completes; no origin entry occurs. `P69` enters at 145 s.

These points again align with the visible discrete origin-admission pattern.
The paper-side release and within-tick ordering conventions remain unknown.
No kernel discrepancy is established by the comparison.

## Artifacts

Outputs are under
`outputs/validation/m8_desouza_figure5a_dt1_comparison_v2/`:

- `overlay.png`;
- `difference.png`;
- `comparison_series.csv`;
- `summary.json`.
