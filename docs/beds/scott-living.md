# Scott Living

**Status:** Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Scott Living adjustable bed bases

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | Scott Living | `com.keeson.scottlivingrelease` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (4 motors: head, foot, tilt, lumbar) |
| Position Feedback | ❌ |
| Memory Presets | ✅ (3 slots) |
| Factory Presets | ✅ (Flat, Zero-G, TV, Anti-Snore) |
| Massage | ❌ |
| Light Control | ✅ (toggle) |

## Protocol Details

**Service UUID:** `0000ffe5-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `0000ffe9-0000-1000-8000-00805f9b34fb`
**Notify Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb`
**Format:** 9-byte packets with inverted sum checksum

## Detection

No auto-detection - must be manually selected during setup.

Note: Scott Living shares the same service UUID (FFE5) as Keeson and other beds. Without a unique device name pattern, it cannot be automatically distinguished.

## Packet Format

All commands are 9 bytes:

```text
[0xE6, 0xFE, 0x16, cmd0, cmd1, cmd2, cmd3, side, checksum]
```

Where:
- Bytes 0-2 = Header `[0xE6, 0xFE, 0x16]` (note: 0xE6, not 0xE5)
- Bytes 3-6 = Command bytes (32-bit value in little-endian)
- Byte 7 = Side selector (always 0x01 in this implementation)
- Byte 8 = Checksum: `(~sum(bytes 0-7)) & 0xFF` (inverted sum)

## Commands

### Motor Control (cmd0 byte)

| Action | Value | Notes |
|--------|-------|-------|
| Head Up | 0x01 | Hold to move |
| Head Down | 0x02 | Hold to move |
| Foot Up | 0x04 | Hold to move |
| Foot Down | 0x08 | Hold to move |
| Tilt Up | 0x10 | Hold to move |
| Tilt Down | 0x20 | Hold to move |
| Lumbar Up | 0x40 | Hold to move |
| Lumbar Down | 0x80 | Hold to move |
| Stop | 0x00 | All zeros |

### cmd1 Byte Commands

| Action | Full Value | cmd1 | Notes |
|--------|------------|------|-------|
| Memory 1 | 0x100 | 0x01 | |
| Light Toggle | 0x200 | 0x02 | |
| Zero-G | 0x1000 | 0x10 | Factory preset |
| Memory 2 | 0x2000 | 0x20 | |
| Memory 3 / TV | 0x4000 | 0x40 | Dual-purpose |
| Anti-Snore | 0x8000 | 0x80 | Factory preset |

### cmd3 Byte Commands

| Action | Full Value | cmd3 | Notes |
|--------|------------|------|-------|
| Flat | 0x8000000 | 0x08 | Factory preset |

## Command Examples

### Move Head Up
```text
[0xE6, 0xFE, 0x16, 0x01, 0x00, 0x00, 0x00, 0x01, checksum]
```

### Go to Flat Preset
```text
[0xE6, 0xFE, 0x16, 0x00, 0x00, 0x00, 0x08, 0x01, checksum]
```

### Toggle Lights
```text
[0xE6, 0xFE, 0x16, 0x00, 0x02, 0x00, 0x00, 0x01, checksum]
```

## Command Timing

| Operation | Repeat Count | Delay | Notes |
|-----------|-------------|-------|-------|
| Motor movement | 10 | 100ms | Continuous while held |
| Presets | 1 | - | Single command |
| Light toggle | 1 | - | Single command |
| Stop | 1 | - | Always sent after movement |

## Notes

1. Scott Living uses the same Keeson FFE5 service UUID but with a different packet format (9 bytes vs 8 bytes).

2. The header byte is 0xE6 (not 0xE5 like standard Keeson), and includes a side selector byte.

3. The checksum algorithm is inverted sum: `(~sum) & 0xFF`, which differs from Keeson's XOR checksum.

4. Memory 3 and TV preset share the same command value (0x4000).

5. The side byte is always 0x01 in the app's implementation, suggesting single-bed mode only.
