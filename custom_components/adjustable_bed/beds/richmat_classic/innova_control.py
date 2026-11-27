"""Innova Control's own catalog on the literal-verified Richmat runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import time
from functools import partial
from typing import TYPE_CHECKING, Final

from homeassistant.exceptions import ServiceValidationError

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_UTILITY
from ...codec import richmat as codec
from ...const import CONF_RICHMAT_CLASSIC_THIRD_SERVICE
from ...controller_state import StateKey
from ...errors import invalid
from ...profiles import innova_control as profile
from ...state_keys import UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from ..base import BedController
from ..cancellation import settled
from ..entity_specs import ControllerNumberSpec, ControllerSelectSpec
from .controller import RichmatClassicController
from .homezone import HomeZoneController, HomeZoneReceive
from .protocol import INITIALIZE, STARTUP_MS, aroma, worker_interval
from .resource_protocol import Request
from .transport import ROUTES, Transport, select

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

TIMER_PROGRESS: Final = StateKey[str | None]("innova_control_timer_progress")
AROMA_START_2: Final = StateKey[int | None]("innova_control_aroma_start_2")
AROMA_START_3: Final = StateKey[int | None]("innova_control_aroma_start_3")
AROMA_PAUSE_3: Final = StateKey[int | None]("innova_control_aroma_pause_3")
AROMA_SETTINGS: Final = (
    ("aroma_start_2", AROMA_START_2, 0x1B, 60, "min"),
    ("aroma_start_3", AROMA_START_3, 0x1C, 60, "min"),
    ("aroma_pause_3", AROMA_PAUSE_3, 0x1D, 12, "h"),
)


class InnovaControlController(HomeZoneController):
    """Package-local selection; shared safe gestures, settings and sum parser.

    The accepted app uses the same callbacks as the shared runtime. Phone
    broadcast admission is phone-only; HA cancellation and STOP instead cancel
    the active refresh and pending save before releasing the captured link.
    """

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, device_name: str | None = None
    ) -> None:
        if (
            str(coordinator.entry.data.get("product_type", "")).strip().upper()
            in profile.EXCLUDED_LAYOUTS
        ):
            raise invalid("richmat_classic_control")
        RichmatClassicController.__init__(
            self, coordinator, app=profile.APP, device_name=device_name
        )
        self.app_profile = profile.PROFILE
        self._receive = HomeZoneReceive()
        self._group_only = False
        self._preferences = {}
        self._deadline = None
        self._lamp_timeout = self._massage_timer = None

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("The bed is disconnected")
        self._group_only = False
        try:
            session = select(
                client,
                third_service=self._coordinator.entry.data.get(
                    CONF_RICHMAT_CLASSIC_THIRD_SERVICE, False
                ),
            )
        except ValueError:
            # A receiver offering only grouping is never a motor transport.
            if any(client.services.get_service(route[0]) is not None for route in ROUTES):
                raise
            session = self._group_transport()
            self._group_only = True
        # FFE0 belongs exclusively to grouping, including in a generic G5 slot.
        if session.write.uuid.lower() == "0000ffe2-0000-1000-8000-00805f9b34fb":
            session = self._group_transport()
            self._group_only = True
        self._worker.cancel()
        name = self._device_name or self._coordinator.entry.data.get("ble_device_name")
        self._worker.set_interval(worker_interval(name, session.wire, rise=True))
        self._session, self._wire = session, session.wire
        self._receive = HomeZoneReceive()
        self._notifications_started = False
        try:
            with self._transaction():
                if session.has_notifications:

                    async def subscribe() -> None:
                        result = await client.start_notify(
                            session.notify, partial(self._notification, session)
                        )
                        self._notifications_started = result is not False

                    await settled(subscribe())
                if self._group_only:
                    return
                if session.wire == "FRAMED" and self._notifications_started:
                    if not await self._wait(STARTUP_MS, self._coordinator.cancel_command):
                        return
                    await self.write_command(INITIALIZE)
                # Opening Settings becomes capability preparation in HA. No
                # saved RGB/aroma/alarm preference is replayed on connection.
                await self.execute_request(Request("query"))
        except BaseException:
            if self._session is session:
                self._session = None
                if self._notifications_started and self.client is client and client.is_connected:
                    await settled(client.stop_notify(session.notify))
                self._notifications_started = False
            raise
        self._publish()

    def _publish(self) -> None:
        super()._publish()
        self.forward_controller_state_updates(
            TIMER_PROGRESS(str(self._massage_timer) if self._massage_timer is not None else None)
        )
        event = self._receive.value_event
        if event in ("6e0e00017d", "6e0e00037f"):
            self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(event == "6e0e00037f"))

    def on_disconnect(self) -> None:
        super().on_disconnect()
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(None),
            UNDER_BED_LIGHTS_RGB(None),
            *(key(None) for _, key, _, _, _ in AROMA_SETTINGS),
        )

    @property
    def controller_button_specs(self):
        return () if self._group_only else super().controller_button_specs

    @property
    def supports_stop_all(self) -> bool:
        return not self._group_only

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        if self._group_only:
            return None
        capability = super().alarm_capability
        # FDRM/FFRM explicitly tag k_zg2_return for alarms. Its single-preset
        # path is valid; combineCommand has no corresponding massage branch.
        if 0x6B in self._alarm_actions().values():
            if capability is None:
                return AlarmCapability(wake_actions=("zero_g_2",), requires_wake_action=True)
            return replace(capability, wake_actions=(*capability.wake_actions, "zero_g_2"))
        return capability

    @property
    def settings_transport(self):
        return None if self._group_only else super().settings_transport

    @property
    def has_live_session(self) -> bool:
        session = self._session
        return session is not None and self.client is session.client and session.client.is_connected

    async def execute_action(
        self, node: int, *, long: bool = False, hold_ms: int | None = None
    ) -> None:
        if self._group_only:
            raise invalid("richmat_classic_control")
        await super().execute_action(node, long=long, hold_ms=hold_ms)

    async def stop_all(self) -> None:
        if not self._group_only:
            await super().stop_all()

    @property
    def supports_massage_timer(self) -> bool:
        # Popup IDs and slider labels disagree about duration. Expose the exact
        # slider positions below, never invent physical minutes.
        return False

    async def set_massage_timer(self, minutes: int) -> None:
        raise invalid("richmat_classic_control")

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        specs = super().controller_select_specs
        if self.layout not in ("D1RM", "D9RM"):
            return specs

        async def select_progress(controller: BedController, value: str) -> None:
            assert isinstance(controller, InnovaControlController)
            await controller.execute_request(Request("massage_timer", progress=int(value)))

        return (
            *specs,
            ControllerSelectSpec(
                "innova_control_timer_progress",
                "innova_control_timer_progress",
                TIMER_PROGRESS,
                tuple(str(i) for i in range(6)),
                select_progress,
                card=CARD_UTILITY,
            ),
        )

    @property
    def retained_entity_keys(self) -> frozenset[tuple[str, str]]:
        return super().retained_entity_keys | {
            ("light", "under_bed_lights"),
            *(
                ("number", "controller_number_innova_control_" + name)
                for name, _, _, _, _ in AROMA_SETTINGS
            ),
        }

    @property
    def unavailable_controller_entity_keys(self) -> tuple[str, ...]:
        return (
            *super().unavailable_controller_entity_keys,
            *(("under_bed_lights",) if not self.supports_lights else ()),
            *(
                "controller_number_innova_control_" + name
                for name, _, _, _, _ in AROMA_SETTINGS
                if not self._receive.aroma_capable
            ),
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs = list(super().controller_number_specs)
        if self._receive.aroma_capable:
            for name, key, opcode, limit, unit in AROMA_SETTINGS:

                async def set_value(
                    controller: BedController,
                    value: float,
                    *,
                    state_key: StateKey[int | None] = key,
                    code: int = opcode,
                    maximum: int = limit,
                ) -> None:
                    assert isinstance(controller, InnovaControlController)
                    if (
                        not float(value).is_integer()
                        or not 1 <= value <= maximum
                        or not controller._receive.aroma_capable
                    ):
                        raise invalid("richmat_classic_control")
                    with controller._transaction() as session:

                        def current() -> bool:
                            return (
                                controller._session is session
                                and controller.client is session.client
                                and session.client.is_connected
                            )

                        with controller.sent_state(state_key(int(value)), is_current=current):
                            await controller.write_command(aroma(code, int(value)))
                    await controller._wait(150, controller._coordinator.cancel_command)

                specs.append(
                    ControllerNumberSpec(
                        "innova_control_" + name,
                        "innova_control_" + name,
                        key,
                        1,
                        limit,
                        1,
                        set_value,
                        unit,
                        card=CARD_UTILITY,
                    )
                )
        return tuple(specs)

    def _light_toggle(self) -> int | None:
        if self._group_only or len(self._model.modes) > 1:
            return None
        return next(
            (
                c.node
                for c in self._controls
                if not c.excluded_short
                and c.resource_keys.get("press_short")
                in ("@string/k_ubl_on_off", "@string/com_ubl_on_off")
                and not self._nordic_label(c)
            ),
            None,
        )

    @property
    def supports_lights(self) -> bool:
        return self._light_toggle() is not None

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    @property
    def supports_discrete_light_control(self) -> bool:
        return False

    @property
    def supports_light_state_feedback(self) -> bool:
        return self._receive.light_capable

    @property
    def supports_light_color_control(self) -> bool:
        return self.supports_lights and self._receive.light_capable

    @property
    def supported_color_mode(self) -> str | None:
        return "rgb" if self.supports_light_color_control else None

    async def lights_toggle(self) -> None:
        node = self._light_toggle()
        if node is None:
            raise invalid("richmat_classic_control")
        await self.execute_action(node)

    async def set_light_color(
        self, rgb_color: tuple[int, int, int], *, before_write: Callable[[], bool] | None = None
    ) -> None:
        self.validate_request(Request("rgb", color=rgb_color))
        with self._transaction() as session:

            def current() -> bool:
                return (
                    self._session is session
                    and self.client is session.client
                    and session.client.is_connected
                )

            with self.sent_state(UNDER_BED_LIGHTS_RGB(rgb_color), is_current=current):
                await self._send_at(
                    codec.rgb(*rgb_color),
                    cancel=self._coordinator.cancel_command,
                    before_write=before_write,
                )
        await self._wait(150, self._coordinator.cancel_command)

    def _alarm_request(self, alarm: AlarmRequest) -> Request:
        if alarm.enabled and alarm.wake_action == "zero_g_2":
            node = next(
                (key for key, value in self._alarm_actions().items() if value == 0x6B), None
            )
            if node is None or alarm.massage:
                raise invalid("richmat_classic_control")
            return Request(
                "alarm", actions=(node,), when=time(alarm.hour, alarm.minute), native_alarm=alarm
            )
        try:
            return super()._alarm_request(alarm)
        except (KeyError, ValueError, ServiceValidationError) as error:
            raise invalid("richmat_classic_control") from error

    def validate_request(self, request: Request, *, live: bool = True) -> None:
        if self._group_only:
            raise invalid("richmat_classic_control")
        try:
            super().validate_request(request, live=live)
        except ServiceValidationError as error:
            raise invalid("richmat_classic_control") from error

    def _group_transport(self) -> Transport:
        client = self.client
        service = (
            client.services.get_service("0000ffe0-0000-1000-8000-00805f9b34fb") if client else None
        )
        write = (
            service.get_characteristic("0000ffe2-0000-1000-8000-00805f9b34fb") if service else None
        )
        notify = (
            service.get_characteristic("0000ffe1-0000-1000-8000-00805f9b34fb") if service else None
        )
        if (
            client is None
            or write is None
            or notify is None
            or not set(write.properties) & {"write", "write-without-response"}
        ):
            raise invalid("richmat_classic_control")
        return Transport(client, write, notify, "RAW")

    def validate_group_request(self) -> None:
        if not self.has_live_session:
            raise invalid("richmat_classic_control")
        self._group_transport()

    async def async_group(self, name: str | None) -> None:
        packet = codec.local_group(name)
        self.validate_group_request()
        group = self._group_transport()
        with self._transaction() as session:
            if self._coordinator.cancel_command.is_set():
                return
            subscribed = False
            try:
                if group.notify is not session.notify and group.has_notifications:

                    async def subscribe() -> None:
                        nonlocal subscribed
                        subscribed = True
                        result = await group.client.start_notify(
                            group.notify, lambda _sender, _data: None
                        )
                        subscribed = result is not False

                    await settled(subscribe())
                # The explicitly selected HA device replaces the phone's
                # raw-offset scan selector. This protocol has no group ACK.
                await self._send_at(
                    packet, characteristic=group.write, cancel=self._coordinator.cancel_command
                )
            finally:

                async def close() -> None:
                    await asyncio.sleep(0.5)
                    async with self._coordinator.async_connection_operation_guard() as disconnect:
                        if self._session is not session or self.client is not session.client:
                            return
                        try:
                            if subscribed and session.client.is_connected:
                                await session.client.stop_notify(group.notify)
                        finally:
                            if session.client.is_connected:
                                if not await disconnect("innova_control_group"):
                                    raise ConnectionError("The grouped receiver did not disconnect")

                await settled(close())
