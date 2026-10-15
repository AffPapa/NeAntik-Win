# Release evidence — NeAntik Win 0.8.22-preview

Verified 2026-10-15. This release improves local backup integrity checks. It does
not implement fingerprint spoofing or establish network anonymity.

## Browser artifact

- GitHub prerelease: [v0.8.22-preview](https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.22-preview).
- Exact tagged binary source commit: `95a4c91e7cfedf868710bc287a82e25ade5f87de`;
  annotated tag `v0.8.22-preview` peels to this commit on `origin/main`.
- Portable ZIP: `NeAntikWin-portable-v0.8.22-preview.zip`, 262,380,994 bytes.
- SHA-256: `27beb070067034f48493a4b45f00f1ab43f86a7a0c467dc76e06b02dddf9c81d`.
- Packaged `NeAntikWin.exe` SHA-256:
  `37f20823405b68bf0af18b267fc50489c3a91d6e3094e00fc419da3cdca1628f`.
- Chromium: `155.0.8059.79`, source commit
  `a49e2e3d4addfd84e765b52afe230bedb81096db`. The engine executable SHA-256
  matched the exact 0.8.21 public ZIP extraction; Chromium was not rebuilt.
- Release manifest records `source_state=clean` and
  `fingerprint_modification=false`; `Data/` is absent from the archive.
- GitHub release has the portable ZIP, SHA-256 sidecar and manifest. The public
  ZIP was downloaded again; its size, local hash, sidecar and GitHub API asset
  digest all matched. The downloaded ZIP passed the archive verifier for 1,066
  files. Extracted packaged EXE `--self-test` exited 0.

## Tests and observed performance

- Four targeted backup tests passed, including a corrupted member CRC and
  preservation of an earlier backup if the new verification fails.
- `python -m unittest -v test_nevision_win.py test_profile_identity.py test_privacy_defaults.py`:
  126 passed, 3 skipped. The run caught a long-Windows-path regression in the
  first implementation; the extended-path handling was fixed and the full run
  then passed.
- `tools/test-release-tools.ps1`: 58 checks passed.
- `tools/check-public-repo.ps1`: passed; no oversized public source files.
- On a synthetic 128 MiB incompressible file, one timing run measured 2.623 s
  without the read-back verifier and 2.733 s with it (+0.110 s). This is one
  cached Windows-host measurement, not a performance guarantee for slow disks
  or near-limit profiles.
- A manual GUI backup scenario on the exact packaged EXE was **NOT RUN**. The
  packaged self-test uses synthetic storage/backup data; it is not equivalent
  to a full GUI acceptance run.

## Site deployment

- Public Site: https://nevision-win.mail782861.chatgpt.site/
- Site source commit: `c713d20e1b0264428e2aa11d1db566f1c8b1a500`.
- Production Sites version 56; the pre-existing public audience was preserved.
- TypeScript check and Vinext production build passed. The existing build emitted
  its known dynamic-import and route-classification warnings, but completed.
- Live `/`, `/release.json`, and `/CHANGELOG.md` returned HTTP 200. The release
  metadata matched version, source commit, filename, size, hash and GitHub URL;
  the changelog includes 0.8.22 and preserves 0.8.21 history with readable
  Cyrillic. GitHub ZIP HEAD returned HTTP 200 with exact length `262380994`.

## Scope notes

The backup writer now checks the expected member set, manifest and each ZIP
member CRC before atomically publishing the new archive. Failed verification
removes only the new partial file; older completed archives remain untouched.
This reads the completed ZIP again and adds I/O proportional to archive size.
Backups remain unencrypted and can contain cookies and active sessions; the
change does not provide encryption, protection from same-account malware,
fingerprint spoofing, or a network anonymity guarantee.
