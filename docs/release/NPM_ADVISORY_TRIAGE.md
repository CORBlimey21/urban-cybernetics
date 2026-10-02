# npm advisory triage for v1.0.0

Audit date: 2026-09-19. The workbench is a local development/replay interface;
none of the affected packages is shipped as server-side production code. The
built browser bundle was tested after the lockfile update.

`npm audit fix --package-lock-only` selected versions already permitted by
`package.json`. It did not change a direct dependency range or cross a major
version. Tests, TypeScript/Vite build, and ESLint all passed afterward.

| Package/advisory | Initial severity | Dependency path and scope | Disposition |
| --- | --- | --- | --- |
| `brace-expansion` DoS advisories | High | Transitive through `eslint > minimatch` and `typescript-eslint > typescript-estree > minimatch`; lint/development only | Fixed in lockfile at 1.1.21 and 5.0.12 |
| `browserslist` memory/crash advisories | High | Transitive through `@vitejs/plugin-react > @babel/core > @babel/helper-compilation-targets`; build tooling | Fixed at 4.29.0 |
| `baseline-browser-mapping` invalid-input DoS | Moderate | Transitive dependency of `browserslist`; build metadata tooling | Fixed at 2.11.25 |
| `js-yaml` CPU advisories | High | Transitive through `eslint > @eslint/eslintrc`; lint/development only | Fixed at 4.3.2 |
| `nanoid` custom-generator loop | High | Transitive through `vite > postcss`; build tooling | Fixed at 3.3.19 |
| `postcss` source-map file-read advisory | Moderate | Transitive through `vite`; build tooling | Fixed at 8.5.28 |
| `@vitest/mocker` redirect-mock path traversal/file read, GHSA-82fw-gwwq-j7x9 | Moderate | Transitive through direct dev dependency `vitest`; test runner only | Remains at 3.2.7. The audited fix is Vitest 5.0.1, a major upgrade. Do not run untrusted test/mocking code or expose the test runner as a service. |
| `vitest` propagation of the same mocker advisory | Moderate | Direct dev dependency; test runner only | Same remaining issue, counted separately by npm; defer the major upgrade to a reviewed follow-up |

Final `npm audit --json`: zero critical, zero high, two moderate entries. Those
two entries describe one underlying test-runner advisory. They do not affect the
FastAPI runtime dependencies or the static browser bundle at runtime, but they
remain a maintenance issue rather than a claim of zero known advisories.
