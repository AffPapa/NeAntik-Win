# Release checklist

This is a gate, not a record claiming every item already passed. Record commands, environment, artifact hashes and actual outcomes for the exact release.

## 1. Freeze scope and version

- Set `release-version.json` once; it is the source for runtime, Windows metadata, artifact names and release manifests. Do not independently hardcode a new runtime version.
- Update CHANGELOG with date, changes, limitations and migration notes; preserve historical entries.
- Keep README, architecture, security scope and site claims consistent with implemented behavior.
- After a source change, rerun affected source tests; after a runtime or packaging change, rebuild and rerun all gates tied to the new binary SHA-256. Documentation or test-harness changes require their own checks, not a duplicate expensive browser run with unchanged inputs. Before any repeated expensive gate, record the new hypothesis or changed input. Source-only success is not packaged or public-download QA.

## 2. Verify source and release tooling

```powershell
python -m unittest -v test_nevision_win.py
python -m unittest -v test_profile_identity.py
python -m unittest -v test_privacy_defaults.py
python -m unittest discover -s tools -p 'test_*integration.py' -v
python tools\gui_regression.py
python nevision_win.py --self-test
.\tools\test-release-tools.ps1
.\tools\check-public-repo.ps1
```

- Include Data-directory mutex, stale launch/deleted profile/proxy binding, malformed ZIP and recovery regression coverage.
- Test safe close with work in flight, duplicate clicks/queue limits, external browser locks, error dialogs and missing browser.
- Synthetic Tk tests are not a substitute for real browser and packaged UI testing.
- Inspect repository and artifact candidates for Data, passwords, tokens, cookies, private screenshots/logs and accidental credentials. Confirm root MPL-2.0 `LICENSE` is in source and ZIP, preserve third-party notices, and verify visual-asset provenance.

## 3. Build an immutable clean candidate

```powershell
.\build.ps1 -Clean -EngineDirectory <staged-engine-directory>
```

For a bundled-browser release, stage the pinned stable Chromium source build
per [docs/CHROMIUM_SOURCE_BUILD.md](docs/CHROMIUM_SOURCE_BUILD.md), then pass
`-EngineDirectory <staged-engine-directory>` to `build.ps1`. A continuous
snapshot may be used only for a local `-dev` archive, never a public release.

- Use the build's dedicated allowlisted workspace, not a used portable installation.
- Confirm matching version in executable, JSON, folder, ZIP and manifest.
- Include runtime dependency/license notices, source provenance and file-hash inventory.
- Verify the archive with `tools\verify-release-archive.ps1`; ensure no Data, private files, links/reparse points or unexpected payloads.
- Record final ZIP size and SHA-256; retain its separate checksum. A versioned published artifact must never be silently overwritten.
- Verify manifest OS claims: tested Windows 11 x64 build 26200 only; do not label Windows 10 validated.
- Verify Chromium source commit, build-only patch SHA-256, version, `LICENSE`,
  `credits.html` and exact runtime allowlist. A bundled archive must contain
  no PDBs, build intermediates, tests or user `Data/`.
- Reject staged and untracked Chromium source edits outside the approved
  build-compatibility patch and any explicitly approved privacy patch. For the
  0.8.17 stock candidate, require no runtime patch and an explicit
  `fingerprint_modification: false` manifest. Repeated staging of identical source/build inputs should
  produce identical file hashes, including the normalized offline credits.
- For the 0.8.17 stock candidate, verify `privacy_patch_sha256` is empty,
  `fingerprint_modification` is false and the source-built provenance matches
  Chromium 155.0.8059.79 plus the exact build-compatibility patch. Do not create
  a synthetic capability receipt or imply fingerprint modification.
- For 0.7.0, verify only en-US/ru/th Chromium UI packs are present; no size
  reduction is claimed for this release.

## 4. Test the exact packaged ZIP

- Extract to a fresh writable folder; run packaged `NeAntikWin.exe --self-test` (historical NeVision releases use `NeVisionWin.exe`).
- Launch the real GUI on Windows 11 x64 build 26200; record this environment.
- Exercise first-run/missing-browser guidance, per-user browser discovery and custom path.
- With installed-browser discovery disabled, verify a new profile selects the
  extracted `Engine/Chromium/chrome.exe`; existing Chrome/Edge profiles must
  remain pinned rather than silently migrating to Chromium.
- Create/edit/search/duplicate a test profile; launch Chrome/Edge, persist a harmless session/history item, close and reopen.
- Verify Ctrl+N, Ctrl+F, Enter, Escape and F5; system light/dark themes; scrolling, resizing, focus and readable error states.
- Test native Extensions action closed/open; do not install untrusted extensions.
- Test invalid/missing proxy rejection, unsupported SOCKS5 auth rejection, IPv6 formatting and clear TCP-only diagnostics. Do not claim untested authenticated proxy success.
- In a fresh bundled profile, verify real Chromium denies geolocation, notifications, camera and microphone and retains initial Preferences. Confirm a subsequent launch does not overwrite user changes; old profiles remain untouched.
- In a fresh bundled profile, verify `chrome://newtab` renders a blank document and the new-tab preference survives Chromium startup. Confirm existing profiles and later user choices are untouched. Record remaining background requests; a blank page is not a zero-telemetry claim.
- Run `tools/cookie_integration.py` on the extracted core: require an allowing control profile and a blocking privacy-default profile on two disposable HTTPS sites.
- When running raw `chrome.exe` tests from a fresh NTFS extraction, first give AppContainer read/execute access **only** to the disposable `Engine/Chromium` directory, as the real launcher does on first profile launch. An unprepared raw-engine failure is a test-setup failure, not a cookie/privacy result; never grant this access to `Data/`.
- For the stock 0.8.17 candidate, inspect the exact extracted core receipt and
  confirm it has no NeAntik runtime patch. Exercise the app launcher and assert
  no `--neantik-*` fingerprint override is emitted. Keep raw device-trait
  reports private; one host is not an anonymity estimate.
- Run `tools/browser_integration.py` with the extracted core: require separate cookies, localStorage, IndexedDB, Cache Storage and service-worker registrations across two disposable profiles, persistence after restart, same-account backup/restore, and a clean settings-only clone.
- Run `tools/download_integration.py` with the extracted core: require distinct synthetic files under each new profile's `Downloads`, no cross-profile copy, and a new download after portable relocation. At the packaged launcher boundary, verify Chromium receives a browser-visible absolute path without the internal `\\?\` prefix. Backup/restore must retain files and rebase only the managed path; user-selected custom locations stay untouched.
- Run `tools/proxy_integration.py` and `tools/launcher_integration.py`; require loopback URL requests to traverse HTTP/SOCKS5 proxies, no DIRECT fallback for unavailable proxies, and exact strict flags at the real launcher boundary. These are not public-network leak tests.
- Run `tools/https_proxy_integration.py` and `tools/websocket_route_integration.py` against the extracted candidate core. Require local positive controls, a working TLS HTTPS-proxy CONNECT route, WS/WSS over direct/HTTP/HTTPS/SOCKS5, and unavailable/untrusted-proxy negative controls. Record the core and ZIP SHA-256. These fixtures do not validate external DNS/UDP/IPv6.
- Run `tools/webrtc_udp_integration.py` with a self-owned private IPv4 STUN host and a known-good Chrome control. Compare receiver counts with Chromium NetLog send counts. Do not mark a test passed if the direct control's STUN request is not delivered; such a result is inconclusive even when the proxy-bound case attempts zero UDP sends. NetLog captures stay private. This local probe does not cover public STUN/TURN, IPv6, DNS or all interfaces.
- Where Ubuntu WSL QA is available, run `tools/wsl_stun_route_audit.py` against its private IPv4 address. Require a received direct STUN positive control and zero received/proxy NetLog UDP with sandbox enabled; record the separate-network-namespace result without calling it a public-network or P2 Gate pass.
- Open the diagnostic page in the selected profile and verify it explains that its host sees the request IP; no STUN or automatic fingerprint upload. Record external IP as a one-site observation, not a leak-free claim.
- Exercise clipboard cleanup without overwriting newer clipboard content; keep Windows history limitation explicit.
- Test backup/restore of a closed synthetic profile; show sensitive-data warning, validate manifest and new profile/no assigned proxy. Reject hostile/colliding archives without partial restored profiles.
- Verify safe close during queued work; second manager instance and externally opened profile behavior; restart/recovery after controlled interruption.
- Measure startup, idle CPU/memory, search and profile-list responsiveness with method, data size and environment. Do not claim a universal speed or RAM figure.
- Test upgrade in a new folder with private pre-copy of Data and rollback using the preserved old snapshot.
- Run `tools/upgrade_rollback_integration.py` with a freshly downloaded, SHA-256-verified public previous ZIP and the exact candidate ZIP. Require same-account synthetic profile/proxy/DPAPI preservation and an unchanged old snapshot after candidate writes; separately test packaged GUI and browser-session migration before claiming a complete update gate.
- Run `tools/upgrade_browser_session_integration.py` with those same two exact ZIPs. Require a persistent synthetic cookie and localStorage written by the previous bundled Chromium to be read by the candidate bundled Chromium on the same loopback origin after copying `Data/`; require the old snapshot to remain unchanged. This is one-profile, same-account evidence only: test packaged GUI update and other storage surfaces separately.
- Both upgrade scripts require explicit `--old-zip`, `--old-version`, `--old-sha256`,
  `--candidate-zip`, `--candidate-version` and `--candidate-sha256`; the storage
  script also requires `--report`, while the browser-session script accepts it.
  Use hashes measured from the exact public download and candidate, not values
  copied from an older release report.
- Run available Windows security scanning, record results and limitations; unsigned/SmartScreen warnings remain possible.

Use disposable test data outside the shipping folder. Re-check the final ZIP after testing; never publish a test-used Data directory.

## 5. Publish and verify downloads

- Publish only the authorized binary ZIP, checksum and required public release metadata via the approved hosting route.
- Download the public ZIP again, compare its SHA-256 with the locally verified candidate and check its archive contents.
- Verify public checksum and release metadata agree with the downloaded ZIP.
- Record actual public URLs, HTTP status, size and hash. A working local file or landing page is not proof of a public download.
- If hosting/permissions fail, report the blocker and retain the verified candidate; do not claim the release complete.

## 6. Update the existing public site

- Update the existing official site only after the download resolves: [NeAntik Win](https://nevision-win.mail782861.chatgpt.site/).
- Update version/date/download target/hash/size and CHANGELOG; never invent a GitHub repository or release URL.
- Verify page, download and changelog GET/HEAD behavior and UTF-8 rendering (including Cyrillic).
- Recheck desktop/mobile layout, system light/dark theme and all release links.
- Keep product limits visible for the exact downloadable artifact: stock bundled Chromium runs new profiles; old Chrome/Edge profiles stay pinned. NeAntik does not modify fingerprint values. The proxy WebRTC UDP restriction is not a guarantee against leaks. Unsigned preview, sensitive backups and cross-PC encryption limits remain explicit.

## 7. Bundled-browser release gate

- For the 0.8.17 stock preview verify `release-manifest.json` reports
  `native_core_bundled: true`, `fingerprint_modification: false`, and empty
  `privacy_patch_sha256`; the archive must contain complete engine provenance,
  licenses and runtime files. The final manifest and `build-provenance.json`
  must agree on clean source state, exact source commit and source-tree hash.
- Verify ordinary launches emit no `--neantik-*` override and use stock
  Chromium values. Test that a legacy experimental profile remains unchanged,
  is blocked before process creation and can produce a fresh settings-only copy;
  never silently launch it with another browser.
- Test bundled Chromium launch, old Chrome/Edge pinning, data isolation, backup/restore, proxy assignment and update/rollback using disposable data as described above.
- Reverify the exact portable ZIP after testing, then repeat public-download hash and launch checks.

Release is complete only when the exact portable artifact, public download, checksums, release notes and public website agree and no known release-blocking P0/P1 defect remains. Keep release evidence; do not describe pending gates as passed.
