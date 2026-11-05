"""MotoMotion app profile, with independent panel, transport and name flags."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from functools import partial
from math import isfinite
from time import monotonic
from typing import TYPE_CHECKING

from ..codec import motomotion as codec
from ..codec.motomotion import Position, ascii_command, binary_command, music_command
from ..const import CONF_BLE_DEVICE_NAME
from ..motomotion_protocol import color_parameters, decimal, light_cycle, posture, rgb_total
from ..motomotion_requests import Request
from ..motomotion_state import Comfort, State
from ..profiles.motomotion import Profile
from .base import (
    CONTROLLER_GESTURE_RELEASE,
    BedController,
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
)

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

MUSIC = {
    "custom": (8, 2, 2, 7),
    "wide": (8, 10, 5, 5),
    "electric": (8, 13, 14, 15),
    "live": (8, 10, 15, 13),
}
BINARY_EXTRA = {"custom": (7, 7), "wide": (5, 7), "electric": (7, 7), "live": (8, 8)}
FINE_LIMITS = {"head": 863, "base": 3174, "back": 1454, "lumbar": 874, "tilt": 629}


def select_transport(
    client: BleakClient,
) -> tuple[BleakGATTCharacteristic, BleakGATTCharacteristic, BleakGATTCharacteristic | None, float]:
    write = notify = binding = None
    delay = 0.0
    for service in client.services:
        uuid = service.uuid.upper()
        if "FFE0" in uuid:
            delay = 0.1
            for char in service.characteristics:
                if "FFE1" in char.uuid.upper():
                    write = notify = char
                if "FFE2" in char.uuid.upper():
                    binding = char
        elif "FFF0" in uuid:
            delay = 0.0
            for char in service.characteristics:
                if "FFF1" in char.uuid.upper():
                    write = char
                if "FFF2" in char.uuid.upper():
                    notify = char
    if write is None or notify is None:
        raise ValueError("MotoMotion needs its FFE0/FFE1 or FFF0/FFF1/FFF2 layout")
    return write, notify, binding, delay


def select_unpair_characteristic(client: BleakClient) -> BleakGATTCharacteristic | None:
    """Unpair has its own FFE0/FFE1 selector, independent of normal roles."""
    for service in client.services:
        if "FFE0" in service.uuid.upper():
            for char in service.characteristics:
                if "FFE1" in char.uuid.upper():
                    return char
    return None


async def action(controller: BedController, key: str) -> None:
    await controller.async_execute_motomotion_action(key)


async def number(controller: BedController, value: float, *, key: str) -> None:
    await controller.async_set_motomotion_number(key, value)


async def select(controller: BedController, value: str, *, key: str) -> None:
    await controller.async_select_motomotion(key, value)


class MotoMotionController(BedController):
    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        device_name: str | None = None,
        manufacturer_data: dict[int, bytes] | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._target_address = coordinator.address
        stored = coordinator.entry.data.get(CONF_BLE_DEVICE_NAME)
        self.profile = Profile(stored if isinstance(stored, str) else device_name or "")
        self._manufacturer = (manufacturer_data or {}).get(1465, b"")
        self._state = State()
        self._local_d = False
        self._prepared_light: int | None = 32788
        self._local_cm: Comfort | None = None
        self._local_hsw: tuple[bool, int] | None = None
        self._panel_heat = 0
        self._panel_lift = False
        self._local_lr: tuple[Comfort | None, Comfort | None] = (None, None)
        self._session: (
            tuple[BleakClient, BleakGATTCharacteristic, BleakGATTCharacteristic] | None
        ) = None
        self._unpair_write: BleakGATTCharacteristic | None = None
        self._generation = 0
        self._rejection: str | None = None
        self._bind_code = ""
        self._side = "left"
        self._music_mode = "custom"
        self._eq = [8, 2, 2, 7]
        self._custom_eq = [8, 2, 2, 7]
        self._rgb = [255, 255, 255]
        self._timer = 15
        self._posture: str | None = "upright"
        self._dimensions: dict[str, float] = {}
        self._users: dict[str, tuple[float, float, float]] = {}
        self._user: str | None = None
        self._targets: Position | None = None
        self._custom: dict[str, Position] = {}
        self._user_positions: dict[str, dict[str, Position]] = {}

    @property
    def control_characteristic_uuid(self) -> str:
        return self._session[1].uuid if self._session else "0000ffe1-0000-1000-8000-00805f9b34fb"

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_motor_control(self) -> bool:
        return False  # Explicit app-labelled controls avoid guessed HA motor mappings.

    @property
    def supports_single_address_pairing(self) -> bool:
        return self.profile.sides

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_preset_zero_g(self) -> bool:
        return False

    @property
    def supports_preset_tv(self) -> bool:
        return False

    @property
    def supports_preset_anti_snore(self) -> bool:
        return False

    @property
    def supports_memory_presets(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def supports_memory_programming(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def memory_slot_count(self) -> int:
        if self.profile.panel in ("A", "Seven", "H", "Music", "Binary music"):
            return 0
        if self.profile.panel == "Six":
            return 0 if self.profile.heat else 1
        return 4 if self.profile.panel == "G" else 1 if self.profile.panel in ("D", "E") else 2

    @property
    def persisted_app_state_key(self) -> str:
        return "motomotion:" + self.profile.name

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {
            "bind_code": self._bind_code,
            "side": self._side,
            "posture": self._posture,
            "working_targets": {
                "user": self._user,
                "posture": self._posture,
                "dimensions": self._dimensions.copy(),
                "positions": asdict(self._targets),
            }
            if self._targets is not None
            else None,
            "music_mode": self._music_mode,
            "eq": self._eq.copy(),
            "timer": self._timer,
            "custom_eq": self._custom_eq.copy(),
            "rgb": self._rgb.copy(),
            "dimensions": self._dimensions.copy(),
            "custom": {key: asdict(value) for key, value in self._custom.items()},
            "users": dict(self._users),
            "user_positions": {
                user: {key: asdict(value) for key, value in positions.items()}
                for user, positions in self._user_positions.items()
            },
            "user": self._user,
        }

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        bind = state.get("bind_code", "")
        if not isinstance(bind, str) or (
            bind and (len(bind) != 16 or any(c not in "0123456789abcdef" for c in bind))
        ):
            raise ValueError("Invalid MotoMotion binding")
        self._bind_code = bind
        side = state.get("side", "left")
        if side not in ("left", "right"):
            raise ValueError("Invalid MotoMotion saved side")
        self._side = side if self.profile.sides else "left"
        selected_posture = state.get("posture", "upright")
        # An invalid optional selector must not reset the address's valid side.
        self._posture = (
            (
                selected_posture
                if isinstance(selected_posture, str)
                and selected_posture in ("upright", "recline", "tv", "lay")
                else None
            )
            if self.profile.users
            else "upright"
        )
        for key, target, limits in (
            (
                "custom_eq",
                self._custom_eq,
                (63, 31, 31, 31) if self.profile.panel == "Binary music" else (22, 15, 15, 15),
            ),
            ("rgb", self._rgb, (255, 255, 255)),
        ):
            values = state.get(key)
            if values is not None:
                if (
                    not isinstance(values, list)
                    or len(values) != len(limits)
                    or any(
                        type(v) is not int or not 0 <= v <= maximum
                        for v, maximum in zip(values, limits, strict=True)
                    )
                ):
                    raise ValueError("Invalid MotoMotion saved controls")
                target[:] = values
        dimensions = state.get("dimensions", {})
        if not isinstance(dimensions, dict) or any(
            k not in ("height", "buttocks", "knee")
            or not isinstance(v, (float, int))
            or not isfinite(v)
            for k, v in dimensions.items()
        ):
            raise ValueError("Invalid MotoMotion measurements")
        self._dimensions = dict(dimensions)
        custom = state.get("custom", {})
        if not isinstance(custom, dict):
            raise ValueError("Invalid MotoMotion postures")
        self._custom = {}
        for key, value in custom.items():
            if (
                key not in ("upright", "recline", "tv", "lay")
                or not isinstance(value, dict)
                or set(value) != set(FINE_LIMITS)
                or any(type(v) is not int or not 0 <= v <= 65535 for v in value.values())
            ):
                raise ValueError("Invalid MotoMotion custom posture")
            self._custom[key] = Position(**value)
        users = state.get("users", {})
        if not isinstance(users, dict) or any(
            not isinstance(k, str)
            or not isinstance(v, (tuple, list))
            or len(v) != 3
            or any(not isinstance(x, (float, int)) or not isfinite(x) for x in v)
            for k, v in users.items()
        ):
            raise ValueError("Invalid MotoMotion users")
        self._users = {k: tuple(v) for k, v in users.items()}
        selected = state.get("user")
        if selected is not None and (not isinstance(selected, str) or selected not in self._users):
            raise ValueError("Invalid MotoMotion selected user")
        self._user = selected
        positions = state.get("user_positions", {})
        if not isinstance(positions, dict):
            raise ValueError("Invalid MotoMotion user positions")
        self._user_positions = {}
        for user, saved in positions.items():
            if user not in self._users or not isinstance(saved, dict):
                raise ValueError("Invalid MotoMotion user positions")
            parsed: dict[str, Position] = {}
            for key, value in saved.items():
                if (
                    key not in ("upright", "recline", "tv", "lay")
                    or not isinstance(value, dict)
                    or set(value) != set(FINE_LIMITS)
                    or any(type(v) is not int or not 0 <= v <= 65535 for v in value.values())
                ):
                    raise ValueError("Invalid MotoMotion saved targets")
                parsed[key] = Position(**value)
            self._user_positions[user] = parsed
        if self._user is not None:
            self._custom = self._user_positions.setdefault(self._user, self._custom)
        self._targets = None
        working = state.get("working_targets")
        if self.profile.users and self._posture is not None and isinstance(working, dict):
            positions = working.get("positions")
            dimensions_owner = working.get("dimensions")
            if (
                set(working) == {"user", "posture", "dimensions", "positions"}
                and working["user"] == self._user
                and working["posture"] == self._posture
                and isinstance(dimensions_owner, dict)
                and dimensions_owner == self._dimensions
                and all(type(v) in (int, float) and isfinite(v) for v in dimensions_owner.values())
                and isinstance(positions, dict)
                and set(positions) == set(FINE_LIMITS)
                # Generated helper targets have a wider domain than slider edits.
                and all(type(v) is int and 0 <= v <= 65535 for v in positions.values())
            ):
                self._targets = Position(**positions)
        if self.profile.music:
            mode = state.get("music_mode", "custom")
            valid_mode = isinstance(mode, str) and mode in MUSIC
            if not isinstance(mode, str) or mode not in MUSIC:
                mode = "custom"
            self._music_mode = mode
            self._eq = (
                self._custom_eq.copy()
                if self._music_mode == "custom"
                else list(MUSIC[self._music_mode])
            )
            levels = state.get("eq")
            limits = (63, 31, 31, 31) if self.profile.panel == "Binary music" else (22, 15, 15, 15)
            if (
                valid_mode
                and isinstance(levels, list)
                and len(levels) == 4
                and all(
                    type(v) is int and 0 <= v <= maximum
                    for v, maximum in zip(levels, limits, strict=True)
                )
            ):
                self._eq = levels.copy()
        timer = state.get("timer", 15)
        self._timer = (
            timer if self.profile.rgb and type(timer) is int and 0 <= timer <= 7259 else 15
        )
        self._publish()

    def _publish(self) -> None:
        comfort = self._comfort()
        values: dict[str, object] = {
            "motomotion_status": self._rejection or "ready",
            "motomotion_panel": self.profile.panel,
            "motomotion_tokens": self._state.token_count,
            "motomotion_panel_heat": self._panel_heat,
            "motomotion_lift_status": self._panel_lift,
            "motomotion_user": self._user,
            "motomotion_users": list(self._users),
            "motomotion_received": {
                "rgb": self._state.rgb,
                "d": self._state.d,
                "cm": asdict(self._state.cm) if self._state.cm else None,
                "hsw": self._state.hsw,
            },
            "motomotion_heat": comfort.heat if comfort else None,
            "motomotion_massage": comfort.massage if comfort else None,
            "motomotion_side": self._side,
            "motomotion_music_mode": self._music_mode,
            "motomotion_posture": self._posture,
            "motomotion_timer": self._timer,
        }
        values.update(
            {
                "motomotion_" + key: value
                for key, value in zip(
                    ("volume", "treble", "bass", "vibration"), self._eq, strict=True
                )
            }
        )
        values.update(
            {
                "motomotion_" + key: value
                for key, value in zip(("red", "green", "blue"), self._rgb, strict=True)
            }
        )
        values.update(
            {
                "motomotion_" + key: self._dimensions.get(key)
                for key in ("height", "buttocks", "knee")
            }
        )
        values.update(
            {"motomotion_target_" + key: getattr(self._targets, key, None) for key in FINE_LIMITS}
        )
        for side, comfort_state in zip(("left", "right"), self._local_lr, strict=True):
            values[f"motomotion_heat_{side}"] = comfort_state.heat if comfort_state else None
            values[f"motomotion_massage_{side}"] = comfort_state.massage if comfort_state else None
        self.forward_controller_state_updates(values)

    def _comfort(self) -> Comfort | None:
        if self.profile.sides:
            return self._local_lr[1 if (self.command_side or self._side) == "right" else 0]
        return self._local_cm

    def _deliver(self, generation: int, event: str) -> None:
        if generation != self._generation or self._session is None:
            return
        # An event carries its name only; it reads the current singleton at delivery.
        if event == "OK":
            self._local_d = self._state.d is not None
            self._local_cm, self._local_hsw = self._state.cm, self._state.hsw
        elif event == "LR":
            self._local_lr = (self._state.left, self._state.right)
        if self._state.token_count == 50 and self._state.hsw is not None:
            self._panel_lift, self._panel_heat = self._state.hsw
        elif self._state.cm is not None:
            self._panel_heat = self._state.cm.heat
            self._panel_lift = self._state.cm.flag
            if self.profile.panel == "H" and self._panel_heat == 3:
                self._panel_heat = 2
        if self.profile.panel in ("D", "E"):
            try:
                self._prepare_light()
            except ValueError as err:
                self._rejection = str(err)
        self._publish()

    def _prepare_light(self) -> None:
        self._prepared_light = None
        self._prepared_light = light_cycle(self._state.d[0] if self._state.d else "", self._local_d)

    def _notification(
        self, generation: int, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        session = self._session
        if (
            self._coordinator.address != self._target_address
            or generation != self._generation
            or session is None
            or self.client is not session[0]
            or not session[0].is_connected
        ):
            return
        self.forward_raw_notification(sender.uuid, bytes(data))

        def enqueue(event: str) -> None:
            asyncio.get_running_loop().call_soon(self._deliver, generation, event)

        try:
            self._state.feed(bytes(data), self.profile.name, enqueue)
            self._rejection = None
        except (ValueError, IndexError) as err:
            self._rejection = str(err)
        self._publish()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if (
            client is None
            or not client.is_connected
            or self._coordinator.address != self._target_address
        ):
            raise ConnectionError("MotoMotion is disconnected or its target changed")
        self._generation += 1
        self._session = None
        self._unpair_write = None
        manufacturer = self._manufacturer
        if manufacturer and manufacturer[0] != 1 and manufacturer[1:].hex() != self._bind_code:
            self._rejection = (
                "MotoMotion binding ownership does not match this address's saved code"
            )
            self._publish()
            raise ValueError(self._rejection)
        write, notify, binding, delay = select_transport(client)
        self._unpair_write = select_unpair_characteristic(client)
        self._generation += 1
        self._session = (client, write, notify)
        self._state = State()
        self._local_d = False
        self._local_cm = None
        self._local_hsw = None
        self._local_lr = (None, None)
        try:
            # Manufacturer status 01 is the app's binding request, not an OS bond.
            manufacturer = self._manufacturer
            if binding is not None and manufacturer[:1] == b"\x01":
                code = codec.binding_code(secrets.randbelow(255) for _ in range(8))
                self._bind_code = code.hex()
                self._coordinator.save_app_state(
                    self
                )  # Request precedes BLE, durability unconfirmed.
                await client.write_gatt_char(binding, code, response=True)
            if delay:
                await asyncio.sleep(delay)
            await client.start_notify(notify, partial(self._notification, self._generation))
            if self.profile.panel == "Binary music":
                await self.write_command(binary_command(10))
                await self.write_command(binary_command(8))
        except BaseException:
            self._session = None
            self._unpair_write = None
            self._generation += 1
            raise
        self._rejection = None
        self._publish()

    async def stop_notify(self) -> None:
        session, self._session = self._session, None
        self._unpair_write = None
        self._generation += 1
        self._state.buffer.clear()
        if session is not None and session[0].is_connected:
            await session[0].stop_notify(session[2])

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        session = self._session
        if session is None:
            raise ConnectionError("MotoMotion notification session is unavailable")
        cancel = cancel_event or self._coordinator.cancel_command
        for i in range(repeat_count):
            if cancel.is_set():
                return
            if i and not await self._wait(repeat_delay_ms / 1000, cancel):
                return
            async with self._ble_lock:
                if (
                    self._coordinator.address != self._target_address
                    or self._session is not session
                    or self.client is not session[0]
                    or not session[0].is_connected
                ):
                    raise ConnectionError("MotoMotion BLE session changed")
                if cancel.is_set():
                    return
                self._coordinator.record_command_trace(
                    payload={"hex": command.hex()},
                    characteristic_uuid=session[1].uuid,
                    characteristic_handle=session[1].handle,
                    response=True,
                    repeat_count=1,
                    repeat_delay_ms=repeat_delay_ms,
                    command_origin="motomotion",
                    controller_class=type(self).__name__,
                )
                await session[0].write_gatt_char(session[1], command, response=True)

    async def _wait(self, seconds: float, cancel: asyncio.Event) -> bool:
        try:
            await asyncio.wait_for(cancel.wait(), seconds)
            return False
        except TimeoutError:
            return True

    def _parameter(self) -> int:
        side = self.command_side or self._side
        if side == "both":
            raise ValueError("MotoMotion commands require one side")
        if side == "right":
            if not self.profile.sides:
                raise ValueError("This MotoMotion name has no side selector")
            return 10000
        return 0

    async def _ascii(
        self, command: int, parameter: int | None = None, *, cleanup: bool = False
    ) -> None:
        await self.write_command(
            ascii_command(command, self._parameter() if parameter is None else parameter),
            cancel_event=asyncio.Event() if cleanup else None,
        )

    def movement_commands(self) -> dict[str, tuple[int, int, bool]]:
        p = self.profile
        if "music" in p.panel.lower():
            return {}
        head = (32, 16) if p.char(9) == "2" else (2, 1)
        result = {"headrest": (*head, p.binary and p.char(9) != "2"), "main": (128, 85, False)}
        if p.panel not in ("Three", "Seven"):
            result["lumbar"] = (128, 64, True) if p.binary else (8, 4, False)
        if p.panel == "G":
            result["main"] = (32773, 32774, False)
        if p.panel in ("A", "H", "J", "Five", "Six"):
            result["back"] = (32, 16, p.binary and p.panel == "Six")
            result["legrest"] = (8, 4, True) if p.binary and p.panel == "Six" else (64, 128, False)
            result["main"] = (165, 80 if p.panel in ("J", "Five") else 64, False)
        if p.panel == "Five":
            result["back"] = (16, 32, False)  # Slider's direction differs from the button bars.
            if p.char(14) in ("M", "X"):
                result["main"] = (32776, 32775, False)
        if p.panel == "Six":
            result["main"] = (1445, 80, p.binary)
            result["tilt"] = (512, 256, True) if p.binary else (337, 338, False)
        if p.panel in ("A", "H", "J", "Five"):
            result["headrest"] = (2, 1, False)
            result["lumbar"] = (8, 4, False)
        return result

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (
            tuple(
                f"motomotion_{axis}_{direction}"
                for axis in self.movement_commands()
                for direction in ("up", "down")
            )
            + tuple(f"motomotion_memory_{slot}" for slot in range(1, self.memory_slot_count + 1))
            + (("motomotion_home",) if self.profile.panel in ("One", "Three", "D", "E") else ())
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 60000
        ):
            raise ValueError("Choose an available MotoMotion control and a 1..60000 ms hold")
        self._parameter()

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        if control.startswith("motomotion_memory_"):
            await self.recall_memory(int(control.rsplit("_", 1)[1]), hold_ms=duration_ms)
            return
        if control == "motomotion_home":
            # The shared Home widget refreshes but has no release/STOP callback.
            await self._refresh_held(ascii_command(262, self._parameter()), duration_ms)
            return
        axis, direction = control.removeprefix("motomotion_").rsplit("_", 1)
        up, down, binary = self.movement_commands()[axis]
        command = up if direction == "up" else down
        frame = binary_command(command) if binary else ascii_command(command, self._parameter())
        try:
            await self._refresh_held(frame, duration_ms)
        finally:
            await self.stop_all()

    async def _refresh_held(self, frame: bytes, duration_ms: int) -> None:
        cancel = self._coordinator.cancel_command
        start = monotonic()
        deadline = start + duration_ms / 1000
        for tick in range(1, duration_ms // 100 + 1):
            if cancel.is_set() or not await self._wait(
                max(0, start + tick * 0.1 - monotonic()), cancel
            ):
                return
            if monotonic() > deadline:
                return
            await self.write_command(frame)
        if not cancel.is_set() and monotonic() < deadline:
            await self._wait(deadline - monotonic(), cancel)

    async def stop_all(self) -> None:
        if CONTROLLER_GESTURE_RELEASE.get():
            return  # The cancelled hold owns its protocol-specific release cleanup.
        # Source schedules three independent timers at the SAME 50ms deadline.
        await asyncio.sleep(0.05)
        frame = (
            binary_command(0)
            if "MOTOA" in self.profile.name
            else ascii_command(0, self._parameter())
        )
        for _ in range(3):
            await self.write_command(frame, cancel_event=asyncio.Event())

    async def _move(self, axis: str, direction: str) -> None:
        await self.hold_control(f"motomotion_{axis}_{direction}", 1000)

    async def move_head_up(self) -> None:
        await self._move("headrest", "up")

    async def move_head_down(self) -> None:
        await self._move("headrest", "down")

    async def move_back_up(self) -> None:
        await self._move("back", "up")

    async def move_back_down(self) -> None:
        await self._move("back", "down")

    async def move_legs_up(self) -> None:
        await self._move("legrest", "up")

    async def move_legs_down(self) -> None:
        await self._move("legrest", "down")

    async def move_feet_up(self) -> None:
        raise NotImplementedError("MotoMotion has no feet mapping")

    async def move_feet_down(self) -> None:
        raise NotImplementedError("MotoMotion has no feet mapping")

    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = stop_all

    async def preset_flat(self) -> None:
        raise NotImplementedError("MotoMotion does not identify a generic flat preset")

    async def preset_memory(self, memory_num: int) -> None:
        if not 1 <= memory_num <= self.memory_slot_count:
            raise ValueError("Unavailable MotoMotion memory")
        await self.recall_memory(memory_num, hold_ms=1000)

    async def recall_memory(self, slot: int, *, hold_ms: int) -> None:
        if (
            not 1 <= slot <= self.memory_slot_count
            or type(hold_ms) is not int
            or not 1 <= hold_ms <= 60000
        ):
            raise ValueError("Choose an available MotoMotion memory and a bounded hold")
        command = (256, 257, 32779, 32780)[slot - 1]
        if self.profile.panel == "D":
            command = 257
        frame = (
            binary_command(32777)
            if self.profile.panel == "Six" and self.profile.binary
            else ascii_command(command, self._parameter())
        )
        try:
            await self._refresh_held(frame, hold_ms)
        finally:
            if self.profile.sofa and self.profile.char(12) == "E":
                await self.stop_all()

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        for slot in range(1, self.memory_slot_count + 1):
            if key == f"preset_memory_{slot}":
                return ControllerHoldSpec(
                    f"motomotion_memory_{slot}",
                    release_button_key="motomotion_release",
                )
        return None

    async def program_memory(self, memory_num: int) -> None:
        if not 1 <= memory_num <= self.memory_slot_count:
            raise ValueError("Unavailable MotoMotion memory")
        if self.profile.panel == "Six" and self._local_cm is not None and self._local_cm.flag:
            raise ValueError("MotoMotion blocks programming while its lift status is active")
        if self.profile.panel == "D":
            await self._ascii(264)
        elif self.profile.panel == "Six" and self.profile.binary:
            await self.write_command(binary_command(33050))
        elif self.profile.panel == "E":
            await self._ascii(33050, 0)
            if await self._wait(0.3, self._coordinator.cancel_command):
                await self._ascii(263)
        else:
            await self._ascii((263, 264, 33052, 33053)[memory_num - 1])

    async def _color(self) -> None:
        for i in range(3):
            if i and not await self._wait(0.1, self._coordinator.cancel_command):
                return
            value = color_parameters((self._rgb[0], self._rgb[1], self._rgb[2]))[i]
            await self._ascii(315 + i, value + self._parameter())

    async def _lumbar(self) -> None:
        value = decimal(self._state.d[1]) if self._local_d and self._state.d else None
        if self.profile.panel == "E":
            command = 353 if value else 352
            for i in range(3):
                if i and not await self._wait(0.1, self._coordinator.cancel_command):
                    return
                await self._ascii(command, 0)
        elif value is None:
            for i in range(3):
                if i and not await self._wait(0.1, self._coordinator.cancel_command):
                    return
                await self._ascii(33055, 0)
        elif value == 0:
            await self._ascii(33055, 0)
        else:
            await self._ascii(33050, 0)
            if await self._wait(0.3, self._coordinator.cancel_command):
                await self._ascii(16, 0)

    async def async_execute_motomotion_action(self, key: str) -> None:
        await self.action(key)

    async def async_set_motomotion_number(self, key: str, value: float) -> None:
        await self.set_number(key, value)

    async def async_select_motomotion(self, key: str, value: str) -> None:
        await self.select(key, value)

    async def action(self, key: str) -> None:
        if key in self.held_control_options:
            await self.hold_control(key, 1000)
            return
        allowed = {spec.key for spec in self.controller_button_specs}
        if key not in allowed:
            raise ValueError("Action unavailable for this MotoMotion panel")
        key = key.removeprefix("motomotion_")
        if key == "program_release":
            await self._ascii(0)
        elif key == "lumbar_toggle":
            await self._lumbar()
        elif key == "light_cycle":
            self._prepare_light()
            if await self._wait(0.2, self._coordinator.cancel_command):
                # A delivered event can rebuild the prepared command during the one-shot.
                if self._prepared_light is None:
                    raise ValueError("The current MotoMotion light state cannot build a command")
                await self._ascii(self._prepared_light, 0)
        elif key == "memory_lumbar_combo":
            if self.profile.panel != "D":
                raise ValueError("The simultaneous memory/lumbar gesture belongs to panel D")
            if await self._wait(3, self._coordinator.cancel_command):
                await self._ascii(33050, 0)
        elif key == "light_off":
            await self._ascii(32787, 0)
        elif key == "light_toggle":
            if self.profile.light_kind == 1:
                await self._ascii(262)
            else:
                total = rgb_total(self._state.rgb)
                if self.profile.char(13) == "F":
                    await self._ascii(300)
                else:
                    self._rgb[:] = [255 if total == 0 else 0] * 3
                    await self._color()
        elif key == "heat_cycle":
            heat = self._panel_heat
            panel = self.profile.panel
            command = (
                (332, 333, 334)[heat % 3]
                if panel == "Five"
                else (332, 334, 335)[heat % 3]
                if panel == "H"
                else (335, 332, 333, 334)[(heat + (2 if heat == 1 else 1)) & 3]
            )
            if await self._wait(0.2, self._coordinator.cancel_command):
                await self._ascii(command)
        elif key.startswith(("heat_", "massage_")):
            comfort = self._comfort() or Comfort()
            heat = key.startswith("heat_")
            level = comfort.heat if heat else comfort.massage
            level = 0 if level == 4 else level
            level = max(level - 1, 0) if key.endswith("down") else min(level + 1, 3)
            if not 0 <= level <= 3:
                raise ValueError("Received level is outside the app command table")
            if await self._wait(0.2, self._coordinator.cancel_command):
                await self._ascii(((335, 332, 333, 334) if heat else (353, 350, 351, 352))[level])
        elif key == "rgb_apply":
            await self._color()
        elif key == "timer_apply":
            await self.write_command(codec.TIMER_PREFIX)
            if await self._wait(0.05, self._coordinator.cancel_command):
                await self._ascii(32999, self._timer)
        elif key.startswith("music_"):
            await self.write_command(
                binary_command({"music_play": 14, "music_next": 12, "music_previous": 13}[key])
            )
        elif key.startswith("posture_"):
            if self._posture is None:
                raise ValueError("Select a MotoMotion posture before using posture controls")
            if key == "posture_save":
                if self._targets is None:
                    raise ValueError("Recall or fine tune a posture first")
                self._custom[self._posture] = self._targets
                self._coordinator.save_app_state(self)
            else:
                if key == "posture_reset":
                    self._custom.pop(self._posture, None)
                    self._coordinator.save_app_state(self)
                self._targets = self._position()
                await self.write_command(self._targets.to_bytes())
        elif key == "unbind":
            session = self._session
            unpair = self._unpair_write
            if session is None or unpair is None:
                raise ValueError("Application unbinding requires the FFE0/FFE1 layout")
            async with self._ble_lock:
                if (
                    self._coordinator.address != self._target_address
                    or self._session is not session
                    or self.client is not session[0]
                    or not session[0].is_connected
                ):
                    raise ConnectionError("MotoMotion unbind session changed")
                self._coordinator.record_command_trace(
                    payload={"hex": codec.UNPAIR.hex()},
                    characteristic_uuid=unpair.uuid,
                    characteristic_handle=unpair.handle,
                    response=False,
                    repeat_count=1,
                    repeat_delay_ms=0,
                    command_origin="motomotion_unbind",
                    controller_class=type(self).__name__,
                )
                await session[0].write_gatt_char(unpair, codec.UNPAIR, response=False)
            try:
                await asyncio.sleep(1)
            finally:
                await self._coordinator.async_disconnect()
        self._publish()

    def _select_posture(self, value: str) -> None:
        if value != self._posture:
            self._targets = None
            self._posture = value

    def _position(self) -> Position:
        if self._posture is None:
            raise ValueError("Select a MotoMotion posture before using posture controls")
        if self._posture in self._custom:
            return self._custom[self._posture]
        if set(self._dimensions) != {"height", "buttocks", "knee"}:
            raise ValueError(
                "Set height, buttocks height and knee height before recalling a posture"
            )
        return posture(
            self._posture,
            self._dimensions["height"],
            self._dimensions["buttocks"],
            self._dimensions["knee"],
        )

    def _action_label(self, key: str) -> str:
        label = key.removeprefix("motomotion_")
        if self.profile.char(9) == "2" and label.startswith("headrest_"):
            label = "back_" + label.removeprefix("headrest_")
        return label.replace("_", " ").capitalize()

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        keys: list[str] = [
            key for key in self.held_control_options if not key.startswith("motomotion_memory_")
        ]
        if self.memory_slot_count:
            keys.append("motomotion_program_release")
        if self.profile.panel in ("D", "E"):
            keys.extend("motomotion_" + s for s in ("lumbar_toggle", "light_cycle", "light_off"))
        if self.profile.panel == "D":
            keys.append("motomotion_memory_lumbar_combo")
        if self.profile.light_kind:
            keys.append("motomotion_light_toggle")
        if self.profile.massage:
            keys.extend(("motomotion_heat_down", "motomotion_heat_up"))
        if (
            self.profile.panel == "H"
            or (self.profile.panel == "Five" and self.profile.char(14) not in ("N", "M", "X"))
            or (self.profile.panel == "Six" and self.profile.heat)
        ):
            keys.append("motomotion_heat_cycle")
        if self.profile.massage:
            keys.extend(("motomotion_massage_down", "motomotion_massage_up"))
        if self.profile.rgb:
            keys.extend(("motomotion_rgb_apply", "motomotion_timer_apply"))
        if self.profile.panel == "Binary music":
            keys.extend("motomotion_music_" + s for s in ("play", "next", "previous"))
        if self.profile.users:
            keys.extend("motomotion_posture_" + s for s in ("recall", "save", "reset"))
        if self.held_control_options:
            keys.append("motomotion_release")
        keys.append("motomotion_unbind")
        return tuple(
            ControllerButtonSpec(
                key,
                self._action_label(key),
                partial(action, key=key),
                translation_key="motomotion_release"
                if key == "motomotion_release"
                else "motomotion_action",
                translation_placeholders={"action": self._action_label(key)},
                release_only=key == "motomotion_release",
                # The admitted controller owns both the first tick and cleanup delay.
                hold=ControllerHoldSpec(
                    key,
                    release_button_key="motomotion_release",
                )
                if key in self.held_control_options
                else None,
            )
            for key in keys
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        choices: dict[str, tuple[str, ...]] = {}
        if self.profile.sides:
            choices["side"] = ("left", "right")
        if self.profile.music:
            choices["music_mode"] = tuple(MUSIC)
        if self.profile.users:
            choices["posture"] = ("upright", "recline", "tv", "lay")
        return tuple(
            ControllerSelectSpec(
                "motomotion_" + key,
                "motomotion_" + key,
                "motomotion_" + key,
                values,
                partial(select, key=key),
            )
            for key, values in choices.items()
        )

    async def select(self, key: str, value: str) -> None:
        choices = next(
            (s.options for s in self.controller_select_specs if s.key == "motomotion_" + key), ()
        )
        if value not in choices:
            raise ValueError("Unavailable MotoMotion selection")
        if key == "side":
            if self.command_side is not None and self.command_side != value:
                raise ValueError("A paired child cannot select the other side")
            self._side = value
        elif key == "posture":
            self._select_posture(value)
        else:
            self._music_mode = value
            profile = self._custom_eq if value == "custom" else list(MUSIC[value])
            self._eq[1:] = profile[1:]
            if self.profile.panel == "Binary music":
                params = [
                    self._eq[1],
                    self._eq[1],
                    self._eq[2],
                    self._eq[3],
                    *BINARY_EXTRA[value],
                    self._eq[0],
                ]
                for i, (code, param) in enumerate(zip((1, 2, 3, 4, 5, 6, 9), params, strict=True)):
                    if i and not await self._wait(0.05, self._coordinator.cancel_command):
                        return
                    await self.write_command(binary_command(code, param))
            else:
                await self.write_command(
                    b"".join(
                        music_command(letter, v) for letter, v in zip("MTBV", self._eq, strict=True)
                    )
                )
        self._publish()

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        ranges: dict[str, tuple[int, int]] = {}
        if self.profile.music:
            ranges.update(
                {
                    "volume": (0, 63 if self.profile.panel == "Binary music" else 22),
                    **dict.fromkeys(
                        ("treble", "bass", "vibration"),
                        (0, 31 if self.profile.panel == "Binary music" else 15),
                    ),
                }
            )
        if self.profile.rgb:
            ranges.update(dict.fromkeys(("red", "green", "blue"), (0, 255)))
            ranges["timer"] = (0, 7259)
        if self.profile.users:
            ranges.update(dict.fromkeys(("height", "buttocks", "knee"), (0, 65535)))
            ranges.update({"target_" + k: (0, v) for k, v in FINE_LIMITS.items()})
        return tuple(
            ControllerNumberSpec(
                "motomotion_" + key,
                "motomotion_" + key,
                "motomotion_" + key,
                low,
                high,
                1,
                partial(
                    number,
                    key=key,
                ),
            )
            for key, (low, high) in ranges.items()
        )

    async def set_number(self, key: str, value: float) -> None:
        spec = next((s for s in self.controller_number_specs if s.key == "motomotion_" + key), None)
        if (
            spec is None
            or not isfinite(value)
            or not spec.native_min_value <= value <= spec.native_max_value
        ):
            raise ValueError("MotoMotion value is outside this control's range")
        v = int(value)
        if key in ("volume", "treble", "bass", "vibration"):
            i = ("volume", "treble", "bass", "vibration").index(key)
            if self._music_mode != "custom" and (
                key == "bass" or (key == "treble" and self.profile.panel != "Binary music")
            ):
                raise ValueError("Treble and bass require custom music mode")
            self._eq[i] = v
            if self._music_mode == "custom":
                self._custom_eq[i] = v
                self._coordinator.save_app_state(self)
            if self.profile.panel == "Binary music":
                code = (9, 1, 3, 4)[i]
                await self.write_command(binary_command(code, v))
                if key == "treble" and await self._wait(0.05, self._coordinator.cancel_command):
                    await self.write_command(binary_command(2, v))
            else:
                await self.write_command(music_command("MTBV"[i], value))
        elif key in ("red", "green", "blue"):
            self._rgb[("red", "green", "blue").index(key)] = v
            await self._color()
        elif key == "timer":
            self._timer = v
        elif key in ("height", "buttocks", "knee"):
            if self._dimensions.get(key) != value:
                self._targets = None
            self._dimensions[key] = value
        elif key.startswith("target_"):
            current = self._targets or self._position()
            self._targets = replace(current, **{key.removeprefix("target_"): v})
            await self.write_command(self._targets.to_bytes())
        self._publish()

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        specs = (
            ControllerStateSensorSpec(
                "motomotion_status",
                "motomotion_status",
                "motomotion_status",
                "mdi:bed",
                attribute_keys=(
                    "motomotion_user",
                    "motomotion_users",
                    "motomotion_panel_heat",
                    "motomotion_lift_status",
                    "motomotion_panel",
                    "motomotion_tokens",
                    "motomotion_received",
                    "motomotion_heat",
                    "motomotion_massage",
                ),
            ),
        )

        if not self.profile.sides:
            return specs
        sides = (
            (self.command_side,) if self.command_side in ("left", "right") else ("left", "right")
        )
        return specs + tuple(
            ControllerStateSensorSpec(
                f"motomotion_{kind}_{side}",
                f"motomotion_{kind}_{side}",
                f"motomotion_{kind}_{side}",
                "mdi:seat",
            )
            for side in sides
            for kind in ("heat", "massage")
        )

    @property
    def supports_motomotion_users(self) -> bool:
        return self.profile.users

    def validate_motomotion_request(self, request: Request) -> None:
        if not self.profile.users:
            raise ValueError("This name has no MotoMotion users tab")
        if request.posture not in ("upright", "recline", "tv", "lay"):
            raise ValueError("Unknown MotoMotion posture")
        if request.operation == "save_user":
            if (
                not request.user
                or request.dimensions is None
                or any(not isfinite(x) for x in request.dimensions)
            ):
                raise ValueError(
                    "Supply a user and finite height, buttocks height and knee height in cm"
                )
        elif request.operation in ("select_user", "delete_user"):
            if request.user not in self._users:
                raise ValueError("Select an existing MotoMotion user")
        elif request.operation == "fine_tune":
            if request.targets is None or any(
                not 0 <= getattr(request.targets, key) <= maximum
                for key, maximum in FINE_LIMITS.items()
            ):
                raise ValueError("Fine tune targets must fit the app sliders")
        elif request.operation in ("recall", "reset_posture"):
            if request.user is not None and request.user not in self._users:
                raise ValueError("Select an existing MotoMotion user")
            if not self._dimensions and request.user is None:
                raise ValueError("Save and select measurements before recalling a posture")
        elif request.operation == "save_posture":
            if request.posture != self._posture or (
                request.user is not None and request.user != self._user
            ):
                raise ValueError("Working targets belong to a different user or posture")
            if self._targets is None:
                raise ValueError("Recall or fine tune a posture first")
        else:
            raise ValueError("Unknown MotoMotion user operation")
        self._parameter()

    async def async_execute_motomotion_request(self, request: Request) -> None:
        self.validate_motomotion_request(request)
        if request.operation == "save_user":
            assert request.user is not None and request.dimensions is not None
            self._users[request.user] = request.dimensions
            if request.user == self._user:
                self._dimensions = dict(
                    zip(("height", "buttocks", "knee"), request.dimensions, strict=True)
                )
                self._targets = None
        elif request.operation == "delete_user":
            assert request.user is not None
            del self._users[request.user]
            self._user_positions.pop(request.user, None)
            if self._user == request.user:
                self._user = None
                self._dimensions.clear()
                self._custom.clear()
                self._targets = None
        if request.operation == "select_user" or (
            request.operation in ("recall", "reset_posture") and request.user is not None
        ):
            assert request.user is not None
            self._user = request.user
            self._dimensions = dict(
                zip(("height", "buttocks", "knee"), self._users[request.user], strict=True)
            )
            self._targets = None
            self._custom = self._user_positions.setdefault(request.user, {})
        self._select_posture(request.posture)
        if request.operation == "fine_tune":
            self._targets = request.targets
            assert self._targets is not None
            await self.write_command(self._targets.to_bytes())
        elif request.operation in ("recall", "reset_posture", "save_posture"):
            await self.action(
                "motomotion_posture_"
                + {"recall": "recall", "reset_posture": "reset", "save_posture": "save"}[
                    request.operation
                ]
            )
        self._coordinator.save_app_state(self)
        self._publish()
