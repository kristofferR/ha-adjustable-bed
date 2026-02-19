# SBI / Q-Plus (Costco)

**Status:** Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Q-Plus adjustable bed bases (sold through Costco)
- SBI (South Bay International) branded beds

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | Q-Plus | `com.sbi.costco` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (4 motors: head, foot, tilt, lumbar) |
| Position Feedback | ✅ (pulse-to-angle lookup tables) |
| Memory Presets | ✅ (2 slots) |
| Factory Presets | ✅ (Flat, Zero-G, TV) |
| Massage | ✅ (3 modes, head/foot/lumbar zones) |
| Light Control | ✅ (toggle) |
| Dual Bed Control | ✅ (A/B/Both modes for split-king) |

## Protocol Details

**Service UUID:** Uses discovery (typically FFE5)
**Write Characteristic:** `0000ffe9-0000-1000-8000-00805f9b34fb`
**Notify Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb`
**Alternate (Nordic UART):** `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
**Format:** 8 or 9-byte packets with inverted sum checksum

## Detection

No auto-detection - must be manually selected during setup.

Note: SBI shares service UUIDs with Keeson and other beds. Without a unique identifier, it cannot be automatically distinguished.

## Protocol Variants

SBI supports split-king (dual bed) configurations with three modes:

| Variant | Format | Header | Side Byte | Description |
|---------|--------|--------|-----------|-------------|
| Both | 8 bytes | 0xE5 | N/A | Controls both sides simultaneously |
| Side A | 9 bytes | 0xE6 | 0x01 | Controls left/A side only |
| Side B | 9 bytes | 0xE6 | 0x02 | Controls right/B side only |

## Packet Format

### 8-byte format (Both mode)

```text
[0xE5, 0xFE, 0x16, cmd0, cmd1, cmd2, cmd3, checksum]
```

### 9-byte format (A/B mode)

```text
[0xE6, 0xFE, 0x16, cmd0, cmd1, cmd2, cmd3, side, checksum]
```

Where:
- Bytes 0-2 = Header
- Bytes 3-6 = Command bytes (32-bit little-endian value)
- Byte 7 (9-byte only) = Side selector (1=A, 2=B)
- Last byte = Checksum: `(~sum(bytes 0 to n-1)) & 0xFF`

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

### Preset Commands

| Action | Full Value | cmd bytes |
|--------|------------|-----------|
| Flat | 0x08000000 | cmd3=0x08 |
| Zero-G | 0x00001000 | cmd1=0x10 |
| Reset | 0x08001000 | cmd1=0x10, cmd3=0x08 |
| Memory 1 | 0x00002000 | cmd1=0x20 |
| Memory 2 | 0x00004000 | cmd1=0x40 |
| TV | 0x00008000 | cmd1=0x80 |

### Light Command

| Action | Full Value | cmd bytes |
|--------|------------|-----------|
| Light Toggle | 0x00020000 | cmd2=0x02 |

### Massage Commands

| Action | Full Value | cmd bytes |
|--------|------------|-----------|
| Massage Level | 0x00000100 | cmd1=0x01 |
| Foot Massage | 0x00000400 | cmd1=0x04 |
| Head Massage | 0x00000800 | cmd1=0x08 |
| Mode 1 | 0x00100000 | cmd2=0x10 |
| Mode 2 | 0x00200000 | cmd2=0x20 |
| Mode 3 | 0x00080000 | cmd2=0x08 |
| Lumbar Massage | 0x00400000 | cmd2=0x40 |

## Position Feedback

**Notify Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb`

Notifications are 16+ byte packets. Position data is extracted from:
- **Bytes 3-4:** Head pulse count (little-endian 16-bit)
- **Bytes 5-6:** Foot pulse count (little-endian 16-bit)

Pulse values are converted to angles via calibrated lookup tables from the APK.

### Head Angle (0-60 degrees)

Pulse values map to angles using a 61-entry lookup table:

```
[0, 327, 577, 855, 1148, 1676, 2083, 2401, 2711, 3020, 3402, 3679, 4019, 4529,
 4864, 5262, 5633, 6024, 6453, 6826, 7239, 7611, 8015, 8423, 8862, 9240, 9632,
 10029, 10404, 10840, 11245, 11640, 11976, 12351, 12752, 13106, 13511, 13819,
 14169, 14518, 14901, 15217, 15556, 15856, 16177, 16530, 16788, 17118, 17389,
 17700, 18000, 18268, 18481, 18767, 19035, 19260, 19487, 19757, 19970, 20164, 20413]
```

### Foot Angle (0-32 degrees)

Pulse values map to angles using a 33-entry lookup table:

```
[0, 570, 784, 968, 1150, 1372, 1653, 1837, 2062, 2283, 2494, 2755, 3015, 3290,
 3578, 3819, 4039, 4261, 4544, 4895, 5170, 5461, 5723, 6020, 6334, 6631, 6922,
 7243, 7546, 7810, 8174, 8546, 8718]
```

### Pulse Inversion

Pulse values >= 32768 are inverted: `pulse = 65535 - pulse`

## Command Timing

| Operation | Repeat Count | Delay | Notes |
|-----------|-------------|-------|-------|
| Motor movement | 10 | 100ms | Continuous while held |
| Presets | 1 | - | Single command |
| Massage toggle | 1 | - | Single command |
| Light toggle | 1 | - | Single command |
| Stop | 1 | - | Always sent after movement |

## Notes

1. SBI beds are sold through Costco under the Q-Plus brand name.

2. The app supports both BLE and Classic Bluetooth connections. This integration uses BLE only.

3. Split-king beds use the A/B/Both variant modes. Configure the appropriate variant during setup.

4. The position feedback feature requires enabling angle sensing in the integration options.

5. The app includes additional features (weather, alarms, sleep tracking) that are not relevant to bed control.

6. Multiple remote layouts are supported in the app (H, M, M2, M3, MX) with varying button counts.
