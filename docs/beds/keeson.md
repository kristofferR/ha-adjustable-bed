# Keeson

**Status:** ✅ Tested

**Credit:** Reverse engineering by [alanbixby](https://github.com/alanbixby) and [Richard Hopton/smartbed-mqtt](https://github.com/richardhopton/smartbed-mqtt)

## Known Models

Brands using Keeson/Ergomotion actuators:

- Serta
- Ergomotion
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

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Ergomotion 4.0](https://play.google.com/store/apps/details?id=com.sfd.hump) | `com.sfd.hump` |
| ✅ | [Ergomotion](https://play.google.com/store/apps/details?id=com.sfd.ergomotion) | `com.sfd.ergomotion` |
| ✅ | [Tempur Zero G Bed Base](https://play.google.com/store/apps/details?id=com.sfd.row) | `com.sfd.row` |
| ✅ | [Member's Mark Base Remote](https://play.google.com/store/apps/details?id=com.sfd.mm) | `com.sfd.mm` |

## Features

| Feature | BaseI4/I5 | KSBT | Ergomotion |
|---------|-----------|------|------------|
| Motor Control | ✅ | ✅ | ✅ |
| Position Feedback | ❌ | ❌ | ✅ |
| Memory Presets | ✅ (slots 3-4) | ✅ (slots 1-2) | ✅ (4 slots) |
| TV Preset | ❌ | ✅ | ✅ |
| Anti-Snore Preset | ❌ | ✅ | ✅ |
| Lounge Preset | ❌ | ✅ | ✅ |
| Massage | ✅ | ✅ | ✅ |
| Safety Lights | ✅ | ✅ | ✅ |
| Zero-G | ✅ | ✅ | ✅ |

## Protocol Variants

### Base Variant (BaseI4/BaseI5) - Most Common
**Primary Service UUID:** `0000ffe5-0000-1000-8000-00805f9b34fb`
**Format:** 8 bytes `[0xE5, 0xFE, 0x16, b4, b5, b6, b7, checksum]`
**Checksum:** `sum(bytes) XOR 0xFF`

**Fallback Service UUIDs:** Some Keeson beds use different service UUIDs. The integration automatically tries these if the primary isn't found:
- `0000fff0-0000-1000-8000-00805f9b34fb` (characteristic: `0000fff2`)
- `0000ffb0-0000-1000-8000-00805f9b34fb` (characteristic: `0000ffb2`)

### KSBT Variant (Older Remotes)
**Primary Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e` (Nordic UART Service)
**Format:** 6 bytes `[0x04, 0x02, ...int_bytes]` (big-endian)

**Fallback Service UUIDs:** Some KSBT devices use different service UUIDs. The integration automatically tries these if the primary isn't found:
- `0000ffe5-0000-1000-8000-00805f9b34fb` (characteristic: `0000ffe9`)
- `0000ffe0-0000-1000-8000-00805f9b34fb` (characteristic: `0000ffe1`)

### Ergomotion Variant (with Position Feedback)
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
| Memory 1 / Lounge | `0x00002000` | KSBT "M" button (not available on BaseI4/I5) |
| Memory 2 / TV | `0x00004000` | KSBT TV button (not available on BaseI4/I5) |
| Memory 3 / Anti-Snore | `0x00008000` | Memory 3 on BaseI4/I5, Anti-Snore on KSBT |
| Memory 4 | `0x00010000` | Go to memory 4 |
| Toggle Lights | `0x00020000` | Toggle safety lights |
| Massage Head Down | `0x00800000` | Decrease head massage |
| Massage Foot Down | `0x01000000` | Decrease foot massage |
| Flat | `0x08000000` | Flat preset |
| Massage Wave | `0x10000000` | Cycle wave massage |

> **Note:** Command `0x00008000` has different meanings depending on the protocol variant:
> - On **BaseI4/I5**: This is Memory 3 preset
> - On **KSBT**: This is Anti-Snore preset
>
> The TV, Lounge, and Anti-Snore presets are only available on KSBT beds. BaseI4/I5 beds (like Member's Mark) use different button layouts and may not support these commands.

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

| Device Name Prefix | Protocol |
|-------------------|----------|
| `base` | Standard FFE5/FFE9 (8-byte) |
| `KSBT03C` | Nordic UART with 6-byte packets |
| `EH` | Mattress variant (E0FF service) |
