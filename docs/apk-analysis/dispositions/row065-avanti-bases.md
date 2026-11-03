# Row065: Avanti Bases dispositions

`com.ore.AvantiBases` **1.0.5 (7)**, standalone FULL. Accepted evidence: **17/17
independent audit gates PASS, ACCEPT**. This implementation ledger has **73
items: 4 IMPLEMENTED, 50 ALREADY_IMPLEMENTED, 19 EXCLUDED**.
Acceptance and implementation are separate counts. Hardware remains **unverified**.

Ref #436, #443, #447. Global queue updates belong to the coordinator.

| Frozen artifact | SHA-256 |
|---|---|
| Complete APK/set | `9a97eb40f71c51eab1b8750fa45692538be758e400360fdae21563d32e084bd0` |
| REPORT.SHA256 | `99ad6130cf505eeea4184d33db5d42ef05e4ec2d2ef5f6d7e5d1b42a98efc347` |
| Audit VERDICT.json | `78d7a6d0a711c28e3b27861d6f6e83db56d83cc255f637f2bafad55d56c34357` |
| Audit FINDINGS.json | `f1aeaa4d7e61fcfdcb1368f47d039daf630ff77e5ac8365e91a519328c6deddb` |

All input, report, source-evidence and audit seals were rechecked before comparison.
The package-local report is `com.ore.AvantiBases-1.0.5-2026-11-03-bulk061-001/report`.
E01-E23 below refer to that accepted report; T01-T45 to its transport ledger.
Raw evidence remains machine-local. The audit's two nonblocking clarifications
are preserved alongside it: E02/E03 manifest ranges end at 82, E13 slider bounds
are at `bed_massage.xml:134-140,173-179,212-218`; slider listeners lack touch-button
init guards, and the preset long-click callback does not recheck those guards.
No accepted evidence was edited.

## Comparison and user surface

The separate Avanti artifact proves the same frame words, 2M/3M/4M control maps,
100 ms timing, release, preset, massage and light behavior already implemented
by `OreComfortBedController`. Reuse is based on these item-by-item comparisons,
not package names or sibling assumptions. Registration adds `avanti_bases`, a
searchable app choice, per-side motor layout ownership, fixed-field hiding and
an explicit profile-review choice. Existing sibling behavior is unchanged.

[Setup, command table and entities](../../beds/ore-comfort-bed.md) describe the
profile. HA uses explicit Save and Stop actions instead of the phone's long
press and second-tap gesture state, and semantic massage levels 0-3 instead of
40 slider ticks with repeated encodings. These preserve every reachable BLE
operation. No sensor interpretation is invented for discarded reply bits.

The APK leaves write type to Android/discovered-characteristic state. The shared
controller's platform adapter selects no-response when offered, otherwise response;
this is tested software compatibility, not proof of the actual bed's ATT opcode.
No fixed service UUID, extra CCCD, PIN or initialization command is inferred.

## Discovery ledger

`ore_comfort_bed.py` means `custom_components/adjustable_bed/beds/ore_comfort_bed.py`;
other production files are under `custom_components/adjustable_bed/`.
Unqualified test names are in `tests/test_avanti_bases.py`. ALREADY_IMPLEMENTED
rows name both equivalent code and tests; tests now exercise the Avanti route.

| ID | Discovery | Disposition | Artifact evidence | Code/equivalence or exclusion reason | Validation |
|---|---|---|---|---|---|
| CMD01 | back_up | ALREADY_IMPLEMENTED | E09, E10, E11, E08, E06, E07 | ore_comfort_bed.py: LAYOUTS, motor_control_specs, _move_axis, _hold | test_avanti_movement_vectors_and_release |
| CMD02 | back_down | ALREADY_IMPLEMENTED | E09, E10, E11, E08, E06, E07 | ore_comfort_bed.py: LAYOUTS, motor_control_specs, _move_axis, _hold | test_avanti_movement_vectors_and_release |
| CMD03 | foot_up | ALREADY_IMPLEMENTED | E09, E10, E11, E08, E06, E07 | ore_comfort_bed.py: LAYOUTS, motor_control_specs, _move_axis, _hold | test_avanti_movement_vectors_and_release |
| CMD04 | foot_down | ALREADY_IMPLEMENTED | E09, E10, E11, E08, E06, E07 | ore_comfort_bed.py: LAYOUTS, motor_control_specs, _move_axis, _hold | test_avanti_movement_vectors_and_release |
| CMD05 | combined_up | ALREADY_IMPLEMENTED | E09, E08, E06, E07 | ore_comfort_bed.py: LAYOUTS, motor_control_specs, _move_axis, _hold | test_avanti_movement_vectors_and_release |
| CMD06 | combined_down | ALREADY_IMPLEMENTED | E09, E08, E06, E07 | ore_comfort_bed.py: LAYOUTS, motor_control_specs, _move_axis, _hold | test_avanti_movement_vectors_and_release |
| CMD07 | head_up | ALREADY_IMPLEMENTED | E10, E08, E06, E07 | ore_comfort_bed.py: LAYOUTS, motor_control_specs, _move_axis, _hold | test_avanti_movement_vectors_and_release |
| CMD08 | head_down | ALREADY_IMPLEMENTED | E10, E08, E06, E07 | ore_comfort_bed.py: LAYOUTS, motor_control_specs, _move_axis, _hold | test_avanti_movement_vectors_and_release |
| CMD09 | waist_label_up | ALREADY_IMPLEMENTED | E11, E08, E06, E07 | ore_comfort_bed.py: LAYOUTS, motor_control_specs, _move_axis, _hold | test_avanti_movement_vectors_and_release |
| CMD10 | waist_label_down | ALREADY_IMPLEMENTED | E11, E08, E06, E07 | ore_comfort_bed.py: LAYOUTS, motor_control_specs, _move_axis, _hold | test_avanti_movement_vectors_and_release |
| CMD11 | lumbar_up | ALREADY_IMPLEMENTED | E11, E08, E06, E07 | ore_comfort_bed.py: LAYOUTS, motor_control_specs, _move_axis, _hold | test_avanti_movement_vectors_and_release |
| CMD12 | lumbar_down | ALREADY_IMPLEMENTED | E11, E08, E06, E07 | ore_comfort_bed.py: LAYOUTS, motor_control_specs, _move_axis, _hold | test_avanti_movement_vectors_and_release |
| CMD13 | movement_release_or_same_preset_stop | ALREADY_IMPLEMENTED | E08, E12, E06, E07 | ore_comfort_bed.py: stop_all, preset_flat, preset_zero_g, preset_memory, program_flat, program_zero_g, program_memory, lights_on, lights_off, set_massage_timer_option | test_avanti_single_action_vectors |
| CMD14 | recall_zero_gravity | ALREADY_IMPLEMENTED | E12, E06, E07 | ore_comfort_bed.py: stop_all, preset_flat, preset_zero_g, preset_memory, program_flat, program_zero_g, program_memory, lights_on, lights_off, set_massage_timer_option | test_avanti_single_action_vectors |
| CMD15 | save_zero_gravity | ALREADY_IMPLEMENTED | E12, E06, E07 | ore_comfort_bed.py: stop_all, preset_flat, preset_zero_g, preset_memory, program_flat, program_zero_g, program_memory, lights_on, lights_off, set_massage_timer_option | test_avanti_single_action_vectors |
| CMD16 | recall_flat | ALREADY_IMPLEMENTED | E12, E06, E07 | ore_comfort_bed.py: stop_all, preset_flat, preset_zero_g, preset_memory, program_flat, program_zero_g, program_memory, lights_on, lights_off, set_massage_timer_option | test_avanti_single_action_vectors |
| CMD17 | save_flat | ALREADY_IMPLEMENTED | E12, E06, E07 | ore_comfort_bed.py: stop_all, preset_flat, preset_zero_g, preset_memory, program_flat, program_zero_g, program_memory, lights_on, lights_off, set_massage_timer_option | test_avanti_single_action_vectors |
| CMD18 | recall_memory_a | ALREADY_IMPLEMENTED | E12, E06, E07 | ore_comfort_bed.py: stop_all, preset_flat, preset_zero_g, preset_memory, program_flat, program_zero_g, program_memory, lights_on, lights_off, set_massage_timer_option | test_avanti_single_action_vectors |
| CMD19 | save_memory_a | ALREADY_IMPLEMENTED | E12, E06, E07 | ore_comfort_bed.py: stop_all, preset_flat, preset_zero_g, preset_memory, program_flat, program_zero_g, program_memory, lights_on, lights_off, set_massage_timer_option | test_avanti_single_action_vectors |
| CMD20 | recall_memory_b | ALREADY_IMPLEMENTED | E12, E06, E07 | ore_comfort_bed.py: stop_all, preset_flat, preset_zero_g, preset_memory, program_flat, program_zero_g, program_memory, lights_on, lights_off, set_massage_timer_option | test_avanti_single_action_vectors |
| CMD21 | save_memory_b | ALREADY_IMPLEMENTED | E12, E06, E07 | ore_comfort_bed.py: stop_all, preset_flat, preset_zero_g, preset_memory, program_flat, program_zero_g, program_memory, lights_on, lights_off, set_massage_timer_option | test_avanti_single_action_vectors |
| CMD22 | massage_head_level | ALREADY_IMPLEMENTED | E13, E14, E06, E07 | ore_comfort_bed.py: set_massage_level, massage_start, massage_off | test_avanti_massage_vectors_and_preferences |
| CMD23 | massage_foot_level | ALREADY_IMPLEMENTED | E13, E14, E06, E07 | ore_comfort_bed.py: set_massage_level, massage_start, massage_off | test_avanti_massage_vectors_and_preferences |
| CMD24 | massage_wave_level | ALREADY_IMPLEMENTED | E13, E14, E06, E07 | ore_comfort_bed.py: set_massage_level, massage_start, massage_off | test_avanti_massage_vectors_and_preferences |
| CMD25 | massage_start_sequence | ALREADY_IMPLEMENTED | E13, E06, E07 | ore_comfort_bed.py: set_massage_level, massage_start, massage_off | test_avanti_massage_vectors_and_preferences |
| CMD26 | massage_stop_sequence | ALREADY_IMPLEMENTED | E13, E06, E07 | ore_comfort_bed.py: set_massage_level, massage_start, massage_off | test_avanti_massage_vectors_and_preferences |
| CMD27 | massage_timer_10_minutes | ALREADY_IMPLEMENTED | E13, E06, E07 | ore_comfort_bed.py: stop_all, preset_flat, preset_zero_g, preset_memory, program_flat, program_zero_g, program_memory, lights_on, lights_off, set_massage_timer_option | test_avanti_single_action_vectors |
| CMD28 | massage_timer_20_minutes | ALREADY_IMPLEMENTED | E13, E06, E07 | ore_comfort_bed.py: stop_all, preset_flat, preset_zero_g, preset_memory, program_flat, program_zero_g, program_memory, lights_on, lights_off, set_massage_timer_option | test_avanti_single_action_vectors |
| CMD29 | massage_timer_30_minutes | ALREADY_IMPLEMENTED | E13, E06, E07 | ore_comfort_bed.py: stop_all, preset_flat, preset_zero_g, preset_memory, program_flat, program_zero_g, program_memory, lights_on, lights_off, set_massage_timer_option | test_avanti_single_action_vectors |
| CMD30 | light_on | ALREADY_IMPLEMENTED | E15, E06, E07 | ore_comfort_bed.py: stop_all, preset_flat, preset_zero_g, preset_memory, program_flat, program_zero_g, program_memory, lights_on, lights_off, set_massage_timer_option | test_avanti_single_action_vectors |
| CMD31 | light_off | ALREADY_IMPLEMENTED | E15, E06, E07 | ore_comfort_bed.py: stop_all, preset_flat, preset_zero_g, preset_memory, program_flat, program_zero_g, program_memory, lights_on, lights_off, set_massage_timer_option | test_avanti_single_action_vectors |
| profile | Explicit Avanti Bases app choice; never inferred from shared FFE9/FFE4 or a device name | IMPLEMENTED | E03,E04,E06 | const.py KEESON_VARIANT_AVANTI_BASES and ORE_COMFORT_BED_VARIANTS; detection.py APP_VARIANT_CHOICES; actuator_groups.py; controller_factory.py existing explicit dispatch | test_avanti_app_choice_and_side_owned_layout; tests/test_ore_comfort_bed.py::test_profile_is_explicit_and_auto_keeps_keeson |
| layout2 | bedding2: back/feet/combined, same command words have distinct roles on other layouts | ALREADY_IMPLEMENTED | E03,E09,E22 | ore_comfort_bed.py LAYOUTS[2], motor_control_specs | test_avanti_movement_vectors_and_release; test_avanti_entities_and_serialized_actions |
| layout3 | bedding3: back/feet/head | ALREADY_IMPLEMENTED | E03,E10,E22 | ore_comfort_bed.py LAYOUTS[3], motor_control_specs | test_avanti_movement_vectors_and_release; test_avanti_entities_and_serialized_actions |
| layout4 | bedding4: back/feet/waist/lumbar; preserve waist label without inferring physical semantics | ALREADY_IMPLEMENTED | E03,E11,E22 | ore_comfort_bed.py LAYOUTS[4], motor_control_specs | test_avanti_movement_vectors_and_release; test_avanti_entities_and_serialized_actions |
| profile-fields | Always-on massage, no position sensing, fixed refresh; hide irrelevant generic options | IMPLEMENTED | E08,E13,E16 | app_profiles.py _HIDDEN_BY_VARIANT; existing auto_enable_massage and motor_pulse_settings | test_avanti_app_choice_and_side_owned_layout; test_avanti_entities_and_serialized_actions |
| side-profile | Motor layout and app choice belong to one receiver; offline pair side keeps its capabilities | IMPLEMENTED | E03,E05 (one address, manual layout); HA pairing policy | app_profiles.py SideProfile with CONF_MOTOR_COUNT; const.py OFFLINE_CAPABILITY_SAFE_KEESON_VARIANTS via ORE_COMFORT_BED_VARIANTS | test_avanti_app_choice_and_side_owned_layout; tests/test_innova.py::test_pair_reload_with_one_side_offline_keeps_both_sides[avanti_bases-ore_comfort_massage_start-OreComfortBedController] |
| profile-review | Existing ORE profile review offers Avanti as an explicit choice, without auto-conversion | IMPLEMENTED | E03,E04 | profile_review.py _ORE_APPS | tests/test_profile_review.py; test_avanti_app_choice_and_side_owned_layout |
| gatt | Enumerate all services; last FFE9 write role and FFE4 presence; no fixed service UUID | ALREADY_IMPLEMENTED | E06 | ore_comfort_bed.py _resolve_write_characteristic | test_avanti_gatt_and_no_reported_state |
| write-mode | No app override of discovered characteristic write type; use platform default (no-response if offered) | ALREADY_IMPLEMENTED | E06; report limitation: no measured ATT opcode | ore_comfort_bed.py _resolve_write_characteristic, write_command; platform compatibility choice, not hardware proof | test_avanti_gatt_and_no_reported_state |
| packet | Eight bytes E5 FE 16 + big-endian low32 word + complement sum; no side/counter/encryption | ALREADY_IMPLEMENTED | E07,E23 | ore_comfort_bed.py build_frame | test_avanti_movement_vectors_and_release; test_avanti_single_action_vectors; test_avanti_massage_vectors_and_preferences; tests/test_ore_comfort_bed.py::test_builder_reproduces_every_report_vector |
| held-timing | Immediate held write then 100 ms repeats, bounded by configured pulse count | ALREADY_IMPLEMENTED | E08 | ore_comfort_bed.py motor_pulse_settings, _hold | test_avanti_movement_vectors_and_release |
| single-timing | 100 ms before each one-shot frame; no trailing zero for state/save/recall | ALREADY_IMPLEMENTED | E08,E12,E13,E15 | ore_comfort_bed.py _send_single | test_avanti_single_action_vectors; test_avanti_massage_vectors_and_preferences |
| release | Global zero after 100 ms on UP/CANCEL/outside; HA cleanup uses fresh cancel event in finally | ALREADY_IMPLEMENTED | E08-E11 | ore_comfort_bed.py _hold, _send_release, motor_control_specs scheduler_resource=* | test_avanti_cancelled_movement_releases; test_avanti_movement_vectors_and_release |
| preset-gestures | Short UP recalls, repeat tap sends zero; long-click saves and suppresses recall | ALREADY_IMPLEMENTED | E12; audit F002: long-click callback does not recheck touch guards | ore_comfort_bed.py preset_*, program_*, stop_all; separate Recall, Save and Stop actions expose every BLE result without phone gesture state | test_avanti_single_action_vectors; test_avanti_entities_and_serialized_actions |
| slider-quantization | Progress 0..39 -> floor(progress/10), defaults 10 -> level1; three independent domains | ALREADY_IMPLEMENTED | E13,E14; audit F001 corrected bed_massage.xml:134-140,173-179,212-218 | ore_comfort_bed.py MASSAGE_BASE, MASSAGE_DEFAULT_LEVEL, controller_number_specs: semantic levels 0..3 | test_avanti_massage_vectors_and_preferences |
| slider-events | Progress-change sends at multiples of 10; tracking start/stop only at nonmultiples; no touch-button guards | ALREADY_IMPLEMENTED | E13,E14; audit F002 event-vectors slider cases | ore_comfort_bed.py set_massage_level: every submitted HA level sends exactly once, preserves the resulting word; Android drag-event duplication is not a bed feature | test_avanti_massage_vectors_and_preferences |
| massage-state | Start wave/head/foot; stop head/foot zero, retains sliders and clears only local timer indication | ALREADY_IMPLEMENTED | E13 | ore_comfort_bed.py massage_start, massage_off, STATE_LEVEL, STATE_TIMER | test_avanti_massage_vectors_and_preferences |
| timer-state | 10/20/30/10 cycle without prerequisite; no timer-off word or countdown report | ALREADY_IMPLEMENTED | E13 | ore_comfort_bed.py controller_select_specs, set_massage_timer_option: explicit options for each cycle result | test_avanti_single_action_vectors; test_avanti_massage_vectors_and_preferences |
| preferences | Persist independent slider levels; restore without writes; scope per receiver/profile in HA | ALREADY_IMPLEMENTED | E13; raw progress remainder has no distinct BLE meaning | ore_comfort_bed.py persisted_app_state/restore_persisted_app_state; coordinator.py app-state storage | test_avanti_massage_vectors_and_preferences; tests/test_ore_comfort_bed.py::test_profiles_sharing_an_address_keep_separate_slots |
| light-state | Explicit on/off words with local unsynchronized flag, no confirmed state | ALREADY_IMPLEMENTED | E15 | ore_comfort_bed.py supports_discrete_light_control, light_state_is_assumed; switch.py assumed state | test_avanti_entities_and_serialized_actions; test_avanti_single_action_vectors |
| no-reported-state | No measured motor/state/capability/ACK semantics; no position target or sensor data | ALREADY_IMPLEMENTED | E16,E20 | ore_comfort_bed.py read_positions/start_notify no-ops; base supports_position_feedback=False; entity platform gates | test_avanti_gatt_and_no_reported_state; test_avanti_entities_and_serialized_actions |
| local-notify | Phone-local setCharacteristicNotification(true), no CCCD transaction or readiness dependency | EXCLUDED | E06,E16; T15 | Unrelated phone callback plumbing: Bleak subscription would write an unproven CCCD, while the only parser result is discarded. No remote feature or state is omitted. | test_avanti_gatt_and_no_reported_state asserts no subscribe/read |
| unused-parser | Nonempty FFE4 -> exact length9 -> byte7 MSB-first bits; no header/checksum/reassembly; result discarded | EXCLUDED | E16; T43,T44 | Unrelated unused computation: no field meaning or downstream state. Do not invent a sensor or implement the discarded bit array. | Not applicable |
| auth | No PIN, bond requirement, credentials, handshake or notification readiness gate | ALREADY_IMPLEMENTED | E05,E06,E20 | controller_factory.py explicit controller; ore_comfort_bed.py no auth/init write | test_avanti_gatt_and_no_reported_state; test_avanti_entities_and_serialized_actions |
| session | One configured BLE address, service discovery before controls; clear connection-owned controller on disconnect | ALREADY_IMPLEMENTED | E05,E06 | coordinator.py async_connect, async_disconnect/_on_disconnect; per-connection OreComfortBedController | test_avanti_massage_vectors_and_preferences (restart); test_avanti_entities_and_serialized_actions (setup/unload) |
| discovery-ui | Unfiltered legacy 5-second scan, display aliases, selected last address; no name/manufacturer/service rule | EXCLUDED | E04 | Phone scan implementation and UI lifecycle are unrelated to bed commands. HA manual address setup replaces it; explicit profile preserves lack of an automatic signature. | test_avanti_app_choice_and_side_owned_layout |
| android-gates | SDK>30/>23 permission/location/adapter gates; <=23 no scan; adapter enable/disable prompts | EXCLUDED | E04,E05; T01-T14,T16-T21,T35,T40,T45 | Android OS administration is unrelated to bed protocol. HA owns adapters/proxies and its discovery infrastructure. | Not applicable |
| android-session | autoConnect=false, close old GATT, bound service, onResume/touch reconnect; errors133/257 and discovery129 | EXCLUDED | E05; T25-T29,T41 | Android callback/service/error-code implementation is platform-specific. HA coordinator owns connection/retry/discovery lifecycle; do not copy stuck isDiscoverying on failures. | Not applicable |
| unsafe-queue | Shared mutable characteristic FIFO, overwrite pending values, drain regardless of status, disconnect above10 | EXCLUDED | E21; T23,T34,T39 | Safety exclusion: HA serializes immutable frame writes and awaits outcomes. Recreating corrupted pending frames or discarding failures is not protocol compatibility. | test_avanti_entities_and_serialized_actions exercises serialized action |
| unsafe-lifecycle | Screen-off/background disconnect without STOP, destroy cancels timer only, guarded CANCEL can leak runnable | EXCLUDED | E08-E11 | Safety exclusion: HA lifecycle cancellation must attempt defined release; do not reproduce surviving movement producers across reconnect. | test_avanti_cancelled_movement_releases |
| phone-timing | 300 ms preset UI disable, Android long-press threshold, screen coordinates and icon-state changes | EXCLUDED | E08,E12,E15 | Phone presentation/gesture timing is unrelated to the bed. All resulting BLE commands remain available through explicit actions. | Not applicable |
| actuator1 | Actuator1 local boolean, default false; no command transform/capability effect | EXCLUDED | E17; config:isActuator1On | Unrelated inert phone preference, not a BLE reversal setting. | Not applicable |
| actuator2 | Actuator2 local boolean, default false; no command transform/capability effect | EXCLUDED | E17; config:isActuator2On | Unrelated inert phone preference, not a BLE reversal setting. | Not applicable |
| installation | InstallationMode local boolean, default false; no BLE procedure | EXCLUDED | E17; config:isInstallationOn | Unrelated inert phone preference. | Not applicable |
| haptics | Feedback flag causes 500 ms phone vibration only | EXCLUDED | E17; config:isFeedBack | Phone haptics are unrelated to direct BLE bed control. | Not applicable |
| nickname | MAC-keyed local nickname; never transmitted to bed | EXCLUDED | E04,E17; C10 | Phone identity preference only, not a BLE rename feature; HA has local device naming. | Not applicable |
| legacy-selectors | Unreachable bedding/others/seating selectors, others init1000000F and 500 ms refresh | EXCLUDED | E18; C11; legacy:bedding/others/seating | Dead artifact routes: no live selector/adapter route; no inferred commands. | Not applicable |
| dead-resources | others_fridge/lamp/massage/music and sofa_memory/six_button/two_button; unused M1-M4 label | EXCLUDED | E18; D-others_* and D-sofa_* | Dead resources without a live inflation/handler route; no extra slots, RGB, brightness or accessory controls. | Not applicable |
| unused-transport | Unseeded read queue; read/RSSI/notify helper and descriptor-log callback | EXCLUDED | E06,E16; T22,T24,T30,T32,T33,T42 | Dead helpers/log-only callback; no live bed query or subscription path. | Not applicable |
| libraries | GIF JNI wrapper without supplied native code/live use; unused CrashHandler; permission/UI/general libraries | EXCLUDED | E19; C12-C14 | Unrelated or dead application infrastructure; no bed command, parser, transport or factory. | Not applicable |
| network | Wi-Fi provisioning/SSID/password/network admin, cloud/account and Classic sockets | EXCLUDED | E20 negative closure across all stacks | Outside direct-BLE bed scope and no reachable payload exists in this artifact. No implementation debt. | Not applicable |
| advanced-absent | OTA/firmware/calibration/reset/device-info/capability query/remote code/split-side negotiation | EXCLUDED | E20 negative closure | No reachable artifact command or parser exists. Union keys are axis controls, not partner-bed coupling; do not invent bytes or capabilities. | Not applicable |

## Source-row reconciliation

Every command row is represented once as CMD01-CMD31. The 20 layout-specific
movement listeners expand the 12 semantic movement words without adding a new
protocol. Every one of the 45 transport callsites and 66 candidate-ledger rows,
and all 10 variant-inventory entries map below to the semantic ledger; these
are coverage references, not additional completion credit.

| Source rows | Ledger items |
|---|---|
| T01, T02, T03, T04, T05, T06, T07, T08, T09, T10, T11, T12, T13, T14, T16, T17, T18, T19, T20, T21, T35, T40, T45 | android-gates |
| T15 | local-notify |
| T22, T24, T30, T32, T33, T42 | unused-transport |
| T23, T34, T39 | unsafe-queue |
| T25, T26, T27, T28, T29, T41 | android-session |
| T31, T36, T37, T38 | gatt |
| T43, T44 | unused-parser |
| C01 | packet |
| C02 | profile, discovery-ui |
| C03 | layout2, layout3, layout4 |
| C04 | CMD01, CMD02, CMD03, CMD04, CMD05, CMD06, CMD07, CMD08, CMD09, CMD10, CMD11, CMD12, CMD13 |
| C05 | CMD14, CMD15, CMD16, CMD17, CMD18, CMD19, CMD20, CMD21, preset-gestures |
| C06 | CMD22, CMD23, CMD24, CMD25, CMD26, CMD27, CMD28, CMD29, slider-events, preferences |
| C07 | CMD30, CMD31, light-state |
| C08 | unused-parser, no-reported-state |
| C09 | actuator1, actuator2, installation, haptics |
| C10 | nickname |
| C11 | legacy-selectors |
| C12 | libraries |
| C13 | libraries |
| C14 | libraries |
| D-others_fridge | dead-resources |
| D-others_lamp | dead-resources |
| D-others_massage | dead-resources |
| D-others_music | dead-resources |
| D-sofa_memory | dead-resources |
| D-sofa_six_button | dead-resources |
| D-sofa_two_button | dead-resources |
| bedding2 | layout2 |
| bedding3 | layout3 |
| bedding4 | layout4 |
| config:isActuator1On | actuator1 |
| config:isActuator2On | actuator2 |
| config:isFeedBack | haptics |
| config:isInstallationOn | installation |
| legacy:bedding | legacy-selectors |
| legacy:others | legacy-selectors |
| legacy:seating | legacy-selectors |

## Validation and limits

Avanti-specific tests cover all 20 directional controls, all four recall/save
pairs, STOP, all 12 zone levels, start/stop sequences, all 3 timer values, both
light writes, GATT role selection/presence/write modes, event/task cancellation,
preference persistence, searchable setup, side-owned layout and entity exposure
for every layout. Shared profile, factory, detection, repair and offline paired
capability tests cover the added registration. No physical bed was tested.

After beta/release, real users can validate physical axes (especially the
waist-labelled control), held/release stopping, all four save targets, massage
levels/timers, actual GATT properties/ATT opcode and notification behavior.
These are deferred external observations, not omitted app functionality or a
request for maintainer hardware. No merge or deployment is authorized here.
