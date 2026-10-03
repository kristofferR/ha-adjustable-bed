# Malouf Base / Lucid Base app profiles

**Status:** Artifact-verified, hardware unverified. This opt-in controller is
separate from the existing tested Malouf/OKIN and generic Richmat controllers.

The evidence is the accepted APK Protocol Audit cluster007 reports for Malouf
Base 2.4.3 (`com.malouf.bedbase`) and Lucid Base 1.3.3
(`com.lucid.bedbase`). The [discovery dispositions](../apk-analysis/dispositions/row023-malouf-lucid.md)
account for the complete reachable behavior and exclusions.

## Setup

Select **Malouf Base / Lucid Base app** under Malouf/Lucid, then choose the
Android app and exact model used with your bed. A retail model does not prove
its Bluetooth protocol. Existing entries retain their controller and settings.

Choose the physical primary/secondary role used in the app. Home Assistant's
Left/Right names do not prove that role. When combining two Bluetooth addresses,
configure each bed separately before combining them. Single-address pairing is
not offered: the app's secondary selector covers only some commands, while STOP
and other actions remain global.

Automatic transport selection uses the observed Bluetooth name and connected
GATT services. It rejects ambiguous or incomplete layouts. An explicit transport
override must still match a complete writable service/characteristic layout.
Shared UART and custom service identifiers never select an app or retail model.

## Models and controls

The supported model constructors include Altitude, E450, E455, Forte, Good Life
Base, Good Life Premier Base, Good Life Pro Base, L300, L600, M455, M550, M555,
Premium, S655, S750, and S755. Some are available only through the apps' persisted
model selection, so the selected app remains significant for these models too.
Setup selects the app first, then offers its packaged model picker: 14 choices
for Malouf Base and L300, L600, and Premium for Lucid Base. Options retain an
existing persisted-only model for that same app. Changing apps refreshes the
model choices before saving; it does not carry a stored-only model to another app.

Controls follow the selected constructor and its reachable app routes. These
include back/legs, supported combined movement, tilt/lumbar, Altitude head/full
tilt, Flat, available presets, zero to two memory slots, massage, wave mode,
under-bed lighting, and alarms. A constructor label alone never enables a command
that has no endpoint in the selected app and transport.

- Lucid Premium on an OKIN transport exposes **Read**. Its command shares the
  lounge value. Malouf's uppercase READ route has no write endpoint.
- Lucid Good Life Zero-G and Anti-Snore routes work only on Richmat. Malouf
  normalizes those app labels and supports both command families.
- Good Life combined movement has no OKIN endpoint and is suppressed there.
- Lucid Good Life models expose **Save Memory 2** for the shared save route
  reached by holding either Oz control. Those models declare zero recall slots,
  so this button does not enable memory recall or generic memory programming.
- Richmat massage timers are direct 10/20/30-minute controls where reachable.
  OKIN has a timer-step command rather than direct duration selection.
- Notification state reports massage time and, where supported, light status.
  The apps provide no motor-position, light-brightness, or color feedback.

For a feedback light whose state is still unknown, use the card's light toggle
or Home Assistant's `light.toggle` action. Both send the native toggle without
guessing the current state. Explicit `light.turn_on` and `light.turn_off` require
known feedback.

## Transport contracts

All characteristic writes use Android's numeric mode 2, `WRITE_TYPE_DEFAULT`,
which requires acknowledgement (`response=True`). A bounded audit addendum
corrects the older reports' descriptive no-response wording; their numeric
artifact evidence remains unchanged.

| Transport | Command frame | Preset policy |
|-----------|---------------|---------------|
| Richmat single | One opcode byte | One write, then `6e` STOP |
| Richmat framed | `6e 01 selector opcode checksum` | One write, no preset STOP |
| OKIN legacy | `e6 fe 16` + little-endian command + zero + complement checksum | Three writes, no preset STOP |
| OKIN custom | `04 02` + big-endian command + four zeros | Three writes, then zero STOP |
| OKIN new | `05 02` + big-endian command + two zeros | One write, then zero STOP |

Richmat framed selector 1 applies only to secondary head up/down, head massage,
Flat, Zero-G and Anti-Snore. Foot, combined movement, memory, timer, lighting,
and STOP use selector 0. The controller never extrapolates side selection to
unsupported actions.

Movement sends an immediate command and refreshes every 150 ms, then sends the
protocol STOP after the app's 150 ms release delay. Cancellation cannot suppress
cleanup. Richmat memory programming sends once. OKIN legacy/custom saves use 85
delayed writes at 150 ms; new saves use 55 delayed writes at 100 ms. These save
routes have no terminal STOP endpoint in the apps. The observed Smartbed238
name selects the artifact's special slot-1 save value.

The new OKIN transport sends the raw status query `00 b0` after the app's
lighting and massage operations. Other transports do not receive that query.
Notification parsing preserves signed bytes and exact length/offset guards;
it does not infer angles or claim position feedback.

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

There are two exact Good Life exceptions. Malouf's **All** label has no inactive
partner remap, so run only the main combined action. Lucid's **All** on Richmat
uses the parallel sequence above. Lucid's Good Life **All** with an OKIN main has
no main write endpoint even though the app can move the inactive partner's foot;
that partial combined route is excluded for safety. Standalone head/foot control
remains available. Shared app UI light state and side-selection persistence are
application behavior, not inferred controller feedback or a physical-side proof.

## Clock and alarms

Use `adjustable_bed.malouf_set_alarm` to set or clear an alarm. The selected
model must expose the app's alarm UI, and the connected transport must be OKIN.
Supported choices are Zero-G, Lounge, TV, Anti-Snore, Memory 1, and Memory 2,
subject to the model's memory capacity. An alarm choice can be available even
when the same manual preset is absent.

Time uses Home Assistant's configured local time zone and minute precision.
Selected weekdays create a repeating alarm. An empty weekday list selects the
next occurrence of that local time, using the app's one-shot weekday encoding.
Clock synchronization runs immediately before programming an enabled alarm.
`adjustable_bed.sync_clock` (or the older `malouf_sync_clock`) also permits
explicit clock synchronization.
Connecting alone never writes the clock.

Legacy/custom clock and alarm frames use complement checksums and three writes;
new frames use one write, the artifact's year/month/weekday encoding, and alarm
type offset. Clearing an alarm preserves the new transport's `f4` encoded type
field rather than inventing a different command.

Both actions validate every selected physical bed before any write and use the
coordinator's serialized configuration path. An active movement is not cancelled
to change an alarm. See [action examples](../SERVICES.md#malouf-base--lucid-base-clock-and-alarm).

## Hardware validation

The APKs establish command construction, app reachability, timing and parsing.
Physical motion directions, firmware acceptance and app/remote coexistence still
need reports from real users after a beta or release. No maintainer hardware is
required to complete the artifact-derived implementation.
