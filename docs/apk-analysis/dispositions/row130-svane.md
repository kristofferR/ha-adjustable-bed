# Unit 130: Svane Remote implementation disposition

Implementation has focused author validation (637 Svane/Jensen/discovery tests and 984 broad configuration/compatibility tests). Ruff and Pyright pass. Local crq preflight was skipped by the shared account quota; this is not a clean review receipt. Retired notification callbacks are rejected before raw or state forwarding. Final full-suite validation, latest-master binding and independent convergence review remain required before acceptance or PR merge. Physical hardware is unverified.

The accepted package is `com.svane.svaneremote` Version 1.8 (8). Artifact-set SHA-256: `11b1e26276044bd19b09ad35d52a7f0c5927830f20fab6e90278d039f82bfb71`. Accepted REPORT.SHA256: `627a4fa1e673a660094c7475ee7bb7d2f0d562fc125d253ce0315ec5f8c1bd4f`. Accepting independent audit003 AUDIT.SHA256: `dc826283087af974248e3ed92a6fd0079a7c22a0c9b2d68998479660a8bfd2a2`. Full semantic audits001/002 and their repair histories remain bound by audit003. Raw artifacts/reports stay machine-local.

The immutable post-freeze comparison has **663 rows: 401 IMPLEMENTED, 6 ALREADY_IMPLEMENTED, 256 EXCLUDED**. Counts include structural negative/census claims and overlapping evidence, not 663 hardware operations. All 3173 domain leaf pointers have one owner. The separate **200-vector** plan has 146 BLE implementation vectors and 54 exact Classic/OTA exclusions. Excluded vectors remain verified accepted artifact evidence; they do not create integration operations.

Two explicit BLE profiles preserve source destinations, raw memory, initialization, release and local lamp intent. The Jensen LinOn adaptation replaces inheritance from Svane with its own unchanged legacy endpoint writer and movement delegation on `BedController`; it retains its one-byte commands, 800 ms cadence and existing tests, while preventing new Svane entities, initialization or held actions leaking into that app. Generic Jensen is unchanged. See the [profile contract and user actions](../../beds/svane.md).

## Proof catalog

Code and test symbols below are bound by file and AST-symbol SHA-256 in the additive machine-local implementation map. References are shared by several claims; each row retains its exact accepted JSON pointer and source anchor. Tests execute source literals and real public service/entity/config paths, including paired physical-side preference persistence. Unsafe source cases bind the safe host handling plus the exact exclusions below, not an assertion that HA reproduces a crash.

| Area | Production symbols | Focused proof |
| --- | --- | --- |
| GATT | [`SvaneController._role`](../../../custom_components/adjustable_bed/beds/svane.py#L264)<br>[`SvaneController._write`](../../../custom_components/adjustable_bed/beds/svane.py#L279) | [`test_exact_role_and_property_backed_write_mode`](../../../tests/test_svane.py#L251)<br>[`test_role_failure_precedes_any_movement`](../../../tests/test_svane.py#L259)<br>[`test_artifact_literal_destination`](../../../tests/test_svane_artifact_vectors.py#L437) |
| INIT | [`SvaneController.start_notify`](../../../custom_components/adjustable_bed/beds/svane.py#L411)<br>[`SvaneController.refresh_device_information`](../../../custom_components/adjustable_bed/beds/svane.py#L386)<br>[`SvaneController._read_state`](../../../custom_components/adjustable_bed/beds/svane.py#L396) | [`test_initialization_exact_order_old_cccd_normal_query_and_every_read`](../../../tests/test_svane.py#L275)<br>[`test_state_read_attempts_all_present_roles_in_order`](../../../tests/test_svane.py#L322)<br>[`test_partial_dis_observation_survives_later_failure_and_reconstruction`](../../../tests/test_svane.py#L338)<br>[`test_initialization_cancel_stops_before_query_preserves_completed_metadata`](../../../tests/test_svane.py#L530) |
| PROFILE | [`create_controller`](../../../custom_components/adjustable_bed/controller_factory.py#L390)<br>[`SvaneController.__init__`](../../../custom_components/adjustable_bed/beds/svane.py#L98)<br>[`SvaneController.controller_button_specs`](../../../custom_components/adjustable_bed/beds/svane.py#L204)<br>[`SvaneController.controller_number_specs`](../../../custom_components/adjustable_bed/beds/svane.py#L217)<br>[`SvaneController.controller_state_sensor_specs`](../../../custom_components/adjustable_bed/beds/svane.py#L225)<br>[`JensenLinonController`](../../../custom_components/adjustable_bed/beds/jensen_linon.py#L71) | [`test_stored_profile_factory_preserves_old_routes_and_explicit_jmc`](../../../tests/test_svane_profiles.py#L58)<br>[`test_native_entities_expose_literals_raw_records_and_unknown_assumed_lamp`](../../../tests/test_svane_profiles.py#L165)<br>[`test_real_parser_coordinator_and_diagnostic_freshness_no_angle_inference`](../../../tests/test_svane_profiles.py#L207)<br>[`TestJensenLinonMovement`](../../../tests/test_jensen_linon.py#L103) |
| DISCOVERY | [`detect_bed_type_detailed`](../../../custom_components/adjustable_bed/detection.py#L1005)<br>[`_add_svane_schema_fields`](../../../custom_components/adjustable_bed/config_flow.py#L949)<br>[`AdjustableBedConfigFlow._finish_with_verify`](../../../custom_components/adjustable_bed/config_flow.py#L4995)<br>[`AdjustableBedOptionsFlow._async_options_form`](../../../custom_components/adjustable_bed/config_flow.py#L5974)<br>[`svane_profile_for_selected_name`](../../../custom_components/adjustable_bed/svane_state.py#L107)<br>[`is_svane_discovery_name`](../../../custom_components/adjustable_bed/svane_state.py#L112) | [`test_shared_or_nonexact_name_does_not_silently_select_svane_app`](../../../tests/test_svane_profiles.py#L156)<br>[`test_all_setup_forms_explicit_profile_without_unproven_layout_or_timing`](../../../tests/test_svane_profiles.py#L79)<br>[`test_preverification_normalizes_legacy_options_before_probe`](../../../tests/test_svane_profiles.py#L106)<br>[`test_options_explicit_jmc_persists_and_clears_changed_app_session`](../../../tests/test_svane_profiles.py#L125)<br>[`test_changed_bed_type_rebuilds_hidden_generic_choices_before_entry`](../../../tests/test_svane_profiles.py#L325)<br>[`test_new_explicit_svane_selection_uses_case_sensitive_app_name_rule`](../../../tests/test_svane_profiles.py#L357)<br>[`test_source_exact_scan_allowlist_independent_of_known_address_selection`](../../../tests/test_svane_profiles.py#L390) |
| LIGHT | [`SvaneCommands.light_brightness`](../../../custom_components/adjustable_bed/beds/svane.py#L58)<br>[`SvaneController.hold_control`](../../../custom_components/adjustable_bed/beds/svane.py#L508)<br>[`SvaneController.lights_toggle`](../../../custom_components/adjustable_bed/beds/svane.py#L706)<br>[`SvaneController.set_light_level`](../../../custom_components/adjustable_bed/beds/svane.py#L712)<br>[`get_svane_session`](../../../custom_components/adjustable_bed/svane_state.py#L70) | [`test_java_int32_light_vectors`](../../../tests/test_svane.py#L99)<br>[`test_lamp_triangle_updates_intent_before_failure_and_no_release_frame`](../../../tests/test_svane.py#L426)<br>[`test_lamp_hold_off_or_short_no_io`](../../../tests/test_svane.py#L442)<br>[`test_top_defaults_light_on_off_and_no_extra_stop`](../../../tests/test_svane.py#L407)<br>[`test_native_entities_expose_literals_raw_records_and_unknown_assumed_lamp`](../../../tests/test_svane_profiles.py#L165) |
| MEMORY | [`SvaneController.program_memory`](../../../custom_components/adjustable_bed/beds/svane.py#L670)<br>[`SvaneController.preset_memory`](../../../custom_components/adjustable_bed/beds/svane.py#L653)<br>[`SvaneController.execute_app_control`](../../../custom_components/adjustable_bed/beds/svane.py#L720)<br>[`get_svane_session`](../../../custom_components/adjustable_bed/svane_state.py#L70)<br>[`AdjustableBedCoordinator.remember_svane_preferences`](../../../custom_components/adjustable_bed/coordinator.py#L1198) | [`test_save_read_only_and_recall_exact_opaque_bytes`](../../../tests/test_svane.py#L384)<br>[`test_unbounded_p1_raw_memory_and_cancelled_head_feet_gap`](../../../tests/test_svane.py#L397)<br>[`test_process_cache_rebuild_cold_restart_and_target_isolation`](../../../tests/test_svane.py#L450)<br>[`test_paired_persistence_and_parent_to_standalone_migration_remain_target_local`](../../../tests/test_svane_profiles.py#L257)<br>[`test_artifact_literal_destination`](../../../tests/test_svane_artifact_vectors.py#L437) |
| RAW | [`SvaneController.accept_response`](../../../custom_components/adjustable_bed/beds/svane.py#L318)<br>[`SvaneController._read_state`](../../../custom_components/adjustable_bed/beds/svane.py#L396)<br>[`SvaneController.execute_app_control`](../../../custom_components/adjustable_bed/beds/svane.py#L720)<br>[`SvaneController._observe`](../../../custom_components/adjustable_bed/beds/svane.py#L306)<br>[`SvaneController._subscribe`](../../../custom_components/adjustable_bed/beds/svane.py#L340) | [`test_dispatch_origin_precedence_and_short_buffers`](../../../tests/test_svane.py#L367)<br>[`test_state_read_attempts_all_present_roles_in_order`](../../../tests/test_svane.py#L322)<br>[`test_artifact_literal_destination`](../../../tests/test_svane_artifact_vectors.py#L437)<br>[`test_real_parser_coordinator_and_diagnostic_freshness_no_angle_inference`](../../../tests/test_svane_profiles.py#L207)<br>[`test_retired_notification_callback_cannot_forward_raw_or_state`](../../../tests/test_svane.py#L499) |
| MOTOR | [`SvaneController.hold_control`](../../../custom_components/adjustable_bed/beds/svane.py#L508)<br>[`SvaneController.motor_control_specs`](../../../custom_components/adjustable_bed/beds/svane.py#L127)<br>[`handle_svane_hold_control`](../../../custom_components/adjustable_bed/services.py#L1856) | [`test_literal_held_actions_and_release`](../../../tests/test_svane.py#L129)<br>[`test_source_schedule_after_work`](../../../tests/test_svane.py#L157)<br>[`test_real_hold_endpoint_frames_and_cleanup`](../../../tests/test_svane_services.py#L43)<br>[`test_mixed_profile_native_pair_routes_each_physical_target`](../../../tests/test_svane_services.py#L99)<br>[`test_later_target_rejected_before_first_motion`](../../../tests/test_svane_services.py#L70) |
| RELEASE | [`SvaneController.hold_control`](../../../custom_components/adjustable_bed/beds/svane.py#L508)<br>[`SvaneController._release`](../../../custom_components/adjustable_bed/beds/svane.py#L578)<br>[`SvaneController.request_svane_axis_release`](../../../custom_components/adjustable_bed/beds/svane.py#L477)<br>[`SvaneController.stop_notify`](../../../custom_components/adjustable_bed/beds/svane.py#L436)<br>[`handle_svane_release_axis`](../../../custom_components/adjustable_bed/services.py#L1879) | [`test_partial_release_preserves_remaining_axis`](../../../tests/test_svane.py#L174)<br>[`test_started_roles_cleanup_after_cancellation_or_write_failure`](../../../tests/test_svane.py#L199)<br>[`test_cleanup_attempts_all_p1_directions_when_one_stop_fails`](../../../tests/test_svane.py#L226)<br>[`test_notify_lifecycle_cleanup_unsubscribes_even_failed_motor_release`](../../../tests/test_svane.py#L487)<br>[`test_axis_release_endpoint_signals_active_real_writer_no_independent_ble_lane`](../../../tests/test_svane_services.py#L144)<br>[`test_retired_notification_callback_cannot_forward_raw_or_state`](../../../tests/test_svane.py#L499) |

## Every discovery disposition

`S#` identifies an exact pointer in the accepted package-local analysis.json. Source inventories, all frozen file hashes, exact source anchor ranges and executed test bindings live in the preserved comparison and additive implementation evidence. The following table lists every row, including all 256 exclusions with its precise reason.

| ID | Accepted claim | Disposition | Proof area or exact exclusion |
| --- | --- | --- | --- |
| R130-0001 | `S#/candidate_ledger/0` | IMPLEMENTED | INIT |
| R130-0002 | `S#/candidate_ledger/1` | IMPLEMENTED | PROFILE |
| R130-0003 | `S#/candidate_ledger/2` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. User-selected live Classic controller; out of BLE scope. |
| R130-0004 | `S#/candidate_ledger/3` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: No constructor calls; all BedProtocol methods stub. |
| R130-0005 | `S#/candidate_ledger/4` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: No constructor calls; UUIDs/commands unused, methods stub. |
| R130-0006 | `S#/candidate_ledger/5` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: No constructor calls; live OldService uses supplied LinonPIProtocol. |
| R130-0007 | `S#/candidate_ledger/6` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: readPosition/goToPos/goToSavePosition/gotToSavePosition/savePosition/flattenBed/translatePosition are not called by reachable transport actions. setLight(true) not used by UI. Endstop/current/load/light-intensity/device-number/serial/software-info UUID constants have no live read destination. |
| R130-0008 | `S#/candidate_ledger/7` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Main fragments use enum overload. Raw multi-bed packet mutation/DFU misrouting and five-second split-write path are not live normal controls. |
| R130-0009 | `S#/candidate_ledger/8` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: No subclass/instance that can connect; callbacks alone are not reachable transport. |
| R130-0010 | `S#/candidate_ledger/9` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Reverse caller search only definitions; normal connection uses other overloads. |
| R130-0011 | `S#/candidate_ledger/10` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Main ACTION_DATA_AVAILABLE receiver does not invoke either; asset-specific16.0/16.1 mapping dormant. |
| R130-0012 | `S#/candidate_ledger/11` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Firmware update dialog leads boot command, address change, DFU service and completion reconnect; only boundary affects BLE controls. |
| R130-0013 | `S#/candidate_ledger/12` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Six GATT compatibility strategies, Legacy/Secure payload transfer and bond helpers; firmware-update scope, no bed command factories. |
| R130-0014 | `S#/candidate_ledger/13` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Six zip payloads inspected manifest/data/hash/strings; not host execution. OnlyRC18 asset opened on live update path. |
| R130-0015 | `S#/candidate_ledger/14` | EXCLUDED | Phone alarm/audio/browser/pager/logging/build identity is unrelated to BLE bed control. All discovery, selection, persistence or packet effects in the same app remain separately in scope. Phone alarm audio/local notification and browser Intent only; no alarm motor command/network client. |
| R130-0016 | `S#/candidate_ledger/15` | EXCLUDED | Phone alarm/audio/browser/pager/logging/build identity is unrelated to BLE bed control. All discovery, selection, persistence or packet effects in the same app remain separately in scope. Reflection confined to library serialization/UI or SDK GATT refresh/bond removal; no dynamic bed transport implementation. |
| R130-0017 | `S#/candidate_ledger/16` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0018 | `S#/candidate_ledger/17` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0019 | `S#/candidate_ledger/18` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Local-file I/O; not Bluetooth. |
| R130-0020 | `S#/candidate_ledger/19` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Local-file I/O; not Bluetooth. |
| R130-0021 | `S#/candidate_ledger/20` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0022 | `S#/candidate_ledger/21` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0023 | `S#/candidate_ledger/22` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0024 | `S#/candidate_ledger/23` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0025 | `S#/candidate_ledger/24` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0026 | `S#/candidate_ledger/25` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0027 | `S#/candidate_ledger/26` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0028 | `S#/candidate_ledger/27` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0029 | `S#/candidate_ledger/28` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0030 | `S#/candidate_ledger/29` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0031 | `S#/candidate_ledger/30` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0032 | `S#/candidate_ledger/31` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0033 | `S#/candidate_ledger/32` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0034 | `S#/candidate_ledger/33` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0035 | `S#/candidate_ledger/34` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0036 | `S#/candidate_ledger/35` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0037 | `S#/candidate_ledger/36` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0038 | `S#/candidate_ledger/37` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0039 | `S#/candidate_ledger/38` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0040 | `S#/candidate_ledger/39` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0041 | `S#/candidate_ledger/40` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0042 | `S#/candidate_ledger/41` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0043 | `S#/candidate_ledger/42` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0044 | `S#/candidate_ledger/43` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0045 | `S#/candidate_ledger/44` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0046 | `S#/candidate_ledger/45` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0047 | `S#/candidate_ledger/46` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0048 | `S#/candidate_ledger/47` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0049 | `S#/candidate_ledger/48` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0050 | `S#/candidate_ledger/49` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0051 | `S#/candidate_ledger/50` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0052 | `S#/candidate_ledger/51` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0053 | `S#/candidate_ledger/52` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0054 | `S#/candidate_ledger/53` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0055 | `S#/candidate_ledger/54` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0056 | `S#/candidate_ledger/55` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0057 | `S#/candidate_ledger/56` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0058 | `S#/candidate_ledger/57` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0059 | `S#/candidate_ledger/58` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0060 | `S#/candidate_ledger/59` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0061 | `S#/candidate_ledger/60` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0062 | `S#/candidate_ledger/61` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0063 | `S#/candidate_ledger/62` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0064 | `S#/candidate_ledger/63` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0065 | `S#/candidate_ledger/64` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0066 | `S#/candidate_ledger/65` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0067 | `S#/candidate_ledger/66` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0068 | `S#/candidate_ledger/67` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0069 | `S#/candidate_ledger/68` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0070 | `S#/candidate_ledger/69` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0071 | `S#/candidate_ledger/70` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0072 | `S#/candidate_ledger/71` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0073 | `S#/candidate_ledger/72` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0074 | `S#/candidate_ledger/73` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0075 | `S#/candidate_ledger/74` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0076 | `S#/candidate_ledger/75` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0077 | `S#/candidate_ledger/76` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0078 | `S#/candidate_ledger/77` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0079 | `S#/candidate_ledger/78` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0080 | `S#/candidate_ledger/79` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Local-file I/O; not Bluetooth. |
| R130-0081 | `S#/candidate_ledger/80` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Local-file I/O; not Bluetooth. |
| R130-0082 | `S#/candidate_ledger/81` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0083 | `S#/candidate_ledger/82` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0084 | `S#/candidate_ledger/83` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0085 | `S#/candidate_ledger/84` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0086 | `S#/candidate_ledger/85` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. OTA SDK transport, reached only from DfuService; not normal control. |
| R130-0087 | `S#/candidate_ledger/86` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned reachable Bluetooth Classic; out of BLE scope. |
| R130-0088 | `S#/candidate_ledger/87` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned reachable Bluetooth Classic; out of BLE scope. |
| R130-0089 | `S#/candidate_ledger/88` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned reachable Bluetooth Classic; out of BLE scope. |
| R130-0090 | `S#/candidate_ledger/89` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned reachable Bluetooth Classic; out of BLE scope. |
| R130-0091 | `S#/candidate_ledger/90` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned reachable Bluetooth Classic; out of BLE scope. |
| R130-0092 | `S#/candidate_ledger/91` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned reachable Bluetooth Classic; out of BLE scope. |
| R130-0093 | `S#/candidate_ledger/92` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned reachable Bluetooth Classic; out of BLE scope. |
| R130-0094 | `S#/candidate_ledger/93` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned reachable Bluetooth Classic; out of BLE scope. |
| R130-0095 | `S#/candidate_ledger/94` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned reachable Bluetooth Classic; out of BLE scope. |
| R130-0096 | `S#/candidate_ledger/95` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned reachable Bluetooth Classic; out of BLE scope. |
| R130-0097 | `S#/candidate_ledger/96` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned reachable Bluetooth Classic; out of BLE scope. |
| R130-0098 | `S#/candidate_ledger/97` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned reachable Bluetooth Classic; out of BLE scope. |
| R130-0099 | `S#/candidate_ledger/98` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned reachable Bluetooth Classic; out of BLE scope. |
| R130-0100 | `S#/candidate_ledger/99` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uninstantiated callback scaffold; no connection callsite. |
| R130-0101 | `S#/candidate_ledger/100` | IMPLEMENTED | GATT |
| R130-0102 | `S#/candidate_ledger/101` | IMPLEMENTED | PROFILE |
| R130-0103 | `S#/candidate_ledger/102` | IMPLEMENTED | GATT |
| R130-0104 | `S#/candidate_ledger/103` | IMPLEMENTED | GATT |
| R130-0105 | `S#/candidate_ledger/104` | IMPLEMENTED | GATT |
| R130-0106 | `S#/candidate_ledger/105` | IMPLEMENTED | GATT |
| R130-0107 | `S#/candidate_ledger/106` | IMPLEMENTED | GATT |
| R130-0108 | `S#/candidate_ledger/107` | IMPLEMENTED | GATT |
| R130-0109 | `S#/candidate_ledger/108` | IMPLEMENTED | GATT |
| R130-0110 | `S#/candidate_ledger/109` | IMPLEMENTED | GATT |
| R130-0111 | `S#/candidate_ledger/110` | IMPLEMENTED | GATT |
| R130-0112 | `S#/candidate_ledger/111` | IMPLEMENTED | GATT |
| R130-0113 | `S#/candidate_ledger/112` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uncalled helper/overload; reverse search retained in followup-reachability. |
| R130-0114 | `S#/candidate_ledger/113` | IMPLEMENTED | PROFILE |
| R130-0115 | `S#/candidate_ledger/114` | IMPLEMENTED | PROFILE |
| R130-0116 | `S#/candidate_ledger/115` | IMPLEMENTED | PROFILE |
| R130-0117 | `S#/candidate_ledger/116` | IMPLEMENTED | PROFILE |
| R130-0118 | `S#/candidate_ledger/117` | IMPLEMENTED | GATT |
| R130-0119 | `S#/candidate_ledger/118` | IMPLEMENTED | GATT |
| R130-0120 | `S#/candidate_ledger/119` | IMPLEMENTED | GATT |
| R130-0121 | `S#/candidate_ledger/120` | IMPLEMENTED | GATT |
| R130-0122 | `S#/candidate_ledger/121` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uncalled helper/overload; reverse search retained in followup-reachability. |
| R130-0123 | `S#/candidate_ledger/122` | IMPLEMENTED | GATT |
| R130-0124 | `S#/candidate_ledger/123` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uncalled helper/overload; reverse search retained in followup-reachability. |
| R130-0125 | `S#/candidate_ledger/124` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uncalled helper/overload; reverse search retained in followup-reachability. |
| R130-0126 | `S#/candidate_ledger/125` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uncalled helper/overload; reverse search retained in followup-reachability. |
| R130-0127 | `S#/candidate_ledger/126` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uncalled helper/overload; reverse search retained in followup-reachability. |
| R130-0128 | `S#/candidate_ledger/127` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uncalled helper/overload; reverse search retained in followup-reachability. |
| R130-0129 | `S#/candidate_ledger/128` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uncalled helper/overload; reverse search retained in followup-reachability. |
| R130-0130 | `S#/candidate_ledger/129` | IMPLEMENTED | GATT |
| R130-0131 | `S#/candidate_ledger/130` | IMPLEMENTED | GATT |
| R130-0132 | `S#/candidate_ledger/131` | IMPLEMENTED | GATT |
| R130-0133 | `S#/candidate_ledger/132` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uncalled helper/overload; reverse search retained in followup-reachability. |
| R130-0134 | `S#/candidate_ledger/133` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uncalled helper/overload; reverse search retained in followup-reachability. |
| R130-0135 | `S#/candidate_ledger/134` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uncalled helper/overload; reverse search retained in followup-reachability. |
| R130-0136 | `S#/candidate_ledger/135` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uncalled helper/overload; reverse search retained in followup-reachability. |
| R130-0137 | `S#/candidate_ledger/136` | IMPLEMENTED | GATT |
| R130-0138 | `S#/candidate_ledger/137` | IMPLEMENTED | GATT |
| R130-0139 | `S#/candidate_ledger/138` | IMPLEMENTED | GATT |
| R130-0140 | `S#/candidate_ledger/139` | IMPLEMENTED | GATT |
| R130-0141 | `S#/candidate_ledger/140` | IMPLEMENTED | GATT |
| R130-0142 | `S#/candidate_ledger/141` | IMPLEMENTED | GATT |
| R130-0143 | `S#/candidate_ledger/142` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uncalled helper/overload; reverse search retained in followup-reachability. |
| R130-0144 | `S#/candidate_ledger/143` | IMPLEMENTED | DISCOVERY |
| R130-0145 | `S#/candidate_ledger/144` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uninstantiated callback scaffold; no connection callsite. |
| R130-0146 | `S#/candidate_ledger/145` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uninstantiated callback scaffold; no connection callsite. |
| R130-0147 | `S#/candidate_ledger/146` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uninstantiated callback scaffold; no connection callsite. |
| R130-0148 | `S#/candidate_ledger/147` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uninstantiated callback scaffold; no connection callsite. |
| R130-0149 | `S#/candidate_ledger/148` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: Uninstantiated callback scaffold; no connection callsite. |
| R130-0150 | `S#/candidate_ledger/149` | IMPLEMENTED | DISCOVERY |
| R130-0151 | `S#/candidate_ledger/150` | IMPLEMENTED | DISCOVERY |
| R130-0152 | `S#/candidate_ledger/151` | IMPLEMENTED | DISCOVERY |
| R130-0153 | `S#/candidate_ledger/152` | EXCLUDED | Phone alarm/audio/browser/pager/logging/build identity is unrelated to BLE bed control. All discovery, selection, persistence or packet effects in the same app remain separately in scope. Local-file I/O; not Bluetooth. |
| R130-0154 | `S#/candidate_ledger/153` | EXCLUDED | Phone alarm/audio/browser/pager/logging/build identity is unrelated to BLE bed control. All discovery, selection, persistence or packet effects in the same app remain separately in scope. Local-file I/O; not Bluetooth. |
| R130-0155 | `S#/candidate_ledger/154` | IMPLEMENTED | DISCOVERY |
| R130-0156 | `S#/candidate_ledger/155` | IMPLEMENTED | DISCOVERY |
| R130-0157 | `S#/candidate_ledger/156` | IMPLEMENTED | DISCOVERY |
| R130-0158 | `S#/candidate_ledger/157` | IMPLEMENTED | DISCOVERY |
| R130-0159 | `S#/candidate_ledger/158` | EXCLUDED | Phone alarm/audio/browser/pager/logging/build identity is unrelated to BLE bed control. All discovery, selection, persistence or packet effects in the same app remain separately in scope. Local-file I/O. |
| R130-0160 | `S#/candidate_ledger/159` | EXCLUDED | Phone alarm/audio/browser/pager/logging/build identity is unrelated to BLE bed control. All discovery, selection, persistence or packet effects in the same app remain separately in scope. Local-file I/O; not Bluetooth. |
| R130-0161 | `S#/candidate_ledger/160` | EXCLUDED | Phone alarm/audio/browser/pager/logging/build identity is unrelated to BLE bed control. All discovery, selection, persistence or packet effects in the same app remain separately in scope. Local-file I/O; not Bluetooth. |
| R130-0162 | `S#/candidate_ledger/161` | IMPLEMENTED | DISCOVERY |
| R130-0163 | `S#/candidate_ledger/162` | IMPLEMENTED | DISCOVERY |
| R130-0164 | `S#/candidate_ledger/163` | EXCLUDED | Phone alarm/audio/browser/pager/logging/build identity is unrelated to BLE bed control. All discovery, selection, persistence or packet effects in the same app remain separately in scope. UI/local diagnostics/alarm/identity helper, no separate protocol. Only discovery/selection caller effects retained. |
| R130-0165 | `S#/candidate_ledger/164` | IMPLEMENTED | PROFILE |
| R130-0166 | `S#/candidate_ledger/165` | EXCLUDED | Phone alarm/audio/browser/pager/logging/build identity is unrelated to BLE bed control. All discovery, selection, persistence or packet effects in the same app remain separately in scope. UI/local diagnostics/alarm/identity helper, no separate protocol. Only discovery/selection caller effects retained. |
| R130-0167 | `S#/candidate_ledger/166` | IMPLEMENTED | MEMORY |
| R130-0168 | `S#/candidate_ledger/167` | EXCLUDED | Phone alarm/audio/browser/pager/logging/build identity is unrelated to BLE bed control. All discovery, selection, persistence or packet effects in the same app remain separately in scope. UI/local diagnostics/alarm/identity helper, no separate protocol. Only discovery/selection caller effects retained. |
| R130-0169 | `S#/candidate_ledger/168` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: No constructor/caller to live action; unused/stub candidate. |
| R130-0170 | `S#/candidate_ledger/169` | IMPLEMENTED | PROFILE |
| R130-0171 | `S#/candidate_ledger/170` | IMPLEMENTED | PROFILE |
| R130-0172 | `S#/candidate_ledger/171` | EXCLUDED | Phone alarm/audio/browser/pager/logging/build identity is unrelated to BLE bed control. All discovery, selection, persistence or packet effects in the same app remain separately in scope. UI/local diagnostics/alarm/identity helper, no separate protocol. Only discovery/selection caller effects retained. |
| R130-0173 | `S#/candidate_ledger/172` | IMPLEMENTED | PROFILE |
| R130-0174 | `S#/candidate_ledger/173` | EXCLUDED | Phone alarm/audio/browser/pager/logging/build identity is unrelated to BLE bed control. All discovery, selection, persistence or packet effects in the same app remain separately in scope. UI/local diagnostics/alarm/identity helper, no separate protocol. Only discovery/selection caller effects retained. |
| R130-0175 | `S#/candidate_ledger/174` | EXCLUDED | Phone alarm/audio/browser/pager/logging/build identity is unrelated to BLE bed control. All discovery, selection, persistence or packet effects in the same app remain separately in scope. UI/local diagnostics/alarm/identity helper, no separate protocol. Only discovery/selection caller effects retained. |
| R130-0176 | `S#/candidate_ledger/175` | IMPLEMENTED | PROFILE |
| R130-0177 | `S#/candidate_ledger/176` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned live class; reviewed caller/resource linkage. |
| R130-0178 | `S#/candidate_ledger/177` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned live class; reviewed caller/resource linkage. |
| R130-0179 | `S#/candidate_ledger/178` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned live class; reviewed caller/resource linkage. |
| R130-0180 | `S#/candidate_ledger/179` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned live class; reviewed caller/resource linkage. |
| R130-0181 | `S#/candidate_ledger/180` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned live class; reviewed caller/resource linkage. |
| R130-0182 | `S#/candidate_ledger/181` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. App-owned live class; reviewed caller/resource linkage. |
| R130-0183 | `S#/candidate_ledger/182` | IMPLEMENTED | PROFILE |
| R130-0184 | `S#/candidate_ledger/183` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: No constructor/caller to live action; unused/stub candidate. |
| R130-0185 | `S#/candidate_ledger/184` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: No constructor/caller to live action; unused/stub candidate. |
| R130-0186 | `S#/candidate_ledger/185` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: No constructor/caller to live action; unused/stub candidate. |
| R130-0187 | `S#/candidate_ledger/186` | IMPLEMENTED | PROFILE |
| R130-0188 | `S#/candidate_ledger/187` | EXCLUDED | Phone alarm/audio/browser/pager/logging/build identity is unrelated to BLE bed control. All discovery, selection, persistence or packet effects in the same app remain separately in scope. UI/local diagnostics/alarm/identity helper, no separate protocol. Only discovery/selection caller effects retained. |
| R130-0189 | `S#/candidate_ledger/188` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact artifact reason: No constructor/caller to live action; unused/stub candidate. |
| R130-0190 | `S#/candidate_ledger/189` | IMPLEMENTED | PROFILE |
| R130-0191 | `S#/candidate_ledger/190` | IMPLEMENTED | PROFILE |
| R130-0192 | `S#/candidate_ledger/191` | IMPLEMENTED | PROFILE |
| R130-0193 | `S#/candidate_ledger/192` | IMPLEMENTED | PROFILE |
| R130-0194 | `S#/candidate_ledger/193` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. App DFU service/UI only; boot/reconnect boundary covered. |
| R130-0195 | `S#/candidate_ledger/194` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. App DFU service/UI only; boot/reconnect boundary covered. |
| R130-0196 | `S#/candidate_ledger/195` | IMPLEMENTED | PROFILE |
| R130-0197 | `S#/candidate_ledger/196` | EXCLUDED | Phone alarm/audio/browser/pager/logging/build identity is unrelated to BLE bed control. All discovery, selection, persistence or packet effects in the same app remain separately in scope. UI/local diagnostics/alarm/identity helper, no separate protocol. Only discovery/selection caller effects retained. |
| R130-0198 | `S#/candidate_ledger/197` | IMPLEMENTED | MEMORY |
| R130-0199 | `S#/candidate_ledger/198` | IMPLEMENTED | PROFILE |
| R130-0200 | `S#/candidate_ledger/199` | IMPLEMENTED | MOTOR |
| R130-0201 | `S#/candidate_ledger/200` | IMPLEMENTED | PROFILE |
| R130-0202 | `S#/candidate_ledger/201` | EXCLUDED | Phone alarm/audio/browser/pager/logging/build identity is unrelated to BLE bed control. All discovery, selection, persistence or packet effects in the same app remain separately in scope. UI/local diagnostics/alarm/identity helper, no separate protocol. Only discovery/selection caller effects retained. |
| R130-0203 | `S#/candidate_ledger/202` | EXCLUDED | Phone alarm/audio/browser/pager/logging/build identity is unrelated to BLE bed control. All discovery, selection, persistence or packet effects in the same app remain separately in scope. UI/local diagnostics/alarm/identity helper, no separate protocol. Only discovery/selection caller effects retained. |
| R130-0204 | `S#/variant_inventory/0` | IMPLEMENTED | DISCOVERY |
| R130-0205 | `S#/variant_inventory/1` | IMPLEMENTED | DISCOVERY |
| R130-0206 | `S#/variant_inventory/2` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. Exact selector: Legacy user-selected screen; Classic single mode |
| R130-0207 | `S#/variant_inventory/3` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. Exact selector: Legacy user-selected screen; Classic dual mode |
| R130-0208 | `S#/variant_inventory/4` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact selector: No constructor call |
| R130-0209 | `S#/variant_inventory/5` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact selector: No constructor call; empty stub |
| R130-0210 | `S#/variant_inventory/6` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact selector: No constructor call; empty stub |
| R130-0211 | `S#/variant_inventory/7` | IMPLEMENTED | DISCOVERY |
| R130-0212 | `S#/variant_inventory/8` | IMPLEMENTED | DISCOVERY |
| R130-0213 | `S#/variant_inventory/9` | IMPLEMENTED | DISCOVERY |
| R130-0214 | `S#/variant_inventory/10` | IMPLEMENTED | DISCOVERY |
| R130-0215 | `S#/variant_inventory/11` | IMPLEMENTED | DISCOVERY |
| R130-0216 | `S#/variant_inventory/12` | IMPLEMENTED | DISCOVERY |
| R130-0217 | `S#/variant_inventory/13` | IMPLEMENTED | DISCOVERY |
| R130-0218 | `S#/variant_inventory/14` | IMPLEMENTED | DISCOVERY |
| R130-0219 | `S#/variant_inventory/15` | IMPLEMENTED | DISCOVERY |
| R130-0220 | `S#/variant_inventory/16` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact selector: Unused handleCommand branch: hardware 16.0 -> rev16_5 firmware |
| R130-0221 | `S#/variant_inventory/17` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact selector: Unused handleCommand branch: hardware 16.1 -> rev16_11 firmware |
| R130-0222 | `S#/variant_inventory/18` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact selector: Live firmware string comparison -> offer LinOnPro1_0RC18.zip; no control-protocol switch |
| R130-0223 | `S#/variant_inventory/19` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact selector: DfuServiceProvider GATT compatibility ButtonlessDfuWithBondSharingImpl |
| R130-0224 | `S#/variant_inventory/20` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact selector: DfuServiceProvider GATT compatibility ButtonlessDfuWithoutBondSharingImpl |
| R130-0225 | `S#/variant_inventory/21` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact selector: DfuServiceProvider GATT compatibility SecureDfuImpl |
| R130-0226 | `S#/variant_inventory/22` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact selector: DfuServiceProvider GATT compatibility LegacyButtonlessDfuImpl |
| R130-0227 | `S#/variant_inventory/23` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact selector: DfuServiceProvider GATT compatibility LegacyDfuImpl |
| R130-0228 | `S#/variant_inventory/24` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact selector: DfuServiceProvider GATT compatibility ExperimentalButtonlessDfuImpl |
| R130-0229 | `S#/firmware_inventory/0` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact archive/member: LinONPI_rev16_11.zip/LinONPI_rev16_11.bin |
| R130-0230 | `S#/firmware_inventory/1` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact archive/member: LinONPI_rev16_11.zip/LinONPI_rev16_11.dat |
| R130-0231 | `S#/firmware_inventory/2` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact archive/member: LinONPI_rev16_11.zip/manifest.json |
| R130-0232 | `S#/firmware_inventory/3` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact archive/member: LinONPI_rev16_5.zip/LinONPI_rev16_5.bin |
| R130-0233 | `S#/firmware_inventory/4` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact archive/member: LinONPI_rev16_5.zip/LinONPI_rev16_5.dat |
| R130-0234 | `S#/firmware_inventory/5` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact archive/member: LinONPI_rev16_5.zip/manifest.json |
| R130-0235 | `S#/firmware_inventory/6` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact archive/member: LinOnPro10RC8adj.zip/LinOn_Pro.bin |
| R130-0236 | `S#/firmware_inventory/7` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact archive/member: LinOnPro10RC8adj.zip/LinOn_Pro.dat |
| R130-0237 | `S#/firmware_inventory/8` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact archive/member: LinOnPro10RC8adj.zip/manifest.json |
| R130-0238 | `S#/firmware_inventory/9` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact archive/member: LinOnPro10RC8adjb.zip/LinOn_Pro.bin |
| R130-0239 | `S#/firmware_inventory/10` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact archive/member: LinOnPro10RC8adjb.zip/LinOn_Pro.dat |
| R130-0240 | `S#/firmware_inventory/11` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact archive/member: LinOnPro10RC8adjb.zip/manifest.json |
| R130-0241 | `S#/firmware_inventory/12` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact archive/member: LinOnPro1_0RC10.zip/LinOn_Pro.bin |
| R130-0242 | `S#/firmware_inventory/13` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact archive/member: LinOnPro1_0RC10.zip/LinOn_Pro.dat |
| R130-0243 | `S#/firmware_inventory/14` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact archive/member: LinOnPro1_0RC10.zip/manifest.json |
| R130-0244 | `S#/firmware_inventory/15` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact archive/member: LinOnPro1_0RC18.zip/LinOn_Pro_RC18.bin |
| R130-0245 | `S#/firmware_inventory/16` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact archive/member: LinOnPro1_0RC18.zip/LinOn_Pro_RC18.dat |
| R130-0246 | `S#/firmware_inventory/17` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Exact archive/member: LinOnPro1_0RC18.zip/manifest.json |
| R130-0247 | `S#/protocols/0/id` | IMPLEMENTED | PROFILE |
| R130-0248 | `S#/protocols/0/reachability` | IMPLEMENTED | PROFILE |
| R130-0249 | `S#/protocols/0/selectors/0` | IMPLEMENTED | INIT |
| R130-0250 | `S#/protocols/0/discovery_rules/single_results` | IMPLEMENTED | DISCOVERY |
| R130-0251 | `S#/protocols/0/discovery_rules/batch_results` | IMPLEMENTED | DISCOVERY |
| R130-0252 | `S#/protocols/0/discovery_rules/service_uuid_filter` | IMPLEMENTED | DISCOVERY |
| R130-0253 | `S#/protocols/0/discovery_rules/service_uuid_filter_unknown_reason` | IMPLEMENTED | DISCOVERY |
| R130-0254 | `S#/protocols/0/discovery_rules/manufacturer_data` | IMPLEMENTED | INIT |
| R130-0255 | `S#/protocols/0/discovery_rules/manufacturer_data_unknown_reason` | IMPLEMENTED | INIT |
| R130-0256 | `S#/protocols/0/discovery_rules/reconnect` | IMPLEMENTED | DISCOVERY |
| R130-0257 | `S#/protocols/0/discovery_rules/evidence/0` | IMPLEMENTED | DISCOVERY |
| R130-0258 | `S#/protocols/0/gatt/roles/0/role` | IMPLEMENTED | GATT |
| R130-0259 | `S#/protocols/0/gatt/roles/0/service` | IMPLEMENTED | GATT |
| R130-0260 | `S#/protocols/0/gatt/roles/0/characteristic` | IMPLEMENTED | GATT |
| R130-0261 | `S#/protocols/0/gatt/roles/1/role` | IMPLEMENTED | GATT |
| R130-0262 | `S#/protocols/0/gatt/roles/1/service` | IMPLEMENTED | GATT |
| R130-0263 | `S#/protocols/0/gatt/roles/1/characteristic` | IMPLEMENTED | GATT |
| R130-0264 | `S#/protocols/0/gatt/roles/2/role` | IMPLEMENTED | GATT |
| R130-0265 | `S#/protocols/0/gatt/roles/2/service` | IMPLEMENTED | GATT |
| R130-0266 | `S#/protocols/0/gatt/roles/2/characteristic` | IMPLEMENTED | GATT |
| R130-0267 | `S#/protocols/0/gatt/roles/3/role` | IMPLEMENTED | GATT |
| R130-0268 | `S#/protocols/0/gatt/roles/3/service` | IMPLEMENTED | GATT |
| R130-0269 | `S#/protocols/0/gatt/roles/3/characteristic` | IMPLEMENTED | GATT |
| R130-0270 | `S#/protocols/0/gatt/roles/4/role` | IMPLEMENTED | RAW |
| R130-0271 | `S#/protocols/0/gatt/roles/4/service` | IMPLEMENTED | GATT |
| R130-0272 | `S#/protocols/0/gatt/roles/4/characteristic` | IMPLEMENTED | GATT |
| R130-0273 | `S#/protocols/0/gatt/roles/5/role` | IMPLEMENTED | RAW |
| R130-0274 | `S#/protocols/0/gatt/roles/5/service` | IMPLEMENTED | GATT |
| R130-0275 | `S#/protocols/0/gatt/roles/5/characteristic` | IMPLEMENTED | GATT |
| R130-0276 | `S#/protocols/0/gatt/roles/6/role` | IMPLEMENTED | GATT |
| R130-0277 | `S#/protocols/0/gatt/roles/6/service` | IMPLEMENTED | GATT |
| R130-0278 | `S#/protocols/0/gatt/roles/6/characteristic` | IMPLEMENTED | GATT |
| R130-0279 | `S#/protocols/0/gatt/roles/7/role` | IMPLEMENTED | LIGHT |
| R130-0280 | `S#/protocols/0/gatt/roles/7/service` | IMPLEMENTED | GATT |
| R130-0281 | `S#/protocols/0/gatt/roles/7/characteristic` | IMPLEMENTED | GATT |
| R130-0282 | `S#/protocols/0/gatt/roles/8/role` | IMPLEMENTED | LIGHT |
| R130-0283 | `S#/protocols/0/gatt/roles/8/service` | IMPLEMENTED | GATT |
| R130-0284 | `S#/protocols/0/gatt/roles/8/characteristic` | IMPLEMENTED | GATT |
| R130-0285 | `S#/protocols/0/gatt/roles/9/role` | IMPLEMENTED | LIGHT |
| R130-0286 | `S#/protocols/0/gatt/roles/9/service` | IMPLEMENTED | GATT |
| R130-0287 | `S#/protocols/0/gatt/roles/9/characteristic` | IMPLEMENTED | GATT |
| R130-0288 | `S#/protocols/0/gatt/roles/10/role` | IMPLEMENTED | GATT |
| R130-0289 | `S#/protocols/0/gatt/roles/10/service` | IMPLEMENTED | GATT |
| R130-0290 | `S#/protocols/0/gatt/roles/10/characteristic` | IMPLEMENTED | GATT |
| R130-0291 | `S#/protocols/0/gatt/roles/11/role` | IMPLEMENTED | GATT |
| R130-0292 | `S#/protocols/0/gatt/roles/11/service` | IMPLEMENTED | GATT |
| R130-0293 | `S#/protocols/0/gatt/roles/11/characteristic` | IMPLEMENTED | GATT |
| R130-0294 | `S#/protocols/0/gatt/roles/12/role` | IMPLEMENTED | GATT |
| R130-0295 | `S#/protocols/0/gatt/roles/12/service` | IMPLEMENTED | GATT |
| R130-0296 | `S#/protocols/0/gatt/roles/12/characteristic` | IMPLEMENTED | GATT |
| R130-0297 | `S#/protocols/0/gatt/roles/13/role` | IMPLEMENTED | GATT |
| R130-0298 | `S#/protocols/0/gatt/roles/13/service` | IMPLEMENTED | GATT |
| R130-0299 | `S#/protocols/0/gatt/roles/13/characteristic` | IMPLEMENTED | GATT |
| R130-0300 | `S#/protocols/0/gatt/uuid_selection` | IMPLEMENTED | DISCOVERY |
| R130-0301 | `S#/protocols/0/gatt/write_type` | IMPLEMENTED | GATT |
| R130-0302 | `S#/protocols/0/gatt/write_type_unknown_reason` | IMPLEMENTED | GATT |
| R130-0303 | `S#/protocols/0/gatt/write_properties_mask` | IMPLEMENTED | GATT |
| R130-0304 | `S#/protocols/0/gatt/cccd/descriptor` | IMPLEMENTED | INIT |
| R130-0305 | `S#/protocols/0/gatt/cccd/enable_bytes` | IMPLEMENTED | GATT |
| R130-0306 | `S#/protocols/0/gatt/cccd/disable_bytes` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. This literal false branch has no source caller. Host stop_notify cleanup remains required through the supported backend API. |
| R130-0307 | `S#/protocols/0/gatt/cccd/initial_target/service` | IMPLEMENTED | INIT |
| R130-0308 | `S#/protocols/0/gatt/cccd/initial_target/characteristic` | IMPLEMENTED | INIT |
| R130-0309 | `S#/protocols/0/gatt/cccd/detail` | IMPLEMENTED | INIT |
| R130-0310 | `S#/protocols/0/gatt/mtu` | IMPLEMENTED | GATT |
| R130-0311 | `S#/protocols/0/gatt/mtu_unknown_reason` | IMPLEMENTED | GATT |
| R130-0312 | `S#/protocols/0/gatt/bonding` | IMPLEMENTED | INIT |
| R130-0313 | `S#/protocols/0/gatt/connection_priority` | IMPLEMENTED | GATT |
| R130-0314 | `S#/protocols/0/gatt/connection_priority_unknown_reason` | IMPLEMENTED | GATT |
| R130-0315 | `S#/protocols/0/gatt/read_preconditions` | IMPLEMENTED | RAW |
| R130-0316 | `S#/protocols/0/session_sequence/0` | IMPLEMENTED | INIT |
| R130-0317 | `S#/protocols/0/session_sequence/1` | IMPLEMENTED | INIT |
| R130-0318 | `S#/protocols/0/session_sequence/2` | IMPLEMENTED | INIT |
| R130-0319 | `S#/protocols/0/session_sequence/3` | IMPLEMENTED | INIT |
| R130-0320 | `S#/protocols/0/session_sequence/4` | IMPLEMENTED | INIT |
| R130-0321 | `S#/protocols/0/session_sequence/5` | IMPLEMENTED | INIT |
| R130-0322 | `S#/protocols/0/packet_format/movement/length` | IMPLEMENTED | GATT |
| R130-0323 | `S#/protocols/0/packet_format/movement/bytes` | IMPLEMENTED | RELEASE |
| R130-0324 | `S#/protocols/0/packet_format/preset/length` | IMPLEMENTED | GATT |
| R130-0325 | `S#/protocols/0/packet_format/preset/bytes` | IMPLEMENTED | MEMORY |
| R130-0326 | `S#/protocols/0/packet_format/memory/length` | IMPLEMENTED | MEMORY |
| R130-0327 | `S#/protocols/0/packet_format/memory/bytes` | IMPLEMENTED | MEMORY |
| R130-0328 | `S#/protocols/0/packet_format/light/length` | IMPLEMENTED | LIGHT |
| R130-0329 | `S#/protocols/0/packet_format/light/offsets/0` | IMPLEMENTED | LIGHT |
| R130-0330 | `S#/protocols/0/packet_format/light/offsets/1` | IMPLEMENTED | LIGHT |
| R130-0331 | `S#/protocols/0/packet_format/light/offsets/2` | IMPLEMENTED | LIGHT |
| R130-0332 | `S#/protocols/0/packet_format/light/offsets/3` | IMPLEMENTED | LIGHT |
| R130-0333 | `S#/protocols/0/packet_format/light/offsets/4` | IMPLEMENTED | LIGHT |
| R130-0334 | `S#/protocols/0/packet_format/light/offsets/5` | IMPLEMENTED | LIGHT |
| R130-0335 | `S#/protocols/0/packet_format/auxiliary/length` | IMPLEMENTED | GATT |
| R130-0336 | `S#/protocols/0/packet_format/auxiliary/software` | IMPLEMENTED | GATT |
| R130-0337 | `S#/protocols/0/packet_format/auxiliary/boot` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. |
| R130-0338 | `S#/protocols/0/packet_format/checksum` | IMPLEMENTED | GATT |
| R130-0339 | `S#/protocols/0/packet_format/encryption` | IMPLEMENTED | GATT |
| R130-0340 | `S#/protocols/0/packet_format/byte_order` | IMPLEMENTED | RAW |
| R130-0341 | `S#/protocols/0/packet_format/fragmentation` | IMPLEMENTED | GATT |
| R130-0342 | `S#/protocols/0/packet_format/pseudocode` | IMPLEMENTED | LIGHT |
| R130-0343 | `S#/protocols/0/commands/0` | IMPLEMENTED | RELEASE |
| R130-0344 | `S#/protocols/0/commands/1` | IMPLEMENTED | RELEASE |
| R130-0345 | `S#/protocols/0/commands/2` | IMPLEMENTED | RELEASE |
| R130-0346 | `S#/protocols/0/commands/3` | IMPLEMENTED | RELEASE |
| R130-0347 | `S#/protocols/0/commands/4` | IMPLEMENTED | RELEASE |
| R130-0348 | `S#/protocols/0/commands/5` | IMPLEMENTED | RELEASE |
| R130-0349 | `S#/protocols/0/commands/6` | IMPLEMENTED | RELEASE |
| R130-0350 | `S#/protocols/0/commands/7` | IMPLEMENTED | RELEASE |
| R130-0351 | `S#/protocols/0/commands/8` | IMPLEMENTED | LIGHT |
| R130-0352 | `S#/protocols/0/commands/9` | IMPLEMENTED | LIGHT |
| R130-0353 | `S#/protocols/0/commands/10` | IMPLEMENTED | LIGHT |
| R130-0354 | `S#/protocols/0/commands/11` | IMPLEMENTED | LIGHT |
| R130-0355 | `S#/protocols/0/commands/12` | IMPLEMENTED | MEMORY |
| R130-0356 | `S#/protocols/0/commands/13` | IMPLEMENTED | MEMORY |
| R130-0357 | `S#/protocols/0/commands/14` | IMPLEMENTED | MEMORY |
| R130-0358 | `S#/protocols/0/commands/15` | IMPLEMENTED | MEMORY |
| R130-0359 | `S#/protocols/0/commands/16` | IMPLEMENTED | MEMORY |
| R130-0360 | `S#/protocols/0/commands/17` | IMPLEMENTED | RELEASE |
| R130-0361 | `S#/protocols/0/commands/18` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Normal firmware metadata reads remain separate IMPLEMENTED command rows. |
| R130-0362 | `S#/protocols/0/commands/19` | IMPLEMENTED | RELEASE |
| R130-0363 | `S#/protocols/0/commands/20` | IMPLEMENTED | RELEASE |
| R130-0364 | `S#/protocols/0/commands/21` | IMPLEMENTED | RELEASE |
| R130-0365 | `S#/protocols/0/commands/22` | IMPLEMENTED | MEMORY |
| R130-0366 | `S#/protocols/0/notifications/0` | IMPLEMENTED | MEMORY |
| R130-0367 | `S#/protocols/0/notifications/1` | IMPLEMENTED | MEMORY |
| R130-0368 | `S#/protocols/0/notifications/2` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Normal firmware metadata reads remain separate IMPLEMENTED command rows. |
| R130-0369 | `S#/protocols/0/capabilities/physical_motor_mapping` | IMPLEMENTED | MOTOR |
| R130-0370 | `S#/protocols/0/capabilities/motor_count` | IMPLEMENTED | MOTOR |
| R130-0371 | `S#/protocols/0/capabilities/motor_count_unknown_reason` | IMPLEMENTED | MOTOR |
| R130-0372 | `S#/protocols/0/capabilities/memory_slots` | IMPLEMENTED | MEMORY |
| R130-0373 | `S#/protocols/0/capabilities/memory_kind` | IMPLEMENTED | MEMORY |
| R130-0374 | `S#/protocols/0/capabilities/presets/0` | IMPLEMENTED | PROFILE |
| R130-0375 | `S#/protocols/0/capabilities/presets/1` | IMPLEMENTED | PROFILE |
| R130-0376 | `S#/protocols/0/capabilities/presets/2` | IMPLEMENTED | RAW |
| R130-0377 | `S#/protocols/0/capabilities/other_presets` | IMPLEMENTED | PROFILE |
| R130-0378 | `S#/protocols/0/capabilities/other_presets_unknown_reason` | IMPLEMENTED | PROFILE |
| R130-0379 | `S#/protocols/0/capabilities/lights/on_off` | IMPLEMENTED | LIGHT |
| R130-0380 | `S#/protocols/0/capabilities/lights/brightness` | IMPLEMENTED | LIGHT |
| R130-0381 | `S#/protocols/0/capabilities/lights/rgb` | IMPLEMENTED | LIGHT |
| R130-0382 | `S#/protocols/0/capabilities/lights/rgb_unknown_reason` | IMPLEMENTED | LIGHT |
| R130-0383 | `S#/protocols/0/capabilities/massage` | IMPLEMENTED | PROFILE |
| R130-0384 | `S#/protocols/0/capabilities/massage_unknown_reason` | IMPLEMENTED | PROFILE |
| R130-0385 | `S#/protocols/0/capabilities/authentication` | IMPLEMENTED | PROFILE |
| R130-0386 | `S#/protocols/0/capabilities/authentication_unknown_reason` | IMPLEMENTED | PROFILE |
| R130-0387 | `S#/protocols/0/capabilities/capability_query` | IMPLEMENTED | PROFILE |
| R130-0388 | `S#/protocols/0/capabilities/capability_query_unknown_reason` | IMPLEMENTED | RELEASE |
| R130-0389 | `S#/protocols/0/capabilities/remote_codes` | IMPLEMENTED | PROFILE |
| R130-0390 | `S#/protocols/0/capabilities/remote_codes_unknown_reason` | IMPLEMENTED | PROFILE |
| R130-0391 | `S#/protocols/0/capabilities/eeprom_settings` | IMPLEMENTED | PROFILE |
| R130-0392 | `S#/protocols/0/capabilities/eeprom_settings_unknown_reason` | IMPLEMENTED | PROFILE |
| R130-0393 | `S#/protocols/0/capabilities/split_behavior` | IMPLEMENTED | PROFILE |
| R130-0394 | `S#/protocols/0/capabilities/positions/encoding` | IMPLEMENTED | RAW |
| R130-0395 | `S#/protocols/0/capabilities/positions/units` | IMPLEMENTED | RAW |
| R130-0396 | `S#/protocols/0/capabilities/positions/units_unknown_reason` | IMPLEMENTED | INIT |
| R130-0397 | `S#/protocols/0/capabilities/evidence/0` | IMPLEMENTED | PROFILE |
| R130-0398 | `S#/protocols/0/capabilities/evidence/1` | IMPLEMENTED | MEMORY |
| R130-0399 | `S#/protocols/0/capabilities/evidence/2` | IMPLEMENTED | LIGHT |
| R130-0400 | `S#/protocols/0/capabilities/evidence/3` | IMPLEMENTED | PROFILE |
| R130-0401 | `S#/protocols/0/capabilities/evidence/4` | IMPLEMENTED | PROFILE |
| R130-0402 | `S#/protocols/0/model_mappings/0` | IMPLEMENTED | DISCOVERY |
| R130-0403 | `S#/protocols/0/model_mappings/1` | IMPLEMENTED | DISCOVERY |
| R130-0404 | `S#/protocols/0/timing/motor/initial_delay_ms` | IMPLEMENTED | INIT |
| R130-0405 | `S#/protocols/0/timing/motor/scheduled_repeat_ms` | IMPLEMENTED | MOTOR |
| R130-0406 | `S#/protocols/0/timing/motor/repeat_count` | IMPLEMENTED | MOTOR |
| R130-0407 | `S#/protocols/0/timing/motor/detail` | IMPLEMENTED | MOTOR |
| R130-0408 | `S#/protocols/0/timing/light/tap_threshold_ms` | IMPLEMENTED | LIGHT |
| R130-0409 | `S#/protocols/0/timing/light/initial_delay_ms` | IMPLEMENTED | LIGHT |
| R130-0410 | `S#/protocols/0/timing/light/scheduled_repeat_ms` | IMPLEMENTED | LIGHT |
| R130-0411 | `S#/protocols/0/timing/light/repeat_count` | IMPLEMENTED | LIGHT |
| R130-0412 | `S#/protocols/0/timing/light/detail` | IMPLEMENTED | LIGHT |
| R130-0413 | `S#/protocols/0/timing/scan_period_ms` | IMPLEMENTED | DISCOVERY |
| R130-0414 | `S#/protocols/0/timing/read_sequence_ms` | IMPLEMENTED | PROFILE |
| R130-0415 | `S#/protocols/0/timing/reconnect` | IMPLEMENTED | DISCOVERY |
| R130-0416 | `S#/protocols/0/timing/serialization` | IMPLEMENTED | PROFILE |
| R130-0417 | `S#/protocols/0/release_behavior/motor` | IMPLEMENTED | RELEASE |
| R130-0418 | `S#/protocols/0/release_behavior/light` | IMPLEMENTED | LIGHT |
| R130-0419 | `S#/protocols/0/release_behavior/preset_memory` | IMPLEMENTED | MEMORY |
| R130-0420 | `S#/protocols/0/release_behavior/lifecycle` | EXCLUDED | Exclude the exact unsafe app behavior described in this row; retain valid packets, ordering and destinations. Host operations must serialize, clean up on cancellation, reject malformed input and isolate physical targets without inventing a command or hardware state. Android pause closes the link without guaranteed STOP and leaves timers; host teardown must cancel and clean up started movement. |
| R130-0421 | `S#/protocols/0/evidence/0` | IMPLEMENTED | PROFILE |
| R130-0422 | `S#/protocols/0/evidence/1` | IMPLEMENTED | PROFILE |
| R130-0423 | `S#/protocols/0/evidence/2` | IMPLEMENTED | PROFILE |
| R130-0424 | `S#/protocols/0/evidence/3` | IMPLEMENTED | PROFILE |
| R130-0425 | `S#/protocols/0/evidence/4` | IMPLEMENTED | PROFILE |
| R130-0426 | `S#/protocols/0/evidence/5` | IMPLEMENTED | PROFILE |
| R130-0427 | `S#/protocols/0/evidence/6` | IMPLEMENTED | PROFILE |
| R130-0428 | `S#/protocols/0/evidence/7` | IMPLEMENTED | LIGHT |
| R130-0429 | `S#/protocols/0/evidence/8` | IMPLEMENTED | MEMORY |
| R130-0430 | `S#/protocols/0/evidence/9` | IMPLEMENTED | PROFILE |
| R130-0431 | `S#/protocols/0/notification_dispatch` | IMPLEMENTED | INIT |
| R130-0432 | `S#/protocols/1/id` | IMPLEMENTED | PROFILE |
| R130-0433 | `S#/protocols/1/reachability` | IMPLEMENTED | PROFILE |
| R130-0434 | `S#/protocols/1/selectors/0` | IMPLEMENTED | PROFILE |
| R130-0435 | `S#/protocols/1/discovery_rules/single_results` | IMPLEMENTED | DISCOVERY |
| R130-0436 | `S#/protocols/1/discovery_rules/batch_results` | IMPLEMENTED | DISCOVERY |
| R130-0437 | `S#/protocols/1/discovery_rules/service_uuid_filter` | IMPLEMENTED | DISCOVERY |
| R130-0438 | `S#/protocols/1/discovery_rules/service_uuid_filter_unknown_reason` | IMPLEMENTED | DISCOVERY |
| R130-0439 | `S#/protocols/1/discovery_rules/manufacturer_data` | IMPLEMENTED | INIT |
| R130-0440 | `S#/protocols/1/discovery_rules/manufacturer_data_unknown_reason` | IMPLEMENTED | INIT |
| R130-0441 | `S#/protocols/1/discovery_rules/reconnect` | IMPLEMENTED | DISCOVERY |
| R130-0442 | `S#/protocols/1/discovery_rules/evidence/0` | IMPLEMENTED | DISCOVERY |
| R130-0443 | `S#/protocols/1/gatt/roles/0/role` | IMPLEMENTED | RAW |
| R130-0444 | `S#/protocols/1/gatt/roles/0/service` | IMPLEMENTED | GATT |
| R130-0445 | `S#/protocols/1/gatt/roles/0/characteristic` | IMPLEMENTED | GATT |
| R130-0446 | `S#/protocols/1/gatt/roles/1/role` | IMPLEMENTED | GATT |
| R130-0447 | `S#/protocols/1/gatt/roles/1/service` | IMPLEMENTED | GATT |
| R130-0448 | `S#/protocols/1/gatt/roles/1/characteristic` | IMPLEMENTED | GATT |
| R130-0449 | `S#/protocols/1/gatt/roles/2/role` | IMPLEMENTED | GATT |
| R130-0450 | `S#/protocols/1/gatt/roles/2/service` | IMPLEMENTED | GATT |
| R130-0451 | `S#/protocols/1/gatt/roles/2/characteristic` | IMPLEMENTED | GATT |
| R130-0452 | `S#/protocols/1/gatt/roles/3/role` | IMPLEMENTED | GATT |
| R130-0453 | `S#/protocols/1/gatt/roles/3/service` | IMPLEMENTED | GATT |
| R130-0454 | `S#/protocols/1/gatt/roles/3/characteristic` | IMPLEMENTED | GATT |
| R130-0455 | `S#/protocols/1/gatt/roles/4/role` | IMPLEMENTED | GATT |
| R130-0456 | `S#/protocols/1/gatt/roles/4/service` | IMPLEMENTED | GATT |
| R130-0457 | `S#/protocols/1/gatt/roles/4/characteristic` | IMPLEMENTED | GATT |
| R130-0458 | `S#/protocols/1/gatt/uuid_selection` | IMPLEMENTED | DISCOVERY |
| R130-0459 | `S#/protocols/1/gatt/write_type` | IMPLEMENTED | GATT |
| R130-0460 | `S#/protocols/1/gatt/write_type_unknown_reason` | IMPLEMENTED | GATT |
| R130-0461 | `S#/protocols/1/gatt/write_properties_mask` | IMPLEMENTED | GATT |
| R130-0462 | `S#/protocols/1/gatt/cccd/descriptor` | IMPLEMENTED | INIT |
| R130-0463 | `S#/protocols/1/gatt/cccd/enable_bytes` | IMPLEMENTED | GATT |
| R130-0464 | `S#/protocols/1/gatt/cccd/disable_bytes` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. This literal false branch has no source caller. Host stop_notify cleanup remains required through the supported backend API. |
| R130-0465 | `S#/protocols/1/gatt/cccd/initial_target/service` | IMPLEMENTED | INIT |
| R130-0466 | `S#/protocols/1/gatt/cccd/initial_target/characteristic` | IMPLEMENTED | INIT |
| R130-0467 | `S#/protocols/1/gatt/cccd/detail` | IMPLEMENTED | INIT |
| R130-0468 | `S#/protocols/1/gatt/mtu` | IMPLEMENTED | GATT |
| R130-0469 | `S#/protocols/1/gatt/mtu_unknown_reason` | IMPLEMENTED | GATT |
| R130-0470 | `S#/protocols/1/gatt/bonding` | IMPLEMENTED | INIT |
| R130-0471 | `S#/protocols/1/gatt/connection_priority` | IMPLEMENTED | GATT |
| R130-0472 | `S#/protocols/1/gatt/connection_priority_unknown_reason` | IMPLEMENTED | GATT |
| R130-0473 | `S#/protocols/1/gatt/read_preconditions` | IMPLEMENTED | RAW |
| R130-0474 | `S#/protocols/1/session_sequence/0` | IMPLEMENTED | INIT |
| R130-0475 | `S#/protocols/1/session_sequence/1` | IMPLEMENTED | INIT |
| R130-0476 | `S#/protocols/1/session_sequence/2` | IMPLEMENTED | INIT |
| R130-0477 | `S#/protocols/1/session_sequence/3` | IMPLEMENTED | INIT |
| R130-0478 | `S#/protocols/1/session_sequence/4` | IMPLEMENTED | INIT |
| R130-0479 | `S#/protocols/1/session_sequence/5` | IMPLEMENTED | INIT |
| R130-0480 | `S#/protocols/1/packet_format/movement/length` | IMPLEMENTED | GATT |
| R130-0481 | `S#/protocols/1/packet_format/movement/bytes` | IMPLEMENTED | GATT |
| R130-0482 | `S#/protocols/1/packet_format/preset/length` | IMPLEMENTED | GATT |
| R130-0483 | `S#/protocols/1/packet_format/preset/bytes` | IMPLEMENTED | GATT |
| R130-0484 | `S#/protocols/1/packet_format/memory/length` | IMPLEMENTED | MEMORY |
| R130-0485 | `S#/protocols/1/packet_format/memory/bytes` | IMPLEMENTED | MEMORY |
| R130-0486 | `S#/protocols/1/packet_format/light/length` | IMPLEMENTED | LIGHT |
| R130-0487 | `S#/protocols/1/packet_format/light/offsets/0` | IMPLEMENTED | LIGHT |
| R130-0488 | `S#/protocols/1/packet_format/light/offsets/1` | IMPLEMENTED | LIGHT |
| R130-0489 | `S#/protocols/1/packet_format/light/offsets/2` | IMPLEMENTED | LIGHT |
| R130-0490 | `S#/protocols/1/packet_format/light/offsets/3` | IMPLEMENTED | LIGHT |
| R130-0491 | `S#/protocols/1/packet_format/light/offsets/4` | IMPLEMENTED | LIGHT |
| R130-0492 | `S#/protocols/1/packet_format/light/offsets/5` | IMPLEMENTED | LIGHT |
| R130-0493 | `S#/protocols/1/packet_format/auxiliary/length` | IMPLEMENTED | GATT |
| R130-0494 | `S#/protocols/1/packet_format/auxiliary/software` | IMPLEMENTED | GATT |
| R130-0495 | `S#/protocols/1/packet_format/auxiliary/boot` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. |
| R130-0496 | `S#/protocols/1/packet_format/checksum` | IMPLEMENTED | GATT |
| R130-0497 | `S#/protocols/1/packet_format/encryption` | IMPLEMENTED | GATT |
| R130-0498 | `S#/protocols/1/packet_format/byte_order` | IMPLEMENTED | RAW |
| R130-0499 | `S#/protocols/1/packet_format/fragmentation` | IMPLEMENTED | GATT |
| R130-0500 | `S#/protocols/1/packet_format/pseudocode` | IMPLEMENTED | LIGHT |
| R130-0501 | `S#/protocols/1/commands/0` | IMPLEMENTED | RELEASE |
| R130-0502 | `S#/protocols/1/commands/1` | IMPLEMENTED | RELEASE |
| R130-0503 | `S#/protocols/1/commands/2` | IMPLEMENTED | RELEASE |
| R130-0504 | `S#/protocols/1/commands/3` | IMPLEMENTED | RELEASE |
| R130-0505 | `S#/protocols/1/commands/4` | IMPLEMENTED | RELEASE |
| R130-0506 | `S#/protocols/1/commands/5` | IMPLEMENTED | RELEASE |
| R130-0507 | `S#/protocols/1/commands/6` | IMPLEMENTED | RELEASE |
| R130-0508 | `S#/protocols/1/commands/7` | IMPLEMENTED | RELEASE |
| R130-0509 | `S#/protocols/1/commands/8` | IMPLEMENTED | RELEASE |
| R130-0510 | `S#/protocols/1/commands/9` | IMPLEMENTED | LIGHT |
| R130-0511 | `S#/protocols/1/commands/10` | IMPLEMENTED | LIGHT |
| R130-0512 | `S#/protocols/1/commands/11` | IMPLEMENTED | LIGHT |
| R130-0513 | `S#/protocols/1/commands/12` | IMPLEMENTED | LIGHT |
| R130-0514 | `S#/protocols/1/commands/13` | IMPLEMENTED | MEMORY |
| R130-0515 | `S#/protocols/1/commands/14` | IMPLEMENTED | MEMORY |
| R130-0516 | `S#/protocols/1/commands/15` | IMPLEMENTED | MEMORY |
| R130-0517 | `S#/protocols/1/commands/16` | IMPLEMENTED | RELEASE |
| R130-0518 | `S#/protocols/1/commands/17` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Normal firmware metadata reads remain separate IMPLEMENTED command rows. |
| R130-0519 | `S#/protocols/1/commands/18` | IMPLEMENTED | RELEASE |
| R130-0520 | `S#/protocols/1/commands/19` | IMPLEMENTED | RELEASE |
| R130-0521 | `S#/protocols/1/commands/20` | IMPLEMENTED | RELEASE |
| R130-0522 | `S#/protocols/1/commands/21` | IMPLEMENTED | MEMORY |
| R130-0523 | `S#/protocols/1/notifications/0` | IMPLEMENTED | MEMORY |
| R130-0524 | `S#/protocols/1/notifications/1` | EXCLUDED | User-confirmed firmware boot/update, address mutation, firmware comparison/RC preference and Nordic DFU/bond helpers are destructive firmware-update scope. Exclude these operations and MCU internals; retain normal DIS reads and normal software query separately. Normal firmware metadata reads remain separate IMPLEMENTED command rows. |
| R130-0525 | `S#/protocols/1/capabilities/physical_motor_mapping` | IMPLEMENTED | MOTOR |
| R130-0526 | `S#/protocols/1/capabilities/motor_count` | IMPLEMENTED | MOTOR |
| R130-0527 | `S#/protocols/1/capabilities/motor_count_unknown_reason` | IMPLEMENTED | MOTOR |
| R130-0528 | `S#/protocols/1/capabilities/memory_slots` | IMPLEMENTED | MEMORY |
| R130-0529 | `S#/protocols/1/capabilities/memory_kind` | IMPLEMENTED | MEMORY |
| R130-0530 | `S#/protocols/1/capabilities/presets/0` | IMPLEMENTED | PROFILE |
| R130-0531 | `S#/protocols/1/capabilities/presets/1` | IMPLEMENTED | PROFILE |
| R130-0532 | `S#/protocols/1/capabilities/presets/2` | IMPLEMENTED | RAW |
| R130-0533 | `S#/protocols/1/capabilities/other_presets` | IMPLEMENTED | PROFILE |
| R130-0534 | `S#/protocols/1/capabilities/other_presets_unknown_reason` | IMPLEMENTED | PROFILE |
| R130-0535 | `S#/protocols/1/capabilities/lights/on_off` | IMPLEMENTED | LIGHT |
| R130-0536 | `S#/protocols/1/capabilities/lights/brightness` | IMPLEMENTED | LIGHT |
| R130-0537 | `S#/protocols/1/capabilities/lights/rgb` | IMPLEMENTED | LIGHT |
| R130-0538 | `S#/protocols/1/capabilities/lights/rgb_unknown_reason` | IMPLEMENTED | LIGHT |
| R130-0539 | `S#/protocols/1/capabilities/massage` | IMPLEMENTED | PROFILE |
| R130-0540 | `S#/protocols/1/capabilities/massage_unknown_reason` | IMPLEMENTED | PROFILE |
| R130-0541 | `S#/protocols/1/capabilities/authentication` | IMPLEMENTED | PROFILE |
| R130-0542 | `S#/protocols/1/capabilities/authentication_unknown_reason` | IMPLEMENTED | PROFILE |
| R130-0543 | `S#/protocols/1/capabilities/capability_query` | IMPLEMENTED | PROFILE |
| R130-0544 | `S#/protocols/1/capabilities/capability_query_unknown_reason` | IMPLEMENTED | RELEASE |
| R130-0545 | `S#/protocols/1/capabilities/remote_codes` | IMPLEMENTED | PROFILE |
| R130-0546 | `S#/protocols/1/capabilities/remote_codes_unknown_reason` | IMPLEMENTED | PROFILE |
| R130-0547 | `S#/protocols/1/capabilities/eeprom_settings` | IMPLEMENTED | PROFILE |
| R130-0548 | `S#/protocols/1/capabilities/eeprom_settings_unknown_reason` | IMPLEMENTED | PROFILE |
| R130-0549 | `S#/protocols/1/capabilities/split_behavior` | IMPLEMENTED | PROFILE |
| R130-0550 | `S#/protocols/1/capabilities/positions/encoding` | IMPLEMENTED | RAW |
| R130-0551 | `S#/protocols/1/capabilities/positions/units` | IMPLEMENTED | RAW |
| R130-0552 | `S#/protocols/1/capabilities/positions/units_unknown_reason` | IMPLEMENTED | INIT |
| R130-0553 | `S#/protocols/1/capabilities/evidence/0` | IMPLEMENTED | PROFILE |
| R130-0554 | `S#/protocols/1/capabilities/evidence/1` | IMPLEMENTED | MEMORY |
| R130-0555 | `S#/protocols/1/capabilities/evidence/2` | IMPLEMENTED | LIGHT |
| R130-0556 | `S#/protocols/1/capabilities/evidence/3` | IMPLEMENTED | PROFILE |
| R130-0557 | `S#/protocols/1/capabilities/evidence/4` | IMPLEMENTED | PROFILE |
| R130-0558 | `S#/protocols/1/model_mappings/0` | IMPLEMENTED | DISCOVERY |
| R130-0559 | `S#/protocols/1/model_mappings/1` | IMPLEMENTED | DISCOVERY |
| R130-0560 | `S#/protocols/1/timing/motor/initial_delay_ms` | IMPLEMENTED | INIT |
| R130-0561 | `S#/protocols/1/timing/motor/scheduled_repeat_ms` | IMPLEMENTED | MOTOR |
| R130-0562 | `S#/protocols/1/timing/motor/repeat_count` | IMPLEMENTED | MOTOR |
| R130-0563 | `S#/protocols/1/timing/motor/detail` | IMPLEMENTED | MOTOR |
| R130-0564 | `S#/protocols/1/timing/light/tap_threshold_ms` | IMPLEMENTED | LIGHT |
| R130-0565 | `S#/protocols/1/timing/light/initial_delay_ms` | IMPLEMENTED | LIGHT |
| R130-0566 | `S#/protocols/1/timing/light/scheduled_repeat_ms` | IMPLEMENTED | LIGHT |
| R130-0567 | `S#/protocols/1/timing/light/repeat_count` | IMPLEMENTED | LIGHT |
| R130-0568 | `S#/protocols/1/timing/light/detail` | IMPLEMENTED | LIGHT |
| R130-0569 | `S#/protocols/1/timing/scan_period_ms` | IMPLEMENTED | DISCOVERY |
| R130-0570 | `S#/protocols/1/timing/read_sequence_ms` | IMPLEMENTED | PROFILE |
| R130-0571 | `S#/protocols/1/timing/reconnect` | IMPLEMENTED | DISCOVERY |
| R130-0572 | `S#/protocols/1/timing/serialization` | IMPLEMENTED | PROFILE |
| R130-0573 | `S#/protocols/1/release_behavior/motor` | IMPLEMENTED | RELEASE |
| R130-0574 | `S#/protocols/1/release_behavior/light` | IMPLEMENTED | LIGHT |
| R130-0575 | `S#/protocols/1/release_behavior/preset_memory` | IMPLEMENTED | MEMORY |
| R130-0576 | `S#/protocols/1/release_behavior/lifecycle` | EXCLUDED | Exclude the exact unsafe app behavior described in this row; retain valid packets, ordering and destinations. Host operations must serialize, clean up on cancellation, reject malformed input and isolate physical targets without inventing a command or hardware state. Android pause closes the link without guaranteed STOP and leaves timers; host teardown must cancel and clean up started movement. |
| R130-0577 | `S#/protocols/1/evidence/0` | IMPLEMENTED | PROFILE |
| R130-0578 | `S#/protocols/1/evidence/1` | IMPLEMENTED | PROFILE |
| R130-0579 | `S#/protocols/1/evidence/2` | IMPLEMENTED | PROFILE |
| R130-0580 | `S#/protocols/1/evidence/3` | IMPLEMENTED | PROFILE |
| R130-0581 | `S#/protocols/1/evidence/4` | IMPLEMENTED | PROFILE |
| R130-0582 | `S#/protocols/1/evidence/5` | IMPLEMENTED | PROFILE |
| R130-0583 | `S#/protocols/1/evidence/6` | IMPLEMENTED | PROFILE |
| R130-0584 | `S#/protocols/1/evidence/7` | IMPLEMENTED | LIGHT |
| R130-0585 | `S#/protocols/1/evidence/8` | IMPLEMENTED | MEMORY |
| R130-0586 | `S#/protocols/1/evidence/9` | IMPLEMENTED | PROFILE |
| R130-0587 | `S#/protocols/1/notification_dispatch` | IMPLEMENTED | INIT |
| R130-0588 | `S#/protocols/2/id` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0589 | `S#/protocols/2/reachability` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0590 | `S#/protocols/2/live_reachability` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0591 | `S#/protocols/2/out_of_scope` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0592 | `S#/protocols/2/selectors/0` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0593 | `S#/protocols/2/discovery_rules/scan` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0594 | `S#/protocols/2/discovery_rules/service_uuid` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0595 | `S#/protocols/2/discovery_rules/evidence/0` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0596 | `S#/protocols/2/gatt` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0597 | `S#/protocols/2/gatt_unknown_reason` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0598 | `S#/protocols/2/session_sequence/0` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0599 | `S#/protocols/2/packet_format/length` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0600 | `S#/protocols/2/packet_format/bytes` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0601 | `S#/protocols/2/packet_format/offsets/0` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0602 | `S#/protocols/2/packet_format/offsets/1` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0603 | `S#/protocols/2/packet_format/offsets/2` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0604 | `S#/protocols/2/packet_format/offsets/3..6` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0605 | `S#/protocols/2/packet_format/offsets/7` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0606 | `S#/protocols/2/packet_format/checksum` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0607 | `S#/protocols/2/packet_format/encryption` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0608 | `S#/protocols/2/packet_format/pseudocode` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0609 | `S#/protocols/2/commands/0` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0610 | `S#/protocols/2/commands/1` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0611 | `S#/protocols/2/commands/2` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0612 | `S#/protocols/2/commands/3` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0613 | `S#/protocols/2/commands/4` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0614 | `S#/protocols/2/commands/5` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0615 | `S#/protocols/2/commands/6` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0616 | `S#/protocols/2/commands/7` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0617 | `S#/protocols/2/commands/8` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0618 | `S#/protocols/2/commands/9` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0619 | `S#/protocols/2/commands/10` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0620 | `S#/protocols/2/commands/11` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0621 | `S#/protocols/2/commands/12` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0622 | `S#/protocols/2/commands/13` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0623 | `S#/protocols/2/commands/14` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0624 | `S#/protocols/2/commands/15` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0625 | `S#/protocols/2/commands/16` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0626 | `S#/protocols/2/notifications/0` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0627 | `S#/protocols/2/capabilities/axes` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0628 | `S#/protocols/2/capabilities/preset_slots` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0629 | `S#/protocols/2/capabilities/light` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0630 | `S#/protocols/2/capabilities/coupling` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0631 | `S#/protocols/2/capabilities/evidence/0` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0632 | `S#/protocols/2/model_mappings/0` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0633 | `S#/protocols/2/timing/loop_delay_ms` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0634 | `S#/protocols/2/timing/queued_extra_delay_ms` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0635 | `S#/protocols/2/timing/answer_gate` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0636 | `S#/protocols/2/timing/save_program` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0637 | `S#/protocols/2/timing/radio_side_effect` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0638 | `S#/protocols/2/release_behavior/detail` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0639 | `S#/protocols/2/evidence/0` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0640 | `S#/protocols/2/evidence/1` | EXCLUDED | App-owned Classic RFCOMM socket/1101 and its framed key/queue transport are outside this BLE integration. The accepted artifact proves this route is user-selected, not BLE GATT. |
| R130-0641 | `S#/unused_command_candidates/LinonPIProtocol` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact dormant candidate group: LinonPIProtocol |
| R130-0642 | `S#/unused_command_candidates/OldProtocol` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact dormant candidate group: OldProtocol |
| R130-0643 | `S#/unused_command_candidates/NewProtocol~1BLEProtocol` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact dormant candidate group: NewProtocol/BLEProtocol |
| R130-0644 | `S#/unused_command_candidates/evidence` | EXCLUDED | Accepted reverse caller/constructor search proves this implementation/overload/constant has no reachable normal-control caller. Do not execute a firmware command merely because its literal exists. Exact dormant candidate group: evidence |
| R130-0645 | `S#/protocols/0/session_sequence/1` | EXCLUDED | Exclude the exact unsafe app behavior described in this row; retain valid packets, ordering and destinations. Host operations must serialize, clean up on cancellation, reject malformed input and isolate physical targets without inventing a command or hardware state. Do not use connected/RPC success as discovery/auth/bond proof; gate actual role availability. |
| R130-0646 | `S#/protocols/0/session_sequence/2` | EXCLUDED | Exclude the exact unsafe app behavior described in this row; retain valid packets, ordering and destinations. Host operations must serialize, clean up on cancellation, reject malformed input and isolate physical targets without inventing a command or hardware state. Missing optional source initialization role produces explicit unavailable diagnostic; never guess another characteristic. Present roles retain the exact source subscription/query path. |
| R130-0647 | `S#/protocols/0/session_sequence/2` | EXCLUDED | Exclude the exact unsafe app behavior described in this row; retain valid packets, ordering and destinations. Host operations must serialize, clean up on cancellation, reject malformed input and isolate physical targets without inventing a command or hardware state. Read metadata only for the addressed physical target; no cross-target metadata or identity inheritance. |
| R130-0648 | `S#/protocols/0/session_sequence/3` | EXCLUDED | Exclude the exact unsafe app behavior described in this row; retain valid packets, ordering and destinations. Host operations must serialize, clean up on cancellation, reject malformed input and isolate physical targets without inventing a command or hardware state. Use safe completed host subscription setup, not false subscription ACK or authentication. Preserve query bytes/destination and ordering on the valid path. |
| R130-0649 | `S#/protocols/0/session_sequence/4` | EXCLUDED | Exclude the exact unsafe app behavior described in this row; retain valid packets, ordering and destinations. Host operations must serialize, clean up on cancellation, reject malformed input and isolate physical targets without inventing a command or hardware state. Use per-target state and serialized GATT transactions while preserving source fixed read-pair order and read-only/missing-name preconditions. |
| R130-0650 | `S#/protocols/0/timing/serialization` | EXCLUDED | Exclude the exact unsafe app behavior described in this row; retain valid packets, ordering and destinations. Host operations must serialize, clean up on cancellation, reject malformed input and isolate physical targets without inventing a command or hardware state. Each physical target receives its own valid route; mixed paired targets must not starve a P1 side. |
| R130-0651 | `S#/protocols/0/release_behavior/motor` | EXCLUDED | Exclude the exact unsafe app behavior described in this row; retain valid packets, ordering and destinations. Host operations must serialize, clean up on cancellation, reject malformed input and isolate physical targets without inventing a command or hardware state. Release/cleanup all actually started axis/direction roles. Never substitute an undocumented global P1 byte or leave another active role moving. |
| R130-0652 | `S#/protocols/1/release_behavior/motor` | EXCLUDED | Exclude the exact unsafe app behavior described in this row; retain valid packets, ordering and destinations. Host operations must serialize, clean up on cancellation, reject malformed input and isolate physical targets without inventing a command or hardware state. Host cancel/release/unload always ends its own refresh; preserve P2 remaining-axis-mask behavior and final-stop packet. |
| R130-0653 | `S#/protocols/0/release_behavior/light` | EXCLUDED | Exclude the exact unsafe app behavior described in this row; retain valid packets, ordering and destinations. Host operations must serialize, clean up on cancellation, reject malformed input and isolate physical targets without inventing a command or hardware state. Stop brightness stream on host cancel/teardown without adding movement STOP or a lamp OFF packet. |
| R130-0654 | `S#/protocols/0/notifications/0` | EXCLUDED | Exclude the exact unsafe app behavior described in this row; retain valid packets, ordering and destinations. Host operations must serialize, clean up on cancellation, reject malformed input and isolate physical targets without inventing a command or hardware state. Scope opaque axis memory by exact physical MAC; synthetic empty fixture does not prove real broadcaster passes empty frames. |
| R130-0655 | `S#/protocols/1/notifications/0` | EXCLUDED | Exclude the exact unsafe app behavior described in this row; retain valid packets, ordering and destinations. Host operations must serialize, clean up on cancellation, reject malformed input and isolate physical targets without inventing a command or hardware state. Keep P2 cache and slots target-local; reject save without an observed valid four-byte target record. |
| R130-0656 | `S#/protocols/1/capabilities/memory_kind` | EXCLUDED | Exclude the exact unsafe app behavior described in this row; retain valid packets, ordering and destinations. Host operations must serialize, clean up on cancellation, reject malformed input and isolate physical targets without inventing a command or hardware state. Require a completed target-local four-byte cache before replacing a slot. Invalid persisted slot objects are explicit unavailable data or a documented safe default repair, not firmware programming or fabricated measured position. |
| R130-0657 | `S#/protocols/0/notification_dispatch` | EXCLUDED | Exclude the exact unsafe app behavior described in this row; retain valid packets, ordering and destinations. Host operations must serialize, clean up on cancellation, reject malformed input and isolate physical targets without inventing a command or hardware state. DIS precedence then exact axis roles and configured P2 response role; reject missing origin and insufficient length safely. Preserve valid raw projection, not guessed measured units. |
| R130-0658 | `S#/comparison/narrow_equivalence/P1 motion literal` | ALREADY_IMPLEMENTED | GATT |
| R130-0659 | `S#/comparison/narrow_equivalence/P1 direction release literal` | ALREADY_IMPLEMENTED | GATT |
| R130-0660 | `S#/comparison/narrow_equivalence/P1 top preset literal` | ALREADY_IMPLEMENTED | GATT |
| R130-0661 | `S#/comparison/narrow_equivalence/Lamp off literal` | ALREADY_IMPLEMENTED | GATT |
| R130-0662 | `S#/comparison/narrow_equivalence/P1 valid software raw replay` | ALREADY_IMPLEMENTED | MEMORY |
| R130-0663 | `S#/comparison/narrow_equivalence/P2 closed motion literal domain` | ALREADY_IMPLEMENTED | GATT |
