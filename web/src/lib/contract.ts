import { z } from "zod";
import contractEnums from "../contract-enums.json";
import v2ContractEnums from "../v2-contract-enums.json";

const literalUnion = <T extends readonly [string, ...string[]]>(values: T) =>
  z.enum(values);

export const semanticStatusSchema = literalUnion(
  contractEnums.semantic_status as [string, ...string[]],
);
export const runStatusSchema = literalUnion(
  contractEnums.run_status as [string, ...string[]],
);
export const packetReplayStatusSchema = literalUnion(
  contractEnums.packet_replay_status as [string, ...string[]],
);
export const fieldAvailabilitySchema = literalUnion(
  contractEnums.field_availability as [string, ...string[]],
);
export const layoutKindSchema = literalUnion(
  contractEnums.layout_kind as [string, ...string[]],
);
export const layoutOriginSchema = literalUnion(
  contractEnums.layout_origin as [string, ...string[]],
);

export const descriptorSchema = z.object({
  semantic_status: semanticStatusSchema,
  source: z.string(),
  units: z.string().nullable(),
  time_basis: z.string().nullable(),
  counting_basis: z.string().nullable(),
  boundary_direction: z.string().nullable(),
  aggregation_window_ticks: z.number().int().nullable(),
});

export const runSchema = z.object({
  run_id: z.string(),
  scenario_name: z.string(),
  status: runStatusSchema,
  status_reason: z.string(),
  topology_id: z.string(),
  topology_hash: z.string(),
  configuration_id: z.string(),
  configuration_hash: z.string(),
  model_profile_id: z.string(),
  tick_duration_seconds: z.number().positive(),
  simulation_time_basis: z.literal("integer_physical_tick"),
  start_tick: z.number().int().nonnegative(),
  end_tick: z.number().int().nonnegative(),
  event_count: z.number().int().nonnegative(),
  packet_count: z.number().int().nonnegative(),
  created_at: z.string().nullable(),
});

export const runListSchema = z.array(
  runSchema.extend({
    validation_status: z.enum(["not_run", "passed", "failed"]),
  }),
);

export const linkSchema = z.object({
  link_id: z.string(),
  tail_node_id: z.string(),
  head_node_id: z.string(),
  source_link_id: z.string(),
  length_m: z.number().nullable(),
  lane_count: z.number().int().nullable(),
  free_flow_speed_mps: z.number().nullable(),
  capacity_veh_per_hour_per_lane: z.number().nullable(),
  jam_density_veh_per_km_per_lane: z.number().nullable(),
  backward_wave_speed_mps: z.number().nullable(),
  field_availability: z.record(z.string(), fieldAvailabilitySchema),
});

export const nodeSchema = z.object({
  node_id: z.string(),
  source_node_id: z.string(),
  incoming_link_ids: z.array(z.string()),
  outgoing_link_ids: z.array(z.string()),
  movement_ids: z.array(z.string()),
  fifo_policy: z.string(),
});

export const movementSchema = z.object({
  movement_id: z.string(),
  node_id: z.string(),
  upstream_link_id: z.string(),
  downstream_link_id: z.string(),
  priority_weight: z.number().int(),
  lane_group_ids: z.array(z.string()),
  conflict_resource_ids: z.array(z.string()),
  signal_group_id: z.string().nullable(),
});

export const packetSchema = z.object({
  packet_id: z.string(),
  demand_id: z.string(),
  origin_node_id: z.string().nullable(),
  destination_node_id: z.string().nullable(),
  route_id: z.string().nullable(),
  route_intent: z.array(z.string()),
  cohort_id: z.string().nullable(),
  authority_id: z.string().nullable(),
  packet_unit_weight: z.number().int(),
  field_availability: z.record(z.string(), fieldAvailabilitySchema),
});

export const eventSchema = z.object({
  sequence_number: z.number().int().nonnegative(),
  packet_id: z.string(),
  event_type: z.enum([
    "instantiated",
    "link_entry",
    "link_exit",
    "queue_entry",
    "queue_exit",
    "completed",
    "cancelled",
  ]),
  entity_id: z.string(),
  physical_tick: z.number().int().nonnegative(),
});

export const replayPacketSchema = z.object({
  packet_id: z.string(),
  status: packetReplayStatusSchema,
  current_link_id: z.string().nullable(),
  queue_boundary_id: z.string().nullable(),
  realised_path: z.array(z.string()),
  last_event_sequence: z.number().int().nullable(),
});

export const replayLinkSchema = z.object({
  link_id: z.string(),
  packet_ids: z.array(z.string()),
  queued_packet_ids: z.array(z.string()),
  occupancy_packets: z.number().int().nonnegative(),
  cumulative_entries: z.number().int().nonnegative(),
  cumulative_exits: z.number().int().nonnegative(),
});

export const replayStateSchema = z.object({
  descriptor: descriptorSchema,
  tick: z.number().int().nonnegative(),
  applied_through_sequence: z.number().int().nullable(),
  packets: z.array(replayPacketSchema),
  links: z.array(replayLinkSchema),
  queues: z.array(z.object({ boundary_id: z.string(), packet_ids: z.array(z.string()) })),
  counts: z.object({
    not_yet_observed: z.number().int().nonnegative(),
    in_transit: z.number().int().nonnegative(),
    queued: z.number().int().nonnegative(),
    completed: z.number().int().nonnegative(),
    cancelled: z.number().int().nonnegative(),
  }),
});

export const networkLayoutSchema = z.object({
  schema_version: z.literal("uc.visualisation.layout.v1"),
  layout_id: z.string().min(1),
  label: z.string().min(1),
  kind: layoutKindSchema,
  version: z.string().min(1),
  preferred: z.boolean(),
  is_geographic: z.boolean(),
  coordinate_basis: z.string(),
  coordinate_units: z.string(),
  source: z.string(),
  provenance: z.string(),
  origin: layoutOriginSchema,
  generated_by: z.string().nullable(),
  deterministic_seed: z.number().int().nullable(),
  crs: z.string().nullable(),
  node_coordinates: z.record(z.string(), z.tuple([z.number(), z.number()])),
  edge_routes: z.record(z.string(), z.array(z.tuple([z.number(), z.number()]))),
  warnings: z.array(z.string()),
  distance_semantics: z.string(),
  angle_semantics: z.string(),
}).superRefine((layout, context) => {
  if (layout.kind === "geographic" && (!layout.is_geographic || !layout.crs)) {
    context.addIssue({ code: "custom", message: "Geographic layouts require is_geographic and CRS." });
  }
  if (layout.kind !== "geographic" && layout.is_geographic) {
    context.addIssue({ code: "custom", message: "Only geographic layouts may declare geographic coordinates." });
  }
  if (layout.origin === "generated" && !layout.generated_by) {
    context.addIssue({ code: "custom", message: "Generated layouts require generator identity." });
  }
  if (layout.kind === "generated_schematic" && layout.deterministic_seed === null) {
    context.addIssue({ code: "custom", message: "Generated layouts require a deterministic seed." });
  }
});

export const manifestSchema = z.object({
  schema_version: z.literal("uc.visualisation.run.v1"),
  run: runSchema,
  provenance: z.object({
    descriptor: descriptorSchema,
    code_version: z.string().nullable(),
    input_artifact_ids: z.array(z.string()),
    source_name: z.string(),
    source_format: z.string(),
    source_file_sha256: z.string(),
    interpretation_assumptions: z.array(z.string()),
    config_snapshot: z.record(z.string(), z.unknown()),
  }),
  topology: z.object({
    descriptor: descriptorSchema,
    topology_id: z.string(),
    topology_hash: z.string(),
    nodes: z.array(nodeSchema),
    links: z.array(linkSchema),
    movements: z.array(movementSchema),
  }),
  packets_descriptor: descriptorSchema,
  packets: z.array(packetSchema),
  validation: z.object({
    descriptor: descriptorSchema,
    overall_status: z.enum(["not_run", "passed", "failed"]),
    checks: z.record(z.string(), z.enum(["not_run", "passed", "failed"])),
    notes: z.array(z.string()),
  }),
  presentation: z.object({
    descriptor: descriptorSchema,
    layout_schema_version: z.literal("uc.visualisation.layout.v1").nullable().optional(),
    default_layout_id: z.string().nullable().optional(),
    layouts: z.array(networkLayoutSchema).optional().default([]),
    layout_kind: z.enum(["synthetic_declared", "synthetic_deterministic"]),
    layout_note: z.string(),
    node_positions: z.record(z.string(), z.tuple([z.number(), z.number()])),
    interpolation_note: z.string(),
  }),
});

export const eventsResponseSchema = z.object({
  descriptor: descriptorSchema,
  events: z.array(eventSchema),
  start_sequence: z.number().int(),
  next_sequence: z.number().int().nullable(),
  total_event_count: z.number().int(),
});

export const replayResponseSchema = z.object({
  states: z.array(replayStateSchema),
  start_tick: z.number().int(),
  end_tick: z.number().int(),
  run_end_tick: z.number().int(),
});

export const cumulativeSeriesSchema = z.object({
  descriptor: descriptorSchema,
  link_id: z.string(),
  ticks: z.array(z.number().int()),
  cumulative_entries: z.array(z.number().int()),
  cumulative_exits: z.array(z.number().int()),
  storage_packets: z.array(z.number().int()),
});

export const finalBundleSchema = manifestSchema.extend({
  event_stream: z.object({ descriptor: descriptorSchema, events: z.array(eventSchema) }),
  replay_states: z.array(replayStateSchema),
  cumulative_link_series: z.array(cumulativeSeriesSchema),
});

export const lifecycleStateSchema = literalUnion(v2ContractEnums.run_lifecycle_state as [string, ...string[]]);

export const artifactSchema = z.object({
  artifact_format: literalUnion(v2ContractEnums.artifact_format as [string, ...string[]]),
  run_id: z.string(),
  title: z.string(),
  description: z.string(),
  contract_version: z.string(),
  topology_id: z.string(),
  topology_hash: z.string(),
  physical_profile_id: z.string(),
  profile_hash: z.string(),
  demand_source_id: z.string(),
  demand_hash: z.string(),
  seed: z.number().int(),
  status: z.string(),
  stop_reason: z.string().nullable(),
  created_at: z.string().nullable(),
  updated_at: z.string().nullable(),
  validation_status: z.string(),
  configuration_hash: z.string(),
  event_count: z.number().int().nonnegative(),
  final_tick: z.number().int().nonnegative(),
  counts: z.record(z.string(), z.number().int().nonnegative()),
  assumption_warnings: z.array(z.string()),
});
export const artifactListSchema = z.array(artifactSchema);

export const catalogueResourceSchema = z.object({
  resource_id: z.string(), kind: z.string(), name: z.string(), description: z.string(),
  provenance: z.string(), classification: z.string(), warnings: z.array(z.string()),
  compatible_topology_ids: z.array(z.string()), compatible_profile_ids: z.array(z.string()),
  parameters: z.array(z.object({
    parameter_id: z.string(), name: z.string(), description: z.string(), units: z.string().nullable(),
    default: z.union([z.string(), z.number(), z.boolean()]).nullable(), minimum: z.number().nullable(), maximum: z.number().nullable(),
  })),
});
export const resourceCatalogueSchema = z.object({
  schema_version: z.literal("uc.visualisation.control.v2"), resources: z.array(catalogueResourceSchema),
});

export const runRequestSchema = z.object({
  schema_version: z.literal("uc.visualisation.control.v2").default("uc.visualisation.control.v2"),
  topology_id: z.string(), physical_profile_id: z.string(), demand_source_id: z.string(),
  requested_packet_count: z.number().int().min(1).max(1000),
  packet_selection_policy_id: z.string().default("canonical_prefix_v1"), seed: z.number().int().nonnegative(),
  tick_policy_id: z.string(), requested_tick_duration_seconds: z.number().positive().nullable(),
  runtime_limit_seconds: z.number().positive(), tick_limit: z.number().int().positive(),
  completion_policy_id: z.string().default("all_instantiated_packets_terminal_v1"),
  stop_policy_id: z.string().default("bounded_tick_or_wall_time_v1"),
  validation_policy_id: z.string().default("core_integrity_v1"), replay_policy_id: z.string().default("exact_if_complete_v1"),
  persistence_policy_id: z.string().default("retain_all_evidence_v1"), run_label: z.string().nullable(), note: z.string().nullable(),
});

export const liveMessageSchema = z.object({
  schema_version: z.literal("uc.visualisation.control.v2"), message_id: z.number().int(), run_id: z.string(),
  message_type: z.string(), occurred_at: z.string(), lifecycle_state: lifecycleStateSchema,
  payload: z.record(z.string(), z.unknown()),
});

export const movementEvidenceSchema = z.object({
  schema_version: z.literal("uc.visualisation.movement-trace.v1"), run_id: z.string(), tick: z.number().int(),
  junction_id: z.string(), allocator_id: z.string(), movement_spec_hash: z.string().nullable(),
  semantic_sources: z.record(z.string(), z.string()),
  movements: z.array(z.object({
    movement_id: z.string(), upstream_link_id: z.string(), downstream_link_id: z.string(),
    request_packet_ids: z.array(z.string()), upstream_fifo_packet_ids: z.array(z.string()), approved_packet_ids: z.array(z.string()),
    rejected_packet_reasons: z.array(z.tuple([z.string(), z.string()])), receiving_supply_packets: z.number().int().nullable(),
    movement_capacity_packets: z.number().int().nullable(), lane_group_constraints: z.record(z.string(), z.number().int()),
    conflict_resource_constraints: z.record(z.string(), z.number().int()), signal_state: z.enum(["open", "closed", "not_declared"]),
    governance_state: z.string().nullable(), resulting_canonical_event_sequences: z.array(z.number().int()),
  })),
});

export const evidenceSourceSchema = z.enum(["canonical", "event_derived", "engine_exported", "analytical_reference", "validation_output", "presentation_only"]);
export const validationSeriesSchema = z.object({
  series_id: z.string(), label: z.string(), quantity: z.string(), units: z.string(), time_basis: z.string(),
  ticks: z.array(z.number().int()), values: z.array(z.number()), evidence_source: evidenceSourceSchema,
  aggregation_window_ticks: z.number().int().nullable(), counting_basis: z.string().nullable(), boundary_direction: z.string().nullable(),
}).refine((value) => value.ticks.length === value.values.length, "validation series lengths differ");
export const scalarEvidenceSchema = z.object({ scalar_id: z.string(), label: z.string(), value: z.union([z.number(), z.string(), z.boolean()]), units: z.string().nullable(), evidence_source: evidenceSourceSchema });
export const validationOverlaySchema = z.object({ overlay_id: z.string(), kind: z.enum(["relevant_link", "queued_region", "blocked_boundary", "reference_wave", "event_marker", "released_storage"]), label: z.string(), link_id: z.string().nullable(), boundary_id: z.string().nullable(), active_from_tick: z.number().int(), active_through_tick: z.number().int(), direction: z.enum(["forward", "backward", "none"]), evidence_source: evidenceSourceSchema, note: z.string() });
export const validationExecutionEvidenceSchema = z.object({
  schema_version: z.literal("uc.validation.execution-evidence.v1"),
  result_id: z.string(),
  movement_evidence: z.array(movementEvidenceSchema),
  observed_overlays: z.array(validationOverlaySchema),
});
export const validationCaseSchema = z.object({
  schema_version: z.literal("uc.validation.case.v1"), case_id: z.string(), version: z.string(), group_id: z.string(), title: z.string(), short_explanation: z.string(), claim_ids: z.array(z.string()),
  evidence_class: z.enum(["analytical", "published_numerical_reproduction", "structural_requirement", "cross_implementation", "benchmark"]),
  citations: z.array(z.object({ source_id: z.string(), citation_text: z.string(), source_section: z.string().nullable(), figure: z.string().nullable(), equation: z.string().nullable(), table: z.string().nullable(), url: z.string().nullable() })),
  reference_assets: z.array(z.object({ asset_id: z.string(), source_id: z.string(), label: z.string(), citation_text: z.string(), figure_table_equation: z.string().nullable(), local_asset_path: z.string().nullable(), digitised_series_id: z.string().nullable(), rights_provenance_note: z.string(), transformation_metadata: z.array(z.string()), comparison_suitability: z.enum(["suitable", "context_only", "blocked", "not_assessed"]), missing_input_notes: z.array(z.string()) })),
  input_completeness: z.enum(["complete", "partial", "missing"]), comparison_status: z.enum(["exact", "converted", "bounded", "statistical", "structural", "blocked", "not_comparable"]),
  topology_reference: z.string(), profile_reference: z.string(), demand_reference: z.string(), route_sequences: z.array(z.array(z.string())), tick_duration_seconds: z.number().positive(), initial_state_reference: z.string(),
  expected_physical_sequence: z.array(z.string()), expected_result_summary: z.string(), why_it_matters: z.string(), limits_on_interpretation: z.array(z.string()),
  expected_series: z.array(validationSeriesSchema), expected_scalars: z.array(scalarEvidenceSchema), metrics: z.array(z.object({ metric_id: z.string(), label: z.string(), comparison: z.enum(["max_absolute_error", "absolute_error", "exact_sequence", "exact_boolean"]), expected_id: z.string(), tolerance: z.number(), units: z.string(), tolerance_justification: z.string() })),
  overlays: z.array(validationOverlaySchema), known_model_differences: z.array(z.string()), safe_claim: z.string(), provenance: z.array(z.string()), reproducibility_notes: z.array(z.string()), default_final_tick: z.number().int().nonnegative(),
});
export const validationResultSchema = z.object({
  schema_version: z.literal("uc.validation.result.v1"), result_id: z.string(), case_id: z.string(), case_version: z.string(), status: z.enum(["not_run", "running", "passed", "failed", "blocked", "cancelled"]), lifecycle: z.array(z.string()), created_at: z.string(), completed_at: z.string().nullable(), code_commit: z.string().nullable(), configuration_hash: z.string(), expected_evidence_hash: z.string(), replay_run_id: z.string().nullable(),
  observed_series: z.array(validationSeriesSchema), observed_scalars: z.array(scalarEvidenceSchema), difference_series: z.array(validationSeriesSchema), metric_results: z.array(z.object({ metric_id: z.string(), value: z.number(), tolerance: z.number(), units: z.string(), passed: z.boolean(), explanation: z.string() })), headline_metric: z.string(), observed_result_summary: z.string(), difference_summary: z.string(),
  packet_wait_explanations: z.array(z.object({ packet_id: z.string(), active_from_tick: z.number().int(), active_through_tick: z.number().int(), current_link_id: z.string().nullable(), fifo_position: z.number().int().nullable(), head_packet_id: z.string().nullable(), intended_movement: z.string().nullable(), blocking_reason: z.string().nullable(), receiving_supply_packets: z.number().int().nullable(), signal_or_governance_constraint: z.string().nullable(), expected_next_release_tick: z.number().int().nullable(), evidence_sources: z.array(evidenceSourceSchema), unavailable_fields: z.array(z.string()) })),
  stop_reason: z.string().nullable(), linked_issue: z.string().nullable(), linked_fix_commit: z.string().nullable(), provenance: z.array(z.string()),
});
export const validationRunStatusSchema = z.object({ result_id: z.string(), case_id: z.string(), lifecycle: z.string(), physical_tick: z.number().int(), final_tick: z.number().int(), detail: z.string(), terminal: z.boolean() });
export const validationLibrarySchema = z.array(z.object({ case: validationCaseSchema, latest_result: validationResultSchema.nullable(), history_count: z.number().int().nonnegative() }));

export const labVariableSchema = z.object({
  variable_id: z.string(), label: z.string(), value: z.union([z.number(), z.string(), z.array(z.number()), z.array(z.string())]),
  units: z.string(), source: z.string(), evidence_classification: z.string(), configuration_identity: z.string(), linked: z.boolean(),
});
export const labColumnSchema = z.object({
  column_id: z.string(), label: z.string(), units: z.string(),
  kind: z.enum(["manual", "formula_derived", "imported", "case_linked", "uc_observed"]),
  provenance: z.enum(["user_hand_derivation", "independently_encoded_arithmetic", "published_source", "external_implementation", "model_suggestion", "uc_derived_ineligible_as_oracle", "imported", "presentation_only"]),
  values: z.array(z.number()), formula: z.string().nullable(), source_reference: z.string().nullable(),
});
export const tickTableSchema = z.object({
  tick_start: z.number().int(), tick_end: z.number().int(), evaluation_order: z.literal("ascending_tick_then_declared_column"),
  out_of_range_values: z.record(z.string(), z.number()), columns: z.array(labColumnSchema),
});
export const labMappingSchema = z.object({
  expected_column_id: z.string(), observed_series_id: z.string(), time_alignment: z.enum(["same_tick", "offset"]), tick_offset: z.number().int(),
  expected_units: z.string(), observed_units: z.string(), metric: z.enum(["exact", "pointwise_difference", "absolute_error"]), tolerance: z.number().nonnegative(),
});
export const labWorksheetSchema = z.object({
  schema_version: z.literal("uc.lab_bench.worksheet.v1"), worksheet_id: z.string(), revision: z.number().int().nonnegative(), title: z.string(),
  state: z.enum(["scratch", "candidate_reference"]), case_id: z.string().nullable(), case_version: z.string().nullable(), case_configuration_hash: z.string().nullable(), detached: z.boolean(),
  author_source: z.enum(["user_hand_derivation", "independently_encoded_arithmetic", "published_source", "external_implementation", "model_suggestion", "uc_derived_ineligible_as_oracle", "imported", "presentation_only"]),
  created_at: z.string(), updated_at: z.string(), notebook: z.object({ markdown: z.string(), origin: z.enum(["user_authored", "imported", "deterministic_tool_output", "model_suggestion"]), linked_references: z.array(z.string()) }),
  variables: z.array(labVariableSchema), table: tickTableSchema, mappings: z.array(labMappingSchema), assumptions: z.array(z.string()), limitations: z.array(z.string()),
});
export const labEvaluationResultSchema = z.object({ expression: z.string(), substituted_expression: z.string(), value: z.union([z.number(), z.boolean()]), units: z.string(), steps: z.array(z.string()) });
export const labTableResultSchema = z.object({ table: tickTableSchema, dependency_order: z.array(z.string()), diagnostics: z.array(z.string()) });
export const labComparisonResultSchema = z.object({
  formal: z.boolean(), label: z.string(), exact: z.boolean(), differences: z.array(z.number()), compared_ticks: z.array(z.number().int()), maximum_absolute_error: z.number(), mean_absolute_error: z.number(), first_mismatch_tick: z.number().int().nullable(), tick_offset: z.number().int(), cumulative_bound_violations: z.number().int(), mismatched_rows: z.number().int(), tolerance: z.number(),
});
export const labOracleSchema = z.object({
  schema_version: z.literal("uc.lab_bench.oracle.v1"), oracle_id: z.string(), version: z.number().int().positive(), state: z.literal("frozen_oracle"), associated_case_id: z.string(), associated_case_version: z.string(), author_source: z.string(), created_at: z.string(), formula_table_provenance: z.array(z.string()), units: z.array(z.string()), tick_convention: z.string(), input_references: z.array(z.string()), detached_literal_values: z.record(z.string(), z.union([z.number(), z.string()])), artifact_hash: z.string(), approval_action: z.string(), notes: z.array(z.string()), limitations: z.array(z.string()), source_worksheet_revision: z.number().int(), dependency_hash: z.string(), worksheet: labWorksheetSchema,
});

export type Manifest = z.infer<typeof manifestSchema>;
export type CanonicalEvent = z.infer<typeof eventSchema>;
export type ReplayState = z.infer<typeof replayStateSchema>;
export type LinkRecord = z.infer<typeof linkSchema>;
export type PacketRecord = z.infer<typeof packetSchema>;
export type CumulativeSeries = z.infer<typeof cumulativeSeriesSchema>;
export type ArtifactSummary = z.infer<typeof artifactSchema>;
export type ResourceCatalogue = z.infer<typeof resourceCatalogueSchema>;
export type RunRequest = z.infer<typeof runRequestSchema>;
export type LiveMessage = z.infer<typeof liveMessageSchema>;
export type MovementEvidence = z.infer<typeof movementEvidenceSchema>;
export type NetworkLayout = z.infer<typeof networkLayoutSchema>;
export type ValidationCase = z.infer<typeof validationCaseSchema>;
export type ValidationResult = z.infer<typeof validationResultSchema>;
export type ValidationExecutionEvidence = z.infer<typeof validationExecutionEvidenceSchema>;
export type ValidationRunStatus = z.infer<typeof validationRunStatusSchema>;
export type ValidationLibraryRecord = z.infer<typeof validationLibrarySchema>[number];
export type LabVariable = z.infer<typeof labVariableSchema>;
export type LabColumn = z.infer<typeof labColumnSchema>;
export type LabWorksheet = z.infer<typeof labWorksheetSchema>;
export type LabEvaluationResult = z.infer<typeof labEvaluationResultSchema>;
export type LabComparisonResult = z.infer<typeof labComparisonResultSchema>;
export type LabOracle = z.infer<typeof labOracleSchema>;

export { contractEnums, v2ContractEnums };
