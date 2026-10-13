# Fast, evidence-bound test selection

Use this matrix before each change. It reduces duplicate expensive runs; it
does **not** waive a release gate. Record source commit, ZIP/EXE/core SHA-256,
test-harness commit, topology and PASS/FAIL/NOT RUN/INCONCLUSIVE separately.
If a test or input changes, rerun the affected gate. A previous PASS on an
identical Chromium core may be referenced for unchanged core behavior, never
relabelled as a fresh run on a new GUI or network topology.

| Change | Minimum local tests | Extra release gate |
| --- | --- | --- |
| Prose or Site metadata only | Diff/link/encoding check; Site typecheck/build if Site source changes | Verify live version, URL and download SHA after deployment. No browser rebuild. |
| Manager UI without storage schema or launch-flag change | Relevant unit and GUI regression; source self-test | Clean portable build, archive verifier, packaged EXE self-test and disposable GUI/startup check. Mark manual interaction INCONCLUSIVE if automation cannot enter text. |
| Profile storage, import/export, backup or upgrade | Relevant unit/GUI tests with synthetic data; public-repo guard | Same-account old-ZIP→new-ZIP migration and rollback; packaged test of changed flow. Cross-account/PC remains NOT RUN until physically exercised. |
| Proxy/launch flags/network harness | Route unit tests and changed local fixture with positive control | Run exact packaged core through affected proxy/route scenarios. External DNS/UDP/TURN requires an independent observer; loopback PASS cannot close it. |
| Chromium source, patch or bundled core | Native patch/unit tests, stock-vs-candidate controls, fingerprint/context and compatibility checks | Full bundled-core, route, storage, startup and public-download gates on the exact ZIP. Recheck security update status from official Chromium/Chrome sources. |
| Every public portable release | Full CI, staged-source guard, clean-source build, archive verifier, packaged self-test | New immutable tag/assets; redownload and hash-check ZIP/sidecar; verify live Site matches the published asset. |

Parallelize CPU-light source checks. Run browser timing gates without a second
browser workload so their latency comparisons remain interpretable. Use
disposable profiles only; never run QA against user `Data/` or real secrets.
If a fixture fails before assertions, report INCONCLUSIVE and repair the
fixture once; do not count a tool failure as a product FAIL or PASS.
