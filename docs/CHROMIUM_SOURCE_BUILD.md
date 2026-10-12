# Bundled Chromium source build (Windows x64)

The portable archive contains unbranded Chromium, **not Google Chrome**. The
browser binary is not stored in Git history. Its exact version, upstream source
commit, build arguments, approved build-only patch SHA-256, license and credits
are recorded in `Engine/Chromium/ENGINE_PROVENANCE.json` inside each archive.

For the first bundled-core releases, the source version is 155.0.8059.40 at
Chromium commit `cfaadc5a132d78e1828635aa8405a499f3e14864`. The checkout
corresponds to the [October 6, 2026 Windows stable announcement](https://chromereleases.googleblog.com/2026/10/stable-channel-update-for-desktop_086471744.html). The checkout
must not contain any changes to browser runtime, Blink, V8 or networking code
for releases through 0.7.1-preview. Beginning with the 0.8.0-preview proposal,
the separate, reviewable [privacy baseline patch](CHROMIUM_PRIVACY_BASELINE.md)
is allowed and disclosed; no other runtime changes are allowed. A version
number and a provenance JSON alone do not prove security or byte-for-byte
reproducibility; use the official source and verify the build yourself.

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
0.8.0-preview, additionally pass the exact hash and file of the separate
[privacy baseline patch](CHROMIUM_PRIVACY_BASELINE.md) as
`--approved-privacy-patch-sha256` and `--privacy-patch-file`. The staging tool
rejects changed tracked files outside the approved build and privacy inputs,
checks the pinned commit and version, curates runtime files, and extracts
`chrome://credits` from the staged browser. The runtime set includes the
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
