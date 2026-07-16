# Parity Kernel Status After M0-M7 and Stage 2 Nodes

> Superseded status snapshot. This document records the pre-M8 state and its
> 507-test baseline. As of 2026-07-16, de Souza Figures 5, 7, 8, and 9 have
> completed observational comparisons, the freeze closure is 686 tests plus 88
> subtests (the accepted pre-freeze baseline was 682), and the base kernel is
> frozen by
> `docs/architecture/loading_kernel_freeze_contract_v1.md`. Historical
> statements below that call de Souza deferred or externally unvalidated are
> not current claims. Full Sioux Falls and empirical parity remain deferred.

Status: current implementation summary after M0-M7 and Stage 2 movement allocation.

Scope: this document summarizes what the UC parity kernel can safely claim today, what is internally verified, and what remains blocked before full benchmark parity validation. It does not introduce new requirements, mechanics, validation fixtures, or benchmark claims.

Verification snapshot:

- Full test suite: `507 passed`.
- Diff hygiene: `git diff --check` passed.
- No external Sioux Falls parity validation is claimed by this document.

## What the Parity Kernel Now Supports

The `parity_ltm_v1` profile now has a profile-gated packet LTM kernel covering the M0-M7 implementation scope:

- parity claim/status vocabulary and evidence labels;
- resolved static physical-parameter eligibility checks for triangular-FD-style metadata;
- event-derived aggregate cumulative boundary counts;
- route-disaggregated cumulative counts where immutable route intent exists;
- packet boundary ordinals tied to canonical event sequence order;
- replayable count projections from canonical events;
- lagged parity sending with FIFO prefix selection and bounded integer capacity carry;
- lagged parity receiving and backward-vacancy supply with bounded integer receiving carry;
- physical shortage and governance closure as distinct receiving causes;
- read-only delayed spillback evidence for simple validated cases;
- Stage 2 movement allocation for one-to-one, strict route-encoded diverge, declared-priority merge, and declared MIMO movement sets;
- conflict-resource, lane-group, signal-gate, movement-closure, and partial-FIFO metadata paths for supported junction semantics;
- explicit rejection boundaries for unsupported advanced semantics;
- unit-packet multi-commodity evidence based on immutable route intent;
- route travel-time curves for completed non-rerouted unit packets.

Legacy loading behaviour remains available outside the parity profile and is not parity evidence by default.

## What Is Verified Internally

The current internal verification is strong for implementation invariants and synthetic/reference behaviours:

- canonical event logs remain physical truth;
- packet identity is preserved;
- topology does not store live loading state;
- count projections, route counts, ordinals, and replay checks are derived from canonical events;
- parity sending and receiving fixtures pass under the declared discrete-tick convention;
- delayed spillback fixtures pass for the currently supported scope;
- Stage 2 allocator tests cover one-to-one movements, strict diverges, priority merges, simple MIMO cases, resource gates, lane-group gates, signal gates, closures, conservation, and deterministic traces;
- M7 commodity tests cover unit-packet route disaggregation, ordinal correspondence, route travel-time curves, high-commodity fixtures, and legacy-profile non-evidence;
- parity torture tests cover deterministic regressions, randomized small-case invariants, synthetic stress, commodity evidence, and Sioux Falls regression bookkeeping;
- canonical analytical fixtures reproduce six recognised textbook/LTM behaviours exactly under the repository's discrete integer-packet convention.

The current full suite passes: `507 passed`.

## What Remains Unvalidated Externally

The kernel has not yet been externally validated against an independent full benchmark implementation or full primary-source numerical scenario.

Not safe yet:

- full Sioux Falls parity validation;
- Anaheim, Los Angeles, Cork, or other city-scale parity claims;
- empirical calibration claims;
- equivalence to Yperman 2007 or de Souza et al. 2025;
- adaptive signals, lane changing, gap acceptance, roundabout-specific behaviour, or weighted-packet LTM claims;
- rerouting or dynamic route-choice parity;
- performance or reproducibility claims at scale beyond the tested regression/readiness scope.

The current canonical validation document records Yperman 2007 and de Souza et al. 2025 as deferred, not reproduced.

## What Blocks Full Sioux Falls Parity Validation

Full Sioux Falls is currently readiness/stress evidence only. The current readiness label is `sioux_falls_readiness_stress_only`, and `can_run_as_parity_ltm_v1` is false.

Known blockers:

- the committed full Sioux Falls topology lacks `backward_wave_speed_mps`;
- the committed full Sioux Falls topology lacks `jam_density_veh_per_km_per_lane`;
- the physical gate reports 152 missing-metadata reasons across 76 links;
- reviewed full-network junction semantics metadata is missing;
- commodity and spillback parity gates are not run on the full topology because physical and junction metadata are not parity-eligible.

The Stage 2 allocator can initialize the full Sioux Falls topology, so the current blocker is not "MIMO architecture cannot load." The blocker is missing reviewed benchmark metadata and semantics needed to make a defensible parity claim.

## Data and Metadata Work, Not Architecture Work

The next full-Sioux-Falls-enabling work is mostly data and benchmark curation:

- source or justify backward-wave speed assumptions for each benchmark link;
- source or derive jam-density assumptions with provenance;
- check triangular-FD consistency and timestep/storage admissibility from those assumptions;
- add benchmark-loader paths that construct parity-eligible links without using legacy storage overrides as evidence;
- review and encode junction semantics: movement sets, conflict resources, lane groups, signal groups, and governance-controlled movement gates;
- preserve provenance labels distinguishing empirical metadata, benchmark assumptions, and non-evidence stress defaults.

Those tasks may reveal kernel bugs, but they are no longer primarily about inventing a node architecture.

## What Remains Before M8/M9

Before M8:

- freeze the canonical validation gate for the implemented M0-M7 scope;
- add or ingest independent reference fixtures where enough primary-source numerical detail exists;
- define exact versus bounded-error comparisons for each accepted fixture;
- classify any discrepancy as implementation bug, modelling choice, discretisation artefact, or unresolved discrepancy;
- keep deferred literature sources deferred until a reproducible scenario is actually encoded;
- run the full M0-M7 parity evidence bundle under `parity_ltm_v1`.

Before M9:

- complete M8 first;
- define kernel version and evidence-bundle boundaries;
- run reproducibility checks with artifact digests;
- establish memory/runtime budgets and scale ladders;
- treat Sioux Falls, Anaheim, Cork, Los Angeles, or similar benchmarks as scale/reproducibility evidence only after the validation gate permits that label.

## Safe Claims

The following claims are safe today:

- UC has a profile-gated `parity_ltm_v1` packet LTM kernel covering M0-M7 mechanics.
- Canonical events remain the physical source of truth.
- Aggregate counts, route counts, ordinals, and route travel-time curves are derived evidence, not independent state.
- Stage 2 movement allocation is the current parity node architecture.
- The old minimal M6 node-family framing has been superseded by movement allocation.
- The full test suite currently passes.
- Full Sioux Falls can initialize under the allocator as readiness evidence.
- A supported Sioux Falls subnetwork is parity-ready under documented benchmark assumptions.
- Full Sioux Falls parity validation is currently blocked by missing physical and junction metadata, not by the absence of a MIMO allocator.

## Claims Not Safe Yet

The following claims are not safe yet:

- UC has achieved full academic LTM parity.
- UC has externally validated full Sioux Falls parity.
- Sioux Falls readiness/stress results are scientific validation results.
- The supported Sioux Falls subnetwork proves full Sioux Falls.
- Current synthetic and analytical fixtures prove all literature cases.
- Deferred Yperman 2007 or de Souza et al. 2025 scenarios have been reproduced.
- The kernel supports weighted packets, rerouting parity, adaptive signal control, lane changing, gap acceptance, or roundabout-specific traffic behaviour.
- Legacy-profile runs are parity evidence.
- Benchmark assumptions are empirical calibration.

## Bottom Line

The architecture and internal M0-M7 mechanics are now in place for a serious M8 validation gate. The remaining full-Sioux-Falls blocker is primarily reviewed benchmark data and junction metadata, plus independent validation evidence, not another core loading or node-model redesign.
