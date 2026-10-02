# Jordan's Serenity app profile

Select **Jordan's Serenity** manually when the bed uses Android package `com.okin.bedding.serenity`. Shared OKIN advertisements or GATT UUIDs do not identify this app. The implementation follows the independently accepted S01 FULL analysis of version 1.0.1/code 2, with four verified APK/split members. Artifact-set SHA-256: `b0729dc3a4eae2644cc5035b984a05ac116a658b79c886ab1b02eebdea584cc6`. Physical operation is unverified.

[Jordan's Tranquil](tranquil.md) and the [Customatic Z-Series](customatic-z-series.md) apps share this controller core, with their own action tables.

The app always selects CSTProtocol and the Z280 remote/massage screen pair. Persisted bed-type settings do not change that selection. Manufacturer values, including CST13/CST14, never select a protocol and always leave alarm controls disabled. Existing CST product profiles are separate.

## Transport and packets

| Role | UUID |
|---|---|
| Service | `62741523-52f9-8864-b1ab-3b3a8d65950b` |
| Command | `62741525-52f9-8864-b1ab-3b3a8d65950b` |
| Notify | `62741625-52f9-8864-b1ab-3b3a8d65950b` |
| Manufacturer service | `0000180a-0000-1000-8000-00805f9b34fb` |
| Manufacturer read | `00002a29-0000-1000-8000-00805f9b34fb` |

Normal packets are 14 bytes: `0c 02`, a 32-bit primary field in big-endian order, a 32-bit secondary field in big-endian order, then four zero bytes. There is no normal checksum, encryption, side selector, or authentication packet. The existing CST builder is reused because its bytes are equivalent; another product's capabilities are not inherited.

The Android app leaves its characteristic write type unchanged, so the runtime ATT mode is unknown. HA validates the command role and prefers acknowledged writes when `write` is advertised, otherwise using `write-without-response`. This is a host policy, not a recovered fixed Android write mode. Notifications require the exact notify role and remain subscribed with angle sensing disabled. Bleak handles the notification CCCD.

Initial app discovery scans without a service filter and accepts names whose lowercase form starts with `okin`. This shared prefix cannot select Serenity. There is no PIN, bonding, or pairing gate established by the artifact.

## Reachable commands

All values below occupy the primary field unless the secondary column is specified.

| Control | Primary | Secondary |
|---|---:|---:|
| Head/back up, down | `0x1`, `0x2` | 0 |
| Foot/legs up, down | `0x4`, `0x8` | 0 |
| Remote Selector 4 up, down | `0x10`, `0x20` | 0 |
| Remote Selector 5 up, down | `0x40`, `0x80` | 0 |
| Flat | `0x08000000` | 0 |
| Zero Gravity | `0x1000` | 0 |
| M1, M2 | `0x10000`, `0x40000` | 0 |
| TV | `0x4000` | 0 |
| Leisure, exposed through Lounge | `0x2000` | 0 |
| Anti-Snore | `0x8000` | 0 |
| Save Zero Gravity | `0x08001000` | 0 |
| Save M1, Save M2 | `0x08010000`, `0x08040000` | 0 |
| Save TV | `0x08004000` | 0 |
| Head massage cycle | `0x800` | 0 |
| Foot massage cycle | `0x400` | 0 |
| Massage mode cycle | `0x10000000` | 0 |
| Massage timer cycle | `0x200` | 0 |
| Massage toggle | `0x100` | 0 |
| Massage off | `0x02000000` | 0 |
| Wave 1, 2, 3 | 0 | `0x80000`, `0x100000`, `0x200000` |
| Light toggle | `0x20000` | 0 |
| Light on, off | 0 | `0x40`, `0x80` |
| Release/Stop | 0 | 0 |

The held-control service uses these exact `control` values:

- Movement: `head_up`, `head_down`, `foot_up`, `foot_down`, `selector_4_up`, `selector_4_down`, `selector_5_up`, `selector_5_down`.
- Presets: `flat`, `zero_g`, `memory_1`, `tv`, `memory_2`, `leisure`, `anti_snore`.
- Save: `save_zero_g`, `save_memory_1`, `save_tv`, `save_memory_2`.
- Massage: `massage_head_cycle`, `massage_foot_cycle`, `massage_mode_cycle`, `massage_timer_cycle`, `massage_toggle`, `massage_off`, `wave_1`, `wave_2`, `wave_3`.
- Lighting: `light_toggle`, `light_on`, `light_off`.

Light on/off is exposed as a switch that starts unknown and marks commanded values as assumed. The separate **Toggle Light** button preserves the app's native toggle/cycle. Neither control has physical state feedback, RGB selection, or brightness selection.

Only M1 and M2 are numbered memory slots. Separate Save Zero Gravity and Save TV buttons preserve the reachable Flat+preset chords. Save buttons hold for five seconds, matching the bound app help gesture. Frames begin immediately; the app has no five-second command gate or storage acknowledgement. The held action service permits longer holds without assuming a storage acknowledgement.

Touch labels and voice labels conflict for the extra selectors. Remote lumbar controls send selector 4, while the presenter calls that tilt; remote tilt controls send selector 5, while its presenter calls that lumbar. Voice lumbar selects 4 and headtilt selects 5. HA therefore exposes literal **Remote Selector 4/5 Up/Down** buttons rather than assigning unverified physical lumbar/headtilt axes. Only the proven head/feet controls create covers. All covers share the global scheduler resource because every release zeros the whole command.

## Timing and cleanup

Every reachable touch action uses an immediate stream repeated every 100 ms. Handled release/cancel ends that stream and attempts zero packets at +100 and +200 ms from one release timestamp. This applies to motor, preset, save, massage, and light controls. HA preserves those nominal offsets while serializing writes. If the first write finishes after the second deadline, HA attempts the second immediately afterward. HA attempts both cleanup writes even if the first fails, and uses a fresh cancellation event so task cancellation cannot suppress either attempt. A requested elapsed duration ends refresh before cleanup begins.

The `serenity_hold_control` action exposes the controller's literal controls for 0.1–60 seconds, including saves and both extra selectors. Ordinary cover pulses use the configured count with the app's fixed 100 ms interval. Save buttons use the app help gesture's five-second hold; other ordinary button actions use a bounded 500 ms hold. Flat uses the reachable voice path's 1500 ms duration. Voice presets, light commands, and direct massage commands request stop after 500 ms. Exact Android repeat counts at the deadline depend on handler scheduling; HA uses an elapsed ceiling instead of reproducing the boundary race.

The app does not establish valid combined-motor packets. Its shared touch mask is interpreted through exact switch cases; unknown combinations can leave a prior stream running. HA rejects unknown or combined held controls before writing.

The app's voice Stop briefly emits head-up before scheduling Stop. HA excludes that unsafe branch and sends the two zero frames only. It also excludes indefinite voice motion, delayed stops interrupting replacement commands, stale callbacks writing to a newly selected bed, and command callbacks surviving disconnect/background/destruction. HA serializes commands per physical bed and finishes cleanup before replacement.

## Notifications and diagnostic state

The parser accepts each notification independently. Inputs of ten bytes or fewer are ignored. The app does not validate the first byte, header, checksum, or frame length beyond that guard; HA preserves these recognition rules and signed byte values.

If byte 1 is 12, the parser reads signed repeat/hour/minute from bytes 4/6/7, maps subtype byte 5 to alarm type, and reads enabled as byte 9 equal to 1. Subtypes 1–9 map to types 9/17/18/16/20/19/18/9/21; unknown subtypes retain the previous type. Alarm replies are reachable even though alarm commands/UI are dead. HA exposes diagnostic alarm state and adds no alarm-writing action.

Other notifications use signed byte 10 as a change-only status code. With a pending save, the next changed code reports the source's local save event and clears that pending code; it does not update the timer. Release, movement, massage, light controls, duplicate status codes, and alarm replies preserve a pending save. Any preset recall clears it. The local event codes are 5 for Zero Gravity, 4 for M1, 6 for TV, and 8 for M2. Otherwise the changed code updates the massage timer code. Codes 1/2/3 select 10/20/30 minutes in the app; other signed values remain raw and have unknown duration. This is a selected timer, not remaining time.

HA supplies the active callback equivalent, copies notification bytes immediately, and scopes state to one controller. It does not reproduce null callback crashes, mutable-buffer callback races, or app-global state leaking between selected devices. The diagnostic save event is not proof of successful physical storage. The app records intent before transmission, so a failed or cancelled save write can still produce this local event on a later changed status.

Diagnostic state keys: `serenity_manufacturer`, `serenity_status_code`, `serenity_massage_timer_code`, `serenity_massage_timer_minutes`, `serenity_save_event_code`, and `serenity_alarm_type`. Alarm sensor attributes use `serenity_alarm_repeat`, `serenity_alarm_hour`, `serenity_alarm_minute`, and `serenity_alarm_on`. Controller diagnostics also include the pending save code.

Manufacturer is read one second after subscription, with the exact Information service/read property required. Missing information or read failures do not block control. **Refresh Manufacturer** repeats the reachable on-resume read. Text decodes using UTF-8 with replacement, the modern Android default charset. Manufacturer never enables alarms or changes capabilities.

## Exclusions and validation

Excluded dead artifact paths include Z230 and legacy remote screens, alarm/current-time/query/clock-adjustment builders, combined selector-3 helpers, direct massage level/timer/query helpers without callers, the unused presenter speech map, unused save timer/checksum helpers, and child-lock artwork without a command. Android speech recognition, help graphics, localization, framework code, connector-map/UI plumbing, and BLE library internals are outside BLE protocol implementation. Unsafe callback and voice behavior is excluded as described above.

Focused vectors in `tests/test_serenity.py` account for all 45 reachable action rows, with CMD32 explicitly mapped to safe Stop rather than head-up. They cover signed parser branches, unknown alarm types, save-event persistence and diversion, deadlines, cancellation-safe double release, independent release attempts after a write failure, button routing, exact GATT role/property validation, subscription/read ordering, and optional manufacturer failures. Physical actuator mapping, save outcomes, ATT compatibility, and notification meanings remain deferred external validation.
