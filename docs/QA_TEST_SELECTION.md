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
| Proxy/launch flags/network harness | Route unit tests, `test_proxy_diagnostics.py` and changed local fixture with positive control | Run exact packaged core through affected proxy/route scenarios. Protocol diagnostics must never send saved credentials or a destination request. External DNS/UDP/TURN requires an independent observer; loopback PASS cannot close it. |
| Chromium source, patch or bundled core | Native patch/unit tests, stock-vs-candidate controls, fingerprint/context and compatibility checks | Full bundled-core, route, storage, startup and public-download gates on the exact ZIP. Recheck security update status from official Chromium/Chrome sources. |
| Every public portable release | Full CI, staged-source guard, clean-source build, archive verifier, packaged self-test | New immutable tag/assets; redownload and hash-check ZIP/sidecar; verify live Site matches the published asset. |

Parallelize CPU-light source checks. Run browser timing gates without a second
browser workload so their latency comparisons remain interpretable. Use
disposable profiles only; never run QA against user `Data/` or real secrets.
If a fixture fails before assertions, report INCONCLUSIVE and repair the
fixture once; do not count a tool failure as a product FAIL or PASS.

The public-ZIP second-host gate (`public-portable-second-host.yml`) is **manual
only**, not a push-time test. Supply the immutable release tag, published ZIP
SHA-256 and binary source commit. It checks the public archive and synthetic
storage on a fresh hosted Windows VM; it does not prove external routing,
fingerprint anonymity, consumer Windows compatibility or cross-account
portability. Do not dispatch it again without a changed gate or new ZIP.

Measured 2026-10-14: ordinary Windows CI took 68–71 seconds and did not
duplicate the root unittest suite. Adding more runner jobs to save under a
minute would add setup and coordination overhead. This host has 8 physical/16
logical CPUs and 31.1 GiB RAM, but only about 14.5 GiB of free commit at the
measurement; do not set native Chromium `-j16` from an idle snapshot. Retain
the measured `-j4` baseline and trial 5–6 only during a needed native build
with >8 GiB commit reserve and no concurrent browser timing test.
