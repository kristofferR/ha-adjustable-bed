# Actions and Automations

Use **Developer Tools → Actions → Adjustable Bed** to inspect the fields for an
action. In YAML the action name is `adjustable_bed.<name>`. The examples below
use `device_id` in `data`; replace each placeholder with the ID of your bed's
device. A device ID is different from an entity ID such as `cover.bed_back`.

Only controls supported by the selected controller are available. Registering
an action does not mean that every bed supports it. For ordinary controls you
can also use the bed's `cover`, `button`, `number`, `light`, or other entities in
Home Assistant automations.

For named raise/lower/stop voice commands and Apple Home controls, see
[Apple Home and Siri](HOMEKIT.md), including ready-to-copy scripts and side targeting.

## Targeting a Bed or Side

| Target | Default behavior |
|--------|------------------|
| Standalone bed device | Operate that bed using its configured controller/side |
| Combined parent device | Operate both sides |
| Left or Right child device | Operate that child side |

For control actions, an optional `side: left`, `right`, or `both` narrows a
parent target. An explicit side conflicting with a child device, including
`both`, is rejected before commands run. Selecting both children in a supported
multi-device request is coalesced into a both-side operation. A combined command
uses the pair's connection strategy; the two sides are not guaranteed to start
at exactly the same instant. A failed combined movement triggers cleanup on
both sides.

`generate_support_bundle` is different: it accepts exactly one `device_id` or
`target_address` and has no `side` parameter. Select a child device for a
two-address pair. See [support capture](GETTING_HELP.md#generating-a-support-bundle).

## Malouf Base / Lucid Base Clock and Alarm

The explicit [app profile](beds/malouf-app.md) exposes clock actions only for
supported OKIN model/transport combinations. These actions accept `device_id`
and the ordinary optional `side`. Every target is validated before any write.

```yaml
action: adjustable_bed.malouf_set_alarm
data:
  device_id: YOUR_DEVICE_ID
  enabled: true
  time: "07:30:00"
  weekdays: [monday, tuesday, wednesday, thursday, friday]
  preset: zero_g
```

Choose `zero_g`, `lounge`, `tv`, `anti_snore`, `memory_1`, or `memory_2`.
Memory choices must fit every selected model's capacity. Time uses Home
Assistant's configured time zone and minute precision. An empty weekday list
programs the next occurrence as a one-shot alarm. Setting an enabled alarm
also synchronizes the device clock.

```yaml
action: adjustable_bed.malouf_set_alarm
data:
  device_id: YOUR_DEVICE_ID
  enabled: false
```

Use [`adjustable_bed.sync_clock`](#sync_clock) with `device_id` to synchronize
the clock separately; the older `malouf_sync_clock` name still works. Both
actions serialize configuration with other commands without cancelling active
movement. Hardware behavior remains unverified.

## Movement and Memory

| Action | Required fields besides `device_id` | Behavior |
|--------|------------------------------------|----------|
| `goto_preset` | `preset` | Recall a memory slot, 1–8 where supported. Optional `duration` sets the recall hold where the bed supports it |
| `save_preset` | `preset` | Overwrite a supported memory slot with the current position |
| `stop_all` | None | Cancel pending/active movement and perform the controller's STOP or release cleanup |
| `set_position` | `motor`, `position` | Move one supported axis to a target |
| `set_positions` | `positions` | Validate all motor targets before starting an ordered multi-motor request |
| `timed_move` | `motor`, `direction`, `duration_ms` | Move up/down for an elapsed movement ceiling of 100–30000 ms |

The maximum memory slot depends on the bed; accepting numbers up to 8 does not
create extra hardware memory. Named presets such as Flat or Zero G are exposed
as buttons where supported. `save_preset` changes memory stored on the bed.

`goto_preset` accepts an optional `duration` (0.1–60 seconds, whole
milliseconds) only on beds whose app recalls a memory by holding its button:
FSM Relax and Limoss Remote. Other beds reject it before any bed moves. Leave
it unset to use the bed's own recall gesture.

Position targets use the controller's units, which may be degrees or percentages.
Check the position entity and [protocol guide](SUPPORTED_ACTUATORS.md). Feedback
must be enabled for feedback-driven seeks. Sleep Number MCR uses `left_back`,
`right_back`, `left_legs`, and `right_legs` with percentage targets for discovered
foundation actuators. A `set_positions` list cannot repeat a motor. Its validation
is performed before movement, but a later transport failure can still leave a
partially completed move.

A direct command being accepted is not confirmation that the target was reached.
Reported state remains the last measured value until feedback arrives. See
[position state and freshness](TROUBLESHOOTING.md#position-commands-and-reported-state).

### Examples

Recall memory 1 on the left side of a combined bed:

```yaml
action: adjustable_bed.goto_preset
data:
  device_id: <combined bed device ID>
  side: left
  preset: 1
```

Set two positions on a bed that supports these axes and targets:

```yaml
action: adjustable_bed.set_positions
data:
  device_id: <bed device ID>
  positions:
    - motor: back
      position: 30
    - motor: legs
      position: 15
```

Raise the back for up to one second:

```yaml
action: adjustable_bed.timed_move
data:
  device_id: <bed device ID>
  motor: back
  direction: up
  duration_ms: 1000
```

The movement timer starts after connection and movement preparation. Write
latency counts toward the ceiling; some controllers finish earlier. The action
waits for release cleanup, so total execution time can exceed `duration_ms`.
Transport and cleanup failures remain errors. See [command lifecycle](COMMAND_LIFECYCLE.md).

Stop both sides of a combined bed:

```yaml
action: adjustable_bed.stop_all
data:
  device_id: <combined bed device ID>
  side: both
```

## Held Controls, Rename and Clock

These generic actions take `device_id` and optional `side`. Each bed's
controller declares what it supports, and every physical target is checked
before any of them is written.

### `hold_control`

Hold one control declared by the bed's app profile for `duration` seconds
(0.1–60, whole milliseconds), then send that profile's release sequence. A
control the bed does not declare is rejected with the list of controls the bed
accepts. Save controls can change stored positions. Svane Remote and Limoss
Remote beds validate and release through their own live session, so a single
call cannot mix them with other profiles.

```yaml
action: adjustable_bed.hold_control
data:
  device_id: YOUR_DEVICE_ID
  control: head_up
  duration: 2.5
```

| Profile | Controls | Timing and release |
|---------|----------|--------------------|
| [Leggett Okin app profiles](beds/leggett-okin.md) | `flat`, `snore`, `lights_toggle`, `massage_toggle`, `massage_wave`, `massage_head_up`, `massage_head_down`, `massage_foot_up`, `massage_foot_down`; U Series adds `memory_1`, `memory_2`, `store` | See the guide. `leggett_hold_control` remains as an alias limited to this list |
| [Jordan's Serenity](beds/serenity.md#reachable-commands) | 31 literal app actions | Two-frame release |
| [Jordan's Tranquil](beds/tranquil.md#reachable-commands) | 30 literal app actions | Two-frame release |
| [Customatic Z-Series](beds/customatic-z-series.md#reachable-commands) | Literal Z-230 or Z-280 actions | A Z-230 rejects Z-280-only actions and the reverse |
| [SIMMONS](beds/simmons.md) | `head_up`, `head_down`, `legs_up`, `legs_down`, `flat`, `memory`, `light`, plus `zero_g`, `tv`, `anti_snore` on a regular bed or `inclined_left`, `inclined_middle`, `inclined_right` on an inclined bed | Frame every 300 ms, then STOP at +100 and +400 ms. Holding `memory` for 5 seconds mirrors the app's Custom Mode save; whether the bed stores it is unverified |
| [Adjustable bed (Lumbar)](beds/adjustable-lumbar.md#timing-and-controls) | `head_up`, `head_down`, `feet_up`, `feet_down`, `lumbar_up`, `lumbar_down`, `flat`, `zero_g`, `lounge`, `incline`, `anti_snore`, `save_zero_g`, `save_lounge`, `save_incline`, `save_anti_snore`, `light`, `wave_1`, `wave_2`, `wave_3`, `massage_up`, `massage_down` | Frame every 100 ms, then STOP immediately and 300 ms later. Whether a save stores the position is unverified |
| [Simon Li / Heal Every Night / OKIN-Seating](beds/keeson.md#simon-li-heal-every-night-and-okin-seating-profiles) | Simon Li: `back_up`, `back_down`, `foot_up`, `foot_down`, `lumbar_up`, `lumbar_down`, `home`, `memory_1`, `memory_2`. OKIN-Seating: `back_up`, `back_down`, `foot_up`, `foot_down`, `home`. Heal Every Night: `head_up`, `head_down`, `foot_up`, `foot_down`, plus `tilt_up`, `tilt_down`, `lumbar_up`, `lumbar_down` on Healing 7 and 8 | Key every 100 ms, then the zero frame 10 ms (Simon Li, OKIN-Seating) or 100 ms (Heal Every Night) later. Holding a Simon Li memory for 2.1 seconds or more is the app's memory save |
| [Restonic BT (Keeson)](beds/keeson.md#restonic-bt-profiles) | Remote A: `head_up`, `head_down`, `feet_up`, `feet_down`, `flat`, `zero_g`. Remote B adds `back_legs_up`, `back_legs_down`, `light`, `zzz` | Directions, remote B's back and legs and remote A's `zero_g` repeat every 100 ms; the others are sent once. One zero frame 100 ms after the hold |
| [INNOVA](beds/keeson.md#innova-profile) | `back_up`, `back_down`, `legs_up`, `legs_down`, `memory_a`, `memory_b`, `memory_timer`, plus `combined_up`/`combined_down` (2M), `lumbar_up`/`lumbar_down` (3M, 4M) and `waist_up`/`waist_down` (4M) | Key every 100 ms, then the zero key 100 ms later |
| [AdjustableM5X4](beds/starcode-abm5-4.md) | Movement, preset, save and massage controls | Movement and memory refresh every 100 ms with immediate STOP. Flat runs 600 ms; save and reset run the six-second confirmation interval regardless of `duration`. Positive massage controls require observed active state. One physical address only |
| [Caresse / Werkmeister](beds/vibradorm_app.md) | Profile motor directions, `all_up`, `all_down`, `memory_1` to `memory_6`, Werkmeister `sync` | Completion-gated refresh, then a fresh release. All-down is a held direction, not a flat preset. Save memory uses the Save buttons |
| [V-MAT Basic](beds/vmatbasic.md) | `all_up`, `all_down`, `back_up`, `back_down`, `legs_up`, `legs_down`, XT-only `floor_hold` | Movement ends with a fresh `ff` release; both sides need two ready receivers. `floor_hold` ends its refresh without a release and targets one physical receiver |
| [Svane Remote](beds/svane.md) | `head_up`, `head_down`, `feet_up`, `feet_down`, the four `head_*_feet_*` combinations, `light_adjust` | See [Svane Remote held controls](#svane-remote-held-controls) |
| [Limoss Remote](beds/limoss-remote.md) | Controls rendered for the receiver's layout | Five-frame release |
| [FSM Relax](beds/fsm_relax.md) | `command_XX` values from the profile's protocol diagnostics | Replies cannot prove physical arrival |

Customatic Clarity, Remedy and Jerome's C use
[`customatic_hold_memory` and `customatic_move_simultaneously`](beds/customatic.md),
which select their memory and motor combinations as lists.

### `rename`

Write a new Bluetooth name to each targeted controller that supports it. This
does not rename the Home Assistant device or entities. Each controller applies
its app's name rule to every target before any write:

| Profile | Name rule |
|---------|-----------|
| [Linak Bed Control](beds/linak.md) | 1–17 UTF-8 bytes. The controller then disconnects so it can advertise the new name |
| [LOGICDATA app profiles](beds/logicdata-app.md) | Phone and tablet: 1–255 printable ASCII characters. [Sleep Smart](beds/logicdata-sleep-smart.md) beds and pumps: 1–20 letters, digits, ä, ö, ü or ß |
| [Jiecang app profiles](beds/jiecang-app.md) | 1–20 ASCII letters or digits |
| [INNOVA](beds/keeson.md#innova-profile) | At most 14 characters as typed, then trimmed and non-empty |
| [FurniMove](beds/furnimove.md#controls-and-actions) | One physical receiver; a unique name of at most 18 UTF-16 units after trimming |
| [V-MAT Basic](beds/vmatbasic.md) | One physical receiver; Java-style trim, at most ten UTF-16 units (empty allowed) and 20 UTF-8 bytes |

```yaml
action: adjustable_bed.rename
data:
  device_id: YOUR_DEVICE_ID
  name: Bedroom
```

The released `linak_rename`, `logicdata_rename` and `jiecang_rename` names
still work, with their original name checks.

### `sync_clock`

Set each targeted controller's clock to Home Assistant's local time. Supported
by the [Malouf Base / Lucid Base](beds/malouf-app.md) app profile on its OKIN
transports, [SIMMONS](beds/simmons.md#alarms-and-clock), and
[Customatic Z-Series](beds/customatic-z-series.md) controllers whose
manufacturer string enables the alarm page (see
[`zseries_set_alarm`](#zseries_set_alarm)). Z-Series beds cannot share a call
with other profiles. The released `malouf_sync_clock` name still works.

## Bed-Specific Actions

These actions also accept optional paired-bed `side` targeting. Use the linked
guide for controller requirements, parameter ranges, and examples. Held
controls, Bluetooth rename and clock synchronization use the
[generic actions](#held-controls-rename-and-clock) above. App-based
profiles must match the actual product; do not substitute another profile to
enable additional commands.

| Controller/profile | Actions | Guide |
|--------------------|---------|-------|
| Linak Bed Control | `linak_move_simultaneously`, `linak_set_alarm` | [Linak](beds/linak.md) |
| Jensen JMC400 | `linak_move_simultaneously` (back and legs only; the action keeps its original name) | [Jensen](beds/jensen.md) |
| Solace MotionFlex | `solace_audio`, `solace_set_alarm` | [Solace](beds/solace.md) |
| Solace Woosa Sleep | `solace_set_alarm` (sound `none` or `alarm`, no music) | [Woosa](beds/woosa.md) |
| Leggett Okin app profiles | `leggett_sleep_timer`, `leggett_alarm_timer` | [Prodigy / U Series](beds/leggett-okin.md) |
| Customatic Clarity / Remedy | `customatic_hold_memory` (all 31 memory combinations), `customatic_move_simultaneously` (safe motor combinations) | [Customatic](beds/customatic.md) |
| Customatic Jerome's C | `customatic_move_simultaneously` (back and legs) | [Customatic](beds/customatic.md) |
| Customatic Z-Series app | `zseries_set_alarm` | [Z-Series](beds/customatic-z-series.md) |
| SIMMONS app | `simmons_set_alarm` | [SIMMONS](beds/simmons.md) |
| LOGICDATA app profiles | `logicdata_set_alarm`, `logicdata_hold_preset` | [LOGICDATA](beds/logicdata-app.md) |
| LOGICDATA Sleep Smart app | `logicdata_hold_preset` (flat, zero gravity, anti-snore, memory 1) | [Sleep Smart](beds/logicdata-sleep-smart.md) |
| Jiecang app profiles | `jiecang_set_alarm`, `jiecang_wake`, `jiecang_stop_wake` | [Jiecang](beds/jiecang-app.md) |
| Richmat RMControl products | `rmcontrol_alarm`, `rmcontrol_anti_snore` | [RMControl](beds/rmcontrol.md) |
| Richmat app profiles | `richmat_mh_alarm`, `richmat_mh_aroma`, `richmat_mh_waist_alarm`, `richmat_mh_light_color` | [Richmat app profiles](beds/richmat-mh.md#actions) |
| Sleep Number Fuzion / BAM-MCR | `sleep_number_command` | [Command and parameter reference](beds/sleep-number-services.md) |

Controller alarm actions program the bed itself, rather than creating a Home
Assistant automation.

### `richmat_mh_alarm`, `richmat_mh_aroma`, `richmat_mh_waist_alarm` and `richmat_mh_light_color`

For the explicit Richmat app profiles. Each action checks every targeted bed before writing any of them and runs through the configuration lane without stopping motion.

- `richmat_mh_alarm` takes `device_id`, `enabled`, `time` (local, minute precision, required when enabling), `position` and `massage` choices listed on the model's alarm page, `slot` (1–3, required on three-slot models) and optional `side`. The bed receives the minutes until the next occurrence of `time` (a time equal to now means 24 hours). A position with a massage sends the app's combined opcode, two massages become head-and-foot, and a combination the app cannot express is rejected. Disabling sends the app's cancel frames, or deletes the chosen slot.
- `richmat_mh_aroma` takes `mode2_startup_minutes` and `mode3_startup_minutes` (1–60) and `mode3_pause_hours` (1–12) and sends the app's three timing frames 150 ms apart. It is available when the model's aroma page is shown.
- `richmat_mh_waist_alarm` takes `waist_side` (`left`, `right`, `both`), `enabled`, `time`, `repeat` (`once`, `daily`) and `intensity` (1–3). Saving sends Home Assistant's current local time with the alarm, as the app does; disabling cancels that side.
- `richmat_mh_light_color` takes `rgb_color` and writes the LED or button-light page's colour frame. Models whose motor page has no light toggle have no on/off command, so they get no Home Assistant light and set the colour with this action.

Alarm countdowns and the waist alarm's current time are read for each bed just before its frames are built, after any reconnect.

### `zseries_set_alarm`

Available only when the controller's Device Information manufacturer string is exactly `CST13` or `CST14`; that string is what makes the app show its alarm page. The last successful read is stored with the entry; if it has never been read, the action reads it on the live connection first. Every targeted bed or side is checked before any of them is written, so one ineligible or unreadable bed fails the whole call without changes. `zseries_set_alarm` takes `device_id`, `enabled`, `time` (minute precision, Home Assistant time zone) and `wake_mode` (`massage` or `memory_1`), both required when enabling, and optional `side`. Like the app, it targets today's weekday, or tomorrow's when the time has already passed; there is no weekday choice. It first sends the clock, then the alarm frame, then two status queries. The app separates the clock and alarm frames by a user tap; HA sends them back-to-back. [`sync_clock`](#sync_clock) sends the clock frame and the same queries. Alarm replies update the **App alarm state** sensor.

### `simmons_set_alarm`

Accepts `device_id`, `slot` (1 or 2), `enabled`, `time`, `weekdays` (empty for the next occurrence), `mode` (`custom_mode`, `flat`, or regular-bed `anti_snore`), `confirm_custom_mode` and optional `side`. Custom Mode requires `confirm_custom_mode: true`. An enabled alarm cannot share its time or mode with the other enabled alarm. Both alarm records must be reported on the current connection; HA queries the bed and refuses the call, writing nothing, if it does not answer. With several beds, every bed is checked before any bed is programmed, so one failing bed changes none. See [SIMMONS alarms](beds/simmons.md#alarms-and-clock).

## Support Bundle

`generate_support_bundle` captures configuration, connection and pairing
evidence, GATT data, notifications, nearby advertisements, and recent command
trace. `capture_duration` is 10–300 seconds (default 120); `include_logs` defaults
to `true`. Provide exactly one configured `device_id` or raw `target_address`.
Logs include recent in-memory HA Bluetooth records and live Bluetooth messages
from reachable ESPHome proxies, plus the latest setup/pairing attempt for the
target address when available. A disk log file is not required. Debug logging
is enabled temporarily during both setup/pairing and bundle capture, then the
previous levels are restored. The action is available once the integration's
setup flow starts, even before a bed entry is created.

See [Getting Help](GETTING_HELP.md) for the capture procedure, privacy details,
and how to download the report.

### FurniMove app controls

The [FurniMove guide](beds/furnimove.md#controls-and-actions) describes
`furnimove_action`, `furnimove_move_simultaneously`, `furnimove_massage_program`
and `furnimove_massage_duration`; renaming uses [`rename`](#rename). Every
action takes `device_id` and optional `side`; rename targets one physical
receiver.
Ordered action indexes come from diagnostics and the selected handset.
Hold overrides accept 0.1–60 seconds; widgets use their separate fixed timing.
All targets validate before movement starts. The advisory massage duration is
local state, sends no timer packet and does not stop the receiver on expiry.

## Motion Bed app actions

The [Motion Bed action index](beds/motion_bed.md#actions) covers all 12 typed app actions, including alarms, sleep calibration/reporting, hub modules, pressure, thermal schedules and audio. Named action keys are listed in controller diagnostics. Persistent changes require confirmation; every target is validated before writes, and native paired child targets retain their side.
### Svane Remote held controls

[`hold_control`](#hold_control) holds a selected Svane head/feet axis or combination for `duration` seconds (0.1–60). Feet-only actions and P1 combinations require more than 0.1 seconds to allow the source's 100 ms feet delay; shorter requests are rejected before any target moves. If awaited delivery consumes the remaining budget before feet start, the action fails explicitly and releases any started axis. The `light_adjust` control runs the app's triangular lamp preference loop after the source's 200 ms threshold. All physical targets are checked before movement.

`svane_release_axis` accepts `motor: head` or `motor: feet` during that hold and signals its serialized writer. The remaining axis continues; final release uses the profile's actual STOP. Both actions accept the normal `device_id` and paired `side` fields. The literal Svane position, Read/TV, toggle and refresh buttons, local intensity number and diagnostic records are described in the [profile guide](beds/svane.md).


## Limoss Remote app

The explicit [Limoss Remote app profile](beds/limoss-remote.md) adds `limoss_remote_rename_memory`, `limoss_remote_calibrate` and `limoss_remote_features`, and supports [`hold_control`](#hold_control) and `goto_preset` with an optional recall `duration`. Holds accept 0.1–60 seconds. Calibration requires `confirmed: true`. Memory actions accept slots 1–8 within the live capacity; `save_preset` and `goto_preset` expose the same local slots. Rename permits an empty name. All selected targets are validated before writes; paired child targets and `side` retain their physical-target settings.

### FSM Relax app actions

[`hold_control`](#hold_control) accepts a supported `command_XX` and explicit
`duration` in seconds. `goto_preset` accepts local `preset` 1–8 and an optional
`duration`; `fsm_relax_calibrate` requires `confirmed: true` and makes one
write attempt.
Native Save/Memory buttons and generic memory actions expose up to eight slots
subject to the reported count. All actions use the serialized coordinator path.
Duration is local gesture policy and replies cannot prove physical arrival.
See [FSM Relax](beds/fsm_relax.md) for profile gates and reply ambiguity.

### `starcode_move_lifts`

Controls the accessories configured on an AdjustableM5X5 main entry. Choose one main `device_id` and `action`: `up`, `down`, `flat` or `stop`. Movement preflights every selected address and interrupts the conflicting main. `flat` interrupts the selected group, sends main flat, waits 1600 ms and sends lift flat. STOP, unloading or a changed selection cancels the retained delay. If a member fails, every admitted target receives cleanup. The action supports one main plus up to three distinct lifts and never fans out lighting, massage or programming.

```yaml
action: adjustable_bed.starcode_move_lifts
data:
  device_id: YOUR_MAIN_DEVICE_ID
  action: flat
```

Main controls also expose Ascent/TV, Zero Gravity, Anti-Snore, Lounge, two memory slots, three named-save buttons and reset. Programming sends 55 attempts and reports transport completion, not proof that firmware retained the setting. RGB palette indices and brightness use controller-declared select/number entities. Alarm, sound/EQ, sonic and kneading feedback are read-only.
