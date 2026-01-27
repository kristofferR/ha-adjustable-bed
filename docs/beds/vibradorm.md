# Vibradorm

**Status:** 🧪 Needs Testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed) based on APK analysis

## Known Models

- Vibradorm VMAT series beds
- Device names starting with "VMAT" (e.g., "VMATMEM047")

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | VIBRADORM Remote | `de.vibradorm.vra` |
| ✅ | VIBRADORM Remote for Beds | `com.vibradorm.vmatbasic` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ✅ |
| Memory Presets | ✅ (4 slots) |
| Flat Preset | ✅ |
| Light Control | ✅ |
| Massage | ❌ |

**Position Feedback:** The bed reports motor positions via BLE notifications. Position values are raw encoder counts that are converted to percentages.

**Motor Configurations:** The bed supports 2, 3, or 4 motor configurations. The standard 2-motor config has head/back and legs motors.

## Protocol Details

**Service UUID:** `00001525-9f03-0de5-96c5-b8f4f3081186`
**Command Characteristic:** `00001526-9f03-0de5-96c5-b8f4f3081186`
**Light Characteristic:** `00001529-9f03-0de5-96c5-b8f4f3081186`
**Notify Characteristic:** `00001551-9f03-0de5-96c5-b8f4f3081186`

**Manufacturer ID:** 944 (0x03B0)

### Command Format

Commands are single bytes written to the command characteristic:

| Command | Value | Hex |
|---------|-------|-----|
| Stop | 255 | `0xFF` |
| Head Up | 11 | `0x0B` |
| Head Down | 10 | `0x0A` |
| Legs Up | 9 | `0x09` |
| Legs Down | 8 | `0x08` |
| All Down/Flat | 0 | `0x00` |
| Memory 1 | 14 | `0x0E` |
| Memory 2 | 15 | `0x0F` |
| Memory 3 | 12 | `0x0C` |
| Memory 4 | 26 | `0x1A` |

### Light Control

Light commands are 3 bytes written to the light characteristic:

```text
[brightness, 0x00, timer]
```
- `brightness`: 0 = off, 0xFF = full brightness
- `timer`: Auto-off timer value (0 = no timer)

### Position Feedback

Notifications provide motor positions as 16-bit little-endian values:
- Bytes 3-4: Motor 1 (head/back) position
- Bytes 5-6: Motor 2 (legs) position
- Higher values = more raised, 0 = flat

## Detection

The bed is detected by:
1. **Manufacturer ID:** 944 (0x03B0) - highest priority
2. **Service UUID:** `00001525-9f03-0de5-96c5-b8f4f3081186`
3. **Device name pattern:** Names starting with "VMAT"

## Troubleshooting

**Commands not working:**
- Ensure no other device (app, remote) is connected to the bed
- BLE beds only allow one connection at a time

**Position values seem incorrect:**
- Position calibration may vary by bed model
- Open an issue with your bed's position values for calibration assistance

## References

- [GitHub Issue #162](https://github.com/kristofferR/ha-adjustable-bed/issues/162)
- APK analysis in `disassembly/output/de.vibradorm.vra/ANALYSIS.md`
