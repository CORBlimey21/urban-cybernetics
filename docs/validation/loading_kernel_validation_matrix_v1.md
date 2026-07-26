# Base loading-kernel validation matrix v1

Status: passed and frozen as `loading-kernel-v1.0.1`. The accepted de Souza
Figures 5, 7, 8, and 9 evidence set is complete. Other unselected literature or
cross-implementation groups remain explicitly deferred and are not implied by
this boundary.

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
| Kernel hardening v1.0.1 | transfer preflight, queued/ordinary pairing, completion pairing, spatial uniqueness, active cancellation, consolidated report, exact rerun | exact pre/post event, trace, packet, count, outcome and benchmark equality | passed | `tests/test_kernel_hardening.py` and hardening evidence note |
| de Souza Figure 5 DT1 | L1 cumulative inflow, outflow and storage against digitised Figure 5(a) | descriptive RMSE/MAE/max/threshold/drift metrics; no fitted tolerance | comparison complete | committed data, report, DT1 replay fixture, local plots |
| de Souza Figure 5 DT3/DT6 | declared input execution and complete UC evidence | internal invariants only; no paper curve supplied | evidence complete; external comparison not run | Workbench fixtures |
| de Souza Figure 7 DT1/DT3 | route-encoded strict-FIFO diverge; six Figure 7 cumulative/per-tick observables | exact routes/conservation/FIFO/replay internally; DT1 descriptive metrics with no fitted tolerance | DT1 observational comparison/audit complete; DT3 reference pending | raw digitisation, report, comparison tool, case/run replay fixtures, focused tests |
| de Souza Figure 8 DT1 | 100 seeded 75:25 route-encoded diverge replications | exact closure/conservation/FIFO/identity/eligibility/replay; descriptive ensemble bands | observational stochastic envelope reproduced | ensemble JSON/CSVs, report, plots, exporter, focused tests |
| de Souza Figure 9 equal priority | 1:1 merge, retained queues, post-change unused-share release | descriptive published-curve metrics; exact closure/conservation/FIFO/identity/eligibility/events/replay | observational comparison and read-only audit complete | raw CSVs, UC evidence, summary, report, plots, exporter, focused tests |
| de Souza Figure 9 asymmetric priority | resolved 3:1 merge, disadvantaged queue retention and discharge | descriptive published-curve metrics; exact priority/closure/conservation/FIFO/identity/eligibility/events/replay | observational comparison and read-only audit complete | raw CSVs, UC evidence with ambiguity resolution, summary, report, plots, exporter, focused tests |

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
or invariant evidence. It is not external validation. Figures 5, 7, 8, and 9
are published observational reproductions; their digitised curves remain
reference measurements with digitisation and paper-convention uncertainty.

The machine-readable companion is
`docs/validation/loading_kernel_validation_matrix_v1.json`.

## Closure verification

- Python freeze closure: 693 passed, zero failed, 88 subtests passed in 16.67
  seconds; accepted v1.0.0 closure: 686 passed.
- Frontend: 26 passed, zero failed in 0.453 seconds (0.94 seconds wall time).
- TypeScript: project typecheck passed in 1.60 seconds wall time.
- Known non-failure: one FastAPI `TestClient` deprecation warning.
