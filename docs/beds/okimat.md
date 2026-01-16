# Okimat/Okin

**Status:** ❓ Untested

## Known Models
- Okimat beds
- Lucid L600
- Other beds with Okin motors

## Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ❌ |
| Memory Presets | ✅ (2-4 slots depending on remote) |
| Massage | ✅ |
| Under-bed Lights | ✅ |

## Protocol Details

**Service UUID:** `62741523-52f9-8864-b1ab-3b3a8d65950b`
**Format:** 6 bytes `[0x04, 0x02, ...int_bytes]` (big-endian)

**⚠️ Requires BLE pairing before use!**

## Supported Remote Codes

Different Okimat remotes have varying capabilities. The remote code is typically printed on the remote or controller.

| Remote Code | Model | Motors | Memory Slots |
|-------------|-------|--------|--------------|
| 80608 | RFS ELLIPSE | Back, Legs | None |
| 82417 | RF TOPLINE | Back, Legs | None |
| 82418 | RF TOPLINE | Back, Legs | 2 |
| 88875 | RF LITELINE | Back, Legs | None |
| 91244 | RF-FLASHLINE | Back, Legs | None |
| 93329 | RF TOPLINE | Head, Back, Legs | 4 |
| 93332 | RF TOPLINE | Head, Back, Legs, Feet | 2 |
| 94238 | RF FLASHLINE | Back, Legs | 2 |

## Commands (32-bit Values)

| Command | Value | Remotes | Description |
|---------|-------|---------|-------------|
| Stop | `0x00000000` | All | Stop all motors |
| Back Up | `0x00000001` | All | Raise back |
| Back Down | `0x00000002` | All | Lower back |
| Legs Up | `0x00000004` | All | Raise legs |
| Legs Down | `0x00000008` | All | Lower legs |
| Head Up | `0x00000010` | 93329, 93332 | Raise head (tilt) |
| Head Down | `0x00000020` | 93329, 93332 | Lower head (tilt) |
| Feet Up | `0x00000040` | 93332 | Raise feet |
| Feet Down | `0x00000020` | 93332 | Lower feet |
| Memory 1 | `0x00001000` | 82418, 93329, 93332, 94238 | Go to memory 1 |
| Memory 2 | `0x00002000` | 82418, 93329, 93332, 94238 | Go to memory 2 |
| Memory 3 | `0x00004000` | 93329 | Go to memory 3 |
| Memory 4 | `0x00008000` | 93329 | Go to memory 4 |
| Memory Save | `0x00010000` | 82418, 93329, 93332, 94238 | Save current position |
| Toggle Lights | `0x00020000` | All | Toggle under-bed lights |

### Flat Command Values

Different remotes use different values for the Flat preset:

| Flat Value | Remotes |
|------------|---------|
| `0x000000aa` | 82417, 82418, 93332 |
| `0x0000002a` | 93329 |
| `0x10000000` | 94238 |
| `0x100000aa` | 80608, 88875, 91244 |
