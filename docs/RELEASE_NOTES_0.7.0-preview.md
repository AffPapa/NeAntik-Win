# NeAntik Win 0.7.0-preview

Portable Windows x64 ZIP with NeAntikWin.exe and source-built Chromium
155.0.8059.40. Extract the entire ZIP into a writable NTFS folder; no
installer, separately installed Chrome, account or Python is required.

New bundled-Chromium profiles now disable network prediction/preloading in
addition to blocking third-party cookies and denying geolocation,
notifications, camera and microphone. These one-time initial preferences do
not overwrite existing profiles or later user changes. A real two-site HTTPS
control test confirms third-party-cookie blocking, and Chromium reports the
four permissions denied.

For a bundled-Chromium profile with an assigned proxy, the launcher now routes
localhost URLs through the proxy rather than using Chromium's implicit direct
bypass, blocks background name resolution except the proxy endpoint, disables
QUIC and restricts non-proxied WebRTC UDP. Local sites and real-time calls may
stop working. Disposable real-browser tests covered HTTP, SOCKS5, loopback
URLs, unavailable proxies, launcher flags and no-STUN ICE candidates.

This does **not** spoof device/browser fingerprints or guarantee anonymity.
There is no external packet-capture, public STUN, arbitrary DNS/IPv6/UDP or
commercial-proxy certification. The proxy's own hostname may be resolved
locally. Installed Chrome/Edge legacy profiles are unchanged. Chromium has no
automatic updater, and the EXE is unsigned. Tested on Windows 11 x64 build
26200; Windows 10 and ARM64 are unverified.

Before upgrading, close profile windows and copy the whole previous portable
folder including `Data/`. Extract this version separately and copy `Data/`
under the same Windows user. Keep the old copy for rollback; older Chromium
may not reopen upgraded profile data. Windows DPAPI proxy secrets and browser
sessions may not transfer to another computer.

Engineering evidence and precise limits are in
`docs/NETWORK_PRIVACY_2026-10.md` and `SECURITY_AND_SCOPE.md` in the public
source repository.
