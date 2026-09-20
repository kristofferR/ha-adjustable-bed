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
    OCTO_SYSTEM_FROM_DEVICE,
    OCTO_SYSTEM_PIN_STATE,
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

    Uses the frozen OCTO Smart Control 1.03.01 PIN report: discovery precedes
    authentication, and SYSTEM/PIN_STATE value 1 proves acceptance. This sends
    no movement, PIN-setting, or PIN-clearing commands and starts no keepalive.
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
    pin_required = False
    malformed_pin_feature = False
    pin_sent = False
    reply: asyncio.Future[OctoPinStatus] = asyncio.get_running_loop().create_future()

    def notified(_char: BleakGATTCharacteristic, data: bytearray) -> None:
        nonlocal pin_required, malformed_pin_feature
        for packet in codec._extract_response_packets(bytes(data)):
            command, payload = packet["command"], packet["data"]
            if command == [OCTO_SYSTEM_FROM_DEVICE, 0x71] and not pin_sent:
                feature = codec._extract_feature_value_pair(payload)
                if feature is None:
                    # A malformed PIN record must not look like an absent one.
                    if payload[:3] == [0, 0, OCTO_FEATURE_PIN]:
                        malformed_pin_feature = True
                    continue
                feature_id, value, _ = feature
                if feature_id == OCTO_FEATURE_END:
                    features_complete.set()
                elif feature_id == OCTO_FEATURE_PIN:
                    if payload[4] < 1 or len(value) < 2:
                        malformed_pin_feature = True
                    else:
                        pin_required = payload[5] == 1 and value[0] == 1
            elif (
                pin_sent
                and command == [OCTO_SYSTEM_FROM_DEVICE, OCTO_SYSTEM_PIN_STATE]
                and payload
                and not reply.done()
            ):
                reply.set_result(
                    OctoPinStatus.ACCEPTED if payload[0] == 1 else OctoPinStatus.REJECTED
                )

    subscribed = False
    try:
        async with asyncio.timeout(PIN_VERIFICATION_TIMEOUT):
            await client.start_notify(OCTO_CHAR_UUID, notified)
            subscribed = True
            await client.write_gatt_char(
                OCTO_CHAR_UUID, codec._build_packet([0x20, 0x71]), response=False
            )
            await features_complete.wait()
            if malformed_pin_feature or codec.invalid_response_received:
                return OctoPinStatus.INCONCLUSIVE
            if not pin_required:
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
            return await reply
    except TimeoutError, BleakError, ConnectionError:
        return OctoPinStatus.INCONCLUSIVE
    finally:
        if subscribed:
            with contextlib.suppress(BleakError, ConnectionError, TimeoutError):
                async with asyncio.timeout(3):
                    await client.stop_notify(OCTO_CHAR_UUID)
