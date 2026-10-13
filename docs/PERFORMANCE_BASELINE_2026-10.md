# P4.3 source-UI performance baseline — 13 October 2026

This is a **single-host source-code measurement**, not a packaged EXE startup
benchmark or a claim that the app is as fast as another editor. The existing
[`benchmark_runtime.py`](../tools/benchmark_runtime.py) used Python 3.12.10
on Windows 11 build 26200 with 16 logical CPUs and disposable SQLite/profile
data. It did not open the user's `Data/` or bundled Chromium. Checkout HEAD
before this documentation change: `b55ea6ec8dd3dde141aadbbee748953cf09ec500`.
The private raw report is
`C:\NeAntikBuild\qa-public-v0.8.6-preview-20261013\benchmark-main-b55ea6e.json`.

| Synthetic profiles | UI ready, one sample | Search median / p95 (30) | Refresh median / p95 (30) |
| ---: | ---: | ---: | ---: |
| 10 | 115.784 ms | 1.016 / 1.191 ms | 6.095 / 7.177 ms |
| 100 | 98.694 ms | 1.420 / 1.606 ms | 6.748 / 7.780 ms |
| 1000 | 112.735 ms | 6.469 / 8.038 ms | 16.299 / 17.436 ms |

No list/search bottleneck was demonstrated by this fixture. The one-sample
UI-ready figure excludes Python interpreter or frozen EXE process startup,
disk cold cache, packaged assets and actual browser launch; it is insufficient
for the five-run median/spread acceptance target in P4.3. The packaged-manager
observation below addresses one part of that gap. Next, measure actual
Chromium launch, UI readiness, cold-cache behavior and accessibility on
disposable profiles before changing UI implementation. Keep processes and
measurements isolated from user profiles. No product code or release artifact
was changed based on this baseline alone.

## Packaged portable-manager observation — 13 October 2026

`tools/benchmark_packaged_startup.py` verified and extracted the **publicly
downloaded** 0.8.7-preview ZIP into a disposable directory, then started and
closed its GUI five times. ZIP SHA-256:
`9bf12392f8c8057763024cb88666679e8d9938e73cc050f976e7057b5c5234d1`;
EXE SHA-256: `e3c97c1623dee5fa2f59d08744b8006d8ca82e2ef3fecf189785688e34bf07eb`;
binary source commit: `d2e6eac9a50f5edfa474ec72aff9ace64c2e8801`.
The disposable extraction was removed after testing; no user `Data/` was read.
Private raw report: `C:\NeAntikBuild\qa-performance-v0.8.7-preview-20261013\packaged-startup-five-runs.json`.

| Visible-window observation | Result |
| --- | ---: |
| Run 1 (fresh extracted Data) | 707.052 ms |
| Runs 2–5 (same extracted folder) | 208.546, 209.291, 210.273, 209.545 ms |
| Median of five | 209.545 ms |
| Manager private memory after 5 s idle | 21.95–22.20 MiB |

**PASS** means five ordinary launches reached a visible titled main window
and exited under the harness. This is not a cold OS-cache benchmark, proof
that every widget was usable, browser/Chromium launch timing, Windows 10 QA,
accessibility QA, or a cross-machine performance guarantee. The existing
source-UI numbers above and these packaged measurements have different
boundaries and must not be directly compared.
