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
