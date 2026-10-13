# 0.8.6-preview publication evidence — 2026-10-13

This record supplements the pre-publication candidate-4 report. It does not turn a local test into proof of anonymity or make tests from another binary transferable.

- Source release tag `v0.8.6-preview` points to clean build commit `3934773840210c519817dce381d7ad8066cf3c61`. The later QA-document commit is not embedded in the archive.
- [GitHub prerelease](https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.6-preview) is public with ZIP, checksum and manifest assets. No versioned asset was overwritten.
- The ZIP was downloaded back from that public release: 262,382,459 bytes, SHA-256 `a370e9dfae4ccab89beb036a9a075b5372944aab19bdf151484ed4ace17da1c1`. It matches the local candidate and published checksum. The archive verifier passed for 1,066 files; extracted `NeAntikWin.exe` SHA-256 is `74184dea8fad0472f95d4731ab921552d37ca0e794766871b1fce721d6144309` and its packaged `--self-test` exited 0.
- The public Site was updated from clean site source commit `56fed1becf9d04683394186d684a92813266a52a`, Sites version 36, deployment `appgdep_6ace35ed00348191b6c360f97b73d20d` succeeded. Live [`release.json`](https://nevision-win.mail782861.chatgpt.site/release.json) returned `0.8.6-preview`, the exact public ZIP SHA-256 and size, and the tag's source commit. Live homepage and UTF-8 [`CHANGELOG.md`](https://nevision-win.mail782861.chatgpt.site/CHANGELOG.md) returned HTTP 200 and showed the 0.8.6 release.

Limits remain: Windows 10/ARM64, a second machine, full GUI accessibility and user-data migrations, external DNS/IPv6/UDP/TURN leakage, WebGL/WebGPU, statistical unlinkability and full anonymity were **not** established by this release gate. The executable is unsigned and bundled Chromium does not auto-update. See the candidate-4 report for exact PASS/INCONCLUSIVE/NOT RUN detail.
