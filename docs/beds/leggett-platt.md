# Leggett & Platt

**Status:** ❓ Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), MarcusW, [Josh Pearce](https://github.com/joshpearce), and [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt)

## Known Models
- Leggett & Platt Prodigy 2.0 / S-Cape 2.0
- Leggett & Platt beds with "MlRM" Bluetooth name prefix
- Some Tempur-Pedic bases (non-Ergo)
- Fashion Bed Group bases

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [L&P Adjustable Base](https://play.google.com/store/apps/details?id=com.richmat.lp2) | `com.richmat.lp2` |

## Features

| Feature | Gen2 | Okin | MlRM |
|---------|------|------|------|
| Motor Control | ✅ (head, feet, pillow, lumbar) | ✅ (head, feet, tilt, lumbar) | ✅ (discrete) |
| Position Feedback | ❌ | ❌ | ❌ |
| Memory Presets | ✅ (4 slots) | ✅ (4 slots) | ✅ (2 slots) |
| Massage | ✅ (0-10 levels) | ✅ (wave, timer) | ✅ (discrete UP/DOWN) |
| Lighting | ✅ RGB | ✅ Toggle | ✅ Toggle |
| Anti-Snore | ✅ | ❌ | ✅ |
| Zero-G | ❌ | ✅ | ✅ |
| TV Preset | ❌ | ❌ | ✅ |
| Lounge Preset | ❌ | ❌ | ✅ |

## Detection

Leggett & Platt beds have three protocol variants with different detection methods:

### Gen2 Variant
- **Service UUID:** `45e25100-...` (unique to Gen2)
- Detection: Automatic by service UUID

### Okin Variant
- **Service UUID:** `62741523-...` (shared with Okimat and Nectar)
- Detection: By device name patterns ("leggett", "l&p", "adjustable base")

### MlRM Variant
- **Service UUID:** WiLinke service (`f0010001-...` or `fee9`)
- **Device Name:** Starts with "MlRM"
- Detection: Automatic by device name prefix + WiLinke service UUID

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

### Motor Commands

Format: `M {up}:{down}:{stop}` where each field is a comma-separated list of motor numbers.

Motor numbers: 0=head, 1=feet, 2=pillow, 3=lumbar

| Command | Text | Description |
|---------|------|-------------|
| Head Up | `M 0::123` | Head up, stop feet/pillow/lumbar |
| Head Down | `M :0:123` | Head down, stop feet/pillow/lumbar |
| Feet Up | `M 1::023` | Feet up, stop head/pillow/lumbar |
| Feet Down | `M :1:023` | Feet down, stop head/pillow/lumbar |
| Pillow Up | `M 2::013` | Pillow up, stop head/feet/lumbar |
| Pillow Down | `M :2:013` | Pillow down, stop head/feet/lumbar |
| Lumbar Up | `M 3::012` | Lumbar up, stop head/feet/pillow |
| Lumbar Down | `M :3:012` | Lumbar down, stop head/feet/pillow |
| Stop All | `M ::0123` | Stop all motors |

### Massage Commands

| Command | Text |
|---------|------|
| Head Massage (0-10) | `MVI 0:{level}` |
| Foot Massage (0-10) | `MVI 1:{level}` |
| Wave On | `MMODE 0:0` |
| Wave Off | `MMODE 0:2` |
| Wave Level | `WSP 0:{level}` |

### Light Commands

Gen2 beds with RGB lighting expose a **Light** entity with a color picker instead of a simple on/off switch. The default color is white (255, 255, 255).

| Command | Text | Description |
|---------|------|-------------|
| Get State | `GET STATE` | Query current bed state |
| RGB Off | `RGBENABLE 0:0` | Turn off RGB lights |
| RGB Set | `RGBSET 0:{RRGGBBBB}` | Set RGB color + brightness (hex RRGGBBBB, brightness fixed at FF) |

## Okin Variant (Binary)

**Service UUID:** `62741523-52f9-8864-b1ab-3b3a8d65950b`
**Format:** 6 bytes `[0x04, 0x02, ...int_bytes]` (big-endian)
**Note:** Requires BLE pairing

Uses same 32-bit command values as Keeson - see [Keeson commands](keeson.md#commands-32-bit-values).

### Motor Commands

| Command | 32-bit Value | Description |
|---------|-------------|-------------|
| Head Up | `0x00000001` | Raise head |
| Head Down | `0x00000002` | Lower head |
| Feet Up | `0x00000004` | Raise feet |
| Feet Down | `0x00000008` | Lower feet |
| Tilt Up | `0x00000010` | Raise tilt (pillow) |
| Tilt Down | `0x00000020` | Lower tilt (pillow) |
| Lumbar Up | `0x00000040` | Raise lumbar |
| Lumbar Down | `0x00000080` | Lower lumbar |
| Stop | `0x00000000` | Stop all motors |

Multiple motors can be moved simultaneously by OR-ing their command values together.

### Massage Commands

| Command | 32-bit Value | Description |
|---------|-------------|-------------|
| Head Massage Up | `0x00000800` | Increase head massage intensity |
| Head Massage Down | `0x00800000` | Decrease head massage intensity |
| Foot Massage Up | `0x00000400` | Increase foot massage intensity |
| Foot Massage Down | `0x01000000` | Decrease foot massage intensity |
| Massage Step | `0x00000100` | Cycle through massage modes |
| Massage Timer Step | `0x00000200` | Cycle through massage timer options |
| Massage Wave Step | `0x10000000` | Cycle through massage wave patterns |

## MlRM Variant (WiLinke)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), [Josh Pearce](https://github.com/joshpearce)

**Characteristic UUID:** `d44bc439-abfd-45a2-b575-925416129600`
**Format:** 5 bytes `[0x6E, 0x01, 0x00, command, checksum]`
**Checksum:** Sum of first 4 bytes, truncated to 8 bits

This variant uses Richmat WiLinke BLE hardware but with Leggett & Platt-specific commands. A key differentiator from standard Richmat WiLinke is discrete massage UP/DOWN commands instead of cycling step commands.

### Preset Commands

| Command | Byte | Description |
|---------|------|-------------|
| Flat | `0x31` | Flat position |
| Zero-G | `0x45` | Zero gravity |
| Anti-Snore | `0x46` | Anti-snore position |
| TV | `0x58` | TV viewing position |
| Lounge | `0x59` | Lounge position |
| Memory 1 | `0x2E` | Recall memory slot 1 |
| Memory 2 | `0x2F` | Recall memory slot 2 |

### Program Commands

| Command | Byte | Description |
|---------|------|-------------|
| Program Memory 1 | `0x2B` | Save current position to slot 1 |
| Program Memory 2 | `0x2C` | Save current position to slot 2 |
| Program Zero-G | `0x66` | Save as zero-g position |
| Program Anti-Snore | `0x69` | Save as anti-snore position |
| Program TV | `0x64` | Save as TV position |
| Program Lounge | `0x65` | Save as lounge position |

### Motor Commands

| Command | Byte | Description |
|---------|------|-------------|
| Head Up | `0x24` | Raise head |
| Head Down | `0x25` | Lower head |
| Feet Up | `0x26` | Raise feet |
| Feet Down | `0x27` | Lower feet |
| End/Stop | `0x6E` | Stop all movement |

### Massage Commands

| Command | Byte | Description |
|---------|------|-------------|
| Head Massage Up | `0x4C` | Increase head massage |
| Head Massage Down | `0x4D` | Decrease head massage |
| Foot Massage Up | `0x4E` | Increase foot massage |
| Foot Massage Down | `0x4F` | Decrease foot massage |
| Stop Massage | `0x47` | Stop all massage |
| Head Toggle | `0x32` | Toggle head massage |
| Foot Toggle | `0x33` | Toggle foot massage |
| Intensity Up | `0x34` | Overall intensity up |
| Intensity Down | `0x35` | Overall intensity down |
| Pattern Step | `0x38` | Cycle massage patterns |
| Wave Mode | `0x39` | Toggle wave mode |

### Light Commands

| Command | Byte | Description |
|---------|------|-------------|
| Lights Toggle | `0x3C` | Toggle under-bed lights |
