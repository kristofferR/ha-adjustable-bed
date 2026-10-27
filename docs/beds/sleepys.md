# Sleepy's Elite (MFRM)

**Status:** ✅ Protocol implemented; hardware unverified

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed) and [SethCalkins](https://github.com/SethCalkins) (BOX25 Star, ported from [ha-dewertokin-bed](https://github.com/sethcalkins/ha-dewertokin-bed))

## Known Models

- MFRM Sleepy's Elite adjustable beds
- Mattress Firm adjustable beds using the Sleepy's Elite app
- DewertOkin BOX25 Star controller beds (BLE name: `Star*`)

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [MFRM Sleepy's Elite](https://play.google.com/store/apps/details?id=com.okin.bedding.sleepy) | `com.okin.bedding.sleepy` |
| ✅ | Adjustable Comfort M1X12 | `com.starcode.adjustablem1x12` |
| ✅ | AdjustableM5X4 / AdjustableM5X5 | `com.starcode.abm5_4` / `com.starcode.abm5_5` |
| ✅ | MFRM Luxe / Ultra | `com.okin.bedding.luxe` / `com.okin.bedding.ultra` |

## Protocol Variants

The Sleepy's Elite app supports multiple control box types. This integration implements three BLE protocols:

`SLEEPSTAR` is not one of these variants. It is the SleepSpa S9000AI CB37
sleep-monitor protocol, which tunnels StarCode inside an additional envelope.
Use the separate [SleepSpa S9000AI protocol](sleepstar.md) for that device name.

| Variant | Packet Size | Checksum | Lumbar | Neck | Lights | Massage | Positions | Service UUID |
|---------|-------------|----------|--------|------|--------|---------|-----------|--------------|
| BOX15 | 9 bytes | Yes | ✅ | ❌ | ❌ | ❌ | ❌ | FFE5 |
| BOX24 | 7 bytes | No | ❌ | ❌ | ❌ | ❌ | ❌ | 62741523 (OKIN 64-bit) |
| BOX25 (StarCode or legacy) | 2-20 bytes | No | ✅ | ✅ | ✅ | ✅ | ✅ | 6e400001 (Nordic UART) |

**Protocol Selection:**

- If your device name starts with **"Star25"** and advertises Nordic UART, use BOX25. Auto mode reads Device Information `2A29`: text containing `star` selects StarCode; any other/missing value selects legacy CB25. A manual dialect override is available.
- If your bed has **lumbar control** (but no Star name), use the BOX15 variant
- If your bed has **OKIN 64-bit service UUID** (62741523-...), use BOX24
- Octo Star2 beds also use `Star2` names, but they advertise the Octo Star2 UUID and are detected as Octo first
- When in doubt, try BOX24 first (simplest protocol)

### Explicit Sleepy's Elite app profile

Choose **Sleepy's Elite app** in manual setup when the bed is operated with the
`com.okin.bedding.sleepy` app. This is a separate, app-findable profile. It is
never inferred from a shared BLE service or transport, and it does not replace
the existing BOX15, BOX24, or BOX25 integrations above. For a paired bed, choose
the selector independently for each physical receiver. Select `none` only when
the app has no named control box for that receiver.

The selector list follows the app: `none`, `BOX15`, `BOX24`, `BOX1220`,
`BOX1221`, `BOX2422`, `BOX2442`, `BOX3633`, `BOX25`, and `BOX25_STAR`.
Selectors control the app's exact GATT route and packet builders. Setup writes
`5A 0B 00 A5` with response before enabling the selected notification target;
an initial setup-write error triggers one retry of the same frame. Once the
notification channel is ready, this profile checks Device Information and
best-effort reads manufacturer name `2A29`, followed by software revision
`2A28`. These optional metadata reads do not gate readiness. A disconnect ends
the sequence, so a prior session cannot store metadata from a stale response.
Other Sleepy's profiles keep their existing generic `2A29`/`2A24` behavior.

| Selector | Write characteristic | Notification characteristic | App-only additions |
|----------|----------------------|-----------------------------|--------------------|
| `none`, `BOX24`, `BOX1221`, `BOX2422`, `BOX2442` | Nordic UART `6E400002` | Nordic UART `6E400003` | Position target sliders and raw app state where the app caller is proven |
| `BOX15` | `FFE9` in `FFE5` | `FFE4` in `FFE0` | Position target sliders and raw app state where the app caller is proven |
| `BOX1220` | `1001` in `1000` | `1002` in `1000` | Position target sliders and raw app state where the app caller is proven |
| `BOX3633` | `62741525` in `62741523` | `62741625` in `62741523` | Only the proven safe common app surface; the conditional navigation-race position slider is excluded |
| `BOX25`, `BOX25_STAR` | Nordic UART `6E400002` | Nordic UART `6E400003` | App light, massage, timer-code, and voice actions |

The profile exposes proven head, feet, lumbar, and selector-supported neck
movement, the app's preset and memory actions, position refresh, and eligible
light/massage actions. Position target values and unlabelled state fields keep
the app's raw axis/field identities; the integration does not guess physical
axis labels or semantics. Nine proven UI selectors expose axis `0`, `1`, and
`2` target numbers over the logical `0..100` range. BOX25 and BOX25_STAR also
retain separate one-shot voice endpoints at `0` and `100`. Stable BOX3633
continues to expose its direction controls before target-event creation; its
conditional navigation-race target slider remains excluded.

The accepted position input domain is axes `0`, `1`, and `2` with slider
targets truncated to integer `0..100`; the app's tagged `0xc8` argument is
integer `100`, not `200`.
The app's 25-position layouts commit the requested target once at drag end or
active cancellation, with no appended STOP. Its seven 36-position selectors
commit the changed target, send STOP at interaction end, then separately try
midpoint `50`. Home Assistant numbers provide one commit and no drag-end
callback, so a 36-selector number commit is adapted as target, STOP, then a
separate midpoint value write. That midpoint is a real position command, not a
STOP substitute. The app's private StoppedState delta thresholds (3/3/5),
running-axis queue and deduplication, same-axis reset `(7, 0)`, event-4
queue-clear without reset, STOP, or transition, and event-5 completion/replay
are source facts; the final duplicate target event is ignored. Event
consumption reads the manager's then-current selector.
HA commits do not create that private gesture queue; they run as finite
per-controller commands through the integration's command lane using the
physical side's explicit selector. No physical axis meaning is inferred.

On `BOX25` and `BOX25_STAR`, lights and massage follow the app's actual callers.
The brightness number spans `0..6`: positive values send one brightness
frame, while zero uses the separate light-off route. The controller brightness
setter still supports the distinct source value-zero brightness frame. Two
one-step HA buttons adapt the source's relative voice brightness calls; they
retain the current `0..6` level at either endpoint and wait for a known level
before sending. Slider and palette commits require the parsed under-bed-light
enabled state. HA commits require the active BLE controller session but do
not reproduce the app's UI-only debounce or local preview. Combined massage
intensity spans `0..7` and maps to builder
value `0` or `2..8`; timer options are opaque codes `1`, `2`, and `3`, not
minute labels. Intensity and timer commits require active massage; timer
selection also skips the already-selected code. The source sends brightness
after slider end/active cancellation, timer choices on button up/cancel, and
intensity on slider end/active cancellation or button up/cancel; its intensity
down callback is inert. HA numbers/selects are single commits, each sending
one frame with no implicit STOP. The color number exposes codes `1..7`.
Palette/cycle up and cancel are speak-mode callers: each commit attempts one
frame, starts no repeat timer, and sends no STOP. The app's event-4 interrupt
clears only its pending position-event queue before massage time/intensity
writes; the HA adapter has no retained app gesture queue and does not invent a
reset or STOP for those commits. Selector-specific button repeats use the
app's 100 ms refresh and STOP release paths. The card honors each direction's
declared 100 ms start and release delays. Native Home Assistant button and
cover actions use a bounded 300 ms adapter window with the same refresh and
release behavior. Voice position calls are one-shot.
Motion-sensor refresh ends after five seconds by cancelling its repeat; this
path sends no fabricated STOP frame. The app's
`setAlarm` and `queryAlarm` routes are unreachable from the app UI and are not
exposed. The two empty BOX15 writer calls are retained as exact empty-value
attempts in the internal route table; no payload bytes or platform acceptance
are inferred for them, and they do not create public massage controls.

Current caller policy, its accepted addendum/audit hashes, and the selector
classification correction are indexed additively in the [row003 disposition
ledger](../apk-analysis/dispositions/row003-sleepys-elite.json). They leave the
canonical route table and original dynamic-vector provenance intact.

Raw RX state is parsed atomically: malformed or bounds-faulting packets, and
callbacks without a current BLE notification session, leave the prior state
unchanged. Unknown fields are surfaced with neutral raw
field names instead of inferred physical labels. The protocol is reconstructed
from accepted canonical v2 app evidence; physical behavior has not been
verified on a bed.

## Features

| Feature | BOX15 | BOX24 | BOX25 Star |
|---------|-------|-------|------------|
| Motor Control | ✅ | ✅ | ✅ |
| Lumbar Motor | ✅ | ❌ | ✅ |
| Neck Tilt Motor | ❌ | ❌ | ✅ |
| Position Feedback | ❌ | ❌ | ✅ (0-100%) |
| Direct Position Control | ❌ | ❌ | ✅ (protocol: head/feet/lumbar) |
| Memory Presets | ❌ | ❌ | ✅ (2 slots) |
| Memory Programming | ❌ | ❌ | ✅ |
| Flat Preset | ✅ | ✅ | ✅ |
| Zero-G Preset | ✅ | ✅ | ✅ |
| Anti-Snore Preset | ❌ | ❌ | ✅ |
| Lounge Preset | ❌ | ❌ | ✅ |
| Under-Bed Lights | ❌ | ❌ | ✅ (RGB color, on/off and level 0-6; legacy CB25: on/off and level) |
| Massage | ❌ | ❌ | ✅ (toggle/off, 3 wave modes, timer) |
| Massage Intensity | ❌ | ❌ | ✅ (head/foot steps and combined level 0-7) |

## Protocol Details

### BOX15 Protocol (9-byte packets with checksum)

**Service UUID:** `0000FFE5-0000-1000-8000-00805F9B34FB`

**Write Characteristic:** `0000FFE9-0000-1000-8000-00805F9B34FB`

**Packet Structure:**

```text
[0]    Header1: 0xE6
[1]    Header2: 0xFE
[2]    Prefix:  0x2C
[3]    Motor command
[4]    Preset data (byte 4)
[5]    Reserved: 0x00
[6]    Preset data (byte 6)
[7]    Reserved: 0x00
[8]    Checksum: (~sum(bytes[0:8])) & 0xFF
```

**Motor Commands (byte 3):**

| Command | Hex | Description |
|---------|-----|-------------|
| STOP | 0x00 | Stop all motors |
| HEAD UP | 0x02 | Raise head |
| HEAD DOWN | 0x01 | Lower head |
| FOOT UP | 0x08 | Raise foot |
| FOOT DOWN | 0x04 | Lower foot |
| LUMBAR UP | 0x20 | Raise lumbar |
| LUMBAR DOWN | 0x10 | Lower lumbar |

**Preset Commands (byte 4 + byte 6):**

| Preset | Byte 4 | Byte 6 |
|--------|--------|--------|
| Flat | 0x00 | 0x10 |
| Zero-G | 0x20 | 0x00 |

**Example - Move Head Up:**

```text
E6 FE 2C 02 00 00 00 00 [checksum]
```

### BOX24 Protocol (7-byte packets)

**Service UUID:** `62741523-52F9-8864-B1AB-3B3A8D65950B` (OKIN 64-bit)

**Write Characteristic:** `62741625-52F9-8864-B1AB-3B3A8D65950B`

**Packet Structure:**

```text
[0]    Header1: 0xA5
[1]    Header2: 0x5A
[2]    Reserved: 0x00
[3]    Reserved: 0x00
[4]    Reserved: 0x00
[5]    Command type: 0x40
[6]    Motor/Preset command
```

**Motor Commands (byte 6):**

| Command | Hex | Description |
|---------|-----|-------------|
| STOP | 0x00 | Stop all motors |
| HEAD UP | 0x02 | Raise head |
| HEAD DOWN | 0x01 | Lower head |
| FOOT UP | 0x06 | Raise foot |
| FOOT DOWN | 0x05 | Lower foot |

**Preset Commands (byte 6):**

| Preset | Hex |
|--------|-----|
| Flat | 0xCC |
| Zero-G | 0xC0 |

**Example - Move Head Up:**

```text
A5 5A 00 00 00 40 02
```

### BOX25 Protocol (Nordic UART)

**Service UUID:** `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` (Nordic UART)

**Write Characteristic (TX):** `6E400002-B5A3-F393-E0A9-E50E24DCCA9E`

**Notify Characteristic (RX):** `6E400003-B5A3-F393-E0A9-E50E24DCCA9E`

**BLE Device Name:** Starts with `Star25` (e.g., `Star252201154718`)

**Integration motor surface:** `head`, `feet`, `lumbar`, `tilt`

**Integration direct-position surface:** `head`, `feet`, and `lumbar`, exposed both as number sliders and through the `set_position` service. Neck tilt does not currently have a protocol-backed position zone.

The Sleepy's app first classifies `Star25...` as BOX25, reads manufacturer name
characteristic `2A29`, then promotes it to `BOX25_STAR` only when the decoded
text starts with `star`. The M1X12/M5X5 implementations corroborate the same
runtime split using a case-insensitive `contains("star")` test. Fixed F23 and
kneading product identifiers (`STAR254203/4205/4255/4256/4257`,
`STAR255401/5402/5403`) are StarCode-only.

`BOX25_STAR` uses StarCode for every motor, preset, light, and massage action:

```text
5A 01 03 10 [category] [command] A5
```

Normal commands are written to Nordic UART without response. The integration
sends the proven `5A 0B 00 A5` wake frame once **with response**, before enabling
RX notifications, exactly matching the Sleepy's app session. There is no
application-level delay after wake. The legacy
`00 D0` / `00 B0` subsystem initializers and `05 02`, `08 02`, and `04 E0`
command families do not apply to `BOX25_STAR`.

#### Motor Commands (category `0x30`)

| Command | Action |
|---------|--------|
| `0x00` | Head up |
| `0x01` | Head down |
| `0x02` | Foot up |
| `0x03` | Foot down |
| `0x06` | Lumbar up |
| `0x07` | Lumbar down |
| `0x0A` | Neck tilt up |
| `0x0B` | Neck tilt down |
| `0x0F` | Stop |

#### Preset and Memory Recall Commands (StarCode, 7 bytes)

The Adjustable Comfort M1X12 app uses StarCode framing for presets:

```text
5A 01 03 10 30 [command] A5
```

| Preset | Command |
|--------|---------|
| Flat | 0x10 |
| Zero Gravity | 0x13 |
| Anti-Snore | 0x16 |
| Lounge/Reading | 0x17 |
| Memory 1 | 0x1A |
| Memory 2 | 0x1B |

Each preset frame is sent three times at 100 ms intervals, followed 100 ms
later by the StarCode commit frame `5A 01 03 10 30 0F A5`. Without that final
frame the bed remains armed until STOP or BLE disconnect (issue #372).

Saving Memory 1/2 uses command `0x94`/`0x95`, respectively. The app models this
as a long press: it repeats the save frame 110 times at 100 ms intervals and
does not append the preset commit frame.

#### Position Commands

```text
5A F0 03 [zone] [position 0-100] 00 A5
```

Zones are `0x00` for head, `0x01` for foot, and `0x02` for lumbar. The status
query is `5A B0 00 A5`.

#### Lighting Commands (category `0x30`)

| Command | Action |
|---------|--------|
| `0x71` | Toggle under-bed light |
| `0x73` | Turn under-bed light on |
| `0x74` | Turn under-bed light off |

Direct brightness uses `5A E0 04 00 [level 0-6] 00 00 A5`.

Arbitrary color uses `5A E0 04 02 [R] [G] [B] A5`, for example
`5A E0 04 02 00 FF FF A5` for cyan. These observations come from a reporter's
hardware tests on a Sleepy's Elite (#557), not from the Sleepy's app, which only
offers preset colors:

- The ON frame (`0x73`) resets the LEDs to white. An RGB frame also lights the
  LEDs from OFF, so the integration turns them on with the last selected color
  (default white) and never sends ON. This avoids a white flash.
- After the RGB frame, the integration resends the last selected level 1-6 to
  restore brightness. Brightness frames keep the current color.
- Levels above 6 (`07` through `FF`) had no effect on the hardware.
- The RGB light entity maps Home Assistant brightness onto levels 1-6. The light
  level number entity still covers 0-6.
- RX notifications appear to carry the current RGB value and brightness. The
  reported fragments (`... 18 11 00 FF FF ...` at level 1, `... 68 11 00 FF FF ...`
  at level 6) lack a frame header and offsets, so the integration does not parse
  them. Light state stays assumed.

The legacy CB25 dialect has no proven color frame. Its extended frame carries
only two values, so legacy beds keep the on/off switch. With the auto variant, a
later connection that resolves the other dialect reloads the entities once the
link is released.

#### Massage Commands

| Category | Command | Action |
|----------|---------|--------|
| `0x30` | `0x52` / `0x53` / `0x54` | Massage modes 1-3 |
| `0x30` | `0x5A` | Toggle massage on/off |
| `0x30` | `0x6F` | Massage off |
| `0x30` | `0x60` / `0x61` | Head strength up/down |
| `0x30` | `0x62` / `0x63` | Foot strength up/down |
| `0x40` | `0x60` / `0x61` | Overall strength up/down |

The direct combined-intensity slider is normalized as 0-7 in the app. Zero is
encoded as zero; positive levels are encoded as 2-8:

```text
5A E0 04 06 [encoded] [encoded] 00 A5
```

The 10/20/30 minute timer maps to values 1/2/3:

```text
5A E0 04 07 [1-3] 00 00 A5
```

#### Legacy CB25 Runtime Dialect

When `2A29` is missing, unreadable, empty, or does not contain `star`, Auto mode
uses the legacy packet builders recovered from the same reachable BOX25 class:

```text
normal:   05 02 [32-bit key, big-endian] 00
extended: 04 E0 [subcommand] [value] [value2] 00
position: 03 F0 [zone] [position] 00
query:    00 B0 (massage/light), 00 D0 (motor position)
```

Movement keys are `1/2` head, `4/8` foot, `10/20` lumbar, `40/80` neck,
and zero for STOP. Preset keys are `08000000` flat, `00004000` TV,
`00001000` zero-G, `00008000` anti-snore, `00002000` lounge,
`00010000` memory 1, and `00040000` memory 2. The integration preserves the
same three-repeat plus STOP recall sequence and the proven long-press memory
programming behavior.

Legacy light on/off uses `04 E0 01 01/00 00 00`; toggle and wave modes use the
10-byte `08 02` family. Direct brightness, combined massage intensity, and the
timer use the same subcommands as StarCode without the `5A ... A5` wrapper.
Feedback uses the shared BOX25 parser below.

#### Notification Parsing

Both legacy `BOX25` and `BOX25_STAR` route Nordic UART RX notifications through
the same parser. A legacy `00 D0` position query and the StarCode
`5A B0 00 A5` query therefore produce the same 20-byte position packet family:

```text
A5 0D ... [head at byte 4] ... [foot at byte 6] ... [lumbar at byte 8] ...
```

Each motor position is clamped to the app's 0-100 range. Issue #372's captured
notification `A5 0D 11 01 16 00 00 ...` therefore reports head position 22.
Parsing is selected by this notification header, not by a pending-query token
or the runtime dialect.

`A5 0B` is the massage/status branch. Remaining duration is the big-endian
value `(byte[4] << 8) | byte[5]`; 1-600, 601-1200, and 1201-1800 seconds map to
the 10, 20, and 30 minute timer choices. The OEM parser consumes each BLE value
event directly and does not reassemble fragments.

## Checksum Calculation (BOX15 only)

The BOX15 protocol uses an inverted 8-bit sum (one's complement):

```python
checksum = (~sum(bytes[0:8])) & 0xFF
```

## Command Timing

From app disassembly:

- **Repeat Interval:** Continuous while button held
- **Pattern:** Send command repeatedly with ~100ms delay
- **Stop Required:** Yes, explicit stop after motor release
- **BOX25 Star normal write mode:** write without response
- **BOX25 Star wake:** one write with response before notifications, no app delay

## Detection

Sleepy's Elite beds are auto-detected by name plus BLE services:

- Device names starting with `star25` (case-insensitive) plus Nordic UART → BOX25, then `2A29` selects StarCode or legacy packets at connection time
- `ELEVATE*` plus Nordic UART → the separate [ELEVATE controller](star-elevate.md),
  never BOX25
- Device names starting with "star" without Nordic UART are treated as a low-confidence BOX25 match because Octo Star2 uses similar names
- Device names containing "sleepy" or "mfrm" (case-insensitive):
  - OKIN 64-bit service (62741523-...) → BOX24
  - FFE5 service (0000FFE5-...) → BOX15

**If auto-detection fails:**

1. Use nRF Connect app to scan your bed
2. If device name starts with "Star" → manually select BOX25 Star
3. If you see service `62741523-...` → manually select BOX24
4. If you only see service `0000FFE5-...` → manually select BOX15
5. If BOX24 doesn't work and your bed has lumbar → try BOX15

## Related Protocols

- **[DewertOkin](dewertokin.md)** - Different command format, uses handle writes
- **[Okin 64-bit](okin-64bit.md)** - Similar service UUID but different packet format
- **[Keeson](keeson.md)** - Same FFE5 service but different command encoding
- **[Adjustable bed (Lumbar) app](adjustable-lumbar.md)** - Also serves `Star` names over Nordic UART, but selects its own tables from an exact `STAR` manufacturer reply; choose that explicit profile for beds using that app

## AdjustableM5X5

Beds controlled by AdjustableM5X5 1.2.3 use the dedicated [app profile](starcode-m5x5.md). Its exact manufacturer selector, lumbar/massage keys, RGB overrides, feedback and accessory grouping differ from the generic BOX25 route. Select the app and confirmed CB25, F23 or kneading class explicitly.
