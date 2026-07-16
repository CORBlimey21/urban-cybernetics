# M8 de Souza Figure 5(a) Link 1 cumulative outflow DT=1 comparison v1

Status: observational comparison complete. No UC simulation semantics were
modified and the preserved DT=1 preparation run was not rerun.

Superseded for current measurement by the improved digitisation comparison in
`docs/validation/m8_desouza_figure5a_link1_cumulative_outflow_dt1_comparison_v2.md`.
This v1 report and its inputs remain preserved for provenance.

## Quantity identification

The supplied curve is treated as Link 1 cumulative outflow. Its first values
appear after the declared 5 s free-flow travel time, unlike the previously
supplied Link 1 cumulative inflow curve, which begins near time zero. This
identification is explicit; if the points denote another paper quantity, the
comparison mapping must be revised rather than silently reinterpreted.

## Sources and interpolation

- UC source: persisted `l1_cumulative_outflow` from
  `m8-pub-dsouza-fig5-dt1-baseline-v1/result.json`.
- Published reference: 67 supplied points preserved verbatim in
  `data/validation/desouza_figure5a_link1_cumulative_outflow_digitised_v1.csv`.
- Comparison support: exact UC integer-second observations from 8 through
  146 s inclusive, 139 samples.
- Interpolation: piecewise linear interpolation of only the digitised
  reference onto the UC ticks.
- UC interpolation: none.
- Extrapolation, smoothing, fitting, shifting, or point editing: none.
- Signed difference: `UC - digitised reference`.

The digitised cumulative series contains two small decreases of 0.010637
packets, between 79.286-80.116 s and 109.382-110.212 s. They are retained
unchanged and classified as digitisation uncertainty.

## Numerical summary

| Measure | Result |
| --- | ---: |
| Maximum absolute difference | 4.932058 packets at 133 s |
| Mean absolute difference | 2.162683 packets |
| RMSE | 2.523922 packets |
| First absolute difference greater than 0.5 packets | 11 s |
| First absolute difference greater than 1 packet | 13 s |
| First absolute difference greater than 2 packets | 43 s |
| Final common-support difference | -3.461707 packets at 146 s |

## Transition analysis

| Region | Max abs. difference | MAE | RMSE | Mean signed difference |
| --- | ---: | ---: | ---: | ---: |
| Initial, 8-49 s | 2.014316 | 0.725038 | 0.927638 | -0.716452 |
| Transition, 50-60 s | 1.932168 | 1.360393 | 1.392743 | -1.360393 |
| Post-transition, 61-146 s | 4.932058 | 2.967407 | 3.102843 | -2.967407 |

Observed behaviour:

- UC and the digitised curve nearly coincide at 8 and 10 s.
- A negative sawtooth offset begins before the declared 50 s demand
  transition and grows in successive bands.
- The transition itself does not cause the first discrepancy or threshold
  crossing.
- After 61 s the signed difference has a least-squares slope of -0.030225
  packets/s and changes by -1.513079 packets between the region endpoints.
  The difference therefore exhibits negative drift over the observed
  post-transition interval, with packet-scale oscillation superimposed.

## Event diagnostics

At 11 s, the first 0.5-packet exceedance is -0.679512 packets. UC has three L1
exits. `P4` enters the L1-to-L2 boundary queue at that tick and exits L1 at
12 s.

At 13 s, the first 1-packet exceedance is -1.044035 packets. UC has four L1
exits. `P5` enters the boundary queue at 13 s and exits L1 at 14 s.

At 43 s, the first 2-packet exceedance is -2.014316 packets. UC has 18 L1
exits. `P19` enters the boundary queue at 43 s and exits L1 at 44 s.

The maximum occurs at 133 s. UC remains at 60 L1 exits while the interpolated
reference is 64.932058. `P61` entered the boundary queue at 131 s, remained
queued through 133 s, and exited L1 at 134 s. The maximum therefore coincides
with a visible multi-tick boundary wait rather than the demand transition.

At the final comparison tick, UC has 67 L1 exits. `P67` exits at 146 s;
`P68` and `P69` exit later at 148 and 150 s, while `P70` is only instantiated
at 150 s. The digitised reference is 70.461707 packets at 146 s, slightly
above the declared 70-packet integrated demand. That overrun is retained and
is evidence of digitisation uncertainty, not a value to correct.

## Classification

- **Implementation assumption:** integer unit packets, 0.5-packet/s capacity
  represented through UC fractional carry, and existing within-tick movement
  and queue ordering.
- **Digitisation uncertainty:** non-integer points, two small decreases in a
  nominally cumulative curve, sparse late-time segments, and a final value
  slightly above the declared integrated demand.
- **Possible kernel discrepancy:** the growing outflow offset is a genuine
  cross-model discrepancy requiring later investigation, but the present
  evidence does not establish a kernel error. UC's cumulative series agrees
  with its canonical event history.
- **Unknown:** the exact paper-side packet-release, fractional-capacity, queue,
  and within-tick ordering conventions.

No corrective action is taken.

## Artifacts

Outputs are under
`outputs/validation/m8_desouza_figure5a_link1_cumulative_outflow_dt1_comparison_v1/`:

- `overlay.png`;
- `difference.png`;
- `comparison_series.csv`;
- `summary.json`.
