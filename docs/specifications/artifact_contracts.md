**Status:** specification.
**Scope:** defines the required content and structure of every experiment artifact: run bundle, topology artifact, demand manifest, event logs, observation archive, decision logs, intervention logs, derived summaries, and validation reports.
**Non-scope:** does not define loading algorithms, routing policies, or observability mechanics.

---

### Purpose

An artifact is reproducible if an independent party, given only the artifact and the declared code version, can reconstruct the run or verify its outputs. Reproducibility is P11 of core_principles.md. This document specifies what each artifact must contain to satisfy that requirement.

---

### Run Bundle

Every experiment run produces a run bundle: a directory or structured archive containing all artifacts for that run. The run bundle is identified by the run_id.

**Required top-level fields in every run bundle:**

- run_id: stable unique identifier, assigned before the run begins
- created_at: ISO 8601 timestamp of run start
- topology_hash: hash of the canonical topology record used for this run
- manifest_hash: hash of the committed demand manifest
- config_snapshot: complete serialised run configuration (every parameter, declared explicitly; no defaults assumed)
- seed_registry: all random seeds by component name, registered before run start, immutable after registration
- code_version: git commit hash or equivalent version identifier
- schema_version: version of the artifact contract schema this bundle conforms to
- provenance_chain: list of upstream artifact IDs (prior run IDs, topology source IDs, manifest source IDs) that this run depends on

Two runs are scientifically comparable if and only if topology_hash, manifest_hash, config_snapshot, seed_registry, and code_version all match, or all differences are documented as the declared experimental variable.

---

### Topology Artifact

The topology artifact is a serialised record of the canonical topology used in the run. It must be sufficient to recompute the topology_hash independently.

**Required fields:** canonical link records (canonical_link_id, head_node_id, tail_node_id, length_metres, declared_static_capacity, free_flow_speed_mps, lane_count), canonical node records (canonical_node_id, latitude, longitude), OSM provenance metadata (osm_way_ids, osm_node_ids, osm_snapshot_date, bounding_box, filter_parameters), and the topology_hash itself.

**Forbidden fields:** travel_time_seconds, simulated_volume, live_occupancy_count, bpr_alpha, bpr_beta, any dynamic simulation field.

---

### Demand Manifest

The demand manifest is a committed input artifact. It must be immutable once committed and must be sufficient to reproduce the demand input independently of the run.

**Required fields per demand declaration:** demand_event_id (stable within manifest), origin_node_id (canonical), destination_node_id (canonical), departure_time (in declared units with units field), cohort_class, and any behavioural initialisation parameters declared for the cohort.

**Required manifest-level fields:** manifest_id, schema_version, generator_provenance (script version, input data sources, random seed used in generation), trip_count, departure_time_units, and manifest_hash.

**Forbidden fields:** selfish, routed, assigned, or any routing policy label on a demand declaration. Routing policy belongs in the experiment configuration, not the manifest.

---

### Raw Event Logs

Raw event logs are the primary output of a run. They must be preserved in full. Derived summaries may be discarded and recomputed; raw event logs may not.

**Packet lifecycle event log.** One record per packet lifecycle event: packet_id, event_type (instantiation, link_entry, link_exit, node_transfer, queue_entry, queue_exit, reroute, completion, cancellation), canonical_link_id or canonical_node_id, physical_timestamp (simulation tick), sequence_number.

**Governance intervention log.** One record per governance intervention: intervention_id, type, target_entity_id, parameter_values, action_time, visibility_time.

All raw event log files must include: run_id, schema_version, and log_type as header fields.

---

### Observation Frame Archive

The observation frame archive contains all published observation frames for the run. Frames are immutable; the archive is append-only.

**Required fields per frame:** frame_id, run_id, sensor_id, canonical_link_id and boundary_direction (or canonical_node_id), measurement_time, aggregation_window, publication_time, primary_count, noise_model, noise_params, noise_seed_reference, and any declared derived fields with their derivation formula and input frame IDs.

**Frame supersession.** If a frame is superseded by a corrected frame, the corrected frame carries a supersedes field referencing the original frame_id. The original frame is preserved and marked as superseded; it is not deleted.

---

### Routing Decision Log

**Required fields per decision entry:** decision_id, authority_id, decision_time, frame_ids_used (list), cohort_id or packet_id, route_assigned (ordered canonical link ID sequence), policy_parameters_used.

---

### Derived Summaries

Derived summaries are recomputable from raw event logs and must declare their derivation.

**Required fields per derived summary file:** run_id, schema_version, summary_type, derivation_formula (or reference to a versioned derivation script), input_log_ids (list of raw event log files used), aggregation_window (where applicable), boundary_direction (where applicable), counting_basis (where applicable), units.

Any derived summary that omits aggregation_window, boundary_direction, counting_basis, or units for a field named volume, flow, occupancy, travel_time, cost, or delay violates P12 and is invalid.

**I1 run outcome summaries.** A run outcome summary is an inspection artifact, not a provenance artifact and not an experiment result. It answers what happened in one run by deriving:

- realised packet travel-time metrics from instantiation and completion events;
- completion counts from canonical lifecycle history and loading-engine packet state;
- link entry and exit counts from LINK_ENTRY and LINK_EXIT events;
- experienced/free-flow ratios only for completed packets whose route free-flow metadata is available.

The summary artifact ID is recorded through the generic P1 output artifact index. P1 is not extended with inspection-specific fields.

**I2 bottleneck diagnostics.** A bottleneck diagnostics artifact is an
inspection artifact, not an experiment result. It answers what caused the run
outcome by deriving ranked packet, OD/group, route, link, and queue summaries
from canonical lifecycle events plus optional demand and route artifact
metadata. Queue waits are derived only from QUEUE_ENTRY and QUEUE_EXIT events.
Link delay contribution is an approximate realised traversal-time comparison
against static free-flow metadata where available; it does not infer speeds,
maps, assignment behaviour, or a competing source of physical truth.

---

### Validation Reports

A validation report compares run outputs against a reference dataset (observed count data, prior run outputs, or benchmark reference outputs).

**Required fields:** report_id, run_id, reference_dataset_id (with provenance), comparison_metric (GEH, RMSE, or other declared metric), scope (which links, which time windows), result_summary, and a declared validity statement (what scientific claim this comparison supports and what its limitations are).

A validation report that does not include a validity statement is a smoke test, not scientific evidence.

---

### Benchmark Reference Outputs

Outputs from legacy BPR or static assignment runs must be stored in a separate namespace (outputs/legacy_reference/) and must carry a header field legacy_reference: true and a field dynamic_model_output: false. They must not be stored alongside dynamic packet-LTM outputs in a way that allows them to be mistaken for current model results.

---

### Open Questions

- **Event log compression.** For large runs, full packet event logs may be large. What is the minimum log content that satisfies conservation verification and reproducibility? Can intermediate events be pruned if conservation can be verified from boundary events alone? → to be resolved before any large-scale run is attempted.
- **Manifest versioning.** If a manifest is corrected after initial commitment (schema error, unit error), how is the corrected manifest related to the original? Is it a new manifest with a new manifest_id, or a versioned update? → to be resolved before any manifest correction workflow is implemented.
- **Cross-run comparison artifacts.** When comparing two runs (experimental vs control), what additional metadata is required to document the comparison? → to be defined alongside the first multi-run experiment design.

---
