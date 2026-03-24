# SUTA Smart Home

**Status:** ✅ Tested

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- SUTA bed-frame controllers with names like `SUTA-B*`, `SUTA-M*`, `SUTA-S*`
- Confirmed app model families include B803/B804/B805, B207/B202, and M-series variants

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | SUTA Smart Home | `com.shuta.smart_home` |
| ✅ | SUTA (legacy stub app) | `com.shuta.suta_old` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (back/head, legs/feet, lumbar/tilt) |
| Position Feedback | ❌ |
| Memory Presets | ✅ (4 slots) |
| Factory Presets | ✅ (Flat, Zero-G, TV, Anti-Snore) |
| Under-bed Lights | ✅ (discrete on/off) |
| Massage | ✅ (head/foot zones, timer/duty cycle/level) |
| Split-King Sync | ✅ (discrete on/off) |

## Protocol Details

**Service UUID:** `0000fff0-0000-1000-8000-00805f9b34fb`  
**Write Characteristic:** Dynamic discovery by GATT properties (fallback: `0000fff1-0000-1000-8000-00805f9b34fb`)  
**Format:** ASCII AT commands terminated with `\r\n` (no checksum)

## Detection

Auto-detection uses:
1. Device name prefix `SUTA-`
2. `FFF0` service UUID for high confidence

Accessory/smart-mattress subtypes are intentionally excluded because they use a different protocol:
- `SUTA-MOON`
- `SUTA-TEMP`
- `SUTA-RBHC`
- `SUTA-DRAWER`
- `SUTA-STORAGE`
- `SUTA-SOFA`
- `SUTA-YOGABED`
- `SUTA-ROLLSOFA`

## Packet Format

Commands are plain UTF-8 text:

```text
"AT+...<CR><LF>"
```

Example:

```text
AT+CTRL=BOTH BACK UP\r\n
```

## Implemented Commands

### Motor Control

| Action | Command |
|--------|---------|
| Head Up | `AT+CTRL=BOTH HEAD UP` |
| Head Down | `AT+CTRL=BOTH HEAD DOWN` |
| Back Up | `AT+CTRL=BOTH BACK UP` |
| Back Down | `AT+CTRL=BOTH BACK DOWN` |
| Legs/Foot Up | `AT+CTRL=BOTH FOOT UP` |
| Legs/Foot Down | `AT+CTRL=BOTH FOOT DOWN` |
| Lumbar/Tilt Up | `AT+CTRL=BOTH T/L UP` |
| Lumbar/Tilt Down | `AT+CTRL=BOTH T/L DOWN` |
| Stop All | `AT+CTRL=BOTH STOP` |

Note: `head` is mapped to the same upper actuator commands as `back` for compatibility with existing entities.

### Presets

| Action | Command |
|--------|---------|
| Flat | `AT+MODE=BOTH FLAT` |
| Zero-G | `AT+MODE=BOTH ZEROG` |
| Anti-Snore | `AT+MODE=BOTH SNORE` |
| TV | `AT+MODE=BOTH TV` |
| Memory 1-4 Recall | `AT+MODE=BOTH M1` ... `M4` |
| Memory 1-4 Save | `AT+SETMODE=BOTH M1` ... `M4` |

### Lights

| Action | Command |
|--------|---------|
| Light On | `AT+ENABLE=LIGHT` |
| Light Off | `AT+DISABLE=LIGHT` |

### Sync / Split King

| Action | Command |
|--------|---------|
| Sync Slave On | `AT+SINSLAVE=ON` |
| Sync Slave Off | `AT+SINSLAVE=OFF` |

For split-king beds, enabling sync slave mode makes this side mirror the other side's movements.

### Massage

Massage uses three parameters per zone: Timer (T), Duty Cycle (DT), and Level (LV).

| Action | Command | Values |
|--------|---------|--------|
| Head Timer | `AT+MASS=BOTH HEAD T<param>` | e.g. `T00M` |
| Foot Timer | `AT+MASS=BOTH FOOT T<param>` | e.g. `T00M` |
| Head Duty Cycle | `AT+MASS=BOTH HEAD DT<value>` | `00` (off), `20`, `33`, `50` |
| Foot Duty Cycle | `AT+MASS=BOTH FOOT DT<value>` | `00` (off), `20`, `33`, `50` |
| Head Level | `AT+MASS=BOTH HEAD LV<value>` | `00` (off), `10`, `20`, `30` |
| Foot Level | `AT+MASS=BOTH FOOT LV<value>` | `00` (off), `10`, `20`, `30` |

Duty cycle cycles: `00` -> `20` -> `33` -> `50` -> `00`. Level cycles: `00` -> `10` -> `20` -> `30` -> `00`. Setting DT to `00` for both zones turns off all massage.

## Command Timing

| Operation | Repeat Count | Delay | Notes |
|-----------|-------------|-------|-------|
| Motor movement (default) | 7 | 150ms | Bed-type pulse defaults |
| Stop | 2 | 100ms | Sent after movement |
| Preset recall | 1 | n/a | Single command, bed firmware handles full move |
| Save memory | 5 | 150ms | Program command burst |

## Notes

1. The app includes many extra AT commands (massage, lock, beep, calibration, scheduling). Current integration support is focused on core bed control and presets.
2. The SUTA accessory family uses a different binary protocol and is intentionally excluded from SUTA bed-frame detection.
3. Characteristic UUIDs are discovered at runtime from service properties, not hardcoded in the app.

## References

- `disassembly/output/com.shuta.smart_home/ANALYSIS.md`
