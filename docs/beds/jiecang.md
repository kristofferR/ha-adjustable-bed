# Jiecang

**Status:** ❓ Untested

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt)

## Known Models

Brands using Jiecang actuators:

- Comfort Motion
- Dream Motion / Dreamotion Smart
- ERGOBALANCE
- Glide adjustable beds
- Jiecang-branded controllers

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Jiecang Bed / Comfort Motion](https://play.google.com/store/apps/details?id=com.jiecang.app.android.jiecangbed) | `com.jiecang.app.android.jiecangbed` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ❌ (presets only) |
| Position Feedback | ❌ |
| Memory Presets | ✅ (2 slots) |
| Zero-G | ✅ |
| Flat | ✅ |

## Protocol Details

**Characteristic UUID:** `0000ff01-0000-1000-8000-00805f9b34fb`
**Format:** 7-byte fixed packets

**Note:** Jiecang beds only support preset positions - direct motor control is not available.

### Preset Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Flat | `f1 f1 08 01 01 0a 7e` | Go to flat position |
| Zero-G | `f1 f1 07 01 01 09 7e` | Go to zero gravity |
| Memory 1 | `f1 f1 0b 01 01 0d 7e` | Go to memory preset 1 |
| Memory 2 | `f1 f1 0d 01 01 0f 7e` | Go to memory preset 2 |

## Detection

Detected by device name containing: `jiecang`, `jc-`, `dream motion`, or `glide`
