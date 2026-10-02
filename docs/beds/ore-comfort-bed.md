# MaxCoil Una / Dynasty Bases app profile

**Status:** 🧪 artifact-verified, hardware unverified. Clean-room analysis of
MaxCoil Una 1.1.0 (5) (`com.ore.maxcoil`) and Dynasty Bases 1.0.2 (3)
(`com.ore.Dynasty`) is complete and accepted (formal cluster-013). See the
[app dispositions](../apk-analysis/dispositions/row056-ore-maxcoil-dynasty.md).

Both apps ship the same `com.ore.okincomfortbed` code base. Their Bluetooth
behavior is identical; only the launcher, Back navigation and artwork differ.

## Setup

Choose **Keeson**, then the protocol variant for your app:

| App | Protocol variant |
|-----|------------------|
| MaxCoil Una | `maxcoil_una` |
| Dynasty Bases | `dynasty_bases` |

Set the **motor count** to the screen you pick in the app:

| App screen | Motor count | Covers |
|------------|-------------|--------|
| 2M | 2 | Back, Feet, Back and legs (one combined key) |
| 3M | 3 | Back, Feet, Head |
| 4M | 4 | Back, Feet, Waist, Lumbar |

The apps scan for every Bluetooth device and let you choose one by address.
They have no name, service or manufacturer rule, so **Auto never selects this
profile**. The older `sino` variant (Dynasty, INNOVA, BetterLiving) is
unchanged; it sends different preset and massage values. For a two-address
pair, split the pair before changing the profile.

## Transport

| Role | UUID | Behavior |
|------|------|----------|
| Write | `0000ffe9-0000-1000-8000-00805f9b34fb` | Last match across all services; the service UUID is ignored |
| Notify | `0000ffe4-0000-1000-8000-00805f9b34fb` | Must exist; the app enables it locally only and writes no CCCD |

Controls stay unavailable unless both characteristics exist. The app never
sets a write type, so Android's default applies: write without response when
the characteristic offers it, otherwise with response. There is no PIN,
pairing, handshake, MTU request or initialization packet.

## Frame

```text
E5 FE 16 | w3 w2 w1 w0 | checksum
```

The 32-bit action word is big-endian. The checksum is
`(~sum(first seven bytes)) & 0xFF`, so all eight bytes sum to `0xFF`.

```python
def frame(word):
    body = bytes([0xE5, 0xFE, 0x16]) + (word & 0xFFFFFFFF).to_bytes(4, "big")
    return body + bytes([(~sum(body)) & 0xFF])
```

## Commands

| Action | Word | Frame |
|--------|------|-------|
| Back up / down | `00000001` / `00000002` | `e5 fe 16 00 00 00 01 05` / `… 02 04` |
| Feet up / down | `00000004` / `00000008` | `e5 fe 16 00 00 00 04 02` / `… 08 fe` |
| 2M Back and legs, 3M Head, 4M Waist up / down | `00000010` / `00000020` | `e5 fe 16 00 00 00 10 f6` / `… 20 e6` |
| 4M Lumbar up / down | `00000040` / `00000080` | `e5 fe 16 00 00 00 40 c6` / `… 80 86` |
| Release / STOP | `00000000` | `e5 fe 16 00 00 00 00 06` |
| Zero G (ZG) recall / save | `01000001` / `20000001` | `e5 fe 16 01 00 00 01 04` / `e5 fe 16 20 00 00 01 e5` |
| Flat recall / save | `01000002` / `20000002` | `e5 fe 16 01 00 00 02 03` / `e5 fe 16 20 00 00 02 e4` |
| Memory A recall / save | `01000008` / `20000008` | `e5 fe 16 01 00 00 08 fd` / `e5 fe 16 20 00 00 08 de` |
| Memory B recall / save | `01000009` / `20000009` | `e5 fe 16 01 00 00 09 fc` / `e5 fe 16 20 00 00 09 dd` |
| Light on / off | `31000001` / `31000000` | `e5 fe 16 31 00 00 01 d4` / `… 00 d5` |
| Head massage level 0-3 | `10000010` + level | `e5 fe 16 10 00 00 10 e6` … `13 e3` |
| Foot massage level 0-3 | `11000010` + level | `e5 fe 16 11 00 00 10 e5` … `13 e2` |
| Wave level 0-3 | `10000020` + level | `e5 fe 16 10 00 00 20 d6` … `23 d3` |
| Massage timer 10 / 20 / 30 min | `10000030` / `31` / `32` | `e5 fe 16 10 00 00 30 c6` / `31 c5` / `32 c4` |

Memory A and B are position slots, not bed sides. Flat and Zero G can be saved
like the memory slots.

## Timing and release

- **Held movement:** the key is written at 0 ms and again 100 ms after each
  write while held. On release the app sleeps 100 ms and writes the zero word.
  The integration uses the configured repeat count at the app's fixed 100 ms
  interval, then sends the zero word with a fresh cancel event so a STOP can
  never suppress it. The app has one global key, so any STOP ends every motion.
- **Every other action** sleeps 100 ms and is written once.
- **Second tap:** tapping the running preset again sends the zero word. The
  integration exposes the same frame as the **Stop** button; preset buttons
  always recall.
- **Long press** on a preset saves it. The integration uses Save buttons
  (**Save Memory A/B**, **Save Flat**, **Save Zero G**).

## Massage

| Entity | Behavior |
|--------|----------|
| Head, Foot and Wave massage numbers (0-3) | A slider change sends that zone's level word. Levels persist across restarts like the app's preferences; a fresh install starts at level 1. |
| **Start massage** button | Sends the current wave, head and foot levels, in that order. |
| **Massage off** button | Sends head level 0, then foot level 0. The sliders keep their levels and the timer indicator resets. No wave-off frame exists. |
| **Massage timer** select | Sends the 10, 20 or 30 minute word. The app's timer button cycles through the same three words; it has no timer-off word. |

## Light

The app toggles a local flag and sends explicit on and off words, so the
integration exposes an under-bed light switch with assumed state.

## Feedback

None. The app accepts any nine-byte FFE4 value, extracts bits from byte 7 and
discards them. No position, light, massage or acknowledgement state exists.

## Not implemented

- The app's phone settings (haptic feedback, actuator 1/2, installation) do not
  change any packet.
- Dead legacy screens (sofa, seating, fridge, music, lamp, others and the 500
  ms "others" repeat) are unreachable in both apps.
- Bluetooth Classic, Wi-Fi, cloud and OTA paths are absent from both apps.

## Deferred validation

Hardware is unverified. Real users should confirm after a beta or release:
the physical axis for each layout (especially 2M's combined key and 4M's
waist), hold and release behavior, preset save/recall, massage levels and
timer durations, and the actual write type.
