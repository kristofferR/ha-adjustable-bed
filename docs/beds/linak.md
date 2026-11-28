# Linak

**Status:** Partly tested (Bed Control tested on hardware, AA Control My Bed verified offline)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), jascdk and [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt)

## Known Models

For a Carpe Diem Beds receiver that uses the Vindö app, choose the
[Vindö profile](vindo.md).

- Linak DPG1M (OEM controller used in many beds)
- Bedre Nætter
- Jensen
- Auping
- Carpe Diem
- Wonderland
- Svane
- Many OEM adjustable beds with Linak motors

The integration learns which motors and features your bed has when it
connects. A retail brand or model name does not select the app profile.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Linak Bed Control](https://play.google.com/store/apps/details?id=com.linak.linakbed.ble.memory) 6.0.9 (`264`) | `com.linak.linakbed.ble.memory` |
| ✅ | [Bed Connect](https://play.google.com/store/apps/details?id=com.linak.bedconnect.iot) 5.2.4 (`253`) | `com.linak.bedconnect.iot` |
| ✅ | [AA Control My Bed](https://play.google.com/store/apps/details?id=com.americanAdjustables.AmericanAdjustablesRemote) 6.1.3 (`269`) | `com.americanAdjustables.AmericanAdjustablesRemote` |
| ✅ | [Tempur Relax Control](https://play.google.com/store/apps/details?id=fr.tempur.relaxcontrol) 6.1.3 (`269`), [profile](#tempur-relax-control) | `fr.tempur.relaxcontrol` |
| ✅ | [Carpe Diem Beds](https://play.google.com/store/apps/details?id=se.carpediembeds.controller.iot) 5.2.5 (`254`) | `se.carpediembeds.controller.iot` |
| ✅ | [Performance Series](https://play.google.com/store/apps/details?id=com.linak.leggettandplatt) 1.0 (`124`) | `com.linak.leggettandplatt` |

## Features

| Feature | Bed Control / Bed Connect | AA Control My Bed | Performance Series |
|---------|---------------------------|-------------------|--------------------|
| Motor control | Back, Legs, Head, Feet, Base, as the bed reports them | Same axes | ✅ |
| Moving two sections together | Any two available sections | Two sections selected by the actuator mask | ❌ |
| Flat | ✅ | ✅ | ✅ |
| All up | ✅ | ✅ | ❌ |
| Four memory recalls and stores | TD3/Advanced only | TD3/Advanced only | ✅ |
| Position, reported speed and four status flags | Advanced only | Advanced only | ❌ |
| Error messages | All 104 error codes | All 104 error codes | ❌ |
| Massage | Off, modes, zones and intensity | Off, modes, zones and intensity | Toggle, wave/frequency, intensity and impulse |
| AUX/under-bed light | On/off light entity | Toggle button | Toggle button |
| Automatic drive configuration | ✅ | Alarm model only | ❌ |
| BLE device rename | ✅ | ✅ | ❌ |
| Alarms | Once, alarm model only | Once or 24-hour recurrence, alarm model only | ❌ |
| Reset defaults (`4E 00`) | ✅, disabled by default | ✅, disabled by default | ✅ |
| Configuration factory reset (`7F 3E 80`) | ✅, disabled by default | ❌ | ❌ |
| Wake command | ✅ | ❌ | ❌ |
| Hold until release | [Renewable](../SERVICES.md#renewable-holds), 100 ms refresh | Renewable, 100 ms refresh | Renewable, 300 ms refresh |

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

- The analyzed BLE applications bond with the controller through
  Android/OS pairing before they use it. Bed Control's help text has the user
  unplug the bed for 60 seconds to make it ready to connect.
- Physical testing with two Advanced controllers shows that every read, write
  and subscription is refused with `Insufficient authentication` until the link
  is encrypted.
- The controller accepts an adapter it does not know only during the first 3
  minutes after power-on. In that window it advertises its control service,
  the limited-discoverable flag and a transmit power of +4 dBm, and any
  adapter can connect and pair. A session that sends commands ends the window
  early.
- Outside the window it advertises only its name, at -8 dBm, and ignores
  connection attempts from an adapter it has not paired with. An ESPHome proxy
  then reports `ESP_GATT_ERROR while connecting` (disconnect reason `0x3e`) and
  BlueZ reports `le-connection-abort-by-local`. An adapter that paired inside a
  window connects at any time afterwards. Every adapter and proxy needs its own
  pairing, and each of the two controllers accepted five at once. An adapter
  that can connect may also pair anew at any time.
- Through an ESPHome Bluetooth proxy the integration asks the proxy to encrypt
  the link right after connecting, which takes 0.2 to 0.3 seconds with the bond
  the proxy holds. Without a bond the same request starts a new pairing
  (ESP-IDF `esp_ble_set_encryption`), which takes about 0.5 seconds. A proxy
  that is not asked encrypts only when the controller
  requests it: about two seconds after a connect, about ten seconds after a
  disconnect when the reconnect is quick, and never while the under-bed light
  is on. That last case left the bed refusing all control until it was
  power-cycled.
- A BlueZ adapter encrypts the link by itself on the first refused read, also
  while the under-bed light is on, so the integration does not request pairing
  there. A post-connect readiness retry waits until the link is encrypted.
- When the bed is advertising but no connection comes up, the setup check, the
  integration's start-up message and the command error explain the pairing
  window instead of range: unplug the bed for 60 seconds, plug it back in and
  use it from Home Assistant within 3 minutes.
- A proxy that holds a stored bond only re-encrypts and never pairs again. One
  proxy stayed refused by one controller for that reason: its stored key still
  encrypted a session inside the window, but the controller no longer listed
  the proxy and refused it as soon as the window closed, after every power
  cycle. Removing the proxy's stored bond and pairing anew made the controller
  accept it.
- So the first connection through an ESPHome proxy inside a pairing window
  removes the proxy's stored bond. The proxy drops the link when it does, and
  the retry pairs anew. That command takes about 5 seconds longer, once per
  window. Outside the window a stored bond is left alone.
- Home Assistant ranks the paths by signal, earlier failures and free slots. In
  the tested setup it fell back from a refusing proxy to another one after two
  failed attempts and kept using it until Home Assistant or the proxy
  restarted.
- There is no application PIN, passkey, challenge, token or protocol encryption.

## Detection

- Bed type: the control service `99fa0001-...` or Reference Output service
  `99fa0020-...` in the advertisement, or a name of `Bed ` followed only by digits
  (for example `Bed 1696`), for beds that advertise no service UUIDs.
- Profile and model: see below. A retail brand or model name does not identify them.

## Profiles and model variants

Leave **Automatic (recommended)** or choose **Bed Control or Bed Connect app**
for either of those apps. Choose **AA Control My Bed app** in the bed-type list
if you use that app. For older beds controlled by Performance Series, choose
**Performance Series app (older bases)** under **Advanced: bed model or remote**.
The control service UUID identifies the Linak family. The explicit app choices
select AA Control My Bed and Performance Series.

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

### AA Control My Bed

The TD3 profile uses `37 00` for All up and `34 00` for Flat. Both group Back
and Legs. This requires a confirmed zero actuator mask. Advanced models use
the ordinary all-section commands and allow grouped movement on two axes
reported by the mask. Home Assistant releases movement with `FF 00`.

Rename through `adjustable_bed.rename` with a name of up to 17 UTF-16 code units.
Most characters use one unit and supplementary characters such as emoji use
two. The integration writes UTF-8 to Device Name, attempts a readback from
the same receiver, then disconnects so advertising can refresh.

The alarm requires a nonzero confirmed actuator mask and a successful Timer
subscription. `adjustable_bed.set_alarm` accepts a favorite, massage or both.
Clear the weekdays for a one-time alarm, or select all seven to request the
app's 24-hour recurrence.

| Alarm operation | Bytes or sequence | Destination |
|-----------------|-------------------|-------------|
| Enable automatic drive | `89 3B 80 01` | Configuration |
| Set event | Countdown header, then favorite and/or massage. Each action has lifetime `05` and pause `00` | Timer |
| Set recurrence | `10 00 00` for once, `10 A0 FD` for a 24-hour interval | Timer |
| Query channel 1 | `20` | Timer |
| Turn off | `89 3B 80 00`, then `40` | Configuration, then Timer |

The app sends favorite recalls, saves and its main-screen massage controls to
its primary receiver. In Home Assistant, a combined bed uses the action's
selected physical side or sides.

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

These tables describe Bed Control unless a profile is named. Tempur Relax
Control has its own [conditional release rules](#tempur-relax-control).

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
> reverse movement. Bed Control releases with `FF 00`; Tempur Relax Control
> selects its release from the primary receiver's capabilities as described below.

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
  `adjustable_bed.rename` (`rename` still works).
- Alarm setup first enables automatic drive, writes an event with one to four
  actions, writes packed recurrence, then commits with `20`. Use
  `adjustable_bed.set_alarm`; it appears only on an alarm-capable model.

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
- The app does not give a physical unit for extension or speed.

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
  handling by one count. It adds to the Bed Control 6.0.9 reference parser; it
  does not change the packet parser, status flags,
  command timing or connection policy.
- Upper endpoints retain the normal tolerance. No upper-endpoint exception is
  enabled without a hardware report.

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

- Keep **Bluetooth connection** on **Release right after each command** when using the physical remote.
- Linak holds the connection for one second after an operation, so rapid
  follow-up taps reuse the authenticated link.
- Combined actions retain both links until both sides finish, then start the
  handoff together.
- A new command renews this short window; the explicit **Disconnect** button
  bypasses it. Choosing **Stay connected for a while** uses **Seconds to stay connected** instead.
- When the link is released after each command, background position polling is also suppressed
  so it cannot reclaim the remote's connection while idle. Position feedback
  refreshes during HA operations; remote-only movements appear on the next
  connection.

### Connection readiness and retries

- Through an ESPHome proxy the link is encrypted on connect and accepts control
  on the first probe. Inside the pairing window the proxy pairs anew first. When the proxy cannot encrypt it, and on other adapters,
  the integration retries the safe STOP probe for up to 15 seconds per readiness
  request, including after interrupted startup.
- Cancellation does not mark the session ready unless a write was acknowledged,
  and deferred subscriptions resume on the next command.
- Queued commands remain serialized and STOP invalidates older pending movement.
- When HA sees multiple available connection paths, Linak allows up to five
  connection attempts so HA can fall back from a stronger but failing proxy to a
  working alternative. Retry backoff stops growing after the second retry.
- A genuinely unreachable bed still reports failure after this bounded retry
  budget.

## Profiles


### Carpe Diem Beds

**App:** [Carpe Diem Beds](https://play.google.com/store/apps/details?id=se.carpediembeds.controller.iot) 5.2.5, `se.carpediembeds.controller.iot`

**Status:** Not yet tested on hardware

#### Setup

Choose **Carpe Diem Beds app** explicitly. The shared control-service advertisement
cannot select the app. Declare two, three or four motors and whether the bed has
massage. These settings describe your bed; the reference mask does not replace
them. Add each independent bed half separately, then combine them in Home
Assistant for Left/Right targeting. No side-selector byte or mattress-product
selection is required.

#### Controls

| Feature | Supported |
|---|---|
| Movement | Back and legs; head with three motors; feet with four |
| Flat and all up | Held controls |
| Memories | Four recalls/stores when the connected model supports favorites |
| Massage | Off, back/legs/both selection, mode and intensity steps |
| Light | Toggle button, without an assumed on/off state |
| Local reset | Reset defaults button, disabled by default |
| References | Extension, speed magnitude and flags as disabled diagnostic sensors |
| Angles and position sliders | Not available for this profile |
| Hardware timer, rename and automatic-drive configuration | Not available |

Movement uses the selected-section table below. For three sections the first
matching pair wins, following the app's ordering. Selecting all four uses the
all-up or all-down command. Memory labels such as TV, Read, Sleep and Relax are
names for slots, not extra presets.

<!-- generated:linak-carpe-controls -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Control | Bytes |
|---|---|
| back down | `0A 00` |
| back up | `0B 00` |
| legs down | `08 00` |
| legs up | `09 00` |
| head down | `02 00` |
| head up | `03 00` |
| feet down | `04 00` |
| feet up | `05 00` |
| back, legs down | `34 00` |
| back, legs up | `37 00` |
| back, head down | `2D 00` |
| back, head up | `33 00` |
| back, feet down | `22 00` |
| back, feet up | `2B 00` |
| legs, head down | `2C 00` |
| legs, head up | `32 00` |
| legs, feet down | `21 00` |
| legs, feet up | `2A 00` |
| head, feet down | `20 00` |
| head, feet up | `29 00` |
| back, legs, head down | `34 00` |
| back, legs, head up | `37 00` |
| back, legs, feet down | `34 00` |
| back, legs, feet up | `37 00` |
| back, head, feet down | `22 00` |
| back, head, feet up | `2B 00` |
| legs, head, feet down | `21 00` |
| legs, head, feet up | `2A 00` |
| back, legs, head, feet down | `00 00` |
| back, legs, head, feet up | `01 00` |
| STOP / release | `FF 00` |
| Recall 1 | `0E 00` |
| Save 1 | `38 00` |
| Recall 2 | `0F 00` |
| Save 2 | `39 00` |
| Recall 3 | `0C 00` |
| Save 3 | `3A 00` |
| Recall 4 | `44 00` |
| Save 4 | `45 00` |
<!-- /generated -->

#### Timing

<!-- generated:linak-carpe-timing -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Operation | Schedule |
|---|---|
| Normal held movement | Immediate, then 300 ms |
| Favorite recall | Immediate, 25 ms initial delay, then 200 ms |
| Massage zone selection | Motor 1, 100 ms gap, motor 2 |
<!-- /generated -->

Home Assistant bounds a recall or flat/all-up action to 30 seconds and explicitly
releases its gesture on completion, cancellation or STOP. This is a Home
Assistant safety limit. The Android favorite timer ending alone does not prove
that it emits a release or sends STOP. Actual app relay finalization submits
STOP; Android lifecycle and disconnect behavior must not be used as a hardware
stop guarantee.

#### Notifications

The connected service set and exact reference mask select Standard, TD3 or
Advanced. A successful timer subscription can identify Advanced with Alarm,
but does not enable hardware timer programming in this profile. A failed mask
read leaves capabilities unresolved. Capabilities are rediscovered per link.
References decode unsigned extension counts and speed magnitude, without
converting to angles or inferring movement direction. Short reference values
clear the decoded fields to zero. Configuration and timer payloads and the read
device name remain raw diagnostics.

#### Services

Use the standard memory, massage, light and reset controls. For a bounded group
movement use `adjustable_bed.linak_move_sections` with `sections`, `direction`
and `duration_ms`. The existing two-motor action also accepts this profile with
matching directions. Both actions preserve physical side targets and send the
neutral release on the same connection that received movement.

#### Evidence

Based on Carpe Diem Beds 5.2.5 (`254`). Physical behavior needs testing.

### Tempur Relax Control

**App:** [Tempur Relax Control](https://play.google.com/store/apps/details?id=fr.tempur.relaxcontrol) 6.1.3 (`269`), `fr.tempur.relaxcontrol`

**Status:** Not yet tested on hardware

#### Setup

Choose **Tempur Relax Control app** explicitly. Its shared Linak control service
cannot distinguish this app from Bed Control or the other Linak apps. Declare
the motor count for a controller without reference outputs and enable massage
only if your bed has it. On Advanced controllers, the live actuator mask selects
the available back, legs, head, feet and base controls. Declared motor count is
used only after Standard or TD3 is resolved. An unreadable mask does not enable
movement from an assumed layout. Ordinary presses and timed actions both check
the live capabilities. Capabilities are rediscovered per connection.

If authentication initially refuses the mask, Home Assistant uses the shared
Linak bond/encryption and bounded readiness recovery before retrying it on the
same connection. Deferred notification channels resume too. Newly proven covers
and favorite buttons appear automatically, including when a later reconnect
resolves setup's missing mask. Recovery uses the existing STOP readiness probe
as Home Assistant link preparation, without inventing an app startup command.
For sequential pairs, capability recovery uses the same one-connection side
operations as movement and releases each receiver before connecting the next.

Home Assistant handles Bluetooth bonding. Add independent bed halves separately
and combine them in Home Assistant to use Left/Right targets. Each write keeps
the app's default zero side byte; this profile offers no single-address pairing.
Tempur pairs honor the selected connection topology. With concurrent links,
each refresh awaits primary (Left), then secondary (Right), followed by the
100 ms gap. A primary failure prevents the secondary write. With sequential
links, a finite operation completes on Left, releases its link, then runs on
Right. Finite Both holds work in either mode; a renewable Both hold requires
two concurrent links. Names save both local choices before ordered device writes.
A Both tap uses the primary side's Movement per tap settings for one shared
refresh plan. Per-side taps retain their own settings. The combined card's
gesture release ends its admitted hold; the explicit Stop remains separate.
Favorites, massage, automatic drive, reset and alarms belong to the primary.
The secondary exposes its movement and light controls. Cleanup on both receivers
uses the primary's alarm/TD3 flags.

#### Controls

| Feature | Available |
|---|---|
| Movement | Individual and selected sections, held flat and all up |
| Favorites | Four recalls and stores on TD3 and Advanced; none on Standard |
| Massage | Back, legs or both, off, next mode and intensity steps |
| Under-bed light | Toggle button |
| Automatic drive | Commanded-state switch, disabled by default |
| Device name | Generic rename action, up to 17 UTF-16 code units |
| Wake and reset defaults | Shared buttons; reset disabled by default |
| Position sliders and angles | Not available |
| Hardware alarms | Daily favorite and/or massage alarm on Advanced with Alarm |
| Favorite labels | Shared Name a favorite and Forget a favorite actions, saved locally |

<!-- generated:linak-tempur-controls -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Control | Bytes |
|---|---|
| Back down | `0A 00` |
| Back up | `0B 00` |
| Legs down | `08 00` |
| Legs up | `09 00` |
| Head down | `02 00` |
| Head up | `03 00` |
| Feet down | `04 00` |
| Feet up | `05 00` |
| Base down | `06 00` |
| Base up | `07 00` |
| All down (Standard / Advanced) | `00 00` |
| All up (Standard / Advanced) | `01 00` |
| All down (TD3) | `34 00` |
| All up (TD3) | `37 00` |
| Direct STOP API (see release table) | `FF 00` |
| Wake | `FE 00` |
| Light toggle | `94 00` |
| Reset defaults | `4E 00` |
| Massage off | `80 00` |
| Next massage mode | `81 00` |
| Back intensity up | `8D 00` |
| Back intensity down | `8E 00` |
| Leg intensity up | `8F 00` |
| Leg intensity down | `90 00` |
| Both intensity up | `A8 00` |
| Both intensity down | `A9 00` |
| Recall 1 | `0E 00` |
| Save 1 | `38 00` |
| Recall 2 | `0F 00` |
| Save 2 | `39 00` |
| Recall 3 | `0C 00` |
| Save 3 | `3A 00` |
| Recall 4 | `44 00` |
| Save 4 | `45 00` |
| Back massage | `89 00`, wait 100 ms, `8C 00` |
| Leg massage | `8A 00`, wait 100 ms, `8B 00` |
| Both massage zones | `89 00`, wait 100 ms, `8B 00` |
| Automatic drive on | `89 3B 80 01` |
| Automatic drive off | `89 3B 80 00` |
<!-- /generated -->

Favorites, Flat and All up support press-and-hold through the native card.
Releasing ends that gesture using the conditional policy below; explicit Stop
remains separate. Save buttons remain confirmation actions.

Native Flat and All up use the initialize-all commands on Standard and Advanced,
regardless of the actuator mask. TD3 uses the fixed Back + Legs pair. Explicit
selected-section requests use the app's ordered selector. Four selected primary axes
use All up/down, including when Base is also selected; other groups use the
first matching pair from the shared selector. The native action accepts one
direction per group. Mixed-direction SDK vectors and the modifier bit are
covered by encoder tests but do not establish an app control.

Selecting the same massage zone selection again sends global off. Two-write
zone changes are separate GATT writes; interruption can leave the first write
applied. Home Assistant clears its commanded selection when a sequence is
incomplete, including cancellation during the gap between writes. The last
commanded selection survives a routine Bluetooth release/reconnect; Reset defaults
invalidates it. This is an assumption about our commands, not measured state:
using another remote or app can change the bed independently. Automatic drive
similarly shows the last delivered command, without
claiming configuration reply confirmation. Rename uses HA's UTF-8 encoding
(the Android artifact calls its runtime default charset), without a terminator,
and reads the name back on the same connection. Names and favorite labels are
saved locally before device writes; a failed write does not roll those settings
back. Forgetting a favorite used by the alarm disables and clears that alarm.

#### Timing

<!-- generated:linak-tempur-timing -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Operation | Schedule |
|---|---|
| Movement and recall | Immediate, then 100 ms after each completed write |
| Massage zone selection | First write, 100 ms delay, second write |
| Store, light, wake, configuration, name | One write per action |
| Alarm | Event, recurrence, query: ordered completed writes, no app ACK wait |
| Reset | Clear alarm when supported, then reset |
<!-- /generated -->

Home Assistant bounds recalls and flat/all-up to 30 seconds. An admitted
movement uses the primary-selected cleanup below on completion or cancellation.
TD3 favorite release only ends refresh. For non-TD3 automatic recall, an ordinary
card release leaves the refresh running within its separate 30-second bound,
including after lease expiry. Explicit Stop ends it and dispatches the
primary-selected packet. Explicit Stop can reopen a released paired receiver;
gesture cleanup stays on its original client.
Wake is not a proven physical stop. Cleanup stays on its captured BLE session.
The app's UI guards, refresh watchdog and foreground/background lifecycle are
not hardware guarantees: its repeat loop has no STOP finally and its delayed
background disconnect has no pre-disconnect STOP.

<!-- generated:linak-tempur-release -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Primary alarm | Primary TD3 | Gesture | Automatic drive | Cleanup |
|---|---|---|---|---|
| False | False | Movement | n/a | `FF 00` |
| False | False | Recall | False | `FF 00` |
| False | False | Recall | True | End refresh, no frame |
| False | True | Movement | n/a | `FE 00` |
| False | True | Recall | False | End refresh, no frame |
| False | True | Recall | True | End refresh, no frame |
| True | False | Movement | n/a | `FE 00` |
| True | False | Recall | False | `FE 00` |
| True | False | Recall | True | End refresh, no frame |
| True | True | Movement | n/a | `FE 00` |
| True | True | Recall | False | End refresh, no frame |
| True | True | Recall | True | End refresh, no frame |
<!-- /generated -->

#### Notifications

Absence of the reference service selects Standard. A zero mask selects TD3;
a nonzero mask selects Advanced. Successful timer notification setup promotes
Advanced with Alarm. No physical model names are inferred from those modes.

Reference samples must be four bytes. Extension is unsigned little-endian and
divided by 100; signed 12-bit speed is scaled to its absolute magnitude. Their
physical units remain unknown. They appear only as disabled diagnostic speed
sensors and reference attributes, without angle conversion or direction inference.
Invalid-length samples clear these fields to zero. Control-error enum labels
are diagnostic values, not a claim that every fault can occur on your bed.

Configuration responses retain the artifact's signed length slice, ignoring
the header and trailing bytes. Configuration reads in this SDK have no current
app caller and are not controls. Automatic-drive writes wait only for GATT
completion, without inventing a configuration acknowledgement requirement.

Timer query parsing uses signed time, adds the high-time bit and reads exactly
one action with signed lifetime/pause values. Timer events and malformed replies
stay diagnostic. They do not confirm or roll back commanded alarm state.

For Set alarm, select every weekday: one-time or selected-day requests are
rejected because the source writes a fixed daily recurrence. The action writes
the event, fixed daily recurrence (31 repeats,
1440 minutes), then channel-one query, awaiting each GATT write. It does not wait
for a timer ACK. A favorite alarm asks for the shared confirmation before enabling
automatic drive. Clearing sends impulse-disable then clear; disabling automatic
drive also clears an active favorite alarm. Reset clears local favorites and
supported alarms before the reset command. Failure stops the remaining sequence;
there is no invented rollback packet.

Setting an alarm requires successful live timer discovery. Clearing a saved
active alarm requires a writable timer endpoint and can proceed even when its
notification subscription failed.

The source computes the duration to today's requested time and discards its
attempt to advance earlier times to tomorrow. This profile preserves that signed
encoding quirk, including rounding fractional negative seconds down.
Hardware interpretation of negative durations remains unverified.

#### Services

Use shared Set alarm, Name a favorite, Forget a favorite, rename and movement
actions, plus the native massage controls. Use
`adjustable_bed.linak_move_sections` for a bounded same-direction section group,
including `base` when the live mask offers it. The two-section action also
accepts matching directions. Both retain physical side targets.

#### Evidence

Based on the independently accepted full static contracts of Tempur Relax
Control 6.1.3 (`269`). All 582 frozen frame, sequence, parser, routing and discovery
cases are covered by the Tempur vector and runtime tests, with the full 256-byte
mask census. Physical effects, units and firmware behavior remain unverified.

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
  ON/OFF. Initial reference notifications were position values, not the light
  state.
- This does not prove that every firmware lacks another feedback mechanism. The
  issue reporter's TD5 (Standard profile) has not been physically tested in this
  session.
- This hardware report adds to what the app shows: the app not using those
  constants did not mean the bed rejects them. It
  does not enable other dead library commands (such as memories 5/6).
- The modern-profile ON/OFF commands also restore the pre-v4 integration behavior
  reported working in #615. They are not gated on the position-feedback service
  that distinguishes Standard from Advanced; the app's modern AUX command enum
  does not define a separate packet format for those models.

### Bed Connect exclusion

Bed Connect contains two paths. Its direct P1 BLE bed-control path corroborates
the modern control protocol and is covered by the Bed Control implementation,
including its unique configuration-level factory reset. Its P2 path provisions
and updates a separate WiFi module. P2 is intentionally and permanently out of
scope: this integration controls beds over BLE only and will not implement WiFi
provisioning, cloud control or module firmware updates.

### App features

Bed Control, Bed Connect and legacy-profile features are grouped below by
builder, lifecycle and control. Dedicated app sections describe their own gates
and release rules, including Tempur Relax Control.

| Feature | Home Assistant |
|---------|----------------|
| Bed Control discovery, app bonding and GATT session | Coordinator connection; an ESPHome proxy encrypts the link on connect, other adapters use the readiness retry; a refused connection is explained as a closed pairing window |
| STANDARD/TD3/ADVANCED/alarm capability selection | Live service/mask discovery with persisted snapshot |
| Individual, all-section and all 40 two-section movements | Covers, preset buttons and simultaneous-move service |
| STOP/release and 100 ms held-command lifecycle | Guaranteed cleanup on completion, failure and cancellation |
| Four favorite recalls and stores with model gating | Buttons and generic preset services |
| Massage zones, modes and all intensity actions | Capability-gated buttons |
| AUX/light toggle | Native controller action; legacy toggle button, modern on/off entity |
| Defaults reset and configuration factory reset | Separate buttons, both disabled by default |
| Automatic drive configuration | Assumed-state switch, disabled by default |
| Device rename | `rename` action plus advertising refresh disconnect |
| Alarm event, commit and notification states | `set_alarm` action and diagnostic sensor |
| Reference extension, flags and reported speed | Position entities, speed sensors and fault diagnostic |
| All 104 modern error values | Diagnostic sensor with raw code/payload attributes |
| Double/synchronized bed targeting | Generic paired-bed routing sends the same frames per side |
| Performance discovery, command surface and one-byte release | Explicit Performance Series profile |
| Performance opaque required notification | Subscription and raw diagnostics without invented parsing |
| Bed Connect direct-BLE P1 commands, variants and parsers | Modern controller is a superset; its unique factory reset is implemented separately |
| Bed Connect phone-local scheduled favorite/massage actions | Home Assistant scheduling invokes the same preset/massage controls |

Not supported: the Bed Connect P2 WiFi module (WiFi provisioning, cloud and
module firmware are outside this BLE-only integration), library code no app
calls (including memories 5/6), and app-local settings with no BLE effect, such
as the Performance app's child-lock preference.

### Analysis provenance

Based on Bed Control 6.0.9 (`com.linak.linakbed.ble.memory`), Bed Connect
5.2.4 (`com.linak.bedconnect.iot`), AA Control My Bed 6.1.3
(`com.americanAdjustables.AmericanAdjustablesRemote`) and Performance Series
1.0 (`com.linak.leggettandplatt`).
