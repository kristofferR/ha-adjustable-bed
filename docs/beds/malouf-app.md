# Malouf Base / Lucid Base app profiles

**Status:** ❓ Needs testing (artifact-verified, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

This opt-in controller is separate from the existing tested
[Malouf/OKIN](malouf.md) and generic [Richmat](richmat.md) controllers.

## Known Models

The supported model constructors include Altitude, E450, E455, Forte, Good Life
Base, Good Life Premier Base, Good Life Pro Base, L300, L600, M455, M550, M555,
Premium, S655, S750, and S755.

- Setup selects the app first, then offers its packaged model picker: 14 choices
  for Malouf Base and L300, L600, and Premium for Lucid Base.
- Some models are available only through the apps' persisted model selection,
  so the selected app remains significant for these models too. Options retain
  an existing persisted-only model for that same app.
- A retail model does not prove its Bluetooth protocol.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Malouf Base](https://play.google.com/store/apps/details?id=com.malouf.bedbase) 2.4.3 | `com.malouf.bedbase` |
| ✅ | [Lucid Base](https://play.google.com/store/apps/details?id=com.lucid.bedbase) 1.3.3 | `com.lucid.bedbase` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Back/legs, supported combined movement, tilt/lumbar, Altitude head/full tilt |
| Position Feedback | ❌ (the apps provide no motor-position feedback) |
| Memory Presets | ⚠️ Zero to two slots, per model |
| Presets | ✅ Flat, plus the model's Zero-G, TV, Anti-Snore and Lounge |
| Massage | ✅ Head, foot, wave mode; direct 10/20/30-minute timers (Richmat) or timer step (OKIN) |
| Under-bed Lighting | ✅ Native toggle; on/off need known feedback |
| Clock and Alarms | ⚠️ OKIN transports, alarm-capable models |
| Single-address Pairing | ❌ |

Controls follow the selected constructor and its reachable app routes. A
constructor label alone never enables a command that has no endpoint in the
selected app and transport.

## Protocol Details

**Format:** five transports, each with its own frame; see [Transport contracts](#transport-contracts)

| Transport | Service | Write | Notify |
|-----------|---------|-------|--------|
| Richmat single | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | none |
| Richmat framed | `0000fee9-0000-1000-8000-00805f9b34fb` | `d44bc439-abfd-45a2-b575-925416129600` | none |
| OKIN legacy | `0000ffe5-0000-1000-8000-00805f9b34fb` | `0000ffe9-0000-1000-8000-00805f9b34fb` | `0000ffe4-0000-1000-8000-00805f9b34fb` (service `0000ffe0-0000-1000-8000-00805f9b34fb`) |
| OKIN custom | `62741523-52f9-8864-b1ab-3b3a8d65950b` | `62741525-52f9-8864-b1ab-3b3a8d65950b` | `62741625-52f9-8864-b1ab-3b3a8d65950b` |
| OKIN new | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` |

### Transport contracts

| Transport | Command frame | Preset policy |
|-----------|---------------|---------------|
| Richmat single | One opcode byte | One write, then `6e` STOP |
| Richmat framed | `6e 01 selector opcode checksum` | One write, no preset STOP |
| OKIN legacy | `e6 fe 16` + little-endian command + zero + complement checksum | Three writes, no preset STOP |
| OKIN custom | `04 02` + big-endian command + four zeros | Three writes, then zero STOP |
| OKIN new | `05 02` + big-endian command + two zeros | One write, then zero STOP |

- The Richmat framed checksum is `(0x6F + selector + opcode) & 0xFF`.
- Each transport is a complete, coherent role set, never a service-order hybrid.
  Each required characteristic must appear exactly once with its write or
  notify property.

### Write Mode

All characteristic writes use Android's numeric mode 2, `WRITE_TYPE_DEFAULT`,
which requires acknowledgement (`response=True`). A bounded audit addendum
corrects the older reports' descriptive no-response wording; their numeric
artifact evidence remains unchanged.

### Secondary Selector

Richmat framed selector 1 applies only to secondary head up/down, head massage,
Flat, Zero-G and Anti-Snore. Foot, combined movement, memory, timer, lighting,
and STOP use selector 0. The controller never extrapolates side selection to
unsupported actions.

## Detection / Setup

Select **Malouf Base / Lucid Base app** under Malouf/Lucid, then choose the
Android app and exact model used with your bed. Existing entries retain their
controller and settings.

- Changing apps refreshes the model choices before saving; it does not carry a
  stored-only model to another app.
- Choose the physical primary/secondary role used in the app. Home Assistant's
  Left/Right names do not prove that role.
- When combining two Bluetooth addresses, configure each bed separately before
  combining them.
- Single-address pairing is not offered: the app's secondary selector covers
  only some commands, while STOP and other actions remain global.
- Automatic transport selection uses the observed Bluetooth name and connected
  GATT services. It rejects ambiguous or incomplete layouts.
- An explicit transport override must still match a complete writable
  service/characteristic layout.
- Shared UART and custom service identifiers never select an app or retail model.

## Models and controls

| Model | Memory slots | Movement | Presets | Functions |
|-------|--------------|----------|---------|-----------|
| Altitude | 0 | Back, legs, combined, head tilt, full tilt | Zero-G, Anti-Snore | Massage (head, foot, wave), massage off, light |
| E450 | 0 | Back, legs | Zero-G, Anti-Snore | None |
| E455 | 0 | Back, legs | Zero-G, Anti-Snore | None |
| Forte | 0 | Back, legs | Zero-G | Massage (head, wave), massage off |
| Good Life Base | 0 | Back, legs, combined | Zero-G, TV, Anti-Snore, Lounge | None |
| Good Life Premier Base | 0 | Back, legs, combined, tilt, lumbar | Zero-G, TV, Anti-Snore, Lounge | Massage (head, foot, wave), massage off, direct timer, light |
| Good Life Pro Base | 0 | Back, legs, combined | Zero-G, TV, Anti-Snore, Lounge | Massage (head, foot, wave), massage off, direct timer, light |
| L300 | 0 | Back, legs | Zero-G, Anti-Snore | None |
| L600 | 1 | Back, legs | Zero-G, Anti-Snore, Lounge, TV | Massage (head, foot, wave), timer step, alarm, light |
| M455 | 0 | Back, legs | Zero-G, Anti-Snore | Massage (head, wave), massage off, direct timer |
| M550 | 1 | Back, legs | Zero-G, Anti-Snore, Lounge, TV | Massage (head, foot, wave), timer step, alarm, light |
| M555 | 1 | Back, legs, combined | Zero-G, TV, Anti-Snore, Lounge | Massage (head, foot, wave), massage off, direct timer, light |
| Premium | 2 | Back, legs, combined | Zero-G, Anti-Snore, TV | Massage (head, foot, wave), timer step, alarm, light |
| S655 | 2 | Back, legs, combined, tilt | Zero-G, TV, Anti-Snore, Lounge | Massage (head, foot, wave), massage off, direct timer, light |
| S750 | 2 | Back, legs, tilt, lumbar | Zero-G, TV, Anti-Snore, Lounge | Massage (head, foot, wave), timer step, alarm, light |
| S755 | 2 | Back, legs, combined, tilt, lumbar | Zero-G, TV, Anti-Snore, Lounge | Massage (head, foot, wave), massage off, direct timer, light |

The table lists each constructor's controls. The connected transport then
removes routes it has no endpoint for:

- Lucid Premium on an OKIN transport exposes **Read**. Its command shares the
  lounge value. Malouf's uppercase READ route has no write endpoint.
- Lucid Good Life Zero-G and Anti-Snore routes work only on Richmat. Malouf
  normalizes those app labels and supports both command families.
- Good Life combined movement has no OKIN endpoint and is suppressed there.
- Altitude head tilt and full tilt are Richmat-only.
- Lucid Good Life models expose **Save Memory 2** for the shared save route
  reached by holding either Oz control. Those models declare zero recall slots,
  so this button does not enable memory recall or generic memory programming.
- Richmat massage timers are direct 10/20/30-minute controls where reachable.
  OKIN has a timer-step command rather than direct duration selection. Massage
  off is Richmat-only.
- Notification state reports massage time and, where supported, light status.
  The apps provide no motor-position, light-brightness, or color feedback.

For a feedback light whose state is still unknown, use the card's light toggle
or Home Assistant's `light.toggle` action. Both send the native toggle without
guessing the current state. Explicit `light.turn_on` and `light.turn_off` require
known feedback.

## Commands

Richmat values are the opcode byte; OKIN values are the 32-bit command placed in
the transport frame.

### Motor Control

| Command | Richmat | OKIN | Description |
|---------|---------|------|-------------|
| STOP | `0x6E` | `0x00000000` | Global release |
| Head up / down | `0x24` / `0x25` | `0x00000001` / `0x00000002` | Selector 1 on secondary |
| Foot up / down | `0x26` / `0x27` | `0x00000004` / `0x00000008` | |
| Combined (dual) up / down | `0x29` / `0x2A` | `0x00000005` / `0x0000000A` | Back and legs together |
| Tilt up / down | `0x3F` / `0x40` | `0x00000010` / `0x00000020` | |
| Lumbar up / down | `0x41` / `0x42` | `0x00000040` / `0x00000080` | |
| Altitude head tilt up / down | `0x41` / `0x42` | none | Richmat only |
| Altitude full tilt up / down | `0x3F` / `0x40` | none | Richmat only |

### Presets

| Command | Richmat | OKIN |
|---------|---------|------|
| Flat | `0x31` | `0x08000000` |
| Zero-G | `0x45` | `0x00001000` |
| Anti-Snore | `0x46` | `0x00008000` |
| TV | `0x58` | `0x00004000` |
| Lounge (and Lucid Premium **Read**) | `0x59` | `0x00002000` |

### Memory

| Command | Richmat | OKIN |
|---------|---------|------|
| Recall 1 / 2 | `0x2E` / `0x2F` | `0x00010000` / `0x00040000` |
| Save 1 / 2 | `0x2B` / `0x2C` | `0x00010000` / `0x80040000` |
| Save 1 on a `Smartbed238` name | `0x2B` | `0x80010000` |

### Massage

| Command | Richmat | OKIN |
|---------|---------|------|
| Head massage | `0x4C` | `0x00000800` |
| Foot massage | `0x4E` | `0x00000400` |
| Wave mode | `0x48` | `0x10000000` |
| Massage off | `0x47` | none |
| Timer 10 / 20 / 30 min | `0x5F` / `0x63` / `0x61` | none |
| Timer step | none | `0x00000200` |

### Lights

| Command | Richmat | OKIN |
|---------|---------|------|
| Light toggle | `0x3C` | `0x00020000` |

### Clock and Alarm Frames

| Frame | OKIN legacy / custom | OKIN new |
|-------|----------------------|----------|
| Clock | `e7 80 01 (year − 1900) (month − 1) day hour minute second` + complement checksum, three writes | `07 04 year month day weekday hour minute second` (year low byte, Sunday = 0), one write |
| Alarm | `ed 80 03 hour minute repeats type` + eight zeros + complement checksum, three writes | `07 05 days (type − 12) hour minute 00 (days > 0) 00`, one write |
| Clear alarm | Alarm frame with zero time, repeats and type | Same; type encodes as `f4` |
| Status query | none | `00 b0` after light and massage operations |

| Alarm choice | Type |
|--------------|------|
| Zero-G | 13 |
| Lounge | 14 |
| TV | 15 |
| Anti-Snore | 16 |
| Memory 1 | 17 |
| Memory 2 | 18 |

`repeats` always sets bit 0, plus bit 1 (Monday) through bit 7 (Sunday) for each
selected weekday; with no weekdays it sets only the next occurrence's day. The
new transport's `days` keeps bits 1-6 and moves Sunday to bit 0.

## Two-address split-head routing

Home Assistant selects physical targets explicitly, rather than importing the
apps' persisted `ActiveBed` selection and `motorSwapped` UI state. Configure each
physical bed's app/model/primary role first. Use the child device IDs as the main
and partner targets. The apps do not establish synchronized physical motion.

For a supported main **Both/Dual** control and an inactive partner's **Legs**,
use this parallel action sequence. The existing simultaneous-movement action
works with any controller that declares that capability, despite its historic
`linak_` name. Replace the two device-ID placeholders with your child IDs.

```yaml
parallel:
  - action: adjustable_bed.linak_move_simultaneously
    data:
      device_id: YOUR_MAIN_DEVICE_ID
      first_motor: back
      first_direction: up
      second_motor: legs
      second_direction: up
      duration_ms: 1000
  - action: adjustable_bed.timed_move
    data:
      device_id: YOUR_PARTNER_DEVICE_ID
      motor: legs
      direction: up
      duration_ms: 1000
```

Choose `down` for both direction fields to lower them. Each operation retains
its own physical command lock and cancellation-safe STOP. The main receives its
combined command, while the partner receives foot movement, rather than sending
the main's combined command to both beds.

| App operation | Explicit Home Assistant targets |
|---------------|----------------------------------|
| Selected-side head movement | `timed_move`, motor `back`, main child only |
| Foot movement shared with inactive partner | `timed_move`, motor `legs`, both child IDs |
| Both/Dual movement with partner foot | Parallel sequence above |
| STOP/release | `stop_all`, both child IDs or paired parent |
| Position preset | Press the corresponding preset buttons on both children; memory recall can use `goto_preset` on the paired parent |
| Save memory | `save_preset` on the selected child only; Lucid Good Life uses its **Save Memory 2** button on that child |
| Partner foot massage | Press the foot-massage action on both children |

There are two exact Good Life exceptions:

- Malouf's **All** label has no inactive partner remap, so run only the main
  combined action.
- Lucid's **All** on Richmat uses the parallel sequence above.

Lucid's Good Life **All** with an OKIN main has no main write endpoint even
though the app can move the inactive partner's foot; that partial combined route
is excluded for safety. Standalone head/foot control remains available. Shared
app UI light state and side-selection persistence are application behavior, not
inferred controller feedback or a physical-side proof.

## Clock and alarms

Use `adjustable_bed.malouf_set_alarm` to set or clear an alarm. The selected
model must expose the app's alarm UI, and the connected transport must be OKIN.
Supported choices are Zero-G, Lounge, TV, Anti-Snore, Memory 1, and Memory 2,
subject to the model's memory capacity. An alarm choice can be available even
when the same manual preset is absent.

- Time uses Home Assistant's configured local time zone and minute precision.
- Selected weekdays create a repeating alarm. An empty weekday list selects the
  next occurrence of that local time, using the app's one-shot weekday encoding.
- Clock synchronization runs immediately before programming an enabled alarm.
  `adjustable_bed.sync_clock` (or the older `malouf_sync_clock`) also permits
  explicit clock synchronization. Connecting alone never writes the clock.
- Legacy/custom clock and alarm frames use complement checksums and three
  writes; new frames use one write, the artifact's year/month/weekday encoding,
  and alarm type offset.
- Clearing an alarm preserves the new transport's `f4` encoded type field rather
  than inventing a different command.
- Both actions validate every selected physical bed before any write and use
  the coordinator's serialized configuration path. An active movement is not
  cancelled to change an alarm.

See [action examples](../SERVICES.md#malouf-base--lucid-base-clock-and-alarm).

## Notifications

Notification parsing preserves signed bytes and exact length/offset guards; it
does not infer angles or claim position feedback.

| Transport | Accepted frames | Massage time | Light status |
|-----------|-----------------|--------------|--------------|
| OKIN legacy | Length 10, 16 or 20 only | Low nibble of byte 8 / 14 / 19; 1-3 means 10-30 minutes | Signed byte 7 / 13 / 18, shifted right by 6 |
| OKIN custom | Any | Signed byte 10 × 10 minutes | None |
| OKIN new | Byte 1 = `0x0B` | Signed byte 4: above 4 = 30, above 2 = 20, above 0 = 10 minutes | On when byte 9 or 13 is `1` |

Light state feedback is used on OKIN legacy and OKIN new; any nonzero status
means on. OKIN massage models add a massage-remaining sensor in minutes.

## Command Timing

- Movement sends an immediate command and refreshes every 150 ms, then sends the
  protocol STOP after the app's 150 ms release delay. Cancellation cannot
  suppress cleanup.
- Presets follow the per-transport policy in [Transport contracts](#transport-contracts).
- Richmat memory programming sends once.
- OKIN legacy/custom saves use 85 delayed writes at 150 ms; new saves use 55
  delayed writes at 100 ms. These save routes have no terminal STOP endpoint in
  the apps.
- The observed Smartbed238 name selects the artifact's special slot-1 save value.
- The new OKIN transport sends the raw status query `00 b0` after the app's
  lighting and massage operations. Other transports do not receive that query.

## Notes

### Hardware validation

The APKs establish command construction, app reachability, timing and parsing.
Physical motion directions, firmware acceptance and app/remote coexistence still
need reports from real users after a beta or release. No maintainer hardware is
required to complete the artifact-derived implementation.

### Analysis provenance

- The evidence is the accepted APK Protocol Audit cluster007 reports for Malouf
  Base 2.4.3 (`com.malouf.bedbase`) and Lucid Base 1.3.3 (`com.lucid.bedbase`).
- The [discovery dispositions](../apk-analysis/dispositions/row023-malouf-lucid.md)
  account for the complete reachable behavior and exclusions.
