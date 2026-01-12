# Supported Actuators

This document provides detailed information about each supported bed brand, including protocol details and command references.

## Table of Contents

- [Linak](#linak)
- [Richmat](#richmat)
- [Keeson](#keeson)
- [Ergomotion](#ergomotion)
- [Solace](#solace)
- [MotoSleep](#motosleep)
- [Leggett & Platt](#leggett--platt)
- [Reverie](#reverie)
- [Okimat/Okin](#okimatokin)
- [Jiecang](#jiecang)
- [DewertOkin](#dewertokin)
- [Serta](#serta)
- [Octo](#octo)
- [Mattress Firm 900](#mattress-firm-900)
- [Not Yet Supported](#not-yet-supported)

---

## Linak

**Status:** ✅ Tested

### Known Models
- Linak DPG1M (OEM controller used in many beds)
- IKEA PRAKTVÄDD / VARDÖ
- Bedre Nætter
- Jensen
- Auping
- Carpe Diem
- Many OEM adjustable beds with Linak motors

### Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ✅ |
| Memory Presets | ✅ (4 slots) |
| Massage | ✅ |
| Under-bed Lights | ✅ |

### Protocol Details

**Service UUID:** `99fa0001-338a-1024-8a49-009c0215f78a`
**Write Characteristic:** `99fa0002-338a-1024-8a49-009c0215f78a`
**Format:** 2 bytes `[command, 0x00]`

#### Motor Commands

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

#### Preset Commands

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

#### Light Commands

| Command | Bytes |
|---------|-------|
| Lights On | `0x92 0x00` |
| Lights Off | `0x93 0x00` |
| Lights Toggle | `0x94 0x00` |

#### Massage Commands

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

#### Position Feedback

Position data available via notify characteristics:
- Back: `99fa0028-...` (max 820 → 68°)
- Leg: `99fa0027-...` (max 548 → 45°)
- Head: `99fa0026-...` (3+ motors)
- Feet: `99fa0025-...` (4 motors)

---

## Richmat

**Status:** ⚠️ Untested

### Known Models
- Richmat HJA5 series
- Saatva
- Lucid L300
- Classic Brands
- Rize / Mantua (some models)
- Some Sven & Son beds

### Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ❌ |
| Memory Presets | ✅ (2 slots) |
| Massage | ✅ |
| Under-bed Lights | ✅ |
| Zero-G / Anti-Snore | ✅ |

### Protocol Variants

#### Nordic Variant
**Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
**Format:** Single byte commands

#### WiLinke Variant
**Service UUIDs:** `8ebd4f76-...` or `0000fee9-...`
**Format:** 5 bytes `[0x6E, 0x01, 0x00, command, checksum]`
**Checksum:** `(command + 111) & 0xFF`

#### Commands (Single Byte)

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

---

## Keeson

**Status:** ✅ Tested

### Known Models
- Purple adjustable bases
- GhostBed
- Member's Mark (Sam's Club) adjustable beds
- Ergomotion beds
- Tempur-Pedic (some newer models)
- Sealy Ease
- Serta (some models)
- Beautyrest (some models)
- Some Costco beds

### Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ✅ (Ergomotion variant only) |
| Memory Presets | ✅ (4 slots) |
| Massage | ✅ |
| Safety Lights | ✅ |
| Zero-G | ✅ |

### Protocol Variants

#### Base Variant (BaseI4/BaseI5) - Most Common
**Primary Service UUID:** `0000ffe5-0000-1000-8000-00805f9b34fb`
**Format:** 8 bytes `[0xE5, 0xFE, 0x16, b4, b5, b6, b7, checksum]`
**Checksum:** `sum(bytes) XOR 0xFF`

**Fallback Service UUIDs:** Some Keeson beds use different service UUIDs. The integration automatically tries these if the primary isn't found:
- `0000fff0-0000-1000-8000-00805f9b34fb` (characteristic: `0000fff2`)
- `0000ffb0-0000-1000-8000-00805f9b34fb` (characteristic: `0000ffb2`)

#### KSBT Variant (Older Remotes)
**Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
**Format:** 6 bytes `[0x04, 0x02, ...int_bytes]` (big-endian)

#### Ergomotion Variant (with Position Feedback)
Same protocol as Base variant but with real-time position updates via BLE notifications.

**Notify Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb`

Position data formats (by header byte):
| Header | Length | Description |
|--------|--------|-------------|
| `0xED` | 16 bytes | Basic position data |
| `0xF0` | 19 bytes | Extended position data |
| `0xF1` | 20 bytes | Full status data |

Position data includes:
- Head position (16-bit, 0-100 scale)
- Foot position (16-bit, 0-100 scale)
- Movement status flags
- Massage levels (0-6)
- LED status

#### Commands (32-bit Values)

| Command | Value | Description |
|---------|-------|-------------|
| Stop | `0x00000000` | Stop all |
| Head Up | `0x00000001` | Raise head |
| Head Down | `0x00000002` | Lower head |
| Feet Up | `0x00000004` | Raise feet |
| Feet Down | `0x00000008` | Lower feet |
| Tilt Up | `0x00000010` | Raise tilt |
| Tilt Down | `0x00000020` | Lower tilt |
| Lumbar Up | `0x00000040` | Raise lumbar |
| Lumbar Down | `0x00000080` | Lower lumbar |
| Massage Step | `0x00000100` | Cycle massage mode |
| Massage Timer | `0x00000200` | Cycle massage timer |
| Massage Foot Up | `0x00000400` | Increase foot massage |
| Massage Head Up | `0x00000800` | Increase head massage |
| Zero-G | `0x00001000` | Zero-G preset |
| Memory 1 | `0x00002000` | Go to memory 1 |
| Memory 2 | `0x00004000` | Go to memory 2 |
| Memory 3 | `0x00008000` | Go to memory 3 |
| Memory 4 | `0x00010000` | Go to memory 4 |
| Toggle Lights | `0x00020000` | Toggle safety lights |
| Massage Head Down | `0x00800000` | Decrease head massage |
| Massage Foot Down | `0x01000000` | Decrease foot massage |
| Flat | `0x08000000` | Flat preset |
| Massage Wave | `0x10000000` | Cycle wave massage |

---

## Solace

**Status:** ⚠️ Untested

### Known Models
- Solace hospital/care beds
- Some medical adjustable beds

### Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ❌ |
| Memory Presets | ✅ (5 slots) |
| Lift/Tilt | ✅ |
| Zero-G / Anti-Snore | ✅ |

### Protocol Details

**Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb`
**Format:** 11-byte fixed packets

#### Motor Commands

| Command | Bytes (hex) |
|---------|-------------|
| Back Up | `FF FF FF FF 05 00 00 00 03 97 01` |
| Back Down | `FF FF FF FF 05 00 00 00 04 D6 C3` |
| Legs Up | `FF FF FF FF 05 00 00 00 06 57 02` |
| Legs Down | `FF FF FF FF 05 00 00 00 07 96 C2` |
| Lift Up | `FF FF FF FF 05 00 00 00 21 17 18` |
| Lift Down | `FF FF FF FF 05 00 00 00 22 57 19` |
| Tilt Up | `FF FF FF FF 05 00 00 00 28 D7 1E` |
| Tilt Down | `FF FF FF FF 05 00 00 00 29 16 DE` |
| Stop | `FF FF FF FF 05 00 00 00 00 D7 00` |

#### Preset Commands

| Command | Bytes (hex) |
|---------|-------------|
| Flat | `FF FF FF FF 05 00 00 00 08 D6 C6` |
| All Flat | `FF FF FF FF 05 00 00 00 2A 56 DF` |
| Zero-G | `FF FF FF FF 05 00 00 00 09 17 06` |
| Anti-Snore | `FF FF FF FF 05 00 00 00 0F 97 04` |
| TV | `FF FF FF FF 05 00 00 00 05 17 03` |

#### Memory Commands

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

---

## MotoSleep

**Status:** ⚠️ Untested

### Known Models
- Beds with HHC (Hangzhou Huaci) controllers
- Device names start with "HHC" (e.g., `HHC3611243CDEF`)

### Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ❌ |
| Memory Presets | ✅ (2 slots) |
| Massage | ✅ |
| Under-bed Lights | ✅ |
| Zero-G / Anti-Snore | ✅ |

### Protocol Details

**Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb`
**Format:** 2 bytes `[0x24, ASCII_char]` (0x24 = '$')

#### Motor Commands

| Command | Bytes | ASCII | Description |
|---------|-------|-------|-------------|
| Head Up | `24 4B` | `$K` | Raise head |
| Head Down | `24 4C` | `$L` | Lower head |
| Feet Up | `24 4D` | `$M` | Raise feet |
| Feet Down | `24 4E` | `$N` | Lower feet |
| Neck Up | `24 50` | `$P` | Raise neck |
| Neck Down | `24 51` | `$Q` | Lower neck |
| Lumbar Up | `24 70` | `$p` | Raise lumbar |
| Lumbar Down | `24 71` | `$q` | Lower lumbar |

#### Preset Commands

| Command | Bytes | ASCII |
|---------|-------|-------|
| Home/Flat | `24 4F` | `$O` |
| Zero-G | `24 54` | `$T` |
| Anti-Snore | `24 52` | `$R` |
| TV | `24 53` | `$S` |
| Memory 1 | `24 55` | `$U` |
| Memory 2 | `24 56` | `$V` |
| Save Memory 1 | `24 5A` | `$Z` |
| Save Memory 2 | `24 61` | `$a` |
| Save Zero-G | `24 59` | `$Y` |
| Save Anti-Snore | `24 57` | `$W` |
| Save TV | `24 58` | `$X` |

#### Other Commands

| Command | Bytes | ASCII |
|---------|-------|-------|
| Lights Toggle | `24 41` | `$A` |
| Massage Head | `24 43` | `$C` |
| Massage Foot | `24 42` | `$B` |
| Massage Stop | `24 44` | `$D` |
| Massage Head Up | `24 47` | `$G` |
| Massage Head Down | `24 48` | `$H` |
| Massage Foot Up | `24 45` | `$E` |
| Massage Foot Down | `24 46` | `$F` |
| Massage Head Off | `24 4A` | `$J` |
| Massage Foot Off | `24 49` | `$I` |

---

## Leggett & Platt

**Status:** ⚠️ Untested

### Known Models
- Leggett & Platt Prodigy 2.0 / S-Cape 2.0
- Some Tempur-Pedic bases (non-Ergo)
- Fashion Bed Group bases

### Features

| Feature | Gen2 | Okin |
|---------|------|------|
| Motor Control | Preset-based | ✅ |
| Position Feedback | ❌ | ❌ |
| Memory Presets | ✅ (4 slots) | ✅ (4 slots) |
| Massage | ✅ (0-10 levels) | ✅ |
| RGB Lighting | ✅ | ❌ |
| Anti-Snore | ✅ | ❌ |

### Gen2 Variant (ASCII Commands)

**Service UUID:** `45e25100-3171-4cfc-ae89-1d83cf8d8071`
**Format:** ASCII text (UTF-8)

#### Preset Commands

| Command | Text |
|---------|------|
| Flat | `MEM 0` |
| Unwind (Memory 1) | `MEM 1` |
| Sleep (Memory 2) | `MEM 2` |
| Wake Up (Memory 3) | `MEM 3` |
| Relax (Memory 4) | `MEM 4` |
| Anti-Snore | `SNR` |
| Stop | `STOP` |

#### Save Commands

| Command | Text |
|---------|------|
| Save Unwind | `SMEM 1` |
| Save Sleep | `SMEM 2` |
| Save Wake Up | `SMEM 3` |
| Save Relax | `SMEM 4` |
| Save Anti-Snore | `SNPOS 0` |

#### Massage Commands

| Command | Text |
|---------|------|
| Head Massage (0-10) | `MVI 0:{level}` |
| Foot Massage (0-10) | `MVI 1:{level}` |
| Wave On | `MMODE 0:0` |
| Wave Off | `MMODE 0:2` |
| Wave Level | `WSP 0:{level}` |

#### Light Commands

| Command | Text |
|---------|------|
| Get State | `GET STATE` |
| RGB Off | `RGBENABLE 0:0` |
| RGB Set | `RGBSET 0:{RRGGBBBB}` |

### Okin Variant (Binary)

**Service UUID:** `62741523-52f9-8864-b1ab-3b3a8d65950b`
**Format:** 6 bytes `[0x04, 0x02, ...int_bytes]` (big-endian)
**Note:** Requires BLE pairing

Uses same 32-bit command values as Keeson - see [Keeson commands](#commands-32-bit-values).

---

## Reverie

**Status:** ⚠️ Untested

### Known Models
- Reverie 9T / 8Q / 7S
- Various Reverie adjustable bases

### Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (position 0-100%) |
| Position Feedback | ✅ (partial) |
| Memory Presets | ✅ (4 slots) |
| Massage | ✅ (0-10 levels) |
| Wave Massage | ✅ |
| Under-bed Lights | ✅ |
| Zero-G / Anti-Snore | ✅ |

### Protocol Details

**Service UUID:** `1b1d9641-b942-4da8-89cc-98e6a58fbd93`
**Format:** `[0x55, ...payload, checksum]`
**Checksum:** `0x55 XOR all_payload_bytes`

#### Preset Commands

| Command | Payload | Full Packet |
|---------|---------|-------------|
| Flat | `0x05` | `55 05 50` |
| Zero-G | `0x15` | `55 15 40` |
| Anti-Snore | `0x16` | `55 16 43` |
| Memory 1 | `0x11` | `55 11 44` |
| Memory 2 | `0x12` | `55 12 47` |
| Memory 3 | `0x13` | `55 13 46` |
| Memory 4 | `0x14` | `55 14 41` |
| Save Memory 1 | `0x21` | `55 21 74` |
| Save Memory 2 | `0x22` | `55 22 77` |
| Save Memory 3 | `0x23` | `55 23 76` |
| Save Memory 4 | `0x24` | `55 24 71` |
| Stop | `0xFF` | `55 FF AA` |

#### Motor Commands (Position-based)

| Command | Payload | Description |
|---------|---------|-------------|
| Head Position | `0x51 {pos}` | Move head to position (0-100) |
| Feet Position | `0x52 {pos}` | Move feet to position (0-100) |

#### Other Commands

| Command | Payload |
|---------|---------|
| Lights Toggle | `0x5B 0x00` |
| Head Massage | `0x53 {level}` (0-10) |
| Foot Massage | `0x54 {level}` (0-10) |
| Wave Massage | `0x40 + level` (0-10) |

---

## Okimat/Okin

**Status:** ⚠️ Untested

### Known Models
- Okimat beds
- Lucid L600
- Other beds with Okin motors

### Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ❌ |
| Memory Presets | ✅ (4 slots) |
| Massage | ✅ |
| Lights | ✅ |

### Protocol Details

**Service UUID:** `62741523-52f9-8864-b1ab-3b3a8d65950b`
**Format:** 6 bytes `[0x04, 0x02, ...int_bytes]` (big-endian)

**⚠️ Requires BLE pairing before use!**

Uses same 32-bit command values as Keeson - see [Keeson commands](#commands-32-bit-values).

---

## Jiecang

**Status:** ⚠️ Untested

### Known Models
- Glide adjustable beds
- Beds using Dream Motion app
- Jiecang-branded controllers

### Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ❌ (presets only) |
| Position Feedback | ❌ |
| Memory Presets | ✅ (2 slots) |
| Zero-G | ✅ |
| Flat | ✅ |

### Protocol Details

**Characteristic UUID:** `0000ff01-0000-1000-8000-00805f9b34fb`
**Format:** 7-byte fixed packets

**Note:** Jiecang beds only support preset positions - direct motor control is not available.

#### Preset Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Flat | `f1 f1 08 01 01 0a 7e` | Go to flat position |
| Zero-G | `f1 f1 07 01 01 09 7e` | Go to zero gravity |
| Memory 1 | `f1 f1 0b 01 01 0d 7e` | Go to memory preset 1 |
| Memory 2 | `f1 f1 0d 01 01 0f 7e` | Go to memory preset 2 |

### Detection

Detected by device name containing: `jiecang`, `jc-`, `dream motion`, or `glide`

---

## DewertOkin

**Status:** ⚠️ Untested

### Known Models
- A H Beard adjustable beds
- HankookGallery beds
- Beds with DewertOkin HE150 controller
- "Comfort Enhancement 2" / "Comfort Plus" app beds

### Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ❌ |
| Memory Presets | ✅ (2 slots) |
| Massage | ✅ (wave, head, foot) |
| Under-bed Lights | ✅ |
| Zero-G / TV / Quiet Sleep | ✅ |

### Protocol Details

**Write Handle:** `0x0013`
**Format:** 6-byte fixed packets
**Address Type:** Random

**Note:** DewertOkin uses handle-based writes rather than characteristic UUIDs.

#### Motor Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Head Up | `04 02 00 00 00 01` | Raise head |
| Head Down | `04 02 00 00 00 02` | Lower head |
| Foot Up | `04 02 00 00 00 04` | Raise foot |
| Foot Down | `04 02 00 00 00 08` | Lower foot |
| Stop | `04 02 00 00 00 00` | Stop all motors |

#### Preset Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Flat | `04 02 10 00 00 00` | Go to flat |
| Zero-G | `04 02 00 00 40 00` | Go to zero gravity |
| TV | `04 02 00 00 30 00` | Go to TV position |
| Quiet Sleep | `04 02 00 00 80 00` | Go to quiet sleep |
| Memory 1 | `04 02 00 00 10 00` | Go to memory 1 |
| Memory 2 | `04 02 00 00 20 00` | Go to memory 2 |

#### Massage Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Wave Massage | `04 02 80 00 00 00` | Toggle wave massage |
| Head Massage | `04 02 00 00 08 00` | Toggle head massage |
| Foot Massage | `04 02 00 40 00 00` | Toggle foot massage |
| Massage Off | `04 02 02 00 00 00` | Turn off massage |

#### Light Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Underlight | `04 02 00 02 00 00` | Toggle under-bed light |

### Detection

Detected by device name containing: `dewertokin`, `dewert`, `a h beard`, or `hankook`

---

## Serta

**Status:** ⚠️ Untested

### Known Models
- Serta Motion Perfect III
- Serta adjustable bases (BLE-enabled, non-cloud)

### Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ❌ |
| Memory Presets | ❌ |
| Massage | ✅ (intensity control) |
| Zero-G / TV / Lounge | ✅ |

### Protocol Details

**Write Handle:** `0x0020`
**Format:** 8-byte packets with `e5fe16` prefix

**Note:** Serta uses handle-based writes rather than characteristic UUIDs.

#### Motor Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Head Up | `e5 fe 16 01 00 00 00 05` | Raise head |
| Head Down | `e5 fe 16 02 00 00 00 04` | Lower head |
| Foot Up | `e5 fe 16 04 00 00 00 02` | Raise foot |
| Foot Down | `e5 fe 16 08 00 00 00 fe` | Lower foot |
| Stop | `e5 fe 16 00 00 00 00 06` | Stop all motors |

#### Preset Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Flat | `e5 fe 16 00 00 00 08 fe` | Go to flat |
| Zero-G | `e5 fe 16 00 10 00 00 f6` | Go to zero gravity |
| TV | `e5 fe 16 00 40 00 00 c6` | Go to TV position |
| Lounge | `e5 fe 16 00 20 00 00 e6` | Go to lounge |
| Head Up Preset | `e5 fe 16 00 80 00 00 86` | Go to head up preset |

#### Massage Commands

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Head Massage + | `e5 fe 16 00 08 00 00 fe` | Increase head massage |
| Head Massage - | `e5 fe 16 00 00 80 00 86` | Decrease head massage |
| Foot Massage + | `e5 fe 16 00 04 00 00 02` | Increase foot massage |
| Foot Massage - | `e5 fe 16 00 00 00 01 05` | Decrease foot massage |
| Head+Foot On | `e5 fe 16 00 01 00 00 05` | Turn on both massage |
| Massage Timer | `e5 fe 16 00 02 00 00 04` | Cycle massage timer |

### Detection

Detected by device name containing: `serta` or `motion perfect`

---

## Octo

**Status:** ⚠️ Untested

### Known Models
- Octo-branded adjustable beds
- Some OEM beds with Octo controllers

### Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ❌ |
| Memory Presets | ❌ |
| Under-bed Lights | ✅ |

### Protocol Details

**Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `0000ffe1-0000-1000-8000-00805f9b34fb`
**Format:** Packet-based with start/end markers and checksum

#### Packet Structure

```
[0x40, cmd[0], cmd[1], len_hi, len_lo, checksum, ...data, 0x40]
```

**Checksum:** `((sum_of_all_bytes XOR 0xFF) + 1) & 0xFF`

#### Motor Commands

Motors are controlled via bit masks:
- Head motor: `0x02`
- Legs motor: `0x04`
- Both motors: `0x06`

| Command | Command Bytes | Data | Description |
|---------|---------------|------|-------------|
| Move Up | `[0x02, 0x70]` | `[motor_bits]` | Move motor(s) up |
| Move Down | `[0x02, 0x71]` | `[motor_bits]` | Move motor(s) down |
| Stop | `[0x02, 0x73]` | none | Stop all motors |

#### Light Commands

| Command | Command Bytes | Data | Description |
|---------|---------------|------|-------------|
| Lights On | `[0x20, 0x72]` | `[0x00, 0x01, 0x02, 0x01, 0x01, 0x01, 0x01, 0x01]` | Turn on under-bed lights |
| Lights Off | `[0x20, 0x72]` | `[0x00, 0x01, 0x02, 0x01, 0x01, 0x01, 0x01, 0x00]` | Turn off under-bed lights |

#### Optional PIN

Some Octo beds support a 4-digit PIN lock. If enabled:
- PIN command: `command=[0x20, 0x43], data=[digit1, digit2, digit3, digit4]`

### Detection

Detected by device name containing: `octo`

---

## Mattress Firm 900

**Status:** ⚠️ Untested

**Credit:** Protocol reverse-engineered by [David Delahoz](https://github.com/daviddelahoz) - [BLEAdjustableBase](https://github.com/daviddelahoz/BLEAdjustableBase)

### Known Models
- Mattress Firm 900 Adjustable Base (iFlex)
- iFlex-branded adjustable beds

### Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (Head, Foot, Lumbar) |
| Position Feedback | ❌ |
| Memory Presets | ❌ (uses built-in presets instead) |
| Massage | ✅ (3 intensity levels) |
| Under-bed Lights | ✅ (cycle mode) |
| Lumbar Control | ✅ |

### Protocol Details

**Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e` (Nordic UART Service)
**Write Characteristic:** `6e400002-b5a3-f393-e0a9-e50e24dcca9e`
**Format:** 7-byte commands: `5A 01 03 10 [XX] [YY] A5`

**Initialization Required:** Two-step initialization sequence must be sent on first connection.

#### Initialization Commands

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Init 1 | `09 05 0A 23 05 00 00` | First initialization command |
| Init 2 | `5A 0B 00 A5` | Second initialization command |

#### Motor Commands

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Head Up | `5A 01 03 10 30 00 A5` | Raise head |
| Head Down | `5A 01 03 10 30 01 A5` | Lower head |
| Foot Up | `5A 01 03 10 30 02 A5` | Raise feet |
| Foot Down | `5A 01 03 10 30 03 A5` | Lower feet |
| Lumbar Up | `5A 01 03 10 30 06 A5` | Raise lumbar |
| Lumbar Down | `5A 01 03 10 30 07 A5` | Lower lumbar |

#### Preset Commands

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Flat | `5A 01 03 10 30 10 A5` | Go to flat position |
| Zero Gravity | `5A 01 03 10 30 13 A5` | Go to zero-G position |
| Anti-Snore | `5A 01 03 10 30 16 A5` | Go to anti-snore position |
| Lounge | `5A 01 03 10 30 17 A5` | Go to lounge position |
| Incline | `5A 01 03 10 30 18 A5` | Go to incline position |

#### Massage Commands

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Massage Level 1 | `5A 01 03 10 30 52 A5` | Set massage to level 1 |
| Massage Level 2 | `5A 01 03 10 30 53 A5` | Set massage to level 2 |
| Massage Level 3 | `5A 01 03 10 30 54 A5` | Set massage to level 3 |
| Massage Stop | `5A 01 03 10 30 6F A5` | Stop massage |
| Massage Intensity Up | `5A 01 03 10 40 60 A5` | Increase intensity |
| Massage Intensity Down | `5A 01 03 10 40 63 A5` | Decrease intensity |

#### Light Commands

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Light Cycle | `5A 01 03 10 30 70 A5` | Cycle through light modes |
| Light Off (Hold) | `5A 01 03 10 30 74 A5` | Turn off lights (hold mode) |

### Detection

Detected by device name starting with: `iflex` (case-insensitive)

Or manually configured with bed type: `mattressfirm`

### Notes

- The Mattress Firm 900 does not support user-programmable memory positions
- Instead, it provides 5 built-in presets: Flat, Zero-G, Anti-Snore, Lounge, and Incline
- Lumbar control is exposed as a separate Cover entity
- Light cycling allows stepping through brightness levels
- Protocol was manually reverse-engineered by David Delahoz in 2020 from the M900 app

---

## Advanced Configuration

### Motor Pulse Settings

For fine-tuning motor movement behavior, you can adjust these settings in the integration options:

| Setting | Range | Default | Description |
|---------|-------|---------|-------------|
| Motor Pulse Count | 1-100 | Bed-specific | Number of command repeats sent for motor movement |
| Motor Pulse Delay (ms) | 10-500 | Bed-specific | Delay between command pulses |

**Default values by bed type:**
| Bed Type | Pulse Count | Pulse Delay |
|----------|-------------|-------------|
| Richmat | 30 | 50ms |
| Keeson | 25 | 200ms |
| Others | 25 | 50ms |

**When to adjust:**
- **Increase pulse count** if motors stop moving too soon
- **Decrease pulse delay** for smoother movement
- **Increase pulse delay** if commands are getting dropped

---

## Not Yet Supported

### Sleeptracker AI (Cloud-based)
- Tempur-Pedic Ergo series (cloud-connected models)
- Beautyrest SmartMotion (cloud-connected models)
- Serta Motion series (cloud-connected models)

**Reason:** Requires cloud API, not local BLE control.

### Logicdata (Local Network)
- Tempur-Pedic beds with Logicdata controllers
- Uses local UDP/HTTP protocol, not BLE

### ErgoWifi (Cloud-based)
- Beds using Xlink cloud platform
- Requires Chinese cloud API authentication

### Eight Sleep
Will not be implemented. Use the [Eight Sleep](https://github.com/lukas-clarke/eight_sleep) integration instead.

### Sleep Number
Will not be implemented. Use the [SleepIQ](https://www.home-assistant.io/integrations/sleepiq/) integration instead.

---

## Identifying Your Bed Type

1. **Check the remote or controller** for brand markings
2. **Scan for BLE devices** using nRF Connect app
3. **Look at device names:**
   - `HHC*` → MotoSleep
   - `DPG*` or `Desk*` → Linak
   - `Okin*` → Okimat
   - `Ergomotion*` or `Ergo*` → Ergomotion
   - `Jiecang*`, `JC-*`, or `Glide*` → Jiecang
   - `Dewert*`, `A H Beard*`, or `Hankook*` → DewertOkin
   - `Serta*` or `Motion Perfect*` → Serta
   - `Octo*` → Octo

If your bed isn't auto-detected, use manual configuration and try different bed types.
