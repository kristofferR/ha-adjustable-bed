# Row047: Cool Base app dispositions

The accepted Android app `com.keeson.coolbase` 1.0.0 (3) is a complete 19-APK XAPK with one reachable BLE control protocol. The comparison accounts for **70 discovery items: 23 IMPLEMENTED, 21 ALREADY_IMPLEMENTED, 26 EXCLUDED**. Rows overlap evidence coverage and are not distinct physical features. Hardware is unverified (STATIC VERIFIED / HARDWARE UNVERIFIED).

The public controller contract is [Cool Base](../../beds/coolbase.md). Only the Cool Base profile follows this app; the DewertOKIN `OKIN-BLE` profile keeps its separately sourced behavior.

## Exact accepted authority

| Identity or authority | SHA-256 / result |
|---|---|
| Frozen XAPK, 1.0.0 (3) | `f8b8968ee2247fa071dc919edf33d68255e377331d5de49aa96a5b25b7b74182` |
| Signer certificate | `ac23afbd10a5c0f26a62639677eb6b8a4169eed7b8b981ae3818f80a3d24c9f9` |
| Attempt 001 REPORT.SHA256, preserved | `f17892108a652e4b243a748a9f3e5b058d3e9953fa30ba4a57bff326ca2f22d1` |
| Attempt 001 full independent audit (REPAIR_REQUIRED, IA001) | `9857d18bccd893e2c8eaa6ec727f4e8b549032eee75c2effca4a777a492fa303` |
| Accepted attempt 002 REPORT.SHA256 | `abaaa0a3e8eb37114cf4ee65cde34e629f602dde08941bb4eeac6eec5477595c` |
| Accepted attempt 002 analysis.json | `573de1af097814d254760a1968ab4e63abd3ad4ca177bb6a4cd639ea3742f8e8` |
| Accepting affected-scope audit AUDIT.SHA256 | `6ccaee9a3b9bf351dc1870e2d625d625e8db38f939a7895b3e6ef4f42c27d39f` |
| Effective decision | COMPLETE, 17 gates PASS, IA001 closed, 0 open material findings |

IA001 (the omitted 12-second discovery-screen deadline and refresh lifecycle) was repaired in an isolated attempt and closed by the affected-scope audit. Raw artifacts, reports and decompiled sources remain machine-local.

## What changed

- Every app frame was already byte-identical; the builder formula reproduces each literal trailer and tests now pin all 17.
- Left fan, right fan, fan sync, head massage, foot massage, massage mode and the star button are exposed as app-labelled buttons. Before, these frames existed without any entity.
- Status replies are parsed exactly like the app (28 bytes only, out-of-range values keep the prior value). Fan levels and massage mode publish diagnostic sensors; the light becomes an on/off light driven by the reported flag.
- The app status query runs after each tap (three times, 200 ms apart) and every 3 s on a live connection, without extending the idle disconnect.
- The notify channel is kept with angle sensing off, so status replies arrive on default entries.
- Writes mirror Android's default write type for the FFE5 characteristic instance.
- The unproven Memory 1 and Lounge labels on the star frame were removed; the star button keeps the frame without inferred meaning.
- Detection uses the app's `base-i5` substring rule.

## Ledger

| ID | Area | Item | Disposition | Evidence | Binding or exclusion reason |
|---|---|---|---|---|---|
| D01 | command | Head/back up frame `E5 FE 16 01 00 00 00 05` | ALREADY_IMPLEMENTED | Command table V01; C03 | beds/coolbase.py MOTOR_HEAD_UP; move_head_up/move_back_up; tests/test_coolbase.py test_builder_reproduces_every_app_literal |
| D02 | command | Head/back down frame `E5 FE 16 02 00 00 00 04` | ALREADY_IMPLEMENTED | Command table V01; C03 | beds/coolbase.py MOTOR_HEAD_DOWN; move_head_down/move_back_down; tests/test_coolbase.py test_builder_reproduces_every_app_literal |
| D03 | command | Foot/leg up frame `E5 FE 16 04 00 00 00 02` | ALREADY_IMPLEMENTED | Command table V01; C03 | beds/coolbase.py MOTOR_FEET_UP; move_feet_up/move_legs_up; tests/test_coolbase.py test_builder_reproduces_every_app_literal |
| D04 | command | Foot/leg down frame `E5 FE 16 08 00 00 00 FE` | ALREADY_IMPLEMENTED | Command table V01; C03 | beds/coolbase.py MOTOR_FEET_DOWN; move_feet_down/move_legs_down; tests/test_coolbase.py test_builder_reproduces_every_app_literal |
| D05 | command | Foot massage frame `E5 FE 16 00 04 00 00 02`, single tap (T timing) | IMPLEMENTED | Command table V01; C03 | beds/coolbase.py MASSAGE_FOOT; coolbase_foot_massage button (frame existed, no entity before); tests/test_coolbase.py test_builder_reproduces_every_app_literal, test_button_specs_press_app_frames |
| D06 | command | Head massage frame `E5 FE 16 00 08 00 00 FE`, single tap (T timing) | IMPLEMENTED | Command table V01; C03 | beds/coolbase.py MASSAGE_HEAD; coolbase_head_massage button (frame existed, no entity before); tests/test_coolbase.py test_builder_reproduces_every_app_literal, test_button_specs_press_app_frames |
| D07 | command | Left fan frame `E5 FE 16 00 00 40 00 C6`, single tap (T timing) | IMPLEMENTED | Command table V01; C03 | beds/coolbase.py FAN_LEFT; coolbase_left_fan button (frame existed, no entity before); tests/test_coolbase.py test_builder_reproduces_every_app_literal, test_button_specs_press_app_frames |
| D08 | command | Star (meaning unknown) frame `E5 FE 16 00 00 01 00 05`, single tap (T timing) | IMPLEMENTED | Command table V01; C03 | beds/coolbase.py STAR; coolbase_star button (frame existed, no entity before); tests/test_coolbase.py test_builder_reproduces_every_app_literal, test_button_specs_press_app_frames |
| D09 | command | Massage mode/level frame `E5 FE 16 00 00 00 04 02`, single tap (T timing) | IMPLEMENTED | Command table V01; C03 | beds/coolbase.py MASSAGE_LEVEL; coolbase_massage_mode button (frame existed, no entity before); tests/test_coolbase.py test_builder_reproduces_every_app_literal, test_button_specs_press_app_frames |
| D10 | command | Right fan frame `E5 FE 16 00 00 00 40 C6`, single tap (T timing) | IMPLEMENTED | Command table V01; C03 | beds/coolbase.py FAN_RIGHT; coolbase_right_fan button (frame existed, no entity before); tests/test_coolbase.py test_builder_reproduces_every_app_literal, test_button_specs_press_app_frames |
| D11 | command | Fan sync frame `E5 FE 16 00 00 04 00 02`, single tap (T timing) | IMPLEMENTED | Command table V01; C03 | beds/coolbase.py FAN_SYNC; coolbase_fan_sync button (frame existed, no entity before); tests/test_coolbase.py test_builder_reproduces_every_app_literal, test_button_specs_press_app_frames |
| D12 | command | TV preset frame `E5 FE 16 00 40 00 00 C6` | ALREADY_IMPLEMENTED | Command table V01; C03 | beds/coolbase.py PRESET_TV; preset_tv; tests/test_coolbase.py test_builder_reproduces_every_app_literal |
| D13 | command | ZG preset frame `E5 FE 16 00 10 00 00 F6` | ALREADY_IMPLEMENTED | Command table V01; C03 | beds/coolbase.py PRESET_ZERO_G; preset_zero_g; tests/test_coolbase.py test_builder_reproduces_every_app_literal |
| D14 | command | Flat frame `E5 FE 16 00 00 00 08 FE` | ALREADY_IMPLEMENTED | Command table V01; C03 | beds/coolbase.py PRESET_FLAT; preset_flat; tests/test_coolbase.py test_builder_reproduces_every_app_literal |
| D15 | command | Light frame `E5 FE 16 00 00 02 00 04` | ALREADY_IMPLEMENTED | Command table V01; C03 | beds/coolbase.py TOGGLE_LIGHT; lights_toggle and feedback light; tests/test_coolbase.py test_builder_reproduces_every_app_literal |
| D16 | command | Snore preset frame `E5 FE 16 00 80 00 00 86` | ALREADY_IMPLEMENTED | Command table V01; C03 | beds/coolbase.py PRESET_ANTI_SNORE; preset_anti_snore; tests/test_coolbase.py test_builder_reproduces_every_app_literal |
| D17 | command | Status query frame `E5 FE 16 00 00 00 00 06` (Q timing) | IMPLEMENTED | Command table V01 status query; C03 | beds/coolbase.py _send_status_query; tests/test_coolbase.py test_status_query_is_the_all_zero_frame |
| D18 | command | Maintenance firmware-entry literal `E2 5A 42 4C 35` (V02) | EXCLUDED | C07; E15 | Firmware-update transport, out of scope; also a safety constraint: it diverts the controller to its bootloader. Never sent. |
| D19 | builder | Eight-byte frame with literal trailer; no live checksum algorithm | ALREADY_IMPLEMENTED | Packet formats; C10 | beds/coolbase.py _build_command reproduces all 17 literals; tests/test_coolbase.py test_builder_reproduces_every_app_literal pins each literal |
| D20 | transport | Write FFE9 under service FFE5, fixed UUID lookup | ALREADY_IMPLEMENTED | GATT table; C03 | beds/coolbase.py control_characteristic_uuid, _init_write_mode restricted to FFE5; tests/test_coolbase.py test_control_characteristic_uuid, test_write_type_mirrors_android_default |
| D21 | transport | Write type inherited from the characteristic (Android default: no-response when advertised) | IMPLEMENTED | GATT table; command table write-type note | beds/coolbase.py _init_write_mode; tests/test_coolbase.py test_write_type_mirrors_android_default |
| D22 | transport | Notify subscription on FFE4 with standard CCCD, also with angle sensing off | IMPLEMENTED | GATT table; C04 | beds/coolbase.py start_notify, requires_notification_channel (previously skipped when angle sensing was disabled); tests/test_coolbase.py test_status_replies_subscribe_with_angle_sensing_disabled |
| D23 | transport | MTU 243 request; subscribe only after MTU success, no fallback | EXCLUDED | Session steps 4-5; C02 | Platform connection lifecycle owned by the Home Assistant Bluetooth stack; every frame is 8 or 5 bytes, so MTU never gates control. App-requested OS lifecycle is not a controller requirement (#436 hardware policy). |
| D24 | transport | Firmware revision read 2A26 and exact "1.03" update diversion | EXCLUDED | C04; E14/E15 | Firmware-update gating; out of scope. The value is not displayed by the app. |
| D25 | parser | Only exact 28-byte replies are parsed | IMPLEMENTED | Notification/parser table | beds/coolbase.py _parse_notification; tests/test_coolbase.py test_only_exact_28_byte_replies_are_parsed |
| D26 | parser | Left/right fan level bytes 20/21, 0-3, other values keep prior | IMPLEMENTED | Notification/parser table | beds/coolbase.py _parse_notification, STATE_LEFT_FAN/STATE_RIGHT_FAN sensors; tests/test_coolbase.py test_parser_vectors, test_out_of_range_values_keep_previous_state |
| D27 | parser | Light flag `(b13 & 0xF0) >> 6`, 0/1 only, other values keep prior | IMPLEMENTED | Notification/parser table | beds/coolbase.py _parse_notification, get_light_state, supports_light_state_feedback; tests/test_coolbase.py test_out_of_range_values_keep_previous_state |
| D28 | parser | Massage mode byte 19, 0-3, other values keep prior | IMPLEMENTED | Notification/parser table | beds/coolbase.py _parse_notification, STATE_MASSAGE_MODE sensor; tests/test_coolbase.py test_parser_vectors |
| D29 | parser | All other offsets unused; no reassembly, checksum or ACK correlation | ALREADY_IMPLEMENTED | Notification/parser table | beds/coolbase.py _parse_notification reads only bytes 13/19/20/21; tests/test_coolbase.py test_parser_vectors |
| D30 | timing | Hold movement repeats every 100 ms (H timing) | ALREADY_IMPLEMENTED | Timing codes H; E12 | const.py BED_TYPE_COOLBASE pulse (10, 100); coordinator motor pulses |
| D31 | timing | Release ends the refresh with no distinct STOP frame | ALREADY_IMPLEMENTED | Timing section; E12 | beds/coolbase.py _move_motor ends the cancellable refresh; its trailing all-zero frame is the app status query, not an invented STOP; tests/test_coolbase.py test_move_head_up_sends_8_byte_packet, test_stop_all_sends_zero_command |
| D32 | timing | Tap: one write, then three status queries each after 200 ms | IMPLEMENTED | Timing code T; E13 | beds/coolbase.py tap; tests/test_coolbase.py test_tap_sends_command_then_three_spaced_status_queries |
| D33 | timing | Periodic 3000 ms status query while connected and idle | IMPLEMENTED | Timing code Q; E13 | beds/coolbase.py diagnostic_poll_interval/async_refresh_diagnostics (coordinator live-session poll, no idle renewal); tests/test_coolbase.py test_status_poll_mirrors_app_interval |
| D34 | timing | Poll thread may overlap movement; unsynchronized threads replace callbacks | EXCLUDED | Timing section; E09/E12/E13 | Safety constraint: the integration serializes every GATT write (AGENTS command serialization). The overlap is an app race, not protocol behavior. |
| D35 | session | No automatic bed reconnect after an unexpected disconnect | EXCLUDED | Session step 8; C02 | Platform connection lifecycle: the coordinator connects on demand for each command; app reconnect policy is not a controller requirement (#436 hardware policy). |
| D36 | session | Writes require only a connection, not notification readiness | EXCLUDED | Session step 6 | Platform lifecycle ordering: the coordinator subscribes before any command and the app sets no readiness gate to mirror. |
| D37 | dead | Stored autoConBle/deviceName/deviceid never read | EXCLUDED | Timing section (stored fields) | Dead code: written but never read for any reconnect path. |
| D38 | state | Reported state cleared when the session ends | IMPLEMENTED | Timing section (disconnect behavior) | beds/coolbase.py invalidate_diagnostics; tests/test_coolbase.py test_session_end_clears_reported_state |
| D39 | state | Light on/off uses the reported flag and toggles only on mismatch | IMPLEMENTED | Capability matrix light; parser table | beds/coolbase.py lights_on/lights_off/_set_light_state; tests/test_coolbase.py test_light_on_off_toggles_only_on_mismatch, test_unknown_light_state_queries_then_uses_reply, test_unknown_light_state_without_reply_raises |
| D40 | discovery | Scan name contains `base-i5` | IMPLEMENTED | Discovery matrix default list search; C01 | detection.py Cool Base substring match (case-insensitive, retained for the shared Keeson lineage); tests/test_detection.py test_detect_coolbase_by_base_i5_substring |
| D41 | discovery | QR lookup sets the next scan filter | EXCLUDED | Discovery matrix QR lookup; C09 | App UI identity entry; Home Assistant discovers by advertisement and stores the configured address. |
| D42 | discovery | Manual lookup with impossible success branch | EXCLUDED | Discovery matrix manual lookup; C09 | Dead code: the uppercase-versus-lowercase prefix test can never pass. |
| D43 | discovery | Selected-name rescan and first-result connect after 300 ms | EXCLUDED | Discovery matrix list item; C01 | App UI scan flow; the integration connects to the configured address, so substring-only first-result races cannot occur. |
| D44 | discovery | 12000 ms discovery-screen deadline and redirect | EXCLUDED | Discovery matrix deadline; C01/E25 | App screen lifecycle, not bed protocol; setup timing is owned by the config flow. |
| D45 | discovery | Hidden refresh/back callbacks with 2000 ms debounce | EXCLUDED | C20; E27 | Dead code: both views are GONE with no reveal or programmatic click. |
| D46 | discovery | Unexpected disconnect scans `BT01D_BOOT` | EXCLUDED | Discovery matrix maintenance; C02 | Firmware recovery path; out of scope. |
| D47 | session | Connect autoConnect=false, 5000 ms timeout, retry after 100 ms | EXCLUDED | Session step 3; C02 | Platform connection lifecycle owned by the coordinator; app retry policy is not a controller requirement (#436 hardware policy). |
| D48 | session | Service discovery 500 ms after connect, 300 ms settle | EXCLUDED | Session step 4; C02 | Platform connection lifecycle owned by the Home Assistant Bluetooth stack. |
| D49 | session | No authentication, PIN, bonding or connection-priority request | ALREADY_IMPLEMENTED | Session section; capability matrix auth | beds/coolbase.py requires no pairing or authentication step; tests/test_coolbase.py test_status_replies_subscribe_with_angle_sensing_disabled connects and subscribes without one |
| D50 | session | Single target connection; no dual or coupled movement | ALREADY_IMPLEMENTED | Capability matrix dual/split | beds/coolbase.py single coordinator connection; fan sync is not bed sync; tests/test_coolbase.py test_button_specs_press_app_frames |
| D51 | dead | Alternate write FFE0/FFE9 (writeToDevice2) | EXCLUDED | C05 | Dead code: no callers. |
| D52 | dead | Indication on 8ec90003-f315-4f60-9fb8-838830daea50 | EXCLUDED | C06 | Dead code: no callers. |
| D53 | dead | Encoder/checksum helpers (four-byte sum, faulty hex decoder, converters) | EXCLUDED | C10 | Dead code: not called by protocol code. |
| D54 | dead | Memory/remote-choice assets | EXCLUDED | C11 | Dead code: no live resource references. |
| D55 | dead | Wi-Fi placeholder fields | EXCLUDED | C12 | Dead code: never routed to a transport. |
| D56 | dead | Unused SDK RSSI/priority/indication/unsubscribe/custom-descriptor branches | EXCLUDED | C14 | Dead code inside the BLE SDK. |
| D57 | firmware | Six firmware SDK implementations and DFU transfer | EXCLUDED | C15; E16 | Firmware-update transport; out of scope. |
| D58 | firmware | Embedded firmware payloads and firmware-only strings | EXCLUDED | C16; E22 | Device firmware, not app-loaded code; firmware update out of scope. |
| D59 | firmware | Update screen: boot-name scan, 70 s timeout, keepBond, buttonless DFU | EXCLUDED | Timing section firmware trigger; E15 | Firmware-update flow; out of scope. |
| D60 | platform | Permission, GPS and adapter availability gates | EXCLUDED | C17 | Android platform gating; Home Assistant owns Bluetooth availability. |
| D61 | platform | Phone-vendor permission routing, privacy browser intent, UI/support libraries | EXCLUDED | C13; C18; C19 | Unrelated to bed control. |
| D62 | capability | Motors: head/back and foot/leg up/down | ALREADY_IMPLEMENTED | Capability matrix motors | beds/coolbase.py move_head_*/move_feet_*; motor_count 2; tests/test_coolbase.py test_motor_commands, test_move_head_up_sends_8_byte_packet |
| D63 | capability | Presets TV, ZG, snore, flat | ALREADY_IMPLEMENTED | Capability matrix presets | beds/coolbase.py supports_preset_tv/zero_g/anti_snore and preset_flat; tests/test_coolbase.py test_supports_preset_tv, test_supports_preset_zero_g, test_supports_preset_anti_snore, test_builder_reproduces_every_app_literal |
| D64 | capability | No lounge preset in the app | IMPLEMENTED | Capability matrix presets | beds/coolbase.py supports_preset_lounge False for Cool Base; tests/test_coolbase.py test_cool_base_profile_has_no_inferred_memory_or_lounge |
| D65 | capability | Star button meaning unknown; no memory save/recall path | IMPLEMENTED | Capability matrix memory; C11 | beds/coolbase.py memory_slot_count 0, coolbase_star button; tests/test_coolbase.py test_cool_base_profile_has_no_inferred_memory_or_lounge |
| D66 | capability | Massage: head, foot and mode buttons as app-labelled taps | IMPLEMENTED | Capability matrix massage | beds/coolbase.py controller_button_specs; frontend discovery massage bucket; tests/test_coolbase.py test_button_specs_press_app_frames |
| D67 | capability | Fans: left, right and sync buttons with reported levels | IMPLEMENTED | Capability matrix fans | beds/coolbase.py controller_button_specs and controller_state_sensor_specs; frontend discovery utility bucket |
| D68 | capability | Light: fixed toggle, no brightness/colour/timer | ALREADY_IMPLEMENTED | Capability matrix light | beds/coolbase.py supports_discrete_light_control False; no level/colour capability; tests/test_coolbase.py test_capability_surface_has_no_position_or_settings |
| D69 | capability | No position, sensor, error, battery, lock or alarm fields | ALREADY_IMPLEMENTED | Capability matrix sensors | beds/coolbase.py read_positions no-op; Cool Base absent from BEDS_WITH_POSITION_FEEDBACK; tests/test_coolbase.py test_capability_surface_has_no_position_or_settings |
| D70 | capability | No EEPROM, settings, reset or calibration writes | ALREADY_IMPLEMENTED | Capability matrix EEPROM | beds/coolbase.py exposes no such action; tests/test_coolbase.py test_capability_surface_has_no_position_or_settings |

## Deferred external validation

For real users after a beta or release: whether release without a distinct STOP halts motion promptly, what the star button does, how massage mode and fan levels cycle on the device, and the characteristic write properties reported by the controller. None of these blocks the static implementation.
