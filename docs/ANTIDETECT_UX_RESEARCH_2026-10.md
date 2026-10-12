# Product and UX research — 12 October 2026

Scope: public vendor documentation for ten profile browsers. Vendor statements
describe their own products and are not independent proof of leak prevention.
The comparison is for prioritising a small local Windows application, not a
claim that NeAntik implements every listed fingerprint feature.

| Product | Documented profile workflow and network controls | Small-product lesson |
| --- | --- | --- |
| [Multilogin](https://multilogin.com/help/en_US/profile-behavior-identity/profile-settings-fingerprint-section) | Profile fingerprint panel covers WebRTC, timezone, location, language and more; its docs advise most people to keep coordinated defaults. | Show safe defaults first; don't expose dozens of unexplained switches. |
| [Dolphin Anty](https://docs.dolphin-anty.com/en/interface-dolphin-anty/application-interface-dolphin-anty) | Profile list, proxy list, search/filter, bulk actions and scenarios are separate navigation areas; its [profile API](https://docs.dolphin-anty.com/en/api/api-profile-creation-template-dolphin-anty) has WebRTC and auto-timezone fields. | Keep profile creation, search and proxy assignment direct; omit cloud scripting/bulk UI for now. |
| [AdsPower](https://help.adspower.com/docs/browser_fingerprint) | Several WebRTC modes including real, disabled and disabled UDP; [global settings](https://help.adspower.com/docs/global_settings) include dynamic-IP timezone matching. | Explain that disabling WebRTC can break calls, and a TCP check is not an IP/leak check. |
| [GoLogin](https://support.gologin.com/en/articles/14854406-profile-settings) | Proxy, timezone and profile summary; automatic timezone uses external IP. | A visible summary of effective settings beats an advanced form. |
| [Incogniton](https://api-docs.incogniton.com/apis) | Profile metadata/notes/groups, proxy, automatic or manual timezone and WebRTC configuration. | Our name, group, note and proxy cover the useful local organisation baseline. |
| [Kameleo](https://developer.kameleo.io/tutorials/managing-profiles/) | Full API exposes many fingerprint fields but notes that common setup often needs only name, proxy and defaults; [proxy guide](https://developer.kameleo.io/tutorials/using-proxy-servers/) describes `disable_non_proxied_udp` for WebRTC. | Keep the default path short; apply a tested network restriction automatically with a proxy. |
| [Octo Browser](https://docs.octobrowser.net/en/profiles/browser-profile-settings/) | Profiles have notes, folders, tags, proxy/VPN and advanced timezone/WebRTC controls. | Preserve simple organisation; do not imply an HTTP proxy routes all protocols. |
| [MoreLogin](https://support.morelogin.com/en/articles/10204297-profile-settings) | Match-IP/custom timezone, multiple WebRTC modes and many advanced fingerprint fields. | Keep advanced identity controls out of the primary form. |
| [Vision](https://docs.browser.vision/api-reference/profiles/create-profile) | Profile API includes notes, tags, proxy ID and a WebRTC preference. | Profile metadata and network assignment should be easy to inspect. |
| [Undetectable](https://undetectable.io/blog/first-undetectable-profile-set-up-guide/) | Its introductory guide says to leave advanced settings at defaults and warns that disabling WebRTC can break site functionality. | Prefer conservative defaults and contextual help over a crowded switchboard. |

## Decision for NeAntik Win 0.5.1-preview

1. Keep the primary flow as **create profile → optionally assign proxy → run**.
   Hide the installed-browser path under old-profile compatibility. Add hover
   and keyboard-focus help to risky/ambiguous actions, and show the actual
   pinned browser in profile details.
2. For a bundled-Chromium profile with a configured proxy, apply Chromium's
   [`--webrtc-ip-handling-policy=disable_non_proxied_udp`](https://chromium.googlesource.com/chromium/src/+/3d6bf17ccb45f22a9f86ce2dfc12559ea39dac74)
   switch. Chromium maps the switch to the WebRTC IP-handling preference. This
   restricts direct UDP; it does **not** prove that all WebRTC or DNS traffic
   uses the proxy, and calls may behave differently. No proxy means stock
   browser behaviour. Existing pinned Chrome/Edge profiles are unchanged.
3. Do not fake an IP-derived timezone. A proxy host can be a DNS name, a
   datacenter endpoint or a rotating exit. Geo-IP services disagree and need
   external queries. An automatic timezone would be a claim we cannot
   validate locally. The browser reports the system timezone; the UI states
   this plainly. Revisit only with a reliable, consented, testable data source.
4. Do not add cloud sync, account/team panels, profile scripting or an array
   of Canvas/WebGL/noise toggles to this light local release. They increase
   support and consistency risk without improving the basic workflow.

## Verification boundary

The launcher flag is covered by argument-level tests and the bundled browser
by headless integration tests. Neither a vendor feature list nor a headless
test proves anonymity, a specific external IP, cross-machine session
portability, or absence of WebRTC/DNS leaks across every network. The user
should verify the network route independently before relying on it.
