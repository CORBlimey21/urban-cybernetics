import { z } from "zod";
import {
  cumulativeSeriesSchema,
  eventsResponseSchema,
  manifestSchema,
  replayResponseSchema,
  runListSchema,
  type CanonicalEvent,
  type CumulativeSeries,
  type Manifest,
  type ReplayState,
  artifactListSchema,
  finalBundleSchema,
  liveMessageSchema,
  movementEvidenceSchema,
  resourceCatalogueSchema,
  runRequestSchema,
  artifactSchema,
  replayStateSchema,
  eventSchema,
  validationLibrarySchema,
  validationResultSchema,
  validationRunStatusSchema,
  type ArtifactSummary,
  type LiveMessage,
  type RunRequest,
} from "./contract";

const getJson = async (path: string): Promise<unknown> => {
  const response = await fetch(path, { signal: AbortSignal.timeout(15_000) });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
};

const postJson = async (path: string, body: unknown): Promise<unknown> => {
  const response = await fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response.json();
};

export const loadRun = async (runId: string): Promise<{
  manifest: Manifest;
  events: CanonicalEvent[];
  states: ReplayState[];
  initialSeries: CumulativeSeries;
}> => {
  const manifest = manifestSchema.parse(
    await getJson(`/api/v1/runs/${encodeURIComponent(runId)}/manifest`),
  );
  const [eventPayload, replayPayload] = await Promise.all([
    getJson(
      `/api/v1/runs/${encodeURIComponent(runId)}/events?start_sequence=0&limit=10000`,
    ).then((value) => eventsResponseSchema.parse(value)),
    getJson(
      `/api/v1/runs/${encodeURIComponent(runId)}/replay?start_tick=0&end_tick=${manifest.run.end_tick}`,
    ).then((value) => replayResponseSchema.parse(value)),
  ]);
  if (eventPayload.next_sequence !== null) {
    throw new Error("This V1 client requires event pagination support for this run size.");
  }
  const initialLinkId = manifest.topology.links[0]?.link_id;
  if (!initialLinkId) throw new Error("Run topology has no links.");
  const initialSeries = cumulativeSeriesSchema.parse(
    await getJson(
      `/api/v1/runs/${encodeURIComponent(runId)}/links/${encodeURIComponent(initialLinkId)}/cumulative-counts`,
    ),
  );
  return {
    manifest,
    events: eventPayload.events,
    states: replayPayload.states,
    initialSeries,
  };
};

export const loadRunList = async () => runListSchema.parse(await getJson("/api/v1/runs"));

export const loadCumulativeSeries = async (
  runId: string,
  linkId: string,
): Promise<CumulativeSeries> =>
  cumulativeSeriesSchema.parse(
    await getJson(
      `/api/v1/runs/${encodeURIComponent(runId)}/links/${encodeURIComponent(linkId)}/cumulative-counts`,
    ),
  );

export const loadArtifactCumulativeSeries = async (artifact: ArtifactSummary, linkId: string): Promise<CumulativeSeries> =>
  cumulativeSeriesSchema.parse(await getJson(
    artifact.artifact_format === "v1_bundle"
      ? `/api/v1/runs/${encodeURIComponent(artifact.run_id)}/links/${encodeURIComponent(linkId)}/cumulative-counts`
      : `/api/v2/runs/${encodeURIComponent(artifact.run_id)}/links/${encodeURIComponent(linkId)}/cumulative-counts`,
  ));

export const loadArtifactLibrary = async () => artifactListSchema.parse(await getJson("/api/v2/artifacts"));
export const loadCatalogue = async () => resourceCatalogueSchema.parse(await getJson("/api/v2/catalogue"));

export const loadArtifact = async (artifact: ArtifactSummary) => {
  if (artifact.artifact_format === "v1_bundle") return loadRun(artifact.run_id);
  const bundle = finalBundleSchema.parse(await getJson(`/api/v2/runs/${encodeURIComponent(artifact.run_id)}/bundle`));
  const initialSeries = bundle.cumulative_link_series[0];
  if (!initialSeries) throw new Error("Run has no link projection.");
  return { manifest: bundle, events: bundle.event_stream.events, states: bundle.replay_states, initialSeries };
};

export const launchRun = async (request: RunRequest) => {
  const payload = z.record(z.string(), z.unknown()).parse(
    await postJson("/api/v2/runs", runRequestSchema.parse(request)),
  );
  return artifactSchema.parse({ artifact_format: "v2_chunked", ...payload });
};

export const commandRun = async (runId: string, action: "pause" | "resume" | "cancel") =>
  postJson(`/api/v2/runs/${encodeURIComponent(runId)}/commands`, {
    schema_version: "uc.visualisation.control.v2",
    command_id: `${action}-${crypto.randomUUID()}`,
    action,
  });

export const loadMovementEvidence = async (runId: string, tick: number) => {
  const payload = await getJson(`/api/v2/runs/${encodeURIComponent(runId)}/movements?tick=${tick}`);
  return movementEvidenceSchema.array().parse(payload);
};

export const loadLiveManifest = async (runId: string) => manifestSchema.parse(await getJson(`/api/v2/runs/${encodeURIComponent(runId)}/live-manifest`));
export const loadExactReplayState = async (runId: string, tick: number) => {
  const payload = await getJson(`/api/v2/runs/${encodeURIComponent(runId)}/replay/${tick}`);
  return replayResponseSingleSchema.parse(payload).state;
};

export const loadV2EventPage = async (runId: string, startSequence: number) => {
  const payload = z.object({ events: z.array(eventSchema), start_sequence: z.number().int(), next_sequence: z.number().int().nullable(), total_event_count: z.number().int() }).parse(
    await getJson(`/api/v2/runs/${encodeURIComponent(runId)}/events?start_sequence=${startSequence}&limit=10000`),
  );
  return payload;
};

const replayResponseSingleSchema = z.object({ state: replayStateSchema, source: z.object({ kind: z.string(), checkpoint_tick: z.number().int().nullable() }) });

export const followRun = (runId: string, onMessage: (message: LiveMessage) => void, onError: () => void) => {
  const stream = new EventSource(`/api/v2/runs/${encodeURIComponent(runId)}/stream`);
  const receive = (event: MessageEvent<string>) => onMessage(liveMessageSchema.parse(JSON.parse(event.data)));
  for (const type of ["lifecycle_transition", "setup_progress", "tick_batch_sealed", "canonical_event_range_appended", "checkpoint_sealed", "progress", "validation_progress", "warning", "terminal_result"]) {
    stream.addEventListener(type, receive as EventListener);
  }
  stream.onerror = onError;
  return () => stream.close();
};

export const loadValidationLibrary = async () => validationLibrarySchema.parse(await getJson("/api/v3/validation/cases"));
export const loadValidationHistory = async (caseId: string) => validationResultSchema.array().parse(await getJson(`/api/v3/validation/cases/${encodeURIComponent(caseId)}/history`));
export const startValidationCase = async (caseId: string) => validationRunStatusSchema.parse(await postJson(`/api/v3/validation/cases/${encodeURIComponent(caseId)}/runs`, {}));
export const startValidationGroup = async (groupId: string) => validationRunStatusSchema.array().parse(await postJson(`/api/v3/validation/groups/${encodeURIComponent(groupId)}/runs`, {}));
export const loadValidationRunStatus = async (resultId: string) => validationRunStatusSchema.parse(await getJson(`/api/v3/validation/runs/${encodeURIComponent(resultId)}/status`));
export const cancelValidationRun = async (resultId: string) => validationRunStatusSchema.parse(await postJson(`/api/v3/validation/runs/${encodeURIComponent(resultId)}/commands`, { schema_version: "uc.validation.control.v1", command_id: `cancel-${crypto.randomUUID()}`, action: "cancel" }));
export const loadValidationResult = async (resultId: string) => validationResultSchema.parse(await getJson(`/api/v3/validation/results/${encodeURIComponent(resultId)}`));
export const loadValidationBundle = async (resultId: string) => finalBundleSchema.parse(await getJson(`/api/v3/validation/results/${encodeURIComponent(resultId)}/bundle`));
