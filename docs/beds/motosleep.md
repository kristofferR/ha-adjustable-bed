# MotoSleep / Power Bob

**Status:** ⚠️ Partially tested (existing HHC support ✅ user tested; expanded model matrix static verified, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), waynebowie99 and [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt)

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

## Known Models

- Beds with HHC (Hangzhou Huaci) controllers
- Power Bob
- Device names containing "HHC" (e.g., `HHC3611243CDEF`, `HHC0069815CDEF`)
- Binary MOTO beds with exact 28-character `MOTOB...` or `MOTOS...` names
- Dedicated model pages: WR1140, the WRS14 series (WRS14Dmm, WRS14ms), WRS16ms,
  WRS18ms, WRS20ms, WRS20ms Swing, WRS23ms, WRS27ms, WRC30Mms and WR219

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [MotoSleep](https://play.google.com/store/apps/details?id=com.HHC.MotoSleep) 5.1.5 (`2026071001`) | `com.HHC.MotoSleep` |
| ✅ | [Power Bob for Adjustable Bed](https://play.google.com/store/apps/details?id=com.HHC.PowerBob) 2.0.3 (`2025061101`) | `com.HHC.PowerBob` |

See [Analysis provenance](#analysis-provenance) for artifact hashes.

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (profile-specific: back, legs, head, feet, lumbar, neck, tilt, neutral auxiliary pairs) |
| Position Feedback | ❌ |
| Memory Presets | ✅ (2 slots on most profiles; none on WR219 and the smallest panels) |
| Zero-G / Anti-Snore / TV / Flat | ✅ (profile-specific) |
| Swing | ✅ (WRS20ms Swing and WR219) |
| Massage | ✅ (profile-specific head/foot toggles, intensity steps, stop) |
| Under-bed Lights | ✅ (`$A` toggle or RGB, profile-specific) |
| Split-King Sync | ✅ (current MotoSleep HHC MainPanel profiles F, G, H, WR1140 and `New` variants) |
| Audio | ❌ (excluded, see [Notes](#notes)) |

## Protocol Details

**Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb` (fallback `0000fff0-0000-1000-8000-00805f9b34fb`)
**Write Characteristic:** `0000ffe1-0000-1000-8000-00805f9b34fb` (fallback `0000fff1-0000-1000-8000-00805f9b34fb`)
**Notify Characteristic (MotoSleep):** `0000ffe2-0000-1000-8000-00805f9b34fb` (fallback `0000fff2-0000-1000-8000-00805f9b34fb`)
**Format:** HHC ASCII: 2 bytes `[0x24, ASCII_char]` (0x24 = '$'), optionally wrapped; MOTO binary: nine-byte frames

The apps prefer the following roles and retain the exact discovered UUID:

| Role | Preferred | Fallback |
|------|-----------|----------|
| Service | `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000fff0-0000-1000-8000-00805f9b34fb` |
| Write | `0000ffe1-0000-1000-8000-00805f9b34fb` | `0000fff1-0000-1000-8000-00805f9b34fb` |
| Notify (MotoSleep) | `0000ffe2-0000-1000-8000-00805f9b34fb` | `0000fff2-0000-1000-8000-00805f9b34fb` |

### Write Mode

Power Bob writes without response. MotoSleep HHC and MOTO binary write with
response.

### HHC ASCII packet format

**MotoSleep HHC status:** EXISTING CORE USER TESTED; EXPANDED PROFILES STATIC
VERIFIED / HARDWARE UNVERIFIED

**Power Bob HHC status:** STATIC VERIFIED / HARDWARE UNVERIFIED

- Raw actions are a dollar sign plus one case-sensitive command letter.
- Power Bob always sends raw actions.
- MotoSleep normally sends the raw form; names with `localName[22] == "M"`
  wrap a short action such as `$K` as `$#$KR\r`.

### MOTO binary frame

**MOTO binary status:** STATIC VERIFIED / HARDWARE UNVERIFIED

Binary bed commands use this exact nine-byte frame:

```text
24 23 CMD_HI CMD_LO DATA_HI DATA_LO XOR(2..5) 41 0D
```

Command and data are unsigned 16-bit big-endian values. For example, standard
head/back up (`0x0002`, data `0x0000`) is `24 23 00 02 00 00 02 41 0D`.

### Numeric frames (RGB and sync)

- Both apps scale each RGB component from 0..255 to 0..120. Red, green, and
  blue use decimal selectors `00315`, `00316`, and `00317`, with 20 ms between
  writes.
- Power Bob places selector before value; MotoSleep places value before
  selector. Values are five decimal digits.
- Both XOR the decimal digits and append a five-digit decimal checksum plus
  `R\r`, after a `$#` prefix. Example (MotoSleep, red 255): `$#001200031500004R\r`.
- RGB channels are absolute: a non-zero color turns the LEDs on and three zero
  channels turn them off.
- MotoSleep's MainPanel sync frame is `$#` + opcode + `00000` + checksum +
  `R\r`: enable sends `00012` (`$#000120000000003R\r`), disable sends `00015`
  (`$#000150000000004R\r`).

## Detection / Setup

### Discovery and model routing

Character positions in this section are zero-based string indexes, matching
the apps' `localName[index]` expressions. For example, `HHC0069815CDEF` has `1`
at index 8 and `5` at index 9, which selects the Power Bob A15 panel.

- Power Bob accepts an exact 14-character name containing `HHC`. Characters 8
  and 9 select 14 root panel profiles.
- Current MotoSleep HHC names (longer than 14 characters) use characters 16,
  18, 22, and 26 to select 21 panel profiles, raw versus wrapped writes,
  conditional axes, and `New` variants.
- Binary MOTO beds use exact 28-character `MOTOB...` or `MOTOS...` names
  matching `^MOTO(B|S)(\d{2})(\w)([0-9])([BCD])([A-Za-f])(\w)(\w)(\w)`.
  Character 7 selects ten bed pages: WRS23ms, WRS14Dmm, WRS18ms, WRS14ms,
  WRS20ms, WRS16ms, WRC30Mms, WRS27ms, WRS20ms Swing, and WR219.
- Advertised-name matching and model routing normalize letter case, including
  selector letters. Protocol command letters remain case-sensitive.
- Short HHC names that select Power Bob Panel Eight retain Home as `$O`. A
  user-confirmed device uses this shared command, matching the reachable
  MotoSleep 5.1.5 PanelEight action even though Power Bob 2.0.3 does not render
  that action on its separate Panel Eight
  ([issue #468](https://github.com/kristofferR/ha-adjustable-bed/issues/468)).
- The same user-confirmed Panel Eight hardware exposes its under-bed light as
  the root `$A` toggle. It does not support the generic Power Bob RGB settings,
  so Home Assistant keeps the toggle button and does not expose RGB controls
  ([issue #470](https://github.com/kristofferR/ha-adjustable-bed/issues/470)).
- Unmatched Power Bob selectors and malformed MOTO names receive no speculative
  controls. Legacy manual configurations without a usable advertised name keep
  a conservative two-axis fallback (back `$K`/`$L`, legs `$M`/`$N`, STOP);
  current long HHC names retain the app's PanelOne default route.
- AUDIO and MotoAMP names are intentionally not bed controllers.

### Power Bob profiles (14-character names)

First matching rule wins. "All four presets" means Flat `$O`, Anti-snore `$R`,
TV `$S` and Zero-G `$T`; "memory" means recall `$U`/`$V` and save `$Z`/`$a`.
Every profile except Panel Eight also routes to the RGB settings.

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

The Power Bob app's RGB settings route is independent of the selected root
motor panel. Advertised-name character 10 selects the Mood configuration when
it is `D` and the Night configuration otherwise. Reachability in the generic
settings UI does not by itself prove the connected hardware implements those
numeric commands: the user-confirmed Panel Eight compatibility profile supports
only its root `$A` light toggle.

### MotoSleep HHC profiles (names longer than 14 characters)

First matching rule wins (char 16 alone unless char 18 is listed). Every HHC
profile releases with `$b`. "New" variants have `I` at char 26.

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

### MOTO binary pages (28-character names)

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

## Commands

### HHC Motor Control

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

### HHC Presets and Memory

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

### HHC Light, Massage and Other

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
> integration does not send; sync uses the numeric MainPanel frames above.

Where an app exposes a command pair but does not establish one unique physical
label across models, Home Assistant uses `Auxiliary`, `Auxiliary 1`, or
`Auxiliary 2`. This preserves statically proven controls without guessing that
they are lumbar, neck, or tilt. Real users can provide model-specific hardware
confirmation after release. Panel E's exact `$W` callsite is likewise
preserved as an `Auxiliary action` button. The APK does not provide a
trustworthy physical label, so the integration does not invent one.

### MOTO Binary Commands

Model profiles select the exposed axes from the exact app page controls,
including WRC30M neck/back/lumbar/foot axes and WR219's distinct motor values.
Common fixed commands include:

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

## Command Timing

### HHC timing

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

### MOTO timing

Normal MOTO movement release sends command/data `0x0000/0x0000` five times at
100 ms intervals. WR219 sends `0x9088/0x0001` six times at 100 ms intervals.

## Notes

- Audio-only code is deliberately excluded. `AUDIO`, `YbAudio`, `MotoAMP`,
  speakers, music, and volume controls are not adjustable-bed functions.
  Physical bed swing/rocking commands remain supported.
- On RGB profiles, Home Assistant treats the absolute RGB channels as the
  light's on/off control and does not send the unrelated `$A` toggle.

### Analysis provenance

The [README Supported Beds table](../../README.md#supported-beds) remains the
canonical support matrix. Protocol evidence here was frozen from MotoSleep
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

The app-selected bytes, frames, callsites, timing, and routing are statically
verified. The following cannot be finished by maintainers without real user
hardware or app-delivered runtime tables:

- Assign product-facing lumbar/neck/tilt labels to every neutral HHC auxiliary
  entity.
- Bind every binary MOTO massage table member to a model-specific zone, mode,
  intensity, and off label. The five exact command families are known, but the
  generic callsite obtains their per-product mapping at runtime.
- Confirm friendly units for RGB, alarm, bind, and sync notification fields.

These are post-beta/release validation requests, not a requirement that a
maintainer acquire the beds and not a reason to guess protocol semantics.
