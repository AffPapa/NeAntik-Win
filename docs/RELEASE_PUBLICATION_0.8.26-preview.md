# Release evidence: NeAntik Win 0.8.26-preview

Дата: 2026-10-15. Канал: публичный prerelease; Windows x64; приложение не
подписано. Chromium 155.0.8059.79 (source
`a49e2e3d4addfd84e765b52afe230bedb81096db`); browser/device fingerprint не
изменяется (`fingerprint_modification=false`).

## Идентичность артефакта

- Binary source commit: `2c868bee8a18ae9776009e0a253b862ecbaef0b0` (clean source state).
- Annotated tag: `v0.8.26-preview`, peeled remote tag resolves to that commit.
- Local portable ZIP: `NeAntikWin-portable-v0.8.26-preview.zip`, 262,391,420 bytes,
  SHA-256 `77e5b36649ff198c6982b49bb17f656377e31610880e8a0f0d6f17ee8cda5955`.
- Packaged EXE SHA-256:
  `c80e93c49af26aca089bb929955cda1b911cb1f650c4ab5d25103d7442e1d0e3`.
- GitHub Release API digest for the ZIP equals the local SHA-256. A fresh public
  download also matched both the 262,391,420-byte size and SHA-256; the downloaded
  archive verifier passed (1,066 files).
- Manifest: portable preview, source tree clean, Chromium 155.0.8059.79,
  fingerprint modification false, `NotSigned`.

## Verification log

| Check | Exact input | Result |
| --- | --- | --- |
| Full source suite | binary source commit `2c868bee…`; 295 pass, 3 skipped | PASS |
| Callback-level GUI regression | same source; 21/21 | PASS |
| Release tooling | same source; 58 checks | PASS |
| Public-source guard | same source; 227 tracked files | PASS |
| Windows CI | run `38749404602`, source commit above | PASS |
| Build + archive verifier | exact local ZIP; 1,066 files | PASS |
| Packaged EXE `--self-test` | fresh isolated extraction; exit 0 | PASS |
| GUI window smoke | exact isolated portable EXE; window displayed v0.8.26-preview and closed; no user profile used | PASS for launch/render only |
| Fresh GitHub asset download | exact release ZIP; size + SHA-256 equal local/API digest; verifier rerun | PASS |
| Site production acceptance | Site v63, Site source commit `279d40d0364626d5c4e936e37961ddccb0980cc8`; `/`, `/release.json`, `/CHANGELOG.md` HTTP 200; ZIP HEAD 200 and `Content-Length` 262,391,420 | PASS |

## Limits and not-run checks

- The callback tests invoke the button handlers directly. The GUI smoke proves
  the window opens; it does not prove an actual keyboard-only journey, Tcl/Tk
  event routing, UIA/MSAA exposure, or NVDA/Narrator behavior.
- Windows 10, Windows ARM64, another physical machine/account, broad website
  compatibility, external DNS/IPv6/UDP/STUN/TURN routes were not tested.
- No fingerprint spoofing or anonymity claim is made. A local proxy assignment
  does not prove that every browser/network route uses it. The executable is
  unsigned.

Public endpoints:

- [GitHub release](https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.26-preview)
- [Portable ZIP](https://github.com/AffPapa/NeAntik-Win/releases/download/v0.8.26-preview/NeAntikWin-portable-v0.8.26-preview.zip)
- [Production Site](https://nevision-win.mail782861.chatgpt.site/)
