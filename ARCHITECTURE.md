# Architecture — portable profile manager

## Lightweight local runtime

NeAntik is a Python 3.12/Tk desktop manager packaged as a PyInstaller onedir executable. SQLite stores local metadata. The 0.8.1-preview portable folder includes source-built unbranded Chromium in `Engine/Chromium`; new profiles prefer it and older Chrome/Edge profiles remain pinned to their browser family. Its reviewed native privacy patch caps reported CPU count and device memory; the separate build-compatibility patch and exact hashes are recorded in the engine receipt. No Electron runtime, cloud account service or web application server is required.

`release-version.json` is the single application/build version source and is bundled in the executable distribution.

```text
NeAntikWin-portable-v<version>/
  NeAntikWin.exe
  _internal/
  Engine/Chromium/                bundled browser, license and provenance
  README.md, CHANGELOG.md, SECURITY_AND_SCOPE.md, ...
  THIRD_PARTY_NOTICES.md, licenses/
  release-manifest.json, SHA256SUMS.txt, provenance metadata
  Data/                         created at runtime; never in a public ZIP
    local SQLite/settings
    browser profile directories
    backups/staging/recovery data
    Deleted/                    retained deleted profile data, not a full Trash UI
```

The external ZIP checksum verifies the complete archive; the internal inventory describes payload files. Actual build output names and the manifest are authoritative.

ZIP archives do not preserve NTFS ACLs. Before its first bundled-browser launch
in a manager session, NeAntik checks for links/junctions under `Engine/Chromium`
and grants the Windows AppContainer group read/execute access to that engine
directory only. `Data/` and backups are outside the grant. This is required for
Chromium's sandbox to load resources such as `icudtl.dat`; the sandbox is not
disabled.

## Storage, locking and lifecycle

Every profile has an independent user-data directory and metadata such as name, group, tags, notes and activity. Settings-only duplication does not clone cookies or session identity. Cookies/history/password storage is browser-owned; Windows DPAPI and browser encryption rules still apply.

A Data-directory manager mutex prevents competing manager instances from concurrently performing startup recovery and mutations against the same data. Profile operation locks serialize risky mutations and browser launches. Browser lock checks detect already-open profiles, including ones opened outside this manager. Unknown/unreadable state is surfaced instead of treated as definitely closed.

Delete and restore use journals/staging for restart recovery. Unknown malformed recovery state must fail safely. Deleted directories retained under Data are not a substitute for an independent backup or a complete recycle-bin UI.

## UI concurrency

Tk widgets remain on the UI thread. Browser launch and blocking checks run through a shared executor with **3 workers** and a maximum of **6 total running/queued operations**. Duplicate operation keys, overload and work during shutdown are rejected. Results are delivered through a queue drained by Tk approximately every 120 ms.

External browser status is refreshed approximately every 3 seconds through background work. This is a status hint; mutation-time lock checks remain authoritative. List updates reuse rows and search is debounced. Detail content scrolls independently of the two-row action area.

Normal application close stops accepting work, clears an owned clipboard secret when still current, waits for outstanding operations and then destroys the UI. A worker error can cancel close and surface its error. Closing the manager does not forcibly kill browser windows.

## Browser launch and extensions

Discovery considers an explicitly selected executable, a complete bundled Chromium runtime, standard machine paths, per-user LOCALAPPDATA installs and HKCU/HKLM App Paths registry entries for Chrome/Edge, then deduplicates results. New profiles prefer bundled Chromium unless a custom path is selected; existing profiles remain pinned to their original Chrome/Edge/Chromium family. A partial bundled engine fails rather than silently falling back to an installed browser.

Launch re-reads the profile and verifies its proxy binding before process creation. A queued launch must not create a process after profile deletion or proxy reassignment. The browser receives a profile-specific `--user-data-dir` and first-run suppression flags; secrets are never embedded in arguments.

The Extensions action uses the same profile launch path with `chrome://extensions/` or `edge://extensions/`. It is available for a closed profile; an already-open profile uses its browser's native menu. No extension marketplace, automatic extension installation or unsupported command-line extension injection is implemented.

## Proxy and secrets

Proxy host validation handles IPv4, IPv6 and IDNA hostnames and rejects URL/list/malformed host input. IPv6 endpoints use brackets. Missing assigned proxies and authenticated SOCKS5 fail before launch because Chromium-based browsers do not implement the required SOCKS5 authentication here. HTTP(S) proxy authentication remains a manual browser prompt.

Saved proxy passwords use current-user Windows DPAPI. The clipboard helper clears a copied password after 30 seconds or normal close only if the clipboard still matches; it does not remove history or synchronized copies.

The diagnostic opens a TCP connection only. It does not negotiate the proxy protocol, authenticate, prove an exit IP or guarantee no DNS/WebRTC/UDP leaks. There is no local proxy broker.

## Backups and restore

A profile must be safely closed before backup. Caches and lock files are excluded. Traversal does not follow directory symlinks/junctions (non-excluded linked directories fail backup); linked/non-regular files are skipped. The archive is first written to a unique partial file and atomically promoted.

The v1 manifest declares profile metadata and sensitivity: browser session data included, archive not encrypted, proxy credentials excluded. Existing v1 backups remain supported. Archive restore creates a new ID and no proxy assignment, using staging before committing profile metadata.

Validation applies to restored profile payloads: original/raw ZIP names, separator/path traversal, empty/dot parts, control/invalid Windows characters, trailing dot/space, device names including superscript COM/LPT variants, case-insensitive duplicates, file/directory collisions, encrypted entries, symlinks and non-regular entries. A duplicate manifest is rejected. Limits are 20,000 files and 8 GB uncompressed. Irrelevant ZIP metadata is not a promise of arbitrary archive sanitization.

ZIPs can contain cookies, history, saved sessions and browser credential stores. They are sensitive plaintext archives even though the proxy vault is excluded. DPAPI and browser App-Bound Encryption mean moving Data or a backup does not guarantee passwords/cookies/sessions work on another PC or account.

## Build and release boundary

The build copies a source allowlist into a new workspace, rejects linked inputs, pins build dependencies, prepares Windows version metadata and packages a windowed onedir app. It includes dependency licenses/runtime inventory, source commit/dirty state and source-file hashes. Versioned output is immutable; shipping Data is forbidden. Archive validation runs before final promotion.

The product is unsigned and its validated release environment is Windows 11 x64 build 26200, not a claim of validation on all Windows versions. Runtime initialization failures are surfaced as visible Windows errors when the Tk interface cannot start.

Test counts and environment evidence are recorded per version rather than treated as permanent properties of the application. The exact packaged executable and public download require the independent gates in [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## Deliberate exclusions

No fingerprint-patched browser engine, cloud sync/team service, RPA platform, authenticated SOCKS proxy broker or automatic updater is present. No anonymity/anti-detection guarantee is made. Project-authored source is licensed under MPL-2.0; third-party terms remain separate.
