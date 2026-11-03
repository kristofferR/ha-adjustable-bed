# Row 110: Comfort Enhancements implementation dispositions

This is a separate source-comparison and implementation pass after independent
acceptance, not clean-room analysis. Ref #436, #443 and #447. Coordinator-owned
queue publication is separate. No raw APK, decompilation or report is committed.

## Authority and provenance

- Package `com.okin.enhancements`, 1.0.3, version code 4, standalone APK.
- Verified artifact-set SHA-256:
  `bc76b08e593f42a3772385551553cb93345394639cfeb4d8e2cc61a99c28eab7`.
- Accepted revised report: `work/report-continuation-001` under package run
  `com.okin.enhancements-1.0.3-2026-11-03-bulk101-188-001`.
- `REPORT.SHA256` hash:
  `c1b57c58c161bc50847e17e56c5f07a7668c927ab2be09a73b60ba6b575d9af5`.
- Independent accepted audit: `audit/round002`; `AUDIT.SHA256` hash:
  `0d2a3da64e153f19bdf92930883fd5728e213a6d94a747116a8fde289da910cc`.
- Both manifests and every listed file were verified read-only before comparison.
  The superseded original report is history, not implementation authority.
- F001 is closed in the accepted continuation: WheelView selected listeners
  **are reachable BLE field construction** on all four layouts. Both 300 ms
  debounce and 500 ms programmatic positioning are included below.

The report's candidate IDs C01..C19, complete 42-action table, variant matrix,
transport-callsite inventory and corrected alarm timing cover the discovery
universe. Each item below has exactly one disposition. Grouped ranges enumerate
their individual behaviors. All code references below are relative to
`custom_components/adjustable_bed/`; tests are relative to the repository root.
`CE` means `beds/comfort_enhancements.py`; `T` means
`tests/test_comfort_enhancements.py`. Packet literals in T are the frozen
artifact vectors, not derived from another protocol or physical captures.

## Reachable transport, state and selection ledger

| ID | Accepted evidence and discovery | Disposition | Code and focused validation, or exact exclusion reason |
| --- | --- | --- | --- |
| D01 / C01 | `BluetoothSearchActivity:47-72,198-269`; unfiltered BLE scan, MAC deduplication, no name/service/manufacturer predicate | IMPLEMENTED | Manual app selection in `detection.BED_TYPE_DISPLAY_NAMES`; no automatic signature or manifest entry is added. `T::test_profile_requires_explicit_variant_and_owns_settings`; HA layout setup test. HA scanner/proxy inventory supplies devices. |
| D02 / C02 | `MyService:85-134,180-215`; last FFE9 with WRITE and FFE4 with NOTIFY, dynamic service parents | IMPLEMENTED | `CE._roles`, `write_command`, `start_notify`, `stop_notify`; `T::test_gatt_last_matching_properties_notify_and_no_parser` checks duplicates, invalid properties, exact objects, response metadata and unsubscribe. No guessed parent restriction. |
| D03 / C02 | Inuker ordinary write, no explicit write type, no ACK/init/auth/PIN/bond/MTU/fragmentation | IMPLEMENTED | `CE.write_command` uses runtime write metadata, intact 8/14-byte frames, shared BLE lock and error propagation. No invented handshake or retry. GATT test and builder-vector test. |
| D04 / C01-C02 | Cached address*name, one current mDevice; reconnect on disconnect, retries 0 per request, 30 s library timeouts, 300 ms service-discovery delay, 20 s scan window | IMPLEMENTED | HA config-entry address persistence, connection/session lifecycle and platform-controlled scanning replace Android service/cache/SDK plumbing. `T::controller` and `test_ha_entities_and_alarm_service` exercise real coordinator connect/unload; established coordinator tests cover retries and cancellation. New entries disable quick handoff by default so successive stateful controls retain their connection-local state; the focused new-entry/layout-change test checks the default. The Android cache string format, unconditional reconnect and SDK timers are not hardware timing requirements. |
| D05 | `SelectViewActivity:165-251`, `MainActivity:73-84,125-162`, `VARIANTS.json`; explicit MC2/3/4/5, no device identity selector | IMPLEMENTED | `COMFORT_ENHANCEMENTS_VARIANTS`, required-variant validation, factory constructor and `CE.motor_control_specs`; `T::test_layout_and_every_movement`. No generic motor-count inference, no auto variant. Offline capabilities are permitted only for the four saved layout variants, via `OFFLINE_CAPABILITY_SAFE_VARIANTS`; `test_offline_capabilities_require_the_saved_layout` checks every valid layout plus missing/auto rejection. |
| D06 | MC2/3 union, TV/A/B; MC4 lumbar, single Memory; MC5 Hi Lo, single Memory; MC3 hides massage/light | IMPLEMENTED | Layout-derived axes, presets, memories, lights and massage capabilities; `app_profiles` declares hidden generic fields and per-side ownership. Layout test and all-four-layout HA entity test; frontend discovery test. Obsolete custom buttons retire on layout changes through the existing `button.py` cleanup namespace; `test_new_entries_keep_connection_state_and_layout_change_retires_actions` checks MC2→MC3→MC5. No fabricated fourth axis or remote-code catalog. |
| D07 / C08 | `MyService:65-80`; live FFE4 callback rejects every payload through lowercase/uppercase mismatch | IMPLEMENTED | `CE._notification` retains raw diagnostic bytes, accepts short bytes safely and publishes no parsed state. GATT/notification test. No claimed alarm status or position/sensor feedback. |
| D08 | `PositionsFragment` / `MessageFragment` / `LightFragment`: local animations, lastBt, levels/wave/timer and lamp flag, no working device feedback | IMPLEMENTED | `CE._last_preset`, `_levels`, `_timer`, `get_massage_state`, assumed light flag; states update only after writes, no success claims after cancellation, reset on reconnect. Massage sequences and entity/service tests. Stopping the last active zone clears and publishes local timer0; the next zone start resends timer1. Remote changes and device timer expiry remain unobservable, documented. |
| D09 | `MyService`/SDK requests FIFO, max100, queued Handler dispatch100ms, callback timeout30s | IMPLEMENTED | HA command serialization and BLE operation lock replace the Android queue; command frames remain one-shot where proven. No unconditional 100 ms wire minimum is invented (accepted report explicitly disclaims one). Hold and cancellation tests verify serialized writes and no late restart. |

## Every reachable action and compound transition

All action words below build `E5 FE 16 || word_be32 || complement_sum` in
`CE.control_frame`. `T::test_all_static_and_dynamic_builder_vectors` checks every
reachable static builder and all six accepted clock/alarm vectors. The live
E2 query is distinct from the unused E5 all-FF constant.

| ID / report action | Exact evidence / action words | Disposition | Implementation and validation |
| --- | --- | --- | --- |
| A01-A04: Back/head up/down, Legs/feet up/down | `PositionsFragment:107-208`; `00000001/02/04/08` | IMPLEMENTED | `CE._move`, back/legs covers; `T::test_layout_and_every_movement` calls each direction for every layout. |
| A05-A10: union up/down MC2/3, lumbar up/down MC4, Hi Lo up/down MC5 | Same source, `00000010/20` with explicit screen labels | IMPLEMENTED | Third control is Both, Lumbar or Bed height; same test checks all six app-labelled mappings. No inferred physical actuator count. |
| A11: manual release STOP | `PositionsFragment.stopTimer`; `00000000`, 100 ms after release | IMPLEMENTED | `CE._move` finally calls `_release`; normal delay100ms, cancellation shortens the wait and cleanup uses a fresh event with cancellation shielding. `test_hold_cadence_cancel_and_stop_classes`, `test_task_cancellation_still_releases`. HA does not reproduce connected-guard release loss, orphan timers or queued writes targeting a changed device. |
| A12-A14: Zero G, Flat, Quiet sleep | `MemoryFragment:95-240`; `01000001/02/04` | IMPLEMENTED | Generic preset buttons plus custom Quiet sleep button; `CE._preset`, presets in `T::test_all_preset_light_and_massage_sequences`. Card places Quiet sleep under presets. |
| A15-A18: TV MC2/3, A/B MC2/3, single Memory MC4/5 | Same source; `01000003/08/09/03` | IMPLEMENTED | `preset_tv`, `preset_memory`, `_memory_id`; layout test validates byte mappings and rejects unavailable slots. |
| A19: same-last-preset repeat STOP | Same source; `01000000`, clears lastBt | IMPLEMENTED | `CE._preset` tracks last requested preset; repeated recall sends the separate preset STOP. Explicit Stop handles both packet classes. Layout memory test and STOP-class test. |
| A20-A22: save A/B/single Memory | Same source, long-click; `20000008/09/03` | IMPLEMENTED | `CE.program_memory`; generic Save buttons and program-memory service through coordinator. No framework long-click duration is guessed. Layout and entity tests. |
| A23-A30: head/foot intensities 0..3 | `MessageFragment`; `10000010..13`, `11000010..13` | IMPLEMENTED | Per-zone toggles and intensity-cycle buttons, `CE._zone_click/_level`; sequence test reaches every zone level. No invented relative increment command. |
| A31-A34: wave0..3 | `MessageFragment`; `10000020..23` | IMPLEMENTED | `CE.massage_mode_step`; when active cycles1/2/3/0; zero schedules foot0 at200ms then head0 at300ms. Full sequence tested. |
| A35-A37: 10/20/30 minute timers | `MessageFragment`; `10000030/31/32` | IMPLEMENTED | Timer selector and timer/stop button, `CE.set_massage_timer/_timer_click`; full sequence and HA entity test. Off uses explicit proven zone-off frames, no invented timer-off packet. |
| A38-A39: light On/Off | `LightFragment`; `31000001/00`, MC2/4/5 | IMPLEMENTED | `CE.lights_on/off`, assumed-state switch; vector, command and all-layout entity tests. MC3 rejects light commands. |
| A40: E2 clock/query | `AlarmFragment`; binary ss/mm/hh/Sunday0 day | IMPLEMENTED | `CE.sync_clock`, existing `sync_clock` service; exact Sunday/Saturday builder vectors and HA service dispatch. |
| A41: enable/program BLE alarm | `AlarmFragment:143-312,480-545`; EB14 with current time/day, retained alarm fields, day mask, massage11/33 or00/00, memoryF8/F9/F3/FF | IMPLEMENTED | `CE.alarm_frame/set_alarm/validate_alarm`, `services.handle_comfort_enhancements_set_alarm`, schema/UI translations and docs. Exact A/B/single/none vectors; all-layout service tests validate memory gates before writes. MC3 alarm massage remains selectable, as the app does. |
| A42: disable BLE alarm | Same source; FF at6/7/9/10/11/12, current time/day retained | IMPLEMENTED | Full disable packet independent of previous local fields or time input; both accepted disable vectors and service disable test. |
| M01: zone toggle0↔3, intensity0→3→2→1→0; timer1 if local timer0, zone3 at+200ms | `MessageFragment` compound click transitions | IMPLEMENTED | `CE._zone_click/_start_timer`; command-sequence test covers both zones and all levels. |
| M02: wave with both zones off sends optional timer1, head3+200ms, foot3+300ms, no wave packet | Same source | IMPLEMENTED | `CE.massage_mode_step`; exact sequence test. |
| M03: timer active stops head0 now, foot0+200ms, resets timer0 without timer frame; otherwise cycles1/2/3/1 | Same source | IMPLEMENTED | `CE._timer_click/massage_off`; exact sequence test. Delayed start writes check cancellation; once shutdown begins, its zero-level writes finish under the command owner before preempting presets, with fresh cancellation events and shielding. `test_massage_shutdown_finishes_before_preempting_preset` checks both timer-stop and wave-zero through the real coordinator. No autonomous tasks outlive their command owner. |
| F001: wheel selected300ms debounce, setSelection500ms positioning; stale/FF minute/hour possible; disable does not reset retained cmd; posted String is immutable snapshot | Revised report F001, AlarmFragment/WheelView smali and56 timing cases/496 transformations | IMPLEMENTED | HA commits validated explicit time and selected memory/massage in a single service invocation. It never sends initialFF/stale enabled fields or replays UI debounce; current-day packet semantics retained. Invalid/missing time rejects before writes. `T::test_ha_entities_and_alarm_service` and exact settled vectors. This is safe HA behavior for proven app races, not a new inferred wire protocol. |
| L01: movement repeats200ms without cap; release100ms; no lifecycle timer cleanup; no purging queued transport writes, delayed callbacks use current device | `PositionsFragment`, `BaseFragment`, `MyService` lifecycle | IMPLEMENTED | Fixed200ms bounded HA pulses, same-address command owner, cancellable delays and awaited cleanup; no unsafe app orphan work. STOP event and task cancellation tests. App's unbounded count is represented by configurable bounded taps/held card actions, not an infinite writer. |

## Explicit exclusions and negative inventory

These are terminal dispositions, not implementation debt.

| ID / candidate | Accepted exact evidence | Disposition | Reason |
| --- | --- | --- | --- |
| X09 / C09 | `AlarmFragment:402-477`, only producer is impossible `MyService:65-80` condition | EXCLUDED | Dead alarm parser, no reachable status consumer. Its unchecked offsets3/4/8/9 and always-true massage predicate do not establish a valid live parser or reply format. |
| X10 / C10 | `MyService:142-143,216-219`; FF91 role discovered, no BLE_MODIFY_NAME producer | EXCLUDED | Dead rename write. Discovering a characteristic is not a reachable rename feature; no name-edit action. |
| X11 / C11 | `SelectViewActivity:81-143`, private connectDeviceIfNeeded uncalled and mDevice never assigned | EXCLUDED | Dead alternate connection/init packet `A5C7110000000082` and100ms sleep. Not initialization. |
| X12 / C12 | `service/BluetoothLeService.java`, absent manifest/start/bind/construction | EXCLUDED | Dead legacy GATT read/write queues and unused activity field. |
| X13 / C13 | `devicmd/DataManager.java`, no DataDispose caller | EXCLUDED | Dead type1/2/4/8 sensor logger; temperature/humidity offsets have no live consumer or proven unit. No sensors invented. |
| X14 / C14 | `AlarmFragment:642-677`; uncalled SetRTCDate/EA13; `MyService.buildBluetoothPackage(long)` uncalled; `DevCmd.cmd_getAM_Data` unreferenced | EXCLUDED | Dead builders/constants, including E5FFFFFFFF. Live E2 clock/query is implemented separately. |
| X15 / C15 | Complete `TRANSPORT-CALLSITES.json`101 matches; SDK search/mirror/read/indicate/no-response/descriptor APIs lack app callers | EXCLUDED | Unused alternative SDK transports and file-close false positives. No extra bed transport is inferred from bundled libraries. |
| X16 / C16 | All four `libpl_droidsonroids_gif.so` ABIs and graphics JNI mappings | EXCLUDED | Unrelated GIF graphics/native rendering, no BLE packet logic. |
| X17 / C17 | `AlertActivity`/`RingActivity`, MediaPlayer/AlarmManager; ALARM_MASSAGE consumer does nothing | EXCLUDED | Phone ringtone/playback and Android scheduler are companion infrastructure. BLE clock/alarm A40-A42 remains implemented. |
| X18 / C18 | `devicmd/Constantss:5-11`, CHAIR/LOVE_SEAT/SOFA no caller | EXCLUDED | Dead identifiers, not additional model variants. |
| X19 / C19 | Generic material resources, manufacturer registry, UI scroller reflection | EXCLUDED | Unrelated library resources do not establish RGB, authentication, side selection or product capabilities. Reachable WheelView selected callbacks are specifically included as F001 above, not excluded wholesale. |
| X20 | Accepted capability searches: no WiFi/SSID/cloud/account/OTA path, no app INTERNET permission/caller | EXCLUDED | Outside direct BLE bed product boundary; no reachable implementation item found. |
| X21 | Accepted parser/capability searches: no live position/angle/height/current/firmware/battery/lock/error/capability parser, EEPROM/calibration/reset/RGB/split/sync/coupling/PIN handshake | EXCLUDED | No reachable artifact behavior. Negative inventory is not evidence for commands or entities. HA proxy/adapter setup stays supported through its own platform. |

## Validation and hardware boundary

Focused vector, sequence, GATT, cancellation, factory, setup/entity/service and
frontend discovery tests establish software behavior. Existing coordinator,
profile, import-isolation and config-flow tests protect shared integration
contracts. Ruff, Pyright and the rebuilt committed frontend bundle are required.
The implementation preserves every reachable direct BLE feature. Physical
semantics, stop latency and actual alarm operation are deferred real-user
validation after beta/release, not missing maintainer implementation work.
