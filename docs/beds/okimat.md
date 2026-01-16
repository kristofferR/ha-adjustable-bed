# Okimat/Okin

**Status:** ⚠️ Untested

## Known Models
- Okimat beds
- Lucid L600
- Other beds with Okin motors

## Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ❌ |
| Memory Presets | ✅ (4 slots) |
| Massage | ✅ |
| Lights | ✅ |

## Protocol Details

**Service UUID:** `62741523-52f9-8864-b1ab-3b3a8d65950b`
**Format:** 6 bytes `[0x04, 0x02, ...int_bytes]` (big-endian)

**⚠️ Requires BLE pairing before use!**

Uses same 32-bit command values as Keeson - see [Keeson commands](keeson.md#commands-32-bit-values).
