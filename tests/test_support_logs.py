"""Support evidence works without a disk log and releases temporary resources."""

import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.ble_diagnostics import BLEDiagnosticRunner, DiagnosticReport
from custom_components.adjustable_bed.support_bundle import (
    generate_support_bundle,
    save_support_bundle,
)
from custom_components.adjustable_bed.support_logs import (
    MAX_LOG_ENTRIES,
    MAX_LOG_MESSAGE_LENGTH,
    async_setup_support_logs,
    sanitize_log_message,
)
from custom_components.adjustable_bed.support_proxy_logs import capture_proxy_logs
from custom_components.adjustable_bed.support_report import _get_recent_logs, async_check_log_file


async def test_memory_logs_include_failure_before_capture_without_file(hass: HomeAssistant, caplog, tmp_path):
    """Setup failures survive until a bundle even when HA only logs to stdout."""
    hass.config.config_dir = str(tmp_path)
    buffer = async_setup_support_logs(hass)
    assert async_setup_support_logs(hass) is buffer
    assert not Path(hass.config.path("home-assistant.log")).exists()
    caplog.set_level(logging.DEBUG, logger="custom_components.adjustable_bed")
    logger = logging.getLogger("custom_components.adjustable_bed.coordinator")
    try:
        raise ValueError("Authentication failed")
    except ValueError:
        logger.exception("Pairing failed, octo_pin='123456', noise_psk=noise-psk-value")
    logger.error(
        "Credentials: token=plain-token, access_token='access token', "
        "refresh_token=refresh-token, secret=plain-secret, "
        'client_secret="client secret", authorization=Bearer bearer-token'
    )
    logging.getLogger("other.integration").error("Unrelated secret")

    logs = await _get_recent_logs(hass)
    assert len(logs) == 2
    assert "ValueError: Authentication failed" in logs[0]["message"]
    serialized_logs = json.dumps(logs)
    for credential in (
        "123456",
        "noise-psk-value",
        "plain-token",
        "access token",
        "refresh-token",
        "plain-secret",
        "client secret",
        "bearer-token",
    ):
        assert credential not in serialized_logs

    bundle_path = save_support_bundle(
        hass,
        {"recent_logs": logs},
        "AA:BB:CC:DD:EE:FF",
    )
    saved_bundle = bundle_path.read_text(encoding="utf-8")
    assert "**REDACTED**" in saved_bundle
    for credential in (
        "123456",
        "noise-psk-value",
        "plain-token",
        "access token",
        "refresh-token",
        "plain-secret",
        "client secret",
        "bearer-token",
    ):
        assert credential not in saved_bundle
    assert (await async_check_log_file(hass))["available"] is True


async def test_memory_buffer_is_bounded(hass: HomeAssistant, caplog):
    """Both record count and message size have limits."""
    buffer = async_setup_support_logs(hass)
    caplog.set_level(logging.INFO, logger="bleak")
    logger = logging.getLogger("bleak")
    for i in range(MAX_LOG_ENTRIES + 2):
        logger.info("%s %s", i, "x" * (MAX_LOG_MESSAGE_LENGTH + 1))
    logs = buffer.snapshot()
    assert len(logs) == MAX_LOG_ENTRIES
    assert logs[0]["message"].startswith("2 ")
    assert len(logs[-1]["message"]) == MAX_LOG_MESSAGE_LENGTH


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "Write Characteristic 1234 | /org/bluez/char0001: "
            "bytearray(b'\\x20\\x43\\x01\\x02\\x03\\x04')",
            "Write Characteristic 1234 | /org/bluez/char0001: **REDACTED**",
        ),
        (
            "Could not write value bytearray(b'\\x20\\x43\\x01\\x02\\x03\\x04') "
            "to characteristic 0012",
            "Could not write value **REDACTED** to characteristic 0012",
        ),
    ],
)
def test_raw_ble_write_payloads_are_redacted(message: str, expected: str):
    """Transport debug logs must not reintroduce authentication packets."""
    assert sanitize_log_message(message) == expected


async def test_debug_capture_restores_levels_after_overlap_and_cancellation(hass, caplog):
    """Overlapping captures must not restore logging while another still owns it."""
    buffer = async_setup_support_logs(hass)
    logger = logging.getLogger("bleak")
    caplog.set_level(logging.WARNING, logger="bleak")
    first = buffer.capture_debug()
    second = buffer.capture_debug()
    first.__enter__()
    second.__enter__()
    assert logger.level == logging.DEBUG
    first.__exit__(None, None, None)
    assert logger.level == logging.DEBUG
    second.__exit__(None, None, None)
    assert logger.level == logging.WARNING
    with pytest.raises(asyncio.CancelledError), buffer.capture_debug():
        raise asyncio.CancelledError
    assert logger.level == logging.WARNING
    with buffer.capture_debug():
        logger.setLevel(logging.ERROR)
    assert logger.level == logging.ERROR


async def test_debug_capture_only_forwards_sanitized_records(hass, caplog):
    """Capture-only debug logging must not expose payloads to root handlers."""
    buffer = async_setup_support_logs(hass)
    logger = logging.getLogger("bleak")
    caplog.set_level(logging.DEBUG)

    with buffer.capture_debug():
        logger.debug(
            "Write Characteristic 1234: bytearray(b'\\x20\\x43\\x01\\x02')"
        )

    assert "bytearray" not in caplog.text
    assert "Write Characteristic 1234: **REDACTED**" in caplog.text
    assert logger.propagate is True


@pytest.fixture
def proxy(hass):
    """A registered proxy with a separate, existing HA control connection."""
    entry = MockConfigEntry(domain="esphome", data={"password": "api-password"})
    existing = MagicMock(connected_address="192.0.2.1", port=6053, noise_psk="api-key")
    entry.runtime_data = SimpleNamespace(client=existing)
    entry.add_to_hass(hass)
    registration = MockConfigEntry(domain="bluetooth", data={
        "source": "11:22:33:44:55:66", "source_domain": "esphome",
        "source_config_entry_id": entry.entry_id,
    })
    registration.add_to_hass(hass)
    client = MagicMock(connect=AsyncMock(), disconnect=AsyncMock())
    with (
        patch("aioesphomeapi.client.APIClient", return_value=client) as factory,
        patch(
            "custom_components.adjustable_bed.support_proxy_logs.bluetooth.async_scanner_devices_by_address",
            return_value=[SimpleNamespace(scanner=SimpleNamespace(source="11:22:33:44:55:66"))],
        ),
    ):
        yield client, existing, factory


async def test_proxy_capture_filters_logs_and_preserves_control_connection(hass, proxy):
    """Use a separate socket, omit config dumps, and keep only Bluetooth messages."""
    client, existing, factory = proxy
    async with capture_proxy_logs(hass, "AA:BB:CC:DD:EE:FF") as reports:
        callback = client.subscribe_logs.call_args.args[0]
        callback(SimpleNamespace(message=b"[wifi] password=do-not-include", level=5))
        callback(SimpleNamespace(message=b"\x1b[0;32m[esp32_ble_client] GATT insufficient encryption\x1b[0m", level=2))
        assert len(reports) == 1  # Same proxy's connectable/non-connectable sightings merge.
        assert reports[0]["status"] == "available"
        assert len(reports[0]["entries"]) == 1
        assert reports[0]["entries"][0]["message"] == "[esp32_ble_client] GATT insufficient encryption"
        client.disconnect.assert_not_called()
    factory.assert_called_once()
    assert client.subscribe_logs.call_args.kwargs["dump_config"] is False
    client.disconnect.assert_awaited_once_with(force=True)
    existing.subscribe_logs.assert_not_called()
    existing.disconnect.assert_not_called()
    assert "api-key" not in str(reports)
    assert "api-password" not in str(reports)


async def test_proxy_failure_and_cancellation_close_temporary_socket(hass, proxy):
    """Connection failures stay in the report and cancellation releases sockets."""
    client, existing, _ = proxy
    client.connect.side_effect = TimeoutError("secret credential")
    async with capture_proxy_logs(hass, "AA:BB:CC:DD:EE:FF") as reports:
        assert reports[0]["status"] == "unavailable"
        assert reports[0]["reason"] == "TimeoutError"
        assert "secret credential" not in str(reports)
    client.disconnect.assert_awaited_once_with(force=True)
    client.reset_mock()
    client.connect.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        async with capture_proxy_logs(hass, "AA:BB:CC:DD:EE:FF"):
            pytest.fail("Cancelled connection must not start diagnostics")
    client.disconnect.assert_awaited_once_with(force=True)
    existing.disconnect.assert_not_called()


async def test_proxy_disconnect_is_explicit_even_after_receiving_logs(hass, proxy):
    """Partial logs must not masquerade as an uninterrupted capture."""
    client, _, _ = proxy
    async with capture_proxy_logs(hass, "AA:BB:CC:DD:EE:FF") as reports:
        client.subscribe_logs.call_args.args[0](SimpleNamespace(message=b"[bluetooth_proxy] paired", level=5))
        await client.connect.call_args.kwargs["on_stop"](False)
        assert reports[0]["status"] == "disconnected"
        assert len(reports[0]["entries"]) == 1


@pytest.mark.parametrize("include_logs", [True, False])
async def test_bundle_captures_debug_without_file_and_honors_opt_out(
    hass, proxy, caplog, enable_custom_integrations, include_logs,
):
    """Exercise the bundle orchestration, including opt-out for both log sources."""
    client, _, factory = proxy
    caplog.set_level(logging.WARNING, logger="custom_components.adjustable_bed")
    logger = logging.getLogger("custom_components.adjustable_bed.coordinator")
    async_setup_support_logs(hass)
    logger.warning("Original pairing failure before capture")

    async def run():
        for _ in range(MAX_LOG_ENTRIES + 1):
            logger.debug("Verbose diagnostic traffic")
        logger.debug("Support capture authentication failure")
        if include_logs:
            client.subscribe_logs.call_args.args[0](SimpleNamespace(message=b"[esp32_ble_client] GATT error 15", level=2))
        return DiagnosticReport(
            metadata={}, device={}, advertisement={}, advertisements_by_source=[],
            detection={}, gatt_services=[], gatt_summary={}, device_information={},
            notifications=[], notification_summary={}, adapter_details={},
            connection_history={}, connection_attempt_details=[], command_trace=[], errors=[],
        )

    with patch.object(BLEDiagnosticRunner, "run_diagnostics", side_effect=run):
        report = await generate_support_bundle(
            hass, address="AA:BB:CC:DD:EE:FF", capture_duration=0, include_logs=include_logs,
        )
    assert logging.getLogger("custom_components.adjustable_bed").level == logging.WARNING
    if include_logs:
        assert report["evidence"]["log_capture_status"] == "available"
        assert any("authentication failure" in item["message"] for item in report["recent_logs"])
        assert any("Original pairing failure" in item["message"] for item in report["recent_logs"])
        assert report["bluetooth"]["proxy_logs"][0]["status"] == "available"
    else:
        assert report["recent_logs"] == []
        assert report["bluetooth"]["proxy_logs"] == []
        assert report["evidence"]["log_capture_status"] == "not_requested"
        factory.assert_not_called()
