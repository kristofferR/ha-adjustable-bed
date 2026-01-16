# Solace

**Status:** ⚠️ Untested

## Known Models
- Solace hospital/care beds
- Some medical adjustable beds

## Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ❌ |
| Memory Presets | ✅ (5 slots) |
| Lift/Tilt | ✅ |
| Zero-G / Anti-Snore | ✅ |

## Protocol Details

**Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb`
**Format:** 11-byte fixed packets

### Motor Commands

| Command | Bytes (hex) |
|---------|-------------|
| Back Up | `FF FF FF FF 05 00 00 00 03 97 01` |
| Back Down | `FF FF FF FF 05 00 00 00 04 D6 C3` |
| Legs Up | `FF FF FF FF 05 00 00 00 06 57 02` |
| Legs Down | `FF FF FF FF 05 00 00 00 07 96 C2` |
| Lift Up | `FF FF FF FF 05 00 00 00 21 17 18` |
| Lift Down | `FF FF FF FF 05 00 00 00 22 57 19` |
| Tilt Up | `FF FF FF FF 05 00 00 00 28 D7 1E` |
| Tilt Down | `FF FF FF FF 05 00 00 00 29 16 DE` |
| Stop | `FF FF FF FF 05 00 00 00 00 D7 00` |

### Preset Commands

| Command | Bytes (hex) |
|---------|-------------|
| Flat | `FF FF FF FF 05 00 00 00 08 D6 C6` |
| All Flat | `FF FF FF FF 05 00 00 00 2A 56 DF` |
| Zero-G | `FF FF FF FF 05 00 00 00 09 17 06` |
| Anti-Snore | `FF FF FF FF 05 00 00 00 0F 97 04` |
| TV | `FF FF FF FF 05 00 00 00 05 17 03` |

### Memory Commands

| Command | Bytes (hex) |
|---------|-------------|
| Memory 1 | `FF FF FF FF 05 00 00 A1 0A 2E 97` |
| Memory 2 | `FF FF FF FF 05 00 00 B1 0B E2 97` |
| Memory 3 | `FF FF FF FF 05 00 00 51 05 2A 93` |
| Memory 4 | `FF FF FF FF 05 00 00 91 09 7A 96` |
| Memory 5 | `FF FF FF FF 05 00 00 F1 0F D2 94` |
| Save Memory 1 | `FF FF FF FF 05 00 00 A0 0A 2F 07` |
| Save Memory 2 | `FF FF FF FF 05 00 00 B0 0B E3 07` |
| Save Memory 3 | `FF FF FF FF 05 00 00 50 05 2B 03` |
| Save Memory 4 | `FF FF FF FF 05 00 00 90 09 7B 06` |
| Save Memory 5 | `FF FF FF FF 05 00 00 F0 0F D3 04` |
