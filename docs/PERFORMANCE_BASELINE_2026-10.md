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
for the five-run median/spread acceptance target in P4.3. Next, measure
**packaged** manager cold/warm startup and profile browser launch at least
five times on a disposable public-ZIP extraction, record elapsed time and
memory, and inspect accessibility before changing UI implementation. Keep
processes and measurements isolated from user profiles. No product code or
release artifact was changed based on this baseline alone.
