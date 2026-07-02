# Sioux Falls UC Default Physical Profile v1 Run

Status: first full-topology engineering-assumption profile run.

This artifact records an execution of the complete M0-M7 parity kernel on the
full committed Sioux Falls topology using
`SiouxFallsPhysicalProfile_UC_Default_v1`. It is not empirical calibration and
does not claim canonical Sioux Falls parity.

## Profile Summary

- Profile identifier: `SiouxFallsPhysicalProfile_UC_Default_v1`
- Version: `v1`
- Profile hash:
  `5c29ec863dface7d4a8bcbe3798c93665d4edc5f67fbf222a23d3761ad6449de`
- Topology: committed `sioux_falls_tntp_v1`
- Topology size: 24 nodes, 76 directed links
- Generated timestamp: deterministic profile artifact timestamp
- Statement: engineering assumption profile, not empirical calibration

## Assumptions

- Published Sioux Falls TNTP topology is retained.
- Published free-flow times/speeds are retained.
- Published capacities are retained.
- Current one-lane Sioux Falls topology interpretation is retained.
- Global backward-wave speed is assumed as `5.0 m/s`.
- Jam density is derived per link from `kj = q(v + w) / (v * w)`.
- Storage capacity is derived per link from
  `floor(length_km * lane_count * kj)`.
- No manual storage capacities are specified.

## Derived Parameter Statistics

- Link count: 76
- Backward-wave speed: `5.0 m/s`
- Jam density min/mean/max:
  `317.9550030414347 / 675.4112206112641 / 1707.127344736605`
  vehicles/km/lane
- Storage capacity min/mean/max:
  `1023 / 4263.078947368421 / 16484` packets
- Capacity min/mean/max:
  `4823.950831 / 10247.206327210526 / 25900.20064`
  vehicles/hour/lane

## Execution

Command:

```bash
.venv/bin/python -m urban_cybernetics.canonical_validation.sioux_falls_readiness --assumption-profile --tick-limit 600 --max-pairs 12 --max-total-quantity-packets 24
```

Execution status:

- Run completed: yes
- Runtime: `0.08748783398186788` seconds
- Ticks run: 18
- OD pairs included in bounded demand slice: 7
- Scheduled/submitted/instantiated/completed packets: `24 / 24 / 24 / 24`
- Event count: 178

## Validation Results

- Physical metadata: pass
- Kernel execution: pass
- Packet conservation: pass
- Count consistency: pass
- FIFO validation: pass
- Spillback validation: pass
- Commodity validation: pass
- Node movement validation: pass
- Deterministic replay: pass

Validation status: passed.

Earlier investigation of this run exposed FIFO mismatches on `L0004` and
`L0016`. The root cause was a kernel event-ordering bug: final-link completions
were appended before same-tick approved transfers from the same upstream link,
allowing later packets whose route ended on the link to receive earlier
`LINK_EXIT` events than earlier packets that still needed a downstream transfer.
Final completions and transfers are now executed in upstream-link FIFO order for
the same sending tick, while keeping the same sending-budget accounting.

## Warnings

- `engineering_assumption_profile_not_empirical_calibration`
- `bounded_demand_slice_not_full_od_demand_validation`
- `not_external_canonical_sioux_falls_validation`
- `full_network_junction_metadata_not_reviewed:24_nodes`

## Scientific Claim Boundary

Safe claim:

UC can generate a reproducible, assumption-owned physical profile for all 76
Sioux Falls links and execute the full-topology parity kernel against a bounded
deterministic demand slice with internal packet conservation, count, FIFO,
spillback, commodity, node movement, and deterministic replay checks passing.

Not safe:

UC has not achieved canonical Sioux Falls parity. The run is not a full OD
demand validation, not empirical calibration, and not an external reference
comparison.

## Recommended Next Scientific Steps

- Add reviewed full-network junction metadata before treating Sioux Falls as a
  canonical validation benchmark.
- Seek an independent Sioux Falls packet-LTM reference or primary-source
  numerical scenario before making external validation claims.
