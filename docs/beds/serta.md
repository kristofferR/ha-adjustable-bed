# Serta

**Status:** ⚠️ Untested

**Credit:** Reverse engineering by [Richard Hopton/smartbed-mqtt](https://github.com/richardhopton/smartbed-mqtt)

## Known Models
- Serta Motion Perfect III
- Serta adjustable bases (BLE-enabled, non-cloud)

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ❌ | [Serta Sleep](https://play.google.com/store/apps/details?id=com.smarthome.serta) | `com.smarthome.serta` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ❌ |
| Memory Presets | ❌ |
| Massage | ✅ (intensity control) |
| Zero-G / TV / Lounge | ✅ |

## Protocol Details

**Write Handle:** `0x0020`
**Format:** 8-byte packets with `e5fe16` prefix

**Note:** Serta uses handle-based writes rather than characteristic UUIDs.

### Motor Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Head Up | `e5 fe 16 01 00 00 00 05` | Raise head |
| Head Down | `e5 fe 16 02 00 00 00 04` | Lower head |
| Foot Up | `e5 fe 16 04 00 00 00 02` | Raise foot |
| Foot Down | `e5 fe 16 08 00 00 00 fe` | Lower foot |
| Stop | `e5 fe 16 00 00 00 00 06` | Stop all motors |

### Preset Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Flat | `e5 fe 16 00 00 00 08 fe` | Go to flat |
| Zero-G | `e5 fe 16 00 10 00 00 f6` | Go to zero gravity |
| TV | `e5 fe 16 00 40 00 00 c6` | Go to TV position |
| Lounge | `e5 fe 16 00 20 00 00 e6` | Go to lounge |
| Head Up Preset | `e5 fe 16 00 80 00 00 86` | Go to head up preset |

### Massage Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Head Massage + | `e5 fe 16 00 08 00 00 fe` | Increase head massage |
| Head Massage - | `e5 fe 16 00 00 80 00 86` | Decrease head massage |
| Foot Massage + | `e5 fe 16 00 04 00 00 02` | Increase foot massage |
| Foot Massage - | `e5 fe 16 00 00 00 01 05` | Decrease foot massage |
| Head+Foot On | `e5 fe 16 00 01 00 00 05` | Turn on both massage |
| Massage Timer | `e5 fe 16 00 02 00 00 04` | Cycle massage timer |

## Detection

Detected by device name containing: `serta` or `motion perfect`
