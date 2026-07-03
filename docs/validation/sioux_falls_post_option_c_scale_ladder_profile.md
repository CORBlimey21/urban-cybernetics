# Post-Option-C Sioux Falls Scale Ladder Profile

This artifact profiles wall-clock phase timings for Sioux Falls UC-default assumption-profile rungs after the Option C unified queue/active FIFO allocator fix. It does not change model semantics and does not relax validation.

| Requested | Submitted | Instantiated | Completed | Unresolved | Ticks | Events | Setup/preload s | Primary s | Validation s | Replay s | Total s | Primary events/s | Primary packets/s | Total events/s | Total packets/s | Max RSS bytes | Validation | Replay | Failure |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| 10000 | 10000 | 10000 | 10000 | 0 | 75 | 109856 | 0.045 | 1.335 | 0.842 | 1.399 | 3.628 | 82313.339 | 7492.840 | 30281.196 | 2756.444 | 118816768 | passed | `passed_exact_replay` | none |
## 10000 Packets

- Status: `passed`
- Failure reason: `none`
- Submitted / instantiated / completed / unresolved: `10000 / 10000 / 10000 / 0`
- Ticks / events: `75 / 109856`
- Wall-clock setup / primary / validation / replay / total seconds: `0.045 / 1.335 / 0.842 / 1.399 / 3.628`
- Throughput, primary events/s / primary packets/s / total events/s / total packets/s: `82313.339 / 7492.840 / 30281.196 / 2756.444`
- Max RSS bytes: `118816768`
- Replay status: `passed_exact_replay`

| Phase | Seconds | Status | Details |
| --- | ---: | --- | --- |
| tntp_topology_loading | 0.004784 | completed | `{}` |
| physical_profile_build | 0.000358 | completed | `{}` |
| physical_profile_application | 0.000573 | completed | `{"links": 76, "nodes": 24}` |
| od_pair_selection_and_demand_manifest_creation | 0.000549 | completed | `{"declared_packets": 10000, "od_pairs": 30}` |
| route_resolution | 0.000375 | completed | `{"resolved_routes": 30}` |
| scheduled_loading_expansion | 0.008818 | completed | `{"scheduled_requests": 10000}` |
| parity_readiness_checks | 0.000330 | completed | `{"junction_passed": false, "physical_passed": true}` |
| engine_initialisation | 0.000112 | completed | `{"links": 76, "nodes": 24}` |
| initial_departure_submission | 0.029123 | completed | `{"completed": 0, "events": 2606, "instantiated": 1303, "pending": 8697, "submitted": 10000, "tick": 0}` |
| engine_stepping_primary | 1.334608 | completed | `{}` |
| validation_setup_packet_conservation | 0.000099 | completed | `{}` |
| validation_context_snapshot | 0.000603 | completed | `{"events": 109856, "links": 76, "nodes": 24, "packets": 10000}` |
| shared_projection_build | 0.404278 | completed | `{"aggregate_counts": 5776, "packet_ordinals": 72600, "route_counts": 173280, "route_travel_time_curves": 30}` |
| validation_setup_count_consistency | 0.056079 | completed | `{}` |
| validation_setup_fifo | 0.197289 | completed | `{}` |
| validation_setup_spillback | 0.135929 | completed | `{}` |
| validation_setup_commodity | 0.034601 | completed | `{}` |
| validation_setup_node | 0.013100 | completed | `{}` |
| deterministic_replay_engine_stepping | 1.388983 | completed | `{"completed_packets": 10000, "events": 109856, "ticks": 75}` |
| validation_setup_replay_compare | 0.009568 | completed | `{}` |
| artifact_serialisation | 0.000080 | completed | `{}` |

| 25000 | 25000 | 25000 | 25000 | 0 | 131 | 230086 | 0.102 | 3.297 | 2.368 | n/a | 5.784 | 69782.483 | 7582.217 | 39782.174 | 4322.533 | 240713728 | passed | `skipped_by_policy_after_determinism_certification` | none |
## 25000 Packets

- Status: `passed`
- Failure reason: `none`
- Submitted / instantiated / completed / unresolved: `25000 / 25000 / 25000 / 0`
- Ticks / events: `131 / 230086`
- Wall-clock setup / primary / validation / replay / total seconds: `0.102 / 3.297 / 2.368 / n/a / 5.784`
- Throughput, primary events/s / primary packets/s / total events/s / total packets/s: `69782.483 / 7582.217 / 39782.174 / 4322.533`
- Max RSS bytes: `240713728`
- Replay status: `skipped_by_policy_after_determinism_certification`

| Phase | Seconds | Status | Details |
| --- | ---: | --- | --- |
| tntp_topology_loading | 0.004726 | completed | `{}` |
| physical_profile_build | 0.000351 | completed | `{}` |
| physical_profile_application | 0.000586 | completed | `{"links": 76, "nodes": 24}` |
| od_pair_selection_and_demand_manifest_creation | 0.000654 | completed | `{"declared_packets": 25000, "od_pairs": 76}` |
| route_resolution | 0.000847 | completed | `{"resolved_routes": 76}` |
| scheduled_loading_expansion | 0.020566 | completed | `{"scheduled_requests": 25000}` |
| parity_readiness_checks | 0.000363 | completed | `{"junction_passed": false, "physical_passed": true}` |
| engine_initialisation | 0.000107 | completed | `{"links": 76, "nodes": 24}` |
| initial_departure_submission | 0.073924 | completed | `{"completed": 0, "events": 5942, "instantiated": 2971, "pending": 22029, "submitted": 25000, "tick": 0}` |
| engine_stepping_primary | 3.297189 | completed | `{}` |
| validation_setup_packet_conservation | 0.000341 | completed | `{}` |
| validation_context_snapshot | 0.002351 | completed | `{"events": 230086, "links": 76, "nodes": 24, "packets": 25000}` |
| shared_projection_build | 1.252566 | completed | `{"aggregate_counts": 10032, "packet_ordinals": 150400, "route_counts": 762432, "route_travel_time_curves": 76}` |
| validation_setup_count_consistency | 0.102579 | completed | `{}` |
| validation_setup_fifo | 0.437384 | completed | `{}` |
| validation_setup_spillback | 0.457797 | completed | `{}` |
| validation_setup_commodity | 0.084214 | completed | `{}` |
| validation_setup_node | 0.031235 | completed | `{}` |
| artifact_serialisation | 0.000071 | completed | `{}` |

| 50000 | 50000 | 50000 | 50000 | 0 | 173 | 439984 | 0.194 | 7.804 | 6.107 | n/a | 14.141 | 56381.569 | 6407.229 | 31112.996 | 3535.696 | 480935936 | passed | `skipped_by_policy_after_determinism_certification` | none |
## 50000 Packets

- Status: `passed`
- Failure reason: `none`
- Submitted / instantiated / completed / unresolved: `50000 / 50000 / 50000 / 0`
- Ticks / events: `173 / 439984`
- Wall-clock setup / primary / validation / replay / total seconds: `0.194 / 7.804 / 6.107 / n/a / 14.141`
- Throughput, primary events/s / primary packets/s / total events/s / total packets/s: `56381.569 / 6407.229 / 31112.996 / 3535.696`
- Max RSS bytes: `480935936`
- Replay status: `skipped_by_policy_after_determinism_certification`

| Phase | Seconds | Status | Details |
| --- | ---: | --- | --- |
| tntp_topology_loading | 0.004822 | completed | `{}` |
| physical_profile_build | 0.000343 | completed | `{}` |
| physical_profile_application | 0.000556 | completed | `{"links": 76, "nodes": 24}` |
| od_pair_selection_and_demand_manifest_creation | 0.000845 | completed | `{"declared_packets": 50000, "od_pairs": 143}` |
| route_resolution | 0.001611 | completed | `{"resolved_routes": 143}` |
| scheduled_loading_expansion | 0.045066 | completed | `{"scheduled_requests": 50000}` |
| parity_readiness_checks | 0.000334 | completed | `{"junction_passed": false, "physical_passed": true}` |
| engine_initialisation | 0.000106 | completed | `{"links": 76, "nodes": 24}` |
| initial_departure_submission | 0.139869 | completed | `{"completed": 0, "events": 8560, "instantiated": 4280, "pending": 45720, "submitted": 50000, "tick": 0}` |
| engine_stepping_primary | 7.803685 | completed | `{}` |
| validation_setup_packet_conservation | 0.000558 | completed | `{}` |
| validation_context_snapshot | 0.004457 | completed | `{"events": 439984, "links": 76, "nodes": 24, "packets": 50000}` |
| shared_projection_build | 2.962119 | completed | `{"aggregate_counts": 13224, "packet_ordinals": 291000, "route_counts": 1891032, "route_travel_time_curves": 143}` |
| validation_setup_count_consistency | 0.226115 | completed | `{}` |
| validation_setup_fifo | 0.934941 | completed | `{}` |
| validation_setup_spillback | 1.736414 | completed | `{}` |
| validation_setup_commodity | 0.176264 | completed | `{}` |
| validation_setup_node | 0.066401 | completed | `{}` |
| artifact_serialisation | 0.000067 | completed | `{}` |

| 100000 | 100000 | 100000 | 100000 | 0 | 227 | 822574 | 0.375 | 16.883 | 12.471 | n/a | 29.796 | 48721.495 | 5923.053 | 27606.551 | 3356.118 | 870825984 | passed | `skipped_by_policy_after_determinism_certification` | none |
## 100000 Packets

- Status: `passed`
- Failure reason: `none`
- Submitted / instantiated / completed / unresolved: `100000 / 100000 / 100000 / 0`
- Ticks / events: `227 / 822574`
- Wall-clock setup / primary / validation / replay / total seconds: `0.375 / 16.883 / 12.471 / n/a / 29.796`
- Throughput, primary events/s / primary packets/s / total events/s / total packets/s: `48721.495 / 5923.053 / 27606.551 / 3356.118`
- Max RSS bytes: `870825984`
- Replay status: `skipped_by_policy_after_determinism_certification`

| Phase | Seconds | Status | Details |
| --- | ---: | --- | --- |
| tntp_topology_loading | 0.004726 | completed | `{}` |
| physical_profile_build | 0.000347 | completed | `{}` |
| physical_profile_application | 0.000563 | completed | `{"links": 76, "nodes": 24}` |
| od_pair_selection_and_demand_manifest_creation | 0.001096 | completed | `{"declared_packets": 100000, "od_pairs": 206}` |
| route_resolution | 0.002232 | completed | `{"resolved_routes": 206}` |
| scheduled_loading_expansion | 0.086434 | completed | `{"scheduled_requests": 100000}` |
| parity_readiness_checks | 0.000412 | completed | `{"junction_passed": false, "physical_passed": true}` |
| engine_initialisation | 0.000153 | completed | `{"links": 76, "nodes": 24}` |
| initial_departure_submission | 0.279117 | completed | `{"completed": 0, "events": 11074, "instantiated": 5537, "pending": 94463, "submitted": 100000, "tick": 0}` |
| engine_stepping_primary | 16.883185 | completed | `{}` |
| validation_setup_packet_conservation | 0.001175 | completed | `{}` |
| validation_context_snapshot | 0.010292 | completed | `{"events": 822574, "links": 76, "nodes": 24, "packets": 100000}` |
| shared_projection_build | 5.350103 | completed | `{"aggregate_counts": 17328, "packet_ordinals": 521000, "route_counts": 3569568, "route_travel_time_curves": 206}` |
| validation_setup_count_consistency | 0.427384 | completed | `{}` |
| validation_setup_fifo | 1.782908 | completed | `{}` |
| validation_setup_spillback | 4.415177 | completed | `{}` |
| validation_setup_commodity | 0.359695 | completed | `{}` |
| validation_setup_node | 0.124205 | completed | `{}` |
| artifact_serialisation | 0.000076 | completed | `{}` |

| 200000 | 200000 | 200000 | 200000 | 0 | 476 | 1562198 | 0.744 | 55.875 | 31.139 | n/a | 87.958 | 27959.000 | 3579.444 | 17760.771 | 2273.818 | 2332622848 | passed | `skipped_by_policy_after_determinism_certification` | none |
## 200000 Packets

- Status: `passed`
- Failure reason: `none`
- Submitted / instantiated / completed / unresolved: `200000 / 200000 / 200000 / 0`
- Ticks / events: `476 / 1562198`
- Wall-clock setup / primary / validation / replay / total seconds: `0.744 / 55.875 / 31.139 / n/a / 87.958`
- Throughput, primary events/s / primary packets/s / total events/s / total packets/s: `27959.000 / 3579.444 / 17760.771 / 2273.818`
- Max RSS bytes: `2332622848`
- Replay status: `skipped_by_policy_after_determinism_certification`

| Phase | Seconds | Status | Details |
| --- | ---: | --- | --- |
| tntp_topology_loading | 0.004847 | completed | `{}` |
| physical_profile_build | 0.000342 | completed | `{}` |
| physical_profile_application | 0.000585 | completed | `{"links": 76, "nodes": 24}` |
| od_pair_selection_and_demand_manifest_creation | 0.001595 | completed | `{"declared_packets": 200000, "od_pairs": 321}` |
| route_resolution | 0.003739 | completed | `{"resolved_routes": 321}` |
| scheduled_loading_expansion | 0.176803 | completed | `{"scheduled_requests": 200000}` |
| parity_readiness_checks | 0.000329 | completed | `{"junction_passed": false, "physical_passed": true}` |
| engine_initialisation | 0.000107 | completed | `{"links": 76, "nodes": 24}` |
| initial_departure_submission | 0.555708 | completed | `{"completed": 0, "events": 16448, "instantiated": 8224, "pending": 191776, "submitted": 200000, "tick": 0}` |
| engine_stepping_primary | 55.874602 | completed | `{}` |
| validation_setup_packet_conservation | 0.002458 | completed | `{}` |
| validation_context_snapshot | 0.022647 | completed | `{"events": 1562198, "links": 76, "nodes": 24, "packets": 200000}` |
| shared_projection_build | 14.459132 | completed | `{"aggregate_counts": 36252, "packet_ordinals": 966000, "route_counts": 11636892, "route_travel_time_curves": 321}` |
| validation_setup_count_consistency | 1.243230 | completed | `{}` |
| validation_setup_fifo | 3.482765 | completed | `{}` |
| validation_setup_spillback | 10.882181 | completed | `{}` |
| validation_setup_commodity | 0.798734 | completed | `{}` |
| validation_setup_node | 0.247866 | completed | `{}` |
| artifact_serialisation | 0.000097 | completed | `{}` |

| 360600 | 360600 | 266100 | 76600 | 284000 | 1958 | 981232 | 1.356 | 598.667 | 0.000 | n/a | 600.024 | 1639.027 | 127.951 | 1635.321 | 127.662 | 2332622848 | failed | `not_run` | runtime_limit_exceeded:600.0s:engine_stepping_primary |
## 360600 Packets

- Status: `failed`
- Failure reason: `runtime_limit_exceeded:600.0s:engine_stepping_primary`
- Submitted / instantiated / completed / unresolved: `360600 / 266100 / 76600 / 284000`
- Ticks / events: `1958 / 981232`
- Wall-clock setup / primary / validation / replay / total seconds: `1.356 / 598.667 / 0.000 / n/a / 600.024`
- Throughput, primary events/s / primary packets/s / total events/s / total packets/s: `1639.027 / 127.951 / 1635.321 / 127.662`
- Max RSS bytes: `2332622848`
- Replay status: `not_run`

| Phase | Seconds | Status | Details |
| --- | ---: | --- | --- |
| tntp_topology_loading | 0.004955 | completed | `{}` |
| physical_profile_build | 0.000348 | completed | `{}` |
| physical_profile_application | 0.000580 | completed | `{"links": 76, "nodes": 24}` |
| od_pair_selection_and_demand_manifest_creation | 0.002320 | completed | `{"declared_packets": 360600, "od_pairs": 528}` |
| route_resolution | 0.005952 | completed | `{"resolved_routes": 528}` |
| scheduled_loading_expansion | 0.303035 | completed | `{"scheduled_requests": 360600}` |
| parity_readiness_checks | 0.000324 | completed | `{"junction_passed": false, "physical_passed": true}` |
| engine_initialisation | 0.000116 | completed | `{"links": 76, "nodes": 24}` |
| initial_departure_submission | 1.038609 | completed | `{"completed": 0, "events": 25708, "instantiated": 12854, "pending": 347746, "submitted": 360600, "tick": 0}` |
| engine_stepping_primary | 598.667426 | timeout | `{"completed": 76600, "events": 981232, "instantiated": 266100, "pending": 94500, "submitted": 360600, "tick": 1958}` |

Artifact writing seconds: `0.000000`

## Optimization Notes

- Aggregate cumulative counts are built from indexed event increments instead of repeated full-event scans.
- Spillback queue curves and downstream receiving causes are event-indexed and remain read-only.
- Baseline validation seconds: 10k 45.398, 25k 190.378, 50k timed out at 600s in spillback validation.
- Full demand stopped in primary stepping before validation: `runtime_limit_exceeded:600.0s:engine_stepping_primary`.
