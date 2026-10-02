# Row056: MaxCoil Una / Dynasty Bases app dispositions

Formal cluster-013 covers two apps built on one `com.ore.okincomfortbed` code base: `R` = com.ore.maxcoil 1.1.0 (5) (MaxCoil Una, representative); `D` = com.ore.Dynasty 1.0.2 (3) (Dynasty Bases, sibling). Both package reports and the whole-cluster reconciliation are independently accepted. Status: static verified, hardware unverified.

The comparison maps **441 inventory entries** (all twelve categories, the accepted candidate ledger and the Android Bluetooth callsites of both reachable inventories) onto **35 behavior rows: 23 IMPLEMENTED, 0 ALREADY_IMPLEMENTED, 12 EXCLUDED**. Entries: 191 implemented, 0 already implemented, 250 excluded. The machine-local generator `row056-ledger.py` asserts that the pointer map equals both inventories with no duplicates; `row056-ledger.json` stores it.

## Accepted authority

| Artifact | SHA-256 |
|---|---|
| maxcoil REPORT.SHA256 | `0c852b85d334ce9479170f647cbc3ac570c55b674c1b53cc68583429a95bf0f5` |
| Dynasty REPORT.SHA256 | `9db15b97e5913201eed1acd1298efd4aeabc727971ad0e867f5ab7a6fc0065bb` |
| maxcoil analysis.json | `7a72cf3610342559c137ecac27775ac02176be7a0bb39426a93c692cef87d984` |
| Dynasty analysis.json | `8655e55bfc7e6d187394097c3d2338535529825929192d1205a3ab07787d803f` |
| RECONCILIATION.SHA256 | `085d83764cac2062617e1302a19affe2839a479999839b14c4c073c67d717bbb` |
| representative-reachable-inventory.json | `d59eff60d6700058f351ec4fca7d9ace112228ebd69b3de31047377cd2a3dac6` |
| sibling-1-reachable-inventory.json | `7a6df8c985978fd3eab51d23ee589723f9ae8c01b4b1904ed1c80f7e9ecff2a4` |

## Entries per package

| Package | Implemented | Already implemented | Excluded |
|---|---|---|---|
| com.ore.maxcoil 1.1.0 (5) (MaxCoil Una, representative) | 91 | 0 | 114 |
| com.ore.Dynasty 1.0.2 (3) (Dynasty Bases, sibling) | 100 | 0 | 136 |

Both packages receive the same disposition on every row. The reconciliation's DIFFERENT areas (delivery, launcher and Back navigation, artwork and GIF rendering) send no frame and fall in the excluded UI row.

## What changed

- Two explicit Keeson protocol variants, `maxcoil_una` and `dynasty_bases`, built by a new `OreComfortBedController` (`beds/ore_comfort_bed.py`). An app registry maps both to the shared behavior, so a later sibling app of this code base adds one entry. Auto never selects them; `sino` is unchanged.
- The motor count (2, 3 or 4) selects the app's 2M, 3M or 4M screen: back and feet always, then the combined back+foot key, head, or waist plus lumbar. Holds repeat every 100 ms and release sends the zero word after 100 ms with a fresh cancel event; other actions sleep 100 ms and write once.
- Zero G, Flat and Memory A/B recall and save; light on/off switch; head, foot and wave massage levels 0-3 (persisted per bed like the app's preferences, through a new generic `persisted_app_state` store), Start massage, Massage off and the 10/20/30 minute timer select.
- GATT roles follow the app: last FFE9/FFE4 across all services, both required, Android's default write type, no CCCD write. Two-address pairs refuse a shared profile change.

## Exclusions

| Row | Entries | Reason |
|---|---|---|
| L05 Nine-byte FFE4 acceptance, byte 7 bit extraction and broadcast forwarding | 11 | Dead artifact computation: the extracted bits are discarded; no state, gate, UI or later command consumes them (E-RX / E15), and without a CCCD write no notification is requested. |
| L06 Mutable-characteristic write queue and callback drain | 10 | Safety constraint: the app queues references to one mutable characteristic (a later value can replace an earlier pending write), drains regardless of status and disconnects above ten entries; the integration serializes every write under the BLE lock instead. The race is a defect, not protocol. |
| L07 Connect, discover services, connection/discovery callbacks, disconnect, close, reconnect on resume or touch | 41 | Platform or app lifecycle boundary: connection setup, discovery callbacks, reconnects, close and Android lifecycle handling are owned by the Home Assistant Bluetooth stack and coordinator. |
| L08 Screen-off/background disconnect without STOP, onDestroy repeat removal | 4 | Platform or app lifecycle boundary: connection setup, discovery callbacks, reconnects, close and Android lifecycle handling are owned by the Home Assistant Bluetooth stack and coordinator. Every integration hold ends in a finally block that sends the zero word. |
| L09 Unfiltered LE scan, 5000 ms stop, permissions, adapter enable, device rows, saved MAC and aliases | 50 | App UI identity and scan flow: Android scanning, permissions, adapter checks, device rows, saved MAC and aliases; Home Assistant connects to the configured address. |
| L10 Search-menu Bluetooth on/off (enable intent or BluetoothAdapter.disable) | 11 | Platform boundary: toggles the phone's own Bluetooth adapter and sends nothing to the bed. |
| L21 300 ms preset-button disable after a recall | 2 | Unrelated to bed control: a UI debounce that sends no frame; the coordinator serializes commands. |
| L31 Bluetooth Classic, Wi-Fi, cloud and OTA paths (proven absent) | 4 | Out-of-scope product boundary; the artifacts contain no such path and no INTERNET permission. |
| L32 Haptic feedback, actuator 1/2 and installation switches | 10 | Unrelated to bed control: phone-side setting, haptics or library code with no on-air effect. |
| L33 Launcher splash, Back navigation, GIF/static artwork, menus, About, broadcast registration flag | 15 | Unrelated to bed control: app presentation and navigation (launcher, Back, artwork, menus, About). This is where the packages differ (reconciliation DIFFERENT: delivery, manifest_discovery, resources_variants, stack_native, capability_routing); none of it sends a frame. |
| L34 Legacy layout/view constants, others/sofa resources, 500 ms others repeat, unused wrappers, read/RSSI/descriptor paths, helpers, crash handler, unused preferences | 86 | Dead or unreachable artifact code: no reachable producer or selector in either package. |
| L35 GIF JNI library and framework/library code | 6 | Unrelated to bed integration: third-party rendering and Android library code with no bed behavior. |

## Deferred hardware validation

Real users should confirm after a beta or release: the physical axis per screen (2M combined key, 4M waist), hold/release, preset save and recall, massage levels and timer durations, and the write type. See [the profile documentation](../../beds/ore-comfort-bed.md).

## Ledger

| ID | Area | Entries (R/D) | Item | Disposition | Binding or exclusion reason |
|---|---|---|---|---|---|
| L01 | packets | 2/2 | P1 frame: E5 FE 16 + low 32 bits big-endian + (~sum(first 7)) & 0xFF | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py build_frame; tests/test_ore_comfort_bed.py::test_builder_reproduces_every_report_vector |
| L02 | transport | 6/9 | GATT roles: every service enumerated, service UUID ignored, last FFE9 write and last FFE4 notify win, both required before controls work | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py _resolve_write_characteristic; tests/test_ore_comfort_bed.py::test_write_roles_follow_the_app_scan |
| L03 | transport | 3/4 | FFE9 write of the built frame with the inherited Android write type (no response when the characteristic offers it) | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py write_command (_write_gatt_with_retry, BLE lock, exact characteristic); tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once, test_write_roles_follow_the_app_scan |
| L04 | notifications | 2/2 | FFE4 notification enabled locally only: no CCCD or descriptor write | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py start_notify (writes nothing); tests/test_ore_comfort_bed.py::test_notifications_are_never_subscribed |
| L05 | notifications | 5/6 | Nine-byte FFE4 acceptance, byte 7 bit extraction and broadcast forwarding | EXCLUDED | Dead artifact computation: the extracted bits are discarded; no state, gate, UI or later command consumes them (E-RX / E15), and without a CCCD write no notification is requested. |
| L06 | transport | 5/5 | Mutable-characteristic write queue and callback drain | EXCLUDED | Safety constraint: the app queues references to one mutable characteristic (a later value can replace an earlier pending write), drains regardless of status and disconnects above ten entries; the integration serializes every write under the BLE lock instead. The race is a defect, not protocol. |
| L07 | transport | 17/24 | Connect, discover services, connection/discovery callbacks, disconnect, close, reconnect on resume or touch | EXCLUDED | Platform or app lifecycle boundary: connection setup, discovery callbacks, reconnects, close and Android lifecycle handling are owned by the Home Assistant Bluetooth stack and coordinator. |
| L08 | timing | 2/2 | Screen-off/background disconnect without STOP, onDestroy repeat removal | EXCLUDED | Platform or app lifecycle boundary: connection setup, discovery callbacks, reconnects, close and Android lifecycle handling are owned by the Home Assistant Bluetooth stack and coordinator. Every integration hold ends in a finally block that sends the zero word. |
| L09 | discovery | 20/30 | Unfiltered LE scan, 5000 ms stop, permissions, adapter enable, device rows, saved MAC and aliases | EXCLUDED | App UI identity and scan flow: Android scanning, permissions, adapter checks, device rows, saved MAC and aliases; Home Assistant connects to the configured address. |
| L10 | discovery | 5/6 | Search-menu Bluetooth on/off (enable intent or BluetoothAdapter.disable) | EXCLUDED | Platform boundary: toggles the phone's own Bluetooth adapter and sends nothing to the bed. |
| L11 | discovery | 1/1 | No name, service or manufacturer rule: the bed is chosen by hand | IMPLEMENTED | custom_components/adjustable_bed/const.py ORE_COMFORT_BED_VARIANTS; custom_components/adjustable_bed/controller_factory.py explicit variant branch, Auto keeps KeesonController; no manifest matcher; tests/test_ore_comfort_bed.py::test_profile_is_explicit_and_auto_keeps_keeson |
| L12 | selection | 7/9 | User-chosen bedding2/3/4 (2M/3M/4M) screens, all P1 on one GATT; four phone settings never change a packet (48 combinations) | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py LAYOUTS keyed by the configured motor count; custom_components/adjustable_bed/const.py KEESON_VARIANTS maxcoil_una/dynasty_bases; custom_components/adjustable_bed/actuator_groups.py; tests/test_ore_comfort_bed.py::test_motor_count_selects_the_app_screen, test_setup_exposes_the_app_surface |
| L13 | commands | 12/12 | Back 0x1/0x2 and foot 0x4/0x8 on every screen | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py motor_control_specs back/feet; tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero |
| L14 | commands | 2/2 | 2M combined back+foot 0x10/0x20 | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py LAYOUTS[2] 'both' cover (translation Back and legs); tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero |
| L15 | commands | 2/2 | 3M head 0x10/0x20 | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py LAYOUTS[3] 'head' cover; tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero, test_head_exists_only_on_the_three_motor_screen |
| L16 | commands | 2/2 | 4M waist 0x10/0x20 | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py LAYOUTS[4] 'waist' cover (new translation); tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero |
| L17 | commands | 2/2 | 4M lumbar 0x40/0x80 | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py LAYOUTS[4] 'lumbar' cover; tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero |
| L18 | timing | 6/9 | Held movement listeners: write at 0 ms then 100 ms after each write, one global key | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py _hold, motor_pulse_settings (configured count, fixed 100 ms), scheduler_resource '*'; tests/test_ore_comfort_bed.py::test_hold_repeats_every_100ms_then_releases_with_zero, test_motor_count_selects_the_app_screen |
| L19 | commands | 2/2 | Release/STOP zero word after 100 ms on UP, CANCEL or outside MOVE; second tap of a running preset sends the same word | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py _send_release (fresh Event, sent even after cancellation), stop_all and every cover stop; tests/test_ore_comfort_bed.py::test_release_is_sent_even_when_the_hold_was_cancelled, test_single_actions_wait_100ms_then_write_the_app_frame_once[stop] |
| L20 | timing | 3/3 | sendSingleMessage: sleep 100 ms then one write; long-press threshold and release-without-recall after a save | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py _send_single; save buttons; tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once |
| L21 | timing | 1/1 | 300 ms preset-button disable after a recall | EXCLUDED | Unrelated to bed control: a UI debounce that sends no frame; the coordinator serializes commands. |
| L22 | commands | 2/2 | Zero G 0x01000001 and Flat 0x01000002 recall | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py preset_zero_g/preset_flat; tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once |
| L23 | commands | 2/2 | Zero G 0x20000001 and Flat 0x20000002 save (long press) | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py program_zero_g/program_flat as Save Zero G / Save Flat buttons; tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once, test_setup_exposes_the_app_surface |
| L24 | commands | 6/6 | Memory A/B recall 0x01000008/09 and save 0x20000008/09; memory page | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py preset_memory/program_memory, memory_slot_names Memory A/B; tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once |
| L25 | commands | 4/4 | Light on 0x31000001 / off 0x31000000 from a local toggle flag | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py lights_on/lights_off, supports_discrete_light_control (assumed-state switch); tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once, test_setup_exposes_the_app_surface |
| L26 | commands | 11/11 | Wave/head/foot sliders: base + progress // 10 (levels 0-3); progress kept in preferences (default 10); massage page | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py set_massage_level, controller_number_specs, persisted_app_state/restore_persisted_app_state; custom_components/adjustable_bed/coordinator.py _async_restore_app_state (Store); tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once, test_massage_levels_timer_and_stop_publish_app_state, test_slider_levels_persist_across_restarts |
| L27 | commands | 2/2 | Start: current wave, head and foot levels in that order | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py massage_start (Start massage button); tests/test_ore_comfort_bed.py::test_start_sends_current_wave_head_foot_levels |
| L28 | commands | 2/2 | Stop: head level 0 then foot level 0, local timer status reset, no wave frame | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py massage_off; tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once[massage_stop], test_massage_levels_timer_and_stop_publish_app_state |
| L29 | commands | 3/3 | Timer button cycling 10/20/30 minute words 0x10000030/31/32 | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py set_massage_timer_option (Massage timer select, the three words the cycle emits); tests/test_ore_comfort_bed.py::test_single_actions_wait_100ms_then_write_the_app_frame_once |
| L30 | capabilities | 7/7 | Proven absent in the app: PIN/bond/handshake, device info or EEPROM, advanced light, side or sync addressing, position or state feedback, other actions; no capability negotiation | IMPLEMENTED | custom_components/adjustable_bed/beds/ore_comfort_bed.py exposes none of these (no pairing, no feedback entities, single target); custom_components/adjustable_bed/config_flow.py _PER_SIDE_APP_PROFILES; tests/test_ore_comfort_bed.py::test_setup_exposes_the_app_surface, test_notifications_are_never_subscribed, test_two_address_pairs_refuse_a_shared_profile_change |
| L31 | capabilities | 2/2 | Bluetooth Classic, Wi-Fi, cloud and OTA paths (proven absent) | EXCLUDED | Out-of-scope product boundary; the artifacts contain no such path and no INTERNET permission. |
| L32 | configuration | 5/5 | Haptic feedback, actuator 1/2 and installation switches | EXCLUDED | Unrelated to bed control: phone-side setting, haptics or library code with no on-air effect. |
| L33 | presentation | 8/7 | Launcher splash, Back navigation, GIF/static artwork, menus, About, broadcast registration flag | EXCLUDED | Unrelated to bed control: app presentation and navigation (launcher, Back, artwork, menus, About). This is where the packages differ (reconciliation DIFFERENT: delivery, manifest_discovery, resources_variants, stack_native, capability_routing); none of it sends a frame. |
| L34 | dead | 41/45 | Legacy layout/view constants, others/sofa resources, 500 ms others repeat, unused wrappers, read/RSSI/descriptor paths, helpers, crash handler, unused preferences | EXCLUDED | Dead or unreachable artifact code: no reachable producer or selector in either package. |
| L35 | dead | 3/3 | GIF JNI library and framework/library code | EXCLUDED | Unrelated to bed integration: third-party rendering and Android library code with no bed behavior. |
