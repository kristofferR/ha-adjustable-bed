# Sleep Number BLE commands

Use `adjustable_bed.sleep_number_command` for additional Sleep Number controls and
queries. The command picker includes both Fuzion and older MCR commands; each bed
rejects commands or features it does not support. Parameters are a structured
object, never raw packets. Unknown or missing fields fail validation.

```yaml
action: adjustable_bed.sleep_number_command
data:
  device_id: YOUR_DEVICE_ID
  command: get_system_status
response_variable: bed_status
```

The optional response has `command` and `results` fields. `results` maps `single`,
`left`, `right`, or native `both` to the controller's parsed response. Setters may return an empty
object. Firmware errors and missing required responses fail the action.

For paired beds, the top-level `side` selects the physical target (`left`, `right`,
or `both`). Targeting a child device defaults to that child. Commands with a
`parameters.side` field require `left` or `right`; it must agree with a bound
physical side. To run such a command on both paired sides, make separate calls
with matching top-level and parameter sides. All selected sides are validated
before the requested commands execute. Calls use the integration's command lock
and paired cancellation rules. Status and configuration calls do not interrupt
motion; motion and stop calls can cancel a running movement.

## Fuzion commands

`get_temperature_programs` joins temperature-program info and settings by
program ID into a complete program list. Hardware support is checked from the
connected bed.

Use the command name below with exactly the listed `parameters`. A selected
physical side cannot be overridden by a conflicting `side` or program `side`.
The service returns a dictionary with the listed response fields. JSON schedule,
paired-device metadata and diagnostic results are decoded into native objects.
Commands missing from the connected bed's SYCG capability flags are rejected.
`set_system_time.date_time` uses UTC `YYYY-MM-DDTHH:mm:ss`, from the app's Hh/a.d formatter.

Integer actuator/preset positions are 0-100. Firmness is 5-100 in steps of 5.
Footwarming timers are 0-360 minutes, underbed lighting 0-180, and core/cooling
timers 0-600. Articulation preset timers retain the nonnegative Java integer
range of their artifact builder; no thermal limit is borrowed for articulation.
Off commands use a zero timer. Enum request values are strings (including `0`/`1`
for Responsive Air). Readback enum strings retain their wire values.

| Operation | Parameters in wire order | Response fields in wire order |
|---|---|---|
| `cancel_current_diagnostic_run` | None | Empty dictionary |
| `cancel_target_preset` | `side`: Side | Empty dictionary |
| `create_temperature_program` | `program`: String | `program_json`: String |
| `delete_temperature_program` | `program_id`: String | Empty dictionary |
| `get_active_temperature_programs` | None | `program_ids`: String |
| `get_actuator_movement_status` | None | `right_head`: ActuatorMovementStatus, `right_foot`: ActuatorMovementStatus, `left_head`: ActuatorMovementStatus, `left_foot`: ActuatorMovementStatus |
| `get_actuator_position` | `side`: Side, `actuator`: ActLocation | `current_actuator_position`: int |
| `get_bed_configuration` | None | `mattress_size`: MattressSize, `base_type`: BaseType, `chamber_type`: ChamberType |
| `get_central_devices_metadata` | None | `paired_devices_information`: String |
| `get_current_preset` | `side`: Side | `current_preset`: ArticulationPreset |
| `get_favorite_sleep_number` | `side`: Side | `favorite_sleep_number`: int |
| `get_footwarming_presence` | `side`: Side | `footwarming_presence_flag`: int |
| `get_footwarming_settings` | `side`: Side | `footwarming_level`: FootwarmingSetting, `remaining_time`: int, `total_remaining_time`: int |
| `get_frosty_mode` | `side`: Side | `frosty_mode_state`: ThermalMode, `remaining_time`: int |
| `get_frosty_presence` | `side`: Side | `frosty_presence`: Presence |
| `get_fuzion_remote_mac_addresses` | None | `remote_device_addresses`: String |
| `get_heidi_mode` | `side`: Side | `heidi_mode_state`: ThermalMode, `remaining_time`: int |
| `get_heidi_presence` | `side`: Side | `heidi_presence`: Presence |
| `get_manifest_name` | None | `current_manifest_name`: String |
| `get_responsive_air_enabled_status` | `side`: Side | `responsive_air_enable_flag`: EnabledSetting |
| `get_simple_diagnostic_run_results` | None | `run_results`: String |
| `get_sleep_number_controls` | `side`: Side | `sleep_number_adjustment_status`: SleepNumberAdjustmentStatus, `ambient_sleep_number`: int, `user_sleep_number`: int |
| `get_sleepiq_privacy_state` | None | `sleepiq_privacy_state`: SleepiqDataState |
| `get_system_configuration` | None | `chamber_type`: ChamberType, `pressure_control_enabled_flag`: EnableFlag, `articulation_enable_flag`: EnableFlag, `underbed_light_enable_flag`: EnableFlag, `rapid_sleep_setting_enable_flag`: EnableFlag, `thermal_control_enabled_flag`: ThermalEnableFlag, `right_head_actuator`: EnableFlag, `right_foot_actuator`: EnableFlag, `left_head_actuator`: EnableFlag, `left_foot_actuator`: EnableFlag, `flat_preset`: EnableFlag, `favorite_preset`: EnableFlag, `snore_preset`: EnableFlag, `zero_gravity_preset`: EnableFlag, `watch_tv_preset`: EnableFlag, `read_preset`: EnableFlag |
| `get_system_settings_applied_status` | None | `bed_installation_status`: InstallationStatus, `hardware_sku`: HwSku |
| `get_system_status` | None | `network_connectivity_status`: NetworkConnectivity, `fuzion_device_software_download_status`: SoftwareDownloadStatus |
| `get_target_preset_with_timer` | `side`: Side | `target_preset_with_timer`: ArticulationPreset, `remaining_time`: int |
| `get_temperature_program_info` | `side`: Side | `program_json`: String |
| `get_temperature_program_settings` | `side`: Side | `program_json`: String |
| `get_underbed_light_auto_mode_status` | None | `underbed_light_auto_mode_enable_status`: UblAutoEnable, `underbed_light_auto_mode_intensity_level`: UblLevel |
| `get_underbed_light_settings` | None | `underbed_light_intensity_level`: UblLevel, `underbed_light_timer_value`: int |
| `gets_actuator_homing_state` | None | `bed_homing_state`: Homing |
| `halt_all_actuators` | None | Empty dictionary |
| `interrupt_sleep_number_adjustment` | None | Empty dictionary |
| `migrate_routines_to_temperature_programs` | `side`: Side, `migration_options`: MigrateOptions | Empty dictionary |
| `reboot_system` | `reboot_device`: RebootDevice | Empty dictionary |
| `routine_migration_status` | `side`: Side | `migration_status`: int |
| `set_actuator_target_position` | `side`: Side, `actuator`: ActLocation, `target_actuator_position`: int | Empty dictionary |
| `set_actuator_target_position_with_timer` | `side`: Side, `actuator`: ActLocation, `target_actuator_position`: int | Empty dictionary |
| `set_articulation_preset_settings` | `side`: Side, `articulation_preset`: ArticulationPreset, `preset_head_position`: int, `preset_foot_position`: int | Empty dictionary |
| `set_bed_presence` | `side`: Side, `bed_presence_flag`: BedPresenceFlag | Empty dictionary |
| `set_favorite_sleep_number` | `side`: Side, `favorite_sleep_number`: int | Empty dictionary |
| `set_footwarming_settings` | `side`: Side, `footwarming_level`: FootwarmingSetting, `footwarming_timer_value`: int | Empty dictionary |
| `set_frosty_mode` | `side`: Side, `frosty_mode_control`: ThermalMode, `cooling_timer_value`: int | Empty dictionary |
| `set_heidi_mode` | `side`: Side, `heidi_mode_control`: ThermalMode, `timer`: int | Empty dictionary |
| `set_responsive_air_enabled_status` | `side`: Side, `responsive_air_enable_flag`: EnabledSetting | Empty dictionary |
| `set_sleepiq_privacy_state` | `sleepiq_privacy_state`: SleepiqDataState | Empty dictionary |
| `set_system_time` | `date_time`: String | Empty dictionary |
| `set_target_preset_with_timer` | `side`: Side, `target_preset_with_timer`: ArticulationPreset, `timer`: int | Empty dictionary |
| `set_target_preset_without_timer` | `side`: Side, `target_preset`: ArticulationPreset | Empty dictionary |
| `set_temperature_program` | `program`: String | `program_json`: String |
| `set_underbed_light_auto_mode` | `underbed_light_auto_mode_enable_status`: UblAutoEnable, `underbed_light_auto_mode_intensity_level`: UblLevel | Empty dictionary |
| `set_underbed_light_settings` | `underbed_light_intensity_level`: UblLevel, `underbed_light_timer_value`: int | Empty dictionary |
| `start_sleep_number_adjustment` | `side`: Side, `user_sleep_number`: int | Empty dictionary |
| `starts_actuator_homing` | None | Empty dictionary |
| `get_temperature_programs` | `side`: Side | `programs`: combined list |

### Fuzion request enums

- **ActLocation:** `head`, `foot`.
- **ArticulationPreset:** `flat`, `favorite`, `snore`, `zero_g`, `watch_tv`, `read`.
- **BedPresenceFlag:** `out`, `in`.
- **EnabledSetting:** `0`, `1`.
- **FootwarmingSetting:** `off`, `low`, `medium`, `high`.
- **MigrateOptions:** `keep`, `new`.
- **RebootDevice:** `maverick`, `goose`, `both`.
- **Side:** `left`, `right`.
- **SleepiqDataState:** `active`, `paused`.
- **ThermalMode:** `off`, `cooling_pull_low`, `cooling_pull_med`, `cooling_pull_high`, `cooling_push_high`, `heating_push_low`, `heating_push_med`, `heating_push_high`.
- **UblAutoEnable:** `true`, `false`.
- **UblLevel:** `off`, `low`, `medium`, `high`.

Cooling-only CLMS accepts only off and three cooling_pull modes. THMS additionally
accepts heating and cooling boost. Fan/heater factory-test enum values are never
accepted. Disabling automatic underbed lighting always serializes `false low`,
as the app does.

### Fuzion temperature program object

`create_temperature_program` and `set_temperature_program` require `program`
with `version`, `enabled`, `side`, `type`, `bed_time`, `days`,
`footwarming`, `segments`. New programs may omit `id` or supply null; updates
require an existing ID. Times use `HHmm`; optional `wake_time` may be absent,
empty, or null. Nullable fields are omitted from writes like the app's Gson
serializer. Days are
Mon/Tue/Wed/Thu/Fri/Sat/Sun. Types are personal, all-night, deep-sleep,
warming-deep-sleep, footwarming. Each segment has `stage` (0=fall_asleep, 1=stay_asleep, 2=wake_up), matching
`type` (fall_asleep,
stay_asleep, wake_up), `start_time`, `end_time`, `footwarming`, `core_temperature`.
JSON thermal values are off, cooling_low, cooling_med, cooling_high,
special_cooling_high, heating_low, heating_med, heating_high. They are deliberately
different from direct THMS values. Retrieval combines info/settings by ID, using
off footwarming and empty segments if settings are absent.

## Older MCR commands

These commands require the older MCR protocol. Every listed required parameter
must be supplied. Optional durations default to zero, except active foot warming defaults to 120 minutes. Omitted massage timer preserves its current value. Numeric fields
must be integers and booleans must be actual booleans.

| Command | Required parameters | Optional parameters |
|---|---|---|
| `mcr_status` | None | None |
| `foundation_status` | None | None |
| `position` | `axis`, `position`, `side` | None |
| `stop` | `side` | None |
| `preset_save` | `preset`, `side` | None |
| `preset_reset` | `preset`, `side` | None |
| `preset_timer` | `preset`, `side`, `timer` | None |
| `firmness_favorite` | `firmness`, `side` | None |
| `firmness_favorites` | None | None |
| `responsive_air` | `enabled`, `side` | None |
| `responsive_air_status` | None | None |
| `massage` | `side` | `foot`, `head`, `mode`, `timer` |
| `massage_status` | `side` | None |
| `foot_warming` | `level`, `side` | `duration` |
| `foot_warming_status` | `side` | None |
| `outlet` | `enabled`, `outlet` | `duration` |
| `outlet_status` | `outlet` | None |
| `light_intensity` | `intensity`, `side` | None |
| `underbed_auto` | `enabled` | None |
| `underbed_auto_status` | None | None |
| `pinch_status` | None | None |
| `sense_and_do` | `enabled` | None |
| `sense_and_do_status` | None | None |
| `kid_outlet` | `device` | `light_on`, `outlet_on` |
| `kid_outlet_status` | `device` | None |
| `head_tilt` | `enabled` | None |
| `software_versions` | None | None |

Parameter values:

- `side`: `left` or `right`; `axis`: `head` or `foot`.
- `position`: 0–100; `firmness`: 5–100 in steps of 5.
- `head`, `foot`, `mode`, `level`: 0–3.
- `duration`, `timer`: 0–32767. Massage and outlet timers use seconds.
  Foot-warming durations use minutes. Preset timers accept the raw protocol value,
  with zero cancelling the timer; the APK evidence does not establish a time unit.
  Massage timer 255 preserves the existing timer.
- `outlet`: 1–4 (right/left nightstand 1/2, right/left nightlight 3/4; outlet 3 is the under-bed light on models with that feature); `device`: 0–15.
- `intensity`: 1, 30, 45, 75 or 100.
- `enabled`, `outlet_on`, `light_on`: true or false.
- `preset`: `Favorite`, `Read`, `Watch TV`, `Flat`, `Zero G` or `Snore`,
  restricted to presets supported by the connected foundation.

`massage` needs at least one of its optional settings. `kid_outlet` needs
`outlet_on` or `light_on`. Foundation features, presets, massage, warming, the
head-tilt chamber and sense-and-do are checked before commands execute.

```yaml
action: adjustable_bed.sleep_number_command
data:
  device_id: YOUR_DEVICE_ID
  side: left
  command: position
  parameters:
    side: left
    axis: head
    position: 35
```

Protocol behavior comes from the SleepIQ 5.4.11 APK. Physical validation on each
bed model remains pending; successful static tests do not establish hardware
compatibility.

### MCR position services

Use `set_position` or `set_positions` with the motor keys `left_back`,
`right_back`, `left_legs`, or `right_legs` and percentage targets from 0 to 100.
Only axes reported by the foundation are accepted. Unsided `back` and `legs`
are rejected so a request cannot silently move the wrong side.
