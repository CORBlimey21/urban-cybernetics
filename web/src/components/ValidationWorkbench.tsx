import { useCallback, useEffect, useMemo, useState } from "react";
import { cancelValidationRun, loadValidationBundle, loadValidationHistory, loadValidationLibrary, loadValidationResult, loadValidationRunStatus, startValidationCase, startValidationGroup } from "../lib/api";
import type { CanonicalEvent, CumulativeSeries, Manifest, ReplayState, ValidationCase, ValidationLibraryRecord, ValidationResult, ValidationRunStatus } from "../lib/contract";
import { defaultLayout } from "../lib/layout";
import { stateAtTick } from "../lib/replay";
import { Inspector } from "./Inspector";
import { NetworkCanvas } from "./NetworkCanvas";
import { ValidationComparisonChart } from "./ValidationComparisonChart";

type Bundle = Manifest & { event_stream: { events: CanonicalEvent[] }; replay_states: ReplayState[]; cumulative_link_series: CumulativeSeries[] };

const sourceLabel = (source: string) => source.replaceAll("_", " ");

export function ValidationWorkbench() {
  const [library, setLibrary] = useState<ValidationLibraryRecord[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [history, setHistory] = useState<ValidationResult[]>([]);
  const [runStatus, setRunStatus] = useState<ValidationRunStatus | null>(null);
  const [tick, setTick] = useState(0);
  const [selectedLinkId, setSelectedLinkId] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedPacketId, setSelectedPacketId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const records = await loadValidationLibrary();
    setLibrary(records);
    setSelectedCaseId((current) => current ?? records[0]?.case.case_id ?? null);
    return records;
  }, []);

  const loadResult = useCallback(async (resultId: string, validationCase: ValidationCase) => {
    const [nextResult, nextBundle, nextHistory] = await Promise.all([loadValidationResult(resultId), loadValidationBundle(resultId), loadValidationHistory(validationCase.case_id)]);
    setResult(nextResult); setBundle(nextBundle); setHistory(nextHistory); setTick(nextBundle.run.start_tick);
    setSelectedLinkId(nextBundle.topology.links[0]?.link_id ?? ""); setSelectedNodeId(null); setSelectedPacketId(null);
  }, []);

  useEffect(() => { void refresh().catch((reason) => setError(String(reason))); }, [refresh]);
  const record = library.find((item) => item.case.case_id === selectedCaseId) ?? null;

  useEffect(() => {
    if (!record) return;
    if (record.latest_result) void loadResult(record.latest_result.result_id, record.case).catch((reason) => setError(String(reason)));
    else { setResult(null); setBundle(null); void loadValidationHistory(record.case.case_id).then(setHistory); }
  }, [loadResult, record?.case.case_id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!runStatus || runStatus.terminal || !record) return;
    const timer = window.setInterval(() => void loadValidationRunStatus(runStatus.result_id).then((status) => {
      setRunStatus(status);
      if (status.terminal) void loadResult(status.result_id, record.case).then(refresh);
    }).catch((reason) => setError(String(reason))), 90);
    return () => window.clearInterval(timer);
  }, [loadResult, record, refresh, runStatus]);

  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (!bundle || event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement) return;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault(); setTick((current) => Math.max(bundle.run.start_tick, Math.min(bundle.run.end_tick, current + (event.key === "ArrowRight" ? 1 : -1))));
      }
    };
    window.addEventListener("keydown", keydown); return () => window.removeEventListener("keydown", keydown);
  }, [bundle]);

  const runSelected = async () => {
    if (!record) return;
    setRunStatus(await startValidationCase(record.case.case_id));
  };
  const runGroup = async () => {
    if (!record) return;
    const statuses = await startValidationGroup(record.case.group_id);
    const selected = statuses.find((item) => item.case_id === record.case.case_id) ?? statuses[0];
    setRunStatus(selected);
  };

  const state = bundle ? stateAtTick(bundle.replay_states, tick) : null;
  const series = bundle?.cumulative_link_series.find((item) => item.link_id === selectedLinkId) ?? bundle?.cumulative_link_series[0] ?? null;
  const activeOverlays = record?.case.overlays.filter((overlay) => overlay.active_from_tick <= tick && tick <= overlay.active_through_tick) ?? [];
  const wait = result?.packet_wait_explanations.find((item) => item.packet_id === selectedPacketId && item.active_from_tick <= tick && tick <= item.active_through_tick);
  const metricsById = useMemo(() => new Map(result?.metric_results.map((item) => [item.metric_id, item]) ?? []), [result]);

  return <div className="validation-shell">
    <aside className="validation-library panel">
      <div className="library-heading"><div><span className="eyebrow">Validation plane</span><h2>Validation Library</h2></div><button className="icon-action" onClick={() => void refresh()}>↻</button></div>
      <div className="validation-coverage"><strong>{library.filter((item) => item.latest_result?.status === "passed").length}/{library.length}</strong><span>evidence obligations with passing latest results</span></div>
      <div className="validation-group-heading"><span>Analytical</span><button onClick={() => void runGroup()}>Run group</button></div>
      <div className="validation-case-list">{library.map((item) => <button key={item.case.case_id} className={item.case.case_id === selectedCaseId ? "selected" : ""} onClick={() => setSelectedCaseId(item.case.case_id)}><span><i className={`validation-dot status-${item.latest_result?.status ?? "not_run"}`} />{item.case.case_id}<em>{item.case.comparison_status}</em></span><strong>{item.case.title}</strong><small>{item.case.evidence_class} · {item.history_count} result{item.history_count === 1 ? "" : "s"}</small><b>{item.latest_result?.headline_metric ?? "not run"}</b></button>)}</div>
    </aside>

    <section className="validation-detail">
      {error && <div className="inline-error">{error}<button onClick={() => setError(null)}>×</button></div>}
      {!record ? <div className="panel validation-empty">Loading declared validation cases…</div> : <>
        <header className="validation-hero panel"><div><span className="eyebrow">{record.case.case_id} · {record.case.evidence_class}</span><h1>{record.case.title}</h1><p>{record.case.short_explanation}</p></div><div className="validation-actions"><span className={`status-pill validation-${result?.status ?? "not_run"}`}>{result?.status ?? "not run"}</span><button onClick={() => void runSelected()}>Run selected case</button>{runStatus && !runStatus.terminal && <button className="danger" onClick={() => void cancelValidationRun(runStatus.result_id).then(setRunStatus)}>Cancel</button>}</div></header>
        {runStatus && <div className="validation-progress panel"><div><span>{sourceLabel(runStatus.lifecycle)}</span><strong>tick {runStatus.physical_tick}/{runStatus.final_tick}</strong></div><progress max={Math.max(runStatus.final_tick, 1)} value={runStatus.physical_tick} /><p>{runStatus.detail}</p><small>Simulation execution and post-run comparison are separate lifecycle stages.</small></div>}
        <div className="validation-answer-grid">
          <section className="panel validation-overview"><span className="eyebrow">Answer-first case overview</span><h2>Claim being tested</h2><p>{record.case.why_it_matters}</p><div className="claim-chips">{record.case.claim_ids.map((id) => <span key={id}>{id}</span>)}</div><h3>Expected physical sequence</h3><ol>{record.case.expected_physical_sequence.map((step) => <li key={step}>{step}</li>)}</ol><div className="answer-pair"><div><span>Expected</span><p>{record.case.expected_result_summary}</p></div><div><span>Observed</span><p>{result?.observed_result_summary ?? "No result loaded."}</p></div><div><span>Difference</span><p>{result?.difference_summary ?? "Not yet comparable."}</p></div></div><h3>Limits on interpretation</h3><ul>{record.case.limits_on_interpretation.map((limit) => <li key={limit}>{limit}</li>)}</ul></section>
          <section className="panel validation-metrics"><span className="eyebrow">Declared metrics and tolerances</span>{record.case.metrics.map((metric) => { const observed = metricsById.get(metric.metric_id); return <div key={metric.metric_id} className="metric-row"><div><strong>{metric.label}</strong><small>{metric.tolerance_justification}</small></div><span className={observed?.passed ? "metric-pass" : observed ? "metric-fail" : ""}>{observed ? `${observed.value} / tol ${observed.tolerance} ${observed.units}` : "not run"}</span></div>; })}<div className="safe-claim"><span>Safe claim if passed</span><p>{record.case.safe_claim}</p></div></section>
        </div>
        {result && <section className="panel validation-chart-panel"><div className="panel-heading compact"><div><span className="eyebrow">Expected versus observed</span><h2>Scientific comparison series</h2></div><span className="source-chip">Python comparison</span></div><ValidationComparisonChart validationCase={record.case} result={result} tick={tick} /></section>}
        {bundle && state && series && <>
          <section className="validation-replay-bar panel"><button onClick={() => setTick(bundle.run.start_tick)}>↺</button><button onClick={() => setTick((value) => Math.max(bundle.run.start_tick, value - 1))}>‹</button><input aria-label="Validation replay tick" type="range" min={bundle.run.start_tick} max={bundle.run.end_tick} value={tick} onChange={(event) => setTick(Number(event.target.value))} /><button onClick={() => setTick((value) => Math.min(bundle.run.end_tick, value + 1))}>›</button><strong>tick {tick}</strong><small>Arrow keys step exact replay</small></section>
          <div className="validation-replay-grid"><section className="network-panel panel"><div className="network-heading"><div><span className="eyebrow">Validation replay · exact scientific state</span><h2>{bundle.run.scenario_name}</h2></div><span className="source-chip">canonical + declared overlays</span></div><div className="validation-overlay-strip">{activeOverlays.length ? activeOverlays.map((overlay) => <div key={overlay.overlay_id} className={`overlay-kind-${overlay.kind}`}><strong>{overlay.label}</strong><span>{sourceLabel(overlay.evidence_source)}</span><small>{overlay.note}</small></div>) : <em>No validation overlay active at this tick.</em>}</div><NetworkCanvas manifest={bundle} layout={defaultLayout(bundle)} state={state} selectedLinkId={selectedNodeId || selectedPacketId ? "" : selectedLinkId} selectedNodeId={selectedNodeId} selectedPacketId={selectedPacketId} followingPacket={Boolean(selectedPacketId)} phase={0} validationOverlays={record.case.overlays} onSelectLink={(id) => { setSelectedLinkId(id); setSelectedNodeId(null); setSelectedPacketId(null); }} onSelectNode={(id) => { setSelectedNodeId(id); setSelectedPacketId(null); }} /></section><Inspector manifest={bundle} state={state} events={bundle.event_stream.events} movementEvidence={[]} selectedLinkId={selectedLinkId} selectedNodeId={selectedNodeId} selectedPacketId={selectedPacketId} followingPacket={Boolean(selectedPacketId)} series={series} onSelectPacket={(id) => { setSelectedPacketId(id); setSelectedNodeId(null); }} onSelectLink={(id) => { setSelectedLinkId(id); setSelectedNodeId(null); setSelectedPacketId(null); }} onSelectNode={(id) => { setSelectedNodeId(id); setSelectedPacketId(null); }} onToggleFollow={() => undefined} onNavigateEvent={(event) => { setTick(event.physical_tick); setSelectedPacketId(event.packet_id); }} /></div>
          {selectedPacketId && <section className="panel waiting-explanation"><span className="eyebrow">Why is this packet waiting?</span>{wait ? <><h2>{wait.packet_id}</h2><div className="waiting-grid"><span>Current link<strong>{wait.current_link_id ?? "unavailable"}</strong></span><span>FIFO position<strong>{wait.fifo_position ?? "unavailable"}</strong></span><span>Intended movement<strong>{wait.intended_movement ?? "unavailable"}</strong></span><span>Blocking reason<strong>{wait.blocking_reason ?? "unavailable"}</strong></span><span>Receiving supply<strong>{wait.receiving_supply_packets ?? "unavailable"}</strong></span><span>Expected release<strong>{wait.expected_next_release_tick === null ? "unavailable" : `tick ${wait.expected_next_release_tick}`}</strong></span></div><p>Sources: {wait.evidence_sources.map(sourceLabel).join(" · ")}. Unavailable: {wait.unavailable_fields.join(", ") || "none"}.</p></> : <p>No declared waiting explanation exists for this packet at tick {tick}. No reason is inferred.</p>}</section>}
        </>}
        <div className="validation-bottom-grid"><section className="panel reference-panel"><span className="eyebrow">Literature and reference assets</span>{record.case.reference_assets.map((asset) => <article key={asset.asset_id}><h3>{asset.label}</h3><p>{asset.citation_text}</p><small>{asset.figure_table_equation ?? "No figure/table number"} · {asset.comparison_suitability}</small><p>{asset.rights_provenance_note}</p>{!asset.local_asset_path && <em>No local figure embedded. An allowed image or digitised series can be attached later.</em>}</article>)}</section><section className="panel validation-history"><span className="eyebrow">Append-only scientific history</span>{history.length ? [...history].reverse().map((item) => <button key={item.result_id} onClick={() => void loadResult(item.result_id, record.case)}><span className={`validation-dot status-${item.status}`} /><strong>{item.status}</strong><span>{new Date(item.created_at).toLocaleString()}</span><code>{item.code_commit?.slice(0, 8) ?? "unknown"}</code><small>{item.headline_metric}</small></button>) : <p>No persisted result history.</p>}</section></div>
      </>}
    </section>
  </div>;
}
