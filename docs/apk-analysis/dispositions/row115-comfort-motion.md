# Row115 Comfort Motion implementation dispositions

Package `com.jiecang.app.android.jiecangbed`, 2.2.1/code28. Standalone FULL comparison following independent acceptance. This is a derived implementation ledger; raw APKs, extraction, reports and audits remain machine-local and uncommitted. Protocol facts come only from the accepted package-local evidence. Existing integration code establishes comparison results, never artifact facts.

## Accepted authority

Accepted report: `work/report-repair-sol-002`, audit: `audit/sol-round003`, under the package/version run named `com.jiecang.app.android.jiecangbed-2.2.1-2026-11-03-bulk101-188-001`. Acceptance is `ACCEPTANCE.json` recorded 2026-11-03T15:13:12.857263+00:00. SOL-001 and SOL-002 are independently CLOSED_VERIFIED, 17 gates accepted, zero open material findings. Superseded candidates are preservation bases only.

| Seal | SHA-256 |
| --- | --- |
| Artifact set | `ee964a8074ab8776f1b54ba936372ce22bcca8e1b37a0af95775959b633e7879` |
| REPORT.SHA256 | `3db8d22c26c6e9a73a13b9cc93055ab0d9df2572017d6ce576a4c1c2cc8fd431` |
| SUPERSESSION.json | `d66f50c4835aab4c81f59773a139937b9d495003016c162d230f9c5d0e5495fd` |
| AUDIT.SHA256 | `718c801a22518c84d7b2e7b68acb77600707729071cdf1b93a83b03f2ed5a63f` |
| AUDIT.md | `4bbfc5ee7b7200b4c6393ead1ffe970e87c78b31d453987ef4842ee007a0ae1d` |
| findings.json | `114d09e68fa51971094d7bdbe2eac1e374742d1ab016bf98740f4a16426ada47` |
| ACCEPTANCE.json | `e18773021d6d1a1ed687443646b39f2ff06431203ced539aa83fad1cef079a90` |

Implementer independently rehashed all 38 report, 122 audit and 42 input manifest members read-only and checked the six explicit authority seals. Artifact-set manifest hash matches the acceptance. Evidence IDs below resolve in that report, and source references are package-local Java/smali as indexed there. No sibling semantic output was consulted.

## Implementation and equivalence references

Production references are relative to `custom_components/adjustable_bed/`. New behavior is in `beds/comfort_motion.py`, selected only by explicit `jiecang_app_profile=comfort_motion` in `controller_factory.create_controller`. It shares the existing type `jiecang_app` and its profile setup, not the other app controllers. The legacy `comfort_motion` and `jiecang` types are unchanged.

All new paths are exercised by `tests/test_comfort_motion.py`. Reused routes are checked through actual HA setup, cover/number/light/buttons and rename/wake services in `test_real_entities_services_and_serialization`. Explicit flow/options validity is checked in `test_profile_setup_and_options_reject_other_layouts` and `test_profile_setup_accepts_comfort_motion`. Existing Jiecang app equivalence is covered by `tests/test_jiecang_app_config.py`, `tests/test_jiecang_app_controller.py`, `tests/test_jiecang_app_entities.py` and `tests/test_app_profiles.py`.

## Candidate ledger (all 74 accepted discoveries)

Each row has exactly one implementation disposition. K rows enumerate every literal, including all 22 unreachable constants. New behavior is IMPLEMENTED, with concrete method and focused test references. EXCLUDED means outside the BLE product or artifact-unreachable, never deferred feature work.

| ID / discovery | Disposition | Evidence | Implementation, equivalence or exclusion reason |
| --- | --- | --- | --- |
| C01 (BLE scan and device selection) | ALREADY_IMPLEMENTED | E03 | `config_flow` manual/Bluetooth setup and HA Bluetooth scanning; no app inference from shared service. `tests/test_jiecang_app_config.py::test_all_setup_routes_collect_explicit_profile`, plus explicit Comfort Motion setup test. |
| C02 (Barcode and saved-address selection) | ALREADY_IMPLEMENTED | E03,E16 | `config_flow` selected/manual address persists per config entry; same setup-route test. Barcode camera/Android UI is unrelated infrastructure; its address handoff is already supported. |
| C03 (T1 GATT) | IMPLEMENTED | E04 | `_select_transport`, `test_runtime_properties_and_rename`, actual HA route test. |
| C04 (T2 GATT) | IMPLEMENTED | E03,E04 | `_select_transport`, `test_setup_queries_without_layout_or_massage`, G2 variant tests; no G2 advertisement inference. |
| C05 (Login-named GATT discovery) | EXCLUDED | E04,E14 | Stored login-named handle has no reader or transport use; E04/E14. No authentication behavior to implement. |
| C06 (Login command path) | EXCLUDED | E04,E14 | No login frame, PIN, credentials, bond call or authentication gate exists; E04/E14. |
| C07 (Generic characteristic-read helper) | EXCLUDED | E05,E18 | Generic read helper has no caller in shipped DEX; E05/E18. |
| C08 (Motion actions and release) | IMPLEMENTED | E07,E08,E22 | `_move`, motor specs and cleanup; `test_motion_vectors_and_release`, cancellation and temporal tests. |
| C09 (Preset recall and save) | IMPLEMENTED | E09 | `_recall`, `program_memory`; `test_click_vectors` and actual HA buttons. Local memory labels use HA entity naming, not BLE writes. |
| C10 (Massage UI) | IMPLEMENTED | E10,E22 | `_massage_step`, `set_massage_intensity`, `massage_mode_step`, `massage_off`; all unsigned/parser/step and literal tests. |
| C11 (Light and rename) | IMPLEMENTED | E12 | `lights_toggle`, `_set_light`, `rename_device`; runtime rename, light feedback and actual service tests. |
| C12 (Initialization query writes) | IMPLEMENTED | E06 | `start_notify`/SETUP; unconditional setup query test and cancellation/reconnect failure test. |
| C13 (Notifications and layout/state consumers) | IMPLEMENTED | E11,E22 | `_handle_notification`, cached raw intensities/layout/light; all24 variants, unsigned values, short/unknown and real-number unknown-state tests. |
| C14 (Alarm navigation and new schedule UI) | EXCLUDED | E13 | Alarm navigation has no reachable tab in current app; E13. HA scheduling replaces companion-app WorkManager, with no bed alarm frame invented. |
| C15 (Alarm broadcast and previously persisted worker) | IMPLEMENTED | E13 | `execute_wake_routine`/`stop_wake_routine`; exact conditional command route via existing jiecang_wake services and HA automations. Wake source-vector and real-service tests. |
| C16 (App local preferences) | ALREADY_IMPLEMENTED | E14 | `config_flow`, `app_profiles`/pairing own per-bed address/name/light/massage/layout; setup/options tests and `tests/test_app_profiles.py`. Local label/schedule/UI preferences use HA naming/automations, no bed configuration frame. |
| C17 (Play app update) | EXCLUDED | E15 | E15: Play companion-app updates, not bed BLE firmware. |
| C18 (Native GIF library) | EXCLUDED | E02 | E02: third-party GIF rendering JNI only, unrelated to bed integration. |
| C19 (Wi-Fi provisioning/cloud/account candidates) | EXCLUDED | E14,E15 | E14/E15: no reachable app-owned Wi-Fi/cloud/account/network provisioning path; product-boundary excluded, no debt. |
| C20 (Bed OTA/calibration/reset candidates) | EXCLUDED | E14,E18 | E14/E18: no reachable OTA/calibration/reset/EEPROM write; dead reset literal is not a supported action. |
| K-antiSnoreCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-backDownCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-backUpCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-backVibrationIntensity0Cmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-backVibrationIntensity10Cmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-backVibrationIntensity1Cmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-backVibrationIntensity2Cmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-backVibrationIntensity3Cmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-backVibrationIntensity4Cmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-backVibrationIntensity5Cmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-backVibrationIntensity6Cmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-backVibrationIntensity7Cmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-backVibrationIntensity8Cmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-backVibrationIntensity9Cmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-bothDownCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-bothUpCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-buttonReleaseCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-flatCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-getActuatorStatusCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-getActuatorTimerVibrationStatusCmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-getHardwareCofigCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-getStatusCmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-getTimerStatusCmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-getVibrationIntensityCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-goA_PositionCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-goB_PositionCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-goC_PositionCmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-headDownCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-headUpCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-legDownCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-legUpCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-legVibrationIntensity0Cmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-legVibrationIntensity10Cmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-legVibrationIntensity1Cmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-legVibrationIntensity2Cmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-legVibrationIntensity3Cmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-legVibrationIntensity4Cmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-legVibrationIntensity5Cmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-legVibrationIntensity6Cmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-legVibrationIntensity7Cmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-legVibrationIntensity8Cmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-legVibrationIntensity9Cmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-lightCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-memoryA_PositionCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-memoryB_PositionCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-memoryC_PositionCmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-modeCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-resetCmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-startCmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-stopCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-timerCmd (command constant) | EXCLUDED | E07,E18 | E07/E18: zero executable Java/smali callers. Dead literal, no supported command or arbitrary builder. |
| K-waistDownCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-waistUpCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |
| K-zgCmd (command constant) | IMPLEMENTED | E07,E18 | Exact live literal is accounted individually in the action table below; same command ID, controller method and vector test. |

## All 33 reachable actions

Every action is IMPLEMENTED with the accepted exact bytes/destination. The following test families exercise each route: motion=motion vector/cancellation; click=click vectors; massage=zone literal/unsigned-step tests; setup=unconditional setup queries; rename=runtime properties/rename and real service. All refer to `tests/test_comfort_motion.py`. Source locations and evidence IDs are accepted report references.

| Action ID | Exact payload | Controller route / vector family | Evidence | Disposition |
| --- | --- | --- | --- | --- |
| antiSnoreCmd | `F1F10901010B7E` | `_recall`, wake / click | E07,E09,E13,E22 | IMPLEMENTED |
| backDownCmd | `F1F1020101047E` | `_move`, motor specs / motion | E07,E08,E22 | IMPLEMENTED |
| backUpCmd | `F1F1010101037E` | `_move`, motor specs / motion | E07,E08,E22 | IMPLEMENTED |
| backVibrationIntensity0Cmd | `F1F1120208001C7E` | `set_massage_intensity`, `_massage_step`, wake / massage | E07,E10,E13,E22 | IMPLEMENTED |
| backVibrationIntensity2Cmd | `F1F1120208021E7E` | `set_massage_intensity`, `_massage_step`, wake / massage | E07,E10,E13,E22 | IMPLEMENTED |
| backVibrationIntensity3Cmd | `F1F1120208031F7E` | `set_massage_intensity`, `_massage_step`, wake / massage | E07,E10,E13,E22 | IMPLEMENTED |
| backVibrationIntensity4Cmd | `F1F112020804207E` | `set_massage_intensity`, `_massage_step`, wake / massage | E07,E10,E13,E22 | IMPLEMENTED |
| bothDownCmd | `F1F1060101087E` | `_move`, motor specs / motion | E07,E08,E22 | IMPLEMENTED |
| bothUpCmd | `F1F1050101077E` | `_move`, motor specs / motion | E07,E08,E22 | IMPLEMENTED |
| buttonReleaseCmd | `F1F14E004E7E` | `stop_all`, cleanup / motion | E07,E08,E13,E22 | IMPLEMENTED |
| flatCmd | `F1F10801010A7E` | `_recall`, wake / click | E07,E09,E13,E22 | IMPLEMENTED |
| getActuatorStatusCmd | `F1F1000101027E` | `start_notify` / setup | E07,E06,E22 | IMPLEMENTED |
| getHardwareCofigCmd | `F1F1000140417E` | `start_notify` / setup | E07,E06,E22 | IMPLEMENTED |
| getVibrationIntensityCmd | `F1F1000108097E` | `start_notify` / setup | E07,E06,E22,E23 | IMPLEMENTED |
| goA_PositionCmd | `F1F10B01010D7E` | `_recall`, wake / click | E07,E09,E13,E22 | IMPLEMENTED |
| goB_PositionCmd | `F1F10D01010F7E` | `_recall`, wake / click | E07,E09,E13,E22 | IMPLEMENTED |
| headDownCmd | `F1F11A01011C7E` | `_move`, motor specs / motion | E07,E08,E22 | IMPLEMENTED |
| headUpCmd | `F1F11901011B7E` | `_move`, motor specs / motion | E07,E08,E22 | IMPLEMENTED |
| legDownCmd | `F1F1040101067E` | `_move`, motor specs / motion | E07,E08,E22 | IMPLEMENTED |
| legUpCmd | `F1F1030101057E` | `_move`, motor specs / motion | E07,E08,E22 | IMPLEMENTED |
| legVibrationIntensity0Cmd | `F1F1140208001E7E` | `set_massage_intensity`, `_massage_step`, wake / massage | E07,E10,E13,E22 | IMPLEMENTED |
| legVibrationIntensity2Cmd | `F1F114020802207E` | `set_massage_intensity`, `_massage_step`, wake / massage | E07,E10,E13,E22 | IMPLEMENTED |
| legVibrationIntensity3Cmd | `F1F114020803217E` | `set_massage_intensity`, `_massage_step`, wake / massage | E07,E10,E13,E22 | IMPLEMENTED |
| legVibrationIntensity4Cmd | `F1F114020804227E` | `set_massage_intensity`, `_massage_step`, wake / massage | E07,E10,E13,E22 | IMPLEMENTED |
| lightCmd | `F1F10F000F7E` | `lights_toggle`, `_set_light` / click | E07,E12,E22 | IMPLEMENTED |
| memoryA_PositionCmd | `F1F10A01010C7E` | `program_memory` / click | E07,E09,E22 | IMPLEMENTED |
| memoryB_PositionCmd | `F1F10C01010E7E` | `program_memory` / click | E07,E09,E22 | IMPLEMENTED |
| modeCmd | `F1F116010A217E` | `massage_mode_step` / click | E07,E10,E22 | IMPLEMENTED |
| stopCmd | `F1F11101081A7E` | `massage_off`, `stop_wake_routine` / click | E07,E10,E13,E22 | IMPLEMENTED |
| waistDownCmd | `F1F11C01011E7E` | `_move`, motor specs / motion | E07,E08,E22 | IMPLEMENTED |
| waistUpCmd | `F1F11B01011D7E` | `_move`, motor specs / motion | E07,E08,E22 | IMPLEMENTED |
| zgCmd | `F1F1070101097E` | `_recall`, wake / click | E07,E09,E13,E22 | IMPLEMENTED |
| rename | `ASCII(name), 1..18 characters from ._0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ, no terminator or frame` | `rename_device` / rename | E12 | IMPLEMENTED |

## All 24 runtime variants

Variant metadata is not a continuing permission mask. Each row is IMPLEMENTED and parameterized in `test_all_24_variants_and_temporal_retention`: both transports, all six layout replies and both local light choices. The configured layout owns physical axes, and massage is a separate per-side option. Every layout reply is consumed and retained in diagnostics; invalid replies become 0 without resetting state.

| Accepted variant | HA selection | Response layout | Light | Disposition |
| --- | --- | --- | --- | --- |
| T1-B1-L0 | T1 / standard_2, massage false | 1 | false | IMPLEMENTED |
| T1-B1-L1 | T1 / standard_2, massage false | 1 | true | IMPLEMENTED |
| T1-B2-L0 | T1 / standard_2, massage true | 2 | false | IMPLEMENTED |
| T1-B2-L1 | T1 / standard_2, massage true | 2 | true | IMPLEMENTED |
| T1-B3-L0 | T1 / standard_3_neck, massage false | 3 | false | IMPLEMENTED |
| T1-B3-L1 | T1 / standard_3_neck, massage false | 3 | true | IMPLEMENTED |
| T1-B4-L0 | T1 / standard_3_neck, massage true | 4 | false | IMPLEMENTED |
| T1-B4-L1 | T1 / standard_3_neck, massage true | 4 | true | IMPLEMENTED |
| T1-B5-L0 | T1 / standard_4_legacy, massage false | 5 | false | IMPLEMENTED |
| T1-B5-L1 | T1 / standard_4_legacy, massage false | 5 | true | IMPLEMENTED |
| T1-B6-L0 | T1 / standard_4_legacy, massage true | 6 | false | IMPLEMENTED |
| T1-B6-L1 | T1 / standard_4_legacy, massage true | 6 | true | IMPLEMENTED |
| T2-B1-L0 | T2 / standard_2, massage false | 1 | false | IMPLEMENTED |
| T2-B1-L1 | T2 / standard_2, massage false | 1 | true | IMPLEMENTED |
| T2-B2-L0 | T2 / standard_2, massage true | 2 | false | IMPLEMENTED |
| T2-B2-L1 | T2 / standard_2, massage true | 2 | true | IMPLEMENTED |
| T2-B3-L0 | T2 / standard_3_neck, massage false | 3 | false | IMPLEMENTED |
| T2-B3-L1 | T2 / standard_3_neck, massage false | 3 | true | IMPLEMENTED |
| T2-B4-L0 | T2 / standard_3_neck, massage true | 4 | false | IMPLEMENTED |
| T2-B4-L1 | T2 / standard_3_neck, massage true | 4 | true | IMPLEMENTED |
| T2-B5-L0 | T2 / standard_4_legacy, massage false | 5 | false | IMPLEMENTED |
| T2-B5-L1 | T2 / standard_4_legacy, massage false | 5 | true | IMPLEMENTED |
| T2-B6-L0 | T2 / standard_4_legacy, massage true | 6 | false | IMPLEMENTED |
| T2-B6-L1 | T2 / standard_4_legacy, massage true | 6 | true | IMPLEMENTED |

## Cross-cutting behavior and safe HA adaptations

These rows supplement the action and variant tables. IMPLEMENTED adaptations preserve the BLE behavior while using HA lifecycle/controls; EXCLUDED rows name an exact safety or unrelated-infrastructure reason. No accepted discovery is silently deferred.

| Discovery / accepted evidence | Disposition | Code, test and decision |
| --- | --- | --- |
| E04, two independent service branches, last output assignment, multiple subscriptions | IMPLEMENTED | `_select_transport`; runtime/dual-service failure tests. Explicit transport pins one, Auto uses enumeration order. Discovered ATT properties choose the supported write type. |
| E04/E05, stale static handles after disconnect | EXCLUDED | Safety: stale GATT/name roles can address a different connection. HA rediscovers on each connection; G2 reconnect test proves old name handle is discarded. |
| E05, connection status errors and write-return ignorance | IMPLEMENTED | Connected-state checks, propagated Bleak errors, HA coordinator retry/backoff/serialization. Failure cleanup and real route tests. No invented firmware ACK/retry. |
| E06/E23, unconditional setup queries at 200..700 ms, no layout/massage/ACK gate | IMPLEMENTED | `start_notify` subscribes at 100 ms and attempts all six fixed queries. Setup test verifies exact order and repeats without any response or massage. |
| E23, anonymous setup callbacks can cross disconnect/reconnect | EXCLUDED | Safety: stale queued writes must not target a replacement link. Awaited cancellable startup cleans failed subscriptions, new connection starts a fresh batch; setup failure/cancellation tests. |
| E06/E08, 60s Android layout/reconnect dialogs, 4s scan stop, 1s mode animation | EXCLUDED | Companion UI timers do not define firmware command timing. HA owns scanning, connection recovery and error UI. App missed scan-stop destruction is not reproduced. |
| E07/E19/E20, fixed framing and corroborated additive relation | IMPLEMENTED | Fixed literal maps only, no generic frame/checksum builder. Every reachable literal tested; dead constants excluded individually above. |
| E08, 100ms held refresh and normal release after 100ms | IMPLEMENTED | `_move`, `_recall`, fresh-event release; motion/click vectors and cancellation tests. HA pulse count bounds a hold; no guessed Android long-click threshold. |
| E08/E22, final repeat after release, missing cancel/key/pause/destroy release | EXCLUDED | Safety: HA does not deliberately restart movement on release or omit cleanup. `finally` sends the observed release on command/task cancellation and failures. |
| E09, memory label inequality and long-click UI interaction | EXCLUDED | Labels are app-local strings, not transmitted. HA entity naming and explicit program-memory buttons avoid unintended recall; memory save/recall literals remain implemented. |
| E10/E22, independent retained massage zones, default zero, unsigned tag06 updates | IMPLEMENTED | `_levels`, `_massage_step`, numbers. Source levels 0/2/3/4 map to slider 0..3; unknown wire values yield unknown/no-op. No optimistic update; all256 values tested. |
| E11, single-callback parser, no framing/checksum or source filter | IMPLEMENTED | `_handle_notification`; exact minima7/9, offsets4/6/8, bit6. Short/unknown safe ignore; no splitting or fabricated positions. Parser and temporal tests. |
| E11, empty/no EXTRA_DATA null dereference | EXCLUDED | Safety: empty callbacks are ignored, never crash HA. Short/unknown test. |
| E22, selected motor/zone/panels survive valid/repeated/changed/invalid layouts | IMPLEMENTED | Explicit layout owns HA motor choices; per-zone state and latest reported layout survive all replies. HA has independent zone controls, not a global selected panel. All24 temporal tests and real entity routing. |
| E22, visibility is not a runtime write gate | IMPLEMENTED | Reported layout is diagnostic only; no destructive revocation/reset of configured axes or massage. Actual current controller validates explicit layout, preventing stale HA motor specs dispatching wrong axes. |
| E22, same-instance reconnect retains parsed state | IMPLEMENTED | Raw intensity/layout/light persist in coordinator state and hydrate replacement controller; temporal reconnect test. Availability follows connection, values remain last-known. |
| E12, local light presence versus parsed light bit | IMPLEMENTED | Per-side `has_light`, `get_light_state`, reported-state light entity. Unknown desired state rejected; native toggle available; no optimistic feedback. Real light route, light-feedback tests and `test_disabled_light_has_no_controls` (no toggle or light entity when disabled). |
| E12, raw rename with ASCII UI alphabet and length18, no ACK | IMPLEMENTED | Generic `rename` service, discovered writable G1 role, `_name_response`. Exact raw-byte and rejected-name tests plus actual HA service. |
| E13, conditional broadcast wake commands at0/200/500ms | IMPLEMENTED | `execute_wake_routine`: enabled zones with +100ms releases, preset at500ms without release. Zero means zone disabled, valid1..3 maps wire2/3/4. Wake vector, cancellation and actual service tests. |
| E13, conditional stopAlarm | IMPLEMENTED | `stop_wake_routine` sends massage stop, distinct from movement release. Wake/stop vector test and actual HA service. |
| E13, Android periodic jobs/weekday filters, notifications and exported receivers | EXCLUDED | Companion infrastructure; HA automations schedule the implemented BLE wake service. No BLE clock/alarm programming exists; `jiecang_set_alarm` capability rejected. |
| E14, one static current bed and app-global preferences | ALREADY_IMPLEMENTED | `coordinator` per-address command lock, `paired_coordinator` address-side routing and `app_profiles` per-side fields; existing paired/app-profile tests and actual HA serialization test. No native one-address pairing/side packet invented. |
| E14/E15, Wi-Fi/cloud/account/network/OTA candidates | EXCLUDED | Product boundary and absence of reachable app-owned behavior. GIF/Play/password-eye support assets do not create bed features. |
| E17/E18, transport invocations and variant selection | IMPLEMENTED | All72 transport callsites collapse into scanning/address selection, connect/discover/subscribe/write/close and unused reads, covered above. No additional transport/auth/command exists. |
| Deferred physical effects, ATT properties, physical layout mapping, mode names and rename persistence | EXCLUDED | External validation, not missing static implementation. Real users after beta/release may validate these effects; no maintainer hardware blocker or speculative mapping. |

## Completion boundary

All 74 candidates, 33 reachable actions, 24 runtime variants and 25 cross-cutting rows have final dispositions. Physical tests remain explicitly unverified. The comprehensive implementation PR must remain open and unmerged. Shared queue/global issue updates belong to the coordinator and are intentionally outside this checkout. Local validation and independent review receipts live in the row115 implementation handoff; publication/convergence status is recorded there without embedding raw audit reports.
