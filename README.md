# NeAntik Win

Local-first portable Windows browser profile manager, previously named NeVision Win. Portable releases include unbranded Chromium built from pinned upstream source, so new profiles work without an installed Chrome or Edge. In the current V5 core, ordinary profiles report stock CPU, memory and timezone values; only the separate opt-in experimental mode caps exposed CPU at 4, device memory at 8 GiB and selects UTC. Existing profiles remain pinned to their original browser family; older unpinned profiles containing data require an explicit original-browser choice or a clean copy. Different engines do not reuse the same data directory. Profile isolation and partial fingerprint changes do **not** establish anonymity or independent network identities. Check the [official download page](https://nevision-win.mail782861.chatgpt.site/#download) for the current published version and its checksum.

**0.8.11-preview** refuses a profile backup containing file symlinks or
Windows reparse files instead of silently producing an incomplete ZIP. The
previous [0.8.10 release evidence](docs/RELEASE_PUBLICATION_0.8.10-preview.md)
records the exact public ZIP, hash, tests and open gates. Browser-saved
passwords, cookies and sessions may require new sign-in under another Windows
account or on another PC; proxy-vault passwords are not included in backups.
The bundled Chromium engine and profile format are unchanged. Ordinary mode
does not apply the experimental CPU/RAM/UTC controls.

Version **0.8.6-preview** added an opt-in V4b native mode that requires the exact
source-built core and changes only opaque sRGB uint8 Canvas2D readbacks, keyed
per browser session and top-level site; CPU, RAM and UTC controls are partial.
Its single-host local gates passed, but other graphics paths, external network
routes and a second computer are not validated. See the
[V4b audit](docs/NATIVE_PERSONA_PROTOTYPE_AUDIT.md). Neither this mode
nor a proxy guarantees anonymity.

## Download and start

The [official download page](https://nevision-win.mail782861.chatgpt.site/#download) links to the published portable ZIP. Extract the **entire ZIP** into a writable local NTFS folder and open `NeAntikWin.exe`. Python, an installer and a separate Chrome installation are not required for new profiles. On first bundled-browser launch, NeAntik grants Windows AppContainer read/execute access to `Engine/Chromium` only; it does not change permissions on private `Data/`. The bundled browser reports its actual browser and system values.

This unsigned preview has been tested on **Windows 11 x64, build 26200**. Other Windows versions are not validated by this release. A matching checksum detects changed bytes; it does not replace an Authenticode signature or make Windows trust a publisher.

## What it does

- Separate local browser directories, persistent cookies/history and profile metadata.
- New bundled-Chromium profiles keep downloads in their own `Data/Profiles/<id>/Downloads` folder. Moving the portable folder or restoring a backup rebases only this managed path; a custom download directory chosen in Chromium is not overwritten. Previously used and installed-browser profiles keep their settings.
- New bundled-Chromium profiles also start with a blank new-tab document. This avoids loading Chromium's remote new-tab page but does **not** stop all browser background requests; see the [startup-network measurements](docs/START_PAGE_NETWORK_2026-10.md).
- An optional experimental Chromium mode caps two hardware-related fingerprint signals consistently across measured JavaScript contexts and the Device-Memory Client Hint; ordinary bundled-Chromium and installed Chrome/Edge profiles do not enable those controls.
- Groups, tags, notes, search, settings-only duplication and local activity history.
- Local proxy vault; passwords protected with Windows DPAPI for the current Windows account.
- Background browser launches with a bounded worker queue and status for externally opened profiles.
- Atomic ZIP backup and restore into a new profile, with strict archive-path validation.
- Native browser Extensions page for a closed profile; install only extensions you trust.
- New bundled-Chromium profiles block third-party cookies and sensitive location/notification/camera/microphone permissions and disable network prediction by default; old profiles and later user choices are unchanged. A two-site HTTPS control test confirms cookie behavior.
- Proxy-bound bundled Chromium blocks implicit localhost bypass and background DNS except for the proxy endpoint, disables QUIC and restricts direct WebRTC UDP. This can break local websites or calls and does not certify all-traffic routing.
- Optional [profile diagnostic page](https://nevision-win.mail782861.chatgpt.site/check.html) shows browser-visible values and, on request, the IP seen by that site. Visiting the page reveals your IP to its hosting; it is not a comprehensive leak test.
- System light/dark theme, scrollable details and keyboard shortcuts: Ctrl+N new profile, Ctrl+F search, Enter launch selected profile, Escape clear search, F5 refresh.

The portable edition provides profile isolation, local proxy assignment, encrypted local proxy credentials, backup/restore, groups, tags, notes and activity history. The experimental mode's two capped hardware values are only a partial fingerprint change; UA, graphics, fonts, screen and many other signals are not standardized. Chromium security updates require a new portable release; this bundle has no automatic updater.

Proxy diagnostics check TCP reachability, not authentication, exit IP or absence of leaks. Authenticated SOCKS5 is rejected before launch; HTTP(S) authentication is entered in the browser's own prompt. Proxy credentials are not put in process arguments.

Copied proxy passwords are cleared after 30 seconds, or on normal close, only if the clipboard still contains that password. Windows clipboard history, synchronization and copies made by other apps are not erased.

## Your data and backups

`Data/` is created beside the executable. It contains sensitive browser data, local SQLite metadata, backups and DPAPI-protected proxy secrets. Keep it private, outside source repositories, shared drives and cloud-sync folders.

Profile backup ZIPs are **not encrypted** and may contain cookies, active sessions, history, saved browser credentials and downloaded files in managed profile folders. Proxy-vault passwords are excluded and a restored profile has no proxy assigned. Caches and browser locks are excluded. Downloads can make a backup large; the existing 8 GB / 20,000-file limits apply. A backup is sensitive even if proxy passwords are absent.

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
python -m unittest discover -q
python tools\gui_regression.py
python nevision_win.py --self-test
.\tools\test-release-tools.ps1
.\tools\check-public-repo.ps1
.\build.ps1 -Clean -EngineDirectory C:\path\to\staged-source-built-Chromium
```

`release-version.json` is the single version source. The build produces a versioned portable folder, ZIP, external checksum, release manifest, dependency notices and provenance/hash inventories under `release/`. Never build over a used portable folder containing `Data/`.

The 0.8.5-preview packages the same source-built Chromium runtime as 0.8.4-preview; the browser binary is not committed to Git. Version 0.8.6-preview uses a separately reviewed [V4b patch](docs/chromium-native-persona-prototype-v4b.patch). The bundle carries `en-US`, Russian and Thai Chromium UI packs; other system languages fall back to English. Development snapshots are allowed only in local `-dev` archives. The [privacy patch](docs/CHROMIUM_PRIVACY_BASELINE.md) and [full plan](docs/MASTER_IMPLEMENTATION_PLAN.md) document exactly what changed and what remains unverified. Legacy schema-1 experimental profile metadata is retained as a blocked marker and is never sent to the browser. A clean profile clone copies no cookies or browser session data. See [bundled-browser research](docs/BUNDLED_BROWSER_RESEARCH.md), [browser comparison](docs/PRIVACY_RESEARCH_2026-10.md), [network privacy engineering](docs/NETWORK_PRIVACY_2026-10.md), [next-phase anonymity architecture](docs/ANONYMITY_ARCHITECTURE_2026-10.md) and [project roadmap](docs/PROJECT_VISION_AND_ROADMAP.md) for the scope and test gates. `tools/fingerprint_surface_audit.py` is a loopback-only developer audit; its output may expose device traits and must not be published.

The public bundled-core release uses source-built stable-branch Chromium,
not a continuous snapshot. The staging script, reviewed build-only patch and
reproducibility notes are in [CHROMIUM_SOURCE_BUILD.md](https://github.com/AffPapa/NeAntik-Win/blob/main/docs/CHROMIUM_SOURCE_BUILD.md).
The release verifier rejects a snapshot that claims the stable channel.

Source, packaged and public-download checks are distinct gates. Follow [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) for each release; source unit tests alone do not certify the downloaded ZIP.

## Documentation and publication

- [CHANGELOG.md](CHANGELOG.md) — version history.
- [ARCHITECTURE.md](ARCHITECTURE.md) — storage, concurrency and recovery.
- [SECURITY_AND_SCOPE.md](SECURITY_AND_SCOPE.md) — limits and data handling.
- [SECURITY.md](SECURITY.md) — vulnerability reporting.
- [PUBLISHING.md](PUBLISHING.md) — source publication precautions.
- [LICENSE](LICENSE) — MPL-2.0 for project-authored source.
- [docs/PROJECT_VISION_AND_ROADMAP.md](docs/PROJECT_VISION_AND_ROADMAP.md) — mission, threat model and release gates.
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) — bundled components.

Project-authored source is available under MPL-2.0. Third-party components retain their own licenses and notices; the project license does not grant trademark rights in the NeAntik name or logo. Never upload `Data/`, credentials, cookies, databases, certificates, private logs or screenshots. Publish the reviewed source export, not the parent workspace.
