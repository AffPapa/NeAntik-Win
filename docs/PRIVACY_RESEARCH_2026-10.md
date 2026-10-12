# NeAntik Win — privacy and anti-detect research, 12 October 2026

This is a product/engineering comparison, **not** an independent certification
of any vendor's anonymity claims. The ten vendor pages below describe their
own features. User reviews are anecdotes and are separated from measured facts.

## What ten profile browsers expose

| Browser | Vendor-documented profile controls | What is useful for a small local browser |
| --- | --- | --- |
| [Multilogin](https://multilogin.com/help/en_US/profile-behavior-identity/profile-settings-fingerprint-section) | WebRTC, timezone, geolocation, language, screen, fonts, media, Navigator, WebGL, Canvas, AudioContext; recommends coordinated defaults. | Avoid independently randomising every API. Show effective values and network state. |
| [Indigo](https://faq.indigobrowser.com/fingerprints/hardware/) | Hardware-related screen, media, WebGL/WebGPU and Canvas settings; [its advice](https://faq.indigobrowser.com/getting-started/multiple-accounts-best-practices/) warns about inconsistent host/profile OS and changing defaults. | Test a profile on its actual Windows host; do not promise identical results after moving to another computer. |
| [Dolphin Anty](https://docs.dolphin-anty.com/en/getting-started/quick-start-in-dolphin-anty) | Profile proxy and engine-level WebRTC, Canvas, WebGL, ClientRects, timezone, geolocation and device parameters. | Keep create → assign proxy → run short; advanced identity settings need a tested core. |
| [GoLogin](https://support.gologin.com/en/articles/14854406-profile-settings) | Proxy, automatic timezone and profile summary; [advanced settings](https://support.gologin.com/en/articles/14854407-advanced-profile-settings) cover Canvas and WebRTC. | Put a clear summary before an advanced panel. |
| [AdsPower](https://help.adspower.com/docs/browser_fingerprint) | Multiple WebRTC modes, timezone based on IP/real/custom, geolocation and language. | A proxy hostname is not an exit-IP geolocation. Verify the route before deriving timezone. |
| [Octo Browser](https://docs.octobrowser.net/en/profiles/browser-profile-settings/) | Proxy-based location/timezone/WebRTC, UA/OS/fonts/GPU and noise settings. | Network, locale and device values must be coherent together. |
| [Kameleo](https://developer.kameleo.io/tutorials/managing-profiles/) | Base fingerprints with optional Canvas/WebGL/audio, timezone and proxy overrides; [proxy guide](https://developer.kameleo.io/tutorials/using-proxy-servers/) describes non-proxied WebRTC UDP restriction. | A default profile and proxy should be enough for a common workflow. |
| [Incogniton](https://docs.incogniton.com/getting-started/create-your-first-browser-profile) | Profile separation with proxy and identity settings; [API](https://api-docs.incogniton.com/apis) includes timezone and WebRTC fields. | Preserve local profile metadata and backup reliability. |
| [MoreLogin](https://support.morelogin.com/en/articles/10204297-profile-settings) | Match-IP timezone, WebRTC modes, geolocation, language, fonts, Canvas/WebGL/WebGPU/audio. | Do not put dozens of unexplained switches on the primary form. |
| [Vision](https://docs.browser.vision/api-reference/profiles/create-profile) | Fingerprint object, proxy ID, notes/tags, WebRTC preference. | Show the active browser/proxy and leave technical overrides behind a tested model. |

## Independent feedback and evidence quality

- [Proxyway's hands-on Multilogin review](https://proxyway.com/reviews/multilogin)
  measured a much older release (2022). Its UX observations are useful, but its
  fingerprint scores are **not** evidence about a 2026 build.
- [Dolphin Anty](https://www.trustpilot.com/review/dolphin-anty.com) and
  [Multilogin](https://www.trustpilot.com/review/multilogin.com) user reviews
  praise convenience and also report upgrade/support/data problems. These are
  unverified reports; Trustpilot marks removed fake reviews on Multilogin.
- [Indigo reviews on Partnerkin](https://partnerkin.com/services/indigobrowser?page=2)
  include instability complaints, but the platform is affiliate-oriented. We
  do not use its ratings as a technical benchmark.
- [USENIX Security research](https://www.usenix.org/system/files/conference/usenixsecurity18/sec18-vastel.pdf)
  shows inconsistent spoofing is detectable. This is why a pile of random
  JavaScript overrides is not a credible anonymity implementation.

## Threat model and this release

A site can see a network exit IP, HTTP/TLS traits, browser/OS version, locale,
timezone, screen, graphics, fonts, media APIs, WebRTC candidates and state such
as cookies. Other parties can see DNS or network traffic. A local attacker with
the same Windows account can read profile files. Separate local profile folders
alone do not solve these problems.

Version 0.6.0-preview adds one-time Chromium defaults for **new** profiles:
block third-party cookies and deny geolocation, notifications, camera and
microphone by default. Existing profiles and subsequent user changes are not
overwritten. A new optional diagnostic page, opened inside the chosen profile,
shows browser-visible parameters and the IP observed by our hosting on demand.
It does not run STUN, measure DNS/UDP, or certify anonymity. The existing proxy
launch flag restricts non-proxied WebRTC UDP only for bundled Chromium profiles
with a proxy. No arbitrary Canvas/WebGL/UA/timezone spoofing is added.

The diagnostic page itself is an external site: its hosting receives a request
IP and User-Agent when visited and may retain ordinary service logs. The page
contains no tracker or automatic report upload. All displayed browser values
are computed in the client and are not sent to our API; the IP endpoint returns
only the address/country headers already visible to the host.

## Why this is not yet a full anti-detect/anonymity browser

- A real native identity layer would need one stable per-profile configuration
  across Blink and browser processes: JavaScript APIs, HTTP headers, WebRTC,
  locale/timezone, screen/GPU/fonts/media and persisted state. Changing one
  surface in a script or extension while leaving others real creates conflicts.
- Proxy assignment is not a VPN or Tor: we have not certified HTTPS CONNECT,
  proxy authentication, DNS, IPv6, UDP and WebRTC packet routes on arbitrary
  networks. The built-in proxy TCP check is not an exit-IP check.
- We do not automatically infer timezone from a proxy server name. A rotating
  exit, approximate or stale GeoIP database, or another transport can make that
  inference wrong. The OS timezone is reported as-is.
- The portable Chromium needs manual security updates and is unsigned.
  Windows 10, ARM64, public proxy services and cross-computer session
  portability remain unverified.

Next engineering gate before any fingerprint-spoofing claim: build a versioned
native configuration and test matrix that compares all exposed surfaces on
multiple Windows hosts and proxy types, checks stability across restart and
backup, and records site compatibility and network capture. Until those gates
pass, the product should be described as a privacy-hardened local profile
browser, not a guaranteed anonymous identity generator. For anonymity against
websites and network observers, [Privacy Guides](https://2026.www.privacyguides.org/en/desktop-browsers/)
distinguishes Tor Browser from ordinary fingerprint protection.
