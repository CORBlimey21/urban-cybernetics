# Paper 1 evidence freeze v1

Freeze date: 2026-08-20  
Verified candidate parent: `cf9e9b0dba67853e48eb5920c4a66c0ba134dfb1`  
Final revision: resolve `paper1-evidence-freeze-v1^{commit}`  
Evidence manifest SHA-256: `1c4b1e5ee1cc0bb6682dd621c58a806b059bee3f3b34a34872c88095b7547a96`

Final verification passed:

- focused Paper 1 integration suite: 140 tests;
- full suite: 912 tests and 88 subtests (one dependency deprecation warning);
- frozen-kernel verifier: 101 tests, all 64 recorded files, status `passed`;
- Paper 1 evidence verifier: 10 tracked artifacts, 18 retained ignored outputs,
  and the external pinned Cork GraphML, status `passed`;
- clean-checkout representative suite: 29 tests;
- clean-checkout frozen verifier: 101 tests;
- clean-checkout Maryville, compact Boreenmanna, Cork adapter, and Cork
  100-packet fixed-horizon exact-replay regeneration: passed;
- `git diff --check`, tracked-worktree, staged-file, source-identity, and
  deterministic package/hash checks: passed.

The loading kernel and canonical event schema are unchanged. The Cork evidence
uses synthetic demand and an uncalibrated engineering physical profile. The
claim qualifications and unsupported/future-work boundaries are frozen in
`CLAIM_SUPPORT_AUDIT.md`.
