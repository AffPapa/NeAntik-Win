"""NeAntik Win — local-first portable Windows browser profile manager.

This release uses bundled stock Chromium for new local profiles and can continue
to launch profiles pinned to an installed Chrome or Edge browser. It does not
modify browser or device fingerprint values. Legacy experimental profile
metadata is retained for safe identification and migration, not enabled as a
launch-time persona.
"""

from __future__ import annotations

import base64
import contextlib
import ctypes
import hashlib
import ipaddress
import json
import os
import queue
import re
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from profile_identity import (CoreError, NATIVE_PREVIEW, identity_arguments,
                              ordinary_identity, serialize_identity, validate_identity)
from privacy_defaults import ensure_managed_download_directory, initialize_privacy_defaults
from proxy_diagnostics import diagnose_proxy

import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

try:
    import win32crypt
except ImportError:  # pragma: no cover - packaged build always supplies this
    win32crypt = None

try:
    import winreg
except ImportError:  # pragma: no cover - non-Windows source checks
    winreg = None


APP_NAME = "NeAntik Win"
APP_VERSION = json.loads((Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "release-version.json").read_text(encoding="utf-8"))["version"]
SITE_URL = "https://nevision-win.mail782861.chatgpt.site"
PRIVACY_CHECK_URL = SITE_URL + "/check.html"
PRIVACY_DIAGNOSTICS_CONSENT = (
    "Откроется внешний сайт проверки в выбранном профиле. Сайт увидит IP-адрес "
    "этого запроса; если настроенный proxy работает, это может быть его адрес "
    "выхода. Маршрут отдельно не проверен.\n\n"
    "Страница не проверяет DNS, WebRTC, UDP или весь сетевой трафик и не "
    "подтверждает анонимность.\n\nПродолжить?"
)
PORTABILITY_WARNING = (
    "На другом ПК или под другой учётной записью Windows сохранённые в Chromium "
    "пароли, cookies и сессии могут не работать из-за защиты Windows DPAPI и "
    "Chromium App-Bound Encryption. Возможно, потребуется войти на сайты заново. "
    "Proxy-пароли в backup не включаются — введите их повторно."
)
DB_NAME = "nevision.db"
PROFILE_DIR_NAME = "Profiles"
BACKUP_DIR_NAME = "Backups"
LOG_DIR_NAME = "Logs"
VAULT_ENTROPY = b"NeVision-Win-v0.1-local-vault"
# A deliberately generous ceiling for a local browser profile backup.  These checks
# protect the restore action from accidentally importing an archive that expands far
# beyond the available disk space.  A larger profile can be restored after creating
# a new backup with a future format/version that explicitly supports it.
MAX_BACKUP_FILES = 20_000
MAX_BACKUP_ARCHIVE_ENTRIES = MAX_BACKUP_FILES + 1  # Profile files plus one manifest.
MAX_BACKUP_CENTRAL_DIRECTORY_BYTES = 32 * 1024 * 1024
MAX_BACKUP_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024
MAX_BACKUP_MANIFEST_BYTES = 1 * 1024 * 1024
PROFILE_TEMPLATE_FORMAT = "neantik-profile-template-v1"
MAX_PROFILE_TEMPLATE_BYTES = 64 * 1024
CHROMIUM_LOCK_MARKERS = ("SingletonLock", "SingletonCookie", "SingletonSocket")
WINDOWS_CHROMIUM_LOCKFILE = "lockfile"
JOURNAL_FORMAT = "nevision-operation-v1"
NATIVE_JOURNAL_FORMAT = "neantik-operation-v3"
NATIVE_BACKUP_FORMAT = "neantik-profile-backup-v3"
SCHEMA_VERSION = "1"
DB_BUSY_TIMEOUT_MS = 8_000
NATIVE_PREVIEW_PATCH_SHA256 = "0c592ca18304823faf8f0e2534619c5f7b458072e451ede81eb528a2b8c76d22"

THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEME_SETTING_KEY = "theme_preference"
THEME_OPTIONS = {
    "Системная — как в Windows": THEME_SYSTEM,
    "Светлая": THEME_LIGHT,
    "Тёмная": THEME_DARK,
}
THEME_LABELS = {value: label for label, value in THEME_OPTIONS.items()}

# Keep every surface semantic.  The app never relies on a filter/inversion for
# light mode: both palettes were tuned independently so text, focus outlines
# and status colors retain their intended contrast.
DARK_COLORS = {
    "bg": "#0B1020",
    "header": "#0D1423",
    "sidebar": "#111827",
    "panel": "#111827",
    "panel_2": "#182238",
    "panel_hover": "#24314B",
    "input": "#0D1525",
    "text": "#F4F7FF",
    "muted": "#A5B2C9",
    "muted_dim": "#77869F",
    "line": "#2B3A58",
    "accent": "#8B6DFF",
    "accent_hover": "#A68CFF",
    "violet_soft": "#C4B6FF",
    "lime": "#C7F83A",
    "lime_soft": "#F0FFC8",
    "lime_surface": "#24351D",
    "amber": "#FFB763",
    "cyan": "#74C7FF",
    "danger": "#FF8C9A",
    "danger_surface": "#3B202C",
    "danger_hover": "#502432",
    "ink": "#11182A",
    "card": "#182238",
    "selection": "#2D2756",
    "menu_bg": "#20283A",
    "menu_active": "#3A345E",
    "menu_text": "#EFF1F7",
    "menu_active_text": "#FFFFFF",
    "illustration_inner": "#28234E",
    "badge_1": "#2D2557",
    "badge_2": "#16344E",
    "badge_3": "#3A2945",
    "badge_4": "#273C32",
    "badge_5": "#3D2C22",
}

LIGHT_COLORS = {
    "bg": "#F1F4FA",
    "header": "#FBFCFF",
    "sidebar": "#F0F3F9",
    "panel": "#F9FAFE",
    "panel_2": "#E8ECF5",
    "panel_hover": "#DCE3F0",
    "input": "#FFFFFF",
    "text": "#151A29",
    "muted": "#556176",
    "muted_dim": "#748097",
    "line": "#D4DCE9",
    "accent": "#6F56D9",
    "accent_hover": "#5C42C7",
    "violet_soft": "#765FE0",
    "lime": "#577A16",
    "lime_soft": "#D9F4A7",
    "lime_surface": "#EDF7D9",
    "amber": "#AD5B11",
    "cyan": "#1672B1",
    "danger": "#C53954",
    "danger_surface": "#FCE9EE",
    "danger_hover": "#F8D8E0",
    "ink": "#FFFFFF",
    "card": "#FFFFFF",
    "selection": "#E5DFFF",
    "menu_bg": "#FBFCFF",
    "menu_active": "#E8E2FF",
    "menu_text": "#182033",
    "menu_active_text": "#211646",
    "illustration_inner": "#E8E1FF",
    "badge_1": "#D8CEFF",
    "badge_2": "#CBE9FB",
    "badge_3": "#F4D4E6",
    "badge_4": "#D7EDD0",
    "badge_5": "#F8DEC4",
}


class NeVisionError(RuntimeError):
    """User-safe error raised by the application core."""


def normalize_theme_preference(value: str) -> str:
    """Return a supported appearance preference, preserving a safe default."""

    return value if value in (THEME_SYSTEM, THEME_LIGHT, THEME_DARK) else THEME_SYSTEM


def windows_apps_use_light_theme() -> bool | None:
    """Read Windows' per-app appearance setting without changing system state."""

    if os.name != "nt" or winreg is None:
        return None
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            try:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            except FileNotFoundError:
                value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
        return bool(int(value))
    except (FileNotFoundError, OSError, TypeError, ValueError):
        return None


def resolve_theme(preference: str, apps_use_light: bool | None = None) -> str:
    """Resolve System / Light / Dark into one concrete palette name."""

    normalized = normalize_theme_preference(preference)
    if normalized != THEME_SYSTEM:
        return normalized
    current = windows_apps_use_light_theme() if apps_use_light is None else apps_use_light
    # Preserve the original graphite look if Windows cannot expose a preference.
    return THEME_LIGHT if current is True else THEME_DARK


def palette_for_theme(theme: str) -> dict[str, str]:
    """Return an isolated copy so widget code cannot mutate shared tokens."""

    return dict(LIGHT_COLORS if theme == THEME_LIGHT else DARK_COLORS)


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def display_datetime(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return value


def safe_label(value: str, fallback: str = "profile") -> str:
    clean = "".join(char if char.isalnum() or char in "-_." else "-" for char in value.strip())
    clean = clean.strip("-._")[:48]
    return clean or fallback


def filesystem_path(path: Path) -> Path:
    """Use extended Windows paths for internal IO, without changing public paths.

    A longPathAware manifest alone still needs a machine-wide Windows policy.
    The explicit prefix works without that policy or administrator privileges.
    It is not a safety validator: archive members must be validated first, and
    this representation must not be passed to Chromium or shown as its data dir.
    """

    if os.name != "nt":
        return path
    absolute = os.path.abspath(path)
    if absolute.startswith("\\\\?\\"):
        return Path(absolute)
    if absolute.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + absolute[2:])
    return Path("\\\\?\\" + absolute)


def canonical_path_key(path: Path) -> str:
    """Give ordinary and extended aliases the same lock identity."""

    resolved = str(filesystem_path(path).resolve())
    if os.name == "nt":
        if resolved[:8].lower() == "\\\\?\\unc\\":
            resolved = "\\\\" + resolved[8:]
        elif resolved.startswith("\\\\?\\"):
            resolved = resolved[4:]
    return os.path.normcase(os.path.normpath(resolved))


def app_resource(relative_path: str) -> Path:
    """Return a bundled asset path in development and in a PyInstaller bundle."""

    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative_path


def normalize_proxy_host(value: str) -> str:
    """Accept a single DNS/IP host, never Chromium proxy-list syntax or a URL."""
    host = value.strip()
    if "%" in host or any(ord(c) < 32 for c in host):
        raise NeVisionError("Введите сервер proxy без IPv6 scope и управляющих символов.")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    try:
        ascii_host = host.encode("idna").decode("ascii").rstrip(".")
    except UnicodeError as exc:
        raise NeVisionError("Некорректное имя сервера proxy.") from exc
    labels = ascii_host.split(".")
    if len(ascii_host) > 253 or any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") or not all(c.isascii() and (c.isalnum() or c == "-") for c in label) for label in labels):
        raise NeVisionError("Введите только IP или имя сервера proxy — без URL, логина, порта и разделителей.")
    return ascii_host.lower()


def proxy_host_requires_local_name_resolution(value: str) -> bool:
    """Distinguish a proxy hostname from an IP literal for route disclosure."""
    host = normalize_proxy_host(value)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return True
    return False


def proxy_endpoint(proxy: dict[str, Any]) -> str:
    host = normalize_proxy_host(str(proxy["host"]))
    if ":" in host:
        host = f"[{host}]"
    return f"{proxy['scheme']}://{host}:{int(proxy['port'])}"


def bundled_proxy_privacy_arguments(proxy: dict[str, Any]) -> list[str]:
    """Constrain Chromium URL bypass and background DNS for one fixed proxy.

    The proxy endpoint itself must remain reachable, including when it is an
    IP literal (Chromium's resolver rules also apply to literal endpoints).
    This does not control other applications or prove that every
    Chromium transport is proxied; it is deliberately scoped to the bundled
    browser and tested with disposable loopback fixtures.
    """
    host = normalize_proxy_host(str(proxy["host"]))
    resolver = f"MAP * ~NOTFOUND, EXCLUDE {host}"
    return [
        "--proxy-bypass-list=<-loopback>",
        f"--host-resolver-rules={resolver}",
        "--disable-quic",
        "--webrtc-ip-handling-policy=disable_non_proxied_udp",
    ]


def browser_family_for_executable(path: Path) -> str:
    """Accept only the stock Chrome/Edge executable names supported by this build."""

    name = path.name.casefold()
    if name == "chrome.exe":
        return "chrome"
    if name == "msedge.exe":
        return "edge"
    raise NeVisionError("Выберите chrome.exe или msedge.exe. Другие браузеры не поддерживаются.")


def proxy_choices(proxies: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Keep display labels distinct while preserving stable proxy IDs by index."""

    labels = ["— Без proxy —"]
    ids = [""]
    for proxy in proxies:
        label = f"{proxy['name']} · {proxy['scheme']}://{proxy['host']}:{proxy['port']}"
        if label in labels:
            base_label = label
            suffix = 2
            while label in labels:
                label = f"{base_label} ({suffix})"
                suffix += 1
        labels.append(label)
        ids.append(str(proxy["id"]))
    return labels, ids


def profile_network_note(proxy_id: str | None, linked_profiles: int = 0) -> str:
    """Explain the network-identity limit without claiming proxy leak protection."""
    if not proxy_id:
        return "Без proxy: данные профилей разделены, но сайты могут видеть один и тот же прямой внешний IP."
    if linked_profiles > 1:
        return (f"Этот proxy назначен {linked_profiles} профилям. У них может быть общий внешний IP — "
                "разные профили не становятся отдельными сетевыми личностями.")
    return "Proxy назначен только этому профилю. Его внешний IP и отсутствие DNS/WebRTC-утечек не подтверждены."


def validated_browser_family(value: Any) -> str:
    if type(value) is not str or value not in {"", "chrome", "edge", "chromium"}:
        raise NeVisionError("Backup или профиль содержит неподдерживаемую привязку браузера.")
    return value


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @classmethod
    def for_runtime(cls) -> "AppPaths":
        # In a PyInstaller one-folder bundle, sys.executable is the portable folder's exe.
        root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        return cls(root)

    @property
    def data(self) -> Path:
        return self.root / "Data"

    @property
    def profiles(self) -> Path:
        return self.data / PROFILE_DIR_NAME

    @property
    def backups(self) -> Path:
        return self.data / BACKUP_DIR_NAME

    @property
    def logs(self) -> Path:
        return self.data / LOG_DIR_NAME

    @property
    def operations(self) -> Path:
        return self.data / "Operations"

    @property
    def database(self) -> Path:
        return self.data / DB_NAME

    def prepare(self) -> None:
        for folder in (self.root, self.data, self.profiles, self.backups, self.logs, self.operations):
            folder.mkdir(parents=True, exist_ok=True)


class SecretVault:
    """Windows-DPAPI-backed storage for small secrets such as proxy passwords.

    DPAPI intentionally binds the encrypted value to the current Windows user. The
    application can remain portable while a copied vault requires the user to re-enter
    secrets on a different Windows account or computer.
    """

    @staticmethod
    def encrypt(value: str) -> str:
        if not value:
            return ""
        if win32crypt is None:
            raise NeVisionError("Windows DPAPI недоступен. Установите Windows-сборку NeAntik Win.")
        try:
            # PyWin32 returns the protected byte blob directly; the description is
            # returned only by CryptUnprotectData.
            protected = win32crypt.CryptProtectData(value.encode("utf-8"), APP_NAME, VAULT_ENTROPY, None, None, 0)
            return base64.b64encode(protected).decode("ascii")
        except Exception as exc:  # pragma: no cover - OS-specific failure
            raise NeVisionError(f"Не удалось зашифровать секрет Windows DPAPI: {exc}") from exc

    @staticmethod
    def decrypt(value: str) -> str:
        if not value:
            return ""
        if win32crypt is None:
            raise NeVisionError("Windows DPAPI недоступен.")
        try:
            protected = base64.b64decode(value.encode("ascii"))
            clear = win32crypt.CryptUnprotectData(protected, VAULT_ENTROPY, None, None, 0)[1]
            return clear.decode("utf-8")
        except Exception as exc:
            raise NeVisionError(
                "Не удалось расшифровать секрет. Возможно, база перенесена на другой Windows-профиль или компьютер."
            ) from exc


class Storage:
    """Local SQLite repository. All records stay in the portable Data directory."""

    def __init__(self, paths: AppPaths):
        self.paths = paths
        try:
            self.paths.prepare()
            self._initialize()
            with self.profile_operation_lock("__data_recovery__"):
                self._recover_interrupted_operations()
        except NeVisionError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise NeVisionError(f"Не удалось подготовить локальное хранилище: {exc}") from exc

    @contextlib.contextmanager
    def connection(self) -> Iterable[sqlite3.Connection]:
        db: sqlite3.Connection | None = None
        try:
            db = sqlite3.connect(self.paths.database, timeout=DB_BUSY_TIMEOUT_MS / 1_000)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            db.execute(f"PRAGMA busy_timeout = {DB_BUSY_TIMEOUT_MS}")
            yield db
            db.commit()
        except NeVisionError:
            if db is not None:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
            raise
        except sqlite3.Error as exc:
            if db is not None:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                raise NeVisionError("Локальная база данных занята. Закройте второй экземпляр NeAntik Win и повторите действие.") from exc
            raise NeVisionError(f"Ошибка локальной базы данных: {exc}") from exc
        except OSError as exc:
            if db is not None:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
            raise NeVisionError(f"Не удалось обратиться к локальному хранилищу: {exc}") from exc
        except Exception:
            if db is not None:
                with contextlib.suppress(sqlite3.Error):
                    db.rollback()
            raise
        finally:
            if db is not None:
                with contextlib.suppress(sqlite3.Error):
                    db.close()

    def _initialize(self) -> None:
        with self.connection() as db:
            db.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS proxies (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    scheme TEXT NOT NULL CHECK(scheme IN ('http', 'https', 'socks5')),
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL CHECK(port BETWEEN 1 AND 65535),
                    username TEXT NOT NULL DEFAULT '',
                    password_protected TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    group_name TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    browser_family TEXT NOT NULL DEFAULT '',
                    proxy_id TEXT REFERENCES proxies(id) ON DELETE SET NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_launch_at TEXT,
                    last_exit_at TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    action TEXT NOT NULL,
                    profile_id TEXT REFERENCES profiles(id) ON DELETE SET NULL,
                    details TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_profiles_name ON profiles(name COLLATE NOCASE);
                CREATE TABLE IF NOT EXISTS profile_fingerprints (
                    profile_id TEXT PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
                    config_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at DESC);
                """
            )
            schema = db.execute("SELECT value FROM settings WHERE key = 'schema_version'").fetchone()
            if schema and str(schema["value"]) != SCHEMA_VERSION:
                raise NeVisionError(
                    f"Неподдерживаемая версия локальной базы данных: {schema['value']}. "
                    "Сохраните копию Data и обновите NeAntik Win."
                )
            columns = {row["name"] for row in db.execute("PRAGMA table_info(profiles)")}
            if "browser_family" not in columns:
                db.execute("ALTER TABLE profiles ADD COLUMN browser_family TEXT NOT NULL DEFAULT ''")
            if not schema:
                self.set_setting("schema_version", SCHEMA_VERSION, db)
            self.set_setting("app_version", APP_VERSION, db)

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def set_setting(self, key: str, value: str, db: sqlite3.Connection | None = None) -> None:
        if db is not None:
            db.execute(
                """INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (key, value, timestamp()),
            )
            return
        with self.connection() as active:
            self.set_setting(key, value, active)

    def get_setting(self, key: str, default: str = "") -> str:
        with self.connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def log(self, action: str, profile_id: str | None = None, details: str = "") -> None:
        with self.connection() as db:
            db.execute(
                "INSERT INTO events(created_at, action, profile_id, details) VALUES (?, ?, ?, ?)",
                (timestamp(), action, profile_id, details),
            )

    def list_profiles(self, query: str = "") -> list[dict[str, Any]]:
        needle = f"%{query.strip()}%"
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT p.*, pr.name AS proxy_name, pr.scheme AS proxy_scheme, pr.host AS proxy_host, pr.port AS proxy_port,
                       fp.config_json AS fingerprint_json
                FROM profiles p
                LEFT JOIN proxies pr ON pr.id = p.proxy_id
                LEFT JOIN profile_fingerprints fp ON fp.profile_id = p.id
                WHERE p.name LIKE ? OR p.group_name LIKE ? OR p.tags LIKE ?
                ORDER BY lower(p.group_name), lower(p.name)
                """,
                (needle, needle, needle),
            ).fetchall()
        profiles = []
        for row in rows:
            profile = dict(row)
            encoded = profile.pop("fingerprint_json")
            try:
                profile["fingerprint"] = validate_identity(json.loads(encoded)) if encoded is not None else ordinary_identity()
            except CoreError as exc:
                # Identity validators emit fixed explanations, never profile
                # secrets. Keep incompatibility actionable without rewriting it.
                raise NeVisionError(f"Fingerprint-настройки несовместимы: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise NeVisionError("Fingerprint-настройки профиля повреждены. Восстановите проверенный backup.") from exc
            profiles.append(profile)
        return profiles

    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                """
                SELECT p.*, pr.name AS proxy_name, pr.scheme AS proxy_scheme, pr.host AS proxy_host, pr.port AS proxy_port,
                       pr.username AS proxy_username, pr.password_protected AS proxy_password_protected
                FROM profiles p LEFT JOIN proxies pr ON pr.id = p.proxy_id WHERE p.id = ?
                """,
                (profile_id,),
            ).fetchone()
            fingerprint = db.execute("SELECT config_json FROM profile_fingerprints WHERE profile_id=?", (profile_id,)).fetchone()
        result = self._row_to_dict(row)
        if result is not None:
            try:
                result["fingerprint"] = validate_identity(json.loads(fingerprint["config_json"])) if fingerprint else ordinary_identity()
            except CoreError as exc:
                raise NeVisionError(f"Fingerprint-настройки несовместимы: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise NeVisionError("Fingerprint-настройки профиля повреждены. Восстановите проверенный backup.") from exc
        return result

    def count_profiles_for_proxy(self, proxy_id: str) -> int:
        """Count exact proxy assignments, not names that users may duplicate."""
        with self.connection() as db:
            row = db.execute("SELECT count(*) FROM profiles WHERE proxy_id = ?", (proxy_id,)).fetchone()
        return int(row[0])

    def _save_fingerprint_in_db(self, db: sqlite3.Connection, profile_id: str, fingerprint: dict[str, Any]) -> None:
        db.execute("INSERT INTO profile_fingerprints(profile_id, config_json) VALUES (?, ?) ON CONFLICT(profile_id) DO UPDATE SET config_json=excluded.config_json", (profile_id, serialize_identity(fingerprint)))

    def save_profile(self, data: dict[str, Any], profile_id: str | None = None) -> str:
        if profile_id and "fingerprint" in data:
            with self.profile_operation_lock(profile_id):
                return self._save_profile(data, profile_id)
        return self._save_profile(data, profile_id)

    def _save_profile(self, data: dict[str, Any], profile_id: str | None = None) -> str:
        name = str(data.get("name", "")).strip()
        if not name:
            raise NeVisionError("У профиля должно быть имя.")
        fingerprint = None
        if "fingerprint" in data:
            try:
                fingerprint = validate_identity(data["fingerprint"])
            except CoreError as exc:
                raise NeVisionError(str(exc)) from exc
        if profile_id and fingerprint is not None:
            original = self.get_profile(profile_id)
            if original and original["fingerprint"] != fingerprint:
                self.ensure_profile_closed(profile_id)
                if original["fingerprint"]["mode"] != fingerprint["mode"] and any(filesystem_path(self.profile_path(profile_id)).iterdir()):
                    raise NeVisionError("Для смены ядра создайте чистую копию профиля. Существующие браузерные данные остаются в исходном профиле.")
        proxy_id = str(data.get("proxy_id") or "").strip() or None
        payload = (
            name,
            str(data.get("group_name", "")).strip(),
            str(data.get("tags", "")).strip(),
            str(data.get("notes", "")).strip(),
            proxy_id,
        )
        now = timestamp()
        with self.connection() as db:
            if proxy_id and not db.execute("SELECT id FROM proxies WHERE id = ?", (proxy_id,)).fetchone():
                raise NeVisionError("Выбранный proxy больше не существует. Обновите форму профиля и повторите действие.")
            if profile_id:
                exists = db.execute("SELECT id FROM profiles WHERE id = ?", (profile_id,)).fetchone()
                if not exists:
                    raise NeVisionError("Профиль не найден.")
                db.execute(
                    """UPDATE profiles SET name=?, group_name=?, tags=?, notes=?, proxy_id=?, updated_at=? WHERE id=?""",
                    (*payload, now, profile_id),
                )
                if fingerprint is not None:
                    self._save_fingerprint_in_db(db, profile_id, fingerprint)
                self.log_in_db(db, "profile.updated", profile_id, name)
                return profile_id
        # Create the profile directory before committing its database record.  A
        # full disk or an ACL error must not leave an unlaunchable ghost profile.
        new_id = uuid.uuid4().hex
        folder = filesystem_path(self.profile_path(new_id))
        try:
            folder.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise NeVisionError(f"Не удалось создать каталог профиля: {exc}") from exc
        try:
            with self.connection() as db:
                if proxy_id and not db.execute("SELECT id FROM proxies WHERE id = ?", (proxy_id,)).fetchone():
                    raise NeVisionError("Выбранный proxy больше не существует. Обновите форму профиля и повторите действие.")
                db.execute(
                    """INSERT INTO profiles(id, name, group_name, tags, notes, proxy_id, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (new_id, *payload, now, now),
                )
                self._save_fingerprint_in_db(db, new_id, fingerprint or ordinary_identity())
                self.log_in_db(db, "profile.created", new_id, name)
        except Exception:
            with contextlib.suppress(OSError):
                folder.rmdir()
            raise
        return new_id

    def delete_profile(self, profile_id: str) -> dict[str, Any]:
        with self.profile_operation_lock("__data_recovery__"), self.profile_operation_lock(profile_id):
            return self._delete_profile_locked(profile_id)

    def _delete_profile_locked(self, profile_id: str) -> dict[str, Any]:
        profile = self.get_profile(profile_id)
        if not profile:
            raise NeVisionError("Профиль не найден.")
        self.ensure_profile_closed(profile_id)
        folder = filesystem_path(self.profile_path(profile_id))
        moved_folder: Path | None = None
        journal: Path | None = None
        if folder.exists():
            deleted_root = filesystem_path(self.data_deleted_root())
            target = deleted_root / f"{safe_label(profile['name'])}-{profile_id[:8]}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}-{uuid.uuid4().hex[:8]}"
            try:
                deleted_root.mkdir(parents=True, exist_ok=True)
                journal = self._create_operation_journal(
                    {"operation": "delete", "profile_id": profile_id, "deleted_dir": target.name}
                )
                os.replace(folder, target)
                moved_folder = target
            except OSError as exc:
                if journal is not None:
                    self._discard_operation_journal(journal)
                raise NeVisionError(f"Не удалось переместить данные профиля в Data\\Deleted: {exc}") from exc
        try:
            with self.connection() as db:
                db.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
                self.log_in_db(db, "profile.deleted", None, profile["name"])
        except Exception as exc:
            if moved_folder is not None:
                try:
                    os.replace(moved_folder, folder)
                except OSError as rollback_error:
                    raise NeVisionError(
                        f"Не удалось обновить запись профиля. Данные сохранены в {moved_folder}; "
                        f"вернуть их автоматически не удалось: {rollback_error}"
                    ) from exc
            if journal is not None:
                self._discard_operation_journal(journal)
            raise
        if journal is not None:
            self._discard_operation_journal(journal)
        return profile

    def list_proxies(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM proxies ORDER BY lower(name)").fetchall()
        return [dict(row) for row in rows]

    def get_proxy(self, proxy_id: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM proxies WHERE id = ?", (proxy_id,)).fetchone()
        return self._row_to_dict(row)

    def save_proxy(self, data: dict[str, Any], proxy_id: str | None = None) -> str:
        name = str(data.get("name", "")).strip()
        host = str(data.get("host", "")).strip()
        scheme = str(data.get("scheme", "http")).lower()
        try:
            port = int(data.get("port", 0))
        except (TypeError, ValueError):
            port = 0
        if not name or not host or scheme not in {"http", "https", "socks5"} or not 1 <= port <= 65535:
            raise NeVisionError("Заполните имя, сервер, тип и корректный порт proxy.")
        host = normalize_proxy_host(host)
        existing = self.get_proxy(proxy_id) if proxy_id else None
        password = data.get("password")
        if password is None:
            encrypted = existing["password_protected"] if existing else ""
        else:
            encrypted = SecretVault.encrypt(str(password))
        now = timestamp()
        values = (name, scheme, host, port, str(data.get("username", "")).strip(), encrypted)
        with self.connection() as db:
            if proxy_id:
                if not existing:
                    raise NeVisionError("Proxy не найден.")
                db.execute(
                    """UPDATE proxies SET name=?, scheme=?, host=?, port=?, username=?, password_protected=?, updated_at=? WHERE id=?""",
                    (*values, now, proxy_id),
                )
                self.log_in_db(db, "proxy.updated", None, name)
                return proxy_id
            new_id = uuid.uuid4().hex
            db.execute(
                """INSERT INTO proxies(id, name, scheme, host, port, username, password_protected, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (new_id, *values, now, now),
            )
            self.log_in_db(db, "proxy.created", None, name)
        return new_id

    def delete_proxy(self, proxy_id: str) -> None:
        proxy = self.get_proxy(proxy_id)
        if not proxy:
            raise NeVisionError("Proxy не найден.")
        with self.connection() as db:
            linked = db.execute("SELECT count(*) FROM profiles WHERE proxy_id = ?", (proxy_id,)).fetchone()[0]
            db.execute("DELETE FROM proxies WHERE id = ?", (proxy_id,))
            self.log_in_db(db, "proxy.deleted", None, f"{proxy['name']}; отвязано профилей: {linked}")

    def list_events(self, profile_id: str | None = None, limit: int = 150) -> list[dict[str, Any]]:
        with self.connection() as db:
            if profile_id:
                rows = db.execute(
                    """SELECT e.*, p.name AS profile_name FROM events e LEFT JOIN profiles p ON p.id=e.profile_id
                       WHERE e.profile_id=? ORDER BY e.id DESC LIMIT ?""",
                    (profile_id, limit),
                ).fetchall()
            else:
                rows = db.execute(
                    """SELECT e.*, p.name AS profile_name FROM events e LEFT JOIN profiles p ON p.id=e.profile_id
                       ORDER BY e.id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        return [dict(row) for row in rows]

    def log_in_db(self, db: sqlite3.Connection, action: str, profile_id: str | None = None, details: str = "") -> None:
        db.execute(
            "INSERT INTO events(created_at, action, profile_id, details) VALUES (?, ?, ?, ?)",
            (timestamp(), action, profile_id, details),
        )

    def touch_profile_launch(self, profile_id: str) -> None:
        now = timestamp()
        with self.connection() as db:
            db.execute("UPDATE profiles SET last_launch_at=?, updated_at=? WHERE id=?", (now, now, profile_id))
            self.log_in_db(db, "profile.launched", profile_id)

    def pin_browser_family(self, profile_id: str, family: str) -> None:
        if family not in {"chrome", "edge", "chromium"}:
            raise NeVisionError("Неподдерживаемый браузер для профиля.")
        with self.connection() as db:
            updated = db.execute(
                "UPDATE profiles SET browser_family=? WHERE id=? AND browser_family=''",
                (family, profile_id),
            )
            if not updated.rowcount:
                row = db.execute("SELECT browser_family FROM profiles WHERE id=?", (profile_id,)).fetchone()
                if row is None:
                    raise NeVisionError("Профиль больше не существует.")
                if row["browser_family"] != family:
                    raise NeVisionError("Профиль закреплён за другим браузером. Верните прежнее ядро или создайте чистую копию профиля.")

    def touch_profile_exit(self, profile_id: str, exit_code: int | None) -> None:
        now = timestamp()
        with self.connection() as db:
            updated = db.execute("UPDATE profiles SET last_exit_at=?, updated_at=? WHERE id=?", (now, now, profile_id))
            if updated.rowcount:
                self.log_in_db(db, "profile.process_exited", profile_id, f"code={exit_code}")
            else:
                self.log_in_db(db, "profile.process_exited", None, f"profile={profile_id}; code={exit_code}; профиль уже удалён")

    def profile_path(self, profile_id: str) -> Path:
        if type(profile_id) is not str or re.fullmatch(r"[0-9a-f]{32}", profile_id) is None:
            raise NeVisionError("Некорректный идентификатор профиля.")
        return self.paths.profiles / profile_id

    def data_deleted_root(self) -> Path:
        return self.paths.data / "Deleted"

    def active_profile_lock_markers(self, profile_id: str) -> list[str]:
        """Return Unix Chromium markers, including dangling links.

        Windows Chromium uses an exclusively opened ``lockfile`` instead.  The
        fallback keeps source checks useful off Windows without weakening the
        Windows release's native handle check.
        """

        folder = self.profile_path(profile_id)
        return [marker for marker in CHROMIUM_LOCK_MARKERS if os.path.lexists(folder / marker)]

    def _profile_mutex_name(self, profile_id: str) -> str:
        # This fixed sentinel serializes Data-wide recovery and is not a profile
        # ID. Preserve its existing mutex path while validating all real IDs.
        mutex_path = self.paths.profiles / profile_id if profile_id == "__data_recovery__" else self.profile_path(profile_id)
        canonical = canonical_path_key(mutex_path)
        digest = hashlib.sha256(canonical.encode("utf-8", "surrogatepass")).hexdigest()
        return f"Local\\NeVisionWin.Profile.{digest}"

    @contextlib.contextmanager
    def profile_operation_lock(self, profile_id: str) -> Iterable[None]:
        """Serialize changing operations for a profile across NeVision processes.

        A named Windows mutex is released by the OS if a process crashes, unlike a
        lock file that could become stale.  It covers NeVision's own concurrent
        backup, delete, and launch operations; Chromium's separate lockfile is
        checked by :meth:`ensure_profile_closed`.
        """

        if os.name != "nt":
            yield
            return
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            create_mutex = kernel32.CreateMutexW
            create_mutex.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
            create_mutex.restype = ctypes.c_void_p
            wait_for_single_object = kernel32.WaitForSingleObject
            wait_for_single_object.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
            wait_for_single_object.restype = ctypes.c_uint32
            release_mutex = kernel32.ReleaseMutex
            release_mutex.argtypes = (ctypes.c_void_p,)
            release_mutex.restype = ctypes.c_bool
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = (ctypes.c_void_p,)
            close_handle.restype = ctypes.c_bool
            handle = create_mutex(None, False, self._profile_mutex_name(profile_id))
        except (AttributeError, ctypes.ArgumentError, OSError) as exc:
            raise NeVisionError("Не удалось создать защитную блокировку операции профиля.") from exc
        if not handle:
            raise NeVisionError(f"Не удалось создать защитную блокировку операции профиля (Win32: {ctypes.get_last_error()}).")

        acquired = False
        try:
            wait_result = wait_for_single_object(handle, 0)
            if wait_result == 0x00000102:  # WAIT_TIMEOUT
                raise NeVisionError("Профиль занят другой операцией NeAntik Win или NeVision Win. Дождитесь её завершения и повторите действие.")
            if wait_result not in (0x00000000, 0x00000080):  # WAIT_OBJECT_0, WAIT_ABANDONED
                raise NeVisionError(f"Не удалось получить блокировку профиля (Win32: {ctypes.get_last_error()}).")
            acquired = True
            yield
        finally:
            if acquired:
                with contextlib.suppress(OSError):
                    release_mutex(handle)
            with contextlib.suppress(OSError):
                close_handle(handle)

    def _windows_chromium_lock_is_active(self, profile_id: str) -> bool:
        """Probe Chromium's Windows lockfile without modifying it.

        Chromium holds ``<user-data-dir>\\lockfile`` with write access while its
        profile is open.  A write probe with only read sharing fails with
        ``ERROR_SHARING_VIOLATION`` for an active browser, while a stale lockfile
        opens and is immediately closed.
        """

        lock_path = filesystem_path(self.profile_path(profile_id) / WINDOWS_CHROMIUM_LOCKFILE)
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            create_file = kernel32.CreateFileW
            create_file.argtypes = (
                ctypes.c_wchar_p,
                ctypes.c_uint32,
                ctypes.c_uint32,
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_uint32,
                ctypes.c_void_p,
            )
            create_file.restype = ctypes.c_void_p
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = (ctypes.c_void_p,)
            close_handle.restype = ctypes.c_bool
            handle = create_file(
                str(lock_path),
                0x40000000,  # GENERIC_WRITE
                0x00000001,  # FILE_SHARE_READ
                None,
                3,  # OPEN_EXISTING
                0x00000080,  # FILE_ATTRIBUTE_NORMAL
                None,
            )
        except (AttributeError, ctypes.ArgumentError, OSError) as exc:
            raise NeVisionError("Не удалось безопасно проверить блокировку Chromium.") from exc

        if handle == ctypes.c_void_p(-1).value:  # INVALID_HANDLE_VALUE
            error = ctypes.get_last_error()
            if error in (2, 3):  # ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND
                return False
            if error == 32:  # ERROR_SHARING_VIOLATION
                return True
            raise NeVisionError(f"Не удалось безопасно проверить блокировку Chromium (Win32: {error}).")
        try:
            return False
        finally:
            with contextlib.suppress(OSError):
                close_handle(handle)

    def ensure_profile_closed(self, profile_id: str) -> None:
        if os.name == "nt":
            if self._windows_chromium_lock_is_active(profile_id):
                raise NeVisionError(
                    "Профиль занят запущенным Chromium. Закройте все окна этого профиля и дождитесь завершения браузера, затем повторите действие."
                )
            return
        markers = self.active_profile_lock_markers(profile_id)
        if markers:
            raise NeVisionError("Профиль занят запущенным Chromium. Закройте все окна этого профиля и повторите действие.")

    def wait_for_chromium_lock(self, profile_id: str, process: subprocess.Popen[Any], timeout_seconds: float = 1.5) -> None:
        """Keep NeVision's launch mutex until Chromium has claimed its profile.

        Chromium normally creates the lockfile in a few milliseconds.  A short
        bounded wait closes the tiny race between Popen returning and lockfile
        ownership becoming visible to another NeVision instance.
        """

        if os.name != "nt":
            return
        deadline = time.monotonic() + timeout_seconds
        while process.poll() is None and time.monotonic() < deadline:
            try:
                if self._windows_chromium_lock_is_active(profile_id):
                    return
            except NeVisionError:
                # The browser was already launched. Do not turn a successful launch
                # into a false UI failure because a third-party filesystem filter
                # briefly prevents probing its lockfile.
                return
            time.sleep(0.04)

    @staticmethod
    def _journal_profile_id(value: Any) -> str:
        profile_id = str(value)
        if len(profile_id) != 32 or any(char not in "0123456789abcdef" for char in profile_id.lower()):
            raise NeVisionError("Журнал операции содержит неверный идентификатор профиля.")
        return profile_id

    @staticmethod
    def _journal_child(root: Path, name: Any) -> Path:
        if not isinstance(name, str) or not name or name in {".", ".."}:
            raise NeVisionError("Журнал операции содержит небезопасный путь.")
        candidate = root / name
        if candidate.parent != root:
            raise NeVisionError("Журнал операции содержит небезопасный путь.")
        return candidate

    def _create_operation_journal(self, payload: dict[str, Any]) -> Path:
        """Persist recovery intent before changing profile files or SQLite state."""

        journal = self.paths.operations / f"{uuid.uuid4().hex}.json"
        partial = self.paths.operations / f".{journal.name}.{uuid.uuid4().hex}.partial"
        native_restore = payload.get("operation") == "restore" and isinstance(payload.get("profile"), dict) and payload["profile"].get("fingerprint", {}).get("mode") == NATIVE_PREVIEW
        record = {**payload, "format": NATIVE_JOURNAL_FORMAT if native_restore else JOURNAL_FORMAT, "created_at": timestamp()}
        try:
            with open(filesystem_path(partial), "x", encoding="utf-8") as output:
                json.dump(record, output, ensure_ascii=False, sort_keys=True)
                output.flush()
                os.fsync(output.fileno())
            os.replace(filesystem_path(partial), filesystem_path(journal))
        except (OSError, TypeError, ValueError) as exc:
            with contextlib.suppress(FileNotFoundError):
                filesystem_path(partial).unlink()
            raise NeVisionError(f"Не удалось сохранить журнал операции: {exc}") from exc
        return journal

    @staticmethod
    def _discard_operation_journal(journal: Path) -> None:
        # A completed operation remains recoverable when this cleanup fails: the
        # startup reconciler will validate it and remove the journal later.
        with contextlib.suppress(FileNotFoundError, OSError):
            filesystem_path(journal).unlink()

    def _read_operation_journal(self, journal: Path) -> dict[str, Any]:
        journal = filesystem_path(journal)
        if journal.is_symlink():
            raise NeVisionError(f"Журнал операции не должен быть ссылкой: {journal.name}")
        try:
            payload = json.loads(journal.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NeVisionError(f"Не удалось прочитать журнал незавершённой операции: {journal.name}") from exc
        if not isinstance(payload, dict) or payload.get("format") not in (JOURNAL_FORMAT, "neantik-operation-v2", NATIVE_JOURNAL_FORMAT):
            raise NeVisionError(f"Журнал незавершённой операции имеет неверный формат: {journal.name}")
        return payload

    def _journal_restore_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile = payload.get("profile")
        if not isinstance(profile, dict):
            raise NeVisionError("Журнал восстановления не содержит профиль.")
        profile_id = self._journal_profile_id(profile.get("id"))
        fields = ("name", "group_name", "tags", "notes", "created_at", "updated_at")
        if any(not isinstance(profile.get(field), str) for field in fields):
            raise NeVisionError("Журнал восстановления содержит неверные данные профиля.")
        name = str(profile["name"]).strip()
        if not name:
            raise NeVisionError("Журнал восстановления содержит профиль без имени.")
        try:
            fingerprint = validate_identity(profile.get("fingerprint", ordinary_identity()))
        except CoreError as exc:
            raise NeVisionError("Журнал восстановления содержит неверный fingerprint.") from exc
        if (payload.get("format") == NATIVE_JOURNAL_FORMAT) != (fingerprint["mode"] == NATIVE_PREVIEW) or payload.get("format") == "neantik-operation-v2":
            raise NeVisionError("Формат журнала не соответствует fingerprint-профилю.")
        return {"id": profile_id, **{field: str(profile[field]) for field in fields},
                "browser_family": validated_browser_family(profile.get("browser_family", "")), "fingerprint": fingerprint}

    def _insert_recovered_profile(self, profile: dict[str, Any], details: str) -> None:
        with self.connection() as db:
            existing = db.execute("SELECT id FROM profiles WHERE id = ?", (profile["id"],)).fetchone()
            if existing:
                return
            db.execute(
                """INSERT INTO profiles(id, name, group_name, tags, notes, browser_family, proxy_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    profile["id"],
                    profile["name"],
                    profile["group_name"],
                    profile["tags"],
                    profile["notes"],
                    profile["browser_family"],
                    None,
                    profile["created_at"],
                    profile["updated_at"],
                ),
            )
            self._save_fingerprint_in_db(db, profile["id"], profile.get("fingerprint", ordinary_identity()))
            self.log_in_db(db, "profile.restore_recovered", profile["id"], details)

    def _recover_delete_operation(self, payload: dict[str, Any]) -> None:
        profile_id = self._journal_profile_id(payload.get("profile_id"))
        target = filesystem_path(self._journal_child(self.data_deleted_root(), payload.get("deleted_dir")))
        source = filesystem_path(self.profile_path(profile_id))
        profile_exists = self.get_profile(profile_id) is not None
        source_exists = source.exists()
        target_exists = target.exists()

        if profile_exists:
            if source_exists and not target_exists:
                return
            if not source_exists and target_exists:
                try:
                    os.replace(target, source)
                except OSError as exc:
                    raise NeVisionError("Не удалось вернуть профиль после прерванного удаления.") from exc
                self.log("profile.delete_recovered", profile_id, target.name)
                return
            raise NeVisionError("Невозможно безопасно восстановить прерванное удаление профиля.")

        if not source_exists and target_exists:
            return
        raise NeVisionError("Невозможно безопасно подтвердить завершение удаления профиля.")

    def _recover_restore_operation(self, payload: dict[str, Any]) -> None:
        profile = self._journal_restore_profile(payload)
        target = filesystem_path(self.profile_path(profile["id"]))
        staging = filesystem_path(self._journal_child(self.paths.profiles, payload.get("staging_dir")))
        db_profile_exists = self.get_profile(profile["id"]) is not None
        target_is_directory = target.is_dir()
        staging_is_directory = staging.is_dir()

        if db_profile_exists and target_is_directory:
            return
        if not db_profile_exists and target_is_directory:
            self._insert_recovered_profile(profile, "journal recovery")
            return
        if not db_profile_exists and staging_is_directory:
            try:
                shutil.rmtree(staging)
            except OSError as exc:
                raise NeVisionError("Не удалось убрать временный каталог прерванного восстановления.") from exc
            return
        raise NeVisionError("Невозможно безопасно восстановить прерванное восстановление профиля.")

    def _recover_interrupted_operations(self) -> None:
        for journal in sorted(filesystem_path(self.paths.operations).glob("*.json")):
            payload = self._read_operation_journal(journal)
            operation = payload.get("operation")
            if operation == "delete":
                self._recover_delete_operation(payload)
            elif operation == "restore":
                self._recover_restore_operation(payload)
            else:
                raise NeVisionError(f"Журнал содержит неизвестную операцию: {journal.name}")
            self._discard_operation_journal(journal)

    def _backup_files(self, source: Path) -> list[tuple[Path, Path]]:
        """Collect restorable profile files and enforce restore-compatible limits."""

        source = filesystem_path(source)
        if not source.is_dir():
            raise NeVisionError("Каталог данных профиля отсутствует. Восстановите профиль из backup или создайте новый.")
        if source.is_symlink() or (hasattr(source, "is_junction") and source.is_junction()):
            raise NeVisionError("Backup не поддерживает ссылки/junction в каталоге профиля. Данные не изменены.")
        excluded_dirs = {"Cache", "Code Cache", "GPUCache", "Crashpad", "GrShaderCache", "ShaderCache"}
        excluded_files = {*CHROMIUM_LOCK_MARKERS, WINDOWS_CHROMIUM_LOCKFILE}
        files_to_archive: list[tuple[Path, Path]] = []
        total_size = 0

        def on_walk_error(error: OSError) -> None:
            raise NeVisionError(f"Не удалось прочитать данные профиля для backup: {error}") from error

        for root, dirs, files in os.walk(source, onerror=on_walk_error):
            current = Path(root)
            dirs[:] = [item for item in dirs if item not in excluded_dirs]
            for item in dirs:
                child = current / item
                if child.is_symlink() or (hasattr(child, "is_junction") and child.is_junction()):
                    raise NeVisionError("Backup не поддерживает ссылки/junction в каталоге профиля. Данные не изменены.")
            for file_name in files:
                if file_name in excluded_files:
                    continue
                file_path = current / file_name
                try:
                    file_link_stat = file_path.lstat()
                    if (file_path.is_symlink() or
                            (hasattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT") and
                             getattr(file_link_stat, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)):
                        raise NeVisionError(
                            "Backup не поддерживает ссылки/reparse-файлы в данных профиля: "
                            f"{file_path.name}. Замените ссылку отдельной копией файла."
                        )
                    file_stat = file_path.stat()
                except OSError as exc:
                    raise NeVisionError(f"Не удалось прочитать файл профиля для backup: {file_path.name}: {exc}") from exc
                if not stat.S_ISREG(file_stat.st_mode):
                    continue
                if file_stat.st_nlink > 1:
                    raise NeVisionError(
                        "Backup не поддерживает hardlink в данных профиля: "
                        f"{file_path.name}. Удалите ссылку или сохраните отдельную копию файла."
                    )
                if len(files_to_archive) >= MAX_BACKUP_FILES:
                    raise NeVisionError(f"Профиль содержит слишком много файлов для backup (лимит: {MAX_BACKUP_FILES}).")
                total_size += file_stat.st_size
                if total_size > MAX_BACKUP_UNCOMPRESSED_BYTES:
                    raise NeVisionError("Профиль слишком большой для текущего формата backup (лимит: 8 GB).")
                files_to_archive.append((file_path, file_path.relative_to(source)))
        return files_to_archive

    def export_profile_template(self, profile_id: str) -> Path:
        """Export only a new-profile template, never Chromium data or vault entries."""
        profile = self.get_profile(profile_id)
        if not profile:
            raise NeVisionError("Профиль не найден.")
        mode = profile["fingerprint"]["mode"]
        if mode != "ordinary":
            raise NeVisionError("Шаблон старого экспериментального профиля нельзя экспортировать. Создайте чистый обычный профиль.")
        template = {
            "format": PROFILE_TEMPLATE_FORMAT,
            "profile": {
                "name": profile["name"],
                "group_name": profile["group_name"],
                "tags": profile["tags"],
                "mode": mode,
            },
        }
        encoded = (json.dumps(template, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        if len(encoded) > MAX_PROFILE_TEMPLATE_BYTES:
            raise NeVisionError("Настройки профиля слишком велики для переноса (лимит: 64 KB).")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = self.paths.backups / f"{safe_label(profile['name'])}-{stamp}-{uuid.uuid4().hex[:8]}.neantik-profile.json"
        created = False
        try:
            # Exclusive creation is important: an export must never replace an
            # earlier user-owned template, even if a generated name collides.
            with open(filesystem_path(target), "xb") as destination:
                created = True
                destination.write(encoded)
                destination.flush()
                os.fsync(destination.fileno())
        except FileExistsError as exc:
            raise NeVisionError("Файл настроек с таким именем уже существует. Повторите экспорт.") from exc
        except OSError as exc:
            if created:
                with contextlib.suppress(FileNotFoundError):
                    filesystem_path(target).unlink()
            raise NeVisionError(f"Не удалось экспортировать настройки профиля: {exc}") from exc
        self.log("profile.template_exported", profile_id, target.name)
        return target

    @staticmethod
    def _read_profile_template(source_path: Path) -> dict[str, str]:
        try:
            with open(filesystem_path(source_path), "rb") as source:
                encoded = source.read(MAX_PROFILE_TEMPLATE_BYTES + 1)
        except OSError as exc:
            raise NeVisionError(f"Не удалось прочитать настройки профиля: {exc}") from exc
        if len(encoded) > MAX_PROFILE_TEMPLATE_BYTES:
            raise NeVisionError("Файл настроек профиля слишком велик (лимит: 64 KB).")

        def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise NeVisionError("Файл настроек профиля содержит повторяющиеся поля.")
                result[key] = value
            return result

        try:
            template = json.loads(encoded.decode("utf-8"), object_pairs_hook=unique_keys)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NeVisionError("Файл настроек профиля повреждён или имеет неверную кодировку.") from exc
        if not isinstance(template, dict) or set(template) != {"format", "profile"} or template["format"] != PROFILE_TEMPLATE_FORMAT:
            raise NeVisionError("Неподдерживаемый формат настроек профиля.")
        profile = template["profile"]
        if not isinstance(profile, dict) or set(profile) != {"name", "group_name", "tags", "mode"}:
            raise NeVisionError("Файл настроек профиля содержит неизвестные или отсутствующие поля.")
        if any(not isinstance(profile[key], str) for key in profile):
            raise NeVisionError("Поля настроек профиля должны быть текстом.")
        if not profile["name"].strip():
            raise NeVisionError("В файле настроек отсутствует имя профиля.")
        if profile["mode"] != "ordinary":
            raise NeVisionError("Этот шаблон использует отключённый экспериментальный режим. Создайте новый обычный профиль.")
        return profile

    def import_profile_template(self, source_path: Path) -> str:
        """Create an empty independent profile, without proxy or browser sessions."""
        template = self._read_profile_template(source_path)
        identity = ordinary_identity()
        profile_id = self.save_profile({
            "name": template["name"],
            "group_name": template["group_name"],
            "tags": template["tags"],
            "notes": "",
            "proxy_id": None,
            "fingerprint": identity,
        })
        self.log("profile.template_imported", profile_id)
        return profile_id

    def backup_profile(self, profile_id: str) -> Path:
        with self.profile_operation_lock(profile_id):
            return self._backup_profile_locked(profile_id)

    def _backup_profile_locked(self, profile_id: str) -> Path:
        profile = self.get_profile(profile_id)
        if not profile:
            raise NeVisionError("Профиль не найден.")
        self.ensure_profile_closed(profile_id)
        source = self.profile_path(profile_id)
        files_to_archive = self._backup_files(source)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        archive = self.paths.backups / f"{safe_label(profile['name'])}-{profile_id[:8]}-{stamp}-{uuid.uuid4().hex[:8]}.zip"
        partial = self.paths.backups / f".{archive.name}.{uuid.uuid4().hex}.partial"
        manifest = {
            "format": "nevision-profile-backup-v1",
            "created_at": timestamp(),
            "profile": {key: profile.get(key) for key in ("id", "name", "group_name", "tags", "notes", "browser_family")},
            "proxy_credentials_included": False,
            "browser_session_data_included": True,
            "encrypted": False,
        }
        if profile["fingerprint"]["mode"] != "ordinary":
            manifest["format"] = NATIVE_BACKUP_FORMAT
            manifest["profile"]["fingerprint"] = profile["fingerprint"]
        try:
            with zipfile.ZipFile(filesystem_path(partial), "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zip_out:
                zip_out.writestr("nevision-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                for file_path, relative in files_to_archive:
                    zip_out.write(file_path, Path("profile") / relative)
            self._verify_created_backup(partial, manifest, files_to_archive)
            os.replace(filesystem_path(partial), filesystem_path(archive))
        except (OSError, RuntimeError, zipfile.BadZipFile, EOFError, zlib.error, NeVisionError) as exc:
            with contextlib.suppress(FileNotFoundError):
                filesystem_path(partial).unlink()
            raise NeVisionError(f"Не удалось создать backup: {exc}") from exc
        self.log("profile.backup_created", profile_id, str(archive.name))
        return archive

    @classmethod
    def _verify_created_backup(
        cls,
        archive_path: Path,
        expected_manifest: dict[str, Any],
        files_to_archive: list[tuple[Path, Path]],
    ) -> None:
        """Verify the completed ZIP and its CRCs before publishing the backup."""
        cls._preflight_backup_archive(archive_path)
        try:
            with zipfile.ZipFile(filesystem_path(archive_path), "r") as archive:
                infos = archive.infolist()
                names = [item.filename for item in infos]
                expected = {"nevision-manifest.json", *("profile/" + relative.as_posix() for _, relative in files_to_archive)}
                if len(names) != len(set(names)) or set(names) != expected:
                    raise NeVisionError("Состав backup не совпадает с исходными данными профиля.")
                cls._validated_backup_members(infos)
                manifest_info = archive.getinfo("nevision-manifest.json")
                if manifest_info.file_size > MAX_BACKUP_MANIFEST_BYTES:
                    raise NeVisionError("Manifest backup превышает безопасный размер.")
                try:
                    actual_manifest = json.loads(archive.read(manifest_info).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
                    raise NeVisionError("Manifest созданного backup повреждён.") from exc
                if actual_manifest != expected_manifest:
                    raise NeVisionError("Manifest созданного backup не совпадает с профилем.")
                corrupt_member = archive.testzip()
                if corrupt_member is not None:
                    raise NeVisionError(f"CRC-проверка backup не прошла: {Path(corrupt_member).name}.")
        except (zipfile.BadZipFile, EOFError, OSError, RuntimeError, zlib.error) as exc:
            raise NeVisionError("Не удалось проверить целостность созданного backup.") from exc

    @staticmethod
    def _preflight_backup_archive(archive_path: Path) -> None:
        """Bound ZIP metadata before ZipFile reads the whole central directory."""
        end_record = getattr(zipfile, "_EndRecData", None)
        entries_index = getattr(zipfile, "_ECD_ENTRIES_TOTAL", None)
        directory_size_index = getattr(zipfile, "_ECD_SIZE", None)
        if end_record is None or entries_index is None or directory_size_index is None:
            raise NeVisionError("Версия Python не поддерживает безопасную проверку backup.")
        try:
            with filesystem_path(archive_path).open("rb") as source:
                metadata = end_record(source)
        except Exception as exc:
            raise NeVisionError("Не удалось безопасно прочитать метаданные backup.") from exc
        if metadata is None:
            raise NeVisionError("Файл backup повреждён или не является ZIP-архивом.")
        if metadata[entries_index] > MAX_BACKUP_ARCHIVE_ENTRIES:
            raise NeVisionError(f"Backup содержит слишком много записей (лимит: {MAX_BACKUP_ARCHIVE_ENTRIES}).")
        if metadata[directory_size_index] > MAX_BACKUP_CENTRAL_DIRECTORY_BYTES:
            raise NeVisionError("Backup содержит слишком большой каталог ZIP-записей.")

    @staticmethod
    def _validated_backup_members(archive_members: list[zipfile.ZipInfo]) -> list[zipfile.ZipInfo]:
        """Return only safe profile files from a supported backup archive.

        ZIP file names are always POSIX-style.  We validate them before creating a
        restored profile so a malformed archive cannot write outside its new data
        directory or unexpectedly consume an unbounded amount of disk space.
        """
        if len(archive_members) > MAX_BACKUP_ARCHIVE_ENTRIES:
            raise NeVisionError(f"Backup содержит слишком много записей (лимит: {MAX_BACKUP_ARCHIVE_ENTRIES}).")
        manifest_members = [member for member in archive_members if member.filename == "nevision-manifest.json"]
        if len(manifest_members) != 1 or manifest_members[0].is_dir():
            raise NeVisionError("Backup должен содержать ровно один manifest NeAntik Win / NeVision Win.")
        members = []
        for member in archive_members:
            if member is manifest_members[0]:
                continue
            if not member.filename.startswith("profile/") or member.is_dir():
                raise NeVisionError("Backup содержит неподдерживаемую запись.")
            members.append(member)
        if len(members) > MAX_BACKUP_FILES:
            raise NeVisionError(f"Backup содержит слишком много файлов (лимит: {MAX_BACKUP_FILES}).")

        total_size = 0
        seen: set[str] = set()
        directories: set[str] = set()
        reserved = {"con", "prn", "aux", "nul", "conin$", "conout$", *(f"com{i}" for i in "123456789¹²³"), *(f"lpt{i}" for i in "123456789¹²³")}
        for member in members:
            if member.orig_filename != member.filename or "\\" in member.orig_filename or "\x00" in member.orig_filename:
                raise NeVisionError("Backup содержит небезопасный путь.")
            try:
                relative = PurePosixPath(member.filename).relative_to("profile")
            except ValueError as exc:  # Defensive: the prefix was already checked above.
                raise NeVisionError("Backup содержит небезопасный путь.") from exc
            raw_parts = member.filename[len("profile/"):].split("/")
            if not relative.parts or any(part in {"", ".", ".."} for part in raw_parts):
                raise NeVisionError("Backup содержит небезопасный путь.")
            # Reject Windows drive-qualified and backslash paths rather than relying
            # on platform-specific normalization while extracting them.
            if any(any(c in part for c in '\\:<>"|?*') or any(ord(c) < 32 for c in part) or part.endswith((".", " ")) or part.split(".")[0].casefold() in reserved for part in raw_parts):
                raise NeVisionError("Backup содержит небезопасный путь.")
            key = "/".join(raw_parts).casefold()
            parents = {"/".join(raw_parts[:i]).casefold() for i in range(1, len(raw_parts))}
            if key in seen or key in directories or parents & seen:
                raise NeVisionError("Backup содержит повторяющиеся или конфликтующие пути Windows.")
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode) or (mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG)) or member.flag_bits & 1:
                raise NeVisionError("Backup содержит ссылку, специальный или зашифрованный файл.")
            seen.add(key)
            directories.update(parents)
            total_size += member.file_size
            if total_size > MAX_BACKUP_UNCOMPRESSED_BYTES:
                raise NeVisionError("Backup слишком большой для безопасного восстановления (лимит: 8 GB).")
        return members

    def restore_profile(
        self,
        archive_path: Path,
        name_override: str = "",
    ) -> str:
        with self.profile_operation_lock("__data_recovery__"):
            return self._restore_profile_locked(archive_path, name_override)

    def _restore_profile_locked(
        self,
        archive_path: Path,
        name_override: str = "",
    ) -> str:
        archive_path = filesystem_path(archive_path)
        if not archive_path.exists():
            raise NeVisionError("Файл backup не найден.")
        staging: Path | None = None
        journal: Path | None = None
        try:
            self._preflight_backup_archive(archive_path)
            with zipfile.ZipFile(archive_path, "r") as archive:
                archive_members = archive.infolist()
                if len(archive_members) > MAX_BACKUP_ARCHIVE_ENTRIES:
                    raise NeVisionError(f"Backup содержит слишком много записей (лимит: {MAX_BACKUP_ARCHIVE_ENTRIES}).")
                if sum(item.filename == "nevision-manifest.json" for item in archive_members) != 1:
                    raise NeVisionError("Backup должен содержать ровно один manifest NeAntik Win / NeVision Win.")
                try:
                    manifest_info = archive.getinfo("nevision-manifest.json")
                except KeyError as exc:
                    raise NeVisionError("В backup отсутствует manifest NeAntik Win / NeVision Win.") from exc
                if manifest_info.file_size > MAX_BACKUP_MANIFEST_BYTES:
                    raise NeVisionError("Manifest backup слишком большой.")
                try:
                    manifest = json.loads(archive.read(manifest_info).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise NeVisionError("Manifest backup повреждён.") from exc
                if not isinstance(manifest, dict):
                    raise NeVisionError("Manifest backup имеет неверный формат.")
                if manifest.get("format") not in ("nevision-profile-backup-v1", "neantik-profile-backup-v2", NATIVE_BACKUP_FORMAT):
                    raise NeVisionError("Неподдерживаемый формат backup NeAntik.")
                original = manifest.get("profile", {})
                if not isinstance(original, dict):
                    raise NeVisionError("Manifest backup имеет неверный профиль.")
                try:
                    fingerprint = validate_identity(original.get("fingerprint", ordinary_identity()))
                except CoreError as exc:
                    raise NeVisionError("Manifest backup содержит неверный fingerprint.") from exc
                if ((manifest["format"] == NATIVE_BACKUP_FORMAT) != (fingerprint["mode"] != "ordinary") or
                        manifest["format"] == "neantik-profile-backup-v2"):
                    raise NeVisionError("Формат backup не соответствует fingerprint-профилю.")
                # Restore keeps legacy identity metadata intact for data recovery.
                # The launcher blocks these profiles; restoring must not rewrite or discard them.
                members = self._validated_backup_members(archive_members)
                profile_name = name_override.strip() or str(original.get("name", "Восстановленный профиль"))
                data = {
                    "name": profile_name,
                    "group_name": original.get("group_name", ""),
                    "tags": original.get("tags", ""),
                    "notes": original.get("notes", ""),
                    "browser_family": validated_browser_family(original.get("browser_family", "")),
                    "proxy_id": None,
                    "fingerprint": fingerprint,
                }
                staging = filesystem_path(self.paths.profiles / f".restore-{uuid.uuid4().hex}.partial")
                staging.mkdir(parents=True, exist_ok=False)
                staging_resolved = staging.resolve()
                try:
                    for member in members:
                        relative = PurePosixPath(member.filename).relative_to("profile")
                        candidate = staging.joinpath(*relative.parts).resolve()
                        if staging_resolved not in candidate.parents:
                            raise NeVisionError("Backup содержит небезопасный путь.")
                        candidate.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member, "r") as source, open(candidate, "wb") as destination:
                            shutil.copyfileobj(source, destination)
                except NeVisionError:
                    raise
                except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                    raise NeVisionError(f"Не удалось распаковать backup: {exc}") from exc

            # Persist recovery intent before making the staged data visible. A
            # power loss after the rename is reconciled on the next startup.
            new_id = uuid.uuid4().hex
            target = filesystem_path(self.profile_path(new_id))
            now = timestamp()
            restored_profile = {
                "id": new_id,
                "name": str(data["name"]).strip() or "Восстановленный профиль",
                "group_name": str(data["group_name"] or "").strip(),
                "tags": str(data["tags"] or "").strip(),
                "notes": str(data["notes"] or "").strip(),
                "browser_family": data["browser_family"],
                "created_at": now,
                "updated_at": now,
                "fingerprint": data["fingerprint"],
            }
            journal = self._create_operation_journal(
                {"operation": "restore", "profile": restored_profile, "staging_dir": staging.name}
            )
            try:
                os.replace(staging, target)
            except OSError as exc:
                self._discard_operation_journal(journal)
                raise NeVisionError(f"Не удалось подготовить восстановленный профиль: {exc}") from exc
            try:
                with self.connection() as db:
                    db.execute(
                        """INSERT INTO profiles(id, name, group_name, tags, notes, browser_family, proxy_id, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            restored_profile["id"],
                            restored_profile["name"],
                            restored_profile["group_name"],
                            restored_profile["tags"],
                            restored_profile["notes"],
                            restored_profile["browser_family"],
                            None,
                            restored_profile["created_at"],
                            restored_profile["updated_at"],
                        ),
                    )
                    self._save_fingerprint_in_db(db, new_id, restored_profile["fingerprint"])
                    self.log_in_db(db, "profile.restored", new_id, archive_path.name)
            except Exception as exc:
                try:
                    os.replace(target, staging)
                except OSError as rollback_error:
                    raise NeVisionError(
                        f"Не удалось сохранить запись восстановленного профиля. Данные сохранены в {target}; "
                        f"вернуть их во временный каталог не удалось: {rollback_error}"
                    ) from exc
                self._discard_operation_journal(journal)
                raise
            self._discard_operation_journal(journal)
        except zipfile.BadZipFile as exc:
            raise NeVisionError("Файл backup повреждён или не является ZIP-архивом.") from exc
        except (OSError, RuntimeError) as exc:
            raise NeVisionError(f"Не удалось восстановить backup: {exc}") from exc
        finally:
            if staging is not None and staging.exists():
                with contextlib.suppress(OSError):
                    shutil.rmtree(staging)
        return new_id

    def health_check(self, profile_id: str) -> list[tuple[str, str]]:
        profile = self.get_profile(profile_id)
        if not profile:
            raise NeVisionError("Профиль не найден.")
        path = self.profile_path(profile_id)
        result: list[tuple[str, str]] = []
        result.append(("Каталог данных", "OK" if path.exists() else "Отсутствует"))
        result.append(("Размер профиля", human_size(directory_size(path))))
        result.append(("Последний запуск", display_datetime(profile.get("last_launch_at"))))
        result.append(("Proxy", profile.get("proxy_name") or "Не назначен"))
        result.append(("Сетевой выход", profile_network_note(
            profile.get("proxy_id"),
            self.count_profiles_for_proxy(str(profile["proxy_id"])) if profile.get("proxy_id") else 0,
        )))
        if profile.get("proxy_id") and not self.get_proxy(str(profile["proxy_id"])):
            result.append(("Связь proxy", "Профиль ссылается на удалённый proxy"))
        else:
            result.append(("Связь proxy", "OK"))
        return result


def directory_size(folder: Path) -> int:
    folder = filesystem_path(folder)
    total = 0
    if not folder.exists():
        return total
    for root, _, files in os.walk(folder):
        for file_name in files:
            with contextlib.suppress(OSError):
                total += (Path(root) / file_name).stat().st_size
    return total


def human_size(size: int) -> str:
    units = ("B", "KB", "MB", "GB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


class BrowserLauncher:
    """Launches a bundled Chromium or installed browser with isolated user data."""

    BUNDLED_RELATIVE = Path("Engine") / "Chromium" / "chrome.exe"
    PROFILE_REPARSE_CHECKS = (
        Path("Local State"), Path("Default"),
        Path("Default/Network"), Path("Default/Network/Cookies"),
        Path("Default/Cookies"), Path("Default/Local Storage"),
        Path("Default/Local Storage/leveldb"), Path("Default/IndexedDB"),
        Path("Default/Service Worker"), Path("Default/Service Worker/Database"),
        Path("Default/Service Worker/CacheStorage"), Path("Default/Session Storage"),
        Path("Default/Extensions"), Path("Default/Storage"),
        Path("Default/Preferences"), Path("Default/Secure Preferences"),
        Path("Default/Login Data"), Path("Default/Web Data"),
    )

    KNOWN_BROWSERS = (
        ("Google Chrome", Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")),
        ("Google Chrome (x86)", Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe")),
        ("Microsoft Edge", Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")),
        ("Microsoft Edge", Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")),
    )

    def __init__(self, storage: Storage):
        self.storage = storage
        self._sandbox_acl_prepared = False

    def ensure_profile_path_is_isolated(self, profile_id: str) -> None:
        """Reject profile roots that redirect Chromium data through a reparse point."""
        try:
            root = self.storage.paths.root.resolve(strict=True)
        except OSError as exc:
            raise NeVisionError("Не удалось проверить portable-папку профиля.") from exc
        profile = self.storage.profile_path(profile_id)
        profiles = self.storage.paths.profiles
        for path in (self.storage.paths.data, profiles, profile):
            try:
                details = path.lstat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise NeVisionError("Не удалось проверить безопасность папки данных профиля.") from exc
            attributes = getattr(details, "st_file_attributes", 0)
            reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            if stat.S_ISLNK(details.st_mode) or (reparse_flag and attributes & reparse_flag):
                raise NeVisionError(
                    "Папка данных профиля является ссылкой/junction. "
                    "Восстановите обычную папку профиля перед запуском."
                )
        # Check a fixed set of Chromium storage roots without walking caches or
        # the full profile tree on every launch. This detects pre-existing
        # redirects in common cookie, site-storage, extension, and preference
        # locations; it is not a defense against same-user tampering or TOCTOU.
        for relative in self.PROFILE_REPARSE_CHECKS:
            path = profile / relative
            try:
                details = path.lstat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise NeVisionError("Не удалось проверить хранилища Chromium перед запуском.") from exc
            attributes = getattr(details, "st_file_attributes", 0)
            reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            if stat.S_ISLNK(details.st_mode) or (reparse_flag and attributes & reparse_flag):
                raise NeVisionError(
                    "В ключевом хранилище Chromium обнаружена ссылка/junction. "
                    "Профиль не запущен; восстановите обычную структуру данных."
                )
        try:
            resolved_profiles = profiles.resolve(strict=True)
            resolved_profile = profile.resolve(strict=False)
            resolved_data = self.storage.paths.data.resolve(strict=True)
            if (
                resolved_data.parent != root
                or resolved_profiles.parent != resolved_data
                or resolved_profile.parent != resolved_profiles
            ):
                raise ValueError("profile path escaped its dedicated directory")
        except (OSError, RuntimeError, ValueError) as exc:
            raise NeVisionError(
                "Путь данных профиля выходит за пределы его отдельной папки. "
                "Профиль не запущен; проверьте portable-каталог."
            ) from exc

    def ensure_bundled_sandbox_access(self, engine_dir: Path) -> None:
        """Grant Windows sandbox children read-only access to public engine files.

        ZIP extraction does not retain NTFS ACLs. Never extend this grant to
        profile Data/ or follow a junction outside the bundled engine folder.
        """
        if self._sandbox_acl_prepared or sys.platform != "win32":
            return
        root = self.storage.paths.root.resolve(strict=True)
        engine_parent = engine_dir.parent
        if engine_parent.is_symlink() or engine_dir.is_symlink() or engine_dir.resolve(strict=True) != root / self.BUNDLED_RELATIVE.parent:
            raise NeVisionError("Папка встроенного Chromium является ссылкой или находится вне portable-папки.")
        pending = [engine_parent, engine_dir]
        while pending:
            path = pending.pop()
            details = path.lstat()
            attrs = getattr(details, "st_file_attributes", 0)
            if path.is_symlink() or attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise NeVisionError("В папке встроенного Chromium обнаружена ссылка/junction. Распакуйте исходный ZIP заново.")
            if path != engine_parent and stat.S_ISDIR(details.st_mode):
                with os.scandir(path) as children:
                    pending.extend(Path(child.path) for child in children)
        try:
            result = subprocess.run(
                ["icacls.exe", str(engine_dir), "/grant:r", "*S-1-15-2-1:(OI)(CI)RX", "/T"],
                capture_output=True, timeout=60,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise NeVisionError("Не удалось подготовить права чтения встроенного Chromium для песочницы Windows. Распакуйте ZIP в доступную для записи папку NTFS.") from exc
        if result.returncode:
            raise NeVisionError("Windows не разрешила подготовить права чтения встроенного Chromium. Распакуйте ZIP в доступную для записи папку NTFS.")
        self._sandbox_acl_prepared = True

    def bundled_browser(self) -> Path | None:
        engine = self.storage.paths.root / self.BUNDLED_RELATIVE
        # A lone chrome.exe is not a usable portable browser. Require its main
        # runtime payload before offering it as the default.
        if all(path.is_file() for path in (engine, engine.parent / "chrome.dll", engine.parent / "icudtl.dat", engine.parent / "resources.pak", engine.parent / "ENGINE_PROVENANCE.json")):
            return engine
        return None

    def has_native_privacy_baseline(self) -> bool:
        """True only for the older always-on baseline, not V5 opt-in mode."""
        engine = self.bundled_browser()
        if engine is None:
            return False
        try:
            receipt = json.loads((engine.parent / "ENGINE_PROVENANCE.json").read_text(encoding="utf-8"))
            patch_hash = receipt.get("privacy_patch_sha256", "")
            return (receipt.get("format") == "neantik-chromium-source-build-v1"
                    and bool(re.fullmatch(r"[0-9a-f]{64}", patch_hash))
                    and patch_hash != NATIVE_PREVIEW_PATCH_SHA256)
        except (OSError, ValueError, TypeError, AttributeError):
            return False

    def browser_family(self, path: Path) -> str:
        bundled = self.bundled_browser()
        if bundled is not None and path.resolve() == bundled.resolve():
            return "chromium"
        return browser_family_for_executable(path)

    def available_browsers(self) -> list[tuple[str, Path]]:
        discovered: list[tuple[str, Path]] = []
        custom = self.storage.get_setting("browser_path")
        if custom and Path(custom).is_file() and Path(custom).name.casefold() in {"chrome.exe", "msedge.exe"}:
            discovered.append(("Выбранный браузер", Path(custom)))
        bundled = self.bundled_browser()
        if bundled is not None and bundled not in [item[1] for item in discovered]:
            discovered.append(("NeAntik Chromium · встроенный", bundled))
        candidates = list(self.KNOWN_BROWSERS)
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.extend((name, Path(local) / suffix) for name, suffix in (("Google Chrome (пользователь)", "Google/Chrome/Application/chrome.exe"), ("Microsoft Edge (пользователь)", "Microsoft/Edge/Application/msedge.exe")))
        if winreg is not None:
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for binary in ("chrome.exe", "msedge.exe"):
                    try:
                        with winreg.OpenKey(hive, rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{binary}") as key:
                            value = winreg.QueryValue(key, None)
                            candidates.append(("Chrome / Edge (реестр)", Path(str(value).strip('"'))))
                    except OSError:
                        pass
        for name, path in candidates:
            if path.is_file() and path.name.casefold() in {"chrome.exe", "msedge.exe"} and path not in [item[1] for item in discovered]:
                discovered.append((name, path))
        return discovered

    def resolve_browser(self) -> Path:
        engine_dir = self.storage.paths.root / "Engine" / "Chromium"
        if engine_dir.exists() and self.bundled_browser() is None:
            raise NeVisionError("Встроенный Chromium повреждён или распакован не полностью. Распакуйте весь ZIP заново в новую папку; не используйте отдельный EXE.")
        browsers = self.available_browsers()
        if not browsers:
            raise NeVisionError("Не найден встроенный Chromium, Chrome или Microsoft Edge. Проверьте целостность portable-папки либо выберите браузер в Настройках.")
        return browsers[0][1]

    def launch(self, profile: dict[str, Any], extensions: bool = False, diagnostics: bool = False) -> subprocess.Popen[bytes]:
        profile_id = str(profile["id"])
        with self.storage.profile_operation_lock(profile_id):
            return self._launch_locked(profile, profile_id, extensions, diagnostics)

    def _launch_locked(self, profile: dict[str, Any], profile_id: str, extensions: bool = False, diagnostics: bool = False) -> subprocess.Popen[bytes]:
        current_profile = self.storage.get_profile(profile_id)
        if current_profile is None:
            raise NeVisionError("Профиль больше не существует. Обновите список перед запуском.")
        self.ensure_profile_path_is_isolated(profile_id)
        if profile.get("proxy_id") != current_profile.get("proxy_id"):
            raise NeVisionError("Назначенный proxy отсутствует или изменён. Обновите список и проверьте настройки перед запуском.")
        profile = current_profile
        fingerprint = profile["fingerprint"]
        if fingerprint["mode"] != "ordinary":
            raise NeVisionError(
                "Этот профиль использует отключённый экспериментальный режим и не будет запущен. "
                "Исходные данные не изменены. Чтобы продолжить, создайте «Чистую копию»: "
                "она перенесёт настройки, но не cookies, историю или сессии."
            )
        executable = self.resolve_browser()
        family = self.browser_family(executable)
        pinned_family = validated_browser_family(profile.get("browser_family", ""))
        # Existing 0.4.x profiles stay on their original browser even after a
        # bundled core becomes the default for new profiles.
        if family == "chromium" and pinned_family in {"chrome", "edge"} and not self.storage.get_setting("browser_path"):
            for _, candidate in self.available_browsers():
                if self.browser_family(candidate) == pinned_family:
                    executable, family = candidate, pinned_family
                    break
        if pinned_family and pinned_family != family:
            browser_label = {"chrome": "Chrome", "edge": "Edge", "chromium": "встроенным Chromium"}[pinned_family]
            guidance = (
                "Распакуйте полный portable ZIP со встроенным Chromium либо создайте чистую копию профиля."
                if pinned_family == "chromium" else
                "Установите исходный браузер или выберите его EXE в Настройках; иначе создайте чистую копию профиля."
            )
            raise NeVisionError(
                f"Профиль закреплён за {browser_label}. {guidance}"
            )
        self.storage.ensure_profile_closed(profile_id)
        profile_dir = self.storage.profile_path(profile_id)
        browser_data_dir = filesystem_path(profile_dir)
        if family == "chromium" and not pinned_family and browser_data_dir.is_dir() and any(browser_data_dir.iterdir()):
            raise NeVisionError(
                "У профиля уже есть данные, но его прежний браузер не определён. "
                "Не открывайте их новым Chromium вслепую: выберите исходный Chrome/Edge в Настройках "
                "или создайте чистую копию профиля."
            )
        browser_data_dir.mkdir(parents=True, exist_ok=True)
        arguments = [
            str(executable),
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            *identity_arguments(fingerprint),
        ]
        if profile.get("proxy_id"):
            proxy = self.storage.get_proxy(str(profile["proxy_id"]))
            if proxy:
                if proxy["scheme"] == "socks5" and (proxy.get("username") or proxy.get("password_protected")):
                    raise NeVisionError("Chromium/Chrome/Edge не поддерживает SOCKS5 с логином/паролем. Используйте proxy с IP-авторизацией или HTTP(S). Пароль в vault хранится, но автоматически в браузер не передаётся.")
                arguments.append(f"--proxy-server={proxy_endpoint(proxy)}")
                if family == "chromium":
                    arguments.extend(bundled_proxy_privacy_arguments(proxy))
            else:
                raise NeVisionError("Назначенный proxy отсутствует. Выберите другой proxy перед запуском.")
        if extensions:
            arguments.append("edge://extensions/" if executable.name.lower() == "msedge.exe" else "chrome://extensions/")
        if diagnostics:
            arguments.append(PRIVACY_CHECK_URL)
        if family == "chromium":
            self.ensure_bundled_sandbox_access(executable.parent)
        # Pin before spawning so even a storage write failure cannot leave a
        # newly launched browser attached to an unguarded profile.
        self.storage.pin_browser_family(profile_id, family)
        if family == "chromium":
            try:
                initialize_privacy_defaults(browser_data_dir)
                ensure_managed_download_directory(browser_data_dir)
            except (OSError, ValueError) as exc:
                raise NeVisionError("Не удалось безопасно подготовить настройки нового профиля Chromium или папку загрузок. Проверьте доступ к Data и отсутствие ссылок/junction.") from exc
        try:
            process = subprocess.Popen(arguments, cwd=str(profile_dir), creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        except OSError as exc:
            raise NeVisionError(f"Не удалось запустить браузер: {exc}") from exc
        self.storage.wait_for_chromium_lock(profile_id, process)
        if process.poll() not in (None, 0):
            raise NeVisionError(f"Браузер завершился при запуске (код {process.returncode}). Проверьте выбранный EXE в Настройках.")
        try:
            self.storage.touch_profile_launch(profile_id)
        except NeVisionError:
            # A launched browser must remain tracked even if its audit write fails.
            process.nevision_warning = "Браузер открыт, но запись в журнал не сохранена. Проверьте доступ к Data."
        return process


def draw_round_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, radius: float, fill: str) -> None:
    """Draw a compact rounded surface without pulling in a web or image renderer."""

    radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    canvas.create_rectangle(x1 + radius, y1, x2 - radius, y2, fill=fill, outline=fill)
    canvas.create_rectangle(x1, y1 + radius, x2, y2 - radius, fill=fill, outline=fill)
    canvas.create_arc(x1, y1, x1 + 2 * radius, y1 + 2 * radius, start=90, extent=90, fill=fill, outline=fill)
    canvas.create_arc(x2 - 2 * radius, y1, x2, y1 + 2 * radius, start=0, extent=90, fill=fill, outline=fill)
    canvas.create_arc(x1, y2 - 2 * radius, x1 + 2 * radius, y2, start=180, extent=90, fill=fill, outline=fill)
    canvas.create_arc(x2 - 2 * radius, y2 - 2 * radius, x2, y2, start=270, extent=90, fill=fill, outline=fill)


def draw_vector_icon(canvas: tk.Canvas, name: str, x: float, y: float, size: float, color: str) -> None:
    """Render NeVision's small native 24px line-icon vocabulary on a Tk canvas."""

    scale = size / 24
    stroke = max(1, size * 1.8 / 24)

    def point(px: float, py: float) -> tuple[float, float]:
        return x + px * scale, y + py * scale

    def line(*points: tuple[float, float], width: float = stroke) -> None:
        flat: list[float] = []
        for px, py in points:
            sx, sy = point(px, py)
            flat.extend((sx, sy))
        canvas.create_line(*flat, fill=color, width=width, capstyle="round", joinstyle="round")

    def circle(cx: float, cy: float, radius: float, width: float = stroke) -> None:
        x1, y1 = point(cx - radius, cy - radius)
        x2, y2 = point(cx + radius, cy + radius)
        canvas.create_oval(x1, y1, x2, y2, outline=color, width=width)

    def rect(px1: float, py1: float, px2: float, py2: float, width: float = stroke) -> None:
        x1, y1 = point(px1, py1)
        x2, y2 = point(px2, py2)
        canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=width)

    if name == "add":
        line((12, 5), (12, 19))
        line((5, 12), (19, 12))
    elif name == "profiles":
        rect(4, 4, 16, 16)
        line((8, 20), (18, 20), (20, 18), (20, 8))
        line((8.5, 9.3), (10.9, 11.7), (14, 8.6))
    elif name == "vault":
        rect(4, 5, 20, 20)
        line((8, 5), (8, 3.8), (9.8, 2), (14.2, 2), (16, 3.8), (16, 5))
        circle(12, 12.5, 2.5)
        line((12, 15), (12, 17))
    elif name == "proxy":
        circle(6, 12, 2.5)
        circle(18, 6, 2.5)
        circle(18, 18, 2.5)
        line((8.3, 10.9), (15.7, 7.1))
        line((8.3, 13.1), (15.7, 16.9))
    elif name == "history":
        line((4.5, 7.5), (4.5, 3.8), (8.2, 3.8))
        line((4.5, 3.8), (7.3, 6.6))
        x1, y1 = point(5.1, 4.5)
        x2, y2 = point(20.1, 19.7)
        canvas.create_arc(x1, y1, x2, y2, start=25, extent=290, style="arc", outline=color, width=stroke)
        line((12, 8), (12, 12), (14.9, 13.8))
    elif name == "backup":
        line((6, 8.5), (6, 5.8), (7.8, 4), (16.2, 4), (18, 5.8), (18, 8.5))
        rect(3, 9, 21, 20)
        line((9, 14), (12, 11), (15, 14))
        line((12, 11), (12, 17))
    elif name == "health":
        line((12, 3.5), (19, 6.35), (19, 11.7), (17.5, 16.7), (12, 20.5), (6.5, 16.7), (5, 11.7), (5, 6.35), (12, 3.5))
        line((8, 12.2), (10.15, 12.2), (11.4, 9.65), (13.15, 14.3), (14.55, 11.75), (16.3, 11.75))
    elif name == "search":
        circle(10.7, 10.7, 5.7)
        line((15, 15), (20, 20))
    elif name == "settings":
        circle(12, 12, 3)
        circle(12, 12, 7.2, max(1, stroke * 0.85))
        for start, end in (((12, 2.7), (12, 5)), ((12, 19), (12, 21.3)), ((2.7, 12), (5, 12)), ((19, 12), (21.3, 12)), ((5.45, 5.45), (7.1, 7.1)), ((16.9, 16.9), (18.55, 18.55)), ((18.55, 5.45), (16.9, 7.1)), ((7.1, 16.9), (5.45, 18.55))):
            line(start, end, width=max(1, stroke * 0.85))
    elif name == "launch":
        line((13, 5), (19, 5), (19, 11))
        line((19, 5), (10.5, 13.5))
        line((18, 14.5), (18, 18), (16, 20), (6, 20), (4, 18), (4, 8), (6, 6), (9.5, 6))
    elif name == "filter":
        line((4, 6), (20, 6))
        line((7, 12), (17, 12))
        line((10, 18), (14, 18))
    elif name == "folder":
        line((3.5, 8), (9, 8), (10.7, 5.5), (19.5, 5.5), (21, 7), (21, 18.5), (19.5, 20), (4.5, 20), (3, 18.5), (3, 9.5), (3.5, 8))
        line((3.2, 10), (20.8, 10))
    elif name == "edit":
        line((5, 19), (8.4, 18.3), (18.5, 8.2), (15.8, 5.5), (5.7, 15.6), (5, 19))
        line((14.5, 6.8), (17.2, 9.5))
    elif name == "clone":
        rect(4, 7, 14, 17)
        line((10, 4), (18, 4), (20, 6), (20, 16), (18, 18), (14, 18))
    elif name == "trash":
        line((5, 7), (19, 7))
        line((9, 7), (9, 4.5), (15, 4.5), (15, 7))
        line((7, 7), (8, 20), (16, 20), (17, 7))
        line((10.5, 10), (10.5, 17))
        line((13.5, 10), (13.5, 17))
    elif name == "check":
        circle(12, 12, 8)
        line((8, 12), (10.8, 14.8), (16.5, 9.2))
    elif name == "info":
        circle(12, 12, 8)
        line((12, 10.5), (12, 16))
        x1, y1 = point(11.1, 7.3)
        x2, y2 = point(12.9, 9.1)
        canvas.create_oval(x1, y1, x2, y2, fill=color, outline=color)
    else:
        circle(12, 12, 7)


class VectorIcon(tk.Canvas):
    """A sharp, dependency-free native Canvas icon matching the SVG icon set."""

    def __init__(self, parent: tk.Misc, name: str, size: int, color: str, background: str):
        super().__init__(parent, width=size, height=size, bg=background, highlightthickness=0, borderwidth=0)
        draw_vector_icon(self, name, 0, 0, size, color)


class BrandMark(tk.Canvas):
    """Native rendering of the shipped NeVision logo mark for a crisp desktop UI."""

    def __init__(self, parent: tk.Misc, size: int, background: str, colors: dict[str, str]):
        super().__init__(parent, width=size, height=size, bg=background, highlightthickness=0, borderwidth=0)
        inset = max(1, round(size * 0.06))
        draw_round_rect(self, inset, inset, size - inset, size - inset, max(6, round(size * 0.27)), colors["accent"])
        self.create_line(
            size * 0.31,
            size * 0.69,
            size * 0.31,
            size * 0.33,
            size * 0.64,
            size * 0.69,
            size * 0.64,
            size * 0.33,
            fill=colors["ink"],
            width=max(2, round(size * 0.078)),
            capstyle="round",
            joinstyle="round",
        )
        point = max(4, round(size * 0.09))
        self.create_oval(size * 0.72 - point, size * 0.27 - point, size * 0.72 + point, size * 0.27 + point, fill=colors["lime"], outline=colors["lime_soft"], width=1)


class ProfileBadge(tk.Canvas):
    """Small profile identity tile; it is decorative and never claims device identity."""

    def __init__(self, parent: tk.Misc, label: str, size: int, background: str, colors: dict[str, str]):
        super().__init__(parent, width=size, height=size, bg=background, highlightthickness=0, borderwidth=0)
        swatches = tuple(colors[f"badge_{index}"] for index in range(1, 6))
        index = sum(ord(char) for char in label) % len(swatches)
        draw_round_rect(self, 0, 0, size, size, max(7, round(size * 0.23)), swatches[index])
        initials = (label.strip() or "P")[:1].upper()
        self.create_text(size / 2, size / 2 + 0.5, text=initials, fill=colors["text"], font=("Segoe UI", max(10, round(size * 0.31)), "bold"))
        self.create_oval(size - 10, size - 10, size - 4, size - 4, fill=colors["lime"], outline=colors["lime_soft"])


class HoverTip:
    """Small delayed hint for native controls; no extra UI framework or polling."""

    def __init__(self, widget: tk.Misc, text: str, colors: dict[str, str]):
        self.widget = widget
        self.text = text
        self.colors = colors
        self.timer: str | None = None
        self.popup: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<FocusIn>", self._schedule, add="+")
        widget.bind("<FocusOut>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event: tk.Event[Any] | None = None) -> None:
        self._hide()
        self.timer = self.widget.after(550, self._show)

    def _show(self) -> None:
        self.timer = None
        if not self.widget.winfo_exists() or self.popup is not None:
            return
        popup = tk.Toplevel(self.widget)
        popup.withdraw()
        popup.overrideredirect(True)
        tk.Label(popup, text=self.text, justify="left", wraplength=320,
                 bg=self.colors["panel_2"], fg=self.colors["text"],
                 relief="solid", borderwidth=1, padx=10, pady=7,
                 font=("Segoe UI", 9)).pack()
        popup.update_idletasks()
        x = min(self.widget.winfo_rootx() + 12, max(0, self.widget.winfo_screenwidth() - popup.winfo_reqwidth() - 12))
        y = min(self.widget.winfo_rooty() + self.widget.winfo_height() + 6,
                max(0, self.widget.winfo_screenheight() - popup.winfo_reqheight() - 12))
        popup.geometry(f"+{x}+{y}")
        popup.deiconify()
        self.popup = popup

    def _hide(self, _event: tk.Event[Any] | None = None) -> None:
        if self.timer is not None:
            with contextlib.suppress(tk.TclError):
                self.widget.after_cancel(self.timer)
            self.timer = None
        if self.popup is not None:
            with contextlib.suppress(tk.TclError):
                self.popup.destroy()
            self.popup = None


class IconButton(tk.Canvas):
    """Keyboard-focusable, native icon button with a small, fast hover response."""

    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        icon: str,
        command: Any,
        colors: dict[str, str],
        canvas_bg: str,
        kind: str = "secondary",
        width: int | None = None,
        height: int = 38,
        tooltip: str | None = None,
    ):
        self.text = text
        self.icon = icon
        self.command = command
        self.colors = colors
        self.canvas_bg = canvas_bg
        self.kind = kind
        self.height = height
        label_font = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        self.width = width or max(height, label_font.measure(text) + (43 if icon else 24))
        self.hovered = False
        self.focused = False
        self._pressed_keys: set[str] = set()
        super().__init__(parent, width=self.width, height=height, bg=canvas_bg, highlightthickness=0, borderwidth=0, cursor="hand2", takefocus=1)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Return>", self._on_key)
        self.bind("<space>", self._on_key)
        self.bind("<KeyRelease-Return>", self._on_key_release)
        self.bind("<KeyRelease-space>", self._on_key_release)
        self.hint = HoverTip(self, tooltip, colors) if tooltip else None
        self._render()

    def _palette(self) -> tuple[str, str, str, str]:
        if self.kind == "primary":
            return self.colors["accent"], self.colors["accent_hover"], self.colors["ink"], self.colors["ink"]
        if self.kind == "danger":
            return self.colors["danger_surface"], self.colors["danger_hover"], self.colors["danger"], self.colors["danger"]
        if self.kind == "quiet":
            return self.canvas_bg, self.colors["panel_2"], self.colors["muted"], self.colors["muted"]
        return self.colors["panel_2"], self.colors["panel_hover"], self.colors["text"], self.colors["violet_soft"]

    def _render(self) -> None:
        self.delete("all")
        base, hover, text_color, icon_color = self._palette()
        fill = hover if self.hovered else base
        draw_round_rect(self, 0, 0, self.width, self.height, 8, fill)
        if self.focused:
            self.create_rectangle(2, 2, self.width - 2, self.height - 2, outline=self.colors["violet_soft"], width=1)
        if self.icon:
            draw_vector_icon(self, self.icon, 11, (self.height - 18) / 2, 18, icon_color)
            anchor_x = 37
        else:
            anchor_x = self.width / 2
        self.create_text(anchor_x, self.height / 2 + 0.5, text=self.text, anchor="w" if self.icon else "center", fill=text_color, font=("Segoe UI", 9, "bold"))

    def _on_enter(self, _event: tk.Event[Any]) -> None:
        self.hovered = True
        self._render()

    def _on_leave(self, _event: tk.Event[Any]) -> None:
        self.hovered = False
        self._render()

    def _on_focus_in(self, _event: tk.Event[Any]) -> None:
        self.focused = True
        self._render()

    def _on_focus_out(self, _event: tk.Event[Any]) -> None:
        self.focused = False
        self._pressed_keys.clear()
        self._render()

    def _on_click(self, _event: tk.Event[Any]) -> None:
        self.focus_set()
        self.command()

    def _on_key(self, event: tk.Event[Any]) -> str:
        key = str(event.keysym)
        if key not in {"Return", "space"}:
            return "break"
        if key not in self._pressed_keys:
            self._pressed_keys.add(key)
            self.command()
        return "break"

    def _on_key_release(self, event: tk.Event[Any]) -> str:
        self._pressed_keys.discard(str(event.keysym))
        return "break"


class BaseDialog(tk.Toplevel):
    def __init__(self, app: "NeVisionApp", title: str, size: str = "520x420"):
        super().__init__(app.root)
        self.app = app
        self.title(title)
        self.geometry(size)
        self.minsize(400, 280)
        self.transient(app.root)
        self.grab_set()
        self.configure(bg=app.colors["panel"])
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())
        self._initial_window_setup_scheduled = False
        self.bind("<Configure>", self._schedule_initial_window_setup, add="+")

    def _schedule_initial_window_setup(self, event: tk.Event[Any]) -> None:
        """Wait for the final native Toplevel before centering and styling its frame."""
        if self._initial_window_setup_scheduled or event.widget is not self or event.width <= 1 or event.height <= 1:
            return
        self._initial_window_setup_scheduled = True
        self.after_idle(self._finish_initial_window_setup)

    def _finish_initial_window_setup(self) -> None:
        if not self.winfo_exists():
            return
        self._center_on_parent()
        self.app._configure_title_bar(self)

    def _center_on_parent(self) -> None:
        """Place a modal visibly near the parent instead of at the virtual origin."""
        if not self.winfo_exists():
            return
        self.update_idletasks()
        parent = self.app.root
        parent.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = max(parent.winfo_width(), parent.winfo_reqwidth())
        parent_height = max(parent.winfo_height(), parent.winfo_reqheight())
        target_x = parent_x + max(0, (parent_width - width) // 2)
        target_y = parent_y + max(0, (parent_height - height) // 2)
        virtual_x = self.winfo_vrootx()
        virtual_y = self.winfo_vrooty()
        virtual_right = virtual_x + self.winfo_vrootwidth() - width
        virtual_bottom = virtual_y + self.winfo_vrootheight() - height
        target_x = max(virtual_x, min(target_x, virtual_right))
        target_y = max(virtual_y, min(target_y, virtual_bottom))
        self.geometry(f"+{target_x}+{target_y}")

    def labeled_entry(self, parent: tk.Widget, label: str, value: str = "", show: str | None = None) -> ttk.Entry:
        ttk.Label(parent, text=label, style="Label.TLabel").pack(anchor="w", pady=(0, 5))
        entry = ttk.Entry(parent, style="Input.TEntry", show=show or "")
        entry.insert(0, value)
        entry.pack(fill="x", pady=(0, 14))
        return entry

    def footer(self, parent: tk.Widget, on_submit: Any, submit_label: str) -> None:
        footer = ttk.Frame(parent, style="Panel.TFrame")
        footer.pack(fill="x", side="bottom", pady=(16, 0))
        ttk.Button(footer, text="Отмена", style="Ghost.TButton", command=self.destroy).pack(side="right")
        ttk.Button(footer, text=submit_label, style="Accent.TButton", command=on_submit).pack(side="right", padx=(0, 8))


class ProfileDialog(BaseDialog):
    def __init__(self, app: "NeVisionApp", profile: dict[str, Any] | None = None):
        super().__init__(app, "Новый профиль" if not profile else "Изменить профиль", "560x650")
        self.profile = profile
        self.identity = profile.get("fingerprint", ordinary_identity()) if profile else ordinary_identity()
        if self.identity["mode"] != "ordinary":
            messagebox.showerror(
                APP_NAME,
                "Этот профиль использует отключённый экспериментальный режим. Его данные сохранены. "
                "Создайте «Чистую копию», чтобы продолжить без cookies, истории и сессий.",
                parent=self,
            )
            self.destroy()
            return
        viewport = ttk.Frame(self, style="Panel.TFrame")
        viewport.pack(fill="both", expand=True)
        canvas = tk.Canvas(viewport, bg=app.colors["panel"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        self.form_canvas = canvas
        self.bind("<MouseWheel>", self._scroll_form, add="+")
        body = ttk.Frame(canvas, style="Panel.TFrame", padding=24)
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        ttk.Label(body, text="Профиль браузера", style="DialogTitle.TLabel").pack(anchor="w", pady=(0, 16))
        self.name = self.labeled_entry(body, "Название *", profile.get("name", "") if profile else "")
        self.group = self.labeled_entry(body, "Папка / группа", profile.get("group_name", "") if profile else "")
        self.tags = self.labeled_entry(body, "Теги", profile.get("tags", "") if profile else "")
        ttk.Label(body, text="Proxy", style="Label.TLabel").pack(anchor="w", pady=(0, 5))
        proxy_labels, self.proxy_ids = proxy_choices(app.storage.list_proxies())
        selected_id = profile.get("proxy_id") if profile else ""
        selected_index = next((index for index, proxy_id in enumerate(self.proxy_ids) if proxy_id == selected_id), 0)
        self.proxy = ttk.Combobox(body, values=proxy_labels, style="Input.TCombobox", state="readonly")
        self.proxy.current(selected_index)
        self.proxy.pack(fill="x", pady=(0, 14))
        browser_hint = ("Встроенный Chromium · настройки fingerprint не изменяются приложением."
                        if app.launcher.bundled_browser() else
                        "Обычный Chrome или Edge · настройки fingerprint не изменяются приложением.")
        ttk.Label(body, text=browser_hint, style="Muted.TLabel", wraplength=470).pack(anchor="w", pady=(0, 10))
        if not profile and app.launcher.bundled_browser():
            ttk.Label(body, text="Новый профиль: сторонние cookies, геолокация, уведомления, камера и микрофон блокируются по умолчанию. При необходимости измените разрешения в Chromium.", style="Muted.TLabel", wraplength=470).pack(anchor="w", pady=(0, 10))
        ttk.Label(body, text="Заметка", style="Label.TLabel").pack(anchor="w", pady=(0, 5))
        self.notes = tk.Text(
            body,
            height=3,
            bg=app.colors["input"],
            fg=app.colors["text"],
            insertbackground=app.colors["text"],
            selectbackground=app.colors["selection"],
            selectforeground=app.colors["text"],
            relief="flat",
            wrap="word",
            font=("Segoe UI", 10),
        )
        self.notes.insert("1.0", profile.get("notes", "") if profile else "")
        self.notes.pack(fill="both", expand=True)
        self.footer(self, self.save, "Сохранить")
        self.name.focus_set()

    def _scroll_form(self, event: tk.Event[Any]) -> str | None:
        # The Toplevel bindtag also receives wheel events from its form fields.
        # Leave controls with their own scrolling/selection behavior alone.
        if isinstance(event.widget, (tk.Text, ttk.Combobox)) or not event.delta:
            return None
        steps = max(1, abs(event.delta) // 120)
        self.form_canvas.yview_scroll(-steps if event.delta > 0 else steps, "units")
        return "break"

    def save(self) -> None:
        try:
            identity = ordinary_identity()
            profile_id = self.app.storage.save_profile(
                {
                    "name": self.name.get(),
                    "group_name": self.group.get(),
                    "tags": self.tags.get(),
                    "notes": self.notes.get("1.0", "end-1c"),
                    "proxy_id": self.proxy_ids[self.proxy.current()] if self.proxy.current() >= 0 else "",
                    "fingerprint": identity,
                },
                self.profile.get("id") if self.profile else None,
            )
        except NeVisionError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return
        self.app.refresh_profiles(select_id=profile_id)
        self.destroy()


class ProxyDialog(BaseDialog):
    def __init__(self, app: "NeVisionApp", proxy: dict[str, Any] | None = None, after_save: Any | None = None):
        # The complete form, including its password safety note and footer, must
        # remain visible at common 150% Windows scaling.  The former 600px
        # logical height clipped the Save/Cancel controls on a 1080p display.
        super().__init__(app, "Новый proxy" if not proxy else "Изменить proxy", "540x700")
        self.proxy = proxy
        self.after_save = after_save
        body = ttk.Frame(self, style="Panel.TFrame", padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Proxy vault", style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(body, text="Пароль шифруется Windows DPAPI и доступен только текущему Windows-пользователю.", style="Hint.TLabel", wraplength=460).pack(anchor="w", pady=(5, 18))
        self.name = self.labeled_entry(body, "Название *", proxy.get("name", "") if proxy else "")
        ttk.Label(body, text="Тип", style="Label.TLabel").pack(anchor="w", pady=(0, 5))
        self.scheme = ttk.Combobox(body, values=["http", "https", "socks5"], style="Input.TCombobox", state="readonly")
        self.scheme.set(proxy.get("scheme", "http") if proxy else "http")
        self.scheme.pack(fill="x", pady=(0, 14))
        self.host = self.labeled_entry(body, "Сервер / IP *", proxy.get("host", "") if proxy else "")
        self.host_route_hint = HoverTip(
            self.host,
            "Если указано имя сервера, адрес самого proxy может разрешаться локально. "
            "IP-адрес убирает только этот DNS-шаг; отсутствие других утечек не доказано.",
            app.colors,
        )
        self.port = self.labeled_entry(body, "Порт *", str(proxy.get("port", "")) if proxy else "")
        self.username = self.labeled_entry(body, "Логин", proxy.get("username", "") if proxy else "")
        ttk.Label(body, text="Пароль" + (" (оставьте пустым, чтобы не менять)" if proxy else ""), style="Label.TLabel").pack(anchor="w", pady=(0, 5))
        self.password = ttk.Entry(body, style="Input.TEntry", show="●")
        self.password.pack(fill="x", pady=(0, 3))
        ttk.Label(body, text="NeAntik не передаёт пароль браузеру автоматически; браузер запросит его штатно при необходимости.", style="Hint.TLabel", wraplength=460).pack(anchor="w")
        self.footer(body, self.save, "Сохранить proxy")
        self.name.focus_set()

    def save(self) -> None:
        password = self.password.get()
        try:
            proxy_id = self.app.storage.save_proxy(
                {
                    "name": self.name.get(),
                    "scheme": self.scheme.get(),
                    "host": self.host.get(),
                    "port": self.port.get(),
                    "username": self.username.get(),
                    "password": password if password or not self.proxy else None,
                },
                self.proxy.get("id") if self.proxy else None,
            )
        except NeVisionError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return
        self.app.refresh_profiles()
        if proxy_host_requires_local_name_resolution(self.host.get()):
            self.app.set_status(f"Proxy сохранён: {proxy_id[:8]}. Имя proxy может разрешаться локально.")
        else:
            self.app.set_status(f"Proxy сохранён: {proxy_id[:8]}. IP proxy не требует разрешения имени узла.")
        if self.after_save:
            self.after_save()
        self.destroy()


class ProxyVaultDialog(BaseDialog):
    def __init__(self, app: "NeVisionApp"):
        super().__init__(app, "Proxy vault", "760x510")
        body = ttk.Frame(self, style="Panel.TFrame", padding=22)
        body.pack(fill="both", expand=True)
        header = ttk.Frame(body, style="Panel.TFrame")
        header.pack(fill="x", pady=(0, 14))
        ttk.Label(header, text="Proxy vault", style="DialogTitle.TLabel").pack(side="left")
        ttk.Button(header, text="Новый proxy", style="Accent.TButton", command=lambda: ProxyDialog(app, after_save=self.refresh)).pack(side="right")
        ttk.Label(body, text="Пароли защищены Windows DPAPI. HTTP(S): ввод в окне браузера вручную. SOCKS5: только без логина/пароля (например, IP-авторизация). Vault не передаёт пароль браузеру автоматически.", style="Hint.TLabel", wraplength=700).pack(anchor="w", pady=(0, 13))
        table_wrap = ttk.Frame(body, style="Panel.TFrame")
        table_wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table_wrap, columns=("name", "endpoint", "auth"), show="headings", style="History.Treeview", selectmode="browse")
        for key, label, width in (("name", "НАЗВАНИЕ", 185), ("endpoint", "ENDPOINT", 330), ("auth", "AUTH", 120)):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, stretch=key == "endpoint")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview, style="NV.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        actions = ttk.Frame(body, style="Panel.TFrame")
        actions.pack(fill="x", pady=(14, 0))
        ttk.Button(actions, text="Изменить", style="Ghost.TButton", command=self.edit).pack(side="left")
        ttk.Button(actions, text="Удалить", style="Danger.TButton", command=self.delete).pack(side="left", padx=(7, 0))
        ttk.Button(actions, text="Закрыть", style="Ghost.TButton", command=self.destroy).pack(side="right")
        self.refresh()

    def refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for proxy in self.app.storage.list_proxies():
            try:
                endpoint = proxy_endpoint(proxy)
            except NeVisionError:
                endpoint = "Некорректный сервер — измените proxy"
            auth = "сохранён" if proxy.get("password_protected") else ("логин без пароля" if proxy.get("username") else "не нужен")
            self.tree.insert("", "end", iid=proxy["id"], values=(proxy["name"], endpoint, auth))

    def selected_proxy(self) -> dict[str, Any] | None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(APP_NAME, "Выберите proxy в списке.", parent=self)
            return None
        return self.app.storage.get_proxy(selected[0])

    def edit(self) -> None:
        proxy = self.selected_proxy()
        if proxy:
            ProxyDialog(self.app, proxy=proxy, after_save=self.refresh)

    def delete(self) -> None:
        proxy = self.selected_proxy()
        if not proxy:
            return
        if not messagebox.askyesno(APP_NAME, f"Удалить proxy «{proxy['name']}»? Он будет отвязан от профилей, но сами профили останутся.", icon="warning", parent=self):
            return
        try:
            self.app.storage.delete_proxy(str(proxy["id"]))
        except NeVisionError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return
        self.app.refresh_profiles()
        self.app.set_status(f"Удалён proxy: {proxy['name']}")
        self.refresh()


class SettingsDialog(BaseDialog):
    def __init__(self, app: "NeVisionApp"):
        super().__init__(app, "Настройки", "650x680")
        viewport = ttk.Frame(self, style="Panel.TFrame")
        viewport.pack(fill="both", expand=True)
        canvas = tk.Canvas(viewport, bg=app.colors["panel"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        self.settings_canvas = canvas
        self.bind("<MouseWheel>", self._scroll_settings, add="+")
        body = ttk.Frame(canvas, style="Panel.TFrame", padding=24)
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        ttk.Label(body, text="Настройки", style="DialogTitle.TLabel").pack(anchor="w", pady=(0, 15))
        ttk.Label(body, text="Оформление", style="Label.TLabel").pack(anchor="w", pady=(0, 5))
        self.theme = ttk.Combobox(body, values=list(THEME_OPTIONS), style="Input.TCombobox", state="readonly")
        self.theme.set(THEME_LABELS[app.theme_preference])
        self.theme.pack(fill="x", pady=(0, 4))
        ttk.Label(
            body,
            text="Системная тема следует параметру «Режим приложений» Windows и обновляется без перезапуска, когда нет открытых диалогов.",
            style="Hint.TLabel",
            wraplength=520,
        ).pack(anchor="w", pady=(0, 16))
        ttk.Separator(body).pack(fill="x", pady=(0, 14))
        ttk.Label(body, text="Браузер", style="Label.TLabel").pack(anchor="w", pady=(0, 5))
        ttk.Label(body, text="Новые профили открываются во встроенном Chromium. Отдельный Chrome не нужен.",
                  style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=(0, 5))
        ttk.Label(body, text="Встроенный Chromium с proxy не обходит его для localhost, ограничивает фоновый DNS и прямой WebRTC UDP. Имя самого proxy может разрешаться локально. Локальные сайты и звонки могут работать иначе; часовой пояс остаётся системным.",
                  style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=(0, 9))
        self.compatibility_button = ttk.Button(body, text="Совместимость со старыми профилями ▸", style="Ghost.TButton", command=self.toggle_compatibility)
        self.compatibility_button.pack(anchor="w", pady=(0, 7))
        self.compatibility = ttk.Frame(body, style="Panel.TFrame")
        ttk.Label(self.compatibility, text="Путь к прежнему Chrome или Edge (необязательно)", style="Label.TLabel").pack(anchor="w", pady=(0, 5))
        row = ttk.Frame(self.compatibility, style="Panel.TFrame")
        row.pack(fill="x", pady=(0, 5))
        self.path = ttk.Entry(row, style="Input.TEntry")
        self.path.insert(0, app.storage.get_setting("browser_path"))
        self.path.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Выбрать…", style="Ghost.TButton", command=self.choose).pack(side="left", padx=(8, 0))
        ttk.Label(self.compatibility, text="Нужно только для старых данных, закреплённых за Chrome/Edge. Пустое поле использует встроенный Chromium для новых профилей.",
                  style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=(0, 5))
        if self.path.get():
            self.toggle_compatibility()
        ttk.Separator(body).pack(fill="x", pady=8)
        ttk.Label(body, text="Где мои данные?", style="Label.TLabel").pack(anchor="w", pady=(8, 5))
        ttk.Label(body, text="Тот же ПК и Windows-аккаунт: закройте браузер и скопируйте всю portable-папку. Профили, история и backup лежат в Data рядом с EXE; backup также содержит загрузки и данные сайтов, поэтому храните его как пароль.",
                  style="Hint.TLabel", wraplength=540).pack(anchor="w")
        ttk.Label(body, text="Другой ПК или Windows-аккаунт", style="Label.TLabel").pack(anchor="w", pady=(10, 5))
        ttk.Label(body, text="Перенесите только настройки выбранного профиля: имя, группу, теги и режим браузера. Импорт создаст новый пустой профиль. Вход на сайты и proxy настройте заново.",
                  style="Hint.TLabel", wraplength=540).pack(anchor="w")
        transfer_actions = ttk.Frame(body, style="Panel.TFrame")
        transfer_actions.pack(anchor="w", pady=(8, 0))
        ttk.Button(transfer_actions, text="Экспорт настроек…", style="Ghost.TButton",
                   command=lambda: self._run_transfer_action(app.export_selected_template)).pack(side="left")
        ttk.Button(transfer_actions, text="Импорт настроек…", style="Ghost.TButton",
                   command=lambda: self._run_transfer_action(app.import_profile_template)).pack(side="left", padx=(8, 0))
        ttk.Label(body, text=PORTABILITY_WARNING, style="Hint.TLabel", wraplength=540).pack(anchor="w", pady=(8, 0))
        self.footer(self, self.save, "Сохранить")

    def _scroll_settings(self, event: tk.Event[Any]) -> str | None:
        if isinstance(event.widget, ttk.Combobox) or not event.delta:
            return None
        steps = max(1, abs(event.delta) // 120)
        self.settings_canvas.yview_scroll(-steps if event.delta > 0 else steps, "units")
        return "break"

    def _run_transfer_action(self, action: Any) -> None:
        # The existing import/export dialogs are parented to the main window.
        # Temporarily hide this modal so their confirmations stay in front.
        self.grab_release()
        self.withdraw()
        try:
            action()
        finally:
            if self.winfo_exists():
                self.deiconify()
                self.grab_set()

    def toggle_compatibility(self) -> None:
        if self.compatibility.winfo_manager():
            self.compatibility.pack_forget()
            self.compatibility_button.configure(text="Совместимость со старыми профилями ▸")
        else:
            self.compatibility.pack(fill="x", after=self.compatibility_button, pady=(0, 6))
            self.compatibility_button.configure(text="Совместимость со старыми профилями ▾")

    def choose(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Выберите Chrome/Edge/Chromium", filetypes=[("Исполняемый файл", "*.exe"), ("Все файлы", "*.*")])
        if path:
            self.path.delete(0, "end")
            self.path.insert(0, path)

    def save(self) -> None:
        candidate = self.path.get().strip()
        if candidate and not Path(candidate).is_file():
            messagebox.showerror(APP_NAME, "Указанный файл браузера не найден.", parent=self)
            return
        if candidate:
            try:
                browser_family_for_executable(Path(candidate))
            except NeVisionError as exc:
                messagebox.showerror(APP_NAME, str(exc), parent=self)
                return
        preference = THEME_OPTIONS.get(self.theme.get(), THEME_SYSTEM)
        self.app.storage.set_setting("browser_path", candidate)
        self.destroy()
        self.app.set_theme_preference(preference)
        self.app.set_status("Настройки сохранены")


class HistoryDialog(BaseDialog):
    def __init__(self, app: "NeVisionApp", profile_id: str | None = None):
        super().__init__(app, "История действий", "760x520")
        body = ttk.Frame(self, style="Panel.TFrame", padding=22)
        body.pack(fill="both", expand=True)
        title = "История профиля" if profile_id else "Общая история действий"
        ttk.Label(body, text=title, style="DialogTitle.TLabel").pack(anchor="w", pady=(0, 14))
        ttk.Button(body, text="Закрыть", style="Ghost.TButton", command=self.destroy).pack(side="bottom", anchor="e", pady=(14, 0))
        list_frame = ttk.Frame(body, style="Panel.TFrame")
        list_frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(list_frame, columns=("time", "action", "profile", "details"), show="headings", style="History.Treeview")
        for key, label, width in (("time", "Время", 145), ("action", "Действие", 165), ("profile", "Профиль", 150), ("details", "Детали", 260)):
            tree.heading(key, text=label)
            tree.column(key, width=width, stretch=key == "details")
        for event in app.storage.list_events(profile_id):
            tree.insert("", "end", values=(display_datetime(event["created_at"]), event["action"], event.get("profile_name") or "—", event["details"]))
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview, style="NV.Vertical.TScrollbar")
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        tree.focus_set()


class NeVisionApp:
    def __init__(self, storage: Storage, paths: AppPaths):
        self.storage = storage
        self.paths = paths
        self.launcher = BrowserLauncher(storage)
        self.running: dict[str, subprocess.Popen[bytes]] = {}
        self.theme_preference = normalize_theme_preference(storage.get_setting(THEME_SETTING_KEY, THEME_SYSTEM))
        self.active_theme = resolve_theme(self.theme_preference)
        self.colors = palette_for_theme(self.active_theme)
        self._shell_widgets: list[tk.Widget] = []
        self._search_refresh_id: str | None = None
        self._background_results: queue.Queue[tuple[str, Any, Any, Any, Exception | None]] = queue.Queue()
        self._background_operations: set[str] = set()
        self._executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="nevision")
        self._closing = False
        self._active_profiles: set[str] = set()
        self._unknown_profiles: set[str] = set()
        self._clipboard_secret: str | None = None
        self._clipboard_generation = 0
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("1240x780")
        self.root.minsize(1020, 660)
        self.root.configure(bg=self.colors["bg"])
        self._configure_window_icon()
        self._configure_style()
        self._make_menu()
        self.selected_id: str | None = None
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._schedule_profile_refresh())
        self._build_layout()
        self.root.protocol("WM_DELETE_WINDOW", self._request_close)
        self.root.bind("<Control-f>", lambda event: self._shortcut(self.search_entry.focus_set))
        self.root.bind("<Control-n>", lambda event: self._shortcut(lambda: ProfileDialog(self)))
        self.root.bind("<F5>", lambda event: self._shortcut(self.refresh_profiles))
        self.root.bind("<MouseWheel>", self._scroll_detail)
        self.root.after_idle(self._configure_title_bar)
        self.refresh_profiles()
        self.root.after(900, self._watch_processes)
        self.root.after(1800, self._watch_system_theme)
        self.root.after(120, self._drain_background_results)
        self.storage.log("application.opened", details=APP_VERSION)

    def _shortcut(self, action: Any) -> str:
        if not self._has_open_dialog() and not self._closing:
            action()
        return "break"

    def _request_close(self) -> None:
        self._closing = True
        self._clear_copied_password()
        if self._background_operations:
            self.set_status("Завершаю текущие операции… Не отключайте накопитель.")
            return
        self._executor.shutdown(wait=False)
        self.root.destroy()

    def _is_profile_active(self, profile_id: str) -> bool:
        process = self.running.get(profile_id)
        return profile_id in self._active_profiles or (process is not None and process.poll() is None)

    def _scroll_detail(self, event: tk.Event[Any]) -> None:
        widget = event.widget
        while widget is not None:
            if widget == getattr(self, "detail_canvas", None):
                self.detail_canvas.yview_scroll(-int(event.delta / 120), "units")
                return
            widget = getattr(widget, "master", None)

    def _configure_window_icon(self) -> None:
        icon = app_resource("assets/nevision.ico")
        if icon.is_file():
            try:
                self.root.iconbitmap(default=str(icon))
            except tk.TclError:
                # A missing icon is purely cosmetic; startup must not fail on a
                # restricted desktop or an interpreter without ICO support.
                pass

    def _configure_title_bar(self, window: tk.Misc | None = None) -> None:
        """Keep root and dialog native title bars aligned with the active palette."""

        if os.name != "nt":
            return
        try:
            target = window or self.root
            user32 = ctypes.windll.user32
            get_parent = user32.GetParent
            get_parent.argtypes = (ctypes.c_void_p,)
            get_parent.restype = ctypes.c_void_p
            dwm_set_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
            dwm_set_attribute.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint)
            dwm_set_attribute.restype = ctypes.c_long
            widget_handle = int(target.winfo_id())
            hwnd = get_parent(widget_handle) or widget_handle
            enabled = ctypes.c_int(1 if self.active_theme == THEME_DARK else 0)
            # Attribute 20 is supported by current Windows 10/11; 19 retains
            # compatibility with older builds.  Failure is cosmetic only.
            for attribute in (20, 19):
                result = dwm_set_attribute(hwnd, attribute, ctypes.byref(enabled), ctypes.sizeof(enabled))
                if result == 0:
                    break
        except (AttributeError, ctypes.ArgumentError, OSError, tk.TclError):
            pass

    def _has_open_dialog(self) -> bool:
        return any(isinstance(widget, tk.Toplevel) and widget.winfo_exists() for widget in self.root.winfo_children())

    def _rebuild_shell(self) -> None:
        """Redraw every palette-dependent Canvas while retaining user context."""

        selected_id = self.selected_id
        focus = self.root.focus_get()
        focused_search = focus is getattr(self, "search_entry", None)
        focused_tree = focus is getattr(self, "profile_tree", None)
        search_cursor = self.search_entry.index("insert") if focused_search else 0
        scroll = self.detail_canvas.yview()[0] if hasattr(self, "detail_canvas") else 0.0
        for widget in self._shell_widgets:
            if widget.winfo_exists():
                widget.destroy()
        self.root.configure(bg=self.colors["bg"])
        self._configure_style()
        self._make_menu()
        self._build_layout()
        self.refresh_profiles(select_id=selected_id)
        if focused_search:
            self.search_entry.focus_set()
            self.search_entry.icursor(min(search_cursor, len(self.search_var.get())))
        elif focused_tree:
            self.profile_tree.focus_set()
        if scroll:
            self.root.after_idle(lambda position=scroll: self.detail_canvas.yview_moveto(position))

    def _apply_theme(self, theme: str) -> None:
        self.active_theme = theme
        self.colors = palette_for_theme(theme)
        self._configure_title_bar()
        self._rebuild_shell()

    def set_theme_preference(self, preference: str) -> None:
        """Persist a user override and immediately redraw when it changes output."""

        self.theme_preference = normalize_theme_preference(preference)
        self.storage.set_setting(THEME_SETTING_KEY, self.theme_preference)
        resolved = resolve_theme(self.theme_preference)
        if resolved != self.active_theme:
            self._apply_theme(resolved)

    def _watch_system_theme(self) -> None:
        """Follow Windows without interrupting a form that the user is editing."""

        if self.theme_preference == THEME_SYSTEM and not self._has_open_dialog():
            resolved = resolve_theme(THEME_SYSTEM)
            if resolved != self.active_theme:
                self._apply_theme(resolved)
        self.root.after(1800, self._watch_system_theme)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Panel.TFrame", background=self.colors["panel"])
        style.configure("Sidebar.TFrame", background=self.colors["sidebar"])
        style.configure("Title.TLabel", background=self.colors["panel"], foreground=self.colors["text"], font=("Segoe UI", 20, "bold"))
        style.configure("DialogTitle.TLabel", background=self.colors["panel"], foreground=self.colors["text"], font=("Segoe UI", 17, "bold"))
        style.configure("Subtitle.TLabel", background=self.colors["panel"], foreground=self.colors["muted"], font=("Segoe UI", 9))
        style.configure("Label.TLabel", background=self.colors["panel"], foreground=self.colors["text"], font=("Segoe UI", 9, "bold"))
        style.configure("Muted.TLabel", background=self.colors["panel"], foreground=self.colors["muted"], font=("Segoe UI", 9))
        style.configure("Hint.TLabel", background=self.colors["panel"], foreground=self.colors["muted"], font=("Segoe UI", 9))
        style.configure("Status.TLabel", background=self.colors["header"], foreground=self.colors["muted"], font=("Consolas", 8))
        style.configure("Accent.TButton", background=self.colors["accent"], foreground=self.colors["ink"], borderwidth=0, padding=(12, 8), font=("Segoe UI", 9, "bold"))
        style.map("Accent.TButton", background=[("active", self.colors["accent_hover"])])
        style.configure("Ghost.TButton", background=self.colors["panel_2"], foreground=self.colors["text"], borderwidth=0, padding=(10, 7), font=("Segoe UI", 9))
        style.map("Ghost.TButton", background=[("active", self.colors["panel_hover"])])
        style.configure("Danger.TButton", background=self.colors["danger_surface"], foreground=self.colors["danger"], borderwidth=0, padding=(10, 7), font=("Segoe UI", 9, "bold"))
        style.map("Danger.TButton", background=[("active", self.colors["danger_hover"])])
        style.configure("Input.TEntry", fieldbackground=self.colors["input"], foreground=self.colors["text"], insertcolor=self.colors["text"], bordercolor=self.colors["line"], lightcolor=self.colors["line"], darkcolor=self.colors["line"], padding=9)
        style.map("Input.TEntry", fieldbackground=[("focus", self.colors["input"])], foreground=[("focus", self.colors["text"])])
        style.configure("Input.TCombobox", fieldbackground=self.colors["input"], background=self.colors["input"], foreground=self.colors["text"], arrowcolor=self.colors["violet_soft"], bordercolor=self.colors["line"], padding=7)
        style.map("Input.TCombobox", fieldbackground=[("readonly", self.colors["input"])], foreground=[("readonly", self.colors["text"])], selectbackground=[("readonly", self.colors["selection"])], selectforeground=[("readonly", self.colors["text"])])
        style.configure("Profiles.Treeview", background=self.colors["sidebar"], fieldbackground=self.colors["sidebar"], foreground=self.colors["text"], rowheight=42, borderwidth=0, relief="flat", focuscolor=self.colors["sidebar"], bordercolor=self.colors["sidebar"], lightcolor=self.colors["sidebar"], darkcolor=self.colors["sidebar"], font=("Segoe UI", 9))
        style.map("Profiles.Treeview", background=[("selected", self.colors["selection"])], foreground=[("selected", self.colors["text"])], focuscolor=[("focus", self.colors["sidebar"])])
        style.configure("Profiles.Treeview.Heading", background=self.colors["sidebar"], foreground=self.colors["muted_dim"], relief="flat", font=("Segoe UI", 8, "bold"))
        style.configure("History.Treeview", background=self.colors["input"], fieldbackground=self.colors["input"], foreground=self.colors["text"], rowheight=30, borderwidth=0, font=("Segoe UI", 9))
        style.map("History.Treeview", background=[("selected", self.colors["selection"])], foreground=[("selected", self.colors["text"])])
        style.configure("History.Treeview.Heading", background=self.colors["panel_2"], foreground=self.colors["muted"], relief="flat", font=("Segoe UI", 8, "bold"))
        style.configure("NV.Vertical.TScrollbar", background=self.colors["panel_hover"], troughcolor=self.colors["sidebar"], bordercolor=self.colors["sidebar"], arrowcolor=self.colors["muted"])
        style.configure("TSeparator", background=self.colors["line"])

    def _make_menu(self) -> None:
        menu_options = {
            "tearoff": False,
            "bg": self.colors["menu_bg"],
            "fg": self.colors["menu_text"],
            "activebackground": self.colors["menu_active"],
            "activeforeground": self.colors["menu_active_text"],
        }
        menu = tk.Menu(self.root, **menu_options)
        file_menu = tk.Menu(menu, **menu_options)
        file_menu.add_command(label="Новый профиль", command=lambda: ProfileDialog(self))
        file_menu.add_command(label="Импортировать настройки профиля…", command=self.import_profile_template)
        file_menu.add_command(label="Импортировать backup…", command=self.restore_backup)
        file_menu.add_command(label="Открыть папку резервных копий", command=self.open_backup_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self._request_close)
        menu.add_cascade(label="Файл", menu=file_menu)
        profile_menu = tk.Menu(menu, **menu_options)
        profile_menu.add_command(label="Запустить", command=self.launch_selected)
        profile_menu.add_command(label="Создать чистую копию", command=self.clone_selected)
        profile_menu.add_command(label="Экспортировать настройки профиля…", command=self.export_selected_template)
        profile_menu.add_command(label="Создать backup", command=self.backup_selected)
        profile_menu.add_command(label="Проверить профиль", command=self.health_selected)
        profile_menu.add_command(label="Папка профиля", command=self.open_profile_folder)
        profile_menu.add_command(label="Расширения", command=self.open_extensions)
        menu.add_cascade(label="Профиль", menu=profile_menu)
        vault_menu = tk.Menu(menu, **menu_options)
        vault_menu.add_command(label="Открыть Proxy vault", command=self.open_proxy_vault)
        vault_menu.add_command(label="Добавить proxy", command=lambda: ProxyDialog(self))
        menu.add_cascade(label="Vault", menu=vault_menu)
        help_menu = tk.Menu(menu, **menu_options)
        help_menu.add_command(label="Как пользоваться", command=self.show_quick_guide)
        help_menu.add_command(label="История изменений", command=self.open_changelog)
        help_menu.add_command(label="О продукте", command=self.show_about)
        menu.add_cascade(label="Помощь", menu=help_menu)
        self.root.config(menu=menu)

    def _build_layout(self) -> None:
        header = tk.Frame(self.root, bg=self.colors["header"], height=82, highlightthickness=1, highlightbackground=self.colors["line"])
        header.pack(fill="x")
        header.pack_propagate(False)
        BrandMark(header, 42, self.colors["header"], self.colors).pack(side="left", padx=(24, 12), pady=19)
        brand_copy = tk.Frame(header, bg=self.colors["header"])
        brand_copy.pack(side="left", fill="y", pady=15)
        tk.Label(brand_copy, text=APP_NAME, bg=self.colors["header"], fg=self.colors["text"], font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(brand_copy, text="Локальные профили браузера · portable preview", bg=self.colors["header"], fg=self.colors["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))
        IconButton(header, "Настройки", "settings", lambda: SettingsDialog(self), self.colors, self.colors["header"], width=122,
                   tooltip="Тема, путь к браузеру и расположение portable-данных.").pack(side="right", padx=(8, 24), pady=22)
        IconButton(header, "Журнал", "history", lambda: HistoryDialog(self), self.colors, self.colors["header"], width=105,
                   tooltip="Локальная история действий менеджера профилей.").pack(side="right", pady=22)
        IconButton(header, "Изменения", "history", self.open_changelog, self.colors, self.colors["header"], width=128,
                   tooltip="Открыть историю версий этого выпуска.").pack(side="right", padx=(0, 8), pady=22)
        local_chip = tk.Frame(header, bg=self.colors["lime_surface"], padx=10, pady=6)
        local_chip.pack(side="right", padx=(0, 12), pady=23)
        tk.Label(local_chip, text="LOCAL", bg=self.colors["lime_surface"], fg=self.colors["lime"], font=("Segoe UI", 8, "bold")).pack()

        workspace = tk.Frame(self.root, bg=self.colors["bg"])
        workspace.pack(fill="both", expand=True)
        sidebar = tk.Frame(workspace, bg=self.colors["sidebar"], width=270, highlightthickness=1, highlightbackground=self.colors["line"])
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        sidebar_inner = tk.Frame(sidebar, bg=self.colors["sidebar"])
        sidebar_inner.pack(fill="both", expand=True, padx=16, pady=18)
        IconButton(sidebar_inner, "Новый профиль", "add", lambda: ProfileDialog(self), self.colors, self.colors["sidebar"], kind="primary", width=238, height=42,
                   tooltip="Создать отдельный каталог браузера с собственной историей и cookies.").pack(fill="x")
        tools = tk.Frame(sidebar_inner, bg=self.colors["sidebar"])
        tools.pack(fill="x", pady=(8, 22))
        IconButton(tools, "Vault", "vault", self.open_proxy_vault, self.colors, self.colors["sidebar"], width=112,
                   tooltip="Локальное хранилище proxy; пароли защищены Windows DPAPI.").pack(side="left")
        IconButton(tools, "Импорт", "backup", self.restore_backup, self.colors, self.colors["sidebar"], width=118,
                   tooltip="Восстановить профиль из ранее созданного backup ZIP.").pack(side="right")

        list_heading = tk.Frame(sidebar_inner, bg=self.colors["sidebar"])
        list_heading.pack(fill="x", pady=(0, 8))
        VectorIcon(list_heading, "profiles", 17, self.colors["violet_soft"], self.colors["sidebar"]).pack(side="left")
        tk.Label(list_heading, text="ПРОФИЛИ", bg=self.colors["sidebar"], fg=self.colors["muted"], font=("Segoe UI", 8, "bold")).pack(side="left", padx=(7, 0))
        self.profile_count_label = tk.Label(list_heading, text="0", bg=self.colors["panel_2"], fg=self.colors["violet_soft"], font=("Consolas", 8, "bold"), padx=7, pady=2)
        self.profile_count_label.pack(side="right")

        search_box = tk.Frame(sidebar_inner, bg=self.colors["input"], highlightthickness=1, highlightbackground=self.colors["line"])
        search_box.pack(fill="x", pady=(0, 12))
        VectorIcon(search_box, "search", 17, self.colors["muted"], self.colors["input"]).pack(side="left", padx=(10, 6), pady=9)
        search = tk.Entry(search_box, textvariable=self.search_var, bg=self.colors["input"], fg=self.colors["text"], insertbackground=self.colors["text"], relief="flat", highlightthickness=0, font=("Segoe UI", 9))
        search.pack(side="left", fill="x", expand=True, pady=8, padx=(0, 7))
        self.search_entry = search
        HoverTip(search, "Поиск по названию, группе и тегам. Ctrl+F — перейти к поиску; Escape — очистить.", self.colors)
        search.bind("<Escape>", lambda event: self.search_var.set(""))

        tree_wrap = tk.Frame(sidebar_inner, bg=self.colors["sidebar"])
        tree_wrap.pack(fill="both", expand=True)
        self.profile_tree = ttk.Treeview(tree_wrap, columns=("name", "group", "status"), show="headings", style="Profiles.Treeview", selectmode="browse")
        self.profile_tree.heading("name", text="ПРОФИЛЬ")
        self.profile_tree.heading("group", text="ГРУППА")
        self.profile_tree.heading("status", text="СТАТУС")
        self.profile_tree.column("name", width=112, stretch=True)
        self.profile_tree.column("group", width=68, stretch=True)
        self.profile_tree.column("status", width=64, stretch=False)
        self.profile_tree.tag_configure("running", foreground=self.colors["lime"])
        self.profile_tree.bind("<<TreeviewSelect>>", self._on_profile_select)
        self.profile_tree.bind("<Return>", lambda event: self._shortcut(self.launch_selected))
        scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.profile_tree.yview, style="NV.Vertical.TScrollbar")
        self.profile_tree.configure(yscrollcommand=scroll.set)
        HoverTip(self.profile_tree, "Выберите профиль: справа появятся запуск, резервная копия и другие действия. Enter — запуск.", self.colors)
        self.profile_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        footer = tk.Frame(sidebar_inner, bg=self.colors["sidebar"])
        footer.pack(fill="x", pady=(14, 0))
        local_dot = tk.Canvas(footer, width=10, height=10, bg=self.colors["sidebar"], highlightthickness=0, borderwidth=0)
        local_dot.create_oval(2, 2, 8, 8, fill=self.colors["lime"], outline=self.colors["lime_soft"])
        local_dot.pack(side="left", pady=(2, 0))
        footer_copy = tk.Frame(footer, bg=self.colors["sidebar"])
        footer_copy.pack(side="left", padx=(5, 0), fill="x", expand=True)
        tk.Label(footer_copy, text="Данные хранятся локально", bg=self.colors["sidebar"], fg=self.colors["muted"], font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(footer_copy, text="Data рядом с приложением", bg=self.colors["sidebar"], fg=self.colors["muted_dim"], font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))

        self.detail = tk.Frame(workspace, bg=self.colors["panel"])
        self.detail.pack(side="left", fill="both", expand=True, padx=(1, 0))
        self._build_empty_detail()

        status = tk.Frame(self.root, bg=self.colors["header"], height=34, highlightthickness=1, highlightbackground=self.colors["line"])
        status.pack(fill="x")
        status.pack_propagate(False)
        self.status_label = tk.Label(status, text="Готово", bg=self.colors["header"], fg=self.colors["muted"], font=("Consolas", 8))
        self.status_label.pack(side="left", padx=24, pady=8)
        tk.Label(status, text=f"{APP_VERSION}  ·  Windows DPAPI vault  ·  без cloud sync", bg=self.colors["header"], fg=self.colors["muted_dim"], font=("Consolas", 8)).pack(side="right", padx=24, pady=8)
        self._shell_widgets = [header, workspace, status]

    def _clear_detail(self) -> None:
        for child in self.detail.winfo_children():
            child.destroy()

    def _build_empty_detail(self) -> None:
        self._clear_detail()
        bundled = self.launcher.bundled_browser() is not None
        browser_hint = "Во встроенном Chromium; установленный Chrome не нужен." if bundled else "Для запуска нужен установленный Chrome или Edge."
        empty = tk.Frame(self.detail, bg=self.colors["panel"])
        empty.pack(expand=True)
        illustration = tk.Canvas(empty, width=86, height=86, bg=self.colors["panel"], highlightthickness=0, borderwidth=0)
        draw_round_rect(illustration, 5, 5, 81, 81, 20, self.colors["card"])
        draw_round_rect(illustration, 13, 13, 73, 73, 16, self.colors["illustration_inner"])
        draw_vector_icon(illustration, "profiles", 25, 25, 36, self.colors["violet_soft"])
        illustration.pack(pady=(0, 19))
        tk.Label(empty, text="Ваше рабочее пространство", bg=self.colors["panel"], fg=self.colors["text"], font=("Segoe UI", 21, "bold")).pack()
        tk.Label(empty, text=f"Создайте локальный профиль или выберите существующий слева.\nКаждый профиль хранит свои данные отдельно. {browser_hint}", bg=self.colors["panel"], fg=self.colors["muted"], justify="center", font=("Segoe UI", 10), wraplength=500).pack(pady=(8, 20))
        IconButton(empty, "Создать профиль", "add", lambda: ProfileDialog(self), self.colors, self.colors["panel"], kind="primary", width=180, height=42,
                   tooltip="Новый профиль создаётся локально и запускается во встроенном Chromium.").pack()
        privacy_note = ("Данные локально · без облака · уменьшена детализация CPU/RAM"
                        if self.launcher.has_native_privacy_baseline() else
                        "Данные локально · без синхронизации · приложение не меняет fingerprint")
        tk.Label(empty, text=privacy_note, bg=self.colors["panel"], fg=self.colors["muted_dim"], font=("Segoe UI", 8)).pack(pady=(18, 0))
        tk.Label(empty, text=f"Ctrl+N — новый профиль   ·   Ctrl+F — поиск   ·   Enter — запуск\n{browser_hint}", bg=self.colors["panel"], fg=self.colors["muted"], font=("Segoe UI", 9), justify="center").pack(pady=(12, 0))
        IconButton(empty, "Сайт и обновления", "launch", self.open_release_site, self.colors, self.colors["panel"], width=200,
                   tooltip="Открыть сайт с последней portable-версией и инструкцией обновления.").pack(pady=(12, 0))

    def _metric_card(self, parent: tk.Misc, icon: str, title: str, value: str, accent: str) -> tk.Frame:
        card = tk.Frame(parent, bg=self.colors["card"], highlightthickness=1, highlightbackground=self.colors["line"], padx=15, pady=14)
        heading = tk.Frame(card, bg=self.colors["card"])
        heading.pack(fill="x")
        VectorIcon(heading, icon, 17, accent, self.colors["card"]).pack(side="left")
        tk.Label(heading, text=title.upper(), bg=self.colors["card"], fg=self.colors["muted"], font=("Segoe UI", 8, "bold")).pack(side="left", padx=(7, 0))
        tk.Label(card, text=value, bg=self.colors["card"], fg=self.colors["text"], anchor="w", justify="left", wraplength=185, font=("Segoe UI", 10, "bold")).pack(fill="x", pady=(13, 0))
        return card

    def _build_detail(self, profile: dict[str, Any]) -> None:
        self._clear_detail()
        canvas = tk.Canvas(self.detail, bg=self.colors["panel"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.detail, orient="vertical", command=canvas.yview, style="NV.Vertical.TScrollbar")
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        self.detail_canvas = canvas
        body = tk.Frame(canvas, bg=self.colors["panel"])
        body_window = canvas.create_window(24, 22, window=body, anchor="nw")
        def resize_detail(_event: Any = None) -> None:
            canvas.itemconfigure(body_window, width=max(1, canvas.winfo_width() - 48), height=max(body.winfo_reqheight(), canvas.winfo_height() - 44))
            canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.bind("<Configure>", resize_detail)
        body.bind("<Configure>", resize_detail)
        top = tk.Frame(body, bg=self.colors["panel"])
        top.pack(fill="x")
        ProfileBadge(top, profile["name"], 48, self.colors["panel"], self.colors).pack(side="left")
        heading = tk.Frame(top, bg=self.colors["panel"])
        heading.pack(side="left", fill="x", expand=True, padx=(13, 0))
        tk.Label(heading, text=profile["name"], bg=self.colors["panel"], fg=self.colors["text"], font=("Segoe UI", 20, "bold"), wraplength=380, justify="left").pack(anchor="w")
        identity = profile.get("fingerprint", ordinary_identity())
        unsupported = identity["mode"] != "ordinary"
        family = profile.get("browser_family") or ""
        browser_label = {"chromium": "Встроенный Chromium", "chrome": "Google Chrome", "edge": "Microsoft Edge"}.get(family, "Браузер ещё не закреплён")
        identity_label = ("Старый режим отключён · данные сохранены · создайте чистую копию" if unsupported else
                          f"{browser_label} · настройки fingerprint не изменяются приложением")
        sub = "  ·  ".join(part for part in [identity_label, profile.get("group_name"), profile.get("tags")] if part)
        tk.Label(heading, text=sub, bg=self.colors["panel"], fg=self.colors["muted"],
                 font=("Segoe UI", 10), wraplength=360, justify="left").pack(anchor="w", pady=(3, 0))
        is_running = self._is_profile_active(str(profile["id"]))
        chip_bg = self.colors["lime_surface"] if is_running else self.colors["panel_2"]
        chip_fg = self.colors["lime"] if is_running else self.colors["muted"]
        state = "ОТКРЫТ" if is_running else ("ПРОВЕРЬТЕ ДОСТУП" if str(profile["id"]) in self._unknown_profiles else "СОЗДАЙТЕ КОПИЮ" if unsupported else "ГОТОВ")
        status_chip = tk.Frame(top, bg=chip_bg, padx=10, pady=6)
        status_chip.pack(side="right", padx=(10, 8), pady=5)
        tk.Label(status_chip, text=state, bg=chip_bg, fg=chip_fg, font=("Segoe UI", 8, "bold")).pack()
        IconButton(top, "Изменить", "edit", self.edit_selected, self.colors, self.colors["panel"], width=112,
                   tooltip="Изменить название, группу, proxy или заметку профиля.").pack(side="right", pady=5)

        action_row = tk.Frame(body, bg=self.colors["card"], highlightthickness=1, highlightbackground=self.colors["line"], padx=10, pady=10)
        action_row.pack(fill="x", pady=(27, 22))
        actions = (
            ("Запустить", "launch", self.launch_selected, "Открыть этот профиль в закреплённом браузере."),
            ("Резервная копия", "backup", self.backup_selected, "Создать ZIP с данными профиля. В нём могут быть cookies и сессии — храните его приватно."),
            ("Чистая копия", "clone", self.clone_selected, "Создать новый профиль с теми же настройками, но без cookies, истории и сессий."),
            ("Проверить", "health", self.health_selected, "Проверить состояние локальных файлов и привязку браузера."),
            ("Диагностика", "health", self.open_privacy_diagnostics, "Открыть проверку IP и видимых сайту параметров именно в этом профиле. Наш сайт увидит ваш IP; DNS и WebRTC не проверяются."),
            ("Расширения", "profiles", self.open_extensions, "Открыть страницу расширений в браузере этого профиля."),
        )
        for index, (label, icon, command, hint) in enumerate(actions):
            IconButton(action_row, label, icon, command, self.colors, self.colors["card"], kind="primary" if index == 0 else "ghost", width=190, height=38,
                       tooltip=hint).grid(row=index // 3, column=index % 3, sticky="ew", padx=4, pady=3)
        for column in range(3):
            action_row.columnconfigure(column, weight=1)

        info = tk.Frame(body, bg=self.colors["panel"])
        info.pack(fill="x")
        columns = [
            ("proxy", "Proxy", profile.get("proxy_name") or "Не назначен", self.colors["cyan"] if profile.get("proxy_name") else self.colors["amber"]),
            ("history", "Последний запуск", display_datetime(profile.get("last_launch_at")), self.colors["violet_soft"]),
            ("folder", "Каталог", profile["id"][:12] + "…", self.colors["muted"]),
        ]
        for index, (icon, label, value, accent) in enumerate(columns):
            card = self._metric_card(info, icon, label, value, accent)
            card.pack(side="left", fill="x", expand=True, padx=(0, 10 if index < len(columns) - 1 else 0))

        linked_profiles = (self.storage.count_profiles_for_proxy(str(profile["proxy_id"]))
                           if profile.get("proxy_id") else 0)
        route_note = tk.Frame(body, bg=self.colors["panel_2"], padx=12, pady=10)
        route_note.pack(fill="x", pady=(12, 0))
        note_accent = self.colors["amber"] if not profile.get("proxy_id") or linked_profiles > 1 else self.colors["cyan"]
        VectorIcon(route_note, "proxy", 17, note_accent, self.colors["panel_2"]).pack(side="left")
        tk.Label(route_note, text=profile_network_note(profile.get("proxy_id"), linked_profiles),
                 bg=self.colors["panel_2"], fg=self.colors["text"], font=("Segoe UI", 9),
                 wraplength=690, justify="left", anchor="w").pack(side="left", fill="x", expand=True, padx=(9, 0))

        lower = tk.Frame(body, bg=self.colors["panel"])
        lower.pack(fill="both", expand=True, pady=(20, 0))
        left = tk.Frame(lower, bg=self.colors["card"], highlightthickness=1, highlightbackground=self.colors["line"], padx=20, pady=19)
        left.pack(side="left", fill="both", expand=True)
        note_heading = tk.Frame(left, bg=self.colors["card"])
        note_heading.pack(fill="x")
        VectorIcon(note_heading, "history", 18, self.colors["violet_soft"], self.colors["card"]).pack(side="left")
        tk.Label(note_heading, text="ЗАМЕТКА", bg=self.colors["card"], fg=self.colors["muted"], font=("Segoe UI", 8, "bold")).pack(side="left", padx=(7, 0))
        notes = profile.get("notes") or "Заметка пока не добавлена."
        tk.Label(left, text=notes, bg=self.colors["card"], fg=self.colors["text"] if profile.get("notes") else self.colors["muted"], wraplength=470, justify="left", anchor="nw", font=("Segoe UI", 10)).pack(fill="both", expand=True, pady=(13, 0))
        IconButton(left, "История профиля", "history", lambda: HistoryDialog(self, profile["id"]), self.colors, self.colors["card"], width=160,
                   tooltip="Посмотреть локальную историю действий только этого профиля.").pack(anchor="w", pady=(19, 0))
        right = tk.Frame(lower, bg=self.colors["card"], width=255, height=220, highlightthickness=1, highlightbackground=self.colors["line"], padx=12, pady=12)
        right.pack(side="left", fill="y", padx=(14, 0))
        right.pack_propagate(False)
        operations_heading = tk.Frame(right, bg=self.colors["card"])
        operations_heading.pack(fill="x")
        VectorIcon(operations_heading, "health", 18, self.colors["cyan"], self.colors["card"]).pack(side="left")
        tk.Label(operations_heading, text="ОПЕРАЦИИ", bg=self.colors["card"], fg=self.colors["muted"], font=("Segoe UI", 8, "bold")).pack(side="left", padx=(7, 0))
        IconButton(right, "Проверить proxy", "proxy", self.test_selected_proxy, self.colors, self.colors["card"], width=224,
                   tooltip="Отправляет короткий протокольный запрос выбранному proxy. Без сохранённого пароля и запроса сайта.").pack(fill="x", pady=(10, 0))
        IconButton(right, "Скопировать пароль", "vault", self.copy_selected_proxy_password, self.colors, self.colors["card"], width=244,
                   tooltip="Скопировать сохранённый proxy-пароль на 30 секунд. Доступно только для текущего Windows-пользователя.").pack(fill="x", pady=(8, 0))
        IconButton(right, "Удалить профиль", "trash", self.delete_selected, self.colors, self.colors["card"], kind="danger", width=244,
                   tooltip="Переместить закрытый профиль в Data\\Deleted после подтверждения.").pack(fill="x", pady=(24, 0))

    def set_status(self, message: str) -> None:
        self.status_label.configure(text=message)

    def _schedule_profile_refresh(self) -> None:
        """Avoid rebuilding the full profile list on every key stroke."""

        if self._search_refresh_id is not None:
            with contextlib.suppress(tk.TclError):
                self.root.after_cancel(self._search_refresh_id)
        self._search_refresh_id = self.root.after(180, self._refresh_after_search)

    def _refresh_after_search(self) -> None:
        self._search_refresh_id = None
        self.refresh_profiles()

    def _run_in_background(self, key: str, operation: Any, on_success: Any, on_failure: Any | None = None) -> bool:
        """Run slow local I/O off the Tk thread and return results on the UI thread."""

        if self._closing or key in self._background_operations:
            return False
        if len(self._background_operations) >= 6:
            self.set_status("Все фоновые слоты заняты. Повторите действие после завершения операции.")
            return False
        self._background_operations.add(key)

        def worker() -> None:
            try:
                result = operation()
            except Exception as exc:  # Converted into a UI-safe result on the main thread.
                self._background_results.put((key, on_success, on_failure, None, exc))
            else:
                self._background_results.put((key, on_success, on_failure, result, None))

        self._executor.submit(worker)
        return True

    def _drain_background_results(self) -> None:
        try:
            while True:
                key, on_success, on_failure, result, error = self._background_results.get_nowait()
                self._background_operations.discard(key)
                if self._closing:
                    if error is not None:
                        self._closing = False
                        messagebox.showerror(APP_NAME, str(error), parent=self.root)
                    continue
                if error is None:
                    on_success(result)
                elif on_failure is not None:
                    on_failure(error)
                else:
                    messagebox.showerror(APP_NAME, str(error), parent=self.root)
        except queue.Empty:
            pass
        finally:
            if self._closing and not self._background_operations:
                self._request_close()
            elif self.root.winfo_exists():
                self.root.after(120, self._drain_background_results)

    def refresh_profiles(self, select_id: str | None = None) -> None:
        current = select_id or self.selected_id
        try:
            rows = self.storage.list_profiles(self.search_var.get())
        except NeVisionError as exc:
            self.set_status(str(exc))
            return
        visible_ids: set[str] = set()
        existing_ids = set(self.profile_tree.get_children())
        for index, profile in enumerate(rows):
            profile_id = str(profile["id"])
            visible_ids.add(profile_id)
            running = self._is_profile_active(profile_id)
            mode = profile.get("fingerprint", ordinary_identity())["mode"]
            unsupported = mode != "ordinary"
            status = "ОТКРЫТ" if running else ("ДОСТУП?" if profile_id in self._unknown_profiles else "СОЗДАЙТЕ КОПИЮ" if unsupported else "ГОТОВ")
            tags = ("running",) if running else ()
            values = (profile["name"], profile.get("group_name") or "—", status)
            if profile_id in existing_ids:
                if tuple(self.profile_tree.item(profile_id, "values")) != values:
                    self.profile_tree.item(profile_id, values=values, tags=tags)
                self.profile_tree.move(profile_id, "", index)
            else:
                self.profile_tree.insert("", index, iid=profile_id, values=values, tags=tags)
        for item in existing_ids - visible_ids:
            self.profile_tree.delete(item)
        if hasattr(self, "profile_count_label"):
            self.profile_count_label.configure(text=str(len(rows)))
        if current and current in visible_ids:
            self.profile_tree.selection_set(current)
            self.profile_tree.focus(current)
            self.selected_id = current
            profile = self.storage.get_profile(current)
            if profile:
                self._build_detail(profile)
            return
        self.selected_id = None
        self._build_empty_detail()

    def _on_profile_select(self, _event: tk.Event[Any]) -> None:
        selected = self.profile_tree.selection()
        if not selected:
            return
        self.selected_id = selected[0]
        profile = self.storage.get_profile(self.selected_id)
        if profile:
            self._build_detail(profile)

    def selected_profile(self) -> dict[str, Any] | None:
        if self._closing:
            return None
        if not self.selected_id:
            messagebox.showinfo(APP_NAME, "Сначала выберите профиль.", parent=self.root)
            return None
        profile = self.storage.get_profile(self.selected_id)
        if not profile:
            messagebox.showerror(APP_NAME, "Профиль больше не существует.", parent=self.root)
            self.refresh_profiles()
        return profile

    def _backup_in_progress(self, profile_id: str) -> bool:
        return any(f"{prefix}:{profile_id}" in self._background_operations for prefix in ("backup", "launch", "delete"))

    def _allow_profile_mutation(self, profile: dict[str, Any]) -> bool:
        if self._backup_in_progress(str(profile["id"])):
            messagebox.showinfo(
                APP_NAME,
                "Для этого профиля выполняется операция. Дождитесь завершения, прежде чем запускать, изменять или удалять профиль.",
                parent=self.root,
            )
            return False
        return True

    def edit_selected(self) -> None:
        profile = self.selected_profile()
        if not profile or not self._allow_profile_mutation(profile):
            return
        ProfileDialog(self, profile)

    def launch_selected(self, extensions: bool = False, diagnostics: bool = False) -> None:
        profile = self.selected_profile()
        if not profile:
            return
        if not self._allow_profile_mutation(profile):
            return
        if self._is_profile_active(str(profile["id"])):
            if diagnostics:
                self.root.clipboard_clear()
                self.root.clipboard_append(PRIVACY_CHECK_URL)
                messagebox.showinfo(APP_NAME, "Профиль уже открыт. Ссылка проверки скопирована: вставьте её в адресную строку именно этого профиля. Наш сайт увидит IP при открытии страницы.", parent=self.root)
                return
            messagebox.showinfo(APP_NAME, "Профиль уже открыт. Расширения доступны через меню браузера → Расширения. Для нового запуска закройте все окна этого профиля.", parent=self.root)
            return
        if profile["fingerprint"]["mode"] == "ordinary":
            try:
                self.launcher.resolve_browser()
            except NeVisionError as exc:
                messagebox.showinfo(APP_NAME, str(exc), parent=self.root)
                if not (self.paths.root / "Engine" / "Chromium").exists():
                    SettingsDialog(self)
                return
        elif profile["fingerprint"]["mode"] != "ordinary":
            messagebox.showerror(
                APP_NAME,
                "Этот профиль использует отключённый экспериментальный режим и не будет запущен. "
                "Исходные данные сохранены. Нажмите «Чистая копия»: настройки будут перенесены, "
                "а cookies, история и сессии останутся только в исходном профиле.",
                parent=self.root,
            )
            return
        if profile.get("proxy_id"):
            proxy = self.storage.get_proxy(str(profile["proxy_id"]))
            if proxy and proxy["scheme"] in {"http", "https"} and (proxy.get("username") or proxy.get("password_protected")):
                messagebox.showinfo(APP_NAME, "HTTP(S) proxy: браузер запросит логин и пароль самостоятельно. Сохранённый пароль можно скопировать кнопкой в профиле. NeAntik не передаёт пароль через командную строку.", parent=self.root)
        self.set_status(f"Запускаю: {profile['name']}…")

        def completed(spawned: subprocess.Popen[bytes]) -> None:
            self.running[str(profile["id"])] = spawned
            self.set_status(getattr(spawned, "nevision_warning", f"Запущен: {profile['name']}"))
            self.refresh_profiles(select_id=str(profile["id"]))

        def failed(error: Exception) -> None:
            self.set_status("Запуск не выполнен")
            messagebox.showerror(APP_NAME, str(error), parent=self.root)

        self._run_in_background(f"launch:{profile['id']}", lambda: self.launcher.launch(profile, extensions=extensions, diagnostics=diagnostics), completed, failed)

    def open_extensions(self) -> None:
        self.launch_selected(extensions=True)

    def open_privacy_diagnostics(self) -> None:
        if not self.selected_profile():
            return
        confirmed = messagebox.askyesno(
            APP_NAME,
            PRIVACY_DIAGNOSTICS_CONSENT,
            parent=self.root,
            default=messagebox.NO,
        )
        if not confirmed:
            return
        self.launch_selected(diagnostics=True)

    def clone_selected(self) -> None:
        profile = self.selected_profile()
        if not profile:
            return
        copy_name = f"Копия · {profile['name']}"
        try:
            new_id = self.storage.save_profile(
                {
                    "name": copy_name,
                    "group_name": profile.get("group_name", ""),
                    "tags": profile.get("tags", ""),
                    "notes": f"Создано как чистая копия профиля «{profile['name']}».\n\n{profile.get('notes', '')}".strip(),
                    "proxy_id": profile.get("proxy_id") or None,
                    "fingerprint": ordinary_identity(),
                }
            )
            self.storage.log("profile.settings_cloned", new_id, f"source={profile['id']}")
        except NeVisionError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self.root)
            return
        self.set_status("Создана чистая копия: без cookies, истории и сессий")
        self.refresh_profiles(select_id=new_id)

    def export_selected_template(self) -> None:
        if not self.selected_id:
            messagebox.showinfo(APP_NAME, "Сначала выберите профиль для экспорта настроек.", parent=self.root)
            return
        profile = self.selected_profile()
        if not profile:
            return
        if not messagebox.askyesno(
            APP_NAME,
            "Экспорт настроек создаёт небольшой незашифрованный JSON: название, группа, теги и режим браузера. "
            "В них может быть личная информация, введённая вами. Cookies, история, сессии, заметки и proxy не переносятся. "
            "На другом ПК настройте proxy заново.\n\nЭкспортировать?",
            parent=self.root,
        ):
            return
        try:
            target = self.storage.export_profile_template(str(profile["id"]))
        except NeVisionError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self.root)
            return
        self.set_status(f"Настройки экспортированы: {target.name}")
        messagebox.showinfo(APP_NAME, f"Файл настроек создан:\n{target}\n\nНа другом ПК используйте «Файл → Импортировать настройки профиля». Данные сайтов и proxy не включены.", parent=self.root)

    def import_profile_template(self) -> None:
        source = filedialog.askopenfilename(
            parent=self.root,
            title="Выберите настройки профиля NeAntik",
            filetypes=[("Настройки профиля NeAntik", "*.neantik-profile.json"), ("JSON", "*.json")],
        )
        if not source:
            return
        if not messagebox.askyesno(
            APP_NAME,
            "Будет создан новый пустой профиль. Данные сайтов, cookies, история, сессии и proxy не переносятся; "
            "proxy и вход на сайты настройте заново. Исходный профиль и файл не изменятся.\n\nИмпортировать настройки?",
            parent=self.root,
        ):
            return
        try:
            new_id = self.storage.import_profile_template(Path(source))
        except NeVisionError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self.root)
            return
        self.set_status("Создан новый профиль без данных сайтов и proxy")
        self.refresh_profiles(select_id=new_id)

    def backup_selected(self) -> None:
        profile = self.selected_profile()
        if not profile:
            return
        if self._is_profile_active(str(profile["id"])):
            messagebox.showinfo(
                APP_NAME,
                "Закройте браузер этого профиля перед backup. Копирование работающего Chromium-профиля может создать неконсистентный архив.",
                parent=self.root,
            )
            return
        if not self._allow_profile_mutation(profile):
            return
        if not messagebox.askyesno(APP_NAME, "Backup — незашифрованный ZIP. Он может содержать cookies, историю и активные сессии сайтов. Храните его как пароль; не публикуйте и не отправляйте посторонним.\n\nСоздать backup?", parent=self.root, icon="warning"):
            return
        self.set_status("Создаю backup…")

        def completed(archive: Path) -> None:
            self.set_status(f"Backup создан: {archive.name}")
            messagebox.showinfo(APP_NAME, f"Backup создан:\n{archive}", parent=self.root)

        def failed(exc: Exception) -> None:
            self.set_status("Ошибка backup")
            messagebox.showerror(APP_NAME, str(exc), parent=self.root)

        if not self._run_in_background(f"backup:{profile['id']}", lambda: self.storage.backup_profile(str(profile["id"])), completed, failed):
            self.set_status("Backup этого профиля уже выполняется")

    def restore_backup(self) -> None:
        archive = filedialog.askopenfilename(parent=self.root, title="Выберите backup NeAntik", filetypes=[("Backup профиля", "*.zip"), ("Все файлы", "*.*")])
        if not archive:
            return
        if not messagebox.askyesno(
            APP_NAME,
            f"Backup может содержать незашифрованные данные сайтов. {PORTABILITY_WARNING}\n\nВосстановить профиль?",
            parent=self.root,
            icon="warning",
        ):
            return
        archive_path = Path(archive)
        self.set_status("Восстанавливаю backup…")

        def completed(new_id: str) -> None:
            self.set_status("Профиль восстановлен без proxy-секретов")
            self.refresh_profiles(select_id=new_id)

        def failed(exc: Exception) -> None:
            self.set_status("Ошибка восстановления backup")
            messagebox.showerror(APP_NAME, str(exc), parent=self.root)

        self._run_in_background(
            f"restore:{uuid.uuid4().hex}",
            lambda: self.storage.restore_profile(archive_path),
            completed,
            failed,
        )

    def open_proxy_vault(self) -> None:
        ProxyVaultDialog(self)

    def health_selected(self) -> None:
        profile = self.selected_profile()
        if not profile:
            return
        self.set_status("Проверяю профиль…")

        def completed(checks: list[tuple[str, str]]) -> None:
            text = "\n".join(f"{label}: {value}" for label, value in checks)
            try:
                self.storage.log("profile.health_checked", str(profile["id"]))
            except NeVisionError as exc:
                self.set_status(str(exc))
            messagebox.showinfo(f"Проверка · {profile['name']}", text, parent=self.root)
            self.set_status("Проверка профиля завершена")

        def failed(exc: Exception) -> None:
            self.set_status("Ошибка проверки профиля")
            messagebox.showerror(APP_NAME, str(exc), parent=self.root)

        self._run_in_background(f"health:{profile['id']}", lambda: self.storage.health_check(str(profile["id"])), completed, failed)

    def test_selected_proxy(self) -> None:
        profile = self.selected_profile()
        if not profile:
            return
        if not profile.get("proxy_id"):
            messagebox.showinfo(APP_NAME, "Для профиля не назначен proxy.", parent=self.root)
            return
        proxy = self.storage.get_proxy(str(profile["proxy_id"]))
        if not proxy:
            messagebox.showerror(APP_NAME, "Назначенный proxy не найден.", parent=self.root)
            return
        self.set_status("Проверяю ответ proxy без передачи пароля…")

        self._run_in_background(
            f"proxy-test:{profile['id']}",
            lambda: diagnose_proxy(proxy),
            lambda result: self._proxy_test_result(profile, proxy, result),
            lambda _exc: self._proxy_test_result(profile, proxy, (False, "Внутренняя ошибка диагностики proxy.")),
        )

    def _proxy_test_result(self, profile: dict[str, Any], proxy: dict[str, Any], result: tuple[bool, str]) -> None:
        success, message = result
        try:
            self.storage.log("proxy.protocol_check", str(profile["id"]), f"{proxy['name']}: {message}")
        except NeVisionError as exc:
            self.set_status(str(exc))
        self.set_status(message)
        dialog = messagebox.showinfo if success else messagebox.showwarning
        dialog(APP_NAME, f"{proxy['name']}\n{message}\n\nHTTP(S): отправляется OPTIONS *. SOCKS5: предлагается только режим без авторизации. Запрос адресуется выбранному proxy; сохранённые учётные данные и адрес сайта не отправляются. Имя proxy разрешает Windows. Ответ не доказывает поддержку CONNECT или успешное открытие сайта, внешний IP, DNS, WebRTC, UDP или анонимность.", parent=self.root)

    def copy_selected_proxy_password(self) -> None:
        profile = self.selected_profile()
        if not profile or not profile.get("proxy_id"):
            messagebox.showinfo(APP_NAME, "Для профиля не назначен proxy.", parent=self.root)
            return
        proxy = self.storage.get_proxy(str(profile["proxy_id"]))
        if not proxy or not proxy.get("password_protected"):
            messagebox.showinfo(APP_NAME, "У этого proxy нет сохранённого пароля.", parent=self.root)
            return
        try:
            password = SecretVault.decrypt(str(proxy["password_protected"]))
        except NeVisionError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self.root)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(password)
        self._clipboard_secret = password
        self._clipboard_generation += 1
        generation = self._clipboard_generation
        self.root.after(30_000, lambda value=password, token=generation: self._clear_copied_password(value, token))
        self.storage.log("proxy.password_copied", str(profile["id"]), proxy["name"])
        self.set_status("Пароль скопирован; очистка через 30 с. Историю/синхронизацию буфера Windows это не очищает.")

    def _clear_copied_password(self, expected: str | None = None, generation: int | None = None) -> None:
        if generation is not None and generation != self._clipboard_generation:
            return
        value = expected if expected is not None else self._clipboard_secret
        if value is None:
            return
        with contextlib.suppress(tk.TclError):
            if self.root.clipboard_get() == value:
                self.root.clipboard_clear()
        if self._clipboard_secret == value:
            self._clipboard_secret = None

    def open_profile_folder(self) -> None:
        profile = self.selected_profile()
        if not profile:
            return
        path = self.storage.profile_path(str(profile["id"]))
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(path))
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Не удалось открыть папку: {exc}", parent=self.root)

    def open_backup_folder(self) -> None:
        path = filesystem_path(self.storage.paths.backups)
        try:
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(str(path))
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Не удалось открыть папку резервных копий: {exc}", parent=self.root)

    def delete_selected(self) -> None:
        profile = self.selected_profile()
        if not profile:
            return
        if not self._allow_profile_mutation(profile):
            return
        if self._is_profile_active(str(profile["id"])):
            messagebox.showinfo(APP_NAME, "Сначала закройте запущенный браузер этого профиля. Это защитит данные и журнал действий.", parent=self.root)
            return
        confirmed = messagebox.askyesno(
            APP_NAME,
            f"Удалить профиль «{profile['name']}»?\n\nЕго данные будут перемещены в Data\\Deleted, а запись исчезнет из списка. Это не удалит внешний аккаунт на сайтах.",
            icon="warning",
            parent=self.root,
        )
        if not confirmed:
            return
        try:
            self.storage.delete_profile(str(profile["id"]))
        except (NeVisionError, OSError) as exc:
            messagebox.showerror(APP_NAME, f"Не удалось удалить профиль: {exc}", parent=self.root)
            return
        self.running.pop(str(profile["id"]), None)
        self.set_status(f"Профиль перемещён в Data\\Deleted: {profile['name']}")
        self.refresh_profiles()

    def _watch_processes(self) -> None:
        exited: list[tuple[str, int | None]] = []
        for profile_id, process in list(self.running.items()):
            status = process.poll()
            if status is not None:
                exited.append((profile_id, status))
                self.running.pop(profile_id, None)
        for profile_id, code in exited:
            try:
                self.storage.touch_profile_exit(profile_id, code)
                self.set_status(f"Процесс профиля завершился (код {code})")
            except NeVisionError as exc:
                self.set_status(str(exc))
        if exited:
            self.refresh_profiles(select_id=self.selected_id)
        def scan() -> tuple[set[str], set[str]]:
            active: set[str] = set()
            unknown: set[str] = set()
            for profile in self.storage.list_profiles():
                profile_id = str(profile["id"])
                try:
                    if os.name == "nt":
                        if self.storage._windows_chromium_lock_is_active(profile_id):
                            active.add(profile_id)
                    elif self.storage.active_profile_lock_markers(profile_id):
                        active.add(profile_id)
                except NeVisionError:
                    unknown.add(profile_id)
            return active, unknown

        def scanned(result: tuple[set[str], set[str]]) -> None:
            if result != (self._active_profiles, self._unknown_profiles):
                self._active_profiles, self._unknown_profiles = result
                self.refresh_profiles(select_id=self.selected_id)

        self._run_in_background("status-scan", scan, scanned, lambda error: self.set_status("Не удалось проверить состояние профилей: " + str(error)))
        self.root.after(3000, self._watch_processes)

    def open_release_site(self) -> None:
        try:
            os.startfile(SITE_URL + "/#download")
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Не удалось открыть сайт: {exc}", parent=self.root)

    def show_quick_guide(self) -> None:
        messagebox.showinfo(
            "Как пользоваться NeAntik Win",
            "1. Распакуйте весь ZIP в доступную для записи папку NTFS и запустите NeAntikWin.exe.\n"
            "2. Создайте профиль. Новый профиль откроется во встроенном Chromium со своими cookies и историей.\n"
            "3. Proxy добавьте через Vault и назначьте профилю. TCP-проверка не подтверждает внешний IP или отсутствие утечек.\n"
            "   Загрузки новых профилей встроенного Chromium находятся в папке Downloads профиля; откройте её через меню «Профиль → Папка профиля».\n"
            "4. Перед переносом или обновлением закройте браузер и сохраните всю папку Data. Backup ZIP содержит незашифрованные данные сайтов.\n"
            f"5. {PORTABILITY_WARNING}\n\n"
            "Наведите курсор на кнопку или выделите её клавишей Tab — появится подсказка.",
            parent=self.root,
        )

    def open_changelog(self) -> None:
        file = self.paths.root / "CHANGELOG.md"
        if file.exists():
            os.startfile(str(file))
        else:
            messagebox.showinfo(APP_NAME, "Changelog доступен в репозитории проекта.", parent=self.root)

    def show_about(self) -> None:
        scope = ("В этот portable-выпуск входит Chromium; установленный Chrome не требуется. В ядре уменьшена детализация CPU/RAM; анонимность не гарантируется."
                 if self.launcher.has_native_privacy_baseline() else
                 "В этот portable-выпуск входит Chromium; установленный Chrome не требуется. Приложение не задаёт fingerprint-переопределения."
                 if self.launcher.bundled_browser() else
                 "Этот portable-выпуск использует установленный Chrome или Edge. Приложение не задаёт fingerprint-переопределения.")
        messagebox.showinfo(
            APP_NAME,
            f"{APP_NAME} {APP_VERSION}\n\nЛокальные изолированные профили для Windows. {scope}\n\nВключает Windows DPAPI vault, proxy-настройки, backup/restore и журнал действий.",
            parent=self.root,
        )

    def run(self) -> None:
        self.root.mainloop()


def self_test() -> int:
    """Non-interactive core test used before packaging and after building the exe."""
    temp_root = Path(tempfile.mkdtemp(prefix="nevision-selftest-"))
    try:
        paths = AppPaths(temp_root)
        storage = Storage(paths)
        fixture_value = "self-test-value-✓"
        assert SecretVault.decrypt(SecretVault.encrypt(fixture_value)) == fixture_value
        proxy_id = storage.save_proxy({"name": "Self test", "scheme": "http", "host": "127.0.0.1", "port": 8080, "username": "demo", "password": fixture_value})
        profile_id = storage.save_profile({"name": "Self test profile", "group_name": "QA", "tags": "test", "notes": "ok", "proxy_id": proxy_id})
        profile_dir = storage.profile_path(profile_id)
        try:
            storage.profile_path("../outside-synthetic")
        except NeVisionError as exc:
            assert "идентификатор профиля" in str(exc)
        else:
            raise AssertionError("Profile path accepted a traversal ID")
        (profile_dir / "Default").mkdir(parents=True)
        (profile_dir / "Default" / "test.txt").write_text("hello", encoding="utf-8")
        # Exercise the packaged interpreter's actual file APIs, not just source
        # tests. Chromium extensions commonly exceed MAX_PATH on Windows where
        # LongPathsEnabled is off, including under portable Cyrillic locations.
        long_relative = Path("Default") / "Extensions" / ("synthetic-" + "x" * 90) / ("version-" + "v" * 90) / "localFileSignInRedirection.html"
        long_file = filesystem_path(profile_dir / long_relative)
        assert len(str(profile_dir / long_relative)) > 260
        long_file.parent.mkdir(parents=True)
        long_file.write_bytes(b"synthetic long-path self-test")
        archive = storage.backup_profile(profile_id)
        assert archive.is_file() and archive.stat().st_size > 0
        restored_id = storage.restore_profile(archive, "Restored test")
        assert (storage.profile_path(restored_id) / "Default" / "test.txt").read_text(encoding="utf-8") == "hello"
        assert filesystem_path(storage.profile_path(restored_id) / long_relative).read_bytes() == b"synthetic long-path self-test"
        outside = temp_root / "outside-synthetic.txt"
        outside.write_text("outside profile", encoding="utf-8")
        os.link(outside, profile_dir / "hardlink-synthetic.txt")
        try:
            storage.backup_profile(profile_id)
        except NeVisionError as exc:
            assert "hardlink" in str(exc)
        else:
            raise AssertionError("Backup accepted a hardlink outside the profile")
        assert len(storage.list_profiles()) == 2
        assert len(storage.list_events()) >= 4
        ordinary = ordinary_identity()
        ordinary_id = storage.save_profile({"name": "Ordinary profile self-test", "fingerprint": ordinary})
        ordinary_backup = storage.backup_profile(ordinary_id)
        ordinary_restored = storage.restore_profile(ordinary_backup, "Ordinary profile restored")
        assert storage.get_profile(ordinary_restored)["fingerprint"] == ordinary
        storage.save_profile({"name": "Ordinary metadata updated"}, ordinary_id)
        assert storage.get_profile(ordinary_id)["fingerprint"] == ordinary
        print(f"{APP_NAME} self-test: PASS")
        return 0
    except Exception as exc:
        print(f"{APP_NAME} self-test: FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(filesystem_path(temp_root), ignore_errors=True)


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    paths = AppPaths.for_runtime()
    try:
        storage = Storage(paths)
        app = NeVisionApp(storage, paths)
        app.run()
        return 0
    except (NeVisionError, OSError, tk.TclError) as exc:
        if tk._default_root:
            messagebox.showerror(APP_NAME, str(exc))
        else:
            if os.name == "nt":
                ctypes.windll.user32.MessageBoxW(None, f"Не удалось открыть {APP_NAME}.\n\n{exc}\n\nРаспакуйте весь ZIP в доступную для записи папку. Не запускайте EXE прямо из архива.", APP_NAME, 0x10)
            elif sys.stderr:
                print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
