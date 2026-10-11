"""Generate Windows version resources and preserve the build runtime's notices.

Only generated build output is written. This helper never touches application Data.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import re
import shutil
import sqlite3
import ssl
import sys
import tkinter
from pathlib import Path


def prepare(version_file: Path, output: Path) -> None:
    release = json.loads(version_file.read_text(encoding="utf-8-sig"))
    version = release.get("version", "")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?", version):
        raise ValueError("Invalid release version")
    numbers = release.get("file_version")
    if not isinstance(numbers, list) or len(numbers) != 4 or any(type(n) is not int or not 0 <= n <= 65535 for n in numbers):
        raise ValueError("file_version must contain four uint16 integers")
    if ".".join(map(str, numbers[:3])) != version.split("-")[0]:
        raise ValueError("file_version disagrees with version")
    if platform.machine().lower() not in {"amd64", "x86_64"} or sys.maxsize <= 2**32:
        raise RuntimeError("The current release requires an x64 Python runtime")
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Use Python 3.12 for this release")
    output.mkdir(parents=True, exist_ok=True)
    licenses = output / "licenses"
    licenses.mkdir(exist_ok=True)
    base = Path(sys.base_prefix)
    tcl = tkinter.Tcl()
    tcl_version = str(tcl.call("info", "patchlevel"))
    if not tcl_version.startswith("8.6."):
        raise RuntimeError("Review Tcl license and runtime compatibility before changing Tcl versions")
    if not ssl.OPENSSL_VERSION.startswith("OpenSSL 3."):
        raise RuntimeError("Review the OpenSSL license before changing its runtime major version")
    notices = {
        "Python-LICENSE.txt": base / "LICENSE.txt",
        "Tk-license.terms": base / "tcl" / "tk8.6" / "license.terms",
        "Tcl-license.terms": Path(__file__).parent / "licenses" / "Tcl-license.terms",
        "OpenSSL-LICENSE.txt": Path(__file__).parent / "licenses" / "OpenSSL-LICENSE.txt",
    }
    dependencies = {}
    for package in ("pyinstaller", "pywin32", "pywin32-ctypes"):
        dist = importlib.metadata.distribution(package)
        dependencies[package] = dist.version
        requirements = version_file.parent / "requirements-build.txt"
        if requirements.is_file() and f"{package}=={dist.version}" not in requirements.read_text(encoding="utf-8").splitlines():
            raise RuntimeError(f"Installed {package} does not match requirements-build.txt")
        found = [f for f in dist.files or () if "license" in Path(f).name.lower() or "copying" in Path(f).name.lower()]
        if not found:
            raise RuntimeError(f"Missing license for {package}")
        for index, file in enumerate(found):
            notices[f"{package}-{index + 1}-{Path(file).name}"] = Path(dist.locate_file(file))
    for name, source in notices.items():
        if not source.is_file():
            raise FileNotFoundError(f"Required runtime notice missing: {source}")
        shutil.copyfile(source, licenses / name)
    runtime = {
        "python": platform.python_version(),
        "architecture": "x64",
        "tcl": tcl_version,
        "tk": str(tkinter.TkVersion),
        "sqlite": sqlite3.sqlite_version,
        "openssl": ssl.OPENSSL_VERSION,
        "dependencies": dependencies,
        "licenses": sorted(notices),
    }
    (output / "runtime-components.json").write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")
    fields = {
        "FileDescription": "NeAntik Win portable browser",
        "FileVersion": ".".join(map(str, numbers)),
        "InternalName": "NeAntikWin",
        "OriginalFilename": "NeAntikWin.exe",
        "ProductName": "NeAntik Win",
        "ProductVersion": version,
    }
    strings = ",\n".join(f"StringStruct({key!r}, {value!r})" for key, value in fields.items())
    resource = (
        "VSVersionInfo(\n"
        f"ffi=FixedFileInfo(filevers={tuple(numbers)!r}, prodvers={tuple(numbers)!r}, "
        f"mask=0x3f, flags={2 if release.get('channel') == 'preview' else 0}, OS=0x40004, fileType=1, subtype=0, date=(0,0)),\n"
        f"kids=[StringFileInfo([StringTable('040904B0', [{strings}])]), "
        "VarFileInfo([VarStruct('Translation', [1033, 1200])])])\n"
    )
    (output / "windows-version-info.txt").write_text(resource, encoding="utf-8")
    print(f"Build metadata ready: {version}; Python {runtime['python']}; {len(notices)} license texts")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    prepare(args.version_file, args.output)
