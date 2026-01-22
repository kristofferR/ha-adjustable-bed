# Okimat/Okin

**Status:** ❓ Untested

**Credit:** Reverse engineering by david_nagy, corne, PT, and [Richard Hopton/smartbed-mqtt](https://github.com/richardhopton/smartbed-mqtt)

## Known Models
- Okimat beds
- Lucid L600
- Other beds with Okin motors

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [OKIN ComfortBed II-N](https://play.google.com/store/apps/details?id=com.ore.jalon.neworebeding) | `com.ore.jalon.neworebeding` |
| ⬜ | [OKIN Comfort Bed](https://play.google.com/store/apps/details?id=com.ore.okincomfortbed) | `com.ore.okincomfortbed` |
| ✅ | [OKIN Smart Bed](https://play.google.com/store/apps/details?id=com.okin.bedding.smartbedwifi) | `com.okin.bedding.smartbedwifi` |
| ✅ | [Adjustable bed](https://play.google.com/store/apps/details?id=com.okin.bedding.adjustbed) | `com.okin.bedding.adjustbed` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ✅ |
| Memory Presets | ✅ (2-4 slots depending on remote) |
| Massage | ✅ |
| Under-bed Lights | ✅ |

> [!NOTE]
> **Okin Protocol Family**
>
> Okimat is part of a family of beds using Okin-based BLE protocols. While they share the same service UUID, they use different command formats:
>
> | Bed Type | Format | Key Difference |
> |----------|--------|----------------|
> | **Okimat** | 6-byte | UUID-based writes, has position feedback |
> | [Leggett & Platt Okin](leggett-platt.md) | 6-byte | Same protocol, different name detection |
> | [Nectar](nectar.md) | 7-byte | Different command structure |
> | [DewertOkin](dewertokin.md) | 6-byte | Handle-based writes (not UUID) |
> | [Mattress Firm 900](mattressfirm.md) | 7-byte | Uses Nordic UART service |
>
> See [Okin Protocol Family](../SUPPORTED_ACTUATORS.md#okin-protocol-family) for detection priority and troubleshooting.

## Detection

Okimat is the fallback for beds using the Okin service UUID. Detection priority:
1. Device name contains "nectar" → Nectar
2. Device name contains "leggett", "l&p", or "adjustable base" → Leggett & Platt
3. Device name contains "okimat", "okin rf", or "okin ble" → Okimat
4. Fallback → Okimat (with warning)

**If your bed is misidentified:** Change the bed type in integration settings.

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
| 92471 | RF TOPLINE | Back, Legs | 2 |
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

**Note:** On remote 93332, Head Down and Feet Down share the same command value (`0x00000020`). This is intentional per the [smartbed-mqtt reference implementation](https://github.com/richardhopton/smartbed-mqtt) - the remote hardware maps this single command to different motor functions.

### Flat Command Values

Different remotes use different values for the Flat preset:

| Flat Value | Remotes |
|------------|---------|
| `0x000000aa` | 82417, 82418, 93332 |
| `0x0000002a` | 93329 |
| `0x10000000` | 94238 |
| `0x100000aa` | 80608, 88875, 91244 |

## Position Feedback

Okimat beds support position feedback via BLE notifications.

**Position Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb`
**Notify Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb`

### Data Format

Position notifications are 7+ bytes:
- Bytes 3-4: Head position (little-endian uint16)
- Bytes 5-6: Foot position (little-endian uint16)

### Angle Conversion

| Motor | Max Raw Value | Max Angle |
|-------|---------------|-----------|
| Head/Back | 16000 | 60° |
| Foot/Legs | 12000 | 45° |

Formula: `angle = (raw_value / max_raw) * max_angle`

## Command Timing

From app disassembly analysis:

- **Repeat Interval:** ~100-150ms
- **Pattern:** Continuous while button held
- **Stop Required:** Yes

## Protocol Variants (from OKIN ComfortBed II-N app)

The app supports multiple protocol versions based on device name:

| Device Prefix | Protocol | Packet Format |
|---------------|----------|---------------|
| `okin-ble` | CB.13/CB.15 (FFE5) | 9-byte: `[0xE6, 0xFE, 0x16, cmd(4), side, checksum]` |
| `smartbed` | CB.24 (Nordic UART) | 7-byte: `[0x05, 0x02, cmd(4), 0x00]` (no checksum) |

### Additional Motors Supported

| Motor | Up | Down |
|-------|-----|------|
| Neck | `0x00000010` | `0x00000020` |
| Lumbar | `0x00000040` | `0x00000080` |
| Hips (CB.24) | `0x40000000` | `0x80000000` |
