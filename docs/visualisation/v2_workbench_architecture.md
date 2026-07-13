# V2 Simulation Workbench architecture

## Outcome and ownership

V2 extends the V1 replay instrument with an artifact library and a narrow local
run-control surface. The Python loading engine remains the only executor and
owner of physical truth. No module under `urban_cybernetics.loading` imports the
visualisation package. The browser submits stable resource IDs and consumes
sealed evidence; it never creates packets, allocates movements, decides supply,
or advances physical time.

The application has two explicit planes:

- The **evidence plane** stores immutable topology, frozen provenance, canonical
  event chunks, replay checkpoints, packet metadata, movement traces,
  validation output, and a final V1-compatible bundle.
- The **control plane** validates a V2 run request, resolves a declared resource
  catalogue, owns lifecycle transitions, executes Python in a background
  thread, and acknowledges pause, resume, and cancellation commands.

The planes share FastAPI transport and a run ID but not authority. Stream
messages are progress notifications; durable artifacts are authoritative.

## Selected stack

- Python 3.13, Pydantic 2, FastAPI, and Uvicorn keep schema validation and
  scientific projections beside the existing Python evidence layer.
- A Python background-thread orchestrator lets a local run survive browser
  disconnects without adding a production job-queue dependency.
- Server-sent events provide ordered, reconnectable one-way progress with less
  protocol surface than WebSockets. Commands remain explicit HTTP POSTs.
- React 19, TypeScript, Vite, Zod, Canvas, and ECharts extend V1's maintainable
  rendering/chart stack. React owns viewer position only.

## Backend packages

- `v2_contract.py`: control, evidence, chunk, checkpoint, movement, and stream schemas.
- `catalogue.py`: stable resource IDs and strict compatibility resolution.
- `lifecycle.py`: legal run transitions.
- `orchestrator.py`: sanctioned engine construction, stepping, commands, and finalisation.
- `persistence.py`: root-confined durable registry and sealed artifact records.
- `v2_fixtures.py`: bounded Sioux Falls acceptance export.
- `server.py`: V1 compatibility plus V2 evidence/control endpoints.

The V2 server writes only beneath its backend-declared runtime root
`outputs/visualisation/runs/`. It additionally discovers the read-only committed
fixture root `fixtures/visualisation/v2/`. No endpoint accepts a filesystem path,
Python class name, import target, or shell command.

## Browser structure

The workbench keeps the network dominant. A left artifact library switches
runs without restarting the server. The main column contains live lifecycle
status, viewer transport, Canvas topology, contextual inspector, Python-derived
cumulative counts, canonical event stream, and movement evidence. Two artifacts
may be pinned for metadata/outcome compatibility inspection.

“Pause viewer” changes only replay presentation. “Pause run” sends a typed
control command and is not shown as acknowledged until Python transitions to
`paused` at a between-tick boundary. Scrubbing turns off follow-live; “Go live”
returns to the latest sealed scientific state.

## Developer quick-start

```bash
.venv/bin/pip install -e '.[visualisation,dev]'
cd web
npm install
npm run build
cd ..
.venv/bin/uc-visualisation serve
```

Open <http://127.0.0.1:8000>. For split development, run
`.venv/bin/uvicorn urban_cybernetics.visualisation.server:create_app --factory --reload`
and `npm run dev` in `web/`.

Targeted verification:

```bash
.venv/bin/python -m pytest tests/visualisation -q
cd web && npm test && npm run typecheck && npm run lint && npm run build
```

## Extension points

Resource kinds and evidence descriptors can later add authority beliefs,
observation delay, governance overlays, reference curves, parameter sweeps, and
synchronised comparison without changing engine ownership. A future process
executor can implement the same orchestrator contract if runs outgrow the local
thread model.
