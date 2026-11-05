# Leggett & Platt

**Status:** ⚠️ Partially tested (Gen2 LP Comfort Connect pairing and movement in [discussion #614](https://github.com/kristofferR/ha-adjustable-bed/discussions/614) and [#385](https://github.com/kristofferR/ha-adjustable-bed/issues/385); the QRRM Richmat route's presets in [#504](https://github.com/kristofferR/ha-adjustable-bed/issues/504); other variants and features need more testing)

[Discussion #614](https://github.com/kristofferR/ha-adjustable-bed/discussions/614) confirms that a Prodigy LBR with an LP Comfort Connect 209-M001 controller was auto-detected, bonded through an ESPHome Bluetooth proxy, and moved with tested commands. The reporter has not yet checked every motor, preset, massage and lighting control, or long-term connection stability.

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), MarcusW, [Josh Pearce](https://github.com/joshpearce), and [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt)

## Known Models

- Leggett & Platt Prodigy 2.0 / S-Cape 2.0
- Leggett & Platt Prodigy LBR (LP Comfort Connect 209-M001; Gen2 movement and bonding confirmed)
- Leggett & Platt Prodigy Comfort Elite / Prodigy CE (`LP BED CONTROL`, CU170)
- Leggett & Platt beds with "MlRM" Bluetooth name prefix
- Some Tempur-Pedic bases (non-Ergo)
- Fashion Bed Group bases

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [L&P Adjustable Base](https://play.google.com/store/apps/details?id=com.richmat.lp2) 2.3.25 | `com.richmat.lp2` |
| ✅ | L&P Adjustable Base 2.2.1 (legacy) | `com.richmat.lp` |
| ✅ | [LP Control](https://play.google.com/store/apps/details?id=com.leggett.android.universal) 2.9.0 (LP Comfort Connect) | `com.leggett.android.universal` |

## Features

| Feature | Gen2 | Okin | MlRM | QRRM profile |
|---------|------|------|------|--------------|
| Motor Control | ✅ (head, feet, pillow, lumbar) | ✅ (head, feet, tilt, lumbar) | ✅ (discrete) | ✅ (head, feet) |
| Position Feedback | ❌ | ❌ | ❌ | ❌ |
| Memory Presets | ✅ (4 slots) | ✅ (4 slots) | ✅ (2 slots) | ✅ (2 slots) |
| Massage | ✅ (0-10 levels) | ✅ (wave, timer) | ✅ (discrete UP/DOWN) | ❌ |
| Lighting | ✅ RGB | ✅ Toggle | ✅ Toggle | ❌ |
| Anti-Snore | ✅ | ❌ | ✅ | ❌ |
| Zero-G | ❌ | ✅ | ✅ | ✅ |
| TV Preset | ❌ | ❌ | ✅ | ❌ |
| Lounge Preset | ❌ | ❌ | ✅ | ❌ |
| Hold until release | ✅ ([renewable](../SERVICES.md#renewable-holds): 200 ms refresh, then STOP) | ❌ | ❌ | ❌ |

## Home Assistant setup

The bed-type list has one **Leggett & Platt: Prodigy CE, Prodigy 2, Prodigy 2L,
U Series, LP Control and L&P Adjustable Base apps** row; the Gen2 and MlRM rows
are behind it. Setup then asks which app or remote you use. Each answer comes
from that app's accepted report; the bed's name never decides it.

| Answer | Route |
|---|---|
| Prodigy CE (Prodigy 4), Prodigy 2, Prodigy 2L or U Series app | [Leggett Okin](okin-nframe.md#leggett-okin-family) with that app's layout; requires pairing |
| LP Control app with an LP BED receiver | Leggett Okin with its default (Prodigy CE) layout; requires pairing |
| LP Control app with an LP Comfort Connect base | [Gen2](#gen2-variant); requires pairing |
| L&P Adjustable Base app with an MlRM base | [MlRM](#mlrm-variant) |
| L&P Adjustable Base app with a QRRM remote (Flat, Zero G, Custom 1, Custom 2) | [Richmat](richmat.md) with the **L&P QRRM** remote |
| L&P Adjustable Base legacy app (2.2.1) | [L&P legacy](lp-legacy.md), which keeps its own row and settings |
| I don't know: keep the current controls | The detected or chosen route |

LP Control lists its own Okin products, but none is proven to change the Leggett
Okin layout, so LP Control on an LP BED receiver keeps the default one.

For an existing bed, open the entry's three-dot menu and **Reconfigure** (see
[Changing the app or layout](../CONFIGURATION.md#changing-the-app-or-layout-of-an-existing-bed));
**Keep** leaves the entry as it is. An entry on the legacy app or on the L&P
app's QRRM remote gets the same question. A change to the Okin or Gen2 route pairs the
bed before the review, as setup does; the MlRM, Richmat and legacy routes switch
unchecked, as Configure did. A saved `leggett_platt` entry keeps that ID. A
review lists the added and removed controls before **Apply this change** saves
it. **Configure** keeps routine settings; the app, layout and route change only
through **Reconfigure**.

## Detection

Leggett & Platt beds have four protocol variants with different detection methods:

### QRRM Richmat Variant

Some L&P bases advertise as `QRRM` and are configured as the **Richmat** bed
type, rather than one of the three Leggett-specific variants below. QRRM does
not identify the physical remote layout. If the remote has Flat, Zero G,
Custom 1, and Custom 2 buttons, answer the [L&P question](#home-assistant-setup)
with **L&P Adjustable Base app with a QRRM remote**, or select **L&P QRRM** as
the Richmat remote in an existing Richmat entry's options. The current L&P and Richmat apps likewise require a typed,
scanned, or previously saved physical remote profile because the BLE peripheral
does not expose one. Flat is confirmed on the issue #504 hardware; the other
command frames are recovered consistently from the current apps and still need
physical validation. See [Richmat](richmat.md) for the protocol details.

### Gen2 Variant
- **Service UUID:** `45e25100-...` (unique to Gen2), when advertised
- **LP Comfort Connect (control box 209-M001, ESP32):** advertises **no service
  UUID** — only manufacturer data under company ID `0x092D` (2349) whose payload
  begins with ASCII `XP` or `CP` (e.g. `58 50 05 00 00 00` = `"XP"…`). Detected
  from that prefix, matching the LP Control app's `isGen2Box()` check.
- Detection: automatic by service UUID **or** the `XP`/`CP` manufacturer prefix.

> **Connection & bonding (LP Comfort Connect):** LP Control requests an Android
> **BLE bond** for an unbonded Gen2 device, but only after service discovery
> (`BLEConnectionViewModel.java:210-218`: `SERVICES_DISCOVERED` + bond state
> `BOND_NONE` + Gen2 → `createBond()`), while the Gen2 controller concurrently
> configures its GATT receive paths.
>
> **The bond is advisory, not required.** That `createBond()` is the only one in
> the whole app, there is no `ACTION_BOND_STATE_CHANGED` receiver and no bond
> retry anywhere, and the call site deliberately falls through rather than
> returning — so the app never learns whether the bond succeeded and simply
> keeps using the same link either way. It also connects with
> `connectGatt(ctx, autoConnect=true, cb, TRANSPORT_LE)`
> (`BLEService.java:195`), i.e. an untimed background connection, and never
> disconnects to "retry properly".
>
> **The box grants roughly one connection per power cycle.** The issue #385
> bundles record exactly one completed connection followed by an unbroken run of
> connect timeouts (3.3.0: `connect_completed_total: 1` at 39s after startup,
> then 41 consecutive failures, every one of them this bed) until the base is
> unplugged. Whether the firmware filters unbonded peers at the link layer or
> stops advertising connectably is hardware behaviour the APK cannot prove.
>
> Both facts drive the same rule: **never spend or discard a live link.** The
> integration therefore mirrors the app on the first connection — connect
> without a bond, discover the live GATT services, then create the BLE bond
> while that link is active — and if the bond fails it logs the failure, raises
> the pairing repair, and *keeps the connection* rather than reconnecting.
> For the same reason the setup capability probe, the config flow's "Pair Now"
> step and the pairing repair flow do not open their own throwaway connection
> for this bed type; the repair drives the coordinator instead. All connect
> paths also share a per-address lock so two attempts cannot collide into
> `org.bluez.Error.InProgress` and abort each other.
>
> **An unpaired reconnect is unencrypted, not unbonded.** Through an ESP32
> Bluetooth proxy, a reconnect that skips the bond request leaves the link
> unencrypted even though the bed still holds the bond, so commands fail with
> "Insufficient encryption" (issue #709). BlueZ raises link security on that
> reply by itself; the proxy in that report did not. When a command hits that
> error on a link that has not paired, the integration first pairs the live
> link in place.
> With stored keys this needs no pairing mode. The repair is raised only when
> the bed refuses, or when a link that already paired fails again. After the
> first such failure, every reconnect requests the bond after service discovery,
> and a reconnect that bonds clears any earlier repair, because this bed has no
> Device Information characteristic for the usual bond probe.
>
> Pairing should still happen during the pairing window:
>
> - **Entering pairing mode** (per the LP Control app): unplug the bed, remove
>   any batteries from the power supply, plug it back in — a small chime plays
>   and a pulsing blue light shows under the bed. Pair promptly while it pulses;
>   the APK does not state the duration of this initial power-cycle window.
>   A connected client can also re-open the window with the `PAIR ENABLE`
>   serial command; for that "Pair Another Phone" flow, the app states that
>   pairing mode remains active for 2 minutes. On the reported Prodigy LBR,
>   **LP Control → Settings → Change Bed settings → Re-enable pairing mode**
>   opened the pairing window without a power cycle; the integration's
>   **Begin pairing** action then bonded through an ESPHome proxy.
> - `DWIPE` is the app's Gen2 factory-reset command, and its own dialog lists
>   "Bluetooth Pairings" among what it erases. The app's take-ownership copy
>   also tells the user to remove the bond from phone settings afterwards, so
>   `DWIPE` does not clear the central-side bond. It needs an existing
>   connection, so it is a recovery tool after connecting, not a way in.
> - **A bond that fails to authenticate (`AuthenticationFailed` /
>   `AuthenticationRejected`).** The
>   issue #385 logs show the box accepting an unbonded GATT link, failing the bond at the
>   SMP authentication stage, and dropping the connection about a second later,
>   repeatedly. BlueZ's `AuthenticationFailed` is generic, so the cause is not proven from
>   the error alone. The reading that best fits the evidence is stale key material: the box
>   still holds a pairing for the connecting adapter while that adapter no longer
>   has the matching key, so neither side accepts the other and re-pairing alone
>   changes nothing. `DWIPE`'s own dialog lists "Bluetooth Pairings" among what
>   it erases, and the app tells the user to remove the bond from phone settings
>   as well, which is the same both-sides asymmetry. Recovery therefore means
>   clearing the connecting adapter (`bluetoothctl remove` on a host, or the
>   proxy itself when connecting through ESPHome) **and** the box's own pairing
>   table, then pairing inside the power-cycle window. Unverified on hardware:
>   no reporter has yet confirmed that this restores pairing.
>
> - No per-box limit on how many phones can be paired appears anywhere in the
>   app: an exhaustive search of the base string table and all shipped locale
>   tables found no cap, no "already paired to another phone" error, and no
>   eviction policy. That is absence of evidence in the app, not proof about the
>   firmware.
>
> Once BlueZ confirms the bond the integration records it and skips `pair=True`
> on later connections. The initial bond is confirmed on the Prodigy LBR in
> [discussion #614](https://github.com/kristofferR/ha-adjustable-bed/discussions/614);
> subsequent reconnects and long-term stability remain unverified. The
> integration holds the link open for this bed type (no idle disconnect); LP
> Control's own UI warns that the remote does not function while the app is
> connected.

### Okin Variant
- **Service UUID:** `62741523-...` (shared with Okimat and Nectar)
- **Device name:** `LP BED...` (LP Control's own prefix), or a name containing
  "leggett" / "l&p"
- Detection: automatic from the name plus the shared Okin service
- Some Prodigy CE / CU170 receivers also expose CSS `90311623-...` and Nordic
  DFU `00001530-...`. LP Control ignores both services for bed control, so their
  presence must not override the `LP BED` identity to Okin CST.

### MlRM Variant
- **Service UUID:** WiLinke service (`f0010001-...` or `fee9`)
- **Device Name:** Starts with "MlRM"
- Detection: Automatic by device name prefix + WiLinke service UUID

**If your Okin bed is misidentified as Okimat:** in Configure, change the bed type to the Leggett & Platt row and submit, then choose the app layout it shows. LP Control with an LP BED receiver uses the default Prodigy 4 (Prodigy CE) layout.

See also: [Okin Protocol Family](../SUPPORTED_ACTUATORS.md#okin-protocol-family)

### Aliases

`leggett_platt` is kept for existing entries and is not offered in the bed-type
list. With variant `gen2`, or `auto` when the bed exposes no WiLinke service,
it builds the same Gen2 controller with the same timing as `leggett_gen2`, so
the two send identical bytes; with variant
`okin` it is an alias of `leggett_okin` (see the
[Okin N-frame aliases](okin-nframe.md#aliases)). The
[protocol inventory](../design/protocol-inventory.md) proves both by capture.

## Gen2 Variant (ASCII Commands)

**Service UUID:** `45e25100-3171-4cfc-ae89-1d83cf8d8071`
**Format:** ASCII text (UTF-8)

### Preset Commands

| Command | Text |
|---------|------|
| Flat | `MEM 0` |
| Unwind (Memory 1) | `MEM 1` |
| Sleep (Memory 2) | `MEM 2` |
| Wake Up (Memory 3) | `MEM 3` |
| Relax (Memory 4) | `MEM 4` |
| Anti-Snore | `SNR` |
| Stop | `STOP` |

### Save Commands

| Command | Text |
|---------|------|
| Save Unwind | `SMEM 1` |
| Save Sleep | `SMEM 2` |
| Save Wake Up | `SMEM 3` |
| Save Relax | `SMEM 4` |

### Motor Commands

Format: `M {down}:{up}:{stop}` — three colon-separated fields, each a list of
motor numbers. For a single press the motor number goes in **exactly one**
field and the others are empty; there is no trailing stop list. The app
re-sends the move command every 200 ms while a button is held and sends a
per-actuator stop on release.

Motor numbers: 0=head, 1=feet, 2=pillow, 3=lumbar

| Command | Text | Description |
|---------|------|-------------|
| Head Up | `M :0:` | Raise head |
| Head Down | `M 0::` | Lower head |
| Head Stop | `M ::0` | Stop head |
| Feet Up | `M :1:` | Raise feet |
| Feet Down | `M 1::` | Lower feet |
| Pillow Up | `M :2:` | Raise pillow |
| Pillow Down | `M 2::` | Lower pillow |
| Lumbar Up | `M :3:` | Raise lumbar |
| Lumbar Down | `M 3::` | Lower lumbar |
| Stop All | `STOP` | Stop all motors |

Combined moves put codes in two fields, e.g. head down + feet up = `M 0:1:`.

### Massage Commands

Gen2 massage intensity is relative (`VII`); an absolute set (`MVI`) also exists
and is used to switch everything off. Channel: 0=head, 1=foot, `0123`=all.
Mode codes: 0=wave, 1=pulse, 2=always-on.

| Command | Text |
|---------|------|
| Increase intensity | `VII :{channel}` |
| Decrease intensity | `VII {channel}::` |
| Set intensity (absolute) | `MVI {channel}:{level}` (level 0-3; 0=off) |
| Set massage mode | `MMODE 0:{mode}` |
| Toggle wave | `WVE TOGGLE` |

### Light Commands

Under-bed light (LightID `0`). The toggle is the only on/off primitive.

| Command | Text | Description |
|---------|------|-------------|
| Toggle | `UBL TOGGLE` | Toggle the under-bed light on/off |
| Set colour | `RGBSET 0:RRGGBBAA` | Set colour (8 hex: red, green, blue, alpha/brightness) |
| Set brightness | `RGBBRT 0:AA` | Set brightness (2 hex) |
| Default colour | `RGD 0[,<decimal>]` | Get/set the stored default colour |

Live light state (on/off + colour) is reported in the `45e25103` STATE frame via a
mode byte (`OperatingMode` `CONSTANT_COLOR`/`OFF`) with RGBA bytes.

### Per-model capabilities

Gen2 beds **do not report their feature set over BLE**. The app ships a bundled
profile per model (`assets/ID_<productId>.json`) and selects it by a `productId`
it derives from the advertisement manufacturer data (hex each payload byte after
the `XP`/`CP` prefix, reverse, take the first four, parse base-16 — e.g.
`58 50 05 …` → `5`). The profile declares the under-bed light style
(**none / toggle / single-colour / RGB**), which actuators are present (**pillow
and lumbar vary by model**), massage, and memory slot count (**typically 3**).
Unknown product ids fall back to a fully-featured profile.

## Okin Variant (Binary)

**Service UUID:** `62741523-52f9-8864-b1ab-3b3a8d65950b`
**Format:** 6 bytes `[0x04, 0x02, ...int_bytes]` (big-endian)
**Note:** Requires BLE pairing
**Write characteristic:** `62741525-52f9-8864-b1ab-3b3a8d65950b`

The motor and massage keycodes overlap with Keeson's, but the preset ladder,
repeat behaviour and release semantics do **not** - see
[Leggett & Platt Okin](okin-nframe.md#leggett-okin-family) for the protocol as it was actually
recovered from the vendor apps, including the memory ladder, the two-stage
memory store, and the second (checksummed) frame format used by older control
boxes.

### Motor Commands

| Command | 32-bit Value | Description |
|---------|-------------|-------------|
| Head Up | `0x00000001` | Raise head |
| Head Down | `0x00000002` | Lower head |
| Feet Up | `0x00000004` | Raise feet |
| Feet Down | `0x00000008` | Lower feet |
| Tilt Up | `0x00000010` | Raise tilt (pillow) |
| Tilt Down | `0x00000020` | Lower tilt (pillow) |
| Lumbar Up | `0x00000040` | Raise lumbar |
| Lumbar Down | `0x00000080` | Lower lumbar |
| Stop | `0x00000000` | Stop all motors |

Multiple motors can be moved simultaneously by OR-ing their command values together.

### Massage Commands

| Command | 32-bit Value | Description |
|---------|-------------|-------------|
| Head Massage Up | `0x00000800` | Increase head massage intensity |
| Head Massage Down | `0x00800000` | Decrease head massage intensity |
| Foot Massage Up | `0x00000400` | Increase foot massage intensity |
| Foot Massage Down | `0x01000000` | Decrease foot massage intensity |
| Massage Step | `0x00000100` | Cycle through massage modes |
| Massage Wave Step | `0x10000000` | Cycle through massage wave patterns |

## MlRM Variant (WiLinke)

This variant uses Richmat WiLinke BLE hardware with Leggett & Platt codes: discrete
massage up/down commands instead of the Richmat step commands, and held presets.
Its frames, timing and controls are in the [L&P MlRM profile](richmat.md#lp-mlrm)
of the Richmat codec guide.
