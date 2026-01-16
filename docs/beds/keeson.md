# Keeson

**Status:** ✅ Tested

## Known Models
- Purple adjustable bases
- GhostBed
- Member's Mark (Sam's Club) adjustable beds
- South Bay International MMKD
- Ergomotion beds
- Tempur-Pedic (some newer models)
- Sealy Ease
- Serta (some models)
- Beautyrest (some models)
- Some Costco beds

## Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ✅ (Ergomotion variant only) |
| Memory Presets | ✅ (4 slots) |
| Massage | ✅ |
| Safety Lights | ✅ |
| Zero-G | ✅ |

## Protocol Variants

### Base Variant (BaseI4/BaseI5) - Most Common
**Primary Service UUID:** `0000ffe5-0000-1000-8000-00805f9b34fb`
**Format:** 8 bytes `[0xE5, 0xFE, 0x16, b4, b5, b6, b7, checksum]`
**Checksum:** `sum(bytes) XOR 0xFF`

**Fallback Service UUIDs:** Some Keeson beds use different service UUIDs. The integration automatically tries these if the primary isn't found:
- `0000fff0-0000-1000-8000-00805f9b34fb` (characteristic: `0000fff2`)
- `0000ffb0-0000-1000-8000-00805f9b34fb` (characteristic: `0000ffb2`)

### KSBT Variant (Older Remotes)
**Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
**Format:** 6 bytes `[0x04, 0x02, ...int_bytes]` (big-endian)

### Ergomotion Variant (with Position Feedback)
Same protocol as Base variant but with real-time position updates via BLE notifications.

**Notify Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb`

Position data formats (by header byte):
| Header | Length | Description |
|--------|--------|-------------|
| `0xED` | 16 bytes | Basic position data |
| `0xF0` | 19 bytes | Extended position data |
| `0xF1` | 20 bytes | Full status data |

Position data includes:
- Head position (16-bit, 0-100 scale)
- Foot position (16-bit, 0-100 scale)
- Movement status flags
- Massage levels (0-6)
- LED status

### Commands (32-bit Values)

| Command | Value | Description |
|---------|-------|-------------|
| Stop | `0x00000000` | Stop all |
| Head Up | `0x00000001` | Raise head |
| Head Down | `0x00000002` | Lower head |
| Feet Up | `0x00000004` | Raise feet |
| Feet Down | `0x00000008` | Lower feet |
| Tilt Up | `0x00000010` | Raise tilt |
| Tilt Down | `0x00000020` | Lower tilt |
| Lumbar Up | `0x00000040` | Raise lumbar |
| Lumbar Down | `0x00000080` | Lower lumbar |
| Massage Step | `0x00000100` | Cycle massage mode |
| Massage Timer | `0x00000200` | Cycle massage timer |
| Massage Foot Up | `0x00000400` | Increase foot massage |
| Massage Head Up | `0x00000800` | Increase head massage |
| Zero-G | `0x00001000` | Zero-G preset |
| Memory 1 | `0x00002000` | Go to memory 1 |
| Memory 2 | `0x00004000` | Go to memory 2 |
| Memory 3 | `0x00008000` | Go to memory 3 |
| Memory 4 | `0x00010000` | Go to memory 4 |
| Toggle Lights | `0x00020000` | Toggle safety lights |
| Massage Head Down | `0x00800000` | Decrease head massage |
| Massage Foot Down | `0x01000000` | Decrease foot massage |
| Flat | `0x08000000` | Flat preset |
| Massage Wave | `0x10000000` | Cycle wave massage |
