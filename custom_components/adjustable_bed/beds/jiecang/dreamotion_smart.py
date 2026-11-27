"""Dreamotion Smart's local records on the shared Jiecang movement interface."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.exceptions import ServiceValidationError

from ...card import CARD_LIGHTING, CARD_MASSAGE, CARD_PRESETS, CARD_UTILITY
from ...codec import jiecang as codec
from ...command_scheduler import Delivery, delivered, note_frame_skipped, note_frame_written
from ...controller_state import StateKey, StateUpdate
from ...errors import BedNotConnectedError, invalid
from ...profiles import dreamotion_smart as app
from ...profiles.jiecang import Schedule
from ...state_keys import (
    LIGHT_LEVEL,
    MASSAGE_TIMER_MINUTES,
    UNDER_BED_LIGHTS_ON,
    UNDER_BED_LIGHTS_RGB,
)
from ..base import BedController, require_controller
from ..cancellation import settled
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
        self._revisions: dict[int, int] = {}
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
            raise BedNotConnectedError("dreamotion_smart_session")

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
            raise BedNotConnectedError("dreamotion_smart_session")
        return link

    def _select_transport(self) -> None:
        """Use concrete GATT roles, never Android's mutable callback address.

        The app matches case-folded substrings. HA accepts exactly one matching
        service and role, and selects response mode from actual properties.
        """
        client = self.client
        if client is None:
            raise BedNotConnectedError()
        services = [s for s in client.services if "fe60" in s.uuid.lower()]
        if len(services) != 1:
            raise invalid("dreamotion_smart_gatt")
        writes = [c for c in services[0].characteristics if "fe61" in c.uuid.lower()]
        notifies = [c for c in services[0].characteristics if "fe62" in c.uuid.lower()]
        if (
            len(writes) != 1
            or len(notifies) != 1
            or not {"write", "write-without-response"}.intersection(writes[0].properties)
            or not {"notify", "indicate"}.intersection(notifies[0].properties)
        ):
            raise invalid("dreamotion_smart_gatt")
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
            MASSAGE_TIMER_MINUTES(None),
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

    def _current(self, link: _Link) -> bool:
        return self._link is link and self.client is link.client and link.client.is_connected

    @contextmanager
    def _setting_state(
        self,
        link: _Link,
        opcode: int,
        updates: tuple[StateUpdate, ...],
        remember: Callable[[bool], None],
    ) -> Iterator[None]:
        revision = self._revisions.get(opcode, 0)

        def current() -> bool:
            return self._current(link) and self._revisions.get(opcode, 0) == revision

        def cache(delivery: Delivery) -> None:
            if current() and delivery is not Delivery.NONE:
                remember(delivery is Delivery.SENT)

        with delivered(cache), self.sent_state(*updates, is_current=current):
            yield

    async def _write(
        self,
        link: _Link,
        data: bytes,
        cancel: asyncio.Event,
        *,
        on_sent: Callable[[], None] | None = None,
    ) -> None:
        async with self._ble_lock:
            self._live(link)
            if cancel.is_set():
                note_frame_skipped()
                return

            async def send() -> None:
                await link.client.write_gatt_char(link.write, data, response=link.response)
                note_frame_written(cancel)
                if on_sent is not None:
                    on_sent()

            try:
                self._record_command_trace(
                    link.write.uuid, data, response=link.response, characteristic=link.write
                )
                await settled(send(), eager_start=True)
                self._live(link)
            except Exception:
                # Native failure invalidates admission, without protocol retries.
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
            raise invalid("option_unavailable")
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
        self._revisions[op] = self._revisions.get(op, 0) + 1
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
            MASSAGE_TIMER_MINUTES(s.duration * 10 if s.duration in range(4) else None),
        )

    def _color(self) -> app.Color:
        if self._page == "timed" and self._timed is not None:
            return self._timed[0]
        if self._page == "presets" and self._colors is not None:
            return self._colors[self._slot - 1]
        raise invalid("dreamotion_smart_refresh", setting="light")

    def _publish_color(self) -> None:
        try:
            color = self._color()
        except ValueError, ServiceValidationError:
            self.forward_controller_state_updates(UNDER_BED_LIGHTS_RGB(None), LIGHT_LEVEL(None))
            return
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_RGB((color.red, color.green, color.blue)),
            LIGHT_LEVEL(color.brightness),
        )

    async def cycle_massage(self, action: str) -> None:
        if not self._massage_known or not self._mode_known:
            raise invalid("dreamotion_smart_refresh", setting="massage")
        if action in ("back", "foot", "pattern") and self._massage.hz == 0:
            raise invalid("dreamotion_smart_inherent")
        local, wire = self._massage.cycle(action)
        if wire is None:
            return
        link = self._live()

        def remember(sent: bool) -> None:
            self._massage_known = sent
            if sent:
                # Levels/pattern retain the app's notification-only semantics;
                # only its local timer and pattern-start promotion are committed.
                self._massage = replace(
                    self._massage,
                    back=local.back,
                    foot=local.foot,
                    pattern=local.pattern,
                    duration=local.duration,
                )

        minutes = local.duration * 10 if local.duration in range(4) else None
        with self._setting_state(
            link,
            0x81,
            (
                BACK(local.back),
                FOOT(local.foot),
                PATTERN(local.pattern),
                TIMER(minutes),
                MASSAGE_TIMER_MINUTES(minutes),
            ),
            remember,
        ):
            await self._write(link, wire.frame(), self._coordinator.cancel_command)

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_massage_timer(self) -> bool:
        return True

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20, 30]

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return False

    async def set_massage_timer(self, minutes: int) -> None:
        if minutes not in self.massage_timer_options:
            raise invalid("option_unavailable")
        # Reselecting the current duration toggles it off in the app. There is
        # no unconditional off action independent of the selected duration.
        await self.cycle_massage(f"timer{minutes}")

    async def set_mode(self, option: str) -> None:
        if option not in ("inherent", "acoustic"):
            raise invalid("option_unavailable")
        if option == "inherent" and not self._massage_known:
            raise invalid("dreamotion_smart_refresh", setting="massage")
        link, cancel = self._live(), self._coordinator.cancel_command
        hz = 0x32 if option == "inherent" else 0

        def remember(sent: bool) -> None:
            self._mode_known = sent
            if sent:
                self._massage = replace(self._massage, hz=hz)

        final_written = False

        def finished() -> None:
            nonlocal final_written
            final_written = True

        with self._setting_state(link, 0x80, (MODE(option),), remember):
            try:
                await self._write(
                    link,
                    app.setting(0x80, hz),
                    cancel,
                    on_sent=finished if option == "acoustic" else None,
                )
                if await self._pause(300 if option == "inherent" else 500, cancel):
                    return
                self._live(link)
                if option == "inherent":
                    # Keep the late read of reported pattern/duration.
                    await self._write(
                        link,
                        replace(self._massage, back=0, foot=0).frame(),
                        cancel,
                        on_sent=finished,
                    )
            finally:
                if not final_written:
                    note_frame_skipped()

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
        except ValueError, ServiceValidationError:
            return None
        return c.red, c.green, c.blue

    @property
    def light_intensity(self) -> int | None:
        try:
            return self._color().brightness
        except ValueError, ServiceValidationError:
            return None

    async def lights_on(self) -> None:
        await self._light_power(True)

    async def lights_off(self) -> None:
        await self._light_power(False)

    async def _light_power(self, on: bool) -> None:
        link = self._live()
        with self._setting_state(link, 0x43, (UNDER_BED_LIGHTS_ON(on),), lambda _sent: None):
            await self._write(link, app.setting(0x43, int(on)), self._coordinator.cancel_command)

    async def _save_light(
        self,
        *,
        preview: bool,
        delay_ms: int = 300,
        timed: tuple[app.Color, int] | None = None,
        colors: tuple[app.Color, app.Color, app.Color] | None = None,
    ) -> None:
        link, cancel = self._live(), self._coordinator.cancel_command
        page, slot = self._page, self._slot
        timed = self._timed if timed is None else timed
        colors = self._colors if colors is None else colors
        if page == "timed":
            if timed is None:
                raise invalid("dreamotion_smart_refresh", setting="timed light")
            frame, color, opcode = app.timed(*timed), timed[0], 0x45
        else:
            if colors is None:
                raise invalid("dreamotion_smart_refresh", setting="saved light")
            frame, color, opcode = app.slots(colors), colors[slot - 1], 0x44
        revision = self._revisions.get(opcode, 0)

        def remember(sent: bool) -> None:
            if page == "timed":
                self._timed = timed if sent else None
            else:
                self._colors = colors if sent else None

        color_updates = (
            UNDER_BED_LIGHTS_RGB((color.red, color.green, color.blue)),
            LIGHT_LEVEL(color.brightness),
        )
        updates: tuple[StateUpdate, ...] = ()
        if page == "timed" and timed is not None:
            updates = (
                SECONDS(timed[1]),
                DURATION(str(timed[1]) if timed[1] in app.DURATIONS else None),
            )
        final_written = False

        def finished() -> None:
            nonlocal final_written
            final_written = True

        def current_color() -> bool:
            return (
                self._current(link)
                and self._revisions.get(opcode, 0) == revision
                and (self._page, self._slot) == (page, slot)
            )

        with (
            self._setting_state(link, opcode, updates, remember),
            self.sent_state(*color_updates, is_current=current_color),
        ):
            try:
                await self._write(link, frame, cancel, on_sent=finished if not preview else None)
                if not preview:
                    return
                if await self._pause(delay_ms, cancel):
                    return
                self._live(link)
                latest = self._colors if self._revisions.get(opcode, 0) != revision else colors
                if page == "timed":
                    follow = app.setting(0x43, 1)
                else:
                    if latest is None:
                        raise invalid("dreamotion_smart_refresh", setting="saved light")
                    follow = app.preview(latest[self._slot - 1])
                with self._setting_state(
                    link,
                    0x43,
                    (UNDER_BED_LIGHTS_ON(True),) if page == "timed" else (),
                    lambda _sent: None,
                ):
                    await self._write(link, follow, cancel, on_sent=finished)
            finally:
                if not final_written:
                    note_frame_skipped()

    async def set_light_color_with_level(self, rgb_color: tuple[int, int, int], level: int) -> None:
        self._color()  # Never overwrite unread peer entries or duration.
        if not 0 <= level <= 100:
            raise invalid("value_out_of_range", min=0, max=100, step=1)
        if any(not 0 <= channel <= 255 for channel in rgb_color):
            raise invalid("value_out_of_range", min=0, max=255, step=1)
        color = app.Color(level, *rgb_color)
        color.payload()
        if self._page == "timed":
            assert self._timed is not None
            await self._save_light(preview=True, timed=(color, self._timed[1]))
        else:
            assert self._colors is not None
            colors = list(self._colors)
            colors[self._slot - 1] = color
            await self._save_light(preview=True, colors=(colors[0], colors[1], colors[2]))

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        await self.set_light_color_with_level(rgb_color, self._color().brightness)

    async def set_light_level(self, level: int) -> None:
        c = self._color()
        await self.set_light_color_with_level((c.red, c.green, c.blue), level)

    def set_page(self, option: str) -> None:
        if option not in ("timed", "presets"):
            raise invalid("option_unavailable")
        self._page = option
        self.forward_controller_state_updates(PAGE(option))
        self._publish_color()

    async def select_slot(self, option: str) -> None:
        if option not in ("1", "2", "3"):
            raise invalid("option_unavailable")
        if self._colors is None:
            raise invalid("dreamotion_smart_refresh", setting="saved light")
        self._slot = int(option)
        self.set_page("presets")
        self.forward_controller_state_updates(SLOT(option))
        await self._save_light(preview=True)

    async def set_duration(self, value: float) -> None:
        if value != int(value) or int(value) not in app.DURATIONS:
            raise invalid("dreamotion_smart_duration")
        if self._timed is None:
            raise invalid("dreamotion_smart_refresh", setting="timed light")
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
