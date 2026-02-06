# TiMOTION AHF

**Status:** Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- TiMOTION AHF devices advertising names starting with `AHF`
- Adjustable bed/recliner controllers with up to 5 motor channels

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | AHF Remote | `com.timotion.ahf` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (up to 5 motors) |
| Position Feedback | ❌ |
| Memory Presets | ❌ |
| Factory Presets | ❌ |
| Under-bed Lights | ✅ (toggle semantics) |
| Massage | ❌ |

## Protocol Details

**Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e` (Nordic UART)  
**Write Characteristic:** `6e400002-b5a3-f393-e0a9-e50e24dcca9e`  
**Notify Characteristic:** `6e400003-b5a3-f393-e0a9-e50e24dcca9e`  
**Format:** 11-byte bitmask packet, no TX checksum

## Detection

Auto-detection uses:
1. Device name prefix `AHF`
2. Nordic UART service as confidence boost

Because Nordic UART is shared by many bed types, AHF detection is name-led.

## Packet Format

All commands are 11 bytes:

```text
[0xDD, 0xDD, 0xFF, group1, group1, group2, group2, 0x00, 0x00, 0x00, 0x00]
```

- `group1` controls motors 1-3
- `group2` controls motors 4-5 and light/chair toggles

## Implemented Commands

### Group 1 (Motors 1-3)

| Action | Bitmask | Packet Core |
|--------|---------|-------------|
| Motor 1 Up / Down | `0x01` / `0x02` | `... group1=0x01/0x02 ...` |
| Motor 2 Up / Down | `0x04` / `0x08` | `... group1=0x04/0x08 ...` |
| Motor 3 Up / Down | `0x10` / `0x20` | `... group1=0x10/0x20 ...` |

### Group 2 (Motors 4-5 + Extras)

| Action | Bitmask | Packet Core |
|--------|---------|-------------|
| Motor 4 Up / Down | `0x01` / `0x02` | `... group2=0x01/0x02 ...` |
| Motor 5 Up / Down | `0x04` / `0x08` | `... group2=0x04/0x08 ...` |
| Night Light Toggle | `0x10` | `... group2=0x10 ...` |
| Under-bed Light Toggle | `0x20` | `... group2=0x20 ...` |
| Chair Mode Toggle | `0x40` | `... group2=0x40 ...` |

### Stop

| Action | Packet |
|--------|--------|
| Stop All | `DD DD FF 00 00 00 00 00 00 00 00` |

Stop is sent 3 times at 100ms intervals.

## Entity Mapping

Current integration mapping:
- `back` -> motor 1
- `legs` -> motor 2
- `head` -> motor 3
- `feet` -> motor 4
- `pillow` -> motor 5 (exposed when `motor_count >= 4`)

## Notification Format

Status notifications are 15 bytes and must pass checksum validation:

```text
Header byte: 0x9D
Checksum: sum(bytes[2..13]) & 0x7F == byte[14]
```

Parsed fields:
- Byte 2: feature lock mask
- Byte 3: light state (`0=off`, `1=white`, `2=green`, `3=red`)

## Command Timing

| Operation | Repeat Count | Delay | Notes |
|-----------|-------------|-------|-------|
| Motor movement (default) | 10 | 100ms | Bed-type pulse defaults |
| Light toggle | 2 | 100ms | Repeated toggle command |
| Stop | 3 | 100ms | Explicit stop burst |

## Notes

1. This protocol has no memory preset or flat/Zero-G commands.
2. Light control is toggle-only; there are no discrete on/off packets.
3. The app does not send an explicit initialization command and relies on notifications after connect.

## References

- `disassembly/output/com.timotion.ahf/ANALYSIS.md`

