# Sleepy's Elite (MFRM)

**Status:** ❓ Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed) and [SethCalkins](https://github.com/SethCalkins) (BOX25 Star, ported from [ha-dewertokin-bed](https://github.com/sethcalkins/ha-dewertokin-bed))

## Known Models

- MFRM Sleepy's Elite adjustable beds
- Mattress Firm adjustable beds using the Sleepy's Elite app
- DewertOkin BOX25 Star controller beds (BLE name: `Star*`)

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [MFRM Sleepy's Elite](https://play.google.com/store/apps/details?id=com.okin.bedding.sleepy) | `com.okin.bedding.sleepy` |

## Protocol Variants

The Sleepy's Elite app supports multiple control box types. This integration implements three BLE protocols:

| Variant | Packet Size | Checksum | Lumbar | Neck | Lights | Massage | Positions | Service UUID |
|---------|-------------|----------|--------|------|--------|---------|-----------|--------------|
| BOX15 | 9 bytes | Yes | ✅ | ❌ | ❌ | ❌ | ❌ | FFE5 |
| BOX24 | 7 bytes | No | ❌ | ❌ | ❌ | ❌ | ❌ | 62741523 (OKIN 64-bit) |
| BOX25 Star | 5-10 bytes | No | ✅ | ✅ | ✅ | ✅ | ✅ | 6e400001 (Nordic UART) |

**Protocol Selection:**

- If your device name starts with **"Star"** and advertises Nordic UART, use the BOX25 Star variant
- If your bed has **lumbar control** (but no Star name), use the BOX15 variant
- If your bed has **OKIN 64-bit service UUID** (62741523-...), use BOX24
- Octo Star2 beds also use `Star2` names, but they advertise the Octo Star2 UUID and are detected as Octo first
- When in doubt, try BOX24 first (simplest protocol)

## Features

| Feature | BOX15 | BOX24 | BOX25 Star |
|---------|-------|-------|------------|
| Motor Control | ✅ | ✅ | ✅ |
| Lumbar Motor | ✅ | ❌ | ✅ |
| Neck Tilt Motor | ❌ | ❌ | ✅ |
| Position Feedback | ❌ | ❌ | ✅ (0-100%) |
| Direct Position Control | ❌ | ❌ | ✅ (protocol: head/feet/lumbar) |
| Memory Presets | ❌ | ❌ | ✅ (4 slots) |
| Memory Programming | ❌ | ❌ | ✅ |
| Flat Preset | ✅ | ✅ | ✅ |
| Zero-G Preset | ✅ | ✅ | ✅ |
| Anti-Snore Preset | ❌ | ❌ | ✅ |
| Lounge Preset | ❌ | ❌ | ✅ |
| Under-Bed Lights | ❌ | ❌ | ✅ (on/off) |
| Massage | ❌ | ❌ | ✅ (3 wave modes) |
| Massage Intensity | ❌ | ❌ | ✅ (per-zone) |

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

### BOX25 Star Protocol (multi-subsystem, Nordic UART)

**Service UUID:** `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` (Nordic UART)

**Write Characteristic (TX):** `6E400002-B5A3-F393-E0A9-E50E24DCCA9E`

**Notify Characteristic (RX):** `6E400003-B5A3-F393-E0A9-E50E24DCCA9E`

**BLE Device Name:** Starts with `Star` (e.g., `Star1234`)

**Integration motor surface:** `head`, `feet`, `lumbar`, `tilt`

**Integration direct-position surface:** `head` and `feet` sliders/services. The protocol also reports lumbar position and accepts direct lumbar position commands, but neck tilt does not currently have a protocol-backed position zone.

The BOX25 Star uses a multi-subsystem protocol with a two-track initialization:

1. **Wake:** Send `5A 0B 00 A5`, wait 150ms
2. **Motor init:** Send `00 D0`, wait 80ms (required before motor/preset commands)
3. **Massage/Light init:** Send `00 B0`, wait 80ms (required before massage/light commands)

#### Motor Commands (7 bytes, `05 02` prefix)

```text
[0-1]  Header: 05 02
[2]    Flags (preset/exit)
[3]    Motor bitmask (directional)
[4]    Preset/Memory store bitmask
[5]    Memory recall bitmask
[6]    Reserved: 0x00
```

**Motor Bitmask (byte 3):**

| Bit | Motor | Direction |
|-----|-------|-----------|
| 0x01 | Head | Up |
| 0x02 | Head | Down |
| 0x04 | Foot | Up |
| 0x08 | Foot | Down |
| 0x10 | Lumbar | Up |
| 0x20 | Lumbar | Down |
| 0x40 | Neck Tilt | Up |
| 0x80 | Neck Tilt | Down |

**Preset Commands (byte 2 or byte 4):**

| Preset | Byte 2 | Byte 4 |
|--------|--------|--------|
| Flat | 0x08 | — |
| Zero Gravity | — | 0x10 |
| Lounge/Relax | — | 0x20 |
| Ascent | — | 0x40 |
| Anti-Snore | — | 0x80 |

Presets require a confirmation: send the preset command, then send `MOTOR_STOP` (`05 02 00 00 00 00 00`).

**Memory Commands:**

| Action | Slot | Byte 4 (store) | Byte 5 (recall) |
|--------|------|-----------------|------------------|
| Store | 1 | 0x01 | — |
| Store | 2 | 0x02 | — |
| Store | 3 | 0x04 | — |
| Store | 4 | 0x08 | — |
| Recall | 1 | — | 0x01 |
| Recall | 2 | — | 0x02 |
| Recall | 3 | — | 0x04 |
| Recall | 4 | — | 0x08 |

#### Position Commands (5 bytes, `03 F0` prefix)

```text
[0-1]  Header: 03 F0
[2]    Zone (0x00=head, 0x01=foot, 0x02=lumbar, 0x07=sync)
[3]    Position (0-100)
[4]    Reserved: 0x00
```

#### Lighting Commands (6 bytes, `04 E0` prefix)

```text
Color:      04 E0 01 [color 0-7] 00 00
Brightness: 04 E0 00 [level 1-6] 00 00
```

| Color | Value |
|-------|-------|
| Off | 0x00 |
| White | 0x01 |
| Red | 0x02 |
| Orange | 0x03 |
| Yellow | 0x04 |
| Green | 0x05 |
| Blue | 0x06 |
| Purple | 0x07 |

#### Vibration Commands (6 bytes, `04 E0 06` prefix)

```text
04 E0 06 [head 0-8] [foot 0-8] 00
```

#### Massage Commands (10 bytes, `08 02` prefix)

```text
[0-1]  Header: 08 02
[2]    Head intensity add (0x01 = step up)
[3]    Head intensity reduce (0x01 = step down)
[4]    Foot intensity add
[5]    Foot intensity reduce
[6]    All flags (0x01 = all add, 0x02 = all reduce)
[7]    Mode (0x08 = wave1, 0x10 = wave2, 0x20 = wave3)
[8]    Timer
[9]    Reserved: 0x00
```

#### Notification Parsing

The bed pushes status via Nordic UART RX notifications:

| Prefix | Length | Content |
|--------|--------|---------|
| `05` | 7+ bytes | Motor/movement status (bytes 2-6 non-zero = moving) |
| `03` | 4+ bytes | Position report: byte 1 = zone, byte 2 = position (0-100) |
| `04` | 6+ bytes | Light/vibration status |
| `08` | 10 bytes | Massage status (byte 7 = active mode, 0 = off) |

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
- **BOX25 wake delay:** 150ms after wake command
- **BOX25 init delay:** 80ms after subsystem init

## Detection

Sleepy's Elite beds are auto-detected by name plus BLE services:

- Device names starting with "star" (case-insensitive) plus Nordic UART → BOX25 Star
- Device names starting with "star" without Nordic UART are treated as a low-confidence BOX25 match because Octo Star2 uses similar names
- Device names containing "sleepy" or "mfrm" (case-insensitive):
  - OKIN 64-bit service (62741523-...) → BOX24
  - FFE5 service (0000FFE5-...) → BOX15

**If auto-detection fails:**

1. Use nRF Connect app to scan your bed
2. If device name starts with "Star" → manually select BOX25 Star
3. If you see service `62741523-...` → manually select BOX24
4. If you only see service `0000FFE5-...` → manually select BOX15
5. If BOX24 doesn't work and your bed has lumbar → try BOX15

## Related Protocols

- **[DewertOkin](dewertokin.md)** - Different command format, uses handle writes
- **[Okin 64-bit](okimat.md#okin-64-bit-protocol)** - Similar service UUID but different packet format
- **[Keeson](keeson.md)** - Same FFE5 service but different command encoding
