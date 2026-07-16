# Figure 8 — stochastic route-encoded diverge replication envelope

## Technical summary

The frozen Figure 7(a) DT1 fixture was rerun as 100 stochastic Figure 8
replications. Each replication uses a local `random.Random(seed)` stream, with
ordered integer seeds 0 through 99 and 68 independent packet-route draws:
`L2` when `U[0,1)<0.75`, otherwise `L3`. The topology, physical parameters,
demand, 120 s horizon, 1 s timestep, packetisation, loading engine, and
observation rules are unchanged.

The deterministic Figure 7(a) `Gu`, `F1`, and `F2` curves lie within both the
ensemble minimum–maximum envelope and the pointwise 5th–95th percentile band
at every one of the 121 observation ticks. All 100 replications pass exact
closure, conservation, FIFO, identity, physical eligibility, and replay.
Figure 8 is therefore observationally reproduced as a stochastic envelope
around the existing deterministic centre. No kernel change, parameter tuning,
digitisation, or first-divergence audit was required.

## Ensemble findings

![Selected stochastic traces, percentile bands, means, and deterministic reference](../../outputs/validation/m8_desouza_figure8_ensemble_v1/ensemble_overlay.png)

The deterministic curve is black, the ensemble mean is coloured, the shaded
region is the Type-7 linear 5th–95th percentile band, and eleven declared
replications (`0,1,2,3,4,5,10,25,50,75,99`) are overlaid faintly.

| Endpoint at 120 s | Mean | Population SD | Minimum | P05 | Median | P95 | Maximum |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `F1` | 49.49 | 3.4914 | 38 | 43.95 | 49 | 55 | 56 |
| `F2` | 16.51 | 3.4914 | 10 | 11 | 17 | 22.05 | 28 |

The final assigned-route share to `L2` has mean `0.750147`, population SD
`0.052675`, range `0.558824–0.838235`, and 5th/95th percentiles
`0.675735/0.824265`. The complementary `L3` mean is `0.249853`. Thus the mean
route-share deviations from the declared 75:25 probabilities are
`+0.000147` and `-0.000147` respectively.

![Route-count and endpoint distributions](../../outputs/validation/m8_desouza_figure8_ensemble_v1/endpoint_distributions.png)

## Deterministic centre and mean deviation

| Series | Envelope coverage | P05–P95 coverage | Mean absolute deviation | RMSE | Maximum absolute deviation (tick) | Final signed deviation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Gu` | 121/121 | 121/121 | 0.3655 | 0.5548 | 1.81 (79) | 0.00 |
| `F1` | 121/121 | 121/121 | 0.6184 | 0.7615 | 2.01 (83) | -0.51 |
| `F2` | 121/121 | 121/121 | 0.3442 | 0.4314 | 0.89 (65) | +0.51 |

`Gu` can vary before the endpoint because strict FIFO packet ordering changes
which downstream receiving credit is encountered at the head of the queue.
Every endpoint still closes exactly at `Gu=66`, while each replication also
satisfies `Gu(t)=F1(t)+F2(t)` at every tick.

## Reproducibility and validation gates

Each CSV row preserves its integer seed, full 68-destination route sequence,
SHA-256 route-sequence digest, route totals and shares, endpoints, event count,
and every boolean validation gate. A second engine run from the same seed must
produce an identical route sequence and canonical event log. Pass counts are:

| Gate | Passed |
| --- | ---: |
| Conservation | 100/100 |
| FIFO | 100/100 |
| Packet identity/count folds | 100/100 |
| Exact cumulative closure | 100/100 |
| Physical eligibility | 100/100 |
| Seeded canonical replay | 100/100 |

Focused tests fix route hashes for seeds 0–2, distinguish adjacent seeds,
check exact closure and all gates across the complete ensemble, assert
convergence of the ensemble mean to 75:25, and require full deterministic-band
coverage.

## Machine-readable evidence and regeneration

- `data/validation/desouza_figure8_ensemble_summary_v1.json`: seed roster,
  fixture declaration, route distributions, endpoint statistics, coverage,
  deviations, validation pass counts, and every per-replication cumulative
  series and route/check record;
- `data/validation/desouza_figure8_pointwise_v1.csv`: all 121 ticks of mean,
  median, minimum, maximum, 5th/95th percentile, and deterministic values for
  all three cumulative series;
- `data/validation/desouza_figure8_replications_v1.csv`: exact route and gate
  evidence for all 100 runs;
- `scripts/run_desouza_figure8_ensemble.py`: deterministic exporter and plot
  generator;
- `tests/external_validation/test_m8_desouza_figure8.py`: focused regression
  contract.

Run `python scripts/run_desouza_figure8_ensemble.py` from the repository
environment. Reproducible PNGs are written under the ignored
`outputs/validation/m8_desouza_figure8_ensemble_v1/` directory.

## Claim boundary

This validates the seeded, independent 75:25 route-encoded extension under the
existing Figure 7(a) packet and tick conventions. It does not fit the faint
published Figure 8 traces, establish universal stochastic convergence, or
validate alternative RNG algorithms, adaptive route choice, non-unit packets,
or other timesteps. The discrepancy classification is `none observed within
the declared envelope`; the read-only audit trigger was not reached.
