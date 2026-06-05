**Status:** policy document.
**Scope:** defines the permitted and forbidden roles of BPR functions, static assignment outputs, and pre-migration legacy code within the framework.
**Non-scope:** does not define packet-LTM mechanics or dynamic model structure.

---

### The One Sentence Version

BPR and static assignment are provenance records and benchmark comparators. They are not physics.

---

### Permitted Uses

**Provenance record.** The pre-migration codebase and its outputs document where the project came from. Preserving them under legacy/ with clear labels is appropriate and useful.

**Aggregate flow comparator.** Static assignment equilibrium outputs (UE, SO, C-SO link flow vectors) may be compared against aggregate-flow summaries from packet-LTM runs as a sanity check on output magnitude. This comparison has a narrow validity scope: it says whether the dynamic model produces flow volumes in a similar range to the static model under similar demand. It does not validate the dynamic model's temporal structure, queue propagation, information asymmetry, or churn dynamics.

**Calibration reference.** BPR free-flow times and capacity values may inform the calibration of topology metadata. Once calibrated values are committed to the topology record as declared static capacity metadata and free-flow speed, their BPR origin is provenance; the values in the topology record stand independently.

**Smoke test.** Running static assignment on Sioux Falls or a small Cork subnetwork and verifying that it converges confirms that the tooling is installed and the benchmark data loads correctly. This is plumbing verification, not model validation.

---

### Forbidden Uses

BPR and static assignment must not:

- provide link travel times during a dynamic simulation run
- define canonical link capacity as a live model parameter
- appear as fields in canonical topology records (bpr_alpha, bpr_beta are forbidden topology fields per topology_semantics.md)
- be imported by any canonical dynamic package (loading, packets, routing, observability, governance, behaviour, validation)
- be used as the acceptance criterion for dynamic model correctness
- be named or labelled in a way that could be mistaken for dynamic model output

---

### Naming Rules

All BPR and static assignment outputs must be stored under outputs/legacy_reference/ and must carry the prefix bpr_ref_ or static_assign_ in their filenames. Example: bpr_ref_ue_link_flows.csv, static_assign_so_od_costs.csv.

These outputs must never be named link_volumes.csv, travel_times.csv, od_costs.csv, or any unqualified name shared with dynamic output namespaces.

---

### Import Restrictions

No module under src/urban_cybernetics/ may import from legacy/, bpr_reference/, or static_assignment. This restriction is enforced by invariant I12. Any import of a legacy module from a canonical package is a test failure, not a style issue.

---

### Why Static Assignment Is Not Dynamic Loading

Static assignment solves for an equilibrium flow distribution over a fixed network given a fixed OD demand matrix. It has no notion of time, queue propagation, information delay, behavioural adaptation, or packet identity. Its outputs are flow vectors, not event logs.

Packet-LTM models time-dependent loading through cumulative boundary counts, queue dynamics, node transfer mechanics, and packet lifecycle events. Its outputs are event logs from which aggregate flows can be derived.

The two models answer different questions. Comparing their aggregate flow outputs under equivalent demand is a valid but narrow check. Treating BPR as a substitute for packet-LTM mechanics, or using static equilibrium as the acceptance criterion for dynamic behaviour, confuses the questions.

---
