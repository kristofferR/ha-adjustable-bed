# Adjustable Comfort M1X12 app

**Status:** ❓ Needs testing (artifact-verified, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

The **Adjustable Comfort M1X12 app** is an explicit Home Assistant bed profile
for the CB25, F23 and kneading layouts. Nordic UART, manufacturer, firmware
text, the advertised ELEVATE name and group membership do not select this
profile. Existing AdjustableM5X5 and DewertOkin ELEVATE entries keep their
current behavior until the user reconfigures them.

## Known Models

- StarCode `STAR25*` beds operated with Adjustable Comfort M1X12, in three
  layouts: CB25, F23 and kneading (see [Configuration and groups](#configuration-and-groups))
- Up to two [DewertOkin ELEVATE](okin-5a.md#dewertokin-elevate) lifts per main, configured as
  the **Adjustable Comfort M1X12 ELEVATE** variant

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Adjustable Comfort M1X12](https://play.google.com/store/apps/details?id=com.starcode.adjustablem1x12) 1.1.3 | `com.starcode.adjustablem1x12` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Raw Parts 1, 2, 4, 8 and 16, plus the Part 1+2 union |
| Position Feedback | ⚠️ Read-only Part percentages (no degree sliders or physical axis names) |
| Presets | ✅ Flat, TV, zero gravity, anti-snore, lounge |
| Memory Presets | ✅ Memory 1/2 recall and save, raw MemoryType 8 recall, reset |
| Massage | ✅ Toggle/off, 10/20/30-minute timer, held wave and head/foot/both intensity |
| Lights | ✅ On/off/cycle, model-gated light modes 0/1, brightness 1–6 |
| Alarm, EQ, USB, sonic and kneading state | ⚠️ Read-only |
| ELEVATE lifts | ✅ Up to two explicitly configured M1X12 ELEVATE entries |
| Hold until release | ✅ ([renewable](../SERVICES.md#renewable-holds) `timed_move` and `hold_control`: 100 ms refresh, then STOP) |

## Protocol Details

**Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e` (Nordic UART)
**Write Characteristic:** `6e400002-b5a3-f393-e0a9-e50e24dcca9e` (TX/write)
**Notify Characteristic:** `6e400003-b5a3-f393-e0a9-e50e24dcca9e` (RX/notify)
**Format:** Normal S frames `5a 01` + four-byte big-endian key + `a5`; normal C frames `05 02` + the same key order + trailing `00`

The main profile also requires Device Information Service
`0000180a-0000-1000-8000-00805f9b34fb` and readable Software Revision
`00002a28-0000-1000-8000-00805f9b34fb`. It reads optional Manufacturer Name
`00002a29-0000-1000-8000-00805f9b34fb`.

### Packet Format

| Builder | C (legacy) | S (Star) |
|---|---|---|
| Normal key | `05 02 BE32(key) 00` | `5a 01 BE32(key) a5` |
| Extended value | `04 e0 command value 00 00` | `5a e0 04 command value 00 00 a5` |
| Long C light | `08 02 00 00 00 00 BE32(key)` | n/a |
| Part position | `03 f0 part target 00` | `5a f0 03 part target 00 a5` |
| Query | `00 b0` | `5a b0 00 a5` |
| Keep-open | n/a | `5a 0b 00 a5` |
| Clock | n/a | `5a 14 07 year month day weekday hour minute second a5` |

- Extended S/C, long C-light, position and query frames are implemented by the
  target codec.
- Accepted literal packets, including unsigned high-bit keys, are in the
  [151-vector fixture](../../tests/fixtures/starcode_m1x12_vectors.json); all
  165 accepted command rows run through the M1X12 controller in focused tests.
- The clock builder matches the app, including the shipped caller's second
  subtraction of 2000 from the year and the weekday-before-time field order.
- Every write uses write without response.

### Dialect selection

- The main profile reads optional 2A29 with a one-second bound. Only the exact
  raw string `star`, compared case-insensitively, selects S framing. Missing,
  unreadable or other values select C framing.
- The ELEVATE profile requires and reads 2A28, records its version state the
  same way, recognizes whether 2A29 exists but does not read it, and always uses
  S framing.
- Firmware contents never gate capabilities or select a model.

## Configuration and groups

Choose **Adjustable Comfort M1X12 app** from the bed list, enter the original
Bluetooth name and select CB25, F23 or kneading.

| Name prefix, checked first to last | Layout |
|---|---|
| `STAR254205`, `STAR255401` | F23 |
| `STAR255402`, `STAR255403` | Kneading |
| Generic `STAR25` | CB25 |

- The name selector is case-insensitive and checks the F23 and kneading
  prefixes before generic `STAR25`.
- The selected app/profile is still required; a name or shared BLE service
  cannot change the entry to M1X12.

### ELEVATE lift group

An M1X12 main entry can link up to two independent ELEVATE entries.

- Each lift must be explicitly reconfigured to the **Adjustable Comfort M1X12
  ELEVATE** variant first. The group form rejects a generic ELEVATE entry with a
  request to reconfigure it.
- Linking leaves the other entry's configuration, controller, device ID and
  associations untouched.
- The M1X12 lift group is not a paired left/right bed. Existing AdjustableM5X5
  groups retain their three-lift limit.
- Profile and lift ownership stay with one physical side of a two-address pair.

### Home Assistant setup

Choose the **StarCode apps** row, then **Adjustable Comfort M1X12 app**, then enter the exact Bluetooth name and choose CB25, F23 or kneading. Specific F23 and kneading prefixes take precedence over generic `STAR25`; the app identity is not inferred from Nordic UART, manufacturer, firmware or the name alone. Existing AdjustableM5X5 entries retain their current controller and configuration.

An M1X12 main can include up to **two separately configured ELEVATE accessories**. Each ELEVATE entry must be explicitly reconfigured to **Adjustable Comfort M1X12 ELEVATE** before it can be linked. Linking never changes that entry. Existing ELEVATE defaults and AdjustableM5X5 groups keep their current behavior. These entries remain independent devices and do not become Left/Right paired beds. The M1X12 profile and accessory list belong to one physical side and cannot be changed from a shared two-address pair form.

The optional manufacturer read selects its normal command framing only inside the chosen M1X12 profile. The required Device Information 2A28 characteristic supplies the firmware version state; firmware text does not select capabilities.

## Connection and version state

- A missing required service or characteristic prevents readiness.
- The 2A28 value read has a five-second bound. Nonempty bytes become the
  firmware state one byte at a time with no UTF-8 decoding or trimming. Empty
  data or a caught read error leaves the state unknown and does not block the
  otherwise valid session. A result from a stale BLE session is discarded.

**Startup order:**

| Controller | Sequence |
|---|---|
| Main | Read 2A28, subscribe to RX, read optional 2A29, then send the S keep-open frame only for the `star` selector. F23 and kneading then send their clock frame before the status query. |
| ELEVATE | Read 2A28, subscribe to RX, and follow its existing required initialization, including the accepted wake frame. |

Disconnect and subscription replacement invalidate pending state and queued
work.

## Commands

Each action has a C key and an S key; the manufacturer-selected dialect picks
the key and frame. For example Part 1 up is `05 02 00 00 00 01 00` (C) or
`5a 01 03 10 30 00 a5` (S).

### Motor Control

| Command | C key | S key | Description |
|---|---|---|---|
| Part 1 up / down | `00000001` / `00000002` | `03103000` / `03103001` | Raw Part 1 |
| Part 2 up / down | `00000004` / `00000008` | `03103002` / `03103003` | Raw Part 2 |
| Part 4 up / down | `00000010` / `00000020` | `03103004` / `03103005` | Raw Part 4 |
| Part 8 up / down | `00000040` / `00000080` | `03103008` / `03103009` | Raw Part 8 |
| Part 16 up / down | n/a | `0310300a` / `0310300b` | Always S framing, even when the manufacturer selector chose C |
| Part 1+2 union up / down | `00000005` / `0000000a` | `0310300c` / `0310300d` | Accepted union |
| STOP | `00000000` | `0310300f` | Protocol STOP / neutral |
| Interrupt | `00000000` | `0310301f` | Interrupt |

### Presets

| Command | C key | S key |
|---|---|---|
| Flat | `08000000` | `03103010` |
| TV | `00004000` | `03103011` |
| Zero gravity | `00001000` | `03103013` |
| Anti-snore | `00008000` | `03103016` |
| Lounge | `00002000` | `03103017` |

### Memory

| Command | C key | S key |
|---|---|---|
| Memory 1 recall | `00010000` | `0310301a` |
| Memory 2 recall | `00040000` | `0310301b` |
| Raw MemoryType 8 recall | `00004000` | `03103018` |
| Save memory 1 | `08010000` | `03103094` |
| Save memory 2 | `08040000` | `03103095` |
| Save TV | `08004000` | `03103092` |
| Save zero gravity | `08001000` | `03103090` |
| Save lounge | `08002000` | `03103091` |
| Reset | `88000000` | `03103096` |

### Massage

| Command | C key | S key | Notes |
|---|---|---|---|
| Toggle | `00000100` | `0310305a` | |
| Off | `02000000` | `0310306f` | Also sent for timer 0 |
| Wave up / down | `10000000` / `04000000` | `03103058` / `03103059` | Held control |
| Head intensity up / down | `00000800` / `00800000` | `03103066` / `03103067` | Held control |
| Foot intensity up / down | `00000400` / `01000000` | `03103068` / `03103069` | Held control |
| Both intensity up / down | `00000c00` / `01800000` | n/a | Held control; no S-dialect packet |
| Timer 10/20/30 minutes | Extended command `7`, value 1/2/3 | Extended command `7`, value 1/2/3 | Manufacturer-selected framing for every profile |

C-dialect intensity controls keep the S packet family: they are sent as
`5a 01 BE32(C key) a5`.

### Lights

| Command | C | S | Notes |
|---|---|---|---|
| Light on / off | Long C light, key `00000040` / `00000080` | `03103073` / `03103074` | F23 and kneading always use S |
| Light cycle | `00040000` | `03103070` | F23 and kneading always use S |
| Brightness 1–6 | Extended command `0` | Extended command `0` | F23 and kneading always use S |
| Light mode 0 / 1, models `252201`, `254202`, `352201` | `00020004` | `03103079` / `0310307a` | Sent 35 times |
| Light mode 0 / 1, other or empty models | S `03103089` / `0310308a` | S `03103089` / `0310308a` | Mode 1 is followed by S STOP |
| Light mode, F23 and kneading | S `03103089` | S `03103089` | Followed by S STOP |

The model ID is the Bluetooth-name substring `[4:10]`, read only from names longer than 14 characters.

### Other

| Command | Frame |
|---|---|
| Status query | Query builder; F23 and kneading always use S |
| Keep-open | `5a 0b 00 a5`, only for the `star` selector |
| Clock | Clock builder, F23 and kneading before the status query |

## Command Timing

- Movement and held massage wave/intensity controls refresh at 100 ms. The first
  refresh is delayed by 100 ms, and busy ticks are skipped.
- The Lovelace card uses each entity's typed `held_control` metadata and invokes
  the existing bounded `adjustable_bed.hold_control` service once, for at most
  60 seconds. A pointer/keyboard release, STOP, or card teardown immediately
  routes STOP through the owning device and paired side.
- The controller also sends its protocol STOP after cancellation, failure,
  replacement or expiry, using a fresh cancellation event.
- Finite app actions keep their accepted repeat counts and cleanup frames:

| Action | Repeats | Cleanup |
|---|---|---|
| Presets and memory recall | 3 | STOP |
| Saves and reset | 55, after a STOP | None |
| Massage toggle / off | 2 | STOP |
| Light on / off / cycle (CB25) | 2 | STOP |
| Light on / off / cycle (F23, kneading) | 1 | S STOP |
| Brightness, massage timer | 1 | STOP in the frame's dialect |
| Single massage wave / intensity step | 1 | STOP |
| Light mode, special models | 35 | None |

## Position Feedback / State

Part feedback uses the accepted byte mapping and clamps values to 0–100%:

| Part | Byte |
|---|---|
| 1, 2, 4, 8 | 4, 6, 8, 10 |
| 16, 32 | 5, 7 |

- These appear as separately named Part state sensors. The main controller does
  not assign physical names to Parts 8 or 16.
- The notification's motor-stopped flag is byte 17 equal to zero.
- No generic degree-position sliders or invented physical axes are exposed.
  Part state is not mapped to standard angle sensors.

### Internal progress targets

The internal progress-target helper encodes Part selectors 0–4 and a target
byte. Stopped feedback advances an already populated internal queue; movement,
STOP and session teardown clear or invalidate it. The accepted app has no UI
enqueue/set-position entry point, so this helper is retained as internal
protocol behavior and is not presented as a Home Assistant control.

## App controls and reported state

The main profile exposes:

- Flat, TV, zero gravity, anti-snore, lounge, memory 1/2 recall, raw MemoryType
  8 recall, memory 1/2 save and reset.
- Per-Part movement, Part 1+2 union, interrupt, STOP and continuous held
  controls for wave and head/foot/both massage intensity.
- Massage toggle/off and 10/20/30-minute timer choices.
- Light on/off/cycle, model-gated light modes 0/1 and brightness 1–6. The
  three accepted model IDs are `252201`, `254202` and `352201`; other or empty
  models keep their distinct behavior. F23 and kneading use their accepted S
  lighting overrides.
- Read-only Part percentages, motor state, massage state, light state/RGB and
  sonic state. CB25 exposes its basic alarm state. F23 and kneading expose the
  advanced alarm, EQ and USB state; kneading additionally exposes kneading
  on/demo/mode/time state. These notifications do not imply setters that the
  app does not provide.
- One brightness number entity and stable `starcode_m1x12_*` entity translation
  keys.

ELEVATE keeps the existing two-actuator surface plus the combined action. Its
three covers publish the same bounded hold metadata, with paired-side ownership
preserved. It does not gain massage, light, preset or model controls.

The native card includes the Part covers, read-only state and held massage
actions. Translation files and the shipped card bundle are updated with the
integration.

## Notes

### Scope and validation

- Nordic DFU transfer/bootloader, cloud/account services, Wi-Fi provisioning
  and network administration remain excluded at the accepted source rows.
  Normal 2A28 version state and ordinary BLE session readiness remain
  implemented.
- The machine-local accepted report and comparison are sealed; this task does
  not reopen the APK or create a new analysis claim. The implementation ledger
  preserves all 126 accepted exclusions with their original evidence and
  reasons.
- Focused validation covers the 165 command rows, 151 literal packet vectors,
  notification/parser guards, startup ordering and version-read failures,
  explicit ELEVATE selection, app profile capabilities, group validation,
  paired-side ownership, card hold/release, and actual cover/button/service STOP
  paths. Full-suite scheduling and independent conformance review belong to the
  root task owner.
- Hardware operation remains unverified. Real-user checks are deferred until a
  beta or release.

### Analysis provenance

- This implementation follows accepted artifact evidence, including the frozen
  report SHA-256 `ed4d010495b70c6ceb31ef7c2f896b872e67b95b14e44c6f8844bc9f46ff6ae1`.
- The full 970-ID mapping, including all exclusions, is in the
  [M1X12 implementation ledger](starcode-m1x12-implementation-ledger.json).
