# Release evidence — NeAntik Win 0.8.21-preview

Publication verified on 2026-10-15. This record captures the immutable browser
release and the separate production Site deployment; it does not claim complete
privacy, anonymity, or fingerprint modification.

## Browser artifact

- GitHub: [v0.8.21-preview](https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.21-preview)
- Source commit: `1ef1cf26ad15150f2799280bb46eaa3ca2447da3` on `main`; the annotated
  `v0.8.21-preview` tag peels to this commit.
- Portable ZIP: `NeAntikWin-portable-v0.8.21-preview.zip`, 262,380,444 bytes.
- SHA-256: `0d037e430eef4c48d41d599f0f6434815b5b71cec10b1eb50327ef8b19d189af`.
- Packaged executable SHA-256:
  `bbf1bbdffc49e73643f30b4ec2396f52ee6907131504ced556a22627023f7f6f`.
- Chromium: stock bundled Chromium `155.0.8059.79`; fingerprint modification is
  false. `Data/` and user profiles are not included.
- The exact GitHub asset was downloaded again; size, SHA-256 sidecar and GitHub
  asset digest matched the local ZIP. Archive verifier passed for 1,066 files,
  and the executable self-test exited 0.

## Tests and GUI evidence

- `python -m unittest -v test_nevision_win.py test_profile_identity.py test_privacy_defaults.py`:
  124 passed, 3 skipped (platform/environment constraints).
- `python -m unittest discover -s tools -p 'test_*integration.py' -v`:
  72 passed.
- `tools/test-release-tools.ps1`: 58 checks passed.
- `tools/check-public-repo.ps1`: passed for 217 public source files; no file
  exceeded the configured size limit. This is a repository hygiene gate, not a
  proof that no secret exists anywhere.
- On a separate disposable extracted copy of the exact candidate, the manager
  launched; File → “Открыть папку резервных копий” opened that copy's own
  `Data/Backups` in Explorer. No user profile/data was used. This is a focused
  GUI scenario, not a full end-to-end UX audit.

## Production Site

- Public Site: https://nevision-win.mail782861.chatgpt.site/
- Site source commit: `277e94e3cf0dd6a32f76682c3113875f6f10c375`.
- Sites production version: 55; existing public audience preserved.
- Live `/`, `/release.json`, and `/CHANGELOG.md` returned HTTP 200. `release.json`
  matched version `0.8.21-preview`, browser source commit, archive filename,
  size, SHA-256, and GitHub download URL. ZIP HEAD returned HTTP 200 with exact
  length `262380444`; the CHANGELOG contains readable Cyrillic text.

## Scope and remaining limitations

The release adds a menu shortcut to the portable `Data/Backups` folder, creating
it if missing. Proxy routing remains subject to documented network limits;
external DNS/IPv6/UDP/STUN/TURN and successful proxy-auth behavior are not proven
by this release. Fingerprint spoofing is not implemented. Backup archives remain
unencrypted and can contain session data; the 0.8.21 shortcut does not change
backup format or sensitivity.
