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

Use `adjustable_bed.malouf_sync_clock` with `device_id` to synchronize the
clock separately. Both actions serialize configuration with other commands
without cancelling active movement. Hardware behavior remains unverified.

## Movement and Memory

| Action | Required fields besides `device_id` | Behavior |
|--------|------------------------------------|----------|
| `goto_preset` | `preset` | Recall a memory slot, 1–6 where supported |
| `save_preset` | `preset` | Overwrite a supported memory slot with the current position |
| `stop_all` | None | Cancel pending/active movement and perform the controller's STOP or release cleanup |
| `set_position` | `motor`, `position` | Move one supported axis to a target |
| `set_positions` | `positions` | Validate all motor targets before starting an ordered multi-motor request |
| `timed_move` | `motor`, `direction`, `duration_ms` | Move up/down for an elapsed movement ceiling of 100–30000 ms |

The maximum memory slot depends on the bed; accepting numbers up to 6 does not
create extra hardware memory. Named presets such as Flat or Zero G are exposed
as buttons where supported. `save_preset` changes memory stored on the bed.

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

## Bed-Specific Actions

These actions also accept optional paired-bed `side` targeting. Use the linked
guide for controller requirements, parameter ranges, and examples. App-based
profiles must match the actual product; do not substitute another profile to
enable additional commands.

| Controller/profile | Actions | Guide |
|--------------------|---------|-------|
| Linak Bed Control | `linak_move_simultaneously`, `linak_rename`, `linak_set_alarm` | [Linak](beds/linak.md) |
| Jensen JMC400 | `linak_move_simultaneously` (back and legs only; the action keeps its original name) | [Jensen](beds/jensen.md) |
| Solace MotionFlex | `solace_audio`, `solace_set_alarm` | [Solace](beds/solace.md) |
| Solace Woosa Sleep | `solace_set_alarm` (sound `none` or `alarm`, no music) | [Woosa](beds/woosa.md) |
| Leggett Okin app profiles | `leggett_sleep_timer`, `leggett_alarm_timer`, `leggett_hold_control` | [Prodigy / U Series](beds/leggett-okin.md) |
| Customatic Clarity / Remedy | `customatic_hold_memory` (all 31 memory combinations), `customatic_move_simultaneously` (safe motor combinations) | [Customatic](beds/customatic.md) |
| Customatic Jerome's C | `customatic_move_simultaneously` (back and legs) | [Customatic](beds/customatic.md) |
| Jordan's Serenity app | `serenity_hold_control` (one of 31 literal app actions) | [Serenity](beds/serenity.md) |
| AdjustableM5X4 app | `starcode_abm5_4_hold_control` (literal held movement, preset, save or massage controls) | [AdjustableM5X4](beds/starcode-abm5-4.md) |
| Caresse / Werkmeister apps | `vibradorm_hold_control` (profile-specific movement, memory recall or sync) | [Caresse / Werkmeister](beds/vibradorm_app.md) |
| V-MAT Basic app | `vmatbasic_hold_control`, `vmatbasic_rename` | [V-MAT Basic](beds/vmatbasic.md) |
| LOGICDATA app profiles | `logicdata_set_alarm`, `logicdata_rename`, `logicdata_hold_preset` | [LOGICDATA](beds/logicdata-app.md) |
| Jiecang app profiles | `jiecang_set_alarm`, `jiecang_wake`, `jiecang_stop_wake`, `jiecang_rename` | [Jiecang](beds/jiecang-app.md) |
| Richmat RMControl products | `rmcontrol_alarm`, `rmcontrol_anti_snore` | [RMControl](beds/rmcontrol.md) |
| Sleep Number Fuzion / BAM-MCR | `sleep_number_command` | [Command and parameter reference](beds/sleep-number-services.md) |

Controller alarm actions program the bed itself, rather than creating a Home
Assistant automation. Rename actions change the controller's Bluetooth name;
renaming an HA entity or device is a separate operation.

### `serenity_hold_control`

Hold one literal control from the explicit Jordan's Serenity profile for `duration` seconds (0.1–60), then send its two-frame release sequence. Supply `device_id`, `control`, `duration` and optional `side`. The [Serenity control catalog](beds/serenity.md#reachable-commands) lists the literal action names. The controller validates supported action names before dispatch; arbitrary combinations are rejected. Save controls can change stored positions. This action uses all-target capability preflight and the shared command lock.

### `vibradorm_hold_control`

Supply `device_id`, `control`, `duration` in seconds (0.1–60), and optional
`side`. Every target is checked against its explicit app and remote profile
before dispatch. Supported controls include its motor directions, all-up and
all-down, memory recall slots, and Werkmeister four-axis sync. All-down is a
held direction, not an automatic flat preset. Ordinary movement and recall
buttons use a bounded one-second hold; this action lets an automation choose
the hold duration. Both paths retain the app's completion-gated refresh and
send a fresh release command on completion or cancellation. Memory storage
uses the separate Save memory buttons, not this action.

### `vmatbasic_hold_control` and `vmatbasic_rename`

Hold accepts `device_id`, `control`, `duration` (0.1–60 seconds in whole milliseconds), and optional `side`. Controls are `all_up`, `all_down`, `back_up`, `back_down`, `legs_up`, `legs_down`, and XT-only `floor_hold`. Admitted movement ends with a fresh `ff` release; floor hold ends its refresh without an invented release. Movement on both sides requires two concurrently ready physical receivers. Floor hold targets one physical receiver only.

Rename accepts `device_id`, `name`, and optional `side`, for one physical receiver. It applies Java-style trim and the ten UTF-16-unit limit, including empty names, with a 20-byte UTF-8 safety limit. The retained name changes only after a successful write. Other floor, mood and massage controls use their named child buttons/selects/numbers; accessory commands do not automatically mirror across linked receivers.

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
`furnimove_action`, `furnimove_move_simultaneously`, `furnimove_massage_program`,
`furnimove_massage_duration` and `furnimove_rename`. Every action takes
`device_id` and optional `side`; rename targets one physical receiver.
Ordered action indexes come from diagnostics and the selected handset.
Hold overrides accept 0.1–60 seconds; widgets use their separate fixed timing.
All targets validate before movement starts. The advisory massage duration is
local state, sends no timer packet and does not stop the receiver on expiry.

### `starcode_abm5_4_hold_control`

Hold one exact app action. Flat runs 600 ms; save and reset run the six-second local confirmation interval. No device acknowledgement is inferred.

Target one or more physical devices with `device_id`, an exact supported `control`, `duration` in seconds (0.1–60), and optional paired `side`. Every target’s profile and observed-state gate is checked before any write. Movement and memory refresh every 100 ms with immediate STOP; presets release according to the retained UI selector. Flat runs 600 ms after activation; save/reset stream through the six-second local confirmation interval regardless of the duration field. Positive massage controls require observed active state; this profile has no massage timer Off command. [The protocol document](beds/starcode-abm5-4.md) lists all controls, exact capability gates and exclusions.

### Svane Remote held controls

`svane_hold_control` holds a selected head/feet axis or combination for `duration` seconds (0.1–60). Feet-only actions and P1 combinations require more than 0.1 seconds to allow the source's 100 ms feet delay; shorter requests are rejected before any target moves. If awaited delivery consumes the remaining budget before feet start, the action fails explicitly and releases any started axis. Its literal dropdown also offers `light_adjust`, which runs the app's triangular lamp preference loop after the source's 200 ms threshold. All physical targets are checked before movement.

`svane_release_axis` accepts `motor: head` or `motor: feet` during that hold and signals its serialized writer. The remaining axis continues; final release uses the profile's actual STOP. Both actions accept the normal `device_id` and paired `side` fields. The literal Svane position, Read/TV, toggle and refresh buttons, local intensity number and diagnostic records are described in the [profile guide](beds/svane.md).
