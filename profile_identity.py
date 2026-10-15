"""Versioned browser identity metadata with legacy-mode isolation."""
from __future__ import annotations

import json
import secrets
from typing import Any, Mapping

LEGACY_UNAVAILABLE = "legacy-native-unavailable"
NATIVE_PREVIEW = "native-persona-preview"
UINT64_MAX = (1 << 64) - 1


class CoreError(ValueError):
    """A stored profile requires an engine this edition does not provide."""


def ordinary_identity() -> dict[str, Any]:
    return {"schema": 1, "mode": "ordinary"}


def native_preview_identity(seed: int | None = None) -> dict[str, Any]:
    """Create schema-2 compatibility metadata; V4 Canvas does not use this seed."""
    if seed is None:
        seed = secrets.randbelow(UINT64_MAX) + 1
    if type(seed) is not int or not 1 <= seed <= UINT64_MAX:
        raise CoreError("Seed экспериментального профиля должен быть ненулевым uint64.")
    return {"schema": 2, "mode": NATIVE_PREVIEW, "seed": str(seed)}


def validate_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or type(value.get("schema")) is not int:
        raise CoreError("Неподдерживаемая схема профиля.")
    if value["schema"] == 1 and value.get("mode") == "ordinary" and set(value) == {"schema", "mode"}:
        return ordinary_identity()
    if value["schema"] == 1 and value.get("mode") in {"native", LEGACY_UNAVAILABLE}:
        # Keep a non-runnable marker for experimental records, without retaining
        # or propagating their former spoofing configuration.
        return {"schema": 1, "mode": LEGACY_UNAVAILABLE}
    if value["schema"] == 2 and value.get("mode") == NATIVE_PREVIEW and set(value) == {"schema", "mode", "seed"}:
        raw = value["seed"]
        if (not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal() or
                raw.startswith("0") or len(raw) > 20):
            raise CoreError("Seed экспериментального профиля повреждён.")
        try:
            return native_preview_identity(int(raw))
        except (ValueError, CoreError) as exc:
            raise CoreError("Seed экспериментального профиля повреждён.") from exc
    raise CoreError("Профиль содержит неподдерживаемые параметры браузера.")


def serialize_identity(value: Mapping[str, Any]) -> str:
    return json.dumps(validate_identity(value), sort_keys=True, separators=(",", ":"))


def identity_arguments(value: Mapping[str, Any]) -> list[str]:
    identity = validate_identity(value)
    if identity["mode"] == "ordinary":
        return []
    raise CoreError(
        "Этот профиль использует отключённый экспериментальный режим. "
        "Исходные данные сохранены; создайте чистую копию без cookies, истории и сессий."
    )
