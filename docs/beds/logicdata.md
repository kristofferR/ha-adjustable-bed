# Logicdata SimplicityFrame (SILVERmotion)

**Status:** ❓ Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

> [!NOTE]
> For the MOTIONrelax phone and tablet Android apps, use the separate
> [LOGICDATA app profiles](logicdata-app.md).

## Known Models

- Logicdata SimplicityFrame beds controlled by the SILVERmotion app
- Advertises Bluetooth manufacturer ID `0x0547` (1351)

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [SILVERmotion](https://play.google.com/store/apps/details?id=at.silvermotion) (Flutter/Dart) | `at.silvermotion` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head/back, legs |
| Position Feedback | ❌ |
| Flat Preset | ✅ |
| Memory Presets | ✅ (2 slots, recall and save) |
| Massage | ✅ (intensity up/down, off) |
| Under-bed Light | ✅ (discrete on/off) |
| Move-to-position | ❌ (see [Not Implemented](#not-implemented)) |

## Protocol Details

Logicdata beds use a proprietary "LogicLink" BLE protocol with XXTEA encryption,
CRC-CCITT integrity checks, and SLIP framing. This is a completely separate
protocol family from all other supported beds.

**Service UUID:** `b9934c43-5c91-462b-80a1-30fccc29d758`
**Write Characteristic:** `b9934c44-5c91-462b-80a1-30fccc29d758`
**Manufacturer ID:** `0x0547` (1351)
**Format:** 3-byte command payload, encrypted, CRC-checked and SLIP-framed

### BLE Connection

| Property | Value |
|----------|-------|
| BLE Pairing | **Required** (encrypted characteristic) |
| Write mode | Write without response |

### TX Pipeline

Commands go through a multi-stage pipeline before being written to BLE:

```
[3-byte command payload]
    → Pad to 8 bytes (zeros)
    → XXTEA encrypt (16-byte static key)
    → Append CRC-CCITT (2 bytes, big-endian)
    → Prepend length byte
    → SLIP frame (0xC0 delimiters, escape 0xC0/0xDB)
```

Each 3-byte command therefore becomes `C0`, length `0A`, 8 encrypted bytes,
2 CRC bytes and `C0`: 13 bytes, or more when SLIP escapes a byte.

### XXTEA Encryption

- Algorithm: Corrected Block TEA (XXTEA)
- Key: 16-byte static key `6C 4F 42 F5 67 68 02 E2 53 AC 9A 27 02 A6 37 AB`,
  packed as four little-endian uint32 words
- DELTA: `0x9E3779B9`
- Rounds: `6 + 52/n` where n = number of 32-bit words
- Word packing: Little-endian

> [!NOTE]
> Earlier versions of this guide described the key as `LogicLink_BT_Key`. That is
> not the key material: the ASCII text differs from the bytes above. The bytes in
> `beds/logicdata.py` match the key an independent clean-room analysis recovered
> from the related LOGICDATA SimplicityFrame app's native library.

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

## Detection / Setup

Detected automatically by:

1. **Manufacturer data** (Company ID 0x0547) - confidence 0.95
2. **Service UUID** (`b9934c43-...`) - confidence 1.0

BLE pairing is required before the encrypted characteristic accepts commands.

## Commands

All commands are 3-byte payloads `[opcode, param1, param2]`. The on-wire frames
below are produced by the shipped pipeline; the static key makes them constant.

### Motor Control

| Command | Bytes | On-wire frame | Notes |
|---------|-------|---------------|-------|
| Head up | `0x51 0x00 0x00` | `C0 0A 85 CB F9 5A 9E 86 B8 5D C2 3A C0` | Hold-style, repeat to move |
| Head down | `0x52 0x00 0x00` | `C0 0A 0A 7A 39 49 A6 BD D0 BC 0B 26 C0` | Hold-style, repeat to move |
| Legs up | `0x51 0x01 0x00` | `C0 0A 96 F6 7E 0E 43 4A CC 27 DD 7A C0` | Hold-style, repeat to move |
| Legs down | `0x52 0x01 0x00` | `C0 0A 4C E5 F3 67 69 43 7A DB DD E5 95 C0` | Hold-style, repeat to move (contains an escaped `DB`) |
| Stop | `0xB0 0x00 0x01` | `C0 0A E0 52 C4 14 A7 82 60 DE 31 46 C0` | Stops all motors |

HA's back and feet controls use the head and legs commands. Every movement ends
with one Stop, sent with a fresh cancel event so it also runs after cancellation.

### Presets

Preset commands require an `AnyKeyPressed` preamble (`0xB0 0x00 0x00`) followed by a 50ms delay.

| Command | Bytes | On-wire frame | Notes |
|---------|-------|---------------|-------|
| AnyKey pressed | `0xB0 0x00 0x00` | `C0 0A C9 74 BF A6 14 62 25 41 7A 24 C0` | Preamble for presets |
| Memory 1 recall | `0x5C 0x00 0x00` | `C0 0A A2 AD D4 F2 1C 16 C2 72 45 01 C0` | After AnyKey |
| Memory 2 recall | `0x5C 0x01 0x00` | `C0 0A AF A9 F5 CD 82 BF 2D 69 2F 02 C0` | After AnyKey |
| Flat | `0x5C 0x04 0x00` | `C0 0A 7A E8 78 FA 17 5C 7F 16 A1 93 C0` | After AnyKey |
| Save Memory 1 | `0x5B 0x00 0x00` | `C0 0A E7 23 31 51 D5 84 72 80 E9 4B C0` | |
| Save Memory 2 | `0x5B 0x01 0x00` | `C0 0A 2B 03 BA 94 1C B5 0E 1B 57 96 C0` | |

### Under-bed Light

| Command | Bytes | On-wire frame |
|---------|-------|---------------|
| Light on | `0x95 0x00 0x0F` | `C0 0A 90 C8 60 A0 AB 95 FC 56 6A F0 C0` |
| Light off | `0x95 0x00 0x00` | `C0 0A AC 1F F2 D9 8C 52 B2 1B E7 01 C0` |

### Massage

| Command | Bytes | On-wire frame |
|---------|-------|---------------|
| Intensity up | `0x81 0x00 0x00` | `C0 0A 2F 16 F4 A4 7A C8 64 B6 94 CE C0` |
| Intensity down | `0x82 0x00 0x00` | `C0 0A CA 83 B3 4D 40 EB 20 31 C3 FE C0` |
| Massage off | `0x86 0x00 0x00` | `C0 0A 88 76 D3 AF EE 50 80 3F 76 B2 C0` |

## Command Timing

| Parameter | Value | Source |
|-----------|-------|--------|
| Motor repeat count | 10 | APK: `sendCount` |
| Motor repeat delay | 30ms | APK: `SF_GetPipelineTx` |
| Feature repeat count | 3 | APK: button command sends |
| Feature repeat delay | 30ms | Integration (`_send_feature_command`) |
| Preset preamble delay | 50ms | APK: AnyKey → preset gap |

The motor values are this bed type's default pulse count and delay, which users
can change in options. Presets, memory saves, light and massage commands are
each sent three times; a preset sends AnyKey three times, waits 50 ms, then
sends the preset three times. Stop is sent once.

## Not Implemented

- **Move-to-position** (`0x5F`): No position feedback available, so absolute positioning cannot work
- **Reset commands** (`0x08`): Too dangerous for accidental activation

## Notes

### Analysis provenance

Protocol reverse-engineered from the SILVERmotion APK (`at.silvermotion`), a
Flutter/Dart application. Key classes from Blutter analysis:

- `SF_GetPipelineTx` - TX pipeline filter chain configuration
- `SF_Controller` - Command method definitions
- `SF_CryptoXXTEA` - XXTEA implementation
- `SF_CRC16` - CRC-CCITT implementation
- `SF_SLIP` - SLIP framing
