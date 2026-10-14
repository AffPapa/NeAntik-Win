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
- Site typecheck and production build passed. At initial publication, manual
  GUI on a fresh machine, Windows 10/ARM64 and external network-route tests
  were **NOT RUN**. Follow-up bounded tests against the same public ZIP are
  recorded in the network and route reports: proxy loss/recovery 10/10, public
  STUN policy 4/4, and HTTPS proxy cases 28/28. Independent DNS/packet
  observation, another host and cross-machine storage portability remain
  **NOT RUN**.

## Notes for the next cycle

Publication used the pre-existing authenticated GitHub CLI login stored by
Windows; no new PAT was created or exposed. The tested GitHub + public Site
workflow and Windows packaging workarounds are recorded in
[RELEASE_OPERATIONS.md](RELEASE_OPERATIONS.md). Start each release by following
that document and record the exact binary and Site source commits separately.
