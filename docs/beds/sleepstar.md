# SleepSpa S9000AI (SLEEPSTAR)

**Status:** ❓ Needs testing (statically verified from the OEM app; physical hardware testing is pending)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- SleepSpa S9000AI device class, advertised as `SLEEPSTAR` (single-side and
  dual-side variants)

> [!WARNING]
> This is a CB37 sleep-monitor session over Nordic UART. Bed actions use
> StarCode, but every StarCode packet is tunneled through the CB37 transparent
> control-box route. It must not be configured as Sleepy's BOX25 or Okin CB35.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [SleepSpa](https://play.google.com/store/apps/details?id=com.dot.bedding.sleepspa.sleep_spa) 1.3.7 (build 37) | `com.dot.bedding.sleepspa.sleep_spa` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head, feet, lumbar, Auxiliary 1, Auxiliary 2; shared STOP |
| Position Feedback | ✅ 0-100% for five addressable parts; sixth feedback-only part retained in diagnostics |
| Direct Position | ✅ Zones 0-4, one packet |
| Presets | ✅ Flat, TV, Zero-G, Anti-Snore, Lounge, both-up |
| Memory Presets | ✅ Two app-visible slots; recall 3 writes then STOP, save 55 writes |
| Lighting | ✅ Discrete on/off/toggle, brightness 0-6; protocol API also retains color indices 0-7 |
| Sonic Massage | ✅ Head, foot, and combined intensity 0-6; five modes; 10/20/30-minute timer |
| Sleep Monitor | ⚠️ Query/config builders for anti-snore, sleep zone, daily/monthly reports |
| Environment | ⚠️ Duration, address, and seven-register query builders |
| Audio | ⚠️ Media, USB, noise, sonic type, volume, cutoff, reset, preset, and EQ protocol methods |

## Protocol Details

**Service UUID:** `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` (Nordic UART)
**Write Characteristic:** `6E400002-B5A3-F393-E0A9-E50E24DCCA9E` (TX, write without response)
**Notify Characteristic:** `6E400003-B5A3-F393-E0A9-E50E24DCCA9E` (RX, notify)
**Format:** CB37 envelopes; StarCode bed actions inside the transparent control-box route

There is no application PIN, authentication exchange, encryption wrapper,
nonce, or outer checksum. The environment-sensor payload alone uses an inner
CRC-16/MODBUS value.

### Transparent control-box route

```text
AA 00 00 09 02 LL [StarCode payload]
```

`LL` is the one-byte StarCode payload length. Example STOP:

```text
AA 00 00 09 02 07 5A 01 03 10 30 0F A5
```

| StarCode frame | Bytes |
|----------------|-------|
| Normal action | `5A 01 [32-bit key, big endian] A5` |
| Extended value | `5A E0 04 key value value2 value3 A5` |
| Direct motor position | `5A F0 03 zone position 00 A5` |
| Query | `5A key 00 A5` |

Position is clamped to 0 through 100 and zones 0 through 4 address the five
controllable actuator parts.

### Sleep and environment routes

Sleep queries use:

```text
2A 00 00 family command length [payload]
```

Environment MODBUS messages use:

```text
AA 00 00 09 03 LL [MODBUS payload] crcLo crcHi
```

### Session sequence

The integration enables RX notifications before writing anything, then sends:

1. CB37 configuration page 1
2. Raw CB37 local date/time calibration
3. Wrapped StarCode local date/time calibration
4. Sleep-sensor firmware-version query
5. Motor, light, sleep configuration, environment duration, and environment
   address state queries

- Writes use the app's 100 ms sender cadence.
- A single 12-second recovery timer clears and requests configuration page 1
  again.
- Page 1 contains a bitmap for pages 2 through 8; only advertised missing pages
  are requested.
- Disconnect cleanup cancels all session timers and sends no logout packet.

## Detection / Setup

| Signal | Meaning |
|--------|---------|
| BLE name starts with `SLEEPSTAR` | S9000AI demo sleep-monitor device |
| Company ID `0x00B2`, payload byte 6 = `0x88` | Single-side variant |
| Company ID `0x00B2`, payload byte 6 = `0x86` | Dual-side variant |
| Missing or any other subtype byte | Dual fallback, matching the app |

The app also bundles real `SLEEPBT` single/dual library classes, but its own
application filter rejects them. The integration therefore explicitly rejects
`SLEEPBT` instead of misclassifying the shared Nordic UART service as another
bed protocol.

## Commands

Normal actions are sent as `AA 00 00 09 02 07 5A 01 <key> A5`; extended values
as `AA 00 00 09 02 08 5A E0 04 key value value2 value3 A5`.

### Motor Control

| Command | Key | Description |
|---------|-----|-------------|
| STOP | `0x0310300F` | Shared STOP for every actuator |
| Head up / down | `0x03103000` / `0x03103001` | Zone 0 |
| Feet up / down | `0x03103002` / `0x03103003` | Zone 1 |
| Lumbar up / down | `0x03103004` / `0x03103005` | Zone 2 |
| Part 4 (Auxiliary 1) up / down | `0x03103008` / `0x03103009` | Zone 3 |
| Part 5 (Auxiliary 2) up / down | `0x0310300A` / `0x0310300B` | Zone 4 |
| Head and feet up (both-up preset) / down | `0x0310300C` / `0x0310300D` | Combined movement |
| Direct position | `5A F0 03 zone position 00 A5` | Zones 0-4, position 0-100 |

### Presets

| Command | Key |
|---------|-----|
| Flat | `0x03103010` |
| TV | `0x03103011` |
| Zero-G | `0x03103013` |
| Anti-Snore | `0x03103016` |
| Lounge | `0x03103017` |

### Memory

| Command | Key |
|---------|-----|
| Memory 1 / 2 recall | `0x0310301A` / `0x0310301B` |
| Memory 1 / 2 store | `0x03103094` / `0x03103095` |

### Lights

| Command | Bytes | Description |
|---------|-------|-------------|
| Light toggle | key `0x03103070` | |
| Light on / off | key `0x03103073` / `0x03103074` | Brightness 0 sends light off |
| Brightness 1-6 | extended key `0x00`, value = level | |
| Color index 0-7 | extended key `0x01`, value = index | Protocol API only |

### Sonic Massage

| Command | Bytes | Description |
|---------|-------|-------------|
| Mode step | extended key `0x08`, value 0-4 | Cycles the five modes |
| Head intensity 0-6 | extended key `0x0F`, value = level | |
| Foot intensity 0-6 | extended key `0x10`, value = level | |
| Combined intensity 0-6 | extended key `0x11`, value and value2 = level | |
| Timer off / 10 / 20 / 30 min | extended key `0x0B`, value `0` / `1` / `2` / `3` | Massage off selects timer `0` |

### Audio

| Command | Bytes |
|---------|-------|
| Media previous / play-pause / next | key `0x03104018` / `0x0310401A` / `0x03104019` |
| Media volume up / down | key `0x03104016` / `0x03104017` |
| USB play / exit | key `0x03105003` / `0x03104031` |
| Noise track 1 / 2 / 3 | key `0x03104020` / `0x03104021` / `0x03104022` |
| Stop noise | key `0x03104023` |
| Noise volume (raw 0-255) | extended key `0x0A` |
| Sonic type 0 / 1 | key `0x03104012` / `0x03104013` |
| Reset sound | key `0x03104035` |
| Sound presets 0-5 (app order) | key `0x03104033`, `0x0310403A`, `0x03104032`, `0x03104034`, `0x0310403B`, `0x0310403C` |
| Sound cutoff (raw 0-255) | extended key `0x0E` |
| EQ profile value 1-10 | extended key `0x0D` |

### Session, Sleep Monitor and Environment

| Frame | Bytes |
|-------|-------|
| CB37 configuration page 1-8 | `2A 00 00 05 81 09 page FF FF 00 00 22 25 12 4B` |
| CB37 date/time | `AA 00 00 03 01 08 YY MM DD hh mm ss weekday tz` (year − 2000, ISO weekday, whole-hour offset) |
| Wrapped StarCode date/time | control-box wrapper around `5A 14 07 YY MM DD hh mm ss weekday A5` |
| Sleep-sensor firmware version | `2A 00 00 08 81 00` |
| Motor / light status query | wrapped `5A D0 00 A5` / `5A B0 00 A5` |
| Sleep configuration query | `2A 00 00 07 81 00` |
| Anti-snore configuration | `AA 00 00 07 01 08 sensitivity duration enabled motor 00 00 00 00` |
| Sleep-zone configuration | `AA 00 00 07 04 03 right zone_type left` |
| Daily report (left / right) | `2A 00 00 07 84` / `85`, then `03 YY MM DD` |
| Monthly report (left / right) | `2A 00 00 07 86` / `87`, then `02 YY MM` |
| Environment working duration | `2A 00 00 09 81 01 01` |
| Environment address (broadcast) | environment wrapper around `00 02 00 00 00 01` + CRC |
| Environment seven registers | environment wrapper around `address 03 00 02 00 07` + CRC |

## Notifications

Both forms below are accepted:

- Direct inner status beginning with `A5`
- `AA ... 02` wrapper whose declared inner payload begins at byte 6

| Notification | Handling |
|--------------|----------|
| Motor status type `0x0D` | Bytes `4, 6, 8, 10, 5, 7` map to head, foot, lumbar, part 4, part 5, and feedback-only part 6. Values are clamped to 100. |
| Sonic (`0x0B`), alarm (`0x0C`), EQ (`0x0E`) | Routed to diagnostic controller state |
| CB37 configuration page (`2A … 05 81`) | Bitmap at byte 6, page at byte 7; page 1 also carries motor, motor-type and soft-start masks and peripheral info |
| Sleep, environment, config and report responses | Retained in controller state as hex |

- Identical notifications inside 200 ms are ignored, matching the app.
- Sleep/environment/config/report responses are retained in controller state as
  hex so support bundles preserve unmodified protocol evidence. The integration
  does not guess the physical meaning of values that the analyzed app leaves
  model-dependent.

## Command Timing

| Operation | Timing |
|-----------|--------|
| Sender cadence | 100 ms between frames |
| Movement | Configured pulse count and delay, then STOP |
| Preset and memory recall | 3 writes at 100 ms, then STOP |
| Memory store | 55 writes at 100 ms, no STOP |
| Brightness, color, sonic mode/intensity/timer | 2 writes at 100 ms, then STOP |
| Configuration recovery | One retry after 12 seconds |

## Notes

### Auxiliary labels

The APK names the last three position channels only by part number. The
integration exposes the two controllable channels as Auxiliary 1 and Auxiliary
2 rather than guessing their physical purpose. The sixth channel is
feedback-only and appears in controller diagnostics as
`sleepstar_part6_position`.

### Analysis provenance

The implementation comes from a clean-room APK Protocol Audit analysis of:

- App: SleepSpa 1.3.7 (build 37)
- Package: `com.dot.bedding.sleepspa.sleep_spa`
- Complete split APK set: base, `arm64_v8a`, `en`, `nb`, and `xxhdpi`
- Artifact-set SHA-256: `d114ec34fcd6645c30d356019ad756d3117d09f0eed8c41eb8e377b885557fdf`
- Report status: COMPLETE, with 29/29 independent packet/parser vectors passing

The report proves application behavior. Real-bed validation remains deferred
until a user can test a beta or release and provide a support bundle if needed.

### Deferred physical validation

After beta or release, useful validation includes:

1. Confirm Company ID `0x00B2`, subtype byte, and single/dual selection from an
   actual `SLEEPSTAR` advertisement.
2. Exercise every actuator and verify the two Auxiliary labels.
3. Verify preset, memory-save, brightness, sonic intensity/mode/timer, and STOP
   behavior.
4. Capture representative motor, sonic, alarm, environment, daily, and monthly
   notifications with a generated support bundle.
