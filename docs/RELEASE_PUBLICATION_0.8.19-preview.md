# NeAntik Win 0.8.19-preview — publication evidence

Date: 2026-10-15. Channel: public preview. This is a keyboard activation
correction in the manager UI; it is not a fingerprint or Chromium privacy
patch. Chrome Stable was 155.0.8059.79 on 2026-10-13
([Chrome Releases](https://chromereleases.googleblog.com/2026/10/stable-channel-update-for-desktop_01668083673.html)).

## Identity

- Browser source commit and immutable tag target: `826f81671aa164434840eb023170c6ddf831cb51` (`v0.8.19-preview`).
- GitHub prerelease: <https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.19-preview>.
- ZIP: `NeAntikWin-portable-v0.8.19-preview.zip`, 262,378,971 bytes.
- ZIP SHA-256: `adec43f1fb17c1864cac0ca826b329162a0f7b56d924f87ecc4d7aa1a4910d2a`.
- Packaged `NeAntikWin.exe` SHA-256: `316a4a6b707eefcd58a923f6c9fb1ea85d1797436e0363c52f157800ce0cc7ab`.
- Runtime: Windows 11 Pro x64 build 26200, CPython 3.12.10, PyInstaller 6.21.0.
- Engine: stock Chromium 155.0.8059.79, source commit `a49e2e3d4addfd84e765b52afe230bedb81096db`, build-compat patch SHA-256 `2992c690bd16fd3f7196a52b018cdc0a2556f4148959fb7f3b7072803fe81a3d`; no runtime fingerprint patch (`fingerprint_modification: false`, empty privacy patch).

## PASS

- `python tools/gui_regression.py` on browser source commit `826f816`: 19/19 PASS, 8.285 s. The keyboard regression invokes callbacks with synthetic events; it verifies held-key repeat suppression, release/re-activation, and unrelated keys.
- `python -m unittest discover -q` on `826f816`: 265 tests PASS, 3 skipped, 13.269 s.
- Source `python nevision_win.py --self-test`: PASS; staged public-source guard: PASS (212 files); release tooling on version `0.8.19-preview`: 58 checks PASS.
- Windows CI run `38706390343` for exact source commit `826f816`: success.
- Clean portable build from the pinned Chromium stage: PASS. Release archive verifier: PASS (1,066 files); packaged `--self-test`: exit 0.
- Five starts from the exact ZIP: PASS. Visible manager window observed at 677.51, 209.66, 209.02, 209.28, and 208.52 ms; median 209.275 ms, range 208.52–677.51 ms. First-launch spread is material. This measures window appearance, not full UI readiness, Chromium startup, or a cold operating-system start.
- GitHub Release metadata reported prerelease and all three assets uploaded. The ZIP asset size and SHA-256 digest matched the local artifact. A fresh public download was 262,378,971 bytes, had the same SHA-256, and passed the archive verifier again.
- Production Site version 53 deployed at <https://nevision-win.mail782861.chatgpt.site>. Site source commit: `383c9e07f1bd4016e5801c1257bc5b95929ad290`; deployment status `succeeded`. The Site package was a 17,807,360-byte tar with content hash `sha256:35ba4e5233ddbb1a6f2a69edf2fdf187795cc0d0e934f3df38c9da0c1e8e2b50`.
- Live `/`, `/release.json`, and `/CHANGELOG.md`: HTTP 200. The live metadata named version `0.8.19-preview`, browser source commit `826f816…`, the exact ZIP filename, 262,378,971-byte size, expected SHA-256, and exact GitHub download URL. Public ZIP HEAD: HTTP 200 and Content-Length 262,378,971. Changelog response: `text/markdown; charset=utf-8`, Russian text and the new release heading decoded correctly.
- Hosted second-host gate: PASS, GitHub Actions run [38708197509](https://github.com/AffPapa/NeAntik-Win/actions/runs/38708197509), Windows Server 2022 runner. It fetched the exact public ZIP, checked its expected SHA/source identity, ran the packaged self-test, and verified isolated portable storage using synthetic data. This complements—but does not replace—manual GUI/accessibility, cross-PC/account, and external-network testing.

## Post-publication exact-ZIP route checks — 2026-10-15

The following loopback-only checks were run after publication against
`Engine/Chromium/chrome.exe` extracted from the exact ZIP above. The executable
SHA-256 was
`7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`; it matches
the ACL-prepared disposable copy in the harnesses. Browser source commit
`826f816…` is unchanged at harness commit
`d40d839b713962e3790a97893cfb36637a0e7639`; `nevision_win.py` was byte-identical
between those commits. All runs used synthetic profiles and loopback fixtures,
except the WebRTC STUN receiver hosted in the private WSL network namespace on
the same PC.

- HTTP/SOCKS5 route matrix: **72/72 assertions, 19 launches PASS**, including
  IPv4/IPv6 loopback targets and proxies, positive controls, and unavailable
  proxy no-direct-fallback checks.
- HTTPS proxy: **10/10 cases PASS**, including IPv4/IPv6 CONNECT, untrusted
  certificates, unavailable endpoints and a rejecting 407-auth case. Correct
  proxy credential entry is not covered.
- WS/WSS: **16/16 cases PASS** over direct, HTTP, HTTPS and SOCKS5 routes, plus
  unavailable proxies and untrusted HTTPS-proxy certificate controls.
- Proxy loss/recovery: **10/10 checks PASS** in one browser process; no target
  hits during outage, route resumed after recovery, NetLog contained only
  loopback TCP and zero UDP sends.
- WebRTC via WSL: **3 cases PASS**. The direct positive control delivered five
  STUN Binding requests/five UDP datagrams to the private WSL receiver. With
  HTTP and SOCKS5 proxy selected, it received zero STUN requests and zero UDP
  datagrams; Chromium NetLog recorded zero UDP sends in both proxy cases.
- Browser-storage integration: **21/21 assertions across seven visits PASS**
  on harness source commit `c988ec25dfaced8733909bd82f6cf1f959150ce9`.
  Synthetic A/B profiles isolated cookies, localStorage, IndexedDB, Cache
  Storage and service workers through restart; backup/restore retained A's
  state, while a configuration-only clone started empty. It used real
  `Storage`/backup/clone code and the exact release `chrome.exe`, not the GUI.
  Full unit suite on this harness commit: **266 PASS, 3 skipped**.
- The first browser-storage attempt was **INCONCLUSIVE**, before any storage
  assertion: Chromium sandbox reported access denied for the source-extracted
  executable (`0x5`). The harness was repaired to create a disposable
  ACL-prepared copy and verify byte-identical executable SHA-256. The exact-ZIP
  rerun passed; browser product code and the release ZIP were unchanged.
- A new real-Windows-junction regression on harness commit `d40d839…` checked
  the production `BrowserLauncher.ensure_profile_path_is_isolated` method. It
  rejects junctions at `Data`, `Profiles`, and the selected profile directory
  before process creation. Full unit suite on that commit: **266 PASS, 3
  skipped**.

Harness reports are retained locally outside the public repository; their raw
local addresses, synthetic tokens and diagnostics are not published. Script
and report hashes and the route/storage matrices are recorded in
[`ROUTE_MATRIX_2026-10.md`](ROUTE_MATRIX_2026-10.md).

## NOT RUN / INCONCLUSIVE

- Physical keyboard held-key behavior, manual profile create/edit, Windows UI Automation/MSAA tree, and NVDA/Narrator: NOT RUN. Synthetic callback tests do not prove operating-system key delivery or screen-reader semantics.
- Browser-storage cases beyond the listed synthetic APIs/origin (including extension/download state and arbitrary sites); external DNS, public IPv6/UDP/STUN/TURN, independent egress/packet observer, another Windows account/PC, and Windows 10: NOT RUN on this exact ZIP. The local route checks above do not imply those results.
- No claim of fingerprint spoofing, passing anti-bot checks, complete anonymity, or universal privacy is made. Profiles isolate local browser storage; they are not separate network identities.

## Release recovery note

The first Site package attempt committed and pushed the source, then failed
because the WSL package subprocess could not resolve `node`. Local HEAD/status
were inspected and the Site source remote was reconciled; the same commit was
repackaged successfully from WSL after adding its resolved Node directory to
PATH. No duplicate Site edit or commit was created. The verified publication
sequence remains: GitHub release → fresh ZIP download and hash/verifier → Site
source push/package/save/deploy → live metadata and HTTP verification.
