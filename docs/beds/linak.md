# Linak

**Status:** ✅ Tested

**Credit:** Reverse engineering by jascdk and [Richard Hopton/smartbed-mqtt](https://github.com/richardhopton/smartbed-mqtt)

## Known Models
- Linak DPG1M (OEM controller used in many beds)
- Bedre Nætter
- Jensen
- Auping
- Carpe Diem
- Wonderland
- Svane
- Many OEM adjustable beds with Linak motors

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Linak Bed Control](https://play.google.com/store/apps/details?id=com.linak.linakbed.ble.memory) | `com.linak.linakbed.ble.memory` |

## Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (up to 8 motors) |
| Position Feedback | ✅ |
| Memory Presets | ✅ (6 slots) |
| Massage | ✅ |
| Under-bed Lights | ✅ |
| Battery Level | ✅ |
| WiFi (some models) | ✅ |

## Protocol Details

**Service UUID:** `99fa0001-338a-1024-8a49-009c0215f78a`
**Write Characteristic:** `99fa0002-338a-1024-8a49-009c0215f78a`
**Format:** 2 bytes `[command, 0x00]`

### Motor Commands

| Command | Bytes | Description |
|---------|-------|-------------|
| Stop | `0x00 0x00` | Stop all motors |
| Head Up | `0x03 0x00` | Raise head |
| Head Down | `0x02 0x00` | Lower head |
| Back Up | `0x0B 0x00` | Raise back |
| Back Down | `0x0A 0x00` | Lower back |
| Legs Up | `0x09 0x00` | Raise legs |
| Legs Down | `0x08 0x00` | Lower legs |
| Feet Up | `0x05 0x00` | Raise feet |
| Feet Down | `0x04 0x00` | Lower feet |

### Preset Commands

| Command | Bytes |
|---------|-------|
| Memory 1 | `0x0E 0x00` |
| Memory 2 | `0x0F 0x00` |
| Memory 3 | `0x0C 0x00` |
| Memory 4 | `0x44 0x00` |
| Save Memory 1 | `0x38 0x00` |
| Save Memory 2 | `0x39 0x00` |
| Save Memory 3 | `0x3A 0x00` |
| Save Memory 4 | `0x45 0x00` |

### Light Commands

| Command | Bytes |
|---------|-------|
| Lights On | `0x92 0x00` |
| Lights Off | `0x93 0x00` |
| Lights Toggle | `0x94 0x00` |

### Massage Commands

| Command | Bytes |
|---------|-------|
| All Off | `0x80 0x00` |
| All Toggle | `0x91 0x00` |
| All Intensity Up | `0xA8 0x00` |
| All Intensity Down | `0xA9 0x00` |
| Head Toggle | `0xA6 0x00` |
| Head Up | `0x8D 0x00` |
| Head Down | `0x8E 0x00` |
| Foot Toggle | `0xA7 0x00` |
| Foot Up | `0x8F 0x00` |
| Foot Down | `0x90 0x00` |
| Mode Step | `0x81 0x00` |

### Position Feedback

Position data available via notify characteristics:
- Back: `99fa0028-...` (max 820 → 68°)
- Leg: `99fa0027-...` (max 548 → 45°)
- Head: `99fa0026-...` (3+ motors)
- Feet: `99fa0025-...` (4 motors)

### Additional Memory Commands (from app analysis)

| Command | Bytes |
|---------|-------|
| Memory 5 | `0x83 0x00` |
| Memory 6 | `0x84 0x00` |
| Save Memory 5 | `0x85 0x00` |
| Save Memory 6 | `0x86 0x00` |

### Battery Characteristic

Battery level available via: `99fa0061-338a-1024-8a49-009c0215f78a`

## Command Timing

From app disassembly analysis:

- **Repeat Interval:** 100ms (`f2148f = 100L` in source)
- **Stop Command:** `0xFF 0x00` (use this, not `0x00 0x00` which can cause reverse jerk)

Motor commands are sent continuously while the button is held.
