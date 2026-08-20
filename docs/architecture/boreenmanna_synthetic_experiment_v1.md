# Boreenmanna synthetic representation experiment v1

## Claim boundary

This is a **controlled comparison of alternative traffic representations on pinned real-world geometry under synthetic control and demand assumptions**. It is not validation, calibration, or reconstruction of the real Boreenmanna Road–South Link controller.

The immutable OSM export supplies geometry, directionality, road classification, speeds, nine of ten lane counts, signal-head locations, and incomplete restriction evidence. Geometry is deterministically derived from OSM coordinates. Capacity, density, wave speed, one lane count, U-turn policy, queue partitions, movement-to-signal bindings, controller ownership, timing, and demand are either review-supplied or explicitly synthetic. Runtime gate and service-credit evidence remain separate from both.

The original compiler results remain intact:

- source-strict OSM audit: `unresolved_non_executable`;
- reviewed road candidate: valid road topology, signal-unresolved and non-executable;
- synthetic experiment candidate: `executable_with_warnings_or_defaults`.

The preserved full-export synthetic compilation package hash is
`c3740a2a658ae613b672fbc446f454ae9a0d98ac6715b2730cdcee925364ce60`.
It includes the external 905,366-byte OSM source inventory. The clean-checkout
package generated from the committed compact extraction fixture has hash
`9511409b044b479c750ea5ca5b58877176a6adbf787b834974c11e03182ac617`.
Both resolve to the same compilation identity and executable semantic hash;
the package-hash difference is the retained versus excluded source inventory.

Synthetic dossier hash: `3a84cb5186e6ef0aa50163bef091c0258eef0c4fef8a0a004de053cdbae839ad`.

Executable semantic hash: `db59ef926cebf67e32090a31955c6cd8471b545e4bace571f56031998173f3aa`.

Compilation identity: `659c437fd5bcaac5e3ef44a56953dc778d43daeee371a500b82d8b42c349ff9c`.

## Synthetic control and representation dossier

Every authored item uses `classification=synthetic_experiment`, a stable artefact ID, actor/source ID, scope, target field or movement, value, unit, reason, schema version, and deterministic item hash. Compiler provenance retains the same classification; no synthetic evidence is labelled observed or inferred from OSM.

The dossier contains 68 records:

| Kind | Count | Purpose |
| --- | ---: | --- |
| Experiment configuration | 1 | Two-second experimental tick |
| Controllers | 9 | Six OSM signal-head control points and three synthetic multi-movement control points |
| Ordered stages | 36 | Four stages per controller |
| Movement/signal bindings | 14 | Explicit synthetic movement ownership and grouping |
| Lane partitions | 8 | One synthetic lane-to-movement group for each movement on four two-lane diverging approaches |

The nine synchronized controller nodes are `10218634801`, `10218634802`, `10218634803`, `1116982191`, `1116982210`, `13900917292`, `322508227`, `367554319`, and `367554868`. The last three multi-movement control points are included to exercise alternative FIFO semantics; they are not claims about real controller boundaries.

Every controller uses this exact 40-tick, 80-second synthetic programme:

| Ordered stage | Ticks | Seconds | Permission |
| --- | ---: | ---: | --- |
| South Link green | 18 | 36 | Bound movements whose downstream link is trunk/trunk-link |
| Clearance one | 2 | 4 | No movements |
| Boreenmanna green | 15 | 30 | Bound movements whose downstream link is secondary |
| Clearance two | 5 | 10 | No movements |

Cycle length is 40 ticks, offset is zero, and the two clearance stages are all-red. This programme is internally coherent and deliberately simple; it is not intended to resemble the real controller.

The compiler emits eight declared synthetic single-movement groups. Other approaches receive the existing conservative shared-group fallback, producing 23 executable groups in total. Shared strict FIFO remains a conservative fallback; movement-partial FIFO is an experimental allocator representation; explicit groups depend on synthetic lane-to-movement allocation.

## Synthetic demand

Demand is deterministic, unit-packet, uncalibrated, and uses fixed seed zero. Seven routes cover east, north, and south origins plus through, turn, and slip movements:

- east to south;
- east to north;
- east via slip to south;
- South Link through;
- south to north;
- south to east;
- North Link through.

The moderate scenario contains 28 packets: four copies of each route departing at ticks 0–3, with a 120-tick horizon. The stress scenario contains 84 packets: twelve copies departing at ticks 0–11, with a 180-tick horizon. Demand scenario IDs, routes, departure ticks, units, reasons, and hashes are serialized independently of the compiler source evidence.

## Fractional service credit

`uc.fractional-service-credit.v1` is an opt-in shell above existing loading-engine continuous-capacity hooks. It modifies no frozen file and creates no new canonical physical event type. Allocation and physical events remain authoritative.

The extension needs two link-level accounts because sending and receiving have different retention semantics. No movement or lane-group fractional account is added: the compiler supplies continuous capacity only at link level, while movement, conflict, signal, and lane-group constraints remain integer allocation gates.

For link rate `c` at tick `t`:

Sending:

1. opening fractional remainder is in `[0,1)`;
2. add `c` before allocation;
3. expose `floor(opening + c)` whole services;
4. retain only `(opening + c) mod 1`;
5. unused whole sending service expires.

Receiving:

1. expose `floor(opening_credit)` whole entries;
2. allocator and storage constraints select transfers;
3. subtract only physically executed link entries;
4. add `c` after the tick;
5. cap closing credit at `ceil(c)+1`.

There is no reservation ledger outside the allocator. If a proposed transfer does not become a physical entry, receiving credit is not consumed. Sending whole credit is not banked after an empty queue, red signal, blocked movement, or failed receiving constraint. Fractional phase continues deterministically. Receiving credit may accumulate during closure, but only to the explicit de Souza-compatible bound. Shared downstream receiving credit remains the merge competition domain; existing priority and deterministic allocation order remain authoritative.

Credit evidence records account/resource ID, tick, allowance, opening credit, whole service, physical consumption, closing credit, cap/saturation, linked packet IDs, policies, configuration hash, and executable semantic hash. Exact rerun reproduces physical events, allocation traces, signal gates, lane assignments, credit balances, and terminal state.

Legacy mode retains the compiler's integer declarations. Fractional mode consumes continuous compiler capacities. Their extension configuration and run identities are distinct while referencing the same executable semantic network.

## Controlled comparison

The preserved full-export-linked matrix hash is
`3d493f7306f4a7766393fe41cb83f26d4dd0b83e233456f9ccb50b4f7d61920f`.
The clean-checkout compact-fixture matrix hash is
`b2f1be3f69ee271cf6b7db2a260207816d49fbbfc7d1f1f2c82ec269e366ebcf`.
All twelve canonical event hashes and reported physical outcomes are identical;
the matrix identity changes because it includes the parent compilation-package
identity.

All twelve cases use identical geometry, physical assumptions, synthetic plan, demand, tick duration, seed, and horizon within each scenario. Only representation and service-credit mode vary.

| Scenario | Capacity mode | Representation | Completed | Incomplete | Mean queue delay (ticks) | Peak queue | Events |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| Moderate | Fractional | Explicit groups | 28 | 0 | 11.455 | 2 | 458 |
| Moderate | Fractional | Movement partial | 28 | 0 | 12.897 | 2 | 450 |
| Moderate | Fractional | Shared strict | 17 | 11 | 17.000 | 2 | 363 |
| Moderate | Legacy | Explicit groups | 23 | 5 | 14.120 | 2 | 404 |
| Moderate | Legacy | Movement partial | 23 | 5 | 14.708 | 2 | 402 |
| Moderate | Legacy | Shared strict | 17 | 11 | 17.261 | 2 | 356 |
| Stress | Fractional | Explicit groups | 60 | 24 | 13.071 | 2 | 1,119 |
| Stress | Fractional | Movement partial | 60 | 24 | 15.338 | 2 | 1,102 |
| Stress | Fractional | Shared strict | 35 | 49 | 18.245 | 2 | 796 |
| Stress | Legacy | Explicit groups | 48 | 36 | 15.441 | 2 | 958 |
| Stress | Legacy | Movement partial | 48 | 36 | 16.286 | 2 | 952 |
| Stress | Legacy | Shared strict | 35 | 49 | 17.477 | 2 | 776 |

At the fixed horizons, explicit partitions reduce queue delay relative to movement-partial, while shared strict FIFO blocks following movements and completes substantially fewer packets. These are architecture outcomes under the authored plan/demand, not empirical traffic claims.

The legacy/fractional comparison is mixed by design. At a two-second tick, a 1,500 veh/h two-lane link has continuous allowance `1.6667` but legacy floor service `1`, so legacy execution understates that link. A 1,500 veh/h one-lane link has continuous allowance `0.8333` but legacy minimum-one service `1`, so legacy execution overstates it. The matrix measures the network-level combination rather than describing every clamped link as inflation. Fractional mode completes more packets here because recovery of truncated multi-lane service dominates removal of inflated sub-unit service.

Machine-dependent first-run wall times ranged from 2.86 to 7.40 seconds and measured peak Python memory from 4.1 to 32.6 MB. Deterministic evidence counts are more portable: fractional moderate runs contain 5,280 credit records and fractional stress runs 7,920; legacy runs contain none. Canonical event counts appear in the table. Machine timings and memory are serialized but excluded from deterministic run hashes.

All cases pass conservation, materialized-event cache validation, cumulative-count consistency, and exact replay.

## Smaller junction selection

The attached export contains no self-contained multi-movement junction whose retained approaches avoid signal-control evidence. No live data was fetched. A second pinned real export is still required.

The repository therefore includes `simple_unsignalized_diverge_fixture.osm`, a clearly synthetic OSM XML fixture implementing the selection contract: one two-lane approach, two one-lane branches, explicit one-way direction, lanes and 50 km/h speeds, no signal, roundabout, conditional access, or reversible lane.

Fixture SHA-256: `2a525921bd271ae122b793e1cfdb51b6e61048f8b7eb624bc2aad93c87217a50`.

Its source-strict pass refuses only missing model-specific physical fields. Review-supplied capacity/density/wave defaults produce an executable unsignalised network with semantic hash `0ca5efbf584876a1f9b9e2f701cca14bdb92be4a9abe83c3f8c2445d69126696`. A four-packet shared-FIFO smoke run completes all packets and passes conservation/replay-facing consistency checks. Explicit or movement-partial lane claims are not made because the fixture has no lane-to-turn allocation evidence.

Small-junction deterministic package hash: `3715d6e786cbb8563b1e96be7c82666ebf3340b972b3d441b00e81a46af3675d`. Machine-dependent timing and memory measurements are carried in the file but excluded from this identity.

## Limitations and next step

The Cork geometry remains uncalibrated. Physical priors, controller plan, movement bindings, lane partitions, demand, and the three added multi-movement control points are not observed. OSM restriction evidence remains incomplete. The two-second tick is an experiment design choice. Fractional v1 supports static link allowances only and relies on existing integer movement/lane/conflict resources. Timing and memory figures are single-machine measurements, and no statistical generality follows from one geometry and one deterministic demand realization.

The next scientific step is to acquire immutable field-reviewed movement/control evidence and one observed timing sheet, plus a second pinned unsignalised-junction export. Then freeze a preregistered scenario matrix, calibrate only the physical parameters for which measurements exist, and repeat the representation/service-credit comparison with sensitivity bands rather than a single synthetic demand realization.

The separate `boreenmanna_integrity_audit_v1.md` preserves this v1 table as its
parent evidence and adds drain-to-empty, phase sensitivity, representation
parity, analytical periodic gating, and evidence-scaling results.
