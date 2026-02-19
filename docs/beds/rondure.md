# Rondure

**Status:** Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- 1500 Tilt Base (internal name: Rondure Hump)

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | 1500 Tilt Base Remote | `com.sfd.rondure_hump` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (4 motors: head, foot, tilt, lumbar) |
| Split-King | ✅ (independent side control) |
| Position Feedback | ❌ |
| Memory Presets | ❌ |
| Factory Presets | ✅ (Flat, Zero-G, TV/Anti-Snore) |
| Massage | ✅ (head, foot, lumbar zones) |
| Lights | ✅ |

## Protocol Details

**Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `0000ffe9-0000-1000-8000-00805f9b34fb`
**Read Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb`
**Alternative:** Nordic UART Service (6e400001-...)
**Format:** 8-byte (both sides) or 9-byte (single side) packets with checksum

## Detection

Manual bed type selection required. The service UUID `0000ffe0-...` is shared with many other bed types (Solace, Octo, etc.), so auto-detection is not possible.

## Packet Format

### Both Sides (8 bytes)

```text
[0xE5, 0xFE, 0x16, cmd[0], cmd[1], cmd[2], cmd[3], checksum]
```

### Single Side (9 bytes)

```text
[0xE6, 0xFE, 0x16, cmd[0], cmd[1], cmd[2], cmd[3], side, checksum]
```

Where:
- `0xE5` header = both sides, `0xE6` header = single side
- `0xFE, 0x16` = fixed protocol bytes
- `cmd[0-3]` = 32-bit command in little-endian order
- `side` = `0x01` for Side A, `0x02` for Side B
- `checksum` = bitwise NOT of sum of all preceding bytes

### Checksum Calculation

```python
checksum = (~sum(packet[:-1])) & 0xFF
```

## Commands

Commands are 32-bit values sent in little-endian byte order.

### Motor Control (Hold to move)

| Action | Command | Notes |
|--------|---------|-------|
| Head Up | `0x00000001` | Continuous while held |
| Head Down | `0x00000002` | Continuous while held |
| Foot Up | `0x00000004` | Continuous while held |
| Foot Down | `0x00000008` | Continuous while held |
| Tilt Up | `0x00000010` | Continuous while held |
| Tilt Down | `0x00000020` | Continuous while held |
| Lumbar Up | `0x00000040` | Continuous while held |
| Lumbar Down | `0x00000080` | Continuous while held |
| Stop | `0x00000000` | Stop all motors |

### Presets (Single press)

| Action | Command | Notes |
|--------|---------|-------|
| Flat | `0x08000000` | Go to flat position |
| Zero-G | `0x00001000` | Zero gravity position |
| TV/Anti-Snore | `0x00008000` | TV or anti-snore position |
| Timer/Level | `0x00000100` | Timer toggle |
| Read Preset | `0x00002000` | Reading position |
| Music/Memory | `0x00004000` | Music or memory preset |

### Massage Control

| Action | Command |
|--------|---------|
| Head Massage | `0x00000800` |
| Foot Massage | `0x00000400` |
| Lumbar Massage | `0x00400000` |
| Massage Mode 1 | `0x00100000` |
| Massage Mode 2 | `0x00200000` |
| Massage Mode 3 | `0x00080000` |

### Light Control

| Action | Command |
|--------|---------|
| Light Toggle | `0x00020000` |

## Configuration

### Side Selection (Split-King)

For split-king beds, configure the protocol variant:

| Variant | Value | Description |
|---------|-------|-------------|
| Both | `both` | Control both sides (default) |
| Side A | `side_a` | Control left side only |
| Side B | `side_b` | Control right side only |

## Command Timing

| Operation | Repeat Count | Delay | Notes |
|-----------|-------------|-------|-------|
| Motor movement | 25 | 50ms | Continuous while held |
| Presets | 1 | - | Single command |
| Massage toggle | 1 | - | Single command |
| Light toggle | 1 | - | Single command |
| Stop | 1 | - | Always sent after movement |

## Notes

1. The app supports both BLE and Classic Bluetooth. This implementation uses BLE only.

2. For Classic Bluetooth, the protocol uses big-endian command encoding instead of little-endian.

3. Timer status can be read from notifications (byte values 1=10min, 2=20min, 3=30min).
