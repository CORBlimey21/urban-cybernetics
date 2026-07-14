
Urban Cybernetics

A packet-based urban traffic simulation framework for studying how information, behaviour, and infrastructure interact in transportation systems, developed as part of ongoing research into cybernetic urban traffic systems.

The framework models traffic as a dynamic system in which physical network conditions are observed through delayed and imperfect information, interpreted by routing authorities, acted upon by travellers, and fed back into the network itself.

Core Loop

Physical State
→ Observation
→ Belief
→ Routing Decision
→ Behavioural Response
→ Physical State

Current Status

The architectural and specification phase is complete, and implementation is now
moving through focused milestones.

Defined components include:

* System ontology and ownership boundaries
* Packet semantics and conservation rules
* Loading-state architecture
* Observability and information-delay model
* Routing authority framework
* Governance and intervention model
* Behavioural adaptation model
* Reproducibility and artifact contracts
* Synthetic invariant test suite
* Pre-packet OD demand, scheduling, scaling, and benchmark loading smoke runs
* Run outcome inspection summaries

Implementation is currently focused on synthetic-network validation and
benchmark-demand execution before any real-world deployment or calibration.

Repository Structure

docs/
├── architecture/
├── specifications/
├── policies/
├── audits/
└── benchmarks/
src/
tests/

Reading Order

1. docs/architecture/core_principles.md
2. docs/architecture/system_ontology.md
3. docs/specifications/loading_state.md
4. docs/specifications/timestep_semantics.md
5. docs/specifications/invariants.md

Track shorthand:

* P = what was used and whether a run can be reproduced and audited
* D = what demand was declared, scheduled, scaled, generated, or loaded
* I = what happened in a run
* R = what claim was tested

Real-world networks, calibration, dashboards, and authority/governance analytics
are to come.

V-track local simulation workbench

The first browser-based simulation replay instrument lives in `web/` and reads
persisted, versioned run evidence through a FastAPI adapter. V2 adds a narrow,
typed control plane for sanctioned Python runs; it does not own or mutate
loading state in the browser.

```bash
.venv/bin/pip install -e '.[visualisation,dev]'
cd web && npm install && npm run build && cd ..
.venv/bin/uc-visualisation serve
```

Open <http://127.0.0.1:8000>. For split development, run the API on port 8000
and `npm run dev` from `web/`; Vite proxies `/api` locally. The workbench can
browse the V1 acceptance bundle and the bounded 100-packet Sioux Falls V2
artifact, launch declared synthetic or Sioux Falls runs, follow durable live
progress, pause/resume/cancel Python execution, seek exact checkpoints, and
inspect movement-allocation evidence. Runtime artifacts are retained under
`outputs/visualisation/runs/`.

The network panel exposes only artifact-declared visual layouts. Sioux Falls
defaults to a non-geographic published-benchmark schematic; use the layout
selector to compare it with deterministic generated or circular fallbacks.
Layout choice, pan, zoom, and label layers are presentation state and never
alter topology identity or replay evidence.

Nodes, directed links, and packets can be inspected from the canvas and
evidence panels. Packet follow highlights declared and realised paths while
remaining presentation-only; unavailable movement or supply fields are shown
as unavailable rather than inferred.

See `docs/visualisation/v2_workbench_architecture.md` for the V2 ownership
boundary and developer quick-start. V1 contracts remain documented and
loadable without migration.
