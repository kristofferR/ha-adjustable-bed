# Cool Base

**Status:** ❓ Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Cool Base adjustable bed bases (Keeson BaseI5 with cooling fan)

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | Cool Base | `com.keeson.coolbase` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (2 motors: head, foot) |
| Position Feedback | ❌ |
| Memory Presets | ✅ (1 slot) |
| Factory Presets | ✅ (Flat, Zero-G, TV, Anti-Snore, Lounge) |
| Massage | ✅ |
| Light Control | ✅ (toggle) |
| Fan Control | ✅ (left/right/sync, 3 levels) |

## Protocol Details

**Service UUID:** `0000ffe5-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `0000ffe9-0000-1000-8000-00805f9b34fb`
**Notify Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb`
**Format:** 8-byte packets with XOR checksum

## Detection

Devices are auto-detected by device name starting with `base-i5` (case-insensitive).

Note: Cool Base shares the same service UUID (FFE5) as Keeson and other beds, but is distinguished by the device name pattern.

## Packet Format

All commands are 8 bytes:

```text
[0xE5, 0xFE, 0x16, cmd0, cmd1, cmd2, cmd3, checksum]
```

Where:
- Bytes 0-2 = Header `[0xE5, 0xFE, 0x16]`
- Bytes 3-6 = Command bytes (32-bit value in little-endian)
- Byte 7 = Checksum: `(sum(bytes 0-6) ^ 0xFF) & 0xFF`

## Commands

### Motor Control

| Action | Value | cmd0 | Notes |
|--------|-------|------|-------|
| Head Up | 0x01 | 0x01 | Hold to move |
| Head Down | 0x02 | 0x02 | Hold to move |
| Foot Up | 0x04 | 0x04 | Hold to move |
| Foot Down | 0x08 | 0x08 | Hold to move |
| Stop | 0x00 | 0x00 | All zeros |

### Factory Presets

| Action | Value | cmd bytes |
|--------|-------|-----------|
| Flat | 0x08000000 | cmd3=0x08 |
| Zero-G | 0x00001000 | cmd1=0x10 |
| TV | 0x00004000 | cmd1=0x40 |
| Anti-Snore | 0x00008000 | cmd1=0x80 |
| Memory 1 | 0x00010000 | cmd2=0x01 |

### Light & Massage

| Action | Value | cmd bytes |
|--------|-------|-----------|
| Light Toggle | 0x00020000 | cmd2=0x02 |
| Massage Head | 0x00000800 | cmd1=0x08 |
| Massage Foot | 0x00000400 | cmd1=0x04 |
| Massage Level | 0x04000000 | cmd3=0x04 |

### Fan Control (Unique to Cool Base)

| Action | Value | cmd bytes | Notes |
|--------|-------|-----------|-------|
| Left Fan Cycle | 0x00400000 | cmd2=0x40 | Cycles 0→1→2→3→0 |
| Right Fan Cycle | 0x40000000 | cmd3=0x40 | Cycles 0→1→2→3→0 |
| Sync Fan Cycle | 0x00040000 | cmd2=0x04 | Both fans together |

## Notification Format

28-byte status notifications include:
- Byte 13, bit 6: Light status (on/off)
- Byte 19: Massage level (0-3)
- Byte 20: Left fan level (0-3)
- Byte 21: Right fan level (0-3)

## Command Timing

| Operation | Repeat Count | Delay | Notes |
|-----------|-------------|-------|-------|
| Motor movement | 10 | 100ms | Continuous while held |
| Presets | 1 | - | Single command |
| Fan cycle | 1 | - | Single command |
| Stop | 1 | - | Always sent after movement |

## Notes

1. Cool Base is a Keeson BaseI5 variant with additional fan/wind control features for cooling.

2. The fan commands cycle through levels 0→1→2→3→0. Each command increments the level by 1.

3. Fan levels are reported in notifications, allowing the integration to track current state.

4. The sync fan command controls both left and right fans together.
