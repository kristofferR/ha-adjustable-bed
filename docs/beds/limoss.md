# Limoss

**Status:** Needs testing

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
| Motor Control | ✅ (head/back + legs) |
| Position Feedback | ✅ |
| Flat Preset | ✅ |
| Memory Presets | ❌ (capability is read, but preset recall/program commands are not exposed yet) |
| Light Control | ⚠️ Protocol has a toggle command (`0x70`), not exposed by default |
| Massage | ❌ |

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
| Stop All | `0xFF` |
| Flat (both down) | `0x51` |
| Query Capabilities | `0x02` |
| Ask Motor 1 Position | `0x10` |
| Ask Motor 2 Position | `0x20` |
| Ask Motor 3 Position | `0x30` |
| Ask Motor 4 Position | `0x40` |

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
- The integration currently maps motor 1 to head/back and motor 2 to legs.

## References

- `disassembly/output/com.limoss.limossremote/ANALYSIS.md`
- `disassembly/output/com.stawett/ANALYSIS.md`
