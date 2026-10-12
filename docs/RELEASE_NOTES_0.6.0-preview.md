# NeAntik Win 0.6.0-preview

A single portable Windows x64 ZIP containing NeAntikWin.exe and Chromium
155.0.8059.40. Extract the whole ZIP to a writable NTFS folder. No installer,
Python, account or separately installed Chrome is needed for a new profile.

New bundled-Chromium profiles now start with third-party cookies blocked and
geolocation, notifications, camera and microphone denied. These are Chromium's
own preferences, created only once for an empty profile. Existing profiles and
any later changes made in Chromium are not overwritten. Sites that need these
capabilities may require you to allow them manually.

The new Diagnostics action opens a check page in the chosen browser profile.
It shows ordinary browser-visible values and, on request, the IP seen by the
NeAntik website. Visiting this external page reveals a request IP and headers
to its hosting; ordinary host logs may exist. The page does not upload a
fingerprint report, run STUN or prove DNS/WebRTC/UDP routing. If the profile is
already open, NeAntik copies the page address for you to open in that profile.

The bundled core still restricts non-proxied WebRTC UDP when a proxy is assigned;
its system timezone is unchanged. No coherent device/browser fingerprint
spoofing, Tor routing or anonymity guarantee is included. Proxy TCP checks do
not verify authentication, external exit IP or leaks. Windows 10, ARM64 and
cross-machine session portability remain unverified. This preview is unsigned,
and bundled Chromium does not auto-update.

Before upgrading, close all profile windows and save a copy of the complete
previous portable folder, including `Data/`. Extract this version separately
and copy `Data/` under the same Windows user. Keep the old copy for rollback;
an older Chromium may not reopen data written by a newer one. Windows DPAPI
proxy secrets and browser session encryption may not transfer to another PC.

Research comparing ten profile browsers and the exact protection boundaries is
in `docs/PRIVACY_RESEARCH_2026-10.md` in the public source repository.
