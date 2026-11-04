# Row062: AMERICANSTAR 1.0 (1) implementation dispositions

Standalone FULL package `com.ore.americanstar`, app label **AMERICANSTAR**.
The accepted artifact is independently verified; hardware remains **UNVERIFIED**.
This comparison was performed only after the report was frozen and accepted.
The original analyst report's pending-audit prose is historical; the separate
round01 acceptance is authoritative. No accepted evidence was changed.

## Authority and verification

| Item | SHA-256 / result |
|---|---|
| Single APK / artifact set | `1f9c2d6e2974bb9dffd0bfa7a8a17e40c7e36eb7648ddfaff842ccac4e3ff698` |
| REPORT.SHA256 | `a1dc5e9e246a451cf5cf3aa41071fe1af80d13361e40d6fd9e46487734ad8ae8` |
| Independent round01 audit.json | `be097f4b4725e63cca0f25f3875b8cb8738d5686a135f1c2ba3fa4db1a9fe43e` |
| Audit | ACCEPT, 17 PASS, no material findings or repairs |
| Reverified seals | 72 input members, 865 evidence members, 18 report members |

Raw artifacts, decompilation and reports remain local. Evidence IDs below refer
only to this accepted package's `ANALYSIS.md` and `EVIDENCE.json`. Source anchors
are `MainActivity` (builder/GATT/timing), `BluetoothLeService` (session/receive),
`BluetoothSearchActivity` (scan), the named movement fragments, `BedMemoryFragment`,
`BedMassageFragment`, `BedLightFragment`, and `OptionsActivity`, under the
artifact's `com/ore/maxcoil` namespace. A shared namespace alone is not equivalence.

## Result

The independent report proves the same 34 distinct payloads, three layouts,
100 ms timing, delayed zero release, four recall/save slots, massage bucket
selection/start/stop/timer, explicit light words and discarded replies already
implemented by `OreComfortBedController`. All 55 frozen vectors were reconciled
against `REPORT_VECTORS` in `tests/test_ore_comfort_bed.py`, including ordered
start/stop sequences and every slider boundary. Runtime tests now exercise
AMERICANSTAR through the controller factory and coordinator, not just the builder.

The new explicit `americanstar` profile selects that proven implementation.
Users can find the app in setup and the actuator guide; motor count selects
2M/3M/4M. The profile owns massage and makes motor count a per-side setting so
shared pair edits cannot silently change another receiver's layout. Offline pair
capabilities remain available. No controller behavior was changed for siblings.
See the [user-facing protocol and setup guide](../../beds/keeson.md#ore-comfort-bed-profiles).

## Coverage and counts

61 items: **1 IMPLEMENTED**, **45 ALREADY_IMPLEMENTED**, **15 EXCLUDED**.

The ledger maps every command (31), variant (21), candidate (26 semantic
plus 43 transport candidates), and transport callsite (43) exactly once.
The 43 T rows in CANDIDATES.json duplicate TRANSPORT-CALLSITES.json and are
represented once: 121 unique inventory pointers. The local reconciliation
asserts full coverage and no duplicates. Every command applies to each layout
listed in the frozen command inventory; A05/A06 are 2M, A07/A08 are 3M,
A09-A12 are 4M; all other actions are common.

## Discovery ledger

Production paths without a prefix are under `custom_components/adjustable_bed/`.
Test names refer to the committed tests, including the Americanstar parameters.
ALREADY_IMPLEMENTED means exact existing behavior reached by the new app entry,
not prior public support for this app. EXCLUDED rows have an explicit boundary,
dead-code, unrelated-phone-UI or safety reason.

| ID | Discovery | Disposition | Artifact evidence | Implementation / test or exclusion |
|---|---|---|---|---|
| A01 | back_up: `e5 fe 16 00 00 00 01 05` | ALREADY_IMPLEMENTED | E-BedSixButtonFragment, E-BUILD, E-GATT, E-TIME, E-BedFourButtonFragment, E-BedSixButtonThreeMotorFragment | `beds/ore_comfort_bed.py` _move_axis(back); `tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero` |
| A02 | back_down: `e5 fe 16 00 00 00 02 04` | ALREADY_IMPLEMENTED | E-BedSixButtonFragment, E-BUILD, E-GATT, E-TIME, E-BedFourButtonFragment, E-BedSixButtonThreeMotorFragment | `beds/ore_comfort_bed.py` _move_axis(back); `tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero` |
| A03 | foot_up: `e5 fe 16 00 00 00 04 02` | ALREADY_IMPLEMENTED | E-BedSixButtonFragment, E-BUILD, E-GATT, E-TIME, E-BedFourButtonFragment, E-BedSixButtonThreeMotorFragment | `beds/ore_comfort_bed.py` _move_axis(feet); `tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero` |
| A04 | foot_down: `e5 fe 16 00 00 00 08 fe` | ALREADY_IMPLEMENTED | E-BedSixButtonFragment, E-BUILD, E-GATT, E-TIME, E-BedFourButtonFragment, E-BedSixButtonThreeMotorFragment | `beds/ore_comfort_bed.py` _move_axis(feet); `tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero` |
| A05 | union_up: `e5 fe 16 00 00 00 10 f6` | ALREADY_IMPLEMENTED | E-BedSixButtonFragment, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` _move_axis(both), 2M only; `tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero` |
| A06 | union_down: `e5 fe 16 00 00 00 20 e6` | ALREADY_IMPLEMENTED | E-BedSixButtonFragment, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` _move_axis(both), 2M only; `tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero` |
| A07 | head_up: `e5 fe 16 00 00 00 10 f6` | ALREADY_IMPLEMENTED | E-BedSixButtonThreeMotorFragment, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` _move_axis(head), 3M only; `tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero` |
| A08 | head_down: `e5 fe 16 00 00 00 20 e6` | ALREADY_IMPLEMENTED | E-BedSixButtonThreeMotorFragment, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` _move_axis(head), 3M only; `tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero` |
| A09 | waist_up: `e5 fe 16 00 00 00 10 f6` | ALREADY_IMPLEMENTED | E-BedWaistButtonFragment, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` _move_axis(waist), 4M only; `tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero` |
| A10 | waist_down: `e5 fe 16 00 00 00 20 e6` | ALREADY_IMPLEMENTED | E-BedWaistButtonFragment, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` _move_axis(waist), 4M only; `tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero` |
| A11 | lumbar_up: `e5 fe 16 00 00 00 40 c6` | ALREADY_IMPLEMENTED | E-BedWaistButtonFragment, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` _move_axis(lumbar), 4M only; `tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero` |
| A12 | lumbar_down: `e5 fe 16 00 00 00 80 86` | ALREADY_IMPLEMENTED | E-BedWaistButtonFragment, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` _move_axis(lumbar), 4M only; `tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero` |
| A13 | movement_release_or_repeat_preset_stop: `e5 fe 16 00 00 00 00 06` | ALREADY_IMPLEMENTED | E-TIME, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` stop_all / _send_release; generic Stop button replaces the app’s second tap; `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` |
| A14 | recall_ZG: `e5 fe 16 01 00 00 01 04` | ALREADY_IMPLEMENTED | E-MEM, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` preset_zero_g; `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` |
| A15 | save_ZG: `e5 fe 16 20 00 00 01 e5` | ALREADY_IMPLEMENTED | E-MEM, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` program_zero_g (Save Zero G button); `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` |
| A16 | recall_Flat: `e5 fe 16 01 00 00 02 03` | ALREADY_IMPLEMENTED | E-MEM, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` preset_flat; `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` |
| A17 | save_Flat: `e5 fe 16 20 00 00 02 e4` | ALREADY_IMPLEMENTED | E-MEM, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` program_flat (Save Flat button); `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` |
| A18 | recall_Memory_A: `e5 fe 16 01 00 00 08 fd` | ALREADY_IMPLEMENTED | E-MEM, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` preset_memory(1); `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` |
| A19 | save_Memory_A: `e5 fe 16 20 00 00 08 de` | ALREADY_IMPLEMENTED | E-MEM, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` program_memory(1); `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` |
| A20 | recall_Memory_B: `e5 fe 16 01 00 00 09 fc` | ALREADY_IMPLEMENTED | E-MEM, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` preset_memory(2); `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` |
| A21 | save_Memory_B: `e5 fe 16 20 00 00 09 dd` | ALREADY_IMPLEMENTED | E-MEM, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` program_memory(2); `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` |
| A22 | light_on: `e5 fe 16 31 00 00 01 d4` | ALREADY_IMPLEMENTED | E-LIGHT, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` lights_on (assumed-state switch); `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` |
| A23 | light_off: `e5 fe 16 31 00 00 00 d5` | ALREADY_IMPLEMENTED | E-LIGHT, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` lights_off (assumed-state switch); `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` |
| A24 | massage_wave: `F(0x10000020 + floor(progress/10)), progress=0..39, bucket=0..3` | ALREADY_IMPLEMENTED | E-MASS, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` set_massage_level(wave), number 0..3; `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` |
| A25 | massage_head_intensity: `F(0x10000010 + floor(progress/10)), progress=0..39, bucket=0..3` | ALREADY_IMPLEMENTED | E-MASS, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` set_massage_level(head), number 0..3; `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` |
| A26 | massage_foot_intensity: `F(0x11000010 + floor(progress/10)), progress=0..39, bucket=0..3` | ALREADY_IMPLEMENTED | E-MASS, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` set_massage_level(foot), number 0..3; `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` |
| A27 | massage_timer_10_minutes: `e5 fe 16 10 00 00 30 c6` | ALREADY_IMPLEMENTED | E-MASS, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` set_massage_timer_option(10); `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` |
| A28 | massage_timer_20_minutes: `e5 fe 16 10 00 00 31 c5` | ALREADY_IMPLEMENTED | E-MASS, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` set_massage_timer_option(20); `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` |
| A29 | massage_timer_30_minutes: `e5 fe 16 10 00 00 32 c4` | ALREADY_IMPLEMENTED | E-MASS, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` set_massage_timer_option(30); `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` |
| A30 | massage_start: `F(0x10000020+floor(wave/10)); F(0x10000010+floor(head/10)); F(0x11000010+floor(foot/10)); each raw progress=0..39` | ALREADY_IMPLEMENTED | E-MASS, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` massage_start, wave then head then foot (Start massage button); `tests/test_ore_comfort_bed.py::test_start_sends_current_wave_head_foot_levels` |
| A31 | massage_stop: `e5 fe 16 10 00 00 10 e6 ; e5 fe 16 11 00 00 10 e5` | ALREADY_IMPLEMENTED | E-MASS, E-BUILD, E-GATT, E-TIME | `beds/ore_comfort_bed.py` massage_off, head zero then foot zero (Massage off button); `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` |
| C01 | Android scan start/stop, adapter enable prompts and disable request | EXCLUDED | E-DISC | Phone adapter ownership is outside bed control. HA owns host/proxy scans; never reproduce a phone Bluetooth-disable action or its 5-second UI timer. |
| C02 | Manual address selection, no advertisement signature | ALREADY_IMPLEMENTED | E-DISC | `config_flow.py::async_step_manual_entry`, `detection.py::APP_VARIANT_CHOICES`; `tests/test_app_profiles.py::test_setup_resolves_an_app_entry_to_its_bed_type_and_variant` and `tests/test_ore_comfort_bed.py::test_profile_is_explicit_and_auto_keeps_keeson`. No added automatic matcher. |
| C03 | One receiver session, connect/discover on demand, no auth/init packet | ALREADY_IMPLEMENTED | E-CONN, E-GATT | `coordinator.py::async_connect`, factory app branch, `beds/ore_comfort_bed.py` write_command; `tests/test_ore_comfort_bed.py::test_setup_exposes_the_app_surface` and `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once`. Calls through the real coordinator, exact writes contain no handshake. HA manages the connection rather than Android bindService. |
| C04 | Last FFE9/FFE4 across all services; both required; inherited write mode | ALREADY_IMPLEMENTED | E-GATT | `beds/ore_comfort_bed.py` _resolve_write_characteristic; `tests/test_ore_comfort_bed.py::test_write_roles_follow_the_app_scan` and `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once` (request/command modes). Runtime properties choose ATT mode; not an unconditional protocol claim. |
| C05 | Mutable characteristic FIFO, callback drain, >10 backlog disconnect, no ACK retry | EXCLUDED | E-CONN | Safety: the app aliases queued values and can drop/overwrite movement or release. HA command locking plus immutable payloads and bounded GATT retry replace this queue. `coordinator.py::async_execute_controller_command`, `beds/base.py::_write_gatt_with_retry`; no app queue is reproduced. |
| C06 | Eight-byte big-endian low32 key, complement sum | ALREADY_IMPLEMENTED | E-BUILD | `beds/ore_comfort_bed.py` build_frame; `tests/test_ore_comfort_bed.py::test_builder_reproduces_every_report_vector` (34 distinct frames, also reconciled against all 55 Americanstar vectors). |
| C07 | Local-only FFE4 enable; nine-byte byte7 bit extraction discarded | EXCLUDED | E-NOTIFY, E-GATT | No state or command dependency consumes the bits. Do not add a CCCD write absent from the artifact or synthesize bed feedback. `beds/ore_comfort_bed.py` start_notify/read_positions are no-ops; `tests/test_ore_comfort_bed.py::test_notifications_are_never_subscribed`. |
| C08 | Characteristic read wrapper/queue and read continuations | EXCLUDED | E-CONN | Dead code: no caller populates the read queue; read continuations cannot initiate themselves (C08, T27/T29/T41). |
| C09 | Notification wrapper | EXCLUDED | E-GATT | Dead code: no caller; MainActivity uses its separate local enable path (C07). |
| C10 | Remote RSSI wrapper and logging callback | EXCLUDED | E-CONN | Dead code: getRssiVal has no caller. HA advertisement RSSI remains independent. |
| C11 | Descriptor callback logging | EXCLUDED | E-GATT | Dead code: no descriptor write exists; no descriptor protocol to implement. |
| C12 | Two-motor back/feet/union controls | ALREADY_IMPLEMENTED | E-BedSixButtonFragment | `beds/ore_comfort_bed.py` LAYOUTS[2], _hold; `tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero`, `tests/test_ore_comfort_bed.py::test_motor_count_selects_the_app_screen`. |
| C13 | Three-motor back/feet/head controls | ALREADY_IMPLEMENTED | E-BedSixButtonThreeMotorFragment | `beds/ore_comfort_bed.py` LAYOUTS[3], _hold; `tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero`, `tests/test_ore_comfort_bed.py::test_motor_count_selects_the_app_screen`. |
| C14 | Four-motor back/feet page | ALREADY_IMPLEMENTED | E-BedFourButtonFragment | `beds/ore_comfort_bed.py` LAYOUTS[4], _hold; `tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero`, `tests/test_ore_comfort_bed.py::test_motor_count_selects_the_app_screen`. |
| C15 | Four-motor waist/lumbar page | ALREADY_IMPLEMENTED | E-BedWaistButtonFragment | `beds/ore_comfort_bed.py` LAYOUTS[4], _hold; `tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero`, `tests/test_ore_comfort_bed.py::test_motor_count_selects_the_app_screen`. |
| C16 | Four recall/save slots and same-preset zero | ALREADY_IMPLEMENTED | E-MEM | `beds/ore_comfort_bed.py` preset_*/program_* and stop_all; `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once`. Save buttons replace long press; explicit Stop replaces ambiguous fragment-local second-tap state. 300 ms animation is UI debounce, not motor timing. |
| C17 | Wave/head/foot bucket sliders, default 1, persist on release | ALREADY_IMPLEMENTED | E-MASS, E-RES | `beds/ore_comfort_bed.py` set_massage_level, restore_persisted_app_state; `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once`, `tests/test_ore_comfort_bed.py::test_slider_levels_persist_across_restarts`. HA exposes the four effective levels, not duplicate raw progress 0..39 values. |
| C18 | Ordered massage Start/Stop and timer selection/reset | ALREADY_IMPLEMENTED | E-MASS | `beds/ore_comfort_bed.py` massage_start/massage_off/set_massage_timer_option; `tests/test_ore_comfort_bed.py::test_start_sends_current_wave_head_foot_levels`, `tests/test_ore_comfort_bed.py::test_massage_levels_timer_and_stop_publish_app_state`. |
| C19 | Explicit light on/off selected by local boolean | ALREADY_IMPLEMENTED | E-LIGHT | `beds/ore_comfort_bed.py` lights_on/lights_off/light_state_is_assumed; `tests/test_ore_comfort_bed.py::test_light_switch_reports_assumed_state`. |
| C20 | Actuator1/2, installation booleans and phone vibration | EXCLUDED | E-OPTIONS | Unrelated phone settings: boolean getters populate switches only; none changes BLE or reverses axes. Vibration is local phone feedback, not a bed actuator. |
| C21 | Fourteen unused selectors, accessory/sofa screens and others refresh | EXCLUDED | E-SELECT, E-RES | Dead code: factory only reaches bedding2/3/4; VIEW_OTHERS cannot be selected. Do not expose its 0x1000000f word or 500 ms timer; unused lamp/music/fridge resources are not bed features. |
| C22 | Address-to-alias preference and name display | EXCLUDED | E-DISC | Phone-local identity UI, no device rename packet. HA device/entity names already provide local naming. Do not reproduce the null-name display bug. |
| C23 | Four native GIF libraries | EXCLUDED | E-NATIVE | Third-party image rendering, no BLE transport or bed behavior. |
| C24 | Support/UI/commons helpers | EXCLUDED | C24, E-RES | Third-party phone UI/helpers, no alternate transport. |
| C25 | CrashHandler and Android Build/device information | EXCLUDED | C25 | Unused phone diagnostics (no init caller), not bed firmware or diagnostics. |
| C26 | Screen-off/background disconnect and absent lifecycle STOP | EXCLUDED | E-CONN, E-TIME | Phone activity lifecycle is not HA lifecycle. Safety: never reproduce missing cleanup on cancellation/discovery. HA retains intentional disconnect cleanup and release in finally with a fresh event. `tests/test_ore_comfort_bed.py::test_release_is_sent_even_when_the_hold_was_cancelled` proves zero survives cancellation. |
| P01 | App-findable AMERICANSTAR profile and per-side layout | IMPLEMENTED | E-ID, E-SELECT | `const.py::KEESON_VARIANT_AMERICANSTAR`, `detection.py::APP_VARIANT_CHOICES`, `actuator_groups.py`, `profile_review.py`, `app_profiles.py`, `beds/ore_comfort_bed.py::ORE_COMFORT_BED_APPS`; `tests/test_app_profiles.py::test_americanstar_profile_owns_massage_and_per_side_layout`, setup/options tests, `tests/test_innova.py::test_pair_reload_with_one_side_offline_keeps_both_sides`. Factory reuses the proven controller; Auto and sibling controller behaviors are unchanged. |
| P02 | Held immediate write + 100 ms refresh, one-shots/release delayed 100 ms | ALREADY_IMPLEMENTED | E-TIME | `beds/ore_comfort_bed.py` motor_pulse_settings, _hold, _send_single, _send_release; `tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero`, `tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once`. User pulse count bounds the hold; it is not an APK fixed repeat count. |
| P03 | Only requested/local state; no measured position/capability/auth/config protocol | ALREADY_IMPLEMENTED | E-NOTIFY, E-SELECT, E-MASS, E-LIGHT | `beds/ore_comfort_bed.py` motor_control_specs, controller_*_specs, persisted_app_state, protocol_diagnostics; `tests/test_ore_comfort_bed.py::test_setup_exposes_the_app_surface`, `tests/test_ore_comfort_bed.py::test_massage_levels_timer_and_stop_publish_app_state`, `tests/test_ore_comfort_bed.py::test_light_switch_reports_assumed_state`. Fixed app capabilities, no firmware/model probe, state remains assumed where appropriate. |
| P04 | Wi-Fi provisioning/network management, cloud/account, OTA, side-address and advanced feature search | EXCLUDED | ANALYSIS.md feature-domain checklist; SEARCH_LOG.md; E-OPTIONS, E-RES | No reachable implementation found. Wi-Fi/cloud/provisioning would be outside the BLE-only product boundary even if carried over BLE. No commands invented for absent auth/PIN/bond, rename/config, brightness/color, alarm/lock, OTA or on-wire split-side functions. Two physical addresses use HA paired routing. |

## Inventory mapping

| Ledger row | Frozen inventory pointers |
|---|---|
| A01 | command:back_up |
| A02 | command:back_down |
| A03 | command:foot_up |
| A04 | command:foot_down |
| A05 | command:union_up |
| A06 | command:union_down |
| A07 | command:head_up |
| A08 | command:head_down |
| A09 | command:waist_up |
| A10 | command:waist_down |
| A11 | command:lumbar_up |
| A12 | command:lumbar_down |
| A13 | command:movement_release_or_repeat_preset_stop |
| A14 | command:recall_ZG |
| A15 | command:save_ZG |
| A16 | command:recall_Flat |
| A17 | command:save_Flat |
| A18 | command:recall_Memory_A |
| A19 | command:save_Memory_A |
| A20 | command:recall_Memory_B |
| A21 | command:save_Memory_B |
| A22 | command:light_on |
| A23 | command:light_off |
| A24 | command:massage_wave |
| A25 | command:massage_head_intensity |
| A26 | command:massage_foot_intensity |
| A27 | command:massage_timer_10_minutes |
| A28 | command:massage_timer_20_minutes |
| A29 | command:massage_timer_30_minutes |
| A30 | command:massage_start |
| A31 | command:massage_stop |
| C01 | candidate:C01, transport:T01, transport:T02, transport:T03, transport:T04, transport:T05, transport:T06, transport:T07, transport:T08, transport:T13, transport:T14 |
| C02 | candidate:C02, transport:T09, transport:T10, transport:T11, transport:T12 |
| C03 | candidate:C03, transport:T20, transport:T21, transport:T22, transport:T23, transport:T30, transport:T35, transport:T36, transport:T40 |
| C04 | candidate:C04, transport:T15, transport:T16, transport:T17, transport:T39 |
| C05 | candidate:C05, transport:T28, transport:T43 |
| C06 | candidate:C06, transport:T19 |
| C07 | candidate:C07, transport:T18, transport:T32, transport:T33 |
| C08 | candidate:C08, transport:T27, transport:T29, transport:T41 |
| C09 | candidate:C09, transport:T42 |
| C10 | candidate:C10, transport:T38 |
| C11 | candidate:C11, transport:T31 |
| C12 | candidate:C12, variant:bedding2 |
| C13 | candidate:C13, variant:bedding3 |
| C14 | candidate:C14, variant:bedding4 |
| C15 | candidate:C15 |
| C16 | candidate:C16 |
| C17 | candidate:C17 |
| C18 | candidate:C18 |
| C19 | candidate:C19 |
| C20 | candidate:C20, variant:option:isActuator1On, variant:option:isActuator2On, variant:option:isFeedBack, variant:option:isInstallationOn |
| C21 | candidate:C21, variant:unused:bedFourButtons, variant:unused:bedMassage, variant:unused:bedMemory, variant:unused:bedSixButtons, variant:unused:bedding, variant:unused:others, variant:unused:othersFridge, variant:unused:othersLamp, variant:unused:othersMassage, variant:unused:othersMusic, variant:unused:seating, variant:unused:sofaMemory, variant:unused:sofaSixButtons, variant:unused:sofaTwoButtons |
| C22 | candidate:C22, transport:T24, transport:T25, transport:T26 |
| C23 | candidate:C23 |
| C24 | candidate:C24 |
| C25 | candidate:C25 |
| C26 | candidate:C26, transport:T34, transport:T37 |

## Validation and external limits

Focused tests cover packet bytes, every layout action, delayed one-shots,
release despite cancellation, GATT role selection/write mode, no subscription,
app-state persistence, setup/options, entity exposure and offline paired routing.
The shared coordinator continues to serialize commands and STOP cleanup.

Physical actuator mapping (especially union/waist), actual ATT properties,
release/disconnect behavior, preset save/recall, wave patterns and massage timer
durations remain deferred validation for real users after beta/release. No
maintainer hardware is required to complete the static implementation. No
unaccounted in-scope feature is deferred to hardware testing.
