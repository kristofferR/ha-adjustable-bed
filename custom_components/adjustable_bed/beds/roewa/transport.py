"""Read-only RÖWA admission shared by setup and live activation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...errors import BedNotConnectedError
from ...profiles import roewa as app


@dataclass(frozen=True, slots=True)
class RoewaLink:
    client: BleakClient
    write: BleakGATTCharacteristic
    feedback: BleakGATTCharacteristic
    firmware: BleakGATTCharacteristic
    model: BleakGATTCharacteristic
    rename: BleakGATTCharacteristic | None


def select_link(client: BleakClient) -> RoewaLink:
    """Find the first exact UUID/property role across discovered services."""
    if not client.is_connected:
        raise BedNotConnectedError()

    def find(uuid: str, prop: str) -> BleakGATTCharacteristic | None:
        return next(
            (
                char
                for service in client.services
                for char in service.characteristics
                if char.uuid.lower() == uuid and prop in char.properties
            ),
            None,
        )

    write, feedback = find(app.WRITE_UUID, "write"), find(app.FEEDBACK_UUID, "read")
    firmware, model = find(app.FIRMWARE_UUID, "read"), find(app.MODEL_UUID, "read")
    if (
        write is None
        or feedback is None
        or firmware is None
        or model is None
        or not {"notify", "indicate"}.intersection(feedback.properties)
    ):
        raise BedNotConnectedError("roewa_setup_required")
    return RoewaLink(client, write, feedback, firmware, model, find(app.NAME_UUID, "write"))


async def read_identity(link: RoewaLink, *, is_current: Callable[[], bool]) -> tuple[str, str]:
    """Read nonempty UTF-8 identity without subscribing or initializing the bed."""

    def check() -> None:
        if not link.client.is_connected or not is_current():
            raise BedNotConnectedError()

    check()
    try:
        firmware = bytes(await link.client.read_gatt_char(link.firmware)).decode("utf-8")
        check()
        model = bytes(await link.client.read_gatt_char(link.model)).decode("utf-8")
    except UnicodeError:
        raise BedNotConnectedError("roewa_setup_required") from None
    check()
    if not firmware or not model:
        raise BedNotConnectedError("roewa_setup_required")
    return firmware, model
