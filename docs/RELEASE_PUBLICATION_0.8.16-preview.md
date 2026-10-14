# NeAntik Win 0.8.16-preview — publication evidence

Verified on 2026-10-14. This record separates the browser binary source commit
from the public Site source commit.

## GitHub Release

- Public release: [v0.8.16-preview](https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.16-preview), prerelease.
- Binary source commit: `3fd8777de5d04f6e1cf706756096df950f60d98c` (clean source state in the release manifest).
- Portable ZIP: 262,403,257 bytes; SHA-256
  `8b9099f20dce636966e8bfac358e7c4bc1c616c204e4da128a7d41b81db42116`.
- Executable SHA-256:
  `caa05a1dc223955aaf1ee776128cae068886641c8a929f953c19654a47576701`.
- Public API metadata reported the ZIP as uploaded with the same size and
  SHA-256. The ZIP was downloaded again from the public release URL; local and
  downloaded ZIP, manifest and checksum sidecar sizes and SHA-256 values
  matched. `tools/verify-release-archive.ps1` passed for 1,066 files.
- Chromium 155.0.8059.40 is bundled. The preview is unsigned. The manifest
  limits its experimental Canvas2D/CPU/RAM/UTC behavior and does not claim
  anonymity; WebGL/WebGPU and external DNS/IPv6/UDP/TURN routes remain
  unverified.

## Site deployment

- Public Site: [nevision-win.mail782861.chatgpt.site](https://nevision-win.mail782861.chatgpt.site/).
- Sites version 50, source commit
  `8c0f8071d0f49488269b56db37b052a383062c56`; deployment returned `succeeded`.
- Live homepage returned HTTP 200 and included version `0.8.16-preview` and
  the matching portable ZIP name.
- Live `/release.json` reported the same release URL, ZIP size and SHA-256 as
  the public GitHub asset. A public ZIP HEAD request returned HTTP 200 and
  `Content-Length: 262403257`.
- Site typecheck and production build passed. Manual GUI on a fresh machine,
  Windows 10/ARM64, external network-route tests and cross-machine browser
  storage portability were **NOT RUN** in this publication check.

## Notes for the next cycle

The exact mechanism for earlier GitHub uploads was not recorded. This release
used the pre-existing authenticated GitHub CLI login stored by Windows; no new
PAT was created or exposed. For the repeatable workflow and Windows packaging
workarounds, see [RELEASE_OPERATIONS.md](RELEASE_OPERATIONS.md).
