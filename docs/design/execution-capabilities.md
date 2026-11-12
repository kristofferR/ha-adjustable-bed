# Execution capabilities: held motion, concurrent motors and motor speed

Research and design for #516 (concurrent motors), #483 (continuous hold) and
#591 (native motor speed), part of the v5 protocol split (#742). It records,
for every supported bed type and route, what accepted evidence proves about
each capability, then proposes where the capability is declared and how the
scheduler uses it.

State described: `v5` at `439a5d33`. No integration code changed and no new
APK analysis was started. Evidence was read only from the accepted APK
Protocol Audit report workspaces, the disposition ledgers, the bed and codec
guides, the frozen vectors and the issues with their comments.

## Summary

Totals count matrix rows: one per bed type, or per route or app profile where
the evidence differs. There are 113 rows covering all 120 `SUPPORTED_BED_TYPES`.

| Capability | Supported | Unsupported | Blocked |
| --- | ---: | ---: | ---: |
| #483 hold until release | 79 (70 stream, 3 stream without a release frame, 6 latched) | 2 | 32 |
| #516 concurrent motors | 5 | 71 | 37 |
| #591 native motor speed | 0 | 78 | 35 |

Rolled up by bed type (a bed type counts as supported when any route is, and as
blocked when no route is supported and any route is blocked): hold 80 supported
(4 of them also have a blocked route), 9 unsupported, 31 blocked; concurrent 6
supported (2 of them also have a blocked route), 76 unsupported, 38 blocked;
speed 0 supported, 82 unsupported, 38 blocked.

- **#516 candidates:** the Prodigy CE and U Series profiles of `leggett_okin`
  and `leggett_platt`, `customatic_clarity`, `customatic_jeromes`, `customatic_remedy`, and `svane`
  (both Svane Remote routes: P1 and the `JMC`-named P2 route, which this
  matrix once listed with the Jensen app).
- **#483:** almost every accepted app streams a held key at a fixed cadence until
  release. The capability is real and broad. The open questions are the
  surface and the dead-man bound, not the evidence.
- **#591:** no accepted evidence shows a selectable motor speed. Recommend an
  explicit deferral, as #591 allows, instead of an empty abstraction.

## Disposition rules

Nothing is inferred by analogy with another protocol, another app of the same
family, or a shared codec. A disposition rests on the evidence cited in its own
row.

| Code | #483 hold | #516 concurrent | #591 speed |
| --- | --- | --- | --- |
| **S stream** | The app refreshes a held frame with no fixed count until release, then sends the cited release frames | | |
| **S stream (no release frame)** | Same, but the app's only release is ending the refresh. Hardware auto-stop is not proven | | |
| **S latched** | The app sends one start frame and an explicit stop at release | | |
| **S** | | The app holds two independent axes in one time window (one composed frame or interleaved per-axis frames), releases one without stopping the other, and has a bed-wide STOP | The app selects a motor speed for movement |
| **U** | The bed has no motor axis | A complete accepted report exhausts the app's movement paths and none holds two independent axes. Only new hardware evidence could change this | The complete command inventory has no motor-speed selection |
| **B** | The accepted evidence is missing or incomplete; the row names the gap | Same | Same |

A report's status is the `status` of the frozen `analysis.json` in the latest
non-rejected workspace (see [Evidence keys](#evidence-keys)). Acceptance is
tracked in #447 and in the machine-local disposition ledgers. A later scoped-repair workspace
that froze `PARTIAL` (Ergo Slim, Tempur AU) does not downgrade its accepted base
report; cluster033 acceptance is recorded in #447. The accepted Leggett Prodigy
CE and U Series reports live in `report/final/` and `final-report/`, as the
Leggett app ledger records; the July Prodigy
CE build is a different artifact and is not used.

## Evidence matrix

Evidence keys resolve in [Evidence keys](#evidence-keys).

| Bed type (route) | #483 hold | #516 concurrent | #591 speed | Evidence | Notes |
|---|---|---|---|---|---|
| **Okin N-frame (O1)** | | | | | |
| `leggett_okin`, `leggett_platt` (Prodigy CE, U Series) | S stream | S | U | p4, useries, leggett-disp, #368, #516c, #483c | held keys OR into one word, release removes one key; four zero frames; CU170 watchdog measured on hardware |
| `leggett_okin`, `leggett_platt` (Prodigy 2) | S stream | B | U | p2, leggett-disp | blocked by evidence (rechecked): the report says multiple active keys are ORed, but its only release is the zero word; per-key release while another key stays held is not stated |
| `leggett_okin`, `leggett_platt` (Prodigy 2L) | S stream | B | U | p2l, leggett-disp | blocked by evidence (rechecked): the report never states that held keys compose, and its release sets key zero |
| `leggett_platt` (`okin`) | S stream (no release frame) | U | U | universal | okin six-byte key route: refresh ends the hold, no per-axis or global STOP |
| `customatic_clarity` | S stream | S | U | clarity, row028 | shared OR mask; partial release keeps the reduced mask; hold and concurrent (back, legs) declared |
| `customatic_jeromes` | S stream | S | U | jeromes, row028 | same; hold and concurrent (back, legs) declared |
| `customatic_remedy` | S stream | S | U | remedy, row028 | same, including lumbar; hold and concurrent (back, legs, lumbar) declared |
| `okin_cst` (all routes) | S stream | U | U | resident, sanctuary, aviada, bob, contempo, carefree, iiclarity, mf900, support | only recognized masks; motor chords never composed |
| `okimat` | S stream | U | U | glory, support, resident | same apps as Okin CST; see observation 3 |
| `customatic_zseries` | S stream | U | U | glory | recognized masks only |
| `serenity` | S stream | U | U | serenity | remaining bitmask restarts a recognized command or is ignored |
| `tranquil` | S stream | U | U | tranquil | recognized masks only |
| `adjustable_bed` (unit087) | S stream (P1/P3), S latched (P2) | U | U | adjustbed | P2 uses the conservative latched ceiling because lumbar sends one start; head/feet still refresh during the lease. Speech movement is bounded, followed by voice STOP and ordinary release |
| `resident` | S stream | U | U | resident-base | Every held control refreshes at 300 ms and releases with two STOP frames; combined head/foot keys are explicit, arbitrary motor composition is unproven |
| `adjustable_lumbar` (both routes) | S stream | U | U | lumbar | unsupported chord only stops |
| `eshine_okin` (E2000, E3000/E3100, E5000) | S stream | U | U | eshine-okin | held keys write at once, refresh every 300 ms with no fixed count, STOP 200 ms after release; hold declared. Single-touch coordination excludes a second movement control; the one multi-touch path, Flat+Zero Gravity, is a fixed frame either release stops. None of its 25 constructors sets a speed |
| `paramount` | S stream | U | S | paramount | One reply-driven held action, neutral on release. Speed is a bed-wide setting, not per-command speed. |
| `simmons` (all routes) | S stream | U | U | simmons | one held action |
| `starcode_abm5_4` | S stream | U | U | abm5_4 | one held action |
| `starcode_m1x12` | S stream | U | U | m1x12 | no bitmask combination; hold declared |
| `starcode_m5x5` | S stream | U | U | abm5_5 | head and foot is a fixed combination; hold declared |
| `star_elevate` (both routes) | S stream | U | U | abm5_5, m1x12 | one held action; hold declared on the Okin 5A ELEVATE profile, refreshed at the apps' 100 ms |
| `sleepys_box25` (both routes) | S stream | U | U | sleepy | one held action; Sleepy's cluster accepted in #447 |
| `doublesleep` | B | B | B | dsleep | report PARTIAL |
| `okin_handle` | B | B | B | none | no accepted report |
| `dewertokin` | B | B | B | none | no accepted report |
| `okin_uuid` | B | B | B | none | no accepted report |
| `okin_rf_eco_bt` | B | B | B | none | no accepted report |
| `okin_cb24` | B | B | B | none | no accepted report |
| `okin_dot` | B | B | B | none | no accepted report |
| `okin_64bit` | B | B | B | none | no accepted report |
| **Okin 5A (O2)** | | | | | |
| `nectar` | S stream | U | U | nectar, row042 | combined motor masks do not produce OR'd commands; not declared, because the report reaches the Okin CST frame and not the 5A keys this bed type sends |
| `mattressfirm` | S stream | U | U | mf900 | a remaining chord button replaces the stream; not declared, for the same reason |
| `okin_cb35` | B | B | B | sealy | report PARTIAL |
| `okin_7byte` | B | B | B | none | no accepted report |
| `okin_nordic` | B | B | B | none | no accepted report |
| **Keeson E5/E6 (K1)** | | | | | |
| `keeson` (`ergomotion`), `ergomotion`, `ergomotion_app` | S stream | U | U | sfdergo | zero frame once at release |
| `keeson` (`serta`), `serta`, `serta_mp_remote` | S stream | U | U | serta330 | BLE key is overwritten, not OR'd; the OR path is Classic RFCOMM |
| `keeson` (`restonic_a`, `restonic_b`) | S stream | U | U | restonic | combined head and foot is a fixed key |
| `keeson` (`innova`) | S stream | U | U | sfm | combined is a motor union inside one fixed key |
| `keeson` (`bedsense_bases`) | S stream | U | U | sfmc2 | multi-touch shares one key code |
| `keeson` (`avanti_bases`, `dynasty_bases`, `maxcoil_una`, `americanstar`) | S stream | U | U | avanti, dynasty, maxcoil, americanstar | fixed combined keys |
| `keeson` (`simon_li`, `heal_every_night`, `okin_seating`) | S stream | U | U | simon, heal, minghua | one held key |
| `keeson` (`adjustable_lite`) | S stream (no release frame) | U | U | adjlite | release cancels the timer, no STOP frame |
| `ergomotion_4` | S stream | U | U | hump, issue558 | P1 zero after release; P2 routes end by refresh cessation |
| `keeson` (`ksbt`) | S stream | U | U | hump, mancini | Ergomotion 4.0 zero frame; Ergomotion Sync ends by refresh cessation |
| `keeson` (`base`, `okin`, `sino`, `ksbt_cr`), `okin_ffe` | B | B | B | none | no accepted report for these routes |
| `sbi` (all routes), `qplus_app` | S stream | U | U | costco | zero-mask release |
| `ergo_slim` | S stream | U | U | slim | zero-mask release |
| `keeson:okin_comfort_bed` | S stream | U | U | okincomfort | global zero-word release; no concurrent key composition |
| `omazz_adjusto_iii` | S stream | U | U | omazz | zero at release |
| `row_control` | S stream | U | U | row | zero mask at release |
| `tempur_au` | S stream | U | U | tempur_au | zero frame at release |
| `tempur_curve` | S stream | U | U | tempur | BLE path; the OR-combined key buffer is Classic RFCOMM |
| `coolbase` | S stream (no release frame) | U | U | coolbase | release cancels the timer, no STOP bytes |
| `bf` | S stream | U | U | bf | zero frame at release |
| `cherish` | S stream | U | U | cherish | combined is a fixed key |
| `comfortbase` (all ten products) | S stream | U | U | row161 | one held key refreshed every 100 ms, zero STOP at release; combined is a fixed key, no motor-speed control |
| `symphony_sleep` (all five models and three transports) | S stream | U | U | symphony078 | Immediate held key, 300 ms refresh, STOP at 0/300/600 ms. Combined head and foot is a fixed key. |
| `comfort_enhancements` | S stream | U | U | enh | STOP 100 ms after release |
| `glideaway_motion` | S stream | U | U | glide | zero frames at +300 and +600 ms |
| `adjustamattress` | S stream | U | U | row067 | union movement is a fixed action |
| `furnimove` | S stream | U | U | fm157 | composites OR fixed frames (D015); no partial release; hold declared |
| `malouf_legacy_okin` | S stream | U | U | malouf, row023 | STOP after release |
| `sleepys_box15` | B | B | B | none | no accepted report |
| `rondure` | B | B | B | none | no accepted report |
| `scott_living` | B | B | B | none | no accepted report |
| **Richmat 6E (R1)** | | | | | |
| `richmat` (all routes) | S stream | U | U | rmc2 | explicit STOP after the sustain timer; speed rows are massage |
| `richmat_revive`, `richmat_best_mattress`, `richmat_blvd_home`, `richmat_harmony`, `richmat_idealbed` | S stream | U | U | revive, best, blvd, harmony, ideal, row055 | KEEP rows repeat until removed, STOP after 120 ms; speed rows are massage |
| `ruf_betten`, `wsilver_products`, `richmat_americanstar`, `bailey_bed_control`, `richmat_tx` | S stream | U | U | ruf, wsilver, rmamericanstar, bailey, tx, row061 | KEEP rows repeat at the model's interval until removed; RUF sends STOP at once, the others STOP after 120 ms |
| `leggett_wilinke`, `leggett_platt` (`mlrm`) | S stream | U | U | lp2 | framed STOP per mode |
| `richmat_app` | S stream | U | U | row173 | product movement only; 100ms ticks and explicit STOP |
| `hjbed` | S stream | U | U | row121 | per-action recovered release |
| `richmat_classic_apps` (Avocado Eco Base, CoasterSleep, Forty Winks, Milemont, Superior) | S stream | U | U | avocado, coaster, fortywinks, milemont, superior, row066 | keep buttons repeat every 150 ms tick (110 ms for TWRM and MLRM names) until UP, then release 50 ms later; hold declared per control, on the held controls that run the keep mode under the current selection (see [per-control scope](#per-control-hold-scope)). Each press replaces the sender's one shared command and the release frame ends it; combined motors are fixed keys; speed keys are massage (`com_msg_speed`) |
| `bedtech` legacy | B | B | B | bedtech | Existing hardware-backed route; no new execution declaration |
| `bedtech` explicit BT2000, BT2500, BT3000, BT3000FH, BT6500, BTX4, BTX4FH, BTX5, BTX5FH | S stream (no release frame) | U | U | bedtech713 | One timer per physical receiver, 100 ms refresh; stop cancels it without writing; FH banks share the timer |
| `gmmotor` | B | B | B | gm | report PARTIAL; release behavior unresolved |
| `casper_base` | B | B | B | casper | report PARTIAL |
| `luuna` (Rise, Rise Pro, Rise Pro Light) | S stream (no release frame) | U | U | luuna | 100 ms held refresh, cancelled on tap-up/cancel; no live STOP enum caller. No composed axes or speed selector in the complete catalog. |
| `hush_base` | S stream | B | B | hush, row126 | movement refreshes every 100 ms, first write after 100 ms, until release, then sends STOP `6e` on the same side; massage strength sends once on press and STOP on release; text controls send their short or long gesture with no release. #516 and #591: no shard assesses two held axes or a motor-speed selection. Not declared: the mixed gestures need a per-control scope (see [per-control scope](#per-control-hold-scope)), and Hush runs on the shared Casper Base controller, whose own hold is blocked |
| **Jiecang F1 (J1)** | | | | | |
| `jiecang_app` (Dreamask, Dreamotion, Dream Motion HD) | S stream | U | U | dreamask, dreamotion, dreamhd | combined sections are fixed opcodes |
| `jiecang_app` (Comfort Motion), `jiecang`, `comfort_motion` | B | B | B | jcbed | report PARTIAL; legacy route has no report |
| `logicdata_app` (all profiles) | S stream | U | U | ld-phone, ld-pad, ld-mattress | combined is a fixed key |
| **Limoss DD (L1)** | | | | | |
| `limoss`, `limoss_remote` | S stream | U | U | limoss | more than one pressed flag returns before any write or STOP; hold declared on the Limoss Remote profile only, since the legacy `limoss` route repeats at the entry's pulse settings with one STOP, not the app's schedule |
| `fsm_relax` | S stream | U | U | fsm | more than one pressed entry suppresses all writes; hold declared |
| **FFFF frame (S1)** | | | | | |
| `solace` (both routes) | S latched | U | U | motionflex, homekobo, dianqi, woosa | one start frame, global STOP on release; hold declared on the five report-backed profiles; Legacy S4-Y and unidentified entries have no report |
| `bedsense` | S latched | U | U | bedsense | one start write, pause frame on release; hold declared |
| `motion_bed` | S latched | U | U | blackdianqi | no movement repeat; global STOP; not declared: its covers are not `timed_move` motors and it has no held controls, so no route a lease could renew |
| **Distinct protocols** | | | | | |
| `svane` (Svane Remote: `auto` P1 and `svane_remote_jmc` P2) | S stream | S | U | svane, svane-guide | P1 per-role release; P2 mask drops the released axis; global P2 STOP. The app selects P2 when the device name contains `JMC`; hold and concurrent declared on both routes, whose timed moves run on the merged stream |
| `jensen` | S stream | U | U | jensen, jensen-disp | 300 ms refresh, then one stop frame; combined head and foot is one alternating control; hold declared |
| `svane` (`jensen_linon`) | S stream | U | U | jensen, jensen-disp | 800 ms refresh; STOP to head then foot; combined motion alternates as one control; hold declared |
| `linak` (all routes) | S stream | U | U | linak-iot, linak-lp, linak-mem, linak-guide | two-section moves are fixed opcodes; one bed-wide release; speed is reported, not commanded; hold declared |
| `octo` (standard) | S stream | U | U | octo | 100 ms delayed global STOP; hold declared on the standard controller only |
| `octo` (`star2`) | B | B | B | none | no accepted artifact; `auto_stops_on_idle` rests on community reverse engineering |
| `reverie` | S latched | U | U | reverie, row041 | one frame on press, per-axis stop on release; routines serialize; hold declared |
| `reverie_pairlink` | B | B | B | reverie, row041 | row041: Pairlink runtime acceptance pending |
| `reverie_nightstand` | B | B | B | none | no accepted report |
| `rize` | S latched | U | U | rize149 | one write per press, matching axis STOP on release; app voice starts are bounded by HA; no concurrent multi-motor evidence |
| `kaidi`, `isleep` | S latched | U | U | kaidi | one start per press, per-axis release; combined is its own opcode; hold declared, except Floyd (B) and the dual-seat `seat_1_2` variant, which starts seat 2 only after seat 1's repeats |
| `kaidi` (`floyd`) | B | B | B | floyd | report PARTIAL |
| `remacro` (all models) | S latched | U | U | brick, jewmes, slumber, row050 | one write on press, paired STOP; rocking speed is massage and unreachable (R075); hold declared |
| `malouf_app`, `malouf_new_okin` | S stream | U | U | lucid, malouf, row023 | apps do not establish synchronized motion |
| `leggett_gen2`, `leggett_platt` (`gen2`) | S stream | U | U | universal | per-axis and global STOP exist; no path holds two axes; hold declared |
| `leggett_lp_legacy` | S stream | U | U | lp | explicit release once; SPEED rows are massage; not declared: it exposes button gestures only, with no `timed_move` or `hold_control` route a lease could renew |
| `timotion_ahf` | S stream | U | U | ahf | three neutral frames at release; hold declared |
| `vibradorm` | S stream | U | U | vmat | STOP on release; speed is mood light; not declared: the VMAT app runs as a `vibradorm_app` profile, and the generic route repeats at the entry's pulse settings |
| `vibradorm_app` | S stream | U | U | diamant, werkmeister | STOP on release; speed is mood light; hold declared, including its VMAT profile (vmat) |
| `vmatbasic` | S stream | U | U | vmatbasic | all-up/all-down are fixed keys; speed is mood light; hold declared |
| `eshine` | S stream | U | U | eshine | STOP once after a sustained press; hold declared |
| `galaxy` | S stream | U | U | galaxy | sustained catalog gestures first tick after 100 ms, refresh until released, then side STOP; memory-latch gestures use one long operand; no concurrent axes or motor-speed proof |
| `goodvibe` | S stream | U | U | goodvibe | sustained controls refresh every 100 ms, then release `6e`; hold declared per control, on the held controls whose effective gesture is a sustained press (see [per-control scope](#per-control-hold-scope)). Each frame carries one operand and the only release is the side's STOP; all-motor moves are fixed operands; speed rows are massage and music shake |
| `mlily` | S stream | U | U | mlily159 | Sustained controls only, after a 100 ms tick and at 100 ms intervals; submitted ticks release with STOP. Memory, force-long and 3 s gestures retain the exact selected product rules. |
| `sleepys_elite_app` | S stream | U | U | sleepy | selector STOP once at release; hold declared |
| `motosleep` | S stream | B | B | motosleep, powerbob, motosleep-guide | movement repeats every 100 ms while held; release sends `$b` five times (MotoSleep HHC and the Power Bob profiles whose release has it) or the MOTO release frame (zero five times, or `0x9088/0x0001` six times on WR219); other Power Bob profiles stop when the refresh ends. #516 and #591: the guide covers only the commands the integration sends, and the frozen reports that would show composition and the full command inventory are not retained. MotoMotion is another app, with its own row |
| `motomotion` | S stream | B | B | motomotion, row113 | held motor keys refresh every 100 ms, first write after 100 ms, then send STOP three times 50 ms after release; memory recall refreshes the same way but stops only on `SOFA` names with index 12 `E`, and the shared Home control ends by stopping its refresh with no release frame. Not declared: the controls need a per-control scope (see [per-control scope](#per-control-hold-scope)) and their own review. #516 and #591 not assessed yet |
| `bedjet_powerlayer` | B | B | B | none | no accepted app report: the commands and the self-stopping movement come from a community capture and the contributor's hardware, so the hold stays undeclared |
| `sleep_number` | B | B | B | sleepiq | report PARTIAL |
| `sleep_number_mcr` | B | B | B | none | no accepted report |
| `sleepstar` | B | B | B | none | no accepted report |
| `sleepys_box24` | B | B | B | none | no accepted report |
| `okin_ore` | B | B | B | none | no accepted report |
| `logicdata` | B | B | B | none | no accepted report |
| `suta` | B | B | B | none | no frozen analysis.json |
| `sleeptracker` | B | B | B | none | addenda only, no complete report |
| **No motor axis** | | | | | |
| `logicdata_air_pump` | U | U | U | ld-mattress | air-pump firmness, not a motor |
| `casper_remote`, `casper_sleep_mm`, `casper_sleep_sxb`, `hush_remote`, `hush_sleep_mm`, `hush_sleep_sxb`, `gmmotor_sleep_mm`, `gmmotor_sleep_sxb` | U | U | U | casper, hush, gm | remote or sleep sensor |

## Specific checks

### #483: held streams, release frames and idle stop

| Group | Rows | Refresh | Release |
| --- | --- | --- | --- |
| Leggett Okin | `leggett_okin` | 100 ms OR word | Four zero words, 100 ms apart. No distinct STOP opcode |
| Customatic | `customatic_clarity`, `customatic_jeromes`, `customatic_remedy` | 120 ms OR mask; each press may start another phase-offset chain in the app | One delayed write 100 ms after the final release, which reads the shared mask and is zero only when no key was pressed again. HA's profile uses one lane and one STOP |
| Okin CST and Okimat apps | `okin_cst`, `okimat`, `customatic_zseries`, `serenity`, `tranquil`, `nectar`, `mattressfirm` | 100 ms | Zero word twice, at +100 and +200 ms |
| Keeson E5/E6 apps | most K1 rows | 100 to 300 ms | One zero key or zero mask; Glideaway at +300 and +600 ms |
| Richmat 6E apps | R1 rows | 100 to 170 ms | Mode-aware STOP frame, 120 ms after release in the MH apps |
| Jiecang F1 apps | Dreamask, Dreamotion, Dream Motion HD, LOGICDATA | 100 or 200 ms | Dream Motion HD and LOGICDATA: short release at +100 ms. Dreamask: long release at +50 and +150 ms. Dreamotion: short at +100 ms, then long at +800 ms |
| Limoss DD | `limoss`, `limoss_remote`, `fsm_relax` | 60 or 80 ms | Five STOP frames at the poll cadence |
| Linak | `linak` | 100 or 300 ms | One bed-wide release frame |
| Distinct apps | Svane, Jensen, OCTO, Vibradorm, V-MAT Basic, TiMOTION, Eshine, Sleepy's | 30 to 350 ms; Jensen LinOn 800 ms | Per row: Svane per-role release, Jensen JMC400 one stop frame and LinOn STOP to head then foot, OCTO delayed global STOP, TiMOTION three neutral frames |
| Latched | `solace`, `bedsense`, `motion_bed`, `reverie`, `kaidi`, `isleep`, `remacro` | none | Explicit STOP at release; Reverie and Kaidi per axis |

**Stops on its own when frames stop.** Only Leggett Okin CU170 has hardware
evidence: Taudris measured the watchdog onset at 217 to 218 ms and found that
motion keys never latch (#516 and #483 comments, #368). Four app routes end a
hold only by ending the refresh: `coolbase`, `keeson` (`adjustable_lite`),
Ergomotion Sync on `keeson` (`ksbt`), and `leggett_platt` (`okin`). Their
reports state explicitly that hardware auto-stop must not be inferred. Today
`auto_stops_on_idle` is true for `furnimove`, OCTO Star2 and stop-less MotoSleep
profiles only. Star2 has no accepted artifact and MotoSleep's report is BLOCKED,
so neither declaration is evidence for #483.

`auto_stops_on_idle` answers whether cleanup may skip a release frame. It does
not say that a refresh sustains motion or how long one frame lasts. The design
below keeps it and adds the missing facts beside it, as Taudris proposed in #483.

### #516: independent axes, per-axis release and STOP

| Row | Interleaving | Per-axis release | Bed-wide STOP | Evidence |
| --- | --- | --- | --- | --- |
| Prodigy CE (`leggett_okin`, `leggett_platt`) | Normal keys combine by bitwise OR | Release or cancel removes one key; the next frame carries the rest | Four zero words | p4; CU170 measurements in #516 |
| U Series (`leggett_okin`, `leggett_platt`) | Keys OR in the output thread's accumulator; the UI names no chord | ACTION_UP or ACTION_CANCEL removes that key | Four zero words | useries |
| `customatic_clarity`, `_jeromes`, `_remedy` | Held motor masks OR into one shared mask | Partial release clears one bit; the reduced mask keeps streaming | Zero mask after the final release | clarity, jeromes, remedy, row028 |
| `svane` (Svane Remote) | P2 composes a head and feet mask; P1 refreshes per-role characteristics | P2 drops the released axis from the mask; P1 releases that role | P2 global STOP frame | svane, [svane.md](../beds/svane.md#release) |

**Customatic composes on the merged stream.** Clarity, Jerome's and Remedy
declare every motor their app holds concurrent: back and legs, and lumbar on
Remedy. Clarity's lumbar is a dead variant in its report and is not declared,
and Customatic Z-Series sends recognized masks only (`U` above). Each tick is
the OR of the live motors' keys on the app's 120 ms lane, a released motor's
bit leaves the next frame at once, and the last motor out gets the app's zero
write 100 ms after the release. HA keeps its one-lane adaptation: it does not
replay the app's duplicate phase-offset chains. The motors now have per-motor
scheduler resources, which kept Customatic serialized until a motor-scoped
Stop could pre-empt whatever holds the writer, as a bed-wide Stop does. It
now can (see [Scheduler and coordinator](#scheduler-and-coordinator)): a
cover's Stop on one motor still pre-empts a serial move on another at once,
and inside the stream it ends only its own motor.

Disconnect safety is unconditional only for Leggett Okin CU170, where motion
needs a fresh frame within the watchdog. For Customatic and Svane, a dropped
link leaves the last command to the firmware. That stays deferred validation
for beta users, as #516 allows.

Prodigy 2 and Prodigy 2L stay blocked by evidence. A recheck of both accepted
reports (`ANALYSIS.md` and `analysis.json`, no new analysis) found no per-key
release and, for Prodigy 2L, no composition:

- **Prodigy 2** (`p2`) proves composition but not per-key release. Its timing
  section says "Held/touch commands are scheduled every 100 ms. Multiple active
  keys are ORed." Its only release is the zero word: "BLE normal release
  schedules four zero attempts at 100 ms, subject to backpressure, then idles.
  [...] There is no distinct STOP opcode." Nothing says that releasing one key
  keeps another held key in the frame.
- **Prodigy 2L** (`p2l`) proves neither. Its session sequence says "For normal
  held controls, release/cancel sets key zero. Because the preceding
  `runNormal` nonzero branch cleared `sentZero`, the loop schedules four
  explicit zero attempts", and `analysis.json` (`release_behavior.normal`)
  repeats "Key zero then schedules four normal-zero attempts". The report has
  no statement that held keys combine.

Prodigy CE and U Series are the only Leggett Okin profiles with evidence for
both composition and per-key release, so they are the only ones declared
concurrent (#516). Only new evidence for Prodigy 2 or Prodigy 2L can change
their disposition.

Notable `unsupported` evidence: the Rize, Glory, Serenity, Tranquil and Nectar
apps send only recognized masks, so motor chords are never OR'd (Nectar states
it outright, row042). Limoss and FSM Relax suppress every write while more than
one control is pressed. Linak's 40 two-section moves are fixed opcodes with one
bed-wide release. Jensen interleaves head and foot as one combined control with
one stop. FurniMove composites OR fixed frames (D015) with no partial release.

### #591: motor speed

No complete report has a motor-speed command. These look like speed but are not
motor speed:

| Source | What it is |
| --- | --- |
| Richmat 6E apps, Leggett LP legacy (`SPEED up/down`) | Massage speed keys |
| Leggett universal (`WSP`), Prodigy CE wave speed | Massage wave speed |
| Vibradorm, V-MAT Basic, Caresse | Mood-light effect speed |
| Remacro `YbActivity` slow/medium/fast | Rocking massage on an unreachable screen (row050 R075) |
| Linak reference notifications | Reported actuator speed, read only |
| Limoss queue speed | Transport write-slice classification |

The 34 blocked rows are where a speed command could still appear once their
reports complete, notably `gmmotor`, `sleep_number` and `doublesleep`, or once
`motosleep`'s complete reports, which were not retained, are available again.

## Design

### Where each capability lives

| Capability | Codec | Profile | Controller |
| --- | --- | --- | --- |
| Hold | Release and STOP frames (already there) | The family `Hold` (already there) gains the hold mode and an optional measured sustain window | Open-ended write loop driven by a lease. Standalone controllers declare the capability directly |
| Concurrent motors | A composition rule where the wire has one: Okin N-frame ORs words | The axes the app is proven to compose. Profile evidence, never codec-wide | One streamer per device that writes the composed frame each tick |
| Speed | Speed encoding, when a protocol has one | Supported speed values | Cover `supported_speeds` |

The codec states what the wire can express. The profile states what its app is
proven to do. The Okin N-frame codec can OR any words, but only Prodigy CE, U
Series and the three Customatic profiles are allowed to.

### Typed API

One frozen dataclass, read by the scheduler, the cover platform and paired
intersection:

```python
@dataclass(frozen=True, kw_only=True)
class ExecutionCapabilities:
    hold: Literal["stream", "latched"] | None = None
    """Open-ended hold until release; None keeps finite pulses."""
    sustain_ms: int | None = None
    """Measured motion one frame buys. None when unproven (all but CU170)."""
    concurrent: frozenset[str] = frozenset()
    """Motor resources that may run in one window. Empty means serialized."""
    hold_controls: frozenset[str] | None = None
    """Held controls the hold is scoped to. None scopes it to the controller."""
    speeds: tuple[str, ...] = ()
    """Native motor speeds, for #591. Empty until evidence exists."""
```

- `BedController.execution` returns the empty default. Family controllers return
  `self.profile.execution`. Standalone controllers such as Svane override it.
- The family `Hold` dataclasses keep their timing. `execution` only adds what
  they lack: whether the hold may be open-ended, and which axes compose.
- `auto_stops_on_idle` stays as it is, the cleanup question.
- `speeds` ships empty until a candidate exists. Omit the field entirely if that
  reads as an empty abstraction, and add it with the first real candidate.

### Per-control hold scope

`hold` is normally a fact about the whole controller. `hold_controls` scopes it
to named `hold_control` controls, for a controller whose held buttons also
carry gestures a lease would change. `hold_for(control)` returns the mode a
lease may use on one control, or `None`; a motor route (`timed_move`) is
outside every scope. Service admission, the button attributes the card reads,
and paired held-control buttons all ask `hold_for`. A control outside the scope
is refused exactly as on an undeclared controller ("does not support renewable
holds"), and the card keeps that control's bounded hold. With `None`, every
other row behaves as before.

Good Vibe Sleep is the one scoped row. The accepted report (goodvibe,
`protocols[0].capabilities.gesture`, `timing.held_period_ms`) says a sustained
press first sends after 100 ms, repeats every 100 ms with no fixed count and,
once a tick fired, queues the generic STOP (`6e 01 side 6e sum8`, or `6e` on
the single-byte link). A short press sends at once and releases on up, long
and short-and-long presses act on a 3-second threshold without that release,
and local memory mode (`capabilities.memory`) turns an eligible sustained press
on E3RM, GXRM, JDRM, JFRM or JGRM into one long operand. The controller
therefore scopes its stream hold to the held controls whose effective gesture
is a sustained press, recomputed from memory mode on every read, and refuses a
lease inside `press` when memory mode changed after admission. Each control's
gesture is its catalog entry; all 1,369 report-backed reachable descriptors
match the report's per-descriptor `timing.gesture`, and the five Y6RM menu
controls match the ledger's derived-menu table. The one sustained descriptor
without a BLE release is the local Mlily menu, which is never a held control.
A lease reuses the existing press loop: expiry ends the refresh through the
cancel event, the 30-second ceiling is clock time rather than a tick count, and
the release follows with a fresh cleanup write.

The classic Richmat apps are the second scoped row. All five accepted reports
(avocado, coaster, fortywinks, milemont, superior) give one sender state
machine: a keep button (worker mode 1) enqueues its payload every worker tick,
150 ms or 110 ms for TWRM and MLRM names, with no fixed count until UP; UP sets
mode 0, which waits 50 ms and sends the release (`6E` raw, or `6E 01 mode 6E
sum8` framed). Once and short presses (mode 2), long presses (modes 3 and 4)
and the one-shot mode 5 run their own gestures. Three selectors change which
mode a press runs, so the scope is recomputed from them on every read:

- **Hold/Release** (BRRM, YFRM, YGRM): Hold turns the recall presets and Flat
  into keep buttons and reveals their separate save buttons; Release restores
  long-press recall and single-shot Flat.
- **Memory arming** (GXRM, JDRM, JFRM, JGRM SelectView): an armed action runs
  forced mode 10, one short or long payload, so it leaves the scope until the
  arm is used.
- **Head/foot** (GVRM tag 63): the foot side reaches the null legacy-long
  getter and sends nothing, so those controls leave the scope.

The scope comes from the accepted caller transition (`beds/richmat_classic/caller.py`), and
`tests/test_richmat_classic_hold_lease.py` checks it against every accepted DOWN and
UP caller vector. Some controls send only on one wire (GVRM ships a few with
only the legacy operand, which only RAW sends), so offline the last session's
wire decides; before any session either wire may, and the press checks the
session's own. The press also refuses a lease when a selector changed after
admission. Outside the scope:

| Control | Disposition |
|---|---|
| E3RM tvMem recall | The app's keep mode while unarmed, but a tap control here because the same button saves once armed; it has no `hold_control` route a lease could renew |
| Desk recall and reset (FWRM, WFRM) | A separate 200 ms sender with no release frame, run by the `richmat_classic` desk action rather than `hold_control` |
| APRM, AQRM Release/Hold buttons | `setReleaseHold` has no branch for these layouts, so their buttons keep their ordinary gestures |

### Scheduler and coordinator

**#483 hold lease.** A held intent carries a lease: owner, generation and a
monotonic deadline. A call that names an active lease's owner, motor and
direction replaces its deadline outright, without a new frame or a release. The
controller's write loop refreshes until the deadline passes or the context is
cancelled, then runs its existing cleanup with a fresh event. This keeps the
rules in #483: a stale generation is rejected, STOP outranks renewal through the
existing stop epoch, nothing replays after disconnect, unload or restart, and
streaming and cleanup stay in the controller. Leases are a new
`CommandKind.HOLD`; replacement and admission otherwise behave as today.
`IntentLifetime.HELD` and `hold_owner` are already gone from
`command_scheduler.py`, so the lease arrives complete.

**#516 merged stream.** `serial_opaque` stays the default. A second strategy,
used only when every requested resource is in `execution.concurrent`, runs one
streamer task per device that owns the wire. Holds, timed moves and seeks on
disjoint motors register as members. Each tick the streamer asks the controller
to compose the live members into frames: one OR word for Okin N-frame, a mask or
per-role frames for Svane. When a member ends or reverses, the controller runs
that member's own cleanup: the next composed frame without its bit for a mask
codec, or a directional release for Svane P1, which has no global P1 STOP.
Removing the last member runs the profile release. A motor-scoped STOP
(`ControllerMotorHoldSpec.stop_scope == "motor"`) ends only its member. A side
or bed-wide STOP clears every member at the stop epoch and sends the bed-wide
STOP before any later member is admitted. One
writer means no extra BLE concurrency. None of the candidates reports motor
positions, so seeks join later; holds and timed moves come first.

**STOP pre-emption.** A STOP never waits behind another motor's command. A
motor-scoped STOP admission (`DeviceCommandScheduler.admit_stop`) or a queued
`CommandKind.STOP` command pre-empts whatever motion holds the writer in its
bed or side: any active command on `motor:*` of that namespace, not only the
stopped motor. The in-flight write and that command's own cleanup finish, then
the STOP's frames go out, ahead of anything queued. A merged stream that owns
the stopped motor keeps the writer and ends only that member, with its cleanup
next, before any further tick. Commands on other resources (lighting,
configuration) and work confined to the other side of a one-address pair are
never pre-empted. A native Both move drives both sides in one frame, so it
cannot end on one side alone: a Stop on either side ends it on both, as
overlapping replacement and a side STOP always have. Waiting it out instead
would leave the stopping side moving for up to its lease ceiling. A pair's
side-lane admission matches wildcards, so a side-wide Stop also drops a move
still queued on that side's lane. A declared side-wide cover Stop is a `motor:*` STOP that ends every
motor's work, the stream included. Uncontended, a cover Stop writes exactly
what it wrote before.

Every cover Stop goes through `async_stop_motor` on its runtime. A standalone
bed admits the STOP. A pair's side bypasses the side lanes, as a side STOP does,
through `PairTopology.stop_motor`: a two-address receiver admits the STOP; a
one-address side, whose scheduler the other side shares, queues a STOP-kind
command so the shared STOP epoch, and the other side's queued work, stay
untouched. A sequential pair moves a side only inside a cycle that drops the
side's link when the command ends, and the drop halts it (the topology's
dead-man model). There the Stop pre-empts a cycling side's command, whose own
release goes out, and adds no frame of its own: one would race the cycle's
disconnect, which does not wait for the command lock, or reconnect the side
and open the second link the topology avoids. A connected side outside a cycle
gets the motor's stop, and a disconnected one already halted.

**#591.** When a candidate exists, the cover advertises
`execution.speeds` as `supported_speeds`. An omitted speed keeps today's
behavior; an unsupported value is rejected before admission.

### Paired sides

- **Two addresses:** each side keeps its own lease and streamer. A combined
  hold is two leases with one owner, and one renewal renews both. The combined
  control offers a hold only when both sides declare the same `hold` mode.
- **One address with a side field:** the side is part of the frame. No
  candidate proves that both sides compose into one frame, so sides stay
  serialized.
- **Intersection:** combined controls use the intersection of `concurrent` and
  of `speeds`. An empty intersection disables the feature for the combined
  control only; each side keeps its own.

### Test strategy

- **Evidence allowlist.** `tests/test_execution_capabilities.py` maps each bed
  type or profile that declares a capability to its evidence key from this
  document, and fails when a declaration has no entry. Adding a capability then
  needs a reviewed evidence row.
- **Frozen vectors.** Each declared profile's held, composed and release frames
  must be among its frozen literals (`tests/*_vectors.py`): the Prodigy CE head
  and foot chord, the Customatic back and foot mask, a partial-release frame,
  the zero word, and Svane's per-role and global frames.
- **Scheduler.** Lease renewal replaces the deadline without a frame; expiry
  releases; STOP preempts renewal; a stale generation is refused; disconnect,
  unload and shutdown do not replay. For the merged stream: every member appears
  each tick, replacing one member leaves the other, STOP during interleaving,
  cleanup failure, and a non-opted controller staying serialized. On every
  opted-in family (`tests/test_merged_stream_families.py`), an unload or a
  shutdown that cancels every task ends both streaming motors with the
  family's release, and a motor replaced faster than the refresh never delays
  the other's refreshes.
- **Paired.** Intersection, combined renewal, and one side's STOP leaving the
  other side's lease intact.
- Hardware stays deferred to beta users; see
  [Physical validation](#physical-validation).

## Physical validation

Deferred for the v5 beta ([#783](https://github.com/kristofferR/ha-adjustable-bed/issues/783)).

- **Proven offline.** The accepted app reports prove which frames each
  candidate app composes, releases and stops with. The merged stream's
  scheduler tests (membership, partial release, STOP and the serialized
  fallback) arrive with it. The only hardware evidence is the Leggett Okin
  CU170 watchdog measurement.
- **Needs real-bed reports.** For each candidate as its declaration lands: that
  two held motors move together without stutter, that releasing one leaves the
  other moving, that STOP halts both at once, and what the bed does when the
  link drops mid-chord. The last one matters most for Customatic and Svane (see
  [#516 above](#516-independent-axes-per-axis-release-and-stop)). Taudris offered
  to validate Leggett Okin.

The merged stream (#795) is not in the current beta; until it lands, every bed
keeps serialized motors.

## Decisions for the maintainer

### 1. #483 surface

| Option | Pros | Cons |
| --- | --- | --- |
| **A. Lease semantics on `timed_move` and `hold_control`** (Recommended) | No new service. Renewing replaces the deadline. Automations keep one bounded call; the card renews short calls. Both already validate and release per profile | Changes renewal behavior of two existing actions for opted-in controllers |
| B. New `hold_motor` and `release_motor` services | Clear names; no change to existing actions | A third timing surface beside `timed_move` and `hold_control` |
| C. `open_cover` runs until `stop_cover` | Matches HA's cover semantics | A blocking call outlives a vanished client (#483 comment), and it changes covers for every bed |

Recommend A. Keep covers finite. Revisit C only behind a lease, as Taudris
proposed.

### 2. #483 dead-man bound

| Option | Pros | Cons |
| --- | --- | --- |
| **A. Caller-supplied lease, server floor and ceiling** (Recommended) | The card renews every 250 ms with a 750 ms lease, so two lost renewals end intent. The ceiling stays the existing 30 s `timed_move` cap | The card cadence is a UI constant to tune |
| B. Fixed server timeout, for example 1 s | One number | Too short stutters on slow proxies; too long runs away |
| C. Derive it from `sustain_ms` | Exact for CU170 | Known for one bed only |

With A, a vanished client stops a stream bed within the lease plus that bed's
own behavior. Latched protocols (Reverie, Solace, Kaidi, Remacro, BedSense,
Motion Bed) keep moving until a STOP arrives. Recommend opting them in only
after the stream rows ship, with a shorter ceiling.

**Decided: latched holds stop at 10 s.** `ExecutionCapabilities.hold_ceiling_ms`
is 30 s for `stream` and 10 s for `latched`, and a renewable hold never runs
past its controller's ceiling, however often it is renewed. A latched bed keeps
moving after its one start frame, so the ceiling bounds how far it travels when
a client vanishes and no renewal or STOP arrives; the lease still ends it
sooner. No accepted report states a travel time or a firmware cutoff for a
latched row, so no row justifies a different bound. The end of a lease sends
each protocol's own STOP or release with a fresh event, as every other end of a
hold does. The ceiling is clock time owned by the scheduler, not a refresh
count: per-write latency would otherwise stretch a counted refresh past it.

### 3. #516 opt-in list

| Option | Pros | Cons |
| --- | --- | --- |
| **A. Leggett Okin (Prodigy CE, U Series), then Customatic** (Recommended) | One codec, one composition rule, hardware-measured cadence, a willing tester | Customatic is static evidence only |
| B. All five rows at once | Covers every candidate | Svane adds per-role streaming to a standalone controller in the same change |
| C. Leggett Okin only | Smallest | Leaves proven Customatic behavior unused |

Svane follows as its own PR.

### 4. #591 first candidates

| Option | Pros | Cons |
| --- | --- | --- |
| **A. Defer #591 with this matrix as its assessment** (Recommended) | Matches #591's own exit; no empty abstraction | No speed feature in v5 unless a blocked report completes |
| B. Ship the cover plumbing with no controller | Ready for a future candidate | Dead code, and untestable against vectors |

Revisit when the `gmmotor`, `sleep_number` or `doublesleep` reports complete,
or `motosleep`'s complete reports are available again.

## Implementation plan

| # | PR | Owns | Depends on |
| --- | --- | --- | --- |
| 1 | `ExecutionCapabilities`, `BedController.execution` default, evidence allowlist test | `beds/base.py`, new test | None |
| 2 | #483 hold lease in the scheduler and coordinator, fake-controller tests | `command_scheduler.py`, `coordinator.py`, `services.py` | 1 |
| 3 | #483 Okin N-frame: Leggett Okin and Customatic declare `hold`, open-ended loop, vectors | `codec/okin_nframe.py`, `profiles/okin_nframe.py`, `beds/okin_nframe.py`, `tests/okin_nframe_vectors.py` | 2 |
| 4 | #483 card renewal for declared controllers, rebuilt bundle | `frontend/` | 2 |
| 5 | #483 one PR per further family: Jiecang, Keeson, Richmat, Limoss, Okin 5A, FF frame, then standalone controllers | each family's codec, profile, controller and vector files | 2 |
| 6 | #516 merged-stream strategy behind `execution.concurrent` | `command_scheduler.py`, `coordinator.py` | 2 |
| 7 | #516 Leggett Okin and Customatic composition | Okin N-frame files | 3, 6 |
| 8 | #516 Svane | `beds/svane/controller.py`, `beds/svane/state.py`, Svane tests | 6 |
| 9 | #591 closed as deferred, citing this document | none | none |

PRs 3, 4 and each PR in 5 own disjoint files and run in parallel after 2. PRs 2
and 6 share the scheduler, so they run in sequence. PR 7 follows 3 because they
share the Okin N-frame files.

## Observations (not fixed here)

1. #483 says only `linak` and `motosleep` declare `auto_stops_on_idle`. Now
   `linak` returns false, and `furnimove`, OCTO Star2 and stop-less MotoSleep
   profiles return true.
2. #483 lists `okin_handle` among the keepalive streams. `okin_handle` is now a
   DewertOkin profile over the Okin N-frame codec with no keepalive. OCTO's
   keepalive is a PIN session refresh, not a motion stream.
3. The [Okin N-frame guide](../beds/okin-nframe.md#features) lists Okimat as
   "Held motors combine". The accepted reports for its apps (Glory, Support,
   Rize Resident) send recognized masks only. The guide claim needs a source or
   a correction.
4. OCTO Star2's `auto_stops_on_idle` rests on community reverse engineering, with
   no accepted artifact.

## Evidence keys

| row132 | OkinComfortBed II 2.0.2 (9), `com.ore.jalon.neworebeding`, unit132 E07/E09: all three profiles refresh held movement every 300 ms; STOP immediately and again after 300 ms. No concurrent-motor composition. |

Report workspaces are machine-local under
`disassembly/output/phase4-early/` in the main checkout.

| Key | Package | Version | Status | Workspace under `phase4-early/` |
|---|---|---|---|---|
| paramount | `com.paramount.bedcontrol` | 3.0.4 | COMPLETE | `com.paramount.bedcontrol-3.0.4-2026-11-09-queue002/report/` |
| smart-comfort-synargy | `com.synargy.okin` | 1.1.0 (12) | COMPLETE, accepted | `com.synargy.okin-1.1.0-2026-11-09-queue002/` |
| smart-comfort-synergy | `com.synergy.okin` | 2.2.0 (16) | COMPLETE, accepted | `com.synergy.okin-2.2.0-2026-11-09-queue002/` |
| mlily159 | `com.richmat.mlily2` | 5.0.2 (50200) | COMPLETE, independent audit ACCEPT | `com.richmat.mlily2-5.0.2-2026-11-10-reconciliation002/report/` |
| abm5_4 | `com.starcode.abm5_4` | 1.0.1 | COMPLETE | `com.starcode.abm5_4-1.0.1-2026-09-30-extra-four-004-005/report/` |
| abm5_5 | `com.starcode.abm5_5` | 1.2.3 | COMPLETE | `com.starcode.abm5_5-1.2.3-2026-09-30-extra-four-005-005/report/` |
| adjlite | `com.keeson.adjustablelite` | 1.0.2 | COMPLETE | `com.keeson.adjustablelite-1.0.2-2026-10-01-queue-e0bb6807-20261001-051-003/report/` |
| ahf | `com.timotion.ahf` | 1.0.4 | COMPLETE | `com.timotion.ahf-1.0.4-2026-10-26-39bdcafa-repair-001/report/` |
| americanstar | `com.ore.americanstar` | 1.0 | COMPLETE | `com.ore.americanstar-1.0-2026-11-03-bulk061-001/report/` |
| avanti | `com.ore.AvantiBases` | 1.0.5 | COMPLETE | `com.ore.AvantiBases-1.0.5-2026-11-03-bulk061-001/report/` |
| aviada | `com.okin.bedding.rizeaviada` | 1.0.1 | COMPLETE | `com.okin.bedding.rizeaviada-1.0.1-2026-08-30/report/` |
| avocado | `com.richmat.avocadoecobase` | 1.0.4 | COMPLETE | `com.richmat.avocadoecobase-1.0.4-2026-11-03-bulk061-clean002/work/report-revision-sol-003/` |
| bailey | `com.richmat.bailey2` | 2.1.21 | COMPLETE | `com.richmat.bailey2-2.1.21-2026-11-03-bulk061-001/work/report-revision-sol-002/` |
| bedsense | `com.fenmenbielei.bedsense` | 1.8 | COMPLETE | `com.fenmenbielei.bedsense-1.8-2026-11-03-bulk101-188-001/report/` |
| bedtech713 | `com.bedtech` | 7.1.3 (14) | COMPLETE | `com.bedtech-7.1.3-2026-11-10-maxqueue001/report/`, accepted audit001; unit095 |
| bedtech | `com.richmat.bed_tech` | 2.8.3 | PARTIAL | `com.richmat.bed_tech-2.8.3-2026-11-03-bulk061-001/report/` |
| best | `com.richmat.best_mattress` | 1.1.1 | COMPLETE | `com.richmat.best_mattress-1.1.1-2026-10-02-queue-e0bb6807-20261001-055-005/report/` |
| bf | `com.BF` | 1.2.3 | COMPLETE | `com.BF-1.2.3-2026-11-03-bulk061-001/report/` |
| blackdianqi | `com.sn.blackdianqi` | 1.24 | COMPLETE | `com.sn.blackdianqi-1.24-2026-09-30-extra-four-b-032-007/report/` |
| blvd | `com.richmat.blvd_home` | 1.0.1 | COMPLETE | `com.richmat.blvd_home-1.0.1-2026-10-02-queue-e0bb6807-20261001-055-008/report/` |
| bob | `com.okin.bedding.rizebob` | 1.0.1 | COMPLETE | `com.okin.bedding.rizebob-1.0.1-2026-08-30/report/` |
| brick | `com.cheers.brick` | v1.0 | COMPLETE | `com.cheers.brick-v1.0-2026-10-01-queue-e0bb6807-20261001-050-002/report/` |
| carefree | `com.okin.bedding.rizeiicarefree` | 1.0.1 | COMPLETE | `com.okin.bedding.rizeiicarefree-1.0.1-2026-08-30/report/` |
| luuna | `com.richmat.luuna` | 2.0.1 (20102) | COMPLETE | `com.richmat.luuna-2.0.1-2026-11-10-maxqueue001/report/`, accepted audit002 |
| casper | `com.richmat.casperbase` | 1.0.8 | PARTIAL | `com.richmat.casperbase-1.0.8-2026-11-03-bulk101-188-001/report/` |
| cherish | `com.okin.ore.cherish` | 1.0.4 | COMPLETE | `com.okin.ore.cherish-1.0.4-2026-11-03-bulk061-001/report/` |
| clarity | `com.okin.bedding.customaticclarity` | 1.0.1 | COMPLETE | `com.okin.bedding.customaticclarity-1.0.1-2026-08-30/report/` |
| coaster | `com.richmat.coastersleep` | 1.0.10 | COMPLETE | `com.richmat.coastersleep-1.0.10-2026-11-03-bulk061-clean002/work/report-revision-sol-001/` |
| contempo | `com.okin.bedding.rizecontempo` | 1.0.2 | COMPLETE | `com.okin.bedding.rizecontempo-1.0.2-2026-08-30/report/` |
| coolbase | `com.keeson.coolbase` | 1.0.0 | COMPLETE | `com.keeson.coolbase-1.0.0-2026-10-01-queue-e0bb6807-20261001-047-002/report/` |
| costco | `com.sbi.costco` | 1.8 | COMPLETE | `com.sbi.costco-1.8-2026-10-26-39bdcafa-repair-001/report/` |
| diamant | `de.vibradorm.diamant` | 0.3 | COMPLETE | `de.vibradorm.diamant-0.3-2026-09-30-isolated-003/report/` |
| dianqi | `com.sn.dianqi` | 1.0.6 | COMPLETE | `com.sn.dianqi-1.0.6-20260830/report/` |
| dreamask | `com.jiecang.dreamask.app.android.bed` | 1.0.8 | COMPLETE | `com.jiecang.dreamask.app.android.bed-1.0.8-20260827-acceptance-v4-replay-b/report/` |
| dreamhd | `com.dreamhd.jiecang.android.pad.bed` | 1.0.4 | COMPLETE | `com.dreamhd.jiecang.android.pad.bed-1.0.4-2026-11-03-bulk101-188-002/report/` |
| dreamotion | `com.jiecang.dreamotion.app.android.bed` | 1.0.5 | COMPLETE | `com.jiecang.dreamotion.app.android.bed-1.0.5-20260827/report/` |
| dsleep | `com.okin.doublesleep` | 1.2.24 | PARTIAL | `com.okin.doublesleep-1.2.24-2026-11-03-bulk101-188-001/report/` |
| dynasty | `com.ore.Dynasty` | 1.0.2 | COMPLETE | `com.ore.Dynasty-1.0.2-2026-10-02-queue-903926b6-20261002-056-001/report/` |
| enh | `com.okin.enhancements` | 1.0.3 | COMPLETE | `com.okin.enhancements-1.0.3-2026-11-03-bulk101-188-001/report/` |
| eshine | `com.richmat.eshinesleep` | 1.0.1 | COMPLETE | `com.richmat.eshinesleep-1.0.1-2026-11-03-bulk101-188-001/report/` |
| eshine-okin | `com.okin.eshine` | 1.1.8 | COMPLETE | `com.okin.eshine-1.1.8-2026-11-03-bulk101-188-001/work/report-repair-sol-002/` |
| floyd | `com.kaidi_test4.floyd` | 1.0.7 | PARTIAL | `com.kaidi_test4.floyd-1.0.7-2026-11-03-bulk101-188-001/report/` |
| fortywinks | `com.richmat.fortywinks` | 1.0.1 | COMPLETE | `com.richmat.fortywinks-1.0.1-2026-11-03-bulk061-001/work/report-revision-sol-001/` |
| fsm | `com.limoss.fsmrelax` | 1.9 | COMPLETE | `com.limoss.fsmrelax-1.9-2026-09-30-extra-four-075-001/report/` |
| glide | `com.ore.bedding.glideawaymontion` | 1.0.3 | COMPLETE | `com.ore.bedding.glideawaymontion-1.0.3-2026-11-03-bulk061-001/report/` |
| galaxy | `nl.starinternational.galaxy` | 3.3.0 (330002) | COMPLETE | `nl.starinternational.galaxy-3.3.0-2026-11-10-reconciliation001/report/` |
| goodvibe | `com.richmat.goodvibesleep` | 2.0.1 | COMPLETE | `com.richmat.goodvibesleep-2.0.1-2026-11-03-bulk101-188-001/work/report-repair-sol-003/` |
| glory | `com.okin.bedding.glory` | 1.0.4 | COMPLETE | `com.okin.bedding.glory-1.0.4-2026-10-01-queue-e0bb6807-20261001-052-002/report/` |
| gm | `com.desarketing.gmmotor` | 4.6.6 | PARTIAL | `com.desarketing.gmmotor-4.6.6-2026-11-03-bulk101-188-001/report/` |
| harmony | `com.richmat.harmony` | 1.0.0 | COMPLETE | `com.richmat.harmony-1.0.0-2026-10-02-queue-e0bb6807-20261001-055-006/report/` |
| heal | `com.okin.healeverynight` | 1.0 | COMPLETE | `com.okin.healeverynight-1.0-2026-10-02-queue-903926b6-20261002-060-002/report/` |
| homekobo | `com.ly.homekobo` | 1.4 | COMPLETE | `com.ly.homekobo-1.4-20260830/report/` |
| hush | `com.richmat.hushbase` | 1.0.5 | PARTIAL | `com.richmat.hushbase-1.0.5-2026-11-03-afk-003/report/`; the shards freeze `PARTIAL`, and the root acceptance in the row126 ledger covers all ten |
| hump | `com.sfd.hump` | 3.7 | COMPLETE | `com.sfd.hump-3.7-2026-11-03-issue558-20261103-006/report/` |
| ideal | `com.richmat.idealbed` | 2.4.2 | COMPLETE | `com.richmat.idealbed-2.4.2-2026-10-02-queue-e0bb6807-20261001-055-003/report/` |
| iiclarity | `com.okin.bedding.rizeiiclarity` | 1.0.1 | COMPLETE | `com.okin.bedding.rizeiiclarity-1.0.1-2026-08-30/report/` |
| jcbed | `com.jiecang.app.android.jiecangbed` | 2.2.1 | PARTIAL | `com.jiecang.app.android.jiecangbed-2.2.1-2026-11-03-bulk101-188-001/report/` |
| jensen | `air.no.jensen.adjustablesleep` | 2.0.37 | COMPLETE | `air.no.jensen.adjustablesleep-2.0.37-2026-09-29/report/` |
| jeromes | `com.okin.bedding.customaticjeromes` | 1.0.1 | COMPLETE | `com.okin.bedding.customaticjeromes-1.0.1-2026-08-30/report/` |
| jewmes | `com.cheers.jewmes` | v1.202112141512 | COMPLETE | `com.cheers.jewmes-v1.202112141512-2026-10-01-queue-e0bb6807-20261001-050-002/report/` |
| rize149 | `com.kaidi_test4.rize` | 1.4.2 (57) | COMPLETE | `com.kaidi_test4.rize-1.4.2-2026-11-10-maxqueue001/report/` |
| kaidi | `com.kaidi_test4` | 1.6.3 | COMPLETE | `com.kaidi_test4-1.6.3-2026-11-03-bulk061-001/report/` |
| ld-mattress | `com.logicdata.app.mattress.bed` | 1.0.0 | COMPLETE | `com.logicdata.app.mattress.bed-1.0.0-2026-10-01-queue-e0bb6807-20261001-053-005/report/` |
| ld-pad | `com.logicdata.app.android.pad.bed` | 1.0.4 | COMPLETE | `com.logicdata.app.android.pad.bed-1.0.4-20260827/report/` |
| ld-phone | `com.logicdata.app.android.bed` | 1.0.6 | COMPLETE | `com.logicdata.app.android.bed-1.0.6-20260827/report/` |
| limoss | `com.limoss.limossremote` | 7.1.8 | COMPLETE | `com.limoss.limossremote-7.1.8-2026-09-30-extra-four-b-040-003/report/` |
| linak-iot | `com.linak.bedconnect.iot` | 5.2.4 | COMPLETE | `com.linak.bedconnect.iot-5.2.4-20260829/report/` |
| linak-lp | `com.linak.leggettandplatt` | 1.0 | COMPLETE | `com.linak.leggettandplatt-1.0-20260829/report/` |
| linak-mem | `com.linak.linakbed.ble.memory` | 6.0.9 | COMPLETE | `com.linak.linakbed.ble.memory-6.0.9-20260829/report/` |
| lp | `com.richmat.lp` | 2.2.1 | COMPLETE | `com.richmat.lp-2.2.1-20260827/report/` |
| lp2 | `com.richmat.lp2` | 2.3.25 | COMPLETE | `com.richmat.lp2-2.3.25-20260827/report/` |
| lucid | `com.lucid.bedbase` | 1.3.3 | COMPLETE | `com.lucid.bedbase-1.3.3-2026-08-27/report/` |
| adjustbed | `com.okin.bedding.adjustbed` | 1.2.1 (33) | COMPLETE | `com.okin.bedding.adjustbed-1.2.1-2026-11-09-queue002/report/` |
| resident-base | `com.okin.resident.release` | 1.0.0 (1) | COMPLETE | `com.okin.resident.release-1.0.0-2026-11-10-maxqueue001/report/`, accepted audit001 |
| lumbar | `com.okin.bedding.adjustablelumbar` | 1.2.2 | COMPLETE | `com.okin.bedding.adjustablelumbar-1.2.2-2026-10-01-queue-e0bb6807-20261001-054-002/report/` |
| m1x12 | `com.starcode.adjustablem1x12` | 1.1.3 | COMPLETE | `com.starcode.adjustablem1x12-1.1.3-2026-10-26-39bdcafa-repair-002/report/` |
| malouf | `com.malouf.bedbase` | 2.4.3 | COMPLETE | `com.malouf.bedbase-2.4.3-2026-08-27/report/` |
| mancini | `cn.com.mancini` | 1.0.5 | COMPLETE | `cn.com.mancini-1.0.5-20260722/report/` |
| maxcoil | `com.ore.maxcoil` | 1.1.0 | COMPLETE | `com.ore.maxcoil-1.1.0-2026-10-02-queue-903926b6-20261002-056-002/report/` |
| mf900 | `com.okin.bedding.rizemf900` | 1.1.2 | COMPLETE | `com.okin.bedding.rizemf900-1.1.2-20260826/report/` |
| milemont | `com.richmat.milemont` | 1.0.4 | COMPLETE | `com.richmat.milemont-1.0.4-2026-11-03-bulk061-001/work/report-revision-sol-002/` |
| minghua | `com.okin.minghua.R` | 1.0.1 | COMPLETE | `com.okin.minghua.R-1.0.1-2026-10-02-queue-903926b6-20261002-060-002/report/` |
| motionflex | `com.sealy.motionflex` | 1.0.3 | COMPLETE | `com.sealy.motionflex-1.0.3-20260830/report/` |
| motomotion | `com.HHC.MotoMotion` | 3.1.9 | COMPLETE | `com.HHC.MotoMotion-3.1.9-2026-11-03-bulk101-188-002/work/report-repair-sol-003/` |
| motosleep | `com.HHC.MotoSleep` | 5.1.5 | COMPLETE | Not retained; accepted in #447, `analysis.json` hash in the [MotoSleep guide](../beds/motomotion.md#analysis-provenance) |
| nectar | `com.okin.bedding.nectarmotion` | 1.0.1 | COMPLETE | `com.okin.bedding.nectarmotion-1.0.1-2026-10-26-39bdcafa-003/report/` |
| octo | `de.octoactuators.octosmartcontrolapp` | 1.03.02 | COMPLETE | `de.octoactuators.octosmartcontrolapp-1.03.02-2026-10-26-39bdcafa-repair-001/report/` |
| okincomfort | `com.ore.okincomfortbed` | 1.1.6 (8) | COMPLETE | `com.ore.okincomfortbed-1.1.6-2026-11-10-maxqueue001/report/` |
| omazz | `com.sfd.Omazz` | 1.0.5 | COMPLETE | `com.sfd.Omazz-1.0.5-2026-10-26-39bdcafa-repair-001/report/` |
| p2 | `com.leggett.prodigy2` | 2.2.0 | COMPLETE | `com.leggett.prodigy2-2.2.0-20260827/report/` |
| p2l | `com.leggett.prodigy2L` | 1.2 | COMPLETE | `com.leggett.prodigy2L-1.2-20260827/report/` |
| p4 | `com.leggett.prodigy4` | 1.2.0 | COMPLETE | `com.leggett.prodigy4-1.2.0-20260827/report/final/` |
| powerbob | `com.HHC.PowerBob` | 2.0.3 | COMPLETE | Not retained; accepted in #447, `analysis.json` hash in the [MotoSleep guide](../beds/motomotion.md#analysis-provenance) |
| remedy | `com.okin.bedding.customaticremedy` | 1.0.1 | COMPLETE | `com.okin.bedding.customaticremedy-1.0.1-2026-08-30/report/` |
| resident | `com.okin.bedding.rizeResident` | 1.0.1 | COMPLETE | `com.okin.bedding.rizeResident-1.0.1-2026-08-30/report/` |
| restonic | `com.keeson.restonicBT` | 1.2.0 | COMPLETE | `com.keeson.restonicBT-1.2.0-2026-10-02-queue-903926b6-20261002-058-002/report/` |
| reverie | `com.reverie.reverie` | 3.3.3.8 | COMPLETE | `com.reverie.reverie-3.3.3.8-2026-10-27-39bdcafa-amendment-consolidation-001/report/` |
| revive | `com.richmat.revive3` | 1.0.26 | COMPLETE | `com.richmat.revive3-1.0.26-2026-10-02-queue-e0bb6807-20261001-055-006/report/` |
| rmamericanstar | `com.richmat.americanstar` | 1.0.0 | COMPLETE | `com.richmat.americanstar-1.0.0-2026-11-03-bulk061-001/work/report-revision-sol-001/` |
| rmc2 | `com.richmat.rmcontrol2` | 21.3.7 | COMPLETE | `com.richmat.rmcontrol2-21.3.7-20260906-comparison-001/report/` |
| row | `com.sfd.row` | 2.0 | COMPLETE | `com.sfd.row-2.0-2026-10-26-39bdcafa-repair-001/report/` |
| ruf | `com.desarketing.ruf_betten_motor2` | 1.1.8 | COMPLETE | `com.desarketing.ruf_betten_motor2-1.1.8-2026-11-03-bulk061-001/work/report-revision-sol-001/` |
| sanctuary | `com.okin.bedding.rizeSanctuary` | 1.0.1 | COMPLETE | `com.okin.bedding.rizeSanctuary-1.0.1-2026-08-30/report/` |
| sealy | `com.okin.sealy` | 1.1.3 | PARTIAL | `com.okin.sealy-1.1.3-2026-10-03-extra-four-b-036-repair-004/report/` |
| serenity | `com.okin.bedding.serenity` | 1.0.1 | COMPLETE | `com.okin.bedding.serenity-1.0.1-2026-09-30-isolated-002/report/` |
| serta330 | `com.ore.serta330` | 1.1 | COMPLETE | `com.ore.serta330-1.1-2026-09-30-extra-four-033-com-ore-serta330-007/report/` |
| sfdergo | `com.sfd.ergomotion` | 1.6.4 | COMPLETE | `com.sfd.ergomotion-1.6.4-2026-10-26-39bdcafa-repair-002/report/` |
| sfm | `com.ore.sfm` | 2.0 | COMPLETE | `com.ore.sfm-2.0-2026-10-02-queue-903926b6-20261002-059-002/report/` |
| jalon | `com.ore.jalon.neworebeding_android` | 1.4 (4) | COMPLETE | `com.ore.jalon.neworebeding_android-1.4-2026-11-10-queue001/report/` |
| sfmc2 | `com.ore.sfmc2bedsence` | 1.1 | COMPLETE | `com.ore.sfmc2bedsence-1.1-2026-10-02-queue-903926b6-20261002-059-001/report/` |
| simmons | `com.okin.simmons` | 1.12.9 | COMPLETE | `com.okin.simmons-1.12.9-2026-10-01-queue-e0bb6807-20261001-049-004/report/` |
| simon | `com.okin.simon` | 1.0.1 | COMPLETE | `com.okin.simon-1.0.1-2026-10-02-queue-903926b6-20261002-060-001/report/` |
| sleepiq | `com.selectcomfort.SleepIQ` | 5.4.11 | PARTIAL | `com.selectcomfort.SleepIQ-5.4.11-20260923/report/` |
| sleepy | `com.okin.bedding.sleepy` | 1.1.5 | COMPLETE | `com.okin.bedding.sleepy-1.1.5-2026-10-26-39bdcafa-repair-005/report/` |
| slim | `com.sfd.slim` | 1.3 | COMPLETE | `com.sfd.slim-1.3-2026-10-26-39bdcafa-001/report/` |
| slumber | `com.cheers.slumber` | v1.0 | COMPLETE | `com.cheers.slumber-v1.0-2026-10-01-queue-e0bb6807-20261001-050-001/report/` |
| superior | `com.richmat.superior` | 1.0.9 | COMPLETE | `com.richmat.superior-1.0.9-2026-11-03-bulk061-001/work/report-revision-sol-001/` |
| support | `com.okin.bedding.support` | 1.0.4 | COMPLETE | `com.okin.bedding.support-1.0.4-2026-08-30/report/` |
| svane | `com.svane.svaneremote` | Version 1.8 | COMPLETE | `com.svane.svaneremote-Version_1.8-2026-09-30-extra-four-b-130-003/report/` |
| tempur | `com.ore.tempur` | 1.7 | COMPLETE | `com.ore.tempur-1.7-2026-10-26-39bdcafa-repair-001/report/` |
| tempur_au | `com.sfd.tempur_au` | 1.6 | COMPLETE | `com.sfd.tempur_au-1.6-2026-10-26-39bdcafa-001/report/` |
| tranquil | `com.okin.bedding.tranquil` | 1.0.2 | COMPLETE | `com.okin.bedding.tranquil-1.0.2-2026-10-01-queue-e0bb6807-20261001-052-002/report/` |
| tx | `com.richmat.tx` | 1.0.0 | COMPLETE | `com.richmat.tx-1.0.0-2026-11-03-bulk061-001/work/report-revision-sol-001/` |
| universal | `com.leggett.android.universal` | 2.9.0 | COMPLETE | `com.leggett.android.universal-2.9.0-20260824/report/` |
| useries | `com.leggett.useries` | 2.1 | COMPLETE | `com.leggett.useries-2.1-20260827/final-report/` |
| vmat | `de.vibradorm.vmat` | 1.11 | COMPLETE | `de.vibradorm.vmat-1.11-2026-09-30-isolated-001/report/` |
| vmatbasic | `com.vibradorm.vmatbasic` | 2.4.3 | COMPLETE | `com.vibradorm.vmatbasic-2.4.3-2026-09-30-isolated-001/report/` |
| werkmeister | `de.vibradorm.werkmeister` | 0.2 | COMPLETE | `de.vibradorm.werkmeister-0.2-2026-09-30-isolated-001/report/` |
| woosa | `com.sn.woosa` | 1.1.9 | COMPLETE | `com.sn.woosa-1.1.9-20260923/report/` |
| wsilver | `com.richmat.wsilver2` | 1.1.19 | COMPLETE | `com.richmat.wsilver2-1.1.19-2026-11-03-bulk061-001/work/report-revision-sol-003/` |

Ledgers, guides and issues. An audit ledger is a machine-local record kept with
its APK Protocol Audit report, named here by its file stem:

| Key | Source |
|---|---|
| #368 | [368](https://github.com/kristofferR/ha-adjustable-bed/issues/368) |
| #483c | [483](https://github.com/kristofferR/ha-adjustable-bed/issues/483) |
| #516c | [516](https://github.com/kristofferR/ha-adjustable-bed/issues/516) |
| fm157 | audit ledger `157-furnimove` |
| issue558 | audit ledger `issue558-ergomotion4` |
| jensen-disp | audit ledger `jensen-disposition` |
| leggett-disp | audit ledger `leggett-app-disposition` |
| linak-guide | [linak.md](../beds/linak.md) |
| motosleep-guide | [motomotion.md](../beds/motomotion.md#stop-and-release-behavior) |
| row023 | audit ledger `row023-malouf-lucid` |
| row028 | audit ledger `row028-customatic` |
| row041 | audit ledger `row041-reverie` |
| row042 | audit ledger `row042-nectar-motion` |
| row050 | audit ledger `row050-remacro` |
| row055 | audit ledger `row055-richmat-cluster` |
| row061 | discovery ledger `implementation-row061-five/DISCOVERY-LEDGER` (PR #928) |
| row066 | audit ledger `row066-classic-richmat-apps` |
| row067 | audit ledger `row067-adjustamattress` |
| row121 | audit ledger `row121-hjbed` |
| symphony078 | Accepted Symphony Sleep 1.1.0 (14), row078, all 15 dispatch outcomes; `com.ore.bedding.symphony-1.1.0-2026-11-12-queue001/report/`. |
| row161 | accepted ComfortBaseForBluetooth 1.1.2 (6), `com.ore.yorkfeng.comfortbaseble2-1.1.2-2026-11-10-maxqueue001/report/` and independent audit001 |
| row173 | Richmat 4.2.0 accepted catalog gesture and literal STOP evidence |
| row126 | audit ledger `row126-hush-base` |
| svane-guide | [svane.md](../beds/svane.md) |

### Smart Comfort seat controls

Both accepted apps stream six motor directions and Home at 100 ms and release
with a seat-scoped zero command after 100 ms. The integration captures the seat
and release command, cancels refresh on disconnect, and does not retain the
apps' mutable release race. No concurrent commands, watchdog interval or speed
selection is proven. Memories are one-shot prepare then recall/save, outside
the held controls. See [Smart Comfort](../beds/smart-comfort.md).
