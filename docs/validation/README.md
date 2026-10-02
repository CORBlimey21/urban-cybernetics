# Reading historical validation evidence in the public repository

The reports in this directory describe their recorded validation runs. Several
are checksum-controlled and are preserved byte-for-byte; they are not inventories
of files bundled in the current public repository.

## External references and local images

The Figure 9 reports' statements that raw CSVs were "committed byte-for-byte"
describe the original development state. Those digitised CSVs were removed from
public history and must be supplied separately under their source terms; see
[THIRD_PARTY.md](../../THIRD_PARTY.md) and the
[reproduction index](../../REPRODUCIBILITY.md).

These historical reports contain image references to local products absent from
the public repository:

| Report | Referenced local images |
| --- | --- |
| [Figure 8 ensemble](m8_desouza_figure8_ensemble_v1.md) | `outputs/validation/m8_desouza_figure8_ensemble_v1/ensemble_overlay.png`, `endpoint_distributions.png` in the same directory |
| [Figure 9 equal merge](m8_desouza_figure9a_equal_comparison_v1.md) | `outputs/validation/m8_desouza_figure9a_equal_v1/overlay.png`, `difference.png` in the same directory |
| [Figure 9 asymmetric merge](m8_desouza_figure9d_asymmetric_comparison_v1.md) | `outputs/validation/m8_desouza_figure9d_asymmetric_v1/overlay.png`, `difference.png` in the same directory |

The Figure 8 images are derived UC ensemble plots. The Figure 9 overlay and
difference plots depict reconstructed published reference curves and remain
excluded from public redistribution. Their absence is intentional; no images
or scientific evidence have been regenerated for release preparation.

## Historical Git identifiers

The implementation and baseline SHAs in
[the hardening report](loading_kernel_hardening_v1_0_1.md), and the evidence and
hardening boundaries in the
[freeze contract](../architecture/loading_kernel_freeze_contract_v1.md), are
original development-history identifiers. The same applies to the candidate
parent in [the Paper 1 freeze record](../paper1/EVIDENCE_FREEZE_V1.md).
Consult [public-history provenance](../provenance/PUBLIC_HISTORY_PROVENANCE.md)
and [the commit mapping](../provenance/public-commit-map.tsv) for corresponding
public commits. Scientific file checksums and evidence identities are unchanged.
