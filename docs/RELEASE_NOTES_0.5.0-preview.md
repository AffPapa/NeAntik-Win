# NeAntik Win 0.5.0-preview

Windows x64 portable ZIP with unbranded Chromium 155.0.8059.40 built from pinned
upstream source. Extract the **whole archive** into a writable folder and open
`NeAntikWin.exe`; no installed Chrome, Python, installer or account is required
for a new profile.

Use a writable local NTFS folder. At first bundled-browser launch, NeAntik
grants Windows sandboxed child processes read/execute access to
`Engine/Chromium` only; it does not change permissions on private `Data/`.

New profiles use bundled Chromium. Existing Chrome/Edge profiles stay pinned to
their original browser family; older unpinned profiles with existing data must
explicitly select their original browser or make a clean copy. Local profiles,
proxy vault, history and backups remain in `Data/` beside the app. The ZIP
contains no user `Data/`.

This is an **unsigned preview** tested on Windows 11 Pro x64 build 26200.
Windows 10 and ARM64 were not validated. There is no Chromium auto-updater,
fingerprint modification, automatic timezone-to-proxy matching or anonymity
guarantee. Proxy checking is TCP-only; it does not verify DNS, UDP, WebRTC,
authentication or exit IP. Chromium and extensions may make their own network
requests. Install a newer portable release when browser security fixes arrive.

Before upgrading, close all profile windows and preserve a private copy of the
entire old portable folder including `Data/`. Extract this version into a new
folder and copy `Data/` there. Windows DPAPI/browser encryption can prevent
passwords or sessions from working under a different Windows account or PC.
Rollback requires the preserved old folder and pre-upgrade data snapshot.

The attached `.zip.sha256` and `.manifest.json` identify the exact archive and
source commit. The bundled Chromium license, `chrome://credits` notices and
source-build provenance are inside `Engine/Chromium/`. See `CHANGELOG.md` and
`SECURITY_AND_SCOPE.md` in the archive for details.
