# M8 de Souza Figure 5(a) DT=1 comparison v1

Status: first observational published comparison completed. No UC simulation
semantics were modified and the preserved preparation run was not rerun.

## Scope and sources

This comparison uses:

- case `M8-PUB-DSOUZA-FIG5-DT1`, version 1;
- the persisted `l1_cumulative_inflow` series in
  `fixtures/visualisation/validation/runs/m8-pub-dsouza-fig5-dt1-baseline-v1/result.json`;
- the 70 digitised Figure 5(a) points supplied for this comparison, preserved
  verbatim in
  `data/validation/desouza_figure5a_cumulative_inflow_digitised_v1.csv`.

The digitised series is published reference data extracted from a plotted
curve. It is not ground truth. No point was smoothed, fitted, shifted, or
manually adjusted.

## Comparison convention

UC is observed at exact integer-second ticks. The digitised reference begins
at 1.106210283 s and ends at 145.935950649 s. The comparison therefore uses
the 144 common-support UC observations from 2 through 145 s inclusive.

At each comparison tick, the two adjacent digitised reference points are
joined by a straight line and evaluated at that integer second. UC is not
interpolated. No extrapolation is performed. The signed difference is:

`UC cumulative inflow - linearly interpolated digitised cumulative inflow`.

## Numerical summary

| Measure | Result |
| --- | ---: |
| Maximum absolute difference | 1.799111 packets at 74 s |
| Mean absolute difference | 0.861127 packets |
| RMSE | 0.988138 packets |
| First absolute difference greater than 0.5 packets | 5 s |
| First absolute difference greater than 1 packet | 34 s |
| First absolute difference greater than 2 packets | not observed |
| Final common-support difference | -0.790447 packets at 145 s |

The difference is bounded within the observed common support. After 61 s its
least-squares signed-difference slope is 0.000698 packets/s and its endpoint
change is +0.067307 packets. This does not exhibit sustained post-transition
drift; it exhibits a bounded, predominantly negative sawtooth offset.

## Transition analysis

The region definitions below are declared for this report, not fitted:

- initial capacity region: 2-49 s;
- transition window: 50-60 s;
- post-transition low-demand region: 61-145 s.

| Region | Max abs. difference | MAE | RMSE | Mean signed difference |
| --- | ---: | ---: | ---: | ---: |
| Initial capacity | 1.324956 | 0.415479 | 0.520488 | -0.037876 |
| Transition | 0.779669 | 0.403952 | 0.472488 | -0.283210 |
| Post-transition low demand | 1.799111 | 1.171951 | 1.213379 | -1.171951 |

Observed behaviour:

- In the initial region, UC and the digitised curve alternate around one
  another before the signed difference becomes more negative near 32-35 s.
- The declared 50 s demand transition does not introduce the first
  discrepancy or the first threshold crossing. The transition-window errors
  are smaller than the largest pre- and post-transition errors.
- After 61 s, the digitised cumulative curve remains above UC at every sampled
  integer second. The difference repeats as a sawtooth rather than increasing
  steadily.

## Event and packet diagnostics

The first non-zero sampled difference is +0.480977 packets at 2 s. At that
tick the persisted event history records `P2` being instantiated and entering
L1; UC cumulative inflow is exactly 2. The non-integer digitised value after
linear interpolation is consistent with curve digitisation and differing
continuous-versus-discrete presentation. That observation alone cannot
identify a kernel discrepancy.

The first 0.5-packet exceedance is at 5 s. `P5` is instantiated and enters L1
at tick 5, bringing UC cumulative inflow to exactly 5. The reference
interpolation lies between neighbouring non-integer digitised points. This is
classified as digitisation/timing uncertainty, with the UC unit-packet release
convention an explicit implementation assumption.

The first 1-packet exceedance is at 34 s. The trace around that point is:

- tick 31: `P31` enters L1; L1 storage becomes 18 and `P14` queues;
- tick 32: `P14` transfers to L2, but no new origin packet enters in that tick;
- tick 33: `P32` enters L1 and `P15` queues;
- tick 34: `P15` transfers to L2, but no new origin packet enters;
- tick 35: `P33` is instantiated and enters L1.

Thus the first greater-than-one difference coincides with an alternating
origin-admission pattern while L1 is constrained, not with the 50 s demand
transition. The within-tick origin-admission and transfer ordering is an
explicit UC implementation assumption because the paper does not declare its
corresponding convention. Whether the published curve uses the same convention
is unknown.

The maximum absolute difference occurs at 74 s. UC has 51 L1 entries. `P51`
entered at tick 73; tick 74 contains the L1-to-L2 transfer of `P33` but no new
origin entry; `P52` enters at tick 75. This is the same visible alternating
release/admission pattern. It is not evidence of accumulating drift.

## Discrepancy classification

- **Implementation assumption:** UC's integer unit packets, tick-end demand
  conversion, and current within-tick origin-admission/transfer ordering.
- **Digitisation uncertainty:** non-integer coordinates extracted from a
  plotted curve and linear reconstruction between sparse points, especially
  after 77 s.
- **Possible kernel discrepancy:** none established by this comparison. The
  internal event history is consistent with the persisted UC cumulative series.
- **Unknown:** the exact packet release and event-ordering conventions used to
  produce the published curve.

No claim of reproduction, agreement, or disagreement beyond the reported
measurements is made.

## Reproduction and artifacts

Run:

```text
python scripts/compare_desouza_figure5a_dt1.py
```

Outputs are written under
`outputs/validation/m8_desouza_figure5a_dt1_comparison_v1/`:

- `overlay.png`;
- `difference.png`;
- `comparison_series.csv`;
- `summary.json`.
