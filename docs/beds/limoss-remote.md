# Limoss Remote app profile

Select **Limoss Remote app** explicitly under Limoss, then choose bed or chair and
its local lamp/massage controls. This profile comes from the independently
accepted `com.limoss.limossremote` 7.1.8 (44) artifact. Hardware behavior remains
unverified. The existing generic Limoss selection retains its previous behavior.
A shared FFE0 service or device name cannot identify this app profile.

The receiver supplies key count, system/motor count, configuration and memory
capacity. Recognized system ranges select the app's bed/chair layout; the chosen
product supplies the fallback for an unknown system code. Unsupported key counts
use the source's eight-key fallback. Bed layouts have 2, 4, 6, 8, 10 or 12 keys;
chair layouts have 2, 4, 6 or 8. Configuration 1 selects the eight-key chair's
custom Alpha ordering. Every rendered lamp/massage combination is retained,
including blank cells and omitted combined/shift directions. Controls use literal
motor channels rather than assigning unproven physical axes or angle units.

Four reversal flags are independent local settings. Lamp and massage selections
change the available controls, not measured hardware state. Enabling a feature
changes the local layout. Disabling a previously selected lamp or massage feature
first sends ten source OFF commands, then saves the selection. Failed OFF writes
leave the saved selection unchanged. The settings action supports the same
transaction. For paired or multi-target service calls, every selected OFF burst
must finish before any feature selections are saved. A failure or cancellation
retains the previous local selections even if some hardware writes succeeded.
Entity reloads wait until the selected operations and any active sibling command
have released their command lanes. App artwork themes are retained as a local preference in diagnostics;
Home Assistant continues to use its own theme and does not copy app artwork.

## Controls and actions

Motor channels have up/down/stop covers where both directions occur in the
selected rendered table. Named buttons expose every rendered app action. A
button or cover activation holds its action for **one second**, a Home Assistant
policy separate from the app's refresh cadence. All actions on a physical receiver
share the global motor resource. STOP releases that receiver's active control.
Two-address pairs retain independent profiles, reversal flags, features and
memories per child. This profile has no single-address side selector.

`adjustable_bed.limoss_remote_hold_control` accepts one currently rendered control
and a duration from 0.1 to 60 seconds, with millisecond precision. Available names
are:

- `motor_1_up`, `motor_1_down` through `motor_4_up`, `motor_4_down`;
- `combined_up`, `combined_down`, `lift_up`, `lift_down`, `shift_up`, `shift_down`;
- `massage_back_plus`, `massage_back_minus`, `massage_foot_plus`,
  `massage_foot_minus`, `massage_both_plus`, `massage_both_minus`;
- `light`.

The live layout allowlist gates each action. A combined-down control is a held
command, not a flat preset. The app has no named flat, zero-gravity or TV preset,
position slider, massage intensity feedback, lamp ON/OFF feedback, synchronization,
PIN or native bond workflow. Light/massage OFF utility buttons send their source
ten-frame burst without an additional motor release.

Example:

```yaml
action: adjustable_bed.limoss_remote_hold_control
data:
  device_id: YOUR_DEVICE_ID
  control: motor_1_up
  duration: 0.5
```

`limoss_remote_calibrate` requires `confirmed: true`, a duration, and a
memory-capable receiver. It holds the source calibration operation and always
attempts its five calibration release frames once a command has been constructed.
A calibration reply is reported as **reply received**, not proof of physical
completion. `limoss_remote_features` accepts both `underbed_light` and `massage`
booleans. Services validate every selected physical target before writing to any.
Target a paired child device or supply `side: left`, `right` or `both` normally.

## Eight local memories

The device-reported capacity limits slots 1–8. These are app-local captured raw
positions, not firmware preset writes. Save buttons and `save_preset` query each
reported motor sequentially, then atomically persist the complete captured slot
for that physical address. The supported capture domain is one to four motors.
A failure, timeout or cancellation preserves the previous complete slot.
Unsupported capacity above eight or motor count above four is rejected before
sending a save/recall command, avoiding source array crashes and an unparsed
fifth-motor query.

Recall buttons and `goto_preset` hold a stored memory for one second. For an
explicit duration, use `limoss_remote_recall_memory` with `preset` and `duration`.
Recall requires a stored motor-1 row. Sparse retained rows for the other reported
motors are allowed and sent in motor order. Raw signed 32-bit values are preserved
bit for bit without inventing distance or angle units.

`limoss_remote_rename_memory` accepts `preset` and `name`. Names are local and may
be empty. Rename retains all captured positions and updates button labels without
reconnecting. Memory names and positions survive controller recreation, entry
reload, unpair/re-pair and integration restart through the physical target's
config data. Changing the selected protocol preserves the stored app memory data;
other protocols do not use it. No source-backed clear-memory action exists.

## Transport and timing

The source selects the first exact service
`0000ffe0-0000-1000-8000-00805f9b34fb`, then its first exact characteristic
`0000ffe1-0000-1000-8000-00805f9b34fb`. The selected characteristic must support
notification and a write property. Each actual write binds that selected object,
including after reconnect; unsubscribe uses the same object and owning client.
The app inherits the Android write mode without a proven override. This controller
uses acknowledged writes when `write` is available, otherwise the explicitly
advertised `write-without-response` property. This is a host transport policy,
not a claim about the artifact's inherited mode.

The native frame is ten bytes: `DD`, eight encrypted bytes and an outer sum.
Plaintext is `AA`, five command bytes, one low sequence byte and an inner sum.
The accepted native library proves 16-round, big-endian TEA arithmetic. The source
global sequence advances at logical construction, including packets whose later
write fails; every repeated command and release has a fresh sequence. Logical
batches are constructed together to preserve cross-receiver sequence ordering.
The Java signed-int wrap and low-byte behavior are retained.

The source's write pump is nominally 80 ms. The controller serializes ATT calls
and enforces at least 80 ms between write starts, waiting for each call to complete.
Each ATT call has a two-second host deadline; this is not an artifact timing claim.
Ordinary controls first poll at 80 ms and refresh at 80 ms; ending before the first
poll constructs no command and sends no release. Memory batches begin immediately
and repeat nominally every 300 ms, while their individual packets use the same
80 ms transport lane. Calibration starts immediately and repeats at 100 ms.
A requested duration limits refreshes; cleanup occurs outside that deadline.

Ordinary movement/recall cleanup attempts five `FF` commands with the four reversal
bytes. Calibration cleanup attempts five `03 00 00 00 00` commands. Cleanup uses
fresh cancellation events, bounded writes and shielding against repeated task
cancellation, and attempts all five frames even when an earlier release fails.
The first command error remains the reported error. Lamp and massage OFF operations
send ten `71` and `66` frames respectively with four zero bytes and no STOP tail.

After notification subscription, the information transaction requests `02`,
retries that capability query at one-second intervals, then requests hardware `00`
and software `01` in reply order. The host bounds this transaction to ten seconds.
Completed diagnostic fields survive later failures and reconstruction. Changed
capability snapshots refresh the offline layout and request an entity
reload after the link and paired command lanes are released. There are
no live Device Information Service reads or idle position queries in this profile.
An unsolicited `06` reply retains its signed serial value; there is no reachable
serial-query sender.

## Replies and state

Notifications may be fragmented or contain multiple frames. The receive path
finds `DD`, waits for ten bytes and decrypts the inner payload. The artifact does
not validate either checksum or the decrypted `AA`; the admitted parsing domain
preserves that behavior. The host keeps a bounded buffer per physical receiver,
clears it on reconnect, and never combines bytes from different receivers.

Hardware/software versions use the source signed-byte string concatenation.
Position replies `10`, `20`, `30`, `40` and serial `06` retain signed big-endian
32-bit values. Position sensors are explicitly **raw**, have no physical unit,
and do not create angle sliders or estimated bed positions. Only a matching active
save query can contribute to a local memory transaction. Idle or late position
replies may update raw diagnostics but cannot overwrite memories or issue queries.

Diagnostics expose raw capability fields, chosen product, exact layout, visible
opcodes, reversal flags, theme preference, local memories and the app sequence.
Reported information and acknowledgments never establish authentication, measured
lamp state, measured massage state or physical motion completion.

## Evidence and exclusions

The artifact-set hash is
`5914bd873c4a5911575f85623125ab67c4fc6e34577e0be4359041d26bf88d06`.
The accepted repair-004 report manifest is
`1f595cb461818dd4a4661b827a78078c70b040fd7fa62b5a93b58f91945ea16c`;
accepting independent-audit-004 manifest is
`9e02c4dbe33ff65c65a3fb8b17ce184aed047a660f4ea284aed86bf0a303f061`.
Raw artifacts and frozen audit reports remain machine-local.

The unit040 ledger has 801 rows: 585 implementation rows, 27 already implemented
pure-cipher rows, and 189 exclusions. The [disposition ledger](../apk-analysis/row040-dispositions.md)
records each exclusion and final code/test binding. Excluded behavior includes
dead transports/commands, nonrendered cells, Android OS/UI operations, blind
non-CCCD descriptor writes, false readiness, overlapping ATT/backlog races,
multitouch STOP inhibition, surviving producers, cross-device/unbounded/overread
buffers, unsolicited or partial memory mutation, unsupported array domains,
unsynchronized sequence races, cross-device global preferences, unproven physical
state/units and numeric-version UI errors. These boundaries retain useful commands
and raw state while using Home Assistant's serialized, cancellable lifecycle.

Physical actuator assignment, hardware timing and real receiver behavior remain
external validation items after release. They do not defer any statically proven
reachable control or memory operation.

## Chair artwork interpretation

The frozen resource images show the following pictured changes. These are source artwork descriptions, not verified actuator assignments. Channel labels remain literal across themes, and custom Alpha changes the rendered order of `12/13` and `42/43`.

| Artwork theme | Command pair | Pictured change (inferred) |
|---|---|---|
| chairs_hc338 / chairs_clear | 12/13 | extended raised leg section / vertical lowered leg section |
| chairs_hc338 / chairs_clear | 22/23 | reclined back / upright back |
| chairs_hc338 / chairs_clear | 32/33 | top headrest segment changes shape/orientation; physical direction uncertain |
| chairs_hc338 / chairs_clear | 42/43 | raised/tilted seat-base / lowered level seat-base |
| chairs_hc314 | 12/13 | vertical lower leg / extended diagonal lower leg; opposite pictured order from hc338 |
| chairs_hc314 | 22/23 | reclined back / upright back |
| chairs_hc314 | 32/33 | inner vertical back segment higher / lower; exact actuator uncertain |
| chairs_hc314 | 42/43 | small headrest cap upright / angled; exact actuator uncertain |
| chairs_legacy | 12/13 | footrest up arrow / footrest down arrow |
| chairs_legacy | 22/23 | back recline arrow / back upright arrow |
| chairs_legacy | 32/33 | whole seat/back assembly tilt up arrow / return down arrow |
| chairs_legacy | 42/43 | seat tilt up arrow / return down arrow |
| all four chair themes | 50/51 and type2_12/type2_13 | combined reclined back and raised footrest / upright back and lowered footrest; type2 filenames selected only by cKey2 |
