# Vibradorm

**Status:** ✅ Tested (VMAT-basic), 🧪 Reverse-engineered from de.vibradorm.vra2 (CBI/mood light/VRT)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Vibradorm VMAT series beds
- Device names starting with "VMAT" (e.g., "VMATMEM047")
- CARESSE / WERKMEISTER / de.vibradorm.vmat (beta) — share the vra2 protocol
- Older `de.vibradorm.vra` 1.11 — same family, slightly leaner command set

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | VIBRADORM Remote | `de.vibradorm.vra` |
| ✅ | VIBRADORM Remote (vra2) | `de.vibradorm.diamant` / `de.vibradorm.vmat-beta` |
| ✅ | VIBRADORM Remote for Beds | `com.vibradorm.vmatbasic` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control (2/3/4 motors) | ✅ |
| Position Feedback (XMCMotorData) | ✅ (init/sync flags tracked) |
| Memory Presets (recall + store) | ✅ (6 slots) |
| Flat Preset | ✅ |
| Sync mode (head+foot linked) | ✅ |
| Floor Light (level + timer) | ✅ (level 0..8 on CBI, 0..255 on VMAT-basic) |
| Mood Light (RGB color / effect / speed / toggle) | ✅ (CBI/XT-box) |
| Massage / VRT (effect, speed, intensity, timer) | ✅ (head + foot zones, 0..5) |
| EEPROM diagnostics (32×8-row reassembly) | ✅ (256-byte image) |
| Control-version → motor count (advertisement) | ✅ |

**Position Feedback:** The bed reports motor positions via BLE notifications on `0x1551`. Position values are raw encoder counts that are converted to percentages of the per-motor max. The `flags` byte (bit 4 = init/limit-run requested, bit 6 = sync active) is exposed via `init_requested` and `sync_active` and forwarded to the controller-state stream.

**Motor Configurations:** The bed supports 2, 3, or 4 motor configurations. The standard 2-motor config has head/back and legs motors. The motor count is normally derived from the OEM app's `ControlType` byte in the `vibIdentifier` field of the advertisement manufacturer data (control version `0`/`5` → 2-motor, `4`/`6` → 3-motor, `1`/`-1` → 4-motor); the user-configured `motor_count` option is used as a fallback.

## Protocol Details

**Primary Service UUID:** `00001525-9f03-0de5-96c5-b8f4f3081186`
**Secondary Service UUID (DEVICE_MANAGEMENT):** `00001527-9f03-0de5-96c5-b8f4f3081186`
**Command Characteristic (VMAT-basic motor):** `00001526-9f03-0de5-96c5-b8f4f3081186` (fallbacks: `00001528`, `00001534`)
**Light Characteristic (VMAT-basic floor light):** `00001529-9f03-0de5-96c5-b8f4f3081186`
**CBI Characteristic (motor/memory/light/mood/VRT):** `00001550-9f03-0de5-96c5-b8f4f3081186`
**CBI_RESPONSE Characteristic (motor/EEPROM notifications):** `00001551-9f03-0de5-96c5-b8f4f3081186`
**Service Info (article/FW name notify):** `00001533-9f03-0de5-96c5-b8f4f3081186`

**Manufacturer ID:** 944 (0x03B0)

There are two parallel command paths:

1. **VMAT-basic** (used by `de.vibradorm.vra` and the `vmat-basic-rf-cbi` model) — single byte written to the COMMAND characteristic. `disable_angle_sensing` is auto-enabled for the RF-CBI variant because the OEM app does not use position feedback.
2. **CBI** (used by `de.vibradorm.vra2`/`vmat-beta` and their derivatives) — framed 16-bit big-endian command word `[msb, lsb, …payload]` on CBI. The toggle bit alternates `0x0000 ⇄ 0x8000` between writes (`MC.toggle()`), and the CBI bus mask `0x1000` OR'd in routes the command to the secondary "XT box" accessory bus.

Both paths share the same code words for motors, memory, and store.

### VMAT-basic command format (single byte on `COMMAND` 0x1526)

| Command | Hex | Meaning (de) | Action |
|---------|-----|--------------|--------|
| `STOP` | `0xFF` | Stop | Stop all motors |
| `AR` | `0x00` | Alles Runter | All down / flat |
| `AH` | `0x10` | Alles Hoch | All up |
| `NR` / `NH` | `0x02` / `0x03` | Nacken r/h | Neck (3/4-motor) |
| `FR` / `FH` | `0x04` / `0x05` | Fuß r/h | Foot (4-motor) |
| `OSR` / `OSH` | `0x08` / `0x09` | Oberschenkel r/h | Legs |
| `KR` / `KH` | `0x0A` / `0x0B` | Kopf r/h | Back |
| `SYNC_OFF` / `SYNC_ON` | `0x19` / `0x18` | sync off/on | head+foot sync |
| `STORE` | `0x0D` | Store | store-to-memory arming |
| `MEM1`..`MEM6` | `0x0E` `0x0F` `0x0C` `0x1A` `0x1B` `0x1C` | Memory | memory slot recall |

### CBI command set (2-byte BE word `[msb(toggle|cmd), lsb, …payload]` on `CBI` 0x1550)

| Command | Hex (base) | Purpose | Payload |
|---------|------------|---------|---------|
| `CMD_STORE` | `0x0D` | store-to-memory arming | none |
| `MEM1`..`MEM6` | `0x0E` `0x0F` `0x0C` `0x1A` `0x1B` `0x1C` | memory recall | none |
| `CMD_DIM` | `0x11` | floor light (CBI variant) | `[level, timer_min]` |
| `CMD_COLOR` | `0x77` (`0x1077` for XT box) | mood light base | varies by subcmd |
| `CMD_VxEFF` | `0x30` (`0x1030` for XT box) | VRT settings | `[effect, speed, zone1, zone2, 0, 0, 0, timer]` |
| `CMD_VRT` | `0x34` (`0x1034` for XT box) | VRT on/off | `[0|1]` |
| `CMD_GET_STATUS` | `0x3D` | request motor + EEPROM update | `[0x3F]` |
| `CMD_INIT` | `0x3E` | init/teach | — |
| `CMD_GET_INFO` | `0x1A0` | device info | — |

Mood-light subcommands ride on `CMD_COLOR` (or `0x1077` for XT box):

| Subcmd | Hex | Payload | Meaning |
|--------|-----|---------|---------|
| color | `0x01` | `[0x01, 0x00, R, G, B]` | set RGB |
| effect | `0x08` | `[0x08, effect_id]` | select effect |
| effect speed | `0x09` | `[0x09, 20-(ui+1)*2]` | set effect speed |
| toggle | — | (no payload) | on/off toggle (always uses bus mask) |

### Light control (CmdLightVMAT / CmdLightCBI)

VMAT-basic on `LIGHT` (`0x1529`):

```text
[level, 0x00, timer_min]
```

- `level`: 0 = off, `0xFF` = full brightness (we expose `0..255` here).
- `timer_min`: auto-off timer in minutes, 0 = no timer.

CBI / XT-box on `CBI` (`0x1550`):

```text
[msb(toggle|0x11|bus), lsb, level(0..8), timer_min]
```

- `level` clamped to `0..8` by `MC.setFloorLightLevel`.
- For XT-box beds, OR in the CBI bus mask (`0x1000`).

### Position feedback (XMCMotorData, on `CBI_RESPONSE` 0x1551)

Long format (11 bytes):

```text
0x20, 0x3F, flags, M1hi, M1lo, M2hi, M2lo, M3hi, M3lo, M4hi, M4lo
```

Short format (10 bytes, no 0x20 prefix):

```text
0x3F, flags, M1hi, M1lo, M2hi, M2lo, M3hi, M3lo, M4hi, M4lo
```

Motor positions are big-endian u16:

- Motor 1 (back/Kopf) — bytes `[3,4]`
- Motor 2 (legs/Oberschenkel) — bytes `[5,6]`
- Motor 3 (head/Nacken) — bytes `[7,8]`
- Motor 4 (feet/Fuß) — bytes `[9,10]`

> **Note:** the decompiled `XMCMotorData.java` reads motor 2 from bytes `[6,7]` which overlaps motor 1's MSB with motor 2's LSB. This is a source typo; the correct layout puts motor 2 at `[7,8]` and motor 3 at `[9,10]`. Our parser uses the corrected layout — see issue #403.

`flags` byte:

- `0x10` — init/limit run requested (the bed is asking the user to perform a teach-in before it can trust its positions)
- `0x40` — sync active (head+foot motors are linked)

Both bits are surfaced via the `vibradorm_init_requested` / `vibradorm_sync_active` controller-state keys (forwarded to the diagnostics stream and the `init_requested` / `sync_active` properties on the controller).

### EEPROM diagnostics (XMCeeprom, 32×8-row reassembly)

The same `CBI_RESPONSE` stream also carries 32 row notifications of 8 bytes each — the full 256-byte controller EEPROM. The layout follows `XMCeeprom.java` (issue #403 § 5c):

| Offset | Field | Type |
|--------|-------|------|
| 0 | `lock_flag` | u8 |
| 1 | `sync_mode` | u8 |
| 2 | `initZwang` | u8 |
| 10/12/14/16 | `pulseMot1..4` (live positions) | u16 |
| 20 + slot*8 + motor*2 | memory positions (6 slots × 4 motors) | u16 |
| 72/74/76/78 | `teachIn` / `factoryReset` / `initZwangCount` / `powerUp` counts | u16 |
| 80/81/82 | `wdtReset` / `systemReset` / `otherReset` | u8 |
| 84/88/92/96 | `totalPulseCountMot1..4` (lifetime travel) | u32 |
| 100 | `totalOnTime` | u32 |
| 104/106/108/110 | drive-monitoring 1..4 | u8 |
| 112 | H-bridge over-temperature | u8 |

`VibradormEeprom.set_row()` applies each notification; the controller publishes `vibradorm_eeprom_complete=True` once all 32 rows have been received. The `assets/md08eemap.xml` field labels are kept for the MD08 variant only; the generic runtime layout is the table above.

### Advertising / detection (ManufacturerDataParser)

The advertisement manufacturer-data block is parsed as:

- `manufacturerID = data[0] | data[1]<<8` (LE)
- `vibIdentifier = data[2]<<8 | data[3]` (BE) — its LSB is the OEM `ControlType` and maps to motor count (`0`/`5` → 2-motor, `4`/`6` → 3-motor, `1`/`-1` → 4-motor)
- `vibFlags = (data[4]&0xF0) | (data[5]&0xF0)>>4`
- `kundenID = (data[8]&0xF0) | (data[9]&0xF0)>>4` (or `0xFFFF` if ≤6 bytes)

## Detection

The bed is detected by:

1. **Manufacturer ID:** 944 (0x03B0) — highest priority
2. **Service UUID:** `00001525-...` or `00001527-...`
3. **Device name pattern:** Names starting with "VMAT"

## Troubleshooting

**Commands not working:**
- Ensure no other device (app, remote) is connected to the bed
- BLE beds only allow one connection at a time

**Position values seem incorrect:**
- Position calibration may vary by bed model
- Open an issue with your bed's position values for calibration assistance

**Mood light / VRT / CBI light commands silently fail:**
- These ride on the CBI characteristic (`0x1550`) — confirm the bed actually exposes it (some VMAT-basic and RF-CBI variants don't).
- Enable `has_massage` / mood light in the controller's capability flags; the `vibradorm_eeprom_complete` and `vibradorm_init_requested` controller-state keys can help diagnose.

**Octo-style 30s disconnect:**
- N/A — that's a different protocol. Vibradorm does not require a PIN.

## References

- [GitHub Issue #162](https://github.com/kristofferR/ha-adjustable-bed/issues/162) — "no positions" gap
- [GitHub Issue #403](https://github.com/kristofferR/ha-adjustable-bed/issues/403) — VMAT full protocol parity
- APK analysis in `disassembly/output/de.vibradorm.diamant/jadx/sources/de/vibradorm/vra2/`
- `Vib Control_1.11-beta-vc49_de.vibradorm.vmat.apk`
