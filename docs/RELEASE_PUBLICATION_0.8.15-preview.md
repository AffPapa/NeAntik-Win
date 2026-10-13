# NeAntik Win 0.8.15-preview — candidate evidence (not published)

Status checked 2026-10-14: the portable candidate is locally built and tested,
but **not publicly released**. The current GitHub Release endpoint returns
HTTP 404 for `v0.8.15-preview`; the public Site still serves 0.8.14-preview.
Do not describe this candidate as available for download.

## Source and artifact

- Binary/source commit: `ec0de9cad0f26cb9aec90ef6cbbb59df7174ff23` on `main`.
- GitHub Actions CI run [38460588326](https://github.com/AffPapa/NeAntik-Win/actions/runs/38460588326)
  completed with conclusion `success` on that exact commit.
- Local portable ZIP:
  `NeAntikWin-portable-v0.8.15-preview.zip`, 262,397,892 bytes,
  SHA-256 `8e3d1ff6a1cd99fedf3e11ca7095ed61acd78160a6ade3af4c3d2f3396dbbab7`.
- Candidate manifest says unsigned (`NotSigned`); Windows 10 and ARM64 are
  unverified. Experimental fingerprint-related behavior remains partial and
  must not be described as anonymity or comprehensive anti-detection.

## Local evidence at the binary source commit

- Python unittest suite: 261 tests, 3 skips — **PASS**.
- Source `--self-test` — **PASS**.
- Release-tool tests: 55 checks — **PASS**.
- Public repository guard: 207 files — **PASS**.
- Portable archive verifier: 1,066 files — **PASS**.
- Packaged executable `--self-test` — **PASS**.
- Manual GUI, Windows 10, second consumer PC/account, external DNS/IPv6/UDP/TURN,
  and broad site compatibility — **NOT RUN** for this candidate.

## Site state

Site source for 0.8.15 was pushed at
`32a909d9d78b264a4df505feeb4fa374c3f9ad04`; typecheck and build passed and
Site version 48 was saved. Saving did not deploy it. Live `release.json` still
reports the 0.8.14 ZIP (262,397,107 bytes; SHA-256
`44fef435ec5a46fa52d8441ac7e6d951e0577f611a16a21628a4a33ddcf61284`).
Version 48 must not be deployed until the matching immutable GitHub asset
exists and has been downloaded back and hash-verified.

## Remaining publication gates

1. Create immutable GitHub prerelease `v0.8.15-preview` at the binary source
   commit and upload the ZIP, `.sha256` sidecar, and manifest.
2. Download the public ZIP and sidecars again; compare bytes, SHA-256, manifest,
   and source commit with this record.
3. Deploy the saved Site version only after gate 2 passes.
4. Verify live `/release.json`, page download link, HTTP response and downloaded
   asset size/SHA-256. Then update this record from candidate evidence to the
   exact publication evidence.
