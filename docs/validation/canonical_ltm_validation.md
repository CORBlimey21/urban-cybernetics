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
- No new node families.
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
- `parity_profile_full_topology_initialization`: fail. Full Sioux Falls cannot
  currently initialize under `parity_ltm_v1` because the minimal M6 node family
  rejects multi-input/multi-output Sioux Falls nodes, for example `N001`.
- `parity_commodity_evidence`: not run, because full-topology parity
  initialization fails first.
- `parity_spillback_evidence`: not run, because full-topology parity
  initialization fails first.
- `legacy_profile_readiness_stress_run`: pass, labelled explicitly as
  readiness/stress evidence only. It uses `legacy_packet_ltm_style`, so it is
  not parity evidence.

Therefore the current machine-readable evidence label is
`sioux_falls_readiness_stress_only`, and `can_run_as_parity_ltm_v1` is false.
No kernel bug is indicated by the readiness check. The failures are benchmark
metadata and scope constraints, not demonstrated loading-mechanics defects.

Before true Sioux Falls parity validation, the project needs:

- Reviewed Sioux Falls physical metadata or documented benchmark assumptions for
  jam density and backward-wave speed, plus consistency with the triangular FD
  and storage/timestep gates.
- A benchmark-loader path that can construct parity-eligible loading links from
  those physical parameters without using legacy storage overrides as evidence.
- A node-family decision for full Sioux Falls multi-input/multi-output nodes, or
  a documented restriction to a parity-supported subnetwork. Adding new node
  families is outside the current Phase II readiness scope.
- Successful `parity_ltm_v1` full-topology initialization before commodity,
  route-count, travel-time, spillback, and external-validation claims are
  allowed.

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
