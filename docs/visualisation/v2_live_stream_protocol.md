# V2 live stream protocol

`GET /api/v2/runs/{run_id}/stream?after={message_id}` is an SSE stream of
validated `LiveMessage` objects. Each message has the V2 control-contract
version, monotonically increasing message ID, run ID, UTC timestamp, lifecycle
state, declared message type, and typed-by-message payload.

Declared message types are lifecycle transition, setup progress, tick batch
sealed, canonical event range appended, checkpoint sealed, progress, validation
progress, warning, and terminal result. Progress may include physical tick,
simulation seconds, wall time, packet counts, canonical event count, and
active-frontier metrics.

Every message is appended to `progress.jsonl` before publication. Reconnection
can request messages after the last known ID. SSE keepalives contain no
scientific evidence. Transient messages are never the only copy of canonical
events: event chunks and checkpoints are already durable when their notification
is sent.

Skipped browser frames and tab throttling cannot skip engine events. The client
recovers by querying canonical event ranges and an exact replay state. Duplicate
progress messages do not enter scientific replay because canonical sequence
numbers, not stream message IDs, identify physical evidence.

Viewer playback rate and viewer pause are local presentation state. Engine pause
is a command followed by a lifecycle acknowledgement. Follow-live selects the
latest sealed tick; scrubbing requests exact evidence for an earlier tick while
Python may continue running.
