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


# BlueZ reports an SMP-level refusal as org.bluez.Error.AuthenticationFailed.
# That is a different condition from the markers above: those mean the link came
# up but a characteristic needs an encrypted link, whereas this means the
# peripheral rejected the bond negotiation itself.
_BLE_PAIRING_REJECTED_MARKERS: tuple[str, ...] = (
    "authenticationfailed",
    "authentication failed",
)


def is_ble_pairing_rejected(err: BaseException) -> bool:
    """Return True when the peripheral refused the pairing attempt itself.

    Distinct from :func:`is_ble_authentication_error`, which means an existing
    link lacks the encryption a characteristic requires. This means the bond
    never happened because the remote device said no, which usually points at
    key material the two sides disagree about rather than anything the host can
    retry its way out of.
    """
    message = str(err).lower()
    return any(marker in message for marker in _BLE_PAIRING_REJECTED_MARKERS)
