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

## BedTech app

`bedtech_app_command` uses the selected [BedTech 7.1.3 model](beds/richmat.md#bedtech)
and its sleeper routing. Each receiver must use the same explicit model.
`action` names a control from that model's ordinary screen, such as `headUp`,
`footDown`, `headMassageUp`, `massageTimer20`, `presetFlat`, `memory1Save` or
`lightToggle`. A normal movement action uses the finite pulse count; use
`timed_move` for an elapsed duration or renewable hold. `connectionTest` explicitly
raises the first head for two seconds and returns the link through HA's normal
connection handoff. Automatic setup never moves the bed. Unsupported model or
secondary-head actions fail before any receiver is commanded.

| `sleeper` | Normal two-receiver model | FH single-receiver model |
|---|---|---|
| `1` / `2` | First / second receiver | Unmodified first-head action |
| `3` (default) | Both receivers | Both heads; other controls retain bank 0 |
| `4` / `5` | First / second head; foot actions and STOP reach both receivers | First / second head; shared foot, memory and massage stay in bank 0 |

Target the paired parent for shared-foot operation. A child target or optional
`side` restricts the request; conflicting app sleeper routing is rejected.
An unpaired FH receiver can also select its bank with `sleeper`.

```yaml
action: adjustable_bed.bedtech_app_command
data:
  device_id: YOUR_PAIRED_BED_DEVICE_ID
  action: footUp
  sleeper: 4
```

This example raises both foot sections while selecting the first head for
head actions. `stop` cancels refresh and writes no movement STOP packet on
explicit models. Their massage-off packet is a separate action. Hardware
behavior for these explicit app profiles remains unverified.

## OKIN SleepEase / DoubleSleep

`doublesleep_configure` accepts a bed `device_id` and optional paired target
`side`. Its `action` selects alarm setup, anti-snore apply/demo, sensitivity,
day/month report retrieval, named preset programming or MFP capability queries.
The fields and model/driver gates are documented in the
[SleepEase guide](beds/okin-nframe.md#configuration-and-reports).
`report_side` chooses a sensor stream independently of paired-device `side`.
Report sensors retain raw results and typed records for automations.

```yaml
action: adjustable_bed.doublesleep_configure
data:
  device_id: YOUR_BED_DEVICE_ID
  action: report
  report_side: left
  report_kind: day
  date: "2026-11-03"
```

## Sleeptracker Smart Bed

These actions require the separate [Sleeptracker framed-JSON processor](beds/sleeptracker.md).
They reject Adjustable Lite UART entries and validate every selected layout
before the first write. All accept `device_id` and optional paired-device `side`.
ActiveBreeze `fan_side` separately chooses the processor's fan fields.

| Action | Fields besides `device_id` | Behavior |
|--------|---------------------------|----------|
| `sleeptracker_preset` | `preset`; optional `save: false` | Recall `all_flat`, `zero_g`, `anti_snore`, `user_favorite`, `tv_pc` or `favorite_2`, subject to layout. `save: true` programs a supported preset; Flat is recall only. Processor types 5–7 reject saving. |
| `sleeptracker_climate` | `mode: heat` or `cool`, `level: 0`–`3`; optional `fan_side: both`, `constant: true` | ActiveBreeze only. Level 0 turns the selected fan off. Heat sends a fixed 3600-second timer, cool 36000 seconds; timers are not configurable. |
| `sleeptracker_wave` | `frequency`; optional `minutes: 30` | Premium layouts: 28, 40, 52, 68 or 88 Hz and 5–105 minutes in steps of five. |
| `sleeptracker_massage` | `action` | `head`, `foot`, `pattern`, `28Hz`, `40Hz` or `off`, subject to layout. `off` uses selected-unit massage stop. |
| `sleeptracker_relaxation` | `action` | Premium layouts: `wind_down_1`, `wind_down_2` or `local_animation`. Local animation contains motor/massage statements only. |

```yaml
action: adjustable_bed.sleeptracker_climate
data:
  device_id: YOUR_PROCESSOR_DEVICE_ID
  fan_side: left
  mode: cool
  level: 2
  constant: false
```

```yaml
action: adjustable_bed.sleeptracker_massage
data:
  device_id: YOUR_PROCESSOR_DEVICE_ID
  action: 40Hz
```

```yaml
action: adjustable_bed.sleeptracker_wave
data:
  device_id: YOUR_PROCESSOR_DEVICE_ID
  frequency: 52
  minutes: 30
```

Use `sleeptracker_massage` with `action: "off"` to stop massage, wave or
wind-down. Use `stop_all` to cancel movement and stop the local motor/massage
animation. Wave duration units, physical side mapping and hardware effects
remain unverified. Last commanded climate timers describe acknowledged writes,
not countdown readback. No service accepts arbitrary JSON, network configuration
or speaker/audio commands.

## Malouf Base / Lucid Base Clock and Alarm

The explicit [app profile](beds/malouf.md#malouf-base--lucid-base-family) exposes clock actions only for
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
| `goto_preset` | `preset` | Recall a supported memory slot, 1–255 where the controller advertises it. Optional `duration` sets the recall hold where supported |
| `save_preset` | `preset` | Overwrite a supported memory slot with the current position |
| `stop_all` | None | Cancel pending/active movement and perform the controller's STOP or release cleanup |
| `set_position` | `motor`, `position` | Move one supported axis to a target |
| `set_positions` | `positions` | Validate all motor targets before starting an ordered multi-motor request |
| `timed_move` | `motor`, `direction`, `duration_ms` | Move up/down for an elapsed movement ceiling of 100–30000 ms |
| `reverie_set_comfort` | `comfort` | Send a typed Reverie composite setting after every selected model validates it |
| `reverie_run_routine` | `steps` | Replace and run the selected target's Reverie Composer queue |
| `reverie_test` | None | Run the selected Reverie protocol's timed diagnostic writes and cleanup |

M1X12 uses `m1x12_part_1`, `m1x12_part_2`, `m1x12_part_4`,
`m1x12_part_8`, and `m1x12_part_16` motor targets. ELEVATE uses
`elevate_actuator_1`, `elevate_actuator_2`, and `elevate_both`.
Each target must be declared by the selected bed's controller.

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

Beds without position feedback can opt in to calibrated travel-time estimates
and saved positions. Their actions (`save_position`, `recall_position`,
`set_position_reference` and others) are described in
[Estimated positions](ESTIMATED_POSITIONS.md#actions).

### Renewable holds

`timed_move` and `hold_control` accept two optional fields, `hold_owner` and
`hold_generation`, that turn the call into a renewable hold on beds whose app
is proven to hold a key until release, by streaming it or by one start frame
and a STOP. Other beds, and controls a bed's app does not hold this way (such
as Good Vibe Sleep's short, long and short-and-long presses), reject the fields
before anything moves, and a call without them behaves exactly as before.

| Field | Meaning |
|-------|---------|
| `hold_owner` | Who holds, for example one card instance (1–64 characters) |
| `hold_generation` | Number of this press. Use a new, higher number for each press |

The call's duration is the lease: 100–30000 ms (`duration_ms`) or 0.1–30
seconds (`duration`). The bed keeps moving while calls naming the same owner,
generation, motor and direction (or control) arrive within the lease. Each
renewal replaces the deadline outright, so a shorter lease shortens the hold.
A renewal writes nothing to the bed and returns at once. When the lease runs
out, the bed sends its usual release or STOP.

A generation ends when its lease expires, when STOP or a replacement move
interrupts it, when the link drops, or when the integration unloads. Calls
naming an ended generation, an older generation, or a different motion under
the same generation are refused, so a late renewal can never restart motion.
Nothing is replayed after a reconnect or restart. One hold never streams
longer than 30 seconds in total, however often it is renewed. Latched beds
(Solace, BedSense, Reverie, Kaidi, iSleep and Remacro) keep moving
after one start frame until STOP arrives, so their holds stop after 10 seconds
in total. A renewable
hold targets one bed or paired bed per call; on a paired bed both sides must
declare the same hold mode, and one renewal renews both sides.

The dashboard card uses this for every press on a bed that supports it: one
call starts the hold, the card renews it every 250 ms with a 750 ms lease, and
releasing the control stops renewing and sends STOP. Hiding the page or
removing the card ends the hold the same way; if that STOP is lost, the bed
still stops when the lease runs out. Entities that can be held this way carry
a `hold_lease_mode` attribute (`stream` or `latched`), and `hold_lease_motor`
names the `timed_move` motor where there is one. A combined control on a paired
bed carries them only when both sides declare the same mode.

```yaml
# Repeat every 250 ms while a button is held; send stop_all on release.
action: adjustable_bed.timed_move
data:
  device_id: abc123
  motor: back
  direction: up
  duration_ms: 750
  hold_owner: bedroom-card
  hold_generation: 42
```

**Physical validation.** Proven offline: scheduler and service tests show that a renewal writes nothing and only moves the deadline,
that expiry runs the bed's own release or STOP once, that STOP, a replacement,
a dropped link or an unload ends the generation, and that a late or stale
renewal never starts motion. Card tests cover the 250 ms renewals and the STOP
on release, hide and removal. Needs real-bed reports, family by family as each
opts in: whether a held motor moves smoothly while renewals arrive through real
adapters and ESPHome proxies, and how long it keeps moving after renewals stop.
The first opt-ins are the Leggett Okin and Customatic profiles of the
[Okin N-frame codec](beds/okin-nframe.md#hold-and-release-timing).

### Reverie composite actions

`reverie_set_comfort` accepts a `comfort` object with optional `head_position`,
`foot_position`, `lumbar_position`, `head_massage`, `foot_massage`, `timer_byte`,
and `mode` fields. Each Reverie protocol and selected model validates its supported fields
and ranges before any selected target writes. Protocol 110 Composer requests
require its five position and strength fields because its app sends one
complete payload. Protocol 108 applies changed position and massage values
after stable notification feedback. Pairlink ordinary requests send only values
changed from accepted state. Its alarm route sends the source-defined complete
eight-write sequence. `timer_byte` is a raw source byte, not a duration in
minutes. Pairlink central writes require the accepted per-target session inputs
and a ready mesh session; local peripheral writes require the separately
configured local role to be ready.

`reverie_run_routine` accepts ordered `steps`, each with an integer
`duration_minutes` and an optional `comfort` object. It replaces the selected
physical target's routine queue. HA automation timing remains the user's
scheduler; this action only runs the bed-specific sequence. Protocol 108 and
Protocol 110 each own a queue and timer per physical address. The STK Composer
route uses its selected V1 facade with numeric side values 1, 2, or 3, which
have no inferred left/right mapping. Pairlink uses its separate routine timing
and replacement behavior: missing comfort settings are skipped, the duration
list is retained independently, missing durations default to one minute, and
durations have a one-minute minimum. Pairlink does not schedule a timer after
its last resolved setting. Other Reverie profiles still require a duration.
The paired-bed `side` field remains the separate Home Assistant left/right/both
target selector.

STOP cancels the selected target's remaining routine steps as well as current
movement. Routines, diagnostics, and Protocol 108 comfort require concurrent
connection mode for two-address pairs using central Bluetooth connections,
including side-only targets. Sequential mode disconnects each receiver before deferred work can
finish. Local Pairlink peripheral transports do not have that restriction.

`reverie_test` starts the accepted Protocol 108 or 110 ten-second bed test and
schedules its matching protocol stop writes. Pairlink's two-second diagnostic
uses the central encrypted route and has the same explicit runtime-input
requirements as other Pairlink sends. The local peripheral profile uses the
selected host adapter's verified address in its advertisement. Its backend is
integration-owned direct BlueZ D-Bus, separate from Home Assistant's managed
client transport. A successful characteristic write does not confirm a
physical response.

Use Home Assistant automations to schedule direct Reverie actions such as
`reverie_set_comfort`, `reverie_run_routine`, `goto_preset`, and `save_preset`.
Phone-local alarm storage, Android notification delivery, and the phone's
alarm scheduler are outside the integration's scope.
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

Card release events apply to the press that started the movement. Releasing an
older direction after STOP does not stop a newer press. Compact card cleanup
retains only targets whose movement service was dispatched; cancelling before
a declared start delay expires does not send an extra cleanup STOP. An explicit
Stop button still stops its selected target immediately.

Hold one control declared by the bed's app profile for `duration` seconds
(0.1–60, whole milliseconds), then send that profile's release sequence. A
control the bed does not declare is rejected with the list of controls the bed
accepts. Save controls can change stored positions. Svane Remote and Limoss
Remote beds validate and release through their own live session, so a single
call cannot mix them with other profiles.

Sleepy's Elite uses selector-supported static controls here. Numeric and select
entities remain separate commit paths. Its accepted palette commits select
codes `1`–`7`, each as one writer attempt without repeat or STOP. Caller timing
for the other dynamic app values remains under source-to-caller reconciliation;
they are not exposed through `hold_control`.

| Profile | Controls | Timing and release |
|---------|----------|--------------------|
| [Sleepy's Elite app](beds/sleepys.md#explicit-sleepys-elite-app-profile) | Selector-supported motor directions and app buttons with hold metadata | 100 ms refresh and that selector's STOP frame at release; duration 100–60000 ms. Motion-sensor actions end after five seconds without an added STOP. BOX25 voice position targets are one-shot. |
| [Glideaway Motion / Montion](beds/keeson.md#glideaway-motion) | Model-specific axes, presets, memories, light and massage controls in the guide | 300 ms refresh, zero-mask release at +300/+600 ms. Maximum 30 seconds; memory recalls below 5 seconds, programming through `save_preset` |
| [Leggett Okin app profiles](beds/okin-nframe.md#leggett-okin-family) | `flat`, `snore`, `lights_toggle`, `massage_toggle`, `massage_wave`, `massage_head_up`, `massage_head_down`, `massage_foot_up`, `massage_foot_down`; U Series adds `memory_1`, `memory_2`, `store` | See the guide. `leggett_hold_control` remains as an alias limited to this list |
| [Jordan's Serenity](beds/okin-nframe.md#reachable-commands) | 31 literal app actions | Two-frame release |
| [Jordan's Tranquil](beds/okin-nframe.md#reachable-commands-1) | 30 literal app actions | Two-frame release |
| [Customatic Z-Series](beds/okin-nframe.md#reachable-commands-2) | Literal Z-230 or Z-280 actions | A Z-230 rejects Z-280-only actions and the reverse |
| [SIMMONS](beds/okin-nframe.md#simmons) | `head_up`, `head_down`, `legs_up`, `legs_down`, `flat`, `memory`, `light`, plus `zero_g`, `tv`, `anti_snore` on a regular bed or `inclined_left`, `inclined_middle`, `inclined_right` on an inclined bed | Frame every 300 ms, then STOP at +100 and +400 ms. Holding `memory` for 5 seconds mirrors the app's Custom Mode save; whether the bed stores it is unverified |
| [AdjustaMattress](beds/keeson.md#adjustamattress) | App action identifiers such as `headUp`, `footDown`, `unionUp`, `neckTiltUp`, `lumbarDown`, `flatPosition`, `zeroGravity`, `m1`, `underbedLighting`, `headStrengthAdd`, `timer10`, subject to the selected model/layout | 200 ms refresh; movement/lift starts at +200 ms. STOP at +200 ms after release. Ordinary P3/P4 massage additionally queries at +400/+600 ms. P2 unsafe prior-frame lighting replay is excluded |
| [Adjustable bed (Lumbar)](beds/okin-nframe.md#timing-and-controls) | `head_up`, `head_down`, `feet_up`, `feet_down`, `lumbar_up`, `lumbar_down`, `flat`, `zero_g`, `lounge`, `incline`, `anti_snore`, `save_zero_g`, `save_lounge`, `save_incline`, `save_anti_snore`, `light`, `wave_1`, `wave_2`, `wave_3`, `massage_up`, `massage_down` | Frame every 100 ms, then STOP immediately and 300 ms later. Whether a save stores the position is unverified |
| [Simon Li / Heal Every Night / OKIN-Seating](beds/keeson.md#simon-li-heal-every-night-and-okin-seating-profiles) | Simon Li: `back_up`, `back_down`, `foot_up`, `foot_down`, `lumbar_up`, `lumbar_down`, `home`, `memory_1`, `memory_2`. OKIN-Seating: `back_up`, `back_down`, `foot_up`, `foot_down`, `home`. Heal Every Night: `head_up`, `head_down`, `foot_up`, `foot_down`, plus `tilt_up`, `tilt_down`, `lumbar_up`, `lumbar_down` on Healing 7 and 8 | Key every 100 ms, then the zero frame 10 ms (Simon Li, OKIN-Seating) or 100 ms (Heal Every Night) later. Holding a Simon Li memory for 2.1 seconds or more is the app's memory save |
| [Restonic BT (Keeson)](beds/keeson.md#restonic-bt-profiles) | Remote A: `head_up`, `head_down`, `feet_up`, `feet_down`, `flat`, `zero_g`. Remote B adds `back_legs_up`, `back_legs_down`, `light`, `zzz` | Directions, remote B's back and legs and remote A's `zero_g` repeat every 100 ms; the others are sent once. One zero frame 100 ms after the hold |
| [INNOVA](beds/keeson.md#innova-profile) | `back_up`, `back_down`, `legs_up`, `legs_down`, `memory_a`, `memory_b`, `memory_timer`, plus `combined_up`/`combined_down` (2M), `lumbar_up`/`lumbar_down` (3M, 4M) and `waist_up`/`waist_down` (4M) | Key every 100 ms, then the zero key 100 ms later |
| [AdjustableM5X4](beds/okin-nframe.md#adjustablem5x4) | Movement, preset, save and massage controls | Movement and memory refresh every 100 ms with immediate STOP. Flat runs 600 ms; save and reset run the six-second confirmation interval regardless of `duration`. Positive massage controls require observed active state. One physical address only |
| [Adjustable Comfort M1X12](beds/starcode-m1x12.md) | Parts 1, 2, 4, 8, 16 and union movement, massage wave/intensity, plus explicit ELEVATE actions | 100 ms held refresh, 0.1–60 seconds, fresh STOP on release/cancellation. The native card invokes one bounded service window and routes STOP to the owning side |
| [Caresse / Werkmeister](beds/vibradorm.md#caresse-and-werkmeister) | Profile motor directions, `all_up`, `all_down`, `memory_1` to `memory_6`, Werkmeister `sync` | Completion-gated refresh, then a fresh release. All-down is a held direction, not a flat preset. Save memory uses the Save buttons |
| [V-MAT Basic](beds/vibradorm.md#v-mat-basic) | `all_up`, `all_down`, `back_up`, `back_down`, `legs_up`, `legs_down`, XT-only `floor_hold` | Movement ends with a fresh `ff` release; both sides need two ready receivers. `floor_hold` ends its refresh without a release and targets one physical receiver |
| [OCTO Smart Control](beds/octo.md) | Advertised motor directions and `memory_1` through the discovered memory count | P1 commands repeat every 350 ms inside each bounded operation, which ends with STOP. The 60-second service maximum is a Home Assistant safety bound; the card starts another bounded call only while the user still holds the control. |
| [Svane Remote](beds/svane.md) | `head_up`, `head_down`, `feet_up`, `feet_down`, the four `head_*_feet_*` combinations, `light_adjust` | See [Svane Remote held controls](#svane-remote-held-controls) |
| [Limoss Remote](beds/limoss.md#limoss-remote) | Controls rendered for the receiver's layout | Five-frame release |
| [FSM Relax](beds/limoss.md#fsm-relax) | `command_XX` values from the profile's protocol diagnostics | Replies cannot prove physical arrival |
| [TiMOTION AHF](beds/timotion-ahf.md) | `control_1_up`/`control_1_down` through `control_5_up`/`control_5_down`, `night`, `light`, `chair` | First 100 ms wait is inside the requested bound; a 100 ms wait separates writes, plus BLE write latency. Release sends three neutral STOP writes. This is bounded HA behavior, not Android timing parity or a firmware maximum |

Customatic Clarity, Remedy and Jerome's C use
[`customatic_hold_memory` and `customatic_move_simultaneously`](beds/okin-nframe.md#customatic-family),
which select their memory and motor combinations as lists.

### `rename`

Write a new Bluetooth name to each targeted controller that supports it. This
does not rename the Home Assistant device or entities. Each controller applies
its app's name rule to every target before any write:

| Profile | Name rule |
|---------|-----------|
| [Linak Bed Control](beds/linak.md) | 1–17 UTF-8 bytes. The controller then disconnects so it can advertise the new name |
| [LOGICDATA app profiles](beds/jiecang.md#logicdata-app-family) | Phone and tablet: 1–255 printable ASCII characters. Sleep Smart [beds](beds/jiecang.md#sleep-smart-air-mattress-bed) and [pumps](beds/logicdata-sleep-smart.md): 1–20 letters, digits, ä, ö, ü or ß |
| [ERGOBALANCE](beds/jiecang.md#ergobalance-dreamask) and [Dream Motion](beds/jiecang.md#dream-motion-dreamotion) | 1–20 ASCII letters or digits |
| [Dream Motion HD](beds/jiecang.md#dream-motion-hd) | 1–20 printable ASCII characters |
| [Comfort Motion app](beds/jiecang.md#comfort-motion-app) | 1–18 ASCII letters, digits, dots or underscores, discovered G1 name role required |
| [INNOVA](beds/keeson.md#innova-profile) | At most 14 characters as typed, then trimmed and non-empty |
| [FurniMove](beds/furnimove.md#controls-and-actions) | One physical receiver; a unique name of at most 18 UTF-16 units after trimming |
| [V-MAT Basic](beds/vibradorm.md#v-mat-basic) | One physical receiver; Java-style trim, at most ten UTF-16 units (empty allowed) and 20 UTF-8 bytes |

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
by the [Malouf Base / Lucid Base](beds/malouf.md#malouf-base--lucid-base-family) app profile on its OKIN
transports, [Glideaway Motion / Montion](beds/keeson.md#alarm-and-clock), [SIMMONS](beds/okin-nframe.md#alarms-and-clock), and
[Customatic Z-Series](beds/okin-nframe.md#customatic-z-series) controllers whose
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
| Sleepy's Elite app | Selector-backed controls are exposed as Home Assistant entities; there is no separate alarm action | [Sleepy's Elite app profile](beds/sleepys.md#explicit-sleepys-elite-app-profile) |
| Linak Bed Control | `linak_move_simultaneously`, `linak_set_alarm` | [Linak](beds/linak.md) |
| Jensen JMC400 | `linak_move_simultaneously` (back and legs only; the action keeps its original name) | [Jensen](beds/jensen.md) |
| Solace MotionFlex | `solace_audio`, `solace_set_alarm` | [Solace](beds/ff_frame.md#solace-name-routes) |
| Solace Woosa Sleep | `solace_set_alarm` (sound `none` or `alarm`, no music) | [Woosa](beds/ff_frame.md#woosa-sleep) |
| Leggett Okin app profiles | `leggett_sleep_timer`, `leggett_alarm_timer` | [Prodigy / U Series](beds/okin-nframe.md#leggett-okin-family) |
| Customatic Clarity / Remedy | `customatic_hold_memory` (all 31 memory combinations), `customatic_move_simultaneously` (safe motor combinations) | [Customatic](beds/okin-nframe.md#customatic-family) |
| Customatic Jerome's C | `customatic_move_simultaneously` (back and legs) | [Customatic](beds/okin-nframe.md#customatic-family) |
| Glideaway Motion / Montion app | `glideaway_set_alarm` | [Glideaway Motion](beds/keeson.md#alarm-and-clock) |
| Customatic Z-Series app | `zseries_set_alarm` | [Z-Series](beds/okin-nframe.md#customatic-z-series) |
| SIMMONS app | `simmons_set_alarm` | [SIMMONS](beds/okin-nframe.md#simmons) |
| LOGICDATA app profiles | `logicdata_set_alarm`, `logicdata_hold_preset` | [LOGICDATA](beds/jiecang.md#motionrelax-phone-and-tablet) |
| LOGICDATA Sleep Smart app | `logicdata_hold_preset` (flat, zero gravity, anti-snore, memory 1) | [Sleep Smart](beds/jiecang.md#sleep-smart-air-mattress-bed) |
| Jiecang app profiles | `jiecang_set_alarm`, `jiecang_wake`, `jiecang_stop_wake` | [Jiecang](beds/jiecang.md#dream-app-family) |
| Comfort Motion app | `jiecang_wake`, `jiecang_stop_wake`; use HA automations for scheduling | [Comfort Motion](beds/jiecang.md#comfort-motion-app) |
| Richmat RMControl products | `rmcontrol_alarm`, `rmcontrol_anti_snore` | [RMControl](beds/richmat.md#rmcontrol) |
| Richmat app profiles | `richmat_mh_alarm`, `richmat_mh_aroma`, `richmat_mh_waist_alarm`, `richmat_mh_light_color` | [Richmat app profiles](beds/richmat.md#richmat-mh-apps) |
| Classic Richmat apps (Avocado Eco Base, CoasterSleep, Forty Winks, Milemont, Superior) | `richmat_classic` ([operations](#classic-richmat-app-settings)) | [Classic Richmat apps](beds/richmat.md#classic-richmat-apps) |
| Sleep Number Fuzion / BAM-MCR | `sleep_number_command` | [Command and parameter reference](beds/sleep-number-services.md) |
| MotoMotion app | `motomotion` (local users and postures: save, select, delete, recall, reset and fine-tune) | [MotoMotion](beds/motomotion.md) |

Controller alarm actions program the bed itself, rather than creating a Home
Assistant automation.

### `richmat_mh_alarm`, `richmat_mh_aroma`, `richmat_mh_waist_alarm` and `richmat_mh_light_color`

For the explicit Richmat app profiles. Each action checks every targeted bed before writing any of them and runs through the configuration lane without stopping motion.

- `richmat_mh_alarm` takes `device_id`, `enabled`, `time` (local, minute precision, required when enabling), `position` and `massage` choices listed on the model's alarm page, `slot` (1–3, required on three-slot models) and optional `side`. The bed receives the minutes until the next occurrence of `time` (a time equal to now means 24 hours). A position with a massage sends the app's combined opcode, two massages become head-and-foot, and a combination the app cannot express is rejected. Disabling sends the app's cancel frames, or deletes the chosen slot.
- `richmat_mh_aroma` takes `mode2_startup_minutes` and `mode3_startup_minutes` (1–60) and `mode3_pause_hours` (1–12) and sends the app's three timing frames 150 ms apart. It is available when the model's aroma page is shown.
- `richmat_mh_waist_alarm` takes `waist_side` (`left`, `right`, `both`), `enabled`, `time`, `repeat` (`once`, `daily`) and `intensity` (1–3). Saving sends Home Assistant's current local time with the alarm, as the app does; disabling cancels that side.
- `richmat_mh_light_color` takes `rgb_color` and writes the LED or button-light page's colour frame. Models whose motor page has no light toggle have no on/off command, so they get no Home Assistant light and set the colour with this action.

Alarm countdowns and the waist alarm's current time are read for each bed just before its frames are built, after any reconnect.

### `glideaway_set_alarm`

For the explicit MOTION 400/450/500/600 profiles. Accepts `device_id`, `enabled`,
`time` (minute precision, required when enabling), `wake_mode` (`none`,
`memory_1`, `memory_2`, default `none`) and optional `side`. Sends HA local RTC,
then the alarm 300 ms later. Time is the wire 24-hour value; the app sends one
hour below its 1–12 wheel label. The app's unusual automatic weekday rule and
RTC offsets are preserved. Read the [calendar details](beds/keeson.md#alarm-and-clock)
before use. `sync_clock` sends only RTC; Refresh alarm queries twice, 200 ms apart.
Alarm state is reported by a sensor. Hardware semantics remain unverified.

### `zseries_set_alarm`

Available only when the controller's Device Information manufacturer string is exactly `CST13` or `CST14`; that string is what makes the app show its alarm page. The last successful read is stored with the entry; if it has never been read, the action reads it on the live connection first. Every targeted bed or side is checked before any of them is written, so one ineligible or unreadable bed fails the whole call without changes. `zseries_set_alarm` takes `device_id`, `enabled`, `time` (minute precision, Home Assistant time zone) and `wake_mode` (`massage` or `memory_1`), both required when enabling, and optional `side`. Like the app, it targets today's weekday, or tomorrow's when the time has already passed; there is no weekday choice. It first sends the clock, then the alarm frame, then two status queries. The app separates the clock and alarm frames by a user tap; HA sends them back-to-back. [`sync_clock`](#sync_clock) sends the clock frame and the same queries. Alarm replies update the **App alarm state** sensor.

### `simmons_set_alarm`

Accepts `device_id`, `slot` (1 or 2), `enabled`, `time`, `weekdays` (empty for the next occurrence), `mode` (`custom_mode`, `flat`, or regular-bed `anti_snore`), `confirm_custom_mode` and optional `side`. Custom Mode requires `confirm_custom_mode: true`. An enabled alarm cannot share its time or mode with the other enabled alarm. Both alarm records must be reported on the current connection; HA queries the bed and refuses the call, writing nothing, if it does not answer. With several beds, every bed is checked before any bed is programmed, so one failing bed changes none. See [SIMMONS alarms](beds/okin-nframe.md#alarms-and-clock).

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

The [Motion Bed action index](beds/ff_frame.md#services-2) covers all 12 typed app actions, including alarms, sleep calibration/reporting, hub modules, pressure, thermal schedules and audio. Named action keys are listed in controller diagnostics. Persistent changes require confirmation; every target is validated before writes, and native paired child targets retain their side.
### Svane Remote held controls

[`hold_control`](#hold_control) holds a selected Svane head/feet axis or combination for `duration` seconds (0.1–60). Feet-only actions and P1 combinations require more than 0.1 seconds to allow the source's 100 ms feet delay; shorter requests are rejected before any target moves. If awaited delivery consumes the remaining budget before feet start, the action fails explicitly and releases any started axis. The `light_adjust` control runs the app's triangular lamp preference loop after the source's 200 ms threshold. All physical targets are checked before movement.

`svane_release_axis` accepts `motor: head` or `motor: feet` during that hold and signals its serialized writer. The remaining axis continues; final release uses the profile's actual STOP. Both actions accept the normal `device_id` and paired `side` fields. The literal Svane position, Read/TV, toggle and refresh buttons, local intensity number and diagnostic records are described in the [profile guide](beds/svane.md).


## Limoss Remote app

The explicit [Limoss Remote app profile](beds/limoss.md#limoss-remote) adds `limoss_remote_rename_memory`, `limoss_remote_calibrate` and `limoss_remote_features`, and supports [`hold_control`](#hold_control) and `goto_preset` with an optional recall `duration`. Holds accept 0.1–60 seconds. Calibration requires `confirmed: true`. Memory actions accept slots 1–8 within the live capacity; `save_preset` and `goto_preset` expose the same local slots. Rename permits an empty name. All selected targets are validated before writes; paired child targets and `side` retain their physical-target settings.

### FSM Relax app actions

[`hold_control`](#hold_control) accepts a supported `command_XX` and explicit
`duration` in seconds. `goto_preset` accepts local `preset` 1–255, subject to the
selected controller's live capacity, and an optional
`duration`; `fsm_relax_calibrate` requires `confirmed: true` and makes one
write attempt.
Native Save/Memory buttons and generic memory actions expose up to eight slots
subject to the reported count. All actions use the serialized coordinator path.
Duration is local gesture policy and replies cannot prove physical arrival.
See [FSM Relax](beds/limoss.md#fsm-relax) for profile gates and reply ambiguity.

### `starcode_move_lifts`

Controls accessories configured on an AdjustableM5X5 or Adjustable Comfort M1X12 main entry. AdjustableM5X5 retains its one-main-plus-three-lifts limit and accepts its existing member types. M1X12 accepts up to two distinct ELEVATE entries explicitly configured with the M1X12 variant. Choose one main `device_id` and `action`: `up`, `down`, `flat` or `stop`. Movement preflights every selected address and interrupts the conflicting main. `flat` interrupts the selected group, sends main flat, waits 1600 ms and sends lift flat. STOP, unloading or a changed selection cancels the retained delay. If a member fails, every admitted target receives cleanup. The action never fans out lighting, massage or programming.

```yaml
action: adjustable_bed.starcode_move_lifts
data:
  device_id: YOUR_MAIN_DEVICE_ID
  action: flat
```

Main controls also expose Ascent/TV, Zero Gravity, Anti-Snore, Lounge, two memory slots, three named-save buttons and reset. Programming sends 55 attempts and reports transport completion, not proof that firmware retained the setting. RGB palette indices and brightness use controller-declared select/number entities. Alarm, sound/EQ, sonic and kneading feedback are read-only.

### `configure_alarm_schedule`

Writes whole weekly and one-time tables for the explicit Tempur Curve, Q-Plus
Adjustable Remote, Omazz Adjusto III, Ergomotion, ROW Control, Ergo Slim and
TEMPUR AU app profiles. Serta MP Remote has no accepted table writer and is
unavailable for this action. `supports_alarm` alone never grants this contract.

```yaml
action: adjustable_bed.configure_alarm_schedule
data:
  device_id: YOUR_DEVICE_ID
  weekly:
    - enabled: true
      wake: true
      hour: 7
      minute: 30
      weekdays: [0, 1, 2, 3, 4]
  one_time: []
  dispatch: weekly
```

Both lists are required and may be empty. `dispatch` is required and is `both`,
`weekly`, or `one_time`. Records default to `enabled: false`, `wake: false`,
`hour: 0`, `minute: 0`. Hours are 0..23 and minutes 0..59. Weekly days are unique
integers, Monday 0 through Sunday 6; an enabled weekly record requires a day.
Each table permits at most three enabled records. Disabled rows consume no
slots; an enabled `wake: false` row does consume a slot.

An enabled one-time record must be later today in Home Assistant's local
timezone. The action captures one reference time and reuses it for every
physical target and serialization. Equal/past times, nonexistent DST times and
ambiguous DST times are rejected before any write. There is no next-day
rollover. Absolute target/reference timestamps first use Java Date millisecond
precision. Their positive millisecond difference then uses integer division
for relative hour/minute/second fields; zero bytes do not establish firmware clearing.

Both complete tables, including the unselected table, and every physical
target must pass validation before checksums or writes. Fourth rows, source
partial-overflow corruption and negative deltas are rejected. `both` sends
weekly first, waits 500 ms, then sends one-time; single-table dispatch retains
500 ms post-write pacing. Configuration uses the existing command lock and
scheduler with `cancel_running: false`. Native child targets and optional
`side` retain their existing routing and conflict checks.

Empty tables attempt empty-table writes; clearing firmware is unverified. A
transport failure may leave one table sent and the other unsent. There is no
wire rollback. Phone alarm schedulers, local audio, permissions and snooze UI
storage are outside this BLE action. Normalize any automation's hour/minute
arithmetic first, reject cross-date results, and preserve its intended weekly
or one-time dispatch. See each [app guide](beds/keeson.md#keeson-layout-app-family)
for exact weekday-marker, wake-byte, notification and release differences.

## Comfort Enhancements alarm

`adjustable_bed.comfort_enhancements_set_alarm` programs or disables the app's
current-day BLE alarm. Supply `device_id`, `enabled`, and `time: "06:45:00"`
when enabling. Optional `memory` is 0 (none), 1 (A/single Memory), or 2 (B,
MC2/MC3 only); `massage` defaults to false. Paired `side` routing is supported.
Disable with `enabled: false`, without a time. `adjustable_bed.sync_clock`
synchronizes the clock and sends the app query. There is no alarm feedback or
phone scheduler. See [packet behavior and limits](beds/keeson.md#clock-and-alarm).
### Floyd Home actions

`adjustable_bed.floyd_action` exposes confirmed `save_zero_g`,
`save_anti_snore`, unassigned BLE `assign_room` / `confirm_add`, and preset
recall with explicit conditional `internal_side` selection. All controls use
normal `device_id` and paired physical `side` routing. See the
[Floyd action table](beds/kaidi.md#floyd-action) before programming a
preset or assigning membership. Combined movement uses `hold_control` with
`head_feet_up` or `head_feet_down` and a duration up to 30 seconds. HA automations
schedule these presets; the app's phone alarms are not on-bed alarm storage.

### BF and Cherish bed alarms

`adjustable_bed.bf_cherish_set_alarm` accepts `device_id`, `enabled`, optional
`side`, `time` (required when enabling, minute precision), and `memory` (`none`,
`memory_1`, `memory_2`, default `none`). The clock uses HA local time. All
targets must be BF or Cherish profiles. [Profile details and example](beds/keeson.md#alarm-action)
cover distinct packet formats, retained intent and report limitations.

### Casper Base

`adjustable_bed.casper_base` provides capability-validated alarm, light, automatic
external-detector, sleep sensor and remote-finder operations. Select a `device_id`
and `operation`; paired targets are validated together before sending commands.
The [Casper Base guide](beds/casper-base.md#configuration-actions) lists each
operation's fields and the separate sensor/remote entry types.

### GM Control

`adjustable_bed.gmmotor` runs finite, product-admitted Bluetooth operations.
Choose `device_id` and `operation`, with optional paired `side`. Every selected
target is validated before its operation is scheduled. Named product controls
use their button or `hold_control`; no raw-write action is exposed.

The [GM Control command reference](beds/gmmotor.md#specialized-actions) lists
clock/countdown/repeat alarm, RGB/timeout, anti-snore, bottom massage timer and
sleep-name operations. The state sensor's `gmmotor_alarm_choices` attribute lists
the exact accepted `mode` names for that product. Countdown alarms use `value`
in minutes, or `alarm_at` with local `hour`/`minute`. Repeat records use `slot`,
`repeat`, `hour`, `minute`, `mode`, `status`. Clock and light menus require their
source capability replies.

Independent MM/SXB entries expose `sensor_time`, `sensor_part`,
`sensor_query_part`, `sensor_live`, `sensor_report`, `sensor_stop`, and the
SXB-only `sensor_sensitivity` query. Device-part setting uses `value` (MM 1/2,
SXB 11/12/13). Reports use `part` (1 left, 2 right), `report_type` (1 day, 2 month)
and optional `report_date`. Live polling uses `enabled`. Local stop sends no
hardware STOP. The [sleep-module reference](beds/gmmotor.md#sleep-modules) records
the distinct wire builders and raw-data limitations.

### HJBed configuration

`adjustable_bed.hjbed` exposes product-gated single/repeat alarms, alarm query/delete/toggle, clock synchronization, light timeout/RGB and Normal-layout control mode. Use the exact product alarm action key. All targets validate before writing; feature acknowledgements cannot override static profile flags. See the [operation fields and eligibility](beds/richmat.md#hjbed).

### MLILY Control configuration

`adjustable_bed.mlily` exposes the selected MLILY product's alarms, RGB light and
countdown controls, plus independent MM/SXB sleep queries. Light and alarm actions
require their capability reply and exact product getter. Use the product's alarm
action IDs and observed six-field `alarm_record` from the status sensor. `toggle`
changes its enabled bit; editing without an explicit action recovers the current
mode. Repeat saves require an explicit `alarm_id` (1–7), or an observed
`alarm_record` for an edit. The protocol does not signal when the list is complete,
so the integration cannot safely choose an unused ID from cached records.
Save/delete refresh the observed list. See the
[MLILY Control guide](beds/richmat.md#mlily-control) for all profile gates,
gestures, notifications and sleep operations.

### Galaxy Bed Control configuration

`adjustable_bed.galaxy` configures the selected Galaxy bed's alarms, lights,
massage countdown and bed anti-snore settings. It uses the same fields as the
bed settings of `goodvibe`, with Galaxy's own product gates and record format.
Choose exact alarm action IDs from the [Galaxy command table](beds/richmat.md#galaxy-bed-control).
Relevant capability replies must have arrived on the current connection.
`enable_alarm` takes an observed `alarm_id` and `enabled`, preserving the
received time, action, reserved field and weekday mask.
Separate sleep-sensor operations are not offered.

### Good Vibe Sleep configuration

`adjustable_bed.goodvibe` exposes product-gated alarm, light and snore settings plus independent sleep-sensor queries. Select an exact alarm action ID from the [command/profile tables](beds/richmat.md#alarms-and-snore-settings). Sleep reports use `operation: report`, a date, part and report type (1 day, 2 month); metadata, continuation and typed receipt form one operation. The status sensor retains typed reports and per-side live values. Use the app-labelled buttons for normal controls and the existing bounded `hold_control` action for held gestures. See the [protocol guide](beds/richmat.md#good-vibe-sleep) for every packet, profile gate and lifecycle limit.

## Ergomotion 4.0

The [Ergomotion 4.0 profile](beds/keeson.md#ergomotion-40) exposes each selected product's
named action as a button. Held buttons work with `hold_control` (1–60000 ms);
the guide's command table lists each control key. Existing device/side targeting
routes P1 commands and cleanup through the same Left/Right child. A parent
target defaults to native Both. P2 products do not have a side field.

The existing `rename`, `sync_clock` and `configure_alarm_schedule` actions also
support this profile, including P2 layouts. To end an active wake vibration,
press the profile's **Dismiss wake vibration** button, which every product
offers. No action stops it: `jiecang_stop_wake` accepts only the Jiecang app
profiles and the Comfort Motion app. Rename accepts a trimmed 1–16
UTF-16-unit name, with the app's byte-copy rules.
Weekly/one-time alarm tables each hold three enabled records; both are
validated before dispatch. One-time targets must be later today and unambiguous
in the local timezone. These configuration frames have no side field: target
the physical receiver/parent once when configuring shared state.

RGB requires an eligible product and reported light-on state. Use its light
toggle button while off. The named high/medium/low buttons preserve 100/60/20%
channel scaling. Meditation Start/Stop is available only for the guide's exact
product/name gates; an HA automation can repeat Start for cycle operation.

## eShine E2000 / E3000 / E3100 / E5000 alarm

`adjustable_bed.eshine_set_alarm` sets or disables the next-occurrence bed-local
alarm. Required fields: `device_id`, `enabled`; an enabled alarm also requires
minute-precision `time`. `wake_mode` is `zero_g` (default), `flat`, or `massage`
(E3000/E3100/E5000 only). Optional `side` retains native paired-side routing.
Every selected target is validated before any clock or alarm write.

Use `sync_clock`, `hold_control`, and the profile's refresh/strength/timer buttons
for other controls. See the [protocol guide](beds/okin-nframe.md#eshine-clock-and-alarms)
for packet values, timing and hardware-unverified status. This is separate from
the E6000 app profile.

## Luuna Rise / Power Cool bed settings

`adjustable_bed.richmat_rise` targets the exact selected app and layout. Use
`query` to refresh alarm and lamp capability, `alarm` / `cancel_alarm` for the
bed's countdown, `rgb` for a three-byte color, and `lamp_timer` with `seconds`
(0–300) and optional `timer_save` to select the app's zero encoding. `actions`
is a list of `node_<number>` keys from the device's `alarm_actions` diagnostics.
Only that layout's choices are admitted. `time` is the next local occurrence;
omitting it selects 1440 minutes. Unsupported preset/massage combinations are
rejected before writing. Confirmation is not schedule readback.

`massage_timer` accepts `progress` 0–5 only for D1RM/D9RM. `massage_popup` uses
Y6RM's `popup` choice (`15`, `30`, `45`, `toggle`). These labels do not establish
firmware durations. Alarm and lamp writes require capability evidence from the
current physical session, including after an idle reconnect.

Power Cool's explicitly selected TEST layout permits `diagnostic_cycle`, a
finite motor sequence cancelled by STOP. Its RMCS layout permits
`program_schedule`. Supply `schedule` with twelve `[order, run_seconds,
rest_seconds]` records in fixed M1/M2/M3/M4/M12/M34 up/down order, plus `rest`,
`count`, `radio` (`rf` or `ble`), `code` (`new` or `old`), `identifier` (1–9), and
`motors` (a permutation of 1–4). Orders must be a permutation of 1–12. The radio
field is part of the BLE program. No program abort or readback is proven.
These operations use movement scheduling. Luuna's manufacturing layouts,
standalone desks, networks and separate accessories are not service targets.

See the [generated command tables](beds/richmat.md#luuna-rise--power-cool).

## Classic Richmat app settings

`adjustable_bed.richmat_classic` targets the selected Avocado Eco Base,
CoasterSleep, Forty Winks, Milemont or Superior app profile. It validates every
selected physical target before sending settings.

| Operation | Fields | Effect |
|---|---|---|
| `query` | None | Query alarm metadata when present, lamp and aroma capabilities. |
| `alarm` | `action`, `time` | Schedule one action from the layout’s diagnostics `alarm_actions`, at minute precision. |
| `cancel_alarm` | None | Cancel the bed alarm. |
| `rgb` | `rgb_color` | One RGB write, when the app’s lamp capability/menu is available. |
| `lamp_slider` / `lamp_save` | `minutes`, 0-15 | Preserve the app’s distinct seconds/minutes encodings. |
| `aroma` | `aroma_times: [mode2_minutes, mode3_minutes, pause_hours]` | Write three settings, ranges 1-60, 1-60 and 1-12. |
| `massage_popup` | `popup`: `15`, `30`, `45` or `toggle` | Choose an option bound to the current layout’s popup. |
| `massage_timer` | `progress`: 0-5 | D1RM/D9RM slider, preserving pass-through values 1 and 4. |
| `desk_target` | `height` | Target within the desk’s current reported app ruler range. |
| `desk_unit` | `unit`: `cm` or `inches` | Set the source unit value. |
| `desk_recall` | `slot`: 1-4, optional `duration_ms`: 1-60000 | Hold the selected desk button with 200 ms refresh. Slot 4 is reset. |
| `desk_reset` | None | Confirm a newly reported desk error once; the last reported error remains visible. |

Alarm, light and aroma actions retain the app’s capability and layout gates.
Alarm delay is until the next chosen local wall-clock time; the same minute
means tomorrow. There is no inferred weekly schedule. Desk actions require
FWRM/WFRM. App mode labels do not authorize one-address side pairing. Wi-Fi,
cloud and bed network/group administration are excluded.
See the [protocol guide](beds/richmat.md#classic-richmat-apps) for the frames.

### Hush Base

Use `adjustable_bed.hush_base` for Hush bed and independent sleep-module configuration. The [Hush guide](beds/hush-base.md#configuration-actions) lists the finite operations, profile gates and sensor partition domains; the [Richmat guide](beds/richmat.md#hush-base) has the packet formats.

### Richmat app mattress and calendar alarms

`adjustable_bed.richmat_app_alarm` supports the explicit W.Silver Products,
AMERICANSTAR (Richmat), Bailey and TX profiles, subject to their model gates.
See [the app guide](beds/ruf-richmat-apps.md#alarms) for the supported families.

- `device_id`: one or more beds; `side` optionally targets a paired-bed side.
- `family`: `mattress` or `calendar`.
- `time`: local alarm time; `enabled`: whether to enable it.
- Mattress: `mattress_side` (`left`/`right`), `repeat` (`once`/`daily`), `intensity` (1–3).
  Requires the explicit normal-mattress variant and a fresh powered initialization.
- Calendar: `slot` (1–7), `mode` (decimal opcode from the model's alarm position list),
  `weekdays` (Monday 0 through Sunday 6, empty for once). `delete: true` deletes the slot;
  `enabled: false` retains a disabled record. A received record's bed number is preserved.

All selected targets are validated before any writes. Existing
`richmat_mh_alarm`, `richmat_mh_waist_alarm`, `richmat_mh_aroma` and
`richmat_mh_light_color` actions also work for the model/reply-gated features
of these app profiles. RUF exposes only its waist alarm among those actions.

### OkinComfortBed II alarm

`adjustable_bed.jalon_set_alarm` configures the Jalon app's bed-local alarm on P2
or P3 receivers. Supply `device_id`, `enabled`, minute-precision `time`, optional
`weekdays` (`mon` through `sun`, empty for the next occurrence), and `wake_mode`
(`flat`, `memory_1`, `memory_2`, `zero_g`, `anti_snore`, `tv`, or `massage`). Paired
child targets retain their side. P1 has no alarm setter. See the
[profile guide](beds/keeson.md#okincomfortbed-ii) for timing and notification state.

### Rize Beds default-preset programming

`adjustable_bed.rize_program_preset` accepts `device_id`, `preset` (`zero_g`,
`anti_snore`, `book`, `leisure`) and required `confirm: true`. It requires an
extended Rize product and one physical target. Reading (`book`) programming
requires layout5/6 (products135/136/140); Reading recall is also available on7/8. For a paired bed, select its
child device or specify `side: left` or `side: right`; Both and multi-target
programming are rejected. It writes once to that selected target, with no
preliminary memory-slot write. See the [Rize guide](beds/kaidi.md#rize-beds).

## Luuna +

`adjustable_bed.luuna` controls the selected Rise, Rise Pro or Rise Pro Light
profile. See the [Luuna + profile](beds/richmat.md#luuna-) for its capability gates.
Choose `alarm` with `hour`, `minute` and `mode` (`anti_snore`, `zero_g`, `tv`,
`memory_1` or `memory_2`, as the product offers), or `alarm_cancel`.
Light operations are `light_rgb` (`rgb_color`), `light_warm` / `light_cold`
(`value`, 0–100 percent brightness), `light_seconds` (`value`, 0/300/600/900),
and `light_off`. Zero duration means always on. `sleep_name` queries the
bed-provided accessory name for Rise and Rise Pro Light; `time_sync` sends the
local calendar. Each target is validated before any writes. Physical behavior
is unverified.

### ComfortBaseForBluetooth bed alarm

`adjustable_bed.comfortbase_set_alarm` accepts `device_id`, `enabled`, a minute-precision
`time` when enabling, and `memory` (1 for A, 2 for B). Optional `side` targets a physical
receiver of a two-address pair. Enabling synchronizes the local wall clock twice, then
programs the bed alarm. Disabling writes the app's all-zero cancel record. There is no
alarm feedback or decoded weekday schedule. `adjustable_bed.sync_clock` is also available.


### Richmat 4.2.0 configuration

`adjustable_bed.richmat_app` exposes product-gated lighting, alarms, blanket,
detection, anti-snore/off-bed, USB and cancellable demos. Sleep operations target
a separate Richmat sleep entry. See the [operation and parameter reference](beds/richmat.md#richmat-420).

### OkinComfortBed Ⅱ (Jalon) bed alarm

`adjustable_bed.jalon_bed_set_alarm` targets this app's bed-local wake timer.
Set `enabled: true`, `time: "07:30:00"`, `weekdays: [0, 1, 2, 3, 4]` (Monday
through Friday), and `wake_mode: memory_1`. Other wake modes are `none`,
`memory_2` and `massage`. Empty weekdays means the next occurrence today or
tomorrow. `enabled: false` clears the alarm without clock synchronization.
Use the usual `device_id` and optional `side` fields. See the
[Jalon profile](beds/keeson.md#okincomfortbed-ⅱ-jalon) for the wire behavior,
held gestures and hardware caveats. The generic `sync_clock` action also
supports this profile.

## N32 Motion Bed alarms

`adjustable_bed.n32_motion_bed_alarm` targets an explicitly configured N32
Motion Bed and accepts `slot: 1`, `2` or `3`, plus `operation: set`, `disable`,
`delete` or `query`. Two-address pairs retain normal `side` routing.

For `set`, supply `time` (minute precision), `weekdays` (Monday through Sunday,
empty for once), and `mode` (`none`, `m1`, `m2`, `m3`, `flat`). Disable preserves
a fresh reported slot; delete clears it and queries it again. Alarm sensors
publish actual callback state and freshness. See the [N32 profile](beds/okin-nframe.md#n32-motion-bed).

```yaml
action: adjustable_bed.n32_motion_bed_alarm
data:
  device_id: YOUR_DEVICE_ID
  slot: 1
  operation: set
  time: "06:30:00"
  weekdays: [monday, tuesday, wednesday, thursday, friday]
  mode: m1
```
