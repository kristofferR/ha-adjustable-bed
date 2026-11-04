# Good Vibe Sleep

**Status:** ❓ Needs testing (static app evidence only)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Choose the exact product or remote shown in Good Vibe Sleep. Shared Bluetooth services do not identify a model.
- The shipped catalog supplies 848 admitted normal-product/configuration choices and 27 remote/image aliases. The [complete profile index](../apk-analysis/dispositions/row116-goodvibe/inventory.csv) retains every accepted selector, including excluded selectors.
- Independent sleep sensors use case-sensitive `RM-` (type 1) or `HJ-` (type 2) name prefixes. Add the sensor's own Bluetooth address with the corresponding sleep profile.
- FWRM and WFRM are desk products and are excluded.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Good Vibe Sleep](https://play.google.com/store/apps/details?id=com.richmat.goodvibesleep) 2.0.1 (20103) | `com.richmat.goodvibesleep` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Exact app-labelled actions, with each product's gesture and operand |
| Position Feedback | ❌ No calibrated position controls; raw typed events remain visible |
| Memory Presets | ✅ Product-specific short/long gestures and local memory mode |
| Massage | ✅ Exact controls in the selected app layout |
| Lights | ✅ Product-gated actions, RGB settings and duration choices |
| Alarms | ✅ Product-gated single and repeat alarms, slots 1–7 |
| Snore settings | ✅ Where the normal product's settings menu admits them; separate type 2 sleep controls |
| Sleep sensors | ✅ Independent type 1/type 2 sessions, live values and direct BLE reports |
| Paired sides | ✅ Only sides listed by the selected product |
| Firmware / Wi-Fi / Cloud | ❌ Outside the integration's direct BLE bed boundary |

## Protocol Details

### Normal-product GATT

| Service UUID | Write characteristic | Generic format |
|--------------|----------------------|----------------|
| `0000fee9-0000-1000-8000-00805f9b34fb` | `d44bc439-abfd-45a2-b575-925416129600` | Framed |
| `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | Single byte |
| `0000e0ff-3c17-d293-8e48-14fe2e4da212` | `00000002-3c17-d293-8e48-14fe2e4da212` | Framed |
| `0000fff0-0000-1000-8000-00805f9b34fb` | `0000fff2-0000-1000-8000-00805f9b34fb` | Framed |
| `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe2-0000-1000-8000-00805f9b34fb` | Framed |
| `0000fee9-0000-1000-8000-00805f9b34bb` | `d44bc439-abfd-45a2-b575-925416129622` | Framed |

The first exact TX with the `write` property is retained. RX is the first `notify` characteristic in an accepted service, without nominal RX equality. The last accepted service sets framed/single-byte mode even when TX/RX came from an earlier service. Missing usable TX/RX fails setup. Writes prefer without-response when TX supports it.

### Sleep GATT

Both sleep types accept `0000e0ff-3c17-d293-8e48-14fe2e4da212` and `2320567c-05cf-6eb4-c341-772851827e1b`.

| Profile | TX selection | RX selection | Writes |
|---------|--------------|--------------|--------|
| Type 1 / `RM-` | First write-without-response property | First notify property | Without response |
| Type 2 / `HJ-` | `00000002-3c17-d293-8e48-14fe2e4da212` with write | `00000003-3c17-d293-8e48-14fe2e4da212` with notify | With response |

The additional service is live BLE support. Its enum name does not turn it into excluded network provisioning. Nominal `26f66991-68ee-c2be-444d-b95c3f2dc38a` characteristic fields are not used for selection.

### Packet Format

Normal generic frames are `6e 01 side operand sum8`, except exact special query prefixes. The legacy service emits only the operand. Short, long and legacy-short operands are distinct per descriptor. Each is listed in the [complete command table](../apk-analysis/dispositions/row116-goodvibe/commands.csv).

Settings records are `6e 20 len domain command operation data sum8`, where `len` counts the whole frame. The [Richmat codec](richmat.md) builds the same command, light, colour and countdown frames byte for byte, but places `len` before `20` in its records. Good Vibe therefore stays a standalone controller rather than a Richmat profile.

Sleep JSON uses insertion-ordered `id`, `cmd`, `val` and UTF-8 encoding:

```text
00 seq 01 00 ((n+7)&ff) 00 00 11 03 43 55 44 lenLo lenHi JSON
```

`n` is the JSON byte length. Ordinary IDs cycle 1–254. There is no ordinary sleep checksum or CRC. Each packet is chunked using the current link's MTU minus three, bounded by 512 bytes.

## Detection / Setup

1. Choose Good Vibe Sleep and the exact app product/configuration or remote alias. Name matches offer app hints and do not replace another identified receiver.
2. Choose the Home Assistant Bluetooth adapter or proxy that reaches that physical address.
3. Add each independent sleep device separately, selecting type 1 or type 2. A normal product's `sleep_advertisement_name` status attribute can identify the app's requested sensor name.

Single-address pairs expose only the selected product's admitted sides. A combined command uses native side 2 when the product offers it; products offering only sides 0 and 1 receive left then right commands on the same BLE link.

The source app has no app-owned PIN, challenge, encryption or bond request. This does not establish that firmware never requires OS bonding. Home Assistant retains its normal adapter, proxy and setup infrastructure.

## Commands

### Motor Control, Presets, Memory and Massage

The [complete command table](../apk-analysis/dispositions/row116-goodvibe/commands.csv) contains every accepted command ID, exact framed/legacy alternatives, source owner and implementation disposition. The [catalog](../../custom_components/adjustable_bed/goodvibe_catalog.py) contains 1,393 current layout/alarm action definitions and five controls constructed inside the Y6RM menu. Controls retain their app labels without assigning a physical motor to a name alone.

| Command | Bytes | Description |
|---------|-------|-------------|
| Generic short action | `6e 01 S C sum8` or `C` | `C` is the exact selected descriptor's short/legacy-short operand |
| Generic long action | `6e 01 S L sum8` or `L` | `L` is the exact descriptor's reachable long operand |
| Release / STOP | `6e 01 S 6e sum8` or `6e` | Sent by gestures that define release; no inferred firmware guarantee |
| Exit limit | `6e 02 01 00 71` or `00` | Connection startup |
| Check clock | `6e 08 01 01 78` or `01` | Startup menu query |
| Check light | `6e 0a 00 01 79` or `01` | Startup menu query |

The five-model memory predicate applies only to E3RM, GXRM, JDRM, JFRM and JGRM, with the GXRM/TV exception. The app's memory control sends its ordinary operand before changing local mode. Forced-long details and local release/hold choices remain separate from physical state.

### Y6RM Menu Controls

Y6RM's menu expands into these exact app-labelled controls. They use the common frame `6e 01 S operand sum8`, or the single operand on the legacy service.

| App label | Operand | Gesture |
|-----------|---------|---------|
| Head Up | `24` | Sustain |
| Foot Up | `26` | Sustain |
| Head Down | `25` | Sustain |
| Foot Down | `27` | Sustain |
| Motor Reset | `31` | Short press |

The sustained controls refresh every 100 ms; a released control sends `6e` through the same common builder. These labels do not establish physical axes for an untested bed.

### Lights

| Command | Bytes | Description |
|---------|-------|-------------|
| Duration | `6e 0b HH LL sum8` | Seconds, big-endian; zero maps to `ff ff` |
| Color | `6e 0c ff R sum8 6e 0d G B sum8` | Both records in one write buffer |
| Close bed light | `6e 01 S 75 sum8` or `75` | Dedicated close action, no extra release |

Full-gamut products offer 0–900 seconds in 60-second steps. Eight-color products offer 0/300/600/900 seconds; RNRN offers 0/1800/3600/14400/28800. The eight colors are `(255,255,0)`, `(0,255,0)`, `(0,127,255)`, `(0,0,255)`, `(139,0,255)`, `(255,255,255)`, `(255,0,0)` and `(255,165,0)`.

### Massage Countdown

Products with the bottom massage countdown offer off, 10, 20 and 30 minutes. Their exact operands are `5e`, `5f`, `63` and `61`, respectively: `6e 01 S operand sum8`, or the single operand on the legacy service. The dedicated slider callback sends once without a release frame.

### Alarms and Snore Settings

| Command | Bytes | Description |
|---------|-------|-------------|
| Single alarm low | `6e 05 minuteLow 00 sum8` | First write |
| Single alarm high | `6e 06 minuteHigh action sum8` | Second write |
| Repeat alarm | `6e 20 0d 05 01 01 slot 00 hour minute action mask sum8` | Monday bit 7 through Sunday bit 1; enabled bit 0 |
| Delete repeat alarm | `6e 20 08 05 02 01 slot sum8` | Slots 1–7 |
| Query repeat alarms | `6e 20 08 05 01 00 00 9c` | Retains returned records |
| Query sleep name | `6e 20 08 06 03 00 00 9f` | Normal product's independent sensor name |
| Snore switch | `6e 20 09 06 01 01 00 enabled sum8` | Normal settings menu |
| Snore configuration | `6e 20 0a 06 05 01 selector 00 value sum8` | Selector 1: count 1–30; selector 2: time 5–30 in steps of five |
| Query snore configuration | `6e 20 09 06 05 00 00 00 a2` | Count/time query |
| Query snore switch | `6e 20 08 06 01 00 00 9d` | Switch query |

Single-alarm date and current time are truncated to minutes. A nonpositive difference adds one day once. A single-alarm preference is saved only on its ACK. Repeat alarms use an explicit slot or the smallest unoccupied slot in the observed list. Automatic slots are checked and retained for all targets before any target writes. The normal snore menu excludes HNRN, HQRN, HSRN, HURN, M7RN and MJRN.

Time sync sends `6e 20 0c 08 02 01 epochBE32 offsetHours sum8`, followed by `6e 20 0d 08 03 01 yearMinus1970 month day hour minute second sum8`.

### Sleep Controls and Reports

| Action | Type 1 JSON command/value | Type 2 JSON command/value |
|--------|---------------------------|---------------------------|
| Set time | `s_time:{ts,tz}` | `s_time:{ts,utc}` |
| Query time | No packet | `q_time:null` |
| Query part | `s_part:null` with retained query selector | `q_part:null` |
| Set part | `s_part:part` | `s_part:part` |
| Live query | `q_realtime:{type:0,time:1}` | Same |
| Report metadata | `q_report:{part,type,y,m,d}` | Same |
| Report continuation | `q_report:{part,type,y,m,d,allow:1}` | `q_report:{allow:1}` |
| Query sensitivity | No setter/query packet admitted | `q_sens:null`; removed setter has no packet |
| Query anti-snore | No packet | `q_antiSnore:null` |
| Set anti-snore | No packet | `s_antiSnore:{L:[enabled,8,4],R:[enabled,8,4]}` |

Use `adjustable_bed.goodvibe` for these settings and queries. The action validates every target before writing. The dashboard card includes app controls, local side selection, light durations, snore numbers and sleep state. A report action automatically requests metadata and continuation, then waits for the typed result. Day is type 1 and month is type 2; report parts are 1 or 2. Setting a type 1 sleep part accepts 1 or 2; type 2 accepts 11, 12 or 13. Type 2 startup selects the shipped default 12. Report operations replace live monitoring to protect the shared response selector.

## Position Feedback / Notifications

- Normal frames retain the shipped checksum/framing and event order. Incomplete normal data expires after 500 ms. Malformed bounds and zero-length records are rejected without fabricating state.
- Sleep ordinary assembly uses byte 12 and strips one 14-byte header. Type 1 routes by the retained request; type 2 uses the artifact's ordered text-contains routing. Incoming bytewise text is separate from outbound UTF-8.
- Report continuation preserves the type-specific whole-chunk versus per-chunk-header rule, then bounded GZip decoding and typed day/month schemas. Type 2 day schema selection retains the algorithm-version comparison and first-component-1 exception.
- Live values preserve separate L/R occupancy, heart, respiration, movement and snore fields. Type 2 invalid markers retain earlier values; malformed new updates do not partially replace one side.
- Full typed event and report records remain in status attributes. The integration does not claim medical or physical validation of these values.

## Command Timing

- Sustained normal controls first send after 100 ms and repeat every 100 ms. Short actions send once and release on completion/cancellation. Long/short-and-long gestures use a 3-second threshold and do not acquire an invented release frame. Releasing a short-and-long card control before that threshold sends its short action; explicit STOP and aborted operations do not.
- Source normal queue timing is a 100 ms backlog scheduler, not a universal minimum write gap. Home Assistant serializes commands and owns finite cancellation and release cleanup.
- Sleep writes await each chunk. Monitoring polls every 2 seconds and retains its user intent through an unexpected disconnect. Manual disconnect, unload and explicit stop end that intent and cancel owned resources.
- The app's unretained 100 ms timer and active split futures are not firmware guarantees. Home Assistant stops unsent chunks on cancellation and does not recreate the app's timer or callback ownership leaks.

## Notes

Hardware, ATT delivery, firmware acceptance and physiological interpretation remain unverified. Real users may validate them after beta/release; maintainer hardware acquisition is not required.

See the [discovery and implementation ledger](../apk-analysis/dispositions/row116-goodvibe.md) for source bindings, hashes, exclusions and audit limits.
