# M8 de Souza Figure 5(a) Link 1 storage DT=1 comparison v1

Status: observational comparison complete. The existing DT=1 UC evidence was
read unchanged; the simulator was not rerun.

## Sources and interpolation

- UC source: persisted `l1_storage` observations from
  `m8-pub-dsouza-fig5-dt1-baseline-v1/result.json`.
- Reference source: 274 supplied digitised points, preserved verbatim in
  `data/validation/desouza_figure5a_link1_storage_digitised_v1.csv`.
- Comparison support: exact UC integer-second observations from 1 through
  136 s inclusive, 136 samples.
- Difference: `UC storage - digitised reference storage`.

Unlike the earlier flow references, the storage digitisation is not supplied
in monotone time order. It contains 92 non-increasing adjacent time pairs and
39 repeated timestamps, representing vertical and locally reversed traced
segments. To make interpolation defined, points are stable-sorted by ascending
time. Values sharing a time retain their supplied order. No point is averaged,
removed, shifted, smoothed, or fitted. Piecewise linear interpolation is then
applied only to the sorted digitised reference. UC is not interpolated and no
extrapolation is performed.

## Numerical summary

| Measure | Result |
| --- | ---: |
| Maximum absolute difference | 4.682678 packets at 135 s |
| Mean absolute difference | 1.636418 packets |
| RMSE | 1.891800 packets |
| First absolute difference > 0.5 | 7 s |
| First absolute difference > 1 | 7 s |
| First absolute difference > 2 | 59 s |
| Final common-support difference | +3.383445 packets at 136 s |

## Peak comparison

- UC global peak on the common support: 19 packets, first reached at 37 s.
- Digitised global peak: 18.906504 packets at 64.964456 s.
- Peak magnitude difference, UC minus reference: +0.093496 packets.
- Global-peak timing difference, UC minus reference: -27.964456 s; absolute
  difference 27.964456 s.

The timing statistic is highly sensitive to digitisation. A second reference
point reaches 18.901120 packets at 34.951566 s, within 0.01 packets of the
digitised global maximum. Relative to that near-equal peak, UC's first
19-packet peak is only 2.048434 s later. Both values are retained; the global
peak definition is used for the formal timing metric.

## Regional statistics

| Region | Max abs. difference | MAE | RMSE | Mean signed difference |
| --- | ---: | ---: | ---: | ---: |
| Initial, 1-49 s | 1.935025 | 1.055393 | 1.189301 | +0.999452 |
| Transition, 50-60 s | 2.015484 | 1.324102 | 1.405984 | +1.324102 |
| Post-transition, 61-136 s | 4.682678 | 2.056231 | 2.281734 | +1.970954 |

After 61 s, the signed difference has a least-squares slope of +0.042824
packets/s and changes by +1.825562 packets between the region endpoints. The
observed difference therefore exhibits positive drift: UC storage becomes
increasingly higher than the digitised reference late in the common support.

## Event observations

- At 7 s, the first 0.5- and 1-packet exceedance is +1.032250. UC storage is
  six packets. `P7` enters L1 and `P2` enters the L1-to-L2 boundary queue.
- At 37 s, UC first reaches its 19-packet peak. `P34` enters L1 while `P16`
  remains in the boundary queue.
- At 59 s, the first 2-packet exceedance is +2.015484. UC storage is 19;
  `P45` enters L1 and `P27` enters the boundary queue.
- At 135 s, the maximum difference is +4.682678. UC storage is six;
  `P67` enters L1 and `P62` enters the boundary queue. At 136 s, `P62`
  transfers to L2 and UC storage falls to five.

These are temporal coincidences in the preserved evidence, not causal
explanations.

## Discrepancy classification

- **Digitisation uncertainty:** non-monotone traced time order, 39 duplicate
  timestamps, vertical segments, and two nearly equal reference maxima at
  widely separated times. The deterministic stable-sort convention materially
  limits peak-timing interpretation.
- **Implementation assumption:** UC's integer unit-packet storage, tick-end
  observations, fractional-capacity carry, and current within-tick queue and
  transfer ordering.
- **Unknown paper convention:** the precise sampling phase and whether the
  published storage curve is presented immediately before or after each
  within-tick admission or transfer.
- **Possible kernel discrepancy:** not established. The pointwise storage
  difference and positive late drift are real comparison results, but UC's
  stored occupancy agrees with cumulative entries minus exits and its
  canonical event history.

No corrective action is attempted.

## Artifacts

`outputs/validation/m8_desouza_figure5a_link1_storage_dt1_comparison_v1/`
contains:

- `overlay.png`;
- `difference.png`;
- `comparison_series.csv`;
- `summary.json`.
