# S01: Serenity implementation disposition

**Implementation comparison: complete and independently accepted.** This is the post-freeze discovery/evidence ledger for Jordan’s Serenity. Physical hardware remains unverified.

## Accepted evidence identity

`S` denotes `com.okin.bedding.serenity` version 1.0.1, code 2, frozen run `com.okin.bedding.serenity-1.0.1-2026-09-30-isolated-002`. Each `S#/...` pointer identifies the immutable package-local `report/analysis.json` claim. Raw APKs, decompilation and reports remain machine-local.

| Evidence | SHA-256 |
| --- | --- |
| Complete four-member artifact set | `b0729dc3a4eae2644cc5035b984a05ac116a658b79c886ab1b02eebdea584cc6` |
| Report REPORT.SHA256 | `9f95495d46c2f4325b15c68ae126028c52300fd76b193807fc7550e76955648c` |
| Independent accepted AUDIT.SHA256 | `8553cc74a5893eeaaa70968071d5bda68c54928948043e3b8f890540a71a7ca0` |
| Pinned package schema | `f36eac2916cef415d51161eafc61fb6310fcd92327df02d65c3e8025a3dfd246` |

Exact report/audit manifest members, all four artifact members, schema and all 17 PASS gates were independently checked. The independent isolated audit accepts the FULL report with zero findings. Both frozen reproductions pass, including 1784 actual-smali packet comparisons. Nested preservation verification also checks 1886 reviewed files and all 11755 original input/output files against the accepted audit inventories. There is one reachable packet implementation and one fixed remote/massage screen pair. The seven inventory entries contain two reachable screen entries and five dead entries; they are not seven hardware models.

## Integration requirements and boundaries

The artifact transmits 14-byte `0c 02` frames with two big-endian 32-bit fields and four trailing zero bytes. It refreshes held commands at 100 ms and attempts two zero release frames at +100/+200 ms from one common release origin. The host schedules both nominal deadlines without adding the first write round-trip time to the second. Voice-only Anti-Snore, Leisure, three waves and discrete light on/off remain reachable controls. The remote’s selector-4 and selector-5 labels disagree with presenter method names; the integration must expose the exact selector routes without inferring physical motor count or remapping them from names. Generic head/foot paths and M1/M2 are separate from explicit selectors and named ZG/TV saves. Numbered and named save buttons follow the shipped five-second help gesture, with immediate frames and cancellable refresh; this does not establish a hardware time gate or storage acknowledgement.

The artifact inherits an unknown Android characteristic write type. HA may validate actual writable properties and choose a documented host write policy, without claiming an artifact ATT mode. Notifications are required independently of angle sensing. The parser accepts messages longer than ten bytes without header/checksum validation, preserves signed alarm/status fields and unknown alarm types, and distinguishes change-only status, pending local save success and timer state. A dead alarm UI does not make its reachable reply parser dead. Manufacturer data is display-only; reads must honor the information-service/read-property role and preserve an explicit refresh route.

Valid exclusions cover dead clock/alarm/query/adjustment builders, unattached legacy screens/helpers, Android scan/connector/speech/UI lifecycle and unsafe pointer or stale-callback replay. The voice “stop” branch erroneously starts head-up before a delayed stop; that movement is excluded for safety while protocol STOP remains retained. Arbitrary simultaneous motor masks are not inferred from the remote’s aggregate pointer bitset: unmatched switch cases emit no new command. Hardware acceptance, physical axis interpretation and save storage remain unverified.

## Ledger status

**169 discovery/evidence rows: 114 IMPLEMENTED, 2 ALREADY_IMPLEMENTED, 53 EXCLUDED.** Every in-scope item has exact current code/test references and an independently checked disposition. Counts include structural negative/dead closure facts, not only independent reachable BLE operations. Every exclusion is listed below.

Existing exact serializer proof: [custom_components/adjustable_bed/beds/okin_protocol.py:53 (build_cst_command)](../../../custom_components/adjustable_bed/beds/okin_protocol.py#L53); [tests/test_cluster_011_convergence.py:234 (test_frozen_cluster_vectors_build_exact_frames)](../../../tests/test_cluster_011_convergence.py#L234). Five existing literal-vector cases independently pass. A shared serializer does not prove equivalent Serenity capabilities, timing, parser or routes.

## Current proof catalog

Every ledger row uses the code (`C`) and focused test (`T`) references below. `S#/...` remains the exact immutable package-local claim. Code and test file/symbol hashes, source anchors and literal vector bindings are retained in the machine-local comparison evidence. Repeated references mean shared behavior, not additional operations.

| Reference | Current code or focused test |
| --- | --- |
| C01 | [custom_components/adjustable_bed/beds/base.py:534 (_write_gatt_with_retry)](../../../custom_components/adjustable_bed/beds/base.py#L534) |
| C02 | [custom_components/adjustable_bed/beds/base.py:1399 (supports_clock_alarm)](../../../custom_components/adjustable_bed/beds/base.py#L1399) |
| C03 | [custom_components/adjustable_bed/beds/base.py:1404 (supports_clock_sync)](../../../custom_components/adjustable_bed/beds/base.py#L1404) |
| C04 | [custom_components/adjustable_bed/beds/base.py:1200 (supports_position_feedback)](../../../custom_components/adjustable_bed/beds/base.py#L1200) |
| C05 | [custom_components/adjustable_bed/beds/base.py:1538 (supports_sync)](../../../custom_components/adjustable_bed/beds/base.py#L1538) |
| C06 | [custom_components/adjustable_bed/beds/okin_cst.py:487 (_move_motor)](../../../custom_components/adjustable_bed/beds/okin_cst.py#L487) |
| C07 | [custom_components/adjustable_bed/beds/okin_cst.py:545 (_send_button_press)](../../../custom_components/adjustable_bed/beds/okin_cst.py#L545) |
| C08 | [custom_components/adjustable_bed/beds/okin_cst.py:537 (_send_preset)](../../../custom_components/adjustable_bed/beds/okin_cst.py#L537) |
| C09 | [custom_components/adjustable_bed/beds/okin_cst.py:298 (control_characteristic_uuid)](../../../custom_components/adjustable_bed/beds/okin_cst.py#L298) |
| C10 | [custom_components/adjustable_bed/beds/okin_cst.py:333 (memory_slot_names)](../../../custom_components/adjustable_bed/beds/okin_cst.py#L333) |
| C11 | [custom_components/adjustable_bed/beds/okin_cst.py:622 (stop_all)](../../../custom_components/adjustable_bed/beds/okin_cst.py#L622) |
| C12 | [custom_components/adjustable_bed/beds/okin_cst.py:345 (supports_discrete_light_control)](../../../custom_components/adjustable_bed/beds/okin_cst.py#L345) |
| C13 | [custom_components/adjustable_bed/beds/okin_cst.py:349 (supports_massage)](../../../custom_components/adjustable_bed/beds/okin_cst.py#L349) |
| C14 | [custom_components/adjustable_bed/beds/okin_cst.py:309 (supports_preset_anti_snore)](../../../custom_components/adjustable_bed/beds/okin_cst.py#L309) |
| C15 | [custom_components/adjustable_bed/beds/okin_cst.py:313 (supports_preset_lounge)](../../../custom_components/adjustable_bed/beds/okin_cst.py#L313) |
| C16 | [custom_components/adjustable_bed/beds/okin_cst.py:305 (supports_preset_zero_g)](../../../custom_components/adjustable_bed/beds/okin_cst.py#L305) |
| C17 | [custom_components/adjustable_bed/beds/okin_protocol.py:53 (build_cst_command)](../../../custom_components/adjustable_bed/beds/okin_protocol.py#L53) |
| C18 | [custom_components/adjustable_bed/beds/serenity.py:46 (_ACTIONS)](../../../custom_components/adjustable_bed/beds/serenity.py#L46) |
| C19 | [custom_components/adjustable_bed/beds/serenity.py:79 (_SAVE_CODES)](../../../custom_components/adjustable_bed/beds/serenity.py#L79) |
| C20 | [custom_components/adjustable_bed/beds/serenity.py:80 (_SAVE_HOLD_MS)](../../../custom_components/adjustable_bed/beds/serenity.py#L80) |
| C21 | [custom_components/adjustable_bed/beds/serenity.py:680 (SerenityController.__init__)](../../../custom_components/adjustable_bed/beds/serenity.py#L680) |
| C22 | [custom_components/adjustable_bed/beds/serenity.py:483 (OkinBeddingAppController._handle_notification)](../../../custom_components/adjustable_bed/beds/serenity.py#L483) |
| C23 | [custom_components/adjustable_bed/beds/serenity.py:618 (OkinBeddingAppController._send_repeated_command)](../../../custom_components/adjustable_bed/beds/serenity.py#L618) |
| C24 | [custom_components/adjustable_bed/beds/serenity.py:591 (OkinBeddingAppController._send_stop_sequence)](../../../custom_components/adjustable_bed/beds/serenity.py#L591) |
| C25 | [custom_components/adjustable_bed/beds/serenity.py:392 (OkinBeddingAppController._write_response)](../../../custom_components/adjustable_bed/beds/serenity.py#L392) |
| C26 | [custom_components/adjustable_bed/beds/serenity.py:413 (OkinBeddingAppController.async_discover_capabilities)](../../../custom_components/adjustable_bed/beds/serenity.py#L413) |
| C27 | [custom_components/adjustable_bed/beds/serenity.py:664 (OkinBeddingAppController.controller_button_specs)](../../../custom_components/adjustable_bed/beds/serenity.py#L664) |
| C28 | [custom_components/adjustable_bed/beds/serenity.py:526 (OkinBeddingAppController.controller_state_sensor_specs)](../../../custom_components/adjustable_bed/beds/serenity.py#L526) |
| C29 | [custom_components/adjustable_bed/beds/serenity.py:670 (OkinBeddingAppController.execute_app_control)](../../../custom_components/adjustable_bed/beds/serenity.py#L670) |
| C30 | [custom_components/adjustable_bed/beds/serenity.py:553 (OkinBeddingAppController.held_control_options)](../../../custom_components/adjustable_bed/beds/serenity.py#L553) |
| C31 | [custom_components/adjustable_bed/beds/serenity.py:556 (OkinBeddingAppController.hold_control)](../../../custom_components/adjustable_bed/beds/serenity.py#L556) |
| C32 | [custom_components/adjustable_bed/beds/serenity.py:370 (OkinBeddingAppController.motor_control_specs)](../../../custom_components/adjustable_bed/beds/serenity.py#L370) |
| C33 | [custom_components/adjustable_bed/beds/serenity.py:374 (OkinBeddingAppController.motor_pulse_settings)](../../../custom_components/adjustable_bed/beds/serenity.py#L374) |
| C34 | [custom_components/adjustable_bed/beds/serenity.py:652 (OkinBeddingAppController.program_memory)](../../../custom_components/adjustable_bed/beds/serenity.py#L652) |
| C35 | [custom_components/adjustable_bed/beds/serenity.py:385 (OkinBeddingAppController.protocol_diagnostics)](../../../custom_components/adjustable_bed/beds/serenity.py#L385) |
| C36 | [custom_components/adjustable_bed/beds/serenity.py:456 (OkinBeddingAppController.refresh_manufacturer)](../../../custom_components/adjustable_bed/beds/serenity.py#L456) |
| C37 | [custom_components/adjustable_bed/beds/serenity.py:350 (OkinBeddingAppController.requires_notification_channel)](../../../custom_components/adjustable_bed/beds/serenity.py#L350) |
| C38 | [custom_components/adjustable_bed/beds/serenity.py:445 (OkinBeddingAppController.start_notify)](../../../custom_components/adjustable_bed/beds/serenity.py#L445) |
| C39 | [custom_components/adjustable_bed/beds/serenity.py:428 (OkinBeddingAppController.write_command)](../../../custom_components/adjustable_bed/beds/serenity.py#L428) |
| C40 | [custom_components/adjustable_bed/config_flow.py:1863 (AdjustableBedConfigFlow._async_rebuild_changed_serenity_form)](../../../custom_components/adjustable_bed/config_flow.py#L1863) |
| C41 | [custom_components/adjustable_bed/config_flow.py:1896 (AdjustableBedConfigFlow.async_step_bluetooth_confirm)](../../../custom_components/adjustable_bed/config_flow.py#L1896) |
| C42 | [custom_components/adjustable_bed/config_flow.py:2882 (AdjustableBedConfigFlow.async_step_manual_config)](../../../custom_components/adjustable_bed/config_flow.py#L2882) |
| C43 | [custom_components/adjustable_bed/config_flow.py:3185 (AdjustableBedConfigFlow.async_step_manual_entry)](../../../custom_components/adjustable_bed/config_flow.py#L3185) |
| C44 | [custom_components/adjustable_bed/config_flow.py:5391 (AdjustableBedOptionsFlow.async_step_init)](../../../custom_components/adjustable_bed/config_flow.py#L5391) |
| C45 | [custom_components/adjustable_bed/config_flow.py:620 (_motor_count_options)](../../../custom_components/adjustable_bed/config_flow.py#L620) |
| C46 | [custom_components/adjustable_bed/config_flow.py:661 (_normalize_fixed_motor_count)](../../../custom_components/adjustable_bed/config_flow.py#L661) |
| C47 | [custom_components/adjustable_bed/const.py:2377 (bed_type_has_position_feedback)](../../../custom_components/adjustable_bed/const.py#L2377) |
| C48 | [custom_components/adjustable_bed/const.py:2264 (requires_pairing)](../../../custom_components/adjustable_bed/const.py#L2264) |
| C49 | [custom_components/adjustable_bed/controller_factory.py:350 (_create_from_registry)](../../../custom_components/adjustable_bed/controller_factory.py#L350) |
| C50 | [custom_components/adjustable_bed/sensor.py:407 (AdjustableBedControllerStateSensor)](../../../custom_components/adjustable_bed/sensor.py#L407) |
| C51 | [custom_components/adjustable_bed/sensor.py:153 (_sensor_entities_for)](../../../custom_components/adjustable_bed/sensor.py#L153) |
| C52 | [custom_components/adjustable_bed/services.py:1763 (_hold_targets)](../../../custom_components/adjustable_bed/services.py#L1763) |
| C53 | [custom_components/adjustable_bed/services.py:1713 (handle_hold_control)](../../../custom_components/adjustable_bed/services.py#L1713) |
| C54 | [custom_components/adjustable_bed/switch.py:160 (AdjustableBedSwitch)](../../../custom_components/adjustable_bed/switch.py#L160) |
| T01 | [tests/test_cluster_011_convergence.py:234 (test_frozen_cluster_vectors_build_exact_frames)](../../../tests/test_cluster_011_convergence.py#L234) |
| T02 | [tests/test_serenity.py:637 (test_aborted_save_retains_artifact_local_intent_without_storage_ack)](../../../tests/test_serenity.py#L637) |
| T03 | [tests/test_serenity.py:110 (test_all45_artifact_rows_or_explicit_safe_stop)](../../../tests/test_serenity.py#L110) |
| T04 | [tests/test_serenity.py:522 (test_both_release_attempts_survive_first_write_error)](../../../tests/test_serenity.py#L522) |
| T05 | [tests/test_serenity.py:268 (test_cancelled_task_and_signal_cannot_suppress_two_stop_frames)](../../../tests/test_serenity.py#L268) |
| T06 | [tests/test_serenity.py:494 (test_default_public_action_elapsed_duration)](../../../tests/test_serenity.py#L494) |
| T07 | [tests/test_serenity.py:678 (test_default_save_gesture_matches_bound_five_second_app_help)](../../../tests/test_serenity.py#L678) |
| T08 | [tests/test_serenity.py:179 (test_exact_capabilities_no_guessed_extra_axes)](../../../tests/test_serenity.py#L179) |
| T09 | [tests/test_serenity.py:339 (test_exact_gatt_roles_fail_before_subscription)](../../../tests/test_serenity.py#L339) |
| T10 | [tests/test_serenity.py:504 (test_inherited_wave_routes_use_reachable_direct_frames)](../../../tests/test_serenity.py#L504) |
| T11 | [tests/test_serenity.py:219 (test_literal_buttons_bound_callback)](../../../tests/test_serenity.py#L219) |
| T12 | [tests/test_serenity.py:161 (test_live_alarm_reply_with_dead_alarm_controls)](../../../tests/test_serenity.py#L161) |
| T13 | [tests/test_serenity.py:363 (test_manufacturer_exact_optional_role)](../../../tests/test_serenity.py#L363) |
| T14 | [tests/test_serenity.py:307 (test_manufacturer_no_capability_selection_or_alarm_enable)](../../../tests/test_serenity.py#L307) |
| T15 | [tests/test_serenity.py:385 (test_manufacturer_subscription_order_and_explicit_refresh_button)](../../../tests/test_serenity.py#L385) |
| T16 | [tests/test_serenity.py:662 (test_notification_during_first_save_write_consumes_local_intent)](../../../tests/test_serenity.py#L662) |
| T17 | [tests/test_serenity.py:418 (test_notification_setup_has_only_subscription_and_information_read)](../../../tests/test_serenity.py#L418) |
| T18 | [tests/test_serenity.py:291 (test_notification_subscription_required_manufacturer_failure_optional)](../../../tests/test_serenity.py#L291) |
| T19 | [tests/test_serenity.py:320 (test_property_write_policy)](../../../tests/test_serenity.py#L320) |
| T20 | [tests/test_serenity.py:244 (test_public_controller_actions)](../../../tests/test_serenity.py#L244) |
| T21 | [tests/test_serenity.py:252 (test_real_elapsed_ceiling_and_two_delayed_releases)](../../../tests/test_serenity.py#L252) |
| T22 | [tests/test_serenity.py:466 (test_recall_clears_prior_save_code)](../../../tests/test_serenity.py#L466) |
| T23 | [tests/test_serenity.py:565 (test_release_deadlines_share_origin_despite_write_latency)](../../../tests/test_serenity.py#L565) |
| T24 | [tests/test_serenity.py:541 (test_repeated_task_cancellation_during_release_keeps_both_frames)](../../../tests/test_serenity.py#L541) |
| T25 | [tests/test_serenity.py:438 (test_save_pending_survives_release_nonrecall_and_duplicate_status)](../../../tests/test_serenity.py#L438) |
| T26 | [tests/test_serenity.py:137 (test_signed_status_change_only_save_diversion_and_short_input)](../../../tests/test_serenity.py#L137) |
| T27 | [tests/test_serenity.py:329 (test_unsupported_actions_no_write)](../../../tests/test_serenity.py#L329) |
| T28 | [tests/test_serenity.py:604 (test_write_timeout_is_not_mistaken_for_elapsed_hold_deadline)](../../../tests/test_serenity.py#L604) |
| T29 | [tests/test_serenity_config.py:146 (test_changing_setup_profile_restores_choices_and_keeps_entered_values)](../../../tests/test_serenity_config.py#L146) |
| T30 | [tests/test_serenity_config.py:26 (test_explicit_profile_builds_fixed_controls_without_live_advertisement)](../../../tests/test_serenity_config.py#L26) |
| T31 | [tests/test_serenity_config.py:46 (test_fixed_named_axis_layout_normalizes_old_generic_motor_setting)](../../../tests/test_serenity_config.py#L46) |
| T32 | [tests/test_serenity_config.py:93 (test_options_switch_from_generic_profile_preserves_explicit_serenity_defaults)](../../../tests/test_serenity_config.py#L93) |
| T33 | [tests/test_serenity_config.py:67 (test_setup_hides_unproven_motor_count_and_fixed_refresh_delay)](../../../tests/test_serenity_config.py#L67) |
| T34 | [tests/test_serenity_entities.py:186 (test_discrete_light_switch_tracks_only_commanded_intent)](../../../tests/test_serenity_entities.py#L186) |
| T35 | [tests/test_serenity_entities.py:117 (test_native_light_toggle_keeps_unknown_physical_state)](../../../tests/test_serenity_entities.py#L117) |
| T36 | [tests/test_serenity_entities.py:138 (test_other_axis_stop_preempts_a_running_cover_through_production_scheduler)](../../../tests/test_serenity_entities.py#L138) |
| T37 | [tests/test_serenity_entities.py:215 (test_parser_publishes_native_diagnostic_values_and_signed_alarm_attributes)](../../../tests/test_serenity_entities.py#L215) |
| T38 | [tests/test_serenity_entities.py:95 (test_profile_retires_old_lumbar_cover_without_guessing_auxiliary_axes)](../../../tests/test_serenity_entities.py#L95) |
| T39 | [tests/test_serenity_entities.py:29 (test_status_sensor_reload_reconciles_only_the_current_side)](../../../tests/test_serenity_entities.py#L29) |
| T40 | [tests/test_generic_services.py:105 (test_hold_control_lists_valid_controls_before_any_write)](../../../tests/test_generic_services.py#L105) |
| T41 | [tests/test_serenity_services.py:165 (test_cancelled_dispatch_restores_later_preflighted_target_idle_timer)](../../../tests/test_serenity_services.py#L165) |
| T42 | [tests/test_serenity_services.py:97 (test_later_incompatible_target_rejects_before_any_write)](../../../tests/test_serenity_services.py#L97) |
| T43 | [tests/test_serenity_services.py:120 (test_real_pair_preserves_requested_side_and_literal_action)](../../../tests/test_serenity_services.py#L120) |
| T44 | [tests/test_serenity_services.py:50 (test_serenity_hold_preflights_profile_and_literal_action)](../../../tests/test_serenity_services.py#L50) |
| T45 | [tests/test_serenity_services.py:77 (test_service_to_real_controller_emits_artifact_save_and_release)](../../../tests/test_serenity_services.py#L77) |

## Complete ledger

| ID | Discovery and immutable source | Disposition | Current proof or exact exclusion reason |
| --- | --- | --- | --- |
| CMD-001 | CMD01 head up. `S#/protocols/0/commands/0` | IMPLEMENTED | C18, C31, C33, C32, C01, C06, C53, C52, T03, T21, T05, T44, T45, T42, T43, T41, T40, T36; literal action-vector row 1 |
| CMD-002 | CMD02 head down. `S#/protocols/0/commands/1` | IMPLEMENTED | C18, C31, C33, C32, C01, C06, C53, C52, T03, T21, T05, T44, T45, T42, T43, T41, T40, T36; literal action-vector row 2 |
| CMD-003 | CMD03 foot up. `S#/protocols/0/commands/2` | IMPLEMENTED | C18, C31, C33, C32, C01, C06, C53, C52, T03, T21, T05, T44, T45, T42, T43, T41, T40, T36; literal action-vector row 3 |
| CMD-004 | CMD04 foot down. `S#/protocols/0/commands/3` | IMPLEMENTED | C18, C31, C33, C32, C01, C06, C53, C52, T03, T21, T05, T44, T45, T42, T43, T41, T40, T36; literal action-vector row 4 |
| CMD-005 | CMD05 remote lumbarp (presenter tilt up). `S#/protocols/0/commands/4` | IMPLEMENTED | C18, C31, C33, C32, C01, C06, C53, C52, T03, T21, T05, T44, T45, T42, T43, T41, T40, T36; literal action-vector row 5 |
| CMD-006 | CMD06 remote lumbardown (presenter tilt down). `S#/protocols/0/commands/5` | IMPLEMENTED | C18, C31, C33, C32, C01, C06, C53, C52, T03, T21, T05, T44, T45, T42, T43, T41, T40, T36; literal action-vector row 6 |
| CMD-007 | CMD07 remote tiltup (presenter lumbar up). `S#/protocols/0/commands/6` | IMPLEMENTED | C18, C31, C33, C32, C01, C06, C53, C52, T03, T21, T05, T44, T45, T42, T43, T41, T40, T36; literal action-vector row 7 |
| CMD-008 | CMD08 remote tiltdown (presenter lumbar down). `S#/protocols/0/commands/7` | IMPLEMENTED | C18, C31, C33, C32, C01, C06, C53, C52, T03, T21, T05, T44, T45, T42, T43, T41, T40, T36; literal action-vector row 8 |
| CMD-009 | CMD09 Flat recall. `S#/protocols/0/commands/8` | IMPLEMENTED | C18, C19, C31, C01, C08, C23, C53, C52, T03, T20, T06, T25, T22, T02, T16, T44, T45, T42, T43, T41, T40; literal action-vector row 9 |
| CMD-010 | CMD10 Zero Gravity recall. `S#/protocols/0/commands/9` | IMPLEMENTED | C18, C19, C31, C01, C08, C23, C53, C52, T03, T20, T06, T25, T22, T02, T16, T44, T45, T42, T43, T41, T40; literal action-vector row 10 |
| CMD-011 | CMD11 M1 recall. `S#/protocols/0/commands/10` | IMPLEMENTED | C18, C19, C31, C01, C08, C23, C53, C52, T03, T20, T06, T25, T22, T02, T16, T44, T45, T42, T43, T41, T40; literal action-vector row 11 |
| CMD-012 | CMD12 TV recall. `S#/protocols/0/commands/11` | IMPLEMENTED | C18, C19, C31, C01, C08, C23, C53, C52, T03, T20, T06, T25, T22, T02, T16, T44, T45, T42, T43, T41, T40; literal action-vector row 12 |
| CMD-013 | CMD13 M2 recall. `S#/protocols/0/commands/12` | IMPLEMENTED | C18, C19, C31, C01, C08, C23, C53, C52, T03, T20, T06, T25, T22, T02, T16, T44, T45, T42, T43, T41, T40; literal action-vector row 13 |
| CMD-014 | CMD14 Zero Gravity save. `S#/protocols/0/commands/13` | IMPLEMENTED | C18, C19, C31, C20, C34, C29, C01, C08, C23, C53, C52, T03, T20, T06, T25, T22, T02, T16, T07, T44, T45, T42, T43, T41, T40; literal action-vector row 14 |
| CMD-015 | CMD15 M1 save. `S#/protocols/0/commands/14` | IMPLEMENTED | C18, C19, C31, C20, C34, C29, C01, C08, C23, C53, C52, T03, T20, T06, T25, T22, T02, T16, T07, T44, T45, T42, T43, T41, T40; literal action-vector row 15 |
| CMD-016 | CMD16 TV save. `S#/protocols/0/commands/15` | IMPLEMENTED | C18, C19, C31, C20, C34, C29, C01, C08, C23, C53, C52, T03, T20, T06, T25, T22, T02, T16, T07, T44, T45, T42, T43, T41, T40; literal action-vector row 16 |
| CMD-017 | CMD17 M2 save. `S#/protocols/0/commands/16` | IMPLEMENTED | C18, C19, C31, C20, C34, C29, C01, C08, C23, C53, C52, T03, T20, T06, T25, T22, T02, T16, T07, T44, T45, T42, T43, T41, T40; literal action-vector row 17 |
| CMD-018 | CMD18 head massage cycle. `S#/protocols/0/commands/17` | IMPLEMENTED | C18, C31, C27, C01, C07, C23, C53, C52, T03, T20, T06, T10, T44, T45, T42, T43, T41, T40; literal action-vector row 18 |
| CMD-019 | CMD19 foot massage cycle. `S#/protocols/0/commands/18` | IMPLEMENTED | C18, C31, C27, C01, C07, C23, C53, C52, T03, T20, T06, T10, T44, T45, T42, T43, T41, T40; literal action-vector row 19 |
| CMD-020 | CMD20 massage mode cycle. `S#/protocols/0/commands/19` | IMPLEMENTED | C18, C31, C27, C01, C07, C23, C53, C52, T03, T20, T06, T10, T44, T45, T42, T43, T41, T40; literal action-vector row 20 |
| CMD-021 | CMD21 massage timer cycle. `S#/protocols/0/commands/20` | IMPLEMENTED | C18, C31, C27, C01, C07, C23, C53, C52, T03, T20, T06, T10, T44, T45, T42, T43, T41, T40; literal action-vector row 21 |
| CMD-022 | CMD22 massage toggle. `S#/protocols/0/commands/21` | IMPLEMENTED | C18, C31, C27, C01, C07, C23, C53, C52, T03, T20, T06, T10, T44, T45, T42, T43, T41, T40; literal action-vector row 22 |
| CMD-023 | CMD23 under-bed light toggle. `S#/protocols/0/commands/22` | IMPLEMENTED | C18, C31, C27, C01, C07, C23, C53, C52, T03, T20, T06, T10, T44, T45, T42, T43, T41, T40; literal action-vector row 23 |
| CMD-024 | CMD24 Voice headup. `S#/protocols/0/commands/23` | IMPLEMENTED | C18, C31, C33, C32, C01, C06, C53, C52, T03, T21, T05, T44, T45, T42, T43, T41, T40, T36; literal action-vector row 24 |
| CMD-025 | CMD25 Voice headdown / headeddown / hadtodown / headthatdown / heatherdown. `S#/protocols/0/commands/24` | IMPLEMENTED | C18, C31, C33, C32, C01, C06, C53, C52, T03, T21, T05, T44, T45, T42, T43, T41, T40, T36; literal action-vector row 25 |
| CMD-026 | CMD26 Voice footup. `S#/protocols/0/commands/25` | IMPLEMENTED | C18, C31, C33, C32, C01, C06, C53, C52, T03, T21, T05, T44, T45, T42, T43, T41, T40, T36; literal action-vector row 26 |
| CMD-027 | CMD27 Voice footdown. `S#/protocols/0/commands/26` | IMPLEMENTED | C18, C31, C33, C32, C01, C06, C53, C52, T03, T21, T05, T44, T45, T42, T43, T41, T40, T36; literal action-vector row 27 |
| CMD-028 | CMD28 Voice headtiltup. `S#/protocols/0/commands/27` | IMPLEMENTED | C18, C31, C33, C32, C01, C06, C53, C52, T03, T21, T05, T44, T45, T42, T43, T41, T40, T36; literal action-vector row 28 |
| CMD-029 | CMD29 Voice headtiltdown. `S#/protocols/0/commands/28` | IMPLEMENTED | C18, C31, C33, C32, C01, C06, C53, C52, T03, T21, T05, T44, T45, T42, T43, T41, T40, T36; literal action-vector row 29 |
| CMD-030 | CMD30 Voice lumbarup. `S#/protocols/0/commands/29` | IMPLEMENTED | C18, C31, C33, C32, C01, C06, C53, C52, T03, T21, T05, T44, T45, T42, T43, T41, T40, T36; literal action-vector row 30 |
| CMD-031 | CMD31 Voice lumbardown. `S#/protocols/0/commands/30` | IMPLEMENTED | C18, C31, C33, C32, C01, C06, C53, C52, T03, T21, T05, T44, T45, T42, T43, T41, T40, T36; literal action-vector row 31 |
| CMD-032 | CMD32 Voice stop (actually head-up then delayed STOP). `S#/protocols/0/commands/31` | EXCLUDED | The voice stop branch starts head-up before delaying STOP, which is unsafe for a stop action. Safe protocol STOP is retained separately as CMD45; this excludes only the erroneous movement trigger. |
| CMD-033 | CMD33 Voice leisure. `S#/protocols/0/commands/32` | IMPLEMENTED | C18, C19, C31, C01, C08, C23, C53, C52, T03, T20, T06, T25, T22, T02, T16, T44, T45, T42, T43, T41, T40; literal action-vector row 33 |
| CMD-034 | CMD34 Voice zerogravity. `S#/protocols/0/commands/33` | IMPLEMENTED | C18, C19, C31, C01, C08, C23, C53, C52, T03, T20, T06, T25, T22, T02, T16, T44, T45, T42, T43, T41, T40; literal action-vector row 34 |
| CMD-035 | CMD35 Voice snore / snow. `S#/protocols/0/commands/34` | IMPLEMENTED | C18, C19, C31, C01, C08, C23, C53, C52, T03, T20, T06, T25, T22, T02, T16, T44, T45, T42, T43, T41, T40; literal action-vector row 35 |
| CMD-036 | CMD36 Voice tv. `S#/protocols/0/commands/35` | IMPLEMENTED | C18, C19, C31, C01, C08, C23, C53, C52, T03, T20, T06, T25, T22, T02, T16, T44, T45, T42, T43, T41, T40; literal action-vector row 36 |
| CMD-037 | CMD37 Voice flat. `S#/protocols/0/commands/36` | IMPLEMENTED | C18, C19, C31, C01, C08, C23, C53, C52, T03, T20, T06, T25, T22, T02, T16, T44, T45, T42, T43, T41, T40; literal action-vector row 37 |
| CMD-038 | CMD38 Voice massageon / waveone / wave1. `S#/protocols/0/commands/37` | IMPLEMENTED | C18, C31, C27, C01, C07, C23, C53, C52, T03, T20, T06, T10, T44, T45, T42, T43, T41, T40; literal action-vector row 38 |
| CMD-039 | CMD39 Voice wavetwo / wave2. `S#/protocols/0/commands/38` | IMPLEMENTED | C18, C31, C27, C01, C07, C23, C53, C52, T03, T20, T06, T10, T44, T45, T42, T43, T41, T40; literal action-vector row 39 |
| CMD-040 | CMD40 Voice wavethree / wave3. `S#/protocols/0/commands/39` | IMPLEMENTED | C18, C31, C27, C01, C07, C23, C53, C52, T03, T20, T06, T10, T44, T45, T42, T43, T41, T40; literal action-vector row 40 |
| CMD-041 | CMD41 Voice massageoff. `S#/protocols/0/commands/40` | IMPLEMENTED | C18, C31, C27, C01, C07, C23, C53, C52, T03, T20, T06, T10, T44, T45, T42, T43, T41, T40; literal action-vector row 41 |
| CMD-042 | CMD42 Voice lighton / lightson. `S#/protocols/0/commands/41` | IMPLEMENTED | C18, C31, C27, C01, C07, C23, C53, C52, T03, T20, T06, T10, T44, T45, T42, T43, T41, T40; literal action-vector row 42 |
| CMD-043 | CMD43 Voice lightoff / lightsoff. `S#/protocols/0/commands/42` | IMPLEMENTED | C18, C31, C27, C01, C07, C23, C53, C52, T03, T20, T06, T10, T44, T45, T42, T43, T41, T40; literal action-vector row 43 |
| CMD-044 | CMD44 Voice togglelights / togglelight. `S#/protocols/0/commands/43` | IMPLEMENTED | C18, C31, C27, C01, C07, C23, C53, C52, T03, T20, T06, T10, T44, T45, T42, T43, T41, T40; literal action-vector row 44 |
| CMD-045 | CMD45 Release/cancel STOP. `S#/protocols/0/commands/44` | IMPLEMENTED | C24, C31, C01, C11, C53, C52, T03, T05, T21, T23, T04, T24, T44, T45, T42, T43, T41, T40, T36; literal action-vector row 45 |
| CAND-001 | T01 discoverServices. `S#/candidate_ledger/0` | EXCLUDED | Android connector/discovery/connection lifecycle is a transport boundary; HA owns physical address, connection/retry/cleanup. Exact wire characteristics and subscribed/read/written behavior are retained separately. |
| CAND-002 | T02 close. `S#/candidate_ledger/1` | EXCLUDED | Android connector/discovery/connection lifecycle is a transport boundary; HA owns physical address, connection/retry/cleanup. Exact wire characteristics and subscribed/read/written behavior are retained separately. |
| CAND-003 | T03 close. `S#/candidate_ledger/2` | EXCLUDED | Android connector/discovery/connection lifecycle is a transport boundary; HA owns physical address, connection/retry/cleanup. Exact wire characteristics and subscribed/read/written behavior are retained separately. |
| CAND-004 | T04 disconnect. `S#/candidate_ledger/3` | EXCLUDED | Android connector/discovery/connection lifecycle is a transport boundary; HA owns physical address, connection/retry/cleanup. Exact wire characteristics and subscribed/read/written behavior are retained separately. |
| CAND-005 | T05 connectGatt. `S#/candidate_ledger/4` | EXCLUDED | Android connector/discovery/connection lifecycle is a transport boundary; HA owns physical address, connection/retry/cleanup. Exact wire characteristics and subscribed/read/written behavior are retained separately. |
| CAND-006 | T06 connectGatt. `S#/candidate_ledger/5` | EXCLUDED | Android connector/discovery/connection lifecycle is a transport boundary; HA owns physical address, connection/retry/cleanup. Exact wire characteristics and subscribed/read/written behavior are retained separately. |
| CAND-007 | T07 disconnect. `S#/candidate_ledger/6` | EXCLUDED | Android connector/discovery/connection lifecycle is a transport boundary; HA owns physical address, connection/retry/cleanup. Exact wire characteristics and subscribed/read/written behavior are retained separately. |
| CAND-008 | T08 getService. `S#/candidate_ledger/7` | IMPLEMENTED | C37, C26, C38, C49, T18, T08, T09, T17, T30 |
| CAND-009 | T09 getCharacteristic. `S#/candidate_ledger/8` | IMPLEMENTED | C37, C26, C38, C49, T18, T08, T09, T17, T30 |
| CAND-010 | T10 setCharacteristicNotification. `S#/candidate_ledger/9` | IMPLEMENTED | C37, C26, C38, T18, T08, T09, T17 |
| CAND-011 | T11 getDescriptor. `S#/candidate_ledger/10` | IMPLEMENTED | C37, C26, C38, T18, T08, T09, T17 |
| CAND-012 | T12 writeDescriptor. `S#/candidate_ledger/11` | IMPLEMENTED | C37, C26, C38, T18, T08, T09, T17 |
| CAND-013 | T13 getService. `S#/candidate_ledger/12` | IMPLEMENTED | C36, C38, C27, T14, T18, T13, T15 |
| CAND-014 | T14 getCharacteristic. `S#/candidate_ledger/13` | IMPLEMENTED | C36, C38, C27, T14, T18, T13, T15 |
| CAND-015 | T15 readCharacteristic. `S#/candidate_ledger/14` | IMPLEMENTED | C36, C38, C27, T14, T18, T13, T15 |
| CAND-016 | T16 getService. `S#/candidate_ledger/15` | IMPLEMENTED | C25, C39, C26, C01, T19, T03, T09 |
| CAND-017 | T17 getCharacteristic. `S#/candidate_ledger/16` | IMPLEMENTED | C25, C39, C26, C01, T19, T03, T09 |
| CAND-018 | T18 writeCharacteristic. `S#/candidate_ledger/17` | IMPLEMENTED | C25, C39, C26, C01, T19, T03, T09 |
| CAND-019 | T19 startLeScan. `S#/candidate_ledger/18` | EXCLUDED | Android connector/discovery/connection lifecycle is a transport boundary; HA owns physical address, connection/retry/cleanup. Exact wire characteristics and subscribed/read/written behavior are retained separately. |
| CAND-020 | T20 stopLeScan. `S#/candidate_ledger/19` | EXCLUDED | Android connector/discovery/connection lifecycle is a transport boundary; HA owns physical address, connection/retry/cleanup. Exact wire characteristics and subscribed/read/written behavior are retained separately. |
| CAND-021 | T21 disconnect. `S#/candidate_ledger/20` | EXCLUDED | Android connector/discovery/connection lifecycle is a transport boundary; HA owns physical address, connection/retry/cleanup. Exact wire characteristics and subscribed/read/written behavior are retained separately. |
| CAND-022 | T22 disconnect. `S#/candidate_ledger/21` | EXCLUDED | Unused disconnect-all helper; no reachable caller in app UI/lifecycle; no reachable BLE operation to implement. |
| CAND-023 | T23 disconnect. `S#/candidate_ledger/22` | EXCLUDED | Android connector/discovery/connection lifecycle is a transport boundary; HA owns physical address, connection/retry/cleanup. Exact wire characteristics and subscribed/read/written behavior are retained separately. |
| CAND-024 | C01 Protocol factory. `S#/candidate_ledger/23` | IMPLEMENTED | C21, C32, C30, C27, C49, T08, T27, T30 |
| CAND-025 | C02 Packet builder. `S#/candidate_ledger/24` | ALREADY_IMPLEMENTED | C17, T01, T03 |
| CAND-026 | C03 Action dispatch. `S#/candidate_ledger/25` | IMPLEMENTED | C18, C31, C29, C49, T03, T11, T27, T30 |
| CAND-027 | C04 Notification parser. `S#/candidate_ledger/26` | IMPLEMENTED | C22, C28, C35, C51, C50, T26, T12, T25, T22, T02, T16, T39, T37 |
| CAND-028 | C05 Z230 screen pair. `S#/candidate_ledger/27` | EXCLUDED | getBedType==0 never true; no reachable BLE operation to implement. |
| CAND-029 | C06 Legacy lift screen. `S#/candidate_ledger/28` | EXCLUDED | No attachment or instantiation; no reachable BLE operation to implement. |
| CAND-030 | C07 Legacy massage screen. `S#/candidate_ledger/29` | EXCLUDED | Unused constructed Activity field; no reachable BLE operation to implement. |
| CAND-031 | C08 Alarm controls/current time/query. `S#/candidate_ledger/30` | EXCLUDED | haveAlarm initialized false and only ever set false; no attached alarm page; no reachable BLE operation to implement. |
| CAND-032 | C09 Adjustment clock checksum. `S#/candidate_ledger/31` | EXCLUDED | adjustAlarm has no caller; not a normal-control checksum; no reachable BLE operation to implement. |
| CAND-033 | C10 Query massage/direct level/timer helpers. `S#/candidate_ledger/32` | EXCLUDED | queryMassageStatus, setMassageTime, setMassageIntensity, massageModeDecrease, turnOnMassage have no reachable caller; no reachable BLE operation to implement. |
| CAND-034 | C11 Presenter speech delegate. `S#/candidate_ledger/33` | EXCLUDED | startListening has no caller; Activity uses speech intent result instead. Distinct legacy voice map preserved as dead.; no reachable BLE operation to implement. |
| CAND-035 | C12 Combined motors3 helpers. `S#/candidate_ledger/34` | EXCLUDED | unionUp/Down dispatch cases exist but selected remote never emits those bits; no voice mapping; no reachable BLE operation to implement. |
| CAND-036 | C13 Unused checksum and save timer. `S#/candidate_ledger/35` | EXCLUDED | getSum unused; saveMemoryRunnable never posted; no reachable BLE operation to implement. |
| CAND-037 | C14 Framework/UI SDKs. `S#/candidate_ledger/36` | EXCLUDED | UUID masks, timers, byte arrays, reflection, config and model hits outside app namespace are AndroidX/material/pickers/fonts/media/speech/graphics helpers, not control builders; no reachable BLE operation to implement. |
| CAND-038 | C15 Diagnostic logging. `S#/candidate_ledger/37` | EXCLUDED | App diagnostic hex renderer does not transform BLE behavior; Android logging/UI is unrelated to bed operation. |
| CAND-039 | C16 App lifecycle observer. `S#/candidate_ledger/38` | EXCLUDED | Observer installed but onStateChanged body empty; no background control cleanup; no reachable BLE operation to implement. |
| VAR-001 | V01 setProtocol("CSTProtocol"). `S#/variant_inventory/0` | IMPLEMENTED | C21, C32, C30, C27, C49, T08, T27, T30 |
| VAR-002 | V02 getBedType()==0. `S#/variant_inventory/1` | EXCLUDED | getBedType always returns 1; paired Z230MassageFragment is unreachable |
| VAR-003 | V03 getBedType()!=0. `S#/variant_inventory/2` | IMPLEMENTED | C21, C32, C30, C27, C49, T08, T27, T30 |
| VAR-004 | V04 isHaveAlarm()==true. `S#/variant_inventory/3` | EXCLUDED | Initially false; all reachable writes to haveAlarm set false |
| VAR-005 | V05 No instantiation/caller. `S#/variant_inventory/4` | EXCLUDED | Not added to pager or manifest |
| VAR-006 | V06 FunctionActivity field only. `S#/variant_inventory/5` | EXCLUDED | Constructed field but never attached to pager |
| VAR-007 | V07 Persisted bedSelection default1. `S#/variant_inventory/6` | EXCLUDED | setBedSelection has no caller; getBedSelection only consumed in unreachable alarm builder |
| BEH-001 | selectors/0. `S#/protocols/0/selectors/0` | IMPLEMENTED | C21, C32, C30, C27, C49, T08, T27, T30 |
| BEH-002 | discovery_rules/name_source. `S#/protocols/0/discovery_rules/name_source` | EXCLUDED | Android permission/name-list scan, selected-device connector and posted lifecycle sequencing are application/transport boundaries; HA explicit profile/address discovery and per-device connection lifecycle replace them. Normal subscription/manufacturer-read wire behaviors remain separate positive rows. |
| BEH-003 | discovery_rules/rule. `S#/protocols/0/discovery_rules/rule` | EXCLUDED | The accepted app lowercases the advertised name using the Java default locale and accepts the shared startsWith("okin") prefix, without trimming or an app/product discriminator. That prefix cannot safely identify Serenity among products sharing this transport. HA keeps explicit manual Serenity selection rather than assigning this app profile from a shared name; the exact source rule is documented, while no protocol command is excluded. |
| BEH-004 | discovery_rules/case. `S#/protocols/0/discovery_rules/case` | EXCLUDED | The accepted app lowercases the advertised name using the Java default locale and accepts the shared startsWith("okin") prefix, without trimming or an app/product discriminator. That prefix cannot safely identify Serenity among products sharing this transport. HA keeps explicit manual Serenity selection rather than assigning this app profile from a shared name; the exact source rule is documented, while no protocol command is excluded. |
| BEH-005 | discovery_rules/advertised_service_filter. `S#/protocols/0/discovery_rules/advertised_service_filter` | EXCLUDED | Android permission/name-list scan, selected-device connector and posted lifecycle sequencing are application/transport boundaries; HA explicit profile/address discovery and per-device connection lifecycle replace them. Normal subscription/manufacturer-read wire behaviors remain separate positive rows. |
| BEH-006 | discovery_rules/advertised_service_filter_unknown_reason. `S#/protocols/0/discovery_rules/advertised_service_filter_unknown_reason` | EXCLUDED | Android permission/name-list scan, selected-device connector and posted lifecycle sequencing are application/transport boundaries; HA explicit profile/address discovery and per-device connection lifecycle replace them. Normal subscription/manufacturer-read wire behaviors remain separate positive rows. |
| BEH-007 | discovery_rules/manufacturer_filter. `S#/protocols/0/discovery_rules/manufacturer_filter` | EXCLUDED | Android permission/name-list scan, selected-device connector and posted lifecycle sequencing are application/transport boundaries; HA explicit profile/address discovery and per-device connection lifecycle replace them. Normal subscription/manufacturer-read wire behaviors remain separate positive rows. |
| BEH-008 | discovery_rules/manufacturer_filter_unknown_reason. `S#/protocols/0/discovery_rules/manufacturer_filter_unknown_reason` | EXCLUDED | Android permission/name-list scan, selected-device connector and posted lifecycle sequencing are application/transport boundaries; HA explicit profile/address discovery and per-device connection lifecycle replace them. Normal subscription/manufacturer-read wire behaviors remain separate positive rows. |
| BEH-009 | discovery_rules/precedence. `S#/protocols/0/discovery_rules/precedence` | EXCLUDED | Android permission/name-list scan, selected-device connector and posted lifecycle sequencing are application/transport boundaries; HA explicit profile/address discovery and per-device connection lifecycle replace them. Normal subscription/manufacturer-read wire behaviors remain separate positive rows. |
| BEH-010 | gatt/service. `S#/protocols/0/gatt/service` | IMPLEMENTED | C25, C39, C26, C01, T19, T03, T09 |
| BEH-011 | gatt/write. `S#/protocols/0/gatt/write` | IMPLEMENTED | C25, C39, C26, C01, C09, T19, T03, T09 |
| BEH-012 | gatt/notify. `S#/protocols/0/gatt/notify` | IMPLEMENTED | C37, C26, C38, T18, T08, T09, T17 |
| BEH-013 | gatt/descriptor. `S#/protocols/0/gatt/descriptor` | IMPLEMENTED | C37, C26, C38, T18, T08, T09, T17 |
| BEH-014 | gatt/descriptor_value. `S#/protocols/0/gatt/descriptor_value` | IMPLEMENTED | C37, C26, C38, T18, T08, T09, T17 |
| BEH-015 | gatt/information_service. `S#/protocols/0/gatt/information_service` | IMPLEMENTED | C36, C38, C27, T14, T18, T13, T15 |
| BEH-016 | gatt/information_read. `S#/protocols/0/gatt/information_read` | IMPLEMENTED | C36, C38, C27, T14, T18, T13, T15 |
| BEH-017 | gatt/write_type. `S#/protocols/0/gatt/write_type` | IMPLEMENTED | C25, C39, C26, C01, T19, T03, T09 |
| BEH-018 | gatt/read_properties. `S#/protocols/0/gatt/read_properties` | IMPLEMENTED | C36, C38, C27, T14, T18, T13, T15 |
| BEH-019 | gatt/write_properties. `S#/protocols/0/gatt/write_properties` | EXCLUDED | Artifact null/property guard is erroneous (nonnull bypass/null dereference). HA validates actual writable GATT roles for safety; no hardware byte behavior is omitted. |
| BEH-020 | gatt/mtu. `S#/protocols/0/gatt/mtu` | IMPLEMENTED | C21, C26, C38, C01, T17 |
| BEH-021 | gatt/mtu_unknown_reason. `S#/protocols/0/gatt/mtu_unknown_reason` | IMPLEMENTED | C21, C26, C38, C01, T17 |
| BEH-022 | gatt/connection_priority. `S#/protocols/0/gatt/connection_priority` | IMPLEMENTED | C21, C26, C38, C01, T17 |
| BEH-023 | gatt/connection_priority_unknown_reason. `S#/protocols/0/gatt/connection_priority_unknown_reason` | IMPLEMENTED | C21, C26, C38, C01, T17 |
| BEH-024 | gatt/bonding. `S#/protocols/0/gatt/bonding` | IMPLEMENTED | C21, C26, C38, C01, C48, T17, T31 |
| BEH-025 | gatt/bonding_unknown_reason. `S#/protocols/0/gatt/bonding_unknown_reason` | IMPLEMENTED | C21, C26, C38, C01, C48, T17, T31 |
| BEH-026 | session_sequence/0. `S#/protocols/0/session_sequence/0` | EXCLUDED | Android permission/name-list scan, selected-device connector and posted lifecycle sequencing are application/transport boundaries; HA explicit profile/address discovery and per-device connection lifecycle replace them. Normal subscription/manufacturer-read wire behaviors remain separate positive rows. |
| BEH-027 | session_sequence/1. `S#/protocols/0/session_sequence/1` | EXCLUDED | Android permission/name-list scan, selected-device connector and posted lifecycle sequencing are application/transport boundaries; HA explicit profile/address discovery and per-device connection lifecycle replace them. Normal subscription/manufacturer-read wire behaviors remain separate positive rows. |
| BEH-028 | session_sequence/2. `S#/protocols/0/session_sequence/2` | EXCLUDED | Android permission/name-list scan, selected-device connector and posted lifecycle sequencing are application/transport boundaries; HA explicit profile/address discovery and per-device connection lifecycle replace them. Normal subscription/manufacturer-read wire behaviors remain separate positive rows. |
| BEH-029 | session_sequence/3. `S#/protocols/0/session_sequence/3` | EXCLUDED | Android permission/name-list scan, selected-device connector and posted lifecycle sequencing are application/transport boundaries; HA explicit profile/address discovery and per-device connection lifecycle replace them. Normal subscription/manufacturer-read wire behaviors remain separate positive rows. |
| BEH-030 | session_sequence/4. `S#/protocols/0/session_sequence/4` | EXCLUDED | Android permission/name-list scan, selected-device connector and posted lifecycle sequencing are application/transport boundaries; HA explicit profile/address discovery and per-device connection lifecycle replace them. Normal subscription/manufacturer-read wire behaviors remain separate positive rows. |
| BEH-031 | packet_format/normal. `S#/protocols/0/packet_format/normal` | ALREADY_IMPLEMENTED | C17, T01, T03 |
| BEH-032 | packet_format/inactive_builders. `S#/protocols/0/packet_format/inactive_builders` | EXCLUDED | Alarm query/set/current-time/adjustment/checksum builders are uncalled or behind an unattached alarm page; haveAlarm is always false. No reachable write/init command uses these builders. |
| BEH-033 | capabilities/exposure. `S#/protocols/0/capabilities/exposure` | IMPLEMENTED | C21, C32, C30, C27, C49, T08, T27, T30 |
| BEH-034 | capabilities/individual_motor_selectors. `S#/protocols/0/capabilities/individual_motor_selectors` | IMPLEMENTED | C21, C32, C30, C27, C49, T08, T27, T30, T38 |
| BEH-035 | capabilities/motor_count. `S#/protocols/0/capabilities/motor_count` | IMPLEMENTED | C21, C32, C30, C27, C49, C45, C46, C47, C40, C43, C42, C41, C44, T08, T27, T30, T31, T33, T32, T29, T38 |
| BEH-036 | capabilities/motor_count_unknown_reason. `S#/protocols/0/capabilities/motor_count_unknown_reason` | IMPLEMENTED | C21, C32, C30, C27, C49, C45, C46, C47, C40, C43, C42, C41, C44, T08, T27, T30, T31, T33, T32, T29, T38 |
| BEH-037 | capabilities/presets. `S#/protocols/0/capabilities/presets` | IMPLEMENTED | C21, C32, C30, C27, C16, C14, C15, C10, C49, T08, T27, T30 |
| BEH-038 | capabilities/save. `S#/protocols/0/capabilities/save` | IMPLEMENTED | C21, C32, C30, C27, C20, C34, C29, C49, T08, T27, T07, T30 |
| BEH-039 | capabilities/massage. `S#/protocols/0/capabilities/massage` | IMPLEMENTED | C21, C32, C30, C27, C13, C49, T08, T27, T30 |
| BEH-040 | capabilities/light. `S#/protocols/0/capabilities/light` | IMPLEMENTED | C21, C32, C30, C27, C12, C49, C54, T08, T27, T30, T38, T35, T34 |
| BEH-041 | capabilities/alarm. `S#/protocols/0/capabilities/alarm` | IMPLEMENTED | C21, C32, C30, C27, C02, C03, C49, T08, T27, T30 |
| BEH-042 | capabilities/side_sync. `S#/protocols/0/capabilities/side_sync` | IMPLEMENTED | C21, C32, C30, C27, C05, C49, T08, T27, T30 |
| BEH-043 | capabilities/side_sync_unknown_reason. `S#/protocols/0/capabilities/side_sync_unknown_reason` | IMPLEMENTED | C21, C32, C30, C27, C05, C49, T08, T27, T30 |
| BEH-044 | capabilities/pin_authentication. `S#/protocols/0/capabilities/pin_authentication` | IMPLEMENTED | C21, C32, C30, C27, C49, C48, T08, T27, T30, T31 |
| BEH-045 | capabilities/pin_authentication_unknown_reason. `S#/protocols/0/capabilities/pin_authentication_unknown_reason` | IMPLEMENTED | C21, C32, C30, C27, C49, C48, T08, T27, T30, T31 |
| BEH-046 | capabilities/position_feedback. `S#/protocols/0/capabilities/position_feedback` | IMPLEMENTED | C21, C32, C30, C27, C04, C49, C45, C46, C47, T08, T27, T30, T31, T33, T32 |
| BEH-047 | capabilities/position_feedback_unknown_reason. `S#/protocols/0/capabilities/position_feedback_unknown_reason` | IMPLEMENTED | C21, C32, C30, C27, C04, C49, C45, C46, C47, T08, T27, T30, T31, T33, T32 |
| BEH-048 | capabilities/advanced_absence. `S#/protocols/0/capabilities/advanced_absence` | IMPLEMENTED | C21, C32, C30, C27, C49, T08, T27, T30 |
| BEH-049 | model_mappings/0. `S#/protocols/0/model_mappings/0` | IMPLEMENTED | C21, C32, C30, C27, C49, T08, T27, T30 |
| BEH-050 | model_mappings/1. `S#/protocols/0/model_mappings/1` | IMPLEMENTED | C21, C32, C30, C27, C49, T08, T27, T30 |
| BEH-051 | model_mappings/2. `S#/protocols/0/model_mappings/2` | IMPLEMENTED | C21, C32, C30, C27, C49, T08, T27, T30 |
| BEH-052 | timing/sender. `S#/protocols/0/timing/sender` | IMPLEMENTED | C31, C24, C32, C01, T21, T05, T23, T28, T36 |
| BEH-053 | timing/stop_attempts_ms. `S#/protocols/0/timing/stop_attempts_ms` | IMPLEMENTED | C24, C31, C01, C11, T03, T05, T21, T23, T04, T24, T36 |
| BEH-054 | timing/scan_timeout_s. `S#/protocols/0/timing/scan_timeout_s` | EXCLUDED | Android scan/connect callback scheduling and stale repeat/selected-destination continuation are transport/application boundaries and unsafe stale-action resumption. HA serializes, bounds and cancels operations with fresh physical-target cleanup. |
| BEH-055 | timing/connection_success_delay_ms. `S#/protocols/0/timing/connection_success_delay_ms` | EXCLUDED | Android scan/connect callback scheduling and stale repeat/selected-destination continuation are transport/application boundaries and unsafe stale-action resumption. HA serializes, bounds and cancels operations with fresh physical-target cleanup. |
| BEH-056 | timing/manufacturer_read_delay_ms. `S#/protocols/0/timing/manufacturer_read_delay_ms` | IMPLEMENTED | C36, C38, C27, T14, T18, T13, T15 |
| BEH-057 | timing/retry. `S#/protocols/0/timing/retry` | EXCLUDED | Android scan/connect callback scheduling and stale repeat/selected-destination continuation are transport/application boundaries and unsafe stale-action resumption. HA serializes, bounds and cancels operations with fresh physical-target cleanup. |
| BEH-058 | timing/lifecycle. `S#/protocols/0/timing/lifecycle` | EXCLUDED | Android scan/connect callback scheduling and stale repeat/selected-destination continuation are transport/application boundaries and unsafe stale-action resumption. HA serializes, bounds and cancels operations with fresh physical-target cleanup. |
| BEH-059 | release_behavior/touch. `S#/protocols/0/release_behavior/touch` | IMPLEMENTED | C31, C24, C32, C01, T21, T05, T23, T28, T36 |
| BEH-060 | release_behavior/voice. `S#/protocols/0/release_behavior/voice` | EXCLUDED | Speech recognition phrases and uncancelled Android pending-stop queues are UI/safety boundaries. Reachable voice-only BLE commands and their bounded500ms/1500ms actions remain implemented in command rows; unbounded movement and stale queued stops are not replayed. |
| BEH-061 | release_behavior/guarantee. `S#/protocols/0/release_behavior/guarantee` | IMPLEMENTED | C31, C24, C32, C01, T21, T05, T23, T28, T36 |
| NOTIFY-001 | Ignored short message. `S#/protocols/0/notifications/0` | IMPLEMENTED | C22, C28, C35, C51, C50, T26, T12, T25, T22, T02, T16, T39, T37 |
| NOTIFY-002 | Alarm reply. `S#/protocols/0/notifications/1` | IMPLEMENTED | C22, C28, C35, C51, C50, T26, T12, T25, T22, T02, T16, T39, T37 |
| FIELD-001 | Alarm reply/repeat. `S#/protocols/0/notifications/1/fields/repeat` | IMPLEMENTED | C22, C28, C35, C51, C50, T26, T12, T25, T22, T02, T16, T39, T37 |
| FIELD-002 | Alarm reply/type. `S#/protocols/0/notifications/1/fields/type` | IMPLEMENTED | C22, C28, C35, C51, C50, T26, T12, T25, T22, T02, T16, T39, T37 |
| FIELD-003 | Alarm reply/hour. `S#/protocols/0/notifications/1/fields/hour` | IMPLEMENTED | C22, C28, C35, C51, C50, T26, T12, T25, T22, T02, T16, T39, T37 |
| FIELD-004 | Alarm reply/minute. `S#/protocols/0/notifications/1/fields/minute` | IMPLEMENTED | C22, C28, C35, C51, C50, T26, T12, T25, T22, T02, T16, T39, T37 |
| FIELD-005 | Alarm reply/on. `S#/protocols/0/notifications/1/fields/on` | IMPLEMENTED | C22, C28, C35, C51, C50, T26, T12, T25, T22, T02, T16, T39, T37 |
| NOTIFY-003 | Other status. `S#/protocols/0/notifications/2` | IMPLEMENTED | C22, C28, C35, C51, C50, T26, T12, T25, T22, T02, T16, T39, T37 |
| FIELD-006 | Other status/status. `S#/protocols/0/notifications/2/fields/status` | IMPLEMENTED | C22, C28, C35, C51, C50, T26, T12, T25, T22, T02, T16, T39, T37 |
| FIELD-007 | Other status/massage_time. `S#/protocols/0/notifications/2/fields/massage_time` | IMPLEMENTED | C22, C28, C35, C51, C50, T26, T12, T25, T22, T02, T16, T39, T37 |
| NOTIFY-004 | Manufacturer read. `S#/protocols/0/notifications/3` | IMPLEMENTED | C36, C38, C27, T14, T18, T13, T15 |
| SAFE-001 | Android touch pointer-mask replay and callback lifetime. `S#/protocols/0/release_behavior` | EXCLUDED | Only enumerated switch cases issue commands; unmatched remote masks do not establish arbitrary simultaneous motor combinations. HA exposes each proven endpoint/chord directly and does not synthesize unsafe multi-pointer ownership races. |
| SAFE-002 | Repeater survives disconnect or selected-device replacement. `S#/protocols/0/timing/lifecycle` | EXCLUDED | Android sendCmd may resume a stale held action on a newly selected physical destination; HA excludes this unsafe application state and ties cleanup to the configured physical target. |
| SAFE-003 | Null callbacks, global device-status leakage and local save success. `S#/protocols/0/notifications/2` | EXCLUDED | Android callback null dereference and global cross-device cache/UI toast ownership are application/safety boundaries. Signed status/timer fields, change-only guards and pending-save routing remain retained; save notification is not hardware-confirmed storage. |
| EXP-001 | Manufacturer read after connection and on information refresh. `S#/protocols/0/gatt/information_read` | IMPLEMENTED | C36, C38, C27, T14, T18, T13, T15 |
| EXP-002 | Notification subscription required independently of angle sensing. `S#/protocols/0/gatt/notify` | IMPLEMENTED | C37, C26, C38, T18, T08, T09, T17 |
| EXP-003 | Flat+ZG/M1/TV/M2 save chords start immediately; five-second bound help gesture, no hardware threshold. `S#/protocols/0/commands/13` | IMPLEMENTED | C18, C19, C31, C20, C34, C29, C01, C08, C23, T03, T20, T06, T25, T22, T02, T16, T07 |

## Validation boundary

The accepted APK report proves shipped application behavior. The comparison checks all 45 action rows, all 39 transport/candidate entries, all seven inventory entries, every GATT/configuration/capability/timing/release claim and each notification/parser field. Four dead clock/alarm test vectors remain excluded with their dead builder routes. Physical actuator identity, storage outcomes and ATT/hardware compatibility remain deferred to real users after release.

The independent implementation audit compares 86016 notification/parser cases against the frozen package reproducer and verifies latency-sensitive release pacing. Focused controller, configuration, service, entity lifecycle and production scheduler validation passes; repository validation and PR checks are recorded with the integration change.
