"""Dreamotion Smart's local records on the shared Jiecang movement interface."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...card import CARD_LIGHTING, CARD_MASSAGE, CARD_PRESETS, CARD_UTILITY
from ...codec import jiecang as codec
from ...command_scheduler import note_frame_skipped, note_frame_written
from ...controller_state import StateKey
from ...profiles import dreamotion_smart as app
from ...profiles.jiecang import Schedule
from ...state_keys import LIGHT_LEVEL, UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from ..base import BedController, require_controller
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from .controller import JiecangProfileController

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

SENSOR_ENABLED: Final = StateKey[bool | None]("dreamotion_smart_sensor_enabled")
MODE: Final = StateKey[str | None]("dreamotion_smart_mode")
BACK: Final = StateKey[int | None]("dreamotion_smart_back")
FOOT: Final = StateKey[int | None]("dreamotion_smart_foot")
PATTERN: Final = StateKey[int | None]("dreamotion_smart_pattern")
TIMER: Final = StateKey[int | None]("dreamotion_smart_timer")
SECONDS: Final = StateKey[int | None]("dreamotion_smart_seconds")
PAGE: Final = StateKey[str | None]("dreamotion_smart_page")
SLOT: Final = StateKey[str | None]("dreamotion_smart_slot")


@dataclass(frozen=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    response: bool


class DreamotionSmartController(JiecangProfileController):
    """One explicit app, with session-owned writes and notification state."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, app.PROFILE)
        self._link: _Link | None = None
        self._notifying = False
        self._massage = app.Massage()
        self._massage_known = False
        self._mode_known = False
        self._timed: tuple[app.Color, int] | None = None
        self._colors: tuple[app.Color, app.Color, app.Color] | None = None
        page = coordinator.controller_state.get(PAGE)
        slot = coordinator.controller_state.get(SLOT)
        self._page = page if isinstance(page, str) and page in ("timed", "presets") else "timed"
        self._slot = int(slot) if isinstance(slot, str) and slot in ("1", "2", "3") else 1
        self.forward_controller_state_updates(PAGE(self._page), SLOT(str(self._slot)))

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app": "com.sendinfo.dreammotionpro 1.1.8",
            "hardware": "UNVERIFIED",
            "write_response": self._link.response if self._link else None,
        }

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def requires_linked_live_readiness(self) -> bool:
        return True

    async def async_validate_linked_readiness(self) -> None:
        self._live()
        if not self._notifying:
            raise ConnectionError("Dreamotion Smart notification channel is not ready")

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def has_neck_support(self) -> bool:
        return True

    def _live(self, expected: _Link | None = None) -> _Link:
        link = self._link
        if (
            link is None
            or expected is not None
            and link is not expected
            or self.client is not link.client
            or not link.client.is_connected
        ):
            raise ConnectionError("Dreamotion Smart BLE session changed or disconnected")
        return link

    def _select_transport(self) -> None:
        """Use concrete GATT roles, never Android's mutable callback address.

        The app matches case-folded substrings. HA accepts exactly one matching
        service and role, and selects response mode from actual properties.
        """
        client = self.client
        if client is None:
            raise ConnectionError("Dreamotion Smart is not connected")
        services = [s for s in client.services if "fe60" in s.uuid.lower()]
        if len(services) != 1:
            raise ValueError("Dreamotion Smart requires one unambiguous FE60 service")
        writes = [c for c in services[0].characteristics if "fe61" in c.uuid.lower()]
        notifies = [c for c in services[0].characteristics if "fe62" in c.uuid.lower()]
        if (
            len(writes) != 1
            or len(notifies) != 1
            or not {"write", "write-without-response"}.intersection(writes[0].properties)
            or not {"notify", "indicate"}.intersection(notifies[0].properties)
        ):
            raise ValueError(
                "Dreamotion Smart requires unambiguous writable FE61 and notifying FE62 roles"
            )
        self._link = _Link(client, writes[0], notifies[0], "write" in writes[0].properties)
        self._write_uuid = writes[0].uuid

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        self._select_transport()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        if self._notifying:
            self._live()
            return
        if self._link is None:
            self._select_transport()
        link = self._live()

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._link is not link
                or self.client is not link.client
                or not link.client.is_connected
            ):
                return
            self.forward_raw_notification(sender.uuid, bytes(data))
            self._receive(bytes(data))

        async with self._ble_lock:
            self._live(link)
            await link.client.start_notify(link.notify, receive)
            self._live(link)
            self._notifying = True

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()
        await self.refresh_state()

    def on_disconnect(self) -> None:
        self._link = None
        self._notifying = False
        self._massage = app.Massage()
        self._massage_known = self._mode_known = False
        self._timed = self._colors = None
        self.forward_controller_state_updates(
            SENSOR_ENABLED(None),
            MODE(None),
            BACK(None),
            FOOT(None),
            PATTERN(None),
            TIMER(None),
            SECONDS(None),
            DURATION(None),
            UNDER_BED_LIGHTS_ON(None),
            UNDER_BED_LIGHTS_RGB(None),
            LIGHT_LEVEL(None),
        )

    async def stop_notify(self) -> None:
        link, notifying = self._link, self._notifying
        self.on_disconnect()
        if link and notifying and link.client.is_connected:
            async with self._ble_lock:
                await link.client.stop_notify(link.notify)

    async def _write(self, link: _Link, data: bytes, cancel: asyncio.Event) -> None:
        async with self._ble_lock:
            self._live(link)
            if cancel.is_set():
                note_frame_skipped()
                return
            try:
                self._record_command_trace(
                    link.write.uuid, data, response=link.response, characteristic=link.write
                )
                await link.client.write_gatt_char(link.write, data, response=link.response)
                note_frame_written(cancel)
                self._live(link)
            except Exception:
                # A failed native write invalidates admission, with no invented
                # Android Boolean, device ACK, callback or dormant retry policy.
                if self._link is link:
                    self.on_disconnect()
                    try:
                        await link.client.disconnect()
                    except Exception:
                        pass
                raise

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 300,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            if index and await self._pause(repeat_delay_ms, cancel):
                return
            await self._write(link, command, cancel)

    async def _sequence(self, link: _Link, steps: Schedule, *, cleanup: bool = False) -> None:
        cancel = asyncio.Event() if cleanup else self._coordinator.cancel_command
        start = asyncio.get_running_loop().time()
        for offset, frame in steps:
            if await self._pause(
                offset - (asyncio.get_running_loop().time() - start) * 1000, cancel
            ):
                return
            await self._write(link, frame, cancel)

    async def refresh_state(self) -> None:
        link = self._live()
        await self._write(link, app.query(0), self._coordinator.cancel_command)
        await self._sequence(link, app.MAIN_QUERIES)
        # HA subscribes to every supported control instead of relying on which
        # Android page happens to own its shared completion callback.
        await self._write(link, app.query(0x45), self._coordinator.cancel_command)
        await self._write(link, app.query(0x44), self._coordinator.cancel_command)

    async def _move_axis(self, axis: codec.Axis, up: bool) -> None:
        if axis not in app.AXES:
            raise ValueError("Unknown Dreamotion Smart motor")
        link, cancel = self._live(), self._coordinator.cancel_command
        try:
            count = self.leased_hold_refreshes(300) or self._coordinator.motor_pulse_count
            for index in range(count):
                if index and await self._pause(300, cancel):
                    break
                if cancel.is_set():
                    break
                await self._write(link, codec.motion(axis, up, codec.BILATERAL), cancel)
        finally:
            # Cancellation still releases, but never into a replacement session.
            if self._link is link and self.client is link.client and link.client.is_connected:
                await self._sequence(link, self.profile.hold.releases, cleanup=True)

    async def move_lumbar_up(self) -> None:
        await self._move_axis("lumbar", True)

    async def move_lumbar_down(self) -> None:
        await self._move_axis("lumbar", False)

    async def move_lumbar_stop(self) -> None:
        await self.stop_all()

    async def stop_all(self) -> None:
        await self._write(self._live(), codec.LONG_RELEASE, asyncio.Event())

    async def _preset(self, preset: codec.Preset) -> None:
        await self._tap(codec.preset(preset, codec.BILATERAL), self.profile.recall)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                axis,
                lambda c, a=axis: require_controller(c, DreamotionSmartController)._move_axis(
                    a, True
                ),
                lambda c, a=axis: require_controller(c, DreamotionSmartController)._move_axis(
                    a, False
                ),
                lambda c: c.stop_all(),
                stop_scope="side",
                scheduler_resource="*",
            )
            for axis in app.AXES
        )

    def _receive(self, data: bytes) -> None:
        record = codec.parse_sendinfo_record(data)
        if record is None:
            return
        op, payload = record
        if op in (0x40, 0x43):
            key = SENSOR_ENABLED if op == 0x40 else UNDER_BED_LIGHTS_ON
            self.forward_controller_state_updates(key(payload[0] != 0))
        elif op == 0x80:
            self._massage = replace(self._massage, hz=payload[0])
            self._mode_known = True
            self.forward_controller_state_updates(
                MODE("acoustic" if payload[0] == 0 else "inherent")
            )
        elif op == 0x81:
            self._massage = replace(
                self._massage,
                back=payload[0],
                foot=payload[1],
                pattern=payload[2],
                duration=payload[3],
            )
            self._massage_known = True
            self._publish_massage()
        elif op == 0x45:
            self._timed = app.Color(*payload[:4]), int.from_bytes(payload[4:], "big")
            self.forward_controller_state_updates(
                SECONDS(self._timed[1]),
                DURATION(str(self._timed[1]) if self._timed[1] in app.DURATIONS else None),
            )
            self._publish_color()
        elif op == 0x44:
            self._colors = (
                app.Color(*payload[:4]),
                app.Color(*payload[4:8]),
                app.Color(*payload[8:12]),
            )
            self._publish_color()

    def _publish_massage(self) -> None:
        s = self._massage
        self.forward_controller_state_updates(
            BACK(s.back),
            FOOT(s.foot),
            PATTERN(s.pattern),
            TIMER(s.duration * 10 if s.duration in range(4) else None),
        )

    def _color(self) -> app.Color:
        if self._page == "timed" and self._timed is not None:
            return self._timed[0]
        if self._page == "presets" and self._colors is not None:
            return self._colors[self._slot - 1]
        raise ValueError("Refresh light settings before editing them")

    def _publish_color(self) -> None:
        try:
            color = self._color()
        except ValueError:
            self.forward_controller_state_updates(UNDER_BED_LIGHTS_RGB(None), LIGHT_LEVEL(None))
            return
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_RGB((color.red, color.green, color.blue)),
            LIGHT_LEVEL(color.brightness),
        )

    async def cycle_massage(self, action: str) -> None:
        if not self._massage_known or not self._mode_known:
            raise ValueError("Refresh massage state before changing it")
        if action in ("back", "foot", "pattern") and self._massage.hz == 0:
            raise ValueError("Select inherent vibration mode to adjust massage")
        local, wire = self._massage.cycle(action)
        if wire is None:
            return
        self._massage = local
        self._publish_massage()
        await self.write_command(wire.frame())

    async def set_mode(self, option: str) -> None:
        if option not in ("inherent", "acoustic"):
            raise ValueError("Unknown vibration mode")
        if option == "inherent" and not self._massage_known:
            raise ValueError("Refresh massage state before changing mode")
        link, cancel = self._live(), self._coordinator.cancel_command
        self._massage = replace(self._massage, hz=0x32 if option == "inherent" else 0)
        await self._write(link, app.setting(0x80, self._massage.hz), cancel)
        self.forward_controller_state_updates(MODE(option))
        self._mode_known = True
        if await self._pause(300 if option == "inherent" else 500, cancel):
            return
        self._live(link)
        if option == "inherent":
            # The source reads the latest notification fields after the delay.
            await self._write(link, replace(self._massage, back=0, foot=0).frame(), cancel)

    async def set_sensor(self, on: bool) -> None:
        await self.write_command(app.setting(0x40, int(on)))

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def supports_light_color_control(self) -> bool:
        return True

    @property
    def supported_color_mode(self) -> str:
        return "rgb"

    @property
    def supports_light_level_control(self) -> bool:
        return True

    @property
    def light_level_max(self) -> int:
        return 100

    @property
    def publishes_rgb_light_state(self) -> bool:
        return True

    @property
    def preserves_unknown_rgb_power(self) -> bool:
        return True

    @property
    def current_light_rgb_color(self) -> tuple[int, int, int] | None:
        try:
            c = self._color()
        except ValueError:
            return None
        return c.red, c.green, c.blue

    @property
    def light_intensity(self) -> int | None:
        try:
            return self._color().brightness
        except ValueError:
            return None

    async def lights_on(self) -> None:
        await self.write_command(app.setting(0x43, 1))

    async def lights_off(self) -> None:
        await self.write_command(app.setting(0x43, 0))

    async def _save_light(self, *, preview: bool, delay_ms: int = 300) -> None:
        link = self._live()
        cancel = self._coordinator.cancel_command
        page = self._page
        if page == "timed":
            if self._timed is None:
                raise ValueError("Refresh timed light settings first")
            await self._write(link, app.timed(*self._timed), cancel)
        else:
            if self._colors is None:
                raise ValueError("Refresh all three saved light entries first")
            await self._write(link, app.slots(self._colors), cancel)
        if preview and not await self._pause(delay_ms, cancel):
            self._live(link)
            await self._write(
                link,
                app.setting(0x43, 1) if page == "timed" else app.preview(self._saved_color()),
                cancel,
            )
        self._publish_color()

    def _saved_color(self) -> app.Color:
        if self._colors is None:
            raise ValueError("Refresh saved light entries first")
        return self._colors[self._slot - 1]

    async def set_light_color_with_level(self, rgb_color: tuple[int, int, int], level: int) -> None:
        self._color()  # Never overwrite unread peer entries or duration.
        color = app.Color(level, *rgb_color)
        color.payload()  # Validate before changing local state.
        if self._page == "timed":
            assert self._timed is not None
            self._timed = color, self._timed[1]
        else:
            assert self._colors is not None
            colors = list(self._colors)
            colors[self._slot - 1] = color
            self._colors = colors[0], colors[1], colors[2]
        await self._save_light(preview=True)

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        await self.set_light_color_with_level(rgb_color, self._color().brightness)

    async def set_light_level(self, level: int) -> None:
        c = self._color()
        await self.set_light_color_with_level((c.red, c.green, c.blue), level)

    def set_page(self, option: str) -> None:
        if option not in ("timed", "presets"):
            raise ValueError("Unknown light page")
        self._page = option
        self.forward_controller_state_updates(PAGE(option))
        self._publish_color()

    async def select_slot(self, option: str) -> None:
        if option not in ("1", "2", "3"):
            raise ValueError("Unknown saved light entry")
        if self._colors is None:
            raise ValueError("Refresh saved light entries first")
        self._slot = int(option)
        self.set_page("presets")
        self.forward_controller_state_updates(SLOT(option))
        await self._save_light(preview=True)

    async def set_duration(self, value: float) -> None:
        if value != int(value) or int(value) not in app.DURATIONS:
            raise ValueError("Choose a supported light duration")
        if self._timed is None:
            raise ValueError("Refresh timed light settings first")
        self._timed = self._timed[0], int(value)
        self.forward_controller_state_updates(SECONDS(int(value)))
        # The app duration slider edits locally until Save/Preview.

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            ControllerButtonSpec(
                "dreamotion_smart_yoga",
                "Yoga",
                lambda c: require_controller(c, DreamotionSmartController)._preset("yoga"),
                translation_key="preset_yoga",
                card=CARD_PRESETS,
                combine_sides=True,
            ),
            *(
                ControllerButtonSpec(
                    "dreamotion_smart_" + action,
                    label,
                    lambda c, a=action: require_controller(
                        c, DreamotionSmartController
                    ).cycle_massage(a),
                    translation_key="dreamotion_smart_" + action,
                    card=CARD_MASSAGE,
                    combine_sides=True,
                )
                for action, label in (
                    ("back", "Cycle back massage"),
                    ("foot", "Cycle foot massage"),
                    ("pattern", "Cycle massage pattern"),
                    ("timer10", "Toggle 10-minute timer"),
                    ("timer20", "Toggle 20-minute timer"),
                    ("timer30", "Toggle 30-minute timer"),
                )
            ),
            ControllerButtonSpec(
                "dreamotion_smart_save_light",
                "Save light settings",
                lambda c: require_controller(c, DreamotionSmartController)._save_light(
                    preview=False
                ),
                translation_key="dreamotion_smart_save_light",
                card=CARD_LIGHTING,
                cancel_movement=False,
            ),
            ControllerButtonSpec(
                "dreamotion_smart_preview_light",
                "Preview light settings",
                lambda c: require_controller(c, DreamotionSmartController)._save_light(
                    preview=True
                ),
                translation_key="dreamotion_smart_preview_light",
                card=CARD_LIGHTING,
                cancel_movement=False,
            ),
            ControllerButtonSpec(
                "dreamotion_smart_refresh",
                "Refresh settings",
                lambda c: require_controller(c, DreamotionSmartController).refresh_state(),
                translation_key="dreamotion_smart_refresh",
                diagnostic=True,
                cancel_movement=False,
            ),
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        return (
            ControllerSelectSpec(
                "dreamotion_smart_mode",
                "dreamotion_smart_mode",
                MODE,
                ("inherent", "acoustic"),
                lambda c, o: require_controller(c, DreamotionSmartController).set_mode(o),
                card=CARD_MASSAGE,
            ),
            ControllerSelectSpec(
                "dreamotion_smart_page",
                "dreamotion_smart_page",
                PAGE,
                ("timed", "presets"),
                lambda c, o: _select_page(c, o),
                local_select_fn=self.set_page,
                card=CARD_LIGHTING,
            ),
            ControllerSelectSpec(
                "dreamotion_smart_slot",
                "dreamotion_smart_slot",
                SLOT,
                ("1", "2", "3"),
                lambda c, o: require_controller(c, DreamotionSmartController).select_slot(o),
                card=CARD_LIGHTING,
            ),
            ControllerSelectSpec(
                "dreamotion_smart_duration",
                "dreamotion_smart_duration",
                DURATION,
                tuple(str(v) for v in app.DURATIONS),
                lambda c, o: require_controller(c, DreamotionSmartController)._duration_option(o),
                card=CARD_LIGHTING,
            ),
        )

    async def _duration_option(self, option: str) -> None:
        await self.set_duration(float(option))
        self.forward_controller_state_updates(DURATION(option))

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        return (
            ControllerSwitchSpec(
                "dreamotion_smart_sensor",
                "dreamotion_smart_sensor",
                lambda c, on: require_controller(c, DreamotionSmartController).set_sensor(on),
                state_key=SENSOR_ENABLED,
                card=CARD_UTILITY,
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(
                str(key),
                str(key),
                key,
                icon,
                entity_registry_enabled_default=True,
                card=card,
                entity_category=None,
                native_unit_of_measurement=unit,
            )
            for key, icon, card, unit in (
                (BACK, "mdi:vibrate", CARD_MASSAGE, None),
                (FOOT, "mdi:vibrate", CARD_MASSAGE, None),
                (PATTERN, "mdi:waveform", CARD_MASSAGE, None),
                (TIMER, "mdi:timer", CARD_MASSAGE, "min"),
                (SECONDS, "mdi:timer", CARD_LIGHTING, "s"),
            )
        )


DURATION: Final = StateKey[str | None]("dreamotion_smart_duration")


async def _select_page(controller: BedController, option: str) -> None:
    require_controller(controller, DreamotionSmartController).set_page(option)
