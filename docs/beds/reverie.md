# Reverie

**Status:** ❓ Untested

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), Vitaliy and [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt)

## Known Models

- Reverie 9T / 8Q / 7S
- Various Reverie adjustable bases

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Reverie Nightstand](https://play.google.com/store/apps/details?id=com.reverie.reverie) | `com.reverie.reverie` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (position 0-100%) |
| Position Feedback | ✅ (partial) |
| Memory Presets | ✅ (4 slots) |
| Massage | ✅ (0-10 levels) |
| Wave Massage | ✅ |
| Under-bed Lights | ✅ |
| Zero-G / Anti-Snore | ✅ |

## Protocol Details

**Service UUID:** `1b1d9641-b942-4da8-89cc-98e6a58fbd93`
**Format:** `[0x55, ...payload, checksum]`
**Checksum:** `0x55 XOR all_payload_bytes`

### Preset Commands

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

### Motor Commands (Position-based)

| Command | Payload | Description |
|---------|---------|-------------|
| Head Position | `0x51 {pos}` | Move head to position (0-100) |
| Feet Position | `0x52 {pos}` | Move feet to position (0-100) |

### Other Commands

| Command | Payload |
|---------|---------|
| Lights Toggle | `0x5B 0x00` |
| Head Massage | `0x53 {level}` (0-10) |
| Foot Massage | `0x54 {level}` (0-10) |
| Wave Massage | `0x40 + level` (0-10) |

## Protocol 110 (Characteristic-Based)

Some Reverie beds use a different service with characteristic-based commands:

**Service UUID:** `db801000-f324-29c3-38d1-85c0c2e86885`

### Position Characteristics

| Function | UUID | Values |
|----------|------|--------|
| Head Position | `db801041-...` | 0x00-0x64 (0-100%) |
| Foot Position | `db801042-...` | 0x00-0x64 (0-100%) |
| Lumbar Position | `db801040-...` | 0x00-0x64 (0-100%) |
| Linear Head | `db801021-...` | 0x01 (up), 0x00 (stop), 0x02 (down) |
| Linear Foot | `db801022-...` | 0x01 (up), 0x00 (stop), 0x02 (down) |
| LED | `db8010a0-...` | 0x00-0x64 (brightness) |
| Presets | `db8010d0-...` | 0x01-0x07 (preset/memory selection) |

## Command Timing

From app disassembly analysis:

- **Motor commands:** Write 0x01/0x02 to start movement, 0x00 to stop
- **Position commands:** Single write (bed handles movement to target)
