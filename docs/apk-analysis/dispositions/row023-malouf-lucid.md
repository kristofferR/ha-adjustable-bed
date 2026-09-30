# Row023: Malouf Base and Lucid Base implementation disposition

This document accounts for the complete cluster007 post-freeze discovery ledger against the explicit Malouf Base / Lucid Base integration profile. It is implementation documentation, not an APK Protocol Audit report. Raw artifacts and accepted reports remain machine-local.

**Implementation audit: complete.** Every discovery has an implemented, already-implemented or excluded disposition. Both bounded evidence amendments are independently accepted. Controller, configuration and service behavior independently passed 243 focused tests, including SplitHead composition and Lucid Oz fallback save2. Thirteen entity lifecycle/native-toggle cases independently passed during the PR review followups, including cross-profile Altitude cover retirement. The coordinator passed the full 6073-test suite and Ruff/Pyright checks. Hardware behavior remains unverified.

## Evidence identity

`M` means `com.malouf.bedbase` version 2.4.3, frozen package run `com.malouf.bedbase-2.4.3-2026-08-27`. `L` means `com.lucid.bedbase` version 1.3.3, frozen package run `com.lucid.bedbase-1.3.3-2026-08-27`. A source pointer such as `M#/protocols/0/commands/0` identifies that package's preserved `report/analysis.json` claim; it is not a repository file or a network link.

| Evidence | SHA-256 |
| --- | --- |
| M artifact set / XAPK | `d9b242a8dda6772f62c5b8f21fe13b462af2533b82a16d67ee7a4a841e6ff894` |
| L artifact set | `88162f4b6adc2cf0d0d5ee4252fe4de3e6564db1881e42ed0a34db3ba58ad148` |
| M original REPORT.SHA256 | `746d913ad256afd0deffe42e989a96c4e2f4c7aa941add5343a65f2236f9e5de` |
| L original REPORT.SHA256 | `8d21996769e6d209345dc38ac84bb178b9fe70293305f22a39227dfe9f3a880c` |
| cluster007 original REPORT.SHA256 | `fd9492a0f0a17ba454247ad9532c5e5f309cbc1090c20a5c9519e8bc8c820239` |
| Accepted write-mode amendment001 REPORT.SHA256 | `d5ec1708a80f2b8dbc0a3dbda7da0ccb2bcfd2a42cafbe7ec51184b2a741d5dc` |
| Independent write-mode acceptance AUDIT.SHA256 | `fe44470752b3514b2dc376590d00d714b87a6bee70b3813779ecc35327091d8e` |
| Accepted routing amendment002 REPORT.SHA256 | `200bd5f4a5efedd784435a5fd672b83aab2ad5c30d640dbc7e0fe532d659d754` |
| Independent routing acceptance AUDIT.SHA256 | `45962ac9eb4b00cd806ce85f4bb70c8d5e37aa6ae9b687f2e57be9e2f2e314d5` |
| Preserved routing amendment001 REPORT.SHA256 | `2c1e29ceeb8710e15622fa8ccd983b09cf2f48537e840e061aef4a19a340f57f` |
| Accepted cluster reconciliation JSON | `c584d5aaab3d9e881816e97190554871f10aa70fb0a24ca53933c3bbdb9a1fef` |
| Accepting reconciliation round005 | `94c824326a6c8391065c15e48aa5e5c59401b6b89dec784c53bf84fd6e12769c` |

All original manifest entries were independently verified before comparison; original files were preserved. The accepted reconciliation retains two FULL package reports and agrees on terminal command families while identifying app/model route differences. Physical hardware behavior remains unverified. The independent bounded audits checked complete original manifests and supplied Java/smali/resource copies against their originals; no scoped evidence or implementation gap remains. Cluster PR publication and tracker synchronization are coordinator-owned steps.

## Scoped corrections

The original descriptive write-mode label incorrectly calls Android numeric write type 2 “no response.” `BedBaseConnection.Request` sets 2 and passes it to the Android write API. Android `WRITE_TYPE_DEFAULT=2` is acknowledged; `WRITE_TYPE_NO_RESPONSE=1`. The explicit controller requires a characteristic with the `write` property and uses `response=True`. Numeric values and payload evidence remain unchanged. The independent bounded write-mode amendment is accepted: both complete original manifests and source copies agree, 245 exact structured corrections and seven prose lines were checked, and eleven semantic negative controls were rejected. This acceptance clears only write-mode descriptions; the separately accepted routing amendment qualifies the remaining route claims.

The OFF and TIMER labels share the packaged `massageTimer` listener. `RemoteTabBarActivity.sendCommand` remaps that action to `massageOff` only when the connected controller can set a massage timer. Richmat sets that capability; Okin does not. Therefore Lucid command claims `/protocols/0/commands/81..83` contain dead Okin off SDK branches, and model action claims 16,38,67,84,117,148,184,224 require an Okin timer-step route. The Okin UI value is 512 (`0x200`), not the off SDK value. The three terminal rows are excluded; eight model action rows are implemented with the corrected route.

Malouf's direct timer panel follows connected-controller capability. Lucid's panel follows the model's `MASSAGE TIMER SET` function. A massage-capable Richmat Forte, Altitude or persisted L600 can consequently expose direct timers in Malouf while Lucid lacks that panel. The model constructor arrays and terminal values do not change. `MassageFragment.java:325-352`, each app's `RemoteTabBarActivity.sendCommand`, `RichmatConnection.java:24-29` and the packaged `fragment_massage.xml` listener are the affected source chain. The isolated routing amendment002 and independent audit accept these corrections and their dependent reachability. Both packages were reviewed separately with authoritative smali and complete XML wiring. The original reports and amendment001 remain unchanged. A transient draft numeric concern was already corrected before amendment001 froze; its frozen timer value is 512, and no nonexistent frozen counterexample is asserted.

Good Life `All` becomes `allUp/allDown`. Richmat accepts those aliases; Okin emits no write. Lucid's original model action traces already record that difference correctly. Malouf transforms Oz preset labels into accepted endpoints; Lucid preserves the Oz label, which is unsupported on Okin. Premium READ is unsupported in Malouf and on Richmat, while Lucid maps it to the Okin lounge endpoint. The integration preserves these app/model/transport gates and exposes Lucid READ through an explicit controller button. Lucid's two unmapped Oz preset labels additionally enable a memory-2 editor after eight 250 ms hold ticks. The editor's Save dispatches setMemory2 without a constructor capacity check. All three Good Life constructors still declare zero standard memory slots. A separate Save Memory 2 button implements that proven save path on all five transports without adding generic recall or memory 1. The six Oz action rows below account for both short-release and long-hold/save behavior. The independent audit rejected seven mutations of the fallback slot, hold/editor callback, intent, constructed command, Save callback, SDK target and XML Save handler.

## Integration boundary and coverage

The profile requires an app, one of all 16 constructor model keys, a coherent transport or safe automatic selection, and the physical primary/secondary role. Fresh app picker lists are retained separately from persisted-only constructor reachability; neither app's valid persisted models are silently discarded. Shared GATT services do not identify the retail model or app. Transport selection rejects unsupported names, missing roles, duplicate roles and ambiguous service-order hybrids.

Coverage includes every command endpoint, all five packet builders, every model array, every Lucid action trace, alarm/time writes, notification guards/signed values/change-only state, save/preset/movement cadence and release, physical role bytes, discovery and configuration. Tests combine independently transcribed terminal action vectors with every transport builder, every model constructor and the distinct lifecycle/route cases. That composition proves variant-expanded command rows without duplicating identical command matrices for each byte serializer. Legacy negative light status means selected/on in the packaged app UI; the raw signed value remains diagnostic state. The custom Okin parser returns constant light 0 without reading a light field, so that app display default is covered by P07 while the integration exposes the native toggle and withholds inferred hardware light feedback.

P01 physical selector semantics are implemented: only head-up/down, head massage, flat, Zero G and Anti Snore use the configured secondary selector. HA logical left/right binding preserves the configured physical role. P01 partner routing is implemented through the documented [explicit HA action composition](../../beds/malouf-app.md#two-address-split-head-routing). A registered-service test uses real controllers and literal vectors to prove distinct main combined versus partner foot commands, fresh STOP cleanup and separate motor resources. Explicit main-only head, both-foot/STOP/preset, selected-side save and foot-massage routes are documented. Malouf Good Life All is main-only; Lucid Good Life Richmat All additionally routes partner foot. Lucid Good Life All with an Okin main has no main endpoint and a possible partner-only foot write; P04 excludes that unsafe partial combined path while retaining each standalone command. Vendor active-side selection, motor-swapped persistence and shared application UI state are application UI boundaries; no reachable physical head, foot, combined, STOP or preset endpoint is excluded for lack of an entity.

Profile reloads reconcile the current side's app button namespace and massage sensor against the selected model and transport, retaining the other side and unrelated entities. Sensor and Altitude tilt-head/full-tilt cover cleanup also cover transitions to a different bed type. Cover retirement runs before skipping unsupported motor controls, and valid Richmat Altitude covers remain available. The platform tests additionally prove that the existing feedback light entity sends its native toggle while state is unknown, with exact legacy and new transport vectors. The [card toggle](../../../custom_components/adjustable_bed/frontend/src/adjustable-bed-card.ts#L1546) dispatches `homeassistant.toggle` through that same entity path; explicit on/off still requires known feedback. These thirteen review-followup test cases supplement the controller/configuration/service audit without changing the frozen evidence or the 534 dispositions.

## Disposition totals

The ledger contains **534 rows: 473 IMPLEMENTED, 5 ALREADY_IMPLEMENTED, 56 EXCLUDED**. IMPLEMENTED identifies work added in this cluster. ALREADY_IMPLEMENTED retains an exact baseline code/test proof, while app gates and new profile exposure are separately accounted for. EXCLUDED rows below name the exact frozen evidence and valid boundary, unreachable path or safety reason.

## Code and test reference groups

Every nonexcluded row names the following concrete code and test group references. Functions are included so references remain findable if later edits move line numbers.

### MODEL

Code: [custom_components/adjustable_bed/malouf_app_protocol.py:33 (MALOUF_APP_MODELS)](../../../custom_components/adjustable_bed/malouf_app_protocol.py#L33); [custom_components/adjustable_bed/malouf_app_protocol.py:74 (APP_MODEL_OPTIONS)](../../../custom_components/adjustable_bed/malouf_app_protocol.py#L74); [custom_components/adjustable_bed/beds/malouf_app.py:274 (_require_manual)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L274); [custom_components/adjustable_bed/beds/malouf_app.py:278 (_require_function)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L278); [custom_components/adjustable_bed/beds/malouf_app.py:567 (memory_slot_count)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L567); [custom_components/adjustable_bed/beds/malouf_app.py:393 (motor_control_specs)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L393); [custom_components/adjustable_bed/button.py:709 (_button_entities_for)](../../../custom_components/adjustable_bed/button.py#L709); [custom_components/adjustable_bed/beds/malouf_app.py:796 (stale_controller_state_sensor_entity_keys)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L796); [custom_components/adjustable_bed/sensor.py:153 (_sensor_entities_for)](../../../custom_components/adjustable_bed/sensor.py#L153); [custom_components/adjustable_bed/sensor.py:269 (_async_remove_stale_sensor_entities)](../../../custom_components/adjustable_bed/sensor.py#L269); [custom_components/adjustable_bed/cover.py:199 (_cover_entities_for)](../../../custom_components/adjustable_bed/cover.py#L199); [custom_components/adjustable_bed/cover.py:265 (_async_remove_stale_cover_entities)](../../../custom_components/adjustable_bed/cover.py#L265); [custom_components/adjustable_bed/beds/malouf_app.py:454 (stale_motor_entity_keys)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L454).

Tests: [tests/test_malouf_app.py:743 (test_all_model_constructor_contracts)](../../../tests/test_malouf_app.py#L743); [tests/test_malouf_app.py:411 (test_all_persisted_models_available_but_fresh_lists_are_app_specific)](../../../tests/test_malouf_app.py#L411); [tests/test_malouf_app.py:360 (test_model_axes_memory_and_legacy_entity_retirement)](../../../tests/test_malouf_app.py#L360); [tests/test_malouf_app_entities.py:55 (test_profile_reload_reconciles_only_current_side_app_buttons)](../../../tests/test_malouf_app_entities.py#L55); [tests/test_malouf_app_entities.py:86 (test_profile_reload_reconciles_massage_sensor)](../../../tests/test_malouf_app_entities.py#L86); [tests/test_malouf_app_entities.py:152 (test_profile_reload_reconciles_altitude_covers)](../../../tests/test_malouf_app_entities.py#L152).

### PROFILE

Code: [custom_components/adjustable_bed/config_flow.py:802 (_add_malouf_app_schema_fields)](../../../custom_components/adjustable_bed/config_flow.py#L802); [custom_components/adjustable_bed/config_flow.py:826 (_malouf_app_errors)](../../../custom_components/adjustable_bed/config_flow.py#L826); [custom_components/adjustable_bed/config_flow.py:1199 (async_step_malouf_app)](../../../custom_components/adjustable_bed/config_flow.py#L1199); [custom_components/adjustable_bed/button.py:709 (_button_entities_for)](../../../custom_components/adjustable_bed/button.py#L709); [custom_components/adjustable_bed/beds/malouf_app.py:796 (stale_controller_state_sensor_entity_keys)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L796); [custom_components/adjustable_bed/sensor.py:153 (_sensor_entities_for)](../../../custom_components/adjustable_bed/sensor.py#L153); [custom_components/adjustable_bed/sensor.py:269 (_async_remove_stale_sensor_entities)](../../../custom_components/adjustable_bed/sensor.py#L269); [custom_components/adjustable_bed/cover.py:199 (_cover_entities_for)](../../../custom_components/adjustable_bed/cover.py#L199); [custom_components/adjustable_bed/cover.py:265 (_async_remove_stale_cover_entities)](../../../custom_components/adjustable_bed/cover.py#L265); [custom_components/adjustable_bed/beds/malouf_app.py:454 (stale_motor_entity_keys)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L454).

Tests: [tests/test_malouf_app_config.py:38 (test_setup_routes_require_app_and_model)](../../../tests/test_malouf_app_config.py#L38); [tests/test_malouf_app_config.py:69 (test_options_preserve_explicit_app_and_role)](../../../tests/test_malouf_app_config.py#L69); [tests/test_malouf_app_config.py:104 (test_pair_common_settings_keep_distinct_app_models_and_roles)](../../../tests/test_malouf_app_config.py#L104); [tests/test_malouf_app_config.py:126 (test_factory_forwards_explicit_profile)](../../../tests/test_malouf_app_config.py#L126); [tests/test_malouf_app_entities.py:55 (test_profile_reload_reconciles_only_current_side_app_buttons)](../../../tests/test_malouf_app_entities.py#L55); [tests/test_malouf_app_entities.py:86 (test_profile_reload_reconciles_massage_sensor)](../../../tests/test_malouf_app_entities.py#L86); [tests/test_malouf_app_entities.py:152 (test_profile_reload_reconciles_altitude_covers)](../../../tests/test_malouf_app_entities.py#L152).

### FRAME

Code: [custom_components/adjustable_bed/malouf_app_protocol.py:203 (command_frame)](../../../custom_components/adjustable_bed/malouf_app_protocol.py#L203); [custom_components/adjustable_bed/beds/malouf_app.py:196 (_frames)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L196); [custom_components/adjustable_bed/beds/malouf_app.py:178 (write_command)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L178).

Tests: [tests/test_malouf_app.py:88 (test_artifact_command_vectors)](../../../tests/test_malouf_app.py#L88); [tests/test_malouf_app.py:793 (test_all_reachable_richmat_action_vectors)](../../../tests/test_malouf_app.py#L793); [tests/test_malouf_app.py:834 (test_all_reachable_okin_action_vectors)](../../../tests/test_malouf_app.py#L834).

### MOTION

Code: [custom_components/adjustable_bed/beds/malouf_app.py:225 (_motion)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L225); [custom_components/adjustable_bed/beds/malouf_app.py:218 (_send_stop)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L218); [custom_components/adjustable_bed/beds/malouf_app.py:294 (move_head_up)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L294); [custom_components/adjustable_bed/beds/malouf_app.py:314 (move_feet_up)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L314); [custom_components/adjustable_bed/beds/malouf_app.py:334 (move_tilt_up)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L334); [custom_components/adjustable_bed/beds/malouf_app.py:345 (move_lumbar_up)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L345); [custom_components/adjustable_bed/beds/malouf_app.py:480 (move_simultaneously)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L480); [custom_components/adjustable_bed/cover.py:199 (_cover_entities_for)](../../../custom_components/adjustable_bed/cover.py#L199); [custom_components/adjustable_bed/cover.py:265 (_async_remove_stale_cover_entities)](../../../custom_components/adjustable_bed/cover.py#L265); [custom_components/adjustable_bed/beds/malouf_app.py:454 (stale_motor_entity_keys)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L454).

Tests: [tests/test_malouf_app.py:917 (test_timed_combined_motion_ceiling_stops_refresh_before_release)](../../../tests/test_malouf_app.py#L917); [tests/test_malouf_app.py:935 (test_timed_combined_motion_preserves_controller_timeout_and_still_releases)](../../../tests/test_malouf_app.py#L935); [tests/test_malouf_app.py:953 (test_timed_motion_preserves_controller_timeout_during_deadline_cancellation)](../../../tests/test_malouf_app.py#L953); [tests/test_malouf_app.py:180 (test_real_motion_lifecycle_acknowledged_hold_and_release)](../../../tests/test_malouf_app.py#L180); [tests/test_malouf_app.py:197 (test_motion_cancellation_still_sends_uncancelled_stop)](../../../tests/test_malouf_app.py#L197); [tests/test_malouf_app.py:793 (test_all_reachable_richmat_action_vectors)](../../../tests/test_malouf_app.py#L793); [tests/test_malouf_app.py:834 (test_all_reachable_okin_action_vectors)](../../../tests/test_malouf_app.py#L834); [tests/test_malouf_app.py:382 (test_dual_moves_only_proven_same_direction_axes)](../../../tests/test_malouf_app.py#L382); [tests/test_malouf_app_entities.py:152 (test_profile_reload_reconciles_altitude_covers)](../../../tests/test_malouf_app_entities.py#L152).

### PRESET

Code: [custom_components/adjustable_bed/beds/malouf_app.py:262 (_preset)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L262); [custom_components/adjustable_bed/beds/malouf_app.py:512 (preset_flat)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L512); [custom_components/adjustable_bed/beds/malouf_app.py:515 (preset_zero_g)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L515); [custom_components/adjustable_bed/beds/malouf_app.py:520 (preset_anti_snore)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L520); [custom_components/adjustable_bed/beds/malouf_app.py:525 (preset_tv)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L525); [custom_components/adjustable_bed/beds/malouf_app.py:530 (preset_lounge)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L530); [custom_components/adjustable_bed/beds/malouf_app.py:582 (preset_memory)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L582).

Tests: [tests/test_malouf_app.py:228 (test_variant_specific_preset_repeats_and_stop)](../../../tests/test_malouf_app.py#L228); [tests/test_malouf_app.py:793 (test_all_reachable_richmat_action_vectors)](../../../tests/test_malouf_app.py#L793); [tests/test_malouf_app.py:834 (test_all_reachable_okin_action_vectors)](../../../tests/test_malouf_app.py#L834).

### SAVE

Code: [custom_components/adjustable_bed/beds/malouf_app.py:586 (program_memory)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L586); [custom_components/adjustable_bed/beds/malouf_app.py:578 (_validate_memory)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L578); [custom_components/adjustable_bed/beds/malouf_app.py:590 (_save_memory)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L590).

Tests: [tests/test_malouf_app.py:277 (test_memory_save_exact_hold_count_initial_delay_and_no_stop)](../../../tests/test_malouf_app.py#L277); [tests/test_malouf_app.py:291 (test_memory1_normal_name_has_no_save_bit_and_cancellation_has_no_invented_stop)](../../../tests/test_malouf_app.py#L291); [tests/test_malouf_app.py:858 (test_okin_memory_save_values_on_every_variant)](../../../tests/test_malouf_app.py#L858); [tests/test_malouf_app.py:793 (test_all_reachable_richmat_action_vectors)](../../../tests/test_malouf_app.py#L793).

### MASSAGE

Code: [custom_components/adjustable_bed/beds/malouf_app.py:643 (supports_massage)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L643); [custom_components/adjustable_bed/beds/malouf_app.py:673 (supports_massage_timer)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L673); [custom_components/adjustable_bed/beds/malouf_app.py:651 (supports_massage_off_control)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L651); [custom_components/adjustable_bed/beds/malouf_app.py:655 (supports_massage_toggle_control)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L655); [custom_components/adjustable_bed/beds/malouf_app.py:684 (massage_off)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L684); [custom_components/adjustable_bed/beds/malouf_app.py:689 (massage_toggle)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L689); [custom_components/adjustable_bed/beds/malouf_app.py:694 (massage_head_toggle)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L694); [custom_components/adjustable_bed/beds/malouf_app.py:698 (massage_foot_toggle)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L698); [custom_components/adjustable_bed/beds/malouf_app.py:702 (massage_mode_step)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L702); [custom_components/adjustable_bed/beds/malouf_app.py:706 (set_massage_timer)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L706).

Tests: [tests/test_malouf_app.py:574 (test_massage_timer_visibility_and_shared_listener_gate)](../../../tests/test_malouf_app.py#L574); [tests/test_malouf_app.py:315 (test_richmat_reachable_massage_commands)](../../../tests/test_malouf_app.py#L315); [tests/test_malouf_app.py:322 (test_richmat_direct_timer_opcode_order)](../../../tests/test_malouf_app.py#L322); [tests/test_malouf_app.py:793 (test_all_reachable_richmat_action_vectors)](../../../tests/test_malouf_app.py#L793); [tests/test_malouf_app.py:834 (test_all_reachable_okin_action_vectors)](../../../tests/test_malouf_app.py#L834).

### LIGHT

Code: [custom_components/adjustable_bed/beds/malouf_app.py:608 (supports_lights)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L608); [custom_components/adjustable_bed/beds/malouf_app.py:616 (supports_light_state_feedback)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L616); [custom_components/adjustable_bed/beds/malouf_app.py:638 (lights_toggle)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L638); [custom_components/adjustable_bed/beds/malouf_app.py:624 (lights_on)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L624); [custom_components/adjustable_bed/beds/malouf_app.py:631 (lights_off)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L631); [custom_components/adjustable_bed/beds/malouf_app.py:847 (get_light_state)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L847); [custom_components/adjustable_bed/light.py:440 (async_toggle)](../../../custom_components/adjustable_bed/light.py#L440).

Tests: [tests/test_malouf_app.py:609 (test_feedback_light_power_uses_known_state_and_native_toggle)](../../../tests/test_malouf_app.py#L609); [tests/test_malouf_app.py:550 (test_custom_notifications_do_not_claim_light_feedback)](../../../tests/test_malouf_app.py#L550); [tests/test_malouf_app.py:901 (test_legacy_light_boolean_matches_artifact_ui_nonzero_selection)](../../../tests/test_malouf_app.py#L901); [tests/test_malouf_app.py:793 (test_all_reachable_richmat_action_vectors)](../../../tests/test_malouf_app.py#L793); [tests/test_malouf_app.py:834 (test_all_reachable_okin_action_vectors)](../../../tests/test_malouf_app.py#L834); [tests/test_malouf_app_entities.py:129 (test_feedback_light_entity_toggles_without_initial_state)](../../../tests/test_malouf_app_entities.py#L129).

### STATE

Code: [custom_components/adjustable_bed/malouf_app_protocol.py:272 (parse_notification)](../../../custom_components/adjustable_bed/malouf_app_protocol.py#L272); [custom_components/adjustable_bed/beds/malouf_app.py:800 (start_notify)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L800); [custom_components/adjustable_bed/beds/malouf_app.py:813 (stop_notify)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L813); [custom_components/adjustable_bed/beds/malouf_app.py:821 (_notification_handler)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L821); [custom_components/adjustable_bed/beds/malouf_app.py:782 (controller_state_sensor_specs)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L782); [custom_components/adjustable_bed/beds/malouf_app.py:796 (stale_controller_state_sensor_entity_keys)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L796); [custom_components/adjustable_bed/sensor.py:153 (_sensor_entities_for)](../../../custom_components/adjustable_bed/sensor.py#L153); [custom_components/adjustable_bed/sensor.py:269 (_async_remove_stale_sensor_entities)](../../../custom_components/adjustable_bed/sensor.py#L269).

Tests: [tests/test_malouf_app.py:135 (test_artifact_parser_vectors)](../../../tests/test_malouf_app.py#L135); [tests/test_malouf_app.py:151 (test_parser_guard_mutations)](../../../tests/test_malouf_app.py#L151); [tests/test_malouf_app.py:158 (test_legacy_notification_offsets_and_timer_nibble)](../../../tests/test_malouf_app.py#L158); [tests/test_malouf_app.py:529 (test_notification_subscription_raw_forward_state_dedup_and_no_clock_on_connect)](../../../tests/test_malouf_app.py#L529); [tests/test_malouf_app.py:550 (test_custom_notifications_do_not_claim_light_feedback)](../../../tests/test_malouf_app.py#L550); [tests/test_malouf_app.py:901 (test_legacy_light_boolean_matches_artifact_ui_nonzero_selection)](../../../tests/test_malouf_app.py#L901); [tests/test_malouf_app_entities.py:86 (test_profile_reload_reconciles_massage_sensor)](../../../tests/test_malouf_app_entities.py#L86).

### QUERY

Code: [custom_components/adjustable_bed/beds/malouf_app.py:206 (_action)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L206).

Tests: [tests/test_malouf_app.py:338 (test_new_telemetry_query_only_after_reachable_state_actions)](../../../tests/test_malouf_app.py#L338).

### CLOCK

Code: [custom_components/adjustable_bed/malouf_app_protocol.py:219 (clock_frame)](../../../custom_components/adjustable_bed/malouf_app_protocol.py#L219); [custom_components/adjustable_bed/beds/malouf_app.py:731 (sync_clock)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L731); [custom_components/adjustable_bed/services.py:1660 (handle_malouf_sync_clock)](../../../custom_components/adjustable_bed/services.py#L1660).

Tests: [tests/test_malouf_app.py:112 (test_artifact_clock_alarm_vectors)](../../../tests/test_malouf_app.py#L112); [tests/test_malouf_app.py:470 (test_alarm_sync_then_weekly_program_and_exact_clear)](../../../tests/test_malouf_app.py#L470); [tests/test_malouf_app_services.py:95 (test_clock_sync_is_serialized)](../../../tests/test_malouf_app_services.py#L95).

### ALARM

Code: [custom_components/adjustable_bed/malouf_app_protocol.py:193 (ALARM_TYPES)](../../../custom_components/adjustable_bed/malouf_app_protocol.py#L193); [custom_components/adjustable_bed/malouf_app_protocol.py:253 (alarm_frame)](../../../custom_components/adjustable_bed/malouf_app_protocol.py#L253); [custom_components/adjustable_bed/beds/malouf_app.py:741 (configure_clock_alarm)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L741); [custom_components/adjustable_bed/beds/malouf_app.py:720 (clock_alarm_preset_options)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L720); [custom_components/adjustable_bed/services.py:1622 (handle_malouf_set_alarm)](../../../custom_components/adjustable_bed/services.py#L1622).

Tests: [tests/test_malouf_app.py:112 (test_artifact_clock_alarm_vectors)](../../../tests/test_malouf_app.py#L112); [tests/test_malouf_app.py:470 (test_alarm_sync_then_weekly_program_and_exact_clear)](../../../tests/test_malouf_app.py#L470); [tests/test_malouf_app.py:493 (test_alarm_one_shot_today_or_tomorrow_without_repeat_bit)](../../../tests/test_malouf_app.py#L493); [tests/test_malouf_app.py:509 (test_invalid_alarm_has_no_clock_or_alarm_side_effect)](../../../tests/test_malouf_app.py#L509); [tests/test_malouf_app.py:885 (test_six_reachable_alarm_types)](../../../tests/test_malouf_app.py#L885); [tests/test_malouf_app.py:979 (test_alarm_clear_ignores_unused_memory_preset_capacity)](../../../tests/test_malouf_app.py#L979); [tests/test_malouf_app_services.py:46 (test_alarm_dispatches_local_time_and_weekdays)](../../../tests/test_malouf_app_services.py#L46); [tests/test_malouf_app_services.py:59 (test_clear_alarm_defaults)](../../../tests/test_malouf_app_services.py#L59); [tests/test_malouf_app_services.py:77 (test_alarm_preset_is_validated_on_every_target_before_writing)](../../../tests/test_malouf_app_services.py#L77).

### DISCOVERY

Code: [custom_components/adjustable_bed/malouf_app_protocol.py:109 (TRANSPORTS)](../../../custom_components/adjustable_bed/malouf_app_protocol.py#L109); [custom_components/adjustable_bed/beds/malouf_app.py:107 (_name_family)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L107); [custom_components/adjustable_bed/beds/malouf_app.py:128 (_resolve_transport)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L128); [custom_components/adjustable_bed/beds/malouf_app.py:175 (async_discover_capabilities)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L175).

Tests: [tests/test_malouf_app.py:426 (test_auto_rejects_order_dependent_or_unmatched_transport)](../../../tests/test_malouf_app.py#L426); [tests/test_malouf_app.py:439 (test_auto_null_name_uses_legacy_derived_family_not_user_title)](../../../tests/test_malouf_app.py#L439); [tests/test_malouf_app.py:449 (test_configured_transport_validates_actual_service_roles)](../../../tests/test_malouf_app.py#L449); [tests/test_malouf_app.py:463 (test_explicit_transport_breaks_service_order_tie_without_hybrid)](../../../tests/test_malouf_app.py#L463); [tests/test_malouf_app.py:623 (test_name_factory_precedence_and_duplicate_role_rejection)](../../../tests/test_malouf_app.py#L623).

### SELECTOR

Code: [custom_components/adjustable_bed/malouf_app_protocol.py:190 (SELECTOR_ACTIONS)](../../../custom_components/adjustable_bed/malouf_app_protocol.py#L190); [custom_components/adjustable_bed/beds/malouf_app.py:196 (_frames)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L196).

Tests: [tests/test_malouf_app.py:252 (test_only_six_secondary_actions_embed_physical_role)](../../../tests/test_malouf_app.py#L252); [tests/test_malouf_app.py:257 (test_paired_logical_side_does_not_change_configured_role)](../../../tests/test_malouf_app.py#L257).

### LABELS

Code: [custom_components/adjustable_bed/beds/malouf_app.py:282 (_has_preset)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L282); [custom_components/adjustable_bed/beds/malouf_app.py:469 (supports_simultaneous_movement)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L469); [custom_components/adjustable_bed/beds/malouf_app.py:536 (controller_button_specs)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L536); [custom_components/adjustable_bed/beds/malouf_app.py:547 (preset_read)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L547); [custom_components/adjustable_bed/beds/malouf_app.py:375 (execute_app_control)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L375); [custom_components/adjustable_bed/beds/malouf_app.py:393 (motor_control_specs)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L393); [custom_components/adjustable_bed/button.py:709 (_button_entities_for)](../../../custom_components/adjustable_bed/button.py#L709); [custom_components/adjustable_bed/cover.py:199 (_cover_entities_for)](../../../custom_components/adjustable_bed/cover.py#L199); [custom_components/adjustable_bed/cover.py:265 (_async_remove_stale_cover_entities)](../../../custom_components/adjustable_bed/cover.py#L265); [custom_components/adjustable_bed/beds/malouf_app.py:454 (stale_motor_entity_keys)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L454).

Tests: [tests/test_malouf_app.py:395 (test_profile_specific_preset_terminal_dispositions)](../../../tests/test_malouf_app.py#L395); [tests/test_malouf_app.py:584 (test_goodlife_all_label_does_not_invent_okin_dual_alias)](../../../tests/test_malouf_app.py#L584); [tests/test_malouf_app.py:372 (test_altitude_distinct_literal_actions_and_no_invented_height)](../../../tests/test_malouf_app.py#L372); [tests/test_malouf_app.py:592 (test_callback_specs_invoke_current_controller_after_reconnect)](../../../tests/test_malouf_app.py#L592); [tests/test_malouf_app.py:834 (test_all_reachable_okin_action_vectors)](../../../tests/test_malouf_app.py#L834); [tests/test_malouf_app_entities.py:55 (test_profile_reload_reconciles_only_current_side_app_buttons)](../../../tests/test_malouf_app_entities.py#L55); [tests/test_malouf_app_entities.py:152 (test_profile_reload_reconciles_altitude_covers)](../../../tests/test_malouf_app_entities.py#L152).

### OZ_SAVE

Code: [custom_components/adjustable_bed/beds/malouf_app.py:553 (_has_oz_memory_editor)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L553); [custom_components/adjustable_bed/beds/malouf_app.py:536 (controller_button_specs)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L536); [custom_components/adjustable_bed/beds/malouf_app.py:560 (save_oz_memory_position)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L560); [custom_components/adjustable_bed/beds/malouf_app.py:590 (_save_memory)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L590); [custom_components/adjustable_bed/beds/malouf_app.py:375 (execute_app_control)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L375); [custom_components/adjustable_bed/button.py:709 (_button_entities_for)](../../../custom_components/adjustable_bed/button.py#L709).

Tests: [tests/test_malouf_app.py:998 (test_lucid_oz_long_hold_editor_slot2_save_vectors)](../../../tests/test_malouf_app.py#L998); [tests/test_malouf_app.py:1039 (test_oz_memory_editor_is_restricted_to_exact_lucid_models)](../../../tests/test_malouf_app.py#L1039); [tests/test_malouf_app.py:1047 (test_oz_memory_editor_callback_uses_current_controller)](../../../tests/test_malouf_app.py#L1047); [tests/test_malouf_app_entities.py:55 (test_profile_reload_reconciles_only_current_side_app_buttons)](../../../tests/test_malouf_app_entities.py#L55).

### PARTNER

Code: [custom_components/adjustable_bed/services.py:1210 (handle_linak_move_simultaneously)](../../../custom_components/adjustable_bed/services.py#L1210); [custom_components/adjustable_bed/services.py:1116 (handle_timed_move)](../../../custom_components/adjustable_bed/services.py#L1116); [custom_components/adjustable_bed/services.py:523 (handle_goto_preset)](../../../custom_components/adjustable_bed/services.py#L523); [custom_components/adjustable_bed/services.py:643 (handle_stop_all)](../../../custom_components/adjustable_bed/services.py#L643); [custom_components/adjustable_bed/beds/malouf_app.py:480 (move_simultaneously)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L480); [custom_components/adjustable_bed/beds/malouf_app.py:225 (_motion)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L225); [custom_components/adjustable_bed/beds/malouf_app.py:258 (_release_motion)](../../../custom_components/adjustable_bed/beds/malouf_app.py#L258).

Tests: [tests/test_malouf_app_services.py:112 (test_explicit_split_head_actions_route_main_dual_and_partner_foot)](../../../tests/test_malouf_app_services.py#L112); [tests/test_malouf_app.py:584 (test_goodlife_all_label_does_not_invent_okin_dual_alias)](../../../tests/test_malouf_app.py#L584); [tests/test_malouf_app.py:793 (test_all_reachable_richmat_action_vectors)](../../../tests/test_malouf_app.py#L793); [tests/test_malouf_app.py:834 (test_all_reachable_okin_action_vectors)](../../../tests/test_malouf_app.py#L834).

## Existing baseline proofs

| ID | Exact existing code | Exact existing tests |
| --- | --- | --- |
| B01 | [custom_components/adjustable_bed/beds/malouf.py:301](../../../custom_components/adjustable_bed/beds/malouf.py#L301) | [tests/test_malouf.py:166](../../../tests/test_malouf.py#L166); [tests/test_malouf.py:184](../../../tests/test_malouf.py#L184); [tests/test_malouf.py:201](../../../tests/test_malouf.py#L201) |
| B02 | [custom_components/adjustable_bed/beds/malouf.py:644](../../../custom_components/adjustable_bed/beds/malouf.py#L644) | [tests/test_malouf.py:237](../../../tests/test_malouf.py#L237); [tests/test_malouf.py:256](../../../tests/test_malouf.py#L256); [tests/test_malouf.py:273](../../../tests/test_malouf.py#L273) |
| S01 | [custom_components/adjustable_bed/beds/malouf.py:485](../../../custom_components/adjustable_bed/beds/malouf.py#L485) | [tests/test_malouf.py:485](../../../tests/test_malouf.py#L485); [tests/test_malouf.py:542](../../../tests/test_malouf.py#L542) |
| S02 | [custom_components/adjustable_bed/beds/malouf.py:187](../../../custom_components/adjustable_bed/beds/malouf.py#L187); [custom_components/adjustable_bed/beds/malouf.py:829](../../../custom_components/adjustable_bed/beds/malouf.py#L829) | [tests/test_malouf.py:508](../../../tests/test_malouf.py#L508); [tests/test_malouf.py:562](../../../tests/test_malouf.py#L562); [tests/test_malouf.py:605](../../../tests/test_malouf.py#L605) |
| S04 | [custom_components/adjustable_bed/beds/malouf.py:440](../../../custom_components/adjustable_bed/beds/malouf.py#L440) | [tests/test_malouf.py:394](../../../tests/test_malouf.py#L394); [tests/test_malouf.py:414](../../../tests/test_malouf.py#L414); [tests/test_malouf.py:434](../../../tests/test_malouf.py#L434) |

## Complete row ledger

Each command ID retains package, one-based command index and one-based protocol index. Lucid P1 is Okin; Malouf P1 is Richmat, so the protocol index alone is never used as a family identifier. Model/action indices also retain frozen order. A no-write route may be IMPLEMENTED when the integration explicitly prevents the unsupported app action; its underlying SDK-only terminal remains EXCLUDED.

| ID | Behavior | Disposition | Code/test groups | Frozen source |
| --- | --- | --- | --- | --- |
| malouf-command-001-p1 | richmat: headUp | IMPLEMENTED | FRAME, MOTION | `M#/protocols/0/commands/0` |
| malouf-command-002-p1 | richmat: headDown | IMPLEMENTED | FRAME, MOTION | `M#/protocols/0/commands/1` |
| malouf-command-003-p1 | richmat: footUp | IMPLEMENTED | FRAME, MOTION | `M#/protocols/0/commands/2` |
| malouf-command-004-p1 | richmat: footDown | IMPLEMENTED | FRAME, MOTION | `M#/protocols/0/commands/3` |
| malouf-command-005-p1 | richmat: dualUp/allUp | IMPLEMENTED | FRAME, MOTION | `M#/protocols/0/commands/4` |
| malouf-command-006-p1 | richmat: dualDown/allDown | IMPLEMENTED | FRAME, MOTION | `M#/protocols/0/commands/5` |
| malouf-command-007-p1 | richmat: setMemory1 | IMPLEMENTED | FRAME, SAVE | `M#/protocols/0/commands/6` |
| malouf-command-008-p1 | richmat: setMemory2 | IMPLEMENTED | FRAME, SAVE | `M#/protocols/0/commands/7` |
| malouf-command-009-p1 | richmat: setMemory3 | EXCLUDED |  | `M#/protocols/0/commands/8` |
| malouf-command-010-p1 | richmat: memory1/Memory 1 | IMPLEMENTED | FRAME, PRESET, LABELS | `M#/protocols/0/commands/9` |
| malouf-command-011-p1 | richmat: memory2/Memory 2 | IMPLEMENTED | FRAME, PRESET, LABELS | `M#/protocols/0/commands/10` |
| malouf-command-012-p1 | richmat: memory3 | EXCLUDED |  | `M#/protocols/0/commands/11` |
| malouf-command-013-p1 | richmat: allFlat | IMPLEMENTED | FRAME, PRESET, LABELS | `M#/protocols/0/commands/12` |
| malouf-command-014-p1 | richmat: lightSwitch | IMPLEMENTED | FRAME, LIGHT | `M#/protocols/0/commands/13` |
| malouf-command-015-p1 | richmat: fullTiltUp/headTiltUp | IMPLEMENTED | FRAME, MOTION | `M#/protocols/0/commands/14` |
| malouf-command-016-p1 | richmat: fullTiltDown/headTiltDown | IMPLEMENTED | FRAME, MOTION | `M#/protocols/0/commands/15` |
| malouf-command-017-p1 | richmat: tiltHeadUp/lumbarUp | IMPLEMENTED | FRAME, MOTION | `M#/protocols/0/commands/16` |
| malouf-command-018-p1 | richmat: tiltHeadDown/lumbarDown | IMPLEMENTED | FRAME, MOTION | `M#/protocols/0/commands/17` |
| malouf-command-019-p1 | richmat: zeroG/Zero G/Oz Spine Relief | IMPLEMENTED | FRAME, PRESET, LABELS | `M#/protocols/0/commands/18` |
| malouf-command-020-p1 | richmat: antiSnore/Anti Snore/Oz Anti Snore | IMPLEMENTED | FRAME, PRESET, LABELS | `M#/protocols/0/commands/19` |
| malouf-command-021-p1 | richmat: massageOff | IMPLEMENTED | FRAME, MASSAGE | `M#/protocols/0/commands/20` |
| malouf-command-022-p1 | richmat: massageWave | IMPLEMENTED | FRAME, MASSAGE | `M#/protocols/0/commands/21` |
| malouf-command-023-p1 | richmat: massageHead | IMPLEMENTED | FRAME, MASSAGE | `M#/protocols/0/commands/22` |
| malouf-command-024-p1 | richmat: massageFoot | IMPLEMENTED | FRAME, MASSAGE | `M#/protocols/0/commands/23` |
| malouf-command-025-p1 | richmat: tvRead/TV Read/TV | IMPLEMENTED | FRAME, PRESET, LABELS | `M#/protocols/0/commands/24` |
| malouf-command-026-p1 | richmat: lounge/Lounge | IMPLEMENTED | FRAME, PRESET, LABELS | `M#/protocols/0/commands/25` |
| malouf-command-027-p1 | richmat: massage10 | IMPLEMENTED | FRAME, MASSAGE | `M#/protocols/0/commands/26` |
| malouf-command-028-p1 | richmat: massage30 | IMPLEMENTED | FRAME, MASSAGE | `M#/protocols/0/commands/27` |
| malouf-command-029-p1 | richmat: massage20 | IMPLEMENTED | FRAME, MASSAGE | `M#/protocols/0/commands/28` |
| malouf-command-030-p1 | richmat: stopDriver | IMPLEMENTED | FRAME, MOTION | `M#/protocols/0/commands/29` |
| malouf-command-001-p2 | okin: stopDriver | IMPLEMENTED | FRAME, MOTION | `M#/protocols/1/commands/0` |
| malouf-command-002-p2 | okin: headUp | IMPLEMENTED | FRAME, MOTION | `M#/protocols/1/commands/1` |
| malouf-command-003-p2 | okin: headDown | IMPLEMENTED | FRAME, MOTION | `M#/protocols/1/commands/2` |
| malouf-command-004-p2 | okin: footUp | IMPLEMENTED | FRAME, MOTION | `M#/protocols/1/commands/3` |
| malouf-command-005-p2 | okin: dualUp | IMPLEMENTED | FRAME, MOTION | `M#/protocols/1/commands/4` |
| malouf-command-006-p2 | okin: footDown | IMPLEMENTED | FRAME, MOTION | `M#/protocols/1/commands/5` |
| malouf-command-007-p2 | okin: dualDown | IMPLEMENTED | FRAME, MOTION | `M#/protocols/1/commands/6` |
| malouf-command-008-p2 | okin: headTiltUp/headTiltDown | IMPLEMENTED | FRAME, MOTION | `M#/protocols/1/commands/7` |
| malouf-command-009-p2 | okin: lumbarUp/lumbarDown | IMPLEMENTED | FRAME, MOTION | `M#/protocols/1/commands/8` |
| malouf-command-010-p2 | okin: massageAll | EXCLUDED |  | `M#/protocols/1/commands/9` |
| malouf-command-011-p2 | okin: massageTimer | IMPLEMENTED | FRAME, MASSAGE | `M#/protocols/1/commands/10` |
| malouf-command-012-p2 | okin: massageFoot | IMPLEMENTED | FRAME, MASSAGE | `M#/protocols/1/commands/11` |
| malouf-command-013-p2 | okin: massageHead | IMPLEMENTED | FRAME, MASSAGE | `M#/protocols/1/commands/12` |
| malouf-command-014-p2 | okin: zeroG | IMPLEMENTED | FRAME, PRESET, LABELS | `M#/protocols/1/commands/13` |
| malouf-command-015-p2 | okin: lounge/Lounge | IMPLEMENTED | FRAME, PRESET, LABELS | `M#/protocols/1/commands/14` |
| malouf-command-016-p2 | okin: read/Read | EXCLUDED |  | `M#/protocols/1/commands/15` |
| malouf-command-017-p2 | okin: tvRead | IMPLEMENTED | FRAME, PRESET, LABELS | `M#/protocols/1/commands/16` |
| malouf-command-018-p2 | okin: TV Read/tv/TV | EXCLUDED |  | `M#/protocols/1/commands/17` |
| malouf-command-019-p2 | okin: antiSnore | IMPLEMENTED | FRAME, PRESET, LABELS | `M#/protocols/1/commands/18` |
| malouf-command-020-p2 | okin: memory1/Memory 1 | IMPLEMENTED | FRAME, PRESET, LABELS | `M#/protocols/1/commands/19` |
| malouf-command-021-p2 | okin: lightSwitch | IMPLEMENTED | FRAME, LIGHT | `M#/protocols/1/commands/20` |
| malouf-command-022-p2 | okin: memory2/Memory 2 | IMPLEMENTED | FRAME, PRESET, LABELS | `M#/protocols/1/commands/21` |
| malouf-command-023-p2 | okin: intensityOne | EXCLUDED |  | `M#/protocols/1/commands/22` |
| malouf-command-024-p2 | okin: intensityTwo | EXCLUDED |  | `M#/protocols/1/commands/23` |
| malouf-command-025-p2 | okin: intensityThree | EXCLUDED |  | `M#/protocols/1/commands/24` |
| malouf-command-026-p2 | okin: massageWaist | EXCLUDED |  | `M#/protocols/1/commands/25` |
| malouf-command-027-p2 | okin: massageHeadMinus | EXCLUDED |  | `M#/protocols/1/commands/26` |
| malouf-command-028-p2 | okin: massageFootMinus | EXCLUDED |  | `M#/protocols/1/commands/27` |
| malouf-command-029-p2 | okin: massageStopAll | EXCLUDED |  | `M#/protocols/1/commands/28` |
| malouf-command-030-p2 | okin: massageOff | EXCLUDED |  | `M#/protocols/1/commands/29` |
| malouf-command-031-p2 | okin: massageAllOnOff | EXCLUDED |  | `M#/protocols/1/commands/30` |
| malouf-command-032-p2 | okin: allFlat | IMPLEMENTED | FRAME, PRESET, LABELS | `M#/protocols/1/commands/31` |
| malouf-command-033-p2 | okin: massageWaistMinus | EXCLUDED |  | `M#/protocols/1/commands/32` |
| malouf-command-034-p2 | okin: massageWave | IMPLEMENTED | FRAME, MASSAGE | `M#/protocols/1/commands/33` |
| malouf-command-035-p2 | okin: setMemory1 | IMPLEMENTED | FRAME, SAVE | `M#/protocols/1/commands/34` |
| malouf-command-036-p2 | okin: setMemory2 | IMPLEMENTED | FRAME, SAVE | `M#/protocols/1/commands/35` |
| malouf-command-037-p2 | okin: setCurrentTime | IMPLEMENTED | FRAME, CLOCK | `M#/protocols/1/commands/36` |
| malouf-command-038-p2 | okin: setAlarm/clearAlarm | IMPLEMENTED | FRAME, ALARM | `M#/protocols/1/commands/37` |
| malouf-command-039-p2 | okin: query light/massage status | IMPLEMENTED | FRAME, QUERY | `M#/protocols/1/commands/38` |
| malouf-model-01 | Altitude | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `M#/model_mappings/0` |
| malouf-model-02 | E450 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `M#/model_mappings/1` |
| malouf-model-03 | E455 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `M#/model_mappings/2` |
| malouf-model-04 | Forte | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `M#/model_mappings/3` |
| malouf-model-05 | Good Life Base | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE, OZ_SAVE | `M#/model_mappings/4` |
| malouf-model-06 | Good Life Premier Base | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE, OZ_SAVE | `M#/model_mappings/5` |
| malouf-model-07 | Good Life Pro Base | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE, OZ_SAVE | `M#/model_mappings/6` |
| malouf-model-08 | L300 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `M#/model_mappings/7` |
| malouf-model-09 | L600 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `M#/model_mappings/8` |
| malouf-model-10 | M455 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `M#/model_mappings/9` |
| malouf-model-11 | M550 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `M#/model_mappings/10` |
| malouf-model-12 | M555 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `M#/model_mappings/11` |
| malouf-model-13 | Premium | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `M#/model_mappings/12` |
| malouf-model-14 | S655 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `M#/model_mappings/13` |
| malouf-model-15 | S750 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `M#/model_mappings/14` |
| malouf-model-16 | S755 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `M#/model_mappings/15` |
| lucid-command-001-p1 | okin: headUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/0` |
| lucid-command-002-p1 | okin: headUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/1` |
| lucid-command-003-p1 | okin: headUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/2` |
| lucid-command-004-p1 | okin: headDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/3` |
| lucid-command-005-p1 | okin: headDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/4` |
| lucid-command-006-p1 | okin: headDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/5` |
| lucid-command-007-p1 | okin: footUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/6` |
| lucid-command-008-p1 | okin: footUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/7` |
| lucid-command-009-p1 | okin: footUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/8` |
| lucid-command-010-p1 | okin: footDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/9` |
| lucid-command-011-p1 | okin: footDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/10` |
| lucid-command-012-p1 | okin: footDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/11` |
| lucid-command-013-p1 | okin: dualUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/12` |
| lucid-command-014-p1 | okin: dualUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/13` |
| lucid-command-015-p1 | okin: dualUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/14` |
| lucid-command-016-p1 | okin: dualDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/15` |
| lucid-command-017-p1 | okin: dualDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/16` |
| lucid-command-018-p1 | okin: dualDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/17` |
| lucid-command-019-p1 | okin: headTiltUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/18` |
| lucid-command-020-p1 | okin: headTiltUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/19` |
| lucid-command-021-p1 | okin: headTiltUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/20` |
| lucid-command-022-p1 | okin: headTiltDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/21` |
| lucid-command-023-p1 | okin: headTiltDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/22` |
| lucid-command-024-p1 | okin: headTiltDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/23` |
| lucid-command-025-p1 | okin: lumbarUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/24` |
| lucid-command-026-p1 | okin: lumbarUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/25` |
| lucid-command-027-p1 | okin: lumbarUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/26` |
| lucid-command-028-p1 | okin: lumbarDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/27` |
| lucid-command-029-p1 | okin: lumbarDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/28` |
| lucid-command-030-p1 | okin: lumbarDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/29` |
| lucid-command-031-p1 | okin: massageAll | EXCLUDED |  | `L#/protocols/0/commands/30` |
| lucid-command-032-p1 | okin: massageAll | EXCLUDED |  | `L#/protocols/0/commands/31` |
| lucid-command-033-p1 | okin: massageAll | EXCLUDED |  | `L#/protocols/0/commands/32` |
| lucid-command-034-p1 | okin: massageTimer | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/0/commands/33` |
| lucid-command-035-p1 | okin: massageTimer | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/0/commands/34` |
| lucid-command-036-p1 | okin: massageTimer | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/0/commands/35` |
| lucid-command-037-p1 | okin: massageFoot | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/0/commands/36` |
| lucid-command-038-p1 | okin: massageFoot | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/0/commands/37` |
| lucid-command-039-p1 | okin: massageFoot | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/0/commands/38` |
| lucid-command-040-p1 | okin: massageHead | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/0/commands/39` |
| lucid-command-041-p1 | okin: massageHead | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/0/commands/40` |
| lucid-command-042-p1 | okin: massageHead | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/0/commands/41` |
| lucid-command-043-p1 | okin: zeroG  /  Zero G | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/42` |
| lucid-command-044-p1 | okin: zeroG  /  Zero G | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/43` |
| lucid-command-045-p1 | okin: zeroG  /  Zero G | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/44` |
| lucid-command-046-p1 | okin: lounge  /  Lounge  /  read  /  Read | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/45` |
| lucid-command-047-p1 | okin: lounge  /  Lounge  /  read  /  Read | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/46` |
| lucid-command-048-p1 | okin: lounge  /  Lounge  /  read  /  Read | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/47` |
| lucid-command-049-p1 | okin: tv  /  TV  /  tvRead  /  TV Read | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/48` |
| lucid-command-050-p1 | okin: tv  /  TV  /  tvRead  /  TV Read | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/49` |
| lucid-command-051-p1 | okin: tv  /  TV  /  tvRead  /  TV Read | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/50` |
| lucid-command-052-p1 | okin: antiSnore  /  Anti Snore | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/51` |
| lucid-command-053-p1 | okin: antiSnore  /  Anti Snore | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/52` |
| lucid-command-054-p1 | okin: antiSnore  /  Anti Snore | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/53` |
| lucid-command-055-p1 | okin: memory1  /  Memory 1 | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/54` |
| lucid-command-056-p1 | okin: memory1  /  Memory 1 | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/55` |
| lucid-command-057-p1 | okin: memory1  /  Memory 1 | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/56` |
| lucid-command-058-p1 | okin: lightSwitch | IMPLEMENTED | FRAME, LIGHT | `L#/protocols/0/commands/57` |
| lucid-command-059-p1 | okin: lightSwitch | IMPLEMENTED | FRAME, LIGHT | `L#/protocols/0/commands/58` |
| lucid-command-060-p1 | okin: lightSwitch | IMPLEMENTED | FRAME, LIGHT | `L#/protocols/0/commands/59` |
| lucid-command-061-p1 | okin: memory2  /  Memory 2 | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/60` |
| lucid-command-062-p1 | okin: memory2  /  Memory 2 | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/61` |
| lucid-command-063-p1 | okin: memory2  /  Memory 2 | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/62` |
| lucid-command-064-p1 | okin: intensityOne | EXCLUDED |  | `L#/protocols/0/commands/63` |
| lucid-command-065-p1 | okin: intensityOne | EXCLUDED |  | `L#/protocols/0/commands/64` |
| lucid-command-066-p1 | okin: intensityOne | EXCLUDED |  | `L#/protocols/0/commands/65` |
| lucid-command-067-p1 | okin: intensityTwo | EXCLUDED |  | `L#/protocols/0/commands/66` |
| lucid-command-068-p1 | okin: intensityTwo | EXCLUDED |  | `L#/protocols/0/commands/67` |
| lucid-command-069-p1 | okin: intensityTwo | EXCLUDED |  | `L#/protocols/0/commands/68` |
| lucid-command-070-p1 | okin: intensityThree | EXCLUDED |  | `L#/protocols/0/commands/69` |
| lucid-command-071-p1 | okin: intensityThree | EXCLUDED |  | `L#/protocols/0/commands/70` |
| lucid-command-072-p1 | okin: intensityThree | EXCLUDED |  | `L#/protocols/0/commands/71` |
| lucid-command-073-p1 | okin: massageWaist | EXCLUDED |  | `L#/protocols/0/commands/72` |
| lucid-command-074-p1 | okin: massageWaist | EXCLUDED |  | `L#/protocols/0/commands/73` |
| lucid-command-075-p1 | okin: massageWaist | EXCLUDED |  | `L#/protocols/0/commands/74` |
| lucid-command-076-p1 | okin: massageHeadMinus | EXCLUDED |  | `L#/protocols/0/commands/75` |
| lucid-command-077-p1 | okin: massageHeadMinus | EXCLUDED |  | `L#/protocols/0/commands/76` |
| lucid-command-078-p1 | okin: massageHeadMinus | EXCLUDED |  | `L#/protocols/0/commands/77` |
| lucid-command-079-p1 | okin: massageFootMinus | EXCLUDED |  | `L#/protocols/0/commands/78` |
| lucid-command-080-p1 | okin: massageFootMinus | EXCLUDED |  | `L#/protocols/0/commands/79` |
| lucid-command-081-p1 | okin: massageFootMinus | EXCLUDED |  | `L#/protocols/0/commands/80` |
| lucid-command-082-p1 | okin: massageStopAll  /  massageOff | EXCLUDED |  | `L#/protocols/0/commands/81` |
| lucid-command-083-p1 | okin: massageStopAll  /  massageOff | EXCLUDED |  | `L#/protocols/0/commands/82` |
| lucid-command-084-p1 | okin: massageStopAll  /  massageOff | EXCLUDED |  | `L#/protocols/0/commands/83` |
| lucid-command-085-p1 | okin: massageAllOnOff | EXCLUDED |  | `L#/protocols/0/commands/84` |
| lucid-command-086-p1 | okin: massageAllOnOff | EXCLUDED |  | `L#/protocols/0/commands/85` |
| lucid-command-087-p1 | okin: massageAllOnOff | EXCLUDED |  | `L#/protocols/0/commands/86` |
| lucid-command-088-p1 | okin: allFlat | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/87` |
| lucid-command-089-p1 | okin: allFlat | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/88` |
| lucid-command-090-p1 | okin: allFlat | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/0/commands/89` |
| lucid-command-091-p1 | okin: massageWave  /  massageWaistMinus | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/0/commands/90` |
| lucid-command-092-p1 | okin: massageWave  /  massageWaistMinus | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/0/commands/91` |
| lucid-command-093-p1 | okin: massageWave  /  massageWaistMinus | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/0/commands/92` |
| lucid-command-094-p1 | okin: stopDriver | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/93` |
| lucid-command-095-p1 | okin: stopDriver | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/94` |
| lucid-command-096-p1 | okin: stopDriver | IMPLEMENTED | FRAME, MOTION | `L#/protocols/0/commands/95` |
| lucid-command-097-p1 | okin: setMemory1 | IMPLEMENTED | FRAME, SAVE | `L#/protocols/0/commands/96` |
| lucid-command-098-p1 | okin: setMemory1 | IMPLEMENTED | FRAME, SAVE | `L#/protocols/0/commands/97` |
| lucid-command-099-p1 | okin: setMemory1 | IMPLEMENTED | FRAME, SAVE | `L#/protocols/0/commands/98` |
| lucid-command-100-p1 | okin: setMemory2 | IMPLEMENTED | FRAME, SAVE | `L#/protocols/0/commands/99` |
| lucid-command-101-p1 | okin: setMemory2 | IMPLEMENTED | FRAME, SAVE | `L#/protocols/0/commands/100` |
| lucid-command-102-p1 | okin: setMemory2 | IMPLEMENTED | FRAME, SAVE | `L#/protocols/0/commands/101` |
| lucid-command-103-p1 | okin: setCurrentTime | IMPLEMENTED | FRAME, CLOCK | `L#/protocols/0/commands/102` |
| lucid-command-104-p1 | okin: setCurrentTime | IMPLEMENTED | FRAME, CLOCK | `L#/protocols/0/commands/103` |
| lucid-command-105-p1 | okin: setCurrentTime | IMPLEMENTED | FRAME, CLOCK | `L#/protocols/0/commands/104` |
| lucid-command-106-p1 | okin: setAlarm | IMPLEMENTED | FRAME, ALARM | `L#/protocols/0/commands/105` |
| lucid-command-107-p1 | okin: setAlarm | IMPLEMENTED | FRAME, ALARM | `L#/protocols/0/commands/106` |
| lucid-command-108-p1 | okin: setAlarm | IMPLEMENTED | FRAME, ALARM | `L#/protocols/0/commands/107` |
| lucid-command-109-p1 | okin: clearAlarm | IMPLEMENTED | FRAME, ALARM | `L#/protocols/0/commands/108` |
| lucid-command-110-p1 | okin: clearAlarm | IMPLEMENTED | FRAME, ALARM | `L#/protocols/0/commands/109` |
| lucid-command-111-p1 | okin: clearAlarm | IMPLEMENTED | FRAME, ALARM | `L#/protocols/0/commands/110` |
| lucid-command-112-p1 | okin: queryLightAndMassageStatus | IMPLEMENTED | FRAME, QUERY | `L#/protocols/0/commands/111` |
| lucid-command-001-p2 | richmat: headUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/0` |
| lucid-command-002-p2 | richmat: headUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/1` |
| lucid-command-003-p2 | richmat: headDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/2` |
| lucid-command-004-p2 | richmat: headDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/3` |
| lucid-command-005-p2 | richmat: footUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/4` |
| lucid-command-006-p2 | richmat: footUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/5` |
| lucid-command-007-p2 | richmat: footDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/6` |
| lucid-command-008-p2 | richmat: footDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/7` |
| lucid-command-009-p2 | richmat: dualUp  /  allUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/8` |
| lucid-command-010-p2 | richmat: dualUp  /  allUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/9` |
| lucid-command-011-p2 | richmat: dualDown  /  allDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/10` |
| lucid-command-012-p2 | richmat: dualDown  /  allDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/11` |
| lucid-command-013-p2 | richmat: setMemory1 | IMPLEMENTED | FRAME, SAVE | `L#/protocols/1/commands/12` |
| lucid-command-014-p2 | richmat: setMemory1 | IMPLEMENTED | FRAME, SAVE | `L#/protocols/1/commands/13` |
| lucid-command-015-p2 | richmat: setMemory2 | IMPLEMENTED | FRAME, SAVE | `L#/protocols/1/commands/14` |
| lucid-command-016-p2 | richmat: setMemory2 | IMPLEMENTED | FRAME, SAVE | `L#/protocols/1/commands/15` |
| lucid-command-017-p2 | richmat: setMemory3 | EXCLUDED |  | `L#/protocols/1/commands/16` |
| lucid-command-018-p2 | richmat: setMemory3 | EXCLUDED |  | `L#/protocols/1/commands/17` |
| lucid-command-019-p2 | richmat: memory1  /  Memory 1 | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/1/commands/18` |
| lucid-command-020-p2 | richmat: memory1  /  Memory 1 | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/1/commands/19` |
| lucid-command-021-p2 | richmat: memory2  /  Memory 2 | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/1/commands/20` |
| lucid-command-022-p2 | richmat: memory2  /  Memory 2 | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/1/commands/21` |
| lucid-command-023-p2 | richmat: memory3 | EXCLUDED |  | `L#/protocols/1/commands/22` |
| lucid-command-024-p2 | richmat: memory3 | EXCLUDED |  | `L#/protocols/1/commands/23` |
| lucid-command-025-p2 | richmat: allFlat | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/1/commands/24` |
| lucid-command-026-p2 | richmat: allFlat | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/1/commands/25` |
| lucid-command-027-p2 | richmat: lightSwitch | IMPLEMENTED | FRAME, LIGHT | `L#/protocols/1/commands/26` |
| lucid-command-028-p2 | richmat: lightSwitch | IMPLEMENTED | FRAME, LIGHT | `L#/protocols/1/commands/27` |
| lucid-command-029-p2 | richmat: headTiltUp  /  fullTiltUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/28` |
| lucid-command-030-p2 | richmat: headTiltUp  /  fullTiltUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/29` |
| lucid-command-031-p2 | richmat: headTiltDown  /  fullTiltDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/30` |
| lucid-command-032-p2 | richmat: headTiltDown  /  fullTiltDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/31` |
| lucid-command-033-p2 | richmat: lumbarUp  /  tiltHeadUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/32` |
| lucid-command-034-p2 | richmat: lumbarUp  /  tiltHeadUp | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/33` |
| lucid-command-035-p2 | richmat: lumbarDown  /  tiltHeadDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/34` |
| lucid-command-036-p2 | richmat: lumbarDown  /  tiltHeadDown | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/35` |
| lucid-command-037-p2 | richmat: zeroG  /  Zero G  /  Oz Spine Relief | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/1/commands/36` |
| lucid-command-038-p2 | richmat: zeroG  /  Zero G  /  Oz Spine Relief | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/1/commands/37` |
| lucid-command-039-p2 | richmat: antiSnore  /  Anti Snore  /  Oz Anti Snore | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/1/commands/38` |
| lucid-command-040-p2 | richmat: antiSnore  /  Anti Snore  /  Oz Anti Snore | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/1/commands/39` |
| lucid-command-041-p2 | richmat: massageOff | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/1/commands/40` |
| lucid-command-042-p2 | richmat: massageOff | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/1/commands/41` |
| lucid-command-043-p2 | richmat: massageWave | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/1/commands/42` |
| lucid-command-044-p2 | richmat: massageWave | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/1/commands/43` |
| lucid-command-045-p2 | richmat: massageHead | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/1/commands/44` |
| lucid-command-046-p2 | richmat: massageHead | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/1/commands/45` |
| lucid-command-047-p2 | richmat: massageFoot | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/1/commands/46` |
| lucid-command-048-p2 | richmat: massageFoot | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/1/commands/47` |
| lucid-command-049-p2 | richmat: tvRead  /  TV Read  /  TV | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/1/commands/48` |
| lucid-command-050-p2 | richmat: tvRead  /  TV Read  /  TV | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/1/commands/49` |
| lucid-command-051-p2 | richmat: lounge  /  Lounge | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/1/commands/50` |
| lucid-command-052-p2 | richmat: lounge  /  Lounge | IMPLEMENTED | FRAME, PRESET, LABELS | `L#/protocols/1/commands/51` |
| lucid-command-053-p2 | richmat: massage10 | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/1/commands/52` |
| lucid-command-054-p2 | richmat: massage10 | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/1/commands/53` |
| lucid-command-055-p2 | richmat: massage30 | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/1/commands/54` |
| lucid-command-056-p2 | richmat: massage30 | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/1/commands/55` |
| lucid-command-057-p2 | richmat: massage20 | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/1/commands/56` |
| lucid-command-058-p2 | richmat: massage20 | IMPLEMENTED | FRAME, MASSAGE | `L#/protocols/1/commands/57` |
| lucid-command-059-p2 | richmat: stopDriver | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/58` |
| lucid-command-060-p2 | richmat: stopDriver | IMPLEMENTED | FRAME, MOTION | `L#/protocols/1/commands/59` |
| lucid-command-061-p2 | richmat: read [Premium preset attempted action] | EXCLUDED |  | `L#/protocols/1/commands/60` |
| lucid-command-062-p2 | richmat: read [Premium preset attempted action] | EXCLUDED |  | `L#/protocols/1/commands/61` |
| lucid-model-01 | Altitude | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `L#/protocols/0/model_mappings/0` |
| lucid-model-02 | E450 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `L#/protocols/0/model_mappings/1` |
| lucid-model-03 | E455 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `L#/protocols/0/model_mappings/2` |
| lucid-model-04 | Forte | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `L#/protocols/0/model_mappings/3` |
| lucid-model-05 | Good Life Base | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE, OZ_SAVE | `L#/protocols/0/model_mappings/4` |
| lucid-model-06 | Good Life Premier Base | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE, OZ_SAVE | `L#/protocols/0/model_mappings/5` |
| lucid-model-07 | Good Life Pro Base | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE, OZ_SAVE | `L#/protocols/0/model_mappings/6` |
| lucid-model-08 | L300 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `L#/protocols/0/model_mappings/7` |
| lucid-model-09 | L600 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `L#/protocols/0/model_mappings/8` |
| lucid-model-10 | M455 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `L#/protocols/0/model_mappings/9` |
| lucid-model-11 | M550 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `L#/protocols/0/model_mappings/10` |
| lucid-model-12 | M555 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `L#/protocols/0/model_mappings/11` |
| lucid-model-13 | Premium | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `L#/protocols/0/model_mappings/12` |
| lucid-model-14 | S655 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `L#/protocols/0/model_mappings/13` |
| lucid-model-15 | S750 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `L#/protocols/0/model_mappings/14` |
| lucid-model-16 | S755 | IMPLEMENTED | MODEL, PROFILE, LABELS, MASSAGE | `L#/protocols/0/model_mappings/15` |
| lucid-model-action-001 | Altitude: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/0` |
| lucid-model-action-002 | Altitude: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/1` |
| lucid-model-action-003 | Altitude: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/2` |
| lucid-model-action-004 | Altitude: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/3` |
| lucid-model-action-005 | Altitude: DUAL | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/4` |
| lucid-model-action-006 | Altitude: DUAL | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/5` |
| lucid-model-action-007 | Altitude: TILT HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/6` |
| lucid-model-action-008 | Altitude: TILT HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/7` |
| lucid-model-action-009 | Altitude: FULL TILT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/8` |
| lucid-model-action-010 | Altitude: FULL TILT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/9` |
| lucid-model-action-011 | Altitude: ZERO G | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/10` |
| lucid-model-action-012 | Altitude: ANTI SNORE | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/11` |
| lucid-model-action-013 | Altitude: MASSAGE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/12` |
| lucid-model-action-014 | Altitude: MASSAGE HEAD | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/13` |
| lucid-model-action-015 | Altitude: MASSAGE FOOT | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/14` |
| lucid-model-action-016 | Altitude: MASSAGE TYPE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/15` |
| lucid-model-action-017 | Altitude: MASSAGE OFF | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/16` |
| lucid-model-action-018 | Altitude: LIGHT | IMPLEMENTED | MODEL, LIGHT | `L#/model_action_traces/17` |
| lucid-model-action-019 | E450: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/18` |
| lucid-model-action-020 | E450: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/19` |
| lucid-model-action-021 | E450: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/20` |
| lucid-model-action-022 | E450: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/21` |
| lucid-model-action-023 | E450: ZERO G | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/22` |
| lucid-model-action-024 | E450: ANTI SNORE | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/23` |
| lucid-model-action-025 | E455: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/24` |
| lucid-model-action-026 | E455: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/25` |
| lucid-model-action-027 | E455: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/26` |
| lucid-model-action-028 | E455: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/27` |
| lucid-model-action-029 | E455: ZERO G | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/28` |
| lucid-model-action-030 | E455: ANTI SNORE | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/29` |
| lucid-model-action-031 | Forte: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/30` |
| lucid-model-action-032 | Forte: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/31` |
| lucid-model-action-033 | Forte: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/32` |
| lucid-model-action-034 | Forte: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/33` |
| lucid-model-action-035 | Forte: ZERO G | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/34` |
| lucid-model-action-036 | Forte: MASSAGE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/35` |
| lucid-model-action-037 | Forte: MASSAGE HEAD | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/36` |
| lucid-model-action-038 | Forte: MASSAGE TYPE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/37` |
| lucid-model-action-039 | Forte: MASSAGE OFF | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/38` |
| lucid-model-action-040 | Good Life Base: Head | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/39` |
| lucid-model-action-041 | Good Life Base: Head | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/40` |
| lucid-model-action-042 | Good Life Base: Foot | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/41` |
| lucid-model-action-043 | Good Life Base: Foot | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/42` |
| lucid-model-action-044 | Good Life Base: All | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/43` |
| lucid-model-action-045 | Good Life Base: All | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/44` |
| lucid-model-action-046 | Good Life Base: Oz Spine Relief | IMPLEMENTED | MODEL, PRESET, LABELS, OZ_SAVE | `L#/model_action_traces/45` |
| lucid-model-action-047 | Good Life Base: TV | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/46` |
| lucid-model-action-048 | Good Life Base: Oz Anti Snore | IMPLEMENTED | MODEL, PRESET, LABELS, OZ_SAVE | `L#/model_action_traces/47` |
| lucid-model-action-049 | Good Life Base: Lounge | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/48` |
| lucid-model-action-050 | Good Life Premier Base: Head | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/49` |
| lucid-model-action-051 | Good Life Premier Base: Head | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/50` |
| lucid-model-action-052 | Good Life Premier Base: Foot | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/51` |
| lucid-model-action-053 | Good Life Premier Base: Foot | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/52` |
| lucid-model-action-054 | Good Life Premier Base: All | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/53` |
| lucid-model-action-055 | Good Life Premier Base: All | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/54` |
| lucid-model-action-056 | Good Life Premier Base: Head Tilt | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/55` |
| lucid-model-action-057 | Good Life Premier Base: Head Tilt | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/56` |
| lucid-model-action-058 | Good Life Premier Base: Lumbar | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/57` |
| lucid-model-action-059 | Good Life Premier Base: Lumbar | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/58` |
| lucid-model-action-060 | Good Life Premier Base: Oz Spine Relief | IMPLEMENTED | MODEL, PRESET, LABELS, OZ_SAVE | `L#/model_action_traces/59` |
| lucid-model-action-061 | Good Life Premier Base: TV | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/60` |
| lucid-model-action-062 | Good Life Premier Base: Oz Anti Snore | IMPLEMENTED | MODEL, PRESET, LABELS, OZ_SAVE | `L#/model_action_traces/61` |
| lucid-model-action-063 | Good Life Premier Base: Lounge | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/62` |
| lucid-model-action-064 | Good Life Premier Base: MASSAGE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/63` |
| lucid-model-action-065 | Good Life Premier Base: MASSAGE HEAD | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/64` |
| lucid-model-action-066 | Good Life Premier Base: MASSAGE FOOT | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/65` |
| lucid-model-action-067 | Good Life Premier Base: MASSAGE TYPE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/66` |
| lucid-model-action-068 | Good Life Premier Base: MASSAGE OFF | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/67` |
| lucid-model-action-069 | Good Life Premier Base: MASSAGE TIMER SET | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/68` |
| lucid-model-action-070 | Good Life Premier Base: LIGHT | IMPLEMENTED | MODEL, LIGHT | `L#/model_action_traces/69` |
| lucid-model-action-071 | Good Life Pro Base: Head | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/70` |
| lucid-model-action-072 | Good Life Pro Base: Head | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/71` |
| lucid-model-action-073 | Good Life Pro Base: Foot | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/72` |
| lucid-model-action-074 | Good Life Pro Base: Foot | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/73` |
| lucid-model-action-075 | Good Life Pro Base: All | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/74` |
| lucid-model-action-076 | Good Life Pro Base: All | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/75` |
| lucid-model-action-077 | Good Life Pro Base: Oz Spine Relief | IMPLEMENTED | MODEL, PRESET, LABELS, OZ_SAVE | `L#/model_action_traces/76` |
| lucid-model-action-078 | Good Life Pro Base: TV | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/77` |
| lucid-model-action-079 | Good Life Pro Base: Oz Anti Snore | IMPLEMENTED | MODEL, PRESET, LABELS, OZ_SAVE | `L#/model_action_traces/78` |
| lucid-model-action-080 | Good Life Pro Base: Lounge | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/79` |
| lucid-model-action-081 | Good Life Pro Base: MASSAGE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/80` |
| lucid-model-action-082 | Good Life Pro Base: MASSAGE HEAD | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/81` |
| lucid-model-action-083 | Good Life Pro Base: MASSAGE FOOT | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/82` |
| lucid-model-action-084 | Good Life Pro Base: MASSAGE TYPE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/83` |
| lucid-model-action-085 | Good Life Pro Base: MASSAGE OFF | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/84` |
| lucid-model-action-086 | Good Life Pro Base: MASSAGE TIMER SET | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/85` |
| lucid-model-action-087 | Good Life Pro Base: LIGHT | IMPLEMENTED | MODEL, LIGHT | `L#/model_action_traces/86` |
| lucid-model-action-088 | L300: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/87` |
| lucid-model-action-089 | L300: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/88` |
| lucid-model-action-090 | L300: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/89` |
| lucid-model-action-091 | L300: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/90` |
| lucid-model-action-092 | L300: ZERO G | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/91` |
| lucid-model-action-093 | L300: ANTI SNORE | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/92` |
| lucid-model-action-094 | L600: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/93` |
| lucid-model-action-095 | L600: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/94` |
| lucid-model-action-096 | L600: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/95` |
| lucid-model-action-097 | L600: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/96` |
| lucid-model-action-098 | L600: ZERO G | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/97` |
| lucid-model-action-099 | L600: ANTI SNORE | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/98` |
| lucid-model-action-100 | L600: LOUNGE | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/99` |
| lucid-model-action-101 | L600: TV READ | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/100` |
| lucid-model-action-102 | L600: MASSAGE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/101` |
| lucid-model-action-103 | L600: MASSAGE HEAD | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/102` |
| lucid-model-action-104 | L600: MASSAGE FOOT | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/103` |
| lucid-model-action-105 | L600: MASSAGE TYPE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/104` |
| lucid-model-action-106 | L600: MASSAGE TIMER | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/105` |
| lucid-model-action-107 | L600: ALARM | IMPLEMENTED | MODEL, ALARM | `L#/model_action_traces/106` |
| lucid-model-action-108 | L600: LIGHT | IMPLEMENTED | MODEL, LIGHT | `L#/model_action_traces/107` |
| lucid-model-action-109 | M455: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/108` |
| lucid-model-action-110 | M455: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/109` |
| lucid-model-action-111 | M455: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/110` |
| lucid-model-action-112 | M455: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/111` |
| lucid-model-action-113 | M455: ZERO G | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/112` |
| lucid-model-action-114 | M455: ANTI SNORE | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/113` |
| lucid-model-action-115 | M455: MASSAGE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/114` |
| lucid-model-action-116 | M455: MASSAGE HEAD | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/115` |
| lucid-model-action-117 | M455: MASSAGE TYPE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/116` |
| lucid-model-action-118 | M455: MASSAGE OFF | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/117` |
| lucid-model-action-119 | M455: MASSAGE TIMER SET | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/118` |
| lucid-model-action-120 | M550: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/119` |
| lucid-model-action-121 | M550: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/120` |
| lucid-model-action-122 | M550: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/121` |
| lucid-model-action-123 | M550: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/122` |
| lucid-model-action-124 | M550: ZERO G | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/123` |
| lucid-model-action-125 | M550: ANTI SNORE | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/124` |
| lucid-model-action-126 | M550: LOUNGE | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/125` |
| lucid-model-action-127 | M550: TV READ | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/126` |
| lucid-model-action-128 | M550: MASSAGE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/127` |
| lucid-model-action-129 | M550: MASSAGE HEAD | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/128` |
| lucid-model-action-130 | M550: MASSAGE FOOT | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/129` |
| lucid-model-action-131 | M550: MASSAGE TYPE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/130` |
| lucid-model-action-132 | M550: MASSAGE TIMER | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/131` |
| lucid-model-action-133 | M550: ALARM | IMPLEMENTED | MODEL, ALARM | `L#/model_action_traces/132` |
| lucid-model-action-134 | M550: LIGHT | IMPLEMENTED | MODEL, LIGHT | `L#/model_action_traces/133` |
| lucid-model-action-135 | M555: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/134` |
| lucid-model-action-136 | M555: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/135` |
| lucid-model-action-137 | M555: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/136` |
| lucid-model-action-138 | M555: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/137` |
| lucid-model-action-139 | M555: DUAL | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/138` |
| lucid-model-action-140 | M555: DUAL | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/139` |
| lucid-model-action-141 | M555: ZERO G | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/140` |
| lucid-model-action-142 | M555: TV READ | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/141` |
| lucid-model-action-143 | M555: ANTI SNORE | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/142` |
| lucid-model-action-144 | M555: LOUNGE | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/143` |
| lucid-model-action-145 | M555: MASSAGE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/144` |
| lucid-model-action-146 | M555: MASSAGE HEAD | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/145` |
| lucid-model-action-147 | M555: MASSAGE FOOT | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/146` |
| lucid-model-action-148 | M555: MASSAGE TYPE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/147` |
| lucid-model-action-149 | M555: MASSAGE OFF | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/148` |
| lucid-model-action-150 | M555: MASSAGE TIMER SET | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/149` |
| lucid-model-action-151 | M555: LIGHT | IMPLEMENTED | MODEL, LIGHT | `L#/model_action_traces/150` |
| lucid-model-action-152 | Premium: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/151` |
| lucid-model-action-153 | Premium: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/152` |
| lucid-model-action-154 | Premium: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/153` |
| lucid-model-action-155 | Premium: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/154` |
| lucid-model-action-156 | Premium: DUAL | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/155` |
| lucid-model-action-157 | Premium: DUAL | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/156` |
| lucid-model-action-158 | Premium: ZERO G | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/157` |
| lucid-model-action-159 | Premium: ANTI SNORE | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/158` |
| lucid-model-action-160 | Premium: TV | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/159` |
| lucid-model-action-161 | Premium: READ | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/160` |
| lucid-model-action-162 | Premium: MASSAGE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/161` |
| lucid-model-action-163 | Premium: MASSAGE HEAD | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/162` |
| lucid-model-action-164 | Premium: MASSAGE FOOT | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/163` |
| lucid-model-action-165 | Premium: MASSAGE TYPE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/164` |
| lucid-model-action-166 | Premium: MASSAGE TIMER | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/165` |
| lucid-model-action-167 | Premium: ALARM | IMPLEMENTED | MODEL, ALARM | `L#/model_action_traces/166` |
| lucid-model-action-168 | Premium: LIGHT | IMPLEMENTED | MODEL, LIGHT | `L#/model_action_traces/167` |
| lucid-model-action-169 | S655: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/168` |
| lucid-model-action-170 | S655: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/169` |
| lucid-model-action-171 | S655: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/170` |
| lucid-model-action-172 | S655: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/171` |
| lucid-model-action-173 | S655: DUAL | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/172` |
| lucid-model-action-174 | S655: DUAL | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/173` |
| lucid-model-action-175 | S655: HEAD TILT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/174` |
| lucid-model-action-176 | S655: HEAD TILT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/175` |
| lucid-model-action-177 | S655: ZERO G | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/176` |
| lucid-model-action-178 | S655: TV READ | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/177` |
| lucid-model-action-179 | S655: ANTI SNORE | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/178` |
| lucid-model-action-180 | S655: LOUNGE | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/179` |
| lucid-model-action-181 | S655: MASSAGE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/180` |
| lucid-model-action-182 | S655: MASSAGE HEAD | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/181` |
| lucid-model-action-183 | S655: MASSAGE FOOT | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/182` |
| lucid-model-action-184 | S655: MASSAGE TYPE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/183` |
| lucid-model-action-185 | S655: MASSAGE OFF | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/184` |
| lucid-model-action-186 | S655: MASSAGE TIMER SET | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/185` |
| lucid-model-action-187 | S655: LIGHT | IMPLEMENTED | MODEL, LIGHT | `L#/model_action_traces/186` |
| lucid-model-action-188 | S750: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/187` |
| lucid-model-action-189 | S750: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/188` |
| lucid-model-action-190 | S750: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/189` |
| lucid-model-action-191 | S750: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/190` |
| lucid-model-action-192 | S750: HEAD TILT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/191` |
| lucid-model-action-193 | S750: HEAD TILT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/192` |
| lucid-model-action-194 | S750: LUMBAR | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/193` |
| lucid-model-action-195 | S750: LUMBAR | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/194` |
| lucid-model-action-196 | S750: ZERO G | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/195` |
| lucid-model-action-197 | S750: TV READ | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/196` |
| lucid-model-action-198 | S750: ANTI SNORE | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/197` |
| lucid-model-action-199 | S750: LOUNGE | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/198` |
| lucid-model-action-200 | S750: MASSAGE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/199` |
| lucid-model-action-201 | S750: MASSAGE HEAD | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/200` |
| lucid-model-action-202 | S750: MASSAGE FOOT | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/201` |
| lucid-model-action-203 | S750: MASSAGE TYPE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/202` |
| lucid-model-action-204 | S750: MASSAGE TIMER | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/203` |
| lucid-model-action-205 | S750: ALARM | IMPLEMENTED | MODEL, ALARM | `L#/model_action_traces/204` |
| lucid-model-action-206 | S750: LIGHT | IMPLEMENTED | MODEL, LIGHT | `L#/model_action_traces/205` |
| lucid-model-action-207 | S755: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/206` |
| lucid-model-action-208 | S755: HEAD | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/207` |
| lucid-model-action-209 | S755: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/208` |
| lucid-model-action-210 | S755: FOOT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/209` |
| lucid-model-action-211 | S755: DUAL | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/210` |
| lucid-model-action-212 | S755: DUAL | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/211` |
| lucid-model-action-213 | S755: HEAD TILT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/212` |
| lucid-model-action-214 | S755: HEAD TILT | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/213` |
| lucid-model-action-215 | S755: LUMBAR | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/214` |
| lucid-model-action-216 | S755: LUMBAR | IMPLEMENTED | MODEL, MOTION, LABELS | `L#/model_action_traces/215` |
| lucid-model-action-217 | S755: ZERO G | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/216` |
| lucid-model-action-218 | S755: TV READ | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/217` |
| lucid-model-action-219 | S755: ANTI SNORE | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/218` |
| lucid-model-action-220 | S755: LOUNGE | IMPLEMENTED | MODEL, PRESET, LABELS | `L#/model_action_traces/219` |
| lucid-model-action-221 | S755: MASSAGE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/220` |
| lucid-model-action-222 | S755: MASSAGE HEAD | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/221` |
| lucid-model-action-223 | S755: MASSAGE FOOT | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/222` |
| lucid-model-action-224 | S755: MASSAGE TYPE | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/223` |
| lucid-model-action-225 | S755: MASSAGE OFF | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/224` |
| lucid-model-action-226 | S755: MASSAGE TIMER SET | IMPLEMENTED | MODEL, MASSAGE, STATE | `L#/model_action_traces/225` |
| lucid-model-action-227 | S755: LIGHT | IMPLEMENTED | MODEL, LIGHT | `L#/model_action_traces/226` |
| B01 | NEW 8-byte uint32 BE command | ALREADY_IMPLEMENTED | FRAME | `M ANALYSIS.md:129` |
| B02 | LEGACY 9-byte LE32 and complement checksum | ALREADY_IMPLEMENTED | FRAME | `M ANALYSIS.md:127` |
| B03 | MIDDLE 10-byte 04 02 BE32 plus four zeros | IMPLEMENTED | FRAME | `M ANALYSIS.md:129` |
| B04 | Richmat one-byte and 6e 01 S opcode checksum | IMPLEMENTED | FRAME, SELECTOR | `M ANALYSIS.md:123-125` |
| B05 | Legacy/middle 10-byte current-time frame | IMPLEMENTED | CLOCK | `L BedBaseUtils.java:289-317` |
| B06 | New 9-byte current-time frame | IMPLEMENTED | CLOCK | `L BedBaseUtils.java:289-317` |
| B07 | Legacy/middle 16-byte alarm frame | IMPLEMENTED | ALARM | `L BedBaseUtils.java:257-287` |
| B08 | New 9-byte alarm frame | IMPLEMENTED | ALARM | `L BedBaseUtils.java:257-287` |
| S01 | NEW 55x100ms delayed-first-write hold without final STOP | ALREADY_IMPLEMENTED | SAVE | `M ANALYSIS.md:247-248` |
| S02 | LEGACY 85x150ms save and Smartbed238 special value | ALREADY_IMPLEMENTED | SAVE | `M ANALYSIS.md:247-248` |
| S03 | MIDDLE 85x150ms save without STOP | IMPLEMENTED | SAVE | `M ANALYSIS.md:247-248` |
| S04 | NEW one-copy preset then zero STOP | ALREADY_IMPLEMENTED | PRESET | `M ANALYSIS.md:246` |
| S05 | LEGACY three-copy preset without STOP | IMPLEMENTED | PRESET | `M ANALYSIS.md:246` |
| S06 | MIDDLE three-copy preset then zero STOP | IMPLEMENTED | PRESET | `M ANALYSIS.md:246` |
| S07 | Richmat legacy one-copy preset then 6e STOP; framed no STOP | IMPLEMENTED | PRESET | `M ANALYSIS.md:246` |
| S08 | 150ms held motor refresh and delayed release STOP | IMPLEMENTED | MOTION | `M ANALYSIS.md:246` |
| G01 | Subscribe three Okin notify UUIDs; no Richmat parser | IMPLEMENTED | DISCOVERY, STATE | `L OkinConnection.java:59-149` |
| N-legacy | legacy massage minutes and light parser | IMPLEMENTED | STATE | `L BedBaseUtils.java:328-407` |
| N-middle | middle massage minutes and light parser | IMPLEMENTED | STATE | `L BedBaseUtils.java:328-407` |
| N-new | new massage minutes and light parser | IMPLEMENTED | STATE | `L BedBaseUtils.java:328-407` |
| N-query | New raw 00 b0 follow-up after light/massage writes | IMPLEMENTED | QUERY | `L OkinConnection.java:793-803` |
| A01 | Alarm position types, weekday mask, one-shot next-day conversion | IMPLEMENTED | ALARM | `L AlarmPosition.java:11-19` |
| D01 | App family name factory and five service layouts | IMPLEMENTED | DISCOVERY, PROFILE | `M BedBaseUtils.java:216-230` |
| P01 | Richmat six side-sensitive actions and partner route | IMPLEMENTED | SELECTOR, PARTNER | `M ANALYSIS.md:250` |
| P02 | No credential transform; passive bond wait only | EXCLUDED |  | `M ANALYSIS.md:135,278` |
| P03 | Android request queue 500ms timeout without retry | EXCLUDED |  | `M ANALYSIS.md:249` |
| P04 | Unsafe order-dependent GATT hybrids and partial Lucid GoodLife+Okin partner-only combined route | EXCLUDED | DISCOVERY, LABELS, PARTNER | `L analysis.json#/protocols/0/multi_service_behavior` |
| P05 | Model-number read with no parser/behavior effect | EXCLUDED |  | `L OkinConnection.java:83-88` |
| P06 | No motor position/brightness/color/calibration/EEPROM feedback | EXCLUDED |  | `M ANALYSIS.md:241,278` |
| P07 | Snore classifier microphone/TFLite and Android application persistence | EXCLUDED |  | `M ANALYSIS.md:278` |
| A-unselectable-20 | Alarm enum Massage=20 | EXCLUDED | ALARM | `L AlarmPosition.java:11-19` |
| A-unselectable-21 | Alarm enum Flat=21 | EXCLUDED | ALARM | `L AlarmPosition.java:11-19` |

## Every exclusion

| ID | Exact source evidence | Reason |
| --- | --- | --- |
| malouf-command-009-p1 | M#/protocols/0/commands/8; RichmatConnection.smali:539-1728; work/searches/second-04-actions.txt | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| malouf-command-012-p1 | M#/protocols/0/commands/11; RichmatConnection.smali:90-145,539-1728; work/searches/second-04-actions.txt | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| malouf-command-010-p2 | M#/protocols/1/commands/9; OkinConnection.smali:1187-2667; work/searches/second-04-actions.txt | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| malouf-command-016-p2 | M#/protocols/1/commands/15; OkinConnection.smali:1187-2667; work/searches/second-04-actions.txt | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| malouf-command-018-p2 | M#/protocols/1/commands/17; OkinConnection.smali:1187-2667; PresetControlRecyclerViewAdapter.java:56-111; work/searches/second-04-actions.txt | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| malouf-command-023-p2 | M#/protocols/1/commands/22; OkinConnection.smali:1187-2667; work/searches/second-04-actions.txt | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| malouf-command-024-p2 | M#/protocols/1/commands/23; OkinConnection.smali:1187-2667; work/searches/second-04-actions.txt | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| malouf-command-025-p2 | M#/protocols/1/commands/24; OkinConnection.smali:1187-2667; work/searches/second-04-actions.txt | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| malouf-command-026-p2 | M#/protocols/1/commands/25; OkinConnection.smali:1187-2667; work/searches/second-04-actions.txt | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| malouf-command-027-p2 | M#/protocols/1/commands/26; OkinConnection.smali:1187-2667; work/searches/second-04-actions.txt | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| malouf-command-028-p2 | M#/protocols/1/commands/27; OkinConnection.smali:1187-2667; work/searches/second-04-actions.txt | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| malouf-command-029-p2 | M#/protocols/1/commands/28; OkinConnection.smali:1187-2667; work/searches/second-04-actions.txt | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| malouf-command-030-p2 | M#/protocols/1/commands/29; OkinConnection.smali:1187-2667; RemoteTabBarActivity.java:789-807 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| malouf-command-031-p2 | M#/protocols/1/commands/30; OkinConnection.smali:1187-2667; work/searches/second-04-actions.txt | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| malouf-command-033-p2 | M#/protocols/1/commands/32; OkinConnection.smali:1187-2667; work/searches/second-04-actions.txt | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-031-p1 | L#/protocols/0/commands/30; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1483; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1494; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-032-p1 | L#/protocols/0/commands/31; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1483; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1494; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-033-p1 | L#/protocols/0/commands/32; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1483; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1494; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-064-p1 | L#/protocols/0/commands/63; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1246; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1257; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-065-p1 | L#/protocols/0/commands/64; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1246; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1257; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-066-p1 | L#/protocols/0/commands/65; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1246; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1257; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-067-p1 | L#/protocols/0/commands/66; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1220; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1231; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-068-p1 | L#/protocols/0/commands/67; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1220; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1231; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-069-p1 | L#/protocols/0/commands/68; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1220; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1231; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-070-p1 | L#/protocols/0/commands/69; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1414; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1425; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-071-p1 | L#/protocols/0/commands/70; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1414; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1425; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-072-p1 | L#/protocols/0/commands/71; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1414; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1425; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-073-p1 | L#/protocols/0/commands/72; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1330; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1341; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-074-p1 | L#/protocols/0/commands/73; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1330; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1341; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-075-p1 | L#/protocols/0/commands/74; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1330; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1341; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-076-p1 | L#/protocols/0/commands/75; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1440; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1451; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-077-p1 | L#/protocols/0/commands/76; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1440; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1451; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-078-p1 | L#/protocols/0/commands/77; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1440; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1451; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-079-p1 | L#/protocols/0/commands/78; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1555; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1566; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-080-p1 | L#/protocols/0/commands/79; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1555; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1566; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-081-p1 | L#/protocols/0/commands/80; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1555; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1566; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-082-p1 | L#/protocols/0/commands/81; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1645; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1656; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197; routing-corrections-referral/claims.json#R-OFF; MassageFragment.java:325-352; RemoteTabBarActivity.java:780-802; fragment_massage.xml:22; routing-corrections-referral/claims.json#R-OFF; MassageFragment.java:325-352; RemoteTabBarActivity.java:780-802; fragment_massage.xml:22; routing-corrections-referral/claims.json#R-OFF; MassageFragment.java:325-352; RemoteTabBarActivity.java:780-802; fragment_massage.xml:22; routing-corrections-referral/claims.json#R-OFF; MassageFragment.java:325-352; RemoteTabBarActivity.java:780-802; fragment_massage.xml:22; routing-corrections-referral/claims.json#R-OFF; MassageFragment.java:325-352; RemoteTabBarActivity.java:780-802; fragment_massage.xml:22; routing-corrections-referral/claims.json#R-OFF; MassageFragment.java:325-352; RemoteTabBarActivity.java:780-802; fragment_massage.xml:22 | Dead SDK-only Okin massageOff/massageStopAll branch. Packaged OFF/TIMER button calls massageTimer; only Richmat capability remaps it to off. Okin actual action is0x200 timer step. Original REACHABLE producer label is superseded by accepted routing amendment002 with exact source/producer checks. |
| lucid-command-083-p1 | L#/protocols/0/commands/82; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1645; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1656; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197; routing-corrections-referral/claims.json#R-OFF; MassageFragment.java:325-352; RemoteTabBarActivity.java:780-802; fragment_massage.xml:22; routing-corrections-referral/claims.json#R-OFF; MassageFragment.java:325-352; RemoteTabBarActivity.java:780-802; fragment_massage.xml:22; routing-corrections-referral/claims.json#R-OFF; MassageFragment.java:325-352; RemoteTabBarActivity.java:780-802; fragment_massage.xml:22; routing-corrections-referral/claims.json#R-OFF; MassageFragment.java:325-352; RemoteTabBarActivity.java:780-802; fragment_massage.xml:22; routing-corrections-referral/claims.json#R-OFF; MassageFragment.java:325-352; RemoteTabBarActivity.java:780-802; fragment_massage.xml:22; routing-corrections-referral/claims.json#R-OFF; MassageFragment.java:325-352; RemoteTabBarActivity.java:780-802; fragment_massage.xml:22 | Dead SDK-only Okin massageOff/massageStopAll branch. Packaged OFF/TIMER button calls massageTimer; only Richmat capability remaps it to off. Okin actual action is0x200 timer step. Original REACHABLE producer label is superseded by accepted routing amendment002 with exact source/producer checks. |
| lucid-command-084-p1 | L#/protocols/0/commands/83; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1645; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1656; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197; routing-corrections-referral/claims.json#R-OFF; MassageFragment.java:325-352; RemoteTabBarActivity.java:780-802; fragment_massage.xml:22; routing-corrections-referral/claims.json#R-OFF; MassageFragment.java:325-352; RemoteTabBarActivity.java:780-802; fragment_massage.xml:22; routing-corrections-referral/claims.json#R-OFF; MassageFragment.java:325-352; RemoteTabBarActivity.java:780-802; fragment_massage.xml:22; routing-corrections-referral/claims.json#R-OFF; MassageFragment.java:325-352; RemoteTabBarActivity.java:780-802; fragment_massage.xml:22; routing-corrections-referral/claims.json#R-OFF; MassageFragment.java:325-352; RemoteTabBarActivity.java:780-802; fragment_massage.xml:22; routing-corrections-referral/claims.json#R-OFF; MassageFragment.java:325-352; RemoteTabBarActivity.java:780-802; fragment_massage.xml:22 | Dead SDK-only Okin massageOff/massageStopAll branch. Packaged OFF/TIMER button calls massageTimer; only Richmat capability remaps it to off. Okin actual action is0x200 timer step. Original REACHABLE producer label is superseded by accepted routing amendment002 with exact source/producer checks. |
| lucid-command-085-p1 | L#/protocols/0/commands/84; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1613; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1624; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-086-p1 | L#/protocols/0/commands/85; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1613; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1624; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-087-p1 | L#/protocols/0/commands/86; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1613; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/OkinConnection.smali:1624; work/jadx/sources/com/malouf/adjustablebasebluetooth/BedBaseUtils.java:233-271; work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/ManualControlRecyclerViewAdapter.java:142-197 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-017-p2 | L#/protocols/1/commands/16; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/RichmatConnection.smali:920; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/RichmatConnection.smali:931; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/RichmatConnection.smali:1570-1696 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-018-p2 | L#/protocols/1/commands/17; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/RichmatConnection.smali:920; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/RichmatConnection.smali:931; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/RichmatConnection.smali:1570-1696 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-023-p2 | L#/protocols/1/commands/22; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/RichmatConnection.smali:650; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/RichmatConnection.smali:661; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/RichmatConnection.smali:1570-1696 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-024-p2 | L#/protocols/1/commands/23; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/RichmatConnection.smali:650; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/RichmatConnection.smali:661; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/RichmatConnection.smali:1570-1696 | Frozen application caller/model tracing proves this terminal alias dead or unused; do not promote SDK-only values into app features. |
| lucid-command-061-p2 | L#/protocols/1/commands/60; work/jadx/sources/com/malouf/database/model/Premium.java:121; work/smali/base/smali_classes2/com/lucid/bedbase/recycler_view_adapters/PresetControlRecyclerViewAdapter.smali:119-339; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/RichmatConnection.smali:539-1696 | App preset routes to an unknown command and emits no BLE write; do not invent a command for READ. |
| lucid-command-062-p2 | L#/protocols/1/commands/61; work/jadx/sources/com/malouf/database/model/Premium.java:121; work/smali/base/smali_classes2/com/lucid/bedbase/recycler_view_adapters/PresetControlRecyclerViewAdapter.smali:119-339; work/smali/base/smali_classes2/com/malouf/adjustablebasebluetooth/RichmatConnection.smali:539-1696 | App preset routes to an unknown command and emits no BLE write; do not invent a command for READ. |
| P02 | M ANALYSIS.md:135,278; Lucid BedBaseConnection.java:223-652 | Android transport-specific 250ms bonded service-discovery wait is handled by HA/Bleak. No app-auth challenge/key/PIN exists to implement. |
| P03 | M ANALYSIS.md:249; Lucid BedBaseConnection.java:223-652 | Android request queue/descriptor/cache mechanics are platform boundary; HA/Bleak owns callbacks and request lifetime. Do not port Android transport internals. |
| P04 | L analysis.json#/protocols/0/multi_service_behavior; Lucid analysis.json#/protocols/1/multi_service_behavior; Lucid RemoteTabBarActivity.java:783-800; Lucid model_action_traces ACTION-044/045/054/055/075/076 | Safety exclusion: choose only coherent GATT roles, rejecting service-order hybrids. Lucid GoodLife All with Okin main has no main allUp/allDown endpoint but can route inactive partner foot; the unsupported combined path is excluded to prevent a partner-only partial movement. All coherent transport variants and standalone head/foot controls remain available. |
| P05 | L OkinConnection.java:83-88; Malouf ANALYSIS.md:278 | Artifact device-info read has no command/variant/capability response mapping. HA may retain diagnostic metadata; do not invent auth dependency. |
| P06 | M ANALYSIS.md:241,278 | Frozen parser accounts only for massage minutes and light status; no frame supports these extra features. |
| P07 | M ANALYSIS.md:278; Lucid analysis.json#/application_stacks; Lucid RemoteTabBarActivity.java:780-810; Malouf RemoteTabBarActivity.java:799-834; ActiveBed.java:sideIsActive/usePrimary; PartnerControlActivity.java:onSave; Lucid ActiveBed.java:37-51; Lucid PartnerControlActivity.java:57-119 | Non-BLE microphone/TFLite and Android application persistence/UI boundary: ActiveBed selection, activeSide, motorSwapped display mapping, inSnorePosition and shared last-base UI light state. HA retains explicit configured targets/physical role and independent controller telemetry; all reachable command endpoints remain exposed. |
| A-unselectable-20 | L AlarmPosition.java:11-19; Lucid arrays.xml:37-44; Lucid AddEditAlarmActivity.java:143-155; Lucid DatabaseHandler.java:548 | No current packaged UI creates this enum value: array has six entries and constructor uses selectedIndex+13. Database can restore enum values but no supplied runtime/persisted input proves20/21 originated in a valid app flow; do not expose enum-only action as fresh support. |
| A-unselectable-21 | L AlarmPosition.java:11-19; Lucid arrays.xml:37-44; Lucid AddEditAlarmActivity.java:143-155; Lucid DatabaseHandler.java:548 | No current packaged UI creates this enum value: array has six entries and constructor uses selectedIndex+13. Database can restore enum values but no supplied runtime/persisted input proves20/21 originated in a valid app flow; do not expose enum-only action as fresh support. |

The non-BLE UI/persistence boundary in P07 includes the vendor's remembered active bed, active side, motor-swapped UI and shared last-base display state. HA uses explicit configured device/side targets and per-controller state. This boundary does not remove any terminal command or parser discovered in the accepted artifacts. Android bond waits, queue timeouts and descriptor mechanics in P02/P03 belong to HA/Bleak transport ownership. P04 excludes unsafe order-dependent hybrids and the unsafe partial Lucid Good Life/Okin partner-only combined path, retaining all five coherent variants and standalone head/foot movement. P05 has no device-info response-dependent command/capability behavior to port. P06 accounts for absent extra feedback, preventing invented motor positions, color, brightness or EEPROM control. Alarm 20/21 have no packaged UI producer: the six-entry position array and selected index plus 13 constructor produce only 13..18; enum/database acceptance alone does not establish an originating reachable application flow.

Validation: `uv run --no-sync pytest -n 0 tests/test_malouf_app.py tests/test_malouf_app_config.py tests/test_malouf_app_services.py --tb=short -q`, independently passed 243 tests after the timed deadline, SplitHead composition and Oz memory-editor refinements. The coordinator additionally passed the full 6073-test suite and complete Ruff/Pyright checks. Both bounded amendments are independently accepted. Physical validation remains deferred for real users.
