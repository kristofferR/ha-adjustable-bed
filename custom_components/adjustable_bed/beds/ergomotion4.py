"""Direct BLE controls from the accepted com.sfd.hump 3.7 audit.

Product selection is explicit. Shared UUIDs never identify a remote layout.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from time import monotonic
from typing import TYPE_CHECKING, cast

from ..codec import keeson as codec
from ..ergomotion4_profiles import ACTIONS, PRODUCTS, Action, Product, Step
from ..profiles.keeson import ergomotion_4_profile
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from .keeson_layout_app import AppController

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

TX_UUIDS = frozenset(
    (
        "0000ffe9-0000-1000-8000-00805f9b34fb",
        "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400021-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400002-b5a3-f393-e0a9-38534c454550",
    )
)
RX_UUIDS = frozenset(
    (
        "0000ffe4-0000-1000-8000-00805f9b34fb",
        "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400022-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400027-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400003-b5a3-f393-e0a9-38534c454550",
    )
)
# This subscribed suffix never reaches the app's broadcast receiver.
SILENT_RX = "6e400003-b5a3-f393-e0a9-38534c454550"
P2_KEYS = frozenset(
    (
        0,
        1,
        2,
        4,
        8,
        16,
        32,
        64,
        80,
        128,
        160,
        192,
        240,
        256,
        512,
        1024,
        2048,
        4096,
        8192,
        16384,
        32768,
        65536,
        69632,
        131072,
        8388608,
        16777216,
        33554432,
        67108864,
        134217728,
        134221824,
        1073741824,
        1207959552,
    )
)
MODEL_KEYS = ("k1", "k2", "k3", "o1", "o2", "o3", "o4", "o5")
MASSAGE_KEYS = tuple(f"m{i}" for i in range(1, 11))
CONF_MODEL_KEYS = "ergomotion4_model_keys"
CONF_MASSAGE_KEYS = "ergomotion4_massage_keys"
CONF_RGB = "ergomotion4_rgb"
CONF_PRODUCT_NAME = "ergomotion4_product_name"
# Host-side bound for confirming a requested toggle, not a firmware timing value.
LIGHT_POWER_CONFIRM_TIMEOUT_SECONDS = 2.0


def p2_frame(key: int) -> bytes:
    """Finite shipped switch, including its zero-key fallback."""
    return codec.p2(key if key in P2_KEYS else codec.RELEASE)


def custom_product(
    name: str, model: tuple[str, ...], massage: tuple[str, ...], light: bool, rgb: bool
) -> Product:
    """The artifact's ordered model keys and effective ancestor gates."""
    if any(k not in MODEL_KEYS for k in model) or any(k not in MASSAGE_KEYS for k in massage):
        raise ValueError("Choose only the app's declared feature keys")
    if len(set(model)) != len(model) or len(set(massage)) != len(massage):
        raise ValueError("Feature keys must be unique")
    ids: list[int] = []
    simple = any(k in model for k in ("k1", "k2", "k3"))
    if simple:
        for k, values in (("k1", (12, 18)), ("k2", (3, 8)), ("k3", (32,))):
            if k in model:
                ids.extend(values)
    else:
        if "m10" in massage:
            ids.extend((2, 7, 10, 11, 16, 17, 31, 36))
        elif any(k in massage for k in ("m7", "m8", "m9")):
            ids.extend((20, 21, 47, 48, 33, 34))
            for k, values in (("m7", (13, 14)), ("m8", (19, 22)), ("m9", (4, 5))):
                if k in massage:
                    ids.extend(values)
        else:
            ids.extend((1, 6, 9, 15, 30, 35))
        if any(k in model for k in ("o1", "o2", "o3", "o4")):
            slots = 4 if {"o1", "o2", "o3", "o4"} <= set(model) else 3
            ids.extend(43 + int(k[1]) - 1 for k in model[:slots] if k in ("o1", "o2", "o3", "o4"))
    if "m1" in massage:
        ids.append(42)
        if "m2" in massage:
            ids.append(41)
    if {"m3", "m4"} <= set(massage):
        ids.extend((23, 24, 25, 26))
    elif {"m5", "m6"} <= set(massage):
        ids.extend((38, 40))
    elif "m5" in massage:
        ids.append(40)
    elif "m6" in massage:
        ids.append(39)
    if light:
        ids.append(37)
    return Product(
        name,
        "P2",
        tuple(f"C{i:03}" for i in sorted(ids)),
        ("C027", "C028", "C029") if light and rgb else (),
        light and rgb,
    )


def parse_status(
    data: bytes, style: str, *, dynamic: bool = False, side: str = "both"
) -> dict[str, object]:
    """Dispatch complete notifications only; discarded locals are not positions."""

    def timer(seconds: int) -> int:
        return (seconds - 1) // 600 + 1 if 1 <= seconds <= 1800 else -1

    def signed(index: int) -> int:
        return int.from_bytes(data[index : index + 1], signed=True)

    n = len(data)
    if n == 18 and data[:3] == b"\xa5\x0b\x0f":
        return {"timer": timer(int.from_bytes(data[3:5], "big")), "light": bool(data[12])}
    if n == 16:
        if data[:3] == b"\xa5\x0b\x0d":
            if style == "M10":
                return {"timer": signed(5)}
            result: dict[str, object] = {"timer": timer(int.from_bytes(data[3:5], "big"))}
            if style in ("M16", "M19") or dynamic:
                result["light"] = bool(data[12])
            return result
        return {} if data[13] & 32 else {"timer": signed(14)}
    if n == 19:
        if data[:3] == b"\xa5\x0d\x10":
            return {}
        if style == "M19" or dynamic:
            return {
                "timer": timer(int.from_bytes(data[3:5], "big")),
                "light": bool(data[12]),
                "rgb": tuple(data[15:18]),
            }
        bits = data[16] & 3
        if bits and ((bits & 2 and side != "right") or (not bits & 2 and side == "right")):
            return {}
        return {"timer": signed(14 if data[0] == 241 else 15)}
    if n in (20, 23):
        return {"timer": signed(14 if n == 20 else 15)}
    if n == 31:
        if data[:2] == b"\x1d\x0b":
            return {"timer": -1, "light": bool(data[14])}
        if data[:2] == b"\x1c\x0b":
            return {
                "timer": timer(int.from_bytes(data[3:5], "big")),
                "light": bool(data[10]),
                "rgb": tuple(data[11:14]),
            }
        return {"timer": timer(int.from_bytes(data[2:4], "big"))}
    return {}


class Ergomotion4Controller(AppController):
    """One physical connection, exact selected product and task-local sides."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        data = coordinator.entry.data
        selected = data.get("product_type", "H")
        if selected == "custom":
            self.product = custom_product(
                data.get(CONF_PRODUCT_NAME, "Custom"),
                tuple(data.get(CONF_MODEL_KEYS, ())),
                tuple(data.get(CONF_MASSAGE_KEYS, ())),
                data.get("has_light", False),
                data.get(CONF_RGB, False),
            )
        else:
            try:
                self.product = PRODUCTS[selected]
            except KeyError as err:
                raise ValueError("Choose an Ergomotion 4.0 product") from err
        self._dynamic = selected == "custom" or selected not in {
            "H",
            *(f"M{i}" for i in range(1, 23)),
            "M30",
            "EZI MAID",
        }
        # Reuse the existing transport, rename, clock and validated alarm tables.
        super().__init__(coordinator, ergomotion_4_profile(self.product.style))
        self._light: bool | None = None
        self._light_state_changed = asyncio.Event()
        self._rgb = (0, 0, 0)
        self._rgb_seeded = False
        self._level = 100

    @property
    def supports_single_address_pairing(self) -> bool:
        return self.product.protocol == "P1"

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # Every app action, including distinct dual-head axes, has its own held
        # button. Do not infer actuator geometry from numeric keys or artwork.
        return ()

    @property
    def supports_preset_flat(self) -> bool:
        return False

    def _actions(self) -> tuple[Action, ...]:
        return tuple(ACTIONS[k] for k in self.product.commands + self.product.light_commands)

    def _selected_action(self, key: str) -> Action:
        for action in self._actions():
            if action.key == key:
                if (
                    action.light_gate or action.key.upper() in self.product.light_commands
                ) and self._light is not True:
                    raise ValueError("This control requires reported light-on state")
                return action
        raise ValueError("Control is unavailable for the selected Ergomotion 4.0 product")

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(a.key for a in self._actions() if a.held)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        def press(key: str):
            async def run(controller: BedController) -> None:
                await cast(Ergomotion4Controller, controller)._run_action(key)

            return run

        specs = tuple(
            ControllerButtonSpec(
                a.key,
                a.name,
                press(a.key),
                hold=ControllerHoldSpec(a.key, 0, 0) if a.held else None,
            )
            for a in self._actions()
        )
        # Shared alarm dismissal is not gated by a selected product.
        specs += (
            ControllerButtonSpec(
                "dismiss_alarm",
                "Dismiss wake vibration",
                lambda c: c.stop_wake_routine(),
                cancel_movement=False,
                scheduler_resource="configuration",
            ),
        )
        if self._meditation_product:
            specs += tuple(
                ControllerButtonSpec(
                    key,
                    name,
                    press(key),
                )
                for key, name in (
                    ("meditation_start", "Start meditation"),
                    ("meditation_stop", "Stop meditation"),
                )
            )
        return specs

    def controller_button_available(self, key: str) -> bool:
        if key in {"dismiss_alarm", "meditation_start", "meditation_stop"}:
            return key == "dismiss_alarm" or self._meditation_allowed
        try:
            self._selected_action(key)
        except ValueError:
            return False
        return True

    def _frame(self, mask: int) -> bytes:
        if self.product.protocol == "P2":
            if self.command_side in ("left", "right"):
                raise ValueError("Ergomotion 4.0 P2 has no side selector")
            return p2_frame(mask)
        if self.command_side in ("left", "right"):
            return codec.side_frame(mask & 0xFFFFFFFF, cast(codec.Side, self.command_side))
        return codec.frame(mask & 0xFFFFFFFF)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if (
            self.client is self._session_client
            and self._tx is not None
            and self._rx is not None
            and not self._session_cancel.is_set()
        ):
            self._notify_callback = callback
            return
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Ergomotion 4.0 session is disconnected")
        rx_chars = []
        for service in client.services:
            for char in service.characteristics:
                if char.uuid.lower() in TX_UUIDS:
                    self._tx = char
                if char.uuid.lower() in RX_UUIDS:
                    self._rx = char
                    rx_chars.append(char)
        if self._tx is None or self._rx is None:
            self.on_disconnect()
            raise ConnectionError("Ergomotion 4.0 requires write and notification characteristics")
        self._session_client = client
        self._session_cancel = asyncio.Event()
        self._notify_callback = callback
        session = self._session_cancel
        for char in rx_chars:

            def notify(
                sender: BleakGATTCharacteristic, data: bytearray, *, uuid: str = char.uuid
            ) -> None:
                if client is self._session_client and not session.is_set():
                    self.forward_raw_notification(uuid, bytes(data))
                    if uuid.lower() != SILENT_RX:
                        self._parse_notification(bytes(data))

            await client.start_notify(char, notify)
        self._notification_chars = tuple(rx_chars)
        # M30/EZI MAID initializes using P1 zero despite its P2 movement keys.
        if self.product.protocol == "P1" or self.product.style == "M30":
            await self.write_command(codec.frame(codec.RELEASE))
        else:
            await self._queries((300, 600, 900))

    async def stop_notify(self) -> None:
        client, chars = self._session_client, getattr(self, "_notification_chars", ())
        self.on_disconnect()
        if client is not None and client.is_connected:
            for char in chars:
                await client.stop_notify(char)

    def on_disconnect(self) -> None:
        super().on_disconnect()
        self._notification_chars = ()
        self._light = None
        self._rgb_seeded = False
        self.forward_controller_state_updates(
            {
                prefix + key: None
                for prefix in ("", "left_", "right_")
                for key in (
                    "app_timer_status",
                    "ergomotion4_light",
                    "under_bed_lights_on",
                    "under_bed_lights_rgb",
                )
            }
        )

    async def _steps(self, steps: tuple[Step, ...], *, cleanup: bool = False) -> None:
        session = self._session_cancel
        for kind, value in steps:
            if session is not self._session_cancel or session.is_set():
                return
            if not cleanup and self._coordinator.cancel_command.is_set():
                return
            if kind == "delay":
                if await self._wait(value, cleanup=cleanup):
                    return
            elif kind == "query":
                await self._queries((300, 600, 900), cleanup=cleanup)
            elif kind == "brightness":
                await self._send_rgb(self._rgb, value)
            else:
                frame = (
                    self._frame(value)
                    if kind == "p1"
                    else p2_frame(value)
                    if kind == "p2"
                    else codec.custom_massage(value)
                )
                await self.write_command(frame, cancel_event=asyncio.Event() if cleanup else None)

    async def _queries(self, offsets: tuple[int, ...], *, cleanup: bool = False) -> None:
        session = self._session_cancel
        previous = 0
        for offset in offsets:
            if await self._wait(offset - previous, cleanup=cleanup):
                return
            if session is not self._session_cancel or session.is_set():
                return
            await self.write_command(codec.STATUS_QUERY, cancel_event=asyncio.Event() if cleanup else None)
            previous = offset

    def _device_name_frame(self, name: str) -> bytes:
        # The sixteenth copied byte is overwritten by the source checksum.
        # Longer input overruns its 18-byte array and is rejected before BLE.
        name = name.strip("".join(chr(value) for value in range(33)))
        units = len(name.encode("utf-16-le")) // 2
        if not name or units > 16:
            raise ValueError("Use a nonempty name of at most 16 UTF-16 units")
        return codec.rename(name.encode("utf-8")[: min(units, 15)])

    async def _run_action(self, key: str) -> None:
        if key in ("meditation_start", "meditation_stop"):
            if not self._meditation_allowed:
                raise ValueError("The selected product and Bluetooth name do not admit meditation")
            code = (
                0x48000000
                if self.product.style == "M14"
                or ("Flex3" in self.product.style and "Massage" in self.product.style)
                else 0x11000
            )
            await self._steps(
                (
                    ("p2", code if key.endswith("start") else 0x08000000),
                    ("delay", 200),
                    ("query", 0),
                )
            )
            return
        action = self._selected_action(key)
        if action.held:
            await self.hold_control(
                key, max(1, min(60000, self._coordinator.motor_pulse_count * 100))
            )
            return
        # Source pulse cleanup survives cancellation and a failed first write.
        pulse = len(action.steps) > 1 and action.steps[-1] in (("p1", 0), ("query", 0))
        if pulse:
            session = self._session_cancel
            try:
                await self._steps(action.steps[:-1])
            finally:
                if session is self._session_cancel and not session.is_set():
                    await self._steps(action.steps[-1:], cleanup=True)
        else:
            await self._steps(action.steps)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        action = self._selected_action(control)
        self._ready()
        session = self._session_cancel
        try:
            deadline = monotonic() * 1000 + duration_ms
            while monotonic() * 1000 < deadline and not self._coordinator.cancel_command.is_set():
                await self._steps(action.steps)
                remaining = deadline - monotonic() * 1000
                if remaining <= 0 or await self._wait(min(100, remaining)):
                    break
        finally:
            if session is self._session_cancel and not session.is_set():
                await self._steps(action.release, cleanup=True)

    async def _release(self) -> None:
        if self._session_client is self.client and not self._session_cancel.is_set():
            await self._steps(
                (("p1", 0),) if self.product.protocol == "P1" else (("query", 0),), cleanup=True
            )

    @property
    def _meditation_product(self) -> bool:
        style = self.product.style
        return (
            style in ("M14", "M21") or ("Flex3" in style and "Massage" in style) or "20th" in style
        )

    @property
    def _meditation_allowed(self) -> bool:
        name = self._coordinator.observed_ble_device_name or self._coordinator.entry.data.get(
            "ble_device_name", ""
        )
        if not self._meditation_product or not name:
            return False
        if "20th" in self.product.style:
            return True
        return name.upper().startswith("KSBT03CW" if self.product.style == "M21" else "KSBT03CP")

    @property
    def supports_light_color_control(self) -> bool:
        return self.product.rgb

    @property
    def supported_color_mode(self) -> str | None:
        return "rgb" if self.product.rgb else None

    @property
    def supports_lights(self) -> bool:
        return self.product.rgb

    @property
    def supports_light_toggle_control(self) -> bool:
        # Exact product-labelled toggles are already in controller_button_specs.
        return False

    @property
    def supports_discrete_light_control(self) -> bool:
        # The public power methods use reported state to make toggles idempotent.
        return self.product.rgb

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.product.rgb

    @property
    def supports_explicit_light_on_control(self) -> bool:
        return self.product.rgb

    async def lights_toggle(self) -> None:
        action = next(
            (
                a
                for a in self._actions()
                if a.steps and a.steps[0] in (("p1", 0x20000), ("p2", 0x20000))
            ),
            None,
        )
        if action is None:
            raise ValueError("The selected product has no light toggle")
        await self._run_action(action.key)

    async def lights_on(self) -> None:
        await self._set_light_power(True)

    async def lights_off(self) -> None:
        await self._set_light_power(False)

    async def _set_light_power(self, enabled: bool) -> None:
        self._ready()
        if self._light is None:
            raise ValueError("Wait for reported light state before changing power")
        if self._light is enabled:
            return
        session = self._session_cancel
        await self.lights_toggle()
        # A color write following power-on must wait for the source's light-on
        # gate. Session/cancellation waiters also release the command lane promptly.
        async with asyncio.timeout(LIGHT_POWER_CONFIRM_TIMEOUT_SECONDS):
            while True:
                self._ready()
                if session is not self._session_cancel or session.is_set():
                    raise ConnectionError("Light confirmation belongs to an expired session")
                if self._coordinator.cancel_command.is_set():
                    raise asyncio.CancelledError
                if self._light is enabled:
                    return
                self._light_state_changed.clear()
                waiters = tuple(
                    asyncio.create_task(event.wait())
                    for event in (
                        self._light_state_changed,
                        session,
                        self._coordinator.cancel_command,
                    )
                )
                try:
                    await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for waiter in waiters:
                        waiter.cancel()
                    await asyncio.gather(*waiters, return_exceptions=True)

    async def _send_rgb(self, color: tuple[int, int, int], level: int) -> None:
        if not self.product.rgb or self._light is not True:
            raise ValueError("RGB requires a selected RGB product and reported light-on state")
        # Java float multiplication, then truncation. The source's three levels
        # are 1.0f, 0.6f, 0.2f; struct preserves their binary32 arithmetic.
        import struct

        factor = struct.unpack("f", struct.pack("f", level / 100))[0]
        scaled = tuple(int(struct.unpack("f", struct.pack("f", c * factor))[0]) for c in color)
        frame = codec.rgb(
            cast(tuple[int, int, int], scaled),
            inverted=self._dynamic and "4194" in self.product.style,
        )
        await self.write_command(frame)
        self._rgb, self._level = color, level

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        if any(type(c) is not int or not 0 <= c <= 255 for c in rgb_color):
            raise ValueError("RGB channels must be integers 0 through 255")
        await self._send_rgb(rgb_color, self._level)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        prefix = f"{self.command_side}_" if self.command_side in ("left", "right") else ""
        return (
            ControllerStateSensorSpec(
                "app_timer_status",
                "app_timer_status",
                prefix + "app_timer_status",
                "mdi:timer-outline",
            ),
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        prefix = f"{self.command_side}_" if self.command_side in ("left", "right") else ""
        return (
            ControllerStateBinarySensorSpec(
                "ergomotion4_light",
                "ergomotion4_light",
                prefix + "ergomotion4_light",
                "mdi:lightbulb-outline",
            ),
        )

    def _parse_notification(self, data: bytes | None) -> None:
        if not data:
            return
        updates: dict[str, object] = {}
        for side in ("both", "left", "right"):
            parsed = parse_status(data, self.product.style, dynamic=self._dynamic, side=side)
            prefix = "" if side == "both" else f"{side}_"
            if "timer" in parsed:
                updates[prefix + "app_timer_status"] = parsed["timer"]
            if "light" in parsed:
                updates[prefix + "ergomotion4_light"] = parsed["light"]
                updates[prefix + "under_bed_lights_on"] = parsed["light"]
            if "rgb" in parsed:
                updates[prefix + "under_bed_lights_rgb"] = parsed["rgb"]
            if side == "both":
                if "light" in parsed:
                    self._light = bool(parsed["light"])
                    self._light_state_changed.set()
                if (
                    "rgb" in parsed
                    and not self._rgb_seeded
                    and (self.product.style == "M19" or self._dynamic)
                ):
                    self._rgb = cast(tuple[int, int, int], parsed["rgb"])
                    self._rgb_seeded = True
        if updates:
            self.forward_controller_state_updates(updates)
