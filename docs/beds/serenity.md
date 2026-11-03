# Jordan's Serenity

**Status:** ❓ Needs testing (APK-verified, physical operation unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Beds controlled with the Jordan's Serenity app (Android package `com.okin.bedding.serenity`)
- OKIN receivers; their Bluetooth names (lowercase form starting with `okin`) are shared with other apps
- Sibling apps on the same controller core, each with its own action table:
  [Jordan's Tranquil](tranquil.md) and the [Customatic Z-Series](customatic-z-series.md)

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Jordan's Serenity](https://play.google.com/store/apps/details?id=com.okin.bedding.serenity) 1.0.1 (code 2) | `com.okin.bedding.serenity` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head/back and foot/legs covers; Remote Selector 4/5 as literal buttons |
| Position Feedback | ❌ |
| Memory Presets | ✅ (M1, M2; plus Save Zero Gravity and Save TV) |
| Presets | ✅ Flat, Zero Gravity, TV, Leisure (exposed through Lounge), Anti-Snore |
| Massage | ✅ (head/foot/mode/timer cycles, toggle, off, Wave 1-3) |
| Lights | ✅ (native toggle, assumed-state on/off switch; no RGB or brightness) |
| Alarms | ❌ (alarm replies are parsed as diagnostic state only) |
| Diagnostic state | ✅ (manufacturer, status code, massage timer, save event, alarm reply) |

## Protocol Details

**Service UUID:** `62741523-52f9-8864-b1ab-3b3a8d65950b`
**Write Characteristic:** `62741525-52f9-8864-b1ab-3b3a8d65950b`
**Notify Characteristic:** `62741625-52f9-8864-b1ab-3b3a8d65950b`
**Manufacturer Read:** service `0000180a-0000-1000-8000-00805f9b34fb`, characteristic `00002a29-0000-1000-8000-00805f9b34fb`
**Format:** 14-byte CST frame: `0c 02`, a 32-bit primary field and a 32-bit
secondary field (both big-endian), then four zero bytes

### Packet Format

```text
[0x0C, 0x02, primary(4, big-endian), secondary(4, big-endian), 0x00, 0x00, 0x00, 0x00]
```

- No normal checksum, encryption, side selector, or authentication packet.
- The existing CST builder is reused because its bytes are equivalent; another
  product's capabilities are not inherited.
- Examples: Head up `0c 02 00 00 00 01 00 00 00 00 00 00 00 00`, Wave 1
  `0c 02 00 00 00 00 00 08 00 00 00 00 00 00`, Release/Stop is `0c 02` plus
  twelve zero bytes.

### Write Mode

- The Android app leaves its characteristic write type unchanged, so the runtime
  ATT mode is unknown.
- HA validates the command role and prefers acknowledged writes when `write` is
  advertised, otherwise using `write-without-response`. This is a host policy,
  not a recovered fixed Android write mode.
- Notifications require the exact notify role and remain subscribed with angle
  sensing disabled. Bleak handles the notification CCCD.

## Detection / Setup

- Select **Jordan's Serenity** manually. Shared OKIN advertisements or GATT UUIDs
  do not identify this app.
- Initial app discovery scans without a service filter and accepts names whose
  lowercase form starts with `okin`. This shared prefix cannot select Serenity.
- The app always selects CSTProtocol and the Z280 remote/massage screen pair.
  Persisted bed-type settings do not change that selection.
- Manufacturer values, including CST13/CST14, never select a protocol and always
  leave alarm controls disabled. Existing CST product profiles are separate.
- There is no PIN, bonding, or pairing gate established by the artifact.

## Reachable commands

Values occupy the primary field unless a secondary value is listed. The
held-control service (`hold_control`) uses these exact `control` values.

### Motor Control

| Command | `control` | Primary | Secondary |
|---------|-----------|--------:|----------:|
| Head/back up, down | `head_up`, `head_down` | `0x1`, `0x2` | 0 |
| Foot/legs up, down | `foot_up`, `foot_down` | `0x4`, `0x8` | 0 |
| Remote Selector 4 up, down | `selector_4_up`, `selector_4_down` | `0x10`, `0x20` | 0 |
| Remote Selector 5 up, down | `selector_5_up`, `selector_5_down` | `0x40`, `0x80` | 0 |
| Release/Stop | | 0 | 0 |

Touch labels and voice labels conflict for the extra selectors:

- Remote lumbar controls send selector 4, while the presenter calls that tilt.
- Remote tilt controls send selector 5, while its presenter calls that lumbar.
- Voice lumbar selects 4 and headtilt selects 5.

HA therefore exposes literal **Remote Selector 4/5 Up/Down** buttons rather than
assigning unverified physical lumbar/headtilt axes. Only the proven head/feet
controls create covers. All covers share the global scheduler resource because
every release zeros the whole command.

### Presets

| Command | `control` | Primary | Secondary |
|---------|-----------|--------:|----------:|
| Flat | `flat` | `0x08000000` | 0 |
| Zero Gravity | `zero_g` | `0x1000` | 0 |
| TV | `tv` | `0x4000` | 0 |
| Leisure, exposed through Lounge | `leisure` | `0x2000` | 0 |
| Anti-Snore | `anti_snore` | `0x8000` | 0 |

### Memory

| Command | `control` | Primary | Secondary |
|---------|-----------|--------:|----------:|
| M1, M2 | `memory_1`, `memory_2` | `0x10000`, `0x40000` | 0 |
| Save Zero Gravity | `save_zero_g` | `0x08001000` | 0 |
| Save M1, Save M2 | `save_memory_1`, `save_memory_2` | `0x08010000`, `0x08040000` | 0 |
| Save TV | `save_tv` | `0x08004000` | 0 |

- Only M1 and M2 are numbered memory slots. Separate Save Zero Gravity and Save
  TV buttons preserve the reachable Flat+preset chords.
- Save buttons hold for five seconds, matching the bound app help gesture.
  Frames begin immediately; the app has no five-second command gate or storage
  acknowledgement.
- The held action service permits longer holds without assuming a storage
  acknowledgement.

### Massage

| Command | `control` | Primary | Secondary |
|---------|-----------|--------:|----------:|
| Head massage cycle | `massage_head_cycle` | `0x800` | 0 |
| Foot massage cycle | `massage_foot_cycle` | `0x400` | 0 |
| Massage mode cycle | `massage_mode_cycle` | `0x10000000` | 0 |
| Massage timer cycle | `massage_timer_cycle` | `0x200` | 0 |
| Massage toggle | `massage_toggle` | `0x100` | 0 |
| Massage off | `massage_off` | `0x02000000` | 0 |
| Wave 1, 2, 3 | `wave_1`, `wave_2`, `wave_3` | 0 | `0x80000`, `0x100000`, `0x200000` |

### Lights

| Command | `control` | Primary | Secondary |
|---------|-----------|--------:|----------:|
| Light toggle | `light_toggle` | `0x20000` | 0 |
| Light on, off | `light_on`, `light_off` | 0 | `0x40`, `0x80` |

Light on/off is exposed as a switch that starts unknown and marks commanded
values as assumed. The separate **Toggle Light** button preserves the app's
native toggle/cycle. Neither control has physical state feedback, RGB
selection, or brightness selection.

## Command Timing

| Operation | Hold | Source |
|-----------|------|--------|
| Every reachable touch action | Immediate stream repeated every 100 ms | App |
| Ordinary cover pulses | Configured count at the app's fixed 100 ms interval | HA setting |
| Save buttons | Five seconds | App help gesture |
| Flat | 1500 ms | Reachable voice path |
| Voice presets, light commands, direct massage commands | Stop requested after 500 ms | Voice path |
| Other ordinary button actions | Bounded 500 ms | HA policy |
| `hold_control` | 0.1–60 seconds, any literal control including saves and both extra selectors | HA service |

Release and cleanup:

- Handled release/cancel ends the stream and attempts zero packets at +100 and
  +200 ms from one release timestamp. This applies to motor, preset, save,
  massage, and light controls.
- HA preserves those nominal offsets while serializing writes. If the first
  write finishes after the second deadline, HA attempts the second immediately
  afterward.
- HA attempts both cleanup writes even if the first fails, and uses a fresh
  cancellation event so task cancellation cannot suppress either attempt.
- A requested elapsed duration ends refresh before cleanup begins.
- Exact Android repeat counts at the deadline depend on handler scheduling; HA
  uses an elapsed ceiling instead of reproducing the boundary race.
- The app does not establish valid combined-motor packets. Its shared touch mask
  is interpreted through exact switch cases; unknown combinations can leave a
  prior stream running. HA rejects unknown or combined held controls before
  writing.

## Notifications and diagnostic state

The parser accepts each notification independently:

- Inputs of ten bytes or fewer are ignored. The app does not validate the first
  byte, header, checksum, or frame length beyond that guard; HA preserves these
  recognition rules and signed byte values.
- **Alarm reply** (byte 1 is 12): signed repeat/hour/minute from bytes 4/6/7,
  subtype byte 5 mapped to alarm type, enabled when byte 9 equals 1. Subtypes
  1–9 map to types 9/17/18/16/20/19/18/9/21; unknown subtypes retain the
  previous type. Alarm replies are reachable even though alarm commands/UI are
  dead. HA exposes diagnostic alarm state and adds no alarm-writing action.
- **Status code** (other notifications): signed byte 10 is a change-only status
  code.
  - With a pending save, the next changed code reports the source's local save
    event and clears that pending code; it does not update the timer.
  - Release, movement, massage, light controls, duplicate status codes, and
    alarm replies preserve a pending save. Any preset recall clears it.
  - Local save event codes: 5 for Zero Gravity, 4 for M1, 6 for TV, and 8 for M2.
  - Otherwise the changed code updates the massage timer code. Codes 1/2/3
    select 10/20/30 minutes in the app; other signed values remain raw and have
    unknown duration. This is a selected timer, not remaining time.

| State | Keys |
|-------|------|
| Diagnostic state | `serenity_manufacturer`, `serenity_status_code`, `serenity_massage_timer_code`, `serenity_massage_timer_minutes`, `serenity_save_event_code`, `serenity_alarm_type` |
| Alarm sensor attributes | `serenity_alarm_repeat`, `serenity_alarm_hour`, `serenity_alarm_minute`, `serenity_alarm_on` |
| Controller diagnostics | Also include the pending save code (`save_pending_code`) |

HA-specific handling:

- HA supplies the active callback equivalent, copies notification bytes
  immediately, and scopes state to one controller. It does not reproduce null
  callback crashes, mutable-buffer callback races, or app-global state leaking
  between selected devices.
- The diagnostic save event is not proof of successful physical storage. The app
  records intent before transmission, so a failed or cancelled save write can
  still produce this local event on a later changed status.

### Manufacturer

- Read one second after subscription, with the exact Information service/read
  property required. Missing information or read failures do not block control.
- **Refresh Manufacturer** repeats the reachable on-resume read.
- Text decodes using UTF-8 with replacement, the modern Android default charset.
- Manufacturer never enables alarms or changes capabilities.

## Notes

### Safety adaptations

- The app's voice Stop briefly emits head-up before scheduling Stop. HA excludes
  that unsafe branch and sends the two zero frames only.
- HA also excludes indefinite voice motion, delayed stops interrupting
  replacement commands, stale callbacks writing to a newly selected bed, and
  command callbacks surviving disconnect/background/destruction.
- HA serializes commands per physical bed and finishes cleanup before
  replacement.

### Exclusions

- Excluded dead artifact paths: Z230 and legacy remote screens,
  alarm/current-time/query/clock-adjustment builders, combined selector-3
  helpers, direct massage level/timer/query helpers without callers, the unused
  presenter speech map, unused save timer/checksum helpers, and child-lock
  artwork without a command.
- Android speech recognition, help graphics, localization, framework code,
  connector-map/UI plumbing, and BLE library internals are outside BLE protocol
  implementation.
- Unsafe callback and voice behavior is excluded as described above.

### Validation

- Focused vectors in `tests/test_serenity.py` account for all 45 reachable action
  rows, with CMD32 explicitly mapped to safe Stop rather than head-up.
- They cover signed parser branches, unknown alarm types, save-event persistence
  and diversion, deadlines, cancellation-safe double release, independent
  release attempts after a write failure, button routing, exact GATT
  role/property validation, subscription/read ordering, and optional
  manufacturer failures.
- Physical actuator mapping, save outcomes, ATT compatibility, and notification
  meanings remain deferred external validation.

### Analysis provenance

- Independently accepted S01 FULL analysis of `com.okin.bedding.serenity`
  version 1.0.1/code 2, with four verified APK/split members.
- Artifact-set SHA-256: `b0729dc3a4eae2644cc5035b984a05ac116a658b79c886ab1b02eebdea584cc6`
- Discovery ledger: [S01 dispositions](../apk-analysis/dispositions/S01-serenity.md)
