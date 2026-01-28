# Remacro Protocol

**Bed Type:** `remacro`
**Status:** Needs testing
**Detection:** Unique service UUID (auto-detected)

## Overview

The Remacro protocol is used by multiple furniture store brands that share the same OEM controller:
- CheersSleep
- Jeromes (com.cheers.jewmes)
- Slumberland (com.cheers.slumber)
- The Brick (com.cheers.brick)

The beds use the SynData protocol with 8-byte command packets. Features include:
- 4 motors: head, foot, lumbar, tilt/neck
- 4 memory presets (user programmable)
- 4 default presets: flat, zero-g, TV, anti-snore
- Multiple massage modes and zones
- RGB LED under-bed lighting
- Heat control (model dependent)

## Bluetooth Details

| Property | Value |
|----------|-------|
| Service UUID | `6e403587-b5a3-f393-e0a9-e50e24dcca9e` |
| Write Characteristic | `6e403588-b5a3-f393-e0a9-e50e24dcca9e` |
| Read Characteristic | `6e403589-b5a3-f393-e0a9-e50e24dcca9e` |

Note: The service UUID is similar to Nordic UART Service (6e400001-...) but with a different prefix (6e4035xx vs 6e4000xx), making it uniquely identifiable.

## Packet Format

All commands are 8 bytes:

```
[serial, PID, cmd_lo, cmd_hi, param0, param1, param2, param3]
```

Where:
- `serial` = Incrementing sequence number (1-255, wraps around)
- `PID` = Command type (0x01 for control commands)
- `cmd_lo/cmd_hi` = 16-bit command code in little-endian order
- `param0-3` = 32-bit parameter in little-endian order (usually 0)

### PID Types

| PID | Value | Description |
|-----|-------|-------------|
| CPID_CTRL | 0x01 | Control commands |
| CPID_GET_STATE | 0x02 | Get state |
| CPID_SET_PARA | 0x03 | Set parameters |
| CPID_GET_PARA | 0x04 | Get parameters |

## Commands

### Motor Control

| Action | Command | Value | Notes |
|--------|---------|-------|-------|
| Stop All | STOP | 0x0000 | Stop everything |
| Stop Motors | STOP_MOTOR | 0x0001 | Stop all motors |
| Motor 1 Stop | M1_STOP | 0x0100 (256) | Head |
| Motor 1 Up | M1_UP | 0x0101 (257) | Head |
| Motor 1 Down | M1_DOWN | 0x0102 (258) | Head |
| Motor 2 Stop | M2_STOP | 0x0104 (260) | Foot |
| Motor 2 Up | M2_UP | 0x0105 (261) | Foot |
| Motor 2 Down | M2_DOWN | 0x0106 (262) | Foot |
| Motor 3 Stop | M3_STOP | 0x0108 (264) | Lumbar |
| Motor 3 Up | M3_UP | 0x0109 (265) | Lumbar |
| Motor 3 Down | M3_DOWN | 0x010A (266) | Lumbar |
| Motor 4 Stop | M4_STOP | 0x010C (268) | Tilt/Neck |
| Motor 4 Up | M4_UP | 0x010D (269) | Tilt/Neck |
| Motor 4 Down | M4_DOWN | 0x010E (270) | Tilt/Neck |
| All Up | M_UP | 0x0110 (272) | All motors |
| All Down | M_DOWN | 0x0111 (273) | All motors |

### Presets - User Memory

| Action | Command | Value | Notes |
|--------|---------|-------|-------|
| Go to Memory 1 | MOV_ML1 | 0x0311 (785) | Recall |
| Go to Memory 2 | MOV_ML2 | 0x0313 (787) | Recall |
| Go to Memory 3 | MOV_ML3 | 0x0315 (789) | Recall |
| Go to Memory 4 | MOV_ML4 | 0x0317 (791) | Recall |
| Save Memory 1 | SET_ML1 | 0x0310 (784) | Program |
| Save Memory 2 | SET_ML2 | 0x0312 (786) | Program |
| Save Memory 3 | SET_ML3 | 0x0314 (788) | Program |
| Save Memory 4 | SET_ML4 | 0x0316 (790) | Program |

### Presets - Factory Defaults

| Action | Command | Value | Notes |
|--------|---------|-------|-------|
| Flat | DEF_ML1 | 0x0301 (769) | Factory preset |
| Zero-G | DEF_ML2 | 0x0302 (770) | Factory preset |
| TV | DEF_ML3 | 0x0303 (771) | Factory preset |
| Anti-Snore | DEF_ML4 | 0x0304 (772) | Factory preset |

### Massage Control

| Action | Command | Value | Notes |
|--------|---------|-------|-------|
| Stop Massage | MMODE_STOP | 0x0200 (512) | |
| Mode 1 | MMODE1_RUN | 0x0201 (513) | |
| Mode 2 | MMODE2_RUN | 0x0202 (514) | |
| Mode 3 | MMODE3_RUN | 0x0203 (515) | |
| Zone 1 | MM1_RUN | 0x0121 (289) | Head zone |
| Zone 2 | MM2_RUN | 0x0122 (290) | Foot zone |
| Both Zones | MM12_RUN | 0x0120 (288) | |

### LED Control

| Action | Command | Value | Notes |
|--------|---------|-------|-------|
| Off | LED_OFF | 0x0500 (1280) | |
| RGB Value | LED_RGBV | 0x0501 (1281) | With param |
| White | LED_W | 0x0502 (1282) | |
| Red | LED_R | 0x0503 (1283) | |
| Green | LED_G | 0x0504 (1284) | |
| Blue | LED_B | 0x0505 (1285) | |
| Mode 1 | LED_M1 | 0x0509 (1289) | Pattern |
| Mode 2 | LED_M2 | 0x050A (1290) | Pattern |
| Mode 3 | LED_M3 | 0x050B (1291) | Pattern |

### Heat Control

| Action | Command | Value | Notes |
|--------|---------|-------|-------|
| Off | HEAT_OFF | 0x7000 (28672) | |
| Mode 1 | HEAT_M1 | 0x7001 (28673) | Low |
| Mode 2 | HEAT_M2 | 0x7002 (28674) | Medium |
| Mode 3 | HEAT_M3 | 0x7003 (28675) | High |

## Command Timing

| Operation | Repeat Count | Delay | Notes |
|-----------|-------------|-------|-------|
| Motor movement | 10 | 100ms | Continuous while held |
| Presets | 1 | - | Single command |
| Massage toggle | 1 | - | Single command |
| Light toggle | 1 | - | Single command |
| Stop | 1 | - | Always sent after movement |

## Brands

Beds known to use this protocol:
- CheersSleep beds
- Jeromes furniture store beds
- Slumberland furniture store beds
- The Brick furniture store beds

## Apps

| App | Package |
|-----|---------|
| Jeromes | `com.cheers.jewmes` |
| Slumberland | `com.cheers.slumber` |
| The Brick | `com.cheers.brick` |

## Detection

Devices are detected by the unique service UUID:
- `6e403587-b5a3-f393-e0a9-e50e24dcca9e`

The app also uses manufacturer data to identify specific device models (keys 45-53), but this is not required for basic operation.

## Notes

1. The serial number in byte 0 is important - it should increment with each command. The bed uses this for command deduplication.

2. Motor movement commands should be sent repeatedly while the button is held, similar to other bed protocols.

3. The app has extensive device model support via manufacturer data lookup, but all models use the same BLE protocol.

4. Sleep tracking functionality (heart rate, breath rate) uses different PID types (-121, -120) in notification responses.
