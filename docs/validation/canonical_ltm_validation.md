# Canonical LTM Validation

Status: initial analytical validation slice.

Scope: compare the frozen packetised parity kernel against recognised LTM
behaviours without adding loading mechanics. This document is validation
evidence, not a new model specification.

## Reproduced Analytical Cases

The executable fixtures live in
`urban_cybernetics.canonical_validation.analytical_ltm` and are covered by
`tests/canonical_validation/test_analytical_ltm.py`.

The current machine-readable validation summary is produced by
`urban_cybernetics.canonical_validation.build_canonical_validation_summary`.
It reports reproduced scenarios, failed scenarios, blocked literature
references, and whether Sioux Falls parity validation is currently allowed.
Each reproduced scenario also carries source IDs for the recognised literature
behaviour it exercises.

Current analytical/textbook scenarios:

- `single_link_free_flow_shift`: cumulative exits are the cumulative entry curve
  shifted by `free_flow_ticks` when sending capacity is nonbinding
  (`newell_1993_simplified_kinematic_waves`).
- `single_link_sending_capacity_saturation`: one packet exits per tick under a
  sending capacity of one, with storage falling by one packet per tick
  (`newell_1993_simplified_kinematic_waves`,
  `daganzo_1994_cell_transmission_model`).
- `two_link_receiving_bottleneck`: downstream receiving capacity admits one
  packet per tick; the upstream queue forms and dissipates one packet per tick
  (`newell_1993_freeway_bottlenecks`,
  `daganzo_1995_cell_transmission_networks`).
- `two_link_delayed_vacancy_spillback`: storage spillback releases only after
  the delayed downstream vacancy signal reaches the upstream boundary
  (`newell_1993_freeway_bottlenecks`,
  `daganzo_1995_cell_transmission_networks`).
- `strict_fifo_diverge_blocked_head`: a blocked head packet prevents a tail
  packet from bypassing to an open branch under strict upstream FIFO
  (`tampere_2011_generic_node_models`).
- `priority_merge_declared_share`: a two-to-one declared priority merge produces
  the expected long-horizon source sequence under unit receiving capacity
  (`tampere_2011_generic_node_models`).

Each scenario compares explicit cumulative curves, queue evolution, travel-time
series where completed packets exist, and merge/diverge behaviour where
applicable. Comparisons are exact integer packet-count series using the existing
inclusive physical-tick count convention.

## Assumptions

- Unit packets only.
- Integer simulation ticks.
- Inclusive cumulative-count convention.
- No rerouting.
- No weighted packets.
- General movement allocation is used for parity node transfer semantics.
- Stage 2 movement allocation supports conflict resources, lane groups, signal
  gates, governance closures, and declared partial FIFO.
- No adaptive signal control, gap acceptance, roundabout-specific behaviour,
  weighted packets, rerouting, or empirical calibration.
- Route travel-time curves use completed packet instantiation and completion
  ticks, tied to final-link route ordinals.

## Current Status

All analytical/textbook fixtures currently pass exactly.

The delayed-spillback fixture carries one explicit discretisation note: the
observed release timing is interpreted under UC's one-tick event boundary and
backward-vacancy convention.

`build_canonical_validation_summary()` currently reports six reproduced
analytical scenarios, no failed reproduced scenarios, no blocking literature
references, and two deferred literature references: `yperman_2007_thesis` and
`de_souza_2025_mesoscopic_ltm`. The deferral reflects the current validation
scope only; neither source is claimed reproduced. Therefore
`is_ready_for_sioux_falls_parity_validation` is currently true for the current
deferred-source pass.

Covered source IDs currently reported by the summary:

- `daganzo_1994_cell_transmission_model`
- `daganzo_1995_cell_transmission_networks`
- `newell_1993_freeway_bottlenecks`
- `newell_1993_simplified_kinematic_waves`
- `tampere_2011_generic_node_models`

## Comparison Plots

Small SVG overlays are generated from the executable fixture comparisons:

- `docs/validation/plots/single_link_free_flow_shift.svg`
- `docs/validation/plots/single_link_sending_capacity_saturation.svg`
- `docs/validation/plots/two_link_receiving_bottleneck.svg`
- `docs/validation/plots/two_link_delayed_vacancy_spillback.svg`
- `docs/validation/plots/strict_fifo_diverge_blocked_head.svg`
- `docs/validation/plots/priority_merge_declared_share.svg`

In each plot, blue is the expected reference series and red is the observed UC
series. Exact overlap is expected for the current analytical fixtures.

## Phase II: Sioux Falls Parity Readiness

Sioux Falls is currently executable only as readiness/stress evidence, not as a
scientific packet-LTM validation result. The executable readiness check lives in
`urban_cybernetics.canonical_validation.sioux_falls_readiness` and can be run
with:

```bash
.venv/bin/python -m urban_cybernetics.canonical_validation.sioux_falls_readiness
```

The check deliberately runs a small deterministic Sioux Falls slice: committed
TNTP topology, committed TNTP demand, deterministic route resolution, and a
bounded scheduled packet subset. It emits topology, demand, and resolved-route
hashes so the output is provenance-bearing. It does not run Anaheim, LA, Cork,
or any larger benchmark study.

Current status:

- `benchmark_loader`: pass. Sioux Falls topology, OD demand, and deterministic
  route-resolution artifacts load and hash.
- `physical_metadata`: fail. The TNTP Sioux Falls topology has 76 links, and
  the parity physical gate currently reports 152 missing-metadata reasons:
  each link lacks `backward_wave_speed_mps` and
  `jam_density_veh_per_km_per_lane`.
- `junction_semantics_metadata`: fail. The committed Sioux Falls TNTP topology
  has complex full-network junctions but no reviewed conflict-resource,
  lane-group, or signal metadata.
- `allocator_capability`: pass. Full Sioux Falls topology can initialize under
  the Stage 2 movement allocator. This is an architecture-readiness signal
  only.
- `parity_commodity_evidence`: not run, because the full topology is not
  parity-eligible until physical and junction semantics metadata are supplied.
- `parity_spillback_evidence`: not run, because the full topology is not
  parity-eligible until physical and junction semantics metadata are supplied.
- `legacy_profile_readiness_stress_run`: pass, labelled explicitly as
  readiness/stress evidence only. It uses `legacy_packet_ltm_style`, so it is
  not parity evidence.

Therefore the current machine-readable evidence label is
`sioux_falls_readiness_stress_only`, and `can_run_as_parity_ltm_v1` is false.
No kernel bug is indicated by the readiness check. The blocking full-network
failures are benchmark physical metadata and missing reviewed junction metadata,
not allocator architecture or MIMO topology shape.

Before true Sioux Falls parity validation, the project needs:

- Reviewed Sioux Falls physical metadata or documented benchmark assumptions for
  jam density and backward-wave speed, plus consistency with the triangular FD
  and storage/timestep gates.
- A benchmark-loader path that can construct parity-eligible loading links from
  those physical parameters without using legacy storage overrides as evidence.
- Reviewed full-network junction metadata: conflict resources, lane groups,
  signal groups, and any governance-controlled movement gates required for a
  defensible Sioux Falls parity claim.
- Successful physical metadata eligibility before commodity, route-count,
  travel-time, spillback, and external-validation claims are allowed.

## Supported Sioux Falls Subnetwork Bridge

Phase II also provides an interim recognised-network readiness bridge:
`sioux_falls_supported_movement_subnetwork_v1`. This is not full Sioux Falls
parity validation. It is a connected Sioux Falls subnetwork selected so every
adapted internal junction is expressible with Stage 2 movement-allocation
semantics and reviewed physical metadata assumptions.

Run it with:

```bash
.venv/bin/python -m urban_cybernetics.canonical_validation.sioux_falls_readiness --subnetwork
```

Selected source nodes:

- `1`, `2`, `3`, `4`, `5`, `6`, `8`

Selected directed source links:

- `1->2` (`L0001`)
- `1->3` (`L0002`)
- `2->1` (`L0003`)
- `2->6` (`L0004`)
- `3->4` (`L0006`)
- `4->5` (`L0009`)
- `5->6` (`L0012`)
- `6->8` (`L0016`)

Adapted internal movement specifications:

- `N002`: route-encoded diverge movements, `L0001 -> {L0003, L0004}`
- `N003`: one-to-one movement, `L0002 -> L0006`
- `N004`: one-to-one movement, `L0006 -> L0009`
- `N005`: one-to-one movement, `L0009 -> L0012`
- `N006`: merge movements, `{L0004, L0012} -> L0016`, equal priority weights

The full Sioux Falls node records are no longer rejected merely because they are
multi-input/multi-output. Any future full-network rejection should identify
missing junction data or unsupported semantics, not the absence of a specialised
node class. The subnetwork remains useful because it supplies reviewed physical
metadata assumptions over a small recognised-network slice.

Subnetwork physical metadata assumptions:

- `backward_wave_speed_mps = 5.0`, labelled
  `benchmark_assumption_not_empirical_calibration`.
- `jam_density_veh_per_km_per_lane` is derived per selected link from TNTP
  capacity, TNTP free-flow speed, and the assumed backward-wave speed so the
  selected link is triangular-FD consistent.
- `declared_storage_capacity_packets` is derived from length, lane count, and
  assumed jam density. The adapter does not use the legacy synthetic storage
  override as parity evidence.

Current subnetwork gate status:

- `supported_subnetwork_structure`: pass.
- `physical_metadata`: pass.
- `parity_profile_initialization`: pass under `parity_ltm_v1`.
- `parity_commodity_evidence`: pass.
- `parity_spillback_evidence`: pass.
- `count_evidence`: pass.
- `packet_conservation`: pass.
- `deterministic_replay`: pass.

The subnetwork readiness label is
`sioux_falls_supported_movement_subnetwork_parity_ready`. This means the selected
subnetwork is ready to serve as the first recognised-network parity readiness
target. It does not mean the full Sioux Falls benchmark has been validated, and
it does not remove the future need for full-network conflict-resource,
lane-group, and signal metadata, nor for future adaptive-control solver layers.

## Full Sioux Falls Engineering-Assumption Physical Profile

The first full-network physical profile is
`SiouxFallsPhysicalProfile_UC_Default_v1`. It exists to exercise the complete
M0-M7 parity kernel and Stage 2 movement-allocation path on the full committed
Sioux Falls topology. It is not empirical calibration, and it does not claim
that the derived values are the true physical parameters of Sioux Falls.

Run the assumption-profile execution with:

```bash
.venv/bin/python -m urban_cybernetics.canonical_validation.sioux_falls_readiness --assumption-profile --tick-limit 600 --max-pairs 12 --max-total-quantity-packets 24
```

The profile keeps the topology immutable. The profile owns the assumptions and
derivations:

- Published Sioux Falls TNTP topology, free-flow times/speeds, capacities, and
  the current one-lane topology interpretation are retained.
- `backward_wave_speed_mps = 5.0` is assumed globally.
- Jam density is derived per link from the triangular fundamental diagram:
  `kj = q(v + w) / (v * w)`, where `q` is the published per-lane capacity,
  `v` is free-flow speed, and `w` is the assumed backward-wave speed.
- Storage capacity is derived per link as
  `floor(length_km * lane_count * kj)`.
- No manual storage values are specified.

The profile records:

- profile identifier and version;
- deterministic generated timestamp;
- source topology hash and source-file hash;
- assumption list;
- derivation equations;
- derived fields;
- per-link derived parameters;
- profile hash;
- the explicit statement that the profile is an engineering assumption profile,
  not empirical calibration.

Current profile use supports this claim:

- UC can build a reproducible assumption-owned full-network physical profile
  that makes all 76 Sioux Falls loading links physically eligible for the
  current `parity_ltm_v1` physical metadata gate.
- UC can run a bounded deterministic demand slice on the full 24-node, 76-link
  topology under `parity_ltm_v1` using that profile.
- The run can report packet conservation, count consistency, FIFO validation,
  spillback validation, commodity validation, node movement validation, and
  deterministic replay status.

### Deterministic Replay Policy

Deterministic replay is a reproducibility and release-regression check. It is
not the same category as packet conservation, count consistency, FIFO,
spillback, commodity, or node movement validation. Those internal validators
ask whether a completed event log is internally coherent under the model
contracts. Replay asks whether a second full execution with identical inputs
produces the same event log.

Replay status must therefore be reported separately:

- `passed_exact_replay`: an actual second execution ran and matched.
- `skipped_by_policy_after_determinism_certification`: exact replay was not
  run for this rung after smaller representative deterministic runs matched.
- `timeout`: replay or the guarded run exceeded the budget.
- `failed_mismatch`: a second execution ran and diverged.
- `not_run`: no replay evidence was attempted.

Never report replay as passed unless a rerun actually occurred and matched.
Policy skip is permitted only when recent deterministic certification exists
for representative Sioux Falls assumption-profile runs, the change under test
is not determinism-sensitive, and all internal validators still run for the
scale rung being reported. Determinism-sensitive changes include event ordering,
packet identity, movement tie-breaking, cumulative count projection,
validation-context reconstruction, mutable state ownership, and any loading
mechanics change.

Safe claims under the policy:

- The internally validated rung passed conservation/count/FIFO/spillback/
  commodity/node checks.
- Exact replay was either passed, skipped by stated policy, timed out, failed,
  or not run.
- A skipped replay is evidence of scale progress only, not exact replay
  evidence for that rung.

Unsafe claims:

- A policy-skipped rung must not be called replay-passed.
- Determinism certification at one scale must not be treated as proof that all
  larger scales are deterministic.
- Internal validation plus skipped replay is not external Sioux Falls
  calibration or canonical benchmark validation.

July 2, 2026 determinism experiments on the UC-default Sioux Falls
assumption-profile runner found exact repeated-run matches at 24, 100, and
1,000 packets. The 5,000-packet repeated comparison was attempted but stopped
after exceeding the prior 180 second budget during the second full engine
execution; no mismatch was observed before interruption, but 5,000 exact replay
is not certified by that run.

After materialising deterministic cumulative entry/exit prefix counts inside
the loading engine, exact replay still matched at 24, 100, and 1,000 packets
with the same event-log fingerprints. With exact replay required through 1,000
packets and skipped above that by explicit policy, the scale ladder result was:

| Rung | Submitted | Instantiated | Completed | Unresolved | Ticks | Primary s | Projection s | Validators s | Replay status | Scale status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1,000 | 1,000 | 1,000 | 1,000 | 0 | 19 | 0.056 | 0.577 | 0.056 | `passed_exact_replay` | passed |
| 5,000 | 5,000 | 5,000 | 5,000 | 0 | 81 | 0.901 | 19.024 | 2.774 | `skipped_by_policy_after_determinism_certification` | passed |
| 10,000 | 10,000 | 10,000 | 8,900 | 1,100 | 20,000 | 112.333 | timeout after 187.630 | not run | `not_run` | failed incomplete/projection timeout |
| 25,000 | not run | not run | not run | not run | not run | not run | not run | not run | `not_run` | stopped after 10,000 |

The removed primary-stepping bottleneck was repeated event-log scans and sorts
inside parity sending/receiving view construction. The new dominant bottleneck
is no longer primary stepping at the largest internally validated rung: 5,000
primary stepping dropped from about 130 seconds to under 1 second. At 10,000,
the engine reaches the 20,000 tick limit with 1,100 packets unresolved; the
subsequent shared projection build times out on a 106,674-event incomplete run.

Follow-up unresolved-packet diagnostics classify the 10,000-packet stop as a
queue-release / movement-allocation issue, not ordinary congestion or an
insufficient runtime horizon. Continuing the same run to 50,000 ticks produced
no additional events or completions after tick 1,000. The terminal state was:

- 8,900 completed packets and 1,100 unresolved packets.
- All unresolved packets were on `L0002` or queued at
  `boundary:L0002->L0006`.
- 400 unresolved packets remained in transit on `L0002`, with FIFO head
  `P9101` wanting movement `L0002->L0007`.
- 700 unresolved packets were queued for `L0002->L0006`.
- Downstream supply was available: `L0006` had 285 receiving slots and `L0007`
  had 390 receiving slots at the inspected terminal state.
- There were no active signal, governance, lane-group, or conflict-resource
  closures explaining the stop.
- The blocked-edge SCC analysis found no cyclic spillback component.
- The allocator rejected one active head packet as `not_selected_this_tick` and
  the remaining 389 terminal candidates as `upstream_fifo_blocked`.

The minimal reproducer is recorded as an expected-failure test:
`test_strict_fifo_allows_active_head_ahead_of_queued_tail`. It constructs one
upstream FIFO with active head `P1 -> L3` and queued tail `P2 -> L2`, both with
available downstream supply. The current Stage 2 allocator excludes the active
head merely because some queued request exists on the same upstream link, then
rejects the queued tail because the active head remains ahead in strict FIFO.
That creates a self-sustaining release deadlock.

Current profile use does not support these claims:

- It does not prove canonical Sioux Falls parity.
- It does not validate the full OD demand table.
- It does not provide empirical jam-density or backward-wave-speed calibration.
- It does not reproduce an independent Sioux Falls packet-LTM reference run.
- It does not resolve the lack of reviewed full-network junction metadata.
- It does not validate adaptive signals, lane changing, gap acceptance,
  roundabout-specific behaviour, weighted packets, or rerouting.

The remaining scientific blocker is no longer that the full Sioux Falls network
cannot initialize under the Stage 2 allocator. The remaining scientific blocker
is evidence quality: reviewed physical metadata or defensible benchmark
assumptions, reviewed junction semantics, and independent reference validation
before any canonical full-Sioux-Falls parity claim.

## Yperman Thesis

Deferred by user for this pass; not yet reproduced.

Source status: bibliographic citation identified as `Yperman, I. (2007). The
link transmission model for dynamic network loading. Ph.D. thesis, Katolieke
Universiteit Leuven.` The source audit found this citation in the reference
metadata for Osorio and Flotterod, `Capturing Dependency Among Link Boundaries
in a Stochastic Dynamic Network Loading Model`
(`https://doi.org/10.1287/trsc.2013.0504`).

Reproduction status: deferred by user for the current canonical-validation pass.

Deferral reason: no numerically specified thesis scenario has been extracted
into the repository yet, and the user explicitly parked this source for a later
pass. The source audit checked Crossref metadata for the exact thesis title and
the KU Leuven Lirias search endpoint. Crossref returned later LTM references
rather than a primary thesis record with scenario data; Lirias returned a
JavaScript catalogue shell rather than an extractable thesis record or
numerical example. The next validation step is to source the smallest Yperman
cumulative-count example with enough detail to recreate link parameters,
demand, capacities, storage, and time-step convention without forcing
agreement.

## de Souza Paper

Deferred by user for this pass; not yet reproduced.

Source status: likely paper identified as `de Souza, F., Verbas, O., Auld, J.,
and Tampere, C. M. J. (2025). A mesoscopic link-transmission-model able to
track individual vehicles. Simulation Modelling Practice and Theory`
(`https://doi.org/10.1016/j.simpat.2025.103088`).

Reproduction status: deferred by user for the current canonical-validation pass.

Deferral reason: source metadata identifies the likely reference, but no small
numerical validation scenario has been extracted from an accessible source, and
the user explicitly parked this source for a later pass. DOI resolution reaches
the Elsevier article landing page. The Elsevier text/plain API request returned
HTTP 400 minimized metadata for unauthorized access; the text/xml API request
returned HTTP 200 with zero content and an unauthorized minimized-metadata
warning. The next validation step is to review the full paper and choose the
smallest reproducible link or network scenario before making any UC comparison
claim.

These two statuses are also encoded as executable metadata in
`urban_cybernetics.canonical_validation.literature_sources` so the requested
literature references remain visible to tests and future validation work.

## Remaining Deferred Work Before Broader Literature Validation

- Source and encode at least one primary Yperman scenario, or archive the exact
  reason no numerical scenario can be reproduced from available thesis sources.
- Review and encode at least one de Souza scenario, or archive the exact reason
  no numerical scenario can be reproduced from the identified paper.
- Add reviewed comparison plots for any literature scenario where the paper or
  thesis presents cumulative curves.
- Keep any discrepancies classified as implementation bug, modelling choice,
  discretisation artefact, or unresolved discrepancy before moving to Sioux
  Falls parity validation claims that depend on those deferred sources.
