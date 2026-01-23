# Sleepy's Elite (MFRM)

**Status:** Untested

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed) from MFRM Sleepy's Elite app v1.1.4 (com.okin.bedding.sleepy)

## Known Models

- MFRM Sleepy's Elite adjustable beds
- Mattress Firm adjustable beds using the Sleepy's Elite app

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [MFRM Sleepy's Elite](https://play.google.com/store/apps/details?id=com.okin.bedding.sleepy) | `com.okin.bedding.sleepy` |

## Protocol Variants

The Sleepy's Elite app supports multiple control box types. This integration implements the two main BLE protocols:

| Variant | Packet Size | Checksum | Lumbar Support | Service UUID |
|---------|-------------|----------|----------------|--------------|
| BOX15 | 9 bytes | Yes | ✅ | FFE5 |
| BOX24 | 7 bytes | No | ❌ | 62741523 (OKIN 64-bit) |

**Protocol Selection:**

- If your bed has **lumbar control**, use the BOX15 variant
- If your bed has **OKIN 64-bit service UUID** (62741523-...), use BOX24
- When in doubt, try BOX24 first (simpler protocol)

## Features

| Feature | BOX15 | BOX24 |
|---------|-------|-------|
| Motor Control | ✅ | ✅ |
| Lumbar Motor | ✅ | ❌ |
| Position Feedback | ❌ | ❌ |
| Memory Presets | ❌ | ❌ |
| Flat Preset | ✅ | ✅ |
| Zero-G Preset | ✅ | ✅ |

## Protocol Details

### BOX15 Protocol (9-byte packets with checksum)

**Service UUID:** `0000FFE5-0000-1000-8000-00805F9B34FB`

**Write Characteristic:** `0000FFE9-0000-1000-8000-00805F9B34FB`

**Packet Structure:**

```text
[0]    Header1: 0xE6
[1]    Header2: 0xFE
[2]    Prefix:  0x2C
[3]    Motor command
[4]    Preset data (byte 4)
[5]    Reserved: 0x00
[6]    Preset data (byte 6)
[7]    Reserved: 0x00
[8]    Checksum: (~sum(bytes[0:8])) & 0xFF
```

**Motor Commands (byte 3):**

| Command | Hex | Description |
|---------|-----|-------------|
| STOP | 0x00 | Stop all motors |
| HEAD UP | 0x02 | Raise head |
| HEAD DOWN | 0x01 | Lower head |
| FOOT UP | 0x08 | Raise foot |
| FOOT DOWN | 0x04 | Lower foot |
| LUMBAR UP | 0x20 | Raise lumbar |
| LUMBAR DOWN | 0x10 | Lower lumbar |

**Preset Commands (byte 4 + byte 6):**

| Preset | Byte 4 | Byte 6 |
|--------|--------|--------|
| Flat | 0x00 | 0x10 |
| Zero-G | 0x20 | 0x00 |

**Example - Move Head Up:**

```text
E6 FE 2C 02 00 00 00 00 [checksum]
```

### BOX24 Protocol (7-byte packets)

**Service UUID:** `62741523-52F9-8864-B1AB-3B3A8D65950B` (OKIN 64-bit)

**Write Characteristic:** `62741625-52F9-8864-B1AB-3B3A8D65950B`

**Packet Structure:**

```text
[0]    Header1: 0xA5
[1]    Header2: 0x5A
[2]    Reserved: 0x00
[3]    Reserved: 0x00
[4]    Reserved: 0x00
[5]    Command type: 0x40
[6]    Motor/Preset command
```

**Motor Commands (byte 6):**

| Command | Hex | Description |
|---------|-----|-------------|
| STOP | 0x00 | Stop all motors |
| HEAD UP | 0x02 | Raise head |
| HEAD DOWN | 0x01 | Lower head |
| FOOT UP | 0x06 | Raise foot |
| FOOT DOWN | 0x05 | Lower foot |

**Preset Commands (byte 6):**

| Preset | Hex |
|--------|-----|
| Flat | 0xCC |
| Zero-G | 0xC0 |

**Example - Move Head Up:**

```text
A5 5A 00 00 00 40 02
```

## Checksum Calculation (BOX15 only)

The BOX15 protocol uses an inverted 8-bit sum (one's complement):

```python
checksum = (~sum(bytes[0:8])) & 0xFF
```

## Command Timing

From app disassembly:

- **Repeat Interval:** Continuous while button held
- **Pattern:** Send command repeatedly with ~100ms delay
- **Stop Required:** Yes, explicit stop after motor release

## Detection

Sleepy's Elite beds are **auto-detected** by device name patterns:

- Device names containing "sleepy" or "mfrm" (case-insensitive)
- Protocol variant is selected based on available service UUIDs:
  - OKIN 64-bit service (62741523-...) → BOX24
  - FFE5 service (0000FFE5-...) → BOX15

**If auto-detection fails:**

1. Use nRF Connect app to scan your bed
2. If you see service `62741523-...` → manually select BOX24
3. If you only see service `0000FFE5-...` → manually select BOX15
4. If BOX24 doesn't work and your bed has lumbar → try BOX15

## Related Protocols

- **[DewertOkin](dewertokin.md)** - Different command format, uses handle writes
- **[Okin 64-bit](okimat.md#okin-64-bit-protocol)** - Similar service UUID but different packet format
- **[Keeson](keeson.md)** - Same FFE5 service but different command encoding
