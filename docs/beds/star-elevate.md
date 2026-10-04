# DewertOkin ELEVATE

**Status:** ⚠️ Implemented from complete APK evidence, hardware validation pending

ELEVATE is a separate two-actuator lift accessory used by Adjustable Comfort
M1X12 and AdjustableM5X5 systems. It is not a BOX25 bed variant even though it
uses the same Nordic UART service and StarCode envelope.

## Identification

| Field | Value |
|---|---|
| BLE name | `ELEVATE*` |
| Service | `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` |
| Write | `6E400002-B5A3-F393-E0A9-E50E24DCCA9E` |
| Notify | `6E400003-B5A3-F393-E0A9-E50E24DCCA9E` |
| Normal write type | Without response |
| Held-command interval | 100 ms |
| Authentication | None |

The integration requires the ELEVATE name plus Nordic UART for high-confidence
automatic discovery. Nordic UART by itself is intentionally not treated as a bed
signature because many unrelated devices use it.

## Session

The analyzed apps enable RX notifications and send the one-time keep-connected
frame `5A 0B 00 A5`. Normal movement writes then use:

```text
5A 01 03 10 30 [key] A5
```

Release cancels held repeats and sends the shared STOP frame once.

## Commands

| Action | Key | Final bytes |
|---|---:|---|
| Actuator 1 up | `40` | `5A 01 03 10 30 40 A5` |
| Actuator 1 down | `41` | `5A 01 03 10 30 41 A5` |
| Actuator 2 up | `42` | `5A 01 03 10 30 42 A5` |
| Actuator 2 down | `43` | `5A 01 03 10 30 43 A5` |
| Both up | `44` | `5A 01 03 10 30 44 A5` |
| Both down | `45` | `5A 01 03 10 30 45 A5` |
| Flat | `46` | `5A 01 03 10 30 46 A5` |
| STOP | `0F` | `5A 01 03 10 30 0F A5` |
| Interrupt | `4F` | `5A 01 03 10 30 4F A5` |

The app uses one or two saved ELEVATE devices by sending the same command to
each address. That is application-side fan-out, not a side selector or split-bed
byte in this protocol. Notifications are logged/de-duplicated by the apps but do
not have a semantic ELEVATE state parser, so the integration exposes no position
feedback for this controller.

## Evidence

The implementation is based on the frozen COMPLETE APK Protocol Audit reports for:

- `com.starcode.adjustablem1x12` 1.1.3
- `com.starcode.abm5_5` 1.2.3

Command direction and multi-device fan-out remain deferred real-hardware checks
after beta/release; no APK-analysis gap remains.

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

The app's session also refuses a device without a readable firmware
characteristic before it sends the wake frame. That check sends nothing to the
device and released ELEVATE entries already work without it, so this controller
does not add it as a new connection requirement. ELEVATE has no
manufacturer-selected dialect: it always uses these Star frames.
