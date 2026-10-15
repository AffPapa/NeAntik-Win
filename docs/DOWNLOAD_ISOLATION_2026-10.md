# Managed profile downloads — 13 October 2026

NeAntik Win 0.8.3-preview changes only **new profiles launched with the bundled
Chromium**. They save files to `Data/Profiles/<id>/Downloads`, inside the
profile's portable data directory. Already-used profiles and profiles pinned
to installed Chrome/Edge keep their existing download settings. A user-selected
custom path in Chromium is never overwritten.

Chromium stores an absolute `download.default_directory` in Preferences and
resets relative values to a system default. NeAntik therefore writes a
browser-visible absolute path at first launch and records that exact managed
value in `NeAntikManagedDownloads.json` inside the profile. Before later
launches, while the profile is closed and protected by its operation lock, the
manager changes the path only if Preferences still equals the recorded
managed value. This handles copying the portable folder or restoring a backup
under a new profile ID. If Chromium/user changed the path, no rebase occurs.
The marker is not a security boundary against software running as the same
Windows account.

## Evidence

- `test_privacy_defaults.py` covers first-run setup, normal/extended Windows
  path representation, portable move, legacy profile opt-out, and respect for a
  custom directory.
- `test_nevision_win.py` checks that real backup/restore includes a synthetic
  downloaded file and rebases the restored profile's path.
- `tools/launcher_integration.py` inspects Preferences at the actual launcher
  spawn boundary and again after the source-built Chromium starts.
- `tools/download_integration.py` served a synthetic 4,880-byte file over
  loopback. The extracted 0.8.2 Chromium (same engine as 0.8.3) downloaded
  distinct files into profiles A and B, then downloaded again in moved A.
  Files appeared only under their expected profile folders. The private report
  is `C:\NeAntikBuild\qa\download-managed-v082-20261013-b.json`.

The download test uses an owned Windows Job and a loopback-only server. Its
browser process is deliberately stopped after the file bytes are verified:
headless `--dump-dom` may otherwise remain alive after an attachment download.
It does not use a real website, test all file types, assert OS-level secrecy,
or prove cross-machine session portability. Profile backups include downloaded
files; those ZIPs are unencrypted and subject to the existing size/file-count
limits. Keep both `Data/` and backups private.

## Exact public 0.8.18-preview portable-root regression — 15 October 2026

The exact public Chromium (`chrome.exe` SHA-256
`7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`) passed
**3/3 synthetic 4,880-byte downloads** in disposable profiles A and B. The A/B
files remained separated; then the whole disposable portable root was moved,
the managed Downloads binding rebased, and A downloaded again without losing
its first file. The harness invokes `BrowserLauncher.ensure_profile_path_is_isolated`
before every Popen, uses the exact hash-identical engine in a sandbox-ACL
prepared QA copy, and reapplies bundled-engine sandbox ACL after the move.
The real Windows profile-junction launch regression passed immediately before
the run. Harness commit `7fb6240baa736e71821d9317d729cb08f170f67e`, SHA-256
`7038d05d7b88a2a6555aa968d7fd8f713136a7b020f4c16e28585f3f567f981e`.
Private report:
`C:\N155\download-integration-final-diagnostic-0.8.18-preview-20261015.json`.

This is a headless source harness on one Windows host, not packaged-GUI,
cross-account, cross-PC, or real-site coverage. The two initial runs exposed
test-harness environment gaps (profile layout and engine sandbox ACL); those
were fixed before the passing run. No product engine bytes were changed.
