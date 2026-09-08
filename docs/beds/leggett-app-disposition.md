# Leggett app cluster implementation disposition

This is the post-freeze implementation ledger for Phase 4 row022,
`cluster-005`, against `release/4.0`. It reuses the four accepted reports from
2026-08-27. It does not replace, amend, or redistribute those reports.

## Evidence and acceptance

[Issue #443](https://github.com/kristofferR/ha-adjustable-bed/issues/443)
accepts all four members as COMPLETE and independently audited. Prodigy 2L is
the FULL representative; each sibling completed independent artifact-local
Stage 1 and was promoted to FULL after comparison. Each final report has all
17 completion gates passing and zero blockers. The implementation pass verified
every entry in each accepted report manifest and both hashes below before
changing code. The earlier July Prodigy CE artifact is a different build and is
not substituted for this corpus member.

| ID | Exact package and version | APK SHA-256 |
| --- | --- | --- |
| L | `com.leggett.prodigy2L` 1.2 (15) | `5b903311019805f4ea45414a8b96df2a225d0459a0bcea37c9621af133d3532c` |
| P | `com.leggett.prodigy2` 2.2.0 (44) | `060fe2e64e21b55543ab3101c8eb8cab460d44820c5318868215c86c3cc151bb` |
| C | `com.leggett.prodigy4` 1.2.0 (18) | `45922c518c9e8070d8a65f65762bf00f22702ac8493b36c0a3ac9f9607c571b8` |
| U | `com.leggett.useries` 2.1 (16) | `e942a6314103f34cc16306d643c0b8e1b0dd4fd4694c7b9f6bb5d18038afbd0a` |

| ID | `analysis.json` SHA-256 | `REPORT.SHA256` SHA-256 |
| --- | --- | --- |
| L | `b8a96b2dba9a7c5ef259b7999182b7423d611f33791fce710c9c8e52938e4b85` | `64118d475120cdae0d76c71223be40b277ee49d4eda0918887fadf798c0e4cc7` |
| P | `7dd2e55565c3aca3b018ed4347b987fbe4c135a3cc7482460e509a4114d3c5ee` | `f846f965066fe9a553960dbe3a18aa96f1a45388eff18050df68f73aa74263e1` |
| C | `95232bc44a6e6970abd6af4977db0863bb08ae67c88f8202470e6249d5dc00af` | `7662df4dc9cda82f19749abf3e3494ad43402186a700a6da2a0c70c39fb31255` |
| U | `124026fd8531286b7d375b3ac362877c19f0921a2eeb0f93037ddaa9716b7e37` | `eb47243874ea9d7824ec3f9a0178d84f1b8988a783d941729812fca71e6d2dc0` |

The machine-local accepted paths are under
`disassembly/output/phase4-early/<package>-<version>-20260827/`: `report/`
for L and P, `report/final/` for C, and `final-report/` for U. The manifest
entry counts are respectively 4, 4, 10, and 9. The shared signer is
`ca843e7cdc2e6d1db4fa079c03a9530772ca607cb8e2bb6717d97710026c163c`.

P's `stage2_reconciliation` resolves all eleven comparison areas and corrects
its sealed Stage 1 omission of the separate Classic sleep frame. C's
`cluster-reconciliation.tsv` resolves all eleven areas, including live pillow
commands absent from L's reachable route. U's `COMPARISON.json` resolves all
eleven areas as different, with no unresolved entry. Its independently covered
five native ABIs contain PDF/DjVu rendering only. The final U report also
corrects the earlier overbroad special-command release statement and preserves
the distinction between its reachable legacy search activity and that
activity's unusable target-selection output. These final reconciliations are
authoritative; none needs another APK analysis.

## Existing implementation retained

[PR #536](https://github.com/kristofferR/ha-adjustable-bed/pull/536), commit
`e8294e2a2b4c276bfe1e22151f48b1780b71cc1a`, is an ancestor of this worktree's
release baseline. Its implementation is in
`custom_components/adjustable_bed/beds/leggett_okin.py`. The existing focused
checks in `tests/test_leggett.py::TestLeggettOkinController` demonstrate:

- `test_revision_zero_framing_selected_when_selector_is_absent` and
  `test_revision_one_framing_selected_when_selector_is_present`: normal R0/R1
  bytes and characteristic-presence selection.
- `test_motor_surface_matches_cu170_actuators`,
  `test_motor_streams_then_sends_four_release_frames`, and
  `test_motor_stream_uses_the_proven_pulse_delay`: CE actuator commands and
  normal 100 ms held/release cadence.
- `test_favorites_match_the_prodigy_ce_model` and
  `test_memory_recall_ladder_and_burst`: Favorite 1, Favorite 2, fixed Snore,
  Favorite 3, including their ten-frame normal recall bursts.
- `test_control_modes_use_the_exact_special_command_lifecycle`: both mode
  values, 55 attempts and one explicit zero.
- `test_feedback_parser_matches_frozen_apk_vectors` and
  `test_status_channels_are_subscribed_and_settings_initialized`: existing
  LED/status transforms and optional settings initialization bytes.
- `test_light_and_massage_taps_end_with_a_release_burst` and
  `test_massage_wave_mode_is_advertised_and_sends_release`: existing CE light,
  power, intensity and wave commands with release cleanup.

The baseline does not establish the other profiles' capability gates, their
new timer services, held Snore access, or a correct favorite-store transition.
Those are implementation debt. A shared byte value alone is not an
`ALREADY_IMPLEMENTED` disposition. Existing successful CE behavior and its
focused tests remain the baseline; changed cancellation, initialization and
profile behavior are accounted for separately below.

## Complete command ledger

Each ID names the one-based command row in its accepted `analysis.json`.
L, P and C each have one protocol. U1/U2/U3 identify the R0 BLE, R1 BLE and
Classic protocols respectively. All 154 structured rows appear exactly once:
28 L + 27 P + 30 C + 23 U1 + 23 U2 + 23 U3. Dispositions total
109 `IMPLEMENTED`, 22 `ALREADY_IMPLEMENTED`, and 23 `EXCLUDED`.
P's combined rows are implemented for their BLE facet; their Classic facet is
explicitly excluded under X1 below.

| Evidence row | Discovery | Disposition | Result |
| --- | --- | --- | --- |
| `L:1` | head up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:2` | head down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:3` | foot up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:4` | foot down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:5` | lumbar up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:6` | lumbar down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:7` | flat | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:8` | underbed light toggle | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:9` | snore button | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:10` | head massage intensity up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:11` | head massage intensity down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:12` | foot massage intensity up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:13` | foot massage intensity down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:14` | massage power toggle | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:15` | massage wave selector | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:16` | favorite index 0 ui fav 1 recall | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:17` | favorite index 1 ui fav 2 recall | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:18` | favorite index 2 ui snore recall | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:19` | favorite index 3 ui fav 3 recall | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:20` | favorite store sequence | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:21` | press and hold settings mode | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:22` | press and release settings mode | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:23` | alarm timer | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `L:24` | alarm cancel | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `L:25` | sleep timer | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `L:26` | sleep timer cancel | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `L:27` | explicit release stop | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `L:28` | settings notification initialization | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:1` | release stop | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:2` | head up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:3` | head down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:4` | foot up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:5` | foot down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:6` | pillow tilt up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:7` | pillow tilt down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:8` | massage power toggle | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:9` | foot massage intensity up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:10` | head massage intensity up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:11` | memory 1 recall | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:12` | memory 2 recall | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:13` | snore or memory 3 recall | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:14` | memory 4 recall | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:15` | memory store arm | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:16` | underbed light toggle | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:17` | head massage intensity down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:18` | foot massage intensity down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:19` | flat | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:20` | massage wave | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:21` | press and hold mode | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:22` | press and release mode | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `P:23` | sleep timer cancel | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `P:24` | alarm cancel | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `P:25` | sleep timer set | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `P:26` | alarm timer set | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `P:27` | custom settings initialize | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `C:1` | pillow up | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:2` | pillow down | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:3` | head up | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:4` | head down | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:5` | foot up | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:6` | foot down | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:7` | lumbar up | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:8` | lumbar down | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:9` | flat | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:10` | underbed light toggle | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:11` | snore button | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `C:12` | head massage intensity up | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:13` | head massage intensity down | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:14` | foot massage intensity up | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:15` | foot massage intensity down | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:16` | massage power toggle | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:17` | massage wave selector | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:18` | favorite index 0 ui fav 1 recall | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:19` | favorite index 1 ui fav 2 recall | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:20` | favorite index 2 ui snore recall | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:21` | favorite index 3 ui fav 3 recall | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:22` | favorite store sequence | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `C:23` | press and hold settings mode | `IMPLEMENTED` | Existing values/counts retained; final explicit zero corrected to the next 100 ms tick. |
| `C:24` | press and release settings mode | `IMPLEMENTED` | Existing values/counts retained; final explicit zero corrected to the next 100 ms tick. |
| `C:25` | alarm timer | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `C:26` | alarm cancel | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `C:27` | sleep timer | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `C:28` | sleep timer cancel | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `C:29` | explicit release stop | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `C:30` | settings notification initialization | `ALREADY_IMPLEMENTED` | Existing Prodigy CE control; baseline tests listed below. |
| `U1:1` | head up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:2` | head down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:3` | foot up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:4` | foot down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:5` | pillow tilt up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:6` | pillow tilt down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:7` | massage on/off toggle | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:8` | foot massage intensity up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:9` | head massage intensity up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:10` | memory 1 recall | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:11` | memory 2 recall | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:12` | snore preset | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:13` | SET/program | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:14` | underbed light toggle | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:15` | head massage intensity down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:16` | foot massage intensity down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:17` | flat preset | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:18` | massage wave/pattern | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:19` | release all held keys | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U1:20` | sleep start | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `U1:21` | sleep cancel | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `U1:22` | alarm start | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `U1:23` | alarm stop | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `U2:1` | head up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:2` | head down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:3` | foot up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:4` | foot down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:5` | pillow tilt up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:6` | pillow tilt down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:7` | massage on/off toggle | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:8` | foot massage intensity up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:9` | head massage intensity up | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:10` | memory 1 recall | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:11` | memory 2 recall | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:12` | snore preset | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:13` | SET/program | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:14` | underbed light toggle | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:15` | head massage intensity down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:16` | foot massage intensity down | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:17` | flat preset | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:18` | massage wave/pattern | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:19` | release all held keys | `IMPLEMENTED` | Profile-specific control, lifecycle, and capability exposure. |
| `U2:20` | sleep start | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `U2:21` | sleep cancel | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `U2:22` | alarm start | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `U2:23` | alarm stop | `IMPLEMENTED` | Member-specific timer builder and service; normal special burst has ten attempts and no new idle release. |
| `U3:1` | head up | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:2` | head down | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:3` | foot up | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:4` | foot down | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:5` | pillow tilt up | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:6` | pillow tilt down | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:7` | massage on/off toggle | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:8` | foot massage intensity up | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:9` | head massage intensity up | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:10` | memory 1 recall | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:11` | memory 2 recall | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:12` | snore preset | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:13` | SET/program | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:14` | underbed light toggle | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:15` | head massage intensity down | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:16` | foot massage intensity down | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:17` | flat preset | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:18` | massage wave/pattern | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:19` | release all held keys | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:20` | sleep start | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:21` | sleep cancel | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:22` | alarm start | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |
| `U3:23` | alarm stop | `EXCLUDED` | Classic RFCOMM transport is outside this BLE integration. |

## Profiles and complete behavior disposition

`LeggettOkinController` retains the existing `leggett_okin` bed type. Its
explicit `app_profile` is `prodigy2l`, `prodigy2`, `prodigy4`, or `useries`;
the compatibility default is `prodigy4`. The profile describes the actual app
control surface. The independent R0/R1 selector still comes from GATT.
`leggett_app_protocol.py` contains the profile table and missing timer builders;
`beds/leggett_okin.py` owns transport, lifecycle and feedback. `services.py`
exposes native timers and bounded held controls through the coordinator.

| Profile | Actuators | Favorite surface | Additional profile gates |
| --- | --- | --- | --- |
| `prodigy2l` | Head, feet, lumbar | Favorite 1, Favorite 2, fixed Snore, Favorite 3 | Settings notification/init and both mode commands |
| `prodigy2` | Head, feet, pillow | Favorite 1, Favorite 2, fixed Snore, Favorite 3 | Settings notification/init and both mode commands; BLE only here |
| `prodigy4` | Head, feet, pillow, lumbar | Favorite 1, Favorite 2, fixed Snore, Favorite 3 | Settings notification/init and both mode commands |
| `useries` | Head, feet, pillow | Two held memory recalls, held Snore and held SET | LED notification only; no settings service, mode commands, lumbar or direct third/fourth memory recall |

All profiles have Flat, underbed-light toggle, head/foot massage intensity
up/down, massage power toggle, wave selection, sleep timer and alarm. U Series
Memory 3 exists only as a sleep-timer destination. The shared keycode declared
as a different function in a legacy constant table never overrides its live
layout binding. No measured position, calibration, RGB, brightness, split-side,
remote-code or model query is inferred from these apps.

The following 21 rows cover non-command behavior and exclusions. They are
separate from the 154 command rows: ten `IMPLEMENTED`, four
`ALREADY_IMPLEMENTED`, and seven `EXCLUDED`. The combined discovery ledger
therefore contains 175 rows: 119 implemented, 26 already implemented and
30 excluded. Candidate and comparison tables below cross-reference these rows
and do not add duplicate findings to that total.

| ID | Discovery and evidence | Disposition | Integration result |
| --- | --- | --- | --- |
| D1 | All four `variant_inventory`/capability tables and live resource bindings | `IMPLEMENTED` | Explicit profile selection, actuator and memory gates, and profile-specific available services; absent axes cannot be sent through stale aliases. |
| D2 | L/C discovery prefixes `OKIN`, `DEWERT`, `LP`; P/U `OKIN`, `DEWERT`, `LP BED CONTROL`, case-sensitive before display normalization | `IMPLEMENTED` | Preserve these admitted-device facts without treating an ambiguous shared name or service as proof of a particular app profile. The user selects the app profile. |
| D3 | All four GATT revision selectors: characteristic `00001721-0000-1000-8000-00805f9b34fb` presence in primary service | `ALREADY_IMPLEMENTED` | `_detect_protocol_revision` and the existing R0/R1 selection tests above; selector value and Device Information strings do not choose framing. |
| D4 | Shared normal R0/R1 builders; signed-byte checksum agrees modulo 256 | `ALREADY_IMPLEMENTED` | `_build_revision_0_command` and `build_okin_command`, covered by the existing frame tests. Unconfirmed, wall-clock-paced writes retain the separate established CU170 transport policy; the APK itself never calls `setWriteType`. |
| D5 | All four asynchronous BLE startup/lifecycle and backpressure traces | `IMPLEMENTED` | Resolve a usable connection before control writes; make initialization cancellation/failure retryable, and reset connection-specific state on teardown. No pre-resolution packet-counter leak is copied. |
| D6 | L/P/C optional settings service and fixed initialization; U settings route absent | `IMPLEMENTED` | Settings subscription and `01 02` initialization are profile-gated. U subscribes only to the proven LED channel. |
| D7 | All four standard Device Information read traces | `IMPLEMENTED` | Read available manufacturer, model, serial, hardware, firmware and software fields as diagnostics. They remain control-neutral and missing optional fields do not block controls. |
| D8 | All four notification operation tables and fixed parser vectors | `ALREADY_IMPLEMENTED` | Existing bounded LED/status parser, including 6/7/8/9/11, size 6 XOR exception, signed status and final 32-bit mask. Preserve the actual parser acceptance rather than add a nonexistent checksum. |
| D9 | Stored raw LED/status, alarm/sleep state and connection information | `IMPLEMENTED` | Publish retained raw status and the proven alarm/sleep indicators through the coordinator. Apply the U Series low-eight-bit display filter only to the derived indicators; keep the raw mask intact. Unknown light/massage bit meanings are not guessed from constant names. |
| D10 | Ordinary held controls and exact 100 ms/four-zero lifecycle in all reports | `IMPLEMENTED` | Existing motor/timed-move entities plus one bounded `leggett_hold_control` service cover the ordinary nonmotor held controls. Existing light/massage buttons remain short taps. |
| D11 | L/C favorite-store same-callback reset/slot transition; P equivalent 5 s/2 s flow | `IMPLEMENTED` | Store prefix 5 s then chosen editable slot 2 s with no invented intermediate four-zero gap; final four-zero cleanup. U exposes its standalone SET key and does not inherit this unproven composite. |
| D12 | All reports' normal/special release states and explicit zero frame | `IMPLEMENTED` | Fresh-event release cleanup after normal movement, failed/canceled partial movement and explicit stop. Correct bounded hold deadlines and the 100 ms interval before the mode command's explicit zero. Preserve successful special recall/timer silence; do not copy Android pause/cancel omissions. |
| D13 | Profile-specific sleep/alarm builders and ten-attempt special branches | `IMPLEMENTED` | Native timer start/cancel services use the exact profile builder, destination and allowed values, not a local delayed movement substitute. |
| D14 | Existing coordinator command locking and cancellation contract | `ALREADY_IMPLEMENTED` | Entity and service entry points use `coordinator.py::async_execute_controller_command`; stop uses the coordinator cancellation path. Existing `tests/test_coordinator.py` checks `test_stop_command_cancels_active_controller_operation`, `test_execute_controller_command_cancels_running` and `test_different_motor_command_queues_without_cancelling_active_motor`. |
| X1 | P live Classic RFCOMM and U protocol 3, including socket parser, pairing, timer frames and idle cadence | `EXCLUDED` | This integration controls BLE. Classic-only transport operations are outside the product boundary, including all U3 command rows and the Classic facets of P's combined rows. L/C Classic helpers are dead independently. |
| X2 | Every report's dead candidate ledger | `EXCLUDED` | Uncalled 90 ms senders, rename setters that never write, alternate UUIDs, unused constants, dead layout/activity/input-thread paths and simulated output. U's unused specialized sleep builder, `FD200000` alarm-cancel constant and UI-mode commands are not exposed. |
| X3 | U reachable legacy search activity writes `MyPrefsFile:lastMAC`; live target reads `USeriesPrefsFile:SELECTED_MAC` | `EXCLUDED` | The activity is reachable, but its selection output cannot affect the live bed control target. Reproducing this Android navigation dead end is unrelated to HA device selection. |
| X4 | All reports' local passcode/child lock, favorite labels, preference files and display-only countdowns | `EXCLUDED` | Android local UI/persistence mechanisms do not authenticate the bed or add a command. HA retains its own configuration and automation storage. Native timer writes are implemented separately. |
| X5 | Startup task overlap, first-Device-Information duplicate/read crash, four-packet counter leaks, callback-status ignorance and pause-without-release | `EXCLUDED` | These Android race/failure mechanisms are not protocol requirements. HA serializes operations, waits for readiness, retries initialization and performs proven release cleanup. |
| X6 | PDF/JSON/UI utility code and U's five-ABI `libvudroid.so` | `EXCLUDED` | Exhaustive accepted stack coverage finds only document rendering or unrelated library behavior, with no bed-protocol dependency. |
| X7 | App icon colors, display aliases and scan-window presentation | `EXCLUDED` | These are Android presentation choices. Preserve the parsed raw value and actual BLE identity. The U Series filter that affects derived indicator state is implemented under D9; icon styling and display renaming are not copied. |

### Timers and held operations

Prodigy sleep uses `04 02 FF position delayBE16` under both R0 and R1,
with favorite index 0..3. Prodigy alarm uses the selected normal builder for
`FD000000 + minutes`; alarm cancel is `FD200000`, sleep cancel `FF200000`.
U Series sleep uses the selected normal key builder for
`FF000000 | action | minutes`, where Flat=`00100000`, Memory 1=`00000000`,
Memory 2=`00010000`, Memory 3=`00020000`, and delay is 15/30/45/60/75/90.
U alarm stop is `FD000000`, unlike Prodigy's cancel value. All timer branches
schedule ten attempts 100 ms apart and do not initiate a new normal zero tail.

`leggett_hold_control` exposes Flat, Snore, light toggle, massage power/wave,
and both zones' intensity up/down, with U Series Memory 1, Memory 2 and SET
added only on that profile. The bounded duration is an HA interface choice;
the 100 ms repeat cadence and four-zero cleanup are artifact-proven. Prodigy
favorite recalls are a different fixed-ten-attempt path. The retained generic
anti-snore button can use that special favorite path while the bounded service
covers the separately reachable held Snore control.

A successful favorite recall does not acquire a new zero tail from ordinary
idle. The four-zero normal release is nevertheless the proven stop value for
canceling or failing a partial movement. Cleanup uses a fresh cancellation
event and completes while the coordinator still owns the command lock.

### Narrow post-freeze clarification: Prodigy sleep bounds

The accepted reports summarize sleep bounds differently: L includes 1,440,
while C distinguishes normal UI selection from defensive zero normalization.
A narrow comparison of the already-preserved `TimerSettingDialogFragment.java`
resolved this concrete implementation gap. No report or decompilation was
modified, and no new artifact analysis was performed.

All three files have the same relevant anchors: lines 97–100 create hours 0..23,
119–122 create minutes 0..59, 114/136/168 disable 00:00, and 157–162 compute minutes,
normalize nonpositive input by adding 1,440, then call the timer builder.
Thus normal selectable sleep is 1..1,439 for all three profiles. The 1,440 value
is the defensive zero-normalization branch, not a profile-specific wire limit.
Alarm scheduling separately permits 1..1,440 through forward time-of-day
wrapping. U Series has its own six-value sleep menu described above.

| Member | Existing workspace-relative source | SHA-256 |
| --- | --- | --- |
| L | `work/jadx/sources/com/leggett/prodigy2L/TimerSettingDialogFragment.java` | `75586897b7bf05996ca9db61d2d2c1fd07c7455db6d0327ec4864babce03d697` |
| P | `work/jadx/sources/com/leggett/prodigy2/TimerSettingDialogFragment.java` | `83a9f52acdfcff8513d5be314993822469179f3df5cb8b72faea6c5f522a894a` |
| C | `work/jadx-authoritative/sources/com/leggett/prodigy4/TimerSettingDialogFragment.java` | `b3c612685d7b2d3c4390bdb6306729dffcc9746ae8c71845af2e03c418ef18ae` |


### Narrow post-freeze clarification: timer indicators

The raw status parser is already proven. To expose useful timer state without
inheriting a sibling's interpretation, a second narrow comparison traced each
app's live LED binding. All three Prodigy `activity_main.xml` files bind
`btn_schedule` to mask `00008000` at line 19 and `btn_alarm` to `00004000` at
line 27. The latter's `othersleep` tag is misleading: the live `MainActivity`
click handler explicitly calls `showAlarmTimerDialog` (L/C lines 102–108,
P lines 101–107). Each base `processLEDcode` returns raw LED unchanged, and
`setLED` applies the tagged mask (L lines 530–540, P 561–571, C 551–561).

U Series independently binds the live `alarm_button` to `00004000` at
`firstview.xml:337` and `timer_button` to `00008000` at line 370. Its
`HandSetActivityBaseClass.java:260–300` consumes `processLEDcode`, while
`HandSetActivity.java:134–139` returns zero when any raw low-eight-bit value is
nonzero. The derived Alarm indicator and Sleep timer indicator therefore use
that exact U Series filter. The raw mask sensor preserves the original value.
These names describe the APK's indicators; hardware scheduling confirmation
beyond that indicator remains a physical validation question.

Existing supplemental source hashes, relative to the accepted workspaces:

| Member | Source | SHA-256 |
| --- | --- | --- |
| L/P/C | respective authoritative `resources/res/layout/activity_main.xml` | `3d6ac1c03d8fdccc7a61a3a7b63461fdafe05ad96e09e84512cc8fb8c74646e4` |
| L | `work/jadx/sources/com/leggett/prodigy2L/MainActivity.java` | `dea2e54a71343ffa881796fe771823addd409de18af643c996022883fbde914d` |
| P | `work/jadx/sources/com/leggett/prodigy2/MainActivity.java` | `3af371a8862dd8108a20fe08f5133201a8cd64f53121d41c30c14d7cbaa42c0b` |
| C | `work/jadx-authoritative/sources/com/leggett/prodigy4/MainActivity.java` | `d396b3fc2c302bfbd91b6f2645c6281011b9d7b6f3d060e7fdebac7a4830d7fa` |
| L | `work/jadx/sources/com/leggett/prodigy2L/MainActivityBase.java` | `36e0b232738790ae87be5d1a21269ff8ed3732a79b2585ad1bb3333ec405f27f` |
| P | `work/jadx/sources/com/leggett/prodigy2/MainActivityBase.java` | `a3f8cefdb1f4400b191c7b85f47516f2258eae28d453c67aa64f4595bb845b05` |
| C | `work/jadx-authoritative/sources/com/leggett/prodigy4/MainActivityBase.java` | `b94ebac745a7ec9764b6e4f2803465e9f0099c13669ee5a188004823ccbb6862` |
| U | `work/jadx/resources/res/layout/firstview.xml` | `64950a3ceeaac44324e26e39db269fd6c049e18cfd7f3c6e044a18b352a33d21` |
| U | `work/jadx/sources/com/leggett/useries/HandSetActivity.java` | `6e3c6b7c46e4eb6fbb6173a3f170fc513236fc46ea6fc4caa805df9785b9d20b` |
| U | `work/jadx/sources/com/leggett/useries/HandSetActivityBaseClass.java` | `1f5abae9f5c0d2e45f4d0d22e7c38d1e7ef648eca972836fb87432e9b2de7da6` |

The checked-state drawable confirms the highlighted indicator in each app.
The three Prodigy `header_alarm.xml` files share hash
`00f169b32b751aee9af16b8b32a17c3b610eac3ecbe338296fd2703139413f50`, and
`header_timer.xml` share `2006c361fe4e9186348a09c61db067ebe252170faf566e4307e8215c27e4069c`.
U's `alarm.xml` hash is `c5fbebc8c2c1e38d59095302a42067e92b55a8ac456ff256b503e572f452d285`,
and `timer.xml` is `689f230f63b8b47ed222b96f9aee2923e3dd44c61b18bcd0ad1b36369215b335`.
All are under the respective accepted `work/jadx*/resources/res/drawable/`.

### Narrow post-freeze clarification: mode release deadline

The baseline implementation sent 55 mode frames at 100 ms spacing, then sent
the explicit zero immediately after the last write, only 5.4 seconds after the
first frame on a fast transport. Each accepted Prodigy app's existing
`SettingsDialogFragment.java:162–176` instead creates a 5,500 ms countdown,
sets the 55-attempt special key on its first tick, and schedules the one zero
in `onFinish`. The controller preserves the proven 5.5-second deadline before
normal completion, absorbing write latency; interruption still performs
immediate cleanup. This corrects timing while retaining the existing bytes
and counts. The only inspected paths were these three preserved source files:

| Member | Existing source | SHA-256 |
| --- | --- | --- |
| L | `work/jadx/sources/com/leggett/prodigy2L/SettingsDialogFragment.java` | `ffb88330b449d6616e81fbf3385e9e43f5c273191a6f2f01d2e2a55d6c7403cb` |
| P | `work/jadx/sources/com/leggett/prodigy2/SettingsDialogFragment.java` | `3474f79bf7c445df8853aaed9a8d908f522edd825d831f55472f256c4196ecb9` |
| C | `work/jadx-authoritative/sources/com/leggett/prodigy4/SettingsDialogFragment.java` | `56a7c3f939ec0774b1afccfc1864a6a6ab82ec37fce1f4dcf8c7eab45bb79019` |

## Candidate and comparison reconciliation

All 54 accepted candidate entries are mapped below (13 L, 11 P, 13 C, 17 U).
This crosswalk includes negative, dead and unrelated candidates; it does not
promote them to device capabilities or recount the discoveries above.

| Report candidate | Scope | Disposition reference |
| --- | --- | --- |
| `L/C-BLE-ACTIVE` | BLE GATT transport and FurniBus command stream | D1, D3–D5 |
| `L/C-RFCOMM-SPP` | Classic Bluetooth RFCOMM/SPP socket candidate | X2 |
| `L/C-LEGACY-SCANNERS` | Legacy scanner-only activities/dialogs and positional GATT reads | X2 |
| `L/C-LEGACY-90MS` | Communication 90 ms key timer | X2 |
| `L/C-RENAME-GATT` | Device rename GATT constants and setter | X2 |
| `L/C-UNUSED-UUIDS` | Declared alternate 16-bit key service, revision, and 128-bit revision/protocol UUIDs | X2 |
| `L/C-UNUSED-COMMAND-CONSTANTS` | Extra motors, heater, light intensity, massage program/pulse, MLH memory, semantic stop/store constants | X2 |
| `L/C-SETTINGS-INIT` | Custom settings notification initialization write 01 02 | D6 |
| `L/C-NOTIFICATION-PARSER` | LED/status notification bitmask parser | D8–D9 |
| `L/C-PDF-JSON-THIRDPARTY` | Third-party PDF/Jackson decompiler failures and utility code | X6 |
| `L/C-AUTH-OTA-POSITION-SPLIT` | Authentication/crypto, OTA/DFU, calibration, position feedback, split/side addressing and native/dynamic protocol candidates | X2 |
| `L/C-DEAD-HANDSCHALTER` | Dead handschalteractivity -> firstview resource action route with 18 key tags, including unique 0x10/0x20 pillow keys | X2 |
| `L/C-LEGACY-INPUTTHREAD` | Legacy InputThread polling of FurniBusProtocol ledCode/status defaults | X2 |
| `P/C1` | BLE GATT transport and command stream | D1, D3–D5 |
| `P/C2` | Classic RFCOMM/SPP transport and command stream | X1 |
| `P/C3` | Custom settings notification initialization | D6 |
| `P/C4` | Device Information reads | D7 |
| `P/C5` | Rename characteristic setter | X2 |
| `P/C6` | Communication 90 ms direct-key timer | X2 |
| `P/C7` | Simulated output override | X2 |
| `P/C8` | Bed selector GATT callback and legacy LeScan callback | X2 |
| `P/C9` | ConnectDeviceDialogFragment legacy scanner | X2 |
| `P/C10` | Manifest-declared BluetoothSearchActivityBaseClass scanner | X2 |
| `P/C11` | Legacy unreferenced control layouts | X2 |
| `C/C-BLE-ACTIVE` | BLE GATT transport and FurniBus command stream | D1, D3–D5 |
| `C/C-RFCOMM-SPP` | Classic Bluetooth RFCOMM/SPP socket candidate | X2 |
| `C/C-LEGACY-SCANNERS` | Legacy scanner-only activities/dialogs and positional GATT reads | X2 |
| `C/C-LEGACY-90MS` | Communication 90 ms key timer | X2 |
| `C/C-RENAME-GATT` | Device rename GATT constants and setter | X2 |
| `C/C-UNUSED-UUIDS` | Declared alternate 16-bit key service, revision, and 128-bit revision/protocol UUIDs | X2 |
| `C/C-UNUSED-COMMAND-CONSTANTS` | Extra motors, heater, light intensity, massage program/pulse, MLH memory, semantic stop/store constants | X2 |
| `C/C-SETTINGS-INIT` | Custom settings notification initialization write 01 02 | D6 |
| `C/C-NOTIFICATION-PARSER` | LED/status notification bitmask parser | D8–D9 |
| `C/C-PDF-JSON-FRAGMENT-THIRDPARTY` | Third-party PDF/Jackson decompiler failures and utility code | X6 |
| `C/C-AUTH-OTA-POSITION-SPLIT` | Authentication/crypto, OTA/DFU, calibration, position feedback, split/side addressing and native/dynamic protocol candidates | X2 |
| `C/C-DEAD-HANDSCHALTER` | Dead firstview/handschalter resource route; its 0x10/0x20 values are independently live in fragment_position for this artifact | X2 |
| `C/C-LEGACY-INPUTTHREAD` | Legacy InputThread polling of FurniBusProtocol ledCode/status defaults | X2 |
| `U/C1` | discovery | D2 |
| `U/C2` | BLE transport | D5 |
| `U/C3` | BLE packet format | D4 |
| `U/C4` | BLE packet format | D3 |
| `U/C5` | classic transport | X1 |
| `U/C6` | selector callback | X2 |
| `U/C7` | alternate key sender | X2 |
| `U/C8` | rename GATT service | X2 |
| `U/C9` | alternate UUID constants | X2 |
| `U/C10` | legacy activity | X2 |
| `U/C11` | legacy search activity component; live-target selection output dead-end | X3 |
| `U/C12` | native library | X6 |
| `U/C13` | decompiler failures | X6 |
| `U/C14` | device information | D7 |
| `U/C15` | other application stacks | X2 |
| `U/C16` | BLE startup/backpressure state machine | D5, X5 |
| `U/C17` | sealed sibling comparison | Accepted comparison below; evidence process, no runtime feature |

Each sibling's eleven-area comparison was accepted before implementation.
Differences are resolved at the behavior boundary below, not by assuming that
all four apps share a controller surface.

| Comparison area | Prodigy 2 versus L | Prodigy 4 versus L | U Series versus L | Final disposition |
| --- | --- | --- | --- | --- |
| Delivery | Different artifact/inventory | Different artifact/inventory | Different artifact and five native ABIs | Exact identities retained; unrelated delivery/native details X6 |
| Manifest/discovery | Narrower LP prefix and Classic selection | Same live name admission | Narrower LP prefix and distinct scan/bonded/save mapping | D2; Classic transport X1; presentation X7 |
| GATT roles | Shared live BLE roles | Shared live roles | No settings extension | D3, D5–D7 |
| BLE callsites | Independent dual-transport startup trace | Equivalent active session; dead scaffolding separate | Different writer/session graph; no settings callback | D5–D6; OS defects X5 |
| Packet construction | Additional Classic sleep frame | Same builders; pillow key becomes reachable | Timer operations use normal key builder | D4, D13; Classic-only builder X1 |
| Framing/auth | Shared BLE, additional Classic bond/SPP | Equivalent BLE framing/no app auth | Shared BLE, additional Classic bond/SPP | D3–D4; Classic authentication X1 |
| Notification parsing | Same BLE plus Classic stream parser | Equivalent shared parser | Shared LED parser only plus Classic stream parser | D8–D9; Classic stream X1 |
| Commands/STOP/timing | Pillow replaces lumbar; Classic release differs | Live pillow added; normal lifecycle otherwise shared | Held memories/SET and different timers, no settings modes | Complete command ledger, D10–D13; Classic X1 |
| Resources/variants | Different live pillow layout and three routes | Four live actuators | Live firstview controls and three routes | D1; dead layouts X2 |
| Stack/native | Java only | Java only | Java plus five renderer ABIs | Complete frozen coverage reused; unrelated code X6 |
| Capability routing | Head/feet/pillow, favorites/settings | Head/feet/pillow/lumbar, favorites/settings | Head/feet/pillow, two held memories/SET, no settings | D1, D6, D10–D13 |

## Validation and remaining uncertainty

Focused checks in `tests/test_leggett_app_protocol.py`,
`tests/test_leggett_app_controller.py`, `tests/test_leggett_app_config.py`,
`tests/test_leggett_app_entities.py` and `tests/test_leggett_app_services.py`
cover each profile, both normal frame revisions,
member-specific timers, held and special-command lifecycle differences,
notification transforms, optional Device Information and settings roles,
capability/service exposure, and cancellation/failure cleanup. Existing #536
coverage is reused where the behavior is equivalent. Independent comparison
checks the complete command and candidate inventories against this ledger.
A separate comparison verified all 195 concrete normal-key frame occurrences
in the accepted BLE command rows and all eight fixed U Series parser vectors,
including the long-input wrap and odd/even field cases.

Hardware status remains unverified for these accepted APK-derived profiles.
After beta/release, users can validate characteristic properties, physical
actuator labels, timer behavior on R0 hardware, and actual LED/status meanings.
Those physical checks are deferred external validation, not unfinished
implementation or a request for the maintainer to obtain hardware. Raw APKs,
decompiled code, frozen reports and validation evidence stay machine-local.
