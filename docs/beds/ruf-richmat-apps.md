# RUF, W.Silver, AMERICANSTAR, Bailey and TX apps

**Status:** ❓ Needs testing (app-derived support; physical hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- RUF uses the fixed six-button BQRM remote, including names recognized by its app.
- W.Silver Products: 508 current selectors, including its B6RM, Y2RM, U1RM,
  A6RM, UFRM, A8RM, UVRM, O1RM, DIRM, FJRM, AWRM, AXRM, JPRM and ACRN choices.
- AMERICANSTAR: 532 usable selectors; Bailey's Bed Control: 572 usable selectors;
  TX: 495 usable selectors. Setup lists each app's own selectors. A selector
  identifies the app layout, not a confirmed physical actuator count.
- The separately selected sleep receiver advertises a name containing the
  case-sensitive text `HJ_Bed`. RUF does not expose that receiver.
- The older AMERICANSTAR Comfort Bed profile is a different app and controller.
  See [ORE Comfort Bed](ore-comfort-bed.md).

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [RUF \| Betten Motor 2](https://play.google.com/store/apps/details?id=com.desarketing.ruf_betten_motor2) 1.1.8 | `com.desarketing.ruf_betten_motor2` |
| ✅ | [W.Silver Products](https://play.google.com/store/apps/details?id=com.richmat.wsilver2) 1.1.19 | `com.richmat.wsilver2` |
| ✅ | [AMERICANSTAR](https://play.google.com/store/apps/details?id=com.richmat.americanstar) 1.0.0 | `com.richmat.americanstar` |
| ✅ | [Bailey's Bed Control](https://play.google.com/store/apps/details?id=com.richmat.bailey2) 2.1.21 | `com.richmat.bailey2` |
| ✅ | [TX](https://play.google.com/store/apps/details?id=com.richmat.tx) 1.0.0 | `com.richmat.tx` |

## Features

| Feature | RUF | W.Silver / AMERICANSTAR / Bailey / TX |
|---------|-----|--------------------------------------|
| Motor Control | Head, foot, combined | Exact selected model's axes and buttons |
| Memory Presets | No | Model-specific recall and separate save buttons |
| Massage | No generic massage page | Model-specific buttons and reply/version-gated intensity sliders |
| Lights | No generic light page | Model buttons, reply-gated RGB and timeout controls |
| Position Feedback | No exposed motor sliders | App angle sliders when the model and protocol version provide them |
| Diagnostics | Reply-gated | Reply-gated |
| Waist Mattress | Powered initialization required | Powered initialization required |
| Normal Mattress | No | Explicit opt-in plus powered initialization; W.Silver, AMERICANSTAR and TX only |
| Countdown / Indexed Alarms | No | Model and reply-gated |
| Weekly Alarms | No | Model `hasNewAlarm` plus a nonempty alarm position list |
| Sleep Monitoring / Intervention | No | Separate receiver, explicit app selection |
| App PIN / Authentication | No app handshake found | No app handshake found; OS or firmware link security remains unverified |

## Detection / Setup

1. Select the exact app name in setup. Shared Bluetooth services and four-character
   names cannot identify which app layout a bed uses.
2. Choose **Model from the Bluetooth name** or an explicit model. Automatic model
   selection reads the first four characters of the raw Bluetooth name, ignoring
   case. `QRRM` and `Cool Touch` names require a model choice. RUF always selects
   its fixed BQRM remote.
3. Only choose **with normal mattress** if your W.Silver, AMERICANSTAR or TX bed
   actually provides that function. The normal app constructors do not enable it.
   The apps can consume a saved Boolean enabling this page, but the origin and
   prevalence of old saved records are unknown. HA's explicit choice represents
   that capability choice; it does not import or infer an app's saved history.
   A new, valid, powered normal initialization is also required. VER1/VER2 pages
   do not enable normal-mattress controls.
4. For the separate sleep device, add **W.Silver / AMERICANSTAR / Bailey / TX sleep
   receiver**, choose its app, and select that receiver's address. Its GATT roles
   differ from the bed remote. Device attributes must arrive before settings can
   be changed. A source-single receiver in single mode cannot switch user mode.

Each physical address has its own app, model, capabilities and notification
buffer. Two-address pairs use Home Assistant's side routing. These profiles do
not claim that the app's local group byte is universal left/right addressing.
Close the phone app before connecting from HA.

## Protocol Details

The first present service in this ordered table selects the fixed roles.

| Order | Service UUID | Write Characteristic | Notify Characteristic |
|-------|--------------|----------------------|-----------------------|
| N1 | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` |
| W1 | `0000fee9-0000-1000-8000-00805f9b34fb` | `d44bc439-abfd-45a2-b575-925416129600` | `d44bc439-abfd-45a2-b575-925416129601` |
| W2 | `0000fee9-0000-1000-8000-00805f9b34bb` | `d44bc439-abfd-45a2-b575-925416129622` | `d44bc439-abfd-45a2-b575-925416129611` |
| W3 | `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe2-0000-1000-8000-00805f9b34fb` | `0000ffe1-0000-1000-8000-00805f9b34fb` |
| W4 | `0000fff0-0000-1000-8000-00805f9b34fb` | `0000fff2-0000-1000-8000-00805f9b34fb` | `0000fff1-0000-1000-8000-00805f9b34fb` |

If fixed roles lack suitable properties, fallback visits the first service other
than `1800`/`1801`, retaining the last writable and last notifying characteristic.
A dual write/notify characteristic supplies the write role in this fallback.
Missing fixed characteristics reject an incomplete known service.

### Packet Format

| Family | Format |
|--------|--------|
| Remote button | `6e 01 00 OPCODE SUM8` |
| Legacy absolute angle | `6e 88 (30 OR axis-bits<<2) abs(angle) SUM8` |
| Legacy motor mode | `6e 88 (10 OR mode-bits<<2) 00 SUM8` |
| Legacy massage intensity | `6e 88 a0 ((foot AND 7)<<3 OR (head AND 7)) SUM8` |
| VER2 absolute angle | `6e 20 0a 01 03 01 axis 00 abs(angle) SUM8` |
| VER2 motor mode | `6e 20 09 0b 02 01 00 mode-index SUM8` |
| VER2 massage intensity | `6e 20 09 02 01 01 zone intensity SUM8` |
| Normal mattress | `5e side property value SUM8` |
| Waist mattress | `5e 03 property value SUM8` |

`SUM8` is the low byte of the sum of all preceding bytes. The controller builds
immutable frames and serializes commands. VER2 Map2 controls require the exact
`2i`, `3i` or `4i` model and a `0002` version reply, in Bailey or AMERICANSTAR.
Other models retain their own primary map. No bytes are inferred from a brand.

### Write Mode

The apps do not override the Android characteristic's runtime write type.
HA chooses write-without-response when advertised, otherwise write-with-response.
Notification subscription uses Home Assistant/Bleak's descriptor handling.
No app-specific MTU request, BLE PIN or cryptographic handshake is added.

## Commands

### Motor Control

These are the fixed RUF remote's commands. The other apps use their selected
model's exact mappings, which can assign the same opcode to a different axis.

| Command | Bytes | Description |
|---------|-------|-------------|
| Head up | `6e01002493` | Held movement |
| Head down | `6e01002594` | Held movement |
| Foot up | `6e01002695` | Held movement |
| Foot down | `6e01002796` | Held movement |
| Both up | `6e01002998` | Held movement |
| Both down | `6e01002a99` | Held movement |
| Release | `6e01006edd` | Fresh, uncancelled cleanup write |

### Presets and Memory

Only controls present in the selected app/model/page are exposed. A save button
is separate from recall; a long-code field alone never enables a held command.

| Catalog action | Mode-zero frame | Caveat |
|----------------|-----------------|--------|
| Flat | `6e010031a0` | Some model pages hold this command at their own interval |
| Zero gravity | `6e010045b4` | Exposed as a preset only with a matching app label |
| Anti-snore | `6e010046b5` | Model-specific |
| TV | `6e010058c7` | Model-specific |
| Lounge | `6e010059c8` | Model-specific |
| Memory 1 / 2 / 3 recall | `6e01002e9d` / `6e01002f9e` / `6e0100309f` | Contiguous slots only |
| Memory 1 / 2 save | `6e01002b9a` / `6e01002c9b` | The catalog must contain the save control |
| Memory 3 save | `6e01002d9c` or `6e0100b322` | Exact app/model mapping; Bailey preserves its B3 mapping |
| Memory 4 / 5 recall | `6e0100b221` / `6e0100f463` | Model-specific |

### Lights, Massage and Diagnostics

| Command | Bytes or formula | Gate |
|---------|------------------|------|
| Light toggle | `6e01003cab`, then release | Model button |
| RGB | `6e0cff R SUM1` followed by `6e0d G B SUM2` in one 10-byte write | LED reply/page |
| Light timeout | `6e0b HH LL SUM8`; `HH LL=ffff` for always on | LED page 0–300 seconds; button-light page 0–15 minutes |
| Start diagnostics | `6e88c210c8` | Diagnostic capability reply |
| Stop diagnostics | `6e88c220d8` | Diagnostic capability reply |
| Smart set lock toggle | `6e010084f3`, no release | Model's legacy smart-set-lock control |
| Aroma timing | `6e 1b/1c/1d value 00 SUM8`, 150 ms between writes | Model and aroma reply |

Massage buttons, timers, heat, resets and additional app-labelled actions use
only their app/model catalog bindings. Slider ranges come from that model's
entities; feedback clamps to those ranges. A checksum or GATT completion does
not prove that a physical operation succeeded.

### Mattress Settings

| Normal property | Values |
|-----------------|--------|
| `01` Pressure | `01/02/03` low/medium/high |
| `02` Heat level | `00` off, `01/02/03` low/medium/high |
| `03` Heat duration | `01/02/03/04` = 2/4/6/8 hours |
| `04` Heat area | `00/01/02/03` = off/back/legs/both |
| `05` Mode | `00/01/02/03/04` = off/sleep/wake/decompress/leg |
| `06` Pillow | `00/01/02` = stop/up/down; one movement write and explicit stop |
| `07` Pillow duration | `01/02/03` = 20/40/60 minutes |
| `09` Sleep duration | `01/02/03` = 15/20/30 minutes |
| `0b` Alarm | Cancel `10`; save uses the 10-byte format below |

Normal `side` is `01` left or `02` right. No power or side-selection write is
invented from receive-only fields. Normal pillow cancellation always sends its
own `5e side 06 00 SUM8` release, without a generic `6e` release or held refresh.

| Waist property | Values |
|----------------|--------|
| `01` Mode | `00` off; `01..03` left relax/wake/decompress; `04..06` right; `07..09` both |
| `02/03/04` Heat left/right/both | `00/01/02/03` = off/2/4/8 hours |
| `05/06/07` Pressure left/right/both | `01/02/03` only |
| `08/09/0a` Duration left/right/both | `01/02/03` = 15/20/30 minutes only |
| `0b` Alarm | Cancel `10/11/12` left/right/both |

Bailey's waist pressure/duration zero values are feedback or builder-domain
values, not live UI controls. They are not offered as an Off command.

### Alarms

| Family | Bytes | Action |
|--------|-------|--------|
| Countdown | `6e05 minute-low slot SUM8`, then `6e06 minute-high action SUM8` | Existing `richmat_mh_alarm` action; slot 0 or model-gated 1–3 |
| Normal mattress | `5e side 0b repeat intensity H M nowH nowM SUM8` | `richmat_app_alarm`, family `mattress`; repeat `01` once / `02` daily |
| Waist mattress | `5e03 0b repeat side intensity H M nowH nowM SUM8` | Existing `richmat_mh_waist_alarm` action |
| Weekly save/toggle | `6e200d050101 slot bed H M mode week SUM8` | `richmat_app_alarm`, family `calendar` |
| Weekly delete | `6e2008050201 slot SUM8` | Set `delete: true` |
| Weekly query | `6e2008050100009c` | Sent before clock synchronization and after a change |

Weekly slots are 1–7. Mode is an exact position opcode in the selected model's
alarm list. New records use bed 0; editing preserves a received record's bed.
Week bits 7 through 1 mean Monday through Sunday; bit 0 enables the alarm.
An empty weekday list means once. Clock synchronization sends epoch seconds
(big endian) with whole raw timezone hours, then local year-minus-1970,
month/day/hour/minute/second. The app format loses DST/fractional-hour precision.

## Position Feedback / Notifications

- Version replies select legacy, `0001`, or the supported `0002` model path.
- `6e901`, `6e903`, `6e90a`, `6e904` carry motor mode, signed angle, paired
  massage intensities and memory-arrival state. The duplicate lock prefix is
  shadowed by massage in the app; no independent lock state is invented.
- `6e20` carries extended motor, range, massage, mode and calendar records.
  RUF's extended angle offset differs and does not expose a generic slider.
- Exactly 28-byte powered/checksummed `5e1a` initialization enables an explicitly
  selected normal mattress; exactly 31-byte powered/checksummed `5e1b` enables
  waist controls. `5e01/02` and `5e03` update the respective state families.
- Waist warmth initialization routes by property key; duplicate keys use the
  last reported value. Alarm and setting replies are asynchronous state, not
  correlated command acknowledgments.
- Malformed/partial frames are bounded before indexing. HA does not reproduce
  the phone apps' malformed-frame crashes, shared-buffer races or lossy fanout.

## Separate Sleep Receiver

**Service UUID:** `2320567c-05cf-6eb4-c341-772851827e1b`

**Write / Notify Characteristic:** `26f66991-68ee-c2be-444d-b95c3f2dc38a`

**Format:** `fa LENGTH CRC TYPE PAYLOAD`, where LENGTH is payload length + 2.
CRC covers TYPE and PAYLOAD, initial 0, reflected polynomial `8c`, no final XOR.

| Command | Exact bytes |
|---------|-------------|
| Heartbeat | `fa025e01` |
| Single-user mode | `fa059614010301` |
| Double-user mode | `fa057414010302` |
| Left intervention off / on | `fa055914010100` / `fa050714010101` |
| Right intervention off / on | `fa050c14010200` / `fa055214010201` |
| Attribute acknowledgment | `fa0330a512` |
| Time response | Type `05`, current epoch bytes reversed to little endian |

Type `11` reports Left/Right `HD` heart rate, `BD` breathing rate, `IsOnBed`
and `IsMove`. Rates are raw integers; a status equals true only when its value
is exactly 1. Type `12` attributes are acknowledged before JSON parsing.
`SDModeSet==2` means double, `LI/RI==1` enable intervention. Operation replies
are `a5 14 kind result`: kind 1/2 intervention is on for result 1; kind 3 is
 double for result 2. They are not generic success/failure codes. SDK write
completion is separate. No Wi-Fi or firmware administration action is exposed.

## Command Timing

| App/path | Refresh / release |
|----------|-------------------|
| RUF remote | 150 ms refresh; immediate explicit release |
| Bailey held controls | 80 ms refresh; 120 ms release |
| Bailey one-shot controls | One write; 100 ms natural completion release |
| W.Silver / AMERICANSTAR / TX | Per-widget refresh, usually 100 ms; 120 ms release |
| W.Silver / AMERICANSTAR CERM/ELRM structured Flat | Model catalog preserves 3000 ms KEEP interval |
| Legacy initialization | RUF/Bailey/AMERICANSTAR start at 100 ms; W.Silver/TX at 300 ms; another 300 ms before queries |
| Query spacing | Legacy/VER2 300 ms; VER1 400 ms |
| Separate sleep receiver | Subscribe after 1 second; heartbeat immediately after subscription, then every 5 seconds; 300 ms setting pacing |

W.Silver legacy initialization sends only Exit One Minute and Diagnostics.
TX omits Music USB from both initialization lists. Other apps include that
query in legacy/VER1 lists. Query completion is not a semantic acknowledgment.
HA's configured pulse count bounds movement and protocol-specific release is
attempted even after cancellation. Physical timing and firmware stop behavior
still require real-user confirmation after a beta or release.

## Notes

Wi-Fi provisioning, SSID/password settings, bed-network administration, cloud
accounts/reporting, firmware administration, phone speech recognition/audio,
and phone UI infrastructure are outside this integration's product scope.
BedTech is a separate follow-up and is not covered by these app profiles.

### Analysis provenance

| Package/version | Frozen artifact-set SHA-256 |
|-----------------|----------------------------|
| `com.desarketing.ruf_betten_motor2` 1.1.8 | `3883e4f4197e9bd91d9a52ffad4b45923b2c3b437fb4ab0b45856b311ad148ab` |
| `com.richmat.wsilver2` 1.1.19 | `876cf079b8d7ecf344010714b5178e7c376b444d591687e53d1e41081d421035` |
| `com.richmat.americanstar` 1.0.0 | `998d8c568339b504ffec7f7b062ef6f3f487db3fcd54ad8c7adf08152a8547c4` |
| `com.richmat.bailey2` 2.1.21 | `15bc635d9c98eefaa65355b5ef1942cfd9b61273e065bb87fe9a1f787fb7aed3` |
| `com.richmat.tx` 1.0.0 | `7454dd539701130569e55a5595ab285558286253cd050bde4f4fa00396d987ff` |
