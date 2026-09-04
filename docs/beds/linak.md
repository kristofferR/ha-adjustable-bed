# Linak

**Status:** ✅ Existing protocol user tested; full current Android app corpus statically verified

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

## Analysis provenance

All three current corpus packages have frozen COMPLETE reports that pass the
reusable [Phase 4 completion gates](https://github.com/kristofferR/ha-adjustable-bed/issues/443).
The APKs, decompilation output, and reports remain machine-local as required by
[issue #436](https://github.com/kristofferR/ha-adjustable-bed/issues/436).

| App | Package and version | Artifact-set SHA-256 | Frozen report evidence |
|-----|---------------------|---------------------|------------------------|
| Bed Control | `com.linak.linakbed.ble.memory` 6.0.9 (`264`) | `4ac807c4a76c34edffa06f6d659c07ecd94382e656851fa6f784fd47076854d3` | `analysis.json` `3801cc95b7ddbffa8a828809451143ad74ddedb2ffdc93d383f2c0a474528017`; manifest `c4d5e4ca095f4a7a43aa7ce7f17f82badf16ff1b79485bf80c17511d76cbfb94` |
| Bed Connect | `com.linak.bedconnect.iot` 5.2.4 (`253`) | `21f189557b5a23c1dfc60623feacbf586571da9c125234cf48aabe89fbe2d885` | `analysis.json` `377168b2f0654353d0c5fd1827624f3de3c5a421d385b4755ec23d2fcd30b49a`; manifest `ef22dd0bf16252b6f75e08da39b3f33ce2dd92e9f8e16914a66a1c83edfba235` |
| Performance Series | `com.linak.leggettandplatt` 1.0 (`124`) | `0693675a0182fc5a7a9e430d8ead9e75fefc0e2538692712172842f12095bcfe` | `analysis.json` `405f97be46aa84cf53c17acfe86ccb1665618b2683e2c3804c7b4fc60fe89f92`; manifest `662c3b4158ef31024dcbcbd62616353ef0886cddcf8d0a3585902494fd998b63` |

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

Advanced mask bits select Back, Legs, Head, Feet and Base. Entity creation follows
that exact mask. A Base actuator becomes a bed-height cover; the other selected
axes receive movement controls and position entities. The resolved variant is
shown as the device's Model ID in Home Assistant rather than as a separate entity.

All three analyzed BLE applications proactively request Android/OS bonding, but
physical testing with two Advanced controllers proves that their GATT control
works without a bond. The integration therefore does not force pairing. A short
post-connect readiness retry handles the controllers' transient `Insufficient
authentication` window instead. There is no application PIN, passkey,
challenge, token or protocol encryption.

## Implemented features

| Feature | Bed Control | Performance Series |
|---------|-------------|--------------------|
| Motor control and explicit release | ✅ | ✅ |
| Native two-section movement opcodes | ✅, all 40 combinations | ❌ |
| Flat | ✅ | ✅ |
| All up | ✅ | ❌ |
| Four memory recalls and stores | TD3/Advanced only | ✅ |
| Position, reported speed and four status flags | Advanced only | ❌ |
| All 104 protocol error codes | ✅ | ❌, notification payload is opaque |
| Massage | Off, modes, zones and intensity | Toggle, wave/frequency, intensity and impulse |
| AUX/under-bed light | Toggle button | Toggle button |
| Automatic drive configuration | ✅ | ❌ |
| BLE device rename | ✅ | ❌ |
| Alarm event, recurrence and commit | Alarm model only | ❌ |
| Reset defaults (`4E 00`) | ✅ | ✅ |
| Configuration factory reset (`7F 3E 80`) | ✅, disabled by default | ❌ |
| Wake command | ✅ | ❌ |

The modern app exposes only a light toggle. The integration deliberately does not
create an inaccurate on/off switch or implement the dead library-only `92 00` and
`93 00` constants. The same rule excludes dead memory 5/6 and discrete massage
toggle constants that have no reachable current-app caller.

## Corpus discovery disposition

Every reachable corpus finding has a final disposition. The table groups commands
that share a builder, lifecycle and user-facing control; the byte-level command
tables below remain exhaustive.

| Discovery group | Disposition | Integration surface |
|-----------------|-------------|---------------------|
| Bed Control discovery, optional app bonding and GATT session | Implemented | Unbonded-compatible coordinator connection with readiness retry |
| STANDARD/TD3/ADVANCED/alarm capability selection | Implemented | Live service/mask discovery with persisted snapshot |
| Individual, all-section and all 40 two-section movements | Implemented | Covers, preset buttons and simultaneous-move service |
| STOP/release and 100 ms held-command lifecycle | Implemented | Guaranteed cleanup on completion, failure and cancellation |
| Four favorite recalls and stores with model gating | Implemented | Buttons and generic preset services |
| Massage zones, modes and all intensity actions | Implemented | Capability-gated buttons |
| AUX/light toggle | Implemented | Toggle button only |
| Defaults reset and configuration factory reset | Implemented | Separate buttons; factory reset disabled by default |
| Automatic drive configuration | Implemented | Assumed-state switch, disabled by default |
| Device rename | Implemented | `linak_rename` service plus advertising refresh disconnect |
| Alarm event, recurrence, commit and notification states | Implemented | `linak_set_alarm` service and diagnostic sensor |
| Reference extension, flags and reported speed | Implemented | Position entities, speed sensors and fault diagnostic |
| All 104 modern error values | Implemented | Diagnostic sensor with raw code/payload attributes |
| Double/synchronized bed targeting | Already implemented | Generic paired-bed routing sends the same frames per side |
| Performance discovery, command surface and one-byte release | Implemented | Explicit Performance Series profile |
| Performance opaque required notification | Implemented | Subscription and raw diagnostics without invented parsing |
| Bed Connect direct-BLE P1 commands, variants and parsers | Already implemented | Modern controller is a superset; its unique factory reset is implemented separately |
| Bed Connect phone-local scheduled favorite/massage actions | Already implemented | Home Assistant scheduling invokes the same preset/massage controls |
| Bed Connect P2 WiFi module | Excluded | WiFi provisioning, cloud/module state and firmware are outside this BLE-only integration |
| Library constants and implementations with no app caller | Excluded | Proven dead/unreachable, including memories 5/6 and discrete light on/off |
| App-local settings with no BLE effect | Excluded | Unrelated to bed transport, including the Performance app's local child-lock preference |

## BLE protocol

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

Normal commands are two bytes: `[opcode, 00]`. Representative movement commands:

| Action | Bytes |
|--------|-------|
| Stop/release | `FF 00` |
| Flat/all down | `00 00` |
| All up | `01 00` |
| Base down/up | `06 00` / `07 00` |
| Feet down/up | `04 00` / `05 00` |
| Head down/up | `02 00` / `03 00` |
| Legs down/up | `08 00` / `09 00` |
| Back down/up | `0A 00` / `0B 00` |

The protocol also defines a complete contiguous table of 40 two-section commands
from `10 00` through `37 00`. Use the `adjustable_bed.linak_move_simultaneously`
service to select two axes, their directions and a bounded duration.

### Memories, massage and light

| Action | Bytes or sequence |
|--------|-------------------|
| Recall memories 1/2/3/4 | `0E 00`, `0F 00`, `0C 00`, `44 00` |
| Store memories 1/2/3/4 | `38 00`, `39 00`, `3A 00`, `45 00` |
| Massage off / next mode | `80 00` / `81 00` |
| Both-zone intensity up/down | `A8 00` / `A9 00` |
| Zone 1 intensity up/down | `8D 00` / `8E 00` |
| Zone 2 intensity up/down | `8F 00` / `90 00` |
| Zone 1 only | `89 00`, wait 100 ms, `8C 00` |
| Zone 2 only | `8A 00`, wait 100 ms, `8B 00` |
| Both zones | `89 00`, wait 100 ms, `8B 00` |
| Light toggle | `94 00` |
| Reset defaults | `4E 00` to control |
| Configuration factory reset | `7F 3E 80` to configuration |

Performance additionally exposes massage toggle `91 00`, wave toggle `81 00`,
frequency `87/88 00`, impulse `4D 00`, and reset `4E 00`.

### Position, speed and status

Reference notifications are exactly four little-endian bytes:

- Low 16 bits: extension divided by 100.
- Bits 16 through 19: SLS, end-position-up, end-position-down and position-lost.
- High 12 bits: sign-extended speed; the reported magnitude uses a factor of
  `0.09765625`. Direction is exposed separately from the magnitude.

The integration exposes an axis speed sensor with raw speed, direction, extension
and every status flag as attributes. It also exposes an aggregate position-feedback
fault binary sensor and a diagnostic sensor for all 104 app-defined error codes.
Extension is converted to the configured angle range for the position entities;
the read-only angle sensors are omitted because they would duplicate those same
values. The artifact does not prove a physical unit for extension or speed.

### Configuration, rename and alarm

- Automatic drive writes `89 3B 80 00 01/00` to the configuration characteristic.
- Rename writes 1 to 17 UTF-8 bytes to `2a00`, then disconnects so advertising
  can refresh. Use `adjustable_bed.linak_rename`.
- Alarm setup first enables automatic drive, writes an event with one to four
  actions, writes packed recurrence, then commits with `20`. Use
  `adjustable_bed.linak_set_alarm`; it appears only on an alarm-capable model.

## Timing and release behavior

- Bed Control repeats held movement and recall every 100 ms and sends `FF 00`.
- Performance repeats every 300 ms and attempts the one-byte `FF` release.
- Memory stores, reset, light, massage, configuration, rename and timer packets
  are one-shot writes.
- Modern massage-zone selection spaces its two writes by 100 ms.

Ordinary movement controls use 10 writes at 100 ms for Bed Control and 4 writes
at 300 ms for the explicit Performance profile. Feedback-driven position seeks
refresh the movement command every 100 ms until completion. Every movement path
performs one profile-specific release in cleanup, including cancellation. `00
00` is flat/all down, never STOP.

## Bed Connect exclusion

Bed Connect contains two paths. Its direct P1 BLE bed-control path corroborates
the modern control protocol and is covered by the Bed Control implementation,
including its unique configuration-level factory reset. Its P2 path provisions
and updates a separate WiFi module. P2 is intentionally and
permanently out of scope: this integration controls beds over BLE only and will
not implement WiFi provisioning, cloud control or module firmware updates.

## Position seeking

Linak uses a 0.3° seek tolerance for ordinary targets. During a seek, it follows
Bed Control's held-command lifecycle: one movement frame every 100 ms, with no
intermediate release, then one `FF 00` release when the target is reached or the
operation ends. Fresh per-axis reference notifications drive the feedback loop
directly; an explicit GATT read remains the fallback when that notification
stream is stale. This keeps the motor moving continuously while retaining safe
behavior on variants with missing feedback.

Live testing found lower physical endpoints where an actuator stopped at a
reported 0.2° to 1.1° when 0° was requested. A seek to exactly 0° therefore
skips the downward coast compensation (the frame cannot overshoot its end stop)
and completes after two consecutive stalled checks at or below 1.1°, with at
most one retry after the first confirmed stall. Mid-range stalls continue to
retry normally.

An actuator resting just below its learned zero reports a signed extension of
-1 or -2 (`0xFFFF`/`0xFFFE`). Small negatives decode as 0°; larger negatives
are still discarded as invalid.

Upper endpoints retain the normal tolerance. No upper-endpoint exception is
enabled without supporting evidence.
