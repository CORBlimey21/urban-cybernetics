import type { ArtifactSummary } from "../lib/contract";

type Props = {
  artifacts: ArtifactSummary[];
  loadedRunId: string | null;
  pinned: string[];
  onLoad: (artifact: ArtifactSummary) => void;
  onRefresh: () => void;
  onNewRun: () => void;
  onPin: (runId: string) => void;
};

export function RunLibrary({ artifacts, loadedRunId, pinned, onLoad, onRefresh, onNewRun, onPin }: Props) {
  return <aside className="run-library panel">
    <div className="library-heading"><div><span className="eyebrow">Evidence plane</span><h2>Run library</h2></div><button className="icon-action" onClick={onRefresh} aria-label="Refresh artifact library">↻</button></div>
    <button className="new-run-button" onClick={onNewRun}>＋ New sanctioned run</button>
    <div className="library-filters"><span>{artifacts.length} persisted artifacts</span><span>declared storage root</span></div>
    <div className="artifact-list">
      {artifacts.map((artifact) => <article className={`artifact-card ${loadedRunId === artifact.run_id ? "selected" : ""}`} key={artifact.run_id}>
        <button className="artifact-main" onClick={() => onLoad(artifact)}>
          <span className="artifact-topline"><i className={`lifecycle-dot state-${artifact.status}`} />{artifact.status}<em>{artifact.artifact_format === "v1_bundle" ? "V1" : "V2"}</em></span>
          <strong>{artifact.title}</strong>
          <small>{artifact.topology_id}</small>
          <span className="artifact-counts">{artifact.event_count} events · t{artifact.final_tick}</span>
        </button>
        <button className={`pin-button ${pinned.includes(artifact.run_id) ? "active" : ""}`} onClick={() => onPin(artifact.run_id)} aria-label="Pin run for comparison">◇</button>
      </article>)}
    </div>
  </aside>;
}
