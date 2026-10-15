# Isolated Tcl/Tk 9.1.0 source-build spike — 2026-10-15

This was a scratch experiment only. No production runtime, dependency pin,
portable package, website, or release was changed.

## Inputs and build

Officially listed Tcl/Tk 9.1.0 source archives were downloaded to a disposable
scratch directory and built as x64 with MSVC 14.51.36231. Source archive hashes:

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| `tcl910-src.zip` | 13,909,004 | `E425CA433EBBD84479BAC7ABB684E71F4EFA3344FED12E67D0A3771E1D6D9D82` |
| `tk910-src.zip` | 5,561,409 | `D6F1183BB19661915CDB4E67A7620A6555D3E4CAEA08E9118CA22316FABDE433` |

The stage contained 195 files / 14,165,115 bytes. This is not an app-package
size delta: it includes Tcl/Tk headers, scripts and support libraries.

| Built file | Bytes | SHA-256 |
| --- | ---: | --- |
| `tcl91.dll` | 3,782,636 | `996924B97C232A0CF90BE0497E9C42F0765B6CC9EB3C68F8B192827148D338E2` |
| `tcl9tk91.dll` | 2,698,414 | `E6AE7225C63FD117432F0AABAE75FEF0C64D7A9E3435857D51E9EECCA988C030` |
| `tclsh91.exe` | 387,584 | `DB23448674E6EDE055CF3BB02FAC36AE597566C3C5B40F14C20B97AD7EEB6000` |
| `wish91.exe` | 386,048 | `E382E2276E11F3FEA8A563E9A17260FEE66F7E7F93E53A2F5935CEE2A86A1C84` |

CPython 3.12.10 source (`Python-3.12.10.tar.xz`, 20,520,960 bytes) matched
the MD5 published on [Python.org](https://www.python.org/downloads/release/python-31210/);
local SHA-256 was
`07AB697474595E06F06647417D3C7FA97DED07AFC1A7E4454C5639919B46EAEA`.
`_tkinter.pyd` was built from that tag's `Modules/_tkinter.c` and `tkappinit.c`
with the installed matching CPython 3.12.10 headers/import library, Tcl/Tk
9.1.0 headers/import libraries, and external LibTomMath define/library:

| Built file | Bytes | SHA-256 |
| --- | ---: | --- |
| `_tkinter.pyd` | 49,664 | `3A25050447F2ACA9B41071BA9518DDE0B3B50E0DB0B1FC8373234E1FC06C8891` |

## Results

- **PASS — source build smoke:** `tclsh91.exe` reported Tcl 9.1.0 and exited
  successfully.
- **PASS — basic native GUI smoke:** `wish91.exe` opened a visible test window
  containing a ttk label, entry, button, and a Canvas drawing. It was a scratch
  fixture, not NeAntik UI or a packaged Python app.
- **PASS — isolated Python ABI/runtime smoke:** the custom `_tkinter.pyd`
  imported in the matching CPython 3.12.10 process; Tcl reported `9.1.0`, and
  `expr 6*7` returned `42`. A real Python `tkinter.Tk()` window reported Tcl
  and Tk `9.1.0` on `win32` and rendered ttk Label/Entry/Button controls.
  This was not a full CPython rebuild or test of NeAntik's current app ABI.
- **PASS — synthetic PyInstaller portable folder/ZIP:** PyInstaller 6.22.3
  produced a 997-file onedir folder of 31,327,844 bytes, including the custom
  `_tkinter.pyd`, Tcl/Tk 9 DLLs, and both library data trees. No Tcl/Tk 8.6
  files were present. Tcl and Tk `license.terms` were included. The compressed
  folder ZIP was 13,813,544 bytes, SHA-256
  `1F291A904C59EB6837D9CB7F9E57D4FFAEA913D4C7B063284E48722BDA0709A5`;
  after extraction, its EXE opened and reported `frozen=True`, Tcl/Tk `9.1.0`,
  and internal `_tcl_data`/`_tk_data` paths with no external Tcl/Tk environment
  variables. EXE SHA-256:
  `4D24936D14BAA2BE668C1330B793FEBFEFA0F8FFAF9903C255D8ACF48ED52628`.
- **FAIL — observed UIA widget semantics:** the captured UIA tree showed no
  named Tk child controls. This is scoped to this local test/window and does
  not establish MSAA/screen-reader failure.
- **NOT RUN — MSAA/screen reader:** NVDA was not installed or running. The
  fixture's Tk 9.1 role/name queries returned `0`; upstream's `accessibility.tcl`
  intentionally defines the script accessibility layer as a no-op if the
  screen-reader check is absent/false. Other accessibility clients were not
  audited. This is consistent evidence, not a substitute for an active screen
  reader test.
- **INCONCLUSIVE — Python frozen UIA capture:** CUA returned no accessibility
  tree for the packaged test window. The screenshot proved the form rendered;
  it did not prove its UIA semantics.
- **NOT RUN — product/release gates:** NeAntik application runtime migration,
  full dependency-notice audit, size/startup/memory comparison against the
  production package, keyboard-only profile workflow, MSAA + NVDA, and UIA +
  Narrator.

## NeAntik application compatibility spot check

After the isolated packaging smoke, a disposable copy of the minimum NeAntik
0.8.19-preview application files from source HEAD
`8c77638241abc1607b33c22688b18c14c4811bd3` was launched against this Tcl/Tk
9.1 runtime. This was a scratch-only GUI check: no production files, portable
archive, release, Site, Chromium process, real profile, or proxy was used.

- **PASS — application window render:** the copied application opened with the
  expected `NeAntik Win 0.8.19-preview` title and the profiles dashboard
  rendered.
- **PASS — profile form render:** opening “Создать профиль” displayed the
  profile form and its visible fields/actions.
- **NOT RUN — profile entry/save flow:** CUA exposed no accessible focus/tree
  element for the focused name field, so no text was entered and no profile
  saved. The scratch app initialized its own temporary `Data` directory; it is
  not user or production data.
- **INCONCLUSIVE — close/control automation:** a single Alt+F4 attempt did not
  remove the window from the observed window list; the follow-up state read
  failed because the foreground window did not report a process id. No further
  UI actions were attempted.
- **NOT RUN — accessibility/performance/release gates:** no active screen
  reader was tested, and this was not the production portable build. It does
  not qualify the app for runtime migration or release.

This improves confidence that the app's basic startup widgets are compatible
with the scratch runtime, but does not change the Tk 8.6 production runtime or
the migration decision.

Upstream references: [Tk TIP 733](https://core.tcl-lang.org/tips/doc/main/tip/733.md),
[Tk 9.1 accessibility manual](https://www.tcl-lang.org/man/tcl9.1/TkCmd/accessible.html),
[official Tcl/Tk downloads](https://www.tcl-lang.org/software/tcltk/download.html),
and [PyInstaller changelog](https://pyinstaller.org/en/latest/CHANGES.html).

## CPython source compatibility correction

Follow-up inspection of the exact installed version's upstream source,
[CPython 3.12.10 `Modules/_tkinter.c`](https://github.com/python/cpython/blob/v3.12.10/Modules/_tkinter.c),
found Tcl 9 compatibility code (`Tcl_Size` fallback, Tcl 9 object-type
handling) and an existing `Tcl_FindExecutable` call. An earlier investigation
had incorrectly treated that call as absent; that concern is withdrawn. The
source inspection was followed by the focused build and runtime test above.
`TclZipfs_AppHook` is not present in that source file; this spike therefore used
the regular external Tcl/Tk library directories during analysis and verified
that the PyInstaller runtime hook redirected the extracted test app to its
bundled data trees. That is not a full CPython or application migration test.

## Next gate

Do not replace production Tk 8.6 or change packaging pins based on this spike.
Next adapt the isolated build to the actual portable layout and repeat the
check on an isolated, packaged app; audit every bundled license notice;
measure startup/memory/size against the production baseline; test keyboard-only
profile flows and named controls with MSAA + NVDA. Test UIA + Narrator
separately; Tk's upstream documentation says its Windows UIA bridge is not
robust. The Tk Canvas itself still needs a semantic alternative/control.
