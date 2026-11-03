# DewertOkin CB35 Star

**Status:** ✅ Tested (Sealy Element, ESPHome Bluetooth proxy, 2026-09)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Sealy Posturematic (Element, Ascent, Apex)
- Bluetooth name starts with `Star` (e.g., `Star352201011800`); see [Name Encoding](#name-encoding)

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Sealy Posturematic](https://play.google.com/store/apps/details?id=com.okin.sealy) v1.1.1 | `com.okin.sealy` |

- **Android:** Sealy Posturematic (`com.okin.sealy`), a Flutter app with the protocol defined in a JSON asset
- **iOS:** Sealy Posturematic (App Store)
- **Developer:** Star Seeds Co LTD (DewertOkin)

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head, Foot, Lumbar, Neck, Hips (Hips is the Head End Tilt cover) |
| Position Feedback | ❌ |
| Memory Presets | ⚠️ Recall of Memory 1 and 2; no programming over BLE |
| Massage | ✅ Toggle, head/foot strength, mode step, stop |
| Under-bed Lights | ✅ On/off |
| Flat / Zero G / Anti-Snore / Lounge / Incline / TV | ✅ |
| Hardware-confirmed | Motors, Flat, Memory 1, Zero G, Stop and the under-bed light |

## Protocol Details

**Protocol version:** CB.35.22.01
**Service:** Nordic UART (6E400001)
**Write characteristic:** 6E400002 (write-without-response)
**Notify characteristic:** 6E400003
**Format:** the same 7-byte command frame as Okin Nordic

### Packet Format

```text
[0x5A, 0x01, 0x03, 0x10, 0x30, CMD, 0xA5]
```

### Init Sequence

Only a wake command is needed, sent once before the first command:

```text
5A 0B 00 A5
```

## Detection / Setup

| Signal | Value |
|--------|-------|
| Device name | Starts with `Star` (e.g., `Star352201011800`) |
| Name digits 4-5 | `35` distinguishes CB35 from BOX25 (`25`) |
| Service UUID | Nordic UART `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` |
| Manufacturer ID | 89 (OKIN) |
| Manufacturer Name (2A29) | `STAR` selects StarCode framing but is shared with BOX25 |

### Name Encoding

DewertOkin Star device names encode the protocol version: `Star` + `[protocol digits]` + `[serial]`.

| Name | Digits 4-5 | Protocol | Bed Type |
|------|-----------|----------|----------|
| `Star352201011800` | `35` | CB.35.22.01 | CB35 (this protocol) |
| `Star254202079996` | `25` | 25_42_02 | BOX25 (Sleepy's Elite) |

### Manufacturer Name Is Not a Protocol Discriminator

Both confirmed `Star25...` BOX25 devices from issues #372 and #413 return
`STAR` from Device Information characteristic `2A29`. The Adjustable Comfort
M1X12 app uses this value to choose StarCode command framing within its CB25
device implementation; it does not prove the device is CB35. The integration
therefore uses the `25`/`35` digits in the advertised name and never rewrites a
high-confidence `Star25...` detection from the manufacturer string alone.

## Commands

Every command is the 7-byte frame with the CMD byte below. "Not sent" marks
app protocol entries that no Home Assistant entity sends.

### Motor Control

| Command | CMD byte | Full packet | Description |
|---------|----------|-------------|-------------|
| Head Up | 0x00 | `5A 01 03 10 30 00 A5` | Head cover |
| Head Down | 0x01 | `5A 01 03 10 30 01 A5` | Head cover |
| Foot Up | 0x02 | `5A 01 03 10 30 02 A5` | Feet cover |
| Foot Down | 0x03 | `5A 01 03 10 30 03 A5` | Feet cover |
| Lumbar Up | 0x06 | `5A 01 03 10 30 06 A5` | Lumbar cover |
| Lumbar Down | 0x07 | `5A 01 03 10 30 07 A5` | Lumbar cover |
| Hips Up | 0x08 | `5A 01 03 10 30 08 A5` | Head End Tilt cover |
| Hips Down | 0x09 | `5A 01 03 10 30 09 A5` | Head End Tilt cover |
| Neck Up | 0x0A | `5A 01 03 10 30 0A A5` | Neck cover |
| Neck Down | 0x0B | `5A 01 03 10 30 0B A5` | Neck cover |
| Head+Foot Up | 0x0C | `5A 01 03 10 30 0C A5` | Not sent |
| Head+Foot Down | 0x0D | `5A 01 03 10 30 0D A5` | Not sent |
| Stop | 0x0F | `5A 01 03 10 30 0F A5` | Sent 3 times; see [Command Timing](#command-timing) |

### Presets

| Command | CMD byte | Description |
|---------|----------|-------------|
| Flat | 0x10 | Flat preset |
| TV/PC | 0x11 | TV preset |
| Read | 0x12 | Not sent |
| Zero Gravity | 0x13 | Zero G preset |
| Inverse | 0x14 | Not sent |
| Work | 0x15 | Not sent |
| Anti-Snore | 0x16 | Anti-Snore preset |
| Lounge | 0x17 | Lounge preset |
| Incline | 0x18 | Incline preset |
| Extension | 0x19 | Not sent |
| Memory 1 | 0x1A | Memory 1 recall |
| Memory 2 | 0x1B | Memory 2 recall |

### Lights

| Command | CMD byte | Description |
|---------|----------|-------------|
| Light Color Change | 0x70 | Controller method only; no entity |
| Light Toggle | 0x71 | Controller method; HA hides the toggle button because discrete on/off exists |
| Light On | 0x73 | Light on (also the Light Cycle button) |
| Light Off | 0x74 | Light off, written 3 times 100 ms apart |
| Light Brighter | 0x80 | Controller method only; no entity |
| Light Dim | 0x81 | Controller method only; no entity |

### Massage

| Command | CMD byte | Description |
|---------|----------|-------------|
| Massage Open | 0x52 | Controller massage-on method; no entity |
| Massage Toggle | 0x5A | Massage toggle (also head and foot toggles) |
| Wave Up | 0x58 | Not sent |
| Wave Down | 0x59 | Massage mode step |
| Strength Head Up | 0x60 | Head strength up and overall intensity up |
| Strength Head Down | 0x61 | Head strength down and overall intensity down |
| Strength Foot Up | 0x62 | Foot strength up |
| Strength Foot Down | 0x63 | Foot strength down |
| Massage Time Switch | 0x6D | Not sent |
| Massage Stop | 0x6F | Massage off |

CB35 intensity commands use the `0x30` frame; the inherited Okin Nordic
intensity commands use `0x40` in byte 4 instead.

## Notifications

The controller subscribes to the Nordic UART notify characteristic (6E400003).
Massage status frames start with header `A5 0B` (8 bytes or longer); they are
logged and captured for diagnostics but not parsed into entities.

## Command Timing

- **App:** motor commands repeat every 300ms while held. Stop and massage
  commands send 3 times (initial + 2 repeats at 300ms).
- **Home Assistant:** motor commands repeat at the configured motor pulse count
  and delay, then STOP x3 at 300ms. Massage and light commands are single
  writes, except Light Off.

### Presets and Stop (hardware behaviour)

A preset key on its own only *arms* the bed. The STOP x3 release is what commits the move:

| Sent | Result on the bed |
|------|-------------------|
| Preset key x100 at 300ms, then one STOP (generic Okin path) | Bed sits armed for ~20s, then moves |
| Preset key once, no STOP | Bed sits armed until the link drops, then moves |
| Preset key x2 at 300ms, then STOP x3 at 300ms | Bed starts within a second (implemented) |

A preset that is already driving **ignores STOP** (three STOP x3 bursts during a
Flat had no effect). Any motor key interrupts it, the same as pressing a button
on the handset, so `stop_all` sends one motor-key packet (Head Up) before STOP
while a preset may still be in flight. Motor holds stop with STOP alone.

The interrupt window:

- Lasts 45 seconds after the last successfully transmitted preset packet, based
  on the reporter's approximately 30-second full travel.
- A successful motor-key write clears this window, even if later repeats are
  cancelled or fail. Cancellation during wake-up does not count as a
  transmitted movement command.
- The physical coordinator retains this window across BLE disconnects and
  controller recreation, including the default disconnect-after-command path.
  It is runtime state only, not persisted across integration reloads or Home
  Assistant restarts.
- The window estimates possible motion; it does not confirm that a preset is
  still running. Stop can therefore send the motor-key tap after an early
  completion, and sends STOP alone after the window expires.

The reporter observed no visible idle movement on their Sealy Element; this is
not a verified guarantee for every CB35 model. These timings and physical
observations come from that hardware report, not a newly verified APK analysis.

## Notes

- The bed accepts only one BLE connection. While the Sealy app is open on a
  phone (including in the background) the bed stops advertising and the
  integration cannot connect.

### Relationship to Other Protocols

The CB35 shares the same 7-byte frame and most command bytes with **Okin Nordic** (Mattress Firm 900/iFlex). Key differences:

- **Init:** CB35 uses only `5A 0B 00 A5` wake; Okin Nordic also sends `09 05 0A 23 05 00 00`
- **Write mode:** CB35 requires write-without-response; Okin Nordic uses write-with-response
- **Extra motors:** CB35 adds neck, hips, and head+foot simultaneous
- **Extra presets:** TV/PC, Read, Inverse, Work, Extension
- **Light control:** CB35 adds brightness and color control
- **Massage:** CB35 has separate head/foot strength control

### Analysis provenance

**Ref:** [#310](https://github.com/kristofferR/ha-adjustable-bed/issues/310)

Protocol extracted from `com.okin.sealy` v1.1.1 APK analysis. Complete protocol definition at:
`disassembly/output/com.okin.sealy/extracted/assets/flutter_assets/assets/protocol/35_22_01.json`
