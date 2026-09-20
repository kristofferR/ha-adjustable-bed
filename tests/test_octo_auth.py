"""Setup PIN checks use actual device replies, not successful BLE writes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    CapabilityReport,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OCTO,
    CONF_BED_TYPE,
    CONF_OCTO_PIN,
    CONF_PROTOCOL_VARIANT,
    OCTO_CHAR_UUID,
    OCTO_STAR2_CHAR_UUID,
    OCTO_VARIANT_STANDARD,
    OCTO_VARIANT_STAR2,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.octo_auth import OctoPinStatus, async_verify_octo_pin
from custom_components.adjustable_bed.setup_operation import (
    OperationOutcome,
    OperationResult,
    SetupOperationState,
)

# Derived from the frozen 1.03.01 PIN report's packet/checksum rules.
# Deliberately independent of the production encoder.
PIN_ACCEPTED = bytes.fromhex("40 21 43 00 01 1a 01 40")
PIN_REJECTED = bytes.fromhex("40 21 43 00 01 1b 00 40")
PIN_CAP_SET = bytes.fromhex("40 21 71 00 09 dd 00 00 03 00 01 01 02 01 00 40")
CAP_END = bytes.fromhex("40 21 71 00 06 eb ff ff ff 00 00 00 40")
CAP_QUERY = bytes.fromhex("40 20 71 00 00 ef 40")
PIN_TRANSMIT = bytes.fromhex("40 20 43 00 04 0f 01 02 03 04 40")


@pytest.fixture
def client() -> MagicMock:
    """A connected BLE transport with notification delivery tied to writes."""
    result = MagicMock()
    result.is_connected = True
    result.services.get_service.return_value = None
    result.services.get_characteristic.return_value = MagicMock()
    result.start_notify = AsyncMock()
    result.stop_notify = AsyncMock()
    result.write_gatt_char = AsyncMock()
    return result


def respond(
    client: MagicMock,
    capabilities: bytes = PIN_CAP_SET + CAP_END,
    reply: bytes = PIN_ACCEPTED,
    *,
    fragment: bool = False,
    before_pin: bytes = b"",
) -> None:
    """Deliver only the traffic requested by a discovery or PIN write."""
    callback: Callable[..., None] | None = None

    async def subscribe(_uuid: str, handler: Callable[..., None]) -> None:
        nonlocal callback
        callback = handler
        if before_pin:
            callback(MagicMock(), bytearray(before_pin))

    async def write(_uuid: str, data: bytes, *, response: bool) -> None:
        assert response is False
        assert callback is not None
        assert data in (CAP_QUERY, PIN_TRANSMIT), "Setup must never send control commands"
        output = capabilities if data == CAP_QUERY else reply
        chunks = (output[:4], output[4:]) if fragment else (output,)
        for chunk in chunks:
            callback(MagicMock(), bytearray(chunk))

    client.start_notify.side_effect = subscribe
    client.write_gatt_char.side_effect = write


@pytest.mark.parametrize("fragment", [False, True])
@pytest.mark.parametrize(
    ("reply", "expected"),
    [(PIN_ACCEPTED, OctoPinStatus.ACCEPTED), (PIN_REJECTED, OctoPinStatus.REJECTED)],
)
async def test_acceptance_requires_device_reply(client, fragment, reply, expected):
    respond(client, reply=reply, fragment=fragment)
    assert await async_verify_octo_pin(client, "1234", VARIANT_AUTO) is expected
    assert [call.args[1] for call in client.write_gatt_char.call_args_list] == [
        CAP_QUERY,
        PIN_TRANSMIT,
    ]
    client.stop_notify.assert_awaited_once_with(OCTO_CHAR_UUID)


@pytest.mark.parametrize(
    ("caps", "pin", "expected"),
    [
        (CAP_END, "", OctoPinStatus.NOT_REQUIRED),
        (PIN_CAP_SET + CAP_END, "", OctoPinStatus.REQUIRED),
    ],
)
async def test_discover_requirements_before_sending_pin(client, caps, pin, expected):
    respond(client, capabilities=caps)
    assert await async_verify_octo_pin(client, pin, VARIANT_AUTO) is expected
    assert client.write_gatt_char.await_count == 1


@pytest.mark.parametrize(
    ("caps", "reply", "early"),
    [
        (PIN_CAP_SET, PIN_ACCEPTED, b""),  # Missing capability-list terminator
        (PIN_CAP_SET + CAP_END, b"", PIN_ACCEPTED),  # Stale acceptance before our PIN
        (PIN_CAP_SET + CAP_END, bytes.fromhex("40 21 43 00 01 00 01 40"), b""),
        (PIN_CAP_SET + CAP_END, bytes.fromhex("40 21 43 00 00 1c 40"), b""),
    ],
)
async def test_incomplete_or_invalid_replies_never_confirm_pin(client, caps, reply, early):
    respond(client, capabilities=caps, reply=reply, before_pin=early)
    with patch("custom_components.adjustable_bed.octo_auth.PIN_VERIFICATION_TIMEOUT", 0.01):
        assert (
            await async_verify_octo_pin(client, "1234", VARIANT_AUTO) is OctoPinStatus.INCONCLUSIVE
        )
    client.stop_notify.assert_awaited_once()


async def test_failed_write_is_not_pin_rejection(client):
    client.write_gatt_char.side_effect = BleakError("write failed")
    assert await async_verify_octo_pin(client, "1234", VARIANT_AUTO) is OctoPinStatus.INCONCLUSIVE
    client.stop_notify.assert_awaited_once()


async def test_cancellation_unsubscribes_and_propagates(client):
    writing = asyncio.Event()

    async def write(*args, **kwargs):
        writing.set()
        await asyncio.Future()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(async_verify_octo_pin(client, "1234", VARIANT_AUTO))
    await writing.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    client.stop_notify.assert_awaited_once()


@pytest.mark.parametrize("variant", [VARIANT_AUTO, OCTO_VARIANT_STAR2])
async def test_star2_does_not_receive_standard_auth_commands(client, variant):
    client.services.get_service.return_value = SimpleNamespace(
        characteristics=[SimpleNamespace(uuid=OCTO_STAR2_CHAR_UUID)]
    )
    assert await async_verify_octo_pin(client, "1234", variant) is OctoPinStatus.NOT_REQUIRED
    client.start_notify.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()


def pin_flow(hass: HomeAssistant, status: OctoPinStatus | None) -> AdjustableBedConfigFlow:
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._pending_entry = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
        CONF_NAME: "Octo bed",
        CONF_BED_TYPE: BED_TYPE_OCTO,
        CONF_OCTO_PIN: "1234",
        CONF_PROTOCOL_VARIANT: OCTO_VARIANT_STANDARD,
    }
    flow._pending_title = "Octo bed"
    flow._operation = SetupOperationState(
        result=OperationResult(
            outcome=OperationOutcome.SUCCESS,
            payload=CapabilityReport(octo_pin_status=status),
        )
    )
    return flow


@pytest.mark.parametrize("status", [OctoPinStatus.ACCEPTED, OctoPinStatus.NOT_REQUIRED])
async def test_setup_saves_only_after_showing_verified_result(hass, status):
    flow = pin_flow(hass, status)
    # Replayed input from the preceding form must not skip the result screen.
    shown = await flow.async_step_verify_octo_pin({CONF_OCTO_PIN: "1234"})
    assert shown["type"] is FlowResultType.FORM
    result = await flow.async_step_verify_octo_pin({})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_OCTO_PIN] == "1234"


@pytest.mark.parametrize(
    "status", [OctoPinStatus.REJECTED, OctoPinStatus.REQUIRED, OctoPinStatus.INCONCLUSIVE, None]
)
async def test_setup_retries_without_saving_unverified_entry(hass, status):
    flow = pin_flow(hass, status)
    shown = await flow.async_step_verify_octo_pin()
    assert shown["type"] is FlowResultType.FORM
    assert shown["errors"]["base"] == f"octo_pin_{(status or OctoPinStatus.INCONCLUSIVE).value}"
    with patch.object(
        flow,
        "async_step_setup_progress",
        AsyncMock(return_value={"type": FlowResultType.SHOW_PROGRESS}),
    ):
        result = await flow.async_step_verify_octo_pin({CONF_OCTO_PIN: " 5678 "})
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    assert flow._pending_entry[CONF_OCTO_PIN] == "5678"
    assert not flow._octo_pin_form_shown


@pytest.mark.parametrize("invalid_pin", ["abc", "¹²³⁴", "١٢٣٤"])
async def test_invalid_replacement_pin_stays_on_form(hass, invalid_pin):
    flow = pin_flow(hass, OctoPinStatus.REJECTED)
    await flow.async_step_verify_octo_pin()
    result = await flow.async_step_verify_octo_pin({CONF_OCTO_PIN: invalid_pin})
    assert result["errors"][CONF_OCTO_PIN] == "invalid_pin"
    assert flow._pending_entry[CONF_OCTO_PIN] == "1234"


@pytest.mark.parametrize("step", ["manual_octo", "bluetooth_octo"])
async def test_pin_collection_routes_through_verification(hass, step):
    flow = pin_flow(hass, None)
    assert flow._pending_entry is not None
    flow._manual_data = dict(flow._pending_entry)
    with patch.object(flow, "_finish_with_verify", AsyncMock()) as verify:
        await getattr(flow, f"async_step_{step}")({CONF_OCTO_PIN: "1234"})
    verify.assert_awaited_once_with(flow._manual_data, "Octo bed")


async def test_no_scanner_cannot_bypass_octo_pin_check(hass):
    flow = pin_flow(hass, None)
    with (
        patch.object(flow, "_verification_possible", return_value=False),
        patch.object(flow, "async_step_setup_progress", AsyncMock()) as progress,
    ):
        await flow._finish_with_verify(flow._pending_entry, "Octo bed")
    progress.assert_awaited_once()


@pytest.mark.parametrize(
    "cap",
    [
        bytes.fromhex("40 21 71 00 09 da 00 00 03 00 01 01 02 01 00 40"),
        bytes.fromhex("40 21 71 00 06 e5 00 00 03 00 00 00 40"),
    ],
)
async def test_corrupt_pin_capability_cannot_look_like_pin_free_bed(client, cap):
    respond(client, capabilities=cap + CAP_END)
    assert await async_verify_octo_pin(client, "1234", VARIANT_AUTO) is OctoPinStatus.INCONCLUSIVE
    assert client.write_gatt_char.await_count == 1
