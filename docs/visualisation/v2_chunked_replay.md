# V2 chunked replay and checkpoint semantics

## Canonical storage

Canonical events remain the physical history. The orchestrator seals one or
more contiguous same-order event batches into versioned `EventChunk` JSON files.
Each chunk records exact sequence/tick bounds and a content SHA-256. Chunks are
immutable and retrieved lazily by sequence range. Same-tick order is the
original sequence-number order; chunking never sorts or repairs evidence.

## Checkpoints

`ReplayCheckpoint` stores a versioned Python event-derived `VReplayState`, its
checkpoint index, source-event hash, tick, and applied canonical sequence.
Checkpoints are periodic disposable accelerators and are also sealed at the
terminal tick. They are not canonical state and cannot replace event history.

Exact seeking chooses the nearest checkpoint at or before the target and folds
only subsequent canonical events. If no checkpoint exists, Python folds from
tick zero. Packets instantiated after a checkpoint enter as
`not_yet_observed`; their identities are not manufactured in the checkpoint.

Tests prove that:

- canonical sequence is contiguous across every chunk boundary;
- same-tick order is unchanged;
- every persisted checkpoint plus its continuation equals raw replay from tick zero;
- final live chunks equal the final V1-compatible event stream;
- cancelled/partial artifacts reconstruct through their last sealed evidence.

The browser receives exact Python replay state. Smooth marker movement is a
separate presentation-only interpolation and never enters checkpoint state,
scientific charts, allocation, occupancy, or packet lifecycle.

## Performance model

Topology is loaded once, event ranges are paginated, checkpoints bound seek
work, Canvas batches topology rendering, and progress messages are compact.
Runtime artifacts are directory-indexed; the browser does not rebuild the full
known event universe on each animation frame. A later binary chunk format can
be introduced behind a new schema version without changing canonical semantics.
