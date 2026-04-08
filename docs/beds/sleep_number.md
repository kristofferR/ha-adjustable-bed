# Sleep Number

**Status:** Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Sleep Number Climate 360 bases advertising as `Smart bed *`
- Sleep Number FlexFit / FlexFit Smart bases using the Fuzion bamkey protocol
- Older Sleep Number BAM/MCR bases such as some i8 / 360 FlexFit 2 beds advertising the MCR UART service

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | SleepIQ | `com.selectcomfort.SleepIQ` |

## Pairing

Pairing depends on the Sleep Number BLE protocol family:

- **Fuzion / Climate 360 / FlexFit (`Smart bed *`)**: BLE pairing is required before Home Assistant can connect.
- **BAM / MCR (`ffffd1fd-...`, older i8 / 360 FlexFit 2)**: basic BLE control usually works without OS-level pairing.

For Fuzion bases, enter pairing mode by holding the side pairing button until the indicator flashes blue, then pair from Home Assistant or your system Bluetooth settings.

## Features

### Fuzion / Climate 360 / FlexFit

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

### BAM / MCR (older i8 / 360 FlexFit 2)

| Feature | Supported |
|---------|-----------|
| Motor Control | ❌ |
| Direct Position Control | ❌ |
| Position Feedback | ❌ |
| Side-specific Firmness | ✅ |
| Side-specific Foundation Presets | ✅ |
| Under Bed Lights | ✅ |
| Presence Detection | ⚠️ Only if the firmware exposes chamber occupancy bytes |
| Cooling / Heating / Footwarming | ❌ |

## Current Integration Scope

The Fuzion controller currently controls one side of the base per config entry.

- `auto` protocol variant defaults to the left side
- `left` explicitly targets the left side
- `right` explicitly targets the right side

This keeps the implementation compatible with the current entity model while still exposing split-base control.

Older BAM/MCR bases use a different controller path. They expose both firmness sides from one config entry and create separate left/right firmness numbers plus left/right foundation preset selects.

## Protocol Details

### Fuzion / Climate 360 / FlexFit

**Service UUID:** `09d23fae-90e6-44c2-95b6-0b3d0f1abf25`  
**BamKey UUID:** `421e00f3-ae76-4c49-ab6e-39e4df4a5333`  
**Auth UUID:** `8d4675a5-b5fa-42b2-b587-0ee71c46b709`  
**Transfer Info UUID:** `e8d06e2a-c987-48f8-93a8-4d18d56b4337`  
**Bulk Transfer Notify UUID:** `0ec9a5a3-8ac3-4582-92f3-1666421f323d`  
**Format:** `fUzIoN` framed bamkey blobs with CRC validation  
**Pairing Required:** Yes

## Detection

Auto-detection uses the unique Sleep Number service UUID for each protocol family:

- `09d23fae-90e6-44c2-95b6-0b3d0f1abf25`
- `ffffd1fd-388d-938b-344a-939d1f6efee0`

Typical device names look like:

- `Smart bed 0074E7`
- `64:DB:A0:07:DD:02`

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

The SleepIQ app internally names the two thermal hardware modules **Frosty**
(the "Cooling Module", cooling-only) and **Heidi** (the "Core Temperature
Module", which supports both heating *and* cooling). Only one is typically
present on a given bed; Heidi is the more modern superset.

| Action | Command |
|--------|---------|
| Check footwarming presence | `FWPG <side>` |
| Read footwarming state | `FWTG <side>` |
| Set footwarming level/timer | `FWTS <side> <off\|low\|medium\|high> <minutes>` |
| Check cooling-module (Frosty) presence | `CLPG <side>` |
| Read cooling-module mode | `CLMG <side>` |
| Set cooling-module mode/timer | `CLMS <side> <mode> <minutes>` |
| Check core-temperature-module (Heidi) presence | `THPG <side>` |
| Read core-temperature-module mode | `THMG <side>` |
| Set core-temperature-module mode/timer | `THMS <side> <mode> <minutes>` |

Mode values come from the SleepIQ app's `ThermalMode` enum:

- `off`
- `cooling_pull_low`, `cooling_pull_med`, `cooling_pull_high` — Frosty + Heidi
- `cooling_push_high` — Heidi only (exposed as the `boost` preset)
- `heating_push_low`, `heating_push_med`, `heating_push_high` — Heidi only

Turning Frosty or Heidi off sends `timer=0` to match the SleepIQ app's
behaviour. Footwarming keeps the current remaining timer when turned off, also
matching the app.

The integration exposes a single unified `Climate` climate entity that
routes to whichever module the bed has, plus a separate `Footwarming` climate
entity:

- `Climate`
  - HVAC modes: `off`, `cool`, and (Heidi only) `heat`
  - Preset modes: `low`, `medium`, `high`, and (Heidi only) `boost`
- `Footwarming` climate entity with `low`, `medium`, and `high` presets
- `Climate Timer` select (`30 min` through `10 hr`) and `Footwarming Timer`
  select (`30 min` through `6 hr`)

## Notes

1. Position values are already native percentages, so the integration exposes 0-100 direct-position controls instead of degree-based sliders.
2. Command acknowledgements and query responses depend on the notification/readback path, so the integration keeps the BamKey notification channel subscribed even when angle sensing is disabled.
3. Occupancy polling sends a grouped `BAMG` request for both sides in one call, then publishes separate left/right binary sensors.

## BAM / MCR Notes

Older BAM/MCR Sleep Number beds use a binary request/response protocol instead of BamKey text commands.

- **Service UUID:** `ffffd1fd-388d-938b-344a-939d1f6efee0`
- **Notify UUID:** `ffffd1fd-388d-938b-344a-939d1f6efee1`
- **Write UUID:** `ffffd1fd-388d-938b-344a-939d1f6efee2`
- **Transport:** MCR binary frames with `0x16 0x16` sync bytes and Fletcher-style CRC
- **Known device names:** the BLE name may just be the MAC address

The integration currently exposes:

- `Sleep Number Setting Left` and `Sleep Number Setting Right` number entities
- `Foundation Preset Left` and `Foundation Preset Right` selects
- `Under Bed Lights` switch

Implemented BAM/MCR operations:

- init handshake
- read left/right firmness
- set left/right firmness
- trigger left/right foundation presets (`Favorite`, `Read`, `Watch TV`, `Flat`, `Zero G`, `Snore`)
- read and write under-bed light state
- chamber-type query for optional occupancy support

Current BAM/MCR limitations:

- no live head/foot cover entities yet
- no climate entities
- tested 0.4.x BAM firmware returns only a short chamber payload, so occupancy sensors are not created unless the firmware exposes real occupancy bytes
