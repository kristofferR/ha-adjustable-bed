# Keeson

**Status:** ✅ Tested

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), [alanbixby](https://github.com/alanbixby), [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt) and [MangoScango](https://github.com/MangoScango)

## Known Models

Brands using Keeson/Ergomotion actuators:

- Serta
- Ergomotion
- Ergomotion Rio 5.0 / Denver Mattress Hibernation Platinum (advertises as `KSBT03C...`; 3 motors: back, legs, lumbar — no head tilt)
- Ergomotion Rio 6.0 (advertises as `KSBT04...`, works with KSBT protocol)
- Tempur Zero G / Tempur Curve
- Beautyrest Black
- ENSO
- Dawn House
- Restonic
- Omazz Adjusto
- King Koil
- SomosBeds
- Purple adjustable bases
- GhostBed
- Member's Mark (Sam's Club) adjustable beds
- GlideAway ComfortBase Odessa with lift kit (BaseI4/I5 massage controls confirmed)
- South Bay International MMKD
- Sealy Ease
- Some Costco beds

**Beautyrest BLACK app boundary:** The accepted Android app
`com.keeson.beautyrestblack` 1.2.1 (18) uses TCP and network services, with no
reachable Bluetooth bed-control transport in that exact artifact. BLE hardware
using independently identified Keeson protocols remains supported. See the
[complete app disposition](../apk-analysis/dispositions/row044-beautyrest-black.md)
for all 128 exclusions and exact accepted evidence.

**DewertOkin/ORE brands** also using FFE5 protocol (31 apps):
- Simon Li, Cherish Smart, Minghua, Heal Every Night (Simon Li, Heal Every Night and OKIN-Seating have [explicit profiles](#simon-li-heal-every-night-and-okin-seating-profiles))
- ORE: Dynasty, LevaSleep, American Star, Avanti, Comfort Furniture, Hestia Motion, Maxcoil, Power's Bedding, SFM, Ultramatic, Better Living, Koizumi
- See [DewertOkin](dewertokin.md) for full list

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Ergomotion 4.0](https://play.google.com/store/apps/details?id=com.sfd.hump) | `com.sfd.hump` |
| ✅ | [1500 Tilt Base Remote](https://play.google.com/store/apps/details?id=com.sfd.rondure_hump) | `com.sfd.rondure_hump` |
| ✅ | [Q-Plus Adjustable Remote](https://play.google.com/store/apps/details?id=com.sbi.costco) | `com.sbi.costco` |
| ✅ | [Ergomotion](https://play.google.com/store/apps/details?id=com.sfd.ergomotion) | `com.sfd.ergomotion` |
| ✅ | [Tempur Zero G Bed Base](https://play.google.com/store/apps/details?id=com.sfd.row) | `com.sfd.row` |
| ✅ | Tempur Curve | `com.ore.tempur` |
| ✅ | [Member's Mark Base Remote](https://play.google.com/store/apps/details?id=com.sfd.mm) | `com.sfd.mm` |
| ✅ | [Sleep Harmony](https://play.google.com/store/apps/details?id=com.keeson.ssbaudio) | `com.keeson.ssbaudio` |
| ✅ | Ergomotion Sync | `cn.com.mancini` |
| ✅ | Linx | `com.keeson.connectedbed` |
| ✅ | Juna Sleep | `com.keeson.junasleep` |
| ✅ | [Purple Smart Base](https://play.google.com/store/apps/details?id=com.keeson.purpleBase) | `com.keeson.purpleBase` |
| ✅ | [Adjustable Lite](https://play.google.com/store/apps/details?id=com.keeson.adjustablelite) | `com.keeson.adjustablelite` |
| ✅ | Bedsense Bases ([profile](ore-comfort-bed.md)) | `com.ore.sfmc2bedsence` |
| ✅ | INNOVA ([profile](#innova-profile)) | `com.ore.sfm` |
| ✅ | MaxCoil Una ([profile](ore-comfort-bed.md)) | `com.ore.maxcoil` |
| ✅ | Dynasty Bases ([profile](ore-comfort-bed.md)) | `com.ore.Dynasty` |
| ✅ | Restonic BT Remote | `com.keeson.restonicBT` |

## Features

| Feature | BaseI4/I5 | JSON/A00A | KSBT | Ergomotion | Okin | Serta | Sino | Purple (Premium) | Purple (Premium Plus) |
|---------|-----------|------------|------|------------|------|-------|------|------------------|-----------------------|
| Motor Control | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Position Feedback | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Memory Presets | ⚠️ 4 exposed (slot 3 app-confirmed) | ✅ (remote-dependent 0x2000/0x4000/0x8000/0x10000) | ✅ (slots 1-3: Read/TV/M) | ⚠️ 4 exposed (verification needed) | ✅ | ✅ | ✅ | ✅ (2 slots) | ✅ (3 slots) |
| TV Preset | ❌ | ✅ (remote-dependent) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Anti-Snore Preset | ❌ | ✅ (remote-dependent) | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Lounge Preset | ❌ | ✅ (remote-dependent) | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Massage | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Safety Lights | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Zero-G | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

## Protocol Variants

### Base Variant (BaseI4/BaseI5) - Most Common
**Primary Service UUID:** `0000ffe5-0000-1000-8000-00805f9b34fb`
**Format:** 8 bytes `[0xE5, 0xFE, 0x16, b4, b5, b6, b7, checksum]`
**Checksum:** `sum(bytes) XOR 0xFF`

**Fallback Service UUIDs:** Some Keeson beds use different service UUIDs. The integration automatically tries these if the primary isn't found:
- `0000fff0-0000-1000-8000-00805f9b34fb` (characteristic: `0000fff2`)
- `0000ffb0-0000-1000-8000-00805f9b34fb` (characteristic: `0000ffb2`)

The GlideAway ComfortBase Odessa hardware report in
[issue #508](https://github.com/kristofferR/ha-adjustable-bed/issues/508)
confirms these additional BaseI4/I5 massage actions. A 3.6.0 follow-up confirmed
the wave controls, while its logs showed that the dashboard's established
`massage_intensity_level_*` entity IDs no longer existed, so those button
presses never reached BLE. The entity IDs are retained for compatibility.
Their meanings are variant-specific and must not be applied to the KSBT, Sino,
Purple, or Ergomotion profiles. The existing `0x00000200` timer-step action is
separate from wave selection and is displayed as **Massage: Timer** while
retaining its established entity identity.

| Action | Value |
|--------|-------|
| Wave next | `0x10000000` |
| Wave previous | `0x04000000` |
| Intensity 1 | `0x00080000` |
| Intensity 2 | `0x00100000` |
| Intensity 3 | `0x00200000` |

### JSON/A00A Variant (Juna, Linx, Ergo Health)

**Primary Service UUID:** `0000a00a-0000-1000-8000-00805f9b34fb`  
**Write Characteristic:** `0000b002-0000-1000-8000-00805f9b34fb`  
**Indicate Characteristic:** `0000b004-0000-1000-8000-00805f9b34fb`

This family uses a JSON envelope instead of the older binary Keeson packets:

```json
{"code":2,"dvid":"<ble name>","cmd":{"key":"00001000","ctrm":1,"km":1,"keykt":0}}
```

Known remote families from the OEM apps:

- `Quest`
- `Rewind`
- `Restore`
- `Relax`

One-shot buttons use `ctrm=1, km=1, keykt=0`. Held motion is not fully uniform:

- `Quest` uses `ctrm=0, km=3, keykt=1`
- `Rewind`, `Restore`, and `Relax` use `ctrm=1, km=3, keykt=1`

The integration treats `0000a00a` as a distinct Keeson variant and uses the shared 32-bit command values, while accommodating the split held-motion metadata from the Juna/Linx app family.

### KSBT Variant (Direct P2 Remotes)

**Primary Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e` (Nordic UART Service)
**Format:** 6 bytes `[0x04, 0x02, ...int_bytes]` (big-endian)

Ergomotion 4.0, Q-Plus and 1500 Tilt Base write held movement keys immediately
and refresh them every 100 ms. Releasing a key cancels that refresh and writes
the two-byte status query `[0x00, 0xB0]` at +300, +600 and +900 ms. None of
these P2 paths writes the six-byte zero-key packet on release.

Ergomotion Sync 1.0.5's KSBT03C layout B is distinct: it writes immediately and
uses a 300 ms fixed-delay timer. Release only cancels that timer; its status
queries run in a separate background loop. The app leaves Android's
characteristic write type unchanged. Android defaults a characteristic that
advertises write-without-response to that mode, so detected `KSBT03C` beds use
unacknowledged writes when the characteristic supports them. This prevents a
BLE proxy acknowledgement round trip from stretching every refresh interval.
Explicit per-device pulse settings remain authoritative. No KSBT03C release
frame was found in the complete clean-room analysis, so the integration does
not guess or substitute a zero-key frame. Sync's KSBT04C layouts use their
separate integration profile, including its existing zero-frame release.

Some Ergomotion-branded beds also use this variant. A confirmed Rio 6.0 support bundle advertises as `KSBT04...` and works correctly with the standard KSBT 6-byte protocol.
Juna's `LVrestore` and `LVrelax` remotes also use this direct 6-byte framing rather than the JSON/A00A path.

**Ergomotion Sync remotes (from `cn.com.mancini` APK):** the app has three remote layouts — A and C target `KSBT04C` devices, B targets `KSBT03C` (e.g. Rio 5.0). All three share the same preset buttons: Read = `0x2000`, TV = `0x4000`, M = `0x10000`, Zero-G = `0x1000`, Flat = `0x8000000`, light toggle = `0x20000`, and massage steps head `0x800` / foot `0x400` / timer `0x200` (no all-off command). The Anti-Snore button (`0x8000`) appears on layouts B/C only; that describes the remote UIs, not command support — the integration exposes anti-snore on all KSBT variants. Read/TV/M are exposed as memory slots 1-3 on KSBT variants.

**KSBT03C motor layout:** the KSBT03C remote (layout B) drives only three motors — head/back (`0x1`/`0x2`), feet/legs (`0x4`/`0x8`) and lumbar (`0x40`/`0x80`). There are no head-tilt (`0x10`/`0x20`) buttons, so KSBT03C beds have no tilt motor and the integration maps the third configured motor to lumbar. KSBT04C remotes (layouts A/C) additionally have the head-tilt buttons.

That three-motor rule belongs to the direct six-byte KSBT profile. Sleep Harmony
also accepts a `KSBT03C` name but uses its separate explicit profile and exposes
head, foot, tilt/EJ and lumbar controls.

**Status:** the KSBT03C command values and 3-motor layout are APK-derived (Ergomotion Sync 1.0.2) and not yet confirmed on hardware; the Rio 5.0 report in issue #408 confirms the lumbar motor responds to `0x40`/`0x80` and that no tilt motor exists.

The 300 ms cadence, unacknowledged write mode, and timer-cessation release are
statically verified from Ergomotion Sync 1.0.5 but remain hardware-unverified.
The timer cessation is intentional: no release packet exists in the analyzed
app, and a replacement STOP frame must not be guessed without new protocol
evidence or a hardware capture.

**Fallback Service UUIDs:** Some KSBT devices use different service UUIDs. The integration automatically tries these if the primary isn't found:
- `6e400020-b5a3-f393-e0a9-e50e24dcca9e` (characteristic: `6e400021`) - Extended Nordic UART, used by some Ergomotion/SFD beds
- `0000ffe5-0000-1000-8000-00805f9b34fb` (characteristic: `0000ffe9`)
- `0000ffe0-0000-1000-8000-00805f9b34fb` (characteristic: `0000ffe1`)

### KSBT03CR Variant
**Primary Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e` (Nordic UART Service)
**Format:** 7 bytes `[0x05, 0x02, cmd3, cmd2, cmd1, cmd0, 0x00]` (big-endian)

Auto-detected from device name prefix `ksbt03cr`. Uses the same 32-bit command values as standard KSBT; only the framing differs (7-byte packet with `0x05` prefix and trailing `0x00` byte instead of 6-byte packet with `0x04` prefix). Falls back to the same alternative service UUIDs as standard KSBT.

### Sleep Harmony Variant

**Validation status:** Clean-room APK analysis complete; physical Sleep Harmony
hardware has not yet been tested.

Sleep Harmony 1.0.1 has two name-selected packet families behind the explicit
`sleep_harmony` (`Sleep Harmony (KSBT04C / base-i5)`) profile:

| Name prefix | GATT | Frame |
|-------------|------|-------|
| `KSBT04C` / `KSBT03C` | Nordic UART 6E400001 / 2 / 3 | `04 02 + command_be32 + complement checksum` |
| `base-i5.` | FFE5 / FFE9, notify FFE4 | `E6 FE 16 + command_le32 + side 00 + complement checksum` |

Motor commands start immediately and repeat every 300 ms. Releasing a motor or
one-shot button waits 200 ms and sends one protocol-specific zero command. The
integration preserves that UI release delay but keeps the safety `stop_all`
service immediate. Sleep Harmony's popup M1/M2/M3 sends Reading `0x2000`, TV
`0x4000`, and Snore `0x8000`; it has no memory-save action. Its dedicated
massage-off command is `0x02000000`.

These prefixes overlap Purple Smart Base while the packet endings differ. Select
the explicit Purple or Sleep Harmony profile; a name alone cannot distinguish
the ecosystems safely.

### Adjustable Lite Profile

**Validation status:** clean-room analysis of Adjustable Lite 1.0.2 (5) is
complete; hardware is unverified. See the
[app disposition](../apk-analysis/dispositions/row051-adjustable-lite.md).

Select the `adjustable_lite` (`Adjustable Lite app (KSBT01C / KSBT03C)`)
protocol variant. Auto keeps the generic KSBT profile, because Ergomotion Sync
and Sleep Harmony also use `KSBT03C` names with different memory labels,
cadence or release behavior.

The app writes the six-byte KSBT frame `04 02 b2 b3 b4 b5` to Nordic UART
`6e400002`, with no checksum, and never sets a write type. The integration
therefore writes without response when the characteristic offers it, as
Android does by default. It has two remotes, chosen by the case-sensitive
token `KSBT03C` in the device name; any other name gets the KSBT01C remote.

| Control | Frame | KSBT01C | KSBT03C |
|---------|-------|---------|---------|
| Head/back up / down | `04 02 00 00 00 01` / `04 02 00 00 00 02` | ✅ | ✅ |
| Leg/foot up / down | `04 02 00 00 00 04` / `04 02 00 00 00 08` | ✅ | ✅ |
| Flat | `04 02 08 00 00 00` | ✅ | ✅ |
| Zero G | `04 02 00 00 10 00` | ✅ | ✅ |
| Memory 1 (MI) | `04 02 00 01 00 00` | ✅ | ✅ |
| Memory 2 (MII) | `04 02 00 00 20 00` | ✅ | ✅ |
| Memory 3 (MIII) | `04 02 00 00 40 00` | ✅ | ✅ |
| Light | `04 02 00 02 00 00` | ✅ | ✅ |
| Anti-snore | `04 02 00 00 80 00` | ❌ | ✅ |
| Massage timer | `04 02 00 00 02 00` | ❌ | ✅ |
| Head massage + / - | `04 02 00 00 08 00` / `04 02 00 80 00 00` | ❌ | ✅ |
| Leg massage + / - | `04 02 00 00 04 00` / `04 02 01 00 00 00` | ❌ | ✅ |
| Status query | `00 B0` | ✅ | ✅ |

The shipped MI/MII/MIII labels take precedence over the app's internal
`m`/`read`/`tv` names, so memory slots 1-3 differ from the generic KSBT
mapping. The app has no memory save, lounge, TV, tilt, lumbar, massage
toggle or massage off control, and the profile exposes none. Movement
repeats at 0 ms and then every 300 ms. Release only cancels that timer: no
STOP or release frame exists, so the integration sends none. One-shot
controls are written once.

While connected, the app queries `00 B0` every 500 ms. The integration polls
at the same interval on a live connection, without keeping the link open.
Notifications from `6e400003` longer than 12 bytes are read without header or
checksum checks:

| Byte(s) | Meaning | Entity |
|---------|---------|--------|
| 12 | `1` lights the bulb icon; anything else is off | **Light** binary sensor |
| 3-4 (KSBT03C) | Big-endian value; above 1200, 600 or 0 shows the 30, 20 or 10 minute timer image, otherwise none | **Massage timer** sensor (0/10/20/30 min, raw value as attribute) |

Both states exist only while Home Assistant holds the connection. With the
default **Disconnect After Command** handoff, the link closes about a second
after each command, so Light and Massage timer are usually unknown and update
only briefly after a command. Turn the handoff off to keep them current until
the idle timeout, at the cost of holding the bed's Bluetooth connection, which
keeps the phone app out meanwhile.

The app does not decode whether the light button toggles, how the timer
button cycles, massage level limits, or the unit of the raw timer value. Those
remain to be confirmed on hardware.

### Simon Li, Heal Every Night and OKIN-Seating Profiles

**Validation status:** clean-room analysis of Simon Li 1.0.1 (2), Heal Every
Night 1.0 (1) and OKIN-Seating 1.0.1 (2) is complete; hardware is unverified.
See the [app disposition](../apk-analysis/dispositions/row060-okin-simon-cluster.md).

Select the `simon_li`, `heal_every_night` or `okin_seating` protocol variant.
None of the apps filters its scan or reads a model, so Auto never selects
these profiles: add the seat or bed manually as a Keeson bed and pick the app.
Each app controls one address, so add one entry per seat or bed. Their
frames carry no side field. In a two-address pair, unpair the beds before
changing to, from or between these profiles, so each side keeps its own app,
and before changing the motor count while a side uses Heal Every Night,
whose motor count picks that receiver's product. Every control comes from the
stored profile, so a side that is out of range keeps its entities and the
other side of the pair still loads.

All three write `E5 FE 16 + key_be32 + (~sum(bytes 0-6) & 0xFF)` to the first
FFE9 characteristic of the last service, in Java UUID order, that has one.
The SDK rejects a characteristic without the write property, and the apps
never set a write type, so the integration writes without response when FFE9
offers it, as Android does. The apps enable notifications on every FFE4
characteristic and discard the bytes, so the integration subscribes too and
keeps the replies for diagnostics only. There is no PIN, pairing or
initialization frame.

Held keys write at 0 ms and then every 100 ms (10 x 100 ms per Home Assistant
press by default). The motor pulse count sets how many writes a press makes;
the interval stays at the apps' fixed 100 ms whatever the pulse delay. The release cancels the refresh and writes the zero key
`E5 FE 16 00 00 00 00 06`: Simon Li and OKIN-Seating sleep 10 ms first, Heal
Every Night 100 ms. A cover stop or the end of a timed move writes it at once;
**Stop All** does too. The
`okin_app_hold_control` action holds any streamed control for 0.1-60 s.

| Control | Simon Li | OKIN-Seating |
|---------|----------|--------------|
| Back up / down | `0x04` / `0x08` | `0x04` / `0x08` |
| Foot up / down | `0x01` / `0x02` | `0x01` / `0x02` |
| Lumbar up / down | `0x10` / `0x20` | - |
| Home (button) | `0x16` | `0x0A` |
| Memory 1 / 2 | `0x40` / `0x80` | - |

Every control, including Home and memory, is a held key. Home keeps the app's
neutral label: the apps do not show that it means flat. Simon Li has no save
command: holding a memory key for 2.1 seconds shows "Memory saved", so
**Save memory** holds the same key for 2.1 seconds. A memory recall ends
after at most 2 seconds of elapsed time, whatever the pulse settings or write
latency, so it stays below the app's 2.1 s save hold. Whether the seat stores
the position, and its own save threshold, are unverified. OKIN-Seating's foot
buttons carry the opposite "union" artwork; the integration follows the
button identifiers. The motor count does not change these fixed controls.

Heal Every Night picks Healing 6, 7 or 8 with the motor count (2, 3 or 4).
Healing 7 and 8 both show tilt, lumbar and the light. Its keys:

| Control | Key | Products |
|---------|-----|----------|
| Head up / down | `0x01` / `0x02` (see settings) | all |
| Foot up / down | `0x04` / `0x08` (see settings) | all |
| Tilt up / down | `0x10` / `0x20` | Healing 7/8 |
| Lumbar up / down | `0x40` / `0x80` | Healing 7/8 |
| Zero G / Flat | `0x01000001` / `0x01000002` | all |
| Memory A / B (slots 1 / 2) | `0x01000008` / `0x01000009` | all |
| Save memory A / B | `0x20000008` / `0x20000009` | all |
| Preset STOP | `0x01000000` | all |
| Head massage level 0-3 | `0x10000010` + level | all |
| Foot massage level 0-3 | `0x11000010` + level | all |
| Wave 1-4 | `0x10000020` + wave - 1 | all |
| Timer 10/20/30 | `0x10000030` (the same key for every label) | all |
| Light on / off | `0x31000001` / `0x31000000` | Healing 7/8 |

Presets are single writes. Pressing the selected preset again sends Preset
STOP instead, as the app does, and selecting another preset moves the
selection. **Stop All** also sends Preset STOP while a preset is selected; a
cover stop does not, as the app's movement release does not.

The massage page stays disabled until a timer is chosen. A timer turns zero
levels into one, then writes the timer key, the wave, head and foot levels
100 ms apart. The level sliders (head and foot 0-3, wave 1-4) and the
+/- buttons then write one frame each; +/- clamp but still write. **Massage:
Off** (or the timer's Off) writes head 0 and foot 0 and disables the page
again, keeping the levels. The light switch writes the explicit on/off key. The bed reports no light
state, so the switch starts unknown and shows the commanded state as assumed.
Preset selection, light state and massage levels change only once their
frames are written, so a failed or cancelled write leaves the previous state
for a retry. They are kept across reconnects
until the entry is removed or its profile changes. Home Assistant allows
massage Off and any timer at any time, while the app disables Off before a
timer starts and disables the running timer's button.

Three settings selects mirror the app's settings page. They send nothing,
only change which key the head and foot controls write, and are cleared when
the profile changes:

| Setting | Effect |
|---------|--------|
| Installation mode: swapped | Head controls drive the foot actuator and foot controls the head actuator |
| Actuator 1 direction: reversed | The head actuator's up and down keys are exchanged |
| Actuator 2 direction: reversed | The foot actuator's up and down keys are exchanged |

Excluded: phone vibration, the scan and slot screens, dead helpers (the
rename writer, password and query constants, time and sensor parsers, timers
2 and 3, the quiet-sleep preset and legacy screens), and the apps' Android
lifecycle and queue defects. Real users should confirm, after a beta or
release, which actuators each key moves, what Home does, whether memory saves
persist, the Heal massage and light semantics, and the GATT layout.

### INNOVA Profile

**Validation status:** clean-room analysis of INNOVA 2.0 (3) (`com.ore.sfm`)
is complete; hardware is unverified. See the
[cluster disposition](../apk-analysis/dispositions/row059-ore-bedsense-innova.md).
Its cluster sibling Bedsense Bases uses the
[MaxCoil Una / Dynasty Bases / Bedsense Bases profile](ore-comfort-bed.md).

Select the `innova` (`INNOVA app`) protocol variant. The app scans without any
name or service rule, so Auto never chooses it; `ORE-` names stay on the Base
profile. Set the motor count to the screen picked in the app: 2 (2M), 3 (3M)
or 4 (4M). For a two-address pair, split the pair before
changing the profile: each receiver keeps its own app profile. A pair side
that is out of range keeps its controls, built from the stored profile.

The app writes `E5 FE 16 k0 k1 k2 k3 checksum` to `0000ffe9`: the standard
Keeson 32-bit key in little-endian order, then the complemented byte sum. It
requires `0000ffe4` to exist and never sets a write type, so the integration
writes without response when the characteristic offers it, as Android does.

| Control | Key | Exposed as |
|---------|-----|------------|
| Back up / down | `0x00000001` / `0x00000002` | Back cover |
| Legs up / down | `0x00000004` / `0x00000008` | Legs cover |
| 2M back and legs together | `0x00000005` / `0x0000000A` | Back + Legs cover |
| 3M third actuator (lumbar IDs) | `0x00000040` / `0x00000080` | Lumbar cover |
| 4M waist | `0x00000010` / `0x00000020` | Waist cover |
| 4M lumbar | `0x00000040` / `0x00000080` | Lumbar cover |
| Zero G / Flat | `0x00001000` / `0x08000000` | Zero G / Flat buttons (one write) |
| Memory A / B | `0x00002000` / `0x00004000` | Memory A / B buttons (held) |
| Light | `0x00020000` | Toggle light button |
| Head massage + / - | `0x00000800` / `0x00800000` | Head massage buttons |
| Foot massage + / - | `0x00000400` / `0x01000000` | Foot massage buttons |
| Massage level | `0x00000100` | **Massage level** button |
| Massage timer (massage page) | `0x00000200`, one write | **Massage: Timer** button |
| Massage timer (memory page) | `0x00000200`, held | **Massage timer (memory page)** button |
| Release / Stop | `0x00000000` | Stop button |

Held controls write at 0 ms and then every 100 ms. Releasing them writes the
zero key 100 ms later; a Stop, a cancelled hold or a replacement writes it at
once, on a fresh event, so it cannot be suppressed. One-shot controls sleep
100 ms before their write, as the app does. A cover or held button press holds
for the motor pulse count (10 x 100 ms by default). `innova_hold_control` holds
any streamed control for 0.1-60 s: `back_up`, `back_down`, `legs_up`,
`legs_down`, `memory_a`, `memory_b`, `memory_timer`, plus `combined_up/down`
(2M), `lumbar_up/down` (3M and 4M) and `waist_up/down` (4M).

INNOVA has no memory programming, absolute massage level, massage off or
anti-snore control. The `innova_rename` action writes the app's 18-byte
`EF 02` name frame: at most 14 characters as typed, then trimmed and non-empty.

INNOVA subscribes to `0000ffe4`. Only 16- and 19-byte notifications are read,
without header or checksum checks:

| Length | Flag byte | Timer byte |
|--------|-----------|------------|
| 16 | 13 | 14 |
| 19 | 14 | 15 |

Flag bit 5 (`0x20`) suppresses the update and bit 6 (`0x40`) is the lamp icon,
shown as the **Light** binary sensor. The signed timer byte `-1` clears the
**Massage timer** sensor and `1`/`2`/`3` show 10/20/30 minutes; other values
leave it unchanged. Both states clear when the connection ends. The app shows
the lamp only on its light page and the timer only on its other pages; Home
Assistant shows both. The app enables FFE4 locally without writing the CCCD,
so delivery after Home Assistant subscribes needs confirming on hardware.

Hardware still needs to confirm the physical actuator behind each key
(the 3M third motor uses lumbar IDs beside head artwork), how long Memory A/B
must be held, massage level limits and timer cycling, and the lamp bit.

### Restonic BT Profiles

**Validation status:** clean-room analysis of Restonic BT Remote 1.2.0 (3) is
complete; hardware is unverified. See the
[app disposition](../apk-analysis/dispositions/row058-restonic-bt.md).

The app has two remote styles, chosen by the user in its settings (A is the
default). Select the matching protocol variant: `restonic_a` (`Restonic BT
app, remote A (6 buttons)`) or `restonic_b` (`Restonic BT app, remote B (10
buttons)`). Neither is ever chosen automatically: the app accepts any device
name that starts with `base-i4` or `base-i5` (case-sensitive), and those names
are shared with Member's Mark, Purple, Sleep Harmony and Cool Base, which use
different cadences, releases or frames. How discovery offers such a bed:

| Advertised name | Offered as | What a Restonic BT user does |
|-----------------|------------|------------------------------|
| `base-i4…` (with or without a dot) | Keeson, Auto (Base profile) | Choose the `restonic_a` or `restonic_b` protocol variant |
| `base-i5…` (any) | Cool Base | Change the bed type to Keeson, then choose `restonic_a` or `restonic_b` |

Both styles write the Base frame `E5 FE 16 + command_le32 + checksum`, where
the checksum is `(~sum(bytes 0-6)) & 0xFF`, to FFE5 / FFE9 only. The app never
sets a write type, so the integration writes without response when the
characteristic offers it, as Android does by default. There is no
notification, read, handshake, PIN or memory.

| Control | Frame | Remote A | Remote B |
|---------|-------|----------|----------|
| Head up / down | `E5 FE 16 01 00 00 00 05` / `E5 FE 16 02 00 00 00 04` | Held | Held |
| Foot up / down | `E5 FE 16 04 00 00 00 02` / `E5 FE 16 08 00 00 00 FE` | Held | Held |
| Back + Legs up / down (head and foot together) | `E5 FE 16 05 00 00 00 01` / `E5 FE 16 0A 00 00 00 FC` | ❌ | Held |
| Flat | `E5 FE 16 00 00 00 08 FE` | Once | Once |
| Zero G | `E5 FE 16 00 10 00 00 F6` | Held | Once |
| Light | `E5 FE 16 00 00 02 00 04` | ❌ | Once |
| ZZZ | `E5 FE 16 00 80 00 00 86` | ❌ | Once |
| Release | `E5 FE 16 00 00 00 00 06` | After every control | After every control |

Held controls write at once and then every 100 ms. Once controls write a single
frame when the button is pressed. Releasing any control writes the zero frame
100 ms later. In Home Assistant, a cover or held Zero G button press holds for
the motor pulse settings (10 x 100 ms by default), one-shot buttons press once,
and `restonic_hold_control` holds any control for a chosen duration. A Stop,
a cover's stop, or a command that replaces a running hold writes the zero frame
at once instead of after 100 ms, and a Stop during that 100 ms ends the wait.
The Back + Legs cover shares its scheduler lane with the head and foot covers,
so moving or stopping either of them interrupts it.

Remote B's back-up and back-down glyphs appear as a **Back + Legs** cover. The
app sends the same light frame on every press and tracks no state, so the light
is a toggle button, not a light entity. ZZZ is exposed as a **ZZZ** button: the
app does not show what it does, so it is not mapped to anti-snore or a memory.

Deferred validation for real users: the actual write mode, whether the light
toggles, what ZZZ does, how many actuators move, and whether the zero frame
stops motion and presets.

### Sino Variant (Dynasty, BetterLiving)
**Primary Service UUID:** `0000ffe5-0000-1000-8000-00805f9b34fb`
**Format:** 8 bytes `[0xE5, 0xFE, 0x16, b4, b5, b6, b7, checksum]` (big-endian byte order)

Used by BetterLiving/OKIN-BLE devices. Same packet structure as Base variant but with big-endian command byte ordering. Auto-detected by name pattern `okin-ble`.

The current MaxCoil Una and Dynasty Bases apps use the same frame with different preset, save and massage words and a 2M/3M/4M layout choice. Select their explicit [MaxCoil Una / Dynasty Bases profile](ore-comfort-bed.md) (`maxcoil_una` or `dynasty_bases`); `sino` is unchanged.

### Ergomotion Variant (with Position Feedback)
Same protocol as Base variant but with real-time position updates via BLE notifications.

### Purple Variant

Purple Smart Base 1.0.8 has two explicitly selected products:

| Product | Name prefix | GATT | Command frame |
|---------|-------------|------|---------------|
| Premium | `base-i5` | FFE5 / FFE9, notify FFE4 | `E5 FE 16 + mask_le32 + complement checksum` |
| Premium Plus | `KSBT04C` | Nordic UART 6E400001 / 2 / 3 | `04 02 + mask_be32 + 00` |

Both repeat movement every 100 ms. On release, the app writes the Premium Plus
zero-mask frame `04 02 00 00 00 00 00`, including when Premium's FFE9 target is
selected. Premium has lounge, anti-snore and two memory slots. Premium Plus has
pillow and lumbar motors, anti-snore, three memory slots, massage, underbed and
motion lighting, and no lounge action.

Memory recall/save masks differ:

| Slot | Premium | Premium Plus |
|------|---------|--------------|
| 1 | `0x00010000` | `0x00010000` |
| 2 | `0x00004000` | `0x00002000` |
| 3 | unavailable | `0x00004000` |

The dedicated save flow performs 26 writes, each after 200 ms, for about 5.2
seconds. Notifications report massage time/strength, light state, motion-light
state/duration and version; the app contains no bed-position feedback parser.
Select the explicit Purple profile because `base-i5` and `KSBT04C` names are
also used by other Keeson app families with different packet endings.

### Commands (32-bit Values)

| Command | Value | Description |
|---------|-------|-------------|
| Stop | `0x00000000` | Stop all |
| Head Up | `0x00000001` | Raise head |
| Head Down | `0x00000002` | Lower head |
| Feet Up | `0x00000004` | Raise feet |
| Feet Down | `0x00000008` | Lower feet |
| Tilt Up | `0x00000010` | Raise tilt (pillow area) |
| Tilt Down | `0x00000020` | Lower tilt (pillow area) |
| Lumbar Up | `0x00000040` | Raise lumbar |
| Lumbar Down | `0x00000080` | Lower lumbar |
| Massage Step | `0x00000100` | Cycle massage mode |
| Massage Timer | `0x00000200` | Cycle massage timer |
| Massage Foot Up | `0x00000400` | Increase foot massage |
| Massage Head Up | `0x00000800` | Increase head massage |
| Zero-G | `0x00001000` | Zero-G preset |
| Memory 1 / Lounge | `0x00002000` | KSBT "Read" button; Purple Premium lounge; Purple Plus memory 2 |
| Memory 2 / TV | `0x00004000` | KSBT TV button; Purple Premium memory 2; Purple Plus memory 3 |
| Memory 3 / Anti-Snore | `0x00008000` | Memory 3 on BaseI4/I5, Anti-Snore on KSBT and Purple |
| Memory 4 / M | `0x00010000` | KSBT "M" button (memory slot 3), Maps to Memory 1 on Purple |
| Toggle Lights | `0x00020000` | Toggle safety lights |
| Massage Head Down | `0x00800000` | Decrease head massage |
| Massage Foot Down | `0x01000000` | Decrease foot massage |
| Flat | `0x08000000` | Flat preset |
| Massage Wave | `0x10000000` | Cycle wave massage |

> **Note:** Command `0x00008000` has different meanings depending on the protocol variant:
> - On **BaseI4/I5**: This is Memory 3 preset
> - On **KSBT and Purple**: This is Anti-Snore preset
> - On **Juna/Linx JSON remotes**: It may be Memory 3, Sleep, or another remote-specific preset depending on the remote family
>
> The `0x00002000`, `0x00004000`, `0x00008000`, and `0x00010000` addresses are reused by multiple Keeson remote families. On Juna/Linx they can correspond to `M`, `Read`, `TV`, `Sleep`, or memory slots depending on the chosen remote.

## Command Timing

Fresh decompilation of each relevant OEM app found that cadence belongs to the
app/protocol family, not to the shared 32-bit command values:

| Integration variant | OEM app evidence | App hold behavior | Effective default burst |
|---------------------|------------------|-------------------|-------------------------|
| BaseI4/BaseI5 | Member's Mark | 400ms fixed-delay scheduler | 3 writes, 400ms apart; Base-family zero frame on release |
| JSON/A00A | Juna / Linx | Requests every 5ms / 3ms, but drops requests while a write-with-response is pending | Existing safe 10 writes, 100ms apart |
| KSBT direct P2 | Ergomotion 4.0 / Q-Plus / 1500 Tilt Base | 100ms in the SFD apps | 10 writes, 100ms apart; explicit user overrides are preserved |
| KSBT03C | Ergomotion Sync 1.0.5, Rio 5 layout | Immediate write plus 300ms `Timer.schedule`; release only cancels the timer | 4 writes, 300ms apart, with no release packet |
| KSBT03CR | SomosBeds | 300ms `Timer.schedule` | 4 writes, 300ms apart |
| Sleep Harmony (`KSBT04C` / `base-i5.`) | Sleep Harmony | 300ms handler loop | 4 writes, 300ms apart |
| Adjustable Lite (`KSBT01C` / `KSBT03C`) | Adjustable Lite | Immediate write plus 300ms `Timer.schedule`; release only cancels the timer | 4 writes, 300ms apart, with no release packet |
| INNOVA | INNOVA | Immediate write, then every 100ms; release sends the zero key 100ms later | 10 writes, 100ms apart, then the zero key |
| Restonic BT (remote A / B) | Restonic BT Remote | Immediate write plus 100ms `Timer.schedule`; release writes one zero frame 100ms later | 10 writes, 100ms apart, then the zero frame after 100ms |
| Ergomotion | Ergomotion / Ergomotion 4.0 / Tempur Zero G | 100ms handler loop | 10 writes, 100ms apart |
| Serta | Serta MP Remote | 100ms handler loop | 10 writes, 100ms apart |
| Sino / BetterLiving OKIN | BetterLiving | 100ms on the two-motor screen, 200ms on the three-motor screen | 10 x 100ms or 5 x 200ms |
| Purple | Purple Smart Base | 100ms fixed-delay scheduler | 10 writes, 100ms apart |

The JSON apps do not provide a fixed on-air cadence: their 3/5ms scheduler only
requests a write, and the BLE layer permits one outstanding acknowledged write.
Copying 3/5ms as a BLE delay would therefore be misleading and could shorten an
HA movement burst substantially. The integration retains its established safe
JSON burst until an on-air capture provides a device-independent interval.

For existing Keeson entries, the integration translates only the stored generic
`10 x 100ms` values to the matching app profile. Any pulse count or delay that a
user customized remains authoritative. Dedicated Ergomotion, Serta, and OKIN FFE
bed types already store their own app-derived defaults and are left unchanged.
BetterLiving devices use the BetterLiving cadence whenever that app profile is
detected, even if a future factory path pairs the profile flag with a different
base Keeson variant.

Release behavior also varies. The current SFD direct-six-byte P2 apps stop their
100 ms refresh and send `00 B0` queries at +300/+600/+900 ms. Ergomotion Sync
stops its movement refresh without a dedicated release write; its independent
status timer continues sending `00 B0`. Base (including the integration's
Member's Mark route), Ergomotion, and Serta retain their family-specific zero
frames. Purple uses the explicit seven-byte P2 zero frame. Sleep Harmony waits
200 ms and sends one zero frame after both movement and one-shot actions.
Restonic BT does the same after 100 ms.
KSBT03CR retains its independently derived release behavior. One-shot commands
themselves are sent once before any profile-specific release.

## Split-Bed Support (Member's Mark)

Member's Mark beds support independent control of left and right sides using a 9-byte packet:

```
[0xE6, 0xFE, 0x16, cmd_lo, cmd_mid_lo, cmd_mid_hi, cmd_hi, side, checksum]
```

| Side Byte | Meaning |
|-----------|---------|
| `0x00` | Default |
| `0x01` | Side A (Right) |
| `0x02` | Side B (Left) |

## Device Detection

Unique service UUID auto-detection:

- `0000a00a-0000-1000-8000-00805f9b34fb` -> JSON/A00A variant

| Device Name Prefix | Protocol |
|-------------------|----------|
| `base` / `base-i5` | Ambiguous: Auto keeps the Base profile; Purple Premium uses E5/8-byte and Sleep Harmony uses E6/9-byte, so select either profile explicitly. Restonic BT (`base-i4` / `base-i5`) users select their remote's profile |
| `KSBT01C` | Nordic UART with 6-byte packets; select the Adjustable Lite profile for that app |
| `KSBT03C` | Nordic UART with 6-byte packets (3 motors: no head tilt; e.g. Ergomotion Rio 5.0); Adjustable Lite users select its profile |
| `KSBT04` | Nordic UART with 6-byte packets (confirmed Rio 6.0 family) |
| `KSBT04C` | Ambiguous: Auto keeps the legacy generic checksum profile; Purple Plus uses a trailing zero and Sleep Harmony uses app-specific checksum/release behavior, so select either profile explicitly |
| `ksbt03cr` | Nordic UART with 7-byte packets (KSBT03CR variant) |
| `EH` | Mattress variant (E0FF service) |

Discovery also matches name-only `KSBT01C*` and `KSBT03C*` advertisements.
The Adjustable Lite app also accepts the identity in the middle of a name. Auto
stays prefix-based so existing entries keep their frames; such beds can be added
manually with the Adjustable Lite profile, which selects its remote the same way.

Discovery likewise matches name-only `base-i4*` and `base-i5*` advertisements,
the names the Restonic BT Remote app accepts. Any name starting with `base-i4`,
with or without the dot, is detected as Keeson (Auto keeps Base); any `base-i5`
name is still offered as Cool Base. See
[Restonic BT profiles](#restonic-bt-profiles) for switching to the profile.
