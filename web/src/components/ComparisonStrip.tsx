// SPDX-License-Identifier: MPL-2.0
import type { ArtifactSummary } from "../lib/contract";

export function ComparisonStrip({ runs, onClear }: { runs: ArtifactSummary[]; onClear: () => void }) {
  if (runs.length !== 2) return null;
  const [left, right] = runs;
  return <section className="comparison-strip panel"><div><span className="eyebrow">Comparison foundation</span><h2>Pinned outcome evidence</h2></div>{runs.map((run) => <article key={run.run_id}><strong>{run.title}</strong><span>{run.status} · {run.event_count} events · t{run.final_tick}</span><small>{run.topology_id} · {run.physical_profile_id}</small></article>)}<div className="compatibility"><span className={left.topology_hash === right.topology_hash ? "ok" : "warn"}>topology {left.topology_hash === right.topology_hash ? "compatible" : "differs"}</span><span className={left.profile_hash === right.profile_hash ? "ok" : "warn"}>profile {left.profile_hash === right.profile_hash ? "compatible" : "differs"}</span></div><button onClick={onClear}>Clear</button></section>;
}
