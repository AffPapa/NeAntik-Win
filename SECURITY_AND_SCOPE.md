# Security, privacy and scope

Applies to NeAntik Win 0.7.0-preview portable Chromium edition.

## Product boundary

This downloadable edition manages local directories and bundles unbranded Chromium 155.0.8059.40 built from pinned upstream source. New profiles use that browser without an installed Chrome/Edge. Existing profiles pinned to installed Chrome/Edge retain their browser family. NeAntik does not spoof device or browser identity values. Legacy experimental engine profiles are blocked from launch and remain on disk. Separate directories isolate normal profile storage; they are not a security sandbox against malware running as the same Windows user. The bundled Chromium has no automatic updater; install newer portable releases for security fixes.

For a newly created, empty bundled-Chromium profile, the launcher writes Chromium's own initial Preferences once: block third-party cookies, deny geolocation, notifications, camera and microphone, and disable network prediction/preloading. It never edits existing profile preferences or overwrites later user choices. These settings can break site features until changed in Chromium. They are privacy defaults, **not** a spoofed fingerprint or network-anonymity mechanism. Existing profiles, installed Chrome and Edge do not receive them retroactively.

Chromium's Windows sandbox needs read/execute access to its own runtime files. Because ZIP extraction drops NTFS ACLs, the first bundled-browser launch grants the Windows `ALL APPLICATION PACKAGES` group that access to `Engine/Chromium` only. It does not grant access to `Data/`, backups or proxy secrets. A writable NTFS folder is tested; a filesystem without Windows ACL support is not validated. The browser sandbox remains enabled.

Only Windows 11 x64 build 26200 has been exercised for this release. The portable executable is unsigned. A checksum verifies bytes, not publisher identity.

## Sensitive local data

Metadata is stored in SQLite and browser data lives in `Data/`. There is no NeAntik cloud synchronization or application telemetry. Bundled Chromium, installed browsers and extensions can make their own network requests under their own policies; the manager does not claim to disable all browser telemetry.

Proxy passwords use Windows DPAPI for the current Windows user. Software running as that user may be able to decrypt them. Moving a database to another account or PC does not make its secrets decryptable there. Browser DPAPI/App-Bound Encryption also limits portability of saved browser credentials and sessions; cross-PC cookie portability is not guaranteed.

Backup ZIPs are unencrypted and can include cookies, active sessions, history and browser password stores. They exclude proxy-vault secrets, and restored profiles have no proxy assigned. Keep backups private. A UI warning and manifest fields explicitly describe this sensitivity.

Clipboard password cleanup occurs after 30 seconds and on normal close, only when the current clipboard still equals the copied password. It does not erase Windows clipboard history, cloud clipboard synchronization or copies retained elsewhere; crashes may prevent cleanup.

## Proxy and extension boundaries

Hosts are validated and normalized, including IDNA and IPv6. A missing assigned proxy, invalid configuration or unsupported authenticated SOCKS5 prevents launch. HTTP(S) proxy authentication uses the stock browser's own prompt; secrets are not included in command-line arguments. These fail-closed checks are not a system firewall or a guarantee against every browser/network leak.

Proxy checking is TCP reachability only: it does not verify authentication, protocol negotiation, DNS routing, UDP, exit IP or WebRTC behavior. No local authenticated-proxy broker is bundled.

The optional Diagnostics action opens `https://nevision-win.mail782861.chatgpt.site/check.html` inside the selected profile. That website and its host see the request IP and browser headers; host logs may retain them. A button asks its own server what IP it observed. JavaScript-visible parameters remain in the page; the page does not upload a fingerprint report or start STUN. A displayed IP is a point-in-time observation for one site, **not** proof of DNS/WebRTC/UDP or all-traffic routing.

When a proxy is assigned to a **bundled Chromium** profile, the launcher uses one fixed proxy without a DIRECT fallback, subtracts Chromium's implicit loopback bypass, blocks background name resolution except the proxy endpoint, disables QUIC and sets `disable_non_proxied_udp` WebRTC IP handling. This can prevent local websites or real-time calls from working. Tests show the configured local proxy handles localhost HTTP URLs, unreachable proxies do not fall back to DIRECT in tested cases, and a no-STUN ICE test produces no host candidate. These are browser-scoped checks, **not** a system firewall or proof that every transport uses the proxy; proxy DNS lookup itself is allowed. No-proxy profiles and installed Chrome/Edge are unchanged. The system timezone is not overridden or inferred from proxy IP.

The Extensions action opens the selected browser's native extension manager for a closed profile. When a profile is already open, use its browser menu. Extensions are optional and not installed automatically. They can access sensitive browsing data according to their permissions; NeAntik does not audit or sandbox third-party extensions.

## Browser-surface matrix for this release

This matrix describes the **0.7.0-preview portable Chromium binary**. “Inherited” means NeAntik does not set or rewrite the value; it is supplied by bundled Chromium (or an already-pinned installed browser) and Windows. The release tests exercise selected profile/launcher/network behavior, not comprehensive JavaScript fingerprint measurement.

| Surface | 0.7.0-preview behavior | Evidence / limitation |
|---|---|---|
| Browser engine, version and TLS/network stack | New profiles use bundled unbranded Chromium 155.0.8059.40; old Chrome/Edge profiles stay pinned | Upstream source commit and build-only patch are recorded; no TLS fingerprint suite |
| JavaScript `navigator` values, UA and Client Hints | Not overridden; inherited from the selected browser | No per-property override; API and HTTP-header parity were not measured in this release |
| Language, timezone, CPU/memory, screen and viewport | Not overridden; inherited from Windows/browser configuration. Browser UI packs are en-US, ru and th, with English fallback | No persona configuration; cross-frame and worker consistency were not separately measured |
| Canvas, WebGL/WebGPU, audio, fonts and layout metrics | Not modified by the manager | No surface-level fingerprint probes or equality guarantees |
| Frames, dedicated/shared/service workers | No injected JavaScript or worker patching | These contexts were not independently tested for this release |
| Cookies, history and web storage | Stored by the selected browser inside each profile's separate user-data directory; new bundled profiles start with third-party cookies blocked and network prediction disabled | In two disposable HTTPS sites, an allow-control profile sent the third-party cookie and the new default profile did not; arbitrary websites and exceptions are not exhaustively tested |
| Geolocation, notifications, camera and microphone | New bundled profiles start with Chromium default permission set to Block; existing profiles and later user settings are untouched | Real Chromium `Permissions.query` returns `denied` for the four defaults in a disposable test; site-specific changes remain possible |
| Proxy routing, DNS and WebRTC | Bundled Chromium with proxy blocks implicit loopback bypass/background DNS, disables QUIC and restricts non-proxied WebRTC UDP | Real loopback HTTP/SOCKS tests and no-STUN ICE test pass; public IP, external DNS/UDP, authenticated CONNECT, IPv6 and full leak resistance are not certified |
| Extensions | Uses the browser's native extension manager and browser policy | No automatic installation or extension permission audit |

Do not infer fingerprint spoofing, coherent cross-surface personas, anonymity, or successful anti-fraud testing from profile isolation or proxy assignment. Those are distinct capabilities and are absent from this downloadable edition.

## Backup, recovery and concurrency safeguards

Restore creates a new profile and checks ZIP paths, duplicate/case-insensitive collisions, file/directory collisions, reserved Windows device names (including superscript COM/LPT forms), raw/original name discrepancies, symlinks, encryption and non-regular profile entries. Limits are 20,000 files and 8 GB uncompressed. These limits also apply to backup creation.

Backup traversal does not follow symlinks or junctions: a non-excluded linked directory stops backup; linked/non-regular files are skipped. Cache and lock files are excluded. Output is written to a unique partial file and atomically promoted; restore uses staging and recovery journaling. These controls do not make a hostile archive harmless in every future implementation: keep regression tests and dependency updates.

Profile mutation uses locks, checks live browser use and refuses unsafe operations. A Data-directory manager mutex prevents competing manager instances from concurrently recovering/mutating the same data. Launch rechecks whether the profile and its proxy binding still exist/match before process creation, preventing stale queued launches after deletion or reassignment. Unknown recovery state must fail safely.

Browser launch uses a bounded background executor (3 workers, at most 6 running/queued operations). Normal close drains manager work before destroying the UI and does not forcibly terminate user browser windows.

## Release and source policy

Preserve a private pre-update snapshot of the entire portable folder before copying data into a new version's folder. Roll back with that snapshot, not with data that a newer browser may have upgraded.

The owner authorized publication of the reviewed source repository at https://github.com/AffPapa/NeAntik-Win. No open-source license has been selected for the original application code; public visibility does not itself grant reuse rights. Never publish user `Data/`, secrets or sensitive logs. Every artifact must pass [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md), including clean packaging, hashes, dependency notices, packaged tests and public-download verification. Report vulnerabilities through [SECURITY.md](SECURITY.md).
