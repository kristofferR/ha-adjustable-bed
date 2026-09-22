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
| Solace MotionFlex | `solace_audio`, `solace_set_alarm` | [Solace](beds/solace.md) |
| Leggett Okin app profiles | `leggett_sleep_timer`, `leggett_alarm_timer`, `leggett_hold_control` | [Prodigy / U Series](beds/leggett-okin.md) |
| LOGICDATA app profiles | `logicdata_set_alarm`, `logicdata_rename`, `logicdata_hold_preset` | [LOGICDATA](beds/logicdata-app.md) |
| Jiecang app profiles | `jiecang_set_alarm`, `jiecang_wake`, `jiecang_stop_wake`, `jiecang_rename` | [Jiecang](beds/jiecang-app.md) |
| Richmat RMControl products | `rmcontrol_alarm`, `rmcontrol_anti_snore` | [RMControl](beds/rmcontrol.md) |
| Sleep Number Fuzion / BAM-MCR | `sleep_number_command` | [Command and parameter reference](beds/sleep-number-services.md) |

Controller alarm actions program the bed itself, rather than creating a Home
Assistant automation. Rename actions change the controller's Bluetooth name;
renaming an HA entity or device is a separate operation.

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
