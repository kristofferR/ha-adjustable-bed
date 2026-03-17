# Logicdata SimplicityFrame (SILVERmotion)

## Overview

Logicdata beds use a proprietary "LogicLink" BLE protocol with XXTEA encryption, CRC-CCITT integrity checks, and SLIP framing. This is a completely separate protocol family from all other supported beds.

**Status:** Needs testing

**App:** SILVERmotion (`at.silvermotion`) - Flutter/Dart

## BLE Connection

| Property | Value |
|----------|-------|
| Service UUID | `b9934c43-5c91-462b-80a1-30fccc29d758` |
| Characteristic UUID | `b9934c44-5c91-462b-80a1-30fccc29d758` |
| Manufacturer ID | `0x0547` (1351) |
| BLE Pairing | **Required** (encrypted characteristic) |
| Write mode | Write without response |

## Detection

Detected automatically by:
1. **Manufacturer data** (Company ID 0x0547) - confidence 0.95
2. **Service UUID** (`b9934c43-...`) - confidence 1.0

## TX Pipeline

Commands go through a multi-stage pipeline before being written to BLE:

```
[3-byte command payload]
    → Pad to 8 bytes (zeros)
    → XXTEA encrypt (16-byte static key)
    → Append CRC-CCITT (2 bytes, big-endian)
    → Prepend length byte
    → SLIP frame (0xC0 delimiters, escape 0xC0/0xDB)
```

### XXTEA Encryption

- Algorithm: Corrected Block TEA (XXTEA)
- Key: 16-byte static key (`LogicLink_BT_Key` encoded as 4x uint32 LE)
- DELTA: `0x9E3779B9`
- Rounds: `6 + 52/n` where n = number of 32-bit words
- Word packing: Little-endian

### CRC-CCITT

- Initial value: `0xFFFF`
- Polynomial: `0x1021`
- Appended as 2 bytes, big-endian, after encrypted data

### SLIP Framing (RFC 1055)

| Byte | Name | Escaped as |
|------|------|-----------|
| `0xC0` | END | `0xDB 0xDC` |
| `0xDB` | ESC | `0xDB 0xDD` |

Frame format: `[END] [escaped data] [END]`

## Commands

All commands are 3-byte payloads `[opcode, param1, param2]`.

### Motor Control

| Command | Bytes | Notes |
|---------|-------|-------|
| Head up | `0x51 0x00 0x00` | Hold-style, repeat to move |
| Head down | `0x52 0x00 0x00` | Hold-style, repeat to move |
| Legs up | `0x51 0x01 0x00` | Hold-style, repeat to move |
| Legs down | `0x52 0x01 0x00` | Hold-style, repeat to move |
| Stop | `0xB0 0x00 0x01` | Stops all motors |

### Presets

Preset commands require an `AnyKeyPressed` preamble (`0xB0 0x00 0x00`) followed by a 50ms delay.

| Command | Bytes | Notes |
|---------|-------|-------|
| AnyKey pressed | `0xB0 0x00 0x00` | Preamble for presets |
| Memory 1 recall | `0x5C 0x00 0x00` | After AnyKey |
| Memory 2 recall | `0x5C 0x01 0x00` | After AnyKey |
| Flat | `0x5C 0x04 0x00` | After AnyKey |
| Save Memory 1 | `0x5B 0x00 0x00` | |
| Save Memory 2 | `0x5B 0x01 0x00` | |

### Under-bed Light

| Command | Bytes |
|---------|-------|
| Light on | `0x95 0x00 0x0F` |
| Light off | `0x95 0x00 0x00` |

### Massage

| Command | Bytes |
|---------|-------|
| Intensity up | `0x81 0x00 0x00` |
| Intensity down | `0x82 0x00 0x00` |
| Massage off | `0x86 0x00 0x00` |

## Timing

| Parameter | Value | Source |
|-----------|-------|--------|
| Motor repeat count | 10 | APK: `sendCount` |
| Motor repeat delay | 30ms | APK: `SF_GetPipelineTx` |
| Feature repeat count | 3 | APK: button command sends |
| Preset preamble delay | 50ms | APK: AnyKey → preset gap |

## Not Implemented

- **Move-to-position** (`0x5F`): No position feedback available, so absolute positioning cannot work
- **Reset commands** (`0x08`): Too dangerous for accidental activation

## Source

Protocol reverse-engineered from the SILVERmotion APK (`at.silvermotion`), a Flutter/Dart application. Key classes from Blutter analysis:
- `SF_GetPipelineTx` - TX pipeline filter chain configuration
- `SF_Controller` - Command method definitions
- `SF_CryptoXXTEA` - XXTEA implementation
- `SF_CRC16` - CRC-CCITT implementation
- `SF_SLIP` - SLIP framing
