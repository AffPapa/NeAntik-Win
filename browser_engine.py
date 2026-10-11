"""Small native fingerprint engine adapter; no downloads, injection or stock fallback.

Upstream contract checked 2026-10-11:
https://github.com/adryfish/fingerprint-chromium/blob/main/README.md
This pins an experimental Chromium 150 build, not current security coverage.
The provisioning manifest records integrity, not a publisher signature.
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import tempfile
from typing import Any, Mapping
import zipfile

ENGINE_ID = "adryfish-fingerprint-chromium-150"
ENGINE_VERSION = "150.0.7871.186"
ENGINE_RELATIVE_DIRECTORY = Path("Engine") / "fingerprint-chromium150"
ENGINE_ARCHIVE_URL = "https://github.com/adryfish/fingerprint-chromium/releases/download/150.0.7871.186/ungoogled-chromium_150.0.7871.186-1.1_windows_x64.zip"
ENGINE_ARCHIVE_SHA256 = "4d549c326e51ebbabf562fd365eb5380d9d4a81200da2c60f075c688d9a77e03"
ENGINE_ARCHIVE_SIZE = 193743241
ENGINE_MANIFEST_NAME = "engine-manifest.json"
ENGINE_MANIFEST_FORMAT = "neantik-native-engine-v1"
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
IDENTITY_SCHEMA = 1
LOCALES = {"en-US": "en-US,en", "en-GB": "en-GB,en", "ru-RU": "ru-RU,ru", "de-DE": "de-DE,de", "pt-BR": "pt-BR,pt", "tr-TR": "tr-TR,tr", "fr-FR": "fr-FR,fr", "es-ES": "es-ES,es"}
TIMEZONES = frozenset(("UTC", "Europe/London", "Europe/Berlin", "Europe/Paris", "Europe/Madrid", "Europe/Moscow", "Europe/Istanbul", "Europe/Warsaw", "Europe/Kyiv", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Sao_Paulo", "America/Mexico_City", "America/Bogota", "Asia/Bangkok", "Asia/Dubai", "Asia/Singapore", "Asia/Tokyo", "Asia/Kolkata", "Asia/Hong_Kong", "Australia/Sydney", "Africa/Johannesburg"))
CPU_COUNTS = frozenset((2, 4, 8, 12, 16, 24, 32))
SPOOFING_SURFACES = frozenset(("font", "audio", "canvas", "clientrects", "gpu"))


class EngineError(ValueError):
    """Invalid identity, engine provenance or engine files."""


@dataclass(frozen=True)
class VerifiedEngine:
    executable: Path
    engine_id: str = ENGINE_ID
    version: str = ENGINE_VERSION
    experimental: bool = True


class EngineResolver:
    """Per-manager verified engine cache; invalidate when any file stats change.

    This detects ordinary modifications, not adversarial same-stat replacement.
    The first verification hashes every file; build provisioning proves ZIP bytes.
    """
    def __init__(self, portable_root: Path):
        self.portable_root = Path(portable_root)
        self._signature: tuple[Any, ...] | None = None
        self._verified: VerifiedEngine | None = None

    def _tree_signature(self) -> tuple[Any, ...]:
        directory = self.portable_root.resolve() / ENGINE_RELATIVE_DIRECTORY
        if not directory.is_dir():
            raise EngineError("Native-ядро не найдено. Распакуйте полный portable-архив NeAntik Win.")
        records = []
        for path in sorted(directory.rglob("*")):
            info = path.lstat()
            records.append((path.relative_to(directory).as_posix(), info.st_size, info.st_mtime_ns,
                            info.st_ctime_ns, info.st_mode, getattr(info, "st_file_attributes", 0)))
        return (str(directory), directory.lstat().st_mtime_ns, *records)

    def resolve(self) -> VerifiedEngine:
        try:
            signature = self._tree_signature()
            if self._verified is not None and signature == self._signature:
                return self._verified
            verified = verify_engine(self.portable_root)
            after = self._tree_signature()
            if after != signature:
                raise EngineError("Файлы native-ядра изменились во время проверки.")
            self._signature, self._verified = after, verified
            return verified
        except OSError as exc:
            raise EngineError("Не удалось проверить файлы native-ядра.") from exc


def new_identity(mode: str = "native", *, locale: str = "en-US", timezone: str = "UTC") -> dict[str, Any]:
    """Create once per profile; persist the returned value, never generate on launch."""
    if mode == "ordinary":
        return validate_identity({"schema": IDENTITY_SCHEMA, "mode": mode})
    return validate_identity({"schema": IDENTITY_SCHEMA, "mode": mode, "engine_id": ENGINE_ID,
                              "seed": 1 + secrets.randbelow(0xFFFFFFFF), "locale": locale, "timezone": timezone,
                              "hardware_concurrency": 8, "disable_spoofing": []})


def validate_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return canonical JSON-safe data; forbid unknown/unsupported overrides."""
    if not isinstance(value, Mapping) or type(value.get("schema")) is not int or value["schema"] != IDENTITY_SCHEMA:
        raise EngineError("Неподдерживаемая схема fingerprint-профиля.")
    mode = value.get("mode")
    if mode == "ordinary":
        if set(value) != {"schema", "mode"}:
            raise EngineError("Обычный профиль не должен содержать fingerprint-настройки.")
        return {"schema": IDENTITY_SCHEMA, "mode": "ordinary"}
    if mode != "native":
        raise EngineError("Неподдерживаемый режим fingerprint.")
    fields = {"schema", "mode", "engine_id", "seed", "locale", "timezone", "hardware_concurrency", "disable_spoofing"}
    if set(value) != fields or value.get("engine_id") != ENGINE_ID:
        raise EngineError("Настройки fingerprint несовместимы с выбранным ядром.")
    seed = value.get("seed")
    if type(seed) is not int or not 1 <= seed <= 0xFFFFFFFF:
        raise EngineError("Seed fingerprint должен быть ненулевым целым uint32.")
    locale, timezone = value.get("locale"), value.get("timezone")
    if not isinstance(locale, str) or locale not in LOCALES:
        raise EngineError("Выберите поддерживаемый язык fingerprint-профиля.")
    if not isinstance(timezone, str) or timezone not in TIMEZONES:
        raise EngineError("Выберите поддерживаемый часовой пояс fingerprint-профиля.")
    cpu = value.get("hardware_concurrency")
    if type(cpu) is not int or cpu not in CPU_COUNTS:
        raise EngineError("Неподдерживаемое число процессорных потоков.")
    disabled = value.get("disable_spoofing")
    if not isinstance(disabled, list) or any(not isinstance(item, str) or item not in SPOOFING_SURFACES for item in disabled) or len(disabled) != len(set(disabled)):
        raise EngineError("Некорректный список отключённых fingerprint-поверхностей.")
    return {"schema": IDENTITY_SCHEMA, "mode": "native", "engine_id": ENGINE_ID, "seed": seed,
            "locale": locale, "timezone": timezone, "hardware_concurrency": cpu,
            "disable_spoofing": sorted(disabled)}


def serialize_identity(value: Mapping[str, Any]) -> str:
    return json.dumps(validate_identity(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def fingerprint_arguments(value: Mapping[str, Any]) -> list[str]:
    identity = validate_identity(value)
    if identity["mode"] == "ordinary":
        return []
    argv = [f"--fingerprint={identity['seed']}", "--fingerprint-platform=windows",
            "--fingerprint-brand=Chrome", f"--fingerprint-brand-version={ENGINE_VERSION}",
            f"--fingerprint-hardware-concurrency={identity['hardware_concurrency']}",
            f"--lang={identity['locale']}", f"--accept-lang={LOCALES[identity['locale']]}",
            f"--timezone={identity['timezone']}", "--disable-non-proxied-udp"]
    if identity["disable_spoofing"]:
        argv.append("--disable-spoofing=" + ",".join(identity["disable_spoofing"]))
    return argv


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_relative(raw: Any) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
        raise EngineError("Некорректный путь в manifest ядра.")
    path = PurePosixPath(raw)
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
    if path.is_absolute() or any(part in ("", ".", "..") or part.endswith((" ", ".")) or any(c in part for c in ':<>"|?*') or any(ord(c) < 32 for c in part) or part.split(".")[0].casefold() in reserved for part in raw.split("/")):
        raise EngineError("Небезопасный путь в manifest ядра.")
    return path


def _engine_file(directory: Path, relative: PurePosixPath) -> Path:
    candidate = directory.joinpath(*relative.parts)
    cursor = candidate
    while cursor != directory:
        if cursor.is_symlink() or cursor.is_junction():
            raise EngineError("Ядро не должно содержать ссылки или junction.")
        cursor = cursor.parent
    if not candidate.is_file():
        raise EngineError(f"Отсутствует файл ядра: {relative}")
    return candidate


def windows_file_version(executable: Path) -> str:
    """Read VS_FIXEDFILEINFO via version.dll, without running the binary."""
    if os.name != "nt":
        raise EngineError("Native-ядро этой сборки поддерживается только на Windows.")
    from ctypes import wintypes
    version = ctypes.WinDLL("version", use_last_error=True)
    version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    version.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    version.GetFileVersionInfoW.restype = wintypes.BOOL
    version.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
    version.VerQueryValueW.restype = wintypes.BOOL
    class FixedInfo(ctypes.Structure):
        _fields_ = [(name, wintypes.DWORD) for name in ("signature", "structure", "file_ms", "file_ls", "product_ms", "product_ls", "mask", "flags", "os", "type", "subtype", "date_ms", "date_ls")]
    ignored = wintypes.DWORD()
    size = version.GetFileVersionInfoSizeW(str(executable), ctypes.byref(ignored))
    if not size:
        raise EngineError("Не удалось прочитать Windows FileVersion native-ядра.")
    buffer = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(str(executable), 0, size, buffer):
        raise EngineError("Не удалось прочитать ресурс версии native-ядра.")
    pointer, length = ctypes.c_void_p(), wintypes.UINT()
    if not version.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)) or length.value < ctypes.sizeof(FixedInfo):
        raise EngineError("В native-ядре отсутствует VS_FIXEDFILEINFO.")
    info = ctypes.cast(pointer, ctypes.POINTER(FixedInfo)).contents
    if info.signature != 0xFEEF04BD:
        raise EngineError("Повреждён ресурс версии native-ядра.")
    return f"{info.file_ms >> 16}.{info.file_ms & 0xFFFF}.{info.file_ls >> 16}.{info.file_ls & 0xFFFF}"


def verify_engine(portable_root: Path) -> VerifiedEngine:
    """Verify the complete pinned bundle. Caller may cache until file stats change."""
    directory = Path(portable_root).resolve() / ENGINE_RELATIVE_DIRECTORY
    if not directory.is_dir() or directory.is_symlink() or directory.is_junction() or directory.parent.is_symlink() or directory.parent.is_junction():
        raise EngineError("Native-ядро не найдено. Распакуйте полный portable-архив NeAntik Win.")
    manifest_path = directory / ENGINE_MANIFEST_NAME
    try:
        if manifest_path.stat().st_size > MAX_MANIFEST_BYTES or manifest_path.is_symlink() or manifest_path.is_junction():
            raise EngineError("Manifest ядра имеет недопустимый размер или тип.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EngineError("Не удалось прочитать manifest native-ядра.") from exc
    expected = {"format": ENGINE_MANIFEST_FORMAT, "engine_id": ENGINE_ID, "version": ENGINE_VERSION,
                "archive_url": ENGINE_ARCHIVE_URL, "archive_sha256": ENGINE_ARCHIVE_SHA256,
                "archive_size": ENGINE_ARCHIVE_SIZE, "executable": "chrome.exe", "experimental": True}
    if not isinstance(manifest, dict) or any(type(manifest.get(key)) is not type(required) or manifest[key] != required for key, required in expected.items()):
        raise EngineError("Версия или происхождение native-ядра не соответствует закреплённой сборке.")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files or "chrome.exe" not in files or "chrome.dll" not in files:
        raise EngineError("Manifest native-ядра не содержит необходимых файлов.")
    seen: set[str] = set()
    for raw, digest in files.items():
        relative = _safe_relative(raw)
        if raw.casefold() in seen or raw.casefold() == ENGINE_MANIFEST_NAME.casefold() or not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest):
            raise EngineError("Некорректная запись файла в manifest ядра.")
        seen.add(raw.casefold())
        if _sha256(_engine_file(directory, relative)) != digest:
            raise EngineError(f"Проверка целостности ядра не пройдена: {raw}")
    actual = {item.relative_to(directory).as_posix().casefold() for item in directory.rglob("*") if item.is_file() and item.name != ENGINE_MANIFEST_NAME}
    if actual != seen:
        raise EngineError("Состав native-ядра не соответствует manifest.")
    if windows_file_version(directory / "chrome.exe") != ENGINE_VERSION or windows_file_version(directory / "chrome.dll") != ENGINE_VERSION:
        raise EngineError("Windows FileVersion native-ядра не соответствует manifest.")
    return VerifiedEngine(directory / "chrome.exe")


def build_native_launch_arguments(portable_root: Path, identity: Mapping[str, Any], profile_directory: Path) -> list[str]:
    """Normal sandboxed argv. Proxy and selected URLs remain the launcher's concern."""
    identity = validate_identity(identity)
    if identity["mode"] != "native":
        raise EngineError("Для native-запуска нужен native fingerprint-профиль.")
    engine = verify_engine(portable_root)
    return [str(engine.executable), f"--user-data-dir={profile_directory}", "--no-first-run", "--no-default-browser-check", *fingerprint_arguments(identity)]


def manifest_from_verified_archive(engine_directory: Path, archive_path: Path) -> dict[str, Any]:
    """Provisioning helper: prove extracted bytes match the pinned ZIP, without writing.

    Supports a ZIP with either a single enclosing directory or root-level files.
    The caller writes this returned JSON atomically as engine-manifest.json.
    """
    archive_path, directory = Path(archive_path), Path(engine_directory).resolve()
    if archive_path.stat().st_size != ENGINE_ARCHIVE_SIZE or _sha256(archive_path) != ENGINE_ARCHIVE_SHA256:
        raise EngineError("ZIP native-ядра не соответствует закреплённому SHA-256/размеру.")
    files: dict[str, str] = {}
    with zipfile.ZipFile(archive_path) as archive:
        members = [item for item in archive.infolist() if not item.is_dir()]
        exe_members = [item for item in members if PurePosixPath(item.filename).name == "chrome.exe"]
        if len(exe_members) != 1:
            raise EngineError("ZIP ядра должен содержать ровно один chrome.exe.")
        prefix = PurePosixPath(exe_members[0].filename).parent
        seen: set[str] = set()
        for member in members:
            source_path = _safe_relative(member.filename)
            try:
                relative = source_path.relative_to(prefix)
            except ValueError as exc:
                raise EngineError("ZIP ядра содержит файлы вне каталога chrome.exe.") from exc
            raw = relative.as_posix()
            _safe_relative(raw)
            if raw.casefold() in seen or raw.casefold() == ENGINE_MANIFEST_NAME.casefold():
                raise EngineError("ZIP ядра содержит повторяющийся или зарезервированный файл.")
            seen.add(raw.casefold())
            digest = hashlib.sha256()
            with archive.open(member) as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
            if _sha256(_engine_file(directory, relative)) != digest.hexdigest():
                raise EngineError(f"Распакованный файл отличается от ZIP: {raw}")
            files[raw] = digest.hexdigest()
    return {"format": ENGINE_MANIFEST_FORMAT, "engine_id": ENGINE_ID, "version": ENGINE_VERSION,
            "archive_url": ENGINE_ARCHIVE_URL, "archive_sha256": ENGINE_ARCHIVE_SHA256,
            "archive_size": ENGINE_ARCHIVE_SIZE, "executable": "chrome.exe", "experimental": True,
            "files": files}


def install_verified_archive(portable_root: Path, archive_path: Path) -> Path:
    """Offline build provisioning. Never replace an existing engine directory."""
    archive_path = Path(archive_path)
    if archive_path.stat().st_size != ENGINE_ARCHIVE_SIZE or _sha256(archive_path) != ENGINE_ARCHIVE_SHA256:
        raise EngineError("ZIP native-ядра не соответствует закреплённому SHA-256/размеру.")
    parent = Path(portable_root).resolve() / "Engine"
    if parent.is_symlink() or parent.is_junction():
        raise EngineError("Каталог Engine не должен быть ссылкой или junction.")
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / ENGINE_RELATIVE_DIRECTORY.name
    if target.exists() or target.is_symlink():
        raise EngineError("Каталог ядра уже существует. Используйте отдельную новую папку сборки.")
    staging = Path(tempfile.mkdtemp(prefix=".native-install-", dir=parent))
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if len(members) > 10000 or sum(item.file_size for item in members) > 2 * 1024**3:
                raise EngineError("ZIP ядра превышает допустимые пределы.")
            exe_members = [item for item in members if not item.is_dir() and PurePosixPath(item.filename).name == "chrome.exe"]
            if len(exe_members) != 1:
                raise EngineError("ZIP ядра должен содержать ровно один chrome.exe.")
            prefix = _safe_relative(exe_members[0].filename).parent
            planned: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
            files, directories, explicit_directories = set(), set(), set()
            for member in members:
                if member.orig_filename != member.filename or member.flag_bits & 1:
                    raise EngineError("ZIP ядра содержит повреждённый или зашифрованный файл.")
                source = _safe_relative(member.filename.rstrip("/") if member.is_dir() else member.filename)
                mode = member.external_attr >> 16
                if mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise EngineError("ZIP ядра содержит ссылку или специальный файл.")
                if source == prefix and member.is_dir():
                    continue
                try:
                    relative = source.relative_to(prefix)
                except ValueError as exc:
                    raise EngineError("ZIP ядра содержит файл вне каталога chrome.exe.") from exc
                raw = relative.as_posix()
                _safe_relative(raw)
                key = raw.casefold()
                parents = {PurePosixPath(*relative.parts[:index]).as_posix().casefold() for index in range(1, len(relative.parts))}
                if key in files or parents & files or (not member.is_dir() and key in directories) or key == ENGINE_MANIFEST_NAME.casefold():
                    raise EngineError("ZIP ядра содержит конфликтующие пути Windows.")
                if member.is_dir():
                    if key in explicit_directories:
                        raise EngineError("ZIP ядра содержит повторяющийся каталог.")
                    directories.add(key)
                    explicit_directories.add(key)
                else:
                    files.add(key)
                    directories.update(parents)
                    planned.append((member, relative))
            for member, relative in planned:
                destination = staging.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output)
        manifest = manifest_from_verified_archive(staging, archive_path)
        if windows_file_version(staging / "chrome.exe") != ENGINE_VERSION or windows_file_version(staging / "chrome.dll") != ENGINE_VERSION:
            raise EngineError("Windows FileVersion не совпадает с закреплённой версией ядра.")
        (staging / ENGINE_MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Windows rename refuses an existing destination; never copy over an engine.
        if target.exists():
            raise EngineError("Каталог ядра был создан другим процессом.")
        staging.rename(target)
        return target
    finally:
        if staging.exists():
            _cleanup_install_staging(staging, parent)


def _cleanup_install_staging(staging: Path, validated_parent: Path) -> None:
    """Delete only our direct staging child after validating the resolved target."""
    if validated_parent.is_symlink() or validated_parent.is_junction() or staging.is_symlink() or staging.is_junction():
        raise EngineError("Очистка staging отменена: каталог был заменён ссылкой.")
    parent_resolved, staging_resolved = validated_parent.resolve(strict=True), staging.resolve(strict=True)
    if staging_resolved.parent != parent_resolved or staging.parent != validated_parent or not staging.name.startswith(".native-install-") or validated_parent.name != "Engine":
        raise EngineError("Очистка staging отменена: небезопасный конечный путь.")
    shutil.rmtree(staging_resolved)
