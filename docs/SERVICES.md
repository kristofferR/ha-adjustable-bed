# Actions and Automations

Use **Developer Tools → Actions → Adjustable Bed** to inspect the fields for an
action. In YAML the action name is `adjustable_bed.<name>`. The examples below
use `device_id` in `data`; replace each placeholder with the ID of your bed's
device. A device ID is different from an entity ID such as `cover.bed_back`.

Each bed offers only the controls it supports: an action being listed does not
mean that every bed supports it. For ordinary controls you
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
| [`set_positions`](#movement-and-memory) | Move motors to positions | Moves several motors to their target positions, one after another. Every target is checked before any motor moves. |
| [`timed_move`](#movement-and-memory) | Move motor for a time | Move a motor for a specified duration. |
| [`hold_control`](#hold_control) | Hold control | Holds one of the bed's controls for a set time, then releases it as the remote does. Every bed is checked before any moves; a control the bed does not have is refused with the list of controls it has. |
| [`l2motion`](#l2motion) | L2 Motion: settings | Sets the light color of an L2 Motion bed, or switches its two bases between wired and wireless sync. |
| [`instant_comfort_firmness`](#instant_comfort_firmness) | Instant Comfort: set firmness | Sets the main or lumbar firmness for one sleeper of an Instant Comfort air unit. |
| [`personal_comfort_sequence`](#personal_comfort_sequence) | Personal Comfort / Instant Comfort: run sequence | Runs a full body massage, or moves one base of a pair to a preset while the other base lowers its feet for 30 seconds. |
| [`sleepfunction_settings`](#sleepfunction_settings) | SleepFunction: set fan and aroma | Sets the head fan, foot fan or aroma of a SleepFunction bed. |
| [`set_alarm`](#set_alarm) | Set alarm | Sets or turns off the alarm stored in the bed. Each bed accepts only the options its own app offers; Home Assistant checks every selected bed before changing any. |
| [`baseremote_settings`](#baseremote_settings) | Base Remote: color and receiver group | Sets the light color of a Base Remote bed, or changes the Bluetooth group stored in its receiver. |
| [`sync_clock`](#sync_clock) | Set bed clock | Sets the clock of each selected bed to Home Assistant's local time. Every bed is checked before any clock changes. |
| [`rename`](#rename) | Rename Bluetooth name | Gives each selected bed a new Bluetooth name, on beds that support it. Every bed checks the name against its own rules before any name changes. This does not rename the device in Home Assistant. |
| [`lower_to_flat`](#estimated-positions) | Lower to flat | Lowers the selected motors for their full travel time plus a margin. It does not mark the bed as flat: use Mark estimated position flat afterwards. |
| [`estimate_save_position`](#estimated-positions) | Save estimated position | Saves the current estimated position under a name. Every included motor needs a known estimate. |
| [`estimate_rename_position`](#estimated-positions) | Rename estimated position | Rename a saved position, and optionally show or hide its button entity. |
| [`estimate_update_position`](#estimated-positions) | Update estimated position | Replace a saved position with the current estimated position of the sides it covers. |
| [`estimate_delete_position`](#estimated-positions) | Delete estimated position | Delete a saved position and its button entity. |
| [`estimate_recall_position`](#estimated-positions) | Recall estimated position | Moves each motor for its calculated time to reach a saved position. Every side it covers needs a known estimate. The result is an estimate. |
| [`estimate_set_reference`](#estimated-positions) | Mark estimated position flat | Confirm the selected motors are flat now. Their estimates start again at 0%. |
| [`estimate_confirm_unchanged`](#estimated-positions) | Confirm estimated position | Trust the estimate restored after a restart because the bed has not moved since. |
| [`estimate_mark_unknown`](#estimated-positions) | Forget estimated position | Report a movement the integration could not see, such as the remote or the bed's app. |
| [`estimate_match_side`](#estimated-positions) | Match the other side | Moves one side of a combined bed to the other side's estimated position. The other side does not move. Both sides need a known estimate. |
| [`generate_support_bundle`](#support-bundle) | Create support bundle | Records what the bed sends over Bluetooth while you use its remote, and saves a file to attach to a bug report or bed support request. Bluetooth addresses keep only their manufacturer prefix, and PINs, typed names, health readings and other nearby devices are left out. |
| [`agingplace_action`](#agingplace_action) | Aging in Place: run control | Run one of the bed's actions. Flat ends a cycle or self check; Release held control stops a held key. In and Out are held with Hold control. |
| [`agingplace_set_setting`](#agingplace_set_setting) | Aging in Place: settings | Set light brightness, massage duration or motion light duration. |
| [`bedtech_app_command`](#bedtech_app_command) | BedTech: press button | Press one of the selected BedTech model's buttons, on the sleeper side the app uses for it. Movement repeats for the configured number of pulses. |
| [`bedgear`](#bedgear) | Bedgear: settings | Change Bedgear settings. Values show as unknown until the bed reports them. |
| [`bedsmart`](#bedsmart) | BedSmart / X-Series: settings | Sets the lighting and aroma of a BedSmart or X-Series bed, or presses a bed button. Use Set alarm for wake-up alarms. |
| [`betterliving2_diagnostic_action`](#betterliving2_diagnostic_action) | BetterLiving2: refresh status | Asks the bed for its current alarm or massage status, so its sensors update. |
| [`betterliving2_massage`](#betterliving2_massage) | BetterLiving2: massage levels | Sets the head and foot massage levels. 0 turns a zone off. |
| [`casper_base`](#casper_base) | Casper Base: settings | Sets the light, alarms and clock of a Casper Base, reads its separate sleep sensor, or finds its remote. Only the options your product has can run. |
| [`cheerssleep`](#cheerssleep) | CheersSleep: run control | Run one of the bed's controls, such as movement, presets, massage or the light. Every selected bed is checked before any of them changes. |
| [`comfort_enhancement3_start_massage`](#comfort_enhancement3_start_massage) | Comfort Enhancement 3: start massage | Starts a massage program. The bed does not report massage back, so the values only describe what was sent. |
| [`customatic_hold_memory`](#customatic_hold_memory) | Customatic: hold memory buttons | Holds one or more buttons of the memory page on a Clarity or Remedy remote, as if pressed together. Combinations with Program can change saved positions. |
| [`customatic_move_simultaneously`](#customatic_move_simultaneously) | Customatic: move motors together | Moves up to three motors together, then stops them. |
| [`dreamsense_delete_alarm`](#dreamsense_delete_alarm) | Dream Sense: delete alarm | Deletes a repeating alarm from the bed's alarm list. |
| [`dreamsense_light`](#dreamsense_light) | Dream Sense: lighting | Set the bed light color or duration after the bed reports lighting support. |
| [`fsm_relax_calibrate`](#fsm_relax_calibrate) | FSM Relax: calibrate | Calibrate the bed with its configured motor directions. Calibration is sent once; if Home Assistant reports an error, check the bed before you try again. |
| [`floyd_action`](#floyd_action) | Floyd: settings | Moves to a preset, saves over a built-in preset, or links a bed to a room in the app. |
| [`furnimove_action`](#furnimove_action) | FurniMove: press button | Presses one of the handset's buttons, optionally holding it. |
| [`furnimove_massage_duration`](#furnimove_massage_duration) | FurniMove: massage duration | Sets the massage duration shown in Home Assistant. It is not sent to the bed, so massage does not stop when the time is up. |
| [`furnimove_massage_program`](#furnimove_massage_program) | FurniMove: massage program | Select massage program 1, 2, 3 or 4 (Wave), the way the handset does. |
| [`furnimove_move_simultaneously`](#furnimove_move_simultaneously) | FurniMove: move two motors together | Moves two motors together for a set time, then stops them. |
| [`gmmotor`](#gmmotor) | GM Control: settings | Runs a GM Control setting or reading. Use the bed's buttons or Hold control for movement. |
| [`galaxy`](#galaxy) | Galaxy: settings | Sets the alarm, light and anti-snore options of a Galaxy bed. |
| [`goodvibe`](#goodvibe) | Good Vibe Sleep: settings | Sets the alarm, light, massage and anti-snore options of a Good Vibe Sleep bed or its sleep sensor. |
| [`hjbed`](#hjbed) | HJBed: settings | Sets the alarm, light and other options of an HJBed bed. The bed must report the feature first. |
| [`hush_base`](#hush_base) | Hush Base: settings | Sets the light, alarms and clock of a Hush Base, reads and sets its separate sleep sensor, or finds its remote. Only the options your product has can run. See the Hush Base guide. |
| [`jerome_bed`](#jerome_bed) | Jerome’s power base: control bed | Run an action from the selected bed layout. Preset saves and long-press controls require confirmation. |
| [`jiecang_stop_wake`](#jiecang_stop_wake) | Jiecang: stop wake massage | Stop active wake massage without disabling the stored weekly clock alarm. |
| [`jiecang_wake`](#jiecang_wake) | Jiecang: start wake routine | Move to a preset and start the selected wake massage levels immediately. |
| [`comfy_control`](#comfy_control) | KomfyD and ComfyDS: settings | Moves the bed or runs its timer and lock buttons. |
| [`lp2`](#lp2) | L&P Adjustable Base: settings | Sets the lighting, aromatherapy and fans of an L&P Adjustable Base, or runs one of its remote controls. Use Set alarm for wake-up alarms. |
| [`richmat_resource_bed`](#richmat_resource_bed) | Lady Americana and partner beds: settings | Sets the light and massage timer of a Lady Americana or partner bed, or presses a bed button. Set its alarm with Set alarm. Read the current settings before changing the light. |
| [`leggett_sleep_timer`](#leggett_sleep_timer) | Leggett & Platt: sleep timer | Start a delayed preset or cancel the stored sleep timer. |
| [`limoss_remote_calibrate`](#limoss_remote_calibrate) | Limoss Remote: calibrate | Runs the remote's calibration after you confirm, then releases the motors. |
| [`limoss_remote_features`](#limoss_remote_features) | Limoss Remote: configure controls | Chooses whether the lamp and massage controls are shown. Turning a control off first turns that feature off on the bed. |
| [`limoss_remote_rename_memory`](#limoss_remote_rename_memory) | Limoss Remote: rename memory | Renames a memory in Home Assistant. An empty name is allowed. |
| [`linak_move_simultaneously`](#linak_move_simultaneously) | Linak: move two motors together | Moves two motors together for a set time on a Linak Bed Control or Jensen JMC400, then stops them. |
| [`linx_snore_intervention`](#linx_snore_intervention) | Linx: snore intervention | Run the bed's anti-snore movement once, then ask the bed for its status. It does not listen for snoring. |
| [`logicdata_hold_preset`](#logicdata_hold_preset) | LOGICDATA: hold preset | Holds a flat, preset or memory button for a set time, then releases it. |
| [`luuna`](#luuna) | Luuna: settings | Sets the light of a Luuna bed, or reads the name of its sleep sensor. Set its alarm with Set alarm and its clock with Set bed clock. Only the options your bed reports can run. |
| [`richmat_rise`](#richmat_rise) | Luuna Rise and Power Cool: settings | Sets the light and massage timer of a Luuna Rise or Power Cool bed. Set its alarm with Set alarm. Light settings need the bed to report them first. |
| [`sinca_comfort_command`](#sinca_comfort_command) | Sinca Comfort Bed controls | Refresh settings, read or disable the alarm, adjust automatic anti-snore, or consume local history. |
| [`mline_command`](#mline_command) | M Line: settings | Sets sleep privacy or anti-snore, reads the current settings or alarm, or downloads sleep history. |
| [`mlily`](#mlily) | MLILY: settings | Sets the alarm, light, massage and anti-snore options of an MLILY bed, or reads and sets its separate sleep sensor. |
| [`motion_bed_action`](#motion_bed_action) | Motion Bed: run control | Run a control by its name, such as kuaijie_k2mfragment_flat. The Motion Bed guide lists the common names; the bed's diagnostics list every name it accepts. Saving, clearing, resetting and changing modules need confirmation. |
| [`motion_bed_air_setting`](#motion_bed_air_setting) | Motion Bed: air settings | Reads or saves the air strength and optional timer of one air mode. |
| [`motion_bed_audio`](#motion_bed_audio) | Motion Bed: audio | Select a track, preview a track, or set volume on a target that reports audio support. |
| [`motion_bed_calibration`](#motion_bed_calibration) | Motion Bed: calibrate sleep sensing | Save the app’s flat and side calibration readings. Confirm before changing calibration. |
| [`motion_bed_module`](#motion_bed_module) | Motion Bed: hub modules | Lists, adds or removes the motor, air or heating modules of a Motion Bed hub. Adding and removing need confirmation. |
| [`motion_bed_pressure`](#motion_bed_pressure) | Motion Bed: air pressure | Adjusts one air channel, or saves all twelve air pressures at once. |
| [`motion_bed_sleep_angles`](#motion_bed_sleep_angles) | Motion Bed: sleep positions | Saves the four flat and four side-sleeping positions used by sleep sensing. Use the values shown in the app. |
| [`motion_bed_sleep_report`](#motion_bed_sleep_report) | Motion Bed: sleep report | Reads live, timer, day or month sleep data. |
| [`motion_bed_sleep_timer`](#motion_bed_sleep_timer) | Motion Bed: sleep timer | Chooses a bedtime timer or a fall-asleep timer from the app's list. |
| [`motion_bed_thermal_schedule`](#motion_bed_thermal_schedule) | Motion Bed: heating schedule | Saves a heating or cooling timer with its strength. |
| [`motomotion`](#motomotion) | MotoMotion: postures and users | Save body measurements and your own posture positions on MotoMotion beds whose app has a users tab. Measurements are height, buttocks height and knee height in centimetres. This does not read where the motors are. |
| [`doublesleep_configure`](#doublesleep_configure) | OKIN SleepEase: settings | Sets the alarm, anti-snore and sleep sensor sensitivity of an OKIN SleepEase bed, reads its sleep report, or saves a named position. Reports appear on the bed's report sensors. Send only the fields of the selected setting. |
| [`octo_enroll_pin`](#octo_enroll_pin) | Octo: set PIN | Set a new four-digit PIN on one unlocked OCTO Smart Control receiver. Enter the same PIN twice. Home Assistant saves it for reconnects after sending the command. |
| [`octo_reset_defaults`](#octo_reset_defaults) | Octo: reset receiver | Restore receiver defaults after explicit confirmation. The receiver disconnects five seconds after the reset command. |
| [`okimiki`](#okimiki) | Okimiki: settings | Press or save a control, set the light, or read and set the alarms of the selected Okimiki product. Set the clock with Set bed clock. |
| [`bobpowerbase`](#bobpowerbase) | Power Bob Base: settings | Sets the repeating alarms and the light of a Power Bob Base, when the bed reports them. Set the clock with Set bed clock. |
| [`rmcontrol_anti_snore`](#rmcontrol_anti_snore) | RMControl: anti-snore | Turns anti-snore on or off, or sets how it responds to snoring. |
| [`reverie_pairlink_alarm_comfort`](#reverie_pairlink_alarm_comfort) | Reverie: set alarm comfort | Sets every comfort value the Pairlink alarm uses, including the ones that stay the same. |
| [`reverie_run_routine`](#reverie_run_routine) | Reverie: run routine | Run a routine of comfort steps on the selected Reverie bed. It replaces any routine the bed is running. |
| [`reverie_set_comfort`](#reverie_set_comfort) | Reverie: set comfort | Sends one comfort setting, with its head, foot, lumbar, massage, timer and mode values, to each selected Reverie bed. |
| [`richmat_classic`](#richmat_classic) | Richmat (classic app): settings | Sets the alarm, light, aroma and massage timer of an Avocado Eco Base, CoasterSleep, Forty Winks, Milemont or Superior bed, or moves its desk. Only the options your bed reports can run. |
| [`richmat_app`](#richmat_app) | Richmat app: settings | Sets the light, alarm, heated blanket, sleep sensing and other options of a Richmat app bed. Only the options your product has can run. Read a setting first before changing it. |
| [`richmat_mh_aroma`](#richmat_mh_aroma) | Richmat app: aroma timing | Sets the three aroma timing sliders of a Richmat app bed. |
| [`richmat_mh_light_color`](#richmat_mh_light_color) | Richmat app: light color | Sets the color of the light, or of the button lights, on a Richmat app bed. |
| [`majestichome`](#majestichome) | Majestic Home: settings | Read, create, edit, turn on or off, or delete the bed's alarms. Set the clock with Set bed clock. |
| [`richmat_mh_control`](#richmat_mh_control) | Nisco and MLILY Supreme: run control | Run one of the selected app and model's controls, read one setting from the bed, or set the app mode used by later controls. |
| [`richmat_mh_sleep_mode`](#richmat_mh_sleep_mode) | Nisco: sleep sensor mode | Set the separate sleep sensor for one or two sleepers. |
| [`richmat_legacy`](#richmat_legacy) | SleepEvolution and W.Silver Products: run control | Run a control from the selected app and name prefix, as a press or a save. |
| [`mlily_remote`](#mlily_remote) | MLILY Remote: settings | Sets the countdown alarm of an MLILY MS600 remote, or runs the anti-snore movement of an MS300-SH remote on the left side. Set the clock with Set bed clock. |
| [`rize_program_preset`](#rize_program_preset) | Rize: set default preset | Store the current position as a default preset on one physical Rize bed. Select one side of a combined bed and explicitly confirm. |
| [`sleep_number_command`](#sleep_number_command) | Sleep Number: run control | Runs a Sleep Number control or reading. Readings return their results. See the actions guide for each command's options. |
| [`sleeptracker_climate`](#sleeptracker_climate) | Sleeptracker: climate | Set the left, right or both fan modes and levels. Level 0 stops the selected fans. Heat runs for one hour and cool for ten hours. The bed does not report the time left. |
| [`sleeptracker_massage`](#sleeptracker_massage) | Sleeptracker: massage | Steps a massage zone or pattern, picks a vibration speed, or stops the massage. |
| [`sleeptracker_preset`](#sleeptracker_preset) | Sleeptracker: preset | Moves to or saves a preset. The presets depend on the bed. |
| [`sleeptracker_relaxation`](#sleeptracker_relaxation) | Sleeptracker: relaxation | Starts the wind-down routine or the bed's relaxation movement. |
| [`sleeptracker_wave`](#sleeptracker_wave) | Sleeptracker: relaxation wave | Starts a wave massage at the chosen speed and for the chosen time. Use Stop massage to end it early. |
| [`onlysnore_set_alarm`](#onlysnore_set_alarm) | Snore Monitor: set bed alarm | Set or turn off one of the bed's own alarms. |
| [`solace_audio`](#solace_audio) | Solace: audio | Chooses or previews a MotionFlex music track, reads the volume, or sets it. |
| [`somos_action`](#somos_action) | Somos: press button | Press one of the selected Somos product's buttons. Every bed is checked before any is changed. |
| [`sonicsleep`](#sonicsleep) | SonicSleep: settings | Read the alarms, create or edit an alarm, turn an alarm on or off without changing it, delete an alarm, or read the bed's link name. |
| [`superior_sleep_speech`](#superior_sleep_speech) | Superior Sleep: press button | Sends one bed control: move a motor, move to a preset, stop, turn massage or under-bed motion activation on or off, or toggle the under-bed light. Motor controls run for the duration. |
| [`suta`](#suta) | SUTA Smart Home: run control | Run one control from the bed's SUTA layout, which its Bluetooth name decides. Set alarms with Set alarm and the clock with Set bed clock. |
| [`starcode_move_lifts`](#starcode_move_lifts) | StarCode: move lifts | Moves the lifts set up on one main bed. Flat lowers the main bed first and the lifts a moment later; Stop stops them all. |
| [`svane_release_axis`](#svane_release_axis) | Svane: release motor | Stop one motor while the other keeps moving. |
| [`symphony_anti_snore`](#symphony_anti_snore) | Symphony: anti-snore | Turns anti-snore on or off for the head or the elevation, or runs a demonstration. Some beds take strengths 1, 3 and 6; others take 1, 2 and 3. |
| [`symphony_set_light`](#symphony_set_light) | Symphony: set light | Sets the light color and brightness together. ES700 and SS800 only. |

# General actions

## Targeting a Bed or Side


| Target | Default behavior |
|--------|------------------|
| Standalone bed device | Operate that bed, on the side chosen in its setup |
| Combined bed device | Operate both sides |
| Left or Right device of a combined bed | Operate that side |

For control actions, an optional `side: left`, `right` or `both` narrows a
combined bed. A side that disagrees with a selected side's device, including
`both`, is refused before anything moves. Selecting both sides' devices in one
call acts on both sides together. The two sides may not start at exactly the
same moment. If a combined movement fails, both sides are stopped.

`generate_support_bundle` is different: it accepts exactly one `device_id` or
`target_address` and has no `side` parameter. For a combined bed with two
receivers, select one side's device. See [support capture](GETTING_HELP.md#generating-a-support-bundle).

## Movement and Memory


| Action | Required fields besides `device_id` | Behavior |
|--------|------------------------------------|----------|
| `goto_preset` | `preset` | Move to a saved memory position. Optional `duration` holds the memory button where the bed recalls by holding |
| `save_preset` | `preset` | Save the current position to a memory slot, replacing what was there |
| `stop_all` | None | Stop any movement now, as the bed's own Stop does |
| `set_position` | `motor`, `position` | Move one motor to a position |
| `set_positions` | `positions` | Move several motors, one after another; every target is checked before any motor moves |
| `timed_move` | `motor`, `direction`, `duration_ms` | Move one motor up or down for 100 to 30000 ms |
| `reverie_set_comfort` | `comfort` | Send one comfort setting to each selected Reverie bed |
| `reverie_run_routine` | `steps` | Run a routine of comfort steps, replacing any routine the bed is running |

`preset` is a memory slot from 1 up to the number of memory slots the bed has;
a slot the bed does not have is refused. Named presets such as Flat or Zero G
are buttons where the bed has them. `save_preset` changes the memory stored in
the bed.

`goto_preset` accepts an optional `duration`, 0.1 to 60 seconds, on beds that
recall a memory by holding its button, such as Bedgear, FSM Relax, Limoss
Remote, M Line, MotoMotion, Nerum, Octo, Paramount, Sealy and Symphony Sleep.
Other beds refuse it before any bed moves. Leave it unset to use the bed's own
recall.

M1X12 beds use the `m1x12_part_1` (head), `m1x12_part_2` (foot),
`m1x12_part_4` (lumbar), `m1x12_part_8` and `m1x12_part_16` motors. ELEVATE
uses `elevate_actuator_1`, `elevate_actuator_2` and `elevate_both`. Only the
motors your bed has are accepted.

[Simmons Blue](beds/okin-nframe.md#simmons-blue) uses slots 1–2 for memory recall and save. The bed receives a longer press to save.

[Saatva](beds/richmat.md#saatva) supports `goto_preset` and `save_preset` slots
1 and 2, `timed_move` for `back` and `legs`, and `stop_all` to end held movement.
On a split top, head actions follow the selected side; the foot motor and the
memory slots are shared. Stop ends a held movement but not a preset that is
already moving. Plus massage and light controls are buttons, with a 10/20 minute
**Massage timer** select showing the last value sent.

Positions are in degrees or percent, depending on the bed: check its position
entity and its [guide](README.md#bed-guides). Moving to a position needs the
bed's position readings turned on. Older Sleep Number beds (i8, 360 FlexFit 2)
use `left_back`, `right_back`, `left_legs` and `right_legs` with targets from 0
to 100%. A `set_positions` list cannot repeat a motor. Every target is checked
before movement starts, but if the bed drops the connection on the way, it can
stop part way.

A bed accepting a command does not confirm that it reached the target.

Beds without position feedback can opt in to calibrated travel-time estimates
and saved positions. Their actions (`estimate_save_position`,
`estimate_recall_position`, `estimate_set_reference` and others) are described in
[Estimated positions](ESTIMATED_POSITIONS.md#actions).

### Renewable holds


`timed_move` and `hold_control` accept two optional fields, `hold_owner` and
`hold_generation`, that keep a movement going for as long as you repeat the
call, on beds whose remote keeps moving while a button is held. `timed_move` on
other beds refuses the fields before anything moves. `hold_control` accepts them
on its other held controls too, such as Good Vibe Sleep's short, long and
short-and-long presses: the control then runs as it does without them, for at
most 30 seconds. A call without the fields behaves as before.

| Field | Meaning |
|-------|---------|
| `hold_owner` | Who holds, for example one dashboard card (1 to 64 characters) |
| `hold_generation` | Number of this press. Use a new, higher number for each press |

The call's duration is how long the movement continues without another call:
100 to 30000 ms (`duration_ms`) or 0.1 to 30 seconds (`duration`). The bed keeps
moving while calls with the same owner, number, motor and direction (or
control) arrive within that time. Each call restarts the duration, so a shorter
duration shortens the hold. A repeated call sends nothing to the bed and returns
at once. When the time runs out, the bed stops as it does on release.

A hold ends when its time runs out, when Stop or another move interrupts it,
when the Bluetooth connection drops, or when the integration reloads. A call
with an ended, older or different hold number is refused, so a late call can
never start the bed again. Nothing restarts after a reconnect or a restart.
One hold never runs longer than 30 seconds in total, however often it is
repeated. Solace, BedSense, Reverie, Kaidi, iSleep and Remacro beds keep moving
until they are told to stop, so their holds stop after 10 seconds in total. A
call holds one bed or one combined bed; on a combined bed both sides must hold
the same way, and one call keeps both sides moving.

The dashboard card uses this for its held controls. To do the same in your own
card or script, repeat the call every 250 ms with a 750 ms duration while the
button is held, and call `stop_all` on release. Entities of a bed that supports
it carry a `hold_lease_mode` attribute (`stream` or `latched`), and
`hold_lease_motor` names the `timed_move` motor where there is one. A combined
control on a combined bed carries them only when both sides hold the same way.

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

Renewable holds are not yet confirmed on real beds. Reports are welcome on
whether a held motor moves smoothly through your Bluetooth adapter or proxy, and
how long it keeps moving after the calls stop.

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

The time starts once the bed is connected and ready to move, and the bed may
stop a little earlier. The action waits until the bed has stopped, so it can
take longer than `duration_ms`. See [command lifecycle](COMMAND_LIFECYCLE.md).

Stop both sides of a combined bed:

```yaml
action: adjustable_bed.stop_all
data:
  device_id: <combined bed device ID>
  side: both
```

## Held Controls, Rename and Clock


These general actions take `device_id` and an optional `side`. Each bed offers
only what it supports, and every selected bed is checked before any of them
changes.

### `hold_control`


Holds one of the bed's controls for `duration` seconds (0.1 to 60), then
releases it as the remote does. A control the bed does not have is refused with
the list of controls it has. Save controls can change saved positions. Svane
Remote and Limoss Remote beds cannot share one call with other beds.

Sleepy's Elite beds offer their fixed buttons here. Their number and select
entities, including the light colors, are separate.

| Bed | Controls | Notes |
|-----|----------|-------|
| [Super Colchones](beds/richmat.md#super-colchones) | `head_up`, `head_down`, `foot_up`, `foot_down`; AFEG350 also `lumbar_up`, `lumbar_down` | |
| [BedSmart / X-Series](beds/richmat.md#bedsmart--x-series) | The `richmat_classic_<node>` controls of the selected remote layout that can be held | Saves cannot be held |
| [Base Remote](beds/richmat.md#base-remote) | The held controls of the selected layout and mode | Saves cannot be held |
| [Dream Sense Bed](beds/richmat.md#dream-sense-bed) | The selected product's held controls, such as `HeadUp` | Save buttons are separate |
| [Sleepy's Elite app](beds/sleepys.md#explicit-sleepys-elite-app-profile) | Motor directions and app buttons that can be held | 100 to 60000 ms. Motion sensor actions end after five seconds. BOX25 voice positions run once |
| [Glideaway Motion / Montion](beds/keeson.md#glideaway-motion) | Axes, presets, memories, light and massage controls by model, listed in the guide | At most 30 seconds. Memory recalls take under 5 seconds; save with `save_preset` |
| [Leggett Okin app profiles](beds/okin-nframe.md#leggett-okin-family) | `flat`, `snore`, `lights_toggle`, `massage_toggle`, `massage_wave`, `massage_head_up`, `massage_head_down`, `massage_foot_up`, `massage_foot_down`; U Series adds `memory_1`, `memory_2`, `store` | |
| [Jordan's Serenity](beds/okin-nframe.md#app-commands) | 31 of the app's controls | |
| [Jordan's Tranquil](beds/okin-nframe.md#app-commands-1) | 30 of the app's controls | |
| [Customatic Z-Series](beds/okin-nframe.md#app-commands-2) | The Z-230 or Z-280 controls | A Z-230 refuses Z-280-only controls and the other way round |
| [Simmons Blue](beds/okin-nframe.md#simmons-blue) | `first_up`, `first_down`; iD Motion adds `second_up`, `second_down`, `flat`, `relax`, `tv`, `anti_snore`; 3 and 4 motors add `combined_up`, `combined_down`; 4 motors adds `incline` | Use `goto_preset` and `save_preset` for memories 1–2. |
| [SIMMONS](beds/okin-nframe.md#simmons) | `head_up`, `head_down`, `legs_up`, `legs_down`, `flat`, `memory`, `light`, plus `zero_g`, `tv`, `anti_snore` on a regular bed or `inclined_left`, `inclined_middle`, `inclined_right` on an inclined bed | Holding `memory` for 5 seconds saves Custom Mode, as in the app; not yet confirmed on a real bed |
| [AdjustaMattress](beds/keeson.md#adjustamattress) | The app's control names, such as `headUp`, `footDown`, `unionUp`, `neckTiltUp`, `lumbarDown`, `flatPosition`, `zeroGravity`, `m1`, `underbedLighting`, `headStrengthAdd`, `timer10`, by model and layout | |
| [Adjustable bed (Lumbar)](beds/okin-nframe.md#timing-and-controls) | `head_up`, `head_down`, `feet_up`, `feet_down`, `lumbar_up`, `lumbar_down`, `flat`, `zero_g`, `lounge`, `incline`, `anti_snore`, `save_zero_g`, `save_lounge`, `save_incline`, `save_anti_snore`, `light`, `wave_1`, `wave_2`, `wave_3`, `massage_up`, `massage_down` | Not yet confirmed on a real bed whether a save stores the position |
| [Simon Li / Heal Every Night / OKIN-Seating](beds/keeson.md#simon-li-heal-every-night-and-okin-seating-profiles) | Simon Li: `back_up`, `back_down`, `foot_up`, `foot_down`, `lumbar_up`, `lumbar_down`, `home`, `memory_1`, `memory_2`. OKIN-Seating: `back_up`, `back_down`, `foot_up`, `foot_down`, `home`. Heal Every Night: `head_up`, `head_down`, `foot_up`, `foot_down`, plus `tilt_up`, `tilt_down`, `lumbar_up`, `lumbar_down` on Healing 7 and 8 | Holding a Simon Li memory for 2.1 seconds or more saves it, as in the app |
| [Restonic BT (Keeson)](beds/keeson.md#restonic-bt-profiles) | Remote A: `head_up`, `head_down`, `feet_up`, `feet_down`, `flat`, `zero_g`. Remote B adds `back_legs_up`, `back_legs_down`, `light`, `zzz` | Directions, remote B's back and legs and remote A's `zero_g` keep going while held; the others run once |
| [Bed Tech](beds/richmat.md#bed-tech) | The selected model's held `mh_XX` controls, such as `mh_24` (head up) and `mh_25` (head down) on 5I | At most 30 seconds. Save buttons cannot be held. The separate intervention receiver has no held controls |
| [Enso Remote](beds/keeson.md#enso-remote) | `head_up`, `head_down` (back), `feet_up`, `feet_down`, plus `both_up`/`both_down` (2 motors), `lumbar_up`/`lumbar_down` (3 and 4 motors) and `tilt_up`/`tilt_down` (waist, 4 motors); `memory_A`, `memory_B`, `timer_memory_page`, and `massage_mode` on 3 motors | |
| [Jerome's power base](beds/richmat.md#jeromes-power-base) | `jerome_` controls of the selected layout that can be held, such as `jerome_head_up` | Saves cannot be held |
| [INNOVA](beds/keeson.md#innova-profile) | `back_up`, `back_down`, `legs_up`, `legs_down`, `memory_a`, `memory_b`, `memory_timer`, plus `combined_up`/`combined_down` (2M), `lumbar_up`/`lumbar_down` (3M, 4M) and `waist_up`/`waist_down` (4M) | |
| [AdjustableM5X4](beds/okin-nframe.md#adjustablem5x4) | Movement, preset, save and massage controls | Flat runs 600 ms; save and reset always take six seconds. Massage controls work only while massage is on. One receiver at a time |
| [Adjustable Comfort M1X12](beds/starcode-m1x12.md) | Parts 1, 2, 4, 8, 16 and combined movement, massage wave and intensity, plus the ELEVATE controls | |
| [Caresse / Werkmeister](beds/vibradorm.md#caresse-and-werkmeister) | Motor directions, `all_up`, `all_down`, `memory_1` to `memory_6`, Werkmeister `sync` | All down is a held direction, not a flat preset. Save memories with the Save buttons |
| [V-MAT Basic](beds/vibradorm.md#v-mat-basic) | `all_up`, `all_down`, `back_up`, `back_down`, `legs_up`, `legs_down`, XT-only `floor_hold` | Both sides need two ready receivers. `floor_hold` acts on one receiver |
| [OCTO Smart Control](beds/octo.md) | The bed's motor directions and `memory_1` up to its memory count | At most 60 seconds per call. The card starts another call only while you still hold the control |
| [Superior sleep](beds/okin-nframe.md#superior-sleep-ss350--ss650) | The SS350/SS650 button controls that can be held | Saves, reset and the five-second motion activation are separate buttons |
| [Svane Remote](beds/svane.md) | `head_up`, `head_down`, `feet_up`, `feet_down`, the four `head_*_feet_*` combinations, `light_adjust` | See [Svane Remote held controls](#svane-remote-held-controls) |
| [Limoss Remote](beds/limoss.md#limoss-remote) | The controls of the remote's layout | |
| [Relax Motion](beds/relax-motion.md) | The motors your model has: `back_up/down`, `legs_up/down`, `lumbar_up/down` or `all_motors_up/down` | |
| [FSM Relax](beds/limoss.md#fsm-relax) | `command_` plus an opcode from your configuration's row in the [FSM Relax key tables](beds/limoss.md#fsm-relax-key-tables), such as `command_12` | The bed does not confirm that it moved |
| [TiMOTION AHF](beds/timotion-ahf.md) | `control_1_up`/`control_1_down` through `control_5_up`/`control_5_down`, `night`, `light`, `chair` | |

Customatic Clarity, Remedy and Jerome's C use
[`customatic_hold_memory` and `customatic_move_simultaneously`](beds/okin-nframe.md#customatic-family),
which select their memory and motor combinations as lists.

### `rename`


Gives each selected bed a new Bluetooth name, on beds that support it. This
does not rename the device or its entities in Home Assistant. Every bed checks
the name against its own rules before any name changes:

| Bed | Name rule |
|-----|-----------|
| [Linak Bed Control](beds/linak.md) | 1 to 17 characters (fewer for accented letters). The bed then disconnects so it can show the new name |
| [LOGICDATA app profiles](beds/jiecang.md#logicdata-app-family) | Phone and tablet: 1 to 255 plain letters, digits, spaces and punctuation. Sleep Smart [beds](beds/jiecang.md#sleep-smart-air-mattress-bed) and [pumps](beds/logicdata-sleep-smart.md): 1 to 20 letters, digits, ä, ö, ü or ß |
| [ERGOBALANCE](beds/jiecang.md#ergobalance-dreamask) and [Dream Motion](beds/jiecang.md#dream-motion-dreamotion) | 1 to 20 plain letters or digits |
| [Dream Motion HD](beds/jiecang.md#dream-motion-hd) | 1 to 20 plain letters, digits, spaces and punctuation |
| [Comfort Motion app](beds/jiecang.md#comfort-motion-app) | 1 to 18 plain letters, digits, dots or underscores, on beds that report a renameable name |
| [Enso Remote](beds/keeson.md#enso-remote) | 1 to 14 characters after leading and trailing spaces are removed; names with accented letters are cut short (see the guide) |
| [INNOVA](beds/keeson.md#innova-profile) | At most 14 characters as typed, not empty after leading and trailing spaces are removed |
| [FurniMove](beds/furnimove.md#controls-and-actions) | One bed at a time; a name of at most 18 characters, after leading and trailing spaces are removed, that no other bed uses |
| [V-MAT Basic](beds/vibradorm.md#v-mat-basic) | One receiver at a time; at most 10 characters after leading and trailing spaces are removed (empty allowed), and fewer for some special characters |

```yaml
action: adjustable_bed.rename
data:
  device_id: YOUR_DEVICE_ID
  name: Bedroom
```


### `sync_clock`


Sets the clock of each selected bed to Home Assistant's local time. Beds that
set their clock here include [RMControl](beds/richmat.md#rmcontrol) products
with a clock, the [Malouf Base / Lucid Base](beds/malouf.md#malouf-base--lucid-base-family)
app beds, [Glideaway Motion / Montion](beds/keeson.md#alarm-and-clock),
[SIMMONS](beds/okin-nframe.md#alarms-and-clock), [Simmons Blue](beds/okin-nframe.md#simmons-blue), and
[Customatic Z-Series](beds/okin-nframe.md#customatic-z-series) beds with an alarm
page (see [`set_alarm`](#set_alarm)); Z-Series beds cannot share a call with
other beds. SUTA Smart Home, SonicSleep, MLILY Remote, Good Vibe Sleep, Galaxy,
MLILY, Power Bob Base, Majestic Home and Okimiki products with an alarm, GM
Control products with an alarm, OKIN SleepEase, HJBed, Richmat app beds and
their separate sleep sensor, Bed Tech (including its separate intervention
receiver), Dream Sense Bed and Luuna + set their clock here too. On a Motion Bed it sets
the clock of the motor or heating module; on a hub, select the module first.
HJBed's own `hjbed` action also keeps its Set bed clock operation, which does
the same. A bed whose two sides share one receiver has its clock set once.

### `set_alarm`

Sets or turns off the alarm stored in the bed itself, for the beds in the table
below; the beds in its last row keep the alarm in their own action. Each bed
accepts only the options its own app offers, and Home Assistant checks every
selected bed before changing any of them. An option a bed does not have is
refused with a message naming it. An empty `weekdays` list, `massage: false`
and `light: false` ask nothing of the bed and are not refused as options it lacks.

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
| `confirm_custom_position` | Required for SIMMONS saved custom positions and saved-memory wake actions on Jerome's power base and Dream Sense Bed |
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
| Bed Tech | From the selected model's alarm choices | Countdown or three-slot alarms on supported models. Calendar models use a uniquely reported `slot`, with `weekdays` or once. `mattress_side` selects the separate vibrating mattress alarm, with intensity 1–3 |
| Bedgear | None | Once; leave `slot` out. `massage_intensity` 1 or 2 |
| BF and Cherish | `none`, `memory_1`, `memory_2` | Once only |
| BedSmart / X-Series | From the selected layout's alarm page; left out, the layout's first wake action is used. `none` only with `massage: true` and a supported zone | The layout's `massage` zones and combinations. Once, at the next occurrence: leave out `weekdays` and `slot` |
| BetterLiving2 | `massage`, `memory_1`, `memory_2` | `weekdays` or once, at the next occurrence |
| Comfort Enhancement 3 | Depends on the remote: `none`, `memory_1`, `memory_2`, `zero_g`, `tv`, `anti_snore` | `slot` 0–99, `massage` with zone, intensity and 10/20/30-minute duration, `light`. Once, at the next occurrence |
| Comfort Enhancements | `none`, `memory_1`, `memory_2` | `massage`; today only |
| ComfortBase | `memory_1`, `memory_2` | Once only |
| Customatic Z-Series | `massage`, `memory_1` (required to turn on) | Once. Needs a Z-Series bed with an alarm page |
| Dream Sense Bed | The selected product's presets; required to turn on. Saved memories need `confirm_custom_position: true` | One-time alarms go off at the next occurrence of the time. Products with repeating alarms accept `weekdays` and need the `slot` of an alarm the bed reported (0 to 255); new alarms cannot be added |
| eShine | `zero_g`, `flat`, `massage` (by model) | Once; the bed clock is set first |
| Glideaway Motion | `none`, `memory_1`, `memory_2` | Once |
| Jiecang apps | `flat`, `zero_g`, `anti_snore`, `memory_1`, `memory_2`, `yoga` where reported | `weekdays`, head and foot massage levels 0–3 |
| Keeson app layouts (Ergomotion 4.0, Q-Plus and others) | None | `weekdays` or once, `massage` (wake vibration). One weekly and one one-time alarm; turning off clears both |
| L2 Motion | None | Once; leave `slot` out. `massage_intensity` 1 or 2 |
| Jerome's power base | The selected layout's wake positions; `none` only with `massage: true` and a supported zone | `massage` with the layout's zones. `memory_1` to `memory_3` need `confirm_custom_position: true`. Once, as a countdown to the time. Standalone beds and the physical sides of a two-address pair only, not a one-address combined bed |
| Lady Americana and partner beds | From the selected layout's alarm controls; required to turn the alarm on | `massage` with the layout's zones (then `none` is allowed). Once, at the next occurrence |
| L&P Adjustable Base | From the selected layout's alarm page; required to turn the alarm on | `massage` with the layout's zones (then `none` is allowed). Once, at the next occurrence: leave out `weekdays` and `slot` |
| Leggett & Platt (Okin app) | None | Once; the bed counts down to the time |
| Linak Bed Control | `none`, `memory_1` … `memory_4` | `massage`, `light`. Once; the bed counts down to the time |
| Linx | None | Turn off only (`enabled: false`), `slot` 1–6 |
| Logicdata app | `flat`, `zero_g`, `anti_snore`, `memory_1`, `memory_2` | `weekdays`, head and foot massage levels 0–3 |
| Luuna + | The product's alarm positions: `tv`, `zero_g`, `anti_snore`, `memory_1`, `memory_2`; required to turn the alarm on | Once, at the next occurrence. Needs the bed to report its alarm on the current connection |
| Luuna Rise and Power Cool | From the selected layout's alarm controls; required to turn the alarm on | `massage` with the layout's zones (then `none` is allowed). Once, at the next occurrence. Needs the bed to report its alarm on the current connection |
| M Line | `zero_g`, `flat`, `memory_1`, `memory_2`, `massage`, `anti_snore` | `weekdays` |
| Malouf / Lucid app | `zero_g`, `lounge`, `tv`, `anti_snore`, memories | `weekdays` |
| Motion Bed | `none` (rings only), `zero_g`, `memory_1` | `weekdays`, `massage`, `sound` (the alarm tone by default; music 1 by default where the bed has audio) |
| [Simmons Blue](beds/okin-nframe.md#simmons-blue) | `flat`, `lounge` (Relax), `tv`, `anti_snore`, `memory_1`, `memory_2` | `slot` 1–3, `weekdays`. Turning off keeps the time reported by the bed. |
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
| Superior sleep | `wake_mode_1`, `wake_mode_2` (the app's M1 and M2) | `weekdays`. Turning the alarm off clears its time and days |
| SUTA Smart Home (models whose app has an alarm) | None | `weekdays` or once. To turn an alarm off, send the same `time` and `weekdays` it was set with |
| Symphony Sleep | `none`, `memory_1`, `memory_2` | Once |
| Symphony Sleep Sense | By product | `weekdays` |
| Ultramatic (ORE) | `none`, `massage`, `memory_1`, `memory_2` on the older bed route; `tv`, `massage`, `zero_g` on the newer | `weekdays` or once. Turning it on needs a `wake_action`; connect once first so the route is known |
| Ultramatic Smart Bed | `massage`, `zero_g`, `memory_1` (required to turn on) | `weekdays` or once. Left, Right and Both set the A, B and AB alarms; a standalone bed uses its configured side. Turning off without a time keeps the reported alarm's other fields; refresh the alarm first |
| Yamada | By app version | `slot` 1–2, `weekdays`. Refresh the bed's alarms first |
| Casper Base, classic Richmat apps, Galaxy Bed Control, GM Control, Good Vibe Sleep, HJBed, Hush Base, Majestic Home, MLILY, MLILY Remote, OKIN SleepEase, Okimiki, Power Bob Base, Richmat app (`richmat_app` bed type), Snore Monitor, SonicSleep | Use the bed's own action | See [Casper Base](#casper_base), [classic Richmat apps](#richmat_classic), [Galaxy](#galaxy), [GM Control](#gmmotor), [Good Vibe Sleep](#good-vibe-sleep), [HJBed](#hjbed), [Hush Base](#hush_base), [Majestic Home](#majestichome), [MLILY](#mlily), [MLILY Remote](#mlily-remote), [OKIN SleepEase](#doublesleep_configure), [Okimiki](#okimiki), [Power Bob Base](#bobpowerbase), [Richmat app](#richmat_app), [`onlysnore_set_alarm`](#onlysnore_set_alarm) and [SonicSleep](#sonicsleep) |

### Estimated positions

Beds without position feedback can learn travel times and save positions.
Their actions all start with `estimate_` (`estimate_save_position`,
`estimate_recall_position`, `estimate_set_reference` and others) and are
described in [Estimated positions](ESTIMATED_POSITIONS.md#actions).

## Support Bundle


`generate_support_bundle` records the bed's settings, its connection and
pairing details, what it sends over Bluetooth, nearby beds and the recent
commands, and saves a file to attach to a bug report. Only an administrator can
run it. `capture_duration` is 10 to 300 seconds (default 120); `include_logs`
defaults to `true`. Give exactly one bed (`device_id`) or a Bluetooth address
(`target_address`) for a bed that is not set up yet. The logs include recent
Home Assistant Bluetooth messages, messages from reachable ESPHome Bluetooth
proxies, and the latest setup or pairing attempt for that address. Debug logging
is turned on during setup, pairing and the capture, then put back as it was. The
action is available as soon as setup starts, before a bed is added.

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
| `action` | Action | The action to run. Read and Anti-snore send the same command. One of `light` (Under-bed light), `massage` (Massage cycle), `zero_g` (Zero gravity), `anti_snore` (Anti-snore), `read`, `flat`, `release` (Release held control), `circulation` (Circulation cycle), `sleep` (Sleep cycle), `relax_cycle`, `diagnostic` (Self check), `device_info` (Refresh device information) or `cancel` (Cancel cycle or self check). |

<a id="agingplace_set_setting"></a>
**`agingplace_set_setting`**: Set light brightness, massage duration or motion light duration.

| Field | Name | Meaning |
|-------|------|---------|
| `setting` | Setting | The setting to change. One of `brightness` (Light brightness), `massage_minutes` (Massage duration) or `motion_minutes` (Motion light duration). |
| `value` | Value | Light brightness 0 to 100, massage duration 1 to 60 minutes, or motion light duration 1 to 30 minutes. |

See [Aging in Place / Dawn House](beds/keeson.md#aging-in-place--dawn-house) for the bed's controls.

## Base Remote

<a id="baseremote_settings"></a>
**`baseremote_settings`**: Sets the light color of a Base Remote bed, or changes the Bluetooth group stored in its receiver. The receiver does not confirm a group change and disconnects afterwards.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Setting | What to change. One of `set_color` (Set light color), `set_group` (Set Bluetooth group) or `remove_group` (Remove Bluetooth group). |
| `rgb_color` | Light color | Required for Set light color: the color. |
| `group` | Group | Required for Set Bluetooth group: exactly four printable characters. |

The light color needs the bed to report its light on the current connection.
A group change needs a receiver with the group setting. It goes to the selected
receivers one after another, within twelve seconds in total, and each receiver
disconnects afterwards. Use [`set_alarm`](#set_alarm) for alarms; the light
timeout and aroma times are entities. See the
[Base Remote guide](beds/richmat.md#base-remote).

```yaml
action: adjustable_bed.baseremote_settings
data:
  device_id: YOUR_DEVICE_ID
  operation: set_group
  group: "1234"
```

## BedSmart / X-Series

<a id="bedsmart"></a>
**`bedsmart`**: Sets the lighting and aroma of a BedSmart or X-Series bed, or presses a bed button. Use Set alarm for wake-up alarms.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Setting | What to set or press. Each setting needs its own fields. One of `color` (Light color), `light_duration` (Light timeout), `aromatherapy` (Aroma times) or `bed_command`. |
| `rgb_color` | Light color | For Light color: the color. |
| `seconds` | Light duration (seconds) | For Light timeout: seconds, 0 to 300. |
| `aroma_times` | Aromatherapy times | For Aroma times: three numbers, 1 to 60 minutes, 1 to 60 minutes and 1 to 12 hours. |
| `duration_ms` | Movement duration (milliseconds) | For Bed command: how long to repeat a movement button, 1 to 60000 milliseconds. Default 1000. |
| `command` | Bed command | For Bed command: the button to press. Stop turns massage off and ends movement. One of `head_up`, `head_down`, `foot_up`, `foot_down`, `tv`, `lounge`, `zero_gravity`, `anti_snore` (Anti-snore), `memory_one` (Memory 1), `memory_two` (Memory 2), `memory_three` (Memory 3), `flat` or `voice_stop_request` (Stop). |

Each bed of a combined pair keeps its own layout. Light and aroma settings need
the bed to report them first. Use [`set_alarm`](#set_alarm) for wake-up alarms
with the layout's positions and massage. BedSmart has no clock or Bluetooth
rename action. See the [BedSmart guide](beds/richmat.md#bedsmart--x-series) for
the layout controls.
Not yet confirmed on a real bed.

## Bed Tech

For the [Bed Tech app](beds/richmat.md#bed-tech), use the native movement,
preset, memory, light and massage entities for everyday controls. This is
separate from the newer [BedTech app](#bedtech).

Bed Tech shares `richmat_mh_control` with Nisco and MLILY Supreme, and
`richmat_mh_sleep_mode` with Nisco; their fields are listed under
[Nisco and MLILY Supreme](#richmat_mh_control).

- **[`richmat_mh_control`](#richmat_mh_control)** presses a control, reads a
  setting or sets the app mode used by later controls. On Bed Tech, `action` is
  `press`, `query` or `app_mode` (not `remote_long`), and `motor_group` is
  offered only where the model has it.
- **[`richmat_mh_sleep_mode`](#richmat_mh_sleep_mode)** sets the separate sleep
  and intervention receiver for one or two sleepers. It does not move the bed.

Use [`set_alarm`](#set_alarm) for bed and mattress alarms, and
[`sync_clock`](#sync_clock) for the clock. Calendar alarms need the number of an
alarm the bed reported. **Refresh alarms** reads the alarms, and the **Delete
alarm** button deletes one after you confirm; both start disabled. Each side of
a combined bed keeps its own settings. Light color and aroma timing use
[`richmat_mh_light_color`](#richmat_mh_light_color) and
[`richmat_mh_aroma`](#richmat_mh_aroma) where the bed has them.

## BedTech

<a id="bedtech_app_command"></a>
**`bedtech_app_command`**: Press one of the selected BedTech model's buttons, on the sleeper side the app uses for it. Movement repeats for the configured number of pulses.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Button | The button to press. Only buttons your model has can run. One of `head_up`, `head_down`, `foot_up`, `foot_down`, `pillow_up`, `pillow_down`, `lumbar_up`, `lumbar_down`, `preset_flat` (Flat), `preset_zero_g` (Zero gravity), `preset_anti_snore` (Anti-snore), `preset_tv` (TV), `light_toggle` (Toggle light), `massage_on`, `massage_off`, `head_massage_up`, `foot_massage_up`, `massage_mode`, `massage_timer20` (Massage timer, 20 minutes), `memory1` (Memory 1), `memory1_save` (Save memory 1), `memory2` (Memory 2), `memory2_save` (Save memory 2), `stop` or `connection_test`. |
| `sleeper` | Sleeper | Which part of the bed the button acts on: the first or second sleeper, both, or one sleeper's head with the shared foot. Default both sleepers. One of `1` (First sleeper), `2` (Second sleeper), `3` (Both sleepers), `4` (First head, shared foot) or `5` (Second head, shared foot). |

### BedTech app


`bedtech_app_command` presses a button of the selected
[BedTech 7.1.3 model](beds/richmat.md#bedtech). Both receivers of a combined bed
must use the same model. `action` names a button from the model's main screen,
such as `head_up`, `foot_down`, `head_massage_up`, `massage_timer20`,
`preset_flat`, `memory1_save` or `light_toggle` (the app's own names, such as
`headUp`, still work in existing automations). A movement button moves for the
bed's usual number of steps; use `timed_move` for a set time or a renewable
hold. `connection_test` raises the first head for two seconds. Setup never moves
the bed. A button the model does not have fails before any bed moves.

| `sleeper` | Model with two receivers | FH model with one receiver |
|---|---|---|
| `1` / `2` | First / second receiver | The first head's button as it is |
| `3` (default) | Both receivers | Both heads; other buttons stay as they are |
| `4` / `5` | First / second head; foot buttons and Stop reach both receivers | First / second head; the shared foot, memory and massage stay as they are |

Select the combined bed for the shared foot. Selecting one side's device, or a
`side`, limits the request to that side; a `side` that disagrees with `sleeper`
is refused. A standalone FH receiver can also pick its head with `sleeper`.

```yaml
action: adjustable_bed.bedtech_app_command
data:
  device_id: YOUR_PAIRED_BED_DEVICE_ID
  action: foot_up
  sleeper: 4
```

This example raises both foot sections and picks the first head for head
buttons. On these models `stop` ends movement, and massage off is its own
button. Not yet confirmed on real beds.

## Bedgear

<a id="bedgear"></a>
**`bedgear`**: Change Bedgear settings. Values show as unknown until the bed reports them.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Control | Choose the supported setting or save action. One of `rgb` (Light color), `light_timer`, `sync_mode`, `toggle_sync` (Turn sync on or off), `save_snore` (Save anti-snore position) or `save_memory`. |
| `rgb` | Light color | For Light color: red, green and blue, each 0 to 255. |
| `brightness` | Brightness | For Light color: scales the color, from 0 to 1. Default 1. |
| `minutes` | Light shutdown timer | For Light timer: turns the light off after this many minutes, from 0 (never) to 1439. |
| `wired` | Wired synchronization | For Sync mode: on if the two bases are connected with a cable, off for wireless. |
| `confirm` | Confirm synchronization change | Required to change the sync mode. |
| `slot` | Memory slot | For Save memory: memory slot 1 or 2. |
| `recall_on_release` | Recall after saving | When saving a memory, also move to it afterwards, as the remote does. Not available when saving the anti-snore position. |

### Bedgear settings


Use `adjustable_bed.bedgear` for the light color, the light timer, the sync
between two bases, and saving memories and the anti-snore position. Set the
alarm with [`set_alarm`](#set_alarm), its strength as `massage_intensity`. See
the [Bedgear guide](beds/motomotion.md#bedgear).
Motor covers and the card use the generic held and timed movement actions.

## BetterLiving2

<a id="betterliving2_diagnostic_action"></a>
**`betterliving2_diagnostic_action`**: Asks the bed for its current alarm or massage status, so its sensors update.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Status | Which status to read. Massage status needs a P2 or P3 control box. One of `refresh_alarm` or `refresh_massage`. |

<a id="betterliving2_massage"></a>
**`betterliving2_massage`**: Sets the head and foot massage levels. 0 turns a zone off.

| Field | Name | Meaning |
|-------|------|---------|
| `head` | Head massage level | Head massage level, 0 to 3. |
| `feet` | Foot massage level | Foot massage level, 0 to 3. |

### BetterLiving2 actions

`betterliving2_massage` works on the P1 control box. Set alarms with
[`set_alarm`](#set_alarm) (`wake_action` `massage`, `memory_1` or `memory_2`;
an empty `weekdays` list means the next occurrence) and the clock with
[`sync_clock`](#sync_clock). See the [BetterLiving2 guide](beds/keeson.md#betterliving2).

## Casper Base

<a id="casper_base"></a>
**`casper_base`**: Sets the light, alarms and clock of a Casper Base, reads its separate sleep sensor, or finds its remote. Only the options your product has can run.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | What to set or read. Light, alarm and clock options run on the bed, sleep data options on the separate sleep sensor, and Find remote on the remote. Only the options your product has can run. One of `remote_find` (Find remote), `light_rgb` (Light color), `light_seconds` (Light timer), `light_off`, `rgb_power` (Light strip on or off), `rgb_color` (Light strip color), `rgb_timer` (Light strip timer), `rgb_mode` (Light strip mode), `rgb_groove` (Light strip rhythm), `rgb_breathe` (Light strip breathing), `alarm` (One-time alarm), `alarm_cancel` (Cancel alarm), `repeat_alarm` (Repeating alarm), `repeat_delete` (Delete repeating alarm), `repeat_query` (Read repeating alarms), `time_sync` (Set bed clock), `sleep_name` (Sleeper name), `snore_detector` (Snore detection), `sensor_time` (Set sleep sensor clock), `sensor_info` (Sleep sensor details), `sensor_part` (Sleep data by period), `sensor_query_part` (Read sleep data by period), `sensor_live` (Live sleep data), `sensor_report` (Sleep report) or `sensor_stop` (Stop sleep data). |
| `value` | Value | Number for the selected option: light timer in seconds (0 keeps the light on), light strip timer (5, 8, 10, 13, 15, 18, 21, 24, 27, 30, 120, 210, 300, 390 or 480), light strip mode (2, 3 or 5) or light strip rhythm (1 to 4). Default 0. |
| `rgb_color` | Light color | Color for Light color and Light strip color. |
| `enabled` | Enabled | On or off for Light strip on or off, a repeating alarm, Snore detection and Live sleep data. Default on. |
| `hour` | Alarm hour | Hour the alarm goes off, 0 to 23. |
| `minute` | Alarm minute | Minute the alarm goes off, 0 to 59. |
| `mode` | Alarm preset | Position the bed moves to when a one-time or repeating alarm goes off. Only your product's alarm positions are accepted. One of `tv`, `zero_g` (Zero gravity), `anti_snore` (Anti-snore), `lounge`, `memory_1`, `memory_2` or `memory_3`. |
| `slot` | Repeating alarm number | Number of the repeating alarm to set or delete, 0 to 255. Default 1. |
| `days` | Weekdays | Days the repeating alarm runs. Any of `monday`, `tuesday`, `wednesday`, `thursday`, `friday`, `saturday` or `sunday`. |
| `part` | Sleep data setting | For Sleep data by period and Sleep report: 1 or 2 on a sleep sensor whose name starts with RM-, or 11, 12 or 13 on one whose name starts with HJ-. Default 1. |
| `report_type` | Report type | Sleep report length: 1 for a day, 2 for a month. Default 1. |
| `year` | Report year | Year of the sleep report, 1970 to 2225. |
| `month` | Report month | Month of the sleep report, 1 to 12. |
| `day` | Report day | Day of the month for a daily report. Use 1 for a monthly report. |
| `source` | Snore sensor | For Snore detection: an entity whose state is 1 while you snore and 0 otherwise. After five snoring readings in a row the bed runs anti-snore. |

### Casper Base


The [Casper Base guide](beds/casper-base.md#configuration-actions) explains
each operation and how to add the separate sleep sensor and remote.

## CheersSleep

<a id="cheerssleep"></a>
**`cheerssleep`**: Run one of the bed's controls, such as movement, presets, massage or the light. Every selected bed is checked before any of them changes.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Control | A control this model offers. The controls marked for older models work only on models that use the older app screens. One of `query` (Read bed state), `query_shared` (Read shared state), `position_light_toggle` (Toggle light (position screen)), `color_light_toggle` (Toggle light (color screen)), `massage_head` (Cycle head massage), `massage_foot` (Cycle foot massage), `massage_mode` (Cycle massage mode), `sonic_back` (Sonic back zone), `sonic_foot` (Sonic foot zone), `sonic_toggle` (Toggle sonic massage), `sonic_mode_1` (Sonic massage mode 1), `sonic_mode_2` (Sonic massage mode 2), `sonic_switch` (Switch sonic control mode), `sonic_increase` (Increase sonic level), `sonic_decrease` (Decrease sonic level), `sonic_level` (Set sonic level), `rgb_preview` (Preview light color), `rgb2_preview` (Preview white light), `rgb_commit` (Save light color), `rgb2_commit` (Save white light), `snore_setting` (Snore response setting), `out_of_bed_setting` (Out-of-bed setting), `yb_massage` (Timed massage), `seven_motion` (Move one side (older models)), `ten_motion` (Move by part (older models)), `ten_recall` (Recall memory (older models)), `ten_save` (Save memory (older models)), `newten_motion` (Move by part (older models, second layout)), `newten_recall` (Recall memory (older models, second layout)) or `newten_save` (Save memory (older models, second layout)). |
| `value` | Value | Number for the selected control: head or foot massage level 1 to 4 (0 steps to the next level; some models only step), sonic level 0 to 100, light color save delay 10 to 120, snore response or out-of-bed setting 0 or 1, timed massage speed 1 to 3, or memory 1 or 2. |
| `rgb` | Color | Red, green and blue, each 0 to 255. |
| `brightness` | Brightness | Light brightness, 0 to 255, for the light color controls of older models. |
| `duration_ms` | Duration | How long to hold the control, in milliseconds; the move controls take up to 10000. For Timed massage, 300 sets 5 minutes and 900 sets 15 minutes. |
| `axis` | Part | For Move one side: which part moves. One of `all`, `back`, `legs` or `lumbar`. |
| `up` | Move up | For the move controls: on moves up, off moves down. |
| `position` | Part number | For Move by part: which part moves, 1 all, 2 back, 3 feet or 4 waist. |
| `sleeper` | Side to move | For Move one side: left or right. It must match the selected side. One of `left` or `right`. |

### CheersSleep bed controls

Choose a control your model offers. The controls marked for older models only
work on models that use the older app screens; Move one side takes `axis` and
an optional `sleeper` that must match the selected side, and Move by part takes
`position`, `up` and `duration_ms`. The light color controls take `rgb`,
`brightness` and a save delay in `value`; the white light variants use white.
The [CheersSleep guide](beds/cheerssleep.md) lists which models have which
controls and which settings each side keeps. Not yet confirmed on a real bed.

## Comfort Enhancement 3

<a id="comfort_enhancement3_start_massage"></a>
**`comfort_enhancement3_start_massage`**: Starts a massage program. The bed does not report massage back, so the values only describe what was sent.

| Field | Name | Meaning |
|-------|------|---------|
| `duration` | Massage duration (minutes) | How long the massage runs. Default 10 minutes. One of `10` (10 minutes), `20` (20 minutes) or `30` (30 minutes). |
| `intensity` | Intensity steps | How many steps to raise the intensity, 1 to 3. Wave ignores it. Default 1. |
| `kind` | Massage area or wave | Head, feet, both or a wave massage. Default head. One of `head`, `feet`, `both` or `wave`. |

### Comfort Enhancement 3 / Comfort Plus3


Wake-up programs use [`set_alarm`](#set_alarm) with `slot`, `time`, and the
massage, light and wake position options the selected remote offers. Turning
the alarm off deletes that program. The programs stay stored in the bed while
Home Assistant is disconnected, but Home Assistant cannot list the programs
already stored in it.

## Customatic

<a id="customatic_hold_memory"></a>
**`customatic_hold_memory`**: Holds one or more buttons of the memory page on a Clarity or Remedy remote, as if pressed together. Combinations with Program can change saved positions.

| Field | Name | Meaning |
|-------|------|---------|
| `actions` | Buttons | One to five buttons to hold together: Flat, Zero gravity, Anti-snore, Program and Incline. Jerome's C remote has no memory page. Any of `flat`, `zg` (Zero gravity), `anti` (Anti-snore), `program` or `incline`. |
| `duration` | Duration | How long to hold, 0.1 to 60 seconds. |

<a id="customatic_move_simultaneously"></a>
**`customatic_move_simultaneously`**: Moves up to three motors together, then stops them.

| Field | Name | Meaning |
|-------|------|---------|
| `actions` | Motor directions | Back, legs and optionally lumbar, each set to up or down. Lumbar needs the Remedy remote. |
| `duration` | Duration | How long to move, 0.1 to 60 seconds, then the motors stop. |

## Dream Sense Bed

Select **Dream Sense Bed** and its product in setup. The
[guide](beds/richmat.md#dream-sense-bed) lists each product's controls. Light,
clock, alarm, split mode and vibration settings apply to the whole bed, without
a side. Held controls follow the selected side where the bed supports it. The
app has no Bluetooth rename.

<a id="dreamsense_delete_alarm"></a>
**`dreamsense_delete_alarm`**: Deletes a repeating alarm from the bed's alarm list.

| Field | Name | Meaning |
|-------|------|---------|
| `alarm_number` | Alarm number | The number of an alarm the bed reported. Use Refresh alarms first. |

Turn on the **Refresh alarms** button and the **Alarm response** sensor first;
both start disabled. Press **Refresh alarms**, then read the alarm numbers from
the **Alarm response** sensor's attributes. Every selected bed must have that
alarm.

<a id="dreamsense_light"></a>
**`dreamsense_light`**: Set the bed light color or duration after the bed reports lighting support.

| Field | Name | Meaning |
|-------|------|---------|
| `rgb_color` | Color | Red, green and blue, each 0–255. |
| `seconds` | Duration | 0 keeps the light on; otherwise 1–300 seconds. |

Give `rgb_color`, `seconds` or both. The bed must report lighting support first.

Use [`hold_control`](#hold_control) for held controls,
[`sync_clock`](#sync_clock) for products with a clock and
[`set_alarm`](#set_alarm) for one-time alarms and the repeating alarms the bed
reported.

## FSM Relax

<a id="fsm_relax_calibrate"></a>
**`fsm_relax_calibrate`**: Calibrate the bed with its configured motor directions. Calibration is sent once; if Home Assistant reports an error, check the bed before you try again.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm | Explicitly confirm calibration before invoking this action. |

### FSM Relax app actions


[`hold_control`](#hold_control) takes one of the bed's `command_XX` controls
with a `duration` in seconds. The guide's
[FSM Relax services](beds/limoss.md#services-1) explain the names. `goto_preset` recalls
a memory up to the number the bed reports, and accepts an optional `duration`.
`fsm_relax_calibrate` needs `confirmed: true` and sends the calibration once.
The Save and Memory buttons cover up to eight memories, as many as the bed
reports. The bed does not confirm that it moved. See
[FSM Relax](beds/limoss.md#fsm-relax).

## Floyd

<a id="floyd_action"></a>
**`floyd_action`**: Moves to a preset, saves over a built-in preset, or links a bed to a room in the app.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | Move to a preset, save over a built-in preset, link the bed to a room, or confirm a newly added bed. One of `zero_g` (Zero gravity), `flat`, `anti_snore` (Anti-snore), `memory_1`, `memory_2`, `memory_3`, `save_zero_g` (Save zero gravity), `save_anti_snore` (Save anti-snore), `assign_room` or `confirm_add` (Confirm new bed). |
| `internal_side` | Preset page | Leave at First, the normal Floyd page. Both and Second are alarm pages, not the left and right sides. One of `first` (First side), `both` or `second` (Second side). |
| `confirm` | Confirm configuration write | Required to save over a preset or to link the bed to a room. |
| `room_id` | Room number | Room to link this bed to, for a bed not yet in a room. Does not change the bed's Wi-Fi. |

### Floyd Home actions


`adjustable_bed.floyd_action` moves to a preset, saves over Zero gravity or
Anti-snore after you confirm, and links a new bed to a room in the app. See the
[Floyd action table](beds/kaidi.md#floyd-action) before saving a preset or
linking a room. To move head and feet together, use `hold_control` with
`head_feet_up` or `head_feet_down` for up to 30 seconds. Use Home Assistant
automations to move to a preset at a set time: the app's alarms live on the
phone, not on the bed.

## FurniMove

<a id="furnimove_action"></a>
**`furnimove_action`**: Presses one of the handset's buttons, optionally holding it.

| Field | Name | Meaning |
|-------|------|---------|
| `row_index` | Button number | The button's number, shown at the end of the bed's button entity IDs (for example 3 in furnimove_action_3). |
| `duration` | Hold duration | Seconds to hold movement and memory buttons. Other buttons use their own timing. |

<a id="furnimove_massage_duration"></a>
**`furnimove_massage_duration`**: Sets the massage duration shown in Home Assistant. It is not sent to the bed, so massage does not stop when the time is up.

| Field | Name | Meaning |
|-------|------|---------|
| `minutes` | Duration shown | Massage duration to show, in minutes. One of `10` (10 minutes), `15` (15 minutes), `20` (20 minutes) or `30` (30 minutes). |

<a id="furnimove_massage_program"></a>
**`furnimove_massage_program`**: Select massage program 1, 2, 3 or 4 (Wave), the way the handset does.

| Field | Name | Meaning |
|-------|------|---------|
| `program` | Program | Massage program 1, 2, 3 or 4 (wave). |

<a id="furnimove_move_simultaneously"></a>
**`furnimove_move_simultaneously`**: Moves two motors together for a set time, then stops them.

| Field | Name | Meaning |
|-------|------|---------|
| `first_motor` | First motor | The first motor to move. Only motors your handset has. One of `head`, `back`, `legs` or `feet`. |
| `second_motor` | Second motor | The second motor, different from the first. One of `head`, `back`, `legs` or `feet`. |
| `first_direction` | First direction | Direction of the first motor. One of `up` or `down`. |
| `second_direction` | Second direction | Direction of the second motor. One of `up` or `down`. |
| `duration_ms` | Duration in milliseconds | How long to move, 1 to 60000 milliseconds. |

### FurniMove app controls


The [FurniMove guide](beds/furnimove.md#controls-and-actions) describes these
actions; renaming uses [`rename`](#rename) on one bed at a time. The button
numbers follow the handset and appear at the end of the button entity IDs. A
hold of 0.1 to 60 seconds applies to movement and memory buttons; other buttons
keep their own timing. The massage duration is only shown in Home Assistant: it
is not sent to the bed, and massage does not stop when the time is up.

## GM Control

<a id="gmmotor"></a>
**`gmmotor`**: Runs a GM Control setting or reading. Use the bed's buttons or Hold control for movement.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | What to set or read. Only the options your product has can run; a product with repeating alarms has no countdown alarm. One of `alarm` (Alarm after a countdown), `alarm_at` (Alarm at a time), `alarm_cancel` (Cancel alarm), `repeat_alarm` (Repeating alarm), `repeat_delete` (Delete repeating alarm), `repeat_query` (Read repeating alarms), `light_color`, `light_timeout` (Light timer), `light_off`, `snore_enabled` (Anti-snore on or off), `snore_count` (Anti-snore count), `snore_time` (Anti-snore duration), `snore_query` (Read anti-snore settings), `sleep_name` (Sleeper name), `refresh`, `massage_timer`, `sensor_time` (Set sleep sensor clock), `sensor_part` (Sleep data by period), `sensor_query_part` (Read sleep data by period), `sensor_live` (Live sleep data), `sensor_report` (Sleep report), `sensor_sensitivity` (Sleep sensor sensitivity), `sensor_stop` (Stop sleep data), `desk_height`, `desk_unit` (Desk height unit) or `desk_query` (Read desk height). |
| `value` | Operation value | Number for the selected option: minutes until Alarm after a countdown, light timer in seconds (0 to 900), anti-snore count (1 to 30), anti-snore duration (5 to 30), massage timer choice (0 to 3), or for Sleep data by period 1 or 2 on a sleep module whose name starts with RM-, or 11, 12 or 13 on one whose name starts with HJ-. Default 0. |
| `mode` | Alarm action | What the alarm does: one of your product's alarm actions, such as deviceFunctionItemZeroGravity. The bed's status sensor lists them in its gmmotor_alarm_choices attribute. |
| `slot` | Alarm number | Number of the repeating alarm to set or delete, 0 to 255. Default 1. |
| `hour` | Hour | Hour for Alarm at a time and Repeating alarm, 0 to 23. |
| `minute` | Minute | Minute for Alarm at a time and Repeating alarm, 0 to 59. |
| `enabled` | Enabled | On or off for Anti-snore on or off and Live sleep data. Default on. |
| `rgb_color` | Light color | Color for Light color. A product with an eight-color palette accepts only those colors. |
| `part` | Report side | Side of the sleep report: left or right. Default left. One of `left` or `right`. |
| `report_type` | Report period | Length of the sleep report: a day or a month. Default day. One of `day` or `month`. |
| `report_date` | Report date | Date of the sleep report. Leave unset for today. |
| `height` | Desk height | Desk height to move to, in the selected unit. It must lie within the height range the desk reports, or 60 to 125 cm (23.6 to 49.21 inches) before it reports one. |
| `unit` | Height unit | Unit of the desk height, and the unit Desk height unit sets on the desk. Default centimeters. One of `cm` (Centimeters) or `inch` (Inches). |

### GM Control


`adjustable_bed.gmmotor` runs the settings and readings your product supports.
Movement uses the bed's buttons or `hold_control`.

The [GM Control guide](beds/gmmotor.md#specialized-actions) lists the alarm,
light, anti-snore, massage timer and sleeper name operations. The bed's status
sensor lists the alarm actions your product accepts in its
`gmmotor_alarm_choices` attribute. Alarm after a countdown takes `value` in
minutes; Alarm at a time takes `hour` and `minute`. Repeating alarms take
`slot`, `hour`, `minute` and `mode`. Alarm and light options need the bed to
report them first. Set the clock with [`sync_clock`](#sync_clock).

A separate GM Control sleep module offers the sleep options: set or read the
sleep data setting (`value` 1 or 2 on a module whose name starts with RM-, 11,
12 or 13 on one whose name starts with HJ-), live data (`enabled`), a sleep
report (`part`, `report_type` and optional `report_date`) and, on HJ- modules,
the sensitivity. Stop sleep data only stops reading; it does not move the bed.
See the [sleep module guide](beds/gmmotor.md#sleep-modules).

## Galaxy

<a id="galaxy"></a>
**`galaxy`**: Sets the alarm, light and anti-snore options of a Galaxy bed.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | What to set or read. Only the options your product has can run. One of `single` (One-time alarm), `cancel_single` (Cancel one-time alarm), `repeat` (Repeating alarm), `enable_alarm` (Turn alarm on or off), `delete` (Delete alarm), `alarms` (Read alarms), `light_color`, `light_duration` (Light timer), `light_off`, `massage_timer`, `snore_switch` (Anti-snore on or off), `snore_count` (Anti-snore count), `snore_time` (Anti-snore duration) or `snore_query` (Read anti-snore settings). |
| `action` | Alarm action | For a one-time or repeating alarm: what the alarm does, an alarm action ID from your product's list in the Richmat guide. |
| `datetime` | Alarm date and time | For a one-time or repeating alarm: when it goes off, with a time zone. A repeating alarm uses only the hour and minute. |
| `alarm_id` | Alarm slot | Alarm number, 1 to 7. Leave unset when adding a repeating alarm to use the first free number. Turning an alarm on or off and Delete need it. |
| `weekdays` | Repeat weekdays | For a repeating alarm: the days it repeats, 0 Monday to 6 Sunday. Leave empty for once. Any of `0` (Monday), `1` (Tuesday), `2` (Wednesday), `3` (Thursday), `4` (Friday), `5` (Saturday) or `6` (Sunday). |
| `enabled` | Enabled | On or off for the selected option, such as an alarm or anti-snore. |
| `seconds` | Light duration | For Light timer: the light duration in seconds, one of your product's durations. 0 keeps the light on. |
| `rgb_color` | Light color | For Light color: the color. A product with an eight-color palette accepts only those colors. |
| `value` | Number | For Massage timer: 0, 10, 20 or 30 minutes. For Anti-snore count: 1 to 30. For Anti-snore duration: 5 to 30 in steps of 5. |

### Galaxy Bed Control configuration


`adjustable_bed.galaxy` sets the alarms, the light, the massage timer and the
anti-snore options of a Galaxy bed, with the same fields as `goodvibe`. Choose
alarm action IDs from the [Galaxy command table](beds/richmat.md#galaxy-bed-control).
The bed must report each feature first. Turn alarm on or off takes the number
of an alarm the bed reported and `enabled`, and keeps the rest of that alarm as
it is. Galaxy has no separate sleep sensor.

## Good Vibe Sleep

<a id="goodvibe"></a>
**`goodvibe`**: Sets the alarm, light, massage and anti-snore options of a Good Vibe Sleep bed or its sleep sensor.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | What to set or read. Only the options your product has can run. One of `single` (One-time alarm), `cancel_single` (Cancel one-time alarm), `repeat` (Repeating alarm), `delete` (Delete alarm), `alarms` (Read alarms), `light_color`, `light_duration` (Light timer), `light_off`, `massage_timer`, `snore_switch` (Anti-snore on or off), `snore_count` (Anti-snore count), `snore_time` (Anti-snore duration), `snore_query` (Read anti-snore settings), `part` (Sleep data by period), `time` (Read sleep sensor clock), `realtime` (Live sleep data), `report` (Sleep report), `anti_snore` (Anti-snore) or `sensitivity` (Sensor sensitivity). |
| `action` | Alarm action | For a one-time or repeating alarm: what the alarm does, an alarm action ID from your product's list in the Richmat guide. |
| `datetime` | Alarm date and time | For a one-time or repeating alarm: when it goes off, with a time zone. A repeating alarm uses only the hour and minute. |
| `alarm_id` | Alarm slot | Alarm number, 1 to 7. Leave unset when adding a repeating alarm to use the first free number. Delete needs it. |
| `weekdays` | Repeat weekdays | For a repeating alarm: the days it repeats, 0 Monday to 6 Sunday. Leave empty for once. Any of `0` (Monday), `1` (Tuesday), `2` (Wednesday), `3` (Thursday), `4` (Friday), `5` (Saturday) or `6` (Sunday). |
| `enabled` | Enabled | On or off for the selected option, such as an alarm or anti-snore. |
| `seconds` | Light duration | For Light timer: the light duration in seconds, one of your product's durations. 0 keeps the light on. |
| `rgb_color` | Light color | For Light color: the color. A product with an eight-color palette accepts only those colors. |
| `value` | Number | For Massage timer: 0, 10, 20 or 30 minutes. For Anti-snore count: 1 to 30. For Anti-snore duration: 5 to 30 in steps of 5. |
| `part` | Sleep data setting | For Sleep data by period: 1 or 2 on a sleep sensor whose name starts with RM-, or 11, 12 or 13 on one whose name starts with HJ-. For Sleep report: 1 or 2. |
| `date` | Report date | For Sleep report: the date to read. |
| `report_type` | Report type | For Sleep report: a day or a month. Default day. One of `1` (Day) or `2` (Month). |

### Good Vibe Sleep configuration


`adjustable_bed.goodvibe` sets the alarms, the light and the anti-snore options
your product has, and reads the separate sleep sensor. Choose alarm action IDs
from the [Richmat guide's tables](beds/richmat.md#alarms-and-snore-settings). A
sleep report takes `operation: report`, a `date`, `part` and `report_type`; the
status sensor keeps the reports and each side's live values. Use the bed's
buttons for everyday controls and `hold_control` for held buttons. See the
[Good Vibe Sleep guide](beds/richmat.md#good-vibe-sleep).

## HJBed

<a id="hjbed"></a>
**`hjbed`**: Sets the alarm, light and other options of an HJBed bed. The bed must report the feature first.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | What to set or read. A product with repeating alarms has no one-time alarm, and the other way round. One of `single` (One-time alarm), `cancel_single` (Cancel one-time alarm), `repeat` (Repeating alarm), `delete` (Delete alarm), `query` (Read current settings), `toggle` (Turn alarm on or off), `sync` (Set bed clock), `light_timeout` (Light timer), `light_color` or `mode`. |
| `action` | Alarm action | For a one-time or repeating alarm: what the alarm does, an alarm action such as zero_gravity from your product's list in the Richmat guide. |
| `time` | Time | For a one-time or repeating alarm: when it goes off, in whole minutes. |
| `alarm_id` | Alarm number | Alarm number, 1 to 7. Delete and Turn on or off need a number the bed has reported. For a repeating alarm, leave it unset only to reuse a number deleted during this Bluetooth connection. |
| `weekdays` | Weekdays (empty means once) | For a repeating alarm: the days it repeats. Leave empty for once. Any of `monday`, `tuesday`, `wednesday`, `thursday`, `friday`, `saturday` or `sunday`. |
| `enabled` | Enabled | On or off for a repeating alarm or Turn on or off. Default on. |
| `seconds` | Light timeout in seconds | For Light timer: seconds, 0 to 900, or 1800 to 28800 on products with the long light timer. |
| `rgb_color` | Light color | For Light color: the color. |
| `mode` | Control mode | For Mode: move both heads together, or separately. Only some products have it. One of `split_head` (Separate heads) or `standard`. |

### HJBed configuration


`adjustable_bed.hjbed` sets the one-time or repeating alarms your product has,
reads, deletes and turns them on or off, and sets the light timer, the light
color and, on some products, whether both heads move together. Each product's
alarm actions are listed under
[HJBed alarm actions](beds/richmat.md#hjbed-alarm-actions). See the
[HJBed guide](beds/richmat.md#hjbed) for each product's options.

## Hush Base

<a id="hush_base"></a>
**`hush_base`**: Sets the light, alarms and clock of a Hush Base, reads and sets its separate sleep sensor, or finds its remote. Only the options your product has can run. See the Hush Base guide.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | What to set or read. Light, alarm and clock options run on the bed, sleep data options on the separate sleep sensor, and Find remote on the remote. Only the options your product has can run. One of `remote_find` (Find remote), `light_rgb` (Light color), `light_seconds` (Light timer), `light_off`, `rgb_power` (Light strip on or off), `rgb_color` (Light strip color), `rgb_timer` (Light strip timer), `rgb_mode` (Light strip mode), `rgb_groove` (Light strip rhythm), `rgb_breathe` (Light strip breathing), `alarm` (One-time alarm), `alarm_cancel` (Cancel alarm), `repeat_alarm` (Repeating alarm), `repeat_delete` (Delete repeating alarm), `repeat_query` (Read repeating alarms), `time_sync` (Set bed clock), `sleep_name` (Sleeper name), `snore_detector` (Snore detection), `sensor_time` (Set sleep sensor clock), `sensor_part` (Sleep data by period), `sensor_query_part` (Read sleep data by period), `sensor_live` (Live sleep data), `sensor_report` (Sleep report), `sensor_stop` (Stop sleep data), `sensor_query_time` (Read sleep sensor clock), `sensor_sensitivity` (Sleep sensor sensitivity), `sensor_query_anti_snore` (Read anti-snore setting) or `sensor_anti_snore` (Anti-snore setting). |
| `value` | Value | Number for the selected option: light timer in seconds (0 keeps the light on), light strip timer (5, 8, 10, 13, 15, 18, 21, 24, 27, 30, 120, 210, 300, 390 or 480), light strip mode (2, 3 or 5) or light strip rhythm (1 to 4). Default 0. |
| `rgb_color` | Light color | Color for Light color and Light strip color. |
| `enabled` | Enabled | On or off for Light strip on or off, a repeating alarm, Snore detection, Live sleep data, and the sleep sensor's Anti-snore setting, which applies to both sleepers. Default on. |
| `hour` | Alarm hour | Hour the alarm goes off, 0 to 23. |
| `minute` | Alarm minute | Minute the alarm goes off, 0 to 59. |
| `mode` | Alarm preset | Position the bed moves to when a one-time or repeating alarm goes off. Only your product's alarm positions are accepted. One of `tv`, `zero_g` (Zero gravity), `anti_snore` (Anti-snore), `lounge`, `memory_1`, `memory_2` or `memory_3`. |
| `slot` | Repeating alarm number | Number of the repeating alarm to set or delete, 0 to 255. Default 1. |
| `days` | Weekdays | Days the repeating alarm runs. Any of `monday`, `tuesday`, `wednesday`, `thursday`, `friday`, `saturday` or `sunday`. |
| `part` | Sleep data setting | For Sleep data by period: 1 or 2 on a sleep sensor whose name starts with RM-, or 11, 12 or 13 on one whose name starts with HJ-. For Sleep report: 1, 2 or 3 (RM-) or 1 or 2 (HJ-). Default 1. |
| `report_type` | Report type | Sleep report length: 1 for a day, 2 for a month. Default 1. |
| `year` | Report year | Year of the sleep report, 1970 to 2225. |
| `month` | Report month | Month of the sleep report, 1 to 12. |
| `day` | Report day | Day of the month for a daily report. Use 1 for a monthly report. |
| `source` | Snore sensor | For Snore detection: an entity whose state is 1 while you snore and 0 otherwise. After five snoring readings in a row the bed runs anti-snore. |

### Hush Base


The [Hush Base guide](beds/hush-base.md#configuration-actions) explains each
operation and how to add the separate sleep sensor and remote.

## Instant Comfort

<a id="instant_comfort_firmness"></a>
**`instant_comfort_firmness`**: Sets the main or lumbar firmness for one sleeper of an Instant Comfort air unit. When both change, the lumbar firmness is sent after the main adjustment has finished.

| Field | Name | Meaning |
|-------|------|---------|
| `sleeper` | Sleeper | The left or the right sleeper of the air unit. One of `left` or `right`. |
| `firmness` | Main firmness | Main firmness, a whole number from 5 to 50. |
| `lumbar_firmness` | Lumbar firmness | Lumbar firmness, a whole number from 5 to 50. Only for an ANM V5 air unit set up with four channels. |

Give at least one of the two. An ANM V5 air unit must be idle and report the
layout it was set up with before a firmness is sent: wait for a running
adjustment to finish, or use `stop_all` first. If the main adjustment does not
finish, the lumbar firmness is not sent, and Stop cancels it. ANM V3 and RA air
units take only `firmness` and cannot stop the pump. See the
[Instant Comfort guide](beds/personal-comfort.md#instant-comfort).

Bases set up with the Instant Comfort app also run
[`personal_comfort_sequence`](#personal_comfort_sequence).

## Jerome's power base

<a id="jerome_bed"></a>
**`jerome_bed`**: Run an action from the selected bed layout. Preset saves and long-press controls require confirmation.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | Named layout action, such as head_up, zero_gravity or save_m1. Available actions are listed in the bed guide. |
| `keep` | Keep moving | Keep moving until the duration ends, on controls that support it. |
| `mode` | Operating mode | Mode 0, 1 or 2 on layouts with Mode 1, Mode 2 and Mode 3 controls. Use Side for layouts labeled Left and Right. |
| `confirm` | Confirm action | Required for preset saves and long-press actions. |
| `duration_ms` | Movement duration | How long a continuous control runs, 1 to 60000 milliseconds. Default 1000. |
| `rgb_color` | Light color | For light_color: red, green and blue values. |
| `aroma_times` | Aroma settings | For aroma_settings: mode 2 time in minutes, mode 3 time in minutes, and mode 3 pause in hours. |
| `long_press` | Long press | Use the control's long press when the layout also has a separate save button. Needs Confirm. |

Run a control of your [Jerome's power base](beds/richmat.md#jeromes-power-base)
layout, such as `head_up`, `zero_gravity` or `save_m1`; the guide lists each
layout's controls. Saves and long-press-only controls need `confirm: true`.
`long_press: true` picks the long press when the same save is also a short press.
Saves cannot use `keep: true`.

`keep: true` keeps a control going for `duration_ms` (1 to 60000) where the
control supports it; held controls also support renewable holds. `mode` applies
only to layouts with Mode 1, Mode 2 and Mode 3 buttons. Use `side` for layouts
labelled Left and Right.

Use `action: light_color` with `rgb_color: [255, 68, 68]` once the bed reports
a light, or `action: aroma_settings` with `aroma_times: [1, 1, 2]` once it
reports aroma. The aroma values are the mode 2 and mode 3 times in minutes (1 to
60), then the mode 3 pause in hours (1 to 12). These settings also have number
entities. Alarms use [`set_alarm`](#set_alarm), with the choices of your layout.

## Jiecang

<a id="jiecang_stop_wake"></a>
**`jiecang_stop_wake`**: Stop active wake massage without disabling the stored weekly clock alarm.

<a id="jiecang_wake"></a>
**`jiecang_wake`**: Move to a preset and start the selected wake massage levels immediately.

| Field | Name | Meaning |
|-------|------|---------|
| `preset` | Bed preset | The position the bed moves to. One of `flat`, `zero_g` (Zero gravity), `anti_snore` (Anti-snore), `memory_1` or `memory_2`. |
| `head_level` | Head massage level | Wake massage intensity, with 0 for off and 1 to 3 for increasing intensity. |
| `foot_level` | Foot massage level | Wake massage intensity, with 0 for off and 1 to 3 for increasing intensity. |

## Keeson app layouts

### Ergomotion 4.0


The [Ergomotion 4.0](beds/keeson.md#ergomotion-40) beds have a button for each
control of your product. Held buttons also work with `hold_control` (1 to 60000
ms); the guide lists each control name. Selecting one side's device moves that
side; selecting the combined bed moves both. Some products have no sides.

[`rename`](#rename), [`sync_clock`](#sync_clock) and [`set_alarm`](#set_alarm)
work on these beds. A new name is 1 to 16 characters after leading and trailing
spaces are removed. To end a wake vibration, press the **Dismiss wake
vibration** button; `jiecang_stop_wake` does not work on these beds. The bed
keeps three weekly and three one-time alarms. A one-time alarm must be later
today. Alarm and clock settings apply to the whole bed: select it once, not each
side.

The light color needs a product with a color light that is on; while it is off,
use its light button. The high, medium and low buttons set 100, 60 and 20%
brightness. Meditation Start and Stop are on the products the guide lists; an
automation can repeat Start to keep it going.

## KomfyD and ComfyDS

<a id="comfy_control"></a>
**`comfy_control`**: Moves the bed or runs its timer and lock buttons.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Button | The button to press, or read the current settings. One of `zero` (Flat), `h_increase` (Head up), `h_decrease` (Head down), `f_increase` (Foot up), `f_decrease` (Foot down), `timer_start` (Start timer), `timer_stop` (Stop timer), `lock`, `unlock` or `query` (Read current settings). |

### KomfyD / ComfyDS


The timer duration is the Timer duration select; the Control lock and Timer
switches lock, unlock and start or stop the timer. The head, foot and timer
buttons work as in the app. See the [KomfyD and ComfyDS guide](beds/kaidi.md#komfyd-and-comfyds).

## L&P Adjustable Base

<a id="lp2"></a>
**`lp2`**: Sets the lighting, aromatherapy and fans of an L&P Adjustable Base, or runs one of its remote controls. Use Set alarm for wake-up alarms.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Setting | What to set or run. Each setting needs its own fields. Light and aromatherapy settings need the bed to report them first. One of `color` (Set light color), `light_duration` (Set light duration), `aromatherapy` (Set aromatherapy times), `fan` (Set fan) or `control` (Run control). |
| `rgb_color` | Light color | For Set light color: the color. |
| `seconds` | Light duration (seconds) | For Set light duration: seconds, 0 to 300. |
| `aroma_times` | Aromatherapy times | For Set aromatherapy times: three numbers, 1 to 60 minutes, 1 to 60 minutes and 1 to 12 hours. |
| `fan` | Fan | For Set fan: the head or foot fan. One of `head` or `foot`. |
| `intensity` | Intensity (%) | For Set fan: 0 to 100 percent in steps of 20. |
| `duration` | Fan duration | For Set fan: duration choice 0 to 6, required for either fan. Only the head fan uses it. |
| `confirm` | Confirm programming or saving | Required for a control's long press or save. |
| `control` | Control | For Run control: the control's number in your bed's remote layout, from the layout's list in the Richmat guide. A number that cannot send the chosen press on your bed is refused. |
| `mode` | Control mode | For Run control: the layout's control mode, 0 to 2, one your layout offers. Default 0. |
| `long` | Long press | For Run control: send the control's long press. Needs Confirm. |
| `held` | Continuous movement | For Run control: hold the control for the movement duration. Controls that repeat on their own, such as motor movement, run for the duration without it. |
| `head` | Head selection | For Run control: the head selection, as in the app. Default on. |
| `motor` | Motor | For Run control: the motor a selected-motor control uses, 3 to 5. Default 3. |
| `duration_ms` | Movement duration (milliseconds) | For Run control: how long a held or repeating control runs, 1 to 60000 milliseconds. Default 1000. |

The [L&P Adjustable Base guide](beds/richmat.md#lp-adjustable-base) lists what
each layout accepts, including the
[control numbers](beds/richmat.md#lp-control-numbers) for Run control. Set wake-up alarms with [`set_alarm`](#set_alarm).

## Lady Americana and partner beds

<a id="richmat_resource_bed"></a>
**`richmat_resource_bed`**: Sets the light and massage timer of a Lady Americana or partner bed, or presses a bed button. Set its alarm with Set alarm. Read the current settings before changing the light.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | What to set, read or press. One of `query` (Read current settings), `rgb` (Light color), `lamp_timeout` (Lamp timer), `massage_timer` or `bed_command` (Bed button). |
| `rgb_color` | Light color | For Light color: the color. |
| `seconds` | Light timeout | For Lamp timer: seconds, 0 to 300. 0 keeps the light on. |
| `progress` | Massage timer choice | For Massage timer: slider position, 0 to 5. Only models with the massage timer slider accept it. |
| `command` | Bed button | For Bed button: the button to press. Stop ends movement and massage. One of `head_up`, `head_down`, `foot_up`, `foot_down`, `tv`, `lounge`, `zero_gravity`, `anti_snore` (Anti-snore), `memory_one` (Memory 1), `memory_two` (Memory 2), `memory_three` (Memory 3), `flat` or `voice_stop_request` (Stop). |
| `duration_ms` | Hold duration | For Bed button: how long to hold Head up, Head down, Foot up or Foot down, 1 to 60000 milliseconds. Default 1000. |

### Lady Americana / ACAA / STA Homecare / Zero Gravity


`adjustable_bed.richmat_resource_bed` uses the app and layout chosen in setup.

| Operation | Fields | Notes |
|-----------|--------|-------|
| `query` | none | Reads the layout's alarms and whether the bed has a light |
| `rgb` | `rgb_color` | Needs the bed to report its light first |
| `lamp_timeout` | `seconds` (0 to 300) | Needs the bed to report its light first; 0 keeps the light on |
| `massage_timer` | `progress` (0 to 5) | Only models with the massage timer slider |
| `bed_command` | `command`, optional `duration_ms` (1 to 60000) | Presses the app's bed buttons, whatever the remote layout |

Set the alarm with [`set_alarm`](#set_alarm): one position and optional
massage, as your layout offers them. For example, zero gravity with head and
foot massage:

```yaml
action: adjustable_bed.set_alarm
data:
  device_id: YOUR_BED_DEVICE_ID
  enabled: true
  time: "07:00:00"
  wake_action: zero_g
  massage: true
  massage_zone: both
```

`bed_command` offers head and foot up and down, TV, lounge, zero gravity,
anti-snore, memory one to three, flat and Stop. Memory buttons are sent even if
your bed has fewer memories. Other controls and saving use the layout's buttons,
and held buttons work with `hold_control` and the dashboard card.

If you press Stop while the action is still connecting to a later bed, that bed
is not moved. Holding both sides at once needs a combined bed that stays
connected to both; other combined beds move one side at a time. Timer values and
alarm choices show what was sent; the bed does not report them back. See the
[Lady Americana guide](beds/richmat.md#lady-americana--acaa--sta-homecare--zero-gravity-family).

## L2 Motion

<a id="l2motion"></a>
**`l2motion`**: Sets the light color of an L2 Motion bed, or switches its two bases between wired and wireless sync.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Control | Choose light color or synchronization mode. One of `rgb` (Light color) or `sync_mode` (Synchronization mode). |
| `rgb` | Light color | For Light color: red, green and blue, each 0 to 255. |
| `brightness` | Brightness | For Light color: scales the color, from 0 to 1. Default 1. |
| `wired` | Wired synchronization | For Synchronization mode: on if the two bases are connected with a cable, off for wireless. |
| `confirm` | Confirm synchronization change | Required to change the synchronization mode. |

Every selected bed must support the request before any changes. Use the Light
timer number to change the timer, and [`set_alarm`](#set_alarm) for the alarm
time and strength (`massage_intensity: 1` or `2`, or `enabled: false` to turn it
off). The [L2 Motion guide](beds/motomotion.md#l2-motion) explains which beds
are set up as L2 Motion.

## Leggett & Platt

<a id="leggett_sleep_timer"></a>
**`leggett_sleep_timer`**: Start a delayed preset or cancel the stored sleep timer.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | Start the sleep timer, or cancel the one that is set. One of `start` or `cancel`. |
| `minutes` | Delay | Required to start. Prodigy accepts 1 to 1439 minutes; U Series accepts 15, 30, 45, 60, 75, or 90 minutes. |
| `preset` | Sleep action | Prodigy beds use memory 1 to 4. U Series beds use 0 for flat or memory 1 to 3; memory 3 is only reachable through this timer. |

## Limoss Remote

<a id="limoss_remote_calibrate"></a>
**`limoss_remote_calibrate`**: Runs the remote's calibration after you confirm, then releases the motors.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm calibration | Required: confirms that the remote calibrates the bed. |
| `duration` | Duration | How long to hold calibration, 0.1 to 60 seconds. |

<a id="limoss_remote_features"></a>
**`limoss_remote_features`**: Chooses whether the lamp and massage controls are shown. Turning a control off first turns that feature off on the bed.

| Field | Name | Meaning |
|-------|------|---------|
| `underbed_light` | Lamp controls | Show the lamp controls. |
| `massage` | Massage controls | Show the massage controls. |

<a id="limoss_remote_rename_memory"></a>
**`limoss_remote_rename_memory`**: Renames a memory in Home Assistant. An empty name is allowed.

| Field | Name | Meaning |
|-------|------|---------|
| `preset` | Memory slot | Memory slot 1 to 8, up to the number of memories the remote has. |
| `name` | Name | The name to show. It can be empty. |

### Limoss Remote app


The [Limoss Remote app](beds/limoss.md#limoss-remote) beds also support
[`hold_control`](#hold_control) (0.1 to 60 seconds) and `goto_preset` with an
optional `duration`. Calibration needs `confirmed: true`. Memories 1 to 8 work
up to the number the remote has, for `goto_preset`, `save_preset` and renaming.
A memory name can be empty. Each side of a combined bed keeps its own settings.

## Linak

<a id="linak_move_simultaneously"></a>
**`linak_move_simultaneously`**: Moves two motors together for a set time on a Linak Bed Control or Jensen JMC400, then stops them.

| Field | Name | Meaning |
|-------|------|---------|
| `first_motor` | First motor | The first motor to move. One of `base`, `feet`, `head`, `legs` or `back`. |
| `first_direction` | First direction | Direction of the first motor. One of `up` or `down`. |
| `second_motor` | Second motor | The second motor, different from the first. One of `base`, `feet`, `head`, `legs` or `back`. |
| `second_direction` | Second direction | Direction of the second motor. One of `up` or `down`. |
| `duration_ms` | Duration | How long to move before stopping, 100 to 30000 milliseconds. |

## Linx

<a id="linx_snore_intervention"></a>
**`linx_snore_intervention`**: Run the bed's anti-snore movement once, then ask the bed for its status. It does not listen for snoring.

| Field | Name | Meaning |
|-------|------|---------|
| `hold_minutes` | Hold duration | Minutes the bed holds the anti-snore position. Default 10. |
| `up_speed` | Up speed | The app's up-speed setting for this movement. Default 10. |
| `lift_time` | Lift time | The app's lift-time setting for this movement. Default 10. |

The bed is asked for its status once, on the same connection. See the
[Linx guide](beds/linx.md).

## Logicdata

<a id="logicdata_hold_preset"></a>
**`logicdata_hold_preset`**: Holds a flat, preset or memory button for a set time, then releases it.

| Field | Name | Meaning |
|-------|------|---------|
| `preset` | Preset | The button to hold. One of `flat`, `zero_g` (Zero gravity), `anti_snore` (Anti-snore), `memory_1` or `memory_2`. |
| `duration` | Duration | How long to hold, 0.2 to 60 seconds. |

## Luuna

<a id="luuna"></a>
**`luuna`**: Sets the light of a Luuna bed, or reads the name of its sleep sensor. Set its alarm with Set alarm and its clock with Set bed clock. Only the options your bed reports can run.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | What to set or read. One of `light_rgb` (Light color), `light_seconds` (Light timer), `light_off`, `light_warm` (Warm light), `light_cold` (Cool light) or `sleep_name` (Sleeper name). |
| `value` | Value | Light timer in seconds (0, 300, 600 or 900; 0 keeps the light on), or brightness of Warm light and Cool light in percent (0 to 100). |
| `rgb_color` | Light color | Color for Light color. |

### Luuna +


`adjustable_bed.luuna` works with the Rise, Rise Pro and Rise Pro Light. See
the [Luuna + guide](beds/richmat.md#luuna-) for what each has. The light takes
a color (`light_rgb` with `rgb_color`), warm or cool light with a brightness of
0 to 100 percent in `value`, a timer of 0, 300, 600 or 900 seconds (0 keeps it
on), or off. `sleep_name` reads the name of the Rise or Rise Pro Light sleep
sensor. Set the one-time alarm with [`set_alarm`](#set_alarm) and the clock
with [`sync_clock`](#sync_clock). Not yet confirmed on a real bed.

## Luuna Rise and Power Cool

<a id="richmat_rise"></a>
**`richmat_rise`**: Sets the light and massage timer of a Luuna Rise or Power Cool bed. Set its alarm with Set alarm. Light settings need the bed to report them first.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | What to set or read. One of `query` (Read current settings), `rgb` (Light color), `lamp_timer`, `massage_timer` or `massage_popup` (Massage menu). |
| `rgb_color` | Light color | For Light color: the color. |
| `seconds` | Lamp timer | For Lamp timer: seconds, 0 to 300. |
| `timer_save` | Save the lamp timer | For Lamp timer: save the timer as the app's Save button does, instead of as releasing its slider does. |
| `progress` | Massage timer index | For Massage timer: slider position, 0 to 5. Only models with the massage timer slider accept it. |
| `popup` | Timer popup choice | For Massage menu: a 15, 30 or 45 minute timer, or turn massage on or off. One of `15` (15 minutes), `30` (30 minutes), `45` (45 minutes) or `toggle` (Turn on or off). |

### Luuna Rise / Power Cool bed settings


`adjustable_bed.richmat_rise` uses the app and layout chosen in setup. Use
`query` to read the alarm and lamp settings, `rgb` for the light color, and
`lamp_timer` with `seconds` (0 to 300) and optional `timer_save`. Set the
one-time alarm with [`set_alarm`](#set_alarm): one of the layout's positions,
optional `massage` with a zone, or `none` with `massage` for massage alone. A
position and massage combination the layout does not have is refused before
anything is sent. The bed does not report the alarm back.

`massage_timer` takes `progress` 0 to 5 on models with the massage timer slider.
`massage_popup` takes `popup` (`15`, `30`, `45` or `toggle`) on models with the
massage timer menu. Alarm and lamp settings need the bed to report them on the
current connection, also after it reconnects.

See the [Luuna Rise and Power Cool guide](beds/richmat.md#luuna-rise--power-cool).

## Sinca Comfort Bed

Use [`goto_preset`](#movement-and-memory) for either memory and [`save_preset`](#movement-and-memory)
to run the app's long memory press. Use [`sync_clock`](#sync_clock) to set bed time.
Alarm queries and disable use the action below. See the [bed guide](beds/mline.md#sinca-comfort-bed).

<a id="sinca_comfort_command"></a>
**`sinca_comfort_command`** refreshes settings, reads or disables the wake alarm,
adjusts automatic anti-snore, or handles a local history transfer.

| Field | Name | Description |
|---|---|---|
| `device_id` | Devices | Select one or more Sinca Comfort Bed devices. Choose one physical receiver for history. |
| `side` | Side | Select the left or right side of a combined bed. |
| `action` | Action | Choose `refresh_settings`, `refresh_alarm`, `disable_alarm`, `anti_snore`, `demo_anti_snore`, or `consume_history`. |
| `enabled` | Enable anti-snore | Turn automatic anti-snore on or off. Defaults to on. |
| `position` | Adjustment | Choose `head` or `elevation`. Defaults to `head`. |
| `level` | Level | Choose `low`, `medium`, or `high` for automatic anti-snore. Defaults to `low`. |
| `all_records` | All records | Request all stored history. The default asks for new records. |
| `confirmed` | Confirm history acknowledgement | Let the bed mark report-length history as received. Home Assistant does not save a sleep report. Defaults to false. |

Anti-snore settings and demonstrations require the Sleep receiver. A demonstration
only uses the selected adjustment. Disable writes the alarm-off frame and then
queries the resulting alarm state.

History runs on one current connection. An aligned transfer with no report-length
groups is acknowledged automatically. To also acknowledge a report-length
group, run the action with `confirmed: true`. The optional response gives
`acknowledged` and the number of distinct admitted `records`. A transfer with
no aligned data returns zero records and leaves the bed's history unchanged.


## M Line

<a id="mline_command"></a>
**`mline_command`**: Sets sleep privacy or anti-snore, reads the current settings or alarm, or downloads sleep history.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Setting | What to set or read. Sleep history works on one bed at a time. One of `privacy`, `anti_snore` (Anti-snore), `anti_snore_demo` (Anti-snore demo), `settings_refresh` (Read settings), `alarm_refresh` (Read alarm), `live_query` (Read live data), `history_read` (Read sleep history) or `history_ack` (Confirm sleep history received). |
| `enabled` | Enabled | For Privacy, Anti-snore and Anti-snore demo: on or off. Default on. |
| `angle` | Angle | For Anti-snore and Anti-snore demo: how far the bed moves. Default low. One of `1` (Low), `3` (Medium) or `6` (High). |
| `position` | Position | For Anti-snore and Anti-snore demo: which part of the bed moves. Default head. One of `1` (Head) or `2` (Elevation). |
| `all_records` | All records | For Read sleep history: read all stored nights instead of only the new ones. Default off. |
| `transfer` | Transfer | The transfer code from a finished sleep history download, to confirm you received it. |

### M Line


Choose the M Line app and your bed's layout in setup or Configure. Covers and
preset buttons can be held, also from the dashboard card. Set the clock with
`sync_clock` and the wake alarm with [`set_alarm`](#set_alarm).

`mline_command` takes `device_id`, optional `side`, and an `action`:

| Action | Fields and notes |
|---|---|
| `privacy` | Beds with sleep sensing; `enabled` |
| `anti_snore` | Beds with sleep sensing; `enabled`, `angle` `1`, `3` or `6`, `position` `1` (head) or `2` (elevation) |
| `anti_snore_demo` | Beds with sleep sensing; `position` |
| `settings_refresh` | Reads the settings page |
| `alarm_refresh` | Sets the clock, then reads the alarm |
| `live_query` | Beds with sleep sensing; reads the sensor once |
| `history_read` | Beds with sleep sensing; one side at a time, optional `all_records`. Returns the stored nights and a `transfer` code |
| `history_ack` | Confirms, on the same connection, that you received the `transfer` from a finished read |

A history read ends after one second without new data, or after 30 seconds or
8192 records. It does not confirm itself or create sleep reports: save the
result first, then confirm it with `history_ack`. The `transfer` code expires 30
seconds after the read finishes, and when the bed reconnects or the read is
cancelled. See the [M Line guide](beds/mline.md) for what each reading holds.

## Majestic Home

<a id="majestichome"></a>
**`majestichome`**: Read, create, edit, turn on or off, or delete the bed's alarms. Set the clock with Set bed clock.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | What to read or change. Read the alarms first to see their numbers. One of `list` (Read alarms), `new` (New alarm), `set` (Edit alarm), `toggle` (Turn alarm on or off) or `delete` (Delete alarm). |
| `alarm_id` | Alarm number | Needed to create, edit, turn on or off, or delete an alarm: 1 to 7 for a new alarm, or the number the bed reported. A partial list cannot show which numbers are free. |
| `hour` | Hour | For New alarm and Edit alarm: hour, 0 to 23. Default 7. |
| `minute` | Minute | For New alarm and Edit alarm: minute, 0 to 59. Default 30. |
| `preset` | Alarm position | For New alarm and Edit alarm: the position the bed moves to, one your product has. Default memory 1. One of `zero_gravity`, `anti_snore` (Anti-snore), `memory_1` or `memory_2`. |
| `weekdays` | Weekdays | Leave empty for a one-time alarm. Any of `0` (Monday), `1` (Tuesday), `2` (Wednesday), `3` (Thursday), `4` (Friday), `5` (Saturday) or `6` (Sunday). |
| `enabled` | Enabled | Whether the alarm is on. Default on. |

### Majestic Home settings

`adjustable_bed.majestichome` reads (`list`), adds (`new`), edits (`set`),
turns on or off (`toggle`) or deletes (`delete`) the bed's alarms; set the clock
with [`sync_clock`](#sync_clock). Alarm operations need the bed to report its
clock on the current connection. FARM and JLRM beds take `preset`
(`zero_gravity`, `anti_snore`, `memory_1` or `memory_2`), `hour`, `minute`,
`weekdays` (0 Monday to 6 Sunday; empty means once) and `enabled`.

Every operation except `list` needs `alarm_id`: 1 to 7 for a new alarm, or the
number the bed reported. The bed's replies never show which numbers are free,
so Home Assistant does not pick one for you. Turn on or off reads that alarm
first and changes nothing else; if it changed meanwhile, nothing is sent.

`list` listens for five seconds. In a script it can return `targets`, one
result per bed and `side`, with the alarms it heard and `complete: false`: the
bed may have more alarms than it sent. The alarms are also attributes of the
diagnostic Model sensor, which is disabled by default; turn it on to see them.
See the [Majestic Home guide](beds/richmat.md#majestic-home).

## MLILY

<a id="mlily"></a>
**`mlily`**: Sets the alarm, light, massage and anti-snore options of an MLILY bed, or reads and sets its separate sleep sensor.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | What to set or read. Only the options your product has can run. One of `single` (One-time alarm), `cancel_single` (Cancel one-time alarm), `repeat` (Repeating alarm), `delete` (Delete alarm), `alarms` (Read alarms), `light_color`, `light_duration` (Light timer), `light_off`, `massage_timer`, `snore_switch` (Anti-snore on or off), `snore_count` (Anti-snore count), `snore_time` (Anti-snore duration), `snore_query` (Read anti-snore settings), `part` (Sleep data by period), `time` (Read sleep sensor clock), `realtime` (Live sleep data), `report` (Sleep report), `anti_snore` (Anti-snore), `sensitivity` (Sensor sensitivity), `init` (Start sleep sensing) or `toggle` (Turn alarm on or off). |
| `action` | Alarm action | For a one-time or repeating alarm: what the alarm does, an alarm action ID from your product's list in the Richmat guide. |
| `datetime` | Alarm date and time | For a one-time or repeating alarm: when it goes off, with a time zone. A repeating alarm uses only the hour and minute. |
| `alarm_id` | Alarm slot | Alarm number, 1 to 7. Required to add a repeating alarm, unless you give the alarm as the bed reported it. Delete needs it. |
| `weekdays` | Repeat weekdays | For a repeating alarm: the days it repeats, 0 Monday to 6 Sunday. Leave empty for once. Any of `0` (Monday), `1` (Tuesday), `2` (Wednesday), `3` (Thursday), `4` (Friday), `5` (Saturday) or `6` (Sunday). |
| `enabled` | Enabled | On or off for the selected option, such as an alarm or anti-snore. |
| `seconds` | Light duration | For Light timer: the light duration in seconds, one of your product's durations. 0 keeps the light on. |
| `rgb_color` | Light color | For Light color: the color. A product with an eight-color palette accepts only those colors. |
| `value` | Number | For Massage timer: 0, 10, 20 or 30 minutes. For Anti-snore count: 1 to 30. For Anti-snore duration: 5 to 30 in steps of 5. |
| `part` | Sleep data setting | For Sleep data by period and Sleep report: the setting to send to the sleep sensor. |
| `date` | Report date | For Sleep report: the date to read. |
| `report_type` | Report type | For Sleep report: a day or a month. Default day. One of `1` (Day) or `2` (Month). |
| `alarm_record` | Alarm as reported | For editing or turning on or off an existing alarm: its six numbers as the bed reported them, so the same alarm changes. |
| `left` | Left anti-snore setting | For Anti-snore on the sleep sensor: the left side's setting, a number or a list of numbers. |
| `right` | Right anti-snore setting | For Anti-snore on the sleep sensor: the right side's setting, a number or a list of numbers. |

### MLILY Control configuration


`adjustable_bed.mlily` sets the alarms, light and massage timer of your MLILY
product, and reads and sets its separate sleep sensor. Light and alarm options
need the bed to report them first. Use your product's alarm action IDs, and to
change an existing alarm, the six numbers of `alarm_record` from the status
sensor. Turn alarm on or off changes only whether it is on; editing without an
action keeps the alarm's action. Saving a repeating alarm needs `alarm_id` (1 to
7), or `alarm_record` for an edit: the bed never says when its alarm list is
complete, so Home Assistant cannot pick a free number. Saving and deleting
refresh the list. See the [MLILY Control guide](beds/richmat.md#mlily-control).

## MLILY Remote

<a id="mlily_remote"></a>
**`mlily_remote`**: Sets the countdown alarm of an MLILY MS600 remote, or runs the anti-snore movement of an MS300-SH remote on the left side. Set the clock with Set bed clock.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | Set or cancel the alarm, or run the anti-snore movement. One of `alarm` (Set alarm), `alarm_cancel` (Cancel alarm) or `anti_snore` (Anti-snore intervention). |
| `hour` | Alarm hour | Hour the alarm goes off, 0 to 23. |
| `minute` | Alarm minute | Minute the alarm goes off, 0 to 59. |
| `mode` | Alarm position | Position the bed moves to when the alarm goes off. One of `zero_g` (Zero gravity), `anti_snore` (Anti-snore), `tv`, `memory_1`, `memory_2` or `memory_3`. |

### MLILY Remote settings

`adjustable_bed.mlily_remote` sets or cancels the MS600 countdown alarm and runs
the anti-snore movement on the left side; set the clock with
[`sync_clock`](#sync_clock). The [MLILY Remote guide](beds/richmat.md#mlily-remote)
lists the alarm positions. Two separate receivers keep their own side. When both
sides share one receiver, select the bed: the alarm runs once, and the
anti-snore movement runs on the left.

## Motion Bed

<a id="motion_bed_action"></a>
**`motion_bed_action`**: Run a control by its name, such as kuaijie_k2mfragment_flat. The Motion Bed guide lists the common names; the bed's diagnostics list every name it accepts. Saving, clearing, resetting and changing modules need confirmation.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm stored change | Required for saving, clearing, resetting and changing modules. |
| `action` | Action | Name of the control to run. The Motion Bed guide lists the common names; the bed's diagnostics list every name it accepts. |
| `branch` | Preset step | For a preset you can program: recall it, save the current position to it, or clear it. Default recall. One of `app`, `save` or `clear`. |
| `duration` | Duration | How long a movement control runs, 0.01 to 10 seconds. Default 1. |

<a id="motion_bed_air_setting"></a>
**`motion_bed_air_setting`**: Reads or saves the air strength and optional timer of one air mode.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm stored change | Required for changes the bed stores. |
| `mode` | Air mode | Air mode by number: 3 full body, 18 back, 4 neck, 5 waist or 12 yoga. |
| `query` | Read only | Read the mode's current settings instead of saving. Default off. |
| `gear` | Strength | Required to save: air strength, 1 to 8. |
| `timer` | Timer | Optional when saving: 0 for 10 minutes, 1 for 20 minutes or 2 for 30 minutes. |

<a id="motion_bed_audio"></a>
**`motion_bed_audio`**: Select a track, preview a track, or set volume on a target that reports audio support.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm stored change | Required for changes the bed stores. |
| `operation` | Operation | Choose a track or set the volume. One of `track` or `volume`. |
| `value` | Value | Track number or volume, 1 to 5. |
| `preview` | Preview | For Track: play a preview of the track. Default off. |

<a id="motion_bed_calibration"></a>
**`motion_bed_calibration`**: Save the app’s flat and side calibration readings. Confirm before changing calibration.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm stored change | Required for changes the bed stores. |
| `flat` | Flat | Reading while lying flat, as the app shows it, 0 or more. |
| `side_position` | Side position | Reading while lying on your side, as the app shows it, 0 or more. |

<a id="motion_bed_module"></a>
**`motion_bed_module`**: Lists, adds or removes the motor, air or heating modules of a Motion Bed hub. Adding and removing need confirmation.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm stored change | Required to add or delete a module. |
| `operation` | Operation | List the hub's modules, add one, or delete one. One of `query` (Read current settings), `bind` (Add) or `delete`. |
| `module_type` | Module type | For Add and Delete: 10 for a motor, 11 for air or 12 for heating. |
| `address` | Address | For Add: the module's Bluetooth address, six pairs of hexadecimal digits separated by colons. |

<a id="motion_bed_pressure"></a>
**`motion_bed_pressure`**: Adjusts one air channel, or saves all twelve air pressures at once.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm stored change | Required for changes the bed stores. |
| `operation` | Operation | Adjust one channel now, or save all twelve. One of `live` or `save`. |
| `channel` | Channel | For Live: the air channel, 0 to 11. |
| `value` | Pressure | For Live: pressure, 0 to 9. |
| `values` | Pressures | For Save: twelve pressures, 0 to 9 each, one per channel. |

<a id="motion_bed_sleep_angles"></a>
**`motion_bed_sleep_angles`**: Saves the four flat and four side-sleeping positions used by sleep sensing. Use the values shown in the app.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm stored change | Required for changes the bed stores. |
| `page` | Motor count | Number of motors on the app page the positions come from: 2, 3 or 4. |
| `flat` | Flat positions | Four numbers, 0 to 255 each: the flat positions the app shows. |
| `side_positions` | Side positions | Four numbers, 0 to 255 each: the side-sleeping positions the app shows. |

<a id="motion_bed_sleep_report"></a>
**`motion_bed_sleep_report`**: Reads live, timer, day or month sleep data.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm stored change | Not used when reading a report. |
| `kind` | Report | Which sleep data to read. One of `month`, `real` (Live), `timer` or `day`. |
| `offset` | Days back | For Day: how many days back, 0 to 29. Default 0. |
| `window_offset` | Chart start | For Day: start the 12-hour chart 0 to 4 hours after 20:00. Default 0. |

<a id="motion_bed_sleep_timer"></a>
**`motion_bed_sleep_timer`**: Chooses a bedtime timer or a fall-asleep timer from the app's list.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm stored change | Required for changes the bed stores. |
| `slot` | Timer | Timer number from the app's list: 0 to 8, or 0 to 4 for the fall-asleep timer. |
| `fall` | Fall-asleep timer | Choose from the fall-asleep timers instead of the bedtime timers. Default off. |

<a id="motion_bed_thermal_schedule"></a>
**`motion_bed_thermal_schedule`**: Saves a heating or cooling timer with its strength.

| Field | Name | Meaning |
|-------|------|---------|
| `confirmed` | Confirm stored change | Required for changes the bed stores. |
| `hour` | Hour | Hour the timer runs, 0 to 23. |
| `minute` | Minute | Minute the timer runs, 0 to 59. |
| `mode` | Mode | 1 for heating, 2 for cooling. |
| `gear` | Strength | Strength, 1 to 4. |

### Motion Bed app actions


The [Motion Bed guide](beds/ff_frame.md#services-2) covers all of the Motion
Bed actions, including the alarm, sleep calibration and reports, hub modules, air
pressure, heating schedules and audio. The guide lists the
[control names](beds/ff_frame.md#control-names-for-motion_bed_action) for
`motion_bed_action`. Changes the bed stores need `confirmed:
true`. Selecting one side's device acts on that side.

## MotoMotion

<a id="motomotion"></a>
**`motomotion`**: Save body measurements and your own posture positions on MotoMotion beds whose app has a users tab. Measurements are height, buttocks height and knee height in centimetres. This does not read where the motors are.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | Save, select or delete a user, or recall, save, reset or fine tune a posture. One of `save_user`, `select_user`, `delete_user`, `recall`, `save_posture`, `reset_posture` or `fine_tune` (Fine-tune). |
| `user` | User | Name of the local user to save or select. |
| `dimensions` | Body measurements | Three numbers in order: height, buttocks height and knee height, in centimetres. |
| `posture` | Posture | Upright, recline, TV or lay posture. One of `upright`, `recline`, `tv` or `lay` (Lie flat). |
| `targets` | Posture positions | Position for each of the five motors (head, base, back, lumbar and tilt), within the app's slider range. |

## Nisco and MLILY Supreme

<a id="richmat_mh_control"></a>
**`richmat_mh_control`**: Run one of the selected app and model's controls, read one setting from the bed, or set the app mode used by later controls.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | Press a control, save with a remote button, read one setting, or set the app mode used by later controls. One of `press` (Press control), `remote_long` (Save with remote button), `query` (Read setting) or `app_mode` (Set app mode). |
| `control` | Control | The control's name, as its button or the app shows it, such as Flat, Memory 1, Save M1 or Massage: Mode. Add up or down for a motor, such as Back up. |
| `query` | Setting to read | For Read setting: the setting to read. One of `version` (Firmware version), `exit_one_minute` (Leave one-minute mode), `alarm`, `light`, `mattress`, `waist_mattress`, `snore` (Snore intervention), `diagnostics` (Component check), `motor_mode`, `motor1_angle` (Motor 1 angle), `motor2_angle` (Motor 2 angle), `motor3_angle` (Motor 3 angle), `motor4_angle` (Motor 4 angle), `massage` or `light_lock`. |
| `transmit_mode` | Transmit mode | For Set app mode: the app's transmit mode setting, which later controls use. Default 0. One of `mode_0` (Transmit mode 0 (default)), `mode_1` (Transmit mode 1) or `mode_2` (Transmit mode 2). |
| `motor_group` | Motor group | For Set app mode: the app's motor group, which decides the motor mode choices. One of `single`, `group_sync` (Synchronized group) or `group_split` (Split group). |

<a id="richmat_mh_sleep_mode"></a>
**`richmat_mh_sleep_mode`**: Set the separate sleep sensor for one or two sleepers.

| Field | Name | Meaning |
|-------|------|---------|
| `mode` | Sleepers | Set the separate sleep sensor for one or two sleepers. One of `single` (One sleeper) or `double` (Two sleepers). |

### Nisco and MLILY Supreme controls

`adjustable_bed.richmat_mh_control` takes `action: press` with a `control`
named as its button or the app shows it (add `up` or `down` for a motor, such as
`Back up`), `action: remote_long` to save with an attached remote's button, or
`action: query` with the setting to read. A control your model does not have is
refused. Saving with the remote button waits three seconds before it saves and
releases; Stop cancels it. `action: app_mode` sets the app's `transmit_mode`
(`mode_0`, `mode_1` or `mode_2`) and `motor_group` (`single`, `group_sync` or
`group_split`, as the model offers) for later controls on that side. It sends
nothing to the bed itself. The motor group decides the Motor mode choices.

`richmat_mh_sleep_mode` works with the separate sleep receiver of Nisco and Bed
Tech beds; MLILY Supreme does not have it. Alarms use [`set_alarm`](#set_alarm)
with the alarm page the bed reports; the light color uses
`richmat_mh_light_color`. A mattress alarm needs its mattress chosen and
switched on. The separate HJ_Bed receiver has sensing and anti-snore entities
and no motor actions.

Every selected bed is checked before any control is sent, and one side's
device keeps its side. The transmit mode and the mattress pad choices do not
pick another Bluetooth device.

## OKIN SleepEase

<a id="doublesleep_configure"></a>
**`doublesleep_configure`**: Sets the alarm, anti-snore and sleep sensor sensitivity of an OKIN SleepEase bed, reads its sleep report, or saves a named position. Reports appear on the bed's report sensors. Send only the fields of the selected setting.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Setting | What to set or read. Each setting takes only its own fields. One of `alarm` (Set alarm), `anti_snore` (Anti-snore), `anti_snore_demo` (Anti-snore demo), `sensitivities` (Sensitivity), `report` (Sleep report), `save_preset` or `capabilities` (Read features). |
| `hour` | Alarm hour | For Set alarm: hour, 0 to 23. |
| `minute` | Alarm minute | For Set alarm: minute, 0 to 59. |
| `weekdays` | Repeat on | For Set alarm: days the alarm repeats. Leave empty for a one-time alarm at the next occurrence of the time. Any of `sun` (Sunday), `mon` (Monday), `tue` (Tuesday), `wed` (Wednesday), `thu` (Thursday), `fri` (Friday) or `sat` (Saturday). |
| `alarm_preset` | Alarm action | For Set alarm: what the bed does when the alarm goes off. One of `zero_g` (Zero gravity), `flat`, `memory_1`, `memory_2` or `vibration`. |
| `alarm_massage` | Alarm massage | For Set alarm: also start massage when the alarm goes off. Default off. |
| `mode` | Anti-snore level | For Anti-snore and Anti-snore demo: level, 1 to 3. |
| `pwm` | Anti-snore strength | For Anti-snore and Anti-snore demo: movement strength, 0 to 255. Only beds with the slow anti-snore setting accept it. Leave unset to keep the bed's setting. |
| `timer` | Anti-snore time | For Anti-snore and Anti-snore demo: movement time, 0 to 255. Only beds with the slow anti-snore setting accept it. Leave unset to keep the bed's setting. |
| `sensor_side` | Sensor sides | For Sensitivity: which sensor sides are used, 1, 2 or 3. Leave unset to keep the bed's setting. Some models can only read it. |
| `left_sensitivity` | Left sensitivity | For Sensitivity: left sensor sensitivity. Leave unset to keep the bed's setting. One of `1` (Low), `2` (Medium) or `3` (High). |
| `right_sensitivity` | Right sensitivity | For Sensitivity: right sensor sensitivity. Leave unset to keep the bed's setting. One of `1` (Low), `2` (Medium) or `3` (High). |
| `date` | Report date | For Sleep report: the date to read. |
| `report_side` | Report sensor side | For Sleep report: the sensor side to read. One of `left` or `right`. |
| `report_kind` | Report period | For Sleep report: a day or a month. One of `day` or `month`. |
| `preset` | Preset to program | For Save preset: the position that stores where the bed is now. One of `memory_1`, `memory_2`, `anti_snore` (Anti-snore), `lounge`, `tv` or `zero_g` (Zero gravity). |
| `capability_page` | Feature list | For Read features: which feature list to read, 0 to 255. Default 0. |

### OKIN SleepEase / DoubleSleep


`doublesleep_configure` sets the alarm, runs or tries out anti-snore, sets the
sensor sensitivity, reads a day or month sleep report, saves a named position or
reads the bed's features. The [SleepEase guide](beds/okin-nframe.md#configuration-and-reports)
lists which models have which settings. `report_side` picks the sensor to read,
separately from the combined bed's `side`. The report sensors keep the results
for automations.

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
| `operation` | Operation | What to press, set or read. A product with one-time alarms has no repeating alarms, and the other way round. One of `press`, `save`, `light_color`, `light_duration`, `light_off`, `single` (Set one-time alarm), `cancel_single` (Cancel one-time alarm), `alarms` (Read alarms), `repeat` (Set alarm), `enable` (Turn alarm on or off) or `delete` (Delete alarm). |
| `control` | Control | For Press and Save: the control, one your product has. One of `head_up`, `head_down`, `foot_up`, `foot_down`, `head_foot_up` (Head and foot up), `head_foot_down` (Head and foot down), `flat`, `memory_1`, `memory_2`, `lounge` or `zero_gravity`. |
| `duration_ms` | Press duration | For Press: how long to hold the control, 0 to 60000 milliseconds. Default 1000. Save always holds for 3 seconds. |
| `datetime` | Alarm time | For an alarm: when it goes off, with a time zone. A repeating alarm uses only the hour and minute. |
| `alarm_id` | Alarm slot | Choose 1 through 7 explicitly when creating an alarm. Read the alarms first (the Alarms sensor lists them) before editing, turning on or off, or deleting one. |
| `mode` | Wake action | For an alarm: the position the bed moves to. One-time alarms take Lounge only. Leave unset when editing to keep the alarm's position. One of `lounge`, `zero_gravity`, `memory_1` or `memory_2`. |
| `weekdays` | Weekdays | Days the alarm repeats. An empty list sets a one-time alarm; leaving the field out keeps an edited alarm's days. Any of `monday`, `tuesday`, `wednesday`, `thursday`, `friday`, `saturday` or `sunday`. |
| `enabled` | Enabled | For Turn alarm on or off: whether the alarm is on. |
| `seconds` | Light duration | For Light duration: seconds, 0 to 900. 0 keeps the light on. |
| `rgb_color` | Light color | For Light color: the color. |

### Okimiki controls and alarms


Use `adjustable_bed.okimiki` with one or more beds, or one side's device, and an
`operation`; your product decides which operations it has. `press` takes
`control` and `duration_ms`; `save` holds the preset for three seconds. Covers,
memory buttons and `hold_control` work too.

The light takes `light_color` (`rgb_color`), `light_duration` (`seconds`, 0 to
900; 0 keeps it on) and `light_off`, once the bed reports its light. Set the
clock with [`sync_clock`](#sync_clock).

IQRM beds have a one-time alarm (`single` with `datetime`, Lounge only) and
`cancel_single`. KWRN beds have `alarms`, `repeat` (`datetime`, `mode`, optional
`weekdays` and `enabled`), `enable` and `delete`. Read the alarms with `alarms`
before changing one by `alarm_id`; the Alarms diagnostic sensor (disabled by
default) lists them with time, wake action, days and on or off. An edit keeps
the fields you leave out. An empty `weekdays` list means once; leaving the field
out keeps an edited alarm's days. Alarm operations need the bed to report its
clock first. The bed does not confirm the alarm back.

Okimiki alarms are not on [`set_alarm`](#set_alarm) yet: editing this bed's
alarms needs safeguards that action does not have yet.

## Personal Comfort

<a id="personal_comfort_sequence"></a>
**`personal_comfort_sequence`**: Runs a full body massage, or moves one base of a pair to a preset while the other base lowers its feet for 30 seconds.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Sequence | The sequence to run. The two preset sequences need a combined pair: the selected side moves to the preset and the other side lowers its feet. One of `full_body_massage`, `flat_with_peer_foot` (Flat, other side lowers its feet) or `anti_snore_with_peer_foot` (Anti-snore, other side lowers its feet). |

Full body massage starts the head massage, then the foot massage half a second
later. The two preset sequences need a combined pair that connects to both bases at
once, and a `left` or `right` side: the selected base moves to the preset and the other base lowers its feet
for 30 seconds. Every base is checked before anything starts, and Stop ends the
sequence. See the [Personal Comfort guide](beds/personal-comfort.md).

The same action runs on Instant Comfort bases. Instant Comfort Malouf and Reverie
V2 bases take `goto_preset` and `save_preset` for memories 1 and 2; Reverie V1
bases and air units have no bed memory.

## Power Bob Base

<a id="bobpowerbase"></a>
**`bobpowerbase`**: Sets the repeating alarms and the light of a Power Bob Base, when the bed reports them. Set the clock with Set bed clock.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | What to set or read. Only the options your product has can run. One of `repeat` (Save repeating alarm), `delete` (Delete alarm), `alarms` (Read alarms), `light_color` (Set light color), `light_duration` (Set light duration) or `light_off` (Turn light off). |
| `action` | Alarm preset | For Save repeating alarm: the position the bed moves to when the alarm goes off. One of `anti_snore` (Anti-snore), `zero_gravity`, `tv`, `memory_1` or `memory_2`. |
| `datetime` | Alarm date and time | For Save repeating alarm: when it goes off, with a time zone. Only the hour and minute count. |
| `alarm_id` | Alarm slot | Alarm number, 1 to 7. Leave unset when adding a repeating alarm to use the first free number. Set it when the bed's alarm list may be incomplete. Delete needs it. |
| `weekdays` | Repeat weekdays | For a repeating alarm: the days it repeats, 0 Monday to 6 Sunday. Leave empty for once. Any of `0` (Monday), `1` (Tuesday), `2` (Wednesday), `3` (Thursday), `4` (Friday), `5` (Saturday) or `6` (Sunday). |
| `enabled` | Enabled | For Save repeating alarm: whether the alarm is on. Default on. |
| `seconds` | Light duration | For Set light duration: whole minutes from 0 to 15, given in seconds. 0 keeps the light on. |
| `rgb_color` | Light color | For Light color: the color. A product with an eight-color palette accepts only those colors. |

### Power Bob Base configuration

`adjustable_bed.bobpowerbase` sets the repeating alarms and the light once the
bed reports its light; set the clock with [`sync_clock`](#sync_clock). The alarm
positions are `anti_snore`, `zero_gravity`, `tv`, `memory_1` and `memory_2`; a
new alarm takes a `datetime` with a time zone. Days run from 0 Monday to 6
Sunday, an empty list means once, and `enabled` turns the alarm on or off. Give
`alarm_id` when the bed's alarm list may be incomplete. The light duration is
whole minutes from 0 to 15, given in seconds; 0 keeps it on.

The bed's buttons move it, recall and save positions. Held movement uses
`hold_control` with the bed's `goodvibe_` control names. SH products have left
and right controls. Holding both sides with a renewable hold needs a combined
bed that moves both sides at once. See [Power Bob Base](beds/richmat.md#power-bob-base).

## RMControl

<a id="rmcontrol_anti_snore"></a>
**`rmcontrol_anti_snore`**: Turns anti-snore on or off, or sets how it responds to snoring.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | Turn anti-snore on or off, change how it responds, or read its current settings. One of `switch` (Turn on or off), `configure` (Settings) or `query` (Read current settings). |
| `enabled` | Enabled | Required for Turn on or off: turn anti-snore on or off. |
| `mode` | Response type | Required for Settings: respond with a number of nudges, or for a duration. One of `count` (Number of nudges) or `time` (Duration). |
| `value` | Nudges or duration | Required for Settings: how many nudges, or how long, depending on the response type, 0 to 255. |

## Reverie

<a id="reverie_pairlink_alarm_comfort"></a>
**`reverie_pairlink_alarm_comfort`**: Sets every comfort value the Pairlink alarm uses, including the ones that stay the same.

| Field | Name | Meaning |
|-------|------|---------|
| `comfort` | Comfort values | All seven Pairlink comfort values. Every selected bed is checked before any changes. |

<a id="reverie_run_routine"></a>
**`reverie_run_routine`**: Run a routine of comfort steps on the selected Reverie bed. It replaces any routine the bed is running.

| Field | Name | Meaning |
|-------|------|---------|
| `steps` | Steps | The comfort settings to apply, in order, each with a duration in minutes. Pairlink beds skip settings you leave out and use at least one minute per step; other Reverie beds need a duration for every step. Use an automation to choose when the routine starts. |

<a id="reverie_set_comfort"></a>
**`reverie_set_comfort`**: Sends one comfort setting, with its head, foot, lumbar, massage, timer and mode values, to each selected Reverie bed.

| Field | Name | Meaning |
|-------|------|---------|
| `comfort` | Comfort values | Head, foot, lumbar, massage, timer and mode values. Each selected bed is checked before any changes. |

### Reverie comfort actions


`reverie_set_comfort` takes a `comfort` object with optional `head_position`,
`foot_position`, `lumbar_position`, `head_massage`, `foot_massage`, `timer_byte`
and `mode`. Each bed checks the values it supports before any bed changes. A
bed with the Nightstand receiver needs all five position and massage values.
A bed with the older receiver applies the changed values once its position
readings settle. Pairlink beds send only the values that changed. `timer_byte`
is the app's timer setting, 0 to 255, not a number of minutes.

`reverie_run_routine` takes `steps` in order, each with a whole number of
`duration_minutes` and an optional `comfort` object, and replaces the bed's
running routine. Use automations to choose when it starts. Pairlink beds skip
settings you leave out and use at least one minute per step; other Reverie beds
need a duration for every step. The `side` field picks the side of a combined
bed as usual.

Stop ends the routine as well as the movement. On a combined bed with two
receivers, routines and the older receiver's comfort settings need the bed to
stay connected to both receivers at once.

Use automations to run `reverie_set_comfort`, `reverie_run_routine`,
`goto_preset` and `save_preset` at set times. The app's phone alarms are not
part of the integration.

## Richmat (classic apps)

<a id="richmat_classic"></a>
**`richmat_classic`**: Sets the alarm, light, aroma and massage timer of an Avocado Eco Base, CoasterSleep, Forty Winks, Milemont or Superior bed, or moves its desk. Only the options your bed reports can run.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | What to set or read. One of `query` (Read current settings), `alarm` (One-time alarm), `cancel_alarm`, `rgb` (Light color), `lamp_slider` (Lamp brightness), `lamp_save` (Save lamp setting), `aroma`, `massage_timer`, `massage_popup` (Massage menu), `desk_target` (Desk target height), `desk_unit` (Desk height unit), `desk_recall` or `desk_reset`. |
| `action` | Alarm action | For One-time alarm: what the alarm does, a name such as node_1. The Richmat guide lists the names for the common layouts; for other layouts, the bed's diagnostics do. |
| `time` | Alarm time | For One-time alarm: the time it goes off, at its next occurrence, in whole minutes. |
| `minutes` | Lamp minutes | For Lamp brightness and Save lamp setting: minutes, 0 to 15. |
| `rgb_color` | Light color | For Light color: the color. |
| `aroma_times` | Aroma times | For Aroma: three numbers, 1 to 60 minutes, 1 to 60 minutes and 1 to 12 hours. |
| `progress` | Massage timer slider | For Massage timer: slider position, 0 to 5. Only models with the massage timer slider accept it. |
| `height` | Desk target | For Desk target height: the height, within the range the desk reports. |
| `unit` | Desk unit | For Desk height unit: centimeters or inches. One of `cm` (Centimeters) or `inches`. |
| `slot` | Desk button | For Desk recall: desk button, 1 to 4. |
| `popup` | Massage popup choice | For Massage menu: a 15, 30 or 45 minute timer, or turn massage on or off. One of `15` (15 minutes), `30` (30 minutes), `45` (45 minutes) or `toggle` (Turn on or off). |
| `duration_ms` | Desk button duration | For Desk recall: how long to hold the desk button, 1 to 60000 milliseconds. Default 1000. |

### Classic Richmat app settings


`adjustable_bed.richmat_classic` works with the Avocado Eco Base, CoasterSleep,
Forty Winks, Milemont and Superior apps.

| Operation | Fields | What it does |
|---|---|---|
| `alarm` | `action`, `time` | Sets one [alarm action](beds/richmat.md#classic-alarm-actions), such as `node_1`, for a time in whole minutes |
| `cancel_alarm` | None | Cancels the bed's alarm |
| `lamp_slider` / `lamp_save` | `minutes`, 0 to 15 | Changes the lamp timer, as moving or saving the app's slider does |
| `massage_popup` | `popup`: `15`, `30`, `45` or `toggle` | Picks a choice from the layout's massage timer menu |
| `massage_timer` | `progress`: 0 to 5 | Sets the massage timer slider, on models that have it |
| `desk_target` | `height` | Moves the desk to a height within the range it reports |
| `desk_unit` | `unit`: `cm` or `inches` | Sets the desk's height unit |
| `desk_recall` | `slot`: 1 to 4, optional `duration_ms`: 1 to 60000 | Holds a desk button; button 4 is reset |
| `desk_reset` | None | Confirms a new desk error once; the last error stays visible |

Alarm, light and aroma options need the bed to report them first. The alarm goes
off at the next occurrence of the time; the current minute means tomorrow. It
does not repeat. Desk operations work only with a desk set up as one. Wi-Fi and
cloud settings are not available. See the
[classic Richmat guide](beds/richmat.md#classic-richmat-apps).

## Richmat app

<a id="richmat_app"></a>
**`richmat_app`**: Sets the light, alarm, heated blanket, sleep sensing and other options of a Richmat app bed. Only the options your product has can run. Read a setting first before changing it.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | What to set or read. Sleep options run on the separate sleep sensor; all other options run on the bed. One of `detection` (Bed detection), `toggle_alarm` (Turn alarm on or off), `query` (Read current settings), `single_alarm` (One-time alarm), `cancel_alarm`, `repeat_alarm` (Repeating alarm), `delete_alarm`, `light_timer`, `light_rgb` (Light color), `strip_rgb` (Light strip color), `strip_timer` (Light strip timer), `strip_groove` (Light strip rhythm), `strip_color_mode` (Light strip color mode), `strip_breathe` (Light strip breathing), `strip_power` (Light strip on or off), `therapy_light`, `therapy_sound`, `therapy_timer`, `music_source`, `white_noise`, `snore` (Anti-snore), `get_off_bed` (Out-of-bed alert), `snore_intervention` (Anti-snore response), `blanket_power` (Heated blanket on or off), `blanket_mode` (Heated blanket mode), `blanket_temperature` (Heated blanket temperature), `blanket_delay` (Heated blanket delay), `blanket_mite` (Heated blanket mite mode), `blanket_settings` (Heated blanket settings), `blanket_sleep` (Heated blanket sleep mode), `usb` (USB power), `demo` (Run a demo), `sleep_time` (Read sleep sensor clock), `sleep_part` (Sleep data by period), `sleep_realtime` (Live sleep data), `sleep_report`, `sleep_snore` (Snore data), `sleep_sensitivity` (Sleep sensor sensitivity), `sleep_init` (Start sleep sensing), `sleep_cancel` (Stop sleep sensing) or `sleep_poll` (Read sleep data). |
| `value` | Value | Number for the selected option: light or light strip timer in seconds (0 to 900), therapy timer (30, 60 or 480), heated blanket delay (1 to 12), anti-snore response (0 to 255), music source (3), sleep data by period (0 reads it, 11 off, 12 automatic, 13 on), or snore data (0 reads it, any other number sets it). Default 0. |
| `mode` | Mode | Choice for the selected option: heated blanket mode (1 cool, 2 warm), therapy light, therapy sound or white noise (0 off, 1 to 3), light strip rhythm (1 to 4), light strip color mode (2, 3 or 5), or music source (1). Default 0. |
| `enabled` | Enabled | Turns the selected option on or off: a repeating alarm or Turn alarm on or off, light strip, anti-snore, out-of-bed alert, heated blanket, mite mode, delay, bed detection, reading sleep data, or snore data when its Value is not 0. To stop a one-time alarm, use Cancel alarm. Default on. |
| `rgb_color` | Light color | Color for Light color and Light strip color. A bed without warm and cold lighting accepts only the colors of its own palette. |
| `opacity` | Brightness | Brightness of Light color, 10 to 100 percent. Default 100. |
| `zone` | Blanket zone | Heated blanket zone: A, B or both. A sleep schedule takes A or B. Default A. One of `1` (A), `2` (B) or `3` (Both). |
| `temperature` | Temperature | Heated blanket temperature in °C: 16 to 25 in cool mode, 25 to 55 in warm mode. Default 25. |
| `flags` | Blanket settings | Heated blanket settings: six on or off values, all required. The bed's status shows the current six. |
| `sleep` | Blanket sleep schedule | Heated blanket sleep schedule for zone A or B, with enabled, mode (1 cool, 2 warm), start_hour, start_minute, end_hour and end_minute (5 to under 16 hours apart), days (0 Monday to 6 Sunday), after_mode (1 keeps the blanket on, 0 turns it off after the delay), delay (1 to 60), four temperatures (16 to 25 cool, 25 to 40 warm) and automatic. |
| `weekdays` | Weekdays | Days for a repeating alarm: 0 Monday to 6 Sunday, or 7 for once. |
| `steps` | Demo steps | Steps of a demo, run in order. Each step has an action (a control name from the Richmat guide), sustain (hold it), seconds (0 to 60) and a delay before the next step (0 to 600 seconds). Leave empty to repeat the last demo you ran. |
| `action` | Alarm action | What a one-time or repeating alarm does: one of your product's alarm actions from the Richmat guide. |
| `query` | Setting to read | For Read current settings: alarms, snore, blanket, blanket_power, blanket_settings, sleep_name, blanket_sleep_a or blanket_sleep_b. Default alarms. |
| `datetime` | Alarm time or report date | Time of a one-time or repeating alarm (only the hour and minute count), or the date of a sleep report. |
| `alarm_id` | Alarm number | Repeating alarm number, 1 to 7. Turning an alarm on or off needs a number the bed has reported. Default 1. |
| `cycle` | Repeat demo | Repeat the demo until you stop it. A repeating demo needs a delay or a bed action. |
| `part` | Sleep report part | Part of the sleep report to read: 11, 12 or 13. Default 12. |
| `report_type` | Report type | Sleep report length: 1 for a day, 2 for a month. Default 1. |

<a id="richmat_mh_aroma"></a>
**`richmat_mh_aroma`**: Sets the three aroma timing sliders of a Richmat app bed.

| Field | Name | Meaning |
|-------|------|---------|
| `mode2_startup_minutes` | Mode 2 startup | Minutes, 1 to 60. |
| `mode3_startup_minutes` | Mode 3 startup | Minutes, 1 to 60. |
| `mode3_pause_hours` | Mode 3 pause | Hours, 1 to 12. |

<a id="richmat_mh_light_color"></a>
**`richmat_mh_light_color`**: Sets the color of the light, or of the button lights, on a Richmat app bed.

| Field | Name | Meaning |
|-------|------|---------|
| `rgb_color` | Color | Red, green and blue, 0 to 255. |

### Richmat app aroma, light and alarms

Bed and vibrating-mattress alarms use [`set_alarm`](#set_alarm); the bed counts
down to the alarm time, and the mattress alarm runs once or every day.
`richmat_mh_aroma` sends the aroma page's three timing settings, and
`richmat_mh_light_color` sets the light color on models without a light on/off
button.

### Richmat 4.2.0 configuration


`adjustable_bed.richmat_app` sets the light, alarms, heated blanket, bed
detection, anti-snore and out-of-bed alert, USB power and demos your product
has; Stop ends a demo. The sleep options act on a separate Richmat sleep
sensor, added as its own device. See the [Richmat guide](beds/richmat.md#richmat-420).

## Rize

<a id="rize_program_preset"></a>
**`rize_program_preset`**: Store the current position as a default preset on one physical Rize bed. Select one side of a combined bed and explicitly confirm.

| Field | Name | Meaning |
|-------|------|---------|
| `preset` | Preset | The preset that stores where the bed is now. Only presets your product can save are accepted. One of `zero_g` (Zero gravity), `anti_snore` (Anti-snore), `book` or `leisure`. |
| `confirm` | Confirm programming | Required: confirms that the preset is overwritten. |

### Rize Beds default-preset programming


`adjustable_bed.rize_program_preset` saves where the bed is now as one of its
default presets (`zero_g`, `anti_snore`, `book` or `leisure`), with `confirm:
true`. It works on one bed at a time, on Rize products that can save presets;
`book` (reading) needs a product with a reading button, as the
[Rize guide](beds/kaidi.md#rize-beds) lists. For a combined bed, select one
side's device or give `side: left` or `side: right`; Both is refused.

## Sleep Number

<a id="sleep_number_command"></a>
**`sleep_number_command`**: Runs a Sleep Number control or reading. Readings return their results. See the actions guide for each command's options.

| Field | Name | Meaning |
|-------|------|---------|
| `command` | Command | Only commands supported by the selected bed can run. One of `bind_foundation` (Pair base), `cancel_current_diagnostic_run` (Cancel bed diagnostics), `cancel_target_preset`, `create_temperature_program`, `delete_temperature_program`, `firmness_favorite`, `firmness_favorites`, `foot_warming`, `foot_warming_status`, `foundation_status`, `get_active_temperature_programs`, `get_actuator_movement_status`, `get_actuator_position`, `get_bed_configuration`, `get_central_devices_metadata` (Read paired devices), `get_current_preset`, `get_favorite_sleep_number`, `get_footwarming_presence`, `get_footwarming_settings`, `get_fuzion_remote_mac_addresses` (Read paired remotes), `get_manifest_name` (Read software manifest), `get_responsive_air_enabled_status`, `get_simple_diagnostic_run_results` (Read bed diagnostic results), `get_sleep_number_controls` (Read Sleep Number settings), `get_sleepiq_privacy_state`, `get_system_configuration` (Read bed features), `get_system_settings_applied_status` (Read installation status), `get_target_preset_with_timer`, `get_temperature_program_info`, `get_temperature_program_settings`, `get_temperature_programs`, `get_underbed_light_auto_mode_status`, `get_underbed_light_settings`, `gets_actuator_homing_state` (Read calibration status), `halt_all_actuators`, `head_tilt`, `interrupt_sleep_number_adjustment`, `kid_outlet`, `kid_outlet_status`, `light_intensity`, `massage`, `massage_status`, `mcr_status` (Read bed status), `migrate_routines_to_temperature_programs` (Convert temperature schedules), `outlet`, `outlet_status`, `pinch_status` (Read obstruction status), `position`, `preset_reset`, `preset_save`, `preset_timer`, `reset_articulation_presets` (Reset saved positions), `responsive_air`, `responsive_air_status`, `routine_migration_status` (Read schedule conversion status), `run_diagnostics` (Run bed diagnostics), `sense_and_do`, `sense_and_do_status`, `set_actuator_target_position`, `set_actuator_target_position_with_timer`, `set_articulation_preset_settings`, `set_bed_presence`, `set_favorite_sleep_number`, `set_footwarming_settings`, `set_responsive_air_enabled_status`, `set_sleepiq_privacy_state`, `set_target_preset_with_timer`, `set_target_preset_without_timer`, `set_temperature_program`, `set_underbed_light_auto_mode`, `set_underbed_light_settings`, `software_versions` (Read software versions), `start_sleep_number_adjustment`, `stop`, `underbed_auto`, `underbed_auto_status` or `underbed_intensity` (Set under-bed light brightness). |
| `parameters` | Parameters | The command's own options, as listed in the Sleep Number guide. Unknown options and values are refused, and a side given here must match the selected side. |

See the [Sleep Number command guide](beds/sleep-number-services.md) for the
supported commands and parameter values. Use **Set bed clock**
([`sync_clock`](#sync_clock)) for the clock, and the diagnostic **Calibrate bed
position** and **Restart bed** buttons for homing and restarting.

## SleepEvolution and W.Silver Products 3.x

<a id="richmat_legacy"></a>
**`richmat_legacy`**: Run a control from the selected app and name prefix, as a press or a save.

| Field | Name | Meaning |
|-------|------|---------|
| `control` | Control | Name of a control on your bed's remote, as listed in the Richmat guide. |
| `operation` | Operation | Press runs the control as the app's button does, so pressing a preset longer than the app's save time also saves it. Save runs only the save step. One of `gesture` (Press) or `program` (Save). |
| `duration_ms` | Press length | Milliseconds, 1 to 60000. Applies to a press only. |

### SleepEvolution and W.Silver Products 3.x controls

`adjustable_bed.richmat_legacy` runs a `control` of your bed's remote. The
control names depend on the app and the start of the bed's Bluetooth name, as
the [Richmat guide](beds/richmat.md#sleepevolution--wsilver-products-3x) lists.

| Field | What it does |
|---|---|
| `operation: gesture` (default) | Presses the control as the app's button does. Pressing a preset longer than the app's save time also saves it |
| `duration_ms` | How long the press lasts, 1 to 60000 ms, default 1000 |
| `operation: program` | Only for a control that can save. Saves, then releases; `duration_ms` is not used |

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
memory numbers differ by profile, so the general memory actions are not
available. `hold_control` keeps the same difference between recall and save.
Renewable holds work only for movement, not for saving, timers or massage.

A bed whose two sides share one receiver cannot be controlled by side, and a
combined bed that connects to one side at a time cannot hold both sides at
once. Not yet confirmed on a real bed.

## SleepFunction

<a id="sleepfunction_settings"></a>
**`sleepfunction_settings`**: Sets the head fan, foot fan or aroma of a SleepFunction bed. The app sends no foot fan time, so the bed keeps its own.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Setting | What to set. One of `head_fan`, `foot_fan` or `aroma`. |
| `hours` | Fan duration | Required for Head fan and Foot fan: hours, 0 to 6. |
| `speed` | Fan speed | Required for Head fan and Foot fan: speed in percent, 0 to 100 in steps of 20. |
| `mode_2_minutes` | Aroma mode 2 duration | Required for Aroma: minutes, 1 to 60. |
| `mode_3_minutes` | Aroma mode 3 duration | Required for Aroma: minutes, 1 to 60. |
| `pause_hours` | Aroma pause | Required for Aroma: hours, 1 to 12. |

Aroma needs the bed to report it on the current connection. The foot fan speed
is sent twice, as the app does. See the
[SleepFunction guide](beds/richmat.md#sleepfunction-bed-control).

## Sleeptracker

<a id="sleeptracker_climate"></a>
**`sleeptracker_climate`**: Set the left, right or both fan modes and levels. Level 0 stops the selected fans. Heat runs for one hour and cool for ten hours. The bed does not report the time left.

| Field | Name | Meaning |
|-------|------|---------|
| `fan_side` | Fan zone | Which fans to set: left, right or both. Default both. One of `both`, `left` or `right`. |
| `mode` | Mode | Heat or cool. One of `heat` or `cool`. |
| `level` | Level | Fan level, 1 to 3. 0 stops the selected fans. |
| `constant` | Constant level | Keep the level constant. Turn off to follow the bed's curve instead. Default on. |

<a id="sleeptracker_massage"></a>
**`sleeptracker_massage`**: Steps a massage zone or pattern, picks a vibration speed, or stops the massage.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Massage step | Step the head or foot massage or the pattern, pick a vibration speed, or stop the massage. One of `head`, `foot` (Feet), `pattern`, `28hz` (28 Hz vibration), `40hz` (40 Hz vibration) or `off`. |

<a id="sleeptracker_preset"></a>
**`sleeptracker_preset`**: Moves to or saves a preset. The presets depend on the bed.

| Field | Name | Meaning |
|-------|------|---------|
| `preset` | Preset | The preset to move to or save. Only your bed's presets work. One of `all_flat` (Flat), `zero_g` (Zero gravity), `anti_snore` (Anti-snore), `user_favorite` (Favorite), `tv_pc` (TV and computer) or `favorite_2`. |
| `save` | Save current position | Save where the bed is now to the preset instead of moving to it. Default off. |

<a id="sleeptracker_relaxation"></a>
**`sleeptracker_relaxation`**: Starts the wind-down routine or the bed's relaxation movement.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Routine | Which wind-down routine or light animation to start. One of `wind_down_1`, `wind_down_2` or `local_animation` (Light animation). |

<a id="sleeptracker_wave"></a>
**`sleeptracker_wave`**: Starts a wave massage at the chosen speed and for the chosen time. Use Stop massage to end it early.

| Field | Name | Meaning |
|-------|------|---------|
| `frequency` | Frequency (Hz) | Massage speed in Hz. One of `28` (28 Hz), `40` (40 Hz), `52` (52 Hz), `68` (68 Hz) or `88` (88 Hz). |
| `minutes` | Duration (minutes) | How long the massage runs, 5 to 105 minutes in steps of 5. Default 30. |

### Sleeptracker Smart Bed


These actions need a bed set up with the [Sleeptracker processor](beds/sleeptracker.md);
beds set up as Adjustable Lite cannot use them. `fan_side` picks the
ActiveBreeze fans, separately from the combined bed's `side`.

| Action | Fields besides `device_id` | Notes |
|--------|---------------------------|----------|
| `sleeptracker_preset` | `preset`; optional `save: false` | Moves to `all_flat`, `zero_g`, `anti_snore`, `user_favorite`, `tv_pc` or `favorite_2`, as your layout has them. `save: true` saves a preset that can be saved; Flat cannot. Some processor types cannot save |
| `sleeptracker_climate` | `mode: heat` or `cool`, `level: 0` to `3`; optional `fan_side: both`, `constant: true` | ActiveBreeze only. Level 0 turns the selected fan off. Heat runs for one hour and cool for ten hours; you cannot change these times |
| `sleeptracker_wave` | `frequency`; optional `minutes: 30` | Premium layouts: 28, 40, 52, 68 or 88 Hz, 5 to 105 minutes in steps of five |
| `sleeptracker_massage` | `action` | `head`, `foot`, `pattern`, `28hz`, `40hz` or `off`, as your layout has them (`28Hz` and `40Hz` still work). `off` stops the massage |
| `sleeptracker_relaxation` | `action` | Premium layouts: `wind_down_1`, `wind_down_2` or `local_animation` |

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
wind-down. Use `stop_all` to stop movement and the light animation. Whether the
wave minutes and sides match the app is not yet confirmed on a real bed. The
climate timers show what was sent; the bed does not report the time left.

## Snore Monitor

<a id="onlysnore_set_alarm"></a>
**`onlysnore_set_alarm`**: Set or turn off one of the bed's own alarms.

| Field | Name | Meaning |
|-------|------|---------|
| `slot` | Alarm slot | 1, or 1 to 3 when the bed reports three alarms. |
| `enabled` | Enabled | Turn the alarm on or off. |
| `time` | Time | Alarm time, to the minute. |
| `weekdays` | Repeat on | Leave empty for a one-time alarm. Any of `monday`, `tuesday`, `wednesday`, `thursday`, `friday`, `saturday` or `sunday`. |
| `soft_wake` | Soft wake | Only when the bed reports three alarms. |

Snore Monitor beds keep their own alarm action instead of
[`set_alarm`](#set_alarm): what the app's five alarm actions do is not known,
so they cannot be offered as wake actions. On a combined pair, both beds are
prepared and checked before either changes. See the
[Snore Monitor guide](beds/onlysnore.md#settings-and-alarms) for how one-time
alarms use the weekday.

## Solace

<a id="solace_audio"></a>
**`solace_audio`**: Chooses or previews a MotionFlex music track, reads the volume, or sets it.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | Choose a track, preview one, read the current settings, or set the volume. One of `select` (Select track), `preview` (Preview track), `query` (Read current settings) or `set_volume` (Volume). |
| `track` | Track | Required for Select track and Preview track: track 1 to 5. |
| `volume` | Volume | Required for Volume: volume 1 to 5. |

## SonicSleep

<a id="sonicsleep"></a>
**`sonicsleep`**: Read the alarms, create or edit an alarm, turn an alarm on or off without changing it, delete an alarm, or read the bed's link name.

| Field | Name | Meaning |
|-------|------|---------|
| `operation` | Operation | What to read or change. Read the alarms first: editing, turning on or off and deleting need an alarm the bed reported. One of `list` (Read alarms), `new` (New alarm), `edit` (Edit alarm), `toggle` (Turn alarm on or off), `delete` (Delete alarm) or `link_name` (Read link name). |
| `alarm_id` | Alarm number | The alarm to edit, turn on or off, or delete, as the bed reported it. New alarms get their own number. |
| `hour` | Hour | For New alarm and Edit alarm: hour, 0 to 23. Default 6. |
| `minute` | Minute | For New alarm and Edit alarm: minute, 0 to 59. Default 30. |
| `mode` | Alarm position | For New alarm and Edit alarm: the position the bed moves to. Default zero gravity. One of `zero_gravity`, `lounge`, `tv`, `anti_snore` (Anti-snore), `memory_1` or `memory_2`. |
| `weekdays` | Weekdays | Leave empty for a one-time alarm; select all seven for every day. Any of `0` (Monday), `1` (Tuesday), `2` (Wednesday), `3` (Thursday), `4` (Friday), `5` (Saturday) or `6` (Sunday). |
| `enabled` | Enabled | Whether the alarm is on. Default on. |

### SonicSleep bed settings


`adjustable_bed.sonicsleep` reads the alarms (`list`), adds (`new`), edits
(`edit`), turns on or off (`toggle`) or deletes (`delete`) one, or reads the
link name (`link_name`); set the clock with [`sync_clock`](#sync_clock). An alarm
takes `hour`, `minute`, `mode`, `weekdays` (0 Monday to 6 Sunday) and `enabled`.
Edit, turn on or off and delete need the `alarm_id` the bed reported; turning on
or off changes nothing else. Read the alarms first on the current connection; if
the list changed meanwhile, nothing is sent. A new alarm needs the bed to report
its alarm list first. See the [SonicSleep guide](beds/richmat.md#sonicsleep).

## Somos

<a id="somos_action"></a>
**`somos_action`**: Press one of the selected Somos product's buttons. Every bed is checked before any is changed.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | Which button to press, or ask the bed for its status. Availability depends on the product. One of `flat`, `zero_g` (Zero gravity), `anti_snore` (Anti-snore), `memory_1`, `memory_2`, `memory_3`, `head_massage`, `foot_massage`, `massage_timer_cycle` (Cycle massage timer), `light` or `status_query` (Read status). |

Massage and light actions press the app's button; the bed does not report the
result. Use `hold_control`, `timed_move` and `stop_all` for movement. Signature
Split Head and Ultra Split Head lifts are `axis_1` to `axis_3`. See
[Somos](beds/keeson.md#somos--somosbeds).

## Superior Sleep

<a id="superior_sleep_speech"></a>
**`superior_sleep_speech`**: Sends one bed control: move a motor, move to a preset, stop, turn massage or under-bed motion activation on or off, or toggle the under-bed light. Motor controls run for the duration.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Control | The control to send. One of `head_up`, `head_down`, `foot_up`, `foot_down`, `back_up`, `back_down`, `lumbar_up`, `lumbar_down`, `speech_stop` (Stop), `lounge`, `zero_g` (Zero gravity), `anti_snore` (Anti-snore), `flat`, `memory_1`, `memory_2`, `massage_on`, `massage_off`, `light` (Toggle under-bed light), `motion_on` (Under-bed motion activation on) or `motion_off` (Under-bed motion activation off). |
| `duration_ms` | Motor duration | How long a motor control runs, 1 to 60000 milliseconds. Default 1000. Other controls keep their own timing. |

Preset, light and massage controls keep their own fixed timing. A motor
control runs for `duration_ms`. Under-bed motion activation on and off run for five seconds. The
massage adjustment buttons are not offered here; use the bed's buttons, and
[`hold_control`](#hold_control) for held buttons.

## SUTA Smart Home

<a id="suta"></a>
**`suta`**: Run one control from the bed's SUTA layout, which its Bluetooth name decides. Set alarms with Set alarm and the clock with Set bed clock.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Command | Command key from the SUTA guide, such as both_tv, massage_timer_10 or temperature_setpoint. |
| `suffix` | Step | Two-digit step for massage, massage level or fan commands, such as 00 or 20. |
| `logical_side` | Mattress side | For mattress and heating commands that target one side. One of `left` or `right`. |
| `value` | Value | Needed when a mattress or heating command offers several values. |

### SUTA Smart Home commands


`adjustable_bed.suta` runs the commands of your bed's layout, which its
Bluetooth name decides. Some commands also take a `suffix`, or `logical_side`
and `value`. `snore_cycle` runs the anti-snore movement and then moves the bed
flat; it does not listen for snoring. Alarms use [`set_alarm`](#set_alarm). The
[SUTA guide](beds/suta.md) lists the commands, their values and what each needs
first. The newer controls are not yet confirmed on a real bed.

## Starcode

<a id="starcode_move_lifts"></a>
**`starcode_move_lifts`**: Moves the lifts set up on one main bed. Flat lowers the main bed first and the lifts a moment later; Stop stops them all.

| Field | Name | Meaning |
|-------|------|---------|
| `action` | Action | Raise or lower the lifts, flatten the bed and its lifts, or stop. One of `up`, `down`, `flat` or `stop`. |

### `starcode_move_lifts`


Moves the lifts set up on an AdjustableM5X5 or Adjustable Comfort M1X12 main
bed. AdjustableM5X5 takes up to three lifts; M1X12 takes up to two ELEVATE lifts
set up as M1X12. Choose the main bed and `action`: `up`, `down`, `flat` or
`stop`. Moving stops the main bed first. `flat` moves the main bed flat, waits
1.6 seconds, then moves the lifts flat; Stop, a reload or a changed selection
cancels the wait. If one lift fails, all of them stop. Light, massage and saving
apply to each bed on its own.

```yaml
action: adjustable_bed.starcode_move_lifts
data:
  device_id: YOUR_MAIN_DEVICE_ID
  action: flat
```

The main bed also has Ascent/TV, Zero Gravity, Anti-Snore, Lounge, two memory
buttons, three save buttons and reset. Saving is sent several times; the bed
does not confirm that it kept the setting. The light color and brightness are
select and number entities. The alarm, sound, sonic and kneading readings can
only be read.

## Svane

<a id="svane_release_axis"></a>
**`svane_release_axis`**: Stop one motor while the other keeps moving.

| Field | Name | Meaning |
|-------|------|---------|
| `motor` | Motor | The motor to stop: head or feet. One of `head` or `feet`. |

### Svane Remote held controls


[`hold_control`](#hold_control) holds a Svane head or feet motor, or both, for
`duration` seconds (0.1 to 60). Feet-only controls and some combinations need
more than 0.1 seconds, because the feet start a moment later; shorter requests
are refused before anything moves. If the time runs out before the feet start,
the action fails and stops what started. `light_adjust` steps the lamp
brightness up and down, as holding the app's lamp button does.

`svane_release_axis` stops the head or the feet during that hold while the other
keeps moving; releasing the hold stops both. The [Svane guide](beds/svane.md)
describes the bed's other buttons and entities.

## Symphony

<a id="symphony_anti_snore"></a>
**`symphony_anti_snore`**: Turns anti-snore on or off for the head or the elevation, or runs a demonstration. Some beds take strengths 1, 3 and 6; others take 1, 2 and 3.

| Field | Name | Meaning |
|-------|------|---------|
| `enabled` | Enabled | Turn anti-snore on or off. |
| `axis` | Moves | Which part of the bed anti-snore moves: the head or the elevation. Default head. One of `head` or `elevation`. |
| `strength` | Strength | Strength level. Some beds take 1, 3 and 6 (low, medium, high); others take 1, 2 and 3. A level your bed does not take is refused. Default 1. One of `1` (Low), `2` (Level 2), `3` (Level 3: medium or high, depending on the bed) or `6` (High). |
| `demo` | Run demonstration | Run the anti-snore movement once to show it. Default off. |

<a id="symphony_set_light"></a>
**`symphony_set_light`**: Sets the light color and brightness together. ES700 and SS800 only.

| Field | Name | Meaning |
|-------|------|---------|
| `color` | Color (1 to 7) | Light color, numbered 1 to 7 as in the app. |
| `brightness` | Brightness (20 to 80) | Light brightness, 20 to 80. |

### Symphony Sleep Sense


The [Symphony guide](beds/okin-soundwave.md#symphony-sleep-sense) describes
these actions; alarms use [`set_alarm`](#set_alarm). On split beds the other
side's alarm is read first and kept as it is; split SoundWave beds cannot give
both sides the same alarm time. Combined beds that connect to one side at a time
offer renewable holds on Left or Right, while timed Both moves still work. The
motor covers support renewable holds through `timed_move` and `hold_control`;
presets run once.

