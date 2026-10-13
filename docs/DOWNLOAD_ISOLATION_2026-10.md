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
