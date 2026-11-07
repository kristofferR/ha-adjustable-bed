"""BedSense 1.8 (com.fenmenbielei.bedsense), separate from Bedsense Bases.

All wire literals and layout gates come from the accepted row108 report.
Memory flags and massage bars reproduce app indicators, not measured positions.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic

from ..codec import ff_frame as codec
from ..const import CONF_BLE_DEVICE_NAME
from ..detection import is_mac_like_name
from ..profiles.ff_frame import BEDSENSE, BedSenseProfile, bedsense_layout
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
    PositionNumberSpec,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

CHARACTERISTIC = codec.CHARACTERISTIC_UUID
LAYOUTS = BEDSENSE.layouts
ACTIONS = BEDSENSE.actions
MEMORIES = ("m1", "m2", "tv", "zero_g", "anti_snore")
__all__ = ["CHARACTERISTIC", "BedSenseController", "BedSenseSession", "bedsense_layout"]


def _action(key: str) -> MotorCommandCallable:
    async def run(controller: BedController) -> None:
        target = controller
        if not isinstance(target, BedSenseController):
            raise TypeError("BedSense action requires its controller")
        await target.execute_action(key)

    return run


@dataclass(slots=True)
class BedSenseSession:
    """App indicators shared by this bed's offline and connected controllers."""

    saved: dict[int, bool] = field(default_factory=lambda: dict.fromkeys(range(1, 6), False))
    state: dict[str, object] = field(default_factory=dict)
    timer: int = 0
    counts: dict[str, int] = field(default_factory=lambda: {"head": 0, "foot": 0, "wave": 0})


class BedSenseController(BedController):
    """One GATT target, with explicit app-labelled controls for nine layouts."""

    profile: BedSenseProfile = BEDSENSE

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        variant: str = "auto",
        device_name: str | None = None,
        session: BedSenseSession | None = None,
    ) -> None:
        super().__init__(coordinator)
        if variant == "auto":
            if is_mac_like_name(device_name):
                stored = coordinator.entry.data.get(CONF_BLE_DEVICE_NAME)
                device_name = stored if isinstance(stored, str) else None
            self.layout = bedsense_layout(device_name)
        elif variant.startswith("bedsense_") and variant[9:] in {str(i) for i in LAYOUTS}:
            self.layout = int(variant[9:])
        else:
            raise ValueError(f"Unknown BedSense layout: {variant}")
        self._subscribed: list[BleakGATTCharacteristic] = []
        self._session = session if session is not None else BedSenseSession()
        self._saved = self._session.saved
        self._n = 0
        self._state = self._session.state
        self._counts = self._session.counts

    @property
    def control_characteristic_uuid(self) -> str:
        return CHARACTERISTIC

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 5

    @property
    def memory_slot_names(self) -> tuple[str, ...]:
        return (
            "M1",
            "M2",
            "TV",
            "Zero Gravity",
            "Flat Bed" if self.layout in (6, 8) else "Anti Snore",
        )

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self.layout not in (6, 8)

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                f"bedsense_{axis}",
                _action(f"{axis}_up"),
                _action(f"{axis}_down"),
                lambda c: c.stop_all(),
                scheduler_resource="*",
            )
            for axis in LAYOUTS[self.layout]
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        # Memory recall/save and Flat/TV/Zero Gravity/Anti Snore have standard entities.
        keys = [
            k
            for k, a in ACTIONS.items()
            if self.layout in a.variants
            and (
                k.startswith(("circulation_", "clear_", "massage_", "light_"))
                or k in ("background_tap", "lumbar", "music", "leg_relax", "rise", "decline")
            )
        ]
        specs = []
        for key in keys:
            category = (
                "massage"
                if key.startswith("massage_")
                else "light"
                if key.startswith("light_")
                else "action"
            )
            specs.append(
                ControllerButtonSpec(
                    f"bedsense_{key}",
                    ACTIONS[key].label,
                    _action(key),
                    scheduler_resource="*",
                    translation_key=f"bedsense_{category}",
                    translation_placeholders={"action": ACTIONS[key].label},
                )
            )
        specs.append(
            ControllerButtonSpec(
                "bedsense_refresh_memory",
                "Refresh memory indicators",
                _action("refresh_memory"),
                scheduler_resource="*",
                translation_key="bedsense_action",
                translation_placeholders={"action": "Refresh memory indicators"},
            )
        )
        return tuple(specs)

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return tuple(
            ControllerStateBinarySensorSpec(
                f"bedsense_m{i}_saved",
                f"bedsense_m{i}_saved",
                f"bedsense_m{i}_saved",
                "mdi:content-save",
                attribute_keys=("bedsense_state_source",),
            )
            for i in range(1, 6)
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(
                f"bedsense_{key}",
                f"bedsense_{key}",
                f"bedsense_{key}",
                "mdi:information-outline",
                attribute_keys=("bedsense_state_source",),
            )
            for key in (
                "head_bar",
                "wave_bar",
                "circulation",
                "massage_timer",
                "light_duration",
                "head_steps",
                "foot_steps",
                "wave_steps",
            )
        )

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        return frozenset(axis for axes in LAYOUTS.values() for axis in axes)

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app_package": "com.fenmenbielei.bedsense",
            "app_version": "1.8 (18)",
            "layout": self.layout,
            "memory_parser_n": self._n,
            "state_semantics": "App indicators; writes are not device acknowledgments",
            **self._state,
        }

    @property
    def persisted_app_state_key(self) -> str:
        return "bedsense"

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {f"m{i}": saved for i, saved in self._saved.items()}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        restored: dict[int, bool] = {}
        for i in self._saved:
            value = state.get(f"m{i}", False)
            if not isinstance(value, bool):
                raise ValueError("BedSense saved flags must be boolean")
            restored[i] = value
        self._saved.update(restored)
        self._publish("restored_app_state")

    def _publish(self, source: str) -> None:
        self._state.update({f"bedsense_m{i}_saved": saved for i, saved in self._saved.items()})
        self._state["bedsense_state_source"] = source
        self.forward_controller_state_updates(dict(self._state))

    def _roles(self) -> list[BleakGATTCharacteristic]:
        if self.client is None or not self.client.is_connected:
            raise ConnectionError("BedSense is disconnected")
        roles = [
            c
            for s in self.client.services
            for c in s.characteristics
            if c.uuid.lower() == CHARACTERISTIC
        ]
        if not roles:
            raise ConnectionError("BedSense FFE1 characteristic is missing")
        return roles

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
        *,
        on_write: Callable[[], None] | None = None,
    ) -> None:
        characteristic = self._roles()[-1]

        def publish_write() -> None:
            if on_write is not None:
                on_write()
            self._parse(command, "local_write")

        # Android's default is NO_RESPONSE when that property exists, DEFAULT otherwise.
        await self._write_gatt_with_retry(
            CHARACTERISTIC,
            command,
            cancel_event=cancel_event,
            response="write-without-response" not in characteristic.properties,
            characteristic=characteristic,
            on_write=publish_write,
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        client = self.client
        if client is None:
            raise ConnectionError("BedSense is disconnected")
        roles = self._roles()
        if self._subscribed:
            return
        try:
            for characteristic in roles:
                await client.start_notify(characteristic, self._notification)
                self._subscribed.append(characteristic)
            await asyncio.sleep(self.profile.read_delay_ms / 1000)
            for characteristic in roles:
                async with self._ble_lock:
                    data = await client.read_gatt_char(characteristic)
                self._parse(bytes(data), "read")
            # askState's first write follows setup by query_start_ms.
            await asyncio.sleep((self.profile.query_start_ms - self.profile.read_delay_ms) / 1000)
            await self._query_memory(initial_delay=False)
        except BaseException:
            await self.stop_notify()
            raise

    async def stop_notify(self) -> None:
        roles, self._subscribed = self._subscribed, []
        client = self.client
        try:
            if client is not None and client.is_connected:
                for characteristic in roles:
                    await client.stop_notify(characteristic)
        finally:
            self._notify_callback = None

    def on_disconnect(self) -> None:
        self._subscribed = []
        self._n = 0

    def _notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        self.forward_raw_notification(CHARACTERISTIC, bytes(data))
        self._parse(bytes(data), "notification")

    def _parse(self, data: bytes, source: str) -> None:
        s = data.hex(" ").upper() + " "
        for rule in self.profile.memory_rules:
            if rule.required_n is not None and rule.required_n != self._n:
                continue
            if not (s == rule.pattern if rule.exact else rule.pattern in s):
                continue
            if any(s == v if rule.excluded_exact else v in s for v in rule.excluded):
                continue
            self._saved[rule.slot] = rule.saved
            if rule.next_n is not None:
                self._n = rule.next_n
            break
        else:
            self._n = 10
        # The artifact maps both head and foot patterns to the HEAD bar.
        bars = (
            ("01 00", "head", 0),
            ("01 1E", "head", 20),
            ("01 1F", "head", 40),
            ("01 20", "head", 60),
            ("02 00", "head", 0),
            ("02 21", "head", 20),
            ("02 22", "head", 40),
            ("02 23", "head", 60),
            ("03 24", "wave", 15),
            ("03 25", "wave", 30),
            ("03 26", "wave", 45),
            ("03 27", "wave", 60),
        )
        for pattern, bar, width in bars:
            if pattern in s:
                self._state[f"bedsense_{bar}_bar"] = width
                break
        else:
            if "00 1C" in s:
                self._state.update(bedsense_head_bar=0, bedsense_wave_bar=0)
        # Independent tests in the artifact; a later match takes precedence.
        circulation = (
            ("FF FF FF FF 05 00 00 00 E7 97 4A ", "whole_body"),
            ("FF FF FF FF 05 00 05 00 E4 C7 4A ", "whole_body"),
            ("FF FF FF FF 05 00 05 00 E4 D7 4B ", "hip" if self.layout in (4, 5) else "waist"),
            ("FF FF FF FF 05 00 05 00 E3 86 88 ", "head"),
            ("FF FF FF FF 05 00 05 00 E5 06 8A ", "legs"),
            ("FF FF FF FF 05 00 05 00 E6 46 8B ", "hip" if self.layout in (4, 5) else "waist"),
            ("FF FF FF FF 05 00 05 00 E8 C7 4F ", "back_and_leg"),
        )
        for index, (pattern, value) in enumerate(circulation):
            if pattern in s if index < 3 else pattern == s:
                self._state["bedsense_circulation"] = value
        self._publish(source)

    async def _query_memory(self, *, initial_delay: bool = True) -> None:
        if initial_delay:
            await asyncio.sleep(self.profile.query_start_ms / 1000)
        group = "68" if self.layout in (6, 8) else "7" if self.layout == 7 else "default"
        for index, slot in enumerate((3, 4, 1, 2, 5)):
            if self._coordinator.cancel_command.is_set():
                return
            if index:
                await asyncio.sleep(self.profile.query_spacing_ms / 1000)
            await self.write_command(ACTIONS[f"query_{group}_{slot}"].frame)

    async def execute_action(self, key: str) -> None:
        if key == "refresh_memory":
            await self._query_memory()
            return
        action = ACTIONS.get(key)
        if action is None or self.layout not in action.variants:
            raise ValueError(f"BedSense action unavailable for this layout: {key}")
        if key.endswith(("_up", "_down")) and not key.startswith("massage_"):
            count, delay = self.motor_pulse_settings()
            # This is HA's requested hold duration, NOT a protocol repeat cadence.
            try:
                await self.write_command(action.frame)
                try:
                    # A renewable hold (#483) waits for its lease, within its ceiling.
                    async with asyncio.timeout(self.leased_hold_ms(count * delay) / 1000):
                        await self._coordinator.cancel_command.wait()
                except TimeoutError:
                    pass
            finally:
                task = asyncio.create_task(self.stop_all())
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    await task
                    raise
            return
        if key.startswith("massage_timer_"):
            requested = 0 if key.endswith("cancel") else int(key.rsplit("_", 1)[1])
            selected = 0 if requested == self._session.timer else requested
            frame = ACTIONS[
                f"massage_timer_{selected}" if selected else "massage_timer_cancel"
            ].frame

            def record_timer() -> None:
                self._session.timer = selected
                self._state["bedsense_massage_timer"] = selected

            await self.write_command(frame, on_write=record_timer)
            return

        def record_selection() -> None:
            if key.startswith("light_"):
                self._state["bedsense_light_duration"] = {
                    "light_10_min": "10 min",
                    "light_8_h": "8 h",
                    "light_10_h": "10 h",
                }[key]
            if key.startswith("massage_"):
                _, zone, direction = key.split("_")
                self._counts[zone] = max(
                    0,
                    min(
                        4 if zone == "wave" else 3,
                        self._counts[zone] + (1 if direction == "up" else -1),
                    ),
                )
                self._state[f"bedsense_{zone}_steps"] = self._counts[zone]

        await self.write_command(action.frame, on_write=record_selection)

    async def stop_all(self) -> None:
        await self.write_command(ACTIONS["release"].frame, cancel_event=asyncio.Event())

    def validate_memory_recall(self, memory_num: int) -> None:
        super().validate_memory_recall(memory_num)
        if memory_num in (1, 2) and not self._saved[memory_num]:
            raise ValueError("Save this BedSense memory before recalling it")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        name = "flat" if memory_num == 5 and self.layout in (6, 8) else MEMORIES[memory_num - 1]
        prefix = "recall" if self._saved[memory_num] or name == "flat" else "builtin"
        await self.execute_action(f"{prefix}_{name}")

    async def program_memory(self, memory_num: int) -> None:
        if not 1 <= memory_num <= 5:
            raise ValueError("BedSense has five memory slots")
        name = "flat" if memory_num == 5 and self.layout in (6, 8) else MEMORIES[memory_num - 1]
        await self.execute_action(f"save_{name}")

    async def preset_flat(self) -> None:
        await self.execute_action("recall_flat" if self.layout in (6, 8) else "flat")

    async def preset_tv(self) -> None:
        await self.preset_memory(3)

    async def preset_zero_g(self) -> None:
        await self.preset_memory(4)

    async def preset_anti_snore(self) -> None:
        if not self.supports_preset_anti_snore:
            raise ValueError("This layout has Flat Bed instead of Anti Snore")
        await self.preset_memory(5)

    async def move_back_up(self) -> None:
        await self.execute_action("back_up")

    async def move_back_down(self) -> None:
        await self.execute_action("back_down")

    async def move_head_up(self) -> None:
        await self.execute_action("head_up")

    async def move_head_down(self) -> None:
        await self.execute_action("head_down")

    async def move_legs_up(self) -> None:
        await self.execute_action("legs_up")

    async def move_legs_down(self) -> None:
        await self.execute_action("legs_down")

    async def move_feet_up(self) -> None:
        raise ValueError("BedSense has no separate feet control")

    async def move_feet_down(self) -> None:
        raise ValueError("BedSense has no separate feet control")

    move_back_stop = stop_all
    move_head_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all
