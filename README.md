# NeAntik Win

Local-first portable Windows browser profile manager, previously named NeVision Win. The `0.4.0-preview` edition creates isolated local profiles and launches installed stock Google Chrome or Microsoft Edge. It does not bundle a browser engine, provide a standalone browser, or alter browser fingerprint signals. Legacy experimental engine-profile records are non-runnable in this edition and their data is left intact.

## Download and start

The [official download page](https://nevision-win.mail782861.chatgpt.site/#download) is the source of published binaries. New builds use `NeAntikWin.exe`. Extract the **entire ZIP** into a writable local folder. Python and an installer are not required. Profiles use installed Google Chrome or Microsoft Edge and report their actual browser and system values.

This unsigned preview has been tested on **Windows 11 x64, build 26200**. Other Windows versions are not validated by this release. A matching checksum detects changed bytes; it does not replace an Authenticode signature or make Windows trust a publisher.

## What it does

- Separate local browser directories, persistent cookies/history and profile metadata.
- Groups, tags, notes, search, settings-only duplication and local activity history.
- Local proxy vault; passwords protected with Windows DPAPI for the current Windows account.
- Background browser launches with a bounded worker queue and status for externally opened profiles.
- Atomic ZIP backup and restore into a new profile, with strict archive-path validation.
- Native browser Extensions page for a closed profile; install only extensions you trust.
- System light/dark theme, scrollable details and keyboard shortcuts: Ctrl+N new profile, Ctrl+F search, Enter launch selected profile, Escape clear search, F5 refresh.

The downloadable edition provides profile isolation, local proxy assignment, encrypted local proxy credentials, backup/restore, groups, tags, notes and activity history. It does not include fingerprint modification. The release builder and archive verifier refuse custom browser-engine payloads.

Proxy diagnostics check TCP reachability, not authentication, exit IP or absence of leaks. Authenticated SOCKS5 is rejected before launch; HTTP(S) authentication is entered in the browser's own prompt. Proxy credentials are not put in process arguments.

Copied proxy passwords are cleared after 30 seconds, or on normal close, only if the clipboard still contains that password. Windows clipboard history, synchronization and copies made by other apps are not erased.

## Your data and backups

`Data/` is created beside the executable. It contains sensitive browser data, local SQLite metadata, backups and DPAPI-protected proxy secrets. Keep it private, outside source repositories, shared drives and cloud-sync folders.

Profile backup ZIPs are **not encrypted** and may contain cookies, active sessions, history and saved browser credentials. Proxy-vault passwords are excluded and a restored profile has no proxy assigned. Caches and browser locks are excluded. A backup is sensitive even if proxy passwords are absent.

Portable means the app runs from a folder; it does not mean all secrets can move between PCs. DPAPI and browser App-Bound Encryption can prevent saved passwords or sessions working under another Windows account, installation or computer. No cross-PC cookie/session guarantee is made.

## Update without losing your data

1. Close NeAntik / NeVision and all browser windows belonging to its profiles.
2. Make a private copy of the complete old portable folder, including `Data/`.
3. Download and verify the new ZIP; extract it into a **new** folder.
4. Copy the old `Data/` into the new folder before first launch. Keep the old folder unchanged.
5. Launch the new executable and check profiles, proxy settings and a test backup.

For rollback, close the new app and its profile browsers, then use the preserved old folder with its pre-update data snapshot. Do not assume an older browser can safely read a profile already upgraded by a newer browser.

## Build and verify from source

Use Windows x64, PowerShell and Python 3.12 in an authorized source checkout:

```powershell
python -m pip install -r requirements-build.txt
python -m unittest -v test_nevision_win.py test_profile_identity.py
python tools\gui_regression.py
python nevision_win.py --self-test
.\tools\test-release-tools.ps1
.\tools\check-public-repo.ps1
.\build.ps1 -Clean
```

`release-version.json` is the single version source. The build produces a versioned portable folder, ZIP, external checksum, release manifest, dependency notices and provenance/hash inventories under `release/`. Never build over a used portable folder containing `Data/`.

This project does not build or bundle Chromium. Every profile uses the installed stock browser; no fingerprint configuration or launch flags are created. Legacy experimental profile metadata is retained as a blocked marker and is never sent to Chrome/Edge. A clean profile clone copies no cookies or browser session data.

The source freeze checkpoint passed 44 core tests, 7 Tk checks, 13 release-tool checks and the source self-test. This is not evidence that a later artifact passed packaged or public-download QA: follow [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) for each release.

## Documentation and publication

- [CHANGELOG.md](CHANGELOG.md) — version history.
- [ARCHITECTURE.md](ARCHITECTURE.md) — storage, concurrency and recovery.
- [SECURITY_AND_SCOPE.md](SECURITY_AND_SCOPE.md) — limits and data handling.
- [SECURITY.md](SECURITY.md) — vulnerability reporting.
- [PUBLISHING.md](PUBLISHING.md) — source publication precautions.
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) — bundled components.

The owner has authorized publishing this project's source as NeAntik-Win. No open-source license has been selected for the original application code; public visibility does not itself grant reuse rights. Third-party components retain their own licenses. Never upload `Data/`, credentials, cookies, databases, certificates, private logs or screenshots. Publish the reviewed source export, not the parent workspace.
