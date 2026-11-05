"""BedJet PowerLayer adjustable frame controller.

The PowerLayer is BedJet's ultra-slim adjustable base. It is a separate BLE
peripheral from the BedJet climate blower, even though both advertise the same
1000 service: only the frame exposes the 1001 GATT service, and only after a
connection is established.

Protocol
--------
Commands are two bytes written to the command characteristic::

    [0x01, <button>]

0x01 is the only command opcode the frame accepts; the second byte selects a
remote key. The protocol defines no STOP frame. A movement key runs the motor
for roughly 1.3 seconds and the frame then stops on its own, so holding a
movement means re-sending the key before that watchdog expires and releasing
means letting the refresh end. ``auto_stops_on_idle`` reports this so the
integration never invents a stop write.

Status arrives as a 20-byte frame on the status characteristic, both readable
and notifying. Bytes 12-13 are the head position and bytes 14-15 the foot
position, each a big-endian raw actuator count.

Evidence
--------
GATT layout, command opcodes and key values are ported from the MIT-licensed
``powerlayer`` branch of https://github.com/natekspencer/ha-bedjet
(``custom_components/bedjet/pybedjet/powerlayer.py`` and ``const.py``).

The status layout, the ~1.3s movement watchdog and the raw-to-degree
calibration are derived from a PowerLayer owner's captures and remote
comparisons in https://github.com/natekspencer/ha-bedjet/issues/49:

* In a head-only capture, bytes 12-13 swept 78 to 3362 while bytes 14-15 stayed
  at 0; in a foot-only capture, bytes 14-15 swept 0 to 1704 while bytes 12-13
  stayed at 104.
* Across writes that were isolated by at least 2.8s, a single write produced
  1.18-1.41s of motion (median 1.34s head, 1.28s foot) and about 0.5 degrees of
  travel.
* The degree tables below come from that owner reading the BedJet LCD remote's
  own degree display against the reported counts, so they carry roughly one
  degree of unit-to-unit tolerance.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..const import (
    BEDJET_POWERLAYER_COMMAND_CHAR_UUID,
    BEDJET_POWERLAYER_FOOT_MAX_ANGLE,
    BEDJET_POWERLAYER_HEAD_MAX_ANGLE,
    BEDJET_POWERLAYER_NAME_CHAR_UUID,
    BEDJET_POWERLAYER_SERVICE_UUID,
    BEDJET_POWERLAYER_STATUS_CHAR_UUID,
)
from .base import (
    POSITION_UNIT_DEGREES,
    BedController,
    PositionNumberSpec,
    build_position_number_spec,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

_STATUS_FRAME_LENGTH: Final = 20
_HEAD_RAW_SLICE: Final = slice(12, 14)
_FOOT_RAW_SLICE: Final = slice(14, 16)


class PowerLayerCommand:
    """PowerLayer command opcodes."""

    BUTTON: Final = 0x01


class PowerLayerButton:
    """PowerLayer remote keys carried by a BUTTON command."""

    HEAD_UP: Final = 0x02
    HEAD_DOWN: Final = 0x03
    FOOT_UP: Final = 0x04
    FOOT_DOWN: Final = 0x05

    FLAT: Final = 0x10
    SNORE: Final = 0x11
    ZERO_G: Final = 0x12
    TV: Final = 0x13

    M1: Final = 0x20
    M2: Final = 0x21
    M3: Final = 0x22


# Raw actuator count -> degrees shown on the BedJet LCD remote. Interpolated
# between points and clamped outside them. The head table starts above zero
# because the captured frame rested at a nonzero count when flat.
# fmt: off
_HEAD_ANGLE_TABLE: Final[tuple[tuple[int, float], ...]] = (
    (32, 0), (119, 1), (154, 2), (185, 3), (270, 4), (336, 5),
    (419, 6), (454, 7), (495, 8), (583, 9), (666, 10), (695, 11),
    (783, 12), (851, 13), (950, 14), (989, 15), (1087, 16), (1116, 17),
    (1150, 18), (1178, 19), (1204, 20), (1248, 21), (1274, 22), (1309, 23),
    (1335, 24), (1361, 25), (1410, 26), (1447, 27), (1480, 28), (1507, 29),
    (1542, 30), (1596, 31), (1633, 32), (1660, 33), (1697, 34), (1725, 35),
    (1762, 36), (1825, 37), (1869, 38), (1896, 39), (1923, 40), (1973, 41),
    (2040, 42), (2050, 43), (2117, 44), (2145, 45), (2207, 46), (2232, 47),
    (2307, 48), (2343, 49), (2370, 50), (2426, 51), (2463, 52), (2526, 53),
    (2563, 54), (2599, 55), (2635, 56), (2690, 57), (2728, 58), (2783, 59),
    (2820, 60), (2883, 61), (2919, 62), (2971, 63), (3026, 64), (3055, 65),
    (3115, 66), (3151, 67), (3196, 68), (3223, 69), (3259, 70), (3312, 71),
    (3347, 72), (3390, 73),
)

_FOOT_ANGLE_TABLE: Final[tuple[tuple[int, float], ...]] = (
    (0, 0), (34, 1), (66, 2), (85, 3), (103, 4), (125, 5),
    (163, 6), (189, 7), (216, 8), (242, 9), (269, 10), (306, 11),
    (346, 12), (374, 13), (403, 14), (439, 15), (468, 16), (525, 17),
    (568, 18), (606, 19), (639, 20), (644, 21), (719, 22), (785, 23),
    (823, 24), (862, 25), (923, 26), (982, 27), (1028, 28), (1068, 29),
    (1097, 30), (1163, 31), (1201, 32), (1238, 33), (1276, 34), (1323, 35),
    (1364, 36), (1404, 37), (1461, 38), (1489, 39), (1549, 40), (1561, 41),
    (1600, 42), (1627, 43), (1664, 44), (1692, 45), (1708, 46), (1741, 47),
)
# fmt: on


def raw_count_to_angle(raw: int, table: tuple[tuple[int, float], ...]) -> float:
    """Convert a raw actuator count to degrees using a calibration table."""
    if raw <= table[0][0]:
        return table[0][1]
    if raw >= table[-1][0]:
        return table[-1][1]
    for (low_raw, low_deg), (high_raw, high_deg) in zip(table, table[1:], strict=False):
        if low_raw <= raw <= high_raw:
            span = high_raw - low_raw
            if span == 0:
                return high_deg
            return round(low_deg + (raw - low_raw) * (high_deg - low_deg) / span, 1)
    return table[-1][1]


class BedJetPowerLayerController(BedController):
    """Controller for the BedJet PowerLayer adjustable frame."""

    _write_with_response = False

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the PowerLayer controller."""
        super().__init__(coordinator)
        self._notifications_started = False
        self._head_angle: float | None = None
        self._foot_angle: float | None = None
        self._frame_name: str | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the command characteristic UUID."""
        return BEDJET_POWERLAYER_COMMAND_CHAR_UUID

    @property
    def auto_stops_on_idle(self) -> bool:
        """Return True because the frame defines no STOP frame.

        A movement key runs for roughly 1.3 seconds and the frame then halts by
        itself, so ending the refresh is the protocol's release.
        """
        return True

    @property
    def supports_stop_all(self) -> bool:
        """Return False - there is no stop key to expose."""
        return False

    @property
    def supports_position_feedback(self) -> bool:
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return 3 - the remote exposes M1, M2 and M3."""
        return 3

    @property
    def supports_memory_programming(self) -> bool:
        """Return False - no save opcode is known.

        The remote stores a slot by holding its key, but the frame exposes no
        observed BLE equivalent, so programming stays a remote-only action.
        """
        return False

    @property
    def motor_max_angles(self) -> dict[str, float]:
        """Return the PowerLayer's measured travel limits."""
        return {
            "back": BEDJET_POWERLAYER_HEAD_MAX_ANGLE,
            "head": BEDJET_POWERLAYER_HEAD_MAX_ANGLE,
            "legs": BEDJET_POWERLAYER_FOOT_MAX_ANGLE,
            "feet": BEDJET_POWERLAYER_FOOT_MAX_ANGLE,
        }

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        """Return head and foot sliders scaled to the frame's own travel."""
        return (
            build_position_number_spec(
                "back",
                max_value=BEDJET_POWERLAYER_HEAD_MAX_ANGLE,
                unit=POSITION_UNIT_DEGREES,
            ),
            build_position_number_spec(
                "legs",
                max_value=BEDJET_POWERLAYER_FOOT_MAX_ANGLE,
                unit=POSITION_UNIT_DEGREES,
            ),
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        """Expose the frame's own name and last decoded angles."""
        return {
            "frame_name": self._frame_name,
            "head_angle": self._head_angle,
            "foot_angle": self._foot_angle,
        }

    def _build_command(self, button: int) -> bytes:
        """Build a two-byte BUTTON command."""
        return bytes((PowerLayerCommand.BUTTON, button))

    async def async_discover_capabilities(self) -> None:
        """Confirm the connected peripheral is a frame and read its name.

        The BedJet climate blower advertises the same service, so a mistargeted
        entry would otherwise fail later with an opaque write error.
        """
        client = self.client
        if client is None or not client.is_connected:
            return

        if client.services is not None and (
            client.services.get_service(BEDJET_POWERLAYER_SERVICE_UUID) is None
        ):
            _LOGGER.warning(
                "Connected BedJet device at %s does not expose the PowerLayer service %s. "
                "This is most likely a BedJet climate unit, which this integration "
                "does not control",
                self._coordinator.address,
                BEDJET_POWERLAYER_SERVICE_UUID,
            )
            self.log_discovered_services(level=logging.INFO)
            return

        try:
            async with self._ble_lock:
                data = await client.read_gatt_char(BEDJET_POWERLAYER_NAME_CHAR_UUID)
        except BleakError as err:
            _LOGGER.debug("Could not read PowerLayer frame name: %s", err)
            return

        self._frame_name = bytes(data).decode("utf-8", errors="replace").strip("\x00").strip()
        _LOGGER.debug("PowerLayer frame name: %s", self._frame_name)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Subscribe to the 20-byte status frame."""
        self._notify_callback = callback

        client = self.client
        if client is None or not client.is_connected:
            _LOGGER.warning("Cannot start PowerLayer notifications: not connected")
            return
        if self._notifications_started:
            return

        try:
            async with self._ble_lock:
                await client.start_notify(
                    BEDJET_POWERLAYER_STATUS_CHAR_UUID,
                    self._handle_status_notification,
                )
        except BleakError as err:
            _LOGGER.debug("Could not start PowerLayer position notifications: %s", err)
            return

        self._notifications_started = True
        _LOGGER.debug(
            "PowerLayer position notifications active on %s",
            BEDJET_POWERLAYER_STATUS_CHAR_UUID,
        )

    async def stop_notify(self) -> None:
        """Unsubscribe from the status frame."""
        client = self.client
        if client is None or not client.is_connected or not self._notifications_started:
            self._notifications_started = False
            self._notify_callback = None
            return

        try:
            async with self._ble_lock:
                await client.stop_notify(BEDJET_POWERLAYER_STATUS_CHAR_UUID)
        except BleakError:
            _LOGGER.debug("Failed to stop PowerLayer notifications", exc_info=True)
        finally:
            self._notifications_started = False
            self._notify_callback = None

    def on_disconnect(self) -> None:
        """Drop subscription state so a reconnect re-subscribes."""
        self._notifications_started = False

    def _handle_status_notification(
        self, _characteristic: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Decode head and foot positions from a status frame."""
        payload = bytes(data)
        self.forward_raw_notification(BEDJET_POWERLAYER_STATUS_CHAR_UUID, payload)

        if len(payload) < _STATUS_FRAME_LENGTH:
            _LOGGER.debug(
                "Ignoring short PowerLayer status frame: expected %d bytes, got %d (%s)",
                _STATUS_FRAME_LENGTH,
                len(payload),
                payload.hex(),
            )
            return

        head_raw = int.from_bytes(payload[_HEAD_RAW_SLICE], "big")
        foot_raw = int.from_bytes(payload[_FOOT_RAW_SLICE], "big")
        head_angle = raw_count_to_angle(head_raw, _HEAD_ANGLE_TABLE)
        foot_angle = raw_count_to_angle(foot_raw, _FOOT_ANGLE_TABLE)

        self._head_angle = head_angle
        self._foot_angle = foot_angle

        _LOGGER.debug(
            "PowerLayer position: head=%d raw (%.1f deg), foot=%d raw (%.1f deg)",
            head_raw,
            head_angle,
            foot_raw,
            foot_angle,
        )

        if self._notify_callback:
            self._notify_callback("back", head_angle)
            self._notify_callback("legs", foot_angle)

    async def read_positions(self, motor_count: int = 2) -> None:  # noqa: ARG002
        """Read the status characteristic directly."""
        client = self.client
        if client is None or not client.is_connected:
            return

        try:
            async with self._ble_lock:
                data = await client.read_gatt_char(BEDJET_POWERLAYER_STATUS_CHAR_UUID)
        except BleakError as err:
            _LOGGER.debug("Could not read PowerLayer status: %s", err)
            return

        if data:
            self._handle_status_notification(None, bytearray(data))  # type: ignore[arg-type]

    async def _send_stop(self) -> None:
        """Release the motor by ending the refresh.

        The protocol defines no STOP frame: the frame halts about 1.3 seconds
        after the last write, so sending anything here would be an invented
        command that would instead start a new movement.
        """
        _LOGGER.debug("PowerLayer release: no STOP frame exists, motors halt once writes cease")

    async def _move(self, button: int) -> None:
        """Hold a movement key for the configured press, then release."""
        await self._move_with_stop(self._build_command(button))

    async def _send_once(self, button: int) -> None:
        """Send a latched key once.

        Presets and memory recalls are not watchdogged: the frame drives to the
        stored position on a single write, so repeating would re-trigger them.
        """
        await self.write_command(self._build_command(button))

    # Motor control
    async def move_back_up(self) -> None:
        """Raise the head section."""
        await self._move(PowerLayerButton.HEAD_UP)

    async def move_back_down(self) -> None:
        """Lower the head section."""
        await self._move(PowerLayerButton.HEAD_DOWN)

    async def move_back_stop(self) -> None:
        """Release the head section."""
        await self._send_stop()

    async def move_head_up(self) -> None:
        """Raise the head section (the frame has a single head axis)."""
        await self.move_back_up()

    async def move_head_down(self) -> None:
        """Lower the head section (the frame has a single head axis)."""
        await self.move_back_down()

    async def move_head_stop(self) -> None:
        """Release the head section."""
        await self._send_stop()

    async def move_legs_up(self) -> None:
        """Raise the foot section."""
        await self._move(PowerLayerButton.FOOT_UP)

    async def move_legs_down(self) -> None:
        """Lower the foot section."""
        await self._move(PowerLayerButton.FOOT_DOWN)

    async def move_legs_stop(self) -> None:
        """Release the foot section."""
        await self._send_stop()

    async def move_feet_up(self) -> None:
        """Raise the foot section (the frame has a single foot axis)."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Lower the foot section (the frame has a single foot axis)."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Release the foot section."""
        await self._send_stop()

    async def stop_all(self) -> None:
        """Release every motor."""
        await self._send_stop()

    # Presets
    async def preset_flat(self) -> None:
        """Return the frame to flat."""
        await self._send_once(PowerLayerButton.FLAT)

    async def preset_zero_g(self) -> None:
        """Recall the zero-gravity position."""
        await self._send_once(PowerLayerButton.ZERO_G)

    async def preset_anti_snore(self) -> None:
        """Recall the anti-snore position."""
        await self._send_once(PowerLayerButton.SNORE)

    async def preset_tv(self) -> None:
        """Recall the TV position."""
        await self._send_once(PowerLayerButton.TV)

    async def preset_memory(self, memory_num: int) -> None:
        """Recall a stored memory position."""
        buttons = {
            1: PowerLayerButton.M1,
            2: PowerLayerButton.M2,
            3: PowerLayerButton.M3,
        }
        button = buttons.get(memory_num)
        if button is None:
            raise ValueError("The PowerLayer remote only stores memory slots 1-3")
        await self._send_once(button)

    async def program_memory(self, memory_num: int) -> None:
        """Reject programming - the frame exposes no save command."""
        raise ValueError(
            "The PowerLayer has no BLE command to save a memory slot; "
            "hold M1, M2 or M3 on the physical remote instead"
        )
