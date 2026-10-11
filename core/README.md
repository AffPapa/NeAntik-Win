# NeAntik native core: current-source patch contract

Status: **patches001–011 are source-applied and all31 exact postimages checked**. The first full incremental compile stopped on Clang's `-Wunsafe-buffer-usage` for a raw three-element Canvas channel array. Patch011 replaces it with `std::array` without weakening warnings or changing Canvas behavior; the corrected source now passes the exact source gate. The incremental build has not yet been rerun, and no final EXE/runtime release checks exist. Upstream Chromium does not support these switches without this patch series.

Files under `core/native/` are authored inputs for the early patch stages, not a standalone mirror of the final Chromium postimage. Later patches deliberately refine that code (for example, patch008 narrows the Windows155 device-memory values); use the fully applied, hash-verified source checkout as the release contract. Reading an authoring input file alone does not establish the final runtime behavior.

Supplementary009 is reviewed and **applied to the source checkout**, not yet verified in a compiled browser. It pins Chrome website-frame WebRTC routing to `disable_non_proxied_udp` only when an immutable native persona and a nonempty explicit `--proxy-server` are both present. Matching per-URL overrides are cleared in renderer preferences, without writing stored preferences or OS settings. This is not a network kill-switch, protection for privileged standalone extensions, or a guarantee about DNS, proxy bypass rules, TCP/TURN, or every UDP API. Ordinary and native unproxied profiles retain upstream behavior. Source-contract tests and owned socket-fixture tests are not compiled-browser evidence.

The user selected a current, own Chromium core on 2026-10-11. The external Chromium150 prototype is not the chosen release implementation. Its initial loopback fixture runs timed out, so no positive fingerprint capability was proved from that binary.

## Exact upstream pin

Chromium tag `155.0.8059.40`, commit `cfaadc5a132d78e1828635aa8405a499f3e14864`.

- [Official source tag](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.40)
- [Exact Gitiles ref](https://chromium.googlesource.com/chromium/src/+refs/tags/155.0.8059.40?format=JSON)
- [Mirror ref API independently checked](https://api.github.com/repos/chromium/chromium/git/ref/tags/155.0.8059.40)
- [Official Windows Stable version history](https://versionhistory.googleapis.com/v1/chrome/platforms/win/channels/stable/versions/155.0.8059.40/releases)

Every source-file link below targets that exact tag, and each path was fetched successfully during this research. Build/toolchain pinning and guarded commands live in `tools/native-core/`, maintained separately.

## Capability contract

One immutable validated persona per browser profile/process. The first authored native interface uses small validated switches instead of sandboxed JSON file access:

```text
--neantik-fingerprint-seed=<nonzero uint64 decimal>
--neantik-hardware-concurrency=<integer 1..64>
--neantik-device-memory=<2|4|8|16|32>  # Windows155 scope after008
--neantik-timezone=<IANA identifier>   # optional, requires seed
--neantik-core-info=<output JSON file>  # capability query; exits before navigation
```

Seed activates persona mode; omitted CPU and memory are stable 8/8 defaults. CPU/memory/timezone flags without seed, invalid values and any unknown `neantik-` switch fail closed with exit 78. Query without output path fails closed; query file write failure exits 74. The earlier conceptual `--neantik-fingerprint-config` is rejected, not silently accepted. Timezone syntax is bounded ASCII at argument validation; ICU validates system IANA identifiers at PreSandboxStartup after ContentMainRunner initializes ICU. Unknown well-formed zones exit 78 before pages. Omitted timezone retains the host zone; Windows OS settings are not changed. Locale uses stock Chrome `--lang` and `--accept-lang`. OS/platform/UA/CH retain genuine Windows/current Chromium defaults.

Browser startup validates arguments before navigation. The renderer launch path forwards the four persona switches before page/worker contexts exist. Each process parses a const function-local snapshot once with C++ thread-safe initialization. Sandboxed children do not read persona files. Getters on worker threads read immutable state; there is no main-thread-only preference lookup, polling or repeated parsing. The browser does not forward the capability-output path into renderer processes.

The runtime capability manifest must distinguish `implemented`, `compiled`, `observed`, `unsupported` and `deferred`. UI cannot infer support from accepted command-line arguments: stock Chromium silently ignores many unknown switches.

| Capability | Native target at exact tag | Required invariant | First-cycle scope |
|---|---|---|---|
| CPU | [navigator_concurrent_hardware.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.40/third_party/blink/renderer/core/frame/navigator_concurrent_hardware.cc) | Same explicit CPU value in window/iframes/dedicated/shared/service workers | Implement shared accessor with immutable state |
| Device memory | [navigator_device_memory.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.40/third_party/blink/renderer/core/frame/navigator_device_memory.cc), [approximated_device_memory.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.40/third_party/blink/common/device_memory/approximated_device_memory.cc) | JS and device-memory Client Hints agree, secure-context rules unchanged | Windows155 discrete2/4/8/16/32 scope; no Android limit mixture |
| UA/Client Hints | [user_agent_utils.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.40/components/embedder_support/user_agent_utils.cc), [client_hints.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.40/content/browser/client_hints/client_hints.cc) | HTTP UA/CH and JS agree; actual core major/full version; genuine Windows desktop architecture | Central metadata construction, no arbitrary old-version pool |
| Window/worker navigator | [navigator_base.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.40/third_party/blink/renderer/core/execution_context/navigator_base.cc), [worker_navigator.h](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.40/third_party/blink/renderer/core/workers/worker_navigator.h), [navigator.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.40/third_party/blink/renderer/core/frame/navigator.cc) | Common context UA/platform model, including early script reads | Verify shared execution-context paths; preserve Windows `Win32` default |
| Child state | [render_process_host_impl.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.40/content/browser/renderer_host/render_process_host_impl.cc) | State present before page/worker creation, OOPIF/process restart consistent | Explicit propagation plus tests; no unreviewed unrestricted forwarding |
| Timezone | [timezone_controller.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.40/third_party/blink/renderer/core/timezone/timezone_controller.cc) | Date offsets and Intl/ICU agree, DST correct, notifications reach workers | Validated override through native ICU/V8 path; OS timezone stays unchanged |
| Canvas2D readback | [base_rendering_context_2d.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.40/third_party/blink/renderer/modules/canvas/canvas2d/base_rendering_context_2d.cc) | Deterministic seed; repeated reads, subregions, canvas copies and serialization consistent | Shared native implementation and semantic tests, not per-call random noise |
| Canvas export | [html_canvas_element.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.40/third_party/blink/renderer/core/html/canvas/html_canvas_element.cc), [image_data_buffer.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.40/third_party/blink/renderer/platform/graphics/image_data_buffer.cc) | Decoded toDataURL/toBlob pixels equal getImageData for supported formats; tainted errors unchanged | Audit common image encoding path and async blob path together |
| OffscreenCanvas | [offscreen_canvas.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.40/third_party/blink/renderer/core/offscreencanvas/offscreen_canvas.cc) | convertToBlob and worker readback match main-thread canvas | Same native pixel/seed algorithm, no window-only override |
| Screen/fonts/GPU/audio | Actual Windows OS/backend defaults initially | No impossible Windows/macOS/GPU mixture; no fabricated support | Deferred until coherent native implementations and tests exist |

Exact Chromium155 Windows source quantizes and clamps deviceMemory to2–32GB. Its Android-only branch uses1–8GB, not a Windows compatibility branch. Supplementary008 therefore rejects0.25/0.5/1 in both native CLI and application identity validation. Existing invalid unreleased drafts fail explicitly: no silent clamp, seed rotation, database blob rewrite or ordinary-browser fallback occurs. UI presets4/8/16 remain valid. Chromium148-era values are not the current Windows contract.

CPU caveat: exact155 `NavigatorBase::hardwareConcurrency` calls the native getter and then the stock Inspector `ApplyHardwareConcurrencyOverride` probe. Explicit attached CDP/DevTools emulation can therefore supersede the profile count per target. This is not a website-accessible setting and is not enabled by default, but unconditional CPU immutability against developer emulation is not promised. Real execution performance, GPU and fonts remain those of the host; exposed counts do not prove undetectability.

## Authored patch series and remaining stages

- `patches/0001-native-seed-state.patch`: public Blink common helper, configuration validation, immutable snapshot, specified domain-separated uint64 seed mixing, Chrome startup validation and capability handshake, renderer switch propagation, 10 authored GoogleTests registered in `blink_common_unittests`.
- `patches/0002-native-cpu-memory.patch`: shared native hardwareConcurrency getter and ApproximatedDeviceMemory getter, used by NavigatorDeviceMemory and browser HTTP device-memory Client Hints. Capability handshake reflects these two implementations.
- `patches/003-canvas-readback.patch`: independently authored opaque sRGB8 pixel transformation and HTML/Offscreen export; see `CANVAS_PATCH_NOTES.md` for explicitly deferred formats.
- `patches/004-native-timezone.patch`: immutable IANA persona, semantic ICU validation after ICU initialization, explicit renderer propagation, native TimeZoneController initialization and protection against host/CDP timezone replacement. Four additional GoogleTests and seven Blink Date/Intl/DST context cases are authored, not executed.
- `patches/timezone-chain-provenance.json`: final ordered001/002/003/004 exact-source apply evidence and every modified/new postimage SHA256. It is not compile/runtime evidence.
- `patches/0005-omit-branded-updater-test.patch`: excludes only a branded old-updater x86 test fixture from this unbranded source build, without disabling endpoint protection.
- `patches/006-core-capability-scope.patch`: handshake exposes exact source commit and deliberately granular opaque sRGB8 Canvas capability, not generic all-format coverage. Adds three C++ no-argument/unknown-switch/query regressions. `capability-chain-provenance.json` records all six patch hashes and27 final postimages; neither file proves runtime behaviour.
- `patches/007-deterministic-midl-name-hashes.patch`: controlled unbranded Windows build fix for deterministic MIDL name hashes; no OS locale change.
- `patches/008-windows155-memory-values.patch`: limits validated persona memory to Windows1552/4/8/16/32; adds C++ rejection/no-clamp regression. The shared browser/renderer JS/HTTP memory getter is unchanged. `memory-chain-provenance.json` records scratch verification and controlled actual checkout application with all28 final postimages. It does not prove compilation or runtime behaviour.
- `patches/009-native-proxy-webrtc-policy.patch`: source-applied Chrome website-frame routing policy, three authored Chrome unit tests, and the narrow `webrtc_non_proxied_udp_proxied_webframes` source capability. `webrtc-candidate-provenance.json` preserves the historical disposable post008 evidence; `webrtc-chain-provenance.json` records controlled actual application and all31 final postimages, not compilation or runtime success. The real Chrome harness requires positive unproxied STUN controls, proxy-routed page observations and absence of owned UDP for the protected case before release.
- `patches/010-define-core-info-file-path.patch`: adds only `base/files/file_path.h` in the native helper that uses `GetSwitchValuePath`. The authored generator template has the same include. `file-path-chain-provenance.json` is historical evidence for the 10-patch source state before011; it does not claim a successful final compile or runtime check.
- `patches/011-canvas-safe-channel-index.patch`: replaces the three-element raw channel array with `std::array` after the first incremental compile correctly rejected unsafe raw-buffer indexing. It preserves the same fixed channel mapping and strict compiler warnings. `canvas-buffer-safety-chain-provenance.json` records the 11-patch source state and explicitly leaves compilation/runtime unverified until the incremental build and browser QA pass.
- `native/` contains original authored helper and test source used by `tools/native-core/generate-seed-patches.py`. That generator fetches exact immutable Gitiles sources, rejects changed/repeated replacement anchors, generates unified patches, and checks/applies the sequence in a disposable source fixture. It does not touch the actual Chromium checkout.
- `patches/seed-patch-provenance.json` records patch hashes, exact baseline source hashes and apply evidence. **Compilation and runtime checks are explicitly not run.**

The native capability handshake reports compiled-source stages, not independently observed behaviour. The launcher must require a binary that produces this response and verify installed artifact provenance; a copied JSON file on disk is not native proof. Further patches must update capability fields only for implemented native surfaces.

1. **Configuration and state — authored:** validated CLI, immutable seed state, GN registration, browser initialization and renderer propagation. Negative GoogleTests cover invalid seed/CPU/memory, orphan override, unknown switch and missing handshake path. No profile browsing begins after config rejection. Compile and worker race tests remain.
2. **CPU/memory — authored:** shared native accessors; memory hints and JS use the same implementation. Compile and test main, frames and all worker types under concurrent process creation and crashes/restarts.
3. **UA/CH:** one actual-version metadata source, platform restricted to genuine Windows desktop for this cycle. Test first navigation before Accept-CH, second navigation with high entropy hints, fetch, iframe and worker request headers.
4. **ICU timezone:** validate IANA value once, initialize before V8 context observations, preserve dynamic notification behavior without letting host timezone overwrite profile override. Test winter/summer, UTC, half-hour offsets and worker creation races.
5. **Canvas/Offscreen:** design one deterministic transformation across readback and export. Keep transparent pixels/alpha, dimensions, colour space, float16/sRGB semantics and taint checks intact. Do not cumulatively mutate backing pixels on each read. Audit drawImage/copy/readback consistency; readback-only noise that breaks these relationships fails the gate. Coordinate absolute pixel positions for subregions. JPEG/WebP lossy exports require format-aware comparisons rather than exact compressed bytes.
6. **Capability handshake/build provenance:** expose version/schema/capability manifest that the launcher can verify locally; actual native implementation is required before claiming any feature. Include source commit, patch hashes, dependency pins and all third-party notices.

Porting published adryfish148 patches directly is not this series. In155, NavigatorBase is under `core/execution_context/`, and worker state/UA/memory semantics need current-source review. Old CDP stealth, fakeShadowRoot and webdriver suppression are outside this minimal human GUI contract. The prior patch source and BSD notices may be used as references while retaining attribution, but apply success alone does not prove behaviour.

## Validation and performance

Timezone tests require an actually patched `content_shell` and explicit driver flags (no fake upstream suite owner was added):

```text
python third_party/blink/tools/run_web_tests.py --additional-driver-flag=--neantik-fingerprint-seed=123456 --additional-driver-flag=--neantik-timezone=Europe/Berlin http/tests/neantik/timezone.html
blink_common_unittests.exe --gtest_filter=NeAntikFingerprintTest.*
```

Expected timezone observations include winter UTC offset -60 minutes, summer -120, and the March2026 Berlin DST transition. Service-worker registration activation is awaited directly, since the test page is outside the worker's resources scope. Any timeout is failure. Running these cases under an unconfigured host zone is not proof. Core-info after stage006 has `engine_id:"neantik-chromium"`, `schema:1`, actual native `version`, exact `source_commit`, `capability_evidence:"compiled-source-only"`, and `compiled_stage:6`. Capabilities `stable_seed`, `hardware_concurrency`, `device_memory`, `timezone`, `canvas_opaque_srgb_uint8` are true. Generic `canvas`, `canvas_float16`, `canvas_display_p3`, `canvas_translucent` remain false. These report implemented source scope only once an EXE is actually compiled; trusted manifest source/patch hashes and independently observed APIs, not this self-report alone, authorize product release.

Current external150 fixture is `tools/test_native_fingerprint.py`, tied to a pinned third-party ZIP. It is not yet a test of this custom core. A custom-core adapter must consume its own release manifest and config interface, not bypass the old pinned checksum check.

Mandatory gates: C++ unit tests for schema/seed/transform; relevant Blink web tests; actual compiled EXE; A/A restart and A/B identity; frame/worker parity; HTTP headers; decoded canvas exports and Offscreen; headed Windows tabs/history/downloads/extensions; proxy fail-closed/WebRTC policy; backup/restore persona continuity. Any timeout or unsupported API appears in raw results and cannot count as passed coverage.

Launch/idle measurements must compare the same build mode and web workload. UI remains lightweight and native core runs directly; no browser automation server in production. Seed derivation happens once; getters remain constant-time. Pixel work is proportional to requested data, and large-canvas memory/CPU must be measured. No startup network needed for persona generation. Limits are enforced so a configuration cannot request unbounded allocations.

The guarded driver must consume the exact authored patch series and verify hashes before product build. An explicit upstream-baseline build only proves the toolchain. A successful baseline EXE must not be published as NeAntik fingerprint capability. Exact-source `git apply --check` is a textual verification and does not replace C++ compilation, GN dependency checks, GoogleTests or real browser measurements.
