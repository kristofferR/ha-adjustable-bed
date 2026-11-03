# RMControl product profiles

**Status:** ❓ Needs testing (source-verified against RMControl 21.3.7, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

These opt-in profiles preserve the app's exact product choices and individual
button commands. They are separate from the existing [Richmat profiles](richmat.md).

## Known Models

- Beds whose RMControl product code is in the app's catalog. An app product
  code identifies a remote layout, not a guarantee that every bed using the same
  Bluetooth service supports the same controls.
- BLE sleep products: the ten source-listed products get the sleep-discovery
  query; HNRN, HQRN, HSRN, HURN, M7RN and MJRN support automatic snore
  intervention.
- Standing-desk-only products (FWRM, WFRM) use a separate desk protocol and are
  rejected.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [RMControl](https://play.google.com/store/apps/details?id=com.richmat.rmcontrol2) 21.3.7 | `com.richmat.rmcontrol2` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Catalog movement with cancellable repeats and release cleanup |
| Position Feedback | ❌ (numbered motor reports are not relabeled as physical axes) |
| Presets / Memory Programming | ✅ Where the selected catalog supports them |
| Massage | ✅ Including head/foot intensity up/down where both directions exist |
| Lighting | ⚠️ RGB, **Always On** or **1 through 15 minutes** timer; gated on the light acknowledgment and strip flag |
| Extra Catalog Actions | ✅ **Disabled-by-default buttons** (heating, fan, airbag, anti-pinch, aroma, music, sleep, combined/extra motors) |
| Alarms | ⚠️ `adjustable_bed.rmcontrol_alarm`, product-gated |
| Automatic Snore Intervention | ⚠️ `adjustable_bed.rmcontrol_anti_snore`, six products |

## Protocol Details

**Format:** framed `6e 01 side command SUM`, or one opcode byte on Nordic UART

| Service | Write | Notify | Format |
|---------|-------|--------|--------|
| `0000fee9-0000-1000-8000-00805f9b34fb` | `d44bc439-abfd-45a2-b575-925416129600` | `d44bc439-abfd-45a2-b575-925416129601` | framed |
| `0000fee9-0000-1000-8000-00805f9b34bb` | `d44bc439-abfd-45a2-b575-925416129622` | `d44bc439-abfd-45a2-b575-925416129611` | framed |
| `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe2-0000-1000-8000-00805f9b34fb` | `0000ffe1-0000-1000-8000-00805f9b34fb` | framed |
| `0000fff0-0000-1000-8000-00805f9b34fb` | `0000fff2-0000-1000-8000-00805f9b34fb` | `0000fff1-0000-1000-8000-00805f9b34fb` | framed |
| `0000e0ff-3c17-d293-8e48-14fe2e4da212` | `00000002-3c17-d293-8e48-14fe2e4da212` | `00000003-3c17-d293-8e48-14fe2e4da212` | framed |
| `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | Nordic (one opcode byte) |

- The controller discovers the selected transport's actual service, writable
  characteristic and notification role. Exactly one known writable transport
  must be present.
- Writes use response unless the characteristic offers write without response.
- It does not broaden automatic discovery to every device advertising a shared
  Bluetooth service.

### Packet Format

- `SUM` is the low byte of the sum of the preceding bytes.
- `side` is the configured RMControl side: `left` 0, `right` 1, `both` 2.
- Extended frames are `6e len 20 domain command operation data SUM`, with
  `len` = data length + 7 on outbound frames (notifications do not place the
  length before `20`).

### Connection Setup

1. Subscribe to the notification role.
2. Send ExitLimit (`6e 02 01 00 71`).
3. With an alarm catalog, send the two time-synchronization frames.
4. For a BLE sleep product, send the sleep-advertisement query.
5. Send Check Clock (`6e 08 01 01 78`) and Check Light (`6e 0a 00 01 79`).
6. Wait up to 5 seconds for the light, alarm and sleep-advertisement replies
   the product expects. Some beds omit optional replies; basic controls stay
   usable and late replies are accepted.

## Detection / Setup

In the integration's Richmat setup/options:

- Leave **RMControl product** (`rmcontrol_product`) empty to retain the existing
  Richmat behavior. Existing entries are not automatically migrated.
- To opt in, choose the exact product code used in RMControl. Do not select a
  similar-looking product to unlock unsupported controls. Empty catalogs remain
  empty, and standing-desk-only products are rejected.
- Set **RMControl side** (`rmcontrol_side`) to `left`, `right` or `both`. The
  default is `left`. This selects the app's command side, not a new Bluetooth
  address. A paired-bed service's optional `side` selects which paired controller
  receives the operation; it does not add a side byte to specialized packets.

## Controls and Reported State

Standard movement, presets, memory programming, massage and lighting appear
where the selected catalog supports them. Additional catalog actions are exposed
as **disabled-by-default buttons**. Enable the relevant entities in the device's
entity list.

- Button names retain the app getter/context and occurrence number where needed
  to distinguish variants. Long-press actions have separate buttons; held
  movement uses cancellable repeats and protocol-specific release cleanup.
- This includes supported combined/extra motor commands and less common heating,
  fan, airbag, anti-pinch, aroma, music and sleep actions. It does not invent
  parameterized controls merely because the shared library can parse a report.
- Phone flashlight, menus, headings, desk-only and sofa-specific controls are
  excluded.
- Head and foot massage strength actions appear as intensity up/down controls
  when the selected product provides both directions. A product with only a
  strength-increase action retains its named product button; it does not expose
  that action as a zone on/off toggle.

Sensors and binary sensors are added when their corresponding state is first
reported, rather than creating permanently unknown entities for every catalog.
Diagnostics retain the selected product, transport, capability replies, decoded
state, supported alarm action names and all received alarm records. Reported
numeric values without proven units are deliberately unitless. A numbered motor
is not silently relabeled as a particular physical axis.

### Lighting

- RGB starts unknown until a color report arrives.
- Where supported, the light timer offers **Always On** and **1 through 15
  minutes**. Always On uses the app's `ff ff` timeout representation.
- A generic light capability alone is not a promise of RGB support. Color and
  timer controls require the app's light acknowledgment and selected strip flag.
- PARN accepts only its eight source-defined colors, listed as exact RGB tuples
  in diagnostics; other colors are rejected.

## Commands

Movement, preset, memory, massage, light and extra-action opcodes are per
product: they come from the RMControl catalog in
[`richmat_profiles.py`](../../custom_components/adjustable_bed/richmat_profiles.py),
with separate short, long-press and Nordic short opcodes. The frames that carry
them are shared. Extended frames below are listed as `domain command operation`,
then their data bytes.

### Catalog Actions

| Command | Frame | Description |
|---------|-------|-------------|
| Action (framed) | `6e 01 side cmd SUM` | Short or long-press opcode |
| Action (Nordic) | `cmd` | Nordic short opcode, or the long-press opcode |
| STOP / release | `6e 01 side 6e SUM` (Nordic: `6e`) | Sent after every sustain press with a fresh cancel event |

A few catalog items replace the `6e 01 side` prefix with their own:

| Prefix | Catalog items |
|--------|---------------|
| `6e 02 01` | ExitLimit |
| `6e 08 01` | Check Clock |
| `6e 0a 00` | Check Light |
| `6e 15 01` | Check Music |
| `6e 1a 00` | Check Aroma |
| `5e 1a 00` | Check Mattress |
| `6e 21 00` | Check Snore |
| `6e 22 00` | Check Speech |
| `6e 9a c0` | Check Detection |
| `6e 88 c2` | Send Start Detection |
| `6e 9a 00` | Query Version |
| `6e 9a 10` | Version-one current bed mode |
| `6e 9a 30` | Version-one motor 1-4 current angle |
| `6e 9a a0` | Version-one current massage mode |
| `6e 9a b0` | Version-one current bed light status |

### Lights

| Command | Frame |
|---------|-------|
| Light timer | `6e 0b HH LL SUM` (seconds; 0 sends `ff ff`, Always On) |
| Light colour | `6e 0c ff R SUM` + `6e 0d G B SUM` |

### Alarms

| Command | Frame |
|---------|-------|
| Single (countdown) alarm | `6e 05 lo 00 SUM`, then `6e 06 hi cmd SUM` |
| Cancel single alarm | The same frames with minutes 0 and command 0 |
| Repeating alarm create/replace | Extended `05 01 01`: `id 00 hour minute cmd repeat_mask` |
| Repeating alarm delete | Extended `05 02 01`: `id` |
| Repeating alarm query | Extended `05 01 00`: `00` |
| Time sync, Unix time and zone | Extended `08 02 01`: Unix time (4 bytes, big-endian) + whole-hour offset |
| Time sync, local calendar | Extended `08 03 01`: `year−1970 month day hour minute second` |

`repeat_mask` uses bit 7 for Monday through bit 1 for Sunday.

### Snore Intervention

| Command | Frame |
|---------|-------|
| Switch | Extended `06 01 01`: `00 enabled` |
| Configure | Extended `06 05 01`: `01` (count) or `02` (time), `00`, value |
| Query switch / configuration | Extended `06 01 00`: `00` / `06 05 00`: `00 00` |
| Sleep-advertisement query | Extended `06 03 00`: `00` |

## Alarm service

Use `adjustable_bed.rmcontrol_alarm`, selecting the device and operation. It
requires an explicitly selected RMControl profile and the appropriate supported
alarm capability. Action names must come from that device's diagnostics
`alarm_actions` list, not raw bytes or another product's catalog. Ambiguous or
absent actions are rejected before writing.

| Operation | Additional fields | Effect |
| --- | --- | --- |
| `single` | `minutes` (1..65535), `action` | Run the selected action after a countdown measured in minutes. |
| `cancel_single` | None | Cancel the countdown alarm. |
| `repeat` | `alarm_id` (1..7), `time`, `weekdays`, `action` | Create or replace the selected repeating-alarm slot at local time, with minute precision. |
| `delete` | `alarm_id` (1..7) | Delete that repeating-alarm slot. |
| `query` | None | Request repeating-alarm records; received records appear in state/diagnostics. |
| `sync` | None | Send current Home Assistant time, timezone and local calendar values to the supported alarm subsystem. |

- `weekdays` uses `monday` through `sunday`; it is not a raw bit mask.
- An optional `side` accepts `left`, `right` or `both` for paired-bed targeting.
- Replacing a slot changes the alarm stored on the bed, not merely a Home
  Assistant automation.
- A **single alarm is a countdown**, not a wall-clock alarm or time-sync
  operation.
- The separate synchronization protocol encodes timezone offsets in whole hours,
  truncated toward zero. Half-hour and quarter-hour offsets cannot be represented
  fully; this is a source-proven limitation, not an automatic adjustment by HA.
- New alarm creation resolves the current selected product's effective command,
  including its override. It does not reproduce the app's separate restoration
  path that can discard an override.

The app's single and repeating alarm pages are distinct. An alarm acknowledgment
and nonempty selected `alarmList` normally enable the menu; PNRN has the app's
explicit initial-menu exception. The exact product flag then chooses single or
repeating operations. An empty action list never permits arbitrary alarm actions.
Time synchronization has its own condition, a nonempty `alarmList`, and is also
performed during connection setup independently of the repeating-alarm flag.

## Automatic snore intervention

Use `adjustable_bed.rmcontrol_anti_snore`. This is separate from moving to the
anti-snore preset position.

| Operation | Additional fields | Effect |
| --- | --- | --- |
| `switch` | `enabled` (boolean) | Enable or disable supported automatic snore detection/intervention. |
| `configure` | `mode` (`count` or `time`), `value` (0..255) | Set the app's intervention count or time value. |
| `query` | None | Request the enable state and intervention configuration. |

- The service also accepts the paired-bed `side` field.
- The time mode deliberately does not claim seconds or minutes where the
  artifact does not establish that unit.
- Configuring count/time is not equivalent to enabling the feature.

This service requires the app's BLE sleep-monitoring metadata, a received sleep
advertisement event and one of its six supported selectors: HNRN, HQRN, HSRN,
HURN, M7RN or MJRN. The connection setup queries sleep discovery only for the
ten source-listed BLE sleep products. A generic snore state report is not enough
to activate automatic intervention.

## Notifications

Frames must start with `6e` and carry a valid additive checksum; unknown or
malformed frames have no effect.

| Frame | Meaning |
|-------|---------|
| `6e09010078`, `6e0e00037f`, `6e1a000189`, `6e16010186`, `6e90c101c0`, `6e2100008f` | Alarm, light, aroma, music, detection and anti-snore capability |
| `6e07010177` / `6e07010278` | Single alarm added / cancelled |
| `6e23018416` / `6e23008415` | Locked / unlocked |
| `6e23a06e9f` | Anti-snore stop music |
| `6e 90 selector value SUM` | Protocol version, bed mode, motor (number, status, angle), massage mode/strengths, music, detection status, component diagnostics |
| `6e 20 len …` | Extended reports: diagnostics, sleep advertisement, RGB, light timer, white light, lock, press mode, fan, aroma, heating, massage, motor travel, motor angle, alarm records |

The receive buffer assembles fragmented or coalesced notifications and discards
a partial frame after 500 ms without new data, as the app's timer does.

## Command Timing

| Operation | Timing |
|-----------|--------|
| Write queue | At least 100 ms between writes, including release |
| Sustain press | Configured pulse count at 100 ms, then STOP |
| Short and long press | One write |
| Capability replies at connect | Up to 5 seconds (integration readiness budget, not an on-wire interval) |

## Notes

### Evidence and validation boundary

The commands, decoders, HA entry points and exact product/menu/reply gates are
implemented from the independently accepted evidence composition. Do not
interpret the service list as a promise that every profile supports those
features. A rejected operation must not be worked around by choosing an
unrelated profile.

### Analysis provenance

- Source-verified against RMControl 21.3.7 (`com.richmat.rmcontrol2`),
  implemented on `release/4.0`, hardware unverified. The independent evidence
  reconciliation is accepted.
- The [implementation ledger](../apk-analysis/row018-rmcontrol-implementation.md)
  tracks the remaining gates.
- The [specialized evidence record](../apk-analysis/row018-rmcontrol-specialized-evidence.md)
  preserves the original report, corrected runtime inventory, independently
  verified packet order and subsequent source interpretation corrections.
  Original APKs and analysis outputs remain machine-local and unchanged.
