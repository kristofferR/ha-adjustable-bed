# Dream Motion HD 1.0.4 discovery dispositions (row105)

This is a separate integration comparison of the independently accepted repaired
report, not a clean-room analysis. It covers only
`com.dreamhd.jiecang.android.pad.bed` **1.0.4 (4)**. No shared-family inference
supplies a command, parser field, timing value or layout.

## Frozen authority

- Artifact set: `29ba464c30d384eabc46312f54301a9881761be69416289d16ff76c0a88b09c0`.
- Accepted `work/report-repair-sol-001/REPORT.SHA256`:
  `2bc0c2799d867cc8a218edd07be1e9d21a7ef5c431fb36378a84fee24cee9f56`.
- Independent `audit/round003/AUDIT.SHA256`:
  `fd8554082332b4818b5e68c968a8fd1bc70e8949825053734315a9e2b935ae6e`.
- Local run basename:
  `com.dreamhd.jiecang.android.pad.bed-1.0.4-2026-11-03-bulk101-188-002`.
- All report/audit members and six input members were verified read-only before
  comparison; canonical artifact-set digest matches. Round003 accepts all 17
  gates and closes `ROW105-AUD002-F001`. The superseded original report is not
  implementation authority. Raw APKs, reports and decompiler outputs remain local.

Source references below are package-local accepted evidence, not repository
paths. `MainActivity.java` is under
`com/dreamotion/jiecang/android/dreamhd/`. E03 scan, E04 GATT, E05 startup,
E06 callsites, E07 layouts, E08 parser, E10 controls, E11 clock/alarm,
E12 RGB, E13 rename, E14 broadcast wake, E16 dead-code census and E18 repaired
helper/consumer bind the evidence. The corrected source helper is
MainActivity.java:4944–4945 and the feature caller is :604–617; authoritative
smali helper :3969–4021 and receiver :1595–1697 establish operation order.

## Implementation and test reference key

All production paths below are relative to `custom_components/adjustable_bed/`.
Every `ALREADY_IMPLEMENTED` packet row has equivalent code and an independent
HD literal check, even when the same bytes also occur in another app.

| Key | Production implementation | Concrete test reference |
| --- | --- | --- |
| PK | `jiecang_app_protocol.py`: `build_frame`, motion/preset/massage builders | `tests/test_dreamhd.py::test_complete_reachable_fixed_frame_census` checks exactly all 45 fixed frames |
| CT | `beds/jiecang_app.py`: `_move_axis`, `_click`, `stop_all`, memory methods | `tests/test_dreamhd.py::test_hd_controller_commands_and_cancellation` |
| GT | `beds/jiecang_app.py`: `_TRANSPORTS`, `_select_transport`, `start_notify`, `stop_notify`, `write_command` | `tests/test_dreamhd.py::test_hd_transports_bootstrap_and_reconnect`; `tests/test_jiecang_app_controller.py::test_absolute_schedule_accounts_for_ble_latency` |
| CF | `const.py`: `JIECANG_APP_PROFILES`; `config_flow.py`: `_jiecang_app_errors`, `async_step_jiecang_app`; `controller_factory.py`: app construction | `tests/test_jiecang_app_config.py::test_dreamhd_setup_and_factory_keep_explicit_profile`, `test_dreamhd_setup_rejects_other_apps_layouts` |
| DS | `manifest.json` G1/G3 discovery; `config_flow.py` manual address and explicit app step | `tests/test_dreamhd.py::test_hd_discovery_has_no_app_or_name_inference`; `tests/test_jiecang_app_config.py::test_all_setup_routes_collect_explicit_profile` |
| RX | `jiecang_app_protocol.py`: `parse_notification`; `beds/jiecang_app.py`: `_handle_notification` | `tests/test_dreamhd.py::test_hd_wake_offsets_and_parser_edges`, `test_hd_unknown_alarm_preset_retains_previous_selection`, `test_hd_split_feedback_alias_and_no_optimistic_intensity` |
| LC | `jiecang_app_protocol.py`: `DreamHDLightControls`; controller light gates and methods | `tests/test_dreamhd.py::test_all_feature_bytes_and_sticky_consumer_orders`, `test_hd_light_consumer_and_released_toggles`, `test_hd_manual_light_gate_and_legacy_consumer` |
| DY | `jiecang_app_protocol.py`: clock/alarm/RGB/name builders | `tests/test_dreamhd.py::test_hd_startup_and_dynamic_vectors`; `tests/test_jiecang_app_protocol.py::test_truncated_notifications_never_read_fields_out_of_bounds` |
| WK | `jiecang_app_protocol.py`: `wake_schedule`; controller `execute_wake_routine`, `stop_wake_routine` | `tests/test_dreamhd.py::test_hd_wake_offsets_and_parser_edges`, `test_hd_wake_cleanup_on_success_cancel_and_failure` |
| UI | existing cover/button/number/light/select/switch platforms and `services.py` Jiecang alarm/wake plus generic rename | `tests/test_jiecang_app_entities.py::test_dreamhd_entities_use_hd_frames_and_notification_aliases`, `test_dreamhd_alarm_wake_and_rename_services` |

## Reachable command ledger

P1 destination is selected coherently from G1/G2/G3. G1 service FF12 has
write FF01, notify FF02, name FF06; G3 FE60 has write FE61, notify FE62,
name FE63 (all Bluetooth-base UUIDs). G2 service
`88121427-11e2-52a2-4615-ff00dec16800` uses characteristic ending `6801`
for write and notify, no name. Runtime properties choose response writes.
No app-selected write type, login handshake, MTU or PIN is invented.

The table enumerates all 50 accepted command rows, including dynamic builders
and the two name routes. PK/CT/GT/DY/WK/UI resolve to concrete code and tests above.
Timing consumers that differ from a reused packet builder are separately
`IMPLEMENTED` in the behavior ledger.

| ID | Reachable action | Packet / builder | Disposition | Code + test key | Package-local evidence |
| --- | --- | --- | --- | --- | --- |
| C01 | Query General status | `F1F10000007E` | IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:567; MainActivity.java:948 |
| C02 | Query Actuator status | `F1F1000101027E` | IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:559 |
| C03 | Query Vibration intensity | `F1F1000108097E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:543 |
| C04 | Query Alarm configuration | `F1F1000110117E` | ALREADY_IMPLEMENTED | DY / UI | MainActivity.java:535 |
| C05 | Query Hardware configuration | `F1F1000140417E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:551 |
| C06 | Query Software configuration | `F1F100024000427E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:527 |
| C07 | Back/head section up (split left) | `F1F1010101037E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:4355; MainActivity.java:4367; MainActivity.java:4376; MainActivity.java:4385 |
| C08 | Back/head section down (split left) | `F1F1020101047E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:4305; MainActivity.java:4317; MainActivity.java:4326; MainActivity.java:4335 |
| C09 | Legs up | `F1F1030101057E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:4361; MainActivity.java:4370; MainActivity.java:4382; MainActivity.java:4388 |
| C10 | Legs down | `F1F1040101067E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:4311; MainActivity.java:4320; MainActivity.java:4332; MainActivity.java:4338 |
| C11 | Back and legs up | `F1F1050101077E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:4358 |
| C12 | Back and legs down | `F1F1060101087E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:4308 |
| C13 | Zero gravity | `F1F1070101097E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:1879; MainActivity.java:1883; MainActivity.java:1887; MainActivity.java:1891; MainActivity.java:1895; MainActivity.java:2344; MainActivity.java:2348; MainActivity.java:2352; MainActivity.java:2356; MainActivity.java:2360; MainActivity.java:4085 |
| C14 | Flat | `F1F10801010A7E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:1905; MainActivity.java:1909; MainActivity.java:1913; MainActivity.java:1917; MainActivity.java:1921; MainActivity.java:2370; MainActivity.java:2374; MainActivity.java:2378; MainActivity.java:2382; MainActivity.java:2386; MainActivity.java:4091; MainActivity.java:4097 |
| C15 | Anti-snore | `F1F10901010B7E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:1934; MainActivity.java:1938; MainActivity.java:1942; MainActivity.java:1946; MainActivity.java:1950; MainActivity.java:2399; MainActivity.java:2403; MainActivity.java:2407; MainActivity.java:2411; MainActivity.java:2415; MainActivity.java:4103 |
| C16 | Save/program memory 1 | `F1F10A01010C7E` | IMPLEMENTED | PK / CT / GT / WK | SetMemoryActivity.java:63; SetMemoryActivity.java:67; SetMemoryActivity.java:71 |
| C17 | Recall memory 1 | `F1F10B01010D7E` | IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:1823; MainActivity.java:1827; MainActivity.java:1831; MainActivity.java:1835; MainActivity.java:1839; MainActivity.java:2288; MainActivity.java:2292; MainActivity.java:2296; MainActivity.java:2300; MainActivity.java:2304; MainActivity.java:4110 |
| C18 | Save/program memory 2 | `F1F10C01010E7E` | IMPLEMENTED | PK / CT / GT / WK | SetMemoryActivity.java:85; SetMemoryActivity.java:89; SetMemoryActivity.java:93 |
| C19 | Recall memory 2 | `F1F10D01010F7E` | IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:1851; MainActivity.java:1855; MainActivity.java:1859; MainActivity.java:1863; MainActivity.java:1867; MainActivity.java:2316; MainActivity.java:2320; MainActivity.java:2324; MainActivity.java:2328; MainActivity.java:2332; MainActivity.java:4125 |
| C20 | Toggle legacy under-bed light | `F1F10F000F7E` | IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:4065 |
| C21 | Stop massage (also legacy alarm stop) | `F1F11101081A7E` | ALREADY_IMPLEMENTED | DY / UI | MainActivity.java:2444; MainActivity.java:3715; MainActivity.java:3751 |
| C22 | Set massage back / split left head wire intensity 0 | `F1F1120208001C7E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:3663; MainActivity.java:3798; MainActivity.java:3834 |
| C23 | Set massage back / split left head wire intensity 2 | `F1F1120208021E7E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:1612; MainActivity.java:1616; MainActivity.java:1620; MainActivity.java:1969; MainActivity.java:1973; MainActivity.java:1977; MainActivity.java:3610; MainActivity.java:3666; MainActivity.java:3801; MainActivity.java:3837; MainActivity.java:3883; MainActivity.java:3915 |
| C24 | Set massage back / split left head wire intensity 3 | `F1F1120208031F7E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:1644; MainActivity.java:1648; MainActivity.java:1652; MainActivity.java:2037; MainActivity.java:2041; MainActivity.java:2045; MainActivity.java:3602; MainActivity.java:3669; MainActivity.java:3804; MainActivity.java:3840; MainActivity.java:3875; MainActivity.java:3907 |
| C25 | Set massage back / split left head wire intensity 4 | `F1F112020804207E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:1676; MainActivity.java:1680; MainActivity.java:1684; MainActivity.java:2105; MainActivity.java:2109; MainActivity.java:2113; MainActivity.java:3604; MainActivity.java:3877; MainActivity.java:3909 |
| C26 | Set massage legs wire intensity 0 | `F1F1140208001E7E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:3699; MainActivity.java:3816 |
| C27 | Set massage legs wire intensity 2 | `F1F114020802207E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:1715; MainActivity.java:1719; MainActivity.java:1723; MainActivity.java:2180; MainActivity.java:2184; MainActivity.java:2188; MainActivity.java:3642; MainActivity.java:3702; MainActivity.java:3819; MainActivity.java:3899 |
| C28 | Set massage legs wire intensity 3 | `F1F114020803217E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:1747; MainActivity.java:1751; MainActivity.java:1755; MainActivity.java:2212; MainActivity.java:2216; MainActivity.java:2220; MainActivity.java:3634; MainActivity.java:3705; MainActivity.java:3822; MainActivity.java:3891 |
| C29 | Set massage legs wire intensity 4 | `F1F114020804227E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:1782; MainActivity.java:1786; MainActivity.java:1790; MainActivity.java:2247; MainActivity.java:2251; MainActivity.java:2255; MainActivity.java:3636; MainActivity.java:3893 |
| C30 | Cycle massage mode | `F1F116010A217E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:3941 |
| C31 | Neck up or Hi Low up (layout dependent) | `F1F11901011B7E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:4364; MainActivity.java:4373 |
| C32 | Neck down or Hi Low down (layout dependent) | `F1F11A01011C7E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:4314; MainActivity.java:4323 |
| C33 | Lumbar up | `F1F11B01011D7E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:4379 |
| C34 | Lumbar down | `F1F11C01011E7E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:4329 |
| C35 | Split right head up | `F1F1200101227E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:4391 |
| C36 | Split right head down | `F1F1210101237E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:4341 |
| C37 | Set massage split right head wire intensity 0 | `F1F1220208002C7E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:3681; MainActivity.java:3852 |
| C38 | Set massage split right head wire intensity 2 | `F1F1220208022E7E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:1993; MainActivity.java:1997; MainActivity.java:2001; MainActivity.java:3626; MainActivity.java:3684; MainActivity.java:3855; MainActivity.java:3931 |
| C39 | Set massage split right head wire intensity 3 | `F1F1220208032F7E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:2061; MainActivity.java:2065; MainActivity.java:2069; MainActivity.java:3618; MainActivity.java:3687; MainActivity.java:3858; MainActivity.java:3923 |
| C40 | Set massage split right head wire intensity 4 | `F1F122020804307E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:2129; MainActivity.java:2133; MainActivity.java:2137; MainActivity.java:3620; MainActivity.java:3925 |
| C41 | Both split heads up | `F1F1230101257E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:4394 |
| C42 | Both split heads down | `F1F1240101267E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:4344 |
| C43 | Yoga | `F1F1280200002A7E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:4217 |
| C44 | Toggle human-icon automatic light function | `F1F1290200002B7E` | ALREADY_IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:4079; E18 |
| C45 | Button release | `F1F14E004E7E` | IMPLEMENTED | PK / CT / GT / WK | MainActivity.java:1624; MainActivity.java:1628; MainActivity.java:1632; MainActivity.java:1656; MainActivity.java:1660; MainActivity.java:1664; MainActivity.java:1688; MainActivity.java:1692; MainActivity.java:1696; MainActivity.java:1727; MainActivity.java:1731; MainActivity.java:1735; MainActivity.java:1759; MainActivity.java:1763; MainActivity.java:1767; MainActivity.java:1794; MainActivity.java:1798; MainActivity.java:1802; MainActivity.java:1981; MainActivity.java:1985; MainActivity.java:1989; MainActivity.java:2005; MainActivity.java:2009; MainActivity.java:2013; MainActivity.java:2049; MainActivity.java:2053; MainActivity.java:2057; MainActivity.java:2073; MainActivity.java:2077; MainActivity.java:2081; MainActivity.java:2117; MainActivity.java:2121; MainActivity.java:2125; MainActivity.java:2141; MainActivity.java:2145; MainActivity.java:2149; MainActivity.java:2192; MainActivity.java:2196; MainActivity.java:2200; MainActivity.java:2224; MainActivity.java:2228; MainActivity.java:2232; MainActivity.java:2259; MainActivity.java:2263; MainActivity.java:2267; MainActivity.java:4281 |
| C46 | Set local device clock | `F1 F1 50 07 [year-1970,month1-12,day,weekday(Sun=0),hour,minute,second] SUM8(50..second) 7E` | ALREADY_IMPLEMENTED | DY / UI | MainActivity.java:597-599; MainActivity.java:1535-1604 |
| C47 | Configure bed-side alarm | `Dynamic builder, see DY and protocol guide` | ALREADY_IMPLEMENTED | DY / UI | MainActivity.java:2609-2680; MainActivity.java:3144-3218; MainActivity.java:3225-3254; MainActivity.java:3399-3523 |
| C48 | Set RGB light, brightness, duration, state | `Dynamic builder, see DY and protocol guide` | ALREADY_IMPLEMENTED | DY / UI | ColorPicker/ColorPickerActivity.java:86-200; ColorPicker/ColorPickerActivity.java:243-293; ColorPicker/ColorPickerActivity.java:412-443; MainActivity.java:4056-4067; E18 |
| C49 | Rename BLE device | `Dynamic builder, see DY and protocol guide` | IMPLEMENTED | DY / UI | RenameDeviceActivity.java:41-112; MainActivity.java:2814-2823 |
| C50 | Rename BLE device | `Dynamic builder, see DY and protocol guide` | IMPLEMENTED | DY / UI | RenameDeviceActivity.java:41-112; MainActivity.java:2814-2823 |

## Behavior, consumer and lifecycle ledger

| ID | Discovery and evidence | Disposition | Implementation and validation |
| --- | --- | --- | --- |
| B01 | E03 sequential G1/G3 scans, deduplication, optional exact QR MAC, history reconnect | IMPLEMENTED | DS/CF/GT. HA owns scanning and saved-address reconnection. Shared UUIDs discover a candidate, never select HD; explicit profile required. No G2-only advertised filter or name/manufacturer match added. |
| B02 | E04 G1/G3 require all three roles for startup; G2 has no ready event, possible persisted/manual address | IMPLEMENTED | GT. A pure G2 link subscribes but emits no startup burst. Co-present complete G1/G3 permits it. No invented hardware setup success or authentication. |
| B03 | E04–05 CCCD notification setup, G3 name notify at 3000 ms, stale shared flags/last match | IMPLEMENTED | GT. Bleak awaits descriptor completion; one coherent service is selected with explicit override and no static cross-device references. Duplicate ready events are coalesced. |
| B04 | E05 general query at 0/100, actuator 1000/1100, hardware 1200/1300, vibration 1400/1500, alarm 1600/1700, software 1800/1900 | IMPLEMENTED | `DREAMHD_BOOTSTRAP`, GT. No phone-app light query or actuator payload is reused. Absolute scheduling accounts for write latency. |
| B05 | E06 F1 F1 opcode length payload sum8 7E, no framing escape/encryption | ALREADY_IMPLEMENTED | PK `build_frame`; independent 45-frame census and DY dynamic vectors establish exact equivalence. |
| B06 | E10 movement click/held 100 ms, terminal movement and short release after 100 ms; missing ACTION_CANCEL/key/destroy/Flat hold cleanup | IMPLEMENTED | CT. Configured pulse count bounds HA hold; terminal movement only on uncancelled completion. Fresh-event short release in finally, immediate explicit STOP. No long release packet added. |
| B07 | E10 preset/memory/Yoga taps release at 100 ms, save memory at 0/30/60 without release | IMPLEMENTED | CT and UI use HD memory payload01 and short release. Flat is a safe discrete preset action; its unsafe Android endless long-hold path is excluded below. |
| B08 | E10 UI massage0/2/3/4, single writes for step/mode/stop, no normal release; levels derive from received state | IMPLEMENTED | PK/CT/RX/UI. Steps await notifications instead of incrementing cached intensity on write. Mode names/count remain unknown; use cycle action. |
| B09 | E08 byte4 back/left and byte6 both legs/right, header-independent byte2=06 | IMPLEMENTED | RX updates both split controls from byte6; no speculative third field. Each control still writes its independently proven opcode. |
| B10 | E18 feature helper minimal binary + append zeros + first8 + reverse, char5; Yoga independently real bit1 | IMPLEMENTED | RX already has equivalent helper; LC now implements HD's consumer. Tests cover all256 bytes, both manual gates, suppression states and prior visibility. 06 means RGB false/Yoga true; A0 means RGB true/Yoga false. |
| B11 | E18 negative feature sets picker8, human/container4, sticky suppression=true; positive sets0 without clearing suppression | IMPLEMENTED | LC state is retained and exposed in protocol diagnostics. Human gate and picker gate are independent. |
| B12 | E18 PackageCheck reveals picker only with suppressionfalse, does not forcibly hide a visible picker, never reveals human controls | IMPLEMENTED | LC consumes RGB before feature/layout logic. Parsed values continue to update even while controls are hidden. |
| B13 | E18 manual no/empty/unknown skips feature visibility writes; standard layout no hides all three; split-series bypasses standard refresh | IMPLEMENTED | CF stores a typed boolean, mapping yes/no only; LC skips absent-light feature writes and handles layout refresh. HA always adds explicit `has_light` consent before exposing light entities, avoiding Android's unsolicited picker despite manual=no. |
| B14 | E18 connection hides controls, resets suppression/color/brightness/lightStatus, retains Yoga/timer; old preference/history retained visibility | IMPLEMENTED | GT/LC reset visibility and invalidate cached RGB/on/automatic state; Yoga survives. HA requests state before a partial write instead of writing Android's speculative color/brightness defaults. Entry reload replaces stale activity/history state. |
| B15 | E08 F2F250 >=6 bytes requests local clock, F2F20F >=7 applies configured layout without parsing motors | IMPLEMENTED | RX/CF and serialized `_respond_with_clock`; `test_clock_reply_uses_coordinator_serialization` plus DY clock vector. No model inference from response. |
| B16 | E08 F2F251 >=7 reveals alarm tab; >=14 reads enable/day bits1..7/hour/minute/preset/intensities, unknown preset retained | IMPLEMENTED | RX/UI with unknown-preset retention, truncated-state preservation and range guards. Invalid raw fields are rejected rather than re-encoded into malformed alarm strings. |
| B17 | E08 F2F25207 >=13 BGR/brightness/seconds/on; F2F253 zero off, nonzero on | IMPLEMENTED | RX/LC/UI; HD fixes profile-specific icon-state polarity. Bad checksum/trailer and trailing bytes are accepted as in app; no invented fragmentation or ACK parser. |
| B18 | E08 legacy byte2=05/06 byte8.bit6: set stores on; clear stores off only with light button visible | IMPLEMENTED | RX honors manual light visibility for clear; state propagates to cached RGB so future writes preserve current on/off. |
| B19 | E12 RGB brightness0..100; durations0,1,2,3,4,5,10,15,20,25,30 min; white and color edits, slider immediate/final events, MOVE smali correction | IMPLEMENTED | DY/LC/UI. HA color/brightness/timer sets one explicit final value, preserves other reported fields, and can select white. Android per-pixel drag/redundant final writes are presentation event noise, not independent BLE features. Arbitrary received timers are reported; unsupported timer write values fail before transmission. |
| B20 | E12 main toggle RGB0, short release100, legacy toggle200, short release300; human toggle release100 | IMPLEMENTED | LC exact packet order and cancellation-safe final short release. Automatic-light control requires known prior state and is idempotent. Physical meaning of icon deferred. |
| B21 | E11 clock year-1970, month,day,Sun=0,hour,minute,second; alarm enabled/repeat/days/time/preset/back/leg, preset map03/04/02/00/01/06 | ALREADY_IMPLEMENTED | DY builders plus independent HD vectors and UI service literal prove byte equivalence. UI weekly service uses distinct weekdays; no speculative clock query added. |
| B22 | E13 G1 raw Android string, G3 01FC07 length/unpadded UTF16 bug, two writes0/500, local name saved before success | IMPLEMENTED | DY/GT/UI support printable ASCII names including spaces. G3 uses valid byte length for10–15 rather than odd-nibble truncation; reject lossy non-ASCII, never persist success before BLE write. Name follows selected coherent service. |
| B23 | E14 conditional START_ALARM broadcast, back triple0/30/60 + release90/120/150; split right180/210/240 + release270/300/330; legs500; preset800..920, no final release, Yoga no executor | IMPLEMENTED | WK/UI expose HA wake service for both standard and split-upper/series, using HD memory frames and timing. HA adds proven short release after preset, also independently attempts wake-massage stop on cancellation/failure even when the release write fails. `test_hd_cancelled_wake_attempts_massage_stop_even_when_release_fails` verifies both attempts and propagated failure. Yoga alarm storage allowed only after reported Yoga; Yoga wake execution rejected. |
| B24 | E07 six standard layouts x2massage x2light plus split-series, transport orthogonal; no bilateral4 or retained bilateral mix | IMPLEMENTED | CF and `DREAMHD_LAYOUTS`; HA covers all25 without inference. Each standard layout's independent booleans use existing setup controls; split-series also allows explicit disabling of optional hardware. Tests cover all seven selector values and rejected alternatives. |
| B25 | E04 disconnect/unbind/close, reconnect UI and timeout, one static GATT, no partner discovery/coupling | IMPLEMENTED | GT plus existing `coordinator.py` command lock/connection owner/STOP paths. HA owns bounded reconnect and one physical address per standalone entry. Logical split controls route opcodes on that address. No coupling packet invented. |
| B26 | E08 raw read/notify/write echoes feed same parser with no UUID discriminator or checksum check; no queue or ACK waiting | IMPLEMENTED | RX handles notification/name bytes safely; GT serializes writes and propagates real failures. Host write echoes are not spoofed as bed feedback, preventing false state acknowledgements. |
| B27 | E07/16 old IsThereLight preference read on startup/result100; legacy false hides, true retains existing views; unused settings editor | EXCLUDED | App-specific local preference and activity restoration, no BLE write or new hardware behavior. HA explicit light setting replaces it; conservative hidden initial views and connected reset are LC, B14. The dead editor is separately excluded below. |
| B28 | E10 missing release on cancellation/destroy/Flat repeat, stale flags, no write queue, ignored write failures | EXCLUDED | Unsafe app defects, replaced by B03/B06/B23/B26 cleanup, per-entry roles, HA serialization and errors. No harmful repeat after cancellation, premature local rename success, or false write-echo feedback. |
| B29 | E03/05 Android scan windows2s/1s/2s,60s overlay timeout, QR camera/history/Activity resume status pair | EXCLUDED | Android presentation/lifecycle, not bed timing or an independent bed feature. HA Bluetooth owns scanning/setup, explicit address replaces QR, reconnect reruns B04. No extra scan timer, local activity state or duplicate resume burst. |
| B30 | E16 no WiFi/SSID/password/provisioning, cloud-bed service or OTA found | EXCLUDED | No reachable bed behavior exists in this artifact; WiFi/cloud/provisioning are outside this integration's direct-BLE bed boundary. SDK WorkManager network/password strings are unrelated, not feature debt. |
| B31 | E08 no measured position, angle, firmware/serial/battery parser, lock/calibration/coupling | EXCLUDED | No reachable parser/command evidence. Do not fabricate values or capabilities from status queries, dead reset constants or model names. |
| B32 | E08/E18 capability replies can arrive after setup and withdraw/reveal controls repeatedly | IMPLEMENTED | `has_dynamic_controller_entities`, `entity_discovery.py` and dynamic button/switch setup reconcile newly proven controls without reload. Retired registry instances are forgotten so a later positive reply recreates them. `tests/test_jiecang_app_entities.py::test_dreamhd_late_light_and_yoga_entities_reconcile_repeated_transitions` covers missing/negative initial responses and repeated negative/positive transitions across RGB, brightness, timer, automatic light and Yoga. |

## Explicit variant dispositions

Every accepted layout below is `IMPLEMENTED` via CF/UI. The concrete test
`tests/test_jiecang_app_entities.py::test_dreamhd_all_25_configurations_gate_entities`
loads each configuration and checks the exact cover axes, optional massage
zones, lighting, automatic-light switch and timer entities. E07 and
`variant-inventory.json` supply each selector. Split-series has no separate
feature-selection form in Android; HA uses explicit optional-feature settings
instead of accidentally retained preferences. That safety adaptation does not
remove its generic controls or add a new packet.

| Accepted selector | HA layout | Disposition |
| --- | --- | --- |
| `split-series` | `split_series` | IMPLEMENTED |
| `standard-2/massage=0/light=0` | `standard_2` | IMPLEMENTED |
| `standard-2/massage=0/light=1` | `standard_2` | IMPLEMENTED |
| `standard-2/massage=1/light=0` | `standard_2` | IMPLEMENTED |
| `standard-2/massage=1/light=1` | `standard_2` | IMPLEMENTED |
| `standard-3-hilow/massage=0/light=0` | `standard_3_hi_low` | IMPLEMENTED |
| `standard-3-hilow/massage=0/light=1` | `standard_3_hi_low` | IMPLEMENTED |
| `standard-3-hilow/massage=1/light=0` | `standard_3_hi_low` | IMPLEMENTED |
| `standard-3-hilow/massage=1/light=1` | `standard_3_hi_low` | IMPLEMENTED |
| `standard-3-lumbar/massage=0/light=0` | `standard_3_lumbar` | IMPLEMENTED |
| `standard-3-lumbar/massage=0/light=1` | `standard_3_lumbar` | IMPLEMENTED |
| `standard-3-lumbar/massage=1/light=0` | `standard_3_lumbar` | IMPLEMENTED |
| `standard-3-lumbar/massage=1/light=1` | `standard_3_lumbar` | IMPLEMENTED |
| `standard-3-neck/massage=0/light=0` | `standard_3_neck` | IMPLEMENTED |
| `standard-3-neck/massage=0/light=1` | `standard_3_neck` | IMPLEMENTED |
| `standard-3-neck/massage=1/light=0` | `standard_3_neck` | IMPLEMENTED |
| `standard-3-neck/massage=1/light=1` | `standard_3_neck` | IMPLEMENTED |
| `standard-3-top-split/massage=0/light=0` | `standard_3_split_upper` | IMPLEMENTED |
| `standard-3-top-split/massage=0/light=1` | `standard_3_split_upper` | IMPLEMENTED |
| `standard-3-top-split/massage=1/light=0` | `standard_3_split_upper` | IMPLEMENTED |
| `standard-3-top-split/massage=1/light=1` | `standard_3_split_upper` | IMPLEMENTED |
| `standard-4/massage=0/light=0` | `standard_4_legacy` | IMPLEMENTED |
| `standard-4/massage=0/light=1` | `standard_4_legacy` | IMPLEMENTED |
| `standard-4/massage=1/light=0` | `standard_4_legacy` | IMPLEMENTED |
| `standard-4/massage=1/light=1` | `standard_4_legacy` | IMPLEMENTED |

## Complete candidate and transport-callsite accounting

This indexes all90 accepted candidate rows, including each of47 transport or
structural API matches. Rows with equivalent packet builders still point to
the command table above; every live operation is integrated into the explicit
HD runtime. Dead/unrelated rows retain their exact evidence and reason. A
hidden listener's bytes with another live route remain covered by C01–C50.

| Candidate | Disposition | Evidence / integration reference or exclusion reason |
| --- | --- | --- |
| `G1` | IMPLEMENTED | tools/BluetoothLeService.java:237-338; All three characteristics found; emits BLE_NOTIFIED inside each service-loop iteration after flags become true. Code/tests: GT / PK / CT / UI; applicable safety adaptations in B01–B29. |
| `G2` | IMPLEMENTED | tools/BluetoothLeService.java:237-338; Sets isPeilin but does not emit BLE_NOTIFIED. Not an advertised scan filter. Conditional on a selected device exposing this service (e.g. also advertising a scanned service or a persisted address); no standalone setup-completion claim. Code/tests: GT / PK / CT / UI; applicable safety adaptations in B01–B29. |
| `G3` | IMPLEMENTED | tools/BluetoothLeService.java:237-338; All three characteristics found; emits BLE_NOTIFIED; additionally subscribes name characteristic after 3000 ms. Code/tests: GT / PK / CT / UI; applicable safety adaptations in B01–B29. |
| `SCAN` | IMPLEMENTED | SearchResultActivity.java:41-120; Two service-filtered scans; QR only adds exact MAC filter. Code/tests: DS / CF; applicable safety adaptations in B01–B29. |
| `CONTROL` | IMPLEMENTED | MainActivity.java:4286-4296; 45 fixed frames and 3 dynamic builders; callsite-census contains247 wrapper callsites. Four final write callsites total including rename. Code/tests: GT / PK / CT / UI; applicable safety adaptations in B01–B29. |
| `NAME1` | IMPLEMENTED | RenameDeviceActivity.java:55-56; P2, G1 flag. Code/tests: DY / GT / UI; applicable safety adaptations in B01–B29. |
| `NAME3` | IMPLEMENTED | RenameDeviceActivity.java:57-68; P3, G3 flag; length/encoding defects preserved. Code/tests: DY / GT / UI; applicable safety adaptations in B01–B29. |
| `LOGIN` | EXCLUDED | tools/BluetoothLeService.java:328-334; Service9e5d1e47-5c13-43a0-8635-82adffc0386f and characteristic9e5d1e47-5c13-43a0-8635-82adffc1386f only cached; no auth read/write/caller. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `READ` | EXCLUDED | tools/BluetoothLeService.java:220-235; readCharacteristic and getSupportedGattServices have no callers. Read callback exists but notifications/write echoes are live routes. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `ALARM` | IMPLEMENTED | MainActivity.java:3144-3218; Clock sync and user settings are BLE bed functions, in scope. Code/tests: DY / UI; applicable safety adaptations in B01–B29. |
| `LEGACY_ALARM` | IMPLEMENTED | MainActivity.java:782-795; Registered START_ALARM receiver can execute legacy sequences. No reachable internal timer start or Worker enqueue; externally delivered broadcast is the condition. No new frame constants beyond command table. Code/tests: WK / UI; applicable safety adaptations in B01–B29. |
| `SCHEDULE` | EXCLUDED | MainActivity.java:920-935; initialOthers has no caller; work requests are never constructed. Worker classes and timer logic remain dormant. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `NOTIFICATIONS` | IMPLEMENTED | MainActivity.java:592-780; Complete9-row parser table; unparsed actuator feedback is not position support. Code/tests: RX / LC; applicable safety adaptations in B01–B29. |
| `LAYOUTS` | IMPLEMENTED | work/report-repair-sol-001/variant-inventory.json; All25 configurations plus three independent transport axes and response-driven features. Code/tests: CF / UI; applicable safety adaptations in B01–B29. |
| `BUGLY` | EXCLUDED | work/jadx/sources/com/tencent/bugly/crashwork/report-repair-sol-001/crash/jni/NativeCrashHandler.java; EXCLUDED: crash reporting and its native logging library. App MyApplication initializes SDK; no BLE command path crosses JNI. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `GIF` | EXCLUDED | work/jadx/sources/pl/droidsonroids/gif/GifInfoHandle.java; EXCLUDED: UI animation decode/render methods map exported JNI symbols; no Bluetooth. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `LICENSE` | EXCLUDED | work/jadx/sources/com/pairip/application/Application.java; EXCLUDED: Google Play license check before Application initialization, no bed protocol or account-control feature. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `HIDDEN_SPLIT_UI` | EXCLUDED | MainActivity.java:2532-2563; Split-specific leg/stop/+/- views remain XML-invisible. Their installed listeners are not normal UI actions; all frame values also have reachable standard UI, generic left/right UI or legacy alarm paths. activity_main.xml1359-1462. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `OLD_LIGHT_PREF` | EXCLUDED | isThereLightActivity.java:12-31; EXCLUDED unused settings Activity, exportedfalse and no launch callsite. Its IsThereLight preference remains read by MainActivity.refreshUnderBedLight at initialization/result100, defaultfalse; persisted value can affect split initial light visibility. No BLE write from this setting. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-backLeftVibrationIntensity1Cmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F1120208011D7E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-backRightVibrationIntensity1Cmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F1220208012D7E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-backVibrationIntensity10Cmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F11202080A267E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-backVibrationIntensity1Cmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F1120208011D7E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-backVibrationIntensity5Cmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F112020805217E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-backVibrationIntensity6Cmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F112020806227E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-backVibrationIntensity7Cmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F112020807237E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-backVibrationIntensity8Cmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F112020808247E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-backVibrationIntensity9Cmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F112020809257E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-getActuatorTimerVibrationStatusCmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F100010B0C7E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-getTimerStatusCmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F1000102037E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-goC_PositionCmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F11801011A7E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-legVibrationIntensity10Cmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F11402080A287E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-legVibrationIntensity1Cmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F1140208011F7E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-legVibrationIntensity1CmdSplitBed` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F1140208011F7E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-legVibrationIntensity5Cmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F114020805237E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-legVibrationIntensity6Cmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F114020806247E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-legVibrationIntensity7Cmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F114020807257E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-legVibrationIntensity8Cmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F114020808267E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-legVibrationIntensity9Cmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F114020809277E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-memoryC_PositionCmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F1170101197E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-resetCmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F1160101187E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-startCmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F1100108197E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CONST-timerCmd` | EXCLUDED | MainActivity.java:97-180; EXCLUDED unreachable constant F1F10E000E7E; no reference or inlined send callsite. Includes unused third memory, reset, timer and extra intensities. Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CALL-MainActivity.java:506` | IMPLEMENTED | MainActivity.java:506; MainActivity.this.mBluetoothLeService.setCharacteristicNotification(); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-MainActivity.java:575` | IMPLEMENTED | MainActivity.java:575; BluetoothLeService.mBluetoothGatt.setCharacteristicNotification(BluetoothLeService.BTnameCharacteristic, true); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-MainActivity.java:580` | IMPLEMENTED | MainActivity.java:580; BluetoothGattDescriptor descriptor = BluetoothLeService.BTnameCharacteristic.getDescriptor(UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-MainActivity.java:583` | IMPLEMENTED | MainActivity.java:583; descriptor.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-MainActivity.java:584` | IMPLEMENTED | MainActivity.java:584; BluetoothLeService.mBluetoothGatt.writeDescriptor(descriptor); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-MainActivity.java:807` | IMPLEMENTED | MainActivity.java:807; MainActivity.this.mBluetoothLeService.connect(MainActivity.mDeviceAddress); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-MainActivity.java:1602` | IMPLEMENTED | MainActivity.java:1602; BluetoothLeService.OutCharacteristic.setValue(hexStringToBytes(str)); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-MainActivity.java:1603` | IMPLEMENTED | MainActivity.java:1603; BluetoothLeService.mBluetoothGatt.writeCharacteristic(BluetoothLeService.OutCharacteristic); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-MainActivity.java:2479` | IMPLEMENTED | MainActivity.java:2479; boolean zConnect = this.mBluetoothLeService.connect(mDeviceAddress); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-MainActivity.java:2627` | IMPLEMENTED | MainActivity.java:2627; this.mBluetoothLeService.disconnect(); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-MainActivity.java:3217` | IMPLEMENTED | MainActivity.java:3217; BluetoothLeService.OutCharacteristic.setValue(hexStringToBytes(str9)); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-MainActivity.java:3218` | IMPLEMENTED | MainActivity.java:3218; BluetoothLeService.mBluetoothGatt.writeCharacteristic(BluetoothLeService.OutCharacteristic); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-MainActivity.java:4288` | IMPLEMENTED | MainActivity.java:4288; BluetoothLeService.OutCharacteristic.setValue(hexStringToBytes(str)); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-MainActivity.java:4289` | IMPLEMENTED | MainActivity.java:4289; BluetoothLeService.mBluetoothGatt.writeCharacteristic(BluetoothLeService.OutCharacteristic); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-RenameDeviceActivity.java:56` | IMPLEMENTED | RenameDeviceActivity.java:56; BluetoothLeService.BTnameCharacteristic.setValue(RenameDeviceActivity.this.name); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-RenameDeviceActivity.java:68` | IMPLEMENTED | RenameDeviceActivity.java:68; BluetoothLeService.BTnameCharacteristic.setValue(bArrHexString2Bytes); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-RenameDeviceActivity.java:70` | IMPLEMENTED | RenameDeviceActivity.java:70; BluetoothLeService.mBluetoothGatt.writeCharacteristic(BluetoothLeService.BTnameCharacteristic); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-SearchResultActivity.java:84` | IMPLEMENTED | SearchResultActivity.java:84; this.mBluetoothAdapter.startLeScan(new UUID[]{UUID.fromString(BluetoothLeService.UUID_SERVICE1)}, this.mLeScanCallback); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-SearchResultActivity.java:97` | IMPLEMENTED | SearchResultActivity.java:97; SearchResultActivity.this.mBluetoothAdapter.stopLeScan(SearchResultActivity.this.mLeScanCallback); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-SearchResultActivity.java:101` | IMPLEMENTED | SearchResultActivity.java:101; SearchResultActivity.this.mBluetoothAdapter.startLeScan(new UUID[]{UUID.fromString(BluetoothLeService.UUID_SERVICE3)}, SearchResultActivity.this.mLeScanCallback); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-SearchResultActivity.java:106` | IMPLEMENTED | SearchResultActivity.java:106; SearchResultActivity.this.mBluetoothAdapter.stopLeScan(SearchResultActivity.this.mLeScanCallback); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:85` | IMPLEMENTED | tools/BluetoothLeService.java:85; Log.i(BluetoothLeService.TAG, "Attempting to start service discovery:" + BluetoothLeService.mBluetoothGatt.discoverServices()); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:184` | IMPLEMENTED | tools/BluetoothLeService.java:184; if (!mBluetoothGatt.connect()) { Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:195` | IMPLEMENTED | tools/BluetoothLeService.java:195; mBluetoothGatt = remoteDevice.connectGatt(this, true, this.mGattCallback); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:207` | IMPLEMENTED | tools/BluetoothLeService.java:207; bluetoothGatt.disconnect(); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:216` | IMPLEMENTED | tools/BluetoothLeService.java:216; bluetoothGatt.close(); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:225` | EXCLUDED | tools/BluetoothLeService.java:225; bluetoothGatt.readCharacteristic(bluetoothGattCharacteristic); Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CALL-tools/BluetoothLeService.java:234` | EXCLUDED | tools/BluetoothLeService.java:234; return bluetoothGatt.getServices(); Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CALL-tools/BluetoothLeService.java:238` | IMPLEMENTED | tools/BluetoothLeService.java:238; for (BluetoothGattService bluetoothGattService : mBluetoothGatt.getServices()) { Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:241` | IMPLEMENTED | tools/BluetoothLeService.java:241; for (BluetoothGattCharacteristic bluetoothGattCharacteristic : bluetoothGattService.getCharacteristics()) { Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:245` | IMPLEMENTED | tools/BluetoothLeService.java:245; mBluetoothGatt.setCharacteristicNotification(bluetoothGattCharacteristic, true); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:246` | IMPLEMENTED | tools/BluetoothLeService.java:246; BluetoothGattDescriptor descriptor = bluetoothGattCharacteristic.getDescriptor(UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:249` | IMPLEMENTED | tools/BluetoothLeService.java:249; descriptor.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:250` | IMPLEMENTED | tools/BluetoothLeService.java:250; mBluetoothGatt.writeDescriptor(descriptor); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:271` | IMPLEMENTED | tools/BluetoothLeService.java:271; for (BluetoothGattCharacteristic bluetoothGattCharacteristic2 : bluetoothGattService.getCharacteristics()) { Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:280` | IMPLEMENTED | tools/BluetoothLeService.java:280; mBluetoothGatt.setCharacteristicNotification(bluetoothGattCharacteristic2, true); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:281` | IMPLEMENTED | tools/BluetoothLeService.java:281; BluetoothGattDescriptor descriptor2 = bluetoothGattCharacteristic2.getDescriptor(UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:284` | IMPLEMENTED | tools/BluetoothLeService.java:284; descriptor2.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:285` | IMPLEMENTED | tools/BluetoothLeService.java:285; mBluetoothGatt.writeDescriptor(descriptor2); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:305` | IMPLEMENTED | tools/BluetoothLeService.java:305; for (BluetoothGattCharacteristic bluetoothGattCharacteristic3 : bluetoothGattService.getCharacteristics()) { Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:309` | IMPLEMENTED | tools/BluetoothLeService.java:309; mBluetoothGatt.setCharacteristicNotification(bluetoothGattCharacteristic3, true); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:310` | IMPLEMENTED | tools/BluetoothLeService.java:310; BluetoothGattDescriptor descriptor3 = this.InCharacteristic.getDescriptor(UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:313` | IMPLEMENTED | tools/BluetoothLeService.java:313; descriptor3.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:314` | IMPLEMENTED | tools/BluetoothLeService.java:314; mBluetoothGatt.writeDescriptor(descriptor3); Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/BluetoothLeService.java:329` | IMPLEMENTED | tools/BluetoothLeService.java:329; for (BluetoothGattCharacteristic bluetoothGattCharacteristic4 : bluetoothGattService.getCharacteristics()) { Code/tests: GT / PK / CT / DY / UI; applicable safety adaptations in B01–B29. |
| `CALL-tools/StringUtil.java:61` | EXCLUDED | tools/StringUtil.java:61; fileInputStream.close(); Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |
| `CALL-tools/StringUtil.java:69` | EXCLUDED | tools/StringUtil.java:69; fileOutputStream.close(); Dead/unreachable or unrelated app/SDK behavior; no missing bed command. |

## Completion and external validation

All reachable discoveries above have a terminal disposition and user-facing
control where applicable. No in-scope feature is deferred for missing hardware
or lack of an existing entity. Existing card discovery consumes the stable
translation keys for covers, memory, massage, lights, timers and switches; no
frontend source or bundle change is needed. Alarm/wake/rename use existing
service forms and configuration-lane serialization.

Physical actuator directions, RGB/human-icon effects, G2 unsolicited startup,
actual GATT properties and persistence still require real-user beta/release
validation. They are external validation, not unimplemented static behavior.
No maintainer hardware acquisition, next-row work, global queue publication,
merge or deployment is included in this unit.
