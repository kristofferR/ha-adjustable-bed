# Limoss

**Status:** ❓ Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Limoss adjustable bed controllers
- Stawett-branded controllers using the same protocol

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | Limoss Remote | `com.limoss.limossremote` |
| ✅ | Stawett | `com.limoss.stawett` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (head/back + legs, 3/4 motor auto-detected) |
| Position Feedback | ✅ |
| Flat Preset | ✅ |
| Memory Presets | ✅ (software-based: saves raw positions, recalls via SetPos commands) |
| Light Control | ✅ (toggle via `0x70`) |
| Massage / Vibration | ✅ (up to 6 zones, zone count reported by capabilities query) |

## Protocol Details

**Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `0000ffe1-0000-1000-8000-00805f9b34fb`
**Notify Characteristic:** `0000ffe1-0000-1000-8000-00805f9b34fb`
**Format:** 10-byte encrypted packet

This protocol uses TEA encryption for every command/response payload.

## Detection

Auto-detection uses:
1. Device name containing `limoss` or `stawett`
2. Shared service UUID `0000ffe0-...` as a confidence boost

`FFE0` is shared with other bed types, so UUID alone is not enough.

## Packet Format

### Outer Frame (10 bytes)

```text
[0xDD, enc0, enc1, enc2, enc3, enc4, enc5, enc6, enc7, checksum]
```

- Byte 0: fixed header `0xDD`
- Bytes 1-8: TEA-encrypted inner payload
- Byte 9: outer checksum (`sum(bytes[0:9]) & 0xFF`)

### Inner Payload (before encryption, 8 bytes)

```text
[0xAA, cmd, p1, p2, p3, p4, counter, inner_checksum]
```

- Byte 0: fixed header `0xAA`
- Byte 1: command
- Bytes 2-5: parameters
- Byte 6: sequence counter
- Byte 7: inner checksum (`sum(bytes[0:7]) & 0xFF`)

## Implemented Commands

| Action | Command |
|--------|---------|
| Motor 1 Up / Down | `0x12` / `0x13` |
| Motor 2 Up / Down | `0x22` / `0x23` |
| Motor 3 Up / Down | `0x32` / `0x33` |
| Motor 4 Up / Down | `0x42` / `0x43` |
| Stop All | `0xFF` |
| Flat (both down) | `0x51` |
| Query Capabilities | `0x02` |
| Ask Motor 1 Position | `0x10` |
| Ask Motor 2 Position | `0x20` |
| Ask Motor 3 Position | `0x30` |
| Ask Motor 4 Position | `0x40` |
| Set Motor 1 Position | `0x11` |
| Set Motor 2 Position | `0x21` |
| Set Motor 3 Position | `0x31` |
| Set Motor 4 Position | `0x41` |
| Vibration Zone 1-6 | `0x60` - `0x65` |
| Light Toggle | `0x70` |

## Position Feedback

The bed responds to position queries with 32-bit big-endian raw values for each motor.
The integration converts raw values to estimated angles using per-motor max-angle settings.

## Command Timing

Default motor timing for this bed type:

- Pulse count: `12`
- Pulse delay: `80ms`

These values are derived from APK behavior (`LIMOSS_SENDING_INTERVAL = 80`).

## Notes

- Limoss/Stawett is a unique encrypted protocol and is not compatible with Okin, Solace, or Octo packet formats even though it shares `FFE0/FFE1` UUIDs.
- Motor mapping: motor 1 = back, motor 2 = legs, motor 3 = head (3+ motor beds), motor 4 = feet (4-motor beds). For 2-motor beds, head aliases to motor 1 and feet to motor 2.
- Memory presets are software-based: `program_memory` saves current raw positions locally, `preset_memory` recalls them via SetPos commands. The capability response reports how many memory slots the hardware supports.
- Vibration zone count is reported by the capabilities query and stored at runtime.

## References

- `disassembly/output/com.limoss.limossremote/ANALYSIS.md`
- `disassembly/output/com.stawett/ANALYSIS.md`
