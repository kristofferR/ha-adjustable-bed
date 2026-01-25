# Svane

**Status:** Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Svane adjustable beds with "Svane Bed" BLE name (LinonPI controller)
- Note: JMC400 beds (also in Svane app) use the [Jensen protocol](jensen.md)

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Svane Remote](https://play.google.com/store/apps/details?id=com.produktide.svane.svaneremote) | `com.produktide.svane.svaneremote` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (2 motors: head, feet) |
| Position Feedback | ✅ |
| Memory Presets | ✅ (1 slot) |
| Flat Preset | ✅ |
| Svane Position (Zero-G) | ✅ |
| Under-bed Lights | ✅ |
| Massage | ❌ |

## Protocol Details

The LinonPI protocol uses a **multi-service architecture** where each motor has its own BLE service with direction-specific characteristics. This is different from most beds which use a single service with command bytes.

### BLE Services

| Function | Service UUID |
|----------|--------------|
| Head Motor | `0000abcb-0000-1000-8000-00805f9b34fb` |
| Feet Motor | `0000c258-0000-1000-8000-00805f9b34fb` |
| Lights | `0000d07b-0000-1000-8000-00805f9b34fb` |
| DFU | `0000f92a-0000-1000-8000-00805f9b34fb` |

### Characteristics (same UUIDs in each motor service)

| Function | Characteristic UUID |
|----------|---------------------|
| Up | `000001ac-0000-1000-8000-00805f9b34fb` |
| Down | `0000bae9-0000-1000-8000-00805f9b34fb` |
| Position | `0000143d-0000-1000-8000-00805f9b34fb` |
| Memory | `0000fb6e-0000-1000-8000-00805f9b34fb` |

### Light Service Characteristics

| Function | Characteristic UUID |
|----------|---------------------|
| On/Off | `0000a8e0-0000-1000-8000-00805f9b34fb` |
| Increase | `0000b5e9-0000-1000-8000-00805f9b34fb` |
| Decrease | `00003fb2-0000-1000-8000-00805f9b34fb` |
| Intensity | `00006eec-0000-1000-8000-00805f9b34fb` |

### Motor Commands (2-byte)

Commands are written to the direction-specific characteristic within the appropriate service:

| Action | Service | Characteristic | Bytes |
|--------|---------|----------------|-------|
| Head Up | `abcb` | `01ac` (UP) | `[0x01, 0x00]` |
| Head Down | `abcb` | `bae9` (DOWN) | `[0x01, 0x00]` |
| Head Stop | `abcb` | same as move | `[0x00, 0x00]` |
| Feet Up | `c258` | `01ac` (UP) | `[0x01, 0x00]` |
| Feet Down | `c258` | `bae9` (DOWN) | `[0x01, 0x00]` |
| Feet Stop | `c258` | same as move | `[0x00, 0x00]` |

### Preset Commands (written to MEMORY characteristic `fb6e`)

| Command | Bytes | Description |
|---------|-------|-------------|
| Svane Position | `[0x03, 0x00]` | Comfort preset (similar to zero-g) |
| Flatten | `[0x3F, 0x81, 0x00, 0x00, 0x00, 0x00]` | Go to flat position |
| Recall Position | `[0x3F, 0x80, 0x00, 0x00, 0x00, 0x00]` | Go to saved memory position |
| Save Position | `[0x3F, 0x40, 0x00, 0x00, 0x00, 0x00]` | Save current position to memory |
| Read Position | `[0x3F, 0xFF, 0x00, 0x00, 0x00, 0x00]` | Query current position |

### Light Commands (6-byte, written to LIGHT_ON_OFF `a8e0`)

| Command | Bytes | Notes |
|---------|-------|-------|
| Light On | `[0x13, 0x02, 0x50, 0x01, 0x00, 0x50]` | brightness=80 |
| Light Off | `[0x13, 0x02, 0x00, 0x00, 0x00, 0x00]` | |
| Set Intensity | `[0x13, 0x02, brightness, on_flag, 0x00, 0x64]` | brightness 0-255 |

### Position Feedback

Position data available via notify on the POSITION characteristic (`0000143d-...`) in each motor service:
- Head position: Enable notify on `143d` in service `abcb`
- Feet position: Enable notify on `143d` in service `c258`

Position is returned as a raw byte value (0-100), which is scaled to estimated angles:
- Head: 0-60°
- Feet: 0-45°

## Device Detection

Detected by:
- Service UUID: `0000abcb-0000-1000-8000-00805f9b34fb` (head service)
- Device name pattern: `"Svane Bed"` (case-insensitive)

## Command Timing

- **Repeat count:** 10 (default)
- **Repeat delay:** 100ms
- **Stop:** Always sent after movement commands

## Related Protocols

The Svane Remote app also supports:
- **JMC400** devices - Use the [Jensen protocol](jensen.md), detected by "JMC" in device name
- **OKIN-i** devices - Classic Bluetooth (not BLE), not supported by this integration

## Notes

1. The "LinON" name in the protocol appears to be Svane's internal product name for their bed controller. It is NOT related to Linak despite the similar-sounding name.

2. The multi-service architecture means the same characteristic UUID exists in multiple services. The controller must write to the correct service to control the intended motor.

3. Svane is a Norwegian bed manufacturer. Their beds are primarily sold in Scandinavia.
