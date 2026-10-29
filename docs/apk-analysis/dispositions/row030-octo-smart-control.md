# OCTO Smart Control 1.03.02 disposition ledger

## Scope and provenance

This ledger records all 53 reachable discoveries in the accepted comparison for
`de.octoactuators.octosmartcontrolapp` version 1.03.02 (version code 10302), dated
2026-10-26. The complete received set contained 19 APKs and 21 members. It does
not establish coverage of all Play deliveries or variants: 57 optional locales
were absent. The accepted report seal is
`7135e331ba3620704e93e912a5f51eb611f929234d441dd91d48e3d5b750b77b`; the
independent accepting audit seal is
`e6cf1e55f5488bedd206d517767625948be9f40889493919976b5773e5b871fa`.

Every discovery has one disposition. `IMPLEMENTED` items below were completed
in the row030 implementation; `ALREADY_IMPLEMENTED` items retain the cited
equivalence proof; `EXCLUDED` items record the accepted artifact evidence and
the exact scope or safety reason. The standard P1 protocol remains the existing
OCTO Standard controller. Star2 remains a separate variant. Physical hardware
has not been tested; that validation is deferred to real users after beta or
release.

## Dispositions

| ID | Disposition | Discovery and implementation evidence |
|---|---|---|
| R030-POST-001 | ALREADY_IMPLEMENTED | P1 uses FFE0/FFE1; the device-name table formats the app list and does not select a protocol. `detection.py`/`manifest.json`; `tests/test_detection.py::TestFFE0UUIDDisambiguation`, `tests/test_octo.py::TestOctoVariantSelection`. |
| R030-POST-002 | ALREADY_IMPLEMENTED | One P1 protocol; no CID/PID/HW/FW/branding/locale/name protocol branch; Star2 is not selected by this app. Existing factory/detection selection; `tests/test_octo.py::TestOctoVariantSelection`. |
| R030-POST-003 | EXCLUDED | App list filtering, local labels, and resource-only locale/density splits are companion-app presentation. The received artifact inventory proves the supplied splits contain resources only, and does not authenticate absent locales or all deliveries. No HA bed feature is inferred from this UI. |
| R030-POST-004 | EXCLUDED | Cordova permissions, `autoConnect=false`, 7-second plugin timeout, CCCD choice, reconnect/retry, and RSSI polling are mobile transport policy. HA Bluetooth owns connection lifecycle; the existing Octo no-response write mode is retained. |
| R030-POST-005 | IMPLEMENTED | When replies arrive, Standard follows the app's ordered P1 ping, exact reply validation, device-info and capability sequence before PIN/readiness. A missing reply alone can use the established field fallback; any malformed optional reply remains strict for the whole setup attempt, including late PING/device-info frames during CAPS or PIN confirmation. Setup still requires complete capabilities and current PIN proof. `beds/octo.py`, `octo_auth.py`, `coordinator.py`; `tests/test_octo.py::TestOctoOrderedSession`, `TestOctoRequiredStartupDiscovery`, `test_absent_session_reply_keeps_legacy_controls_available`, `tests/test_octo_auth.py::test_absent_optional_replies_reach_caps_and_verified_setup_flow`, `test_late_malformed_optional_reply_stays_strict_for_setup_attempt`, `test_invalid_ping_reply_stops_setup_before_device_info_or_pin`. |
| R030-POST-006 | IMPLEMENTED | Parses exact 10-byte SYSTEM 70 replies (CID/FW/PID/HW, big-endian). A missing reply permits the next ordered request but does not fabricate device information; capability fallback remains non-authoritative. Setup tolerates genuinely absent optional replies, still requires a complete capability list and a current PIN reply when required, and rejects unresolved partial or malformed responses before clearing buffers or accepting terminal proof. `beds/octo.py`, `octo_auth.py`; `tests/test_octo.py::TestOctoOrderedSession`, `test_absent_session_reply_keeps_legacy_controls_available`, `tests/test_octo_auth.py::test_absent_optional_replies_keep_current_pin_proof_and_setup_outcome`, `test_late_malformed_optional_reply_stays_strict_for_setup_attempt`, `test_late_partial_optional_reply_is_not_absence`, `test_partial_optional_reply_is_not_cleared_before_capabilities`, `test_invalid_device_info_stops_setup_before_capabilities_or_pin`, `test_incomplete_or_invalid_replies_never_confirm_pin`. |
| R030-POST-007 | ALREADY_IMPLEMENTED | P1 delimiter, length, checksum, escaping, direction and no-response writes match accepted vectors. `beds/octo.py`; `tests/test_octo.py::TestOctoCommands`, `TestOctoRGBWICommands`, `TestOctoNotificationStream`. |
| R030-POST-008 | ALREADY_IMPLEMENTED | Fragmented/multiple notification framing, resynchronization, bounds and lifecycle clearing match accepted behavior. `beds/octo.py`; `tests/test_octo.py::TestOctoNotificationStream`. |
| R030-POST-009 | IMPLEMENTED | Normalize valid six-byte destination/source address fields for flags 08/04 before dispatch. `beds/octo.py`; `tests/test_octo.py::TestOctoNotificationStream`. |
| R030-POST-010 | EXCLUDED | Accepted malformed vectors V21-V23 include data beyond declared length. Strict exact-length validation is retained because undeclared trailing bytes could be misread as capability or PIN state. |
| R030-POST-011 | EXCLUDED | The source strips partial flagged address fields, but no valid vector demonstrates a short address. Rejecting short fields prevents payload bytes shifting into command, PIN or capability state. |
| R030-POST-012 | IMPLEMENTED | Preserve full typed capability records (ID, read-only flag, characteristic, type, value); writes alter only value bytes. `beds/octo.py`; `tests/test_octo.py::TestOctoRGBWIFeatureValuePair`, `TestOctoCapabilityControls`. |
| R030-POST-013 | ALREADY_IMPLEMENTED | End sentinel controls completion; incomplete discovery is not persisted as a real snapshot. `beds/octo.py`; `tests/test_octo.py::TestCapabilitySnapshot`, `TestOctoRequiredStartupDiscovery`. |
| R030-POST-014 | IMPLEMENTED | Auto motor layout reads CAP_MOTORCOUNT characteristic[0]; explicit 1–4 override remains available, invalid advertised counts do not create motor surfaces. With no discovered count, the established RTV-name fallback selects one motor; valid discovery or explicit override wins. Accepted absent-capability fallback exposes only that known effective layout without persisting an authoritative snapshot, and malformed replies remain strict. New OCTO setup uses its own override selector. `beds/octo.py`, `cover.py`, `config_flow.py`, `app_profiles.py`; `tests/test_octo.py::TestOctoCapabilityControls`, `TestOctoDynamicEntities`, `TestOctoLegacyMotorSurface`, `tests/test_paired_setup.py::TestOctoLegacyMotorFallbackSetup`, `tests/test_config_flow.py::test_rtv_octo_config_flow_uses_name_when_motor_count_is_unadvertised`. |
| R030-POST-015 | ALREADY_IMPLEMENTED | Motor command IDs/masks match; movement cleanup sends fresh-event STOP in `finally`. `beds/octo.py`; `tests/test_octo.py::TestOctoCommands`, `TestMemPosRelease`. |
| R030-POST-016 | IMPLEMENTED | Card motor hold uses the existing bounded `hold_control` contract and Octo-declared cadence; release/cancel routes side STOP, and delayed callbacks are generation guarded. `beds/base.py`, `beds/octo.py`, `button.py`, `frontend/src/hold.ts`; `tests/test_octo.py::TestOctoCapabilityControls`, `tests/test_octo_services.py::test_combined_motor_button_keeps_controller_hold_metadata`, `frontend/src/hold.test.ts`. |
| R030-POST-017 | IMPLEMENTED | CAP_MEMCOUNT/MEMINFO characteristic fields determine effective slots; expose all advertised slots with dynamic entities and runtime service bounds. `beds/octo.py`, `button.py`, `services.py`, `services.yaml`; `tests/test_octo.py::TestOctoMemoryInfoAndCombinedStep`, `TestOctoDynamicEntities`, `tests/test_octo_services.py`. |
| R030-POST-018 | ALREADY_IMPLEMENTED | Three-byte MEMINFO class parsing, bounds, full name-vector requirement, and locked/fixed save rules match. `beds/octo.py`; `tests/test_octo.py::TestOctoMemoryInfoAndCombinedStep`. |
| R030-POST-019 | ALREADY_IMPLEMENTED | Recall/save packet family, command IDs and one-based HA to zero-based slot conversion match. `beds/octo.py`; `tests/test_octo.py::TestOctoMemoryInfoAndCombinedStep`, `TestMemPosRelease`. |
| R030-POST-020 | IMPLEMENTED | Added card-held memory recall using bounded existing service calls; refreshes while held, side-scoped STOP on release/cancel, and generation/ownership checks prevent stale callbacks. `frontend/src/hold.ts`, `adjustable-bed-card.ts`; `frontend/src/hold.test.ts`. |
| R030-POST-021 | IMPLEMENTED | Capability and live PIN states now follow the complete PIN notification state machine; locked state gates normal controls while STOP remains available. `beds/octo.py`, `octo_auth.py`, entity platforms; `tests/test_octo.py::TestOctoPinAuth`, `TestPinReauth`, `TestOctoCapabilityControls`. |
| R030-POST-022 | ALREADY_IMPLEMENTED | Four-digit validated unlock uses SYSTEM 43 raw digit bytes; setup verification waits for PIN_STATE=1 and does not move the bed. `beds/octo.py`, `octo_auth.py`; `tests/test_octo.py::TestOctoPinAuth`, config-flow PIN verification tests. |
| R030-POST-023 | IMPLEMENTED | The app's PIN_LOCK retry waits exactly 1000 ms and validates four ASCII digits. Separately, established-field compatibility restores main's periodic 25-second keepalive for a configured PIN on a held link. Long held motor and memory operations track the existing monotonic due time from the last successful PIN write, include prior elapsed time and GATT cost, and refresh inside their already-owned command lane. A due refresh waits for any in-flight movement write, then resumes at the next eligible movement cadence; cancellation, current session/client checks, finite hold deadline and fresh STOP remain. The interval is host behavior, not an app timing claim. `beds/octo.py`, `coordinator.py`, `const.py`; `tests/test_octo.py::TestPinReauth`, `TestOctoPinAuth::test_periodic_pin_keepalive_uses_command_lane_and_disconnect_generation`, `test_coordinator_starts_keepalive_after_octo_session`, `tests/test_octo_services.py::test_registered_octo_motor_and_memory_holds_refresh_pin_in_lane`, `test_registered_octo_hold_refresh_uses_monotonic_due_time`, `test_registered_stop_cancels_long_octo_hold_before_in_lane_refresh`, `test_long_octo_hold_does_not_refresh_or_move_after_link_identity_changes`. |
| R030-POST-024 | IMPLEMENTED | Added explicit four-digit PIN enrollment with confirmation, correct SYSTEM 41 record and optional secret persistence. `octo_auth.py`, `services.py`, `services.yaml`; `tests/test_octo_services.py` enrollment cases. |
| R030-POST-025 | IMPLEMENTED | CAP_SYNCHRO availability/state use advertised characteristic/value and metadata-preserving SYSTEM 72 writes. `beds/octo.py`, `switch.py`; `tests/test_octo.py::TestOctoCapabilityControls`. |
| R030-POST-026 | IMPLEMENTED | Added PIN-gated remote-lock state and record-preserving writer. `beds/octo.py`, `switch.py`; `tests/test_octo.py::TestOctoCapabilityControls`. |
| R030-POST-027 | IMPLEMENTED | Complete discovery uses active CAP_LIGHT/color records for authoritative light controls. Only a missing/incomplete capability reply uses the established assumed-light switch path, without fabricating writable records; on/off-only receivers retain the legacy switch ID. Color writes turn light on first when needed. `beds/octo.py`, `light.py`, `switch.py`; `tests/test_octo.py::TestOctoRGBWILightEntity`, `TestOctoCapabilityControls::test_onoff_only_light_keeps_legacy_switch_entity_identity`, `TestOctoOrderedSession::test_absent_session_reply_keeps_legacy_controls_available`. |
| R030-POST-028 | IMPLEMENTED | Added CAP_LIGHT_DURATION number (0–60 minutes, zero permanent), preserving advertised metadata. `beds/octo.py`, `number.py`; `tests/test_octo.py::TestOctoCapabilityControls`. |
| R030-POST-029 | IMPLEMENTED | Added active-gated automatic-light switch using its capability value and exact record. `beds/octo.py`, `switch.py`; `tests/test_octo.py::TestOctoCapabilityControls`. |
| R030-POST-030 | IMPLEMENTED | Added light sensitivity select for the advertised 6/35/85 values, encoded as big-endian two-byte values. `beds/octo.py`, `select.py`; `tests/test_octo.py::TestOctoCapabilityControls`. |
| R030-POST-031 | IMPLEMENTED | RGBW uses its independent five-byte RGB/intensity capability; brightness and unrelated metadata survive writes. `beds/octo.py`, `light.py`; `tests/test_octo.py::TestOctoRGBWILightEntity`, `TestOctoRGBWICommands`. |
| R030-POST-032 | IMPLEMENTED | Added independent RGB support. RGB and RGBW can coexist, with requested color fields routed to their own exact records and active mode. `beds/base.py`, `beds/octo.py`, `light.py`; `tests/test_octo.py::TestOctoRGBWILightEntity`. |
| R030-POST-033 | IMPLEMENTED | Added PIN-gated remote-teach action using active CAP_RCTEACH record. `beds/octo.py`, `button.py`; `tests/test_octo.py::TestOctoCapabilityControls`. |
| R030-POST-034 | IMPLEMENTED | Added explicitly confirmed, PIN-gated SYSTEM AE reset and delayed five-second disconnect. No physical bed was connected. `beds/octo.py`, `services.py`, `services.yaml`; `tests/test_octo_services.py::test_octo_reset_requires_true_confirmation_and_routes_once`. |
| R030-POST-035 | IMPLEMENTED | Capability records, device info and PIN state are copied per physical controller/paired side; writes retain side target and PIN enrollment persists on the shared physical coordinator behind a single-address side view. `beds/octo.py`, coordinator snapshot code, `services.py`; `tests/test_octo.py::TestCapabilitySnapshot`, Octo side-routing cases in `tests/test_paired_coordinator.py`, `tests/test_octo_services.py::test_octo_enroll_pin_from_single_address_side_updates_physical_owner`. |
| R030-POST-036 | IMPLEMENTED | Dynamic Octo entity availability follows complete authoritative discovery; incomplete scans preserve prior surfaces, complete loss retires Octo-owned IDs, and regain reuses stable IDs. `entity_discovery.py`, entity platforms; `tests/test_octo.py::TestOctoDynamicEntities`, `TestOctoRGBWILightEntity`, `TestOctoLegacyMotorSurface::test_later_complete_motor_count_reconciles_fallback_registry_rows`. |
| R030-POST-037 | IMPLEMENTED | Setup label and documentation use OCTO Smart Control while retaining the existing OCTO Standard bed type. `const.py`, `config_flow.py`, translations; `tests/test_config_flow.py` Octo selector cases. |
| R030-POST-038 | EXCLUDED | Accepted notification/capability coverage has no position, angle, massage, battery, alarm or motor-state source. This is artifact-bounded absence for this app version, not all firmware. No sensor or state is inferred. |
| R030-POST-039 | EXCLUDED | Address slots and active-device switching are companion-app organization. HA config entries, native paired children and explicit side routing own device/address selection. |
| R030-POST-040 | EXCLUDED | Custom saved-position names are app-local preferences, not BLE state. HA entity IDs/translations own names; four proven built-in memory descriptions remain supported. |
| R030-POST-041 | EXCLUDED | CID-to-logo/color mapping is branding presentation and does not choose protocol/capabilities. Brand-based support claims were removed; no CID-specific controller profile is added. |
| R030-POST-042 | EXCLUDED | Cloud BLE-name lookup only enriches app display labels; direct BLE control requires no cloud metadata. |
| R030-POST-043 | EXCLUDED | Cloud branding/logo downloads only affect app presentation; no cloud client is added. |
| R030-POST-044 | EXCLUDED | The device-not-found route opens an external companion support page. Destination was not fetched; it is not direct bed control. |
| R030-POST-045 | EXCLUDED | The manual route opens an external companion support page; PID remains parsed device information, not a protocol selector. Destination was not fetched. |
| R030-POST-046 | EXCLUDED | Forgotten-PIN support opens an external companion support page; its destination was not fetched. BLE PIN state/unlock/enrollment are separately implemented in rows 021–024. |
| R030-POST-047 | EXCLUDED | Firmware update caller is commented/unreachable and no firmware image ships; transfer is outside the product boundary. Normal BLE session/control stays implemented; no updater packets are enabled. |
| R030-POST-048 | EXCLUDED | DEMODEVICE entries synthesize local demo state and have no physical BLE effect. |
| R030-POST-049 | EXCLUDED | The accepted app has no bed Wi-Fi provisioning, SSID/password, network administration or Bluetooth Classic bed transport. HA-side Bluetooth adapters/proxies remain supported. |
| R030-POST-050 | EXCLUDED | EEPROM/bus-teach/token/auxiliary/BC00/slave-position declarations are dead or unhandled in the accepted app. Do not promote constants into commands. Inbound PIN_CLEARED is separately implemented in row 021. |
| R030-POST-051 | EXCLUDED | No reachable parser reports position, travel completion, alarm, battery or motor status. Do not infer/synthesize state from command timing. |
| R030-POST-052 | IMPLEMENTED | Unmatched CONFIG/DEBUG/NORMAL responses remain no-op; explicit Octo capability/PIN handling is separate. `beds/octo.py`; `tests/test_octo.py::TestOctoNotificationStream`. |
| R030-POST-053 | EXCLUDED | The source omits STOP after touchcancel when page scroll is at most 140 px, potentially leaving repeated motion active. HA cancellation always stops and cancels refresh for safety; exact unsafe behavior is not copied. `frontend/src/hold.ts`, `frontend/src/hold.test.ts`. |

## Sol round-one repair crosswalk

All 16 verified findings from the first independent source review are repaired.
The second independent source review verified every fix and approved the changed
snapshot with no open or new findings. There are no disagreements or scope cuts.

| Finding | Status | Code and focused proof |
|---|---|---|
| S030-1 | CLOSED_VERIFIED | Optional HA extra attributes are read safely in `cover.py` and `button.py`; real entity catalog/routing cases in `tests/test_entities.py` and `tests/test_homekit_blueprint.py`. |
| S030-2 | CLOSED_VERIFIED | `frontend/src/hold.ts` retains delayed release targets and flushes them on abandon/card replacement; fake-timer cases for 100 ms motor and 200 ms memory release plus old-release ownership checks in `frontend/src/hold.test.ts`. |
| S030-3 | CLOSED_VERIFIED | Unrelated Octo capability writes preserve notification-owned PIN state in `beds/octo.py`; `tests/test_octo.py::TestOctoCapabilityControls::test_unrelated_settings_keep_latest_notification_owned_pin_state`. |
| S030-4 | CLOSED_VERIFIED | Unlock and escaped enrollment packets are redacted before logs and support traces in `beds/octo.py`; `tests/test_octo.py::TestOctoPinAuth::test_send_pin_redacts_command_diagnostics` and `test_enrollment_pin_is_redacted_from_logs_and_support_trace`. |
| S030-5 | CLOSED_VERIFIED | Dynamic recall/save entities emit stable memory translation keys and bounded hold metadata from actual `ControllerButtonSpec` records; `tests/test_octo_services.py::test_octo_memory_action_specs_publish_card_metadata_for_standalone_and_side` and `frontend/src/discovery.test.ts::Octo backend motor and dynamic memory metadata is retained for the card`. |
| S030-6 | CLOSED_VERIFIED | The read-only `CAP_RCTEACH` exception is local to the artifact-defined action and emits the exact accepted record payload only after the PIN gate; `beds/octo.py::teach_remote` and `tests/test_octo.py::TestOctoCapabilityControls::test_readonly_remote_teach_uses_exact_action_and_requires_unlocked_pin`. |
| S030-7 | CLOSED_VERIFIED | The PIN challenge stops an active held operation before authorization; retry response tracking lets accepted authentication finish without 60-second scheduler starvation; `tests/test_octo.py::TestPinReauth::test_pin_lock_preempts_real_scheduled_held_control_before_reauth`. |
| S030-8 | CLOSED_VERIFIED | Enrollment persistence requires completion inside the scheduled callback; a skipped scheduler ticket reports interruption and leaves both stored PINs unchanged; `tests/test_octo_services.py::test_octo_enroll_pin_is_not_persisted_when_scheduler_skips_callback`. |
| S030-9 | CLOSED_VERIFIED | Ordinary runtime commands wait for session-owned PIN acceptance; rejection, timeout, cancellation and stale generation are distinguished; `tests/test_octo.py::test_runtime_reconnect_waits_for_session_pin_acceptance_before_command` and `TestPinReauth::test_pin_acceptance_wait_distinguishes_rejection_timeout_cancel_and_stale_session`. |
| S030-10 | CLOSED_VERIFIED | PIN availability transitions participate in Octo light state change detection; lock and unlock publish HA state with unchanged power/color; `tests/test_octo.py::TestOctoRGBWILightEntity::test_pin_only_state_transitions_publish_light_availability`. |
| S030-11 | CLOSED_VERIFIED | Incomplete capability scans preserve known Octo light IDs and suppress guessed light fallback; complete loss retires the real ID and regain restores it; `tests/test_octo.py::TestOctoRGBWILightEntity::test_octolight_builder_preserves_incomplete_registry_and_retires_authoritatively`. |
| S030-12 | CLOSED_VERIFIED | Complete Octo memory reconciliation retires all stale slots above eight only for the selected runtime/side; `tests/test_octo_services.py::test_complete_memory_loss_retires_only_the_selected_octo_side_ids`. |
| S030-13 | CLOSED_VERIFIED | Auto lift detection reads the live snapshot's actual discovered count; the real pair flow rejects two one-motor receivers; `tests/test_paired_setup.py::TestPairBedsConversion::test_auto_octo_one_motor_snapshot_lifts_cannot_be_paired`. |
| S030-14 | CLOSED_VERIFIED | Three/four-motor M1+M2 and down-only all-motor controls use accepted masks, bounded hold specs and fresh STOP; `tests/test_octo.py::TestOctoCommands::test_three_and_four_motor_artifact_holds_are_bounded_and_stopped`. |
| S030-15 | CLOSED_VERIFIED | Octo RGBWI intensity zero is preserved on initialization, update and write without changing legacy level semantics; `tests/test_octo.py::TestOctoRGBWILightEntity::test_rgbwi_intensity_zero_survives_initial_state_updates_and_writes`. |
| S030-16 | CLOSED_VERIFIED | Auto-detect ownership is compared against the confidently detected profile, preserving Star2 variant and pulse defaults without rebuilding the same form; `tests/test_starcode_setup_discovery.py::test_private_star2_auto_preserves_receiver_and_pulse_defaults[manual]` and `[bluetooth_full_list]`. |

## Established field compatibility (separate from APK behavior)

The following compatibility paths preserve prior field-verified behavior from
closed issues. They do not add claims about the accepted app artifact or change
any of the 53 ledger IDs/dispositions:

- [Issue #176](https://github.com/kristofferR/ha-adjustable-bed/issues/176): an
  advertised positive duration uses its minutes, explicit zero means permanent
  lighting, and an absent duration uses the established 300-second fallback.
  On/off-only OCTO lights keep the existing `under_bed_lights` switch unique ID;
  color/intensity capabilities may add the light entity without deleting that
  switch. A deliberate ON restarts its expiry, while identical telemetry and an
  equivalent reconnect preserve the existing deadline. Focused proofs:
  `tests/test_octo.py::TestOctoCapabilityControls::test_light_duration_reports_positive_timeout_and_permanent_zero`,
  `test_light_duration_absence_uses_legacy_five_minute_default`, and
  `test_onoff_only_light_keeps_legacy_switch_entity_identity`.
- [Issue #29](https://github.com/kristofferR/ha-adjustable-bed/issues/29): the
  configured-PIN keepalive runs every 25 seconds while the OCTO link is held,
  through the serialized coordinator command lane, alongside the app's reactive
  one-second PIN_LOCK retry. The periodic cadence is host compatibility policy.
  As on main, it runs only when the receiver reports a PIN or never reports its
  PIN state, and a receiver without a complete capability list gets the
  configured PIN at connect (main's `requires_pin` fallback). Focused proofs:
  `TestOctoPinAuth::test_unreported_pin_state_sends_configured_pin_and_keepalive`
  and `test_reported_pinless_bed_gets_no_pin_or_keepalive`.
- [Issues #499](https://github.com/kristofferR/ha-adjustable-bed/issues/499)
  and [#64](https://github.com/kristofferR/ha-adjustable-bed/issues/64): a
  receiver that answers follows the app's strict ordered session. Missing
  ping/device-info replies continue, and an absent/incomplete capability list
  uses main's legacy defaults, including assume-lights, without marking the
  records authoritative or retiring known entities. Malformed replies remain
  strict failures. Focused proofs are the absent-reply and malformed-reply
  cases in `tests/test_octo.py::TestOctoOrderedSession`.
- [Issue #440](https://github.com/kristofferR/ha-adjustable-bed/issues/440):
  an RTV name selects the one-motor fallback only when no motor count was
  discovered; an advertised count or explicit override takes precedence.
  Focused proof: `tests/test_config_flow.py::TestBluetoothDiscoveryFlow::test_rtv_octo_config_flow_uses_name_when_motor_count_is_unadvertised`.

## Validation boundary

Focused controller, coordinator startup, setup, paired-routing, service, light,
and frontend checks are recorded with this implementation. They validate source
behavior against accepted static vectors and mocks. No BLE connection to a
physical bed was made. A real OCTO Smart Control receiver, supported firmware
variants, and deliveries containing the absent optional locales remain
unverified for user beta/release validation.

## Completed source validation

The earlier reviewed implementation passed 19,848 full Python tests with zero
failures. The published PR checkpoint `3df3a4fd2a59ed5df252da189810ff3e65d49ae1`
later passed 19,849 full tests. These are historical results and do not cover
the pending merge and compatibility changes described below.

## Current pending candidate validation

The uncommitted merge candidate passed 172 OCTO/controller/service tests, 268
config-flow tests, and 101 paired, assumed-light, RMControl and RTV-entity tests.
The card's Bun suite passed 147 tests with 587 assertions, and TypeScript
checking plus bundle generation passed. Scoped Ruff and full-project Pyright
passed; `git diff --check` passed. On an isolated archive of published commit
`6c2c50d7c3e40cb77ce341b339cbd16eea5d9701`, seven compatibility regression
cases failed at their intended assertions; all eight candidate cases passed.
The eighth case confirms advertised positive and explicit-zero duration
semantics and passes on both revisions. The negative controls had no
collection, import or setup failures.
This candidate still awaits the root's distinct review and exclusive full
suite. Physical BLE behavior remains unverified for user beta/release
validation.
