"""Allowlisted Fuzion control schema from the verified SleepIQ 5.4.11 artifact.

Names are service operations, never arbitrary wire commands. The response field
order follows generated constructors, not alphabetical getter inventories.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class FuzionCommand:
    key: str
    parameters: tuple[tuple[str, str], ...] = ()
    response: tuple[tuple[str, str], ...] = ()


ENUMS: dict[str, tuple[str, ...]] = {
    "AccessPointAction": ("start", "stop"),
    "ActLocation": ("head", "foot"),
    "ActuatorMovementStatus": ("0", "1"),
    "ApplyType": ("app", "app_no_check", "recovery"),
    "ArticulationPreset": (
        "none",
        "in_progress",
        "flat",
        "favorite",
        "snore",
        "zero_g",
        "watch_tv",
        "read",
    ),
    "BaseType": ("unknown", "no_base", "integrated_base", "ff1", "ff2", "ff3", "c360"),
    "BedPresence": ("out", "in", "unknown"),
    "BedPresenceFlag": ("out", "in"),
    "ChamberType": ("single", "dual"),
    "CreqCommand": ("0", "1", "2", "3", "4"),
    "DataRecordServiceName": (
        "all",
        "articulation",
        "biosignal",
        "ble_mgmt",
        "boson",
        "cloud",
        "diagnostics",
        "footwarming",
        "led",
        "logging",
        "messaging",
        "network",
        "ubl",
        "button",
        "persistence",
        "power",
        "pressure_control",
        "remote",
        "responsive_air",
        "routine",
        "software_mgmt",
        "software_watchdog",
        "system",
        "temperature_sensor",
        "thermal",
    ),
    "EnableFlag": ("yes", "no"),
    "EnabledSetting": ("0", "1", "2"),
    "FileType": ("report", "metadata"),
    "FootwarmingSetting": ("off", "low", "medium", "high"),
    "FrostySoftwareType": ("app", "update", "recovery", "bootloader"),
    "HealthStatus": (
        "normal",
        "not_enabled",
        "wrong_sensor_count",
        "read_sensor_position_error",
        "duplicate_sensor_position_error",
        "read_sensor_temperature_error",
        "temperature_strip_not_connected",
        "temperature_out_of_range",
    ),
    "HeidiRoutineEnable": ("true", "false"),
    "HeidiVersionType": ("app", "update", "recovery", "bootloader"),
    "Homing": ("done", "in_progress", "required", "error"),
    "HwSku": ("unknown", "SKUA", "SKUB", "SKUC"),
    "Image": ("app", "recovery"),
    "InstallationStatus": ("none", "done", "articulation_error", "configuration_error"),
    "LedState": ("off", "on", "blink_fast", "blink_slow"),
    "LogLevel": ("0", "1", "2", "3", "4", "5", "6", "7", "8"),
    "MattressSize": (
        "twin",
        "twinxl",
        "full",
        "double",
        "queen",
        "king",
        "king-split",
        "king-flex",
    ),
    "MigrateOptions": ("keep", "new"),
    "NameType": ("fuzion_bed_name", "right_sleeper_name", "left_sleeper_name"),
    "NetworkConnectivity": (
        "no_config",
        "network_cred",
        "detecting_ssid",
        "ssid_not_found",
        "bad_wifi_pwd",
        "wifi_associated",
        "wifi_disassociated",
        "dns_resolution",
        "server_login_attempted",
        "connected_over_bloh",
    ),
    "Presence": ("false", "true"),
    "RebootDevice": ("maverick", "goose", "both"),
    "RemoteBinaryType": (
        "bootloader",
        "main_app",
        "recovery",
        "ble_main_app",
        "ble_recovery",
        "ui_assets",
        "none",
    ),
    "ResetType": ("flat", "favorite", "snore", "zero_g", "watch_tv", "read", "all"),
    "SensorIndex": ("0", "1", "2", "3", "4"),
    "ServiceName": (
        "all",
        "articulation",
        "biosignal",
        "ble_conn",
        "ble_mgmt",
        "boson",
        "cloud",
        "cooling",
        "diagnostics",
        "direct_transfer",
        "footwarming",
        "led",
        "logging",
        "messaging",
        "network",
        "peripheral",
        "persistence",
        "power",
        "pressure",
        "provisioning",
        "remote",
        "responsive_air",
        "routine",
        "sleep_sensor_data",
        "software_mgmt",
        "software_watchdog",
        "supervisor_logger",
        "system",
        "temperature_sensor",
        "thermal_control",
    ),
    "Side": ("left", "right"),
    "SleepNumberAdjustmentStatus": ("0", "1"),
    "SleepiqDataState": ("unknown", "active", "paused"),
    "SoftwareDownloadStatus": (
        "no_update_needed",
        "downloading_fuzion_app",
        "applying_fuzion_app",
        "downloading_fuzion_rfs",
        "applying_fuzion_rfs",
        "downloading_fuzion_goose",
        "applying_fuzion_goose",
        "downloading_heidi",
        "applying_heidi",
        "downloading_frosty",
        "applying_frosty",
        "downloading_fuzion_remote",
        "applying_fuzion_remote",
        "waiting_to_apply",
        "downloading_unknown",
        "done",
    ),
    "StatusCode": (
        "0",
        "16",
        "17",
        "18",
        "19",
        "20",
        "21",
        "32",
        "33",
        "48",
        "49",
        "50",
        "64",
        "65",
        "66",
        "67",
        "68",
        "69",
    ),
    "ThermalEnableFlag": ("none", "heat_cool", "cool"),
    "ThermalMode": (
        "off",
        "cooling_pull_low",
        "cooling_pull_med",
        "cooling_pull_high",
        "cooling_push_high",
        "heating_push_low",
        "heating_push_med",
        "heating_push_high",
        "fan_test_pull",
        "fan_test_push",
        "heater_test_push",
    ),
    "UblAutoEnable": ("true", "false"),
    "UblCurrentStatus": ("normal", "under_current", "over_current"),
    "UblLevel": ("off", "low", "medium", "high"),
}

COMMANDS: dict[str, FuzionCommand] = {
    "cancel_current_diagnostic_run": FuzionCommand("DSRC", (), ()),
    "cancel_target_preset": FuzionCommand("ACCP", (("side", "Side"),), ()),
    "create_temperature_program": FuzionCommand(
        "TTPC", (("program", "String"),), (("program_json", "String"),)
    ),
    "delete_temperature_program": FuzionCommand("TTPD", (("program_id", "String"),), ()),
    "get_active_temperature_programs": FuzionCommand("TTPR", (), (("program_ids", "String"),)),
    "get_actuator_movement_status": FuzionCommand(
        "ACTM",
        (),
        (
            ("right_head", "ActuatorMovementStatus"),
            ("right_foot", "ActuatorMovementStatus"),
            ("left_head", "ActuatorMovementStatus"),
            ("left_foot", "ActuatorMovementStatus"),
        ),
    ),
    "get_actuator_position": FuzionCommand(
        "ACTG",
        (("side", "Side"), ("actuator", "ActLocation")),
        (("current_actuator_position", "int"),),
    ),
    "get_bed_configuration": FuzionCommand(
        "SYAG",
        (),
        (
            ("mattress_size", "MattressSize"),
            ("base_type", "BaseType"),
            ("chamber_type", "ChamberType"),
        ),
    ),
    "get_central_devices_metadata": FuzionCommand(
        "BGCD", (), (("paired_devices_information", "String"),)
    ),
    "get_current_preset": FuzionCommand(
        "AGCP", (("side", "Side"),), (("current_preset", "ArticulationPreset"),)
    ),
    "get_favorite_sleep_number": FuzionCommand(
        "SNFG", (("side", "Side"),), (("favorite_sleep_number", "int"),)
    ),
    "get_footwarming_presence": FuzionCommand(
        "FWPG", (("side", "Side"),), (("footwarming_presence_flag", "int"),)
    ),
    "get_footwarming_settings": FuzionCommand(
        "FWTG",
        (("side", "Side"),),
        (
            ("footwarming_level", "FootwarmingSetting"),
            ("remaining_time", "int"),
            ("total_remaining_time", "int"),
        ),
    ),
    "get_frosty_mode": FuzionCommand(
        "CLMG",
        (("side", "Side"),),
        (("frosty_mode_state", "ThermalMode"), ("remaining_time", "int")),
    ),
    "get_frosty_presence": FuzionCommand(
        "CLPG", (("side", "Side"),), (("frosty_presence", "Presence"),)
    ),
    "get_fuzion_remote_mac_addresses": FuzionCommand(
        "FRMG", (), (("remote_device_addresses", "String"),)
    ),
    "get_heidi_mode": FuzionCommand(
        "THMG",
        (("side", "Side"),),
        (("heidi_mode_state", "ThermalMode"), ("remaining_time", "int")),
    ),
    "get_heidi_presence": FuzionCommand(
        "THPG", (("side", "Side"),), (("heidi_presence", "Presence"),)
    ),
    "get_manifest_name": FuzionCommand("SMNG", (), (("current_manifest_name", "String"),)),
    "get_responsive_air_enabled_status": FuzionCommand(
        "LRAG", (("side", "Side"),), (("responsive_air_enable_flag", "EnabledSetting"),)
    ),
    "get_simple_diagnostic_run_results": FuzionCommand("DSRG", (), (("run_results", "String"),)),
    "get_sleep_number_controls": FuzionCommand(
        "SNCG",
        (("side", "Side"),),
        (
            ("sleep_number_adjustment_status", "SleepNumberAdjustmentStatus"),
            ("ambient_sleep_number", "int"),
            ("user_sleep_number", "int"),
        ),
    ),
    "get_sleepiq_privacy_state": FuzionCommand(
        "SPRG", (), (("sleepiq_privacy_state", "SleepiqDataState"),)
    ),
    "get_system_configuration": FuzionCommand(
        "SYCG",
        (),
        (
            ("chamber_type", "ChamberType"),
            ("pressure_control_enabled_flag", "EnableFlag"),
            ("articulation_enable_flag", "EnableFlag"),
            ("underbed_light_enable_flag", "EnableFlag"),
            ("rapid_sleep_setting_enable_flag", "EnableFlag"),
            ("thermal_control_enabled_flag", "ThermalEnableFlag"),
            ("right_head_actuator", "EnableFlag"),
            ("right_foot_actuator", "EnableFlag"),
            ("left_head_actuator", "EnableFlag"),
            ("left_foot_actuator", "EnableFlag"),
            ("flat_preset", "EnableFlag"),
            ("favorite_preset", "EnableFlag"),
            ("snore_preset", "EnableFlag"),
            ("zero_gravity_preset", "EnableFlag"),
            ("watch_tv_preset", "EnableFlag"),
            ("read_preset", "EnableFlag"),
        ),
    ),
    "get_system_settings_applied_status": FuzionCommand(
        "SYSA", (), (("bed_installation_status", "InstallationStatus"), ("hardware_sku", "HwSku"))
    ),
    "get_system_status": FuzionCommand(
        "SYST",
        (),
        (
            ("network_connectivity_status", "NetworkConnectivity"),
            ("fuzion_device_software_download_status", "SoftwareDownloadStatus"),
        ),
    ),
    "get_target_preset_with_timer": FuzionCommand(
        "ACGP",
        (("side", "Side"),),
        (("target_preset_with_timer", "ArticulationPreset"), ("remaining_time", "int")),
    ),
    "get_temperature_program_info": FuzionCommand(
        "TTPG", (("side", "Side"),), (("program_json", "String"),)
    ),
    "get_temperature_program_settings": FuzionCommand(
        "TTPE", (("side", "Side"),), (("program_json", "String"),)
    ),
    "get_underbed_light_auto_mode_status": FuzionCommand(
        "UBAG",
        (),
        (
            ("underbed_light_auto_mode_enable_status", "UblAutoEnable"),
            ("underbed_light_auto_mode_intensity_level", "UblLevel"),
        ),
    ),
    "get_underbed_light_settings": FuzionCommand(
        "UBLG",
        (),
        (("underbed_light_intensity_level", "UblLevel"), ("underbed_light_timer_value", "int")),
    ),
    "gets_actuator_homing_state": FuzionCommand("ACHG", (), (("bed_homing_state", "Homing"),)),
    "halt_all_actuators": FuzionCommand("ACHA", (), ()),
    "interrupt_sleep_number_adjustment": FuzionCommand("PSNI", (), ()),
    "migrate_routines_to_temperature_programs": FuzionCommand(
        "TTPM", (("side", "Side"), ("migration_options", "MigrateOptions")), ()
    ),
    "reboot_system": FuzionCommand("SYRS", (("reboot_device", "RebootDevice"),), ()),
    "routine_migration_status": FuzionCommand(
        "TTPN", (("side", "Side"),), (("migration_status", "int"),)
    ),
    "set_actuator_target_position": FuzionCommand(
        "ACTS",
        (("side", "Side"), ("actuator", "ActLocation"), ("target_actuator_position", "int")),
        (),
    ),
    "set_actuator_target_position_with_timer": FuzionCommand(
        "ASTM",
        (("side", "Side"), ("actuator", "ActLocation"), ("target_actuator_position", "int")),
        (),
    ),
    "set_articulation_preset_settings": FuzionCommand(
        "ACPS",
        (
            ("side", "Side"),
            ("articulation_preset", "ArticulationPreset"),
            ("preset_head_position", "int"),
            ("preset_foot_position", "int"),
        ),
        (),
    ),
    "set_bed_presence": FuzionCommand(
        "LBPS", (("side", "Side"), ("bed_presence_flag", "BedPresenceFlag")), ()
    ),
    "set_favorite_sleep_number": FuzionCommand(
        "SNFS", (("side", "Side"), ("favorite_sleep_number", "int")), ()
    ),
    "set_footwarming_settings": FuzionCommand(
        "FWTS",
        (
            ("side", "Side"),
            ("footwarming_level", "FootwarmingSetting"),
            ("footwarming_timer_value", "int"),
        ),
        (),
    ),
    "set_frosty_mode": FuzionCommand(
        "CLMS",
        (("side", "Side"), ("frosty_mode_control", "ThermalMode"), ("cooling_timer_value", "int")),
        (),
    ),
    "set_heidi_mode": FuzionCommand(
        "THMS", (("side", "Side"), ("heidi_mode_control", "ThermalMode"), ("timer", "int")), ()
    ),
    "set_responsive_air_enabled_status": FuzionCommand(
        "LRAS", (("side", "Side"), ("responsive_air_enable_flag", "EnabledSetting")), ()
    ),
    "set_sleepiq_privacy_state": FuzionCommand(
        "SPRS", (("sleepiq_privacy_state", "SleepiqDataState"),), ()
    ),
    "set_system_time": FuzionCommand("SYTS", (("date_time", "String"),), ()),
    "set_target_preset_with_timer": FuzionCommand(
        "ACSP",
        (("side", "Side"), ("target_preset_with_timer", "ArticulationPreset"), ("timer", "int")),
        (),
    ),
    "set_target_preset_without_timer": FuzionCommand(
        "ASTP", (("side", "Side"), ("target_preset", "ArticulationPreset")), ()
    ),
    "set_temperature_program": FuzionCommand(
        "TTPS", (("program", "String"),), (("program_json", "String"),)
    ),
    "set_underbed_light_auto_mode": FuzionCommand(
        "UBAS",
        (
            ("underbed_light_auto_mode_enable_status", "UblAutoEnable"),
            ("underbed_light_auto_mode_intensity_level", "UblLevel"),
        ),
        (),
    ),
    "set_underbed_light_settings": FuzionCommand(
        "UBLS",
        (("underbed_light_intensity_level", "UblLevel"), ("underbed_light_timer_value", "int")),
        (),
    ),
    "start_sleep_number_adjustment": FuzionCommand(
        "PSNS", (("side", "Side"), ("user_sleep_number", "int")), ()
    ),
    "starts_actuator_homing": FuzionCommand("ACHS", (), ()),
}


# The app joins these two BAMKEY responses by program ID.
COMMANDS["get_temperature_programs"] = COMMANDS["get_temperature_program_info"]


def _object(value: object, fields: set[str], label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError(f"{label} requires exactly: {', '.join(sorted(fields))}")
    if not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} field names must be strings")
    return value


def _text(value: object, label: str, *, spaces: bool = False) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError(f"{label} must be a nonempty string of at most 256 characters")
    if any(ord(char) < 32 for char in value) or (
        not spaces and any(char.isspace() for char in value)
    ):
        raise ValueError(f"{label} contains unsupported whitespace or control characters")
    return value


def _integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer from {minimum} to {maximum}")
    return value


def _choice(value: object, choices: tuple[str, ...], label: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"{label} must be one of {', '.join(choices)}")
    return value


def _time(value: object, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3])[0-5][0-9]", value):
        raise ValueError(f"{label} must use 24-hour HHmm format")
    return value


def validate_temperature_program(value: object, *, creating: bool = False) -> Mapping[str, object]:
    """Validate the artifact's JSON model and its distinct thermal tokens."""
    if not isinstance(value, Mapping):
        raise ValueError("program must be an object")
    normalized = dict(value)
    normalized.setdefault("wake_time", None)
    if normalized["wake_time"] == "":
        normalized["wake_time"] = None
    if creating:
        normalized.setdefault("id", None)
    program = _object(
        normalized,
        {
            "days",
            "enabled",
            "wake_time",
            "footwarming",
            "id",
            "segments",
            "side",
            "bed_time",
            "type",
            "version",
        },
        "program",
    )
    if not creating or program["id"] is not None:
        _text(program["id"], "program.id")
    _integer(program["version"], "program.version", 0, 2**31 - 1)
    if type(program["enabled"]) is not bool:
        raise ValueError("program.enabled must be boolean")
    _choice(program["side"], ENUMS["Side"], "program.side")
    _choice(
        program["type"],
        ("personal", "all-night", "deep-sleep", "warming-deep-sleep", "footwarming"),
        "program.type",
    )
    _choice(program["footwarming"], ENUMS["FootwarmingSetting"], "program.footwarming")
    _time(program["bed_time"], "program.bed_time")
    # Wake time is nullable in the shipped model.
    if program["wake_time"] is not None:
        _time(program["wake_time"], "program.wake_time")
    days = program["days"]
    if not isinstance(days, list) or len(days) > 7:
        raise ValueError("program.days must contain at most 7 weekdays")
    for day in days:
        _choice(day, ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"), "program.days")
    if len(set(days)) != len(days):
        raise ValueError("program.days must not repeat weekdays")
    segments = program["segments"]
    if not isinstance(segments, list):
        raise ValueError("program.segments must be a list")
    for value in segments:
        segment = _object(
            value,
            {"core_temperature", "end_time", "footwarming", "stage", "start_time", "type"},
            "segment",
        )
        stage = _integer(segment["stage"], "segment.stage", 0, 2)
        if segment["type"] != ("fall_asleep", "stay_asleep", "wake_up")[stage]:
            raise ValueError(
                "segment.stage must match its type (fall_asleep=0, stay_asleep=1, wake_up=2)"
            )
        _choice(segment["type"], ("fall_asleep", "stay_asleep", "wake_up"), "segment.type")
        _choice(
            segment["core_temperature"],
            (
                "off",
                "cooling_low",
                "cooling_med",
                "cooling_high",
                "special_cooling_high",
                "heating_low",
                "heating_med",
                "heating_high",
            ),
            "segment.core_temperature",
        )
        _choice(segment["footwarming"], ENUMS["FootwarmingSetting"], "segment.footwarming")
        _time(segment["start_time"], "segment.start_time")
        _time(segment["end_time"], "segment.end_time")
    return program


def format_command(
    command: str, parameters: Mapping[str, object]
) -> tuple[FuzionCommand, tuple[str, ...]]:
    """Validate every parameter before returning any bytes to the caller."""
    try:
        spec = COMMANDS[command]
    except KeyError as err:
        raise ValueError(f"Unsupported Sleep Number operation: {command}") from err
    _object(parameters, {name for name, _kind in spec.parameters}, "parameters")
    args: list[str] = []
    for name, kind in spec.parameters:
        value = parameters[name]
        if kind == "int":
            maximum = 100
            if "timer" in name:
                maximum = {"FWTS": 360, "UBLS": 180, "ACSP": 2**31 - 1}.get(spec.key, 600)
            number = _integer(value, name, 0, maximum)
            if "sleep_number" in name and (number < 5 or number % 5):
                raise ValueError(f"{name} must be 5-100 in steps of 5")
            args.append(str(number))
        elif kind in ENUMS:
            choices = ENUMS[kind]
            if kind == "ThermalMode":
                choices = choices[:4] if spec.key == "CLMS" else choices[:8]
            elif kind == "ArticulationPreset":
                choices = choices[2:]
            elif kind == "SleepiqDataState":
                choices = ("active", "paused")
            elif kind == "EnabledSetting":
                choices = ("0", "1")
            args.append(_choice(value, choices, name))
        elif name == "program":
            args.append(
                json.dumps(
                    {
                        key: item
                        for key, item in validate_temperature_program(
                            value, creating=spec.key == "TTPC"
                        ).items()
                        if item is not None
                    },
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
            )
        elif name == "date_time":
            text = _text(value, name)
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", text):
                raise ValueError("date_time must use UTC YYYY-MM-DDTHH:mm:ss")
            datetime.strptime(text, "%Y-%m-%dT%H:%M:%S")
            args.append(text)
        else:
            args.append(_text(value, name))
    if spec.key == "UBAS" and args[0] == "false":
        # The app explicitly uses low as the ignored intensity on disable.
        args[1] = "low"
    return spec, tuple(args)


def parse_response(spec: FuzionCommand, values: list[str]) -> dict[str, object]:
    """Parse response integers/enums in the exact generated field order."""
    if len(values) != len(spec.response):
        raise ValueError(f"{spec.key} returned an invalid number of fields")
    result: dict[str, object] = {}
    for (name, kind), value in zip(spec.response, values, strict=True):
        if kind == "int":
            result[name] = int(value)
        elif kind in ENUMS:
            result[name] = _choice(value, ENUMS[kind], name)
        elif spec.key in {"TTPG", "TTPE", "TTPC", "TTPS", "TTPR", "BGCD", "DSRG"}:
            result[name] = json.loads(value)
        else:
            result[name] = value
    return result


def combine_temperature_programs(info: object, settings: object) -> list[dict[str, object]]:
    """Join settings by ID, using the app's off/empty defaults if missing."""
    if not isinstance(info, list) or not isinstance(settings, list):
        raise ValueError("Temperature program responses must contain lists")
    programs: list[dict[str, object]] = []
    for item in info:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("Temperature program info requires an id")
        matching = next(
            (
                entry
                for entry in settings
                if isinstance(entry, dict) and entry.get("id") == item["id"]
            ),
            {},
        )
        program = dict(item)
        program["footwarming"] = matching.get("footwarming") or "off"
        program["segments"] = matching.get("segments") or []
        programs.append(dict(validate_temperature_program(program)))
    return programs


class SleepNumberActions(ABC):
    """Semantic Sleep Number configuration actions shared by both transports."""

    @property
    @abstractmethod
    def sleep_number_command_names(self) -> tuple[str, ...]:
        """Return the supported semantic Sleep Number configuration actions."""

    @abstractmethod
    def validate_sleep_number_command(self, command: str, parameters: Mapping[str, object]) -> None:
        """Validate a complete action without changing the bed."""

    @abstractmethod
    async def async_execute_sleep_number_command(
        self, command: str, parameters: Mapping[str, object]
    ) -> dict[str, object]:
        """Execute an allowlisted action and return its structured result."""
