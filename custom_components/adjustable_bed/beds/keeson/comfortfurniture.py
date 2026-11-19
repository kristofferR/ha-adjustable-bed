"""ComfortFurniture's fixed BED pages, over the shared ORE Keeson transport.

ComfortFurniture 2.3 establishes intended bytes and local app effects,
not captures or physical reset/bin meanings. HA owns serialization, immutable
writes and cancellation cleanup instead of copying the app's mutable queue.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...card import (
    CARD_MASSAGE,
    CARD_PRESETS,
    CARD_UTILITY,
)
from ...codec.keeson import comfortfurniture_cancels_hold
from ...const import KEESON_BASE_NOTIFY_CHAR_UUID, KEESON_VARIANT_COMFORTFURNITURE
from ...controller_state import StateKey
from ...profiles.comfortfurniture import PROFILE
from ...state_keys import MASSAGE_TIMER_MINUTES
from ..base import BedController
from ..catalog_buttons import save_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSwitchSpec,
    MotorCommandCallable,
    MotorControlSpec,
)
from ..ore_comfort_bed import OreComfortBedController, _axis_command

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

# The app's sliders send three bins (progress 0-9, 10-19, 20-29); entities show bins 1-3.
LEVEL: Final = {s: StateKey[int | None](f"comfortfurniture_{s}_level") for s in PROFILE.slider_bases}
# The shared massage timer select reads this; the bed reports no timer.
TIMER: Final = MASSAGE_TIMER_MINUTES
SAVE_LABELS: Final = {
    "zero_g": "Save zero-gravity position",
    "flat": "Save flat position",
    "anti_snore": "Save anti-snore position",
    "reading": "Save reading position",
}


@dataclass(frozen=True)
class _Target:
    client: BleakClient
    characteristic: BleakGATTCharacteristic
    response: bool
    generation: int
    cancel: asyncio.Event


class ComfortFurnitureController(OreComfortBedController):
    """All five BED pages; four real axes and the explicit back+foot control."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, app=KEESON_VARIANT_COMFORTFURNITURE)
        self._axes = dict(PROFILE.axes)
        self._progress = dict.fromkeys(PROFILE.slider_bases, PROFILE.slider_default)
        self._selected_preset: str | None = None
        self._generation = 0
        self._notify_char: BleakGATTCharacteristic | None = None
        self._notify_client: BleakClient | None = None
        self._held_cancel: asyncio.Event | None = None

    def _capture_target(self) -> _Target:
        client = self.client
        if client is None or not client.is_connected or self._coordinator.controller is not self:
            raise ConnectionError("ComfortFurniture controller no longer owns this BLE session")
        characteristic = self._resolve_write_characteristic()
        return _Target(
            client,
            characteristic,
            self._write_with_response,
            self._generation,
            self._coordinator.cancel_command,
        )

    def _current(self, target: _Target) -> bool:
        return (
            self.client is target.client
            and target.client.is_connected
            and self._coordinator.controller is self
            and self._generation == target.generation
        )

    def _check_target(self, target: _Target) -> None:
        if not self._current(target):
            raise ConnectionError("ComfortFurniture command belongs to a previous BLE session")

    async def _write_word(self, target: _Target, word: int, *, cleanup: bool = False) -> None:
        self._check_target(target)
        await self._write_gatt_with_retry(
            str(target.characteristic.uuid),
            self._frame(word),
            cancel_event=asyncio.Event() if cleanup else target.cancel,
            response=target.response,
            characteristic=target.characteristic,
            expected_client=target.client,
            before_write=lambda: self._check_target(target),
        )

    async def _send_words(self, *words: int) -> None:
        # Capture the physical connection before the first pre-send wait.
        target = self._capture_target()
        for word in words:
            if target.cancel.is_set():
                raise asyncio.CancelledError
            await asyncio.sleep(self.profile.tap_wait_ms / 1000)
            await self._write_word(target, word)
            self._check_target(target)
            if target.cancel.is_set():
                raise asyncio.CancelledError

    async def _send_single(self, word: int) -> None:
        await self._send_words(word)

    async def _release(self, target: _Target) -> None:
        ((wait_ms, word),) = self.profile.release.steps
        assert isinstance(word, int)
        try:
            await asyncio.sleep(wait_ms / 1000)
        finally:
            # A delayed old cleanup must never stop a replacement receiver/session.
            if self._current(target):
                await self._write_word(target, word, cleanup=True)

    async def _send_release(self) -> None:
        await self._release(self._capture_target())

    async def _hold(self, word: int, *, duration_ms: int | None = None) -> None:
        target = self._capture_target()
        self._selected_preset = None
        count, refresh_ms = self.motor_pulse_settings()
        interval = refresh_ms / 1000
        deadline = (
            asyncio.get_running_loop().time()
            + self.leased_hold_ms(count * refresh_ms if duration_ms is None else duration_ms) / 1000
        )
        self._held_cancel = target.cancel
        budget = asyncio.timeout_at(deadline)
        try:
            async with budget:
                while not target.cancel.is_set() and asyncio.get_running_loop().time() < deadline:
                    await self._write_word(target, word)
                    # Always wait after the write. Slow BLE never produces catch-up bursts.
                    await asyncio.sleep(interval)
        except TimeoutError:
            if not budget.expired():
                raise
        finally:
            self._held_cancel = None
            await self._release(target)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key=axis,
                translation_key=axis,
                open_fn=_axis_command(axis, True),
                close_fn=_axis_command(axis, False),
                stop_fn=lambda ctrl: ctrl.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up",
                    f"{axis}_down",
                    release_delay_ms=100,
                    stop_scope="side",
                    press_hold_ms=None,
                ),
            )
            for axis in PROFILE.axes
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(f"{axis}_{direction}" for axis in PROFILE.axes for direction in ("up", "down"))

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or duration_ms <= 0:
            raise ValueError("Invalid ComfortFurniture held control or duration")
        axis, direction = control.rsplit("_", 1)
        await self._hold(PROFILE.axes[axis][direction == "down"], duration_ms=duration_ms)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Subscribe through HA; the app itself enables locally without a CCCD write.

        The peripheral's actual subscription requirement is unverified. No setup
        command, ACK, position parser or service UUID is inferred from this.
        """
        if self._notify_client is self.client and self._notify_char is not None:
            return
        target = self._capture_target()
        notify: BleakGATTCharacteristic | None = None
        for service in target.client.services:
            for char in service.characteristics:
                if str(char.uuid).lower() == KEESON_BASE_NOTIFY_CHAR_UUID:
                    notify = char
        assert notify is not None  # The shared transport requires both roles.

        def received(_sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if not self._current(target):
                return
            self.forward_raw_notification(KEESON_BASE_NOTIFY_CHAR_UUID, bytes(data))
            if comfortfurniture_cancels_hold(bytes(data)) and self._held_cancel is not None:
                self._held_cancel.set()

        await target.client.start_notify(notify, received)
        self._check_target(target)
        self._notify_client, self._notify_char = target.client, notify
        self._publish_progress()

    async def stop_notify(self) -> None:
        client, char = self._notify_client, self._notify_char
        self.on_disconnect()
        if client is not None and char is not None and client.is_connected:
            await client.stop_notify(char)

    def on_disconnect(self) -> None:
        self._generation += 1
        if self._held_cancel is not None:
            self._held_cancel.set()
        self._held_cancel = None
        self._notify_char = self._notify_client = self._write_char = None
        self._selected_preset = None
        self.forward_controller_state_updates(TIMER(None))

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def has_lumbar_support(self) -> bool:
        return False  # Waist retains the app label; no extra lumbar motor.

    async def stop_all(self) -> None:
        if self._selected_preset is not None:
            await self.stop_preset()
        else:
            await self._send_release()

    async def recall_named(self, name: str) -> None:
        word = PROFILE.recalls[name]
        if self._selected_preset == name:
            await self.stop_preset()
        else:
            previous, self._selected_preset = self._selected_preset, name
            try:
                await self._send_single(word)
            except Exception:
                # A rejected write leaves the earlier selection; a cancelled one keeps this preset.
                self._selected_preset = previous
                raise

    async def stop_preset(self) -> None:
        # Preset STOP is a different proven word from movement release.
        target = self._capture_target()
        try:
            await asyncio.sleep(self.profile.tap_wait_ms / 1000)
        finally:
            if self._current(target):
                await self._write_word(target, PROFILE.preset_stop, cleanup=True)
        self._selected_preset = None

    async def save_named(self, name: str) -> None:
        await self._send_single(PROFILE.saves[name])
        self._selected_preset = None

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_reading(self) -> bool:
        return True

    async def preset_flat(self) -> None:
        await self.recall_named("flat")

    async def preset_zero_g(self) -> None:
        await self.recall_named("zero_g")

    async def preset_anti_snore(self) -> None:
        await self.recall_named("anti_snore")

    async def preset_reading(self) -> None:
        await self.recall_named("reading")

    @property
    def memory_slot_count(self) -> int:
        return 1

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        return ("Memory",)

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num != 1:
            raise ValueError("ComfortFurniture has one Memory target")
        await self.recall_named("memory")

    async def program_memory(self, memory_num: int) -> None:
        if memory_num != 1:
            raise ValueError("ComfortFurniture has one Memory target")
        await self.save_named("memory")

    async def program_flat(self) -> None:
        await self.save_named("flat")

    async def program_zero_g(self) -> None:
        await self.save_named("zero_g")

    async def set_massage_progress(self, slider: str, progress: int) -> None:
        word = PROFILE.slider_word(slider, progress)
        self._progress[slider] = progress
        self._publish_progress()
        await self._send_single(word)

    async def set_massage_level(self, zone: str, level: int) -> None:
        if type(level) is not int or not 0 <= level <= 2:
            raise ValueError("ComfortFurniture massage bins are 0..2; bin 0 is not off")
        await self.set_massage_progress(zone, level * 10)

    async def massage_start(self) -> None:
        await self._send_words(
            PROFILE.massage_start,
            *(PROFILE.slider_word(s, self._progress[s]) for s in ("wave", "intensity")),
        )

    async def massage_off(self) -> None:
        await self._send_single(PROFILE.massage_stop)
        self.forward_controller_state_updates(TIMER(None))

    async def set_massage_timer_option(self, option: str) -> None:
        if option not in PROFILE.timers:
            raise ValueError(f"Invalid massage timer {option}")
        await self._send_single(PROFILE.timers[option])
        self.forward_controller_state_updates(TIMER(int(option)))

    @property
    def massage_timer_options(self) -> list[int]:
        return [int(option) for option in PROFILE.timers]

    @property
    def persisted_app_state(self) -> Mapping[str, Any] | None:
        return dict(self._progress)

    def restore_persisted_app_state(self, state: Mapping[str, Any]) -> None:
        if set(state) - set(PROFILE.slider_bases):
            raise ValueError("Unknown ComfortFurniture slider")
        progress = {s: state.get(s, PROFILE.slider_default) for s in PROFILE.slider_bases}
        for slider, value in progress.items():
            PROFILE.slider_word(slider, value)
        self._progress = progress
        self._publish_progress()

    def _publish_progress(self) -> None:
        self.forward_controller_state_updates(
            *(LEVEL[s](p // 10 + 1) for s, p in self._progress.items())
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        return tuple(
            ControllerNumberSpec(
                key=f"comfortfurniture_{s}_level",
                translation_key=f"comfortfurniture_{s}_level",
                state_key=LEVEL[s],
                native_min_value=1,
                native_max_value=3,
                native_step=1,
                set_fn=_level_setter(s),
                card=CARD_MASSAGE,
            )
            for s in PROFILE.slider_bases
        )

    @property
    def supports_massage_off_control(self) -> bool:
        return False  # The massage switch sends start and off.

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        return (
            ControllerSwitchSpec(
                "comfortfurniture_massage",
                "comfortfurniture_massage",
                _set_massage,
                icon="mdi:vibrate",
                card=CARD_MASSAGE,
            ),
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        # The massage timer select replaces the app's timer-cycle key. Stop preset stays:
        # Stop only sends preset stop for a preset this BLE session started.
        return (
            *(
                save_button(
                    f"comfortfurniture_save_{name}",
                    label,
                    _save_named(name),
                    icon="mdi:content-save",
                )
                for name, label in SAVE_LABELS.items()
            ),
            ControllerButtonSpec(
                "comfortfurniture_preset_stop",
                "Stop preset",
                lambda ctrl: cast(ComfortFurnitureController, ctrl).stop_preset(),
                icon="mdi:stop",
                translation_key="comfortfurniture_preset_stop",
                card=CARD_PRESETS,
            ),
            ControllerButtonSpec(
                "comfortfurniture_reset",
                "Reset",
                lambda ctrl: cast(ComfortFurnitureController, ctrl)._send_single(
                    PROFILE.reset_label
                ),
                icon="mdi:alert-outline",
                translation_key="comfortfurniture_reset",
                requires_confirmation=True,
                # Its physical effect is unknown, so it is not a dashboard control.
                diagnostic=True,
                card=CARD_UTILITY,
            ),
        )

    @property
    def protocol_diagnostics(self) -> dict[str, Any]:
        return {
            "app": self._app.name,
            "app_package": f"{self._app.package} {self._app.version}",
            "layout": "bedding: back, foot, head, waist and back+foot",
            "hardware": "UNVERIFIED",
            "subscription": "HA subscription; app local-only, peripheral requirement unverified",
        }


def _level_setter(slider: str) -> Callable[[BedController, float], Awaitable[None]]:
    async def set_level(ctrl: BedController, value: float) -> None:
        if int(value) != value:
            raise ValueError("ComfortFurniture massage level must be an integer")
        await cast(ComfortFurnitureController, ctrl).set_massage_level(slider, int(value) - 1)

    return set_level


async def _set_massage(ctrl: BedController, on: bool) -> None:
    controller = cast(ComfortFurnitureController, ctrl)
    await (controller.massage_start() if on else controller.massage_off())


def _save_named(name: str) -> MotorCommandCallable:
    async def save(ctrl: BedController) -> None:
        await cast(ComfortFurnitureController, ctrl).save_named(name)

    return save
