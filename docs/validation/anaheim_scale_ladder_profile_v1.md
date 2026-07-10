# Anaheim UC Default Scale Ladder Profile v1

Status: executable engineering-assumption scale ladder evidence.

This artifact records bounded Anaheim demand-scale runs using `AnaheimPhysicalProfile_UC_Default_v1`. It is not empirical calibration and does not claim external canonical Anaheim validation.

## Readiness

- Topology load: `pass`
- Demand load: `pass`
- Physical metadata: `pass`
- Movement/junction support: `fail`
- Parity initialization: `pass`
- Nodes: `416`
- Links: `914`
- OD pairs: `1406`
- Full demand requested packets: `104716`

## Runner

- Profile: `AnaheimPhysicalProfile_UC_Default_v1`
- Profile version: `v1`
- Profile hash: `c6557c280dd9ff7100382c8376fbebf239b6389ad6a835ea325bc1c4d984dc5c`
- Topology hash: `c958bf19209c0b7b86b8268ed9c7bdca69f2cc0ab5bda16cc569d13905514231`
- Exact replay packet limit: `1000`
- Tick duration: `2.0` seconds
- Determinism certified packet count: `1000`
- Full demand run attempted: `no`
- Stopped early: `yes`
- Stop reason: `10000:runtime_limit_exceeded:180.0s`

## Results Table

| Rung | Requested | Submitted | Instantiated | Completed | Unresolved | Ticks | Events | Primary s | Validation s | Total s | Events/s | Packets/s | Events/packet | Validation | Replay | Stop reason |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| 1000 | 1000 | 1000 | 1000 | 1000 | 0 | 531 | 30572 | 4.818 | 1.639 | 12.196 | 6345.692 | 207.565 | 30.572 | passed | passed_exact_replay | completed |
| 5000 | 5000 | 5000 | 5000 | 5000 | 0 | 3830 | 203420 | 44.993 | 72.460 | 123.782 | 4521.157 | 111.129 | 40.684 | passed | skipped_by_policy_after_determinism_certification | completed |
| 10000 | 10000 | 0 | 0 | 0 | 10000 | 0 | 0 | 0.000 | 0.000 | 180.000 | n/a | n/a | n/a | failed | timeout | runtime_limit_exceeded:180.0s |

## Claim Boundary

Safe claim: these are internal engineering-assumption Anaheim runs. `passed_exact_replay` means an actual rerun matched; `skipped_by_policy_after_determinism_certification` is not an exact replay pass.

Not safe: this is not empirical calibration, not a benchmark assignment comparison, and not a claim that Anaheim junction semantics have been externally reviewed.
