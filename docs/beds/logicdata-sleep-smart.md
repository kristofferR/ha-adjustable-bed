# LOGICDATA Sleep Smart Air Mattress app

**Status:** ❓ Needs testing. **Static verified, hardware unverified.**

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

The "Sleep Smart Air Mattress" app controls two separate Bluetooth devices, the
adjustable bed base and the air mattress pump, so Home Assistant configures them
as two entries:

| Device | Bed type | Setup choice |
|---|---|---|
| Bed base | `logicdata_app`, app profile `sleep_smart` | **LOGICDATA**, then **Sleep Smart Air Mattress app: bed base** |
| Air pump | `logicdata_air_pump` | **LOGICDATA**, then **Sleep Smart Air Mattress app: air mattress pump** |

The bed base is a profile over the Jiecang codec and is documented in the
[Jiecang codec guide](jiecang.md#sleep-smart-air-mattress-bed). This guide covers
the pump.

## Known Models

- Vienna and Toronto beds (command family `p1`) and the Middle Rail bed (command
  family `p2`): see the [bed profile](jiecang.md#sleep-smart-air-mattress-bed)
- Sleep Smart air mattress pump

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Sleep Smart Air Mattress](https://play.google.com/store/apps/details?id=com.logicdata.app.mattress.bed) 1.0.0 (1) | `com.logicdata.app.mattress.bed` |

## Features

| Feature | Air pump |
|---------|----------|
| Motor Control | ❌ |
| Position Feedback | ❌ |
| Memory | ✅ Pressure memory recall and save |
| Inflate / Deflate / Firmness 30 | ✅ |
| Pressure Reading | ✅ (**Air pressure** sensor, no unit) |
| Bluetooth Rename | ✅ |

## Protocol Details

**Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `ffe1` (with response)
**Notify Characteristic:** `ffe2`
**Format:** LF-terminated text

There is no pairing, authentication or initialization frame.

## Detection / Setup

- The pump cannot be identified from its advertisement: its `ffe0` service is a
  common serial-bridge service.
- Select it manually; existing entries keep their bed type.

## Air pump

### Commands

| Button | Text |
|---|---|
| Inflate (also the app's "60" mode) | `C>FILL>0` |
| Deflate | `C>EXCAPE>0` |
| Firmness 30 | `C>SETP>0>30` |
| Recall pressure memory | `C>MEMORY>0` |
| Save pressure memory | `C>STOPN`, then `C>MEM_S>0` |
| Stop | `C>STOPN` |
| Pressure query | `R>SP>0` |

Each text is sent with a trailing LF (`\n`).

### Command Timing

- A tap sends one command; the pump keeps running until its own logic or a stop.
- The app accepts a tap at most every 500 ms. The integration waits out the rest
  of that interval instead of dropping the tap, so a save always follows its
  stop by at least 500 ms.
- Stop is never delayed.

### Pressure

- While connected, **Air pressure** is queried with `R>SP>0` 800 ms after setup
  and then every 500 ms, like the app's pump tab.
- A reply starting `RET>SP>` with at least 15 characters is decoded from
  characters 13–14 as signed hexadecimal.
- The value is shown as received; the app defines no unit.
- The reading clears when the link closes. New pump entries keep the link
  between commands for the idle timeout so the reading stays current.

### Rename

`rename` renames the pump with `AT+ENAT`, `AT+LENA<name>` after 50 ms
and `AT+REST` after 100 ms, each ending in CR LF. The pump restarts afterwards.
Names use the app's edit-field alphabet (`0-9`, `a-z`, `A-Z`, `ä`, `ö`, `ü`,
`Ä`, `Ö`, `Ü` and `ß`) with at most 20 characters (and at most 40 UTF-8 bytes).

## Not implemented

- The app's pump copy service has no live caller. Bed-side exclusions are listed
  in the [bed profile](jiecang.md#sleep-smart-air-mattress-bed).
- Reconnect dialogs, QR-code address entry, scan lists and Android permission
  flows belong to the phone app; Home Assistant connects to the configured
  address.

## Notes

### Analysis provenance

- Package `com.logicdata.app.mattress.bed` **1.0.0 (1)**. Both devices follow
  the accepted APK Protocol Audit report for this version.
- Bed frames, startup and timing are generated from `profiles/logicdata.py` in
  the [Jiecang codec guide](jiecang.md#logicdata-app-family).
- Audit: APK Protocol Audit row053.

### Deferred hardware checks

Later hardware checks should confirm motor stopping, pressure units and scale,
the pump's response to rapid taps and the three rename phases, and which
services real beds expose.
