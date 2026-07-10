# Keeson

**Status:** ✅ Tested

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), [alanbixby](https://github.com/alanbixby), [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt) and [MangoScango](https://github.com/MangoScango)

## Known Models

Brands using Keeson/Ergomotion actuators:

- Serta
- Ergomotion
- Ergomotion Rio 5.0 / Denver Mattress Hibernation Platinum (advertises as `KSBT03C...`; 3 motors: back, legs, lumbar — no head tilt)
- Ergomotion Rio 6.0 (advertises as `KSBT04...`, works with KSBT protocol)
- Tempur Zero G / Tempur Curve
- Beautyrest Black
- ENSO
- Dawn House
- Restonic
- Omazz Adjusto
- King Koil
- SomosBeds
- Purple adjustable bases
- GhostBed
- Member's Mark (Sam's Club) adjustable beds
- South Bay International MMKD
- Sealy Ease
- Some Costco beds

**DewertOkin/ORE brands** also using FFE5 protocol (31 apps):
- Simon Li, Cherish Smart, Minghua, Heal Every Night
- ORE: Dynasty, LevaSleep, American Star, Avanti, Comfort Furniture, Hestia Motion, Maxcoil, Power's Bedding, SFM, Ultramatic, Better Living, Koizumi
- See [DewertOkin](dewertokin.md) for full list

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Ergomotion 4.0](https://play.google.com/store/apps/details?id=com.sfd.hump) | `com.sfd.hump` |
| ✅ | [Ergomotion](https://play.google.com/store/apps/details?id=com.sfd.ergomotion) | `com.sfd.ergomotion` |
| ✅ | [Tempur Zero G Bed Base](https://play.google.com/store/apps/details?id=com.sfd.row) | `com.sfd.row` |
| ✅ | [Member's Mark Base Remote](https://play.google.com/store/apps/details?id=com.sfd.mm) | `com.sfd.mm` |
| ✅ | Ergomotion Sync | `cn.com.mancini` |
| ✅ | Linx | `com.keeson.connectedbed` |
| ✅ | Juna Sleep | `com.keeson.junasleep` |
| ✅ | [Purple Smart Base](https://play.google.com/store/apps/details?id=com.keeson.purpleBase) | `com.keeson.purpleBase` |

## Features

| Feature | BaseI4/I5 | JSON/A00A | KSBT | Ergomotion | Okin | Serta | Sino | Purple (Premium) | Purple (Premium Plus) |
|---------|-----------|------------|------|------------|------|-------|------|------------------|-----------------------|
| Motor Control | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❓ |
| Position Feedback | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❓ |
| Memory Presets | ✅ (slots 3-4) | ✅ (remote-dependent 0x2000/0x4000/0x8000/0x10000) | ✅ (slots 1-3: Read/TV/M) | ✅ (4 slots) | ✅ | ✅ | ✅ | ✅ | ❓ |
| TV Preset | ❌ | ✅ (remote-dependent) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❓ |
| Anti-Snore Preset | ❌ | ✅ (remote-dependent) | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ❓ |
| Lounge Preset | ❌ | ✅ (remote-dependent) | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ | ❓ |
| Massage | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❓ |
| Safety Lights | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❓ |
| Zero-G | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❓ |

## Protocol Variants

### Base Variant (BaseI4/BaseI5) - Most Common
**Primary Service UUID:** `0000ffe5-0000-1000-8000-00805f9b34fb`
**Format:** 8 bytes `[0xE5, 0xFE, 0x16, b4, b5, b6, b7, checksum]`
**Checksum:** `sum(bytes) XOR 0xFF`

**Fallback Service UUIDs:** Some Keeson beds use different service UUIDs. The integration automatically tries these if the primary isn't found:
- `0000fff0-0000-1000-8000-00805f9b34fb` (characteristic: `0000fff2`)
- `0000ffb0-0000-1000-8000-00805f9b34fb` (characteristic: `0000ffb2`)

### JSON/A00A Variant (Juna, Linx, Ergo Health)

**Primary Service UUID:** `0000a00a-0000-1000-8000-00805f9b34fb`  
**Write Characteristic:** `0000b002-0000-1000-8000-00805f9b34fb`  
**Indicate Characteristic:** `0000b004-0000-1000-8000-00805f9b34fb`

This family uses a JSON envelope instead of the older binary Keeson packets:

```json
{"code":2,"dvid":"<ble name>","cmd":{"key":"00001000","ctrm":1,"km":1,"keykt":0}}
```

Known remote families from the OEM apps:

- `Quest`
- `Rewind`
- `Restore`
- `Relax`

One-shot buttons use `ctrm=1, km=1, keykt=0`. Held motion is not fully uniform:

- `Quest` uses `ctrm=0, km=3, keykt=1`
- `Rewind`, `Restore`, and `Relax` use `ctrm=1, km=3, keykt=1`

The integration treats `0000a00a` as a distinct Keeson variant and uses the shared 32-bit command values, while accommodating the split held-motion metadata from the Juna/Linx app family.

### KSBT Variant (Older Remotes)

**Primary Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e` (Nordic UART Service)
**Format:** 6 bytes `[0x04, 0x02, ...int_bytes]` (big-endian)

Some Ergomotion-branded beds also use this variant. A confirmed Rio 6.0 support bundle advertises as `KSBT04...` and works correctly with the standard KSBT 6-byte protocol.
Juna's `LVrestore` and `LVrelax` remotes also use this direct 6-byte framing rather than the JSON/A00A path.

**Ergomotion Sync remotes (from `cn.com.mancini` APK):** the app has three remote layouts — A and C target `KSBT04C` devices, B targets `KSBT03C` (e.g. Rio 5.0). All three share the same preset buttons: Read = `0x2000`, TV = `0x4000`, M = `0x10000`, Zero-G = `0x1000`, Flat = `0x8000000`, Anti-Snore = `0x8000` (B/C only), light toggle = `0x20000`, and massage steps head `0x800` / foot `0x400` / timer `0x200` (no all-off command). The integration exposes Read/TV/M as memory slots 1-3 on KSBT variants.

**KSBT03C motor layout:** the KSBT03C remote (layout B) drives only three motors — head/back (`0x1`/`0x2`), feet/legs (`0x4`/`0x8`) and lumbar (`0x40`/`0x80`). There are no head-tilt (`0x10`/`0x20`) buttons, so KSBT03C beds have no tilt motor and the integration maps the third configured motor to lumbar. KSBT04C remotes (layouts A/C) additionally have the head-tilt buttons.

**Fallback Service UUIDs:** Some KSBT devices use different service UUIDs. The integration automatically tries these if the primary isn't found:
- `6e400020-b5a3-f393-e0a9-e50e24dcca9e` (characteristic: `6e400021`) - Extended Nordic UART, used by some Ergomotion/SFD beds
- `0000ffe5-0000-1000-8000-00805f9b34fb` (characteristic: `0000ffe9`)
- `0000ffe0-0000-1000-8000-00805f9b34fb` (characteristic: `0000ffe1`)

### KSBT03CR Variant
**Primary Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e` (Nordic UART Service)
**Format:** 7 bytes `[0x05, 0x02, cmd3, cmd2, cmd1, cmd0, 0x00]` (big-endian)

Auto-detected from device name prefix `ksbt03cr`. Uses the same 32-bit command values as standard KSBT; only the framing differs (7-byte packet with `0x05` prefix and trailing `0x00` byte instead of 6-byte packet with `0x04` prefix). Falls back to the same alternative service UUIDs as standard KSBT.

### Sino Variant (Dynasty, INNOVA, BetterLiving)
**Primary Service UUID:** `0000ffe5-0000-1000-8000-00805f9b34fb`
**Format:** 8 bytes `[0xE5, 0xFE, 0x16, b4, b5, b6, b7, checksum]` (big-endian byte order)

Used by BetterLiving/OKIN-BLE devices. Same packet structure as Base variant but with big-endian command byte ordering. Auto-detected by name pattern `okin-ble`.

### Ergomotion Variant (with Position Feedback)
Same protocol as Base variant but with real-time position updates via BLE notifications.

### Purple Variant
Same protocol as Base variant, but with support for Lounge and Anti-Snore presets. Additionally, Memory 1 is mapped to the typical Memory 4 address. Also supports saving memory presets by sending the recall command repeated 30x at 100ms. Note that only the "Premium" model bed has been tested, no functionality has been verified for the "Premium Plus" model.

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

### Commands (32-bit Values)

| Command | Value | Description |
|---------|-------|-------------|
| Stop | `0x00000000` | Stop all |
| Head Up | `0x00000001` | Raise head |
| Head Down | `0x00000002` | Lower head |
| Feet Up | `0x00000004` | Raise feet |
| Feet Down | `0x00000008` | Lower feet |
| Tilt Up | `0x00000010` | Raise tilt (pillow area) |
| Tilt Down | `0x00000020` | Lower tilt (pillow area) |
| Lumbar Up | `0x00000040` | Raise lumbar |
| Lumbar Down | `0x00000080` | Lower lumbar |
| Massage Step | `0x00000100` | Cycle massage mode |
| Massage Timer | `0x00000200` | Cycle massage timer |
| Massage Foot Up | `0x00000400` | Increase foot massage |
| Massage Head Up | `0x00000800` | Increase head massage |
| Zero-G | `0x00001000` | Zero-G preset |
| Memory 1 / Lounge | `0x00002000` | KSBT "Read" button, Lounge on Purple, not available on BaseI4/I5 |
| Memory 2 / TV | `0x00004000` | KSBT TV button, Purple Memory 2, not available on BaseI4/I5  |
| Memory 3 / Anti-Snore | `0x00008000` | Memory 3 on BaseI4/I5, Anti-Snore on KSBT and Purple |
| Memory 4 / M | `0x00010000` | KSBT "M" button (memory slot 3), Maps to Memory 1 on Purple |
| Toggle Lights | `0x00020000` | Toggle safety lights |
| Massage Head Down | `0x00800000` | Decrease head massage |
| Massage Foot Down | `0x01000000` | Decrease foot massage |
| Flat | `0x08000000` | Flat preset |
| Massage Wave | `0x10000000` | Cycle wave massage |

> **Note:** Command `0x00008000` has different meanings depending on the protocol variant:
> - On **BaseI4/I5**: This is Memory 3 preset
> - On **KSBT and Purple**: This is Anti-Snore preset
> - On **Juna/Linx JSON remotes**: It may be Memory 3, Sleep, or another remote-specific preset depending on the remote family
>
> The `0x00002000`, `0x00004000`, `0x00008000`, and `0x00010000` addresses are reused by multiple Keeson remote families. On Juna/Linx they can correspond to `M`, `Read`, `TV`, `Sleep`, or memory slots depending on the chosen remote.

## Command Timing

From app disassembly analysis:

| App | Motor Command Interval | Source |
|-----|------------------------|--------|
| Ergomotion | 100ms | `handler.postDelayed(this, 100)` |
| Ergomotion 4.0 | 100ms | Same as Ergomotion |
| Tempur Zero G | 100ms | Same as Ergomotion |
| Member's Mark | 400ms | `scheduleWithFixedDelay(..., 400L, TimeUnit.MILLISECONDS)` |

Motor commands are sent repeatedly while the button is held. A stop command (`0x00000000`) is sent on button release.

## Split-Bed Support (Member's Mark)

Member's Mark beds support independent control of left and right sides using a 9-byte packet:

```
[0xE6, 0xFE, 0x16, cmd_lo, cmd_mid_lo, cmd_mid_hi, cmd_hi, side, checksum]
```

| Side Byte | Meaning |
|-----------|---------|
| `0x00` | Default |
| `0x01` | Side A (Right) |
| `0x02` | Side B (Left) |

## Device Detection

Unique service UUID auto-detection:

- `0000a00a-0000-1000-8000-00805f9b34fb` -> JSON/A00A variant

| Device Name Prefix | Protocol |
|-------------------|----------|
| `base` | Standard FFE5/FFE9 (8-byte) |
| `KSBT03C` | Nordic UART with 6-byte packets (3 motors: no head tilt; e.g. Ergomotion Rio 5.0) |
| `KSBT04C` | Nordic UART with 6-byte packets (used by some Ergomotion Sync beds, including Rio 6.0) |
| `ksbt03cr` | Nordic UART with 7-byte packets (KSBT03CR variant) |
| `EH` | Mattress variant (E0FF service) |
