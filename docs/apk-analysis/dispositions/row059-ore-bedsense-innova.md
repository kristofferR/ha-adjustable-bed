# Row059: Bedsense Bases and INNOVA app dispositions

Formal cluster `cluster-015` has two accepted members: `com.ore.sfmc2bedsence` 1.1 (3)
("Bedsense Bases", representative) and `com.ore.sfm` 2.0 (3) ("INNOVA", sibling). The
comparison accounts for **126 discovery items: 95 IMPLEMENTED, 2
ALREADY_IMPLEMENTED, 29 EXCLUDED**. Hardware is unverified (STATIC VERIFIED /
HARDWARE UNVERIFIED).

The public contract is the [Bedsense Bases and INNOVA profiles](../../beds/keeson.md#bedsense-bases-and-innova-profiles).
The reconciliation found the two apps materially different in packets, framing, timing,
parsing and capabilities, so every behavior is gated per app. Both share the Keeson
`E5 FE 16` frame and FFE9/FFE4 roles, but Bedsense uses big-endian keys with the
BetterLiving-style preset, save and absolute massage values, while INNOVA uses
little-endian standard Keeson keys, held memory recall, relative massage, a rename frame
and 16/19-byte state notifications. Neither app filters its scan, so both are explicit
`bedsense_bases` and `innova` Keeson profiles that Auto never selects; the motor count
selects the app's 2M/3M/4M layout.

## Exact accepted authority

| Identity or authority | SHA-256 / result |
|---|---|
| Bedsense Bases APK | `dceea120f8d0e56ecaa6c8e5eaa63c8f43a04b4c0acf91e31ad3cc2546640ea1` |
| Bedsense REPORT.SHA256 (attempt 001), accepted by independent audit 001 | `381e2671f1e7bcc8b7596e6a4d5b1c4f550e8e7999fe6f93a11da82b6d3179de` |
| Bedsense AUDIT.SHA256 | `bdf1d641c3095924d250c81bc790d417eb4bd073df4c02e62f942fa798229e94` |
| INNOVA APK | `d46d4bef4be6e62655fc527698e355c938832e72d5a9bfe2ff33904a240ac202` |
| INNOVA REPORT.SHA256 (attempt 002, IA-001..003 repaired), accepted by independent audit 002 | `f0d9f8f5b635e86d6f8aa7c787432d69bb65329ab22c67c1fa1c0c3f4e7ffae5` |
| INNOVA AUDIT.SHA256 | `3ec35e15ca37d0dd0a9cc3f0c99070dfabe3737c31b0d3670aa8d04d9c8535b4` |
| Cluster RECONCILIATION.SHA256 (attempt 001) | `9015b3d9e414ae9da87bfbad6f87ad77e452715fa959272c358d4add391ee261` |
| Reconciliation audit 001 AUDIT.SHA256 | `8ab506943d5694dd88e4f3dc9c759791b11bb012c808b95591b0c4da219527e1` |
| Effective decision | WHOLE_CLUSTER_ACCEPTED; both reports COMPLETE, 17 gates PASS |

Raw artifacts, reports and decompiled sources remain machine-local.

## What changed

- New explicit Keeson variants `bedsense_bases` and `innova` (setup wizard and options), in
  `beds/keeson_ore_sfm.py`. Auto, Sino and every other profile keep their behavior. The
  Sino label no longer names INNOVA, whose accepted app uses little-endian frames.
- Motor count 2/3/4 selects the 2M/3M/4M layout: Back and Legs covers, plus Back + Legs (2M),
  Head (Bedsense 3M) or Lumbar (INNOVA 3M), or Waist and Lumbar (4M). Waist is a new cover key.
- Held controls refresh every 100 ms and release with the zero key 100 ms later; one-shot
  writes sleep 100 ms first, as `sendSingleMessage` does. Stop sends the zero key.
- Bedsense: big-endian recall and long-click program frames for Zero G, Flat and Memory A/B,
  absolute 0-3 wave/head/foot massage numbers, Massage start, Massage off, a 10/20/30 minute
  timer select and discrete light on/off. Replies are discarded by the app, so nothing subscribes.
- INNOVA: little-endian standard keys, held Memory A/B and memory-page timer, relative massage
  steps, Massage level and Massage: Timer buttons, a light toggle, the `innova_rename` action,
  and FFE4 Light / Massage timer states that clear when the connection ends.
- Both profiles write only to FFE9, require FFE4 to exist, and mirror Android's inherited
  write type. Changing profile or bed type removes the profile's covers, buttons and states.

## Totals

| Disposition | Count |
|---|---|
| IMPLEMENTED | 95 |
| ALREADY_IMPLEMENTED | 2 |
| EXCLUDED | 29 |
| Total | 126 |

| Exclusion reason | Count |
|---|---|
| App UI identity flow | 3 |
| Dead artifact code | 8 |
| Platform boundary | 11 |
| Safety constraint | 3 |
| Unrelated to bed integration | 4 |

## Inventory coverage

Every pointer below is mapped to exactly one ledger row; the generator (machine-local
`row059-ledger.py`) asserts that the mapping equals the union of both inventories, that each
count matches the inventory totals and that every row is used (469 pointers).

| Package | Semantic entries | Command/variant instances | Candidate rows | Variant entries | Bluetooth API instructions |
|---|---|---|---|---|---|
| com.ore.sfmc2bedsence 1.1 (3), Bedsense Bases (representative) | 63 | 77 | 35 | 9 | 41 |
| com.ore.sfm 2.0 (3), INNOVA (sibling) | 71 | 62 | 61 | 12 | 38 |

## Ledger

B = Bedsense Bases, S = INNOVA. Pointers counts the inventory entries mapped to the row.

| ID | Pkg | Area | Item | Disposition | Pointers | Binding or exclusion reason |
|---|---|---|---|---|---|---|
| B-cmd-001 | B | command | Back up `0x00000001` held | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Back cover open -> move_head_up; 10 x 100 ms then zero key; tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-002 | B | command | Back down `0x00000002` held | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Back cover close -> move_head_down; tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-003 | B | command | Foot up `0x00000004` held | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Legs cover open -> move_feet_up; tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-004 | B | command | Foot down `0x00000008` held | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Legs cover close -> move_feet_down; tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-005 | B | command | 2M combined up `0x00000010` held | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Back + Legs cover (motor count 2) -> move_union_up; tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-006 | B | command | 2M combined down `0x00000020` held | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Back + Legs cover -> move_union_down; tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-007 | B | command | 3M head up `0x00000010` held | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Head cover (key tilt, motor count 3) -> move_tilt_up; tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-008 | B | command | 3M head down `0x00000020` held | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Head cover -> move_tilt_down; tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-009 | B | command | 4M waist up `0x00000010` held | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Waist cover (motor count 4) -> move_tilt_up; tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-010 | B | command | 4M waist down `0x00000020` held | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Waist cover -> move_tilt_down; tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-011 | B | command | 4M lumbar up `0x00000040` held | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Lumbar cover (motor count 4) -> move_lumbar_up; tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-012 | B | command | 4M lumbar down `0x00000080` held | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Lumbar cover -> move_lumbar_down; tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-013 | B | command | Zero key `0x00000000`: movement release and repeated-preset stop | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py _release_motion (100 ms, fresh event) and the Stop button (stop_all, supports_stop_all); tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames; tests/test_keeson_ore_sfm.py::test_release_survives_a_stop_request |
| B-cmd-014 | B | command | Zero G recall `0x01000001` | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Zero G button -> preset_zero_g; tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-015 | B | command | Zero G program `0x20000001` (long-click) | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Program Zero G button (ore_sfm_program_zero_g); tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-016 | B | command | Flat recall `0x01000002` | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Flat button -> preset_flat; tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-017 | B | command | Flat program `0x20000002` (long-click) | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Program Flat button (ore_sfm_program_flat); tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-018 | B | command | Memory A recall `0x01000008` | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Memory 1 button -> preset_memory(1); tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-019 | B | command | Memory A program `0x20000008` | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Save Memory 1 -> program_memory(1); tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-020 | B | command | Memory B recall `0x01000009` | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Memory 2 button -> preset_memory(2); tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-021 | B | command | Memory B program `0x20000009` | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Save Memory 2 -> program_memory(2); tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-022 | B | command | Wave `0x10000020 + floor(progress/10)`, buckets 0-3 | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Wave intensity number 0-3 -> set_massage_intensity('wave'); tests/test_keeson_ore_sfm.py::test_bedsense_massage_buckets_start_and_stop |
| B-cmd-023 | B | command | Head massage `0x10000010 + n`, buckets 0-3 | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Head massage intensity number 0-3; tests/test_keeson_ore_sfm.py::test_bedsense_massage_buckets_start_and_stop |
| B-cmd-024 | B | command | Foot massage `0x11000010 + n`, buckets 0-3 | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Foot massage intensity number 0-3; tests/test_keeson_ore_sfm.py::test_bedsense_massage_buckets_start_and_stop |
| B-cmd-025 | B | command | Massage start: wave, head, foot at current levels | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Massage start button (ore_sfm_massage_start), 100 ms before each; tests/test_keeson_ore_sfm.py::test_bedsense_massage_buckets_start_and_stop |
| B-cmd-026 | B | command | Massage stop: head 0 then foot 0 | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Massage off button -> massage_off; tests/test_keeson_ore_sfm.py::test_bedsense_massage_buckets_start_and_stop |
| B-cmd-027 | B | command | Massage timer 10 min `0x10000030` | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Massage timer select -> set_massage_timer(10); tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-028 | B | command | Massage timer 20 min `0x10000031` | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Massage timer select -> set_massage_timer(20); tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-029 | B | command | Massage timer 30 min `0x10000032` | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Massage timer select -> set_massage_timer(30); tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-cmd-030 | B | command | Light on `0x31000001` | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Under-bed light switch -> lights_on; toggle follows local state; tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames; tests/test_keeson_ore_sfm.py::test_bedsense_light_toggle_follows_local_state |
| B-cmd-031 | B | command | Light off `0x31000000` | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Under-bed light switch -> lights_off; tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames; tests/test_keeson_ore_sfm.py::test_bedsense_light_toggle_follows_local_state |
| B-builder | B | builder | F(key) = E5 FE 16 + key big-endian + complemented additive checksum | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py ore_sfm_frame(big_endian=True); tests/test_keeson_ore_sfm.py::test_builders_match_the_report_byte_order |
| B-replies | B | parser | Nonempty FFE4 values; only length 9 accepted; byte 7 split into bits and discarded | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py start_notify does not subscribe and the profile publishes no reply state (local enable writes no CCCD, replies drive nothing); tests/test_keeson_ore_sfm.py::test_bedsense_never_subscribes |
| B-timing | B | timing | Held keys at 0 ms then every 100 ms; single sends sleep 100 ms first; dead others 500 ms | IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py default (10, 100) burst, _send_singles; tests/test_keeson_ore_sfm.py::test_hold_timing_and_single_send_delay |
| B-release | B | release | UP/CANCEL/outside: cancel refresh, then zero key 100 ms later; no physical STOP guarantee | IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py _release_motion with a fresh asyncio.Event; tests/test_keeson_ore_sfm.py::test_release_survives_a_stop_request |
| B-gatt | B | transport | FFE9 write and FFE4 notify by UUID across all services; both required; inherited write type | IMPLEMENTED | 9 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py fixed FFE9, _require_roles, _refresh_write_mode; tests/test_keeson_ore_sfm.py::test_both_roles_are_required_like_the_app, tests/test_keeson_ore_sfm.py::test_write_type_mirrors_android_default |
| B-write | B | transport | Initial queue write of the offered frame | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py write_command -> base _write_gatt_with_retry; tests/test_keeson_ore_sfm.py::test_bedsense_controls_send_the_artifact_frames |
| B-queue | B | transport | Mutable-characteristic queue aliasing, status-blind dequeue, >10 overflow disconnect | EXCLUDED | 2 | Safety constraint: the app's queue stores one mutable characteristic, so delayed writes can carry a later payload, and it disconnects above 10 entries; the integration serializes every GATT write with its own frame (AGENTS command serialization). This is an app defect, not protocol behavior. |
| B-auth | B | session | No authentication, PIN, key exchange or bonding | ALREADY_IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/keeson.py KeesonController has no handshake; tests/test_keeson_ore_sfm.py::test_setup_exposes_each_app_surface_and_cleans_up sets up without one |
| B-discovery-fail | B | session | Discovery-failure guard retained after nonzero status; 129 toast only | EXCLUDED | 1 | Platform boundary: Android scan, connection, permission and lifecycle plumbing; Home Assistant's Bluetooth stack and the coordinator own scanning, connecting, retries and session lifecycle. |
| B-lifecycle | B | session | Screen-off/onStop (stale com.ore.sfm2 names) disconnects; destroy cancels without STOP | EXCLUDED | 1 | Platform boundary: Android scan, connection, permission and lifecycle plumbing; Home Assistant's Bluetooth stack and the coordinator own scanning, connecting, retries and session lifecycle. |
| B-scan | B | discovery | Unfiltered 5 s legacy scan; user picks an address | EXCLUDED | 8 | App UI identity flow: Home Assistant discovers by advertisement and connects to the configured address. With no name/service filter the profile is manual-only (tests/test_keeson_ore_sfm.py::test_profiles_are_selected_only_explicitly). |
| B-connect | B | session | One GATT, autoConnect false, saved-address/resume/touch reconnect | EXCLUDED | 22 | Platform boundary: Android scan, connection, permission and lifecycle plumbing; Home Assistant's Bluetooth stack and the coordinator own scanning, connecting, retries and session lifecycle. |
| B-host-toggle | B | platform | Phone Bluetooth adapter enable/disable menu | EXCLUDED | 2 | Platform boundary: phone adapter administration, no bed frame; Home Assistant owns its adapters. |
| B-permission | B | platform | Target 21, no runtime location request | EXCLUDED | 1 | Platform boundary: Android scan, connection, permission and lifecycle plumbing; Home Assistant's Bluetooth stack and the coordinator own scanning, connecting, retries and session lifecycle. |
| B-alias | B | configuration | Saved address and per-address local display alias | EXCLUDED | 1 | App UI identity flow: Home Assistant discovers by advertisement and connects to the configured address. The alias editor sends no frame. |
| B-settings | B | configuration | Haptic feedback and inert actuator/installation switches | EXCLUDED | 13 | Unrelated to bed integration: third-party or phone-local code with no bed protocol effect. Only phone vibration changes; no packet or capability effect. |
| B-rename-closure | B | configuration | No device rename builder in this app | IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py supports_device_rename False for Bedsense; tests/test_keeson_ore_sfm.py::test_rename_writes_once_on_ffe9 |
| B-bedding2 | B | variant | Manual 2M layout (bedding2) | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py motor count 2 selects the layout's covers; tests/test_keeson_ore_sfm.py::test_motor_count_selects_the_app_layout |
| B-bedding3 | B | variant | Manual 3M layout (bedding3) | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py motor count 3 selects the layout's covers; tests/test_keeson_ore_sfm.py::test_motor_count_selects_the_app_layout |
| B-bedding4 | B | variant | Manual 4M layout (bedding4) | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py motor count 4 selects the layout's covers; tests/test_keeson_ore_sfm.py::test_motor_count_selects_the_app_layout |
| B-dead-selectors | B | dead | Unknown-selector fallback and dormant `others` branch (500 ms) | EXCLUDED | 6 | Dead artifact code: no reachable selector, caller or listener-to-write chain in this package. |
| B-dead-resources | B | dead | Unused sofa/others layouts and sav/M1-M4 labels | EXCLUDED | 9 | Dead artifact code: no reachable selector, caller or listener-to-write chain in this package. |
| B-capability | B | capability | Layout chosen manually; no model, firmware or feature-bit route | IMPLEMENTED | 1 | const.py KEESON_VARIANT_BEDSENSE_BASES, controller_factory.py explicit branch, actuator_groups.py wizard entry; tests/test_keeson_ore_sfm.py::test_profiles_are_selected_only_explicitly |
| B-capability-negative | B | capability | No anti-snore, TV, lounge, tilt-by-ID, sides, sensors, OTA or queries | IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py capability gates; tests/test_keeson_ore_sfm.py::test_capabilities_are_gated_per_app, tests/test_keeson_ore_sfm.py::test_setup_exposes_each_app_surface_and_cleans_up |
| B-native | B | dead | GIF JNI libraries and UI support libraries | EXCLUDED | 4 | Unrelated to bed integration: third-party or phone-local code with no bed protocol effect. |
| B-reads | B | dead | Read queue never populated; descriptor/RSSI callbacks log only | EXCLUDED | 5 | Dead artifact code: no reachable selector, caller or listener-to-write chain in this package. |
| B-alt-transport | B | dead | No Classic, network/cloud, firmware or second protocol (negative closure) | EXCLUDED | 1 | Dead artifact code: nothing reachable exists to implement. |
| B-ui-motion | B | ui | Motion fragments: hold, release and out-of-bounds cancel | IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py covers per layout with held burst and release; tests/test_keeson_ore_sfm.py::test_setup_exposes_each_app_surface_and_cleans_up |
| B-ui-preset-toggle | B | ui | Preset fragment lastButton: tapping the same preset again sends the zero key | EXCLUDED | 1 | Safety constraint: the zero key itself is IMPLEMENTED as the Stop button (B-cmd-013), but a hidden toggle would make a preset button or automation alternate between recall and stop depending on earlier presses. |
| B-ui-massage | B | ui | Massage fragment: persisted 0-39 sliders (default 10), timer label cycle, start/stop | IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py levels default to 1, number entities 0-3, timer select, start/off; tests/test_keeson_ore_sfm.py::test_bedsense_massage_buckets_start_and_stop |
| B-ui-light | B | ui | Light fragment: local isLightOn chooses on or off frame | IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py lights_toggle uses local state; tests/test_keeson_ore_sfm.py::test_bedsense_light_toggle_follows_local_state |
| S-cmd-001 | S | command | 4M back up `0x00000001` held | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Back cover; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-002 | S | command | 4M foot up `0x00000004` held | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Legs cover; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-003 | S | command | 4M back down `0x00000002` held | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Back cover; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-004 | S | command | 4M foot down `0x00000008` held | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Legs cover; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-005 | S | command | Light button `0x00020000` on UP | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Toggle light button -> lights_toggle; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-006 | S | command | Head massage + `0x00000800` | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Head massage up button; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-007 | S | command | Massage-page timer `0x00000200` once | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Massage: Timer button -> massage_mode_step; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-008 | S | command | Foot massage + `0x00000400` | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Foot massage up button; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-009 | S | command | Head massage - `0x00800000` | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Head massage down button; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-010 | S | command | Massage level/pattern `0x00000100` | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Massage level button (ore_sfm_massage_level); tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-011 | S | command | Foot massage - `0x01000000` | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Foot massage down button; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-012 | S | command | Memory-page timer `0x00000200` held, zero on release | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Massage timer (memory page) button (ore_sfm_massage_timer_hold); tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-013 | S | command | ZG `0x00001000` once on DOWN | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Zero G button; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-014 | S | command | Flat `0x08000000` once on DOWN | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Flat button; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-015 | S | command | Memory A `0x00002000` held, zero on release | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Memory 1 button -> preset_memory(1) held burst; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-016 | S | command | Memory B `0x00004000` held, zero on release | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Memory 2 button -> preset_memory(2) held burst; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-017 | S | command | 2M back up `0x00000001` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Back cover; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-018 | S | command | 2M foot up `0x00000004` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Legs cover; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-019 | S | command | 2M back down `0x00000002` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Back cover; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-020 | S | command | 2M foot down `0x00000008` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Legs cover; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-021 | S | command | 2M combined up `0x00000005` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Back + Legs cover -> move_union_up; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-022 | S | command | 2M combined down `0x0000000A` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Back + Legs cover -> move_union_down; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-023 | S | command | 3M back up `0x00000001` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Back cover; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-024 | S | command | 3M foot up `0x00000004` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Legs cover; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-025 | S | command | 3M back down `0x00000002` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Back cover; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-026 | S | command | 3M foot down `0x00000008` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Legs cover; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-027 | S | command | 3M third actuator up `0x00000040` (bedLumbar) | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Lumbar cover (motor count 3); tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-028 | S | command | 3M third actuator down `0x00000080` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Lumbar cover; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-029 | S | command | 4M lumbar up `0x00000040` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Lumbar cover (motor count 4); tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-030 | S | command | 4M lumbar down `0x00000080` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Lumbar cover; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-031 | S | command | 4M waist up `0x00000010` (bedWaist) | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Waist cover (motor count 4); tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-032 | S | command | 4M waist down `0x00000020` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py Waist cover; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-033 | S | command | Zero key `0x00000000` release | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py _release_motion and Stop button; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-034 | S | command | Rename `EF 02` 18-byte frame | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py innova_rename action -> rename_device; tests/test_keeson_ore_sfm.py::test_rename_frames_match_the_report, tests/test_keeson_ore_sfm.py::test_rename_writes_once_on_ffe9, tests/test_keeson_ore_sfm.py::test_innova_rename_service |
| S-builder | S | builder | F(key) = E5 FE 16 + key little-endian + complemented additive checksum | IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py ore_sfm_frame(big_endian=False); tests/test_keeson_ore_sfm.py::test_builders_match_the_report_byte_order |
| S-builder-rename | S | builder | Rename: EF 02, copy String.length() bytes of getBytes(), byte 17 checksum | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py innova_rename_frame (UTF-8, Android's default charset); tests/test_keeson_ore_sfm.py::test_rename_frames_match_the_report |
| S-replies | S | parser | Only 16- and 19-byte FFE4 values; no header, checksum or reassembly | IMPLEMENTED | 7 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py parse_innova_status; tests/test_keeson_ore_sfm.py::test_innova_parser_ignores_other_lengths |
| S-parser | S | parser | Flags byte 13/14: bit 5 suppresses, bit 6 lamp; signed timer 14/15: -1 none, 1/2/3 = 10/20/30, else unchanged | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py parse_innova_status; Light binary sensor and Massage timer sensor (both indicators always shown, while the app routes each to its own page); tests/test_keeson_ore_sfm.py::test_innova_parser_branches, tests/test_keeson_ore_sfm.py::test_innova_notifications_publish_and_clear |
| S-state-routing | S | capability | Lamp bit drives the light page; timer drives memory/massage indicators | IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py controller_state_*_specs, invalidate_diagnostics clears at session end; frontend discovery.ts innova_light; tests/test_keeson_ore_sfm.py::test_innova_notifications_publish_and_clear, tests/test_keeson_ore_sfm.py::test_setup_exposes_each_app_surface_and_cleans_up |
| S-timing | S | timing | Held keys at 0 ms then every 100 ms; single sends sleep 100 ms first; dead others 500 ms | IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py default (10, 100) burst, _send_singles; tests/test_keeson_ore_sfm.py::test_hold_timing_and_single_send_delay |
| S-release | S | release | UP/outside (and CANCEL where handled): cancel refresh, zero key 100 ms later | IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py _release_motion with a fresh asyncio.Event; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-gatt | S | transport | FFE9 write and FFE4 notify by UUID; both required; inherited write type; local notify | IMPLEMENTED | 9 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py fixed FFE9, _require_roles, _refresh_write_mode, start_notify on FFE4 (Home Assistant must write the CCCD to receive the replies the app parses); tests/test_keeson_ore_sfm.py::test_both_roles_are_required_like_the_app, tests/test_keeson_ore_sfm.py::test_write_type_mirrors_android_default, tests/test_keeson_ore_sfm.py::test_failed_subscription_does_not_block_control |
| S-write | S | transport | Initial queue write of the offered frame | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py write_command -> base _write_gatt_with_retry; tests/test_keeson_ore_sfm.py::test_innova_controls_send_the_artifact_frames |
| S-queue | S | transport | Mutable-characteristic queue aliasing, status-blind dequeue, >10 overflow disconnect | EXCLUDED | 2 | Safety constraint: the app's queue stores one mutable characteristic, so delayed writes can carry a later payload, and it disconnects above 10 entries; the integration serializes every GATT write with its own frame (AGENTS command serialization). This is an app defect, not protocol behavior. |
| S-auth | S | session | No authentication, PIN, key exchange or bonding | ALREADY_IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/keeson.py KeesonController has no handshake; tests/test_keeson_ore_sfm.py::test_setup_exposes_each_app_surface_and_cleans_up sets up without one |
| S-discovery-fail | S | session | Discovery-failure guard retained after nonzero status; 129 toast only | EXCLUDED | 2 | Platform boundary: Android scan, connection, permission and lifecycle plumbing; Home Assistant's Bluetooth stack and the coordinator own scanning, connecting, retries and session lifecycle. |
| S-lifecycle | S | session | Screen-off disconnects; onStop keeps Main/Options/About; destroy cancels without STOP | EXCLUDED | 1 | Platform boundary: Android scan, connection, permission and lifecycle plumbing; Home Assistant's Bluetooth stack and the coordinator own scanning, connecting, retries and session lifecycle. |
| S-scan | S | discovery | Unfiltered 5 s legacy scan; user picks an address | EXCLUDED | 11 | App UI identity flow: Home Assistant discovers by advertisement and connects to the configured address. With no name/service filter the profile is manual-only (tests/test_keeson_ore_sfm.py::test_profiles_are_selected_only_explicitly). |
| S-connect | S | session | One GATT, autoConnect false, adapter checks, saved-address/resume/touch reconnect | EXCLUDED | 23 | Platform boundary: Android scan, connection, permission and lifecycle plumbing; Home Assistant's Bluetooth stack and the coordinator own scanning, connecting, retries and session lifecycle. |
| S-host-toggle | S | platform | Phone Bluetooth adapter enable/disable menu (T14) | EXCLUDED | 3 | Platform boundary: phone adapter administration, no bed frame; Home Assistant owns its adapters. |
| S-permission | S | platform | Target 24 coarse/fine location request and denial dialog | EXCLUDED | 1 | Platform boundary: Android scan, connection, permission and lifecycle plumbing; Home Assistant's Bluetooth stack and the coordinator own scanning, connecting, retries and session lifecycle. |
| S-rename-editor | S | configuration | Options editor: connected, trimmed, non-empty, max 14 UTF-16 units, sends once, stores last_connected_device | IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py validate_innova_name, rename_device; services.py handle_innova_rename validates every target first (the stored phone-side name is app UI identity); tests/test_keeson_ore_sfm.py::test_innova_rename_service |
| S-settings | S | configuration | Haptic feedback switch; inert actuator/installation fields | EXCLUDED | 11 | Unrelated to bed integration: third-party or phone-local code with no bed protocol effect. Only phone vibration changes; no packet or capability effect. |
| S-receiver | S | platform | isBroadcast receiver-registration flag | EXCLUDED | 2 | Platform boundary: Android scan, connection, permission and lifecycle plumbing; Home Assistant's Bluetooth stack and the coordinator own scanning, connecting, retries and session lifecycle. |
| S-bedding2 | S | variant | Manual 2M layout (bedding2) | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py motor count 2 selects the layout's covers; tests/test_keeson_ore_sfm.py::test_motor_count_selects_the_app_layout |
| S-bedding3 | S | variant | Manual 3M layout (bedding3) | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py motor count 3 selects the layout's covers; tests/test_keeson_ore_sfm.py::test_motor_count_selects_the_app_layout |
| S-bedding4 | S | variant | Manual 4M layout (bedding4) | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py motor count 4 selects the layout's covers; tests/test_keeson_ore_sfm.py::test_motor_count_selects_the_app_layout |
| S-dead-selectors | S | dead | Adapter-default fallback and dormant `others` branch (500 ms, init key) | EXCLUDED | 5 | Dead artifact code: no reachable selector, caller or listener-to-write chain in this package. |
| S-dead-resources | S | dead | Unused sofa/others layouts and sav/M1-M4 labels (no save command) | EXCLUDED | 3 | Dead artifact code: no reachable selector, caller or listener-to-write chain in this package. |
| S-capability | S | capability | Layout chosen manually; no model, firmware or feature-bit route | IMPLEMENTED | 2 | const.py KEESON_VARIANT_INNOVA, controller_factory.py explicit branch, actuator_groups.py wizard entry; tests/test_keeson_ore_sfm.py::test_profiles_are_selected_only_explicitly |
| S-capability-negative | S | capability | No memory save, massage off/absolute levels, anti-snore, TV, lounge, sides, sensors, OTA or queries | IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/keeson_ore_sfm.py capability gates; tests/test_keeson_ore_sfm.py::test_capabilities_are_gated_per_app, tests/test_keeson_ore_sfm.py::test_setup_exposes_each_app_surface_and_cleans_up |
| S-native | S | dead | GIF JNI libraries and UI support libraries | EXCLUDED | 4 | Unrelated to bed integration: third-party or phone-local code with no bed protocol effect. |
| S-reads | S | dead | Read queue never populated; descriptor/RSSI callbacks log only | EXCLUDED | 7 | Dead artifact code: no reachable selector, caller or listener-to-write chain in this package. |
| S-alt-transport | S | dead | No Classic, network/cloud, firmware or second protocol (negative closure) | EXCLUDED | 1 | Dead artifact code: nothing reachable exists to implement. |

## Deferred hardware validation

For real users after beta or release: confirm the physical actuator behind each 2M/3M/4M key
(INNOVA's 3M third motor uses lumbar IDs beside head artwork); the zero key's stop scope;
Bedsense save behavior; whether held INNOVA memory recall needs a longer hold than one motor
burst; massage level limits and timer cycling; the INNOVA lamp-bit meaning; notification
delivery once Home Assistant writes the FFE4 CCCD the apps never write; and non-ASCII rename
results.
