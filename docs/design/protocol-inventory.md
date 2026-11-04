# Protocol inventory: wire formats and the code that implements them

Research output for #743, part of the v5 protocol split (#742). It maps every
bed type to its controller, helpers, routes, config keys and frozen APK report,
then groups bed types by wire format **proven by encoding**. Findings feed #744
(Jiecang pilot), #745 (remaining families), #746 (process) and #747 (docs).

State described: `v5` at `bf0ccd65`, before the #744 pilot. `ergomotion_4`
arrived later from `main` (`bb15d70d`, #751). Its rows below were classified by
the same predicates on its own snapshot scenarios; the counts do not include it.
The pilot consolidates the Jiecang modules listed below into `codec/jiecang.py`
and `profiles/jiecang.py`; this document describes the pre-pilot layout.

No integration behavior changed. The only code added is the capture tool and its
guard test (see [How the proof was produced](#how-the-proof-was-produced)).

## Summary

| Metric | Value |
| --- | ---: |
| Supported bed types (`SUPPORTED_BED_TYPES`) | 110 |
| Modules in `beds/` | 131 files |
| Capture scenarios (bed types, variant and app-profile routes, feature and GATT property routes) | 306 |
| Commands driven (all scenarios, connect included) | 16,579 |
| Scenarios with at least one successful command | 287 |
| Scenarios with a coverage gap (a declared command fails, or the connect hooks fail) | 70 |
| Scenarios where nothing succeeds | 19 |
| Event runs in the committed snapshot | 22,989 (22,466 writes, 263 subscriptions, 258 reads, 2 unsubscribes) |

Seven wire formats cover 70 of the 110 bed types (73 counting the partial Richmat
6E frames of GM Control and the Okin `05 02` motion frames of Starcode M1X12 and
M5X5), including LOGICDATA MOTIONrelax/Sleep Smart in the Jiecang family and the
Richmat MH apps in the Richmat family. The remaining bed
types are distinct protocols, sensors/remotes, or coverage gaps. See the next section.

## Wire families (proven by encoding)

A family is a framing rule that holds, byte for byte, for the **command writes**
of its members: movement, STOP, preset, memory, light and massage frames. Writes
made while connecting (`connect` entries: handshakes, clock sync, configuration,
queries) follow their own encodings and are counted separately. Where a rule has
exceptions among command writes they are listed below the table. "Relation"
classifies how members relate once framed alike:

- **Identical**: same commands, same bytes on all shared commands.
- **Same framing, different command sets**: the frame and checksum rule match, but
  the command payloads (motor masks, preset and memory codes) differ per app.
- **Distinct**: no shared framing rule.

| Family | Frame rule | Command writes matching | Connect writes matching | Bed types | Relation |
| --- | --- | ---: | ---: | ---: | --- |
| **J1 Jiecang F1** | `F1 F1 op len payload sum8(op..payload) 7E` | 2050 / 2076 | 155 / 155 | 4 (+ 3 more app profiles) | Same framing, different command sets and payloads, per profile |
| **K1 Keeson E5/E6** | `E5 FE ...` (8 bytes) or `E6 FE ...` (8 or 9 bytes), last byte `~sum8(all previous)` | 3555 / 3625 | 1 / 18 | 23 | Same framing, different command sets; core classes below |
| **O1 Okin N-frame** | `N 02 <N-byte command word>`, so length is `N+2` | 4405 / 4631 | 3 / 44 | 22 (+ Starcode M1X12 and M5X5 partial) | Same framing, command word width 32/40/48/64/96 bit (48 bit only on `adjustamattress:P4_L6`); different command sets |
| **O2 Okin 5A** | `5A .. .. .. .. .. A5`, 7 bytes | 513 / 538 | 0 / 3 | 6 | Core classes below: `nectar` = `okin_7byte` = `box25_star`, `mattressfirm` = `okin_nordic`, `okin_cb35` differs, `star_elevate` = its M1X12 route |
| **R1 Richmat 6E** | `6E xx xx xx sum8`, 5 bytes | 1012 / 1047 | 87 / 109 | 9 (+ gmmotor partial) | Same framing, per-model byte tables |
| **L1 Limoss DD** | `DD ...`, 10 bytes, last byte `sum8(previous)` | 1099 / 1099 | 31 / 31 | 3 (`limoss_remote` partial: handshake and STOP frames only) | Same framing, different command sets |
| **S1 FFFF frame** | 11 bytes starting `FF FF FF FF` | 1049 / 1050 | 57 / 58 | 3 | Same framing; `head_up`, `back_up`, `legs_up` and `stop_all` coincide between `bedsense` and `solace`, other axes and routes differ (core classes below); trailer algorithm not identified here |

Counts are write runs, in the scenarios (bed types and routes) whose command
writes mostly satisfy the family rule; a route of another family (for example
`keeson:json`) is not counted, nor are the GATT property routes (they repeat a
scenario's frames with another write mode). They cover the whole command plan, so they include
settings, alarm, clock, rename and query frames that the movement frames' rule was
never meant to describe. "Bed types" is the number of `SUPPORTED_BED_TYPES`
entries in the family.
The exact predicates used for counting:

- J1: starts `F1 F1`, ends `7E`, byte 3 equals `len - 6`, byte `-2` equals
  `sum8(bytes[2:-2])`.
- K1: starts `E5 FE` or `E6 FE` (any length), last byte equals `~sum8(all previous)`.
- O1: byte 1 is `02` and byte 0 equals `len - 2`.
- O2: starts `5A`, ends `A5`, length 7 (no checksum test).
- R1: starts `6E`, length 5, last byte equals `sum8(previous)`; the second byte varies.
- L1: starts `DD`, length 10, last byte equals `sum8(previous)`.
- S1: starts `FF FF FF FF`, length 11 (trailer not tested).

Command writes that do **not** satisfy their family rule (all from the snapshot).
Most are not motion frames but settings, clock, alarm, rename and query frames that
the wider command plan now reaches:

| Family | Bed type | Frames outside the rule |
| --- | --- | --- |
| J1 | `jiecang_app`, `logicdata_app` | `01 FC 07 ...` and the ASCII name (`rename_device`) |
| K1 | cluster033 apps (`ergo_slim`, `ergomotion_app`, `qplus_app`, `row_control`, `tempur_au`, `tempur_curve`, `omazz_adjusto_iii`, `serta_mp_remote`), `keeson` | `E7 80 ...` 10-byte clock sync, `E1 80 ...` 4-byte alarm dismiss, `EF 02 ...` 18-byte rename |
| K1 | `adjustamattress`, `glideaway_motion`, `bf`, `comfort_enhancements` | `E2 80`/`E2 FE` alarm queries and clock, `E7 80` clock sync, `ED 80` 16-byte alarm commit |
| K1 | `furnimove` | `00 B0` position request, ASCII rename |
| K1 | `ergomotion_4` | P1 (`H`): the cluster033 `E1 80`, `E7 80` and `EF 02` frames. P2 products: `04 02` O1 frames for every key, `00 B0` queries, `07 D0` 9-byte frames (M22), `09 0A`/`0A 02` RGB frames (M19, 4194RGB) |
| K1 | `simmons` (Okin route) | `05 02` 7-byte frames from the inclined buttons, `E1 80`/`E7 80` alarm and clock |
| O1 | `okin_dot` | `61 66 66 69 72 6D` (ASCII name write) |
| O1 | `sleepys_box25` | `04 E0 ...` 6-byte light and massage frames, `03 F0 ...` position targets, `00 D0` position request |
| O1 | `keeson:ksbt`, `adjustamattress`, `doublesleep`, `simmons`, `starcode_*` | `00 B0`/`00 C0`/`00 D0` 2-byte requests, `07 04`/`07 05`/`08 05` setting frames, short DoubleSleep `01 B1`/`01 B2`/`02 0B` frames |
| O1 | `starcode_m1x12`, `starcode_m5x5`, `starcode_abm5_4` | `04 E0` massage, light and timer frames; M1X12 also sends `5A 01 ...` (O2-shaped) massage holds |
| O1 | `adjustable_lumbar` | `02 04` massage check |
| R1 | `richmat` | `04 09`/`04 0A`/`04 0B` remote-code frames (lights, light timer, colour) |
| R1 | `richmat_best_mattress` | `6E 0C ...` 10-byte colour frame |
| O2 | `okin_nordic`, `mattressfirm` | `09 05 0A 23 05 00 00`, `5A 0B 00 A5` |
| O2 | `okin_cb35` | `5A 0B 00 A5` (4 bytes) |
| O2 | `sleepys_box25` (star route) | `5A E0 ...` 8-byte light and massage frames, `5A B0` request |
| S1 | `motion_bed` | one 10-byte `FF FF FF FF 02 ...` calibration frame |

Connect-time writes outside the rules include the E7 80 01 7E clock/config frame
and `E1 80 03 9B` (K1 apps), `6E 0C ...`/`6E 0D ...` variable-length frames
(`hjbed`), `5E 1A`/`5E 1B` (Richmat MH), one 17-byte `FFFFFFFF01` frame
(`motion_bed`), `01 02` (`leggett_okin`), and `00 B0`, `00 C0`, `00 D0`, `07 04 7E ...`
(`furnimove`, `adjustamattress`, `simmons`, `doublesleep`).
Treat these as separate encodings inside the same controllers: the codec for a
family needs a place for them (setup frames), not only the command frame.

Everything not listed above has its own framing, is a sensor or remote, or is a
coverage gap (see [Coverage gaps](#coverage-gaps)):
`linak`, `octo`, `reverie`, `reverie_nightstand`, `vibradorm`, `vibradorm_app`,
`vmatbasic`, `jensen` (its motor frames equal `svane:svane_remote_jmc`),
`svane:jensen_linon`, `sleep_number` and `_mcr`,
`kaidi` and `isleep`, `motosleep`, `suta`, `sleepstar`, `timotion_ahf`,
`remacro`, `logicdata` (legacy), `logicdata_air_pump`, `eshine`, `casper_base`,
`okin_ore`, `sleepys_box24`, `leggett_gen2`, `malouf_new_okin` and `malouf_app`
(Okin-like header with one extra byte, so the O1 length rule fails), `svane`,
`sleeptracker`, `sleepys_elite_app`, `leggett_lp_legacy`, and the Casper and GM Control sleep sensors/remote.

### Core classes inside each family

A **core class** is a set of scenarios (bed types plus routes) whose motor and STOP
commands (`head/back/legs/feet` up, down, stop and `stop_all`) are exactly equal:
the same commands exist and emit the same distinct frames, release frame
included. These are partitions, not chains, so every pair inside a class is
equal. A scenario with fewer axes forms its own class even if its frames agree on
the axes it has. The digits after a class name count the core commands.

| Family | Core class | Members |
| --- | --- | --- |
| K1 | **A, Keeson mask** (13) | `coolbase`, `ergomotion`, `serta`, `rondure`, `sbi`, `keeson:base`/`ergomotion`/`serta`/`restonic_a`/`restonic_b`/`innova`, the cluster033 apps `ergo_slim`, `ergomotion_app`, `omazz_adjusto_iii`, `qplus_app`, `row_control`, `serta_mp_remote`, `tempur_au`, `tempur_curve`, and `rondure:both`, `sbi:both` (21 scenarios) |
| K1 | **B, E6 9-byte** (13) | `adjustamattress` (base and 3 layouts), `malouf_legacy_okin`, `sleepys_box15`, `simmons:simmons_okin`, `simmons_inclined_okin` (8) |
| K1 | **C, comfort_enhancements** (13) | `comfort_enhancements` and `mc2` to `mc5` (5) |
| K1 | **D, ORE bases** (11) | `keeson:americanstar`, `avanti_bases`, `bedsense_bases`, `dynasty_bases`, `maxcoil_una` (5) |
| K1 | smaller classes | `scott_living` = `rondure:side_a` = `sbi:side_a`; `rondure:side_b` = `sbi:side_b`; `keeson:okin` = `okin_ffe`; `keeson:okin_seating` = `keeson:simon_li`; `keeson:heal_every_night` = `keeson:sino`; singles `bf`, `cherish`, `furnimove`, `glideaway_motion` |
| O1 | **32-bit `04 02`** (13) | `okimat` = `okin_uuid`, `dewertokin` = `okin_handle`, `customatic_clarity`/`jeromes`/`remedy` (7) |
| O1 | **40-bit `05 02`** (13) | `okin_cb24` (base and 6 routes), `doublesleep` (+ `p1`), `simmons` (+ `simmons_smartbed`, `inclined`, `inclined_smartbed`), `keeson:ksbt_cr`, `sleepys_box25` (+ `box25_legacy`), `starcode_m1x12`, `starcode_m5x5` (18) |
| O1 | **96-bit `0C 02`** (13) | `okin_cst` (base and 10 routes), `serenity`, `tranquil`, `customatic_zseries` (14) |
| O1 | **64-bit `08 02`** (13) | `okin_64bit`, `adjustable_lumbar` (6) |
| O1 | 48-bit `06 02` | `adjustamattress:P4_L6` (13), the only 48-bit frame width captured |
| O1 | smaller classes | `leggett_okin` = `leggett_platt` (3 incl. route `okin`); `okin_dot` (+ `97450`, `97544`; `90167`/`91983`/`93558` form a 9-command class; `98035` its own); singles `starcode_abm5_4`, `okin_rf_eco_bt`, `keeson:ksbt`, `keeson:adjustable_lite` |
| O2 | 5A (13) | `nectar` = `okin_7byte` = `sleepys_box25:box25_star` (3); `mattressfirm` = `okin_nordic` (2); `star_elevate` = `star_elevate:adjustable_comfort_m1x12` (2); single `okin_cb35` |
| R1 | 6E (13) | `hjbed`, `leggett_wilinke` = `leggett_platt:mlrm`, `richmat:wilinke`, five Richmat MH apps by model (14); `richmat` = `bedtech` (2); `gmmotor` (5 frames) |
| L1 | DD | `limoss` (13 commands), `fsm_relax` (5), each its own class |
| S1 | FFFF | `bedsense` (5 layouts, 11 commands), `bedsense_1`/`7`/`9` (9), `bedsense_6`/`8` (7), `solace`, `solace:woosa`, `motion_bed` (STOP only): six classes |
| J1 | **legacy** (13) | `jiecang` = `comfort_motion` (2) |
| J1 | **DreamHD and Comfort Motion app** (11 for `standard_2`, 13 for the 3 and 4 motor layouts) | `jiecang_app` profiles `dreamhd` and `comfort_motion` per layout, 8 scenarios in 2 classes |
| J1 | **DreamAsk, Dreamotion** | one class per profile and layout family (9 scenarios in 4 classes); they use the long `4E 02 00 00` release |
| J1 | **LOGICDATA** (11) | P1 over T1: phone (default and massage/light route), tablet, Sleep Smart (5 scenarios); P1 over T3: phone, Sleep Smart (2); P2 "middle" phone/tablet (2); Sleep Smart over T2 alone |

J1 detail: the motion frames of the legacy route, DreamHD, Comfort Motion and
DreamAsk/Dreamotion agree on the shared axes (for example `back_up` is
`F1F1010101037E` in all of them); they differ in the release frame, the motion
refresh and the extra axes. LOGICDATA P1 uses payload `01` throughout and P2 uses
`00 00` throughout (`back_up` is `F1F101020000037E`); DreamAsk and Dreamotion use
`00 00` only for memory recall and program.

Cross-family notes:

- `simmons:simmons_okin` and `keeson:okin` are K1 (E6 frames), while
  `simmons:simmons_smartbed` is O1 (`05 02`): one controller emits two families.
- `keeson:ksbt` and `keeson:ksbt_cr` emit O1 frames, `keeson:adjustable_lite` emits
  O1 with its own mask, and `keeson:json`/`purple`/`ksbt04c`/`sleep_harmony` are
  distinct. "Keeson" is a routing table over four families, not one protocol.
- `sleepys_box25` legacy is O1 `05 02`; the `box25_star` route is O2 `5A`.
- `leggett_platt:mlrm` and `leggett_wilinke` are R1 (Richmat 6E); `:gen2` is distinct.
- The BedSense app, Solace/Woosa and Motion Bed share the `FF FF FF FF` frame, so
  BedSense is a Solace-family wire format with its own app layouts.

## Same app through different controllers

| App or product | Route A | Route B | Bytes |
| --- | --- | --- | --- |
| **Comfort Motion** | bed type `comfort_motion`, `JiecangController` (`beds/jiecang.py`) | `jiecang_app` with profile `comfort_motion`, `ComfortMotionController` (`beds/comfort_motion.py`) | Motion, preset and memory frames **identical** on the shared commands; the sets differ (route A also covers massage start/stop and 3 memory slots). Different: pulse (25 x 50 ms vs 10 x 100 ms), memory slots (3 vs 2), a connect-time setup schedule and name/notify roles only in route B, two massage encodings |
| **Jiecang `jiecang` bed type** | legacy `jiecang` (README: Glideaway, Dream Motion, LOGICDATA) | `jiecang_app` DreamAsk/Dreamotion/DreamHD profiles | Same F1 frame, different payload width for memory (`01` vs `00 00`), different pulse and release schedule |
| **LOGICDATA MOTIONrelax / Sleep Smart** | `jiecang` (its FE60/FE61 "Lierda3" write-characteristic branch) | `logicdata_app` (`logicdata_app_protocol.py`, T1/T2/T3 equal Jiecang G1/G2/G3) | Same F1 frames: all 9 captured `logicdata_app` scenarios satisfy the F1 rule. P1 uses the legacy `01` payload (memory recall equals the legacy route); P2 uses `00 00` for every command, which no Jiecang profile does |
| **JMC400 / Jensen** | `jensen` (`JensenController`) | `svane` variant `svane_remote_jmc` (`SvaneController`) | Same motor and STOP frames on the `1111` characteristic; different pulse (4 x 300 ms against 10 x 100 ms), connect sequence and memory handling (Jensen PIN and saved slots, Svane raw position reads) |
| **QMS / Sealy Motion** | `solace` | `motion_bed` | Both emit the `FF FF FF FF` STOP frame; `motion_bed` adds state and air/thermal controls |
| **Okin SmartBed** | `okin_cb24` variants | `simmons:simmons_smartbed`, `doublesleep`, `starcode_abm5_4` | Shared 40-bit `05 02` framing and motor masks for `okin_cb24`, `simmons`, `doublesleep`; memory and preset mappings differ per profile (`memory_recall_1` is `05 02 00 00 20 00 00` in `okin_cb24`, `05 02 00 01 00 00 00` in `starcode_abm5_4`, which also forms its own core class) |
| **Okin OKIN FFE** | bed type `okin_ffe` | `keeson` variant `okin` | Same controller and frames, different pulse defaults: `okin_ffe` 7 x 150 ms, `keeson:okin` 10 x 100 ms |

Byte-identical routes. The groups below produce the same status and the same
events, timing included, on **every** captured command. Collapsing them needs a
config-entry migration (or documented alias) in #744/#745:

| Group | Controller |
| --- | --- |
| `comfort_motion` = `jiecang` | `JiecangController` |
| `okimat` = `okin_uuid` | `OkinUuidController` |
| `dewertokin` = `okin_handle` | `OkinHandleController` |
| `nectar` = `okin_7byte` | `Okin7ByteController` |
| `mattressfirm` = `okin_nordic` | `OkinNordicController` |
| `ergomotion` = `keeson:ergomotion`; `serta` = `keeson:serta` | `KeesonController` |
| `leggett_okin` = `leggett_platt` = `leggett_platt:okin`; `leggett_gen2` = `leggett_platt:gen2` | `LeggettOkinController`, `LeggettGen2Controller` |
| `keeson:americanstar` = `avanti_bases` = `bedsense_bases` = `dynasty_bases` = `maxcoil_una` | `OreComfortBedController` |
| `richmat_best_mattress:model_bfrm` = `richmat_blvd_home:model_bfrm` (one model in two apps) | `RichmatMhController` |
| `fsm_relax` = `fsm_relax:massage_light` (the light and massage flags change nothing the capture reaches, since the capability handshake is not answered) | `FsmRelaxController` |

Routes equal to their default route: `sbi:both`, `rondure:both`, `keeson:json`,
`octo:standard`, `linak:bed_control`, `doublesleep:p1`, `okin_cb24:cb24` (and
`cb1221`, `cb24_ab`, `cb27`, `cb_old`, `dacheng`), `simmons:simmons_smartbed`,
`sleepys_box25:box25_legacy`, `remacro:the_brick`, `adjustable_lumbar_star`,
`adjustamattress:P1_L1`, `bedsense:bedsense_3`, `comfort_enhancements:mc2`,
`jiecang_app:dreamask:standard_2:g1`, `kaidi:seat_1`, `logicdata_app:phone:p1:standard_2:t1`,
`okin_64bit:nordic`, `okin_cst:cst_aviada`/`cst_contempo`/`cst_mf900` and
`okin_dot:97450`. Other equal route pairs: `okin_cb24:cb27new` = `cb_new`,
`okin_dot:91983` = `93558`, `bedsense_4` = `bedsense_5`,
`simmons:simmons_inclined` = `simmons_inclined_smartbed`.

**Not aliases.** One controller class or one frame, but different bytes or timing
on some commands, so each stays its own profile. Counts are commands of the full
plan that differ (status, events or timing):

| Pair | Commands that differ |
| --- | --- |
| `okin_ffe` vs `keeson:okin` (`KeesonController`) | movement timing only: 7 x 150 ms against 10 x 100 ms |
| `leggett_wilinke` vs `leggett_platt:mlrm` (`LeggettWilinkeController`) | movement timing only: 10 x 110 ms against 10 x 100 ms |
| `tempur_au` vs `tempur_curve` (two cluster033 apps) | same motor frames; 12 controller-declared buttons differ |
| `bf` vs `cherish` (`BfCherishController`) | 30 of 47, including head moves, lights, massage and memory program |
| `customatic_clarity` vs `_jeromes` vs `_remedy` (`CustomaticController`) | 41 of 76 and 24 of 96: product buttons, held combinations, lumbar |
| `remacro:the_brick` vs `remacro:jeromes` | 39 of 42 |
| `serenity` vs `tranquil` | 35 of 103, product buttons and `preset_tv` |
| `serenity` vs `okin_cst` (same 96-bit frame) | 85 of 92: same motion frames, but Serenity paces from the start of each write (wall-clock pacing), plus massage, memory and presets |
| `ergo_slim` vs `ergomotion_app`; `omazz_adjusto_iii` vs `tempur_au` | 30 of 49 and 35 of 54: connect frame, product buttons, `preset_flat` for `ergo_slim` |
| `sbi` vs `rondure` (same E5 frame) | 38 of 51: identical motion masks, but write mode (with against without response), repetition (10 x 100 against 25 x 50 ms) and massage differ |
| `solace` vs `solace:woosa`; `solace` vs `bedsense` (same FFFF frame) | 38 of 84 and 88 of 94 |

## Genuine per-app differences (profile schema inputs)

Values below are captured from the snapshot (movement call on the controller,
virtual time), with each bed type's own pulse defaults
(`get_motor_pulse_defaults`, recorded per scenario as `info.pulse`). Protocol
values are hardware specific and must stay per profile. The stub adds a fixed
7 ms to every write, so a controller that waits its delay after the write shows
107 ms where the intervals below say 100 ms; one that measures the delay from the
start of the write (wall-clock pacing) shows exactly 100 ms. The intervals below
are the nominal values.

| Axis | Observed range | Examples |
| --- | --- | --- |
| Pulse defaults (`BED_MOTOR_PULSE_DEFAULTS`) | 10 x 100 ms default; 1 x 300; 3 x 50/300/350; 4 x 300; 5 x 200; 7 x 150; 8 x 120; 10 x 30/60/110; 12 x 80; 25 x 50; 34 x 30 | `okin_ore` 1 x 300; `octo` 3 x 350 (`octo:star2` 3 x 50); `okin_cb24`/`okin_cb35` 3 x 300; `jensen`/`simmons`/`linak:performance_legacy` 4 x 300; `adjustamattress`/`comfort_enhancements` 5 x 200; `richmat`/`okin_ffe`/`malouf_app`/`malouf_legacy_okin`/`suta` 7 x 150; `customatic_*` 8 x 120; `logicdata` 10 x 30; `fsm_relax` 10 x 60; `leggett_wilinke` 10 x 110; `limoss` 12 x 80; `rondure` 25 x 50; `vmatbasic` 34 x 30 |
| Movement refresh as sent | the pulse default, unless the protocol fixes its own cadence | follows the default: the rows above; fixed by the protocol: `jiecang`/`comfort_motion` 25 x 50, `bf`/`cherish` 10 x 200, `glideaway_motion` 10 x 300, `doublesleep` 10 x 300, `leggett_gen2` 25 x 200, `logicdata_app` 11 x 100, `keeson:base` 3 x 400, `keeson:ksbt*`/`adjustable_lite`/`sleep_harmony` 4 x 300, `svane:jensen_linon` 2 x 800; single frame then release: `bedsense`, `kaidi:floyd`, `isleep`, `keeson:json` |
| Release schedule | none; one STOP; two STOPs at 100 ms; four at 100 ms; five at 30 ms; two at 300 ms | none: `furnimove`, `okin_rf_eco_bt`, `octo:star2`, `keeson:adjustable_lite`; DreamAsk 10 x 100 then the long `4E 02 00 00` release twice; Dreamotion 10 x 100, one more press, the short `4E 00` release, then the long one; DreamHD the same without the long release; Comfort Motion app and legacy: short release only (presets: DreamAsk/Dreamotion press plus long release, DreamHD and Comfort Motion press plus short release, legacy 3 x 100 press with no release); `okin_cst` family and `suta` 2 x 100; `leggett_okin` 4 x 100; `motosleep` 5 x 30 |
| Write mode | response true or false, per protocol and per route | `okin_cb24` false, `okin_cst` true, Richmat MH false, `richmat` true, `adjustable_lumbar` follows the variant (okin true, star false) |
| Hold-only or gesture actions | presets as single press, as repeated hold, or as press plus release | LOGICDATA Sleep Smart presets 10 x 200 ms; DreamHD press then short release; `jiecang` 3 x 100 ms with no release; `bedsense`/`solace`/`remacro` presets are one frame with no STOP (their motion calls send a frame plus STOP) |
| Memory encoding | per profile payload and repeat | DreamAsk/Dreamotion `0B 02 00 00`; Comfort Motion, legacy, LOGICDATA P1 `0B 01 01`; program writes 1 x or 3 x 30 ms |
| Connect-time sequence | none; setup schedule of 1 to 9 write runs (a run is a frame repeated at a fixed interval) | `jiecang_app` 7 runs, `logicdata_app` 4, `hjbed` 6, `motion_bed` 8, `solace:woosa` 8 (its startup queries, recorded as `background`), `simmons` 7, `sleepstar` 9 (and a delayed retry at about 12.6 s, recorded as `background`), `bedsense` 5, `gmmotor` 3, `limoss` 3 |
| Roles from GATT | fixed UUID, service-scoped role, role chosen by property, multi-service | cluster033 and ORE apps: fixed; Jiecang G1/G2/G3 and LOGICDATA T1/T2/T3: per-transport; `eshine`, `serenity`: "exactly one" role checks |
| Sessions, authentication, state | none; PIN; session or auth read; bond or pair; catalog; per-axis state | `octo` and `jensen` PIN; `sleep_number` auth session and BAM key; `linak` auth window; `leggett_gen2` bond and repair; `kaidi`/`isleep`/`floyd` mesh IDs from advertisement; `doublesleep`, `gmmotor`, `hjbed` sessions; `svane` raw axis reads before recall; `richmat_mh` model catalog; `starcode_abm5_4` bond; `fsm_relax` memory names |

Profile data (planned #744 schema) can cover movement refresh, release schedule,
write mode, memory/preset payloads and the connect schedule. State machines and
authentication stay profile-specific controller code, as #742 allows.

## Inventory

`Wire family` uses the labels above. `Routes captured` lists the variant or app
profile scenarios in the snapshot. "inline" under helpers means the frames are
built in the controller module. Helper modules are the package modules the
controller imports directly (module level or inside a function), other than the
shared infrastructure (`base`, `const`, `coordinator`, `detection`, `app_session`,
`adapter`, `entity` and similar). Lines count the controller plus those helpers.
`Primary test` is the first test file importing the controller module.

| Bed type | Controller (module, lines incl. helpers) | Helper modules | Wire family | Routes captured | Primary test |
|---|---|---|---|---|---|
| `adjustable_lumbar` | `AdjustableLumbarController` (`adjustable_lumbar`, 626) | inline | O1 Okin N-frame | adjustable_lumbar_okin, adjustable_lumbar_star | `test_adjustable_lumbar.py` |
| `adjustamattress` | `AdjustaMattressController` (`adjustamattress`, 1197) | `adjustamattress_protocol.py` | K1 Keeson E5/E6 | P1_L0, P1_L1, P1_L2, P4_L6 | `test_adjustamattress.py` |
| `bedsense` | `BedSenseController` (`bedsense`, 1099) | `bedsense_commands.py`, `bedsense_memory.py` | S1 FFFF frame | bedsense_1, bedsense_2, bedsense_3, bedsense_4, bedsense_5 +4 | `test_bedsense.py` |
| `bedtech` | `BedTechController` (`bedtech`, 395) | inline | R1 Richmat 6E |  | `test_bedtech.py` |
| `bf` | `BfCherishController` (`bf_cherish`, 779) | inline | K1 Keeson E5/E6 |  | `test_bf_cherish.py` |
| `casper_base` | `CasperBaseController` (`casper_base`, 1480) | `casper_base_catalog.py`, `casper_base_protocol.py` | D distinct |  | `test_casper_base.py` |
| `casper_remote` | `CasperRemoteController` (`casper_sleep`, 1025) | `casper_base_protocol.py`, `casper_sleep_protocol.py` | N/A not a bed |  | `test_casper_base.py` |
| `casper_sleep_mm` | `CasperSleepController` (`casper_sleep`, 1025) | `casper_base_protocol.py`, `casper_sleep_protocol.py` | N/A sensor |  | `test_casper_base.py` |
| `casper_sleep_sxb` | `CasperSleepController` (`casper_sleep`, 1025) | `casper_base_protocol.py`, `casper_sleep_protocol.py` | N/A sensor |  | `test_casper_base.py` |
| `cherish` | `BfCherishController` (`bf_cherish`, 779) | inline | K1 Keeson E5/E6 |  | `test_bf_cherish.py` |
| `comfort_enhancements` | `ComfortEnhancementsController` (`comfort_enhancements`, 539) | inline | K1 Keeson E5/E6 | mc2, mc3, mc4, mc5 | `test_comfort_enhancements.py` |
| `comfort_motion` | `JiecangController` (`jiecang`, 393) | inline | J1 Jiecang F1 |  | `test_jiecang.py` |
| `coolbase` | `CoolBaseController` (`coolbase`, 667) | inline | K1 Keeson E5/E6 |  | `test_coolbase.py` |
| `customatic_clarity` | `CustomaticController` (`customatic`, 462) | inline | O1 Okin N-frame |  | `test_customatic.py` |
| `customatic_jeromes` | `CustomaticController` (`customatic`, 462) | inline | O1 Okin N-frame |  | `test_customatic.py` |
| `customatic_remedy` | `CustomaticController` (`customatic`, 462) | inline | O1 Okin N-frame |  | `test_customatic.py` |
| `customatic_zseries` | `ZSeriesController` (`serenity`, 1883) | `okin_cst.py`, `okin_protocol.py` | O1 Okin N-frame |  | `test_serenity.py` |
| `dewertokin` | `OkinHandleController` (`okin_handle`, 321) | inline | O1 Okin N-frame |  | `test_okin_handle.py` |
| `doublesleep` | `DoubleSleepController` (`doublesleep`, 2393) | `doublesleep_services.py`, `doublesleep_state.py`, `doublesleep_protocol.py` | O1 Okin N-frame | p1, p2, p3 | `test_doublesleep_controller.py` |
| `ergo_slim` | `ErgoSlimController` (`ergo_slim`, 1184) | `cluster033.py`, `cluster033_profiles.py` | K1 Keeson E5/E6 |  | none direct |
| `ergomotion` | `KeesonController` (`keeson`, 2417) | `okin_protocol.py` | K1 Keeson E5/E6 |  | `test_keeson.py` |
| `ergomotion_app` | `ErgomotionAppController` (`ergomotion_app`, 1184) | `cluster033.py`, `cluster033_profiles.py` | K1 Keeson E5/E6 |  | none direct |
| `ergomotion_4` | `Ergomotion4Controller` (`ergomotion4`, 3207) | `cluster033.py`, `cluster033_profiles.py`, `ergomotion4_profiles.py` | K1 Keeson E5/E6 (P1 products); P2 products send the O1 32-bit `04 02` frame | M10, M14, M19, M22, M30, 4194RGB, custom | `test_ergomotion4.py` |
| `eshine` | `EshineController` (`eshine`, 714) | `eshine_protocol.py` | D distinct |  | `test_eshine.py` |
| `fsm_relax` | `FsmRelaxController` (`fsm_relax`, 1571) | `limoss.py`, `fsm_relax_state.py` | L1 Limoss DD |  | `test_fsm_relax.py` |
| `furnimove` | `FurniMoveController` (`furnimove`, 3028) | `furnimove_profiles.py` | K1 Keeson E5/E6 |  | `test_furnimove.py` |
| `glideaway_motion` | `GlideawayMotionController` (`glideaway_motion`, 609) | inline | K1 Keeson E5/E6 |  | `test_glideaway_motion.py` |
| `gmmotor` | `GmmotorController` (`gmmotor`, 1575) | `gmmotor_catalog_types.py`, `gmmotor_notifications.py`, `gmmotor_profiles.py`, `gmmotor_protocol.py`, `gmmotor_requests.py`, `gmmotor_sessions.py`, `gmmotor_transport.py` | R1 Richmat 6E (partial) |  | `test_gmmotor.py` |
| `gmmotor_sleep_mm` | `GmmotorSleepController` (`gmmotor_sleep`, 1822) | `gmmotor_notifications.py`, `gmmotor_protocol.py`, `gmmotor_requests.py`, `gmmotor_sessions.py`, `gmmotor_sleep_protocol.py`, `gmmotor_sleep_reports.py`, `gmmotor_sleep_state.py`, `gmmotor_transport.py` | N/A sensor |  | `test_gmmotor_sleep.py` |
| `gmmotor_sleep_sxb` | `GmmotorSleepController` (`gmmotor_sleep`, 1822) | `gmmotor_notifications.py`, `gmmotor_protocol.py`, `gmmotor_requests.py`, `gmmotor_sessions.py`, `gmmotor_sleep_protocol.py`, `gmmotor_sleep_reports.py`, `gmmotor_sleep_state.py`, `gmmotor_transport.py` | N/A sensor |  | `test_gmmotor_sleep.py` |
| `hjbed` | `HJBedController` (`hjbed`, 2503) | `hjbed_catalog.py`, `hjbed_protocol.py`, `hjbed_receive.py`, `hjbed_requests.py`, `hjbed_state.py` | R1 Richmat 6E |  | `test_hjbed.py` |
| `isleep` | `IsleepController` (`isleep`, 1072) | `isleep_profile.py`, `kaidi_protocol.py` | D Kaidi mesh |  | `test_isleep.py` |
| `jensen` | `JensenController` (`jensen`, 1003) | inline | D distinct |  | `test_jensen.py` |
| `jiecang` | `JiecangController` (`jiecang`, 393) | inline | J1 Jiecang F1 |  | `test_jiecang.py` |
| `jiecang_app` | `JiecangAppController` (`jiecang_app`, 1336) | `jiecang_app_protocol.py` | J1 Jiecang F1 | comfort_motion:standard_2:g1, comfort_motion:standard_2:g2, comfort_motion:standard_3_neck:g1, comfort_motion:standard_4_legacy:g1, dreamask:standard_2:g1 +11 | `test_dreamhd.py` |
| `kaidi` | `KaidiController` (`kaidi`, 1668) | `kaidi_metadata.py`, `kaidi_protocol.py` | D Kaidi mesh | floyd, seat_1, seat_1_2, seat_2, seat_3 | `test_kaidi.py` |
| `keeson` | `KeesonController` (`keeson`, 2417) | `okin_protocol.py` | K0 Keeson (variants) | adjustable_lite, americanstar, avanti_bases, base, bedsense_bases +18 | `test_keeson.py` |
| `leggett_gen2` | `LeggettGen2Controller` (`leggett_gen2`, 836) | `leggett_gen2_profiles.py` | D distinct |  | `test_leggett.py` |
| `leggett_lp_legacy` | `LeggettLpLegacyController` (`leggett_lp_legacy`, 557) | `lp_legacy_profiles.py` | D distinct |  | `test_paired_setup.py` |
| `leggett_okin` | `LeggettOkinController` (`leggett_okin`, 1443) | `okin_protocol.py`, `leggett_app_protocol.py` | O1 Okin N-frame |  | `test_leggett.py` |
| `leggett_platt` | `LeggettOkinController` (`leggett_okin`, 1443) | `okin_protocol.py`, `leggett_app_protocol.py` | O1 Okin N-frame | gen2, mlrm, okin | `test_leggett.py` |
| `leggett_wilinke` | `LeggettWilinkeController` (`leggett_wilinke`, 501) | inline | R1 Richmat 6E |  | `test_leggett_wilinke.py` |
| `limoss` | `LimossController` (`limoss`, 682) | inline | L1 Limoss DD |  | `test_limoss.py` |
| `limoss_remote` | `LimossRemoteController` (`limoss_remote`, 1385) | `limoss_remote_protocol.py`, `limoss_remote_state.py` | L1 Limoss DD (partial) |  | `test_limoss_remote.py` |
| `linak` | `LinakController` (`linak`, 2568) | `linak_protocol.py` | D distinct | bed_control, performance_legacy | `test_linak.py` |
| `logicdata` | `LogicdataController` (`logicdata`, 393) | inline | D distinct |  | none direct |
| `logicdata_air_pump` | `LogicdataAirPumpController` (`logicdata_air_pump`, 386) | inline | D distinct |  | `test_logicdata_air_pump.py` |
| `logicdata_app` | `LogicdataAppController` (`logicdata_app`, 1310) | `logicdata_app_protocol.py` | J1 Jiecang F1 | phone:p1:standard_2:t1, phone:p1:standard_2:t3, phone:p2:middle:t1, sleep_smart:p1:standard_2:t1, sleep_smart:p1:standard_2:t2 +3 | `test_paired_setup.py` |
| `malouf_app` | `MaloufAppController` (`malouf_app`, 1140) | `malouf_app_protocol.py` | D distinct (Okin-like, one extra byte) |  | `test_malouf_app.py` |
| `malouf_legacy_okin` | `MaloufLegacyOkinController` (`malouf`, 889) | inline | K1 Keeson E5/E6 |  | `test_malouf.py` |
| `malouf_new_okin` | `MaloufNewOkinController` (`malouf`, 889) | inline | D distinct (Okin-like, one extra byte) |  | `test_malouf.py` |
| `mattressfirm` | `OkinNordicController` (`okin_nordic`, 445) | `okin_7byte.py` | O2 Okin 5A |  | `test_okin_nordic.py` |
| `motion_bed` | `MotionBedController` (`motion_bed`, 4676) | `motion_bed_actions.py`, `motion_bed_models.py`, `motion_bed_protocol.py`, `motion_bed_requests.py`, `motion_bed_state.py` | S1 FFFF frame |  | `test_paired_setup.py` |
| `motosleep` | `MotoSleepController` (`motosleep`, 1006) | `motosleep_profiles.py` | D distinct |  | `test_motosleep.py` |
| `nectar` | `Okin7ByteController` (`okin_7byte`, 411) | inline | O2 Okin 5A |  | `test_okin_7byte.py` |
| `octo` | `OctoController` (`octo`, 2941) | inline | D distinct | standard, star2 | `test_octo.py` |
| `okimat` | `OkinUuidController` (`okin_uuid`, 3272) | `okin_protocol.py`, `okin_uuid_remotes.py`, `furnimove_profiles.py` | O1 Okin N-frame |  | `test_okin_uuid.py` |
| `okin_64bit` | `Okin64BitController` (`okin_64bit`, 378) | inline | O1 Okin N-frame | custom, nordic | `test_okin_64bit.py` |
| `okin_7byte` | `Okin7ByteController` (`okin_7byte`, 411) | inline | O2 Okin 5A |  | `test_okin_7byte.py` |
| `okin_cb24` | `OkinCB24Controller` (`okin_cb24`, 755) | `okin_protocol.py` | O1 Okin N-frame | cb1221, cb24, cb24_ab, cb27, cb27new +3 | `test_okin_cb24.py` |
| `okin_cb35` | `OkinCB35Controller` (`okin_cb35`, 839) | `okin_7byte.py` | O2 Okin 5A |  | `test_okin_cb35.py` |
| `okin_cst` | `OkinCstController` (`okin_cst`, 1060) | `okin_protocol.py` | O1 Okin N-frame | cst_aviada, cst_bob, cst_carefree, cst_clarity, cst_contempo +5 | `test_okin_cst.py` |
| `okin_dot` | `OkinDotController` (`okin_dot`, 1735) | `okin_protocol.py`, `okin_uuid.py`, `okin_uuid_remotes.py` | O1 Okin N-frame | 90167, 91983, 93558, 97450, 97544 +1 | `test_okin_dot.py` |
| `okin_ffe` | `KeesonController` (`keeson`, 2417) | `okin_protocol.py` | K1 Keeson E5/E6 |  | `test_keeson.py` |
| `okin_handle` | `OkinHandleController` (`okin_handle`, 321) | inline | O1 Okin N-frame |  | `test_okin_handle.py` |
| `okin_nordic` | `OkinNordicController` (`okin_nordic`, 445) | `okin_7byte.py` | O2 Okin 5A |  | `test_okin_nordic.py` |
| `okin_ore` | `OkinOreController` (`okin_ore`, 458) | inline | D distinct |  | `test_okin_ore.py` |
| `okin_rf_eco_bt` | `OkinRfEcoBtController` (`okin_rf_eco_bt`, 1281) | `okin_uuid.py` | O1 Okin N-frame |  | `test_okin_rf_eco_bt.py` |
| `okin_uuid` | `OkinUuidController` (`okin_uuid`, 3272) | `okin_protocol.py`, `okin_uuid_remotes.py`, `furnimove_profiles.py` | O1 Okin N-frame |  | `test_okin_uuid.py` |
| `omazz_adjusto_iii` | `OmazzAdjustoIIIController` (`omazz_adjusto_iii`, 1184) | `cluster033.py`, `cluster033_profiles.py` | K1 Keeson E5/E6 |  | none direct |
| `qplus_app` | `QPlusAppController` (`sbi`, 1744) | `cluster033.py`, `cluster033_profiles.py` | K1 Keeson E5/E6 |  | `test_sbi.py` |
| `remacro` | `RemacroController` (`remacro`, 1198) | `remacro_protocol.py` | D distinct | jeromes, the_brick | `test_remacro.py` |
| `reverie` | `ReverieController` (`reverie`, 2077) | `reverie_comfort.py`, `reverie_profiles.py` | D distinct |  | `test_reverie.py` |
| `reverie_nightstand` | `ReverieNightstandController` (`reverie_nightstand`, 2573) | `reverie_comfort.py`, `reverie_profiles.py` | D distinct |  | `test_reverie_nightstand.py` |
| `reverie_pairlink` | `ReveriePairlinkController` (`reverie_pairlink`, 10363) | `reverie_pairlink_profile.py`, `reverie_pairlink_protocol.py`, `reverie_pairlink_runtime.py`, `reverie_pairlink_sdk*.py`, `reverie_pairlink_transport.py`, `reverie_comfort.py` | gap (no successful command) |  | `test_reverie_pairlink*.py` |
| `richmat` | `RichmatController` (`richmat`, 1112) | inline | R1 Richmat 6E | nordic, prefix55, prefixaa, wilinke | `test_richmat.py` |
| `richmat_best_mattress` | `RichmatMhController` (`richmat_mh`, 6109) | `richmat_mh_protocol.py`, `richmat_mh_catalog.py` | R1 Richmat 6E | model_bfrm, model_vsrm | `test_richmat_mh.py` |
| `richmat_blvd_home` | `RichmatMhController` (`richmat_mh`, 6109) | `richmat_mh_protocol.py`, `richmat_mh_catalog.py` | R1 Richmat 6E | model_bfrm, model_eorm | `test_richmat_mh.py` |
| `richmat_harmony` | `RichmatMhController` (`richmat_mh`, 6109) | `richmat_mh_protocol.py`, `richmat_mh_catalog.py` | R1 Richmat 6E | model_t3rm, model_utrm | `test_richmat_mh.py` |
| `richmat_idealbed` | `RichmatMhController` (`richmat_mh`, 6109) | `richmat_mh_protocol.py`, `richmat_mh_catalog.py` | R1 Richmat 6E | model_3i, model_p6rm | `test_richmat_mh.py` |
| `richmat_revive` | `RichmatMhController` (`richmat_mh`, 6109) | `richmat_mh_protocol.py`, `richmat_mh_catalog.py` | R1 Richmat 6E | model_vjrm, model_vorm | `test_richmat_mh.py` |
| `rondure` | `RondureController` (`rondure`, 382) | inline | K1 Keeson E5/E6 | both, side_a, side_b | `test_rondure.py` |
| `row_control` | `RowControlController` (`row_control`, 1184) | `cluster033.py`, `cluster033_profiles.py` | K1 Keeson E5/E6 |  | none direct |
| `sbi` | `SBIController` (`sbi`, 1744) | `cluster033.py`, `cluster033_profiles.py` | K1 Keeson E5/E6 | both, side_a, side_b | `test_sbi.py` |
| `scott_living` | `ScottLivingController` (`scott_living`, 460) | inline | K1 Keeson E5/E6 |  | `test_scott_living.py` |
| `serenity` | `SerenityController` (`serenity`, 1883) | `okin_cst.py`, `okin_protocol.py` | O1 Okin N-frame |  | `test_serenity.py` |
| `serta` | `KeesonController` (`keeson`, 2417) | `okin_protocol.py` | K1 Keeson E5/E6 |  | `test_keeson.py` |
| `serta_mp_remote` | `SertaMPRemoteController` (`serta_mp_remote`, 1574) | `cluster033.py`, `cluster033_profiles.py` | K1 Keeson E5/E6 |  | `test_cluster033.py` |
| `simmons` | `SimmonsController` (`simmons`, 1064) | `simmons_protocol.py` | O1 Okin N-frame | simmons_inclined, simmons_inclined_okin, simmons_inclined_smartbed, simmons_okin, simmons_smartbed | `test_simmons.py` |
| `sleep_number` | `SleepNumberController` (`sleep_number`, 3211) | `sleep_number_commands.py`, `sleep_number_auth.py` | D distinct |  | `test_sleep_number.py` |
| `sleep_number_mcr` | `SleepNumberMcrController` (`sleep_number_mcr`, 2079) | `sleep_number_mcr_protocol.py` | D distinct |  | `test_sleep_number_mcr.py` |
| `sleepstar` | `SleepStarController` (`sleepstar`, 1221) | inline | D distinct |  | `test_sleepstar.py` |
| `sleeptracker` | `SleeptrackerController` (`sleeptracker`, 1756) | `sleeptracker_protocol.py` | D distinct (cloud-adjacent) |  | `test_sleeptracker_exposure.py` |
| `sleepys_box15` | `SleepysBox15Controller` (`sleepys`, 507) | inline | K1 Keeson E5/E6 |  | `test_sleepys.py` |
| `sleepys_box24` | `SleepysBox24Controller` (`sleepys`, 507) | inline | D distinct |  | `test_sleepys.py` |
| `sleepys_box25` | `SleepysBox25LegacyController` (`sleepys_box25`, 913) | inline | O1 Okin N-frame | box25_legacy, box25_star | `test_sleepys.py` |
| `sleepys_elite_app` | `SleepysEliteAppController` (`sleepys_app`, 6918) | `sleepys_app_routes.py` | D distinct |  | `test_sleepys_elite_app.py` |
| `solace` | `SolaceController` (`solace`, 1143) | inline | S1 FFFF frame | woosa | `test_solace.py` |
| `star_elevate` | `StarElevateController` (`star_elevate`, 794) | `starcode_accessory_group.py` | O2 Okin 5A | adjustable_comfort_m1x12 | `test_star_elevate.py` |
| `starcode_abm5_4` | `StarcodeAbm5_4Controller` (`starcode_abm5_4`, 1735) | `starcode_abm5_4_profiles.py` | O1 Okin N-frame |  | `test_starcode_abm5_4.py` |
| `starcode_m1x12` | `StarcodeM1X12Controller` (`starcode_m1x12`, 2507) | `star_elevate.py`, `starcode_m1x12_protocol.py`, `starcode_accessory_group.py` | O1 Okin N-frame (partial: motion and presets) |  | `test_starcode_m1x12.py` |
| `starcode_m5x5` | `StarcodeM5X5Controller` (`starcode_m5x5`, 1685) | `starcode_m5x5_protocol.py`, `starcode_accessory_group.py` | O1 Okin N-frame (partial: motion and presets) |  | `test_starcode_m5x5.py` |
| `suta` | `SutaController` (`suta`, 542) | inline | D distinct |  | `test_suta.py` |
| `svane` | `SvaneController` (`svane`, 1018) | `svane_state.py` | D distinct | jensen_linon, svane_remote_jmc | `test_svane.py` |
| `tempur_au` | `TempurAUController` (`tempur_au`, 1184) | `cluster033.py`, `cluster033_profiles.py` | K1 Keeson E5/E6 |  | none direct |
| `tempur_curve` | `TempurCurveController` (`tempur_curve`, 1184) | `cluster033.py`, `cluster033_profiles.py` | K1 Keeson E5/E6 |  | none direct |
| `timotion_ahf` | `TiMOTIONAhfController` (`timotion_ahf`, 714) | inline | D distinct |  | `test_timotion_ahf.py` |
| `tranquil` | `TranquilController` (`serenity`, 1883) | `okin_cst.py`, `okin_protocol.py` | O1 Okin N-frame |  | `test_serenity.py` |
| `vibradorm` | `VibradormController` (`vibradorm`, 1163) | inline | D distinct |  | `test_vibradorm.py` |
| `vibradorm_app` | `VibradormAppController` (`vibradorm_app`, 1983) | `vibradorm_app_state.py`, `vibradorm_vmat_profiles.py`, `vibradorm_vmat_setup.py` | D distinct |  | `test_vibradorm_app.py` |
| `vmatbasic` | `VMatBasicController` (`vmatbasic`, 1024) | `vmatbasic_protocol.py` | D distinct |  | `test_vmatbasic.py` |

### Config keys and APK reports

Owned keys are the `CONF_*` values the controller, its helper modules or its
`controller_factory.py` branch read (including the factory's `octo_pin`,
`jensen_pin`, `richmat_remote`, `rmcontrol_*` and `cb24_bed_selection` arguments,
and the Malouf layout settings read through coordinator properties). Fields every
bed shares are left out: `has_massage`, `has_light`, `reverse_motor_1` to `4`,
`protocol_variant`, `bed_type`, `side`, the bond marker and the timing and adapter
options.

APK status letters: `C` = workspace report `COMPLETE`, `P` = `PARTIAL`, `B` = `BLOCKED`.
The status is the `status` field of the frozen `analysis.json` in the machine-local
report workspace; **acceptance** is tracked in #447/#436 and is not claimed here.
"ledger rowNNN" names a disposition ledger under `docs/apk-analysis/dispositions/`
with no matching workspace report. Package versions are taken from workspace names.
No report content is copied here.

| Bed type | Owned config keys (CONF_*, beyond the generic fields) | APK report(s): package, version, workspace status |
|---|---|---|
| `adjustable_lumbar` | `ble_device_name` | com.okin.bedding.adjustablelumbar 1.2.2 C |
| `adjustamattress` | `ble_device_name` | ledger row067 |
| `bedsense` | `ble_device_name` | com.fenmenbielei.bedsense 1.8 C |
| `bedtech` |  | com.richmat.bed_tech 2.8.3 P |
| `bf` |  | com.BF 1.2.3 C |
| `casper_base` |  | com.richmat.casperbase 1.0.8 P |
| `casper_remote` |  | com.richmat.casperbase P |
| `casper_sleep_mm` |  | com.richmat.casperbase P |
| `casper_sleep_sxb` |  | com.richmat.casperbase P |
| `cherish` |  | com.okin.ore.cherish 1.0.4 C |
| `comfort_enhancements` |  | com.okin.enhancements 1.0.3 C |
| `comfort_motion` |  | com.jiecang.app.android.jiecangbed 2.2.1 P (via row115) |
| `coolbase` |  | com.keeson.coolbase 1.0.0 C |
| `customatic_clarity` |  | com.okin.bedding.customaticclarity 1.0.1 C |
| `customatic_jeromes` |  | com.okin.bedding.customaticjeromes 1.0.1 C |
| `customatic_remedy` |  | com.okin.bedding.customaticremedy 1.0.1 C |
| `customatic_zseries` | `zseries_alarm_available` | com.okin.bedding.glory 1.0.4 C |
| `dewertokin` |  | none |
| `doublesleep` | `device_id`, `ble_device_name`, `product_type` | com.okin.doublesleep 1.2.24 P |
| `ergo_slim` | `product_type` | com.sfd.slim 1.3 C |
| `ergomotion` |  | com.sfd.ergomotion 1.6.4 C |
| `ergomotion_4` | `product_type`, `ergomotion4_product_name`, `ergomotion4_model_keys`, `ergomotion4_massage_keys`, `ergomotion4_rgb` | com.sfd.hump 3.7 C |
| `ergomotion_app` | `product_type` | com.sfd.ergomotion 1.6.4 C |
| `eshine` |  | com.richmat.eshinesleep 1.0.1 C |
| `fsm_relax` | `fsm_relax_memory_names`, `product_type` | com.limoss.fsmrelax 1.9 C |
| `furnimove` | `furnimove_remote` | ledger 157 (no frozen analysis.json) |
| `glideaway_motion` |  | com.ore.bedding.glideawaymontion 1.0.3 C |
| `gmmotor` | `gmmotor_side`, `product_type` | com.desarketing.gmmotor 4.6.6 P |
| `gmmotor_sleep_mm` |  | com.desarketing.gmmotor 4.6.6 P |
| `gmmotor_sleep_sxb` |  | com.desarketing.gmmotor 4.6.6 P |
| `hjbed` |  | ledger row121 |
| `isleep` | `kaidi_room_id`, `kaidi_sofa_acu_no`, `product_type` | com.kaidi_test4 1.6.3 C |
| `jensen` | `jensen_pin` | air.no.jensen.adjustablesleep 2.0.29/2.0.37 C |
| `jiecang` |  | com.jiecang.app.android.jiecangbed 2.2.1 P |
| `jiecang_app` | `jiecang_app_layout`, `jiecang_app_profile`, `jiecang_app_transport` | dreamask 1.0.8 C, dreamotion 1.0.5 C, dreamhd 1.0.4 C, jiecangbed 2.2.1 P |
| `kaidi` | `kaidi_adv_type`, `kaidi_product_id`, `kaidi_resolved_variant`, `kaidi_room_id`, `kaidi_sofa_acu_no`, `kaidi_target_vaddr`, `kaidi_variant_source` | com.kaidi_test4 1.6.3 C; .floyd 1.0.7 P |
| `keeson` |  | see Keeson routes |
| `leggett_gen2` |  | com.leggett.android.universal 2.9.0 C |
| `leggett_lp_legacy` | `lp_legacy_mode`, `lp_legacy_model`, `lp_legacy_read_uuid`, `lp_legacy_write_uuid` | com.richmat.lp 2.2.1 C |
| `leggett_okin` | `leggett_app_profile` | com.leggett.prodigy2 2.2.0, prodigy2L 1.2, prodigy4 1.2.0, useries 2.1 (all C) |
| `leggett_platt` | `leggett_app_profile` | com.leggett.android.universal 2.9.0 C; com.richmat.lp 2.2.1 C; lp2 2.3.25 C |
| `leggett_wilinke` |  | com.richmat.lp2 2.3.25 C |
| `limoss` |  | com.limoss.limossremote 7.1.8 C |
| `limoss_remote` | `limoss_remote_state`, `limoss_remote_theme`, `product_type` | com.limoss.limossremote 7.1.8 C |
| `linak` |  | com.linak.bedconnect.iot 5.2.4, .leggettandplatt 1.0, .linakbed.ble.memory 6.0.9 (all C) |
| `logicdata` |  | none |
| `logicdata_air_pump` |  | com.logicdata.app.mattress.bed 1.0.0 C (row053) |
| `logicdata_app` | `logicdata_app_family`, `logicdata_app_layout`, `logicdata_app_profile`, `logicdata_app_transport` | com.logicdata.app.android.bed 1.0.6 C, .pad.bed 1.0.4 C, .mattress.bed 1.0.0 C |
| `malouf_app` | `malouf_app_model`, `malouf_app_primary`, `malouf_app_profile`, `malouf_app_transport` | com.lucid.bedbase 1.3.3 C, com.malouf.bedbase 2.4.3 C |
| `malouf_legacy_okin` | `malouf_layout`, `malouf_memory_slots` | com.malouf.bedbase 2.4.3 C |
| `malouf_new_okin` | `malouf_layout`, `malouf_memory_slots` | com.lucid.bedbase 1.3.3 C |
| `mattressfirm` |  | com.okin.bedding.rizemf900 1.1.2 C |
| `motion_bed` | `ble_device_name`, `motion_bed_movement`, `motion_bed_preset`, `motion_bed_restored` | com.sn.blackdianqi 1.24 C (ledger 032) |
| `motosleep` |  | com.HHC.MotoMotion 3.1.9 B |
| `nectar` |  | com.okin.bedding.nectarmotion 1.0.1 C |
| `octo` | `octo_motor_count_override`, `octo_pin` | de.octoactuators.octosmartcontrolapp 1.03.02 C |
| `okimat` |  | com.okin.bedding.glory/support/rizeResident (C), smartbedwifi 2.4.2 P |
| `okin_64bit` |  | none |
| `okin_7byte` |  | none |
| `okin_cb24` | `cb24_bed_selection` | none |
| `okin_cb35` |  | com.okin.sealy 1.1.3 P |
| `okin_cst` |  | com.okin.bedding.rize* (7 apps), support, mf900 (all C) |
| `okin_dot` |  | none |
| `okin_ffe` |  | none |
| `okin_handle` |  | none (FurniMove backend) |
| `okin_nordic` |  | none |
| `okin_ore` |  | none |
| `okin_rf_eco_bt` |  | none |
| `okin_uuid` |  | none |
| `omazz_adjusto_iii` | `product_type` | com.sfd.Omazz 1.0.5 C |
| `qplus_app` | `product_type` | com.sbi.costco 1.8 C |
| `remacro` | `remacro_led_level`, `remacro_model` | com.cheers.brick/jewmes/slumber (C) |
| `reverie` |  | com.reverie.reverie 3.3.3.8 C |
| `reverie_nightstand` |  | none |
| `reverie_pairlink` | `pairlink_role`, `pairlink_host_source`, `pairlink_home_id`, `pairlink_password_text`, `pairlink_password_hex` | none |
| `richmat` | `richmat_remote`, `rmcontrol_product`, `rmcontrol_side` | com.richmat.rmcontrol2 21.3.7 C and others |
| `richmat_best_mattress` | `ble_device_name` | com.richmat.best_mattress 1.1.1 C |
| `richmat_blvd_home` | `ble_device_name` | com.richmat.blvd_home 1.0.1 C |
| `richmat_harmony` | `ble_device_name` | com.richmat.harmony 1.0.0 P |
| `richmat_idealbed` | `ble_device_name` | com.richmat.idealbed 2.4.2 C |
| `richmat_revive` | `ble_device_name` | com.richmat.revive3 1.0.26 C |
| `rondure` |  | none |
| `row_control` | `product_type` | com.sfd.row 2.0 C |
| `sbi` |  | com.sbi.costco 1.8 C |
| `scott_living` |  | none |
| `serenity` | `zseries_alarm_available` | com.okin.bedding.serenity 1.0.1 C |
| `serta` |  | com.ore.serta330 1.1 C |
| `serta_mp_remote` | `product_type` | com.ore.serta330 1.1 C |
| `simmons` | `ble_device_name` | com.okin.simmons 1.12.9 C |
| `sleep_number` |  | com.selectcomfort.SleepIQ 5.4.11 P |
| `sleep_number_mcr` | `sleep_number_mcr_client_id` | none |
| `sleepstar` |  | none |
| `sleeptracker` | `product_type`, `sleeptracker_foundation`, `sleeptracker_processor_type`, `sleeptracker_restricted`, `sleeptracker_snapshot_side`, `sleeptracker_unit_number` | com.fullpower.applications.horizon 3.6.2 (addenda only) |
| `sleepys_box15` |  | none |
| `sleepys_box24` |  | none |
| `sleepys_box25` |  | com.okin.bedding.sleepy 1.1.5 P/C |
| `sleepys_elite_app` | `sleepys_elite_selector` | com.okin.bedding.sleepy 1.1.5 P/C (row003) |
| `solace` |  | com.sealy.motionflex 1.0.3, com.ly.homekobo 1.4, com.sn.dianqi 1.0.6, com.sn.woosa 1.1.9 (all C) |
| `star_elevate` | `device_id`, `starcode_lift_entries`, `starcode_m1x12_profile`, `starcode_m5x5_profile` | com.starcode.abm5_5, .adjustablem1x12 |
| `starcode_abm5_4` | `ble_device_name`, `starcode_abm5_4_command_selector`, `starcode_abm5_4_transport_selector`, `starcode_abm5_4_ui_selector` | com.starcode.abm5_4 1.0.1 C |
| `starcode_m1x12` | `device_id`, `starcode_lift_entries`, `starcode_m1x12_profile`, `starcode_m5x5_profile`, `ble_device_name` | com.starcode.adjustablem1x12 1.1.3 C |
| `starcode_m5x5` | `device_id`, `starcode_lift_entries`, `starcode_m1x12_profile`, `starcode_m5x5_profile`, `ble_device_name` | com.starcode.abm5_5 1.2.3 C |
| `suta` |  | com.intretech.app.suta 1.0.3 (no frozen analysis.json) |
| `svane` |  | com.svane.svaneremote 1.8 C |
| `tempur_au` | `product_type` | com.sfd.tempur_au 1.6 C |
| `tempur_curve` | `product_type` | com.ore.tempur 1.7 C |
| `timotion_ahf` |  | com.timotion.ahf 1.0.4 C |
| `tranquil` | `zseries_alarm_available` | com.okin.bedding.tranquil 1.0.2 C |
| `vibradorm` |  | de.vibradorm.vmat 1.11 C |
| `vibradorm_app` | `vibradorm_app_profile`, `vibradorm_control_type`, `vibradorm_floor_default`, `vibradorm_floor_light`, `vibradorm_light_extension`, `vibradorm_restored`, `vibradorm_rgb`, `vibradorm_vmat_remote` | de.vibradorm.diamant 0.3, .werkmeister 0.2 (C) |
| `vmatbasic` | `vmatbasic_floor_level`, `vmatbasic_floor_minutes`, `vmatbasic_profile` | com.vibradorm.vmatbasic 2.4.3 C |

### Keeson routes and APK reports

| Keeson route | Package, version, status | Test carrying the app vectors |
| --- | --- | --- |
| `adjustable_lite` | `com.keeson.adjustablelite` 1.0.2 C | `test_keeson_adjustable_lite.py` |
| `restonic_a`, `restonic_b` | `com.keeson.restonicBT` 1.2.0 C | `test_keeson_restonic.py` |
| `innova` | `com.ore.sfm` 2.0 C | `test_innova.py` |
| `bedsense_bases` | `com.ore.sfmc2bedsence` 1.1 C | `test_innova.py` |
| `avanti_bases` | `com.ore.AvantiBases` 1.0.5 C | `test_avanti_bases.py` |
| `dynasty_bases`, `maxcoil_una`, `americanstar` | `com.ore.Dynasty` 1.0.2, `com.ore.maxcoil` 1.1.0, `com.ore.americanstar` 1.0 (all C) | `test_ore_comfort_bed.py` |
| `simon_li`, `heal_every_night`, `okin_seating` | `com.okin.simon` 1.0.1, `com.okin.healeverynight` 1.0, `com.okin.minghua.R` 1.0.1 (all C) | `test_keeson_okin_apps.py` |

Other reports whose package id appears in a test: `com.fenmenbielei.bedsense`
(`test_bedsense.py`), `com.okin.enhancements` (`test_comfort_enhancements.py`),
`com.keeson.coolbase` (`test_coolbase.py`), `com.cheers.*` (`test_remacro.py`),
`air.no.jensen.adjustablesleep` (`test_jensen.py`, `test_jensen_linon.py`),
`com.starcode.abm5_4` (`starcode_abm5_4_vectors.py`). Most other reports carry their
vectors in a bed-named test or a `tests/fixtures/` vector file. The wire snapshot
pins what the command plan reaches for each bed type and route, within the limits
in [Coverage gaps](#coverage-gaps); it does not replace those vector tests.

### Routes with their own controller class

| Route | Controller class | Frame family |
| --- | --- | --- |
| `keeson:americanstar`, `avanti_bases`, `bedsense_bases`, `dynasty_bases`, `maxcoil_una` | `OreComfortBedController` | K1 class D (ORE bases) |
| `keeson:heal_every_night`, `okin_seating`, `simon_li` | `OkinAppKeesonController` | K1 (`heal_every_night` shares a class with `sino`; `okin_seating` with `simon_li`) |
| `keeson:innova` | `InnovaController` | K1 class A (Keeson mask) |
| `leggett_platt:gen2`, `:mlrm` | `LeggettGen2Controller`, `LeggettWilinkeController` | distinct, R1 |
| `octo:star2` | `OctoStar2Controller` | distinct |
| `sleepys_box25:box25_star` | `SleepysBox25Controller` | O2 |
| `solace:woosa` | `WoosaController` | S1 |
| `star_elevate:adjustable_comfort_m1x12` | `StarElevateM1X12Controller` | O2 |
| `svane:jensen_linon` | `JensenLinonController` | distinct |
| `kaidi:floyd` | `FloydController` | distinct (Kaidi mesh) |

## Proposed #745 migration order

Order weighs duplicated implementations against users (README status and issue
labels as proxies: `okin` 47, `richmat` 13, `octo` 10, `solace` 10, `leggett` 9,
`keeson` 9, `vibradorm` 8, `okimat`/`bedtech`/`motosleep` 7, `malouf`/`reverie` 6,
`linak` 5, `kaidi` 5, `jiecang` 4, `logicdata` 2, `limoss` 2). A family that
needs more than one PR gets its own sub-issue.

- [ ] **0. J1 Jiecang** (#744 pilot): `jiecang`, `comfort_motion`, `jiecang_app` (DreamAsk, Dreamotion, DreamHD, Comfort Motion). Resolves the Comfort Motion double route.
- [ ] **1. J1 LOGICDATA** (first #745 family): `logicdata_app` (phone, tablet, Sleep Smart) onto the Jiecang codec. Same frame and transports as J1; small, no new users at risk; proves the codec on a second profile set. `logicdata` (legacy 13-byte) and `logicdata_air_pump` stay standalone.
- [ ] **2. K1 Keeson E5/E6** (23 bed types, largest verified duplication, stateless): sub-PRs for (a) core `KeesonController` variants and the alias bed types `ergomotion`, `serta`, `okin_ffe`; (b) cluster033 apps (already one base class, so mostly a codec move); (c) the E6 9-byte group `adjustamattress`, `glideaway_motion`, `malouf_legacy_okin`, `sleepys_box15`, `scott_living`, Simmons Okin; (d) `sbi`, `rondure`, `coolbase`, `bf`, `cherish`, `comfort_enhancements`, `furnimove`.
- [ ] **3. O1 Okin N-frame** (22 bed types, most users): one sub-issue, PRs per command word width: 32-bit (`okimat`/`okin_uuid`, `dewertokin`/`okin_handle`, `customatic_*`, `leggett_okin`, `okin_rf_eco_bt`), 40-bit (`okin_cb24`, `simmons`, `doublesleep`, `sleepys_box25`, `starcode_abm5_4`, `okin_dot`, and the motion and preset frames of Starcode M1X12/M5X5), 96-bit (`okin_cst`, `serenity`, `tranquil`, `customatic_zseries`), 64-bit (`okin_64bit`, `adjustable_lumbar`). Keep sessions, bonds and DoubleSleep state in profile controllers.
- [ ] **4. R1 Richmat 6E** (`richmat`, `bedtech`, `leggett_wilinke`, `hjbed`, `richmat_mh` apps, the 6E frames of `gmmotor`): the Richmat MH catalogs stay data; `hjbed` and `gmmotor` sessions stay controller code.
- [ ] **5. S1 FFFF** (`solace`/`woosa`, `bedsense`, `motion_bed`): identify the trailer algorithm first (not done here).
- [ ] **6. O2 Okin 5A** (`okin_7byte`/`nectar`, `okin_nordic`/`mattressfirm`, `okin_cb35`, `star_elevate`, `sleepys_box25` star). `malouf_new_okin` and `malouf_app` share one Okin-like frame with an extra byte (equal motor frames); decide there whether it is an O1 variant or its own codec.
- [ ] **7. L1 Limoss DD** (`limoss`, `limoss_remote`, `fsm_relax`): three controllers, low user count; `limoss_remote` needs a replying session to capture beyond its handshake and STOP frames.
- [ ] **8. Standalone with a recorded reason** (no shared frame): `linak`, `octo`, `sleep_number` and `_mcr`, `reverie`, `_nightstand` and `_pairlink`, `vibradorm` family, `kaidi`/`isleep`/`floyd`, `svane`/`jensen` (the JMC route shares Jensen's motor frames), `sleeptracker`, GM Control, Casper, `suta`, `sleepstar`, `timotion_ahf`, `motosleep`, `remacro`, `eshine`, `okin_ore`/`sleepys_box24`, `leggett_gen2`/`lp_legacy`, `logicdata`, `logicdata_air_pump`, `sleepys_elite_app`, and the non-motion frames of Starcode M5X5/M1X12.

Families 2 and 3 likely carry most of the line-count reduction; families 0 and 1
carry the smallest regression surface.

## How the proof was produced

`scripts/wire_snapshot.py` builds every `SUPPORTED_BED_TYPES` entry through
`create_controller`, plus protocol-variant and app-profile routes, on its own
coordinator stub (the real per-bed pulse defaults from `get_motor_pulse_defaults`,
`has_massage` on, two motors) and a recording client. It replays the
coordinator's post-connect hooks (capability discovery, notifications, the Octo,
Jensen and Sleep Number startup calls), then drives a command plan:

- motors up/down/stop on all ten axes, `stop_all`, flat, zero-g, anti-snore, TV,
  memory recall and program for slot 1, lights toggle/on/off, massage toggle/off
  (the original plan, in its original order);
- every further memory slot up to `memory_slot_count` and held recall per slot;
- each cover the integration creates, through its `motor_control_specs` callables;
- every other no-argument `BedController` action the controller implements;
- one call of each implemented action that takes arguments, with arguments taken
  from the controller's own options: every light level (when the range spans at
  most 20 steps, otherwise both bounds, their neighbours and the middle three), a light colour,
  each light and massage timer option, each massage intensity per zone, fan
  levels, sleep and alarm timers, each motor position slider at mid travel, each
  held control and preset, sync, locks, automatic drive and light, RMControl
  alarm and anti-snore settings, Solace audio, calibration and rename;
- every controller-declared button, each option of every controller select, and
  both bounds of every controller number;
- a STOP pressed 0.3 s into each cover movement, as `async_stop_command` does it:
  bump the cancel counter, set `cancel_command`, let the movement's cleanup finish,
  then send `stop_all`.

Not driven: base actions that take controller-specific request or schedule
objects (`async_execute_*_request`, `async_execute_*_action`,
`async_perform_casper_base_action`, `configure_clock_alarm`,
`configure_alarm_table_schedule`, `program_alarm`, `program_solace_alarm`,
`floyd_action`, `richmat_mh_*` alarms and aroma, `rmcontrol_repeat_alarm`,
`set_motion_bed_surface`, `async_execute_sleep_number_command`) and
`seek_position_step`. Most of those products expose the same frames through the
controller-declared buttons above.

Each event records the characteristic, kind (the write `response` flag, or
`notify`, `unnotify`, `read`, `pair`), bytes, order and virtual time offset. All
timing is virtual: `sleep`, `wait`, `wait_for`, `timeout`, `timeout_at`, the loop
clock and `call_later` run on a fake clock that advances only once runnable work
is quiet, and wall-clock time follows it. Any command still running after 50 s of
virtual time is released, as if the user let go (no bounded preset or recall runs
that long: the longest, `okin_uuid` flat, is 100 x 307 ms), and one still running
after 60 s is recorded as `timeout` (none does). Every stubbed write takes a fixed 7 ms so pacing that
absorbs write latency differs from pacing that adds to it. After the last command
the clock runs 2 s more; events from a task started in an earlier phase are
recorded under `background`. Query callbacks run against the constructed
controller, `random` and `secrets` are seeded per scenario, and HA's Bluetooth
history reads as empty.

A few sessions get scripted replies so they really run: the TiMOTION status
frame, Kaidi and iSleep room join and node ping answers (with a provisioned
Kaidi advertisement, product 139 for Floyd), the Sleep Number Auth session read
and Svane raw axis reads. `limoss_remote` starts from stored capabilities (a
4-motor bed with vibration and two memory slots), as after an earlier handshake.

Optional hardware the factory reads from the config entry has its own routes
(`:massage_light` for `logicdata_app`, `limoss_remote` and `fsm_relax`, and
`vibradorm_app:caresse_restored` with massage, RGB, floor light and light
extension); the default scenarios keep the integration's defaults.

Each scenario replays a hand-maintained fake GATT layout from
`tests/fixtures/wire_snapshot_layouts.json` (a route can reuse another scenario's
through `layout_id`), so renaming a UUID constant changes nothing; a new scenario
needs a layout there. The layouts advertise both write modes on every
characteristic, as the real-device fixtures in the controller tests do. For the 26
controllers that choose their write mode or write characteristic from the
properties, `:props_write` and `:props_wwr` routes replay the same layout with
only acknowledged writes or only writes without response, so every property
branch is pinned. Five of them refuse a characteristic without acknowledged
writes (`casper_base`, `comfort_enhancements`, `eshine`, `hjbed`,
`keeson:simon_li`); that refusal is pinned as well.

`tests/test_wire_snapshot.py` runs `scripts/wire_snapshot.py --check` in its own
process. The capture uses `PYTHONHASHSEED=0`, and the check also captures with a
second seed and fails on any difference outside an explicit allowlist. The list
holds only the two Svane two-axis holds: `SvaneController` releases them by
iterating a set, so their release order changes between processes. A second test
covers the virtual clock.

What the guard proves: on every path the plan reaches, a change to bytes,
characteristic, write mode, subscriptions, reads, order or relative timing fails
it, deterministically, except where the second-seed allowlist applies. What it
does not prove: behavior behind a coverage gap, paths the plan does not drive
(above), cover-level hold loops and paired coordinators, and protocol replies
other than the scripted ones.

For #744 and #745: a refactor that only moves code must leave the snapshot
untouched. A deliberate byte change regenerates it in the same PR so the diff is
reviewed. The #744 pilot does exactly that for one intended change: legacy Jiecang
now releases at the STOP press (300 ms) instead of at the next refresh slot
(342 ms), in the `stop:` steps of `jiecang` and `comfort_motion`; nothing else
moves.

Family tests in this document were computed from the snapshot: frame rules by
checking every captured write run (the counts in the family table), core classes by
byte equality of motor and STOP commands, aliases by equality of every command
including timing.

### Coverage gaps

A gap is a command the controller declares (through a capability property, a
motor spec or a controller entity spec) that does not succeed in the capture. The
scenario lists them under `info.gaps`; every event they recorded stays pinned.

| Scenario | Gaps | Why |
| --- | ---: | --- |
| `casper_remote`, `casper_sleep_mm`, `casper_sleep_sxb` (and its property routes), `gmmotor_sleep_mm` | 0 to 3 | remote or sleep-sensor entries with no bed commands; nothing succeeds |
| `richmat_*` Richmat MH bed types in their `auto` form | 0 (connect fails) | the app needs a known advertised name; covered through the `model_*` routes |
| `sleep_number` | 32 | the encrypted session needs replies the capture does not script (Auth read, subscriptions and the first request are pinned) |
| `sleep_number_mcr`, `limoss_remote` (and `:massage_light`), `fsm_relax` (and `:massage_light`) | 9, 7, 2 | handshake replies are not scripted; the handshake and request frames they send are pinned. `limoss_remote` holds, lights and massage are captured from its stored capabilities; its memory needs a saved slot |
| `sleeptracker` | 23 | its hello/auth/control GATT path is not in the stored layout |
| `reverie_pairlink` | 7 | needs its Pairlink runtime and reported massage state |
| `jensen` (and its property routes) | 10 | memory recall needs a saved slot; programming and position targets wait for a position reply |
| `svane` (and its property routes), `svane:svane_remote_jmc` | 1, 2 | memory recall needs a saved slot (`svane`); the JMC route rejects the scripted position read |
| `comfort_enhancements:props_wwr`, `eshine:props_wwr`, `hjbed:props_wwr`, `keeson:simon_li:props_wwr`, `casper_base:props_wwr` | 0 to 57 | these controllers need acknowledged writes and refuse a write-without-response-only characteristic; the refusal is the pinned behavior |
| `isleep` | 1 | enrollment needs a live unprovisioned advertisement |
| state the bed has not reported: `octo`, `octo:standard`, `jiecang_app` (13 scenarios) light toggle; `reverie_nightstand` light levels; `bedsense` (10 scenarios and both property routes), `solace:woosa` memory recall; `cherish`, `keeson:heal_every_night` massage levels; `motion_bed` audio buttons | 1 to 7 | the controller refuses until the bed reports the state; no notification in the capture supplies it |
| `vibradorm_app:caresse_restored` | 11 | massage actions wait for the app's automatic or individual mode, which no notification sets |
| `furnimove` (and its property routes), `comfort_enhancements:mc3`, `sleepys_elite_app` | 8, 4, 2 | the default handset or product has no massage, although the massage flags are set |
| `leggett_okin`, `leggett_platt`, `leggett_platt:okin` | 1 | press-and-hold mode selection is deliberately disabled for Prodigy CE |

`doublesleep:p3` (the sensor driver) has no motor control by design, so it is
not a gap. `keeson` in its `auto` form resolves to the JSON variant (the variant
routes cover the rest). Remote-code tables (`richmat_remote`), cluster033
product layouts, Okimat remote codes beyond the default and Casper/AdjustaMattress
product sets are sampled, not exhaustive.

## Observations (not fixed here)

- `JiecangController` defines the 4-motor and split-bed literals (`HEAD_UP_ALT`,
  `WAIST_*`, `BACK_RIGHT_*`) but its motor methods never emit them, so a 3 or
  4-motor Jiecang bed cannot use head/lumbar/neck through the legacy route. The
  `jiecang_app` profile layouts do.
- `logicdata_app` sends 11 pulses per movement where `jiecang_app` sends 10 at the
  same interval. Probably per-app, to be proven from the frozen reports before any
  change.
- `simmons` emits two wire families from one controller (E6 and `05 02`); `sleepys_box25` splits O1 (legacy route) and O2 (star route) across two controller classes.
- `keeson` has four controller classes behind one bed type; the `OreComfortBed`,
  `OkinAppKeeson` and `Innova` routes also have their own README rows.
- BedSense, Solace/Woosa and Motion Bed share one frame; three controllers and
  three guides describe it.
- Frozen report workspaces for `com.dewertokin.okinsmartcomfort`,
  `com.intretech.app.suta`, and `com.fullpower.applications.horizon` carry no
  `report/analysis.json` at the top level, so no status is listed for them.
- `SvaneController` releases a two-axis hold (`hold_head_up_feet_down`,
  `hold_head_down_feet_up`) by iterating a set of roles, so which axis gets its
  release frame first changes between Python processes. The snapshot pins it by
  running with `PYTHONHASHSEED=0`.
- Starcode M1X12 and M5X5 send Okin `05 02` 40-bit frames for motion and presets,
  with the same motor and STOP frames as the `okin_cb24` class.
- `malouf_app` and `malouf_new_okin` send the same motor and STOP frames.
- `furnimove`, `comfort_enhancements:mc3` and `sleepys_elite_app` declare massage
  controls their default handset or product rejects.
- Before the #744 pilot, a STOP during a legacy Jiecang move released at the next
  57 ms refresh slot (342 ms for a STOP at 300 ms); the pilot releases at once.
