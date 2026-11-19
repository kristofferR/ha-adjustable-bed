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

## Action index

| Action | Name | What it does |
|--------|------|--------------|
| [`goto_preset`](#movement-and-memory) | Go to preset | Move bed to a saved memory position. |
| [`save_preset`](#movement-and-memory) | Save preset | Save current bed position to a memory slot. |
| [`stop_all`](#movement-and-memory) | Stop all motors | Immediately stop all bed motors. |
| [`set_position`](#movement-and-memory) | Move motor to position | Move a motor to a specific position and stop when reached. |
| [`set_positions`](#movement-and-memory) | Move motors to positions | Move several motors to validated target positions in one ordered request. Every target is validated before movement starts. |
| [`timed_move`](#movement-and-memory) | Move motor for a time | Move a motor for a specified duration. |
| [`hold_control`](#hold_control) | Hold control | Hold one control that the bed's app profile declares for a bounded duration, then send that profile's release sequence. Every target is checked before any bed moves; an unsupported control is rejected with the list of valid controls. |
| [`l2motion`](#l2-motion) | L2 Motion: settings | Change supported light colors or explicitly confirm wired or wireless synchronization. |
| [`personal_comfort_sequence`](#personal_comfort_sequence) | Personal Comfort: run sequence | Run full body massage, or a preset with the other base lowering its feet for 30 seconds. |
| [`set_alarm`](#set_alarm) | Set alarm | Sets or turns off the alarm stored in the bed. Each bed accepts only the options its own app offers; Home Assistant checks every selected bed before changing any. |
| [`betterliving2_massage`](#betterliving2-actions) | BetterLiving2: run control | Set head and foot massage intensity. |
| [`betterliving2_diagnostic_action`](#betterliving2-actions) | BetterLiving2: settings | Refresh alarm or massage status. |
| [`sync_clock`](#sync_clock) | Set bed clock | Set each targeted controller's clock to Home Assistant's local time. Every target is checked before any write. |
| [`rename`](#rename) | Rename Bluetooth name | Write a new Bluetooth name to each targeted controller that supports it. Each app profile applies its own name rule to every target before any write. This does not rename the Home Assistant device. |
| [`lower_to_flat`](#estimated-positions) | Lower to flat | Lower the selected motors for their full travel time plus a margin. This never sets the reference: confirm flat afterwards. |
| [`estimate_save_position`](#estimated-positions) | Save estimated position | Save the current estimated position under a name. Every included motor must be tracking. |
| [`estimate_rename_position`](#estimated-positions) | Rename estimated position | Rename a saved position, and optionally show or hide its button entity. |
| [`estimate_update_position`](#estimated-positions) | Update estimated position | Replace a saved position with the current estimated position of the sides it covers. |
| [`estimate_delete_position`](#estimated-positions) | Delete estimated position | Delete a saved position and its button entity. |
| [`estimate_recall_position`](#estimated-positions) | Recall estimated position | Move each motor for its calculated time to reach a saved position. Every covered side must be tracking. The result is estimated. |
| [`estimate_set_reference`](#estimated-positions) | Set estimated position reference | Confirm the selected motors are flat now. Their estimates start again at 0%. |
| [`estimate_confirm_unchanged`](#estimated-positions) | Confirm estimated position | Trust the estimate restored after a restart because the bed has not moved since. |
| [`estimate_mark_unknown`](#estimated-positions) | Forget estimated position | Report a movement the integration could not see, such as the remote or the bed's app. |
| [`generate_support_bundle`](#support-bundle) | Create support bundle | Records what the bed sends over Bluetooth while you use its remote, and saves a file to attach to a bug report or bed support request. The file lists up to 30 nearby Bluetooth devices with their names and addresses. |
| [`agingplace_action`](#agingplace_action) | Aging in Place: run control | Run one of the bed's actions. Flat ends a cycle or self check; Release held control stops a held key. In and Out are held with Hold control. |
| [`agingplace_set_setting`](#agingplace_set_setting) | Aging in Place: settings | Set light brightness, massage duration or motion light duration. |
| [`bedtech_app_command`](#bedtech_app_command) | BedTech: press button | Press one of the selected BedTech model's buttons, on the sleeper side the app uses for it. Movement repeats for the configured number of pulses. |
| [`bedgear`](#bedgear) | Bedgear: settings | Change Bedgear settings. Values show as unknown until the bed reports them. |
| [`casper_base`](#casper_base) | Casper Base: settings | Configure the selected Casper Base product or its separate sleep sensor. See the Casper Base guide for operation-specific fields. |
| [`cheerssleep`](#cheerssleep) | CheersSleep: run control | Run one of the bed's controls, such as movement, presets, massage or the light. Every selected bed is checked before any of them changes. |
| [`comfort_enhancement3_start_massage`](#comfort_enhancement3_start_massage) | Comfort Enhancement 3: start massage | Start a relative massage program. Values are app choices, not measured bed state. |
| [`customatic_hold_memory`](#customatic_hold_memory) | Customatic: hold memory buttons | Hold a nonempty combination of the Clarity or Remedy memory-page actions. Program combinations can change stored positions. |
| [`customatic_move_simultaneously`](#customatic_move_simultaneously) | Customatic: move motors together | Moves up to three motors together, then stops them. |
| [`fsm_relax_calibrate`](#fsm_relax_calibrate) | FSM Relax: calibrate | Calibrate the bed with its configured motor directions. Calibration is sent once; if Home Assistant reports an error, check the bed before you try again. |
| [`floyd_action`](#floyd_action) | Floyd: settings | Moves to a preset, saves over a built-in preset, or links a bed to a room in the app. |
| [`furnimove_action`](#furnimove_action) | FurniMove: press button | Presses one of the handset's buttons, optionally holding it. |
| [`furnimove_massage_duration`](#furnimove_massage_duration) | FurniMove: massage duration | Set the local app duration preference. This does not program a hardware timer or stop massage when time expires. |
| [`furnimove_massage_program`](#furnimove_massage_program) | FurniMove: massage program | Select massage program 1, 2, 3 or 4 (Wave), the way the handset does. |
| [`furnimove_move_simultaneously`](#furnimove_move_simultaneously) | FurniMove: move two motors together | Hold two supported axes with the app’s combined command and release cleanup. |
| [`gmmotor`](#gmmotor) | GM Control: settings | Runs a GM Control setting or reading. Use the bed's buttons or Hold control for movement. |
| [`galaxy`](#galaxy) | Galaxy: settings | Sets the alarm, light and anti-snore options of a Galaxy bed. |
| [`goodvibe`](#goodvibe) | Good Vibe Sleep: settings | Sets the alarm, light, massage and anti-snore options of a Good Vibe Sleep bed or its sleep sensor. |
| [`hjbed`](#hjbed) | HJBed: settings | Sets the alarm, light and other options of an HJBed bed. The bed must report the feature first. |
| [`hush_base`](#hush_base) | Hush Base: settings | Configure Hush Base bed or independent sleep sensor controls. |
| [`jiecang_stop_wake`](#jiecang_stop_wake) | Jiecang: stop wake massage | Stop active wake massage without disabling the stored weekly clock alarm. |
| [`jiecang_wake`](#jiecang_wake) | Jiecang: start wake routine | Move to a preset and start the selected wake massage levels immediately. |
| [`comfy_control`](#comfy_control) | KomfyD and ComfyDS: settings | Moves the bed or runs its timer and lock buttons. |
| [`richmat_resource_bed`](#richmat_resource_bed) | Lady Americana and partner beds: settings | Control the selected app’s bed features. Query optional light support before changing its color or timeout. App commands do not certify a physical memory slot. |
| [`leggett_sleep_timer`](#leggett_sleep_timer) | Leggett & Platt: sleep timer | Start a delayed preset or cancel the stored sleep timer. |
| [`limoss_remote_calibrate`](#limoss_remote_calibrate) | Limoss Remote: calibrate | Runs the remote's calibration after you confirm, then releases the motors. |
| [`limoss_remote_features`](#limoss_remote_features) | Limoss Remote: configure controls | Set local layout selections. Disabling a selected feature sends its ten OFF commands before saving. |
| [`limoss_remote_rename_memory`](#limoss_remote_rename_memory) | Limoss Remote: rename memory | Rename a local memory. Empty names are permitted. |
| [`linak_move_simultaneously`](#linak_move_simultaneously) | Linak: move two motors together | Move two different sections with one native command (Linak Bed Control, Jensen JMC400), then send STOP. |
| [`linx_snore_intervention`](#linx_snore_intervention) | Linx: snore intervention | Run the bed's anti-snore movement once, then ask the bed for its status. It does not listen for snoring. |
| [`logicdata_hold_preset`](#logicdata_hold_preset) | LOGICDATA: hold preset | Hold a flat, preset or memory recall with repeated commands for a specified duration, then release. |
| [`luuna`](#luuna) | Luuna: settings | Configure the Luuna alarm, light or query the bed-provided sleep accessory name. Requires the selected product and reported capability. |
| [`richmat_rise`](#richmat_rise) | Luuna Rise and Power Cool: settings | Bed settings for Luuna Rise and Power Cool beds. Alarm and lamp settings need the bed to report them first. |
| [`mline_command`](#mline_command) | M Line: settings | Sets sleep privacy or anti-snore, reads the current settings or alarm, or downloads sleep history. |
| [`mlily`](#mlily) | MLILY: settings | Configure this MLILY product or its independent MM/SXB sleep receiver. |
| [`motion_bed_action`](#motion_bed_action) | Motion Bed: run control | Run a control by its name, as listed in the bed's diagnostics. Saving, clearing, resetting and changing modules need confirmation. |
| [`motion_bed_air_setting`](#motion_bed_air_setting) | Motion Bed: air settings | Query or save the selected mode’s upper gear and optional timer. Lower pressure is readback only. |
| [`motion_bed_audio`](#motion_bed_audio) | Motion Bed: audio | Select a track, preview a track, or set volume on a target that reports audio support. |
| [`motion_bed_calibration`](#motion_bed_calibration) | Motion Bed: calibrate sleep sensing | Save the app’s flat and side calibration readings. Confirm before changing calibration. |
| [`motion_bed_module`](#motion_bed_module) | Motion Bed: hub modules | Lists, adds or removes the motor, air or heating modules of a Motion Bed hub. Adding and removing need confirmation. |
| [`motion_bed_pressure`](#motion_bed_pressure) | Motion Bed: air pressure | Adjusts one air channel, or saves all twelve air pressures at once. |
| [`motion_bed_sleep_angles`](#motion_bed_sleep_angles) | Motion Bed: sleep positions | Saves the four flat and four side-sleeping positions used by sleep sensing. Use the values shown in the app. |
| [`motion_bed_sleep_report`](#motion_bed_sleep_report) | Motion Bed: sleep report | Read current, historical day, month or timer data. Historical day selection and graph window offset are separate. |
| [`motion_bed_sleep_timer`](#motion_bed_sleep_timer) | Motion Bed: sleep timer | Select an app bedtime or fall timer slot. |
| [`motion_bed_thermal_schedule`](#motion_bed_thermal_schedule) | Motion Bed: heating schedule | Save a timer with cooling or heating mode and gear, without guessing a thermostat setpoint. |
| [`motomotion`](#motomotion) | MotoMotion: postures and users | Save body measurements and your own posture positions on MotoMotion beds whose app has a users tab. Measurements are height, buttocks height and knee height in centimetres. This does not read where the motors are. |
| [`doublesleep_configure`](#doublesleep_configure) | OKIN SleepEase: settings | Alarm, anti-snore, sensor settings, report retrieval and named preset programming for the SleepEase app profile. Reports remain on the selected physical bed's report sensors. |
| [`octo_enroll_pin`](#octo_enroll_pin) | Octo: set PIN | Set a new four-digit PIN on one unlocked OCTO Smart Control receiver. Enter the same PIN twice. Home Assistant saves it for reconnects after sending the command. |
| [`octo_reset_defaults`](#octo_reset_defaults) | Octo: reset receiver | Restore receiver defaults after explicit confirmation. The receiver disconnects five seconds after the reset command. |
| [`okimiki`](#okimiki) | Okimiki: settings | Press or save a control, set the light, or read and set the alarms of the selected Okimiki product. Set the clock with Set bed clock. |
| [`bobpowerbase`](#bobpowerbase) | Power Bob Base: settings | Manage repeat alarms or set the light, when the bed reports them. Set the clock with Set bed clock. |
| [`rmcontrol_anti_snore`](#rmcontrol_anti_snore) | RMControl: anti-snore | Turns anti-snore on or off, or sets how it responds to snoring. |
| [`reverie_pairlink_alarm_comfort`](#reverie_pairlink_alarm_comfort) | Reverie: set alarm comfort | Send the complete Pairlink alarm comfort sequence, including unchanged values. |
| [`reverie_run_routine`](#reverie_run_routine) | Reverie: run routine | Run a routine of comfort steps on the selected Reverie bed. It replaces any routine the bed is running. |
| [`reverie_set_comfort`](#reverie_set_comfort) | Reverie: set comfort | Send one validated composite Reverie comfort setting to every selected target. |
| [`richmat_classic`](#richmat_classic) | Richmat (classic app): settings | Settings for Avocado Eco Base, CoasterSleep, Forty Winks, Milemont and Superior beds. |
| [`richmat_app`](#richmat_app) | Richmat app: settings | Sets the light, alarm, sleep sensing and other options of a Richmat app bed. Read the feature first before changing it. |
| [`richmat_mh_aroma`](#richmat_mh_aroma) | Richmat app: aroma timing | Write the three aroma timing sliders of a Richmat MH app profile. |
| [`richmat_mh_light_color`](#richmat_mh_light_color) | Richmat app: light color | Write the LED or button-light page colour of a Richmat MH app profile. |
| [`majestichome`](#majestichome) | Majestic Home: settings | Read, create, edit, turn on or off, or delete the bed's alarms. Set the clock with Set bed clock. |
| [`richmat_mh_control`](#richmat_mh_control) | Nisco and MLILY Supreme: run control | Run one of the selected app and model's controls, read one setting from the bed, or set the app mode used by later controls. |
| [`richmat_mh_sleep_mode`](#richmat_mh_sleep_mode) | Nisco: sleep sensor mode | Set the separate sleep sensor for one or two sleepers. |
| [`richmat_legacy`](#richmat_legacy) | SleepEvolution and W.Silver Products: run control | Run a control from the selected app and name prefix, as a press or a save. |
| [`mlily_remote`](#mlily_remote) | MLILY Remote: settings | Set the MS600 countdown alarm, or run the MS300-SH anti-snore movement on the left side. Set the clock with Set bed clock. |
| [`rize_program_preset`](#rize_program_preset) | Rize: set default preset | Store the current position as a default preset on one physical Rize bed. Select one side of a combined bed and explicitly confirm. |
| [`sleep_number_command`](#sleep_number_command) | Sleep Number: run control | Runs a Sleep Number control or reading. Readings return their results. See the actions guide for each command's options. |
| [`sleeptracker_climate`](#sleeptracker_climate) | Sleeptracker: climate | Set the left, right or both fan modes and levels. Level 0 stops the selected fans. Heat runs for one hour and cool for ten hours. The bed does not report the time left. |
| [`sleeptracker_massage`](#sleeptracker_massage) | Sleeptracker: massage | Steps a massage zone or pattern, picks a vibration speed, or stops the massage. |
| [`sleeptracker_preset`](#sleeptracker_preset) | Sleeptracker: preset | Moves to or saves a preset. The presets depend on the bed. |
| [`sleeptracker_relaxation`](#sleeptracker_relaxation) | Sleeptracker: relaxation | Starts the wind-down routine or the bed's relaxation movement. |
| [`sleeptracker_wave`](#sleeptracker_wave) | Sleeptracker: relaxation wave | Starts a wave massage at the chosen speed and for the chosen time. Use Stop massage to end it early. |
| [`onlysnore_set_alarm`](#onlysnore_set_alarm) | Snore Monitor: set bed alarm | Set or turn off one of the bed's own alarms. |
| [`solace_audio`](#solace_audio) | Solace: audio | Select or preview MotionFlex music, query volume, or set volume. |
| [`somos_action`](#somos_action) | Somos: press button | Press one of the selected Somos product's buttons. Every bed is checked before any is changed. |
| [`sonicsleep`](#sonicsleep) | SonicSleep: settings | Read the alarms, create or edit an alarm, turn an alarm on or off without changing it, delete an alarm, or read the bed's link name. |
| [`suta`](#suta) | SUTA Smart Home: run control | Run one control from the bed's SUTA layout, which its Bluetooth name decides. Set alarms with Set alarm and the clock with Set bed clock. |
| [`starcode_move_lifts`](#starcode_move_lifts) | StarCode: move lifts | Control the independently addressed accessories configured on one main bed. Flat moves the main before the delayed lift action. |
| [`svane_release_axis`](#svane_release_axis) | Svane: release motor | Stop one motor while the other keeps moving. |
| [`symphony_anti_snore`](#symphony_anti_snore) | Symphony: anti-snore | Configure Head or Elevation. Legacy strengths are 1, 3 and 6; SoundWave strengths are 1, 2 and 3. |
| [`symphony_preset`](#symphony_preset) | Symphony: preset | Recall a preset, or explicitly save it where the product supports programming. |
| [`symphony_set_light`](#symphony_set_light) | Symphony: set light | Set both light parameters explicitly, without replacing unknown companion state. ES700 and SS800 only. |

# General actions

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
| `goto_preset` | `preset` | Recall a supported memory slot, 1–255 where the controller advertises it. Optional `duration` sets the recall hold where supported |
| `save_preset` | `preset` | Overwrite a supported memory slot with the current position |
| `stop_all` | None | Cancel pending/active movement and perform the controller's STOP or release cleanup |
| `set_position` | `motor`, `position` | Move one supported axis to a target |
| `set_positions` | `positions` | Validate all motor targets before starting an ordered multi-motor request |
| `timed_move` | `motor`, `direction`, `duration_ms` | Move up/down for an elapsed movement ceiling of 100–30000 ms |
| `reverie_set_comfort` | `comfort` | Send a typed Reverie composite setting after every selected model validates it |
| `reverie_run_routine` | `steps` | Replace and run the selected target's Reverie Composer queue |

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
Check the position entity and the bed's [guide](README.md#bed-guides). Feedback
must be enabled for feedback-driven seeks. Sleep Number MCR uses `left_back`,
`right_back`, `left_legs`, and `right_legs` with percentage targets for discovered
foundation actuators. A `set_positions` list cannot repeat a motor. Its validation
is performed before movement, but a later transport failure can still leave a
partially completed move.

A direct command being accepted is not confirmation that the target was reached.

Beds without position feedback can opt in to calibrated travel-time estimates
and saved positions. Their actions (`estimate_save_position`,
`estimate_recall_position`, `estimate_set_reference` and others) are described in
[Estimated positions](ESTIMATED_POSITIONS.md#actions).

### Renewable holds


`timed_move` and `hold_control` accept two optional fields, `hold_owner` and
`hold_generation`, that turn the call into a renewable hold on beds whose app
is known to hold a key until release, by streaming it or by one start frame
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
hold targets one bed or combined bed per call; on a combined bed both sides must
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

**Testing status.** Scheduler and service tests show that a renewal writes nothing and only moves the deadline,
that expiry runs the bed's own release or STOP once, that STOP, a replacement,
a dropped link or an unload ends the generation, and that a late or stale
renewal never starts motion. Card tests cover the 250 ms renewals and the STOP
on release, hide and removal. Needs real-bed reports, family by family as each
opts in: whether a held motor moves smoothly while renewals arrive through real
adapters and ESPHome proxies, and how long it keeps moving after renewals stop.
The first opt-ins are the Leggett Okin and Customatic profiles of the
[Okin N-frame codec](beds/okin-nframe.md#hold-and-release-timing).

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
| [Leggett Okin app profiles](beds/okin-nframe.md#leggett-okin-family) | `flat`, `snore`, `lights_toggle`, `massage_toggle`, `massage_wave`, `massage_head_up`, `massage_head_down`, `massage_foot_up`, `massage_foot_down`; U Series adds `memory_1`, `memory_2`, `store` | See the guide |
| [Jordan's Serenity](beds/okin-nframe.md#reachable-commands) | 31 literal app actions | Two-frame release |
| [Jordan's Tranquil](beds/okin-nframe.md#reachable-commands-1) | 30 literal app actions | Two-frame release |
| [Customatic Z-Series](beds/okin-nframe.md#reachable-commands-2) | Literal Z-230 or Z-280 actions | A Z-230 rejects Z-280-only actions and the reverse |
| [SIMMONS](beds/okin-nframe.md#simmons) | `head_up`, `head_down`, `legs_up`, `legs_down`, `flat`, `memory`, `light`, plus `zero_g`, `tv`, `anti_snore` on a regular bed or `inclined_left`, `inclined_middle`, `inclined_right` on an inclined bed | Frame every 300 ms, then STOP at +100 and +400 ms. Holding `memory` for 5 seconds mirrors the app's Custom Mode save; not yet confirmed on a real bed |
| [AdjustaMattress](beds/keeson.md#adjustamattress) | App action identifiers such as `headUp`, `footDown`, `unionUp`, `neckTiltUp`, `lumbarDown`, `flatPosition`, `zeroGravity`, `m1`, `underbedLighting`, `headStrengthAdd`, `timer10`, subject to the selected model/layout | 200 ms refresh; movement/lift starts at +200 ms. STOP at +200 ms after release. Ordinary P3/P4 massage additionally queries at +400/+600 ms. P2 unsafe prior-frame lighting replay is excluded |
| [Adjustable bed (Lumbar)](beds/okin-nframe.md#timing-and-controls) | `head_up`, `head_down`, `feet_up`, `feet_down`, `lumbar_up`, `lumbar_down`, `flat`, `zero_g`, `lounge`, `incline`, `anti_snore`, `save_zero_g`, `save_lounge`, `save_incline`, `save_anti_snore`, `light`, `wave_1`, `wave_2`, `wave_3`, `massage_up`, `massage_down` | Frame every 100 ms, then STOP immediately and 300 ms later. Not yet confirmed on a real bed whether a save stores the position |
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


### `sync_clock`


Set each targeted controller's clock to Home Assistant's local time. Supported,
for example, by [RMControl](beds/richmat.md#rmcontrol) products with a clock, the [Malouf Base / Lucid Base](beds/malouf.md#malouf-base--lucid-base-family) app profile on its OKIN
transports, [Glideaway Motion / Montion](beds/keeson.md#alarm-and-clock), [SIMMONS](beds/okin-nframe.md#alarms-and-clock), and
[Customatic Z-Series](beds/okin-nframe.md#customatic-z-series) controllers whose
manufacturer string enables the alarm page (see
[`set_alarm`](#set_alarm)). Z-Series beds cannot share a call
with other profiles. SUTA Smart Home, SonicSleep, MLILY Remote, Good Vibe Sleep,
Galaxy, MLILY, Power Bob Base, Majestic Home and Okimiki products with an alarm, Motion Bed (the
motor or thermal module clock; on a hub, the clock of the module in use, so
select the motor or heating module first), GM Control products with an alarm and OKIN
SleepEase also set their clock here; their own actions no longer do. A bed whose
two sides share one receiver has its clock set once.

### `set_alarm`

Sets or turns off the alarm stored in the bed itself. One action covers every
bed with an alarm; each bed accepts only the options its own app offers, and
Home Assistant checks every selected bed before changing any of them. An option
a bed does not have is refused with a message naming it.

| Field | Meaning |
|-------|---------|
| `enabled` | Required. `false` cancels the alarm (or the selected alarm number) |
| `time` | When the alarm goes off, in whole minutes. Required to turn it on |
| `weekdays` | Days to repeat on (`monday` … `sunday`). Empty means once, at the next occurrence |
| `wake_action` | What the bed does at the alarm, for example `flat`, `zero_g`, `memory_1`, `massage` or `none`. Leave empty for the bed's usual choice |
| `slot` | Alarm number on beds that store more than one |
| `massage`, `massage_zone`, `massage_intensity`, `massage_duration`, `head_massage_level`, `foot_massage_level` | Wake-up massage, where the bed has one |
| `light`, `sound` | Turn on the light or play a sound at the alarm, where available |
| `mattress_side` | Set the alarm of a vibrating mattress topper on that side instead of the bed's |
| `confirm_custom_position` | Required to wake at a saved custom position (SIMMONS) |
| `side` | Side of a combined bed |

```yaml
action: adjustable_bed.set_alarm
data:
  device_id: YOUR_DEVICE_ID
  enabled: true
  time: "07:30:00"
  weekdays: [monday, tuesday, wednesday, thursday, friday]
  wake_action: zero_g
```

| Bed | Wake actions | Other options |
|-----|--------------|---------------|
| BF and Cherish | `none`, `memory_1`, `memory_2` | Once only |
| Comfort Enhancement 3 | Depends on the remote: `none`, `memory_1`, `memory_2`, `zero_g`, `tv`, `anti_snore` | `slot` 0–99, `massage` with zone, intensity and 10/20/30-minute duration, `light`. Once, at the next occurrence |
| Comfort Enhancements | `none`, `memory_1`, `memory_2` | `massage`; today only |
| ComfortBase | `memory_1`, `memory_2` | Once only |
| Customatic Z-Series | `massage`, `memory_1` (required to turn on) | Once. Needs a Z-Series controller with an alarm page |
| eShine | `zero_g`, `flat`, `massage` (by model) | Once; the bed clock is set first |
| Glideaway Motion | `none`, `memory_1`, `memory_2` | Once |
| Jiecang apps | `flat`, `zero_g`, `anti_snore`, `memory_1`, `memory_2`, `yoga` where reported | `weekdays`, head and foot massage levels 0–3 |
| Keeson app layouts (Ergomotion 4.0, Q-Plus and others) | None | `weekdays` or once, `massage` (wake vibration). One weekly and one one-time alarm; turning off clears both |
| L2 Motion | None | Once; leave `slot` out. `massage_intensity` 1 or 2 |
| Leggett & Platt (Okin app) | None | Once; the bed counts down to the time |
| Linak Bed Control | `none`, `memory_1` … `memory_4` | `massage`, `light`. Once; the bed counts down to the time |
| Linx | None | Turn off only (`enabled: false`), `slot` 1–6 |
| Logicdata app | `flat`, `zero_g`, `anti_snore`, `memory_1`, `memory_2` | `weekdays`, head and foot massage levels 0–3 |
| M Line | `zero_g`, `flat`, `memory_1`, `memory_2`, `massage`, `anti_snore` | `weekdays` |
| Malouf / Lucid app | `zero_g`, `lounge`, `tv`, `anti_snore`, memories | `weekdays` |
| Motion Bed | `none` (rings only), `zero_g`, `memory_1` | `weekdays`, `massage`, `sound` (the alarm tone by default; music 1 by default where the bed has audio) |
| N32 Motion Bed | `none`, `memory_1` … `memory_3`, `flat` | `slot` 1–3, `weekdays`; turning off keeps the slot's time |
| Nerum (P2, P3) | `none`, `memory_1`, `memory_2`, `light` | `slot` 1–3, `weekdays` or once. The other two alarms are read from the bed first |
| OKIN Smart Sleep | `memory_1`, `memory_2`, `zero_g`, `flat`, `massage`, plus `lounge`, `tv`, `anti_snore`, `light` on newer models | `weekdays` on newer models |
| OkinComfortBed II (bed) | `none`, `memory_1`, `memory_2`, `massage` | `weekdays` |
| OkinComfortBed II (Jalon) | By app version | `weekdays` |
| OrmatekTechnoSmart | New: `massage`, `memory_1`, `flat`. Lite: `zero_g`, `tv` | Daily, one alarm |
| Richmat app beds | From the model's alarm page | Once (the bed counts down), `slot` 1–3 on three-alarm models, `massage` with zone. `mattress_side` sets the vibrating mattress alarm, once or every day, with intensity 1–3 |
| Richmat app calendar models | From the model's alarm list | `slot` 1–7, `weekdays`; `mattress_side` for the vibrating mattress |
| RMControl | From the product's alarm list; required to turn an alarm on | Repeating products: `slot` 1–7 with at least one weekday. Others: once, as a countdown |
| SIMMONS | `custom_position`, `flat`, `anti_snore` (regular bed) | `slot` 1–2, `weekdays`, `confirm_custom_position`. Both alarms are read from the bed first |
| Solace | `none`, `zero_g`, `memory_1` | `weekdays`, `massage`, `sound` |
| Sophie (Solace) | `none`, `zero_g`, `memory_1`; side models `none`, `zero_g_left`, `zero_g_right`, `zero_g` | `weekdays`, `massage` (not QMS2), `sound: alarm` rings. Once the bed reports alarm support |
| SUTA Smart Home (models whose app has an alarm) | None | `weekdays` or once. To turn an alarm off, send the same `time` and `weekdays` it was set with |
| Symphony Sleep | `none`, `memory_1`, `memory_2` | Once |
| Symphony Sleep Sense | By product | `weekdays` |
| Ultramatic (ORE) | `none`, `massage`, `memory_1`, `memory_2` on the older bed route; `tv`, `massage`, `zero_g` on the newer | `weekdays` or once. Turning it on needs a `wake_action`; connect once first so the route is known |
| Ultramatic Smart Bed | `massage`, `zero_g`, `memory_1` (required to turn on) | `weekdays` or once. Left, Right and Both set the A, B and AB alarms; a standalone bed uses its configured side. Turning off without a time keeps the reported alarm's other fields; refresh the alarm first |
| Yamada | By app version | `slot` 1–2, `weekdays`. Refresh the bed's alarms first |
| Bedgear, Casper Base, classic Richmat apps, Galaxy Bed Control, GM Control, Good Vibe Sleep, HJBed, Hush Base, Lady Americana and partner beds, Luuna, Luuna Rise and Power Cool, MLILY, MLILY Remote, OKIN SleepEase, Okimiki, Power Bob Base, Richmat app (`richmat_app` bed type), Snore Monitor, SonicSleep | Use the bed's own action | See [Bedgear](#bedgear), [Casper Base](#casper_base), [classic Richmat apps](#richmat_classic), [Galaxy](#galaxy), [GM Control](#gmmotor), [Good Vibe Sleep](#good-vibe-sleep), [HJBed](#hjbed), [Hush Base](#hush_base), [Lady Americana and partner beds](#richmat_resource_bed), [Luuna](#luuna), [Luuna Rise and Power Cool](#richmat_rise), [MLILY](#mlily), [MLILY Remote](#mlily-remote), [OKIN SleepEase](#doublesleep_configure), [Okimiki](#okimiki), [Power Bob Base](#bobpowerbase), [Richmat app](#richmat_app), [`onlysnore_set_alarm`](#onlysnore_set_alarm) and [SonicSleep](#sonicsleep) |

### Estimated positions

Beds without position feedback can learn travel times and save positions.
Their actions all start with `estimate_` (`estimate_save_position`,
`estimate_recall_position`, `estimate_set_reference` and others) and are
described in [Estimated positions](ESTIMATED_POSITIONS.md#actions).

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

# Bed-specific actions

These actions also accept the optional `side` of a combined bed. Each checks every
selected bed before changing any.

## Aging in Place

<a id="agingplace_action"></a>
**`agingplace_action`**: Run one of the bed's actions. Flat ends a cycle or self check; Release held control stops a held key. In and Out are held with Hold control.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | The action to run. Read and Anti snore send the same command. |

<a id="agingplace_set_setting"></a>
**`agingplace_set_setting`**: Set light brightness, massage duration or motion light duration.

| Field | Name | Meaning |
|-------|------|---------|
| `setting` | Setting | The setting to change. |
| `value` | Value | Brightness: 0-100. Massage: 1-60 minutes. Motion light: 1-30 minutes. |

See [Aging in Place / Dawn House](beds/keeson.md#aging-in-place--dawn-house) for the bed's controls.

## BedTech

<a id="bedtech_app_command"></a>
**`bedtech_app_command`**: Press one of the selected BedTech model's buttons, on the sleeper side the app uses for it. Movement repeats for the configured number of pulses.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | Ordinary app action, subject to the selected model and sleeper. |
| `sleeper` | App sleeper | 1/2 select a receiver, 3 both, 4/5 select one head and share the foot. FH models use one receiver and separate head banks. |

### BedTech app


`bedtech_app_command` uses the selected [BedTech 7.1.3 model](beds/richmat.md#bedtech)
and its sleeper routing. Each receiver must use the same explicit model.
`action` names a control from that model's ordinary screen, such as `head_up`,
`foot_down`, `head_massage_up`, `massage_timer20`, `preset_flat`, `memory1_save` or
`light_toggle` (the app's camelCase names, such as `headUp`, still work in existing
automations). A normal movement action uses the finite pulse count; use
`timed_move` for an elapsed duration or renewable hold. `connection_test` explicitly
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
A standalone FH receiver can also select its bank with `sleeper`.

```yaml
action: adjustable_bed.bedtech_app_command
data:
  device_id: YOUR_PAIRED_BED_DEVICE_ID
  action: foot_up
  sleeper: 4
```

This example raises both foot sections while selecting the first head for
head actions. `stop` cancels refresh and writes no movement STOP packet on
explicit models. Their massage-off packet is a separate action. These app profiles are not yet confirmed on real beds.

## Bedgear

<a id="bedgear"></a>
**`bedgear`**: Change Bedgear settings. Values show as unknown until the bed reports them.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Control | Choose the supported setting or save action. |
| `rgb` | RGB channels | Three color channels, each 0 to 255. |
| `brightness` | Brightness | Scale the supplied RGB channels from 0 to 1. |
| `minutes` | Light shutdown timer | Turns the light off after this many minutes, from 0 (never) to 1439. |
| `time` | Alarm time | HH:MM. Omit only to retain a received alarm time. |
| `strength` | Alarm strength | 0 off, 1 or 2. Omit only to retain an actually received strength. This is not a weekday or repeat mode. |
| `wired` | Wired synchronization | Turn on if the two bases are connected with a cable; turn off for wireless. |
| `confirm` | Confirm synchronization change | Required for synchronization mode changes. |
| `slot` | Memory slot | Memory slot 1 or 2. |
| `recall_on_release` | Recall after saving | When saving a memory, also move to it afterwards, as the remote does. Not available when saving the anti-snore position. |

### Bedgear settings


Use `adjustable_bed.bedgear` for source-supported RGB, light shutdown minutes,
alarm strength/time, bed synchronization and memory/snore save options. See
the [Bedgear control reference](beds/motomotion.md#bedgear) for parameters.
Motor covers and the card use the generic held and timed movement actions.

## Casper Base

<a id="casper_base"></a>
**`casper_base`**: Configure the selected Casper Base product or its separate sleep sensor. See the Casper Base guide for operation-specific fields.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | Bed, light, alarm, sensor, or remote action to run. |
| `value` | Value | Duration or mode required by the selected operation. See the Casper Base guide for its units and range. |
| `rgb_color` | RGB color | Color for the selected light operation. |
| `enabled` | Enabled | Enable or disable the selected function. |
| `hour` | Alarm hour | Alarm hour in 24-hour time. |
| `minute` | Alarm minute | Minute within the selected alarm hour. |
| `mode` | Alarm preset | Position preset recalled by the alarm. |
| `slot` | Repeating alarm number | Existing or new repeating alarm identifier. |
| `days` | Weekdays | Days on which the repeating alarm runs. |
| `part` | Sensor partition | MM: 1 or 2. SXB: 11 for left, 12 for right, or 13 for both. |
| `report_type` | Report type | 1 for a daily report; 2 for a monthly report. |
| `year` | Report year | Year of the requested sensor report. |
| `month` | Report month | Month of the requested sensor report. |
| `day` | Report day | Day of month for a daily report. Use 1 for a monthly report. |
| `source` | Detector status sensor | External status sensor used by snore detection. |

### Casper Base


`adjustable_bed.casper_base` provides capability-validated alarm, light, automatic
external-detector, sleep sensor and remote-finder operations. Select a `device_id`
and `operation`; paired targets are validated together before sending commands.
The [Casper Base guide](beds/casper-base.md#configuration-actions) lists each
operation's fields and the separate sensor/remote entry types.

## CheersSleep

<a id="cheerssleep"></a>
**`cheerssleep`**: Run one of the bed's controls, such as movement, presets, massage or the light. Every selected bed is checked before any of them changes.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Control | A control this model offers. |
| `value` | Value | Level, memory slot or on and off, depending on the control. |
| `rgb` | Color | Red, green and blue, each 0 to 255. |
| `brightness` | Brightness | Light brightness, 0 to 255, on older models. |
| `duration_ms` | Duration | How long to hold the control, in milliseconds. For the timer control, 300 sets 5 minutes and 900 sets 15 minutes. |
| `axis` | Axis | One of `all`, `back`, `legs` or `lumbar`. |
| `up` | Move up | On or off. |
| `position` | Position | Which part to move: 1 all, 2 back, 3 feet or 4 waist. |
| `sleeper` | Sleeper | The side on seven-screen models. It must match the selected side. |

### CheersSleep bed controls

`adjustable_bed.cheerssleep` targets one or more device IDs, including native
paired child devices, and accepts `side` (`left`, `right`, `both`). Every target
is validated before control writes. Choose a supported `operation`:

- `query`, `query_shared`: B0/D0 state queries. `position_light_toggle` and
  `color_light_toggle` retain the position-side and shared color-page callers.
- `massage_head`, `massage_foot`, `massage_mode`: conventional cycles. P1 head/foot
  `value`1–4 selects levels0–3; `value`0 cycles. P2 accepts cycles only.
- `sonic_back`, `sonic_foot`, `sonic_toggle`, `sonic_mode_1`, `sonic_mode_2`,
  `sonic_switch`, `sonic_increase`, `sonic_decrease`, `sonic_level`: model-specific
  physical bed massage. Absolute `value` is0–100; holds use `duration_ms`.
- Conditional legacy screens: `rgb_preview`, `rgb2_preview`, `rgb_commit`,
  `rgb2_commit` use `rgb`, `brightness`0–255 and commit delay `value`10–120.
  RGB2 uses white. `snore_setting` and `out_of_bed_setting` accept `value`0/1.
  `yb_massage` uses speed `value`1–3 and timer parameter `duration_ms`300 or900.
- `seven_motion` uses the conditional split axis (`axis`: all/back/legs/lumbar)
  and optional local `sleeper` (left/right), which must agree with a targeted child.
  `ten_motion`/`newten_motion` use `position`1–4 (all/back/legs/waist), `up` and
  `duration_ms`. `ten_recall`/`newten_recall` and `ten_save`/`newten_save` use
  memory `value`1/2. These screens remain P1 even where their class name says New.

Model gates and shared versus side-specific packets are described in the
[CheersSleep guide](beds/cheerssleep.md). Hardware remains unverified.

## Comfort Enhancement 3

<a id="comfort_enhancement3_start_massage"></a>
**`comfort_enhancement3_start_massage`**: Start a relative massage program. Values are app choices, not measured bed state.

| Field | Name | Meaning |
|-------|------|---------|
| `duration` | Massage duration (minutes) | One of `10` (10 minutes), `20` (20 minutes) or `30` (30 minutes). |
| `intensity` | Relative intensity steps | A number from 1 to 3. |
| `kind` | Massage area or wave | One of `head`, `feet`, `both` or `wave`. |

### Comfort Enhancement 3 / Comfort Plus3


- `adjustable_bed.comfort_enhancement3_start_massage`: `device_id`, `duration`
  (10, 20 or 30 minutes), `intensity` (1..3), `kind` (`head`, `feet`, `both`, `wave`).
  Uses relative steps; does not report measured intensity.
- Wake-up programs use [`set_alarm`](#set_alarm) with `slot`, `time`, and the
  massage, light and wake position options the selected remote offers.
  Turning the alarm off deletes that program.

Wake-up programs stay stored in the bed while Home Assistant is disconnected.
Home Assistant cannot list the programs already stored in the bed.

## Customatic

<a id="customatic_hold_memory"></a>
**`customatic_hold_memory`**: Hold a nonempty combination of the Clarity or Remedy memory-page actions. Program combinations can change stored positions.

| Field | Name | Meaning |
|-------|------|---------|
| `actions` | Actions | Select any combination of flat, zg, anti, program and incline. Jerome's C has no memory page. |
| `duration` | Duration | How long to hold, 0.1 to 60 seconds. |

<a id="customatic_move_simultaneously"></a>
**`customatic_move_simultaneously`**: Moves up to three motors together, then stops them.

| Field | Name | Meaning |
|-------|------|---------|
| `actions` | Motor directions | A mapping of back, legs and optionally lumbar to up or down. Lumbar requires the Remedy profile. Opposing directions on one motor are rejected. |
| `duration` | Duration | Hold for 0.1 to 60 seconds, in whole milliseconds, then release. |

## FSM Relax

<a id="fsm_relax_calibrate"></a>
**`fsm_relax_calibrate`**: Calibrate the bed with its configured motor directions. Calibration is sent once; if Home Assistant reports an error, check the bed before you try again.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm | Explicitly confirm calibration before invoking this action. |

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

## Floyd

<a id="floyd_action"></a>
**`floyd_action`**: Moves to a preset, saves over a built-in preset, or links a bed to a room in the app.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | One of `zero_g` (Zero gravity), `flat`, `anti_snore` (Anti-snore), `memory_1`, `memory_2`, `memory_3`, `save_zero_g` (Save zero gravity), `save_anti_snore` (Save anti-snore) and others; see the action in Home Assistant. |
| `internal_side` | Preset page | Leave at First, the normal Floyd page. Both and Second are alarm pages, not the left and right sides. |
| `confirm` | Confirm configuration write | Required to save over a preset or to link the bed to a room. |
| `room_id` | Room number | Room to link this bed to, for a bed not yet in a room. Does not change the bed's Wi-Fi. |

### Floyd Home actions


`adjustable_bed.floyd_action` exposes confirmed `save_zero_g`,
`save_anti_snore`, unassigned BLE `assign_room` / `confirm_add`, and preset
recall with explicit conditional `internal_side` selection. All controls use
normal `device_id` and paired physical `side` routing. See the
[Floyd action table](beds/kaidi.md#floyd-action) before programming a
preset or assigning membership. Combined movement uses `hold_control` with
`head_feet_up` or `head_feet_down` and a duration up to 30 seconds. HA automations
schedule these presets; the app's phone alarms are not on-bed alarm storage.

## FurniMove

<a id="furnimove_action"></a>
**`furnimove_action`**: Presses one of the handset's buttons, optionally holding it.

| Field | Name | Meaning |
|-------|------|---------|
| `row_index` | Button number | The button's number, shown at the end of the bed's button entity IDs (for example 3 in furnimove_action_3). |
| `duration` | Hold duration | Seconds to hold movement and memory buttons. Other buttons use their own timing. |

<a id="furnimove_massage_duration"></a>
**`furnimove_massage_duration`**: Set the local app duration preference. This does not program a hardware timer or stop massage when time expires.

| Field | Name | Meaning |
|-------|------|---------|
| `minutes` | Advisory duration | One of `10` (10 minutes), `15` (15 minutes), `20` (20 minutes) or `30` (30 minutes). |

<a id="furnimove_massage_program"></a>
**`furnimove_massage_program`**: Select massage program 1, 2, 3 or 4 (Wave), the way the handset does.

| Field | Name | Meaning |
|-------|------|---------|
| `program` | Program | A number from 1 to 4. |

<a id="furnimove_move_simultaneously"></a>
**`furnimove_move_simultaneously`**: Hold two supported axes with the app’s combined command and release cleanup.

| Field | Name | Meaning |
|-------|------|---------|
| `first_motor` | First motor | One of `head`, `back`, `legs` or `feet`. |
| `second_motor` | Second motor | One of `head`, `back`, `legs` or `feet`. |
| `first_direction` | First direction | `up` or `down`. |
| `second_direction` | Second direction | `up` or `down`. |
| `duration_ms` | Duration in milliseconds | A number from 1 to 60000. |

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

## GM Control

<a id="gmmotor"></a>
**`gmmotor`**: Runs a GM Control setting or reading. Use the bed's buttons or Hold control for movement.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | One of `alarm` (Alarm tone), `alarm_at` (Alarm at a time), `alarm_cancel` (Cancel alarm), `repeat_alarm` (Repeating alarm), `repeat_delete` (Delete repeating alarm), `repeat_query` (Read repeating alarms), `light_color`, `light_timeout` (Light timer) and others; see the action in Home Assistant. |
| `value` | Operation value | A number from 0 to 65535. |
| `mode` | Alarm action | Text. |
| `slot` | Alarm number | A number from 0 to 255. |
| `hour` | Hour | A number from 0 to 23. |
| `minute` | Minute | A number from 0 to 59. |
| `enabled` | Enabled | Turn the selected option on or off. |
| `rgb_color` | RGB color | A color. |
| `part` | Report side | One of `left` or `right`. |
| `report_type` | Report period | One of `day` or `month`. |
| `report_date` | Report date | A date. |
| `height` | Desk height | A number from 0 to 2560. |
| `unit` | Height unit | One of `cm` (Centimeters) or `inch` (Inches). |

### GM Control


`adjustable_bed.gmmotor` runs the settings and readings the selected product supports.
Choose `device_id` and `operation`, with optional paired `side`. Every selected
target is validated before its operation is scheduled. Named product controls
use their button or `hold_control`; no raw-write action is exposed.

The [GM Control command reference](beds/gmmotor.md#specialized-actions) lists
countdown/repeat alarm, RGB/timeout, anti-snore, bottom massage timer and
sleep-name operations. The state sensor's `gmmotor_alarm_choices` attribute lists
the exact accepted `mode` names for that product. Countdown alarms use `value`
in minutes, or `alarm_at` with local `hour`/`minute`. Repeat records use `slot`,
`hour`, `minute` and `mode`. Alarm and light menus need the bed to report them
first. Set the bed clock with [`sync_clock`](#sync_clock).

Independent MM/SXB entries expose `sensor_time`, `sensor_part`,
`sensor_query_part`, `sensor_live`, `sensor_report`, `sensor_stop`, and the
SXB-only `sensor_sensitivity` query. Device-part setting uses `value` (MM1/2,
SXB 11/12/13). Reports use `part` (`left` or `right`), `report_type` (`day` or `month`)
and optional `report_date`. Live polling uses `enabled`. Local stop sends no
hardware STOP. The [sleep-module reference](beds/gmmotor.md#sleep-modules) records
the distinct wire builders and raw-data limitations.

## Galaxy

<a id="galaxy"></a>
**`galaxy`**: Sets the alarm, light and anti-snore options of a Galaxy bed.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Action | One of `single` (One-time alarm), `cancel_single` (Cancel one-time alarm), `repeat` (Repeating alarm), `enable_alarm` (Turn alarm on or off), `delete`, `alarms` (Read alarms), `light_color`, `light_duration` (Light timer) and others; see the action in Home Assistant. |
| `action` | Alarm action | Text. |
| `datetime` | Alarm date and time | ISO 8601 with a timezone offset. |
| `alarm_id` | Alarm slot | A number from 1 to 7. |
| `weekdays` | Repeat weekdays | Monday is 0, Sunday is 6. Empty means no repeat days. |
| `enabled` | Enabled | Turn the selected option on or off. |
| `seconds` | Light duration | Zero uses the app's always-on value. |
| `rgb_color` | Light color | A color. |
| `value` | Value (massage minutes or snore setting) | A number from 0 to 255. |

### Galaxy Bed Control configuration


`adjustable_bed.galaxy` configures the selected Galaxy bed's alarms, lights,
massage countdown and bed anti-snore settings. It uses the same fields as the
bed settings of `goodvibe`, with Galaxy's own product gates and record format.
Choose exact alarm action IDs from the [Galaxy command table](beds/richmat.md#galaxy-bed-control).
Relevant capability replies must have arrived on the current connection.
`enable_alarm` takes an observed `alarm_id` and `enabled`, preserving the
received time, action, reserved field and weekday mask.
Separate sleep-sensor operations are not offered.

## Good Vibe Sleep

<a id="goodvibe"></a>
**`goodvibe`**: Sets the alarm, light, massage and anti-snore options of a Good Vibe Sleep bed or its sleep sensor.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Action | One of `single` (One-time alarm), `cancel_single` (Cancel one-time alarm), `repeat` (Repeating alarm), `delete`, `alarms` (Read alarms), `light_color`, `light_duration` (Light timer), `light_off` and others; see the action in Home Assistant. |
| `action` | Alarm action | Text. |
| `datetime` | Alarm date and time | ISO 8601 with a timezone offset. |
| `alarm_id` | Alarm slot | A number from 1 to 7. |
| `weekdays` | Repeat weekdays | Monday is 0, Sunday is 6. Empty means no repeat days. |
| `enabled` | Enabled | Turn the selected option on or off. |
| `seconds` | Light duration | Zero uses the app's always-on value. |
| `rgb_color` | Light color | A color. |
| `value` | Snore count or time value | A number from 0 to 255. |
| `part` | Sleep part | Set type 1 to 1 or 2; type 2 to 11, 12 or 13. Report queries use 1 or 2. |
| `date` | Report date | A date. |
| `report_type` | Report type | Day is 1, month is 2. |

### Good Vibe Sleep configuration


`adjustable_bed.goodvibe` exposes product-gated alarm, light and snore settings plus independent sleep-sensor queries. Select an exact alarm action ID from the [command/profile tables](beds/richmat.md#alarms-and-snore-settings). Sleep reports use `operation: report`, a date, part and report type (1 day, 2 month); metadata, continuation and typed receipt form one operation. The status sensor retains typed reports and per-side live values. Use the app-labelled buttons for normal controls and the existing bounded `hold_control` action for held gestures. See the [protocol guide](beds/richmat.md#good-vibe-sleep) for every packet, profile gate and lifecycle limit.

## HJBed

<a id="hjbed"></a>
**`hjbed`**: Sets the alarm, light and other options of an HJBed bed. The bed must report the feature first.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | One of `single` (One-time alarm), `cancel_single` (Cancel one-time alarm), `repeat` (Repeating alarm), `delete`, `query` (Read current settings), `toggle` (Turn on or off), `sync` (Set bed clock), `light_timeout` (Light timer) and others; see the action in Home Assistant. |
| `action` | Alarm action | Text. |
| `time` | Time | A time of day. |
| `alarm_id` | Alarm number | Choose a slot from 1 to 7. Leave blank only to reuse a slot deleted during this Bluetooth connection. |
| `weekdays` | Weekdays (empty means once) | One of `monday`, `tuesday`, `wednesday`, `thursday`, `friday`, `saturday` or `sunday`. |
| `enabled` | Enabled | Turn the selected option on or off. |
| `seconds` | Light timeout in seconds | A number from 0 to 28800. |
| `rgb_color` | Light color | A color. |
| `mode` | Control mode | One of `split_head` (Separate heads) or `standard`. |

### HJBed configuration


`adjustable_bed.hjbed` exposes product-gated single/repeat alarms, alarm query/delete/toggle, clock synchronization, light timeout/RGB and Normal-layout control mode. Use the exact product alarm action key. All targets validate before writing; feature acknowledgements cannot override static profile flags. See the [operation fields and eligibility](beds/richmat.md#hjbed).

## Hush Base

<a id="hush_base"></a>
**`hush_base`**: Configure Hush Base bed or independent sleep sensor controls.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | Bed, light, alarm, sensor, or remote action to run. |
| `value` | Value | Duration or mode required by the selected operation. See the Casper Base guide for its units and range. |
| `rgb_color` | RGB color | Color for the selected light operation. |
| `enabled` | Enabled | Enable or disable the selected function. |
| `hour` | Alarm hour | Alarm hour in 24-hour time. |
| `minute` | Alarm minute | Minute within the selected alarm hour. |
| `mode` | Alarm preset | Position preset recalled by the alarm. |
| `slot` | Repeating alarm number | Existing or new repeating alarm identifier. |
| `days` | Weekdays | Days on which the repeating alarm runs. |
| `part` | Sensor partition | MM: 1 or 2. SXB: 11 for left, 12 for right, or 13 for both. |
| `report_type` | Report type | 1 for a daily report; 2 for a monthly report. |
| `year` | Report year | Year of the requested sensor report. |
| `month` | Report month | Month of the requested sensor report. |
| `day` | Report day | Day of month for a daily report. Use 1 for a monthly report. |
| `source` | Detector status sensor | External status sensor used by snore detection. |

### Hush Base


Use `adjustable_bed.hush_base` for Hush bed and independent sleep-module configuration. The [Hush guide](beds/hush-base.md#configuration-actions) lists the finite operations, profile gates and sensor partition domains; the [Richmat guide](beds/richmat.md#hush-base) has the packet formats.

## Jiecang

<a id="jiecang_stop_wake"></a>
**`jiecang_stop_wake`**: Stop active wake massage without disabling the stored weekly clock alarm.

<a id="jiecang_wake"></a>
**`jiecang_wake`**: Move to a preset and start the selected wake massage levels immediately.

| Field | Name | Meaning |
|-------|------|---------|
| `preset` | Bed preset | One of `flat`, `zero_g` (Zero gravity), `anti_snore` (Anti-snore), `memory_1` or `memory_2`. |
| `head_level` | Head massage level | Wake massage intensity, with 0 for off and 1 to 3 for increasing intensity. |
| `foot_level` | Foot massage level | Wake massage intensity, with 0 for off and 1 to 3 for increasing intensity. |

## Keeson app layouts

### Ergomotion 4.0


The [Ergomotion 4.0 profile](beds/keeson.md#ergomotion-40) exposes each selected product's
named action as a button. Held buttons work with `hold_control` (1–60000 ms);
the guide's command table lists each control key. Existing device/side targeting
routes P1 commands and cleanup through the same Left/Right child. A parent
target defaults to native Both. P2 products do not have a side field.

The `rename`, `sync_clock` and `set_alarm` actions also
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

## KomfyD and ComfyDS

<a id="comfy_control"></a>
**`comfy_control`**: Moves the bed or runs its timer and lock buttons.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | One of `zero` (Flat), `h_increase` (Head up), `h_decrease` (Head down), `f_increase` (Foot up), `f_decrease` (Foot down), `timer_start` (Start timer), `timer_stop` (Stop timer), `lock` and others; see the action in Home Assistant. |

### KomfyD / ComfyDS


`adjustable_bed.comfy_control` accepts `device_id`, optional paired `side`, and
`action`: `zero`, `h_increase`, `h_decrease`, `f_increase`, `f_decrease`,
`timer_start`, `timer_stop`, `lock`, `unlock`, or `query`. Timer duration uses
the Timer duration select; the Control lock and Timer switches send lock/unlock
and timer start/stop. H/F and timer buttons work as in the app. All targets are validated before any control
write. See the [profile guide](beds/kaidi.md#komfyd-and-comfyds).

## Lady Americana and partner beds

<a id="richmat_resource_bed"></a>
**`richmat_resource_bed`**: Control the selected app’s bed features. Query optional light support before changing its color or timeout. App commands do not certify a physical memory slot.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Action | Query features, set or cancel an alarm, change lighting, set a massage timer, or request an app command. |
| `actions` | Alarm actions | A position, optionally with massage, from the bed's alarm choices. |
| `time` | Alarm time | Next occurrence of this local time. An unset or matching time means tomorrow. |
| `rgb_color` | Light color | Red, green and blue values. |
| `seconds` | Light timeout | 0 to 300 seconds. Zero requests keep on. |
| `progress` | Massage timer choice | D1RM slider choice from 0 to 5. |
| `command` | App command | A command the app can request independently of the remote layout. Use Stop to release movement. |
| `duration_ms` | Hold duration | Duration for a held head or foot app command. |

### Lady Americana / ACAA / STA Homecare / Zero Gravity


`adjustable_bed.richmat_resource_bed` uses the explicitly selected app and layout.
It accepts a configured bed device (or several) and the usual paired `side`.

| Operation | Parameters | Availability |
|-----------|------------|--------------|
| `query` | none | Queries layout-owned alarms, LED support and the shared capability channel |
| `alarm` | `actions`, optional `time` | One layout-owned preset and optional massage choices, in the status entity's `alarm_actions` list |
| `cancel_alarm` | none | Sends the alarm cancellation pair to each selected bed |
| `rgb` | `rgb_color` | Requires an LED capability reply in the current session |
| `lamp_timeout` | `seconds` (0–300) | Requires that same reply; zero requests keep on |
| `massage_timer` | `progress` (0–5) | D1RM only |
| `bed_command` | `command`, optional `duration_ms` (1–60000) | The app's generic BED callback requests, independent of remote buttons |

For example, after choosing a layout with zero-gravity and head/foot massage
alarm choices:

```yaml
action: adjustable_bed.richmat_resource_bed
data:
  device_id: YOUR_BED_DEVICE_ID
  operation: alarm
  time: "07:00:00"
  actions: [zero_gravity, massage_head, massage_foot]
```

`bed_command` offers head/foot up/down, TV, lounge, zero gravity, anti-snore,
memory one/two/three, flat and the app's separate `voice_stop_request`.
Use the normal Stop action to release movement. An app memory request does not
prove a physical slot exists on the chosen bed. Other controls and programming
use the layout's labelled buttons. Current held-button metadata drives the
standard `hold_control` action and dashboard card.

All targets are validated before execution. STOP on a later target while an
earlier target awaits Bluetooth cancels that later target's admission. Both
holds require a topology that can maintain both links; sequential pairs use
one side at a time. Timer values and alarm selections are requests, not observed
device schedules or timer feedback. See the [protocol guide](beds/richmat.md#lady-americana--acaa--sta-homecare--zero-gravity-family).

## Leggett & Platt

<a id="leggett_sleep_timer"></a>
**`leggett_sleep_timer`**: Start a delayed preset or cancel the stored sleep timer.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | One of `start` or `cancel`. |
| `minutes` | Delay | Required to start. Prodigy accepts 1 to 1439 minutes; U Series accepts 15, 30, 45, 60, 75, or 90 minutes. |
| `preset` | Sleep action | Prodigy beds use memory 1 to 4. U Series beds use 0 for flat or memory 1 to 3; memory 3 is only reachable through this timer. |

## Limoss Remote

<a id="limoss_remote_calibrate"></a>
**`limoss_remote_calibrate`**: Runs the remote's calibration after you confirm, then releases the motors.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm calibration | Select true to confirm this device operation. |
| `duration` | Duration | Hold time in seconds, 0.1–60. |

<a id="limoss_remote_features"></a>
**`limoss_remote_features`**: Set local layout selections. Disabling a selected feature sends its ten OFF commands before saving.

| Field | Name | Meaning |
|-------|------|---------|
| `underbed_light` | Lamp controls | Show the app’s lamp action. |
| `massage` | Massage controls | Show the app’s massage actions. |

<a id="limoss_remote_rename_memory"></a>
**`limoss_remote_rename_memory`**: Rename a local memory. Empty names are permitted.

| Field | Name | Meaning |
|-------|------|---------|
| `preset` | Memory slot | Slot 1–8, limited by the device reply. |
| `name` | Name | Local display name, including an empty string. |

### Limoss Remote app


The explicit [Limoss Remote app profile](beds/limoss.md#limoss-remote) adds `limoss_remote_rename_memory`, `limoss_remote_calibrate` and `limoss_remote_features`, and supports [`hold_control`](#hold_control) and `goto_preset` with an optional recall `duration`. Holds accept 0.1–60 seconds. Calibration requires `confirmed: true`. Memory actions accept slots 1–8 within the live capacity; `save_preset` and `goto_preset` expose the same local slots. Rename permits an empty name. All selected targets are validated before writes; paired child targets and `side` retain their physical-target settings.

## Linak

<a id="linak_move_simultaneously"></a>
**`linak_move_simultaneously`**: Move two different sections with one native command (Linak Bed Control, Jensen JMC400), then send STOP.

| Field | Name | Meaning |
|-------|------|---------|
| `first_motor` | First motor | One of `base`, `feet`, `head`, `legs` or `back`. |
| `first_direction` | First direction | `up` or `down`. |
| `second_motor` | Second motor | One of `base`, `feet`, `head`, `legs` or `back`. |
| `second_direction` | Second direction | `up` or `down`. |
| `duration_ms` | Duration | How long to hold the combined movement before STOP. |

## Linx

<a id="linx_snore_intervention"></a>
**`linx_snore_intervention`**: Run the bed's anti-snore movement once, then ask the bed for its status. It does not listen for snoring.

| Field | Name | Meaning |
|-------|------|---------|
| `hold_minutes` | Hold duration | Minutes the bed holds the anti-snore position (default 10). |
| `up_speed` | Up speed | The app's up-speed setting (default 10). |
| `lift_time` | Lift time | The app's lift-time setting (default 10). |

The status query runs once on the same connection; it never reconnects. See the
[Linx guide](beds/linx.md).

## Logicdata

<a id="logicdata_hold_preset"></a>
**`logicdata_hold_preset`**: Hold a flat, preset or memory recall with repeated commands for a specified duration, then release.

| Field | Name | Meaning |
|-------|------|---------|
| `preset` | Preset | One of `flat`, `zero_g` (Zero gravity), `anti_snore` (Anti-snore), `memory_1` or `memory_2`. |
| `duration` | Duration | How long to hold, 0.2 to 60 seconds. |

## Luuna

<a id="luuna"></a>
**`luuna`**: Configure the Luuna alarm, light or query the bed-provided sleep accessory name. Requires the selected product and reported capability.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | Light, countdown alarm, local calendar or sleep-name action. |
| `value` | Value | Light duration in seconds (0, 300, 600 or 900), or warm/cold brightness percent (0–100). Zero duration means always on. |
| `rgb_color` | RGB color | Color for the selected light operation. |
| `hour` | Alarm hour | Alarm hour in 24-hour time. |
| `minute` | Alarm minute | Minute within the selected alarm hour. |
| `mode` | Alarm preset | Position preset recalled by the alarm. |

### Luuna +


`adjustable_bed.luuna` controls the selected Rise, Rise Pro or Rise Pro Light
profile. See the [Luuna + profile](beds/richmat.md#luuna-) for its capability gates.
Choose `alarm` with `hour`, `minute` and `mode` (`anti_snore`, `zero_g`, `tv`,
`memory_1` or `memory_2`, as the product offers), or `alarm_cancel`.
Light operations are `light_rgb` (`rgb_color`), `light_warm` / `light_cold`
(`value`, 0–100 percent brightness), `light_seconds` (`value`, 0/300/600/900),
and `light_off`. Zero duration means always on. `sleep_name` queries the
bed-provided accessory name for Rise and Rise Pro Light; `time_sync` sends the
local calendar. Each target is validated before any writes. Not yet confirmed on a real bed.

## Luuna Rise and Power Cool

<a id="richmat_rise"></a>
**`richmat_rise`**: Bed settings for Luuna Rise and Power Cool beds. Alarm and lamp settings need the bed to report them first.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | One of `query` (Read current settings), `alarm` (Alarm tone), `cancel_alarm`, `rgb` (Light color), `lamp_timer`, `massage_timer`, `massage_popup` (Massage menu), `diagnostic_cycle` (Test cycle) and others; see the action in Home Assistant. |
| `actions` | Alarm actions | Alarm actions such as node_1, as listed under alarm actions in the bed's diagnostics. The first bed action and the massage choices decide what the alarm does. |
| `time` | Alarm time | Next occurrence of this local time, with minute precision. Omit for 1440 minutes. |
| `rgb_color` | RGB color | A color. |
| `seconds` | Lamp timer | Lamp timer, 0 to 300 seconds. |
| `timer_save` | Use save encoding | Saves the timer the way the app's Save button does, instead of the way releasing the slider does. |
| `progress` | Massage timer index | The app's slider position, 0 to 5, on D1RM and D9RM models. |
| `popup` | Timer popup choice | Massage timer choice from the remote: 15, 30 or 45 minutes, or on and off. |
| `schedule` | Motor schedule | Power Cool RMCS only. records: twelve [order, run_seconds, rest_seconds] rows in fixed M1/M2/M3/M4/M12/M34 up/down order; rest and count: nonnegative integers; radio: rf or ble; code: new or old; identifier: 1 to 9; motors: permutation of [1,2,3,4]. A running schedule cannot be stopped or read back. |

### Luuna Rise / Power Cool bed settings


`adjustable_bed.richmat_rise` targets the exact selected app and layout. Use
`query` to refresh alarm and lamp capability, `alarm` / `cancel_alarm` for the
bed's countdown, `rgb` for a three-byte color, and `lamp_timer` with `seconds`
(0–300) and optional `timer_save` to select the app's zero encoding. `actions`
is a list of `node_<number>` keys from the device's `alarm_actions` diagnostics.
Only that layout's choices are accepted. `time` is the next local occurrence;
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
field is part of the BLE program. A running program cannot be stopped or read back.
These operations use movement scheduling. Luuna's manufacturing layouts,
standalone desks, networks and separate accessories are not service targets.

See the [generated command tables](beds/richmat.md#luuna-rise--power-cool).

## M Line

<a id="mline_command"></a>
**`mline_command`**: Sets sleep privacy or anti-snore, reads the current settings or alarm, or downloads sleep history.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | One of `privacy`, `anti_snore` (Anti-snore), `anti_snore_demo` (Anti-snore demo), `settings_refresh` (Read settings), `alarm_refresh` (Read alarm), `live_query` (Read live data), `history_read` (Read sleep history) or `history_ack` (Confirm sleep history received). |
| `enabled` | Enabled | Turn the selected option on or off. |
| `angle` | Angle | One of `1` (Low), `3` (Medium) or `6` (High). |
| `position` | Position | One of `1` (Head) or `2` (Elevation). |
| `all_records` | All records | On or off. |
| `transfer` | Transfer | The transfer code from a finished sleep history download, to confirm you received it. |

### M Line


Choose the M Line app and physical layout in setup or Configure. Covers and
preset buttons support held control and the dashboard card's renewable leases.
Clock synchronization uses `sync_clock`; the bed's wake alarm uses
[`set_alarm`](#set_alarm).

`mline_command` takes `device_id`, optional `side`, and an `action`:

| Action | Fields / behavior |
|---|---|
| `privacy` | Sleep only; `enabled` |
| `anti_snore` | Sleep only; `enabled`, angle `1`, `3` or `6`, position `1` (head) or `2` (elevation) |
| `anti_snore_demo` | Sleep only; `position` |
| `settings_refresh` | Settings-page state request, independent of the normal protocol-gated query |
| `alarm_refresh` | Clock sync, then alarm query |
| `live_query` | Sleep only; raw sensor query |
| `history_read` | Sleep only; exactly one physical side, optional `all_records`; returns raw groups and a `transfer` token |
| `history_ack` | Same live connection; acknowledge the completed `transfer` token once, after consuming the result |

History reads stop at one second idle or the 30-second/8192-record ceiling.
They do not automatically acknowledge or generate sleep reports. Consume the
raw result before acknowledging it; reconnect and cancellation invalidate its
token, which also expires 30 seconds after completion. This explicit consumer boundary replaces the app's phone report/SQL
processing, without claiming SQL success. See the [M Line guide](beds/mline.md)
for field projections, source limitations and the external hardware test status.

## Majestic Home

<a id="majestichome"></a>
**`majestichome`**: Read, create, edit, turn on or off, or delete the bed's alarms. Set the clock with Set bed clock.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | One of `list` (Read alarms), `new` (New alarm), `set` (Set alarm), `toggle` (Turn alarm on or off) or `delete` (Delete alarm). |
| `alarm_id` | Alarm number | Needed to create, edit, turn on or off, or delete an alarm: 1 to 7 for a new alarm, or the number the bed reported. A partial list cannot show which numbers are free. |
| `hour` | Hour | A number from 0 to 23. |
| `minute` | Minute | A number from 0 to 59. |
| `preset` | Preset | One of `zero_gravity`, `anti_snore` (Anti-Snore), `memory_1` or `memory_2`. |
| `weekdays` | Weekdays | Leave empty for a one-time alarm. |
| `enabled` | Enabled | On or off. |

### Majestic Home settings

Supply an explicit `alarm_id` for `new`, `set`, `toggle` and `delete`.
New IDs use 1 through 7. Partial alarm replies cannot prove a free slot, so
Home Assistant never chooses an ID automatically. Sequential pairs refresh
required fields on the execution connection; toggles reject changed fields.

`adjustable_bed.majestichome` accepts `operation: list`, `new`, `set`, `toggle`
or `delete`; set the clock with [`sync_clock`](#sync_clock). Select a configured Majestic Home device or a native
paired parent/child, with `side` when needed. Alarm operations require the current
connection's clock response. FARM/JLRM accept `preset: zero_gravity`,
`anti_snore`, `memory_1` or `memory_2`, `hour`, `minute`, `weekdays` (Monday 0
through Sunday 6) and `enabled`. An empty weekday list means once.

Supply `alarm_id` explicitly for `new`, `set`, `toggle` or `delete`.
Neither an empty nor a nonempty cache proves which IDs are free.
Every `toggle` reads the requested ID on the current connection before changing
only its enable bit. Missing or changed fields refuse the write.
`list` keeps each physical connection open for a fixed five-second observation
window from query submission. It optionally returns `targets`, one result per
physical address and `side`, containing copied `alarms` and `complete: false`.
These are partial observations, including when the array is empty; neither
silence nor elapsed time proves the bed has no other alarms. Sequential sides
disconnect after their window, and returned snapshots cannot authorize mutations.
The received records are attributes of the diagnostic Model sensor, which is
disabled by default: enable it to read them. See the
[Majestic Home profile](beds/richmat.md#majestic-home).

## MLILY

<a id="mlily"></a>
**`mlily`**: Configure this MLILY product or its independent MM/SXB sleep receiver.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Action | One of `single` (One-time alarm), `cancel_single` (Cancel one-time alarm), `repeat` (Repeating alarm), `delete`, `alarms` (Read alarms), `light_color`, `light_duration` (Light timer), `light_off` and others; see the action in Home Assistant. |
| `action` | Alarm action | Text. |
| `datetime` | Alarm date and time | ISO 8601 with a timezone offset. |
| `alarm_id` | Alarm slot | A number from 1 to 7. |
| `weekdays` | Repeat weekdays | Monday is 0, Sunday is 6. Empty means no repeat days. |
| `enabled` | Enabled | Turn the selected option on or off. |
| `seconds` | Light duration | Zero uses the app's always-on value. |
| `rgb_color` | Light color | A color. |
| `value` | Snore count or time value | A number from 0 to 255. |
| `part` | Sleep part | Set type 1 to 1 or 2; type 2 to 11, 12 or 13. Report queries use 1 or 2. |
| `date` | Report date | A date. |
| `report_type` | Report type | Day is 1, month is 2. |
| `alarm_record` | Observed alarm record | The alarm as the bed reported it, so editing keeps the same alarm. |
| `left` | Left sleep operand | SXB anti-snore number or numeric list. |
| `right` | Right sleep operand | SXB anti-snore number or numeric list. |

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

## MLILY Remote

<a id="mlily_remote"></a>
**`mlily_remote`**: Set the MS600 countdown alarm, or run the MS300-SH anti-snore movement on the left side. Set the clock with Set bed clock.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | One of `alarm` (Set alarm), `alarm_cancel` (Cancel alarm) or `anti_snore` (Anti-snore intervention). |
| `hour` | Alarm hour | Alarm hour in 24-hour time. |
| `minute` | Alarm minute | Minute within the selected alarm hour. |
| `mode` | Alarm position | Position the bed moves to when the alarm goes off. |

### MLILY Remote settings

`adjustable_bed.mlily_remote` controls MS600 countdown alarms (`alarm`,
`alarm_cancel`) and the direct default-left `anti_snore` action; set the clock
with [`sync_clock`](#sync_clock). Alarm mode choices and connection gates are documented in
the [MLILY Remote guide](beds/richmat.md#mlily-remote). All selected targets are
validated before commands run. Two separate receivers keep their own side. When
both sides share one receiver, select the bed for the alarm, which runs once;
the anti-snore intervention runs on the left.

## Motion Bed

<a id="motion_bed_action"></a>
**`motion_bed_action`**: Run a control by its name, as listed in the bed's diagnostics. Saving, clearing, resetting and changing modules need confirmation.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm persistent change | On or off. |
| `action` | Action | Text. |
| `branch` | Branch | One of `app`, `save` or `clear`. |
| `duration` | Duration | A number from 0.01 to 10. |

<a id="motion_bed_air_setting"></a>
**`motion_bed_air_setting`**: Query or save the selected mode’s upper gear and optional timer. Lower pressure is readback only.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm persistent change | On or off. |
| `mode` | Mode | A number. |
| `query` | Query | On or off. |
| `gear` | Gear | A number. |
| `timer` | Timer | A number. |

<a id="motion_bed_audio"></a>
**`motion_bed_audio`**: Select a track, preview a track, or set volume on a target that reports audio support.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm persistent change | On or off. |
| `operation` | Operation | One of `track` or `volume`. |
| `value` | Value | A number. |
| `preview` | Preview | On or off. |

<a id="motion_bed_calibration"></a>
**`motion_bed_calibration`**: Save the app’s flat and side calibration readings. Confirm before changing calibration.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm persistent change | On or off. |
| `flat` | Flat | A number from 0 to 2.14748e+09. |
| `side_position` | Side position | A number. |

<a id="motion_bed_module"></a>
**`motion_bed_module`**: Lists, adds or removes the motor, air or heating modules of a Motion Bed hub. Adding and removing need confirmation.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm persistent change | On or off. |
| `operation` | Operation | One of `query` (Read current settings), `bind` (Add) or `delete`. |
| `module_type` | Module type | A number. |
| `address` | Address | Text. |

<a id="motion_bed_pressure"></a>
**`motion_bed_pressure`**: Adjusts one air channel, or saves all twelve air pressures at once.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm persistent change | On or off. |
| `operation` | Operation | One of `live` or `save`. |
| `channel` | Channel | A number from 0 to 11. |
| `value` | Value | A number. |
| `values` | Values | A list of whole numbers, one per channel, for `save`. |

<a id="motion_bed_sleep_angles"></a>
**`motion_bed_sleep_angles`**: Saves the four flat and four side-sleeping positions used by sleep sensing. Use the values shown in the app.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm persistent change | On or off. |
| `page` | Page | A number. |
| `flat` | Flat | A list of whole numbers: the flat positions the app shows. |
| `side_positions` | Side positions | A list of whole numbers: the side-sleeping positions the app shows. |

<a id="motion_bed_sleep_report"></a>
**`motion_bed_sleep_report`**: Read current, historical day, month or timer data. Historical day selection and graph window offset are separate.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm persistent change | On or off. |
| `kind` | Kind | One of `month`, `real` (Live), `timer` or `day`. |
| `offset` | Offset | A number from 0 to 29. |
| `window_offset` | Window offset | A number from 0 to 4. |

<a id="motion_bed_sleep_timer"></a>
**`motion_bed_sleep_timer`**: Select an app bedtime or fall timer slot.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm persistent change | On or off. |
| `slot` | Slot | A number. |
| `fall` | Fall | On or off. |

<a id="motion_bed_thermal_schedule"></a>
**`motion_bed_thermal_schedule`**: Save a timer with cooling or heating mode and gear, without guessing a thermostat setpoint.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm persistent change | On or off. |
| `hour` | Hour | A number from 0 to 23. |
| `minute` | Minute | A number from 0 to 59. |
| `mode` | Mode | A number. |
| `gear` | Gear | A number. |

### Motion Bed app actions


The [Motion Bed action index](beds/ff_frame.md#services-2) covers all 12 typed app actions, including alarms, sleep calibration/reporting, hub modules, pressure, thermal schedules and audio. Named action keys are listed in controller diagnostics. Persistent changes require confirmation; every target is validated before writes, and native paired child targets retain their side.

## MotoMotion

<a id="motomotion"></a>
**`motomotion`**: Save body measurements and your own posture positions on MotoMotion beds whose app has a users tab. Measurements are height, buttocks height and knee height in centimetres. This does not read where the motors are.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | Save, select or delete a user, or recall, save, reset or fine tune a posture. |
| `user` | User | Name of the local user to save or select. |
| `dimensions` | Body measurements | Three finite numbers in order: height, buttocks height and knee height, in centimetres. |
| `posture` | Posture | Upright, recline, TV or lay posture. |
| `targets` | Posture positions | Position for each of the five motors (head, base, back, lumbar and tilt), within the app's slider range. |

## Nisco and MLILY Supreme

<a id="richmat_mh_control"></a>
**`richmat_mh_control`**: Run one of the selected app and model's controls, read one setting from the bed, or set the app mode used by later controls.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | One of `press` (Press control), `remote_long` (Save with remote button), `query` (Read setting) or `app_mode` (Set app mode). |
| `control` | Control | The control's name, as its button or the app shows it, such as Flat, Memory 1, Save M1 or Massage: Mode. Add up or down for a motor, such as Back up. |
| `query` | Setting to read | One of `version` (Firmware version), `exit_one_minute` (Leave one-minute mode), `alarm`, `light`, `mattress`, `waist_mattress`, `snore` (Snore intervention), `diagnostics` (Component check) and others; see the action in Home Assistant. |
| `transmit_mode` | Transmit mode | The app's transmit mode for later control and release frames (Set app mode). |
| `motor_group` | Motor group | The app's motor group, which decides the Motor mode choices (Set app mode). |

<a id="richmat_mh_sleep_mode"></a>
**`richmat_mh_sleep_mode`**: Set the separate sleep sensor for one or two sleepers.

| Field | Name | Meaning |
|-------|------|---------|
| `mode` | Sleepers | One of `single` (One sleeper) or `double` (Two sleepers). |

### Nisco and MLILY Supreme controls

`adjustable_bed.richmat_mh_control` accepts `action: press` and a `control`
named as its button or the app shows it (add `up` or `down` for a motor, such
as `Back up`), `action: remote_long` for an attached fixed-remote save, or
`action: query` and one named included query. Each model resolves the name
against its own app page; a name it does not have is rejected.
The fixed-remote long action waits three seconds, sends the finalized save and
releases through that caller's sequence. STOP cancels admission or execution.
`action: app_mode` sets the app's local `transmit_mode` (`mode_0`, `mode_1` or `mode_2`) and/or
`motor_group` (`single`, `group_sync` or `group_split`, as the model declares)
for later commands on that physical side. It neither connects nor waits for a
running command, and sends nothing itself. The motor group decides which Motor
mode choices are offered.

`richmat_mh_sleep_mode` keeps Nisco's direct single/double user-mode caller;
MLILY Supreme does not have it. Alarms use the shared `set_alarm` action with the
alarm page the bed reports; light colour uses `richmat_mh_light_color`. A normal
mattress alarm requires its explicit extra selection and powered initialization.
The separate HJ_Bed receiver exposes local sensing/intervention entities and no
bed motor actions.

Each action captures physical targets before its first await and validates the
whole selection before sending control frames. A paired child target retains
its side. Transmit modes and mattress pad selectors do not choose another BLE
recipient or create one-address native Left/Right devices.

## OKIN SleepEase

<a id="doublesleep_configure"></a>
**`doublesleep_configure`**: Alarm, anti-snore, sensor settings, report retrieval and named preset programming for the SleepEase app profile. Reports remain on the selected physical bed's report sensors.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | One of `alarm` (Alarm tone), `anti_snore` (Anti-snore), `anti_snore_demo` (Anti-snore demo), `sensitivities` (Sensitivity), `report` (Sleep report), `save_preset` or `capabilities` (Read features). |
| `hour` | Alarm hour | A number from 0 to 23. |
| `minute` | Alarm minute | A number from 0 to 59. |
| `weekdays` | Repeat on | Leave empty for a one-time alarm at the next occurrence of the selected time. |
| `alarm_preset` | Alarm action | One of `zero_g` (Zero gravity), `flat`, `memory_1`, `memory_2` or `vibration`. |
| `alarm_massage` | Alarm massage | On or off. |
| `mode` | Anti-snore mode | A number from 1 to 3. |
| `pwm` | Anti-snore strength | Anti-snore movement strength. |
| `timer` | Anti-snore time | Anti-snore movement time. |
| `sensor_side` | Sensor sides | The app's sensor side setting, 1, 2 or 3. Omit to keep the reported setting. Some models can only read it. |
| `left_sensitivity` | Left sensitivity | Omit to retain the reported value. |
| `right_sensitivity` | Right sensitivity | Omit to retain the reported value. |
| `date` | Report date | A date. |
| `report_side` | Report sensor side | One of `left` or `right`. |
| `report_kind` | Report period | One of `day` or `month`. |
| `preset` | Preset to program | One of `memory_1`, `memory_2`, `anti_snore` (Anti-snore), `lounge`, `tv` or `zero_g` (Zero gravity). |
| `capability_page` | Feature list | Which feature list to read from the bed. |

### OKIN SleepEase / DoubleSleep


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

## Octo

<a id="octo_enroll_pin"></a>
**`octo_enroll_pin`**: Set a new four-digit PIN on one unlocked OCTO Smart Control receiver. Enter the same PIN twice. Home Assistant saves it for reconnects after sending the command.

| Field | Name | Meaning |
|-------|------|---------|
| `octo_pin` | New PIN | The four digits to set on the receiver. |
| `octo_pin_confirmation` | Confirm PIN | Enter the same four digits again. |

<a id="octo_reset_defaults"></a>
**`octo_reset_defaults`**: Restore receiver defaults after explicit confirmation. The receiver disconnects five seconds after the reset command.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm reset | Set to true only when you intend to reset this receiver. |

## Okimiki

<a id="okimiki"></a>
**`okimiki`**: Press or save a control, set the light, or read and set the alarms of the selected Okimiki product. Set the clock with Set bed clock.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | One of `press`, `save`, `light_color`, `light_duration`, `light_off`, `single` (Set one-time alarm), `cancel_single` (Cancel one-time alarm), `alarms` (Read alarms) and others; see the action in Home Assistant. |
| `control` | Control | One of `head_up`, `head_down`, `foot_up`, `foot_down`, `head_foot_up` (Head and foot up), `head_foot_down` (Head and foot down), `flat`, `memory_1` and others; see the action in Home Assistant. |
| `duration_ms` | Press duration | A number from 0 to 60000 ms. |
| `datetime` | Alarm time | A date and time. |
| `alarm_id` | Alarm slot | Choose 1 through 7 explicitly when creating an alarm. Read the alarms first (the Alarms sensor lists them) before editing, turning on or off, or deleting one. |
| `mode` | Wake action | One of `lounge`, `zero_gravity`, `memory_1` or `memory_2`. |
| `weekdays` | Weekdays | Days the alarm repeats. An empty list sets a one-time alarm; leaving the field out keeps an edited alarm's days. |
| `enabled` | Enabled | On or off. |
| `seconds` | Light duration | Zero keeps the light on. |
| `rgb_color` | RGB color | A color. |

### Okimiki controls and alarms


Use `adjustable_bed.okimiki` with `device_id` (one or several physical beds or
native paired-side devices) and `operation`. The selected product controls
which operations are available. `press` takes `control` and `duration_ms`;
`save` waits for the preset's three-second threshold. Standard covers, memory
buttons and renewable `hold_control` also use the same product-owned session.

Lighting operations are `light_color` (`rgb_color`), `light_duration` (`seconds`,
0 to 900, zero always on), and `light_off`, after a light capability reply.
Set the clock with [`sync_clock`](#sync_clock).

IQRM offers `single` (`datetime`, lounge) and `cancel_single`. KWRN offers
`alarms`, `repeat` (`datetime`, `mode`, optional `weekdays` and `enabled`),
`enable` and `delete`. Read the list with `alarms` before editing a slot with
`alarm_id`; the Alarms diagnostic sensor (disabled by default) lists the received
slots with time, wake action, weekdays and on/off. An edit keeps omitted received
fields and the reserved byte. An empty `weekdays` list means once; leaving the
field out keeps an edited alarm's days.
Alarm operations require the current session's clock capability reply. These
are direct bed requests, not confirmed firmware schedules.

Okimiki alarms are not on [`set_alarm`](#set_alarm) yet. That action does not yet
have the safeguards this bed's record edits need across a paired hand-over,
between the check and the write, and when Stop interrupts the check.

## Power Bob Base

<a id="bobpowerbase"></a>
**`bobpowerbase`**: Manage repeat alarms or set the light, when the bed reports them. Set the clock with Set bed clock.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Action | One of `repeat` (Save repeating alarm), `delete` (Delete alarm), `alarms` (Read alarms), `light_color` (Set light color), `light_duration` (Set light duration) or `light_off` (Turn light off). |
| `action` | Alarm preset | One of `anti_snore` (Anti-snore), `zero_gravity`, `tv`, `memory_1` or `memory_2`. |
| `datetime` | Alarm date and time | ISO 8601 with a timezone offset. |
| `alarm_id` | Alarm slot | Use an explicit slot when the reported alarm list may be incomplete. |
| `weekdays` | Repeat weekdays | Monday is 0, Sunday is 6. Empty means once. |
| `enabled` | Enabled | On or off. |
| `seconds` | Light duration | Whole minutes from 0 to 15, supplied as seconds. Zero means always on. |
| `rgb_color` | Light color | A color. |

### Power Bob Base configuration

`adjustable_bed.bobpowerbase` manages repeat alarms and changes lighting after
the connected bed reports its light menu; set the clock with
[`sync_clock`](#sync_clock). Use `repeat`, `delete`, `alarms`, `light_color`, `light_duration` or
`light_off`. Alarm presets are `anti_snore`, `zero_gravity`, `tv`, `memory_1`
and `memory_2`; a new alarm takes a timezone-aware `datetime`. Weekdays use
Monday=0 through Sunday=6, with an empty list for once, and `enabled` controls
the low repeat bit. Supply `alarm_id` explicitly when the observed list may be
incomplete. Light duration is a whole minute from 0 to 15, supplied as seconds;
zero means always on. RGB channels use `rgb_color`.

The normal buttons expose product-specific movement, recall and programming.
Held movement uses `hold_control` with its declared `goodvibe_` control key.
SH products have framed Left/Right controls; a raw Nordic command cannot
address Right. Renewable Both requires simultaneous side execution; finite
holds can run serially. See [Power Bob Base](beds/richmat.md#power-bob-base).

## RMControl

<a id="rmcontrol_anti_snore"></a>
**`rmcontrol_anti_snore`**: Turns anti-snore on or off, or sets how it responds to snoring.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | One of `switch` (Turn on or off), `configure` (Settings) or `query` (Read current settings). |
| `enabled` | Enabled | Turn anti-snore on or off. |
| `mode` | Configuration mode | Required for configure. |
| `value` | Intervention value | How many nudges, or how long, depending on the mode. |

## Reverie

<a id="reverie_pairlink_alarm_comfort"></a>
**`reverie_pairlink_alarm_comfort`**: Send the complete Pairlink alarm comfort sequence, including unchanged values.

| Field | Name | Meaning |
|-------|------|---------|
| `comfort` | Comfort values | All seven Pairlink comfort values. Every selected Pairlink target is checked before any write. |

<a id="reverie_run_routine"></a>
**`reverie_run_routine`**: Run a routine of comfort steps on the selected Reverie bed. It replaces any routine the bed is running.

| Field | Name | Meaning |
|-------|------|---------|
| `steps` | Steps | The comfort settings to apply, in order, each with a duration in minutes. Pairlink beds skip settings you leave out and use at least one minute per step; other Reverie beds need a duration for every step. Use an automation to choose when the routine starts. |

<a id="reverie_set_comfort"></a>
**`reverie_set_comfort`**: Send one validated composite Reverie comfort setting to every selected target.

| Field | Name | Meaning |
|-------|------|---------|
| `comfort` | Comfort values | Head, foot, lumbar, massage, timer and mode values. Each selected bed is checked before any changes. |

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

Use Home Assistant automations to schedule direct Reverie actions such as
`reverie_set_comfort`, `reverie_run_routine`, `goto_preset`, and `save_preset`.
Phone-local alarm storage, Android notification delivery, and the phone's
alarm scheduler are outside the integration's scope.
Reported state remains the last measured value until feedback arrives. See
[position state and freshness](TROUBLESHOOTING.md#position-commands-and-reported-state).

## Richmat (classic apps)

<a id="richmat_classic"></a>
**`richmat_classic`**: Settings for Avocado Eco Base, CoasterSleep, Forty Winks, Milemont and Superior beds.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | One of `query` (Read current settings), `alarm` (Alarm tone), `cancel_alarm`, `rgb` (Light color), `lamp_slider` (Lamp brightness), `lamp_save` (Save lamp setting), `aroma`, `massage_timer` and others; see the action in Home Assistant. |
| `action` | Layout alarm action | Text. |
| `time` | Alarm time | A time of day. |
| `minutes` | Lamp minutes | A number from 0 to 15. |
| `rgb_color` | RGB color | A color. |
| `aroma_times` | Aroma times | Three whole numbers, as the app shows them. |
| `progress` | Massage timer slider | A number from 0 to 5. |
| `height` | Desk target | A number from 0 to 6553. |
| `unit` | Desk unit | One of `cm` (Centimeters) or `inches`. |
| `slot` | Desk button | A number from 1 to 4. |
| `popup` | Massage popup choice | One of `15` (15 minutes), `30` (30 minutes), `45` (45 minutes) or `toggle` (Turn on or off). |
| `duration_ms` | Desk button duration | Bounded duration in milliseconds. |

### Classic Richmat app settings


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

## Richmat app

<a id="richmat_app"></a>
**`richmat_app`**: Sets the light, alarm, sleep sensing and other options of a Richmat app bed. Read the feature first before changing it.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | Operation |
| `value` | Value | Value |
| `mode` | Mode | Mode |
| `enabled` | Enabled | Enabled |
| `rgb_color` | Rgb color | Rgb color |
| `opacity` | Opacity | Opacity |
| `zone` | Zone | Zone |
| `temperature` | Temperature | Temperature |
| `flags` | Flags | Flags |
| `sleep` | Sleep | Sleep |
| `weekdays` | Weekdays | Weekdays |
| `steps` | Steps | Steps |
| `action` | Action | Action |
| `query` | Query | Query |
| `datetime` | Datetime | Datetime |
| `alarm_id` | Alarm number | Alarm id |
| `cycle` | Cycle | Cycle |
| `part` | Part | Part |
| `report_type` | Report type | Report type |

<a id="richmat_mh_aroma"></a>
**`richmat_mh_aroma`**: Write the three aroma timing sliders of a Richmat MH app profile.

| Field | Name | Meaning |
|-------|------|---------|
| `mode2_startup_minutes` | Mode 2 startup | Minutes, 1 to 60. |
| `mode3_startup_minutes` | Mode 3 startup | Minutes, 1 to 60. |
| `mode3_pause_hours` | Mode 3 pause | Hours, 1 to 12. |

<a id="richmat_mh_light_color"></a>
**`richmat_mh_light_color`**: Write the LED or button-light page colour of a Richmat MH app profile.

| Field | Name | Meaning |
|-------|------|---------|
| `rgb_color` | Colour | Red, green and blue, 0 to 255. |

### Richmat app aroma, light and alarms

Bed and vibrating-mattress alarms use [`set_alarm`](#set_alarm); the bed counts
down to the alarm time, and the mattress alarm runs once or every day.
`richmat_mh_aroma` sends the aroma page's three timing settings, and
`richmat_mh_light_color` sets the light color on models without a light on/off
button.

### Richmat 4.2.0 configuration


`adjustable_bed.richmat_app` exposes product-gated lighting, alarms, blanket,
detection, anti-snore/off-bed, USB and cancellable demos. Sleep operations target
a separate Richmat sleep entry. See the [operation and parameter reference](beds/richmat.md#richmat-420).

## Rize

<a id="rize_program_preset"></a>
**`rize_program_preset`**: Store the current position as a default preset on one physical Rize bed. Select one side of a combined bed and explicitly confirm.

| Field | Name | Meaning |
|-------|------|---------|
| `preset` | Preset | One of `zero_g` (Zero gravity), `anti_snore` (Anti-snore), `book` or `leisure`. |
| `confirm` | Confirm programming | On or off. |

### Rize Beds default-preset programming


`adjustable_bed.rize_program_preset` accepts `device_id`, `preset` (`zero_g`,
`anti_snore`, `book`, `leisure`) and required `confirm: true`. It requires an
extended Rize product and one physical target. Reading (`book`) programming
requires layout5/6 (products135/136/140); Reading recall is also available on7/8. For a combined bed, select its
child device or specify `side: left` or `side: right`; Both and multi-target
programming are rejected. It writes once to that selected target, with no
preliminary memory-slot write. See the [Rize guide](beds/kaidi.md#rize-beds).

## Sleep Number

<a id="sleep_number_command"></a>
**`sleep_number_command`**: Runs a Sleep Number control or reading. Readings return their results. See the actions guide for each command's options.

| Field | Name | Meaning |
|-------|------|---------|
| `command` | Command | Only commands supported by the selected bed can run. |
| `parameters` | Parameters | Command-specific fields. Unknown fields and values are rejected. Parameter side cannot override the selected physical side. |

## SleepEvolution and W.Silver Products 3.x

<a id="richmat_legacy"></a>
**`richmat_legacy`**: Run a control from the selected app and name prefix, as a press or a save.

| Field | Name | Meaning |
|-------|------|---------|
| `control` | Control | Control key from the selected profile in the Richmat guide. |
| `operation` | Operation | Press runs the control as the app's button does, so pressing a preset longer than the app's save time also saves it. Save runs only the save step. |
| `duration_ms` | Press length | Milliseconds, 1 to 60000. Applies to a press only. |
### SleepEvolution and W.Silver Products 3.x controls

`adjustable_bed.richmat_legacy` runs a listed profile `control` with
`device_id` and optional paired `side`. Use the exact control keys from the
selected app and prefix in the
[Richmat guide](beds/richmat.md#sleepevolution--wsilver-products-3x).

| Field | Behavior |
|---|---|
| `operation: gesture` (default) | Run the control's DOWN, scheduled refresh and release phases, including its short-recall or long-save boundary. |
| `duration_ms` | Gesture duration, 1–60000 ms, default 1000. Motion with only `m` on DOWN waits for its first actual movement refresh before this active window starts. Other finite wire gestures retain their DOWN-to-release interval. |
| `operation: program` | Only for a control with a proven save event. Wait for the first completed save write, then release. Uses a bounded elapsed budget rather than `duration_ms`; cancellation suppresses short recall. |

For example, this recalls the displayed M1 control on the **A1** profile:

```yaml
action: adjustable_bed.richmat_legacy
data:
  device_id: YOUR_BED_DEVICE_ID
  control: h26_lounge
  operation: gesture
  duration_ms: 100
```

For that same A1 control, `operation: program` saves M1. Control names and
displayed slots differ by profile; generic numeric memory actions are
unavailable. Finite `hold_control` gestures preserve their recall/save boundary.
Native renewable holds admit proven motion only, excluding programming,
countdown and massage. Local selectors and cancellation-only actions send no
wire packet of their own.

All batch targets pass admission before writes. Single-address side selection
and sequential Both holds are unsupported. Release drains on the original
physical connection independently of cancellation, and unconditional cleanup is
attempted even if a short-recall write fails. No arbitrary bytes, phone-torch or
network/account actions are accepted. Hardware behavior remains unverified.

## Sleeptracker

<a id="sleeptracker_climate"></a>
**`sleeptracker_climate`**: Set the left, right or both fan modes and levels. Level 0 stops the selected fans. Heat runs for one hour and cool for ten hours. The bed does not report the time left.

| Field | Name | Meaning |
|-------|------|---------|
| `fan_side` | Fan zone | One of `both`, `left` or `right`. |
| `mode` | Mode | One of `heat` or `cool`. |
| `level` | Level (0 off, 1–3) | A number from 0 to 3. |
| `constant` | Constant level (off selects curve) | On or off. |

<a id="sleeptracker_massage"></a>
**`sleeptracker_massage`**: Steps a massage zone or pattern, picks a vibration speed, or stops the massage.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | One of `head`, `foot` (Feet), `pattern`, `28hz` (28 Hz vibration), `40hz` (40 Hz vibration) or `off`. |

<a id="sleeptracker_preset"></a>
**`sleeptracker_preset`**: Moves to or saves a preset. The presets depend on the bed.

| Field | Name | Meaning |
|-------|------|---------|
| `preset` | Preset | One of `all_flat` (Flat), `zero_g` (Zero gravity), `anti_snore` (Anti-snore), `user_favorite` (Favorite), `tv_pc` (TV and computer) or `favorite_2`. |
| `save` | Save current position | On or off. |

<a id="sleeptracker_relaxation"></a>
**`sleeptracker_relaxation`**: Starts the wind-down routine or the bed's relaxation movement.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | One of `wind_down_1`, `wind_down_2` or `local_animation` (Light animation). |

<a id="sleeptracker_wave"></a>
**`sleeptracker_wave`**: Starts a wave massage at the chosen speed and for the chosen time. Use Stop massage to end it early.

| Field | Name | Meaning |
|-------|------|---------|
| `frequency` | Frequency (Hz) | One of `28` (28 Hz), `40` (40 Hz), `52` (52 Hz), `68` (68 Hz) or `88` (88 Hz). |
| `minutes` | Duration (minutes) | A number from 5 to 105. |

### Sleeptracker Smart Bed


These actions require the separate [Sleeptracker framed-JSON processor](beds/sleeptracker.md).
They reject Adjustable Lite UART entries and validate every selected layout
before the first write. All accept `device_id` and optional paired-device `side`.
ActiveBreeze `fan_side` separately chooses the processor's fan fields.

| Action | Fields besides `device_id` | Behavior |
|--------|---------------------------|----------|
| `sleeptracker_preset` | `preset`; optional `save: false` | Recall `all_flat`, `zero_g`, `anti_snore`, `user_favorite`, `tv_pc` or `favorite_2`, subject to layout. `save: true` programs a supported preset; Flat is recall only. Processor types 5–7 reject saving. |
| `sleeptracker_climate` | `mode: heat` or `cool`, `level: 0`–`3`; optional `fan_side: both`, `constant: true` | ActiveBreeze only. Level 0 turns the selected fan off. Heat sends a fixed 3600-second timer, cool 36000 seconds; timers are not configurable. |
| `sleeptracker_wave` | `frequency`; optional `minutes: 30` | Premium layouts: 28, 40, 52, 68 or 88 Hz and 5–105 minutes in steps of five. |
| `sleeptracker_massage` | `action` | `head`, `foot`, `pattern`, `28hz`, `40hz` or `off`, subject to layout (`28Hz` and `40Hz` still work). `off` uses selected-unit massage stop. |
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
  action: 40hz
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
animation. Wave duration units and side mapping are not yet confirmed on a real bed. Last commanded climate timers describe acknowledged writes,
not countdown readback. No service accepts arbitrary JSON, network configuration
or speaker/audio commands.

## Snore Monitor

<a id="onlysnore_set_alarm"></a>
**`onlysnore_set_alarm`**: Set or turn off one of the bed's own alarms.

| Field | Name | Meaning |
|-------|------|---------|
| `slot` | Alarm slot | 1, or 1 to 3 when the bed reports three alarms. |
| `enabled` | Enabled | Turn the alarm on or off. |
| `time` | Time | Alarm time, to the minute. |
| `weekdays` | Repeat on | Leave empty for a one-time alarm. |
| `soft_wake` | Soft wake | Only when the bed reports three alarms. |

This is a documented exception to [`set_alarm`](#set_alarm). The app's five
alarm actions have no established meaning, so they cannot be named as wake
actions, and the raw repeat mask's top bit has no `set_alarm` equivalent. The
action also prepares both beds of a combined pair before either writes and
rechecks each bed's connection before the first write. See [Snore Monitor
BED](beds/onlysnore.md#settings-and-alarms) for the one-time weekday handling.

## Solace

<a id="solace_audio"></a>
**`solace_audio`**: Select or preview MotionFlex music, query volume, or set volume.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | One of `select` (Select track), `preview` (Preview track), `query` (Read current settings) or `set_volume` (Volume). |
| `track` | Track | Required for select and preview actions. |
| `volume` | Volume | Required for the set_volume action. |

## SonicSleep

<a id="sonicsleep"></a>
**`sonicsleep`**: Read the alarms, create or edit an alarm, turn an alarm on or off without changing it, delete an alarm, or read the bed's link name.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | One of `list` (Read alarms), `new` (New alarm), `edit` (Edit alarm), `toggle` (Turn on or off), `delete` or `link_name`. |
| `alarm_id` | Alarm number | The alarm to edit, turn on or off, or delete, as the bed reported it. New alarms get their own number. |
| `hour` | Hour | A number from 0 to 23. |
| `minute` | Minute | A number from 0 to 59. |
| `mode` | Mode | One of `zero_gravity`, `lounge`, `tv`, `anti_snore` (Anti-snore), `memory_1` or `memory_2`. |
| `weekdays` | Weekdays | Leave empty for a one-time alarm; select all seven for every day. |
| `enabled` | Enabled | Turn the selected option on or off. |

### SonicSleep bed settings


`adjustable_bed.sonicsleep` takes `device_id`, optional paired `side`, and
`operation`: `list`, `new`, `edit`, `toggle`, `delete` or `link_name`; set the
clock with [`sync_clock`](#sync_clock).
Alarm form fields are `hour`, `minute`, `mode`, `weekdays` (Monday 0 to Sunday 6)
and `enabled`. Edit/toggle/delete select a received `alarm_id`; toggle preserves
all received raw fields except enabled. Clock capability and current alarm cache
are required before writes. Missing/changed cache rejects the action. A silent
empty-list query cannot safely allocate a new alarm. All target constraints pass
before any target's setting changes. See the [SonicSleep reference](beds/richmat.md#sonicsleep).

## Somos

<a id="somos_action"></a>
**`somos_action`**: Press one of the selected Somos product's buttons. Every bed is checked before any is changed.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | `flat`, `zero_g`, `anti_snore`, `memory_1`–`memory_3`, `head_massage`, `foot_massage`, `massage_timer_cycle`, `light` or `status_query`, as the product offers. |

Massage and light actions press the app button without guessing its current
state. Use the standard `hold_control`, `timed_move` and STOP actions for
movement; Signature Split Head and Ultra Split Head lifts are `axis_1`–`axis_3`.
See [Somos](beds/keeson.md#somos--somosbeds).

## SUTA Smart Home

<a id="suta"></a>
**`suta`**: Run one control from the bed's SUTA layout, which its Bluetooth name decides. Set alarms with Set alarm and the clock with Set bed clock.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Command | Command key from the SUTA guide, such as both_tv, massage_timer_10 or temperature_setpoint. |
| `suffix` | Step | Two-digit step for massage, massage level or fan commands, such as 00 or 20. |
| `logical_side` | Mattress side | For mattress and heating commands that target one side. |
| `value` | Value | Needed when a mattress or heating command offers several values. |

### SUTA Smart Home commands


`adjustable_bed.suta` runs only commands declared by the saved Bluetooth-name
layout. It accepts `device_id`, optional paired `side`, `action`, and the
command's `suffix` or `logical_side` / `value`. All targets and parameters are
validated before any target moves. The `snore_cycle` command sends the
anti-snore burst and the delayed flat; it performs no phone sensing.
Text-layout alarms use [`set_alarm`](#set_alarm). See the
[SUTA reference](beds/suta.md) for the commands, value ranges, state
prerequisites and the six withheld light schedules. Expanded controls are
**hardware unverified**, for external beta testing.

## Starcode

<a id="starcode_move_lifts"></a>
**`starcode_move_lifts`**: Control the independently addressed accessories configured on one main bed. Flat moves the main before the delayed lift action.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | Up, down, composite flat or STOP. |

### `starcode_move_lifts`


Controls accessories configured on an AdjustableM5X5 or Adjustable Comfort M1X12 main entry. AdjustableM5X5 retains its one-main-plus-three-lifts limit and accepts its existing member types. M1X12 accepts up to two distinct ELEVATE entries explicitly configured with the M1X12 variant. Choose one main `device_id` and `action`: `up`, `down`, `flat` or `stop`. Movement preflights every selected address and interrupts the conflicting main. `flat` interrupts the selected group, sends main flat, waits 1600 ms and sends lift flat. STOP, unloading or a changed selection cancels the retained delay. If a member fails, every selected target is stopped. The action never fans out lighting, massage or programming.

```yaml
action: adjustable_bed.starcode_move_lifts
data:
  device_id: YOUR_MAIN_DEVICE_ID
  action: flat
```

Main controls also expose Ascent/TV, Zero Gravity, Anti-Snore, Lounge, two memory slots, three named-save buttons and reset. Programming sends 55 attempts and reports transport completion, not proof that firmware retained the setting. RGB palette indices and brightness use controller-declared select/number entities. Alarm, sound/EQ, sonic and kneading feedback are read-only.

## Svane

<a id="svane_release_axis"></a>
**`svane_release_axis`**: Stop one motor while the other keeps moving.

| Field | Name | Meaning |
|-------|------|---------|
| `motor` | Axis | One of `head` or `feet`. |

### Svane Remote held controls


[`hold_control`](#hold_control) holds a selected Svane head/feet axis or combination for `duration` seconds (0.1–60). Feet-only actions and P1 combinations require more than 0.1 seconds to allow the source's 100 ms feet delay; shorter requests are rejected before any target moves. If awaited delivery consumes the remaining budget before feet start, the action fails explicitly and releases any started axis. The `light_adjust` control runs the app's triangular lamp preference loop after the source's 200 ms threshold. All physical targets are checked before movement.

`svane_release_axis` accepts `motor: head` or `motor: feet` during that hold and signals its serialized writer. The remaining axis continues; final release uses the profile's actual STOP. Both actions accept the normal `device_id` and paired `side` fields. The literal Svane position, Read/TV, toggle and refresh buttons, local intensity number and diagnostic records are described in the [profile guide](beds/svane.md).

## Symphony

<a id="symphony_anti_snore"></a>
**`symphony_anti_snore`**: Configure Head or Elevation. Legacy strengths are 1, 3 and 6; SoundWave strengths are 1, 2 and 3.

| Field | Name | Meaning |
|-------|------|---------|
| `enabled` | Enabled | Turn the selected option on or off. |
| `axis` | Actuator | One of `head` or `elevation`. |
| `strength` | Strength | One of `1` (Low), `2` (SoundWave medium), `3` (Legacy medium / SoundWave high) or `6` (Legacy high). |
| `demo` | Run demonstration | On or off. |

<a id="symphony_preset"></a>
**`symphony_preset`**: Recall a preset, or explicitly save it where the product supports programming.

| Field | Name | Meaning |
|-------|------|---------|
| `preset` | Preset | One of `zero_g` (Zero gravity), `flat`, `memory_1`, `memory_2`, `reading`, `tv` or `anti_snore` (Anti-snore). |
| `save` | Save current position | On or off. |

<a id="symphony_set_light"></a>
**`symphony_set_light`**: Set both light parameters explicitly, without replacing unknown companion state. ES700 and SS800 only.

| Field | Name | Meaning |
|-------|------|---------|
| `color` | Color code (1–7) | A number from 1 to 7. |
| `brightness` | Brightness (20–80) | A number from 20 to 80. |

### Symphony Sleep Sense


The [Symphony guide](beds/okin-soundwave.md#symphony-sleep-sense) documents
`symphony_set_light`, `symphony_anti_snore` and `symphony_preset`; alarms use
[`set_alarm`](#set_alarm). Recall and save are explicit actions. On split beds
the alarm of the other side is read first and kept; split SoundWave beds cannot
give both sides the same alarm time. Serialized pairs offer renewable holds on Left or
Right, while finite Both actions remain available.
Motor covers expose renewable holds through the standard `timed_move` and
`hold_control` actions; presets stay finite.

## BetterLiving2 actions

Use `set_alarm` with `wake_action` set to `massage`, `memory_1` or `memory_2`.
`weekdays` uses weekday names; an empty list chooses the next occurrence.
The shared `sync_clock` action sets the bed clock.

`betterliving2_massage` takes P1 `head` and `feet` levels from 0 to 3.
`betterliving2_diagnostic_action` offers `refresh_alarm` and P2/P3 `refresh_massage`.
The raw P1 timer inputs have no proven duration mapping and are not exposed as
an action. Every target is checked before any write.

### L2 Motion

`l2motion` accepts `operation: rgb` with `rgb: [r, g, b]` and optional
`brightness` from 0 to 1, or `operation: sync_mode` with `wired` and `confirm: true`.
Every selected physical target must support the request before any writes begin.
Use the Light timer number for immediate timer changes and `set_alarm` for time
and strength (`massage_intensity: 1` or `2`, or `enabled: false` for off).
The [L2 Motion guide](beds/motomotion.md#l2-motion) describes the name gates.

## personal_comfort_sequence

Select `full_body_massage` for head then foot massage 500 ms apart.
`flat_with_peer_foot` and `anti_snore_with_peer_foot` require a combined pair,
concurrent connections and an explicit `left` or `right` side. The selected
base receives the preset; the other lowers its feet for 30 seconds and releases.
Every participant is checked before the first write. STOP, replacement or a
lost physical session cancels delayed work and drains the captured release.
