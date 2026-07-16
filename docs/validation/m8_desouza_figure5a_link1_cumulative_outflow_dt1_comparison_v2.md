# M8 de Souza Figure 5(a) Link 1 cumulative outflow DT=1 comparison v2

Status: improved digitisation compared observationally. The v1 reference and
outputs remain preserved. No UC evidence was rerun or changed.

## Method

The 68 supplied v2 points are preserved verbatim in
`data/validation/desouza_figure5a_link1_cumulative_outflow_digitised_v2.csv`.
They are treated as Link 1 cumulative outflow because the curve begins after
the link free-flow lag. UC uses the existing persisted
`l1_cumulative_outflow` series.

The comparison uses exact UC integer-second observations from 8 through 146 s.
Only the digitised reference is piecewise-linearly interpolated. There is no
UC interpolation, extrapolation, smoothing, fitting, shifting, or point
adjustment. Difference is `UC - digitised reference`.

## Results

| Measure | v2 result | v1 result |
| --- | ---: | ---: |
| Maximum absolute difference | 5.195908 at 141 s | 4.932058 at 133 s |
| Mean absolute difference | 1.995476 | 2.162683 |
| RMSE | 2.381686 | 2.523922 |
| First abs. difference > 0.5 | 11 s | 11 s |
| First abs. difference > 1 | 37 s | 13 s |
| First abs. difference > 2 | 69 s | 43 s |
| Final difference | -3.034844 at 146 s | -3.461707 at 146 s |

The improved digitisation reduces average error and moves the 1- and 2-packet
crossings later. It does not remove the negative outflow discrepancy. Its
largest local deviation is slightly greater and occurs later.

## Regions

| Region | Max abs. difference | MAE | RMSE | Mean signed difference |
| --- | ---: | ---: | ---: | ---: |
| Initial, 8-49 s | 1.834404 | 0.627104 | 0.807234 | -0.570170 |
| Transition, 50-60 s | 1.737618 | 1.173387 | 1.209662 | -1.173387 |
| Post-transition, 61-146 s | 5.195908 | 2.768902 | 2.943268 | -2.768902 |

After 61 s the signed difference slope is -0.033045 packets/s and the endpoint
change is -1.290260 packets. The revised difference still exhibits negative
drift with packet-scale oscillation.

## Event diagnostics

- At 11 s, the first 0.5-packet exceedance is -0.543677. UC has three L1
  exits. `P4` queues at tick 11 and exits L1 at tick 12.
- At 37 s, the first 1-packet exceedance is -1.396224. UC has 15 exits. `P16`
  entered the boundary queue at tick 35 and exits L1 at tick 38.
- At 69 s, the first 2-packet exceedance is -2.225394. UC has 30 exits. `P31`
  entered the boundary queue at tick 67 and exits L1 at tick 70.
- At 141 s, the maximum is -5.195908. UC has 64 exits. `P65` enters the
  boundary queue at tick 141 and exits L1 at tick 142. The maximum also lies
  immediately after the reference's steep 136-140 s segment; both facts are
  observed, but the available evidence does not identify causation.
- At 146 s, UC has 67 exits and the reference interpolation is 70.034844.

## Reference quality and classification

The v2 digitisation contains two retained decreases of 0.013111 packets,
near 80 s and 110 s. Its last supplied value is 70.040432 packets, much closer
to the declared 70-packet integrated demand than v1 but still slightly above
it.

- **Implementation assumption:** integer unit packets, fractional capacity
  carry, and current queue/movement event ordering.
- **Digitisation uncertainty:** non-integer extracted coordinates, the two
  cumulative decreases, sparse late segments, and the small final overrun.
- **Possible kernel discrepancy:** not established. The cross-model outflow
  difference persists, but UC's cumulative series matches its canonical event
  history.
- **Unknown:** paper-side fractional-capacity, packet release, and within-tick
  ordering conventions.

No correction is attempted.

## Artifacts

`outputs/validation/m8_desouza_figure5a_link1_cumulative_outflow_dt1_comparison_v2/`
contains the overlay, difference plot, interpolated comparison series, and
machine-readable summary.
