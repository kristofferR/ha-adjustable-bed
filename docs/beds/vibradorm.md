# Vibradorm

**Status:** ✅ Tested

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Vibradorm VMAT series beds
- Device names starting with "VMAT" (e.g., "VMATMEM047")

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | VIBRADORM Remote | `de.vibradorm.vra` |
| ✅ | VIBRADORM Remote for Beds | `com.vibradorm.vmatbasic` |
| ✅ | VIBRADORM Diamant (vra2) | `de.vibradorm.diamant` |
| ✅ | Vib Control (VMAT beta) | `de.vibradorm.vmat` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ✅ |
| Memory Presets | ✅ (6 slots, recall + programming) |
| Flat Preset | ✅ |
| Floor Light | ✅ (level 0-8 + auto-off timer) |
| RGB Mood Light | ✅ (color, effect, effect speed; disabled by default) |
| Massage (VRT) | ✅ (on/off, head/foot intensity 0-5, timer, effect cycle) |
| Sync Mode | ✅ (head + foot move together) |

**Position Feedback:** The bed reports motor positions via BLE notifications on the CBI_RESPONSE characteristic (`0x1551`). Position values are raw encoder counts converted to percentages. The notification flags byte exposes *init requested* (`0x10`, positions unreliable until a teach run) and *sync active* (`0x40`); status bytes `0xC9` (ED active), `0x0E` (memory store completed) and `0x79` (link failure) are also parsed and logged.

**Motor Configurations:** The bed supports 2, 3, or 4 motor configurations. The standard 2-motor config has head/back and legs motors.

## Protocol Details

**Primary Service UUID:** `00001525-9f03-0de5-96c5-b8f4f3081186`
**Secondary Service UUID (some VMAT-BASIC-RF-CBI beds):** `00001527-9f03-0de5-96c5-b8f4f3081186`
**Command Characteristic (single-byte motor):** `00001526-9f03-0de5-96c5-b8f4f3081186` (fallbacks: `00001528`, `00001534`)
**CBI Characteristic (framed commands):** `00001550-9f03-0de5-96c5-b8f4f3081186`
**Light Characteristic:** `00001529-9f03-0de5-96c5-b8f4f3081186`
**Notify Characteristic:** `00001551-9f03-0de5-96c5-b8f4f3081186`

**Manufacturer ID:** 944 (0x03B0)

### Command paths

VMAT has two write paths:

- **VMAT-basic motor commands** — a *single byte* written to `COMMAND` (`0x1526`). STOP is `[0xFF]` on `COMMAND`.
- **CBI framed commands** — a *16-bit big-endian command word* (OR'd with an alternating toggle bit `0x0000`/`0x8000`) plus payload, written to `CBI` (`0x1550`). Memory, store, light (CBI), mood light and massage all use this path. STOP is `[0x00, 0xFF]` on `CBI`.

The XT-box accessory bus adds `0x1000` (`CBI_BUS_MASK`) to CBI command codes. The integration uses the VMAT-basic codes by default (consistent with the single-byte motor path); mood-light toggle follows the APK and always uses `0x1077`.

### Motor commands (single-byte, `COMMAND` `0x1526`)

| Command | Value | Hex |
|---------|-------|-----|
| Stop | 255 | `0xFF` |
| Head Up | 11 | `0x0B` |
| Head Down | 10 | `0x0A` |
| Legs Up | 9 | `0x09` |
| Legs Down | 8 | `0x08` |
| Foot Up (4-motor) | 5 | `0x05` |
| Foot Down (4-motor) | 4 | `0x04` |
| Neck Up (3/4-motor) | 3 | `0x03` |
| Neck Down (3/4-motor) | 2 | `0x02` |
| All Up | 16 | `0x10` |
| All Down/Flat | 0 | `0x00` |
| Sync On | 24 | `0x18` |
| Sync Off | 25 | `0x19` |

### Memory (CBI `0x1550`, `[msb(cmd\|toggle), lsb]`)

| Slot | Code | Hex |
|------|------|-----|
| M1 | 14 | `0x0E` |
| M2 | 15 | `0x0F` |
| M3 | 12 | `0x0C` |
| M4 | 26 | `0x1A` |
| M5 | 27 | `0x1B` |
| M6 | 28 | `0x1C` |
| Store | 13 | `0x0D` |

Store-to-memory handshake: `STORE (0x0D)` ×4 → `Memory(slot)` → `STOP` ×4.

### Floor light (CmdLightVMAT, `LIGHT` `0x1529`)

```text
[level, 0x00, timerMinutes]
```
- `level`: 0-8 (0 = off, 8 = brightest); clamped per `MC.setFloorLightLevel`
- `timerMinutes`: auto-off timer (0 = no timer)

### RGB mood light (CBI `0x1550`, cmd `0x77`)

- **Color:** `[msb, lsb, 0x01, 0x00, R, G, B]`
- **Effect select:** `[msb, lsb, 0x08, effectId]`
- **Effect speed:** `[msb, lsb, 0x09, speed]` where `speed = 20 - (uiSpeed * 2)` (UI speed 1-5 → wire 18,16,14,12,10)
- **Toggle on/off:** `[msb, lsb]` with cmd `0x1077` (always XT-box bus, per APK)

The mood light entity is disabled by default; enable it in HA if your bed has the hardware.

### Massage / VRT (CBI `0x1550`)

- **On/off** (cmd `0x34`): `[msb, lsb, on_off]` (1 = on, 0 = off)
- **Settings** (cmd `0x30`): `[msb, lsb, effect, speed, zone1, zone2, 0, 0, 0, timer]`
  - `zone1` = head, `zone2` = foot; intensity 0-5 (0 = zone off)
  - `speed` 1-5, `effect` small id, `timer` in minutes

### Status request (CBI `0x1550`, cmd `0x3D`)

`[msb(toggle|0x3D), lsb, 0x3F]` — triggers a position notification on `CBI_RESPONSE`.

### Position Feedback

Notifications on `CBI_RESPONSE` (`0x1551`):

```text
[0x20, 0x3F, flags, M1hi, M1lo, M2hi, M2lo, M3hi, M3lo, M4hi, M4lo]
```
(or the short form without the `0x20` prefix). Motor positions are **big-endian** uint16 values:
- M1 = back/Kopf, M2 = legs/Oberschenkel, M3 = head/Nacken, M4 = feet/Fuß

Flags byte: `0x10` = init requested (teach run needed), `0x40` = sync active.

## Detection

The bed is detected by:
1. **Manufacturer ID:** 944 (0x03B0) - highest priority
2. **Service UUID:** `00001525-...` or `00001527-...`
3. **Device name pattern:** Names starting with "VMAT"

## Troubleshooting

**Commands not working:**
- Ensure no other device (app, remote) is connected to the bed
- BLE beds only allow one connection at a time

**Position values seem incorrect:**
- Position calibration may vary by bed model
- Open an issue with your bed's position values for calibration assistance

## References

- [GitHub Issue #162](https://github.com/kristofferR/ha-adjustable-bed/issues/162)
- [GitHub Issue #403](https://github.com/kristofferR/ha-adjustable-bed/issues/403) — full VMAT protocol parity
- APK analysis in `disassembly/output/de.vibradorm.diamant/jadx/sources/de/vibradorm/vra2/`
- Full protocol notes in `disassembly/output/de.vibradorm.vmat-beta/PROTOCOL.md`
