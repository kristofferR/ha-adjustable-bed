"""Regular diagnostics explain Auth outcomes without logging session IDs."""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.sleep_number_auth import async_read_sleep_number_session


@pytest.mark.parametrize("value,outcome", [
    (b"", "rejected"),
    (bytes(16), "rejected"),
    ((1).to_bytes(16, "big"), "rejected"),
    (bytes.fromhex("112233445566778899aabbccddeeff00"), "accepted"),
])
async def test_auth_diagnostic_records_length_without_session(value, outcome, caplog):
    caplog.set_level(logging.INFO)
    client = MagicMock(read_gatt_char=AsyncMock(return_value=value))
    if outcome == "rejected":
        with pytest.raises(BleakError):
            await async_read_sleep_number_session(client)
    else:
        assert await async_read_sleep_number_session(client) == value
    assert f"Auth {outcome}" in caplog.text
    assert f"bytes={len(value)}" in caplog.text
    if value:
        assert value.hex() not in caplog.text
        assert repr(value) not in caplog.text


async def test_auth_diagnostic_records_transport_failure_and_recovery(caplog):
    caplog.set_level(logging.INFO)
    client = MagicMock(read_gatt_char=AsyncMock(side_effect=[
        BleakError("handle=27 error=15 description=Insufficient encryption"),
        bytes.fromhex("112233445566778899aabbccddeeff00"),
    ]))
    await async_read_sleep_number_session(client)
    assert "read failed: attempt=1" in caplog.text
    assert "handle=27 error=15" in caplog.text
    assert "Auth accepted: attempt=2" in caplog.text
