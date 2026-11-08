"""Helpers for detecting unauthenticated/unbonded BLE GATT links."""

from __future__ import annotations

import re

from .beds.sleep_number.auth import InvalidSleepNumberSession

_BLE_AUTHENTICATION_ERROR_MARKERS: tuple[str, ...] = (
    "insufficient authentication",
    "insufficient authorization",
    "insufficient encryption",
)
_BLE_AUTHENTICATION_ERROR_CODE_RE = re.compile(r"\b(?:error=|gatt error )(?:5|15)\b")


# aioesphomeapi raises this when the proxy reports a link status change while
# it waits for a reply, e.g. "Peripheral AA:BB:CC:DD:EE:01 changed connection
# status while waiting for BluetoothDevicePairingResponse: Insufficient
# authorization (8)". The status is the ESP-IDF disconnect reason printed with
# ATT error names (8 is a connection timeout), so it means the link dropped,
# never that a characteristic refused an unencrypted link.
_ESPHOME_STATUS_CHANGE_MARKER = "changed connection status while waiting for"
_ESPHOME_PAIRING_RESPONSE_MARKERS: tuple[str, ...] = (
    "bluetoothdevicepairingresponse",
    "bluetoothdeviceunpairingresponse",
)


def is_esphome_connection_status_change(err: BaseException) -> bool:
    """Return True when an ESPHome proxy reported a dropped link mid-request."""
    return _ESPHOME_STATUS_CHANGE_MARKER in str(err).lower()


def is_esphome_pairing_response_failure(err: BaseException) -> bool:
    """Return True when an ESPHome pair request ended with the link dropping.

    This is a failed pairing attempt, not evidence that a bond is missing.
    """
    message = str(err).lower()
    return _ESPHOME_STATUS_CHANGE_MARKER in message and any(
        marker in message for marker in _ESPHOME_PAIRING_RESPONSE_MARKERS
    )


def is_ble_authentication_error(err: BaseException) -> bool:
    """Recognize GATT security errors and explicit protocol authentication failures."""
    if isinstance(err, InvalidSleepNumberSession):
        return True
    if is_esphome_connection_status_change(err):
        # A dropped link reported in ATT terms. Treating it as a missing bond
        # cleared the bond marker after every failed proxy pairing attempt.
        return False
    message = str(err).lower()
    return (
        any(marker in message for marker in _BLE_AUTHENTICATION_ERROR_MARKERS)
        or _BLE_AUTHENTICATION_ERROR_CODE_RE.search(message) is not None
    )


# BlueZ reports a pairing failure at the authentication stage under two names.
# AuthenticationRejected is an explicit refusal by the remote; AuthenticationFailed
# is the generic authentication result and can also mean a failed key exchange or
# a passkey problem. Both are distinct from the markers above, which mean the link
# came up but a characteristic needs an encrypted link.
_BLE_PAIRING_AUTH_FAILURE_MARKERS: tuple[str, ...] = (
    "authenticationrejected",
    "authentication rejected",
    "authenticationfailed",
    "authentication failed",
)


def is_ble_pairing_auth_failure(err: BaseException) -> bool:
    """Return True when a bond attempt failed at the authentication stage.

    Deliberately not named "rejected": only AuthenticationRejected proves the
    remote refused, while AuthenticationFailed is generic. What the two share,
    and what callers act on, is that the bond never happened for an
    authentication reason, so retrying unchanged tends not to help.

    Distinct from :func:`is_ble_authentication_error`, which means an existing
    link lacks the encryption a characteristic requires.
    """
    message = str(err).lower()
    return any(marker in message for marker in _BLE_PAIRING_AUTH_FAILURE_MARKERS)
