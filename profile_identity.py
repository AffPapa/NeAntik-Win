"""Ordinary-browser profile mode; no fingerprint-modification interface."""
from __future__ import annotations

import json
from typing import Any, Mapping

LEGACY_UNAVAILABLE = "legacy-native-unavailable"


class CoreError(ValueError):
    """A stored profile requires an engine this edition does not provide."""


def ordinary_identity() -> dict[str, Any]:
    return {"schema": 1, "mode": "ordinary"}


def validate_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or type(value.get("schema")) is not int or value["schema"] != 1:
        raise CoreError("Неподдерживаемая схема профиля.")
    if value.get("mode") == "ordinary" and set(value) == {"schema", "mode"}:
        return ordinary_identity()
    if value.get("mode") in {"native", LEGACY_UNAVAILABLE}:
        # Keep a non-runnable marker for experimental records, without retaining
        # or propagating their former spoofing configuration.
        return {"schema": 1, "mode": LEGACY_UNAVAILABLE}
    raise CoreError("Профиль содержит неподдерживаемые параметры браузера.")


def serialize_identity(value: Mapping[str, Any]) -> str:
    return json.dumps(validate_identity(value), sort_keys=True, separators=(",", ":"))


def identity_arguments(value: Mapping[str, Any]) -> list[str]:
    if validate_identity(value)["mode"] != "ordinary":
        raise CoreError("Запуск старого экспериментального профиля отключён; используйте обычный профиль Chrome или Edge.")
    return []
