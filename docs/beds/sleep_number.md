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
| Sleep Number Setting | ✅ |
| Presence Detection | ✅ (left/right polling sensors, disabled by default) |
| Cooling / Frosty | ✅ |
| Heating / Heidi | ✅ |
| Footwarming | ✅ |

## Current Integration Scope

The integration currently controls one side of the base per config entry.

- `auto` protocol variant defaults to the left side
- `left` explicitly targets the left side
- `right` explicitly targets the right side

This keeps the implementation compatible with the current entity model while still exposing split-base control.

## Protocol Details

**Service UUID:** `09d23fae-90e6-44c2-95b6-0b3d0f1abf25`  
**BamKey UUID:** `421e00f3-ae76-4c49-ab6e-39e4df4a5333`  
**Auth UUID:** `8d4675a5-b5fa-42b2-b587-0ee71c46b709`  
**Transfer Info UUID:** `e8d06e2a-c987-48f8-93a8-4d18d56b4337`  
**Bulk Transfer Notify UUID:** `0ec9a5a3-8ac3-4582-92f3-1666421f323d`  
**Format:** `fUzIoN` framed bamkey blobs with CRC validation  
**Pairing Required:** Yes

## Detection

Auto-detection uses the unique Sleep Number Fuzion service UUID:

- `09d23fae-90e6-44c2-95b6-0b3d0f1abf25`

Typical device names look like:

- `Smart bed 0074E7`

## Command Format

The logical command payloads are bamkey strings:

```text
<BAMKEY> <arg1> <arg2> ...
```

The integration wraps those payloads in the SleepIQ app's `fUzIoN` framing, writes them to the BamKey characteristic without response, and accepts either of these response flows:

```text
1. Full framed response arrives as a notification
2. A notify hint/ack arrives, then the integration reads the BamKey characteristic to fetch the framed response
```

It also primes the Auth and Transfer Info characteristics once per connection before occupancy reads, and listens on the bulk-transfer notify characteristic because some beds use it during the readback flow.

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
| Read occupancy | `BAMG [{"bamkey":"LBPG","args":"left"},{"bamkey":"LBPG","args":"right"}]` |

The integration exposes `Left Bed Presence` and `Right Bed Presence` binary sensors. Both are disabled by default because they require active polling over BLE.

### Sleep Number Setting

| Action | Command |
|--------|---------|
| Read Sleep Number setting | `PSNG <side>` |
| Set Sleep Number setting | `PSNS <side> <5-100>` |

The integration exposes a `Sleep Number Setting` number entity for the configured side.

### Climate / Thermal Controls

| Action | Command |
|--------|---------|
| Check footwarming presence | `FWPG <side>` |
| Read footwarming state | `FWTG <side>` |
| Set footwarming level/timer | `FWTS <side> <off\|low\|medium\|high> <minutes>` |
| Check cooling presence | `CLPG <side>` |
| Read cooling mode | `CLMG <side>` |
| Set cooling mode/timer | `CLMS <side> <mode> <minutes>` |
| Check heating presence | `THPG <side>` |
| Read heating mode | `THMG <side>` |
| Set heating mode/timer | `THMS <side> <mode> <minutes>` |

The integration exposes:

- a `Cooling` climate entity with `low`, `medium`, `high`, and `boost` presets
- a `Heating` climate entity with `low`, `medium`, and `high` presets
- a `Footwarming` climate entity with `low`, `medium`, and `high` presets
- `Cooling Timer`, `Heating Timer`, and `Footwarming Timer` selects with `30 min` through `10 hr`

## Notes

1. Position values are already native percentages, so the integration exposes 0-100 direct-position controls instead of degree-based sliders.
2. Command acknowledgements and query responses depend on the notification/readback path, so the integration keeps the BamKey notification channel subscribed even when angle sensing is disabled.
3. Occupancy polling sends a grouped `BAMG` request for both sides in one call, then publishes separate left/right binary sensors.
