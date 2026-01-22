# DewertOkin

**Status:** ⚠️ Untested

**Credit:** Reverse engineering by [Richard Hopton/smartbed-mqtt](https://github.com/richardhopton/smartbed-mqtt)

## Known Models

Brands using DewertOkin actuators:

- Mattress Firm / Sleepy's Elite
- Resident Adjustable Base
- Rize (multiple models: Home, Remedy, Clarity, Contemporary, Aviada)
- SIMMONS
- Nectar Move
- Power Bob Ultra
- Dynasty Bases
- Glideaway Motion
- AdjustaMattress
- Eshine Sleep
- CHERISH SMART
- OrmatekTechnoSmart
- INNOVA
- Symphony Sleep
- Jordan's (multiple models: Restful, Serenity, Tranquil, Sanctuary, Carefree, Clarity)
- Ultramatic Smart Bed
- M line
- MaxCoil Una
- AVANTI BASES
- Bedsense Bases
- RÖWA
- Simon Li
- Flexsteel Pulse
- A H Beard adjustable beds
- HankookGallery beds
- Beds with DewertOkin HE150 controller

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [FurniMove](https://play.google.com/store/apps/details?id=com.dewertokin.okinsmartcomfort) | `com.dewertokin.okinsmartcomfort` |
| ✅ | [MFRM Sleepy's Elite](https://play.google.com/store/apps/details?id=com.okin.bedding.sleepy) | `com.okin.bedding.sleepy` |
| ✅ | [Resident Adjustable Base](https://play.google.com/store/apps/details?id=com.okin.resident.release) | `com.okin.resident.release` |
| ✅ | [Resident Adjustable Bed](https://play.google.com/store/apps/details?id=com.okin.bedding.rizeResident) | `com.okin.bedding.rizeResident` |
| ✅ | [INNOVA](https://play.google.com/store/apps/details?id=com.ore.sfm) | `com.ore.sfm` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ❌ |
| Memory Presets | ✅ (2 slots) |
| Massage | ✅ (wave, head, foot) |
| Under-bed Lights | ✅ |
| Zero-G / TV / Quiet Sleep | ✅ |

## Protocol Family

DewertOkin uses the same Okin 6-byte command format (`[0x04, 0x02, <4-byte>]`) as:
- **Okimat** - UUID-based writes to `62741525-...`
- **Leggett & Platt Okin** - UUID-based writes to `62741525-...`

The key difference is that DewertOkin writes to a BLE **handle** (`0x0013`) rather than a UUID-based characteristic.

Detection is by **device name patterns** ("dewertokin", "dewert", "a h beard", "hankook"), not service UUID.

See also: [Okin Protocol Family](../SUPPORTED_ACTUATORS.md#okin-protocol-family)

## Protocol Details

**Write Handle:** `0x0013`
**Format:** 6-byte fixed packets
**Address Type:** Random

**Note:** DewertOkin uses handle-based writes rather than characteristic UUIDs.

### Motor Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Head Up | `04 02 00 00 00 01` | Raise head |
| Head Down | `04 02 00 00 00 02` | Lower head |
| Foot Up | `04 02 00 00 00 04` | Raise foot |
| Foot Down | `04 02 00 00 00 08` | Lower foot |
| Stop | `04 02 00 00 00 00` | Stop all motors |

### Preset Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Flat | `04 02 10 00 00 00` | Go to flat |
| Zero-G | `04 02 00 00 40 00` | Go to zero gravity |
| TV | `04 02 00 00 30 00` | Go to TV position |
| Quiet Sleep | `04 02 00 00 80 00` | Go to quiet sleep |
| Memory 1 | `04 02 00 00 10 00` | Go to memory 1 |
| Memory 2 | `04 02 00 00 20 00` | Go to memory 2 |

### Massage Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Wave Massage | `04 02 80 00 00 00` | Toggle wave massage |
| Head Massage | `04 02 00 00 08 00` | Toggle head massage |
| Foot Massage | `04 02 00 40 00 00` | Toggle foot massage |
| Massage Off | `04 02 02 00 00 00` | Turn off massage |

### Light Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Underlight | `04 02 00 02 00 00` | Toggle under-bed light |

## Command Timing

From app disassembly analysis (FurniMove):

- **Repeat Interval:** 100ms (`Thread.sleep(100L)`)
- **Pattern:** Continuous while button held
- **Stop Required:** Yes, explicit stop after motor release

### RF Gateway Variant

Some DewertOkin devices use an RF Gateway with an 8-byte protocol:
```
[0xE5, 0xFE, 0x16, data0, data1, data2, data3, checksum]
```

This variant uses the Keeson-style checksum (one's complement of byte sum).

## Detection

Detected by device name containing: `dewertokin`, `dewert`, `a h beard`, or `hankook`
