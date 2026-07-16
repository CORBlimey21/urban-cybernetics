# Base loading-kernel validation matrix v1

Status: passed for the frozen base-kernel boundary. One additional external de
Souza node benchmark remains blocked on source inputs and is not represented as
completed evidence.

Exact internal cases use zero-packet, zero-tick, and exact sequence tolerances,
except the independently authored mean-delay scalar in M8-LINK-02, which uses
absolute tolerance `1e-12`. Published-figure metrics are descriptive
measurements against digitised reference data, not pass/fail ground truth.

| Evidence group | Mechanisms exercised | Tolerance | Status | Primary evidence |
| --- | --- | --- | --- | --- |
| M8-LINK-01 | free-flow pulse translation, lifecycle events | exact | passed | Workbench case and deterministic fixture |
| M8-LINK-02 | capacity discharge, queue/delay, FIFO eligible prefix | exact counts/ticks; `1e-12` mean delay | passed | Workbench case and deterministic fixture |
| M8-LINK-03 | finite storage, lagged vacancy, boundary queue release | exact | passed | Workbench case and deterministic fixture |
| M8-LINK-04 | sustained uncongested flow | exact | passed | Workbench case and deterministic fixture |
| M8-LINK-05 | queue growth, saturated discharge, clearance | exact | passed | Workbench case and deterministic fixture |
| M8-LINK-06 | repeated backward-vacancy releases | exact | passed | Workbench case and deterministic fixture |
| M8-LINK-07 | fractional sending credit and long-horizon total | exact | passed | Workbench case and deterministic fixture |
| M8-NODE-01 family | one-to-one demand/supply limits, zero boundaries, reopening, fractional receiving | exact | passed | seven Workbench cases and independent arithmetic test |
| Internal node-family matrix | strict FIFO diverge, partial FIFO, priority merge, unused-share release, MIMO, conflict/lane resources, signal/closure gates, ordering invariance | exact packet/event/count sequences and declared integer capacities | passed internal | `tests/test_ltm_parity_node_family.py` |
| Equation (6) | retained whole-packet receiving credit, actual-flow subtraction, published cap | exact tick-2 credit and tick-7 P2 event | passed | focused regression tests and DT1 evidence |
| M8-COMP-NET-01 | four links, equal-priority merge, L4 bottleneck, multi-link spillback, two OD routes, queue clearance | exact storage, queue, count, FIFO and event sequences | passed | composition builder and tests |
| de Souza Figure 5 DT1 | L1 cumulative inflow, outflow and storage against digitised Figure 5(a) | descriptive RMSE/MAE/max/threshold/drift metrics; no fitted tolerance | comparison complete | committed data, report, DT1 replay fixture, local plots |
| de Souza Figure 5 DT3/DT6 | declared input execution and complete UC evidence | internal invariants only; no paper curve supplied | evidence complete; external comparison not run | Workbench fixtures |
| de Souza Figure 7 DT1/DT3 | route-encoded strict-FIFO diverge; six Figure 7 cumulative/per-tick observables | exact routes/conservation/FIFO/replay internally; DT1 descriptive metrics with no fitted tolerance | DT1 observational comparison/audit complete; DT3 reference pending | raw digitisation, report, comparison tool, case/run replay fixtures, focused tests |

## Composition congestion sequence

`M8-COMP-NET-01` contains L1 and L2 merging into L3, followed by the lower-rate
L4 bottleneck. Four packets use each OD route. At tick 3, L3 reaches its
four-packet storage bound while all three boundaries L1→L3, L2→L3, and L3→L4
have active queues. The literal storage and queue series clear to zero by tick
10. All eight packets complete, link exit orders equal link entry orders,
aggregate and route counts reconcile, physical eligibility passes, and a
second run has an identical canonical event log.

## Matrix interpretation

“Passed internal” establishes deterministic agreement with authored analytical
or invariant evidence. It is not external validation. Figure 5 is the first
published observational comparison; its digitised curves remain reference
measurements with digitisation and paper-convention uncertainty.

The machine-readable companion is
`docs/validation/loading_kernel_validation_matrix_v1.json`.

## Closure verification

- Python: 653 passed, zero failed, 88 subtests passed in 14.87 seconds
  (15.16 seconds wall time).
- Frontend: 26 passed, zero failed in 0.453 seconds (0.94 seconds wall time).
- TypeScript: project typecheck passed in 1.60 seconds wall time.
- Known non-failure: one FastAPI `TestClient` deprecation warning.
