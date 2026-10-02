# Remacro

**Status:** 🧪 Artifact-verified, hardware unverified

Remacro is the SynData protocol used by three store-branded Android apps from the
same developer. The integration follows the accepted row 050 analyses of all three
([disposition ledger](../apk-analysis/dispositions/row050-remacro.md)). No physical
bed has confirmed these controls yet.

## Apps and profile

| App | Package | Protocol variant |
|-----|---------|------------------|
| Slumberland | `com.cheers.slumber` 1.0 (2) | `slumberland` (also `auto`) |
| The Brick | `com.cheers.brick` 1.0 (3) | `the_brick` |
| Jerome's | `com.cheers.jewmes` 1.202112141512 (20) | `jeromes` |

Nothing in the advertisement identifies the app, so choose the protocol variant
that matches the app you use. `auto` keeps the Slumberland behavior. The apps differ
in their frame counters, in one OneActivity timing, in massage wave cycling, in the
models they list and in whether the LED light setting is shown.

## Detection and model selection

Beds are detected by the advertised service `6e403587-b5a3-f393-e0a9-e50e24dcca9e`.
Like the apps, the integration then picks the model from the **lowest
manufacturer-specific-data company ID** in the advertisement. Names, payload bytes
and signal strength are never used. The selected model is remembered in the entry
(`remacro_model`, and per side for combined beds) as a fallback when no advertisement
is in Home Assistant's history; a live advertisement always wins. A combined bed's side
with a stored model gets its entities before it first connects.

The model is checked before any connection attempt:

- No model seen yet: setup retries with "model is unknown" until the bed advertises.
- A company ID no app lists, or one the selected app does not list (for example 54 or
  55 with Jerome's): setup fails with that reason and does not retry.
- On a combined bed, such a side is not connected, gets a Repairs issue and loses its
  controls; the other side loads and keeps working. If every side is refused, setup
  fails without retrying; a side that has merely not been seen yet keeps it retrying.
  When the pair loads without an unseen side, it reloads by itself once that side
  advertises, adding its controls.
- An observed company ID is remembered even when no app lists it, so the bed stays
  refused after a restart while it is out of range.
- Setup aborts for a company ID no app lists. When the chosen app does not list the
  model, the setup form shows that as an error on the protocol variant field.
- The options form refuses an app that does not list the stored model. Saving a fix in
  the options reloads an entry that failed or is retrying, so it applies at once.
- Each side of a combined bed keeps its own app, so the combined options refuse any app
  change; unpair and change each side. Removing an entry clears its Repairs issues
  unless another entry still owns that bed.

| Company ID | App label | Screen | Controls |
|-----------|-----------|--------|----------|
| 14, 16 | BS200C/BS200P | TenActivity | All motors, Flat |
| 45 | CS-B200 | TwoActivity | Head, Feet, All motors, Flat |
| 46 | CS-B200A | SixActivity | Head, Feet, All motors, Flat, 2 memories, Anti-snore/TV/Zero-G, light |
| 47 | CS-B200M | ThreeActivity | Head, Feet, All motors, Flat, 2 memories, massage, light |
| 48 | CS-B300 | OneActivity | Head, Lumbar, Feet, All motors, Flat |
| 49 | CS-B300A | FiveActivity | Head, Lumbar, Feet, All motors, Flat, 2 memories, presets, light |
| 50 | CS-B300M | FourActivity | Head, Lumbar, Feet, All motors, Flat, 2 memories, massage, light |
| 51 | CS-B500YA | EightActivity | Split: side-selected Head, Lumbar, All motors, memories and presets; shared Feet; light |
| 52 | CS-B500YM | NineActivity | Split: side-selected Head, Lumbar, All motors, memories and massage; shared Feet; light |
| 53 | BA210 | TwoActivity1 | Head, Feet, All motors, Flat |
| 54 | CS-B300M(ASI) | TwelveActivity | Head, Lumbar, Feet (no All motors), Flat, 1 memory, presets, massage, light |
| 55 | CS-B200M(ASI) | ElevenActivity | Head, Feet, All motors, Flat, 1 memory, presets, massage, light |

Jerome's lists only company IDs 45–53. The motor-count option is ignored: the
screen decides the controls, and no physical motor count is claimed.

The LED light setting (light level slider and **Save light level**) exists only in
Slumberland and The Brick, for company IDs 46 and 49–55. Jerome's hides it for
every model.

## GATT

| Role | UUID |
|------|------|
| Service | `6e403587-b5a3-f393-e0a9-e50e24dcca9e` |
| Write (without response) | `6e403588-b5a3-f393-e0a9-e50e24dcca9e` |
| Notify | `6e403589-b5a3-f393-e0a9-e50e24dcca9e` |

The apps subscribe to notifications on connect but use them only for a sleep
module (heart rate, breathing, presence and its MAC address) whose screens have no
in-app route. The integration subscribes the same way and records the frames in
diagnostics only. There is no pairing, PIN, handshake, read or position feedback.

## Frame

```text
[serial, PID, code_lo, code_hi, p0, p1, p2, p3]   PID 0x01 for every control
```

The code and 32-bit parameter are little-endian. There is no checksum. The serial
is the low byte of one shared counter that starts at 1:

- A "tap" frame uses the counter, then increments it.
- A "hold" frame increments first. Slumberland and The Brick always do; Jerome's
  only when the code differs from the previous hold code, so repeated holds and
  repeated STOPs reuse one serial.
- Movement and release STOP use hold frames in every app. Flat, memory, presets,
  massage and the light toggle use hold frames in Slumberland and The Brick, and tap
  frames in Jerome's. The LED setting uses tap frames.

## Movement

| Control | Up | Down | Release STOP |
|---------|----|------|--------------|
| All motors | `0x0110` | `0x0111` | `0x0001` |
| Head | `0x0101` | `0x0102` | `0x0100` |
| Feet | `0x0105` | `0x0106` | `0x0104` |
| Lumbar | `0x0109` | `0x010A` | `0x0108` |
| Split left All / Head / Lumbar | `0x6444` / `0x6401` / `0x6407` | `0x6445` / `0x6402` / `0x6408` | `0x6443` / `0x6400` / `0x6406` |
| Split right All / Head / Lumbar | `0x6456` / `0x6404` / `0x640A` | `0x6457` / `0x6405` / `0x640B` | `0x6455` / `0x6403` / `0x6409` |
| Split shared Feet | `0x640D` | `0x640E` | `0x640C` |

A press sends one frame; the STOP follows 120 ms after release. Home Assistant's
hold time is the motor pulse count times the pulse delay (default 10 × 100 ms).
OneActivity (company ID 48) differs:

- Head, Lumbar and Feet send STOP three times, at 0, 120 and 240 ms after release.
- All motors repeats the press every 100 ms and sends STOP at 0, 20 and 40 ms after
  release, except in The Brick, which sends one press and one STOP 120 ms later.

The STOP is always sent, including when a movement is cancelled. The apps send no
STOP for a cancelled touch or a closed screen; that behavior is not copied.

Split beds (51, 52) have a **Control side** select that mirrors the app's
left/right toggle. It starts on the left, sends nothing and changes without connecting
to the bed.

The frame counter, side, active preset, massage and wave counters and the LED
slider level are kept for as long as the entry is loaded, across command handoffs and
reconnects. In the app only the counter is static; the rest are screen fields that
reset when the screen reopens. Home Assistant has no app screen and rebuilds its
controller after every command when Disconnect After Command is on, so resetting them
would restart the massage cycle, lose the preset re-press STOP, save an old LED level
or move the other side. This is a deliberate deviation. The state is kept per bed: it
carries over when a pair absorbs a single bed or unpair restores one, and resets when
the last entry for that bed unloads, Home Assistant restarts, or the app profile or
model changes.

## Presets, memory and stop

| Action | Code |
|--------|------|
| Flat (every screen) | `0x0111`, sent once |
| Anti-snore / TV / Zero-G | `0x0301` / `0x0302` / `0x0303` |
| Split left / right presets (51) | `0x6511`–`0x6513` / `0x6521`–`0x6523` |
| Memory recall 1 / 2 | `0x0311` / `0x0313` |
| Memory save 1 / 2 | `0x0310` / `0x0312` |
| Split left recall / save | `0x6530`, `0x6531` / `0x6540`, `0x6541` |
| Split right recall / save | `0x6538`, `0x6539` / `0x6548`, `0x6549` |
| Stop | `0x0001` |

As in the apps, pressing the preset that is already active sends `0x0001` instead.
The Stop button sends `0x0001` and clears the active preset. NineActivity defines no
global STOP, so it has no Stop button; stopping a cover ends the running movement
with its own release STOP. A combined bed gets its combined Stop only when a side has a
global STOP; that Stop only cancels the running movement on a NineActivity side.

## Massage

Massage models expose the apps' three buttons. They keep the same local counters:
head and foot each cycle levels 1, 2, 3 and off; the wave button cycles wave 1,
wave 2 and off. Starting a wave sets both zones to level 1; stopping it sets them off.

| Button | Levels 1–3 | Levels with wave | Off |
|--------|------------|------------------|-----|
| Head | `0x0201`–`0x0203` | `0x0220`–`0x0222` | `0x0123` |
| Foot | `0x0204`–`0x0206` | `0x0228`–`0x022A` | `0x0124` |
| Wave | wave 1 `0x0230`, wave 2 `0x0231` | | `0x0200` |

NineActivity left uses wave off `0x0233`. NineActivity right uses head
`0x0207`–`0x0209`, wave head `0x0240`/`0x2401`/`0x0242` (the `0x2401` is literal in
all three apps), head off `0x0133`, foot `0x020A`–`0x020C`, wave foot
`0x0248`–`0x024A`, foot off `0x0134` and wave `0x0250`/`0x0251`/`0x0253`. The
counters are shared between sides, as in the app.

While a wave runs, Slumberland and The Brick wrap a zone from level 3 back to 1, so
they never send the zone off code then. Jerome's wraps to off.

## Lights

The light switch sends `0x0501` with parameter 0 for on and `0x0500` for off. The bed
never reports its light, so the switch starts unknown and shows the commanded state as
assumed. The
LED light setting sends `0x0501` with parameter `0xFFFFFF00 | level` 150 ms after a
change, and **Save light level** sends `0x050F` with the current level 500 ms after
the press. Each save stores the level in the entry (`remacro_led_level`) under the
model's company ID, like the app's preference keyed by model and address, and the
slider starts there when the entry loads. A model without a saved level, including
one the bed newly advertises, starts at 255, the app's default.

## Not implemented

These app paths have no in-app route, need a network, or are dead code. See the
ledger for each reason: full-color RGB and light auto-off delay, rocking timer,
sleep-module settings and telemetry, Wi-Fi provisioning, the HTTP sleep report, the
Jerome's sleep-module MAC query, and constants that no reachable control sends
(including the heating and LED mode codes earlier versions of this integration used).
