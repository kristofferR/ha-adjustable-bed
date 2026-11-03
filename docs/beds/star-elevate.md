# DewertOkin ELEVATE

**Status:** ❓ Needs testing (implemented from complete APK evidence, hardware validation pending)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- DewertOkin ELEVATE two-actuator lift accessory, advertising as `ELEVATE*`
- Used with Adjustable Comfort M1X12 and [AdjustableM5X5](starcode-m5x5.md)
  systems

ELEVATE is a separate accessory, not a BOX25 bed variant, even though it uses
the same Nordic UART service and StarCode envelope.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Adjustable Comfort M1X12](https://play.google.com/store/apps/details?id=com.starcode.adjustablem1x12) 1.1.3 | `com.starcode.adjustablem1x12` |
| ✅ | [AdjustableM5X5](https://play.google.com/store/apps/details?id=com.starcode.abm5_5) 1.2.3 | `com.starcode.abm5_5` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (actuator 1, actuator 2 and both together) |
| Flat | ✅ (one-shot) |
| Position Feedback | ❌ (no semantic notification parser in the apps) |
| Group control with M5X5 / M1X12 mains | ✅ (see [AdjustableM5X5 lifts](#adjustablem5x5-lifts)) |
| Authentication | Not required |

## Protocol Details

**Service UUID:** `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`
**Write Characteristic:** `6E400002-B5A3-F393-E0A9-E50E24DCCA9E`
**Notify Characteristic:** `6E400003-B5A3-F393-E0A9-E50E24DCCA9E`
**Format:** 7-byte StarCode frame `5A 01 03 10 30 [key] A5`

| Field | Value |
|---|---|
| BLE name | `ELEVATE*` |
| Normal write type | Without response |
| Held-command interval | 100 ms |
| Authentication | None |

### Session

The analyzed apps enable RX notifications and send the one-time keep-connected
frame `5A 0B 00 A5`. Normal movement writes then use:

```text
5A 01 03 10 30 [key] A5
```

Release cancels held repeats and sends the shared STOP frame once.

ELEVATE has no manufacturer-selected dialect: it always uses these Star frames.

## Detection

- High-confidence automatic discovery requires the `ELEVATE*` name **plus**
  Nordic UART.
- Nordic UART by itself is intentionally not treated as a bed signature because
  many unrelated devices use it.
- Adjustable Comfort M1X12 lift groups require the explicit **Adjustable
  Comfort M1X12 ELEVATE** variant; see the [M1X12 guide](starcode-m1x12.md).

## Commands

### Motor Control

| Command | Key | Bytes | Description |
|---|---:|---|---|
| Actuator 1 up | `40` | `5A 01 03 10 30 40 A5` | Raise actuator 1 |
| Actuator 1 down | `41` | `5A 01 03 10 30 41 A5` | Lower actuator 1 |
| Actuator 2 up | `42` | `5A 01 03 10 30 42 A5` | Raise actuator 2 |
| Actuator 2 down | `43` | `5A 01 03 10 30 43 A5` | Lower actuator 2 |
| Both up | `44` | `5A 01 03 10 30 44 A5` | Raise both actuators |
| Both down | `45` | `5A 01 03 10 30 45 A5` | Lower both actuators |
| Flat | `46` | `5A 01 03 10 30 46 A5` | One-shot flat |
| STOP | `0F` | `5A 01 03 10 30 0F A5` | Shared STOP, sent once on release |
| Interrupt | `4F` | `5A 01 03 10 30 4F A5` | Sent to group members before a group moves |

### Session frames

| Command | Bytes | Description |
|---|---|---|
| Keep connected | `5A 0B 00 A5` | One-time wake frame after RX notifications are enabled |

## Notifications

Notifications are logged and de-duplicated by the apps, but they have no
semantic ELEVATE state parser, so the integration exposes no position feedback
for this controller.

## AdjustableM5X5 lifts

This bed type is the one route for ELEVATE devices, including those used with
the AdjustableM5X5 app. That app's ELEVATE class sends exactly the frames above
(its P3 vectors are tested against this controller), so it is not a separate
profile.

Its app-proven group behavior is carried over:

- Select an ELEVATE entry as a lift on an [AdjustableM5X5](starcode-m5x5.md)
  main. An ELEVATE can also be the main and select up to three lifts in its own
  options, matching the app's restored main slot.
- `adjustable_bed.starcode_move_lifts` drives ELEVATE lifts with both-actuator
  up/down, one-shot flat and STOP. Before a group moves, each member receives
  the interrupt frame `5A 01 03 10 30 4F A5`.
- Ordinary ELEVATE movement or flat interrupts the rest of its group first.

## Notes

- **Multiple devices:** the app uses one or two saved ELEVATE devices by
  sending the same command to each address. That is application-side fan-out,
  not a side selector or split-bed byte in this protocol.
- **Firmware characteristic check:** the app's session also refuses a device
  without a readable firmware characteristic before it sends the wake frame.
  That check sends nothing to the device and released ELEVATE entries already
  work without it, so this controller does not add it as a new connection
  requirement.

### Analysis provenance

The implementation is based on the frozen COMPLETE APK Protocol Audit reports for:

- `com.starcode.adjustablem1x12` 1.1.3
- `com.starcode.abm5_5` 1.2.3

Command direction and multi-device fan-out remain deferred real-hardware checks
after beta/release; no APK-analysis gap remains.
