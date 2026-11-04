# LOGICDATA MOTIONrelax phone and tablet apps

**Status:** ❓ Needs testing. **Static verified, hardware unverified.**

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

These explicit app profiles implement the accepted APK Protocol Audit
cluster-006 evidence. The Sleep Smart Air Mattress app uses the same bed type
with app profile `sleep_smart`; see [Sleep Smart](logicdata-sleep-smart.md).

## Known Models

- LOGICDATA MOTIONrelax beds, standard (P1) and middle-motor (P2) families
- Vienna and Toronto: aliases for two-motor layouts with different massage settings
- Existing [Jiecang](jiecang.md#legacy-route) and [SILVERmotion/SimplicityFrame](logicdata.md)
  configurations retain their previous behavior.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [MOTIONrelax phone](https://play.google.com/store/apps/details?id=com.logicdata.app.android.bed) 1.0.6 (7) | `com.logicdata.app.android.bed` |
| ✅ | [MOTIONrelax tablet](https://play.google.com/store/apps/details?id=com.logicdata.app.android.pad.bed) 1.0.4 (5) | `com.logicdata.app.android.pad.bed` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (per layout; see [Layouts](#layouts)) |
| Position Feedback | ❌ (neither app reports motor positions) |
| Presets | ✅ P1: Flat, Zero-G, Anti-Snore. P2: Flat |
| Memory Presets | ✅ (2 slots, recall and save, both families) |
| Held Presets | ✅ P2: `adjustable_bed.logicdata_hold_preset` |
| Massage | ✅ P1 only: Off and levels 1–3 per zone, mode, stop |
| Lights | ✅ (toggle with notification readback; no brightness or RGB) |
| Clock | ✅ Phone app (both families); ❌ tablet |
| Alarm | ✅ Phone app with P1; ❌ tablet |
| Bluetooth Rename | ✅ (T1 or T3) |

## Protocol Details

| Transport | Service | Write | Notify | Name |
|-----------|---------|-------|--------|------|
| T1 | `0000ff12-0000-1000-8000-00805f9b34fb` | `0000ff01-0000-1000-8000-00805f9b34fb` | `0000ff02-0000-1000-8000-00805f9b34fb` | `0000ff06-0000-1000-8000-00805f9b34fb` |
| T2 | `88121427-11e2-52a2-4615-ff00dec16800` | `88121427-11e2-52a2-4615-ff00dec16801` | same as write | none |
| T3 | `0000fe60-0000-1000-8000-00805f9b34fb` | `0000fe61-0000-1000-8000-00805f9b34fb` | `0000fe62-0000-1000-8000-00805f9b34fb` | `0000fe63-0000-1000-8000-00805f9b34fb` |

**Format:** `F1 F1 | opcode | length | payload | checksum | 7E`, where checksum
is the low byte of opcode + length + payload. P1 frames normally carry payload
`01`; P2 frames carry `00 00`.

### Transport Selection

- Automatic transport selection keeps each service's write, notification and
  name characteristics together. It needs exactly one complete transport; when
  GATT is ambiguous, select one explicitly.
- Explicit T1, T2 and T3 choices are available.
- T2 can be used through a known address, but its standalone route has no
  startup query burst in either app.
- No PIN or pairing flow is inferred from these artifacts.

### Write Mode

Writes use a response when the characteristic advertises `write`, otherwise
write-without-response.

### Startup Queries

HA waits 1 s, subscribes to notifications, then (when a T1 or T3 transport is
present) sends each query twice, 100 ms apart:

| Offset | Query | Phone | Tablet |
|--------|-------|-------|--------|
| 1000 ms | Actuator | `F1 F1 00 01 50 51 7E` | `F1 F1 00 01 01 02 7E` |
| 1200 ms | Hardware | P1 `F1 F1 00 01 40 41 7E`, P2 `F1 F1 00 02 40 00 42 7E` | Same |
| 1400 ms | Vibration | `F1 F1 00 01 08 09 7E` | Same |
| 3000 ms, 3100 ms | Clock | Clock frame | None |

On T3, the name characteristic is also subscribed at 3000 ms.

## Detection / Setup

1. Select the LOGICDATA MOTIONrelax app option.
2. Choose the phone or tablet app, packet family, and physical layout.

- The Bluetooth service alone cannot identify those choices.
- Choose the dedicated middle layout with P2; the remaining layouts use P1.
- If the bed's family reply contradicts the configured family, controls other
  than release are refused until the bed is reconfigured. The disabled-by-default
  `logicdata_app_family_match` sensor shows the result.

### Layouts

The standard family supports two motors; three motors with neck, lumbar, height
or split-upper controls; four motors; and split-series controls. Standard layouts
have independent massage and under-bed light settings. The middle-motor family
provides back, legs, flat, two memory slots and lighting.

| Layout | Family | Movement axes | Massage zones |
|--------|--------|---------------|---------------|
| `standard_2` | P1 | Back, legs, both | Back, foot |
| `standard_3_neck` | P1 | Back, legs, head (neck) | Back, foot |
| `standard_3_lumbar` | P1 | Back, legs, lumbar | Back, foot |
| `standard_3_hi_low` | P1 | Back, legs, bed height | Back, foot |
| `standard_3_split_upper` | P1 | Back, right back, both backs, legs | Back, foot |
| `standard_4` | P1 | Head, back, lumbar, legs | Back, foot |
| `split_series` | P1 | Back, right back, legs | Back, right |
| `middle` | P2 | Back, legs | None |

### Paired Beds

For two separately addressed beds, configure each side before combining them.
Shared paired-bed options preserve each side's app, packet family, layout and
transport. Unpair temporarily to change those per-side settings.

## Commands

The [whole-cluster disposition](logicdata-app-disposition.md) records every
reachable command.

### Motor Control

| Axis | P1 up / down | P2 (middle) up / down |
|------|--------------|-----------------------|
| Back | `F1 F1 01 01 01 03 7E` / `F1 F1 02 01 01 04 7E` | `F1 F1 01 02 00 00 03 7E` / `F1 F1 02 02 00 00 04 7E` |
| Legs | `F1 F1 03 01 01 05 7E` / `F1 F1 04 01 01 06 7E` | `F1 F1 03 02 00 00 05 7E` / `F1 F1 04 02 00 00 06 7E` |
| Both | `F1 F1 05 01 01 07 7E` / `F1 F1 06 01 01 08 7E` | n/a |
| Head (neck), bed height | `F1 F1 19 01 01 1B 7E` / `F1 F1 1A 01 01 1C 7E` | n/a |
| Lumbar | `F1 F1 1B 01 01 1D 7E` / `F1 F1 1C 01 01 1E 7E` | n/a |
| Right back | `F1 F1 20 01 01 22 7E` / `F1 F1 21 01 01 23 7E` | n/a |
| Both backs | `F1 F1 23 01 01 25 7E` / `F1 F1 24 01 01 26 7E` | n/a |
| Release (all) | `F1 F1 4E 00 4E 7E` | `F1 F1 4E 00 4E 7E` |

Every axis uses the global release, so all motor controls on one bed share one
scheduler resource.

### Presets and Memory

| Command | P1 | P2 |
|---------|----|----|
| Flat | `F1 F1 08 01 01 0A 7E` | `F1 F1 08 02 00 00 0A 7E` |
| Zero-G | `F1 F1 07 01 01 09 7E` | n/a |
| Anti-Snore | `F1 F1 09 01 01 0B 7E` | n/a |
| Memory 1 Recall | `F1 F1 0B 01 01 0D 7E` | `F1 F1 0B 02 00 00 0D 7E` |
| Memory 2 Recall | `F1 F1 0D 01 01 0F 7E` | `F1 F1 0D 02 00 00 0F 7E` |
| Memory 1 Save | `F1 F1 0A 01 01 0C 7E` | `F1 F1 0A 02 00 00 0C 7E` |
| Memory 2 Save | `F1 F1 0C 01 01 0E 7E` | `F1 F1 0C 02 00 00 0E 7E` |

For the middle family, `adjustable_bed.logicdata_hold_preset` holds flat,
memory 1 or memory 2 for a chosen duration. It refreshes flat every 100 ms or
memory every 200 ms and releases on completion or cancellation. Ordinary
one-shot preset buttons remain available.

### Massage

P1 only. Massage levels are Off and levels 1–3, wire values `00`/`02`/`03`/`04`.

| HA zone | Off | Level 1 | Level 2 | Level 3 |
|---------|-----|---------|---------|---------|
| Head (back) | `F1 F1 12 02 08 00 1C 7E` | `F1 F1 12 02 08 02 1E 7E` | `F1 F1 12 02 08 03 1F 7E` | `F1 F1 12 02 08 04 20 7E` |
| Foot (legs) | `F1 F1 14 02 08 00 1E 7E` | `F1 F1 14 02 08 02 20 7E` | `F1 F1 14 02 08 03 21 7E` | `F1 F1 14 02 08 04 22 7E` |
| Right (`split_series`) | `F1 F1 22 02 08 00 2C 7E` | `F1 F1 22 02 08 02 2E 7E` | `F1 F1 22 02 08 03 2F 7E` | `F1 F1 22 02 08 04 30 7E` |

| Command | Bytes (hex) |
|---------|-------------|
| Massage Stop | `F1 F1 11 01 08 1A 7E` |
| Massage Mode | `F1 F1 16 01 0A 21 7E` |

### Lights

| Command | P1 | P2 |
|---------|----|----|
| Light Toggle | `F1 F1 0F 00 0F 7E` | `F1 F1 0F 02 00 00 11 7E` |

### Clock and Alarm

| Command | Bytes (hex) |
|---------|-------------|
| Clock | `F1 F1 50 07 year-1970 month day weekday hour minute second checksum 7E` |
| Alarm | `F1 F1 51 08 enabled any_day mask hour minute wake back leg checksum 7E` |

- The phone always builds a P1 clock frame, including for the P2 family.
  Weekday uses Sunday = 0.
- Alarm `mask` sets bit 1 for Monday through bit 7 for Sunday. Wake codes:
  flat `0`, anti-snore `1`, zero-g `2`, memory 1 `3`, memory 2 `4`.

### Rename

| Transport | Payload on the name characteristic |
|-----------|------------------------------------|
| T1 | Bare ASCII name |
| T3 | `01 FC 07`, name length, ASCII name |

The phone writes the name once; the tablet writes it twice, 500 ms apart.

## Notifications / State

The apps do not validate checksum/trailer or declared payload lengths; HA
preserves that and only guards field bounds.

| Prefix | Minimum length | Meaning |
|--------|----------------|---------|
| `F2 F2 11` | 5 bytes | Packet family: byte 4 = `01` is the middle (P2) family |
| `F2 F2 0F` | 7 bytes | Hardware acknowledgment |
| `F2 F2 50` (phone) | 6 bytes | Clock request; HA answers with the clock frame |
| `F2 F2 51` (phone) | 14 bytes | Alarm: enabled (byte 4), weekday bits (byte 6), hour, minute, wake code, back and leg levels (bytes 7–11) |
| Byte 2 `05`/`06`, any header | 9 bytes | Light on from byte 8 bit 6; `06` also reports back (byte 4) and legs (byte 6) massage, the right zone in `split_series` |

- When lighting is enabled, the Under Bed Lights binary sensor exposes the
  latest notification state to Home Assistant and automations. The light button
  remains toggle-only; pressing it does not optimistically replace the reported
  state.
- The phone alarm state is exposed as the `logicdata_app_alarm` sensor.
- Neither app reports motor positions, brightness or RGB color, so the
  integration does not create those controls.
- MOTIONrelax drops a clock request that arrives while an earlier request is
  still being answered.

## Command Timing

| Action | Sequence |
|--------|----------|
| Movement | Repeats every 100 ms; on normal completion the app's final movement write, then short release after 100 ms |
| Cancelled movement | The proven release, without another movement write |
| Explicit stop | `F1 F1 4E 00 4E 7E` immediately |
| Presets and memory recall | One frame, release 100 ms later |
| Memory save | Three frames at 0, 30 and 60 ms |
| Light toggle | Toggle; P1 and P2 releases at +80 ms; P1 release at +100 ms |
| Massage mode | Phone: P2 release at +1000 ms, P1 release at +1100 ms. Tablet: no release |
| Massage level, massage stop | One frame |
| Held flat (P2) | Refresh every 100 ms, terminal frame, release 100 ms later |
| Held memory (P2) | Refresh every 200 ms, release 100 ms later |

Timed moves include the terminal write and release delay in the requested
duration, rounded up to the next 100 ms interval. A 100 ms request sends one
movement frame and releases at 100 ms; a 1000 ms request releases at 1000 ms.
Memory, lighting and massage keep their own action-specific timing.

> [!NOTE]
> P2 flat clicks omit cleanup in Android. HA sends the same packet followed by
> the proven held-touch P1 release to guarantee movement cleanup.

## Actions

- The phone profile synchronizes the clock and supports weekly native alarm
  configuration through `adjustable_bed.logicdata_set_alarm` when the standard
  family is selected. Choose weekdays, time, a supported preset, and back/leg
  massage levels. The tablet profile has no clock or alarm BLE implementation.
  The apps' dormant local wake automation is excluded.
- `adjustable_bed.logicdata_hold_preset` holds a middle-family preset (see
  [Presets and Memory](#presets-and-memory)).
- `adjustable_bed.rename` changes the Bluetooth device name when the chosen
  transport provides a name characteristic. Its service description lists the
  supported input. This is separate from the Home Assistant friendly name. The
  older `logicdata_rename` name still works. The controller accepts 1–255
  printable ASCII characters, a deliberate input policy that avoids the tablet
  app's malformed Unicode name encoding.

## Notes

### Analysis provenance

- Packages: `com.logicdata.app.android.bed` **1.0.6 (7)** and
  `com.logicdata.app.android.pad.bed` **1.0.4 (5)**.
- The [whole-cluster disposition](logicdata-app-disposition.md) records every
  reachable command, the phone/tablet differences, report hashes and exclusions.
- Accepted frozen reports remain unchanged.
- Hardware actuator mapping, delivery timing and firmware behavior remain
  deferred validation for users after a beta or release.
