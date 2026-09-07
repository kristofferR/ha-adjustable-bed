# Leggett & Platt Okin (`leggett_okin`)

Control boxes sold as Leggett & Platt Prodigy Comfort Elite and similar, marked
`LP BED CONTROL` in BLE advertisements. Confirmed hardware: DewertOkin CU170.

Select the app profile matching the bed's remote application. The default remains
**Prodigy CE / Prodigy 4**, preserving existing configurations. The accepted
Phase 4 cluster-005 reports establish these distinct BLE control surfaces:

| Profile | Accepted package/version | Movement axes | Direct memories |
|---|---|---|---|
| Prodigy 2L | `com.leggett.prodigy2L` 1.2 (15) | Head, foot, lumbar | Four favorites, including fixed Snore |
| Prodigy 2 | `com.leggett.prodigy2` 2.2.0 (44) | Head, foot, pillow | Four favorites, including fixed Snore |
| Prodigy CE / Prodigy 4 | `com.leggett.prodigy4` 1.2.0 (18) | Head, foot, pillow, lumbar | Four favorites, including fixed Snore |
| U / Ultra Series | `com.leggett.useries` 2.1 (16) | Head, foot, pillow | Two held memory controls and separate held SET |

App profile and wire revision are independent. Device names and shared service
UUIDs cannot establish the correct physical actuator layout. Configure each side
before combining two separately addressed beds; shared paired options preserve
each side's app profile. Unpair temporarily to change that setting.

The new profiles are statically verified and hardware unverified. The CU170
pairing and unconfirmed-write policies below come from existing hardware testing,
not from APK calls that explicitly select bonding or ATT write mode. This
integration supports BLE; Classic RFCOMM paths found in Prodigy 2 and U Series
remain outside its transport support.

## Transport

| | |
|---|---|
| Service UUID | `62741523-52f9-8864-b1ab-3b3a8d65950b` |
| Write characteristic | `62741525-52f9-8864-b1ab-3b3a8d65950b` (accepts unconfirmed writes) |
| Notify characteristic | `62741625-52f9-8864-b1ab-3b3a8d65950b` |
| Pairing | Required. Neither app calls `createBond`, but the write characteristic needs an encrypted link, so Android bonds reactively on the resulting ATT error 5. |
| Position feedback | None. See [Notifications](#notifications). |

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
resolved revision from the current connection's GATT service; unavailable service
discovery does not justify guessing either encoding.

## Keycodes

Ordinary controls use a 32-bit keycode. The app keeps a bitmask of currently-held
buttons, so multiple simultaneous actions are one frame with several bits set.

> **Do not trust the `FBP_KEYCODE_*` constant names in decompiled output.**
> Several are demonstrably wrong for this hardware: `0x00800000` is declared
> `LIGHT_INTENSITY_DOWN` but the shipped massage screen binds it to head massage
> **down**. The layout binding and the write boundary are the authority. Both
> independent analyses of Prodigy CE reached this conclusion separately.

### Motors

| Action | Keycode |
|---|---|
| Head up / down | `0x00000001` / `0x00000002` |
| Feet up / down | `0x00000004` / `0x00000008` |
| Tilt (pillow) up / down | `0x00000010` / `0x00000020` |
| Lumbar up / down | `0x00000040` / `0x00000080` |
| Release / stop | `0x00000000` |

### Presets

| Action | Keycode | Kind |
|---|---|---|
| Favorite 1 | `0x00001000` | editable recall |
| Favorite 2 | `0x00002000` | editable recall |
| Snore | `0x00004000` | fixed recall |
| Favorite 3 | `0x00008000` | editable recall |
| Flat | `0x08000000` | **held button**, not a recall |
| Memory store (arm) | `0x00010000` | **not a recall** |

The three Prodigy profiles initialize Favorite 1, Favorite 2 and Favorite 3 as editable entries.
It initializes the third wire slot as the fixed Snore entry. The integration
therefore exposes no separate Zero-G action, and never offers or accepts a save
operation for the Snore slot.

U Series instead exposes two held memory keys, a held Snore control and a held
SET key. It does not inherit the newer apps' composite favorite-programming
sequence or their four direct favorite entries. Its sleep timer independently
offers a third memory action.

`0x00010000` arms the box to overwrite a slot. It must never appear in the
recall ladder. Earlier releases of this integration used a ladder shifted one
step up (`0x2000`…`0x10000`), so every memory button recalled its neighbour and
"Memory 4" streamed the store-arm keycode for 30 seconds - which could
reprogram a slot with whatever position the bed happened to be in.

### Massage and lights

| Action | Keycode |
|---|---|
| Head massage up / down | `0x00000800` / `0x00800000` |
| Foot massage up / down | `0x00000400` / `0x01000000` |
| Massage on/off (toggle) | `0x00000100` |
| Massage wave mode step | `0x10000000` |
| Under-bed light toggle | `0x00020000` |

Massage power is a **toggle** with no discrete off, so the integration exposes
no massage-off button. The wave keycode is exposed as the massage mode-step
button.

There is no massage timer. `0x00000200` appears in the app as a constant
(`FBP_KEYCODE_M5_IN`, a fifth actuator channel) but is never bound to a control
and never written; it must not be reconstructed as a command.

## Timing and release semantics

This protocol treats held buttons and one-shot recalls very differently, and
getting the distinction wrong is the main way to break it.

**Held keycodes** (motors, flat, light, massage) stream every ~100 ms while the
button is down. On release the app emits **exactly four** keycode-`0` frames and
then goes silent. There is no distinct stop opcode; the release frame is an
ordinary frame carrying zero.

CU170 hardware testing measured a 217-218 ms motion watchdog. The integration
therefore uses unconfirmed writes and measures the 100 ms interval from the
start of each write. Awaiting a confirmed write and then sleeping 100 ms adds
the BLE round trip to every gap, which repeatedly crosses the watchdog over a
WiFi Bluetooth proxy and makes the motor stop and restart.

**One-shot recalls** (the memory slots) are a burst of **exactly 10 frames at
~100 ms**, with **no terminator at all**. The control box drives the move to
completion by itself. Appending a release frame here risks cancelling the motion
the recall just started, so successful Prodigy recalls keep that behavior.
Cancellation or write failure uses the proven zero cleanup. U Series memory
controls follow the ordinary held-key lifecycle instead.

LP Control 2.9.0 uses a 200 ms cadence for held commands where Prodigy CE uses
100 ms. The integration uses the accepted Prodigy/U Series 100 ms cadence and
retains the recorded CU170 hardware policy.

`adjustable_bed.leggett_hold_control` exposes bounded holds for flat, Snore,
lighting and massage buttons. U Series also permits memory 1, memory 2 and SET.
The existing movement services cover motor holds. These actions preserve the
held-button behavior separately from the Prodigy fixed-count favorite recalls.

## Memory programming

There is no program opcode. Storing a position is two ordinary held keycodes in
sequence:

1. hold `0x00010000` for approximately 5 seconds
2. switch directly to the selected slot for approximately 2 seconds
3. finish with the ordinary four zero frames

The app's reset and slot assignment are consecutive calls in one callback.
An intermediate zero can occur through scheduling, but the integration does not
insert a guaranteed four-zero gap between the two stages. U Series has only the
standalone held SET path, available through `leggett_hold_control`.

The shipped user guide corroborates this: "Touch Save… the massage motors will
buzz once. Within 5 seconds, touch the Favorite Position being edited."

## Notifications

The notify characteristic acknowledges accepted writes and also emits status
updates for physical-remote actions. The vendor app reconstructs a generic
LED/status bitmask from operations 6, 7, 8, 9, and 11, but only assigns UI
meaning to sleep timer (`0x8000`) and alarm (`0x4000`). No parsed value ever
influences a later command.

There is **no position, angle, percentage, motor-state or error feedback of any
kind** in either app. CU170 hardware testing confirms that the opaque bitmask
contains light state, but the app never labels that bit and the available
captures do not include a paired light-off/light-on notification. The exact
mask and polarity therefore still require that capture. Until then the
integration keeps the light as a blind toggle rather than guessing.

The integration subscribes to the main status characteristic and, for the
Prodigy profiles when present, the optional Smart Remote CSS status characteristic.
It runs the app's exact
operations 6/7/8/9/11 parser and records the resulting opaque LED mask, signed
status byte, and the two app-labelled alarm/sleep bits in protocol diagnostics.
Raw LED-mask and signed-status sensors expose the parsed values. Available
standard Device Information strings are read for diagnostics. No unlabeled bit
is assigned a new physical meaning.
Alarm and sleep-timer indicator binary sensors use the independently proven app
masks. U Series applies its app's low-byte suppression to those indicators while
preserving the raw mask unchanged.

## Sleep and alarm timers

`adjustable_bed.leggett_sleep_timer` and `adjustable_bed.leggett_alarm_timer`
start or cancel native timers. Prodigy sleep
selects a favorite and a delay of 1–1439 minutes. Its sleep command is a compact
six-byte packet under either wire revision. U Series sleep selects flat or
memory 1–3 and uses 15-minute steps through 90 minutes; its timer key follows the
selected R0/R1 encoding. All profiles support an alarm delay of 1–1440 minutes.
U Series has a different alarm-stop key from the Prodigy profiles.

The services validate the selected profile's actions and ranges before writing.
See their Home Assistant action descriptions for field names and cancellation.

## Control mode

The three Prodigy profiles expose two persistent control-box settings. U Series
does not expose these settings or initialize the optional CSS channel.

| Mode | Keycode | Lifecycle |
|---|---|---|
| Press-and-hold | `0x08010000` | 55 attempts at 100 ms, then one zero frame |
| Press-and-release | `0x01800000` | 55 attempts at 100 ms, then one zero frame |

Home Assistant exposes these as configuration buttons rather than a select,
because neither notification channel reports the currently active mode. On
boxes with the optional Smart Remote CSS service, notification setup also sends
the app's raw `01 02` initialization write.

## Provenance

Command values, framing, timing, notification parsing and release semantics
come from the accepted Phase 4 clean-room analysis of `com.leggett.prodigy4`
1.2.0 (versionCode 18, artifact SHA-256 `45922c518c9e8070…`), traced from layout
binding to the GATT boundary and independently audited. The report is COMPLETE;
the missing light-bit meaning is explicitly deferred physical validation, not
an unresolved APK-analysis path. The [whole-cluster disposition](leggett-app-disposition.md)
records all four accepted report identities, previously implemented behavior,
remaining findings, exact app differences and transport exclusions.

Unverified against hardware, and worth a capture if you have the equipment:
which frame revision real units use, whether preset recall truly ends without a
terminator, whether changing control mode also resets editable favorites on all
firmware, and which opaque notification-mask bit and polarity represent the
under-bed light.
