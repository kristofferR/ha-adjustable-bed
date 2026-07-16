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
- South Bay International MMKD
- Sealy Ease
- Some Costco beds

**DewertOkin/ORE brands** also using FFE5 protocol (31 apps):
- Simon Li, Cherish Smart, Minghua, Heal Every Night
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

## Features

| Feature | BaseI4/I5 | JSON/A00A | KSBT | Ergomotion | Okin | Serta | Sino | Purple (Premium) | Purple (Premium Plus) |
|---------|-----------|------------|------|------------|------|-------|------|------------------|-----------------------|
| Motor Control | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Position Feedback | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Memory Presets | ✅ (slots 3-4) | ✅ (remote-dependent 0x2000/0x4000/0x8000/0x10000) | ✅ (slots 1-3: Read/TV/M) | ✅ (4 slots) | ✅ | ✅ | ✅ | ✅ (2 slots) | ✅ (3 slots) |
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
the two-byte status query `[0x00, 0xB0]` at +300, +600 and +900 ms. Member's
Mark uses a 400 ms movement refresh and runs the same query on an independent
400 ms timer. None of these P2 paths writes the six-byte zero-key packet on
release. The integration uses the 100 ms compatibility cadence needed by
KSBT03C beds such as the issue #408 device; explicit per-device pulse settings
remain authoritative.

Some Ergomotion-branded beds also use this variant. A confirmed Rio 6.0 support bundle advertises as `KSBT04...` and works correctly with the standard KSBT 6-byte protocol.
Juna's `LVrestore` and `LVrelax` remotes also use this direct 6-byte framing rather than the JSON/A00A path.

**Ergomotion Sync remotes (from `cn.com.mancini` APK):** the app has three remote layouts — A and C target `KSBT04C` devices, B targets `KSBT03C` (e.g. Rio 5.0). All three share the same preset buttons: Read = `0x2000`, TV = `0x4000`, M = `0x10000`, Zero-G = `0x1000`, Flat = `0x8000000`, light toggle = `0x20000`, and massage steps head `0x800` / foot `0x400` / timer `0x200` (no all-off command). The Anti-Snore button (`0x8000`) appears on layouts B/C only; that describes the remote UIs, not command support — the integration exposes anti-snore on all KSBT variants. Read/TV/M are exposed as memory slots 1-3 on KSBT variants.

**KSBT03C motor layout:** the KSBT03C remote (layout B) drives only three motors — head/back (`0x1`/`0x2`), feet/legs (`0x4`/`0x8`) and lumbar (`0x40`/`0x80`). There are no head-tilt (`0x10`/`0x20`) buttons, so KSBT03C beds have no tilt motor and the integration maps the third configured motor to lumbar. KSBT04C remotes (layouts A/C) additionally have the head-tilt buttons.

That three-motor rule belongs to the direct six-byte KSBT profile. Sleep Harmony
also accepts a `KSBT03C` name but uses its separate explicit profile and exposes
head, foot, tilt/EJ and lumbar controls.

**Status:** the KSBT03C command values and 3-motor layout are APK-derived (Ergomotion Sync 1.0.2) and not yet confirmed on hardware; the Rio 5.0 report in issue #408 confirms the lumbar motor responds to `0x40`/`0x80` and that no tilt motor exists.

**Fallback Service UUIDs:** Some KSBT devices use different service UUIDs. The integration automatically tries these if the primary isn't found:
- `6e400020-b5a3-f393-e0a9-e50e24dcca9e` (characteristic: `6e400021`) - Extended Nordic UART, used by some Ergomotion/SFD beds
- `0000ffe5-0000-1000-8000-00805f9b34fb` (characteristic: `0000ffe9`)
- `0000ffe0-0000-1000-8000-00805f9b34fb` (characteristic: `0000ffe1`)

### KSBT03CR Variant
**Primary Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e` (Nordic UART Service)
**Format:** 7 bytes `[0x05, 0x02, cmd3, cmd2, cmd1, cmd0, 0x00]` (big-endian)

Auto-detected from device name prefix `ksbt03cr`. Uses the same 32-bit command values as standard KSBT; only the framing differs (7-byte packet with `0x05` prefix and trailing `0x00` byte instead of 6-byte packet with `0x04` prefix). Falls back to the same alternative service UUIDs as standard KSBT.

### Sleep Harmony Variant

Sleep Harmony 1.0.1 has two name-selected packet families behind the explicit
`Sleep Harmony (KSBT04C / base-i5)` profile:

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

### Sino Variant (Dynasty, INNOVA, BetterLiving)
**Primary Service UUID:** `0000ffe5-0000-1000-8000-00805f9b34fb`
**Format:** 8 bytes `[0xE5, 0xFE, 0x16, b4, b5, b6, b7, checksum]` (big-endian byte order)

Used by BetterLiving/OKIN-BLE devices. Same packet structure as Base variant but with big-endian command byte ordering. Auto-detected by name pattern `okin-ble`.

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
| BaseI4/BaseI5 | Member's Mark | 400ms fixed-delay scheduler | 3 writes, 400ms apart |
| JSON/A00A | Juna / Linx | Requests every 5ms / 3ms, but drops requests while a write-with-response is pending | Existing safe 10 writes, 100ms apart |
| KSBT direct P2 | Ergomotion 4.0 / Q-Plus / 1500 Tilt Base; Member's Mark | 100ms in the SFD apps, 400ms in Member's Mark | 10 writes, 100ms apart; explicit user overrides are preserved |
| KSBT03CR | SomosBeds | 300ms `Timer.schedule` | 4 writes, 300ms apart |
| Sleep Harmony (`KSBT04C` / `base-i5.`) | Sleep Harmony | 300ms handler loop | 4 writes, 300ms apart |
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
100 ms refresh and send `00 B0` queries at +300/+600/+900 ms. Member's Mark
stops its 400 ms refresh without a dedicated release write, while its independent
timer continues sending `00 B0`. None sends a zero-key frame. Base/Ergomotion/
Serta families retain their family-specific zero frames. Purple uses the explicit
seven-byte P2 zero frame. Sleep Harmony waits 200 ms and sends one zero frame
after both movement and one-shot actions. KSBT03CR retains its independently
derived release behavior. One-shot commands themselves are sent once before any
profile-specific release.

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
| `base` / `base-i5` | Profile-dependent: Purple Premium uses E5/8-byte; Sleep Harmony uses E6/9-byte; select the explicit profile |
| `KSBT03C` | Nordic UART with 6-byte packets (3 motors: no head tilt; e.g. Ergomotion Rio 5.0) |
| `KSBT04` | Nordic UART with 6-byte packets (confirmed Rio 6.0 family) |
| `KSBT04C` | Profile-dependent: Purple Plus uses a trailing zero, Sleep Harmony uses a checksum; select the matching explicit profile |
| `ksbt03cr` | Nordic UART with 7-byte packets (KSBT03CR variant) |
| `EH` | Mattress variant (E0FF service) |
