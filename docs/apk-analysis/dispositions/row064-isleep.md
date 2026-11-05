# Row064: ISleep 1.6.3 (45), com.kaidi_test4

Post-freeze comparison and implementation, not a clean-room analysis. Hardware **UNVERIFIED**; real-user beta/release captures remain deferred.

Artifact set `6102a03e00d45ac1c12a5c9effb2eb7255128d8dfd5e5c24c5af7f9929e2d897`. Accepted report `report-revision-sol-002`, seal `d00ec6709a9cfd53c7e254590e95fb9ee21151db47e35eb1a10ceeb47a2198f1` (52 entries), handoff `aee825c24fa66a6290cbf3b1e60df114fbc4c75aa300bff16d400727d1f12a11`. Independent audit `audit-sol-round03`, ACCEPT, 17 PASS, seal `fe33a01ce0a19ee55c172310f5344b5d5c5e18befcd65cd91bacad992d751fde`. Proposal-era report wording is superseded only by the separate acceptance receipt/audit. Frozen originals unchanged.

The evidence pointers below are package-local relative to that sealed report. Evidence IDs resolve through `analysis.json#/evidence` and ANALYSIS.md's evidence index. Raw APKs, reports, decompilation and the machine-readable ledger stay machine-local.

## Session safety boundary

HA uses an explicit per-physical-address room/profile configuration. Existing rooms are adopted, never silently reset. Fresh mode09 enrollment is an explicit action into the selected room. Resetting an already-enrolled bed with mode07 advertising is EXCLUDED for safety because it removes existing room ownership. Android SQL allocation, random room/label generation, optimistic add success, wrong-target timer routing, stale global callbacks and missing STOP on unmount are EXCLUDED app infrastructure/defects. HA configuration identity and live matching-MAC roster replace those mechanisms; a BLE success reply alone never creates a different target. No virtual address is trusted after disconnect.

Each ledger row has exactly one disposition. IMPLEMENTED rows are implementation obligations until the referenced tests and validation pass; these labels alone do not claim completion. There are no ALREADY_IMPLEMENTED claims based only on identical bytes.

## Command rows (114, including 105 unique UI opcodes)

| ID | Discovery | Disposition | Evidence |
|---|---|---|---|
| C000 | raise head region / 1 | IMPLEMENTED | analysis.json#/protocols/0/commands/0; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C001 | raise upper/back region / 1 | IMPLEMENTED | analysis.json#/protocols/0/commands/1; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C002 | lower head region / 2 | IMPLEMENTED | analysis.json#/protocols/0/commands/2; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C003 | lower upper/back region / 2 | IMPLEMENTED | analysis.json#/protocols/0/commands/3; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C004 | release head region / 3 | IMPLEMENTED | analysis.json#/protocols/0/commands/4; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C005 | release upper/back region / 3 | IMPLEMENTED | analysis.json#/protocols/0/commands/5; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C006 | raise feet/legs / 4 | IMPLEMENTED | analysis.json#/protocols/0/commands/6; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C007 | lower feet/legs / 5 | IMPLEMENTED | analysis.json#/protocols/0/commands/7; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C008 | release feet/legs / 6 | IMPLEMENTED | analysis.json#/protocols/0/commands/8; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C009 | raise combined axes / 7 | IMPLEMENTED | analysis.json#/protocols/0/commands/9; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C010 | lower combined axes / 8 | IMPLEMENTED | analysis.json#/protocols/0/commands/10; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C011 | release combined axes / 9 | IMPLEMENTED | analysis.json#/protocols/0/commands/11; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C012 | raise upper/back region / 10 | IMPLEMENTED | analysis.json#/protocols/0/commands/12; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C013 | lower upper/back region / 11 | IMPLEMENTED | analysis.json#/protocols/0/commands/13; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C014 | release upper/back region / 12 | IMPLEMENTED | analysis.json#/protocols/0/commands/14; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C015 | raise feet/legs / 13 | IMPLEMENTED | analysis.json#/protocols/0/commands/15; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C016 | lower feet/legs / 14 | IMPLEMENTED | analysis.json#/protocols/0/commands/16; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C017 | release feet/legs / 15 | IMPLEMENTED | analysis.json#/protocols/0/commands/17; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C018 | raise combined axes / 16 | IMPLEMENTED | analysis.json#/protocols/0/commands/18; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C019 | lower combined axes / 17 | IMPLEMENTED | analysis.json#/protocols/0/commands/19; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C020 | release combined axes / 18 | IMPLEMENTED | analysis.json#/protocols/0/commands/20; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C021 | raise upper/back region / 19 | IMPLEMENTED | analysis.json#/protocols/0/commands/21; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C022 | lower upper/back region / 20 | IMPLEMENTED | analysis.json#/protocols/0/commands/22; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C023 | release upper/back region / 21 | IMPLEMENTED | analysis.json#/protocols/0/commands/23; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C024 | raise feet/legs / 22 | IMPLEMENTED | analysis.json#/protocols/0/commands/24; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C025 | lower feet/legs / 23 | IMPLEMENTED | analysis.json#/protocols/0/commands/25; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C026 | release feet/legs / 24 | IMPLEMENTED | analysis.json#/protocols/0/commands/26; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C027 | raise combined axes / 25 | IMPLEMENTED | analysis.json#/protocols/0/commands/27; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C028 | lower combined axes / 26 | IMPLEMENTED | analysis.json#/protocols/0/commands/28; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C029 | release combined axes / 27 | IMPLEMENTED | analysis.json#/protocols/0/commands/29; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C030 | flat / 28 | IMPLEMENTED | analysis.json#/protocols/0/commands/30; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C031 | flat / 29 | IMPLEMENTED | analysis.json#/protocols/0/commands/31; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C032 | flat / 30 | IMPLEMENTED | analysis.json#/protocols/0/commands/32; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C033 | program memory 1 / 37 | IMPLEMENTED | analysis.json#/protocols/0/commands/33; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C034 | program memory 2 / 38 | IMPLEMENTED | analysis.json#/protocols/0/commands/34; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C035 | program memory 3 / 39 | IMPLEMENTED | analysis.json#/protocols/0/commands/35; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C036 | recall memory 1 / 41 | IMPLEMENTED | analysis.json#/protocols/0/commands/36; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C037 | recall memory 2 / 42 | IMPLEMENTED | analysis.json#/protocols/0/commands/37; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C038 | recall memory 3 / 43 | IMPLEMENTED | analysis.json#/protocols/0/commands/38; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C039 | program memory 1 / 45 | IMPLEMENTED | analysis.json#/protocols/0/commands/39; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C040 | program memory 2 / 46 | IMPLEMENTED | analysis.json#/protocols/0/commands/40; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C041 | program memory 3 / 47 | IMPLEMENTED | analysis.json#/protocols/0/commands/41; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C042 | recall memory 1 / 49 | IMPLEMENTED | analysis.json#/protocols/0/commands/42; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C043 | recall memory 2 / 50 | IMPLEMENTED | analysis.json#/protocols/0/commands/43; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C044 | recall memory 3 / 51 | IMPLEMENTED | analysis.json#/protocols/0/commands/44; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C045 | program memory 1 / 53 | IMPLEMENTED | analysis.json#/protocols/0/commands/45; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C046 | program memory 2 / 54 | IMPLEMENTED | analysis.json#/protocols/0/commands/46; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C047 | program memory 3 / 55 | IMPLEMENTED | analysis.json#/protocols/0/commands/47; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C048 | recall memory 1 / 57 | IMPLEMENTED | analysis.json#/protocols/0/commands/48; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C049 | recall memory 2 / 58 | IMPLEMENTED | analysis.json#/protocols/0/commands/49; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C050 | recall memory 3 / 59 | IMPLEMENTED | analysis.json#/protocols/0/commands/50; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C051 | massage on / 71 | IMPLEMENTED | analysis.json#/protocols/0/commands/51; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C052 | massage off / 72 | IMPLEMENTED | analysis.json#/protocols/0/commands/52; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C053 | massage on / 73 | IMPLEMENTED | analysis.json#/protocols/0/commands/53; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C054 | massage off / 74 | IMPLEMENTED | analysis.json#/protocols/0/commands/54; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C055 | massage on / 75 | IMPLEMENTED | analysis.json#/protocols/0/commands/55; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C056 | massage off / 76 | IMPLEMENTED | analysis.json#/protocols/0/commands/56; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C057 | set head massage strength / 77 | IMPLEMENTED | analysis.json#/protocols/0/commands/57; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C058 | set head massage strength / 78 | IMPLEMENTED | analysis.json#/protocols/0/commands/58; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C059 | set leg massage strength / 79 | IMPLEMENTED | analysis.json#/protocols/0/commands/59; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C060 | set leg massage strength / 80 | IMPLEMENTED | analysis.json#/protocols/0/commands/60; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C061 | set head massage strength / 81 | IMPLEMENTED | analysis.json#/protocols/0/commands/61; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C062 | set leg massage strength / 82 | IMPLEMENTED | analysis.json#/protocols/0/commands/62; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C063 | massage timer choice 1 / 83 | IMPLEMENTED | analysis.json#/protocols/0/commands/63; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C064 | massage timer choice 2 / 84 | IMPLEMENTED | analysis.json#/protocols/0/commands/64; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C065 | massage timer choice 3 / 85 | IMPLEMENTED | analysis.json#/protocols/0/commands/65; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C066 | massage timer choice 1 / 86 | IMPLEMENTED | analysis.json#/protocols/0/commands/66; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C067 | massage timer choice 2 / 87 | IMPLEMENTED | analysis.json#/protocols/0/commands/67; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C068 | massage timer choice 3 / 88 | IMPLEMENTED | analysis.json#/protocols/0/commands/68; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C069 | massage timer choice 1 / 89 | IMPLEMENTED | analysis.json#/protocols/0/commands/69; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C070 | massage timer choice 2 / 90 | IMPLEMENTED | analysis.json#/protocols/0/commands/70; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C071 | massage timer choice 3 / 91 | IMPLEMENTED | analysis.json#/protocols/0/commands/71; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C072 | light on / 92 | IMPLEMENTED | analysis.json#/protocols/0/commands/72; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C073 | light off / 93 | IMPLEMENTED | analysis.json#/protocols/0/commands/73; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C074 | light on / 94 | IMPLEMENTED | analysis.json#/protocols/0/commands/74; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C075 | light off / 95 | IMPLEMENTED | analysis.json#/protocols/0/commands/75; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C076 | light on / 96 | IMPLEMENTED | analysis.json#/protocols/0/commands/76; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C077 | light off / 97 | IMPLEMENTED | analysis.json#/protocols/0/commands/77; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C078 | zero gravity / 98 | IMPLEMENTED | analysis.json#/protocols/0/commands/78; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C079 | zero gravity / 99 | IMPLEMENTED | analysis.json#/protocols/0/commands/79; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C080 | zero gravity / 100 | IMPLEMENTED | analysis.json#/protocols/0/commands/80; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C081 | anti-snore / 101 | IMPLEMENTED | analysis.json#/protocols/0/commands/81; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C082 | anti-snore / 102 | IMPLEMENTED | analysis.json#/protocols/0/commands/82; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C083 | anti-snore / 103 | IMPLEMENTED | analysis.json#/protocols/0/commands/83; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C084 | massage pattern 1 / 107 | IMPLEMENTED | analysis.json#/protocols/0/commands/84; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C085 | massage pattern 1 / 108 | IMPLEMENTED | analysis.json#/protocols/0/commands/85; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C086 | massage pattern 1 / 109 | IMPLEMENTED | analysis.json#/protocols/0/commands/86; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C087 | massage pattern 2 / 110 | IMPLEMENTED | analysis.json#/protocols/0/commands/87; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C088 | massage pattern 2 / 111 | IMPLEMENTED | analysis.json#/protocols/0/commands/88; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C089 | massage pattern 2 / 112 | IMPLEMENTED | analysis.json#/protocols/0/commands/89; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C090 | massage pattern 3 / 113 | IMPLEMENTED | analysis.json#/protocols/0/commands/90; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C091 | massage pattern 3 / 114 | IMPLEMENTED | analysis.json#/protocols/0/commands/91; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C092 | massage pattern 3 / 115 | IMPLEMENTED | analysis.json#/protocols/0/commands/92; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C093 | cancel massage pattern / 116 | IMPLEMENTED | analysis.json#/protocols/0/commands/93; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C094 | cancel massage pattern / 117 | IMPLEMENTED | analysis.json#/protocols/0/commands/94; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C095 | cancel massage pattern / 118 | IMPLEMENTED | analysis.json#/protocols/0/commands/95; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C096 | cancel massage timer / 119 | IMPLEMENTED | analysis.json#/protocols/0/commands/96; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C097 | cancel massage timer / 120 | IMPLEMENTED | analysis.json#/protocols/0/commands/97; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C098 | cancel massage timer / 121 | IMPLEMENTED | analysis.json#/protocols/0/commands/98; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C099 | raise upper/back region / 122 | IMPLEMENTED | analysis.json#/protocols/0/commands/99; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C100 | lower upper/back region / 123 | IMPLEMENTED | analysis.json#/protocols/0/commands/100; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C101 | release upper/back region / 124 | IMPLEMENTED | analysis.json#/protocols/0/commands/101; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C102 | raise waist / 131 | IMPLEMENTED | analysis.json#/protocols/0/commands/102; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C103 | lower waist / 132 | IMPLEMENTED | analysis.json#/protocols/0/commands/103; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C104 | release waist / 133 | IMPLEMENTED | analysis.json#/protocols/0/commands/104; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C105 | raise combined axes / 149 | IMPLEMENTED | analysis.json#/protocols/0/commands/105; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C106 | lower combined axes / 150 | IMPLEMENTED | analysis.json#/protocols/0/commands/106; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C107 | release combined axes / 151 | IMPLEMENTED | analysis.json#/protocols/0/commands/107; E-JS-CONTROL,E-BRIDGE,E-BUILDER,E-TRANSPORT,E-LIFECYCLE |
| C108 | authenticate selected room | IMPLEMENTED | analysis.json#/protocols/0/commands/108; E-SESSION,E-PARSERS,E-TRANSPORT,E-BUILDER,E-ROOM-SESSION |
| C109 | enroll fresh device into room | IMPLEMENTED | analysis.json#/protocols/0/commands/109; E-SESSION,E-PARSERS,E-TRANSPORT,E-BUILDER,E-ROOM-SESSION,E-PERSISTENCE |
| C110 | ping room roster | IMPLEMENTED | analysis.json#/protocols/0/commands/110; E-SESSION,E-PARSERS,E-TRANSPORT,E-BUILDER |
| C111 | acknowledge added device | IMPLEMENTED | analysis.json#/protocols/0/commands/111; E-SESSION,E-PARSERS,E-TRANSPORT,E-BUILDER,E-ROOM-SESSION,E-PERSISTENCE |
| C112 | reset foreign-room device for enrollment | EXCLUDED | analysis.json#/protocols/0/commands/112; E-SESSION,E-TRANSPORT,E-ROOM-SESSION |
| C113 | subscribe notification/indication characteristic | IMPLEMENTED | analysis.json#/protocols/0/commands/113; E-TRANSPORT |

## Implementation and proof map

All paths below are relative to `custom_components/adjustable_bed/` unless a
`tests/` prefix is given. Command vectors live in
`tests/fixtures/isleep_row064_commands.json`: 108 UI rows with 105 distinct
opcodes. `tests/test_isleep.py::test_all_108_ui_rows_each_product_and_lane`
executes each row through the public action/movement method for **every**
applicable product and side, checking press count, packet bytes and matching
release. The pure byte builder alone is not treated as lifecycle equivalence.

| Coverage | Implementation | Focused proof in tests/test_isleep.py |
|---|---|---|
| C000-C107, all products/lanes | beds/isleep.py COMMANDS, _axis, _move, _action; motor_control_specs and capability properties | test_all_108_ui_rows_each_product_and_lane; test_exact_product_capabilities; test_exact_role1_side_gate |
| Movement, STOP, retained parameter | _move, _stop, stop_all, control_frame | test_strength_retained_into_move_release_and_preset; test_cancelled_hold_releases_same_lane_and_original_target; test_task_cancellation_and_write_failure_both_release; test_disconnect_during_hold_never_reconnects_to_deliver_release; test_stop_uses_axis_releases_never_flat |
| Invalid/no-write transitions | validation before _action; cancellation, session generation checks | test_invalid_actions_and_cancelled_admission_write_nothing; test_auth_rejection_never_writes_control; test_timeout_and_disconnect_unblock_without_controls; test_old_notification_callback_cannot_poison_reconnected_session |
| C108 auth, C110 ping, C113 notify | room_frame, start_notify, _ensure_session, _notification | test_exact_auth_ping_and_current_mac_roster; test_exact_room_builders; test_parser_sentinels_lengths_and_no_false_telemetry |
| C109 fresh enrollment, C111 pending ack, C112 reset exclusion | enroll_room; durable pending intent; current-MAC _ensure_session | test_enrollment_is_explicit_fresh_only_and_ack_is_durable; test_enrollment_never_resets_foreign_or_same_room; test_enrollment_failure_and_timeout_never_save_success; test_pending_ack_requires_matching_live_roster_and_successful_write |
| Discovery/product/room identity | isleep_profile.py; the `isleep` setup declaration in setup_questions.py (advertisement seed, checks and derived layout) for setup and Configure; app_profiles side ownership | test_advertisement_and_explicit_room_seed; test_discovery_gates_and_truncated_mode2_alternate; test_setup_and_options_preserve_explicit_profile; test_profile_ownership_and_app_search |
| Massage strength/pattern/timer/cancel and optimistic persistence | set_massage_intensity, set_pattern, set_massage_timer, persisted_app_state | all command rows; test_pattern_and_timer_toggle_cancel_are_distinct_from_massage_off; test_saved_intent_survives_reconnect_without_restoring_live_addresses |
| Shared transport and paired infrastructure | controller_factory registry, pairing runtime gate, per-side profile; existing coordinator serialization | tests/test_controller_contract.py; tests/test_kaidi.py; tests/test_app_profiles.py; tests/test_paired_setup.py; tests/test_config_flow.py |
| User exposure | native covers, memory/preset/light/massage entities, controller buttons; frontend discovery | frontend/src/discovery.test.ts ISleep case; frontend typecheck/build/test |

See [ISleep](../../beds/isleep.md) for user setup, wire formats, safety decisions
and deferred external validation. Existing Kaidi entries are not migrated by
this change. Shared-transport discovery offers the ISleep choice without
identifying it from sibling names/UUIDs. HA infrastructure owns adapter/proxy
selection, freshness, CCCD/indications and GATT completion. Android background
scan, queue polling, UI animations, phone alarms and SQL mechanics are not new
bed protocol features. The artifact's all-row discovery RSSI/dedup policies are
phone inventory policy; explicit HA setup and HA Bluetooth own admission and
physical-address uniqueness, avoiding false app attribution and hidden beds.

The phone's static strength parameter survives its connection changes but
resets at process startup. HA deliberately persists requested intent across HA
restart too. This is optimistic state, never telemetry. Combined-side requests
update both requested side states, and each physical target retains its own
layout/session. The wrong-target timer, global stale selection, early-ready,
SQL collision, malformed parser bounds, dropped-release-on-unmount and
unchecked GATT callback defects are explicitly excluded safety behavior.

No Android timer/rename dialog is required for explicit HA memory programming;
its one proven wire action is exposed directly. No onboard scheduling,
position feedback, fourth memory slot, extra UI5 axes or Book/Leisure presets
are invented from constants or model numbers. All reachable direct BLE
operations have the dispositions below. `ALREADY_IMPLEMENTED` count is zero;
shared framework reuse is not claimed to be APK-level semantic equivalence.

## Remaining inventory dispositions

Each source member has one row below; the full machine-local `ledger.json`
retains its exact source object and validation mapping. For K constants and I
constant inventory rows, the C command table is the action-level proof. Dead
constant aliases stay excluded even when their numeric value equals a live
command. For TR entries, the corresponding start_notify/write/teardown path is
mapped; dead/server/read helpers and destructive reset advertising stay excluded.

| ID | Discovery | Disposition | Evidence |
|---|---|---|---|
| P-selectors-0 | selectors-0 | IMPLEMENTED | `analysis.json#/protocols/0/selectors/0` |
| P-selectors-1 | selectors-1 | IMPLEMENTED | `analysis.json#/protocols/0/selectors/1` |
| P-selectors-2 | selectors-2 | IMPLEMENTED | `analysis.json#/protocols/0/selectors/2` |
| P-selectors-3 | selectors-3 | IMPLEMENTED | `analysis.json#/protocols/0/selectors/3` |
| P-selectors-4 | selectors-4 | IMPLEMENTED | `analysis.json#/protocols/0/selectors/4` |
| P-selectors-5 | selectors-5 | IMPLEMENTED | `analysis.json#/protocols/0/selectors/5` |
| P-selectors-6 | selectors-6 | IMPLEMENTED | `analysis.json#/protocols/0/selectors/6` |
| P-selectors-7 | selectors-7 | IMPLEMENTED | `analysis.json#/protocols/0/selectors/7` |
| P-discovery_rules-scan | discovery_rules-scan | IMPLEMENTED | `analysis.json#/protocols/0/discovery_rules/scan` |
| P-discovery_rules-manufacturer_gate | discovery_rules-manufacturer_gate | IMPLEMENTED | `analysis.json#/protocols/0/discovery_rules/manufacturer_gate` |
| P-discovery_rules-inventory_common | discovery_rules-inventory_common | IMPLEMENTED | `analysis.json#/protocols/0/discovery_rules/inventory_common` |
| P-discovery_rules-mode_01 | discovery_rules-mode_01 | IMPLEMENTED | `analysis.json#/protocols/0/discovery_rules/mode_01` |
| P-discovery_rules-mode_09 | discovery_rules-mode_09 | IMPLEMENTED | `analysis.json#/protocols/0/discovery_rules/mode_09` |
| P-discovery_rules-mode_02 | discovery_rules-mode_02 | IMPLEMENTED | `analysis.json#/protocols/0/discovery_rules/mode_02` |
| P-discovery_rules-actuator_filter | discovery_rules-actuator_filter | IMPLEMENTED | `analysis.json#/protocols/0/discovery_rules/actuator_filter` |
| P-discovery_rules-auto_connect | discovery_rules-auto_connect | EXCLUDED | `analysis.json#/protocols/0/discovery_rules/auto_connect` |
| P-discovery_rules-precedence | discovery_rules-precedence | IMPLEMENTED | `analysis.json#/protocols/0/discovery_rules/precedence` |
| P-discovery_rules-evidence | discovery_rules-evidence | IMPLEMENTED | `analysis.json#/protocols/0/discovery_rules/evidence` |
| P-discovery_rules-setup_selector | discovery_rules-setup_selector | IMPLEMENTED | `analysis.json#/protocols/0/discovery_rules/setup_selector` |
| P-gatt-service | gatt-service | IMPLEMENTED | `analysis.json#/protocols/0/gatt/service` |
| P-gatt-write | gatt-write | IMPLEMENTED | `analysis.json#/protocols/0/gatt/write` |
| P-gatt-notify | gatt-notify | IMPLEMENTED | `analysis.json#/protocols/0/gatt/notify` |
| P-gatt-descriptor | gatt-descriptor | IMPLEMENTED | `analysis.json#/protocols/0/gatt/descriptor` |
| P-gatt-write_type | gatt-write_type | IMPLEMENTED | `analysis.json#/protocols/0/gatt/write_type` |
| P-gatt-properties | gatt-properties | IMPLEMENTED | `analysis.json#/protocols/0/gatt/properties` |
| P-gatt-read | gatt-read | EXCLUDED | `analysis.json#/protocols/0/gatt/read` |
| P-gatt-mtu_priority_bond | gatt-mtu_priority_bond | EXCLUDED | `analysis.json#/protocols/0/gatt/mtu_priority_bond` |
| P-gatt-connections | gatt-connections | IMPLEMENTED | `analysis.json#/protocols/0/gatt/connections` |
| P-gatt-evidence | gatt-evidence | IMPLEMENTED | `analysis.json#/protocols/0/gatt/evidence` |
| P-session_sequence-0 | session_sequence-0 | IMPLEMENTED | `analysis.json#/protocols/0/session_sequence/0` |
| P-session_sequence-1 | session_sequence-1 | IMPLEMENTED | `analysis.json#/protocols/0/session_sequence/1` |
| P-session_sequence-2 | session_sequence-2 | IMPLEMENTED | `analysis.json#/protocols/0/session_sequence/2` |
| P-session_sequence-3 | session_sequence-3 | IMPLEMENTED | `analysis.json#/protocols/0/session_sequence/3` |
| P-session_sequence-4 | session_sequence-4 | IMPLEMENTED | `analysis.json#/protocols/0/session_sequence/4` |
| P-session_sequence-5 | session_sequence-5 | IMPLEMENTED | `analysis.json#/protocols/0/session_sequence/5` |
| P-session_sequence-6 | session_sequence-6 | IMPLEMENTED | `analysis.json#/protocols/0/session_sequence/6` |
| P-session_sequence-7 | session_sequence-7 | IMPLEMENTED | `analysis.json#/protocols/0/session_sequence/7` |
| P-session_sequence-8 | session_sequence-8 | IMPLEMENTED | `analysis.json#/protocols/0/session_sequence/8` |
| P-session_sequence-9 | session_sequence-9 | IMPLEMENTED | `analysis.json#/protocols/0/session_sequence/9` |
| P-session_sequence-10 | session_sequence-10 | IMPLEMENTED | `analysis.json#/protocols/0/session_sequence/10` |
| P-session_sequence-11 | session_sequence-11 | IMPLEMENTED | `analysis.json#/protocols/0/session_sequence/11` |
| P-session_sequence-12 | session_sequence-12 | IMPLEMENTED | `analysis.json#/protocols/0/session_sequence/12` |
| P-packet_format-normal_frame | packet_format-normal_frame | IMPLEMENTED | `analysis.json#/protocols/0/packet_format/normal_frame` |
| P-packet_format-payload_state | packet_format-payload_state | IMPLEMENTED | `analysis.json#/protocols/0/packet_format/payload_state` |
| P-packet_format-address | packet_format-address | IMPLEMENTED | `analysis.json#/protocols/0/packet_format/address` |
| P-packet_format-encoder | packet_format-encoder | IMPLEMENTED | `analysis.json#/protocols/0/packet_format/encoder` |
| P-packet_format-auth | packet_format-auth | IMPLEMENTED | `analysis.json#/protocols/0/packet_format/auth` |
| P-packet_format-enroll | packet_format-enroll | IMPLEMENTED | `analysis.json#/protocols/0/packet_format/enroll` |
| P-packet_format-ping | packet_format-ping | IMPLEMENTED | `analysis.json#/protocols/0/packet_format/ping` |
| P-packet_format-reset_ad | packet_format-reset_ad | IMPLEMENTED | `analysis.json#/protocols/0/packet_format/reset_ad` |
| P-packet_format-checksum_encryption | packet_format-checksum_encryption | IMPLEMENTED | `analysis.json#/protocols/0/packet_format/checksum_encryption` |
| P-packet_format-pseudocode | packet_format-pseudocode | IMPLEMENTED | `analysis.json#/protocols/0/packet_format/pseudocode` |
| P-packet_format-evidence | packet_format-evidence | IMPLEMENTED | `analysis.json#/protocols/0/packet_format/evidence` |
| P-packet_format-room_identity | packet_format-room_identity | IMPLEMENTED | `analysis.json#/protocols/0/packet_format/room_identity` |
| P-notifications-0 | notifications-0 | IMPLEMENTED | `analysis.json#/protocols/0/notifications/0` |
| P-notifications-1 | notifications-1 | IMPLEMENTED | `analysis.json#/protocols/0/notifications/1` |
| P-notifications-2 | notifications-2 | IMPLEMENTED | `analysis.json#/protocols/0/notifications/2` |
| P-notifications-3 | notifications-3 | IMPLEMENTED | `analysis.json#/protocols/0/notifications/3` |
| P-notifications-4 | notifications-4 | IMPLEMENTED | `analysis.json#/protocols/0/notifications/4` |
| P-notifications-5 | notifications-5 | IMPLEMENTED | `analysis.json#/protocols/0/notifications/5` |
| P-notifications-6 | notifications-6 | EXCLUDED | `analysis.json#/protocols/0/notifications/6` |
| P-notifications-7 | notifications-7 | EXCLUDED | `analysis.json#/protocols/0/notifications/7` |
| P-notifications-8 | notifications-8 | EXCLUDED | `analysis.json#/protocols/0/notifications/8` |
| P-notifications-9 | notifications-9 | EXCLUDED | `analysis.json#/protocols/0/notifications/9` |
| P-notifications-10 | notifications-10 | IMPLEMENTED | `analysis.json#/protocols/0/notifications/10` |
| P-capabilities-movement | capabilities-movement | IMPLEMENTED | `analysis.json#/protocols/0/capabilities/movement` |
| P-capabilities-presets | capabilities-presets | IMPLEMENTED | `analysis.json#/protocols/0/capabilities/presets` |
| P-capabilities-memory | capabilities-memory | IMPLEMENTED | `analysis.json#/protocols/0/capabilities/memory` |
| P-capabilities-massage | capabilities-massage | IMPLEMENTED | `analysis.json#/protocols/0/capabilities/massage` |
| P-capabilities-light | capabilities-light | IMPLEMENTED | `analysis.json#/protocols/0/capabilities/light` |
| P-capabilities-position_feedback | capabilities-position_feedback | IMPLEMENTED | `analysis.json#/protocols/0/capabilities/position_feedback` |
| P-capabilities-other_absences | capabilities-other_absences | EXCLUDED | `analysis.json#/protocols/0/capabilities/other_absences` |
| P-capabilities-model_selection | capabilities-model_selection | IMPLEMENTED | `analysis.json#/protocols/0/capabilities/model_selection` |
| P-capabilities-side_routing | capabilities-side_routing | IMPLEMENTED | `analysis.json#/protocols/0/capabilities/side_routing` |
| P-capabilities-multi_product_rooms | capabilities-multi_product_rooms | IMPLEMENTED | `analysis.json#/protocols/0/capabilities/multi_product_rooms` |
| P-capabilities-themes | capabilities-themes | IMPLEMENTED | `analysis.json#/protocols/0/capabilities/themes` |
| P-capabilities-state | capabilities-state | IMPLEMENTED | `analysis.json#/protocols/0/capabilities/state` |
| P-capabilities-evidence | capabilities-evidence | IMPLEMENTED | `analysis.json#/protocols/0/capabilities/evidence` |
| P-capabilities-timer_routing_quirk | capabilities-timer_routing_quirk | IMPLEMENTED | `analysis.json#/protocols/0/capabilities/timer_routing_quirk` |
| P-model_mappings-0 | model_mappings-0 | IMPLEMENTED | `analysis.json#/protocols/0/model_mappings/0` |
| P-model_mappings-1 | model_mappings-1 | IMPLEMENTED | `analysis.json#/protocols/0/model_mappings/1` |
| P-model_mappings-2 | model_mappings-2 | IMPLEMENTED | `analysis.json#/protocols/0/model_mappings/2` |
| P-model_mappings-3 | model_mappings-3 | IMPLEMENTED | `analysis.json#/protocols/0/model_mappings/3` |
| P-model_mappings-4 | model_mappings-4 | IMPLEMENTED | `analysis.json#/protocols/0/model_mappings/4` |
| P-model_mappings-5 | model_mappings-5 | IMPLEMENTED | `analysis.json#/protocols/0/model_mappings/5` |
| P-model_mappings-6 | model_mappings-6 | IMPLEMENTED | `analysis.json#/protocols/0/model_mappings/6` |
| P-model_mappings-7 | model_mappings-7 | IMPLEMENTED | `analysis.json#/protocols/0/model_mappings/7` |
| P-timing-queue | timing-queue | EXCLUDED | `analysis.json#/protocols/0/timing/queue` |
| P-timing-movement | timing-movement | IMPLEMENTED | `analysis.json#/protocols/0/timing/movement` |
| P-timing-memory | timing-memory | IMPLEMENTED | `analysis.json#/protocols/0/timing/memory` |
| P-timing-ui_only | timing-ui_only | EXCLUDED | `analysis.json#/protocols/0/timing/ui_only` |
| P-timing-reconnect | timing-reconnect | EXCLUDED | `analysis.json#/protocols/0/timing/reconnect` |
| P-timing-session | timing-session | IMPLEMENTED | `analysis.json#/protocols/0/timing/session` |
| P-timing-write_failure | timing-write_failure | EXCLUDED | `analysis.json#/protocols/0/timing/write_failure` |
| P-release_behavior-normal | release_behavior-normal | IMPLEMENTED | `analysis.json#/protocols/0/release_behavior/normal` |
| P-release_behavior-failure | release_behavior-failure | IMPLEMENTED | `analysis.json#/protocols/0/release_behavior/failure` |
| P-release_behavior-flat | release_behavior-flat | IMPLEMENTED | `analysis.json#/protocols/0/release_behavior/flat` |
| P-release_behavior-hardware | release_behavior-hardware | IMPLEMENTED | `analysis.json#/protocols/0/release_behavior/hardware` |
| K-P1-client | protocol: P1-client | IMPLEMENTED | `analysis.json#/candidate_ledger/0` |
| K-server | protocol: server | EXCLUDED | `analysis.json#/candidate_ledger/1` |
| K-metadata | parser: metadata | EXCLUDED | `analysis.json#/candidate_ledger/2` |
| K-library-ad-modes | alternate builders: library-ad-modes | EXCLUDED | `analysis.json#/candidate_ledger/3` |
| K-library-packet-helpers | alternate builders: library-packet-helpers | EXCLUDED | `analysis.json#/candidate_ledger/4` |
| K-alternate-discovery | discovery: alternate-discovery | EXCLUDED | `analysis.json#/candidate_ledger/5` |
| K-local-schedules | background action: local-schedules | EXCLUDED | `analysis.json#/candidate_ledger/6` |
| K-theme-qr | cloud/theme/configuration: theme-qr | EXCLUDED | `analysis.json#/candidate_ledger/7` |
| K-native-runtime | native: native-runtime | EXCLUDED | `analysis.json#/candidate_ledger/8` |
| K-local-label-config | configuration: local-label-config | IMPLEMENTED | `analysis.json#/candidate_ledger/9` |
| K-CONST-SEAT_1_HEAD_UP | command candidate: CONST-SEAT_1_HEAD_UP | IMPLEMENTED | `analysis.json#/candidate_ledger/10` |
| K-CONST-SEAT_1_HEAD_DOWN | command candidate: CONST-SEAT_1_HEAD_DOWN | IMPLEMENTED | `analysis.json#/candidate_ledger/11` |
| K-CONST-SEAT_1_HEAD_STOP | command candidate: CONST-SEAT_1_HEAD_STOP | IMPLEMENTED | `analysis.json#/candidate_ledger/12` |
| K-CONST-SEAT_1_FOOT_UP | command candidate: CONST-SEAT_1_FOOT_UP | IMPLEMENTED | `analysis.json#/candidate_ledger/13` |
| K-CONST-SEAT_1_FOOT_DOWN | command candidate: CONST-SEAT_1_FOOT_DOWN | IMPLEMENTED | `analysis.json#/candidate_ledger/14` |
| K-CONST-SEAT_1_FOOT_STOP | command candidate: CONST-SEAT_1_FOOT_STOP | IMPLEMENTED | `analysis.json#/candidate_ledger/15` |
| K-CONST-SEAT_1_ALL_UP | command candidate: CONST-SEAT_1_ALL_UP | IMPLEMENTED | `analysis.json#/candidate_ledger/16` |
| K-CONST-SEAT_1_ALL_DOWN | command candidate: CONST-SEAT_1_ALL_DOWN | IMPLEMENTED | `analysis.json#/candidate_ledger/17` |
| K-CONST-SEAT_1_ALL_STOP | command candidate: CONST-SEAT_1_ALL_STOP | IMPLEMENTED | `analysis.json#/candidate_ledger/18` |
| K-CONST-SEAT_2_HEAD_UP | command candidate: CONST-SEAT_2_HEAD_UP | IMPLEMENTED | `analysis.json#/candidate_ledger/19` |
| K-CONST-SEAT_2_HEAD_DOWN | command candidate: CONST-SEAT_2_HEAD_DOWN | IMPLEMENTED | `analysis.json#/candidate_ledger/20` |
| K-CONST-SEAT_2_HEAD_STOP | command candidate: CONST-SEAT_2_HEAD_STOP | IMPLEMENTED | `analysis.json#/candidate_ledger/21` |
| K-CONST-SEAT_2_FOOT_UP | command candidate: CONST-SEAT_2_FOOT_UP | IMPLEMENTED | `analysis.json#/candidate_ledger/22` |
| K-CONST-SEAT_2_FOOT_DOWN | command candidate: CONST-SEAT_2_FOOT_DOWN | IMPLEMENTED | `analysis.json#/candidate_ledger/23` |
| K-CONST-SEAT_2_FOOT_STOP | command candidate: CONST-SEAT_2_FOOT_STOP | IMPLEMENTED | `analysis.json#/candidate_ledger/24` |
| K-CONST-SEAT_2_ALL_UP | command candidate: CONST-SEAT_2_ALL_UP | IMPLEMENTED | `analysis.json#/candidate_ledger/25` |
| K-CONST-SEAT_2_ALL_DOWN | command candidate: CONST-SEAT_2_ALL_DOWN | IMPLEMENTED | `analysis.json#/candidate_ledger/26` |
| K-CONST-SEAT_2_ALL_STOP | command candidate: CONST-SEAT_2_ALL_STOP | IMPLEMENTED | `analysis.json#/candidate_ledger/27` |
| K-CONST-SEAT_1_2_HEAD_UP | command candidate: CONST-SEAT_1_2_HEAD_UP | IMPLEMENTED | `analysis.json#/candidate_ledger/28` |
| K-CONST-SEAT_1_2_HEAD_DOWN | command candidate: CONST-SEAT_1_2_HEAD_DOWN | IMPLEMENTED | `analysis.json#/candidate_ledger/29` |
| K-CONST-SEAT_1_2_HEAD_STOP | command candidate: CONST-SEAT_1_2_HEAD_STOP | IMPLEMENTED | `analysis.json#/candidate_ledger/30` |
| K-CONST-SEAT_1_2_FOOT_UP | command candidate: CONST-SEAT_1_2_FOOT_UP | IMPLEMENTED | `analysis.json#/candidate_ledger/31` |
| K-CONST-SEAT_1_2_FOOT_DOWN | command candidate: CONST-SEAT_1_2_FOOT_DOWN | IMPLEMENTED | `analysis.json#/candidate_ledger/32` |
| K-CONST-SEAT_1_2_FOOT_STOP | command candidate: CONST-SEAT_1_2_FOOT_STOP | IMPLEMENTED | `analysis.json#/candidate_ledger/33` |
| K-CONST-SEAT_1_2_ALL_UP | command candidate: CONST-SEAT_1_2_ALL_UP | IMPLEMENTED | `analysis.json#/candidate_ledger/34` |
| K-CONST-SEAT_1_2_ALL_DOWN | command candidate: CONST-SEAT_1_2_ALL_DOWN | IMPLEMENTED | `analysis.json#/candidate_ledger/35` |
| K-CONST-SEAT_1_2_ALL_STOP | command candidate: CONST-SEAT_1_2_ALL_STOP | IMPLEMENTED | `analysis.json#/candidate_ledger/36` |
| K-CONST-SEAT_1_ALL_MOTOR_STOP | command candidate: CONST-SEAT_1_ALL_MOTOR_STOP | IMPLEMENTED | `analysis.json#/candidate_ledger/37` |
| K-CONST-SEAT_2_ALL_MOTOR_STOP | command candidate: CONST-SEAT_2_ALL_MOTOR_STOP | IMPLEMENTED | `analysis.json#/candidate_ledger/38` |
| K-CONST-SEAT_1_2_ALL_MOTOR_STOP | command candidate: CONST-SEAT_1_2_ALL_MOTOR_STOP | IMPLEMENTED | `analysis.json#/candidate_ledger/39` |
| K-CONST-SEAT_1_ALL_MOTOR_RESET_1 | command candidate: CONST-SEAT_1_ALL_MOTOR_RESET_1 | EXCLUDED | `analysis.json#/candidate_ledger/40` |
| K-CONST-SEAT_2_ALL_MOTOR_RESET_1 | command candidate: CONST-SEAT_2_ALL_MOTOR_RESET_1 | EXCLUDED | `analysis.json#/candidate_ledger/41` |
| K-CONST-SEAT_1_2_ALL_MOTOR_RESET_1 | command candidate: CONST-SEAT_1_2_ALL_MOTOR_RESET_1 | EXCLUDED | `analysis.json#/candidate_ledger/42` |
| K-CONST-SEAT_1_ALL_MOTOR_RESET_2 | command candidate: CONST-SEAT_1_ALL_MOTOR_RESET_2 | EXCLUDED | `analysis.json#/candidate_ledger/43` |
| K-CONST-SEAT_2_ALL_MOTOR_RESET_2 | command candidate: CONST-SEAT_2_ALL_MOTOR_RESET_2 | EXCLUDED | `analysis.json#/candidate_ledger/44` |
| K-CONST-SEAT_1_2_ALL_MOTOR_RESET_2 | command candidate: CONST-SEAT_1_2_ALL_MOTOR_RESET_2 | EXCLUDED | `analysis.json#/candidate_ledger/45` |
| K-CONST-SEAT_1_MEMORY_POSITION_A | command candidate: CONST-SEAT_1_MEMORY_POSITION_A | IMPLEMENTED | `analysis.json#/candidate_ledger/46` |
| K-CONST-SEAT_1_MEMORY_POSITION_B | command candidate: CONST-SEAT_1_MEMORY_POSITION_B | IMPLEMENTED | `analysis.json#/candidate_ledger/47` |
| K-CONST-SEAT_1_MEMORY_POSITION_C | command candidate: CONST-SEAT_1_MEMORY_POSITION_C | IMPLEMENTED | `analysis.json#/candidate_ledger/48` |
| K-CONST-SEAT_1_MEMORY_POSITION_D | command candidate: CONST-SEAT_1_MEMORY_POSITION_D | EXCLUDED | `analysis.json#/candidate_ledger/49` |
| K-CONST-SEAT_1_RUN_TO_POSITION_A | command candidate: CONST-SEAT_1_RUN_TO_POSITION_A | IMPLEMENTED | `analysis.json#/candidate_ledger/50` |
| K-CONST-SEAT_1_RUN_TO_POSITION_B | command candidate: CONST-SEAT_1_RUN_TO_POSITION_B | IMPLEMENTED | `analysis.json#/candidate_ledger/51` |
| K-CONST-SEAT_1_RUN_TO_POSITION_C | command candidate: CONST-SEAT_1_RUN_TO_POSITION_C | IMPLEMENTED | `analysis.json#/candidate_ledger/52` |
| K-CONST-SEAT_1_RUN_TO_POSITION_D | command candidate: CONST-SEAT_1_RUN_TO_POSITION_D | EXCLUDED | `analysis.json#/candidate_ledger/53` |
| K-CONST-SEAT_2_MEMORY_POSITION_A | command candidate: CONST-SEAT_2_MEMORY_POSITION_A | IMPLEMENTED | `analysis.json#/candidate_ledger/54` |
| K-CONST-SEAT_2_MEMORY_POSITION_B | command candidate: CONST-SEAT_2_MEMORY_POSITION_B | IMPLEMENTED | `analysis.json#/candidate_ledger/55` |
| K-CONST-SEAT_2_MEMORY_POSITION_C | command candidate: CONST-SEAT_2_MEMORY_POSITION_C | IMPLEMENTED | `analysis.json#/candidate_ledger/56` |
| K-CONST-SEAT_2_MEMORY_POSITION_D | command candidate: CONST-SEAT_2_MEMORY_POSITION_D | EXCLUDED | `analysis.json#/candidate_ledger/57` |
| K-CONST-SEAT_2_RUN_TO_POSITION_A | command candidate: CONST-SEAT_2_RUN_TO_POSITION_A | IMPLEMENTED | `analysis.json#/candidate_ledger/58` |
| K-CONST-SEAT_2_RUN_TO_POSITION_B | command candidate: CONST-SEAT_2_RUN_TO_POSITION_B | IMPLEMENTED | `analysis.json#/candidate_ledger/59` |
| K-CONST-SEAT_2_RUN_TO_POSITION_C | command candidate: CONST-SEAT_2_RUN_TO_POSITION_C | IMPLEMENTED | `analysis.json#/candidate_ledger/60` |
| K-CONST-SEAT_2_RUN_TO_POSITION_D | command candidate: CONST-SEAT_2_RUN_TO_POSITION_D | EXCLUDED | `analysis.json#/candidate_ledger/61` |
| K-CONST-SEAT_1_2_MEMORY_POSITION_A | command candidate: CONST-SEAT_1_2_MEMORY_POSITION_A | IMPLEMENTED | `analysis.json#/candidate_ledger/62` |
| K-CONST-SEAT_1_2_MEMORY_POSITION_B | command candidate: CONST-SEAT_1_2_MEMORY_POSITION_B | IMPLEMENTED | `analysis.json#/candidate_ledger/63` |
| K-CONST-SEAT_1_2_MEMORY_POSITION_C | command candidate: CONST-SEAT_1_2_MEMORY_POSITION_C | IMPLEMENTED | `analysis.json#/candidate_ledger/64` |
| K-CONST-SEAT_1_2_MEMORY_POSITION_D | command candidate: CONST-SEAT_1_2_MEMORY_POSITION_D | EXCLUDED | `analysis.json#/candidate_ledger/65` |
| K-CONST-SEAT_1_2_RUN_TO_POSITION_A | command candidate: CONST-SEAT_1_2_RUN_TO_POSITION_A | IMPLEMENTED | `analysis.json#/candidate_ledger/66` |
| K-CONST-SEAT_1_2_RUN_TO_POSITION_B | command candidate: CONST-SEAT_1_2_RUN_TO_POSITION_B | IMPLEMENTED | `analysis.json#/candidate_ledger/67` |
| K-CONST-SEAT_1_2_RUN_TO_POSITION_C | command candidate: CONST-SEAT_1_2_RUN_TO_POSITION_C | IMPLEMENTED | `analysis.json#/candidate_ledger/68` |
| K-CONST-SEAT_1_2_RUN_TO_POSITION_D | command candidate: CONST-SEAT_1_2_RUN_TO_POSITION_D | EXCLUDED | `analysis.json#/candidate_ledger/69` |
| K-CONST-SEAT_1_LOCK | command candidate: CONST-SEAT_1_LOCK | EXCLUDED | `analysis.json#/candidate_ledger/70` |
| K-CONST-SEAT_2_LOCK | command candidate: CONST-SEAT_2_LOCK | EXCLUDED | `analysis.json#/candidate_ledger/71` |
| K-CONST-SEAT_1_2_LOCK | command candidate: CONST-SEAT_1_2_LOCK | EXCLUDED | `analysis.json#/candidate_ledger/72` |
| K-CONST-SEAT_1_UNLOCK | command candidate: CONST-SEAT_1_UNLOCK | EXCLUDED | `analysis.json#/candidate_ledger/73` |
| K-CONST-SEAT_2_UNLOCK | command candidate: CONST-SEAT_2_UNLOCK | EXCLUDED | `analysis.json#/candidate_ledger/74` |
| K-CONST-SEAT_1_2_UNLOCK | command candidate: CONST-SEAT_1_2_UNLOCK | EXCLUDED | `analysis.json#/candidate_ledger/75` |
| K-CONST-ADD_DEVICE_SUCCESS | command candidate: CONST-ADD_DEVICE_SUCCESS | IMPLEMENTED | `analysis.json#/candidate_ledger/76` |
| K-CONST-SEAT_1_MASSAGE_START | command candidate: CONST-SEAT_1_MASSAGE_START | IMPLEMENTED | `analysis.json#/candidate_ledger/77` |
| K-CONST-SEAT_1_MASSAGE_STOP | command candidate: CONST-SEAT_1_MASSAGE_STOP | IMPLEMENTED | `analysis.json#/candidate_ledger/78` |
| K-CONST-SEAT_2_MASSAGE_START | command candidate: CONST-SEAT_2_MASSAGE_START | IMPLEMENTED | `analysis.json#/candidate_ledger/79` |
| K-CONST-SEAT_2_MASSAGE_STOP | command candidate: CONST-SEAT_2_MASSAGE_STOP | IMPLEMENTED | `analysis.json#/candidate_ledger/80` |
| K-CONST-SEAT_1_2_MASSAGE_START | command candidate: CONST-SEAT_1_2_MASSAGE_START | IMPLEMENTED | `analysis.json#/candidate_ledger/81` |
| K-CONST-SEAT_1_2_MASSAGE_STOP | command candidate: CONST-SEAT_1_2_MASSAGE_STOP | IMPLEMENTED | `analysis.json#/candidate_ledger/82` |
| K-CONST-SEAT_1_HEAD_MASSAGE_SETTING | command candidate: CONST-SEAT_1_HEAD_MASSAGE_SETTING | IMPLEMENTED | `analysis.json#/candidate_ledger/83` |
| K-CONST-SEAT_2_HEAD_MASSAGE_SETTING | command candidate: CONST-SEAT_2_HEAD_MASSAGE_SETTING | IMPLEMENTED | `analysis.json#/candidate_ledger/84` |
| K-CONST-SEAT_1_LEG_MASSAGE_SETTING | command candidate: CONST-SEAT_1_LEG_MASSAGE_SETTING | IMPLEMENTED | `analysis.json#/candidate_ledger/85` |
| K-CONST-SEAT_2_LEG_MASSAGE_SETTING | command candidate: CONST-SEAT_2_LEG_MASSAGE_SETTING | IMPLEMENTED | `analysis.json#/candidate_ledger/86` |
| K-CONST-SEAT_1_2_HEAD_MASSAGE_SETTING | command candidate: CONST-SEAT_1_2_HEAD_MASSAGE_SETTING | IMPLEMENTED | `analysis.json#/candidate_ledger/87` |
| K-CONST-SEAT_1_2_LEG_MASSAGE_SETTING | command candidate: CONST-SEAT_1_2_LEG_MASSAGE_SETTING | IMPLEMENTED | `analysis.json#/candidate_ledger/88` |
| K-CONST-SEAT_1_MASSAGE_15 | command candidate: CONST-SEAT_1_MASSAGE_15 | IMPLEMENTED | `analysis.json#/candidate_ledger/89` |
| K-CONST-SEAT_1_MASSAGE_30 | command candidate: CONST-SEAT_1_MASSAGE_30 | IMPLEMENTED | `analysis.json#/candidate_ledger/90` |
| K-CONST-SEAT_1_MASSAGE_45 | command candidate: CONST-SEAT_1_MASSAGE_45 | IMPLEMENTED | `analysis.json#/candidate_ledger/91` |
| K-CONST-SEAT_2_MASSAGE_15 | command candidate: CONST-SEAT_2_MASSAGE_15 | IMPLEMENTED | `analysis.json#/candidate_ledger/92` |
| K-CONST-SEAT_2_MASSAGE_30 | command candidate: CONST-SEAT_2_MASSAGE_30 | IMPLEMENTED | `analysis.json#/candidate_ledger/93` |
| K-CONST-SEAT_2_MASSAGE_45 | command candidate: CONST-SEAT_2_MASSAGE_45 | IMPLEMENTED | `analysis.json#/candidate_ledger/94` |
| K-CONST-SEAT_1_2_MASSAGE_15 | command candidate: CONST-SEAT_1_2_MASSAGE_15 | IMPLEMENTED | `analysis.json#/candidate_ledger/95` |
| K-CONST-SEAT_1_2_MASSAGE_30 | command candidate: CONST-SEAT_1_2_MASSAGE_30 | IMPLEMENTED | `analysis.json#/candidate_ledger/96` |
| K-CONST-SEAT_1_2_MASSAGE_45 | command candidate: CONST-SEAT_1_2_MASSAGE_45 | IMPLEMENTED | `analysis.json#/candidate_ledger/97` |
| K-CONST-SEAT_1_BED_LIGHT_ON | command candidate: CONST-SEAT_1_BED_LIGHT_ON | IMPLEMENTED | `analysis.json#/candidate_ledger/98` |
| K-CONST-SEAT_1_BED_LIGHT_OFF | command candidate: CONST-SEAT_1_BED_LIGHT_OFF | IMPLEMENTED | `analysis.json#/candidate_ledger/99` |
| K-CONST-SEAT_2_BED_LIGHT_ON | command candidate: CONST-SEAT_2_BED_LIGHT_ON | IMPLEMENTED | `analysis.json#/candidate_ledger/100` |
| K-CONST-SEAT_2_BED_LIGHT_OFF | command candidate: CONST-SEAT_2_BED_LIGHT_OFF | IMPLEMENTED | `analysis.json#/candidate_ledger/101` |
| K-CONST-SEAT_1_2_BED_LIGHT_ON | command candidate: CONST-SEAT_1_2_BED_LIGHT_ON | IMPLEMENTED | `analysis.json#/candidate_ledger/102` |
| K-CONST-SEAT_1_2_BED_LIGHT_OFF | command candidate: CONST-SEAT_1_2_BED_LIGHT_OFF | IMPLEMENTED | `analysis.json#/candidate_ledger/103` |
| K-CONST-SEAT_1_ZG | command candidate: CONST-SEAT_1_ZG | IMPLEMENTED | `analysis.json#/candidate_ledger/104` |
| K-CONST-SEAT_2_ZG | command candidate: CONST-SEAT_2_ZG | IMPLEMENTED | `analysis.json#/candidate_ledger/105` |
| K-CONST-SEAT_1_2_ZG | command candidate: CONST-SEAT_1_2_ZG | IMPLEMENTED | `analysis.json#/candidate_ledger/106` |
| K-CONST-SEAT_1_ANTI_SNORE | command candidate: CONST-SEAT_1_ANTI_SNORE | IMPLEMENTED | `analysis.json#/candidate_ledger/107` |
| K-CONST-SEAT_2_ANTI_SNORE | command candidate: CONST-SEAT_2_ANTI_SNORE | IMPLEMENTED | `analysis.json#/candidate_ledger/108` |
| K-CONST-SEAT_1_2_ANTI_SNORE | command candidate: CONST-SEAT_1_2_ANTI_SNORE | IMPLEMENTED | `analysis.json#/candidate_ledger/109` |
| K-CONST-SEAT_1_PLAN_BED | command candidate: CONST-SEAT_1_PLAN_BED | EXCLUDED | `analysis.json#/candidate_ledger/110` |
| K-CONST-SEAT_2_PLAN_BED | command candidate: CONST-SEAT_2_PLAN_BED | EXCLUDED | `analysis.json#/candidate_ledger/111` |
| K-CONST-SEAT_1_2_PLAN_BED | command candidate: CONST-SEAT_1_2_PLAN_BED | EXCLUDED | `analysis.json#/candidate_ledger/112` |
| K-CONST-SEAT_1_MASSAGE_MODE1 | command candidate: CONST-SEAT_1_MASSAGE_MODE1 | IMPLEMENTED | `analysis.json#/candidate_ledger/113` |
| K-CONST-SEAT_2_MASSAGE_MODE1 | command candidate: CONST-SEAT_2_MASSAGE_MODE1 | IMPLEMENTED | `analysis.json#/candidate_ledger/114` |
| K-CONST-SEAT_1_2_MASSAGE_MODE1 | command candidate: CONST-SEAT_1_2_MASSAGE_MODE1 | IMPLEMENTED | `analysis.json#/candidate_ledger/115` |
| K-CONST-SEAT_1_MASSAGE_MODE2 | command candidate: CONST-SEAT_1_MASSAGE_MODE2 | IMPLEMENTED | `analysis.json#/candidate_ledger/116` |
| K-CONST-SEAT_2_MASSAGE_MODE2 | command candidate: CONST-SEAT_2_MASSAGE_MODE2 | IMPLEMENTED | `analysis.json#/candidate_ledger/117` |
| K-CONST-SEAT_1_2_MASSAGE_MODE2 | command candidate: CONST-SEAT_1_2_MASSAGE_MODE2 | IMPLEMENTED | `analysis.json#/candidate_ledger/118` |
| K-CONST-SEAT_1_MASSAGE_MODE3 | command candidate: CONST-SEAT_1_MASSAGE_MODE3 | IMPLEMENTED | `analysis.json#/candidate_ledger/119` |
| K-CONST-SEAT_2_MASSAGE_MODE3 | command candidate: CONST-SEAT_2_MASSAGE_MODE3 | IMPLEMENTED | `analysis.json#/candidate_ledger/120` |
| K-CONST-SEAT_1_2_MASSAGE_MODE3 | command candidate: CONST-SEAT_1_2_MASSAGE_MODE3 | IMPLEMENTED | `analysis.json#/candidate_ledger/121` |
| K-CONST-SEAT_1_MASSAGE_MODE_CACEL | command candidate: CONST-SEAT_1_MASSAGE_MODE_CACEL | IMPLEMENTED | `analysis.json#/candidate_ledger/122` |
| K-CONST-SEAT_2_MASSAGE_MODE_CACEL | command candidate: CONST-SEAT_2_MASSAGE_MODE_CACEL | IMPLEMENTED | `analysis.json#/candidate_ledger/123` |
| K-CONST-SEAT_1_2_MASSAGE_MODE_CACEL | command candidate: CONST-SEAT_1_2_MASSAGE_MODE_CACEL | IMPLEMENTED | `analysis.json#/candidate_ledger/124` |
| K-CONST-SEAT_1_TIME_CACEL | command candidate: CONST-SEAT_1_TIME_CACEL | IMPLEMENTED | `analysis.json#/candidate_ledger/125` |
| K-CONST-SEAT_2_TIME_CACEL | command candidate: CONST-SEAT_2_TIME_CACEL | IMPLEMENTED | `analysis.json#/candidate_ledger/126` |
| K-CONST-SEAT_1_2_TIME_CACEL | command candidate: CONST-SEAT_1_2_TIME_CACEL | IMPLEMENTED | `analysis.json#/candidate_ledger/127` |
| K-CONST-SEAT_1_BACK_UP | command candidate: CONST-SEAT_1_BACK_UP | IMPLEMENTED | `analysis.json#/candidate_ledger/128` |
| K-CONST-SEAT_1_BACK_DOWN | command candidate: CONST-SEAT_1_BACK_DOWN | IMPLEMENTED | `analysis.json#/candidate_ledger/129` |
| K-CONST-SEAT_1_BACK_STOP | command candidate: CONST-SEAT_1_BACK_STOP | IMPLEMENTED | `analysis.json#/candidate_ledger/130` |
| K-CONST-SEAT_2_BACK_UP | command candidate: CONST-SEAT_2_BACK_UP | EXCLUDED | `analysis.json#/candidate_ledger/131` |
| K-CONST-SEAT_2_BACK_DOWN | command candidate: CONST-SEAT_2_BACK_DOWN | EXCLUDED | `analysis.json#/candidate_ledger/132` |
| K-CONST-SEAT_2_BACK_STOP | command candidate: CONST-SEAT_2_BACK_STOP | EXCLUDED | `analysis.json#/candidate_ledger/133` |
| K-CONST-SEAT_1_2_BACK_UP | command candidate: CONST-SEAT_1_2_BACK_UP | EXCLUDED | `analysis.json#/candidate_ledger/134` |
| K-CONST-SEAT_1_2_BACK_DOWN | command candidate: CONST-SEAT_1_2_BACK_DOWN | EXCLUDED | `analysis.json#/candidate_ledger/135` |
| K-CONST-SEAT_1_2_BACK_STOP | command candidate: CONST-SEAT_1_2_BACK_STOP | EXCLUDED | `analysis.json#/candidate_ledger/136` |
| K-CONST-SEAT_1_WAIST_UP | command candidate: CONST-SEAT_1_WAIST_UP | IMPLEMENTED | `analysis.json#/candidate_ledger/137` |
| K-CONST-SEAT_1_WAIST_DOWN | command candidate: CONST-SEAT_1_WAIST_DOWN | IMPLEMENTED | `analysis.json#/candidate_ledger/138` |
| K-CONST-SEAT_1_WAIST_STOP | command candidate: CONST-SEAT_1_WAIST_STOP | IMPLEMENTED | `analysis.json#/candidate_ledger/139` |
| K-CONST-SEAT_2_WAIST_UP | command candidate: CONST-SEAT_2_WAIST_UP | EXCLUDED | `analysis.json#/candidate_ledger/140` |
| K-CONST-SEAT_2_WAIST_DOWN | command candidate: CONST-SEAT_2_WAIST_DOWN | EXCLUDED | `analysis.json#/candidate_ledger/141` |
| K-CONST-SEAT_2_WAIST_STOP | command candidate: CONST-SEAT_2_WAIST_STOP | EXCLUDED | `analysis.json#/candidate_ledger/142` |
| K-CONST-SEAT_1_2_WAIST_UP | command candidate: CONST-SEAT_1_2_WAIST_UP | EXCLUDED | `analysis.json#/candidate_ledger/143` |
| K-CONST-SEAT_1_2_WAIST_DOWN | command candidate: CONST-SEAT_1_2_WAIST_DOWN | EXCLUDED | `analysis.json#/candidate_ledger/144` |
| K-CONST-SEAT_1_2_WAIST_STOP | command candidate: CONST-SEAT_1_2_WAIST_STOP | EXCLUDED | `analysis.json#/candidate_ledger/145` |
| K-CONST-SEAT_1_NEW_ALL_UP | command candidate: CONST-SEAT_1_NEW_ALL_UP | IMPLEMENTED | `analysis.json#/candidate_ledger/146` |
| K-CONST-SEAT_1_NEW_ALL_DOWN | command candidate: CONST-SEAT_1_NEW_ALL_DOWN | IMPLEMENTED | `analysis.json#/candidate_ledger/147` |
| K-CONST-SEAT_1_NEW_ALL_STOP | command candidate: CONST-SEAT_1_NEW_ALL_STOP | IMPLEMENTED | `analysis.json#/candidate_ledger/148` |
| K-CONST-SEAT_2_NEW_ALL_UP | command candidate: CONST-SEAT_2_NEW_ALL_UP | EXCLUDED | `analysis.json#/candidate_ledger/149` |
| K-CONST-SEAT_2_NEW_ALL_DOWN | command candidate: CONST-SEAT_2_NEW_ALL_DOWN | EXCLUDED | `analysis.json#/candidate_ledger/150` |
| K-CONST-SEAT_2_NEW_ALL_STOP | command candidate: CONST-SEAT_2_NEW_ALL_STOP | EXCLUDED | `analysis.json#/candidate_ledger/151` |
| K-CONST-SEAT_1_2_NEW_ALL_UP | command candidate: CONST-SEAT_1_2_NEW_ALL_UP | EXCLUDED | `analysis.json#/candidate_ledger/152` |
| K-CONST-SEAT_1_2_NEW_ALL_DOWN | command candidate: CONST-SEAT_1_2_NEW_ALL_DOWN | EXCLUDED | `analysis.json#/candidate_ledger/153` |
| K-CONST-SEAT_1_2_NEW_ALL_STOP | command candidate: CONST-SEAT_1_2_NEW_ALL_STOP | EXCLUDED | `analysis.json#/candidate_ledger/154` |
| K-CONST-ALL_SOFA_UNLOCK | command candidate: CONST-ALL_SOFA_UNLOCK | EXCLUDED | `analysis.json#/candidate_ledger/155` |
| K-CONST-ALL_SOFA_LOCK | command candidate: CONST-ALL_SOFA_LOCK | EXCLUDED | `analysis.json#/candidate_ledger/156` |
| K-CONST-GET_LOCK_STATE | command candidate: CONST-GET_LOCK_STATE | EXCLUDED | `analysis.json#/candidate_ledger/157` |
| K-TR-01 | transport callsite: TR-01 | EXCLUDED | `analysis.json#/candidate_ledger/158` |
| K-TR-02 | transport callsite: TR-02 | EXCLUDED | `analysis.json#/candidate_ledger/159` |
| K-TR-03 | transport callsite: TR-03 | EXCLUDED | `analysis.json#/candidate_ledger/160` |
| K-TR-04 | transport callsite: TR-04 | IMPLEMENTED | `analysis.json#/candidate_ledger/161` |
| K-TR-05 | transport callsite: TR-05 | IMPLEMENTED | `analysis.json#/candidate_ledger/162` |
| K-TR-06 | transport callsite: TR-06 | IMPLEMENTED | `analysis.json#/candidate_ledger/163` |
| K-TR-07 | transport callsite: TR-07 | IMPLEMENTED | `analysis.json#/candidate_ledger/164` |
| K-TR-08 | transport callsite: TR-08 | IMPLEMENTED | `analysis.json#/candidate_ledger/165` |
| K-TR-09 | transport callsite: TR-09 | IMPLEMENTED | `analysis.json#/candidate_ledger/166` |
| K-TR-10 | transport callsite: TR-10 | IMPLEMENTED | `analysis.json#/candidate_ledger/167` |
| K-TR-11 | transport callsite: TR-11 | IMPLEMENTED | `analysis.json#/candidate_ledger/168` |
| K-TR-12 | transport callsite: TR-12 | IMPLEMENTED | `analysis.json#/candidate_ledger/169` |
| K-TR-13 | transport callsite: TR-13 | IMPLEMENTED | `analysis.json#/candidate_ledger/170` |
| K-TR-14 | transport callsite: TR-14 | IMPLEMENTED | `analysis.json#/candidate_ledger/171` |
| K-TR-15 | transport callsite: TR-15 | IMPLEMENTED | `analysis.json#/candidate_ledger/172` |
| K-TR-16 | transport callsite: TR-16 | EXCLUDED | `analysis.json#/candidate_ledger/173` |
| K-TR-17 | transport callsite: TR-17 | EXCLUDED | `analysis.json#/candidate_ledger/174` |
| K-TR-18 | transport callsite: TR-18 | EXCLUDED | `analysis.json#/candidate_ledger/175` |
| K-TR-19 | transport callsite: TR-19 | EXCLUDED | `analysis.json#/candidate_ledger/176` |
| K-TR-20 | transport callsite: TR-20 | EXCLUDED | `analysis.json#/candidate_ledger/177` |
| K-TR-21 | transport callsite: TR-21 | EXCLUDED | `analysis.json#/candidate_ledger/178` |
| K-TR-22 | transport callsite: TR-22 | EXCLUDED | `analysis.json#/candidate_ledger/179` |
| K-TR-23 | transport callsite: TR-23 | EXCLUDED | `analysis.json#/candidate_ledger/180` |
| K-TR-24 | transport callsite: TR-24 | EXCLUDED | `analysis.json#/candidate_ledger/181` |
| K-TR-25 | transport callsite: TR-25 | EXCLUDED | `analysis.json#/candidate_ledger/182` |
| K-TR-26 | transport callsite: TR-26 | IMPLEMENTED | `analysis.json#/candidate_ledger/183` |
| K-TR-27 | transport callsite: TR-27 | IMPLEMENTED | `analysis.json#/candidate_ledger/184` |
| K-TR-28 | transport callsite: TR-28 | IMPLEMENTED | `analysis.json#/candidate_ledger/185` |
| K-TR-29 | transport callsite: TR-29 | IMPLEMENTED | `analysis.json#/candidate_ledger/186` |
| K-TR-30 | transport callsite: TR-30 | EXCLUDED | `analysis.json#/candidate_ledger/187` |
| K-product-129 | product branch: product-129 | IMPLEMENTED | `analysis.json#/candidate_ledger/188` |
| K-product-130 | product branch: product-130 | IMPLEMENTED | `analysis.json#/candidate_ledger/189` |
| K-product-131 | product branch: product-131 | IMPLEMENTED | `analysis.json#/candidate_ledger/190` |
| K-product-132 | product branch: product-132 | IMPLEMENTED | `analysis.json#/candidate_ledger/191` |
| K-product-133 | product branch: product-133 | IMPLEMENTED | `analysis.json#/candidate_ledger/192` |
| K-product-134 | product branch: product-134 | IMPLEMENTED | `analysis.json#/candidate_ledger/193` |
| K-product-142 | product branch: product-142 | IMPLEMENTED | `analysis.json#/candidate_ledger/194` |
| K-product-143 | product branch: product-143 | IMPLEMENTED | `analysis.json#/candidate_ledger/195` |
| K-room-selection-and-recovery | session/configuration selector: room-selection-and-recovery | IMPLEMENTED | `analysis.json#/candidate_ledger/196` |
| K-room-id-generation | session/configuration selector: room-id-generation | EXCLUDED | `analysis.json#/candidate_ledger/197` |
| K-firstRoomIdTest-adjustment | session/configuration selector: firstRoomIdTest-adjustment | EXCLUDED | `analysis.json#/candidate_ledger/198` |
| K-room-persistence-index-and-key | session/configuration persistence: room-persistence-index-and-key | EXCLUDED | `analysis.json#/candidate_ledger/199` |
| K-room-roster-success-and-stored-target | callback/state/control targeting: room-roster-success-and-stored-target | IMPLEMENTED | `analysis.json#/candidate_ledger/200` |
| S-id | Room/session id | EXCLUDED | `analysis.json#/room_session/id` |
| S-confidence | Room/session confidence | EXCLUDED | `analysis.json#/room_session/confidence` |
| S-evidence | Room/session evidence | EXCLUDED | `analysis.json#/room_session/evidence` |
| S-evaluation_order | Room/session evaluation_order | IMPLEMENTED | `analysis.json#/room_session/evaluation_order` |
| S-database_predicates | Room/session database_predicates | EXCLUDED | `analysis.json#/room_session/database_predicates` |
| S-routes | Room/session routes | IMPLEMENTED | `analysis.json#/room_session/routes` |
| S-generator | Room/session generator | EXCLUDED | `analysis.json#/room_session/generator` |
| S-origins | Room/session origins | EXCLUDED | `analysis.json#/room_session/origins` |
| S-join_gate | Room/session join_gate | EXCLUDED | `analysis.json#/room_session/join_gate` |
| S-reset_lifecycle | Room/session reset_lifecycle | EXCLUDED | `analysis.json#/room_session/reset_lifecycle` |
| S-connect_variants | Room/session connect_variants | EXCLUDED | `analysis.json#/room_session/connect_variants` |
| S-wire | Room/session wire | IMPLEMENTED | `analysis.json#/room_session/wire` |
| S-adversarial | Room/session adversarial | EXCLUDED | `analysis.json#/room_session/adversarial` |
| S-verification | Room/session verification | EXCLUDED | `analysis.json#/room_session/verification` |
| S-persistence | Room/session persistence | EXCLUDED | `analysis.json#/room_session/persistence` |
| V-product-129 | product-129 product/profile/capability reconciliation | IMPLEMENTED | `analysis.json#/variant_inventory/0` |
| V-product-130 | product-130 product/profile/capability reconciliation | IMPLEMENTED | `analysis.json#/variant_inventory/1` |
| V-product-131 | product-131 product/profile/capability reconciliation | IMPLEMENTED | `analysis.json#/variant_inventory/2` |
| V-product-132 | product-132 product/profile/capability reconciliation | IMPLEMENTED | `analysis.json#/variant_inventory/3` |
| V-product-133 | product-133 product/profile/capability reconciliation | IMPLEMENTED | `analysis.json#/variant_inventory/4` |
| V-product-134 | product-134 product/profile/capability reconciliation | IMPLEMENTED | `analysis.json#/variant_inventory/5` |
| V-product-142 | product-142 product/profile/capability reconciliation | IMPLEMENTED | `analysis.json#/variant_inventory/6` |
| V-product-143 | product-143 product/profile/capability reconciliation | IMPLEMENTED | `analysis.json#/variant_inventory/7` |
| I-constant-ledger.json-000 | CONST-SEAT_1_HEAD_UP | IMPLEMENTED | `constant-ledger.json#/0` |
| I-constant-ledger.json-001 | CONST-SEAT_1_HEAD_DOWN | IMPLEMENTED | `constant-ledger.json#/1` |
| I-constant-ledger.json-002 | CONST-SEAT_1_HEAD_STOP | IMPLEMENTED | `constant-ledger.json#/2` |
| I-constant-ledger.json-003 | CONST-SEAT_1_FOOT_UP | IMPLEMENTED | `constant-ledger.json#/3` |
| I-constant-ledger.json-004 | CONST-SEAT_1_FOOT_DOWN | IMPLEMENTED | `constant-ledger.json#/4` |
| I-constant-ledger.json-005 | CONST-SEAT_1_FOOT_STOP | IMPLEMENTED | `constant-ledger.json#/5` |
| I-constant-ledger.json-006 | CONST-SEAT_1_ALL_UP | IMPLEMENTED | `constant-ledger.json#/6` |
| I-constant-ledger.json-007 | CONST-SEAT_1_ALL_DOWN | IMPLEMENTED | `constant-ledger.json#/7` |
| I-constant-ledger.json-008 | CONST-SEAT_1_ALL_STOP | IMPLEMENTED | `constant-ledger.json#/8` |
| I-constant-ledger.json-009 | CONST-SEAT_2_HEAD_UP | IMPLEMENTED | `constant-ledger.json#/9` |
| I-constant-ledger.json-010 | CONST-SEAT_2_HEAD_DOWN | IMPLEMENTED | `constant-ledger.json#/10` |
| I-constant-ledger.json-011 | CONST-SEAT_2_HEAD_STOP | IMPLEMENTED | `constant-ledger.json#/11` |
| I-constant-ledger.json-012 | CONST-SEAT_2_FOOT_UP | IMPLEMENTED | `constant-ledger.json#/12` |
| I-constant-ledger.json-013 | CONST-SEAT_2_FOOT_DOWN | IMPLEMENTED | `constant-ledger.json#/13` |
| I-constant-ledger.json-014 | CONST-SEAT_2_FOOT_STOP | IMPLEMENTED | `constant-ledger.json#/14` |
| I-constant-ledger.json-015 | CONST-SEAT_2_ALL_UP | IMPLEMENTED | `constant-ledger.json#/15` |
| I-constant-ledger.json-016 | CONST-SEAT_2_ALL_DOWN | IMPLEMENTED | `constant-ledger.json#/16` |
| I-constant-ledger.json-017 | CONST-SEAT_2_ALL_STOP | IMPLEMENTED | `constant-ledger.json#/17` |
| I-constant-ledger.json-018 | CONST-SEAT_1_2_HEAD_UP | IMPLEMENTED | `constant-ledger.json#/18` |
| I-constant-ledger.json-019 | CONST-SEAT_1_2_HEAD_DOWN | IMPLEMENTED | `constant-ledger.json#/19` |
| I-constant-ledger.json-020 | CONST-SEAT_1_2_HEAD_STOP | IMPLEMENTED | `constant-ledger.json#/20` |
| I-constant-ledger.json-021 | CONST-SEAT_1_2_FOOT_UP | IMPLEMENTED | `constant-ledger.json#/21` |
| I-constant-ledger.json-022 | CONST-SEAT_1_2_FOOT_DOWN | IMPLEMENTED | `constant-ledger.json#/22` |
| I-constant-ledger.json-023 | CONST-SEAT_1_2_FOOT_STOP | IMPLEMENTED | `constant-ledger.json#/23` |
| I-constant-ledger.json-024 | CONST-SEAT_1_2_ALL_UP | IMPLEMENTED | `constant-ledger.json#/24` |
| I-constant-ledger.json-025 | CONST-SEAT_1_2_ALL_DOWN | IMPLEMENTED | `constant-ledger.json#/25` |
| I-constant-ledger.json-026 | CONST-SEAT_1_2_ALL_STOP | IMPLEMENTED | `constant-ledger.json#/26` |
| I-constant-ledger.json-027 | CONST-SEAT_1_ALL_MOTOR_STOP | IMPLEMENTED | `constant-ledger.json#/27` |
| I-constant-ledger.json-028 | CONST-SEAT_2_ALL_MOTOR_STOP | IMPLEMENTED | `constant-ledger.json#/28` |
| I-constant-ledger.json-029 | CONST-SEAT_1_2_ALL_MOTOR_STOP | IMPLEMENTED | `constant-ledger.json#/29` |
| I-constant-ledger.json-030 | CONST-SEAT_1_ALL_MOTOR_RESET_1 | EXCLUDED | `constant-ledger.json#/30` |
| I-constant-ledger.json-031 | CONST-SEAT_2_ALL_MOTOR_RESET_1 | EXCLUDED | `constant-ledger.json#/31` |
| I-constant-ledger.json-032 | CONST-SEAT_1_2_ALL_MOTOR_RESET_1 | EXCLUDED | `constant-ledger.json#/32` |
| I-constant-ledger.json-033 | CONST-SEAT_1_ALL_MOTOR_RESET_2 | EXCLUDED | `constant-ledger.json#/33` |
| I-constant-ledger.json-034 | CONST-SEAT_2_ALL_MOTOR_RESET_2 | EXCLUDED | `constant-ledger.json#/34` |
| I-constant-ledger.json-035 | CONST-SEAT_1_2_ALL_MOTOR_RESET_2 | EXCLUDED | `constant-ledger.json#/35` |
| I-constant-ledger.json-036 | CONST-SEAT_1_MEMORY_POSITION_A | IMPLEMENTED | `constant-ledger.json#/36` |
| I-constant-ledger.json-037 | CONST-SEAT_1_MEMORY_POSITION_B | IMPLEMENTED | `constant-ledger.json#/37` |
| I-constant-ledger.json-038 | CONST-SEAT_1_MEMORY_POSITION_C | IMPLEMENTED | `constant-ledger.json#/38` |
| I-constant-ledger.json-039 | CONST-SEAT_1_MEMORY_POSITION_D | EXCLUDED | `constant-ledger.json#/39` |
| I-constant-ledger.json-040 | CONST-SEAT_1_RUN_TO_POSITION_A | IMPLEMENTED | `constant-ledger.json#/40` |
| I-constant-ledger.json-041 | CONST-SEAT_1_RUN_TO_POSITION_B | IMPLEMENTED | `constant-ledger.json#/41` |
| I-constant-ledger.json-042 | CONST-SEAT_1_RUN_TO_POSITION_C | IMPLEMENTED | `constant-ledger.json#/42` |
| I-constant-ledger.json-043 | CONST-SEAT_1_RUN_TO_POSITION_D | EXCLUDED | `constant-ledger.json#/43` |
| I-constant-ledger.json-044 | CONST-SEAT_2_MEMORY_POSITION_A | IMPLEMENTED | `constant-ledger.json#/44` |
| I-constant-ledger.json-045 | CONST-SEAT_2_MEMORY_POSITION_B | IMPLEMENTED | `constant-ledger.json#/45` |
| I-constant-ledger.json-046 | CONST-SEAT_2_MEMORY_POSITION_C | IMPLEMENTED | `constant-ledger.json#/46` |
| I-constant-ledger.json-047 | CONST-SEAT_2_MEMORY_POSITION_D | EXCLUDED | `constant-ledger.json#/47` |
| I-constant-ledger.json-048 | CONST-SEAT_2_RUN_TO_POSITION_A | IMPLEMENTED | `constant-ledger.json#/48` |
| I-constant-ledger.json-049 | CONST-SEAT_2_RUN_TO_POSITION_B | IMPLEMENTED | `constant-ledger.json#/49` |
| I-constant-ledger.json-050 | CONST-SEAT_2_RUN_TO_POSITION_C | IMPLEMENTED | `constant-ledger.json#/50` |
| I-constant-ledger.json-051 | CONST-SEAT_2_RUN_TO_POSITION_D | EXCLUDED | `constant-ledger.json#/51` |
| I-constant-ledger.json-052 | CONST-SEAT_1_2_MEMORY_POSITION_A | IMPLEMENTED | `constant-ledger.json#/52` |
| I-constant-ledger.json-053 | CONST-SEAT_1_2_MEMORY_POSITION_B | IMPLEMENTED | `constant-ledger.json#/53` |
| I-constant-ledger.json-054 | CONST-SEAT_1_2_MEMORY_POSITION_C | IMPLEMENTED | `constant-ledger.json#/54` |
| I-constant-ledger.json-055 | CONST-SEAT_1_2_MEMORY_POSITION_D | EXCLUDED | `constant-ledger.json#/55` |
| I-constant-ledger.json-056 | CONST-SEAT_1_2_RUN_TO_POSITION_A | IMPLEMENTED | `constant-ledger.json#/56` |
| I-constant-ledger.json-057 | CONST-SEAT_1_2_RUN_TO_POSITION_B | IMPLEMENTED | `constant-ledger.json#/57` |
| I-constant-ledger.json-058 | CONST-SEAT_1_2_RUN_TO_POSITION_C | IMPLEMENTED | `constant-ledger.json#/58` |
| I-constant-ledger.json-059 | CONST-SEAT_1_2_RUN_TO_POSITION_D | EXCLUDED | `constant-ledger.json#/59` |
| I-constant-ledger.json-060 | CONST-SEAT_1_LOCK | EXCLUDED | `constant-ledger.json#/60` |
| I-constant-ledger.json-061 | CONST-SEAT_2_LOCK | EXCLUDED | `constant-ledger.json#/61` |
| I-constant-ledger.json-062 | CONST-SEAT_1_2_LOCK | EXCLUDED | `constant-ledger.json#/62` |
| I-constant-ledger.json-063 | CONST-SEAT_1_UNLOCK | EXCLUDED | `constant-ledger.json#/63` |
| I-constant-ledger.json-064 | CONST-SEAT_2_UNLOCK | EXCLUDED | `constant-ledger.json#/64` |
| I-constant-ledger.json-065 | CONST-SEAT_1_2_UNLOCK | EXCLUDED | `constant-ledger.json#/65` |
| I-constant-ledger.json-066 | CONST-ADD_DEVICE_SUCCESS | IMPLEMENTED | `constant-ledger.json#/66` |
| I-constant-ledger.json-067 | CONST-SEAT_1_MASSAGE_START | IMPLEMENTED | `constant-ledger.json#/67` |
| I-constant-ledger.json-068 | CONST-SEAT_1_MASSAGE_STOP | IMPLEMENTED | `constant-ledger.json#/68` |
| I-constant-ledger.json-069 | CONST-SEAT_2_MASSAGE_START | IMPLEMENTED | `constant-ledger.json#/69` |
| I-constant-ledger.json-070 | CONST-SEAT_2_MASSAGE_STOP | IMPLEMENTED | `constant-ledger.json#/70` |
| I-constant-ledger.json-071 | CONST-SEAT_1_2_MASSAGE_START | IMPLEMENTED | `constant-ledger.json#/71` |
| I-constant-ledger.json-072 | CONST-SEAT_1_2_MASSAGE_STOP | IMPLEMENTED | `constant-ledger.json#/72` |
| I-constant-ledger.json-073 | CONST-SEAT_1_HEAD_MASSAGE_SETTING | IMPLEMENTED | `constant-ledger.json#/73` |
| I-constant-ledger.json-074 | CONST-SEAT_2_HEAD_MASSAGE_SETTING | IMPLEMENTED | `constant-ledger.json#/74` |
| I-constant-ledger.json-075 | CONST-SEAT_1_LEG_MASSAGE_SETTING | IMPLEMENTED | `constant-ledger.json#/75` |
| I-constant-ledger.json-076 | CONST-SEAT_2_LEG_MASSAGE_SETTING | IMPLEMENTED | `constant-ledger.json#/76` |
| I-constant-ledger.json-077 | CONST-SEAT_1_2_HEAD_MASSAGE_SETTING | IMPLEMENTED | `constant-ledger.json#/77` |
| I-constant-ledger.json-078 | CONST-SEAT_1_2_LEG_MASSAGE_SETTING | IMPLEMENTED | `constant-ledger.json#/78` |
| I-constant-ledger.json-079 | CONST-SEAT_1_MASSAGE_15 | IMPLEMENTED | `constant-ledger.json#/79` |
| I-constant-ledger.json-080 | CONST-SEAT_1_MASSAGE_30 | IMPLEMENTED | `constant-ledger.json#/80` |
| I-constant-ledger.json-081 | CONST-SEAT_1_MASSAGE_45 | IMPLEMENTED | `constant-ledger.json#/81` |
| I-constant-ledger.json-082 | CONST-SEAT_2_MASSAGE_15 | IMPLEMENTED | `constant-ledger.json#/82` |
| I-constant-ledger.json-083 | CONST-SEAT_2_MASSAGE_30 | IMPLEMENTED | `constant-ledger.json#/83` |
| I-constant-ledger.json-084 | CONST-SEAT_2_MASSAGE_45 | IMPLEMENTED | `constant-ledger.json#/84` |
| I-constant-ledger.json-085 | CONST-SEAT_1_2_MASSAGE_15 | IMPLEMENTED | `constant-ledger.json#/85` |
| I-constant-ledger.json-086 | CONST-SEAT_1_2_MASSAGE_30 | IMPLEMENTED | `constant-ledger.json#/86` |
| I-constant-ledger.json-087 | CONST-SEAT_1_2_MASSAGE_45 | IMPLEMENTED | `constant-ledger.json#/87` |
| I-constant-ledger.json-088 | CONST-SEAT_1_BED_LIGHT_ON | IMPLEMENTED | `constant-ledger.json#/88` |
| I-constant-ledger.json-089 | CONST-SEAT_1_BED_LIGHT_OFF | IMPLEMENTED | `constant-ledger.json#/89` |
| I-constant-ledger.json-090 | CONST-SEAT_2_BED_LIGHT_ON | IMPLEMENTED | `constant-ledger.json#/90` |
| I-constant-ledger.json-091 | CONST-SEAT_2_BED_LIGHT_OFF | IMPLEMENTED | `constant-ledger.json#/91` |
| I-constant-ledger.json-092 | CONST-SEAT_1_2_BED_LIGHT_ON | IMPLEMENTED | `constant-ledger.json#/92` |
| I-constant-ledger.json-093 | CONST-SEAT_1_2_BED_LIGHT_OFF | IMPLEMENTED | `constant-ledger.json#/93` |
| I-constant-ledger.json-094 | CONST-SEAT_1_ZG | IMPLEMENTED | `constant-ledger.json#/94` |
| I-constant-ledger.json-095 | CONST-SEAT_2_ZG | IMPLEMENTED | `constant-ledger.json#/95` |
| I-constant-ledger.json-096 | CONST-SEAT_1_2_ZG | IMPLEMENTED | `constant-ledger.json#/96` |
| I-constant-ledger.json-097 | CONST-SEAT_1_ANTI_SNORE | IMPLEMENTED | `constant-ledger.json#/97` |
| I-constant-ledger.json-098 | CONST-SEAT_2_ANTI_SNORE | IMPLEMENTED | `constant-ledger.json#/98` |
| I-constant-ledger.json-099 | CONST-SEAT_1_2_ANTI_SNORE | IMPLEMENTED | `constant-ledger.json#/99` |
| I-constant-ledger.json-100 | CONST-SEAT_1_PLAN_BED | EXCLUDED | `constant-ledger.json#/100` |
| I-constant-ledger.json-101 | CONST-SEAT_2_PLAN_BED | EXCLUDED | `constant-ledger.json#/101` |
| I-constant-ledger.json-102 | CONST-SEAT_1_2_PLAN_BED | EXCLUDED | `constant-ledger.json#/102` |
| I-constant-ledger.json-103 | CONST-SEAT_1_MASSAGE_MODE1 | IMPLEMENTED | `constant-ledger.json#/103` |
| I-constant-ledger.json-104 | CONST-SEAT_2_MASSAGE_MODE1 | IMPLEMENTED | `constant-ledger.json#/104` |
| I-constant-ledger.json-105 | CONST-SEAT_1_2_MASSAGE_MODE1 | IMPLEMENTED | `constant-ledger.json#/105` |
| I-constant-ledger.json-106 | CONST-SEAT_1_MASSAGE_MODE2 | IMPLEMENTED | `constant-ledger.json#/106` |
| I-constant-ledger.json-107 | CONST-SEAT_2_MASSAGE_MODE2 | IMPLEMENTED | `constant-ledger.json#/107` |
| I-constant-ledger.json-108 | CONST-SEAT_1_2_MASSAGE_MODE2 | IMPLEMENTED | `constant-ledger.json#/108` |
| I-constant-ledger.json-109 | CONST-SEAT_1_MASSAGE_MODE3 | IMPLEMENTED | `constant-ledger.json#/109` |
| I-constant-ledger.json-110 | CONST-SEAT_2_MASSAGE_MODE3 | IMPLEMENTED | `constant-ledger.json#/110` |
| I-constant-ledger.json-111 | CONST-SEAT_1_2_MASSAGE_MODE3 | IMPLEMENTED | `constant-ledger.json#/111` |
| I-constant-ledger.json-112 | CONST-SEAT_1_MASSAGE_MODE_CACEL | IMPLEMENTED | `constant-ledger.json#/112` |
| I-constant-ledger.json-113 | CONST-SEAT_2_MASSAGE_MODE_CACEL | IMPLEMENTED | `constant-ledger.json#/113` |
| I-constant-ledger.json-114 | CONST-SEAT_1_2_MASSAGE_MODE_CACEL | IMPLEMENTED | `constant-ledger.json#/114` |
| I-constant-ledger.json-115 | CONST-SEAT_1_TIME_CACEL | IMPLEMENTED | `constant-ledger.json#/115` |
| I-constant-ledger.json-116 | CONST-SEAT_2_TIME_CACEL | IMPLEMENTED | `constant-ledger.json#/116` |
| I-constant-ledger.json-117 | CONST-SEAT_1_2_TIME_CACEL | IMPLEMENTED | `constant-ledger.json#/117` |
| I-constant-ledger.json-118 | CONST-SEAT_1_BACK_UP | IMPLEMENTED | `constant-ledger.json#/118` |
| I-constant-ledger.json-119 | CONST-SEAT_1_BACK_DOWN | IMPLEMENTED | `constant-ledger.json#/119` |
| I-constant-ledger.json-120 | CONST-SEAT_1_BACK_STOP | IMPLEMENTED | `constant-ledger.json#/120` |
| I-constant-ledger.json-121 | CONST-SEAT_2_BACK_UP | EXCLUDED | `constant-ledger.json#/121` |
| I-constant-ledger.json-122 | CONST-SEAT_2_BACK_DOWN | EXCLUDED | `constant-ledger.json#/122` |
| I-constant-ledger.json-123 | CONST-SEAT_2_BACK_STOP | EXCLUDED | `constant-ledger.json#/123` |
| I-constant-ledger.json-124 | CONST-SEAT_1_2_BACK_UP | EXCLUDED | `constant-ledger.json#/124` |
| I-constant-ledger.json-125 | CONST-SEAT_1_2_BACK_DOWN | EXCLUDED | `constant-ledger.json#/125` |
| I-constant-ledger.json-126 | CONST-SEAT_1_2_BACK_STOP | EXCLUDED | `constant-ledger.json#/126` |
| I-constant-ledger.json-127 | CONST-SEAT_1_WAIST_UP | IMPLEMENTED | `constant-ledger.json#/127` |
| I-constant-ledger.json-128 | CONST-SEAT_1_WAIST_DOWN | IMPLEMENTED | `constant-ledger.json#/128` |
| I-constant-ledger.json-129 | CONST-SEAT_1_WAIST_STOP | IMPLEMENTED | `constant-ledger.json#/129` |
| I-constant-ledger.json-130 | CONST-SEAT_2_WAIST_UP | EXCLUDED | `constant-ledger.json#/130` |
| I-constant-ledger.json-131 | CONST-SEAT_2_WAIST_DOWN | EXCLUDED | `constant-ledger.json#/131` |
| I-constant-ledger.json-132 | CONST-SEAT_2_WAIST_STOP | EXCLUDED | `constant-ledger.json#/132` |
| I-constant-ledger.json-133 | CONST-SEAT_1_2_WAIST_UP | EXCLUDED | `constant-ledger.json#/133` |
| I-constant-ledger.json-134 | CONST-SEAT_1_2_WAIST_DOWN | EXCLUDED | `constant-ledger.json#/134` |
| I-constant-ledger.json-135 | CONST-SEAT_1_2_WAIST_STOP | EXCLUDED | `constant-ledger.json#/135` |
| I-constant-ledger.json-136 | CONST-SEAT_1_NEW_ALL_UP | IMPLEMENTED | `constant-ledger.json#/136` |
| I-constant-ledger.json-137 | CONST-SEAT_1_NEW_ALL_DOWN | IMPLEMENTED | `constant-ledger.json#/137` |
| I-constant-ledger.json-138 | CONST-SEAT_1_NEW_ALL_STOP | IMPLEMENTED | `constant-ledger.json#/138` |
| I-constant-ledger.json-139 | CONST-SEAT_2_NEW_ALL_UP | EXCLUDED | `constant-ledger.json#/139` |
| I-constant-ledger.json-140 | CONST-SEAT_2_NEW_ALL_DOWN | EXCLUDED | `constant-ledger.json#/140` |
| I-constant-ledger.json-141 | CONST-SEAT_2_NEW_ALL_STOP | EXCLUDED | `constant-ledger.json#/141` |
| I-constant-ledger.json-142 | CONST-SEAT_1_2_NEW_ALL_UP | EXCLUDED | `constant-ledger.json#/142` |
| I-constant-ledger.json-143 | CONST-SEAT_1_2_NEW_ALL_DOWN | EXCLUDED | `constant-ledger.json#/143` |
| I-constant-ledger.json-144 | CONST-SEAT_1_2_NEW_ALL_STOP | EXCLUDED | `constant-ledger.json#/144` |
| I-constant-ledger.json-145 | CONST-ALL_SOFA_UNLOCK | EXCLUDED | `constant-ledger.json#/145` |
| I-constant-ledger.json-146 | CONST-ALL_SOFA_LOCK | EXCLUDED | `constant-ledger.json#/146` |
| I-constant-ledger.json-147 | CONST-GET_LOCK_STATE | EXCLUDED | `constant-ledger.json#/147` |
| I-transport-ledger.json-000 | TR-01 | EXCLUDED | `transport-ledger.json#/0` |
| I-transport-ledger.json-001 | TR-02 | EXCLUDED | `transport-ledger.json#/1` |
| I-transport-ledger.json-002 | TR-03 | EXCLUDED | `transport-ledger.json#/2` |
| I-transport-ledger.json-003 | TR-04 | IMPLEMENTED | `transport-ledger.json#/3` |
| I-transport-ledger.json-004 | TR-05 | IMPLEMENTED | `transport-ledger.json#/4` |
| I-transport-ledger.json-005 | TR-06 | IMPLEMENTED | `transport-ledger.json#/5` |
| I-transport-ledger.json-006 | TR-07 | IMPLEMENTED | `transport-ledger.json#/6` |
| I-transport-ledger.json-007 | TR-08 | IMPLEMENTED | `transport-ledger.json#/7` |
| I-transport-ledger.json-008 | TR-09 | IMPLEMENTED | `transport-ledger.json#/8` |
| I-transport-ledger.json-009 | TR-10 | IMPLEMENTED | `transport-ledger.json#/9` |
| I-transport-ledger.json-010 | TR-11 | IMPLEMENTED | `transport-ledger.json#/10` |
| I-transport-ledger.json-011 | TR-12 | IMPLEMENTED | `transport-ledger.json#/11` |
| I-transport-ledger.json-012 | TR-13 | IMPLEMENTED | `transport-ledger.json#/12` |
| I-transport-ledger.json-013 | TR-14 | IMPLEMENTED | `transport-ledger.json#/13` |
| I-transport-ledger.json-014 | TR-15 | IMPLEMENTED | `transport-ledger.json#/14` |
| I-transport-ledger.json-015 | TR-16 | EXCLUDED | `transport-ledger.json#/15` |
| I-transport-ledger.json-016 | TR-17 | EXCLUDED | `transport-ledger.json#/16` |
| I-transport-ledger.json-017 | TR-18 | EXCLUDED | `transport-ledger.json#/17` |
| I-transport-ledger.json-018 | TR-19 | EXCLUDED | `transport-ledger.json#/18` |
| I-transport-ledger.json-019 | TR-20 | EXCLUDED | `transport-ledger.json#/19` |
| I-transport-ledger.json-020 | TR-21 | EXCLUDED | `transport-ledger.json#/20` |
| I-transport-ledger.json-021 | TR-22 | EXCLUDED | `transport-ledger.json#/21` |
| I-transport-ledger.json-022 | TR-23 | EXCLUDED | `transport-ledger.json#/22` |
| I-transport-ledger.json-023 | TR-24 | EXCLUDED | `transport-ledger.json#/23` |
| I-transport-ledger.json-024 | TR-25 | EXCLUDED | `transport-ledger.json#/24` |
| I-transport-ledger.json-025 | TR-26 | IMPLEMENTED | `transport-ledger.json#/25` |
| I-transport-ledger.json-026 | TR-27 | IMPLEMENTED | `transport-ledger.json#/26` |
| I-transport-ledger.json-027 | TR-28 | IMPLEMENTED | `transport-ledger.json#/27` |
| I-transport-ledger.json-028 | TR-29 | IMPLEMENTED | `transport-ledger.json#/28` |
| I-transport-ledger.json-029 | TR-30 | EXCLUDED | `transport-ledger.json#/29` |
| X-network | WiFi/SSID/password/network administration/cloud/accounts | EXCLUDED | `FEATURE_DOMAINS.md` |
| X-app-defects | Wrong target timer, stale callback, SQL collision, malformed bounds, unmount missing STOP, premature auth ready | EXCLUDED | `E-LIFECYCLE` |

## Exclusion reasons

- `C112`: Safety: do not reset an already-enrolled device or replace another controller room. Use the official app for destructive room transfer; HA adopts an existing room by explicit selection. Exact mode07 advertisement frozen, never guessed.
- `P-discovery_rules-auto_connect`, `P-timing-queue`, `P-timing-ui_only`, `P-timing-reconnect`, `P-timing-write_failure`: Android transport/UI scheduler machinery is replaced by HA Bluetooth, command locking and awaited GATT writes. No hardware command timer, retry, release or packet is inferred from queue polling, GIF or phone countdown timers.
- `P-gatt-read`, `P-gatt-mtu_priority_bond`, `P-capabilities-other_absences`: No reachable app feature was found. Do not invent reads, pairing negotiation, encryption or additional commands from SDK/dead constants.
- `P-notifications-6`, `P-notifications-7`, `P-notifications-8`, `P-notifications-9`: Channel2F is a phone alarm trigger; product/group and remote-response metadata have no app control/state consumer. Companion/library infrastructure, not missing bed telemetry.
- `K-server`, `K-metadata`, `K-library-ad-modes`, `K-library-packet-helpers`, `K-alternate-discovery`, `K-local-schedules`, `K-theme-qr`, `K-native-runtime`, `K-CONST-SEAT_1_ALL_MOTOR_RESET_1`, `K-CONST-SEAT_2_ALL_MOTOR_RESET_1`, `K-CONST-SEAT_1_2_ALL_MOTOR_RESET_1`, `K-CONST-SEAT_1_ALL_MOTOR_RESET_2`, `K-CONST-SEAT_2_ALL_MOTOR_RESET_2`, `K-CONST-SEAT_1_2_ALL_MOTOR_RESET_2`, `K-CONST-SEAT_1_MEMORY_POSITION_D`, `K-CONST-SEAT_1_RUN_TO_POSITION_D`, `K-CONST-SEAT_2_MEMORY_POSITION_D`, `K-CONST-SEAT_2_RUN_TO_POSITION_D`, `K-CONST-SEAT_1_2_MEMORY_POSITION_D`, `K-CONST-SEAT_1_2_RUN_TO_POSITION_D`, `K-CONST-SEAT_1_LOCK`, `K-CONST-SEAT_2_LOCK`, `K-CONST-SEAT_1_2_LOCK`, `K-CONST-SEAT_1_UNLOCK`, `K-CONST-SEAT_2_UNLOCK`, `K-CONST-SEAT_1_2_UNLOCK`, `K-CONST-SEAT_1_PLAN_BED`, `K-CONST-SEAT_2_PLAN_BED`, `K-CONST-SEAT_1_2_PLAN_BED`, `K-CONST-SEAT_2_BACK_UP`, `K-CONST-SEAT_2_BACK_DOWN`, `K-CONST-SEAT_2_BACK_STOP`, `K-CONST-SEAT_1_2_BACK_UP`, `K-CONST-SEAT_1_2_BACK_DOWN`, `K-CONST-SEAT_1_2_BACK_STOP`, `K-CONST-SEAT_2_WAIST_UP`, `K-CONST-SEAT_2_WAIST_DOWN`, `K-CONST-SEAT_2_WAIST_STOP`, `K-CONST-SEAT_1_2_WAIST_UP`, `K-CONST-SEAT_1_2_WAIST_DOWN`, `K-CONST-SEAT_1_2_WAIST_STOP`, `K-CONST-SEAT_2_NEW_ALL_UP`, `K-CONST-SEAT_2_NEW_ALL_DOWN`, `K-CONST-SEAT_2_NEW_ALL_STOP`, `K-CONST-SEAT_1_2_NEW_ALL_UP`, `K-CONST-SEAT_1_2_NEW_ALL_DOWN`, `K-CONST-SEAT_1_2_NEW_ALL_STOP`, `K-CONST-ALL_SOFA_UNLOCK`, `K-CONST-ALL_SOFA_LOCK`, `K-CONST-GET_LOCK_STATE`, `K-TR-01`, `K-TR-02`, `K-TR-03`, `K-TR-16`, `K-TR-17`, `K-TR-18`, `K-TR-19`, `K-TR-20`, `K-TR-21`, `K-TR-22`, `K-TR-23`, `K-TR-24`, `K-TR-25`, `K-TR-30`, `K-room-id-generation`, `K-firstRoomIdTest-adjustment`, `K-room-persistence-index-and-key`: Artifact-dead code or unrelated companion/library infrastructure; phone SQL row allocation, labels and alarms are replaced by HA config entries/automations. Destructive room reset is excluded for safety; no wrong-target, optimistic-success or stale-callback defects reproduced.
- `S-id`, `S-confidence`, `S-evidence`: Audit provenance/index metadata rather than a reachable BLE operation; retained as evidence, no runtime feature implied.
- `S-database_predicates`, `S-generator`, `S-origins`, `S-join_gate`, `S-connect_variants`, `S-adversarial`, `S-verification`, `S-persistence`: Phone database, room inventory/label restoration, SQL keys/index arithmetic and proof harness metadata are companion infrastructure. HA config entries explicitly own each physical MAC/product/room. No optimistic DB success, old-target selection or unverified saved virtual address is reproduced. Equivalent wire behavior remains implemented in C108-C111 and S-wire.
- `S-reset_lifecycle`: HA persists explicit room/MAC/profile rather than reproducing Android ORM, generated room labels, reset broadcasts or callback identity bugs. See session safety boundary below.
- `I-constant-ledger.json-030`, `I-constant-ledger.json-031`, `I-constant-ledger.json-032`, `I-constant-ledger.json-033`, `I-constant-ledger.json-034`, `I-constant-ledger.json-035`, `I-constant-ledger.json-039`, `I-constant-ledger.json-043`, `I-constant-ledger.json-047`, `I-constant-ledger.json-051`, `I-constant-ledger.json-055`, `I-constant-ledger.json-059`, `I-constant-ledger.json-060`, `I-constant-ledger.json-061`, `I-constant-ledger.json-062`, `I-constant-ledger.json-063`, `I-constant-ledger.json-064`, `I-constant-ledger.json-065`, `I-constant-ledger.json-100`, `I-constant-ledger.json-101`, `I-constant-ledger.json-102`, `I-constant-ledger.json-121`, `I-constant-ledger.json-122`, `I-constant-ledger.json-123`, `I-constant-ledger.json-124`, `I-constant-ledger.json-125`, `I-constant-ledger.json-126`, `I-constant-ledger.json-130`, `I-constant-ledger.json-131`, `I-constant-ledger.json-132`, `I-constant-ledger.json-133`, `I-constant-ledger.json-134`, `I-constant-ledger.json-135`, `I-constant-ledger.json-139`, `I-constant-ledger.json-140`, `I-constant-ledger.json-141`, `I-constant-ledger.json-142`, `I-constant-ledger.json-143`, `I-constant-ledger.json-144`, `I-constant-ledger.json-145`, `I-constant-ledger.json-146`, `I-constant-ledger.json-147`, `I-transport-ledger.json-000`, `I-transport-ledger.json-001`, `I-transport-ledger.json-002`, `I-transport-ledger.json-015`, `I-transport-ledger.json-016`, `I-transport-ledger.json-017`, `I-transport-ledger.json-018`, `I-transport-ledger.json-019`, `I-transport-ledger.json-020`, `I-transport-ledger.json-021`, `I-transport-ledger.json-022`, `I-transport-ledger.json-023`, `I-transport-ledger.json-024`, `I-transport-ledger.json-029`: See named constant/callsite in K inventory and session safety boundary; dead code remains excluded.
- `X-network`: Product boundary: direct BLE bed features only; no network/cloud feature protocol discovered. Theme HTTP/QR/Realm remains companion infrastructure.
- `X-app-defects`: Safety: pin movement side/target through cleanup; validate full lengths; require accepted auth and live current-MAC roster; never reproduce app defects.

## Completion record

616 indexed rows: EXCLUDED 150, IMPLEMENTED 466. All 114 command rows, 105 UI opcodes, eight variants, 201 candidates, 148 constants and 30 transport callsites are accounted for. No frozen report or audit was modified.


Validation on rebased main `c3da67cb32a38e1a80c4f33c04e8b2899eb8b295`: focused
ISleep/controller-contract/profile/Kaidi/detection/config-flow/paired-setup suite
**1466 passed**. Existing mocked socket warnings are retained in local logs.
Repository Ruff and Pyright pass. Frontend typecheck/build passes; **98 frontend
tests pass**, and the shipped bundle was rebuilt. No full suite or hardware
tests were run. Independent Sol review and remote checks are recorded in the
implementation handoff; these automated results do not establish hardware support.

After integrating main `9112d33606f4557ecccdab44d3b2db5afe0c57bb`, review fixes
pass 573 affected ISleep/entity/config tests plus 1008 controller/profile/Kaidi/
detection/paired tests. Ruff/Pyright pass; rebuilt frontend passes 124 tests.
`test_single_address_options_reject_losing_split_controls` preserves a working
paired configuration on incompatible edits.
`test_massage_entity_state_survives_idle_disconnect_and_reconnect_per_side`
checks optimistic timer/strength state through real entity/coordinator/paired
callers and reconnected controller restoration, including side isolation.

Final pre-publication integration base
`933861f457c24dfb5e63355b58a2a6762512f462`: the approved source additions/removals
are byte-identical for every non-generated source/document/test file. English
JSON keys were merged semantically and the bundle rebuilt. 1171 focused
ISleep/controller/profile/detection/paired tests pass; frontend typecheck/build
and 125 tests pass. Independent Sol review approved after two rounds, with both
caller bugs and the shared-label nit fixed. Hardware remains unverified.
