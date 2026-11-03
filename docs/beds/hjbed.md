# HJBed app

**Status:** ❓ Needs testing (static app evidence; physical behavior, ATT and firmware acceptance unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

Choose **HJBed app** and the exact product shown in HJBed. The picker includes all
19 current products and 24 conditionally restored products. Shared services and
Bluetooth names do not identify the layout.

| HA product profile | App label | Remote code | App selector |
| --- | --- | --- | --- |
| `aw_motionhc800` | HC800 | `LTRM` | Conditional |
| `aw_motionsn300` | SN300 | `B3RN` | Conditional |
| `aw_motionsn500` | SN500 | `LTRM` | Conditional |
| `dream_blue` | blue | `LTRM` | Conditional |
| `dream_green` | green | `HARM` | Conditional |
| `dream_orange` | orange | `JMRM` | Conditional |
| `dream_yellow` | yellow | `HBRM` | Conditional |
| `flexxafeg300` | AFEG300 | `L5RN` | Conditional |
| `flexxafeg300sh` | AFEG300-SH | `LPRN` | Conditional |
| `flexx_linkrfrn` | FlexxLink | `RFRN` | Conditional |
| `flexxpb250` | PB250 | `VJRM` | Conditional |
| `flexxpb300` | PB300 | `FARM` | Conditional |
| `flexxpb325` | PB325 | `FARM` | Conditional |
| `flexxpb450` | PB450 | `MPRM` | Conditional |
| `flexxpb450sh` | PB450-SH | `LVRN` | Conditional |
| `hj_bedbjrn` | BJRN | `BJRN` | Current |
| `hj_bedbyrn` | BYRN | `BYRN` | Current |
| `hj_bedd4rn` | D4RN | `D4RN` | Current |
| `hj_bedd5rn` | D5RN | `D5RN` | Current |
| `hj_bedd6rn` | D6RN | `D6RN` | Current |
| `hj_bedd7rn` | D7RN | `D7RN` | Current |
| `hj_bede3rm` | E3RM | `E3RM` | Current |
| `hj_bedfarm` | FARM | `FARM` | Current |
| `hj_bedhzrm` | HZRM | `HZRM` | Current |
| `hj_bedjgrm` | JGRM | `JGRM` | Current |
| `hj_bedjhrm` | JHRM | `JHRM` | Current |
| `hj_bedjjrm` | JJRM | `JJRM` | Current |
| `hj_bedkzrm` | KZRM | `KZRM` | Current |
| `hj_bedl2rm` | L2RM | `L2RM` | Current |
| `hj_bedrern` | RERN | `RERN` | Current |
| `hj_bedtyrn` | TYRN | `TYRN` | Current |
| `hj_bedtzrn` | TZRN | `TZRN` | Current |
| `hj_beduurn` | UURN | `UURN` | Current |
| `hj_bedvjrm` | VJRM | `VJRM` | Current |
| `likomioabm10` | ABM10 | `UTRM` | Conditional |
| `motionnxca200` | Series 1 | `GURN` | Conditional |
| `motionnxca300` | Series 2 | `GVRN` | Conditional |
| `motion_opus` | Series 3 | `GWRN` | Conditional |
| `muuegmabf03` | ABF03 | `BNRN` | Conditional |
| `muuegmabf07` | ABF07 | `DNRN` | Conditional |
| `muuegmnupg400` | NUPG400 | `BVRN` | Conditional |
| `velocityvip3` | VIP 3.0 | `` | Conditional |
| `velocityvip3sh` | VIP 3.0-SH | `` | Conditional |

## Apps

| Analyzed | App | Package ID |
| --- | --- | --- |
| ✅ | [HJBed](https://play.google.com/store/apps/details?id=com.richmat.hjbed) 2.1.2 (code 21200) | `com.richmat.hjbed` |

## Features

| Feature | Supported |
| --- | --- |
| Motor Control | ✅ Selected head, foot, combined, pillow, lumbar, tilt, foot-box and sofa routes, depending on product |
| Position Feedback | Raw observed travel, angle and height data; no inferred position seeking or units |
| Memory Presets | ✅ Product-specific named recall/save buttons, including memory 1–4 where selected |
| Massage | ✅ Product-specific mode, intensity and timer buttons |
| Lights | ✅ Selected lamp buttons; advanced timeout/RGB require product flag and acknowledgement |
| Alarms | ✅ Single or repeat alarms where the product flag and clock acknowledgement permit |
| Music | ✅ All eight independent named actions, fixed to left 0 |
| Clock synchronization | ✅ Timestamp and calendar writes |
| Paired beds | ✅ Single-address left/right controls for the four coupled profiles |
| Local layout | ✅ Normal/Motion selection and persisted acknowledged single-alarm preferences |
| Bluetooth authentication | No app-owned PIN, challenge or bonding exchange |

## Protocol Details

| Service UUID | Write characteristic | Generic mode |
| --- | --- | --- |
| `0000fee9-0000-1000-8000-00805f9b34fb` | `d44bc439-abfd-45a2-b575-925416129600` | Framed |
| `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | Single code |
| `0000e0ff-3c17-d293-8e48-14fe2e4da212` | `00000002-3c17-d293-8e48-14fe2e4da212` | Framed |
| `0000fff0-0000-1000-8000-00805f9b34fb` | `0000fff2-0000-1000-8000-00805f9b34fb` | Framed |
| `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe2-0000-1000-8000-00805f9b34fb` | Framed |
| `0000fee9-0000-1000-8000-00805f9b34bb` | `d44bc439-abfd-45a2-b575-925416129622` | Framed |

**Notify characteristic:** first characteristic with `notify` in an accepted service.

### Packet Format

| Packet | Exact format |
| --- | --- |
| Generic single-code | One `code` byte |
| Generic framed | `6e 01 side code sum8`, left `00`, right `01` |
| Exit limit | `6e 02 01 00 71` in framed mode; `00` in single-code mode |
| Clock menu probe | `6e 08 01 01 78` in framed mode; `01` in single-code mode |
| Light menu probe | `6e 0a 00 01 79` in framed mode; `01` in single-code mode |
| Music menu probe | `6e 15 01 01 85` in framed mode; `01` in single-code mode |
| Variable outbound | `6e length 20 ... sum8` |
| Extended inbound | `6e 20 length ...` or `6e 21 length ...` |

`sum8` is the sum of preceding integers masked to eight bits. Every final integer
is masked to eight bits. Variable builders retain their frames in single-code mode.

### Write Mode

Write selection requires `write`. A selected `write-without-response` property
uses writes without response; otherwise writes use response. Selection retains
the first eligible write and first notify, while the last matched service decides
the generic packet mode. HA/Bleak handles MTU negotiation without an arbitrary override.

## Detection / Setup

- Choose the explicit app and product profile; configure two-address sides separately.
- Bluetooth scan candidates contain case-sensitive `QRRM`, `COOL`, `MPE_`, `209A` or `ZRA1`.
- HA's indexed name hints match those prefixes. Service/manual detection still accepts the keywords anywhere in a name.
- Names with an earlier prefix and no eligible advertised service use manual device selection. HA rejects leading-wildcard manifest matchers.
- E0FF uses name hints or manual selection because non-bed devices share it; all six listed transports work after explicit selection.
- HA provides discovery and an explicit device/product picker. Names are scan hints, not capability evidence.
- Phone text/QR input searches the current 19 remote codes; persisted display keys use exact case-sensitive first-match selection.
- HA stores an explicit profile per physical device, so ambiguous remote codes cannot change its layout.
- The two later FlexxLink objects are shadowed by the first RFRN display-key match and are not independent selectable profiles. `None` is unused as a control profile.
- No layout or feature is inferred from a generic Richmat remote table.

## Commands

Values below come from the shipped `beds/hjbed.py` controller and its imported
catalog/packet builders. Detail IDs distinguish product-specific variants. Each
product exposes only its selected controls. The full profile bindings are in the
[discovery ledger](../apk-analysis/dispositions/row121-hjbed.json).

### Motor Control

| Command (detail) | Single code | Framed left | Framed right | Gesture / release |
| --- | --- | --- | --- | --- |
| Foot Box Down (`975861`) | `25` | `6e01002594` | `6e01012595` | Refresh 100 ms; STOP |
| Foot Box Up (`9758e1`) | `24` | `6e01002493` | `6e01012494` | Refresh 100 ms; STOP |
| Foot Down (`9740e1`) | `27` | `6e01002796` | `6e01012797` | Refresh 100 ms; STOP |
| Foot Up (`974161`) | `26` | `6e01002695` | `6e01012696` | Refresh 100 ms; STOP |
| Head And Foot Down (`9743e1`) | `2a` | `6e01002a99` | `6e01012a9a` | Refresh 100 ms; STOP |
| Head And Foot Up (`974461`) | `29` | `6e01002998` | `6e01012999` | Refresh 100 ms; STOP |
| Head Down (`9741e1`) | `25` | `6e01002594` | `6e01012595` | Refresh 100 ms; STOP |
| Head Up (`974261`) | `24` | `6e01002493` | `6e01012494` | Refresh 100 ms; STOP |
| Lumbar Down (`973fe1`) | `40` | `6e010040af` | `6e010140b0` | Refresh 100 ms; STOP |
| Lumbar Down (`974be1`) | `42` | `6e010042b1` | `6e010142b2` | Refresh 100 ms; STOP |
| Lumbar Up (`974061`) | `3f` | `6e01003fae` | `6e01013faf` | Refresh 100 ms; STOP |
| Lumbar Up (`974c61`) | `41` | `6e010041b0` | `6e010141b1` | Refresh 100 ms; STOP |
| Pillow Down (`973ee1`) | `42` | `6e010042b1` | `6e010142b2` | Refresh 100 ms; STOP |
| Pillow Down (`974a61`) | `40` | `6e010040af` | `6e010140b0` | Refresh 100 ms; STOP |
| Pillow Up (`973f61`) | `41` | `6e010041b0` | `6e010141b1` | Refresh 100 ms; STOP |
| Pillow Up (`974ae1`) | `3f` | `6e01003fae` | `6e01013faf` | Refresh 100 ms; STOP |
| Tilt Down (`974fe1`) | `5c` | `6e01005ccb` | `6e01015ccc` | Refresh 100 ms; STOP |
| Tilt Up (`975061`) | `5b` | `6e01005bca` | `6e01015bcb` | Refresh 100 ms; STOP |
| Backward (`975461`) | `5c` | `6e01005ccb` | `6e01015ccc` | Refresh 100 ms; STOP |
| Forword (`9754e1`) | `5b` | `6e01005bca` | `6e01015bcb` | Refresh 100 ms; STOP |
| Head Down (`975561`) | `25` | `6e01002594` | `6e01012595` | Refresh 100 ms; STOP |
| Head Up (`9755e1`) | `24` | `6e01002493` | `6e01012494` | Refresh 100 ms; STOP |
| Lumbar Down (`975661`) | `40` | `6e010040af` | `6e010140b0` | Refresh 100 ms; STOP |
| Lumbar Up (`9756e1`) | `3f` | `6e01003fae` | `6e01013faf` | Refresh 100 ms; STOP |
| Pillow Down (`975761`) | `42` | `6e010042b1` | `6e010142b2` | Refresh 100 ms; STOP |
| Pillow Up (`9757e1`) | `41` | `6e010041b0` | `6e010141b1` | Refresh 100 ms; STOP |

### Presets

| Command (detail) | Single code | Framed left | Framed right | Gesture / release |
| --- | --- | --- | --- | --- |
| Anti Snoring (`9738e1`) | `46` | `6e010046b5` | `6e010146b6` | Once; no extra STOP |
| Anti Snoring (`975961`) | `46` | `6e010046b5` | `6e010146b6` | Refresh 100 ms; no extra STOP |
| Coaxing Sleep Mode (`9744e1`) | `86` | `6e010086f5` | `6e010186f6` | Once; no extra STOP |
| Lounge Position (`973961`) | `59` | `6e010059c8` | `6e010159c9` | Once; no extra STOP |
| Memory Position1 (`973861`) | `2e` | `6e01002e9d` | `6e01012e9e` | Once; no extra STOP |
| Memory Position1 (`974e61`) | `2e` | `6e01002e9d` | `6e01012e9e` | Refresh 100 ms; no extra STOP |
| Memory Position2 (`9737e1`) | `2f` | `6e01002f9e` | `6e01012f9f` | Once; no extra STOP |
| Memory Position2 (`974de1`) | `2f` | `6e01002f9e` | `6e01012f9f` | Refresh 100 ms; no extra STOP |
| Memory Position3 (`9751e1`) | `30` | `6e0100309f` | `6e010130a0` | Refresh 100 ms; no extra STOP |
| Memory Position4 (`975261`) | `b2` | `6e0100b221` | `6e0101b222` | Refresh 100 ms; no extra STOP |
| T V Position (`973a61`) | `58` | `6e010058c7` | `6e010158c8` | Once; no extra STOP |
| T V Position (`974d61`) | `58` | `6e010058c7` | `6e010158c8` | Refresh 100 ms; no extra STOP |
| T V Position (`975161`) | `58` | `6e010058c7` | `6e010158c8` | Refresh 100 ms; no extra STOP |
| Zero Gravity (`9739e1`) | `45` | `6e010045b4` | `6e010145b5` | Once; no extra STOP |
| Zero Gravity (`974ce1`) | `45` | `6e010045b4` | `6e010145b5` | Refresh 100 ms; no extra STOP |
| Zero Gravity (`9750e1`) | `45` | `6e010045b4` | `6e010145b5` | Refresh 100 ms; no extra STOP |

### Massage

| Command (detail) | Single code | Framed left | Framed right | Gesture / release |
| --- | --- | --- | --- | --- |
| Massage10 Minute Timer (`973be1`) | `5f` | `6e01005fce` | `6e01015fcf` | Once; STOP |
| Massage20 Minute Timer (`973b61`) | `63` | `6e010063d2` | `6e010163d3` | Once; STOP |
| Massage30 Minute Timer (`973ae1`) | `61` | `6e010061d0` | `6e010161d1` | Once; STOP |
| Massage Foot Instensity Strengthen (`973d61`) | `4e` | `6e01004ebd` | `6e01014ebe` | Once; STOP |
| Massage Head Instensity Strengthen (`973de1`) | `4c` | `6e01004cbb` | `6e01014cbc` | Once; STOP |
| Massage Instensity Strengthen (`974361`) | `34` | `6e010034a3` | `6e010134a4` | Once; STOP |
| Massage Mode All Off (`973c61`) | `5e` | `6e01005ecd` | `6e01015ece` | Once; STOP |
| Massage Mode Change (`973ce1`) | `48` | `6e010048b7` | `6e010148b8` | Once; STOP |
| Massage Switch (`9742e1`) | `6f` | `6e01006fde` | `6e01016fdf` | Once; STOP |

### Lights

| Command (detail) | Single code | Framed left | Framed right | Gesture / release |
| --- | --- | --- | --- | --- |
| Bed Light (`974961`) | `3c` | `6e01003cab` | `6e01013cac` | Once; STOP |
| Bed Light Close (`9759e1`) | `75` | `6e010075e4` | `6e010175e5` | Once; no extra STOP |
| Light Board (`9749e1`) | `50` | `6e010050bf` | `6e010150c0` | Once; STOP |
| Light (`975361`) | `3c` | `6e01003cab` | `6e01013cac` | Once; no extra STOP |

### Music

| Command (detail) | Single code | Framed left | Framed right | Gesture / release |
| --- | --- | --- | --- | --- |
| Music Blue Tooth Switch (`9748e1`) | `d8` | `6e0100d847` | `6e0100d847` | Once; no extra STOP |
| Music Next Song (`974661`) | `d3` | `6e0100d342` | `6e0100d342` | Once; no extra STOP |
| Music Pause Play (`9745e1`) | `d7` | `6e0100d746` | `6e0100d746` | Once; no extra STOP |
| Music Previous Song (`9746e1`) | `d2` | `6e0100d241` | `6e0100d241` | Once; no extra STOP |
| Music Shake Mode (`974861`) | `d6` | `6e0100d645` | `6e0100d645` | Once; no extra STOP |
| Music Switch Sound Track (`975ae1`) | `c4` | `6e0100c433` | `6e0100c433` | Once; no extra STOP |
| Music Volumu Down (`974761`) | `d5` | `6e0100d544` | `6e0100d544` | Once; no extra STOP |
| Music Volumu Up (`9747e1`) | `d4` | `6e0100d443` | `6e0100d443` | Once; no extra STOP |

### Reset, stop and sync

| Command (detail) | Single code | Framed left | Framed right | Gesture / release |
| --- | --- | --- | --- | --- |
| Exit Limit (`973761`) | `00` | `6e02010071` | `6e02010071` | Once; no extra STOP |
| Motor Reset (`973e61`) | `31` | `6e010031a0` | `6e010131a1` | Once; STOP; Motion once |
| Motor Reset (`974f61`) | `31` | `6e010031a0` | `6e010131a1` | Refresh 100 ms; STOP; Motion once |
| Stop (`975a61`) | `6e` | `6e01006edd` | `6e01016ede` | Once; no extra STOP |
| Sync Off (`9752e1`) | `bd` | `6e0100bd2c` | `6e0101bd2d` | Once; no extra STOP |
| Sync On (`974b61`) | `bc` | `6e0100bc2b` | `6e0101bc2c` | Once; no extra STOP |
| Sit Position (`9753e1`) | `e5` | `6e0100e554` | `6e0101e555` | Refresh 100 ms; no extra STOP |

### Memory

Save is available only for selected preset details with a long code. BJRN waits
three seconds; other product saves send once immediately. Recall and save remain
separate actions.

| Save command (detail) | Single code | Framed left | Framed right |
| --- | --- | --- | --- |
| Anti Snoring (`9738e1`) | `69` | `6e010069d8` | `6e010169d9` |
| Anti Snoring (`975961`) | `69` | `6e010069d8` | `6e010169d9` |
| Coaxing Sleep Mode (`9744e1`) | `89` | `6e010089f8` | `6e010189f9` |
| Lounge Position (`973961`) | `65` | `6e010065d4` | `6e010165d5` |
| Memory Position1 (`973861`) | `2b` | `6e01002b9a` | `6e01012b9b` |
| Memory Position1 (`974e61`) | `2b` | `6e01002b9a` | `6e01012b9b` |
| Memory Position2 (`9737e1`) | `2c` | `6e01002c9b` | `6e01012c9c` |
| Memory Position2 (`974de1`) | `2c` | `6e01002c9b` | `6e01012c9c` |
| Memory Position3 (`9751e1`) | `2d` | `6e01002d9c` | `6e01012d9d` |
| Memory Position4 (`975261`) | `b3` | `6e0100b322` | `6e0101b323` |
| T V Position (`973a61`) | `64` | `6e010064d3` | `6e010164d4` |
| T V Position (`974d61`) | `64` | `6e010064d3` | `6e010164d4` |
| T V Position (`975161`) | `64` | `6e010064d3` | `6e010164d4` |
| Zero Gravity (`9739e1`) | `66` | `6e010066d5` | `6e010166d6` |
| Zero Gravity (`974ce1`) | `66` | `6e010066d5` | `6e010166d6` |
| Zero Gravity (`9750e1`) | `66` | `6e010066d5` | `6e010166d6` |

## Command Timing

- Sustained controls start at the first 100 ms tick and use monotonic tick deadlines.
- Writes are serialized with at least 100 ms between attempts. Write latency does not accumulate in the refresh interval.
- Both-side frames share one bounded hold window. Stale refreshes are dropped; an in-flight write and required cleanup may finish after the window.
- Every attempted side retains its own release, including when another side's release fails.
- Startup sends Exit, two clock-sync frames and the eligible mode query before the three 300 ms menu probes.

## Controls

Covers represent actual selected up/down pairs. A lone combined-up action remains
a button, without inventing combined-down. Named buttons retain each product's
preset, save, massage, light, sync and sofa controls. All eight independently
reachable MusicPage actions are available, including next/previous, even when the
profile has no music tab. Music packets always use left 0, as configured.

The pulse count bounds a normal HA action. The card uses a bounded held action;
its release button cancels refresh and runs that action's own cleanup. Motors,
normal reset, bed light and massage send their configured STOP where applicable.
Presets and sofa reset end refresh without an extra STOP. Sofa lamp and music
send once without STOP. BJRN preset programming waits three seconds; other
programming sends its long code once. Explicit Stop remains available separately.
The **HJBed layout** local select chooses Normal or the conditionally named Motion
layout; Motion reset is a short action and its mode query has a narrower gate.

Short controls with a release callback send once on down, wait for release, then
perform cleanup; holding them does not turn them into repeated commands. Native
single-address paired side controls are offered only by the four coupled profiles.

The `hold_control` action accepts a listed `hjbed_*` control and a finite duration
up to 60 seconds. Sub-100 ms sustained actions send nothing. Save and recall are
separate actions, so holding recall never overwrites a memory.

## Configuration actions

Variable builders below always retain their full frames, including in single-code mode.
These are exact examples from the shipped builders; fields vary with the requested values.

| Operation and example input | Exact GATT write(s) |
| --- | --- |
| Single alarm: 1440 minutes, code `45` | `6e05a00013`; `6e060545be` |
| Cancel single alarm | `6e05000073`; `6e06000074` |
| Light timeout: 600 seconds | `6e0b0258d3` |
| Light always on: 0 seconds | `6e0bffff77` |
| RGB: 11, 22, 33; one combined write | `6e0cff0b846e0d1621b2` |
| Repeat alarm: slot1, kind0, 07:30, code45, Monday enabled | `6e0d200501010100071e45818e` |
| Delete repeat slot1 | `6e0820050201019f` |
| Query repeat list | `6e0820050100009c` |
| Clock sync: 2026-11-03 12:00:00 +01:00 | `6e0c200802016ae9beb00167`; `6e0d20080301380b030c0000f9` |
| Query control mode | `6e08200b020000a3` |
| Split-head mode0 | `6e09200b02010000a5` |
| Standard mode2 | `6e09200b02010002a7` |


Use `adjustable_bed.hjbed` with `device_id` and `operation`. All selected physical
targets are validated before any configuration write. Generic `side` routing
remains supported; direct variable builders configure the current physical
receiver, while generic motion frames select left 0 or right 1. Music stays left.

| Operation | Fields | Eligibility |
| --- | --- | --- |
| `single` | `time`, `action` | Single-alarm product flag and clock acknowledgement |
| `cancel_single` | none | Same single-alarm gate |
| `repeat` | `time`, `action`, optional `alarm_id`, `weekdays`, `enabled` | Repeat-alarm flag and clock acknowledgement |
| `query`, `delete` | `alarm_id` for delete | Repeat-alarm gate |
| `toggle` | observed `alarm_id`, `enabled` | Repeat-alarm gate |
| `sync` | none | Clock synchronization used by the app's product menu |
| `light_timeout` | `seconds` | Light-page flag and light acknowledgement |
| `light_color` | `rgb_color` | Same light-page gate |
| `mode` | `mode: split_head` or `standard` | Normal layout, blue/green/orange only |

Alarm time uses minute precision. Empty weekdays means once; Monday is bit 7,
Sunday bit 1, enabled bit 0. New alarms choose the smallest unused slot 1 through
7 unless a valid slot is supplied. A full table is rejected rather than sending
an invalid slot. Imported custom alarm data is retained when toggling a record.
Single-alarm preferences are persisted only after the bed's success reply and
removed on cancellation success. The saved selected date/time, function identity,
label and nullable repeat metadata remain available after restart. An unsolicited
add-success event cannot replace that metadata with a guessed selection. Repeat-list observations preserve full bean
equality; an escalation replaces only the first matching number. Query clears the
observed list before replies; deletion removes the first selected full bean.
Single-alarm countdowns subtract epoch seconds across DST changes and retain the
86400-second fallback when the target is not later.

Light timeout is 0 to 900 seconds (0 means always on), except blue, which offers
1800 to 28800 seconds. Color sends one 10-byte GATT write containing both
checksummed RGB pieces. No brightness or extra lighting command is invented.

The current 19 profiles have all advanced music/alarm/repeat/light-page flags
false. A feature reply cannot override that static gate. Simple lamp buttons,
selected massage lists, and independently named music routes remain independent.
The full per-product action and flag inventory is in the
[durable disposition ledger](../apk-analysis/dispositions/row121-hjbed.json).
Alarm action keys are snake-case names such as `zero_gravity`, `anti_snoring`,
`memory_position1`, `tv_position`, or `lounge_position`, and must belong to the
selected product's alarm list.

## Telemetry and transport

**HJBed status** exposes the last event, structured `hjbed_events`, complete
`hjbed_alarms`, `hjbed_saved_alarm` and parser rejection information. Bed
observations include motor travel/angles/height, version/control modes, massage,
white/RGB lighting, music, snore/off-bed/name/locks, coaxing, aroma, heating, fan,
blanket and detection data. These passive readings do not enable an outbound
command. Raw values are retained where physical units or motor mappings are not
proven. Position seeking is not inferred from those observations.

The six service/write pairs are in `beds/hjbed.py:GATT`. The first
eligible write and first notify characteristic are retained in returned order;
the last matched service decides single-code versus framed generic commands.
Write selection requires `write`, notification selection requires `notify`.
The response policy follows that characteristic's write-without-response flag.
HA/Bleak owns connection setup, adapters, proxies and MTU negotiation. There is
no app-owned PIN, challenge, authentication or bonding exchange to reproduce.

Generic packets are one command byte on the selected Nordic mode, otherwise
`6e 01 side code sum8`. Exit and three menu probes have exact separate prefixes.
Variable outbound frames are `6e length 20 ... sum8`; inbound extended frames
place length after `20` or `21`. Every final integer is masked to eight bits.
Clock synchronization uses timestamp/calendar from one snapshot and timezone
from a second snapshot, with whole-hour offset truncation.

Complete inbound frames are destructively split before dispatch. Earlier emitted
state survives a later parser/callback failure; failing and later local frames
are not replayed. Retained incomplete bytes receive a 500 ms timer only after
successful dispatch. Common frames retain their individual checksum and
chunk behavior. Zero-length nonprogress input is rejected safely.

Wi-Fi, cloud/accounts, provisioning, network administration, firmware maintenance,
desk-only data and phone camera/torch/PDF infrastructure are explicitly excluded.
See the [disposition summary](../apk-analysis/dispositions/row121-hjbed.md) for exact
source identities, exclusions and safety deviations. Real users can validate
physical effects, actual ATT behavior and firmware acceptance after beta/release;
no maintainer hardware acquisition is required.

## Notes

### Analysis provenance

HJBed 2.1.2 / code 21200 uses artifact set
`bd3a5e96393fb32be9059fbb9a0eae5639deb7f0d761b4a27b3b382433c4d291`.
Exact evidence, reachability, exclusions and safety dispositions belong in the
[disposition summary](../apk-analysis/dispositions/row121-hjbed.md) and
[complete ledger](../apk-analysis/dispositions/row121-hjbed.json).
