# Row059: Bedsense Bases and INNOVA app dispositions

Formal cluster `cluster-015` has two accepted members: `com.ore.sfmc2bedsence` 1.1 (3)
("Bedsense Bases", representative) and `com.ore.sfm` 2.0 (3) ("INNOVA", sibling). The
comparison accounts for **126 discovery items: 50 IMPLEMENTED, 48
ALREADY_IMPLEMENTED, 28 EXCLUDED**. Hardware is unverified (STATIC VERIFIED /
HARDWARE UNVERIFIED).

The public contracts are the [MaxCoil Una / Dynasty Bases / Bedsense Bases profile](../../beds/ore-comfort-bed.md)
and the [INNOVA profile](../../beds/keeson.md#innova-profile). The reconciliation found the two
apps materially different in packets, framing, timing, parsing and capabilities, so they use
separate controllers. Bedsense Bases' accepted report is byte-identical to the ORE comfort-bed
profile of formal cluster-013 (MaxCoil Una / Dynasty Bases): big-endian keys, the same 2M/3M/4M
screens, presets, saves, absolute massage levels, timer words, light words, 100 ms timing,
delayed zero-key release and discarded 9-byte replies. Bedsense is therefore a registry entry
of `OreComfortBedController`, and its behavior rows are ALREADY_IMPLEMENTED with Bedsense
report vectors as proof. INNOVA uses little-endian standard Keeson keys, held memory recall,
relative massage, a rename frame and 16/19-byte state notifications, implemented by the new
`InnovaController`. Neither app filters its scan, so both are explicit profiles that Auto never
selects; the motor count selects the app's 2M/3M/4M screen.

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

- Bedsense Bases joins `OreComfortBedController` (`beds/ore_comfort_bed.py`) as the
  `bedsense_bases` registry entry, with the per-side profile guard and a setup wizard entry. It
  gets the existing covers, presets, Save buttons, persisted massage levels, 10/20/30 timer
  select, assumed-state light switch and never-suppressed release.
- New explicit Keeson variant `innova` (`beds/innova.py`, setup wizard and options). Auto,
  Sino and every other profile keep their behavior. The Sino label and comments no longer name
  INNOVA, whose accepted app uses little-endian frames.
- INNOVA: motor count 2/3/4 selects Back, Legs plus Back + Legs (2M), Lumbar (3M) or Waist and
  Lumbar (4M). Held keys refresh every 100 ms; release writes the zero key 100 ms later, at once
  for a Stop, cancellation or replacement, shielded on a fresh event. One-shot writes sleep
  100 ms first. Memory A/B and the memory-page timer are held; `innova_hold_control` holds any
  streamed control for 0.1-60 s. Relative massage steps, Massage level and Massage: Timer
  buttons, a light toggle, the `innova_rename` action, and FFE4 Light / Massage timer states
  that clear when the connection ends.
- INNOVA writes to and subscribes the last FFE9 and FFE4 found across services, as the app
  does, requires both and mirrors Android's inherited write type. Changing profile or bed
  type removes the profile's covers, buttons and states.
- The `okin_ore` bed type is now labelled "Okin ORE (Glideaway Motion app)": the accepted
  Dynasty Bases and INNOVA reports prove both apps use only the `E5 FE 16` frame, so docs
  point their users to the Keeson app profiles. Its key and behavior are unchanged.

## Totals

| Disposition | Count |
|---|---|
| IMPLEMENTED | 50 |
| ALREADY_IMPLEMENTED | 48 |
| EXCLUDED | 28 |
| Total | 126 |

| Exclusion reason | Count |
|---|---|
| App UI identity flow | 3 |
| Dead artifact code | 8 |
| Platform boundary | 11 |
| Safety constraint | 2 |
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
| B-cmd-001 | B | command | Back up `0x00000001` held | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Back cover -> _move_axis('back'); tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-002 | B | command | Back down `0x00000002` held | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Back cover -> _move_axis('back'); tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-003 | B | command | Foot up `0x00000004` held | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Feet cover -> _move_axis('feet'); tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-004 | B | command | Foot down `0x00000008` held | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Feet cover -> _move_axis('feet'); tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-005 | B | command | 2M combined up `0x00000010` held | ALREADY_IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Back and legs cover (motor count 2); tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-006 | B | command | 2M combined down `0x00000020` held | ALREADY_IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Back and legs cover; tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-007 | B | command | 3M head up `0x00000010` held | ALREADY_IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Head cover (motor count 3); tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-008 | B | command | 3M head down `0x00000020` held | ALREADY_IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Head cover; tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-009 | B | command | 4M waist up `0x00000010` held | ALREADY_IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Waist cover (motor count 4); tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-010 | B | command | 4M waist down `0x00000020` held | ALREADY_IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Waist cover; tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-011 | B | command | 4M lumbar up `0x00000040` held | ALREADY_IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Lumbar cover (motor count 4); tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-012 | B | command | 4M lumbar down `0x00000080` held | ALREADY_IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Lumbar cover; tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-013 | B | command | Zero key `0x00000000`: movement release and repeated-preset stop | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: _send_release (fresh event, never suppressed) and the Stop button; tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller; tests/test_ore_comfort_bed.py::test_release_is_sent_even_when_the_hold_was_cancelled |
| B-cmd-014 | B | command | Zero G recall `0x01000001` | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Zero G button; tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-015 | B | command | Zero G program `0x20000001` (long-click) | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Save Zero G button (ore_comfort_program_zero_g); tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-016 | B | command | Flat recall `0x01000002` | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Flat button; tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-017 | B | command | Flat program `0x20000002` (long-click) | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Save Flat button (ore_comfort_program_flat); tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-018 | B | command | Memory A recall `0x01000008` | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Memory A button; tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-019 | B | command | Memory A program `0x20000008` | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Save Memory A; tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-020 | B | command | Memory B recall `0x01000009` | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Memory B button; tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-021 | B | command | Memory B program `0x20000009` | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Save Memory B; tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-022 | B | command | Wave `0x10000020 + floor(progress/10)`, buckets 0-3 | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Wave number 0-3 -> set_massage_level; tests/test_innova.py::test_bedsense_massage_report_vectors |
| B-cmd-023 | B | command | Head massage `0x10000010 + n`, buckets 0-3 | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Head number 0-3; tests/test_innova.py::test_bedsense_massage_report_vectors |
| B-cmd-024 | B | command | Foot massage `0x11000010 + n`, buckets 0-3 | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Foot number 0-3; tests/test_innova.py::test_bedsense_massage_report_vectors |
| B-cmd-025 | B | command | Massage start: wave, head, foot at current levels | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Start massage button; tests/test_innova.py::test_bedsense_massage_report_vectors |
| B-cmd-026 | B | command | Massage stop: head 0 then foot 0; timer label reset | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Massage off -> massage_off; tests/test_innova.py::test_bedsense_massage_report_vectors |
| B-cmd-027 | B | command | Massage timer 10 min `0x10000030` | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Massage timer select (10/20/30, no Off); tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-028 | B | command | Massage timer 20 min `0x10000031` | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Massage timer select; tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-029 | B | command | Massage timer 30 min `0x10000032` | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Massage timer select; tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-030 | B | command | Light on `0x31000001` | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Under-bed light switch (assumed state) -> lights_on; tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-cmd-031 | B | command | Light off `0x31000000` | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py OreComfortBedController (056) with the Bedsense Bases ORE_COMFORT_BED_APPS entry; byte-identical to the Bedsense report: Under-bed light switch -> lights_off; tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-builder | B | builder | F(key) = E5 FE 16 + key big-endian + complemented additive checksum | ALREADY_IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/ore_comfort_bed.py build_frame; tests/test_ore_comfort_bed.py::test_builder_reproduces_every_report_vector, tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-replies | B | parser | Nonempty FFE4 values; only length 9 accepted; byte 7 split into bits and discarded | ALREADY_IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/ore_comfort_bed.py start_notify is a no-op and publishes no reply state (local enable writes no CCCD, replies drive nothing); tests/test_ore_comfort_bed.py::test_notifications_are_never_subscribed |
| B-timing | B | timing | Held keys at 0 ms then every 100 ms; single sends sleep 100 ms first; dead others 500 ms | ALREADY_IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/ore_comfort_bed.py _hold at HOLD_INTERVAL_MS, _send_single; tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero, tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once |
| B-release | B | release | UP/CANCEL/outside: cancel refresh, then zero key 100 ms later; no physical STOP guarantee | ALREADY_IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/ore_comfort_bed.py _send_release in finally with a fresh asyncio.Event; tests/test_ore_comfort_bed.py::test_release_is_sent_even_when_the_hold_was_cancelled |
| B-gatt | B | transport | FFE9 write and FFE4 notify by UUID across all services; both required; inherited write type | ALREADY_IMPLEMENTED | 9 | custom_components/adjustable_bed/beds/ore_comfort_bed.py _resolve_write_characteristic; tests/test_ore_comfort_bed.py::test_write_roles_follow_the_app_scan |
| B-write | B | transport | Initial queue write of the offered frame | ALREADY_IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/ore_comfort_bed.py write_command; tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-queue | B | transport | Mutable-characteristic queue aliasing, status-blind dequeue, >10 overflow disconnect | EXCLUDED | 2 | Safety constraint: the app's queue stores one mutable characteristic, so delayed writes can carry a later payload, and it disconnects above 10 entries; the integration serializes every GATT write with its own frame (AGENTS command serialization). This is an app defect, not protocol behavior. |
| B-auth | B | session | No authentication, PIN, key exchange or bonding | ALREADY_IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/ore_comfort_bed.py has no handshake; tests/test_ore_comfort_bed.py::test_setup_exposes_the_app_surface, tests/test_innova.py::test_setup_exposes_each_app_surface_and_cleans_up |
| B-discovery-fail | B | session | Discovery-failure guard retained after nonzero status; 129 toast only | EXCLUDED | 1 | Platform boundary: Android scan, connection, permission and lifecycle plumbing; Home Assistant's Bluetooth stack and the coordinator own scanning, connecting, retries and session lifecycle. |
| B-lifecycle | B | session | Screen-off/onStop (stale com.ore.sfm2 names) disconnects; destroy cancels without STOP | EXCLUDED | 1 | Platform boundary: Android scan, connection, permission and lifecycle plumbing; Home Assistant's Bluetooth stack and the coordinator own scanning, connecting, retries and session lifecycle. |
| B-scan | B | discovery | Unfiltered 5 s legacy scan; user picks an address | EXCLUDED | 8 | App UI identity flow: Home Assistant discovers by advertisement and connects to the configured address. With no name/service filter the profile is manual-only (tests/test_ore_comfort_bed.py::test_profile_is_explicit_and_auto_keeps_keeson[bedsense_bases]). |
| B-connect | B | session | One GATT, autoConnect false, saved-address/resume/touch reconnect | EXCLUDED | 22 | Platform boundary: Android scan, connection, permission and lifecycle plumbing; Home Assistant's Bluetooth stack and the coordinator own scanning, connecting, retries and session lifecycle. |
| B-host-toggle | B | platform | Phone Bluetooth adapter enable/disable menu | EXCLUDED | 2 | Platform boundary: phone adapter administration, no bed frame; Home Assistant owns its adapters. |
| B-permission | B | platform | Target 21, no runtime location request | EXCLUDED | 1 | Platform boundary: Android scan, connection, permission and lifecycle plumbing; Home Assistant's Bluetooth stack and the coordinator own scanning, connecting, retries and session lifecycle. |
| B-alias | B | configuration | Saved address and per-address local display alias | EXCLUDED | 1 | App UI identity flow: Home Assistant discovers by advertisement and connects to the configured address. The alias editor sends no frame. |
| B-settings | B | configuration | Haptic feedback and inert actuator/installation switches | EXCLUDED | 13 | Unrelated to bed integration: third-party or phone-local code with no bed protocol effect. Only phone vibration changes; no packet or capability effect. |
| B-rename-closure | B | configuration | No device rename builder in this app | ALREADY_IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/ore_comfort_bed.py exposes no rename (supports_device_rename False); tests/test_innova.py::test_innova_rename_service rejects Bedsense |
| B-bedding2 | B | variant | Manual 2M layout (bedding2) | ALREADY_IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/ore_comfort_bed.py LAYOUTS[2] chosen by the motor count; tests/test_ore_comfort_bed.py::test_motor_count_selects_the_app_screen[2-keys0-bedsense_bases] |
| B-bedding3 | B | variant | Manual 3M layout (bedding3) | ALREADY_IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/ore_comfort_bed.py LAYOUTS[3] chosen by the motor count; tests/test_ore_comfort_bed.py::test_motor_count_selects_the_app_screen[3-keys1-bedsense_bases] |
| B-bedding4 | B | variant | Manual 4M layout (bedding4) | ALREADY_IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/ore_comfort_bed.py LAYOUTS[4] chosen by the motor count; tests/test_ore_comfort_bed.py::test_motor_count_selects_the_app_screen[4-keys2-bedsense_bases] |
| B-dead-selectors | B | dead | Unknown-selector fallback and dormant `others` branch (500 ms) | EXCLUDED | 6 | Dead artifact code: no reachable selector, caller or listener-to-write chain in this package. |
| B-dead-resources | B | dead | Unused sofa/others layouts and sav/M1-M4 labels | EXCLUDED | 9 | Dead artifact code: no reachable selector, caller or listener-to-write chain in this package. |
| B-capability | B | capability | Layout chosen manually; no model, firmware or feature-bit route | IMPLEMENTED | 1 | const.py KEESON_VARIANT_BEDSENSE_BASES in ORE_COMFORT_BED_VARIANTS, custom_components/adjustable_bed/beds/ore_comfort_bed.py ORE_COMFORT_BED_APPS entry, config_flow.py _PER_SIDE_APP_PROFILES guard, actuator_groups.py wizard entry; tests/test_innova.py::test_profiles_are_selected_only_explicitly, tests/test_ore_comfort_bed.py::test_profile_is_explicit_and_auto_keeps_keeson |
| B-capability-negative | B | capability | No anti-snore, TV, lounge, sides, sensors, OTA or queries | ALREADY_IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/ore_comfort_bed.py exposes only the app surface; tests/test_ore_comfort_bed.py::test_setup_exposes_the_app_surface, tests/test_innova.py::test_setup_exposes_each_app_surface_and_cleans_up |
| B-native | B | dead | GIF JNI libraries and UI support libraries | EXCLUDED | 4 | Unrelated to bed integration: third-party or phone-local code with no bed protocol effect. |
| B-reads | B | dead | Read queue never populated; descriptor/RSSI callbacks log only | EXCLUDED | 5 | Dead artifact code: no reachable selector, caller or listener-to-write chain in this package. |
| B-alt-transport | B | dead | No Classic, network/cloud, firmware or second protocol (negative closure) | EXCLUDED | 1 | Dead artifact code: nothing reachable exists to implement. |
| B-ui-motion | B | ui | Motion fragments: hold, release and out-of-bounds cancel | ALREADY_IMPLEMENTED | 4 | custom_components/adjustable_bed/beds/ore_comfort_bed.py covers per screen with held burst and release, one global key (scheduler resource *); tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero |
| B-ui-preset-toggle | B | ui | Preset fragment lastButton: tapping the same preset again sends the zero key | ALREADY_IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/ore_comfort_bed.py stop_all sends the same zero word as the Stop button, as row056 L19 resolves this behavior; preset buttons always recall, so a preset or automation never alternates between recall and stop; tests/test_ore_comfort_bed.py::test_release_is_sent_even_when_the_hold_was_cancelled, tests/test_innova.py::test_bedsense_report_vectors_on_the_ore_comfort_controller |
| B-ui-massage | B | ui | Massage fragment: persisted 0-39 sliders (default 10), timer label cycle, start/stop | ALREADY_IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/ore_comfort_bed.py levels default to 1 and persist per entry through app_state_store; ore_comfort_massage_timer select; tests/test_ore_comfort_bed.py::test_slider_levels_persist_across_restarts, tests/test_ore_comfort_bed.py::test_massage_levels_timer_and_stop_publish_app_state |
| B-ui-light | B | ui | Light fragment: local isLightOn chooses on or off frame | ALREADY_IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/ore_comfort_bed.py discrete on/off with assumed state; tests/test_ore_comfort_bed.py::test_light_switch_reports_assumed_state |
| S-cmd-001 | S | command | 4M back up `0x00000001` held | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Back cover; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-002 | S | command | 4M foot up `0x00000004` held | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Legs cover; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-003 | S | command | 4M back down `0x00000002` held | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Back cover; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-004 | S | command | 4M foot down `0x00000008` held | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Legs cover; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-005 | S | command | Light button `0x00020000` on UP | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/innova.py Toggle light button -> lights_toggle; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-006 | S | command | Head massage + `0x00000800` | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/innova.py Head massage up button; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-007 | S | command | Massage-page timer `0x00000200` once | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/innova.py Massage: Timer button -> massage_mode_step; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-008 | S | command | Foot massage + `0x00000400` | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/innova.py Foot massage up button; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-009 | S | command | Head massage - `0x00800000` | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/innova.py Head massage down button; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-010 | S | command | Massage level/pattern `0x00000100` | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/innova.py Massage level button (innova_massage_level); tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-011 | S | command | Foot massage - `0x01000000` | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/innova.py Foot massage down button; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-012 | S | command | Memory-page timer `0x00000200` held, zero on release | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/innova.py Massage timer (memory page) button and innova_hold_control memory_timer; tests/test_innova.py::test_innova_controls_send_the_artifact_frames, tests/test_innova.py::test_hold_control_streams_for_the_duration, tests/test_innova.py::test_innova_hold_control_service |
| S-cmd-013 | S | command | ZG `0x00001000` once on DOWN | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/innova.py Zero G button; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-014 | S | command | Flat `0x08000000` once on DOWN | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/innova.py Flat button; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-015 | S | command | Memory A `0x00002000` held, zero on release | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/innova.py Memory A button and innova_hold_control memory_a; tests/test_innova.py::test_innova_controls_send_the_artifact_frames, tests/test_innova.py::test_hold_control_streams_for_the_duration, tests/test_innova.py::test_innova_hold_control_service |
| S-cmd-016 | S | command | Memory B `0x00004000` held, zero on release | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/innova.py Memory B button and innova_hold_control memory_b; tests/test_innova.py::test_innova_controls_send_the_artifact_frames, tests/test_innova.py::test_hold_control_streams_for_the_duration, tests/test_innova.py::test_innova_hold_control_service |
| S-cmd-017 | S | command | 2M back up `0x00000001` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Back cover; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-018 | S | command | 2M foot up `0x00000004` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Legs cover; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-019 | S | command | 2M back down `0x00000002` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Back cover; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-020 | S | command | 2M foot down `0x00000008` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Legs cover; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-021 | S | command | 2M combined up `0x00000005` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Back + Legs cover and innova_hold_control combined_up; tests/test_innova.py::test_innova_controls_send_the_artifact_frames, tests/test_innova.py::test_hold_control_streams_for_the_duration, tests/test_innova.py::test_innova_hold_control_service |
| S-cmd-022 | S | command | 2M combined down `0x0000000A` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Back + Legs cover and combined_down; tests/test_innova.py::test_innova_controls_send_the_artifact_frames, tests/test_innova.py::test_hold_control_streams_for_the_duration, tests/test_innova.py::test_innova_hold_control_service |
| S-cmd-023 | S | command | 3M back up `0x00000001` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Back cover; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-024 | S | command | 3M foot up `0x00000004` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Legs cover; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-025 | S | command | 3M back down `0x00000002` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Back cover; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-026 | S | command | 3M foot down `0x00000008` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Legs cover; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-027 | S | command | 3M third actuator up `0x00000040` (bedLumbar) | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Lumbar cover (motor count 3); tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-028 | S | command | 3M third actuator down `0x00000080` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Lumbar cover; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-029 | S | command | 4M lumbar up `0x00000040` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Lumbar cover (motor count 4); tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-030 | S | command | 4M lumbar down `0x00000080` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Lumbar cover; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-031 | S | command | 4M waist up `0x00000010` (bedWaist) | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Waist cover (motor count 4); tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-032 | S | command | 4M waist down `0x00000020` | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py Waist cover; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-cmd-033 | S | command | Zero key `0x00000000` release | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/innova.py _release (shielded, fresh event) and Stop button; tests/test_innova.py::test_innova_controls_send_the_artifact_frames, tests/test_innova.py::test_stop_sends_the_zero_key_at_once |
| S-cmd-034 | S | command | Rename `EF 02` 18-byte frame | IMPLEMENTED | 5 | custom_components/adjustable_bed/beds/innova.py innova_rename action -> rename_device; tests/test_innova.py::test_rename_frames_match_the_report, tests/test_innova.py::test_rename_writes_once_on_ffe9, tests/test_innova.py::test_innova_rename_service |
| S-builder | S | builder | F(key) = E5 FE 16 + key little-endian + complemented additive checksum | IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/innova.py innova_frame; tests/test_innova.py::test_innova_builder_is_little_endian |
| S-builder-rename | S | builder | Rename: EF 02, copy String.length() bytes of getBytes(), byte 17 checksum | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/innova.py innova_rename_frame (UTF-8, Android's default charset); tests/test_innova.py::test_rename_frames_match_the_report |
| S-replies | S | parser | Only 16- and 19-byte FFE4 values; no header, checksum or reassembly | IMPLEMENTED | 7 | custom_components/adjustable_bed/beds/innova.py parse_innova_status; tests/test_innova.py::test_parser_ignores_other_lengths |
| S-parser | S | parser | Flags byte 13/14: bit 5 suppresses, bit 6 lamp; signed timer 14/15: -1 none, 1/2/3 = 10/20/30, else unchanged | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/innova.py parse_innova_status; Light binary sensor and Massage timer sensor (both indicators always shown, while the app routes each to its own page); tests/test_innova.py::test_parser_branches, tests/test_innova.py::test_notifications_publish_and_clear |
| S-state-routing | S | capability | Lamp bit drives the light page; timer drives memory/massage indicators | IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/innova.py controller_state_*_specs, invalidate_diagnostics clears at session end; frontend discovery.ts innova_light; tests/test_innova.py::test_notifications_publish_and_clear, tests/test_innova.py::test_setup_exposes_each_app_surface_and_cleans_up |
| S-timing | S | timing | Held keys at 0 ms then every 100 ms; single sends sleep 100 ms first; dead others 500 ms | IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/innova.py HOLD_INTERVAL_MS, _send_singles; keeson.py _APP_MOTOR_PULSE_DEFAULTS innova (10, 100); tests/test_innova.py::test_hold_timing_and_single_send_delay |
| S-release | S | release | UP/outside (and CANCEL where handled): cancel refresh, zero key 100 ms later | IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/innova.py _release: 100 ms wait ended by Stop, immediate when cancelled, shielded write on a fresh asyncio.Event awaited through any number of cancellations; tests/test_innova.py::test_cancelling_mid_release_still_writes_the_zero_key, tests/test_innova.py::test_release_write_survives_repeated_cancellations, tests/test_innova.py::test_a_stop_during_the_hold_releases_immediately |
| S-gatt | S | transport | FFE9 write and FFE4 notify by UUID; both required; inherited write type; local notify | IMPLEMENTED | 9 | custom_components/adjustable_bed/beds/innova.py _resolve_roles keeps the last FFE9 and last FFE4 per connection and writes/subscribes to those objects, requires both, mirrors the inherited write type; start_notify on that FFE4 (Home Assistant must write the CCCD to receive the replies the app parses); tests/test_innova.py::test_duplicate_roles_use_the_last_ffe9_and_ffe4, tests/test_innova.py::test_both_roles_are_required_like_the_app, tests/test_innova.py::test_write_type_mirrors_android_default, tests/test_innova.py::test_failed_subscription_does_not_block_control |
| S-write | S | transport | Initial queue write of the offered frame | IMPLEMENTED | 3 | custom_components/adjustable_bed/beds/innova.py write_command -> base _write_gatt_with_retry; tests/test_innova.py::test_innova_controls_send_the_artifact_frames |
| S-queue | S | transport | Mutable-characteristic queue aliasing, status-blind dequeue, >10 overflow disconnect | EXCLUDED | 2 | Safety constraint: the app's queue stores one mutable characteristic, so delayed writes can carry a later payload, and it disconnects above 10 entries; the integration serializes every GATT write with its own frame (AGENTS command serialization). This is an app defect, not protocol behavior. |
| S-auth | S | session | No authentication, PIN, key exchange or bonding | ALREADY_IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/keeson.py KeesonController (InnovaController's base) has no handshake; tests/test_innova.py::test_setup_exposes_each_app_surface_and_cleans_up sets up without one |
| S-discovery-fail | S | session | Discovery-failure guard retained after nonzero status; 129 toast only | EXCLUDED | 2 | Platform boundary: Android scan, connection, permission and lifecycle plumbing; Home Assistant's Bluetooth stack and the coordinator own scanning, connecting, retries and session lifecycle. |
| S-lifecycle | S | session | Screen-off disconnects; onStop keeps Main/Options/About; destroy cancels without STOP | EXCLUDED | 1 | Platform boundary: Android scan, connection, permission and lifecycle plumbing; Home Assistant's Bluetooth stack and the coordinator own scanning, connecting, retries and session lifecycle. |
| S-scan | S | discovery | Unfiltered 5 s legacy scan; user picks an address | EXCLUDED | 11 | App UI identity flow: Home Assistant discovers by advertisement and connects to the configured address. With no name/service filter the profile is manual-only (tests/test_innova.py::test_profiles_are_selected_only_explicitly). |
| S-connect | S | session | One GATT, autoConnect false, adapter checks, saved-address/resume/touch reconnect | EXCLUDED | 23 | Platform boundary: Android scan, connection, permission and lifecycle plumbing; Home Assistant's Bluetooth stack and the coordinator own scanning, connecting, retries and session lifecycle. |
| S-host-toggle | S | platform | Phone Bluetooth adapter enable/disable menu (T14) | EXCLUDED | 3 | Platform boundary: phone adapter administration, no bed frame; Home Assistant owns its adapters. |
| S-permission | S | platform | Target 24 coarse/fine location request and denial dialog | EXCLUDED | 1 | Platform boundary: Android scan, connection, permission and lifecycle plumbing; Home Assistant's Bluetooth stack and the coordinator own scanning, connecting, retries and session lifecycle. |
| S-rename-editor | S | configuration | Options editor: connected, maxLength 14 UTF-16 units, trimmed, non-empty, sends once, stores last_connected_device | IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/innova.py validate_innova_name (limit before trim, as the EditText), rename_device; services.py handle_innova_rename validates every target first (the stored phone-side name is app UI identity); tests/test_innova.py::test_innova_rename_service |
| S-settings | S | configuration | Haptic feedback switch; inert actuator/installation fields | EXCLUDED | 11 | Unrelated to bed integration: third-party or phone-local code with no bed protocol effect. Only phone vibration changes; no packet or capability effect. |
| S-receiver | S | platform | isBroadcast receiver-registration flag | EXCLUDED | 2 | Platform boundary: Android scan, connection, permission and lifecycle plumbing; Home Assistant's Bluetooth stack and the coordinator own scanning, connecting, retries and session lifecycle. |
| S-bedding2 | S | variant | Manual 2M layout (bedding2) | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/innova.py motor count 2 selects the screen's covers and held controls; tests/test_innova.py::test_motor_count_selects_the_app_layout |
| S-bedding3 | S | variant | Manual 3M layout (bedding3) | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/innova.py motor count 3 selects the screen's covers and held controls; tests/test_innova.py::test_motor_count_selects_the_app_layout |
| S-bedding4 | S | variant | Manual 4M layout (bedding4) | IMPLEMENTED | 2 | custom_components/adjustable_bed/beds/innova.py motor count 4 selects the screen's covers and held controls; tests/test_innova.py::test_motor_count_selects_the_app_layout |
| S-dead-selectors | S | dead | Adapter-default fallback and dormant `others` branch (500 ms, init key) | EXCLUDED | 5 | Dead artifact code: no reachable selector, caller or listener-to-write chain in this package. |
| S-dead-resources | S | dead | Unused sofa/others layouts and sav/M1-M4 labels (no save command) | EXCLUDED | 3 | Dead artifact code: no reachable selector, caller or listener-to-write chain in this package. |
| S-capability | S | capability | Layout chosen manually; no model, firmware or feature-bit route | IMPLEMENTED | 2 | const.py KEESON_VARIANT_INNOVA, controller_factory.py explicit branch, actuator_groups.py wizard entry; tests/test_innova.py::test_profiles_are_selected_only_explicitly |
| S-capability-negative | S | capability | No memory save, massage off/absolute levels, anti-snore, TV, lounge, sides, sensors, OTA or queries | IMPLEMENTED | 1 | custom_components/adjustable_bed/beds/innova.py capability gates; tests/test_innova.py::test_innova_capabilities, tests/test_innova.py::test_setup_exposes_each_app_surface_and_cleans_up |
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
