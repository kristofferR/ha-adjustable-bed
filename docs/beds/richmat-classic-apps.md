# Avocado Eco Base, CoasterSleep, Forty Winks, Milemont and Superior

**Status:** ❓ Needs testing (accepted static APK evidence; hardware UNVERIFIED)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- App-selected four-character remote layouts, with separate package-local catalogs.
- Avocado Eco Base: 704 layouts; CoasterSleep: 715; Forty Winks: 725;
  Milemont: 700; Superior: 725. A compiled layout is not hardware confirmation.
- `FWRM` and `WFRM` select the separate desk controls.
- Forty Winks and Superior `ZRS6` are layout pickers. Select `ZRS6:CORN` or
  `ZRS6:CPRN` during setup/options to use the corresponding `CORN` or `CPRN`
  controls. The picker itself sends no bed command.
- Advertisement aliases and four-character manual selections are package-local.
  A shared service UUID does not identify the app, axes or physical side.

## Apps

| Analyzed | App | Package ID |
|---|---|---|
| ✅ | [Avocado Eco Base](https://play.google.com/store/apps/details?id=com.richmat.avocadoecobase) 1.0.4 (5) | `com.richmat.avocadoecobase` |
| ✅ | [CoasterSleep](https://play.google.com/store/apps/details?id=com.richmat.coastersleep) 1.0.10 (10) | `com.richmat.coastersleep` |
| ✅ | [Forty Winks](https://play.google.com/store/apps/details?id=com.richmat.fortywinks) 1.0.1 | `com.richmat.fortywinks` |
| ✅ | [Milemont](https://play.google.com/store/apps/details?id=com.richmat.milemont) 1.0.4 | `com.richmat.milemont` |
| ✅ | [Superior](https://play.google.com/store/apps/details?id=com.richmat.superior) 1.0.9 | `com.richmat.superior` |

These older resource-driven apps have an independent profile. Existing Richmat
and RMControl entries retain their own behavior.

## Features

| Feature | Supported |
|---|---|
| Motor and combined movement | ✅ Exact app-labelled controls per selected layout |
| Preset and memory recall/save | ✅ Per-node short/long gestures, memory-arm and Hold/Release gates |
| Massage | ✅ Bound levels, patterns, timers and popup choices |
| Lights | ✅ Bound controls, capability-gated RGB and timer settings |
| Aroma | ✅ Capability-gated settings; no reliable setting acknowledgements |
| Alarm | ✅ One selected layout action at the next requested wall-clock time |
| Desk | ✅ Target, unit, three recall buttons and fourth/reset button |
| Feedback | ✅ Capability, alarm, desk height/range/unit/error callbacks |
| Bed motor angles | ❌ No inferred angle or general command-ACK feedback |
| One-address Left/Right pairing | ❌ App mode labels do not establish physical side roles |
| Wi-Fi/cloud/network/group administration | ❌ Outside the direct BLE product boundary |
| Endurance test/motor mapping programming | ❌ Excluded for actuation safety |

## Protocol Details

### GATT routes

The first present fixed service wins. An incomplete first match fails; it does
not silently choose a lower-priority route.

| Order | Service UUID | Write characteristic | Receive characteristic | Encoding |
|---:|---|---|---|---|
| 1 | `0000fee9-0000-1000-8000-00805f9b34fb` | `d44bc439-abfd-45a2-b575-925416129600` | `d44bc439-abfd-45a2-b575-925416129601` | FRAMED |
| 2 | `0000fee9-0000-1000-8000-00805f9b34bb` | `d44bc439-abfd-45a2-b575-925416129622` | `d44bc439-abfd-45a2-b575-925416129611` | FRAMED |
| 3 | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | RAW |
| 4 | `0000fff0-0000-1000-8000-00805f9b34fb` | `0000fff2-0000-1000-8000-00805f9b34fb` | `0000fff1-0000-1000-8000-00805f9b34fb` | FRAMED |

The app also has an index-2 service fallback. HA requires the explicit fallback
option; it selects the last writable and receive-capable characteristics in
that service. A final read-only receive role still permits RAW controls, with no
invented reads, notification subscription or startup frame. HA always uses
current-session objects. Bleak manages notification
subscription and descriptors. The app never explicitly sets Android writeType;
HA uses write-with-response when supported, otherwise write-without-response.
That ATT choice is not a claim about the app's effective platform write type.

### Packet Format

| Path | Bytes |
|---|---|
| RAW | Selected decoded resource bytes, unchanged |
| FRAMED | `6e 01 M C SUM` with `SUM = (6e + 01 + M + C) & ff` |
| Direct settings | `6e OP A B SUM`, independent of ordinary vendor encoding |
| RGB | Two direct frames concatenated into one 10-byte write |

`M` is an actually available app-mode value. RAW ignores it. The ordinary
FRAMED sender uses only the first selected operand byte. Legacy short operands
can differ from current ones. All five shipped constructors leave the legacy
long getter null; the integration does not use that ignored XML attribute.

## Detection / Setup

1. Select the exact app by name in Adjustable Bed setup.
2. Select the four-character layout shown by that app. The list is scoped to
   the selected package; choose the layout explicitly if the name is ambiguous.
   Four-character app aliases resolve to their package-local layouts. Diagnostic
   TEST/RMCS layouts are excluded.
3. Enable the third-service fallback only when the bed uses that app path.
4. Use native app action buttons and the bounded hold service. Local mode,
   head/foot, memory-arm and Hold/Release selectors appear where present.
5. Call `adjustable_bed.richmat_classic` with `operation: query` to request
   settings capabilities. State and available alarm action IDs are in diagnostics.

The hardware meaning of a motor slot or Mode 1/2/3 is not inferred from a layout
name. `U3RM` remembers its third/fourth/fifth selector. `GVRM` foot selection
reaches a null legacy-long getter, so it cannot invent a movement packet.
Raw SelectView armed-save DOWN has no handler; it does not become a working
save operation by copying another profile's bytes.

## Commands

### Resource-selected controls

The following is an index of operands stored in the shipped five catalogs.
Values are sets across the exact layouts that bind each resource, not universal
capabilities. Each action still applies its node's tag, selector, visibility,
current mode and short/long gesture. FRAMED values are wrapped by the formula
above. The complete node tables ship in `cluster018_data/`.

| Bound resource | RAW short operand(s) | Current short operand(s) | Long operand(s) |
|---|---|---|---|
| `adjust_volume` | `b7` | `b7` | None |
| `com_first_up_once` | `3d` | `3d` | None |
| `com_lumbar_back_pos` | `91` | `91` | `92` |
| `com_lumbar_set_pos` | `91` | `91` | `92` |
| `com_motor1_2_down` | `2a`, `39` | `2a` | None |
| `com_motor1_2_up` | `29`, `36`, `38` | `29` | None |
| `com_motor2_down` | `27`, `41` | `27` | None |
| `com_motor_keep_30` | `90` | `90` | None |
| `com_msg1_intensity_dec` | `49`, `4a`, `4d` | `4d` | None |
| `com_msg1_intensity_inc` | `42`, `46`, `49`, `4c` | `4c` | None |
| `com_msg2_intensity_dec` | `4b`, `4f` | `4f` | None |
| `com_msg2_intensity_inc` | `44`, `48`, `4e` | `4e` | None |
| `com_msg_10min` | `39`, `47`, `49`, `4c`, `50`, `5f` | `5f` | None |
| `com_msg_10min_new` | `a1` | `a1` | None |
| `com_msg_20min` | `63` | `63` | None |
| `com_msg_20min_new` | `a2` | `a2` | None |
| `com_msg_30min` | `61` | `61` | None |
| `com_msg_30min_new` | `a3` | `a3` | None |
| `com_msg_aroma` | `3b` | `3b` | None |
| `com_msg_constant` | `3a`, `47` | `3a` | None |
| `com_msg_foot_intensity2` | `a5` | `a5` | None |
| `com_msg_head_intensity2` | `a4` | `a4` | None |
| `com_msg_intensity_dec` | `35`, `4b` | `35` | None |
| `com_msg_off` | `39`, `47`, `48`, `5d` | `39`, `47`, `48`, `5d` | `47` |
| `com_msg_off2` | `5a` | `5a` | None |
| `com_msg_off3` | `48`, `5e` | `48`, `5e` | `5e` |
| `com_msg_on` | `5d` | `5d` | `47` |
| `com_msg_speed_dec` | `37`, `49` | `37` | None |
| `com_msg_speed_inc` | `36`, `48` | `36` | None |
| `com_msg_wave1` | `49` | `49` | None |
| `com_msg_wave2` | `4a` | `4a` | None |
| `com_msg_wave3` | `4b` | `4b` | None |
| `com_relax_set` | `70` | `70` | `95` |
| `com_second_up_once` | `3e` | `3e` | None |
| `com_table_down` | `02` | `02` | None |
| `com_table_up` | `01` | `01` | None |
| `com_unwind_back` | `8c` | `8c` | `8d` |
| `com_unwind_set` | `8c` | `8c` | `8d` |
| `com_wakeup_back` | `93` | `93` | `94` |
| `com_wakeup_set` | `93` | `93` | `94` |
| `k_first_second_once_up` | `23` | `23` | None |
| `k_first_up_once` | `3d` | `3d` | None |
| `k_first_up_second_down` | `21` | `21` | None |
| `k_flat` | `31`, `32`, `38` | `31` | `84` |
| `k_flat2` | `6c` | `6c` | None |
| `k_flat_old` | `38` | `31` | None |
| `k_flat_old2` | `31` | None | None |
| `k_flat_sleep_back` | `f6`, `f7` | `f6`, `f7` | `f6`, `f7` |
| `k_flat_sleep_save` | `f6`, `f7` | `f6`, `f7` | `f6`, `f7` |
| `k_lock` | `31`, `84`, `d9` | `31`, `84`, `d9` | `84` |
| `k_lounge_back` | `32`, `59` | `59` | `65` |
| `k_lounge_back_old2` | `32` | `31`, `59` | None |
| `k_lounge_save` | `59` | `59` | `65` |
| `k_m1_back` | `2e`, `42` | `2e` | `2b` |
| `k_m1_back_old2` | `42` | `2e`, `3f` | `2b` |
| `k_m1_save` | `2b`, `2e`, `42`, `43` | `2b`, `2e` | `2b` |
| `k_m1_set_old2` | `42`, `43` | `2b`, `2e`, `40` | `2b` |
| `k_m2_back` | `2f`, `44` | `2f` | `2c` |
| `k_m2_back_old2` | `44` | `2f`, `44` | `2c` |
| `k_m2_save` | `2c`, `2f`, `44`, `45` | `2c`, `2f` | `2c` |
| `k_m2_set_old2` | `44`, `45` | `2c`, `2f`, `42` | `2c` |
| `k_m3_back` | `30` | `30` | `2d` |
| `k_m3_save` | `2d`, `30` | `2d`, `30` | `2d` |
| `k_m4_back` | `b2` | `b2` | `b3` |
| `k_m4_save` | `b2` | `b2` | `b3` |
| `k_m5_back` | `f4` | `f4` | `f5` |
| `k_m5_save` | `f4` | `f4` | `f5` |
| `k_motor1_2_down` | `2a`, `39` | `2a` | None |
| `k_motor1_2_down_old` | `39` | `2a` | None |
| `k_motor1_2_down_old2` | `37`, `39` | `2a` | None |
| `k_motor1_2_up` | `29`, `36`, `38` | `29` | None |
| `k_motor1_2_up_old` | `38` | `29` | None |
| `k_motor1_2_up_old2` | `36` | `29`, `3c` | None |
| `k_motor1_down` | `25`, `37`, `38` | `25` | None |
| `k_motor1_down_old` | `37` | `25` | None |
| `k_motor1_down_old2` | `38` | `25` | None |
| `k_motor1_up` | `24`, `34`, `35` | `24` | None |
| `k_motor1_up_old` | `34` | `24` | None |
| `k_motor1_up_old2` | `35` | `24` | None |
| `k_motor2_3_down` | `97` | `97` | None |
| `k_motor2_3_up` | `96` | `96` | None |
| `k_motor2_down` | `27`, `41` | `27` | None |
| `k_motor2_down_old` | `38`, `41` | `27` | None |
| `k_motor2_down_old2` | `41` | `27` | None |
| `k_motor2_up` | `26`, `36`, `37` | `26` | None |
| `k_motor2_up_old` | `35`, `36` | `26` | None |
| `k_motor2_up_old2` | `37` | `26` | None |
| `k_motor3_4_down` | `44` | `44` | None |
| `k_motor3_4_tilt_down` | `5c` | `5c` | None |
| `k_motor3_4_tilt_up` | `5b` | `5b` | None |
| `k_motor3_4_up` | `43` | `43` | None |
| `k_motor3_down` | `40`, `43` | `40` | None |
| `k_motor3_up` | `3f`, `42` | `3f` | None |
| `k_motor4_down` | `42`, `45` | `42` | None |
| `k_motor4_up` | `41` | `41` | None |
| `k_motor5_down` | `72` | `72` | None |
| `k_motor5_up` | `71` | `71` | None |
| `k_motor6_down` | `74` | `74` | None |
| `k_motor6_up` | `73` | `73` | None |
| `k_motor7_down` | `d1` | `d1` | None |
| `k_motor7_up` | `d0` | `d0` | None |
| `k_motor_keep_15` | `76` | `76` | None |
| `k_motor_reset` | `be` | `be` | None |
| `k_msg1_intensity_dec_old2` | `49` | `4d`, `5f` | None |
| `k_msg1_intensity_inc_old2` | `46` | `3c`, `4c` | None |
| `k_msg1_off_old2` | `47` | `47`, `5f` | None |
| `k_msg1_on_off_old` | `42` | `4c` | None |
| `k_msg2_intensity_dec_old2` | `4b` | `35`, `4f` | None |
| `k_msg2_intensity_inc_old2` | `48` | `34`, `4e` | None |
| `k_msg2_on_off_old` | `44` | `4e` | None |
| `k_msg_constant_old` | `47` | `3a` | None |
| `k_msg_first_on_off` | `32` | `32` | None |
| `k_msg_intensity1_old` | `4c` | `67` | None |
| `k_msg_intensity2_old` | `4d` | `4d` | None |
| `k_msg_intensity3_old` | `4e` | `68` | None |
| `k_msg_intensity_dec_old` | `4b` | `35`, `4f` | None |
| `k_msg_intensity_first` | `4c`, `67` | `67` | None |
| `k_msg_intensity_inc` | `34`, `48`, `4a` | `34` | None |
| `k_msg_intensity_inc_old` | `4a` | `34`, `4d` | None |
| `k_msg_intensity_third` | `4e`, `68` | `68` | None |
| `k_msg_mode` | `48`, `4a` | `48` | `47`, `5e` |
| `k_msg_mode_old2` | `4a` | `48` | None |
| `k_msg_off_old` | `39` | `5f` | None |
| `k_msg_off_old2` | `50` | `5f` | None |
| `k_msg_on_off` | `6f` | `6f` | None |
| `k_msg_on_old2` | `4c` | `5f` | None |
| `k_msg_pulse` | `38`, `46` | `38` | None |
| `k_msg_pulse_old` | `46` | `38`, `3c` | None |
| `k_msg_second_on_off` | `33` | `33` | None |
| `k_msg_speed_dec_old` | `49` | `37`, `4c` | None |
| `k_msg_speed_inc_old` | `48` | `36`, `4e` | None |
| `k_msg_wave` | `39`, `45` | `39` | `47` |
| `k_msg_wave_old` | `45` | `39` | None |
| `k_music_lock` | `d9` | `d9` | `84` |
| `k_next` | `d3` | `d3` | None |
| `k_on_off` | `d8` | `d8` | None |
| `k_previous` | `d2` | `d2` | None |
| `k_read_back` | `f2`, `f3` | `f2`, `f3` | `f2`, `f3` |
| `k_read_set` | `f2`, `f3` | `f2`, `f3` | `f2`, `f3` |
| `k_relax_back` | `70` | `70` | `95` |
| `k_reset` | `62` | `62` | None |
| `k_second_up_first_down` | `22` | `22` | None |
| `k_set_old` | `35` | `45` | None |
| `k_side_sleeper_back` | `ba` | `ba` | `bb` |
| `k_side_sleeper_set` | `ba` | `ba` | `bb` |
| `k_sleep_back` | `8e` | `8e` | `8f` |
| `k_sleep_set` | `8e` | `8e` | `8f` |
| `k_snore_back` | `46` | `46` | `69` |
| `k_snore_reset` | `cb` | `cb` | None |
| `k_snore_save` | `46`, `69` | `46`, `69` | `69` |
| `k_start_pause` | `d7` | `d7` | None |
| `k_sync_off` | `bd` | `bd` | `bd` |
| `k_sync_on` | `bc` | `bc` | `bc` |
| `k_tv_back` | `33`, `58` | `58` | `64` |
| `k_tv_back_old2` | `31`, `33` | `58` | None |
| `k_tv_save` | `58`, `64` | `58`, `64` | `64` |
| `k_ubl_off` | `3c`, `75` | `3c`, `75` | `75` |
| `k_ubl_on_off` | `36`, `3c`, `43`, `46` | `3c` | `75` |
| `k_ubl_on_off_old` | `43` | `3c` | None |
| `k_vibration` | `d6` | `d6` | None |
| `k_volume_down` | `d5` | `d5` | None |
| `k_volume_up` | `d4` | `d4` | `d4` |
| `k_wakeup_mode` | `85` | `85` | None |
| `k_yoga_back` | `f0` | `f0` | `f1` |
| `k_yoga_save` | `f0` | `f0` | `f1` |
| `k_zg2_back` | `6b` | `6b` | `6a` |
| `k_zg2_return` | `6b` | `6b` | `6a` |
| `k_zg2_save` | `6b` | `6b` | `6a` |
| `k_zg2_set` | `6b` | `6b` | `6a` |
| `k_zg_back` | `34`, `35`, `45` | `45` | `66` |
| `k_zg_back_old` | `32`, `34` | `45` | `66` |
| `k_zg_save` | `34`, `45`, `66` | `45`, `66` | `66` |
| `sleep1` | `86` | `86` | None |
| `swtch_music` | `b8` | `b8` | None |
| `turn_off_music` | `b9` | `b9` | None |

### Auxiliary settings

`A(op,a,b)` means the direct five-byte checksum frame above.

| Operation | Exact bytes / formula |
|---|---|
| Framed initialization | `6e02010071`, after 300 ms |
| Desk layout initialization/query | `6e94000002` immediately; FRAMED notification startup repeats it after 300 ms |
| Alarm query | `6e08010178`, only if the current alarm metadata list is nonempty |
| Lamp query | `6e0a000179` |
| Aroma query | `6e1a000088` |
| Alarm schedule | `A(05,delay low,00)`, then `A(06,delay high,action)` |
| Alarm cancel | `6e05000073`, then `6e06000074` |
| RGB | `A(0c,ff,R) || A(0d,G,B)` |
| Lamp slider | `A(0b,(minutes*60) high,(minutes*60) low)`; zero is `6e0bffff77` |
| Lamp Save | `A(0b,minutes high,minutes low)`, including zero `6e0b000079` |
| Aroma | `A(1b,00,mode2 minutes)`, `A(1c,00,mode3 minutes)`, `A(1d,00,pause hours)` |
| Massage popup | 15/30/45/toggle: `6e01005fce` / `6e010063d2` / `6e010061d0` / `6e01005ecd` |
| D1RM slider | 0/2/3/5 map to `5e`/`5f`/`63`/`61`; 1/4 pass through, using `A(01,00,value)` |
| D9RM slider | Same, except zero maps to `8b` |
| Desk units | `6e910000ff` cm / `6e91000100` inches |
| Desk target | `A(88,int(float32(display*10))/100,int(float32(display*10))%100)` with Java truncation |
| Desk buttons 1/2/3 | `6e96000408` / `6e9600080c` / `6e96001014` |
| Desk fourth button / newly reported error confirmation | `6e95000003` |
| Ordinary release | RAW `6e`; FRAMED `A(01,M,6e)` |

Alarms select one actual layout checkbox action. Delay is minutes until the
next chosen local time; equal or unset time means 1440 minutes. There are no
weekday/date or combined preset-plus-massage packets exposed. Lamp slider and
Save retain their different source units. Aroma ranges are 1-60, 1-60 minutes
and 1-12 hours; the source's uppercase consumer/two-byte getInt defect prevents
reliable aroma-save feedback.

## Position Feedback / Notifications

| Prefix | Consumer |
|---|---|
| `6e08` | Legacy desk height, base128; oldPack duplicate suppression |
| `6e90` | Modern desk height, base100, source unit-dependent float32 arithmetic |
| `6e94` / `6e92` | Desk unit, range, initial values; only 94 reveals modern controls |
| `6e97` | Desk error callback |
| `6e09010078` | Alarm capability |
| `6e0e00017d` / `6e0e00037f` | Lamp capability/state flags |
| `6e1a000189` | Aroma capability |
| `6e07010177` / `6e07010278` | Alarm set/cancel state |

Checksum, ordered prefix search and source 5/7/16-byte length branches apply.
The app can discard coalesced packets or throw on an empty short-buffer match;
HA reports malformed input without crashing the Bluetooth callback. Numeric
rounding preserves binary32 operations and promoted-float BigDecimal HALF_EVEN.
The Avocado URRM settings observer can starve lamp/aroma rows after its
suppressed alarm row. That package-specific gate is not applied to siblings.

## Command Timing

| Path | Timing |
|---|---|
| Ordinary worker | 150 ms normally; 110 ms for advertised TWRM/MLRM prefixes |
| Held release | 50 ms before release |
| Once / short | Payload, 150 ms, release |
| Long press | Persistent counter, floor(count/tick); normally 3000 ms, or node-specific 5000 ms |
| Alarm writes | 300 ms after each frame |
| Settings queries | 500 ms after each query |
| Aroma writes / RGB busy interval | 150 ms |
| Desk button refresh | 200 ms; bounded hold ends refresh, no invented release packet |

Mode0 resets the counter but retains the long-fired latch; mode4 releases and
resets both. A new DOWN does not reset either. HA cancellation ends pending
commands, always performs protocol-defined cleanup and does not resume a held
movement after disconnect or a lost UI owner. The app's unsafe queued/pending
continuations and stale cached-characteristic reuse are not reproduced.

## Notes

- No normal bed-angle, general massage-state, firmware, memory-count or
  authentication API is inferred from dormant constants.
- Wi-Fi, cloud/accounts, group/network administration and diagnostic endurance
  or motor-mapping configuration are outside the supported control surface.
- See the [complete discovery ledger](../apk-analysis/dispositions/row066-classic-richmat-apps.md)
  for accepted authority, exact member differences, exclusions, safety
  divergences, implementation status and deferred hardware validation.

### Analysis provenance

The accepted versions and all five artifact/report hashes are preserved in the
linked discovery ledger. Coaster's indivisible accepted aggregate and historical
six-cache-file FAIL remain explicit there. Static acceptance is not hardware
confirmation.
