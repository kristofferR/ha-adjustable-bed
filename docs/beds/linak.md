# Linak

**Status:** ✅ Tested (existing protocol user tested; full current Android app corpus statically verified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), jascdk and [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt)

## Known Models

- Linak DPG1M (OEM controller used in many beds)
- Bedre Nætter
- Jensen
- Auping
- Carpe Diem
- Wonderland
- Svane
- Many OEM adjustable beds with Linak motors

The analyzed apps contain no product-name or remote-code catalog. The integration
therefore selects behavior from the live GATT services and actuator mask, not from
a retail brand or guessed model name.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Linak Bed Control](https://play.google.com/store/apps/details?id=com.linak.linakbed.ble.memory) 6.0.9 (`264`) | `com.linak.linakbed.ble.memory` |
| ✅ | [Bed Connect](https://play.google.com/store/apps/details?id=com.linak.bedconnect.iot) 5.2.4 (`253`) | `com.linak.bedconnect.iot` |
| ✅ | [Performance Series](https://play.google.com/store/apps/details?id=com.linak.leggettandplatt) 1.0 (`124`) | `com.linak.leggettandplatt` |

All three have frozen COMPLETE reports; hashes are under
[Analysis provenance](#analysis-provenance).

## Features

| Feature | Bed Control | Performance Series |
|---------|-------------|--------------------|
| Motor control and explicit release | ✅ (mask-selected Back, Legs, Head, Feet, Base) | ✅ |
| Native two-section movement opcodes | ✅, all 40 combinations | ❌ |
| Flat | ✅ | ✅ |
| All up | ✅ | ❌ |
| Four memory recalls and stores | TD3/Advanced only | ✅ |
| Position, reported speed and four status flags | Advanced only | ❌ |
| All 104 protocol error codes | ✅ | ❌, notification payload is opaque |
| Massage | Off, modes, zones and intensity | Toggle, wave/frequency, intensity and impulse |
| AUX/under-bed light | On/off light entity | Toggle button |
| Automatic drive configuration | ✅ | ❌ |
| BLE device rename | ✅ | ❌ |
| Alarm event, recurrence and commit | Alarm model only | ❌ |
| Reset defaults (`4E 00`) | ✅ | ✅ |
| Configuration factory reset (`7F 3E 80`) | ✅, disabled by default | ❌ |
| Wake command | ✅ | ❌ |
| Hold until release | ✅ ([renewable](../SERVICES.md#renewable-holds): 100 ms refresh, then the release) | ✅ ([renewable](../SERVICES.md#renewable-holds): 300 ms refresh, then the release) |

## Protocol Details

**Service UUID:** `99fa0001-338a-1024-8a49-009c0215f78a`
**Write Characteristic:** `99fa0002-338a-1024-8a49-009c0215f78a`
**Notify Characteristic:** `99fa0003-338a-1024-8a49-009c0215f78a` (error, or required legacy notify)
**Format:** 2 bytes `[opcode, 00]`; Performance Series release is the one-byte `FF`

### GATT roles

| Role | UUID |
|------|------|
| Control service | `99fa0001-338a-1024-8a49-009c0215f78a` |
| Control write | `99fa0002-338a-1024-8a49-009c0215f78a` |
| Error or required legacy notify | `99fa0003-338a-1024-8a49-009c0215f78a` |
| Configuration service/write | `99fa0010-...` / `99fa0011-...` |
| Reference Output service | `99fa0020-...` |
| Base/Feet/Head/Legs/Back references | `99fa0024-...` through `99fa0028-...` |
| Actuator mask | `99fa0029-...` |
| Timer service/write | `99fa0050-...` / `99fa0051-...` |
| Device name | Bluetooth SIG `2a00` |

### Bonding and authentication

- All three analyzed BLE applications proactively request Android/OS bonding.
- Physical testing with two Advanced controllers proves that their GATT control
  works without a bond, so the integration does not force pairing.
- A short post-connect readiness retry handles the controllers' transient
  `Insufficient authentication` window instead.
- There is no application PIN, passkey, challenge, token or protocol encryption.

## Detection

- Bed type: the control service `99fa0001-...` or Reference Output service
  `99fa0020-...` in the advertisement, or a name of `Bed ` followed only by digits
  (for example `Bed 1696`), for beds that advertise no service UUIDs.
- Profile and model: see below. A retail brand or model name does not identify them.

## Profiles and model variants

Choose **Auto (Bed Control)** unless the bed was controlled by the old Linak
Performance Series app. Auto and explicit Bed Control use the modern profile and
discover its model after connection. Performance Series must be selected
explicitly because its advertisement does not identify it safely.

| Profile or model | Selection | Positions | Memories | Alarm |
|------------------|-----------|-----------|----------|-------|
| Standard | Reference Output service absent | No | 0 | No |
| TD3 | Reference Output service present, mask is zero | No | 4 | No |
| Advanced | Nonzero actuator mask | Mask-selected axes | 4 | No |
| Advanced with alarm | Advanced plus successful timer subscription | Mask-selected axes | 4 | Yes |
| Performance Series | Explicit protocol variant | No parsed feedback | 4 | No |

- Advanced mask bits select Back, Legs, Head, Feet and Base. Entity creation
  follows that exact mask.
- A Base actuator becomes a bed-height cover; the other selected axes receive
  movement controls and position entities.
- The resolved variant is shown as the device's Model ID in Home Assistant rather
  than as a separate entity.

### Unreadable actuator mask

Some controllers never answer the mask read over an ESPHome proxy, or reject it
with `Insufficient authorization` ([#714](https://github.com/kristofferR/ha-adjustable-bed/issues/714)).

- The read is bounded to two seconds.
- When it fails, a mask read on an earlier connection stays authoritative.
- Without one, the integration falls back to the configured motor count, as 3.x
  did: Back and Legs, plus Head for three motors and Feet for four, limited to
  reference outputs present in the GATT table.
- Both TD3 and Advanced have four memories, so those stay available.
- The snapshot is marked `actuator_mask_inferred`, and a later successful read
  replaces it.

## Commands

All normal commands are written to the control characteristic as `[opcode, 00]`.

### Motor Control

| Command | Bytes | Description |
|---------|-------|-------------|
| Stop/release | `FF 00` | Bed Control release (Performance: one-byte `FF`) |
| Flat/all down | `00 00` | All sections down; never STOP |
| All up | `01 00` | All sections up |
| Base down/up | `06 00` / `07 00` | Bed height |
| Feet down/up | `04 00` / `05 00` | |
| Head down/up | `02 00` / `03 00` | |
| Legs down/up | `08 00` / `09 00` | |
| Back down/up | `0A 00` / `0B 00` | |

> [!WARNING]
> `00 00` is flat/all down (the code's `INITIALIZE_DOWN`), not STOP. Earlier
> versions of this document listed it as Stop; using it to stop can cause a brief
> reverse movement. Always release with `FF 00`.

### Two-section movement

The protocol defines a complete contiguous table of 40 two-section commands from
`10 00` through `37 00`. Use the `adjustable_bed.linak_move_simultaneously`
service to select two axes, their directions and a bounded duration.

Axes are ordered Base, Feet, Head, Legs, Back; the earlier axis is "first".

| Axis pair | Opcodes | Construction |
|-----------|---------|--------------|
| Base + Feet/Head/Legs/Back | `10`–`1F` | `10` + second (Feet 0, Head 1, Legs 2, Back 3), +`08` first up, +`04` second up |
| Feet + Head/Legs/Back | `20`–`2B` | `20` + second (Head 0, Legs 1, Back 2), +`06` first up, +`03` second up |
| Head + Legs/Back | `2C`–`33` | `2C` + second (Legs 0, Back 1), +`04` first up, +`02` second up |
| Legs + Back | `34`–`37` | `34`, +`02` legs up, +`01` back up |

### Memory

| Command | Bytes | Description |
|---------|-------|-------------|
| Recall memories 1/2/3/4 | `0E 00`, `0F 00`, `0C 00`, `44 00` | Held recall (see timing) |
| Store memories 1/2/3/4 | `38 00`, `39 00`, `3A 00`, `45 00` | One-shot |

### Massage

| Command | Bytes or sequence | Description |
|---------|-------------------|-------------|
| Massage off / next mode | `80 00` / `81 00` | |
| Both-zone intensity up/down | `A8 00` / `A9 00` | |
| Zone 1 intensity up/down | `8D 00` / `8E 00` | |
| Zone 2 intensity up/down | `8F 00` / `90 00` | |
| Zone 1 only | `89 00`, wait 100 ms, `8C 00` | Zone selection |
| Zone 2 only | `8A 00`, wait 100 ms, `8B 00` | Zone selection |
| Both zones | `89 00`, wait 100 ms, `8B 00` | Zone selection |

### Lights

| Command | Bytes | Description |
|---------|-------|-------------|
| Light toggle | `94 00` | App AUX toggle; Performance toggle button |
| Light on/off | `92 00` / `93 00` | Modern profile, hardware verified ([#615](https://github.com/kristofferR/ha-adjustable-bed/issues/615)) |

### Configuration and maintenance

| Command | Bytes or sequence | Destination |
|---------|-------------------|-------------|
| Reset defaults | `4E 00` | Control |
| Configuration factory reset | `7F 3E 80` | Configuration |
| Wake | `FE 00` | Control |
| Automatic drive on/off | `89 3B 80 00 01` / `89 3B 80 00 00` | Configuration |
| Rename | 1 to 17 UTF-8 bytes | `2a00` |
| Alarm commit | `20` | Timer |

- Rename writes to `2a00`, then disconnects so advertising can refresh. Use
  `adjustable_bed.rename` (`linak_rename` still works).
- Alarm setup first enables automatic drive, writes an event with one to four
  actions, writes packed recurrence, then commits with `20`. Use
  `adjustable_bed.linak_set_alarm`; it appears only on an alarm-capable model.

### Performance Series

Performance additionally exposes:

| Command | Bytes |
|---------|-------|
| Massage toggle | `91 00` |
| Wave toggle | `81 00` |
| Frequency up/down | `87 00` / `88 00` |
| Impulse | `4D 00` |
| Reset | `4E 00` |
| Release | `FF` |

## Position Feedback

Reference notifications are exactly four little-endian bytes:

- Low 16 bits: extension divided by 100.
- Bits 16 through 19: SLS, end-position-up, end-position-down and position-lost.
- High 12 bits: sign-extended speed; the reported magnitude uses a factor of
  `0.09765625`. Direction is exposed separately from the magnitude.

| Axis | Reference characteristic | Full-scale value | Converted to |
|------|--------------------------|------------------|--------------|
| Back | `99fa0028-...` | 820 | Configured back max angle (default 68°) |
| Legs | `99fa0027-...` | 548 | Configured legs max angle (default 45°) |
| Head | `99fa0026-...` | 820 | Configured head max angle |
| Feet | `99fa0025-...` | 548 | Configured feet max angle |
| Base | `99fa0024-...` | Raw | Bed-height cover |

- The integration exposes an axis speed sensor with raw speed, direction,
  extension and every status flag as attributes.
- It also exposes an aggregate position-feedback fault binary sensor and a
  diagnostic sensor for all 104 app-defined error codes.
- Extension is converted to the configured angle range for the position entities;
  the read-only angle sensors are omitted because they would duplicate those same
  values.
- The artifact does not prove a physical unit for extension or speed.

### Position seeking

- Linak uses a 0.3° seek tolerance for ordinary targets.
- During a seek, it follows Bed Control's held-command lifecycle: one movement
  frame every 100 ms, with no intermediate release, then one `FF 00` release when
  the target is reached or the operation ends.
- Fresh per-axis reference notifications drive the feedback loop directly; an
  explicit GATT read remains the fallback when that notification stream is stale.
  This keeps the motor moving continuously while retaining safe behavior on
  variants with missing feedback.

### Lower endpoints

- Live testing found lower physical endpoints where an actuator stopped at a
  reported 0.2° to 1.1° when 0° was requested.
- A seek to exactly 0° therefore skips the downward coast compensation (the frame
  cannot overshoot its end stop) and completes after two consecutive stalled
  checks at or below 1.1°, with at most one retry after the first confirmed stall.
- Mid-range stalls continue to retry normally.
- An actuator resting just below its learned zero can report -1, -2 or -3
  (`0xFFFF`/`0xFFFE`/`0xFFFD`). Those observed samples decode as 0°; values below
  -3 are still discarded as invalid.
- On 2026-09-23, a stationary Advanced controller returned `FD FF 00 00` for its
  leg position during startup, while the other side returned `FE FF 00 00`. The
  earlier -2 cutoff discarded the right leg sample and left its number and cover
  entities `unknown`. This hardware observation extends the existing near-zero
  handling by one count. It supplements the frozen Bed Control 6.0.9
  reference-parser evidence; it does not change the packet parser, status flags,
  command timing or connection policy.
- Upper endpoints retain the normal tolerance. No upper-endpoint exception is
  enabled without supporting evidence.

## Command Timing

- Bed Control repeats held movement and recall every 100 ms and sends `FF 00`.
- Performance repeats every 300 ms and attempts the one-byte `FF` release.
- Memory stores, reset, light, massage, configuration, rename and timer packets
  are one-shot writes.
- Modern massage-zone selection spaces its two writes by 100 ms.
- Ordinary movement controls use 10 writes at 100 ms for Bed Control and 4 writes
  at 300 ms for the explicit Performance profile.
- Feedback-driven position seeks refresh the movement command every 100 ms until
  completion.
- Every movement path performs one profile-specific release in cleanup, including
  cancellation. `00 00` is flat/all down, never STOP.
- Memory recall and flat presets have a 30-second elapsed hold limit after
  connection readiness. Slow Bluetooth acknowledgements cannot extend that hold;
  STOP cleanup still runs when the limit expires or a command is cancelled.

### Rapid commands and the physical remote

- Keep **Disconnect after command** enabled when using the physical remote.
- Linak holds the connection for one second after an operation, so rapid
  follow-up taps reuse the authenticated link.
- Combined actions retain both links until both sides finish, then start the
  handoff together.
- A new command renews this short window; the explicit **Disconnect** button
  bypasses it. Turning the option off uses the configured idle timeout instead.
- With quick disconnect enabled, background position polling is also suppressed
  so it cannot reclaim the remote's connection while idle. Position feedback
  refreshes during HA operations; remote-only movements appear on the next
  connection.

### Connection readiness and retries

- A fresh connection can take around 12 seconds to accept control writes through
  a Bluetooth proxy. The integration retries the safe STOP probe for up to 15
  seconds per readiness request, including after interrupted startup.
- Cancellation does not mark the session ready unless a write was acknowledged,
  and deferred subscriptions resume on the next command.
- Queued commands remain serialized and STOP invalidates older pending movement.
- When HA sees multiple available connection paths, Linak allows up to five
  connection attempts so HA can fall back from a stronger but failing proxy to a
  working alternative. Retry backoff stops growing after the second retry.
- A genuinely unreachable bed still reports failure after this bounded retry
  budget.

## Notes

### Light state

- The modern app exposes only a light toggle, but direct hardware testing for
  [issue #615](https://github.com/kristofferR/ha-adjustable-bed/issues/615)
  confirmed the library's separate ON (`92 00`) and OFF (`93 00`) commands. The
  modern profile therefore exposes a normal on/off light entity.
- Loading the integration (including adding a bed or reloading its entry) sends
  OFF once to synchronize the physical light and HA. Ordinary BLE reconnects do
  not reset it. A failed initialization leaves the state unknown until a
  successful on/off command.
- HA tracks successful commands; this is not device-reported light feedback.
  Changing the light with the physical remote or app can desynchronize the
  displayed state. An explicit HA ON or OFF command sets the requested state
  again, even if HA already displays that state.
- Performance Series remains toggle-only because its discrete controls have not
  been verified.

### Hardware evidence for issue #615

On 2026-09-21, the maintainer observed the built-in light on the right-hand bed
(modern Advanced profile, actuator mask `C0`) while an isolated probe used the
kitchen ESPHome proxy. Each command was one acknowledged write to the control
characteristic; no movement or configuration commands were sent:

| Local time (Europe/Oslo) | Write | Maintainer-observed result |
| --- | --- | --- |
| 15:48:59 | `92 00` | Initially off, turned on |
| 15:49:44 | `92 00` | Stayed on |
| 15:50:17 | `93 00` | Turned off |
| 15:50:39 | `93 00` | Stayed off |

- All available Linak notification channels were subscribed, and readable Linak
  characteristics were sampled before and after writes.
- No usable light-state feedback was observed: the error read stayed empty,
  configuration stayed `FE`, and subsequent readable values were identical across
  ON/OFF. Initial reference notifications were position values, not evidence of
  light state.
- This does not prove that every firmware lacks another feedback mechanism. The
  issue reporter's TD5 (Standard profile) has not been physically tested in this
  session.
- This hardware evidence supplements the unchanged frozen app reports: absence of
  an app caller did not establish that the peripheral rejects those constants. It
  does not enable other dead library commands (such as memories 5/6).
- The modern-profile ON/OFF commands also restore the pre-v4 integration behavior
  reported working in #615. They are not gated on the position-feedback service
  that distinguishes Standard from Advanced; the frozen modern AUX command enum
  does not define a separate packet format for those models.

### Bed Connect exclusion

Bed Connect contains two paths. Its direct P1 BLE bed-control path corroborates
the modern control protocol and is covered by the Bed Control implementation,
including its unique configuration-level factory reset. Its P2 path provisions
and updates a separate WiFi module. P2 is intentionally and permanently out of
scope: this integration controls beds over BLE only and will not implement WiFi
provisioning, cloud control or module firmware updates.

### Corpus discovery disposition

Every reachable corpus finding has a final disposition. The table groups commands
that share a builder, lifecycle and user-facing control; the byte-level command
tables above remain exhaustive.

| Discovery group | Disposition | Integration surface |
|-----------------|-------------|---------------------|
| Bed Control discovery, optional app bonding and GATT session | Implemented | Unbonded-compatible coordinator connection with readiness retry |
| STANDARD/TD3/ADVANCED/alarm capability selection | Implemented | Live service/mask discovery with persisted snapshot |
| Individual, all-section and all 40 two-section movements | Implemented | Covers, preset buttons and simultaneous-move service |
| STOP/release and 100 ms held-command lifecycle | Implemented | Guaranteed cleanup on completion, failure and cancellation |
| Four favorite recalls and stores with model gating | Implemented | Buttons and generic preset services |
| Massage zones, modes and all intensity actions | Implemented | Capability-gated buttons |
| AUX/light toggle | Implemented | Native controller action; legacy toggle button, modern on/off entity |
| Defaults reset and configuration factory reset | Implemented | Separate buttons; factory reset disabled by default |
| Automatic drive configuration | Implemented | Assumed-state switch, disabled by default |
| Device rename | Implemented | `rename` action (or `linak_rename`) plus advertising refresh disconnect |
| Alarm event, recurrence, commit and notification states | Implemented | `linak_set_alarm` service and diagnostic sensor |
| Reference extension, flags and reported speed | Implemented | Position entities, speed sensors and fault diagnostic |
| All 104 modern error values | Implemented | Diagnostic sensor with raw code/payload attributes |
| Double/synchronized bed targeting | Already implemented | Generic paired-bed routing sends the same frames per side |
| Performance discovery, command surface and one-byte release | Implemented | Explicit Performance Series profile |
| Performance opaque required notification | Implemented | Subscription and raw diagnostics without invented parsing |
| Bed Connect direct-BLE P1 commands, variants and parsers | Already implemented | Modern controller is a superset; its unique factory reset is implemented separately |
| Bed Connect phone-local scheduled favorite/massage actions | Already implemented | Home Assistant scheduling invokes the same preset/massage controls |
| Bed Connect P2 WiFi module | Excluded | WiFi provisioning, cloud/module state and firmware are outside this BLE-only integration |
| Library constants and implementations with no app caller | Excluded | App-unreachable, including memories 5/6; discrete light on/off separately enabled by the hardware evidence above |
| App-local settings with no BLE effect | Excluded | Unrelated to bed transport, including the Performance app's local child-lock preference |

### Analysis provenance

All three current corpus packages have frozen COMPLETE reports that pass the
reusable [APK Protocol Audit completion gates](https://github.com/kristofferR/ha-adjustable-bed/issues/443).
The APKs, decompilation output, and reports remain machine-local as required by
[issue #436](https://github.com/kristofferR/ha-adjustable-bed/issues/436).

| App | Package and version | Artifact-set SHA-256 | Frozen report evidence |
|-----|---------------------|---------------------|------------------------|
| Bed Control | `com.linak.linakbed.ble.memory` 6.0.9 (`264`) | `4ac807c4a76c34edffa06f6d659c07ecd94382e656851fa6f784fd47076854d3` | `analysis.json` `3801cc95b7ddbffa8a828809451143ad74ddedb2ffdc93d383f2c0a474528017`; manifest `c4d5e4ca095f4a7a43aa7ce7f17f82badf16ff1b79485bf80c17511d76cbfb94` |
| Bed Connect | `com.linak.bedconnect.iot` 5.2.4 (`253`) | `21f189557b5a23c1dfc60623feacbf586571da9c125234cf48aabe89fbe2d885` | `analysis.json` `377168b2f0654353d0c5fd1827624f3de3c5a421d385b4755ec23d2fcd30b49a`; manifest `ef22dd0bf16252b6f75e08da39b3f33ce2dd92e9f8e16914a66a1c83edfba235` |
| Performance Series | `com.linak.leggettandplatt` 1.0 (`124`) | `0693675a0182fc5a7a9e430d8ead9e75fefc0e2538692712172842f12095bcfe` | `analysis.json` `405f97be46aa84cf53c17acfe86ccb1665618b2683e2c3804c7b4fc60fe89f92`; manifest `662c3b4158ef31024dcbcbd62616353ef0886cddcf8d0a3585902494fd998b63` |
