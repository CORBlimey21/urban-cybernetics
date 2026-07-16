# External Validation Matrix v1

Status (2026-07-16): the accepted de Souza Figures 5, 7, 8, and 9 evidence set
for `loading-kernel-v1.0.0` is complete. Other unselected published or
cross-implementation rows remain explicitly deferred and are not requirements
for reopening this named freeze. Machine-readable companion:
`docs/validation/external_validation_matrix_v1.json`.

An internal UC test is not external validation. A group may receive an
externally validated label only after its declared independent source or
implementation is reproduced and passes a tolerance fixed before comparison.

## Coverage Summary

| ID | Scientific subject | Reference status | Implementation status |
| --- | --- | --- | --- |
| M8-VAL-01 | Uncongested single-link translation | Independent literal analytical oracle; published table not yet reproduced | Implemented; not externally validated |
| M8-VAL-02 | Capacity bottleneck and queue dissipation | Independent literal analytical oracle; published table not yet reproduced | Implemented; not externally validated |
| M8-VAL-03 | Backward-wave vacancy propagation | Independent literal analytical oracle; published table not yet reproduced | Implemented; not externally validated |
| M8-VAL-04 | One-to-one node | External numerical source not selected | Planned; internal coverage only |
| M8-VAL-05 | Priority merge | de Souza Figure 9(a,d) `G1/G2` supplied | Equal and asymmetric observational comparisons and audits complete without calibration |
| M8-VAL-06 | Strict-FIFO diverge | External tick-by-tick case not selected | Planned; internal coverage only |
| M8-VAL-07 | Partial-FIFO diverge | External formulation and overlap parameters not selected | Planned; internal coverage only |
| M8-VAL-08 | General MIMO node | Tampere 2011 candidate; numerical case/mapping missing | Planned; internal coverage only |
| M8-VAL-09 | Published network-loading numerical case | de Souza Figure 5(a) digitised L1 inflow, outflow, and storage supplied | DT1 observational comparison complete without calibration |
| M8-VAL-10 | External benchmark/cross-implementation comparison | Implementation not selected or run | Blocked on implementation selection |
| M8-VAL-11 | de Souza Figure 7 deterministic diverge | DT1 digitised `Gu/F1/F2` supplied; DT3 values pending | DT1 observational comparison and audit complete without calibration; no formal threshold pass assigned |
| M8-VAL-12 | Figure 8 — stochastic route-encoded diverge replication envelope | Figure 7(a) deterministic cumulative curves used as the declared centre | 100 seeded replications complete; deterministic centre is inside both bands at every tick |

## M8-VAL-01 — Uncongested Single-Link Translation

- Scientific subject: below-capacity free-flow translation.
- Reference type/status: independent closed-form derivation encoded as literal
  tables in M8-LINK-01. Newell/LTM literature is contextual; no published table
  is claimed reproduced.
- Exact inputs: 200 m, one lane, `v=10 m/s`, `w=5 m/s`, `kj=120
  veh/km/lane`, `q=1440 veh/h/lane`, `dt=10 s`, three-unit-packet initial
  pulse at tick 0 with origin admission budget 4.
- Expected outputs: entries `(3,3,3,3)`, exits `(0,0,3,3)`, exit ticks
  `(2,2,2)`, point queue `(0,0,0,0)`, exact conservation.
- Tolerance: zero packets and zero ticks.
- UC subsystem: physical resolution, origin admission, free-flow sending,
  canonical lifecycle events.
- Claim if passed: this pulse translates by `ceil((L/v)/dt)` under the declared
  discrete convention.
- Not supported: academic parity, empirical realism, node or network validity,
  production readiness.
- Status/blocker: implemented, not externally validated; a published or
  cross-implementation reference is still required for that label.

## M8-VAL-02 — Capacity Bottleneck and Queue Dissipation

- Scientific subject: capacity-limited discharge and exit-boundary point queue.
- Reference type/status: independent cumulative-count derivation and literal
  oracle in M8-LINK-02; no published numerical table is claimed reproduced.
- Exact inputs: 200 m, one lane, `v=10 m/s`, `w=5 m/s`, `kj=30
  veh/km/lane`, `q=360 veh/h/lane`, `dt=10 s`, five-packet initial pulse at
  tick 0 with origin admission budget 5.
- Expected outputs: exits `(0,0,1,2,3,4,5)`, queue
  `(0,0,4,3,2,1,0)`, exit ticks `(2,3,4,5,6)`, delays `(0,1,2,3,4)` and
  mean delay `2.0` ticks.
- Tolerance: exact counts/ticks; absolute `1e-12` for mean delay.
- UC subsystem: lagged sending, capacity budget, FIFO eligible prefix, event
  evidence.
- Claim if passed: this queue forms and dissipates at one packet per tick under
  the declared convention.
- Not supported: continuous-flow convergence, empirical queue realism,
  spillback/node/network validity, production readiness.
- Status/blocker: implemented, not externally validated; independent external
  numerical evidence is still required.

## M8-VAL-03 — Backward-Wave Vacancy Propagation

- Scientific subject: delayed upstream reuse of downstream storage.
- Reference type/status: independent lagged-vacancy derivation and literal
  oracle in M8-LINK-03; no published numerical table is claimed reproduced.
- Exact inputs: two 40 m one-lane links, `v=10 m/s`, `w=5 m/s`, `kj=75
  veh/km/lane`, `q=900 veh/h/lane`, `dt=4 s`, downstream storage initially
  full with a three-packet origin preload budget, one upstream transfer
  candidate.
- Expected outputs: first exit tick 1; no pre-accept vacancy at ticks 1–2; one
  slot at tick 3; upstream entry and boundary queue release at tick 3.
- Tolerance: zero packets and zero ticks.
- UC subsystem: finite storage, lagged receiving, canonical boundary queue,
  resumed transfer.
- Claim if passed: downstream vacancy is delayed by `ceil((L/w)/dt)` under the
  declared convention.
- Not supported: continuous-wave convergence, empirical wave speed, general
  network spillback/node validity, production readiness.
- Status/blocker: implemented, not externally validated; independent external
  numerical evidence is still required.

## M8-VAL-04 — One-to-One Node

- Reference/status: independent analytical node-flow table not yet selected;
  UC internal coverage is not external evidence.
- Inputs required: incoming/outgoing link physics, sending/receiving curves,
  node timestep, initial storage, packet order.
- Outputs/tolerance: movement flow, cumulative curves, queues, delays, and
  conservation; exact integer series unless the selected source requires a
  declared numerical tolerance.
- UC subsystem: Stage 2 movement allocation, receiving constraint, queue
  lifecycle.
- Claim if passed: reproduction of the named one-to-one case only.
- Not supported: merge, diverge, MIMO, empirical, or network-wide claims.
- Status/blocker: planned; select a source with complete inputs and convention.

## M8-VAL-05 — Priority Merge

- Reference/status: de Souza Figure 9 is complete. The supplied panel (a)
  equal-priority and panel (d) asymmetric `G1/G2` digitisation are preserved
  byte-for-byte and compared on their actual supports.
- Exact inputs: three inherited 150 m links, `V=30 m/s`, `W=6 m/s`,
  `K1=K2=K3=0.1 veh/m`, Equation (15) demands, `dt=1 s`, 120 s horizon,
  equal `α1=0.5`, `[0,1]`, and asymmetric `α1=0.75`, `[0,0,0,1]` cases.
- Outputs/tolerance: cumulative `G1/G2`, derived `F3=G1+G2`, descriptive
  Figure 5/7 metrics on actual supports, and exact zero-tolerance closure,
  conservation, FIFO, identity, physical eligibility, event ordering, and
  replay gates.
- Claim supported: UC observationally reproduces both Figure 9 priority and
  queue transitions without calibration. Exact internal gates pass. Read-only
  audits classify material differences as digitisation uncertainty, unknown
  paper timing/priority phase, and the documented frozen implementation
  convention.
- Not supported: a formal fitted tolerance, all merge solvers, or a kernel
  change.
- Status/blocker: complete. The asymmetric inconsistency is explicitly
  resolved as `α1=0.75`: the 3:1 sequence, panel labels, behaviour prose,
  algorithm, and later freeway example outweigh two conflicting `0.25`
  transcription instances.

## M8-VAL-06 — Strict-FIFO Diverge

- Reference/status: strict-FIFO literature semantics identified; no external
  tick-by-tick numerical fixture encoded.
- Inputs required: one input, multiple outputs, route split and packet order,
  branch demands/supplies, strict-FIFO rule, any closure schedule.
- Outputs/tolerance: head-of-line blocking, movement flows, cumulative curves,
  boundary queues and delays; exact packet order/counts/ticks.
- UC subsystem: strict FIFO, route-encoded diverge, movement rejection, queue
  release.
- Claim if passed: reproduction of the named strict-FIFO case only.
- Not supported: partial FIFO, lane-changing bypass, empirical diverge or MIMO
  validity.
- Status/blocker: planned; source must expose commodity order and FIFO
  convention.

## M8-VAL-07 — Partial-FIFO Diverge

- Reference/status: UC has internal `partial_by_movement` coverage; external
  formulation and numerical overlap parameters are not selected.
- Inputs required: commodity demands, output supplies, oriented/lane-overlap
  parameters, partial-FIFO rule, timestep.
- Outputs/tolerance: movement flows, restricted fractions, branch curves,
  queues and delays; source-declared flow tolerance and exact conservation.
- UC subsystem: partial FIFO, lane groups, movement allocation, commodity
  evidence.
- Claim if passed: reproduction of the selected formulation for the encoded
  overlap semantics.
- Not supported: physical lane changing, every partial-FIFO formulation,
  empirical lane choice, general MIMO validity.
- Status/blocker: map a selected formulation explicitly to UC metadata.

## M8-VAL-08 — General MIMO Node

- Reference/status: Tampere 2011 is a candidate; a complete reproducible MIMO
  case and exact metadata mapping are absent.
- Inputs required: multiple demands/supplies, turning movements, priorities,
  restrictions/resources, commodity composition, timestep.
- Outputs/tolerance: movement-flow matrix, cumulative curves, resource use,
  queues, commodity conservation; source-declared numerical tolerance and exact
  packet conservation.
- UC subsystem: general allocator, priorities, conflict resources, lane groups,
  gates/closures, commodity evidence.
- Claim if passed: reproduction of the selected MIMO case only.
- Not supported: every node solver, adaptive control, gap acceptance,
  empirical or network-wide validity.
- Status/blocker: select and map a fully specified source case.

## M8-VAL-09 — Published Network-Loading Numerical Case

- Reference/status: de Souza et al. 2025 Figure 5 is selected. Its text-declared
  lane-drop inputs are versioned in
  `m8_desouza_figure5_preparation_v1.json`. Digitised Figure 5(a) L1 cumulative
  inflow, cumulative outflow, and storage references have been compared with
  the DT1 UC evidence without calibration.
- Inputs required: published topology, physics, OD/departures, routes or route
  choice, node parameters, initial state, timestep/horizon, numerical outputs.
- Outputs/tolerance: descriptive RMSE, MAE, maximum absolute difference,
  threshold crossings, final signed difference, peak evidence where relevant,
  and regional signed-difference drift. The digitised curves are reference
  measurements, not pass/fail ground truth; conservation remains exact.
- UC subsystem: complete kernel, node allocation, commodities, travel times,
  spillback, provenance.
- Claim supported: UC has completed one observational published-figure
  comparison with fixed inputs and comparison rules; no calibration was used.
- Not supported: all LTM formulations, calibration, other benchmarks, or
  production readiness.
- Status/blocker: the DT1 comparison is complete. DT3 and DT6 retain complete
  UC evidence but have no supplied published curves. Residual DT1 differences
  remain observational evidence rather than a trigger for further kernel
  changes.

## M8-VAL-10 — External Benchmark/Cross-Implementation Comparison

- Reference/status: no independent implementation/version selected or run.
- Inputs required: identical topology, physics, nodes, demand, routes,
  timestep/rounding, seeds, and versioned output interchange.
- Outputs/tolerance: boundary curves, movement flows, queues, travel times,
  completion/clearance; preregister metric tolerances after convention
  alignment. UC replay and conservation remain separate gates.
- UC subsystem: end-to-end kernel, adapters, evidence export, replay,
  comparison tooling.
- Claim if passed: agreement with the named implementation for the exact shared
  case and metrics.
- Not supported: universal equivalence, empirical realism, calibration,
  performance superiority, or production readiness.
- Status/blocker: select an accessible implementation and neutral interchange,
  then resolve conventions before comparison.

## M8-VAL-11 — Further de Souza Merge or Diverge Figure

- Reference/status: de Souza et al. 2025 Figure 7, Section 4.2 and Equation 14
  are selected. The primary-source text was checked against the exact supplied
  parameters, deterministic 3:1 packet route order, timesteps, and named
  observables. Preserved DT1 `Gu`, `F1`, and `F2` digitised series are loaded;
  DT3 numerical values remain pending.
- Exact inputs: three 150 m links; `V=30 m/s`; `W=6 m/s`; `K1=0.2
  veh/m`; `K2=K3=0.1 veh/m`; routes repeat `L1→L2, L1→L2, L1→L2,
  L1→L3`; demand is 0.8 veh/s for `t<50 s` and 0.4 veh/s for
  `50<t<=120 s`; `dt=1 s` and `dt=3 s`.
- Outputs/tolerance: upstream cumulative outflow and both downstream cumulative
  inflows are compared on their actual reference supports with the Figure 5
  interpolation and descriptive metrics. Exact conservation, packet route
  identity, strict FIFO, and replay are zero-tolerance internal gates. No
  numerical pass threshold was fixed before comparison.
- UC subsystem: frozen parity kernel, strict-FIFO diverge allocator, fractional
  sending/receiving credit, route-encoded commodities, events, replay, and
  cumulative count projections.
- Claim currently supported: DT1 observational reproduction is complete without
  calibration. Differences are bounded and non-drifting, while the digitised
  references themselves have closure MAE 0.496 and maximum residual 1.820
  vehicles. All UC internal gates pass exactly.
- Not supported: a formal threshold-based numerical pass, calibration, general
  agreement with all de Souza cases, or any kernel change.
- Status/blocker: DT1 comparison and read-only first-divergence audit are
  complete; no kernel discrepancy is established. DT3 paper values remain
  required for the bottom-row comparison.

## M8-VAL-12 — Figure 8 Stochastic Diverge Envelope

- Reference/status: de Souza Figure 8 stochastic route choice is represented
  as a seeded extension of the frozen Figure 7(a) fixture. The faint published
  traces are not digitised or fitted; the committed deterministic Figure 7(a)
  curves are the reference centre.
- Exact inputs: all Figure 7(a) DT1 topology, physics, demand, horizon,
  timestep, packetisation, and loading semantics; each of 68 routes is drawn
  independently with `P(L2)=0.75` and `P(L3)=0.25`.
- Ensemble: 100 exactly replayable replications using ordered integer seeds
  0–99 and a local `random.Random(seed)` stream.
- Outputs/tolerance: pointwise mean, median, min/max, Type-7 5th/95th bands;
  endpoint and route-share distributions; exact per-tick closure,
  conservation, FIFO, identity, physical eligibility, and replay.
- Claim supported: the deterministic centre is contained by both the full
  envelope and percentile band for `Gu`, `F1`, and `F2` at all 121 ticks; all
  exact validation gates pass 100/100.
- Not supported: fitted agreement to individual faint Figure 8 traces,
  alternative random generators, behavioural route choice, or changes to the
  frozen kernel.
- Status: observationally reproduced; no material discrepancy and therefore
  no read-only first-divergence audit trigger.

## Recommended Sequence

Compare M8-VAL-11 DT3 when its Figure 7 numerical reference values arrive,
using the already fixed DT1/Figure 5 discipline. M8-VAL-04 through M8-VAL-08 and M8-VAL-10
remain useful external-evidence gaps, even though their kernel mechanisms have
internal regression coverage. A failure remains a failure until classified as
fixture transcription, convention mismatch, or kernel behaviour; loading
semantics must not be changed merely to make a fixture pass.
