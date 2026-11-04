# Row108 BedSense implementation discovery ledger

Ref #436, #443 and #447. Separate source comparison after independent acceptance,
not a clean-room report. This standalone unit is `com.fenmenbielei.bedsense`
1.8/code 18. The revised `work/report-continuation-001` is authoritative; the
original report is superseded history. Hardware behavior remains unverified.
No raw APK, decompilation or audit/report artifact is committed.

- Artifact-set SHA-256: `00845e87a3810642ab9c229f92dbcf1e6ef810eaee46f95e013050693751d42e`.
- Accepted report manifest SHA-256: `6b65efe09634adeeeda63c5066da0294d544d7bc275abc342e6e3f695a515f56`.
- Independent round002 audit manifest SHA-256: `fd68b61959e5aa6e26c7e3fad78a03af74da90253c8aba320195e17d7959ade3`.
- Both manifests and every listed member verified read-only before comparison.
  Independent verdict ACCEPT, 17 supported gates, AUD-001/002/003 closed.

Evidence below names package-local classes and accepted report IDs. Source
locations refer to the frozen artifact's `work/jadx/sources` (and matching smali),
not the integration. Code paths are relative to `custom_components/adjustable_bed`.
Tests are `tests/test_bedsense.py` unless qualified. Each row has exactly one
implementation disposition; cross-index rows reference the same behavior rather
than inventing additional protocol features.

## Discovery, transport, lifecycle and consumers

| ID | Discovery and exact evidence | Disposition | Implementation and validation |
| --- | --- | --- | --- |
| D01 | ShuShiBanActivity:731–766,396–420; nine case-sensitive ordered name selectors, no manufacturer/service/RSSI gate | IMPLEMENTED | `beds/bedsense.py:bedsense_layout`, factory and explicit variant table. `test_case_sensitive_ordered_selection`, `test_factory_and_explicit_app_registration`, `test_nine_fresh_layouts_expose_only_proven_controls`, `test_offline_factory_uses_stored_raw_name_and_live_address_falls_back`. Offline capability controllers use the stored raw name, never HA display names. Short substrings classify only an explicitly selected BedSense app, never new discovery signatures. |
| D02 | BluetoothLeService:201 and ShuShiBanActivity:843–886; selected MAC, all services, every FFE1 characteristic, last write target | IMPLEMENTED | `_roles`, `start_notify`, `write_command`; `test_session_duplicate_roles_read_and_five_query_order`. No guessed service UUID or fallback transport. |
| D03 | BluetoothLeService:255–276; notifications/CCCD 01 00 and delayed read of matching roles | IMPLEMENTED | Bleak `start_notify` owns CCCD; read every match after 200 ms, unwind failed setup and subscriptions. `test_session_duplicate_roles_read_and_five_query_order`, `test_setup_failure_unsubscribes_and_disconnect_resets_parser`. |
| D04 | BluetoothLeService:236–241; unchanged Android characteristic write type, no app repeat/queue/retry | IMPLEMENTED | Single literal write, discovered no-response property otherwise response, exact last characteristic object. `test_artifact_command_vectors_through_writer`, `test_session_duplicate_roles_read_and_five_query_order`. No checksum or arbitrary packet builder. |
| D05 | HHKuaiJieFragment:973–1082; five queries at 2000 ms then 200 ms spacing, groups default/68/7 | IMPLEMENTED | `_query_memory`, initial setup and Refresh memory indicators action. `test_session_duplicate_roles_read_and_five_query_order`; C065–C079 vectors. Serialized reads add their completion latency to nominal startup timing. |
| D06 | Whole-DEX negative searches and accepted protocol session/feature domains: no auth, PIN, bond, MTU, firmware/DFU/config/calibration, side address or measured-position protocol | IMPLEMENTED | Fixed direct-BLE profile, no invented handshake, single-address pairing disabled, no angle/position specs, five explicit memories. `test_nine_fresh_layouts_expose_only_proven_controls`; all session writes tested as the five known queries. |
| D07 | HHWeiTiaoFragment:404–930; one DOWN write, no MOVE refresh, D7 00 on UP/CANCEL | IMPLEMENTED | Covers hold for HA's finite requested window and shield release with fresh cancel event in finally, all resources `*`. `test_artifact_command_vectors_through_writer`, `test_movement_event_and_task_cancellation_always_release`, `test_other_axis_stop_preempts_held_movement_through_scheduler`, `test_movement_write_timeout_propagates_after_release`. Only hold expiry is swallowed, never a GATT timeout. No protocol repeat cadence inferred. |
| D08 | HHKuaiJieFragment:92–243,329–686; short recall, two-second save/clear, flags choose stored/builtin, types6/8 special Flat | IMPLEMENTED | Explicit HA save/clear and recalls replace gesture timers; M1/M2 require flags, special Flat unconditional slot5 recall. `test_saved_flags_recall_fallback_and_special_flat`; every literal tested. |
| D09 | HHWeiTiaoFragment:171–263; two-second circulation UI toggle sends nothing, subsequent clicks write; type9 separate lift clicks | IMPLEMENTED | Layout-gated circulation and RISE/DECLINE buttons. `test_nine_fresh_layouts_expose_only_proven_controls`, `test_artifact_command_vectors_through_writer`; no appended click release. |
| D10 | HHAnMoFragment:84–357; ungated step writes, bounded local counters, mutually exclusive timer toggles | IMPLEMENTED | Six step buttons, three timer buttons plus explicit cancel; app counters and selection sensors. `test_massage_timer_toggle_steps_and_light_duration_are_local`, `test_reconnect_retains_timer_toggle_steps_and_indicators_per_address`; app session retains selections across BLE reconnect, not HA restart. No measured intensity or notifications updating counters/timer. |
| D11 | HHDengGuangFragment:74–155 plus repaired binary XML evidence; 10 min, 8 h, 10 h labels, root D7 00 | IMPLEMENTED | Three duration buttons and selected-duration sensor. Literal tests C062–C064 and local state test. No brightness/color/off assumption. |
| D12 | BluetoothLeService:74–107; uppercase spaced trailing-space broadcasts for reads, notifications and local writes | IMPLEMENTED | `_parse`, `_notification`, successful write callback. `test_failed_write_does_not_publish_success_and_cancel_skips_clicks`, memory vectors. Local writes are explicitly app indicators, not hardware acknowledgments. `test_write_completion_retains_local_selection_when_stop_arrives` verifies successful writes commit local selection even when STOP arrives at write completion. |
| D13 | HHKuaiJieFragment:688–919; 41 ordered memory predicates, global flags, n association, exact exceptions and unmatched n10 | IMPLEMENTED | `profiles/ff_frame.py:BEDSENSE_MEMORY_RULES`, `_parse`, per-bed persistent flags; `test_all41_memory_predicates`, `test_parser_order_exact_matches_unmatched_and_default_m1_gap`, `test_memory_persistence_is_per_app_without_cross_device_state`. No synthesized default M1 association. |
| D14 | HHAnMoFragment displayData:287–345; head/foot both update head bar; wave widths; 00 1C resets bars | IMPLEMENTED | `_parse` preserves original consumer, app-display sensors; `test_massage_parser_app_bar_vectors`. Widths are not physical percentages. |
| D15 | HHWeiTiaoFragment displayData:71–155; independent circulation tests, later wins, mixed exact/contains, hip types4/5 | IMPLEMENTED | `_parse`, circulation sensor; `test_circulation_consumer_vectors`. Parser-only E4 D7 4B at offset6=05 remains distinct from dead writer at offset6=00. |
| D16 | Prefer:53–101 persists global M1–M5 flags; app TYPE/view state can leak across targets | IMPLEMENTED | `persisted_app_state` and stable `bedsense` app key use existing per-physical-address store; restore validates bool before mutation. `test_memory_persistence_is_per_app_without_cross_device_state`, `test_reconnected_memory_flags_reach_cached_service_preflight`; live/offline flags are shared through `app_session`, in-place validated restore preserves that identity. No cross-bed global flags. |
| D17 | Repaired capability matrix, nine fresh XML/onResume layouts and labels, type3 WAIST/HIP conflict, type9 HIP/LIFT | IMPLEMENTED | Exact layout axes, app-labelled covers/buttons, no physical motor-count inference. `test_nine_fresh_layouts_expose_only_proven_controls`; user docs retain label conflict. |
| D18 | All four fragment consumers and reachable actions | IMPLEMENTED | Generic HA covers, preset/memory and controller buttons, sensor/binary-sensor specs; side-scoped stale cleanup. `test_profile_entity_exposure_and_cleanup_is_side_scoped`; frontend `discovery.test.ts` BedSense action/indicator case; rebuilt card bundle. Public entity actions provide automation exposure without a raw arbitrary-command service. |
| D19 | ShuShiBanActivity lifecycle:126–261,509–519,619–713,805–817,890–955; selected address connect/disconnect | ALREADY_IMPLEMENTED | `coordinator_connection.py:async_ensure_connected`, `async_disconnect`, existing HA Bluetooth adapter/proxy/freshness and command ownership; `tests/test_bluetooth_modernization.py::test_cancelled_connect_releases_state_and_can_reconnect`, `tests/test_bluetooth_transport.py`, `tests/test_binary_sensor_connection.py`. Matching controller initialization remains D02–D05. |
| X01 | C080/ShuShiBanActivity:876, current characteristic value never assigned in that path | EXCLUDED | Safety: null/stale arbitrary initialization write has no proven payload or bed feature; do not replay a previous movement or invent initialization bytes. Defined queries initialize supported app indicators. |
| X02 | ShuShiBanActivity:843–886/BluetoothLeService:276; indiscriminate descriptor reads | EXCLUDED | Unrelated GATT enumeration, no bed consumer or config effect. CCCD setup is D03; support capture already enumerates GATT. |
| X03 | HHAnMoFragment:269; GONE sw_on_off, literal `FF FF FF FF 05 00 00 00 1C D9 DD` | EXCLUDED | Dead/unreachable UI, distinct from reachable timer-cancel `1C D6 C9`. No invented massage-off action. |
| X04 | HHWeiTiaoFragment:209; non-type1 parent branch `FF FF FF FF 05 00 00 00 E4 D7 4B` | EXCLUDED | Dead: only type1 exposes that parent and selects E8. Do not expose dead circulation writer. Its different incoming indicator is D15. |
| X05 | Alternate HaoHuaBanActivity launcher GONE/not exported; SettingActivity/ConnectActivity alternate route | EXCLUDED | Dead/unreachable routes, not additional stable hardware profiles. |
| X06 | HHKuaiJieFragment k6, readRssi, OnDataAvailableListener, fragment timerTask fields, ConfirmUtils.isPassword without caller | EXCLUDED | Dead scaffolding. Five queries end without sixth action. Password helper is not authentication. |
| X07 | Url/NetworkUtils/QrCodeActivity, image/cache/QR sharing, databinding/support libraries, ShuShiBanActivity toast-only phone setting, MyApplication stream close | EXCLUDED | Phone/app infrastructure unrelated to direct BLE bed features. No bed WiFi/SSID/password/cloud/account/provisioning path found; these domains remain excluded by product boundary. |
| X08 | App shared gesture counters/CANCEL omission, missing lifecycle STOP, ignored write failures, global stale target/view state | EXCLUDED | Safety: HA uses explicit save/clear actions, per-bed state, serialized writes, failed-write errors and guaranteed movement cleanup (D07/D08/D12/D16). No delayed save after cancellation or stale write is reproduced. Gesture-only labels/phone scan animation/display name substitutions have no BLE effect. |

## Exhaustive fixed command dispositions

Every fixed row C001–C079 is IMPLEMENTED. `profiles/ff_frame.py:BEDSENSE_ACTIONS` retains
the accepted row ID, exact frame and layout gate; the independent frozen vector
fixture drives `test_artifact_command_vectors_through_writer` through the real
writer. Matching layouts are also checked against the fresh capability matrix.
Arrows use covers with release; queries are initialization/refresh; save/recall
uses standard memory APIs; other rows are explicit app buttons or named presets.
C017 also covers quick/light background taps; C018 preserves distinct movement/
massage background semantics. C080 has the single EXCLUDED disposition X01.

| Row | Action key | Disposition |
| --- | --- | --- |
| C001 | `back_up` | IMPLEMENTED |
| C002 | `back_down` | IMPLEMENTED |
| C003 | `head_up` | IMPLEMENTED |
| C004 | `head_down` | IMPLEMENTED |
| C005 | `lift_up` | IMPLEMENTED |
| C006 | `lift_down` | IMPLEMENTED |
| C007 | `waist_up` | IMPLEMENTED |
| C008 | `waist_down` | IMPLEMENTED |
| C009 | `hip_up` | IMPLEMENTED |
| C010 | `hip_down` | IMPLEMENTED |
| C011 | `legs_up` | IMPLEMENTED |
| C012 | `legs_down` | IMPLEMENTED |
| C013 | `rise_and_fall_up` | IMPLEMENTED |
| C014 | `rise_and_fall_down` | IMPLEMENTED |
| C015 | `back_and_leg_up` | IMPLEMENTED |
| C016 | `back_and_leg_down` | IMPLEMENTED |
| C017 | `release` | IMPLEMENTED |
| C018 | `background_tap` | IMPLEMENTED |
| C019 | `circulation_whole_body` | IMPLEMENTED |
| C020 | `circulation_default` | IMPLEMENTED |
| C021 | `circulation_back_and_leg` | IMPLEMENTED |
| C022 | `circulation_head` | IMPLEMENTED |
| C023 | `circulation_waist` | IMPLEMENTED |
| C024 | `circulation_hip` | IMPLEMENTED |
| C025 | `circulation_legs` | IMPLEMENTED |
| C026 | `flat` | IMPLEMENTED |
| C027 | `lumbar` | IMPLEMENTED |
| C028 | `music` | IMPLEMENTED |
| C029 | `leg_relax` | IMPLEMENTED |
| C030 | `rise` | IMPLEMENTED |
| C031 | `decline` | IMPLEMENTED |
| C032 | `save_m1` | IMPLEMENTED |
| C033 | `clear_m1` | IMPLEMENTED |
| C034 | `recall_m1` | IMPLEMENTED |
| C035 | `save_m2` | IMPLEMENTED |
| C036 | `clear_m2` | IMPLEMENTED |
| C037 | `recall_m2` | IMPLEMENTED |
| C038 | `save_tv` | IMPLEMENTED |
| C039 | `clear_tv` | IMPLEMENTED |
| C040 | `recall_tv` | IMPLEMENTED |
| C041 | `builtin_tv` | IMPLEMENTED |
| C042 | `save_zero_g` | IMPLEMENTED |
| C043 | `clear_zero_g` | IMPLEMENTED |
| C044 | `recall_zero_g` | IMPLEMENTED |
| C045 | `builtin_zero_g` | IMPLEMENTED |
| C046 | `save_anti_snore` | IMPLEMENTED |
| C047 | `clear_anti_snore` | IMPLEMENTED |
| C048 | `recall_anti_snore` | IMPLEMENTED |
| C049 | `builtin_anti_snore` | IMPLEMENTED |
| C050 | `save_flat` | IMPLEMENTED |
| C051 | `recall_flat` | IMPLEMENTED |
| C052 | `massage_head_up` | IMPLEMENTED |
| C053 | `massage_head_down` | IMPLEMENTED |
| C054 | `massage_foot_up` | IMPLEMENTED |
| C055 | `massage_foot_down` | IMPLEMENTED |
| C056 | `massage_wave_up` | IMPLEMENTED |
| C057 | `massage_wave_down` | IMPLEMENTED |
| C058 | `massage_timer_10` | IMPLEMENTED |
| C059 | `massage_timer_20` | IMPLEMENTED |
| C060 | `massage_timer_30` | IMPLEMENTED |
| C061 | `massage_timer_cancel` | IMPLEMENTED |
| C062 | `light_10_min` | IMPLEMENTED |
| C063 | `light_8_h` | IMPLEMENTED |
| C064 | `light_10_h` | IMPLEMENTED |
| C065 | `query_default_3` | IMPLEMENTED |
| C066 | `query_default_4` | IMPLEMENTED |
| C067 | `query_default_1` | IMPLEMENTED |
| C068 | `query_default_2` | IMPLEMENTED |
| C069 | `query_default_5` | IMPLEMENTED |
| C070 | `query_68_3` | IMPLEMENTED |
| C071 | `query_68_4` | IMPLEMENTED |
| C072 | `query_68_1` | IMPLEMENTED |
| C073 | `query_68_2` | IMPLEMENTED |
| C074 | `query_68_5` | IMPLEMENTED |
| C075 | `query_7_3` | IMPLEMENTED |
| C076 | `query_7_4` | IMPLEMENTED |
| C077 | `query_7_1` | IMPLEMENTED |
| C078 | `query_7_2` | IMPLEMENTED |
| C079 | `query_7_5` | IMPLEMENTED |
| C080 | Unassigned/current-value initialization attempt | EXCLUDED (X01) |

## Complete source boundary cross-index

All 127 transport/search receipts and every other accepted candidate are mapped
below. Source method/line anchors make dead versus reachable reasons reviewable;
none is left as implementation debt. T043's reachable type1 write is implemented,
while its non-type1 dead subbranch has X04's explicit exclusion.

| Candidate | Artifact source | Disposition | Ledger evidence |
| --- | --- | --- | --- |
| T001 | `service/BluetoothLeService.java:47` | ALREADY_IMPLEMENTED | D19 |
| T002 | `service/BluetoothLeService.java:52` | ALREADY_IMPLEMENTED | D19 |
| T003 | `service/BluetoothLeService.java:53` | ALREADY_IMPLEMENTED | D19 |
| T004 | `service/BluetoothLeService.java:168` | ALREADY_IMPLEMENTED | D19 |
| T005 | `service/BluetoothLeService.java:201` | ALREADY_IMPLEMENTED | D19 |
| T006 | `service/BluetoothLeService.java:208` | ALREADY_IMPLEMENTED | D19 |
| T007 | `service/BluetoothLeService.java:213` | ALREADY_IMPLEMENTED | D19 |
| T008 | `service/BluetoothLeService.java:217` | ALREADY_IMPLEMENTED | D19 |
| T009 | `service/BluetoothLeService.java:222` | ALREADY_IMPLEMENTED | D19 |
| T010 | `service/BluetoothLeService.java:226` | IMPLEMENTED | D03 |
| T011 | `service/BluetoothLeService.java:231` | IMPLEMENTED | D03 |
| T012 | `service/BluetoothLeService.java:236` | IMPLEMENTED | D04/D12 |
| T013 | `service/BluetoothLeService.java:241` | IMPLEMENTED | D04/D12 |
| T014 | `service/BluetoothLeService.java:251` | EXCLUDED | X06 |
| T015 | `service/BluetoothLeService.java:255` | IMPLEMENTED | D03 |
| T016 | `service/BluetoothLeService.java:261` | IMPLEMENTED | D03 |
| T017 | `service/BluetoothLeService.java:268` | IMPLEMENTED | D03 |
| T018 | `service/BluetoothLeService.java:276` | EXCLUDED | X02 |
| T019 | `service/BluetoothLeService.java:285` | ALREADY_IMPLEMENTED | D19 |
| T020 | `ShuShiBanActivity.java:143` | ALREADY_IMPLEMENTED | D19 |
| T021 | `ShuShiBanActivity.java:209` | ALREADY_IMPLEMENTED | D19 |
| T022 | `ShuShiBanActivity.java:372` | ALREADY_IMPLEMENTED | D19 |
| T023 | `ShuShiBanActivity.java:388` | ALREADY_IMPLEMENTED | D19 (HA scan); phone 5-second scan timer is UI-only X08 |
| T024 | `ShuShiBanActivity.java:418` | ALREADY_IMPLEMENTED | D19 |
| T025 | `ShuShiBanActivity.java:623` | ALREADY_IMPLEMENTED | D19 |
| T026 | `ShuShiBanActivity.java:691` | ALREADY_IMPLEMENTED | D19 (HA scan); phone 5-second scan timer is UI-only X08 |
| T027 | `ShuShiBanActivity.java:700` | ALREADY_IMPLEMENTED | D19 (HA scan); phone 5-second scan timer is UI-only X08 |
| T028 | `ShuShiBanActivity.java:705` | ALREADY_IMPLEMENTED | D19 (HA scan); phone 5-second scan timer is UI-only X08 |
| T029 | `ShuShiBanActivity.java:866` | IMPLEMENTED | D03 |
| T030 | `ShuShiBanActivity.java:874` | IMPLEMENTED | D03 |
| T031 | `ShuShiBanActivity.java:876` | EXCLUDED | X01 |
| T032 | `ui/ConnectActivity.java:121` | EXCLUDED | X05 |
| T033 | `ui/ConnectActivity.java:216` | EXCLUDED | X05 |
| T034 | `ui/ConnectActivity.java:239` | EXCLUDED | X05 |
| T035 | `ui/ConnectActivity.java:263` | EXCLUDED | X05 |
| T036 | `ui/ConnectActivity.java:272` | EXCLUDED | X05 |
| T037 | `ui/ConnectActivity.java:277` | EXCLUDED | X05 |
| T038 | `ui/ConnectActivity.java:407` | EXCLUDED | X05 |
| T039 | `ui/ConnectActivity.java:410` | EXCLUDED | X05 |
| T040 | `MyApplication.java:115` | EXCLUDED | X07 |
| T041 | `MyApplication.java:122` | EXCLUDED | X07 |
| T042 | `fragment/HHWeiTiaoFragment.java:201` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T043 | `fragment/HHWeiTiaoFragment.java:216` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T044 | `fragment/HHWeiTiaoFragment.java:225` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T045 | `fragment/HHWeiTiaoFragment.java:240` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T046 | `fragment/HHWeiTiaoFragment.java:249` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T047 | `fragment/HHWeiTiaoFragment.java:263` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T048 | `fragment/HHWeiTiaoFragment.java:445` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T049 | `fragment/HHWeiTiaoFragment.java:478` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T050 | `fragment/HHWeiTiaoFragment.java:511` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T051 | `fragment/HHWeiTiaoFragment.java:539` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T052 | `fragment/HHWeiTiaoFragment.java:567` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T053 | `fragment/HHWeiTiaoFragment.java:595` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T054 | `fragment/HHWeiTiaoFragment.java:623` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T055 | `fragment/HHWeiTiaoFragment.java:651` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T056 | `fragment/HHWeiTiaoFragment.java:679` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T057 | `fragment/HHWeiTiaoFragment.java:721` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T058 | `fragment/HHWeiTiaoFragment.java:763` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T059 | `fragment/HHWeiTiaoFragment.java:794` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T060 | `fragment/HHWeiTiaoFragment.java:825` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T061 | `fragment/HHWeiTiaoFragment.java:854` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T062 | `fragment/HHWeiTiaoFragment.java:877` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T063 | `fragment/HHWeiTiaoFragment.java:906` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T064 | `fragment/HHWeiTiaoFragment.java:928` | IMPLEMENTED | D07/D09, C001–C031; X04 for dead subbranch only |
| T065 | `HaoHuaBanActivity.java:139` | EXCLUDED | X05 |
| T066 | `HaoHuaBanActivity.java:185` | EXCLUDED | X05 |
| T067 | `HaoHuaBanActivity.java:324` | EXCLUDED | X05 |
| T068 | `HaoHuaBanActivity.java:343` | EXCLUDED | X05 |
| T069 | `HaoHuaBanActivity.java:351` | EXCLUDED | X05 |
| T070 | `HaoHuaBanActivity.java:536` | EXCLUDED | X05 |
| T071 | `HaoHuaBanActivity.java:592` | EXCLUDED | X05 |
| T072 | `HaoHuaBanActivity.java:601` | EXCLUDED | X05 |
| T073 | `HaoHuaBanActivity.java:606` | EXCLUDED | X05 |
| T074 | `HaoHuaBanActivity.java:736` | EXCLUDED | X05 |
| T075 | `HaoHuaBanActivity.java:743` | EXCLUDED | X05 |
| T076 | `HaoHuaBanActivity.java:745` | EXCLUDED | X05 |
| T077 | `fragment/HHAnMoFragment.java:122` | IMPLEMENTED | D10, C052–C061/C018 |
| T078 | `fragment/HHAnMoFragment.java:131` | IMPLEMENTED | D10, C052–C061/C018 |
| T079 | `fragment/HHAnMoFragment.java:145` | IMPLEMENTED | D10, C052–C061/C018 |
| T080 | `fragment/HHAnMoFragment.java:154` | IMPLEMENTED | D10, C052–C061/C018 |
| T081 | `fragment/HHAnMoFragment.java:168` | IMPLEMENTED | D10, C052–C061/C018 |
| T082 | `fragment/HHAnMoFragment.java:177` | IMPLEMENTED | D10, C052–C061/C018 |
| T083 | `fragment/HHAnMoFragment.java:188` | IMPLEMENTED | D10, C052–C061/C018 |
| T084 | `fragment/HHAnMoFragment.java:200` | IMPLEMENTED | D10, C052–C061/C018 |
| T085 | `fragment/HHAnMoFragment.java:213` | IMPLEMENTED | D10, C052–C061/C018 |
| T086 | `fragment/HHAnMoFragment.java:225` | IMPLEMENTED | D10, C052–C061/C018 |
| T087 | `fragment/HHAnMoFragment.java:237` | IMPLEMENTED | D10, C052–C061/C018 |
| T088 | `fragment/HHAnMoFragment.java:249` | IMPLEMENTED | D10, C052–C061/C018 |
| T089 | `fragment/HHAnMoFragment.java:261` | IMPLEMENTED | D10, C052–C061/C018 |
| T090 | `fragment/HHAnMoFragment.java:270` | EXCLUDED | X03 |
| T091 | `fragment/HHDengGuangFragment.java:92` | IMPLEMENTED | D11, C062–C064/C017 |
| T092 | `fragment/HHDengGuangFragment.java:103` | IMPLEMENTED | D11, C062–C064/C017 |
| T093 | `fragment/HHDengGuangFragment.java:114` | IMPLEMENTED | D11, C062–C064/C017 |
| T094 | `fragment/HHDengGuangFragment.java:125` | IMPLEMENTED | D11, C062–C064/C017 |
| T095 | `fragment/HHKuaiJieFragment.java:107` | IMPLEMENTED | D08, C026–C051/C017 |
| T096 | `fragment/HHKuaiJieFragment.java:111` | IMPLEMENTED | D08, C026–C051/C017 |
| T097 | `fragment/HHKuaiJieFragment.java:133` | IMPLEMENTED | D08, C026–C051/C017 |
| T098 | `fragment/HHKuaiJieFragment.java:137` | IMPLEMENTED | D08, C026–C051/C017 |
| T099 | `fragment/HHKuaiJieFragment.java:159` | IMPLEMENTED | D08, C026–C051/C017 |
| T100 | `fragment/HHKuaiJieFragment.java:163` | IMPLEMENTED | D08, C026–C051/C017 |
| T101 | `fragment/HHKuaiJieFragment.java:185` | IMPLEMENTED | D08, C026–C051/C017 |
| T102 | `fragment/HHKuaiJieFragment.java:189` | IMPLEMENTED | D08, C026–C051/C017 |
| T103 | `fragment/HHKuaiJieFragment.java:211` | IMPLEMENTED | D08, C026–C051/C017 |
| T104 | `fragment/HHKuaiJieFragment.java:215` | IMPLEMENTED | D08, C026–C051/C017 |
| T105 | `fragment/HHKuaiJieFragment.java:236` | IMPLEMENTED | D08, C026–C051/C017 |
| T106 | `fragment/HHKuaiJieFragment.java:384` | IMPLEMENTED | D08, C026–C051/C017 |
| T107 | `fragment/HHKuaiJieFragment.java:395` | IMPLEMENTED | D08, C026–C051/C017 |
| T108 | `fragment/HHKuaiJieFragment.java:405` | IMPLEMENTED | D08, C026–C051/C017 |
| T109 | `fragment/HHKuaiJieFragment.java:415` | IMPLEMENTED | D08, C026–C051/C017 |
| T110 | `fragment/HHKuaiJieFragment.java:425` | IMPLEMENTED | D08, C026–C051/C017 |
| T111 | `fragment/HHKuaiJieFragment.java:436` | IMPLEMENTED | D08, C026–C051/C017 |
| T112 | `fragment/HHKuaiJieFragment.java:447` | IMPLEMENTED | D08, C026–C051/C017 |
| T113 | `fragment/HHKuaiJieFragment.java:487` | IMPLEMENTED | D08, C026–C051/C017 |
| T114 | `fragment/HHKuaiJieFragment.java:493` | IMPLEMENTED | D08, C026–C051/C017 |
| T115 | `fragment/HHKuaiJieFragment.java:526` | IMPLEMENTED | D08, C026–C051/C017 |
| T116 | `fragment/HHKuaiJieFragment.java:558` | IMPLEMENTED | D08, C026–C051/C017 |
| T117 | `fragment/HHKuaiJieFragment.java:563` | IMPLEMENTED | D08, C026–C051/C017 |
| T118 | `fragment/HHKuaiJieFragment.java:596` | IMPLEMENTED | D08, C026–C051/C017 |
| T119 | `fragment/HHKuaiJieFragment.java:601` | IMPLEMENTED | D08, C026–C051/C017 |
| T120 | `fragment/HHKuaiJieFragment.java:633` | IMPLEMENTED | D08, C026–C051/C017 |
| T121 | `fragment/HHKuaiJieFragment.java:669` | IMPLEMENTED | D08, C026–C051/C017 |
| T122 | `fragment/HHKuaiJieFragment.java:1005` | IMPLEMENTED | D05, C065–C079 |
| T123 | `fragment/HHKuaiJieFragment.java:1034` | IMPLEMENTED | D05, C065–C079 |
| T124 | `fragment/HHKuaiJieFragment.java:1051` | IMPLEMENTED | D05, C065–C079 |
| T125 | `fragment/HHKuaiJieFragment.java:1068` | IMPLEMENTED | D05, C065–C079 |
| T126 | `fragment/HHKuaiJieFragment.java:1082` | IMPLEMENTED | D05, C065–C079 |
| T127 | `fragment/HHKuaiJieFragment.java:1089` | EXCLUDED | X06 |
| P1 | `four control fragments -> BluetoothLeService` | IMPLEMENTED | D02–D18 |
| ALT1 | `HaoHuaBanActivity` | EXCLUDED | X05 |
| ALT2 | `SettingActivity -> ConnectActivity` | EXCLUDED | X05 |
| HIDDEN-MASS | `HHAnMoFragment.onClick(sw_on_off)` | EXCLUDED | X03 |
| HIDDEN-CYCLE | `HHWeiTiaoFragment llBeitui non-TYPE1` | EXCLUDED | X04 |
| Q6 | `HHKuaiJieFragment$20$1 k6` | EXCLUDED | X06 |
| RSSI | `BluetoothLeService.readRssi` | EXCLUDED | X06 |
| LISTENER | `BluetoothLeService.OnDataAvailableListener` | EXCLUDED | X06 |
| TIMERS | `timerTask fields in fragments` | EXCLUDED | X06 |
| BINDING | `com.wnhz.shidaodianqi generated R/databinding` | EXCLUDED | X07 |
| NETWORK | `uitls/Url, NetworkUtils, QrCodeActivity` | EXCLUDED | X07 |
| SETTINGS | `ShuShiBanActivity.onClick sw_on_off` | EXCLUDED | X07 |
| LIBS | `AndroidX/Kotlin/coroutines/Glide/image-loader/UI support` | EXCLUDED | X07 |
| TYPE-1 | `ShuShiBanActivity.java:731-766,396-416,265-289` | IMPLEMENTED | D01/D17 |
| TYPE-2 | `ShuShiBanActivity.java:731-766,396-416,265-289` | IMPLEMENTED | D01/D17 |
| TYPE-3 | `ShuShiBanActivity.java:731-766,396-416,265-289` | IMPLEMENTED | D01/D17 |
| TYPE-4 | `ShuShiBanActivity.java:731-766,396-416,265-289` | IMPLEMENTED | D01/D17 |
| TYPE-5 | `ShuShiBanActivity.java:731-766,396-416,265-289` | IMPLEMENTED | D01/D17 |
| TYPE-6 | `ShuShiBanActivity.java:731-766,396-416,265-289` | IMPLEMENTED | D01/D17 |
| TYPE-7 | `ShuShiBanActivity.java:731-766,396-416,265-289` | IMPLEMENTED | D01/D17 |
| TYPE-8 | `ShuShiBanActivity.java:731-766,396-416,265-289` | IMPLEMENTED | D01/D17 |
| TYPE-9 | `ShuShiBanActivity.java:731-766,396-416,265-289` | IMPLEMENTED | D01/D17 |
| PASSWORD-HELPER | `uitls/ConfirmUtils.java:16,69-71` | EXCLUDED | X06 |

## Parser predicate and consumer coverage

All 41 N1 predicates, in artifact order, are implemented by `MEMORY_RULES`,
not by an inferred register parser. Each has its own frozen positive input and
initial n in `bedsense_vectors.json:memory`, exercised by
`test_all41_memory_predicates`. Rules keep n unless they assign it. N0 is D12;
N1 is D13; N2 (massage) is D14; N3 (circulation) is D15; light logging has no
additional state decoder (D11). Exact/substrings and special exclusions have
additional negative/precedence tests. All 9 selectors and every command layout
set are verified. No checksum, packet buffer, response timeout, authentication,
position, battery or configuration parser is inferred from absence.

No in-scope discovery is deferred. Hardware captures after beta/release are
external validation: GATT properties and duplicate roles, five query replies
(including default M1), movement/cancel and type9 lift clicks, physical actuator
mapping, background-tap effect, massage semantics and actual light durations.
These do not prevent artifact-based implementation or justify an exclusion.
