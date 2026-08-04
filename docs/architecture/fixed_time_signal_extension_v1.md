# Fixed-time signal extension v1

## Boundary and architecture

`fixed-time-signal-extension-v1` is an opt-in control layer above
`loading-kernel-v1.0.1`. It does not modify the frozen loader, movement
allocator, topology records, physical event schema, cumulative counts, or
replay code.

`FixedTimeSignalPlanEvaluator` binds a resolved baseline plan to immutable
`Node.junction_spec.movement_specs`. A separate `SignalOverrideStore` resolves
accepted runtime interventions without mutating that plan. For each requested
controlled movement, `FixedTimeSignalControlMixin` evaluates the baseline,
resolves applicable overrides, derives effective Boolean permission, and
replaces only the `open_signal_group_ids` field of the frozen
`JunctionAllocationInput`. The chain is therefore:

```text
resolved baseline -> override resolution -> effective permission
                  -> existing allocator signal gate
```

The existing `GeneralMovementAllocator` remains the signal-gate enforcement
point. It still applies sending and receiving supply, FIFO, movement
declaration, governance closures, conflict resources, lane-group resources,
and its deterministic selection rule before loading may emit ordinary link or
queue events.

`FixedTimeSignalLoadingEngine` is the standard opt-in shell. It selects the
existing general movement allocator unless the caller injects another
gate-capable allocator. The mixin can also be placed above an extension shell
that already supplies such an allocator. Focused tests exercise this with the
executable-routing shell and the explicit lane-group queue-partition shell;
there is intentionally no matrix of combined production subclasses.

## Resolved schema and compiler boundary

The executable schema is `uc.resolved-fixed-time-signal-plan.v1`. A plan has
stable schema and extension versions, an ordered tuple of controllers, stable
provenance references, optional immutable metadata, a semantic hash, and a
complete configuration hash.

Each `FixedTimeControllerPlan` declares:

- a globally unique, stable controller ID;
- one immutable topology node ID;
- a positive integer cycle length in loading ticks;
- an integer offset, normalized to `[0, cycle_ticks)`;
- an ordered, non-empty tuple of stages;
- a non-empty, duplicate-free tuple of explicitly controlled movement IDs;
- optional field-level resolved provenance records.

Each `FixedTimeStage` has a globally unique, stable stage ID, a positive
integer duration, a duplicate-free set-like tuple of permitted controlled
movement IDs, and optional classification and metadata. An empty permitted set
is a clearance/all-red stage.

`ResolvedValueProvenance` lets a later compiler label a resolved field as
`observed`, `inferred`, `defaulted`, or `overridden`, with a stable source
reference and metadata. The executor does not infer values from these labels.
Required executable values must already be present and correctly typed.
Missing, `null`, malformed, unresolved, or unknown fields are rejected with
`FixedTimePlanValidationError` diagnostics.

The future provenance-aware network compiler should emit this resolved schema,
not an OSM-shaped intermediate record. In particular, it must:

1. assign stable controller, stage, node, movement, signal-group, and source
   identifiers;
2. resolve cycle, offset, stage order, every duration, explicit movement
   ownership, and stage permission sets directly in the universal integer-tick
   domain;
3. attach field-level resolution provenance without leaving executable fields
   unknown;
4. ensure every controlled topology movement has an existing `signal_group_id`;
5. make all movements sharing a signal group belong to one controller and have
   identical permission in every stage;
6. serialize deterministically and preserve or verify the supplied semantic
   and configuration hashes.

This extension deliberately performs no OSM parsing, observation matching,
inference, or default selection. Runtime operator overrides are separate
artifacts and must not be compiled into the immutable baseline. A future
compiler may emit scheduled control programmes as a distinct input, but not
rewrite operator interventions into the resolved plan.

## Validation and ownership rules

Construction and topology binding reject:

- unsupported schema or extension versions;
- empty or duplicate stable IDs;
- Boolean/non-integer cycles, offsets, ticks, or durations;
- non-positive cycles or stage durations;
- stage durations whose sum differs from the declared cycle;
- stage references outside the controller's explicit movement set;
- duplicate movement ownership across controllers;
- unknown nodes or movements, or movements attached to a different node;
- controlled movements without a frozen-topology `signal_group_id`;
- a signal group shared with an uncontrolled movement, across controllers, or
  by same-controller movements whose stage permissions differ;
- a provider rebound to a different topology signal binding;
- an allocator that does not consume the existing junction signal-gate input.

Fixed-time ownership is movement-explicit. Other movements at the same node
are not captured implicitly. Uncontrolled unsignalised movements keep ordinary
legacy behavior. An uncontrolled movement with a different `signal_group_id`
continues to use `LoadingEngine.set_signal_group_open`. Plan-controlled groups
reject that ad hoc setter with an instruction to use the audited override
store; this avoids two competing manual pathways. The signal-group isolation
rule prevents fixed-time or override state from changing an uncontrolled
movement.

## Manual override schema and resolution

`uc.fixed-time-signal-override.v1` defines immutable force and withdrawal
commands. A command includes a stable override ID, controller or signal-group
target, issuing actor, issue and effective ticks, optional exclusive expiry
tick, non-negative priority and target-local version, reason code, metadata,
and either `force_open`, `force_closed`, or `clear`. A clear names the accepted
force IDs it withdraws, must have the same target, is permanent from its
effective tick, and cannot itself expire.

`SignalOverrideStore` validates commands against the plan-bound controller and
signal-group IDs and appends a receipt for every structurally valid submission.
Receipts contain a deterministic sequence and receipt ID, recorded tick,
submitted command/hash, accepted or rejected disposition, exact reason, and a
`participates_in_resolution` marker. Duplicate IDs, unknown targets,
target-local duplicate versions, receipt-before-issue, invalid clear
references, and submissions/effective times after an optional terminal tick
are rejected. Schema-malformed payloads fail before store admission because
they do not constitute an immutable command. Rejected receipts remain in
history and never participate. Snapshot reconstruction replays every receipt
and verifies command, receipt, disposition, participation, and store hashes.

At universal tick `t`, accepted commands participate only when their receipt,
issue, and effective ticks are no later than `t`. Force expiry is exclusive:
`t < expiry_tick`. Applicable clears suppress their explicitly named forces.
Resolution precedence is:

1. signal-group-specific forces over controller-wide forces;
2. greater declared priority within the selected scope;
3. greater target-local version.

Versions are unique per exact target. Consequently two commands cannot share
equal priority and version at that target: the later submission is explicitly
rejected as `duplicate_target_version`, including contradictory open/closed
commands. Receipt insertion order never breaks an execution tie. When no force
survives temporal filtering and clears, permission returns to the baseline.

## Exact timing semantics

For loading tick `t` and normalized controller offset `o`:

```text
cycle_position = (t - o) mod cycle_ticks
```

Python's non-negative modulo result is used, so the position is always in
`[0, cycle_ticks)`. Starting at position zero, ordered stage durations form
contiguous, half-open intervals `[start, end)`. The unique interval containing
`cycle_position` is active. A controlled movement is open exactly when its ID
is listed in that stage; all other movements owned by that controller are
closed. A movement may be listed in more than one stage.

There is one universal simulation tick shared by demand, loading, routing,
signals, canonical events, evidence, replay, visualisation, and future compiler
outputs. State is initialized at tick 0. Demand and initial link-entry events
may exist at tick 0, and signal/override queries use tick 0 directly. The
frozen `LoadingEngine.step()` increments `current_tick` before its coupled
physical phases, so the first allocation is at universal tick 1; no signal
translation or second clock exists.

Tick-0 allocation was investigated but is not implemented. The frozen step
contains the tick increment, cumulative-count extension, parity sending and
receiving carry preparation, pending-demand instantiation, completion
discovery, candidate and receiving construction, allocation, FIFO execution,
receiving carry finalization, and queue enrollment in one method. There is no
pre-increment allocation hook. A tick-0 extension would require duplicating
that body or temporarily moving `current_tick` backward, breaking the frozen
monotonic step contract and creating a brittle special case for routing and
lane-group shells. Under the extension decision rule, tick 1 is therefore the
documented universal first-allocation convention.

At a stage boundary, the ending stage is inactive and the next is active. At a
cycle boundary, position returns to zero. For example, a `[0,2)`, `[2,3)`,
`[3,5)`, `[5,6)` plan selects the stages at positions `0-1`, `2`, `3-4`, and
`5`, then repeats the first stage at position `0` on tick 6 when offset is
zero. A positive offset shifts this pattern without changing lengths or order.

## Queues, evidence, and replay

A baseline or forced red gate rejects the ordinary transfer request with the existing
`signal_gate_closed` reason. The frozen loader records the normal queue entry,
and the packet remains physically stored on its upstream link. A stage change
does not release it directly. On a later step, the same sending, FIFO,
receiving, governance, resource, and allocation checks must approve the queue
head before the loader emits the existing queue exit, link exit, and link
entry events. Baseline or forced green is therefore necessary but never
sufficient.

`FixedTimeSignalPlanEvaluator.evaluate(movement_id, tick)` is the stateless
audit query. For a controlled movement it returns controller and stage IDs,
the stage's half-open cycle-position bounds, cycle position, movement ID,
baseline Boolean result, signal group, immutable plan hash, and the bound
plan/configuration/topology hash. It returns `None` for an uncontrolled
movement. `signal_gate_state()` additionally applies the override store without
persisting evidence.

The loading mixin keeps a separate, extension-only evidence tuple. It appends
one record per controlled movement actually requested in an allocation input,
with the packet IDs covered by that evaluation. Each record contains universal
tick, controller/stage/cycle state, movement and signal group, baseline
permission, considered and cleared override IDs, selected override/action and
scope, effective permission, immutable plan and topology-binding hashes, and
override-store config/history hashes. It emits nothing for idle controllers or
unevaluated movements, and direct queries do not persist records.
`fixed_time_signal_evidence_hash` fingerprints this request-linked ledger
separately from the canonical physical event log.

Exact replay inputs are immutable topology, resolved plan, fixed-time config,
the complete override receipt history, ordinary loading config/demand, and any
other injected extension inputs. Those inputs reconstruct every baseline,
override resolution, and effective gate decision from the universal tick.
Exact reruns reproduce signal evidence, queues/departures, the canonical event
log, and conservation reports.

The deterministic fixture is
`fixtures/fixed_time_signals/v1/alternating_plan_v1.json`. It covers alternating
A and B movement service, two all-red clearances, a nonzero-offset query,
boundary ticks, B queued through red and receiving-blocked green, normal B
release on a later green tick, an uncontrolled movement, exact cycle repeat,
the tick-0-state/tick-1-allocation convention, conservation, and replay.

## Limitations and manuscript wording

V1 is resolved, fixed-time, deterministic, integer-tick, and Boolean. It does
not represent amber-driver response, actuated/adaptive control, stochastic
failures, priority calls, coordination optimization, compiler inference, or
OSM provenance extraction. The existing topology must already expose suitable
signal-group IDs. Request-linked evidence is held in memory; no persistent
evidence artifact format is introduced. There is no new canonical event type.
Overrides do not hold/advance stages, retime cycles, change splits, replace
plans, actuate control, model emergency vehicles, flash signals, or optimize
controllers. The optional store terminal tick models a run boundary; fixed-time
controllers themselves have no independent terminal lifecycle in v1.

Suggested manuscript wording:

> A versioned resolved fixed-time plan assigns explicit topology movements to
> controllers and ordered integer-tick stages. At loading tick t, signal
> baseline permission is reconstructed as a deterministic Boolean function of the
> normalized cycle position `(t - offset) mod cycle`. Stage intervals are
> contiguous and half-open. Accepted runtime overrides may force that Boolean
> open or closed without mutating the baseline plan. Effective signal
> permission is only one necessary movement
> condition: the frozen loading allocator retains authority over sending and
> receiving supply, FIFO, governance, conflicts, lane-group resources, and
> packet realization. Red-held packets remain in their ordinary upstream
> queues and can depart on a later green only through the normal allocator.

Do not describe the signal controller or override issuer as moving packets,
guaranteeing departures, changing queue order, or creating physical packet
states.
