# Richmat

**Status:** ✅ Tested

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), getrav and [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt)

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
| ✅ | [L&P Adjustable Base](https://play.google.com/store/apps/details?id=com.richmat.lp2) | `com.richmat.lp2` |
| ✅ | [SVEN & SON](https://play.google.com/store/apps/details?id=com.richmat.svenson) | `com.richmat.svenson` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (up to 7 motors) |
| Position Feedback | ❌ |
| Memory Presets | ✅ (1-5 slots, varies by model) |
| Massage | ✅ |
| Under-bed Lights | ✅ (toggle; RGB color picker + timer on select models) |
| Zero-G / Anti-Snore / TV / Lounge | ✅ |
| Yoga / Read Presets | ✅ (some models) |
| Split-King Sync | ✅ (discrete on/off) |

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

All variants use the same command byte values. For WiLinke/Prefix55/PrefixAA, the byte is wrapped in the 5-byte packet format described above.

#### Motor Control

| Command | Byte | Description |
|---------|------|-------------|
| Head Up | `0x24` | Raise head |
| Head Down | `0x25` | Lower head |
| Feet Up | `0x26` | Raise feet |
| Feet Down | `0x27` | Lower feet |
| Pillow Up | `0x3F` | Raise pillow (motor 3) |
| Pillow Down | `0x40` | Lower pillow (motor 3) |
| Lumbar Up | `0x41` | Raise lumbar (motor 4) |
| Lumbar Down | `0x42` | Lower lumbar (motor 4) |
| Motor 5 Up | `0x71` | Raise motor 5 |
| Motor 5 Down | `0x72` | Lower motor 5 |
| Motor 6 Up | `0x73` | Raise motor 6 |
| Motor 6 Down | `0x74` | Lower motor 6 |
| Motor 7 Up | `0xD0` | Raise motor 7 |
| Motor 7 Down | `0xD1` | Lower motor 7 |
| Stop | `0x6E` | Stop all motors |
| Stop (compat) | `0x5E` | WiLinke compatibility stop (used by some remotes, e.g. QRRM) |

Motors 5-7 are only present on select models (e.g., some table/lift actuators).

#### Combined Motor Movements

| Command | Byte | Description |
|---------|------|-------------|
| Head+Feet Up | `0x29` | Raise head and feet together |
| Head+Feet Down | `0x2A` | Lower head and feet together |
| All Up | `0x56` | Raise all motors |
| All Down | `0x57` | Lower all motors |
| Lumbar+Pillow Up | `0x43` | Raise lumbar and pillow together |
| Lumbar+Pillow Down | `0x44` | Lower lumbar and pillow together |
| Lumbar+Pillow Tilt Up | `0x5B` | Tilt lumbar and pillow up |
| Lumbar+Pillow Tilt Down | `0x5C` | Tilt lumbar and pillow down |
| Feet+Lumbar Up | `0x96` | Raise feet and lumbar together |
| Feet+Lumbar Down | `0x97` | Lower feet and lumbar together |
| Head Up + Feet Down | `0x21` | Inverse: head up while feet down |
| Head Down + Feet Up | `0x22` | Inverse: head down while feet up |

#### Presets

| Command | Byte | Description |
|---------|------|-------------|
| Flat | `0x31` | Flat preset |
| Zero-G | `0x45` | Zero-G preset |
| Anti-Snore | `0x46` | Anti-snore preset |
| TV | `0x58` | TV preset |
| Lounge | `0x59` | Lounge preset |
| Yoga | `0xF0` | Yoga preset |
| Read | `0xF2` | Read preset |
| Side Sleeper | `0xBA` | Side sleeper preset |
| Sleep | `0x8E` | Sleep preset |
| Wakeup | `0x93` | Wakeup preset |
| Flat Sleep | `0xF6` | Flat sleep preset |

#### Memory Presets

| Command | Byte | Description |
|---------|------|-------------|
| Memory 1 | `0x2E` | Go to memory 1 |
| Memory 2 | `0x2F` | Go to memory 2 |
| Memory 3 | `0x30` | Go to memory 3 |
| Memory 4 | `0xB2` | Go to memory 4 |
| Memory 5 | `0xF4` | Go to memory 5 |
| Save Memory 1 | `0x2B` | Save current position to memory 1 |
| Save Memory 2 | `0x2C` | Save current position to memory 2 |
| Save Memory 3 | `0x2D` | Save current position to memory 3 |
| Save Memory 4 | `0xB3` | Save current position to memory 4 |
| Save Memory 5 | `0xF5` | Save current position to memory 5 |

#### Save Preset Positions

| Command | Byte | Description |
|---------|------|-------------|
| Save Zero-G | `0x66` | Program zero-g position |
| Save Anti-Snore | `0x69` | Program anti-snore position |
| Save TV | `0x64` | Program TV position |
| Save Lounge | `0x65` | Program lounge position |
| Save Yoga | `0xF1` | Program yoga position |
| Save Side Sleeper | `0xBB` | Program side sleeper position |
| Save Sleep | `0x8F` | Program sleep position |
| Save Wakeup | `0x94` | Program wakeup position |
| Save Flat Sleep | `0xF7` | Program flat sleep position |

#### Preset Resets

| Command | Byte | Description |
|---------|------|-------------|
| Reset Motor | `0xBE` | Reset motor preset to factory |
| Reset TV | `0xCA` | Reset TV preset to factory |
| Reset Snore | `0xCB` | Reset anti-snore preset to factory |
| Reset Zero-G | `0xCC` | Reset zero-G preset to factory |

#### Massage

| Command | Byte | Description |
|---------|------|-------------|
| Massage Toggle | `0x5D` | Toggle all massage on/off |
| Massage Head Step | `0x4C` | Cycle head massage intensity |
| Massage Foot Step | `0x4E` | Cycle foot massage intensity |
| Massage Pattern Step | `0x48` | Cycle massage pattern |

#### Discrete Massage Control

Sets massage to a specific level instead of cycling.

| Command | Byte | Description |
|---------|------|-------------|
| Head Massage Off | `0x98` | Turn off head massage |
| Head Massage 1 | `0x99` | Head massage level 1 |
| Head Massage 2 | `0x9A` | Head massage level 2 |
| Head Massage 3 | `0x9B` | Head massage level 3 |
| Foot Massage Off | `0x9C` | Turn off foot massage |
| Foot Massage 1 | `0x9D` | Foot massage level 1 |
| Foot Massage 2 | `0x9E` | Foot massage level 2 |
| Foot Massage 3 | `0x9F` | Foot massage level 3 |
| Third Motor Inc | `0xE0` | Increment third massage motor |

#### Lights

Most Richmat beds have a simple white under-bed light controlled via toggle. Some models (Casper, certain QRRM/BT6500/I7RM remotes) have RGB light strips with full color control. RGB is available on WiLinke-variant beds when a specific remote code is configured (not "Auto").

**RGB Strip protocol** (Casper, QRRM, BT6500, I7RM with Casper/SleepFunction): Framed packet format with explicit on/off, color, and timer commands. Timer range: 1-30 minutes or "Always On".

**Legacy RGB protocol** (other WiLinke remotes with the lights feature flag): Segment-based packet format. Timer range: 1-5 minutes or "Always On".

RGB-capable beds expose a **Light** entity with a color wheel instead of a simple on/off switch.

| Command | Byte | Description |
|---------|------|-------------|
| Lights Toggle | `0x3C` | Toggle under-bed lights (used when RGB is not available) |
| Lights On | (protocol-specific) | Turn on under-bed lights explicitly |
| Lights Off | (protocol-specific) | Turn off under-bed lights explicitly |
| Set RGB Color | (protocol-specific) | Set light color via R/G/B values |
| Set Timer | (protocol-specific) | Set auto-off timer duration |

#### Sync Mode (Split King)

For split king beds, sync mode causes both sides to move together.

| Command | Byte | Description |
|---------|------|-------------|
| Sync On | `0xBC` | Enable sync mode |
| Sync Off | `0xBD` | Disable sync mode |

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
