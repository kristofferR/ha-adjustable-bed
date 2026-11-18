"""The three Personal Comfort air sessions, without an invented pump STOP."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import asdict, replace
from functools import partial
from typing import TYPE_CHECKING, Final

from ...card import CardPlacement, CardSection
from ...codec import personal_comfort as codec
from ...controller_state import StateKey
from ...profiles.personal_comfort import PersonalComfortProfile
from ..base import BedController, ProfileExecution, require_controller
from ..entity_specs import ControllerNumberSpec, ControllerStateSensorSpec, MotorControlSpec
from .session import Owner, PersonalComfortSession

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

LEFT: Final = StateKey[int | None]("personal_comfort_left_firmness")
RIGHT: Final = StateKey[int | None]("personal_comfort_right_firmness")
ADJUSTMENT: Final = StateKey[str | None]("personal_comfort_adjustment")
FIRMNESS_KEYS: Final[tuple[tuple[codec.Side, StateKey[int | None]], ...]] = (
    ("left", LEFT),
    ("right", RIGHT),
)
# HA foreground ceilings, not firmware timing or an automatic pump STOP.
HYDRATION_TIMEOUT: Final = 10
ADJUSTMENT_TIMEOUT: Final = 120
RA_STATUS: Final = {
    0: "idle",
    32768: "error",
    **{
        value: f"{side}_{zone}_{direction}"
        for side, base in (("left", 3), ("right", 6))
        for index, zone in enumerate(("foot", "lumbar", "head"))
        for value, direction in ((base + index, "inflating"), ((base + index) * 256, "deflating"))
    },
}


async def _set(controller: BedController, value: float, *, side: codec.Side) -> None:
    await require_controller(controller, PersonalComfortAir).set_firmness(side, value)


class PersonalComfortAir(ProfileExecution[PersonalComfortProfile], PersonalComfortSession):
    def __init__(
        self, coordinator: AdjustableBedCoordinator, profile: PersonalComfortProfile
    ) -> None:
        super().__init__(coordinator)
        self.profile = profile
        self.values: dict[codec.Side, int | None] = {"left": None, "right": None}
        self.firmware: str | None = None
        self.status: int | None = None
        self._last_reply: codec.AirReply | None = None
        self._changed = asyncio.Event()
        self._notify_owner: Owner | None = None
        self._initial: asyncio.Task[None] | None = None
        self._preparing = False
        self._adjusting = False
        self._active = False
        self._acknowledged = True
        self._reply_version = 0
        self._followups: set[asyncio.Task[None]] = set()

    @property
    def control_characteristic_uuid(self) -> str:
        return self.profile.write

    @property
    def supports_motor_control(self) -> bool:
        return False

    @property
    def supports_stop_all(self) -> bool:
        return self.profile.key == "anm5"

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return ()

    @property
    def supports_memory_presets(self) -> bool:
        return False

    @property
    def supports_memory_programming(self) -> bool:
        return False

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        return tuple(
            ControllerNumberSpec(
                f"personal_comfort_{side}_firmness",
                f"personal_comfort_{side}_firmness",
                key,
                5,
                50,
                1,
                partial(_set, side=side),
                card=CardPlacement(CardSection.FIRMNESS),
            )
            for side, key in FIRMNESS_KEYS
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "personal_comfort_adjustment",
                "personal_comfort_adjustment",
                ADJUSTMENT,
                "mdi:air-filter",
                entity_registry_enabled_default=True,
                card=CardPlacement(CardSection.FIRMNESS),
            ),
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "route": self.profile.key,
            "firmware": self.firmware,
            "status": self.status,
            "preparing": self._preparing,
            "adjusting": self._adjusting,
            "pressure_reply": asdict(self._last_reply) if self._last_reply is not None else None,
        }

    def _publish(self) -> None:
        self.forward_controller_state_updates(
            LEFT(self.values["left"]), RIGHT(self.values["right"])
        )
        self._changed.set()

    def _schedule_refresh(self, delay: float, *, acknowledge: bool = False) -> None:
        # A notification is outside the completed command's cancellation
        # context. Its follow-up owns the current physical STOP epoch instead.
        owner = replace(self.capture(), cancel=asyncio.Event())

        async def refresh() -> None:
            try:
                await self.pause(owner, delay)

                async def query(controller: BedController) -> None:
                    if controller is not self:
                        return
                    self.check_owner(owner, cleanup=True)
                    if self._coordinator.stop_epoch != owner.stop_epoch:
                        return
                    current = replace(owner, cancel=self._coordinator.cancel_command)
                    if acknowledge:
                        await self.send(current, self.profile.write, codec.anm3(0x85))
                        await self.pause(current, 0.2)
                    await self.query(current)

                await self._coordinator.async_execute_controller_query(
                    query,
                    cancel_running=False,
                    preserve_idle_deadline=True,
                    run_if=lambda: (
                        self.client is owner.client
                        and self._generation == owner.generation
                        and self._coordinator.controller is self
                        and self._coordinator.stop_epoch == owner.stop_epoch
                    ),
                )
            except ConnectionError, asyncio.CancelledError:
                return

        task = self._coordinator.hass.async_create_task(refresh())
        self._followups.add(task)
        task.add_done_callback(self._followups.discard)

    def on_disconnect(self) -> None:
        super().on_disconnect()
        if self._initial is not None:
            self._initial.cancel()
        for task in self._followups:
            task.cancel()
        self.firmware = None
        self.values = {"left": None, "right": None}
        self.status = None
        self._last_reply = None
        self._preparing = self._adjusting = False
        self._changed.set()
        self._publish()
        self.forward_controller_state_update(ADJUSTMENT, None)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        del callback
        roles = [(self.profile.service, self.profile.write, "write")]
        assert self.profile.notify is not None and self.profile.notify_service is not None
        roles.append((self.profile.notify_service, self.profile.notify, "notify"))
        if self.profile.key == "ra":
            roles += [
                (codec.RA_SERVICE, characteristic, "write")
                for characteristic in codec.RA_WRITE.values()
            ]
            roles += [
                (codec.RA_SERVICE, characteristic, "read")
                for characteristic in codec.RA_READ.values()
            ]
            roles.append((codec.bluetooth_uuid("180a"), codec.bluetooth_uuid("2a26"), "read"))
        self.require_gatt(roles)
        owner = self.capture()
        self._notify_owner = owner

        def notify(_sender: BleakGATTCharacteristic, data: bytearray) -> None:
            try:
                self.check_owner(owner, cleanup=True)
            except ConnectionError:
                return
            self.receive(bytes(data))

        assert self.profile.notify is not None
        await owner.client.start_notify(self.profile.notify, notify)
        self.check_owner(owner)
        if self.profile.key != "ra":
            # Start the app's first current-value request before setup returns.
            # Only the one-second retries belong to the background session.
            await self.query(owner)
        self._initial = self._coordinator.hass.async_create_task(self._initialize(owner))

    async def stop_notify(self) -> None:
        self.on_disconnect()
        if self._initial is not None:
            await asyncio.gather(self._initial, return_exceptions=True)
            self._initial = None
        await asyncio.gather(*self._followups, return_exceptions=True)
        self._followups.clear()
        owner, self._notify_owner = self._notify_owner, None
        if owner is not None and owner.client.is_connected and self.profile.notify is not None:
            await owner.client.stop_notify(self.profile.notify)

    async def _initialize(self, owner: Owner) -> None:
        try:
            if self.profile.key == "ra":
                await self._read_firmware(owner)
                await self.query(owner)
            else:
                while all(value is None for value in self.values.values()):
                    await self.pause(owner, 1)
                    if all(value is None for value in self.values.values()):
                        await self.query(owner)
        except ConnectionError, asyncio.CancelledError:
            return

    async def _read_firmware(self, owner: Owner) -> None:
        while self.firmware is None:
            self.check_owner(owner)
            try:
                packet = await owner.client.read_gatt_char(codec.bluetooth_uuid("2a26"))
            except Exception:
                await self.pause(owner, 0.2)
                continue
            self.check_owner(owner)
            self.firmware = bytes(packet).decode("utf-8", errors="replace")

    async def _hydrate(self, owner: Owner, side: codec.Side) -> None:
        if self.values[side] is not None:
            return
        async with asyncio.timeout(HYDRATION_TIMEOUT):
            if self.profile.key == "ra":
                await self._read_firmware(owner)
            while self.values[side] is None:
                self.check_owner(owner)
                await self.query(owner, side)
                if self.values[side] is None:
                    await self._wait_change(owner, 1)

    async def query(self, owner: Owner, side: codec.Side | None = None) -> None:
        if self.profile.key == "anm3":
            await self.send(owner, self.profile.write, codec.anm3(0x83, side=3))
        elif self.profile.key == "anm5":
            for _ in range(2):
                await self.send(owner, self.profile.write, codec.anm5("select"))
                await self.pause(owner, 0.2)
            await self.send(owner, self.profile.write, codec.anm5("query"))
        else:
            if self.firmware is None:
                raise ValueError("Air unit firmware has not been read")
            pending: dict[codec.Side, str] = (
                codec.RA_READ if side is None else {side: codec.RA_READ[side]}
            )
            while pending:
                failed: dict[codec.Side, str] = {}
                for read_side, characteristic in pending.items():
                    self.check_owner(owner)
                    try:
                        packet = await owner.client.read_gatt_char(characteristic)
                    except Exception:
                        failed[read_side] = characteristic
                        continue
                    self.check_owner(owner)
                    self.values[read_side] = codec.ra_number(bytes(packet), self.firmware)
                    self._publish()
                pending = failed
                if pending:
                    await self.pause(owner, 0.5)

    def receive(self, packet: bytes) -> None:
        was_adjusting = self._adjusting
        if self.profile.key == "ra":
            self.status = codec.ra_status(packet)
            self._adjusting = self.status in RA_STATUS and self.status not in (0, 32768)
            if self.status is None:
                return
            self.forward_controller_state_update(ADJUSTMENT, RA_STATUS.get(self.status, "unknown"))
            if self.status == 0 and was_adjusting and not self._preparing and not self._active:
                self._schedule_refresh(0.2)
        else:
            reply = (
                codec.parse_anm3(packet) if self.profile.key == "anm3" else codec.parse_anm5(packet)
            )
            if reply is None:
                return
            self._last_reply = reply
            self.status = reply.status
            if self.profile.key == "anm3" or reply.status == 0:
                if reply.left is not None:
                    self.values["left"] = reply.left
                if reply.right is not None:
                    self.values["right"] = reply.right
                self._publish()
            if self.profile.key != "anm3":
                self._adjusting = reply.status != 0
            elif reply.status in (1, 2, 3):
                self._adjusting = True
            elif reply.status not in (0x69, 0x83, 0x88, 0x04, 0x92, 0x99):
                self._adjusting = False
            self.forward_controller_state_update(
                ADJUSTMENT,
                "busy"
                if self.profile.key == "anm3" and reply.status == 0x88
                else "adjusting"
                if self._adjusting
                else "idle",
            )
            if self.profile.key == "anm3":
                if self._adjusting:
                    self._acknowledged = False
                elif reply.status == 0x85 and not self._acknowledged:
                    self._acknowledged = True
                    if not self._active:
                        self._schedule_refresh(0, acknowledge=True)
        self._reply_version += 1
        self._changed.set()

    async def _wait_change(self, owner: Owner, seconds: float) -> bool:
        self._changed.clear()
        try:
            async with asyncio.timeout(seconds):
                await self._changed.wait()
        except TimeoutError:
            self.check_owner(owner)
            return False
        self.check_owner(owner)
        return True

    async def set_firmness(self, side: codec.Side, value: float) -> None:
        if not float(value).is_integer() or not 5 <= value <= 50:
            raise ValueError("Firmness must be an integer from 5 to 50")
        owner = self.capture()
        async with asyncio.timeout(ADJUSTMENT_TIMEOUT):
            # Reconnect startup may still be waiting for firmware or a reply.
            # Hydrate on this command's captured session, not its predecessor's event.
            await self._hydrate(owner, side)
            await self._adjust_firmness(owner, side, int(value))

    async def _adjust_firmness(self, owner: Owner, side: codec.Side, target: int) -> None:
        current = self.values[side]
        assert current is not None
        if target == current:
            return
        self._preparing = True
        self.status = None
        self._active = True
        try:
            if self.profile.key == "anm3":
                await self._set_anm3(owner, side, target, current)
            elif self.profile.key == "anm5":
                await self.send(owner, self.profile.write, codec.anm5("set", side, target))
                deadline = asyncio.get_running_loop().time() + 3
                next_query = asyncio.get_running_loop().time() + 0.5
                preparing = True
                saw_adjusting = False
                while True:
                    await self.pause(owner, max(0, next_query - asyncio.get_running_loop().time()))
                    await self.query(owner)
                    next_query += 0.5
                    saw_adjusting |= self._adjusting
                    if saw_adjusting:
                        preparing = False
                        self._preparing = False
                    if (saw_adjusting and not self._adjusting) or (
                        preparing and asyncio.get_running_loop().time() >= deadline
                    ):
                        break
            else:
                if self.firmware is None:
                    raise ValueError("Air unit firmware has not been read")
                await self.send(owner, codec.RA_WRITE[side], codec.ra(target))
                await self.pause(owner, 5)
                self._preparing = False
                await self.query(owner, side)
        finally:
            self._preparing = False
            self._active = False

    async def _set_anm3(self, owner: Owner, side: codec.Side, target: int, current: int) -> None:
        args = (target if side == "left" else 0, target, 3 if side == "left" else 2)
        ready = codec.anm3(0x69, *args)
        await self.send(owner, self.profile.write, ready)
        retries = 0
        busy_version = -1
        preparing_deadline = asyncio.get_running_loop().time() + 5
        while self.status != 0x69:
            if asyncio.get_running_loop().time() >= preparing_deadline:
                self._preparing = False
            if self.status == 0x88 and busy_version != self._reply_version:
                busy_version = self._reply_version
                if retries >= 3:
                    self._adjusting = False
                    return
                retries += 1
                await self.pause(owner, 1)
                await self.send(owner, self.profile.write, ready)
            else:
                await self._wait_change(owner, 1)
        self._adjusting = True
        self._acknowledged = False
        await self.send(owner, self.profile.write, codec.anm3(1 if target > current else 2, *args))
        retries = 0
        busy_version = -1
        while self.status != 0x85:
            if asyncio.get_running_loop().time() >= preparing_deadline:
                self._preparing = False
            if self.status == 0x88 and busy_version != self._reply_version:
                busy_version = self._reply_version
                if retries >= 3:
                    self._adjusting = False
                    return
                retries += 1
                await self.pause(owner, 1)
                await self.send(
                    owner, self.profile.write, codec.anm3(1 if target > current else 2, *args)
                )
            else:
                await self._wait_change(owner, 1)
        self._acknowledged = True
        await self.send(owner, self.profile.write, codec.anm3(0x85))
        await self.pause(owner, 0.2)
        await self.query(owner)

    async def stop_all(self) -> None:
        if self.profile.key == "anm5":
            owner = self.capture()
            await self.send(owner, self.profile.write, codec.anm5("stop"), cleanup=True)
            # STOP is pump-wide. A fresh post-STOP query owns its own current
            # cancellation epoch, rather than reviving the cancelled setter.
            fresh = self.capture()
            if not fresh.cancel.is_set():
                await self.pause(fresh, 0.5)
                await self.query(fresh)

    async def _unsupported(self) -> None:
        raise NotImplementedError("An air unit does not control base motors or presets")

    move_head_up = move_head_down = move_head_stop = _unsupported
    move_back_up = move_back_down = move_back_stop = _unsupported
    move_legs_up = move_legs_down = move_legs_stop = _unsupported
    move_feet_up = move_feet_down = move_feet_stop = _unsupported
    preset_flat = _unsupported

    async def preset_memory(self, memory_num: int) -> None:
        raise NotImplementedError("Air unit memories are local to the phone app")

    program_memory = preset_memory
