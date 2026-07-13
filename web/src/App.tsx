import { useEffect, useRef, useState } from "react";
import { EventStream } from "./components/EventStream";
import { Inspector } from "./components/Inspector";
import { NetworkCanvas } from "./components/NetworkCanvas";
import { ScientificChart } from "./components/ScientificChart";
import { loadCumulativeSeries, loadRun, loadRunList } from "./lib/api";
import type { CanonicalEvent, CumulativeSeries, Manifest, ReplayState } from "./lib/contract";
import { stateAtTick } from "./lib/replay";

type LoadedRun = {
  manifest: Manifest;
  events: CanonicalEvent[];
  states: ReplayState[];
};

export default function App() {
  const [loaded, setLoaded] = useState<LoadedRun | null>(null);
  const [series, setSeries] = useState<CumulativeSeries | null>(null);
  const [tick, setTick] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [phase, setPhase] = useState(0);
  const [selectedLinkId, setSelectedLinkId] = useState("");
  const [selectedPacketId, setSelectedPacketId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const playbackRef = useRef({ last: 0, accumulator: 0 });

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const runs = await loadRunList();
        if (!runs.length) throw new Error("No persisted V1 run artifacts are available.");
        const payload = await loadRun(runs[0].run_id);
        if (!active) return;
        setLoaded({ manifest: payload.manifest, events: payload.events, states: payload.states });
        setSeries(payload.initialSeries);
        setTick(payload.manifest.run.start_tick);
        setSelectedLinkId(payload.manifest.topology.links[0].link_id);
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : String(reason));
      }
    })();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!loaded || !selectedLinkId) return;
    let active = true;
    loadCumulativeSeries(loaded.manifest.run.run_id, selectedLinkId)
      .then((value) => { if (active) setSeries(value); })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : String(reason)); });
    return () => { active = false; };
  }, [loaded, selectedLinkId]);

  useEffect(() => {
    if (!loaded || !playing) return;
    let animationFrame = 0;
    const frame = (timestamp: number) => {
      const playback = playbackRef.current;
      if (!playback.last) playback.last = timestamp;
      playback.accumulator += timestamp - playback.last;
      playback.last = timestamp;
      const millisecondsPerTick = 760 / speed;
      const elapsedTicks = Math.floor(playback.accumulator / millisecondsPerTick);
      if (elapsedTicks > 0) {
        playback.accumulator -= elapsedTicks * millisecondsPerTick;
        setTick((current) => {
          const next = Math.min(current + elapsedTicks, loaded.manifest.run.end_tick);
          if (next === loaded.manifest.run.end_tick) setPlaying(false);
          return next;
        });
      }
      setPhase(playback.accumulator / millisecondsPerTick);
      animationFrame = requestAnimationFrame(frame);
    };
    animationFrame = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(animationFrame);
      playbackRef.current.last = 0;
    };
  }, [loaded, playing, speed]);

  if (error) return <main className="center-message"><span className="brand-mark">UC·V</span><h1>Evidence viewer unavailable</h1><p>{error}</p><small>Start the read-only API and refresh this page.</small></main>;
  if (!loaded || !series || !selectedLinkId) return <main className="center-message"><span className="brand-mark pulse">UC·V</span><h1>Loading persisted evidence</h1><p>Validating the V1 contract and replay projections…</p></main>;

  const { manifest, events, states } = loaded;
  const state = stateAtTick(states, tick);
  const run = manifest.run;
  const simulationSeconds = tick * run.tick_duration_seconds;
  const seek = (nextTick: number) => {
    setPlaying(false);
    setTick(Math.max(run.start_tick, Math.min(nextTick, run.end_tick)));
    setPhase(0);
    playbackRef.current = { last: 0, accumulator: 0 };
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark">UC·V</span><div><strong>Urban Cybernetics</strong><small>Simulation evidence instrument</small></div></div>
        <div className="run-title"><span className="eyebrow">Loaded run</span><h1>{run.scenario_name}</h1></div>
        <div className="run-badges">
          <span className={`status-pill run-${run.status}`}>{run.status}</span>
          <span className={`status-pill validation-${manifest.validation.overall_status}`}>validation {manifest.validation.overall_status}</span>
        </div>
      </header>

      <section className="replay-bar panel">
        <div className="transport">
          <button className="transport-button" onClick={() => seek(run.start_tick)} aria-label="Seek to start">↺</button>
          <button className="play-button" onClick={() => setPlaying((value) => !value)} aria-label={playing ? "Pause replay" : "Play replay"}>{playing ? "Ⅱ" : "▶"}</button>
          <button className="transport-button" onClick={() => seek(tick - 1)} aria-label="Previous tick">‹</button>
          <button className="transport-button" onClick={() => seek(tick + 1)} aria-label="Next tick">›</button>
        </div>
        <div className="scrubber">
          <input aria-label="Replay tick" type="range" min={run.start_tick} max={run.end_tick} step={1} value={tick} onChange={(event) => seek(Number(event.target.value))} />
          <div className="scrubber-labels"><span>t{run.start_tick}</span><span>canonical events through #{state.applied_through_sequence ?? "—"}</span><span>t{run.end_tick}</span></div>
        </div>
        <div className="time-readout"><span>physical tick</span><strong>{String(tick).padStart(3, "0")}</strong><small>{simulationSeconds.toFixed(1)} s · Δt {run.tick_duration_seconds}s</small></div>
        <label className="speed-control"><span>Replay speed</span><select value={speed} onChange={(event) => setSpeed(Number(event.target.value))}><option value={0.5}>0.5×</option><option value={1}>1×</option><option value={2}>2×</option><option value={4}>4×</option></select></label>
      </section>

      <main className="workspace">
        <section className="network-panel panel">
          <div className="network-heading">
            <div><span className="eyebrow">Directed topology</span><h2>Physical evidence replay</h2></div>
            <div className="legend"><span><i className="legend-dot active" /> occupied</span><span><i className="legend-dot queued" /> queue</span><span><i className="legend-line" /> topology</span></div>
          </div>
          <NetworkCanvas manifest={manifest} state={state} selectedLinkId={selectedLinkId} selectedPacketId={selectedPacketId} phase={phase} onSelectLink={(linkId) => { setSelectedLinkId(linkId); setSelectedPacketId(null); }} />
          <div className="network-metrics">
            <div><span>in transit</span><strong>{state.counts.in_transit}</strong></div>
            <div><span>queued</span><strong className="amber">{state.counts.queued}</strong></div>
            <div><span>completed</span><strong className="lime">{state.counts.completed}</strong></div>
            <div><span>unresolved</span><strong>{state.counts.in_transit + state.counts.queued}</strong></div>
            <div><span>cancelled</span><strong>{state.counts.cancelled}</strong></div>
          </div>
        </section>
        <Inspector manifest={manifest} state={state} events={events} selectedLinkId={selectedLinkId} selectedPacketId={selectedPacketId} series={series} onSelectPacket={setSelectedPacketId} />
      </main>

      <section className="evidence-deck">
        <div className="chart-panel panel">
          <div className="panel-heading compact"><div><span className="eyebrow">Scientific projection · {selectedLinkId}</span><h2>Cumulative boundary counts</h2></div><span className="source-chip">Python-derived</span></div>
          <ScientificChart series={series} tick={tick} />
          <div className="chart-source">Units: {series.descriptor.units} · Basis: {series.descriptor.time_basis}</div>
        </div>
        <div className="events-panel panel"><EventStream events={events} tick={tick} onSelectPacket={setSelectedPacketId} /></div>
      </section>

      <footer className="provenance-bar">
        <span><b>RUN</b> {run.run_id}</span>
        <span><b>TOPOLOGY</b> {run.topology_hash.slice(0, 12)}…</span>
        <span><b>PROFILE</b> {run.model_profile_id}</span>
        <span><b>CONTRACT</b> {manifest.schema_version}</span>
        <span className="truth-label">read-only persisted evidence</span>
      </footer>
    </div>
  );
}
