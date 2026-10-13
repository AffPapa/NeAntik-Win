# Bundled Chromium source build (Windows x64)

The portable archive contains unbranded Chromium, **not Google Chrome**. The
browser binary is not stored in Git history. Its exact version, upstream source
commit, build arguments, approved build-only patch SHA-256, license and credits
are recorded in `Engine/Chromium/ENGINE_PROVENANCE.json` inside each archive.

For the first bundled-core releases, the source version is 155.0.8059.40 at
Chromium commit `cfaadc5a132d78e1828635aa8405a499f3e14864`. The checkout
corresponds to the [October 6, 2026 Windows stable announcement](https://chromereleases.googleblog.com/2026/10/stable-channel-update-for-desktop_086471744.html). The checkout
must not contain any changes to browser runtime, Blink, V8 or networking code
for releases through 0.7.1-preview. For the **published 0.8.0–0.8.5 line**,
the separate, reviewable [privacy baseline patch](CHROMIUM_PRIVACY_BASELINE.md)
is allowed and disclosed; do not combine it with the V4b candidate patch. A version
number and a provenance JSON alone do not prove security or byte-for-byte
reproducibility; use the official source and verify the build yourself.

## Published 0.8.6–0.8.7-preview V4b core

The candidate uses the same upstream commit
`cfaadc5a132d78e1828635aa8405a499f3e14864` and the reviewed
[`chromium-native-persona-prototype-v4b.patch`](chromium-native-persona-prototype-v4b.patch)
(81,030 bytes; SHA-256
`bba02390999c33bcf6097625c03093022ed534c316184462cc8468efbc79b708`).
Do **not** stack it with the baseline or held V3 runtime patch. The separate
build-only compatibility patch remains required and is validated independently.
The candidate's `chrome.exe` SHA-256 is
`751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`;
its `chrome.dll` SHA-256 is
`6762cf6ead3b829b481fde9540069cc709c9de3a211c738856190850a6928413`.
The DLL hash is essential: the EXE hash alone does not distinguish the stock,
V3 and V4b cores. Two staging runs produced 39 byte-identical runtime files.
Native unit tests (6 + 21 + 3), 12/12 two-site/restart and 6/6 context cases
(11/11 checks) passed on one Windows 11 host. These do not replace portable
archive/public-download tests, external DNS/UDP/IPv6/TURN observation or
second-machine QA, all still open. See the [candidate audit](NATIVE_PERSONA_PROTOTYPE_AUDIT.md).

## Unreleased 0.8.8-preview V5 candidate

The [V5 patch](chromium-native-persona-prototype-v5.patch) (84,612 bytes;
SHA-256 `0c592ca18304823faf8f0e2534619c5f7b458072e451ede81eb528a2b8c76d22`)
replaces V4b and is applied to the same pinned Chromium source commit. It
removes the Canvas session key from renderer argv and sends it via early Mojo
initialization. Candidate `chrome.dll` SHA-256 is
`9d0943446e0cbe405f82286ce46c03ad8e928f7b8e46d3ed33082dce2f544075`.
Native parser tests passed 21/21, Canvas unit tests 6/6, and local
main/frame/worker + BrowserContext/session-rotation checks 7/7. Two staging
runs produced 39 byte-identical files. These results precede portable-package
and public-download verification; they do not establish general anonymity.

## Build-only dependency exception

The Chromium `DEPS` entry
`src/third_party/updater/chrome_win_x86/cipd` references an old updater test
fixture that Windows Defender blocks as potentially unwanted software on the
release workstation. This fixture is not used by the unbranded `chrome` target.
Apply the reviewed [`chromium-build-compat.patch`](chromium-build-compat.patch)
to the pinned checkout before `gclient sync`. It sets only that entry's
`condition` from `checkout_win` to `False` and makes the MIDL adjustment below.
Do not disable Defender or suppress its alert. The exact source diff hash is
supplied to the staging command and embedded in the receipt.
For this build, the combined `git diff HEAD --binary -- DEPS
build/toolchain/win/midl.py` SHA-256 is
`fcadf05210669f23925f165d28693e7713f9246c6d382ba7ba24289c4ce81079`.

On this workstation, MIDL-generated typelib name hashes also differ from
Chromium's checked-in Windows output because Windows applies the user's locale
despite `/lcid 1033`. The allowed `build/toolchain/win/midl.py` patch
normalizes only the derived typelib name-hash metadata to the typelib header's
locale and makes the generated-output comparison non-shallow. It does not
change browser runtime code. The release checkout must have no other tracked
changes. This compatibility patch is intentionally visible in the provenance;
it is not described as an upstream-unmodified source tree.

## Procedure

Use the [official Chromium Windows build instructions](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/windows_build_instructions.md) and a sufficiently large
NTFS volume. This build used the local Visual Studio 2026 C++ toolchain
14.51.36231 and Windows SDK. Install the required tools before syncing.
Check out the pinned commit in a separate directory; never modify a user's
existing browser checkout. Configure `.gclient` and apply the patch, then:

```powershell
git apply C:\path\to\NeAntik-Win\docs\chromium-build-compat.patch
```

Run `git apply` from the Chromium source checkout and replace the example
absolute path with the location of your NeAntik source repository. Point
`DEPOT_TOOLS_WIN_TOOLCHAIN=0` and `vs2026_install` at the locally installed
toolchain per Chromium's Windows build instructions; the exact paths are
machine-specific. Then:

```powershell
gclient sync --nohooks --jobs 8
gclient runhooks
gn gen out/NeAntik
autoninja -C out/NeAntik -j 8 chrome
```

The `out/NeAntik/args.gn` contents for this build are:

```gn
is_debug = false
is_component_build = false
is_official_build = false
is_chrome_branded = false
target_cpu = "x64"
symbol_level = 0
blink_symbol_level = 0
v8_symbol_level = 0
use_remoteexec = false
```

Before staging, inspect `git diff HEAD` and calculate the SHA-256 of the raw
`git diff HEAD --binary -- DEPS build/toolchain/win/midl.py` output. Pass that
hash as `--approved-build-patch-sha256` to
`tools/prepare_source_built_chromium.py`, along with `--source-root`,
`--build-root`, `--commit`, `--version` and a new `--output` directory. For
0.8.0–0.8.5, additionally pass the exact hash and file of the separate
[privacy baseline patch](CHROMIUM_PRIVACY_BASELINE.md) as
`--approved-privacy-patch-sha256` and `--privacy-patch-file`. For the 0.8.6
candidate, supply the exact V4b patch through
`--approved-native-patch-sha256` and `--native-patch-file` instead; do not
pass the baseline privacy-patch arguments at the same time. The staging tool
rejects changed tracked **and untracked** files outside the approved build and privacy inputs,
and requires the published privacy patch bytes to equal the approved diff,
checks the pinned commit and version, curates runtime files, and extracts
`chrome://credits` from the staged browser. A per-run Chromium theme URL is
removed from the offline credits copy; two local staging runs of the same
source/build input produced matching hashes for all 39 staged files. The
runtime set includes the
versioned Windows Side-by-Side manifest and unmodified x64 Visual C++
redistributable DLLs. The 0.5.1 portable stage retains only `en-US`, `ru` and
`th` Chromium UI packs; other locales fall back to English. This reduces the
ZIP without modifying or repacking the Chromium DLL. On NTFS, Windows AppContainer children need read/execute
access to engine files; staging and the portable launcher grant that access
only under `Engine/Chromium`, never private `Data/`. Then run `build.ps1
-EngineDirectory <staged-engine-directory>` and verify the resulting ZIP with
`tools/verify-release-archive.ps1`.

Chromium itself does not auto-update in this portable distribution. The team
must rebuild and publish a new version promptly when upstream security updates
arrive. Never claim that a proxy or this build guarantees anonymity or that a
snapshot/development build is a stable security release.
