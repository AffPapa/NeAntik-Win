# Profile isolation evidence — 13 October 2026

This records a bounded P3.1 test of the **extracted public 0.8.2-preview
Chromium** on one Windows 11 host. It is not a proof that every Chromium state
or every installed extension is isolated.

## Procedure

`tools/browser_integration.py` creates an owned temporary NeAntik `Storage`
root and two fresh profiles, A and B. Each launch starts a new real Chromium
process in a Windows Job. The page is served only from a loopback origin;
background network requests meet a rejecting loopback proxy. The script
does not attach to existing windows or personal browser profiles.

Both new profiles receive the same privacy defaults as a newly launched
bundled profile. The page reads cookies, localStorage, IndexedDB, Cache
Storage, service-worker registration, and `navigator.permissions` states for
geolocation and notifications. After A and B have stored distinct synthetic
values, the harness closes A and edits **only A's disposable Preferences** to
allow notifications for the test origin. This is a controlled substitute for
a user permission click, not a GUI test. Chromium itself must then report
`granted` in A and `denied` in B after separate restarts.

The harness backs up A using the product's real backup function, restores it
to a new profile, and creates a configuration-only clone using the product's
real clone handler. It verifies that the restore retains A's data and
notification setting, while the clone starts with neither. The original A
must remain unchanged. The completed run removes only its own disposable
temporary directory.

## Observed result

The released engine passed **21 assertions over seven browser launches**:

| Profile / visit | Geolocation | Notifications | Synthetic site storage |
| --- | --- | --- | --- |
| New A and B | denied | denied | initially empty |
| A after local choice and restart | denied | granted | A's values only |
| B after A's choice | denied | denied | B's values only |
| Restored A | denied | granted | copied A values |
| Configuration-only clone | denied | denied | empty |
| Original A at end | denied | granted | unchanged A values |

The private generated report is
`C:\NeAntikBuild\qa\browser-permission-isolation-v082-20261013-c.json`.
It contains only synthetic tokens and local profile IDs; it is not committed.

## Boundaries

The permission choice was injected into an already closed test profile's
Preferences file. This verifies Chromium's observed cross-profile separation
and the product's backup/clone behavior, but not the UI workflow for granting
permission. It does not cover downloads, extension storage, other browser
permissions, another Windows account or cross-machine encrypted cookies.
Those remain open P3 gates.

## Synthetic extension storage — 13 October 2026

The separate [extension isolation audit](../tools/extension_isolation_audit.py)
used the exact extracted v0.8.4-preview Chromium from release source commit
`7730d6300cf17ceca06dd8219cdf6d7bf1b48be3` (portable ZIP SHA-256
`eff5ba66f6a564eb0260bf2fa0635d69c5c79590d8a27f7b7230deb22659b597`;
`chrome.exe` SHA-256
`751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`).
It built a synthetic unpacked Manifest V3 extension in a disposable temporary
directory. Only owned headless Chromium processes loaded it; no user's browser
or extension was opened. A loopback page and rejecting loopback proxy kept the
test's background requests from being forwarded.

The same extension ID wrote different `chrome.storage.local` values in fresh
profiles A and B. B could not read A's value, both retained their own values
after restart, a same-machine backup/restore retained A's value, and the
product's actual configuration-only clone handler created a profile without
it. Eight checks passed. The private report is
`C:\NeAntikBuild\qa\extension-isolation-v084-20261013-c.json`; it records
boolean checks, not the synthetic values or browser data. An initial failed
harness run incorrectly treated an existing Preferences file as initialization
failure; the harness was corrected and rerun. That run is not evidence of a
product defect.

This covers only one unpacked extension and its local-storage API on one
Windows 11 host. It does **not** test Chrome Web Store installation, extension
network privileges, a malicious extension, extension updates, another Windows
account or portable restoration on another machine. Extension data in backups
may be sensitive and backups remain unencrypted. P3 is still open.
