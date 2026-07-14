# M8 Validation Workbench v1

## Architecture

The validation workbench is a third, narrow plane beside V2 evidence and
control. `uc.validation.case.v1` contains authored claims, independent expected
evidence, metrics, tolerances, explanations, overlays, citations, and reference
asset declarations. `uc.validation.result.v1` contains Python-observed evidence,
differences, metric results, provenance, and packet-wait explanations.

The validation runner is outside the loading kernel. It resolves only declared
case IDs, constructs the sanctioned analytical fixture, lets the loading engine
own execution, folds observations from canonical events in Python, compares
them with the authored oracle, and exports an ordinary V replay bundle. The
browser never executes loading mechanics or derives expectations.

## Initial case library

- `M8-LINK-01`: exact free-flow pulse translation.
- `M8-LINK-02`: exact capacity-constrained discharge, point queue, and delay.
- `M8-LINK-03`: exact backward-vacancy lag and boundary-queue release.

Expected tables remain literal fixture data. They are duplicated deliberately
between the original external-validation tests and the workbench case contract;
neither is generated from UC projections. Baseline results under
`fixtures/visualisation/validation/` are deterministic reloadable evidence.

## Evidence semantics

| Display | Status |
| --- | --- |
| packet/link lifecycle and queue events | canonical |
| cumulative counts and realised replay state | event-derived |
| authored expected curves and release ticks | analytical/reference |
| observed-minus-expected series and metric decisions | validation output |
| whole-link queue/wave shading and animation | presentation-only rendering of a declared overlay |

The backward-wave overlay communicates direction and the declared lag interval;
it is not a continuous shock position. Anonymous interpolated packet dots remain
presentation-only. A waiting explanation is shown only when the persisted
validation result identifies its canonical, exported, or analytical sources.

## Run and persistence workflow

The browser can run one declared case or the current analytical group. A
background Python thread exposes setup, execution, comparison, persistence, and
terminal stages. Cancellation is accepted between exact ticks and writes a
partial replay result instead of deleting evidence. Browser disconnect does not
own the run.

Runtime results append beneath `outputs/visualisation/validation/runs/`. A new
pass never overwrites an earlier failure or cancellation. Each result freezes
case version, configuration hash, expected-evidence hash, code commit, metrics,
and timestamps. Optional issue/fix-commit fields are reserved in the result
contract.

Regenerate the baseline fixtures with:

```bash
.venv/bin/uc-visualisation export-validation-fixtures
```

## Reference assets

Reference declarations support citation text, section/figure/table/equation,
an allowed local asset path, a digitised-series ID, rights/provenance notes,
transformations, comparison suitability, and missing-input notes. This slice
embeds only repository-authored tables. It neither downloads nor extracts
copyrighted figures.

## Known limitations

- The three cases share one analytical execution adapter; future published
  cases must declare their own suitable mechanism rather than pretending all M8
  evidence is homogeneous.
- Run-all is limited to the current analytical group.
- Validation progress is polled locally; a separate stream is unnecessary at
  this scale.
- The point queue and vacancy supply are Python validation projections, not new
  engine state.
- The next recommended scientific case is the independently sourced one-to-one
  node case, followed by the de Souza lane-drop reproduction.
