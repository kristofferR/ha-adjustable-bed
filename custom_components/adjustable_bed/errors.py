"""Errors users see, built from the translated keys in ``strings.json``.

Home Assistant shows the translation of the key. The English text is rendered
here too, from the same ``translations/en.json`` string, so the error reads
plainly in logs and anywhere ``str()`` runs without Home Assistant to look the
translation up. These builders are the only place an error message is written.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from homeassistant.exceptions import (
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)

from .const import DOMAIN

# Read once at import, which Home Assistant runs outside the event loop.
_ENGLISH: dict[str, dict[str, str]] = json.loads(
    (Path(__file__).parent / "translations" / "en.json").read_text(encoding="utf-8")
)["exceptions"]


def _placeholders(values: dict[str, object]) -> dict[str, str]:
    return {name: str(value) for name, value in values.items()}


def _english(key: str, placeholders: dict[str, str]) -> str:
    return _ENGLISH[key]["message"].format(**placeholders)


def keyed(key: str, **placeholders: object) -> tuple[str, dict[str, Any]]:
    """English text and translation keywords, for the integration's own error classes."""
    values = _placeholders(placeholders)
    return _english(key, values), {
        "translation_domain": DOMAIN,
        "translation_key": key,
        "translation_placeholders": values,
    }


def invalid(key: str, **placeholders: object) -> ServiceValidationError:
    """A request the user can correct."""
    values = _placeholders(placeholders)
    return ServiceValidationError(
        _english(key, values),
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=values,
    )


def rejected(err: BaseException) -> ServiceValidationError:
    """A bed's own reason for refusing a request, passed on as it is."""
    return invalid("action_rejected", reason=err)


def failed(key: str, **placeholders: object) -> HomeAssistantError:
    """A request that could not be carried out."""
    values = _placeholders(placeholders)
    return HomeAssistantError(
        _english(key, values),
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=values,
    )


def not_ready(key: str, **placeholders: object) -> ConfigEntryNotReady:
    """Why a bed could not start; shown on the integration card while it retries."""
    values = _placeholders(placeholders)
    return ConfigEntryNotReady(
        _english(key, values),
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=values,
    )
