# Loading kernel scientific capability statement v1

Status: current as of 2026-07-16. This document states claim boundaries; it
does not expand loading scope.

## Safe claims

- UC has a frozen, packetised, event-sourced LTM loading kernel under the
  `parity_ltm_v1` profile.
- The frozen kernel preserves unit-packet identity, FIFO, exact conservation,
  finite storage, backward-wave spillback, physical eligibility, canonical
  event order, and deterministic replay under its documented tick convention.
- The frozen kernel supports validated one-to-one, route-encoded diverge, and
  equal/cyclic-priority merge allocation, plus internally validated supported
  movement-based MIMO allocation.
- Principal de Souza lane-drop, deterministic diverge, seeded stochastic-route
  diverge, and equal/asymmetric merge cases are observationally reproduced.
- External discrepancies are measured, bounded within the observed comparison
  artifacts, and classified without tuning.
- No kernel discrepancy was identified in the completed external validation
  cases.

## Claims not yet safe

- full Sioux Falls academic parity;
- Cork or any other city-scale empirical validity;
- calibrated traffic realism or field-calibrated behaviour/governance;
- weighted-packet parity;
- adaptive signal-control parity;
- lane-changing, gap-acceptance, or roundabout-specific validity;
- dynamic rerouting parity;
- production-scale performance;
- equivalence to every LTM implementation, merge solver, initialization phase,
  or within-tick timing convention.

## Evidence classes must remain distinct

| Evidence class | Meaning | Current examples |
| --- | --- | --- |
| Exact internal invariant | Repository-owned semantic property with zero-tolerance checks | identity, conservation, event order, FIFO, closure, replay |
| Exact analytical fixture | Independently authored arithmetic or canonical scenario under the declared discrete convention | link translation, capacity, storage, vacancy, composition cases |
| Observational literature reproduction | Comparison to preserved primary-source figure data without fitted pass thresholds | de Souza Figures 5, 7, 8, and 9 |
| Readiness or stress evidence | Engineering evidence that a topology or workload initializes/runs | Sioux Falls and scale ladders |
| Deferred claim | Evidence is missing, ineligible, or outside the frozen scope | full Sioux Falls parity, empirical Cork validity, advanced traffic mechanics |

Exact internal and analytical evidence must not be described as independent
external validation. Observational reproduction must retain digitisation and
paper-convention caveats. Readiness and stress runs must not be promoted to
scientific parity or empirical validity.

The canonical scope and change-control rules are defined by
`docs/architecture/loading_kernel_freeze_contract_v1.md`. Detailed evidence is
in the loading-kernel validation dossier and validation matrices.
