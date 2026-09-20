# Sleep Number

**Status:** Supported. The expanded BLE controls below are based on the SleepIQ
5.4.11 application; physical validation of the new behavior remains pending.

**Credit:** Reverse engineering by
[kristofferR](https://github.com/kristofferR/ha-adjustable-bed), with field reports
from [@homer-aty](https://github.com/homer-aty) and
[@JonGilmore](https://github.com/JonGilmore).

## Connection and authentication

Sleep Number uses two distinct BLE transports. Detection selects the controller
from the advertised service, rather than assuming all models share one protocol.

| Transport | Service | Typical models |
|---|---|---|
| Fuzion | `09d23fae-90e6-44c2-95b6-0b3d0f1abf25` | Climate 360, FlexFit, FlexFit Smart |
| MCR | `ffffd1fd-388d-938b-344a-939d1f6efee0` | Older BAM / i8 / 360 FlexFit 2 |

### Fuzion

The application connects and discovers GATT services, requests bonding, reads
Auth, and only then subscribes to notifications. The integration follows that
order. It does not request pairing during the initial connection or repeatedly
pair a connection whose bond is still usable.

Auth must return a 16-byte session UUID. A short value such as `0000` is invalid;
the all-zero and UUID-one values are explicit failure responses. A failed or
malformed Auth value keeps pairing verification incomplete and prevents
notification startup and commands. Successful
notification subscription alone does not prove authentication.

An ATT error 15 (`Insufficient encryption`) is an authentication failure, just
like ATT error 5. Recovery tracks the adapter or Bluetooth proxy that actually
carried the connection. Pairing on the Home Assistant host does not establish a
bond on a separate ESPHome proxy. Use the integration's pairing repair for the
active transport and close the phone app before connecting.

Earlier documentation incorrectly stated that Fuzion never bonds. The 5.4.11
application explicitly bonds after service discovery. This ordering matters for
the proxy failures reported in #318 and the startup failures in #565 and #574.

### MCR

MCR uses its own binary session binding. The integration persists a random
nonzero 64-bit client identity and uses the addresses assigned by the bind
response for subsequent frames. It does not derive the client identity from the
bed's Bluetooth address or continue after a missing bind response.

MCR keeps its BLE connection open after startup. Idle disconnect and
disconnect-after-command are disabled for this transport to avoid reconnect
churn during its session handshake.

## Controls

Features are enabled from the connected bed's system or foundation capability
responses. A model name alone does not enable optional hardware.

| Feature | Fuzion | MCR |
|---|---|---|
| Head/foot movement and percentage targets | Yes | When foundation supports them |
| Position feedback | Queried | Foundation response |
| Foundation presets | Supported presets | Supported presets per side |
| Firmness | Configured side | Left and right |
| Favorite firmness and responsive air | Named service commands | Named service commands |
| Under-bed lighting | Level and timer | Foundation lighting and options |
| Core heating/cooling | Hardware dependent | Not in this transport's exposed controls |
| Footwarming | Hardware dependent | Supported foundation |
| Temperature schedules | Named service commands | Not exposed by the app |
| Massage and outlets | Not exposed by this transport | Supported foundation commands |
| Presence polling | Left/right, disabled by default | Not exposed as occupancy sensors |

Use the normal cover, position, firmness, preset, lighting and climate entities
for everyday controls. Additional controls and structured queries are available
through [`adjustable_bed.sleep_number_command`](sleep-number-services.md),
including temperature programs, firmness favorites, responsive air, older-bed
massage, footwarming, outlets and foundation settings. The service validates
parameters and capabilities before executing requests; it does not accept raw
protocol bytes or arbitrary command strings.

Fuzion entries control the selected side (`auto` defaults to left). Paired
entries bind commands to their selected side. A standalone MCR entry exposes
both sides, with separate firmness, preset and supported motor controls.

Position values are native percentages, not degrees. Enable position feedback
in integration options to expose position sliders. Optional polling can keep the
BLE connection occupied, so leave it disabled if it interferes with another
controller.

MCR movement performs its own status checks even with optional angle sensing
disabled. Held controls send continued-adjustment requests; position targets and
presets wait for stationary feedback. A target that stops short reports an error
instead of treating command delivery as completed movement. Positions are read
again after release, including cancellation.

If MCR reports that it needs homing, use the selected side's **Flat** preset.
Recovery is monitored and succeeds only after the homing flag clears. Other
configuration, actuator and obstruction faults still block motion. The integration
does not bypass those faults to force a reset.

MCR presets retain the app's selected-side routing. A side selector does not
guarantee mechanically independent movement on foundations with shared sections.
Firmware/layout-specific reports that some presets move both sides remain pending
real-user validation; there is no blanket whole-bed preset restriction.

## Protocol behavior

Fuzion reads Auth (`8d4675a5-b5fa-42b2-b587-0ee71c46b709`) before subscribing to
BamKey (`421e00f3-ae76-4c49-ab6e-39e4df4a5333`) and bulk notifications
(`0ec9a5a3-8ac3-4582-92f3-1666421f323d`). Text commands, including the trailing
space on commands without arguments, are wrapped in CRC-checked `fUzIoN`
frames. Writes respect the characteristic's supported chunk size. Session UUID
notifications signal that a framed response is available to read; unrelated
sessions are ignored and fragmented reads are assembled before parsing.

Actuator targets use `ACTS`; explicit halt uses the app's global `ACHA` command.
That halt can stop the other side of a split base too. The integration does not
invent a side-specific release from unused generated methods. Firmness is read
from `SNCG`; system capabilities come from `SYCG`.

MCR receives notifications on `ffffd1fd-388d-938b-344a-939d1f6efee1` and writes
on `ffffd1fd-388d-938b-344a-939d1f6efee2`. Its framed requests use assigned
session addresses, integrity checks, response correlation and fragmented
transport. On the wire, right is side 0 and left is side 1. Foundation and pump
operations retain their distinct message layouts and capability checks.

## Evidence and discovery disposition

The clean-room analysis and independent audit covered the complete application,
both BLE stacks, generated command catalogs, call sites and decompiler failures.
The frozen report remains machine-local with the APK and decompilation output.

- Package: `com.selectcomfort.SleepIQ`, version `5.4.11`, code `1787576046`.
- APK SHA-256: `710b7dfd536007fc4812ad9a16402be3c1bf882cfc27fa9214ad72154bf36f5f`.
- Frozen `REPORT.SHA256` digest: `1c751b8ba76fd89d85eb0fb96f20d1f7fbc40171e3c3e3a7c59be3d36463475d`.
- [Fuzion discovery disposition](sleep-number-fuzion-disposition.md).
- [MCR discovery disposition](sleep-number-mcr-disposition.md).

These ledgers distinguish implemented controls, internal transport behavior,
unreachable generated methods and explicit exclusions. Wi-Fi/account
provisioning, firmware/file transfers, destructive factory operations and cloud
report export are outside the integration's bed-control scope. Hardware testing
is deferred to users of the beta or release; static protocol evidence does not
establish compatibility with every firmware/model combination.

This supplemental 5.4.11 analysis does not replace the separately frozen 5.4
acquisition item or silently change its completion status.
