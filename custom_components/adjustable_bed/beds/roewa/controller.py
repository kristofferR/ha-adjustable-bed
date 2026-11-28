"""Connection-owned RÖWA controls using the shared Okin N-frame family."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Final

from ...card import CARD_HIDDEN
from ...codec import okin_nframe as codec
from ...command_scheduler import note_frame_skipped
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid
from ...profiles import roewa as app
from ...state_keys import UNDER_BED_LIGHTS_ON
from ..base import BedController, require_controller
from ..builder import BuildContext
from ..catalog_buttons import Kind, catalog_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateBinarySensorSpec,
    MotorControlSpec,
    PositionNumberSpec,
)
from ..lifecycle import ControllerSession
from ..okin_64bit import Okin64BitController
from .transport import RoewaLink, read_identity, select_link

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

MEMORY_STORE: Final = StateKey[bool | None]("roewa_memory_store")


class _Released(Exception):
    """An admitted frame was released before dispatch."""


class RoewaController(Okin64BitController):
    """One action stream; every release stops refresh without a wire STOP."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, layout: str = app.DEFAULT_LAYOUT
    ) -> None:
        super().__init__(coordinator, char_uuid=app.WRITE_UUID, profile=app.PROFILES[layout])
        self._link: RoewaLink | None = None
        self._epoch = 0
        self._ready = False
        self._notifying = False
        self._subscription: object | None = None
        self._session_current: Callable[[], bool] = lambda: True
        self._model: str | None = None
        self._firmware: str | None = None

    @property
    def supports_preset_zero_g(self) -> bool:
        return False

    @property
    def supports_preset_anti_snore(self) -> bool:
        return False

    @property
    def supports_preset_tv(self) -> bool:
        return False

    @property
    def supports_preset_lounge(self) -> bool:
        return False

    @property
    def has_lumbar_support(self) -> bool:
        return False

    @property
    def supports_discrete_light_control(self) -> bool:
        return False

    @property
    def supports_light_state_feedback(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return self.profile.memory_slots

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def reconnect_for_explicit_stop(self) -> bool:
        return False

    @property
    def auto_stops_on_idle(self) -> bool:
        return True

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def supports_device_rename(self) -> bool:
        return True

    @property
    def device_rename_needs_live_validation(self) -> bool:
        return True

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {"layout": self.profile.key, "model": self._model, "firmware": self._firmware}

    def _live(self, expected: RoewaLink | None = None) -> RoewaLink:
        link = self._link
        if (
            link is None
            or expected is not None
            and link is not expected
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.controller is not self
            or not self._session_current()
        ):
            raise BedNotConnectedError()
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError()

        self._link = select_link(client)

    async def async_on_connect(self, session: ControllerSession) -> None:
        self._session_current = session.is_current
        link = self._live()
        # HA awaits setup and activation before admitting commands. Identity never selects a layout.
        self._firmware, self._model = await read_identity(
            link,
            is_current=lambda: self._live(link) is link,
        )
        session.store_device_info("RÖWA", self._model)
        await self.start_notify()
        await self._frame(link, app.INITIALIZE, asyncio.Event(), startup=True)
        self._live(link)
        self._ready = True

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._notifying:
            return
        token = object()
        self._subscription = token

        def receive(_: object, data: bytearray) -> None:
            if self._subscription is not token:
                return
            try:
                self._live(link)
            except BedNotConnectedError:
                return
            self.forward_raw_notification(app.FEEDBACK_UUID, bytes(data))
            mask = codec.parse_masked_feedback(bytes(data))
            if mask is not None:
                self.forward_controller_state_updates(
                    UNDER_BED_LIGHTS_ON(bool(mask & app.COMMON["light_toggle"])),
                    MEMORY_STORE(bool(mask & app.COMMON["memory_store"])),
                )

        await link.client.start_notify(link.feedback, receive)
        self._live(link)
        if self._subscription is not token:
            raise BedNotConnectedError()
        self._notifying = True

    def _clear_feedback(self) -> None:
        self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(None), MEMORY_STORE(None))

    async def stop_notify(self) -> None:
        link, notifying = self._link, self._notifying
        self._notifying = False
        self._subscription = None
        self.on_gesture_release()
        self._clear_feedback()
        if link is not None and notifying and link.client.is_connected:
            await link.client.stop_notify(link.feedback)

    def on_disconnect(self) -> None:
        self.on_gesture_release()
        self._link = None
        self._ready = self._notifying = False
        self._subscription = None
        self._session_current = lambda: True
        self._model = self._firmware = None
        self._clear_feedback()

    def on_app_state_replaced(self) -> None:
        self.on_disconnect()

    def on_gesture_release(self) -> None:
        self._epoch += 1

    def on_connection_release(self, reason: str) -> None:
        self.on_gesture_release()

    async def _frame(
        self,
        link: RoewaLink,
        frame: bytes,
        cancel: asyncio.Event,
        *,
        epoch: int | None = None,
        deadline: float | None = None,
        startup: bool = False,
        rename: bool = False,
        light_target: bool | None = None,
    ) -> None:
        def check() -> None:
            self._live(link)
            if not startup and not self._ready:
                raise BedNotConnectedError()
            if (
                epoch is not None
                and epoch != self._epoch
                or deadline is not None
                and asyncio.get_running_loop().time() >= deadline
            ):
                note_frame_skipped()
                raise _Released
            if rename:
                limit = self._rename_payload_limit(link)
                if len(frame) > limit:
                    raise invalid("roewa_name", limit=max(0, limit - 2))
            elif not startup and frame == self._build_command(app.COMMON["light_toggle"]):
                if light_target is not None:
                    state = self._coordinator.controller_state.get(UNDER_BED_LIGHTS_ON)
                    if not isinstance(state, bool):
                        raise invalid("light_state_unknown")
                    if state is light_target:
                        note_frame_skipped()
                        raise _Released
                # Dispatch makes the old sample stale. A notification during the
                # acknowledged write is newer evidence and must remain authoritative.
                self.forward_controller_state_update(UNDER_BED_LIGHTS_ON, None)

        char = link.rename if rename else link.write
        if char is None:
            raise BedNotConnectedError("roewa_rename_unavailable")
        await self._write_gatt_with_retry(
            char.uuid,
            frame,
            cancel_event=cancel,
            response=True,
            characteristic=char,
            expected_client=link.client,
            before_write=check,
            settle_write=True,
            write_timeout=15,
            track_command_write=not startup,
        )
        self._live(link)

    @staticmethod
    async def _pause(cancel: asyncio.Event, seconds: float) -> bool:
        try:
            await asyncio.wait_for(cancel.wait(), max(0, seconds))
        except TimeoutError:
            return cancel.is_set()
        return True

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = app.REFRESH_MS,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link, epoch = self._live(), self._epoch
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        try:
            for tick in range(repeat_count):
                if cancel.is_set() or tick and await self._pause(cancel, repeat_delay_ms / 1000):
                    return
                await self._frame(link, command, cancel, epoch=epoch)
        except _Released:
            return

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            key for key in self.profile.keys if key in (self.execution.hold_controls or ())
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise invalid(
                "held_control_not_supported",
                device_name=self._coordinator.name,
                control=control,
                valid_controls=", ".join(self.held_control_options),
            )
        if type(duration_ms) is not int or not 1 <= duration_ms <= 60000:
            raise invalid("roewa_hold_duration")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        link, epoch, cancel = self._live(), self._epoch, self._coordinator.cancel_command
        end = asyncio.get_running_loop().time() + self.leased_hold_ms(duration_ms) / 1000
        try:
            while asyncio.get_running_loop().time() < end and not cancel.is_set():
                await self._frame(
                    link,
                    self._build_command(self.profile.keys[control]),
                    cancel,
                    epoch=epoch,
                    deadline=end,
                )
                # Awaited write completion + 80 ms, with no catch-up writes.
                if await self._pause(
                    cancel, min(app.REFRESH_MS / 1000, end - asyncio.get_running_loop().time())
                ):
                    return
        except _Released:
            return
        finally:
            if self._epoch == epoch:
                self.on_gesture_release()

    async def _press(self, word: int, *, light_target: bool | None = None) -> None:
        key = next(key for key, value in self.profile.keys.items() if value == word)
        if key in self.held_control_options:
            await self.hold_control(key, self._coordinator.motor_pulse_count * app.REFRESH_MS)
        else:
            link, epoch, cancel = self._live(), self._epoch, self._coordinator.cancel_command
            try:
                await self._frame(
                    link, self._build_command(word), cancel, epoch=epoch,
                    light_target=light_target,
                )
            except _Released:
                return
            # Preserve one-shot admission while awaiting delivery, then the source's local latch.
            await self._pause(cancel, app.LATCH_MS / 1000)

    async def _send_stop(self) -> None:
        self.on_gesture_release()

    async def _move_with_stop(self, command: bytes) -> None:
        await self._press(codec.word_of(command))

    async def _move_axis(self, axis: str, direction: str) -> None:
        if axis not in self.profile.axes:
            raise self.not_supported(axis)
        await self._press(self.profile.keys[f"{axis}_{direction}"])

    async def move_head_up(self) -> None:
        await self._move_axis("head", "up")

    async def move_head_down(self) -> None:
        await self._move_axis("head", "down")

    async def move_back_up(self) -> None:
        await self._move_axis("back", "up")

    async def move_back_down(self) -> None:
        await self._move_axis("back", "down")

    async def move_legs_up(self) -> None:
        await self._move_axis("legs", "up")

    async def move_legs_down(self) -> None:
        await self._move_axis("legs", "down")

    async def move_feet_up(self) -> None:
        await self._move_axis("feet", "up")

    async def move_feet_down(self) -> None:
        await self._move_axis("feet", "down")

    # The shared family has other app commands; this route admits only its own keys.
    preset_zero_g = BedController.preset_zero_g
    preset_anti_snore = BedController.preset_anti_snore
    preset_tv = BedController.preset_tv
    preset_lounge = BedController.preset_lounge
    move_lumbar_up = BedController.move_lumbar_up
    move_lumbar_down = BedController.move_lumbar_down
    massage_toggle = BedController.massage_toggle
    massage_head_up = BedController.massage_head_up
    massage_head_down = BedController.massage_head_down
    massage_foot_up = BedController.massage_foot_up
    massage_mode_step = BedController.massage_mode_step

    async def lights_toggle(self) -> None:
        state = self._coordinator.controller_state.get(UNDER_BED_LIGHTS_ON)
        await self._press(
            app.COMMON["light_toggle"],
            light_target=not state if isinstance(state, bool) else None,
        )

    async def _set_light(self, on: bool) -> None:
        self._live()
        state = self._coordinator.controller_state.get(UNDER_BED_LIGHTS_ON)
        if not isinstance(state, bool):
            raise invalid("light_state_unknown")
        if state is not on:
            await self._press(app.COMMON["light_toggle"], light_target=on)

    async def lights_on(self) -> None:
        await self._set_light(True)

    async def lights_off(self) -> None:
        await self._set_light(False)

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._press(self.profile.keys[f"memory_{memory_num}"])

    async def recall_memory(self, slot: int, *, hold_ms: int) -> None:
        self.validate_memory_recall(slot)
        await self.hold_control(f"memory_{slot}", hold_ms)

    async def memory_store(self) -> None:
        await self._press(app.COMMON["memory_store"])

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        link, epoch = self._live(), self._epoch
        await self.memory_store()
        self._live(link)
        if epoch != self._epoch or self._coordinator.cancel_command.is_set():
            return
        await self.preset_memory(memory_num)

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        control = "flat" if key == "preset_flat" else key.removeprefix("preset_")
        return (
            ControllerHoldSpec(control, release_button_key="roewa_release")
            if control in self.held_control_options
            else None
        )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                axis,
                lambda c, a=axis: require_controller(c, RoewaController)._move_axis(a, "up"),
                lambda c, a=axis: require_controller(c, RoewaController)._move_axis(a, "down"),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                timed_move_fn=lambda c, up, ms, a=axis: c.hold_control(
                    f"{a}_{'up' if up else 'down'}", ms
                ),
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up",
                    f"{axis}_down",
                    stop_scope="side",
                    press_hold_ms=None,
                    press_is_native=True,
                    release_button_key="roewa_release",
                ),
            )
            for axis in self.profile.axes
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        store = catalog_button(
            "roewa_memory_store",
            "Enable memory storage",
            lambda c: require_controller(c, RoewaController).memory_store(),
            kind=Kind.SAVE,
            requires_confirmation=True,
        )
        assert store is not None
        return (
            replace(store, translation_key="roewa_memory_store", translation_placeholders=None),
            ControllerButtonSpec(
                "roewa_release",
                "Release held control",
                lambda c: c.stop_all(),
                translation_key="roewa_release",
                release_only=True,
                card=CARD_HIDDEN,
            ),
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (
            ControllerStateBinarySensorSpec(
                "roewa_memory_store",
                "roewa_memory_store",
                MEMORY_STORE,
                "mdi:content-save",
                entity_registry_enabled_default=True,
                entity_category=None,
            ),
        )

    def _rename_payload_limit(self, link: RoewaLink) -> int:
        self._live(link)
        if link.rename is None or select_link(link.client).rename is not link.rename:
            raise BedNotConnectedError("roewa_rename_unavailable")
        mtu = getattr(link.client, "mtu_size", 23)
        return min(512, (mtu if isinstance(mtu, int) else 23) - 3)

    def validate_device_rename(self, name: str) -> None:
        try:
            frame = app.rename_frame(name)
        except ValueError, UnicodeError:
            raise invalid("roewa_name", limit=510) from None
        limit = self._rename_payload_limit(self._live())
        if not name or len(frame) > limit:
            raise invalid("roewa_name", limit=limit - 2)

    async def rename_device(self, name: str) -> None:
        self.validate_device_rename(name)
        link, epoch = self._live(), self._epoch
        try:
            await self._frame(
                link,
                app.rename_frame(name),
                self._coordinator.cancel_command,
                epoch=epoch,
                rename=True,
            )
        except _Released:
            return


async def build_controller(ctx: BuildContext) -> BedController:
    layout = ctx.data.get("protocol_variant", app.DEFAULT_LAYOUT)
    if layout == "auto":
        layout = app.DEFAULT_LAYOUT
    if layout not in app.PROFILES:
        raise invalid("roewa_layout")
    return RoewaController(ctx.coordinator, layout)
