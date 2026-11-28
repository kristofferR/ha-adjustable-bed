"""Softide's AA family hooks: captured sessions, care release and staged programs."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, Final

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...card import CARD_MASSAGE_TIMER, CARD_PRESETS, CARD_UTILITY
from ...codec import sleep_assistant as codec
from ...command_scheduler import CommandIntent, current_command_context, note_frame_skipped
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid
from ...profiles import softide as app
from ...state_keys import MASSAGE_TIMER_MINUTES
from ..base import BedController, ProfileExecution, require_controller
from ..builder import BuildContext
from ..cancellation import cancellable, settled
from ..catalog_buttons import Kind, catalog_button, massage_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
    massage_timer_sensor_spec,
    sleep_flag_binary_sensor_spec,
    sleep_rate_sensor_spec,
)
from ..lifecycle import ControllerSession
from .softide_state import SoftideState

if TYPE_CHECKING:
    from ...command_scheduler import CommandContext
    from ...coordinator import AdjustableBedCoordinator

HEART: Final = StateKey[int | None]("softide_heart_rate")
BREATHING: Final = StateKey[int | None]("softide_breathing_rate")
PRESENCE: Final = StateKey[bool | None]("softide_presence")
TWITCH: Final = StateKey[int | None]("softide_movement_count")
PROGRAM: Final = StateKey[str | None]("softide_program")


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    response: bool
    generation: int


def select_link(client: BleakClient, generation: int) -> Link:
    service = next((s for s in client.services if s.uuid.lower() == app.SERVICE), None)
    tx = service.get_characteristic(app.WRITE) if service else None
    rx = service.get_characteristic(app.NOTIFY) if service else None
    if (
        tx is None
        or rx is None
        or not {"write", "write-without-response"}.intersection(tx.properties)
        or "notify" not in rx.properties
    ):
        raise BedNotConnectedError("softide_gatt")
    return Link(client, tx, rx, "write-without-response" not in tx.properties, generation)


def _action(action: str) -> MotorCommandCallable:
    async def run(controller: BedController) -> None:
        await require_controller(controller, SoftideController).perform(action)

    return run


class SoftideController(ProfileExecution[app.SoftideProfile], BedController):
    def __init__(self, coordinator: AdjustableBedCoordinator, profile: app.SoftideProfile) -> None:
        super().__init__(coordinator)
        self.profile = profile
        self._address = coordinator.address.upper()
        self._link: Link | None = None
        self._subscription: object | None = None
        self._state = SoftideState()
        self._diagnostics: dict[str, object] = {}
        self._frequency_pending = profile.prepare_massage
        self._followup: asyncio.Task[None] | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return app.WRITE

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def requires_linked_live_readiness(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def requires_persistent_connection(self) -> bool:
        # These host consumers need notifications beyond the normal idle window.
        return self._state.active_program in ("one_button_sleep", "smart_relaxation")

    @property
    def auto_stops_on_idle(self) -> bool:
        return self.profile.route == "care"

    @property
    def supports_motor_control(self) -> bool:
        return bool(self.profile.axes)

    @property
    def supports_preset_flat(self) -> bool:
        return "flat" in self.profile.controls

    @property
    def supports_preset_zero_g(self) -> bool:
        return "zero_g" in self.profile.controls

    @property
    def supports_preset_tv(self) -> bool:
        return "tv" in self.profile.controls

    @property
    def supports_preset_reading(self) -> bool:
        return "reading" in self.profile.controls

    @property
    def persisted_app_state_key(self) -> str:
        return f"{self.profile.model}:{self.profile.route}"

    @property
    def persisted_app_state(self) -> Mapping[str, object] | None:
        return (
            {"frequency_prepared": not self._frequency_pending}
            if self.profile.prepare_massage
            else None
        )

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        prepared = state.get("frequency_prepared", False)
        if type(prepared) is not bool:
            raise ValueError("frequency_prepared")
        if prepared:
            self._frequency_pending = False

    def _frequency_prepared(self) -> None:
        self._frequency_pending = False
        self._coordinator.save_app_state(self)

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            **self._diagnostics,
            "app": "Softide 1.2.4",
            "model": self.profile.model,
            "layout": self.profile.layout,
            "route": self.profile.route,
            "sensor_selection": self.profile.sensors,
            "hardware_verified": False,
            "moon_shown_samples": self._state.moon.shown,
            "moon_zero_samples": self._state.moon.zero,
            "last_moon_rates": self._state.last_moon,
            "last_relax_rates": self._state.last_relax,
            "frequency_preparation_pending": self._frequency_pending,
        }

    def _live(self, expected: Link | None = None, *, cleanup: bool = False) -> Link:
        link = self._link
        if (
            link is None
            or expected is not None
            and expected is not link
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.controller is not self
            or self._coordinator.address.upper() != self._address
            or self._coordinator.connection_generation != link.generation
            or self.command_side not in (None, "both")
            or not cleanup
            and app.selected(self._coordinator.entry.data) != self.profile
        ):
            raise BedNotConnectedError("softide_session")
        return link

    def _current(self, link: Link, token: object | None, *, cleanup: bool = False) -> bool:
        try:
            self._live(link, cleanup=cleanup)
        except ConnectionError, ValueError:
            return False
        return token is not None and token is self._subscription

    async def async_validate_linked_readiness(self) -> None:
        self._live()
        if self._subscription is None:
            raise BedNotConnectedError("softide_session")

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError()
        self._link = select_link(client, self._coordinator.connection_generation)

    async def async_on_connect(self, session: ControllerSession) -> None:
        # HA advances its public generation after capability discovery.
        if (
            self._link is None
            or session.client is not self._link.client
            or not session.is_current()
        ):
            raise BedNotConnectedError("softide_session")
        self._link = replace(self._link, generation=self._coordinator.connection_generation)
        await session.async_start_notify()

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        # The artifact reads no Device Information characteristics.
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._subscription is not None:
            return
        token = object()
        self._subscription = token

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                not self._current(link, token)
                or sender.handle != link.notify.handle
                or sender.uuid.lower() != link.notify.uuid.lower()
            ):
                return
            self.forward_raw_notification(link.notify.uuid, bytes(data))
            record = codec.softide_notification(bytes(data))
            if record is None:
                return
            self._diagnostics["last_record"] = asdict(record)
            self._receive(record, link, token)

        try:
            await link.client.start_notify(link.notify, receive)
            self._live(link)
        except BaseException:
            if self._subscription is token:
                self._subscription = None
            raise
        # The app has no BLE startup query, authentication frame or wire heartbeat.

    def _receive(self, record: codec.SoftideNotification, link: Link, token: object) -> None:
        data = record.data
        if isinstance(data, codec.SoftideFunction):
            # HA binds one selected physical connection. It deliberately refuses
            # the app's care inequality filter, which admits unrelated beds.
            if not self._selected_ble_name():
                return
            if data.Ftype == 0:
                self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES(data.timer_minutes))
            elif (
                data.Ftype == 1
                and data.FuncF == 0
                and self._state.active_program == "one_button_sleep"
            ):
                self._state.retire()
                self.forward_controller_state_updates(PROGRAM(None))
                scheduler = self._coordinator.command_scheduler
                if (
                    scheduler.active is None
                    and not scheduler.has_pending
                    and not scheduler.has_pending_stop
                ):
                    self._coordinator.resume_disconnect_timer()
            return
        pair = self._state.realtime.realtime(data, self.profile.sensors)
        if pair is not None:
            present = self._state.realtime.presence
            self.forward_controller_state_updates(
                HEART(pair[0] if pair[0] >= 0 and present else None),
                BREATHING(pair[1] if pair[1] >= 0 and present else None),
                PRESENCE(present),
                TWITCH(self._state.realtime.twitch),
            )
        now = asyncio.get_running_loop().time()
        if (
            self._selected_ble_name()
            and self._state.feed(data, self.profile.sensors, now)
            and self._followup is None
        ):
            self._queue_rest(link, token)

    def _selected_ble_name(self) -> bool:
        # Direct B003 callbacks carry the BLE device, unlike receiverTime's dvid.
        # Care's broad inequality is restricted to this selected physical target.
        return (
            bool(self.profile.identity)
            and self._coordinator.ble_device_name == self.profile.identity
        )

    def _queue_rest(self, link: Link, token: object) -> None:
        epoch = self._state.epoch
        coordinator = self._coordinator
        cancel_counter = coordinator.cancel_counter
        stop_epoch = coordinator.command_scheduler.stop_epoch

        def target_owned() -> bool:
            return (
                self._current(link, token)
                and self._selected_ble_name()
                and coordinator.cancel_counter == cancel_counter
                and coordinator.command_scheduler.stop_epoch == stop_epoch
            )

        def owned() -> bool:
            return (
                target_owned()
                and self._state.active_program == "one_button_sleep"
                and self._state.epoch is epoch
            )

        async def rest(controller: BedController) -> None:
            if controller is not self or not owned():
                return
            claimed_epoch = await self._run_program(
                "rest",
                link,
                token,
                coordinator.cancel_command,
                claim=owned,
                guard=target_owned,
            )

            def finish() -> None:
                if not target_owned() or self._state.epoch is not claimed_epoch:
                    note_frame_skipped()
                    raise asyncio.CancelledError

            await self._send(
                link,
                app.frame("disable_uploads"),
                coordinator.cancel_command,
                token,
                on_start=finish,
            )

        async def admitted(_context: CommandContext) -> None:
            # A background response must wait behind user work. The ordinary
            # command API makes shared-timer commands preempt even with False.
            await coordinator.async_execute_controller_query(rest, run_if=owned)

        async def run() -> None:
            try:
                await coordinator.command_scheduler.execute(
                    CommandIntent(admitted, cancel_running=False), expected_stop_epoch=stop_epoch
                )
            finally:
                if self._followup is asyncio.current_task():
                    self._followup = None

        self._followup = coordinator.hass.async_create_task(run(), "softide_no_data_rest")

    def invalidate_diagnostics(self) -> None:
        self._state = SoftideState()
        self._diagnostics.clear()
        self.forward_controller_state_updates(
            HEART(None),
            BREATHING(None),
            PRESENCE(None),
            TWITCH(None),
            PROGRAM(None),
            MASSAGE_TIMER_MINUTES(None),
        )

    def on_disconnect(self) -> None:
        self._link = None
        self._subscription = None
        task, self._followup = self._followup, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
        self.invalidate_diagnostics()

    async def stop_notify(self) -> None:
        link, subscribed = self._link, self._subscription is not None
        self.on_disconnect()
        if (
            link is not None
            and subscribed
            and self.client is link.client
            and link.client.is_connected
        ):
            await link.client.stop_notify(link.notify)

    async def _send(
        self,
        link: Link,
        frame: bytes,
        cancel: asyncio.Event,
        token: object | None,
        *,
        cleanup: bool = False,
        on_start: Callable[[], None] | None = None,
        on_write: Callable[[], None] | None = None,
        deadline: float | None = None,
    ) -> None:
        context, caller = current_command_context(), asyncio.current_task()
        written = False

        def delivered() -> None:
            nonlocal written
            written = True
            if on_write is not None and self._current(link, token):
                on_write()

        def admit() -> None:
            if not self._current(link, token, cleanup=cleanup):
                raise BedNotConnectedError("softide_session")
            if not cleanup and (
                cancel.is_set()
                or caller is not None
                and caller.cancelling()
                or deadline is not None
                and asyncio.get_running_loop().time() >= deadline
                or context is not None
                and (
                    not context.active
                    or context.caller_is_cancelling is not None
                    and context.caller_is_cancelling()
                    or context.hold_deadline is not None
                    and asyncio.get_running_loop().time() >= context.hold_deadline
                )
            ):
                raise asyncio.CancelledError
            if on_start is not None:
                on_start()

        await self._write_gatt_with_retry(
            link.write.uuid,
            frame,
            cancel_event=cancel,
            characteristic=link.write,
            expected_client=link.client,
            response=link.response,
            before_write=admit,
            on_write=delivered,
            track_command_write=not cleanup,
            settle_write=True,
            write_timeout=1,
        )
        if not written:
            raise asyncio.CancelledError
        # App SDK's per-request delay; all proven frames fit its 20-byte chunk.
        if not cleanup:
            await cancellable(asyncio.sleep(app.REQUEST_DELAY_MS / 1000), cancel)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = app.REFRESH_MS,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link, token = self._live(), self._subscription
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            if index:
                await cancellable(asyncio.sleep(repeat_delay_ms / 1000), cancel)
            await self._send(link, command, cancel, token)

    async def _release(self, link: Link, token: object | None) -> None:
        if not self._current(link, token, cleanup=True):
            return
        if self.profile.route == "primary":
            await settled(self._send(link, app.frame("stop"), asyncio.Event(), token, cleanup=True))
        if (context := current_command_context()) is not None:
            context.cleanup_stop_sent = True

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            f"{axis}_{direction}" for axis in self.profile.axes for direction in ("up", "down")
        ) + tuple(
            control
            for control in self.profile.controls
            if control in ("flat", "zero_g", "tv", "reading")
        )

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        action = key.removeprefix("preset_")
        return ControllerHoldSpec(action) if action in self.held_control_options else None

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= app.PRIMARY_TIMEOUT_MS
        ):
            raise invalid("softide_control")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self.perform(control, duration_ms=duration_ms)

    async def _run_program(
        self,
        action: str,
        link: Link,
        token: object | None,
        cancel: asyncio.Event,
        *,
        claim: Callable[[], bool] | None = None,
        guard: Callable[[], bool] | None = None,
    ) -> object:
        attempted = complete = released = False
        origin = target_at = asyncio.get_running_loop().time()
        epoch = self._state.epoch
        context, caller = current_command_context(), asyncio.current_task()

        def retire() -> None:
            nonlocal epoch
            self._state.retire()
            epoch = self._state.epoch
            self.forward_controller_state_updates(PROGRAM(None))

        if claim is None:
            # Public replacements retire their consumer before preparation.
            retire()

        def owned() -> bool:
            return self._state.epoch is epoch and (guard is None or guard())

        def dispatched() -> None:
            nonlocal attempted
            if not attempted and claim is not None:
                # Runs synchronously in _send's before_write under the BLE lock.
                # Moon can still end while this automatic response is waiting.
                if not claim():
                    note_frame_skipped()
                    raise asyncio.CancelledError
                retire()
            if not owned():
                note_frame_skipped()
                raise asyncio.CancelledError
            attempted = True

        def target_written() -> None:
            nonlocal target_at
            target_at = asyncio.get_running_loop().time()

        def current() -> bool:
            return (
                complete
                and owned()
                and self._current(link, token)
                and not cancel.is_set()
                and not (caller is not None and caller.cancelling())
                and (
                    context is None
                    or context.active
                    and not (
                        context.caller_is_cancelling is not None and context.caller_is_cancelling()
                    )
                )
            )

        try:
            with self.sent_state(PROGRAM(app.PROGRAMS[action][0]), is_current=current):
                if action == "one_button_sleep":
                    await self._send(link, app.frame("disable_uploads"), cancel, token)
                    origin = asyncio.get_running_loop().time()
                for index, (at, frame) in enumerate(app.program(action)):
                    await cancellable(
                        asyncio.sleep(
                            max(0, origin + at / 1000 - asyncio.get_running_loop().time())
                        ),
                        cancel,
                    )
                    await self._send(
                        link,
                        frame,
                        cancel,
                        token,
                        on_start=dispatched,
                        on_write=target_written if index == 5 else None,
                    )
                complete = True
                if not current():
                    complete = False
                    raise asyncio.CancelledError
                self._state.start(action, target_at)
                epoch = self._state.epoch
            released = True
            return epoch
        finally:
            if attempted and not released:
                await self._release(link, token)

    async def perform(self, action: str, *, duration_ms: int | None = None) -> None:
        motor = any(
            action == f"{axis}_{direction}"
            for axis in self.profile.axes
            for direction in ("up", "down")
        )
        if (
            not motor
            and action not in self.profile.controls
            and action not in self.profile.programs
            and action != "query"
            and not (action == "disable_uploads" and self.profile.route == "primary")
        ):
            raise invalid("softide_control")
        link, token, cancel = self._live(), self._subscription, self._coordinator.cancel_command
        if cancel.is_set():
            note_frame_skipped()
            return
        if action in self.profile.programs:
            await self._run_program(action, link, token, cancel)
            return
        attempted = False
        released = False

        def dispatched() -> None:
            nonlocal attempted
            attempted = True

        origin = asyncio.get_running_loop().time()
        try:
            if self._frequency_pending and action in (
                "massage_head",
                "massage_foot",
                "massage_off",
            ):
                prepared_at = asyncio.get_running_loop().time()
                await self._send(
                    link,
                    app.frame("prepare_frequency"),
                    cancel,
                    token,
                    on_start=dispatched,
                    on_write=self._frequency_prepared,
                )
                await cancellable(
                    asyncio.sleep(
                        max(
                            0,
                            prepared_at
                            + app.FREQUENCY_DELAY_MS / 1000
                            - asyncio.get_running_loop().time(),
                        )
                    ),
                    cancel,
                )
            refreshes = self.leased_hold_refreshes(app.REFRESH_MS) if motor else None
            count = (
                (
                    refreshes
                    or (
                        -(-duration_ms // app.REFRESH_MS)
                        if duration_ms is not None
                        else self._coordinator.motor_pulse_count
                    )
                )
                if motor
                else 1
            )
            start = asyncio.get_running_loop().time()
            deadline = (
                min(
                    start
                    + (
                        duration_ms / 1000
                        if duration_ms is not None
                        else count * app.REFRESH_MS / 1000
                    ),
                    start + app.PRIMARY_TIMEOUT_MS / 1000,
                )
                if motor
                else None
            )
            for index in range(count):
                await self._send(
                    link, app.frame(action), cancel, token, on_start=dispatched, deadline=deadline
                )
                if motor:
                    await cancellable(
                        asyncio.sleep(
                            max(
                                0,
                                min(start + (index + 1) * app.REFRESH_MS / 1000, deadline or start)
                                - asyncio.get_running_loop().time(),
                            )
                        ),
                        cancel,
                    )
            if not motor and duration_ms is not None:
                await cancellable(
                    asyncio.sleep(
                        max(0, origin + duration_ms / 1000 - asyncio.get_running_loop().time())
                    ),
                    cancel,
                )
            if (
                action in ("massage_head", "massage_foot", "massage_timer")
                or self.profile.route == "primary"
                and action in app.MODES
            ):
                await self._release(link, token)
                released = True
                await cancellable(
                    asyncio.sleep(
                        max(
                            0, start + app.QUERY_DELAY_MS / 1000 - asyncio.get_running_loop().time()
                        )
                    ),
                    cancel,
                )
                await self._send(link, app.frame("query"), cancel, token)
        finally:
            if attempted and not released and action not in ("query", "disable_uploads"):
                await self._release(link, token)

    async def stop_all(self) -> None:
        self._state.retire()
        self.forward_controller_state_updates(PROGRAM(None))
        if (context := current_command_context()) is not None:
            for previous in context.preempted_contexts:
                if previous.cleanup_stop_sent:
                    previous.cleanup_stop_sent = False
                    return
        await self._release(self._live(), self._subscription)

    async def move_head_up(self) -> None:
        await self.perform("combined_up" if self.profile.layout == "IQ3Y" else "back_up")

    async def move_head_down(self) -> None:
        await self.perform("combined_down" if self.profile.layout == "IQ3Y" else "back_down")

    move_back_up = move_head_up
    move_back_down = move_head_down

    async def move_feet_up(self) -> None:
        await self.perform("foot_up" if self.profile.layout == "IQ3Y" else "legs_up")

    async def move_feet_down(self) -> None:
        await self.perform("foot_down" if self.profile.layout == "IQ3Y" else "legs_down")

    move_legs_up = move_feet_up
    move_legs_down = move_feet_down
    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = stop_all

    async def preset_flat(self) -> None:
        await self.perform("flat")

    async def preset_zero_g(self) -> None:
        await self.perform("zero_g")

    async def preset_tv(self) -> None:
        await self.perform("tv")

    async def preset_reading(self) -> None:
        await self.perform("reading")

    async def preset_memory(self, memory_num: int) -> None:
        raise invalid("softide_memory")

    async def program_memory(self, memory_num: int) -> None:
        raise invalid("softide_memory")

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                {
                    "combined": "back",
                    "foot": "legs",
                    "section_a": "softide_section_a",
                    "section_b": "softide_section_b",
                }.get(axis, axis),
                _action(f"{axis}_up"),
                _action(f"{axis}_down"),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up", f"{axis}_down", stop_scope="side", press_is_native=True
                ),
            )
            for axis in self.profile.axes
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        buttons = []
        for action, label in {**app.MASSAGE, **app.MODES}.items():
            if action in self.profile.controls:
                button = massage_button(
                    f"softide_{action}", label, _action(action), scheduler_resource="*"
                )
                buttons.append(button)
        for action in self.profile.programs:
            button = catalog_button(
                f"softide_{action}",
                app.PROGRAMS[action][0],
                _action(action),
                kind=Kind.PRESET,
                scheduler_resource="*",
            )
            assert button is not None
            buttons.append(button)
        buttons.append(
            ControllerButtonSpec(
                "softide_query",
                "Refresh bed status",
                _action("query"),
                translation_key="catalog_action",
                translation_placeholders={"action": "Refresh bed status"},
                diagnostic=True,
                card=CARD_UTILITY,
            )
        )
        if self.profile.route == "primary":
            buttons.append(
                ControllerButtonSpec(
                    "softide_disable_uploads",
                    "Stop sensor updates",
                    _action("disable_uploads"),
                    translation_key="catalog_action",
                    translation_placeholders={"action": "Stop sensor updates"},
                    diagnostic=True,
                    card=CARD_UTILITY,
                )
            )
        return tuple(buttons)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            sleep_rate_sensor_spec("heart_rate", "softide_heart", HEART),
            sleep_rate_sensor_spec("breathing_rate", "softide_breathing", BREATHING),
            ControllerStateSensorSpec(
                "softide_movement",
                "softide_movement",
                TWITCH,
                "mdi:motion-sensor",
                entity_category=None,
                card=CARD_UTILITY,
                entity_registry_enabled_default=True,
            ),
            *(
                (
                    ControllerStateSensorSpec(
                        "softide_program",
                        "softide_program",
                        PROGRAM,
                        "mdi:bed",
                        entity_category=None,
                        card=CARD_PRESETS,
                        entity_registry_enabled_default=True,
                    ),
                )
                if self.profile.programs
                else ()
            ),
            massage_timer_sensor_spec(
                "softide_timer", "softide_timer", MASSAGE_TIMER_MINUTES, card=CARD_MASSAGE_TIMER
            ),
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (sleep_flag_binary_sensor_spec("bed_presence", "softide_presence", PRESENCE),)


async def build_controller(ctx: BuildContext) -> SoftideController:
    data = dict(ctx.data)
    if ctx.variant not in (None, "auto"):
        data["protocol_variant"] = ctx.variant
    return SoftideController(ctx.coordinator, app.selected(data))
