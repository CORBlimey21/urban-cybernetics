# Provenance-aware network compiler v1

## Status and boundary

This is the first bounded vertical slice of the Urban Cybernetics network compiler. It compiles explicit OSM-like fixture records into the existing immutable topology, movement, lane-group, and fixed-time-signal contracts. It does not download OSM data, compile Cork, or alter the frozen loading kernel.

The compiler version is `uc-network-compiler-v0.2.0`. Its source, normalized, physical-derivation, executable-semantic, configuration, ruleset, and evidence-bundle schemas are independently versioned.

## Pipeline

The implementation has five inspectable stages:

1. `adapt_osm_like` captures source records and raw fields as immutable evidence. Duplicate, malformed, and conflicting values remain present.
2. `normalize_source` parses units and primitive types into a separate normalized graph. Parsing does not choose simulation truth and does not mutate source evidence.
3. `compile_network` resolves link, movement, lane-group, and signal semantics with deterministic versioned rules and immutable compiler-time overrides.
4. Existing constructors validate canonical topology, junction movements, frozen lane-group resources, explicit queue partitions, fixed-time plans, topology binding, and loading-link numerics.
5. The compiler emits either an `ExecutableNetwork` plus a sealed `CompilerEvidenceBundle`, or a non-executable result with retained normalized evidence, partial resolutions, derivations, provenance, and stable diagnostics. Only `CompilationResult.require_executable()` exposes executable output.

The result disposition distinguishes:

- `executable`;
- `executable_with_warnings_or_defaults`;
- `unresolved_non_executable`;
- `structurally_invalid_source`;
- `internally_inconsistent_resolved_output`.

## Schemas

`SourceNetworkEvidence`, `SourceRecord`, and `SourceField` preserve source identity and canonical JSON representations of raw values. A field may be malformed or conflict with another field without being discarded.

`NormalizedSourceGraph`, `NormalizedRecord`, and `NormalizedField` retain both raw and parsed values, a parse status, and a parse note. Normalized records are ordered only for serialization and hashing; input traversal order is not semantic.

`ResolvedLink`, `ResolvedMovement`, and `ResolvedSemanticGraph` expose the selected simulation semantics before executable construction. Unresolved mandatory values remain visible here but are never passed to the loader.

`PhysicalDerivationRecord` (`uc.physical-derivation.v1`) is immutable and hash-sealed. Every record names its target artefact and field; source value and unit; normalized value and unit; executable value and unit; formula ID and version; rounding policy; lower and upper clamps; tick duration; explanatory reason; absolute and relative discretisation error; clamp activation; and deterministic derivation hash. The compiler therefore distinguishes three scientific layers:

- the physical source value as supplied by evidence, configuration, or override;
- the normalized continuous value used to define the compiled physical model;
- the discretised executable value admitted by the frozen integer/unit-packet loader contract.

The stable rounding-policy vocabulary is `none`, `ceil`, `floor`, `floor_then_minimum_one`, and `ceil_then_minimum_one`. A representation fallback is separate from a numerical derivation: it selects an executable queue/resource representation when evidence is insufficient for a more detailed one; it does not transform a physical measurement.

`ProvenanceRecord` is immutable and field-level. Each record includes the target artifact and field, resolved value if any, classification, evidence references, retained source value, rule ID and version, confidence class, reason, compiler version, configuration hash, optional override and prior value, and its own deterministic hash. The classifications are:

- `observed`: one valid, unambiguous source value;
- `inferred`: a deterministic transformation of evidence or topology;
- `defaulted`: a value explicitly permitted by compiler configuration;
- `overridden`: the selected immutable compiler override;
- `unresolved`: no safe executable value was established.

`CompilerDiagnostic` uses stable codes and the severities `info`, `warning`, `unresolved`, `structural_error`, `internal_consistency_error`, and `refusal`.

`CompilerOverride` targets one stable artifact field. The unique highest precedence wins. Equal-precedence different values are a structural conflict. Lower-precedence inputs remain in the bundle. An override records actor, source, reason, prior evidence, and replacement value. These artifacts are distinct from runtime signal override commands.

## Initial resolution rules

All rules are listed and hashed as `uc.network-resolution-rules.v2`.

| Semantic field | Rule order and exact applicability |
| --- | --- |
| Link identity/endpoints | Retain one explicit source ID, tail node, and head node. Missing or conflicting endpoints are unresolved. |
| Travel direction | Accept only an explicit `forward` directed arc in this slice. Other or missing direction values are unresolved. |
| Length | Use one positive observed `length_m`. There is no length default. |
| Lane count | Override; otherwise observed `lane_count` or `lanes:forward`; otherwise observed `lanes` when `oneway=true`; otherwise infer half of an even total when `oneway=false`; otherwise use a configured road-class default when enabled; otherwise refuse. |
| Free-flow speed | Override; otherwise one observed `speed_mps`, `maxspeed`, or `maxspeed_kph`, normalized to m/s; otherwise configured road-class default when enabled; otherwise refuse. |
| Capacity | Override; otherwise observed positive per-lane capacity; otherwise total observed capacity divided by resolved lanes; otherwise configured road-class per-lane default when enabled; otherwise refuse. |
| Jam density and backward-wave speed | Override; otherwise one positive observed value; otherwise the explicit scalar compiler default. |
| Loader fields | Retain continuous travel times, capacity, and storage, then separately derive loader lags, storage packets, and equal integer sending/receiving capacities with explicit formula, units, rounding, clamps, distortion, provenance, and hashes. |
| Turn permission | Override; otherwise one explicit permission or prohibition; otherwise infer permission from continuous directed topology when no restriction exists. Contradictory restrictions are unresolved. |
| Movement identity and priority | Derive stable `movement:upstream->downstream` identity and node continuity from topology. V1 defaults priority to one and reports that default field-by-field. |
| Detailed lane groups | Prefer complete explicit declarations. If every permitted movement on an approach has valid in-range lane indices, infer one resource per lane index. Partial or out-of-range detail is not invented. |
| Shared lane fallback | When detailed representation is active elsewhere and configuration permits it, compile one shared resource covering every permitted movement on an otherwise unsupported approach. This is **a conservative executable representation selected because detailed lane allocation is insufficiently supported by evidence**. It preserves approach FIFO and emits a warning; it is not an inference that the physical junction truly has a single shared lane group. |
| Fixed-time signals | Compile complete controller/node ownership, controlled movements, signal-group bindings, exact cycle, non-negative offset, stages, positive durations, and stage permissions. Stage durations must sum to the cycle. |
| Signal default | Only when `allow_default_signal_plans=true`, replace incomplete timing with one deterministic all-green stage of the configured cycle. Without that permission, the controller remains signalized and compilation refuses its plan. |

## Mandatory executable semantics

Every emitted directed link requires tail and head nodes, `forward` travel direction, positive length, positive directional lane count, positive free-flow speed, positive per-lane capacity, positive jam density, and positive backward-wave speed. The compiler also derives concrete free-flow lag, storage packets, and sending and receiving capacities before exposing the loader artifact.

Every emitted movement requires a unique stable identity, topological continuity, an explicit Boolean permission result, positive priority, and valid resource references. Prohibited movements remain in resolved semantics and provenance but are omitted from canonical executable movement declarations.

Every signalized controller requires one topology node, exclusive movement ownership, signal groups on every controlled movement, a positive exact cycle, non-negative offset, at least one positive-duration stage, stage permissions within controller ownership, and durations summing to the cycle.

Lane-group declarations require a known node, local incoming link, known permitted movements on that approach, positive service capacity, complete coverage of a partitioned approach, and compatibility with the existing frozen resource boundary.

## Physical formulas and executable discretisation

For link length `L_m`, lane count `n`, normalized free-flow speed `v_mps`, normalized backward-wave speed `w_mps`, per-lane capacity `q_lane_vph`, jam density `k_jam_veh_km_lane`, and tick duration `dt_s`, the compiler records:

| Quantity | Exact formula and executable policy |
| --- | --- |
| Normalized speed | km/h ÷ `3.6`; mph × `1.609344` ÷ `3.6`; direct m/s unchanged. |
| Continuous free-flow time | `t_ff_s = L_m / v_mps`. |
| Executable free-flow lag | `max(1, ceil(t_ff_s / dt_s))` ticks (`ceil_then_minimum_one`). |
| Continuous backward-wave time | `t_bw_s = L_m / w_mps`. |
| Executable backward-wave lag | `max(1, ceil(t_bw_s / dt_s))` ticks (`ceil_then_minimum_one`). |
| Continuous total capacity per hour | `q_total_vph = q_lane_vph × n`. |
| Continuous total capacity per tick | `q_tick = q_total_vph × dt_s / 3600`. |
| Executable sending capacity | `max(1, floor(q_tick))` unit packets/tick (`floor_then_minimum_one`). |
| Executable receiving capacity | `max(1, floor(q_tick))` unit packets/tick (`floor_then_minimum_one`). |
| Continuous finite storage | `storage_veh = (L_m / 1000) × n × k_jam_veh_km_lane`. |
| Executable finite storage | `max(1, floor(storage_veh))` unit packets (`floor_then_minimum_one`). |

For every discrete quantity, absolute error is `abs(executable - continuous)` and relative error is `absolute_error / abs(continuous)` when the continuous value is non-zero. The default relative-error warning threshold is `0.25` and is part of hashed compiler configuration. `UC.DISCRETIZATION.MINIMUM_ONE_CLAMP` is emitted whenever a minimum-one clamp activates; `UC.DISCRETIZATION.RELATIVE_ERROR` is emitted whenever relative error exceeds the configured threshold. The low-capacity minimum-one clamp is a numerical compatibility policy with measurable distortion, not a claim about physical capacity. The same continuous/discrete/error treatment applies to storage and lag.

## Conservative fallbacks and refusal

The permitted conservative lane fallback is a single shared approach queue. It does not claim lane-level truth. Road-class physical defaults and the optional fixed-time default are enabled only by hashed compiler configuration. No rule invents length, repairs arbitrary topology, treats an unresolved controller as unsignalized, or passes `None` into an executable artifact.

Compilation refuses on duplicate IDs; unknown endpoints; discontinuous or unknown turn references; contradictory turn restrictions; unresolved mandatory link fields; malformed mandatory values without another permitted rule; invalid or non-local lane-group references; incomplete detailed grouping when fallback is disabled; duplicate or conflicting overrides; unknown override targets; unknown controller nodes or movements; multiple controller ownership; conflicting signal groups; invalid stages; incomplete signal timing without an enabled default; or failure of an existing immutable artifact validator.

Structural source failures and unresolved semantics are reported separately. A failure produced only after apparently resolved output violates an existing contract is classified as internal inconsistency.

Refused inspection artefacts are not executable artefacts. A refused result may retain normalized evidence, a partially resolved graph, derivations for resolved links, provenance, diagnostics, and candidate topology/signal hash evidence for inspection. `CompilationResult` enforces `successful disposition ⇔ executable artefact exists` in `__post_init__`; ordinary construction and `dataclasses.replace` reject either inconsistent direction. Its executable field is private. `is_executable` requires both a successful disposition and validated artefact presence. `require_executable()` returns the artefact only after its executable topology and semantic hashes agree with the evidence bundle; otherwise it raises `CompilationNotExecutableError` containing the disposition and diagnostic codes. Evidence-bundle deserialisation enforces the same disposition/artefact invariant and rejects inconsistent or hash-divergent payloads.

## Deterministic identities and evidence bundle

Canonical JSON uses sorted keys, compact separators, UTF-8, and domain-separated SHA-256 hashes. Record order, field order, dictionary insertion order, and process state are non-semantic.

The hash domains are deliberately separate:

- `canonical_topology_artifact_hash` is the existing canonical-topology object identity. It retains that type's source metadata contract and is an artefact/audit reference, not the simulator compatibility key.
- `executable_topology_hash` covers behavior-consumed directed nodes, movements, resources, governance/FIFO declarations, loader link fields, model profile, tick duration, discretisation-policy version, and executable interpretation schema. It excludes source IDs and provenance.
- `executable_semantic_hash` is the compiler-to-run compatibility and scientific-equivalence identity. It covers `executable_topology_hash`; continuous normalized physical quantities and units; discrete loader values, rounding/clamps, and tick duration; lane-group representation and resource bindings; fixed-time controllers, stages, timing, permissions, signal groups, and ownership; and executable schema versions. It excludes raw representation, input ordering, unused metadata/configuration, diagnostics, explanatory provenance, and overrides that leave final executable semantics unchanged.
- `compilation_identity_hash` is the complete compilation/audit identity. It covers the executable semantic hash, raw and normalized evidence identities, complete compiler configuration and default/fallback permissions, compiler and ruleset versions, all rules, all overrides and precedence/prior evidence, derivations, provenance, diagnostics, disposition, candidate/executable artefact references, and complete normalized/executable payloads.
- `evidence_bundle_hash` seals the complete serialized envelope, including derivation, provenance, and diagnostic records plus the compilation identity. The compatibility alias `complete_result_hash` means `compilation_identity_hash`; new code should use the explicit name.

Consequently numeric `10` and textual `"10"` have the same executable semantic hash after valid normalization but different compilation identities because raw evidence differs. An unused fallback permission or warning threshold affects compilation identity but not executable semantics. A used default or value-changing override affects both. Canonically equivalent reordered evidence affects neither. Simulator compatibility must use `executable_semantic_hash`; reproducibility/provenance audits use `compilation_identity_hash` and `evidence_bundle_hash`.

`CompilerEvidenceBundle` contains the complete configuration/rules/evidence plus derivation, topology, signal, lane-group, executable-semantic, compilation-identity, and bundle hashes. Round-trip construction recomputes configuration, ruleset, normalized evidence, every derivation/provenance/diagnostic record, semantic payload hashes, compilation identity, and bundle identity. It cross-checks serialized loader fields and derivations against their semantic payloads before execution can be requested.

## Simulator contract

Successful compilation constructs the existing `CanonicalTopology`, `MovementSpec`, `LaneGroupExtensionConfig`, `ExplicitLaneGroup`, and `ResolvedFixedTimeSignalPlan` types. Simulator integration obtains them through `CompilationResult.require_executable()`. `CompiledNetworkLoadingEngine` composes the existing fixed-time signal mixin with the existing lane-group loading shell through their supported extension seams. The frozen event, sending, receiving, storage, allocator, replay, and conservation implementation is unchanged.

Fixture A proves a route across a controlled explicit-partition junction and a second junction carrying existing frozen lane-group resources. The test executes the plan, completes the packet, checks exact conservation and event/cache/count/queue consistency, reconstructs replay state, and compares an exact rerun.

## Fixtures

| Fixture | Expected outcome |
| --- | --- |
| A | Executable with warnings/defaults. Includes a fully observed link, observed speed with defaulted lanes, directional-lane inference, defaulted capacity, a speed override, observed prohibition, inferred legal movement, explicit partition, shared fallback, frozen resources, and complete fixed-time plan. |
| B | Non-executable unresolved signal plan. The missing stage duration is named exactly; source signalization is retained; no plan is emitted. |
| C | Deterministic rejection of contradictory permission/prohibition evidence. |
| D | Non-executable lane conflict without repair; executable with a field-review override. Both conflicting originals and the selected override/prior values remain auditable. |
| E | Fixture A in reversed record and field order. Source, normalized, executable-semantic, topology, signal, lane-group, provenance, diagnostics, compilation-identity, and evidence-bundle identities match A. |

## Current OSM boundary

The adapter accepts explicit OSM-like records and common primitive representations, including numeric strings and `maxspeed` in km/h or mph. It deliberately does not implement live download, OSM way splitting, relation assembly, reversible lanes, conditional/access restrictions, vehicle-class permissions, roundabout semantics, complex `turn:lanes`, destination-lane connectivity, placement, level/bridge separation, time-dependent restrictions, regional speed rules, lane-change mechanics, or real signal phase extraction.

A production ingestion layer should create the same source-evidence records rather than bypass semantic resolution.

## Research claims

Now supportable from this slice:

- bounded mixed-quality evidence can be compiled deterministically into the current simulator contracts;
- every emitted field in the covered slice is tied to evidence, a versioned rule/default, or an override;
- missing signal timing and contradictory turn evidence cause explicit refusal rather than silent guessing;
- compiler outputs and audit evidence are order-independent and tamper-evident;
- the compiled vertical-slice network executes with exact conservation and deterministic replay without changing the frozen kernel.

Still requiring experiments or broader implementation:

- empirical correctness or completeness on Cork OSM data;
- scalability, throughput, memory use, or incremental recompilation;
- accuracy of road-class defaults or inferred lanes against field observations;
- calibrated capacity, storage, signal timing, or behavioural realism;
- benefits of explicit lane groups or signal strategies at network scale;
- robustness across unsupported OSM tagging and junction forms.

## Next smallest real-network step

Export one manually bounded, non-roundabout Cork junction plus its immediate approaches from a pinned OSM snapshot. Add an ingestion-only adapter that preserves node/way/relation IDs and raw tags in the current source schema. Supply reviewed signal timing or leave the controller explicitly unresolved. Compile it with defaults disabled first, list the missing semantics, then add only documented configuration or overrides needed to obtain one executable route. This exercises real OSM identity and parsing without expanding into live download or city-scale compilation.
