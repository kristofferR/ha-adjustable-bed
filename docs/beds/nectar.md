# Nectar

**Status:** ❓ Untested

**Credit:** Reverse engineering by [MaximumWorf](https://github.com/MaximumWorf) - [homeassistant-nectar](https://github.com/MaximumWorf/homeassistant-nectar)

## Known Models

- Nectar Split King Luxe Adjustable Foundation
- Nectar adjustable bases
- Other beds using Okin controllers with 7-byte command format

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ⬜ | Nectar Adjustable | (no longer available) |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (Head, Feet, Lumbar) |
| Position Feedback | ❌ |
| Memory Presets | ❌ |
| Massage | ✅ |
| Under-bed Lights | ✅ |
| Zero-G / Anti-Snore / Lounge | ✅ |

## Protocol Details

**Service UUID:** `62741523-52f9-8864-b1ab-3b3a8d65950b` (OKIN Primary Service)
**Write Characteristic:** `62741525-52f9-8864-b1ab-3b3a8d65950b`
**Format:** 7-byte commands: `5A 01 03 10 30 [XX] A5`

**Note:** Nectar beds share the Okin service UUID with Okimat but use a **7-byte command format** (vs Okimat's 6-byte format). This means commands are not interchangeable - if your bed is detected as the wrong type, change it in integration settings.

### Motor Commands

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Head Up | `5A 01 03 10 30 00 A5` | Raise head |
| Head Down | `5A 01 03 10 30 01 A5` | Lower head |
| Foot Up | `5A 01 03 10 30 02 A5` | Raise feet |
| Foot Down | `5A 01 03 10 30 03 A5` | Lower feet |
| Lumbar Up | `5A 01 03 10 30 04 A5` | Raise lumbar |
| Lumbar Down | `5A 01 03 10 30 07 A5` | Lower lumbar |
| Stop | `5A 01 03 10 30 0F A5` | Stop all motors |

### Preset Commands

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Flat | `5A 01 03 10 30 10 A5` | Go to flat position |
| Lounge | `5A 01 03 10 30 11 A5` | Go to lounge position |
| Zero Gravity | `5A 01 03 10 30 13 A5` | Go to zero-G position |
| Anti-Snore | `5A 01 03 10 30 16 A5` | Go to anti-snore position |

### Massage Commands

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Massage On | `5A 01 03 10 30 58 A5` | Turn on massage |
| Massage Wave | `5A 01 03 10 30 59 A5` | Switch to wave pattern |
| Massage Off | `5A 01 03 10 30 5A A5` | Turn off massage |

### Light Commands

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Light On | `5A 01 03 10 30 73 A5` | Turn on under-bed lights |
| Light Off | `5A 01 03 10 30 74 A5` | Turn off under-bed lights |

## Detection

Detected by device name containing: `nectar` (case-insensitive) AND Okin service UUID present

Or manually configured with bed type: `nectar`

## Protocol Family

Nectar is part of the [Okin Protocol Family](../SUPPORTED_ACTUATORS.md#okin-protocol-family). Key differences from other Okin beds:

- Uses **7-byte** command format (similar to Mattress Firm 900)
- Does **not** require Bluetooth pairing
- No position feedback support

## Notes

- Nectar beds share the Okin service UUID with Okimat beds but use a different command protocol
- Detection requires both the "nectar" device name AND the Okin service UUID to avoid false positives
- Massage control is global (no separate head/foot control)
- Lights have separate on/off commands (no toggle)
