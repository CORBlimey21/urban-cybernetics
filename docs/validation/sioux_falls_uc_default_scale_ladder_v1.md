# Sioux Falls UC Default Scale Ladder v1

Status: executable assumption-profile scale ladder evidence with replay policy
reported separately from internal validation.

This artifact records bounded Sioux Falls demand-scale runs using
`SiouxFallsPhysicalProfile_UC_Default_v1`. It is not empirical calibration and
does not claim canonical Sioux Falls validation.

## Replay Policy

- Determinism certification: exact repeated executions matched at 24, 100, and
  1,000 packets.
- 5,000-packet exact replay was attempted but not certified; it was interrupted
  during the second full engine execution after exceeding the prior 180 second
  budget, with no mismatch observed before interruption.
- Exact replay remains required through 1,000 packets.
- Larger rungs may report
  `skipped_by_policy_after_determinism_certification`; this is not a replay
  pass.
- Replay is only `passed_exact_replay` when an actual rerun occurred and
  matched.

## Runner

- Command family: `.venv/bin/python scripts/run_sioux_falls_scale_ladder.py --packets 1000 5000 10000 25000 --tick-limit 20000 --max-runtime-seconds-per-rung 300.0 --exact-replay-packet-limit 1000 --determinism-certified-packet-count 1000`
- Profile: `SiouxFallsPhysicalProfile_UC_Default_v1`
- Profile version: `v1`
- Profile hash: `5c29ec863dface7d4a8bcbe3798c93665d4edc5f67fbf222a23d3761ad6449de`
- Topology hash: `0531866e3d3594f0e67bd10877acc8d1e38266a6d059dbb4d04b096b3f362b5b`
- Full demand requested packet count: `360600`
- Full demand run attempted: `no`
- Stopped early: `yes`
- Stop reason: `10000:runtime_limit_exceeded:300.0s:shared_projection_build`

## Results Table

| Rung | Requested | Submitted | Instantiated | Completed | Unresolved | Ticks | Primary s | Projection s | Validators s | Replay s | Total s | Events | Internal validation | Replay status | Scale status | Failure reason |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| 1,000 | 1,000 | 1,000 | 1,000 | 1,000 | 0 | 19 | 0.056 | 0.577 | 0.056 | 0.054 | 0.763 | 6,866 | passed | `passed_exact_replay` | passed | none |
| 5,000 | 5,000 | 5,000 | 5,000 | 5,000 | 0 | 81 | 0.901 | 19.024 | 2.774 | n/a | 22.859 | 55,650 | passed | `skipped_by_policy_after_determinism_certification` | passed | none |
| 10,000 | 10,000 | 10,000 | 10,000 | 8,900 | 1,100 | 20,000 | 112.333 | timeout after 187.630 | not run | n/a | 300.000 | 106,674 | not run | `not_run` | failed_runtime | `runtime_limit_exceeded:300.0s:shared_projection_build` |
| 25,000 | 25,000 | not run | not run | not run | not run | not run | not run | not run | not run | n/a | n/a | not run | not run | `not_run` | not_run | stopped after 10,000 runtime failure |

## Claim Boundary

Safe claim: the 1,000-packet rung passed internal validation and exact replay.
The 5,000-packet rung passed internal validation after replay was skipped by
explicit policy. Materialised cumulative entry/exit prefix counts removed the
previous primary-stepping bottleneck. The 10,000-packet rung now reaches the
20,000 tick limit with unresolved packets, and the subsequent shared projection
build exceeded the runtime guard.

Follow-up unresolved-packet diagnostics showed the 10,000 stop is not simply an
insufficient horizon. Continuing to 50,000 ticks produced no additional events
after tick 1,000. The terminal unresolved set is 400 in-transit packets on
`L0002` plus 700 queued packets at `boundary:L0002->L0006`; downstream supply
is available, and the Stage 2 allocator rejects the active FIFO head as
`not_selected_this_tick` while rejecting the queued tail as
`upstream_fifo_blocked`.

Not safe: the 5,000-packet rung did not pass exact replay in this run. The
10,000-packet rung was not internally validated. This artifact is not empirical
calibration, canonical Sioux Falls validation, or external reference
comparison.
