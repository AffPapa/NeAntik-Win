# NeAntik Win: bounded fingerprint engine integration

Status: implementation design from source inspection, 2026-10-11. The actual engine and its documented parameter contract must be selected and verified before application integration. This document does not claim that the current stock Chrome/Edge launcher changes fingerprints.

## Product contract

Keep the existing Python/Tk desktop shell, SQLite storage, portable folder, backup/recovery safeguards and asynchronous launch. A browser process must perform fingerprint changes in its own native engine. A single profile has a stable identity across restarts; a clean clone receives a new identity; restoration of a backup preserves the original identity. The UI exposes one coherent preset and an optional advanced panel rather than dozens of unrelated toggles.

Initial target is Windows x64 desktop Chromium identity matching the actual bundled engine family. Cross-platform Safari/macOS impersonation, independent arbitrary User-Agent strings and per-navigation randomization are outside this bounded implementation. Real process architecture, fonts, codecs, graphics capabilities and browser version cannot safely be treated as arbitrary independent values.

Required release gate: native preset parameters produce measured changes in a real browser at normal document start in main frames, same-origin frames, cross-origin frames and supported worker contexts. Server-observed headers and User-Agent Client Hints agree with JavaScript identity. Persistent canvas outputs differ between distinct seeds, remain stable for the same profile and do not break normal drawing. The degree of coverage is recorded surface by surface.

## Engine decision gate

An engine is eligible only after all of these are established from its actual project and downloaded release:

1. Redistribution and source-publication terms, executable provenance and Windows x64 availability.
2. Documented parameters or a reviewed native patch implementing a seed/config contract; invented command-line switches are not accepted.
3. Sandbox remains enabled and the standard browser window, navigation, downloads, extensions and cookies continue to function.
4. Native coverage demonstrated on an independent local fixture. A page-injected JavaScript shim is insufficient evidence of native coverage.
5. Engine and Chromium version are pinned; a browser security-update process exists. An older version is not silently selected merely because it exposes more switches.
6. Package has the required licenses and verified artifact hashes. If supplied by a third-party engine, the UI and repository say so.

Do not silently fall back to stock Chrome when an anti-fingerprint engine is missing, unsupported or fails validation. Offer an actionable error. A separately named ordinary profile mode can be preserved for migration, but cannot be represented as fingerprint-protected.

## Small engine adapter

Create a standard-library-only module `browser_engine.py` with immutable types for an engine manifest and validated profile configuration. Its responsibilities are:

- Find the bundled engine inside the portable directory; resolve an explicitly selected developer engine only when its capability manifest passes validation.
- Validate engine family/version/capabilities once and cache by executable path, size and modification time. Hash checking is performed during install/build and whenever those attributes change, not per navigation.
- Validate each configuration at creation/edit/import and again before launch. Reject unknown schema versions, control characters, invalid seeds and unsupported overrides.
- Produce an argv list from a single documented contract. Use `subprocess.Popen(list)` without a shell. Keep credentials out of argv.
- Translate the verified contract to command-line parameters or a versioned JSON config file, depending on the engine. File-based configs are written atomically outside the browser's internal `Default` folder.
- Return a concise capability summary for the UI and a detailed structured capability report for QA.

Do not add Electron, a persistent local web service or browser automation runtime to the shipped application. No remote debugging listener is needed for normal operation. Test-only automation may be separate and must not change normal launch flags.

## Stable identity storage

Use a separate `profile_fingerprints` table keyed by `profiles.id`, with foreign-key cascade, to avoid rewriting each existing profile SQL statement and to preserve the old profile column layout. Store a versioned, canonical JSON config, created/updated timestamps and engine compatibility metadata. Seed generation uses `secrets`, once on creation, within the engine's verified supported integer range; never Python `hash()` or a time-derived seed.

The canonical config is authoritative. Example conceptual fields are `schema`, `mode`, `engine_family`, `preset_id`, `seed`, `locale`, `timezone` and explicitly supported optional values. This is an application schema, not a claim that any engine accepts these literal parameter names.

- Existing profiles: record an explicit ordinary mode initially. Migration to a native engine must be an explicit, backup-supported operation because newer Chromium data may not be readable by the old engine.
- Save existing profile: keep the original seed when unrelated name/proxy fields change.
- Clean clone: copy the preset, generate a new seed, and retain the current no-cookie/history/session behavior.
- Backup restore: retain the backed-up seed and preset even though restoration gives the database record a new profile ID. Otherwise canvas/session identity changes unexpectedly.
- UI regeneration: available only when the browser is closed; explain that this changes the profile identity and cannot repair a site's prior trust decision.
- Fingerprint settings mutations use the same profile-operation locks and closed-profile guards as backup/restore.

Do not increment the current strict database `schema_version` without a deliberate migration strategy: `_initialize()` rejects every value different from `"1"`. An additive table can preserve database readability for metadata rollback, but old application versions will not apply the new fingerprint settings. Browser data downgrade remains a separate issue.

## Existing source integration points

`nevision_win.py` currently has these critical paths:

| Path | Required change |
| --- | --- |
| `Storage._initialize` | Add the identity table transactionally; preserve existing records and schema compatibility policy. |
| `Storage.save_profile/get_profile/list_profiles` | Persist/return the validated identity; avoid creating a new seed on each read/edit; avoid expensive joins or serialized config parsing in every 1,000-row UI refresh. |
| `BrowserLauncher.resolve_browser/_launch_locked` | Resolve the eligible engine, validate its compatibility, and append documented preset arguments before starting. Preserve current proxy checks and process tracking. |
| `ProfileDialog` | Compact selector, locale/timezone when supported, current stable identity, clear ordinary/native engine state. |
| `NeVisionApp.clone_selected` | New identity for a clean clone; no browser-data copying. |
| `Storage._backup_profile_locked` | Include versioned identity in the manifest, not proxy credentials. |
| `Storage._restore_profile_locked` | Validate identity before extraction; preserve it through the database insert and recovery intent. |
| `_journal_restore_profile/_insert_recovered_profile` | Preserve validated identity in power-loss recovery; do not let journal recovery silently reset it. |
| `health_check` and detail pane | Show engine version, preset state and unsupported capabilities rather than a generic protected/green badge. |
| `self_test` | Exercise persistence/edit stability/clean clone/new seed/backup restore/power-loss journal recovery for identities without requiring network access. |
| `build.ps1` allowlisted source snapshot | Include adapter module, presets and engine manifest; PyInstaller must see imports from the snapshot, not an accidental working-tree path. |
| release verifier/provenance/notices | Include engine files, hashes and licenses; ensure `Data` and developer test profiles are excluded. |

Current backup format is `nevision-profile-backup-v1` and its manifest only stores ID/name/group/tags/notes. New optional identity data must be strictly validated. Older v1 backups remain valid and yield explicit ordinary mode. If the native identity cannot be preserved under v1's old-reader behavior, use a new supported format version for native profiles and reject it clearly in unsupported readers. Do not claim old-reader compatibility only because ZIP extraction succeeds.

## Independent fixture and acceptance matrix

Create a small standard-library loopback HTTP server plus static JS fixture. It must have no dependency on the shipped adapter's expected-value generation. Use two distinct origins and a fresh per-run token, and record HTTP headers on the server. A browser report alone cannot prove its own network headers. The server validates received run/profile IDs; reports record engine file hash/version, host system, exact argv without credentials, errors and raw surface values.

Context matrix:

- Main document and early synchronous inline code.
- Same-origin iframe and a different-origin iframe; recursive frame creation after startup.
- Dedicated Worker, SharedWorker where available and service-worker-controlled fetch in supported secure contexts.
- Navigation/reload, reopened process, two simultaneous profiles and clean clone.

Surfaces:

- `navigator.userAgent`, platform, language/languages, hardwareConcurrency, deviceMemory, UA-CH low/high entropy.
- Request User-Agent, Accept-Language and Client Hints, including a second request after Accept-CH negotiation.
- `Intl.DateTimeFormat().resolvedOptions().timeZone` and winter/summer offset to catch incorrect fixed timezone offsets.
- Screen/available screen/colorDepth/pixelDepth/devicePixelRatio; report differences caused by zoom and actual window size explicitly.
- Canvas 2D deterministic text/shapes hash and repeated reads, WebGL vendor/renderer and a deterministic rendered image, WebGL2 where supported.
- Worker OffscreenCanvas where supported; a missing implementation is reported, not treated as a pass.
- Audio rendering hash, fonts/text metrics and WebRTC candidate addresses if the engine advertises coverage. These are optional only when explicitly labelled uncovered.
- Property descriptors/prototype getters/function representation, to detect page shims and cross-context inconsistencies. These checks help assess implementation but cannot prove universal undetectability.

Assertions separate three questions: expected configured value, coherence across supported contexts, and stable/different seeded output. Do not expect canvas hashes to be the same across driver updates or engine-version changes unless the engine explicitly provides that guarantee. Do not mutate machine graphics settings or disable hardware acceleration merely to simplify tests.

## Performance and release gates

Compare the old shell and new shell on the same host with fresh synthetic profiles, before first browser start and after engine readiness. Measure manager cold start, idle working set/CPU, 10/100/1,000-profile search/refresh and browser process startup. Report distribution over repeated runs. Compare the chosen engine with the same upstream Chromium version where available; existing Chrome version and engine version differences must be disclosed.

Config validation and generation should take milliseconds, not require a server call. A preset is read once on launch; no background fingerprint polling. Do not promise manager-size downloads for a self-contained Chromium engine: its real archive/extracted sizes are shown publicly. An optional minimal manager download that fetches the engine once must provide visible download progress, authenticated hashes, retry and offline-ready subsequent launches; it cannot be advertised as immediately self-contained.

Required correctness gates: all existing backup/restore/proxy/long-path/Tk tests; identity lifecycle tests; actual engine fixture; manual ordinary browser behavior; frozen portable self-test; archive completeness and licenses; public-download hash; website/changelog/capability claims consistent with measured coverage. Release only measured support, not blanket promises to pass every anti-bot check.

## Suggested finite implementation cycle

1. Select and prove one eligible Windows native engine and record its exact API.
2. Implement adapter/config and independent native-surface fixture; block incompatible/missing engines.
3. Integrate persisted identity and recovery/clone/backup semantics.
4. Add a compact preset UI and engine readiness/progress flow.
5. Rebrand to NeAntik Win, package the engine/licenses and migration instructions.
6. Run correctness/performance/manual gates, publish source only after secret scan and publish verified binaries/site notes.

If engine evaluation fails, stop at that concrete technical gate with the observed reason; do not rename a JS-injected stock browser as a completed native antidetect engine.

## Implemented experimental adapter checkpoint

`browser_engine.py`, `test_browser_engine.py` and `tools/install-browser-engine.py` now implement the isolated adapter/provisioning stage. They do not change the application launcher or select the experimental engine by default. The pinned adryfish Windows ZIP is version 150.0.7871.186, 193,743,241 bytes, SHA-256 `4d549c326e51ebbabf562fd365eb5380d9d4a81200da2c60f075c688d9a77e03`, as returned by the upstream release API on 2026-10-11.

Public interfaces: `new_identity`, `validate_identity`, `serialize_identity`, `fingerprint_arguments`, `verify_engine`, `EngineResolver.resolve`, `build_native_launch_arguments`, `manifest_from_verified_archive`, `install_verified_archive`. The offline installer refuses an existing target, validates ZIP paths and entries, hashes extracted bytes against the pinned archive, reads native EXE/DLL Windows FileVersion resources, preserves upstream files and atomically publishes the directory with a per-file manifest. It performs no download. The per-process resolver avoids repeated complete hashing while tree stats remain unchanged; this cache is ordinary integrity checking and not protection from an adversary preserving file stats.

The default native identity is Windows/Chrome with its actual pinned engine version, a stable uint32 seed, a selected supported locale/timezone and eight logical processors. Only documented parameters are emitted. Removed GPU metadata arguments are not used. The optional disabled-surface list explicitly represents diminished coverage. An ordinary identity has no fingerprint flags and cannot invoke the native-only launch builder.

20 isolated unit tests pass. They cover canonical identity persistence, nonzero uint32 seed creation, malformed overrides and injection, manifest/version/files integrity, no stock fallback, cache invalidation, archive safety, prefixed and root ZIP structures, atomic provisioning, overwrite refusal and bounded staging cleanup. Zero seeds are deliberately excluded until their actual native behavior is established. Fake fixture binaries mock FileVersion only for unit tests; actual engine capability tests remain a separate release gate.

## Current Chromium source-build feasibility

Read-only host audit on 2026-10-11: C: is NTFS with approximately 244.4 GiB free of 930.4 GiB; physical RAM is 31.1 GiB and the host has 16 logical processors. Git is installed. No compiler/depot-tools commands were found in PATH. Standard Visual Studio installer, VS 2022/2026 and Windows SDK directories were absent; conventional `C:\src\depot_tools` and `C:\src\chromium\src` paths and a workspace depot-tools folder were absent. This is evidence about checked locations, not proof that no custom installation exists anywhere on disk.

The [current official Chromium Windows build instructions](https://chromium.googlesource.com/chromium/src/+/main/docs/windows_build_instructions.md) require Visual Studio 2026 >=18.0.0 with desktop C++ and MFC/ATL components, Windows 11 SDK 10.0.28000.2270 and debugging tools >=10.0.26100.3323. Requirements must be rechecked against the exact selected source tag. Disk/RAM meet the stated minimums, but the required toolchain and checkout have not been provisioned. A full checkout and first build therefore remain substantial new work, not a small manager rebuild. No compiler installation, Chromium checkout or security-setting change was performed by this audit.
