# Changelog

All notable changes to NeAntik Win (previously NeVision Win) are documented here.

## Unreleased — expanded local QA (2026-10-13)

- Completed a clean-from-scratch development build of the experimental V3
  Chromium core and an internal-only portable QA archive. Exact patch/build
  provenance, Canvas and cross-context loopback probes, the archive checker,
  EXE self-test and four ordinary/native launch cases passed. This did **not**
  replace or update the public 0.8.1-preview download; multi-device,
  cross-API, external-network and privacy-benefit gates remain open.
- Published a surface-by-surface measurement matrix for HTTP/JS/worker,
  graphics, media, network and profile-state behavior, with explicit controls
  and criteria for evaluating whether fingerprint changes actually help.
- Added a `Date.getTimezoneOffset()` cross-context check to the loopback
  fingerprint audit. It passed on the clean V3 development core alongside the
  existing `Intl` timezone and Device-Memory Client Hint checks.
- Added JavaScript/HTTP parity checks for high-entropy UA full-version-list
  and platform-version Client Hints; missing or mismatched values fail the
  audit. These local checks passed on the clean development core.
- Manually opened the extracted internal portable candidate, created an
  ordinary profile, launched its bundled Chromium, and closed both windows.
  The default Chromium new-tab page displayed Google; it remains an explicit
  browser-network privacy item rather than a claim of zero third-party calls.
- Added a disposable startup-network probe that publishes hostname counts,
  never full request URLs. On one clean-core headless run `about:blank` showed
  5 HTTP(S) request jobs versus 12 for `chrome://newtab`; blank still showed
  background Google-related hosts, so no zero-telemetry claim is made.
- Expanded the loopback fingerprint audit to another origin, Shared Worker and
  Service Worker. A missing Device-Memory Client Hint now fails the audit.
- Expanded real-browser profile isolation QA to Cache Storage and service-
  worker registrations, including restart, same-account backup/restore and
  clean configuration clones. These are post-release test-tool changes; the
  0.8.1-preview binary and its public checksum are unchanged. External network
  leaks, a second hardware class and Windows 10 remain unverified.
- Added a self-hosted WebRTC STUN/UDP diagnostic with a required direct positive
  control and a Chromium NetLog check. Installed Chrome sent and delivered
  local STUN requests. Both the exact 0.8.1 packaged Chromium and an unpatched
  source-built Chromium 155 attempted five STUN sends in direct mode, but the
  local sink received none; their proxy-bound cases attempted zero UDP sends.
  This narrows the discrepancy away from the published CPU/memory patch but
  does not resolve delivery, so the overall result remains inconclusive.
- Added a disposable Canvas probe and documented a separate native-persona
  development build. Its seed-based Canvas and timezone behavior is **not** in
  the 0.8.1 public download. The unreleased manager source has an opt-in mode
  that requires an exact staged native-core receipt; the public manager has no
  such mode.
- Exported the complete experimental Chromium patch with an exact upstream
  commit and deterministic verifier. This is source for review, not a release
  of the experimental browser core.
- Hardened source-built Chromium staging to reject untracked source files;
  previously the provenance gate checked only tracked changes. This prevents
  an experimental new source file from entering a build under an incomplete
  patch receipt. The public runtime patch must also match the approved diff
  byte-for-byte, not merely reverse-apply successfully.
- Removed a timestamped `chrome://theme` link from the offline Chromium credits
  copy at staging time. The credits content remains intact while repeated
  staging of identical sources can produce identical credits bytes.
- Added a strict experimental native-persona staging path: exact patch hash,
  exact public bytes, and a compiled capability handshake. A local staged core
  passed disposable Canvas and six-context CPU/memory/timezone checks; it is
  not a public portable release.
- Expanded the Canvas probe to asynchronous PNG/blob decoding, main-thread
  OffscreenCanvas and dedicated-worker OffscreenCanvas behind a loopback load
  barrier. The staged prototype passes; the 0.8.1 release correctly fails the
  seed-difference negative control.
- Added versioned experimental profile identity, a fresh seed for clean clones,
  preservation through v3 backup/restore, and a fail-closed launcher that will
  not run these profiles in stock Chrome or Edge. GUI and unit regressions cover
  opt-in selection and missing-core refusal. This remains unreleased source;
  stable per-profile seeds may increase linkability and are not an anonymity
  claim.
- Corrected the muted-label theme style found during disposable dark/light GUI
  inspection; explanatory text in the profile form now uses the dialog surface
  instead of the operating system's default light label background.
- Added archive-level native patch/capability provenance checks and negative
  fixtures. A public package carrying the experimental core must state its
  exact native patch hash; malformed capability receipts are rejected.
- Published experimental native patch revisions that bound requested CPU and
  memory values by stock Chromium's host values and increment the compiled
  capability handshake to schema 2. Synthetic low-end tests cover the bound;
  staging and the manager reject the previous schema-1 binary. Full runtime
  rebuild and second-machine QA are still pending, so the public download
  remains 0.8.1-preview.
- Made the clean-source, bundled-engine, privacy-patch and locale release gates
  apply to future public versions by numeric version, rather than silently
  expiring after a hard-coded 0.8.1 list.

## 0.8.1-preview — clean source provenance correction (2026-10-13)

- Rebuilt the same limited native privacy baseline from a committed, clean
  public source tree. The 0.8.0-preview binary was built before its source
  commit and recorded `source_state: modified`; its bytes remain available
  for audit but it is superseded for downloads. No profile-data migration or
  functional behavior change is intended.
- Repeated packaged EXE, browser-surface, cookie, proxy and launcher checks.
  The scope remains two capped CPU/memory signals, **not** full anonymity.

## 0.8.0-preview — limited native fingerprint reduction (2026-10-12)

- Built Chromium 155.0.8059.40 from the pinned source with a published, hashed
  privacy patch. The bundled core caps reported logical CPU count at 4 and
  approximated device memory at 8 GiB. JavaScript and Device-Memory Client
  Hints agree in disposable loopback tests on one Windows 11 machine.
- Added a source-build receipt, release-manifest linkage, patch allowlist and
  release-verifier checks so the patched binary cannot be presented as an
  unmodified upstream build. Existing installed Chrome/Edge profiles are not
  changed. No per-profile random fingerprint or timezone override is added.
- Added the detailed [implementation plan](docs/MASTER_IMPLEMENTATION_PLAN.md)
  and [privacy-patch rationale](docs/CHROMIUM_PRIVACY_BASELINE.md). This is an
  incremental reduction of two fingerprint surfaces, **not** a guarantee of
  anonymity or protection from account, network or cross-surface correlation.
- Profile data format is unchanged. Keep a private copy of the whole old
  portable folder before upgrading; never reuse an older browser with data
  already upgraded by a newer Chromium.

## 0.7.1-preview — open-source license and verifiable release scope (2026-10-12)

- Project-authored source is now published under MPL-2.0. The portable ZIP
  includes the same license, and archive verification rejects a missing one.
  Bundled Chromium and other dependencies retain their own license terms.
- Added a durable project mission, threat model, phased roadmap and release
  gates. The first phase documents profile independence and privacy claims;
  later fingerprint and network-privacy work is explicitly not shipped here.
- No browser-engine or network behavior changed from 0.7.0-preview. The bundled
  Chromium version remains 155.0.8059.40. There is no native fingerprint
  modification or guarantee of anonymity. Existing `Data/` remains compatible;
  keep a private copy of the complete old portable folder before upgrading.

## 0.7.0-preview — strict proxy routing and measured cookie protection (2026-10-12)

- Bundled Chromium profiles with a proxy now disable Chromium's implicit
  localhost proxy bypass, block background name resolution except for the
  configured proxy endpoint, disable QUIC and continue to restrict non-proxied
  WebRTC UDP. Local websites and real-time calls may work differently. This is
  browser-scoped, not a system firewall, VPN or proof of leak-free routing.
- New bundled-Chromium profiles also disable network prediction/preloading.
  Existing profile settings and later user choices remain untouched.
- Third-party cookie blocking is now behavior-tested in real Chromium: a
  control profile sent a cookie between two disposable HTTPS sites, while a
  new privacy-default profile did not. A no-STUN WebRTC check found no host
  ICE candidates with the proxy policy; it is not an external UDP/STUN test.
- Added loopback HTTP/SOCKS5 tests for localhost routing and unreachable-proxy
  failure, plus disposable packaged-launcher checks for the exact flags.
  No device/browser fingerprint spoofing or anonymity guarantee is claimed.
- Bundled Chromium remains 155.0.8059.40; Windows 10, external proxies,
  authenticated HTTPS CONNECT, IPv6 routing and cross-machine sessions remain
  unverified. Keep the complete old portable folder for rollback.

## 0.6.0-preview — safer new profiles and visible diagnostics (2026-10-12)

- New bundled-Chromium profiles start with third-party cookies blocked and
  geolocation, notifications, camera and microphone denied. These are
  Chromium's own preferences, created once before first launch; existing
  profiles and later user changes are not overwritten. Sites needing those
  permissions may require the user to allow them in Chromium.
- A profile's Diagnostics action opens a public check page in that browser
  profile. It shows browser-visible UA, language, timezone, screen,
  hardware/WebGL and permission states; on request, it shows the IP seen by
  our site. The page does not score anonymity, run STUN or send a fingerprint
  report. Hosting sees the request IP and may keep ordinary access logs.
- Added tests of real Chromium permission behavior and actual BrowserLauncher
  wiring in disposable profiles. Research now compares ten competing profile
  browsers, their vendor claims and lower-confidence independent reviews.
- This does **not** provide a coherent spoofed fingerprint, Tor routing or a
  guarantee against IP/DNS/WebRTC leaks. Proxy route checks, Windows 10 and
  cross-PC portability remain limited or unverified. Chromium core remains
  155.0.8059.40. Keep the old complete portable folder for rollback.

## 0.5.1-preview — smaller portable build and clearer controls (2026-10-12)

- Bundled Chromium now carries `en-US`, Russian and Thai UI locale packs instead
  of 228 languages. Other Windows languages fall back to English; browser core
  and profile data format are unchanged. ZIP is still a single portable folder.
- Added delayed, keyboard-accessible explanations to the principal controls and
  a short in-app guide under Help. Ambiguous action labels now say “Backup” and
  “Clean copy” in full Russian wording, including the sensitive backup warning.
- Profile details now display the actual pinned browser family instead of always
  saying “Chrome / Edge”. No browsing data is migrated or deleted.
- A bundled-Chromium profile with a configured proxy now restricts non-proxied
  WebRTC UDP using Chromium's supported IP-handling preference. WebRTC calls may
  behave differently; this is not a leak or anonymity guarantee. The system
  timezone remains unchanged.
- The core remains Chromium 155.0.8059.40, built from the same pinned upstream
  source. This preview is unsigned, does not spoof device/browser identity values and does
  not guarantee anonymity. Save the whole old portable folder before upgrading.

## 0.5.0-preview — self-contained portable Chromium (2026-10-12)

- The portable ZIP now includes source-built, unbranded Chromium 155.0.8059.40.
  New profiles use it by default; installed Chrome or Edge is not required.
- Existing profiles remain pinned to their original browser family, so a
  Chrome or Edge data directory is not silently opened with Chromium. Older
  unpinned profiles that already contain browser data require an explicit
  choice of their original browser or a clean copy.
- The bundled runtime includes its upstream license, third-party credits,
  pinned source commit and build provenance. Release checks reject development
  snapshots falsely claiming stable provenance or incomplete engine folders.
- On first bundled-browser launch, the manager grants Windows AppContainer
  read/execute access only to public `Engine/Chromium` files. ZIP extraction
  does not preserve NTFS ACLs; private `Data/` is never included in that grant.
- Browser launch, proxy vault, local profile data, backup and restore remain
  local. The release is portable-only, unsigned and has no automatic browser
  updater. Install a newer portable release for future Chromium security fixes.
- NeAntik does not modify fingerprint signals, automatically synchronize
  timezone to proxy, or guarantee anonymity. Proxy checking is TCP-only and
  does not prove exit IP, DNS, WebRTC or UDP behavior.

## 0.4.1-preview — portable reliability and usability (2026-10-12)

- Profiles now remember whether their local browser data belongs to Chrome or Edge.
  Switching to the other family is blocked instead of reusing the same data directory.
  Existing profiles are pinned on their first launch with this version; backup and
  restore preserve the family. A clean copy starts unpinned.
- Custom browser selection accepts only an installed `chrome.exe` or `msedge.exe`.
- Profiles with visually identical proxy choices retain the correct proxy assignment.
  Recopying the same proxy password restarts its 30-second clipboard-clear timer.
- Replaced obsolete Native-core text on the first-run screen. Dialogs close with
  Escape; history has an explicit Close button; theme changes retain search focus,
  caret and profile-detail scroll. Native menus expose the main actions.
- Removed an unused engine installer. The public-source guard now scans the exact
  staged Git blobs, not potentially different working-tree files.
- Portable-only preview. Requires installed stock Chrome or Edge; no fingerprint
  modification or bundled browser engine. Back up `Data/` before upgrading.

## 0.4.0-preview — ordinary-browser edition (2026-10-12)

- Removed the native fingerprint-profile controls and launch path from the app. New
  profiles launch installed stock Chrome or Edge without browser-surface override flags.
- Legacy experimental native profile records remain on disk but are marked unavailable;
  this edition refuses to launch, edit or clone them. Their browser data is not deleted.
- Release packaging and archive verification now reject custom browser-engine payloads
  and reject a release manifest that claims fingerprint modification.
- This remains a portable profile manager, not a standalone Chromium distribution.
  It requires Chrome or Edge installed on Windows; it does not modify fingerprint signals.
- **Preview only.** Back up `Data/` before upgrading. The artifact remains unsigned;
  Windows SmartScreen may warn. Tested OS scope is documented below.

## 0.3.0-preview — portable profile manager edition (2026-10-12)

- Renamed the product to NeAntik Win and published reviewed sources at
  https://github.com/AffPapa/NeAntik-Win; personal runtime data is excluded.
- The downloadable portable artifact is a local profile manager that launches
  installed Chrome or Edge. It contains no native Chromium binary and no
  fingerprint-modification runtime.
- Profile creation in this edition exposes only the ordinary browser mode.
  Existing native profiles are kept on disk; this edition does not edit, clone
  or launch them without the matching separate native bundle.
- The repository's own Chromium 155 implementation and its native QA artifacts
  remain research/build sources, separate from this downloadable package.
- Ordinary profile metadata and legacy backup identifiers remain compatible.
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
