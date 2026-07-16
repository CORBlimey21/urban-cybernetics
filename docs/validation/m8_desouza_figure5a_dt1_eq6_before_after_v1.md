# M8 de Souza Figure 5(a) DT=1 Equation (6) before/after evidence

Status: complete observational comparison. The only kernel change between the
two UC states is the receiving-credit recurrence. No published digitisation,
demand, route, packet schedule, loading parameter, or comparison convention
was changed.

## The Equation (6) patch corrects the targeted credit history

The pre-patch implementation consumed offered whole-packet capacity even when
no packet transferred. The patched implementation retains unused whole-packet
credit, subtracts actual transferred flow, and caps the credit at
`ceil(C * dt) + 1`, as declared by de Souza Equation (6). At DT=1:

- L2 offers zero packets at tick 2 and retains 1.0 packet of credit;
- packet P2 enters L2 at tick 7;
- the bounded 150-second run completes 68 of 70 packets and retains one packet
  on each link;
- conservation, event/cache consistency, cumulative-count consistency,
  physical eligibility, and deterministic replay pass.

These observations establish the recurrence consequence in UC. They do not
make the digitised figure ground truth or establish agreement with every paper
convention.

## Before/after comparison metrics

Difference is `UC - digitised reference`. Negative error deltas mean smaller
disagreement after the patch.

| Quantity | Metric | Before | After | After - before |
| --- | --- | ---: | ---: | ---: |
| L1 cumulative inflow | maximum absolute difference (packets) | 2.160546 | 2.160546 | 0.000000 |
| L1 cumulative inflow | MAE (packets) | 1.125466 | 0.984037 | -0.141429 |
| L1 cumulative inflow | RMSE (packets) | 1.304916 | 1.199089 | -0.105827 |
| L1 cumulative inflow | final signed difference (packets) | -1.352852 | -1.352852 | 0.000000 |
| L1 cumulative outflow | maximum absolute difference (packets) | 5.195908 | 2.762781 | -2.433128 |
| L1 cumulative outflow | MAE (packets) | 1.995476 | 0.745504 | -1.249972 |
| L1 cumulative outflow | RMSE (packets) | 2.381686 | 0.885554 | -1.496132 |
| L1 cumulative outflow | final signed difference (packets) | -3.034844 | -2.034844 | +1.000000 |
| L1 storage | maximum absolute difference (packets) | 4.682678 | 1.985438 | -2.697240 |
| L1 storage | MAE (packets) | 1.636418 | 0.658075 | -0.978343 |
| L1 storage | RMSE (packets) | 1.891800 | 0.881411 | -1.010390 |
| L1 storage | final signed difference (packets) | +3.383445 | +0.383445 | -3.000000 |

Threshold and drift evidence is preserved in the local machine-readable
summary at
`outputs/validation/m8_desouza_figure5_dt1_eq6_patch_v2/before_after_summary.json`.
The regenerated overlays, difference plots, and comparison series are under
the adjacent `comparisons/` directory.

## Fixed comparison method

The reference inputs are:

- inflow: `desouza_figure5a_cumulative_inflow_digitised_v2.csv`;
- outflow: `desouza_figure5a_link1_cumulative_outflow_digitised_v2.csv`;
- storage: `desouza_figure5a_link1_storage_digitised_v1.csv`.

Each digitised reference is piecewise-linearly interpolated onto UC's unchanged
integer-second observations. UC is not interpolated, no extrapolation is used,
and no reference point is fitted, smoothed, shifted, or edited. Storage retains
its previously declared stable time-sort convention for duplicate and locally
reversed traced points.

## Limitations

The published references are digitised figure data, not ground truth. Residual
differences may include digitisation uncertainty, implementation assumptions,
unknown paper conventions, or a possible kernel discrepancy; this comparison
does not distinguish them beyond the event evidence already reported in the
individual inflow, outflow, and storage reports. No further kernel change is
made from these measurements.
