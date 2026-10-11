# Security, privacy and scope

Applies to NeVision Win 0.2.1-preview.

## Product boundary

NeVision manages local directories and launches installed stock Chrome/Edge. It does not patch a browser engine, spoof fingerprints, hide automation, guarantee anonymity, bypass anti-fraud systems or guarantee account outcomes. Separate directories isolate normal profile storage; they are not a security sandbox against malware running as the same Windows user.

Only Windows 11 x64 build 26200 has been exercised for this release. The portable executable is unsigned. A checksum verifies bytes, not publisher identity.

## Sensitive local data

Metadata is stored in SQLite and browser data lives in `Data/`. There is no NeVision cloud synchronization or telemetry. Chrome/Edge and installed extensions can make their own network requests under their own policies.

Proxy passwords use Windows DPAPI for the current Windows user. Software running as that user may be able to decrypt them. Moving a database to another account or PC does not make its secrets decryptable there. Browser DPAPI/App-Bound Encryption also limits portability of saved browser credentials and sessions; cross-PC cookie portability is not guaranteed.

Backup ZIPs are unencrypted and can include cookies, active sessions, history and browser password stores. They exclude proxy-vault secrets, and restored profiles have no proxy assigned. Keep backups private. A UI warning and manifest fields explicitly describe this sensitivity.

Clipboard password cleanup occurs after 30 seconds and on normal close, only when the current clipboard still equals the copied password. It does not erase Windows clipboard history, cloud clipboard synchronization or copies retained elsewhere; crashes may prevent cleanup.

## Proxy and extension boundaries

Hosts are validated and normalized, including IDNA and IPv6. A missing assigned proxy, invalid configuration or unsupported authenticated SOCKS5 prevents launch. HTTP(S) proxy authentication uses the stock browser's own prompt; secrets are not included in command-line arguments. These fail-closed checks are not a system firewall or a guarantee against every browser/network leak.

Proxy checking is TCP reachability only: it does not verify authentication, protocol negotiation, DNS routing, UDP, exit IP or WebRTC behavior. No local authenticated-proxy broker is bundled.

The Extensions action opens the native Chrome/Edge extension manager for a closed profile. When a profile is already open, use its browser menu. Extensions are optional and not installed automatically. They can access sensitive browsing data according to their permissions; NeVision does not audit or sandbox third-party extensions.

## Backup, recovery and concurrency safeguards

Restore creates a new profile and checks ZIP paths, duplicate/case-insensitive collisions, file/directory collisions, reserved Windows device names (including superscript COM/LPT forms), raw/original name discrepancies, symlinks, encryption and non-regular profile entries. Limits are 20,000 files and 8 GB uncompressed. These limits also apply to backup creation.

Backup traversal does not follow symlinks or junctions: a non-excluded linked directory stops backup; linked/non-regular files are skipped. Cache and lock files are excluded. Output is written to a unique partial file and atomically promoted; restore uses staging and recovery journaling. These controls do not make a hostile archive harmless in every future implementation: keep regression tests and dependency updates.

Profile mutation uses locks, checks live browser use and refuses unsafe operations. A Data-directory manager mutex prevents competing manager instances from concurrently recovering/mutating the same data. Launch rechecks whether the profile and its proxy binding still exist/match before process creation, preventing stale queued launches after deletion or reassignment. Unknown recovery state must fail safely.

Browser launch uses a bounded background executor (3 workers, at most 6 running/queued operations). Normal close drains manager work before destroying the UI and does not forcibly terminate user browser windows.

## Release and source policy

Preserve a private pre-update snapshot of the entire portable folder before copying data into a new version's folder. Roll back with that snapshot, not with data that a newer browser may have upgraded.

Public binary distribution is authorized; source licensing is unresolved, so keep the source repository private. Never publish user Data, secrets or sensitive logs. Every artifact must pass [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md), including clean packaging, hashes, dependency notices, packaged tests and public-download verification. Report vulnerabilities through [SECURITY.md](SECURITY.md).
