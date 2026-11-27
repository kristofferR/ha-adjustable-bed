"""M3 Ambient controls on one subscribed BLE connection."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from functools import partial
from typing import TYPE_CHECKING, Final, cast

from bleak.exc import BleakError

from ...card import CARD_MASSAGE, CARD_PRESETS, CARD_UTILITY, CardPlacement
from ...codec import ambient as p1
from ...codec import ambient_climate as p2
from ...codec.ambient import Coordinates, MassageZone, Side
from ...command_scheduler import current_command_context, note_frame_skipped
from ...errors import BedNotConnectedError, failed, invalid
from ...profiles import ambient as app
from ...state_keys import UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB, StateKey
from ..base import BedController, require_controller
from ..builder import BuildContext
from ..cancellation import cancellable, settled
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from .transport import resolve_gatt

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

_POWER_SUPPLY: Final = StateKey[str | None]("ambient_power_supply")
_FIRMWARE: Final = StateKey[str | None]("ambient_firmware")
_MASSAGE: Final[dict[MassageZone, StateKey[int | None]]] = {
    "shoulder": StateKey("ambient_shoulder_massage"),
    "feet": StateKey("ambient_feet_massage"),
}
_FANS: Final = {
    Side.LEFT: p2.Query.LEFT_FAN,
    Side.RIGHT: p2.Query.RIGHT_FAN,
}
_FAN_STATE: Final = {
    _FANS[side]: StateKey[int | None](f"ambient_{label}_fan") for label, side in app.SIDES.items()
}
_POSITION: Final = {
    (side, axis): StateKey[int | None](f"ambient_{prefix}{axis}")
    for side, prefix in ((None, ""), (Side.LEFT, "left_"), (Side.RIGHT, "right_"))
    for axis in app.AXIS_LIMITS
}
_ZONE_NAMES: Final = ("shoulder", "torso", "legs")
_HEAT: Final = tuple(
    StateKey[int | None](f"ambient_{side}_{zone}_heat")
    for side in ("right", "left")
    for zone in _ZONE_NAMES
)


@dataclass(slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    ready: bool = False
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    positions: dict[Side | None, p1.Position] = field(default_factory=dict)
    template: bytes | None = None
    heat: p2.Heat | None = None
    next_write: float = 0


def _integer(value: float, maximum: int) -> int:
    if not 0 <= value <= maximum or value != int(value):
        raise invalid("value_out_of_range", min=0, max=maximum, step=1)
    return int(value)


class AmbientController(BedController):
    """Present the split selectors as separate controls on one HA device."""

    def __init__(self, coordinator: AdjustableBedCoordinator, layout: str) -> None:
        super().__init__(coordinator)
        if layout not in app.LAYOUTS:
            raise ValueError("M3 Ambient requires an explicit one-piece or split layout")
        self.split = layout == app.SPLIT
        self._link: _Link | None = None
        self._send_lock = asyncio.Lock()

    @property
    def control_characteristic_uuid(self) -> str:
        return app.WRITE

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        # The layout already defines both selectors on this device.
        return False

    @property
    def supports_stop_all(self) -> bool:
        return False

    @property
    def supports_preset_flat(self) -> bool:
        # Dedicated buttons distinguish Position-tab Flat and one-piece Home Flat.
        return False

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return ()

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def supports_light_state_feedback(self) -> bool:
        return True

    @property
    def supports_light_color_control(self) -> bool:
        return True

    @property
    def supported_color_mode(self) -> str:
        return "rgb"

    @property
    def publishes_rgb_light_state(self) -> bool:
        return True

    @property
    def preserves_unknown_rgb_power(self) -> bool:
        return True

    @property
    def reads_light_state_on_connect(self) -> bool:
        return True

    def _current(self, link: _Link) -> bool:
        return self._link is link and self.client is link.client and link.client.is_connected

    def _live(self) -> _Link:
        link = self._link
        if link is None or not self._current(link) or not link.ready:
            raise BedNotConnectedError
        return link

    def _require_link(self, link: _Link) -> None:
        if self._live() is not link:
            raise BedNotConnectedError

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError
        if self._link is not None and self._current(self._link) and self._link.ready:
            return
        write, notify = resolve_gatt(client.services)
        self.on_disconnect()
        link = self._link = _Link(client, write, notify)

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if self._current(link) and sender.handle == notify.handle:
                self._receive(link, bytes(data))

        try:
            await client.start_notify(notify, receive)
            if not self._current(link):
                raise BedNotConnectedError
            link.ready = True
        except BaseException:
            if self._link is link:
                await settled(self.stop_notify())
            raise

    def on_disconnect(self) -> None:
        link, self._link = self._link, None
        if link is not None:
            link.changed.set()

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link is not None and self.client is link.client and link.client.is_connected:
            try:
                await link.client.stop_notify(link.notify)
            except BleakError:
                # The coordinator closes the connection even if unsubscribe fails.
                pass

    async def async_after_connect(self, session: ControllerSession) -> None:
        if session.is_current():
            await self.refresh_state(startup=True)

    async def _write(
        self,
        link: _Link,
        frame: bytes | Callable[[], bytes],
        *,
        query: bool = False,
        startup: bool = False,
        deadline: float | None = None,
    ) -> None:
        # Leave the cancellation gate and characteristic identity checks at the
        # actual send boundary, including when pacing delayed an admitted action.
        event = asyncio.Event() if startup else self._coordinator.cancel_command
        clock = asyncio.get_running_loop()

        def validate() -> None:
            self._require_link(link)
            if deadline is not None and clock.time() >= deadline:
                raise TimeoutError

        def admit() -> None:
            context = current_command_context()
            caller_cancelling = context.caller_is_cancelling if context is not None else None
            if caller_cancelling is not None and caller_cancelling():
                note_frame_skipped()
                raise asyncio.CancelledError
            validate()

        async with self._send_lock:
            validate()
            delay = link.next_write - clock.time()
            if delay > 0:
                await cancellable(asyncio.sleep(delay), event)
            if event.is_set():
                raise asyncio.CancelledError
            try:
                await self._write_gatt_with_retry(
                    link.write.uuid,
                    frame if isinstance(frame, bytes) else b"",
                    cancel_event=event,
                    characteristic=link.write,
                    expected_client=link.client,
                    before_write=admit,
                    command_factory=frame if callable(frame) else None,
                    track_command_write=not query,
                    settle_write=True,
                )
            except ConnectionError as err:
                if not self._current(link):
                    raise BedNotConnectedError from err
                raise
            finally:
                link.next_write = clock.time() + app.WRITE_PACING
            self._require_link(link)
            if event.is_set():
                raise asyncio.CancelledError

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        # All exposed controls use the link-bound protocol methods below.
        raise NotImplementedError("Use an M3 Ambient control")

    def _receive(self, link: _Link, data: bytes) -> None:
        self.forward_raw_notification(link.notify.uuid, data)
        state = p1.parse_bed_state(data)
        position = state.position if isinstance(state, p1.BedState) else state
        if position is not None:
            if self.split != (position.side is not None):
                return
            link.positions[position.side] = position
            if position.template is not None:
                link.template = position.template
            updates = [
                _POSITION[position.side, axis](value if 0 <= value <= limit else None)
                for axis, limit in app.AXIS_LIMITS.items()
                for value in (getattr(position.coordinates, axis),)
            ]
            if isinstance(state, p1.BedState):
                updates.extend(
                    (
                        _MASSAGE["shoulder"](state.shoulder),
                        _MASSAGE["feet"](state.feet_massage),
                        UNDER_BED_LIGHTS_ON(any(state.rgb)),
                        UNDER_BED_LIGHTS_RGB(app.picker_color(*state.rgb)),
                    )
                )
            self.forward_controller_state_updates(*updates)
            link.changed.set()
        elif (echo := p1.parse_massage_echo(data)) is not None:
            zone, level = echo
            self.forward_controller_state_update(_MASSAGE[zone], level)
        elif data in (p1.LIGHT_ON, p1.LIGHT_OFF):
            self.forward_controller_state_update(UNDER_BED_LIGHTS_ON, data == p1.LIGHT_ON)
        else:
            climate = p2.parse(data)
            if isinstance(climate, p2.Heat):
                link.heat = climate
                self.forward_controller_state_updates(
                    *(key(value) for key, value in zip(_HEAT, climate.zones, strict=True))
                )
                link.changed.set()
            elif isinstance(climate, p2.Fan):
                self.forward_controller_state_update(_FAN_STATE[climate.code], climate.level)
            elif isinstance(climate, p2.Supply):
                self.forward_controller_state_update(_POWER_SUPPLY, climate.source)
            elif isinstance(climate, p2.Firmware):
                self.forward_controller_state_update(_FIRMWARE, str(climate.version))

    async def refresh_state(self, *, startup: bool = False) -> None:
        link = self._live()
        await self._write(link, p1.BED_STATE_QUERY, query=startup, startup=startup)
        for code in p2.Query:
            await self._write(link, p2.query(code), query=startup, startup=startup)

    async def _sample[T](
        self,
        link: _Link,
        receive: Callable[[], T | None],
        timeout: float,
    ) -> T | None:
        async def wait() -> T:
            while True:
                self._require_link(link)
                if (value := receive()) is not None:
                    return value
                link.changed.clear()
                await link.changed.wait()

        try:
            async with asyncio.timeout(timeout):
                return await cancellable(wait(), self._coordinator.cancel_command)
        except TimeoutError:
            return None

    def validate_position_side(self, side: Side | None) -> None:
        if side not in (None, Side.LEFT, Side.RIGHT) or self.split != (side is not None):
            raise invalid("ambient_position_side")

    def _invalidate_position(self, link: _Link, side: Side | None) -> None:
        link.positions.pop(side, None)
        # Keep the link's target template separate from reported positions.
        self.forward_controller_state_updates(
            *(_POSITION[side, axis](None) for axis in app.AXIS_LIMITS)
        )

    def _position_frame(self, link: _Link, side: Side | None, coordinates: Coordinates) -> bytes:
        for axis, maximum in app.AXIS_LIMITS.items():
            _integer(getattr(coordinates, axis), maximum)
        frame = p1.position(coordinates, side, template=link.template)
        self._invalidate_position(link, side)
        return frame

    async def set_position(self, side: Side | None, coordinates: Coordinates) -> None:
        self.validate_position_side(side)
        link = self._live()
        await self._write(link, partial(self._position_frame, link, side, coordinates))

    async def _set_axis(self, side: Side | None, axis: str, value: float) -> None:
        self.validate_position_side(side)
        target_value = _integer(value, app.AXIS_LIMITS[axis])
        link = self._live()
        previous: p1.Position | None = None
        loop = asyncio.get_running_loop()
        requested_at = 0.0

        def query() -> bytes:
            nonlocal previous, requested_at
            requested_at = loop.time()
            previous = link.positions.get(side)
            return p1.BED_STATE_QUERY

        await self._write(link, query, query=True)
        sample = await self._sample(
            link,
            lambda: current if (current := link.positions.get(side)) is not previous else None,
            app.SAMPLE_TIMEOUT,
        )
        if sample is None:
            raise failed("ambient_position_unknown")

        def target() -> bytes:
            current = link.positions.get(side)
            if (
                current is None
                or current is previous
                or loop.time() - requested_at > app.SAMPLE_TIMEOUT
            ):
                raise failed("ambient_position_unknown")
            coordinates = replace(current.coordinates, **{axis: target_value})
            return self._position_frame(link, side, coordinates)

        await self._write(link, target)

    async def preset_flat(self) -> None:
        if self.split:
            raise invalid("ambient_position_side")
        link = self._live()

        def target() -> bytes:
            self._invalidate_position(link, None)
            return p1.HOME_FLAT

        await self._write(link, target)

    async def _unsupported_movement(self) -> None:
        raise NotImplementedError("M3 Ambient exposes only one-shot position targets")

    move_head_up = move_head_down = move_head_stop = _unsupported_movement
    move_back_up = move_back_down = move_back_stop = _unsupported_movement
    move_legs_up = move_legs_down = move_legs_stop = _unsupported_movement
    move_feet_up = move_feet_down = move_feet_stop = _unsupported_movement

    async def stop_all(self) -> None:
        raise invalid("ambient_stop_unavailable")

    async def preset_memory(self, memory_num: int) -> None:
        raise NotImplementedError("M3 Ambient exposes no hardware memory controls")

    program_memory = preset_memory

    async def lights_on(self) -> None:
        await self._write(self._live(), p1.LIGHT_ON)

    async def lights_off(self) -> None:
        await self._write(self._live(), p1.LIGHT_OFF)

    async def set_light_color(self, rgb_color: p1.RGB) -> None:
        red, green, blue = (app.picker_value(component) for component in rgb_color)
        await self.set_raw_rgb((red, green, blue))

    async def set_raw_rgb(self, rgb_color: p1.RGB) -> None:
        frames = tuple(
            p1.rgb(channel, value)
            for channel, value in zip(("red", "green", "blue"), rgb_color, strict=True)
        )
        link = self._live()
        for frame in frames:
            await self._write(link, frame)
        await self._write(link, p1.BED_STATE_QUERY, query=True)

    async def _set_massage(self, zone: MassageZone, value: float) -> None:
        await self._write(self._live(), p1.massage(zone, _integer(value, 3)))

    async def _set_fan(self, code: p2.Query, value: float) -> None:
        link = self._live()
        await self._write(link, p2.fan(code, _integer(value, 10)))
        await self._write(link, p2.query(code), query=True)

    async def set_heat(
        self, side: Side, zones: dict[int, int], *, timer_hours: int | None = None
    ) -> None:
        if side not in (Side.LEFT, Side.RIGHT) or not zones or not zones.keys() <= {0, 1, 2}:
            raise invalid("ambient_heat_zones")
        for value in zones.values():
            _integer(value, app.HEAT_LEVEL_MAX)
        if timer_hours not in (None, app.HEAT_TIMER_HOURS):
            raise invalid("ambient_heat_timer")
        link = self._live()
        previous: p2.Heat | None = None
        loop = asyncio.get_running_loop()
        requested_at = 0.0
        expected: p2.Zones | None = None

        def query() -> bytes:
            nonlocal previous, requested_at
            requested_at = loop.time()
            previous = link.heat
            return p2.query(p2.Query.HEAT_ZONES)

        await self._write(link, query, query=True)
        sample = await self._sample(
            link, lambda: link.heat if link.heat is not previous else None, app.SAMPLE_TIMEOUT
        )
        if sample is None:
            raise failed("ambient_heat_unknown")

        def target() -> bytes:
            nonlocal expected
            current = link.heat
            if (
                current is None
                or current is previous
                or loop.time() - requested_at > app.SAMPLE_TIMEOUT
            ):
                raise failed("ambient_heat_unknown")
            values = list(current.zones)
            offset = 0 if side == Side.RIGHT else 3
            for index, value in zones.items():
                values[offset + index] = value
            expected = cast(p2.Zones, tuple(values))
            return p2.heat(expected)

        await self._write(link, target)
        accepted = link.heat

        def confirmation() -> p2.Heat | None:
            sample = link.heat
            if sample is not None and sample is not accepted and sample.zones == expected:
                return sample
            return None

        deadline = loop.time() + app.HEAT_TIMEOUT
        try:
            async with asyncio.timeout_at(deadline):
                for _ in range(app.HEAT_PROBES):
                    await self._write(
                        link, p2.query(p2.Query.HEAT_ZONES), query=True, deadline=deadline
                    )
                    if await self._sample(link, confirmation, app.HEAT_PROBE_INTERVAL) is not None:
                        break
                else:
                    # Keep listening after the last probe until the overall deadline.
                    if await self._sample(link, confirmation, deadline - loop.time()) is None:
                        raise TimeoutError
        except TimeoutError as err:
            raise failed("ambient_heat_unconfirmed") from err
        if timer_hours is not None:
            await cancellable(asyncio.sleep(app.HEAT_TIMER_DELAY), self._coordinator.cancel_command)

            def timer() -> bytes:
                if link.heat is None or link.heat.zones != expected:
                    raise failed("ambient_heat_unconfirmed")
                return p2.heat_timer(timer_hours)

            await self._write(link, timer)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        sides = tuple(app.SIDES.values()) if self.split else (None,)
        return (
            *(
                _number(
                    _POSITION[side, axis],
                    maximum,
                    partial(_position_number, side, axis),
                )
                for side in sides
                for axis, maximum in app.AXIS_LIMITS.items()
            ),
            *(
                _number(key, 3, partial(_massage_number, zone), card=CARD_MASSAGE)
                for zone, key in _MASSAGE.items()
            ),
            *(_number(_FAN_STATE[code], 10, partial(_fan_number, code)) for code in _FANS.values()),
            *(
                _number(key, app.HEAT_LEVEL_MAX, partial(_heat_number, side, index))
                for side, keys in ((Side.RIGHT, _HEAT[:3]), (Side.LEFT, _HEAT[3:]))
                for index, key in enumerate(keys)
            ),
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        presets = tuple(
            ControllerButtonSpec(
                f"ambient_{prefix}{preset}",
                preset,
                partial(_position_preset, side, coordinates),
                translation_key=f"ambient_{prefix}{preset}",
                card=CARD_PRESETS,
                invalidates_position=True,
            )
            for side, prefix in (
                ((Side.LEFT, "left_"), (Side.RIGHT, "right_")) if self.split else ((None, ""),)
            )
            for preset, coordinates in app.PRESETS.items()
        )
        refresh = ControllerButtonSpec(
            "ambient_refresh",
            "Refresh bed state",
            _refresh,
            translation_key="ambient_refresh",
            cancel_movement=False,
        )
        if self.split:
            return (*presets, refresh)
        return (
            *presets,
            refresh,
            ControllerButtonSpec(
                "ambient_home_flat",
                "Home flat",
                lambda controller: controller.preset_flat(),
                translation_key="ambient_home_flat",
                card=CARD_PRESETS,
                invalidates_position=True,
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                _POWER_SUPPLY,
                _POWER_SUPPLY,
                _POWER_SUPPLY,
                "mdi:power-plug",
                entity_registry_enabled_default=True,
            ),
            ControllerStateSensorSpec(
                _FIRMWARE,
                _FIRMWARE,
                _FIRMWARE,
                "mdi:chip",
                entity_registry_enabled_default=True,
            ),
        )


def _number(
    key: StateKey[int | None],
    maximum: int,
    setter: Callable[[BedController, float], Awaitable[None]],
    *,
    card: CardPlacement = CARD_UTILITY,
) -> ControllerNumberSpec:
    return ControllerNumberSpec(key, key, key, 0, maximum, 1, setter, card=card)


async def build_controller(ctx: BuildContext) -> AmbientController:
    return AmbientController(ctx.coordinator, ctx.variant or "")


async def _position_number(
    side: Side | None, axis: str, controller: BedController, value: float
) -> None:
    await require_controller(controller, AmbientController)._set_axis(side, axis, value)


async def _position_preset(
    side: Side | None, coordinates: Coordinates, controller: BedController
) -> None:
    await require_controller(controller, AmbientController).set_position(side, coordinates)


async def _massage_number(zone: MassageZone, controller: BedController, value: float) -> None:
    await require_controller(controller, AmbientController)._set_massage(zone, value)


async def _fan_number(code: p2.Query, controller: BedController, value: float) -> None:
    await require_controller(controller, AmbientController)._set_fan(code, value)


async def _heat_number(side: Side, index: int, controller: BedController, value: float) -> None:
    await require_controller(controller, AmbientController).set_heat(
        side, {index: _integer(value, app.HEAT_LEVEL_MAX)}
    )


async def _refresh(controller: BedController) -> None:
    await require_controller(controller, AmbientController).refresh_state()
