# Richmat

**Status:** ⚠️ Untested

**Credit:** Reverse engineering by getrav and [Richard Hopton/smartbed-mqtt](https://github.com/richardhopton/smartbed-mqtt)

## Known Models

Brands using Richmat actuators:

- L&P Adjustable Base (Leggett & Platt)
- SVEN & SON
- Casper Base
- Galaxy (e.g., Galaxy 26W-N)
- MLILY
- Luuna / Luuna Rise
- Bed Tech
- Jerome's
- Revive
- Idealbed
- Maxprime
- Milemont
- Hush Base
- FLEXX MOTION
- Likimio
- Lunio Smart+
- Good Vibe Sleep
- Best Mattress Power Base
- Easy Rest
- Coaster Sleep
- Avocado Eco Base
- ENSO Sleep
- Dynasty DM9000
- Thomas Cole Sleep
- Forty Winks ActivFlex
- Richmat HJA5 series
- Saatva
- Lucid L300
- Classic Brands

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [RMControl](https://play.google.com/store/apps/details?id=com.richmat.rmcontrol2) | `com.richmat.rmcontrol2` |
| ✅ | [BedTech](https://play.google.com/store/apps/details?id=com.bedtech) | `com.bedtech` |
| ✅ | [SleepFunction Bed Control](https://play.google.com/store/apps/details?id=com.richmat.sleepfunction) | `com.richmat.sleepfunction` |
| ⬜ | [L&P Adjustable Base](https://play.google.com/store/apps/details?id=com.richmat.lp2) | `com.richmat.lp2` |
| ✅ | [SVEN & SON](https://play.google.com/store/apps/details?id=com.richmat.svenson) | `com.richmat.svenson` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (up to 7 motors) |
| Position Feedback | ❌ |
| Memory Presets | ✅ (3 slots) |
| Massage | ✅ |
| Under-bed Lights | ✅ |
| Zero-G / Anti-Snore / TV / Lounge | ✅ |
| Yoga / Read Presets | ✅ (some models) |

## Protocol Variants

### Nordic Variant
**Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
**Format:** Single byte commands

### WiLinke Variant (Most Common)
**Service UUIDs:** `8ebd4f76-...` or `0000fee9-...`
**Format:** 5 bytes `[0x6E, 0x01, 0x00, command, checksum]`
**Checksum:** `(command + 111) & 0xFF`

### Prefix55 Variant
**Format:** 5 bytes `[0x55, 0x01, 0x00, command, checksum]`
**Checksum:** `(command + 0x56) & 0xFF`

### PrefixAA Variant
**Format:** 5 bytes `[0xAA, 0x01, 0x00, command, checksum]`
**Checksum:** `(command + 0xAB) & 0xFF`

### Commands (Single Byte)

| Command | Byte | Description |
|---------|------|-------------|
| Head Up | `0x24` | Raise head |
| Head Down | `0x25` | Lower head |
| Feet Up | `0x26` | Raise feet |
| Feet Down | `0x27` | Lower feet |
| Pillow Up | `0x3F` | Raise pillow |
| Pillow Down | `0x40` | Lower pillow |
| Lumbar Up | `0x41` | Raise lumbar |
| Lumbar Down | `0x42` | Lower lumbar |
| Stop | `0x6E` | Stop all |
| Flat | `0x31` | Flat preset |
| Zero-G | `0x45` | Zero-G preset |
| Anti-Snore | `0x46` | Anti-snore preset |
| TV | `0x58` | TV preset |
| Lounge | `0x59` | Lounge preset |
| Memory 1 | `0x2E` | Go to memory 1 |
| Memory 2 | `0x2F` | Go to memory 2 |
| Save Memory 1 | `0x2B` | Save memory 1 |
| Save Memory 2 | `0x2C` | Save memory 2 |
| Save Zero-G | `0x66` | Program zero-g position |
| Save Anti-Snore | `0x69` | Program anti-snore position |
| Save TV | `0x64` | Program TV position |
| Save Lounge | `0x65` | Program lounge position |
| Lights Toggle | `0x3C` | Toggle lights |
| Massage Toggle | `0x5D` | Toggle massage |
| Massage Head Step | `0x4C` | Cycle head massage |
| Massage Foot Step | `0x4E` | Cycle foot massage |
| Massage Pattern Step | `0x48` | Cycle massage pattern |
| Yoga | `0xF0` | Yoga preset |
| Read | `0xF2` | Read preset |
| Memory 3 | `0x30` | Go to memory 3 |
| Save Memory 3 | `0x2D` | Save memory 3 |

## Command Timing

From app disassembly analysis (SleepFunction):

| Device Name Prefix | Interval | Notes |
|-------------------|----------|-------|
| `6BRM` (Nordic) | 170ms | Nordic vendor |
| `TWRM`, `MLRM` | 110ms | Faster repeat |
| Default | **150ms** | Most devices |

Motor commands are sent continuously while the button is held. A stop byte (`0x6E`) is sent on release.

## Service Detection Order

The app tries BLE services in this order:

1. **WiLinke 1**: `0000FEE9-0000-1000-8000-00805F9B34FB`
2. **WiLinke 2**: `0000FEE9-0000-1000-8000-00805F9B34BB`
3. **Nordic UART**: `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
4. **FFF0**: `0000FFF0-0000-1000-8000-00805F9B34FB`
5. **FFE0**: `0000FFE0-0000-1000-8000-00805F9B34FB`

## Device Detection

| Device Name Prefix | Features |
|-------------------|----------|
| `WFRM`, `FWRM` | Table/Lift with height control |
| `6BRM` | Nordic variant (170ms timing) |
| `TWRM`, `MLRM` | Fast timing (110ms) |
| `YGRM`, `BRRM` | Extended presets |
