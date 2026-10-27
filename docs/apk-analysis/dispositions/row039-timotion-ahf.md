# Row039: TiMOTION AHF Remote convergence

This file records the final implementation disposition of all 32 rows from the
post-freeze comparison ledger for AHF Remote (`com.timotion.ahf`) 1.0.4 (7).
The accepted APK and audit evidence remain immutable. Physical control effects,
the real peripheral's characteristic properties and STOP latency are still
hardware validation items; they do not block the static implementation.

## Evidence identity

- Frozen APK SHA-256: `7d8560decebea782a4cdc98458641ce6263b01ea7fffd6f86a15f167cd42e348`
- Accepted report manifest SHA-256: `0255f72ba86a10ea1942200dcc0f5a36363471e066e6a94a5f7079f09ca057a3`
- Accepted `analysis.json` SHA-256: `5342b598bf990f9c115b63900813212f349d67f7d1f95f2740d1c7c2327274cb`
- Accepting audit seal SHA-256: `8eea8ee2567c6080febbd5eeed88ff15e2185bce51f104257cb6d129058cf11a`
- Comparison manifest SHA-256: `2d071bfe6e0afdf1af486477a89a84bc04e7543820c562d7944e3a0219819eda`
- Comparison baseline: `702bede885f66d3a9b820762208e7e91cc7d3c54`, clean at comparison start.
- Ledger: 19 `IMPLEMENTED`, 4 `ALREADY_IMPLEMENTED`, 9 `EXCLUDED`.

## Final dispositions

| ID | Finding | Disposition | Concrete implementation or proof |
|----|---------|-------------|----------------------------------|
| D-001 | Findable fixed AHF bed type and one fixed P1 route | `ALREADY_IMPLEMENTED` | `const.py`, `detection.py`, and `controller_factory.py`; `tests/test_detection.py::test_detect_timotion_ahf_by_name`, `tests/test_config_flow.py::test_detect_timotion_ahf_bed`, and `tests/test_controller_contract.py`. No app profile or variant selector is needed. |
| D-002 | Fixed Nordic UART write characteristic | `ALREADY_IMPLEMENTED` | `TiMOTIONAhfController.control_characteristic_uuid` and `TIMOTION_AHF_WRITE_CHAR_UUID`; `tests/test_timotion_ahf.py::test_controller_declares_app_labels_without_physical_axes`. |
| D-003 | Immutable 11-byte neutral-based packet builder | `ALREADY_IMPLEMENTED` | `build_timotion_ahf_command`; `tests/test_timotion_ahf.py::test_command_builder_is_immutable_neutral_based_and_eleven_bytes` and all 13 parameter cases in `test_app_action_vectors_and_finite_button_pulse`. |
| D-004 | Serialized coordinator command path and fresh-context neutral STOP | `ALREADY_IMPLEMENTED` | `ControllerActionButton.async_press`, coordinator command execution, and `TiMOTIONAhfController._send_stop`; `tests/test_controller_action_buttons.py::test_remote_action_dispatches_to_current_controller` and `tests/test_timotion_ahf.py::test_stop_uses_three_neutral_writes_and_a_fresh_cancel_event`. |
| I-001 | Status notifications required with angle sensing disabled | `IMPLEMENTED` | `requires_notification_channel`; `tests/test_timotion_ahf.py::test_status_channel_stays_required_when_angle_sensing_is_disabled` connects with `disable_angle_sensing: true` and proves status notify/read. |
| I-002 | Session-local readiness from a valid read or notification, bounded to eight seconds | `IMPLEMENTED` | `start_notify` applies one deadline across subscription, initial read and status wait; `_begin_status_session` and `_set_status_timeout` keep state session-local. Tests `test_status_deadline_includes_a_stalled_notification_subscription`, both cases of `test_status_deadline_covers_pending_read_and_notification_can_win`, `test_status_notify_and_initial_read_establish_session_readiness`, `test_duplicate_notification_frame_establishes_readiness`, `test_valid_initial_read_establishes_readiness_after_notify_failure`, `test_read_and_notify_failure_stay_unready_until_eight_second_bound`, `test_failed_status_can_become_ready_from_a_later_valid_notification`, and `test_disconnect_resets_readiness_and_rejects_stale_notification`. |
| I-003 | Exact RX length, marker and checksum validation | `IMPLEMENTED` | `_is_valid_notification`; tests `test_status_parser_rejects_wrong_size_marker_or_checksum` and `test_status_parser_accepts_unchecked_and_uninterpreted_fields`. |
| I-004 | Raw lock-mask and lamp-display diagnostics | `IMPLEMENTED` | Three typed `ControllerStateSensorSpec` entries and `_process_status_frame`; `test_status_parser_accepts_unchecked_and_uninterpreted_fields` preserves unknown raw values and verifies sensor keys. |
| I-005 | Lock bits gate app actions and refresh button availability | `IMPLEMENTED` | `_action_enabled`, `controller_button_available`, and `validate_hold_control`; `test_lock_mask_gates_only_app_actions`, `test_ahf_hold_control_preflights_status_and_lock_before_writes`, both cases of `test_idle_disconnected_hold_reconnects_then_checks_current_status`, and `tests/test_controller_action_buttons.py::test_controller_action_availability_refreshes_and_unsubscribes` prove lock gating, controller/connection-state refresh, and cleanup. |
| I-006 | Control 1 Up/Down app actions | `IMPLEMENTED` | `_CONTROL_ACTIONS` and `controller_button_specs`; exact vectors and labels covered by `test_app_action_vectors_and_finite_button_pulse`. |
| I-007 | Control 2 Up/Down app actions | `IMPLEMENTED` | `_CONTROL_ACTIONS` and `controller_button_specs`; exact vectors and labels covered by `test_app_action_vectors_and_finite_button_pulse`. |
| I-008 | Control 3 Up/Down app actions | `IMPLEMENTED` | `_CONTROL_ACTIONS` and `controller_button_specs`; exact vectors and labels covered by `test_app_action_vectors_and_finite_button_pulse`. |
| I-009 | Control 4 Up/Down app actions | `IMPLEMENTED` | `_CONTROL_ACTIONS` and `controller_button_specs`; exact vectors and labels covered by `test_app_action_vectors_and_finite_button_pulse`. |
| I-010 | Control 5 Up/Down without a motor-count inference | `IMPLEMENTED` | `_CONTROL_ACTIONS` exposes Control 5 regardless of motor count; only the legacy pillow cover keeps its earlier 4+ motor gate. `test_app_action_vectors_and_finite_button_pulse` plus `test_ahf_setup_hides_massage_and_motor_count_only_sizes_legacy_covers`. |
| I-011 | App-labelled held Night action, not a preset | `IMPLEMENTED` | `night` action in `controller_button_specs` and `held_control_options`; exact packet and bit 5 gate covered by vector and lock-mask tests. |
| I-012 | Held Light action without assumed on/off/toggle semantics | `IMPLEMENTED` | App-labelled `light` and raw lamp diagnostic. The legacy toggle and assumed light send the same action and add no state claim. `test_app_action_vectors_and_finite_button_pulse` and `test_legacy_ahf_entities_keep_their_ids_and_send_app_actions`. |
| I-013 | App-labelled held Chair action, not a posture preset | `IMPLEMENTED` | `chair` action in `controller_button_specs` and `held_control_options`; exact packet and bit 6 gate covered by vector and lock-mask tests. |
| I-014 | Bounded held controls and finite HA button pulse | `IMPLEMENTED` | `hold_control` includes the initial wait, refresh cadence and each GATT write in the request bound, then uses fresh-context release; `_send_action` retains configured finite pulses. Tests `test_idle_disconnected_hold_reconnects_then_checks_current_status` (real coordinator scheduler), `test_app_action_vectors_and_finite_button_pulse`, `test_hold_duration_includes_initial_wait_cadence_and_three_stop_writes`, `test_stalled_hold_write_is_cancelled_at_deadline_before_stop_cleanup`, and `test_hold_cancel_and_action_write_error_both_attempt_neutral_cleanup`. |
| I-015 | Three neutral STOP writes after release, cancellation or write error | `IMPLEMENTED` | `_send_stop` sends three neutral frames 100 ms apart with a fresh cancellation event; `test_stop_uses_three_neutral_writes_and_a_fresh_cancel_event`, `test_hold_duration_includes_initial_wait_cadence_and_three_stop_writes`, and `test_hold_cancel_and_action_write_error_both_attempt_neutral_cleanup`. |
| I-016 | Lamp display-code changes preempt with serialized neutral STOP | `IMPLEMENTED` | `_process_status_frame` detects any changed valid raw code and queues `request_command_cancel` plus coordinator `async_stop_command`; `test_lamp_display_changes_preempt_serialized_stop_but_duplicates_do_not` covers first baseline, duplicate, mask-only, known and unknown changes. |
| I-017 | Keep legacy covers and light toggle; hide irrelevant AHF setup choices | `IMPLEMENTED` | Existing covers and the light toggle keep their entity IDs and send app Controls 1–5 and Light through the same status and lock gates (closed issues #615, #669, #670 established that working controls are not removed from existing entries). Stale `timotion_ahf_` actions are still cleaned up, and massage is hidden through `app_profiles.hidden_generic_fields`. Tests `test_legacy_ahf_entities_keep_their_ids_and_send_app_actions` and `test_ahf_setup_hides_massage_and_motor_count_only_sizes_legacy_covers`. Existing pairing allowlist tests continue to establish no AHF single-address side selector. |
| I-018 | Select only a write mode advertised by discovered GATT properties | `IMPLEMENTED` | `_refresh_write_mode` uses discovered properties and rejects neither-mode characteristics; tests `test_write_mode_uses_only_supported_gatt_properties` (write-only, WWR-only, both) and `test_write_mode_rejects_a_characteristic_without_write_properties`. Actual peripheral properties and Android runtime parity remain deferred. |
| I-019 | Durable protocol, service and setup documentation; correct finite-pulse comment | `IMPLEMENTED` | `docs/beds/timotion-ahf.md`, the AHF rows in `docs/SUPPORTED_ACTUATORS.md` and `docs/SERVICES.md`, and the AHF pulse policy comment in `const.py`. The E20 handset instruction is documented as app guidance only. |
| X-001 | Host-wide Android `removeBond` across remembered bonds (E11) | `EXCLUDED` | Unsafe host-wide bond administration is outside bed-control commands; HA owns host Bluetooth administration. |
| X-002 | Android scan, permission, adapter prompts, remembered-address UI and app display name (E02/E13) | `EXCLUDED` | HA owns BLE discovery, adapter/proxy and config-entry address infrastructure. Required protocol name/service discovery remains implemented and accounted for. |
| X-003 | Phone screen timeout, unlock hold and haptics preferences (E12) | `EXCLUDED` | These are local phone UI preferences and emit no bed BLE command. |
| X-004 | Missing ACTION_CANCEL cleanup, overlapping handler races and mutable TX carryover (E06–E09/E13) | `EXCLUDED` | Unsafe APK behavior is not reproduced. The integration uses immutable command construction, coordinator serialization, cancellation and fresh-context STOP cleanup. |
| X-005 | Wi-Fi provisioning, network/cloud/account behavior (E01/E03/E07/E08/E17) | `EXCLUDED` | The integration supports direct BLE bed features only. Network administration, provisioning, cloud/accounts and BLE tunnels to those services are outside the product boundary. |
| X-006 | Additional authentication or selector inferred from setup instructions (E03/E11/E17/E20) | `EXCLUDED` | Accepted evidence verifies no PIN, auth packet or selector. E20 is guidance text and does not add protocol behavior. |
| X-007 | Android GATT status codes, retry policy, ignored return values, descriptor scheduling and Activity/service lifecycle (E03/E04/E10/E11/E13) | `EXCLUDED` | These are Android transport/host semantics. HA's Bluetooth lifecycle is used instead; AHF-specific status readiness and actionable read/notify failure remain implemented in I-001/I-002. |
| X-008 | Position, Device Information, ACK, battery, memory, presets, massage, calibration, firmware, model or count fields (E05/E07/E09/E17) | `EXCLUDED` | The accepted artifact has no reachable parser or action for these features. Adding them would invent behavior. |
| X-009 | AHF one-address side routing, synchronization or split-bed selector (E02/E11/E13/E17) | `EXCLUDED` | The artifact has one address and no side route. AHF is absent from the single-address side-aware allowlist; generic separate HA entries remain available. |

## Deferred hardware validation

After beta or release, real users may verify the physical effects of Controls 1–5,
Night, Chair and Light, the physical meaning of lock bits and lamp codes, the
peripheral's actual GATT write properties/status behavior, and STOP latency. No
physical mapping or semantic claim is inferred here.
