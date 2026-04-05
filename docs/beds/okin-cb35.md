# DewertOkin CB35 Star

**Status:** Needs testing
**Protocol version:** CB.35.22.01
**Ref:** [#310](https://github.com/kristofferR/ha-adjustable-bed/issues/310)

## Known Brands

- Sealy Posturematic (Element, Ascent, Apex)

## Detection

| Signal | Value |
|--------|-------|
| Device name | Starts with `Star` (e.g., `Star352201011800`) |
| Service UUID | Nordic UART `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` |
| Manufacturer ID | 89 (OKIN) |

## Protocol

Uses the same 7-byte command frame as Okin Nordic:

```
[0x5A, 0x01, 0x03, 0x10, 0x30, CMD, 0xA5]
```

**Service:** Nordic UART (6E400001)
**Write characteristic:** 6E400002 (write-without-response)
**Notify characteristic:** 6E400003

### Init Sequence

Only a wake command is needed:
```
5A 0B 00 A5
```

### Motor Commands

| Action | CMD byte | Full packet |
|--------|----------|-------------|
| Head Up | 0x00 | `5A 01 03 10 30 00 A5` |
| Head Down | 0x01 | `5A 01 03 10 30 01 A5` |
| Foot Up | 0x02 | `5A 01 03 10 30 02 A5` |
| Foot Down | 0x03 | `5A 01 03 10 30 03 A5` |
| Lumbar Up | 0x06 | `5A 01 03 10 30 06 A5` |
| Lumbar Down | 0x07 | `5A 01 03 10 30 07 A5` |
| Hips Up | 0x08 | `5A 01 03 10 30 08 A5` |
| Hips Down | 0x09 | `5A 01 03 10 30 09 A5` |
| Neck Up | 0x0A | `5A 01 03 10 30 0A A5` |
| Neck Down | 0x0B | `5A 01 03 10 30 0B A5` |
| Head+Foot Up | 0x0C | `5A 01 03 10 30 0C A5` |
| Head+Foot Down | 0x0D | `5A 01 03 10 30 0D A5` |
| Stop | 0x0F | `5A 01 03 10 30 0F A5` |

### Presets

| Preset | CMD byte |
|--------|----------|
| Flat | 0x10 |
| TV/PC | 0x11 |
| Read | 0x12 |
| Zero Gravity | 0x13 |
| Inverse | 0x14 |
| Work | 0x15 |
| Anti-Snore | 0x16 |
| Lounge | 0x17 |
| Incline | 0x18 |
| Extension | 0x19 |
| Memory 1 | 0x1A |
| Memory 2 | 0x1B |

### Light Control

| Action | CMD byte |
|--------|----------|
| Light Color Change | 0x70 |
| Light Toggle | 0x71 |
| Light On | 0x73 |
| Light Off | 0x74 |
| Light Brighter | 0x80 |
| Light Dim | 0x81 |

### Massage Control

| Action | CMD byte |
|--------|----------|
| Massage Open | 0x52 |
| Massage Toggle | 0x5A |
| Wave Up | 0x58 |
| Wave Down | 0x59 |
| Strength Head Up | 0x60 |
| Strength Head Down | 0x61 |
| Strength Foot Up | 0x62 |
| Strength Foot Down | 0x63 |
| Massage Time Switch | 0x6D |
| Massage Stop | 0x6F |

### Timing

Motor commands repeat every 300ms while held. Stop and massage commands send 3 times (initial + 2 repeats at 300ms).

## Relationship to Other Protocols

The CB35 shares the same 7-byte frame and most command bytes with **Okin Nordic** (Mattress Firm 900/iFlex). Key differences:

- **Init:** CB35 uses only `5A 0B 00 A5` wake; Okin Nordic also sends `09 05 0A 23 05 00 00`
- **Write mode:** CB35 requires write-without-response; Okin Nordic uses write-with-response
- **Extra motors:** CB35 adds neck, hips, and head+foot simultaneous
- **Extra presets:** TV/PC, Read, Inverse, Work, Extension
- **Light control:** CB35 adds brightness and color control
- **Massage:** CB35 has separate head/foot strength control

## App

- **Android:** Sealy Posturematic (`com.okin.sealy`) — Flutter app, protocol defined in JSON asset
- **iOS:** Sealy Posturematic (App Store)
- **Developer:** Star Seeds Co LTD (DewertOkin)

## Source

Protocol extracted from `com.okin.sealy` v1.1.1 APK analysis. Complete protocol definition at:
`disassembly/output/com.okin.sealy/extracted/assets/flutter_assets/assets/protocol/35_22_01.json`
