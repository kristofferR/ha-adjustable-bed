# MotoMotion, MotoSleep, Power Bob, Bedgear, L2 Motion, MoodBase and ErgoBed Control

**Status:** Partly tested (existing MotoSleep HHC support user tested in [#51](https://github.com/kristofferR/ha-adjustable-bed/issues/51) and [#445](https://github.com/kristofferR/ha-adjustable-bed/issues/445); MotoMotion, Power Bob and the other MotoSleep models need testing)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), waynebowie99 and [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt)

## Known Models

- **MotoMotion:** 17 panel layouts (13 panels and four aliases). Setup finds
  devices whose Bluetooth name contains `SOFA` (15 characters long), `BT201`
  (9 characters long) or `MOTO`, anywhere in the name and case-sensitive.
- **MotoSleep / Power Bob:** beds with HHC (Hangzhou Huaci) controllers and
  Power Bob. Device names contain "HHC" (e.g., `HHC3611243CDEF`,
  `HHC0069815CDEF`).
- Binary MOTO beds with exact 28-character `MOTOB...` or `MOTOS...` names
  (MotoSleep app).
- Dedicated MotoSleep model pages: WR1140, the WRS14 series (WRS14Dmm,
  WRS14ms), WRS16ms, WRS18ms, WRS20ms, WRS20ms Swing, WRS23ms, WRS27ms, WRC30Mms
  and WR219.
- MotoMotion, MotoSleep and Power Bob are separate app profiles; pick the app
  you use. A model in one app is not assumed to match a model in another.
- **MoodBase:** HHC receivers that appear in Bob Mills Furniture’s MoodBase app.
  The app lists Bluetooth names with uppercase `HHC` and 14 UTF-16 code units.

## Apps

| Analyzed | App | Package ID | Profile |
|----------|-----|------------|---------|
| ✅ | [Leon's L2Motion](https://play.google.com/store/apps/details?id=com.leon.l2motion) | `com.leon.l2motion` | [L2 Motion](#l2-motion) |
| ✅ | [Bedgear](https://play.google.com/store/apps/details?id=com.Bedgear.AdjustableBed) 2.0.1 (`2024031901`) | `com.Bedgear.AdjustableBed` | [Bedgear](#bedgear) |
| ✅ | [MoodBase](https://play.google.com/store/apps/details?id=com.BobMills.MoodBase) 1.0.5 | `com.BobMills.MoodBase` | [MoodBase](#moodbase) |
| ✅ | [ErgoBed Control](https://play.google.com/store/apps/details?id=com.FOA.ergobed) 1.0.3 | `com.FOA.ergobed` | [ErgoBed Control](#ergobed-control) |
| ✅ | [MotoMotion](https://play.google.com/store/apps/details?id=com.HHC.MotoMotion) 3.1.9 (code 2026051101) | `com.HHC.MotoMotion` | [MotoMotion](#motomotion) |
| ✅ | [MotoSleep](https://play.google.com/store/apps/details?id=com.HHC.MotoSleep) 5.1.5 (`2026071001`) | `com.HHC.MotoSleep` | [MotoSleep](#motosleep) |
| ✅ | [Power Bob for Adjustable Bed](https://play.google.com/store/apps/details?id=com.HHC.PowerBob) 2.0.3 (`2025061101`) | `com.HHC.PowerBob` | [Power Bob](#power-bob) |

## Features

| Feature | MotoMotion | MotoSleep | Power Bob | Legacy route | Bedgear |
|---------|------------|-----------|-----------|--------------| --- |
| Motor Control | ✅ Headrest, lumbar, main, back, legrest and tilt, by panel, named as in the app | ✅ By model: back, legs, head, feet, lumbar, neck, tilt, auxiliary pairs | ✅ By model: back, legs, lumbar, tilt, auxiliary pairs | ✅ Back and legs | ✅ Motor zones, by model name |
| Position Feedback | ❌ | ❌ | ❌ | ❌ | ❌ |
| Memory Presets | ✅ 0–4 slots, recall and save, by panel | ✅ 2 slots on most profiles; none on WR219 and the smallest panels | ✅ 2 slots on most profiles; none on the smallest panels | ❌ | ✅ 0 or 2 slots; Panel E snore save |
| Zero-G / Anti-Snore / TV / Flat | Home only | ✅ By model | ✅ By model | Flat | ✅ By layout |
| Swing | ❌ | ✅ WRS20ms Swing and WR219 | ❌ | ❌ | ❌ |
| Massage | ✅ Level controls, by model name | ✅ Head/foot toggles, intensity steps, stop, by model | ✅ Head/foot toggles, intensity steps, stop, by model | ❌ | ✅ Buttons, by layout |
| Heat | ✅ Level or cycle controls, by model | ❌ | ❌ | ❌ | ❌ |
| Lights | ✅ Light cycle or toggle; RGB and timer where the panel has them | ✅ Under-bed toggle or RGB, by model | ✅ RGB settings; toggle, by model | ❌ | ✅ Toggle, RGB and shutdown minutes where the layout has them |
| Split-King Sync | ❌ | ✅ Panels F, G, H, WR1140 and the `New` variants | ❌ | ❌ | ✅ On layouts that have it |
| Music / Audio | ✅ Equalizer controls; playback buttons on some panels | ❌ Not supported, see [Notes](#notes) | ❌ Not supported | ❌ | ❌ Not supported |
| User postures | ✅ Measure positions, four saved postures, fine tuning | ❌ | ❌ | ❌ | ❌ |
| Side selection | ✅ Left/right on sofas whose name has `S` as its 11th character; remembered across reconnects | ❌ | ❌ | ❌ | ❌ No side choice; two receivers can be paired in Home Assistant |
| Binding | ✅ Bind and unbind, as the app does | ❌ | ❌ | ❌ | Not needed |

## Choosing a profile

The advertised local name selects the profile. Detection suggests `motosleep`
for an HHC or exact MOTO name. Bedgear's exact name gate adds an app candidate,
or a low-confidence candidate when no existing route matches. L2 Motion adds its
own app candidate for matching names, as do MoodBase and ErgoBed Control. See
each profile's Setup.

| Profile | Key | Bed type | Selected by |
|---------|-----|----------|-------------|
| [L2 Motion](#l2-motion) | `l2motion` | `l2motion` | Explicit app choice; original Bluetooth name selects its controls |
| [Bedgear](#bedgear) | `bedgear` | `bedgear` | Explicit app choice; exact 14-unit Bluetooth name selects the layout and independent flags |
| [MoodBase](#moodbase) | `moodbase` | `moodbase` | Explicit app choice; the original Bluetooth name selects controls |
| [ErgoBed Control](#ergobed-control) | `ergobed` | `ergobed` | Explicit app choice and a Bluetooth local name with a supported panel selector |
| [MotoMotion](#motomotion) | `motomotion` | `motomotion` | The explicit app choice; the exact Bluetooth name selects the panel and flags |
| [MotoSleep](#motosleep) | `motosleep` | `motosleep` | A name longer than 14 characters containing `HHC`, or a name starting with `MOTO` |
| [Power Bob](#power-bob) | `power_bob` | `motosleep` | An exact 14-character name containing `HHC` |
| [Legacy route](#legacy-route) | `legacy` | `motosleep` | Any other name, such as a manual entry without a usable advertised name |

Each profile keeps its own command table and timing; none reuses a sibling's.

### Aliases

None. `motomotion` and `motosleep` build different controllers.

## Wire codec

`codec/motomotion.py` builds every frame of the three apps. Which commands a
panel sends, its name flags and its timing are profile data
(`profiles/motomotion.py`, `profiles/motosleep.py`).

### Transports

MotoMotion:

| Service match | Write characteristic match | Notify characteristic match | Binding |
|---------------|----------------------------|-----------------------------|---------|
| `FFE0` | `FFE1` | Same `FFE1`, after 100 ms | `FFE2` |
| Otherwise `FFF0` | `FFF1` | `FFF2` | None |

Matches use the discovered UUID strings uppercased and containing the indicated fragment. The full discovered characteristic is retained. Later matching services may replace roles. Normal writes require a response. Only application unbinding uses write without response. Unbinding resolves FFE0/FFE1 independently, even when later FFF0 roles win for normal commands. Home Assistant/Bleak owns notification subscription and CCCD management.

MotoSleep and Power Bob prefer the following roles and retain the exact
discovered UUID:

| Role | Preferred | Fallback |
|------|-----------|----------|
| Service | `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000fff0-0000-1000-8000-00805f9b34fb` |
| Write | `0000ffe1-0000-1000-8000-00805f9b34fb` | `0000fff1-0000-1000-8000-00805f9b34fb` |
| Notify (MotoSleep) | `0000ffe2-0000-1000-8000-00805f9b34fb` | `0000fff2-0000-1000-8000-00805f9b34fb` |

Power Bob writes without response. MotoSleep HHC and MOTO binary write with
response.

### Framing and checksum

| Format | Bytes |
|--------|-------|
| A | ASCII `$#` + command padded to five decimal digits + parameter padded to five digits + numeric-digit XOR padded to five digits + `R\r` |
| B | `24 23 cmdHi cmdLo paramHi paramLo xor(bytes2..5) 41 0d` |
| C | ASCII `$#` + `M`, `T`, `B` or `V` + truncated value padded to two digits + `\r` |
| D | `41 49 4f 4b` + five big-endian saturated unsigned 16-bit targets in head/lumbar/back/base/tilt order + `52 0d` |
| E | Eight random bytes, each 0–254, without framing/checksum |
| F | `24` + one case-sensitive ASCII command letter; wrapped, `24 23 24` + letter + `52 0d` |

Padding does not truncate A/C values. B masks words to 16 bits. D saturates each word to 0–65535. No extra CRC, encryption, fragmentation or command acknowledgment layer is inferred.

- **B, MOTO binary:** command and data are unsigned 16-bit big-endian values.
  For example, standard head/back up (`0x0002`, data `0x0000`) is
  `24 23 00 02 00 00 02 41 0D`.
- **F, HHC letters:** a raw action is a dollar sign plus one case-sensitive
  command letter, such as `$K` (`24 4B`). The wrapped form of `$K` is
  `$#$KR\r`.

### Command encoders

| Encoder | Format | Used by |
| --- | --- | --- |
| `ascii_command(command, parameter)` | A | MotoMotion; MotoSleep and Power Bob RGB and sync frames |
| `binary_command(command, parameter)` | B | MotoMotion `MOTO` names; MotoSleep MOTO pages |
| `music_command(letter, value)` | C | MotoMotion |
| `Position(...).to_bytes()` | D | MotoMotion |
| `binding_code(draws)` | E | MotoMotion |
| `letter_command(letter, wrapped=...)` | F | MotoMotion's `$z` timer prefix; MotoSleep and Power Bob |

`A(c,p)` and `B(c,p)` below refer to the first two encoders. Command values are
profile data: see the [MotoMotion](#motomotion) and
[MotoSleep and Power Bob](#motosleep-and-power-bob-family) controls.

### Responses

MotoMotion parses `$`…CR notifications into status, heat, massage and RGB
state (see [MotoMotion](#motomotion)). MotoSleep and Power Bob read no
notifications and report no positions.

### STOP and release behavior

- **MotoMotion:** STOP is B(0,0) for `MOTOA` names, otherwise A(0,S), three
  writes at the same 50 ms deadline after release. The shared Home control ends
  by stopping its refresh, without a release frame.
- **MotoSleep HHC and Power Bob:** `$b` five times at 30 ms intervals on
  release, where the profile has it; other Power Bob profiles stop when the
  movement writes cease.
- **MotoSleep MOTO pages:** command/data `0x0000/0x0000` five times at 100 ms
  intervals; WR219 sends `0x9088/0x0001` six times.
- Every release uses a fresh cancel event, so cancellation cannot suppress it.

### Vectors

- `tests/motomotion_vectors.py` freezes the MotoMotion report's test vectors
  (`REPORT_VECTORS`) and every fixed frame the MotoSleep, Power Bob and legacy
  profiles send (`MOTOSLEEP_FRAMES`).
- `tests/test_motomotion_vectors.py` proves that each round-trips through the
  codec and that the MotoSleep, Power Bob and legacy profiles send exactly
  their frozen frames.

## Profiles

### MotoMotion

**App:** [MotoMotion](https://play.google.com/store/apps/details?id=com.HHC.MotoMotion) 3.1.9 (code 2026051101), `com.HHC.MotoMotion`

**Status:** Not yet tested

#### Setup

Choose **MotoMotion app** in the bed-type list; searching for MotoMotion finds it. The next question asks the exact Bluetooth local name, filled in from the advertisement when there is one. Configure asks the same name and checks it the same way. The Home Assistant display name never selects a panel. Discovery offers a candidate without overriding another app's confident match. Shared service UUIDs alone do not select this app.

- `BT201` selects binary music first. Otherwise zero-based name index 9 selects `1`, `2`, `3`, `5`, `6`, `7`, `8`, `9`, `A`, `D`, `E`, `G`, `H`, or `J`. `MM` at indices 9 and 10 selects ASCII music. Other selectors use the One panel.
- Home Assistant's automatic name index requires three literal leading characters, so its name-only hints are `SOFA*`, `BT201*` and `MOTO*`. Names with another prefix can still reach discovery through advertised service hints, or through **Pick any Bluetooth device** and manual setup. The app's case-sensitive substring rules and exact Bluetooth name remain the profile inputs; a shared service does not select the MotoMotion app automatically.

Name lengths and zero-based indices follow the app’s UTF-16 code units. A supplementary Unicode character occupies two units in both profile selection and receive routing.

Name flags are independent:

| Name condition | Behavior |
|----------------|----------|
| `SOFA`, index 10 `S` | Left parameter `S=0`, right `S=10000` |
| `SOFA`, index 12 `E` | Memory recall release requests STOP |
| `SOFA`, index 11 `B`/`D` | Light kind 1; index 11 `C` selects kind 2 |
| `SOFA`, index 13 `F` | Kind 2 still validates RGB, then sends A(300,S) |
| `SOFA`, index 14 `H` | Heat-only mode; `M` admits heat/massage tab |
| `SOFA`, index 11 `D` | RGB tab, except panel 6 with index 10 `A` |
| `SOFA`, index 10 `A` | Users/posture tab |
| `SOFA`, index 9/10 `M`, index 9 `8`, or index 10 `S` | Music tab |
| Contains `MOTO` | Shared movement uses B; STOP independently tests `MOTOA` |
| Panel Five, index 14 `M`/`X` | Main up/down use 32776/32775; its embedded heat button is hidden |

Short names that would make the app index outside the name are rejected during HA setup. Controls are available from the stored profile before connecting. Two-address pairs keep profile names, binding codes, users and settings per physical address. One-address side controls are available only for the exact S name flag and retain their child side. Parent Both operations fan out left then right; there is no native Both value or synchronized hardware operation claim.

##### Binding

Binding status uses manufacturer ID 1465 (`0x05b9`): empty data is unbound, leading `01` requests binding, other first bytes indicate bound. The app and HA reject bound devices unless the entire advertised hex suffix after the first byte exactly matches the saved code for that address. A missing or mismatched code rejects session admission before notification subscription or ordinary writes; no additional mask or firmware ACK is inferred. A binding request generates eight bytes, updates local cache and starts a persistence request before the FFE2 write. Neither the app nor HA claims that durability has completed at that point. No cached-code retransmission, auth ACK gate, PIN, or OS bond is invented.

#### Controls

`S` is a decimal parameter, never a bit mask. Tables describe app-labelled actions, without inferred motor remapping.

##### Motor Control

| Panel/action | Command up / down |
|--------------|-------------------|
| Shared headrest | A(2,S) / A(1,S); selector `2` is labelled Back in the app and always uses ASCII A(32,S) / A(16,S), including MOTO names |
| Shared lumbar | A(8,S) / A(4,S) |
| Shared main | A(128,S) / A(85,S); home A(262,S) |
| G main | A(32773,S) / A(32774,S) |
| A/H main | A(165,S) / A(64,S) |
| J/Five main | A(165,S) / A(80,S), with Five M/X override above |
| Explicit back | A(32,S) / A(16,S) |
| Five back slider | A(16,S) / A(32,S), intentionally reversed from the button bar |
| Explicit legrest | A(64,S) / A(128,S) |
| Six main | A(1445,S) / A(80,S), or B(1445,0) / B(80,0) |
| Six tilt | A(337,S) / A(338,S), or B(512,0) / B(256,0) |
| Shared binary headrest / lumbar / back / legrest | B(2/1,0), B(128/64,0), B(32/16,0), B(8/4,0) |
| STOP | B(0,0) for `MOTOA`; otherwise A(0,S), three writes at the same 50 ms deadline |

##### Memory

| Panel | Available hardware memories |
|-------|-----------------------------|
| One (including aliases), Three, Five, J | 2 |
| G | 4 |
| D | 1 exposed slot, using the app's M2 command |
| E | 1 |
| Six | 1, or none when its heat-only center is selected |
| A, Seven, H, ASCII/binary music | None |

| Action | Command |
|--------|---------|
| Recall slots 1/2/3/4 | A(256,S), A(257,S), A(32779,S), A(32780,S) |
| Program slots 1/2/3/4 | A(263,S), A(264,S), A(33052,S), A(33053,S) |
| D single exposed memory | Recall A(257,S), program A(264,S) |
| E program | A(33050,0), then A(263,S) after 300 ms |
| Six binary recall/program | B(32777,0) / B(33050,0) |
| Program/release button | A(0,S) |
| D memory/lumbar combined gesture | Wait 3000 ms, then A(33050,0); programming remains an explicit separate action |

##### Massage, Heat and Lights

| Action | Commands |
|--------|----------|
| Heat levels 0–3 | A(335/332/333/334,S) |
| Massage levels 0–3 | A(353/350/351/352,S) |
| Five heat cycle | A([332,333,334][heat % 3],S) |
| H heat cycle | A([332,334,335][heat % 3],S); CM heat 3 displays as 2, HSW is unchanged |
| Six heat cycle | A([335,332,333,334][(heat + (2 if heat==1 else 1)) & 3],S) |
| D lumbar, unknown / known zero | A(33055,0) at 0/100/200 ms / once |
| D lumbar, known nonzero | A(33050,0), then A(16,0) after 300 ms |
| E lumbar | A(352,0) if unknown/zero, otherwise A(353,0), at 0/100/200 ms |
| D/E light cycle | A(32787+next,0), `next` in 1–8; off A(32787,0) |
| Kind 1 light | A(262,S) |
| Kind 2 light | RGB zero total selects white (120 each), nonzero selects black (0 each), or A(300,S) for flag F |
| RGB | A(315/316/317,S+level), level=floor(channel/255*120), values below 10 become 0 |
| RGB timer | Literal `24 7a`, then A(32999,seconds) after 50 ms; off 0, enable default 15, picker 0–120 minutes and 0–59 seconds |

Level up/down normalizes received 4 to 0, then bounds to 0–3. D/E light cycling wraps each signed 64-bit increment before remainder modulo nine and maps zero to one. RGB zero testing wraps each intermediate signed 64-bit addition. Invalid strings fail before a new command. Partial receive stores can change the next action without an event.

##### Music and Postures

| Action | Command / range |
|--------|-----------------|
| Binary music initialization | B(10,0), B(8,0) |
| Binary play / next / previous | B(14,0) / B(12,0) / B(13,0) |
| Binary volume / treble / bass / vibration | B(9,v), B(1,v) then B(2,v) after 50 ms, B(3,v), B(4,v); ranges 0–63 / 0–31 / 0–31 / 0–31 |
| ASCII channels | C(M/T/B/V,value); ranges volume 0–22, other channels 0–15 |
| Music modes | Custom, wide, electric, live; volume retained; binary seven writes spaced 50 ms, ASCII concatenates four frames |
| User posture / fine tune | One full D frame, raw Hall targets; no degree feedback |
| Application unbinding | Literal `$#005001234500004R\r`, without response; disconnect after 1000 ms |

#### Timing

Held movement refreshes every 100 ms, first write after 100 ms. HA button presses are bounded to one second; the hold action accepts an explicit duration. STOP cleanup uses a fresh cancellation event. The shared Home control refreshes every 100 ms and ends by stopping refresh, without a release frame. The controller owns the first-tick and release timing; the card adds no extra delay. Card gesture release cancels the admitted hold and lets that hold own its cleanup; a separate explicit STOP still sends the source STOP packets. Normal settings are one-shots; source nonrepeat controls use a 200 ms delay. RGB components are sent at 0/100/200 ms. Notify callbacks and pending commands are tied to the current connection session.

The selected side and posture, current music mode/EQ, RGB timer and user-owned working Hall targets survive an idle disconnect and controller replacement. Working targets belong to the selected user, posture and current measurements; changing those inputs invalidates the working edit while saved custom postures stay with their user. Raw helper targets retain their full 16-bit domain, including values outside an individual edit slider's range. Live bed feedback and connection/hold state are refreshed for each session.

A malformed saved posture requires an explicit valid posture selection before posture controls can move the bed. Malformed optional working/music/timer state is handled locally and cannot reset a valid side selection. Restoring preferences sends no BLE settings or movement frames.

HA deliberately cancels delayed writes on release/cancellation, always performs admitted movement cleanup, and separates saving from recall. The shipped app can retain a delayed write after release, suppress queued STOP on re-press, or recall on the release of a save gesture. Those hazards are not reproduced.

#### Notifications

The framer waits for `$` then CR, discards preceding noise and the entire coalesced suffix, and clears the buffer before parsing. It strips all characters other than ASCII digits/spaces, then splits literal spaces, retaining empty tokens. Supported token counts: 11, 16, 24, 31, 37, 38, 39, 42, 43, 50, 62 and 71. Count 43 emits two events.

The status sensor retains RGB/D/comfort/HSW fields and parse errors. Heat, massage, lift/calibration flags and the unidentified `field_1b` remain protocol state, not invented angle sensors. Completed stores survive later parse failures. Events are asynchronous names and read current state when delivered. Numeric consumers accept nonnegative signed-64-bit decimal values with arbitrarily many leading zeroes; actual overflow and empty fields fail in source order.

#### Services

The `adjustable_bed.motomotion` action manages named local users and postures. `dimensions` is `[height, buttocks_height, knee_height]` in centimetres. All must be finite. The Height number accepts 122 to 271 cm, the span of the app's pickers (140 to 220 cm, or 4 ft 0 in to 8 ft 11 in). The Upright, Recline, TV and Lie flat buttons each select that posture and move the bed to it in one press, as tapping a posture does in the app; they need the selected user's measurements or a saved custom posture. The Posture select only stores the choice and never moves the bed, so a scene can restore it safely; Recall posture then sends it. A posture becomes the selection, and its targets become available to Save posture, only once its frame has reached the bed. The four posture keys are `upright`, `recline`, `tv`, and `lay`. Fine-tuning targets require all five keys: head 0–863, base 0–3174, back 0–1454, lumbar 0–874, tilt 0–629. Generated head targets can reach 867; that source mismatch is preserved. Local custom saves do not program hardware memory. Switching user or posture invalidates unsent working targets; a save request must match the user and posture that own those targets.

#### Evidence

MotoMotion 3.1.9: its test vectors round-trip through the codec.

### MotoSleep and Power Bob family

**Status:** Partly tested (the original HHC models are tested; the other models need testing)

This integration follows the controller routing in the two shipped Android
apps. It does not treat every device using the shared HHC UUID as one universal
bed. The advertised local name selects the transport, motor layout, presets,
features, and STOP behavior.

- **Existing HHC support:** ✅ User tested
- **Expanded model matrix:** needs testing on hardware. Owners of these beds can help confirm
  them. The apps show what they send, but not how every firmware and actuator
  behaves.

#### Setup

Detection: a local name starting with `HHC`, a name of at least 14 characters
containing `HHC`, or an exact MOTO bed name selects the `motosleep` bed type.

Character positions in these sections are zero-based string indexes, matching
the apps' `localName[index]` expressions. For example, `HHC0069815CDEF` has `1`
at index 8 and `5` at index 9, which selects the Power Bob A15 panel.

- Power Bob accepts an exact 14-character name containing `HHC`. Characters 8
  and 9 select 14 root panel profiles (see [Power Bob](#power-bob)).
- Current MotoSleep HHC names (longer than 14 characters) use characters 16,
  18, 22, and 26 to select 21 panel profiles, raw versus wrapped writes,
  conditional axes, and `New` variants (see [MotoSleep](#motosleep)).
- Binary MOTO beds use exact 28-character `MOTOB...` or `MOTOS...` names
  matching `^MOTO(B|S)(\d{2})(\w)([0-9])([BCD])([A-Za-f])(\w)(\w)(\w)`.
  Character 7 selects ten bed pages: WRS23ms, WRS14Dmm, WRS18ms, WRS14ms,
  WRS20ms, WRS16ms, WRC30Mms, WRS27ms, WRS20ms Swing, and WR219.
- Advertised-name matching and model routing normalize letter case, including
  selector letters. Protocol command letters remain case-sensitive.
- Unmatched Power Bob selectors and malformed MOTO names receive no speculative
  controls. Legacy manual configurations without a usable advertised name keep
  a conservative two-axis fallback (see [Legacy route](#legacy-route)); current
  long HHC names retain the app's PanelOne default route.
- AUDIO and MotoAMP names are intentionally not bed controllers.

#### Controls

"All four presets" means Flat `$O`, Anti-snore `$R`, TV `$S` and Zero-G `$T`;
"memory" means recall `$U`/`$V` and save `$Z`/`$a`.

##### HHC Motor Control

| Command | Bytes | ASCII | Description |
|---------|-------|-------|-------------|
| Main head/back up | `24 4B` | `$K` | |
| Main head/back down | `24 4C` | `$L` | |
| Legs/feet up | `24 4D` | `$M` | |
| Legs/feet down | `24 4E` | `$N` | |
| Auxiliary pair 1 up | `24 70` | `$p` | Lumbar, tilt or auxiliary, per profile |
| Auxiliary pair 1 down | `24 71` | `$q` | |
| Auxiliary pair 2 up | `24 50` | `$P` | Lumbar, tilt, neck or auxiliary, per profile |
| Auxiliary pair 2 down | `24 51` | `$Q` | |
| Explicit motor STOP | `24 62` | `$b` | Sent on release where the profile has it |

Availability and axis meaning are profile-specific. In particular, the Power
Bob A15 profile selected by `HHC0069815CDEF` labels uppercase `$P/$Q` as
lumbar. Lowercase `$p/$q` is not the manual lumbar pair for that bed. This is
the root cause of [issue #445](https://github.com/kristofferR/ha-adjustable-bed/issues/445).

##### HHC Presets and Memory

| Command | Bytes | ASCII |
|---------|-------|-------|
| Home/Flat | `24 4F` | `$O` |
| Anti-Snore | `24 52` | `$R` |
| TV | `24 53` | `$S` |
| Zero-G | `24 54` | `$T` |
| Memory 1 recall | `24 55` | `$U` |
| Memory 2 recall | `24 56` | `$V` |
| Save Memory 1 | `24 5A` | `$Z` |
| Save Memory 2 | `24 61` | `$a` |

##### HHC Light, Massage and Other

| Command | Bytes | ASCII | Description |
|---------|-------|-------|-------------|
| Light toggle | `24 41` | `$A` | |
| Head massage | `24 43` | `$C` | Standard panels |
| Foot massage | `24 42` | `$B` | Standard panels |
| Massage stop | `24 44` | `$D` | |
| Extended head intensity up | `24 47` | `$G` | |
| Extended head intensity down | `24 48` | `$H` | |
| Extended foot intensity up | `24 45` | `$E` | |
| Extended foot intensity down | `24 46` | `$F` | |
| Extended head massage toggle | `24 4A` | `$J` | PanelZero equivalent of `$C` |
| Extended foot massage toggle | `24 49` | `$I` | PanelZero equivalent of `$B` |
| Panel E auxiliary action | `24 57` | `$W` | Exposed as `Auxiliary action` |

> [!WARNING]
> Earlier versions of this document listed `$Y`/`$X`/`$W` as Save Zero-G, Save
> TV and Save Anti-Snore, `$z` as a sync toggle, `$J`/`$I` as head/foot massage
> off, and `$P`/`$p` as neck/lumbar on every bed. The apps show `$W` is
> only Panel E's unlabelled action and `$X`/`$Y` are not sent by any profile.
> `$z` is an initialization-only query that the wrapped path drops and the
> integration does not send; sync uses the numeric MainPanel frames below.

Where an app has a command pair but no single physical
label across models, Home Assistant uses `Auxiliary`, `Auxiliary 1`, or
`Auxiliary 2`. This preserves app-defined controls without guessing that
they are lumbar, neck, or tilt. Real users can provide model-specific hardware
confirmation after release. Panel E's exact `$W` callsite is likewise
preserved as an `Auxiliary action` button. The APK does not provide a
trustworthy physical label, so the integration does not invent one.

##### Numeric frames (RGB and sync)

- Both apps scale each RGB component from 0..255 to 0..120. Red, green, and
  blue use decimal selectors `00315`, `00316`, and `00317`, with 20 ms between
  writes.
- Power Bob places selector before value, A(selector,value); MotoSleep places
  value before selector, A(value,selector). Values are five decimal digits.
- Both XOR the decimal digits and append a five-digit decimal checksum plus
  `R\r`, after a `$#` prefix. Example (MotoSleep, red 255): `$#001200031500004R\r`.
- RGB channels are absolute: a non-zero color turns the LEDs on and three zero
  channels turn them off. On RGB profiles, Home Assistant treats them as the
  light's on/off control and does not send the unrelated `$A` toggle.
- MotoSleep's MainPanel sync frame is `$#` + opcode + `00000` + checksum +
  `R\r`, A(opcode,0): enable sends `00012` (`$#000120000000003R\r`), disable
  sends `00015` (`$#000150000000004R\r`).

#### Timing

- Movement actions repeat at 100 ms while active (the configured motor pulse
  count bounds a Home Assistant cover movement).
- Power Bob sends its first movement pulse after the first 100 ms interval; it
  does not send an immediate pulse on press.
- Current MotoSleep HHC sends `$b` five times at 0, 30, 60, 90, and 120 ms on
  release.
- Power Bob sends that STOP schedule only on the profiles whose release paths
  contain `$b`. Other Power Bob profiles stop when periodic movement writes
  cease.
- Presets, memory, light, and massage actions are single writes.
- The STOP schedule uses a fresh cancel event so cancellation cannot suppress it.

> [!NOTE]
> Older documentation described HHC movement as one command per press and a
> `$b` STOP sent 3 times with a 50 ms delay. The apps and the current
> code use the schedule above.

#### Evidence

Based on MotoSleep 5.1.5 and Power Bob 2.0.3; the legacy route sends the pre-v5
controller's frames. See [Analysis provenance](#analysis-provenance).

### MotoSleep

**App:** [MotoSleep](https://play.google.com/store/apps/details?id=com.HHC.MotoSleep) 5.1.5 (`2026071001`), `com.HHC.MotoSleep`

**Status:** Partly tested (the original HHC models are tested; the other profiles and MOTO binary pages need testing)

Behaves as the [MotoSleep and Power Bob family](#motosleep-and-power-bob-family), except as below.

#### Setup

##### HHC profiles (names longer than 14 characters)

First matching rule wins (char 16 alone unless char 18 is listed). Every HHC
profile releases with `$b`. "New" variants have `I` at char 26. MotoSleep
normally sends the raw form; names with `localName[22] == "M"` wrap a short
action such as `$K` as `$#$KR\r`.

| Profile | Rule (char 16, char 18) | Motors (up/down) | Presets and memory | Light, massage, extras |
|---|---|---|---|---|
| F | `F` | Back `$K`/`$L`, legs `$M`/`$N` | All four, memory | `$A`; massage `$C`/`$B`/`$D`; sync |
| G | `G` | Back, legs, lumbar `$p`/`$q` | All four, memory | `$A`; massage `$C`/`$B`/`$D`; sync |
| H | `H` | Back, legs, tilt `$p`/`$q` | All four, memory | `$A`; massage `$C`/`$B`/`$D`; sync |
| A | `1`+`5`, or `A` | Back, legs, plus lumbar `$p`/`$q` when char 26 is `H`, otherwise tilt `$P`/`$Q` | All four, memory | `$A` |
| One | `1` (char 18 not `5`), `4`+`6`, or any unmatched char 16 | Back | Flat | None |
| D | `3`+`5`, `3`+`6`, `4`+`5`, `8`+`5`, or `C` | Back, legs, plus one pair (`$p`/`$q` when char 26 is `H`, otherwise `$P`/`$Q`): neck (`3`+`5`), tilt (`3`+`6`, `8`+`5`), lumbar (`4`+`5`), auxiliary (`C`) | All four, memory | `$A`; massage `$C`/`$B`/`$D` |
| Four | `4`, `2`+`5`, `5`+`5`, or `B` | Back, legs, auxiliary 1 `$p`/`$q`, auxiliary 2 `$P`/`$Q` | All four, memory | `$A`; massage `$C`/`$B`/`$D` |
| WR1140 | `9` with char 18 `5`–`8` | Back, legs, lumbar `$p`/`$q`, auxiliary `$P`/`$Q` | All four, memory | `$A`; RGB; massage `$C`/`$B`/`$D`; sync |
| Zero | `0` | Back, legs, lumbar `$p`/`$q`, tilt `$P`/`$Q` | Flat, memory | `$A`; RGB; massage `$J`/`$I`, `$G`/`$H`, `$E`/`$F` |
| Two | `2` | Back, legs, auxiliary 1 `$p`/`$q`, auxiliary 2 `$P`/`$Q` | Flat, memory | `$A`; massage `$C`/`$B`/`$D` |
| Three | `3`, `6`+`5`, or `7`+`5` | Back | All four, memory | `$A` |
| Five / Five New | `5` | Back | Flat | New: RGB, sync |
| Six / Six New | `6` | Back, legs | Flat; New adds Zero-G `$T` | New: RGB, sync |
| Seven | `7` | Back, legs | Flat, memory | `$A`; massage `$C`/`$B`/`$D` |
| Eight / Eight New | `8` | Back, legs | All four, memory | `$A`; New: RGB, sync |
| Nine | `9` | Back, legs | Flat | None |
| Six ZG | `D` | Back, legs | Zero-G `$T` | None |
| E | `E` | Back | Flat, anti-snore | `$A`; auxiliary action `$W` |

##### MOTO binary pages (28-character names)

**MOTO binary status:** needs testing on hardware

Every page except WR219 has Flat `0x800E`, Anti-snore `0x8009`, TV `0x800A`,
Zero-G `0x800B`, memory recall `0x800C`/`0x800D` and save `0x811D`/`0x811E`.
Motor labels follow each page's app buttons.

| Char 7 | Page | Motors (up/down) | Extras |
|---|---|---|---|
| `0` | WRS23ms | Back `0x0002`/`0x0001`, legs `0x0200`/`0x0100`, head `0x0020`/`0x0010`, lumbar `0x0080`/`0x0040`, feet `0x0008`/`0x0004` | |
| `1` | WRS14Dmm | Back `0x0020`/`0x0010`, legs `0x0200`/`0x0100`, head `0x0002`/`0x0001` | |
| `2` | WRS18ms | Back `0x0002`/`0x0001`, legs `0x0200`/`0x0100`, lumbar `0x0080`/`0x0040`, feet `0x0008`/`0x0004` | |
| `3` | WRS14ms | Back `0x0002`/`0x0001`, legs `0x0200`/`0x0100`, feet `0x0008`/`0x0004` | |
| `4` | WRS20ms | Back `0x0002`/`0x0001`, legs `0x0200`/`0x0100`, head `0x0020`/`0x0010`, lumbar `0x0080`/`0x0040`, feet `0x0008`/`0x0004` | |
| `5` | WRS16ms | Back `0x0002`/`0x0001`, legs `0x0200`/`0x0100`, feet `0x0008`/`0x0004` | |
| `6` | WRC30Mms | Neck `0x0020`/`0x0010`, back `0x0002`/`0x0001`, lumbar `0x0080`/`0x0040`, legs `0x0008`/`0x0004` | |
| `7` | WRS27ms | Back `0x0002`/`0x0001`, legs `0x0008`/`0x0004`, lumbar `0x0080`/`0x0040` | |
| `8` | WRS20ms Swing | Back `0x0002`/`0x0001`, legs `0x0200`/`0x0100`, head `0x0020`/`0x0010`, lumbar `0x0080`/`0x0040`, feet `0x0008`/`0x0004` | Swing `0x8014` |
| `9` | WR219 | Back `0x000A`/`0x0005`, lumbar `0x0200`/`0x0100`, legs `0x00A0`/`0x0050` | Flat `0x5555`, Anti-snore `0x8009`, Zero-G `0x800B`, swing `0x9089`; no TV or memory |

#### Controls

##### MOTO Binary Commands

Every command is B(command,data). Model profiles select the exposed axes from
the exact app page controls, including WRC30M neck/back/lumbar/foot axes and
WR219's distinct motor values. Common fixed commands include:

| Function | Command |
|----------|---------|
| Standard head/back up/down | `0x0002` / `0x0001` |
| Standard legs up/down | `0x0008` / `0x0004` |
| MotoB/Swing legs up/down | `0x0200` / `0x0100` |
| MotoS back up/down | `0x0020` / `0x0010` |
| Anti-snore, TV, zero gravity | `0x8009`, `0x800A`, `0x800B` |
| Memory 1, memory 2, flat | `0x800C`, `0x800D`, `0x800E` |
| Save memory 1/2 | `0x811D`, `0x811E` |
| WRS20 Swing | `0x8014` |
| WR219 flat, swing | `0x5555`, `0x9089` |
| Normal release | `0x0000` / data `0x0000` |
| WR219 release | `0x9088` / data `0x0001` |

#### Timing

Normal MOTO movement release sends command/data `0x0000/0x0000` five times at
100 ms intervals. WR219 sends `0x9088/0x0001` six times at 100 ms intervals.

### Power Bob

**App:** [Power Bob for Adjustable Bed](https://play.google.com/store/apps/details?id=com.HHC.PowerBob) 2.0.3 (`2025061101`), `com.HHC.PowerBob`

**Status:** Not yet tested

Behaves as the [MotoSleep and Power Bob family](#motosleep-and-power-bob-family), except as below.

#### Setup

##### Power Bob profiles (14-character names)

First matching rule wins. Power Bob always sends raw actions. Every profile
except Panel Seven and Panel Eight also routes to the RGB settings.

| Profile | Rule (chars 8, 9) | Motors (up/down) | Presets and memory | Light and massage | Release STOP |
|---|---|---|---|---|---|
| A15 | `15`, or char 8 `A` | Back `$K`/`$L`, legs `$M`/`$N`, lumbar `$P`/`$Q` | All four, memory | `$A` | None |
| D345 | char 8 `3`/`4`/`8` with `5`, or char 8 `C` | Back, legs, auxiliary `$P`/`$Q` | Flat, memory | `$A`; massage `$C`/`$B`/`$D` | None |
| Four | char 8 `4`, `25`, `55`, or char 8 `B` | Back, legs, auxiliary 1 `$p`/`$q`, auxiliary 2 `$P`/`$Q` | All four, memory | `$A`; massage `$C`/`$B`/`$D` | `$b` |
| WR1140 | char 8 `9` with `5`–`8` | Back, legs, lumbar `$p`/`$q`, auxiliary `$P`/`$Q` | All four, memory | `$A`; massage `$C`/`$B`/`$D` | `$b` |
| Zero | char 8 `0` | Back, legs, lumbar `$p`/`$q`, tilt `$P`/`$Q` | Flat, memory | `$A`; massage `$J`/`$I`, `$G`/`$H`, `$E`/`$F` | None |
| One | char 8 `1` | Back | Flat | None | `$b` |
| Two | char 8 `2` | Back, legs, auxiliary 1 `$p`/`$q`, auxiliary 2 `$P`/`$Q` | Flat, memory | `$A`; massage `$C`/`$B`/`$D` | `$b` |
| Three | char 8 `3` | Back, legs | All four, memory | `$A` | `$b` |
| Five | char 8 `5` | Back | None | None | None |
| Six | char 8 `6` | Back, legs | None | None | None |
| Seven | char 8 `7` | Back, legs | Flat, memory | `$A` only, no RGB; massage `$C`/`$B`/`$D` | None |
| Eight | char 8 `8` | Back, legs | All four (`$O` per [issue #468](https://github.com/kristofferR/ha-adjustable-bed/issues/468)), memory | `$A` only, no RGB | None |
| Nine | char 8 `9` | Back, legs | Flat | None | `$b` |
| Six ZG | char 8 `D` | Back, legs | None | None | `$b` |

- Short HHC names that select Power Bob Panel Eight retain Home as `$O`. A
  user-confirmed device uses this shared command, matching the
  MotoSleep 5.1.5 PanelEight action even though Power Bob 2.0.3 does not render
  that action on its separate Panel Eight
  ([issue #468](https://github.com/kristofferR/ha-adjustable-bed/issues/468)).
- The same user-confirmed Panel Eight hardware exposes its under-bed light as
  the root `$A` toggle. It does not support the generic Power Bob RGB settings,
  so Home Assistant keeps the toggle button and does not expose RGB controls
  ([issue #470](https://github.com/kristofferR/ha-adjustable-bed/issues/470)).
- A reported Panel Seven bed has a single-colour light that ignores the RGB
  settings, so Home Assistant sends the root `$A` toggle and exposes no RGB
  controls. The toggle is not yet confirmed on that bed
  ([issue #973](https://github.com/kristofferR/ha-adjustable-bed/issues/973)).

The Power Bob app's RGB settings route is independent of the selected root
motor panel. Advertised-name character 10 selects the Mood configuration when
it is `D` and the Night configuration otherwise. Showing them in the generic
settings UI does not by itself mean the connected hardware implements those
numeric commands: the user-confirmed Panel Eight compatibility profile supports
only its root `$A` light toggle.

### Legacy route

**Status:** Not yet tested (the fallback for manual entries without a usable advertised name)

Behaves as the [MotoSleep and Power Bob family](#motosleep-and-power-bob-family), except as below.

#### Setup

Manual configurations created before model routing had no reliable local name.
Any name that selects neither app keeps their prior two-axis behavior, without
speculative auxiliary, massage, light, memory, or sync entities.

#### Controls

Back `$K`/`$L`, legs `$M`/`$N`, Flat `$O` and STOP `$b`, each wrapped as
`$#$KR\r` and written with response. STOP follows the MotoSleep HHC release
schedule.

### Bedgear

**App:** [Bedgear](https://play.google.com/store/apps/details?id=com.Bedgear.AdjustableBed) 2.0.1 (`2024031901`), `com.Bedgear.AdjustableBed`

**Status:** Not yet tested

#### Setup

Choose **Bedgear app** during setup and enter the exact Bluetooth local name.
Configure can update that name. Eligible names contain uppercase `HHC` anywhere
and have exactly 14 UTF-16 code units. Case matters. The advertised name adds
Bedgear as an app candidate; it does not replace an existing MotoSleep route.
Manual model titles do not select a protocol.

The primary layout and feature gates are independent. Name index 10 other than
`B` enables the light shutdown timer; `D` also enables RGB and brightness.
Index 11 `E` enables alarm settings, while `M` wraps short commands and
suppresses the query. Index 13 `X` enables synchronization settings. These
indices are zero-based UTF-16 positions.

GATT selection matches uppercase UUID strings containing `FFE0` and `FFE1`.
The last matching characteristic receives writes, without response. Every
matching characteristic is subscribed. HA/Bleak manages CCCD and Bluetooth
connection retries. No application PIN, authentication or startup query is sent.

<!-- generated:bedgear-layouts -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Panel selector example (name[8:10]) | Layout | Motor zones | Memory slots | Presets |
|---|---|---|---|---|
| 15 | PanelA | head, foot, lumbar | 2 | flat, anti_snore, tv, zero_g |
| 35 | PanelD | head, foot, neck | 2 | flat |
| E1 | PanelE | actuator | 0 | anti_snore |
| 81 | PanelEight | head, foot | 2 | flat, anti_snore, tv, zero_g |
| 51 | PanelFive | actuator | 0 | flat |
| 44 | PanelFour | neck, head, lumbar, foot | 2 | flat, anti_snore, tv, zero_g |
| 91 | PanelNine | head, foot | 0 | flat |
| 13 | PanelOne | neck, head, foot | 0 | flat |
| 71 | PanelSeven | head, foot | 2 | flat |
| 61 | PanelSix | head, foot | 0 | flat |
| D1 | PanelSixZG | head, foot | 0 | zero_g |
| 34 | PanelThree | neck, head, lumbar, foot | 2 | flat, anti_snore, tv, zero_g |
| 23 | PanelTwo | neck, head, foot | 2 | flat |
| 01 | PanelZero | head, foot, combined, tilt | 2 | flat |
| 97 | WR1140 | neck, head, lumbar, foot | 2 | flat, anti_snore, tv, zero_g |
<!-- /generated -->

#### Controls

Motor covers expose the selected head, foot, neck, lumbar, tilt, combined or
single-actuator controls. The card supports renewable holds; `timed_move` gives
a finite movement. Presets, memory recall and memory save appear only on layouts
that provide them. Buttons expose light toggle and the layout's massage controls.
SixZG has a Zero-G preset without an guessed Flat action. There are no measured
motor positions or absolute seeks.

The layout selector gives pair rules priority: 15, then 35/45/85, then index 8
`4` or 25/55, then 95–98, then 65/75, then single-character layout rules.
One/Two accept head or head+foot or neck+head+foot. Three/Four additionally use
source-selected lumbar/tilt arrays. No hidden axis is exposed merely because
its command appears in a switch branch.

<!-- generated:bedgear-controls -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Control | Plain bytes | M-name bytes | Press | Release |
|---|---|---|---|---|
| head up | `24 4B` | `24 23 24 4B 52 0D` | 100 ms refresh | stop |
| head down | `24 4C` | `24 23 24 4C 52 0D` | 100 ms refresh | stop |
| foot up | `24 4D` | `24 23 24 4D 52 0D` | 100 ms refresh | stop |
| foot down | `24 4E` | `24 23 24 4E 52 0D` | 100 ms refresh | stop |
| lumbar up | `24 50` | `24 23 24 50 52 0D` | 100 ms refresh | stop |
| lumbar down | `24 51` | `24 23 24 51 52 0D` | 100 ms refresh | stop |
| preset flat | `24 4F` | `24 23 24 4F 52 0D` | 100 ms refresh | fallback |
| preset anti snore | `24 52` | `24 23 24 52 52 0D` | 100 ms refresh | fallback |
| preset tv | `24 53` | `24 23 24 53 52 0D` | 100 ms refresh | fallback |
| preset zero g | `24 54` | `24 23 24 54 52 0D` | 100 ms refresh | fallback |
| memory 1 | `24 55` | `24 23 24 55 52 0D` | 100 ms refresh | none |
| memory 2 | `24 56` | `24 23 24 56 52 0D` | 100 ms refresh | none |
| light toggle | `24 41` | `24 23 24 41 52 0D` | once | none |
| neck up | `24 50` | `24 23 24 50 52 0D` | 100 ms refresh | stop |
| neck down | `24 51` | `24 23 24 51 52 0D` | 100 ms refresh | stop |
| massage head | `24 43` | `24 23 24 43 52 0D` | once | none |
| massage foot | `24 42` | `24 23 24 42 52 0D` | once | none |
| massage stop | `24 44` | `24 23 24 44 52 0D` | once | none |
| actuator up | `24 4B` | `24 23 24 4B 52 0D` | 100 ms refresh | stop |
| actuator down | `24 4C` | `24 23 24 4C 52 0D` | 100 ms refresh | stop |
| preset anti snore | `24 52` | `24 23 24 52 52 0D` | 100 ms refresh | none |
| lumbar up | `24 70` | `24 23 24 70 52 0D` | 100 ms refresh | stop |
| lumbar down | `24 71` | `24 23 24 71 52 0D` | 100 ms refresh | stop |
| preset flat | `24 4F` | `24 23 24 4F 52 0D` | 100 ms refresh | none |
| preset tv | `24 53` | `24 23 24 53 52 0D` | 100 ms refresh | none |
| preset zero g | `24 54` | `24 23 24 54 52 0D` | 100 ms refresh | none |
| combined up | `24 70` | `24 23 24 70 52 0D` | 100 ms refresh | stop |
| combined down | `24 71` | `24 23 24 71 52 0D` | 100 ms refresh | stop |
| tilt up | `24 50` | `24 23 24 50 52 0D` | 100 ms refresh | stop |
| tilt down | `24 51` | `24 23 24 51 52 0D` | 100 ms refresh | fallback |
| massage head up | `24 47` | `24 23 24 47 52 0D` | 100 ms refresh | fallback |
| massage head down | `24 48` | `24 23 24 48 52 0D` | 100 ms refresh | fallback |
| massage head stop | `24 4A` | `24 23 24 4A 52 0D` | 100 ms refresh | fallback |
| massage foot up | `24 45` | `24 23 24 45 52 0D` | 100 ms refresh | fallback |
| massage foot down | `24 46` | `24 23 24 46 52 0D` | 100 ms refresh | fallback |
| massage foot stop | `24 49` | `24 23 24 49 52 0D` | 100 ms refresh | fallback |
<!-- /generated -->

#### Timing

<!-- generated:bedgear-timing -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Behavior | Value |
|---|---|
| First held tick and interval | 100 ms, no immediate write |
| Motor STOP | 5 writes, 30 ms apart |
| Short up, fewer than five ticks and no custom up | 3 extra writes, 100 ms apart |
<!-- /generated -->

Motor releases use STOP except Zero tilt-down, whose normal short up can repeat
the movement command and whose cancellation only ends refresh. Presets use their
own release policy. Memory recalls and LCD presets end refresh without a STOP;
classical presets and Zero massage buttons can use the short-up fallback.

The first-tick delay above applies to renewable card gestures. Finite Home
Assistant holds send their first pulse immediately, then refresh at 100 ms
intervals within the requested duration. This keeps short memory and motor
actions usable despite event-loop wake latency. Expired queued pulses are
discarded; the captured gesture still owns its normal release policy.

HA serializes commands. Each action captures its BLE session, so cancellation,
reconnection or controller replacement cannot send delayed writes on a new link.
The RGB transaction captures one requested color and completes in source order;
it avoids the app's overlapping mutable timer chains. No phone timer or local
LCD animation is exposed as a measured bed value.

#### Notifications

Only received RGB, light minutes, alarm time/strength and bind/synchronization
fields become state. Disconnect clears them. The receiver preserves the source's
first-chunk CR deferral, pre-CR byte removal, dollar-suffix buffering and literal
space splitting. HA bounds the buffer and rejects malformed numeric projections.
The app emits its `OK` event only for a successful 39-token response; this is not
an acknowledgement for a particular command. Other known response lengths are
44, 71 and 75 tokens.

#### Services

`adjustable_bed.bedgear` accepts `device_id`, optional physical `side`, and:

| Operation | Parameters and behavior |
| --- | --- |
| `rgb` | `rgb: [red, green, blue]` (0–255), `brightness` (0–1). Brightness scales the channels before 0–120 conversion. Red below 10, green/blue below 30 become zero. Sends red, green, then blue with the source queries and delays. |
| `light_timer` | `minutes: 0..1439`. Zero disables shutdown; 10 is the app's on-switch value. This is minutes, not brightness. |
| `sync_mode` | `wired: false` selects wireless, true wired. Requires `confirm: true`. This is bed synchronization, not Bluetooth pairing or network membership. |
| `toggle_sync` | Requires a received available bind state. The current active/inactive state selects the source command. |
| `save_memory` | `slot: 1..2`, subject to layout. Optional `recall_on_release: true` sends recall after save, matching the source's up-before-rebuild branch. |
| `save_snore` | Panel E only, sends save without a release recall. Use the separate held anti-snore preset to recall. |

Set the alarm with `set_alarm`: `time`, `enabled` and optional
`massage_intensity` 1 or 2 (the alarm strength); disabling sends strength 0
with the time the bed reported, when it has reported one.
The alarm gate is name character 11 `E`. There is no weekday or repeat
parameter.

Memory saves default to save only. Panel E snore save has no release-send branch.
HA does not reproduce a race against a Flutter widget rebuild. Synchronization does not select another Bluetooth
address; independent paired beds retain HA's normal physical-side routing.

#### Evidence

Row A12's accepted Bedgear 2.0.1 frames match the shared HHC codec byte for byte,
including six-plus-four-digit alarm fields. All selected layouts have their own
Bedgear profile rules. The app does not confirm physical movement,
STOP completion or firmware compatibility. External owners can
qualify those behaviors with timestamps, GATT details and physical observations.


### L2 Motion

**App:** [Leon's L2Motion](https://play.google.com/store/apps/details?id=com.leon.l2motion)

**Status:** Not yet tested

#### Setup

Choose **L2 Motion app** for beds controlled by Leon's L2Motion app. Setup and
Reconfigure ask for the bed's exact Bluetooth name, which decides the controls;
there are no motor or massage questions. A combined bed keeps each side's name.

Choose **L2 Motion app** and enter the original Bluetooth name exactly, including case.
Names contain `HHC` and have exactly fourteen UTF-16 units. Display renames do not
change the layout. Matching names are app candidates; choose the app actually used
with the bed. Each physical side keeps its own name when combining two entries.

The service UUID is selected by an uppercase substring match for `FFE0`, and all
characteristics matching `FFE1` are subscribed. Writes use the actual last matching
characteristic with no response. No application handshake or startup write is sent.

#### Controls

The name selects the layout, axes, memory capacity, presets and massage
controls below. A shared UUID does not grant another app's controls.

<!-- generated:l2motion-layouts -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Name selector example | Layout | Motor zones | Memory slots | Presets |
|---|---|---|---|---|
| 15 | PanelA | head, foot, lumbar | 2 | flat, anti_snore, tv, zero_g |
| 35 | PanelD | head, foot, neck | 2 | flat |
| E1 | PanelE | head | 0 | flat, anti_snore |
| 81 | PanelEight | head, foot | 2 | flat, anti_snore, tv, zero_g |
| 51 | PanelFive | head | 0 | flat |
| 44 | PanelFour | neck, head, lumbar, foot | 2 | flat, anti_snore, tv, zero_g |
| 91 | PanelNine | head, foot | 0 | flat |
| 13 | PanelOne | neck, head, foot | 0 | flat |
| 71 | PanelSeven | head, foot | 2 | flat |
| 61 | PanelSix | head, foot | 0 | flat |
| D1 | PanelSixZG | head, foot | 0 | zero_g |
| 34 | PanelThree | neck, head, lumbar, foot | 2 | flat, anti_snore, tv, zero_g |
| 23 | PanelTwo | neck, head, foot | 2 | flat |
| 01 | PanelZero | head, foot, combined, tilt | 2 | flat |
| 97 | WR1140 | neck, head, lumbar, foot | 2 | flat, anti_snore, tv, zero_g |
<!-- /generated -->

<!-- generated:l2motion-controls -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Control | Plain bytes | M-name bytes | Press | Release |
|---|---|---|---|---|
| head up | `24 4B` | `24 23 24 4B 52 0D` | Periodic | stop |
| head down | `24 4C` | `24 23 24 4C 52 0D` | Periodic | stop |
| foot up | `24 4D` | `24 23 24 4D 52 0D` | Periodic | stop |
| foot down | `24 4E` | `24 23 24 4E 52 0D` | Periodic | stop |
| lumbar up | `24 50` | `24 23 24 50 52 0D` | Periodic | stop |
| lumbar down | `24 51` | `24 23 24 51 52 0D` | Periodic | stop |
| preset flat | `24 4F` | `24 23 24 4F 52 0D` | Periodic | fallback |
| preset anti snore | `24 52` | `24 23 24 52 52 0D` | Periodic | fallback |
| preset tv | `24 53` | `24 23 24 53 52 0D` | Periodic | fallback |
| preset zero g | `24 54` | `24 23 24 54 52 0D` | Periodic | fallback |
| memory 1 | `24 55` | `24 23 24 55 52 0D` | Periodic | none |
| memory 2 | `24 56` | `24 23 24 56 52 0D` | Periodic | none |
| light toggle | `24 41` | `24 23 24 41 52 0D` | Completed tap | none |
| neck up | `24 50` | `24 23 24 50 52 0D` | Periodic | stop |
| neck down | `24 51` | `24 23 24 51 52 0D` | Periodic | stop |
| massage head | `24 43` | `24 23 24 43 52 0D` | Once on press | none |
| massage foot | `24 42` | `24 23 24 42 52 0D` | Once on press | none |
| massage stop | `24 44` | `24 23 24 44 52 0D` | Once on press | none |
| preset anti snore | `24 52` | `24 23 24 52 52 0D` | Periodic | none |
| lumbar up | `24 70` | `24 23 24 70 52 0D` | Periodic | stop |
| lumbar down | `24 71` | `24 23 24 71 52 0D` | Periodic | stop |
| preset flat | `24 4F` | `24 23 24 4F 52 0D` | Periodic | none |
| preset tv | `24 53` | `24 23 24 53 52 0D` | Periodic | none |
| preset zero g | `24 54` | `24 23 24 54 52 0D` | Periodic | none |
| combined up | `24 70` | `24 23 24 70 52 0D` | Periodic | stop |
| combined down | `24 71` | `24 23 24 71 52 0D` | Periodic | stop |
| tilt up | `24 50` | `24 23 24 50 52 0D` | Periodic | stop |
| tilt down | `24 51` | `24 23 24 51 52 0D` | Periodic | fallback |
| massage head up | `24 47` | `24 23 24 47 52 0D` | Periodic | fallback |
| massage head down | `24 48` | `24 23 24 48 52 0D` | Periodic | fallback |
| massage head stop | `24 4A` | `24 23 24 4A 52 0D` | Periodic | fallback |
| massage foot up | `24 45` | `24 23 24 45 52 0D` | Periodic | fallback |
| massage foot down | `24 46` | `24 23 24 46 52 0D` | Periodic | fallback |
| massage foot stop | `24 49` | `24 23 24 49 52 0D` | Periodic | fallback |
<!-- /generated -->

Toggle light sends a completed tap only. Save position actions save directly,
without arming a subsequent action or automatically recalling it. The single-axis
anti-snore layout also has **Save anti-snore position**. The phone's programming
gesture can recall after saving only when its current widget still permits that
release; a rebuild that clears programming suppresses the recall. HA saves
directly and does not assume the phone's widget state or rebuild order.

The lighting page is available unless name character 10 is `B`. Color and brightness
are unavailable when character 11 is `D`, while the light timer remains available.
RGB changes scale the selected channels by brightness, then apply the channel
thresholds. **Light timer** sends minutes immediately and shows received timer
minutes. Incoming values can exceed the range accepted for setting the timer.

Character 11 `M` enables sound controls and letter wrapping. Volume and vibration
remain adjustable in every sound mode; treble and bass can be changed only in
Custom. Choosing a mode sends the current volume and that mode's current treble,
bass and vibration together. Changed vibration survives switching away and back
within the session. Sound controls show successfully sent intent, not readback;
local unsent drafts are never entities.

<!-- generated:l2motion-auxiliary -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Setting | Value or frame |
|---|---|
| First periodic tick and interval | 100 ms |
| Motor release | 5 writes, 30 ms apart |
| Short normal-UP filler | 3 writes, 100 ms apart |
| Red / green / blue at full scale | `24 23 30 30 33 31 35 30 30 31 32 30 30 30 30 30 34 52 0D`; `24 23 30 30 33 31 36 30 30 31 32 30 30 30 30 30 37 52 0D`; `24 23 30 30 33 31 37 30 30 31 32 30 30 30 30 30 36 52 0D` |
| Light timer, 10 minutes | `24 23 30 30 33 31 39 30 30 30 31 30 30 30 30 31 30 52 0D` |
| Synchronization on / off | `24 23 30 30 30 31 32 30 30 30 30 30 30 30 30 30 33 52 0D`; `24 23 30 30 30 31 35 30 30 30 30 30 30 30 30 30 34 52 0D` |
| Wireless / wired synchronization | `24 23 33 33 30 34 39 30 30 30 30 30 30 30 30 31 33 52 0D`; `24 23 33 33 30 34 39 30 30 30 30 31 30 30 30 31 32 52 0D` |
| Alarm 06:30, strengths off / 1 / 2 | `24 23 30 36 33 30 30 30 30 30 31 37 30 30 30 30 33 52 0D`; `24 23 30 36 33 30 30 30 30 31 31 38 30 30 30 31 33 52 0D`; `24 23 30 36 33 30 30 30 30 32 31 39 30 30 30 31 35 52 0D` |
| Initial custom sound, volume 11 | `24 23 4D 31 31 0D 24 23 54 31 31 0D 24 23 42 31 31 0D 24 23 56 31 31 0D 52 0D` |
| Initial vocal sound, volume 11 | `24 23 4D 31 31 0D 24 23 54 31 30 0D 24 23 42 30 35 0D 24 23 56 30 35 0D 52 0D` |
| Initial cinema sound, volume 11 | `24 23 4D 31 31 0D 24 23 54 31 38 0D 24 23 42 31 36 0D 24 23 56 31 35 0D 52 0D` |
| Initial entertainment sound, volume 11 | `24 23 4D 31 31 0D 24 23 54 31 35 0D 24 23 42 31 39 0D 24 23 56 31 37 0D 52 0D` |
<!-- /generated -->

#### Timing

Periodic controls wait for the first timer tick. Arrows add no movement write on
release. Their cleanup drains the five-write STOP sequence on normal release and
cancellation. Short normal releases add filler only for periodic controls with
fewer than five ticks and no release callback. Cancellation and failed writes
never add filler. A finite hold includes its final due periodic tick when the
timer wakes less than one interval late; a write queued past the deadline is
discarded. Missed periods are not replayed after slow writes.
PanelZero tilt-down deliberately lacks tilt-up's STOP callback. Preset callbacks
can end refresh without a release packet; no extra hardware frame is added.

Color writes query before each channel, delay before each non-M channel, then
wait between channels. Busy updates use the latest requested color with a replaced
debounce. Each channel callback reads the current requested fields. The
integration drains a color sequence in its serialized command lane before
starting the debounced final sequence. Timer and alarm writes query, then
wait before sending. All delayed work retains its original physical session;
reconnection cannot redirect old writes to a replacement bed.

#### Notifications

The stream parser preserves the app's fragmented-message behavior, including
ignoring a terminator in an initial packet and removing the byte before a later
terminator. Only token counts 39, 44, 71 and 75 update state. RGB, light timer and
alarm time/strength are projected from their own offsets; synchronization is
available only after the bed reports support. Unknown synchronization values and
raw color state stay in diagnostics. The bed reports no position, firmware or
movement feedback. There is no command acknowledgement correlation.

#### Services

Use `set_alarm` with time, `enabled` and optional `massage_intensity` 1 or 2.
Disabling maps to strength 0, with the time the bed reported when it has one. The alarm gate is name character 11 `E`; weekdays,
extra slots, wake actions, dates and timezone settings are unsupported.

`l2motion` sets RGB color/brightness or synchronization mode. Changing wired or
wireless synchronization requires name character 13 `X` and `confirm: true`.
The synchronization switch requires received support. Synchronization never
selects a left or right receiver and does not enable concurrent motor movement.
Use the standard memory, timed-movement and held-control actions for motion.

#### Evidence

Based on Leon's L2Motion 2.0.2 (`com.leon.l2motion`).


### MoodBase

**App:** [MoodBase](https://play.google.com/store/apps/details?id=com.BobMills.MoodBase) 1.0.5, `com.BobMills.MoodBase`

**Status:** Not yet tested on a physical bed.

#### Setup

Choose **MoodBase app** and keep the receiver’s Bluetooth name exactly as the
app shows it. The name contains uppercase `HHC` anywhere and is 14 UTF-16
code units long. Positions 9 and 10 select the button layout. Other characters
independently enable the extra axis command pair, light and timer, vibration,
alarm, or synchronization settings. The name and the shared FFE0 service can
offer MoodBase as an app choice. Choose the app explicitly because other HHC
apps use the same receiver identifiers. One Bluetooth connection controls one
receiver. Separate receivers can be combined in Home Assistant with their own
Bluetooth names.

On the live connection the selected service must contain `FFE0` and its
write characteristic `FFE1`, case-insensitively. The receiver must also expose
notifications on a matching characteristic for status. The integration binds
writes and notifications to that connection.

<!-- generated:moodbase-layouts -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Name selector | Layout | Axes and letter pairs | Memory slots | Presets |
|---|---|---|---|---|
| 15 | PanelA | head (K/L), foot (M/N), lumbar (P/Q) | 2 | flat, anti snore, tv, zero g |
| 15 / H | PanelA | head (K/L), foot (M/N), lumbar (p/q) | 2 | flat, anti snore, tv, zero g |
| 35 | PanelD | head (K/L), foot (M/N), neck (P/Q) | 2 | flat |
| 35 / H | PanelD | head (K/L), foot (M/N), neck (p/q) | 2 | flat |
| E1 | PanelE | head (K/L) | 0 | flat, anti snore |
| 81 | PanelEight | head (K/L), foot (M/N) | 2 | flat, anti snore, tv, zero g |
| 51 | PanelFive | head (K/L) | 0 | flat |
| 44 | PanelFour | neck (P/Q), head (K/L), lumbar (p/q), foot (M/N) | 2 | flat, anti snore, tv, zero g |
| 91 | PanelNine | head (K/L), foot (M/N) | 0 | flat |
| 13 | PanelOne | neck (P/Q), head (K/L), foot (M/N) | 0 | flat |
| 71 | PanelSeven | head (K/L), foot (M/N) | 2 | flat |
| 61 | PanelSix | head (K/L), foot (M/N) | 0 | flat |
| D1 | PanelSixZG | head (K/L), foot (M/N) | 0 | zero g |
| 34 | PanelThree | neck (P/Q), head (K/L), lumbar (p/q), foot (M/N) | 2 | flat, anti snore, tv, zero g |
| 23 | PanelTwo | neck (P/Q), head (K/L), foot (M/N) | 2 | flat |
| 01 | PanelZero | head (K/L), foot (M/N), combined (p/q), tilt (P/Q) | 2 | flat |
| 97 | WR1140 | neck (P/Q), head (K/L), lumbar (p/q), foot (M/N) | 2 | flat, anti snore, tv, zero g |
| 25 | PanelFour | head (K/L), lumbar (P/Q), foot (M/N) | 2 | flat, anti snore, tv, zero g |
| 55 | PanelFour | neck (P/Q), head (K/L), foot (M/N), tilt (p/q) | 2 | flat, anti snore, tv, zero g |
| 65 | PanelThree | head (K/L), lumbar (P/Q), foot (M/N) | 2 | flat, anti snore, tv, zero g |
| 75 | PanelThree | neck (P/Q), head (K/L), lumbar (p/q), foot (M/N) | 2 | flat, anti snore, tv, zero g |
| 95 | WR1140 | head (K/L), foot (M/N), tilt (P/Q) | 2 | flat, anti snore, tv, zero g |
| 96 | WR1140 | head (K/L), foot (M/N) | 2 | flat, anti snore, tv, zero g |
| 98 | WR1140 | head (K/L), lumbar (p/q), foot (M/N) | 2 | flat, anti snore, tv, zero g |
| 41 | PanelFour | head (K/L) | 2 | flat, anti snore, tv, zero g |
| 42 | PanelFour | head (K/L), foot (M/N) | 2 | flat, anti snore, tv, zero g |
| 43 | PanelFour | neck (P/Q), head (K/L), foot (M/N) | 2 | flat, anti snore, tv, zero g |
| 31 | PanelThree | head (K/L) | 2 | flat, anti snore, tv, zero g |
| 32 | PanelThree | head (K/L), foot (M/N) | 2 | flat, anti snore, tv, zero g |
| 11 | PanelOne | head (K/L) | 0 | flat |
| 12 | PanelOne | head (K/L), foot (M/N) | 0 | flat |
| 21 | PanelTwo | head (K/L) | 2 | flat |
| 22 | PanelTwo | head (K/L), foot (M/N) | 2 | flat |
| 45 | PanelD | head (K/L), foot (M/N), lumbar (P/Q) | 2 | flat |
| 45 / H | PanelD | head (K/L), foot (M/N), lumbar (p/q) | 2 | flat |
| 85 | PanelD | head (K/L), foot (M/N), tilt (P/Q) | 2 | flat |
| 85 / H | PanelD | head (K/L), foot (M/N), tilt (p/q) | 2 | flat |
| C1 | PanelD | head (K/L), foot (M/N), neck (P/Q) | 2 | flat |
| C1 / H | PanelD | head (K/L), foot (M/N), neck (p/q) | 2 | flat |
| B1 | PanelFour | head (K/L), foot (M/N) | 2 | flat, anti snore, tv, zero g |
| Z4 | PanelOne | neck (P/Q), head (K/L), foot (M/N) | 0 | flat |
<!-- /generated -->

#### Controls

The layout adds only its own motor zones, presets, numbered memories, light
toggle and massage buttons. Panel E saves its anti-snore position through a
separate confirmed button. The timer appears with an `M` in position 12. RGB
color and brightness additionally need `D` in position 11. The under-bed toggle
is a separate control. Position 11 `B` enables vibration, position 12 `E`
enables the alarm, and position 14 `X` enables wired or wireless settings.
The synchronization switch becomes available when the receiver reports bound
bases. To change wired or wireless mode, wait for an unbound report on the
current connection. There is no motor-position feedback.

<!-- generated:moodbase-controls -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Control | Plain bytes | M-name bytes | Gesture | Release |
|---|---|---|---|---|
| head up | `24 4B` | `24 23 24 4B 52 0D` | Periodic | stop |
| head down | `24 4C` | `24 23 24 4C 52 0D` | Periodic | stop |
| foot up | `24 4D` | `24 23 24 4D 52 0D` | Periodic | stop |
| foot down | `24 4E` | `24 23 24 4E 52 0D` | Periodic | stop |
| lumbar up | `24 50` | `24 23 24 50 52 0D` | Periodic | stop |
| lumbar down | `24 51` | `24 23 24 51 52 0D` | Periodic | stop |
| preset flat | `24 4F` | `24 23 24 4F 52 0D` | Periodic | fallback |
| preset anti snore | `24 52` | `24 23 24 52 52 0D` | Periodic | fallback |
| preset tv | `24 53` | `24 23 24 53 52 0D` | Periodic | fallback |
| preset zero g | `24 54` | `24 23 24 54 52 0D` | Periodic | fallback |
| memory 1 | `24 55` | `24 23 24 55 52 0D` | Periodic | none |
| memory 2 | `24 56` | `24 23 24 56 52 0D` | Periodic | none |
| light toggle | `24 41` | `24 23 24 41 52 0D` | Completed tap | none |
| lumbar up | `24 70` | `24 23 24 70 52 0D` | Periodic | stop |
| lumbar down | `24 71` | `24 23 24 71 52 0D` | Periodic | stop |
| neck up | `24 50` | `24 23 24 50 52 0D` | Periodic | stop |
| neck down | `24 51` | `24 23 24 51 52 0D` | Periodic | stop |
| massage head | `24 43` | `24 23 24 43 52 0D` | Direct | none |
| massage foot | `24 42` | `24 23 24 42 52 0D` | Direct | none |
| massage stop | `24 44` | `24 23 24 44 52 0D` | Direct | none |
| neck up | `24 70` | `24 23 24 70 52 0D` | Periodic | stop |
| neck down | `24 71` | `24 23 24 71 52 0D` | Periodic | stop |
| preset anti snore | `24 52` | `24 23 24 52 52 0D` | Periodic | none |
| preset flat | `24 4F` | `24 23 24 4F 52 0D` | Periodic | none |
| preset tv | `24 53` | `24 23 24 53 52 0D` | Periodic | none |
| preset zero g | `24 54` | `24 23 24 54 52 0D` | Periodic | none |
| combined up | `24 70` | `24 23 24 70 52 0D` | Periodic | stop |
| combined down | `24 71` | `24 23 24 71 52 0D` | Periodic | stop |
| tilt up | `24 50` | `24 23 24 50 52 0D` | Periodic | stop |
| tilt down | `24 51` | `24 23 24 51 52 0D` | Periodic | fallback |
| massage head up | `24 47` | `24 23 24 47 52 0D` | Direct | none |
| massage head down | `24 48` | `24 23 24 48 52 0D` | Direct | none |
| massage head stop | `24 4A` | `24 23 24 4A 52 0D` | Direct | none |
| massage foot up | `24 45` | `24 23 24 45 52 0D` | Direct | none |
| massage foot down | `24 46` | `24 23 24 46 52 0D` | Direct | none |
| massage foot stop | `24 49` | `24 23 24 49 52 0D` | Direct | none |
| tilt up | `24 70` | `24 23 24 70 52 0D` | Periodic | stop |
| tilt down | `24 71` | `24 23 24 71 52 0D` | Periodic | stop |
| tilt down | `24 51` | `24 23 24 51 52 0D` | Periodic | stop |
| save memory 1 | `24 5A` | `24 23 24 5A 52 0D` | Direct | none |
| save memory 2 | `24 61` | `24 23 24 61 52 0D` | Direct | none |
| save anti-snore position | `24 57` | `24 23 24 57 52 0D` | Direct | none |
| motion stop | `24 62` | `24 23 24 62 52 0D` | Direct | five writes |
| status query | `24 7A` | suppressed | Direct | never sent on M |
<!-- /generated -->

#### Timing

Motion sends periodic pulses and uses STOP on release or cancellation where
the layout defines it. Panel Zero tilt-down refreshes while held and can send
the short-release repeat, without an automatic STOP for that direction.
Other presets and memory recall stop refreshing when released. Saving a
position sends its own command without also recalling it.

RGB channels are sent in order in a serialized command. Brightness scales
the requested color before the channel conversion. Turning off the RGB
light sends zero for all channels. A zero-minute timer turns the timer off;
turning it on from its switch sets the default duration.

<!-- generated:moodbase-auxiliary -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Behavior | Value or example bytes | Notes |
|---|---|---|
| Service and write/notify channel | `0000ffe0-0000-1000-8000-00805f9b34fb` / `0000ffe1-0000-1000-8000-00805f9b34fb` | Case-insensitive identifier substrings; write without response |
| Held controls | First tick at 100 ms; repeat every 100 ms | STOP, where used, sends 5 writes 30 ms apart |
| Short release fallback | 3 extra frames 100 ms apart | Only after a completed release with fewer than five ticks and no release callback |
| Red | `24 23 30 30 31 32 30 30 30 33 31 35 30 30 30 30 34 52 0D` | Maximum channel value at +0 ms nominally |
| Green | `24 23 30 30 31 32 30 30 30 33 31 36 30 30 30 30 37 52 0D` | Maximum channel value at +100 ms nominally |
| Blue | `24 23 30 30 31 32 30 30 30 33 31 37 30 30 30 30 36 52 0D` | Maximum channel value at +200 ms nominally |
| Light timer on | `24 23 30 30 30 31 30 30 30 33 31 39 30 30 30 31 30 52 0D` | Set 10 minutes, after 50 ms |
| Light timer off | `24 23 30 30 30 30 30 30 30 33 31 39 30 30 30 31 31 52 0D` | Set zero, after 50 ms |
| Light timer maximum | `24 23 30 31 34 33 39 30 30 33 31 39 30 30 30 30 34 52 0D` | Minutes from 0 to 1439 |
| Alarm off | `24 23 30 37 33 30 30 30 30 30 31 37 30 30 30 30 32 52 0D` | 07:30 example, 50 ms after query |
| Alarm strength 1 | `24 23 30 37 33 30 30 30 30 31 31 38 30 30 30 31 32 52 0D` | 07:30 example, 50 ms after query |
| Alarm strength 2 | `24 23 30 36 34 35 30 30 30 32 31 39 30 30 30 31 33 52 0D` | 06:45 example, 50 ms after query |
| Synchronize bases | `24 23 30 30 30 31 32 30 30 30 30 30 30 30 30 30 33 52 0D` | Available when the bed reports bound and unsynchronized |
| Stop synchronization | `24 23 30 30 30 31 35 30 30 30 30 30 30 30 30 30 34 52 0D` | Available when the bed reports bound and synchronized |
| Wireless mode | `24 23 33 33 30 34 39 30 30 30 30 30 30 30 30 31 33 52 0D` | Sync settings when unbound |
| Wired mode | `24 23 33 33 30 34 39 30 30 30 30 31 30 30 30 31 32 52 0D` | Sync settings when unbound |
| Vibration | `24 23 56 32 32 0D` | Level 0–22; M names add the shared envelope |
<!-- /generated -->

#### Notifications

The same connection carries status. The receiver parser starts at a dollar
marker, retains partial chunks and uses the first carriage return in an active
chunk. Supported status sizes are 39, 44, 71 and 75 space-separated fields.
They can report RGB and timer minutes. A 75-field message also carries alarm
time and strength. A 39-field message carries synchronization and binding
status. Receive state is scoped to the connection.

#### Services

Use [hold control](../SERVICES.md#hold_control) for finite holds and
[set alarm](../SERVICES.md#set_alarm) for the bed’s alarm. The bed’s
wired/wireless controls synchronize motion between bases. The app’s nickname
is local to the app, and Home Assistant’s device name can be edited in device
settings.

#### Evidence

Based on MoodBase 1.0.5. The HHC letter, decimal and vibration frames share the
MotoMotion codec. See [the MoodBase literal vectors](../../tests/test_moodbase_vectors.py).

### ErgoBed Control

**App:** [ErgoBed Control](https://play.google.com/store/apps/details?id=com.FOA.ergobed) 1.0.3, `com.FOA.ergobed`

**Status:** Not yet tested on hardware.

#### Setup

Choose **ErgoBed Control app** and enter the exact Bluetooth name shown in the
app. The local name must contain uppercase `HHC` and be 14 UTF-16 code units
long. The characters at indices 8 and 9 select the panel. Setup can offer the
app from a matching local name even if Home Assistant shows a different cached
name. Automatic name-based discovery uses the `HHC` prefix. For a name with
`HHC` elsewhere, use the nearby device picker or enter the name manually.
Choose the app explicitly. Each receiver keeps its own name when combining two
Bluetooth devices.

The receiver uses one characteristic for notifications and writes without
response. Home Assistant starts notifications even with position sensing
disabled. This profile exposes no motor position feedback.

#### Controls

Each panel exposes its own axes, presets, memory, lamp button and massage
controls. PanelZero sends a single command for the combined head-and-foot
control shown in the app. Axis labels follow the app's controls and illustrations.
The receiver's actual range, motion and response to release need hardware
confirmation.

<!-- generated:ergobed-layouts -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Selector examples | Panel | Motor controls | Presets | Memory slots |
|---|---|---|---|---|
| 01 | PanelZero | head (K/L), foot (M/N), combined (p/q), tilt (P/Q) | flat | 2 |
| 11 | PanelOne | head (K/L) | flat | 0 |
| 12 | PanelOne | head (K/L), foot (M/N) | flat | 0 |
| 13, 19 | PanelOne | neck (P/Q), head (K/L), foot (M/N) | flat | 0 |
| 15, A1 | PanelA | head (K/L), foot (M/N), lumbar (P/Q) | flat, anti snore, tv, zero g | 2 |
| 21 | PanelTwo | head (K/L) | flat | 2 |
| 22, 29 | PanelTwo | head (K/L), foot (M/N) | flat | 2 |
| 23 | PanelTwo | neck (P/Q), head (K/L), foot (M/N) | flat | 2 |
| 25 | PanelFour | head (K/L), lumbar (P/Q), foot (M/N) | flat, anti snore, tv, zero g | 2 |
| 31 | PanelThree | head (K/L) | flat, anti snore, tv, zero g | 2 |
| 32, 34 | PanelThree | head (K/L), foot (M/N) | flat, anti snore, tv, zero g | 2 |
| 33 | PanelThree | neck (P/Q), head (K/L), foot (M/N) | flat, anti snore, tv, zero g | 2 |
| 35, C1 | PanelD | head (K/L), foot (M/N), neck (P/Q) | flat | 2 |
| 41 | PanelFour | head (K/L) | flat, anti snore, tv, zero g | 2 |
| 42, 46, B1 | PanelFour | head (K/L), foot (M/N) | flat, anti snore, tv, zero g | 2 |
| 43 | PanelFour | neck (P/Q), head (K/L), foot (M/N) | flat, anti snore, tv, zero g | 2 |
| 44 | PanelFour | neck (P/Q), head (K/L), lumbar (p/q), foot (M/N) | flat, anti snore, tv, zero g | 2 |
| 45 | PanelD | head (K/L), foot (M/N), lumbar (P/Q) | flat | 2 |
| 51 | PanelFive | head (K/L) | flat | 0 |
| 55 | PanelFour | neck (P/Q), head (K/L), foot (M/N), tilt (p/q) | flat, anti snore, tv, zero g | 2 |
| 61 | PanelSix | head (K/L), foot (M/N) | flat | 0 |
| 65 | PanelThree | head (K/L), lumbar (P/Q), foot (M/N) | flat, anti snore, tv, zero g | 2 |
| 71 | PanelSeven | head (K/L), foot (M/N) | flat | 2 |
| 75 | PanelThree | neck (P/Q), head (K/L), lumbar (p/q), foot (M/N) | flat, anti snore, tv, zero g | 2 |
| 81 | PanelEight | head (K/L), foot (M/N) | flat, anti snore, tv, zero g | 2 |
| 85 | PanelD | head (K/L), foot (M/N), tilt (P/Q) | flat | 2 |
| 91 | PanelNine | head (K/L), foot (M/N) | flat | 0 |
| 95 | WR1140 | head (K/L), foot (M/N), tilt (P/Q) | flat, anti snore, tv, zero g | 2 |
| 96 | WR1140 | head (K/L), foot (M/N) | flat, anti snore, tv, zero g | 2 |
| 97 | WR1140 | neck (P/Q), head (K/L), lumbar (p/q), foot (M/N) | flat, anti snore, tv, zero g | 2 |
| 98 | WR1140 | head (K/L), lumbar (p/q), foot (M/N) | flat, anti snore, tv, zero g | 2 |
| D1 | PanelSixZG | head (K/L), foot (M/N) | zero g | 0 |
<!-- /generated -->

<!-- generated:ergobed-controls -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Control | Bytes | Writes |
|---|---|---|
| head up | `24 4B` | First tick, then every 100 ms |
| head down | `24 4C` | First tick, then every 100 ms |
| foot up | `24 4D` | First tick, then every 100 ms |
| foot down | `24 4E` | First tick, then every 100 ms |
| combined up | `24 70` | First tick, then every 100 ms |
| combined down | `24 71` | First tick, then every 100 ms |
| tilt up | `24 50` | First tick, then every 100 ms |
| tilt down | `24 51` | First tick, then every 100 ms |
| preset flat | `24 4F` | First tick, then every 100 ms |
| memory 1 | `24 55` | First tick, then every 100 ms |
| memory 2 | `24 56` | First tick, then every 100 ms |
| light toggle | `24 41` | Once |
| massage head up | `24 47` | First tick, then every 100 ms |
| massage head down | `24 48` | First tick, then every 100 ms |
| massage head stop | `24 4A` | First tick, then every 100 ms |
| massage foot up | `24 45` | First tick, then every 100 ms |
| massage foot down | `24 46` | First tick, then every 100 ms |
| massage foot stop | `24 49` | First tick, then every 100 ms |
| neck up | `24 50` | First tick, then every 100 ms |
| neck down | `24 51` | First tick, then every 100 ms |
| lumbar up | `24 50` | First tick, then every 100 ms |
| lumbar down | `24 51` | First tick, then every 100 ms |
| preset anti snore | `24 52` | First tick, then every 100 ms |
| preset tv | `24 53` | First tick, then every 100 ms |
| preset zero g | `24 54` | First tick, then every 100 ms |
| massage head | `24 43` | Once |
| massage foot | `24 42` | Once |
| massage stop | `24 44` | Once |
| lumbar up | `24 70` | First tick, then every 100 ms |
| lumbar down | `24 71` | First tick, then every 100 ms |
| tilt up | `24 70` | First tick, then every 100 ms |
| tilt down | `24 71` | First tick, then every 100 ms |
| Save memory 1 | `24 5A` | Once |
| Save memory 2 | `24 61` | Once |
<!-- /generated -->

On memory-enabled panels, **Save memory** sends a single save command.
**Recall memory** is a separate held action. On panels that have a light
toggle, the toggle is a separate button. Names with `D` at index 10 add the
RGB light. Turning that entity off sends zero to all three color channels.
Other names expose the light timer without color control. All supported names
can set the timer in seconds.

#### Timing

Held controls send on the first tick and refresh at the interval above. Release
or cancellation ends that refresh. **Stop massage** sends its own command on
panels with a three-button massage group. Saving a position sends no extra
recall on release.

The clock and status query run once per connection when the name has `E` at
index 11. Settings writes run in order on the current connection. Each query
and subsequent write follows the schedule below without waiting for a reply.

<!-- generated:ergobed-settings -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Setting | Value or example bytes | Schedule |
|---|---|---|
| Transport | `FFE0` / `FFE1` | Service / shared write and notify characteristic, matched by UUID substring |
| Status query | `24 7A` | Before each settings write and at 500 ms after discovery on alarm layouts |
| Local clock | `24 23 39 37 35 31 31 30 30 30 30 30 31 31 41 0D` | 09:07:05 example, immediately after the startup query |
| Red | `24 23 30 30 33 31 35 30 30 31 32 30 30 30 30 30 34 52 0D` | 255/255, at +50 ms |
| Green | `24 23 30 30 33 31 36 30 30 30 36 30 30 30 30 30 32 52 0D` | 128/255, at +150 ms |
| Blue | `24 23 30 30 33 31 37 30 30 30 30 30 30 30 30 30 35 52 0D` | 0/255, at +250 ms |
| Light timer | `24 23 30 30 33 31 39 30 30 31 32 30 30 30 30 30 38 52 0D` | 120 s example. Range 0–540 s, 50 ms after query |
| Alarm off | `24 23 30 30 31 37 30 37 33 30 30 30 30 30 30 30 32 52 0D` | 07:30 example, 50 ms after query |
| Alarm strength 1 | `24 23 30 31 31 38 31 32 33 34 30 30 30 30 30 31 32 52 0D` | 12:34 example, 50 ms after query |
| Alarm strength 2 | `24 23 30 32 31 39 32 33 34 35 30 30 30 30 30 31 30 52 0D` | 23:45 example, 50 ms after query |
<!-- /generated -->

#### Notifications

The receiver processes fragmented dollar/CR traffic in the app's delimiter
order and accepts exactly 75 space-separated tokens. RGB uses offsets 28–30,
the timer uses offset 54, and the alarm uses offsets 8, 9 and 11. The
integration discards partial state on disconnect. The RGB light shows off
when the receiver reports three zero channels. Missing or invalid channels
leave its power state unknown. RGB and timer values are bounded to their
entity ranges.

#### Services

Use [Set alarm](../SERVICES.md#set_alarm) on layouts with `E` at index 11.
It accepts a time and massage strength 1 or 2. An off request without a time
keeps the time reported on the current connection. If the receiver has not
reported a valid time, supply one to turn the alarm off.

#### Evidence

Based on ErgoBed Control 1.0.3. The [literal vector tests](../../tests/test_ergobed.py)
cover its short letters, decimal settings and clock records.

## Notes

- Audio-only code is deliberately excluded. `AUDIO`, `YbAudio`, `MotoAMP`,
  speakers, music, and volume controls are not adjustable-bed functions in the
  MotoSleep and Power Bob profiles. Physical bed swing/rocking commands remain
  supported. MotoMotion's music controls are its own app's feature.

### Analysis provenance

Based on MotoMotion 3.1.9 (`com.HHC.MotoMotion`), MotoSleep 5.1.5
(`com.HHC.MotoSleep`) and Power Bob 2.0.3 (`com.HHC.PowerBob`).

### Deferred user validation

The MotoSleep and Power Bob app-selected bytes, frames, callsites, timing, and
routing are checked against the app. The following need owners' beds or the app's runtime tables:

- Assign product-facing lumbar/neck/tilt labels to every neutral HHC auxiliary
  entity.
- Bind every binary MOTO massage table member to a model-specific zone, mode,
  intensity, and off label. The five exact command families are known, but the
  generic callsite obtains their per-product mapping at runtime.
- Confirm friendly units for RGB, alarm, bind, and sync notification fields.

Until then, the integration does not guess these meanings.

Based on Bedgear 2.0.1 (`2024031901`).
