# HHC `$#` frames (MotoMotion, MotoSleep, Power Bob, Bedgear)

**Status:** ⚠️ Partially tested (existing MotoSleep HHC support user tested in [#51](https://github.com/kristofferR/ha-adjustable-bed/issues/51) and [#445](https://github.com/kristofferR/ha-adjustable-bed/issues/445); MotoMotion 3.1.9, Power Bob and the expanded MotoSleep model matrix static verified, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), waynebowie99 and [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt)

## Known Models

- **MotoMotion:** the app selects 17 primary routes: 13 panel classes and four
  aliases. Case-sensitive local names containing `SOFA` with length 15, `BT201`
  with length 9, or containing `MOTO` are scan candidates. These are contains
  tests, not prefixes.
- **MotoSleep / Power Bob:** beds with HHC (Hangzhou Huaci) controllers and
  Power Bob. Device names contain "HHC" (e.g., `HHC3611243CDEF`,
  `HHC0069815CDEF`).
- Binary MOTO beds with exact 28-character `MOTOB...` or `MOTOS...` names
  (MotoSleep app).
- Dedicated MotoSleep model pages: WR1140, the WRS14 series (WRS14Dmm,
  WRS14ms), WRS16ms, WRS18ms, WRS20ms, WRS20ms Swing, WRS23ms, WRS27ms, WRC30Mms
  and WR219.
- No physical brand/model equivalence is inferred between the apps' selectors.
  MotoMotion, MotoSleep and Power Bob remain separate app profiles, and none
  treats every device using the shared HHC UUID as one universal bed.

## Apps

| Analyzed | App | Package ID | Profile |
|----------|-----|------------|---------|
| ✅ | [Bedgear](https://play.google.com/store/apps/details?id=com.Bedgear.AdjustableBed) 2.0.1 (`2024031901`) | `com.Bedgear.AdjustableBed` | [Bedgear](#bedgear) |
| ✅ | [MotoMotion](https://play.google.com/store/apps/details?id=com.HHC.MotoMotion) 3.1.9 (code 2026051101) | `com.HHC.MotoMotion` | [MotoMotion](#motomotion) |
| ✅ | [MotoSleep](https://play.google.com/store/apps/details?id=com.HHC.MotoSleep) 5.1.5 (`2026071001`) | `com.HHC.MotoSleep` | [MotoSleep](#motosleep) |
| ✅ | [Power Bob for Adjustable Bed](https://play.google.com/store/apps/details?id=com.HHC.PowerBob) 2.0.3 (`2025061101`) | `com.HHC.PowerBob` | [Power Bob](#power-bob) |

See [Analysis provenance](#analysis-provenance) for artifact hashes.

## Features

| Feature | MotoMotion | MotoSleep | Power Bob | Legacy route | Bedgear |
|---------|------------|-----------|-----------|--------------| --- |
| Motor Control | ✅ App-labelled headrest, lumbar, main, back, legrest and tilt controls, selected by panel | ✅ Profile-specific: back, legs, head, feet, lumbar, neck, tilt, neutral auxiliary pairs | ✅ Profile-specific: back, legs, lumbar, tilt, neutral auxiliary pairs | ✅ Back and legs | ✅ Name-selected motor zones |
| Position Feedback | ❌ No measured motor angle/percentage response | ❌ | ❌ | ❌ | ❌ |
| Memory Presets | ✅ 0–4 slots, with panel-specific recall and programming | ✅ 2 slots on most profiles; none on WR219 and the smallest panels | ✅ 2 slots on most profiles; none on the smallest panels | ❌ | ✅ 0 or 2 slots; Panel E snore save |
| Zero-G / Anti-Snore / TV / Flat | Home only | ✅ Profile-specific | ✅ Profile-specific | Flat | ✅ Layout-specific |
| Swing | ❌ | ✅ WRS20ms Swing and WR219 | ❌ | ❌ | ❌ |
| Massage | ✅ Name-selected level controls | ✅ Profile-specific head/foot toggles, intensity steps, stop | ✅ Profile-specific head/foot toggles, intensity steps, stop | ❌ | ✅ Layout-specific buttons |
| Heat | ✅ Name/panel-selected level or cycle controls | ❌ | ❌ | ❌ | ❌ |
| Lights | ✅ Panel light cycle/toggle, RGB and timer where admitted | ✅ Under-bed `$A` toggle or RGB, profile-specific | ✅ RGB settings; `$A` toggle, profile-specific | ❌ | ✅ Toggle, RGB and shutdown minutes where admitted |
| Split-King Sync | ❌ | ✅ Current MotoSleep HHC MainPanel profiles F, G, H, WR1140 and `New` variants | ❌ | ❌ | ✅ Source-gated bed synchronization |
| Music / Audio | ✅ ASCII or binary equalizer controls; binary playback buttons | ❌ Excluded, see [Notes](#notes) | ❌ Excluded | ❌ | ❌ Excluded |
| User postures | ✅ Local measurements, four generated/custom raw Hall target postures, fine tuning | ❌ | ❌ | ❌ | ❌ |
| Side selection | ✅ Left/right when `SOFA` name index 10 is `S`; retained per address and exact profile across reconnections, with paired child routing taking precedence | ❌ | ❌ | ❌ | ❌ No app wire side selector; HA can pair two receivers |
| Binding | ✅ Eight-byte application binding and explicit application unbinding | ❌ | ❌ | ❌ | Received bed sync state/toggle, no ownership or authentication exchange |

## Choosing a profile

The advertised local name selects the profile. Detection suggests `motosleep`
for an HHC or exact MOTO name. Bedgear's exact name gate adds an app candidate,
or a low-confidence candidate when no existing route matches. See each profile's Setup.

| Profile | Key | Bed type | Selected by |
|---------|-----|----------|-------------|
| [Bedgear](#bedgear) | `bedgear` | `bedgear` | Explicit app choice; exact 14-unit Bluetooth name selects the layout and independent flags |
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

**Status:** ❓ Needs testing (MotoMotion 3.1.9, static artifact evidence; hardware unverified)

#### Setup

Choose **MotoMotion app (exact Bluetooth name)** in the bed-type list; searching for MotoMotion finds it. The next question asks the exact Bluetooth local name, filled in from the advertisement when there is one. Configure asks the same name and checks it the same way. The Home Assistant display name never selects a panel. Discovery offers a candidate without overriding another app's confident match. Shared service UUIDs alone do not select this app.

- `BT201` selects binary music first. Otherwise zero-based name index 9 selects `1`, `2`, `3`, `5`, `6`, `7`, `8`, `9`, `A`, `D`, `E`, `G`, `H`, or `J`. `MM` at indices 9 and 10 selects ASCII music. Other selectors use the One panel.
- Home Assistant's automatic name index requires three literal leading characters, so its name-only hints are `SOFA*`, `BT201*` and `MOTO*`. Names with another prefix can still reach discovery through advertised service hints, or through **Show all BLE devices** and manual setup. The app's case-sensitive substring rules and exact Bluetooth name remain the profile inputs; a shared service does not select the MotoMotion app automatically.

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

HA deliberately cancels delayed writes on release/cancellation, always performs admitted movement cleanup, and separates saving from recall. The shipped app can retain a delayed write after release, suppress queued STOP on re-press, or recall on the release of a save gesture. Those hazards are not reproduced. Exact findings and negative tests are in the ledger.

#### Notifications

The framer waits for `$` then CR, discards preceding noise and the entire coalesced suffix, and clears the buffer before parsing. It strips all characters other than ASCII digits/spaces, then splits literal spaces, retaining empty tokens. Supported token counts: 11, 16, 24, 31, 37, 38, 39, 42, 43, 50, 62 and 71. Count 43 emits two events.

The status sensor retains RGB/D/comfort/HSW fields and parse errors. Heat, massage, lift/calibration flags and the unidentified `field_1b` remain protocol state, not invented angle sensors. Completed stores survive later parse failures. Events are asynchronous names and read current state when delivered. Numeric consumers accept nonnegative signed-64-bit decimal values with arbitrarily many leading zeroes; actual overflow and empty fields fail in source order.

#### Services

The `adjustable_bed.motomotion` action manages named local users and postures. `dimensions` is `[height, buttocks_height, knee_height]` in centimetres. All must be finite. The four posture keys are `upright`, `recline`, `tv`, and `lay`. Fine-tuning targets require all five keys: head 0–863, base 0–3174, back 0–1454, lumbar 0–874, tilt 0–629. Generated head targets can reach 867; that source mismatch is preserved. Local custom saves do not program hardware memory. Switching user or posture invalidates unsent working targets; a save request must match the user and posture that own those targets.

#### Evidence

The accepted MotoMotion 3.1.9 report (row113): its test vectors round-trip
through the codec. See [Analysis provenance](#analysis-provenance).

### MotoSleep and Power Bob family

**Status:** ⚠️ Existing HHC support user tested; expanded model matrix static verified, hardware unverified

This integration follows the controller routing in the two shipped Android
apps. It does not treat every device using the shared HHC UUID as one universal
bed. The advertised local name selects the transport, motor layout, presets,
features, and STOP behavior.

- **Existing HHC support:** ✅ User tested
- **Expanded model matrix:** STATIC VERIFIED / HARDWARE UNVERIFIED. Hardware
  confirmation is deferred until a beta or release reaches real users with the
  corresponding beds. Maintainers cannot own or directly test this many
  physical models. Static verification proves what the OEM apps send, but not
  how every firmware and actuator behaves.

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
> off, and `$P`/`$p` as neck/lumbar on every bed. The audited apps show `$W` is
> only Panel E's unlabelled action and `$X`/`$Y` are not sent by any profile.
> `$z` is an initialization-only query that the wrapped path drops and the
> integration does not send; sync uses the numeric MainPanel frames below.

Where an app exposes a command pair but does not establish one unique physical
label across models, Home Assistant uses `Auxiliary`, `Auxiliary 1`, or
`Auxiliary 2`. This preserves statically proven controls without guessing that
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
> `$b` STOP sent 3 times with a 50 ms delay. The audited apps and the current
> code use the schedule above.

#### Evidence

Both reports are COMPLETE; see [Analysis provenance](#analysis-provenance).
MotoSleep, Power Bob and the legacy route send only their frozen frames.

### MotoSleep

**App:** [MotoSleep](https://play.google.com/store/apps/details?id=com.HHC.MotoSleep) 5.1.5 (`2026071001`), `com.HHC.MotoSleep`

**Status:** ⚠️ Existing core HHC support user tested; expanded profiles and MOTO binary pages static verified, hardware unverified

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

**MOTO binary status:** STATIC VERIFIED / HARDWARE UNVERIFIED

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

**Status:** ❓ Needs testing (static verified, hardware unverified)

Behaves as the [MotoSleep and Power Bob family](#motosleep-and-power-bob-family), except as below.

#### Setup

##### Power Bob profiles (14-character names)

First matching rule wins. Power Bob always sends raw actions. Every profile
except Panel Eight also routes to the RGB settings.

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
| Seven | char 8 `7` | Back, legs | Flat, memory | `$A`; massage `$C`/`$B`/`$D` | None |
| Eight | char 8 `8` | Back, legs | All four (`$O` per [issue #468](https://github.com/kristofferR/ha-adjustable-bed/issues/468)), memory | `$A` only, no RGB | None |
| Nine | char 8 `9` | Back, legs | Flat | None | `$b` |
| Six ZG | char 8 `D` | Back, legs | None | None | `$b` |

- Short HHC names that select Power Bob Panel Eight retain Home as `$O`. A
  user-confirmed device uses this shared command, matching the reachable
  MotoSleep 5.1.5 PanelEight action even though Power Bob 2.0.3 does not render
  that action on its separate Panel Eight
  ([issue #468](https://github.com/kristofferR/ha-adjustable-bed/issues/468)).
- The same user-confirmed Panel Eight hardware exposes its under-bed light as
  the root `$A` toggle. It does not support the generic Power Bob RGB settings,
  so Home Assistant keeps the toggle button and does not expose RGB controls
  ([issue #470](https://github.com/kristofferR/ha-adjustable-bed/issues/470)).

The Power Bob app's RGB settings route is independent of the selected root
motor panel. Advertised-name character 10 selects the Mood configuration when
it is `D` and the Night configuration otherwise. Reachability in the generic
settings UI does not by itself prove the connected hardware implements those
numeric commands: the user-confirmed Panel Eight compatibility profile supports
only its root `$A` light toggle.

### Legacy route

**Status:** ⚠️ Conservative fallback for manual entries without a usable advertised name

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

**Status:** ❓ Needs testing (static verification; hardware unverified)

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
SixZG has a Zero-G preset without an inferred Flat action. There are no measured
motor positions or absolute seeks.

The layout selector gives pair rules priority: 15, then 35/45/85, then index 8
`4` or 25/55, then 95–98, then 65/75, then single-character layout rules.
One/Two admit head or head+foot or neck+head+foot. Three/Four additionally use
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
| `alarm` | `time: HH:MM`, `strength: 0..2` (off, 1, 2). Omit time or strength only to reuse an actually received value; received time digit widths are preserved. No weekday or repeat parameter. |
| `sync_mode` | `wired: false` selects wireless, true wired. Requires `confirm: true`. This is bed synchronization, not Bluetooth pairing or network membership. |
| `toggle_sync` | Requires a received available bind state. The current active/inactive state selects the source command. |
| `save_memory` | `slot: 1..2`, subject to layout. Optional `recall_on_release: true` sends recall after save, matching the source's up-before-rebuild branch. |
| `save_snore` | Panel E only, sends save without a release recall. Use the separate held anti-snore preset to recall. |

Memory saves default to save only. Panel E snore save has no release-send branch.
HA does not reproduce a race against a Flutter widget rebuild. Synchronization does not select another Bluetooth
address; independent paired beds retain HA's normal physical-side routing.

#### Evidence

Row A12's accepted Bedgear 2.0.1 frames match the shared HHC codec byte for byte,
including six-plus-four-digit alarm fields. All selected layouts have their own
Bedgear profile rules. Static verification does not establish physical movement,
STOP completion or firmware compatibility. External beta/release users can
qualify those behaviors with timestamps, GATT details and physical observations.


## Notes

- Audio-only code is deliberately excluded. `AUDIO`, `YbAudio`, `MotoAMP`,
  speakers, music, and volume controls are not adjustable-bed functions in the
  MotoSleep and Power Bob profiles. Physical bed swing/rocking commands remain
  supported. MotoMotion's music controls are its own app's feature.

### Analysis provenance

The [README Supported Beds table](../../README.md#supported-beds) remains the
canonical support matrix.

**MotoMotion:**

- Accepted package: `com.HHC.MotoMotion` 3.1.9, code 2026051101.
- Frozen XAPK SHA-256: `b1a590b6f24c8d4f5b8dfd10293b5266b4d0a95abd3a04f27786524bfd6accc2`.
- Separate APK-member-set SHA-256: `a354614e81258f020f5207de3b3f85393535beedb8f1028e3dc2aa6221e60522`. These identify different things.
- Five-APK arm64-v8a/en/fr/mdpi delivery only. Public Play metadata establishes versionName only, not versionCode, signer or exact delivery. Same-version replacement and other device/region deliveries are not excluded. Acquisition source-stamp and application signer digests were separated by the accepted audit.
- The row113 audit ledger records report/audit seals, all command and candidate mappings, corrections and exclusions. Its item coverage is the [ledger fixture](../../tests/fixtures/motomotion_ledger.json) the tests check. Raw artifacts, decompilation and audit reports remain local.
- ATT acceptance, actual firmware responses and physical effects need real-user validation after beta/release. No maintainer hardware check is required to complete the static implementation.

**MotoSleep and Power Bob:** protocol evidence was frozen from MotoSleep
`com.HHC.MotoSleep` 5.1.5 (`2026071001`) and Power Bob `com.HHC.PowerBob`
2.0.3. Both reports are COMPLETE and pass the reusable
[APK Protocol Audit completion gates](https://github.com/kristofferR/ha-adjustable-bed/issues/443):

| Package | Artifact-set SHA-256 | Frozen report evidence |
|---------|---------------------|------------------------|
| `com.HHC.MotoSleep` 5.1.5 (`2026071001`) | `d909b93159816b0de135e26a423f618eabbe3d9c1effbe885c3d4d08d9f26c96` | Package-local `REPORT.SHA256` verifies `analysis.json` as `1d70180d98fc76727c6c6a1ebb7a51430c1f2d4bd0b4d3f0e61608658194b3ab` |
| `com.HHC.PowerBob` 2.0.3 (`2025061101`) | `134568e8bbdc3a6794eb12e3452abec74957924824d8c24c0b1479af4f90ab31` | Package-local `REPORT.SHA256` verifies `analysis.json` as `25a0a8be736003b7802e9dfad89df8d2ac1701c9181c6ad596e0fe5cd277a872` |

The durable [#447 accepted-exclusions registry](https://github.com/kristofferR/ha-adjustable-bed/issues/447)
records both reports as accepted and removed from the later #436 bulk run. Raw
reports and APKs remain machine-local as required by
[issue #436](https://github.com/kristofferR/ha-adjustable-bed/issues/436).

### Deferred user validation

The MotoSleep and Power Bob app-selected bytes, frames, callsites, timing, and
routing are statically verified. The following cannot be finished by
maintainers without real user hardware or app-delivered runtime tables:

- Assign product-facing lumbar/neck/tilt labels to every neutral HHC auxiliary
  entity.
- Bind every binary MOTO massage table member to a model-specific zone, mode,
  intensity, and off label. The five exact command families are known, but the
  generic callsite obtains their per-product mapping at runtime.
- Confirm friendly units for RGB, alarm, bind, and sync notification fields.

These are post-beta/release validation requests, not a requirement that a
maintainer acquire the beds and not a reason to guess protocol semantics.

Bedgear 2.0.1 (`2024031901`), row A12: XAPK SHA-256
`4e5430558c7aa4badc5f23e466bfb02ba3412e89a3e0c808760aebeddefbbf1f`.
Supplied arm64 delivery has 20 APKs. Its APK signer and distinct distribution
source stamp are separate identities; the config.xxhdpi filename contains
xhdpi resources. Mirror availability does not certify a Play rollout.
