# Paper 1 claim-support audit

Status is limited to the exact evidence frozen in `evidence_manifest_v1.json`.
“Supported with qualifier” means the stated boundary belongs in the manuscript
wherever the claim appears.

## Physical validity

| Intended claim | Status | Evidence and manuscript boundary |
| --- | --- | --- |
| Unit packets retain stable identity and exact network conservation. | Supported | Frozen internal cases, M8-COMP-NET-01, published-comparison gates, exact replay, and Cork horizon ledgers. |
| Link and route service is FIFO. | Supported | Exact internal FIFO cases, strict-diverge fixtures, parity torture, composed case, and published diverge/merge gates. This is mesoscopic FIFO, not microscopic lane order. |
| Links have finite storage and propagate spillback. | Supported | Storage-constrained link cases, backward-wave recurrence, composed bottleneck, and scale-ladder validation gates. |
| Supported merge and diverge allocators behave as declared. | Supported with qualifier | Exact internal oracles plus observational de Souza Figure 7/9 comparisons. The external curves are digitised observational comparisons, not proof of equivalence to every LTM convention. |
| Identical inputs reproduce the canonical physical event stream. | Supported | Frozen verifier, exact replay fixtures, 100-replication replay, Maryville smoke, Boreenmanna cases, and Cork replay through the declared replay limits. |
| The simulator is externally validated for arbitrary networks or every published LTM convention. | Unsupported / future work | Remove or weaken. Claim only the named exact internal cases and named observational published comparisons. |

## Junction representation

| Intended claim | Status | Evidence and manuscript boundary |
| --- | --- | --- |
| Shared-link representation enforces strict head-of-line FIFO. | Supported | Canonical lane-group fixtures and Boreenmanna controlled cases. |
| Movement-partial FIFO permits declared independent movement service. | Supported | Exact fixture and representation-parity cases. It is an aggregate movement partition, not a lane-changing model. |
| Explicit lane-group queues partition FIFO service by declared group. | Supported with qualifier | Exact extension fixtures and synthetic Boreenmanna lane-to-movement assignments. No microscopic lateral position or lane-changing claim. |
| Representation choice changes congestion, evaluation throughput, queue delay, and clearance in the controlled study. | Supported with qualifier | Full-export matrix `3d493f...`, compact matrix `b2f1be...`, and integrity audit `b047b4...`. Demand, controllers, lane assignments, and several physical values are authored; this is controlled evidence on real geometry, not real Boreenmanna traffic validation. |
| The explicit Boreenmanna lane groups are observed real lane connectivity. | Unsupported / future work | Remove. They are explicitly synthetic experiment evidence. |

## Fractional service and readiness

| Intended claim | Status | Evidence and manuscript boundary |
| --- | --- | --- |
| Indivisible packets can represent sub-unit continuous capacity through deterministic credit. | Supported | Analytical recurrence tests, exact service totals, conserved whole-packet execution, and deterministic evidence hashes. |
| V1 has a signal-phase aliasing boundary under periodic gating. | Supported | Analytical and regression fixtures show legitimate 0-or-80 service phase outcomes for the tested GGRR case. Describe this as a V1 boundary, not a generic failure of fractional credit. |
| V2 makes accrual gate-aware and removes the tested rational phase lock. | Supported | Analytical hash `95d107...` and Boreenmanna V2 deterministic package `76a812...`; tested offsets all serve at the expected gate-aware rate. |
| V3 adds optional first-order discharge-readiness dynamics. | Supported with qualifier | Analytical hash `26b50a...` and V3 deterministic package `cf480f...`. The exponential form and time constants are experimental and uncalibrated. |
| Baseline V3 materially changes the Boreenmanna representation conclusion. | Unsupported | Remove. Under the baseline it adds modest delay and at most one clearance tick while preserving evaluation completions, eventual completions, and representation ordering. |
| Baseline V3 has limited effect under the controlled Boreenmanna settings. | Supported with qualifier | V3 core results show the stated modest delay/clearance effect; sensitivity can be larger for explicit groups. Do not generalise beyond this synthetic baseline. |

## Provenance-aware compilation

| Intended claim | Status | Evidence and manuscript boundary |
| --- | --- | --- |
| The compiler distinguishes observed, inferred, defaulted, overridden, synthetic, and unresolved semantics. | Supported | Compiler provenance records and exact classification tests for both real OSM cases. |
| Unresolved mandatory or contradictory semantics are refused deterministically. | Supported | Guarded `require_executable()`, source-strict/refusal tests, diagnostic hashes, and package tamper checks. |
| Boreenmanna is a real-data compiler case. | Supported with qualifier | Pinned real OSM geometry/source identity and deterministic extraction are supported; source-strict and reviewed packages remain non-executable because controller semantics are absent. The executable experiment adds synthetic control/demand. |
| Maryville–Blackrock is an executable real unsignalised compiler case. | Supported with qualifier | Real pinned OSM geometry, observed lanes/speed, explicit reviewed engineering priors, shared-FIFO movement review, deterministic six-movement synthetic smoke. It is not calibrated traffic validation. |
| The importer implements all OSM semantics. | Unsupported / future work | Remove. Claim only the documented Paper 1 constructs and deterministic refusal outside them. |

## Scalability

| Intended claim | Status | Evidence and manuscript boundary |
| --- | --- | --- |
| The frozen stack executes high packet counts on a smaller canonical network with exact completed-run conservation. | Supported with qualifier | Sioux Falls passes through 200,000 completed packets; exact replay is run at 10,000 and larger replay is skipped by policy. The 360,600 rung is a guarded failure and is not validated completion evidence. |
| The full Cork topology executes a common fixed horizon. | Supported | 5,891 nodes, 13,111 directed edges, and all five declared rungs execute 15,000 ticks. |
| The 10,000-packet synthetic Cork rung has exact conservation. | Supported | At the horizon: 9,687 admitted = 631 completed + 9,056 active/queued; 313 pending origin admissions; requested 10,000 = admitted + pending. Event and horizon-state hashes are frozen. |
| The Cork study establishes calibrated Cork congestion, demand, delay, queue, or capacity. | Unsupported / future work | Remove. Cork uses seeded synthetic demand and uncalibrated road-class engineering parameters. |
| Timing and memory numbers are portable deterministic results. | Unsupported | Report them as recording-machine measurements only; use deterministic event/state/run identities for reproduction. |

## Optional cybernetics composition proof

| Intended claim | Status | Evidence and manuscript boundary |
| --- | --- | --- |
| Observation, information visibility, authority choice, and physical execution compose as separate paths. | Supported with qualifier | The small deterministic asymmetric-information fixture gives fresh and stale authorities different visible frames and routes, then independently executes both routes through the loading engine. This is proof of capability only and belongs to UC II if a substantive policy claim is desired. |

## Required manuscript weakening

- Do not call the Boreenmanna synthetic experiment real traffic validation or
  claim observed lane connectivity/controller timing.
- Do not call Maryville calibrated; its demand is a deterministic smoke and its
  missing physical values use explicit reviewed priors.
- Do not claim calibrated Cork operations or portable performance.
- Do not claim full OSM coverage, universal LTM equivalence, or external
  validation beyond the named observational comparisons.
- Do not claim the guarded 360,600 Sioux Falls rung passed.
