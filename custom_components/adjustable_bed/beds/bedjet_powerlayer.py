"""BedJet PowerLayer adjustable frame controller.

The PowerLayer is BedJet's ultra-slim adjustable base. It is a separate BLE
peripheral from the BedJet climate blower, even though both advertise the same
1000 service: only the frame exposes the 1001 GATT service, and only after a
connection is established.

The frames come from ``codec/bedjet_powerlayer.py``, and the keys, calibration
and travel limits from ``profiles/bedjet_powerlayer.py``. A movement key runs
the motor for roughly 1.3 seconds and the frame then stops on its own, so
holding a movement means re-sending the key before that watchdog expires and
releasing means letting the refresh end. ``auto_stops_on_idle`` reports this so
the integration never invents a stop write.

The status layout, the ~1.3s movement watchdog and the raw-to-degree
calibration are derived from a PowerLayer owner's captures and remote
comparisons in https://github.com/natekspencer/ha-bedjet/issues/49:

* In a head-only capture, bytes 12-13 swept 78 to 3362 while bytes 14-15 stayed
  at 0; in a foot-only capture, bytes 14-15 swept 0 to 1704 while bytes 12-13
  stayed at 104.
* Across writes that were isolated by at least 2.8s, a single write produced
  1.18-1.41s of motion (median 1.34s head, 1.28s foot) and about 0.5 degrees of
  travel.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..codec import bedjet_powerlayer as codec
from ..profiles.bedjet_powerlayer import POWERLAYER, PowerLayerProfile, raw_count_to_angle
from .base import BedController, ProfileExecution
from .entity_specs import POSITION_UNIT_DEGREES, PositionNumberSpec, build_position_number_spec

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class BedJetPowerLayerController(ProfileExecution[PowerLayerProfile], BedController):
    """Controller for the BedJet PowerLayer adjustable frame."""

    _write_with_response = False

    def __init__(
        self, coordinator: AdjustableBedCoordinator, profile: PowerLayerProfile = POWERLAYER
    ) -> None:
        """Initialize the PowerLayer controller."""
        super().__init__(coordinator)
        self.profile = profile
        self._notifications_started = False
        self._head_angle: float | None = None
        self._foot_angle: float | None = None
        self._frame_name: str | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the command characteristic UUID."""
        return codec.TRANSPORT.command_uuid

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
        return len(self.profile.memory)

    @property
    def supports_memory_programming(self) -> bool:
        """Return False - no save opcode is known.

        The remote stores a slot by holding its key, but the frame exposes no
        observed BLE equivalent, so programming stays a remote-only action.
        """
        return False

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        """Return head and foot sliders scaled to the frame's own travel."""
        return (
            build_position_number_spec(
                "back",
                max_value=self.profile.head_max_angle,
                unit=POSITION_UNIT_DEGREES,
            ),
            build_position_number_spec(
                "legs",
                max_value=self.profile.foot_max_angle,
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

    async def async_discover_capabilities(self) -> None:
        """Confirm the connected peripheral is a frame and read its name.

        The BedJet climate blower advertises the same service, so a mistargeted
        entry would otherwise fail later with an opaque write error.
        """
        client = self.client
        if client is None or not client.is_connected:
            return

        if client.services is not None and (
            client.services.get_service(codec.TRANSPORT.service_uuid) is None
        ):
            _LOGGER.warning(
                "Connected BedJet device at %s does not expose the PowerLayer service %s. "
                "This is most likely a BedJet climate unit, which this integration "
                "does not control",
                self._coordinator.address,
                codec.TRANSPORT.service_uuid,
            )
            self.log_discovered_services(level=logging.INFO)
            return

        try:
            async with self._ble_lock:
                data = await client.read_gatt_char(codec.TRANSPORT.name_uuid)
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
                    codec.TRANSPORT.status_uuid,
                    self._handle_status_notification,
                )
        except BleakError as err:
            _LOGGER.debug("Could not start PowerLayer position notifications: %s", err)
            return

        self._notifications_started = True
        _LOGGER.debug(
            "PowerLayer position notifications active on %s",
            codec.TRANSPORT.status_uuid,
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
                await client.stop_notify(codec.TRANSPORT.status_uuid)
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
        self.forward_raw_notification(codec.TRANSPORT.status_uuid, payload)

        counts = codec.positions(payload)
        if counts is None:
            _LOGGER.debug(
                "Ignoring short PowerLayer status frame: expected %d bytes, got %d (%s)",
                codec.STATUS_LENGTH,
                len(payload),
                payload.hex(),
            )
            return

        head_raw, foot_raw = counts
        head_angle = raw_count_to_angle(head_raw, self.profile.head_angles)
        foot_angle = raw_count_to_angle(foot_raw, self.profile.foot_angles)

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
                data = await client.read_gatt_char(codec.TRANSPORT.status_uuid)
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

    async def _move(self, control: str) -> None:
        """Hold a movement key for the configured press, then release."""
        await self._move_with_stop(codec.command(self.profile.movement[control]))

    async def _send_once(self, key: int) -> None:
        """Send a latched key once.

        Presets and memory recalls are not watchdogged: the frame drives to the
        stored position on a single write, so repeating would re-trigger them.
        """
        await self.write_command(codec.command(key))

    # Motor control
    async def move_back_up(self) -> None:
        """Raise the head section."""
        await self._move("head_up")

    async def move_back_down(self) -> None:
        """Lower the head section."""
        await self._move("head_down")

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
        await self._move("foot_up")

    async def move_legs_down(self) -> None:
        """Lower the foot section."""
        await self._move("foot_down")

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
        await self._send_once(self.profile.presets["flat"])

    async def preset_zero_g(self) -> None:
        """Recall the zero-gravity position."""
        await self._send_once(self.profile.presets["zero_g"])

    async def preset_anti_snore(self) -> None:
        """Recall the anti-snore position."""
        await self._send_once(self.profile.presets["anti_snore"])

    async def preset_tv(self) -> None:
        """Recall the TV position."""
        await self._send_once(self.profile.presets["tv"])

    async def preset_memory(self, memory_num: int) -> None:
        """Recall a stored memory position."""
        key = self.profile.memory.get(memory_num)
        if key is None:
            raise ValueError("The PowerLayer remote only stores memory slots 1-3")
        await self._send_once(key)

    async def program_memory(self, memory_num: int) -> None:
        """Reject programming - the frame exposes no save command."""
        raise ValueError(
            "The PowerLayer has no BLE command to save a memory slot; "
            "hold M1, M2 or M3 on the physical remote instead"
        )
