# Jiecang

**Status:** ❓ Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt)

## Known Models

Brands using Jiecang actuators:

- Comfort Motion
- Dream Motion / Dreamotion Smart
- ERGOBALANCE
- Glide adjustable beds
- LOGICDATA MOTIONrelax
- Jiecang-branded controllers

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Jiecang Bed / Comfort Motion](https://play.google.com/store/apps/details?id=com.jiecang.app.android.jiecangbed) | `com.jiecang.app.android.jiecangbed` |
| ✅ | LOGICDATA MOTIONrelax | `com.logicdata.motionrelax` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ❌ |
| Memory Presets | ✅ (3 slots) |
| Memory Programming | ✅ |
| Zero-G | ✅ |
| Anti-Snore | ✅ |
| Flat | ✅ |
| Massage | ✅ (back/leg, 0-10 levels) |
| Lights | ✅ (toggle) |

## Protocol Details

**Service/Characteristic variants:**

- Lierda1 / Comfort Motion: Service `0000ff12-0000-1000-8000-00805f9b34fb`, write `0000ff01-0000-1000-8000-00805f9b34fb`
- Lierda3 / LOGICDATA: Service `0000fe60-0000-1000-8000-00805f9b34fb`, write `0000fe61-0000-1000-8000-00805f9b34fb`

**Format:** 7-byte fixed packets

**Command format:** `F1 F1` + data bytes + checksum + `7E`
**Checksum:** Sum of data bytes (single byte)

### Motor Control Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Head Up | `f1 f1 01 01 01 03 7e` | Move head/back up |
| Head Down | `f1 f1 02 01 01 04 7e` | Move head/back down |
| Leg Up | `f1 f1 03 01 01 05 7e` | Move legs up |
| Leg Down | `f1 f1 04 01 01 06 7e` | Move legs down |
| Both Up | `f1 f1 05 01 01 07 7e` | Move head and legs up |
| Both Down | `f1 f1 06 01 01 08 7e` | Move head and legs down |
| Stop | `f1 f1 4e 00 4e 7e` | Button release / stop all |

#### 4-Motor Variants

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Head Up (Alt) | `f1 f1 19 01 01 1b 7e` | Head up (4-motor beds) |
| Head Down (Alt) | `f1 f1 1a 01 01 1c 7e` | Head down (4-motor beds) |
| Waist Up | `f1 f1 1b 01 01 1d 7e` | Waist up |
| Waist Down | `f1 f1 1c 01 01 1e 7e` | Waist down |

### Preset Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Flat | `f1 f1 08 01 01 0a 7e` | Go to flat position |
| Zero-G | `f1 f1 07 01 01 09 7e` | Go to zero gravity |
| Anti-Snore | `f1 f1 09 01 01 0b 7e` | Go to anti-snore position |

### Memory Preset Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Memory 1 (Go) | `f1 f1 0b 01 01 0d 7e` | Go to memory preset 1 (A) |
| Memory 2 (Go) | `f1 f1 0d 01 01 0f 7e` | Go to memory preset 2 (B) |
| Memory 3 (Go) | `f1 f1 18 01 01 1a 7e` | Go to memory preset 3 (C) |
| Memory 1 (Set) | `f1 f1 0a 01 01 0c 7e` | Program memory preset 1 |
| Memory 2 (Set) | `f1 f1 0c 01 01 0e 7e` | Program memory preset 2 |
| Memory 3 (Set) | `f1 f1 17 01 01 19 7e` | Program memory preset 3 |

### Massage Commands

Massage commands use the format: `F1 F1` + zone + `02 08` + level + checksum + `7E`

| Zone | Zone Byte | Level Range |
|------|-----------|-------------|
| Back | `0x12` | 0-10 |
| Leg | `0x14` | 0-10 |

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Back Massage Off | `f1 f1 12 02 08 00 1c 7e` | Turn off back massage |
| Leg Massage Off | `f1 f1 14 02 08 00 1e 7e` | Turn off leg massage |

### Other Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Light Toggle | `f1 f1 0f 00 0f 7e` | Toggle under-bed lights |
| Timer | `f1 f1 0e 00 0e 7e` | Timer function |

## Detection

Detected by:
1. Service UUID `0000ff12-...` (Comfort Motion / Lierda1) or `0000fe60-...` (Lierda3)
2. Device name containing: `jiecang`, `jc-`, `dream motion`, `glide`, `comfort motion`, or `lierda`
