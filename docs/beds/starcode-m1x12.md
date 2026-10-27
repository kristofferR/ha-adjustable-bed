# Adjustable Comfort M1X12 app

The **Adjustable Comfort M1X12 app** is an explicit Home Assistant bed profile
for the CB25, F23 and kneading layouts. Nordic UART, manufacturer, firmware
text, the advertised ELEVATE name and group membership do not select this
profile. Existing AdjustableM5X5 and DewertOkin ELEVATE entries keep their
current behavior until the user reconfigures them.

This implementation follows accepted artifact evidence, including the frozen
report SHA-256 `ed4d010495b70c6ceb31ef7c2f896b872e67b95b14e44c6f8844bc9f46ff6ae1`.
The full 970-ID mapping, including all exclusions, is in the
[M1X12 implementation ledger](starcode-m1x12-implementation-ledger.json).
Hardware operation remains unverified. Real-user checks are deferred until a
beta or release.

## Configuration and groups

Choose **Adjustable Comfort M1X12 app** from the bed list, enter the original
Bluetooth name and select CB25, F23 or kneading. The name selector is
case-insensitive and checks `STAR254205` / `STAR255401` for F23 and
`STAR255402` / `STAR255403` for kneading before generic `STAR25`. The selected
app/profile is still required; a name or shared BLE service cannot change the
entry to M1X12.

An M1X12 main entry can link up to two independent ELEVATE entries. Each lift
must be explicitly reconfigured to the **Adjustable Comfort M1X12 ELEVATE**
variant first. The group form rejects a generic ELEVATE entry with a request to
reconfigure it. Linking leaves the other entry's configuration, controller,
device ID and associations untouched. The M1X12 lift group is not a paired
left/right bed. Existing AdjustableM5X5 groups retain their three-lift limit.
Profile and lift ownership stay with one physical side of a two-address pair.

## Connection and version state

The main profile requires Nordic UART Service
`6e400001-b5a3-f393-e0a9-e50e24dcca9e`, TX/write
`6e400002-b5a3-f393-e0a9-e50e24dcca9e`, RX/notify
`6e400003-b5a3-f393-e0a9-e50e24dcca9e`, Device Information Service
`0000180a-0000-1000-8000-00805f9b34fb`, and readable Software Revision
`00002a28-0000-1000-8000-00805f9b34fb`. A missing required service or
characteristic prevents readiness. The 2A28 value read has a five-second
bound. Nonempty bytes become the firmware state one byte at a time with no
UTF-8 decoding or trimming. Empty data or a caught read error leaves the state
unknown and does not block the otherwise valid session. A result from a stale
BLE session is discarded.

The main profile reads optional Manufacturer Name `00002a29-0000-1000-8000-00805f9b34fb`
with a one-second bound. Only the exact raw string `star`, compared
case-insensitively, selects S framing. Missing, unreadable or other values
select C framing. The ELEVATE profile requires and reads 2A28, records its
version state the same way, recognizes whether 2A29 exists but does not read it,
and always uses S framing. Firmware contents never gate capabilities or select
a model.

For the main controller, startup reads 2A28, subscribes to RX, reads optional
2A29, then sends the S keep-open frame only for the `star` selector. F23 and
kneading then send their clock frame before the status query. ELEVATE reads
2A28, subscribes to RX, and follows its existing required initialization,
including the accepted wake frame. Disconnect and subscription replacement
invalidate pending state and queued work.

## Commands and timing

Normal S frames are `5a 01` plus a four-byte big-endian key and `a5`. Normal C
frames use `05 02`, the same key order, and a trailing `00`. Extended S/C,
long C-light, position and query frames are implemented by the target codec.
Accepted literal packets, including unsigned high-bit keys, are in the
[151-vector fixture](../../tests/fixtures/starcode_m1x12_vectors.json); all 165
accepted command rows run through the M1X12 controller in focused tests.

The main controller exposes movement for raw Parts 1, 2, 4, 8 and 16, plus the
accepted Part 1+2 union. It does not assign physical names to Parts 8 or 16.
Part feedback uses the accepted byte mapping and clamps values to 0–100%:
Parts 1, 2, 4 and 8 use bytes 4, 6, 8 and 10; Parts 16 and 32 use bytes 5 and
7. These appear as separately named Part state sensors. The notification's
motor-stopped flag is byte 17 equal to zero. No generic degree-position sliders
or invented physical axes are exposed.

Movement and held massage wave/intensity controls refresh at 100 ms. The first
refresh is delayed by 100 ms, and busy ticks are skipped. The Lovelace card
uses each entity's typed `held_control` metadata and invokes the existing
bounded `adjustable_bed.hold_control` service once, for at most 60 seconds. A
pointer/keyboard release, STOP, or card teardown routes STOP through the owning
device and paired side. The controller also sends its protocol STOP after
cancellation, failure, replacement or expiry, using a fresh cancellation
event. Finite app actions keep their accepted repeat counts and cleanup frames.

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
  keys. Part state is not mapped to standard angle sensors.

ELEVATE keeps the existing two-actuator surface plus the combined action. Its
three covers publish the same bounded hold metadata, with paired-side ownership
preserved. It does not gain massage, light, preset or model controls.

The native card includes the Part covers, read-only state and held massage
actions. Translation files and the shipped card bundle are updated with the
integration.

## Scope and validation

Nordic DFU transfer/bootloader, cloud/account services, Wi-Fi provisioning and
network administration remain excluded at the accepted source rows. Normal
2A28 version state and ordinary BLE session readiness remain implemented.
The machine-local accepted report and comparison are sealed; this task does
not reopen the APK or create a new analysis claim. The implementation ledger
preserves all 126 accepted exclusions with their original evidence and reasons.

Focused validation covers the 165 command rows, 151 literal packet vectors,
notification/parser guards, startup ordering and version-read failures,
explicit ELEVATE selection, app profile capabilities, group validation,
paired-side ownership, card hold/release, and actual cover/button/service STOP
paths. Full-suite scheduling and independent conformance review belong to the
root task owner.
