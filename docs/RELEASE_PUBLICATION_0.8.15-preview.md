# NeAntik Win 0.8.15-preview — candidate evidence (not published)

Status checked 2026-10-14: the portable candidate is locally built and tested,
but **not publicly released**. The current GitHub Release endpoint returns
HTTP 404 for `v0.8.15-preview`; the public Site still serves 0.8.14-preview.
Do not describe this candidate as available for download.

**This exact ZIP is now superseded:** after it was built, `main` gained a
profile-root junction/reparse guard before Chromium launch. That fix is covered
by source tests and is included in the rebuilt candidate below. Do not publish
the earlier hash `8e3d1ff6…dbbab7`; the new archive is the only candidate to
consider for release.

## Source and artifact

- Binary/source commit: `5434718dd14a5ea0edc20c440c801a873c9fbcf4` on `main`.
- GitHub Actions CI run [38463083866](https://github.com/AffPapa/NeAntik-Win/actions/runs/38463083866)
  completed with conclusion `success` on that exact commit.
- Local portable ZIP:
  `NeAntikWin-portable-v0.8.15-preview.zip`, 262,401,905 bytes,
  SHA-256 `fd9eedf2b9f6b9f3b42b51eb5ce29608e41b165c7ec2d282e17926c4f2b44ead`.
- Packaged `NeAntikWin.exe` SHA-256:
  `6392a400aea47912792ac266cf9cf9044acc7a7ec7fce0fc82cce7e94fbecef2`.
- Candidate manifest says unsigned (`NotSigned`); Windows 10 and ARM64 are
  unverified. Experimental fingerprint-related behavior remains partial and
  must not be described as anonymity or comprehensive anti-detection.

## Local evidence at the binary source commit

- Python unittest suite: 262 tests, 3 skips — **PASS**.
- Source `--self-test` — **PASS**.
- Release-tool tests: 55 checks — **PASS**.
- Public repository guard: 208 files — **PASS**.
- Portable archive verifier: 1,066 files — **PASS**.
- Packaged executable `--self-test` — **PASS**.
- Exact candidate Chromium engine loopback proxy-loss/recovery gate — **PASS**,
  10/10 checks. `chrome.exe` SHA-256
  `751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`;
  `chrome.dll` SHA-256
  `9d0943446e0cbe405f82286ce46c03ad8e928f7b8e46d3ed33082dce2f544075`.
  Before proxy loss, the loopback target was reached through the proxy; during
  loss, no target request escaped and Chromium stayed alive; after recovery,
  the same process routed through the proxy again. NetLog showed TCP only to
  `127.0.0.1` and zero UDP. The harness did not launch the NeAntik GUI and this
  does not prove external DNS, IPv6, TURN or public-network routing.
- The exact extracted candidate Chromium also passed the synthetic profile
  storage/permissions/backup/clone gate: 21/21 assertions over seven real
  visits. A first attempt omitted the AppContainer read/execute ACL because
  this harness launches Chromium directly rather than through the product's
  normal launcher; after matching the launcher's ACL setup on `Engine/Chromium`
  only, the single retry passed. The ZIP bytes were unchanged. Detailed scope:
  [P3.1 profile isolation evidence](PROFILE_ISOLATION_2026-10.md).
- The rebuilt source rejects a linked/reparse-point `Data`, `Profiles` or
  profile root before browser selection/pinning/process creation. A real
  Windows junction regression test passed; it confirms this one launch path,
  not protection from same-user malware or a concurrent path-swap race.
- Manual GUI, Windows 10, second consumer PC/account, external DNS/IPv6/UDP/TURN,
  and broad site compatibility — **NOT RUN** for this candidate.

## Site state

Site source for 0.8.15 was pushed at
`32a909d9d78b264a4df505feeb4fa374c3f9ad04`; typecheck and build passed and
Site version 48 was saved for the superseded ZIP. It must not be deployed or
reused. Live `release.json` still
reports the 0.8.14 ZIP (262,397,107 bytes; SHA-256
`44fef435ec5a46fa52d8441ac7e6d951e0577f611a16a21628a4a33ddcf61284`).
After the new immutable GitHub asset is created and hash-verified, update the
site source to this new hash, save a fresh Site version, and deploy that version.

## Remaining publication gates

1. Create immutable GitHub prerelease `v0.8.15-preview` at the binary source
   commit and upload the ZIP, `.sha256` sidecar, and manifest.
2. Download the public ZIP and sidecars again; compare bytes, SHA-256, manifest,
   and source commit with this record.
3. Deploy the saved Site version only after gate 2 passes.
4. Verify live `/release.json`, page download link, HTTP response and downloaded
   asset size/SHA-256. Then update this record from candidate evidence to the
   exact publication evidence.
