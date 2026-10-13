# New-tab page and startup networking — 13 October 2026

## Product decision

In 0.8.4-preview, **new, empty bundled-Chromium profiles only** receive
`newtab_page_location_override: about:blank` in their initial `Preferences`.
Chromium retains ownership of that file after creation. Existing profiles and
installed Chrome/Edge receive no retrofit. The source-built Chromium binary
itself is unchanged from 0.8.3-preview.

This removes Chromium's remote new-tab *document*. It does **not** suppress
other browser-initiated requests or imply zero telemetry, an anonymous direct
profile, or a leak-free proxy. We did not ship
`--disable-background-networking`/`--disable-component-update`: a local trial
still showed startup requests, and suppressing component updates without a
replacement security-update process would be an unjustified tradeoff.

## Reproducible controls

`tools/start_page_network_audit.py` launches disposable profiles using the
exact extracted 0.8.3 Chromium core, records a redacted NetLog summary and
checks Chromium's `--dump-dom` output. The new-tab case must render exactly a
blank HTML document, and the preference must survive Chromium startup. A
rejecting local HTTP proxy is a separate routing control; its case must show
only loopback TCP and no NetLog UDP sends. The raw private reports remain in
`C:\NeAntikBuild\qa\` and are not committed.

Before the preference change, one same-host run observed 5 HTTP(S) request
jobs from `about:blank` and 12 from `chrome://newtab`; both made other
Google-related background requests. With the preference, three fresh
new-tab controls observed 6–7 HTTP(S) jobs and a blank document. Counts vary
between runs and are **not** a quantitative privacy score. With the new
preference and an intentionally rejecting proxy, the tested startup case
recorded only loopback TCP and zero NetLog UDP sends. This does not replace
packet capture or a public-network route test.

## Remaining gate

Audit each background service and its security role in the pinned Chromium
source. Do not disable Safe Browsing, certificate-related or component updates
merely to make a local request counter zero. Test the actual packaged GUI,
public-network DNS/IPv6/UDP behavior, extension effects, other Windows
versions and a second machine before making stronger claims.
