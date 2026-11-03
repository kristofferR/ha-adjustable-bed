# Row068 Glideaway Motion implementation dispositions

Separate post-freeze comparison of the accepted `com.ore.bedding.glideawaymontion`
1.0.3 (code 11) revision01. Hardware remains unverified. No discovery is deferred
because of missing maintainer hardware or a missing pre-existing entity.

- Complete 19-member XAPK artifact-set SHA256: `7eb30a03349b9d9b9bffc43e2dafdb672c422fdd70e16b3e2c9ec2a55730c315`.
- Accepted revision01 `REPORT.SHA256` SHA256: `b3b4b2cc669d8050a68070aa3f9c1ad8021b0c7f9b244ab6703ae4d0caf3ec04`.
- The original report was rejected; this accepted revision records an explicit
  coordinator mechanical R01-F01 output-agreement repair, independently accepted
  after audit rounds 01/02, all 17 gates PASS. Frozen analyst headers predate
  acceptance; the separate acceptance record supplies the decision.
- Evidence root: local `disassembly/output/phase4-early/com.ore.bedding.glideawaymontion-1.0.3-2026-11-03-bulk061-001/work/report-revision01/`.
  `E01`–`E16`, C01–C31, N1–N5, P1/T/D/X IDs refer only to this accepted report.
  No original rejected candidate or sibling app is implementation evidence.
- Candidate groups plus every command, notification and model are individually
  accounted for below. `transport-callsites.json` exhaustively groups all 54
  invocations into T01–T04, D10/D12 and Android scaffolding X05. There is one
  reachable builder, not a second inferred family. `oracle-vectors.csv` covers
  1008 live/dead builder selector cases; only reachable commands are exported.
- All new controller references below resolve to
  [glideaway_motion.py](../../../custom_components/adjustable_bed/beds/glideaway_motion.py).
  Test names resolve to [test_glideaway_motion.py](../../../tests/test_glideaway_motion.py)
  unless another path is given. Other short module paths are under
  `custom_components/adjustable_bed/`.

Coverage: **86 dispositions**, 61 IMPLEMENTED, 1 ALREADY_IMPLEMENTED, 24 EXCLUDED. No unresolved in-scope items.

## P1 · IMPLEMENTED

Fixed single packet-builder route

Evidence: E02, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:frame, command_frame, rtc_frame, alarm_frame`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_calendar_and_rtc_vectors`.

## T01 · IMPLEMENTED

Unfiltered scan, selected MAC and manual model

Evidence: E04.

Code: `detection.py:APP_VARIANT_CHOICES; actuator_groups.py:ACTUATOR_GROUPS; controller_factory.py:create_controller`.

Tests: `tests/test_glideaway_motion.py:test_factory_manual_models_and_profile_ownership, test_manual_setup_saves_explicit_app_model`.

## T02 · ALREADY_IMPLEMENTED

Connect selected address, discover services, reconnect and explicit disconnect

Evidence: E05, E06.

Code: `custom_components/adjustable_bed/coordinator.py:async_connect, _async_connect_locked, async_disconnect`.

Tests: `tests/test_coordinator.py:TestCoordinatorPositionSeek.test_ensure_connected_reconnects; TestDisconnectCommandSerialization.test_disconnect_button_waits_for_running_command`.

HA owns transport discovery/lifecycle; selected-address connection and explicit disconnect are equivalent. Android API overloads and permission/UI delays are phone infrastructure, excluded in X05; unsafe stale repeats excluded in S02.

## T03 · IMPLEMENTED

FFE0/FFE4 notifications and CCCD subscription

Evidence: E05.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:start_notify, stop_notify, requires_notification_channel`.

Tests: `tests/test_glideaway_motion.py:test_gatt_roles_subscription_and_mode`.

## T04 · IMPLEMENTED

FFE5/FFE9 sole write sink, property-selected write mode

Evidence: E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:_role, write_command`.

Tests: `tests/test_glideaway_motion.py:test_gatt_roles_subscription_and_mode`.

## T05 · IMPLEMENTED

All five notification/parser forms and public state

Evidence: E13.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:_on_notification, _timer, controller_state_sensor_specs`.

Tests: `tests/test_glideaway_motion.py:test_timer_notification_vectors, test_fragmentation_and_safe_bounds, test_complete_f4_and_signed_alarm_state`.

## T06 · IMPLEMENTED

Manual model selection, no advertisement capability inference

Evidence: E03, E10.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:LAYOUTS, supports_massage, supports_lights; const.py:VARIANT_REQUIRED_BED_TYPES; app_profiles.py:_HIDDEN_BY_BED_TYPE, _BY_BED_TYPE`.

Tests: `tests/test_glideaway_motion.py:test_models_and_cover_controls, test_manual_setup_saves_explicit_app_model, test_entity_exposure_and_stale_model_cleanup`.

## T07 · IMPLEMENTED

Clock and alarm writes/readback

Evidence: E12.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:configure_clock_alarm, query_alarm, sync_clock; services.py:handle_glideaway_set_alarm`.

Tests: `tests/test_glideaway_motion.py:test_alarm_vectors_rtc_sequence_and_parser, test_query_alarm_twice_and_explicit_clock_sync, test_alarm_service_validation_and_queue`.

## T08 · IMPLEMENTED

Sustained memory programming without claimed acknowledgement

Evidence: E08, E14.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:program_memory, preset_memory`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors[C17/C18], test_recall_does_not_program_and_invalid_slots_write_nothing`.

## D01 · EXCLUDED

getData functions15,16: separate head/foot massage; inc/dec/levels

Evidence: E07, E08, E16.

No manager call to these function selectors. Masks800/800000 or400/1000000 and levels80000/100000/200000 are artifact constants only.

## D02 · EXCLUDED

setMassageIntensity levels1/2/3

Evidence: E07, E08, E16.

Manager method exists but has no caller; getData20 sub10/11/12 -> masks80000/100000/200000.

## D03 · EXCLUDED

setMassageMode levels1/2/3

Evidence: E07, E08, E16.

No caller; getData17 sub10/11/12 -> mask10000000 parameter40/80/C0.

## D04 · EXCLUDED

setMassageTime(10/20/30)

Evidence: E07, E08, E16.

No caller; getData19 sub10/11/12 -> mask200 parameter40/80/C0. Live UI only adjustMassage -> parameter0.

## D05 · EXCLUDED

queryMassageStatus

Evidence: E07, E08, E16.

No caller; getData18 sub5 -> N(3,0). Not a connection init query.

## D06 · EXCLUDED

callMemory slots4 and7

Evidence: E07, E08, E16.

No UI caller. slot4 -> getData10 mask10000; slot7 -> getData21 mask40000. Actual user A/B are slots3/6, masks2000/4000.

## D07 · EXCLUDED

saveMemory(int)

Evidence: E07, E08, E16.

Empty method. Actual save uses sustained callMemory repetition.

## D08 · EXCLUDED

turnOnMassage/turnOffLight

Evidence: E07, E08, E16.

No caller to on-massage or off-light helper. They alias reachable off-massage mask100 and light mask20000 respectively.

## D09 · EXCLUDED

unused masks/constants and getSum

Evidence: E07, E08, E16.

MASSAGE_STOPALL=02000000, MASSAGE_WAIST=00400000 etc have no selected reachable branch. Manager.getSum is unused; receiver does not validate checksum.

## D10 · EXCLUDED

legacy LeScan callback

Evidence: E07, E08, E16.

LHBleManager$1 allocated, never registered; modern startScan callback is live.

## D11 · EXCLUDED

model state getters/setters and motorNumber

Evidence: E07, E08, E16.

Defaults and setters do not select capabilities or update from notifications; UI uses explicit model selection.

## D12 · EXCLUDED

alternate manager entry helpers

Evidence: E07, E08, E16.

connectDevice(int), activate, disconnectAllDevices, destroy, closeGatt, setWriteCallback have no app caller for an alternate protocol; closeGatt empty. Active UI uses connectdevice(model)/disconnect.

## X01 · EXCLUDED

Physical remote child lock and pairing

Evidence: E14, E15, E16.

Help/remote illustration only; GuideDetailFragment renders text/images, no BLE command. EXCLUDED from BLE feature reconstruction.

## X02 · EXCLUDED

Phone ringtone/local notifications

Evidence: E14, E15, E16.

AlarmWorker/AlarmTipActivity/NotificationUtils play MP3 and schedule phone work, no BLE write. EXCLUDED unrelated phone infrastructure.

## X03 · EXCLUDED

Contact/help/preferences

Evidence: E14, E15, E16.

External dial/email intents, local JSON and selections; EXCLUDED except selected MAC influences reconnect.

## X04 · EXCLUDED

Framework, UI and serialization libraries

Evidence: E14, E15, E16.

AndroidX, Material, Kotlin/coroutines, Gson, ButterKnife, permission/UI widgets have no separate BLE sink or native runtime in complete DEX scans.

## C01 · IMPLEMENTED

Head up

Evidence: E03, E08, E09, E10, E14, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:AXES, LAYOUTS, motor_control_specs, _move_axis, hold_control`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_models_and_cover_controls`.

## C02 · IMPLEMENTED

Head down

Evidence: E03, E08, E09, E10, E14, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:AXES, LAYOUTS, motor_control_specs, _move_axis, hold_control`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_models_and_cover_controls`.

## C03 · IMPLEMENTED

Foot up

Evidence: E03, E08, E09, E10, E14, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:AXES, LAYOUTS, motor_control_specs, _move_axis, hold_control`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_models_and_cover_controls`.

## C04 · IMPLEMENTED

Foot down

Evidence: E03, E08, E09, E10, E14, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:AXES, LAYOUTS, motor_control_specs, _move_axis, hold_control`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_models_and_cover_controls`.

## C05 · IMPLEMENTED

Combined head and foot up

Evidence: E03, E08, E09, E10, E14, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:AXES, LAYOUTS, motor_control_specs, _move_axis, hold_control`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_models_and_cover_controls`.

## C06 · IMPLEMENTED

Combined head and foot down

Evidence: E03, E08, E09, E10, E14, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:AXES, LAYOUTS, motor_control_specs, _move_axis, hold_control`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_models_and_cover_controls`.

## C07 · IMPLEMENTED

Neck tilt up

Evidence: E03, E08, E09, E10, E14, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:AXES, LAYOUTS, motor_control_specs, _move_axis, hold_control`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_models_and_cover_controls`.

## C08 · IMPLEMENTED

Neck tilt down

Evidence: E03, E08, E09, E10, E14, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:AXES, LAYOUTS, motor_control_specs, _move_axis, hold_control`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_models_and_cover_controls`.

## C09 · IMPLEMENTED

Elevation up

Evidence: E03, E08, E09, E10, E14, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:AXES, LAYOUTS, motor_control_specs, _move_axis, hold_control`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_models_and_cover_controls`.

## C10 · IMPLEMENTED

Elevation down

Evidence: E03, E08, E09, E10, E14, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:AXES, LAYOUTS, motor_control_specs, _move_axis, hold_control`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_models_and_cover_controls`.

## C11 · IMPLEMENTED

STOP/release

Evidence: E08, E09, E11, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:stop_all, _release_frames`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_event_cancel_still_releases_twice, test_repeated_task_cancellation_cannot_abandon_release`.

## C12 · IMPLEMENTED

Flat

Evidence: E08, E09, E10, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:PRESETS, preset_flat, preset_anti_snore, preset_zero_g, preset_memory`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_entity_actions_use_live_vectors, test_recall_does_not_program_and_invalid_slots_write_nothing`.

## C13 · IMPLEMENTED

Anti-snore

Evidence: E08, E09, E10, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:PRESETS, preset_flat, preset_anti_snore, preset_zero_g, preset_memory`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_entity_actions_use_live_vectors, test_recall_does_not_program_and_invalid_slots_write_nothing`.

## C14 · IMPLEMENTED

Zero gravity

Evidence: E08, E09, E10, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:PRESETS, preset_flat, preset_anti_snore, preset_zero_g, preset_memory`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_entity_actions_use_live_vectors, test_recall_does_not_program_and_invalid_slots_write_nothing`.

## C15 · IMPLEMENTED

Memory A recall

Evidence: E08, E09, E10, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:PRESETS, preset_flat, preset_anti_snore, preset_zero_g, preset_memory`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_entity_actions_use_live_vectors, test_recall_does_not_program_and_invalid_slots_write_nothing`.

## C16 · IMPLEMENTED

Memory B recall

Evidence: E08, E09, E10, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:PRESETS, preset_flat, preset_anti_snore, preset_zero_g, preset_memory`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_entity_actions_use_live_vectors, test_recall_does_not_program_and_invalid_slots_write_nothing`.

## C17 · IMPLEMENTED

Memory A program by hold

Evidence: E08, E09, E14, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:program_memory, MEMORY_HOLD_SECONDS`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors`.

## C18 · IMPLEMENTED

Memory B program by hold

Evidence: E08, E09, E14, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:program_memory, MEMORY_HOLD_SECONDS`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors`.

## C19 · IMPLEMENTED

Under-bed light toggle

Evidence: E09, E10, E14, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:lights_toggle, supports_light_toggle_control`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_entity_exposure_and_stale_model_cleanup`.

## C20 · IMPLEMENTED

Massage intensity increase

Evidence: E03, E08, E11, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:MASSAGE, _massage, massage_*`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_entity_actions_use_live_vectors, test_entity_exposure_and_stale_model_cleanup`.

## C21 · IMPLEMENTED

Massage intensity decrease

Evidence: E03, E08, E11, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:MASSAGE, _massage, massage_*`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_entity_actions_use_live_vectors, test_entity_exposure_and_stale_model_cleanup`.

## C22 · IMPLEMENTED

Massage wave increase

Evidence: E03, E08, E11, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:MASSAGE, _massage, massage_*`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_entity_actions_use_live_vectors, test_entity_exposure_and_stale_model_cleanup`.

## C23 · IMPLEMENTED

Massage wave decrease

Evidence: E03, E08, E11, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:MASSAGE, _massage, massage_*`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_entity_actions_use_live_vectors, test_entity_exposure_and_stale_model_cleanup`.

## C24 · IMPLEMENTED

Massage timer cycle

Evidence: E03, E08, E11, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:MASSAGE, _massage, massage_*`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_entity_actions_use_live_vectors, test_entity_exposure_and_stale_model_cleanup`.

## C25 · IMPLEMENTED

Massage off button

Evidence: E03, E08, E11, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:MASSAGE, _massage, massage_*`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_entity_actions_use_live_vectors, test_entity_exposure_and_stale_model_cleanup`.

## C26 · IMPLEMENTED

Query alarm status

Evidence: E12, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:query_alarm, controller_button_specs`.

Tests: `tests/test_glideaway_motion.py:test_query_alarm_twice_and_explicit_clock_sync`.

## C27 · IMPLEMENTED

Enable alarm, wake NONE

Evidence: E12, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:alarm_frame, configure_clock_alarm; services.py:handle_glideaway_set_alarm`.

Tests: `tests/test_glideaway_motion.py:test_alarm_vectors_rtc_sequence_and_parser, test_calendar_and_rtc_vectors, test_alarm_service_validation_and_queue, test_alarm_whole_selection_validation_before_dispatch`.

## C28 · IMPLEMENTED

Enable alarm, wake MA

Evidence: E12, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:alarm_frame, configure_clock_alarm; services.py:handle_glideaway_set_alarm`.

Tests: `tests/test_glideaway_motion.py:test_alarm_vectors_rtc_sequence_and_parser, test_calendar_and_rtc_vectors, test_alarm_service_validation_and_queue, test_alarm_whole_selection_validation_before_dispatch`.

## C29 · IMPLEMENTED

Enable alarm, wake MB

Evidence: E12, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:alarm_frame, configure_clock_alarm; services.py:handle_glideaway_set_alarm`.

Tests: `tests/test_glideaway_motion.py:test_alarm_vectors_rtc_sequence_and_parser, test_calendar_and_rtc_vectors, test_alarm_service_validation_and_queue, test_alarm_whole_selection_validation_before_dispatch`.

## C30 · IMPLEMENTED

Disable alarm

Evidence: E12, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:alarm_frame, configure_clock_alarm; services.py:handle_glideaway_set_alarm`.

Tests: `tests/test_glideaway_motion.py:test_alarm_vectors_rtc_sequence_and_parser, test_calendar_and_rtc_vectors, test_alarm_service_validation_and_queue, test_alarm_whole_selection_validation_before_dispatch`.

## C31 · IMPLEMENTED

Set RTC

Evidence: E12, E05, E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:rtc_frame, sync_clock, configure_clock_alarm`.

Tests: `tests/test_glideaway_motion.py:test_calendar_and_rtc_vectors, test_query_alarm_twice_and_explicit_clock_sync, test_public_hold_and_sync_clock_dispatch`.

## N1 · IMPLEMENTED

E7 FE and len>=10; byte8 unsigned timer code

Evidence: E13.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:_on_notification, _timer`.

Tests: `tests/test_glideaway_motion.py:test_timer_notification_vectors`.

## N2 · IMPLEMENTED

ED FE and len>=16; byte14 unsigned timer code

Evidence: E13.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:_on_notification, _timer`.

Tests: `tests/test_glideaway_motion.py:test_timer_notification_vectors`.

## N3 · IMPLEMENTED

F4 FE and len>20; byte19 unsigned timer code

Evidence: E13.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:_on_notification, _timer`.

Tests: `tests/test_glideaway_motion.py:test_timer_notification_vectors, test_complete_f4_and_signed_alarm_state`.

## N4 · IMPLEMENTED

Any other packet starting F4; Copy entire packet into global30-byte buffer; set needJoint and receiveLen. Next unmatched packet appended, then use buffer19.

Evidence: E13.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:_on_notification, _timer`.

Tests: `tests/test_glideaway_motion.py:test_fragmentation_and_safe_bounds`.

## N5 · IMPLEMENTED

ED 80; Copy bytes3..end into 13-byte payload; on=any(first4); signed hour/minute=payload0/1; wake=MA if payload3=11hex, MB if13hex, elseNONE; daymask ignored.

Evidence: E13.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:_on_notification, _timer`.

Tests: `tests/test_glideaway_motion.py:test_alarm_vectors_rtc_sequence_and_parser, test_complete_f4_and_signed_alarm_state`.

## BED_TYPE_400 · IMPLEMENTED

GM-A4Z; explicit model-specific controls

Evidence: E03, E10, E14.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:LAYOUTS, motor_control_specs, supports_massage, supports_lights; detection.py:APP_VARIANT_CHOICES`.

Tests: `tests/test_glideaway_motion.py:test_models_and_cover_controls, test_manual_setup_saves_explicit_app_model, test_entity_exposure_and_stale_model_cleanup`.

## BED_TYPE_450 · IMPLEMENTED

GM-A450Z; explicit model-specific controls

Evidence: E03, E10, E14.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:LAYOUTS, motor_control_specs, supports_massage, supports_lights; detection.py:APP_VARIANT_CHOICES`.

Tests: `tests/test_glideaway_motion.py:test_models_and_cover_controls, test_manual_setup_saves_explicit_app_model, test_entity_exposure_and_stale_model_cleanup`.

## BED_TYPE_500 · IMPLEMENTED

GM-A5Z; explicit model-specific controls

Evidence: E03, E10, E14.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:LAYOUTS, motor_control_specs, supports_massage, supports_lights; detection.py:APP_VARIANT_CHOICES`.

Tests: `tests/test_glideaway_motion.py:test_models_and_cover_controls, test_manual_setup_saves_explicit_app_model, test_entity_exposure_and_stale_model_cleanup`.

## BED_TYPE_600 · IMPLEMENTED

GM-A6Z; explicit model-specific controls

Evidence: E03, E10, E14.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:LAYOUTS, motor_control_specs, supports_massage, supports_lights; detection.py:APP_VARIANT_CHOICES`.

Tests: `tests/test_glideaway_motion.py:test_models_and_cover_controls, test_manual_setup_saves_explicit_app_model, test_entity_exposure_and_stale_model_cleanup`.

## B01 · IMPLEMENTED

Normal LE mask/zero parameter/complement checksum, all 25 live normal rows

Evidence: E07.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:frame, command_frame`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors`.

## B02 · IMPLEMENTED

RTC calendar offsets, midnight FF; local HA clock

Evidence: E12.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:rtc_frame`.

Tests: `tests/test_glideaway_motion.py:test_calendar_and_rtc_vectors, test_query_alarm_twice_and_explicit_clock_sync`.

## B03 · IMPLEMENTED

Alarm padded builder, three wake bytes, off zeros, literal weekday/wheel mapping

Evidence: E12.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:alarm_frame, configure_clock_alarm`.

Tests: `tests/test_glideaway_motion.py:test_alarm_vectors_rtc_sequence_and_parser, test_calendar_and_rtc_vectors`.

## R01 · IMPLEMENTED

300 ms refresh and +300/+600 ms zero-mask releases

Evidence: E08, E09, E11.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:_hold, _release_frames, stop_all`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_models_and_cover_controls, test_event_cancel_still_releases_twice, test_repeated_task_cancellation_cannot_abandon_release, test_write_failure_still_attempts_release, test_first_release_failure_still_attempts_second`.

## R02 · IMPLEMENTED

Query immediate/+200 ms; RTC then alarm +300 ms

Evidence: E12.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:query_alarm, configure_clock_alarm`.

Tests: `tests/test_glideaway_motion.py:test_query_alarm_twice_and_explicit_clock_sync, test_alarm_vectors_rtc_sequence_and_parser`.

## R03 · IMPLEMENTED

Memory 5.2 s stream, local toast is not a bed ACK

Evidence: E08, E14.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:program_memory, preset_memory, validate_hold_control`.

Tests: `tests/test_glideaway_motion.py:test_command_vectors, test_recall_does_not_program_and_invalid_slots_write_nothing`.

## ST01 · IMPLEMENTED

Unsigned timer, FF sentinel, raw/display comparison without maximum (accepted R01-F01)

Evidence: E13.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:_timer, controller_state_sensor_specs`.

Tests: `tests/test_glideaway_motion.py:test_timer_notification_vectors, test_audited_timer_previous_display_comparison`.

## ST02 · IMPLEMENTED

Alarm enabled first-four fields; signed hour/minute, unknown wake=none; day not schedule

Evidence: E13.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:_on_notification, controller_state_sensor_specs`.

Tests: `tests/test_glideaway_motion.py:test_alarm_vectors_rtc_sequence_and_parser, test_complete_f4_and_signed_alarm_state`.

## ST03 · IMPLEMENTED

Reported sensors/model cleanup; no optimistic ACK, angle, light or massage level state

Evidence: E13, E16.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:controller_state_sensor_specs, invalidate_diagnostics; sensor.py:_sensor_entities_for`.

Tests: `tests/test_glideaway_motion.py:test_entity_exposure_and_stale_model_cleanup, test_fragmentation_and_safe_bounds`.

## PUB01 · IMPLEMENTED

Public covers, presets, save, light, all live massage actions, alarm refresh

Evidence: E03, E08, E09, E10, E11, E12.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:motor_control_specs, controller_button_specs; button.py:_button_entities_for`.

Tests: `tests/test_glideaway_motion.py:test_entity_exposure_and_stale_model_cleanup, test_entity_actions_use_live_vectors`.

## PUB02 · IMPLEMENTED

Typed alarm/hold/clock service exposure and target validation

Evidence: E08, E12.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:hold_control, sync_clock; services.py:handle_glideaway_set_alarm, handle_hold_control, handle_sync_clock`.

Tests: `tests/test_glideaway_motion.py:test_alarm_service_validation_and_queue, test_alarm_whole_selection_validation_before_dispatch, test_public_hold_and_sync_clock_dispatch`.

## G01 · IMPLEMENTED

Exact GATT roles, no startup query/auth/RTC, no forced unsupported write mode

Evidence: E04, E05, E06.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:_role, write_command, start_notify`.

Tests: `tests/test_glideaway_motion.py:test_gatt_roles_subscription_and_mode`.

## CAP01 · IMPLEMENTED

Model-gated extras, fixed motor layouts, two memories, no single-address sides or position feedback

Evidence: E03, E10, E13, E16.

Code: `custom_components/adjustable_bed/beds/glideaway_motion.py:LAYOUTS, supports_single_address_pairing, memory_slot_count, supports_massage, supports_lights; app_profiles.py:_BY_BED_TYPE`.

Tests: `tests/test_glideaway_motion.py:test_models_and_cover_controls, test_factory_manual_models_and_profile_ownership`.

## S01 · EXCLUDED

Indefinite streams and missing combined/light release

Evidence: E08, E09, E11.

Safety: finite cover presses/explicit holds (maximum 30 s) always release with the proven global zero mask. App omissions are not evidence of hardware auto-stop. Tests test_command_vectors and test_entity_actions_use_live_vectors exercise the safe stream.

## S02 · EXCLUDED

Stale runner after disconnect, STOP interleaving/new selected device

Evidence: E06, E08.

Safety: HA cancels commands, serializes cleanup and scopes controllers per target. Never revive stale motion on reconnect; see test_repeated_task_cancellation_cannot_abandon_release and coordinator serialization tests.

## S03 · EXCLUDED

Unsafe global fragment buffer, short/overflow copies, indefinite stale joins

Evidence: E13.

Safety: per-controller buffer <=30 bytes, reset on connection/recognized frames, two-second local expiration, minimum assembled length20. Full F4 FE branch retains the unbounded length>20 condition. Tests test_fragmentation_and_safe_bounds, test_complete_f4_and_signed_alarm_state.

## X05 · EXCLUDED

Android permissions, scan UI timeout, copied/discarded advertisement bytes, display fallback, 200 ms UI callback, max-three connector map

Evidence: E04, E05, E06.

Unrelated phone UI/transport implementation. No content filter or capability proof; HA supplies scan/connect/proxy infrastructure. No Android-specific defect or UI delay becomes a bed feature.

## X06 · EXCLUDED

WiFi, cloud/accounts, provisioning, network administration

Evidence: E01, E16.

Outside direct BLE bed product boundary. Exhaustive accepted searches found no such bed path; framework network-state tracking is phone infrastructure.

## X07 · EXCLUDED

Authentication/PIN/bond, capability/firmware/DIS/OTA, EEPROM/reset/calibration and side/sync selectors

Evidence: E01, E04, E05, E06, E16.

No reachable app command/response exists, accepted negative searches and full transport inventory. No guessed features, startup writes or arbitrary model/address mappings.

## X08 · EXCLUDED

Guide-stated five-minute lamp auto-off and other unsupported lamp controls

Evidence: E14, E16.

Guide only, no BLE timeout-setting/state/brightness/color/zone path. Documented claim remains hardware-unverified; do not invent a write or report assumed lamp state.

## X09 · EXCLUDED

Local saved toast and timer event suppression

Evidence: E08, E13, E14.

Phone presentation only: preserve memory hold and displayed timer values, expose raw timer diagnostics, but do not claim device save acknowledgement or require Android emission suppression in HA.

## Frontend and physical validation

The card buckets the Refresh alarm button into utilities and the reported timer
into massage. `frontend/src/discovery.test.ts` test “Glideaway exposes its
reported massage timer and alarm refresh” proves these keys plus tilt/elevation
covers. The committed bundle is rebuilt from source.

[The user guide](../../beds/glideaway-motion.md) documents every wire mask,
calendar offset, model gate, public action and deliberate safety difference.
Real-user post-beta checks remain deferred external validation: GATT properties,
physical tilt/elevation, memory storage threshold, alarm midnight/weekdays,
fragmentation and light cessation/guide auto-off. Static coverage is complete;
physical correctness is not claimed. No merge or deployment is part of this work.
