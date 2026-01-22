# Solace

**Status:** ⚠️ Untested

**Credit:** Reverse engineering by Bonopaws and [Richard Hopton/smartbed-mqtt](https://github.com/richardhopton/smartbed-mqtt)

## Known Models
- Solace hospital/care beds
- Sealy adjustable bases
- Woosa Sleep adjustable bases
- Some medical adjustable beds
- QMS-series beds (QMS-IQ, QMS-I06, QMS-I16, QMS-I26, etc.)
- S-series beds (S3-2, S3-3, S3-4, S4-N, S4-Y, S5-Y, S6-Y)
- SealyMF beds

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Motion Bed](https://play.google.com/store/apps/details?id=com.sn.blackdianqi) | `com.sn.blackdianqi` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ❌ |
| Memory Presets | ✅ (5 slots) |
| Lift/Tilt | ✅ |
| Zero-G / Anti-Snore | ✅ |
| Massage | ✅ |
| Lights | ✅ |

## Protocol Details

**Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb`
**Characteristic UUID:** `0000ffe1-0000-1000-8000-00805f9b34fb`
**Format:** 11-byte fixed packets

## Detection

Device names starting with:
- `QMS-` (QMS-IQ, QMS-I06, QMS-I16, QMS-L04, QMS-JQ-D, QMS-NQ, QMS-MQ, QMS-KQ-H, QMS-DFQ, QMS-DQ, etc.)
- `QMS2`, `QMS3`, `QMS4`
- `S3-`, `S4-`, `S5-`, `S6-`
- `SealyMF`

### Motor Commands

| Command | Bytes (hex) |
|---------|-------------|
| Head Up | `FF FF FF FF 05 00 00 00 01 16 C0` |
| Head Down | `FF FF FF FF 05 00 00 00 02 56 C1` |
| Back Up | `FF FF FF FF 05 00 00 00 03 97 01` |
| Back Down | `FF FF FF FF 05 00 00 00 04 D6 C3` |
| Legs Up | `FF FF FF FF 05 00 00 00 06 57 02` |
| Legs Down | `FF FF FF FF 05 00 00 00 07 96 C2` |
| Hip Up | `FF FF FF FF 05 00 00 00 0D 16 C5` |
| Hip Down | `FF FF FF FF 05 00 00 00 0E 56 C4` |
| Lift Up | `FF FF FF FF 05 00 00 00 21 17 18` |
| Lift Down | `FF FF FF FF 05 00 00 00 22 57 19` |
| Tilt Up | `FF FF FF FF 05 00 00 00 28 D7 1E` |
| Tilt Down | `FF FF FF FF 05 00 00 00 29 16 DE` |
| Stop | `FF FF FF FF 05 00 00 00 00 D7 00` |

### Preset Commands

| Command | Bytes (hex) |
|---------|-------------|
| Flat | `FF FF FF FF 05 00 00 00 08 D6 C6` |
| All Flat | `FF FF FF FF 05 00 00 00 2A 56 DF` |
| Zero-G | `FF FF FF FF 05 00 00 00 09 17 06` |
| Anti-Snore | `FF FF FF FF 05 00 00 00 0F 97 04` |
| TV | `FF FF FF FF 05 00 00 00 05 17 03` |
| Yoga | `FF FF FF FF 05 00 00 00 4E 57 34` |

### Memory Commands

| Command | Bytes (hex) |
|---------|-------------|
| Memory 1 | `FF FF FF FF 05 00 00 A1 0A 2E 97` |
| Memory 2 | `FF FF FF FF 05 00 00 B1 0B E2 97` |
| Memory 3 | `FF FF FF FF 05 00 00 51 05 2A 93` |
| Memory 4 | `FF FF FF FF 05 00 00 91 09 7A 96` |
| Memory 5 | `FF FF FF FF 05 00 00 F1 0F D2 94` |
| Save Memory 1 | `FF FF FF FF 05 00 00 A0 0A 2F 07` |
| Save Memory 2 | `FF FF FF FF 05 00 00 B0 0B E3 07` |
| Save Memory 3 | `FF FF FF FF 05 00 00 50 05 2B 03` |
| Save Memory 4 | `FF FF FF FF 05 00 00 90 09 7B 06` |
| Save Memory 5 | `FF FF FF FF 05 00 00 F0 0F D3 04` |
| Delete Memory 1 | `FF FF FF FF 05 00 00 AF 0A 2A F7` |
| Delete Memory 2 | `FF FF FF FF 05 00 00 BF 0B E6 F7` |
| Delete Memory 3 | `FF FF FF FF 05 00 00 5F 05 2E F3` |
| Delete Memory 4 | `FF FF FF FF 05 00 00 9F 09 7E F6` |
| Delete Memory 5 | `FF FF FF FF 05 00 00 FF 0F D6 F4` |

### Massage Commands

| Command | Bytes (hex) |
|---------|-------------|
| Head Massage + | `FF FF FF FF 05 00 00 00 10 D6 CC` |
| Head Massage - | `FF FF FF FF 05 00 00 00 11 17 0C` |
| Foot Massage + | `FF FF FF FF 05 00 00 00 12 57 0D` |
| Foot Massage - | `FF FF FF FF 05 00 00 00 13 96 CD` |
| Frequency + | `FF FF FF FF 05 00 00 00 14 D7 0F` |
| Frequency - | `FF FF FF FF 05 00 00 00 15 16 CF` |
| Timer 10 min | `FF FF FF FF 05 00 00 00 16 56 CE` |
| Timer 20 min | `FF FF FF FF 05 00 00 00 17 97 0E` |
| Timer 30 min | `FF FF FF FF 05 00 00 00 18 D7 0A` |
| Stop Massage | `FF FF FF FF 05 00 00 00 1C D6 C9` |

### Circulation/Loop Modes

| Command | Bytes (hex) |
|---------|-------------|
| Full Body | `FF FF FF FF 05 00 05 00 E4 C7 4A` |
| Head | `FF FF FF FF 05 00 05 00 E3 86 88` |
| Leg | `FF FF FF FF 05 00 05 00 E5 06 8A` |
| Hip | `FF FF FF FF 05 00 05 00 E6 46 8B` |

### Light Commands

| Command | Bytes (hex) |
|---------|-------------|
| Light Level 0 (Off) | `FF FF FF FF 05 00 00 00 23 96 D9` |
| Light Level 1 | `FF FF FF FF 05 00 00 01 23 97 49` |
| Light Level 2 | `FF FF FF FF 05 00 00 02 23 97 B9` |
| Light Level 3 | `FF FF FF FF 05 00 00 03 23 96 29` |
| Light Level 4 | `FF FF FF FF 05 00 00 04 23 94 19` |
| Light Level 5 | `FF FF FF FF 05 00 00 05 23 95 89` |
| Light Level 6 | `FF FF FF FF 05 00 00 06 23 95 79` |
| Light Level 7 | `FF FF FF FF 05 00 00 07 23 94 E9` |
| Light Level 8 | `FF FF FF FF 05 00 00 08 23 91 19` |
| Light Level 9 | `FF FF FF FF 05 00 00 09 23 90 89` |
| Light Level 10 | `FF FF FF FF 05 00 00 0A 23 90 79` |
| Light Timer 10 min | `FF FF FF FF 05 00 00 00 19 16 CA` |
| Light Timer 8 hours | `FF FF FF FF 05 00 00 00 1A 56 CB` |
| Light Timer 10 hours | `FF FF FF FF 05 00 00 00 1B 97 0B` |
| Query Light Status | `FF FF FF FF 05 00 05 FF 23 C7 28` |

## Command Timing

From app disassembly analysis (Motion Bed):

- **Motor Commands:** Single command per button press (controller latches state)
- **Stop Required:** Yes, explicit stop command on button release
- **No continuous sending** - the bed controller maintains motor movement until a stop command is received

Unlike other protocols that send repeated commands while the button is held, Solace/Motion Bed motors are latched - send move command on press, stop command on release.
