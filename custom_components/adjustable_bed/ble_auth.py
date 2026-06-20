"""Helpers for detecting unauthenticated/unbonded BLE GATT links."""

from __future__ import annotations

import re

_BLE_AUTHENTICATION_ERROR_MARKERS: tuple[str, ...] = (
    "insufficient authentication",
    "insufficient authorization",
    "gatt error 5",
)
_BLE_AUTHENTICATION_ERROR_CODE_RE = re.compile(r"\berror=5\b")


def is_ble_authentication_error(err: BaseException) -> bool:
    """Return True if a Bleak error indicates an unauthenticated GATT link."""
    message = str(err).lower()
    return (
        any(marker in message for marker in _BLE_AUTHENTICATION_ERROR_MARKERS)
        or _BLE_AUTHENTICATION_ERROR_CODE_RE.search(message) is not None
    )
