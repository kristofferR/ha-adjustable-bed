"""Dream Sense Bed: product-owned controls on one captured BLE session."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, Final

from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.const import STATE_UNKNOWN
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...app_session import app_session
from ...card import CARD_HIDDEN, CARD_LIGHTING
from ...codec import richmat as codec
from ...command_scheduler import (
    Delivery,
    current_command_context,
    delivered,
    note_frame_skipped,
    note_frame_written,
    note_write_not_counted,
)
from ...const import CONF_PRODUCT_TYPE, CONF_PROTOCOL_VARIANT, SIDE_LEFT, SIDE_RIGHT
from ...controller_state import StateKey, StateUpdate
from ...errors import invalid
from ...execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities
from ...profiles.dreamsense import (
    ALARM_NAMES,
    BLUE_LIGHT_TIMERS,
    EXPIRY_MS,
    PROBE_MS,
    PROFILES,
    TICK_MS,
    Action,
)
from ...state_keys import LIGHT_TIMER_OPTION, MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_RGB
from ..base import CONTROLLER_GESTURE_RELEASE, BedController, require_controller
from ..builder import BuildContext
from ..cancellation import cancellable, settled
from ..catalog_buttons import Kind, catalog_button, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
)
from ..lifecycle import CapabilitySnapshotPolicy, ControllerSession
from . import protocol as p
from .receive import Receive
from .transport import ROUTES, Session, select

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

_SCOPE: ContextVar[tuple[BedController, Session] | None] = ContextVar(
    "dreamsense_session", default=None
)
LIGHT_SECONDS: Final = StateKey[int | None]("dreamsense_light_seconds")
SPLIT: Final = StateKey[bool | None]("dreamsense_split")
SYNC: Final = StateKey[bool | None]("dreamsense_sync")
SELECTED_SIDE: Final = StateKey[str | None]("dreamsense_selected_side")
ALARMS: Final = StateKey[dict[str, object] | None]("dreamsense_alarms")
ACK: Final = StateKey[str | None]("dreamsense_alarm_ack")


async def build_controller(ctx: BuildContext) -> BedController:
    return DreamSenseController(
        ctx.coordinator,
        product=ctx.variant
        if ctx.variant in PROFILES
        else str(ctx.data.get(CONF_PRODUCT_TYPE, "blue")),
        product_known=ctx.variant in PROFILES or CONF_PRODUCT_TYPE in ctx.data,
        capability_snapshot=ctx.stored_capabilities("dreamsense"),
    )


async def _press(controller: BedController, action: str, save: bool = False) -> None:
    await require_controller(controller, DreamSenseController).press(action, save=save)


@dataclass(slots=True)
class Selection:
    side: str = SIDE_LEFT
    single: bool | None = None


class DreamSenseController(BedController):
    """No retained FIFO intent can cross a connection or product change."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        product: str = "blue",
        product_known: bool = True,
        capability_snapshot: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(coordinator)
        if product not in PROFILES:
            raise invalid("dreamsense_product")
        self.profile = PROFILES[product]
        # Blue's light duration is its own slider; an entry that stores no
        # product keeps the plain seconds until it does.
        self._blue_light = product == "blue" and product_known
        # The other products' slider reaches 900; an entry with no stored
        # product keeps the older 300.
        self._light_seconds_max = 900 if product_known and product != "blue" else 300
        self._session: Session | None = None
        self._last_write: float | None = None
        self._receive = Receive()
        self._expiry: asyncio.TimerHandle | None = None
        self._alarm_event = asyncio.Event()
        self._selection = app_session(
            coordinator.hass, coordinator.address, ("dreamsense_selection", product), Selection
        )
        self.forward_controller_state_updates(SELECTED_SIDE(self._selection.side))
        self._active_action = False
        self._local_stop = asyncio.Event()
        saved = capability_snapshot or {}
        single = saved.get("single")
        if (
            self._selection.single is None
            and saved.get("product") == product
            and isinstance(single, bool)
        ):
            self._selection.single = single
        self._known = {
            name
            for name in ("clock", "light", "music")
            if saved.get("product") == product and saved.get(name) is True
        }

    @property
    def control_characteristic_uuid(self) -> str:
        return self._session.write.uuid if self._session else ROUTES[0][1]

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # The product's named direction buttons own the motor surface.
        return ()

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def auto_enable_massage(self) -> bool:
        return any(a.action.startswith("Massage") for a in self.profile.controls)

    @property
    def supports_single_address_pairing(self) -> bool:
        return self.profile.side and self._session is not None and not self._session.single

    def _side(self) -> int:
        side = self.command_side or self._selection.side
        if side == SIDE_RIGHT and (not self.profile.side or self._live().single):
            raise invalid("dreamsense_side")
        return int(side == SIDE_RIGHT)

    @contextmanager
    def _transaction(self) -> Iterator[Session]:
        session = self._live()
        token = _SCOPE.set((self, session))
        try:
            yield session
        finally:
            _SCOPE.reset(token)

    def _owns(self, session: Session) -> bool:
        return (
            self._session is session
            and self.client is session.client
            and self._coordinator.controller is self
            and session.client.is_connected
            and session.generation == self._coordinator.connection_generation
        )

    def _current(self, session: Session) -> bool:
        return (
            self._owns(session)
            and self._coordinator.entry.data.get(CONF_PROTOCOL_VARIANT, session.product)
            in (session.product, "auto")
            and self._coordinator.entry.data.get(
                CONF_PRODUCT_TYPE, self._coordinator.entry.data.get(CONF_PROTOCOL_VARIANT, "blue")
            )
            == session.product
        )

    def _live(self) -> Session:
        scope = _SCOPE.get()
        session = scope[1] if scope and scope[0] is self else self._session
        if session is None or not self._current(session):
            raise invalid("dreamsense_session")
        return session

    @contextmanager
    def sent_state(
        self, *updates: StateUpdate, is_current: Callable[[], bool] | None = None
    ) -> Iterator[None]:
        session = self._live()

        def show(delivery: Delivery) -> None:
            if (
                not updates
                or not self._current(session)
                or is_current is not None
                and not is_current()
            ):
                return
            if delivery is Delivery.SENT:
                self.forward_controller_state_updates(*updates)
            elif delivery is Delivery.PARTIAL:
                self.forward_controller_state_updates(
                    *(
                        StateUpdate(
                            update.key,
                            STATE_UNKNOWN if update.key == MASSAGE_TIMER_MINUTES else None,
                        )
                        for update in updates
                    )
                )

        with delivered(show):
            yield

    async def _send(
        self,
        packet: bytes,
        cancel: asyncio.Event | None = None,
        *,
        own: bool = True,
        on_write: Callable[[], None] | None = None,
        validate: Callable[[], object] | None = None,
        release_session: Session | None = None,
        not_after: float | None = None,
    ) -> bool:
        session = release_session if release_session is not None else self._live()

        def admitted() -> bool:
            return self._owns(session) if release_session is not None else self._current(session)

        async with self.ble_lock:

            async def write() -> bool:
                # This check is inside the actual writer task, not its waiting parent.
                if not admitted():
                    raise invalid("dreamsense_session")
                if cancel is not None and cancel.is_set():
                    if own:
                        note_frame_skipped()
                    return False
                if self._last_write is not None:
                    delay = max(0, TICK_MS - (monotonic() - self._last_write) * 1000)
                    if delay:
                        try:
                            await self._wait(round(delay), cancel)
                        except asyncio.CancelledError:
                            if own:
                                note_frame_skipped()
                            raise
                if not admitted():
                    raise invalid("dreamsense_session")
                if cancel is not None and cancel.is_set():
                    if own:
                        note_frame_skipped()
                    return False
                if not_after is not None and monotonic() >= not_after:
                    if own:
                        note_frame_skipped()
                    return False
                if validate is not None:
                    validate()
                self._last_write = monotonic()
                self._record_command_trace(
                    session.write.uuid,
                    packet,
                    response=session.response,
                    characteristic=session.write,
                )
                await session.client.write_gatt_char(
                    session.write, packet, response=session.response
                )
                if on_write is not None:
                    on_write()
                if own:
                    note_frame_written(cancel)
                else:
                    note_write_not_counted()
                return True

            return await settled(write())

    async def _wait(self, milliseconds: int, event: asyncio.Event | None = None) -> None:
        await cancellable(asyncio.sleep(milliseconds / 1000), event)

    async def async_on_connect(self, session: ControllerSession) -> None:
        # These notifications carry capabilities even when position sensing is disabled.
        await self.start_notify()
        session.persist_capability_snapshot()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise invalid("dreamsense_session")
        if self._session is not None:
            if (
                self._session.client is client
                and self._session.generation == self._coordinator.connection_generation
            ):
                return
            self.on_disconnect()
        selected = select(client, self._coordinator.connection_generation, self.profile.product)
        self._session = selected
        self._selection.single = selected.single
        self._last_write = None
        self._receive = Receive()
        self.forward_controller_state_updates(SELECTED_SIDE(self._selection.side))
        try:
            with self._transaction():
                subscribed = await client.start_notify(
                    selected.notify, partial(self._notification, selected)
                )
                if subscribed is False:
                    raise invalid("dreamsense_transport")
                await self._send(
                    self.profile.frame(
                        0, single=selected.single, action="deviceFunctionItemExitLimit"
                    ),
                    own=False,
                )
                menu_started = monotonic()
                # Clock sync is independent of capability replies and the menu timer.
                if self.profile.clock:
                    await self._clock(own=False)
                # Product menu probes are unconditional and ordered. Their replies gate UI only.
                for index, action in enumerate(("CheckClock", "CheckLight", "CheckMusic"), 1):
                    deadline = menu_started + index * PROBE_MS / 1000
                    await self._wait(max(0, round((deadline - monotonic()) * 1000)))
                    await self._send(
                        self.profile.frame(
                            1, single=selected.single, action="deviceFunctionItem" + action
                        ),
                        own=False,
                    )
                if self.profile.split:
                    await self._send(p.split_query(), own=False)
        except BaseException:
            self.on_disconnect()
            raise

    def _notification(
        self, session: Session, _sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        if (
            self._session is not session
            or self.client is not session.client
            or self._coordinator.controller is not self
            or not session.client.is_connected
            or self._coordinator.connection_generation != session.generation
            or self._coordinator.entry.data.get(CONF_PROTOCOL_VARIANT, session.product)
            not in (session.product, "auto")
            or self._coordinator.entry.data.get(
                CONF_PRODUCT_TYPE, self._coordinator.entry.data.get(CONF_PROTOCOL_VARIANT, "blue")
            )
            != session.product
        ):
            return
        self.forward_raw_notification(session.notify.uuid, bytes(data))
        if self._expiry is not None:
            self._expiry.cancel()
            self._expiry = None
        revision = self._receive.alarm_revision
        self._receive.feed(bytes(data))
        self._known.update(self._receive.capabilities)
        if self._receive.pending:
            self._expiry = asyncio.get_running_loop().call_later(
                EXPIRY_MS / 1000, self._receive.expire
            )
        if revision != self._receive.alarm_revision:
            self._alarm_event.set()
        self.forward_controller_state_updates(
            SPLIT(self._receive.split),
            ACK(self._receive.last_ack),
            ALARMS({str(k): asdict(v) for k, v in self._receive.alarms.items()}),
        )

    def on_disconnect(self) -> None:
        self._session = None
        self._local_stop.set()
        if self._expiry is not None:
            self._expiry.cancel()
            self._expiry = None
        self._receive = Receive()
        self._alarm_event.set()
        self.forward_controller_state_updates(
            SPLIT(None),
            SYNC(None),
            LIGHT_SECONDS(None),
            LIGHT_TIMER_OPTION(None),
            StateUpdate(MASSAGE_TIMER_MINUTES, STATE_UNKNOWN),
            UNDER_BED_LIGHTS_RGB(None),
            ALARMS(None),
            ACK(None),
        )

    async def stop_notify(self) -> None:
        session = self._session
        self.on_disconnect()
        if session is not None and session.client.is_connected:
            await session.client.stop_notify(session.notify)

    @property
    def capability_snapshot_policy(self) -> CapabilitySnapshotPolicy:
        return CapabilitySnapshotPolicy(deferred_reload=True, after_operations=True)

    def capability_snapshot(self) -> dict[str, object]:
        return {
            "product": self.profile.product,
            "single": self._selection.single,
            **{k: k in self._known for k in ("clock", "light", "music")},
        }

    def _gate(self, name: str) -> bool:
        allowed = {
            "clock": self.profile.clock,
            "light": self.profile.light,
            "music": self.profile.vibration,
        }[name]
        return allowed and name in self._receive.capabilities

    def _physical(self) -> None:
        if self.command_side in (SIDE_LEFT, SIDE_RIGHT):
            raise invalid("dreamsense_physical")

    def _action(self, name: str, save: bool = False) -> Action:
        action = next((a for a in self.profile.controls if a.action == name), None)
        if action is None or save and action.save is None:
            raise invalid("dreamsense_action")
        return action

    async def press(
        self,
        name: str,
        *,
        save: bool = False,
        duration_ms: int = 1000,
        updates: tuple[StateUpdate, ...] = (),
    ) -> None:
        action = self._action(name, save)
        if not 1 <= duration_ms <= 60000:
            raise invalid("dreamsense_action")
        cancel = self._coordinator.cancel_command
        with self._transaction() as session:
            side = self._side()
            code = action.save if save else action.code
            assert code is not None
            packet = self.profile.frame(code, single=session.single, side=side)
            local = self._local_stop = asyncio.Event()
            held = action.held and not save
            context = current_command_context()
            leased = context is not None and context.lease is not None
            self._active_action = True
            deadline = monotonic() + duration_ms / 1000
            sent = False
            frame_sent = False
            elapsed = 0

            def wrote() -> None:
                nonlocal sent, frame_sent
                sent = frame_sent = True

            try:
                with self.sent_state(*updates):
                    try:
                        if save and action.save_delay_ms:
                            await self._wait(action.save_delay_ms, cancel)
                        elapsed = 0
                        if held and not leased and duration_ms < TICK_MS:
                            await self._wait(duration_ms, cancel)
                            note_frame_skipped()
                            return
                        while True:
                            if cancel.is_set() or local.is_set():
                                note_frame_skipped()
                                break
                            if held:
                                if elapsed and not leased and monotonic() >= deadline:
                                    note_frame_skipped()
                                    break
                                delay = (
                                    TICK_MS
                                    if not elapsed or self._last_write is None
                                    else max(
                                        0,
                                        TICK_MS - (monotonic() - self._last_write) * 1000,
                                    )
                                )
                                if sent and not leased:
                                    delay = min(
                                        delay,
                                        max(0, (deadline - monotonic()) * 1000),
                                    )
                                await self._wait(round(delay), cancel)
                                elapsed += TICK_MS
                                if local.is_set():
                                    note_frame_skipped()
                                    break
                            frame_sent = False
                            written = await self._send(
                                packet,
                                cancel,
                                on_write=wrote,
                                # The first source tick waits 100 ms, including
                                # timer jitter. The deadline suppresses repeats.
                                not_after=deadline if held and not leased and sent else None,
                            )
                            if not written:
                                break
                            if not held or not leased and elapsed >= duration_ms:
                                break
                    except asyncio.CancelledError:
                        if not frame_sent or held and (leased or elapsed < duration_ms):
                            note_frame_skipped()
                        raise
            finally:
                try:
                    if sent and action.release and not save:
                        await self._release(session, side)
                finally:
                    self._active_action = False

    async def _release(self, session: Session, side: int) -> None:
        async def cleanup() -> None:
            # Configuration may change before reload. Only ownership of the
            # original physical link, never the new product, gates its release.
            if self._owns(session):
                await self._send(
                    codec.function(codec.STOP, single=session.single, side=side),
                    asyncio.Event(),
                    own=False,
                    release_session=session,
                )

        await settled(cleanup())

    async def stop_all(self) -> None:
        self._local_stop.set()
        if not self._active_action and not CONTROLLER_GESTURE_RELEASE.get():
            with self._transaction() as session:
                await self._release(session, 0 if session.single else self._side())

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        result: list[ControllerButtonSpec | None] = []
        for action in self.profile.controls:
            if (
                "MinuteTimer" in action.action
                or action.action in ("SyncOn", "SyncOff")
                and self._has_sync_pair
            ):
                continue
            hold = (
                ControllerHoldSpec(action.action, release_button_key="dreamsense_release")
                if action.held
                else None
            )
            result.append(
                catalog_button(
                    action.action, action.label, partial(_press, action=action.action), hold=hold
                )
            )
            if action.save is not None:
                result.append(
                    catalog_button(
                        "save_" + action.action,
                        "Save " + action.label,
                        partial(_press, action=action.action, save=True),
                    )
                )
        if self.profile.light and "light" in self._known | self._receive.capabilities:
            result.append(
                catalog_button("dreamsense_light_close", "Underbed light off", _close_light)
            )
        if self.profile.vibration and "music" in self._known | self._receive.capabilities:
            result.append(
                catalog_button(
                    "dreamsense_vibration", "Vibration mode", _vibration, kind=Kind.MASSAGE
                )
            )
        if self.profile.repeat:
            result.append(
                catalog_button(
                    "dreamsense_refresh_alarms",
                    "Refresh alarms",
                    _refresh_alarms,
                    kind=Kind.EXTRA,
                    diagnostic=True,
                )
            )
        result.append(
            ControllerButtonSpec(
                "dreamsense_release",
                "Release",
                lambda c: c.stop_all(),
                translation_key="richmat_classic_release",
                release_only=True,
                card=CARD_HIDDEN,
            )
        )
        return unique_buttons(result)

    def controller_button_available(self, key: str) -> bool:
        if key == "dreamsense_light_close":
            return self._gate("light") and self.command_side is None
        if key == "dreamsense_vibration":
            return self._gate("music") and self.command_side is None
        return any(s.key == key for s in self.controller_button_specs)

    @property
    def execution(self) -> ExecutionCapabilities:
        controls = frozenset(a.action for a in self.profile.controls if a.held)
        return (
            ExecutionCapabilities(hold="stream", hold_controls=controls)
            if controls
            else NO_EXECUTION_CAPABILITIES
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(a.action for a in self.profile.controls if a.held)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or not 1 <= duration_ms <= 60000:
            raise invalid("dreamsense_action")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self.press(control, duration_ms=duration_ms)

    @property
    def _has_sync_pair(self) -> bool:
        return {"SyncOn", "SyncOff"} <= {a.action for a in self.profile.controls}

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        result = []
        if self._has_sync_pair:
            result.append(
                ControllerSwitchSpec(
                    "dreamsense_sync",
                    "synchronization",
                    _sync,
                    SYNC,
                    assumed_state=True,
                    # A setting, as on the other beds with Sync on and Sync off.
                    entity_registry_enabled_default=False,
                )
            )
        if self.profile.split:
            result.append(
                ControllerSwitchSpec(
                    "dreamsense_split",
                    "dreamsense_split",
                    _split,
                    SPLIT,
                    assumed_state=True,
                    available_fn=lambda c: (
                        isinstance(c, DreamSenseController) and c.command_side is None
                    ),
                )
            )
        return tuple(result)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if not self.profile.side:
            return ()
        return (
            ControllerSelectSpec(
                "dreamsense_selected_side",
                "dreamsense_selected_side",
                SELECTED_SIDE,
                (SIDE_LEFT,) if self._selection.single is True else (SIDE_LEFT, SIDE_RIGHT),
                _side_select,
                local_select_fn=self.select_side,
            ),
        )

    def select_side(self, value: str) -> None:
        if value not in (SIDE_LEFT, SIDE_RIGHT) or not self.profile.side:
            raise invalid("dreamsense_side")
        if self._selection.single is True and value == SIDE_RIGHT:
            raise invalid("dreamsense_side")
        self._selection.side = value
        self.forward_controller_state_updates(SELECTED_SIDE(value))

    @property
    def supports_massage_timer(self) -> bool:
        return any("MinuteTimer" in a.action for a in self.profile.controls)

    @property
    def massage_timer_options(self) -> list[int]:
        return [
            n
            for n in (10, 20, 30)
            if any(a.action == f"Massage{n}MinuteTimer" for a in self.profile.controls)
        ]

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return False

    async def set_massage_timer(self, minutes: int) -> None:
        if minutes not in self.massage_timer_options:
            raise invalid("dreamsense_action")
        await self.press(f"Massage{minutes}MinuteTimer", updates=(MASSAGE_TIMER_MINUTES(minutes),))

    @property
    def _has_light(self) -> bool:
        return self.profile.light and "light" in self._known | self._receive.capabilities

    @property
    def supports_light_timer(self) -> bool:
        return self._blue_light and self._has_light

    @property
    def light_timer_options(self) -> list[str]:
        if not self.supports_light_timer:
            return []
        return [timer.option for timer in BLUE_LIGHT_TIMERS]

    async def set_light_timer(self, timer_option: str) -> None:
        timer = next((t for t in BLUE_LIGHT_TIMERS if t.option == timer_option), None)
        if timer is None or not self._blue_light:
            raise invalid("dreamsense_action")
        await self.light_settings(seconds=timer.seconds)

    def _light_wire(self, seconds: int) -> tuple[int, str | None]:
        """What a duration sends, and Blue's slider stop it is, if any."""
        if type(seconds) is int:
            if self._blue_light:
                for timer in BLUE_LIGHT_TIMERS:
                    if timer.seconds == seconds:
                        return timer.wire, timer.option
            # Seconds as given: the slider's range, and on Blue the action's older one.
            if 0 <= seconds <= self._light_seconds_max:
                return seconds, None
        raise invalid("dreamsense_action")

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if self._blue_light or not self._has_light:
            return ()
        return (
            ControllerNumberSpec(
                "dreamsense_light_seconds",
                "dreamsense_light_seconds",
                LIGHT_SECONDS,
                0,
                self._light_seconds_max,
                1,
                _light_time,
                "s",
                card=CARD_LIGHTING,
            ),
        )

    def validate_light(
        self, color: tuple[int, int, int] | None = None, seconds: int | None = None
    ) -> None:
        self._physical()
        if not self.profile.light or color is None and seconds is None:
            raise invalid("dreamsense_action")
        if color is not None and (
            len(color) != 3 or any(type(n) is not int or not 0 <= n <= 255 for n in color)
        ):
            raise invalid("dreamsense_action")
        if seconds is not None:
            self._light_wire(seconds)

    async def light_settings(
        self, *, color: tuple[int, int, int] | None = None, seconds: int | None = None
    ) -> None:
        self.validate_light(color, seconds)
        if not self._gate("light"):
            raise invalid("dreamsense_capability")
        with self._transaction():
            if seconds is not None:
                wire, option = self._light_wire(seconds)
                # On Blue a duration between the slider's stops is none of its options.
                state = LIGHT_TIMER_OPTION(option) if self._blue_light else LIGHT_SECONDS(seconds)
                with self.sent_state(state):
                    await self._send(p.light_seconds(wire), self._coordinator.cancel_command)
            if color is not None:
                with self.sent_state(UNDER_BED_LIGHTS_RGB(color)):
                    await self._send(codec.rgb(*color), self._coordinator.cancel_command)

    async def close_light(self) -> None:
        self._physical()
        if not self._gate("light"):
            raise invalid("dreamsense_capability")
        with self._transaction() as session:
            await self._send(
                self.profile.frame(0x75, single=session.single), self._coordinator.cancel_command
            )

    async def vibration(self) -> None:
        self._physical()
        if not self._gate("music"):
            raise invalid("dreamsense_capability")
        with self._transaction() as session:
            await self._send(
                self.profile.frame(0xD6, single=session.single), self._coordinator.cancel_command
            )

    @property
    def supports_clock_sync(self) -> bool:
        return self.profile.clock

    async def _clock(self, *, own: bool = True) -> None:
        frames = codec.time_sync(dt_util.now(), build=codec.record_20_len)
        for i, frame in enumerate(frames):
            await self._send(frame, self._coordinator.cancel_command if own else None, own=own)
            if i + 1 < len(frames):
                try:
                    await self._wait(TICK_MS, self._coordinator.cancel_command if own else None)
                except asyncio.CancelledError:
                    if own:
                        note_frame_skipped()
                    raise

    async def sync_clock(self) -> None:
        self._physical()
        if not self.supports_clock_sync:
            raise invalid("dreamsense_action")
        with self._transaction():
            await self._clock()

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        if not self.profile.clock or not self.profile.alarm or self.command_side is not None:
            return None
        return AlarmCapability(
            wake_actions=tuple(ALARM_NAMES[k] for k in self.profile.alarm),
            weekdays=self.profile.repeat,
            live_check=True,
            live_slots=self.profile.repeat,
            requires_wake_action=True,
            requires_slot=self.profile.repeat,
            confirm_actions=frozenset(
                ALARM_NAMES[k] for k in self.profile.alarm if k.startswith("Memory")
            ),
        )

    def _alarm_code(self, alarm: AlarmRequest) -> int:
        result = next(
            (
                code
                for key, code in self.profile.alarm.items()
                if ALARM_NAMES[key] == alarm.wake_action
            ),
            None,
        )
        if alarm.enabled and result is None:
            raise invalid("dreamsense_action")
        return result or 0

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        self._physical()
        if self.alarm_capability is None or alarm.weekdays and not self.profile.repeat:
            raise invalid("dreamsense_action")
        self._alarm_code(alarm)
        if (
            not 0 <= alarm.hour <= 23
            or not 0 <= alarm.minute <= 59
            or any(type(day) is not int or not 0 <= day <= 6 for day in alarm.weekdays)
        ):
            raise invalid("dreamsense_action")

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        if not self._gate("clock"):
            raise invalid("dreamsense_capability")
        if self.profile.repeat:
            await self.query_alarms(own=False, number=alarm.slot)
            if alarm.slot not in self._receive.alarms:
                raise invalid("dreamsense_alarm_record")

    async def query_alarms(self, *, own: bool = True, number: int | None = None) -> None:
        self._physical()
        if not self.profile.repeat or not self._gate("clock"):
            raise invalid("dreamsense_capability")
        with self._transaction():
            self._alarm_event.clear()
            self._receive.alarms.clear()
            self._receive.alarm_record_revisions.clear()
            self._receive.alarm_revision += 1
            revision = self._receive.alarm_revision
            await self._send(p.alarm_list(), self._coordinator.cancel_command, own=own)
            try:
                async with asyncio.timeout(5):
                    while (
                        self._receive.alarm_revision == revision
                        or number is not None
                        and number not in self._receive.alarms
                    ):
                        await cancellable(
                            self._alarm_event.wait(), self._coordinator.cancel_command
                        )
                        self._alarm_event.clear()
                        self._live()
            except TimeoutError as err:
                raise invalid("dreamsense_alarm_list") from err
            self._live()
            if self._receive.alarm_revision == revision:
                raise invalid("dreamsense_alarm_list")

    def alarm_record_identity(self, alarm: AlarmRequest) -> tuple[int, int] | None:
        return (
            (alarm.slot, self._receive.alarm_record_revisions[alarm.slot])
            if alarm.slot in self._receive.alarms
            else None
        )

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        if not self._gate("clock"):
            raise invalid("dreamsense_capability")
        with self._transaction() as session:
            identity = None
            if self.profile.repeat:
                identity = self.alarm_record_identity(alarm)
                if (
                    identity is None
                    or alarm.record_identity is not None
                    and identity != alarm.record_identity
                ):
                    raise invalid("dreamsense_alarm_record")
                previous = self._receive.alarms[alarm.slot]
                mask = 1 | sum(1 << (7 - day) for day in set(alarm.weekdays))
                frames = (
                    (
                        p.alarm_add(
                            alarm.slot, mask, self._alarm_code(alarm), alarm.hour, alarm.minute
                        ),
                    )
                    if alarm.enabled
                    else (
                        p.alarm_add(
                            previous.number,
                            previous.repeat & 0xFE,
                            previous.mode,
                            previous.hour,
                            previous.minute,
                            previous.second,
                        ),
                    )
                )
            else:
                frames = codec.countdown(
                    alarm.minutes_until(dt_util.now()) if alarm.enabled else 0,
                    self._alarm_code(alarm) if alarm.enabled else 0,
                )
            with delivered(partial(self._retire_alarms, session)):
                for i, frame in enumerate(frames):
                    guard = (
                        partial(self.validate_record, alarm.slot, identity)
                        if self.profile.repeat
                        else None
                    )
                    await self._send(frame, self._coordinator.cancel_command, validate=guard)
                    if i + 1 < len(frames):
                        try:
                            await self._wait(TICK_MS, self._coordinator.cancel_command)
                        except asyncio.CancelledError:
                            note_frame_skipped()
                            raise

    def _retire_alarms(self, session: Session, delivery: Delivery) -> None:
        if self._current(session) and self.profile.repeat and delivery is not Delivery.NONE:
            # A modifying command is not a readback, including on interruption.
            self._receive.alarms.clear()
            self._receive.alarm_record_revisions.clear()
            self._receive.alarm_revision += 1
            self.forward_controller_state_updates(ALARMS({}))

    def validate_record(
        self, number: int, identity: tuple[int, int] | None = None
    ) -> tuple[int, int]:
        self._physical()
        self._live()
        if not self.profile.repeat or not self._gate("clock") or number not in self._receive.alarms:
            raise invalid("dreamsense_alarm_record")
        current = (number, self._receive.alarm_record_revisions[number])
        if identity is not None and identity != current:
            raise invalid("dreamsense_alarm_record")
        return current

    async def delete_alarm(self, number: int, identity: tuple[int, int]) -> None:
        self.validate_record(number, identity)
        with self._transaction() as session, delivered(partial(self._retire_alarms, session)):
            await self._send(
                p.alarm_delete(number),
                self._coordinator.cancel_command,
                validate=partial(self.validate_record, number, identity),
            )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "dreamsense_alarm_ack",
                "dreamsense_alarm_ack",
                ACK,
                "mdi:alarm",
                attribute_keys=(ALARMS,),
            ),
        )

    async def move_head_up(self) -> None:
        await self.press("HeadUp")

    async def move_head_down(self) -> None:
        await self.press("HeadDown")

    move_back_up = move_head_up
    move_back_down = move_head_down
    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all

    async def move_feet_up(self) -> None:
        await self.press("FootUp")

    async def move_feet_down(self) -> None:
        await self.press("FootDown")

    move_legs_up = move_feet_up
    move_legs_down = move_feet_down

    async def preset_flat(self) -> None:
        await self.press("MotorReset")

    async def preset_memory(self, memory_num: int) -> None:
        await self.press(f"MemoryPosition{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        await self.press(f"MemoryPosition{memory_num}", save=True)


async def _close_light(controller: BedController) -> None:
    await require_controller(controller, DreamSenseController).close_light()


async def _vibration(controller: BedController) -> None:
    await require_controller(controller, DreamSenseController).vibration()


async def _sync(controller: BedController, enabled: bool) -> None:
    ctrl = require_controller(controller, DreamSenseController)
    await ctrl.press("SyncOn" if enabled else "SyncOff", updates=(SYNC(enabled),))


async def _split(controller: BedController, enabled: bool) -> None:
    ctrl = require_controller(controller, DreamSenseController)
    ctrl._physical()
    if not ctrl.profile.split:
        raise invalid("dreamsense_action")
    with ctrl._transaction(), ctrl.sent_state(SPLIT(enabled)):
        await ctrl._send(p.split_mode(0 if enabled else 2), ctrl._coordinator.cancel_command)


async def _side_select(controller: BedController, value: str) -> None:
    require_controller(controller, DreamSenseController).select_side(value)


async def _light_time(controller: BedController, value: float) -> None:
    if not float(value).is_integer():
        raise invalid("dreamsense_action")
    await require_controller(controller, DreamSenseController).light_settings(seconds=int(value))


async def _refresh_alarms(controller: BedController) -> None:
    await require_controller(controller, DreamSenseController).query_alarms()
