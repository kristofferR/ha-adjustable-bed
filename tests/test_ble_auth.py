"""Tests for distinguishing BLE authentication failure modes (issue #385)."""

from __future__ import annotations

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.ble_auth import (
    is_ble_authentication_error,
    is_ble_pairing_auth_failure,
)


@pytest.mark.parametrize(
    "message",
    [
        "[org.bluez.Error.AuthenticationFailed] Authentication Failed",
        "org.bluez.Error.AuthenticationFailed",
        # Device1.Pair() also has an explicit rejection result.
        "[org.bluez.Error.AuthenticationRejected] Authentication Rejected",
        "org.bluez.Error.AuthenticationRejected",
    ],
)
def test_authentication_stage_failures_are_recognised(message: str) -> None:
    """Both BlueZ spellings mean the bond failed at the authentication stage."""
    assert is_ble_pairing_auth_failure(BleakError(message)) is True


@pytest.mark.parametrize(
    "message",
    [
        "Insufficient authentication",
        "GATT error 5",
        "error=5",
    ],
)
def test_gatt_auth_errors_are_not_pairing_failures(message: str) -> None:
    """A link that needs encryption is a different problem from a refused bond.

    These mean the connection came up but a characteristic requires an
    encrypted link. Treating them as a pairing failure would send the user off to
    clear stored keys for something a re-pair fixes.
    """
    err = BleakError(message)
    assert is_ble_authentication_error(err) is True
    assert is_ble_pairing_auth_failure(err) is False


def test_a_pairing_failure_is_not_reported_as_a_gatt_auth_error() -> None:
    """And the reverse: a failed bond never reached the GATT layer."""
    err = BleakError("[org.bluez.Error.AuthenticationFailed] Authentication Failed")
    assert is_ble_pairing_auth_failure(err) is True
    assert is_ble_authentication_error(err) is False


def test_unrelated_errors_match_neither() -> None:
    """A plain timeout must not be blamed on authentication."""
    err = BleakError("[org.bluez.Error.NotConnected] Not Connected")
    assert is_ble_pairing_auth_failure(err) is False
    assert is_ble_authentication_error(err) is False


def test_repair_text_does_not_assume_the_bond_lives_on_the_host() -> None:
    """A proxy bond cannot be cleared with bluetoothctl on the Home Assistant host.

    strings.json already states that Home Assistant cannot remove a bond that
    lives on a proxy, so recovery guidance must not tell every user to run
    bluetoothctl there.
    """
    import json
    from pathlib import Path

    strings = json.loads(
        Path("custom_components/adjustable_bed/strings.json").read_text()
    )
    flow = strings["issues"]["pairing_required"]["fix_flow"]
    description = flow["step"]["confirm"]["description"]

    assert "ESPHome" in description
    assert "stored on the proxy" in description
    # Scoped to the errors that actually mean a refusal, so an ordinary
    # missing-encryption failure is not sent down this path.
    assert "AuthenticationFailed" in description
    assert "AuthenticationRejected" in description


def test_shared_repair_text_prescribes_no_bed_specific_reset() -> None:
    """The pairing repair is shared by every pairing-required protocol.

    Recovery steps inferred from one bed must not be presented to unrelated
    beds as though they were verified for those protocols.
    """
    import json
    from pathlib import Path

    strings = json.loads(
        Path("custom_components/adjustable_bed/strings.json").read_text()
    )
    flow = strings["issues"]["pairing_required"]["fix_flow"]
    blob = json.dumps(flow).lower()

    assert "factory reset" not in blob
    assert "dwipe" not in blob


def test_repair_text_does_not_assert_an_unproven_cause() -> None:
    """AuthenticationFailed is generic, so the cause must be offered, not asserted."""
    import json
    from pathlib import Path

    strings = json.loads(
        Path("custom_components/adjustable_bed/strings.json").read_text()
    )
    flow = strings["issues"]["pairing_required"]["fix_flow"]
    description = flow["step"]["confirm"]["description"]

    assert "One common cause" in description
    # Not "the bed is refusing the bond": only AuthenticationRejected proves that.
    assert "refusing the bond" not in description


def test_translation_strings_contain_no_angle_brackets() -> None:
    """hassfest rejects angle brackets in translations as HTML.

    A placeholder written as `<address>` reads as an HTML tag and fails CI, so
    catch it here instead: the strings already receive {address}.
    """
    import json
    import re
    from pathlib import Path

    pattern = re.compile(r"<[^>]+>")
    offenders: list[str] = []

    def walk(node: object, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, str) and pattern.search(node):
            offenders.append(path)

    for name in (
        "strings.json",
        "translations/en.json",
        "translations/nb.json",
    ):
        walk(
            json.loads(Path("custom_components/adjustable_bed", name).read_text()),
            name,
        )

    assert offenders == []
