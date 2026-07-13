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
} from "./contract";

const getJson = async (path: string): Promise<unknown> => {
  const response = await fetch(path, { signal: AbortSignal.timeout(15_000) });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
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
