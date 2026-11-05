# Hush Base

**Status:** ❓ Needs testing (artifact verified; hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- L200, L300, L300SH, L400, L400SH, L500, S175, S175SH, S375, S375SH, S575 and S575SH.
- Additional stored profiles are explicit restoration choices, not discoveries of Hush hardware.
- Separate RM-/MM and HJ-/SXB sleep modules, plus the RCRM handset finder.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Hush Base](https://play.google.com/store/apps/details?id=com.richmat.hushbase) 1.0.5 (10501) | `com.richmat.hushbase` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Product-specific back, legs, pillow, lumbar, combined and third motor |
| Position Feedback | Raw index/angle/height events only, no inferred physical axis |
| Memory Presets | ✅ Product-specific recall and explicit save commands |
| Massage | ✅ Exact product zones, modes and timers |
| Lights | ✅ RGB strip for lighting-flag profiles; plain color/timer otherwise |
| Alarms | ✅ Single; repeating only on restored profiles with that capability |
| Fan and heating | ✅ Exact restored-profile memberships |
| Music | ✅ Restored music profiles and reported music capability |
| Sleep sensor | ✅ Independent BLE live data, parts, reports, information and SXB settings |
| Split sides | ✅ Explicit side-capable profile and verified non-Nordic transport |

## Protocol Details

| Transport | Service UUID | Write characteristic |
|-----------|--------------|----------------------|
| Bed | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` |
| Bed | `0000fee9-0000-1000-8000-00805f9b34fb` | `d44bc439-abfd-45a2-b575-925416129600` |
| Bed | `0000fee9-0000-1000-8000-00805f9b34bb` | `d44bc439-abfd-45a2-b575-925416129622` |
| Bed | `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe2-0000-1000-8000-00805f9b34fb` |
| Bed | `0000fff0-0000-1000-8000-00805f9b34fb` | `0000fff2-0000-1000-8000-00805f9b34fb` |
| Bed | `0000e0ff-3c17-d293-8e48-14fe2e4da212` | `00000002-3c17-d293-8e48-14fe2e4da212` |

**Notify characteristic:** first notify-capable characteristic in the selected coherent service.
**Write mode:** selected write characteristic must support write; use no-response when also offered.
**Format:** Nordic sends one opcode byte. Other bed services send `6e 01 SIDE OP SUM8`; side is 0 or 1. Shared services never identify a product.

### Sleep transport

Sleep service whitelist: `0000e0ff-3c17-d293-8e48-14fe2e4da212` and
`2320567c-05cf-6eb4-c341-772851827e1b`. MM selects write-without-response and notify properties; SXB uses write `00000002-3c17-d293-8e48-14fe2e4da212` and notify `00000003-3c17-d293-8e48-14fe2e4da212`.
Frames contain the 14-byte envelope, sequence and compact ordered JSON, split at negotiated MTU minus three. Each HA entry owns one physical target, its parser, sequence, callbacks and live intent.

## Detection / Setup

1. Select **Hush Base app (select product)** and the exact model. There is no automatic Hush profile selection from an app name or shared UUID.
2. The twelve models above are fresh Hush setup choices. Labels marked **restored profile** represent the app's wider saved-index domain, not additional fresh Hush setup models.
3. Connect before enabling native Left/Right controls. Nordic has no side byte; one-address pairing is rejected there. Two-address pairs keep independent profile and connection ownership.
4. Add a separate **Hush Base sleep sensor** entry for each sensor. Choose RM/MM or HJ/SXB explicitly. Sensor partitions and actuator sides are different concepts.
5. Add **Hush Base remote finder (RCRM handset)** to connect to the handset. There is no locator packet.

## Commands

The following opcode catalog is gated by the exact selected product; entries with the same label can have different opcodes. Every motor operation finishes with `6e` STOP using the same side and connection.

| Action | Short opcode | Program opcode |
|--------|--------------|----------------|
| HeadUp | `24` | Unavailable |
| HeadDown | `25` | Unavailable |
| FootUp | `26` | Unavailable |
| FootDown | `27` | Unavailable |
| LumberUp | `3f` | Unavailable |
| LumberDown | `40` | Unavailable |
| LightBoard | `3c` | Unavailable |
| MotorReset | `31` | Unavailable |
| MassageHeadInstensityStrengthen | `4c` | Unavailable |
| MassageFootInstensityStrengthen | `4e` | Unavailable |
| MassageModeChange | `48` | Unavailable |
| MassageModeAllOff | `47` | Unavailable |
| Massage10MinuteTimer | `5f` | Unavailable |
| Massage20MinuteTimer | `63` | Unavailable |
| Massage30MinuteTimer | `61` | Unavailable |
| TVPosition | `58` | `64` |
| LoungePosition | `59` | `65` |
| AntiSnoring | `46` | `69` |
| ZeroGravity | `45` | `66` |
| MemoryPosition1 | `2e` | `2b` |
| PillowUp | `3f` | Unavailable |
| PillowDown | `40` | Unavailable |
| LumberUp | `41` | Unavailable |
| LumberDown | `42` | Unavailable |
| LightBoard | `50` | Unavailable |
| BedLight | `3c` | Unavailable |
| MassageModeAllOff | `5e` | Unavailable |
| HeadAndFootUp | `29` | Unavailable |
| HeadAndFootDown | `2a` | Unavailable |
| PillowUp | `41` | Unavailable |
| PillowDown | `42` | Unavailable |
| MusicBlueToothSwitch | `d8` | Unavailable |
| MemoryPosition2 | `2f` | `2c` |
| Motor3Up | `71` | Unavailable |
| Motor3Down | `72` | Unavailable |
| MemoryPosition3 | `30` | `2d` |
| CoaxingSleepMode | `86` | `89` |
| Fan1InstensityStrengthen | `8a` | Unavailable |
| Fan2InstensityStrengthen | `8b` | Unavailable |
| FanAllOff | `a1` | Unavailable |
| FanConstantMode | `a3` | Unavailable |
| FanPulseMode | `a4` | Unavailable |
| FanWaveMode | `a5` | Unavailable |
| HeatingLowGear | `78` | Unavailable |
| HeatingHighGear | `79` | Unavailable |
| HeatingOff | `77` | Unavailable |
| FanChangeMode | `a2` | Unavailable |
| FanForwardAndBackwardChange | `8c` | Unavailable |
| FanTimer2Hour | `a6` | Unavailable |
| FanTimer3Hour | `a7` | Unavailable |
| FanTimer5Hour | `a8` | Unavailable |
| MassageModeAllOff | `dc` | Unavailable |
| ReleasePressurPosition | `c5` | Unavailable |
| MassageModeConstant | `3a` | Unavailable |
| MassageModePulse | `38` | Unavailable |
| MassageModeWave | `39` | Unavailable |
| CoaxingSleepMode | `76` | `89` |

### Configuration actions

Use `adjustable_bed.hush_base` with a `device_id` and `operation`. All targets validate before writes. The standard covers/buttons and card expose product controls.

| Operation | Packet / behavior |
|-----------|-------------------|
| `light_rgb` | `6e 0c ff R SUM8` plus `6e 0d G B SUM8` in one write |
| `light_seconds` | `6e 0b HI LO SUM8`, seconds; zero uses `ff ff` |
| `light_off` | Generic opcode `75`, default side 0 |
| `rgb_color` | Extended category 04/subtype 01, `[00,R,G,B]` |
| `rgb_power` | 04/04, `[00,enable]` |
| `rgb_timer` | 04/02, `[00,minutes//256,minutes&255]`; choices 5,8,10,13,15,18,21,24,27,30,120,210,300,390,480 |
| `rgb_mode`, `rgb_groove`, `rgb_breathe` | 04/05 `[00,01,mode]`, 04/05 `[00,02,mode]`, 04/06 `[00]` |
| `alarm`, `alarm_cancel` | Low `6e 05 LO 00 SUM8` first, then high/mode `6e 06 HI MODE SUM8` |
| `repeat_alarm` | Extended 05/01 `[id,reserved,hour,minute,mode,weekday-mask]` |
| `repeat_delete`, `repeat_query` | Extended 05/02 `[id]`; 05/01 query `[00]` |
| `time_sync` | Extended 08/03 `[year-1970,month,day,hour,minute,second]` |
| `sleep_name` | Extended 06/03 query `[00]` |
| `snore_detector` | Explicit external status source; five positive 3-second samples emit generic `46` on side 0; zero resets |

Extended frames are `6e 20 LENGTH CATEGORY SUBTYPE OPERATION PAYLOAD SUM8`. Query operation is 0, write operation is 1. Responses use 2/3 where defined. Transmit RGB minutes use base 256; receive timer values use base 60.

### Independent sleep actions

| Operation | JSON command / value |
|-----------|----------------------|
| `sensor_time` | `s_time`, timestamp plus MM timezone name or SXB whole-hour UTC offset |
| `sensor_query_time` | SXB `q_time`, null |
| `sensor_part`, `sensor_query_part` | `s_part` with MM 1/2 or SXB 11/12/13; MM query uses `s_part` null, SXB `q_part` null |
| `sensor_live`, `sensor_stop` | `q_realtime` `{type:0,time:1}`; stopping cancels local work, no invented bed STOP |
| `sensor_report` | `q_report` date/type/part, then report permission after one second; report parts MM 1/2/3, SXB 1/2 |
| `sensor_sensitivity` | SXB `q_sens` null; first value per side truncated minus one, without clamp |
| `sensor_query_anti_snore` | SXB `q_antiSnore` null |
| `sensor_anti_snore` | SXB `s_antiSnore` with both `L` and `R` `[enable,8,4]`; no angle semantics assigned |

The live request survives link loss/controller replacement through HA's per-address app-state store. Explicit stop/disconnect clears it. Reports accept the proven gzip/zlib wrappers and single/multi algorithm schemas. Values are device data, without medical interpretation.

## Position Feedback / Notifications

The diagnostic state retains capability events, alarms, RGB, music, raw motor/desk, lock, heating, fan, blanket and atomization values. Sleep entries expose left/right live values, report data, device time, sensitivity and anti-snore settings.

- Ordinary formats have 5, 7 or 16 bytes and no checksum requirement.
- `6e20` and `6e21` use byte length and SUM8. `6e40` uses two-byte length and CRC16-XMODEM; firmware installation is excluded.
- HA bounds malformed packets, preserves marker-valued ordinary data and expires stale partial bed frames after 500 ms.
- No raw axis is assigned a physical motor or calibrated unit without evidence.

## Command Timing

| Timing | Value |
|--------|-------|
| Bed write tick | 100 ms before each write |
| Motor hold | Configured pulse count at 100 ms, followed by protocol STOP |
| Music source | Two-second admission guard; `d8` when Bluetooth flag is false, then `c4` after 900 ms |
| Sensor live poll | Two seconds |
| External snore poll | Three seconds |
| HA query bound | Five seconds, an HA bound rather than a firmware acknowledgement |
| Report permission | One second |

HA operations retain their admitted target, cancel callbacks on connection teardown and do not reproduce the app's cross-target singleton races or unmounted UI callbacks. A local service call commits its supplied light value directly; it does not emulate the phone widget's 200 ms persistence callback or color-wheel gesture throttle.

## Notes

Hardware validation is deferred to real users after beta/release. No maintainer hardware acquisition is required.

### Analysis provenance

- `com.richmat.hushbase` 1.0.5 (10501), artifact set `d24ad2c95ea839969a5406fa8219f62048386598152608554641586041293cd7`.
- The [row126 discovery ledger](../apk-analysis/dispositions/row126-hush-base.md) and its machine-readable catalog give exact accepted source references, exhaustive dispositions and exclusions.
