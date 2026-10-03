# FSM Relax app profile

Select **FSM Relax app (explicit chair/bed profile)** for devices operated by
`com.limoss.fsmrelax` 1.9 (20). This profile is verified against the Android
artifact, with physical hardware unverified. Existing Limoss/Stawett entries keep
their existing controller and settings. Shared advertisements and FFE0 services
cannot identify which app layout a device uses. The exact case-sensitive lowercase
`limoss` name route adds an ambiguous candidate, requiring explicit selection.
The focused chooser also applies when that candidate advertises FFE0. After
profile selection, setup uses normal connection verification when available;
it does not request an OS bond or enter a pairing step for this profile.
The source also checks complete raw scan-record text at an index greater than
zero and rejects null names; HA does not expose that complete Android record,
so it is never reconstructed from unrelated advertisement fields.

## Configuration and controls

Choose the app's chair or bed layout explicitly. Chair is the app default. The
bed layout has separate optional light and massage settings. Four reversal flags
are local configuration and become four unchanged 0/1 bytes in held controls,
release and calibration. Vibration count, versions and serial never select a
layout or enable a feature. Layout labels describe the app's icons; physical
wiring is unverified.

The capability response reports 2/4/6/8 keys, with any other byte falling back to 8.
Half the key count selects 1–4 raw memory motors. Memory count is unsigned
big-endian 16-bit; HA exposes up to eight device-local slots. Valid capabilities
enable controls immediately. Optional hardware/software queries cannot revoke
those capabilities on timeout.

Each available app action has a native button and appears in the card's utility
section. The exact source tables select the buttons, including asymmetric tables
where light replaces a combined direction. No firmware Flat preset, physical-axis
slider, six-zone massage toggle, light on/off state, RGB, brightness, or timer is
inferred. Use `adjustable_bed.hold_control` to specify a hold duration:

```yaml
action: adjustable_bed.hold_control
data:
  device_id: YOUR_DEVICE_ID
  control: command_12
  duration: 1.2
```

Available `command_XX` names appear in protocol diagnostics as `held_controls`.
The app's icons name12/13 back or chair footrest,22/23 legs or chair back,
32/33 tilt,50/51 combined movement,52/53 elevation,54/55 all regions,
60–65 massage plus/minus and70 underbed-light control. These are intended app
labels, not verified hardware semantics. Light/massage controls are held actions
with no invented boolean or measured state.

## Local memories and calibration

Save Memory 1–8 reads each reported raw motor in index order, issuing a new query
immediately after the preceding expected reply. It atomically stores the complete
set in a physical-address-specific HA storage record, retained across combine
and unpair ownership changes and removed only after its final entry is removed.
Within one HA entry and physical address, live and cached offline controllers
share current saved slots, names, capabilities and serial data. Reconnecting or
replacing that target does not leave recall preflight with a stale slot snapshot.
Different addresses and entry owners retain separate runtime models; profile
settings remain controller-local. Ownership transfers load the retained physical
store, and final removal clears its cached models as well as the stored record.
Signed 32-bit values have no
known physical units, scaling, angle or percentage. Slots map to local groups 0–7;
the slot number is never sent over BLE. An unsolicited response updates raw
diagnostics but never saves a slot.

Memory buttons and `goto_preset` recall stored targets once per available motor.
Motor zero must exist; absent later motor rows are skipped. The default button
hold is the configured motor pulse count multiplied by 60 ms. This is a local HA
gesture policy, not an app-proven autonomous preset duration or arrival deadline.
Use `adjustable_bed.goto_preset` with `preset:1..8` and an explicit `duration`
in seconds to choose that policy. A normal release follows remaining
queued targets. Cancellation preempts unsent targets and still attempts all five
memory-release frames.

`goto_preset`, with or without `duration`, validates every target's stored
motor-zero row, signed raw values and quarantine before any bed moves. Valid persisted targets can be
validated while offline; execution still requires a fresh live capability
subscription. A connected controller without that readiness fails preflight.

There is no proven echoed request ID or counter correlation. Local expected-opcode
and connection guards do **not** guarantee a reply is fresh. After timeout,
cancellation or an uncertain memory write, HA retains prior slots and quarantines
memory operations until the connection is replaced and a fresh subscription and
capability response are obtained. Merely resubscribing on the same connection does
not clear quarantine. A device-retained reply after reconnect, or a delayed
byte-identical reply during a new same-opcode request, may still be indistinguishable.
Acknowledgement 04 is observed only and cannot prove physical arrival.

Options expose exactly eight local memory names. A blank field resets that slot
to M1–M8. Editing/resetting names never writes BLE. Names are entry options and
the capability snapshot is entry data; raw targets and the serial are app state
for the physical bed. All survive HA restart/controller replacement, and removing
the last entry that owns the bed removes its app state. Identical capability
snapshots and serial observations skip storage writes. A memory save persists
atomically; a failed write retains the previous value. Fresh live capability
readiness is required on each connection.
Unsolicited signed serial 06 is remembered, without inventing a serial query.

All three FSM Relax action forms expose `side:both/left/right`. A child device
retains its physical side; a paired parent defaults to both unless a side is selected.

`adjustable_bed.fsm_relax_calibrate` requires `confirmed:true`. It sends one 05
frame with all four configured reversal flags and never automatically retries.
A failed write does not prove hardware did nothing. Response 05 records an observed
calibration notification, without claiming measured calibration success.

## BLE and lifecycle

A link drop fails pending queries with a connection error so initialization can
use the coordinator's remaining retries. Explicit caller cancellation still
propagates as cancellation. An offline controller without a capability snapshot
has incomplete entity discovery. A loaded entry's first persisted capability response
requests the existing deferred reload after link release, including the parent of a pair,
so native actions and memories appear without a manual reload. Initial setup builds
its platforms from that first response without scheduling an unnecessary reload.

The exact service is `0000ffe0-0000-1000-8000-00805f9b34fb`, with one write/notify
role `0000ffe1-0000-1000-8000-00805f9b34fb`. Every write uses `response=False`, even
when the characteristic advertises only generic write properties. Source code does
not inspect those property bits; HA reports actual transport failures instead of
inventing a profile rejection. Subscription uses Bleak, without guessed descriptor
UUIDs, GATT reads, MTU/priority changes, authentication or bond commands.

A five-byte body is framed as AA/body/low-eight-bit counter/additive sum, encrypted
as two big-endian 32-bit words using 16 TEA rounds and embedded key
`55551494 74385555 55551494 74385555`. The outer frame is DD/encrypted 8/additive
sum. Each attempted write gets a fresh counter, wrapping 255→0. Per-device process
state retains the counter across controller replacement/reconnect; a cold HA
process starts at zero. Devices have separate counters and memory-operation locks. Pure encryption
and decryption reuse the separately vector-proven existing codec; high-level
Limoss timing, normalization, capabilities and memory behavior are not inherited.

Capability/HW/SW requests are 02/00/01 followed by `00 00 00 03`. Capability retries
occur at nominal 1000 ms offsets within a bounded four-second HA setup window.
Optional stages start 120 ms after the preceding response, take the command lock
only for each write and wait outside that lock. Position-save requests 10/20/30/40
have four zero bytes, one attempt per motor, and a bounded one-second HA response
wait. The timeout is a safety bound, not an artifact-proven success/failure deadline.

Held controls start at 60 ms and repeat at nominal 60 ms offsets. Release sends five
FF frames with reversals; recall release sends five 03/zero frames. All cleanup
attempts use fresh cancellation events and one monotonic release origin, survive
repeated cancellation and attempt remaining frames after an earlier write failure.
Writes remain serialized. Late BLE writes are attempted when possible, so nominal
deadlines are not a promise of physical timing.

Notifications are buffered per controller with bounded storage, fragment/coalesced
support, header and both checksum validation. Raw motor and serial fields are
signed big-endian 32-bit. Version strings preserve signed-byte concatenation:
nonnegative first byte, signed second byte, dot, optional nonnegative third/fourth
bytes. `01 80 02 ff` therefore becomes `1-128.2`. Unknown opcodes are ignored.
Old connection callbacks cannot overwrite the current session. Entry-owned
background query/metadata tasks stop on teardown.

## Evidence and dispositions

[The complete 315-row disposition index](../apk-analysis/dispositions/075-fsm-relax.md)
records 164 implemented items, 5 already implemented pure codec items and 146
explicit exclusions. Tests cover all 43 frozen wire vectors, all 20 exact layout
tables, every key-count byte, signed/raw parsing, GATT role boundaries, persistence,
entity/action exposure, cancellation, timing and reply-correlation limits.

Physical GATT compatibility, wiring, raw units, calibration outcome, optional
light/massage effects and real-device timing remain deferred validation for users
after a beta or release. Static implementation is complete only after its independent
implementation audit and integration PR converge; analysis acceptance alone does
not mark implementation merged.
