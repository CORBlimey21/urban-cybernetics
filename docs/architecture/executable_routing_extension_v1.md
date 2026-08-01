# Executable routing extension v1

## Boundary and ownership

`executable-routing-extension-v1` is an opt-in shell above
`loading-kernel-v1.0.1`. It does not change any source or evidence file pinned
by the kernel freeze manifest. Legacy runs continue to construct
`LoadingEngine`; executable-routing runs explicitly construct
`ExecutableRoutingLoadingEngine`.

The extension separates three records:

- `Packet.route_intent` is the immutable declared route and remains useful as
  the original demand commodity.
- `RoutingDecisionArtifact` is the authority-produced policy record.
- `RoutingInstruction` is the authority-linked, executable packet instruction
  consumed by the loading extension.

Authorities create decision artifacts and instructions but never receive a
loading-engine reference. The loading engine alone emits queue, link, and
terminal events and remains the only owner of physical state. Instructions,
resolutions, and movement-instruction evidence are separate audit ledgers, not
physical events. Static `Node.junction_spec.movement_specs` define the
supported immutable link-to-link transitions.

## Instruction and receipt contract

An instruction carries stable instruction, packet, authority, and decision
artifact IDs; a non-negative packet-local version; issue and effective ticks;
an ordered route beginning at the packet's location when that instruction is
intended to take control; its canonical realised-route start ordinal; a
policy/reason ID; replay provenance; and the
`uc.routing-instruction.v1` schema version.
The start ordinal is zero-based over canonical `LINK_ENTRY` history.

The store is append-only. It retains accepted and rejected receipts, their
stable receipt IDs, receipt tick, canonical submitted-instruction hash, exact
disposition/reason, resolution-participation marker, and deterministic history
sequence. The linked immutable instruction supplies packet, instruction,
version, issue/effective tick, artifact, authority, and submitted payload
fields. Rejected records always have `participates_in_resolution=false`.
Snapshot reconstruction validates the record ID, hash, contiguous order,
rejection outcome, and participation marker before rebuilding resolution
indexes.

Instruction IDs are globally unique and versions are unique per packet.
Versions are packet-global, not authority-local: the packet version is the
authoritative supersession order even when different authorities issue the
records. Issue, receipt, and effective ticks decide temporal eligibility but
do not decide precedence among eligible records. A lower version received
after a higher accepted version is rejected as stale. Duplicate IDs and
duplicate packet versions are rejected explicitly. Receipt cannot predate
issue, and a later receipt cannot affect an earlier decision.

## Exact resolution rules

At a service-eligible downstream decision boundary for packet `p` at tick `t`:

1. Read accepted, resolution-participating receipts for `p` whose receipt,
   issue, and effective ticks are all no later than `t`.
2. Separate explicit instructions from the version-zero route-intent adapter
   and sort explicit instructions by descending packet-global version.
3. Examine explicit instructions in that order. For every invalid candidate,
   append an `InstructionConsideration` containing instruction/version,
   artifact, authority, `inapplicable`, and the exact failure reason. Also add
   its `(instruction_id, reason)` to the fallback chain.
4. Select the first valid explicit instruction. Lower eligible versions are
   superseded; issue time does not reorder them.
5. If no explicit instruction is valid and adapter fallback is enabled,
   validate and select the version-zero immutable-route adapter. Mark the
   selection source as `route_intent_adapter`. If fallback is disabled or the
   adapter is also invalid, record an inapplicable resolution and block.
6. Validate route position using `route_start_ordinal` and the entire canonical
   realised link-entry sequence from that ordinal through the current link.
   The instruction prefix must equal that exact realised slice. This gives a
   deterministic cursor for repeated-link and looping routes; locating a link
   by value alone is insufficient and cannot reinterpret an earlier occurrence.
7. Require every instruction link to exist and every consecutive pair to be a
   declared topology movement. Prefix mismatch, current-link mismatch, unknown
   link, and disconnected route have distinct failure codes.
8. Derive at most one next link from the unmatched instruction suffix. A route
   ending at the current link requests normal completion.
9. Submit that movement request to the unchanged sending, receiving, FIFO,
   signal, governance, conflict-resource, lane-group, and node-allocation
   machinery. An applicable instruction is not approval and guarantees no
   movement.
10. Only the normal canonical link and lifecycle events record realised
   movement. A separate `MovementInstructionEvidence` record links each
   realised link-to-link transfer to its instruction, decision artifact,
   explicit/adapter selection source, skipped-invalid chain, original-intent
   match flag, superseded instruction IDs, rejected instruction IDs, stable
   rejected receipt IDs, and physical event sequence numbers.

An instruction with `issue_tick > effective_tick` becomes available no earlier
than issue/receipt; it is never retroactive. An instruction issued in advance
with a future effective tick leaves the prior applicable version in force
until that tick. An invalid higher version remains accepted history and appears
in every relevant consideration/fallback chain, but the latest older valid
eligible instruction governs. Movement blocks only when no valid explicit
instruction or permitted valid adapter exists.

## Queues and terminal packets

A newly received instruction never moves a packet when submitted. A queued
packet remains stored on its upstream link. At a later loading decision, only
the FIFO head can leave an obsolete movement queue. The loader emits the normal
queue-exit event, asks the allocator for the newly instructed movement, and—if
physical service is denied—emits the normal queue-entry event for the new
boundary. It does not emit a link exit until ordinary allocation approves the
transfer. Packets behind an unreconciled or invalid head cannot bypass it.
The transfer request is rebuilt from the selected downstream link, so movement
identity, partial-FIFO coupling, conflict resources, frozen lane-group
resources, signal/governance gates, and receiving demand are recomputed. The
obsolete boundary queue is exited once before the new queue is entered; cache
consistency checks prohibit double membership or duplicate physical enrolment.

Selecting an instruction that ends at the current link is nonphysical. For a
queued packet, the obsolete queue is first released at a FIFO-safe loading
boundary. Completion then remains loading-owned and uses the canonical
`LINK_EXIT` followed by `COMPLETED` sequence. Receipt, authority artifacts, and
resolution never set terminal state. Cancellation remains terminal and causes
later instructions to be rejected rather than completed.

Instructions submitted after completion or cancellation are appended as
`terminal_packet` rejections and also produce non-physical inapplicability
evidence. They cannot alter the canonical terminal history.

## Replay and compatibility evidence

The deterministic inputs are topology, demand, loading configuration and
seeds, extension configuration, and the complete instruction receipt history.
`instruction_history_hash` fingerprints accepted and rejected receipts;
`executable_routing_evidence_hash` additionally fingerprints every resolution
and movement link. Replaying the fixture with those inputs must reproduce the
instruction history, resolver output, movement evidence, and canonical event
log exactly. The store's JSON-like snapshot round-trip reconstructs rejected
receipts as non-participating and fails if a disposition, payload hash, stable
record ID, or deterministic replay outcome changes.

With the compatibility adapter enabled (the extension default), packet
instantiation creates a version-zero instruction from immutable
`route_intent`, attributed to `legacy-route-intent-adapter`. The adapter does
not change the packet or physical event. Focused tests compare its physical
event log exactly with a base `LoadingEngine` run. Disabling the adapter makes
absence of an explicit instruction inapplicable. Runs that do not opt into the
extension execute the frozen loader and produce no new routing ledgers.

The deterministic fixture is
`fixtures/executable_routing/v1/deterministic_reroute_v1.json`. It realises
`O,U` under route A, applies version 1 at `U`, realises `B,T`, rejects a
post-completion instruction, passes exact conservation, and reproduces both
policy and physical evidence on rerun.
`fixtures/executable_routing/v1/queued_reroute_v1.json` changes a queued
`U->A` request to `U->B`, proves old signal/conflict/lane-group state is not
retained, waits for the new movement's conflict and lane-group resources, and
then reproduces the queue events, transfer, evidence, and conservation exactly.

## Limitations and manuscript wording

- V1 accepts complete instruction suffixes, not incremental single-turn
  patches. The route must contain the control-point link.
- A current-link terminal instruction completes only when the existing loading
  step reaches a FIFO-safe completion boundary; its exact tick follows frozen
  loading order rather than authority receipt time.
- Route-disaggregated frozen count views remain keyed by original
  `route_intent`. Executed-route analysis must use realised events joined to
  `MovementInstructionEvidence`.
- There is no compliance/refusal model, competing-authority arbitration,
  stochastic churn, adaptive signal control, mid-link diversion, or
  retroactive rerouting.
- Frozen `JunctionSpec` lane-group resources and any injected allocator remain
  authoritative, but V1 does not provide a combined shell for executable
  routing plus the separate explicit-lane-group queue-bypass extension.

Manuscript language should no longer say that a routing authority “updates
route intent” or that route intent itself is executed after departure. Use:

> Route intent is the immutable declared route. A routing authority may issue
> versioned routing-decision artifacts and executable instructions. At each
> downstream decision boundary, the loading extension deterministically
> resolves the greatest packet-global version that is both temporally eligible
> and valid against canonical realised history, auditably skipping invalid newer
> versions and using route intent only as a configured final fallback. The
> frozen physical allocator alone determines whether the requested movement is
> realised.

Any route-level count claim should state whether it groups by original route
intent or by the instruction-linked realised route.
