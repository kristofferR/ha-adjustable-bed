# Okin CST (CSTProtocol)

**Status:** Static analysis complete; hardware validation pending
**Ref:** Nine frozen Phase 4 cluster 011 clean-room reports and accepted
cluster reconciliation

## Known Brands

- Mattress Firm 900-O / MFirm 900-O and Rize MF900
- Rize Sanctuary, Resident, Aviada, Bob, and Contempo
- Rize II Carefree and Rize II Clarity
- Support
- Nectar Motion / some `OKIN-*` Nectar bases

## Detection

| Signal | Value |
|--------|-------|
| Service UUID | `62741523-52f9-8864-b1ab-3b3a8d65950b` (standard OKIN) |
| Name patterns | Varies (shared UUID requires disambiguation; some report as `OKIN-XXXXXX`) |
| Connected GATT hint | CSS `90311623-...` plus Nordic DFU `00001530-...` is ambiguous and requires another identity signal |
| BLE Pairing | Required |

Manual selection may be needed since the service UUID is shared with other Okin protocols.
The shared UUID and the official apps' common `OKIN-*` name filter do not
distinguish the nine product layouts. Select the matching **Protocol variant**
in the integration options. `Auto` preserves the MF900 profile for existing
entries.
Do not choose CST solely because diagnostics show both the CSS and Nordic DFU
services. That connected GATT signature is also exposed by RF ECO BT stair
actuators. Device Information model `MEGAMAT MBZ` identifies RF ECO BT. Choose
CST only when the known base or app identity corroborates the CST protocol.

Do not select CST for `LP BED...` receivers. LP Control 2.9.0 identifies those
as its Okin profile and sends 6-byte commands, even when the receiver also
exposes CSS and Nordic DFU services. See [Leggett & Platt](leggett-platt.md).

## Pairing

The captured MFirm receiver gates its reads and notification characteristics behind
an OS-level Bluetooth **bond**. Pairing is "Just Works": **no PIN** and **no
dedicated Bluetooth pairing button**. Before bonding, those characteristics return
GATT `error=5` "Insufficient authentication". The command characteristic
(`62741525-...`) itself was readable unbonded, but the integration still establishes
the bond so the connection matches the official app's full GATT session.

**To enter pairing mode, power-cycle the control box:** unplug it for ~30 seconds,
then plug it back in. The status light blinks blue, then turns green after ~20 s —
that window is when the base accepts a new bond. Some models instead use the
under-bed lamp/light button (hold until it blinks blue). The physical "Pair"/"Learn"
button found on some OKIN control boxes only syncs the **RF remote**, not Bluetooth.

The integration requests `pair=True` automatically and verifies the bond after
connecting; if the link connected but did not bond it clears its cached bond state,
re-pairs on the next attempt, and surfaces a **"Bluetooth pairing required"** repair
with a guided **Fix** button. ESPHome Bluetooth proxies can pair only on ESPHome
≥ 2024.3.0; a local adapter near the bed is the most reliable for the first bond.

## Protocol

Uses a 14-byte command format with two separate 32-bit fields:

```text
[0x0C, 0x02, primary[4], secondary[4], 0x00, 0x00, 0x00, 0x00]
```

- **Primary field** (bytes 2-5): Head, foot, and lumbar motor control plus
  presets, memory-save chords, light toggle, massage stop, and intensity
- **Secondary field** (bytes 6-9): Discrete light on/off and massage wave modes
- **Write characteristic:** `62741525-...`; the app leaves the characteristic's
  runtime/default write type unchanged, while the captured hardware advertises
  the `write` property
- **Notify characteristic:** `62741625-...`; the app only watches byte 10 for a
  generic change and does not decode motor positions

Field placement is app-specific. Do not assume all presets, lights, or massage
commands use the secondary field.

### Motor Commands (primary field)

| Action | Value |
|--------|-------|
| Stop | `0x00000000` |
| Head Up | `0x00000001` |
| Head Down | `0x00000002` |
| Foot Up | `0x00000004` |
| Foot Down | `0x00000008` |
| Lumbar Up | `0x00000010` |
| Lumbar Down | `0x00000020` |

Multiple motor bits can be OR'd together for simultaneous movement.

### Remote Actions (primary field)

| Action | Value |
|--------|-------|
| Flat | `0x08000000` |
| Zero-G | `0x00001000` |
| Lounge | `0x00002000` |
| Incline / TV | `0x00004000` |
| Anti-snore | `0x00008000` |
| Save Zero-G | `0x08001000` |
| Save Lounge | `0x08002000` |
| Save Incline | `0x08004000` |
| Light Toggle | `0x00020000` |
| Massage Off | `0x02000000` |
| Massage All + | `0x00000C00` |
| Massage All - | `0x01800000` |

### Remote Actions (secondary field)

| Action | Value |
|--------|-------|
| Light On | `0x00000040` |
| Light Off | `0x00000080` |
| Massage Wave 1 | `0x00080000` |
| Massage Wave 2 | `0x00100000` |
| Massage Wave 3 | `0x00200000` |

### Product-specific massage fields

| Product | Action | Primary | Secondary |
|---|---|---:|---:|
| Sanctuary, Resident | Head + | `0x00000800` | `0x00000000` |
| Sanctuary, Resident | Head - | `0x00800000` | `0x00000000` |
| Sanctuary, Resident | Foot + | `0x00000400` | `0x00000000` |
| Sanctuary, Resident | Foot - | `0x01000000` | `0x00000000` |
| Bob | Head - | `0x00800000` | `0x00800000` |
| Bob | Foot - | `0x01000000` | `0x01000000` |
| Support | Head - | `0x00800000` | `0x00800000` |
| Support | Foot - | `0x00000000` | `0x01000000` |
| Sanctuary, Bob | Full-body massage | `0x00000000` | `0x00000100` |
| Resident | Timer step | `0x00000200` | `0x00000000` |

Bob and Support use the same primary-only zone-increase fields as Sanctuary and
Resident. Every product with massage uses the shared wave and massage-off
fields above.

### Timing

The Android app sends the active command immediately and every 100 ms while a
button is held. On release it sends the all-zero STOP frame twice, at +100 ms and
+200 ms. For one-shot voice actions such as presets, lights, and massage, the app
streams for 500 ms before the same delayed STOP cleanup. Home Assistant uses that
fixed one-shot cadence for button entities and keeps motor movement duration
configurable.

### Memory Slots

The MFirm app treats Zero-G, Incline, and Lounge as user-programmable preset
memories. Home Assistant exposes those as numbered memory slots:

| HA Memory Slot | MFirm App Memory |
|----------------|------------------|
| Memory 1 | Zero-G |
| Memory 2 | Incline |
| Memory 3 | Lounge |

Other product variants expose only the accepted app's reachable slots. Resident
adds a fourth `M` slot; Sanctuary and Bob expose Zero-G and Lounge; Carefree
exposes only Zero-G. The other profiles use the three MF900 mappings above.

## Product profiles

| Variant | Motors | Presets beyond Flat | Programmable memories | Massage | Light |
|---|---|---|---:|---|---|
| Sanctuary | Head, foot | Anti-snore, lounge, Zero-G | 2 | Head/foot intensity, 3 waves, full-body start, off | Toggle and discrete on/off |
| Resident | Head, foot | Anti-snore, lounge, Zero-G, incline | 4, including `M` | Head/foot intensity, 3 waves, timer step, off | None in the shipped UI |
| Aviada | Head, foot, lumbar | Anti-snore, lounge, Zero-G, incline | 3 | Global intensity, 3 waves, off | Toggle and discrete on/off |
| Bob | Head, foot | Anti-snore, lounge, Zero-G | 2 | Head/foot intensity, 3 waves, full-body start, off | Toggle and discrete on/off |
| Contempo | Head, foot, lumbar | Anti-snore, lounge, Zero-G, incline | 3 | Global intensity, 3 waves, off | Toggle and discrete on/off |
| Carefree | Head, foot | Anti-snore, Zero-G | 1 | None | Toggle and discrete on/off |
| Clarity II | Head, foot | Anti-snore, lounge, Zero-G, incline | 3 | Global intensity, 3 waves, off | Toggle and discrete on/off |
| MF900 | Head, foot, lumbar | Anti-snore, lounge, Zero-G, incline | 3 | Global intensity, 3 waves, off | Toggle and discrete on/off |
| Support | Head, foot, lumbar | Anti-snore, lounge, Zero-G, incline | 3 | Head/foot intensity, 3 waves, off | Toggle and discrete on/off |

The zoned decrease frames are not interchangeable. Bob routes both zone-down
commands through both CST fields, Support routes foot-down through only the
secondary field, and Sanctuary/Resident use only the primary field. Selecting
the product profile is therefore required for safe zoned massage controls.

## Shared features

- Two or three motors depending on product profile
- Product-specific presets and one to four programmable memories
- Product-specific global or head/foot massage controls and three wave modes
- Under-bed light controls on every profile except Resident
- No decoded motor-position feedback

## Relationship to Other Okin Protocols

Many command values match Okimat/Okin UUID values. CST differs in packet framing
and in which 32-bit field carries each remote action.

## App

- **Android:** the nine product packages listed in the source table below
- **Android:** `com.okin.bedding.nectarmotion` (historically associated with this
  profile; not part of this clean-room run)

## Source

The command table, product profiles, and timing come from nine COMPLETE, frozen
Phase 4 cluster 011 reports. Their accepted artifact-set SHA-256 identities are:

| Package | Version | Artifact-set SHA-256 |
|---|---|---|
| `com.okin.bedding.rizeSanctuary` | 1.0.1 (2) | `90b494007dd120b4da9498c8d259411bb2a8f2e643a22433792486d896f535d0` |
| `com.okin.bedding.rizeResident` | 1.0.1 (2) | `26a33ef79aa50f0b899d934c01aad8641b97da58bd9b78134122ac56d33eeaa9` |
| `com.okin.bedding.rizeaviada` | 1.0.1 (2) | `fc1cbef8715de115455a4931264941bf44ad10adc819811496a82221e85b6241` |
| `com.okin.bedding.rizebob` | 1.0.1 (2) | `237ffd39af4e8179a1c83f07cfd53364d66d127f3ccdd7ea1394ea3c6bfca437` |
| `com.okin.bedding.rizecontempo` | 1.0.2 (3) | `9c8ef59a2addb92c9b81c330d629d495c606e6b0d06f67e31c19e7cd8e112ea9` |
| `com.okin.bedding.rizeiicarefree` | 1.0.1 (2) | `204617a5b4b60247478125dd6cfdfaadf769581fe77b874b3f9fc47ff271234f` |
| `com.okin.bedding.rizeiiclarity` | 1.0.1 (2) | `998bcd5962de74c85d3ebf36778007f6cbe11b4c1992477a454fca1a3ab80c1a` |
| `com.okin.bedding.rizemf900` | 1.1.2 (4) | `a4f5ae67b2b9b870e6413d08597364041ac6947c7ba5445eb1979498895ff46f` |
| `com.okin.bedding.support` | 1.0.4 (5) | `c2e01cdc9727f3608bcbd58076fecfa9c84176b343750079284b246e6aba2e00` |

The cluster reconciliation closed all 99 package/domain comparisons with no
blocker. Physical behavior remains unverified on target hardware.
