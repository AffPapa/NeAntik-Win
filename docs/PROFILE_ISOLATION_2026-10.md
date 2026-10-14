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

## Public 0.8.7-preview profile and cookie follow-up — 13 October 2026

The `browser_integration.py` and `cookie_integration.py` harnesses were run
against the engine extracted from the repeat-downloaded public 0.8.7-preview
ZIP (ZIP SHA-256
`9bf12392f8c8057763024cb88666679e8d9938e73cc050f976e7057b5c5234d1`,
`chrome.exe` SHA-256
`751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`). The
release was built from source commit
`d2e6eac9a50f5edfa474ec72aff9ace64c2e8801`; `nevision_win.py` is unchanged
between that commit and the audit checkout. The engine's AppContainer ACL was
prepared only inside the isolated public-download extraction; profile data
and test reports remained outside the repository.

- **Storage/permissions/backup/clone: PASS**, 21 assertions over seven real
  headless Chromium visits. Synthetic Profile A and B were isolated across
  cookies, localStorage, IndexedDB, Cache Storage, service workers and
  permissions; product backup/restore retained A's synthetic state, while a
  configuration-only clone began without it. The notification choice was
  inserted into A's closed disposable Preferences file, so this does not test
  the GUI permission workflow.
- **Third-party cookies: PASS**, with a positive control. The allow-control
  profile sent the synthetic third-party cookie; the privacy-default profile
  did not. Two loopback HTTPS test names, a generated test certificate and a
  rejecting proxy constrained the run.

Private summaries are
`C:\NeAntikBuild\qa\profile-isolation-followup-0.8.7-20261013.json` and
`C:\NeAntikBuild\qa\cookie-isolation-followup-0.8.7-20261013.json`; neither
report nor any profile values are committed. These remain one-host tests; they
do not cover every permission, downloads, extension behavior, another Windows
account or cross-machine encrypted session portability. P3 remains open.

## Concurrent A/B launcher gate — 14 October 2026

The separate `tools/concurrent_profile_integration.py` harness ran against
the extracted public 0.8.9-preview portable engine (`chrome.exe` SHA-256
`751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`).
It copied the engine into an owned temporary root and opened two synthetic
profiles at once through the real `BrowserLauncher.launch` path. A loopback
page held both headless Chromium processes open while the test checked
distinct profile paths and active locks; each profile wrote its own cookie,
localStorage, IndexedDB, Cache Storage and service-worker state.

**17/17 bounded checks passed.** A duplicate launch and backup/delete of busy
A were rejected while B remained active; both browser jobs and profile locks
closed afterward. The private report is
`C:\NeAntikBuild\qa\concurrent-profiles-v0.8.9-preview-20261014.json` and
contains verdicts, not browser storage values. This covers one manager process
on one Windows 11 host. Two independent manager processes, another Windows
session/account, power-cut recovery, GUI actions and public-network routes
remain **NOT RUN**; Gate P3 stays open.

## Two independent managers and process-crash recovery — 14 October 2026

`tools/two_manager_process_gate.py` used three independent Python processes
against one newly created, marked disposable `Storage` root. The first held
the product's `__data_recovery__` Windows mutex after a durable delete journal
and profile-directory move. The second manager received `busy` without
changing the profile row, moved synthetic data or journal. After the first
process deliberately exited while holding the mutex, the third manager
recovered the original profile data and cleared the journal.

**8/8 bounded assertions passed** on this host. This is the source `Storage`
path, not the packaged GUI executable or a browser test. It checks one delete
interruption point and process-crash recovery; restore interruption, a real
power cut, another Windows session/account and hostile same-user processes
remain **NOT RUN**. Gate P3 stays open.

## 0.8.15-preview candidate storage regression — 14 October 2026

The exact rebuilt candidate ZIP from binary source commit
`5434718dd14a5ea0edc20c440c801a873c9fbcf4` (ZIP SHA-256
`fd9eedf2b9f6b9f3b42b51eb5ce29608e41b165c7ec2d282e17926c4f2b44ead`)
passed the loopback `browser_integration.py` storage/permission/backup/clone
scenario: **21/21 assertions across seven real Chromium visits**. Chromium
`chrome.exe` SHA-256 was
`751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`.
The test used the extracted candidate's `Engine/Chromium` directory and owned
temporary profiles; it did not touch user Data or launch the GUI. The first
attempt was invalid because the harness directly launched Chromium without
the AppContainer read/execute ACL normally prepared by `BrowserLauncher`.
After applying that same ACL only to the extracted engine directory, one
retry passed; the ZIP bytes were unchanged. This verifies product `Storage`,
privacy-default and backup/clone behavior with the candidate Chromium. The
harness starts `chrome.exe` directly, so it does not verify the product's
`BrowserLauncher` or packaged-GUI wiring. Downloads, external networking,
another account or PC, and full P3 remain untested.

## Public 0.8.16-preview concurrent-profile regression — 14 October 2026

`tools/concurrent_profile_integration.py` was run against the exact
repeat-downloaded public archive, whose SHA-256 is
`8b9099f20dce636966e8bfac358e7c4bc1c616c204e4da128a7d41b81db42116` and whose
`chrome.exe` SHA-256 is
`751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`. The
test harness source commit was `005c5d3d32ffc3eb4de3a47a0c49dedaf45d769a`;
17/17 boolean checks passed on one Windows 11 host. Two simultaneous synthetic
profiles were confirmed running with separate storage namespaces and service
workers; duplicate launch and backup/delete while busy were refused, each
profile's lock was released, and both processes used the bundled Chromium.
The test uses owned headless processes and loopback-only pages, not personal
profile data, the product GUI, another Windows account or another computer.
It is bounded evidence for concurrent manager/profile isolation, not a claim
that all browser state or network identity is isolated. The report is outside
the repository at
`C:\NeAntikBuild\concurrent-profiles-v0.8.16-preview-20261014.json`.

## Public 0.8.16-preview packaged secret/backup self-test — 14 October 2026

The exact release `NeAntikWin.exe` SHA-256
`caa05a1dc223955aaf1ee776128cae068886641c8a929f953c19654a47576701` was run
with `--self-test` in a hidden process; exit code was 0, expected PASS output
was captured, and stderr was empty. The packaged self-test uses a synthetic
DPAPI value and a temporary `Data` root to check protect/unprotect roundtrip,
proxy vault storage, profile backup/restore and long-path operations. It
deletes its own temporary root. Three matching source tests also passed on
source commit `16bc02603d8c147b9599826b44e255a49ac81b5b`: DPAPI-backed proxy
backup/restore, backup manifest sensitivity wording, and no proxy credentials
in HTTP(S) Chromium arguments. These checks do not prove protection from
malware or other processes under the same Windows account, Windows clipboard
history, a different account/computer, or cryptographic suitability for
portable encrypted session backups. Browser session backups remain sensitive
and are not encrypted by this gate.

## Public 0.8.16-preview extension storage isolation — 14 October 2026

`tools/extension_isolation_audit.py` ran against a disposable ACL-prepared copy
of the exact public Chromium from the same ZIP noted above; the copied
`chrome.exe` retained SHA-256
`751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`. Harness
source commit: `84e953969b50228497bda9f7a222a86cc5b77c71`. All 8 checks passed:
the same synthetic unpacked Manifest V3 extension had separate
`chrome.storage.local` in A/B; each value persisted after restart; A retained
its value after same-machine backup/restore; and a configuration-only clone
had no extension value. Test pages were loopback-only and external startup
requests met a rejecting local proxy. This does not assess malicious extension
permissions/code, store installation or update behavior, arbitrary extension
APIs, another Windows account or PC, or the privacy of extension data in an
unencrypted backup. Raw browser data and report were not published; the report
is at
`C:\NeAntikBuild\extension-isolation-v0.8.16-preview-20261014.json`.
