"""Explicit RMControl 21.3.7 product selection, separate from legacy Richmat.

The accepted product tables supply capabilities, bytes, and gestures. The
packet-construction appendix supplies framing; legacy remote-code heuristics
must never override either input.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Literal, cast

from bleak import BleakClient
from homeassistant.util import dt as dt_util

from ..const import RICHMAT_PROTOCOL_SINGLE, RICHMAT_PROTOCOL_WILINKE, RichmatFeatures
from ..richmat_profiles import RichmatAction, get_product_profile
from ..rmcontrol_protocol import (
    Notification,
    NotificationBuffer,
    RepeatAlarm,
    StateValue,
    build_action,
    build_alarm_time_sync,
    build_anti_snore_config,
    build_anti_snore_switch,
    build_light_color,
    build_light_timer,
    build_repeat_alarm,
    build_single_alarm,
    delete_repeat_alarm,
    query_anti_snore_config,
    query_anti_snore_switch,
    query_repeat_alarms,
    query_sleep_advertisement,
)
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from .richmat import RichmatController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)
_PREFIX = "deviceFunctionItem"
_LOCAL_ACTIONS = frozenset(
    _PREFIX + name
    for name in ("None", "Memory", "MlilyMenu", "PhoneLight", "Clock", "Voice", "Logo")
)
_DESK_PRODUCTS = frozenset({"FWRM", "WFRM"})
_SIDE_VALUES = {"left": 0, "right": 1, "both": 2}
_TRANSPORTS = (
    (
        "0000fee9-0000-1000-8000-00805f9b34fb",
        "d44bc439-abfd-45a2-b575-925416129600",
        "d44bc439-abfd-45a2-b575-925416129601",
    ),
    (
        "0000fee9-0000-1000-8000-00805f9b34bb",
        "d44bc439-abfd-45a2-b575-925416129622",
        "d44bc439-abfd-45a2-b575-925416129611",
    ),
    (
        "0000ffe0-0000-1000-8000-00805f9b34fb",
        "0000ffe2-0000-1000-8000-00805f9b34fb",
        "0000ffe1-0000-1000-8000-00805f9b34fb",
    ),
    (
        "0000fff0-0000-1000-8000-00805f9b34fb",
        "0000fff2-0000-1000-8000-00805f9b34fb",
        "0000fff1-0000-1000-8000-00805f9b34fb",
    ),
    (
        "0000e0ff-3c17-d293-8e48-14fe2e4da212",
        "00000002-3c17-d293-8e48-14fe2e4da212",
        "00000003-3c17-d293-8e48-14fe2e4da212",
    ),
    (
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
    ),
)


async def detect_rmcontrol_transport(client: BleakClient) -> tuple[bool, str, bool]:
    """Require one unambiguous recovered service/write pair and writable role."""
    matches: list[tuple[bool, str, bool]] = []
    for service in client.services:
        for index, (service_uuid, write_uuid, _) in enumerate(_TRANSPORTS):
            if service.uuid.lower() != service_uuid:
                continue
            for characteristic in service.characteristics:
                if characteristic.uuid.lower() != write_uuid:
                    continue
                properties = characteristic.properties
                if "write" not in properties and "write-without-response" not in properties:
                    continue
                matches.append(
                    (
                        index != len(_TRANSPORTS) - 1,
                        write_uuid,
                        "write-without-response" not in properties,
                    )
                )
    if len(matches) != 1:
        raise ValueError("RMControl requires exactly one known writable transport")
    return matches[0]


def _is_transport_action(action: RichmatAction) -> bool:
    return action.action not in _LOCAL_ACTIONS and not action.action.startswith(
        (_PREFIX + "Title", "deviceFunctionSofa")
    )


class RmcontrolController(RichmatController):
    """Artifact-derived opt-in app profile without changing legacy controllers."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        rmcontrol_product: str,
        rmcontrol_side: str = "left",
        is_wilinke: bool = False,
        char_uuid: str | None = None,
        remote_code: str | None = None,
        command_protocol: str | None = None,
        write_with_response: bool = True,
        entry_title: str | None = None,
        configured_name: str | None = None,
        device_name: str | None = None,
    ) -> None:
        profile = get_product_profile(rmcontrol_product)
        if profile is None:
            raise ValueError(f"Unknown RMControl product: {rmcontrol_product}")
        if profile.code in _DESK_PRODUCTS:
            raise ValueError("This RMControl product uses the separate desk protocol")
        if rmcontrol_side not in _SIDE_VALUES:
            raise ValueError(f"Invalid RMControl bed side: {rmcontrol_side}")
        if command_protocol not in (None, RICHMAT_PROTOCOL_SINGLE, RICHMAT_PROTOCOL_WILINKE):
            raise ValueError("RMControl supports only its framed or Nordic app transport")
        self.product_profile = profile
        self._rmcontrol_side = rmcontrol_side
        super().__init__(
            coordinator,
            is_wilinke=is_wilinke,
            char_uuid=char_uuid,
            remote_code=remote_code,
            command_protocol=command_protocol,
            write_with_response=write_with_response,
            entry_title=entry_title,
            configured_name=configured_name,
            device_name=device_name,
        )
        self._features = RichmatFeatures(0)
        self._light_protocol_family = None
        self._last_write_at: float | None = None
        self._reported_capabilities: set[str] = set()
        self._reported_state: dict[str, StateValue] = {}
        self._alarm_records: dict[int, dict[str, StateValue]] = {}
        self._forwarded_state_keys: set[str] = set()
        self._notification_buffer = NotificationBuffer()
        self._notify_uuid: str | None = None

    @property
    def rmcontrol_product(self) -> str:
        return self.product_profile.code

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def _side_value(self) -> int:
        return _SIDE_VALUES[self.command_side or self._rmcontrol_side]

    @property
    def _nordic(self) -> bool:
        return self._command_protocol == RICHMAT_PROTOCOL_SINGLE

    def _build_command(self, command_byte: int) -> bytes:
        return build_action(command_byte, side=self._side_value, nordic=self._nordic)

    def _build_stop_command(self) -> bytes:
        return self._build_command(0x6E)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Preserve the app's 100 ms serialized queue spacing, including release."""
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        for _ in range(repeat_count):
            if cancel is not None and cancel.is_set():
                return
            if self._last_write_at is not None:
                remaining = max(0.0, 0.1 - (loop.time() - self._last_write_at))
                if remaining:
                    await asyncio.sleep(remaining)
            if cancel is not None and cancel.is_set():
                return
            self._last_write_at = loop.time()
            await super().write_command(command, cancel_event=cancel)

    def _lookup(self, name: str) -> RichmatAction | None:
        action = _PREFIX + name
        details_getter = "get _ detailsPageDisplayList"
        # Native entities represent the app's main details-page controls.
        # Alarm/menu-specific gestures do not override that explicit context.
        if self.product_profile.find_actions(action, getter=details_getter):
            return self.product_profile.resolve_action(action, getter=details_getter)
        return self.product_profile.resolve_action(action)

    def _has(self, name: str, *, long_press: bool = False) -> bool:
        action = self._lookup(name)
        if action is None or not _is_transport_action(action):
            return False
        if long_press:
            return action.operate in ("longPress", "shortAndLongPress")
        return action.operate != "longPress"

    async def _execute(self, name: str, *, long_press: bool = False) -> None:
        selected = self._lookup(name)
        if selected is None:
            raise ValueError("Action is absent or ambiguous for this RMControl product")
        await self.async_execute_product_action(
            selected.action,
            getter=selected.getter,
            occurrence=selected.occurrence,
            long_press=long_press,
        )

    async def async_execute_product_action(
        self,
        action: str,
        *,
        long_press: bool = False,
        getter: str | None = None,
        occurrence: int | None = None,
    ) -> None:
        """Execute one proven catalog occurrence inside the coordinator lock.

        Exact getter/occurrence selection is required for conflicting duplicate
        controls. Sustain presses use the artifact's 100 ms cadence and always
        release with a fresh cancellation event, including failed writes.
        """
        if occurrence is not None:
            if getter is None:
                raise ValueError("An occurrence requires its getter context")
            matches = tuple(
                item
                for item in self.product_profile.find_actions(action, getter=getter)
                if item.occurrence == occurrence
            )
            selected = matches[0] if len(matches) == 1 else None
        else:
            selected = self.product_profile.resolve_action(action, getter=getter)
        if selected is None:
            raise ValueError("Action is absent or ambiguous for this RMControl product")
        if not _is_transport_action(selected):
            raise ValueError("This app item is a local UI action or excluded non-bed control")
        if long_press and selected.operate not in ("longPress", "shortAndLongPress"):
            raise ValueError("This product action has no long-press gesture")
        if not long_press and selected.operate == "longPress":
            raise ValueError("This product action requires a long press")
        command = (
            selected.long_opcode
            if long_press
            else selected.nordic_short_opcode
            if self._nordic
            else selected.short_opcode
        )
        packet = build_action(command, side=self._side_value, nordic=self._nordic, action=action)
        if selected.operate != "sustainPress":
            await self.write_command(packet)
            return
        movement_failed = False
        try:
            await self.write_command(
                packet,
                repeat_count=self._coordinator.motor_pulse_count,
                repeat_delay_ms=100,
            )
        except BaseException:
            movement_failed = True
            raise
        finally:
            try:
                await self.write_command(self._build_stop_command(), cancel_event=asyncio.Event())
            except Exception:
                if not movement_failed:
                    raise
                _LOGGER.warning("Failed to release RMControl held action", exc_info=True)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        """Every concrete transport control, retaining ambiguous UI contexts."""
        specs: list[ControllerButtonSpec] = []
        seen: set[tuple[str, str, tuple[int, int, int, str, str]]] = set()
        for action in self.product_profile.actions:
            if not _is_transport_action(action):
                continue
            identity = (action.getter, action.action, action.command_signature)
            if identity in seen:
                continue
            seen.add(identity)
            gestures = (
                (False, True)
                if action.operate == "shortAndLongPress"
                else (True,)
                if action.operate == "longPress"
                else (False,)
            )
            getter_key = action.getter.removeprefix("get _ ")
            action_key = action.action.removeprefix("deviceFunction")
            label = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", action_key.removeprefix("Item"))
            for long_press in gestures:

                async def press(
                    ctrl: BedController,
                    item: RichmatAction = action,
                    long: bool = long_press,
                ) -> None:
                    await cast(RmcontrolController, ctrl).async_execute_product_action(
                        item.action,
                        getter=item.getter,
                        occurrence=item.occurrence,
                        long_press=long,
                    )

                specs.append(
                    ControllerButtonSpec(
                        key=f"rmcontrol_{getter_key}_{action_key}_{action.occurrence}_{'long' if long_press else 'short'}".lower(),
                        name=f"{label}{' (long press)' if long_press else ''} ({getter_key}, {action.occurrence + 1})",
                        press_fn=press,
                        entity_registry_enabled_default=False,
                    )
                )
        return tuple(specs)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        pairs = {
            "head": ("HeadUp", "HeadDown"),
            "feet": ("FootUp", "FootDown"),
            "pillow": ("PillowUp", "PillowDown"),
            "lumbar": ("LumberUp", "LumberDown"),
            "head_feet": ("HeadAndFootUp", "HeadAndFootDown"),
        }
        return tuple(
            spec
            for spec in super().motor_control_specs
            if all(self._has(n) for n in pairs[spec.key])
        )

    @property
    def supports_motor_control(self) -> bool:
        return bool(self.motor_control_specs)

    @property
    def has_pillow_support(self) -> bool:
        return self._has("PillowUp") and self._has("PillowDown")

    @property
    def has_lumbar_support(self) -> bool:
        return self._has("LumberUp") and self._has("LumberDown")

    @property
    def _has_head_feet_support(self) -> bool:
        return self._has("HeadAndFootUp") and self._has("HeadAndFootDown")

    @property
    def supports_preset_flat(self) -> bool:
        return self._has("MotorReset")

    @property
    def supports_preset_zero_g(self) -> bool:
        return self._has("ZeroGravity")

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self._has("AntiSnoring")

    @property
    def supports_preset_tv(self) -> bool:
        return self._has("TVPosition")

    @property
    def supports_preset_lounge(self) -> bool:
        return self._has("LoungePosition")

    @property
    def memory_slot_count(self) -> int:
        # Standard entities assume contiguous numbering. Sparse/ambiguous slots
        # remain available as exact getter-specific product buttons.
        count = 0
        for slot in range(1, 6):
            if not self._has(f"MemoryPosition{slot}"):
                break
            count = slot
        return count

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        return ()

    @property
    def supports_memory_presets(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def supports_memory_programming(self) -> bool:
        return any(
            self.is_memory_slot_programmable(slot) for slot in range(1, self.memory_slot_count + 1)
        )

    def is_memory_slot_programmable(self, memory_num: int) -> bool:
        return 1 <= memory_num <= self.memory_slot_count and self._has(
            f"MemoryPosition{memory_num}", long_press=True
        )

    @property
    def supports_lights(self) -> bool:
        return any(self._has(n) for n in ("BedLight", "BedLightOn", "BedLightClose"))

    @property
    def supports_light_toggle_control(self) -> bool:
        return self._has("BedLight")

    @property
    def supports_discrete_light_control(self) -> bool:
        return self._has("BedLightOn") and self._has("BedLightClose")

    @property
    def supports_explicit_light_on_control(self) -> bool:
        return self._has("BedLightOn")

    @property
    def supports_synchro(self) -> bool:
        return self._has("SyncOn") and self._has("SyncOff")

    @property
    def supports_massage(self) -> bool:
        return any(
            a.action.startswith(_PREFIX + "Massage") and _is_transport_action(a)
            for a in self.product_profile.actions
        )

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_toggle_control(self) -> bool:
        return self._has("MassageSwitch")

    @property
    def supports_massage_off_control(self) -> bool:
        return self._has("MassageModeAllOff")

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return self._has("MassageHeadInstensityStrengthen")

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        return self._has("MassageFootInstensityStrengthen")

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return self._has("MassageModeChange")

    async def move_head_up(self) -> None:
        await self._execute("HeadUp")

    async def move_head_down(self) -> None:
        await self._execute("HeadDown")

    async def move_feet_up(self) -> None:
        await self._execute("FootUp")

    async def move_feet_down(self) -> None:
        await self._execute("FootDown")

    async def move_legs_up(self) -> None:
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        await self.move_feet_down()

    async def move_pillow_up(self) -> None:
        await self._execute("PillowUp")

    async def move_pillow_down(self) -> None:
        await self._execute("PillowDown")

    async def move_lumbar_up(self) -> None:
        await self._execute("LumberUp")

    async def move_lumbar_down(self) -> None:
        await self._execute("LumberDown")

    async def move_head_feet_up(self) -> None:
        await self._execute("HeadAndFootUp")

    async def move_head_feet_down(self) -> None:
        await self._execute("HeadAndFootDown")

    async def preset_flat(self) -> None:
        await self._execute("MotorReset")

    async def preset_zero_g(self) -> None:
        await self._execute("ZeroGravity")

    async def preset_anti_snore(self) -> None:
        await self._execute("AntiSnoring")

    async def preset_tv(self) -> None:
        await self._execute("TVPosition")

    async def preset_lounge(self) -> None:
        await self._execute("LoungePosition")

    async def program_lounge(self) -> None:
        await self._execute("LoungePosition", long_press=True)

    async def preset_memory(self, memory_num: int) -> None:
        if not 1 <= memory_num <= self.memory_slot_count:
            raise ValueError("Unsupported RMControl memory slot")
        await self._execute(f"MemoryPosition{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        if not self.is_memory_slot_programmable(memory_num):
            raise ValueError("This RMControl memory slot is not programmable")
        await self._execute(f"MemoryPosition{memory_num}", long_press=True)

    async def lights_toggle(self) -> None:
        await self._execute("BedLight")

    async def lights_on(self) -> None:
        await self._execute("BedLightOn")

    async def lights_off(self) -> None:
        await self._execute("BedLightClose" if self._has("BedLightClose") else "BedLight")

    async def massage_toggle(self) -> None:
        await self._execute("MassageSwitch")

    async def massage_off(self) -> None:
        await self._execute("MassageModeAllOff")

    async def massage_head_toggle(self) -> None:
        await self._execute("MassageHeadInstensityStrengthen")

    async def massage_foot_toggle(self) -> None:
        await self._execute("MassageFootInstensityStrengthen")

    async def massage_mode_step(self) -> None:
        await self._execute("MassageModeChange")

    async def set_synchro(self, enabled: bool) -> None:
        await self._execute("SyncOn" if enabled else "SyncOff")

    @property
    def supports_rmcontrol_alarm(self) -> bool:
        return self.rmcontrol_product == "PNRN" or (
            "alarm" in self._reported_capabilities and self._has_alarm_catalog
        )

    @property
    def _has_alarm_catalog(self) -> bool:
        return "get _ alarmList" in self.product_profile.getter_names

    @property
    def supports_rmcontrol_single_alarm(self) -> bool:
        return (
            self.supports_rmcontrol_alarm
            and not self.product_profile.settings.is_support_repeat_alarm
        )

    @property
    def supports_rmcontrol_repeat_alarm(self) -> bool:
        return (
            self.supports_rmcontrol_alarm and self.product_profile.settings.is_support_repeat_alarm
        )

    @property
    def supports_rmcontrol_alarm_time_sync(self) -> bool:
        return self._has_alarm_catalog

    @property
    def supports_rmcontrol_anti_snore(self) -> bool:
        return (
            self.product_profile.settings.rmc_sleep_monitoring_type == "deviceSleepMonitoringBle"
            and self.rmcontrol_product in {"HNRN", "HQRN", "HSRN", "HURN", "M7RN", "MJRN"}
            and "sleep_advertisement" in self._reported_capabilities
        )

    @property
    def supports_light_color_control(self) -> bool:
        return (
            "light" in self._reported_capabilities
            and self.product_profile.settings.is_have_light_strip
        )

    @property
    def _light_palette(self) -> tuple[tuple[int, int, int], ...]:
        if (
            self.product_profile.settings.bed_light_display_type
            == "deviceBedLightDisplayCircleEightColorValue"
        ):
            return (
                (255, 255, 0),
                (0, 255, 0),
                (0, 127, 255),
                (0, 0, 255),
                (139, 0, 255),
                (255, 255, 255),
                (255, 0, 0),
                (255, 165, 0),
            )
        return ()

    @property
    def default_light_rgb_color(self) -> tuple[int, int, int] | None:
        value = self._reported_state.get("rmcontrol_rgb_rgb")
        if isinstance(value, tuple) and len(value) == 3:
            return value[0], value[1], value[2]
        return None

    @property
    def supports_light_timer(self) -> bool:
        return self.supports_light_color_control

    @property
    def light_timer_options(self) -> list[str]:
        return (
            ["Always On", *(f"{minute} min" for minute in range(1, 16))]
            if self.supports_light_timer
            else []
        )

    def _accept_notification(self, notification: Notification) -> None:
        """Accept only semantic fields validated by the protocol decoder."""
        if notification.kind == "capability":
            self._reported_capabilities.update(
                name for name, value in notification.values.items() if value is True
            )
        elif notification.kind == "rgb":
            self._reported_capabilities.add("rgb_light")
        elif notification.kind == "light_timer":
            self._reported_capabilities.add("light_timer")
        elif notification.kind == "anti_snore":
            if "sleep_advertisement" in notification.values:
                self._reported_capabilities.add("sleep_advertisement")
        elif notification.kind in ("repeat_alarm", "single_alarm"):
            alarm_id = notification.values.get("alarm_id")
            if isinstance(alarm_id, int) and 1 <= alarm_id <= 7:
                self._alarm_records[alarm_id] = dict(notification.values)
        updates = {
            f"rmcontrol_{notification.kind}_{name}": value
            for name, value in notification.values.items()
        }
        self._reported_state.update(updates)
        if notification.kind == "rgb" and "rgb" in notification.values:
            updates["under_bed_lights_rgb"] = notification.values["rgb"]
        if notification.kind in ("rgb", "white_light") and "on" in notification.values:
            updates["under_bed_lights_on"] = notification.values["on"]
        self._forwarded_state_keys.update(updates)
        self.forward_controller_state_updates(updates)

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        alarm_actions = sorted(
            {
                item.action
                for item in self.product_profile.actions
                if item.getter == "get _ alarmList" and _is_transport_action(item)
            }
        )
        return {
            "rmcontrol_product": self.rmcontrol_product,
            "product_settings": self.product_profile.settings._asdict(),
            "light_rgb_palette": self._light_palette,
            "side": self._rmcontrol_side,
            "transport": "nordic" if self._nordic else "framed",
            "capabilities": sorted(self._reported_capabilities),
            "state": dict(self._reported_state),
            "alarm_actions": alarm_actions,
            # A sequence of last-received observations, not an authoritative
            # current-device alarm list. The parser proves no end-of-list marker.
            "last_received_alarm_records": dict(self._alarm_records),
        }

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        fields = (
            ("protocol_version", "protocol_version", None),
            ("bed_mode", "bed_mode_mode", None),
            ("light_timer", "light_timer_seconds", "s"),
            ("massage_head_strength", "massage_head_strength", None),
            ("massage_foot_strength", "massage_foot_strength", None),
            ("massage_mode", "massage_mode", None),
            ("massage_frequency", "massage_frequency", None),
            ("music_volume", "music_volume", None),
            ("fan_gear", "fan_gear", None),
            ("aroma_timer", "aroma_timer_value", None),
            ("heating_temperature", "heating_temperature", None),
            ("anti_snore_count", "anti_snore_intervention_count", None),
            ("anti_snore_time", "anti_snore_intervention_time", None),
            ("alarm_record", "repeat_alarm_alarm_id", None),
        )
        return tuple(
            ControllerStateSensorSpec(
                key="rmcontrol_" + key,
                translation_key="rmcontrol_" + key,
                state_key="rmcontrol_" + field,
                icon="mdi:information-outline",
                native_unit_of_measurement=unit,
                attribute_keys=tuple(
                    "rmcontrol_repeat_alarm_" + name
                    for name in (
                        "record_flag",
                        "hour",
                        "minute",
                        "command",
                        "repeat_mask",
                    )
                )
                if key == "alarm_record"
                else (),
            )
            for key, field, unit in fields
            if "rmcontrol_" + field in self._reported_state
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        fields = (
            ("anti_snore_enabled", "anti_snore_enabled"),
            ("music_playing", "music_playing"),
            ("lock", "lock_locked"),
            ("rgb_motion", "rgb_motion_enabled"),
        )
        return tuple(
            ControllerStateBinarySensorSpec(
                key="rmcontrol_" + key,
                translation_key="rmcontrol_" + key,
                state_key="rmcontrol_" + field,
                icon="mdi:information-outline",
            )
            for key, field in fields
            if "rmcontrol_" + field in self._reported_state
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Subscribe the exact transport role, then run the recovered menu probes."""
        if self._notify_uuid is not None:
            self._notify_callback = callback
            return
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to RMControl device")
        notify_uuid = next(
            (notify for _, write, notify in _TRANSPORTS if write == self._char_uuid.lower()), None
        )
        if notify_uuid is None:
            raise ValueError("Unknown RMControl notification transport")
        characteristic = client.services.get_characteristic(notify_uuid)
        if characteristic is None or "notify" not in characteristic.properties:
            raise ValueError("RMControl notification characteristic is unavailable")
        self._notification_buffer.clear()
        self._reported_capabilities.clear()
        self._reported_state.clear()
        self._alarm_records.clear()
        if self._forwarded_state_keys:
            previous_keys = self._forwarded_state_keys
            self._forwarded_state_keys = set()
            self.forward_controller_state_updates(dict.fromkeys(previous_keys))
        self._notify_callback = callback

        def receive(_sender: object, data: bytearray) -> None:
            self.forward_raw_notification(notify_uuid, bytes(data))
            for notification in self._notification_buffer.feed(bytes(data)):
                self._accept_notification(notification)

        async with self.ble_lock:
            await client.start_notify(notify_uuid, receive)
        self._notify_uuid = notify_uuid
        try:
            await self.write_command(
                build_action(
                    0, side=self._side_value, nordic=self._nordic, action=_PREFIX + "ExitLimit"
                )
            )
            if self._has_alarm_catalog:
                for frame in build_alarm_time_sync(dt_util.now()):
                    await self.write_command(frame)
            if (
                self.product_profile.settings.rmc_sleep_monitoring_type
                == "deviceSleepMonitoringBle"
            ):
                await self.write_command(query_sleep_advertisement())
            for action in ("CheckClock", "CheckLight"):
                await self.write_command(
                    build_action(
                        1, side=self._side_value, nordic=self._nordic, action=_PREFIX + action
                    )
                )
        except BaseException:
            try:
                await self.stop_notify()
            except Exception:
                _LOGGER.debug("Failed to unsubscribe after RMControl setup failure", exc_info=True)
            raise

    async def stop_notify(self) -> None:
        notify_uuid = self._notify_uuid
        self._notify_uuid = None
        self._notify_callback = None
        self._notification_buffer.clear()
        client = self.client
        if notify_uuid is not None and client is not None and client.is_connected:
            async with self.ble_lock:
                await client.stop_notify(notify_uuid)

    def _require_alarm(self, *, repeat: bool) -> None:
        supported = (
            self.supports_rmcontrol_repeat_alarm if repeat else self.supports_rmcontrol_single_alarm
        )
        if not supported:
            raise NotImplementedError("This product has not advertised this RMControl alarm type")

    def _alarm_command(self, action: str) -> int:
        name = action if action.startswith("deviceFunction") else _PREFIX + action
        matches = tuple(
            item
            for item in self.product_profile.find_actions(name)
            if item.getter == "get _ alarmList" and _is_transport_action(item)
        )
        commands = {item.short_opcode for item in matches}
        if len(commands) != 1:
            raise ValueError("Alarm action is absent or ambiguous in the product's alarm catalog")
        return commands.pop()

    async def rmcontrol_single_alarm(self, minutes: int, action: str | None) -> None:
        self._require_alarm(repeat=False)
        if action is None and minutes != 0:
            raise ValueError("An active alarm requires an action")
        if action is not None and minutes == 0:
            raise ValueError("Use no action when cancelling the alarm")
        frames = build_single_alarm(
            minutes, self._alarm_command(action) if action is not None else 0
        )
        for frame in frames:
            await self.write_command(frame)

    async def rmcontrol_repeat_alarm(
        self,
        alarm_id: int,
        hour: int,
        minute: int,
        weekdays: tuple[int, ...],
        action: str,
    ) -> None:
        self._require_alarm(repeat=True)
        if any(
            isinstance(day, bool) or not isinstance(day, int) or not 0 <= day <= 6
            for day in weekdays
        ):
            raise ValueError("Weekdays must use Monday=0 through Sunday=6")
        mask = sum(1 << (7 - day) for day in set(weekdays))
        alarm = RepeatAlarm(alarm_id, hour, minute, self._alarm_command(action), mask)
        await self.write_command(build_repeat_alarm(alarm))

    async def rmcontrol_delete_alarm(self, alarm_id: int) -> None:
        self._require_alarm(repeat=True)
        frame = delete_repeat_alarm(alarm_id)
        # Invalidate the old observation; this does not assert device deletion.
        self._alarm_records.pop(alarm_id, None)
        await self.write_command(frame)

    async def rmcontrol_query_alarms(self) -> None:
        self._require_alarm(repeat=True)
        self._alarm_records.clear()
        previous_keys = {
            name for name in self._reported_state if name.startswith("rmcontrol_repeat_alarm_")
        }
        for key in previous_keys:
            self._reported_state.pop(key)
        if previous_keys:
            self.forward_controller_state_updates(dict.fromkeys(previous_keys))
        await self.write_command(query_repeat_alarms())

    async def rmcontrol_sync_alarm_time(self, now: datetime) -> None:
        if not self.supports_rmcontrol_alarm_time_sync:
            raise NotImplementedError(
                "This product has no RMControl alarm time synchronization route"
            )
        frames = build_alarm_time_sync(now)
        for frame in frames:
            await self.write_command(frame)

    def _require_anti_snore(self) -> None:
        if not self.supports_rmcontrol_anti_snore:
            raise NotImplementedError("This device has not advertised anti-snore control support")

    async def rmcontrol_anti_snore_switch(self, enabled: bool) -> None:
        self._require_anti_snore()
        await self.write_command(build_anti_snore_switch(enabled))

    async def rmcontrol_anti_snore_config(self, mode: Literal["count", "time"], value: int) -> None:
        self._require_anti_snore()
        await self.write_command(build_anti_snore_config(mode, value))

    async def rmcontrol_query_anti_snore(self) -> None:
        self._require_anti_snore()
        for frame in (query_anti_snore_switch(), query_anti_snore_config()):
            await self.write_command(frame)

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        if not self.supports_light_color_control:
            raise NotImplementedError("This device has not advertised RGB light support")
        if self._light_palette and rgb_color not in self._light_palette:
            raise ValueError(
                "This product supports only the eight RGB colors listed in diagnostics"
            )
        await self.write_command(build_light_color(rgb_color))

    async def set_light_timer(self, timer_option: str) -> None:
        if timer_option not in self.light_timer_options:
            raise ValueError("Unsupported RMControl light timer option")
        seconds = 0 if timer_option == "Always On" else int(timer_option.split()[0]) * 60
        await self.write_command(build_light_timer(seconds))
