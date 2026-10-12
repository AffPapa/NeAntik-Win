"""One-time privacy defaults for an empty bundled-Chromium user-data directory.

This module never edits an existing Preferences file. Chromium owns that file
after first launch, including any subsequent changes made by the user.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile


# Chromium 155 source references:
# components/content_settings/core/common/pref_names.h (cookie controls key)
# components/content_settings/core/browser/cookie_settings.h (kBlockThirdParty=1)
# components/content_settings/core/browser/content_settings_registry.cc (names)
# components/content_settings/core/browser/website_settings_info.cc ("-" -> "_")
# components/content_settings/core/common/content_settings.h (BLOCK=2)
_INITIAL_PREFERENCES = {
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

    payload = json.dumps(_INITIAL_PREFERENCES, separators=(",", ":")).encode("utf-8")
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
        return True
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
