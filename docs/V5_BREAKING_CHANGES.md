# v5 Breaking Changes

This page is for anyone upgrading from 4.x (4.4.2 or earlier) to v5. It
describes each change once, compared with 4.x. Changes between v5 betas are in
each beta's [release notes](https://github.com/kristofferR/ha-adjustable-bed/releases).

> [!CAUTION]
> **Take a Home Assistant backup before you install v5.** v5 migrates every
> Adjustable Bed entry to a new format that 4.x cannot load. Restoring a
> backup taken before the upgrade is the only way back to 4.x. See
> [Rollback](#rollback).

## Contents

- [Before you upgrade](#before-you-upgrade)
- [After you upgrade, check these](#after-you-upgrade-check-these)
- [Actions](#actions)
- [Settings](#settings)
- [Entities](#entities)
- [Movement and Stop](#movement-and-stop)
- [Setup and Reconfigure](#setup-and-reconfigure)
- [Dashboard card](#dashboard-card)
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
5. Restart Home Assistant and reload the dashboard page.

To stop receiving betas, choose **Exclude pre-releases** in the same menu. An
installed beta stays until a newer stable version is out.

**Installed through HACS?** HACS still lists this integration and installs v5
like any other version: open **Adjustable Bed** in HACS, choose **Redownload**
and pick the version. Use either HACS or the Marketplace for this integration,
not both.

## After you upgrade, check these

1. **Alarm automations.** The alarm actions listed under [Actions](#actions)
   are now one action, [`adjustable_bed.set_alarm`](SERVICES.md#set_alarm),
   with new field names. Beds whose alarm is part of their own action, such as
   `richmat_classic`, keep it there; the
   [`set_alarm` table](SERVICES.md#set_alarm) lists them.
2. **Renamed or removed actions.** `linak_rename`, `logicdata_rename`,
   `jiecang_rename`, `leggett_hold_control`, `malouf_sync_clock` and
   `reverie_test` are gone. See [Actions](#actions).
3. **On/off buttons became switches.** On some beds a pair of on and off
   buttons, or an on/off select, is now one switch with a new entity ID. Point
   automations and dashboards at the switch.
4. **Removed entities.** Entities that only mirrored the phone app's internals
   are removed. [Appendix A](#appendix-a-removed-and-replaced-entities-by-bed)
   lists them by bed.
5. **Connection settings.** Two disconnect settings became one **Bluetooth
   connection** setting, and two settings were removed. Your saved choices are
   migrated. See [Settings](#settings).
6. **Changing the app, model or remote** is now done in **Reconfigure**, not
   **Configure**. See [Setup and Reconfigure](#setup-and-reconfigure).
7. **Discovery toggle.** "Stop discovering new Bluetooth devices" moved from
   each bed's Configure to **Add Integration > Adjustable Bed > Find new beds
   automatically**.
8. **Dashboard card quick actions** are saved as entity IDs the next time you
   edit the card. See [Dashboard card](#dashboard-card).

## Actions

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
| `richmat_app_alarm` | `set_alarm` |
| `richmat_mh_alarm` | `set_alarm` |
| `richmat_mh_waist_alarm` | `set_alarm` |
| `rmcontrol_alarm` | `set_alarm` (setting the clock moved to `sync_clock`) |
| `simmons_set_alarm` | `set_alarm` |
| `solace_set_alarm` | `set_alarm` |
| `zseries_set_alarm` | `set_alarm` |
| `jiecang_rename`, `linak_rename`, `logicdata_rename` | `rename` |
| `leggett_hold_control` | `hold_control` |
| `malouf_sync_clock` | `sync_clock` |
| `reverie_test` | Removed (it ran a factory bed test) |

`set_alarm` uses the same fields on every bed. What changed from the old alarm
actions:

- `weekdays` takes `monday` to `sunday` everywhere: no numbers,
  abbreviations or bitmasks. "Once" or "daily" is an empty or full list.
- `wake_mode`, `preset`, `memory`, `mode` and `position` become `wake_action`,
  with shared names such as `zero_g`, `memory_1` and `none`.
- `head_level` and `foot_level` become `head_massage_level` and
  `foot_massage_level`; `intensity` becomes `massage_intensity`; `kind`
  becomes `massage_zone`; `alarm_id` becomes `slot`; `waist_side` becomes
  `mattress_side`.
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
  Keeson app tables with more than one weekly and one one-time alarm; Richmat
  app calendar alarm deletion (`enabled: false` disables the slot instead).

Other action changes:

- `furnimove_action` no longer takes `consumer`.
- `sleep_number_command` no longer accepts service, firmware and diagnostic
  commands such as `reboot_system` and `software_versions`.
- `timed_move` and `hold_control` gain optional `hold_owner` and
  `hold_generation` fields for renewable holds. Calls without them work as
  before. See [Renewable holds](SERVICES.md#renewable-holds).
- New actions for [estimated positions](ESTIMATED_POSITIONS.md#actions)
  (`estimate_save_position`, `estimate_recall_position`,
  `estimate_set_reference`, `lower_to_flat` and others), useful only after you
  enable estimated positions.

## Settings

Your saved settings are migrated on the first start. The migration also
records what it changed in diagnostics, under `profile_migration`.

| 4.x setting | v5 |
|-------------|----|
| **Position update mode** (`position_mode`) | Removed. When a command asks for a position read afterwards, it happens as with the default "Speed": in the background while the link stays open, and before the link is released with **Release right after each command**. No read is made when **Read bed position** is off or another command is waiting |
| **Connection profile** (`connection_profile`) | Removed. Every bed uses the former "Reliable" timing: a 25 s connect timeout, 3 and 6 s backoff and a 1 s pause after connecting |
| **Disconnect after each command** and **Idle disconnect timeout** (including its `0`, "keep connected") | One **Bluetooth connection** setting: **Release right after each command** (was Disconnect after each command on), **Stay connected for a while** with **Seconds to stay connected** (was off, with its timeout), or **Always stay connected** (was a timeout of `0` with Disconnect after each command off). Hidden for beds that always keep their link |
| With **Idle disconnect timeout**, a link the bed or adapter dropped was reconnected 5 s later with a new timeout each time, so a bed that drops idle links stayed connected and blocked its remote and app | **Stay connected for a while** counts from the last command. A dropped link is reconnected once before that time runs out (or whenever a command needs it) and is released when it would have been. If the reconnected link drops too, or after that time, the next command reconnects. **Always stay connected** and **Release right after each command** reconnect on the next command, as before |
| LP Comfort Connect (Leggett & Platt Gen2, and Leggett & Platt on Automatic) kept its link permanently | Follows **Bluetooth connection** and stays connected for a while by default. If a reconnect stalls, it keeps the link until you disconnect it or Home Assistant restarts. Choose **Always stay connected** for the old behavior |
| **Disable angle sensing** | **Read bed position**, on by default and shown only for beds that report a position. A saved choice equal to the bed's default is dropped, so the bed's default applies |
| **Motor pulse count** and **Motor pulse delay (ms)** | **Movement per tap** (the pulse count, usually 1 to 100; a few beds allow more). The delay is no longer shown; each bed uses its own, and a saved delay still applies |
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

## Entities

v5 gives every entity a plain name and removes entities that only mirrored the
phone app's internals.

- **Renamed entities keep their entity IDs, history and settings.** Only the
  shown name changes: brand and app names, notes such as "(app)" or "(raw)",
  protocol words and ALL-CAPS labels are gone. A name you set yourself stays.
- **Removed entities disappear by themselves** once the bed has connected.
  Remove them from dashboards, automations and scripts. Their values stay in
  diagnostics and support bundles.
- **On/off button pairs became switches**, with a new entity ID
  (`switch.<bed>_<name>`). A switch whose bed never reports the setting shows
  separate on and off controls.
- **Raw state sensors are disabled by default** on new installs. Existing ones
  keep their enabled state.
- **Refresh, query and clock-sync buttons are diagnostic** and disabled by
  default where the bed reports the value itself. So is the generic **Wake
  controller** button.
- **Buttons named after an app's controls show what they are.** On beds whose
  buttons come from an app or remote layout, motor up and down buttons sit in
  the card's motor rows, presets and memories in their tiles, and massage and
  light controls in their sections. A preset, memory or massage step every bed
  has takes the shared name (**Zero Gravity**, **Memory 1**, **Massage: Head
  Up**); other buttons keep the app's label without internal identifiers
  ("MasFootAdd" is **Increase foot massage**, "Ubb" is **Under-bed light**).
  Where an app lists two controls under one label, the second is numbered
  (**Wave 2**).
- **App extras start disabled** on new installs: music, fan, heating,
  aromatherapy, Bluetooth, reset and similar buttons. Enable them under the
  device's entities if you use them.
- **Saves follow one rule.** A preset save sits with the presets, is a
  configuration entity and asks for confirmation in the dashboard card. A
  memory save is offered in the card's Set mode and no longer asks twice.
- **Bed occupancy sensors** (Sleep Number) update only while the bed is
  connected. In 4.x their 30-second poll connected the bed and kept it
  connected; it no longer extends **Seconds to stay connected**.
- A paired bed's Left, Right and Both entities are named from their devices,
  as Home Assistant 2026.11 does, so the card no longer shows doubled names
  such as "Bed Left Back".

[Appendix A](#appendix-a-removed-and-replaced-entities-by-bed) lists the
removed and replaced entities by bed.

New in v5: estimated positions for beds without position feedback (see
[Estimated positions](ESTIMATED_POSITIONS.md)), and a `card_section` attribute
on every entity that tells the dashboard card where it belongs.

## Movement and Stop

- **Holding a control.** On beds whose app holds a key down until you let go,
  the dashboard card now keeps the motor moving while you hold the control and
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
  goes out. On Jiecang, Comfort Motion and Jensen LinOn beds, a Stop during a
  move reaches the bed at once instead of at the next repeat.
- **Stop wins while an action is still checking.** A Stop on any selected bed
  while `set_alarm`, `set_position` or `set_positions` is still connecting to
  or checking its beds ends the action: nothing is written or moved. In 4.x the
  first beds could still be written or moved afterwards.
- **Actions write only what they checked.** When a bed reconnects, is replaced
  or is paired differently after the check, `set_alarm` and `set_positions`
  stop with "The bed changed while the action was being checked" and write
  nothing. Preset, rename, clock and hold actions check the bed again when it
  connects and show its own reason if it no longer accepts the request.
- **Combined beds** connect and check both sides before an alarm is written to
  either. A failed alarm check no longer stops the other side.
- **Customatic covers** queue a second motor's move behind the first, as on
  other beds, instead of replacing it.
- **Leggett Okin Prodigy CE and U Series** send the release once after a
  `timed_move`, where 4.x sent it twice.
- **Support bundles** of beds that run their own write loops now record those
  commands, so they are larger.

## Setup and Reconfigure

- **Setup starts from the app or remote** that controls the bed. Choose **Set
  up by app or remote** or **Pick any Bluetooth device**, then search for the
  app. Many brands have one row that asks which app, remote or control box runs
  the bed; [Appendix B](#appendix-b-setup-families) lists them. The bed's own
  settings come last. Rows that left the list keep their bed type and ID, so
  saved entries load unchanged.
- **Reconfigure changes the app, model or remote**, for every bed. Open it from
  the entry's three-dots menu. It asks the same question as setup, shows the
  controls that are added, removed or change meaning, names the automations
  that use a removed control, and offers **Apply this change** or **Keep
  current setup**. **Configure** keeps the everyday settings and no longer
  changes the bed type, app or route. See
  [Changing the app or layout](CONFIGURATION.md#changing-the-bed-type-app-or-layout-of-an-existing-bed).
- **App suggestions in Repairs** open Reconfigure with the suggested app
  selected. A suggestion about a Richmat remote setting still opens Configure.
  Existing Solace entries are asked once whether they use the Woosa Sleep app.
- **Combined beds.** Dual Bed wording is now **Combine** and **Separate**.
  Repairs and Add Integration suggest **Combine two beds** only for two beds
  that use the same commands. **Separate into two beds** keeps the Bluetooth
  adapter and **Bluetooth connection** used while combined, and restores the
  bed type, app and side settings from before.
- **Labels.** The protocol variant is called **Bed model or remote**, and every
  automatic choice reads **Automatic (recommended)**. The Diagnostic row is now
  **Unsupported bed (diagnostics only)**. The Sleeptracker foundation size is
  no longer asked; it never changed a command.

## Dashboard card

- Quick actions (`compact_actions`) are saved as entity IDs. Cards that list
  the old keys keep working, and the editor rewrites them to entity IDs the
  next time you edit the card, if every side keeps the same actions.
- Preset save buttons are never offered as quick actions, and they ask for
  confirmation in the card.
- New options, off by default: **Tap to start and stop movement**
  (`tap_to_move`), percentage and lumbar graphics, and opening the full card
  in a dialog from a compact card. A new `show_graphic_labels` option, on by
  default, can hide the labels under the bed graphic. See the
  [Dashboard Card guide](DASHBOARD_CARD.md).
- The card names entities the way Home Assistant 2026.11 does, so a renamed
  device updates its labels.
- A split bed's side selector is named **Controlled side** on every bed and
  sits with the motor controls. Nerum's light button and light state sit with
  the lights.
- A bed with two controls for one card role, such as a massage timer button
  and a remaining-time sensor, shows both.

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

| Bed or app | Removed | Replaced |
|------------|---------|----------|
| AdjustaMattress | Privacy-agreement select, reported alarm and strength sensors, sleeping, alarm, anti-snore and auxiliary status binary sensors, clock sync, alarm query and massage query buttons | Alarm commit and anti-snore selects and the sleep button became the **Alarm**, **Intelligent anti-snore** and **Sleep mode** switches |
| BedSense | Head and wave bar sensors, memory indicator refresh and background tap buttons; the memory recall buttons of slots 3 to 5 | **TV**, **Zero Gravity** and **Anti-Snore** (**Flat** on layouts 6 and 8) recall those slots; their saves stay |
| Casper Base, Hush Base | "Memory position 1-3", "Save Memory position 1-3" and "Motor reset" buttons | **Memory 1-3**, **Save to Memory 1-3** and **Flat** send the same commands |
| DoubleSleep (OKIN SleepEase) | Four flag binary sensors, parser-error and privacy sensors | Child lock select and privacy buttons became switches; the app's "Stop all" is the disabled **Stop movement** (**Stop All** stops the bed) |
| eShine OKIN | Alarm refresh button | |
| Good Vibe Sleep | "No action", "Logo" and "… menu" buttons from empty app slots; "(long press)" buttons whose long press sends nothing of its own; a control the app lists twice | A preset's long press that sends its save is the **Save …** button |
| Keeson app layouts (TEMPUR, Ergomotion, Q-Plus, Serta MP Remote, Omazz, ROW Control, Ergo Slim) | The app's Flat button | **Flat** |
| FSM Relax | 11 count, acknowledgement, calibration, information and raw motor sensors | |
| FurniMove | Action rows a standard entity already sends (Flat, ZeroGravity, Snore, TV, Memo1-4, MemoSave, UBL, Sync, ChildLock, SwitchToPH/PR), function-result sensor | |
| Limoss Remote | Repeated motor channel buttons, capability count, calibration reply and raw position sensors | Covers are named **Motor 1** to **Motor 4** |
| Motion Bed app | 83 state sensors (preset-selected flags, raw positions, calibration samples, day and month report arrays, module and pressure readings), alarm-sound preview buttons | Alarm, climate timer, fault and sleep report details became attributes of their sensors |
| OKIN bedding apps (Jordan's Serenity and Tranquil, Customatic Z-Series) | Status, timer and save-event code sensors; Z-Series "Toggle light" | **Toggle Light** |
| OKIN CST | Memory recall buttons for slots a named preset recalls | **Zero Gravity**, **Incline**, **Reading** or **Lounge**; the slot's save stays |
| Reverie, Pairlink | Wave sensor, Pairlink massage mode and timer sensors (the select and number show them) | Pairlink massage rhythm select became the **Massage rhythm** switch |
| Richmat sleep receiver | | Left and right intervention selects became the **Left snore intervention** and **Right snore intervention** switches |
| RMControl | Protocol version, bed mode and last alarm record sensors | |
| Serta MP Remote | Memory request sensor | |
| Sleeptracker | Massage pattern and strength sensors (the selects show them) | |
| Sleepy's Elite app | All `field_0x..` sensors, voice STOP, voice brightness and voice position buttons, light on/off buttons (the light entity drives the light) | Motion sensor on/off buttons became the **Motion sensor** switch; axes 0, 1 and 2 are now **Head**, **Foot** and **Lumbar** |
| StarCode Adjustable Comfort M1X12 | Part 8 and Part 16 covers and buttons (still reachable through `hold_control`), Part 8/16/32 position sensors, MemoryType 8 recall, raw time and brightness sensors, motor-stopped, light-on and kneading-demo binary sensors | Parts 1, 2 and 4 are now **Head**, **Foot** and **Lumbar** |
| StarCode AdjustableM5X4 | 19 raw field sensors, selector sensors, wake, firmware-read and massage-release buttons | "App massage active" sensor became the **Massage** binary sensor |
| StarCode AdjustableM5X5 | Raw time, brightness, RGB-mode and motor part 4-6 sensors, motor-stopped, light-on, firmware-read and kneading-demo binary sensors | |
| SUTA Smart Home | Controls the bed's model does not have, query buttons, the **Model** sensor | Lock and unlock became a switch with a new entity ID |
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
| Okin | The FurniMove / OKIN Smart Remote app, an Okimat or OKIN handset code, a DOT remote, the RF ECO BT stair lift, and the Okin apps. Each Okin CST app, such as Resident Adjustable Bed, is its own row |
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
