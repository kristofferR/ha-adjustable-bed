# BedTech

**Status:** ❓ Untested

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- BedTech adjustable bases

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [BedTech](https://play.google.com/store/apps/details?id=com.bedtech) | `com.bedtech` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head, Foot, Leg/Pillow |
| Position Feedback | ❌ |
| Memory Presets | ✅ (2 slots) |
| Massage | ✅ (5 modes, timer) |
| Under-bed Lights | ✅ |
| Zero-G / Anti-Snore / TV / Lounge | ✅ |
| Dual Base Support | ✅ |

## Protocol Details

**Service UUID:** `0000fee9-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `d44bc439-abfd-45a2-b575-925416129600`

> [!NOTE]
> BedTech shares the FEE9 service UUID and characteristic with Richmat WiLinke.
> Both use a similar 5-byte command format with `0x6E` prefix.
> Manual bed type selection may be required if auto-detection selects the wrong type.

### Packet Format

**Single Motor Commands:** `[0x6E, 0x01, 0x00, charCode, (charCode + 0x6F) & 0xFF]`
**Dual Base Commands:** `[0x6E, 0x01, 0x01, charCode, (charCode + 0x70) & 0xFF]`

Commands use ASCII character codes. The last byte is a simple checksum.

## Commands

### Motor Control

| Command | Char | Hex | Description |
|---------|------|-----|-------------|
| Head Up | `$` | `0x24` | Raise head |
| Head Down | `%` | `0x25` | Lower head |
| Foot Up | `&` | `0x26` | Raise foot |
| Foot Down | `'` | `0x27` | Lower foot |
| Leg Up | `)` | `0x29` | Raise leg/pillow |
| Leg Down | `*` | `0x2A` | Lower leg/pillow |

### Sync Commands (Both Sides)

| Command | Char | Hex | Description |
|---------|------|-----|-------------|
| Both Heads Up | `?` | `0x3F` | Raise both heads |
| Both Heads Down | `@` | `0x40` | Lower both heads |
| Both Feet Up | `A` | `0x41` | Raise both feet |
| Both Feet Down | `B` | `0x42` | Lower both feet |

### Presets

| Command | Char | Hex | Description |
|---------|------|-----|-------------|
| Flat | `1` | `0x31` | Flat position |
| Zero-G | `E` | `0x45` | Zero gravity |
| Anti-Snore | `F` | `0x46` | Anti-snore |
| TV | `X` | `0x58` | TV position |
| Lounge | `e` | `0x65` | Lounge position |

### Memory

| Command | Char | Hex | Description |
|---------|------|-----|-------------|
| Memory Go | `/` | `0x2F` | Go to memory position |
| Memory Save | `,` | `0x2C` | Save current position |

### Massage

| Command | Char | Hex | Description |
|---------|------|-----|-------------|
| Massage On | `]` | `0x5D` | Turn massage on |
| Massage Off | `^` | `0x5E` | Turn massage off |
| Massage Switch | `H` | `0x48` | Switch massage mode |
| Head Massage Up | `L` | `0x4C` | Increase head massage |
| Head Massage Down | `M` | `0x4D` | Decrease head massage |
| Foot Massage Up | `N` | `0x4E` | Increase foot massage |
| Foot Massage Down | `O` | `0x4F` | Decrease foot massage |

#### Massage Modes

| Mode | Char | Hex |
|------|------|-----|
| Constant | `:` | `0x3A` |
| Pulse | `8` | `0x38` |
| Wave 1 | `I` | `0x49` |
| Wave 2 | `J` | `0x4A` |
| Wave 3 | `K` | `0x4B` |

#### Massage Timer

| Timer | Char | Hex |
|-------|------|-----|
| 10 min | `_` | `0x5F` |
| 20 min | `c` | `0x63` |
| 30 min | `a` | `0x61` |

### Lights

| Command | Char | Hex | Description |
|---------|------|-----|-------------|
| Light On | `.` | `0x2E` | Turn light on |
| Light Save | `+` | `0x2B` | Save light setting |
| Light Off | `u` | `0x75` | Turn light off |
| Light Toggle | `<` | `0x3C` | Toggle light |

## Dual Base Commands

For dual-base (King/Split King) beds, secondary controls use `_` prefix:
- Head2 Up: `_$`
- Head2 Down: `_%`
- Preset2 Flat: `_1`
- Light2 Toggle: `_<`
- Memory2 Go: `_/`

These use the dual base packet format with `0x01` in byte 2 and `+0x70` checksum.
