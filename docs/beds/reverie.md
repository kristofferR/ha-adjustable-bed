# Reverie

**Status:** ⚠️ Untested

**Credit:** Reverse engineering by Vitaliy and [Richard Hopton/smartbed-mqtt](https://github.com/richardhopton/smartbed-mqtt)

## Known Models

- Reverie 9T / 8Q / 7S
- Various Reverie adjustable bases

Uses the **Reverie Nightstand** app.

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
