# Configuration Guide

This guide covers v4 configuration. Options depend on the selected controller
and its reported capabilities; not every bed shows every field. v4 requires
Home Assistant 2026.9.0 or newer. Read the [migration notes](HA_2026_9.md) before
upgrading from v3.

## Table of Contents

- [Accessing Configuration](#accessing-configuration)
- [Basic Settings](#basic-settings)
- [Toggle-Only Under-Bed Lights](#toggle-only-under-bed-lights)
- [Advanced Settings](#advanced-settings)
- [Motor Pulse Settings](#motor-pulse-settings)
- [Protocol Variants](#protocol-variants)
- [Bed-Specific Settings](#bed-specific-settings)
- [Single-Address Left / Right Controls](#single-address-left--right-controls)
- [Split-King / Controller Sync](#split-king--controller-sync)
- [Troubleshooting Tips](#troubleshooting-tips)

---

## Accessing Configuration

You can configure the integration in two places:

### Initial Setup

During initial setup, you'll configure basic options like bed type, motor count, and massage support.

**OKIN ORE:** Add the integration manually and select **Okin ORE (Glideaway Motion app)**
as the bed type. Beds controlled with the current Dynasty Bases or INNOVA apps use
the Keeson [MaxCoil Una / Dynasty Bases / Bedsense Bases](beds/ore-comfort-bed.md)
or [INNOVA](beds/keeson.md#innova-profile) profile instead. The `00001000-0000-1000-8000-00805f9b34fb` UUID is also the standard
Bluetooth Service Discovery Server UUID, so it cannot identify an ORE bed by itself.
UUID-only automatic discovery is disabled to avoid detecting unrelated devices such
as Apple TVs ([issue #577](https://github.com/kristofferR/ha-adjustable-bed/issues/577)).
Existing ORE configurations continue to work.

### Options (After Setup)

To adjust settings after setup:

1. Go to **Settings** → **Devices & Services**
2. Find "Adjustable Bed" and click **Configure** (gear icon)
3. Choose **Change settings** from the menu
4. Adjust settings and click **Submit**

![Configuration options location](https://github.com/user-attachments/assets/8d6dc2b9-7df2-48dc-9ea5-61aaadce6c63)

---

## Profile recommendations

Every configured bed is checked against the integration's existing Bluetooth
identity and app-profile metadata. Under **Settings → System → Repairs**, Home
Assistant may suggest **A better profile may be available**, or ask you to **Check
the app or product profile** when several profiles fit. Weak or unknown identities
stay quiet. A shared Bluetooth service or a new app alone does not prove that
another profile works better.

**Review profile settings** opens Configure. A clear suggestion shows its settings;
an ambiguous match keeps your current selection so you can check your app, physical
remote and product. Nothing changes until you submit settings. Closing them keeps
your profile. Saving this review confirms your selection.

**Keep current profile** (or Ignore) dismisses the assessment across restarts and
updates. Only a materially different profile or candidate set may ask again.
Paired notices identify the physical bed and explain any required split or restore
standalone action; neither side changes automatically. See the
[matching evidence and limits](design/profile-recommendations.md).

## Basic Settings

| Setting | Options | Default | Description |
|---------|---------|---------|-------------|
| **Motor Count** | 2, 3, 4; 1 for one-motor Standard OCTO lifts | 2 | Number of controllable motor sections |
| **Has Massage** | On/Off | Off | Enable massage controls if your bed supports it |
| **Preferred Adapter** | Auto / Specific adapter | Auto | Which Bluetooth adapter or proxy to use |

Some app profiles add settings that several apps share. Each has one name and
label wherever it appears:

| Setting | Offered by | Description |
|---------|------------|-------------|
| **Enable light controls** (`has_light`) | Logicdata and Jiecang bed apps (default on), FSM Relax and Limoss Remote (default off) | Expose the app's light controls |
| **Bed or chair** (`product_type`) | FSM Relax, Limoss Remote | The product chosen in the app |
| **Reverse motor channel 1–4** (`reverse_motor_1` to `reverse_motor_4`) | FSM Relax, Limoss Remote | The app's per-channel direction flags, sent with every movement |
| **Exact Bluetooth name** (`ble_device_name`) | Motion Bed, AdjustableM5X5 | The unchanged advertised name that identifies the app profile |

Entries that stored `logicdata_app_has_light` or `jiecang_app_has_light` are
migrated to `has_light` when the integration loads.

The adapter choice is a preference. Home Assistant can select another path when
connecting; diagnostics record the actual adapter or proxy used.

### Motor Count Details

| Motors | Controllable Sections |
|--------|----------------------|
| 1 | TV/bed lift (Standard OCTO; `RTV` is detected automatically) |
| 2 | Back + Legs |
| 3 | Head + Back + Legs |
| 4 | Head + Back + Legs + Feet |

**Tip:** Count the distinct moving sections when using your physical remote to determine the correct setting. A one-motor Standard OCTO controller can be selected manually; an OCTO device named `RTV` is detected automatically as a one-motor TV lift.

### Malouf/Lucid Layout and Memory

Malouf and Lucid entries have two additional settings because BLE command
framing does not reveal the physical remote layout:

| Setting | Options | Default | Description |
|---------|---------|---------|-------------|
| **Malouf/Lucid actuator layout** | Back + legs; add head tilt; add lumbar; four motor; Hi-Lo | Auto | Controls which motor entities are exposed |
| **Malouf/Lucid memory positions** | Auto, 1, 2 | Auto | Must match the memory buttons on the physical remote |

Auto uses back + legs for a two-motor entry, head tilt for a three-motor entry,
and the standard head-tilt + lumbar layout for a four-motor entry. Hi-Lo must be
selected explicitly because neither Legacy nor New OKIN framing proves the
physical actuator arrangement. A two-motor layout defaults to one memory
position; other layouts default to two.

These settings are intentionally independent of protocol detection. **Lucid
L600 is not a protocol name**: confirmed L600 hardware includes both OKIN CB24
7-byte and legacy Malouf/OKIN 9-byte controllers.

---

## Toggle-Only Under-Bed Lights

Beds whose existing light control is **Toggle light**, including Tempur/Keeson
profiles without light-state feedback, also offer an optional **Under-bed lights**
light entity. It is disabled by default because its on/off state is an estimate.
To enable it, open the bed's device page under **Settings → Devices & Services**,
show disabled entities, select **Under-bed lights**, and enable it.

On first use, set the physical light off with the remote before enabling the
entity. Home Assistant initially assumes off and restores its last estimate on
later loads. Enabling or loading the entity sends no light command. Use
`light.turn_on`, `light.turn_off`, and `light.toggle` for subsequent control.
Repeated on or off requests do not toggle the light again; a failed command
leaves the estimate unchanged. The bed card uses the light once enabled.

Home Assistant marks this entity's state as **assumed**. It cannot detect changes
made with the physical remote, the manufacturer's app, the existing Toggle light
button, or a hardware auto-off timer. Those changes can make its estimate wrong,
and later on/off actions then rely on that incorrect estimate. Keep the existing
toggle button if you need direct control without an estimated state. For a
combined bed, each side has its own optional light and estimate.

This option uses the existing toggle command. It does not add physical state
feedback or change which commands a bed supports.

---

## Advanced Settings

| Setting | Range | Default | Description |
|---------|-------|---------|-------------|
| **Disable Angle Sensing** | On/Off | Depends on bed type and setup route | Disables position sensors and position controls |
| **Position Mode** | Speed / Accuracy | Speed | How position updates after commands |
| **Refresh Positions While Idle** | On/Off, Linak only | On | Periodically reconcile positions when idle polling is allowed |
| **Connection Profile** | Balanced / Reliable | Balanced | Connection timeout and retry behavior |
| **Disconnect After Command** | On/Off | Bed/variant-specific | Release the connection promptly after commands |
| **Idle Disconnect Seconds** | 10-300 | 40 | Auto-disconnect timeout when idle |
| **Stop Discovering New Bluetooth Devices** | On/Off | Off | Suppress automatic discovery of new beds (integration-wide) |
| **Maximum Back Angle** | Greater than 0, up to 180° | 68° | Back/head range for controllers reporting angles |
| **Maximum Legs Angle** | Greater than 0, up to 180° | 45° | Legs/feet range for controllers reporting angles |

### Setting Details

**Disable Angle Sensing**

- Turn this off to enable position feedback and sliders on supported controllers.
- Turn it on if position monitoring interferes with the physical remote. The controller can still require notifications for authentication or other state.
- Releasing the BLE link is separate: use Disconnect After Command or the Disconnect button to let a remote or app reconnect.

**Position Mode**

- **Speed** (default): Faster response without the extra accuracy-mode read
- **Accuracy**: Reads actual position after each command, slightly slower
- Neither mode treats an accepted target as a measured position. Missing or stale feedback can prevent a seek; see [position troubleshooting](TROUBLESHOOTING.md#position-commands-and-reported-state).

**Refresh Positions While Idle**

- Linak can periodically reconnect to catch up with moves made using the physical remote.
- This requires angle sensing to be enabled and Disconnect After Command to be off. Quick handoff suppresses periodic polling even when this option is selected.
- Turn it off to avoid background position connections. Positions still refresh during supported Home Assistant operations.

**Connection Profile**

- **Balanced** uses a 20-second connection timeout and shorter retry delays.
- **Reliable** uses a 25-second timeout and longer delays for less reliable connections.
- Both normally allow three attempts. Multiple usable Bluetooth paths receive a larger bounded retry budget; see [connection routing](CONNECTION_GUIDE.md#multiple-adapters-and-proxies).

**Maximum Angles**

- These fields appear only for controllers using degree-based feedback, not percentage-based controllers.
- Match the range supported by your bed. They control position conversion and validation, not the hardware's mechanical limits.

**Disconnect After Command**

- Enabled by default for selected bed types: freeing the BLE link lets the physical remote or vendor app reconnect.
- Off by default for beds whose protocol needs the link held open or whose controller must retain connection-scoped state between commands
- Retains the link for one second between rapid commands, then releases it for the physical remote. New commands restart that window. The explicit Disconnect button releases it immediately.
- Concurrent combined-bed actions retain both links until both sides finish, including STOP cleanup, then start the handoff window together. Sequential pairs still release one side before connecting the other.
- Skips periodic position polling to leave the remote's connection available while idle. Position feedback still refreshes during HA operations, and slow reads yield to STOP or replacement commands.
- Initial position and light-state hydration get one attempt with this option enabled. Missing feedback does not keep the link open through repeated background retries; later HA operations can refresh it.
- Turn it off to reuse the connection across longer pauses, up to the configured idle timeout. Controllers that require persistent connections retain their existing behavior.
- Changing it later only affects the bed whose options you edit; beds added before this became the default keep whatever they were set up with

**Idle Disconnect Seconds**
- How long to wait before automatically disconnecting when idle
- Lower values free the connection faster for physical remotes
- Higher values reduce reconnection overhead for frequent Home Assistant use

**Timed Move**
- `adjustable_bed.timed_move` treats the requested milliseconds as an elapsed movement ceiling, starting after connection and movement preparation. Linak completes its readiness handshake before this timer starts. Bluetooth write latency counts toward the ceiling instead of extending it.
- Each controller keeps its existing repeat cadence and release sequence. Some controllers finish sooner; controller setup within the movement also consumes the budget. The service waits for STOP/release cleanup, so its total duration can include connection setup and cleanup in addition to the movement limit.
- Transport errors and failed cleanup remain errors. Reaching the requested movement limit is normal completion.

**Stop Discovering New Bluetooth Devices** (Default: Off)
- Turn on once all your beds are added to stop Home Assistant suggesting new Bluetooth devices as adjustable beds
- This is a global setting that applies to the whole integration, not just the bed whose options you are editing — so you only need to set it on one bed
- You can still add a bed at any time with **Settings → Devices & Services → Add Integration → Adjustable Bed**; only the automatic discovery notifications are suppressed
- To turn discovery back on, uncheck this option in any bed's settings

---

## Motor Pulse Settings

These settings control how motor movement commands are sent. Adjusting them can help if motors move too briefly or commands are dropped.

| Setting | Range | Default | Description |
|---------|-------|---------|-------------|
| **Motor Pulse Count** | 1-100 | Bed-specific | Number of command repeats sent for motor movement |
| **Motor Pulse Delay (ms)** | 10-500 | Bed-specific | Delay between command pulses |

### Default Values by Bed Type

These are configuration defaults for ordinary movement pulses. App/product
profiles and detected controller variants can have their own timing. Presets,
memory programming, and release sequences can use different controller-defined
timing; these settings do not replace it. Use the matching [protocol guide](SUPPORTED_ACTUATORS.md).

| Bed Type | Pulse Count | Pulse Delay |
|----------|-------------|-------------|
| Richmat | 7 | 150ms |
| Keeson | 10 | 100ms |
| Ergomotion | 10 | 100ms |
| Serta | 10 | 100ms |
| Malouf Legacy OKIN | 7 | 150ms |
| Malouf New OKIN | 10 | 100ms |
| OKIN FFE | 7 | 150ms |
| OKIN Nordic | 10 | 100ms |
| Leggett WiLinke | 10 | 110ms |
| Leggett Okin | 10 | 100ms |
| Octo Standard | 3 | 350ms |
| Octo Star2 | 3 | 50ms |
| Jiecang | 10 | 100ms |
| Comfort Motion | 10 | 100ms |
| Limoss | 12 | 80ms |
| Linak Bed Control | 10 | 100ms |
| Linak Performance Series | 4 | 300ms |
| Sleepy's BOX15 | 10 | 100ms |
| Sleepy's BOX24 | 10 | 100ms |
| SleepSpa S9000AI / SLEEPSTAR | 10 | 100ms |
| Jensen | 4 | 300ms |
| Svane Remote app profiles | Held duration, not a configurable repeat count | Source 100ms, feet/separate fallback adds 100ms |
| Vibradorm | 10 | 100ms |
| Rondure | 25 | 50ms |
| Remacro | 10 | 100ms |
| OKIN CB24 | 3 | 300ms |
| OKIN CB35 | 3 | 300ms |
| OKIN DOT | 10 | 100ms |
| OKIN ORE | 1 | 300ms |
| Cool Base | 10 | 100ms |
| Scott Living | 10 | 100ms |
| SBI/Q-Plus | 10 | 100ms |
| SUTA | 7 | 150ms |
| TiMOTION AHF | 10 | 100ms |
| Logicdata | 10 | 30ms |
| All others | 10 | 100ms |

### When to Adjust

| Symptom | Solution |
|---------|----------|
| Motors stop moving too soon | Increase pulse count |
| Movement is choppy or jerky | Decrease pulse delay |
| Commands are getting dropped | Increase pulse delay |

---

## Protocol Variants

Some beds support multiple protocol variants. Auto-detection usually works, but you can override if needed.

The selector lists the variants available for the current bed type. Additional
controller-specific choices are documented here:

| Bed type | Choices covered by its guide |
|----------|-----------------------------|
| [Linak](beds/linak.md#profiles-and-model-variants) | Bed Control and Performance Series |
| [Kaidi](beds/kaidi.md#command-families) | Seat 1, Seat 2, Seat 3, Seat 1+2 |
| [Okin CST](beds/okin-cst.md) | Rize and Support product profiles; Auto retains MF900 behavior |
| [Sleepy's BOX25](beds/sleepys.md#box25-protocol-nordic-uart) | Auto, StarCode, Legacy CB25 |
| [SBI](beds/sbi.md#protocol-variants) / [Rondure](beds/rondure.md#side-selection-split-king) | Both, Side A, Side B |
| [OKIN CB24](beds/okimat.md#cb24-preset-safety) | Legacy/CBNew and specific SmartBed profiles |
| [Okin DOT](beds/okin-dot.md) / [Okin 64-bit](beds/okin-64bit.md) | Handset or transport-specific selection |

### Keeson Variants

| Variant | Description | Use For |
|---------|-------------|---------|
| **Auto** | Auto-detect (recommended) | Most beds |
| **Base** | BaseI4/BaseI5 protocol | Member's Mark, Purple, some Ergomotion |
| **JSON/A00A** | JSON commands | Juna, Linx, Ergo Health |
| **KSBT** | Nordic UART protocol | KSBT03/KSBT04 devices, including some Ergomotion Sync beds |
| **KSBT03CR** | 7-byte KSBT format (0x05 prefix) | KSBT03CR devices |
| **KSBT04C** | Generic 7-byte checksum format | Matching KSBT04C devices |
| **Sleep Harmony** | App-specific settings and lighting | Sleep Harmony controllers |
| **Adjustable Lite** | App profile for KSBT01C / KSBT03C remotes | Beds controlled with the Adjustable Lite app |
| **Simon Li** | App profile, big-endian E5 frames; fixed back, foot, lumbar, Home and two memories | Seats controlled with the Simon Li app |
| **Heal Every Night** | App profile, big-endian E5 frames; motor count picks Healing 6/7/8 | Beds controlled with the Heal Every Night app |
| **OKIN-Seating** | App profile, big-endian E5 frames; back, foot and Home | Seats controlled with the OKIN-Seating app |
| **Bedsense Bases** | ORE comfort-bed app profile; motor count picks 2M/3M/4M | Beds controlled with the Bedsense Bases app |
| **INNOVA** | App profile, little-endian E5 frames; motor count picks 2M/3M/4M | Beds controlled with the INNOVA app |
| **Restonic BT, remote A / B** | App profiles for the two Restonic BT Remote styles | Beds controlled with the Restonic BT Remote app |
| **Purple** | Purple profile | Purple Smart Base |
| **Ergomotion** | Base protocol with position feedback | Ergomotion-branded beds |
| **Okin** | OKIN FFE (0xE6 prefix) | OKIN 13/15 series |
| **Serta** | Serta MP Remote protocol | Serta Motion Perfect |
| **Sino** | Big-endian packet format | Dynasty, BetterLiving |

### Leggett & Platt Variants

| Variant | Description | Use For |
|---------|-------------|---------|
| **Auto** | Auto-detect (recommended) | Most beds |
| **Gen2** | Richmat-based, ASCII commands | Most L&P beds, RGB lighting |
| **Okin** | Requires BLE pairing | Beds with Okin remotes |
| **MlRM** | WiLinke protocol with discrete massage | Matching MlRM controllers |

### Richmat Variants

| Variant | Description | Use For |
|---------|-------------|---------|
| **Auto** | Auto-detect (recommended) | Most beds |
| **Nordic** | Single-byte commands | Simpler Richmat controllers |
| **WiLinke** | 5-byte commands with checksum | WiLinke-based controllers |
| **Prefix55** | 5-byte commands with 0x55 prefix | Matching Prefix55 controllers |
| **PrefixAA** | 5-byte commands with 0xAA prefix | Matching PrefixAA controllers |

### Octo Variants

| Variant | Description | Use For |
|---------|-------------|---------|
| **Auto** | Auto-detect (recommended) | Most beds |
| **Standard** | Standard Octo protocol | Most Octo beds |
| **Star2** | Octo Remote Star2 | Star2 receivers |

### Sleep Number Variants

These variants apply to newer Sleep Number Fuzion bases (`Smart bed *`). Older BAM/MCR beds such as some i8 / 360 FlexFit 2 models expose both firmness sides from one entry and do not use this setting.

| Variant | Description | Use For |
|---------|-------------|---------|
| **Auto** | Auto-detect (recommended, defaults to the left side) | Most Sleep Number bases |
| **Left** | Force the left side | Split bases when you want the left side only |
| **Right** | Force the right side | Split bases when you want the right side only |

When the Fuzion system configuration identifies a single chamber, its protocol
uses the right-side channel regardless of the default side selection. Optional
actuators, lighting and thermal controls follow the bed's reported capabilities.
Older MCR beds likewise expose only the foundation/chamber features discovered
on the connected hardware. Additional BLE settings, including temperature
programs, use the [Sleep Number command action](beds/sleep-number-services.md).

### Okimat Variants

Okimat beds use different remote codes that determine available features and command values.
The table below gives common examples; the setup selector contains the complete
handset list. For beds controlled by the FurniMove app, including RF ECO BT
receivers, use the separate [FurniMove profile](beds/furnimove.md) with its exact
handset selector. Other OKIN app profiles retain their own evidence and options. For example, RF-TOPLINE `82620` exposes Back, Legs, Flat, and the
receiver's under-bed light toggle.

| Variant | Remote Model | Motors |
|---------|--------------|--------|
| **Auto** | Auto-detect (tries 82417 first) | Varies |
| **76688, 78375, 78378, 78386, 80599, 80602, 80608, 80616** | RFS-ELLIPSE/06 | Back, Legs |
| **82417, 82620, 82757, 82760, 82764, 82767, 82770, 83358, 83462, 83489, 84931, 84963, 92461, 93305** | RF-TOPLINE basic | Back, Legs |
| **82418, 85058, 92471, 93306** | RF-TOPLINE/11 | Back, Legs, 2 Memory |
| **88875, 88877, 89137, 89138, 89139, 92535** | RF-LITELINE/07 | Back, Legs |
| **91244** | RF-FLASHLINE/07 | Back, Legs |
| **91246, 92591, 94238** | RF-FLASHLINE/09 | Back, Legs, 2 Memory |
| **93329** | RF TOPLINE | Head, Back, Legs, 4 Memory |
| **93332** | RF TOPLINE | Head, Back, Legs, Feet, 2 Memory |

---

## Bed-Specific Settings

### App and Product Profiles

Choose the app, model or remote supplied with your bed when setup asks for it.
These choices determine which controls are available. Related choices are
listed together below, with links to their setup instructions.

1. Let automatic discovery identify the controller where possible.
2. If adding manually, find your brand or app in [Supported Beds](../README.md#supported-beds).
   The bed-type list names each app, so you can also search it for the app you
   use, for example **INNOVA app (Keeson)** or **The Brick app (Remacro)**.
   Choosing an app sets its protocol variant for you.
3. Match any requested model or remote to your physical bed. Shared Bluetooth
   names and services do not always identify the right layout.

Existing entries keep their selection until you change it. Beds added before
4.1.0 whose bed type gained app profiles are asked once, through a repair,
which app they use; see [the upgrade prompt](TROUBLESHOOTING.md#new-app-profiles-are-available-repair).
For a two-address pair, settings belong to each physical bed. If the shared form
refuses a change, split the pair, configure each side, then combine them again.

| Bed or brand | Model and remote settings |
|--------------|---------------------------|
| Keeson | Choose the matching protocol variant: [Adjustable Lite](beds/keeson.md#adjustable-lite-profile), [Simon Li / Heal Every Night / OKIN-Seating](beds/keeson.md#simon-li-heal-every-night-and-okin-seating-profiles), [INNOVA](beds/keeson.md#innova-profile), [MaxCoil Una / Dynasty Bases / Bedsense Bases](beds/ore-comfort-bed.md), or [Restonic BT](beds/keeson.md#restonic-bt-profiles). Match motor count or remote style where offered. |
| Tempur Sleeptracker-AI | [Processor setup](beds/sleeptracker.md): choose this app profile for ProSmart / ProSmart Air and ActiveBreeze. Select the actual processor endpoint and app layout, unit number, snapshot ordinal, restricted session, processor type and foundation metadata. Add a separate processor entry when the current address exposes UART. Axes and massage come from the app layout; position feedback is unavailable. |
| Richmat | [RMControl](beds/rmcontrol.md): product code and side. [Revive Control / Best Mattress / Blvd Home / HARMONY / Idealbed](beds/richmat-mh.md): app and model. |
| Leggett & Platt | [Prodigy / U Series](beds/leggett-okin.md): remote layout. [L&P legacy](beds/lp-legacy.md): model, protocol mode and confirmed GATT characteristics. |
| Solace / Woosa | [Woosa Sleep](beds/woosa.md): protocol variant `woosa`; `auto` retains name-based Solace routing. |
| Svane / Jensen LinOn | [Svane](beds/svane.md): multi-service or JMC400 remote. [Jensen LinOn](beds/jensen.md#linon): separate `jensen_linon` variant. |
| Jiecang | [ERGOBALANCE / Dream Motion](beds/jiecang-app.md): app, layout, transport and light. |
| LOGICDATA | [MOTIONrelax](beds/logicdata-app.md): phone/tablet app, command family, layout, transport and light. [Sleep Smart](beds/logicdata-sleep-smart.md): bed layout and series, or separate air pump. |
| Malouf / Lucid | [Base apps](beds/malouf-app.md): app, exact model, transport and primary/secondary role. |
| Customatic / Jordan's | [Clarity / Jerome's / Remedy](beds/customatic.md), [Z-Series](beds/customatic-z-series.md), [Serenity](beds/serenity.md), [Tranquil](beds/tranquil.md): select the matching app and model. |
| Vibradorm | [Caresse / Werkmeister](beds/vibradorm_app.md), [VMAT](beds/vmat.md), [V-MAT Basic](beds/vmatbasic.md): app, exact remote or product, and offered light settings. |
| Remacro | [Slumberland / The Brick / Jerome's](beds/remacro.md): protocol variant; advertised company ID selects the model. |
| FurniMove / OKIN Smart Remote | [Exact handset ID](beds/furnimove.md); also includes a guided repair for older RF ECO BT entries. |
| SIMMONS | [Regular/inclined bed and packet format](beds/simmons.md). |
| Adjustable bed (Lumbar) | [Automatic or fixed command table](beds/adjustable-lumbar.md). |
| AdjustableM5X4 / M5X5 | [M5X4](beds/starcode-abm5-4.md): command and transport selectors. [M5X5](beds/starcode-m5x5.md): layout and up to three configured lift entries. |
| Motion Bed | [Layout and retained settings](beds/motion_bed.md); preserve the original Bluetooth name. |
| Limoss | [Limoss Remote](beds/limoss-remote.md): bed/chair layout, light/massage and reversal settings. |
| FSM Relax | [Bed/chair layout, light/massage and reversal settings](beds/fsm_relax.md). |
| Legacy OKIN CB24 | [Single-address controls](#single-address-left--right-controls): both sides, Side A / Left, or Side B / Right. |

<details>
<summary><b>Detailed app and remote settings</b></summary>

### Richmat app profiles

Choose the app your phone uses, for example **Revive Control app (Richmat)**. Shared Richmat names and services never select these profiles. `auto` applies the app's name rule: the first four characters of the raw Bluetooth name, lowercased, select the model. Names starting with `QRRM` (and Idealbed names starting with `Cool Touch`) make the app ask, so choose the model variant (`model_<id>`, labelled as in the app's picker, wizard or manual list). The form reports a name the app cannot resolve. Motor count is fixed; the model's catalog decides the motors, and each control keeps the app's KEEP interval. The variant belongs to each physical bed: split a two-address pair before changing it. See [Richmat app profiles](beds/richmat-mh.md).

### SIMMONS app profile

Choose **SIMMONS app** manually. OKIN and SmartBed names and the shared Bluetooth services do not identify this app. The protocol variant selects the app's bed type (regular or inclined) and, optionally, the packet format. `auto` keeps a regular bed and applies the app's name rule: a name starting with `smartbed` or any unmatched name uses SmartBed frames, a name starting with `okin` uses OKIN frames. Motor count is fixed at two and the 300 ms refresh is fixed. The variant belongs to each physical bed: split a two-address pair before changing it. See [SIMMONS](beds/simmons.md).

### Adjustable bed (Lumbar) app profile

Choose **Adjustable bed (Lumbar) app** manually. OKIN and Star names and the shared services do not identify this app. `auto` applies the app's name rule: a name starting with `okin` uses the OKIN-service table; a name starting with `star` uses a Nordic UART table chosen by the Device Information manufacturer. Any other name needs a fixed variant. Head, foot and lumbar are fixed, as is the 100 ms refresh. The variant belongs to each physical bed: split a two-address pair before changing it. See [Adjustable bed (Lumbar)](beds/adjustable-lumbar.md).

### V-MAT Basic app profiles

Choose **Vibradorm: VMAT, Caresse Diamant, Werkmeister, V-MAT Basic**, then
**V-MAT Basic** and the exact Basic, CBI or CBI with XT-Box product. Bluetooth
identifiers and diagnostic model strings do not choose this profile. CBI exposes
saved floor level 0–255 and timer 0–1439 minutes; XT exposes level 1–6 and timer
0–255 minutes. Leaving the optional level unset preserves the source distinction
between the ON-button default and settings-screen default. Timer defaults to zero.
Product changes use the guided reconfigure flow and discard incompatible floor
values. Ordinary brightness/timer changes remain in Configure. Product profiles
belong to one physical receiver; split a pair before changing them.

### FurniMove app profile

Select **FurniMove / OKIN Smart Remote** and the exact `furnimove_remote` ID used
by the app. The catalog includes all 87 captured production IDs and three
shipped local/offline IDs. Motor count, massage capability and ordered commands
come from the selected table; manual motor count and pulse delay are hidden.
Shared RF ECO BT receiver labels and GATT UUIDs do not choose a handset.
The profile has no angle feedback or mandatory pairing/protected-read gate.

Old RF ECO BT entries receive a [guided layout repair](beds/furnimove.md#repairing-existing-configurations),
including offline entries and unconfirmed one-motor configurations. It preserves
the existing entry and matching entity IDs. Confirm a staircase or select the
FurniMove handset. For a bed using another app, select its corresponding profile
in integration options. Paired repairs change only their own physical side.

### Jordan's Serenity app profile

Select **Jordan's Serenity app** explicitly for the accepted `com.okin.bedding.serenity` 1.0.1 (2) application profile. Shared OKIN discovery and GATT UUIDs do not identify this app profile. The two named main axes use Head and Feet; additional actuator controls retain literal selector 4/5 names because app touch and voice labels disagree. Setup hides motor-count and pulse-delay fields: the app proves two named axes, additional literal selectors, and a fixed 100 ms refresh interval. The internal named-axis count does not claim a physical actuator count. Status notifications remain active when angle sensing is disabled; this profile reports no motor position.

### Jordan's Tranquil and Customatic Z-Series app profiles

Select **Jordan's Tranquil app** for `com.okin.bedding.tranquil` 1.0.2 (3). For `com.okin.bedding.glory` 1.0.4 (5), select **Customatic Z-Series app (Z-230)** or **(Z-280)** to match the model chosen on the app's selection screen (protocol variant `z230` or `z280`). These apps share OKIN discovery names and GATT UUIDs with other products, so none is detected automatically. As with Serenity, setup hides motor-count and pulse-delay fields. The pulse count stays editable: on Z-Series profiles it also bounds an ordinary button press, because the app streams a touched control until release and defines no deadline of its own. Z-Series setup accepts 1 to 600 pulses (0.1 to 60 s). A two-address pair must be split before either side changes to, from or between these profiles. Notifications stay active when angle sensing is disabled; these profiles report no motor position.

### AdjustableM5X4 app selectors

Choose the AdjustableM5X4 app profile explicitly. Star names offer this app as a candidate, while existing receiver detection remains available. The original Bluetooth name chooses transport independently of the saved command/parser selector. Manufacturer classification can update the command selector without changing the retained UI selector. “Use detected transport profile” copies the current transport into both app selectors while retaining this physical bed’s observed timer/light/massage state. Single-address side control is unsupported; two-address pairs retain each child’s settings. See the [complete selector and capability contract](beds/starcode-abm5-4.md).

### Vibradorm guided setup and migration

The bed-type list has one **Vibradorm: VMAT, Caresse Diamant, Werkmeister,
V-MAT Basic** choice. Choose the app you use on your phone, then its remote or
product. **Legacy setup** remains available inside this choice for fresh setup.
The family choice shares setup navigation, while each selected app keeps its
existing controller, features and Bluetooth pairing requirements.

For an existing bed, open **Settings → Devices & services → Adjustable Bed**,
then the entry's three-dot menu and **Reconfigure**. The one-time app review in
Repairs opens the same wizard. Choose **Keep current setup** to keep your
working controls and dismiss the review, or choose your app and remote/product.
Keeping the same app seeds the form with your saved settings.

The wizard temporarily releases Home Assistant's connection to check the chosen
setup. It checks the exact app's required Bluetooth roles and existing pairing
requirements, without moving the bed. A missing scanner, failed check or link
that cannot be closed cannot save the new selection. Retry or keep the current
setup. Closing the wizard leaves the saved configuration and pending review
unchanged. A failed connection remains owned until it is observed closed, so
another setup attempt cannot overlap it.

After a successful check, a final confirmation shows the chosen app and
remote/product. Saving keeps the entry, address, device and unchanged entity
IDs. Controls follow the selected profile; obsolete controls and angle estimates
may disappear. This check does not prove physical movement, lighting or massage
behavior. If settings changed in another window, the wizard refuses to overwrite
them. Routine brightness, timer and connection changes remain in **Configure**.

A paired bed must first be split explicitly, or have its standalone controls
restored for a one-address pair. The wizard offers the existing reversible split
action and preserves each receiver's settings and identities. Afterwards,
reconfigure the intended receiver separately and combine compatible beds again
if needed. It never assigns one app/remote to both receivers or guesses from
Bluetooth identifiers or motor count.

### Caresse / Werkmeister app profiles

Select **Vibradorm: VMAT, Caresse Diamant, Werkmeister, V-MAT Basic** in the
bed-type picker, then choose Caresse Diamant or Werkmeister. Existing generic
entries keep their legacy setup until explicitly reconfigured. Bluetooth identifiers do not select an app
or remote layout. Werkmeister offers its two proven remote
layouts. Fresh Caresse uses its basic two-axis layout; enable retained settings
only when you know the app's saved remote type and independent floor-light,
mood-light, massage and light-extension settings. The `other` retained type has
memory controls but no motor axes. No profile reports positions.

Retained Caresse settings also accept a remembered floor brightness from 1 to 8.
The light-extension slider stops at 6, but a previously remembered 7 or 8 remains
valid. Floor brightness and pending timer choices are local command intent,
not measured bed state. Reconnecting or reloading preserves that intent during
the same Home Assistant process; restarting clears current brightness and the
pending timer while retaining the remembered brightness.

Setup hides generic motor-count and pulse settings. Controls use the selected
profile's fixed refresh and release behavior. First onboarding shares one
10-second connection, information and native pairing deadline. Local stored
bonds require exact-adapter BlueZ evidence; a successful proxy pairing request
remains unverified. App metadata is diagnostic information, not bond proof.

### VMAT app profile

Choose **Vibradorm: VMAT, Caresse Diamant, Werkmeister, V-MAT Basic** in the
bed-type picker, then **VMAT** and the same remote ordinal as the app. Its fourteen
shipped selections derive the logical axes, memory, sync, floor, mood and
massage controls. Independent feature overrides
and inferred product identification are unavailable. Setup requires positive
native bond evidence for the exact address and actual host adapter; an
unverified proxy pairing request cannot finish setup. Ordinary sessions do not
send onboarding queries or position polls. Accessory state is assumed local
intent, preserved during the current HA process and rolled back on failed
writes. See the [complete VMAT contract](beds/vmat.md).
Configure each physical side separately before combining a two-address pair.

### Motion Bed app

Select the explicit **Motion Bed app** route and the original case-sensitive Bluetooth name. Auto chooses the app’s ordered layout; retained overrides belong to the same physical target. FFE1 alone does not identify this app. Two-address pairs preserve each side’s settings and require unpairing before profile changes. See [Motion Bed setup and controls](beds/motion_bed.md).

### Limoss Remote app

Select **Limoss Remote app** manually under Limoss. Choose bed/chair, local lamp and massage controls, four reversal flags and an optional app artwork preference. Live replies select the rendered key layout and memory capacity. These settings belong to each physical receiver, including paired children. Disabling a selected feature sends its ten OFF frames before saving; enabling only changes the local layout. Generic pulse, angle and motor-count settings are hidden for this profile. See [the protocol page](beds/limoss-remote.md).

### AdjustableM5X5 app

Select **AdjustableM5X5** (`starcode_m5x5`) and enter the exact Bluetooth name, preserving case. Confirm CB25, F23 or kneading. ELEVATE lifts use the [DewertOkin ELEVATE](beds/star-elevate.md) bed type instead. The specific F23/kneading prefixes take precedence over generic `STAR25`; shared Nordic UART identifiers alone cannot choose an app. The exact optional manufacturer read selects the command dialect when connecting.

On the main entry, select up to **three other configured AdjustableM5X5 or DewertOkin ELEVATE entries** as lifts. This supports four independent Bluetooth addresses: one main and three lifts. The three bed classes and ELEVATE can occupy either slot; an ELEVATE main selects its lifts in its own options. Duplicate addresses and unrelated products are rejected. This group keeps each device's existing coordinator and entities. It does not convert them into Left/Right paired devices.

Use `adjustable_bed.starcode_move_lifts` for native lift-union movement, STOP or composite flat. A profile or group-selection edit cancels retained delayed writes. Individual controls remain on each physical device. See [protocol and control details](beds/starcode-m5x5.md).

### FSM Relax app

Select the explicit FSM Relax app bed type, then choose chair/bed layout, optional
light/massage controls and four reversal flags. These settings are local app
configuration, not inferred hardware identity. Options include eight local memory
names, with blank names resetting M1–M8. Raw memory values have no known units.
See [FSM Relax](beds/fsm_relax.md) for exact controls, quarantine and calibration.

</details>

### Octo PIN

**Setting:** 4-digit PIN code

Some Octo beds require PIN authentication to maintain the BLE connection. The bed will disconnect after ~30 seconds without re-authentication.

**How to configure:**
1. Go to **Settings** → **Devices & Services**
2. Find your Adjustable Bed and click **Configure** (gear icon)
3. Choose **Change settings** from the menu
4. Enter your 4-digit PIN in the "Octo PIN" field

**Finding your PIN:**
- Use the PIN set in the OCTO Smart Control app; it is not the OS Bluetooth pairing code.
- If your bed works without a PIN, leave this field empty

Standard Octo setup verifies PIN acceptance without moving the bed. Setup finishes
only when the PIN is accepted or the controller confirms no PIN is required.
An inconclusive check leaves the entry unsaved and can be retried; it does not
mean the PIN is wrong. Star2 has no application PIN exchange.

During operation, the integration responds to lock notifications and retains a
periodic keepalive fallback. See [Octo authentication](beds/octo.md#pin-configuration).

### Jensen PIN

**Setting:** 4-digit PIN code (default: 3060)

Jensen JMC400 beds require PIN authentication for BLE control.

**How to configure:**
1. Go to **Settings** → **Devices & Services**
2. Find your Adjustable Bed and click **Configure** (gear icon)
3. Choose **Change settings** from the menu
4. Enter your 4-digit PIN in the "Jensen PIN" field

**Finding your PIN:**
- Default PIN is `3060` (used if field left empty)
- Check your Jensen remote's settings menu for custom PIN

### Richmat Remote

**Setting:** Remote model code

Richmat beds have different feature sets based on the remote model. Selecting your remote ensures only supported features are shown.

| Remote Code | Features |
|-------------|----------|
| **Auto** | All features enabled |
| **AZRN** | Head, Pillow, Feet |
| **BT6500** | Head, Feet, Pillow, Lumbar, memory/presets, Massage, Lights |
| **BURM** | Head, Feet, Massage, Lights |
| **BVRM** | Head, Feet, Massage |
| **VIRM** | Head, Feet, Pillow, Lumbar, Massage, Lights |
| **V1RM** | Head, Feet |
| **W6RM** | Head, Feet, Massage, Lights |
| **X1RM** | Head, Feet |
| **ZR10** | Head, Feet, Lights |
| **ZR60** | Head, Feet, Lights |
| **I7RM / HJH85 / Sleep Function 2.0** | Head, Feet, Pillow, Lumbar, Massage, Lights |
| **190-0055** | Head, Pillow, Feet, Massage, Lights |
| **L&P QRRM** | Head, Feet, Flat, Zero G, Custom 1/2 |

**Note:** The remote code is usually printed on the back of your physical remote.
For an L&P bed that advertises as `QRRM` and has Flat, Zero G, Custom 1, and
Custom 2 buttons, select **L&P QRRM**. Current L&P and Richmat apps also require
a physical remote or product selection for QRRM devices. The BLE name and GATT
services do not identify that profile, so the integration cannot select it
safely on its own.

---

## Troubleshooting Tips

### Physical Remote Stops Working

This is expected when Home Assistant is connected. Most beds only support one BLE connection.

**Solutions:**
1. Enable "Disconnect after each command" where supported, or press Disconnect
2. Reduce "Idle disconnect seconds" for faster automatic disconnection
3. Enable "Disable angle sensing" if position monitoring causes conflicts

### Commands Are Slow or Unresponsive

1. Move your Bluetooth adapter or ESPHome proxy closer to the bed
2. Try a different protocol variant
3. Reduce interference from other 2.4GHz devices

### Motors Move Too Briefly

Increase the "Motor pulse count" setting. Start with +10 and test.

### Commands Are Being Dropped

Increase the "Motor pulse delay" setting. Try 100ms, then 150ms if needed.

### Wrong Features Showing

- **Richmat beds:** Select your specific remote code in options
- **Other beds:** Verify motor count matches your bed's actual motors
- **Massage not showing:** Enable "Has massage" in options

---

## Single-Address Left / Right Controls

SBI, Rondure, legacy CB24, Sleep Number Fuzion, and Kaidi `seat_1_2` beds can
reach both physical sides through one Bluetooth address. Open the bed's
integration options and choose
**Enable Left / Right / Both controls** to expose the same paired-bed surface
used by two-address beds.

This conversion keeps the existing config entry, Bluetooth address, device,
and standalone entity history. It is reversible through **Restore standalone
controls**. Existing entries do not change automatically.

Routing remains protocol-native:

- SBI and Rondure use their Side A, Side B, and native broadcast packets.
- Legacy CB24 uses selectors `0xAA` (left/A), `0xBB` (right/B), and `0x00`
  (both). The selector is also available in initial setup and options.
- Sleep Number Fuzion serializes left then right over its one command lock.
- Kaidi `seat_1_2` binds Seat 1 to Left and Seat 2 to Right; Both retains its
  dual-command behavior. Other Kaidi variants cannot enable this surface.
- Sleep Number BAM/MCR already exposes side-specific controls in its standalone
  entry and is not offered this conversion.
- CBNew profiles are refused because their known packet format has no A/B side
  selector. The integration never guesses a selector byte.

Standalone entries retain their configured default side and send the same
bytes as before. The per-call side binding is used only after this opt-in.

---

## Split-King / Controller Sync

The **Controller Sync** switch (previously **Synchro Mode**) sends a sync command
to the bed controller. Any resulting synchronization depends on the controller's
firmware and its existing relationship with the other frame. Turning it on does
not discover another Home Assistant bed entry or mirror commands between entries.
It does not establish a hardware pairing or replace a sync cable.

For example, the Richmat HJC9 report in
[discussion #503](https://github.com/kristofferR/ha-adjustable-bed/discussions/503)
found that enabling the switch on both frames did not make movement mirror.
Use Home Assistant's paired-bed controls for two independently controlled frames.

### State and Availability

The switch is exposed only when the selected controller supports it and is
**disabled by default**. Its displayed state is not confirmation that both frames
are synchronized: the current switch has no sync-state feedback subscription.
It starts off after setup or reload and records successful on/off requests.
Physical-remote changes may not be reflected, and a toggle-only controller cannot
reliably enforce a requested on/off state. Do not assume that reloading Home
Assistant resets the bed's own sync setting.

To enable it, open **Settings → Devices & Services → Adjustable Bed**, select the
bed, and enable **Controller Sync** under **Entities**. Existing custom entity
names may still show the old label.

### Two Independent Frames in v4

Add each frame as its own Adjustable Bed entry and confirm that each controls
only its intended side. For compatible entries, start **Add Integration →
Adjustable Bed**, then choose **Combine two beds into one (Dual Bed)** and select
Left and Right. The resulting parent device provides
combined controls; the child devices provide side-specific controls. The card
also offers Left/Both/Right selection. This does not require Controller Sync.

Automatic connection mode keeps each receiver's own connection settings, including
its idle timeout and Disconnect After Command choice. Selecting one side does not
disconnect the other, and Both can operate the two receivers concurrently. This
also applies to OCTO/Star2 pairs. Existing automatic pairs pick up this behavior
on reload. If the active adapter reports that the second link exhausted its
connection slots, automatic mode falls back to sequential switching for that
runtime. Explicit concurrent or sequential modes are retained.

The wizard checks protocol and motor-layout compatibility. Some controllers need
a successful connection first to discover their capabilities. One-motor OCTO
TV/bed lifts remain standalone. Combined controls use capabilities shared by both
sides; side-specific controls retain each side's own features.

For two receivers, open **Configure → Change left receiver settings** or
**Change right receiver settings** to adjust its adapter, connection profile,
motor pulses, Disconnect After Command, and idle timeout. These changes apply
only to the selected receiver, without splitting the bed. **Change settings**
retains the shared form; changed values there apply to both receivers.
The card's **Both** view also offers each receiver's Connect and Disconnect
buttons next to its connection status.

On concurrent two-receiver OCTO pairs, holding Back or Legs in **Both** uses
one-second timed movement windows for both receivers, each at its own existing
command cadence. This avoids waiting out the slower receiver's configured pulse
after the faster one has finished. Releasing the control or selecting Stop
cancels both sides. Single-side controls, discrete button presses, other motors,
and explicitly sequential pairs keep their existing movement behavior. Commands
and cleanup remain bounded; connection delays and brief cleanup gaps can still
occur, and simultaneous physical movement is not guaranteed.

Beds whose extra controls require live discovery, including Sleepy's BOX25,
can also be combined. Each such side must connect during paired setup, including
after a Home Assistant restart or integration reload. Otherwise setup retries
instead of loading with missing controls. During conversion, the original
standalone entries remain intact until this check succeeds. Once loaded, an
ordinary disconnect does not remove the side's controls. Beds with saved or
offline-safe capabilities still support setup with one side unavailable.

Existing side entity IDs, device IDs, names, areas, and history are retained when
combining entries. To undo it, choose **Split paired bed** in the pair's options;
the side entries are restored and combined controls are removed. Update any
automation that targeted the combined controls. This restores standalone controls,
not the v3 storage schema; [rollback requires a pre-v4 backup](HA_2026_9.md#backup-and-rollback).

Use the [service targeting rules](SERVICES.md#targeting-a-bed-or-side) for
automations. A child device defaults to its side; a parent defaults to both.

If a sync cable or the bed's firmware already makes either frame control both
sides, keep a single entry rather than combining those frames as independent
sides.

### Keeping Two Standalone Entries

You can instead use a script or automation to send an action to both entries.
For example, this script raises both back motors using their existing movement
actions. Replace the example entity IDs with your own:

```yaml
alias: Raise both bed backs
sequence:
  - parallel:
      - action: cover.open_cover
        target:
          entity_id: cover.left_bed_back
      - action: cover.open_cover
        target:
          entity_id: cover.right_bed_back
```

This runs each cover's normal movement action; it does not make movement
continuous or synchronize positions. To stop, call `cover.stop_cover` targeting
both covers. Unlike the v4 paired-bed controls, this simple script does not stop
the other side automatically if one side fails.

---

## Next Steps

- **Having connection issues?** See [Troubleshooting](TROUBLESHOOTING.md)
- **Want to learn about your bed's protocol?** See [Supported Actuators](SUPPORTED_ACTUATORS.md)
- **Setting up Bluetooth?** See [Connection Guide](CONNECTION_GUIDE.md)
