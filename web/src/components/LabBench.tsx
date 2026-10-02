// SPDX-License-Identifier: MPL-2.0
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import {
  compareLabSeries, createLabStarter, evaluateLabExpression, evaluateLabTable, freezeLabOracle,
  loadLabOracles, loadLabWorksheets, promoteLabWorksheet, saveLabWorksheet,
} from "../lib/api";
import { labWorksheetSchema, type LabComparisonResult, type LabEvaluationResult, type LabOracle, type LabWorksheet, type ValidationCase, type ValidationResult } from "../lib/contract";
import { LabBenchChart } from "./LabBenchChart";

type Mode = "notebook" | "calculator" | "table" | "graph" | "compare" | "oracle";
type ExportedSeries = { label: string; ticks: number[]; values: number[]; units: string; provenance: string };
const modes: { id: Mode; label: string }[] = [
  { id: "notebook", label: "Notebook" }, { id: "calculator", label: "Calculator" }, { id: "table", label: "Tick table" },
  { id: "graph", label: "Graph" }, { id: "compare", label: "Compare" }, { id: "oracle", label: "Oracle" },
];

const readPreference = <T,>(key: string, fallback: T): T => {
  try { return JSON.parse(window.localStorage.getItem(key) ?? "") as T; } catch { return fallback; }
};

function NotebookPreview({ value }: { value: string }) {
  return <div className="lab-note-preview">{value.split("\n").map((line, index) => {
    if (line.startsWith("# ")) return <h2 key={index}>{line.slice(2)}</h2>;
    if (line.startsWith("## ")) return <h3 key={index}>{line.slice(3)}</h3>;
    if (line.startsWith("- ")) return <li key={index}>{line.slice(2)}</li>;
    if (line.startsWith("$$") && line.endsWith("$$")) return <div className="lab-equation" key={index}>{line.slice(2, -2)}</div>;
    return <p key={index}>{line || "\u00a0"}</p>;
  })}</div>;
}

export function LabBench({ validationCase, result, onExport }: { validationCase: ValidationCase; result: ValidationResult | null; onExport: (series: ExportedSeries) => void }) {
  const prefix = "uc.labBench.presentation.v1";
  const [open, setOpen] = useState(() => readPreference(`${prefix}.open`, false));
  const [minimized, setMinimized] = useState(() => readPreference(`${prefix}.minimized`, false));
  const [floating, setFloating] = useState(() => readPreference(`${prefix}.floating`, false));
  const [panelSize, setPanelSize] = useState(() => readPreference(`${prefix}.size`, { width: 760, height: 720 }));
  const [panelPosition, setPanelPosition] = useState(() => readPreference(`${prefix}.position`, { x: Math.max(16, window.innerWidth - 840), y: 128 }));
  const [mode, setMode] = useState<Mode>(() => readPreference(`${prefix}.mode`, "notebook"));
  const [worksheet, setWorksheet] = useState<LabWorksheet | null>(null);
  const [worksheets, setWorksheets] = useState<LabWorksheet[]>([]);
  const [oracles, setOracles] = useState<LabOracle[]>([]);
  const [calculator, setCalculator] = useState("ceil(length / free_flow_speed / timestep)");
  const [calculation, setCalculation] = useState<LabEvaluationResult | null>(null);
  const [graphColumns, setGraphColumns] = useState<string[]>(["cumulative_entries", "cumulative_exits"]);
  const [graphKind, setGraphKind] = useState<"line" | "step" | "scatter">("step");
  const [expectedColumn, setExpectedColumn] = useState("");
  const [observedSeries, setObservedSeries] = useState("");
  const [observedSource, setObservedSource] = useState<"uc" | "fixture">("uc");
  const [tickOffset, setTickOffset] = useState(0);
  const [tolerance, setTolerance] = useState(0);
  const [comparison, setComparison] = useState<LabComparisonResult | null>(null);
  const [comparisonState, setComparisonState] = useState<"scratch" | "candidate_reference" | "frozen_oracle">("scratch");
  const [approval, setApproval] = useState("");
  const [status, setStatus] = useState("Ready");
  const [error, setError] = useState<string | null>(null);
  const autosaveReady = useRef(false);
  const panelRef = useRef<HTMLElement>(null);
  const pointerAction = useRef<null | { kind: "drag" | "resize"; startX: number; startY: number; x: number; y: number; width: number; height: number }>(null);
  const autosaveSignature = useMemo(() => worksheet ? JSON.stringify({
    title: worksheet.title, notebook: worksheet.notebook, table: worksheet.table,
    variables: worksheet.variables, assumptions: worksheet.assumptions, limitations: worksheet.limitations,
    detached: worksheet.detached, case_id: worksheet.case_id, case_version: worksheet.case_version,
  }) : "", [worksheet]);

  const refreshLibrary = useCallback(async () => {
    const [saved, frozen] = await Promise.all([loadLabWorksheets(), loadLabOracles(validationCase.case_id)]);
    setWorksheets(saved); setOracles(frozen);
    const remembered = readPreference<string | null>(`${prefix}.worksheet`, null);
    setWorksheet((current) => current ?? saved.find((item) => item.worksheet_id === remembered) ?? saved.find((item) => item.case_id === validationCase.case_id) ?? null);
  }, [validationCase.case_id]);

  useEffect(() => { if (open) void refreshLibrary().catch((reason) => setError(String(reason))); }, [open, refreshLibrary]);
  useEffect(() => { window.localStorage.setItem(`${prefix}.open`, JSON.stringify(open)); }, [open]);
  useEffect(() => { window.localStorage.setItem(`${prefix}.minimized`, JSON.stringify(minimized)); }, [minimized]);
  useEffect(() => { window.localStorage.setItem(`${prefix}.floating`, JSON.stringify(floating)); }, [floating]);
  useEffect(() => { window.localStorage.setItem(`${prefix}.position`, JSON.stringify(panelPosition)); }, [panelPosition]);
  useEffect(() => { window.localStorage.setItem(`${prefix}.mode`, JSON.stringify(mode)); }, [mode]);
  useEffect(() => {
    const element = panelRef.current; if (!element || minimized) return;
    const observer = new ResizeObserver(([entry]) => {
      const next = { width: Math.round(entry.contentRect.width), height: Math.round(entry.contentRect.height) };
      setPanelSize(next); window.localStorage.setItem(`${prefix}.size`, JSON.stringify(next));
    });
    observer.observe(element); return () => observer.disconnect();
  }, [minimized]);
  useEffect(() => { if (worksheet) window.localStorage.setItem(`${prefix}.worksheet`, JSON.stringify(worksheet.worksheet_id)); }, [worksheet]);

  useEffect(() => {
    if (!worksheet) return;
    if (!autosaveReady.current) { autosaveReady.current = true; return; }
    const timer = window.setTimeout(() => void saveLabWorksheet(worksheet).then(() => setStatus("Autosaved scratch state")).catch((reason) => setError(String(reason))), 850);
    return () => window.clearTimeout(timer);
  }, [autosaveSignature]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedGraphColumns = useMemo(() => worksheet?.table.columns.filter((item) => graphColumns.includes(item.column_id)) ?? [], [graphColumns, worksheet]);
  const ticks = worksheet ? Array.from({ length: worksheet.table.tick_end - worksheet.table.tick_start + 1 }, (_, index) => worksheet.table.tick_start + index) : [];
  const linkedMismatch = worksheet && !worksheet.detached && worksheet.case_id !== validationCase.case_id;

  const start = async () => {
    setError(null); const created = await createLabStarter(validationCase.case_id); setWorksheet(created); setWorksheets((items) => [...items, created]); setComparisonState("scratch"); setStatus("Starter created from declared inputs; fixture expectations were not imported.");
  };
  const update = (next: LabWorksheet) => { setWorksheet(next); setComparisonState(next.state); };
  const saveHistory = async () => { if (!worksheet) return; update(await saveLabWorksheet(worksheet, true)); setStatus("Explicit revision saved"); };
  const exportWorksheet = () => {
    if (!worksheet) return;
    const url = URL.createObjectURL(new Blob([`${JSON.stringify(worksheet, null, 2)}\n`], { type: "application/json" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${worksheet.worksheet_id}.json`; anchor.click(); URL.revokeObjectURL(url);
  };
  const importWorksheet = async (file: File) => {
    const parsed = labWorksheetSchema.parse(JSON.parse(await file.text())); const now = new Date().toISOString();
    const imported = await saveLabWorksheet({ ...parsed, worksheet_id: `import-${crypto.randomUUID()}`, revision: 0, state: "scratch", created_at: now, updated_at: now, author_source: "imported", notebook: { ...parsed.notebook, origin: "imported" } });
    setWorksheets((items) => [...items, imported]); setWorksheet(imported); setComparisonState("scratch"); setStatus("Imported as a new scratch worksheet; no authority was inherited.");
  };
  const evaluateTable = async () => { if (!worksheet) return; const evaluated = await evaluateLabTable(worksheet); update({ ...worksheet, table: evaluated.table }); setStatus(`Evaluated: ${evaluated.dependency_order.join(" → ")}`); };

  const updateManualCell = (columnId: string, row: number, text: string) => {
    if (!worksheet) return; const value = Number(text); if (!Number.isFinite(value)) return;
    update({ ...worksheet, table: { ...worksheet.table, columns: worksheet.table.columns.map((column) => column.column_id === columnId ? { ...column, values: column.values.map((item, index) => index === row ? value : item) } : column) } });
  };
  const updateTickRange = (tickStart: number, tickEnd: number) => {
    if (!worksheet || !Number.isInteger(tickStart) || !Number.isInteger(tickEnd) || tickEnd < tickStart || tickEnd - tickStart > 500) return;
    const size = tickEnd - tickStart + 1;
    update({ ...worksheet, table: { ...worksheet.table, tick_start: tickStart, tick_end: tickEnd, columns: worksheet.table.columns.map((column) => ({ ...column, values: column.kind === "formula_derived" ? [] : Array.from({ length: size }, (_, index) => column.values[index] ?? 0) })) } });
  };
  const pasteColumn = (columnId: string, row: number, text: string) => {
    if (!worksheet || !/[\t\n]/.test(text)) return false;
    const values = text.trim().split(/[\t\n]+/).map(Number); if (values.some((item) => !Number.isFinite(item))) return false;
    update({ ...worksheet, table: { ...worksheet.table, columns: worksheet.table.columns.map((column) => column.column_id === columnId ? { ...column, values: column.values.map((item, index) => values[index - row] ?? item) } : column) } }); return true;
  };
  const runComparison = async () => {
    if (!worksheet) return;
    const expected = worksheet.table.columns.find((item) => item.column_id === expectedColumn);
    const source = observedSource === "uc" ? result?.observed_series : validationCase.expected_series;
    const observed = source?.find((item) => item.series_id === observedSeries);
    if (!expected || !observed) { setError("Choose both series explicitly."); return; }
    const mapping = { expected_column_id: expected.column_id, observed_series_id: observed.series_id, time_alignment: tickOffset ? "offset" : "same_tick", tick_offset: tickOffset, expected_units: expected.units, observed_units: observed.units, metric: "exact", tolerance };
    setComparison(await compareLabSeries({ mapping, expected_ticks: ticks, expected_values: expected.values, observed_ticks: observed.ticks, observed_values: observed.values, expected_state: comparisonState }));
  };
  const beginPointerAction = (kind: "drag" | "resize", event: ReactPointerEvent) => {
    if (event.button !== 0 || !panelRef.current) return;
    const rect = panelRef.current.getBoundingClientRect();
    setFloating(true);
    setPanelPosition({ x: Math.round(rect.left), y: Math.round(rect.top) });
    pointerAction.current = { kind, startX: event.clientX, startY: event.clientY, x: rect.left, y: rect.top, width: rect.width, height: rect.height };
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  };
  const movePointerAction = (event: ReactPointerEvent) => {
    const action = pointerAction.current;
    if (!action) return;
    const dx = event.clientX - action.startX; const dy = event.clientY - action.startY;
    if (action.kind === "drag") {
      setPanelPosition({ x: Math.max(0, Math.min(window.innerWidth - 180, Math.round(action.x + dx))), y: Math.max(0, Math.min(window.innerHeight - 54, Math.round(action.y + dy))) });
    } else {
      setPanelSize({ width: Math.max(520, Math.min(window.innerWidth - action.x, Math.round(action.width + dx))), height: Math.max(260, Math.min(window.innerHeight - action.y, Math.round(action.height + dy))) });
    }
  };
  const endPointerAction = (event: ReactPointerEvent) => {
    if (!pointerAction.current) return;
    pointerAction.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
  };

  if (!open) return <button className="lab-launch" onClick={() => setOpen(true)}><span>LAB</span> Open Lab Bench</button>;
  return <aside ref={panelRef} style={minimized ? undefined : floating ? { left: panelPosition.x, top: panelPosition.y, width: Math.min(panelSize.width, window.innerWidth - panelPosition.x), height: Math.min(panelSize.height, window.innerHeight - panelPosition.y) } : { width: Math.min(panelSize.width, window.innerWidth - 30), height: Math.min(panelSize.height, window.innerHeight - 108) }} className={`lab-bench panel ${floating ? "floating" : "docked"} ${minimized ? "minimized" : ""}`}>
    <header className="lab-header" tabIndex={0} aria-keyshortcuts="Tab" onKeyDown={(event) => { if (event.key === "Tab" && event.target === event.currentTarget) { event.preventDefault(); setMinimized((value) => !value); } }} onPointerDown={(event) => { if (!(event.target as HTMLElement).closest("button")) beginPointerAction("drag", event); }} onPointerMove={movePointerAction} onPointerUp={endPointerAction}><div><span className="eyebrow">Scientific derivation workspace · V1</span><strong>Lab Bench</strong><small>{worksheet?.state.replaceAll("_", " ") ?? "no worksheet"} · {worksheet?.case_id ?? "general scratch"} · Tab toggles minimise</small></div><div><button onClick={() => setFloating((value) => !value)}>{floating ? "Dock" : "Float"}</button><button onClick={() => setMinimized((value) => !value)}>{minimized ? "Restore" : "Minimise"}</button><button aria-label="Close Lab Bench" onClick={() => setOpen(false)}>×</button></div></header>
    {!minimized && <>
      <div className="lab-toolbar">
        <select aria-label="Lab Bench worksheet" value={worksheet?.worksheet_id ?? ""} onChange={(event) => { const selected = worksheets.find((item) => item.worksheet_id === event.target.value) ?? null; setWorksheet(selected); setComparisonState(selected?.state ?? "scratch"); }}><option value="">No worksheet</option>{worksheets.map((item) => <option key={item.worksheet_id} value={item.worksheet_id}>{item.title} · r{item.revision}</option>)}</select>
        <button onClick={() => void start().catch((reason) => setError(String(reason)))} disabled={validationCase.case_id !== "M8-LINK-01"}>New M8-LINK-01 derivation</button>
        <button onClick={() => worksheet && update({ ...worksheet, detached: true, case_id: null, case_version: null })} disabled={!worksheet}>Detach workspace</button>
        <button onClick={() => void saveHistory().catch((reason) => setError(String(reason)))} disabled={!worksheet}>Save revision</button>
        <button onClick={exportWorksheet} disabled={!worksheet}>Export JSON</button>
        <label className="lab-import">Import JSON<input type="file" accept="application/json,.json" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importWorksheet(file).catch((reason) => setError(String(reason))); event.target.value = ""; }} /></label>
      </div>
      {linkedMismatch && <div className="lab-warning">Linked worksheet remains on {worksheet.case_id}; selected case is {validationCase.case_id}. Dependencies were not silently changed.</div>}
      {error && <div className="lab-error">{error}<button onClick={() => setError(null)}>×</button></div>}
      <nav className="lab-tabs">{modes.map((item) => <button className={mode === item.id ? "active" : ""} key={item.id} onClick={() => setMode(item.id)}>{item.label}</button>)}</nav>
      <div className="lab-content">
        {!worksheet ? <div className="lab-empty"><strong>Start with declared inputs</strong><p>Create the M8-LINK-01 starter to derive cumulative curves without importing its fixture expectations.</p></div> : <>
          {mode === "notebook" && <section className="lab-notebook"><div><label>Markdown + LaTeX source <span>{worksheet.notebook.origin.replaceAll("_", " ")}</span></label><textarea value={worksheet.notebook.markdown} onChange={(event) => update({ ...worksheet, notebook: { ...worksheet.notebook, markdown: event.target.value } })} /></div><div><label>Preview <span>scratch material</span></label><NotebookPreview value={worksheet.notebook.markdown} /></div></section>}
          {mode === "calculator" && <section className="lab-calculator"><div className="lab-input-catalog"><h3>Declared inputs</h3>{worksheet.variables.map((item) => <div className="lab-variable" key={item.variable_id}><button onClick={() => setCalculator((value) => `${value}${value ? " " : ""}${item.variable_id}`)}><strong>{item.variable_id}</strong><span>{Array.isArray(item.value) ? item.value.join(", ") : item.value} {item.units}</span><small>{item.source}</small></button><button className={item.linked ? "linked" : "detached"} onClick={() => update({ ...worksheet, variables: worksheet.variables.map((variable) => variable.variable_id === item.variable_id ? { ...variable, linked: !variable.linked } : variable) })}>{item.linked ? "Detach as literal" : "Relink"}</button></div>)}</div><div className="lab-calc-pad"><label>Bounded expression</label><input value={calculator} onChange={(event) => setCalculator(event.target.value)} /><button onClick={() => void evaluateLabExpression(calculator, worksheet.variables).then(setCalculation).catch((reason) => setError(String(reason)))}>Evaluate deterministically</button><p className="lab-security">Arithmetic, powers, min/max/abs/ceil/floor/sum, comparisons and tick/time conversion only. No Python, shell, imports, filesystem, network or browser eval.</p>{calculation && <article><code>{calculation.expression}</code><p>{calculation.substituted_expression}</p><strong>{String(calculation.value)} {calculation.units}</strong><ol>{calculation.steps.map((step) => <li key={step}>{step}</li>)}</ol></article>}</div></section>}
          {mode === "table" && <section className="lab-table-mode"><header><div className="lab-range"><label>Tick start<input aria-label="Tick start" type="number" value={worksheet.table.tick_start} onChange={(event) => updateTickRange(Number(event.target.value), worksheet.table.tick_end)} /></label><label>Tick end<input aria-label="Tick end" type="number" value={worksheet.table.tick_end} onChange={(event) => updateTickRange(worksheet.table.tick_start, Number(event.target.value))} /></label><span>{worksheet.table.evaluation_order.replaceAll("_", " ")}</span></div><button onClick={() => void evaluateTable().catch((reason) => setError(String(reason)))}>Recalculate in Python</button></header><div className="lab-table-scroll"><table><thead><tr><th>tick</th>{worksheet.table.columns.map((column) => <th key={column.column_id}><strong>{column.label}</strong><span>{column.units}</span><em className={`kind-${column.kind}`}>{column.kind.replaceAll("_", " ")}</em>{column.formula && <input className="lab-formula" aria-label={`${column.label} formula`} value={column.formula} onChange={(event) => update({ ...worksheet, table: { ...worksheet.table, columns: worksheet.table.columns.map((item) => item.column_id === column.column_id ? { ...item, formula: event.target.value, values: [] } : item) } })} />}</th>)}</tr></thead><tbody>{ticks.map((tick, row) => <tr key={tick}><th>{tick}</th>{worksheet.table.columns.map((column) => <td key={column.column_id}>{column.kind === "manual" ? <input aria-label={`${column.label} tick ${tick}`} value={column.values[row] ?? ""} onPaste={(event) => { if (pasteColumn(column.column_id, row, event.clipboardData.getData("text"))) event.preventDefault(); }} onChange={(event) => updateManualCell(column.column_id, row, event.target.value)} /> : <span>{column.values[row] ?? "—"}</span>}</td>)}</tr>)}</tbody></table></div><footer>Out-of-range conventions: {Object.entries(worksheet.table.out_of_range_values).map(([key, value]) => `${key}[t&lt;0]=${value}`).join(" · ") || "none declared"}</footer></section>}
          {mode === "graph" && <section className="lab-graph-mode"><header><div>{worksheet.table.columns.map((column) => <label key={column.column_id}><input type="checkbox" checked={graphColumns.includes(column.column_id)} onChange={() => setGraphColumns((items) => items.includes(column.column_id) ? items.filter((id) => id !== column.column_id) : [...items, column.column_id])} />{column.label}</label>)}</div><select value={graphKind} onChange={(event) => setGraphKind(event.target.value as typeof graphKind)}><option value="line">Line</option><option value="step">Step</option><option value="scatter">Scatter</option></select></header><LabBenchChart columns={selectedGraphColumns} ticks={ticks} kind={graphKind} validationCase={validationCase} /><button onClick={() => { const column = selectedGraphColumns[0]; if (column) onExport({ label: column.label, ticks, values: column.values, units: column.units, provenance: column.provenance }); }} disabled={!selectedGraphColumns.length}>Export first selected series into validation comparison</button><small>Chart state is presentation-only; formulas and values remain persisted scientific working state.</small></section>}
          {mode === "compare" && <section className="lab-compare"><div className="lab-map"><label>Expected Lab series<select value={expectedColumn} onChange={(event) => setExpectedColumn(event.target.value)}><option value="">Choose explicitly…</option>{worksheet.table.columns.map((column) => <option key={column.column_id} value={column.column_id}>{column.label} · {column.units}</option>)}</select></label><span>↔</span><label>Observed source<select value={observedSource} onChange={(event) => { setObservedSource(event.target.value as "uc" | "fixture"); setObservedSeries(""); }}><option value="uc">UC-observed evidence</option><option value="fixture">Existing fixture oracle</option></select></label><label>Observed series<select value={observedSeries} onChange={(event) => setObservedSeries(event.target.value)}><option value="">Choose explicitly…</option>{(observedSource === "uc" ? result?.observed_series : validationCase.expected_series)?.map((series) => <option key={series.series_id} value={series.series_id}>{series.label} · {series.units}</option>)}</select></label><label>Tick offset<input type="number" value={tickOffset} onChange={(event) => setTickOffset(Number(event.target.value))} /></label><label>Tolerance<input type="number" min="0" step="any" value={tolerance} onChange={(event) => setTolerance(Number(event.target.value))} /></label><button onClick={() => void runComparison().catch((reason) => setError(String(reason)))}>Compare in Python</button></div>{comparison && <article className={comparison.formal ? "formal" : "informal"}><strong>{comparison.label}</strong><div><span>Exact<b>{comparison.exact ? "yes" : "no"}</b></span><span>Max |error|<b>{comparison.maximum_absolute_error}</b></span><span>Mean |error|<b>{comparison.mean_absolute_error.toPrecision(4)}</b></span><span>First mismatch<b>{comparison.first_mismatch_tick ?? "none"}</b></span><span>Rows mismatched<b>{comparison.mismatched_rows}</b></span><span>Tick offset<b>{comparison.tick_offset}</b></span></div></article>}</section>}
          {mode === "oracle" && <section className="lab-oracle"><div className="lab-lifecycle"><span className={worksheet.state === "scratch" ? "active" : "done"}>Scratch</span><i>→</i><span className={worksheet.state === "candidate_reference" ? "active" : ""}>Candidate reference</span><i>→</i><span>Frozen oracle</span></div>{worksheet.state === "scratch" ? <button onClick={() => void promoteLabWorksheet(worksheet.worksheet_id).then(update).catch((reason) => setError(String(reason)))}>Promote to candidate reference</button> : <><div className="oracle-review"><h3>Freeze review</h3><p><b>Case</b>{worksheet.case_id} v{worksheet.case_version}</p><p><b>Quantities</b>{worksheet.table.columns.map((item) => item.label).join(", ")}</p><p><b>Formulas</b>{worksheet.table.columns.filter((item) => item.formula).map((item) => `${item.column_id}=${item.formula}`).join("; ")}</p><p><b>Inputs</b>{worksheet.variables.filter((item) => item.linked).map((item) => item.variable_id).join(", ")}</p><p><b>Units</b>{[...new Set(worksheet.table.columns.map((item) => item.units))].join(", ")}</p><p><b>Tick convention</b>inclusive integer ticks; explicit zero prehistory</p><p><b>Limitations</b>{worksheet.limitations.join(" ")}</p></div><label>Approval action<input value={approval} placeholder="Describe the deliberate review performed" onChange={(event) => setApproval(event.target.value)} /></label><button disabled={approval.trim().length < 3 || !worksheet.case_id} onClick={() => void freezeLabOracle(worksheet.worksheet_id, approval, ["Frozen deliberately in Lab Bench."], worksheet.limitations).then((oracle) => { setOracles((items) => [...items, oracle]); setComparisonState("frozen_oracle"); setStatus(`Frozen ${oracle.oracle_id} v${oracle.version} · ${oracle.artifact_hash.slice(0, 12)}`); }).catch((reason) => setError(String(reason)))}>Freeze immutable version</button></>}
            <div className="oracle-list"><h3>Append-only frozen versions</h3>{oracles.map((oracle) => <button key={`${oracle.oracle_id}-${oracle.version}`} onClick={() => { setWorksheet(oracle.worksheet); setComparisonState("frozen_oracle"); setMode("compare"); }}><strong>{oracle.oracle_id} · v{oracle.version}</strong><span>{oracle.author_source.replaceAll("_", " ")}</span><code>{oracle.artifact_hash.slice(0, 16)}</code><small>{oracle.approval_action}</small></button>)}</div>
          </section>}
        </>}
      </div>
      <footer className="lab-status"><span>{status}</span><strong>Scratch and candidate material never affects pass/fail. Only explicit frozen oracles are formally eligible.</strong></footer>
    </>}
    {!minimized && <div className="lab-resize-handle" aria-hidden="true" onPointerDown={(event) => beginPointerAction("resize", event)} onPointerMove={movePointerAction} onPointerUp={endPointerAction} />}
  </aside>;
}
