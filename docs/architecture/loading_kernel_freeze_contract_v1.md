# Loading kernel freeze contract v1

Status: canonical scientific compatibility boundary.

Freeze name: Urban Cybernetics Base Loading Kernel v1

Freeze version: `loading-kernel-v1.0.0`

Freeze date: 2026-07-16

Kernel profile: `parity_ltm_v1`

Kernel/evidence tree boundary: `6fb834c7ace57421e0816f2894cc5f53e1f898c0`

The machine-readable manifest records the documentation-seal commit after the
first freeze commit exists. The proposed annotated tag is
`loading-kernel-v1.0.0`; it is a recommendation, not a tag created by this
work.

## Frozen mechanics

This compatibility boundary includes:

- immutable unit-packet identity, lifecycle, and exact conservation;
- loading-owned canonical append-only physical events, deterministic event
  order, and exact replay;
- immutable topology during a run;
- event-derived aggregate and immutable-route-disaggregated cumulative counts;
- free-flow-lagged sending, FIFO-prefix eligibility, fractional sending
  capacity carry, and physical packet eligibility;
- backward-wave-lagged receiving, retained unused receiving credit, storage
  accounting, vacancy propagation, spillback, and the distinction between
  physical shortage and governance closure;
- one-to-one transfers, strict route-encoded diverges, immutable stochastic
  route commodities, equal-priority merges, declared cyclic-priority merges,
  and the supported movement-based MIMO allocator;
- exact node and network conservation under the documented discrete
  unit-packet and tick conventions.

Validated node families are one-to-one, strict route-encoded diverge,
equal-priority merge, declared cyclic-priority merge, and supported declared
movement-based MIMO. Partial-FIFO, conflict-resource, lane-group, signal-gate,
and movement-closure paths have exact internal coverage but are not promoted
to independent external-validation claims by this freeze.

## Evidence boundary

Exact internal invariants and analytical fixtures cover link recurrences,
storage, timing, FIFO, event order, allocation, conservation, and replay. The
accepted observational literature set is:

- de Souza Figure 5, lane-drop benchmark;
- de Souza Figure 7, deterministic route-encoded diverge;
- de Souza Figure 8, seeded stochastic route-encoded diverge ensemble;
- de Souza Figure 9(a–c), equal-priority merge;
- de Souza Figure 9(d–f), asymmetric merge interpreted as `alpha_1=0.75` and
  `x=[0,0,0,1]`.

Published-curve comparisons remain observational evidence, not fitted exact
oracles. Their digitisation and paper-convention discrepancies are preserved
and classified in the validation dossier and comparison reports. No completed
external case identified a loading-kernel discrepancy.

## Covered inputs and outputs

Covered inputs are immutable topology and physical link metadata, declared
demand and packet routes, tick duration, capacity/storage parameters, declared
junction movements and priorities, receiving gates, and deterministic seeds
where a fixture declares stochastic routes.

Covered outputs are canonical packet events and identities, packet locations
and completion state, allocation traces, aggregate and route-disaggregated
cumulative boundary counts, storage and eligible queues, conservation and
closure evidence, physical-eligibility evidence, and deterministic replay
digests.

## Architectural invariants

The constitutional principles remain unchanged. In particular, the loading
engine owns physical truth; topology is immutable during a run; observations
are derived artifacts; routing and governance do not move packets; derived
summaries are not canonical state; packets are conserved; and artifacts carry
reproducible provenance.

## What reopens the freeze

A kernel-semantic change is any change that can alter canonical physical
evidence for the same declared run. This includes changes to:

- packet movement eligibility or free-flow/backward-wave timing;
- sending or receiving recurrences;
- sending or receiving capacity-credit accounting;
- storage or vacancy accounting and the queue ontology;
- FIFO-prefix selection;
- node requests, allocation outcomes, or priority cadence;
- canonical event meanings or event order;
- packet creation, conservation, identity, or completion;
- cumulative-count derivation;
- deterministic replay semantics.

Any such proposal reopens the freeze. Reopening requires an explicit reason,
a read-only first-divergence audit against the frozen artifacts, an isolated
semantic-change commit, updated focused regressions, regeneration and review of
every affected manifest artifact, reruns of relevant external comparisons and
the full suite, a documented claim-impact decision, and a new freeze version.
Parameters or reference data must not be tuned to conceal a divergence.

A genuine inconsistency in the frozen evidence also reopens the boundary, even
if discovered during otherwise non-semantic work.

## Changes that do not reopen the freeze

The following are non-semantic only when canonical evidence remains
byte-equivalent or equivalently identical under its declared deterministic
serialization:

- refactoring and performance optimisation;
- visualisation, presentation, logging, diagnostics, and observability;
- topology or network importers and adapters;
- experiment orchestration and reproducibility tooling;
- new routing authorities and route-choice policies;
- observation policies;
- behaviour or governance modules that issue decisions or constraints but do
  not directly move, create, destroy, reorder, or reinterpret packets.

Future work may add adapters, networks, experiments, diagnostics, performance
improvements, routing policies, observability, behaviour, governance, and
presentation layers without reopening this freeze, provided the canonical
loading semantics above do not change.

## Review and tag procedure

After reviewing both freeze commits, the recommended local annotated-tag
command is:

```bash
git tag -a loading-kernel-v1.0.0 -m "Freeze validated Urban Cybernetics base loading kernel v1"
```

Creating or pushing that tag is outside this task until explicitly authorized.
