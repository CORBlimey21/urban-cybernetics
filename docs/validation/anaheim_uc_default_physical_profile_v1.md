# Anaheim UC Default Physical Profile v1

Status: reproducible engineering-assumption profile, not empirical calibration.

## Identity

- Profile: `AnaheimPhysicalProfile_UC_Default_v1`
- Version: `v1`
- Profile hash: `c6557c280dd9ff7100382c8376fbebf239b6389ad6a835ea325bc1c4d984dc5c`
- Topology hash: `c958bf19209c0b7b86b8268ed9c7bdca69f2cc0ab5bda16cc569d13905514231`
- Source network SHA-256: `99933b415e9500b13907829c37a43cfa9141714fad5af279081e28e5f9356f9a`

## Source Units

- Length: `feet` in the TNTP source, converted to metres internally.
- Time: `minutes` in the TNTP source, converted to seconds internally.
- Capacity: `vehicles_per_hour` retained as the per-link capacity field.
- Parity tick: `2` seconds by default for Anaheim because the shortest feet-based free-flow time is about 3.27 seconds.
- Lane count: `1` as an engineering interpretation because the TNTP file does not provide lanes.

## Assumptions

- `topology` = `published_anaheim_tntp_v1` (source_retained): Published Anaheim TNTP topology, free-flow times, lengths, speeds, and capacities are retained.
- `length_unit` = `foot` (source_header_retained): The Anaheim source header labels network length values as feet.
- `lane_count` = `1` (topology_interpretation_assumption): The current canonical Anaheim loader fixes lane count at one because the TNTP source does not provide lanes.
- `backward_wave_speed_mps` = `5.0` (engineering_assumption_profile_not_empirical_calibration): Global engineering assumption used only to exercise the parity kernel.
- `jam_density_veh_per_km_per_lane` = `derived_per_link` (engineering_assumption_profile_not_empirical_calibration): Derived from each link's published capacity and free-flow speed plus the global backward-wave-speed assumption.
- `declared_storage_capacity_packets` = `derived_per_link` (derived_not_manual_storage): Derived from length, lane count, and jam density; no manual storage values are specified.

## Derived Metadata

- Backward wave speed: `5.0` m/s
- Jam density: triangular FD consistency, `kj = q(v + w) / (v * w)`.
- Storage: `floor(length_km * lane_count * kj)`.
- Links: `914`
- Jam density range: `137.282272` to `777.806480` veh/km/lane
- Storage range: `46` to `1355` packets

## Readiness Boundary

- Topology load: `pass`
- Demand load: `pass`
- Physical metadata: `pass`
- Movement/junction support: `fail`
- Parity initialization: `pass`
