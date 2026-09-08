# RMControl product profiles

**Status:** Source-verified against RMControl 21.3.7
(`com.richmat.rmcontrol2`), hardware unverified. The independent evidence
reconciliation is accepted; this document does not claim the PR is merged.

These opt-in profiles preserve the app's exact product choices and individual
button commands. They are separate from the existing [Richmat profiles](richmat.md).
An app product code identifies a remote layout, not a guarantee that every bed
using the same Bluetooth service supports the same controls.

## Configuration

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

The controller discovers the selected transport's actual service, writable
characteristic and notification role. It does not broaden automatic discovery
to every device advertising a shared Bluetooth service.

## Controls and reported state

Standard movement, presets, memory programming, massage and lighting appear
where the selected catalog supports them. Additional catalog actions are exposed
as **disabled-by-default buttons**. Enable the relevant entities in the device's
entity list. Their names retain the app getter/context and occurrence number
where needed to distinguish variants. Long-press actions have separate buttons;
held movement uses cancellable repeats and protocol-specific release cleanup.

This includes supported combined/extra motor commands and less common heating,
fan, airbag, anti-pinch, aroma, music and sleep actions. It does not invent
parameterized controls merely because the shared library can parse a report.
Phone flashlight, menus, headings, desk-only and sofa-specific controls are
excluded.

Sensors and binary sensors are added when their corresponding state is first
reported, rather than creating permanently unknown entities for every catalog.
Diagnostics retain the selected product, transport, capability replies, decoded
state, supported alarm action names and all received alarm records. Reported
numeric values without proven units are deliberately unitless. A numbered motor
is not silently relabeled as a particular physical axis.

RGB starts unknown until a color report arrives. Where supported, the light
timer offers **Always On** and **1 through 15 minutes**. Always On uses the app's
`ff ff` timeout representation. A generic light capability alone is not a promise
of RGB support. Color and timer controls require the app's light acknowledgment
and selected strip flag. PARN accepts only its eight source-defined colors,
listed as exact RGB tuples in diagnostics; other colors are rejected.

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

`weekdays` uses `monday` through `sunday`; it is not a raw bit mask. An optional
`side` accepts `left`, `right` or `both` for paired-bed targeting. Replacing a slot
changes the alarm stored on the bed, not merely a Home Assistant automation.

A **single alarm is a countdown**, not a wall-clock alarm or time-sync operation.
The separate synchronization protocol encodes timezone offsets in whole hours,
truncated toward zero. Half-hour and quarter-hour offsets cannot be represented
fully; this is a source-proven limitation, not an automatic adjustment by HA.
New alarm creation resolves the current selected product's effective command,
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

The service also accepts the paired-bed `side` field. The time mode deliberately
does not claim seconds or minutes where the artifact does not establish that
unit. Configuring count/time is not equivalent to enabling the feature.

This service requires the app's BLE sleep-monitoring metadata, a received sleep
advertisement event and one of its six supported selectors: HNRN, HQRN, HSRN,
HURN, M7RN or MJRN. The connection setup queries sleep discovery only for the
ten source-listed BLE sleep products. A generic snore state report is not enough
to activate automatic intervention.

## Evidence and validation boundary

The commands, decoders, HA entry points and exact product/menu/reply gates are
implemented from the independently accepted evidence composition. Do not interpret the service
list as a promise that every profile supports those features. A rejected operation
must not be worked around by choosing an unrelated profile.

The [implementation ledger](../apk-analysis/row018-rmcontrol-implementation.md)
tracks the remaining gates. The
[specialized evidence record](../apk-analysis/row018-rmcontrol-specialized-evidence.md)
preserves the original report, corrected runtime inventory, independently verified
packet order and subsequent source interpretation corrections. Original APKs and
analysis outputs remain machine-local and unchanged.


Head and foot massage strength actions appear as intensity up/down controls
when the selected product provides both directions. A product with only a
strength-increase action retains its named product button; it does not expose
that action as a zone on/off toggle.
