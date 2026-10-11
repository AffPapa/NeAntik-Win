# Native Canvas patch 003: review and validation contract

Exact base: Chromium `155.0.8059.40`, commit `cfaadc5a132d78e1828635aa8405a499f3e14864`. Patch dependency: 001 immutable per-process config in `blink::neantik`, `GetFingerprintConfig()` and `MixFingerprintSeed(seed, domain, value)` from `third_party/blink/public/common/fingerprinting/neantik_fingerprint.h`.

Status: patch drafted; `git apply --check --verbose` passed against downloaded exact-commit source files. **Not compiled, not runtime-tested, no claim of undetectability.** Application capability flags must not claim observed protection based on this source review.

## Concrete behavior

The new shared native function projects each opaque sRGB uint8 RGB channel's low bit to a seed/absolute-coordinate bit. Maximum change is one integer value per channel. Alpha, hidden RGB in transparent pixels, partially transparent pixels and row padding remain unchanged. Applying the projection twice at the same coordinates is idempotent, unlike additive per-call random noise. No per-read random state or JS override exists. Same seed/same coordinates uses the same pure fixed-width helper in windows and worker renderers.

`getImageData` transforms its already-owned returned buffer after successful upstream readback. Negative/subregion coordinates use absolute pixel positions and zero outside-canvas pixels remain zero. HTML `toDataURL`/`toBlob` and Offscreen `convertToBlob` call the same private CPU snapshot helper before serialization. The helper reads unpremultiplied RGBA data into a separate buffer; it never modifies an image's shared pixels or drawing backing store. With no active config, the helper returns the existing snapshot without allocation. The asynchronous blob encoder's own scheduling and ownership stay unchanged because it receives an ordinary immutable software image.

Scope is deliberately narrow: default sRGB opaque uint8 Canvas2D output. Float16, wide gamut/HDR, partially transparent colors, WebGL/WebGPU, text metrics and audio are not protected by this patch. It does not normalize OS font/GPU rendering differences. Profile-global seed is not origin-scoped. Arbitrary coordinate translations, scaling or lossy JPEG/WebP conversion cannot promise exact pixel equivalence. A page can probe the presence of a projection; native implementation alone does not make a fingerprint defense undetectable. PNG decoded pixels at the same coordinates and already-projected `putImageData` round trips are the included contract.

## Tests shipped in the patch

Five C++ tests are added to `blink_platform_unittests_sources`: repeat/idempotence and distinct seeds; absolute subregion parity; transparency/alpha/padding; logical RGBA/BGRA parity; float16/premultiplied exclusions. They exercise the explicit-seed pure transform without relying on process-global state initialization.

One Blink web fixture `neantik/canvas-readback.html` adds five browser tests: repeated readback/subregions; `putImageData`/clear; decoded PNG `toDataURL` and `toBlob`; Offscreen main-thread export; dedicated-worker Offscreen export/repeat/window parity. These tests must run in a compiled patched shell with the seed passed to both browser and renderer by 001. They can also pass on stock Chromium, so passing the semantic tests alone is not proof of seed activation. Compare seed A/A and A/B raw opaque pixel output separately against a baseline build.

Required compiled verification commands, adapted to the actual build output folder:

```powershell
autoninja -C out/NeAntik blink_platform_unittests content_shell chrome
out/NeAntik/blink_platform_unittests.exe --gtest_filter=NeAntikCanvasReadbackTest.*
python third_party/blink/tools/run_web_tests.py --build-directory out --target NeAntik --additional-driver-flag=--neantik-fingerprint-seed=123 neantik/canvas-readback.html
```

Run the web-test tool's local `--help` before execution to confirm flags at this pinned revision. Additional release gates: alpha-false canvases, CPU/GPU readback, same-seed renderer restart, seed A/B response, OOPIF workers, tainted-canvas SecurityError, zero dimensions, context loss, open layers, P3/float16 unchanged behavior, put/draw/copy semantics, and 4K/large-canvas time/memory compared to upstream. Until these gates and a real Windows executable pass, the patch remains unverified implementation source.

## References and license handling

Reviewed exact Chromium sources: `base_rendering_context_2d.cc`, `html_canvas_element.cc`, `offscreen_canvas.cc`, `image_data_buffer.cc`, `canvas_async_blob_creator.cc`, `unaccelerated_static_bitmap_image.h`, platform `BUILD.gn`, and `ui/gfx/skia_span_util.h` under the exact commit.

Reviewed prior art: [adryfish148 patch012](https://github.com/adryfish/fingerprint-chromium/blob/148.0.7778.215/patches/extra/fingerprint/012-canvas-get-image-data.patch) and [patch013](https://github.com/adryfish/fingerprint-chromium/blob/148.0.7778.215/patches/extra/fingerprint/013-canvas-toDataURL.patch). Those older patches use different upstream noise hooks/switches and are not applied. This implementation uses a new projection and shared-copy API; no ungoogled dependency or prior shuffle implementation is copied. Existing Chromium/Blink copyright and BSD notices remain untouched in all edited upstream files. Added files use the Chromium source-tree BSD license convention; this does not select a license for the launcher application's own source.
