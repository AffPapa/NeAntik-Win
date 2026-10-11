# Release checklist

This is a gate, not a record claiming every item already passed. Record commands, environment, artifact hashes and actual outcomes for the exact release.

## 1. Freeze scope and version

- Set `release-version.json` once; it is the source for runtime, Windows metadata, artifact names and release manifests. Do not independently hardcode a new runtime version.
- Update CHANGELOG with date, changes, limitations and migration notes; preserve historical entries.
- Keep README, architecture, security scope and site claims consistent with implemented behavior.
- The unpublished 0.2.0 candidate passed its initial source gate but failed packaged long-path backup. Version 0.2.1 adds seven regressions (51 core checks) and a long-path frozen self-test. Repeat the complete gate after freeze; packaged/public QA remains mandatory.

## 2. Verify source and release tooling

```powershell
python -m unittest -v test_nevision_win.py
python tools\gui_regression.py
python nevision_win.py --self-test
.\tools\test-release-tools.ps1
.\tools\check-public-repo.ps1
```

- Include Data-directory mutex, stale launch/deleted profile/proxy binding, malformed ZIP and recovery regression coverage.
- Test safe close with work in flight, duplicate clicks/queue limits, external browser locks, error dialogs and missing browser.
- Synthetic Tk tests are not a substitute for real browser and packaged UI testing.
- Inspect repository and artifact candidates for Data, passwords, tokens, cookies, private screenshots/logs and accidental credentials. Publish original source only with the owner's explicit authorization; retain `SOURCE_LICENSE_NOTICE.txt` and do not invent an open-source license or reuse rights.

## 3. Build an immutable clean candidate

```powershell
.\build.ps1 -Clean
```

- Use the build's dedicated allowlisted workspace, not a used portable installation.
- Confirm matching version in executable, JSON, folder, ZIP and manifest.
- Include runtime dependency/license notices, source provenance and file-hash inventory.
- Verify the archive with `tools\verify-release-archive.ps1`; ensure no Data, private files, links/reparse points or unexpected payloads.
- Record final ZIP size and SHA-256; retain its separate checksum. A versioned published artifact must never be silently overwritten.
- Verify manifest OS claims: tested Windows 11 x64 build 26200 only; do not label Windows 10 validated.

## 4. Test the exact packaged ZIP

- Extract to a fresh writable folder; run packaged `NeAntikWin.exe --self-test` (historical NeVision releases use `NeVisionWin.exe`).
- Launch the real GUI on Windows 11 x64 build 26200; record this environment.
- Exercise first-run/missing-browser guidance, per-user browser discovery and custom path.
- Create/edit/search/duplicate a test profile; launch Chrome/Edge, persist a harmless session/history item, close and reopen.
- Verify Ctrl+N, Ctrl+F, Enter, Escape and F5; system light/dark themes; scrolling, resizing, focus and readable error states.
- Test native Extensions action closed/open; do not install untrusted extensions.
- Test invalid/missing proxy rejection, unsupported SOCKS5 auth rejection, IPv6 formatting and clear TCP-only diagnostics. Do not claim untested authenticated proxy success.
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
- Keep product limits visible for the exact downloadable artifact: the historical stock-browser release has no fingerprint spoofing; a native release must name its actually observed surfaces and uncovered formats. TCP-only proxy diagnostics, unsigned preview, sensitive local backups and cross-PC encryption limits remain explicit.

## 7. Additional gate for the first native NeAntik release

- Do not publish the launcher-only CI artifact or a stock Chromium binary as the native release. Verify exact source/patch hashes, GN args, dependency receipt and license artifacts for the packaged engine.
- Complete the owned current-core compilation, run the authored native GoogleTests, build `content_shell` and run the relevant Blink web tests. Source apply checks are not compile or runtime proof.
- Independently run `tools/test_current_native_fingerprint.py` against the final engine with an externally recorded manifest SHA-256. Require all five fingerprint visits, eight malformed-input rejections and five WebRTC network scenarios, including positive unproxied STUN controls and request-bound unavailable-proxy error evidence. Reject an incomplete report even if its status says `passed`.
- Recheck CPU/memory/HTTP hints, Date/Intl/timezone, supported Canvas readback/export and frame/worker parity. Record unsupported P3, float16 and translucent Canvas, genuine host GPU/fonts/audio, and no undetectability guarantee.
- Real headed Windows checks must include the bundled engine, tabs/history/downloads/extensions, proxy behavior, native backup/restore identity continuity and update/rollback. Historical stock-browser results do not certify this engine.
- Reverify the engine and outer ZIP after testing, then repeat the public-download hash/launch checks. Publish a new version, not new bytes under the old 0.2.1 version.

Release is complete only when the exact portable artifact, public download, checksums, release notes and public website agree and no known release-blocking P0/P1 defect remains. Keep release evidence; do not describe pending gates as passed.
