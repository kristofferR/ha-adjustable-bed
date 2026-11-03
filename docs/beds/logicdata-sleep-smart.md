# LOGICDATA Sleep Smart Air Mattress app

**Status:** ❓ Needs testing. **Static verified, hardware unverified.**

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

The "Sleep Smart Air Mattress" app controls two separate Bluetooth devices, the
adjustable bed base and the air mattress pump, so Home Assistant configures them
as two entries:

| Device | Bed type | Setup choice |
|---|---|---|
| Bed base | `logicdata_app`, app profile `sleep_smart` | **Logicdata → MotionRelax / Sleep Smart bed apps**, then **Sleep Smart Air Mattress app (bed)** |
| Air pump | `logicdata_air_pump` | **Logicdata → Sleep Smart air mattress pump** |

## Known Models

- Vienna and Toronto beds (command family `p1`)
- Middle Rail bed (command family `p2`)
- Sleep Smart air mattress pump

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Sleep Smart Air Mattress](https://play.google.com/store/apps/details?id=com.logicdata.app.mattress.bed) 1.0.0 (1) | `com.logicdata.app.mattress.bed` |

## Features

| Feature | Bed base | Air pump |
|---------|----------|----------|
| Motor Control | ✅ Back, legs, both | ❌ |
| Position Feedback | ❌ | ❌ |
| Presets | ✅ Flat, Zero Gravity, Anti-Snore (hold-only) | ❌ |
| Memory | ✅ (1 slot) | ✅ Pressure memory recall and save |
| Massage | ✅ (Off and levels 1–3 per zone, stop, mode, **Massage mode** sensor) | ❌ |
| Lights | ✅ (under-bed toggle) | ❌ |
| Factory Reset | ⚠️ (disabled by default) | ❌ |
| Inflate / Deflate / Firmness 30 | ❌ | ✅ |
| Pressure Reading | ❌ | ✅ (**Air pressure** sensor, no unit) |
| Bluetooth Rename | ✅ (T1 or T3 name role) | ✅ |

## Protocol Details

### Bed base

The bed uses the same three GATT transports and `F1 F1 | opcode | length |
payload | checksum | 7E` framing as the [MOTIONrelax profiles](logicdata-app-disposition.md#transport-framing-and-initialization),
but its controls, startup and rename differ.

| Transport | Service | Write | Notify | Name |
|-----------|---------|-------|--------|------|
| T1 | `0000ff12-0000-1000-8000-00805f9b34fb` | `0000ff01-0000-1000-8000-00805f9b34fb` | `0000ff02-0000-1000-8000-00805f9b34fb` | `0000ff06-0000-1000-8000-00805f9b34fb` |
| T2 | `88121427-11e2-52a2-4615-ff00dec16800` | `88121427-11e2-52a2-4615-ff00dec16801` | same as write | none |
| T3 | `0000fe60-0000-1000-8000-00805f9b34fb` | `0000fe61-0000-1000-8000-00805f9b34fb` | `0000fe62-0000-1000-8000-00805f9b34fb` | `0000fe63-0000-1000-8000-00805f9b34fb` |

### Air pump

**Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `ffe1` (with response)
**Notify Characteristic:** `ffe2`
**Format:** LF-terminated text

There is no pairing, authentication or initialization frame.

## Detection / Setup

- Neither device can be identified from its advertisement. The bed's `ff12` and
  `fe60` services are shared with other Jiecang/Lierda-based apps, and the
  pump's `ffe0` service is a common serial-bridge service.
- Select both types manually; existing entries keep their bed type.

### Bed configuration

| Setting | Choices |
|---|---|
| Command family | `p1` for the Vienna and Toronto beds; `p2` for the Middle Rail bed |
| Layout | `standard_2` (standard series) or `split_series` (split series) |
| Massage | Enable when the bed has massage. The app's massage tab is reachable for every bed profile |
| Light | Enable for under-bed lighting |
| Transport | `auto`, `t1`, `t2` or `t3`, as for MOTIONrelax |

- The app always ends with a two-motor movement layout: back, legs and both
  together. Its three- and four-motor and split-movement handlers are hidden
  before they can be used, so they are not exposed.
- The series only chooses the massage zones: standard has back and foot, split
  has left back and right back.
- The Middle Rail family changes only back and legs movement to the two-byte
  zero payload. Combined movement, presets, memory, light and massage keep their
  P1 frames.

## Bed base

### Motor Control

| Command | P1 | P2 (Middle Rail) |
|---------|----|------------------|
| Back Up | `F1 F1 01 01 01 03 7E` | `F1 F1 01 02 00 00 03 7E` |
| Back Down | `F1 F1 02 01 01 04 7E` | `F1 F1 02 02 00 00 04 7E` |
| Legs Up | `F1 F1 03 01 01 05 7E` | `F1 F1 03 02 00 00 05 7E` |
| Legs Down | `F1 F1 04 01 01 06 7E` | `F1 F1 04 02 00 00 06 7E` |
| Both Up | `F1 F1 05 01 01 07 7E` | `F1 F1 05 01 01 07 7E` |
| Both Down | `F1 F1 06 01 01 08 7E` | `F1 F1 06 01 01 08 7E` |
| Release | `F1 F1 4E 00 4E 7E` | `F1 F1 4E 00 4E 7E` |

### Presets and Memory

All families use these P1 frames.

| Command | Bytes (hex) |
|---------|-------------|
| Flat | `F1 F1 08 01 01 0A 7E` |
| Zero Gravity | `F1 F1 07 01 01 09 7E` |
| Anti-Snore | `F1 F1 09 01 01 0B 7E` |
| Memory 1 recall | `F1 F1 0B 01 01 0D 7E` |
| Memory 1 save | `F1 F1 0A 00 0A 7E` |

### Massage

| HA zone | Off | Level 1 | Level 2 | Level 3 |
|---------|-----|---------|---------|---------|
| Head (back; left back on split) | `F1 F1 12 02 08 00 1C 7E` | `F1 F1 12 02 08 02 1E 7E` | `F1 F1 12 02 08 03 1F 7E` | `F1 F1 12 02 08 04 20 7E` |
| Foot (standard) | `F1 F1 14 02 08 00 1E 7E` | `F1 F1 14 02 08 02 20 7E` | `F1 F1 14 02 08 03 21 7E` | `F1 F1 14 02 08 04 22 7E` |
| Right back (split) | `F1 F1 22 02 08 00 2C 7E` | `F1 F1 22 02 08 02 2E 7E` | `F1 F1 22 02 08 03 2F 7E` | `F1 F1 22 02 08 04 30 7E` |

| Command | Bytes (hex) |
|---------|-------------|
| Massage stop | `F1 F1 11 01 08 1A 7E` |
| Massage mode | `F1 F1 16 01 0A 21 7E` |
| Massage query | `F1 F1 00 02 08 00 0A 7E` |

### Other Commands

| Command | Bytes (hex) |
|---------|-------------|
| Under-bed light toggle | `F1 F1 0F 00 0F 7E` (P1 for every bed profile) |
| Two-byte release | `F1 F1 4E 02 00 00 50 7E` |
| Factory reset | `F1 F1 1D 02 00 00 1F 7E` |

### Controls

| Control | Behavior |
|---|---|
| Back, legs, both | Repeat every 100 ms; on release one final movement frame, then `F1 F1 4E 00 4E 7E` after 100 ms |
| Flat, Zero Gravity, Anti-Snore, Memory 1 recall | Hold-only in the app: a tap sends nothing. A button holds the preset for the motor pulse count × 200 ms, refreshing every 200 ms, then releases 100 ms later |
| `logicdata_hold_preset` | The same hold for an explicit 0.2–60 s duration |
| Memory 1 save | One `F1 F1 0A 00 0A 7E`, without a release. The app has one memory slot |
| Under-bed light | Toggle, then releases at +80 ms (both forms) and +100 ms |
| Massage intensity | Off and levels 1–3 per zone (wire values 0/2/3/4) |
| Massage stop / mode | Massage stop only stops massage. Mode sends its fixed frame, a two-byte release at +1000 ms and a short release at +1100 ms |
| Refresh massage state | The massage tab's parameter query, sent at 100, 250 and 450 ms |
| Factory reset | Disabled by default. One reset frame; the app warns that it deletes stored memories and that a later held DOWN performs a reference drive |
| `rename` | `01 FC 07`, byte length and UTF-8 name on the name characteristic, once |

Cancellation and failures always finish with the release frame, even though the
app's key-release and cancel paths do not.

### Startup and state

- Only a T3 connection becomes ready in the app: both T3 subscriptions (data and
  name) must succeed. HA subscribes 300 ms after service discovery and adds the
  T3 name subscription 100 ms after the data subscription.
- A T3 service next to a selected T1 or T2 transport also makes the bed ready,
  and startup queries then use the selected write role.
- T1 or T2 alone stays silent until a control is used. A failed name
  subscription leaves controls available without queries.

When ready, the integration sends the app's two startup schedules: software,
vibration, hardware, actuator, light and device-status queries between 300 and
2700 ms, merged with the actuator, hardware (or Middle Rail software) and
vibration pairs at 1000–1500 ms (offsets from readiness):

| Offset | Query | Bytes (hex) |
|--------|-------|-------------|
| 300 ms | Software | `F1 F1 00 02 40 00 42 7E` |
| 600 ms | Vibration | `F1 F1 00 01 08 09 7E` |
| 900 ms | Hardware | `F1 F1 00 01 40 41 7E` |
| 1000, 1100, 1200, 1500 ms | Actuator | `F1 F1 00 01 50 51 7E` |
| 1200, 1300 ms | Hardware (Middle Rail: software) | `F1 F1 00 01 40 41 7E` (P2 `F1 F1 00 02 40 00 42 7E`) |
| 1400, 1500 ms | Vibration | `F1 F1 00 01 08 09 7E` |
| 1800, 2100 ms | Light | `F1 F1 00 02 01 00 03 7E` |
| 2400, 2700 ms | Device status | `F1 F1 00 00 00 7E` |

Replies set the under-bed light state, massage levels and a **Massage mode**
sensor (long interval, short interval, wave or continuous; unknown for other
values). A clock request (`F2 F2 50`) is answered with the current local time.
No positions, firmware, model or calibration are reported.

| Notification | Meaning |
|--------------|---------|
| `F2 F2 50` | Clock request; every request is answered |
| `F2 F2 0D`, 5+ bytes | Massage mode from byte 4, read as two hex digits parsed as decimal: `01` long interval, `02` short interval, `03` wave, `04` continuous; non-decimal text is ignored |
| Byte 2 `05`/`06`, 9+ bytes | Light on from byte 8 bit 6; `06` also reports massage levels in bytes 4 and 6 |

### Rename

- Names are 1–20 characters from `0-9`, `a-z`, `A-Z`, `ä`, `ö`, `ü`, `Ä`, `Ö`,
  `Ü` and `ß`, the app's edit-field alphabet, and at most 100 UTF-8 bytes.
- T1 writes to `ff06` and T3 to `fe63`.
- T2 has no name characteristic of its own; when T3 or T1 is also present, the
  app keeps that name role, and so does the integration (T3 first).

## Air pump

### Commands

| Button | Text |
|---|---|
| Inflate (also the app's "60" mode) | `C>FILL>0` |
| Deflate | `C>EXCAPE>0` |
| Firmness 30 | `C>SETP>0>30` |
| Recall pressure memory | `C>MEMORY>0` |
| Save pressure memory | `C>STOPN`, then `C>MEM_S>0` |
| Stop | `C>STOPN` |
| Pressure query | `R>SP>0` |

Each text is sent with a trailing LF (`\n`).

### Command Timing

- A tap sends one command; the pump keeps running until its own logic or a stop.
- The app accepts a tap at most every 500 ms. The integration waits out the rest
  of that interval instead of dropping the tap, so a save always follows its
  stop by at least 500 ms.
- Stop is never delayed.

### Pressure

- While connected, **Air pressure** is queried with `R>SP>0` 800 ms after setup
  and then every 500 ms, like the app's pump tab.
- A reply starting `RET>SP>` with at least 15 characters is decoded from
  characters 13–14 as signed hexadecimal.
- The value is shown as received; the app defines no unit.
- The reading clears when the link closes. New pump entries keep the link
  between commands for the idle timeout so the reading stays current.

### Rename

`rename` renames the pump with `AT+ENAT`, `AT+LENA<name>` after 50 ms
and `AT+REST` after 100 ms, each ending in CR LF. The pump restarts afterwards.
Names follow the same alphabet with at most 20 characters (and at most 40
UTF-8 bytes).

## Not implemented

- The app's alarm scheduler, alternative Bluetooth manager, connection pool,
  pump copy service and old layouts have no live caller.
- The login characteristic is looked up but never used.
- Reconnect dialogs, QR-code address entry, scan lists and Android permission
  flows belong to the phone app; Home Assistant connects to the configured
  address.
- No Wi-Fi, cloud, firmware update, position feedback, child lock or advanced
  lighting exists in the app.

## Notes

### Analysis provenance

- Package `com.logicdata.app.mattress.bed` **1.0.0 (1)**. Both devices follow
  the accepted APK Protocol Audit report for this version.
- The comparison ledger is
  [row053](../apk-analysis/dispositions/row053-logicdata-sleep-smart.md).

### Deferred hardware checks

Later hardware checks should confirm motor stopping, pressure units and scale,
the pump's response to rapid taps and the three rename phases, and which
services real beds expose.
