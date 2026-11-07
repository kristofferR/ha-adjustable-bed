"""Verify Octo's application PIN on a setup-owned BLE connection."""

from __future__ import annotations

import asyncio
import contextlib
from enum import StrEnum

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from .beds.octo import (
    OCTO_FEATURE_END,
    OCTO_FEATURE_PIN,
    OCTO_FEATURE_TIMEOUT,
    OCTO_SESSION_RESPONSE_TIMEOUT,
    OCTO_SYSTEM_FROM_DEVICE,
    OCTO_SYSTEM_GET_CAPS,
    OCTO_SYSTEM_GET_DEVICEINFO,
    OCTO_SYSTEM_PIN_STATE,
    OCTO_SYSTEM_PING,
    OctoPacketCodec,
)
from .const import (
    OCTO_CHAR_UUID,
    OCTO_STAR2_CHAR_UUID,
    OCTO_STAR2_SERVICE_UUID,
    OCTO_VARIANT_STAR2,
    VARIANT_AUTO,
)
from .validators import is_valid_octo_pin

# Setup bounds, not firmware timing guarantees.
PIN_VERIFICATION_TIMEOUT = 10.0


class OctoPinStatus(StrEnum):
    """Evidence from this connection, never inferred from a successful write."""

    ACCEPTED = "accepted"
    NOT_REQUIRED = "not_required"
    REQUIRED = "required"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"

    @property
    def allows_setup(self) -> bool:
        """Whether setup has enough evidence to save the entry."""
        return self in (self.ACCEPTED, self.NOT_REQUIRED)


async def async_verify_octo_pin(
    client: BleakClient, pin: str, variant: str | None
) -> OctoPinStatus:
    """Discover PIN requirements, then wait for the submitted PIN's reply.

    Replays the app's ordered ping, exact device-info response, capability
    discovery and PIN state proof. This sends no movement or PIN-setting
    command and starts no periodic authentication task.
    The caller owns connecting and disconnecting, including cancellation.
    """
    if variant == OCTO_VARIANT_STAR2:
        return OctoPinStatus.NOT_REQUIRED
    if variant in (None, VARIANT_AUTO):
        # Match the runtime factory's variant selection, including its service
        # check; the Star2 protocol has no application PIN exchange.
        service = client.services.get_service(OCTO_STAR2_SERVICE_UUID)
        if service is not None and any(
            char.uuid.lower() == OCTO_STAR2_CHAR_UUID.lower() for char in service.characteristics
        ):
            return OctoPinStatus.NOT_REQUIRED
    if client.services.get_characteristic(OCTO_CHAR_UUID) is None:
        return OctoPinStatus.INCONCLUSIVE

    codec = OctoPacketCodec()
    features_complete = asyncio.Event()
    ping_reply_seen = asyncio.Event()
    device_info_ready = asyncio.Event()
    ping_valid = False
    ping_invalid = False
    device_info_valid = False
    device_info_invalid = False
    pin_required = False
    malformed_capability = False
    pin_sent = False
    reply: asyncio.Future[OctoPinStatus] = asyncio.get_running_loop().create_future()

    def notified(_char: BleakGATTCharacteristic, data: bytearray) -> None:
        nonlocal pin_required, malformed_capability, ping_valid, ping_invalid
        nonlocal device_info_valid, device_info_invalid
        for packet in codec._extract_response_packets(bytes(data)):
            command, payload = packet["command"], packet["data"]
            if command == [OCTO_SYSTEM_FROM_DEVICE, OCTO_SYSTEM_PING]:
                if packet["wire_command"] == command and not payload:
                    if not ping_invalid:
                        ping_valid = True
                else:
                    ping_invalid = True
                ping_reply_seen.set()
            elif command == [OCTO_SYSTEM_FROM_DEVICE, OCTO_SYSTEM_GET_DEVICEINFO]:
                if len(payload) == 10:
                    if not device_info_invalid:
                        device_info_valid = True
                else:
                    device_info_invalid = True
                device_info_ready.set()
            elif command == [OCTO_SYSTEM_FROM_DEVICE, OCTO_SYSTEM_GET_CAPS] and not pin_sent:
                feature = codec._extract_feature_value_pair(payload)
                if feature is None:
                    malformed_capability = True
                    continue
                if feature.feature_id == OCTO_FEATURE_END:
                    features_complete.set()
                elif feature.feature_id == OCTO_FEATURE_PIN:
                    if not feature.characteristic or len(feature.value) < 2:
                        malformed_capability = True
                    else:
                        pin_required = feature.characteristic[0] == 1 and feature.value[0] == 1
            elif (
                pin_sent
                and command == [OCTO_SYSTEM_FROM_DEVICE, OCTO_SYSTEM_PIN_STATE]
                and payload
                and not reply.done()
            ):
                reply.set_result(
                    OctoPinStatus.ACCEPTED if payload[0] == 1 else OctoPinStatus.REJECTED
                )

    def optional_reply_invalid() -> bool:
        return ping_invalid or device_info_invalid or codec.invalid_response_received

    subscribed = False
    try:
        async with asyncio.timeout(PIN_VERIFICATION_TIMEOUT):
            await client.start_notify(OCTO_CHAR_UUID, notified)
            subscribed = True
            await client.write_gatt_char(
                OCTO_CHAR_UUID,
                codec._build_packet([0x20, OCTO_SYSTEM_PING]),
                response=False,
            )
            try:
                await asyncio.wait_for(
                    ping_reply_seen.wait(), timeout=OCTO_SESSION_RESPONSE_TIMEOUT
                )
            except TimeoutError:
                if optional_reply_invalid() or codec._response_buffer:
                    return OctoPinStatus.INCONCLUSIVE
            if optional_reply_invalid() or (ping_reply_seen.is_set() and not ping_valid):
                return OctoPinStatus.INCONCLUSIVE
            await client.write_gatt_char(
                OCTO_CHAR_UUID,
                codec._build_packet([0x20, OCTO_SYSTEM_GET_DEVICEINFO]),
                response=False,
            )
            try:
                await asyncio.wait_for(
                    device_info_ready.wait(), timeout=OCTO_SESSION_RESPONSE_TIMEOUT
                )
            except TimeoutError:
                if optional_reply_invalid() or codec._response_buffer:
                    return OctoPinStatus.INCONCLUSIVE
            if optional_reply_invalid() or (device_info_ready.is_set() and not device_info_valid):
                return OctoPinStatus.INCONCLUSIVE
            if codec._response_buffer:
                return OctoPinStatus.INCONCLUSIVE
            codec._response_buffer.clear()
            await client.write_gatt_char(
                OCTO_CHAR_UUID,
                codec._build_packet([0x20, OCTO_SYSTEM_GET_CAPS]),
                response=False,
            )
            await asyncio.wait_for(features_complete.wait(), timeout=OCTO_FEATURE_TIMEOUT)
            if malformed_capability or optional_reply_invalid() or codec._response_buffer:
                return OctoPinStatus.INCONCLUSIVE
            if not pin_required:
                if optional_reply_invalid():
                    return OctoPinStatus.INCONCLUSIVE
                return OctoPinStatus.NOT_REQUIRED
            if not pin:
                return OctoPinStatus.REQUIRED
            if not is_valid_octo_pin(pin):
                return OctoPinStatus.INCONCLUSIVE
            # Do not let a pre-authentication partial frame confirm this PIN.
            codec._response_buffer.clear()
            pin_sent = True
            await client.write_gatt_char(
                OCTO_CHAR_UUID,
                codec._build_packet([0x20, 0x43], [int(digit) for digit in pin]),
                response=False,
            )
            status = await asyncio.wait_for(reply, timeout=PIN_VERIFICATION_TIMEOUT)
            return (
                OctoPinStatus.INCONCLUSIVE
                if optional_reply_invalid() or codec._response_buffer
                else status
            )
    except TimeoutError, BleakError, ConnectionError:
        return OctoPinStatus.INCONCLUSIVE
    finally:
        if subscribed:
            with contextlib.suppress(BleakError, ConnectionError, TimeoutError):
                async with asyncio.timeout(3):
                    await client.stop_notify(OCTO_CHAR_UUID)
