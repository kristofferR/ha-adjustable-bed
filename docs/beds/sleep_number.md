# Sleep Number Climate 360 / FlexFit

**Status:** Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Sleep Number Climate 360 bases advertising as `Smart bed *`
- Sleep Number FlexFit / FlexFit Smart bases using the Fuzion bamkey protocol

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | SleepIQ | `com.selectcomfort.SleepIQ` |

## Pairing

Sleep Number control requires BLE pairing before Home Assistant can connect.

To enter pairing mode, hold the side pairing button until the indicator flashes blue, then pair from Home Assistant or your system Bluetooth settings.

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Direct Position Control | ✅ (0-100%) |
| Position Feedback | ✅ (queried on demand) |
| Flat Preset | ✅ |
| Zero-G Preset | ✅ |
| Anti-Snore Preset | ✅ |
| TV Preset | ✅ |
| Numbered Memory Presets | ❌ |
| Under Bed Lights | ✅ |
| Presence Detection | ✅ (polling binary sensor, disabled by default) |

## Current Integration Scope

The integration currently controls one side of the base per config entry.

- `auto` protocol variant defaults to the left side
- `left` explicitly targets the left side
- `right` explicitly targets the right side

This keeps the implementation compatible with the current entity model while still exposing split-base control.

## Protocol Details

**Service UUID:** `09d23fae-90e6-44c2-95b6-0b3d0f1abf25`  
**Characteristic UUID:** `421e00f3-ae76-4c49-ab6e-39e4df4a5333`  
**Format:** UTF-8 bamkey commands and notification responses  
**Pairing Required:** Yes

## Detection

Auto-detection uses the unique Sleep Number Fuzion service UUID:

- `09d23fae-90e6-44c2-95b6-0b3d0f1abf25`

Typical device names look like:

- `Smart bed 0074E7`

## Command Format

Commands are plain UTF-8 strings written to the bamkey characteristic:

```text
<BAMKEY> <arg1> <arg2> ...
```

Responses arrive as notifications on the same characteristic:

```text
PASS:ACK
PASS:<payload>
FAIL:0
FAIL:1
FAIL:2
```

## Implemented Commands

### Actuator Control

| Action | Command |
|--------|---------|
| Read head position | `ACTG <side> head` |
| Read foot position | `ACTG <side> foot` |
| Set head target | `ACTS <side> head <0-100>` |
| Set foot target | `ACTS <side> foot <0-100>` |
| Stop head | `ACTH <side> head` |
| Stop foot | `ACTH <side> foot` |
| Stop configured side | `ACTH <side> head` and `ACTH <side> foot` |

`head` is mapped to the integration's `back` actuator and `foot` is mapped to `legs`.
The protocol also exposes a global `ACHA` halt, but the integration avoids it so one side does not stop its split-base partner.

### Presets

| Action | Command |
|--------|---------|
| Flat | `ACSP <side> flat 0` |
| Zero-G | `ACSP <side> zero_g 0` |
| Anti-Snore | `ACSP <side> snore 0` |
| TV | `ACSP <side> watch_tv 0` |

### Under-Bed Light

| Action | Command |
|--------|---------|
| Read light settings | `UBLG` |
| Set light level and timer | `UBLS <off\|low\|medium\|high> <minutes>` |

The integration exposes:

- an `Under Bed Lights` switch
- a `Light Level` number entity with values `0-3`
- a `Light Timer` select with `Off`, `15 min`, `30 min`, `45 min`, `1 hr`, `2 hr`, and `3 hr`

### Bed Presence

| Action | Command |
|--------|---------|
| Read occupancy | `LBPG <side>` |

The `Bed Presence` binary sensor tracks the configured side (`left` or `right`). It is disabled by default because it requires active polling over BLE.

## Notes

1. Position values are already native percentages, so the integration exposes 0-100 direct-position controls instead of degree-based sliders.
2. Command acknowledgements and query responses depend on BLE notifications, so the integration keeps the notification channel subscribed even when angle sensing is disabled.
