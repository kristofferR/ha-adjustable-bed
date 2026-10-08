# S02 Sleeptracker implementation dispositions

Implementation candidate for the full standalone work unit, ready for independent convergence review. This ledger covers every accepted candidate, selector and command row. Hardware verification is separate from artifact proof. No raw artifact, decompilation, audit report or reproducer is committed.

## Frozen evidence identity

- Package `com.fullpower.applications.horizon`, version **3.6.2 (262)**, complete Google Play base plus density split, acquired 2026-10-08.
- Artifact-set digest `b59b82da218fd1bb7082e5a3b6d096541d7e6377d82c535cf531995f163d3ea5`.
- `report/REPORT.SHA256` digest `e41daa1dc5bd0a1c89154f0ba19fdc056cf09c2d846b1ae19b6448b48a184749`.
- `report/analysis.json` digest `5ba72aeb3d6e476aa53a9af9744a7e4cbb999bc0d080f815e75331a9102304c8`.
- Independent audit **ACCEPT**, all 17 gates pass, no material findings; `work/audit-001/AUDIT.SHA256` digest `97071200b1f893e13e339faebb7e6b5369494dcb7b9fda9c8e8131b23d3d606f`.
- All references below resolve inside the immutable local workspace `disassembly/output/phase4-early/com.fullpower.applications.horizon-3.6.2-2026-10-08/`. `E##` are that report's evidence IDs; the source after `@` is the exact accepted coordinate. The frozen analysis header predates audit acceptance; the separate audit supplies the acceptance decision. Hashes and manifest members were verified before comparison.

- Scoped missing-state addendum independently ACCEPTED: 13 discoveries, manifest `36c07b6237104be8b18d270e20ace923632eca171984837db879f7340f35e841`; discovery digest `bf2e70a13305bb374fba256725d0a386de44972e324aace6dbf1e6992a5f16e0`; independent audit digest `7d0c8a813a16563f518d3a480fc76df6f4bbc085ddaf50fd74b63e091d071154`. Original report bytes remain unchanged. `ADD/D##` refers to exact method-hashed discoveries in that addendum.

## Accounting

The **238 canonical candidates** have exactly one disposition each: **109 IMPLEMENTED**, **10 ALREADY_IMPLEMENTED**, **119 EXCLUDED**. They include all **102 selectors/actions** and all **102 transport callsites**. The separate **42-command crosswalk** is an alias index, not additional discoveries.

Another **27 explicit sub-dispositions** separate audio from mixed sequences/parsers and document HA safety/lifecycle differences and state reporting. Including these, **265 ledger items** have **114 IMPLEMENTED**, **10 ALREADY_IMPLEMENTED**, **141 EXCLUDED**. None is deferred implementation debt.

The previous additional `HA/REPORTED_UART_PRESETS` row was an integration compatibility credit, not a discovery from this APK. It is retired after the user requested removal of the local workaround and PR671 massage extension. All 238 artifact discovery dispositions and all 141 exclusions are unchanged.

`IMPLEMENTED` refers to the local bed behavior in its reference group, with mixed-candidate excluded behaviors separately enumerated. `ALREADY_IMPLEMENTED` requires the exact existing code and tests linked below. `EXCLUDED` has a positive source-backed boundary or safety reason; lack of maintainer hardware is never its reason. Groups provide the concrete code/test references for each row. An excluded behavior deliberately has no new runtime handler or deletion-only test.

## Implementation and validation references

### discovery

Unique processor service and exact characteristic verification; manufacturer flags/model/version and target-match metadata. No name-only UART reassignment.

Code: [custom_components/adjustable_bed/detection.py](../../../custom_components/adjustable_bed/detection.py) `detect_bed_type_detailed`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `async_discover_capabilities`; [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `manufacturer_metadata`.

Tests: [tests/test_sleeptracker_exposure.py](../../../tests/test_sleeptracker_exposure.py) `test_unique_processor_service_wins_without_reclassifying_uart`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_wrong_service_cannot_send_json_to_uart`; [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_manufacturer_fields_are_metadata_not_axis_decoders`.

### session

Hello/auth/control subscriptions and same-channel reads; optional raw firmware revision; explicit restricted route. Only roles used by the selected session are required.

Code: [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `start_notify`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `async_discover_capabilities`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `_read`.

Tests: [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_authenticated_handshake_and_transport_bounded_frames`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_restricted_route_does_not_require_unused_auth_or_firmware_read`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_first_service_precedence_is_not_fallback_after_missing_channels`.

### auth

Fresh-salt bcrypt 2a/cost 10, uppercase configured MAC plus challenge, Base64 hash, literal client ID, token in memory only.

Code: [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `authentication`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `start_notify`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `on_disconnect`.

Tests: [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_authentication_fixed_salt_accepted_vector`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_explicit_write_cancel_releases_all_and_reauthenticates`.

### frame

Little-endian length/first/last grammar, zero outgoing sequence, per-channel reassembly, read continuation, negotiated-transport-safe fragment capacity.

Code: [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `frames`; [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `Reassembler`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `_write`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `_continue_read`.

Tests: [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_frames_reassemble_with_transport_capacity`; [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_malformed_or_orphan_frames_are_rejected`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_read_continuation_uses_same_channel`.

### format

Regular ordered pretty and compact envelopes, omission of absent tokens/request. Trusted values match the artifact; untrusted strings are escaped safely.

Code: [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `pretty`; [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `envelope`.

Tests: [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_movement_and_release_exact_pretty_wire`; [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_untrusted_token_is_escaped_instead_of_copying_formatter_bug`.

### movement

Head/back, foot/legs and layout-gated lumbar increment/release with ticks 4; no position feedback. Reply-driven holds have guaranteed cleanup attempts.

Code: [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `movement`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `_move`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `_release`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `motor_control_specs`.

Tests: [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_movement_and_release_exact_pretty_wire`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_movement_release_ignores_cancel_and_discards_late_session`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_missing_movement_reply_still_releases_within_hold_budget`.

### preset

All six named recall builders and five save builders, separate motor-control envelope; exact layout capacity and processor save gates.

Code: [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `preset`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `validate_sleeptracker_request`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `preset_memory`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `controller_button_specs`.

Tests: [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_preset_recall_and_separate_save`; [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_exact_layout_gates`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_saving_disabled_only_for_exact_processor_type`.

### massage

Pattern, head/foot step, 28Hz/40Hz, selected-unit massage/all stop, wind-down modes 1/2. Standard buttons plus typed actions.

Code: [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `massage`; [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `stop`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `async_execute_sleeptracker_request`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `massage_off`.

Tests: [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_massage_frequency_and_zone_wire`; [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_selected_unit_stop_wire`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_wind_down_mode_does_not_invent_a_countdown_parameter`; [tests/test_sleeptracker_exposure.py](../../../tests/test_sleeptracker_exposure.py) `test_public_actions_execute_through_coordinator`.

### climate

Left/right/both complete fan field groups, side 0, levels 0–3, heat/cool/constant/curve and fixed 3600/36000 timers. No fabricated countdown readback.

Code: [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `fan`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `async_execute_sleeptracker_request`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `controller_select_specs`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `controller_number_specs`.

Tests: [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_breeze_complete_field_groups`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_service_and_entity_climate_model_gates`; [tests/test_sleeptracker_exposure.py](../../../tests/test_sleeptracker_exposure.py) `test_all_receivers_preflight_before_first_climate_write`.

### wave

Five exact frequency-to-pulse values, 500 ms second-statement delay, minutes*600 duration and local finite selectors.

Code: [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `wave`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `controller_select_specs`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `controller_number_specs`.

Tests: [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_relaxation_wave`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_number_callbacks_reject_fractional_or_unsupported_values`; [tests/test_sleeptracker_exposure.py](../../../tests/test_sleeptracker_exposure.py) `test_platform_entities_route_actions_and_show_only_published_state`.

### animation

Six motor/massage statements from the shipped sequence retain order, fields and each local delay. Six audio statements are separately excluded; no claim of media timing equivalence.

Code: [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `local_animation`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `async_execute_sleeptracker_request`.

Tests: [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_local_sequence_independent_audio_disposition`.

### light

Normal selected-unit safety-light toggle, restricted bare toggle/off, four reply-driven local identification commands and literal side-1 split identification with explicit off cleanup.

Code: [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `light`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `async_execute_sleeptracker_request`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `controller_button_specs`.

Tests: [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_restricted_session_and_explicit_light_route`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_identify_cancellation_sends_literal_light_off`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_local_identification_uses_four_response_driven_bare_lights_and_cleanup`.

### state

One/two/other snapshot remote rules, raw strengths/pattern/light, separate single-snapshot fan parser and disconnect invalidation. Audio feedback has its own exclusion.

Code: [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `status`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `_update_status`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `_publish`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `on_disconnect`.

Tests: [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_remote_and_climate_parser_rules_stay_distinct`; [tests/test_sleeptracker_exposure.py](../../../tests/test_sleeptracker_exposure.py) `test_platform_entities_route_actions_and_show_only_published_state`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_late_read_cannot_restore_disconnected_state`.

### model

Nine persisted layouts, independent hello aliases, explicit unit/snapshot/type/foundation selectors and per-physical-side ownership. No bit-to-axis or physical unit-side inference.

Code: [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `MODELS`; [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `HELLO_MODELS`; [custom_components/adjustable_bed/config_flow.py](../../../custom_components/adjustable_bed/config_flow.py) `_add_sleeptracker_schema_fields`; [custom_components/adjustable_bed/app_profiles.py](../../../custom_components/adjustable_bed/app_profiles.py) `SLEEPTRACKER_CONFIG_KEYS`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `protocol_diagnostics`.

Tests: [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_exact_layout_gates`; [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_hello_aliases_are_independent_of_persisted_slim_ids`; [tests/test_sleeptracker_exposure.py](../../../tests/test_sleeptracker_exposure.py) `test_every_setup_route_collects_processor_profile`; [tests/test_sleeptracker_exposure.py](../../../tests/test_sleeptracker_exposure.py) `test_profile_owns_selectors_and_options_keep_product`.

### metadata

Whitelisted hello identity/capability metadata and raw sensor bits, status/sample range, normal and optional setup sensor counts; invariant model/version comparison and four firmware thresholds are diagnostic only.

Code: [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `_parse_hello`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `_update_status`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `protocol_diagnostics`.

Tests: [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_metadata_preserves_optional_sensor_count_rule_and_firmware_ui_gates`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_authenticated_handshake_and_transport_bounded_frames`.

### lifecycle

Serialized reply transactions, 60-second reply ceiling, cancellation/release and generation checks; ambiguous sessions close rather than accepting a late reply as a new acknowledgement.

Code: [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `_exchange`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `_release`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `_accept`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `on_disconnect`.

Tests: [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_movement_release_ignores_cancel_and_discards_late_session`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_reply_timeout_releases_and_closes_ambiguous_session`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_old_callbacks_are_ignored_after_disconnect`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_late_read_cannot_restore_disconnected_state`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_identification_final_off_validates_reply_before_session_reuse`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_empty_startup_reply_closes_session`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_empty_control_reply_releases_without_acknowledged_state`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_nonempty_partial_reply_remains_valid`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_consecutive_fragmented_replies_with_eager_ha_task_creation`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_cancelled_old_continuation_cannot_remove_new_generation_task`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_early_transport_timeout_reaches_caller_after_axis_release`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_local_hold_expiry_is_successful_and_releases`.

### exposure

Finite typed public actions, all-target preflight, shared two-address side routing, entities, English labels and existing card buckets.

Code: [custom_components/adjustable_bed/sleeptracker_services.py](../../../custom_components/adjustable_bed/sleeptracker_services.py) `handle_sleeptracker`; [custom_components/adjustable_bed/sleeptracker_services.py](../../../custom_components/adjustable_bed/sleeptracker_services.py) `async_register_sleeptracker_services`; [custom_components/adjustable_bed/beds/base.py](../../../custom_components/adjustable_bed/beds/base.py) `supports_sleeptracker_controls`; [custom_components/adjustable_bed/frontend/src/discovery.ts](../../../custom_components/adjustable_bed/frontend/src/discovery.ts) `sleeptracker_`.

Tests: [tests/test_sleeptracker_exposure.py](../../../tests/test_sleeptracker_exposure.py) `test_public_actions_execute_through_coordinator`; [tests/test_sleeptracker_exposure.py](../../../tests/test_sleeptracker_exposure.py) `test_two_address_service_targets_only_the_selected_physical_processor`; [tests/test_sleeptracker_exposure.py](../../../tests/test_sleeptracker_exposure.py) `test_service_selectors_match_the_finite_action_schemas`; [tests/test_sleeptracker_exposure.py](../../../tests/test_sleeptracker_exposure.py) `test_every_generated_entity_has_english_translation`.

### privacy

Challenge/token/password and raw hello/auth/control capture redaction; no secret persistence, payload logging or diagnostic token.

Code: [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `_format_command_trace_payload`; [custom_components/adjustable_bed/redaction.py](../../../custom_components/adjustable_bed/redaction.py) `redact_sleeptracker_sessions`; [custom_components/adjustable_bed/ble_diagnostics.py](../../../custom_components/adjustable_bed/ble_diagnostics.py) `SLEEPTRACKER_SECRET_CHARACTERISTICS`.

Tests: [tests/test_sleeptracker_exposure.py](../../../tests/test_sleeptracker_exposure.py) `test_secrets_redacted_in_captures_and_structured_diagnostics`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_authenticated_handshake_and_transport_bounded_frames`.

### infra

Existing HA/Bleak connection, service discovery and disconnect ownership provides the corresponding BLE lifecycle. Android API implementation details are not copied.

Code: [custom_components/adjustable_bed/coordinator.py](../../../custom_components/adjustable_bed/coordinator.py) `_async_connect_attempts_locked`; [custom_components/adjustable_bed/coordinator.py](../../../custom_components/adjustable_bed/coordinator.py) `async_disconnect`.

Tests: [tests/test_coordinator.py](../../../tests/test_coordinator.py) `test_connect_success`; [tests/test_coordinator.py](../../../tests/test_coordinator.py) `test_disconnect`.

### wind_down

Accepted scoped addendum D05-D10/D12: only details.body snapshots; first non-null snapshot numeric mode with default/range rules, no ordinal filter; absent/empty retain, initially/disconnected unknown. Later ordinary scalar snapshots cannot invalidate the independent running state; retain the last remote/climate values when their consumer cannot parse those entries. Malformed consumed structures still reject. The response boundary recursively validates every raw key/value pair before duplicate merging, rejecting nonadvancing nested arrays even in discarded unused fields. Every awaited exchange returns a validated object; final identification off cannot bypass decoding or taint cleanup. Null object fields are skipped, including duplicate-null keys. Premium translated binary state is displayed in the card.

Code: [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `wind_down_running`; [custom_components/adjustable_bed/sleeptracker_protocol.py](../../../custom_components/adjustable_bed/sleeptracker_protocol.py) `_non_null_fields`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `_update_status`; [custom_components/adjustable_bed/beds/sleeptracker.py](../../../custom_components/adjustable_bed/beds/sleeptracker.py) `controller_state_binary_sensor_specs`.

Tests: [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_wind_down_first_snapshot_numeric_rule`; [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_wind_down_absent_snapshots_are_not_stop_proof`; [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_wind_down_uses_first_non_null_snapshot_without_side_filter`; [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_reply_parser_skips_null_fields_including_duplicate_keys`; [tests/test_sleeptracker_exposure.py](../../../tests/test_sleeptracker_exposure.py) `test_platform_entities_route_actions_and_show_only_published_state`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_duplicate_key_reply_cannot_publish_acknowledged_state`; [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_reply_parser_validates_discarded_duplicate_values`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_nested_array_reply_cannot_publish_acknowledged_state`; [tests/test_sleeptracker_protocol.py](../../../tests/test_sleeptracker_protocol.py) `test_reply_parser_rejects_nonadvancing_nested_arrays`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_wind_down_transaction_ignores_unconsumed_later_scalar`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_wind_down_transaction_rejects_malformed_consumed_shapes`; [tests/test_sleeptracker_controller.py](../../../tests/test_sleeptracker_controller.py) `test_nonpremium_remote_rejects_scalar_snapshots`; [custom_components/adjustable_bed/frontend/src/discovery.test.ts](../../../custom_components/adjustable_bed/frontend/src/discovery.test.ts) `a Sleeptracker reported-state-only registry surface is not empty`.

## Exclusion reasons

### excluded-audio

Speaker/audio/synchronization and soundscape feedback are outside the canonical direct-BLE product boundary, even when packets are local BLE.

### excluded-network

Wi-Fi AP listing, SSID/password/configuration, network administration and reboot are outside direct BLE bed control.

### excluded-cloud

HTTP/WebSocket, accounts, cloud, sleep and alarm-only infrastructure use an excluded product/transport boundary.

### excluded-media

Remote help/coaching, WebView keyboard and media playback are unrelated to local bed controls. Local motor/massage statements are separately implemented.

### excluded-dfu

Firmware archives, DFU providers and update lifecycle are outside direct BLE bed control.

### excluded-dead

Accepted reachability analysis proves this mapping, unused channel/UUID or prototype/stage route has no shipped caller or assigned role.

### excluded-android

Android-only scanner scheduling/flush, successful-address autoConnect caching, LE transport selection, adapter factory and process singleton mechanics belong to the app runtime. App scan/flush timing and OS settings are not hardware command requirements. HA owns scanning, adapter selection and connection lifecycle.

### excluded-descriptors

Blind 01 00 writes to every descriptor are unsafe without a CCCD UUID check. Bleak owns standard notification setup; no arbitrary descriptor write is introduced.

### excluded-rssi

App RSSI polling/readiness thresholds are UI policy, not a proven hardware requirement. Existing HA advertisements provide RSSI diagnostics.

### excluded-bond

Automatic destructive host bond removal is excluded for safety. Normal control proves no createBond/PIN requirement; existing explicit HA bond management remains available.

### excluded-version

App firmware/update UI gates, RLB 6.1.56 comparison quirks and setup blocking are not proven device requirements. Raw versions and controller thresholds remain diagnostic.

### excluded-classic

No app-owned Bluetooth Classic bed-control transport is established; third-party SDK/Binder references do not define a protocol.

### excluded-unsafe_json

The unescaped/truncated formatter corrupts untrusted strings. HA emits valid escaped JSON with the same trusted-value grammar.

### excluded-unsafe_ad

Malformed AD zero-padding, partial stale fields and ignored incomplete UUID lists are app parser quirks. HA/Bleak owns well-formed advertisements; no malformed input is used to select a bed.

### excluded-unsafe_session

Shared cross-channel buffers, stale mutable dispatch state, descriptor semaphore hangs and ten immediate API retries can misattribute replies or duplicate side effects. HA isolates channels, serializes awaited writes and closes ambiguous sessions.

### excluded-timing_ui

Android navigation/images/spinners, gesture/vibration/confirmation and UI countdown mechanics do not change the packet. HA uses explicit save actions and finite local selectors; no timer bytes are invented.

### excluded-identity

Persisting processor MAC/serial or challenge/token secrets is unnecessary for local control. Configured address identifies the target, while credentials stay ephemeral and raw captures are redacted.

### excluded-flags

The app XOR of two persisted simulation flags is an app preference implementation. HA exposes the same effective restricted route as one explicit option, never an automatic fallback.

### excluded-inference

No accepted decoder proves physical axes from bitfields, unit-to-half mapping or target position feedback. HA does not invent those semantics or single-address pairing.

## Canonical discovery ledger

| Accepted ID | Disposition | Behavior and concrete references | Exact accepted source |
|-------------|-------------|----------------------------------|-----------------------|
| `V/action:ANTI_SNORE` | `IMPLEMENTED` | [preset](#preset) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:DEBUG_SNORE_1` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:DEBUG_SNORE_2` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:FLAT` | `IMPLEMENTED` | [preset](#preset) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:FOOT_DOWN` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:FOOT_DOWN_INCREMENT` | `IMPLEMENTED` | [movement](#movement) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:FOOT_STOP` | `IMPLEMENTED` | [movement](#movement) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:FOOT_UP` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:FOOT_UP_INCREMENT` | `IMPLEMENTED` | [movement](#movement) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:HEAD_DOWN` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:HEAD_DOWN_INCREMENT` | `IMPLEMENTED` | [movement](#movement) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:HEAD_STOP` | `IMPLEMENTED` | [movement](#movement) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:HEAD_TILT_DOWN` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:HEAD_TILT_DOWN_INCREMENT` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:HEAD_TILT_STOP` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:HEAD_TILT_UP` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:HEAD_TILT_UP_INCREMENT` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:HEAD_UP` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:HEAD_UP_INCREMENT` | `IMPLEMENTED` | [movement](#movement) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:HZ_MASSAGE_28` | `IMPLEMENTED` | [massage](#massage) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:HZ_MASSAGE_40` | `IMPLEMENTED` | [massage](#massage) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:LUMBAR_DOWN` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:LUMBAR_DOWN_INCREMENT` | `IMPLEMENTED` | [movement](#movement) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:LUMBAR_STOP` | `IMPLEMENTED` | [movement](#movement) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:LUMBAR_UP` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:LUMBAR_UP_INCREMENT` | `IMPLEMENTED` | [movement](#movement) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:MASSAGE_FOOT` | `IMPLEMENTED` | [massage](#massage) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:MASSAGE_HEAD` | `IMPLEMENTED` | [massage](#massage) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:MASSAGE_OFF` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:MASSAGE_ON` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:MASSAGE_PATTERN_STEP` | `IMPLEMENTED` | [massage](#massage) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:PROGRAM_ANTI_SNORE` | `IMPLEMENTED` | [preset](#preset) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:PROGRAM_FAVORITE` | `IMPLEMENTED` | [preset](#preset) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:PROGRAM_FAVORITE_2` | `IMPLEMENTED` | [preset](#preset) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:PROGRAM_TV_POSITION` | `IMPLEMENTED` | [preset](#preset) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:PROGRAM_ZERO_G` | `IMPLEMENTED` | [preset](#preset) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:REQUEST_STATUS` | `IMPLEMENTED` | [state](#state) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:START_SPEAKER_SYNC` | `EXCLUDED` | [audio](#excluded-audio) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:START_WIND_DOWN_1` | `IMPLEMENTED` | [massage](#massage) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:START_WIND_DOWN_2` | `IMPLEMENTED` | [massage](#massage) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:STOP_ALL` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:STOP_EVERYTHING` | `IMPLEMENTED` | [massage](#massage) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:STOP_EVERYTHING_ALL` | `IMPLEMENTED` | [massage](#massage) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:STOP_MASSAGERS` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:STOP_SPEAKER_SYNC` | `EXCLUDED` | [audio](#excluded-audio) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:TOGGLE_MASSAGE` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:TOGGLE_SAFETY_LIGHTS` | `IMPLEMENTED` | [light](#light) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:TOGGLE_SPEAKER_SYNC` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:TOGGLE_TIMER` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:TV_POSITION` | `IMPLEMENTED` | [preset](#preset) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:USER_FAVORITE` | `IMPLEMENTED` | [preset](#preset) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:USER_FAVORITE_2` | `IMPLEMENTED` | [preset](#preset) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/action:ZERO_G` | `IMPLEMENTED` | [preset](#preset) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/actrack/a.java:160-227` |
| `V/controller:ERGO` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:108-162` |
| `V/controller:ERGO_ACTIVE_BREEZE_LARGE` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:108-162` |
| `V/controller:ERGO_ACTIVE_BREEZE_SMALL` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:108-162` |
| `V/controller:ERGO_PROSMART` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:108-162` |
| `V/controller:ERGO_SMART` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:108-162` |
| `V/controller:SLIM` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:108-162` |
| `V/controller:SLIM_PROSMART` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:108-162` |
| `V/controller:SLIM_SMART` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:108-162` |
| `V/controller:UNKNOWN` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:108-162` |
| `V/dfu:CB05BF` | `EXCLUDED` | [dfu](#excluded-dfu) | E15, E20, E21, E29, E33 @ `work/jadx/sources/y6/g.java:firmware mapping` |
| `V/dfu:CB05SF` | `EXCLUDED` | [dfu](#excluded-dfu) | E15, E20, E21, E29, E33 @ `work/jadx/sources/y6/g.java:firmware mapping` |
| `V/dfu:KSBF` | `EXCLUDED` | [dfu](#excluded-dfu) | E15, E20, E21, E29, E33 @ `work/jadx/sources/y6/g.java:firmware mapping` |
| `V/dfu:KSBT03C2` | `EXCLUDED` | [dfu](#excluded-dfu) | E15, E20, E21, E29, E33 @ `work/jadx/sources/y6/g.java:firmware mapping` |
| `V/dfu:KSBT05C2` | `EXCLUDED` | [dfu](#excluded-dfu) | E15, E20, E21, E29, E33 @ `work/jadx/sources/y6/g.java:firmware mapping` |
| `V/dfu:KSSF` | `EXCLUDED` | [dfu](#excluded-dfu) | E15, E20, E21, E29, E33 @ `work/jadx/sources/y6/g.java:firmware mapping` |
| `V/foundation:CalKing` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Station.java:108-118` |
| `V/foundation:Full` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Station.java:108-118` |
| `V/foundation:King` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Station.java:108-118` |
| `V/foundation:NonTouchingTwins` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Station.java:108-118` |
| `V/foundation:Queen` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Station.java:108-118` |
| `V/foundation:SplitKing` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Station.java:108-118` |
| `V/foundation:Twin` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Station.java:108-118` |
| `V/foundation:Unspecified` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Station.java:108-118` |
| `V/hello-model:ACTIVE_BREEZE_BIG` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:139-162` |
| `V/hello-model:ACTIVE_BREEZE_SMALL` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:139-162` |
| `V/hello-model:BEST` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:139-162` |
| `V/hello-model:BETTER` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:139-162` |
| `V/hello-model:GOOD` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:139-162` |
| `V/hello-model:NONE` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:139-162` |
| `V/hello-model:SLIM_BEST` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:139-162` |
| `V/hello-model:SLIM_BETTER` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:139-162` |
| `V/hello-model:SLIM_GOOD` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:139-162` |
| `V/layout:prototype` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/RemoteControl.java:1389-1428` |
| `V/package:stage` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/applications/horizon/f.java:310-320` |
| `V/platform:Android` | `EXCLUDED` | [android](#excluded-android) | E15, E20, E21, E29, E33 @ `work/jadx/sources/w7/i.java:6-39` |
| `V/platform:None` | `EXCLUDED` | [dead](#excluded-dead) | E15, E20, E21, E29, E33 @ `work/jadx/sources/w7/i.java:6-39` |
| `V/processor:ERGOZ` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Station.java:140-149` |
| `V/processor:LUXOR` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Station.java:140-149` |
| `V/processor:NON_CONSUMER` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Station.java:140-149` |
| `V/processor:SLEEPZ` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Station.java:140-149` |
| `V/processor:TMONITOR` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Station.java:140-149` |
| `V/processor:TMONITOR_BLE` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Station.java:140-149` |
| `V/processor:UNKNOWN` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Station.java:140-149` |
| `V/session:authenticated` | `IMPLEMENTED` | [auth](#auth) | E15, E20, E21, E29, E33 @ `work/jadx/sources/y6/m.java:450-489` |
| `V/session:restricted` | `IMPLEMENTED` | [session](#session) | E15, E20, E21, E29, E33 @ `work/jadx/sources/y6/m.java:450-489` |
| `V/side:ENTIRE_BED` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Sensor.java:enum b` |
| `V/side:LOC_LEFT` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Sensor.java:enum b` |
| `V/side:LOC_RIGHT` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Sensor.java:enum b` |
| `V/side:OTHER` | `IMPLEMENTED` | [model](#model) | E15, E20, E21, E29, E33 @ `work/jadx/sources/com/fullpower/smartbed/flan/dao/Sensor.java:enum b` |
| `T001` | `EXCLUDED` | [android](#excluded-android) | E37 @ `work/smali/base/smali/com/fullpower/bandwireless/android/AndroidBLEDeviceManager.smali:1151` |
| `T002` | `EXCLUDED` | [android](#excluded-android) | E37 @ `work/smali/base/smali/com/fullpower/bandwireless/android/AndroidBLEDeviceManager.smali:1266` |
| `T003` | `EXCLUDED` | [android](#excluded-android) | E37 @ `work/smali/base/smali/com/fullpower/bandwireless/android/AndroidBLEDeviceManager.smali:1276` |
| `T004` | `ALREADY_IMPLEMENTED` | [infra](#infra) | E37 @ `work/smali/base/smali/com/fullpower/bandwireless/android/AndroidBLEDeviceManager.smali:1474` |
| `T005` | `ALREADY_IMPLEMENTED` | [infra](#infra) | E37 @ `work/smali/base/smali/com/fullpower/bandwireless/android/AndroidBLEDeviceManager.smali:1518` |
| `T006` | `ALREADY_IMPLEMENTED` | [infra](#infra) | E37 @ `work/smali/base/smali/com/fullpower/bandwireless/android/AndroidBLEDeviceManager.smali:1624` |
| `T007` | `ALREADY_IMPLEMENTED` | [infra](#infra) | E37 @ `work/smali/base/smali/com/fullpower/bandwireless/android/AndroidBLEDeviceManager.smali:1633` |
| `T008` | `ALREADY_IMPLEMENTED` | [infra](#infra) | E37 @ `work/smali/base/smali/com/fullpower/bandwireless/android/AndroidBLEDeviceManager.smali:1650` |
| `T009` | `EXCLUDED` | [android](#excluded-android) | E37 @ `work/smali/base/smali/com/fullpower/bandwireless/android/AndroidBLEDeviceManager.smali:1889` |
| `T010` | `EXCLUDED` | [android](#excluded-android) | E37 @ `work/smali/base/smali/com/fullpower/bandwireless/android/AndroidBLEDeviceManager.smali:1899` |
| `T011` | `ALREADY_IMPLEMENTED` | [infra](#infra) | E37 @ `work/smali/base/smali/x7/a.smali:247` |
| `T012` | `ALREADY_IMPLEMENTED` | [infra](#infra) | E37 @ `work/smali/base/smali/x7/a.smali:305` |
| `T013` | `EXCLUDED` | [dead](#excluded-dead) | E37 @ `work/smali/base/smali/x7/a.smali:680` |
| `T014` | `EXCLUDED` | [dead](#excluded-dead) | E37 @ `work/smali/base/smali/x7/a.smali:691` |
| `T015` | `EXCLUDED` | [dead](#excluded-dead) | E37 @ `work/smali/base/smali/x7/a.smali:702` |
| `T016` | `EXCLUDED` | [dead](#excluded-dead) | E37 @ `work/smali/base/smali/x7/a.smali:713` |
| `T017` | `IMPLEMENTED` | [session](#session) | E37 @ `work/smali/base/smali/x7/a.smali:724` |
| `T018` | `IMPLEMENTED` | [session](#session) | E37 @ `work/smali/base/smali/x7/a.smali:735` |
| `T019` | `IMPLEMENTED` | [session](#session) | E37 @ `work/smali/base/smali/x7/a.smali:746` |
| `T020` | `EXCLUDED` | [network](#excluded-network) | E37 @ `work/smali/base/smali/x7/a.smali:757` |
| `T021` | `IMPLEMENTED` | [session](#session) | E37 @ `work/smali/base/smali/x7/a.smali:768` |
| `T022` | `ALREADY_IMPLEMENTED` | [infra](#infra) | E37 @ `work/smali/base/smali/x7/a.smali:837` |
| `T023` | `IMPLEMENTED` | [frame](#frame) | E37 @ `work/smali/base/smali/x7/a.smali:1101` |
| `T024` | `IMPLEMENTED` | [frame](#frame) | E37 @ `work/smali/base/smali/x7/a.smali:1159` |
| `T025` | `IMPLEMENTED` | [session](#session) | E37 @ `work/smali/base/smali/x7/c.smali:233` |
| `T026` | `EXCLUDED` | [descriptors](#excluded-descriptors) | E37 @ `work/smali/base/smali/x7/c.smali:271` |
| `T027` | `EXCLUDED` | [network](#excluded-network) | E37 @ `work/smali/base/smali/x7/c.smali:345` |
| `T028` | `EXCLUDED` | [network](#excluded-network) | E37 @ `work/smali/base/smali/x7/c.smali:377` |
| `T029` | `IMPLEMENTED` | [session](#session) | E37 @ `work/smali/base/smali/x7/c.smali:451` |
| `T030` | `EXCLUDED` | [descriptors](#excluded-descriptors) | E37 @ `work/smali/base/smali/x7/c.smali:483` |
| `T031` | `IMPLEMENTED` | [session](#session) | E37 @ `work/smali/base/smali/x7/c.smali:557` |
| `T032` | `EXCLUDED` | [descriptors](#excluded-descriptors) | E37 @ `work/smali/base/smali/x7/c.smali:589` |
| `T033` | `IMPLEMENTED` | [session](#session) | E37 @ `work/smali/base/smali/x7/c.smali:663` |
| `T034` | `IMPLEMENTED` | [session](#session) | E37 @ `work/smali/base/smali/x7/c.smali:688` |
| `T035` | `EXCLUDED` | [network](#excluded-network) | E37 @ `work/smali/base/smali/x7/c.smali:695` |
| `T036` | `IMPLEMENTED` | [session](#session) | E37 @ `work/smali/base/smali/x7/c.smali:702` |
| `T037` | `IMPLEMENTED` | [session](#session) | E37 @ `work/smali/base/smali/x7/c.smali:709` |
| `T038` | `EXCLUDED` | [descriptors](#excluded-descriptors) | E37 @ `work/smali/base/smali/x7/c.smali:752` |
| `T039` | `EXCLUDED` | [rssi](#excluded-rssi) | E37 @ `work/smali/base/smali/x7/c.smali:1455` |
| `T040` | `ALREADY_IMPLEMENTED` | [infra](#infra) | E37 @ `work/smali/base/smali/x7/c.smali:1707` |
| `T041` | `ALREADY_IMPLEMENTED` | [infra](#infra) | E37 @ `work/smali/base/smali/x7/c.smali:1759` |
| `T042` | `EXCLUDED` | [descriptors](#excluded-descriptors) | E37 @ `work/smali/base/smali/x7/c.smali:1893` |
| `T043` | `IMPLEMENTED` | [session](#session) | E37 @ `work/smali/base/smali/x7/c.smali:2126` |
| `T044` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/BaseCustomDfuImpl$BaseCustomBluetoothCallback.smali:102` |
| `T045` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/BaseCustomDfuImpl$BaseCustomBluetoothCallback.smali:112` |
| `T046` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/BaseCustomDfuImpl.smali:353` |
| `T047` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/BaseCustomDfuImpl.smali:500` |
| `T048` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/BaseDfuImpl$BaseBluetoothGattCallback.smali:274` |
| `T049` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/BaseDfuImpl$BaseBluetoothGattCallback.smali:405` |
| `T050` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/BaseDfuImpl.smali:237` |
| `T051` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/BaseDfuImpl.smali:250` |
| `T052` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/BaseDfuImpl.smali:261` |
| `T053` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/BaseDfuImpl.smali:316` |
| `T054` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/BaseDfuImpl.smali:501` |
| `T055` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/BaseDfuImpl.smali:597` |
| `T056` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/BaseDfuImpl.smali:675` |
| `T057` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/BaseDfuImpl.smali:744` |
| `T058` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/BaseDfuImpl.smali:1063` |
| `T059` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/BaseDfuImpl.smali:1071` |
| `T060` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/BaseDfuImpl.smali:1635` |
| `T061` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/BaseDfuImpl.smali:2098` |
| `T062` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/ButtonlessDfuWithBondSharingImpl.smali:76` |
| `T063` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/ButtonlessDfuWithBondSharingImpl.smali:89` |
| `T064` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/ButtonlessDfuWithBondSharingImpl.smali:97` |
| `T065` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/ButtonlessDfuWithoutBondSharingImpl.smali:76` |
| `T066` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/ButtonlessDfuWithoutBondSharingImpl.smali:89` |
| `T067` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/ButtonlessDfuWithoutBondSharingImpl.smali:97` |
| `T068` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/DfuBaseService$5.smali:203` |
| `T069` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/DfuBaseService.smali:1212` |
| `T070` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/DfuBaseService.smali:1218` |
| `T071` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/DfuBaseService.smali:1273` |
| `T072` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/DfuBaseService.smali:1373` |
| `T073` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/ExperimentalButtonlessDfuImpl.smali:78` |
| `T074` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/ExperimentalButtonlessDfuImpl.smali:91` |
| `T075` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/ExperimentalButtonlessDfuImpl.smali:99` |
| `T076` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/LegacyButtonlessDfuImpl.smali:195` |
| `T077` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/LegacyButtonlessDfuImpl.smali:367` |
| `T078` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/LegacyButtonlessDfuImpl.smali:380` |
| `T079` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/LegacyButtonlessDfuImpl.smali:388` |
| `T080` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/LegacyButtonlessDfuImpl.smali:407` |
| `T081` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/LegacyDfuImpl.smali:391` |
| `T082` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/LegacyDfuImpl.smali:403` |
| `T083` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/LegacyDfuImpl.smali:657` |
| `T084` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/LegacyDfuImpl.smali:938` |
| `T085` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/LegacyDfuImpl.smali:1137` |
| `T086` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/LegacyDfuImpl.smali:1150` |
| `T087` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/LegacyDfuImpl.smali:1158` |
| `T088` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/LegacyDfuImpl.smali:1171` |
| `T089` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/LegacyDfuImpl.smali:1273` |
| `T090` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/LegacyDfuImpl.smali:1279` |
| `T091` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/SecureDfuImpl.smali:2719` |
| `T092` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/SecureDfuImpl.smali:2732` |
| `T093` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/SecureDfuImpl.smali:2740` |
| `T094` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/SecureDfuImpl.smali:2753` |
| `T095` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/a.smali:10` |
| `T096` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/b.smali:10` |
| `T097` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/internal/scanner/BootloaderScannerJB.smali:208` |
| `T098` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/internal/scanner/BootloaderScannerJB.smali:251` |
| `T099` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/internal/scanner/BootloaderScannerLollipop.smali:268` |
| `T100` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/internal/scanner/BootloaderScannerLollipop.smali:273` |
| `T101` | `EXCLUDED` | [dfu](#excluded-dfu) | E37 @ `work/smali/base/smali_classes2/no/nordicsemi/android/dfu/internal/scanner/BootloaderScannerLollipop.smali:317` |
| `T102` | `EXCLUDED` | [bond](#excluded-bond) | E37 @ `work/jadx/sources/com/fullpower/bandwireless/android/AndroidBLEDeviceManager.java:455-465` |
| `P1` | `IMPLEMENTED` | [session](#session) | E03, E07, E15 @ `work/jadx/sources/y6/m.java:709-840` |
| `NET` | `EXCLUDED` | [network](#excluded-network) | E32 @ `work/jadx/sources/com/fullpower/applications/horizon/l.java:126-153,355-368,444-446` |
| `HTTP` | `EXCLUDED` | [cloud](#excluded-cloud) | E18, E32 @ `work/jadx/sources/n7/q0.java:K()` |
| `WEB` | `EXCLUDED` | [media](#excluded-media) | E34 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/KoaWebView.java:322-327` |
| `DFU` | `EXCLUDED` | [dfu](#excluded-dfu) | E33 @ `work/jadx/sources/no/nordicsemi/android/dfu/DfuServiceProvider.java:getServiceImpl()` |
| `META` | `IMPLEMENTED` | [metadata](#metadata) | E35 @ `work/jadx/sources/com/fullpower/smartbed/flan/FLANManager.java:197-328` |
| `LIGHTSIDE` | `IMPLEMENTED` | [light](#light) | E31 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/intro_screens/SelectSideForSplitKingAutobahn.java:42-67` |
| `ANIMATION` | `IMPLEMENTED` | [animation](#animation) | E25 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/VideoPlayer.java:191-367` |
| `CLASSIC` | `EXCLUDED` | [classic](#excluded-classic) | E36 @ `work/searches/transport.txt` |
| `LEGACY_UUID` | `EXCLUDED` | [dead](#excluded-dead) | E07, E11 @ `work/jadx/sources/x7/d.java:54-74` |
| `B/FRAME` | `IMPLEMENTED` | [frame](#frame) | E09, E10 @ `work/jadx/sources/x7/a.java:49-86` |
| `B/AUTH` | `IMPLEMENTED` | [auth](#auth) | E13, E14 @ `work/jadx/sources/y6/m.java:450-488` |
| `B/PRETTY` | `IMPLEMENTED` | [format](#format) | E17, E39 @ `work/jadx/sources/com/fullpower/support/JsonDict.java:544-618` |
| `B/COMPACT` | `IMPLEMENTED` | [format](#format) | E17, E39 @ `work/jadx/sources/com/fullpower/support/JsonDict.java:408-437,600-616` |
| `B/MOVEMENT` | `IMPLEMENTED` | [movement](#movement) | E16, E18 @ `work/jadx/sources/y6/m.java:608-624` |
| `B/PRESET_SAVE` | `IMPLEMENTED` | [preset](#preset) | E16, E19 @ `work/jadx/sources/y6/m.java:626-650` |
| `B/MASSAGE` | `IMPLEMENTED` | [massage](#massage) | E16 @ `work/jadx/sources/y6/m.java:591-606` |
| `B/FAN` | `IMPLEMENTED` | [climate](#climate) | E23, E39 @ `work/jadx/sources/y6/m.java:534-565` |
| `B/WAVE` | `IMPLEMENTED` | [wave](#wave) | E24, E39 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/RelaxWaveFormStart.java:138-165,385-423` |
| `B/VIDEO` | `IMPLEMENTED` | [animation](#animation) | E25, E39 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/VideoPlayer.java:191-224,320-367` |
| `B/LIGHT_BARE` | `IMPLEMENTED` | [light](#light) | E29, E30 @ `work/jadx/sources/y6/m.java:567-590` |
| `B/LIGHT_SIDE` | `IMPLEMENTED` | [light](#light) | E31 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/intro_screens/SelectSideForSplitKingAutobahn.java:42-67` |
| `N/FRAME` | `IMPLEMENTED` | [frame](#frame) | E11, E39 @ `work/jadx/sources/x7/a.java:146-198` |
| `N/ADVERTISEMENT` | `IMPLEMENTED` | [discovery](#discovery) | E04, E06, E39 @ `work/jadx/sources/w7/a.java:106-368` |
| `N/REMOTE` | `IMPLEMENTED` | [state](#state) | E27, E39 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/RemoteControl.java:446-567` |
| `N/CLIMATE` | `IMPLEMENTED` | [state](#state) | E28, E39 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/ClimateControl.java:361-420` |
| `N/SPEAKER` | `EXCLUDED` | [audio](#excluded-audio) | E28, E39 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/RelaxSoundscapeMode.java:128-145` |
| `M/CONTROLLER` | `IMPLEMENTED` | [model](#model) | E20, E39 @ `work/jadx/sources/com/fullpower/smartbed/flan/FSPDatabase.java:108-162` |
| `M/FIRMWARE_GATE` | `IMPLEMENTED` | [metadata](#metadata) | E22, E39 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/ScreenBase.java:2297-2343` |
| `M/RLB_VERSION` | `EXCLUDED` | [version](#excluded-version) | E30, E38, E39 @ `work/jadx/sources/p7/g.java:14-71` |
| `M/SENSOR_METADATA` | `IMPLEMENTED` | [metadata](#metadata) | E35, E39 @ `work/jadx/sources/com/fullpower/smartbed/flan/FLANManager.java:217-328` |
| `L/HOLD` | `IMPLEMENTED` | [movement](#movement) | E18, E30 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/RemoteControl.java:1483-1539,1599-1630` |
| `L/TRANSACTION` | `IMPLEMENTED` | [lifecycle](#lifecycle) | E12 @ `work/jadx/sources/w7/c.java:263-324,346-425` |
| `M/PROFILE_OBJECT` | `EXCLUDED` | [dead](#excluded-dead) | E07, E08 @ `work/jadx/sources/w7/b.java:1-30` |

## Explicit sub-dispositions and HA lifecycle differences

| Item | Disposition | Behavior and concrete references | Exact accepted source |
|------|-------------|----------------------------------|-----------------------|
| `X/VIDEO_AUDIO_STATEMENT_3` | `EXCLUDED` | [audio](#excluded-audio) | E25 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/VideoPlayer.java:191-224,320-367` |
| `X/VIDEO_AUDIO_STATEMENT_4` | `EXCLUDED` | [audio](#excluded-audio) | E25 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/VideoPlayer.java:191-224,320-367` |
| `X/VIDEO_AUDIO_STATEMENT_6` | `EXCLUDED` | [audio](#excluded-audio) | E25 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/VideoPlayer.java:191-224,320-367` |
| `X/VIDEO_AUDIO_STATEMENT_7` | `EXCLUDED` | [audio](#excluded-audio) | E25 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/VideoPlayer.java:191-224,320-367` |
| `X/VIDEO_AUDIO_STATEMENT_8` | `EXCLUDED` | [audio](#excluded-audio) | E25 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/VideoPlayer.java:191-224,320-367` |
| `X/VIDEO_AUDIO_STATEMENT_10` | `EXCLUDED` | [audio](#excluded-audio) | E25 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/VideoPlayer.java:191-224,320-367` |
| `X/REMOTE_SPEAKER_STATE` | `EXCLUDED` | [audio](#excluded-audio) | E27 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/RemoteControl.java:446-567` |
| `X/PRETTY_UNTRUSTED_STRINGS` | `EXCLUDED` | [unsafe_json](#excluded-unsafe_json) | E17 @ `work/jadx/sources/com/fullpower/support/JsonDict.java:544-618` |
| `X/MALFORMED_AD` | `EXCLUDED` | [unsafe_ad](#excluded-unsafe_ad) | E04, E06 @ `work/smali/base/smali/w7/a.smali:281-1832` |
| `X/NAME_OR_STANDARD_SERVICE_ONLY_SELECTION` | `EXCLUDED` | [inference](#excluded-inference) | E05, E07 @ `work/jadx/sources/com/fullpower/bandito/WirelessDeviceFinderImpl.java:369-411,559-688` |
| `X/RSSI_UI_THRESHOLDS` | `EXCLUDED` | [rssi](#excluded-rssi) | E05, E14 @ `work/jadx/sources/y6/m.java:254-263,307-350` |
| `X/FIRMWARE_UI_ENFORCEMENT` | `EXCLUDED` | [version](#excluded-version) | E22, E30 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/ScreenBase.java:1471-1512,2297-2343` |
| `X/AUTH_EXPIRY_PERSISTENCE` | `EXCLUDED` | [identity](#excluded-identity) | E14 @ `work/jadx/sources/y6/m.java:450-511` |
| `X/HELLO_MAC_SERIAL_PERSISTENCE` | `EXCLUDED` | [identity](#excluded-identity) | E29, E35 @ `work/jadx/sources/com/fullpower/smartbed/flan/FLANManager.java:197-328` |
| `X/RESTRICTED_FLAG_XOR` | `EXCLUDED` | [flags](#excluded-flags) | E29 @ `work/jadx/sources/com/fullpower/applications/horizon/rlb/RlbSettings.java:125-180` |
| `X/RAW_BIT_AXIS_OR_PHYSICAL_SIDE_INFERENCE` | `EXCLUDED` | [inference](#excluded-inference) | E20, E35, E36 @ `work/jadx/sources/com/fullpower/smartbed/flan/FLANManager.java:217-328` |
| `X/ANDROID_SAVE_GESTURE_COUNTDOWNS` | `EXCLUDED` | [timing_ui](#excluded-timing_ui) | E19, E24, E26 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/RemoteControl.java:1023-1054,1517-1539` |
| `X/APP_SHARED_SESSION_RETRY_HANGS` | `EXCLUDED` | [unsafe_session](#excluded-unsafe_session) | E07, E10, E11, E12 @ `work/jadx/sources/x7/c.java:75-169,375-399,452-510` |
| `X/ANDROID_AUTOCONNECT_SCAN_POLICY` | `EXCLUDED` | [android](#excluded-android) | E05, E08 @ `work/jadx/sources/com/fullpower/bandwireless/android/AndroidBLEDeviceManager.java:247-356,401-450,455-465,496-522,604-615,643-734` |
| `X/UNUSED_AD_IGNORE_NAMES` | `EXCLUDED` | [dead](#excluded-dead) | E05 @ `work/jadx/sources/com/fullpower/bandito/WirelessDeviceFinderImpl.java:201-210 (no shipped reader, accepted discovery_rules.unused_ignore_names)` |
| `HA/BOUNDED_TRANSPORT_FRAGMENTS` | `IMPLEMENTED` | [frame](#frame) | E09, E10 @ `work/smali/base/smali/x7/a.smali:847-1230` |
| `HA/CANCEL_AND_LATE_REPLY_CLEANUP` | `IMPLEMENTED` | [lifecycle](#lifecycle) | E11, E12, E18, E30 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/RemoteControl.java:1483-1539,1599-1630` |
| `HA/DECLARED_ENTITIES_TYPED_ACTIONS` | `IMPLEMENTED` | [exposure](#exposure) | E21, E23, E24, E25, E26 @ `work/jadx/sources/com/fullpower/applications/horizon/screens/RemoteControl.java:1335-1444,1785-1845` |
| `HA/EPHEMERAL_SECRET_REDACTION` | `IMPLEMENTED` | [privacy](#privacy) | E13, E14 @ `work/jadx/sources/y6/m.java:450-511` |
| `N/WIND_DOWN_RUNNING` | `IMPLEMENTED` | [wind_down](#wind_down) | ADD/D05, ADD/D07, ADD/D08, ADD/D09, ADD/D10, ADD/D12 @ `work/addendum-001/sources/smali/com/fullpower/applications/horizon/screens/RelaxWindDown.smali:1193-1392; JsonDict.smali:1270-1352` |
| `X/WIND_DOWN_CLOUD_RECHECK` | `EXCLUDED` | [cloud](#excluded-cloud) | ADD/D01, ADD/D11 @ `work/addendum-001/sources/smali/com/fullpower/applications/horizon/screens/RelaxWindDown$b.smali:34-68; n7/l0.smali:27-57 (server REQUEST_STATUS route), exact method hashes in scoped discovery D11` |
| `X/WIND_DOWN_UNCHECKED_CONSUMER` | `EXCLUDED` | [unsafe_session](#excluded-unsafe_session) | ADD/D09, ADD/D13 @ `work/addendum-001/sources/smali/com/fullpower/applications/horizon/screens/RelaxWindDown.smali:1193-1392; n7/f.smali:101-156; JsonDict.smali:285-413 (nonadvancing nested-array branch), exact scoped D09/D13 methods` |

## Scoped addendum crosswalk

Every one of the 13 accepted scoped discoveries maps to the following existing or additive dispositions. These are aliases, not another count. App UI lifecycle, unsafe callback/parser behavior and cloud routes are separate from the implemented numeric state. No cloud countdown becomes a BLE polling interval.

| Addendum discovery | Exact ledger dispositions |
|---|---|
| D01 | `P1`, `B/AUTH`, `X/RESTRICTED_FLAG_XOR`, `X/RSSI_UI_THRESHOLDS`, `X/WIND_DOWN_CLOUD_RECHECK` |
| D02 | `V/action:REQUEST_STATUS`, `L/TRANSACTION`, `X/APP_SHARED_SESSION_RETRY_HANGS` |
| D03 | `B/FRAME`, `N/FRAME`, `L/TRANSACTION`, `X/APP_SHARED_SESSION_RETRY_HANGS` |
| D04 | `L/TRANSACTION`, `HA/CANCEL_AND_LATE_REPLY_CLEANUP`, `X/APP_SHARED_SESSION_RETRY_HANGS` |
| D05 | `N/WIND_DOWN_RUNNING`, `X/WIND_DOWN_UNCHECKED_CONSUMER` |
| D06 | `HA/CANCEL_AND_LATE_REPLY_CLEANUP`, `V/platform:Android`, `X/WIND_DOWN_CLOUD_RECHECK` |
| D07 | `N/WIND_DOWN_RUNNING` |
| D08 | `N/WIND_DOWN_RUNNING` |
| D09 | `N/WIND_DOWN_RUNNING`, `X/WIND_DOWN_UNCHECKED_CONSUMER` |
| D10 | `N/WIND_DOWN_RUNNING`, `V/action:START_WIND_DOWN_1`, `V/action:START_WIND_DOWN_2`, `V/action:STOP_EVERYTHING`, `X/ANDROID_SAVE_GESTURE_COUNTDOWNS` |
| D11 | `X/WIND_DOWN_CLOUD_RECHECK`, `X/ANDROID_SAVE_GESTURE_COUNTDOWNS` |
| D12 | `N/WIND_DOWN_RUNNING`, `L/TRANSACTION`, `X/WIND_DOWN_UNCHECKED_CONSUMER` |
| D13 | `X/WIND_DOWN_UNCHECKED_CONSUMER`, `HA/CANCEL_AND_LATE_REPLY_CLEANUP` |

## Command and read crosswalk

Every command row in the accepted report maps below, including reads and builders outside the action enum. Rows referring to mixed video behavior mean its local six statements, with the six speaker statements separately excluded above.

| Accepted action / read | Disposition | Code and focused tests | Accepted evidence |
|------------------------|-------------|------------------------|-------------------|
| `ANTI_SNORE` | `IMPLEMENTED` | [preset](#preset) | E15, E16, E17, E18, E19, E12 |
| `FLAT` | `IMPLEMENTED` | [preset](#preset) | E15, E16, E17, E18, E19, E12 |
| `FOOT_DOWN_INCREMENT` | `IMPLEMENTED` | [movement](#movement) | E15, E16, E17, E18, E19, E12 |
| `FOOT_STOP` | `IMPLEMENTED` | [movement](#movement) | E15, E16, E17, E18, E19, E12 |
| `FOOT_UP_INCREMENT` | `IMPLEMENTED` | [movement](#movement) | E15, E16, E17, E18, E19, E12 |
| `HEAD_DOWN_INCREMENT` | `IMPLEMENTED` | [movement](#movement) | E15, E16, E17, E18, E19, E12 |
| `HEAD_STOP` | `IMPLEMENTED` | [movement](#movement) | E15, E16, E17, E18, E19, E12 |
| `HEAD_UP_INCREMENT` | `IMPLEMENTED` | [movement](#movement) | E15, E16, E17, E18, E19, E12 |
| `HZ_MASSAGE_28` | `IMPLEMENTED` | [massage](#massage) | E15, E16, E17, E18, E19, E12 |
| `HZ_MASSAGE_40` | `IMPLEMENTED` | [massage](#massage) | E15, E16, E17, E18, E19, E12 |
| `LUMBAR_DOWN_INCREMENT` | `IMPLEMENTED` | [movement](#movement) | E15, E16, E17, E18, E19, E12 |
| `LUMBAR_STOP` | `IMPLEMENTED` | [movement](#movement) | E15, E16, E17, E18, E19, E12 |
| `LUMBAR_UP_INCREMENT` | `IMPLEMENTED` | [movement](#movement) | E15, E16, E17, E18, E19, E12 |
| `MASSAGE_FOOT` | `IMPLEMENTED` | [massage](#massage) | E15, E16, E17, E18, E19, E12 |
| `MASSAGE_HEAD` | `IMPLEMENTED` | [massage](#massage) | E15, E16, E17, E18, E19, E12 |
| `MASSAGE_PATTERN_STEP` | `IMPLEMENTED` | [massage](#massage) | E15, E16, E17, E18, E19, E12 |
| `PROGRAM_ANTI_SNORE` | `IMPLEMENTED` | [preset](#preset) | E15, E16, E17, E18, E19, E12 |
| `PROGRAM_FAVORITE` | `IMPLEMENTED` | [preset](#preset) | E15, E16, E17, E18, E19, E12 |
| `PROGRAM_FAVORITE_2` | `IMPLEMENTED` | [preset](#preset) | E15, E16, E17, E18, E19, E12 |
| `PROGRAM_TV_POSITION` | `IMPLEMENTED` | [preset](#preset) | E15, E16, E17, E18, E19, E12 |
| `PROGRAM_ZERO_G` | `IMPLEMENTED` | [preset](#preset) | E15, E16, E17, E18, E19, E12 |
| `REQUEST_STATUS` | `IMPLEMENTED` | [state](#state) | E15, E16, E17, E18, E19, E12 |
| `START_SPEAKER_SYNC` | `EXCLUDED` | [audio](#excluded-audio) | E15, E16, E17, E18, E19, E12 |
| `START_WIND_DOWN_1` | `IMPLEMENTED` | [massage](#massage) | E15, E16, E17, E18, E19, E12 |
| `START_WIND_DOWN_2` | `IMPLEMENTED` | [massage](#massage) | E15, E16, E17, E18, E19, E12 |
| `STOP_ALL` | `EXCLUDED` | [dead](#excluded-dead) | E15, E16, E17, E18, E19, E12 |
| `STOP_EVERYTHING` | `IMPLEMENTED` | [massage](#massage) | E15, E16, E17, E18, E19, E12 |
| `STOP_EVERYTHING_ALL` | `IMPLEMENTED` | [massage](#massage) | E15, E16, E17, E18, E19, E12 |
| `STOP_SPEAKER_SYNC` | `EXCLUDED` | [audio](#excluded-audio) | E15, E16, E17, E18, E19, E12 |
| `TOGGLE_SAFETY_LIGHTS` | `IMPLEMENTED` | [light](#light) | E15, E16, E17, E18, E19, E12 |
| `TV_POSITION` | `IMPLEMENTED` | [preset](#preset) | E15, E16, E17, E18, E19, E12 |
| `USER_FAVORITE` | `IMPLEMENTED` | [preset](#preset) | E15, E16, E17, E18, E19, E12 |
| `USER_FAVORITE_2` | `IMPLEMENTED` | [preset](#preset) | E15, E16, E17, E18, E19, E12 |
| `ZERO_G` | `IMPLEMENTED` | [preset](#preset) | E15, E16, E17, E18, E19, E12 |
| `authenticate` | `IMPLEMENTED` | [auth](#auth) | E13, E14, E09, E10, E12 |
| `GET_HELLO` | `IMPLEMENTED` | [session](#session) | E07, E11, E14, E09, E10, E12 |
| `GET_FIRMWARE` | `IMPLEMENTED` | [session](#session) | E07, E33, E09, E10, E12 |
| `fanControl LEFT/RIGHT/SYNC` | `IMPLEMENTED` | [climate](#climate) | E23, E09, E10, E12 |
| `relax wave animation` | `IMPLEMENTED` | [wave](#wave) | E24, E09, E10, E12 |
| `video sequence / pulseCounts` | `IMPLEMENTED` | [animation](#animation) | E25, E09, E10, E12 |
| `restricted bare light off/toggle` | `IMPLEMENTED` | [light](#light) | E29, E30, E09, E10, E12 |
| `identify split side1 light` | `IMPLEMENTED` | [light](#light) | E31, E09, E10, E12 |

## Boundary details and safe HA differences

- **Transport identity:** the unique processor service and exact same-service roles identify this path. Standard `180a` alone, shared KSSF names and manufacturer board IDs alone do not select it. Tempur Sleeptracker-AI is the app profile for the reported ProSmart Air / ActiveBreeze bed. The PR671 Lite massage override and local preset workaround are removed. A verified processor endpoint is required; no JSON is sent to UART.
- **Scanner policy:** the Android successful-address autoConnect cache, LE transport value 2, OS scan settings and 5/10/12-second scan/flush scheduling are app lifecycle policy. HA owns that infrastructure. The initialized ignore-name list (`_BLANK_`, `UP24`, `UP`, `UP CC`, `UP_CC`, `UP MOVE`, empty string and null) has no shipped reader and is explicitly dead, so it supplies no detection rule.
- **Framing/session:** reject nonadvancing nested arrays at the lossless raw-pair JSON boundary, including unused and duplicate-overwritten fields, before independent consumers can acknowledge them. Every awaited exchange returns a validated object and marks decode failures tainted, including final identification off. Preserve LE header masks, outgoing sequence zero, request byte grammar and same-channel read continuation. Fragment capacity follows negotiated ATT limits rather than blindly assuming 500 bytes. Channels have bounded independent buffers. A stale/cancelled/invalid/timed-out exchange is ambiguous without request IDs, so HA attempts release and closes before reuse. Standard CCCD setup belongs to Bleak; app blind writes, descriptor semaphore hangs, stale mutable dispatch and immediate API retry loops are excluded safety quirks.
- **Movement:** use artifact axes and ticks 4, repeating only after a reply. HA pulse/timed settings bound elapsed hold duration, not protocol refresh cadence. Fresh cancellation events protect axis release/all-stop cleanup; disconnected hardware cannot acknowledge receipt. Main app ACTION_CANCEL and disconnect cleanup omissions are not reproduced. HA idle timers and command serialization remain existing infrastructure.
- **Metadata/model gates:** persist an explicit layout, unit, snapshot ordinal, processor type and foundation choice per physical entry. Hello Slim aliases stay separate from persisted Slim IDs. Raw bitfields, both sensor-count rule variants, model comparison and thresholds 66/83/97/113 are diagnostic; app readiness, smartCable/cloud setup and firmware update gates do not block proven BLE requests. No physical axes/position decoder or unit-to-half inference is invented. Restricted sessions use unit 0 and do not require an unused authentication characteristic.
- **Auth/privacy:** only the configured target MAC is used for authentication. Challenges, generated passwords and tokens are ephemeral and redactable, including raw-address captures. `validUntil` is not a proven expiry requirement (the app never checks it) and is not persisted. App hello MAC/serial and XOR preference persistence are excluded; the effective restricted route is explicitly selectable.
- **Climate:** fixed heating 3600 and cooling 36000 second fields, complete selected left/right groups and constant/curve modes. Levels 0–3 are proven builder values; stock heat UI chooses 0/3. Last commanded timer and curve state are labelled as such; no readback or arbitrary timer is invented.
- **Relaxation:** wave uses mapped pulse strength, frequency after 500 ms, and minutes*600. Wind-down sends only modes 1/2 and exposes the first parsed snapshot numeric running state. Absent/empty snapshots retain state; disconnect makes it unknown. Modes, side ordinals and local countdowns are distinct. The 16/10 minutes are UI countdowns, whose completion recheck always uses the excluded cloud task, not BLE. No stop is invented at countdown completion. Local animation retains six bed statements and individual delays; speaker statement removal means media timing equivalence is not claimed. Explicit massage/all-stop remains available.
- **Local identification:** restricted add/edit sends four reply-driven toggle/off requests. Split setup uses literal side 1 and 1500 ms toggles; HA bounds the otherwise screen-owned loop to four cycles and always attempts explicit off cleanup.
- **Network exclusion:** AP characteristic `34c0cf2d-69de-4860-91c5-6f7021c2dd30` is not subscribed or read by this controller. The CONFIG channel is used only for authentication, never AP/config/reboot. Frozen excluded `SleepZConfig` fields are `lan_encryption_type`, `lan_key_b64`, `lan_essid_b64`, `lan_ssid_b64`, `replacement_bed`, `oauth_token`, `oauth_token_refresh`, `server_config_url`, `sku_model_string`, `sku_part_string`, `sku_sensor_count`, `sku_serial_string`, `time_gmt_secs`, `tz_setting`, `country_code`, `smart_cable_unsynchronized`; `isSplitKing`/`serverEnvironment` are not serialized. E32 supplies the exact builders, including reboot. No credential values are reproduced here.
- **Other exclusions:** all six firmware/DFU routes and their 58 transport callsites; HTTP/WebSocket/cloud/account/sleep/alarm-only flows; WebView help/coaching/keyboard/media; all speaker/audio control and feedback; all dead enum actions, nine unused UUID constants, unassigned reads, prototype/stage/platform-None routes and the unapplied connection-profile object. These are final exclusions, not future feature work.

## Validation and hardware-only follow-up

The comparison pass matched all **78 retained frozen exact-byte payload/frame vectors**; **8 full vectors** cover excluded speaker actions, the dead `STOP_ALL` mapping or mixed media sequences. The independently rewritten local-sequence test covers every retained statement and delay. Focused protocol/session/setup/service/entity tests cover layout gates, framing capacities, read continuation, typed selectors, all-target preflight, cancellation, late replies, reconnect and redaction. Shared platform/routing tests and the bundled card checks complete the candidate validation; the parent performs the final full suite and independent convergence review.

Physical validation is deferred to real users after a beta/release, without a maintainer-hardware requirement:

1. Capture hello/auth/control with secrets redacted; confirm negotiated MTU, standard descriptors, safe fragment capacities and sequence-zero acceptance.
2. Correlate configured unit integers, snapshot ordinals and physical halves, including the scope of selected-unit all-stop. One-address pairing remains unavailable without that evidence.
3. Check climate level/mode/curve effects and fixed timer expiry, wave tick/duration units, direct massage frequencies, wind-down and retained local pulseCounts/animation behavior.
4. Check stock/HA release, cancel, pause, timeout and disconnect stop delivery. A packet write is not physical stop proof; disconnected transport can prevent cleanup delivery.

No artifact/runtime-table blocker remains in this implementation candidate. See the [processor guide](../../beds/sleeptracker.md) and [public actions](../../SERVICES.md#sleeptracker-smart-bed).
