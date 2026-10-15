# NeAntik Win 0.8.28-preview — release evidence

## Release identity

- Channel: public preview; portable Windows x64 archive; EXE is not Authenticode-signed.
- Immutable annotated tag: [`v0.8.28-preview`](https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.28-preview).
- Binary source commit: `fb8029b00b94f750f1daae6cf788ecc268b4b1b0`.
- GitHub Release: https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.28-preview
- Portable archive: [`NeAntikWin-portable-v0.8.28-preview.zip`](https://github.com/AffPapa/NeAntik-Win/releases/download/v0.8.28-preview/NeAntikWin-portable-v0.8.28-preview.zip)
- Size: `262391330` bytes.
- SHA-256: `82d7baa19c01432ec59bdf35b67d101395080ea82f6a03799c1d8dc13bba482c`.
- Packaged `NeAntikWin.exe` SHA-256: `94d35858e127fefc23cb27668bba449307f980ababb61ef4f415c4a2dd2f2ac0`.
- Chromium: stable source-built `155.0.8059.79`, source commit `a49e2e3d4addfd84e765b52afe230bedb81096db`; bundled `chrome.exe` SHA-256 `7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`. The unchanged engine was reused, not rebuilt, for this manager-only change.
- Release metadata: `fingerprint_modification: false`; the application does not modify browser/device fingerprint values.

## Change

The native «Профиль» menu now exposes edit, proxy-check, copy-proxy-password, and delete actions as an alternative path to actions also shown as Canvas controls. No profile storage schema or Chromium behavior changed.

## Verification

| Check | Result |
| --- | --- |
| Full source unittest suite at binary source commit | PASS — 297 passed, 3 skipped |
| `tools/gui_regression.py` | PASS — 22/22 |
| Source `--self-test` | PASS |
| Public-repository source guard | PASS — 229 files |
| Release-tool tests | PASS — 58 checks |
| Windows CI run [`38758749558`](https://github.com/AffPapa/NeAntik-Win/actions/runs/38758749558) | PASS |
| Clean portable build using the verified Chromium engine | PASS |
| Local portable ZIP archive verifier | PASS — 1,066 files |
| Packaged EXE `--self-test` | PASS |
| GitHub asset API digest/size | PASS — matches local archive |
| Fresh download of published ZIP and archive verifier | PASS — 262,391,330 bytes; same SHA-256; 1,066 files |

## Site publication

- Sites project: public NeAntik Win Site, production URL https://nevision-win.mail782861.chatgpt.site/.
- Site source commit: `25a70c9ecdb93af34b78da35afd1740bcabd8467`.
- Saved/deployed Site version: `65`; deployment succeeded.
- Site typecheck and production build: PASS.
- Packaged Worker archive contained `dist/.openai/hosting.json`, configured `dist/server/index.js`, and static assets.
- Live `/`: HTTP 200; expected version and GitHub archive URL present.
- Live `/release.json`: HTTP 200; version, binary source commit, archive URL, size and SHA-256 match this release; `fingerprint_modification` is false.
- Live `/CHANGELOG.md`: HTTP 200; .28 entry and ZIP SHA-256 present.
- GitHub archive URL: HTTP 200; Content-Length `262391330`.

## Not run and limits

- Manual GUI smoke of this exact .28 portable EXE: **NOT RUN**. Source-level Tk GUI regression and packaged non-interactive self-test do not replace opening and visually/keyboard-testing this exact EXE.
- UI Automation / MSAA / NVDA and full keyboard-only interaction: **NOT RUN**.
- External DNS, IPv6, UDP, STUN/TURN and independent egress observation; Windows 10/ARM64; another physical machine/account: **NOT RUN**.
- The release does not claim anonymity, fingerprint spoofing, or evasion of anti-bot controls. Backups remain unencrypted and may contain browser data; proxy routing does not establish anonymity.

## Post-release GUI smoke attempt (2026-10-15)

This is a follow-up observation after the immutable `v0.8.28-preview` release; it
does not change the tagged source, ZIP, EXE, or release metadata.

| Check | Result |
| --- | --- |
| Fresh extraction of the redownloaded public ZIP, verified at 262,391,330 bytes and SHA-256 `82d7baa19c01432ec59bdf35b67d101395080ea82f6a03799c1d8dc13bba482c` | PASS |
| Extracted EXE SHA-256 `94d35858e127fefc23cb27668bba449307f980ababb61ef4f415c4a2dd2f2ac0` | PASS |
| Launch via Windows Computer Use and selection of a uniquely returned .28 window | **INCONCLUSIVE** — launch created a live process, but the UI enumerator exposed only pre-existing NeAntik .21/.23/.24/.26 windows; after one refreshed window listing no .28 window was targetable |
| Profile menu and keyboard navigation | NOT RUN — no uniquely identified .28 window was available, so no UI actions were sent |
| QA data isolation | PASS — only the fresh extracted copy was used; its `Data` directory was created on launch, and no `Profiles` directory was created |
| Cleanup | PASS — only the exact isolated .28 process started for this attempt was stopped; no older app window or user profile was touched |

This observation does not establish a product failure: process lifetime and
window enumeration were not captured together at the first snapshot, and the
UI automation layer may have omitted or mis-associated the window. It also does
not establish that the UI works. Do not repeat the launch without a new,
specific diagnostic hypothesis and a process-ID-bound way to identify the
window; UIA/MSAA/NVDA remain separate untested gates.

The public site was updated after this observation (the binary release remains
unchanged): Site version `66`, source commit
`5f195f989c1742ed42636912824ac791b28bc33a`, deployed successfully. Live `/`
and `/CHANGELOG.md` show the `INCONCLUSIVE` result and link to this record;
live `/release.json` still identifies binary source commit
`fb8029b00b94f750f1daae6cf788ecc268b4b1b0`, ZIP size `262391330` and SHA-256
`82d7baa19c01432ec59bdf35b67d101395080ea82f6a03799c1d8dc13bba482c`. The
public ZIP HEAD returned HTTP 200 with the same content length.
