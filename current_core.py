"""NeAntik's own Chromium 155 identity and bundle contract (stdlib only).

Native engine availability is proved by bundle hashes and the compiled core's
own info command. No stock browser fallback, page injection or old engine flags.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import subprocess
import tempfile
from typing import Any, Mapping

ENGINE_ID = "neantik-chromium"
ENGINE_VERSION = "155.0.8059.40"
SOURCE_COMMIT = "cfaadc5a132d78e1828635aa8405a499f3e14864"
ENGINE_DIRECTORY = Path("Engine") / "NeAntikChromium"
MANIFEST_NAME = "core-manifest.json"
MANIFEST_FORMAT = "neantik-native-core-v1"
CPU_OPTIONS = (2, 4, 8, 12, 16, 24, 32, 64)
MEMORY_OPTIONS = ("2", "4", "8", "16", "32")
REQUIRED_CAPABILITIES = ("stable_seed", "hardware_concurrency", "device_memory",
                         "canvas_opaque_srgb_uint8", "timezone",
                         "webrtc_non_proxied_udp_proxied_webframes")


class CoreError(ValueError):
    pass


def ordinary_identity() -> dict[str, Any]:
    return {"schema": 1, "mode": "ordinary"}


def new_identity(*, cpu: int = 8, memory: str = "8", timezone: str = "system") -> dict[str, Any]:
    return validate_identity({"schema": 1, "mode": "native", "engine_id": ENGINE_ID,
                              "seed": 1 + secrets.randbelow(0xFFFFFFFFFFFFFFFF),
                              "hardware_concurrency": cpu, "device_memory": memory, "timezone": timezone})


def validate_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or type(value.get("schema")) is not int or value["schema"] != 1:
        raise CoreError("Неподдерживаемая схема fingerprint-профиля.")
    if value.get("mode") == "ordinary":
        if set(value) != {"schema", "mode"}:
            raise CoreError("Обычный профиль содержит несовместимые fingerprint-настройки.")
        return ordinary_identity()
    fields = {"schema", "mode", "engine_id", "seed", "hardware_concurrency", "device_memory"}
    if set(value) not in (fields, fields | {"timezone"}) or value.get("mode") != "native" or value.get("engine_id") != ENGINE_ID:
        raise CoreError("Fingerprint-профиль несовместим с ядром NeAntik.")
    seed, cpu, memory = value.get("seed"), value.get("hardware_concurrency"), value.get("device_memory")
    if type(seed) is not int or not 1 <= seed <= 0xFFFFFFFFFFFFFFFF:
        raise CoreError("Seed должен быть ненулевым uint64.")
    if type(cpu) is not int or cpu not in CPU_OPTIONS:
        raise CoreError("Выберите поддерживаемые CPU и память fingerprint-профиля.")
    if not isinstance(memory, str) or memory not in MEMORY_OPTIONS:
        raise CoreError("Native-память Windows Chromium 155: 2, 4, 8, 16 или 32 GB. Несовместимые настройки не изменены.")
    timezone = value.get("timezone", "system")
    if not isinstance(timezone, str) or len(timezone) > 128 or (timezone not in ("system", "UTC") and not re.fullmatch(r"[A-Za-z0-9_+\-]+(?:/[A-Za-z0-9_+\-]+){1,3}", timezone)):
        raise CoreError("Часовой пояс должен быть system, UTC или IANA-именем, например Europe/Berlin.")
    return {"schema": 1, "mode": "native", "engine_id": ENGINE_ID, "seed": seed,
            "hardware_concurrency": cpu, "device_memory": memory, "timezone": timezone}


def serialize_identity(value: Mapping[str, Any]) -> str:
    return json.dumps(validate_identity(value), sort_keys=True, separators=(",", ":"))


def identity_arguments(value: Mapping[str, Any]) -> list[str]:
    value = validate_identity(value)
    if value["mode"] == "ordinary":
        return []
    arguments = [f"--neantik-fingerprint-seed={value['seed']}",
            f"--neantik-hardware-concurrency={value['hardware_concurrency']}",
            f"--neantik-device-memory={value['device_memory']}"]
    if value["timezone"] != "system":
        arguments.append(f"--neantik-timezone={value['timezone']}")
    return arguments


def sha256_file(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


class CoreResolver:
    def __init__(self, portable_root: Path):
        self.root = Path(portable_root).resolve()
        self._signature = None
        self._executable = None

    def _signature_now(self):
        directory = self.root / ENGINE_DIRECTORY
        if not directory.is_dir() or directory.is_symlink() or directory.is_junction() or directory.parent.is_symlink() or directory.parent.is_junction():
            raise CoreError("Native-ядро NeAntik отсутствует. Используйте полный portable-релиз с собственным ядром; обычный Chrome не будет запущен вместо него.")
        signature = []
        for path in sorted(directory.rglob("*")):
            if path.is_symlink() or path.is_junction():
                raise CoreError("Каталог native-ядра содержит ссылку или junction.")
            item = path.stat()
            signature.append((path.relative_to(directory).as_posix(), item.st_size, item.st_mtime_ns, item.st_ctime_ns))
        return tuple(signature)

    @staticmethod
    def _prepare_sandbox_access(directory: Path) -> None:
        """Let Windows AppContainer sandboxes read the bundled engine files.

        ZIP extraction inherits the destination folder's ACL. Many user-writable
        folders do not grant AppContainer read/execute access, which makes
        Chromium's network sandbox fail closed before a window can open. Grant
        only read/execute, with inheritance, to the two Windows package groups;
        never grant write access or touch anything outside this engine folder.
        """
        if os.name != "nt":
            return
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        icacls = system_root / "System32" / "icacls.exe"
        if not icacls.is_file():
            raise CoreError("Не найдена системная icacls.exe для настройки sandbox-доступа к ядру.")
        try:
            result = subprocess.run(
                [str(icacls), str(directory), "/grant:r",
                 "*S-1-15-2-1:(OI)(CI)(RX)", "*S-1-15-2-2:(OI)(CI)(RX)"],
                capture_output=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired as exc:
            raise CoreError("Не удалось завершить настройку sandbox-доступа к ядру.") from exc
        if result.returncode != 0:
            raise CoreError("Windows не разрешила sandbox читать файлы ядра. Проверьте права папки portable.")

    def resolve(self) -> Path:
        try:
            signature = self._signature_now()
            if signature == self._signature and self._executable is not None:
                return self._executable
            directory = self.root / ENGINE_DIRECTORY
            manifest_file = directory / MANIFEST_NAME
            if manifest_file.stat().st_size > 2 * 1024 * 1024:
                raise CoreError("Manifest native-ядра слишком большой.")
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            expected = {"format": MANIFEST_FORMAT, "engine_id": ENGINE_ID, "version": ENGINE_VERSION,
                        "source_commit": SOURCE_COMMIT, "schema": 1}
            if not isinstance(manifest, dict) or any(type(manifest.get(key)) is not type(value) or manifest[key] != value for key, value in expected.items()):
                raise CoreError("Версия или provenance native-ядра не соответствует приложению.")
            files = manifest.get("files")
            if not isinstance(files, dict) or not {"chrome.exe", "chrome.dll"} <= files.keys():
                raise CoreError("Manifest native-ядра не содержит обязательных файлов.")
            seen = set()
            for raw, digest in files.items():
                if not isinstance(raw, str) or not raw or "\\" in raw or ":" in raw or any(part in ("", ".", "..") or part.endswith((".", " ")) or any(char in part for char in '<>"|?*') or any(ord(char) < 32 for char in part) for part in raw.split("/")) or PurePosixPath(raw).is_absolute() or raw.casefold() in seen or raw.casefold() == MANIFEST_NAME:
                    raise CoreError("Небезопасный или повторяющийся путь native-ядра.")
                seen.add(raw.casefold())
                path = directory.joinpath(*PurePosixPath(raw).parts)
                if not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest) or not path.is_file() or sha256_file(path) != digest:
                    raise CoreError(f"Проверка целостности native-ядра не пройдена: {raw}")
            actual = {path.relative_to(directory).as_posix().casefold() for path in directory.rglob("*") if path.is_file() and path.name != MANIFEST_NAME}
            if actual != seen:
                raise CoreError("Состав native-ядра не совпадает с manifest.")
            executable = directory / "chrome.exe"
            self._prepare_sandbox_access(directory)
            self._probe(executable)
            if signature != self._signature_now():
                raise CoreError("Файлы ядра изменились во время проверки.")
            self._signature, self._executable = signature, executable
            return executable
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CoreError(f"Не удалось проверить native-ядро: {exc}") from exc

    @staticmethod
    def _probe(executable: Path) -> None:
        # The dedicated output folder never touches personal browser profiles.
        with tempfile.TemporaryDirectory(prefix="neantik-core-info-") as temporary:
            directory = Path(temporary)
            output = directory / "info.json"
            try:
                result = subprocess.run([str(executable), f"--user-data-dir={directory / 'profile'}",
                                         f"--neantik-core-info={output}",
                                         f"--log-file={directory / 'chrome.log'}",
                                         "--no-first-run", "--no-default-browser-check"],
                                        cwd=directory, capture_output=True, timeout=15,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if result.returncode != 0 or not output.is_file() or output.stat().st_size > 64 * 1024:
                    raise CoreError("Ядро не подтвердило native-контракт NeAntik.")
                info = json.loads(output.read_text(encoding="utf-8"))
            except subprocess.TimeoutExpired as exc:
                raise CoreError("Ядро не ответило на проверку native-контракта.") from exc
            if not isinstance(info, dict) or info.get("engine_id") != ENGINE_ID or info.get("version") != ENGINE_VERSION or info.get("source_commit") != SOURCE_COMMIT or type(info.get("schema")) is not int or info["schema"] != 1:
                raise CoreError("Runtime-версия native-ядра не соответствует manifest.")
            capabilities = info.get("capabilities")
            if not isinstance(capabilities, dict) or any(capabilities.get(key) is not True for key in REQUIRED_CAPABILITIES):
                raise CoreError("Эта сборка ядра ещё не реализует обязательные native-функции, включая WebRTC-политику для сайтов с proxy.")
