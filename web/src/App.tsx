import { useCallback, useEffect, useRef, useState } from "react";
import { ComparisonStrip } from "./components/ComparisonStrip";
import { EventStream } from "./components/EventStream";
import { Inspector } from "./components/Inspector";
import { LiveRunPanel } from "./components/LiveRunPanel";
import { MovementPanel } from "./components/MovementPanel";
import { NetworkCanvas } from "./components/NetworkCanvas";
import { NewRunDrawer } from "./components/NewRunDrawer";
import { RunLibrary } from "./components/RunLibrary";
import { ScientificChart } from "./components/ScientificChart";
import {
  commandRun, followRun, launchRun, loadArtifact, loadArtifactCumulativeSeries,
  loadArtifactLibrary, loadCatalogue, loadExactReplayState, loadLiveManifest,
  loadMovementEvidence, loadV2EventPage,
} from "./lib/api";
import type {
  ArtifactSummary, CanonicalEvent, CumulativeSeries, LiveMessage, Manifest,
  MovementEvidence, ReplayState, ResourceCatalogue, RunRequest,
} from "./lib/contract";
import { stateAtTick } from "./lib/replay";

type LoadedRun = { artifact: ArtifactSummary; manifest: Manifest; events: CanonicalEvent[]; states: ReplayState[] };

export default function App() {
  const [artifacts, setArtifacts] = useState<ArtifactSummary[]>([]);
  const [catalogue, setCatalogue] = useState<ResourceCatalogue | null>(null);
  const [loaded, setLoaded] = useState<LoadedRun | null>(null);
  const [series, setSeries] = useState<CumulativeSeries | null>(null);
  const [tick, setTick] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [phase, setPhase] = useState(0);
  const [selectedLinkId, setSelectedLinkId] = useState("");
  const [selectedPacketId, setSelectedPacketId] = useState<string | null>(null);
  const [movementEvidence, setMovementEvidence] = useState<MovementEvidence[]>([]);
  const [newRunOpen, setNewRunOpen] = useState(false);
  const [liveRun, setLiveRun] = useState<ArtifactSummary | null>(null);
  const [liveMessage, setLiveMessage] = useState<LiveMessage | null>(null);
  const [liveState, setLiveState] = useState<ReplayState | null>(null);
  const [viewerFollowing, setViewerFollowing] = useState(true);
  const [pinned, setPinned] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const playbackRef = useRef({ last: 0, accumulator: 0 });
  const followingRef = useRef(true);
  followingRef.current = viewerFollowing;

  const refreshLibrary = useCallback(async () => {
    const next = await loadArtifactLibrary();
    setArtifacts(next);
    return next;
  }, []);

  const openArtifact = useCallback(async (artifact: ArtifactSummary) => {
    if (artifact.artifact_format === "v2_chunked" && !["complete", "cancelled", "timed_out"].includes(artifact.status)) {
      throw new Error("This artifact is still running; use its live workbench state.");
    }
    const payload = await loadArtifact(artifact);
    setLoaded({ artifact, manifest: payload.manifest, events: payload.events, states: payload.states });
    setSeries(payload.initialSeries);
    setTick(payload.manifest.run.start_tick);
    setSelectedLinkId(payload.manifest.topology.links[0]?.link_id ?? "");
    setSelectedPacketId(null);
    setLiveState(null);
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [runs, declared] = await Promise.all([refreshLibrary(), loadCatalogue()]);
        if (!active) return;
        setCatalogue(declared);
        if (!runs.length) throw new Error("No persisted V-compatible run artifacts are available.");
        await openArtifact(runs[0]);
      } catch (reason) { if (active) setError(reason instanceof Error ? reason.message : String(reason)); }
    })();
    return () => { active = false; };
  }, [openArtifact, refreshLibrary]);

  const loadedArtifact = loaded?.artifact ?? null;

  useEffect(() => {
    if (!loadedArtifact || !selectedLinkId) return;
    let active = true;
    loadArtifactCumulativeSeries(loadedArtifact, selectedLinkId)
      .then((value) => { if (active) setSeries(value); })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : String(reason)); });
    return () => { active = false; };
  }, [loadedArtifact, selectedLinkId]);

  useEffect(() => {
    if (!loadedArtifact || loadedArtifact.artifact_format !== "v2_chunked") { setMovementEvidence([]); return; }
    let active = true;
    loadMovementEvidence(loadedArtifact.run_id, tick).then((value) => { if (active) setMovementEvidence(value); }).catch(() => { if (active) setMovementEvidence([]); });
    return () => { active = false; };
  }, [loadedArtifact, tick]);

  useEffect(() => {
    if (!loaded || !playing || (liveRun && loaded.artifact.run_id === liveRun.run_id)) return;
    let animationFrame = 0;
    const frame = (timestamp: number) => {
      const playback = playbackRef.current;
      if (!playback.last) playback.last = timestamp;
      playback.accumulator += timestamp - playback.last; playback.last = timestamp;
      const millisecondsPerTick = 760 / speed;
      const elapsedTicks = Math.floor(playback.accumulator / millisecondsPerTick);
      if (elapsedTicks > 0) {
        playback.accumulator -= elapsedTicks * millisecondsPerTick;
        setTick((current) => { const next = Math.min(current + elapsedTicks, loaded.manifest.run.end_tick); if (next === loaded.manifest.run.end_tick) setPlaying(false); return next; });
      }
      setPhase(playback.accumulator / millisecondsPerTick);
      animationFrame = requestAnimationFrame(frame);
    };
    animationFrame = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(animationFrame); playbackRef.current.last = 0; };
  }, [loaded, liveRun, playing, speed]);

  const updateLiveHead = useCallback(async (run: ArtifactSummary, headTick: number) => {
    try {
      const [manifest, state, page] = await Promise.all([loadLiveManifest(run.run_id), loadExactReplayState(run.run_id, headTick), loadV2EventPage(run.run_id, 0)]);
      const activeArtifact = { ...run, final_tick: headTick, event_count: page.total_event_count, status: state.counts.completed === run.counts.requested ? "finalising" : "running" };
      setLoaded((current) => ({ artifact: activeArtifact, manifest, states: current?.artifact.run_id === run.run_id ? current.states : [], events: page.events }));
      if (followingRef.current) { setLiveState(state); setTick(headTick); }
      setSelectedLinkId((current) => current || manifest.topology.links[0]?.link_id || "");
      setLiveRun(activeArtifact);
    } catch { /* setup may not have sealed packets yet; next progress message retries */ }
  }, []);

  const startFollowing = useCallback((run: ArtifactSummary) => {
    setLiveRun(run); setViewerFollowing(true); setLiveMessage(null);
    return followRun(run.run_id, (message) => {
      setLiveMessage(message);
      if (message.message_type === "tick_batch_sealed" && typeof message.payload.physical_tick === "number") void updateLiveHead(run, message.payload.physical_tick);
      if (message.message_type === "terminal_result") {
        window.setTimeout(() => void (async () => {
          const next = await refreshLibrary();
          const sealed = next.find((item) => item.run_id === run.run_id);
          if (sealed) { setLiveRun(sealed); await openArtifact(sealed); }
        })(), 80);
      }
    }, () => { /* EventSource reconnects with durable recovery available. */ });
  }, [openArtifact, refreshLibrary, updateLiveHead]);

  const submitRun = async (request: RunRequest) => {
    const created = await launchRun(request);
    setNewRunOpen(false);
    await refreshLibrary();
    startFollowing(created);
  };

  const seek = async (nextTick: number) => {
    if (!loaded) return;
    setPlaying(false);
    const bounded = Math.max(loaded.manifest.run.start_tick, Math.min(nextTick, loaded.manifest.run.end_tick));
    if (liveRun && loaded.artifact.run_id === liveRun.run_id) {
      setViewerFollowing(bounded === loaded.manifest.run.end_tick);
      try { setLiveState(await loadExactReplayState(liveRun.run_id, bounded)); } catch { return; }
    }
    setTick(bounded); setPhase(0); playbackRef.current = { last: 0, accumulator: 0 };
  };

  const goLive = () => {
    setViewerFollowing(true);
    if (loaded) void seek(loaded.manifest.run.end_tick);
  };

  if (error && !loaded) return <main className="center-message"><span className="brand-mark">UC·V2</span><h1>Workbench unavailable</h1><p>{error}</p><small>Start the local API and refresh this page.</small></main>;
  if (!loaded || !series || !selectedLinkId) return <main className="center-message"><span className="brand-mark pulse">UC·V2</span><h1>Loading simulation workbench</h1><p>Discovering and validating persisted evidence…</p></main>;

  const { artifact, manifest, events, states } = loaded;
  const isLiveLoaded = liveRun?.run_id === artifact.run_id;
  const state = isLiveLoaded && liveState?.tick === tick ? liveState : stateAtTick(states, tick);
  const run = manifest.run;
  const simulationSeconds = tick * run.tick_duration_seconds;
  const pinnedRuns = pinned.map((id) => artifacts.find((item) => item.run_id === id)).filter((item): item is ArtifactSummary => Boolean(item));

  return <div className="app-shell workbench-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-mark">UC·V2</span><div><strong>Urban Cybernetics</strong><small>Simulation workbench</small></div></div>
      <div className="run-title"><span className="eyebrow">Loaded evidence</span><h1>{run.scenario_name}</h1></div>
      <div className="run-badges"><span className={`status-pill run-${artifact.status}`}>{artifact.status}</span><span className={`status-pill validation-${artifact.validation_status}`}>validation {artifact.validation_status}</span></div>
    </header>

    <div className="workbench-grid">
      <RunLibrary artifacts={artifacts} loadedRunId={artifact.run_id} pinned={pinned} onRefresh={() => void refreshLibrary()} onNewRun={() => setNewRunOpen(true)} onLoad={(next) => void openArtifact(next).catch((reason) => setError(String(reason)))} onPin={(runId) => setPinned((current) => current.includes(runId) ? current.filter((item) => item !== runId) : current.length < 2 ? [...current, runId] : [current[1], runId])} />
      <div className="instrument-column">
        {liveRun && <LiveRunPanel run={liveRun} message={liveMessage} viewerFollowing={viewerFollowing} onViewerFollow={goLive} onCommand={(action) => void commandRun(liveRun.run_id, action)} />}
        {error && <div className="inline-error">{error}<button onClick={() => setError(null)}>×</button></div>}
        <ComparisonStrip runs={pinnedRuns} onClear={() => setPinned([])} />
        <section className="replay-bar panel">
          <div className="transport"><button className="transport-button" onClick={() => void seek(run.start_tick)} aria-label="Seek to start">↺</button><button className="play-button" onClick={() => { if (isLiveLoaded) { if (viewerFollowing) setViewerFollowing(false); else goLive(); } else setPlaying((value) => !value); }} aria-label={isLiveLoaded ? viewerFollowing ? "Pause viewer" : "Resume viewer at live head" : playing ? "Pause viewer" : "Play viewer"}>{isLiveLoaded ? viewerFollowing ? "Ⅱ" : "▶" : playing ? "Ⅱ" : "▶"}</button><button className="transport-button" onClick={() => void seek(tick - 1)} aria-label="Previous tick">‹</button><button className="transport-button" onClick={() => void seek(tick + 1)} aria-label="Next tick">›</button></div>
          <div className="scrubber"><input aria-label="Replay tick" type="range" min={run.start_tick} max={run.end_tick} step={1} value={tick} onChange={(event) => void seek(Number(event.target.value))} /><div className="scrubber-labels"><span>t{run.start_tick}</span><span>{isLiveLoaded && !viewerFollowing ? "viewer behind live head" : `canonical events through #${state.applied_through_sequence ?? "—"}`}</span><span>t{run.end_tick}</span></div></div>
          <div className="time-readout"><span>physical tick</span><strong>{String(tick).padStart(3, "0")}</strong><small>{simulationSeconds.toFixed(1)} s · Δt {run.tick_duration_seconds}s</small></div>
          <label className="speed-control"><span>Viewer speed</span><select value={speed} onChange={(event) => setSpeed(Number(event.target.value))}><option value={0.5}>0.5×</option><option value={1}>1×</option><option value={2}>2×</option><option value={4}>4×</option></select></label>
        </section>

        <main className="workspace"><section className="network-panel panel"><div className="network-heading"><div><span className="eyebrow">Evidence plane · directed topology</span><h2>{isLiveLoaded ? "Sealed live scientific state" : "Persisted physical evidence replay"}</h2></div><div className="legend"><span><i className="legend-dot active" /> occupied</span><span><i className="legend-dot queued" /> queue</span><span><i className="legend-line" /> topology</span></div></div><NetworkCanvas manifest={manifest} state={state} selectedLinkId={selectedLinkId} selectedPacketId={selectedPacketId} phase={phase} onSelectLink={(linkId) => { setSelectedLinkId(linkId); setSelectedPacketId(null); }} /><div className="network-metrics"><div><span>in transit</span><strong>{state.counts.in_transit}</strong></div><div><span>queued</span><strong className="amber">{state.counts.queued}</strong></div><div><span>completed</span><strong className="lime">{state.counts.completed}</strong></div><div><span>unresolved</span><strong>{state.counts.in_transit + state.counts.queued + state.counts.not_yet_observed}</strong></div><div><span>cancelled</span><strong>{state.counts.cancelled}</strong></div></div></section><Inspector manifest={manifest} state={state} events={events} selectedLinkId={selectedLinkId} selectedPacketId={selectedPacketId} series={series} onSelectPacket={setSelectedPacketId} /></main>
        <section className="evidence-deck"><div className="chart-panel panel"><div className="panel-heading compact"><div><span className="eyebrow">Scientific projection · {selectedLinkId}</span><h2>Cumulative boundary counts</h2></div><span className="source-chip">Python-derived</span></div><ScientificChart series={series} tick={tick} /><div className="chart-source">Units: {series.descriptor.units} · Basis: {series.descriptor.time_basis}</div></div><div className="events-panel panel"><EventStream events={events} tick={tick} onSelectPacket={setSelectedPacketId} /></div></section>
        <MovementPanel evidence={movementEvidence} tick={tick} />
        <footer className="provenance-bar"><span><b>RUN</b> {run.run_id}</span><span><b>TOPOLOGY</b> {run.topology_hash.slice(0, 12)}…</span><span><b>PROFILE</b> {run.model_profile_id}</span><span><b>CONTRACT</b> {artifact.contract_version}</span><span className="truth-label">canonical and Python-derived evidence</span></footer>
      </div>
    </div>
    {newRunOpen && catalogue && <NewRunDrawer catalogue={catalogue} onClose={() => setNewRunOpen(false)} onSubmit={submitRun} />}
  </div>;
}
