"""Controllers over the Jiecang codec.

``JiecangProfileController`` is the glue every Jiecang profile shares: it
drives held movement, stop, presets and memory from a ``JiecangProfile``.
``JiecangController`` is the legacy route of the ``jiecang`` and
``comfort_motion`` bed types, from smartbed-mqtt reverse engineering.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ..codec import jiecang as codec
from ..const import JIECANG_CHAR_UUID
from ..profiles.jiecang import (
    LEGACY,
    JiecangProfile,
    Layout,
    NameRule,
    Schedule,
    Tap,
    light_toggle_command,
    memory_command,
    motion_command,
    preset_command,
)
from .base import BedController, MotorControlSpec

if TYPE_CHECKING:
    from ..codec.jiecang import Axis, Preset
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class JiecangProfileController(BedController):
    """Drive the Jiecang codec from a profile; subclasses select the transport."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        profile: JiecangProfile,
        layout: Layout | None = None,
    ) -> None:
        super().__init__(coordinator)
        if profile.layouts and layout not in profile.layouts:
            raise ValueError(f"Layout {layout} is unavailable for the {profile.key} profile")
        self.profile = profile
        self.layout: Layout | None = layout
        self._write_uuid = ""

    def _select_transport(self) -> None:
        """Set ``_write_uuid`` and the write mode from the discovered GATT roles."""
        raise NotImplementedError

    @property
    def control_characteristic_uuid(self) -> str:
        return self._write_uuid

    @property
    def _name_rule(self) -> NameRule:
        if self.profile.name_rule is None:
            raise ValueError("This profile cannot rename the bed")
        return self.profile.name_rule

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write once per application action, without inventing ACK or retry packets."""
        if self.client is None or not self.client.is_connected:
            raise ConnectionError("Not connected to bed")
        if not self._write_uuid:
            self._select_transport()
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        self._record_command_trace(
            self._write_uuid,
            command,
            response=self._write_with_response,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
        )
        loop = asyncio.get_running_loop()
        started = loop.time()
        for index in range(repeat_count):
            if index:
                delay: float = repeat_delay_ms
                if self.profile.fixed_rate:
                    delay = index * repeat_delay_ms - (loop.time() - started) * 1000
                if await self._pause(delay, cancel):
                    return
            elif cancel.is_set():
                return
            async with self._ble_lock:
                await self.client.write_gatt_char(
                    self._write_uuid, command, response=self._write_with_response
                )

    @staticmethod
    async def _pause(milliseconds: float, cancel: asyncio.Event) -> bool:
        """Wait, returning True early when the running action is stopped."""
        if cancel.is_set():
            return True
        if milliseconds <= 0:
            return False
        try:
            await asyncio.wait_for(cancel.wait(), milliseconds / 1000)
        except TimeoutError:
            return False
        return True

    async def _schedule(self, schedule: Schedule, *, cleanup: bool = False) -> bool:
        """Send frames at absolute offsets. Cleanup cannot be cancelled."""
        cancel = asyncio.Event() if cleanup else self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        started = loop.time()
        for offset, command in schedule:
            if await self._pause(offset - (loop.time() - started) * 1000, cancel):
                return False
            await self.write_command(command, cancel_event=cancel)
        return not cancel.is_set()

    async def _tap(self, command: bytes, tap: Tap) -> None:
        try:
            await self.write_command(command, tap.repeats, tap.repeat_ms)
            if tap.release is not None:
                await self._pause(tap.release_after_ms, self._coordinator.cancel_command)
        finally:
            if tap.release is not None:
                await self.write_command(tap.release, cancel_event=asyncio.Event())

    # Movement

    @property
    def supports_motor_control(self) -> bool:
        return True

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        if self.layout is None:
            return super().motor_control_specs

        def spec(axis: Axis) -> MotorControlSpec:
            return MotorControlSpec(
                key=axis,
                translation_key="back_legs" if axis == "both" else axis,
                open_fn=lambda ctrl: JiecangProfileController._dispatch_axis(ctrl, axis, True),
                close_fn=lambda ctrl: JiecangProfileController._dispatch_axis(ctrl, axis, False),
                stop_fn=lambda ctrl: ctrl.stop_all(),
            )

        return tuple(spec(axis) for axis in self.profile.layouts[self.layout])

    @staticmethod
    async def _dispatch_axis(controller: BedController, axis: Axis, up: bool) -> None:
        """A retained entity spec must operate on the newly connected controller."""
        if not isinstance(controller, JiecangProfileController):
            raise ValueError("Motor controls require the configured Jiecang profile")
        await controller._move_axis(axis, up)

    async def _move_axis(self, axis: Axis, up: bool) -> None:
        if self.layout is not None:
            command = motion_command(self.profile, self.layout, axis, up)
        elif axis in ("back", "legs"):
            # The motor-count layout drives only the back and legs motors.
            command = codec.motion(axis, up)
        else:
            raise NotImplementedError(f"{axis} motor not supported on this bed")
        hold = self.profile.hold
        cancel = self._coordinator.cancel_command
        # A leased hold refreshes at the app's interval until its lease ends.
        leased = self.leased_hold_refreshes(hold.repeat_ms)
        try:
            await self.write_command(
                command,
                leased or hold.repeats or self._coordinator.motor_pulse_count,
                hold.repeat_ms,
            )
            # A cancelled action never restarts movement to imitate the app,
            # and neither does a leased hold that reached its ceiling.
            if hold.final_frame and not cancel.is_set() and leased is None:
                await self.write_command(command)
        finally:
            await self._schedule(hold.releases, cleanup=True)

    async def stop_all(self) -> None:
        # An explicit stop has no release delay before its first frame.
        releases = self.profile.hold.releases
        await self._schedule(
            tuple((offset - releases[0][0], command) for offset, command in releases),
            cleanup=True,
        )

    async def move_back_up(self) -> None:
        await self._move_axis("back", True)

    async def move_back_down(self) -> None:
        await self._move_axis("back", False)

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_head_up(self) -> None:
        await self._move_axis("head", True)

    async def move_head_down(self) -> None:
        await self._move_axis("head", False)

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self._move_axis("legs", True)

    async def move_legs_down(self) -> None:
        await self._move_axis("legs", False)

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    # Presets and memory

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return self.profile.memory_slots

    async def _preset(self, preset: Preset) -> None:
        await self._tap(preset_command(self.layout, preset), self.profile.recall)

    async def preset_flat(self) -> None:
        await self._preset("flat")

    async def preset_zero_g(self) -> None:
        await self._preset("zero_g")

    async def preset_anti_snore(self) -> None:
        await self._preset("anti_snore")

    async def preset_memory(self, memory_num: int) -> None:
        await self._tap(memory_command(self.profile, memory_num), self.profile.recall)

    async def program_memory(self, memory_num: int) -> None:
        await self._tap(
            memory_command(self.profile, memory_num, save=True), self.profile.memory_save
        )


class JiecangController(JiecangProfileController):
    """Legacy route: fixed back/legs axes, three memory slots and 0-10 massage."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, LEGACY)
        self._select_transport()
        self._massage_back_level = 0
        self._massage_leg_level = 0
        _LOGGER.debug(
            "JiecangController initialized with control characteristic %s", self._write_uuid
        )

    def _select_transport(self) -> None:
        """Prefer G3, then G1, else the generic write characteristic. Always with response."""
        self._write_uuid = JIECANG_CHAR_UUID
        services = self.client.services if self.client is not None else None
        if services is None:
            return
        for key in self.profile.transports:
            transport = codec.TRANSPORTS[key]
            service = services.get_service(transport.service_uuid)
            if service is not None and service.get_characteristic(transport.write_uuid):
                self._write_uuid = transport.write_uuid
                return

    # The legacy head and feet controls drive the back and legs motors.
    async def move_head_up(self) -> None:
        await self._move_axis("back", True)

    async def move_head_down(self) -> None:
        await self._move_axis("back", False)

    async def preset_memory(self, memory_num: int) -> None:
        if 1 <= memory_num <= self.profile.memory_slots:
            await super().preset_memory(memory_num)
        else:
            _LOGGER.warning("Jiecang beds support memory presets 1-3 only")

    async def program_memory(self, memory_num: int) -> None:
        if 1 <= memory_num <= self.profile.memory_slots:
            await super().program_memory(memory_num)
        else:
            _LOGGER.warning("Jiecang beds support memory presets 1-3 only")

    @property
    def supports_lights(self) -> bool:
        return True

    async def lights_toggle(self) -> None:
        await self.write_command(light_toggle_command(self.profile))

    async def massage_toggle(self) -> None:
        if self._massage_back_level > 0 or self._massage_leg_level > 0:
            await self.write_command(codec.massage_stop())
            self._massage_back_level = 0
            self._massage_leg_level = 0
        else:
            await self.write_command(codec.massage_start())

    async def massage_mode_step(self) -> None:
        await self.write_command(codec.massage_mode())

    async def massage_off(self) -> None:
        self._massage_back_level = 0
        self._massage_leg_level = 0
        await self.write_command(codec.massage("back", 0))
        await self.write_command(codec.massage("legs", 0))

    async def massage_head_up(self) -> None:
        self._massage_back_level = min(10, self._massage_back_level + 1)
        await self.write_command(codec.massage("back", self._massage_back_level))

    async def massage_head_down(self) -> None:
        self._massage_back_level = max(0, self._massage_back_level - 1)
        await self.write_command(codec.massage("back", self._massage_back_level))

    async def massage_foot_up(self) -> None:
        self._massage_leg_level = min(10, self._massage_leg_level + 1)
        await self.write_command(codec.massage("legs", self._massage_leg_level))

    async def massage_foot_down(self) -> None:
        self._massage_leg_level = max(0, self._massage_leg_level - 1)
        await self.write_command(codec.massage("legs", self._massage_leg_level))
