# Okin CST (CSTProtocol)

**Status:** Needs testing
**Ref:** Reverse-engineered from `com.okin.bedding.rizemf900` APK

## Known Brands

- Mattress Firm 900-O / MFirm 900-O
- Rize MF900
- Nectar Motion / some `OKIN-*` Nectar bases
- Leggett & Platt Prodigy Comfort Elite / `LP BED CONTROL` when diagnostics
  show the CST connected GATT signature

## Detection

| Signal | Value |
|--------|-------|
| Service UUID | `62741523-52f9-8864-b1ab-3b3a8d65950b` (standard OKIN) |
| Name patterns | Varies (shared UUID requires disambiguation; some report as `OKIN-XXXXXX`) |
| Connected GATT hint | CSS `90311623-...` plus Nordic DFU `00001530-...` |
| BLE Pairing | Required |

Manual selection may be needed since the service UUID is shared with other Okin protocols.
Choose this profile for Nectar Motion style `OKIN-*` bases when diagnostics show
both the CSS service and Nordic DFU service.
This also applies to Mattress Firm 900-O / MFirm 900-O bases advertising as
`OKIN-XXXXXX` with the same connected GATT signature.

## Pairing

These bases require an OS-level Bluetooth **bond** before commands are accepted.
Pairing is "Just Works" — **no PIN** and **no dedicated Bluetooth pairing button**.
The bond is negotiated automatically by the OS when a client accesses one of the
firmware's encrypted characteristics; on a real device every read/notify and
Device Information characteristic returns GATT `error=5` "Insufficient
authentication" until the link is bonded, while the command write characteristic
(`62741525-…`) is reachable unbonded.

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

- **Primary field** (bytes 2-5): Head, foot, tilt, lumbar motor control plus
  several remote actions, including presets, memory, light toggle, and most
  massage controls
- **Secondary field** (bytes 6-9): Discrete light on/off and massage wave modes
- **Write characteristic:** `62741525-...` (write-with-response)
- **Position notify:** `62741524-...` (same as Okimat)

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
| Head Tilt Up | `0x00000010` |
| Head Tilt Down | `0x00000020` |
| Lumbar Up | `0x00000040` |
| Lumbar Down | `0x00000080` |

Multiple motor bits can be OR'd together for simultaneous movement.

### Remote Actions (primary field)

| Action | Value |
|--------|-------|
| Flat | `0x08000000` |
| Zero-G | `0x00001000` |
| Lounge | `0x00002000` |
| Incline / TV | `0x00004000` |
| Anti-snore | `0x00008000` |
| App Memory button | `0x00010000` |
| Save Zero-G | `0x08001000` |
| Save Lounge | `0x08002000` |
| Save Incline | `0x08004000` |
| Light Toggle | `0x00020000` |
| Massage Toggle | `0x04000000` |
| Massage Off | `0x02000000` |
| Massage All + | `0x00000C00` |
| Massage All - | `0x01800000` |
| Massage Head + | `0x00000800` |
| Massage Head - | `0x00800000` |
| Massage Feet + | `0x00000400` |
| Massage Feet - | `0x01000000` |

### Remote Actions (secondary field)

| Action | Value |
|--------|-------|
| Light On | `0x00000040` |
| Light Off | `0x00000080` |
| Massage Wave 1 | `0x00080000` |
| Massage Wave 2 | `0x00100000` |
| Massage Wave 3 | `0x00200000` |

### Timing

The Android app repeats the active remote button command while the button is
held, then sends STOP twice after release. The integration mirrors that behavior
by sending cleanup STOP packets after movement, preset, light, and massage
commands. Preset recalls are held longer so a Home Assistant button press can
complete the move; light and massage controls use a short simulated press.

### Memory Slots

The MFirm app treats Zero-G, Incline, and Lounge as user-programmable preset
memories. Home Assistant exposes those as numbered memory slots:

| HA Memory Slot | MFirm App Memory |
|----------------|------------------|
| Memory 1 | Zero-G |
| Memory 2 | Incline |
| Memory 3 | Lounge |

## Features

- 4 motors: head, foot, tilt, lumbar
- Flat, Zero-G, anti-snore, lounge, and incline presets
- 3 programmable preset memory slots: Zero-G, Incline, and Lounge
- Discrete light on/off plus toggle
- Massage with head/foot intensity control and wave modes
- Position feedback (same as Okimat)

## Relationship to Other Okin Protocols

Many command values match Okimat/Okin UUID values. CST differs in packet framing
and in which 32-bit field carries each remote action.

## App

- **Android:** Mattress Firm 900 - O / MFirm 900-O (`com.okin.bedding.rizemf900`)
- **Android:** `com.okin.bedding.nectarmotion`

## Source

Protocol reverse-engineered from `CSTProtocol.java` in the Rize MF900 and
Nectar Motion APKs.
