# Mattress Firm 900

**Status:** ⚠️ Untested

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed) and [David Delahoz](https://github.com/daviddelahoz) - [BLEAdjustableBase](https://github.com/daviddelahoz/BLEAdjustableBase)

## Known Models
- Mattress Firm 900 Adjustable Base (iFlex)
- iFlex-branded adjustable beds

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Mattress Firm 900 - O](https://play.google.com/store/apps/details?id=com.okin.bedding.rizemf900) | `com.okin.bedding.rizemf900` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (Head, Foot, Lumbar) |
| Position Feedback | ❌ |
| Memory Presets | ❌ (uses built-in presets instead) |
| Massage | ✅ (3 intensity levels) |
| Under-bed Lights | ✅ (cycle mode) |
| Lumbar Control | ✅ |

## Protocol Details

**Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e` (Nordic UART Service)
**Write Characteristic:** `6e400002-b5a3-f393-e0a9-e50e24dcca9e`
**Format:** 7-byte commands: `5A 01 03 10 [XX] [YY] A5`

## Protocol Family

Mattress Firm 900 is part of the [Okin Protocol Family](../SUPPORTED_ACTUATORS.md#okin-protocol-family), though it uses:
- **Nordic UART Service** (not the Okin service UUID)
- **7-byte command format** (similar to Nectar)
- **Initialization sequence** required on first connection

This means it won't be confused with other Okin beds during auto-detection.

**Initialization Required:** Two-step initialization sequence must be sent on first connection.

### Initialization Commands

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Init 1 | `09 05 0A 23 05 00 00` | First initialization command |
| Init 2 | `5A 0B 00 A5` | Second initialization command |

### Motor Commands

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Head Up | `5A 01 03 10 30 00 A5` | Raise head |
| Head Down | `5A 01 03 10 30 01 A5` | Lower head |
| Foot Up | `5A 01 03 10 30 02 A5` | Raise feet |
| Foot Down | `5A 01 03 10 30 03 A5` | Lower feet |
| Lumbar Up | `5A 01 03 10 30 06 A5` | Raise lumbar |
| Lumbar Down | `5A 01 03 10 30 07 A5` | Lower lumbar |

### Preset Commands

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Flat | `5A 01 03 10 30 10 A5` | Go to flat position |
| Zero Gravity | `5A 01 03 10 30 13 A5` | Go to zero-G position |
| Anti-Snore | `5A 01 03 10 30 16 A5` | Go to anti-snore position |
| Lounge | `5A 01 03 10 30 17 A5` | Go to lounge position |
| Incline | `5A 01 03 10 30 18 A5` | Go to incline position |

### Massage Commands

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Massage Level 1 | `5A 01 03 10 30 52 A5` | Set massage to level 1 |
| Massage Level 2 | `5A 01 03 10 30 53 A5` | Set massage to level 2 |
| Massage Level 3 | `5A 01 03 10 30 54 A5` | Set massage to level 3 |
| Massage Stop | `5A 01 03 10 30 6F A5` | Stop massage |
| Massage Intensity Up | `5A 01 03 10 40 60 A5` | Increase intensity |
| Massage Intensity Down | `5A 01 03 10 40 63 A5` | Decrease intensity |

### Light Commands

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Light Cycle | `5A 01 03 10 30 70 A5` | Cycle through light modes |
| Light Off (Hold) | `5A 01 03 10 30 74 A5` | Turn off lights (hold mode) |

## Detection

Detected by device name starting with: `iflex` (case-insensitive)

Or manually configured with bed type: `mattressfirm`

## Command Timing

From app disassembly analysis:

- **Repeat Interval:** 100ms
- **Pattern:** Continuous while button held
- **Stop Required:** Yes, sends stop twice (at 100ms and 200ms) after release

### Alternative Packet Format (from app analysis)

The official app uses a 14-byte format:
```
[0x0C, 0x02, motor_bytes(4), control_bytes(4), reserved(4)]
```

Device detection uses device name prefix: "okin" (case-insensitive).

## Notes

- The Mattress Firm 900 does not support user-programmable memory positions
- Instead, it provides 5 built-in presets: Flat, Zero-G, Anti-Snore, Lounge, and Incline
- Lumbar control is exposed as a separate Cover entity
- Light cycling allows stepping through brightness levels
- Protocol was manually reverse-engineered by David Delahoz in 2020 from the M900 app
