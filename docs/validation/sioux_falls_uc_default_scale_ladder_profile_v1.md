# Sioux Falls UC Default Scale Ladder Profile v1

This artifact profiles phase timings for the 1,000- and 5,000-packet Sioux Falls UC-default assumption-profile rungs. It does not change model semantics and does not relax validation.

## 1000 Packets

- Status: `passed`
- Failure reason: `none`
- Submitted / instantiated / completed / unresolved: `1000 / 1000 / 1000 / 0`
- Ticks / events: `19 / 6866`

| Phase | Seconds | Status | Details |
| --- | ---: | --- | --- |
| tntp_topology_loading | 0.004686 | completed | `{}` |
| physical_profile_build | 0.000346 | completed | `{}` |
| physical_profile_application | 0.000567 | completed | `{"links": 76, "nodes": 24}` |
| od_pair_selection_and_demand_manifest_creation | 0.000360 | completed | `{"declared_packets": 1000, "od_pairs": 5}` |
| route_resolution | 0.000072 | completed | `{"resolved_routes": 5}` |
| scheduled_loading_expansion | 0.000775 | completed | `{"scheduled_requests": 1000}` |
| parity_readiness_checks | 0.000318 | completed | `{"junction_passed": false, "physical_passed": true}` |
| engine_initialisation | 0.000094 | completed | `{"links": 76, "nodes": 24}` |
| initial_departure_submission | 0.103803 | completed | `{"completed": 0, "events": 1580, "instantiated": 790, "pending": 210, "submitted": 1000, "tick": 0}` |
| engine_stepping_primary | 3.164773 | completed | `{}` |
| validation_context_snapshot | 0.000053 | completed | `{"events": 6866, "links": 76, "nodes": 24, "packets": 1000}` |
| shared_projection_build | 0.565095 | completed | `{"aggregate_counts": 1520, "packet_ordinals": 4000, "route_counts": 7600, "route_travel_time_curves": 5}` |
| validation_setup_count_consistency | 0.004748 | completed | `{}` |
| validation_setup_fifo | 0.011546 | completed | `{}` |
| validation_setup_spillback | 0.039001 | completed | `{}` |
| validation_setup_commodity | 0.001997 | completed | `{}` |
| validation_setup_node | 0.000739 | completed | `{}` |
| deterministic_replay_engine_stepping | 3.283913 | completed | `{"completed_packets": 1000, "events": 6866, "ticks": 19}` |
| validation_setup_replay_compare | 0.000549 | completed | `{}` |
| artifact_serialisation | 0.000070 | completed | `{}` |

## 5000 Packets

- Status: `failed`
- Failure reason: `runtime_limit_exceeded:180.0s:deterministic_replay_engine_stepping`
- Submitted / instantiated / completed / unresolved: `5000 / 5000 / 5000 / 0`
- Ticks / events: `81 / 55650`

| Phase | Seconds | Status | Details |
| --- | ---: | --- | --- |
| tntp_topology_loading | 0.004655 | completed | `{}` |
| physical_profile_build | 0.000356 | completed | `{}` |
| physical_profile_application | 0.000556 | completed | `{"links": 76, "nodes": 24}` |
| od_pair_selection_and_demand_manifest_creation | 0.000397 | completed | `{"declared_packets": 5000, "od_pairs": 11}` |
| route_resolution | 0.000134 | completed | `{"resolved_routes": 11}` |
| scheduled_loading_expansion | 0.004060 | completed | `{"scheduled_requests": 5000}` |
| parity_readiness_checks | 0.000317 | completed | `{"junction_passed": false, "physical_passed": true}` |
| engine_initialisation | 0.000089 | completed | `{"links": 76, "nodes": 24}` |
| initial_departure_submission | 0.858011 | completed | `{"completed": 0, "events": 1642, "instantiated": 821, "pending": 4179, "submitted": 5000, "tick": 0}` |
| engine_stepping_primary | 128.743429 | completed | `{}` |
| validation_context_snapshot | 0.000239 | completed | `{"events": 55650, "links": 76, "nodes": 24, "packets": 5000}` |
| shared_projection_build | 18.664468 | completed | `{"aggregate_counts": 6232, "packet_ordinals": 31800, "route_counts": 68552, "route_travel_time_curves": 11}` |
| validation_setup_count_consistency | 0.016459 | completed | `{}` |
| validation_setup_fifo | 0.097692 | completed | `{}` |
| validation_setup_spillback | 2.611218 | completed | `{}` |
| validation_setup_commodity | 0.026726 | completed | `{}` |
| validation_setup_node | 0.006047 | completed | `{}` |
| deterministic_replay_engine_stepping | 28.969697 | timeout | `{"completed": 5000, "events": 55650, "instantiated": 5000, "pending": 0, "submitted": 5000, "tick": 81}` |

Artifact writing seconds: `0.000265`
