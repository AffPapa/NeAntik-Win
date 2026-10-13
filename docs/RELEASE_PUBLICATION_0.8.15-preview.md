# NeAntik Win 0.8.15-preview — public release evidence

Status checked 2026-10-14: the GitHub prerelease is public and the live Site
serves the same archive. The annotated tag `v0.8.15-preview` resolves to the
binary/source commit below. This report separates local tests, public asset
integrity, and live Site verification; none establishes full anonymity.

An earlier local ZIP with SHA-256 `8e3d1ff6…dbbab7` was superseded before
publication. It was not attached to the public release. Only the verified ZIP
below is the download for tag `v0.8.15-preview`.

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
- Exact bundled Chromium engine loopback proxy-loss/recovery gate — **PASS**,
  10/10 checks. `chrome.exe` SHA-256
  `751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`;
  `chrome.dll` SHA-256
  `9d0943446e0cbe405f82286ce46c03ad8e928f7b8e46d3ed33082dce2f544075`.
  Before proxy loss, the loopback target was reached through the proxy; during
  loss, no target request escaped and Chromium stayed alive; after recovery,
  the same process routed through the proxy again. NetLog showed TCP only to
  `127.0.0.1` and zero UDP. The harness did not launch the NeAntik GUI and this
  does not prove external DNS, IPv6, TURN or public-network routing.
- The exact released Chromium also passed the synthetic profile
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

## Public GitHub release

- GitHub Release: [v0.8.15-preview](https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.15-preview), `draft=false`, `prerelease=true`.
- The annotated tag resolves to binary/source commit
  `5434718dd14a5ea0edc20c440c801a873c9fbcf4`.
- Three uploaded assets report state `uploaded`; GitHub's ZIP digest and size
  match the local archive. A fresh public download also matched the `.sha256`
  sidecar, manifest version/source/hash, size (262,401,905 bytes), and SHA-256
  `fd9eedf2b9f6b9f3b42b51eb5ce29608e41b165c7ec2d282e17926c4f2b44ead`.
- Sidecar file: 106 bytes, SHA-256
  `afb2ed2013047bcd5e3daccb12f1ebea74b2458d6918bf6c3aaa68cb7b577114`.
- Manifest file: 197,363 bytes, SHA-256
  `2f3fbb5995b696da172bc21378c5ea192eeb34998ff87e13942c232287f6bbeb`.

## Production Site verification

- Source commit `28e90eb18114c43726d403927068cdd846c5fef1` passed TypeScript
  typecheck and production build. Saved Site version 49 contains that commit
  and the packaged archive; deployment completed with status `succeeded`.
- Live `https://nevision-win.mail782861.chatgpt.site/release.json` reports
  version 0.8.15-preview, source commit `5434718…`, ZIP size 262,401,905 bytes,
  and the exact SHA-256 above. Live landing page returned HTTP 200 and contains
  the current version/download. GitHub ZIP HEAD returned HTTP 200 with the
  expected Content-Length.

## Remaining verification gaps

Manual GUI, Windows 10/ARM64, a consumer second PC/account, external DNS/IPv6/
UDP/TURN/public-network routing, and broad site compatibility remain
**NOT RUN** for this release. The preview is unsigned and Chromium does not
auto-update. The optional experimental fingerprint-related behavior remains
limited; this release does not establish anonymity or comprehensive
anti-detection.
