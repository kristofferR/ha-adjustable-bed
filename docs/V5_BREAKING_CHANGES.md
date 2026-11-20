# v5 Breaking Changes

This page is for anyone upgrading from 4.x (4.4.2 or earlier) to v5. Read it
top to bottom once: each change is described once, as v5 is now compared with
4.x. If you ran a v5 beta, also read [If you ran a v5 beta](#if-you-ran-a-v5-beta).
Changes between betas are in each beta's
[release notes](https://github.com/kristofferR/ha-adjustable-bed/releases).

> [!CAUTION]
> **Take a Home Assistant backup before you install v5.** v5 migrates every
> Adjustable Bed entry to a new format that 4.x cannot load. Restoring a
> backup taken before the upgrade is the only way back to 4.x. See
> [Rollback](#rollback).

## Contents

- [Before you upgrade](#before-you-upgrade)
- [After you upgrade, check these](#after-you-upgrade-check-these)
- [Settings and setup](#settings-and-setup)
- [Entities](#entities)
- [Actions and automations](#actions-and-automations)
- [Dashboard card](#dashboard-card)
- [Behavior](#behavior)
- [If you ran a v5 beta](#if-you-ran-a-v5-beta)
- [Rollback](#rollback)
- [Appendix A: removed and replaced entities by bed](#appendix-a-removed-and-replaced-entities-by-bed)
- [Appendix B: setup families](#appendix-b-setup-families)
- [Appendix C: moved guides](#appendix-c-moved-guides)

## Before you upgrade

**v5 requires Home Assistant 2026.11.0 or newer** (4.x needs 2026.9.0).

1. Update Home Assistant to 2026.11.0 or newer and check that it runs.
2. Create a full backup under **Settings > System > Backups**. Keep it until
   you have decided to stay on v5.
3. Note the integration version you run now.
4. Under **Settings > Marketplace**, open **Adjustable Bed**. In its three-dots
   menu, choose **Include pre-releases** and confirm. The beta then shows as an
   update under **Settings > Updates**. To pick one beta instead, choose
   **Install another version** in the same menu and select the `v5.0.0bN`
   version.
5. Install the update, then restart Home Assistant and reload the dashboard
   page.

To stop receiving betas, choose **Exclude pre-releases** in the same menu. An
installed beta stays until a newer stable version is out.

**Installed through HACS?** Home Assistant 2026.11 replaces HACS with the
Marketplace and moves what HACS installed into it, so follow the steps above
once Home Assistant runs 2026.11.

## After you upgrade, check these

1. **Repairs.** Open **Settings > System > Repairs**. When an entity changed
   type and an automation or script still references the old entity, the bed
   gets a repair that lists them. Templates and dashboards are not checked,
   so look through those yourself. Some beds get one question about the app
   they use.
2. **Alarm automations.** The per-bed alarm actions are one action,
   [`adjustable_bed.set_alarm`](SERVICES.md#set_alarm), with new field names.
   See [Actions and automations](#actions-and-automations).
3. **Other renamed or removed actions.** `linak_rename`, `logicdata_rename`,
   `jiecang_rename`, `leggett_hold_control`, `malouf_sync_clock`,
   `motion_bed_clock` and `reverie_test` are gone, and a few actions lost
   fields.
4. **Under-bed lights are `light` entities.** An on/off under-bed light that
   was `switch.<bed>_under_bed_lights` is now `light.<bed>_under_bed_lights`
   on every bed except Octo. Automations that call `switch.turn_on` or
   `switch.turn_off` on it must use `light.turn_on` or `light.turn_off`.
5. **Other entity changes.** On/off button pairs became switches, fixed-time
   timer buttons became one timer select, per-bed clock buttons are gone and
   entities that only mirrored the phone app's internals are removed.
   [Appendix A](#appendix-a-removed-and-replaced-entities-by-bed) lists them
   by bed.
6. **Connection settings.** Two disconnect settings became one **Bluetooth
   connection** setting, and two settings were removed. Your saved choices are
   migrated. See [Settings and setup](#settings-and-setup).
7. **Changing the app, model or remote** is done in **Reconfigure**, not
   **Configure**.
8. **Discovery toggle.** "Stop discovering new Bluetooth devices" moved from
   each bed's Configure to **Add Integration > Adjustable Bed > Find new beds
   automatically**.

## Settings and setup

Your saved settings are migrated on the first start. Diagnostics record what
the migration changed, under `profile_migration`.

| 4.x setting | v5 |
|-------------|----|
| **Position update mode** (`position_mode`) | Removed. When a command asks for a position read afterwards, it happens as with the default "Speed": in the background while the link stays open, and before the link is released with **Release right after each command**. No read is made when **Read bed position** is off or another command is waiting |
| **Connection profile** (`connection_profile`) | Removed. Every bed uses the former "Reliable" timing: by default a 25 s connect timeout (shorter on a few beds whose app uses one), 3 and 6 s backoff and a 1 s pause after connecting |
| **Disconnect after each command** and **Idle disconnect timeout** (including its `0`, "keep connected") | One **Bluetooth connection** setting: **Release right after each command** (was Disconnect after each command on), **Stay connected for a while** with **Seconds to stay connected** (was off, with its timeout), or **Always stay connected** (was a timeout of `0` with Disconnect after each command off). Hidden for beds that always keep their link. What changed in how a dropped link is handled is under [Connection](#connection) |
| LP Comfort Connect (Leggett & Platt Gen2, and Leggett & Platt on Automatic) kept its link permanently | Follows **Bluetooth connection** and stays connected for a while by default. If a reconnect stalls, it keeps the link until you disconnect it or Home Assistant restarts. Choose **Always stay connected** for the old behavior |
| **Disable angle sensing** | **Read bed position**, on by default and shown only for beds that report a position. A saved choice equal to the bed's default is dropped, so the bed's default applies |
| **Motor pulse count** and **Motor pulse delay (ms)** | **Movement per tap** (the pulse count, usually 1 to 100; a few beds allow more), hidden for beds that never repeat a tap. The delay is no longer shown; each bed uses its own, and a saved delay still applies |
| **Stop discovering new Bluetooth devices**, in each bed's Configure | **Add Integration > Adjustable Bed > Find new beds automatically** |
| **Bed type** and **Protocol variant** in Configure | **Reconfigure**, for every bed. The protocol variant is now called **Bed model or remote** |
| **Has massage feature**, maximum angles and a motor count with one choice, shown for beds that ignore them | Hidden |
| A bed added through **Pick any Bluetooth device** saved the scanner that found it as its adapter | Saves **Automatic**, like a discovered bed |
| A combined bed's saved pair connection mode (`pair_connection_mode`) | Removed. A combined bed with two Bluetooth addresses starts with both links and switches between the two beds one at a time only when the adapter cannot hold both |

Three layouts with no massage showed massage buttons in 4.x when Massage was
on. Pressing one raised an error, except FurniMove's **Massage: Off**, which
sent nothing ([#787](https://github.com/kristofferR/ha-adjustable-bed/issues/787)).
The migration turns Massage off for these layouts and deletes their massage
buttons:

| Layout | Removed buttons |
|--------|-----------------|
| FurniMove, a handset without massage rows | **Massage: Off**, **Toggle**, **Intensity Up**, **Intensity Down**, **Head Toggle**, **Head Up**, **Head Down**, **Foot Toggle**, **Foot Up**, **Foot Down** |
| Comfort Enhancements MC3 | **Massage: Off**, **Head Toggle**, **Foot Toggle**, **Mode** |
| Sleepy's Elite app, a control box other than BOX25 | **Massage: Off**, **Toggle** |

Every other layout keeps its massage controls, including a FurniMove handset
with massage rows, BOX25 and the other Comfort Enhancements layouts.

The classic Richmat apps (Avocado Eco Base, CoasterSleep, Forty Winks,
Milemont and Superior) keep their entity IDs and history, but the attributes of
their status sensor are renamed from `cluster018_...` to `richmat_classic_...`,
for example `richmat_classic_layout`. Update templates that read them.
`hold_control` still accepts the old `cluster018_<node>` control names.

Every other saved setting, bed type and ID loads unchanged.

### Setup, Configure and Reconfigure

- **Setup starts from the app or remote** that controls the bed. Choose **Set
  up by app or remote** or **Pick any Bluetooth device**, then search for the
  app. Many brands have one row that asks which app, remote or control box runs
  the bed; [Appendix B](#appendix-b-setup-families) lists them. Long lists of
  models and remotes are searchable. The bed's own settings come last. Rows
  that left the list keep their bed type and ID, so saved entries load
  unchanged.
- **One wording.** Setup, Configure and Repairs use the same plain labels for
  the same field. The protocol variant is **Bed model or remote**, every
  automatic choice reads **Automatic (recommended)**, the keep choice in
  reviews and repairs reads **Keep the current setup**, and the Diagnostic row is **Unsupported bed
  (diagnostics only)**. The Sleeptracker foundation size is no longer asked;
  it never changed a command. Saved values are unchanged.
- **Brand list.** The Okin receiver rows are one **Okin (other receivers)**
  row, which asks which receiver the bed has. The routes keep their IDs.
- **Reconfigure changes the app, model or remote**, for every bed. Open it from
  the entry's three-dots menu. It asks the same question as setup, shows the
  controls that are added, removed or change meaning, names the automations
  that use a removed control, and offers **Apply this change** or **Keep
  the current setup**. **Configure** keeps the everyday settings and no longer
  changes the bed type, app or route. See
  [Changing the app or layout](CONFIGURATION.md#changing-the-bed-type-app-or-layout-of-an-existing-bed).
- **One app review after the upgrade.** Entries on the generic Solace
  (Automatic), Keeson (Automatic, Base or Sino) and Richmat routes get one
  repair that lists the apps added for that route since 4.x. Choose your app,
  or keep the current setup. See
  [the app profiles repair](TROUBLESHOOTING.md#new-app-profiles-are-available-repair).
- **App suggestions in Repairs** open Reconfigure with the suggested app
  selected. A suggestion about a Richmat remote setting still opens Configure.
- **BedSmart / X-Series** is a new choice in the Richmat app question.
  Reconfigure a generic Richmat entry to select this app and its exact layout.
  Its layout controls, local selectors, optional features and shared alarm
  action are described in the [BedSmart guide](beds/richmat.md#bedsmart--x-series).
  Physical behavior still needs testing.
- **The Octo PIN repair is fixable.** It asks for the PIN, saves it on the
  bed (or the matching side of a combined bed) and reloads the entry.
- **Combined beds.** Dual Bed wording is now **Combine** and **Separate**.
  Repairs and Add Integration suggest **Combine two beds** only for two beds
  that use the same commands. **Separate into two beds** keeps the Bluetooth
  adapter and **Bluetooth connection** used while combined, and restores the
  bed type, app and side settings from before.
- **Discovery.** A name rule offers a bed automatically only when its
  Bluetooth name is spelled the way beds of its app advertise it. A bed that
  advertises an unusual spelling of an app-only name, for example lowercase
  `a0rm1234`, may no longer be offered; add it manually or pick the app in
  Reconfigure.

## Entities

- **Renamed entities keep their entity IDs, history and settings.** Only the
  shown name changes: brand and app names, notes such as "(app)" or "(raw)",
  protocol words and ALL-CAPS labels are gone. A name you set yourself stays.
- **Removed entities disappear by themselves** once the bed has connected.
  Remove them from dashboards, automations and scripts. Their values stay in
  diagnostics and support bundles.
- **Entities that change type keep your settings.** When an entity becomes
  another kind (a switch that became a light, a text sensor that became a
  binary sensor, a select that became a switch or number), the new entity
  takes the old object ID where it is free (`switch.bed_under_bed_lights`
  becomes `light.bed_under_bed_lights`) and the name, icon, area, labels,
  categories, aliases and disabled or hidden state you gave the old one. When
  an automation or script still references the old entity, a repair lists it;
  it is checked again after every restart and goes away once none does.
  Templates and dashboards are not checked. A per-bed massage or light timer
  select that became the shared one keeps its entity ID and only changes its options; its line is listed once
  and stays until you dismiss the repair.
- **Raw state sensors are disabled by default** on new installs, and so are
  app extras: music, fan, heating, aromatherapy, Bluetooth, reset,
  demonstration and similar buttons, and on the busiest beds their settings
  and alarm readings. Settings are configuration entities. Entities you
  already have keep their enabled state.
- **Refresh and query buttons are diagnostic** and disabled by default where
  the bed reports the value itself. So is the generic **Wake controller**
  button.
- **No device shows one name twice**, and a paired bed's Left, Right and Both
  entities are named from their devices, as Home Assistant 2026.11 does, so
  the card no longer shows doubled names such as "Bed Left Back".

### One shape per control

The same control now looks the same on every bed:

- **Under-bed lights.** Every on/off under-bed light is a `light` entity
  (**Under Bed Lights**), on every bed except Octo, whose light depends on its
  PIN session and its own light timer. A bed that cannot report the light's
  state shows it as assumed, as the switch did.
- **On and off pairs are switches.** A pair of on and off buttons, or a
  two-choice select, for one setting is one switch. A switch whose bed never
  reports the setting shows what was last sent, and separate on and off
  controls.
- **Timers are selects.** Where the bed can set a duration directly,
  fixed-time buttons ("Massage 20 minutes") and bed-specific timer selects
  became the shared **Massage: Timer** and **Light Timer** selects. A bed
  without an off command offers only its durations. A bed that can only step
  through its timers keeps one cycle button. The **Massage: Timer** select
  shows unknown until a timer is sent or reported.
- **Massage levels are numbers.** Where the bed has an intensity number, the up
  and down step buttons for the same zone are gone; beds that can only step
  keep the buttons. Where a bed has one button per massage level, those buttons
  became one intensity number per zone, offering only the levels the bed has.
- **Buttons from an app or remote layout show what they are.** Motor up and
  down buttons sit in the card's motor rows, presets and memories in their
  tiles, and massage and light controls in their sections. A preset, memory or
  massage step every bed has takes the shared name (**Zero Gravity**,
  **Memory 1**, **Massage: Head Up**); other buttons keep the app's label
  without internal identifiers ("MasFootAdd" is **Increase foot massage**,
  "Ubb" is **Under-bed light**). Where an app lists two controls under one
  label, the second is numbered (**Wave 2**). Empty app slots and buttons that
  sent the same command as another entity are gone.
- **Saves follow one rule.** A preset save sits with the presets, is a
  configuration entity named **Save …** and asks for confirmation in the
  dashboard card. A memory save is offered in the card's Set mode and no
  longer asks twice.
- **Sleep readings are dashboard entities.** Heart rate and breathing rate are
  numeric sensors (bpm and breaths/min where the bed's unit is known) with
  history graphs; a reading the bed does not have shows unknown instead of
  "--". In bed, snoring and body movement are binary sensors with the
  occupancy, sound and motion device classes. They are enabled, no longer under
  Diagnostic, and every bed uses the same names ("Left heart rate", "Right in
  bed"). Heart and breathing rate sensors keep their entity IDs. A reading the
  integration had created disabled is enabled once; one you disabled stays
  disabled. The DoubleSleep breathing rate's unit changes from brpm to
  breaths/min, and Home Assistant offers to update its statistics.
- **Sleep Number bed presence** is enabled by default and named **In bed**,
  **Left in bed** and **Right in bed**. It updates only while the bed is
  connected (see [Connection](#connection)).
- **Clocks are set by an action.** The per-bed **Sync clock** buttons are gone;
  the **Set bed clock** action ([`adjustable_bed.sync_clock`](SERVICES.md#sync_clock))
  sends the same commands.
- **New controls.** Keeson, Serta, Ergomotion and OKIN FFE beds have a **Stop
  All** button, sending the release key the remote sends when a button is let
  go (Adjustable Lite and the KSBT remotes have no such key and still have
  none). Logicdata beds show their two memory slots, recall and save. Sleep
  Number beds get **responsive air** switches per side and an **Automatic
  under-bed light** switch where the model has them, a **Privacy** switch on
  Fuzion beds, and **Head tilt**, **Power outlet** and **Automatic night
  light** switches on BAM/MCR beds that have them. Once a Fuzion bed's
  configuration has been read, it also gets diagnostic **Restart bed**,
  **Calibrate bed position** and **Reset saved positions** buttons (the last
  two only on beds that move), disabled by default; the dashboard card asks
  for confirmation before it presses them.

[Appendix A](#appendix-a-removed-and-replaced-entities-by-bed) lists the
removed and replaced entities by bed.

New in v5: estimated positions for beds without position feedback (see
[Estimated positions](ESTIMATED_POSITIONS.md)), and a `card_section` attribute
on every entity that tells the dashboard card where it belongs.

## Actions and automations

Update scripts and automations that call these actions. The
[Actions and Automations](SERVICES.md) guide describes every current action.

| 4.x action | Use now |
|------------|---------|
| `bf_cherish_set_alarm` | `set_alarm` |
| `comfort_enhancements_set_alarm` | `set_alarm` |
| `configure_alarm_schedule` | `set_alarm` |
| `eshine_set_alarm` | `set_alarm` |
| `glideaway_set_alarm` | `set_alarm` |
| `jiecang_set_alarm` | `set_alarm` |
| `leggett_alarm_timer` | `set_alarm` |
| `linak_set_alarm` | `set_alarm` |
| `logicdata_set_alarm` | `set_alarm` |
| `malouf_set_alarm` | `set_alarm` |
| `motion_bed_alarm` | `set_alarm` |
| `richmat_mh_alarm` | `set_alarm` |
| `richmat_mh_waist_alarm` | `set_alarm` |
| `rmcontrol_alarm` | `set_alarm` (setting the clock moved to `sync_clock`) |
| `simmons_set_alarm` | `set_alarm` |
| `solace_set_alarm` | `set_alarm` |
| `zseries_set_alarm` | `set_alarm` |
| `jiecang_rename`, `linak_rename`, `logicdata_rename` | `rename` |
| `leggett_hold_control` | `hold_control` |
| `malouf_sync_clock` | `sync_clock` |
| `motion_bed_clock` | `sync_clock` (sets the motor or thermal module clock to Home Assistant's time; on a hub, select the motor or heating module first. `timestamp` and `thermal` are gone) |
| `reverie_test` | Removed (it ran a factory bed test) |

Beds whose alarm is part of their own action, such as `richmat_classic`, keep
it there; the [`set_alarm` table](SERVICES.md#set_alarm) lists them.

`set_alarm` uses the same fields on every bed. What changed from the old alarm
actions:

- `weekdays` takes `monday` to `sunday` everywhere: no numbers,
  abbreviations or bitmasks. Where a bed offers them, "once" is an empty list
  and "daily" a full one.
- `wake_mode`, `preset`, `memory`, `mode` and `position` become `wake_action`,
  with shared names such as `zero_g`, `memory_1` and `none`.
- `head_level` and `foot_level` become `head_massage_level` and
  `foot_massage_level`; `intensity` becomes `massage_intensity`; `kind`
  becomes `massage_zone`; `alarm_id` becomes `slot`; `waist_side` becomes
  `mattress_side`; RMControl's `action` becomes `wake_action`; SIMMONS's
  `confirm_custom_mode` becomes `confirm_custom_position`.
- Which of once, weekly and daily a bed accepts depends on the bed: RMControl
  repeating products need at least one weekday. The
  [`set_alarm` table](SERVICES.md#set_alarm) lists each bed's options.
- Countdown alarms (Leggett & Platt, Linak, Richmat app, RMControl single
  alarms) take a clock `time`, and Home Assistant counts down to it.
  `minutes` and `seconds` are gone.
- Motion Bed: `hour` and `minute` become one `time`. The numeric `sound` and
  the `audio` switch become a named `sound`: `none` on every bed, `alarm` on
  beds without audio, or `music_1` to `music_5` on beds with audio. Leaving
  `sound` out now plays the alarm tone (or `music_1`), where 4.x stayed
  silent: set `sound: none` to keep an alarm silent. `repeat` is gone: any
  `weekdays` make the alarm repeat, so where `repeat` was `false`, leave
  `weekdays` out or pass an empty list.
- Keeson app layouts (`configure_alarm_schedule`): one `set_alarm` call sets
  one alarm. With `weekdays` it writes the weekly alarm, without them the
  one-time alarm. A call that wrote both tables becomes two calls; `weekly`,
  `one_time` and `dispatch` are gone.
- Turning an alarm off is `enabled: false`. On an RMControl repeating alarm it
  deletes the alarm; on the Keeson app layouts it clears both alarm tables.
- No longer offered: Linak snooze repeats (`recurrence_count`,
  `recurrence_minutes`) and per-step `actions` with `lifetime` and `pause` (a
  Linak alarm now runs the wake memory, a massage toggle and a light toggle, in
  that order, with the default timing); RMControl alarm query; Motion Bed split
  zero-gravity modes, the raw `switch` value and the `confirmed` flag (a
  Motion Bed alarm without a `wake_action` rings without moving the bed);
  Keeson app tables with more than one weekly and one one-time alarm. On the
  Richmat app beds added in the betas, `enabled: false` disables a calendar
  alarm slot instead of deleting it.

Other action changes:

- `gmmotor` no longer offers `operation: clock_sync`; use `sync_clock`. Its
  `repeat` and `status` fields are gone (repeating alarms send the app's
  defaults), and the sleep report's `part` and `report_type` take `left` or
  `right` and `day` or `month` instead of 1 and 2.
- `goodvibe` no longer offers `operation: sync`; use `sync_clock`.
- `furnimove_action` no longer takes `consumer`.
- `sleep_number_command` no longer offers `reboot_system`,
  `starts_actuator_homing`, `set_system_time`, the cooling and core-temperature
  module commands (`get_frosty_mode`, `set_frosty_mode`, `get_frosty_presence`,
  `get_heidi_mode`, `set_heidi_mode`, `get_heidi_presence`) or
  `get_system_status` (network and update status). Restarting and homing are
  buttons now (see **New controls** under [Entities](#entities)); **Restart
  bed** always restarts both components, so one component can no longer be
  restarted alone. Set the clock with `sync_clock`, which writes Home
  Assistant's current time and takes no `date_time`. Cooling and heating modes
  are the **Climate** entities and their duration the **Climate Timer**
  selects; module presence is detected automatically. `kid_outlet` and
  `kid_outlet_status` accept only `device: 0`. New
  commands: `reset_articulation_presets`, `run_diagnostics`, `bind_foundation`
  and `underbed_intensity`. See the
  [Sleep Number command guide](beds/sleep-number-services.md).
- `timed_move` and `hold_control` gain optional `hold_owner` and
  `hold_generation` fields for renewable holds. Calls without them work as
  before. See [Renewable holds](SERVICES.md#renewable-holds).
- `sync_clock` also sets the clock of SUTA Smart Home, OKIN SleepEase, Motion
  Bed, GM Control, Good Vibe Sleep and Sleep Number (Fuzion) beds, whose own actions or buttons no
  longer do. On a bed whose two sides share one receiver, it
  sets the clock once.
- Bed actions are named "Brand: what they do" in the action list, with
  "settings", "press button" or "run control" for the general ones. Action IDs
  are unchanged.
- New actions for [estimated positions](ESTIMATED_POSITIONS.md#actions)
  (`estimate_save_position`, `estimate_recall_position`,
  `estimate_set_reference`, `lower_to_flat` and others), useful only after you
  enable estimated positions.

### If you ran a v5 beta

Saatva app support is new in v5: select its Adjustable Base or Adjustable Base
Plus model and installation during setup. Existing 4.4.2 BedTech and Richmat
entries retain their own profiles. See [Saatva](beds/richmat.md#saatva).

These actions existed only in v5 betas and are gone. Older field names are not
accepted.

| Beta action | Use now |
|-------------|---------|
| `comfort_enhancement3_set_wakeup`, `comfort_enhancement3_delete_wakeup` | `set_alarm` |
| `comfortbase_set_alarm`, `jalon_bed_set_alarm`, `jalon_set_alarm` | `set_alarm` |
| `mline_set_alarm`, `n32_motion_bed_alarm`, `richmat_app_alarm`, `smart_sleep_set_alarm` | `set_alarm` |
| `symphony_sense_set_alarm`, `symphony_set_alarm`, `yamada_set_alarm` | `set_alarm` |
| `save_position`, `rename_position`, `update_position`, `delete_position` | `estimate_save_position`, `estimate_rename_position`, `estimate_update_position`, `estimate_delete_position` |
| `recall_position`, `set_position_reference` | `estimate_recall_position`, `estimate_set_reference` |
| `confirm_position_unchanged`, `mark_position_unknown` | `estimate_confirm_unchanged`, `estimate_mark_unknown` |

The Richmat sleep receiver (W.Silver Products, AMERICANSTAR, Bailey's Bed
Control and TX), added in beta 6, shows in bed and body movement as binary
sensors with the same object ID where it is free, and its
intervention selects are the **Left snore intervention** and **Right snore
intervention** switches.

Galaxy and MLILY (`operation: sync`) and SonicSleep (`operation: sync_clock`)
set their clock with `sync_clock` now, like Good Vibe Sleep. Beds added during
the betas changed their entities too (clock buttons, timer selects, switches
and sleep readings, as described under [Entities](#entities)); each beta's
release notes list them.

## Dashboard card

- Quick actions (`compact_actions`) are saved as entity IDs. Cards that list
  the old keys keep working, and the editor rewrites them to entity IDs the
  next time you edit the card, if every side keeps the same actions.
- Preset save buttons are never offered as quick actions, and they ask for
  confirmation in the card.
- A button that asks for confirmation is a plain tap: holding it never sends
  it. On the Sleepy's app this applies to **Program memory** and **Reset
  memory**, which 4.x repeated while held; a tap still runs the app's full
  press after you confirm.
- A split bed's side selector is named **Controlled side** on every bed and
  sits with the motor controls.
- A light whose state the bed does not report gets separate On and Off
  buttons.
- A bed with two controls for one place in the card, such as a massage timer
  button and a remaining-time sensor, shows both.
- New options, off by default: **Tap to start and stop movement**
  (`tap_to_move`), percentage and lumbar graphics, and opening the full card
  in a dialog from a compact card. A new `show_graphic_labels` option, on by
  default, can hide the labels under the bed graphic. See the
  [Dashboard Card guide](DASHBOARD_CARD.md).
- The card names entities the way Home Assistant 2026.11 does, so a renamed
  device updates its labels.

## Behavior

### Movement and Stop

- **Holding a control.** On beds whose app holds a key down until you let go,
  the dashboard card keeps the motor moving while you hold the control and
  stops it when you let go, through a renewable hold. Other beds keep the short
  pulses they used in 4.x. A hold ends after at most 30 seconds. See
  [Renewable holds](SERVICES.md#renewable-holds) and the
  [command lifecycle](COMMAND_LIFECYCLE.md#renewable-hold-leases).
- **Two motors at once.** On Leggett Okin Prodigy CE and U Series, Svane Remote
  and the Customatic Clarity, Jerome's and Remedy apps, `timed_move` calls on
  different motors run together. In 4.x the second move replaced the first. See
  the [merged stream](COMMAND_LIFECYCLE.md#merged-stream-for-concurrent-motors).
- **Stop is immediate.** A cover's Stop no longer waits behind a move on
  another motor of the same bed or side; that move ends first, then the Stop
  goes out. Where motors run together in one stream, a cover's Stop ends only
  its own motor. On Jiecang, Comfort Motion and Jensen LinOn beds, a Stop during a
  move reaches the bed at once instead of at the next repeat.
- **Stop wins while an action is still checking.** A Stop on any selected bed
  while `set_alarm`, `set_position` or `set_positions` is still connecting to
  or checking its beds ends the action: nothing is written or moved. In 4.x the
  first beds could still be written or moved afterwards. Customatic Z-Series,
  Symphony and Ultramatic alarms use their own checks instead.
- **Actions write only what they checked.** Right before each bed is written,
  `set_alarm` checks that the selection still resolves to the same beds and
  pairing, that a link it prepared for that bed is still the same one, and
  that the other prepared sides still waiting for their write are on the
  connections it checked; a combined bed's planned switch from one side to
  the other is allowed (again except Customatic Z-Series, Symphony and
  Ultramatic). `set_position` and `set_positions` plan each motor again on the
  connected bed; a plan that no longer matches the check stops with "The bed
  changed while the action was being checked. Try again.", and a motor or
  target the bed no longer accepts shows the bed's own reason. Either way
  nothing more is written; beds already written stay written. Preset, rename, clock and hold actions check the bed again
  when it connects and show its own reason if it no longer accepts the
  request.
- **Combined beds** connect and check both sides before an alarm is written to
  either. A failed alarm check no longer stops the other side.
- **Customatic covers** queue a second motor's move behind the first, as on
  other beds, instead of replacing it.
- **Leggett Okin Prodigy CE and U Series** send the release once after a
  `timed_move`, where 4.x sent it twice.

### Connection

- **Stay connected for a while** counts from the last command. In 4.x, a link
  the bed or adapter dropped was reconnected 5 s later with a new timeout each
  time, so a bed that drops idle links stayed connected and blocked its remote
  and app. Now a dropped link is reconnected at most once, and only before the
  time the last command opened runs out; it is released when that time ends.
  If the reconnected link drops too, or after that time, the next command
  reconnects. Choose **Always stay connected** if a bed must stay connected.
  With **Always stay connected** and **Release right after each command**, a
  dropped link reconnects on the next command by default, as before. Some
  beds reconnect on their own instead: OKIN RF eco BT, FurniMove, GM Control
  sleep modules and LP Comfort Connect while Home Assistant holds their link
  (FurniMove only after a stalled reconnect on an RF eco BT receiver made it
  hold the link), and Good Vibe and Hush sleep sensors while monitoring or
  live data is on.
- **Bed occupancy sensors** (Sleep Number) update only while the bed is
  connected. In 4.x their 30-second poll connected the bed and kept it
  connected; it no longer connects or extends **Seconds to stay connected**.
  Use **Always stay connected** for continuous occupancy.
- **Diagnostics** show the connection setting each bed and side actually uses,
  including the bed's default.
- **Support bundles** of beds that run their own write loops now record those
  commands, so they are larger.

### Shown state

- **Switches, lights, selects and numbers show only what reached the bed.**
  When Stop or a newer command cancels a command before anything was sent, the
  entity keeps its previous state instead of showing the requested one. When a
  command was cut off after part of it was sent, including when the bed itself
  ended it early, the entity shows unknown until the bed reports its state or
  the next command is sent. A toggle counts as sent once its first frame went
  out.
- A switch whose bed cannot run the command shows an error instead of doing
  nothing.

### Errors

- **Every error you see is a plain, translated message** that says what to do
  next, in actions, setup and repairs alike. Automations that matched old
  English error text must match the new text; the same conditions fail as
  before.
- **Combined beds.** When more than one side fails, the error names each side's
  reason. A side whose command fails and that also does not disconnect reports
  both.

## Rollback

> [!WARNING]
> **A Home Assistant backup taken before upgrading is the only way back to
> 4.x.** Installing 4.x over v5 leaves every Adjustable Bed entry failing to
> load. See [Going back to 4.x](TROUBLESHOOTING.md#going-back-to-4x).

Report beta problems in the pinned v5 beta feedback issue
([#914](https://github.com/kristofferR/ha-adjustable-bed/issues/914)), or open
a bug report. Include diagnostics or a
[support bundle](GETTING_HELP.md#generating-a-support-bundle) and the version.

## Appendix A: removed and replaced entities by bed

Beds that 4.x supported. Renamed entities are not listed: they keep their IDs.
Under-bed lights, which became `light` entities on every bed except Octo, are
described under [One shape per control](#one-shape-per-control).

| Bed or app | Removed | Replaced by |
|------------|---------|-------------|
| AdjustaMattress | Privacy-agreement select, reported alarm and strength sensors, sleeping, alarm, anti-snore and auxiliary status binary sensors, clock sync, alarm query and massage query buttons | Alarm commit and anti-snore selects and the sleep button: **Alarm**, **Intelligent anti-snore** and **Sleep mode** switches. Head, foot and wave selector selects: **Massage: Head Intensity**, **Massage: Foot Intensity** and **Massage: Wave Intensity** numbers (1-4). Timer 10, 20 and 30 buttons: **Massage: Timer** select |
| BedSense | Head and wave bar sensors, memory indicator refresh and background tap buttons, massage timer and light duration sensors | Memory recall buttons of slots 3 to 5: **TV**, **Zero Gravity** and **Anti-Snore** (**Flat** on layouts 6 and 8), which recall those slots; their saves stay. Massage timer and cancel buttons, light 10 min, 8 h and 10 h buttons: **Massage: Timer** and **Light Timer** selects |
| BedTech | | Massage 20 minutes button: **Massage: Timer** select |
| Casper Base, Hush Base | | "Memory position 1-3", "Save Memory position 1-3" and "Motor reset": **Memory 1-3**, **Save to Memory 1-3** and **Flat**, which send the same commands. Massage 10, 20 and 30 minute buttons: **Massage: Timer** select (durations only) |
| Comfort Enhancements | Cycle massage timer button (the timer select already sets it) | |
| Customatic Z-Series | | App "Toggle light": **Toggle Light** |
| DoubleSleep (OKIN SleepEase) | Four flag binary sensors, parser-error, privacy, massage running and sonic running sensors, "Sync clock" and "Refresh clock" buttons | Child lock select and privacy buttons: **Child lock** and **Privacy** switches. Massage and sonic on/off buttons: **Massage** and **Sonic massage** switches. The app's "Stop all" is **Stop movement** (**Stop All** stops the bed). Clock: the **Set bed clock** action |
| eShine (E6000) | | Massage 10, 20 and 30 minute buttons: **Massage: Timer** select, with Off |
| eShine OKIN | Alarm refresh and "Sync bed clock" buttons | Clock: the **Set bed clock** action |
| FSM Relax | 11 count, acknowledgement, calibration, information and raw motor sensors | |
| FurniMove | Action rows a standard entity already sends (Flat, ZeroGravity, Snore, TV, Memo1-4, MemoSave, UBL, Sync, ChildLock, SwitchToPH/PR), function-result sensor | |
| GM Control sleep module | Time and Query part buttons (the clock is set on every connection; the `gmmotor` action still queries the part) | Start and stop live data buttons: **Live sleep data** switch; new heart rate, breathing rate, in bed, snoring and body movement entities |
| Good Vibe Sleep | "No action", "Logo" and "… menu" buttons from empty app slots; "(long press)" buttons whose long press sends nothing of its own; a control the app lists twice | A preset's long press that sends its save: the **Save …** button. Massage 10, 20 and 30 minute buttons and the "Massage timer" select: **Massage: Timer** select (with Off where the app has a countdown off; the select keeps its entity ID). "Light duration (seconds)" select: **Light Timer** select (same entity ID). Sync on and Sync off buttons: **Synchronization** switch, disabled by default, on products that have both |
| Good Vibe, Casper and Hush sleep sensors | | In-bed, snoring and movement text sensors: **In bed**, **Snoring** and **Body movement** binary sensors, with the same object ID; heart and breathing rate sensors take the shared names and keep their IDs |
| Heal Every Night (OKIN apps) | | Installation and actuator direction selects: **Reversed installation**, **Reverse actuator 1** and **Reverse actuator 2** switches |
| HJBed | | Sync on and Sync off buttons: **Synchronization** switch, disabled by default, on products that have both |
| Keeson app layouts (TEMPUR AU, Tempur Curve, Ergomotion, Q-Plus, Serta MP Remote, Omazz, ROW Control, Ergo Slim) | | The app's Flat button: **Flat** |
| Limoss Remote | Repeated motor channel buttons, capability count, calibration reply and raw position sensors | Covers are named **Motor 1** to **Motor 4** |
| Motion Bed app | 83 state sensors (preset-selected flags, raw positions, calibration samples, day and month report arrays, module and pressure readings), alarm-sound preview buttons, massage timer and brightness sensors, five mirror binary sensors | Alarm, climate timer, fault and sleep report details: attributes of their sensors. Massage timer, light timer and brightness 0-10 buttons: **Massage: Timer** and **Light Timer** selects and the **Light brightness** number. Night light, smart sleep, module light, module massage, climate timer and adaptive air toggles or on/off pairs: switches |
| OKIN bedding apps (Jordan's Serenity and Tranquil, Customatic Z-Series) | Status, timer and save-event code sensors | |
| OKIN CST | | Memory recall buttons for slots a named preset recalls: **Zero Gravity**, **Incline**, **Reading** or **Lounge**; the slot's save stays |
| ORE comfort-bed apps (Avanti, Bedsense, Dynasty, MaxCoil Una), StarCode ABM5-4 | | Bed-specific massage timer select: **Massage: Timer** select (durations only; same entity ID) |
| Reverie, Reverie Nightstand, Pairlink, Jiecang app | Wave sensor, Pairlink massage mode and timer sensors (the select and number show them), head and foot massage up and down buttons where an intensity number exists | Pairlink massage rhythm select: **Massage rhythm** switch |
| RMControl | Protocol version, bed mode and last alarm record sensors | |
| Serta MP Remote | Memory request sensor | |
| SIMMONS | "Sync Clock" button | Clock: the **Set bed clock** action |
| Sleeptracker | Massage pattern and strength sensors (the selects show them) | |
| Sleepy's Elite app | All `field_0x..` sensors, voice STOP, voice brightness and voice position buttons, light on/off buttons (the light entity drives the light) | Motion sensor on/off buttons: **Motion sensor** switch. Massage timer code select and cycle massage timer button: **Massage: Timer** select (10, 20, 30 min; same entity ID). BOX25 Massage on and Massage off buttons: **Massage** switch. Axes 0, 1 and 2 are now **Head**, **Foot** and **Lumbar** |
| StarCode Adjustable Comfort M1X12 | Part 8 and Part 16 covers and buttons (still reachable through `hold_control`), Part 8/16/32 position sensors, MemoryType 8 recall, raw time and brightness sensors, motor-stopped, light-on and kneading-demo binary sensors | Parts 1, 2 and 4 are now **Head**, **Foot** and **Lumbar** |
| StarCode AdjustableM5X4 | 19 raw field sensors, selector sensors, wake, firmware-read and massage-release buttons | "App massage active" sensor: **Massage** binary sensor |
| StarCode AdjustableM5X5 | Raw time, brightness, RGB-mode and motor part 4-6 sensors, motor-stopped, light-on, firmware-read and kneading-demo binary sensors | |
| SUTA Smart Home | Controls the bed's model does not have, query buttons, the **Model** sensor, the "Sync clock" button | Lock and unlock: a **Lock** switch with a new entity ID. Head and foot massage off, 1, 2 and 3 buttons and Massage level 0 to 3 buttons: **Massage: Head Intensity**, **Massage: Foot Intensity** and **Massage: Intensity** numbers (0-3). MOON left and right massage strength 1, 2 and 3 buttons: **Left massage intensity** and **Right massage intensity** numbers (1-3). Clock: the **Set bed clock** action |
| Svane | Head, feet and position byte sensors | |
| V-MAT Basic | ED motor status binary sensor | |

**SUTA Smart Home** now offers the controls the SUTA app shows for your model,
which it reads from the bed's Bluetooth name (for example `SUTA-B202B`). 4.x
offered one generic set to every SUTA bed. If a control you used is missing,
check the exact Bluetooth name in **Configure**. Names shorter than nine
characters and drawer controllers get no bed controls.

## Appendix B: setup families

Many brands now share one setup row that asks which app, remote or control box
runs the bed. Rows that left the top-level list keep their bed type and ID.

| Family | What setup asks |
|--------|-----------------|
| Customatic, Jordan's | Customatic: Clarity, Jerome's C, Remedy, or Z-Series with its Z-230 or Z-280 model. Jordan's: Serenity or Tranquil |
| Jensen / Svane | The Jensen Adjustable Sleep app with a JMC400 or LinOn bed, or the Svane Remote app with a Svane Bed or a JMC400 bed |
| Jiecang | ERGOBALANCE (Dreamask), Dream Motion, Dream Motion HD, Comfort Motion, or a remote without an app |
| Keeson | The Keeson, Ergomotion, Serta Motion Perfect, Okin FFE and Cool Base rows share one question. Restonic remote A and B are one Restonic BT row that asks the remote style. The ORE apps and INNOVA ask for the app's 2M, 3M or 4M screen |
| Leggett & Platt | Prodigy CE, Prodigy 2, Prodigy 2L or U Series; LP Control with an LP BED receiver or an LP Comfort Connect base; the L&P Adjustable Base app with an MlRM base or a QRRM remote; or the L&P legacy app |
| Limoss | Limoss Remote, FSM Relax, Stawett and the older Limoss controls |
| LOGICDATA | SILVERmotion / SimplicityFrame, the MOTIONrelax apps or the Sleep Smart Air Mattress app. The Sleep Smart pump is its own device |
| Malouf / Lucid | The Malouf Base or Lucid Base app, or a receiver. An app asks its model and whether the bed is the primary one |
| Okin | The FurniMove / OKIN Smart Remote app, an Okimat or OKIN handset code, a DOT remote, the RF ECO BT stair lift, and the Okin apps. Each Okin CST app, such as Resident Adjustable Bed, is its own row. **Okin (other receivers)** in the brand list asks which receiver the bed has, named by the beds and remotes it came with |
| Remacro | Slumberland, The Brick or Jerome's, using the model the bed advertises |
| Reverie | The Nightstand app or the Protocol 110 or 108 receiver, then the model. Pairlink keeps its own row |
| Richmat | RMControl, the Richmat MH apps, the classic apps, SleepFunction, SVEN & SON and Richmat remotes. Each app is also its own searchable row |
| Sleep Number | Fuzion (Climate 360, FlexFit) or BAM/MCR (i8, 360 FlexFit 2). A Fuzion bed then asks its side |
| Sleepy's Elite | The MFRM Sleepy's Elite app, or the BOX15, BOX24 or BOX25 receiver |
| Solace | HomeKobo, Sealy MotionFlex or Sweet Night; Woosa Sleep; Motion Bed; or BedSense |
| StarCode | AdjustableM5X4, AdjustableM5X5 or Adjustable Comfort M1X12 |

Other setup changes:

- An app's own settings are questions on one step instead of a step per app.
  AdjustableM5X4, AdjustableM5X5, Adjustable Comfort M1X12, Ergomotion 4.0
  custom products and FSM Relax memory names keep their own step.
- Motor count and the repeat delay are no longer asked for the Jiecang, Malouf
  and LOGICDATA apps, whose model sets them.
- Good Vibe Sleep's product rows and HJBed's models are one row each, which
  asks the product in a searchable list. The Casper Base and Comfort
  Enhancements apps have one row each.

## Appendix C: moved guides

Per-bed guides that share commands were folded into one guide per family, with
one section per app. Old links to these files on the `v5` branch return 404.

| Old guide | New section |
|-----------|-------------|
| `beds/adjustable-lumbar.md` | [Okin N-frame: Adjustable bed (Lumbar)](beds/okin-nframe.md#adjustable-bed-lumbar) |
| `beds/adjustamattress.md` | [Keeson: AdjustaMattress](beds/keeson.md#adjustamattress) |
| `beds/bedsense.md` | [FFFF frame: BedSense](beds/ff_frame.md#bedsense) |
| `beds/bedtech.md` | [Richmat: BedTech](beds/richmat.md#bedtech) |
| `beds/bf-cherish.md` | [Keeson: BF and Cherish](beds/keeson.md#bf-and-cherish) |
| `beds/comfort-enhancements.md` | [Keeson: Comfort Enhancements](beds/keeson.md#comfort-enhancements) |
| `beds/comfort-motion.md` | [Jiecang: Comfort Motion app](beds/jiecang.md#comfort-motion-app) |
| `beds/coolbase.md` | [Keeson: Cool Base](beds/keeson.md#cool-base) |
| `beds/customatic.md` | [Okin N-frame: Customatic family](beds/okin-nframe.md#customatic-family) |
| `beds/customatic-z-series.md` | [Okin N-frame: Customatic Z-Series](beds/okin-nframe.md#customatic-z-series) |
| `beds/dewertokin.md` | [Okin N-frame: DewertOkin](beds/okin-nframe.md#dewertokin) |
| `beds/doublesleep.md` | [Okin N-frame: OKIN SleepEase](beds/okin-nframe.md#okin-sleepease) |
| `beds/ergo-slim.md` | [Keeson: Ergo Slim](beds/keeson.md#ergo-slim) |
| `beds/ergomotion.md` | [Keeson: Ergomotion app](beds/keeson.md#ergomotion-app) |
| `beds/ergomotion-4.md` | [Keeson: Ergomotion 4.0](beds/keeson.md#ergomotion-40) |
| `beds/eshine.md` | [Richmat: Eshine](beds/richmat.md#eshine) |
| `beds/eshine-okin.md` | [Okin N-frame: eShine](beds/okin-nframe.md#eshine) |
| `beds/floyd.md` | [Kaidi: Floyd Home](beds/kaidi.md#floyd-home) |
| `beds/fsm_relax.md` | [Limoss: FSM Relax](beds/limoss.md#fsm-relax) |
| `beds/glideaway-motion.md` | [Keeson: Glideaway Motion](beds/keeson.md#glideaway-motion) |
| `beds/goodvibe.md` | [Richmat: Good Vibe Sleep](beds/richmat.md#good-vibe-sleep) |
| `beds/hjbed.md` | [Richmat: HJBed](beds/richmat.md#hjbed) |
| `beds/isleep.md` | [Kaidi: ISleep](beds/kaidi.md#isleep) |
| `beds/jiecang-app.md` | [Jiecang: Dream app family](beds/jiecang.md#dream-app-family) |
| `beds/leggett-okin.md` | [Okin N-frame: Leggett Okin family](beds/okin-nframe.md#leggett-okin-family) |
| `beds/limoss-remote.md` | [Limoss: Limoss Remote](beds/limoss.md#limoss-remote) |
| `beds/lp-legacy.md` | [Richmat: L&P legacy app](beds/richmat.md#lp-legacy-app) |
| `beds/logicdata-app.md` | [Jiecang: LOGICDATA app family](beds/jiecang.md#logicdata-app-family) |
| `beds/malouf-app.md` | [Malouf: Malouf Base / Lucid Base family](beds/malouf.md#malouf-base--lucid-base-family) |
| `beds/mattressfirm.md` | [Okin 5A: Mattress Firm 900 / iFlex](beds/okin-5a.md#mattress-firm-900--iflex) |
| `beds/motion_bed.md` | [FFFF frame: Motion Bed](beds/ff_frame.md#motion-bed) |
| `beds/motosleep.md` | [HHC `$#` frames: MotoSleep and Power Bob family](beds/motomotion.md#motosleep-and-power-bob-family) |
| `beds/nectar.md` | [Okin 5A: Nectar](beds/okin-5a.md#nectar) |
| `beds/okimat.md` | [Okin N-frame: Okimat](beds/okin-nframe.md#okimat) |
| `beds/okin-64bit.md` | [Okin N-frame: Okin 64-Bit](beds/okin-nframe.md#okin-64-bit) |
| `beds/okin-cb35.md` | [Okin 5A: Sealy Posturematic (CB35)](beds/okin-5a.md#sealy-posturematic-cb35) |
| `beds/okin-cst.md` | [Okin N-frame: Okin CST](beds/okin-nframe.md#okin-cst) |
| `beds/okin-dot.md` | [Okin N-frame: Okin DOT](beds/okin-nframe.md#okin-dot) |
| `beds/okin-rf-eco-bt.md` | [Okin N-frame: RF ECO BT stair lift](beds/okin-nframe.md#rf-eco-bt-stair-lift) |
| `beds/omazz-adjusto-iii.md` | [Keeson: Omazz Adjusto III](beds/keeson.md#omazz-adjusto-iii) |
| `beds/ore-comfort-bed.md` | [Keeson: ORE comfort-bed profiles](beds/keeson.md#ore-comfort-bed-profiles) |
| `beds/q-plus-adjustable-remote.md` | [Keeson: Q-Plus Adjustable Remote](beds/keeson.md#q-plus-adjustable-remote) |
| `beds/richmat-classic-apps.md` | [Richmat: Classic Richmat apps](beds/richmat.md#classic-richmat-apps) |
| `beds/richmat-mh.md` | [Richmat: Richmat MH apps](beds/richmat.md#richmat-mh-apps) |
| `beds/rmcontrol.md` | [Richmat: RMControl](beds/richmat.md#rmcontrol) |
| `beds/rondure.md` | [Keeson: Rondure](beds/keeson.md#rondure) |
| `beds/row-control.md` | [Keeson: ROW Control](beds/keeson.md#row-control) |
| `beds/sbi.md` | [Keeson: SBI / Q-Plus (Costco)](beds/keeson.md#sbi--q-plus-costco) |
| `beds/scott-living.md` | [Keeson: Scott Living](beds/keeson.md#scott-living) |
| `beds/serenity.md` | [Okin N-frame: Jordan's Serenity](beds/okin-nframe.md#jordans-serenity) |
| `beds/serta.md` | [Keeson: Serta](beds/keeson.md#serta) |
| `beds/serta-mp-remote.md` | [Keeson: Serta MP Remote](beds/keeson.md#serta-mp-remote) |
| `beds/simmons.md` | [Okin N-frame: SIMMONS](beds/okin-nframe.md#simmons) |
| `beds/solace.md` | [FFFF frame: Solace name routes](beds/ff_frame.md#solace-name-routes) |
| `beds/star-elevate.md` | [Okin 5A: DewertOkin ELEVATE](beds/okin-5a.md#dewertokin-elevate) |
| `beds/starcode-abm5-4.md` | [Okin N-frame: AdjustableM5X4](beds/okin-nframe.md#adjustablem5x4) |
| `beds/tempur-au.md` | [Keeson: TEMPUR AU](beds/keeson.md#tempur-au) |
| `beds/tempur-curve.md` | [Keeson: Tempur Curve](beds/keeson.md#tempur-curve) |
| `beds/tranquil.md` | [Okin N-frame: Jordan's Tranquil](beds/okin-nframe.md#jordans-tranquil) |
| `beds/vibradorm_app.md` | [Vibradorm: Caresse and Werkmeister](beds/vibradorm.md#caresse-and-werkmeister) |
| `beds/vmat.md` | [Vibradorm: VMAT](beds/vibradorm.md#vmat) |
| `beds/vmatbasic.md` | [Vibradorm: V-MAT Basic](beds/vibradorm.md#v-mat-basic) |
| `beds/woosa.md` | [FFFF frame: Woosa Sleep](beds/ff_frame.md#woosa-sleep) |
