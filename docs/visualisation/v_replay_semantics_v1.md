# V1 replay semantics

## Scientific replay

The backend folds canonical events exactly once in sequence-number order. It
rejects gaps, reordered events, decreasing ticks, unknown packets or links,
invalid link membership, events before instantiation, invalid FIFO queue exits,
and events after a terminal state.

For tick `t`, scientific state means the state after all canonical events whose
physical tick is less than or equal to `t`. Same-tick events retain their source
sequence. The projection tracks packet lifecycle, current link membership,
queue membership, realised link entries, cumulative link entries/exits, and run
counts. Queue membership is transfer state; it does not relocate a packet from
its upstream link.

The persisted V1 fixture contains one full state per tick. Seeking selects the
exact state for that tick; it does not replay approximately in JavaScript. Tests
rebuild each persisted tick independently from its raw canonical prefix and
assert equality. V1 does not use checkpoints, so there is no checkpoint claim.

## Playback

Play, pause, speed, stepping, and the range control change presentation position
only. Animation frames may skip a visual tick when the browser is late, but the
selected scientific state is always a complete Python projection and no event is
partially applied. Frame rate therefore cannot change state.

The event stream uses `filter` and a trailing display slice without sorting. It
never mutates or reorders its source.

## Terminal and incomplete runs

Run status is one of complete, bounded, timed out, or partial, with a required
reason. Packet status is separately one of not yet observed, in transit, queued,
completed, or cancelled. The UI computes unresolved as in-transit plus queued;
it never treats the run status as packet completion evidence. Partial and timed
out labels remain visible at run level.

## Presentation-only interpolation

Canvas activity dots are produced in `web/src/lib/presentation.ts`. They have
only screen coordinates, radius, and opacity; they do not carry packet identity,
link membership, or lifecycle fields. They are derived from an already-selected
scientific link occupancy only to make activity legible. They are never returned
to the API, persisted, shown as a canonical packet position, or consumed by a
chart or traffic calculation.
