# Ergomotion 4.0

**Status:** ❓ Needs testing (3.7 app behavior verified; hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

The app's built-in products H, M1–M22 and M30/EZI MAID, plus the 21 products
in the offline catalog acquired on 2026-11-03. The product table below gives
the exact choices. App labels do not establish physical motor counts.

This is the **Ergomotion 4.0** app (`com.sfd.hump`), distinct from the older
[Ergomotion app](keeson.md#ergomotion-app) B1/B2/C1/D1 profiles. Existing
[Keeson and Ergomotion profiles](keeson.md) keep their controls and entities.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Ergomotion 4.0](https://play.google.com/store/apps/details?id=com.sfd.hump) 3.7 (65) | `com.sfd.hump` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor control | ✅ Exact product-labelled held buttons, including dual-head and tilt/waist layouts |
| Split sides | ✅ Opt-in Left / Right / Both for P1 products, one Bluetooth address |
| P2 split sides | ❌ No side field in this six-byte protocol |
| Presets and memory | ✅ Product-labelled buttons; no invented memory slots or programming |
| Massage | ✅ Product-specific steps, modes, timer, stop and nine custom patterns |
| Lights | ✅ Toggle buttons; RGB and three brightness levels on eligible products |
| Position feedback | ❌ No measured motor positions in this app |
| Reported state | ✅ Massage timer, light state and RGB where reported |
| Local bed configuration | ✅ Rename, clock sync, two three-slot alarm tables and wake-vibration dismissal |
| Meditation | ✅ BLE start/stop on the four eligible product/name routes; repeat using HA automations |

## Protocol Details

**Write characteristics:** FFE9, Nordic UART `6e400002-b5a3-f393-e0a9-e50e24dcca9e`,
`6e400021-b5a3-f393-e0a9-e50e24dcca9e`, or
`6e400002-b5a3-f393-e0a9-38534c454550`.

**Notify characteristics:** FFE4, Nordic UART `6e400003-b5a3-f393-e0a9-e50e24dcca9e`,
`6e400022-b5a3-f393-e0a9-e50e24dcca9e`,
`6e400027-b5a3-f393-e0a9-e50e24dcca9e`, or
`6e400003-b5a3-f393-e0a9-38534c454550`.
FFE4/FFE9 expand to `0000xxxx-0000-1000-8000-00805f9b34fb`.
No service UUID chooses a product. The last matching write characteristic across
all services is selected, and all matching notification characteristics are
subscribed. The `38534c454550` notification suffix is captured for diagnostics
but ignored by the app-state parser, as in the app.

### Packet Format

[`codec/keeson.py`](../../custom_components/adjustable_bed/codec/keeson.py)
builds every frame below as the `ergomotion_4` Keeson app profile; the product
catalog picks which keys each product sends.

| Route | Format |
|-------|--------|
| P1 Both | `E5 FE 16 key_le32 checksum` (8 bytes) |
| P1 Left | `E6 FE 16 key_le32 02 checksum` (9 bytes) |
| P1 Right | `E6 FE 16 key_le32 01 checksum` (9 bytes) |
| P2 | `04 02 key_be32` (6 bytes), only the finite shipped key switch |
| Status query | `00 B0`, distinct from the P2 zero-key builder |
| Custom massage | `07 D0` plus seven parameter bytes |
| RGB1 | `09 0A 00 02 00 00 01 R G B 00` |
| RGB2 | `0A 02 00 00 00 00 01 01 BB (255-R) (255-G) (255-B) 00` |

P1 uses the low 32 key bits. Its checksum is `(~sum(previous_bytes)) & 0xFF`.
P2 has no checksum, side field or trailing byte. Unsupported keys map to the
builder's zero frame; no arbitrary command service is exposed. Only generic
product names containing `4194` use inverted RGB2. Fixed M16/M19 callbacks
always use RGB1.

### Write Mode

The app leaves Android's characteristic write type unchanged. Home Assistant
writes with response when supported, otherwise without response. It serializes
immutable frames through the existing BLE command lane; it does not reproduce
the app's mutable-characteristic queue or its queue-overflow disconnect defect.
No normal-control PIN, bonding exchange, MTU request or authentication frame
was found.

## Detection / Setup

1. Add the device manually and choose **Ergomotion 4.0 app (explicit product)**.
2. Select the exact product/layout shown by the app. Shared UUIDs and names
   never pick this profile or its product automatically.
3. To control one P1 receiver's split sides, open **Configure → Enable side
   controls**. Use the native Left and Right child devices, or the parent's
   Both controls. Revert using Configure when needed. P2 products do not offer
   this option. Revert side controls before changing from P1 to P2.

For an existing Keeson entry, explicitly select **BaseI4/BaseI5** or
**Ergomotion** before enabling side controls. An existing Ergomotion bed-type
entry also offers the option. Auto is excluded from the menu because it may
resolve to an incompatible JSON or P2 profile at connection time. Choose the
new explicit app profile to use the complete 3.7 controls instead.

Legacy Keeson/Ergomotion feedback has no side ownership, so side-control mode
disables position feedback and position seeking. Movement controls remain
available. Restoring standalone controls restores the saved feedback setting.

The Android 3.7 settings radio stores A/B, but its P1 builder only recognizes
Left/Right. Those A/B values incorrectly produce side byte `00`. HA deliberately
uses the proven Left=`02` and Right=`01` builder branches, never that app defect.
Confirm which physical half corresponds to Left/Right after beta/release; the
reporter has not provided a support bundle or a confirmed receiver profile.
For two independently advertising receivers, use the existing two-address
combined-bed workflow instead.

**Other catalog product** accepts the exact product name, ordered model keys,
massage keys, light and RGB flags from that product's catalog record. It is an
explicit capability selection, not an online lookup. `k1/k2/k3` select simple
head/foot/flat; `o1/o2/o3/o4` select anti-snore/memory/relax/TV in incoming
order. Three preset slots are visible unless all `o1`–`o4` occur, which
selects four slots. `o5` consumes a slot but has no command. Simple layouts take precedence, then
`m10` dual-head, then `m7/m8/m9` head-tilt/waist/foot-tilt. Massage levels
`m3+m4` take precedence over two-zone `m5+m6` or either singleton zone.
`m1` shows timer and `m1+m2` also shows massage stop. Copy only the exact
product's keys, without combining products.

The built-in **M22** choice represents a persisted-only legacy layout; it is not
in the app's current popup. EZI MAID is an alias of M30. A trailing space in
`ErgoBalance100 ` is significant in the frozen catalog.

### Products

| Choice | App label | Frame family |
|--------|-----------|--------------|

| `H` | H (H) | P1 |
| `M10` | 4166 (M10) | P2 |
| `M11` | 8200 (M11) | P2 |
| `M13` | 8280 (M13) | P1 |
| `M14` | 822H (M14) | P2 |
| `M15` | Rio 2.0/3.0 (M15) | P2 |
| `M16` | M16 (M16) | P2 |
| `M17` | 5620 (M17) | P2 |
| `M18` | 567H Flex2 (M18) | P2 |
| `M19` | 4193 RGB (M19) | P2 |
| `M20` | 567H Flex1 (M20) | P2 |
| `M21` | Flex3 Lumbar (M21) | P2 |
| `M22` | M22 (legacy saved layout) | P2 |
| `M2` | M2 (M2) | P1 |
| `M12` | Euro Mattress (M12) | P1 |
| `M30` | EZI MAID (M30) | P2 |
| `M3` | M3 (M3) | P1 |
| `M4` | M4 (M4) | P1 |
| `M5` | M5 (M5) | P1 |
| `M6` | M6 (M6) | P1 |
| `M7` | Symbol Mattress (M7) | P1 |
| `M8` | 6910 (M8) | P2 |
| `M9` | 3350 (M9) | P2 |
| `M1` | M1 (M1) | P1 |
| `20th Anniversary` | 20th Anniversary | P2 |
| `4180` | 4180 | P2 |
| `4184` | 4184 | P2 |
| `4193` | 4193 | P2 |
| `4194RGB` | 4194RGB | P2 |
| `828` | 828 | P2 |
| `Aeroflex-4308` | Aeroflex-4308 | P2 |
| `Aeroflex-5623` | Aeroflex-5623 | P2 |
| `Chaide 4166` | Chaide 4166 | P2 |
| `EZI MAID` | EZI MAID | P2 |
| `ErgoBalance Pro-4168+` | ErgoBalance Pro-4168+ | P2 |
| `ErgoBalance-4168` | ErgoBalance-4168 | P2 |
| `ErgoBalance100 ` | ErgoBalance100 | P2 |
| `ErgoBasic-4087` | ErgoBasic-4087 | P2 |
| `ErgoDuetto-4367/4364` | ErgoDuetto-4367/4364 | P2 |
| `Ergocomfort 5680/568H` | Ergocomfort 5680/568H | P2 |
| `Flex3 Massage` | Flex3 Massage | P2 |
| `Ortobom 3350` | Ortobom 3350 | P2 |
| `Rosen 4165` | Rosen 4165 | P2 |
| `SIMONS SA 3410S` | SIMONS SA 3410S | P2 |
| `SMART TEC-4193` | SMART TEC-4193 | P2 |

### Home Assistant setup

Choose **Ergomotion 4.0 app (explicit product)** and the exact product shown in
the app. This is separate from the older Ergomotion app's B1/B2/C1/D1 layouts.
The [product guide](#products) lists all built-in choices and
the 21 frozen catalog products. Other catalog product accepts that product's
exact name and ordered feature keys, without connecting to a vendor account.
Motor pulse count bounds each held action at the app's fixed 100 ms cadence.

For a P1 receiver with one address, **Configure → Enable side controls** adds
Left/Right child devices and native Both controls. Existing Keeson entries can
use this after explicitly selecting BaseI4/BaseI5 or Ergomotion; the Ergomotion
bed type also supports it. Auto and P2/JSON/OEM profiles are ineligible. Revert
side controls before changing to a profile without a side field. Existing
standalone profiles and entities retain their behavior.

Legacy Keeson/Ergomotion position feedback cannot identify a side. Side-control
mode disables position sliders, sensors and position seeking for these profiles;
movement controls remain available. Restoring standalone controls restores the
stored position-feedback preference.

HA uses the app builder's Left=`02` and Right=`01` branches. The Android app's
A/B radio labels do not establish physical orientation and contain a selector
mismatch. Confirm the halves with the real bed after beta/release. For two
separately advertising receivers, use the ordinary two-address combined bed.

## Commands

Every control below is exposed as a named HA button and appears in the card's
Actions section. Held controls include hold metadata and work with
`adjustable_bed.hold_control`. The control key is shown for automation use.
The table contains exactly the frames and sequences shipped in the controller.
P1 examples show Both; a side-bound action replaces every P1 frame, including
release, with the nine-byte frame for that same side.

`query ×3` means `00 B0` at +300/+600/+900 ms. `hold` means write immediately,
then every 100 ms until the bounded hold ends. A regular button/cover-sized
burst uses motor pulse count ×100 ms; `hold_control` accepts 1–60000 ms.
A source reset chord is exposed as its own held **Reset chord** button.

| Source control | HA control key | Label | Press bytes / sequence | Release |
|----------------|----------------|-------|------------------------|---------|
| C001 | `c001` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C002 | `c002` | Foot down double | hold `04 02 00 00 00 20` | query ×3 |
| C003 | `c003` | Foot down simple | hold `04 02 00 00 00 08` | query ×3 |
| C004 | `c004` | Foot tilt down | hold `04 02 00 00 00 A0` | query ×3 |
| C005 | `c005` | Foot tilt up | hold `04 02 00 00 00 50` | query ×3 |
| C006 | `c006` | Foot up | hold `04 02 00 00 00 04` | query ×3 |
| C007 | `c007` | Foot up double | hold `04 02 00 00 00 10` | query ×3 |
| C008 | `c008` | Foot up simple | hold `04 02 00 00 00 04` | query ×3 |
| C009 | `c009` | Head down | hold `04 02 00 00 00 02` | query ×3 |
| C010 | `c010` | Head down side1 | hold `04 02 00 00 00 02` | query ×3 |
| C011 | `c011` | Head down side2 | hold `04 02 00 00 00 08` | query ×3 |
| C012 | `c012` | Head down simple | hold `04 02 00 00 00 02` | query ×3 |
| C013 | `c013` | Head tilt down | hold `04 02 00 00 00 20` | query ×3 |
| C014 | `c014` | Head tilt up | hold `04 02 00 00 00 10` | query ×3 |
| C015 | `c015` | Head up | hold `04 02 00 00 00 01` | query ×3 |
| C016 | `c016` | Head up side1 | hold `04 02 00 00 00 01` | query ×3 |
| C017 | `c017` | Head up side2 | hold `04 02 00 00 00 04` | query ×3 |
| C018 | `c018` | Head up simple | hold `04 02 00 00 00 01` | query ×3 |
| C019 | `c019` | Waist down | hold `04 02 00 00 00 80` | query ×3 |
| C020 | `c020` | Waist head down | hold `04 02 00 00 00 02` | query ×3 |
| C021 | `c021` | Waist head up | hold `04 02 00 00 00 01` | query ×3 |
| C022 | `c022` | Waist up | hold `04 02 00 00 00 40` | query ×3 |
| C023 | `c023` | Foot massage down | `04 02 01 00 00 00`; wait 300 ms; query ×3 | none |
| C024 | `c024` | Foot massage up | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C025 | `c025` | Head massage down | `04 02 00 80 00 00`; wait 300 ms; query ×3 | none |
| C026 | `c026` | Head massage up | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C027 | `c027` | Brightness high | RGB at 100% | none |
| C028 | `c028` | Brightness low | RGB at 20% | none |
| C029 | `c029` | Brightness medium | RGB at 60% | none |
| C030 | `c030` | Flat | `04 02 08 00 00 00`; wait 500 ms; query ×3 | none |
| C031 | `c031` | Flat double | `04 02 08 00 00 00`; wait 500 ms; query ×3 | none |
| C032 | `c032` | Flat simple | `04 02 08 00 00 00`; wait 500 ms; query ×3 | none |
| C033 | `c033` | Waist flat | `04 02 08 00 00 00`; wait 500 ms; query ×3 | none |
| C034 | `c034` | Waist Zero G | `04 02 00 00 10 00` | none |
| C035 | `c035` | Zero G | `04 02 00 00 10 00` | none |
| C036 | `c036` | Zero G double | `04 02 00 00 10 00` | none |
| C037 | `c037` | Light toggle | `04 02 00 02 00 00`; wait 300 ms; query ×3 | none |
| C038 | `c038` | Foot massage | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C039 | `c039` | Foot massage | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C040 | `c040` | Head massage | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C041 | `c041` | Massage stop | `04 02 02 00 00 00`; wait 300 ms; query ×3 | none |
| C042 | `c042` | Massage timer | `04 02 00 00 02 00`; wait 300 ms; query ×3 | none |
| C043 | `c043` | Anti-snore | hold `04 02 00 00 80 00` | query ×3 |
| C044 | `c044` | Memory | hold `04 02 00 01 00 00` | query ×3 |
| C045 | `c045` | Relax | hold `04 02 00 00 20 00` | query ×3 |
| C046 | `c046` | TV | hold `04 02 00 00 40 00` | query ×3 |
| C047 | `c047` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C048 | `c048` | Foot up | hold `04 02 00 00 00 04` | query ×3 |
| C049 | `c049` | Anti Snore | hold `E5 FE 16 00 80 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C050 | `c050` | Flat | `E5 FE 16 00 00 00 08 FE` | none |
| C051 | `c051` | Foot Down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C052 | `c052` | Foot Up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C053 | `c053` | Head Down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C054 | `c054` | Head Up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C055 | `c055` | Level | `E5 FE 16 00 01 00 00 05` | none |
| C056 | `c056` | Light | `E5 FE 16 00 00 02 00 04` | none |
| C057 | `c057` | Lumbar Down | hold `E5 FE 16 80 00 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C058 | `c058` | Lumbar Up | hold `E5 FE 16 40 00 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C059 | `c059` | Massage Foot Add | `E5 FE 16 00 04 00 00 02`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C060 | `c060` | Massage Head Add | `E5 FE 16 00 08 00 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C061 | `c061` | Massage Lumbar Add | `E5 FE 16 00 00 40 00 C6`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C062 | `c062` | Massage Mode1 | wait 300 ms; `E5 FE 16 00 00 00 00 06`; `E5 FE 16 00 00 10 00 F6` | none |
| C063 | `c063` | Massage Mode2 | `E5 FE 16 00 00 20 00 E6`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C064 | `c064` | Massage Mode3 | `E5 FE 16 00 00 08 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C065 | `c065` | Read | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C066 | `c066` | Reset | hold `E5 FE 16 00 10 00 08 EE` | `E5 FE 16 00 00 00 00 06` |
| C067 | `c067` | Tilt Down | hold `E5 FE 16 20 00 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C068 | `c068` | Tilt Up | hold `E5 FE 16 10 00 00 00 F6` | `E5 FE 16 00 00 00 00 06` |
| C069 | `c069` | Tv | hold `E5 FE 16 00 40 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C070 | `c070` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |
| C071 | `c071` | Anti Snore | hold `04 02 00 00 80 00` | query ×3 |
| C072 | `c072` | Flat | `04 02 08 00 00 00` | none |
| C073 | `c073` | Foot Down | hold `04 02 00 00 00 08` | query ×3 |
| C074 | `c074` | Foot Up | hold `04 02 00 00 00 04` | query ×3 |
| C075 | `c075` | Head Down | hold `04 02 00 00 00 02` | query ×3 |
| C076 | `c076` | Head Up | hold `04 02 00 00 00 01` | query ×3 |
| C077 | `c077` | Light | `04 02 00 02 00 00` | none |
| C078 | `c078` | Lounge | hold `04 02 00 01 00 00` | query ×3 |
| C079 | `c079` | Massage Foot Add | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C080 | `c080` | Massage Head Add | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C081 | `c081` | Reset | hold `04 02 08 00 10 00` | query ×3 |
| C082 | `c082` | Timer | `04 02 04 00 00 00`; wait 300 ms; query ×3 | none |
| C083 | `c083` | Tv | hold `04 02 00 00 40 00` | query ×3 |
| C084 | `c084` | Zero G | `04 02 00 00 10 00` | none |
| C085 | `c085` | Flat | `04 02 08 00 00 00` | none |
| C085_reset | `c085_reset` | Reset chord | hold `04 02 08 00 10 00` | query ×3 |
| C086 | `c086` | Foot Down | hold `04 02 00 00 00 08` | query ×3 |
| C087 | `c087` | Foot Up | hold `04 02 00 00 00 04` | query ×3 |
| C088 | `c088` | Head Down | hold `04 02 00 00 00 02` | query ×3 |
| C089 | `c089` | Head Up | hold `04 02 00 00 00 01` | query ×3 |
| C090 | `c090` | Light | `04 02 00 02 00 00` | none |
| C091 | `c091` | Lounge | hold `04 02 00 00 20 00` | query ×3 |
| C092 | `c092` | Massage Foot Add | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C093 | `c093` | Massage Head Add | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C094 | `c094` | Massage Stop | `04 02 02 00 00 00` | none |
| C095 | `c095` | Music | hold `04 02 00 01 00 00` | query ×3 |
| C096 | `c096` | Zero G | `04 02 00 00 10 00` | none |
| C096_reset | `c096_reset` | Reset chord | hold `04 02 08 00 10 00` | query ×3 |
| C097 | `c097` | Flat | `E5 FE 16 00 00 00 08 FE` | none |
| C097_reset | `c097_reset` | Reset chord | hold `E5 FE 16 00 10 00 08 EE` | `E5 FE 16 00 00 00 00 06` |
| C098 | `c098` | Foot Down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C099 | `c099` | Foot Up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C100 | `c100` | Head Down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C101 | `c101` | Head Up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C102 | `c102` | Light | `E5 FE 16 00 00 02 00 04` | none |
| C103 | `c103` | Lounge | hold `E5 FE 16 00 40 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C104 | `c104` | Massage Foot Add | `E5 FE 16 00 04 00 00 02`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C105 | `c105` | Massage Head Add | `E5 FE 16 00 08 00 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C106 | `c106` | Massage Stop | `E5 FE 16 00 00 00 02 04` | none |
| C107 | `c107` | Music | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C108 | `c108` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |
| C108_reset | `c108_reset` | Reset chord | hold `E5 FE 16 00 10 00 08 EE` | `E5 FE 16 00 00 00 00 06` |
| C110 | `c110` | Flat | `04 02 08 00 00 00` | none |
| C111 | `c111` | Foot Up | hold `04 02 00 00 00 04` | query ×3 |
| C112 | `c112` | Head Down | hold `04 02 00 00 00 02` | query ×3 |
| C113 | `c113` | Head Up | hold `04 02 00 00 00 01` | query ×3 |
| C114 | `c114` | Light | `04 02 00 02 00 00` | none |
| C115 | `c115` | Massage Foot Add | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C116 | `c116` | Massage Head Add | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C117 | `c117` | Read | hold `04 02 00 00 20 00` | query ×3 |
| C118 | `c118` | TV | hold `04 02 00 00 40 00` | query ×3 |
| C119 | `c119` | Timer | `04 02 00 00 02 00`; wait 300 ms; query ×3 | none |
| C120 | `c120` | Zero G | `04 02 00 00 10 00` | none |
| C121 | `c121` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C122 | `c122` | Anti snore | hold `04 02 00 00 80 00` | query ×3 |
| C123 | `c123` | Flat | `04 02 08 00 00 00` | none |
| C124 | `c124` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C125 | `c125` | Foot up | hold `04 02 00 00 00 04` | query ×3 |
| C126 | `c126` | Head down | hold `04 02 00 00 00 02` | query ×3 |
| C127 | `c127` | Head up | hold `04 02 00 00 00 01` | query ×3 |
| C128 | `c128` | Massage all | `04 02 00 00 01 00`; wait 300 ms; query ×3 | none |
| C129 | `c129` | Massage foot | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C130 | `c130` | Massage head | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C131 | `c131` | Massage timer | `04 02 00 00 02 00`; wait 300 ms; query ×3 | none |
| C132 | `c132` | Tv | hold `04 02 00 00 40 00` | query ×3 |
| C133 | `c133` | Zero G | `04 02 00 00 10 00` | none |
| C134 | `c134` | Flat | `04 02 08 00 00 00` | none |
| C135 | `c135` | Foot Up | hold `04 02 00 00 00 04` | query ×3 |
| C136 | `c136` | Head Down | hold `04 02 00 00 00 02` | query ×3 |
| C137 | `c137` | Head Up | hold `04 02 00 00 00 01` | query ×3 |
| C138 | `c138` | Light | `04 02 00 02 00 00`; wait 300 ms; query ×3 | none |
| C139 | `c139` | Massage Foot Add | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C140 | `c140` | Massage Head Add | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C141 | `c141` | Read | hold `04 02 00 00 20 00` | query ×3 |
| C142 | `c142` | TV | hold `04 02 00 00 40 00` | query ×3 |
| C143 | `c143` | Timer | `04 02 00 00 02 00`; wait 300 ms; query ×3 | none |
| C144 | `c144` | Brightness high | RGB at 100% | none |
| C145 | `c145` | Brightness low | RGB at 20% | none |
| C146 | `c146` | Brightness medium | RGB at 60% | none |
| C147 | `c147` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C148 | `c148` | Anti Snore | hold `04 02 00 00 80 00` | query ×3 |
| C149 | `c149` | Flat | `04 02 08 00 00 00`; wait 300 ms; query ×3 | none |
| C150 | `c150` | Foot Up | hold `04 02 00 00 00 04` | query ×3 |
| C151 | `c151` | Head Down | hold `04 02 00 00 00 02` | query ×3 |
| C152 | `c152` | Head Up | hold `04 02 00 00 00 01` | query ×3 |
| C153 | `c153` | Light | `04 02 00 02 00 00` | none |
| C154 | `c154` | Lumbar Down | hold `04 02 00 00 00 80` | query ×3 |
| C155 | `c155` | Lumbar Up | hold `04 02 00 00 00 40` | query ×3 |
| C156 | `c156` | Massage Foot Add | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C157 | `c157` | Massage Head Add | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C158 | `c158` | Read | hold `04 02 00 00 20 00` | query ×3 |
| C159 | `c159` | TV | hold `04 02 00 00 40 00` | query ×3 |
| C160 | `c160` | Timer | `04 02 00 00 02 00`; wait 300 ms; query ×3 | none |
| C161 | `c161` | Zero G | `04 02 00 00 10 00` | none |
| C162 | `c162` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C163 | `c163` | Music | hold `04 02 00 01 00 00` | query ×3 |
| C164 | `c164` | Flat | `04 02 08 00 00 00`; wait 500 ms; query ×3 | none |
| C165 | `c165` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C166 | `c166` | Foot up | hold `04 02 00 00 00 04` | query ×3 |
| C167 | `c167` | Head down | hold `04 02 00 00 00 02` | query ×3 |
| C168 | `c168` | Head up | hold `04 02 00 00 00 01` | query ×3 |
| C169 | `c169` | Light | `04 02 00 02 00 00` | none |
| C170 | `c170` | Massage foot | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C171 | `c171` | Read | hold `04 02 00 00 20 00` | query ×3 |
| C172 | `c172` | Tv | hold `04 02 00 00 40 00` | query ×3 |
| C173 | `c173` | Zero G | `04 02 00 00 10 00` | none |
| C174 | `c174` | Music | hold `04 02 00 00 80 00` | query ×3 |
| C175 | `c175` | Flat | `04 02 08 00 00 00`; wait 500 ms; query ×3 | none |
| C176 | `c176` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C177 | `c177` | Foot up | hold `04 02 00 00 00 04` | query ×3 |
| C178 | `c178` | Head down | hold `04 02 00 00 00 02` | query ×3 |
| C179 | `c179` | Head up | hold `04 02 00 00 00 01` | query ×3 |
| C180 | `c180` | Light | `04 02 00 02 00 00`; wait 300 ms; query ×3 | none |
| C181 | `c181` | Read | hold `04 02 00 00 20 00` | query ×3 |
| C182 | `c182` | Tv | hold `04 02 00 00 40 00` | query ×3 |
| C183 | `c183` | Zero G | `04 02 00 00 10 00` | none |
| C184 | `c184` | Brightness high | RGB at 100% | none |
| C185 | `c185` | Brightness low | RGB at 20% | none |
| C186 | `c186` | Brightness medium | RGB at 60% | none |
| C187 | `c187` | Flat | `04 02 08 00 00 00`; wait 500 ms; query ×3 | none |
| C188 | `c188` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C189 | `c189` | Foot up | hold `04 02 00 00 00 04` | query ×3 |
| C190 | `c190` | Head down | hold `04 02 00 00 00 02` | query ×3 |
| C191 | `c191` | Head up | hold `04 02 00 00 00 01` | query ×3 |
| C192 | `c192` | Zero G | `04 02 00 00 10 00` | none |
| C193 | `c193` | Music | hold `04 02 00 01 00 00` | query ×3 |
| C194 | `c194` | Anti snore | hold `04 02 00 00 80 00` | query ×3 |
| C195 | `c195` | Flat | `04 02 08 00 00 00`; wait 500 ms; query ×3 | none |
| C196 | `c196` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C197 | `c197` | Foot tilt down | hold `04 02 00 00 00 80` | query ×3 |
| C198 | `c198` | Foot tilt up | hold `04 02 00 00 00 40` | query ×3 |
| C199 | `c199` | Foot up | hold `04 02 00 00 00 04` | query ×3 |
| C200 | `c200` | Head down | hold `04 02 00 00 00 02` | query ×3 |
| C201 | `c201` | Head up | hold `04 02 00 00 00 01` | query ×3 |
| C202 | `c202` | Light | `04 02 00 02 00 00` | none |
| C203 | `c203` | Massage foot | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C204 | `c204` | Read | hold `04 02 00 00 20 00` | query ×3 |
| C205 | `c205` | Tv | hold `04 02 00 00 40 00` | query ×3 |
| C206 | `c206` | Zero G | `04 02 00 00 10 00` | none |
| C207 | `c207` | Custom Massage0 | `07 D0 04 04 00 00 10 00 00` | none |
| C208 | `c208` | Custom Massage1 | `07 D0 02 06 00 00 09 00 01` | none |
| C209 | `c209` | Custom Massage2 | `07 D0 02 04 00 00 09 00 02` | none |
| C210 | `c210` | Custom Massage3 | `07 D0 02 04 00 00 09 00 03` | none |
| C211 | `c211` | Custom Massage4 | `07 D0 02 04 00 00 09 00 04` | none |
| C212 | `c212` | Custom Massage5 | `07 D0 04 06 00 00 09 00 05` | none |
| C213 | `c213` | Custom Massage6 | `07 D0 04 06 00 00 09 00 06` | none |
| C214 | `c214` | Custom Massage7 | `07 D0 04 06 00 00 09 00 07` | none |
| C215 | `c215` | Custom Massage8 | `07 D0 04 06 00 00 09 00 08` | none |
| C216 | `c216` | Flat | `04 02 08 00 00 00`; wait 500 ms; query ×3 | none |
| C217 | `c217` | Foot massage down | `04 02 01 00 00 00`; wait 300 ms; query ×3 | none |
| C218 | `c218` | Foot massage up | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C219 | `c219` | Head massage down | `04 02 00 80 00 00`; wait 300 ms; query ×3 | none |
| C220 | `c220` | Head massage up | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C221 | `c221` | Lounge | hold `04 02 00 00 20 00` | query ×3 |
| C222 | `c222` | Massage all | `04 02 00 00 01 00`; wait 300 ms; query ×3 | none |
| C223 | `c223` | Massage all stop | `04 02 02 00 00 00`; wait 300 ms; query ×3 | none |
| C224 | `c224` | Zero G | `04 02 00 00 10 00` | none |
| C225 | `c225` | Anti Snore | hold `E5 FE 16 00 80 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C226 | `c226` | Flat | `E5 FE 16 00 00 00 08 FE` | none |
| C227 | `c227` | Foot Down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C228 | `c228` | Foot Up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C229 | `c229` | Head Down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C230 | `c230` | Head Up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C231 | `c231` | Level | `E5 FE 16 00 01 00 00 05` | none |
| C232 | `c232` | Light | `E5 FE 16 00 00 02 00 04` | none |
| C233 | `c233` | Massage Foot Add | `E5 FE 16 00 04 00 00 02`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C234 | `c234` | Massage Head Add | `E5 FE 16 00 08 00 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C235 | `c235` | Music | hold `E5 FE 16 00 00 01 00 05` | `E5 FE 16 00 00 00 00 06` |
| C236 | `c236` | Read | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C237 | `c237` | Reset | hold `E5 FE 16 00 10 00 08 EE` | `E5 FE 16 00 00 00 00 06` |
| C238 | `c238` | Tv | hold `E5 FE 16 00 40 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C239 | `c239` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |
| C240 | `c240` | Anti Snore | hold `E5 FE 16 00 80 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C241 | `c241` | Flat | `E5 FE 16 00 00 00 08 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C242 | `c242` | Foot Down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C243 | `c243` | Foot Up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C244 | `c244` | Head Down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C245 | `c245` | Head Up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C246 | `c246` | Level | `E5 FE 16 00 01 00 00 05` | none |
| C247 | `c247` | Light | `E5 FE 16 00 00 02 00 04` | none |
| C248 | `c248` | Massage Foot Add | `E5 FE 16 00 04 00 00 02`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C249 | `c249` | Massage Head Add | `E5 FE 16 00 08 00 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C250 | `c250` | Music | hold `E5 FE 16 00 00 01 00 05` | `E5 FE 16 00 00 00 00 06` |
| C251 | `c251` | Read | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C252 | `c252` | Reset | hold `E5 FE 16 00 10 00 08 EE` | `E5 FE 16 00 00 00 00 06` |
| C253 | `c253` | Tv | hold `E5 FE 16 00 40 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C254 | `c254` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |
| C255 | `c255` | Head down | hold `04 02 00 00 00 02` | query ×3 |
| C256 | `c256` | Head up | hold `04 02 00 00 00 01` | query ×3 |
| C257 | `c257` | Flat | `E5 FE 16 00 00 00 08 FE` | none |
| C258 | `c258` | Foot Down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C259 | `c259` | Foot Up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C260 | `c260` | Head Down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C261 | `c261` | Head Up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C262 | `c262` | Level | `E5 FE 16 00 01 00 00 05` | none |
| C263 | `c263` | Read | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C264 | `c264` | Reset | hold `E5 FE 16 00 10 00 08 EE` | `E5 FE 16 00 00 00 00 06` |
| C265 | `c265` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |
| C266 | `c266` | Anti Snore | hold `E5 FE 16 00 80 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C267 | `c267` | Flat | `E5 FE 16 00 00 00 08 FE` | none |
| C268 | `c268` | Foot Down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C269 | `c269` | Foot Up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C270 | `c270` | Head Down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C271 | `c271` | Head Up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C272 | `c272` | Level | `E5 FE 16 00 01 00 00 05` | none |
| C273 | `c273` | M | hold `E5 FE 16 00 00 00 40 C6` | `E5 FE 16 00 00 00 00 06` |
| C274 | `c274` | Massage Foot Add | `E5 FE 16 00 04 00 00 02`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C275 | `c275` | Massage Head Add | `E5 FE 16 00 08 00 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C276 | `c276` | Music | hold `E5 FE 16 00 00 01 00 05` | `E5 FE 16 00 00 00 00 06` |
| C277 | `c277` | Read | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C278 | `c278` | Reset | hold `E5 FE 16 00 10 00 08 EE` | `E5 FE 16 00 00 00 00 06` |
| C279 | `c279` | Tv | hold `E5 FE 16 00 40 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C280 | `c280` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |
| C281 | `c281` | Anti Snore | hold `E5 FE 16 00 80 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C282 | `c282` | Flat | `E5 FE 16 00 00 00 08 FE` | none |
| C283 | `c283` | Foot Up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C284 | `c284` | Head Down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C285 | `c285` | Head Up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C286 | `c286` | Light | `E5 FE 16 00 00 02 00 04` | none |
| C287 | `c287` | Lumbar Down | hold `E5 FE 16 80 00 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C288 | `c288` | Lumbar Up | hold `E5 FE 16 40 00 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C289 | `c289` | Massage Foot Add | `E5 FE 16 00 04 00 00 02`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C290 | `c290` | Massage Head Add | `E5 FE 16 00 08 00 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C291 | `c291` | Music | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C292 | `c292` | Read | hold `E5 FE 16 00 40 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C293 | `c293` | Timer | `E5 FE 16 00 02 00 00 04`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C294 | `c294` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |
| C295 | `c295` | Foot down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C296 | `c296` | Anti snore | hold `E5 FE 16 00 80 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C297 | `c297` | Flat | `E5 FE 16 00 00 00 08 FE` | none |
| C298 | `c298` | Foot down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C299 | `c299` | Foot tilt down | hold `E5 FE 16 80 00 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C300 | `c300` | Foot tilt up | hold `E5 FE 16 40 00 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C301 | `c301` | Foot up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C302 | `c302` | Head down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C303 | `c303` | Head foot down | hold `E5 FE 16 A0 00 00 00 66` | `E5 FE 16 00 00 00 00 06` |
| C304 | `c304` | Head foot up | hold `E5 FE 16 50 00 00 00 B6` | `E5 FE 16 00 00 00 00 06` |
| C305 | `c305` | Head tilt down | hold `E5 FE 16 20 00 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C306 | `c306` | Head tilt up | hold `E5 FE 16 10 00 00 00 F6` | `E5 FE 16 00 00 00 00 06` |
| C307 | `c307` | Head up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C308 | `c308` | Light | `E5 FE 16 00 00 02 00 04` | none |
| C309 | `c309` | Massage foot | `E5 FE 16 00 04 00 00 02`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C310 | `c310` | Massage head | `E5 FE 16 00 08 00 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C311 | `c311` | Massage timer | `E5 FE 16 00 02 00 00 04`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C312 | `c312` | Read | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C313 | `c313` | Tv | hold `E5 FE 16 00 40 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C314 | `c314` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |
| C315 | `c315` | All Massage | `E5 FE 16 00 01 00 00 05`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C316 | `c316` | Anti Snore | hold `E5 FE 16 00 80 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C317 | `c317` | Flat | `E5 FE 16 00 00 00 08 FE` | none |
| C318 | `c318` | Foot Up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C319 | `c319` | Head Down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C320 | `c320` | Head Up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C321 | `c321` | Light | `E5 FE 16 00 00 02 00 04` | none |
| C322 | `c322` | Massage Foot Add | `E5 FE 16 00 04 00 00 02`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C323 | `c323` | Massage Head Add | `E5 FE 16 00 08 00 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C324 | `c324` | Music | hold `E5 FE 16 00 00 01 00 05` | `E5 FE 16 00 00 00 00 06` |
| C325 | `c325` | Read | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C326 | `c326` | TV | hold `E5 FE 16 00 40 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C327 | `c327` | Timer | `E5 FE 16 00 02 00 00 04`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C328 | `c328` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |
| C329 | `c329` | Foot down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C330 | `c330` | Anti snore | hold `04 02 00 00 80 00` | query ×3 |
| C331 | `c331` | Flat | `04 02 08 00 00 00` | none |
| C332 | `c332` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C333 | `c333` | Foot up | hold `04 02 00 00 00 04` | query ×3 |
| C334 | `c334` | Head down | hold `04 02 00 00 00 02` | query ×3 |
| C335 | `c335` | Head tilt down | hold `04 02 00 00 00 20` | query ×3 |
| C336 | `c336` | Head tilt up | hold `04 02 00 00 00 10` | query ×3 |
| C337 | `c337` | Head up | hold `04 02 00 00 00 01` | query ×3 |
| C338 | `c338` | Light | `04 02 00 02 00 00` | none |
| C339 | `c339` | M | hold `04 02 00 01 00 00` | query ×3 |
| C340 | `c340` | Massage foot | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C341 | `c341` | Massage head | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C342 | `c342` | Massage timer | `04 02 00 00 02 00`; wait 300 ms; query ×3 | none |
| C343 | `c343` | Read | hold `04 02 00 00 20 00` | query ×3 |
| C344 | `c344` | Tv | hold `04 02 00 00 40 00` | query ×3 |
| C345 | `c345` | Zero G | `04 02 00 00 10 00` | none |
| C346 | `c346` | Demonstration | hold `04 02 40 00 00 00` | query ×3 |
| C348 | `c348` | Anti Snore | hold `04 02 00 00 80 00` | query ×3 |
| C349 | `c349` | Flat | `04 02 08 00 00 00` | none |
| C350 | `c350` | Foot Up | hold `04 02 00 00 00 04` | query ×3 |
| C351 | `c351` | Head Down | hold `04 02 00 00 00 02` | query ×3 |
| C352 | `c352` | Head Up | hold `04 02 00 00 00 01` | query ×3 |
| C353 | `c353` | Light | `04 02 00 02 00 00` | none |
| C354 | `c354` | Massage Foot Add | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C355 | `c355` | Massage Head Add | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C356 | `c356` | Read | hold `04 02 00 00 20 00` | query ×3 |
| C357 | `c357` | TV | hold `04 02 00 00 40 00` | query ×3 |
| C358 | `c358` | Timer | `04 02 00 00 02 00`; wait 300 ms; query ×3 | none |
| C359 | `c359` | Zero G | `04 02 00 00 10 00` | none |
| C360 | `c360` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C361 | `c361` | Anti Snore | hold `E5 FE 16 00 80 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C362 | `c362` | Flat | `E5 FE 16 00 00 00 08 FE` | none |
| C363 | `c363` | Foot Down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C364 | `c364` | Foot Up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C365 | `c365` | Head Down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C366 | `c366` | Head Up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C367 | `c367` | Level | `E5 FE 16 00 01 00 00 05` | none |
| C368 | `c368` | Light | `E5 FE 16 00 00 02 00 04` | none |
| C369 | `c369` | Massage Foot Add | `E5 FE 16 00 04 00 00 02`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C370 | `c370` | Massage Head Add | `E5 FE 16 00 08 00 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C371 | `c371` | Massage Lumbar Add | `E5 FE 16 00 00 40 00 C6` | none |
| C372 | `c372` | Read | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C373 | `c373` | Reset | hold `E5 FE 16 00 10 00 08 EE` | `E5 FE 16 00 00 00 00 06` |
| C374 | `c374` | Tv | hold `E5 FE 16 00 40 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C375 | `c375` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |

### Shared configuration and meditation

These actions remain available for P1 and P2 products. Rename, clock, alarms and
wake dismissal address the physical receiver, without a side field. Use a
physical/parent target once when configuring shared state.

| Action | Bytes | HA exposure |
|--------|-------|-------------|
| Rename | 18 bytes `EF 02` + 15 name bytes + complement checksum | `rename` action |
| Clock | `E7 80 01 year_minus_1900 month_minus_1 day hour24 minute second checksum` | `sync_clock` action |
| Weekly alarms | `ED 80 03` + 3 × `[hour minute weekday_bits wake]` + checksum | `configure_alarm_schedule` |
| One-time alarms | `ED 80 02` + 3 × `[delta_hours delta_minutes delta_seconds wake]` + checksum | `configure_alarm_schedule` |
| Wake vibration dismissal | `E1 80 04 9A`, once | Dismiss wake vibration button / `stop_wake_routine` |
| Meditation start, M14 or Flex3 Massage | `04 02 48 00 00 00`, wait 200 ms, query ×3 | Start meditation button |
| Meditation start, M21 or 20th Anniversary | `04 02 00 01 10 00`, wait 200 ms, query ×3 | Start meditation button |
| Meditation stop | `04 02 08 00 00 00`, wait 200 ms, query ×3 | Stop meditation button |

Names are Java-trimmed and must contain 1–16 UTF-16 code units. The app copies
that many default-encoded bytes, modeled as UTF-8, and overwrites the sixteenth
copied byte with the checksum. Non-ASCII names can therefore end with a partial
UTF-8 character. Inputs longer than 16 units are rejected before BLE to avoid
the app's array overflow.

Clock sync waits 500 ms after its frame. Alarm tables compact enabled records,
zero-fill three slots and use the complemented byte sum. Recurring weekdays
use `80 | Monday<<1 | Tuesday<<2 | Wednesday<<3 | Thursday<<4 | Friday<<5 |
Saturday<<6 | Sunday`; wake vibration is `03`, otherwise `00`. Both tables are
validated before any frame is written. Dispatch writes weekly then one-time,
500 ms apart, or just the selected table. HA requires future same-day one-time
alarms and rejects nonexistent/ambiguous local times instead of reproducing
Android's ambiguous date parsing. Dismissal does not invent an alarm-enabled
readback. The profile has no memory-save command.

Meditation requires a connected, initialized receiver and a nonempty Bluetooth
name. M14/Flex3 Massage require name prefix `KSBT03CP`, M21 requires `KSBT03CW`
(case-insensitive); 20th Anniversary accepts any nonempty name. `GM_DFU` and
`SMART_DFU` require vendor firmware maintenance in the app; HA does not attempt
that update. Repeat the start action from an HA automation for a cycle routine.
The app's four-row cycle list has no BLE routine-selection action.

RGB buttons and color writes require reported light-on state. HA power actions
use that reported state to make toggles idempotent, then wait up to two seconds
for confirmation on the current connection. Cancellation or disconnection ends
that host-side wait without admitting an unconfirmed color write. The light toggle
remains accessible while off. Brightness buttons use source binary32 factors
1.0, 0.6 and 0.2 and truncate each scaled channel. HA's color picker supplies RGB
channels directly; no phone bitmap/density or out-of-bounds picker behavior is
required. On M19 and generic products, the first applicable report seeds the
brightness-button base color. M16 retains the picker-selected color.

## Position Feedback / Notifications

| Length / prefix | Parsed state |
|-----------------|--------------|
| 11 bytes | No state update |
| 18 / `A5 0B 0F` | Timer seconds `[3:5]` big-endian, light byte 12 |
| 16 / `A5 0B 0D` | M10 signed timer byte 5; otherwise seconds `[3:5]`, with light byte 12 on M16/M19/generic |
| 16 / other | Ignore when byte 13 bit 5 is set; otherwise signed timer byte 14 |
| 19 / `A5 0D 10` | No state update |
| 19 / other, M19/generic | Seconds `[3:5]`, light byte 12, RGB bytes 15–17 |
| 19 / other, fixed layouts | Side-filter byte 16, then signed timer byte 14 when header `F1`, otherwise byte 15 |
| 20 / any | Signed timer byte 14 |
| 23 / any | Signed timer byte 15 |
| 31 / `1D 0B` | Timer -1, light byte 14 |
| 31 / `1C 0B` | Seconds `[3:5]`, light byte 10, RGB bytes 11–13 |
| 31 / other | Seconds `[2:4]` |
| Other lengths/prefixes | Ignored |

Seconds 1–600 map to timer status 1, 601–1200 to 2, 1201–1800 to 3,
otherwise -1. Raw signed byte values are retained. Side bit 1 selects Right;
bit 0 without bit 1 rejects Right; no side bits admit all sides. Side-bound
sensor keys keep reports separate, so one half does not overwrite the other.
HA exposes parsed timer and light state even where the app omits that product
from its visible icon-update overload. Fields discarded by the app are never
reported as measured positions. No receive checksum, acknowledgement,
fragmentation or buffering is invented.

## Command Timing

P1 session initialization writes one zero key. P2 initializes with query ×3;
M30/EZI MAID is the exception, initializing with a P1 zero before P2 controls.
P1 held controls release with a same-side zero frame. P2 releases cancel the
refresh and issue queries, without inventing a motor STOP frame. One-shot
buttons retain their individual waits and release sequences from the table.
H's mode 1 specifically waits 300 ms, writes zero, then writes the mode key.
M10's massage timer sends key `04000000`, not a substituted common timer key.

Cancellation and failed pulse writes still attempt the recovered cleanup with
a fresh cancellation event. Cleanup stays on its original session and side;
a reconnection never receives an older command's pending release or queries.
Normal command serialization, adapter/proxy selection, handoff and reconnect
remain owned by Home Assistant. No firmware watchdog timing is inferred.

## Notes

Real users should validate receiver selection, physical Left/Right mapping,
motor effects, release behavior, ATT write mode, notifications, RGB, rename and
alarm acceptance after a beta/release. Hardware is unverified and is not a
maintainer implementation blocker.

### Analysis provenance

- Package/version: `com.sfd.hump` 3.7 (65), complete five-member Play split set.
- Artifact-set SHA-256: `cd637f0dec9831c9deb08f1449b2faf87c9dd70f511eaeb7210950c7a7eb69c0`.
- Report seal: `221e356d9e6b88aaa68991d666a1bfa978ee5356be7c6da0447979b08ff09e7b`.
- Accepted independent audit: `9b317001ba212a9e58270b340c7ab1be45cbae7bb58f66b3b56bb6e522c8ae4d`, 17/17 PASS.
- [Complete discovery dispositions](../apk-analysis/dispositions/issue558-ergomotion4.md).
- Ref [#558](https://github.com/kristofferR/ha-adjustable-bed/issues/558).
