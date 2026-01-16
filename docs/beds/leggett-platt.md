# Leggett & Platt

**Status:** ⚠️ Untested

## Known Models
- Leggett & Platt Prodigy 2.0 / S-Cape 2.0
- Some Tempur-Pedic bases (non-Ergo)
- Fashion Bed Group bases

## Features

| Feature | Gen2 | Okin |
|---------|------|------|
| Motor Control | Preset-based | ✅ |
| Position Feedback | ❌ | ❌ |
| Memory Presets | ✅ (4 slots) | ✅ (4 slots) |
| Massage | ✅ (0-10 levels) | ✅ |
| RGB Lighting | ✅ | ❌ |
| Anti-Snore | ✅ | ❌ |

## Detection

Leggett & Platt beds have two protocol variants with different detection methods:

### Gen2 Variant
- **Service UUID:** `45e25100-...` (unique to Gen2)
- Detection: Automatic by service UUID

### Okin Variant
- **Service UUID:** `62741523-...` (shared with Okimat and Nectar)
- Detection: By device name patterns ("leggett", "l&p", "adjustable base")

**If your Okin bed is misidentified as Okimat:** Change the bed type in integration settings and select the Okin variant.

See also: [Okin Protocol Family](../SUPPORTED_ACTUATORS.md#okin-protocol-family)

## Gen2 Variant (ASCII Commands)

**Service UUID:** `45e25100-3171-4cfc-ae89-1d83cf8d8071`
**Format:** ASCII text (UTF-8)

### Preset Commands

| Command | Text |
|---------|------|
| Flat | `MEM 0` |
| Unwind (Memory 1) | `MEM 1` |
| Sleep (Memory 2) | `MEM 2` |
| Wake Up (Memory 3) | `MEM 3` |
| Relax (Memory 4) | `MEM 4` |
| Anti-Snore | `SNR` |
| Stop | `STOP` |

### Save Commands

| Command | Text |
|---------|------|
| Save Unwind | `SMEM 1` |
| Save Sleep | `SMEM 2` |
| Save Wake Up | `SMEM 3` |
| Save Relax | `SMEM 4` |
| Save Anti-Snore | `SNPOS 0` |

### Massage Commands

| Command | Text |
|---------|------|
| Head Massage (0-10) | `MVI 0:{level}` |
| Foot Massage (0-10) | `MVI 1:{level}` |
| Wave On | `MMODE 0:0` |
| Wave Off | `MMODE 0:2` |
| Wave Level | `WSP 0:{level}` |

### Light Commands

| Command | Text |
|---------|------|
| Get State | `GET STATE` |
| RGB Off | `RGBENABLE 0:0` |
| RGB Set | `RGBSET 0:{RRGGBBBB}` |

## Okin Variant (Binary)

**Service UUID:** `62741523-52f9-8864-b1ab-3b3a8d65950b`
**Format:** 6 bytes `[0x04, 0x02, ...int_bytes]` (big-endian)
**Note:** Requires BLE pairing

Uses same 32-bit command values as Keeson - see [Keeson commands](keeson.md#commands-32-bit-values).
