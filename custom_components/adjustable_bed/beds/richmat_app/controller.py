"""Richmat 4.2.0 product controls and connection-scoped state."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, Final, cast

from homeassistant.util import dt as dt_util

from ...card import CARD_HIDDEN
from ...codec import richmat as codec
from ...controller_state import StateKey
from ...profiles.richmat import RICHMAT_APP, RichmatProfile
from ..base import CONTROLLER_GESTURE_RELEASE, BedController, ProfileExecution, require_controller
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from . import protocol as p
from .catalog import (
    ACTIONS,
    ENUM_CODES,
    GROOVE_PALETTE,
    LABELS,
    PRODUCTS,
    Action,
    Product,
    descriptors,
)
from .receive import Receiver, Value
from .requests import DemoStep, Request

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

TICK = 0.1
PROBE = 0.05
STATUS: Final = StateKey[str | None]("richmat_app_status")
EVENTS: Final = StateKey[dict[str, Value]]("richmat_app_events")
CAPABILITIES: Final = StateKey[list[str]]("richmat_app_capabilities")
ALARMS: Final = StateKey[list[dict[str, Value]]]("richmat_app_alarms")
BLANKET: Final = StateKey[dict[str, Value]]("richmat_app_blanket")
LOCAL: Final = StateKey[dict[str, object]]("richmat_app_local")
SIDE: Final = StateKey[str | None]("richmat_app_side")
REJECTION: Final = StateKey[str | None]("richmat_app_rejection")
MOTOR_KEYS = tuple(StateKey[int | None](f"richmat_app_motor_{n}") for n in range(4))
MASSAGE_KEYS = tuple(StateKey[int | None](f"richmat_app_massage_{n}") for n in range(2))


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    tx: BleakGATTCharacteristic
    rx: BleakGATTCharacteristic
    single: bool


def select_link(client: BleakClient) -> Link:
    routes = {codec.TRANSPORTS[k].service_uuid: codec.TRANSPORTS[k] for k in RICHMAT_APP.transports}
    tx = rx = None
    single = False
    for service in client.services:
        route = routes.get(service.uuid.lower())
        if route is None:
            continue
        single = route.single
        for char in service.characteristics:
            if (
                tx is None
                and char.uuid.lower() == route.write_uuid.lower()
                and "write" in char.properties
            ):
                tx = char
            if rx is None and "notify" in char.properties:
                rx = char
    if tx is None or rx is None:
        raise ValueError(
            "Richmat app requires its selected writable and notification characteristics"
        )
    return Link(client, tx, rx, single)


def action_name(action: Action) -> str:
    return re.sub(
        r"(?<!^)(?=[A-Z])",
        " ",
        action["enum"].removeprefix("deviceFunctionItem").removeprefix("deviceFunction"),
    ).replace("Lumber", "Lumbar")


async def _press(controller: BedController, *, detail: str, save: bool = False) -> None:
    await require_controller(controller, RichmatAppController).press(detail, save=save)


async def _release(_controller: BedController) -> None:
    # STOP admission cancels the owning hold; its finally sends the release.
    return


class RichmatAppController(ProfileExecution[RichmatProfile], BedController):
    """An explicit product identity, never inferred from a shared service or scalar alias."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, product: str) -> None:
        super().__init__(coordinator)
        if product not in PRODUCTS:
            raise ValueError("Choose the Richmat 4.2.0 product code")
        self.profile = RICHMAT_APP
        self.product_key = product
        self.product: Product = PRODUCTS[product]
        self._link: Link | None = None
        self._last_write: float | None = None
        self._expiry: asyncio.TimerHandle | None = None
        self._version_task: asyncio.Task[None] | None = None
        self._receiver = Receiver(self._accept)
        self.version = 0
        self.features: set[str] = set()
        self.events: dict[str, Value] = {}
        self.alarms: list[dict[str, Value]] = []
        self.blanket: dict[str, Value] = {"7": False, "b": "warm", "f": 25, "17": 25, "23": False}
        self.local: dict[str, object] = {
            "side": self.product["side"],
            "demo": [],
            "light_seconds": 300,
        }
        self._side_selection = self.product["side"]
        self._motor_values: list[int | None] = [None] * 4
        self._massage_values = [0, 0]
        self._pending_alarm: dict[str, object] | None = None
        self._status: str | None = None
        self._rejection: str | None = None
        self._usb_at = float("-inf")

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.tx.uuid if self._link else codec.TRANSPORTS["w1"].write_uuid

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def has_dynamic_buttons(self) -> bool:
        return True

    @property
    def supports_motor_control(self) -> bool:
        return bool(self.route["motors"])

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_preset_zero_g(self) -> bool:
        return False

    @property
    def supports_preset_anti_snore(self) -> bool:
        return False

    @property
    def supports_preset_tv(self) -> bool:
        return False

    @property
    def memory_slot_count(self) -> int:
        return 0

    @property
    def auto_stops_on_idle(self) -> bool:
        return False

    @property
    def supports_single_address_pairing(self) -> bool:
        return len(cast(list[object], self.product["selectors"]["0x11eaf"])) > 1

    @property
    def route(self):
        return self.product["versions"]["one" if self.version == 1 else "other"]

    @property
    def massage_actions(self) -> tuple[str, ...]:
        return descriptors(self.product, "0xf761" if self.version == 1 else "0xeea5")

    @property
    def alarm_actions(self) -> tuple[str, ...]:
        return descriptors(self.product, "0x108d9" if self.version == 1 else "0xe18b")

    def _side(self) -> int:
        explicit = self.command_side
        side = (
            {"left": 0, "right": 1, "both": 2}.get(explicit, self._side_selection)
            if explicit
            else self._side_selection
        )
        # command_side denotes physical sides; the Android label swap applies only to its UI.
        return side

    def _current_link(self) -> Link:
        link = self._link
        if link is None or self.client is not link.client or not link.client.is_connected:
            raise ConnectionError("Richmat app BLE session changed")
        return link

    async def _send(
        self,
        data: bytes,
        link: Link,
        cancel: asyncio.Event | None = None,
        *,
        deadline: float | None = None,
    ) -> bool:
        async with self._ble_lock:
            if self._last_write is not None:
                await asyncio.sleep(max(0, self._last_write + TICK - monotonic()))
            if cancel is not None and cancel.is_set():
                return False
            if deadline is not None and monotonic() > deadline + 1e-9:
                return False
            if self._current_link() is not link:
                raise ConnectionError("Richmat app BLE session changed")
            self._last_write = monotonic()
            response = "write-without-response" not in link.tx.properties
            self._coordinator.record_command_trace(
                payload={"hex": data.hex()},
                characteristic_uuid=link.tx.uuid,
                characteristic_handle=link.tx.handle,
                response=response,
                repeat_count=1,
                repeat_delay_ms=100,
                command_origin="richmat_app",
                controller_class=type(self).__name__,
            )
            await link.client.write_gatt_char(link.tx, data, response=response)
        return True

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._current_link()
        for _ in range(repeat_count):
            if not await self._send(
                command, link, cancel_event or self._coordinator.cancel_command
            ):
                break

    async def _wait(self, seconds: float, cancel: asyncio.Event) -> bool:
        try:
            await asyncio.wait_for(cancel.wait(), seconds)
            return False
        except TimeoutError:
            return True

    def _generic(self, enum: str, *, side: int | None = None) -> bytes:
        code = ENUM_CODES[enum]
        return p.function(
            enum,
            code,
            self._side() if side is None else side,
            self._current_link().single,
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Richmat app disconnected")
        self.on_disconnect()
        link = select_link(client)
        self._link = link
        self.features.clear()
        self.version = 0
        self._side_selection = self.product["side"]
        try:
            await client.start_notify(link.rx, partial(self._notification, link))
            await self._send(self._generic("deviceFunctionItemExitLimit", side=0), link)
            if self.alarm_actions:
                for frame in p.sync_time(dt_util.now(), dt_util.now()):
                    await self._send(frame, link)
            if self.product["selectors"]["0x10d37"] == "DeviceSleepMonitoringType@cdc971":
                await self._send(p.QUERY["sleep_name"], link)
            if self.product["selectors"]["0xea47"]:
                await self._send(p.QUERY["blanket_power"], link)
            for enum in p.STARTUP:
                await asyncio.sleep(PROBE)
                await self._send(self._generic(enum, side=0), link)
        except BaseException:
            self.on_disconnect()
            raise
        self._publish()

    async def _version_queries(self, link: Link) -> None:
        async def query(controller: BedController) -> None:
            if controller is not self or self._link is not link or self.version != 1:
                return
            for enum in p.VERSION_ONE:
                await asyncio.sleep(PROBE)
                await self._send(
                    self._generic(enum, side=0),
                    link,
                    self._coordinator.cancel_command,
                )

        try:
            await self._coordinator.async_execute_controller_command(query, cancel_running=False)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self._rejection = str(err)
            self._publish()

    def _notification(self, link: Link, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        if self._link is not link or self.client is not link.client or not link.client.is_connected:
            return
        self.forward_raw_notification(link.rx.uuid, bytes(data))
        if self._expiry:
            self._expiry.cancel()
        try:
            self._receiver.feed(bytes(data))
            self._rejection = None
        except (ValueError, IndexError) as err:
            self._rejection = str(err)
        if self._receiver.pending:
            self._expiry = asyncio.get_running_loop().call_later(0.5, self._receiver.pending.clear)
        self._publish()

    def _accept(self, event: str, values: dict[str, Value]) -> None:
        self._status = event
        self.events[event] = deepcopy(values)
        if event == "common":
            version = values.get("version")
            if type(version) is int:
                self.version = version
                if (
                    version == 1
                    and self._link
                    and (self._version_task is None or self._version_task.done())
                ):
                    self._version_task = self._coordinator.entry.async_create_background_task(
                        self._coordinator.hass,
                        self._version_queries(self._link),
                        name="richmat_app_version_queries",
                    )
            no, angle = values.get("no"), values.get("angle")
            if type(no) is int and type(angle) is int and 0 <= no < 4:
                self._motor_values[no] = angle
            for n in range(2):
                value = values.get(f"massage{n + 1}")
                if type(value) is int:
                    self._massage_values[n] = value
            if "type" in values and "number" in values:
                diagnostic_state = self.events.get("diagnostics")
                diagnostics = (
                    diagnostic_state.get("items") if isinstance(diagnostic_state, dict) else None
                )
                items = diagnostics if isinstance(diagnostics, list) else []
                items.append(deepcopy(values))
                self.events["diagnostics"] = {"items": items}
        if event == "clock_available" and self.alarm_actions:
            self.features.add("alarm")
        if event == "product_reload":
            self.features.clear()
        if event == "snore_available" and descriptors(self.product, "0xe5e9"):
            self.features.add("snore")
        if event == "light_available":
            for selector, key in (
                ("0x1047b", "strip"),
                ("0xfbbf", "therapy"),
                ("0xf303", "groove"),
                ("0x1276b", "cold_warm"),
            ):
                if self.product["selectors"][selector]:
                    self.features.add(key)
        if event == "detection_available":
            self.features.add("detection")
        if event == "group_5_1" and isinstance(fields := values.get("fields"), dict):
            if values.get("direction") == 2:
                if fields not in self.alarms:
                    self.alarms.append(deepcopy(fields))
            else:
                old = next((i for i, a in enumerate(self.alarms) if a["7"] == fields["7"]), None)
                if old is not None:
                    self.alarms[old] = deepcopy(fields)
        if event == "alarm_saved" and self._pending_alarm:
            self.local["saved_alarm"] = self._pending_alarm
            self._pending_alarm = None
        if event == "alarm_cancelled":
            self.local.pop("saved_alarm", None)
        if event.startswith("group_13_"):
            operation = int(event.rsplit("_", 1)[1])
            merge = {
                1: ("7",),
                2: ("2f", "33"),
                5: ("b", "f", "17"),
                6: ("23",),
                7: ("53", "57"),
                8: ("3f", "43", "47", "4b", "4f", "3b"),
                9: ("4f", "5b", "63", "6b"),
            }.get(operation, ())
            self.blanket.update({k: deepcopy(values[k]) for k in merge if k in values})
            self._clamp_blanket()
        if event == "group_4_2" and type(timer := values.get("timer")) is int:
            self.events["groove"] = {"received_timer": timer, "page_seconds": timer * 60}
        if event == "group_6_3" and isinstance(raw := values.get("name_bytes"), list):
            self.events["sleep_device"] = {
                "advertised_name": bytes(cast(list[int], raw)).decode("latin1")
            }
        if event == "group_4_1" and isinstance(rgb := values.get("rgb"), list):
            palette = GROOVE_PALETTE
            self.local["groove_palette_index"] = next(
                (n for n, color in enumerate(palette) if list(color) == rgb), -1
            )
        if event == "common":
            for flag in ("ble", "usb", "playing"):
                if flag in values:
                    self.local[flag] = values[flag]
        # The extended producer's position key is retained as diagnostics. It does
        # not satisfy the app's required no key and never mutates motor angles.
        self._publish()

    def _clamp_blanket(self) -> None:
        low, high = (16, 25) if self.blanket.get("b") == "cool" else (25, 55)
        for key in ("f", "17"):
            value = self.blanket.get(key)
            if type(value) is int:
                self.blanket[key] = max(low, min(high, value))

    def on_disconnect(self) -> None:
        self._link = None
        self._last_write = None
        self._receiver.pending.clear()
        if self._expiry:
            self._expiry.cancel()
            self._expiry = None
        if self._version_task and not self._version_task.done():
            self._version_task.cancel()
        self._version_task = None
        self._pending_alarm = None

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link and link.client.is_connected:
            await link.client.stop_notify(link.rx)

    def _publish(self) -> None:
        self.forward_controller_state_updates(
            STATUS(self._status),
            EVENTS(deepcopy(self.events)),
            CAPABILITIES(sorted(self.features)),
            ALARMS(deepcopy(self.alarms)),
            BLANKET(deepcopy(self.blanket)),
            LOCAL(deepcopy(self.local)),
            SIDE(
                ("left", "right", "both")[
                    1 - self._side_selection
                    if self.product["swap"] and self._side_selection != 2
                    else self._side_selection
                ]
            ),
            REJECTION(self._rejection),
        )
        for number in range(4):
            self.forward_controller_state_update(MOTOR_KEYS[number], self._motor_values[number])
        for number in range(2):
            self.forward_controller_state_update(MASSAGE_KEYS[number], self._massage_values[number])

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "product": self.product_key,
            "protocol_version": self.version,
            "hardware_verified": False,
            "events": deepcopy(self.events),
            "capabilities": sorted(self.features),
            "blanket": deepcopy(self.blanket),
            "local": deepcopy(self.local),
            "rejection": self._rejection,
        }

    @property
    def persisted_app_state_key(self) -> str:
        return "richmat_app:" + self.product_key

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return deepcopy(self.local)

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        self.local = deepcopy(dict(state))
        side = state.get("side", self.product["side"])
        if type(side) is int and side in range(3):
            self._side_selection = side

    def _detail_label(self, detail: str, selector: str) -> str:
        expression = self.product["labels"].get(
            selector + ":RMDeviceFunctionItemDetialsType@" + detail, ""
        )
        expression = re.sub(
            r"key:([a-z_]+\d+)", lambda match: LABELS.get(match[1], match[0]), expression
        )
        return (
            expression if expression and "key:" not in expression else action_name(ACTIONS[detail])
        )

    def _allowed(self) -> set[str]:
        choices = (
            {str(d) for row in self.route["motors"] for d in row[1:3]}
            | {str(row[0]) for row in self.route["presets"]}
            | set(self.massage_actions)
            | set(self.auxiliary_actions)
        )
        return {detail for detail in choices if "Desk" not in ACTIONS[detail]["enum"]}

    @property
    def auxiliary_actions(self) -> tuple[str, ...]:
        result = []
        for detail in descriptors(self.product, "0x115f3"):
            action = ACTIONS[detail]
            enum = action["enum"]
            if enum == "deviceFunctionItemControlBoxLock" and self.product["selectors"]["0x11195"]:
                result.append(detail)
            elif enum == "deviceFunctionItemLightBoard":
                if (
                    action["light"]
                    or self.product["light_board"]
                    and self.features.intersection(("strip", "groove", "cold_warm", "therapy"))
                ):
                    result.append(detail)
            elif enum in (
                "deviceFunctionItemMotorReset",
                "deviceFunctionItemBedLight",
                "deviceFunctionItemBedLightClose",
                "deviceFunctionItemSyncOn",
                "deviceFunctionItemSyncOff",
            ):
                result.append(detail)
        return tuple(result)

    async def press(self, detail: str, *, save: bool = False, duration_ms: int = 1000) -> None:
        if detail not in self._allowed():
            raise ValueError("This control is unavailable in the current product/protocol layout")
        if save and not any(row[0] == detail and row[1] for row in self.route["presets"]):
            raise ValueError("This preset has no save control")
        if (
            not save
            and detail in self.massage_actions
            and ACTIONS[detail]["enum"] == "deviceFunctionItemMusicSwitchSoundTrack"
        ):
            await self.execute_request(Request("usb"))
            return
        link = self._current_link()
        side = self._side()
        action = ACTIONS[detail]
        frame = p.function(action["enum"], action["long" if save else "short"], side, link.single)
        held = not save and any(detail in row[1:3] for row in self.route["motors"])
        if not held:
            await self._send(frame, link, self._coordinator.cancel_command)
            return
        cancel = self._coordinator.cancel_command
        fired = False
        start = monotonic()
        until = start + self.leased_hold_ms(duration_ms) / 1000
        tick = 1
        try:
            while start + tick * TICK <= until + 1e-6:
                if not await self._wait(max(0, start + tick * TICK - monotonic()), cancel):
                    break
                fired = True
                if not await self._send(frame, link, cancel, deadline=until):
                    break
                tick = max(tick + 1, int((monotonic() - start + 1e-9) / TICK) + 1)
        finally:
            if fired:
                await self._stop_side(link, side)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple("richmat_app_" + str(d) for row in self.route["motors"] for d in row[1:3])

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 60000
        ):
            raise ValueError(
                "Choose an available Richmat app movement and a duration from 1 to 60000 ms"
            )

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self.press(control.removeprefix("richmat_app_"), duration_ms=duration_ms)

    async def stop_all(self) -> None:
        if CONTROLLER_GESTURE_RELEASE.get():
            return
        await self._stop_side(self._current_link(), self._side())

    async def _stop_side(self, link: Link, side: int) -> None:
        await self._send(
            p.function("deviceFunctionItemStop", 110, side, link.single),
            link,
            asyncio.Event(),
        )

    async def _move(self, enum: str) -> None:
        detail = next(
            (d for d in self._allowed() if ACTIONS[d]["enum"] == "deviceFunctionItem" + enum), None
        )
        if detail is None:
            raise ValueError("Motor or preset is unavailable for this product")
        await self.press(detail)

    async def move_head_up(self) -> None:
        await self._move("HeadUp")

    async def move_head_down(self) -> None:
        await self._move("HeadDown")

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self._move("FootUp")

    async def move_legs_down(self) -> None:
        await self._move("FootDown")

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def preset_flat(self) -> None:
        await self._move("MotorReset")

    async def preset_memory(self, memory_num: int) -> None:
        await self._move(f"MemoryPosition{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        detail = next(
            (
                str(row[0])
                for row in self.route["presets"]
                if ACTIONS[str(row[0])]["enum"] == f"deviceFunctionItemMemoryPosition{memory_num}"
            ),
            None,
        )
        if detail is None:
            raise ValueError("This product has no such memory slot")
        await self.press(detail, save=True)

    def controller_button_available(self, key: str) -> bool:
        return key == "richmat_app_release" or any(
            spec.key == key for spec in self.controller_button_specs
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        rows = []
        motors = {str(d) for m in self.route["motors"] for d in m[1:3]}
        selector = "0xdd2d" if self.version == 1 else "0x1230d"
        for detail in sorted(self._allowed() - motors):
            label = self._detail_label(
                detail,
                selector
                if any(row[0] == detail for row in self.route["presets"])
                else ("0xf761" if self.version == 1 else "0xeea5"),
            )
            rows.append(
                ControllerButtonSpec(
                    "richmat_app_" + detail,
                    label,
                    partial(_press, detail=detail),
                    translation_key="richmat_app_action",
                    translation_placeholders={"action": label},
                )
            )
            if any(row[0] == detail and row[1] for row in self.route["presets"]):
                rows.append(
                    ControllerButtonSpec(
                        "richmat_app_save_" + detail,
                        "Save " + label,
                        partial(_press, detail=detail, save=True),
                        translation_key="richmat_app_action",
                        translation_placeholders={"action": "Save " + label},
                    )
                )
        rows.append(
            ControllerButtonSpec(
                "richmat_app_release",
                "Release movement",
                _release,
                translation_key="richmat_app_release",
                release_only=True,
                card=CARD_HIDDEN,
            )
        )
        return tuple(rows)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                "richmat_app_" + str(menu),
                {
                    "foot": "feet",
                    "headAndFoot": "head_feet",
                    "lumber": "lumbar",
                    "allMotor": "richmat_app_all_motor",
                    "lumbar2": "richmat_app_lumbar2",
                    "tilt1": "richmat_app_tilt1",
                    "tilt2": "richmat_app_tilt2",
                }.get(str(menu), str(menu)),
                partial(_press, detail=str(up)),
                partial(_press, detail=str(down)),
                lambda c: c.stop_all(),
                hold=ControllerMotorHoldSpec(
                    "richmat_app_" + str(up),
                    "richmat_app_" + str(down),
                    0,
                    0,
                    "richmat_app_release",
                    stop_scope="side",
                    press_is_native=True,
                ),
            )
            for menu, up, down, *_ in self.route["motors"]
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "richmat_app_status",
                "richmat_app_status",
                STATUS,
                "mdi:bed",
                attribute_keys=(EVENTS, CAPABILITIES, ALARMS, BLANKET, LOCAL, REJECTION),
            ),
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        sides = cast(list[str], self.product["selectors"]["0x11eaf"])
        options = tuple(
            name
            for ref, name in (("cdcb51", "left"), ("cdcb71", "right"), ("cdcb91", "both"))
            if "DeviceSideOfBedType@" + ref in sides
        )

        def apply(option: str) -> None:
            if option not in options:
                raise ValueError("Unavailable product side")
            side = ("left", "right", "both").index(option)
            self._side_selection = 1 - side if self.product["swap"] and side != 2 else side
            self.local["side"] = self._side_selection
            self._publish()

        async def select(controller: BedController, option: str) -> None:
            require_controller(controller, RichmatAppController)._select_side(option)

        self._select_side = apply
        return (
            (
                ControllerSelectSpec(
                    "richmat_app_side",
                    "richmat_app_side",
                    SIDE,
                    options,
                    select,
                    local_select_fn=apply,
                ),
            )
            if len(options) > 1
            else ()
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        rows = []
        for _menu, _up, _down, exposed, maximum, number in self.route["motors"]:
            if not exposed:
                continue
            n = int(number)

            async def set_angle(
                controller: BedController,
                value: float,
                *,
                motor: int = n,
                limit: int = int(maximum),
            ) -> None:
                target = require_controller(controller, RichmatAppController)
                if target.version != 1 or not 0 <= value <= limit:
                    raise ValueError("This product does not currently expose that target angle")
                await target.write_command(codec.packed_motor(motor, int(value)))

            rows.append(
                ControllerNumberSpec(
                    f"richmat_app_motor_{n}",
                    "richmat_app_angle",
                    MOTOR_KEYS[n],
                    0,
                    int(maximum),
                    1,
                    set_angle,
                    "°",
                )
            )
        if self.version == 1 and self.product["massage_sliders"]["version1_page_slider_gate"]:
            sliders = cast(list[dict[str, object]], self.product["massage_sliders"]["sliders"])
            for n, slider in enumerate(sliders[:2]):
                limit = int(cast(int, slider["maximum"]))

                async def set_massage(
                    controller: BedController, value: float, *, zone: int = n, maximum: int = limit
                ) -> None:
                    target = require_controller(controller, RichmatAppController)
                    if target.version != 1 or not 0 <= value <= maximum:
                        raise ValueError("Unavailable massage intensity")
                    target._massage_values[zone] = int(value)
                    await target.write_command(codec.packed_massage(*target._massage_values))
                    target._publish()

                rows.append(
                    ControllerNumberSpec(
                        f"richmat_app_massage_{n}",
                        "richmat_app_intensity",
                        MASSAGE_KEYS[n],
                        0,
                        limit,
                        1,
                        set_massage,
                    )
                )
        return tuple(rows)

    def _resolved_request(self, request: Request) -> Request:
        if request.operation != "demo" or request.steps:
            return request
        raw = self.local.get("demo")
        if not isinstance(raw, list):
            raise ValueError("No saved demo steps")
        steps = []
        for row in raw:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("action"), str)
                or type(row.get("sustain")) is not bool
                or type(row.get("seconds")) is not int
                or type(row.get("delay")) is not int
            ):
                raise ValueError("Invalid saved demo step")
            steps.append(DemoStep(row["action"], row["sustain"], row["seconds"], row["delay"]))
        return replace(request, steps=tuple(steps))

    def validate_request(self, request: Request) -> None:
        from .actions import validate

        validate(self, self._resolved_request(request))

    async def execute_request(self, request: Request) -> None:
        from .actions import execute

        request = self._resolved_request(request)
        self.validate_request(request)
        await execute(self, request)


async def build_controller(ctx: BuildContext) -> RichmatAppController:
    return RichmatAppController(ctx.coordinator, product=ctx.variant or "")
