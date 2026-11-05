# Sleep Number

**Status:** ⚠️ Partially tested (supported; the expanded BLE controls below are based on the SleepIQ 5.4.11 application, and physical validation of the new behavior remains pending)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed) with protocol detail and field testing from [@homer-aty](https://github.com/homer-aty) and [@JonGilmore](https://github.com/JonGilmore)

## Known Models

- Sleep Number Climate 360 bases advertising as `Smart bed *`
- Sleep Number FlexFit / FlexFit Smart bases using the Fuzion bamkey protocol
- Older Sleep Number BAM/MCR bases such as some i8 / 360 FlexFit 2 beds
  advertising the MCR UART service

| Transport | Service | Typical models |
|---|---|---|
| Fuzion | `09d23fae-90e6-44c2-95b6-0b3d0f1abf25` | Climate 360, FlexFit, FlexFit Smart |
| MCR | `ffffd1fd-388d-938b-344a-939d1f6efee0` | Older BAM / i8 / 360 FlexFit 2 |

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [SleepIQ](https://play.google.com/store/apps/details?id=com.selectcomfort.SleepIQ) 5.4.11 (code `1787576046`) | `com.selectcomfort.SleepIQ` |

## Features

Features are enabled from the connected bed's system or foundation capability
responses. A model name alone does not enable optional hardware.

| Feature | Fuzion | MCR |
|---|---|---|
| Head/foot movement and percentage targets | ✅ Yes (0-100%) | ✅ When foundation supports them |
| Position feedback | ✅ Queried | ✅ Foundation response |
| Foundation presets | ✅ Supported presets (Flat, Zero-G, Anti-Snore, TV) | ✅ Supported presets per side |
| Favorite memory | ✅ Slot 1: recall and save | ✅ `Favorite` foundation preset |
| Firmness (Sleep Number setting) | ✅ Configured side | ✅ Left and right |
| Favorite firmness and responsive air | ✅ Named service commands | ✅ Named service commands |
| Under-bed lighting | ✅ Level and timer | ✅ Foundation lighting and options |
| Core heating/cooling | ✅ Hardware dependent (unified entity; heating only on Heidi-equipped beds) | ❌ Not in this transport's exposed controls |
| Footwarming | ✅ Hardware dependent | ✅ Supported foundation |
| Temperature schedules | ✅ Named service commands | ❌ Not exposed by the app |
| Massage and outlets | ❌ Not exposed by this transport | ✅ Supported foundation commands |
| Presence polling | ✅ Left/right, disabled by default | ❌ Not exposed as occupancy sensors |

Use the normal cover, position, firmness, preset, lighting and climate entities
for everyday controls. Additional controls and structured queries are available
through [`adjustable_bed.sleep_number_command`](sleep-number-services.md),
including temperature programs, firmness favorites, responsive air, older-bed
massage, footwarming, outlets and foundation settings. The service validates
parameters and capabilities before executing requests; it does not accept raw
protocol bytes or arbitrary command strings.

## Connection and authentication

Sleep Number uses two distinct BLE transports. Detection selects the controller
from the advertised service, rather than assuming all models share one protocol.
The bed allows only one BLE client at a time, so close the phone app before
connecting.

### Fuzion

The application connects and discovers GATT services, requests bonding, reads
Auth, and only then subscribes to notifications. The integration follows that
order. It does not request pairing during the initial connection or repeatedly
pair a connection whose bond is still usable.

**Auth results:**

- Auth must return a 16-byte session UUID. The read uses the app's three
  attempts, each with a 10-second timeout.
- An empty or short value such as `0000` is an authentication failure, as is
  UUID one. These failures invalidate the cached bond marker, allow the next
  connection attempt to request pairing, and raise the pairing repair if
  recovery fails.
- The all-zero UUID means the connection limit was reached; it blocks startup
  without invalidating the bond or requesting re-pairing.
- None of these responses permit notification startup or commands. Successful
  notification subscription alone does not prove authentication.
- An ATT error 15 (`Insufficient encryption`) is an authentication failure, just
  like ATT error 5.

**Transport and bonding:**

- Recovery tracks the adapter or Bluetooth proxy that actually carried the
  connection. Pairing on the Home Assistant host does not establish a bond on a
  separate ESPHome proxy. Use the integration's pairing repair for the active
  transport and close the phone app before connecting.
- If the bed isn't discoverable, hold the side button until the indicator
  flashes blue to make it connectable.
- An authentication failure through an ESPHome proxy clears both the proxy's
  cached GATT table and Home Assistant's copy of it while the link is still up.
  `use_services_cache=False` does not bypass either cache.
- The next coordinator attempt and the setup and repair retries discover the
  real layout and verify the existing bond without pairing again, because
  re-pairing a bonded ESPHome device can fail with error 82.
- Only a second authentication failure through the same proxy clears the bond
  marker and requests pairing.
- A link that a one-connection bed must retain keeps its services and is not
  cleared.

> [!NOTE]
> Earlier documentation incorrectly stated that Fuzion never bonds. The 5.4.11
> application explicitly bonds after service discovery. This ordering matters
> for the proxy failures reported in #318 and the startup failures in #565 and
> #574.

#### Field evidence

- **#574:** the September 22 captures show that the ESPHome proxy completed
  pairing and retained a bond, while the subsequent Auth read returned zero
  bytes. Other GATT reads worked. That identifies the failed step but does not
  establish why the bed returned an empty Auth value.
- **#660:** support bundles from the same bed show four different handle layouts
  for the Fuzion service across ten days: same characteristics, different order.
  After a power outage, the ESPHome proxy kept serving the table it had cached
  in flash. The Auth read landed on another characteristic and returned 2 bytes,
  and notification subscriptions hit descriptors (`Write not permitted`) or
  encrypted values (`Insufficient encryption`). Every error matches the layout
  discovered after the user erased the proxy, so the bond itself was intact. The
  empty Auth value in #574 fits the same cause.
- **#318:** earlier releases forced OS pairing on every connection
  (`pair=True`), which made ESP32 / ESPHome Bluetooth proxies report
  `auth fail reason=82` and leave the connection wedged in the `ESTABLISHED`
  state, breaking every reconnect until the proxy was factory-reset.
- Regular support bundles now retain the latest setup/pairing HA trace and
  available proxy logs, including Auth outcome and read length, so this does
  not require a separate diagnostic HA build or manual debug-log download. The
  standard ESPHome API cannot report stored bond keys or link-security details;
  those fields require proxy firmware support.
- The runtime recovery correction does not establish successful Climate 360
  hardware operation.

### MCR

- MCR uses its own binary session binding. The integration persists a random
  nonzero 64-bit client identity and uses the addresses assigned by the bind
  response for subsequent frames. It does not derive the client identity from
  the bed's Bluetooth address or continue after a missing bind response.
- Basic BLE control works without OS-level pairing.
- MCR keeps its BLE connection open after startup. Idle disconnect,
  disconnect-after-command and timer-based auto-reconnect are disabled for this
  transport to avoid reconnect churn during its session handshake: older
  BAM/MCR firmware is sensitive to reconnect churn between the notify
  subscribe, init handshake, and follow-up reads. A dropped link reconnects on
  the next command.

## Protocol Details

### Fuzion / Climate 360 / FlexFit

**Service UUID:** `09d23fae-90e6-44c2-95b6-0b3d0f1abf25`
**BamKey UUID (write/notify):** `421e00f3-ae76-4c49-ab6e-39e4df4a5333`
**Auth UUID:** `8d4675a5-b5fa-42b2-b587-0ee71c46b709`
**Transfer Info UUID:** `e8d06e2a-c987-48f8-93a8-4d18d56b4337` (earlier releases primed it before occupancy reads; the integration no longer uses it)
**Bulk Transfer Notify UUID:** `0ec9a5a3-8ac3-4582-92f3-1666421f323d` (not used by the integration)
**Format:** `fUzIoN` framed bamkey blobs with CRC validation

- Fuzion reads Auth (`8d4675a5-b5fa-42b2-b587-0ee71c46b709`) before subscribing
  to BamKey (`421e00f3-ae76-4c49-ab6e-39e4df4a5333`) notifications. It does not
  subscribe to bulk transfer notifications (`0ec9a5a3-8ac3-4582-92f3-1666421f323d`).
- The logical command payloads are bamkey strings, `<BAMKEY> <arg1> <arg2> ...`.
  Text commands, including the trailing space on commands without arguments,
  are wrapped in CRC-checked `fUzIoN` frames.
- Frames are written to the BamKey characteristic without response. Writes
  respect the characteristic's supported chunk size.
- Session UUID notifications signal that a framed response is available to
  read; unrelated sessions are ignored and fragmented reads are assembled before
  parsing.
- Command acknowledgements and query responses depend on the
  notification/readback path, so the integration keeps the BamKey notification
  channel subscribed even when angle sensing is disabled.
- `head` is mapped to the integration's `back` actuator and `foot` is mapped to
  `legs`.

### BAM / MCR (older i8 / 360 FlexFit 2)

**Service UUID:** `ffffd1fd-388d-938b-344a-939d1f6efee0`
**Notify UUID:** `ffffd1fd-388d-938b-344a-939d1f6efee1`
**Write UUID:** `ffffd1fd-388d-938b-344a-939d1f6efee2`
**Format:** MCR binary frames with `0x16 0x16` sync bytes and Fletcher-style CRC

- Older BAM/MCR beds use a binary request/response protocol instead of BamKey
  text commands.
- Framed requests use assigned session addresses, integrity checks, response
  correlation and fragmented transport.
- On the wire, right is side 0 and left is side 1.
- Foundation and pump operations retain their distinct message layouts and
  capability checks.

## Detection

Auto-detection uses the unique Sleep Number service UUID for each protocol family:

- `09d23fae-90e6-44c2-95b6-0b3d0f1abf25` (Fuzion)
- `ffffd1fd-388d-938b-344a-939d1f6efee0` (MCR)

The bed-type list has one **Sleep Number: SleepIQ app, Fuzion (Climate 360,
FlexFit) and BAM/MCR (i8, 360 FlexFit 2) bases** row. When Home Assistant has
seen the advertisement, setup confirms the transport from its service without
asking; otherwise it asks which base the bed is, and a detected transport stays
one answer away. A Fuzion entry then asks its side; a BAM/MCR entry asks
nothing, since it exposes both sides. A model name alone never chooses the
transport, and existing entries are not moved to the other one. **Configure**
lists both transports under their own names.

Typical device names look like:

- `Smart bed 0074E7` (Fuzion)
- `64:DB:A0:07:DD:02` (MCR; the BLE name may just be the MAC address)

### Sides

- Fuzion entries control the selected side: the `auto` protocol variant defaults
  to the left side, `left` and `right` target that side explicitly.
- Paired entries bind commands to their selected side.
- A standalone MCR entry exposes both sides, with separate firmness, preset and
  supported motor controls.
- One side per Fuzion entry keeps the implementation compatible with the
  entity model while still exposing split-base control.

## Commands

The integration's everyday Fuzion entities use the bamkeys below. The complete
Fuzion catalogue, including temperature programs, is in the
[Fuzion discovery disposition](sleep-number-fuzion-disposition.md); the MCR
command and parameter list is in [Sleep Number BLE commands](sleep-number-services.md).

### Actuator Control

| Command | Bamkey | Description |
|---------|--------|-------------|
| Read head position | `ACTG <side> head` | Native percentage |
| Read foot position | `ACTG <side> foot` | Native percentage |
| Set head target | `ACTS <side> head <0-100>` | Percentage target |
| Set foot target | `ACTS <side> foot <0-100>` | Percentage target |
| Halt | `ACHA` | Global halt of every actuator |
| Movement status | `ACTM` | Per-actuator movement status for both sides |
| Current preset | `AGCP <side>` | Preset in progress |
| Homing state | `ACHG` | Homing progress |

The global `ACHA` halt can stop the other side of a split base too. The
integration does not invent a side-specific release from unused generated
methods.

> [!NOTE]
> Earlier versions of this document listed per-side `ACTH <side> head|foot`
> stops and said the integration avoided `ACHA`. The controller now sends the
> app's global `ACHA` for every stop, including on user release.

### Presets

| Command | Bamkey | Description |
|---------|--------|-------------|
| Flat | `ACSP <side> flat 0` | Preset, timer 0 |
| Zero-G | `ACSP <side> zero_g 0` | Preset, timer 0 |
| Anti-Snore | `ACSP <side> snore 0` | Preset, timer 0 |
| TV | `ACSP <side> watch_tv 0` | Preset, timer 0 |
| Favorite (memory 1) | `ACSP <side> favorite 0` | Recall the single native memory |
| Save Favorite | `ACPS <side> favorite <head> <foot>` | Saves the side's current actuator positions |

### Under-Bed Light

| Command | Bamkey | Description |
|---------|--------|-------------|
| Read light settings | `UBLG` | Level and timer |
| Set light level and timer | `UBLS <off\|low\|medium\|high> <minutes>` | Untouched field is preserved |

### Bed Presence

| Command | Bamkey | Description |
|---------|--------|-------------|
| Read occupancy | `BAMG [{"bamkey":"LBPG","args":"left"},{"bamkey":"LBPG","args":"right"}]` | Both sides in one grouped request |
| Read occupancy (fallback) | `LBPG <side>` | Used per side when the bed reports `BAMG` as unknown |

### Sleep Number Setting

| Command | Bamkey | Description |
|---------|--------|-------------|
| Read Sleep Number setting | `SNCG <side>` | Adjustment status, ambient and user Sleep Number |
| Set Sleep Number setting | `PSNS <side> <5-100>` | Starts an asynchronous adjustment, steps of 5 |

> [!NOTE]
> Earlier versions of this document listed `PSNG <side>` for reading the
> setting. The controller now reads firmness from `SNCG`.

### Climate / Thermal Controls

The SleepIQ app internally names the two thermal hardware modules **Frosty**
(the "Cooling Module", cooling-only) and **Heidi** (the "Core Temperature
Module", which supports both heating *and* cooling). Only one is typically
present on a given bed; Heidi is the more modern superset.

| Command | Bamkey |
|---------|--------|
| Check footwarming presence | `FWPG <side>` |
| Read footwarming state | `FWTG <side>` |
| Set footwarming level/timer | `FWTS <side> <off\|low\|medium\|high> <minutes>` |
| Check cooling-module (Frosty) presence | `CLPG <side>` |
| Read cooling-module mode | `CLMG <side>` |
| Set cooling-module mode/timer | `CLMS <side> <mode> <minutes>` |
| Check core-temperature-module (Heidi) presence | `THPG <side>` |
| Read core-temperature-module mode | `THMG <side>` |
| Set core-temperature-module mode/timer | `THMS <side> <mode> <minutes>` |

Mode values come from the SleepIQ app's `ThermalMode` enum:

- `off`
- `cooling_pull_low`, `cooling_pull_med`, `cooling_pull_high` (Frosty + Heidi)
- `cooling_push_high` (Heidi only, exposed as the `boost` preset)
- `heating_push_low`, `heating_push_med`, `heating_push_high` (Heidi only)

- Thermal and footwarming entities are created from the system configuration
  (`SYCG`) flags; the presence bamkeys remain available through
  `adjustable_bed.sleep_number_command`.
- Turning Frosty or Heidi off sends `timer=0` to match the SleepIQ app's
  behaviour. Footwarming keeps the current remaining timer when turned off, also
  matching the app.
- System capabilities come from `SYCG`.

## Home Assistant entities

| Entity | Transport | Notes |
|--------|-----------|-------|
| `Under Bed Lights` switch | Fuzion, MCR | |
| `Light Level` number | Fuzion | Values `0-3` |
| `Light Timer` select | Fuzion | `Off`, `15 min`, `30 min`, `45 min`, `1 hr`, `2 hr`, and `3 hr` |
| `Left Bed Presence` / `Right Bed Presence` binary sensors | Fuzion | Disabled by default because they require active polling over BLE |
| `Sleep Number Setting` number | Fuzion | Configured side |
| `Sleep Number Setting Left` / `Sleep Number Setting Right` numbers | MCR | |
| `Foundation Preset Left` / `Foundation Preset Right` selects | MCR | `Favorite`, `Read`, `Watch TV`, `Flat`, `Zero G`, `Snore`, as supported |
| `Climate` climate | Fuzion | Unified entity routed to whichever module the bed has. HVAC modes `off`, `cool`, and (Heidi only) `heat`; preset modes `low`, `medium`, `high`, and (Heidi only) `boost` |
| `Footwarming` climate | Fuzion | `low`, `medium`, and `high` presets |
| `Climate Timer` select | Fuzion | `30 min` through `10 hr` |
| `Footwarming Timer` select | Fuzion | `30 min` through `6 hr` |

- Occupancy polling sends a grouped `BAMG` request for both sides in one call,
  then publishes separate left/right binary sensors.
  The former single `Bed Presence` alias is removed once the per-side sensors
  exist.
- Implemented BAM/MCR operations include the init handshake, reading and setting
  left/right firmness, triggering left/right foundation presets, and reading and
  writing under-bed light state.

## Position Feedback

Position values are native percentages, not degrees, so the integration exposes
0-100 direct-position controls instead of degree-based sliders. Enable position
feedback in integration options to expose position sliders. Optional polling can
keep the BLE connection occupied, so leave it disabled if it interferes with
another controller.

### Fuzion

- For a single-address Fuzion pair, each position report belongs to the side
  that was queried. Commands refresh that side before releasing the command
  lock, and the side's entities receive each new reading immediately.
- With position feedback enabled, all articulation targets and preset entry
  points, including sliders, held controls and named service commands, monitor
  movement at the app's one-second interval.
- Targets use the selected actuator's `ACTM` status; presets use `AGCP <side>`.
  Both read the side's enabled `ACTG` axes and publish intermediate and final
  measured percentages, rather than leaving the initial position on screen until
  the next press (#623).
- Bluetooth response time adds to the interval; Fuzion does not stream actuator
  positions like Linak. Stop or a replacement command can cancel the refresh.
- Cancellation, failure and timeout send the global halt before releasing the
  command queue, then attempt bounded readback with a fresh cancellation event.
  Explicit Stop also refreshes both physical sides because Fuzion's halt is
  global.
- A 90-second integration timeout bounds the wait if the bed never reports
  completion; it is not a hardware movement deadline.
- Homing uses its separate `ACHG` progress state and reads both sides on
  completion; it does not infer progress percentages.
- Preset monitoring follows the current movement, without holding the command
  queue for a preset timer's countdown.

### MCR

- MCR movement performs its own status checks even with optional angle sensing
  disabled. Held controls send continued-adjustment requests; position targets
  and presets wait for stationary feedback.
- A target that stops short reports an error instead of treating command
  delivery as completed movement. Positions are read again after release,
  including cancellation.
- If MCR reports that it needs homing, use the selected side's **Flat** preset.
  Recovery is monitored and succeeds only after the homing flag clears. Other
  configuration, actuator and obstruction faults still block motion. The
  integration does not bypass those faults to force a reset.
- MCR presets retain the app's selected-side routing. A side selector does not
  guarantee mechanically independent movement on foundations with shared
  sections. Firmware/layout-specific reports that some presets move both sides
  remain pending real-user validation; there is no blanket whole-bed preset
  restriction.

## Notes

### Analysis provenance

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
