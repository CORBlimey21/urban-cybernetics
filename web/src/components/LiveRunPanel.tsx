import type { ArtifactSummary, LiveMessage } from "../lib/contract";

type Props = { run: ArtifactSummary; message: LiveMessage | null; viewerFollowing: boolean; onViewerFollow: () => void; onCommand: (action: "pause" | "resume" | "cancel") => void };

export function LiveRunPanel({ run, message, viewerFollowing, onViewerFollow, onCommand }: Props) {
  const progress = message?.payload ?? {};
  const terminal = ["complete", "cancelled", "timed_out", "failed"].includes(message?.lifecycle_state ?? run.status);
  const state = message?.lifecycle_state ?? run.status;
  return <section className="live-run-panel panel">
    <div><span className="eyebrow">Control plane</span><h2><i className={`lifecycle-dot state-${state}`} /> Python run · {state}</h2><small>{run.run_id}</small></div>
    <div className="live-progress"><span>tick <b>{String(progress.physical_tick ?? run.final_tick)}</b></span><span>events <b>{String(progress.event_count ?? run.event_count)}</b></span><span>complete <b>{String(progress.completed ?? run.counts.completed ?? 0)}</b></span><span>wall <b>{typeof progress.elapsed_wall_seconds === "number" ? `${progress.elapsed_wall_seconds.toFixed(2)}s` : "—"}</b></span></div>
    <div className="live-actions">
      <button className={viewerFollowing ? "active" : ""} onClick={onViewerFollow}>{viewerFollowing ? "Following live" : "Go live"}</button>
      {!terminal && state !== "paused" && <button onClick={() => onCommand("pause")}>Pause run</button>}
      {!terminal && state === "paused" && <button onClick={() => onCommand("resume")}>Resume run</button>}
      {!terminal && <button className="danger" onClick={() => onCommand("cancel")}>Cancel & retain</button>}
    </div>
  </section>;
}
