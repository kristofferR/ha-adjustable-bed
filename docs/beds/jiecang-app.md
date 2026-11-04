# ERGOBALANCE, Dream Motion and Dream Motion HD app profiles

**Status:** ❓ Needs testing. **Static verified, hardware unverified.**

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

These explicit profiles implement the accepted APK Protocol Audit cluster-004
evidence. Existing legacy Jiecang configurations keep their previous behavior
([Jiecang](jiecang.md)). The Comfort Motion app has its own
[profile page](comfort-motion.md).

## Known Models

- ERGOBALANCE beds (app package name: Dreamask)
- Dream Motion beds
- Dream Motion HD tablet app beds (see [Dream Motion HD 1.0.4](#dream-motion-hd-104))
- Both apps use the same Bluetooth services; see
  [Detection / Setup](#detection--setup)

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [ERGOBALANCE](https://play.google.com/store/apps/details?id=com.jiecang.dreamask.app.android.bed) 1.0.8 (8) | `com.jiecang.dreamask.app.android.bed` |
| ✅ | [Dream Motion](https://play.google.com/store/apps/details?id=com.jiecang.dreamotion.app.android.bed) 1.0.5 (11) | `com.jiecang.dreamotion.app.android.bed` |
| ✅ | [Dream Motion HD](https://play.google.com/store/apps/details?id=com.dreamhd.jiecang.android.pad.bed) 1.0.4 (4) | `com.dreamhd.jiecang.android.pad.bed` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (determined by the selected layout) |
| Position Feedback | ❌ (actuator-status packets are not motor position feedback; no position sliders or angle sensors) |
| Presets | ✅ Flat, Zero-G, Anti-Snore; Yoga when the bed reports it |
| Memory Presets | ✅ (2 slots, separate recall and save) |
| Massage | ✅ (Off and levels 1–3 per layout zone, mode, stop) |
| Lights | ✅ (toggle; RGB, brightness, timeout and automatic under-bed lighting when reported) |
| Alarm | ✅ (`adjustable_bed.jiecang_set_alarm`) |
| Wake Routine | ✅ (`adjustable_bed.jiecang_wake`) |
| Clock | ✅ (answered on the bed's clock request) |
| Bluetooth Rename | ✅ (G1 or G3) |

## Protocol Details

| Selection | Service | Write | Notify | Name |
|-----------|---------|-------|--------|------|
| G1 | `0000ff12-0000-1000-8000-00805f9b34fb` | `0000ff01-0000-1000-8000-00805f9b34fb` | `0000ff02-0000-1000-8000-00805f9b34fb` | `0000ff06-0000-1000-8000-00805f9b34fb` |
| G2 | `88121427-11e2-52a2-4615-ff00dec16800` | `88121427-11e2-52a2-4615-ff00dec16801` | same as write | none |
| G3 | `0000fe60-0000-1000-8000-00805f9b34fb` | `0000fe61-0000-1000-8000-00805f9b34fb` | `0000fe62-0000-1000-8000-00805f9b34fb` | `0000fe63-0000-1000-8000-00805f9b34fb` |

**Format:** `F1 F1 | opcode | length | payload | checksum | 7E`, where checksum
is the low byte of opcode + length + payload.

### Transport Selection

- Automatic transport selection uses a coherent GATT service and its
  corresponding write, notification and name channels, trying G3, then G1, then G2.
- Explicit G1/G2/G3 overrides are available.
- ERGOBALANCE requires G1 or G3 to be present when selecting G2; standalone G2 is
  supported only by Dream Motion's manual connection route.

### Write Mode

Writes use a response when the write characteristic advertises `write`,
otherwise write-without-response.

### Startup Queries

When the selected transport has a complete G1 or G3 profile (or G2 next to
one), HA waits 1 s after subscribing, then sends each query twice, 100 ms apart:

| Offset | Query | Bytes (hex) |
|--------|-------|-------------|
| 0 ms | Software | `F1 F1 00 02 40 00 42 7E` |
| 800 ms | Light | `F1 F1 00 02 01 00 03 7E` |
| 1000 ms | Actuator | `F1 F1 00 01 50 51 7E` |
| 1200 ms | Hardware | `F1 F1 00 01 40 41 7E` |
| 1400 ms | Vibration (massage) | `F1 F1 00 01 08 09 7E` |
| 1600 ms | Alarm | `F1 F1 00 01 10 11 7E` |
| 1800 ms | Software | `F1 F1 00 02 40 00 42 7E` |

HA then waits up to 0.5 s for the capability reply. On G3, the name
characteristic is subscribed 3 s after the queries start when it supports
notifications.

## Detection / Setup

1. Select **Jiecang (ERGOBALANCE / Dream Motion / Dream Motion HD apps)**.
2. Choose the exact app profile and control layout.

- Both apps use the same Bluetooth services, so a service UUID cannot determine
  which app's release behavior or layout applies.
- No pairing, PIN or device-name pattern is inferred from these apps.

### Layouts

Layouts cover standard two motors; three motors with neck, lumbar, height or
split-upper controls; four motors with legacy or bilateral controls; and the
split series.

| Layout | Movement axes | Massage zones |
|--------|---------------|---------------|
| `standard_2` | Back, legs, both | Back, legs |
| `standard_3_neck` | Back, legs, head (neck) | Back, legs |
| `standard_3_lumbar` | Back, legs, lumbar | Back, legs |
| `standard_3_hi_low` | Back, legs, bed height | Back, legs |
| `standard_3_split_upper` | Back, legs, right back, both backs | Back, right, legs |
| `standard_4_legacy` | Head, back, lumbar, legs | Back, legs |
| `standard_4_bilateral` | Back, both backs, right back, legs, both legs, right legs | Back, right |
| `split_series` | Back, legs, right back, both backs | Back, right, legs |
| `split_after_bilateral` | Back, legs, right back, both backs | Back, right |

The separate split-after-bilateral option preserves the app's reachable
combination of standard split movement and bilateral global commands. It does
not rely on accidentally retained Android settings.

## Commands

All values are built by the Jiecang codec (`codec/jiecang.py`) from the app
profiles in `profiles/jiecang.py`. The
[complete cluster disposition](jiecang-app-disposition.md) maps every command group.

### Motor Control

Movement frames use payload `01`, or `00 00` in the `standard_4_bilateral` layout.

| Axis | Up | Down | Bilateral up / down |
|------|----|------|---------------------|
| Back | `F1 F1 01 01 01 03 7E` | `F1 F1 02 01 01 04 7E` | `F1 F1 01 02 00 00 03 7E` / `F1 F1 02 02 00 00 04 7E` |
| Legs | `F1 F1 03 01 01 05 7E` | `F1 F1 04 01 01 06 7E` | `F1 F1 03 02 00 00 05 7E` / `F1 F1 04 02 00 00 06 7E` |
| Both (back and legs) | `F1 F1 05 01 01 07 7E` | `F1 F1 06 01 01 08 7E` | n/a |
| Head / neck, bed height | `F1 F1 19 01 01 1B 7E` | `F1 F1 1A 01 01 1C 7E` | n/a |
| Lumbar | `F1 F1 1B 01 01 1D 7E` | `F1 F1 1C 01 01 1E 7E` | n/a |
| Right back | `F1 F1 20 01 01 22 7E` | `F1 F1 21 01 01 23 7E` | `F1 F1 20 02 00 00 22 7E` / `F1 F1 21 02 00 00 23 7E` |
| Both backs | `F1 F1 23 01 01 25 7E` | `F1 F1 24 01 01 26 7E` | `F1 F1 23 02 00 00 25 7E` / `F1 F1 24 02 00 00 26 7E` |
| Right legs | n/a | n/a | `F1 F1 2A 02 00 00 2C 7E` / `F1 F1 2B 02 00 00 2D 7E` |
| Both legs | n/a | n/a | `F1 F1 2C 02 00 00 2E 7E` / `F1 F1 2D 02 00 00 2F 7E` |

| Command | Bytes (hex) |
|---------|-------------|
| Short release | `F1 F1 4E 00 4E 7E` |
| Long release | `F1 F1 4E 02 00 00 50 7E` |

### Presets

Preset frames use payload `01`, or `00 00` in bilateral layouts
(`standard_4_bilateral`, `split_after_bilateral`) and for Yoga.

| Command | Bytes (hex) | Bilateral layouts |
|---------|-------------|-------------------|
| Flat | `F1 F1 08 01 01 0A 7E` | `F1 F1 08 02 00 00 0A 7E` |
| Zero-G | `F1 F1 07 01 01 09 7E` | `F1 F1 07 02 00 00 09 7E` |
| Anti-Snore | `F1 F1 09 01 01 0B 7E` | `F1 F1 09 02 00 00 0B 7E` |
| Yoga (only when the bed reports it) | `F1 F1 28 02 00 00 2A 7E` | `F1 F1 28 02 00 00 2A 7E` |

### Memory

| Command | Bytes (hex) |
|---------|-------------|
| Memory 1 Recall | `F1 F1 0B 02 00 00 0D 7E` |
| Memory 2 Recall | `F1 F1 0D 02 00 00 0F 7E` |
| Memory 1 Save | `F1 F1 0A 02 00 00 0C 7E` |
| Memory 2 Save | `F1 F1 0C 02 00 00 0E 7E` |

### Massage

Massage levels are shown as Off and levels 1–3, mapped to the app's exact wire
values `00`/`02`/`03`/`04`. Frames are `F1 F1 | zone | 02 | 08 | level | checksum | 7E`,
with `00` instead of `08` in bilateral layouts.

| HA zone | Zone byte | Off | Level 1 | Level 2 | Level 3 |
|---------|-----------|-----|---------|---------|---------|
| Head (back) | `12` | `F1 F1 12 02 08 00 1C 7E` | `F1 F1 12 02 08 02 1E 7E` | `F1 F1 12 02 08 03 1F 7E` | `F1 F1 12 02 08 04 20 7E` |
| Foot (legs) | `14` | `F1 F1 14 02 08 00 1E 7E` | `F1 F1 14 02 08 02 20 7E` | `F1 F1 14 02 08 03 21 7E` | `F1 F1 14 02 08 04 22 7E` |
| Right | `22` | `F1 F1 22 02 08 00 2C 7E` | `F1 F1 22 02 08 02 2E 7E` | `F1 F1 22 02 08 03 2F 7E` | `F1 F1 22 02 08 04 30 7E` |

| Command | Bytes (hex) | Bilateral layouts |
|---------|-------------|-------------------|
| Massage Stop | `F1 F1 11 01 08 1A 7E` | `F1 F1 11 02 00 00 13 7E` |
| Massage Mode | `F1 F1 16 01 0A 21 7E` | `F1 F1 16 02 00 00 18 7E` |

### Lights

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Light Toggle | `F1 F1 0F 02 00 00 11 7E` | Sent after the RGB state write |
| Automatic Light Toggle | `F1 F1 29 02 00 00 2B 7E` | Sent only when the reported state differs |
| RGB State | `F1 F1 52 07 BB GG RR brightness time_hi time_lo on checksum 7E` | Blue, green, red 0–255; brightness 0–100; big-endian timeout seconds; on `00`/`01` |

- Timeouts: 0, 60, 120, 180, 240, 300, 600, 900, 1200, 1500 or 1800 seconds.
- On, off, color, brightness and timer write the full RGB state. When no light
  state has been received, HA first sends the light query twice (100 ms apart)
  and waits up to 1 s; without a reply it refuses the change, preserving unknown
  color and timer settings.
- Color, brightness, timeout and automatic lighting require the light option, a
  non-bilateral layout and the bed's reported light-configuration capability.

### Alarm and Clock

| Command | Bytes (hex) |
|---------|-------------|
| Alarm | `F1 F1 51 08 enabled any_day mask hour minute wake back leg checksum 7E` |
| Clock | `F1 F1 50 07 year-1970 month day weekday hour minute second checksum 7E` |

- Alarm `mask` sets bit 1 for Monday through bit 7 for Sunday; `any_day` is `01`
  when any weekday is selected. Massage levels are 0–3.
- Alarm wake codes: flat `0`, anti-snore `1`, zero-g `2`, memory 1 `3`,
  memory 2 `4`, yoga `6`. Yoga requires the bed's reported capability.
- Clock weekday uses Sunday = 0. HA sends it when the bed requests the clock.

### Rename

| Transport | Payload on the name characteristic |
|-----------|------------------------------------|
| G1 | Bare ASCII name |
| G3 | `01 FC 07`, name length, ASCII name |

The name is written twice, 500 ms apart.

## Notifications

No response checksum is required: both apps accept bad trailers. Malformed
fields are ignored instead of overwriting state.

| Prefix | Minimum length | Meaning |
|--------|----------------|---------|
| `F2 F2 50` | 6 bytes | Clock request; HA replies with the clock frame |
| `F2 F2 0E` | 7 bytes | Capabilities: Yoga from byte 4 bit 1; light configuration from the apps' binary-string test of byte 4 |
| `F2 F2 0F` | 7 bytes | Layout re-apply request |
| `F2 F2 51` | 7 bytes | Alarm page visible; with 14+ valid bytes: enabled (byte 4), weekday bits (byte 6), hour, minute, wake code, back and leg levels (bytes 7–11) |
| `F2 F2 52 07` | 13 bytes | RGB: blue, green, red (bytes 4–6), brightness (byte 7, ≤100), timeout (bytes 8–9), on (byte 10) |
| `F2 F2 53` | 7 bytes | Automatic light on when byte 4 is `00` |
| Byte 2 `05`/`06` | 9 bytes | Light on from byte 8 bit 6; `06` also reports back (byte 4) and legs (byte 6) massage, the right zone in bilateral layouts |

Notifications update available state. Actuator-status packets are not motor
position feedback.

## Command Timing

| Action | Sequence |
|--------|----------|
| Movement | Repeats every 100 ms for the motor pulse count |
| ERGOBALANCE release | Long release at 50 and 150 ms after a hold |
| Dream Motion release | Final movement packet, then short and long releases at 100 and 800 ms |
| Explicit stop | The profile's release frames, with the first sent immediately |
| Presets and memory recall | One frame, long release 800 ms later |
| Memory save | Three frames, 30 ms apart, no release |
| Massage level | One frame; in bilateral layouts followed by long release after 800 ms |
| Massage mode | One frame, long release after 1000 ms |
| Light toggle | RGB state write, toggle after 150 ms, then short and long release 80 ms later |

Cleanup also runs when Home Assistant cancels a command; a cancelled Dream Motion
hold never sends the final movement packet. Presets, save operations, massage and
lighting retain their own command sequences instead of sharing a universal
repeat/stop schedule.

## Automations and services

- `adjustable_bed.jiecang_set_alarm` writes the app's weekly alarm configuration.
  It accepts a time, weekdays, wake preset and massage levels. Storing that
  configuration is separate from executing the Android app's local wake routine.
- `adjustable_bed.jiecang_wake` executes the proven wake packet sequence. Use a
  Home Assistant time trigger when local scheduling is required. Yoga can be
  encoded in the alarm configuration but is not an implemented wake choice in
  either app's executor.
- `adjustable_bed.jiecang_stop_wake` stops active wake massage without changing
  the saved alarm schedule. It sends `F1 F1 11 01 08 1A 7E`, even on bilateral layouts.
- `adjustable_bed.rename` (or the older `jiecang_rename`) writes a Bluetooth
  name of up to 20 ASCII letters or digits. This changes the advertised device
  name, separately from its friendly name in Home Assistant.

The normal cover, button, light, number and select actions remain available for
individual movement, presets, massage and lighting.

### Wake Sequence

Alarm massage always uses payload-`08` frames, including bilateral layouts.

| Offset | Frames |
|--------|--------|
| 0 ms | Back massage at +0/+30/+60 ms, short release at +90/+120/+150 ms |
| 180 ms (split layouts) | Right massage at the back level, same pattern |
| 300 ms (500 ms in split layouts) | Leg massage, same pattern |
| 800–920 ms | Preset or memory recall, five times 30 ms apart |
| 1600 ms | Long release (memory 2 on non-split layouts only) |
| 1690, 1720 ms | Long release |

A zone with level 0 is skipped. Split layouts are `split_series` and
`split_after_bilateral`. A cancelled routine sends a long release.

## Dream Motion HD 1.0.4

Choose **Dream Motion HD** for `com.dreamhd.jiecang.android.pad.bed`
1.0.4 (4). This explicit tablet profile is based on independently accepted
row105 evidence. It does not migrate existing phone-app or legacy entries.
See the [complete discovery ledger](dreamhd-disposition.md) for evidence seals,
all 50 command rows, 90 candidate dispositions, consumer behavior and safe HA
adaptations. Static behavior is verified; physical effects remain unverified.

### HD layouts

- Six standard layouts: two motors; neck, lumbar, height or split-upper; and
  four motors with neck/lumbar. Each has independent massage and light choices,
  plus a separate split-series layout, totaling 25 app configurations.
- Bilateral and split-after-bilateral belong to other profiles and are rejected
  for HD.
- Layout, massage and light are user choices, never inferred from the name or a
  shared service. The existing setup massage option and **Enable light
  controls** apply.
- Motor refresh is fixed at 100 ms.

### HD controls and feedback

- HD uses its own startup status queries and one short release 100 ms after
  movement or a preset.
- Two memory slots, with different packet payloads from the phone apps.
- Massage is Off and levels 1–3 (wire 0/2/3/4); normal steps, mode changes and
  stop write once. Intensity changes await notification feedback.
- Right-back and leg feedback share byte 6 on split layouts, so both sliders
  report that value rather than inventing a third feedback field.

### HD lights

- RGB color, brightness and timeout use the app's BGR packet.
- The repaired feature predicate uses minimal binary, appends zeros, truncates
  and reverses; it is not a conventional bit mask.
- A negative reply hides the picker and persists suppression. A later positive
  reply reveals it without clearing suppression. A light-status reply reveals
  only the picker when suppression is clear, never the automatic-light switch.
- Connection resets light visibility and cached color.
- HA always honors **Enable light controls**, even where the Android UI would
  reveal a picker despite that preference.
- Automatic-light status treats zero as off and any nonzero value as on. Its
  physical sensor meaning has not been established.

### HD alarms, wake and rename

- The normal controls, weekly-alarm services and wake services above work for HD.
- Its broadcast-derived wake routine starts leg massage at 500 ms, split right
  massage at 180 ms, and repeats the preset at 800–920 ms. HA adds the proven
  short release on completion and independently attempts to stop wake massage
  on cancellation or failure, including a failed release write. It never copies
  Android's missing release/cancel cleanup.
- `adjustable_bed.rename` accepts 1–20 printable ASCII characters, including
  spaces, for HD. G1 writes the bare name; G3 prefixes a byte length. HA safely
  corrects Android's malformed G3 lengths 10–15 and rejects its lossy non-ASCII
  encoding. The older `jiecang_rename` alias keeps its narrower released schema.
- G2 has no name channel and no startup-query burst when selected alone; it can
  be connected manually but standalone setup completion is not a hardware claim.

### HD dynamic capabilities

- Late capability and RGB replies add the corresponding controls without
  reloading HA.
- Repeated negative and positive feature replies retire and recreate the RGB,
  brightness, timer, automatic-light and Yoga controls as their gates change.
- For paired HD beds, each side's Yoga button follows that side's reported
  capability. The combined Yoga button appears only when both sides support it,
  and follows later withdrawals and replies without reloading the pair.

## Notes

### Safety Adaptations

The implementation serializes GATT operations, validates inputs and performs
cancellation cleanup. It does not reproduce Android's duplicate startup bursts,
unsafe parser exceptions or missing key/cancel cleanup.

### Analysis provenance

- Packages: `com.jiecang.dreamask.app.android.bed` **1.0.8 (8)** and
  `com.jiecang.dreamotion.app.android.bed` **1.0.5 (11)**.
- The [complete cluster disposition](jiecang-app-disposition.md) records every
  command group, both accepted report identities, shared behavior, six material
  differences, implementation choices and exclusions.
- Physical actuator mapping, GATT properties and behavior on real firmware
  remain deferred validation for users after a beta or release.
- No raw APK or frozen analysis is shipped with the integration.
