# Paper 1 closure boundary

## Status and scope rule

Paper 1 is now in closure mode. The importer is complete for Paper 1 when it
can deterministically compile the selected experimental networks, retain
field-level provenance for every behaviour-relevant semantic value, refuse
unresolved or contradictory executable semantics, and support the common OSM
constructs actually encountered by those selected networks.

The importer is not intended to support all OSM. New importer functionality
may be added before Paper 1 only when a selected, pinned experimental network
demonstrates that the functionality is required for correctness. Speculative
OSM coverage and unrelated simulator extensions are out of scope.

## Current importer contract

The validated implementation supports the Paper 1 constructs already
encountered by the pinned Boreenmanna export and compact fixtures:

- immutable OSM XML source identity, byte and parsed-content hashes;
- nodes, coordinates, ordered way-node references, ways, relations, tags,
  relation members, stable OSM identities, and malformed-reference refusal;
- explicit, reviewable operational-boundary extraction with classified
  retained and excluded records;
- ordinary directed and two-way vehicle ways, oneway directionality, divided
  carriageways, service/connectors, and simple access classification;
- deterministic way splitting at retained endpoints, junctions, control or
  restriction points, and operational-boundary cuts;
- geometry-derived WGS84 polyline lengths with source-to-segment mappings;
- common lane counts, directional-lane evidence, speed tags including km/h
  and mph, and preserved lane-related raw evidence;
- ordinary intersections, simple merges/diverges, candidate movements,
  immediate-reversal review, and relevant simple turn restrictions;
- signal/control evidence preservation and explicit refusal where OSM lacks
  controller ownership, movement bindings, phases, timing, or offsets;
- continuous physical values, loader-compatible discrete values, units,
  formulas, rounding/clamps, distortion diagnostics, and deterministic
  derivation hashes;
- explicit compiler defaults and reviewed overrides without reclassifying
  either as observed OSM evidence;
- conservative shared-FIFO fallback and explicit lane-group representation
  only where configured evidence supports them;
- structural non-executability, guarded `require_executable()`, executable
  semantic identity, compilation/audit identity, serialization, and tamper
  detection.

The Boreenmanna source-strict and reviewed-road packages correctly remain
non-executable because real controller timing and some representation
semantics are absent. The separate synthetic experiment candidate is
executable without changing that source finding.

## Explicitly unsupported or deferred

Unless a selected Paper 1 network proves one is required, the following are
future work:

- the complete OSM tagging language;
- conditional restrictions or conditional access;
- reversible lanes;
- the complete `turn:lanes` language and microscopic lane connectivity;
- complicated roundabouts;
- arbitrary public-transport semantics;
- pedestrian, bicycle, and multimodal simulation;
- live OSM download, replication, or Overpass synchronization;
- national-scale extraction or automatic hidden repair;
- inference of real signal phases, timing, or controller logic from OSM;
- movement-specific saturation-flow calibration without supporting evidence.

The exact remaining importer gaps are therefore case-dependent and not yet
known. They will be established by the second pinned real export, not guessed
in advance.

## Second pinned real unsignalised junction

The next external input is a manually supplied, immutable `.osm` export for a
real unsignalised T-junction, merge, or diverge. It should preferably be
non-roundabout, have straightforward one-way/two-way semantics, lane counts,
speed tags, simple legal movements, no conditional or reversible access, and
sufficient approach geometry for finite storage.

The existing `simple_unsignalized_diverge_fixture.osm` is synthetic OSM-like
test evidence. It validates the selection and pipeline contract only and must
not be described as a second real junction.

When the real file is supplied, the fixed workflow is:

```text
pinned OSM source
→ source-strict audit
→ unresolved report
→ explicit model-only physical defaults
→ reviewed executable candidate
→ deterministic smoke run
→ representation comparison where honestly supportable
```

No live source may be fetched and no case may be fabricated. Implementation
work is limited to importer gaps genuinely exposed by that pinned file.

## Evidence policy

Git retains compact pinned fixtures, deterministic schemas and runners,
tests, and manuscript-relevant documentation. Large forensic per-tick output,
transient profiles, caches, and machine-dependent intermediates remain under
the ignored `outputs/` boundary. Their versioned runners, configuration,
deterministic hashes, and compact CSV/JSON summaries provide regeneration and
audit linkage. Frozen benchmark evidence is never regenerated during Paper 1
closure.

## Closed subsystems for Paper 1

The following are finished unless a reproducible correctness defect is found:

- the frozen loading kernel and canonical event schema;
- executable/versioned routing architecture;
- fixed-time signal execution and audited runtime overrides;
- explicit lane-group queue partitioning;
- fractional-service V1;
- gate-aware fractional-service V2;
- discharge-readiness V3 and its readiness equations;
- V3 evidence modes and current performance architecture;
- the generic provenance and compiler refusal models;
- executable-semantic versus compilation/audit hash separation.

Paper 1 will not add V4 service dynamics, driver reaction distributions,
microscopic startup behavior, new routing-authority experiments, adaptive
signals, behavioral compliance/churn, governance experiments, emissions,
multimodal extensions, or another major simulator subsystem.

## Closure sequence

1. Split the current validated branch into coherent commits.
2. Receive the second pinned real unsignalised junction export.
3. Run it through source-strict compilation.
4. Implement only importer gaps genuinely required by that case.
5. Produce the reviewed executable candidate.
6. Freeze importer scope.
7. Define and preregister the final Paper 1 experiment matrix before running
   it.
8. Run the final experiments.
9. Run integrity and falsification checks.
10. Freeze final evidence and manifests.
11. Update Methods from the implementation.
12. Write and finalise Results from frozen evidence.
13. Finish Discussion and limitations.
14. Produce final figures and tables.
15. Tighten the Introduction and Abstract.
16. Cross-check every manuscript implementation claim.
17. Submit.

Further scope expansion is rejected unless a required experiment exposes a
correctness gap.
