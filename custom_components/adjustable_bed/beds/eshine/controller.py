"""Explicit Eshine E6000 profile (com.richmat.eshinesleep 1.0.1, row106), over the Richmat codec."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Final, Literal

from ...card import CARD_MASSAGE, CARD_UTILITY
from ...codec import richmat as codec
from ...controller_state import StateKey
from ...profiles.richmat import ESHINE, Button, RichmatProfile
from ..base import BedController, ProfileExecution
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
)
from .protocol import NotificationStream, Value

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

REFRESH_MS: Final = 100
CODES: Final[Mapping[Button, int]] = ESHINE.codes or {}
HELD: Final[dict[str, int]] = {
    button: code for button, code in CODES.items() if button.endswith(("_up", "_down"))
}
MOTORS: Final[tuple[tuple[str, Button, Button], ...]] = (
    ("head", "head_up", "head_down"),
    ("feet", "feet_up", "feet_down"),
    ("lumbar", "lumbar_up", "lumbar_down"),
    ("pillow", "pillow_up", "pillow_down"),
)
# Setup sends the ExitLimit function selector once, with code 0.
EXIT_LIMIT: Final = "deviceFunctionItemExitLimit"
TRANSPORTS: Final = {
    codec.TRANSPORTS[key].service_uuid: codec.TRANSPORTS[key] for key in ESHINE.transports
}


def _group_key(group: str) -> StateKey[str | None]:
    return StateKey[str | None](f"eshine_{group}")


def _group_data_key(group: str) -> StateKey[dict[str, object] | None]:
    return StateKey[dict[str, object] | None](f"eshine_{group}_data")


# Read-only observations. Neither capability replies nor generic motor numbers
# change the fixed E6000 layout or become physical position feedback.
STATE_GROUPS: Final = {
    "capabilities": (
        "clock_capability",
        "light_capability",
        "aromatherapy_capability",
        "music_capability",
        "detection_capability",
        "snore_capability",
        "protocol_version",
    ),
    "motors": ("motor_angle", "motor_height"),
    "massage": (
        "massage_state",
        "massage_head_strength",
        "massage_foot_strength",
        "massage_mode",
        "massage_frequency",
        "massage_on",
    ),
    "light": ("white_led",),
    "rgb": ("rgb_color", "rgb_timer", "rgb_motion", "rgb_on"),
    "alarm": ("alarm_add_success", "alarm_cancel_success", "alarm_list", "alarm_report"),
    "snore": (
        "anti_snore",
        "off_bed",
        "sleep_adv_name",
        "snore_stop_music",
        "anti_snore_count",
        "anti_snore_time",
    ),
    "lock": ("box_lock", "box_unlock"),
    "music": (
        "music_usb",
        "music_play",
        "music_shake",
        "music_ble",
        "music_volume",
        "music_shake_gear",
    ),
    "mode": ("bed_mode", "press_mode", "standard_split", "same_split"),
    "checks": ("detection_status", *(f"component_check_{i}" for i in range(1, 7))),
}
# Entity key -> (label, the profile button it sends).
EXTRA_BUTTONS: Final[dict[str, tuple[str, Button]]] = {
    "save_zero_g": ("Save Zero Gravity", "save_zero_g"),
    "save_anti_snore": ("Save Anti-Snore", "save_anti_snore"),
    "massage_head_strength": ("Head massage strength", "massage_head"),
    "massage_foot_strength": ("Foot massage strength", "massage_foot"),
    "massage_10_minutes": ("Massage 10 minutes", "massage_timer_10"),
    "massage_20_minutes": ("Massage 20 minutes", "massage_timer_20"),
    "massage_30_minutes": ("Massage 30 minutes", "massage_timer_30"),
}
type Action = Button | Literal["stop"]


def _action(action: Action) -> MotorCommandCallable:
    async def invoke(controller: BedController) -> None:
        target = controller
        if not isinstance(target, EshineController):
            raise TypeError("This action requires the Eshine app profile")
        await target.execute_action(action)

    return invoke


class EshineController(ProfileExecution[RichmatProfile], BedController):
    """The app's fixed controls, with serialized writes and guaranteed release."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self.profile = ESHINE
        self._write_char: BleakGATTCharacteristic | None = None
        self._notify_char: BleakGATTCharacteristic | None = None
        self._compact = False
        self._notifying = False
        self._stream = NotificationStream()
        self._observed: dict[str, dict[str, Value]] = {}

    @property
    def control_characteristic_uuid(self) -> str:
        return self._write_char.uuid if self._write_char else codec.TRANSPORTS["w1"].write_uuid

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "eshine_product": "E6000",
            "eshine_compact": self._compact,
            "eshine_write_uuid": self._write_char.uuid if self._write_char else None,
            "eshine_notify_uuid": self._notify_char.uuid if self._notify_char else None,
        }

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key, key, _action(up), _action(down), _action("stop"), scheduler_resource="*"
            )
            for key, up, down in MOTORS
        )

    def motor_pulse_settings(self) -> tuple[int, int]:
        # A renewable hold (#483) refreshes until its lease ends.
        count = self.leased_hold_refreshes(REFRESH_MS) or self._coordinator.motor_pulse_count
        return count, REFRESH_MS

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(HELD)

    @property
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def has_pillow_support(self) -> bool:
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return False

    @property
    def memory_slot_count(self) -> int:
        return 0

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_light_toggle_control(self) -> bool:
        return True

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            ControllerButtonSpec(
                f"eshine_{key}",
                label,
                _action(button),
                translation_key=f"eshine_{key}",
                icon="mdi:content-save" if key.startswith("save_") else "mdi:vibrate",
                card=CARD_MASSAGE if key.startswith("massage_") else CARD_UTILITY,
            )
            for key, (label, button) in EXTRA_BUTTONS.items()
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(
                f"eshine_{group}",
                f"eshine_{group}",
                _group_key(group),
                "mdi:bluetooth",
                attribute_keys=(_group_data_key(group),),
            )
            for group in STATE_GROUPS
        )

    async def async_discover_capabilities(self) -> None:
        client = self.client
        self._write_char = self._notify_char = None
        self._notifying = False
        self._stream = NotificationStream()
        if client is None:
            raise ConnectionError("Eshine is not connected")
        candidates = []
        for service in client.services or ():
            transport = TRANSPORTS.get(service.uuid.lower())
            if transport is None:
                continue
            write = next(
                (
                    c
                    for c in service.characteristics
                    if c.uuid.lower() == transport.write_uuid and "write" in c.properties
                ),
                None,
            )
            notify = next((c for c in service.characteristics if "notify" in c.properties), None)
            if write is not None and notify is not None:
                candidates.append((transport, write, notify))
        if len(candidates) != 1:
            raise ValueError("Eshine requires exactly one complete supported write/notify endpoint")
        transport, self._write_char, self._notify_char = candidates[0]
        self._compact = transport.single
        self._observed.clear()
        self.forward_controller_state_updates(
            *(
                update
                for group in STATE_GROUPS
                for update in (_group_key(group)(None), _group_data_key(group)(None))
            )
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = REFRESH_MS,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        if self._write_char is None:
            raise ConnectionError("Eshine write endpoint is not resolved")
        await self._write_gatt_with_retry(
            self._write_char.uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response="write-without-response" not in self._write_char.properties,
            characteristic=self._write_char,
            wall_clock_pacing=True,
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        client = self.client
        if client is None or self._notify_char is None:
            raise ConnectionError("Eshine notification endpoint is not resolved")
        if self._notifying:
            return
        async with self._ble_lock:
            await client.start_notify(self._notify_char, self._handle_notification)
        self._notifying = True
        # Setup is the sole reachable non-user write. Never send enum-only queries.
        await self.write_command(
            codec.function(0, action=EXIT_LIMIT, single=self._compact),
            cancel_event=asyncio.Event(),
        )

    async def stop_notify(self) -> None:
        client = self.client
        try:
            if (
                self._notifying
                and client is not None
                and client.is_connected
                and self._notify_char is not None
            ):
                async with self._ble_lock:
                    await client.stop_notify(self._notify_char)
        finally:
            self._notifying = False
            self._notify_callback = None
            self._stream = NotificationStream()

    def _handle_notification(self, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        self.forward_raw_notification(sender.uuid, bytes(data))
        for event, value in self._stream.feed(bytes(data)):
            group = next(group for group, fields in STATE_GROUPS.items() if event in fields)
            observed = self._observed.setdefault(group, {})
            # Keep each numbered motor's observation, without assigning physical axes.
            if event == "motor_angle" and isinstance(value, dict):
                observed[f"motor_{value['no']}"] = value
            elif event == "motor_height" and isinstance(value, dict):
                observed[f"motor_type_{value['type']}"] = value
            else:
                observed[event] = value
            self.forward_controller_state_updates(
                _group_key(group)(event), _group_data_key(group)(dict(observed))
            )

    def _frame(self, code: int) -> bytes:
        """The bare code on a ``single`` transport, else ``6E 01 00 code sum8``."""
        return codec.function(code, single=self._compact)

    async def execute_action(self, action: Action) -> None:
        if action == "stop":
            await self._send_stop()
        elif action in HELD:
            await self._move_with_stop(self._frame(CODES[action]))
        else:
            await self.write_command(self._frame(CODES[action]))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError("Unsupported Eshine held control")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 0 < duration_ms <= 60000
        ):
            raise ValueError("Duration must be an integer from 1 to 60000 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        deadline = asyncio.timeout(duration_ms / 1000)
        write_timeout = False
        try:
            try:
                async with deadline:
                    try:
                        await self.write_command(
                            self._frame(HELD[control]),
                            repeat_count=self.timed_move_repeat_count(duration_ms, REFRESH_MS),
                            repeat_delay_ms=REFRESH_MS,
                        )
                    except TimeoutError:
                        write_timeout = True
                        raise
            except TimeoutError:
                if write_timeout or not deadline.expired():
                    raise
        finally:
            await self._send_stop()

    async def _send_stop(self) -> None:
        await self.write_command(self._frame(self.profile.stop), cancel_event=asyncio.Event())

    async def stop_all(self) -> None:
        await self._send_stop()

    async def move_head_up(self) -> None:
        await self.execute_action("head_up")

    async def move_head_down(self) -> None:
        await self.execute_action("head_down")

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.execute_action("feet_up")

    async def move_feet_down(self) -> None:
        await self.execute_action("feet_down")

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def move_lumbar_up(self) -> None:
        await self.execute_action("lumbar_up")

    async def move_lumbar_down(self) -> None:
        await self.execute_action("lumbar_down")

    async def move_lumbar_stop(self) -> None:
        await self.stop_all()

    async def move_pillow_up(self) -> None:
        await self.execute_action("pillow_up")

    async def move_pillow_down(self) -> None:
        await self.execute_action("pillow_down")

    async def move_pillow_stop(self) -> None:
        await self.stop_all()

    async def preset_flat(self) -> None:
        await self.execute_action("flat")

    async def preset_zero_g(self) -> None:
        await self.execute_action("zero_g")

    async def preset_anti_snore(self) -> None:
        await self.execute_action("anti_snore")

    async def preset_memory(self, memory_num: int) -> None:
        raise NotImplementedError("Eshine has named presets, not numbered memories")

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError("Eshine saves named presets with dedicated buttons")

    async def lights_toggle(self) -> None:
        await self.execute_action("light_toggle")

    async def massage_off(self) -> None:
        await self.execute_action("massage_off")

    async def massage_mode_step(self) -> None:
        await self.execute_action("massage_mode")
