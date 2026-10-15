# Security, privacy and scope

The 0.8.30-preview candidate described below bundles stock Chromium and does not
modify browser fingerprint values. Sections about 0.8.6/0.8.8 native-persona
builds are historical and do not describe this release. Check the official
download page and checksum for the current artifact; local tests alone are not
public-release proof. Exact source, ZIP identity, test evidence and known gaps for
this release are recorded in [release evidence](docs/RELEASE_PUBLICATION_0.8.30-preview.md) after release gates pass.

The published 0.8.7-preview rejects hardlinked files during backup to avoid
copying data outside a profile into the unencrypted ZIP. The exact public
download and remaining test gaps are recorded in
[release evidence](docs/RELEASE_PUBLICATION_0.8.7-preview.md). This change
does not encrypt backups or prove the absence of other local data exposures.

## Historical 0.8.6-preview V4b boundary (not included in 0.8.30-preview)

The opt-in V4b mode requires a matching Chromium 155 source build
and exact capability/provenance receipt. It uses a fresh in-memory session key
and the top-level site for measured opaque sRGB uint8 Canvas2D readbacks,
including frames and dedicated/shared/service workers. The prior V3
persistent, profile-specific Canvas signal is not used in this mode. CPU/RAM
and UTC controls are limited, and a local profile seed remains metadata, not
proof of a unique or anonymous network identity. WebGL/WebGPU, translucent,
float16 and display-p3 readbacks remain stock or unverified. No claim covers
all tracking surfaces, population anonymity or same-user malware.

On one Windows 11 x64 host, the V4b core passed 6 + 21 + 3 native unit
tests, 12/12 two-site/restart Canvas cases and 6/6 context cases with 11/11
checks. Two staging runs yielded 39 byte-identical files. The test identity
is pinned to upstream commit
`cfaadc5a132d78e1828635aa8405a499f3e14864`, V4b patch SHA-256
`bba02390999c33bcf6097625c03093022ed534c316184462cc8468efbc79b708`
and tested `chrome.dll` SHA-256
`6762cf6ead3b829b481fde9540069cc709c9de3a211c738856190850a6928413`.
External DNS/UDP/IPv6/TURN routing and a second computer are **NOT RUN**.
Local packaged verification and public-download integrity are separate gates;
the latter must be checked against the exact published ZIP. No version
guarantees anonymity.

The published 0.8.8-preview V5 release changes the Canvas key transport to
early browser-to-renderer Mojo IPC and pins the opt-in launcher to the V5
patch receipt. A previous V4b engine is rejected for this mode. Local native,
cross-context and session-rotation tests passed on one Windows 11 host. The
portable ZIP was repeat-downloaded, hash-checked and self-tested; external
network gates remain separate. This
does not make the browser generally anonymous.

## Product boundary

The 0.8.30-preview candidate manages local directories and bundles unbranded
stock Chromium `155.0.8059.79`, built from pinned upstream source with a
build-compatibility patch only. `fingerprint_modification` is explicitly
`false`; NeAntik does not override browser/device fingerprint values. New
profiles use bundled Chromium without installed Chrome/Edge; existing Chrome/
Edge profiles remain pinned to their browser family. Experimental
native-persona profiles from older releases stay on disk and can be backed up/
restored, but this build refuses to launch them. “Чистая копия” creates a new
empty profile and carries only settings; it does not copy cookies, history or
sessions. Separate directories isolate normal profile storage; they are not a
security sandbox against malware running as the same Windows user.

At application startup, the manager rejects pre-existing reparse points in the
portable root, `Data`, `Profiles`, `Backups`, `Logs`, `Operations`, the SQLite
database and its journal/WAL/SHM sidecar paths before opening SQLite. Existing
database files and sidecars must be regular files without additional hardlinks.
This startup check reduces accidental path redirection but does not prevent
TOCTOU or same-user tampering. Before launch, the manager also rejects reparse points at the portable `Data`,
`Profiles` and selected profile roots. It also `lstat`s a fixed set of
high-sensitivity Chromium paths (for example cookies, local storage,
IndexedDB, service-worker storage, preferences and login data), without
recursively scanning the whole profile. In addition, it inspects direct
children only in `Default/IndexedDB`,
`Default/Service Worker/CacheStorage`, and
`Default/Local Storage/leveldb`, with a limit of 10,000 entries per directory.
Reparse points and regular files with multiple hardlinks are rejected; direct
`os.stat` is used for the hardlink count because Windows `DirEntry.stat()` may
report zero. A directory that exceeds the limit or cannot be inspected fails
closed. Descendants below those direct children and other unlisted nested paths
are not covered. These checks catch selected pre-existing redirects/sharing;
they are not protection against TOCTOU or same-user tampering and do not
isolate a profile from another process running as the same Windows account. On
one Windows 11 host, the earlier 10,000-entry IndexedDB/CacheStorage scan took
27.7 ms median / 29.7 ms p95 over 15 checks; the added LevelDB scan has not been
included in that timing, so this is not a startup guarantee for other PCs or
storage devices. The bundled Chromium has no automatic updater; install newer
portable releases for security fixes.

For a newly created, empty bundled-Chromium profile, the launcher writes Chromium's own initial Preferences once: block third-party cookies, deny geolocation, notifications, camera and microphone, disable network prediction/preloading, and open a blank new-tab document. It never edits existing profile preferences or overwrites later user choices. These settings can break site features until changed in Chromium. They are privacy defaults, **not** a spoofed fingerprint or network-anonymity mechanism. The blank document does not stop Chromium's other background requests. Existing profiles, installed Chrome and Edge do not receive them retroactively.

New bundled-Chromium profiles also receive a private `Downloads` folder inside their profile. The launcher stores a small marker to rebase **only this managed path** after a portable move or backup restore; a download directory chosen by the user in Chromium is respected. Older profiles without the marker and installed Chrome/Edge profiles are not changed. Browser downloads and backup ZIPs containing them are ordinary sensitive files, not encrypted or sandboxed from software running as the same Windows account. The profile backup's 8 GB / 20,000-file limits can reject a large Downloads folder.

Chromium's Windows sandbox needs read/execute access to its own runtime files. Because ZIP extraction drops NTFS ACLs, the first bundled-browser launch grants the Windows `ALL APPLICATION PACKAGES` group that access to `Engine/Chromium` only. It does not grant access to `Data/`, backups or proxy secrets. A writable NTFS folder is tested; a filesystem without Windows ACL support is not validated. The browser sandbox remains enabled.

Only Windows 11 x64 build 26200 has been exercised for this release. The portable executable is unsigned. A checksum verifies bytes, not publisher identity.

## Sensitive local data

Metadata is stored in SQLite and browser data lives in `Data/`. There is no NeAntik cloud synchronization or application telemetry. Bundled Chromium, installed browsers and extensions can make their own network requests under their own policies; the manager does not claim to disable all browser telemetry.

Proxy passwords use Windows DPAPI for the current Windows user. Software running as that user may be able to decrypt them. Moving a database to another account or PC does not make its secrets decryptable there. Browser DPAPI/App-Bound Encryption also limits portability of saved browser credentials and sessions; cross-PC cookie portability is not guaranteed.

Backup ZIPs are unencrypted and can include cookies, active sessions, history and browser password stores. They exclude proxy-vault secrets, and restored profiles have no proxy assigned. Keep backups private. A UI warning and manifest fields explicitly describe this sensitivity. Before publishing a newly generated archive, NeAntik verifies the expected member set, manifest and member CRCs; this detects many incomplete/corrupt writes but does not encrypt the archive or protect against another process running as the same Windows user. CRC verification reads the completed archive again and adds I/O proportional to its size.

Clipboard password cleanup occurs after 30 seconds and on normal close, only when the current clipboard still equals the copied password. It does not erase Windows clipboard history, cloud clipboard synchronization or copies retained elsewhere; crashes may prevent cleanup.

## Proxy and extension boundaries

Hosts are validated and normalized, including IDNA and IPv6. A missing assigned proxy, invalid configuration or unsupported authenticated SOCKS5 prevents launch. HTTP(S) proxy authentication uses the stock browser's own prompt; secrets are not included in command-line arguments. These fail-closed checks are not a system firewall or a guarantee against every browser/network leak.

The user-initiated proxy diagnostic sends a bounded protocol probe to the selected proxy: `OPTIONS *` for HTTP(S), with strict default TLS verification for HTTPS, or a SOCKS5 greeting offering only no-auth. It never reads/sends saved credentials or requests a destination URL; HTTP 407 is reported as an auth challenge. This is not a CONNECT/forwarding check and does not prove that sites load, DNS is remote, or that there are no UDP/WebRTC leaks or reveal-free routes. Proxy-host DNS uses Windows; using an IP literal removes only that proxy-host lookup, not other potential DNS routes. No local authenticated-proxy broker is bundled. Chromium's built-in SOCKS5 does not support authentication; HTTP(S) credentials are entered manually in its native prompt.

Profile details and health diagnostics warn when no proxy is assigned or the same proxy entry is assigned to multiple profiles. They also state that a uniquely assigned proxy has not been independently checked for exit IP or DNS/WebRTC leaks. This disclosure does not change routing or prove separate network identities.

The optional Diagnostics action opens `https://nevision-win.mail782861.chatgpt.site/check.html` inside the selected profile. That website and its host see the request IP and browser headers; host logs may retain them. A button asks its own server what IP it observed. JavaScript-visible parameters remain in the page; the page does not upload a fingerprint report or start STUN. A displayed IP is a point-in-time observation for one site, **not** proof of DNS/WebRTC/UDP or all-traffic routing.

When a proxy is assigned to a **bundled Chromium** profile, the launcher uses one fixed proxy without a DIRECT fallback, subtracts Chromium's implicit loopback bypass, blocks background name resolution except the proxy endpoint, disables QUIC and sets `disable_non_proxied_udp` WebRTC IP handling. This can prevent local websites or real-time calls from working. Tests show the configured local proxy handles localhost HTTP URLs, unreachable proxies do not fall back to DIRECT in tested cases, and a no-STUN ICE test produces no host candidate. These are browser-scoped checks, **not** a system firewall or proof that every transport uses the proxy; proxy DNS lookup itself is allowed. No-proxy profiles and installed Chrome/Edge are unchanged. The browser inherits the operating-system timezone; NeAntik does not infer it from proxy IP.

The Extensions action opens the selected browser's native extension manager for a closed profile. When a profile is already open, use its browser menu. Extensions are optional and not installed automatically. They can access sensitive browsing data according to their permissions; NeAntik does not audit or sandbox third-party extensions.

## Historical 0.8.5-preview browser-surface matrix

This matrix describes the historical **0.8.5-preview portable Chromium binary**, unchanged from 0.8.4-preview. Later releases added experimental modes that are not included in the 0.8.30-preview candidate. “Inherited” means NeAntik does not set or rewrite the value; it is supplied by bundled Chromium (or an already-pinned installed browser) and Windows. These selected tests on one Windows machine were never a comprehensive anonymity assessment.

| Surface | 0.8.5-preview behavior | Evidence / limitation |
|---|---|---|
| Browser engine, version and TLS/network stack | New profiles use bundled unbranded Chromium 155.0.8059.40; old Chrome/Edge profiles stay pinned | Upstream source commit and build/privacy patch hashes are recorded; no TLS fingerprint suite |
| JavaScript `navigator` values, UA and Client Hints | Bundled Chromium caps `navigator.hardwareConcurrency` at 4 and device memory at 8 GiB; UA and other hints remain browser-supplied | Loopback comparison saw CPU 16→4 and memory/Device-Memory CH 32→8 on one Windows machine; no external cohort or anti-correlation proof |
| Language, timezone, screen and viewport | Inherited from Windows/browser configuration. Browser UI packs are en-US, ru and th, with English fallback | No persona configuration or proxy-based timezone; screen/viewport are not standardized |
| Canvas, WebGL/WebGPU, audio, fonts and layout metrics | Not modified by the manager | Local probes observed selected Canvas/WebGL/Audio values in frames, but do not estimate entropy or establish equality across computers |
| New-tab page and browser background networking | New bundled profiles render `chrome://newtab` as a blank document; existing profiles are untouched | Headless startup probe confirms the document and preference, but also observes Google-related background requests and UDP attempts even with `about:blank` |
| Frames and workers | Native Blink accessors used by measured main frame, same-origin and cross-origin iframe, dedicated/shared/service workers; no injected JavaScript | Expanded loopback QA on one Windows 11 machine after the 0.8.1 build; other hardware, cross-site HTTPS and browser modes remain unverified |
| Cookies, history and web storage | Stored by the selected browser inside each profile's separate user-data directory; new bundled profiles start with third-party cookies blocked and network prediction disabled | In two disposable HTTPS sites, an allow-control profile sent the third-party cookie and the new default profile did not. Additional loopback QA after release found cookie/localStorage/IndexedDB/Cache Storage/service-worker state isolated across two profiles, persistent after restart and restored in one account; arbitrary sites and cross-PC restore are not exhaustively tested |
| Downloads | New bundled profiles use a private `Downloads` directory inside the profile; managed paths rebase after a portable move or same-machine restore | Synthetic files downloaded in real Chromium into two distinct profiles and after moving one. Old profiles and custom download paths are not changed; backup includes files and may hit size limits |
| Geolocation, notifications, camera and microphone | New bundled profiles start with Chromium default permission set to Block; existing profiles and later user settings are untouched | Real Chromium `Permissions.query` returns `denied` for the four defaults in a disposable test; site-specific changes remain possible |
| Proxy routing, DNS and WebRTC | Bundled Chromium with proxy blocks implicit loopback bypass/background DNS, disables QUIC and restricts non-proxied WebRTC UDP | Real loopback HTTP/SOCKS tests and no-STUN ICE test pass; public IP, external DNS/UDP, authenticated CONNECT, IPv6 and full leak resistance are not certified |
| Extensions | Uses the browser's native extension manager and browser policy | No automatic installation or extension permission audit |

Do not infer coherent cross-surface personas, anonymity, or successful anti-fraud testing from two capped hardware signals, profile isolation or proxy assignment. Other fingerprint surfaces and external network leaks remain unverified.

## Backup, recovery and concurrency safeguards

Restore creates a new profile and checks ZIP paths, duplicate/case-insensitive collisions, file/directory collisions, reserved Windows device names (including superscript COM/LPT forms), raw/original name discrepancies, symlinks, encryption and non-regular profile entries. Limits are 20,000 files and 8 GB uncompressed. These limits also apply to backup creation.

Backup traversal does not follow symlinks or junctions: a non-excluded linked directory stops backup; linked/non-regular files are skipped. Cache and lock files are excluded. Output is written to a unique partial file and atomically promoted; restore uses staging and recovery journaling. These controls do not make a hostile archive harmless in every future implementation: keep regression tests and dependency updates.

Profile mutation uses locks, checks live browser use and refuses unsafe operations. A Data-directory manager mutex prevents competing manager instances from concurrently recovering/mutating the same data. Launch rechecks whether the profile and its proxy binding still exist/match before process creation, preventing stale queued launches after deletion or reassignment. Unknown recovery state must fail safely.

Browser launch uses a bounded background executor (3 workers, at most 6 running/queued operations). Normal close drains manager work before destroying the UI and does not forcibly terminate user browser windows.

## Release and source policy

Preserve a private pre-update snapshot of the entire portable folder before copying data into a new version's folder. Roll back with that snapshot, not with data that a newer browser may have upgraded.

The owner authorized publication of the reviewed source repository at https://github.com/AffPapa/NeAntik-Win. Project-authored source is licensed under [MPL-2.0](LICENSE); third-party notices remain in force. This is not a guarantee of anonymity or legality of every use. Never publish user `Data/`, secrets or sensitive logs. Every artifact must pass [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md), including clean packaging, hashes, dependency notices, packaged tests and public-download verification. Report vulnerabilities through [SECURITY.md](SECURITY.md).
