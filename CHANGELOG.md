# Changelog

All notable changes to NeAntik Win (previously NeVision Win) are documented here.

## 0.3.0-preview — release candidate (2026-10-12, not yet published)

- Renamed the product to NeAntik Win and published reviewed sources at
  https://github.com/AffPapa/NeAntik-Win; personal runtime data is excluded.
- Bundles the project's own Chromium 155.0.8059.40 with native profile seed,
  CPU/deviceMemory, ICU timezone and narrowly scoped opaque sRGB uint8 Canvas
  readback behavior. Release QA is limited to the recorded test matrix; this is
  not a claim of undetectability or compatibility with every fingerprint test.
- Added native/ordinary profile choice, compact CPU/memory/timezone controls and
  explicit missing-core errors without falling back to ordinary Chrome.
- Native backup/restore retains the persona; clean cloning uses a fresh seed.
  Existing ordinary profiles and legacy backup identifiers remain compatible.
- WebRTC QA checks owned endpoints and proxy scenarios. This host's NetLog shows
  OS-accepted STUN sends but its local listener received none; no packet capture
  verified delivery outside the OS. Worker Device-Memory Client Hints are not
  emitted by Chromium's current WorkerFetchContext; worker JS surfaces are tested
  separately.
- **Preview only.** Back up `Data/` before first launch or upgrading. Chromium
  profiles may be upgraded and may not be usable by an older browser afterward.
- The artifact remains unsigned; Windows SmartScreen may warn. Other Windows
  versions and untested fingerprint surfaces are not certified.

## 0.2.1-preview — 2026-10-11

The unpublished 0.2.0 candidate was withheld after a packaged Windows long-path
backup failure. Its local artifacts are retained for diagnosis, not recommended for use.

### Launch and everyday use

- Browser launch and Chromium-lock waiting now run outside the Tk UI thread. A shared
  executor uses at most three workers and accepts at most six outstanding operations.
- Closing NeVision waits for pending background work instead of abandoning an active
  backup or restore. A reported operation failure is shown and cancels that close attempt.
- The profile list also checks Chromium locks, including browsers left open across a manager
  restart. An inaccessible lock is shown as an uncertain state.
- Browser discovery includes per-user Chrome/Edge installs and Windows App Paths entries,
  while preserving an explicitly selected executable.
- Search reuses existing rows. Added Ctrl+N, Ctrl+F, F5, Enter in the profile list and Escape
  in the search field. Profile details scroll, long names wrap and actions use two rows.
- Extensions opens the native Chrome/Edge extensions page of a closed profile. For an already
  open profile, use its browser menu. Extensions are not installed automatically.
- The empty state explains the installed-browser requirement and links to the official site.

### Proxy and data protection

- Internal backup/restore, cleanup and recovery support extended Windows paths
  without changing the machine-wide long-path policy or Chromium launch paths.
  Frozen self-test now exercises an actual file path longer than 260 characters.
- Proxy hosts are validated as a single DNS name or IP address; URL, credential and proxy-list
  syntax cannot be entered as a host. IPv6 endpoints receive the required brackets.
- Launch refuses a missing assigned proxy and SOCKS5 with username/password. HTTP(S) credentials
  remain manual browser authentication; a saved vault password is not applied automatically.
- Copied proxy passwords are cleared after 30 seconds or normal close only if the clipboard
  still contains that value. Windows clipboard history, sync and other managers are not cleared.
- Backup warns that its ZIP is unencrypted and may contain cookies, history and active website
  sessions. The manifest distinguishes browser-session data from excluded Proxy Vault credentials.
- Restore rejects duplicate manifests, case-insensitive and file/directory collisions, Windows
  reserved devices including superscript variants, unsafe raw ZIP names, trailing dots/spaces,
  links, special files and encrypted members. Backup does not follow symlink/junction directories.

### Build and delivery

- `release-version.json` supplies the application and Windows executable versions. Packages
  include runtime inventory, third-party licenses, source provenance and file hashes.
- Builds use an isolated source allowlist, stop on native failures and refuse overwriting
  versioned artifacts. Archive validation checks contents, version, hashes and required notices.
- Errors before the Tk window exists use a visible Windows error dialog.

### Compatibility and limits

- Schema `1` and `nevision-profile-backup-v1` remain; legacy v1 manifests are readable.
- This cycle's tested host is Windows 11 x64 build 26200. Windows 10, ARM64, x86 and a separate
  clean PC are not validated by that result. This remains an unsigned preview.
- Installed stock Chrome/Edge is required. No bundled core, fingerprint spoofing or automatic updater.
- Proxy diagnostics still test **TCP reachability only**, not authentication, HTTPS forwarding,
  exit IP or DNS/WebRTC routing.
- DPAPI and browser protections such as App-Bound Encryption limit transfer of saved credentials
  and sessions between Windows users/computers.
- Final packaged GUI, public download and publication checks remain release gates; source
  changes alone do not establish that they passed. See the artifact's release manifest and QA record.

## 0.1.3-preview — 2026-07-26

### Reliability and performance

- Backup files receive a unique name, are written to a temporary `.partial` file and are
  published only after ZIP creation succeeds.
- Backup and restore use the same 20,000-file / 8 GB uncompressed limits.
- Restore extracts into an isolated staging folder before making a profile visible.
- Delete and restore use an atomic local operation journal for recovery after an interrupted
  file/SQLite transition.
- Profile creation and deletion preserve consistency between the local folder and SQLite.
- SQLite errors are converted to user-facing messages, including a clear busy-database state.
- Backup, restore, health and proxy TCP checks run outside the Tk UI thread.
- Search is debounced; Chromium lockfiles and per-profile Windows mutexes prevent conflicting
  profile operations.
- The Proxy Vault form remains usable at common 150% Windows display scaling.

### Capabilities

- Local profile directories, groups, tags, notes and activity history.
- Windows DPAPI Proxy Vault for HTTP, HTTPS and SOCKS5 endpoints.
- Settings-only clean clone and `nevision-profile-backup-v1` backup/restore without proxy
  secrets.
- Safe restore checks for archive paths, file count and uncompressed size.

### Compatibility and known limits

- The v1 backup format and local schema remain compatible with `0.1.2-preview`.
- Saved proxy passwords are readable only by the same Windows user on the same computer.
- The proxy check validates TCP reachability only.
- This preview is unsigned and can trigger Microsoft SmartScreen.
- NeVision Win does not spoof fingerprints, bypass anti-fraud checks, evade bans or automate
  accounts.
