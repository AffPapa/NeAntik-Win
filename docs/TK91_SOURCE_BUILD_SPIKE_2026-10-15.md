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

## Results

- **PASS — source build smoke:** `tclsh91.exe` reported Tcl 9.1.0 and exited
  successfully.
- **PASS — basic native GUI smoke:** `wish91.exe` opened a visible test window
  containing a ttk label, entry, button, and a Canvas drawing. It was a scratch
  fixture, not NeAntik UI or a packaged Python app.
- **FAIL — observed UIA widget semantics:** the captured UIA tree showed no
  named Tk child controls. This is scoped to this local test/window and does
  not establish MSAA/screen-reader failure.
- **NOT RUN — MSAA/screen reader:** NVDA was not installed or running. The
  fixture's Tk 9.1 role/name queries returned `0`; upstream's `accessibility.tcl`
  intentionally defines the script accessibility layer as a no-op if the
  screen-reader check is absent/false. Other accessibility clients were not
  audited. This is consistent evidence, not a substitute for an active screen
  reader test.
- **NOT RUN — application/runtime gates:** CPython `_tkinter` build and ABI,
  PyInstaller packaging, packaged app launch/resources, licensing in a portable
  archive, startup/memory/size comparison, keyboard-only workflow, NVDA, and
  Narrator.

Upstream references: [Tk TIP 733](https://core.tcl-lang.org/tips/doc/main/tip/733.md),
[Tk 9.1 accessibility manual](https://www.tcl-lang.org/man/tcl9.1/TkCmd/accessible.html),
and [official Tcl/Tk downloads](https://www.tcl-lang.org/software/tcltk/download.html).

## Next gate

Do not replace production Tk 8.6 or change packaging pins based on this spike.
First build a matching isolated CPython `_tkinter` against Tcl/Tk 9.1, verify its
ABI and licenses, package a tiny synthetic app, measure the actual archive and
startup, then test named controls with MSAA + NVDA. Test UIA + Narrator
separately; Tk's upstream documentation says its Windows UIA bridge is not
robust. The Tk Canvas itself still needs a semantic alternative/control.
