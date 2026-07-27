"""Tests for distinguishing BLE authentication failure modes (issue #385)."""

from __future__ import annotations

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.ble_auth import (
    is_ble_authentication_error,
    is_ble_pairing_rejected,
)


@pytest.mark.parametrize(
    "message",
    [
        "[org.bluez.Error.AuthenticationFailed] Authentication Failed",
        "org.bluez.Error.AuthenticationFailed",
    ],
)
def test_pairing_rejection_is_recognised(message: str) -> None:
    """BlueZ reports an SMP-level refusal as AuthenticationFailed."""
    assert is_ble_pairing_rejected(BleakError(message)) is True


@pytest.mark.parametrize(
    "message",
    [
        "Insufficient authentication",
        "GATT error 5",
        "error=5",
    ],
)
def test_gatt_auth_errors_are_not_pairing_rejections(message: str) -> None:
    """A link that needs encryption is a different problem from a refused bond.

    These mean the connection came up but a characteristic requires an
    encrypted link. Treating them as a refusal would send the user off to
    factory-reset the bed for something a re-pair fixes.
    """
    err = BleakError(message)
    assert is_ble_authentication_error(err) is True
    assert is_ble_pairing_rejected(err) is False


def test_a_refusal_is_not_reported_as_a_gatt_auth_error() -> None:
    """And the reverse: a refused bond never reached the GATT layer."""
    err = BleakError("[org.bluez.Error.AuthenticationFailed] Authentication Failed")
    assert is_ble_pairing_rejected(err) is True
    assert is_ble_authentication_error(err) is False


def test_unrelated_errors_match_neither() -> None:
    """A plain timeout must not be blamed on authentication."""
    err = BleakError("[org.bluez.Error.NotConnected] Not Connected")
    assert is_ble_pairing_rejected(err) is False
    assert is_ble_authentication_error(err) is False
