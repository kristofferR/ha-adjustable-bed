# Okin CST (CSTProtocol)

**Status:** ❓ Needs testing (static analysis complete; hardware validation pending)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Mattress Firm 900-O / MFirm 900-O and Rize MF900
- Rize Sanctuary, Resident, Aviada, Bob, and Contempo
- Rize II Carefree and Rize II Clarity
- Support
- Nectar Motion using the Nectar Move app profile
- Bluetooth names vary; some report as `OKIN-XXXXXX`

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Rize Sanctuary](https://play.google.com/store/apps/details?id=com.okin.bedding.rizeSanctuary) 1.0.1 (2) | `com.okin.bedding.rizeSanctuary` |
| ✅ | [Rize Resident](https://play.google.com/store/apps/details?id=com.okin.bedding.rizeResident) 1.0.1 (2) | `com.okin.bedding.rizeResident` |
| ✅ | [Rize Aviada](https://play.google.com/store/apps/details?id=com.okin.bedding.rizeaviada) 1.0.1 (2) | `com.okin.bedding.rizeaviada` |
| ✅ | [Rize Bob](https://play.google.com/store/apps/details?id=com.okin.bedding.rizebob) 1.0.1 (2) | `com.okin.bedding.rizebob` |
| ✅ | [Rize Contempo](https://play.google.com/store/apps/details?id=com.okin.bedding.rizecontempo) 1.0.2 (3) | `com.okin.bedding.rizecontempo` |
| ✅ | [Rize II Carefree](https://play.google.com/store/apps/details?id=com.okin.bedding.rizeiicarefree) 1.0.1 (2) | `com.okin.bedding.rizeiicarefree` |
| ✅ | [Rize II Clarity](https://play.google.com/store/apps/details?id=com.okin.bedding.rizeiiclarity) 1.0.1 (2) | `com.okin.bedding.rizeiiclarity` |
| ✅ | [Mattress Firm 900 - O / MFirm 900-O](https://play.google.com/store/apps/details?id=com.okin.bedding.rizemf900) 1.1.2 (4) | `com.okin.bedding.rizemf900` |
| ✅ | [Support](https://play.google.com/store/apps/details?id=com.okin.bedding.support) 1.0.4 (5) | `com.okin.bedding.support` |
| ✅ | [Nectar Motion](https://play.google.com/store/apps/details?id=com.okin.bedding.nectarmotion) 1.0.1 (2), Nectar Move profile | `com.okin.bedding.nectarmotion` |

**Android:** all ten analyzed packages are Android apps. The nine cluster 011
artifact hashes are listed under [Analysis provenance](#analysis-provenance).

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head and foot; lumbar on Aviada, Contempo, MF900 and Support |
| Position Feedback | ❌ (no decoded motor positions) |
| Memory Presets | ✅ (one to four programmable preset memories, per profile) |
| Massage | ⚠️ Per profile: global or head/foot intensity, three wave modes, off; increase only on Nectar Move; none on Carefree |
| Under-bed Lights | ✅ Every profile except Resident (toggle only on Nectar Move) |
| Flat / Zero-G / Anti-Snore | ✅ |
| Lounge / Incline (TV) / Reading | ⚠️ Per profile |
| BLE Pairing | ⚠️ Required for most profiles; Nectar Move does not proactively request a bond |

## Protocol Details

**Service UUID:** `62741523-52f9-8864-b1ab-3b3a8d65950b` (standard OKIN)
**Write Characteristic:** `62741525-...`
**Notify Characteristic:** `62741625-...`
**Format:** 14-byte command with two separate 32-bit fields

### Packet Format

```text
[0x0C, 0x02, primary[4], secondary[4], 0x00, 0x00, 0x00, 0x00]
```

- **Primary field** (bytes 2-5): Head, foot, and lumbar motor control plus
  presets, memory-save chords, light toggle, massage stop, and intensity
- **Secondary field** (bytes 6-9): Discrete light on/off and massage wave modes
- Each field is a big-endian 32-bit value; unused fields are zero.

Field placement is app-specific. Do not assume all presets, lights, or massage
commands use the secondary field.

### Write Mode

The accepted Android app does not set a numeric write type; it leaves the write
characteristic at its runtime default. Home Assistant retains its existing
write-with-response integration policy. The accepted artifacts do not establish
the receiver's effective write mode or required characteristic properties, so
the effective hardware behavior is deferred for real-user validation.

## Pairing

The captured MFirm receiver gates its reads and notification characteristics
(including Device Information) behind an OS-level Bluetooth **bond**. The OS
negotiates the bond automatically when a client accesses one of those encrypted
characteristics.

- Pairing is "Just Works": **no PIN** and **no dedicated Bluetooth pairing button**.
- Before bonding, those characteristics return GATT `error=5` "Insufficient
  authentication". The command characteristic (`62741525-...`) itself was
  readable unbonded, but the integration still establishes the bond so the
  connection matches the official app's full GATT session.

**To enter pairing mode, power-cycle the control box:** unplug it for ~30 seconds,
then plug it back in. The status light blinks blue, then turns green after ~20 s;
that window is when the base accepts a new bond. Some models instead use the
under-bed lamp/light button (hold until it blinks blue). The physical "Pair"/"Learn"
button found on some OKIN control boxes only syncs the **RF remote**, not Bluetooth.

The integration requests `pair=True` automatically and verifies the bond after
connecting. If the link connected but did not bond, it clears its cached bond
state, re-pairs on the next attempt, and surfaces a **"Bluetooth pairing required"**
repair with a guided **Fix** button. ESPHome Bluetooth proxies can pair only on
ESPHome ≥ 2024.3.0; a local adapter near the bed is the most reliable for the
first bond.

Nectar Move's accepted app has no app-issued bond request or authentication
gate, so its profile skips proactive pairing. Home Assistant still routes an
actual GATT authentication failure through the existing bond-recovery repair.
That repair, with its **Pair Now** action, stays until a later connection
succeeds. This does not change pairing policy for other CST profiles.

## Detection / Setup

| Signal | Value |
|--------|-------|
| Service UUID | `62741523-52f9-8864-b1ab-3b3a8d65950b` (standard OKIN) |
| Name patterns | Varies (shared UUID requires disambiguation; some report as `OKIN-XXXXXX`) |
| Connected GATT hint | CSS `90311623-...` plus Nordic DFU `00001530-...` is ambiguous and requires another identity signal |
| BLE Pairing | Required for most profiles; Nectar Move does not proactively request a bond |

- Manual selection may be needed since the service UUID is shared with other Okin protocols.
- The shared UUID and the official apps' common `OKIN-*` name filter do not
  distinguish the nine product layouts. Select the matching **Protocol variant**
  in the integration options. `Auto` preserves the MF900 profile for existing
  entries.
- Do not choose CST solely because diagnostics show both the CSS and Nordic DFU
  services. That connected GATT signature is also exposed by RF ECO BT stair
  actuators and by OKIMAT drives used with FurniMove (#555). Device Information
  model `MEGAMAT MBZ` identifies RF ECO BT. Choose CST only when the known base
  or app identity corroborates the CST protocol. The integration never selects
  CST automatically from GATT; a CST entry whose drive reports an `OKIMAT` model
  is offered a [repair](furnimove.md#repairing-existing-configurations).
- Do not select CST for `LP BED...` receivers. LP Control 2.9.0 identifies those
  as its Okin profile and sends 6-byte commands, even when the receiver also
  exposes CSS and Nordic DFU services. See [Leggett & Platt](leggett-platt.md).
- **Nectar Move** is opt-in; see [Nectar Move profile](#nectar-move-profile).

## Product Profiles

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
| Nectar Move | Head, feet (app axes; physical semantics unverified) | Anti, Zero Gravity, Reading | 2: Zero Gravity, Reading | Increase only | Toggle only |

The zoned decrease frames are not interchangeable. Bob routes both zone-down
commands through both CST fields, Support routes foot-down through only the
secondary field, and Sanctuary/Resident use only the primary field. Selecting
the product profile is therefore required for safe zoned massage controls.

### Nectar Move profile

Choose **Nectar Move** in setup or the Protocol variant options. No shared OKIN
name, UUID, or Device Information result selects it. The profile is opt-in and
keeps the other CST application profiles unchanged.

- **Axes:** two, labelled Head and Feet. Those are app-control labels; the
  receiver's physical actuator semantics have not been verified. Position
  feedback is not supported.
- **Presets:** Flat, Anti, Zero Gravity, and Reading. The two saveable slots are
  Zero Gravity and Reading. Reading has its own stable entity name and does not
  rename Lounge in other profiles.
- **Light:** under-bed lighting is an assumed-state toggle only.
- **Massage:** one combined intensity-increase button. It has no decrease, off,
  start/toggle, head/foot, wave, timer, level, or state action.
- **Save response:** see [Notifications](#notifications).
- **Write mode:** the Android app leaves the write characteristic's write type at
  its runtime default; the integration keeps its write-with-response policy
  (see [Write Mode](#write-mode)).

Hardware checks remain deferred for real users after a beta or release:
effective write behavior, physical axis and preset meaning, notification byte
meaning, and receiver repeat/STOP semantics. They are not implementation work.

## Commands

### Motor Control (primary field)

| Command | Value | Description |
|---------|-------|-------------|
| Stop | `0x00000000` | All-zero frame (also the release) |
| Head Up | `0x00000001` | Raise head |
| Head Down | `0x00000002` | Lower head |
| Foot Up | `0x00000004` | Raise foot |
| Foot Down | `0x00000008` | Lower foot |
| Lumbar Up | `0x00000010` | Raise lumbar (lumbar profiles only) |
| Lumbar Down | `0x00000020` | Lower lumbar (lumbar profiles only) |

Multiple motor bits can be OR'd together for simultaneous movement.

### Presets and Memory (primary field)

| Command | Value | Description |
|---------|-------|-------------|
| Flat | `0x08000000` | Flat |
| Zero-G | `0x00001000` | Zero-G recall |
| Lounge | `0x00002000` | Lounge recall (Reading on Nectar Move) |
| Incline / TV | `0x00004000` | Incline recall |
| Anti-snore | `0x00008000` | Anti-snore |
| Memory `M` | `0x00010000` | Resident's fourth memory recall |
| Save Zero-G | `0x08001000` | Flat + Zero-G chord |
| Save Lounge | `0x08002000` | Flat + Lounge chord (Save Reading on Nectar Move) |
| Save Incline | `0x08004000` | Flat + Incline chord |
| Save `M` | `0x08010000` | Flat + `M` chord (Resident) |

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

### Lights

| Command | Field | Value | Description |
|---------|-------|-------|-------------|
| Light Toggle | Primary | `0x00020000` | Toggle under-bed light |
| Light On | Secondary | `0x00000040` | Discrete on |
| Light Off | Secondary | `0x00000080` | Discrete off |

### Massage

| Command | Field | Value | Description |
|---------|-------|-------|-------------|
| Massage Off | Primary | `0x02000000` | Stop massage |
| Massage All + | Primary | `0x00000C00` | Global intensity up |
| Massage All - | Primary | `0x01800000` | Global intensity down |
| Massage Wave 1 | Secondary | `0x00080000` | Wave mode 1 |
| Massage Wave 2 | Secondary | `0x00100000` | Wave mode 2 |
| Massage Wave 3 | Secondary | `0x00200000` | Wave mode 3 |

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

## Notifications

- The app subscribes to the notify characteristic (`62741625-...`) but only
  watches byte 10 for a generic change; it does not decode motor positions.
- **Nectar Move:** notification byte 10 is tracked only while a memory save is
  pending. A changed signed byte emits the `Memory save response observed`
  diagnostic. That signal is not proof that a physical memory was stored, and
  no position or device state is inferred from the byte.

## Command Timing

### Cluster 011 profiles

- The Android app sends the active command immediately and every 100 ms while a
  button is held.
- On release it sends the all-zero STOP frame twice, at +100 ms and +200 ms.
- For one-shot voice actions such as presets, lights, and massage, the app
  streams for 500 ms before the same delayed STOP cleanup. Home Assistant uses
  that fixed one-shot cadence for button entities and keeps motor movement
  duration configurable.

### Nectar Move

- Nectar Move uses the same 100 ms held-command refresh and delayed STOP pair,
  but its app also repeats every other reachable action only while held.
- Home Assistant movement commands are finite, so each one refreshes the axis
  at the app's 100 ms interval for the configured **Motor pulse count**
  (default 10, about one second), then sends the STOP pair.
- The card's hold loop re-issues movements while a control stays pressed, and a
  STOP or replacement command ends the refresh early with the same release.
- Stateless preset, save, light, and massage buttons send one selected frame,
  then STOP at +100 ms and +200 ms as a bounded Home Assistant tap mapping.

## Notes

### Relationship to Other Okin Protocols

Many command values match Okimat/Okin UUID values. CST differs in packet framing
and in which 32-bit field carries each remote action.

> [!WARNING]
> Earlier versions of this page listed Head Tilt `0x00000010`/`0x00000020`,
> Lumbar `0x00000040`/`0x00000080`, a Massage Toggle `0x04000000`, a position
> notify characteristic `62741524-...` and Okimat-style position feedback. The
> accepted cluster 011 reports and the current controller use Lumbar
> `0x00000010`/`0x00000020`, have no tilt axis or `0x04000000` command, and
> decode no positions.

### Analysis provenance

**Ref:** Nine frozen APK Protocol Audit cluster 011 clean-room reports and
accepted cluster reconciliation. The protocol was first reverse-engineered from
`CSTProtocol.java` in the Rize MF900 and Nectar Motion APKs.

The command table, product profiles, and timing come from nine COMPLETE, frozen
APK Protocol Audit cluster 011 reports. Their accepted artifact-set SHA-256
identities are:

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
blocker. The Nectar Move profile comes from the row042 accepted audit and
convergence proof for `com.okin.bedding.nectarmotion` 1.0.1 (2). Physical
behavior remains unverified on target hardware.
