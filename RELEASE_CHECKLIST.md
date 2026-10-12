# Release checklist

This is a gate, not a record claiming every item already passed. Record commands, environment, artifact hashes and actual outcomes for the exact release.

## 1. Freeze scope and version

- Set `release-version.json` once; it is the source for runtime, Windows metadata, artifact names and release manifests. Do not independently hardcode a new runtime version.
- Update CHANGELOG with date, changes, limitations and migration notes; preserve historical entries.
- Keep README, architecture, security scope and site claims consistent with implemented behavior.
- Re-run the complete gate after every change; source-only success is not packaged or public-download QA.

## 2. Verify source and release tooling

```powershell
python -m unittest -v test_nevision_win.py
python -m unittest -v test_profile_identity.py
python -m unittest -v test_privacy_defaults.py
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
- Run `tools/cookie_integration.py` on the extracted core: require an allowing control profile and a blocking privacy-default profile on two disposable HTTPS sites.
- Run `tools/proxy_integration.py` and `tools/launcher_integration.py`; require loopback URL requests to traverse HTTP/SOCKS5 proxies, no DIRECT fallback for unavailable proxies, and exact strict flags at the real launcher boundary. These are not public-network leak tests.
- Open the diagnostic page in the selected profile and verify it explains that its host sees the request IP; no STUN or automatic fingerprint upload. Record external IP as a one-site observation, not a leak-free claim.
- Exercise clipboard cleanup without overwriting newer clipboard content; keep Windows history limitation explicit.
- Test backup/restore of a closed synthetic profile; show sensitive-data warning, validate manifest and new profile/no assigned proxy. Reject hostile/colliding archives without partial restored profiles.
- Verify safe close during queued work; second manager instance and externally opened profile behavior; restart/recovery after controlled interruption.
- Measure startup, idle CPU/memory, search and profile-list responsiveness with method, data size and environment. Do not claim a universal speed or RAM figure.
- Test upgrade in a new folder with private pre-copy of Data and rollback using the preserved old snapshot.
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
- Keep product limits visible for the exact downloadable artifact: the bundled Chromium runs new profiles; old Chrome/Edge profiles stay pinned. The proxy WebRTC UDP restriction is not a guarantee against leaks. System timezone is unchanged. Unsigned preview, sensitive backups and cross-PC encryption limits remain explicit.

## 7. Bundled-browser release gate

- For 0.8.0-preview verify `release-manifest.json` reports `native_core_bundled: true`, `fingerprint_modification: true`, and the same approved privacy-patch SHA-256 as the engine receipt and public patch file; the release tree must contain complete `Engine/Chromium` provenance, licenses and runtime files. Older releases without the patch must continue to report `false`.
- Verify new profiles use bundled Chromium and a proxy profile receives the tested WebRTC IP-handling preference; the only new identity-value changes are the two documented native CPU/memory caps. Test JavaScript/frame/worker and Device-Memory Client Hint parity in the extracted release, then record untested surfaces explicitly.
- Test an experimental legacy profile marker: its browser data remains unchanged, and launch/edit/clone actions fail clearly without falling back to stock Chrome/Edge.
- Test bundled Chromium launch, old Chrome/Edge pinning, data isolation, backup/restore, proxy assignment and update/rollback using disposable data as described above.
- Reverify the exact portable ZIP after testing, then repeat public-download hash and launch checks.

Release is complete only when the exact portable artifact, public download, checksums, release notes and public website agree and no known release-blocking P0/P1 defect remains. Keep release evidence; do not describe pending gates as passed.
