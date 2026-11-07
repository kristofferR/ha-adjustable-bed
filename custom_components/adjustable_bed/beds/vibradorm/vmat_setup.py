"""VMAT fixed GATT roles and serialized first-bond information stages."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Callable
from typing import cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from .beds.vibradorm_app import (
    VibradormAppMetadata,
    VibradormAppMetadataProgress,
    _cancellable,
    _shield_cleanup,
)
from .codec import vibradorm as codec
from .profiles.vibradorm import VMAT_CLOSE, VMAT_QUERY_STAGES

_LOGGER = logging.getLogger(__name__)

DIS = "0000180a-0000-1000-8000-00805f9b34fb"
DIS_FIELDS = (
    ("model", "00002a24-0000-1000-8000-00805f9b34fb"),
    ("firmware", "00002a26-0000-1000-8000-00805f9b34fb"),
    ("software", "00002a28-0000-1000-8000-00805f9b34fb"),
)


def vmat_characteristic(
    client: BleakClient, uuid: str, property_name: str | None,
) -> BleakGATTCharacteristic:
    """Resolve only the shipped service and exact required property."""
    if not client.is_connected or not client.services:
        raise ConnectionError("VMAT requires a live discovered GATT connection")
    service_uuid = DIS if uuid in {item[1] for item in DIS_FIELDS} else (
        codec.STATUS_SERVICE_UUID if uuid == codec.MANAGEMENT_CHAR_UUID else codec.SERVICE_UUID
    )
    selected = next((
        characteristic
        for service in client.services if service.uuid.lower() == service_uuid
        for characteristic in service.characteristics if characteristic.uuid.lower() == uuid
    ), None)
    if selected is None or property_name is not None and property_name not in selected.properties:
        raise ValueError(f"Missing exact VMAT GATT role {uuid} ({property_name or 'existence'})")
    return selected


def validate_vmat_roles(client: BleakClient, *, basic: bool, onboarding: bool = False) -> None:
    vmat_characteristic(client, codec.CBI_CHAR_UUID, "write-without-response")
    vmat_characteristic(client, codec.RESPONSE_CHAR_UUID, "notify")
    for _, uuid in DIS_FIELDS:
        vmat_characteristic(client, uuid, "read")
    if basic:
        vmat_characteristic(client, codec.MOTOR_CHAR_UUID, "write")
        vmat_characteristic(client, codec.LIGHT_CHAR_UUID, "write")
    if onboarding:
        vmat_characteristic(client, codec.MANAGEMENT_CHAR_UUID, None)
    # Every shipped frame fits the mandatory BLE MTU of 23. Bleak owns MTU
    # negotiation; there is no portable request_mtu API to invent here.
    if client.mtu_size < 23:
        raise ValueError("VMAT requires the mandatory BLE MTU of at least 23")


def parse_stage_response(field: str, prefix: bytes, raw: bytes) -> str | None:
    if not raw.startswith(prefix):
        return None
    if field in ("xmc_status", "opmode"):
        if len(raw) != 3:
            return None
        value = raw[2]
        return str(value - 256 if field == "opmode" and value >= 128 else value)
    if field == "main_firmware_article" and len(raw) <= len(prefix):
        return None
    return codec.decode_text(raw[len(prefix):])


async def async_read_vmat_dis(
    client: BleakClient, cancel_event: asyncio.Event | None,
    progress: Callable[[VibradormAppMetadataProgress], None] | None,
) -> VibradormAppMetadata:
    values: dict[str, str] = {}
    for field, uuid in DIS_FIELDS:
        raw = await _cancellable(client.read_gatt_char(vmat_characteristic(client, uuid, "read")), cancel_event)
        values[field] = codec.decode_text(bytes(raw))
        if progress is not None:
            progress(cast(VibradormAppMetadataProgress, {field: values[field]}))
    return VibradormAppMetadata(values["model"], values["firmware"], values["software"])


async def async_prepare_vmat_pairing(
    client: BleakClient, *, basic: bool, deadline: float,
    cancel_event: asyncio.Event | None = None,
    metadata_progress: Callable[[VibradormAppMetadataProgress], None] | None = None,
) -> VibradormAppMetadata:
    """Read three DIS values and seven bounded stages before native pairing."""
    validate_vmat_roles(client, basic=basic, onboarding=True)
    notify = vmat_characteristic(client, codec.RESPONSE_CHAR_UUID, "notify")
    current: tuple[str, bytes, asyncio.Future[str]] | None = None

    def callback(_sender: BleakGATTCharacteristic, data: bytearray) -> None:
        stage = current
        if stage is None or stage[2].done():
            return
        value = parse_stage_response(stage[0], stage[1], bytes(data))
        if value is not None:
            stage[2].set_result(value)

    subscribed = False
    try:
        async with asyncio.timeout_at(deadline):
            await _cancellable(asyncio.sleep(0.5), cancel_event)
            await _cancellable(client.start_notify(notify, callback), cancel_event)
            subscribed = True
            metadata = await async_read_vmat_dis(client, cancel_event, metadata_progress)
            article: str | None = None
            for field, packet, prefix, timeout in VMAT_QUERY_STAGES:
                reply: asyncio.Future[str] = asyncio.get_running_loop().create_future()
                current = (field, prefix, reply)
                try:
                    await _cancellable(client.write_gatt_char(
                        vmat_characteristic(client, codec.CBI_CHAR_UUID, "write-without-response"),
                        packet, response=False,
                    ), cancel_event)

                    async def receive(pending: asyncio.Future[str] = reply) -> str:
                        return await pending

                    try:
                        async with asyncio.timeout(timeout):
                            value = await _cancellable(receive(), cancel_event)
                    except TimeoutError:
                        pass  # Missing replies do not create an acknowledgment.
                    else:
                        if metadata_progress is not None:
                            metadata_progress(cast(VibradormAppMetadataProgress, {field: value}))
                        if field == "main_firmware_article":
                            article = value
                finally:
                    current = None
                    if not reply.done():
                        reply.cancel()
            return VibradormAppMetadata(metadata.model, metadata.firmware, metadata.software, article)
    finally:
        current = None
        if subscribed:
            async def unsubscribe() -> None:
                async with asyncio.timeout(2):
                    await client.stop_notify(notify)

            original = sys.exception()
            try:
                await _shield_cleanup(unsubscribe())
            except (Exception, asyncio.CancelledError):
                if original is None:
                    raise
                _LOGGER.debug("VMAT unsubscribe failed after an earlier setup failure", exc_info=True)


async def async_close_vmat_setup(client: BleakClient) -> None:
    """Bounded close before the caller disconnects its setup-owned connection."""
    async with asyncio.timeout(2):
        await client.write_gatt_char(
            vmat_characteristic(client, codec.CBI_CHAR_UUID, "write-without-response"),
            VMAT_CLOSE, response=False,
        )
