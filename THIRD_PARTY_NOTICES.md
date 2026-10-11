# Third-party notices

NeVision Win source and build tooling currently use the following direct dependencies:

| Component | Version | License / reference |
| --- | ---: | --- |
| Python | 3.12 | [PSF License](https://docs.python.org/3/license.html) |
| PyInstaller | 6.21.0 | [GPL-2.0-or-later with bootloader exception](https://pyinstaller.org/en/stable/license.html) |
| pywin32 | 311 | [BSD-style license, Mark Hammond and contributors](https://github.com/mhammond/pywin32/blob/main/win32/License.txt) |
| pywin32-ctypes | 0.2.3 | [BSD-3-Clause](https://github.com/enthought/pywin32-ctypes) |
| Pillow (development only) | 10.4.0 | [HPND License](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |

The application does not bundle Chrome or Microsoft Edge. A release also includes the Python
runtime's Tcl/Tk, SQLite, libffi, compression libraries, and OpenSSL components selected by
PyInstaller. Exact runtime versions are recorded in `runtime-components.json` inside the ZIP.
SQLite is [public domain](https://www.sqlite.org/copyright.html). The Windows VC runtime
files originate from the installed official Python distribution.

`build.ps1` now preserves the actual installed Python aggregate license, Tk license,
pywin32 notices, pywin32-ctypes license and PyInstaller copying text in the release's
`licenses/` directory. It also includes the Tcl 8.6 and OpenSSL 3.0 license texts obtained
from the upstream versioned sources below. A missing required text fails the build.
The Python aggregate notice includes notices for its incorporated standard-library code;
the supplemental files preserve Tcl/Tk and OpenSSL distribution notices separately.

- [Tcl 8.6.15 license](https://github.com/tcltk/tcl/blob/core-8-6-15/license.terms)
- [OpenSSL 3.0.16 Apache-2.0 license](https://github.com/openssl/openssl/blob/openssl-3.0.16/LICENSE.txt)
- [PyInstaller licensing and executable exception](https://pyinstaller.org/en/stable/license.html)

Changing Python/Tcl/OpenSSL versions or bundling a browser requires reviewing this inventory
and the notices before publication. Pillow is used only to regenerate the project icon;
it is not an application runtime dependency. These third-party notices do not select a
license for NeVision Win's own source code or branding.
