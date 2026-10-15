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
contains verdicts, not browser storage values. This specific browser test covers
one manager process on one Windows 11 host; the separate independent-process
delete-recovery gate below passed 8/8. Another Windows session/account,
power-cut recovery, GUI actions and public-network routes remain **NOT RUN**;
Gate P3 stays open.

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
interruption point and process-crash recovery; restore-process termination is
separately covered below. A real power cut, another Windows session/account
and hostile same-user processes remain **NOT RUN**. Gate P3 stays open.

The same independent-manager test was rerun on source commit
`f5e2fde4defd85bdfad575ebe171ebe5d5bb88e0`; the Windows unittest passed and
asserted the same 8/8 recovery invariants. This confirms the source gate still
passes after the settings-transfer documentation update; it is not a new
packaged-binary or power-loss test.

## Restore publish/DB interruption fault-injection — 14 October 2026

On source commit `1f97d4b6c6c9c6cdcb61ad98032196e4f3bd0f48`, a new regression
test exercised the actual `Storage.restore_profile` path with synthetic
backup data. It injected a `BaseException` immediately after the staging
directory was atomically renamed into the profile directory and before the DB
insert, then opened a fresh `Storage` instance. Recovery rebuilt the profile
row, preserved both source and restored test files, and cleared the operation
journal. The full `test_nevision_win.py` suite passed 90 tests with one skip.
This tests the exact transaction boundary and startup roll-forward, but the
injected exception still runs Python's `finally`; it is not a child-process
kill or power-loss test.

## Restore recovery after controlled worker-process crash — 14 October 2026

The extended `tools/two_manager_process_gate.py` passed its dedicated Windows
test on harness source commit `531648a1c73e795f8cf7079e54ec31b14c429a13`:
`test_restore_process_crash_after_publish_recovers_profile_and_data`. It runs
the real `Storage.restore_profile` against a synthetic ZIP and pauses its child
after the staging directory is atomically published, when the durable restore
journal exists but before the profile DB insert. The parent verified that
pre-commit state, a second manager received `busy` without changing it, then
instructed the child to terminate with exit code 73. A fresh manager recovered
the restored DB row and data, preserved the source profile, and cleared the
journal. All **10/10** restore-crash invariants passed; all four tests in
`test_two_manager_process_gate.py` passed on this host. This is a controlled
process termination on one Windows 11 host and a disposable root, not a real
power interruption, packaged-GUI test, other Windows account or second PC.
P3 remains open.

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

## P3.3 settings-only transfer regression — 14 October 2026

Four source tests passed on `6af9541bf6a1163e587d3bec84f099492e2fdea9` for the
existing minimal export/import flow: allowed metadata is copied into a new
empty profile; proxy username/password, notes, cookies and old identity seed
are excluded; malformed, oversized and untrusted fields fail without partial
profile creation; and native-mode templates are refused if the receiving
portable lacks the required core. Ordinary templates remain importable without
that core. The current UI already provides export/import confirmation with an
explicit warning that sessions and proxy must be configured again. These are
source-level tests, not a GUI test or proof of operation under a different
Windows account/computer; DPAPI migration and cross-machine cookies remain
**NOT RUN**.

## Native backup/core compatibility preflight — 14 October 2026

Source commit `21d75f382425e12c70b3b8f6ec183a71c0fc28bf` adds a restore-time
guard: the UI checks whether this portable build exposes the compatible native
core before restoring a native-mode backup. If unavailable, restore stops
before profile creation, extraction staging or journal creation. The ordinary
profile backup path remains available. Both targeted regressions and the full
`test_nevision_win.py` suite passed at this source state (91 tests, 1 skipped);
the isolated restore-process crash-recovery gate also passed (10/10 invariants).
This is source/UI-logic coverage only: incompatible native backup restoration
was not exercised in a packaged GUI or across separate portable installations.
The public 0.8.16-preview binary and Site do not include this source change;
no new release was built or published in this cycle. P3 remains open.

## Post-publication exact 0.8.19-preview ZIP storage check — 15 October 2026

The storage integration was run against the `chrome.exe` extracted from the
exact public 0.8.19-preview ZIP (ZIP SHA-256
`adec43f1fb17c1864cac0ca826b329162a0f7b56d924f87ecc4d7aa1a4910d2a`;
`chrome.exe` SHA-256
`7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`). On
harness source commit `c988ec25dfaced8733909bd82f6cf1f959150ce9`,
`tools/browser_integration.py` passed **21/21 assertions across seven visits**.
It verified A/B separation and same-machine restart persistence for synthetic
cookies, localStorage, IndexedDB, Cache Storage and service-worker state;
notification defaults and the A-only synthetic permission fixture; real
product backup/restore to a new profile; and the real configuration-only clone
starting empty. All browser-created profiles were disposable, the loopback
page was the only navigated origin, and background HTTP(S) met a rejecting
loopback proxy. Backup contents were declared unencrypted and sensitive; this
does not test cross-PC DPAPI/App-Bound credential portability.

The first exact-ZIP attempt was **INCONCLUSIVE** because the QA harness launched
the extracted engine from a path that lacked Chromium sandbox read ACLs; stderr
identified `sandbox_win.cc` access denial (`0x5`). No profile-storage
assertion ran. The harness now copies the engine into its own disposable QA
root, applies the product-equivalent read-only sandbox ACL, and requires the
prepared executable SHA-256 to equal the supplied binary before launch. The
rerun passed; this repaired a test-fixture setup error and did not change
browser product code or the public ZIP. Full unittest suite on the same harness
commit: **266 PASS, 3 skipped**. The report remains local; SHA-256
`d42b68d399cc5203f1265546cb1c95a035b2a3d475856f549f86142ed4d371b0`.
Harness SHA-256:
`3df6060a830cfcaa29b97210e02995258e3cd7af71c4d8730cf4d3c147f05830`.

This remains one Windows 11 host, one account, headless source integration and
one loopback origin—not packaged GUI/manual interaction, another account or
PC, downloads/extensions, arbitrary origins, external routing or a complete
inventory of browser storage. P3 remains open.

## Post-commit restore/delete journal recovery — 15 October 2026

Source commit `65923978f9e9c1af89d7437763d4585bd04178e6` adds two fault-
injection regressions to `test_nevision_win.StorageTests`. Each runs the real
storage operation with synthetic data, raises a process-stop exception at the
final journal-cleanup call (after the profile filesystem move and SQLite
transaction have committed), then constructs fresh `Storage` instances to
exercise startup reconciliation twice. Delete retains the deleted profile data
and an unrelated profile while clearing the completed journal; restore retains
the restored profile/data and its source while clearing the journal. The entire
`StorageTests` class passed **33/33** on that exact source commit. This is a
source-level deterministic crash-window test, not a power-loss/filesystem
durability test, packaged GUI restore, or cross-account/PC verification; no
browser process or user `Data/` was used and product code/binary were unchanged.

## Post-publication exact 0.8.27-preview ZIP storage check — 15 October 2026

`tools/browser_integration.py` ran against Chromium extracted from the exact
public 0.8.27-preview ZIP (ZIP SHA-256
`daa9da39bb19428e2989439b6200fbf4d9ee0a5d999f834880e2bbb800ba2eb0`;
`chrome.exe` SHA-256
`7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`). The
release product/storage harness files are unchanged from binary source commit
`5e1b83b7dcdf2a965a2f53c33aab73522fed6879`. The gate passed **21/21
assertions across seven Chromium visits**: synthetic cookie, localStorage,
IndexedDB, Cache Storage and service-worker separation/persistence for profiles
A/B; permission defaults and an A-only synthetic notification fixture; real
backup/restore to a new profile; and configuration-only clone starting empty.
Backup correctly disclaimed encryption and omitted proxy credentials. Exactly
28 background HTTP(S) requests were blocked by the local rejecting proxy; only
the local test origin was navigated.

Harness SHA-256 `3df6060a830cfcaa29b97210e02995258e3cd7af71c4d8730cf4d3c147f05830`;
product `nevision_win.py` SHA-256
`24f8e7c238a0efd015bb416417fb935e99eecc2521bf47040caf2c5f26049914`;
local report SHA-256
`1b64857fec84cf7c8475c83deead9e6a18a1a02403301acf7cc8bed4e6886a23`.
The raw report remains only in the ignored QA build folder. This is one Windows
11 host/account and headless source integration—not GUI, Windows 10, another
host/account, cross-machine DPAPI, arbitrary extensions, or external routing;
P3 remains open.
