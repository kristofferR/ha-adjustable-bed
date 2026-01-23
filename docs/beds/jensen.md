# Jensen

**Status:** Beta (needs user testing)

**Credit:** Protocol reverse-engineered from `com.hilding.jbg_ble` APK

## Known Models
- Jensen JMC400
- Jensen LinON Entry
- Other Jensen beds using the JBG BLE app

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | JBG BLE | `com.hilding.jbg_ble` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ✅ |
| Memory Presets | ✅ (1 slot) |
| Flat Preset | ✅ |
| Massage | ✅ (dynamic) |
| Main Light | ✅ (dynamic) |
| Under-bed Light | ✅ (dynamic) |
| Fan | ❌ (detected but not implemented) |

**Note:** Massage and light features are dynamically detected. Not all Jensen beds have these features - the integration queries the bed's configuration on connection to determine available capabilities.

**Position Feedback:** The integration supports reading head and foot positions via the `READ_POSITION` command. Position values are converted to percentages (0% = flat, 100% = max raised). The calibration constants are based on APK analysis and may need adjustment for some bed variants.

## Protocol Details

**Service UUID:** `00001234-0000-1000-8000-00805f9b34fb`
**Characteristic UUID:** `00001111-0000-1000-8000-00805f9b34fb`
**Format:** 6-byte packets, no checksum
**Pairing Required:** No

## Detection

- Service UUID: `00001234` (unique to Jensen)
- Device name starting with: `jmc400`

## Command Format

All commands are 6 bytes: `[cmd_type, param1, param2, param3, param4, param5]`

Command types:
- `0x0A` - Configuration commands
- `0x10` - Motor/preset commands
- `0x12` - Massage commands
- `0x13` - Light commands

### Motor Commands

| Command | Bytes (hex) |
|---------|-------------|
| Stop | `10 00 00 00 00 00` |
| Head Up | `10 01 00 00 00 00` |
| Head Down | `10 02 00 00 00 00` |
| Foot Up | `10 10 00 00 00 00` |
| Foot Down | `10 20 00 00 00 00` |

### Preset Commands

| Command | Bytes (hex) |
|---------|-------------|
| Flat (Flatten) | `10 81 00 00 00 00` |
| Save Memory | `10 40 00 00 00 00` |
| Recall Memory | `10 80 00 00 00 00` |

### Configuration Commands

| Command | Bytes (hex) |
|---------|-------------|
| Read All Config | `0A 00 00 00 00 00` |
| Read Position | `10 FF 00 00 00 00` |

### Config Response

The bed responds to `CONFIG_READ_ALL` with feature flags in byte 2:

| Bit | Value | Feature |
|-----|-------|---------|
| 0 | 0x01 | Head massage |
| 1 | 0x02 | Foot massage |
| 2 | 0x04 | Main light |
| 4 | 0x10 | Fan |
| 6 | 0x40 | Under-bed light |

Byte 4 contains the box type:
- `4` = LinON Entry
- `2` = Dynamique

### Massage Commands

| Command | Bytes (hex) |
|---------|-------------|
| Massage Off | `12 00 00 00 00 00` |
| Head Massage On | `12 05 00 00 00 00` |
| Foot Massage On | `12 00 05 00 00 00` |
| Both Massage On | `12 05 05 00 00 00` |

### Light Commands

Light commands use format: `[0x13, light_id, brightness, 0x00, 0x00, 0x50]`

| Command | Bytes (hex) |
|---------|-------------|
| Main Light On | `13 00 FF 00 00 50` |
| Main Light Off | `13 00 00 00 00 50` |
| Under-bed Light On | `13 02 FF 00 00 50` |
| Under-bed Light Off | `13 02 00 00 00 50` |

## Command Timing

From APK analysis:
- **Motor Commands:** Repeated while button held (10 repeats, 100ms delay = 1s movement)
- **Stop Required:** Yes, explicit stop command sent after movement
- **Presets:** Longer repeat duration for preset commands (bed moves to target position)

## Position Response Format

When querying position with `10 FF 00 00 00 00`, the bed responds with:
`[0x10, ??, headMSB, headLSB, footMSB, footLSB]`

Position value ranges (from APK analysis):
- **Head:** 1 = flat, ~30500 = max raised
- **Foot:** Values are inverted - 60000 = flat, 1 = max raised

## Limitations

- Only 1 memory slot (some beds may have more)
- Position calibration may vary between bed models - values are estimated from APK analysis
- Fan control not implemented (flag is detected but commands unknown)
