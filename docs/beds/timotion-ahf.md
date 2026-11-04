# TiMOTION AHF

**Status:** ❓ Needs testing (app protocol implemented; physical behavior has not been verified on hardware)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- TiMOTION AHF devices advertising names starting with `AHF`
- Adjustable bed/recliner controllers with up to five app control channels
  (Control 1–5). The Android artifact does not identify physical actuator axes.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [AHF Remote](https://play.google.com/store/apps/details?id=com.timotion.ahf), fixed P1 route | `com.timotion.ahf` |

The Android artifact establishes thirteen app-labelled controls and a status
frame. It does not identify physical actuator axes or the physical meaning of the
lamp codes.

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (app Controls 1–5; covers keep legacy axis names) |
| Night / Chair | ✅ (app-labelled actions; no verified posture meaning) |
| Position Feedback | ❌ |
| Memory Presets | ❌ |
| Factory Presets | ❌ (no flat or Zero-G commands) |
| Under-bed Lights | ✅ (toggle semantics; no discrete on/off packets) |
| Massage | ❌ (setup does not offer massage for this route) |
| Status diagnostics | ✅ (readiness, raw lock mask, lamp display code) |
| Hold until release | ✅ ([renewable](../SERVICES.md#renewable-holds) `timed_move` and `hold_control`: 100 ms refresh, then three neutral frames) |

## Protocol Details

**Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e` (Nordic UART)
**Write Characteristic:** `6e400002-b5a3-f393-e0a9-e50e24dcca9e`
**Notify Characteristic:** `6e400003-b5a3-f393-e0a9-e50e24dcca9e` (status notify/read)
**Format:** 11-byte bitmask packet, no TX checksum

### Packet Format

```text
[0xDD, 0xDD, 0xFF, group1, group1, group2, group2, 0x00, 0x00, 0x00, 0x00]
```

- The neutral packet is `DD DD FF 00 00 00 00 00 00 00 00`.
- An action sets one bit in byte 3 or byte 5, duplicates that byte into byte 4 or
  6, and leaves bytes 7–10 zero.
- `group1` carries Controls 1–3; `group2` carries Controls 4–5, Night, Light and
  Chair.

### Write Mode

- Write mode follows the properties reported for the discovered write
  characteristic.
- The integration uses write-with-response when supported and uses
  write-without-response only when it is the supported write mode.
- If neither mode is advertised, it does not write.
- Android's inherited runtime write mode was not captured, so peripheral parity
  remains a hardware validation item.

### Status readiness

- The status channel is required even when angle sensing is disabled.
- On each BLE session, the integration subscribes and reads the status
  characteristic. A valid frame from either source establishes AHF status
  readiness. A successful BLE connection or notification subscription alone does
  not.
- Subscription, the initial read, and waiting for status share one eight-second
  session deadline. A valid notification can establish readiness while the
  initial read is still pending.
- If no valid frame arrives by the deadline, AHF action buttons and held actions
  stay unavailable and report an actionable status error. The generic STOP action
  remains available for cleanup.
- Readiness resets on reconnect.
- The integration sends no new initialization, PIN, authentication, or
  model-selection packet; it relies on status notifications after connect.

## Detection / Setup

- Auto-detection is name-led: a device name starting with `AHF`, with the Nordic
  UART service as a confidence boost. Nordic UART is shared by many bed types.
- **Motor count** sets how many covers exist. The app-labelled buttons do not
  depend on it.
- Setup does not offer massage for this route.

### App setup guidance

The app's setup guidance says to hold handset buttons **1 and 3 for 5 seconds**
to broadcast, then move the phone close to **TRF2 / the Bluetooth device by the
bed**. This is app-reported setup guidance only. It does not establish another
authentication step, a model selector, a motor map, or a named posture.

## Commands

### App-labelled controls

| Control | Packet | Status lock bit |
|---------|--------|-----------------|
| Control 1 Up | `DD DD FF 01 01 00 00 00 00 00 00` | 0 |
| Control 1 Down | `DD DD FF 02 02 00 00 00 00 00 00` | 0 |
| Control 2 Up | `DD DD FF 04 04 00 00 00 00 00 00` | 1 |
| Control 2 Down | `DD DD FF 08 08 00 00 00 00 00 00` | 1 |
| Control 3 Up | `DD DD FF 10 10 00 00 00 00 00 00` | 2 |
| Control 3 Down | `DD DD FF 20 20 00 00 00 00 00 00` | 2 |
| Control 4 Up | `DD DD FF 00 00 01 01 00 00 00 00` | 3 |
| Control 4 Down | `DD DD FF 00 00 02 02 00 00 00 00` | 3 |
| Control 5 Up | `DD DD FF 00 00 04 04 00 00 00 00` | 4 |
| Control 5 Down | `DD DD FF 00 00 08 08 00 00 00 00` | 4 |
| Night | `DD DD FF 00 00 10 10 00 00 00 00` | 5 |
| Light | `DD DD FF 00 00 20 20 00 00 00 00` | none |
| Chair | `DD DD FF 00 00 40 40 00 00 00 00` | 6 |

- The integration preserves these labels. It does not map Control 1–5 to a
  physical motor, or assign physical posture, Night, Chair, Light, or lamp-code
  meanings.
- Controls 1–5, Night and Chair are unavailable when their corresponding lock bit
  is set. Bit 7 is ignored. Light has no lock bit.
- Both the button entities and the `hold_control` service use the latest valid
  mask.

### Stop

| Command | Packet | Description |
|---------|--------|-------------|
| Stop all | `DD DD FF 00 00 00 00 00 00 00 00` | Neutral frame, sent three times with 100 ms waits |

### Covers and light toggle

The motor covers and **Toggle light** button from earlier releases stay, with
their entity IDs. Removing working controls from existing entries broke
automations on other beds
([#615](https://github.com/kristofferR/ha-adjustable-bed/issues/615),
[#669](https://github.com/kristofferR/ha-adjustable-bed/issues/669),
[#670](https://github.com/kristofferR/ha-adjustable-bed/issues/670)).
These entities send the same app actions as the buttons, with the same status
and lock checks. Their names are legacy labels, not a verified motor map:

| Entity | App action |
|--------|------------|
| Back cover | Control 1 |
| Legs cover | Control 2 |
| Head cover (3+ motors) | Control 3 |
| Feet cover (4+ motors) | Control 4 |
| Pillow cover (4+ motors) | Control 5 |
| Toggle light button and the disabled-by-default assumed light | Light |

## Status diagnostics

The status frame is 15 bytes:

```text
Header byte: 0x9D
Checksum: sum(bytes[2:14]) & 0x7F == byte[14]
```

- Byte 0 must be `0x9D`; byte 14 must equal `sum(bytes[2:14]) & 0x7F`.
- Byte 1 is unchecked. Bytes 4–13 are checksum-covered but unused.

The integration publishes three diagnostic sensors:

- **AHF status communication:** `waiting`, `ready`, or `timed_out`, plus an error
  attribute when no valid frame arrives.
- **AHF raw lock mask:** the unmodified byte 2 value.
- **AHF lamp display code:** the unmodified byte 3 value, including unknown codes.

The app uses lamp code 0 for its default icon. This does not establish that the
physical lamp is off. A changed valid lamp display code queues a preempting,
serialized neutral STOP; duplicate codes and lock-mask-only changes do not.

> [!NOTE]
> Earlier versions of this document read byte 3 as light state (`0=off`,
> `1=white`, `2=green`, `3=red`). The accepted analysis does not establish those
> meanings, so the integration publishes the raw code only.

## Command Timing

| Operation | Writes | Delay | Notes |
|-----------|--------|-------|-------|
| Button press, cover and light toggle | Configured pulse count (default 10) | Configured delay (default 100 ms) | Starts with an immediate write |
| `hold_control` | Until the requested duration | 100 ms | First write after 100 ms |
| Stop | 3 | 100 ms | Neutral frame, fresh cancellation context |

### Bounded Home Assistant actions

The HA **button.press** action uses the configured finite pulse policy, which
defaults to ten writes with a 100 ms configured delay between repeats and starts
with an immediate write. BLE write latency adds to the interval. It always follows
with the three-frame neutral STOP. This is a finite HA button policy, not Android
timing parity.

The generic `adjustable_bed.hold_control` service supports these values:

```yaml
action: adjustable_bed.hold_control
data:
  device_id: YOUR_DEVICE_ID
  control: control_1_up
  duration: 2.5
```

- The first 100 ms wait, refresh cadence, and active writes are included in the
  requested duration.
- BLE write latency adds to each interval; if an action write is still pending at
  the bound, the integration cancels it.
- It then sends three neutral STOP writes with 100 ms waits between them, outside
  the requested hold duration.
- STOP cleanup uses a fresh cancellation context after normal release,
  cancellation, or a write error.
- The requested duration is HA gesture policy; it is not a firmware maximum or a
  claim of exact Android timing.

## Notes

- This protocol has no memory preset or flat/Zero-G commands.
- Light control is toggle-only; there are no discrete on/off packets. Earlier
  versions repeated the light toggle twice; it now uses the same configured pulse
  policy as the other app actions.

### Evidence boundary

The accepted row039 AHF Remote analysis establishes the app behavior summarized
here. Physical control effects, the real peripheral's GATT property combination,
and STOP latency remain unverified until user hardware validation after beta or
release. See [the row039 disposition](../apk-analysis/dispositions/row039-timotion-ahf.md)
for the complete comparison ledger and exclusions.
