# MotoSleep / Power Bob

**Existing HHC support:** ✅ User tested

**Expanded model matrix:** STATIC VERIFIED / HARDWARE UNVERIFIED

This integration follows the controller routing in the two shipped Android
apps. It does not treat every device using the shared HHC UUID as one universal
bed. The advertised local name selects the transport, motor layout, presets,
features, and STOP behavior.

Hardware confirmation for the expanded matrix is deferred until a beta or
release reaches real users with the corresponding beds. Maintainers cannot own
or directly test this many physical models. Static verification proves what the
OEM apps send, but not how every firmware and actuator behaves.

## Analysis provenance

The [README Supported Beds table](../../README.md#supported-beds) remains the
canonical support matrix. Protocol evidence here was frozen from MotoSleep
`com.HHC.MotoSleep` 5.1.5 (`2026071001`) and Power Bob
`com.HHC.PowerBob` 2.0.3. These clean-room runs satisfy the reusable Phase 4
requirements tracked by
[issue #436](https://github.com/kristofferR/ha-adjustable-bed/issues/436).

Audio-only code is deliberately excluded. `AUDIO`, `YbAudio`, `MotoAMP`,
speakers, music, and volume controls are not adjustable-bed functions. Physical
bed swing/rocking commands remain supported.

## Discovery and model routing

- Power Bob accepts an exact 14-character name containing `HHC`. Characters 8
  and 9 select 14 root panel profiles.
- Current MotoSleep HHC names use characters 16, 18, 22, and 26 to select 21
  panel profiles, raw versus wrapped writes, conditional axes, and `New`
  variants.
- Binary MOTO beds use exact 28-character `MOTOB...` or `MOTOS...` names.
  Character 7 selects ten bed pages: WRS23ms, WRS14Dmm, WRS18ms, WRS14ms,
  WRS20ms, WRS16ms, WRC30Mms, WRS27ms, WRS20ms Swing, and WR219.
- Advertised-name matching and model routing normalize letter case, including
  selector letters. Protocol command letters remain case-sensitive.
- Unmatched Power Bob selectors and malformed MOTO names receive no speculative
  controls. Legacy manual configurations without a usable advertised name keep
  a conservative two-axis fallback; current long HHC names retain the app's
  PanelOne default route.

## GATT roles

The apps prefer the following roles and retain the exact discovered UUID:

| Role | Preferred | Fallback |
|------|-----------|----------|
| Service | `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000fff0-0000-1000-8000-00805f9b34fb` |
| Write | `0000ffe1-0000-1000-8000-00805f9b34fb` | `0000fff1-0000-1000-8000-00805f9b34fb` |
| Notify (MotoSleep) | `0000ffe2-0000-1000-8000-00805f9b34fb` | `0000fff2-0000-1000-8000-00805f9b34fb` |

Power Bob writes without response. MotoSleep HHC and MOTO binary write with
response.

## HHC ASCII protocols

Raw actions are a dollar sign plus one case-sensitive command letter. Power Bob
always sends raw actions. MotoSleep normally sends the raw form; names with
`localName[22] == "M"` wrap a short action such as `$K` as `$#$KR\r`.

Common commands include:

| Function | Commands |
|----------|----------|
| Main head/back | `$K` up, `$L` down |
| Legs/feet | `$M` up, `$N` down |
| Auxiliary pair 1 | `$p` up, `$q` down |
| Auxiliary pair 2 | `$P` up, `$Q` down |
| Flat, anti-snore, TV, zero gravity | `$O`, `$R`, `$S`, `$T` |
| Memory recall 1/2 | `$U`, `$V` |
| Memory save 1/2 | `$Z`, `$a` |
| Light, head massage, foot massage, massage stop | `$A`, `$C`, `$B`, `$D` |
| Extended head intensity | `$G` up, `$H` down |
| Extended foot intensity | `$E` up, `$F` down |
| Extended head/foot massage toggle | `$J`, `$I` |
| Panel E auxiliary action | `$W` |
| Explicit motor STOP | `$b` |

Availability and axis meaning are profile-specific. In particular, the Power
Bob A15 profile selected by `HHC0069815CDEF` labels uppercase `$P/$Q` as lumbar.
Lowercase `$p/$q` is not the manual lumbar pair for that bed. This is the root
cause of [issue #445](https://github.com/kristofferR/ha-adjustable-bed/issues/445).

Where an app exposes a command pair but does not establish one unique physical
label across models, Home Assistant uses `Auxiliary`, `Auxiliary 1`, or
`Auxiliary 2`. This preserves statically proven controls without guessing that
they are lumbar, neck, or tilt. Real users can provide model-specific hardware
confirmation after release.

Panel E's exact `$W` callsite is likewise preserved as an `Auxiliary action`
button. The APK does not provide a trustworthy physical label, so the
integration does not invent one.

### HHC timing

- Movement actions repeat at 100 ms while active.
- Power Bob sends its first movement pulse after the first 100 ms interval; it
  does not send an immediate pulse on press.
- Current MotoSleep HHC sends `$b` five times at 0, 30, 60, 90, and 120 ms on
  release.
- Power Bob sends that STOP schedule only on the profiles whose release paths
  contain `$b`. Other Power Bob profiles stop when periodic movement writes
  cease.
- Presets, memory, light, and massage actions are single writes.

### RGB lighting

Both apps scale each RGB component from 0..255 to 0..120. Red, green, and blue
use decimal selectors `00315`, `00316`, and `00317`, with 20 ms between writes.
Power Bob places selector before value; MotoSleep places value before selector.
Both XOR the decimal digits and append a five-digit decimal checksum plus
`R\r`.

Power Bob RGB settings are independent of the selected root motor panel.
Advertised-name character 10 selects the Mood configuration when it is `D` and
the Night configuration otherwise, so even minimal one-motor panels retain RGB
settings when their root controls do not include the raw `$A` light toggle.

## MOTO binary protocol

Binary bed commands use this exact nine-byte frame:

```text
24 23 CMD_HI CMD_LO DATA_HI DATA_LO XOR(2..5) 41 0D
```

Command and data are unsigned 16-bit big-endian values. Model profiles select
the exposed axes from the exact app page controls, including WRC30M neck/back/
lumbar/foot axes and WR219's distinct motor values.

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

Normal MOTO movement release sends command/data `0x0000/0x0000` five times at
100 ms intervals. WR219 sends `0x9088/0x0001` six times at 100 ms intervals.

## Deferred user validation

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
