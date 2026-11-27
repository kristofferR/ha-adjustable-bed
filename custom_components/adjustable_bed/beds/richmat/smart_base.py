"""Smart Base's fixed A8RM panel over the shared Richmat motion/session runtime."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Mapping
from functools import partial
from typing import TYPE_CHECKING, Final

from ...card import CARD_LIGHT_TOGGLE, CARD_LIGHTING, CARD_PRESET_SAVE
from ...codec import richmat as codec
from ...command_scheduler import Delivery, delivered, note_frame_skipped
from ...const import CONF_PRODUCT_TYPE
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, failed, invalid
from ...profiles import smart_base as p
from ...state_keys import UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from ..base import BedController, require_controller
from ..cancellation import cancellable
from ..entity_specs import ControllerButtonSpec, ControllerNumberSpec, MotorControlSpec
from .atlas_lift import AtlasLiftController, _Link

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession

LAMP_SECONDS: Final = StateKey[int | None]("smart_base_lamp_seconds")


class SmartBaseController(AtlasLiftController):
    """One selected product, with optional settings admitted by this connection."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        if coordinator.entry.data.get(CONF_PRODUCT_TYPE) != p.PRODUCT:
            raise invalid("smart_base_product")
        super().__init__(coordinator, profile=p.PROFILE)
        self._is_current: Callable[[], bool] = lambda: False
        self._flags: set[str] = set()
        self._seconds: int | None = None

    @property
    def persisted_app_state_key(self) -> str:
        return "smart_base:" + p.PRODUCT

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {"lamp_seconds": self._seconds}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        value = state.get("lamp_seconds")
        if type(value) is int and 0 <= value <= 300:
            self._seconds = value
        # Restoring a local preference neither writes nor admits capabilities.

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "product": p.PRODUCT,
            "settings_flags": sorted(self._flags),
            "hardware": "UNVERIFIED",
        }

    def _current_link(self, expected: _Link | None = None) -> _Link:
        link = super()._current_link(expected)
        if not self._is_current():
            raise BedNotConnectedError
        return link

    async def async_on_connect(self, session: ControllerSession) -> None:
        self.on_disconnect()
        client = session.client
        if client is None or not session.is_current():
            raise BedNotConnectedError
        services = [s for s in client.services if s.uuid.lower() == p.SERVICE]
        if len(services) != 1:
            raise failed("smart_base_gatt")
        chars = services[0].characteristics
        tx = [c for c in chars if c.uuid.lower() == p.TX and "write" in c.properties]
        rx = [c for c in chars if c.uuid.lower() == p.RX and "notify" in c.properties]
        if len(tx) != 1 or len(rx) != 1:
            raise failed("smart_base_gatt")
        self._is_current = session.is_current
        self._link = link = _Link(client, tx[0], rx[0], False)
        try:
            await session.async_start_notify()
            await asyncio.sleep(p.STARTUP_MS / 1000)
            await self._write_on(link, p.INITIALIZE, asyncio.Event(), track_command_write=False)
        except BaseException:
            self.on_disconnect()
            raise

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._current_link()
        assert link.notify is not None

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._link is not link
                or not self._notifying
                or not self._is_current()
                or self.client is not link.client
                or not link.client.is_connected
            ):
                return
            value = bytes(data)
            self.forward_raw_notification(sender.uuid, value)
            if flag := p.FLAGS.get(value):
                self._flags.add(flag)
                if flag.startswith("led_"):
                    self.forward_controller_state_updates(
                        UNDER_BED_LIGHTS_ON(flag == "led_on"), LAMP_SECONDS(self._seconds)
                    )
                self.forward_controller_state_update(LAMP_SECONDS, self._seconds)

        async with self.ble_lock:
            if self._notifying:
                return
            self._notifying = True
            try:
                await link.client.start_notify(link.notify, receive)
                self._current_link(link)
            except BaseException:
                self._notifying = False
                raise

    async def stop_notify(self) -> None:
        try:
            await super().stop_notify()
        finally:
            self.on_disconnect()

    def on_disconnect(self) -> None:
        super().on_disconnect()
        self._is_current = lambda: False
        self._flags.clear()
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(None), UNDER_BED_LIGHTS_RGB(None), LAMP_SECONDS(None)
        )

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return False

    @property
    def auto_enable_massage(self) -> bool:
        return False

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                f"motor_{index}",
                f"motor_{index}",
                partial(self._motor, code=up),
                partial(self._motor, code=down),
                lambda c: c.stop_all(),
                stop_scope="side",
            )
            for index, (up, down) in enumerate(p.MOTORS, 1)
        )

    @staticmethod
    async def _motor(controller: BedController, *, code: int) -> None:
        await require_controller(controller, SmartBaseController)._move_with_stop(code)

    async def _release_on(self, link: _Link) -> None:
        await asyncio.sleep(p.HELD_RELEASE_MS / 1000)
        await super()._release_on(link)

    async def _tap(self, code: int) -> None:
        link = self._current_link()

        async def release() -> None:
            await asyncio.sleep(p.TAP_RELEASE_MS / 1000)
            await AtlasLiftController._release_on(self, link)

        async with self.releasing(release):
            await self._write_on(link, codec.command(code), self._coordinator.cancel_command)

    async def _recall(self, code: int) -> None:
        await self._tap(code)

    async def lights_toggle(self) -> None:
        await self._tap(self._code("light_toggle"))

    async def _save_zero_g(self) -> None:
        # Cancel before the proven threshold must never program the preset.
        await cancellable(asyncio.sleep(p.SAVE_MS / 1000), self._coordinator.cancel_command)
        await self._tap(self._code("save_zero_g"))

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def has_dynamic_buttons(self) -> bool:
        return True

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = [
            ControllerButtonSpec(
                "smart_base_save_zero_g",
                "Save zero gravity",
                lambda c: require_controller(c, SmartBaseController)._save_zero_g(),
                translation_key="catalog_save",
                translation_placeholders={"preset": "Zero gravity"},
                requires_confirmation=True,
                card=CARD_PRESET_SAVE,
                combine_sides=True,
            ),
            ControllerButtonSpec(
                "smart_base_light_toggle",
                "Toggle bed light",
                lambda c: c.lights_toggle(),
                translation_key="lights_toggle",
                card=CARD_LIGHT_TOGGLE,
                combine_sides=True,
            ),
            ControllerButtonSpec(
                "smart_base_query",
                "Refresh bed settings",
                lambda c: require_controller(c, SmartBaseController)._query(),
                translation_key="smart_base_query",
            ),
        ]
        if "alarm" in self._flags:
            specs.append(
                ControllerButtonSpec(
                    "smart_base_cancel_alarm",
                    "Cancel alarm",
                    lambda c: require_controller(c, SmartBaseController)._cancel_alarm(),
                    translation_key="smart_base_cancel_alarm",
                )
            )
        return tuple(specs)

    async def _query(self) -> None:
        link = self._current_link()
        cancel = self._coordinator.cancel_command
        for packet in p.QUERIES:
            await self._write_on(link, packet, cancel)
            await cancellable(asyncio.sleep(p.QUERY_MS / 1000), cancel)

    async def _cancel_alarm(self) -> None:
        link = self._current_link()
        if "alarm" not in self._flags:
            raise invalid("smart_base_settings")
        cancel = self._coordinator.cancel_command
        for packet in codec.countdown(0, 0):
            await self._write_on(link, packet, cancel)
            await cancellable(asyncio.sleep(p.ALARM_MS / 1000), cancel)

    @property
    def exposes_assumed_toggle_light(self) -> bool:
        return False

    @property
    def retain_live_controller_offline(self) -> bool:
        return True

    @property
    def retained_entity_keys(self) -> frozenset[tuple[str, str]]:
        return frozenset(
            {
                ("light", "under_bed_lights"),
                ("number", "controller_number_smart_base_lamp_seconds"),
                ("button", "smart_base_cancel_alarm"),
            }
        )

    def controller_button_available(self, key: str) -> bool:
        return key != "smart_base_cancel_alarm" or "alarm" in self._flags

    @property
    def unavailable_controller_entity_keys(self) -> tuple[str, ...]:
        return (
            ()
            if self.supports_light_color_control
            else ("under_bed_lights", "controller_number_smart_base_lamp_seconds")
        ) + (() if "alarm" in self._flags else ("smart_base_cancel_alarm",))

    @property
    def supports_light_toggle_control(self) -> bool:
        return True

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.supports_light_color_control

    @property
    def supports_light_color_control(self) -> bool:
        return bool(self._flags & {"led_on", "led_off"})

    @property
    def supported_color_mode(self) -> str | None:
        return "rgb" if self.supports_light_color_control else None

    @property
    def publishes_rgb_light_state(self) -> bool:
        return True

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        link = self._current_link()
        if (
            not self.supports_light_color_control
            or len(rgb_color) != 3
            or any(type(v) is not int or not 0 <= v <= 255 for v in rgb_color)
        ):
            raise invalid("smart_base_settings")
        cancel = self._coordinator.cancel_command
        with self.sent_state(
            UNDER_BED_LIGHTS_RGB(rgb_color),
            is_current=lambda: self._link is link and self._is_current(),
        ):
            await self._write_on(link, codec.rgb(*rgb_color), cancel)
            await cancellable(asyncio.sleep(p.TICK_MS / 1000), cancel)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if not self.supports_light_color_control:
            return ()
        return (
            ControllerNumberSpec(
                "smart_base_lamp_seconds",
                "smart_base_lamp_seconds",
                LAMP_SECONDS,
                0,
                300,
                1,
                lambda c, value: require_controller(c, SmartBaseController)._set_seconds(value),
                "s",
                card=CARD_LIGHTING,
            ),
        )

    async def _set_seconds(self, value: float) -> None:
        link = self._current_link()
        if (
            not self.supports_light_color_control
            or not math.isfinite(value)
            or not 0 <= value <= 300
            or int(value) != value
        ):
            raise invalid("smart_base_settings")
        cancel = self._coordinator.cancel_command
        if cancel.is_set():
            note_frame_skipped()
            return
        seconds = int(value)
        encoded = seconds or 0xFFFF

        def remember(delivery: Delivery) -> None:
            if delivery is Delivery.SENT and self._link is link and self._is_current():
                self._seconds = seconds

        with (
            self.sent_state(
                LAMP_SECONDS(seconds), is_current=lambda: self._link is link and self._is_current()
            ),
            delivered(remember),
        ):
            await self._write_on(
                link,
                codec.light_timer(encoded >> 8, encoded & 255),
                cancel,
            )
