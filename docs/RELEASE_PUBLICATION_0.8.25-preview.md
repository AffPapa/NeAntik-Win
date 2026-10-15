# NeAntik Win 0.8.25-preview — publication evidence

Date: 2026-10-15. This record separates source, the local portable archive,
the public GitHub asset, and the live Site. It does not claim anonymity.

## Source and artifact identity

- Annotated tag: [`v0.8.25-preview`](https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.25-preview)
- App source commit: `112580b7c312763928368e547fa79712d112d739`
- Engine: unbranded stock Chromium `155.0.8059.79`, source commit
  `a49e2e3d4addfd84e765b52afe230bedb81096db`; no fingerprint-modification
  patch. The already-verified engine was reused; Chromium was not rebuilt.
- Portable ZIP: `NeAntikWin-portable-v0.8.25-preview.zip`, 262,390,594 bytes,
  SHA-256 `ffbdc26c81d6081bc7fca2777d0cc9248a5d9debb4324fa888b011251e39c353`.
- EXE SHA-256: `7ff61e24ecc8ffdd6e8723e4b86e1b2d328d87c1e49fcdc5afdca7139379f38b`.
- GitHub Release API reported all three assets uploaded, with sizes and SHA-256
  digests matching local ZIP, `.sha256` sidecar, and manifest. The public ZIP was
  downloaded again; its size and SHA-256 matched, and the public bytes passed
  `tools/verify-release-archive.ps1` (1,066 files).

## Verification

| Gate | Result | Scope |
| --- | --- | --- |
| `python -m unittest discover -q` | PASS — 295 tests, 3 skipped | Local Windows 11 x64; skips are platform-gated. |
| Four focused reparse regressions | PASS | Real Windows junctions under IndexedDB and CacheStorage; entry-limit fail-closed; `scandir` error fail-closed. |
| Release tooling | PASS — 58 checks | Synthetic release/archive fixtures. |
| Public source guard | PASS | Staged files locally and full public checkout in CI. |
| Windows CI [`38743935514`](https://github.com/AffPapa/NeAntik-Win/actions/runs/38743935514) | PASS | Full configured source, route-harness, safety and release-tool jobs. |
| Exact extracted portable EXE `--self-test` | PASS — exit 0 | Fresh extraction of the local release ZIP. |
| Public second-host workflow [`38745934605`](https://github.com/AffPapa/NeAntik-Win/actions/runs/38745934605) | PASS | Hosted Windows 2022: exact public ZIP, archive/provenance verification, packaged self-test and disposable synthetic Chromium storage isolation. |
| GUI smoke | NOT RUN | No UI changed; no profile was created and no Chromium was launched locally for this release. |
| Live Site and ZIP endpoints | PASS | `/`, client bundle, `/CHANGELOG.md`, `/release.json` and public ZIP HEAD returned HTTP 200; release version/source/filename/size/SHA matched. |

The direct-child reparse scan checks only `Default/IndexedDB` and
`Default/Service Worker/CacheStorage`, up to 10,000 entries per directory.
Exceeding the limit or a directory/entry inspection error fails closed; a
`FileNotFoundError` caused by a root or entry disappearing during enumeration
is skipped. It does not inspect deeper descendants, remove TOCTOU, or protect
against another process under the same Windows user.
A synthetic profile with 10,000 files in each directory measured p50 27.676 ms,
p95 29.708 ms and max 31.190 ms across 15 checks on this Windows 11 machine;
these numbers are not a general startup guarantee.

External DNS, IPv6, public UDP/STUN/TURN, a second physical computer, Windows
10/ARM64, and broad site compatibility were NOT RUN or remain unverified. The
EXE is unsigned and this release has no GitHub OIDC/Sigstore review attestation.
Fingerprint modification is false; NeAntik does not promise anti-detection or
complete anonymity.

## Public Site

- Existing public Site audience preserved; Site version **61** deployed at
  <https://nevision-win.mail782861.chatgpt.site>.
- Site source commit: `430a967ced7e3be041817d523ede28b171508252`.
- The live release metadata and changelog refer to the exact public ZIP above;
  version 0.8.24 attestation metadata was not carried forward to this unattested
  archive.
