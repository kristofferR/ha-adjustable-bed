# Richmat

**Status:** ⚠️ Untested

## Known Models
- Richmat HJA5 series
- Saatva
- Lucid L300
- Classic Brands
- Rize / Mantua (some models)
- Some Sven & Son beds

## Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ❌ |
| Memory Presets | ✅ (2 slots) |
| Massage | ✅ |
| Under-bed Lights | ✅ |
| Zero-G / Anti-Snore | ✅ |

## Protocol Variants

### Nordic Variant
**Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
**Format:** Single byte commands

### WiLinke Variant
**Service UUIDs:** `8ebd4f76-...` or `0000fee9-...`
**Format:** 5 bytes `[0x6E, 0x01, 0x00, command, checksum]`
**Checksum:** `(command + 111) & 0xFF`

### Commands (Single Byte)

| Command | Byte | Description |
|---------|------|-------------|
| Head Up | `0x24` | Raise head |
| Head Down | `0x25` | Lower head |
| Feet Up | `0x26` | Raise feet |
| Feet Down | `0x27` | Lower feet |
| Pillow Up | `0x3F` | Raise pillow |
| Pillow Down | `0x40` | Lower pillow |
| Lumbar Up | `0x41` | Raise lumbar |
| Lumbar Down | `0x42` | Lower lumbar |
| Stop | `0x6E` | Stop all |
| Flat | `0x31` | Flat preset |
| Zero-G | `0x45` | Zero-G preset |
| Anti-Snore | `0x46` | Anti-snore preset |
| TV | `0x58` | TV preset |
| Lounge | `0x59` | Lounge preset |
| Memory 1 | `0x2E` | Go to memory 1 |
| Memory 2 | `0x2F` | Go to memory 2 |
| Save Memory 1 | `0x2B` | Save memory 1 |
| Save Memory 2 | `0x2C` | Save memory 2 |
| Save Zero-G | `0x66` | Program zero-g position |
| Save Anti-Snore | `0x69` | Program anti-snore position |
| Save TV | `0x64` | Program TV position |
| Save Lounge | `0x65` | Program lounge position |
| Lights Toggle | `0x3C` | Toggle lights |
| Massage Toggle | `0x5D` | Toggle massage |
| Massage Head Step | `0x4C` | Cycle head massage |
| Massage Foot Step | `0x4E` | Cycle foot massage |
| Massage Pattern Step | `0x48` | Cycle massage pattern |
