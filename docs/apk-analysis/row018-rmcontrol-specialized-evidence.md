# Row 018 specialized implementation evidence

This is a **post-freeze implementation comparison and interpretation correction**,
not another clean-room report. It preserves the accepted reports and raw evidence.
Hardware behavior remains unverified. The integration must gate each feature on
the selected product's reachable UI or an appropriate device response, not merely
the presence of a shared-library builder.

## Evidence identity

All paths below are relative to the machine-local, ignored
`disassembly/output/phase4-early/` directory:

- `com.richmat.rmcontrol2-21.3.7-20260827` (H): original frozen full report and
  its `work/blutter/asm/`, `work/blutter/objs.txt`, and focused
  `work/evidence-notification-{common,dispatch,extra}.txt` source extracts.
- `com.richmat.rmcontrol2-21.3.7-20260906-comparison-001` (C): accepted composite
  report, manifest SHA-256
  `3038c935d219550968b21a2a5c8f363d17aac4ef38f668fb5f58a3e4d9bc745d`.
- `com.richmat.rmcontrol2-21.3.7-20260908-packet-check-001` (P): separately frozen
  ordinary-frame correction. Its `report/ANALYSIS.md` and reproducer establish
  side-before-command and the 18 exceptional prefixes.
- `com.richmat.rmcontrol2-21.3.7-20260908-scalar-check-001` (S): fresh, frozen
  factory metadata, manifest
  `80522a5e45182f611985aa15d0a3fc22e430be6896b095de38b8b2c92d7552c4`.
  All 18,688 typed cells have independent native-instruction checks. The empty
  factory case is not a selectable integration product.
- `com.richmat.rmcontrol2-21.3.7-20260908-scalar-review-001`: independent
  acceptance of S and the complete evidence composition, manifest
  `63b09f74e06b8591de3314c0bf4ee2dca020b86a6b73cee389a369c5904acb25`.
  Its pinned selector join, caller gates and precedence discharge the earlier
  scalar/menu dependency gap without changing original reports.

Source addresses below identify Dart AOT routines, not repository code offsets.
The packet helpers and literal tests are committed; original artifacts remain
machine-local. Nothing in this document supersedes unrelated accepted findings.

## Corrections and packet construction

`richmat_library_utils/product/device_instruct_util.dart` is abbreviated DIU.
All sums below are the low eight bits of the sum of preceding bytes.

| Domain | Source-proven behavior and correction | Evidence anchor |
|---|---|---|
| Ordinary action | `6e 01 side command sum`, not command before side. Nordic sends only the resolved command. Exceptional prefixes use P's exact action identity table. | P; DIU `getFunctionInstruct` `0x7754f0` |
| Light timer | `6e 0b high low sum`, big-endian seconds. Zero sends `ff ff`, not `00 00`. | DIU `getLightSecondFunctionInstruct` `0x77ce24` |
| RGB | Concatenated `6e 0c ff R sum` and `6e 0d G B sum`. No assumed initial color. | DIU light-color builder following `0x77ce24` |
| Single alarm | This is **countdown minutes plus action**, not a wall-clock sync or alarm mode. Send low-minute `6e 05 low 00 sum` before `6e 06 high action sum`. Cancel uses `(0, 0)`. | `alarm_page_model.dart`: `sendAddClock` `0x770820`, countdown conversion call; wrapper `0x770988`; DIU high `0x7709fc`, low `0x771808`; cancel `0x772328` |
| Repeating alarm | `6e 0d 20 05 01 01 id 00 hour minute action repeat_mask sum`. Bean fields are offsets `7,f,17,1f,27,2f`, not a nonexistent second `b` field. UI writes second field zero; its wider firmware meaning is not established. | `repeat_alarm_details_page.dart` `0x78a18c` through `0x78a1c8`; DIU `getAddRepeatAlarm` `0x78a460`, length insertion `0x78a794` |
| Repeating action | New creation uses selected detail override when present, otherwise enum short value. The separate restore path's override loss does **not** justify sending enum defaults for a newly specified action. | `repeat_alarm_details_page.dart` `0x78a0a0` through `0x78a0cc`, stored at `0x78a1c0` |
| Alarm slots/repeat | App allocates slots 1 through 7. Monday is mask bit 7 through Sunday bit 1. Public packet API accepts the complete byte rather than inventing meaning for every reserved/control bit. | slot search `0x78afb0`; repeat builder `0x78a87c`; weekday enum objects `a89d41` through `a89c81` |
| Alarm delete/list | Delete `6e 08 20 05 02 01 id sum`; list `6e 08 20 05 01 00 00 sum`. | DIU delete `0x78b3e0` and immediately following list builder |
| Alarm time/zone | Ordered Unix/zone `6e 0c 20 08 02 01 [BE32 Unix seconds] zone sum`, then calendar `6e 0d 20 08 03 01 year_minus_1970 month day hour minute second sum`. Zone is signed whole hours, truncated toward zero, masked to one byte. Fractional offsets are not fully represented. | DIU `getAlarmSyncZoneFunctionInstruct` `0x781c0c`; timestamp divisions `0x781c74`; zone `0x781f20`; calendar DateTime-parts extraction in same routine |
| Anti-snore configuration | `6e 0a 20 06 05 01 mode 00 value sum`, where `mode=1` means count and `mode=2` means time. This is **not** an enable boolean and its false branch is not zero. No unproven duration unit is attached. | DIU `0x786488`, boolean lowering `0x786510` through `0x786524`; page callers `0x7863f4`, `0x786c78`; response decoder command 5 |
| Anti-snore enable | Separate `6e 09 20 06 01 01 00 enabled sum`, boolean encoded 1/0. Config query `6e 09 20 06 05 00 00 00 sum`; enable query `6e 08 20 06 01 00 00 sum`. | DIU switch `0x787214`, `0x7872b4`; query builders following repeating-alarm builders |
| Sleep advertisement query | `6e 08 20 06 03 00 00 9f`, including the length byte omitted by the historical interpretation. | `getSleepAdvNameInstruct` `0x781994`, length insertion `0x781a30`; caller gate `0x7818ac`..`0x781908` |

Packet-level limits reflect field representation: bytes 0..255, 16-bit values
0..65535, hour 0..23, minute 0..59. Higher-level UI/service limits can be narrower.
Both `ble_device_strip_page.dart` (`0x77d7a0`..`0x77d7b4`) and
`ble_device_eight_strip_page.dart` (`0x77c290`..`0x77c2a4`) prove a light-timer
slider from 0 to 900 seconds, with 15 divisions: no timeout, then 1..15 minutes.
The displayed minute label divides seconds by 60 (`0x77d6a0`), and sending uses
the unchanged seconds field (`0x77e08c`).

## Product and runtime gates

The fresh scalar extraction preserves all sixteen factory properties, but only
the shipped RMControl consumers justify runtime feature selection. Similarly
named shared-library properties are not aliases.

| Feature | Required source conditions |
| --- | --- |
| Alarm menu | The selected product's `alarmList` is nonempty and the common clock event has arrived; PNRN has an explicit initial-menu exception. `richmatAlarmList` is not a substitute. |
| Single versus repeating alarm | Once the alarm menu is reachable, `isSupportRepeatAlarm` selects the repeating page; false selects the single countdown page. `isRichmatSupportRepeatAlarm` does not select this page. |
| Light color and timer | Common light acknowledgment plus `isHaveLightStrip`. `bedLightDisplayType` selects the eight-color page for PARN, otherwise the panchromatic page. PARN's exact palette is enforced rather than accepting arbitrary RGB. |
| Sleep advertisement request | `rmcSleepMonitoringType == deviceSleepMonitoringBle`, not the similarly named alternate-library sleep field. The ten selectors are ETRN, G1RN, G2RN, GKRN, HNRN, HQRN, HSRN, HURN, M7RN and MJRN. |
| Automatic anti-snore | The sleep advertisement event, the BLE sleep gate, and one of the six app-listed selectors HNRN, HQRN, HSRN, HURN, M7RN or MJRN. A generic snore status packet alone does not enable it. |
| Initial alarm time sync | A nonempty selected `alarmList`; this initialization condition is independent of the repeating-alarm flag. |

Alarm-list dispatch is `getDeviceAlarmClockList` at `0x76d230`, GDT `ef45`,
field `7f`, named getter `0x9e0d74`. The settings alarm branch is
`0x781428`..`0x7814e0`; repeat-list request gate is `0x78db54`. Light settings
use the selected display enum at `0x78139c` and strip flag at `0x811cc8`.
The sleep setting callback checks the selected enum at `0x811794`.
These joins resolve the scalar appendix's intentionally unclaimed menu
dependencies without converting shared-library metadata into hardware claims.

Connection initialization composes the source's separate subscription and
settings phases: ExitLimit (`0x804da8`, before continuation `0x804dcc`),
conditional time sync (`0x78189c`), conditional sleep query (`0x781908`),
then Clock/Light polling (`0x78192c`). This is not claimed to be one
unconditional contiguous function in the APK.

## Notification contract

`Notification.kind` identifies the domain and `values` contains only fields
actually supplied. Missing fields do not reset previously known state. The
decoder rejects bad checksum, impossible lengths, and incomplete payloads.
In particular, the checksum is never accepted as a missing payload byte, even
where the app's length guard is permissive.

Extended notifications are **`6e 20 length domain command operation payload sum`**,
not the outbound length-before-20 layout. The dispatcher proves this at
`0x8054d4` and `0x80b550`. Operations 2 and 3 represent responses/reports in the
individual handlers; diagnostic channel reports do not impose that gate.
The stream assembler handles fragmentation, concatenation, noise, and invalid
checksums. It clears old partial input after the source's 500 ms timeout:
dispatcher `0x806e68`, `Duration@a9bdb1`, object duration `0x7a120` microseconds.
The caller also clears state across BLE sessions.

| Notification family | Semantic fields | H evidence |
|---|---|---|
| Exact common capability replies | `alarm`, `light`, `aroma`, `music`, `detection`, `anti_snore`; light alone does not prove every RGB/timer feature | common extractor and constant-pool reply strings |
| Exact common events | Single-alarm added/cancelled, lock state, anti-snore stop-music request | same common extractor |
| Common `6e 90` | Version; mode from low nibble of byte 2; motor number/status from byte 2 and angle from byte 3; packed three-channel massage strengths; music source/play/shake/Bluetooth; volume/vibration gear; detection start/stop/pause/repeat and component diagnostic status | common handler `0x807930` onward; massage `0x807d30`; diagnostics `0x8083e8`..`0x808d14`, enums `RMDeviceDetectionStatusType@a95621`..`a95681` and `RMDeviceDetectionCheckStatusType@a956a1`..`a95701`; volume `0x808d68` onward |
| Motor 1 | Travel/type, optional angle and monitor height; source divides travel by 10. Angle report gives position selector and angle, not an invented axis mapping. | `0x8107b0`, travel `0x810a24`, angle `0x810bf0` |
| Massage 2 | Head/foot strength pairs, mode, frequency, shake strength, power | `0x810028`, pairs `0x810100`; commands 2/4/5/6 |
| White light 3 / RGB 4 | White power; RGB tuple; timer seconds; motion switch; RGB power | `0x80fe88` / `0x80f878` |
| Alarm 5 | Slot, uninterpreted record flag, hour, minute, command, repeat mask | `0x80f57c` |
| Anti-snore 6 | Enable, get-off-bed detection enable, advertisement byte sequence, occupancy/sleep codes and stop-music condition, intervention count/time value | `0x80ee90`, commands 1..5 |
| Lock 7 / music 9 | Lock state; play, volume/silent value, Bluetooth and USB source | corresponding extra handlers |
| Diagnostics 10 | Named channel (motor/massage/white light/RGB/C65/music vibrator), payload bytes. The app emits channel plus frame, not named fault bits. | `_handleCheck` `0x80cd04`, dispatch `0x80b770` |
| Press mode 11 | Press mode, standard/split-control flag, same/split mode | `0x80b824` |
| Fan 14 / aroma 16 | Fan gear; aroma open status and timer value, without guessed timer unit | corresponding extra handlers; aroma `0x80d770` |
| Heating 17 | Position, off/unlimited/timed timer status, timer value, temperature value, model. No unproven temperature or time units. | `0x80d36c` |

### Boundaries that must not become invented capabilities

- Desk and OTA handlers do not establish bed features and remain excluded.
- The shared blanket handler (`0x80bab0`) reads several data fields but emits
  `RMDeviceBlacketDetailsModel` objects whose allocated size is **0x8**, with no
  stored model fields (`0x80bb7c`, `0x80bd6c`, `0x80becc`, `0x80bfec`,
  `0x80c314`, `0x80c438`, `0x80c61c`). This optimized, fieldless event path does
  not establish working blanket controls or named state in this APK. Invented
  temperatures/schedules or a full blanket platform are not justified by it.
- Motor travel reporting is not proof that every selected product has feedback,
  nor that a motor index corresponds to a specific adjustable-bed axis.
- Extended diagnostic payload bytes are preserved as channel-specific state.
  Common diagnostic statuses use the exact source enum labels (abnormal, normal,
  control-box malfunction, not plugged in), not inferred fault bits or repair
  recommendations. The high-nibble component selector remains numeric.
- These helpers do not assert product support. Platform/service wiring must use
  recovered product getters, negotiated capabilities, and evidence-backed action
  resolution, and the cluster disposition ledger owns final integration status.

## Verification

`tests/test_rmcontrol_protocol.py` uses independently written literal vectors for
all specialized builders, normal frame order, semantic updates, fragmented and
coalesced input, malformed frames, and parameter validation. These are artifact
conformance tests, not claimed physical BLE captures.
