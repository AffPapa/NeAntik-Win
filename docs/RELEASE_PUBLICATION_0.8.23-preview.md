# Publication record: 0.8.23-preview

Recorded 2026-10-15 after verifying the exact portable archive and live Site.
This is evidence for this version only; it does not transfer to later builds.

## Browser source and artifact

- Public source commit: `562c0291807989b01ecc1fe825e4cd2441969aee` (`main`, clean at build).
- Immutable annotated tag: `v0.8.23-preview`, peeled commit `562c0291807989b01ecc1fe825e4cd2441969aee`.
- Portable ZIP: 262,388,304 bytes; SHA-256 `f2a3e6829d8a904d3454586d967c4d150f8c1608f3d940785ee18129271249ca`.
- Packaged `NeAntikWin.exe`: SHA-256 `7679a758253dd1a5a31850329add50415c31964d53f67b6fdd816e4784570783`.
- Bundled `chrome.exe`: Chromium `155.0.8059.79`, SHA-256 `7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`.
- Build provenance source tree SHA-256: `09d15326f756e34a37cb0a3906e7dc432f3f385cbc12ad527f0e770609f8fac0`; source state `clean`.
- Release manifest: `native_core_bundled: true`, `fingerprint_modification: false`, `signature_status: NotSigned`.

## Checks

- Relevant Python suite: `python -m unittest -v test_proxy_diagnostics test_nevision_win.py test_profile_identity.py test_privacy_defaults.py tools.test_public_source_export tools.test_public_second_host_gate tools.test_upgrade_rollback_integration` — 164 tests, 4 platform skips, PASS.
- Additional Windows storage recovery gate on the same unchanged application source commit: `python -m unittest -v tools.test_two_manager_process_gate` — 4/4 PASS, including synthetic process crash after restore publication, startup recovery, and preservation of the source profile. This is source-level integration evidence, not a manual packaged-EXE restore test.
- `tools/test-release-tools.ps1` — 58 checks, PASS.
- `tools/check-public-repo.ps1` — 221 files, PASS.
- `tools/verify-release-archive.ps1` on local and newly downloaded public ZIP — PASS, 1,066 files.
- Exact packaged EXE `--self-test` — exit 0, PASS.
- Post-publication route checks against the exact packaged `chrome.exe` from
  the verified ZIP (hash above), using only disposable loopback fixtures —
  HTTPS proxy **10/10 cases PASS** and proxy loss/recovery **10/10 checks
  PASS**. This is additional exact-engine evidence, not a rebuilt application
  or public-network observation; details are in
  [`ROUTE_MATRIX_2026-10.md`](ROUTE_MATRIX_2026-10.md).
- GitHub Windows CI run `38728938907` for the exact source commit — completed, success.
- Manual GUI startup from the exact package — window rendered, PASS. Profile-form typing did not register through the UI automation helper after one refreshed retry; that interaction is **INCONCLUSIVE**, not a product failure. No real profile, proxy credential or browser session was used.

## GitHub publication

- Public Release: <https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.23-preview>
- Uploaded assets: portable ZIP, `.zip.sha256` sidecar, and build manifest.
- Public ZIP redownload size and SHA-256 match the local artifact exactly. GitHub asset API digest and downloaded public sidecar also match the same SHA-256.
- The downloaded public ZIP independently passes the release archive verifier.

## Site publication

- Public Site: <https://nevision-win.mail782861.chatgpt.site/>
- Sites version `57`, deployment status `succeeded`.
- Site source commit: `9fac3232cb209aa81967e448fc067c07d2fc66f1` (distinct from the browser's binary source commit above).
- Site package built from that pushed source commit; its packaged `dist/.openai/hosting.json` retains the existing Site identity and its packaged `dist/client/release.json` points to the verified GitHub ZIP.
- Live `/`, `/release.json`, and `/CHANGELOG.md`: HTTP 200. Live version/source commit/archive filename/size/SHA match the GitHub Release. Public ZIP HEAD: HTTP 200, `Content-Length: 262388304`.

## Limits not closed by this release

The proxy diagnostic covers protocol-stage responses on synthetic local fixtures; it does not establish that an external proxy forwards browser traffic. External proxy/CONNECT behavior, DNS/IPv6/WebRTC/UDP/TURN observations, a second Windows machine, Windows 10/ARM64 compatibility, and physical keyboard/screen-reader behavior remain unverified. The browser does not modify browser/device fingerprints and this release does not claim anonymity.
