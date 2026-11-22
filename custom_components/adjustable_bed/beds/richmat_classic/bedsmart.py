"""BedSmart's resource gestures on one fenced physical BLE session."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from functools import partial
from math import ceil
from time import monotonic
from typing import TYPE_CHECKING, Final

from homeassistant.const import CONF_ADDRESS, EntityCategory
from homeassistant.exceptions import HomeAssistantError

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_CONTROLLED_SIDE, CARD_UTILITY, CardRole, CardSection
from ...codec import richmat as codec
from ...command_scheduler import note_frame_skipped
from ...const import (
    CONF_BED_TYPE,
    CONF_PRODUCT_TYPE,
    CONF_PROFILE_ID,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_CLASSIC_THIRD_SERVICE,
)
from ...controller_state import StateKey
from ...errors import failed, invalid
from ...profiles.bedsmart import ALARM_COMBINATIONS, EXCLUDED_LAYOUTS, MODE_LABELS
from ..base import CONTROLLER_GESTURE_RELEASE, BedController, require_controller
from ..cancellation import cancellable, settled
from ..entity_specs import ControllerButtonSpec, ControllerNumberSpec, ControllerSelectSpec
from .caller import Selection
from .controller import RichmatClassicController
from .lp2 import Gesture, Lp2Controller
from .profiles import Control
from .protocol import (
    ALARM_QUERY,
    AROMA_QUERY,
    INITIALIZE,
    LAMP_QUERY,
    Wire,
    aroma,
    control,
    massage_timer,
    release,
    worker_interval,
)
from .receive import MalformedFrame, ReceiveState
from .requests import Request
from .resource_protocol import BED_COMMANDS
from .transport import Transport, select

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

MODE: Final = StateKey[str | None]("bedsmart_mode")
LAMP_SECONDS: Final = StateKey[int | None]("bedsmart_lamp_seconds")
MASSAGE_INDEX: Final = StateKey[int | None]("bedsmart_massage_index")
AROMA_KEYS: Final = tuple(StateKey[int | None](f"bedsmart_aroma_{i}") for i in range(3))
_ALARMS: Final = {
    0x58: "tv",
    0x46: "anti_snore",
    0x45: "zero_g",
    0x59: "lounge",
    0x2E: "memory_1",
    0x2F: "memory_2",
    0x30: "memory_3",
    0xB0: "wake_mode_1",
    0xB1: "wake_mode_2",
    0x5D: "massage",
    0xF6: "flat_sleep",
    0x6B: "zero_g_2",
    0x4C: "head_massage",
    0x4E: "foot_massage",
}


@dataclass(frozen=True, slots=True)
class Scope:
    owner: BedSmartController
    session: Transport
    generation: int
    address: str
    data: dict[str, object]
    options: dict[str, object]
    side: str | None
    epoch: int


_SCOPE: ContextVar[Scope | None] = ContextVar("bedsmart_session", default=None)


class BedSmartController(Lp2Controller):
    """Only byte-verified caller/worker helpers are shared with the resource apps."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, device_name: str | None = None
    ) -> None:
        RichmatClassicController.__init__(
            self, coordinator, app="bedsmart", device_name=device_name
        )
        if self.layout in EXCLUDED_LAYOUTS:
            raise invalid("bedsmart_layout")
        self._selection = Selection(hold=False)
        self._deadline: float | None = None
        self._active_button = None
        self._preferences = {}
        self._ui_mode = 0
        self._scope: Scope | None = None
        self._config_data = dict(coordinator.entry.data)
        self._config_options = dict(coordinator.entry.options)
        self._known_light = self._known_aroma = False
        self._feature_event = asyncio.Event()

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {
            "mode": self._ui_mode,
            "known_light": self._known_light,
            "known_aroma": self._known_aroma,
            **super().persisted_app_state,
        }

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        # Earlier betas also stored a selected motor and head or foot; each
        # selected-motor button now names its motor, and only head sends.
        mode = state.get("mode", 0)
        if type(mode) is not int or mode not in self._model.modes:
            raise ValueError("Invalid stored BedSmart selection")
        self._ui_mode = mode
        for name in ("known_light", "known_aroma"):
            if type(state.get(name, False)) is not bool:
                raise ValueError("Invalid stored BedSmart capability")
        self._known_light = state.get("known_light", False) is True
        self._known_aroma = state.get("known_aroma", False) is True
        self._restore_wire(state)

    @contextmanager
    def _transaction(self, *, stop: bool = False) -> Iterator[Transport]:
        previous = _SCOPE.get()
        if previous is None:
            if self._scope is None:
                raise failed("bedsmart_session")
            scope = replace(
                self._scope,
                side=self.command_side,
                epoch=self._coordinator.cancel_counter,
            )
        else:
            scope = previous
        self._check(scope, stop=stop)
        token = _SCOPE.set(scope)
        try:
            yield scope.session
        finally:
            _SCOPE.reset(token)

    def _check(self, scope: Scope, *, check_side: bool = True, stop: bool = False) -> None:
        if (
            scope.owner is not self
            or self._session is not scope.session
            or self.client is not scope.session.client
            or not scope.session.client.is_connected
            or self._coordinator.controller is not self
            or self._coordinator.connection_generation != scope.generation
            or self._coordinator.address != scope.address
            or check_side
            and self.command_side != scope.side
        ):
            raise failed("bedsmart_session")
        data, options = self._coordinator.entry.data, self._coordinator.entry.options
        if not stop:
            if data != scope.data or options != scope.options:
                raise failed("bedsmart_session")
            return
        # Timing/idle changes cannot block release of this same physical bed.
        # Catalog, address or transport changes still retire the old route.
        for key in (
            CONF_ADDRESS,
            CONF_BED_TYPE,
            CONF_PROFILE_ID,
            CONF_PROTOCOL_VARIANT,
            CONF_PRODUCT_TYPE,
            CONF_RICHMAT_CLASSIC_THIRD_SERVICE,
        ):
            if data.get(key) != scope.data.get(key) or options.get(key) != scope.options.get(key):
                raise failed("bedsmart_session")
        try:
            selected = select(
                scope.session.client,
                third_service=data.get(CONF_RICHMAT_CLASSIC_THIRD_SERVICE, False),
            )
        except ValueError as err:
            raise failed("bedsmart_session") from err
        if (
            selected.write is not scope.session.write
            or selected.notify is not scope.session.notify
            or selected.wire != scope.session.wire
        ):
            raise failed("bedsmart_session")

    async def _send(
        self,
        packet: bytes,
        cancel: asyncio.Event | None = None,
        *,
        own: bool | None = None,
        stop: bool = False,
    ) -> None:
        with self._transaction(stop=stop) as session:
            if stop and packet not in {release(session.wire, mode) for mode in self._model.modes}:
                raise invalid("bedsmart_control")
            scope = _SCOPE.get()
            assert scope is not None

            def check() -> None:
                self._check(scope, stop=stop)
                if cancel is not None and self._coordinator.cancel_counter != scope.epoch:
                    note_frame_skipped()
                    raise asyncio.CancelledError

            async def write() -> None:
                await self._write_gatt_with_retry(
                    session.write.uuid,
                    packet,
                    cancel_event=cancel if cancel is not None else asyncio.Event(),
                    characteristic=session.write,
                    expected_client=session.client,
                    response=session.response,
                    before_write=check,
                    track_command_write=cancel is not None if own is None else own,
                )

            # Drain an ATT write before STOP can take its lane and record delivery
            # even when cancellation arrives while Bleak is completing the write.
            await settled(write())

    async def _iteration(self, cancel: asyncio.Event, mode: int) -> bool:
        session = self._session
        if session is None:
            raise failed("bedsmart_session")
        if self._worker.mode == 1 and self._deadline is not None and monotonic() >= self._deadline:
            self._worker.mode = 0
        for emission in self._worker.tick():
            if emission.delay_ms and not await self._wait_pending(
                emission.delay_ms, cancel, pending=emission.payload != bytes((codec.STOP,))
            ):
                return False
            if cancel.is_set():
                if emission.payload != bytes((codec.STOP,)):
                    note_frame_skipped()
                return False
            if emission.payload is None:
                note_frame_skipped()
                if session.wire == "FRAMED":
                    raise invalid("bedsmart_control")
                continue
            try:
                await self._send(
                    control(emission.payload, session.wire, mode),
                    None if emission.payload == bytes((codec.STOP,)) else cancel,
                )
            except asyncio.CancelledError:
                if self._pending_refresh():
                    note_frame_skipped()
                raise
        return True

    def _pending_refresh(self) -> bool:
        return self._worker.mode == 3 or (
            self._worker.mode == 1
            and (
                self._deadline is None or monotonic() + self._worker.tick_ms / 1000 < self._deadline
            )
        )

    async def _wait_pending(
        self, milliseconds: int, cancel: asyncio.Event, *, pending: bool
    ) -> bool:
        try:
            ready = await self._wait(milliseconds, cancel)
        except asyncio.CancelledError:
            if pending:
                note_frame_skipped()
            raise
        if not ready and pending:
            note_frame_skipped()
        return ready

    async def _next_tick(self, cancel: asyncio.Event) -> bool:
        delay = self._worker.tick_ms
        if self._worker.mode == 1 and self._deadline is not None:
            delay = min(delay, max(0, ceil((self._deadline - monotonic()) * 1000)))
        return await self._wait_pending(delay, cancel, pending=self._pending_refresh())

    async def _release(self, delay_ms: int = 0, *, mode: int | None = None) -> None:
        scope = _SCOPE.get()
        if scope is None or scope.owner is not self:
            with self._transaction(stop=True):
                await self._release(delay_ms, mode=mode)
            return

        async def cleanup() -> None:
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000)
            # A retired physical target must never receive a replacement's STOP.
            try:
                self._check(scope, stop=True)
            except HomeAssistantError:
                return
            await self._send(
                release(scope.session.wire, self._mode if mode is None else mode), stop=True
            )

        await settled(cleanup())

    async def execute_action(
        self,
        node: int,
        *,
        long: bool = False,
        hold_ms: int | None = None,
        mode: int | None = None,
        head: bool = True,
        flag: str = "53",
        held: bool = False,
    ) -> None:
        with self._transaction():
            button = RichmatClassicController._button(self, node)
            if self.layout == "E3RM" and button.extra == "100":
                if long:
                    selected_mode = self._ui_mode if mode is None else mode
                    self.validate_action(node, long=True)
                    assert button.long is not None and self._session is not None
                    try:
                        await self.write_command(
                            control(bytes.fromhex(button.long), self._session.wire, selected_mode)
                        )
                    finally:
                        await self._release(50, mode=selected_mode)
                    return
                held = True
            await super().execute_action(
                node,
                long=long,
                hold_ms=hold_ms,
                mode=self._ui_mode if mode is None else mode,
                head=head,
                flag=flag,
                held=held,
            )

    def _gesture(
        self,
        node: int,
        wire: Wire,
        *,
        long: bool = False,
        held: bool = False,
        head: bool = True,
        flag: str = "53",
    ) -> Gesture:
        gesture = super()._gesture(node, wire, long=long, held=held, head=head, flag=flag)
        button = RichmatClassicController._button(self, node)
        return (
            replace(gesture, status=1)
            if self.layout == "E3RM" and button.extra == "100" and not long
            else gesture
        )

    def _flags(self, button: Control) -> tuple[str, ...]:
        # The app's motor selector: one button per motor instead.
        if self.layout == "U3RM" and button.tag in ("51", "52"):
            return ("53", "54", "55")
        return super()._flags(button)

    async def stop_all(self) -> None:
        self._worker.cancel()
        if not CONTROLLER_GESTURE_RELEASE.get():
            await self._release(50, mode=self._ui_mode)

    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all

    @property
    def _mode_options(self) -> tuple[str, ...]:
        """The app's bed modes in order: a side on Left/Right layouts."""
        labels = MODE_LABELS.get(self.layout, ())
        if labels == ("Left", "Right"):
            return ("left", "right")
        return tuple(f"mode_{index}" for index, _label in enumerate(labels, 1))

    def _publish(self) -> None:
        super()._publish()
        options = self._mode_options
        self.forward_controller_state_updates(MODE(options[self._ui_mode] if options else None))

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        # The mode is the side byte of every later FRAMED command; RAW frames
        # carry none, so a RAW or not yet connected bed lists no select.
        options = self._mode_options
        if not options or self._resolved_wire != "FRAMED":
            return ()

        def choose(value: str) -> None:
            if value not in options:
                raise invalid("bedsmart_control")
            self._ui_mode = options.index(value)
            self._publish()

        async def selected(_controller: BedController, value: str) -> None:
            choose(value)

        side = options == ("left", "right")
        return (
            ControllerSelectSpec(
                "bedsmart_mode",
                "bedsmart_side" if side else "bedsmart_mode",
                MODE,
                options,
                selected,
                local_select_fn=choose,
                card=CARD_CONTROLLED_SIDE if side else CARD_UTILITY,
            ),
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise failed("bedsmart_session")
        if (
            self._coordinator.entry.data != self._config_data
            or self._coordinator.entry.options != self._config_options
        ):
            raise failed("bedsmart_session")
        session = select(
            client,
            third_service=self._coordinator.entry.data.get(
                CONF_RICHMAT_CLASSIC_THIRD_SERVICE, False
            ),
        )
        self._session, self._wire = session, session.wire
        self._worker.cancel()
        name = self._device_name or self._coordinator.entry.data.get("ble_device_name")
        self._worker.set_interval(worker_interval(name, session.wire, rise=True))
        self._receive = ReceiveState()
        self._feature_event = asyncio.Event()
        self._scope = Scope(
            self,
            session,
            self._coordinator.connection_generation,
            self._coordinator.address,
            self._config_data,
            self._config_options,
            self.command_side,
            self._coordinator.cancel_counter,
        )
        try:
            with self._transaction():
                self._notifications_started = False
                if session.has_notifications:
                    result = await client.start_notify(
                        session.notify, partial(self._notification, session)
                    )
                    self._notifications_started = result is not False
                if session.wire == "FRAMED" and self._notifications_started:
                    await asyncio.sleep(0.3)
                    await self._send(INITIALIZE)
        except BaseException:
            self._session = self._scope = None
            raise
        self._publish()

    def _notification(
        self, session: Transport, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        scope = self._scope
        if scope is None or scope.session is not session:
            return
        try:
            self._check(scope, check_side=False)
        except HomeAssistantError:
            return
        self.forward_raw_notification(sender.uuid, bytes(data))
        if len(self._receive.buffer) + len(data) * 2 > 256:
            self._receive.buffer = ""
            return
        try:
            self._receive.feed(
                bytes(data),
                app="bedsmart",
                layout=self.layout,
                desk_bound=False,
                table_controls_bound=False,
            )
        except MalformedFrame:
            self._rejection = "Malformed notification"
        self._known_light |= self._receive.light_capable
        self._known_aroma |= self._receive.aroma_capable
        self._feature_event.set()
        self._publish()

    def on_disconnect(self) -> None:
        self._scope = None
        self._receive = ReceiveState()
        super().on_disconnect()
        self.forward_controller_state_updates(
            LAMP_SECONDS(None), MASSAGE_INDEX(None), *(key(None) for key in AROMA_KEYS)
        )

    async def query_settings(self, *, own: bool = True) -> None:
        with self._transaction():
            await self._frames(
                (*((ALARM_QUERY,) if self._alarm_actions() else ()), LAMP_QUERY, AROMA_QUERY),
                500,
                own=own,
            )

    async def ensure_feature(self, *, aroma: bool = False) -> None:
        """Prove a settings capability on the link that will receive its write."""
        with self._transaction():

            def supported() -> bool:
                return self._receive.aroma_capable if aroma else self._receive.light_capable

            if not supported():
                await self.query_settings(own=False)
            if not supported():
                try:
                    # HA readiness bound, not a recovered device timer.
                    async with asyncio.timeout(1):
                        while not supported():
                            self._feature_event.clear()
                            await cancellable(
                                self._feature_event.wait(), self._coordinator.cancel_command
                            )
                except TimeoutError as err:
                    raise invalid("bedsmart_control") from err
            scope = _SCOPE.get()
            assert scope is not None
            self._check(scope)

    async def _frames(self, packets: tuple[bytes, ...], gap: int = 0, *, own: bool = True) -> None:
        cancel = self._coordinator.cancel_command
        for index, packet in enumerate(packets):
            if cancel.is_set():
                if own:
                    note_frame_skipped()
                return
            pending = index + 1 < len(packets)
            try:
                await self._send(packet, cancel, own=own)
            except asyncio.CancelledError:
                if own and pending:
                    note_frame_skipped()
                raise
            if pending and gap and not await self._wait_pending(gap, cancel, pending=own):
                return

    async def bed_command(self, command: str, duration_ms: int = 1000) -> None:
        """The app's named BED callers, independent of a layout's old getters."""
        if (
            command not in BED_COMMANDS
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 60000
        ):
            raise invalid("bedsmart_control")
        with self._transaction() as session:
            code, held = BED_COMMANDS[command]
            mode = self._ui_mode
            cancel = self._coordinator.cancel_command
            deadline = monotonic() + duration_ms / 1000
            try:
                while not cancel.is_set():
                    await self.write_command(control(bytes((code,)), session.wire, mode))
                    if not held or monotonic() >= deadline:
                        return
                    next_tick = monotonic() + self._worker.tick_ms / 1000
                    if not await self._wait_pending(
                        min(self._worker.tick_ms, max(0, ceil((deadline - monotonic()) * 1000))),
                        cancel,
                        pending=next_tick < deadline,
                    ):
                        return
                    if monotonic() >= deadline:
                        return
                note_frame_skipped()
            except asyncio.CancelledError:
                if held and monotonic() + self._worker.tick_ms / 1000 < deadline:
                    note_frame_skipped()
                raise
            finally:
                await self._release(50 if held else 150, mode=mode)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        lights = self._light_keys()
        specs = [
            s
            for s in super().controller_button_specs
            if s.key.removesuffix("_raw").removesuffix("_framed") not in lights
        ]
        specs = [
            replace(s, requires_confirmation=False)
            if s.card.role is CardRole.SAVE and s.card.section is CardSection.MEMORY
            else s
            for s in specs
        ]
        specs.append(
            ControllerButtonSpec(
                "bedsmart_query",
                "Refresh bed features",
                lambda c: require_controller(c, BedSmartController).query_settings(),
                translation_key="bedsmart_query",
                diagnostic=True,
                entity_registry_enabled_default=False,
                cancel_movement=False,
                scheduler_resource="configuration",
            )
        )
        return tuple(specs)

    def _light_gesture(self, wire: Wire) -> Gesture | None:
        return next(
            (
                g
                for g in self._gestures(wire)
                if self._resource(g) == "k_ubl_on_off" and not g.long and not g.held
            ),
            None,
        )

    def _format_entity_keys(self) -> set[tuple[str, str]]:
        keys = super()._format_entity_keys()
        if self._mode_options:
            keys.add(("select", "controller_select_bedsmart_mode"))
        return keys

    def _light_keys(self) -> set[str]:
        """The light gesture of the bed's format, or of either before it is known.

        The shared light entities stay until the format is known, as on a
        paired bed's parent; only a session in the light's format can toggle it.
        """
        wire = self._resolved_wire
        return {
            g.key
            for w in ((wire,) if wire else ("RAW", "FRAMED"))
            if (g := self._light_gesture(w)) is not None
        }

    @property
    def supports_lights(self) -> bool:
        return bool(self._light_keys())

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    async def lights_toggle(self) -> None:
        with self._transaction() as session:
            gesture = self._light_gesture(session.wire)
            if gesture is None:
                raise invalid("bedsmart_control")
            await self.execute_action(gesture.node)

    def controller_button_available(self, key: str) -> bool:
        if key == "bedsmart_query":
            return True
        return super().controller_button_available(key)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs = []
        if self._known_light or self._receive.light_capable:

            async def timer(c: BedController, value: float) -> None:
                assert isinstance(c, BedSmartController)
                await c.settings(seconds=int(value))

            specs.append(
                ControllerNumberSpec(
                    "bedsmart_lamp_seconds",
                    "bedsmart_lamp_seconds",
                    LAMP_SECONDS,
                    0,
                    300,
                    1,
                    timer,
                    "s",
                )
            )
        if self.layout in ("D1RM", "D9RM"):

            async def massage(c: BedController, value: float) -> None:
                assert isinstance(c, BedSmartController)
                with c._transaction(), c.sent_state(MASSAGE_INDEX(int(value))):
                    await c._frames((massage_timer(c.layout, int(value)),))

            specs.append(
                ControllerNumberSpec(
                    "bedsmart_massage_index",
                    "bedsmart_massage_index",
                    MASSAGE_INDEX,
                    0,
                    5,
                    1,
                    massage,
                )
            )
        if self._known_aroma or self._receive.aroma_capable:
            for index, limit in enumerate((60, 60, 12)):

                async def aroma_time(c: BedController, value: float, *, i=index) -> None:
                    assert isinstance(c, BedSmartController)
                    await c.set_aroma_time(i, int(value))

                specs.append(
                    ControllerNumberSpec(
                        f"bedsmart_aroma_{index}",
                        f"bedsmart_aroma_{index}",
                        AROMA_KEYS[index],
                        1,
                        limit,
                        1,
                        aroma_time,
                        "h" if index == 2 else "min",
                        entity_registry_enabled_default=False,
                        entity_category=EntityCategory.CONFIG,
                    )
                )
        return tuple(specs)

    def validate_richmat_classic_request(self, request: Request) -> None:
        if request.operation != "query":
            raise invalid("bedsmart_control")

    async def async_execute_richmat_classic_request(self, request: Request) -> None:
        self.validate_richmat_classic_request(request)
        await self.query_settings()

    async def settings(
        self,
        *,
        color: tuple[int, int, int] | None = None,
        seconds: int | None = None,
        aroma_times: tuple[int, int, int] | None = None,
        fan: str | None = None,
        level: int = 0,
        duration: int = 0,
    ) -> None:
        if fan is not None or level or duration:
            raise invalid("bedsmart_control")
        with self._transaction():
            if color is not None:
                if len(color) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in color):
                    raise invalid("bedsmart_control")
                await self.ensure_feature()
                await self._frames((codec.rgb(*color),))
            elif seconds is not None:
                if type(seconds) is not int or not 0 <= seconds <= 300:
                    raise invalid("bedsmart_control")
                await self.ensure_feature()
                with self.sent_state(LAMP_SECONDS(seconds)):
                    await self._frames((codec.light_timer(seconds >> 8, seconds),))
            elif aroma_times is not None:
                if len(aroma_times) != 3 or any(
                    type(v) is not int or not 1 <= v <= limit
                    for v, limit in zip(aroma_times, (60, 60, 12), strict=True)
                ):
                    raise invalid("bedsmart_control")
                await self.ensure_feature(aroma=True)
                for index, value in enumerate(aroma_times):
                    try:
                        with self.sent_state(AROMA_KEYS[index](value)):
                            await self._frames((aroma(0x1B + index, value),))
                    except asyncio.CancelledError:
                        if index < 2:
                            note_frame_skipped()
                        raise
                    if index < 2 and not await self._wait_pending(
                        150, self._coordinator.cancel_command, pending=True
                    ):
                        return
            else:
                raise invalid("bedsmart_control")

    async def set_aroma_time(self, index: int, value: int) -> None:
        if (
            index not in (0, 1, 2)
            or type(value) is not int
            or not 1 <= value <= (60, 60, 12)[index]
        ):
            raise invalid("bedsmart_control")
        with self._transaction():
            await self.ensure_feature(aroma=True)
            with self.sent_state(AROMA_KEYS[index](value)):
                await self._frames((aroma(0x1B + index, value),))
            await self._wait(150, self._coordinator.cancel_command)

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return self.layout == "Y6RM"

    async def set_massage_timer(self, minutes: int) -> None:
        if minutes == 0 and self.layout == "Y6RM":
            from ...state_keys import MASSAGE_TIMER_MINUTES
            from .protocol import massage_popup

            with self._transaction(), self.sent_state(MASSAGE_TIMER_MINUTES(0)):
                await self._frames((massage_popup("toggle"),))
            return
        await super().set_massage_timer(minutes)

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        owned = self._alarm_actions().values()
        actions = tuple(dict.fromkeys(_ALARMS[c] for c in owned if c in _ALARMS))
        zones = self._alarm_zones()
        return (
            AlarmCapability(
                wake_actions=(*actions, "none"),
                massage=bool(zones),
                massage_zones=tuple(zones),
                requires_wake_action=False,
                live_check=True,
            )
            if owned
            else None
        )

    def _alarm_code(self, alarm: AlarmRequest) -> int:
        if not alarm.enabled:
            return 0
        owned = self._alarm_actions().values()
        bed = next((c for c in owned if _ALARMS.get(c) == alarm.wake_action), None)
        massage = self._alarm_zones().get(alarm.massage_zone or "both") if alarm.massage else None
        if alarm.wake_action != "none" and bed is None or alarm.massage and massage is None:
            raise invalid("bedsmart_control")
        if bed in (0x5D, 0x4C, 0x4E):
            return bed if massage is None or massage == bed else 0x5D
        if bed is None:
            if massage is None:
                raise invalid("bedsmart_control")
            return massage
        if massage is None:
            return bed
        combined = ALARM_COMBINATIONS.get(bed)
        if combined is None or combined[(0x5D, 0x4C, 0x4E).index(massage)] is None:
            raise invalid("bedsmart_control")
        return combined[(0x5D, 0x4C, 0x4E).index(massage)]
