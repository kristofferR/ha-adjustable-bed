# Leggett & Platt Okin (`leggett_okin`)

**Status:** ⚠️ Partially tested (Prodigy CE / CU170 hardware-tested in #368; the other app profiles are statically verified, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Control boxes sold as Leggett & Platt Prodigy Comfort Elite and similar
- Marked `LP BED CONTROL` in BLE advertisements
- Confirmed hardware: DewertOkin CU170

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Prodigy 2L](https://play.google.com/store/apps/details?id=com.leggett.prodigy2L) 1.2 (15) | `com.leggett.prodigy2L` |
| ✅ | [Prodigy 2](https://play.google.com/store/apps/details?id=com.leggett.prodigy2) 2.2.0 (44) | `com.leggett.prodigy2` |
| ✅ | [Prodigy CE / Prodigy 4](https://play.google.com/store/apps/details?id=com.leggett.prodigy4) 1.2.0 (18) | `com.leggett.prodigy4` |
| ✅ | [U / Ultra Series](https://play.google.com/store/apps/details?id=com.leggett.useries) 2.1 (16) | `com.leggett.useries` |

The accepted APK Protocol Audit cluster-005 reports establish four distinct BLE
control surfaces; see [App profiles](#app-profiles).

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head and foot, plus pillow and/or lumbar per app profile |
| Position Feedback | ❌ None. See [Notifications](#notifications). |
| Memory Presets | ✅ Prodigy: four favorites, including fixed Snore; U Series: two held memory controls and separate held SET |
| Massage | ✅ Head/foot up/down, on/off toggle, wave mode step (no discrete off, no timer) |
| Under-bed Lights | ✅ Toggle; Prodigy CE adds a notification-backed light entity |
| Flat | ✅ (held button) |
| Sleep / Alarm Timers | ✅ Native timers through actions |
| Control Mode | ⚠️ Prodigy profiles only; press-and-hold refused on Prodigy CE |
| BLE Pairing | ✅ Required |

## Protocol Details

**Service UUID:** `62741523-52f9-8864-b1ab-3b3a8d65950b`
**Write Characteristic:** `62741525-52f9-8864-b1ab-3b3a8d65950b` (accepts unconfirmed writes)
**Notify Characteristic:** `62741625-52f9-8864-b1ab-3b3a8d65950b`
**Format:** 32-bit keycodes in a 6-byte (revision 1) or 8-byte (revision 0) frame
**Position feedback:** None. See [Notifications](#notifications).

This integration supports BLE; Classic RFCOMM paths found in Prodigy 2 and U
Series remain outside its transport support.

### Two frame formats

The app picks its framing once per connection, purely on whether characteristic
`00001721-0000-1000-8000-00805f9b34fb` exists under the service:

| Characteristic present | Frame | Length |
|---|---|---|
| yes (revision 1) | `04 02 <keycode big-endian 32>` | 6 bytes |
| no (revision 0) | `E5 FE 16 <keycode big-endian 32> <checksum>` | 8 bytes |

The revision-0 checksum is `~sum(bytes[0..6])` truncated to 8 bits, giving the
invariant that all eight bytes sum to `0xFF`.

The integration applies this same characteristic check after service discovery
and records the selected revision in protocol diagnostics. Writes require a
resolved revision from the current connection's GATT service; unavailable
service discovery does not justify guessing either encoding.

### Write Mode

CU170 hardware testing measured a 217-218 ms motion watchdog. The integration
therefore uses unconfirmed writes and measures the 100 ms interval from the
start of each write. Awaiting a confirmed write and then sleeping 100 ms adds
the BLE round trip to every gap, which repeatedly crosses the watchdog over a
WiFi Bluetooth proxy and makes the motor stop and restart.

Unconfirmed writes cannot hide packet loss on a proxy's WiFi. Every frame
crosses that hop as a TCP packet, so one lost packet holds back all later
frames until TCP resends it, usually past the watchdog. Long held moves then
stop and restart ([#916](https://github.com/kristofferR/ha-adjustable-bed/issues/916)).
A faster cadence does not help, because queued frames still wait for the lost
one, so the stream keeps the app's 100 ms interval. A frame loop running next
to the bed showed no late frames on similar or weaker radio links. Use an
Ethernet proxy or a Bluetooth adapter on the Home Assistant host when the
proxy's WiFi is weak.

### Pairing

- Required. Neither app calls `createBond`, but the write characteristic needs
  an encrypted link, so Android bonds reactively on the resulting ATT error 5.
- The CU170 pairing and unconfirmed-write policies come from existing hardware
  testing, not from APK calls that explicitly select bonding or ATT write mode.
- An authentication failure during connection clears the cached bond marker and
  allows automatic pairing retries. A successful verified retry suppresses the
  pairing repair entirely. Failed, inconclusive or cancelled recovery still
  raises the repair, and command-time authentication errors remain immediately
  visible.

## Detection / Setup

Select the app profile matching the bed's remote application. The default
remains **Prodigy CE / Prodigy 4**, preserving existing configurations.

### App profiles

| Profile | Accepted package/version | Movement axes | Direct memories |
|---|---|---|---|
| Prodigy 2L | `com.leggett.prodigy2L` 1.2 (15) | Head, foot, lumbar | Four favorites, including fixed Snore |
| Prodigy 2 | `com.leggett.prodigy2` 2.2.0 (44) | Head, foot, pillow | Four favorites, including fixed Snore |
| Prodigy CE / Prodigy 4 | `com.leggett.prodigy4` 1.2.0 (18) | Head, foot, pillow, lumbar | Four favorites, including fixed Snore |
| U / Ultra Series | `com.leggett.useries` 2.1 (16) | Head, foot, pillow | Two held memory controls and separate held SET |

- App profile and wire revision are independent.
- Device names and shared service UUIDs cannot establish the correct physical
  actuator layout.
- Configure each side before combining two separately addressed beds; shared
  paired options preserve each side's app profile. Unpair temporarily to change
  that setting.
- The new profiles are statically verified and hardware unverified.

## Commands

Ordinary controls use a 32-bit keycode. The app keeps a bitmask of currently-held
buttons, so multiple simultaneous actions are one frame with several bits set.

> [!WARNING]
> **Do not trust the `FBP_KEYCODE_*` constant names in decompiled output.**
> Several are demonstrably wrong for this hardware: `0x00800000` is declared
> `LIGHT_INTENSITY_DOWN` but the shipped massage screen binds it to head massage
> **down**. The layout binding and the write boundary are the authority. Both
> independent analyses of Prodigy CE reached this conclusion separately.

### Motor Control

| Command | Keycode | Description |
|---|---|---|
| Head up / down | `0x00000001` / `0x00000002` | Held |
| Feet up / down | `0x00000004` / `0x00000008` | Held |
| Tilt (pillow) up / down | `0x00000010` / `0x00000020` | Held; pillow profiles |
| Lumbar up / down | `0x00000040` / `0x00000080` | Held; lumbar profiles |
| Release / stop | `0x00000000` | Ordinary frame carrying zero |

### Presets

| Command | Keycode | Kind |
|---|---|---|
| Favorite 1 | `0x00001000` | editable recall |
| Favorite 2 | `0x00002000` | editable recall |
| Snore | `0x00004000` | fixed recall |
| Favorite 3 | `0x00008000` | editable recall |
| Flat | `0x08000000` | **held button**, not a recall |
| Memory store (arm) | `0x00010000` | **not a recall** |

- The three Prodigy profiles initialize Favorite 1, Favorite 2 and Favorite 3 as
  editable entries. They initialize the third wire slot as the fixed Snore
  entry. The integration therefore exposes no separate Zero-G action, and never
  offers or accepts a save operation for the Snore slot.
- U Series instead exposes two held memory keys, a held Snore control and a
  held SET key. It does not inherit the newer apps' composite
  favorite-programming sequence or their four direct favorite entries. Its
  sleep timer independently offers a third memory action.

> [!WARNING]
> `0x00010000` arms the box to overwrite a slot. It must never appear in the
> recall ladder. Earlier releases of this integration used a ladder shifted one
> step up (`0x2000`…`0x10000`), so every memory button recalled its neighbour and
> "Memory 4" streamed the store-arm keycode for 30 seconds, which could
> reprogram a slot with whatever position the bed happened to be in.

### Memory programming

There is no program opcode. Storing a position is two ordinary held keycodes in
sequence:

1. hold `0x00010000` for approximately 5 seconds
2. switch directly to the selected slot for approximately 2 seconds
3. finish with the ordinary four zero frames

- The app's reset and slot assignment are consecutive calls in one callback.
  An intermediate zero can occur through scheduling, but the integration does
  not insert a guaranteed four-zero gap between the two stages.
- U Series has only the standalone held SET path, available through
  `hold_control`.
- The shipped user guide corroborates this: "Touch Save… the massage motors
  will buzz once. Within 5 seconds, touch the Favorite Position being edited."

### Massage and lights

| Command | Keycode | Description |
|---|---|---|
| Head massage up / down | `0x00000800` / `0x00800000` | Held |
| Foot massage up / down | `0x00000400` / `0x01000000` | Held |
| Massage on/off (toggle) | `0x00000100` | No discrete off |
| Massage wave mode step | `0x10000000` | Massage mode-step button |
| Under-bed light toggle | `0x00020000` | Held |

- Massage power is a **toggle** with no discrete off, so the integration exposes
  no massage-off button. The wave keycode is exposed as the massage mode-step
  button.
- There is no massage timer. `0x00000200` appears in the app as a constant
  (`FBP_KEYCODE_M5_IN`, a fifth actuator channel) but is never bound to a
  control and never written; it must not be reconstructed as a command.

### Stop all (Prodigy CE / CU170)

| Command | Keycode | Frames |
|---|---|---|
| DUMMY stop | `0x00040000` | R0 `e5fe160004000002` / R1 `040200040000`, then the ordinary release burst |

See [Command Timing](#command-timing) for when it is sent.

### Sleep and alarm timers

`adjustable_bed.leggett_sleep_timer` and `adjustable_bed.leggett_alarm_timer`
start or cancel native timers. Values below come from the integration's
`leggett_app_protocol.py`.

| Command | Profiles | Value | Range |
|---|---|---|---|
| Sleep timer | Prodigy | Raw packet `04 02 FF <favorite - 1> <minutes, 16-bit big-endian>` | Favorite 1–4, 1–1439 minutes |
| Sleep timer | U Series | Keycode `0xFF000000` with the action bits and minutes OR'd in | Action: flat `0x00100000`, memory 1 `0x00000000`, memory 2 `0x00010000`, memory 3 `0x00020000`; 15–90 minutes in 15-minute steps |
| Sleep cancel | All | Keycode `0xFF200000` | |
| Alarm | All | Keycode `0xFD000000` + minutes | 1–1440 minutes |
| Alarm cancel / stop | Prodigy | Keycode `0xFD200000` | |
| Alarm cancel / stop | U Series | Keycode `0xFD000000` | |

- Prodigy sleep selects a favorite and a delay of 1–1439 minutes. Its sleep
  command is a compact six-byte packet under either wire revision.
- U Series sleep selects flat or memory 1–3 and uses 15-minute steps through 90
  minutes; its timer key follows the selected R0/R1 encoding.
- All profiles support an alarm delay of 1–1440 minutes. U Series has a
  different alarm-stop key from the Prodigy profiles.
- Timer commands, including the Prodigy raw sleep packet, are sent as the
  10-frame recall burst. A successful timer has no zero tail; an interrupted
  burst ends with the zero release.
- The services validate the selected profile's actions and ranges before
  writing. See their Home Assistant action descriptions for field names and
  cancellation.

### Control mode

The three Prodigy profiles expose two persistent control-box settings. U Series
does not expose these settings or initialize the optional CSS channel.

| Mode | Keycode | Lifecycle |
|---|---|---|
| Press-and-hold | `0x08010000` | 55 attempts at 100 ms, then one zero frame |
| Press-and-release | `0x01800000` | 55 attempts at 100 ms, then one zero frame |

**Prodigy CE exception:** #368 reports that SET+FLAT (`0x08010000`) factory-resets
the CU170 and wipes its saved presets. For this profile, Home Assistant removes
the press-and-hold configuration button and refuses the command even when
called through an old entity. Use the physical remote's documented procedure
for mode changes. The press-and-release button remains available.

For the other Prodigy profiles, Home Assistant exposes both configuration
buttons rather than a select, because neither notification channel reports the
currently active mode. On boxes with the optional Smart Remote CSS service,
notification setup also sends the app's raw `01 02` initialization write.

## Notifications

The notify characteristic acknowledges accepted writes and also emits status
updates for physical-remote actions. The vendor app reconstructs a generic
LED/status bitmask from operations 6, 7, 8, 9, and 11, but only assigns UI
meaning to sleep timer (`0x8000`) and alarm (`0x4000`). No parsed value ever
influences a later command.

There is **no position, angle, percentage or motor-state feedback**. The
[CU170 hardware report in #368](https://github.com/kristofferR/ha-adjustable-bed/issues/368#issuecomment-5481326088)
provides the physical meaning absent from the app analysis.

### CU170 status frame (Prodigy CE)

- The integration recognizes a 20-byte status frame on the main status
  characteristic: `09 0B`, two identical big-endian status dwords, and ten
  trailing bytes the integration does not interpret.
- The first of these reads `01` while massage wave mode runs and `FF` in every
  other frame observed (CU170 owner's captures and debug log, 2026-07 to
  2026-10).
- Frames of another length or with mismatched dwords are ignored. Other app
  profiles retain their artifact-derived parser.

| CU170 status mask | Meaning |
|---|---|
| `0x00020000` | Under-bed light on |
| `0x00400000` | Alarm armed |
| `0x00800000` | Sleep timer armed |

- The receipt for a toggle contains the **old** light state. A separate
  spontaneous notification contains the **new** state, including changes from
  the physical remote.
- Every valid notification is processed; notifications are not counted as one
  receipt per write.
- Alarm and sleep indicators use the hardware masks after a CU170 status frame
  is recognized, rather than the app's `0x4000`/`0x8000` labels. CSS settings
  notifications cannot overwrite this hardware status.

### Light entity (Prodigy CE)

Prodigy CE exposes an under-bed **light entity** backed by those notifications.

- On/off actions only toggle when the known state differs from the requested
  state, then wait up to three seconds for confirmation. A missing confirmation
  leaves the light unknown and reports an error without retrying the toggle.
- State is not restored from an earlier Home Assistant session and is cleared on
  disconnect.
- After subscribing, startup sends the app's four idle zero frames to request
  live status without toggling the light. The September hardware report
  confirms that a keycode write refreshes status. If no valid reply arrives,
  state stays unknown.
- The redundant **Toggle Light** button is removed from the entity registry;
  `light.toggle` remains available even before the first status update, as does
  the physical remote.

### Other status sensors

The integration also retains raw LED-mask and signed-status sensors for the
app parser, and reads available standard Device Information strings for
diagnostics. CU170 frames have no decoded signed-status field. Other profiles
retain the app's alarm and sleep masks; U Series applies its app's low-byte
suppression while preserving the raw mask.

## Command Timing

This protocol treats held buttons and one-shot recalls very differently, and
getting the distinction wrong is the main way to break it.

| Command family | Lifecycle |
|---|---|
| **Held keycodes** (motors, flat, light, massage) | Stream every ~100 ms while the button is down. On release the app emits **exactly four** keycode-`0` frames and then goes silent |
| **One-shot recalls** (the memory slots) | A burst of **exactly 10 frames at ~100 ms**, with **no terminator at all**. The control box drives the move to completion by itself |
| Flat | Held button with no app-defined duration; the integration streams it for 30 seconds (at the configured pulse delay, never faster than 100 ms), then sends the release burst |
| Memory programming | See [Memory programming](#memory-programming) |
| Control mode | 55 attempts at 100 ms, then one zero frame |

### Held keycodes and release

- The release frame is an ordinary frame carrying zero.
- Light and massage taps now leave one 100 ms command interval before the
  release burst. Previously the first zero could follow the press immediately,
  making the light toggle too short to register. This uses the accepted app
  cadence; the precise minimum hardware debounce interval is not established.
- LP Control 2.9.0 uses a 200 ms cadence for held commands where Prodigy CE
  uses 100 ms. The integration uses the accepted Prodigy/U Series 100 ms cadence
  and retains the recorded CU170 hardware policy.

### Stop all

For **Prodigy CE / CU170 only**, explicit **Stop all** first sends the
reporter's hardware-tested DUMMY keycode `0x00040000`, then the ordinary release
burst.

- This interrupts a latched preset or preset-save sequence, which zero alone
  does not stop.
- It uses the selected R0/R1 framing (`e5fe160004000002` / `040200040000`) and
  ignores the cancelled movement's cancel event.
- Ordinary end-of-hold cleanup still sends only zero; other app profiles retain
  their accepted release behavior.
- This semantic correction comes from the
  [September hardware report](https://github.com/kristofferR/ha-adjustable-bed/issues/368#issuecomment-5747783066),
  not a newly discovered reachable app command.

### One-shot recalls

- Successful Prodigy recalls retain the app's 10-frame behavior; CU170 hardware
  testing shows that explicit interruption needs the DUMMY keycode.
  Cancellation or write failure uses the proven zero cleanup.
- U Series memory controls follow the ordinary held-key lifecycle instead.
  Memory 1, Memory 2 and Snore therefore have no one-shot preset buttons in
  this profile. Use `adjustable_bed.hold_control` with an explicit duration for
  these controls.

### Hold control action

`adjustable_bed.hold_control` exposes bounded holds for flat, Snore, lighting
and massage buttons. U Series also permits memory 1, memory 2 and SET. The
released `leggett_hold_control` name still works with the same control list.
The existing movement services cover motor holds. These actions preserve the
held-button behavior separately from the Prodigy fixed-count favorite recalls.

## Notes

### Remaining hardware observations

- The reporter measured one light pulse when memory storage arms and three when
  a preset is saved. Those pulses also affect the real light state.
- Programming continues to use the accepted app's bounded five-second arm and
  two-second slot sequence. An acknowledgement-driven optimization needs paired
  raw traces of both initial light states to distinguish the initial dark
  interval, pulses, and final restoration safely. It must never combine SET
  with FLAT, the reported factory-reset chord. The existing store path sends
  each key separately.
- The CU170 can be configured for latched or hold-required presets. Memory
  recalls use the app's short recall burst; `adjustable_bed.hold_control`
  supplies an explicit held duration for boxes in hold-required mode. Flat
  retains its bounded held-command behavior. Hardware validation of this change
  remains for users after a beta or release; maintainers do not need to acquire
  a bed.

Unverified against hardware, and worth a capture if you have the equipment:
which frame revision real units use, whether preset recall truly ends without a
terminator, whether changing control mode also resets editable favorites on all
firmware, and whether the corrected tap interval registers reliably on both
local adapters and wireless proxies.

### Analysis provenance

Command values, framing, timing, notification parsing and release semantics
come from the accepted APK Protocol Audit clean-room analysis of
`com.leggett.prodigy4` 1.2.0 (versionCode 18, artifact SHA-256
`45922c518c9e8070…`), traced from layout binding to the GATT boundary and
independently audited. The report is COMPLETE; the hardware status mapping
above supplements that frozen app evidence and does not modify or replace the
accepted analysis. The [whole-cluster disposition](leggett-app-disposition.md)
records all four accepted report identities, previously implemented behavior,
remaining findings, exact app differences and transport exclusions.
