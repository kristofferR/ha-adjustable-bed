# DewertOkin

**Status:** ✅ Supported

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed) and [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt)

## Known Brands

Brands using DewertOkin/ORE actuators (79 apps analyzed):

**Rize Family:**
- Rize (Home, II, II Carefree, II Clarity, Contemporary, Bob, Sanctuary, Aviada, MF900)
- Resident Adjustable Base

**Simmons:**
- SIMMONS (US)
- Simmons Korea (시몬스)

**Customatic:**
- Customatic (Clarity, Demo, Remedy, Jerome's)

**Mattress Brands:**
- Mattress Firm (except Sleepy's Elite - see [Sleepy's Elite](sleepys.md))
- Nectar Motion
- Glory Furniture
- Tranquil Sleep
- Luxe
- Ultra

**ORE/Glideaway Family:**
- Glideaway Motion
- Symphony Sleep
- Movita
- Dynasty Bases
- Better Living
- LevaSleep
- American Star
- Avanti Bases
- Comfort Furniture
- Hestia Motion
- Maxcoil Una
- Power's Bedding
- Ultramatic Smart Bed

**Asian Markets:**
- Jobs 賈伯斯 (Taiwan)
- Koizumi (Japan)
- Minamoto Bed (Japan)
- M line
- Berun
- Alya
- Nerum
- IST

**Other Brands:**
- Simon Li
- Cherish Smart
- Support 挺你
- Apex
- Doublesleep
- OkinSmartComfort
- OrmatekTechnoSmart
- INNOVA (SFM)
- RÖWA
- Flexsteel Pulse
- A H Beard
- Hankook Gallery
- Beds with DewertOkin HE150 controller

## Apps

79 DewertOkin/ORE apps were analyzed. All use one of these protocols:

| Protocol | Apps | Service UUID | Controller |
|----------|------|--------------|------------|
| FFE5/Keeson | 31 | `0000ffe5-...` | `keeson.py` |
| OKIN UUID | 19 | `62741523-...` | `okin_uuid.py` |
| FFE0/Solace | 19 | `0000ffe0-...` | `solace.py` |
| Nordic UART | 5 | `6e400001-...` | `okin_nordic.py` |
| FFF0/WiLinke | 2 | `0000fff0-...` | `leggett_wilinke.py` |

**Key analyzed apps:**

| App | Package ID | Protocol |
|-----|------------|----------|
| MFRM Sleepy's Elite | `com.okin.bedding.sleepy` | Multi-protocol |
| Resident | `com.okin.resident.release` | Flutter |
| Rize II | `com.okin.bedding.rizeii` | OKIN UUID |
| Simmons | `com.okin.simmons` | Flutter |
| Glideaway | `com.ore.bedding.glideawaymontion` | FFE5 |
| Symphony | `com.ore.bedding.symphony` | FFE5 + Nordic |
| INNOVA/SFM | `com.ore.sfm` | FFE5 |
| OkinSmartComfort | `com.okin.okinsmartcomfort` | OKIN UUID + Nordic |

See `disassembly/output/OKIN_MASTER_ANALYSIS.md` for complete app listing.

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
