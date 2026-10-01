"""Pure, target-scoped Motion Bed notification reducers.

Selected preset flags are the application's parser state, not proof that a motor
reached a position. Report windows retain both decoded data and the app's faulty
current-day assignment. No reducer sends Bluetooth traffic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, replace
from typing import Literal

PresetVariant = Literal["K1", "K2", "K2M", "K3", "K4", "K5", "K8", "K9", "K11", "modular"]
MotionBedContext = Literal[
    "home",
    "preset",
    "massage",
    "light",
    "smart_sleep",
    "motor",
    "air",
    "thermal",
    "motor_settings",
    "air_settings",
    "pressure_settings",
    "sleep_adjust",
    "calibration",
    "calibration_capture",
    "day_report",
    "month_report",
    "sleep_report",
    "network",
    "module_binding",
    "module_settings",
    "module_change",
    "module_startup",
    "fault_settings",
    "thermal_schedule",
]
ScalarState = bool | int | float | str | None


@dataclass(frozen=True, slots=True)
class MotionBedRoute:
    """Active functional receivers for one physical target and explicit profile."""

    preset_variant: PresetVariant = "K1"
    alternate_identity: bool = False
    contexts: frozenset[MotionBedContext] = frozenset(
        {"home", "preset", "massage", "light", "smart_sleep"}
    )
    historical_day: bool = False
    day_window_offset: int = 0

    def __post_init__(self) -> None:
        if self.day_window_offset not in range(5):
            raise ValueError("Day window offset must be 0 through 4")


@dataclass(frozen=True, slots=True)
class MotionBedFollowup:
    """Source callback traffic, scheduled by the current-target controller."""

    action: Literal["module_status_query", "sensor_query", "position_query", "network_status_query"]
    delay_ms: int = 0


@dataclass(frozen=True, slots=True)
class MotionBedState:
    """Reported fields and app-selected flags; None means not yet received."""

    memory_1: bool = False
    memory_2: bool = False
    tv: bool = False
    zero_gravity: bool = False
    snore: bool = False
    left_tv: bool = False
    right_tv: bool = False
    left_zero_gravity: bool = False
    right_zero_gravity: bool = False
    left_memory: bool = False
    right_memory: bool = False
    coupled_left_memory: bool = False
    coupled_right_memory: bool = False
    upper_massage: int | None = None
    lower_massage: int | None = None
    massage_wave: int | None = None
    massage_timer: int | None = None
    massage_timer_raw: int | None = None
    brightness: int | None = None
    light_timer: int | None = None
    sync_visible: bool = False
    sync_enabled: bool | None = None
    audio_available: bool | None = None
    audio_volume: int | None = None
    audio_track: int | None = None
    alarm_flag: int | None = None
    alarm_enabled: bool | None = None
    alarm_hour: str | None = None
    alarm_minute: str | None = None
    alarm_weekday_mask: int | None = None
    alarm_weekdays: tuple[int, ...] = ()
    alarm_repeat: bool = False
    alarm_mode: int | None = None
    alarm_massage: bool | None = None
    alarm_sound: bool | None = None
    alarm_music: int | None = None
    first_modular_alarm: bool = False
    sensor_present: bool | None = None
    sensor_mac: str | None = None
    network_code: int | None = None
    network_status: str | None = None
    provisioning_status: str | None = None
    network_poll_attempts: int = 0
    sleep_enabled: bool | None = None
    night_light_enabled: bool | None = None
    sleep_timer: int | None = None
    fall_timer: int | None = None
    raw_positions: tuple[int, ...] = ()
    stored_flat_positions: tuple[int, ...] = ()
    stored_side_positions: tuple[int, ...] = ()
    calibration_flat: int | None = None
    calibration_side: int | None = None
    calibration_aa: int | None = None
    calibration_kk: int | None = None
    calibration_reset_received: bool = False
    day_operation: int | None = None
    day_segment: int | None = None
    day_flat: float | None = None
    day_side: float | None = None
    day_total: float | None = None
    day_unit: str | None = None
    app_day_unit: str | None = None
    day_rolls: int | None = None
    day_slots: tuple[int, ...] = (0,) * 24
    day_received_segments: tuple[int, ...] = ()
    day_previous_window: tuple[int, ...] = ()
    day_window: tuple[int, ...] = ()
    day_next_window: tuple[int, ...] = ()
    app_day_previous_window: tuple[int, ...] = (0,) * 12
    app_day_next_window: tuple[int, ...] = (0,) * 12
    day_window_start_hour: int | None = None
    month_days: int | None = None
    month_average_sleep: float | None = None
    month_maximum_sleep: float | None = None
    month_minimum_sleep: float | None = None
    month_average_rolls: int | None = None
    month_maximum_rolls: int | None = None
    month_minimum_rolls: int | None = None
    month_flat: float | None = None
    month_side: float | None = None
    motor_module_present: bool | None = None
    air_module_present: bool | None = None
    thermal_module_present: bool | None = None
    module_status_raw: str | None = None
    first_module_type: int | None = None
    app_initial_module_type: int | None = None
    motor_programmed_bits: int | None = None
    motor_sensor_enabled: bool | None = None
    motor_massage_visible: bool | None = None
    motor_light_enabled: bool | None = None
    motor_massage_enabled: bool | None = None
    air_full_custom: bool = False
    air_back_custom: bool = False
    air_adaptive: bool | None = None
    air_setting_mode: int | None = None
    air_upper_raw: int | None = None
    air_lower_raw: int | None = None
    air_upper_gear: int | None = None
    air_lower_gear: int | None = None
    air_timer: int | None = None
    pressure_raw: tuple[int, ...] = ()
    pressure_values: tuple[int, ...] = ()
    pressure_triplet_tags: tuple[int, ...] = ()
    thermal_mode: int | None = None
    thermal_gear: int | None = None
    thermal_slider_index: int | None = None
    thermal_timer_enabled: bool | None = None
    thermal_timer_hour: str | None = None
    thermal_timer_minute: str | None = None
    thermal_timer_mode: int | None = None
    thermal_timer_gear: str | None = None
    thermal_temperature: float | None = None
    thermal_temperature_display: str | None = None
    thermal_water: int | None = None
    thermal_low_water: bool | None = None
    fault_part_raw: str | None = None
    fault_code_raw: str | None = None
    fault_part: str | None = None
    fault: str | None = None

    def to_updates(self) -> dict[str, ScalarState]:
        """Publish scalars and lossless JSON arrays, without guessing units."""
        updates: dict[str, ScalarState] = {}
        for item in fields(self):
            value: object = getattr(self, item.name)
            if value is None or isinstance(value, (bool, int, float, str)):
                updates[item.name] = value
            elif isinstance(value, tuple):
                updates[item.name] = json.dumps(value)
        return updates


@dataclass(frozen=True, slots=True)
class MotionBedParseResult:
    state: MotionBedState
    matched_records: tuple[str, ...] = ()
    effects: tuple[MotionBedFollowup, ...] = ()
    receipts: tuple[str, ...] = ()
    rejection: str | None = None


_PRESET_NAMES = ("memory_1", "memory_2", "tv", "zero_gravity", "snore")
_PRESET_ECHOES = (
    ("A00A2F07", "AF0A2AF7"),
    ("B00BE307", "BF0BE6F7"),
    ("50052B03", "5F052EF3"),
    ("90097B06", "9F097EF6"),
    ("F00FD304", "FF0FD6F4"),
)
_SPLIT_NAMES = ("left_tv", "right_tv", "left_zero_gravity", "right_zero_gravity")
_SPLIT_ECHOES = (
    ("10311B14", "1F311EE4"),
    ("20324F15", "2F324AE5"),
    ("30338315", "3F3386E5"),
    ("4034E717", "4F34E2E7"),
)
_FAULT_PARTS = {
    "6008": "head",
    "4002": "head",
    "6009": "back",
    "4004": "back",
    "600C": "left_hip",
    "600D": "right_hip",
    "6007": "left_leg",
    "600A": "right_leg",
    "60CD": "hip",
    "400D": "hip",
    "607A": "leg",
    "400A": "leg",
}
_FAULTS = {
    "000A": "broken_motor",
    "0014": "motor_overload",
    "001E": "motor_short_circuit",
    "00C8": "distance_sensor_fault",
    "00D2": "same_group_distance_sensor_fault",
    "00DC": "excessive_distance_difference",
    "00E6": "reverse_motor",
    "0064": "distance_out_of_range",
    "006E": "distance_jump",
    "0078": "target_position_deviation",
    "0000": "normal",
}


def k4_short_recall_selected(state: MotionBedState, action: str) -> bool:
    """Preserve the app's short-UP cross-field reads, distinct from long save."""
    if action in ("left_tv", "right_tv", "left_zero_gravity"):
        return state.left_tv
    if action == "right_zero_gravity":
        return state.right_tv
    raise ValueError("Unknown K4 split preset")


def _selected(state: MotionBedState, name: str, value: bool) -> MotionBedState:
    return replace(state, **{name: value})


def _decimal_byte(value: int) -> int | None:
    text = f"{value:02X}"
    return int(text) if text.isdecimal() else None


def _le16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "little")


def parse_motion_bed_k4_text(text: str, current: MotionBedState) -> MotionBedParseResult:
    """Replay the case-sensitive app matcher, including synthetic text vectors.

    Real notifications are formatted with uppercase bytes and single spaces.
    This entry point preserves the source's string semantics without accepting
    nonhex text as Bluetooth traffic or applying absolute-offset decoders to it.
    """
    state = current
    matched = False
    for name, selector in zip(_SPLIT_NAMES, ("31", "32", "33", "34"), strict=True):
        if "FF FF FF FF 03 12 00 " + selector in text:
            state = _selected(state, name, True)
            matched = True
    for name, pair in zip(_SPLIT_NAMES, _SPLIT_ECHOES, strict=True):
        for value, echo in zip((True, False), pair, strict=True):
            literal = bytes.fromhex("FFFFFFFF050000" + echo).hex(" ").upper()
            if literal in text:
                state = _selected(state, name, value)
                matched = True
    records = ("KuaijieK4Fragment:handleReceiveData",) if matched else ()
    return MotionBedParseResult(state, records)


def parse_motion_bed_notification(
    data: bytes,
    route: MotionBedRoute,
    current: MotionBedState,
) -> MotionBedParseResult:
    """Reduce active receivers, rejecting unsafe absolute-offset parser inputs."""
    state = current
    records: list[str] = []
    effects: list[MotionBedFollowup] = []
    receipts: list[str] = []
    contexts = route.contexts
    raw = data.hex().upper()

    def matched(record: str) -> None:
        if record not in records:
            records.append(record)

    def prefix(value: str, minimum: int) -> bool:
        token = bytes.fromhex(value)
        if token in data and not data.startswith(token):
            raise ValueError("nonzero_match_absolute_offset")
        if data.startswith(token):
            if len(data) < minimum:
                raise ValueError("underlength")
            return True
        return False

    def literal(value: str) -> bool:
        return bytes.fromhex(value) in data

    try:
        if "preset" in contexts or "motor" in contexts:
            variant = route.preset_variant
            record = f"Kuaijie{variant}Fragment:handleReceiveData"
            if variant == "modular":
                record = "DiandongFragment:handleReceiveData"
            count = 4 if variant in ("K3", "K8") else 5
            if variant == "K4":
                result = parse_motion_bed_k4_text(data.hex(" ").upper(), state)
                state = result.state
                records.extend(result.matched_records)
            elif variant == "K5":
                for index, selector in enumerate(("31", "32", "33", "34")):
                    if literal("FFFFFFFF031200" + selector):
                        matched(record)
                        if index < 2:
                            state = _selected(state, _SPLIT_NAMES[index], True)
                        else:
                            names = (
                                ("left_memory", "coupled_left_memory")
                                if index == 2
                                else ("right_memory", "coupled_right_memory")
                            )
                            for name in names:
                                state = _selected(state, name, True)
            else:
                alternate = variant in ("K3", "K8", "K9") or (
                    variant in ("K2", "K2M") and route.alternate_identity
                )
                selectors = (
                    ("0A", "0B", "05", "09", "0F")
                    if alternate
                    else ("AA", "AB", "AB" if variant in ("K2", "K2M") else "A5", "A9", "AF")
                )
                header = "FFFFFFFF030600" if alternate else "FFFFFFFF031200"
                if variant != "modular":
                    for name, selector in zip(
                        _PRESET_NAMES[:count], selectors[:count], strict=True
                    ):
                        if literal(header + selector):
                            matched(record)
                            state = _selected(state, name, True)
                for name, pair in zip(_PRESET_NAMES[:count], _PRESET_ECHOES[:count], strict=True):
                    for value, echo in zip((True, False), pair, strict=True):
                        if literal("FFFFFFFF050000" + echo):
                            matched(record)
                            state = _selected(state, name, value)
                if variant == "K2M" and prefix("FFFFFFFF0100150B", 9):
                    matched(record)
                    state = replace(state, audio_volume=data[8] & 15)

        if "massage" in contexts or "motor_settings" in contexts:
            levels = (
                ("upper_massage", "01", ("00D690", "1E5698", "1F9758", "20D748"), 0),
                ("lower_massage", "02", ("00D660", "211678", "225679", "2397B9"), 0),
                ("massage_wave", "03", ("24D7EB", "25162B", "26562A", "2797EA"), 1),
            )
            for name, zone, echoes, start in levels:
                if not literal("FFFFFFFF050000" + zone):
                    continue
                for index, echo in enumerate(echoes):
                    if literal("FFFFFFFF050000" + zone + echo):
                        if "massage" in contexts:
                            matched("AnmoFragment:handleReceiveData")
                        if "motor_settings" in contexts:
                            matched("DianDongSetActivity:handleReceiveData")
                        state = replace(state, **{name: index + start})
                break
        if ("light" in contexts or "motor_settings" in contexts) and prefix("FFFFFFFF050001", 8):
            state = replace(
                state, brightness=data[7], light_timer=0 if data[7] == 0 else state.light_timer
            )
            if "light" in contexts:
                matched("DengguangFragment:handleReceiveData")
            if "motor_settings" in contexts:
                matched("DianDongSetActivity:handleReceiveData")

        alarm_contexts = contexts & {"home", "motor", "motor_settings"}
        if alarm_contexts:
            no_alarm = prefix("FFFFFFFF0100030B", 9)
            if "home" not in contexts and no_alarm and data[8] != 0:
                no_alarm = False
            has_alarm = prefix("FFFFFFFF01000413", 19 if "motor" in contexts else 17)
            if no_alarm or has_alarm:
                for context, owner in (
                    ("home", "HomeActivity"),
                    ("motor", "DiandongFragment"),
                    ("motor_settings", "DianDongSetActivity"),
                ):
                    if context in contexts:
                        matched(owner + ":handleReceiveData")
                        if has_alarm:
                            matched(owner + ":setHasAlarm")
                flag = data[8]
                state = replace(
                    state,
                    audio_available=(
                        flag not in ((0x0F, 0xAF) if has_alarm else (0,))
                        and not (route.alternate_identity and "motor" not in contexts)
                    ),
                    alarm_flag=flag,
                    alarm_enabled=has_alarm and flag in (0x0F, 0x1F),
                )
                if has_alarm:
                    weekdays = tuple(day for day in range(1, 8) if data[12] & (1 << day))
                    state = replace(
                        state,
                        alarm_hour=f"{data[9]:02X}",
                        alarm_minute=f"{data[10]:02X}",
                        alarm_weekday_mask=data[12],
                        alarm_weekdays=weekdays,
                        alarm_repeat=bool(weekdays),
                        alarm_mode=data[14],
                        alarm_massage=data[15] == 1,
                        alarm_sound=data[16] == 1,
                        alarm_music=data[16],
                    )
                else:
                    state = replace(
                        state,
                        alarm_hour=None,
                        alarm_minute=None,
                        alarm_weekday_mask=None,
                        alarm_weekdays=(),
                        alarm_repeat=False,
                        alarm_mode=None,
                        alarm_massage=None,
                        alarm_sound=None,
                        alarm_music=None,
                        first_modular_alarm="motor" in contexts,
                    )
            if "home" in contexts and (
                prefix("FFFFFFFF0100090B", 9) or prefix("FFFFFFFF01000A0B", 9)
            ):
                matched("HomeActivity:handleReceiveData")
                state = replace(state, sync_visible=True, sync_enabled=data[8] == 1)
        if "motor_settings" in contexts:
            if prefix("FFFFFFFF0100130B", 9):
                matched("DianDongSetActivity:handleReceiveData")
                state = replace(state, alarm_music=data[8] & 15)
            if prefix("FFFFFFFF01001C1402", 12):
                matched("DianDongSetActivity:handleReceiveData")
                state = replace(
                    state,
                    brightness=data[10],
                    light_timer=(data[11] if data[11] <= 3 else state.light_timer),
                )
            if prefix("FFFFFFFF01001C1404", 13):
                matched("DianDongSetActivity:handleReceiveData")
                state = replace(
                    state,
                    upper_massage=data[9],
                    lower_massage=data[10],
                    massage_wave=data[11],
                    massage_timer=((data[12] + 1) * 10 if data[12] <= 2 else state.massage_timer),
                    massage_timer_raw=data[12],
                )
            for selector in ("01", "03"):
                if prefix("FFFFFFFF01001C14" + selector, 9):
                    matched("DianDongSetActivity:handleReceiveData")
                    receipts.append("motor_defaults_saved_" + selector)
        if "motor" in contexts:
            if prefix("FFFFFFFF01002A14", 13):
                matched("DiandongFragment:handleReceiveData")
                flags = data[8]
                state = replace(
                    state,
                    tv=bool(flags & 1),
                    zero_gravity=bool(flags & 2),
                    memory_1=bool(flags & 4),
                    memory_2=bool(flags & 8),
                    snore=bool(flags & 16),
                    motor_programmed_bits=flags,
                    motor_sensor_enabled=data[9] == 1,
                    motor_massage_visible=data[10] == 1,
                    motor_light_enabled=data[11] == 1,
                    motor_massage_enabled=data[12] == 1,
                )
                if data[9] == 1:
                    effects.append(MotionBedFollowup("sensor_query", 200))
                else:
                    state = replace(state, sensor_present=False)
            if prefix("FFFFFFFF01000C11", 15):
                matched("DiandongFragment:handleReceiveData")
                state = replace(state, sensor_present=data[8] == 3)
                if data[8] == 3:
                    state = replace(state, sensor_mac=data[9:15].hex().upper())

        module_contexts = contexts & {
            "module_startup",
            "module_binding",
            "module_settings",
            "module_change",
        }
        if module_contexts:
            if prefix("FFFFFFFF01002714", 16):
                for context, owner in (
                    ("module_startup", "MainMcuActivity"),
                    ("module_binding", "ConnectMcuActivity"),
                    ("module_settings", "Setting2Activity"),
                    ("module_change", "ChangeDeviceActivity"),
                ):
                    if context in contexts:
                        matched(owner + ":handleReceiveData")
                motor, air, thermal = data[9] == 10, data[12] == 11, data[15] == 12
                state = replace(
                    state,
                    motor_module_present=motor,
                    air_module_present=air,
                    thermal_module_present=thermal,
                    module_status_raw=raw,
                    first_module_type=10 if motor else 11 if air else 12 if thermal else None,
                    app_initial_module_type=(
                        state.app_initial_module_type
                        if state.app_initial_module_type is not None
                        else 10
                        if motor
                        else 11
                        if air
                        else 12
                        if thermal
                        else None
                    ),
                )
            if prefix("FFFFFFFF01002914", 8) and "module_binding" in contexts:
                matched("ConnectMcuActivity:handleReceiveData")
                receipts.append("module_bound")
                effects.append(MotionBedFollowup("module_status_query"))
            if prefix("FFFFFFFF01002814", 8):
                for context, owner in (
                    ("module_settings", "Setting2Activity"),
                    ("module_change", "ChangeDeviceActivity"),
                ):
                    if context in contexts:
                        matched(owner + ":handleReceiveData")
                receipts.append("module_deleted")
                state = replace(
                    state,
                    motor_module_present=None,
                    air_module_present=None,
                    thermal_module_present=None,
                    module_status_raw=None,
                    first_module_type=None,
                    motor_programmed_bits=None,
                    motor_sensor_enabled=None,
                    motor_massage_visible=None,
                    motor_light_enabled=None,
                    motor_massage_enabled=None,
                )
                if "module_settings" in contexts:
                    effects.append(MotionBedFollowup("module_status_query"))

        if "fault_settings" in contexts and prefix("FFFFFFFF0304", 10):
            matched("SettingActivity:handleReceiveData")
            matched("FaultDebugDialog:setFaultBody")
            part, code = raw[12:16], raw[16:20]
            state = replace(
                state,
                fault_part_raw=part,
                fault_code_raw=code,
                fault_part=_FAULT_PARTS.get(part, ""),
                fault=_FAULTS.get(code, ""),
            )

        if "air" in contexts:
            if prefix("FFFFFFFFFF14020901", 11):
                matched("QinangFragment:handleReceiveData")
                state = replace(
                    state,
                    air_full_custom=state.air_full_custom or data[9] in (1, 3),
                    air_back_custom=state.air_back_custom or data[9] in (2, 3),
                    air_adaptive=True if data[10] == 1 else state.air_adaptive,
                )
            if prefix("FFFFFFFFFF0D030C01", 10):
                matched("QinangFragment:handleReceiveData")
                state = replace(state, air_adaptive=data[9] == 1)
            if prefix("FFFFFFFFFF14030D01", 11):
                matched("QinangFragment:handleReceiveData")
                if data[10] in (3, 18):
                    state = replace(
                        state,
                        **{"air_full_custom" if data[10] == 3 else "air_back_custom": data[9] == 1},
                    )
        if "air_settings" in contexts:
            if prefix("FFFFFFFFFF14020801", 15):
                matched("AnmoSetActivity:handleReceiveData")
                upper, lower = _le16(data, 10), _le16(data, 12)
                state = replace(
                    state,
                    air_upper_raw=upper,
                    air_lower_raw=lower,
                    air_upper_gear=upper // 10
                    if upper in range(10, 81, 10)
                    else state.air_upper_gear,
                    air_lower_gear=lower // 10
                    if lower in range(10, 81, 10)
                    else state.air_lower_gear,
                    air_setting_mode=data[9]
                    if data[9] in (3, 18, 5, 4, 12)
                    else state.air_setting_mode,
                    air_timer=data[14] if data[14] <= 2 else state.air_timer,
                )
            if prefix("FFFFFFFFFF14030E01", 9):
                matched("AnmoSetActivity:handleReceiveData")
                receipts.append("air_settings_saved")
        if "pressure_settings" in contexts:
            if prefix("FFFFFFFFFF2F020401", 47):
                if len(data) != 47:
                    raise ValueError("pressure_reply_requires_exact_47_bytes")
                matched("PressSetActivity:handleReceiveData")
                pressures = tuple(_le16(data, 10 + i * 3) for i in range(12))
                state = replace(
                    state,
                    pressure_raw=pressures,
                    pressure_values=tuple(p // 10 for p in pressures),
                    pressure_triplet_tags=tuple(data[9 + i * 3] for i in range(12)),
                )
            if prefix("FFFFFFFFFF2F030501", 9):
                matched("PressSetActivity:handleReceiveData")
                receipts.append("pressure_settings_saved")

        if "thermal" in contexts:
            full = prefix("FFFFFFFFFE14000001", 20)
            periodic = prefix("FFFFFFFFFE14000101", 17)
            if full or periodic:
                matched("LengnuanFragment:handleReceiveData")
                mode, gear = data[9] & 15, _decimal_byte(data[10])
                if mode in (1, 2) and gear is None:
                    raise ValueError("thermal_gear_not_decimal_digits")
                slider = 4
                if mode == 1 and gear is not None:
                    slider = 4 + gear
                elif mode == 2 and gear is not None:
                    slider = 4 - gear
                elif mode not in (0, 3, 4) and periodic:
                    slider = 0
                whole, fraction = _decimal_byte(data[15]), _decimal_byte(data[16])
                display = (
                    f"{whole}.{fraction}" if whole is not None and fraction is not None else None
                )
                state = replace(
                    state, thermal_mode=mode, thermal_gear=gear, thermal_slider_index=slider
                )
                if display is not None or periodic:
                    state = replace(
                        state,
                        thermal_temperature_display=display,
                        thermal_temperature=float(display) if display is not None else None,
                    )
                if full:
                    water = _decimal_byte(data[17])
                    if water is None:
                        raise ValueError("thermal_water_not_decimal_digits")
                    timer = data[9] >> 4 == 1
                    state = replace(
                        state,
                        thermal_timer_enabled=timer,
                        thermal_water=water,
                        thermal_low_water=water < 20,
                    )
                    if timer:
                        state = replace(
                            state,
                            thermal_timer_hour=f"{data[11]:02X}",
                            thermal_timer_minute=f"{data[12]:02X}",
                            thermal_timer_mode=data[13],
                            thermal_timer_gear=f"{data[14]:02X}",
                        )
            if prefix("FFFFFFFFFE14000701", 9):
                matched("LengnuanFragment:handleReceiveData")
                receipts.append("thermal_clock_received")
        if "thermal_schedule" in contexts and prefix("FFFFFFFFFE14000201", 9):
            matched("TimeSettingActivity:handleReceiveData")
            receipts.append("thermal_schedule_received")

        if contexts & {"home", "smart_sleep", "calibration", "network"}:
            status_contexts = contexts & {"smart_sleep", "calibration", "network"}
            status_minimum = (
                19 if "smart_sleep" in contexts else 15 if "network" in contexts else 12
            )
            if status_contexts and prefix("FFFFFFFF02000A14", status_minimum):
                if "smart_sleep" in contexts:
                    matched("SmartSleepFragment:handleReceiveData")
                    state = replace(
                        state, sleep_enabled=data[16] == 1, night_light_enabled=data[17] == 1
                    )
                if "calibration" in contexts:
                    matched("SleepDataEntryActivity:handleReceiveData")
                    state = replace(state, calibration_flat=data[10], calibration_side=data[11] * 2)
                if "network" in contexts:
                    matched("XinLvDaiActivity:handleReceiveData")
                    code = data[14]
                    statuses = {
                        0: "not_configured",
                        1: "not_connected",
                        10: "unstable",
                        15: "connected",
                    }
                    state = replace(
                        state,
                        network_code=code,
                        network_status=statuses.get(code, state.network_status),
                    )
                    matched("NetworkActivity:handleReceiveData")
                    if code in (0, 1):
                        if state.network_poll_attempts >= 10:
                            state = replace(state, provisioning_status="failed")
                        else:
                            state = replace(
                                state, network_poll_attempts=state.network_poll_attempts + 1
                            )
                            effects.append(MotionBedFollowup("network_status_query", 6000))
                    elif code == 15:
                        state = replace(state, provisioning_status="success")
            if ("home" in contexts or "smart_sleep" in contexts) and prefix("FFFFFFFF02000E0B", 10):
                if "home" in contexts:
                    matched("HomeActivity:handleReceiveData")
                if "smart_sleep" in contexts:
                    matched("SmartSleepFragment:handleReceiveData")
                state = replace(state, sleep_timer=data[8])
        if "network" in contexts and prefix("FFFFFFFF02001913", 10):
            matched("NetworkActivity:handleReceiveData")
            if data[9] != 1:
                if data[9] in (0, 15):
                    state = replace(
                        state, provisioning_status="failed" if data[9] == 0 else "success"
                    )
                effects.append(MotionBedFollowup("network_status_query"))
            elif data[9] == 1 and state.network_poll_attempts < 10:
                state = replace(
                    state,
                    provisioning_status="waiting",
                    network_poll_attempts=state.network_poll_attempts + 1,
                )
                effects.append(MotionBedFollowup("network_status_query", 6000))
            else:
                state = replace(state, provisioning_status="failed")
        if "sleep_adjust" in contexts:
            if prefix("FFFFFFFF02000F0E", 12):
                matched("SleepAdjustActivity:handleReceiveData")
                state = replace(state, raw_positions=tuple(data[8:12]))
            if prefix("FFFFFFFF02001012", 16):
                matched("SleepAdjustActivity:handleReceiveData")
                state = replace(
                    state,
                    stored_flat_positions=tuple(data[8:12]),
                    stored_side_positions=tuple(data[12:16]),
                )
                effects.append(MotionBedFollowup("position_query", 100))
        if "calibration" in contexts or "calibration_capture" in contexts:
            if literal("FFFFFFFF0500008208B666"):
                matched("SleepDataEntryActivity:handleReceiveData")
                state = replace(state, calibration_reset_received=True)
            if prefix("FFFFFFFF0200090D01", 11):
                matched("SleepDataEntryActivity:handleReceiveData")
                state = replace(state, calibration_flat=_le16(data, 9) * 2)
            if prefix("FFFFFFFF0200090D02", 11):
                matched("SleepDataEntryActivity:handleReceiveData")
                state = replace(state, calibration_side=_le16(data, 9))
            if "calibration_capture" in contexts and prefix("FFFFFFFF0200090F03", 13):
                matched("SleepDataEntryActivity:handleReceiveData")
                state = replace(
                    state, calibration_aa=_le16(data, 9), calibration_kk=_le16(data, 11)
                )
        if "sleep_report" in contexts and prefix("FFFFFFFF0200160B", 9):
            matched("SleepReportMainActivity:handleReceiveData")
            state = replace(state, fall_timer=data[8])
        if "month_report" in contexts and prefix("FFFFFFFF0200", 17):
            matched("SleepMonthReportActivity:handleReceiveData")
            state = replace(
                state,
                month_days=data[8],
                month_average_sleep=data[9] / 10,
                month_maximum_sleep=data[10] / 10,
                month_minimum_sleep=data[11] / 10,
                month_average_rolls=data[12],
                month_maximum_rolls=data[13],
                month_minimum_rolls=data[14],
                month_flat=data[15] / 10,
                month_side=data[16] / 10,
            )
        if "day_report" in contexts and prefix("FFFFFFFF0200", 9) and data[6] in (4, 5, 20):
            segment = data[8]
            if segment in (1, 6, 60, 2, 3):
                if len(data) < 18:
                    raise ValueError("underlength")
                matched("SleepDayReportActivity:handleReceiveData")
                slots = list(state.day_slots)
                if segment in (1, 6, 60):
                    scale = 0.1 if route.historical_day or segment == 6 else 1
                    state = replace(
                        state,
                        day_flat=data[9] * scale,
                        day_side=data[10] * scale,
                        day_total=(data[9] + data[10]) * scale,
                        day_rolls=data[11],
                        day_unit="hours" if route.historical_day or segment != 1 else "minutes",
                        app_day_unit=(
                            "hours"
                            if route.historical_day or segment != 1
                            else state.app_day_unit or "minutes"
                        ),
                    )
                    slots[:6] = data[12:18]
                else:
                    start = 6 if segment == 2 else 15
                    slots[start : start + 9] = data[9:18]
                state = replace(
                    state,
                    day_operation=data[6],
                    day_segment=segment,
                    day_slots=tuple(slots),
                    day_received_segments=tuple(
                        sorted(set(state.day_received_segments) | {segment})
                    ),
                )
                if segment == 3:
                    start = 8 + route.day_window_offset if route.historical_day else 8
                    state = replace(
                        state,
                        day_window=tuple(slots[start : start + 12]),
                        day_window_start_hour=(20 + route.day_window_offset) % 24
                        if route.historical_day
                        else 20,
                    )
                    if not route.historical_day:
                        state = replace(
                            state,
                            day_previous_window=tuple(slots[:12]),
                            day_next_window=tuple(slots[12:24]),
                            app_day_previous_window=tuple(slots[12:24]),
                        )
    except ValueError as error:
        return MotionBedParseResult(current, rejection=str(error))
    return MotionBedParseResult(state, tuple(records), tuple(effects), tuple(receipts))
