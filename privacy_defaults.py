"""One-time privacy and managed-download defaults for an empty Chromium profile.

Initial setup never overwrites an existing Preferences file. Later rebasing
changes only the managed download path when it still matches our marker;
Chromium owns all other preferences and later user choices.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile


DOWNLOAD_MARKER_NAME = "NeAntikManagedDownloads.json"
DOWNLOAD_MARKER_FORMAT = "neantik-managed-downloads-v1"
MAX_PREFERENCES_BYTES = 16 * 1024 * 1024


# Chromium 155 source references:
# components/content_settings/core/common/pref_names.h (cookie controls key)
# components/content_settings/core/browser/cookie_settings.h (kBlockThirdParty=1)
# components/content_settings/core/browser/content_settings_registry.cc (names)
# components/content_settings/core/browser/website_settings_info.cc ("-" -> "_")
# components/content_settings/core/common/content_settings.h (BLOCK=2)
# chrome/browser/preloading/preloading_prefs.h (kDisabled=2)
_INITIAL_PREFERENCES = {
    "net": {"network_prediction_options": 2},
    "newtab_page_location_override": "about:blank",
    "profile": {
        "cookie_controls_mode": 1,
        "default_content_setting_values": {
            "geolocation": 2,
            "notifications": 2,
            "media_stream_camera": 2,
            "media_stream_mic": 2,
        },
    }
}


def _is_link_or_junction(path: Path) -> bool:
    """Reject links and Windows reparse points before any file operation."""
    if path.is_symlink():
        return True
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    return bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _browser_visible_path(path: Path) -> str:
    """Strip Python's internal extended Win32 prefix before writing Chromium prefs."""
    value = str(path.resolve())
    if os.name == "nt":
        if value.lower().startswith("\\\\?\\unc\\"):
            return "\\\\" + value[8:]
        if value.startswith("\\\\?\\"):
            return value[4:]
    return value


def initialize_privacy_defaults(user_data_dir: str | os.PathLike[str]) -> bool:
    """Write new-profile defaults once; return ``True`` only when created.

    A nonempty user-data directory or Default directory is considered an
    existing profile, even if Preferences is missing. Existing preferences are
    never parsed or changed. The temporary file is synced and atomically linked
    to the final name without replacing a concurrent Chromium/user write.
    """
    root = Path(user_data_dir)
    default = root / "Default"
    preferences = default / "Preferences"

    if any(_is_link_or_junction(path) for path in (root, default, preferences)):
        raise ValueError("Profile path contains a symlink or reparse point")
    if root.exists() and not root.is_dir():
        raise ValueError("Profile path is not a directory")
    if default.exists() and not default.is_dir():
        raise ValueError("Chromium Default path is not a directory")
    if preferences.exists():
        return False

    # No retrofit of existing profiles: not even when their Preferences file is
    # absent, as profile storage might already contain cookies or other state.
    if root.exists() and any(item.name != "Default" for item in root.iterdir()):
        return False
    if default.exists() and any(default.iterdir()):
        return False

    default.mkdir(parents=True, exist_ok=True)
    if any(_is_link_or_junction(path) for path in (root, default, preferences)):
        raise ValueError("Profile path changed to a symlink or reparse point")
    if any(item.name != "Default" for item in root.iterdir()) or any(default.iterdir()):
        return False

    download_dir = root.resolve() / "Downloads"
    if _is_link_or_junction(download_dir):
        raise ValueError("Managed downloads path is a link or reparse point")
    initial = json.loads(json.dumps(_INITIAL_PREFERENCES))
    initial["download"] = {"default_directory": _browser_visible_path(download_dir), "prompt_for_download": False}
    payload = json.dumps(initial, separators=(",", ":")).encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".privacy-defaults-", suffix=".tmp",
            dir=default, delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if any(_is_link_or_junction(path) for path in (root, default, preferences)):
            raise ValueError("Profile path changed to a symlink or reparse point")
        try:
            os.link(temporary, preferences)
        except FileExistsError:
            return False
        try:
            download_dir.mkdir()
            marker = root / DOWNLOAD_MARKER_NAME
            marker_payload = {"format": DOWNLOAD_MARKER_FORMAT, "path": _browser_visible_path(download_dir)}
            _atomic_json_replace(marker, marker_payload)
        except (OSError, ValueError):
            preferences.unlink(missing_ok=True)
            try:
                download_dir.rmdir()
            except OSError:
                pass
            raise
        return True
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _atomic_json_replace(path: Path, payload: dict) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=".neantik-write-", suffix=".tmp",
                                         dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def ensure_managed_download_directory(user_data_dir: str | os.PathLike[str]) -> bool:
    """Rebase only NeAntik-managed Chromium downloads after a portable move.

    Returns True when the managed path is current. Existing profiles without
    a marker and users' custom Chromium download directories are untouched.
    Call only while the profile is closed and guarded by the profile mutex.
    """
    root = Path(user_data_dir)
    marker = root / DOWNLOAD_MARKER_NAME
    preferences = root / "Default" / "Preferences"
    if not marker.exists():
        return False
    download_dir = root.resolve() / "Downloads"
    if any(_is_link_or_junction(path) for path in (root, root / "Default", marker, preferences, download_dir)):
        raise ValueError("Managed downloads path contains a link or reparse point")
    if marker.stat().st_size > 4096 or preferences.stat().st_size > MAX_PREFERENCES_BYTES:
        raise ValueError("Managed download preferences are unexpectedly large")
    binding = json.loads(marker.read_text(encoding="utf-8"))
    if not isinstance(binding, dict) or binding.get("format") != DOWNLOAD_MARKER_FORMAT:
        raise ValueError("Invalid managed downloads marker")
    old_path = binding.get("path")
    if not isinstance(old_path, str) or not Path(old_path).is_absolute() or Path(old_path).name != "Downloads":
        raise ValueError("Invalid managed downloads path")
    payload = json.loads(preferences.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Invalid managed download Preferences")
    if not isinstance(payload.get("download"), dict):
        return False  # User removed the managed preference; do not recreate it.
    current = payload["download"].get("default_directory")
    expected = _browser_visible_path(download_dir)
    if current not in (old_path, expected):
        return False  # User deliberately selected another directory in Chromium.
    download_dir.mkdir(exist_ok=True)
    if current != expected:
        payload.setdefault("download", {})["default_directory"] = expected
        _atomic_json_replace(preferences, payload)
    if old_path != expected:
        _atomic_json_replace(marker, {"format": DOWNLOAD_MARKER_FORMAT, "path": expected})
    return True
