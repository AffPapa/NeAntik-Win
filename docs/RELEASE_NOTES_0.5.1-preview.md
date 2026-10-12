# NeAntik Win 0.5.1-preview

One portable ZIP for Windows x64: NeAntikWin.exe plus source-built, unbranded
Chromium 155.0.8059.40. Extract the whole folder on a writable NTFS volume;
no installed Chrome, Python, account or installer is needed for a new profile.

This update removes unused Chromium UI language packs while preserving English,
Russian and Thai. Other system languages fall back to English. The browser DLL
and profile-data format are unchanged. The main screen now explains its
actions on hover or keyboard focus, includes a short Help guide, and correctly
labels the profile's pinned browser. Backup and clean-copy actions have clearer
Russian names and explain their different treatment of cookies and sessions.
For a bundled-Chromium profile with an assigned proxy, WebRTC is limited from
using non-proxied UDP; calls may behave differently, and this is not a general
leak-prevention guarantee. System timezone remains unchanged.

Keep a private copy of the complete previous portable folder, including
`Data/`, before upgrading. Close all browser windows first, extract this
version separately, then copy `Data/` into it. The ZIP contains no user Data.
Windows DPAPI/browser encryption may prevent proxy passwords or sessions from
working under another Windows account or PC. A rollback needs the original
folder and its pre-upgrade data snapshot.

This unsigned preview was tested on Windows 11 Pro x64 build 26200. Windows 10
and ARM64 remain unverified. Chromium does not auto-update in this portable
distribution. There is no device/browser fingerprint spoofing, automatic timezone-to-proxy
matching, or anonymity guarantee. The proxy test checks TCP only; it does not
prove DNS, WebRTC, UDP, authentication or exit IP routing.

The ZIP's SHA-256 and release manifest are attached. Chromium license,
third-party credits and source-build provenance are inside `Engine/Chromium/`.
