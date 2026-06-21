"""Tests for the BLE connection binary sensor's exposed attributes.

Covers issue #385: an intentional idle disconnect should be surfaced as "idle"
(plus a ``disconnect_reason``) rather than a bare "disconnected" that reads as a
fault.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from custom_components.adjustable_bed.binary_sensor import AdjustableBedConnectionSensor


def _attrs(
    *,
    is_connecting: bool = False,
    is_connected: bool = False,
    last_disconnect_reason: str | None = None,
) -> dict[str, Any]:
    """Evaluate ``extra_state_attributes`` against a stub coordinator."""
    coordinator = SimpleNamespace(
        last_connected=None,
        last_disconnected=None,
        connection_source=None,
        connection_rssi=None,
        is_connecting=is_connecting,
        is_connected=is_connected,
        last_disconnect_reason=last_disconnect_reason,
    )
    fake_self = SimpleNamespace(_coordinator=coordinator)
    fget = AdjustableBedConnectionSensor.extra_state_attributes.fget
    assert fget is not None
    return fget(fake_self)


def test_connected_state_detail() -> None:
    attrs = _attrs(is_connected=True, last_disconnect_reason="idle_timeout")
    assert attrs["state_detail"] == "connected"


def test_connecting_state_detail() -> None:
    attrs = _attrs(is_connecting=True)
    assert attrs["state_detail"] == "connecting"


def test_idle_timeout_surfaces_as_idle() -> None:
    attrs = _attrs(last_disconnect_reason="idle_timeout")
    assert attrs["state_detail"] == "idle"
    assert attrs["disconnect_reason"] == "idle_timeout"


def test_manual_disconnect_surfaces_as_idle() -> None:
    attrs = _attrs(last_disconnect_reason="intentional")
    assert attrs["state_detail"] == "idle"
    assert attrs["disconnect_reason"] == "intentional"


def test_unexpected_disconnect_stays_disconnected() -> None:
    attrs = _attrs(last_disconnect_reason="unexpected")
    assert attrs["state_detail"] == "disconnected"
    assert attrs["disconnect_reason"] == "unexpected"


def test_no_reason_omits_disconnect_reason() -> None:
    attrs = _attrs(last_disconnect_reason=None)
    assert attrs["state_detail"] == "disconnected"
    assert "disconnect_reason" not in attrs
