"""Okimiki's product gates and gestures over the shared Richmat catalog runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict
from functools import partial
from math import ceil
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...card import CARD_HIDDEN, CARD_PRESETS, CardPlacement, CardSection
from ...codec import richmat as codec
from ...command_scheduler import current_command_context
from ...controller_state import StateKey
from ...execution import ExecutionCapabilities
from ...profiles.okimiki import CATALOG, CONTROLS, LIGHT_DELAY_S, PRODUCTS, QUERY_S, SAVE_S, TICK_S
from ..base import CONTROLLER_GESTURE_RELEASE, BedController
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..goodvibe.controller import Gesture, GoodVibeController, Link, select_link
from . import protocol as p

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator
    from .services import Request

STATUS: Final = StateKey[str | None]("okimiki_status")
OBSERVATIONS: Final = StateKey[dict[str, object]]("okimiki_observations")
ALARMS: Final = StateKey[list[dict[str, int]]]("okimiki_alarms")
REQUESTS: Final = StateKey[dict[str, object]]("okimiki_requests")
DURATION: Final = StateKey[int | None]("okimiki_light_seconds")
_SAVE_LABELS: Final = {"lounge": "Save lounge position", "zero_gravity": "Save zero-gravity position"}
_SCOPE: ContextVar[tuple[object, Link, float | None, list[BleakError]] | None] = ContextVar(
    "okimiki_session", default=None
)


class _DeadlineExpired(Exception):
    """A queued refresh reached its elapsed deadline before BLE submission."""


def selected(controller: BedController) -> OkimikiController:
    if not isinstance(controller, OkimikiController):
        raise ValueError("Choose an Okimiki bed")
    return controller


async def _press(controller: BedController, control: str, *, save: bool = False) -> None:
    await selected(controller).press(control, 3000 if save else 1000, save_only=save)


async def _release(_controller: BedController) -> None:
    # The cancelled gesture owns its captured session's release.
    return


class OkimikiController(GoodVibeController):
    def __init__(self, coordinator: AdjustableBedCoordinator, product: str) -> None:
        if product not in PRODUCTS:
            raise ValueError("Choose the exact Okimiki product")
        super().__init__(coordinator, profile=product, catalog=CATALOG)
        self.model = PRODUCTS[product]
        self._normal = p.Receiver(self._event)
        self._alarms: list[p.Alarm] = []
        self._stale_alarm_ids: set[int] = set()
        self._observations: dict[str, object] = {}
        self._requests: dict[str, object] = {}
        self._light_entity_identity: dict[str, str] | None = None

    @property
    def execution(self) -> ExecutionCapabilities:
        return ExecutionCapabilities(
            hold="stream",
            hold_controls=frozenset(
                "okimiki_" + key for key, control in CONTROLS.items() if control.held
            ),
        )

    @property
    def supports_motor_control(self) -> bool:
        return True

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key,
                "head_feet" if key == "both" else key,
                up,
                down,
                lambda controller: controller.stop_all(),
                hold=ControllerMotorHoldSpec(
                    "okimiki_" + prefix + "_up",
                    "okimiki_" + prefix + "_down",
                    release_button_key="goodvibe_release",
                    press_is_native=True,
                ),
            )
            for key, prefix, up, down in (
                ("back", "head", lambda c: c.move_back_up(), lambda c: c.move_back_down()),
                ("legs", "foot", lambda c: c.move_legs_up(), lambda c: c.move_legs_down()),
                (
                    "both",
                    "head_foot",
                    lambda c: selected(c).press("head_foot_up", 1000),
                    lambda c: selected(c).press("head_foot_down", 1000),
                ),
            )
        )

    @property
    def supports_preset_flat(self) -> bool:
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        return self.model.memory_slots > 0

    @property
    def supports_preset_lounge(self) -> bool:
        return self.model.memory_slots > 0

    @property
    def memory_slot_count(self) -> int:
        return self.model.memory_slots

    @property
    def supports_memory_presets(self) -> bool:
        return self.model.memory_slots > 0

    @property
    def supports_memory_programming(self) -> bool:
        return self.model.memory_slots > 0

    def standard_button_requires_confirmation(self, key: str) -> bool:
        return key.startswith("program_memory_") and self.supports_memory_programming

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def retain_live_controller_offline(self) -> bool:
        return True

    def _entity_identity(self) -> dict[str, str]:
        return {"address": self._coordinator.address, "product": self.product_key}

    @property
    def retained_entity_keys(self) -> frozenset[tuple[str, str]]:
        # HA identity metadata only, never a remembered permission to send BLE.
        if self._light_entity_identity != self._entity_identity():
            return frozenset()
        return frozenset(
            {
                ("light", "under_bed_lights"),
                ("number", "controller_number_okimiki_light_seconds"),
            }
        )

    @property
    def unavailable_controller_entity_keys(self) -> tuple[str, ...]:
        if self.supports_lights:
            return ()
        return ("under_bed_lights", "controller_number_okimiki_light_seconds")

    @property
    def supports_lights(self) -> bool:
        return "light" in self._menus

    @property
    def supports_light_color_control(self) -> bool:
        return self.supports_lights

    @property
    def supported_color_mode(self) -> str | None:
        return "rgb" if self.supports_lights else None

    @property
    def light_state_is_assumed(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.supports_lights

    def menu_available(self, menu: str) -> bool:
        return menu in self._menus

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        state = dict(self._requests)
        identity = self._light_entity_identity
        if identity is not None and identity == self._entity_identity():
            state["light_entity_identity"] = dict(identity)
        return state

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        seconds, rgb = state.get("seconds"), state.get("rgb")
        if seconds is not None and (type(seconds) is not int or not 0 <= seconds <= 900):
            raise ValueError("Invalid saved light duration")
        if rgb is not None and (
            not isinstance(rgb, (list, tuple))
            or len(rgb) != 3
            or any(type(value) is not int or not 0 <= value <= 255 for value in rgb)
        ):
            raise ValueError("Invalid saved light color")
        self._requests = {key: value for key, value in state.items() if key in ("seconds", "rgb")}
        identity = state.get("light_entity_identity")
        self._light_entity_identity = (
            self._entity_identity() if identity == self._entity_identity() else None
        )
        self._publish()

    @contextmanager
    def _transaction(self, deadline: float | None = None) -> Iterator[Link]:
        link = self._current_link()
        errors: list[BleakError] = []
        token = _SCOPE.set((self, link, deadline, errors))
        try:
            yield link
            if errors:
                raise errors[0]
        finally:
            _SCOPE.reset(token)

    async def _send(
        self,
        data: bytes,
        *,
        cleanup: bool = False,
        link: Link | None = None,
        release_gesture: Gesture | None = None,
        on_submit: Callable[[], None] | None = None,
    ) -> bool:
        scope = _SCOPE.get()
        if scope is not None and scope[0] is self:
            link = link or scope[1]
        else:
            link = link or self._current_link()
        submitted = False

        def submit() -> None:
            nonlocal submitted
            if not cleanup and scope is not None and scope[0] is self and scope[2] is not None:
                if asyncio.get_running_loop().time() >= scope[2]:
                    raise _DeadlineExpired
            submitted = True
            if on_submit is not None:
                on_submit()

        # Drain an in-flight BLE write before releasing the same captured link.
        task = asyncio.create_task(
            super()._send(
                data, cleanup=cleanup, link=link, release_gesture=release_gesture, on_submit=submit
            )
        )
        cancelled = False
        try:
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    cancelled = True
                    if not submitted and not cleanup:
                        task.cancel()
            result = task.result()
        except _DeadlineExpired:
            return False
        except BleakError as err:
            if scope is None or scope[0] is not self:
                raise
            # The failed head leaves the source FIFO, without retry. Drain the
            # remaining admitted items, then report the failure to HA.
            scope[3].append(err)
            self._rejection = str(err)
            if cancelled:
                raise asyncio.CancelledError from err
            return True
        if cancelled:
            raise asyncio.CancelledError
        return result

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Okimiki is disconnected")
        if self._link is not None:
            await self.stop_notify()
        self.on_disconnect()
        # Same first-write/first-notify and last-service framing policy, proven independently.
        link = select_link(client, 1, self.profile)
        self._link = link
        try:
            await client.start_notify(link.rx, partial(self._notification, link))
            with self._transaction():
                first_action, first_code = self.catalog.startup[0]
                await self._send(
                    codec.function(first_code, action=first_action, single=link.legacy)
                )
                if self.model.alarm != "none":
                    for frame in p.sync_time(dt_util.now(), dt_util.now()):
                        await self._send(frame)
                for action, code in self.catalog.startup[1:]:
                    await asyncio.sleep(QUERY_S)
                    await self._send(codec.function(code, action=action, single=link.legacy))
        except BaseException:
            self.on_disconnect()
            raise
        self._publish()

    def _notification(self, link: Link, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        if self._link is not link or self.client is not link.client or not link.client.is_connected:
            return
        self.forward_raw_notification(link.rx.uuid, bytes(data))
        self._normal.feed(bytes(data))
        self._publish()

    def _event(self, name: str, value: object) -> None:
        self._last_event = name
        self._observations[name] = asdict(value) if isinstance(value, p.Alarm) else value
        if name == "light":
            self._menus.add("light")
            self._light_entity_identity = self._entity_identity()
        elif name == "alarm" and self.model.alarm != "none":
            self._menus.add("alarm")
        elif isinstance(value, p.Alarm) and self.model.alarm == "repeat":
            if name == "alarm_list":
                self._stale_alarm_ids.discard(value.id)
                if value not in self._alarms:
                    self._alarms.append(value)
            elif name == "alarm_update":
                if any(row.id == value.id for row in self._alarms):
                    self._stale_alarm_ids.discard(value.id)
                self._alarms = [value if row.id == value.id else row for row in self._alarms]
        if name in ("light", "alarm") or (
            isinstance(value, p.Alarm) and self.model.alarm == "repeat"
        ):
            # A record read can complete the same service readiness wait.
            self._menus_changed.set()
        # Add/cancel ACKs are uncorrelated observations, never confirmed schedule state.
        self._publish()

    def on_disconnect(self) -> None:
        super().on_disconnect()
        self._alarms = []
        self._stale_alarm_ids = set()
        self._observations = {}
        self._last_event = None
        self._publish()

    def _publish(self) -> None:
        seconds = self._requests.get("seconds") if self.supports_lights else None
        self.forward_controller_state_updates(
            STATUS(self._last_event),
            OBSERVATIONS(dict(getattr(self, "_observations", {}))),
            ALARMS([asdict(row) for row in getattr(self, "_alarms", [])]),
            REQUESTS(dict(getattr(self, "_requests", {}))),
            DURATION(seconds if type(seconds) is int else None),
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app": "Okimiki",
            "product": self.product_key,
            "hardware": "UNVERIFIED",
            "menus": sorted(self._menus),
            "observations": self._observations,
            "requests": self._requests,
            "parser_rejection": self._normal.rejection,
            "write_error": self._rejection,
        }

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            # The state is the last decoded event name; the alarms and
            # observations are attributes, so the sensor is off by default.
            ControllerStateSensorSpec(
                "okimiki_status",
                "okimiki_status",
                STATUS,
                "mdi:bed",
                attribute_keys=(OBSERVATIONS, ALARMS, REQUESTS),
                entity_registry_enabled_default=False,
            ),
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        return ()

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if not self.supports_lights:
            return ()

        async def duration(controller: BedController, value: float) -> None:
            from .services import Request

            if value != int(value):
                raise ValueError("Choose whole seconds")
            await selected(controller).execute_request(
                Request("light_duration", seconds=int(value))
            )

        return (
            ControllerNumberSpec(
                "okimiki_light_seconds",
                "okimiki_light_seconds",
                DURATION,
                0,
                900,
                1,
                duration,
                "s",
                card=CardPlacement(CardSection.LIGHTING),
            ),
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        buttons = []
        for key in self.control_actions:
            control = CONTROLS[key]
            # Standard platforms own motors, combined movement, flat and recalls.
            if control.save is not None and key in ("lounge", "zero_gravity"):
                label = _SAVE_LABELS[key]
                buttons.append(
                    ControllerButtonSpec(
                        "okimiki_save_" + key,
                        label,
                        partial(_press, control=key, save=True),
                        translation_key="okimiki_action",
                        translation_placeholders={"action": label},
                        requires_confirmation=True,
                        card=CARD_PRESETS,
                    )
                )
        buttons.append(
            ControllerButtonSpec(
                "okimiki_release",
                "Release held control",
                _release,
                translation_key="goodvibe_release",
                release_only=True,
                card=CARD_HIDDEN,
            )
        )
        return tuple(buttons)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple("okimiki_" + key for key in self.control_actions)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError("Choose an Okimiki control")
        await self.press(control.removeprefix("okimiki_"), duration_ms)

    async def press(self, detail: str, duration: int, *, save_only: bool = False) -> None:
        if (
            detail not in self.control_actions
            or type(duration) is not int
            or not 0 <= duration <= 60000
        ):
            raise ValueError("Choose an available control and bounded duration")
        control = CONTROLS[detail]
        if save_only and control.save is None:
            raise ValueError("This control has no save action")
        context = current_command_context()
        if context is not None and context.lease is not None and not control.held:
            raise ValueError("Only motor controls support renewable holds")
        loop = asyncio.get_running_loop()
        started = loop.time()
        deadline = started + self.leased_hold_ms(duration) / 1000
        gesture = self._gesture = Gesture(
            0, self._coordinator.cancel_command, asyncio.current_task(), context
        )
        attempted = False
        saved = False

        def submitted() -> None:
            nonlocal attempted
            attempted = True

        with self._transaction(deadline if control.held else None) as link:
            try:
                try:
                    if control.held:
                        due = started + TICK_S
                        while due <= deadline:
                            if not await self._delay(max(0, ceil((due - loop.time()) * 1000))):
                                break
                            if loop.time() >= deadline:
                                break
                            if not await self._send(
                                codec.function(control.opcode, single=link.legacy),
                                on_submit=submitted,
                            ):
                                break
                            # No catch-up burst after a delayed GATT write.
                            due = max(due + TICK_S, loop.time())
                    elif control.save is not None:
                        if duration >= SAVE_S * 1000:
                            if await self._delay(
                                ceil(max(0, started + SAVE_S - loop.time()) * 1000)
                            ):
                                saved = True
                                await self._send(
                                    codec.function(control.save, single=link.legacy),
                                    on_submit=submitted,
                                )
                        elif not save_only and await self._delay(duration):
                            await self._send(
                                codec.function(control.opcode, single=link.legacy),
                                on_submit=submitted,
                            )
                    else:
                        await self._send(
                            codec.function(control.opcode, single=link.legacy), on_submit=submitted
                        )
                        await self._delay(duration)
                except asyncio.CancelledError:
                    if not (
                        control.save is not None
                        and not saved
                        and not save_only
                        and gesture.release_is_current
                        and self._link is link
                    ):
                        raise
                if (
                    not attempted
                    and control.save is not None
                    and not saved
                    and not save_only
                    and gesture.release_is_current
                    and self._link is link
                ):
                    await self._send(
                        codec.function(control.opcode, single=link.legacy),
                        cleanup=True,
                        link=link,
                        release_gesture=gesture,
                        on_submit=submitted,
                    )
            finally:
                if (
                    attempted
                    and (control.held or detail == "flat")
                    and self._link is link
                    and link.client.is_connected
                ):
                    await self._send(
                        codec.function(codec.STOP, single=link.legacy), cleanup=True, link=link
                    )
                if self._gesture is gesture:
                    self._gesture = None

    async def stop_all(self) -> None:
        if CONTROLLER_GESTURE_RELEASE.get():
            return
        with self._transaction() as link:
            await self._send(codec.function(codec.STOP, single=link.legacy), cleanup=True)

    async def move_back_up(self) -> None:
        await self.press("head_up", self._coordinator.motor_pulse_count * 100)

    async def move_back_down(self) -> None:
        await self.press("head_down", self._coordinator.motor_pulse_count * 100)

    async def move_legs_up(self) -> None:
        await self.press("foot_up", self._coordinator.motor_pulse_count * 100)

    async def move_legs_down(self) -> None:
        await self.press("foot_down", self._coordinator.motor_pulse_count * 100)

    move_head_up = move_back_up
    move_head_down = move_back_down
    move_feet_up = move_legs_up
    move_feet_down = move_legs_down
    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all

    async def preset_flat(self) -> None:
        await self.press("flat", 0)

    async def preset_zero_g(self) -> None:
        await self.press("zero_gravity", 0)

    async def preset_lounge(self) -> None:
        await self.press("lounge", 0)

    async def preset_memory(self, memory_num: int) -> None:
        if not 1 <= memory_num <= self.memory_slot_count:
            raise ValueError("This product does not offer that memory")
        await self.press(f"memory_{memory_num}", 0)

    async def program_memory(self, memory_num: int) -> None:
        if not 1 <= memory_num <= self.memory_slot_count:
            raise ValueError("This product does not offer that memory")
        await self.press(f"memory_{memory_num}", 3000, save_only=True)

    async def lights_on(self) -> None:
        from .services import Request

        await self.execute_request(Request("light_duration", seconds=0))

    async def lights_off(self) -> None:
        from .services import Request

        await self.execute_request(Request("light_off"))

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        from .services import Request

        await self.execute_request(Request("light_color", rgb=rgb_color))

    def validate_request(self, request: Request) -> None:
        request.validate(self)

    async def execute_request(self, request: Request) -> None:
        self.validate_request(request)
        if request.operation in ("press", "save"):
            assert request.control is not None
            await self.press(
                request.control,
                3000 if request.operation == "save" else request.duration_ms,
                save_only=request.operation == "save",
            )
            return
        with self._transaction() as link:
            frames = request.frames(self)
            if request.operation == "light_duration":
                if not await self._delay(round(LIGHT_DELAY_S * 1000)):
                    return
            if request.operation == "alarms":
                self._alarms = []
                self._publish()
            if request.operation in ("repeat", "enable", "delete"):
                # ACKs carry no record fields. Reusing a pre-write observation
                # could undo a newer edit; wait for readback or a list refresh.
                self._stale_alarm_ids.add(frames[0][6])
            for frame in frames:
                if not await self._send(frame, link=link):
                    return
            if request.operation == "light_color":
                self._requests["rgb"] = request.rgb
            elif request.operation == "light_duration":
                self._requests["seconds"] = request.seconds
            self._publish()
        if request.operation == "alarms":
            # Deleted IDs cannot return a record. A successful explicit refresh
            # starts a new observed list, without claiming it is complete.
            self._stale_alarm_ids.clear()


async def build_controller(ctx: BuildContext) -> OkimikiController:
    return OkimikiController(ctx.coordinator, ctx.variant or "")
