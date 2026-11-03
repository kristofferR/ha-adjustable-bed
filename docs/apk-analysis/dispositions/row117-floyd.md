# Row117 Floyd Home 1.0.7 implementation dispositions

This is the separate post-freeze comparison, not a clean-room analysis.
Authority: independently accepted COMPLETE report for `com.kaidi_test4.floyd`
1.0.7 (7), six-member delivery, all 17 gates accepted with zero material findings.
Old partial reports are history only. Raw artifacts/reports remain local and
ignored; only derived integration documentation and tests are committed.

| Seal | SHA-256 |
| --- | --- |
| Artifact set | `09001ded373f0b659c6645e7fd94aa963b2cc91a4eb3d2de22d1a0883f177c8f` |
| Accepted REPORT.SHA256 | `455f487d3987a5661124f4f565ae3a99dc29853678f78a6fa7d39baffe2565a4` |
| Independent AUDIT.SHA256 | `be869ca014a1e5cb3f7928d02a103cf1acabcd888f3c115e0ce015b93dab01cf` |

All three seals and their members were reverified read-only before comparison.
The accepted report is `work/report-sol-001` and audit `audit/sol-round001` in
the persistent package workspace dated `2026-11-03-bulk101-188-001`. E1-E18 below
are its frozen evidence IDs. Its 101 protocol vectors, 770 shipped-JS order and
target checks, 15 member orders/35 choices, 179 Bluetooth invokes and 25 variant
entries establish the exhaustive discovery boundary. This ledger accounts for
those reachable behaviors; dead/unrelated tables are explicitly excluded below.
Physical effects are deferred external validation after beta/release.

Implementation paths below are relative to `custom_components/adjustable_bed/`.
`F` = `beds/floyd.py`, `K` = `beds/kaidi.py`, `P` = `kaidi_protocol.py`,
`S` = `services.py`. Tests are in `tests/test_floyd.py` unless explicitly named.
Each ID has exactly one disposition. Reuse requires code and test equivalence,
not a common app brand or a transport-family assumption.

| ID | Discovery / exact accepted evidence | Disposition | Code and verification / reason |
| --- | --- | --- | --- |
| D01 | E3/E8: manufacturer prefix, types 01/02/09, product 139, company 4b44, actuator gates and RSSI >= -92 | IMPLEMENTED | P `is_floyd_advertisement`, detection exact-product signal; `test_floyd_exact_admission_vectors`, `test_floyd_discovery_without_shared_name_or_uuid`. Unknown generic products retain conservative detection. |
| D02 | E8: manufacturer offsets, LE room/vAddr, BE actuator; type02 a0/a1 versus extended 28-byte layout | ALREADY_IMPLEMENTED | P `parse_kaidi_manufacturer_payload`; `tests/test_kaidi.py::test_parse_broadcast_advertisement_payload`, `test_extract_single_advertisement_payload`, `test_parse_issue247_broadcast_payload`, plus Floyd admission vectors. No unsafe 27-byte read is reproduced. |
| D03 | E3: only admitted product 139 selects UI2 | IMPLEMENTED | `kaidi_variants.resolve_kaidi_variant`, factory lazy Floyd selection and explicit app choice; `test_profile_selection_and_capability_boundaries`, `test_factory_selects_floyd_from_advertisement`. Known other products cannot use the explicit Floyd controller. |
| D04 | E4: discover all services for write/notify UUID, CCCD according to properties | ALREADY_IMPLEMENTED | K `_ensure_notify_started` and `_refresh_write_mode`, HA/Bleak CCCD; `tests/test_kaidi.py::test_session_pings_when_advertisement_lacks_vaddr` and Floyd session test. No service/name predicate imposed on Floyd admission. |
| D05 | E4: runtime write type not statically supplied | ALREADY_IMPLEMENTED | K `_refresh_write_mode` discovers supported write properties; `test_gatt_write_properties_and_subscription` in `tests/test_floyd.py`. Static report does not prove a physical write mode. |
| D06 | E6: room assignment 0103 + LE32 room + 1122 + zero4; status0203 | IMPLEMENTED | F `floyd_action`, S `handle_floyd_action`; `test_assignment_and_confirmation_vectors`, `test_room_service_persists_disconnects_and_confirms`. Explicit confirmation and positive unassigned-advertisement proof for one standalone bed; persist inside the acknowledged operation, then disconnect/reconnect. `test_preempted_assignment_never_persists_or_confirms` uses the real scheduler; `test_assignment_requires_positive_unassigned_evidence` rejects unknown membership. `coordinator.remember_floyd_room` suppresses mid-service entry reload; `test_acknowledged_room_persistence_suppresses_mid_service_reload` covers persistence and stale advertisement refresh. |
| D07 | E6: auth011601 + LE32 room + 1122; status0216 | IMPLEMENTED | F `_ensure_session_ready`, `_handle_notification`; `test_authentication_ping_identity_and_zero_target`, `test_auth_failure_and_offline_target_never_write_controls`. HA rejects failure rather than copying app's success-less logging path. |
| D08 | E9: own identity010a, raw4; zero remaps ffffffff | IMPLEMENTED | F parser, initial own0, ping source; `test_authentication_ping_identity_and_zero_target`. |
| D09 | E9: count0102, unsignedLE16 bytes8/9; reset online targets | IMPLEMENTED | F parser invalidates target/session, next command authenticates/pings; session and target-change release tests. No stale cached address authorizes a control. |
| D10 | E4/E9: ping03fffffffffe own4; ff channel reverseMAC6 + signedLE32 node | IMPLEMENTED | F live matching-node readiness; session vector includes wrong node and zero sentinel. Stored0 is rejected; live0 encodes0 via -2. Signed nonzero normal targets are narrowed to LE32; conditional alarm selectors require positive/-2, covered by `test_signed_target_domains_differ_for_normal_and_conditional_paths`. |
| D11 | E6/E7: addition confirmation opcode45 on resolved target | IMPLEMENTED | F `confirm_add`; S assignment reconnect sequence; assignment vector and room service order test. Retry is explicit if interrupted after assignment. |
| D12 | E5: 14-byte control, dynamic own/target, channel20, sofa01000000 | IMPLEMENTED | F `_build_control_packet`; `test_normal_command_vectors` exact complete frames. |
| D13 | E5/E15: progress parameter retained by ordinary sends and room switches | IMPLEMENTED | F retained parameter in coordinator state and protocol diagnostics; `test_confirmed_overwrite_retains_parameter`. Fresh HA integration load initializes0; reconnection does not reset it. |
| C01 | E7/E14: head up01, release03 | IMPLEMENTED | F profile/hold; `test_start_once_then_release[head_up-1-3]`, normal vectors. |
| C02 | E7/E14: head down02, release03 | IMPLEMENTED | F profile/hold; `test_start_once_then_release[head_down-2-3]`. |
| C03 | E7/E14: feet up04, release06 | IMPLEMENTED | F profile/hold; `test_start_once_then_release[feet_up-4-6]`. |
| C04 | E7/E14: feet down05, release06 | IMPLEMENTED | F profile/hold; `test_start_once_then_release[feet_down-5-6]`. |
| C05 | E7/E14: combined up07, release09 | IMPLEMENTED | `hold_control` action `head_feet_up`; exact hold vectors. |
| C06 | E7/E14: combined down08, release09 | IMPLEMENTED | `hold_control` action `head_feet_down`; exact hold vectors and service dispatch. |
| C07 | E7: Flat1c, not STOP/old68 | IMPLEMENTED | F preset; `test_normal_command_vectors[preset_flat-args0-28]`. |
| C08 | E7: Zero gravity62 | ALREADY_IMPLEMENTED | K `preset_zero_g`, Floyd-specific profile retains62; normal vectors. |
| C09 | E7: Anti-snore65 | ALREADY_IMPLEMENTED | K `preset_anti_snore`, Floyd-specific profile retains65; normal vectors. |
| C10 | E7: saveM1=25 | ALREADY_IMPLEMENTED | K `program_memory`, Floyd profile slot1; normal vectors. |
| C11 | E7: saveM2=26 | ALREADY_IMPLEMENTED | K `program_memory`, Floyd profile slot2; normal vectors. |
| C12 | E7: saveM3=27 | ALREADY_IMPLEMENTED | K `program_memory`, Floyd profile slot3; normal vectors. |
| C13 | E7: recallM1=29 | ALREADY_IMPLEMENTED | K `preset_memory`, Floyd profile slot1; normal vectors. |
| C14 | E7: recallM2=2a | ALREADY_IMPLEMENTED | K `preset_memory`, Floyd profile slot2; normal vectors. |
| C15 | E7: recallM3=2b | ALREADY_IMPLEMENTED | K `preset_memory`, Floyd profile slot3; normal vectors. |
| C16 | E7: under-bed light on5c | IMPLEMENTED | F capability exposes inherited K `lights_on`, normal vectors. No unproven feedback. |
| C17 | E7: under-bed light off5d | IMPLEMENTED | F capability exposes inherited K `lights_off`, normal vectors. |
| C18 | E7/E15: overwriteZG=a7,param1 after confirmation | IMPLEMENTED | F `save_zero_g`, S confirmed action; overwrite retention and service tests. |
| C19 | E7/E15: overwrite snore=a7,param4 after confirmation | IMPLEMENTED | F `save_anti_snore`, S confirmed action; overwrite retention and service tests. |
| A01 | E16: internal both ZG64 | IMPLEMENTED | F `FLOYD_PRESETS`, `floyd_action internal_side: both`; `test_all_exported_alarm_selectors`. |
| A02 | E16: internal both Flat1e | IMPLEMENTED | Same action and all-selector vectors. |
| A03 | E16: internal both snore67 | IMPLEMENTED | Same action and all-selector vectors. |
| A04 | E16: internal both M1=39 | IMPLEMENTED | Same action and all-selector vectors. |
| A05 | E16: internal both M2=3a | IMPLEMENTED | Same action and all-selector vectors. |
| A06 | E16: internal both M3=3b | IMPLEMENTED | Same action and all-selector vectors. |
| A07 | E16: internal second ZG63 | IMPLEMENTED | F `FLOYD_PRESETS`, `floyd_action internal_side: second`; all-selector vectors. |
| A08 | E16: internal second Flat1d | IMPLEMENTED | Same action; all-selector vectors and service routing. |
| A09 | E16: internal second snore66 | IMPLEMENTED | Same action and all-selector vectors. |
| A10 | E16: internal second M1=31 | IMPLEMENTED | Same action and all-selector vectors. |
| A11 | E16: internal second M2=32 | IMPLEMENTED | Same action and all-selector vectors. |
| A12 | E16: internal second M3=33 | IMPLEMENTED | Same action and all-selector vectors. First-side six receiver branches duplicate C07-C09/C13-C15, tested in same 18-selector matrix. |
| N01 | E9: channel20,len>=8, payload5=a6,payload6=1 battery mode | IMPLEMENTED | F binary sensor and raise gate, no invented battery percentage; battery event/diagnostic tests. Down/release always remain available. Known battery mode is also checked before any timed target executes (`test_timed_preflight_battery_failure_prevents_every_target`). |
| N02 | E9: channel2f invokes phone schedule observer | EXCLUDED | Payload ignored by app; no bed clock or alarm state. Phone scheduling belongs to HA automations using implemented presets; no extra BLE sender exists. E13 normal receiver and E16 delayed6/7 aliases add no new bed command. |
| N03 | E9: channel12 subcommands4/5/7/8 statusbyte11;9 progressbyte9 | EXCLUDED | App logs only; no reachable bed query/UI state. Raw notification forwarding retains diagnostics, without fabricating OTA/program state. E11 dead updater has no central caller. |
| N04 | E10: channels23/24/25/28 product80/groupd7, signed product/group, differing new/existing vAddr offsets | EXCLUDED | SDK generic DeviceBean list only, no app capability or bed-state consumer. Not interpreted as bed product selection. Raw diagnostics preserve incoming bytes; no read/query is reachable. |
| N05 | E9: cmd0101, type04, channelb0, unknown channels | EXCLUDED | Ignored/false-return central dispatch, no bed functionality. Short malformed PDUs are safely ignored; `test_malformed_notifications_are_ignored`. |
| T01 | E4: queue tick50ms, callback readiness, no retry/timeout/STOPpriority | IMPLEMENTED | F `_send` awaits write completion and spaces writes>=50ms; `test_queue_spacing`. Uses HA bounded transport failure handling instead of reproducing a queue that can hang forever or drop releases. |
| T02 | E14: press starts once, pressout/termination releases once; no held refresh | IMPLEMENTED | F `hold_control` and movement wrapper; all six hold vectors. HA duration bounds are safety policy, not an inferred firmware timer. Authentication precedes the external movement window (`test_timed_movement_prepares_before_deadline`). |
| T03 | E14: no guaranteed unmount/background cleanup, release recalculates target | IMPLEMENTED | HA corrects harmful app lifecycle behavior: finally release with fresh cancel event and captured target. Cancellation/failure and topology-change tests; existing card hold cleanup remains in use. |
| T04 | E9/E13: disconnect closes link/queue/map; room switch rejoins | IMPLEMENTED | F `on_disconnect` invalidates session, target and battery; next command reauth/pings. Retained outgoing parameter preserved within HA entry. No claimed physical STOP from link loss. |
| V01 | E3/E7/E17: seven location sets, 15 orders, 35 choices; [3,4] center fans out, [2,3,4] selects actual center | ALREADY_IMPLEMENTED | HA device/child targeting replaces phone placement DB. `services._resolve_sided_targets`, `paired_devices.py`; `tests/test_paired_devices.py`, `tests/test_paired_coordinator.py`; Floyd service tests prove same first-side command per selected physical address. Exact report member orders affect local target choice only, not opcode. |
| V02 | E15: built-in overwrite sends only last global target in app | IMPLEMENTED | HA deliberately programs every explicitly selected physical target, preflighting all targets first. `test_service_routes_two_address_overwrite_and_conditional_presets`, `test_service_validates_all_targets_before_overwrite`. |
| V03 | E3/E7: UI2 capabilities, three user memories, no position/massage/extra-axis poll | IMPLEMENTED | F sparse profile and explicit two-axis controls, no guessed fourth memory/direct position commands; profile capability test, memory4 rejection. |
| V04 | E3/E13: local placement/name/room DB, language/theme/vibration, memory rename, phone alarm/dismiss/snooze | EXCLUDED | Phone/HA application settings, not BLE commands. Existing HA devices, labels and automations own these. 500ms longpress is UI trigger, not a hardware hold for saving; save is single-shot. |
| X01 | E6: reset conflicting room by company0000,payloadc0ff07 reverseMAC 01 for5s | EXCLUDED | Safety: unauthenticated advertising reset evicts an existing room owner without acknowledgement or ownership proof. HA supports adoption and explicit unassigned assignment, not destructive room takeover. Use official app for intentional takeover. |
| X02 | E3/E7: products100-102,129-138,location1, massage/voice/extra axes/locks | EXCLUDED | Dead/unselectable normal Floyd paths. Shared tables do not prove product139 capability; E16 reachable conditional presets are implemented separately in A01-A12. |
| X03 | E11/E12: peripheralffd0/ffd1/ffd2 server, OTA/PWM/read/RSSI/descriptor helpers | EXCLUDED | No constructor/setupServices/openGattServer/callers install that stack in shipped app. Dead code, no implementation debt. |
| X04 | E2/E17: native engines, SDKs and 60s daemon | EXCLUDED | Runtime/phone infrastructure, no app BLE JNI builder/bridge. All app BLE senders are covered above. |
| X05 | E2/E18: SDK endpoints/certificates, licensing, ASR, uncalled HTTP, network permissions | EXCLUDED | Unrelated SDK/cloud/account infrastructure. Bed Wi-Fi/SSID/password/network provisioning is outside product boundary; no such reachable bed path found. |

## Safe HA behavior and evidence limits

HA does not duplicate malformed-input exceptions, an unbounded callback queue,
stale offline virtual addresses, battery-gated release suppression, target
recalculation during release, or last-only overwrite fanout. These are explicit
safety corrections, not new protocol bytes. No measured position, physical
movement timeout, optional model capability or dual-side movement is inferred.
The conditional exported receiver supports only the twelve extra preset opcodes
above. Normal Floyd setup admits product139, not every common-table product.

Validation: focused Floyd vectors plus Kaidi compatibility, discovery,
controller contracts, app-profile and generic-service checks; Ruff and Pyright.
No raw artifact or decompilation is required by committed tests. Deferred user
captures after beta/release should verify physical releases/disconnects, GATT
properties, room assignment, preset overwrite, lighting and optional battery
mode. Static implementation has no missing-hardware blocker.
