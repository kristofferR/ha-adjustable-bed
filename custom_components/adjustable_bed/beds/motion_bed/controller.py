"""Motion Bed app control, using one explicitly selected physical target."""
from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Coroutine, Mapping
from contextvars import ContextVar
from dataclasses import dataclass, fields, replace
from functools import lru_cache, partial
from hashlib import sha256
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, cast

from bleak.exc import BleakError
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import (
    CARD_CLIMATE,
    CARD_LIGHT_LEVEL,
    CARD_LIGHTING,
    CARD_MASSAGE,
    CARD_UTILITY,
    CardPlacement,
)
from ...command_scheduler import (
    Delivery,
    delivered,
    note_frame_skipped,
    note_frame_written,
    note_write_not_counted,
)
from ...const import (
    CONF_BLE_DEVICE_NAME,
    CONF_MOTION_BED_MOVEMENT,
    CONF_MOTION_BED_PRESET,
    CONF_MOTION_BED_RESTORED,
)
from ...controller_state import StateKey
from ...profiles.ff_frame import MOTION_BED, MotionBedProfile
from ...state_keys import LIGHT_TIMER_OPTION, MASSAGE_TIMER_MINUTES
from ..base import BedController, ProfileExecution, require_controller
from ..builder import BuildContext
from ..catalog_buttons import Kind, catalog_button, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    MotorCommandCallable,
    MotorControlSpec,
    massage_timer_sensor_spec,
)
from ..family_actions import MotionBedModuleActions
from .actions import ACTION_BY_KEY, MOTION_BED_ACTIONS, MotionBedAction
from .models import MotionBedSelection
from .protocol import (
    SOURCE_COMMANDS,
    AirTimer,
    AlarmMode,
    AlarmSound,
    AlarmSwitch,
    build_alarm,
    build_clock,
    build_thermal_clock,
)
from .requests import MotionBedWrite
from .state import (
    MotionBedContext,
    MotionBedFollowup,
    MotionBedState,
    ScalarState,
    parse_motion_bed_notification,
)

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

STOP = MOTION_BED.stop

CHARACTERISTIC = "0000ffe1-0000-1000-8000-00805f9b34fb"

# Hub module that owns each modular screen's controls.
_MODULE_OWNERS: Mapping[str, str] = {
    "DiandongFragment": "motor", "DianDongSetActivity": "motor",
    "QinangFragment": "air", "AnmoSetActivity": "air", "PressSetActivity": "air",
    "LengnuanFragment": "thermal",
}
# Every screen a hub can show, whichever modules it reports.
_HUB_OWNERS: frozenset[str] = frozenset(
    {
        "Setting2Activity", "MainMcuActivity", "ChangeDeviceActivity", "ConnectMcuActivity",
        "DiandongFragment", "DianDongSetActivity", "AlarmActivity",
        "QinangFragment", "AnmoSetActivity", "PressSetActivity",
        "LengnuanFragment", "TimeSettingActivity",
    }
)
# Entity identities follow a control's function, not the app screen hosting it.
_SCREEN_PREFIX = re.compile(
    r"(?:kuaijie_k\w+?fragment|weitiao_w\w+?fragment|setting2activity|\w+?_(?:activity|fragment))_"
)
# Movement pairs are keyed by their app label; split pads add their side.
_COVER_AXES: Mapping[str, str] = {
    "BACK": "back", "HEAD": "head", "LEG": "legs", "LUMBAR": "lumbar", "HIP": "hip",
    "LIFT": "lift", "TILT": "tilt", "BACK LEG": "back_legs",
    "Split Legs Left": "legs", "Split Legs Right": "legs",
}
_SPLIT_SIDE = re.compile(r"_split_\w+?_(left|right)_up$")


def motion_bed_button_key(action: MotionBedAction) -> str:
    """Return the function-derived entity key for a Motion Bed button action."""
    if action.owner == "SleepAdjustActivity":
        # Sleep adjustment keeps its own refresh and release contract.
        return "motion_bed_sleep_adjust_" + action.key.removeprefix("sleep_adjust_activity_").removeprefix("adjust_")
    match = _SCREEN_PREFIX.match(action.key)
    function = action.key[match.end():] if match else action.key
    if _MODULE_OWNERS.get(action.owner) == "air" and not function.startswith("air_"):
        # Air-module programs reuse bed labels (back, lumbar, yoga) for massage.
        function = "air_" + function
    return "motion_bed_" + function


def motion_bed_cover_key(up: MotionBedAction) -> str:
    """Return the entity key for a layout's movement pair, given its up action."""
    axis = _COVER_AXES[up.name.removesuffix(" up")]
    side = _SPLIT_SIDE.search(up.key)
    return f"motion_bed_{side.group(1)}_{axis}" if side else f"motion_bed_{axis}"


# Alarm-sound previews only serve the app's alarm editor; the audio action keeps them.
_NOT_BUTTONS: Final = frozenset(
    {*(f"motion_bed_audio_preview_{index}" for index in range(1, 6)), "motion_bed_audio_stop"}
)

# App buttons that set one value become one control, sending the same action.
# The massage timer select's durations:
_MASSAGE_TIMERS: Final[Mapping[int, str]] = {
    10: "motion_bed_10time",
    20: "motion_bed_20time",
    30: "motion_bed_30time",
}
# The light timer select's options:
_LIGHT_TIMERS: Final[Mapping[str, str]] = {
    "10 min": "motion_bed_tv_10fenzhong",
    "8 hours": "motion_bed_tv_8xiaoshi",
    "10 hours": "motion_bed_tv_10xiaoshi",
}
# The brightness number's levels:
_BRIGHTNESS: Final[Mapping[int, str]] = {
    level: f"motion_bed_brightness_{level}" for level in range(11)
}


@dataclass(frozen=True, slots=True)
class _Switch:
    """An on/off setting the bed reports, sent with its app action(s)."""

    field: str
    on: str
    # None: ``on`` is the app's one toggle, whose frame follows the reported state.
    off: str | None = None
    card: CardPlacement = CARD_UTILITY


# Each switch shows the reported field it is keyed by.
_SWITCHES: Final[tuple[_Switch, ...]] = (
    _Switch("night_light_enabled", "motion_bed_night_light", card=CARD_LIGHTING),
    _Switch("sleep_enabled", "motion_bed_sleepmian"),
    _Switch(
        "motor_light_enabled",
        "motion_bed_light_enabled_on",
        "motion_bed_light_enabled_off",
        CARD_LIGHTING,
    ),
    _Switch(
        "motor_massage_enabled",
        "motion_bed_massage_enabled_on",
        "motion_bed_massage_enabled_off",
        CARD_MASSAGE,
    ),
    _Switch(
        "thermal_timer_enabled",
        "motion_bed_thermal_timer_on",
        "motion_bed_thermal_timer_off",
        CARD_CLIMATE,
    ),
    _Switch("air_adaptive", "motion_bed_air_adaptive_on", "motion_bed_air_adaptive_off", CARD_MASSAGE),
)
_CONTROL_KEYS: Final = frozenset(
    {
        *_MASSAGE_TIMERS.values(),
        *_LIGHT_TIMERS.values(),
        *_BRIGHTNESS.values(),
        *(key for switch in _SWITCHES for key in (switch.on, switch.off) if key),
    }
)

# Entity names for app labels that are unclear, shouted or shared by two buttons.
_BUTTON_NAMES: Mapping[str, str] = {
    "motion_bed_air_back": "Air wave massage",
    "motion_bed_air_fangqi": "Deflate",
    "motion_bed_air_full": "Air combination massage",
    "motion_bed_air_fullgxunhuan": "Full air massage cycle",
    "motion_bed_air_jingbu": "Neck air massage",
    "motion_bed_air_lumbar": "Lumbar air massage",
    "motion_bed_air_massage_stop": "Stop air massage",
    "motion_bed_air_sleepmian": "Air sleep massage",
    "motion_bed_air_yujia": "Air yoga massage",
    "motion_bed_back_down": "Back down",
    "motion_bed_legs_down": "Legs down",
    "motion_bed_back_legsxunhuan": "Back and legs cycle",
    "motion_bed_hipxunhuan": "Hip cycle",
    "motion_bed_legsxunhuan": "Legs cycle",
    "motion_bed_lumbarxunhuan": "Lumbar cycle",
    "motion_bed_upperxunhuan": "Head cycle",
    "motion_bed_calibration_flat_position": "Calibrate sleep sensor flat",
    "motion_bed_calibration_next_position": "Calibrate sleep sensor side",
    "motion_bed_coupled_flat": "Both sides flat",
    "motion_bed_coupled_tv": "Both sides TV",
    "motion_bed_coupled_zero_gravity": "Both sides zero gravity",
    "motion_bed_coupled_memory_left": "Both sides left memory",
    "motion_bed_coupled_memory_right": "Both sides right memory",
    "motion_bed_split_flat": "Split flat",
    "motion_bed_split_flat_left": "Left flat",
    "motion_bed_split_flat_right": "Right flat",
    "motion_bed_split_memory_left": "Left memory",
    "motion_bed_split_memory_right": "Right memory",
    "motion_bed_split_tv_left": "Left TV",
    "motion_bed_split_tv_right": "Right TV",
    "motion_bed_split_zero_gravity_left": "Left zero gravity",
    "motion_bed_split_zero_gravity_right": "Right zero gravity",
    "motion_bed_dingyao": "Lumbar support",
    "motion_bed_flat": "Flat",
    "motion_bed_houqing": "Tilt backward",
    "motion_bed_legsrelax": "Leg relax",
    "motion_bed_massage_lower_decrease": "Decrease leg massage",
    "motion_bed_massage_lower_increase": "Increase leg massage",
    "motion_bed_massage_upper_decrease": "Decrease back massage",
    "motion_bed_massage_upper_increase": "Increase back massage",
    "motion_bed_massage_wave_decrease": "Decrease massage frequency",
    "motion_bed_massage_wave_increase": "Increase massage frequency",
    "motion_bed_memory1": "Memory 1",
    "motion_bed_music": "Sleep music",
    "motion_bed_sync": "Toggle sync",
    "motion_bed_sleep_adjust_stop": "Stop sleep adjustment",
    "motion_bed_snore": "Anti-snore",
    "motion_bed_thermal_gear_4": "Climate off",
    "motion_bed_tv": "TV",
    "motion_bed_wholeflat": "All flat",
    "motion_bed_wholeshangsheng": "Rise",
    "motion_bed_wholexiajiang": "Lower",
    "motion_bed_yijiangshengqi": "Rise",
    "motion_bed_yijiangjiangxia": "Lower",
    "motion_bed_yujia": "Yoga",
    "motion_bed_zero_gravity": "Zero pressure",
}


_FIXED_TIMER: Final = re.compile(r"_\d+time$|_tv_\d+")


def motion_bed_button_name(key: str, action: MotionBedAction) -> str:
    """Return the entity name of a Motion Bed button."""
    return _BUTTON_NAMES.get(key, action.name)


def _is_button(action: MotionBedAction) -> bool:
    if action.kind == "held":
        return action.owner in ("DiandongFragment", "SleepAdjustActivity")
    # Programming is offered by the confirmed action service, never a one-tap erase.
    return action.kind not in ("persistent", "query", "program")


@lru_cache(maxsize=32)
def button_actions_for(owners: frozenset[str]) -> Mapping[str, MotionBedAction]:
    """Map each active function key to the one action its button sends.

    Screens shown together can offer the same function with identical frames
    (Sync, audio preview); they share one entity. The module-owned screen wins
    so hub routing and its receiver context apply.
    """
    chosen: dict[str, MotionBedAction] = {}
    active = [action for action in MOTION_BED_ACTIONS if action.owner in owners and _is_button(action)]
    for action in sorted(active, key=lambda action: action.kind == "held"):
        key = motion_bed_button_key(action)
        if key in _NOT_BUTTONS:
            continue
        current = chosen.get(key)
        if current is None or (current.owner not in _MODULE_OWNERS and action.owner in _MODULE_OWNERS):
            chosen[key] = action
    return MappingProxyType(chosen)


async def _set_switch(controller: BedController, on: bool, *, switch: _Switch) -> None:
    await require_controller(controller, MotionBedController).set_motion_bed_switch(switch, on)


async def _set_brightness(controller: BedController, value: float) -> None:
    await require_controller(controller, MotionBedController).set_motion_bed_brightness(int(value))


def _action_callback(key: str) -> MotorCommandCallable:
    async def invoke(controller: BedController) -> None:
        await require_controller(controller, MotionBedController).async_execute_motion_bed_action(
            key
        )
    return invoke


@dataclass(slots=True)
class _HeldSession:
    client: BleakClient
    characteristic: BleakGATTCharacteristic
    address: str
    released: bool = False


ACTIVE_MODULE: Final = StateKey[str | None]("motion_bed_active_module")
AIR_TIMER_MINUTES: Final = StateKey[int | None]("motion_bed_air_timer_minutes")
_AIR_TIMER_MINUTES: Final[Mapping[int, int]] = {
    AirTimer.TEN_MINUTES: 10,
    AirTimer.TWENTY_MINUTES: 20,
    AirTimer.THIRTY_MINUTES: 30,
}


def _field_key(name: str) -> StateKey[ScalarState]:
    return StateKey[ScalarState]("motion_bed_" + name)


# Without a chosen wake action the alarm only rings; the bed does not move.
_ALARM_MODES: Final = {
    "none": AlarmMode.NO_ACTION,
    "zero_g": AlarmMode.ZERO_GRAVITY,
    "memory_1": AlarmMode.MEMORY_1,
}
# Music tracks, offered only on targets that report an audio module.
_AUDIO_SOUNDS: Final = {
    "music_1": AlarmSound.MUSIC_1,
    "music_2": AlarmSound.MUSIC_2,
    "music_3": AlarmSound.MUSIC_3,
    "music_4": AlarmSound.MUSIC_4,
    "music_5": AlarmSound.MUSIC_5,
}


# Reported values worth an entity: (state field, enabled by default, attribute fields).
# Preset-selected flags, raw readbacks, calibration samples and module inventory
# details stay in diagnostics.
_SENSORS: Final[tuple[tuple[str, bool, tuple[str, ...]], ...]] = (
    # Massage levels the bed reports; it takes no direct level.
    ("upper_massage", True, ()),
    ("lower_massage", True, ()),
    ("massage_wave", True, ()),
    # The massage and light timer selects and the brightness number show those,
    # so the bed's raw light timer stays in diagnostics.
    ("audio_volume", False, ()),
    ("audio_track", False, ()),
    ("sleep_timer", False, ()),
    ("fall_timer", False, ()),
    ("air_upper_gear", True, ()),
    ("air_lower_gear", True, ()),
    ("air_timer", True, ()),
    ("thermal_gear", True, ()),
    ("thermal_temperature", True, ()),
    ("thermal_water", True, ()),
    ("fault", True, ("fault_part",)),
    ("day_total", False, ("day_unit", "day_flat", "day_side", "day_rolls", "day_slots")),
    (
        "month_average_sleep",
        False,
        (
            "month_days", "month_maximum_sleep", "month_minimum_sleep", "month_average_rolls",
            "month_maximum_rolls", "month_minimum_rolls", "month_flat", "month_side",
        ),
    ),
)
# Massage state for the dashboard rather than diagnostics.
_MASSAGE_LEVELS: Final = frozenset(
    {"upper_massage", "lower_massage", "massage_wave", "air_upper_gear", "air_lower_gear"}
)
# The switches show the night light, smart sleep, module light and massage and
# adaptive air settings; the climate timer keeps its schedule as attributes.
_BINARY_SENSORS: Final[tuple[tuple[str, bool, tuple[str, ...]], ...]] = (
    ("sync_enabled", False, ()),
    ("thermal_low_water", True, ()),
    (
        "thermal_timer_enabled",
        False,
        ("thermal_timer_hour", "thermal_timer_minute", "thermal_timer_mode", "thermal_timer_gear"),
    ),
    (
        "alarm_enabled",
        True,
        (
            "alarm_hour", "alarm_minute", "alarm_weekdays", "alarm_repeat", "alarm_mode",
            "alarm_massage", "alarm_sound", "alarm_music",
        ),
    ),
    ("sensor_present", False, ("sensor_mac",)),
    ("motor_module_present", False, ()),
    ("air_module_present", False, ()),
    ("thermal_module_present", False, ()),
)


class MotionBedController(ProfileExecution[MotionBedProfile], BedController, MotionBedModuleActions):
    """Expose app controls without inferring motors or thermostat temperatures."""

    profile: MotionBedProfile = MOTION_BED

    def __init__(self, coordinator: AdjustableBedCoordinator, *, selection: MotionBedSelection) -> None:
        super().__init__(coordinator)
        self.selection = selection
        self._state = MotionBedState()
        self._route = selection.route
        self._session_client: BleakClient | None = None
        self._characteristic: BleakGATTCharacteristic | None = None
        self._notifying = False
        self._target_address = coordinator.address
        self._generation = 0
        self._tasks: set[asyncio.Task[None]] = set()
        self._context_expiry: dict[MotionBedContext, float] = {}
        self._diagnostic_rejection: str | None = None
        self._receipts: tuple[str, ...] = ()
        self._operation_generation: ContextVar[int | None] = ContextVar("motion_bed_operation", default=None)
        self._started_modules: set[str] = set()
        self._active_module: str | None = None
        # The massage timer the select shows: the last one the bed reported or
        # the last one set here, whichever is newer. The home screen's timer
        # keys are not always reported back.
        self._reported_massage_timer: int | None = None
        self._shown_massage_timer: int | None = None
        # The screen state a timer key's frame is chosen from, while one is pressed.
        self._selection_state: MotionBedState | None = None
        self._audio_preference = False
        self._held_session: _HeldSession | None = None
        self._module_generation = 0
        self._thermal_task: asyncio.Task[None] | None = None
        self._module_capabilities: dict[str, bool] = {}
        self._remembered_module: str | None = None
        previous = coordinator.capability_controller
        if (isinstance(previous, MotionBedController) and previous.selection == selection
                and previous._target_address == coordinator.address):
            self._module_capabilities = dict(previous._module_capabilities)
            self._remembered_module = previous._remembered_module or previous._active_module

    def _remember_module_capabilities(self) -> None:
        if self._active_module is not None and self._remembered_module is None:
            self._remembered_module = self._active_module
        for module in ("motor", "air", "thermal"):
            present = getattr(self._state, module + "_module_present")
            if isinstance(present, bool):
                self._module_capabilities[module] = present

    def _module_present(self, module: str) -> bool:
        if self._target_address != self._coordinator.address:
            return False
        present = getattr(self._state, module + "_module_present")
        return present if isinstance(present, bool) else self._module_capabilities.get(module, False)

    @property
    def control_characteristic_uuid(self) -> str:
        return CHARACTERISTIC

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def auto_stops_on_idle(self) -> bool:
        return False

    @property
    def supports_motor_control(self) -> bool:
        return self.selection.surface in ("home", "motor", "hub")

    @property
    def supports_preset_flat(self) -> bool:
        return False  # The complete named actions retain app-specific flat semantics.

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
    def persisted_app_state_key(self) -> str:
        """The audio preference belongs to the selected app profile."""
        profile = "|".join(str(getattr(self.selection, field.name)) for field in fields(self.selection))
        return sha256(profile.encode()).hexdigest()[:16]

    @property
    def persisted_app_state(self) -> dict[str, bool]:
        return {"audio_available": self._audio_preference}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        if set(state) - {"audio_available"} or any(type(value) is not bool for value in state.values()):
            raise ValueError("Invalid Motion Bed audio preference")
        self._audio_preference = state.get("audio_available") is True

    @property
    def _has_audio(self) -> bool:
        reported = self._state.audio_available
        return reported if isinstance(reported, bool) else self._audio_preference

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "profile": self.selection.surface,
            "preset_layout": self.selection.preset,
            "movement_layout": self.selection.movement,
            "alternate_identity": self.selection.alternate_identity,
            "audio_excluded": self.selection.audio_excluded,
            "write_policy_origin": "host: prefer write property, otherwise write-without-response",
            "last_notification_rejection": self._diagnostic_rejection,
            "receipts": self._receipts,
            "hardware_verified": False,
            "active_module": self._active_module,
            "remembered_audio_available": self._audio_preference,
            "remembered_module_capabilities": dict(self._module_capabilities),
            "actions": [{"key": action.key, "name": action.name, "kind": action.kind}
                        for action in self.actions],
            # Nightly sleep reports stay out of files users post publicly.
            **{
                key: value
                for key, value in self._state.to_updates().items()
                if key != "fall_timer" and not key.startswith(("day_", "app_day_", "month_"))
            },
        }

    @property
    def retained_entity_keys(self) -> frozenset[tuple[str, str]]:
        # A hub reports its modules after connecting; keep each module's controls.
        if self.selection.surface != "hub":
            return frozenset()
        actions = button_actions_for(_HUB_OWNERS)
        return frozenset(
            {
                *(("button", key) for key in actions if key not in _CONTROL_KEYS),
                *(
                    ("switch", f"controller_switch_motion_bed_{switch.field}")
                    for switch in _SWITCHES
                    if switch.on in actions
                ),
                *((("number", "controller_number_motion_bed_brightness"),) if _BRIGHTNESS[0] in actions else ()),
                *((("select", "massage_timer"),) if _MASSAGE_TIMERS[10] in actions else ()),
                *((("select", "light_timer"),) if _LIGHT_TIMERS["10 min"] in actions else ()),
            }
        )

    def _active_owners(self) -> frozenset[str]:
        owners: set[str] = {"Setting2Activity"}
        if self.selection.surface == "home":
            owners.update({
                f"Kuaijie{self.selection.preset}Fragment", f"Weitiao{self.selection.movement}Fragment",
                "HomeActivity", "AnmoFragment", "DengguangFragment", "SmartSleepFragment",
                "AlarmActivity", "SleepAdjustActivity", "SleepDataEntryActivity",
                "SleepDayReportActivity", "SleepFallTimerSelectActivity", "SleepMonthReportActivity",
                "SleepReportMainActivity", "SleepTimerSelectActivity",
            })
        if self.selection.surface == "hub":
            owners.update({"MainMcuActivity", "ChangeDeviceActivity", "ConnectMcuActivity"})
        motor = self.selection.surface == "motor" or (self.selection.surface == "hub" and self._module_present("motor"))
        air = self.selection.surface == "air" or (self.selection.surface == "hub" and self._module_present("air"))
        thermal = self.selection.surface == "thermal" or (self.selection.surface == "hub" and self._module_present("thermal"))
        if motor:
            owners.update({"DiandongFragment", "DianDongSetActivity", "AlarmActivity"})
        if air:
            owners.update({"QinangFragment", "AnmoSetActivity", "PressSetActivity"})
        if thermal:
            owners.update({"LengnuanFragment", "TimeSettingActivity"})
        return frozenset(owners)

    @property
    def actions(self) -> tuple[MotionBedAction, ...]:
        owners = self._active_owners()
        return tuple(action for action in MOTION_BED_ACTIONS if action.owner in owners)

    def controller_button_available(self, key: str) -> bool:
        action = button_actions_for(self._active_owners()).get(key)
        if action is None:
            return False
        try:
            self.validate_motion_bed_action(action.key)
        except ValueError:
            return False
        return True

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return unique_buttons(
            catalog_button(
                key,
                motion_bed_button_name(key, action),
                _action_callback(action.key),
                # The app's Zero Gravity recall, which it labels Zero pressure.
                kind=Kind.PRESET if key == "motion_bed_zero_gravity" else None,
                # One button per brightness step or timer length: off by default.
                enabled="_brightness_" not in key and not _FIXED_TIMER.search(key),
            )
            for key, action in button_actions_for(self._active_owners()).items()
            if key not in _CONTROL_KEYS
        )

    @property
    def has_dynamic_controller_entities(self) -> bool:
        # A hub reports its modules after connecting; their switches, timers
        # and brightness then appear.
        return self.selection.surface == "hub"

    def _actions_present(self, *keys: str) -> bool:
        actions = button_actions_for(self._active_owners())
        return all(key in actions for key in keys)

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        return tuple(
            ControllerSwitchSpec(
                f"motion_bed_{switch.field}",
                f"motion_bed_{switch.field}",
                partial(_set_switch, switch=switch),
                StateKey[bool | None]("motion_bed_" + switch.field),
                card=switch.card,
            )
            for switch in _SWITCHES
            if self._actions_present(switch.on, *((switch.off,) if switch.off else ()))
        )

    async def set_motion_bed_switch(self, switch: _Switch, on: bool) -> None:
        """Send the setting's on or off action, or its toggle when the state differs."""
        if switch.off is not None:
            await self.async_execute_motion_bed_action(self._function_action(switch.on if on else switch.off))
            return
        current = getattr(self._state, switch.field)
        if current is on:
            return
        if current is None and not on:
            # The toggle's frame follows the reported state; unknown would send "on".
            raise ValueError("The bed has not reported this setting yet")
        await self.async_execute_motion_bed_action(self._function_action(switch.on))

    def _function_action(self, key: str) -> str:
        action = button_actions_for(self._active_owners()).get(key)
        if action is None:
            raise ValueError("This control is unavailable in the selected Motion Bed profile")
        return action.key

    @property
    def auto_enable_massage(self) -> bool:
        # The massage screens always show their timer; no setup question needed.
        return self.supports_massage_timer

    @property
    def supports_massage_timer(self) -> bool:
        return self._actions_present(*_MASSAGE_TIMERS.values())

    @property
    def massage_timer_options(self) -> list[int]:
        return list(_MASSAGE_TIMERS) if self.supports_massage_timer else []

    async def set_massage_timer(self, minutes: int) -> None:
        """Each timer key starts its duration, or turns off the timer it shows.

        The app picks a key's frame from the timer its screen shows: the
        reported one, or, on screens the bed never reports to, the one chosen
        last. Pressing the shown timer's key turns it off.
        """
        reported = self._state.massage_timer
        shown = reported if reported is not None else self._shown_massage_timer
        if minutes == 0:
            if shown not in _MASSAGE_TIMERS:
                raise ValueError("No massage timer is running to turn off")
            key = _MASSAGE_TIMERS[shown]
        elif minutes not in _MASSAGE_TIMERS:
            raise ValueError("Choose 10, 20 or 30 minutes")
        elif shown == minutes:
            if self._shown_massage_timer == minutes:
                return
            # Pressing the reported timer's key would turn it off.
            raise ValueError("The bed has not reported the last timer change yet; try again shortly")
        else:
            key = _MASSAGE_TIMERS[minutes]
        self._selection_state = replace(self._state, massage_timer=shown)

        def show(delivery: Delivery) -> None:
            self._selection_state = None
            if delivery is not Delivery.NONE:
                # A timer sent only in part is unknown.
                self._shown_massage_timer = (
                    (minutes or None) if delivery is Delivery.SENT else None
                )
                self._publish()

        with delivered(show):
            await self.async_execute_motion_bed_action(self._function_action(key))

    @property
    def supports_light_timer(self) -> bool:
        return self._actions_present(*_LIGHT_TIMERS.values())

    @property
    def light_timer_options(self) -> list[str]:
        return list(_LIGHT_TIMERS) if self.supports_light_timer else []

    async def set_light_timer(self, timer_option: str) -> None:
        if timer_option not in _LIGHT_TIMERS:
            raise ValueError("Choose 10 minutes, 8 hours or 10 hours")
        # The reported light timer's values have no proven option mapping.
        with self.sent_state(LIGHT_TIMER_OPTION(timer_option)):
            await self.async_execute_motion_bed_action(
                self._function_action(_LIGHT_TIMERS[timer_option])
            )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if not self._actions_present(*_BRIGHTNESS.values()):
            return ()
        return (
            ControllerNumberSpec(
                "motion_bed_brightness",
                "motion_bed_brightness",
                # The status parser publishes the level with the other fields.
                cast(StateKey[int | None], _field_key("brightness")),
                0,
                10,
                1,
                _set_brightness,
                card=CARD_LIGHT_LEVEL,
            ),
        )

    async def set_motion_bed_brightness(self, level: int) -> None:
        if level not in _BRIGHTNESS:
            raise ValueError("Brightness is 0 to 10")
        await self.async_execute_motion_bed_action(self._function_action(_BRIGHTNESS[level]))

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        if self.selection.surface != "home":
            return ()  # Modular upper-arrow source callbacks are dead.
        movement = {action.key: action for action in self.actions if action.kind == "held" and action.owner.startswith("Weitiao")}
        controls: dict[str, MotorControlSpec] = {}
        for key, up in movement.items():
            if key.endswith("_up") and key[:-3] + "_down" in movement:
                entity_key = motion_bed_cover_key(up)
                # W8 repeats its LEG pair on the split and coupled pads.
                controls.setdefault(entity_key, MotorControlSpec(
                    key=entity_key, translation_key=entity_key,
                    open_fn=_action_callback(key), close_fn=_action_callback(key[:-3] + "_down"),
                    stop_fn=lambda controller: controller.stop_all(),
                    scheduler_resource="motion_bed_motor",
                ))
        return tuple(controls.values())

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if self.selection.surface != "hub":
            return ()
        async def select(controller: BedController, value: str) -> None:
            await require_controller(controller, MotionBedController).set_motion_bed_surface(value)
        return (ControllerSelectSpec("motion_bed_active_module", "motion_bed_active_module",
                                     ACTIVE_MODULE, ("motor", "air", "thermal"), select),)

    async def set_motion_bed_surface(self, surface: str) -> None:
        if self.selection.surface != "hub" or surface not in ("motor", "air", "thermal"):
            raise ValueError("Choose a reported Motion Bed hub module")
        if not self._module_present(surface):
            raise ValueError("This hub has not reported the selected module")
        self._remembered_module = surface
        if self._active_module != surface:
            self._select_module(surface)
            self._started_modules.discard(surface)
            self._publish()
            self._spawn(self._start_present_modules)

    def _select_module(self, module: str | None, *, remember: bool = True) -> None:
        self._module_generation += 1
        if self._thermal_task is not None:
            self._thermal_task.cancel()
            self._thermal_task = None
        self._active_module = module
        if module is not None and remember:
            self._remembered_module = module

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            massage_timer_sensor_spec(
                "motion_bed_air_timer", "motion_bed_air_timer", AIR_TIMER_MINUTES
            )
            if name == "air_timer"
            else ControllerStateSensorSpec(
                key="motion_bed_" + name, translation_key="motion_bed_" + name,
                state_key=_field_key(name), icon="mdi:bed-outline",
                attribute_keys=tuple(_field_key(item) for item in attributes),
                entity_registry_enabled_default=enabled,
                entity_category=None if name in _MASSAGE_LEVELS else EntityCategory.DIAGNOSTIC,
            )
            for name, enabled, attributes in _SENSORS
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return tuple(
            ControllerStateBinarySensorSpec(
                key="motion_bed_" + name, translation_key="motion_bed_" + name,
                state_key=_field_key(name),
                icon=None if name == "thermal_low_water" else "mdi:bed-outline",
                attribute_keys=tuple(_field_key(item) for item in attributes),
                entity_registry_enabled_default=enabled,
                entity_category=None if name == "alarm_enabled" else EntityCategory.DIAGNOSTIC,
                # Low water: the climate module needs refilling.
                device_class=(
                    BinarySensorDeviceClass.PROBLEM if name == "thermal_low_water" else None
                ),
            )
            for name, enabled, attributes in _BINARY_SENSORS
        )

    def _publish(self) -> None:
        if self._state.massage_timer != self._reported_massage_timer:
            self._reported_massage_timer = self._shown_massage_timer = self._state.massage_timer
        timer = self._shown_massage_timer
        air_timer = self._state.air_timer
        self.forward_controller_state_updates(
            *(_field_key(name)(value) for name, value in self._state.to_updates().items()),
            ACTIVE_MODULE(self._active_module),
            AIR_TIMER_MINUTES(None if air_timer is None else _AIR_TIMER_MINUTES.get(air_timer)),
            MASSAGE_TIMER_MINUTES(timer if timer in _MASSAGE_TIMERS else None),
        )

    async def async_discover_capabilities(self) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Motion Bed is not connected")
        characteristic: BleakGATTCharacteristic | None = None
        for service in client.services or ():
            for candidate in service.characteristics:
                if candidate.uuid.lower() == CHARACTERISTIC:
                    characteristic = candidate
        if characteristic is None:
            raise ValueError("Motion Bed requires its last FFE1 characteristic")
        if not {"write", "write-without-response"}.intersection(characteristic.properties):
            raise ValueError("The last FFE1 characteristic is not writable")
        if not {"notify", "indicate"}.intersection(characteristic.properties):
            raise ValueError("The last FFE1 characteristic has no notification support")
        binding_changed = (self._session_client is not client or self._target_address != self._coordinator.address
                           or self._characteristic is not characteristic)
        if self._notifying and binding_changed:
            await self.stop_notify()
        if binding_changed:
            self._remember_module_capabilities()
            if self._target_address != self._coordinator.address:
                self._module_capabilities.clear()
                self._remembered_module = None
            self._generation += 1
            if self._held_session is not None:
                await self._release_held_session(self._held_session)
            self._cancel_background()
            self._context_expiry.clear()
            self._started_modules.clear()
            self._active_module = None
            self._state = MotionBedState()
            self._route = self.selection.route
            self._publish()
        self._session_client, self._characteristic = client, characteristic
        self._target_address = self._coordinator.address

    def _current_session(self) -> tuple[BleakClient, BleakGATTCharacteristic]:
        client, characteristic = self._session_client, self._characteristic
        origin = self._operation_generation.get()
        if (origin is not None and origin != self._generation) or (client is None or characteristic is None or self.client is not client
                or not client.is_connected or self._coordinator.address != self._target_address):
            raise ConnectionError("Motion Bed target/session changed")
        return client, characteristic

    async def write_command(self, command: bytes, repeat_count: int = 1,
                            repeat_delay_ms: int = 100,
                            cancel_event: asyncio.Event | None = None) -> None:
        if repeat_count != 1:
            raise ValueError("Motion Bed starts once; held motion does not repeat its start frame")
        cancel = cancel_event or self._coordinator.cancel_command
        async with self._ble_lock:
            client, characteristic = self._current_session()
            if cancel.is_set():
                note_frame_skipped()
                return
            response = "write" in characteristic.properties
            self._coordinator.record_command_trace(
                payload={"hex": command.hex()},
                characteristic_uuid=CHARACTERISTIC, characteristic_handle=characteristic.handle,
                response=response, repeat_count=1, repeat_delay_ms=0,
                command_origin="motion_bed_current_target", controller_class=type(self).__name__,
            )
            await client.write_gatt_char(characteristic, command, response=response)
            note_frame_written(cancel)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._notifying:
            await self.stop_notify()
        await self.async_discover_capabilities()
        self._notify_callback = callback
        client, characteristic = self._current_session()
        generation = self._generation
        address = self._target_address
        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (generation != self._generation or self.client is not client or sender is not characteristic
                    or not client.is_connected or self._coordinator.address != address):
                return
            self._handle_notification(bytes(data))
        async with self._ble_lock:
            self._current_session()
            await client.start_notify(characteristic, receive)
        self._notifying = True
        token = self._operation_generation.set(generation)
        try:
            await self._startup()
        except BaseException:
            await self.stop_notify()
            raise
        finally:
            self._operation_generation.reset(token)

    def on_disconnect(self) -> None:
        self._remember_module_capabilities()
        self._generation += 1
        self._cancel_background()
        self._notifying = False
        self._session_client = None
        self._characteristic = None
        self._notify_callback = None
        self._context_expiry.clear()
        self._started_modules.clear()
        self._active_module = None
        self._state = MotionBedState()
        self._publish()

    def _owned_session_current(self, generation: int) -> bool:
        if generation != self._generation or self._coordinator.controller is not self:
            return False
        try:
            self._current_session()
        except ConnectionError:
            return False
        return True

    async def _release_held_session(self, session: _HeldSession) -> None:
        # A started hold owns its original physical client even after a rebind.
        async with self._ble_lock:
            if session.released:
                return
            session.released = True
            if not session.client.is_connected:
                return
            response = "write" in session.characteristic.properties
            self._coordinator.record_command_trace(
                payload={"hex": STOP.hex(), "original_target_address": session.address},
                characteristic_uuid=CHARACTERISTIC, characteristic_handle=session.characteristic.handle,
                response=response, repeat_count=1, repeat_delay_ms=0,
                command_origin="motion_bed_original_hold_release", controller_class=type(self).__name__,
            )
            await session.client.write_gatt_char(session.characteristic, STOP, response=response)
            note_write_not_counted()

    async def stop_notify(self) -> None:
        self._remember_module_capabilities()
        self._generation += 1
        self._cancel_background()
        try:
            if self._held_session is not None:
                await self._release_held_session(self._held_session)
            client, characteristic = self._session_client, self._characteristic
            if self._notifying and client is not None and client.is_connected and characteristic is not None:
                async with self._ble_lock:
                    await client.stop_notify(characteristic)
        finally:
            self._notifying = False
            self._session_client = None
            self._characteristic = None
            self._context_expiry.clear()
            self._started_modules.clear()
            self._state = MotionBedState()
            self._publish()
            self._notify_callback = None

    def _cancel_background(self) -> None:
        self._module_generation += 1
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        self._thermal_task = None

    def _spawn(self, operation: Callable[[], Coroutine[object, object, None]]) -> asyncio.Task[None]:
        # Coroutine functions below own session/generation checks before each write.
        generation = self._generation
        async def run() -> None:
            if generation != self._generation:
                return
            token = self._operation_generation.set(generation)
            try:
                await operation()
            finally:
                self._operation_generation.reset(token)
        task = self._coordinator.hass.async_create_task(run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _activate(self, context: MotionBedContext, seconds: float = 30) -> None:
        if context in ("day_report", "month_report", "sleep_report"):
            for previous in ("day_report", "month_report", "sleep_report"):
                self._context_expiry.pop(previous, None)
        self._context_expiry[context] = asyncio.get_running_loop().time() + seconds

    def _handle_notification(self, data: bytes) -> None:
        self.forward_raw_notification(CHARACTERISTIC, data)
        now = asyncio.get_running_loop().time()
        contexts = self.selection.route.contexts | frozenset(
            key for key, expiry in self._context_expiry.items() if expiry > now
        )
        if self.selection.surface == "hub":
            if self._state.motor_module_present is True:
                contexts |= frozenset({"motor"})
            if self._state.air_module_present is True:
                contexts |= frozenset({"air"})
            if self._state.thermal_module_present is True:
                contexts |= frozenset({"thermal"})
        route = replace(self._route, contexts=contexts)
        result = parse_motion_bed_notification(data, route, self._state)
        self._diagnostic_rejection = result.rejection
        self._state = result.state
        if "module_deleted" in result.receipts:
            self._module_capabilities.clear()
            self._remembered_module = None
        else:
            self._remember_module_capabilities()
        if isinstance(self._state.audio_available, bool):
            self._audio_preference = self._state.audio_available
        self._receipts = result.receipts
        self._publish()
        if self.selection.surface == "hub":
            self._spawn(self._start_present_modules)
        effects = result.effects
        if ("module_deleted" in result.receipts and "module_change" in contexts
                and not any(effect.action == "module_status_query" for effect in effects)):
            # The delete receiver clears inventory; refresh it using the proven query.
            effects += (MotionBedFollowup("module_status_query"),)
        for effect in effects:
            self._spawn(lambda effect=effect: self._followup(effect))

    async def _followup(self, effect: MotionBedFollowup) -> None:
        generation = self._generation
        def current() -> bool:
            return self._owned_session_current(generation)
        await asyncio.sleep(effect.delay_ms / 1000)
        if not current():
            return
        key = {
            "module_status_query": "main_mcu_activity_module_status",
            "sensor_query": "diandong_fragment_sensor_status",
            "position_query": "sleep_adjust_activity_raw_positions",
        }[effect.action]
        async def execute(controller: BedController) -> None:
            if controller is self and current():
                await self.async_execute_motion_bed_internal_query(key)
        await self._coordinator.async_execute_controller_query(execute, cancel_running=False, skip_disconnect=True,
                                                                     run_if=current)

    async def async_execute_motion_bed_internal_query(self, key: str) -> None:
        action = ACTION_BY_KEY[key]
        if action.kind != "query":
            raise ValueError("Internal Motion Bed callback must be a query")
        self._activate(action.context)
        for command in dict.fromkeys(SOURCE_COMMANDS[source_id] for source_id in action.select(self._state, self.selection.alternate_identity)):
            await self.write_command(command)

    async def _send_sequence(self, commands: tuple[bytes, ...], *, spacing: float = 0) -> None:
        for index, command in enumerate(commands):
            if index and spacing:
                await asyncio.sleep(spacing)
            await self.write_command(command)

    async def _startup(self) -> None:
        surface = self.selection.surface
        if surface == "home":
            await asyncio.sleep(0.5)
            await self.write_command(SOURCE_COMMANDS["HomeActivity:321"])
            await asyncio.sleep(0.5)
            await self.write_command(build_clock(dt_util.now()))
            await asyncio.sleep(0.5)
            await self.write_command(SOURCE_COMMANDS["HomeActivity:311"])
            await asyncio.sleep(0.5)
            await asyncio.sleep(0.2)  # The inherited fragment event delays status requests.
            for action in self.actions:
                if action.kind == "query" and action.owner == f"Kuaijie{self.selection.preset}Fragment":
                    commands = tuple(dict.fromkeys(SOURCE_COMMANDS[source_id] for source_id in action.select(self._state, self.selection.alternate_identity)))
                    await self._send_sequence(commands, spacing=0.5)
        elif surface == "hub":
            await asyncio.sleep(0.3)
            await self.write_command(SOURCE_COMMANDS["MainMcuActivity:182"])
        else:
            await self._module_startup(surface)

    def _module_is_active(self, module: str) -> bool:
        return self.selection.surface == module or (
            self.selection.surface == "hub" and self._active_module == module
            and getattr(self._state, module + "_module_present") is True
        )

    async def _module_startup(self, module: str) -> None:
        module_generation = self._module_generation
        def current() -> bool:
            return module_generation == self._module_generation and self._module_is_active(module)
        await asyncio.sleep(0.2)
        if not current():
            return
        if module == "motor":
            await self.write_command(SOURCE_COMMANDS["DiandongFragment:319"])
            await asyncio.sleep(0.2)
            if not current():
                return
            await self.write_command(build_clock(dt_util.now()))
        elif module == "air":
            await self.write_command(SOURCE_COMMANDS["QinangFragment:133"])
        elif module == "thermal":
            await self.write_command(SOURCE_COMMANDS["LengnuanFragment:183"])
            await asyncio.sleep(0.2)
            if not current():
                return
            await self.write_command(build_thermal_clock(dt_util.now()))
            if not current():
                return
            if self._thermal_task is not None:
                self._thermal_task.cancel()
            self._thermal_task = self._spawn(lambda: self._thermal_poll(module_generation=module_generation))

    async def _start_present_modules(self) -> None:
        present = tuple(module for module in ("motor", "air", "thermal")
                        if getattr(self._state, module + "_module_present") is True)
        self._started_modules.intersection_update(present)
        if self._active_module not in present:
            self._select_module(self._remembered_module if self._remembered_module in present
                                else present[0] if present else None, remember=False)
            self._publish()
        module = self._active_module
        if module is None or module in self._started_modules:
            return
        self._started_modules.add(module)
        generation = self._generation
        module_generation = self._module_generation
        completed = False
        async def prepare(controller: BedController) -> None:
            nonlocal completed
            if (controller is not self or not self._owned_session_current(generation) or self._active_module != module
                    or module_generation != self._module_generation
                    or getattr(self._state, module + "_module_present") is not True):
                if module_generation == self._module_generation:
                    self._started_modules.discard(module)
                return
            await self._module_startup(module)
            completed = module_generation == self._module_generation and self._module_is_active(module)
        try:
            await self._coordinator.async_execute_controller_query(prepare, cancel_running=False, skip_disconnect=True,
                                                                     run_if=lambda: self._owned_session_current(generation) and module_generation == self._module_generation)
        finally:
            if not completed and module_generation == self._module_generation:
                self._started_modules.discard(module)

    async def _thermal_poll(self, *, module_generation: int | None = None) -> None:
        generation = self._generation
        if module_generation is None:
            module_generation = self._module_generation
        def current() -> bool:
            return self._owned_session_current(generation) and module_generation == self._module_generation and self._module_is_active("thermal")
        if not current():
            return
        # Poll spacing exceeds quick handoff. Hold only this current poll's link,
        # leaving the command lane free between its bounded status queries.
        with self._coordinator.hold_command_connection():
            await asyncio.sleep(2)
            while current():
                async def query(controller: BedController) -> None:
                    if controller is not self or not current():
                        return
                    await self.write_command(SOURCE_COMMANDS["LengnuanFragment:58"])
                try:
                    await self._coordinator.async_execute_controller_query(query, cancel_running=False, skip_disconnect=True,
                                                                         run_if=current)
                except asyncio.CancelledError:
                    # A command can preempt this query without cancelling its poll owner.
                    task = asyncio.current_task()
                    if task is None or task.cancelling() or not current():
                        raise
                except (BleakError, ConnectionError, TimeoutError):
                    if not current():
                        return
                if not current():
                    return
                await asyncio.sleep(5)

    def validate_motion_bed_action(self, key: str, *, branch: str = "app",
                                  duration: float = 1, confirmed: bool = False) -> None:
        action = ACTION_BY_KEY.get(key)
        if action is None or action.owner not in self._active_owners():
            raise ValueError("Action is unavailable in the selected Motion Bed profile")
        if not 0 < duration <= 10:
            raise ValueError("Motion Bed bounded movement duration must be 0–10 seconds")
        if action.kind in ("program", "persistent") and not confirmed:
            raise ValueError("Confirm this persistent Motion Bed configuration change")
        selected = action.select(self._state, self.selection.alternate_identity, branch=branch)
        if not self._has_audio and any(
            SOURCE_COMMANDS[source_id].startswith(bytes.fromhex("FFFFFFFF0100130B"))
            or SOURCE_COMMANDS[source_id].startswith(bytes.fromhex("FFFFFFFF0100140B"))
            for source_id in selected
        ):
            raise ValueError("This physical target has not reported audio support")

    async def async_execute_motion_bed_action(self, key: str, *, branch: str = "app",
                                             duration: float = 1, confirmed: bool = False) -> None:
        token = self._operation_generation.set(self._generation)
        try:
            await self._execute_action(key, branch=branch, duration=duration, confirmed=confirmed)
        finally:
            self._operation_generation.reset(token)

    async def _execute_action(self, key: str, *, branch: str, duration: float, confirmed: bool) -> None:
        self.validate_motion_bed_action(key, branch=branch, duration=duration, confirmed=confirmed)
        action = ACTION_BY_KEY[key]
        self._activate(action.context)
        if self.selection.surface == "hub":
            module = _MODULE_OWNERS.get(action.owner)
            if module is not None:
                await self.set_motion_bed_surface(module)
        source_ids = action.select(
            self._selection_state or self._state, self.selection.alternate_identity, branch=branch
        )
        commands = tuple(dict.fromkeys(SOURCE_COMMANDS[source_id] for source_id in source_ids))
        if action.kind == "held":
            client, characteristic = self._current_session()
            session = _HeldSession(client, characteristic, self._target_address)
            self._held_session = session
            try:
                for command in commands:
                    await self.write_command(command)
                await self._hold(duration, sleep_adjust=action.context == "sleep_adjust")
            finally:
                try:
                    await self._release_held_session(session)
                finally:
                    if self._held_session is session:
                        self._held_session = None
                generation = self._operation_generation.get()
                if generation is not None and self._owned_session_current(generation) and action.context == "sleep_adjust":
                    await asyncio.sleep(0.1)
                    await self.write_command(SOURCE_COMMANDS["SleepAdjustActivity:255"], cancel_event=asyncio.Event())
        elif key == "sleep_data_entry_activity_capture_debug":
            for _ in range(10):
                try:
                    await asyncio.wait_for(self._coordinator.cancel_command.wait(), 2)
                    return
                except TimeoutError:
                    for command in commands:
                        await self.write_command(command)
        else:
            await self._send_sequence(commands, spacing=0.5 if action.kind == "query" and action.owner.startswith("Kuaijie") else 0)

    async def _hold(self, duration: float, *, sleep_adjust: bool = False) -> None:
        deadline = asyncio.get_running_loop().time() + duration
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            try:
                await asyncio.wait_for(self._coordinator.cancel_command.wait(), min(remaining, 0.5))
                return
            except TimeoutError:
                if sleep_adjust and asyncio.get_running_loop().time() < deadline:
                    await self.write_command(SOURCE_COMMANDS["SleepAdjustActivity:281"])

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        surface = self.selection.surface
        if not (
            surface in ("home", "motor") or (surface == "hub" and self._module_present("motor"))
        ):
            return None
        return AlarmCapability(
            wake_actions=tuple(_ALARM_MODES),
            weekdays=True,
            massage=True,
            # The first sound is the default, so an alarm rings unless set to none.
            sounds=(*_AUDIO_SOUNDS, "none") if self._has_audio else ("alarm", "none"),
            cancel_running=True,
            resource="*",
        )

    def _alarm_write(self, alarm: AlarmRequest) -> MotionBedWrite:
        home = self.selection.surface == "home"
        switch = None if home else AlarmSwitch.ENABLED if alarm.enabled else AlarmSwitch.DISABLED
        sound = {"none": AlarmSound.NONE, "alarm": AlarmSound.BUZZER, **_AUDIO_SOUNDS}[alarm.sound]
        frame = build_alarm(
            enabled=alarm.enabled,
            hour=alarm.hour,
            minute=alarm.minute,
            weekdays={day + 1: True for day in alarm.weekdays},
            mode=_ALARM_MODES[alarm.wake_action],
            massage=alarm.massage,
            sound=sound,
            switch=switch,
            audio=self._has_audio,
        )
        # Setting an alarm through this action is the explicit confirmation.
        return MotionBedWrite(
            "alarm",
            (frame,),
            "home" if home else "motor_settings",
            confirmed=True,
            persistent=True,
            alarm_audio=self._has_audio,
            alarm_switch=None if switch is None else int(switch),
        )

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_motion_bed_write(self._alarm_write(alarm))

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        await self.async_execute_motion_bed_write(self._alarm_write(alarm))

    def _clock_writes(self) -> tuple[MotionBedWrite, ...]:
        """The clock of this bed's surface; on a hub, the active module's, if it has one."""
        now = dt_util.now()
        writes: list[MotionBedWrite] = []
        for write in (
            MotionBedWrite("clock", (build_clock(now),), "home"),
            MotionBedWrite("clock", (build_thermal_clock(now),), "thermal"),
        ):
            try:
                self.validate_motion_bed_write(write)
            except ValueError:
                continue
            writes.append(write)
        if self.selection.surface == "hub":
            # Switching module runs its startup; set only the module in use. A link
            # that went idle keeps the user's module, which reconnecting restores.
            module = self._active_module or self._remembered_module or ""
            active = {"motor": "home", "thermal": "thermal"}.get(module)
            writes = [write for write in writes if write.context == active]
        return tuple(writes)

    @property
    def supports_clock_sync(self) -> bool:
        # A hub's clocks depend on the modules it reports, checked on the live bed.
        return self.selection.surface != "air"

    def validate_clock_sync(self) -> None:
        if not self._clock_writes():
            raise ValueError("Select the hub's motor or heating module first, then set its clock")

    async def sync_clock(self) -> None:
        # The module in use can change after the call was checked; check it again.
        self.validate_clock_sync()
        for write in self._clock_writes():
            await self.async_execute_motion_bed_write(write)

    def validate_motion_bed_write(self, request: MotionBedWrite) -> None:
        available: set[str] = set()
        surface = self.selection.surface
        if surface == "home":
            available.update({"clock", "alarm", "sleep_angles", "calibration", "sleep_timer", "sleep_report"})
            if self.selection.preset == "K2M":
                available.add("audio")
        if surface == "motor" or (surface == "hub" and self._module_present("motor")):
            available.update({"clock", "alarm", "audio"})
        if surface == "air" or (surface == "hub" and self._module_present("air")):
            available.update({"air_setting", "pressure"})
        if surface == "thermal" or (surface == "hub" and self._module_present("thermal")):
            available.update({"clock", "thermal_schedule"})
        if surface == "hub":
            available.add("module")
        if request.name not in available:
            raise ValueError("Configuration is unavailable in this Motion Bed profile/module")
        if request.name == "clock":
            thermal = request.context == "thermal"
            if thermal:
                if not (surface == "thermal" or (surface == "hub" and self._module_present("thermal"))):
                    raise ValueError("Thermal clock requires the thermal module/profile")
            elif not (surface in ("home", "motor") or (surface == "hub" and self._module_present("motor"))):
                raise ValueError("P1 clock requires a motor/home profile")
        if request.name == "alarm":
            if request.alarm_audio != self._has_audio:
                raise ValueError("Alarm audio must match this physical target's reported audio capability")
            if surface == "home" and request.alarm_switch is not None:
                raise ValueError("Home alarms use the enabled flag, not the modular first-alarm switch")
            if request.alarm_switch == 0 and self._state.alarm_flag is not None:
                raise ValueError("Uninitialized alarm switch is unavailable after alarm state arrives")
        if request.name == "audio" and not self._has_audio:
            raise ValueError("This physical target has not reported audio support")
        if request.persistent and not request.confirmed:
            raise ValueError("Confirm this persistent Motion Bed configuration change")

    async def async_execute_motion_bed_write(self, request: MotionBedWrite) -> None:
        self.validate_motion_bed_write(request)
        token = self._operation_generation.set(self._generation)
        try:
            if self.selection.surface == "hub":
                module = "thermal" if request.context in ("thermal", "thermal_schedule") else "air" if request.name in ("air_setting", "pressure") else "motor" if request.name in ("alarm", "audio", "clock") else None
                if module is not None:
                    await self.set_motion_bed_surface(module)
            self._activate(request.context)
            if request.name == "sleep_report":
                fresh = MotionBedState()
                clean = {item.name: getattr(fresh, item.name) for item in fields(fresh)
                         if item.name.startswith(("day_", "app_day_", "month_"))}
                self._state = replace(self._state, **clean)
                self._publish()
                self._route = replace(self._route, historical_day=request.historical_day,
                                      day_window_offset=request.report_offset)
            if request.initial_delay_ms:
                try:
                    await asyncio.wait_for(self._coordinator.cancel_command.wait(), request.initial_delay_ms / 1000)
                    return
                except TimeoutError:
                    pass
            for frame in request.frames:
                if self._coordinator.cancel_command.is_set():
                    return
                await self.write_command(frame)
        finally:
            self._operation_generation.reset(token)

    async def _send_stop(self) -> None:
        await self.write_command(STOP, cancel_event=asyncio.Event())

    async def stop_all(self) -> None:
        surface = self.selection.surface
        if surface == "hub":
            surface = self._remembered_module or self._active_module
            if surface is None or not self._module_present(surface):
                raise ValueError("Choose a validated present Motion Bed hub module before STOP")
        if surface == "air":
            await self.write_command(SOURCE_COMMANDS["QinangFragment:302"], cancel_event=asyncio.Event())
        elif surface == "thermal":
            from .protocol import build_thermal_gear
            await self.write_command(build_thermal_gear(4), cancel_event=asyncio.Event())
        else:
            await self._send_stop()

    async def _axis(self, axis: str, direction: str) -> None:
        candidates = [action for action in self.actions if action.kind == "held" and action.key.endswith("_" + axis + "_" + direction) and action.owner != "SleepAdjustActivity"]
        if len(candidates) != 1:
            raise ValueError("Use the explicitly named Motion Bed movement control")
        await self.async_execute_motion_bed_action(candidates[0].key)

    async def move_head_up(self) -> None: await self._axis("head", "up")
    async def move_head_down(self) -> None: await self._axis("head", "down")
    async def move_head_stop(self) -> None: await self.stop_all()
    async def move_back_up(self) -> None: await self._axis("back", "up")
    async def move_back_down(self) -> None: await self._axis("back", "down")
    async def move_back_stop(self) -> None: await self.stop_all()
    async def move_legs_up(self) -> None: await self._axis("legs", "up")
    async def move_legs_down(self) -> None: await self._axis("legs", "down")
    async def move_legs_stop(self) -> None: await self.stop_all()
    async def move_feet_up(self) -> None: raise NotImplementedError("No inferred feet axis")
    async def move_feet_down(self) -> None: raise NotImplementedError("No inferred feet axis")
    async def move_feet_stop(self) -> None: await self.stop_all()
    async def preset_flat(self) -> None: raise NotImplementedError("Use the app-labelled flat action")
    async def preset_memory(self, memory_num: int) -> None: raise NotImplementedError("Use the app-labelled memory action")
    async def program_memory(self, memory_num: int) -> None: raise NotImplementedError("Use confirmed Motion Bed programming")


async def build_controller(ctx: BuildContext) -> MotionBedController:
    """Build the controller for the stored or name-selected model."""
    from homeassistant.const import CONF_NAME

    from .models import select_motion_bed

    data = ctx.data
    # The app's identity is the exact advertised name, stored as ble_device_name.
    selection = select_motion_bed(
        data.get(CONF_BLE_DEVICE_NAME, data.get(CONF_NAME, "")),
        restored=data.get(CONF_MOTION_BED_RESTORED, False),
        preset_override=data.get(CONF_MOTION_BED_PRESET),
        movement_override=data.get(CONF_MOTION_BED_MOVEMENT),
    )
    return MotionBedController(ctx.coordinator, selection=selection)
