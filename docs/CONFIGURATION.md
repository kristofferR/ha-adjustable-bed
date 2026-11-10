# Configuration Guide

Options depend on the selected controller and its reported capabilities; not
every bed shows every field. The integration requires Home Assistant 2026.11.0 or
newer.

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
- [Dashboard Card Graphics and Dialog](#dashboard-card-graphics-and-dialog)
- [Troubleshooting Tips](#troubleshooting-tips)

---

## Accessing Configuration

You can configure the integration in two places:

### Initial Setup

The first screen lists the discovered beds, each named with its family, then:

- **Set up by app or remote** asks which app controls the bed: one searchable
  list of the apps, remotes and brands in the bed-type list. A row of a family
  names its family after a dot, such as **Heal Every Night app · Keeson**, and
  a family's own row lists its apps the same way. Good Vibe Sleep, HJBed,
  Casper Base and Comfort Enhancements have one row each, which then asks the
  exact product or layout. Its last answer,
  **My app isn't listed, or I don't know**, asks which brand is on the bed:
  each family, named with its apps, then opens its own question, and **Not
  sure** runs diagnostics.
  You then pick the Bluetooth device, or type its address.
- **Pick any Bluetooth device** lets you choose any device first, then asks the
  same app question. A confidently detected bed suggests its own row.
- **Scan again for beds** and **Browse unsupported BLE devices**, and
  **Combine two beds into one (Dual Bed)** when two beds are set up.

A discovered bed asks first which app or remote controls it, from its detected
family: that family's own question, or the detected bed type's rows. **Another
app or remote** opens the full app list for the same bed. The family question's
**Keep** answer saves the detected route, after a screen that says its controls
are generic, whether it needs pairing, and that **Reconfigure** can choose the
app later; its **Back** returns to the question. Detection never picks an app by
itself, because a bed's name and Bluetooth services do not tell these apps
apart. The Reverie and Sleep Number rows settle the receiver from the bed's
advertised service, and ask only when it does not.

The app or remote you choose then asks its own questions, such as a layout,
handset ID or remote style. The final settings come last, drawn for the route
you chose:

- **Name**, **Bluetooth adapter** and **Disconnect after each command**;
- the settings the app or remote does not set itself, such as the motor count
  or massage, and a bed type's own fields, such as the Octo PIN;
- **Advanced: receiver route**, collapsed, for a bed type with several receiver
  routes (see [Protocol Variants](#protocol-variants)). An app sets its own
  route;
- **Advanced connection and timing**, collapsed: the motor pulse count and
  delay and the idle disconnect timeout.

**Glideaway Motion / Montion app:** Select the explicit MOTION 400, 450, 500 or
600 app entry matching the app's model selection. Layout, massage and light
capabilities follow that choice, with a fixed 300 ms refresh interval. No
advertisement identifies the model. See the [Glideaway guide](beds/keeson.md#glideaway-motion).

**OKIN ORE:** The **Okin ORE (legacy A5 5A)** entry preserves existing legacy
configurations. The accepted Glideaway Motion app uses a separate protocol. Beds controlled with the current Dynasty Bases or INNOVA apps use
the Keeson [MaxCoil Una / Dynasty Bases / Bedsense Bases / Avanti Bases / AMERICANSTAR](beds/keeson.md#ore-comfort-bed-profiles)
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

Beds that support [estimated positions](ESTIMATED_POSITIONS.md) also show
**Estimated positions** in this menu, or one entry per side on a paired bed with
two addresses. It enables and calibrates travel-time estimates for beds without
position feedback. Single-address paired beds do not support estimates yet; see
[Supported Beds](ESTIMATED_POSITIONS.md#supported-beds) for why.

### Changing the app or layout of an existing bed

Some families have a guided change: Configure shows **Change app or layout**
with the bed's current setup. Home Assistant cannot open the guided change from
Configure itself, so start it from the entry's three-dot menu, **Reconfigure**,
or from the bed's repair. Today this covers the
[Vibradorm family](beds/vibradorm.md#guided-setup-and-migration), the
[Jiecang family](beds/jiecang.md#home-assistant-setup), the
[Okin family](beds/okin-nframe.md#home-assistant-setup), the
[Keeson family](beds/keeson.md#home-assistant-setup), the
[Solace family](beds/ff_frame.md#home-assistant-setup), the
[Leggett & Platt family](beds/leggett-platt.md#home-assistant-setup), the
[Sleepy's Elite family](beds/sleepys.md#home-assistant-setup), the
[Customatic and Jordan's apps](beds/okin-nframe.md#customatic-family), the
[Malouf / Lucid family](beds/malouf.md#malouf-base--lucid-base-family), the
[LOGICDATA family](beds/logicdata.md#detection--setup), the
[Jensen / Svane family](beds/jensen.md#home-assistant-setup) and the
[Limoss family](beds/limoss.md#home-assistant-setup). Reconfigure also asks
the Okin question for an Okin CST entry, and the L&P question for an L&P
legacy app entry or a Richmat entry on the L&P QRRM remote, so they can move
to that family's other routes; Configure still changes their own settings.

1. Choose the app you use, then the layout or remote the app shows. The
   question's keep answer leaves the entry exactly as it is. Its label depends
   on the family: **I don't know: keep the current controls** (Jiecang, Leggett
   & Platt), **I don't know: keep the detected controls** (Okin, Keeson, Solace,
   Sleepy's Elite, Malouf / Lucid, LOGICDATA), **Keep the current app**
   (Customatic, Jordan's), **Keep the current controls** (Jensen / Svane,
   Limoss) or **Keep current setup** (Vibradorm).
2. Where the family has exact Bluetooth endpoint or pairing requirements,
   Home Assistant releases its connection and checks the chosen setup. The
   check screen lists its steps. Nothing is saved yet.
3. A review lists the controls that are added and removed, the kept controls
   that change meaning (the same entity under another name), how many keep
   their entity IDs, and the automations and scripts that use a removed
   control.
4. **Apply this change** saves it, only if nobody changed the entry meanwhile.
   The last screen names the new setup and the previous one; to switch back,
   run **Reconfigure** again. **Keep current setup** is the other answer on the
   review.

A failed check shows **Nothing was changed** with **Try again** and **Keep
current setup**. A failed check, a closed window, the keep answer, **Keep
current setup** or a concurrent edit leaves the saved setup unchanged and
working. Choosing a label that resolves to
the saved setup changes nothing. A passed check does not prove the bed's
physical layout or presets, so test the controls after applying a change.

A paired bed is split first, because an app belongs to one physical bed.
Splitting keeps the Bluetooth adapter or proxy, idle disconnect and disconnect
after each command that you chose while combined, and restores the bed type,
app profile and side settings from before the beds were combined.

---

## Profile recommendations

Every configured bed is checked against the integration's existing Bluetooth
identity and app-profile metadata. Under **Settings → System → Repairs**, Home
Assistant may suggest **A better profile may be available**, or ask you to **Check
the profile or protocol variant** when several profiles fit. Weak or unknown identities
stay quiet. A shared Bluetooth service or a new app alone does not prove that
another profile works better.

**Review profile settings** opens Configure. A clear suggestion shows its settings;
an ambiguous match keeps your current selection so you can check your app, physical
remote and product. Nothing changes until you submit settings. Closing them keeps
your profile. Saving this review confirms your selection.

When every suggested profile belongs to the bed's family with a
[guided change](#changing-the-app-or-layout-of-an-existing-bed), **Review
profile settings** opens that guided change instead, because Configure refuses
an app or route change within the family. Applying a change there confirms the
review, and the question's keep answer there keeps the current profile. Closing it
leaves the notice open. A suggestion of another bed type still opens Configure,
which can make that change.

**Keep current profile** (or Ignore) dismisses the assessment across restarts and
updates. Only a materially different profile or candidate set may ask again.
Paired notices identify the physical bed and explain any required split or restore
standalone action; neither side changes automatically. See the
[matching evidence and limits](design/profile-recommendations.md).

### Physical Validation of Setup Changes

Proven offline: config flow tests drive setup, Configure, Repairs and the
guided reconfigure against simulated beds, and check the saved fields and the
refusal of invalid combinations. A passed Bluetooth check proves that the bed
answered on the expected connection, not which motors, buttons or remote layout
it has. Needs real-bed reports: after an app or layout change, whether the
controls Home Assistant shows match the bed's remote and app, and whether each
one moves what it names. This applies to each family's v5 setup change from
[#676](https://github.com/kristofferR/ha-adjustable-bed/issues/676) as it lands.
Report the app and layout you chose, with diagnostics, in the v5 beta feedback
issue.

## Basic Settings

| Setting | Options | Default | Description |
|---------|---------|---------|-------------|
| **Motor Count** | Profile-dependent | 2 | Number of controllable motor sections when the profile uses a generic count |
| **Has Massage** | On/Off | Off | Enable massage controls if your bed supports it |
| **Preferred Adapter** | Auto / Specific adapter | Auto | Which Bluetooth adapter or proxy to use |

Some app profiles add settings that several apps share. Each has one name and
label wherever it appears:

| Setting | Offered by | Description |
|---------|------------|-------------|
| **Enable light controls** (`has_light`) | Logicdata and Jiecang bed apps (default on), FSM Relax and Limoss Remote (default off) | Expose the app's light controls |
| **Bed or chair** (`product_type`) | FSM Relax, Limoss Remote | The product chosen in the app |
| **Reverse motor channel 1–4** (`reverse_motor_1` to `reverse_motor_4`) | FSM Relax, Limoss Remote | The app's per-channel direction flags, sent with every movement |
| **Exact Bluetooth name** (`ble_device_name`) | Motion Bed, MotoMotion, AdjustableM5X5, Adjustable Comfort M1X12 | The unchanged advertised name that identifies the app profile |

Entries that stored `logicdata_app_has_light` or `jiecang_app_has_light` are
migrated to `has_light` when the integration loads.

The adapter choice is a preference. Home Assistant can select another path when
connecting; diagnostics record the actual adapter or proxy used.

### Motor Count Details

| Motors | Controllable Sections |
|--------|----------------------|
| 1 | A single controllable section, when offered by the selected profile |
| 2 | Back + Legs |
| 3 | Head + Back + Legs |
| 4 | Head + Back + Legs + Feet |

Standard OCTO reads its default motor layout from the active `CAP_MOTORCOUNT`
capability. Its OCTO-specific setting defaults to **Auto** and can be changed to
an explicit one-to-four motor layout. Bluetooth names do not select the layout.

For other profiles that show **Motor Count**, count the distinct moving sections
on the physical remote.

### Malouf/Lucid Layout and Memory

Malouf and Lucid receiver entries (Nordic UART or FFE5) have two additional
settings because BLE command framing does not reveal the physical remote layout:

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

Beds whose existing light control is the **Toggle Light** button, including
Tempur/Keeson profiles without light-state feedback, also offer an optional
**Under Bed Lights** light entity. It is disabled by default because its on/off state is an estimate.
To enable it, open the bed's device page under **Settings → Devices & Services**,
show disabled entities, select **Under Bed Lights**, and enable it.

On first use, set the physical light off with the remote before enabling the
entity. Home Assistant initially assumes off and restores its last estimate on
later loads. Enabling or loading the entity sends no light command. Use
`light.turn_on`, `light.turn_off`, and `light.toggle` for subsequent control.
Repeated on or off requests do not toggle the light again; a failed command
leaves the estimate unchanged. The bed card uses the light once enabled.

Home Assistant marks this entity's state as **assumed**. It cannot detect changes
made with the physical remote, the manufacturer's app, the existing Toggle Light
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
| **Idle Disconnect Seconds** | 0-300 | 40 | Auto-disconnect timeout when idle; 0 keeps the bed connected |
| **Stop Discovering New Bluetooth Devices** | On/Off | Off | Suppress automatic discovery of new beds (integration-wide) |
| **Maximum Back Angle** | Greater than 0, up to 180° | 68° | Back/head range for controllers reporting angles |
| **Maximum Legs Angle** | Greater than 0, up to 180° | 45° | Legs/feet range for controllers reporting angles |

### Setting Details

**Disable Angle Sensing**

- Turn this off to enable position feedback and sliders on supported controllers.
- Turn it on if position monitoring interferes with the physical remote. The controller can still require notifications for authentication or other state.
- Setup and Configure show it only for beds that can report positions.
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
- `0` keeps the bed connected while Home Assistant runs, so commands respond without reconnecting. Use it only for mains-powered beds: the held link blocks the vendor app and any Bluetooth remote (RF remotes are unaffected), and it keeps the bed's Bluetooth radio active.
- `0` applies only while Disconnect After Command is off; when that option is on, its one-second handoff wins.
- If a kept link drops, the next command reconnects it. Most beds get no background reconnect timer, because some receivers drop idle links and stop advertising after repeated reconnects. Bed types that already reconnect automatically after a drop keep doing so.

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
For TiMOTION AHF, these defaults apply to finite app-labelled `button.press`
actions; its bounded `hold_control` behavior has separate timing in the
[AHF guide](beds/timotion-ahf.md).

<!-- generated:pulse-defaults -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Bed type | Key | Pulse count | Pulse delay |
|---|---|---|---|
| 1500 Tilt Base (Rondure) | `rondure` | 25 | 50 ms |
| AdjustaMattress app (seven product layouts) | `adjustamattress` | 5 | 200 ms |
| Comfort Enhancements app (choose MC2/MC3/MC4/MC5) | `comfort_enhancements` | 5 | 200 ms |
| Customatic Clarity app (Rize Clarity) | `customatic_clarity` | 8 | 120 ms |
| Customatic Jerome's C app | `customatic_jeromes` | 8 | 120 ms |
| Customatic Remedy app (Rize Remedy) | `customatic_remedy` | 8 | 120 ms |
| eShine app (E2000 / E3000 / E3100 / E5000) | `eshine_okin` | 10 | 300 ms |
| FSM Relax app (explicit chair/bed profile) | `fsm_relax` | 10 | 60 ms |
| Jensen Adjustable Sleep app, JMC400 bed (PIN) | `jensen` | 4 | 300 ms |
| Leggett & Platt WiLinke (MlRM) | `leggett_wilinke` | 10 | 110 ms |
| Limoss / Stawett (TEA encrypted) | `limoss` | 12 | 80 ms |
| Linak (Bed Control, Bed Connect and Performance Series apps): Performance Series (legacy, 300 ms hold cadence) | `linak` `performance_legacy` | 4 | 300 ms |
| Logicdata SimplicityFrame (SILVERmotion) | `logicdata` | 10 | 30 ms |
| Malouf (FFE5 protocol) | `malouf_legacy_okin` | 7 | 150 ms |
| Malouf Base / Lucid Base apps | `malouf_app` | 7 | 150 ms |
| OCTO Smart Control | `octo` | 3 | 350 ms |
| OCTO Smart Control: Octo Remote Star2 | `octo` `star2` | 3 | 50 ms |
| Okin CB24 (SmartBed by Okin, Amada) | `okin_cb24` | 3 | 300 ms |
| Okin CB35 (Sealy Posturematic, DewertOkin Star) | `okin_cb35` | 3 | 300 ms |
| Okin FFE (13/15 series) | `okin_ffe` | 7 | 150 ms |
| Okin ORE (legacy A5 5A) | `okin_ore` | 1 | 300 ms |
| Resident Adjustable Base app (com.okin.resident.release) | `resident` | 4 | 300 ms |
| Richmat / RMControl app | `richmat` | 7 | 150 ms |
| SIMMONS app | `simmons` | 4 | 300 ms |
| SUTA Smart Home (AT protocol) | `suta` | 7 | 150 ms |
| V-MAT Basic app | `vmatbasic` | 34 | 30 ms |

Every other bed type defaults to 10 pulses 100 ms apart.
<!-- /generated -->

Svane Remote app profiles hold a control for its duration instead of a
configurable repeat count: the source refreshes every 100 ms, and the
feet/separate fallback adds 100 ms.

The **Sleepy's Elite app** profile uses its selector-specific app timing and
release behavior; the BOX15/BOX24 defaults describe the existing protocol
profiles. Its cadence is not controlled by the generic motor pulse settings.

### When to Adjust

| Symptom | Solution |
|---------|----------|
| Motors stop moving too soon | Increase pulse count |
| Movement is choppy or jerky | Decrease pulse delay |
| Commands are getting dropped | Increase pulse delay |

---

## Protocol Variants

Some beds support multiple protocol variants, also called receiver routes.
Auto-detection usually works, but you can override if needed.

Setup asks for a route only when the chosen bed type has more than one, and
lists only that bed type's own labelled routes. An app chosen from the bed-type
list sets its route itself. The final settings list the routes in a collapsed
**Advanced: receiver route** section. The routes named after an Okin protocol
(Okin Handle, 7-Byte, Nordic, CB24, CB35, FFE, 64-Bit and ORE) are not rows of
the app list: a discovered bed shows its detected route, the brand list under
**My app isn't listed** lists them, and Configure keeps them by name. Configure lists
the routes of the saved bed type. In a family with a
[guided change](#changing-the-app-or-layout-of-an-existing-bed), the app question chooses the route and Configure
refuses a route change; use **Reconfigure**. Additional
controller-specific choices are documented here:

| Bed type | Choices covered by its guide |
|----------|-----------------------------|
| [Sleepy's Elite app](beds/sleepys.md#explicit-sleepys-elite-app-profile) | Explicit control-box selector for each physical bed, asked after the [Sleepy's question](beds/sleepys.md#home-assistant-setup) |
| [Linak](beds/linak.md#profiles-and-model-variants) | Bed Control and Performance Series |
| [Kaidi](beds/kaidi.md#command-families) | Seat 1, Seat 2, Seat 3, Seat 1+2 |
| [Okin CST](beds/okin-nframe.md#okin-cst) | Rize and Support product profiles, asked by app name in the Okin question for a new bed; Auto retains MF900 behavior |
| [Sleepy's BOX25](beds/sleepys.md#box25-protocol-nordic-uart) | Auto, StarCode, Legacy CB25, under **Advanced** after the Sleepy's question |
| [SBI](beds/keeson.md#protocol-variants) / [Rondure](beds/keeson.md#side-selection-split-king) | Both, Side A, Side B |
| [OKIN CB24](beds/okin-nframe.md#cb24-preset-safety) | Legacy/CBNew and specific SmartBed profiles |
| [Okin DOT](beds/okin-nframe.md#okin-dot) / [Okin 64-bit](beds/okin-nframe.md#okin-64-bit) | Handset or transport-specific selection |

### Keeson Variants

New setups answer the [Keeson question](beds/keeson.md#home-assistant-setup).
Its Keeson answers save one of these variants, and **No app: another Keeson
remote route** lists the remote routes. An existing entry changes its variant
through Reconfigure.

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
| **Avanti Bases** | ORE comfort-bed app profile; motor count picks 2M/3M/4M | Beds controlled with the Avanti Bases app |
| **AMERICANSTAR** | ORE comfort-bed app profile; motor count picks 2M/3M/4M | Beds controlled with AMERICANSTAR 1.0 (1) |
| **Bedsense Bases** | ORE comfort-bed app profile; motor count picks 2M/3M/4M | Beds controlled with the Bedsense Bases app |
| **INNOVA** | App profile, little-endian E5 frames; motor count picks 2M/3M/4M | Beds controlled with the INNOVA app |
| **MaxCoil Una / Dynasty Bases** | ORE comfort-bed app profiles; motor count picks 2M/3M/4M | Beds controlled with the MaxCoil Una or Dynasty Bases app |
| **Restonic BT, remote A / B** | App profiles for the two Restonic BT Remote styles | Beds controlled with the Restonic BT Remote app |
| **Purple** | Purple profile | Purple Smart Base |
| **Ergomotion** | Base protocol with position feedback | Ergomotion-branded beds |
| **Okin** | OKIN FFE (0xE6 prefix) | OKIN 13/15 series |
| **Serta** | Serta MP Remote protocol | Serta Motion Perfect |
| **Sino** | Big-endian packet format | Dynasty, BetterLiving |

### Leggett & Platt Variants

New setups answer the [L&P question](beds/leggett-platt.md#home-assistant-setup),
which picks the route from the app you use. These variants apply only to an
entry saved with the older `leggett_platt` ID, which keeps that ID; Reconfigure
changes its route through the same question.

| Variant | Route | Chosen by the L&P answer |
|---------|-------|--------------------------|
| **Auto** | MlRM when the bed has the WiLinke service, otherwise Gen2 | None; kept for existing entries |
| **Gen2** | [Gen2](beds/leggett-platt.md#gen2-variant), requires pairing | LP Control app with an LP Comfort Connect base |
| **Okin** | [Leggett Okin](beds/okin-nframe.md#leggett-okin-family), requires pairing | Prodigy CE, Prodigy 2, Prodigy 2L or U Series app, or LP Control with an LP BED receiver |
| **MlRM** | [MlRM](beds/leggett-platt.md#mlrm-variant) | L&P Adjustable Base app with an MlRM base |

### Richmat Variants

Setup asks the packet dialect under **Advanced** after the
[Richmat question](beds/richmat.md#home-assistant-setup)'s RMControl,
SleepFunction, SVEN & SON or Richmat remote answer. Configure changes it.

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

These variants apply to newer Sleep Number Fuzion bases (`Smart bed *`). Older BAM/MCR beds such as some i8 / 360 FlexFit 2 models expose both firmness sides from one entry and do not use this setting. Setup asks the side once the [Sleep Number question](beds/sleep_number.md#detection) has settled on a Fuzion base; Configure changes it.

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
Setup reaches them through the Okin row's question: **No app: Okimat or OKIN
handset code**, then the code printed on the handset. The table below gives
common examples; the setup selector contains the complete handset list. For
beds controlled by the FurniMove app, including RF ECO BT receivers, answer
**FurniMove / OKIN Smart Remote app** for the separate
[FurniMove profile](beds/furnimove.md) with its exact handset selector. Other OKIN app profiles retain their own evidence and options. For example, RF-TOPLINE `82620` exposes Back, Legs, Flat, and the
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

An app profile is the integration's description of one app or remote: its
layouts, controls, timing and setup questions. Apps that send the same wire
format share one codec guide, with a section per profile; beds with their own
format have their own guide. Each profile's **Setup** part explains the
questions setup asks and which settings it hides. The
[codec and profile architecture](design/protocol-codecs.md) explains the split.

Choose the app, model or remote supplied with your bed when setup asks for it.
These choices determine which controls are available. Related choices are
listed together below, with links to their profile sections.

1. Let automatic discovery identify the controller where possible.
2. If adding manually, find your brand or app in [Supported Beds](../README.md#supported-beds).
   You can type an app's name to search the bed-type list, for example
   **INNOVA app (Keeson)**, **Power Bob** or **HomeKobo**. Not every app is
   named in the list. If yours is not found, its guide's **Apps** table names
   the profile it uses. Choosing an app sets its protocol variant for you. A
   saved compatibility ID,
   such as `okimat`, keeps working; setup shows its friendly name and Configure
   adds the saved ID in brackets.
3. Match any requested model or remote to your physical bed. Shared Bluetooth
   names and services do not always identify the right layout.

Existing entries keep their selection until you change it. Beds added before
4.1.0 whose bed type gained app profiles are asked, through a repair, which
app they use; see [the upgrade prompt](TROUBLESHOOTING.md#new-app-profiles-are-available-repair).
For a two-address pair, settings belong to each physical bed. Each receiver's
own app settings, such as its motor count, massage or light settings, are under
**Configure → Change left receiver settings** or **Change right receiver
settings**. To change a receiver's bed type or app, split the pair, configure
that side, then combine them again.

| Bed or brand | Model and remote settings |
|--------------|---------------------------|
| Sleepy's Elite | [One question](beds/sleepys.md#home-assistant-setup) for the MFRM Sleepy's Elite app or the BOX15, BOX24 or BOX25 receiver. The [app profile](beds/sleepys.md#explicit-sleepys-elite-app-profile) asks the control box the app lists, for each physical receiver. Change an existing bed's app, control box or BOX25 dialect with **Reconfigure**. |
| OKIN SleepEase / DoubleSleep | [SleepEase setup](beds/okin-nframe.md#okin-sleepease): select the saved app model independently of the advertisement-selected P1/P2/P3 driver. Keep each physical receiver's settings separate. Sensor sides do not select motor halves. |
| Keeson | Answer the [Keeson question](beds/keeson.md#home-assistant-setup) with your app: [Adjustable Lite](beds/keeson.md#adjustable-lite-profile), [Simon Li / Heal Every Night / OKIN-Seating](beds/keeson.md#simon-li-heal-every-night-and-okin-seating-profiles), [INNOVA](beds/keeson.md#innova-profile), [MaxCoil Una / Dynasty Bases / Bedsense Bases / Avanti Bases / AMERICANSTAR](beds/keeson.md#ore-comfort-bed-profiles), or [Restonic BT](beds/keeson.md#restonic-bt-profiles). It then asks the app's 2M, 3M or 4M screen, or the Restonic remote style, where the app has one. |
| Tempur Sleeptracker-AI | [Processor setup](beds/sleeptracker.md): choose this app profile for ProSmart / ProSmart Air and ActiveBreeze. Select the actual processor endpoint and app layout, unit number, snapshot ordinal, restricted session, processor type and foundation metadata. Add a separate processor entry when the current address exposes UART. Axes and massage come from the app layout; position feedback is unavailable. |
| Richmat | [One question](beds/richmat.md#home-assistant-setup) for the app: [RMControl](beds/richmat.md#rmcontrol) then asks its product code and side; [Revive Control / Best Mattress / Blvd Home / HARMONY / Idealbed](beds/richmat.md#richmat-mh-apps) the app's model, or Auto from the Bluetooth name; [Avocado Eco Base / CoasterSleep / Forty Winks / Milemont / Superior](beds/richmat.md#classic-richmat-apps) the app's four-character layout, with the third-service fallback an explicit opt-in. Without one of these apps, the [Richmat remotes](beds/richmat.md#richmat-remotes) ask the remote code. Configure changes the same answers and lists each app by name, so an entry can switch apps or opt in to RMControl and out of it. |
| Leggett & Platt | Answer the [L&P question](beds/leggett-platt.md#home-assistant-setup) with your app: [Prodigy CE, Prodigy 2, Prodigy 2L or U Series](beds/okin-nframe.md#leggett-okin-family) sets the layout; LP Control and the L&P Adjustable Base app also name the receiver or remote. [L&P legacy](beds/richmat.md#lp-legacy-app): model, protocol mode and confirmed GATT characteristics. |
| Solace / Woosa | Answer the [Solace question](beds/ff_frame.md#home-assistant-setup) with your app: HomeKobo, Sealy MotionFlex or Sweet Night keep name-based Solace routing; [Woosa Sleep](beds/ff_frame.md#woosa-sleep) is variant `woosa`. |
| Jensen / Svane | Answer the [Jensen / Svane question](beds/jensen.md#home-assistant-setup) with your app and bed: the Jensen Adjustable Sleep app with a [JMC400](beds/jensen.md) bed (then its PIN) or a [LinOn](beds/jensen.md#linon) bed, or the [Svane Remote](beds/svane.md) app with a Svane Bed or a JMC400 bed. Change an existing bed's app or bed with **Reconfigure**. |
| Jiecang | [App profiles](beds/jiecang.md#choosing-a-profile): choose the app ([ERGOBALANCE](beds/jiecang.md#ergobalance-dreamask), [Dream Motion](beds/jiecang.md#dream-motion-dreamotion), [Dream Motion HD](beds/jiecang.md#dream-motion-hd) or [Comfort Motion](beds/jiecang.md#comfort-motion-app)), then layout and local light/massage presence, with the transport under **Advanced**. Comfort Motion supports three layouts and G1/G2 only. Layouts, transports and default timing per profile are in the [generated profile tables](beds/jiecang.md#choosing-a-profile). |
| LOGICDATA | One question for the app ([SILVERmotion / SimplicityFrame](beds/logicdata.md), [MOTIONrelax phone or tablet](beds/jiecang.md#motionrelax-phone-and-tablet), or [Sleep Smart](beds/jiecang.md#sleep-smart-air-mattress-bed) bed base or [separate air pump](beds/logicdata-sleep-smart.md)), then the app's command family and the layouts that family allows (MOTIONrelax P2 is the middle layout), light and transport. Configure keeps the light; another app or layout goes through Reconfigure. |
| Malouf / Lucid | Answer the [Malouf question](beds/malouf.md#choosing-a-profile) with your app or receiver: the [Malouf Base and Lucid Base apps](beds/malouf.md#malouf-base--lucid-base-family) ask the exact model, primary/secondary role and transport; the Nordic UART and FFE5 receivers ask the [layout and memory positions](#malouflucid-layout-and-memory). Change an existing bed's app with **Reconfigure**. |
| Customatic / Jordan's | One question per brand: [Clarity / Jerome's / Remedy](beds/okin-nframe.md#customatic-family) or [Z-Series](beds/okin-nframe.md#customatic-z-series) with its model; [Serenity](beds/okin-nframe.md#jordans-serenity) or [Tranquil](beds/okin-nframe.md#jordans-tranquil). Change an existing bed's app with **Reconfigure**. |
| Vibradorm | [Caresse / Werkmeister](beds/vibradorm.md#caresse-and-werkmeister), [VMAT](beds/vibradorm.md#vmat), [V-MAT Basic](beds/vibradorm.md#v-mat-basic): app, exact remote or product, and offered light settings. |
| Sleep Number | [Setup confirms the transport](beds/sleep_number.md#detection) from its advertised service (Fuzion or BAM/MCR), then a Fuzion entry asks its side. Configure lists both transports. |
| Reverie | [Setup confirms the receiver](beds/reverie.md#setup-and-model-selection) from its advertised service (Protocol 110 or 108), then asks the model the app shows. Configure lists both receivers. |
| Remacro | [One question for Slumberland, The Brick or Jerome's](beds/remacro.md#home-assistant-setup), offering the apps that list the advertised model, or all three when no model is seen or none lists it; Configure changes the app's protocol variant. The advertised company ID selects the model. |
| FurniMove / OKIN Smart Remote | Answer the [Okin question](beds/okin-nframe.md#home-assistant-setup) with **FurniMove / OKIN Smart Remote app**, then the [exact handset ID](beds/furnimove.md); also includes a guided repair for older RF ECO BT entries. |
| SIMMONS | [Regular/inclined bed and packet format](beds/okin-nframe.md#simmons). |
| AdjustaMattress | [Choose the app, BLE model and product layout](beds/keeson.md#adjustamattress). Four models and seven independent layouts; generic motor/massage settings do not add controls. Each physical side owns its profile. |
| Comfort Enhancements | [Choose MC2/MC3/MC4/MC5](beds/keeson.md#comfort-enhancements). The layout fixes controls, massage/light and memory capacity; held refresh is 200 ms. Each physical side owns its layout. |
| Adjustable bed (Lumbar) | [Automatic or fixed command table](beds/okin-nframe.md#adjustable-bed-lumbar). |
| StarCode apps | One question for the app, then its own settings. Configure lists each StarCode app, so an entry can move to another without being removed. [M5X4](beds/okin-nframe.md#adjustablem5x4): command and transport selectors. [M5X5](beds/starcode-m5x5.md): layout and up to three configured lift entries. [M1X12](beds/starcode-m1x12.md): layout and up to two ELEVATE accessories. |
| Motion Bed | [Layout and retained settings](beds/ff_frame.md#motion-bed); preserve the original Bluetooth name. |
| MotoMotion | [The exact Bluetooth name](beds/motomotion.md#motomotion), which selects the panel and its feature flags; preserve its case. |
| Limoss | [One question](beds/limoss.md#home-assistant-setup) for the Limoss Remote or FSM Relax app, or the older controls. [Limoss Remote](beds/limoss.md#limoss-remote): bed/chair layout, light/massage and reversal settings. Change an existing bed's app with **Reconfigure**. |
| FSM Relax | Answer the [Limoss question](beds/limoss.md#home-assistant-setup) with the FSM Relax app, then its [bed/chair layout, light/massage, reversal settings and memory names](beds/limoss.md#fsm-relax). |
| GM Control | [Exact product/configuration and app side](beds/gmmotor.md#detection--setup); independent MM/SXB module entries. |
| Legacy OKIN CB24 | [Single-address controls](#single-address-left--right-controls): both sides, Side A / Left, or Side B / Right. |
| Keeson app family | [Tempur Curve, Q-Plus Adjustable Remote, Serta MP Remote, Omazz Adjusto III, Ergomotion, ROW Control, Ergo Slim and TEMPUR AU](beds/keeson.md#keeson-layout-app-family): the exact app and the layout it shows; Q-Plus also has a Both/Side A/Side B selector. |
| Ergomotion 4.0 | [Exact product, or another catalog product by name and feature keys](beds/keeson.md#ergomotion-40-home-assistant-setup). |
| BF / Cherish | [The exact app](beds/keeson.md#bf-and-cherish); it fixes the layout and movement refresh. |
| Eshine | [Explicit app profile](beds/richmat.md#eshine) with a fixed head, feet, lumbar, pillow, massage and light layout. |
| Kaidi | [ISleep](beds/kaidi.md#isleep): product, room ID and actuator descriptor. [Floyd Home](beds/kaidi.md#floyd-home): product 139. |
| BedSense | [Layout, or the Bluetooth-name layout rule](beds/ff_frame.md#bedsense). |
| Casper Base | [PRO/MAX product](beds/casper-base.md#home-assistant-setup); sleep sensors and the RCRM handset are separate entries. |
| HJBed | [The exact app product](beds/richmat.md#hjbed). |
| Good Vibe Sleep | [The exact product, configuration or remote alias](beds/richmat.md#good-vibe-sleep); independent RM-/HJ- sleep sensors are separate entries with their own type 1 or type 2 profile. App side selection is local; light duration and supported snore settings are device controls. |
| eShine E2000 / E3000 / E3100 / E5000 | [The same product selector as the app](beds/okin-nframe.md#eshine); E3000/E3100 is one choice, and name or UART matches never choose it. The profile owns its axes, massage/light features and 300 ms refresh. Each side of a two-address pair keeps its own profile; single-address split controls are unavailable. |

### Octo PIN

**Setting:** 4-digit PIN code

Standard OCTO reports whether PIN control is enabled, whether a PIN is set, and
whether the receiver is unlocked. Configure a four-digit PIN only when the
receiver reports one is required. Star2 uses a separate protocol and has no
Standard OCTO PIN exchange.

**How to configure:**
1. Go to **Settings** → **Devices & Services**
2. Find your Adjustable Bed and click **Configure** (gear icon)
3. Choose **Change settings** from the menu
4. Enter your 4-digit PIN in the "Octo PIN" field

**Finding your PIN:**
- Use the PIN set in the OCTO Smart Control app; it is not the OS Bluetooth pairing code.
- If your bed works without a PIN, leave this field empty

Standard OCTO setup verifies PIN acceptance without moving the bed. Setup finishes
only when the PIN is accepted or the controller confirms no PIN is required.
An inconclusive check leaves the entry unsaved and can be retried; it does not
mean the PIN is wrong. After a PIN lock challenge, the integration retries the
configured PIN once after one second. It does not use a periodic PIN timer. See
[OCTO Smart Control](beds/octo.md#pin-control).

### Jensen PIN

**Setting:** 4-digit PIN code (default: 3060)

Jensen JMC400 beds require PIN authentication for BLE control.

**How to configure:**
1. Go to **Settings** → **Devices & Services**
2. Find your Adjustable Bed and click **Configure** (gear icon)
3. Choose **Change settings** from the menu (or a side's own settings, for a
   two-address pair)
4. Enter your 4-digit PIN in the "Jensen PIN" field

Setup asks the PIN when you choose the Jensen Adjustable Sleep app with a JMC400 bed.

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
| **GGRM / HJH89** | Head, Feet, Pillow (head tilt), Lumbar, Flat, Zero G, Anti-snore, Memory, Massage, Lights |
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
A bed that advertises as `QRRM` does not identify its remote, so check the
label. The HJH89 remote, for example, prints `GGRM` beside a QR code that
encodes the same code; select **GGRM / HJH89** for it.
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
2. Reduce "Idle disconnect seconds" for faster automatic disconnection (and avoid `0`, which keeps the bed connected)
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

SBI, Rondure, legacy CB24, Sleep Number Fuzion, Kaidi `seat_1_2`, and Keeson
and Ergomotion 4.0 P1 beds can reach both physical sides through one Bluetooth address. Open the bed's
integration options and choose
**Enable Left / Right / Both controls** to expose the same paired-bed surface
used by two-address beds.

This conversion keeps the existing config entry, Bluetooth address, device,
and standalone entity history. It is reversible through **Restore standalone
controls**, which keeps the Bluetooth adapter, idle disconnect and disconnect
after each command chosen while combined. Existing entries do not change
automatically.

Routing remains protocol-native:

- SBI and Rondure use their Side A, Side B, and native broadcast packets.
- Legacy CB24 uses selectors `0xAA` (left/A), `0xBB` (right/B), and `0x00`
  (both). The selector is also available in initial setup and options.
- Sleep Number Fuzion serializes left then right over its one command lock.
- Keeson's explicit BaseI4/BaseI5 and Ergomotion variants, the Ergomotion bed
  type and Ergomotion 4.0 P1 products send their Left (`02`) and Right (`01`)
  side frames. Their position feedback cannot identify a side, so side-control
  mode disables it. See
  [Keeson Base](beds/keeson.md#base-basei4i5) and
  [Ergomotion 4.0](beds/keeson.md#ergomotion-40-home-assistant-setup).
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

### Two Independent Frames

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
motor pulses, Disconnect After Command, idle timeout and its own app's settings.
These changes apply only to the selected receiver, without splitting the bed. **Change settings**
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
combining entries. To undo it, choose **Split into two beds** in the pair's options;
the side entries are restored and combined controls are removed. Update any
automation that targeted the combined controls.

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
both covers. Unlike the paired-bed controls, this simple script does not stop
the other side automatically if one side fails.

## Dashboard Card Graphics and Dialog

These card options are off by default, so an existing card looks and behaves
as before. Each one is in the card's visual editor, for both layouts unless
noted.

| Option | Default | Effect |
|--------|---------|--------|
| `show_percentage_graphic` | `false` | Draws percentage position feedback and estimates as a schematic pose, from flat at 0% to fully raised at 100%. Labels keep the percentage. Degree feedback keeps its measured angle |
| `show_lumbar_graphic` | `false` | Adds a separate lumbar section between head and feet, with its own label, and orders readouts head, lumbar, feet. Beds without a lumbar motor keep two panels |
| `show_graphic_labels` | `true` | `false` hides only the labels beneath the graphic. Compact readouts, tooltips and controls stay |
| `open_dialog` | `false` | Compact layout only. Clicking the bed graphic or the expand button opens the full card in a dialog instead of following `navigation_path` |
| `dialog_config` | none | Full-card options used only inside the dialog |

The percentage pose uses a fixed 0 to 75° drawing range. It is not your bed's
physical angle, and the lumbar geometry is not a model of the bed's linkage.
If either the head or feet panel has no numeric feedback, the card shows the
unavailable placeholder, never a flat bed. Unknown lumbar feedback draws only
the lumbar section faint, dotted and flat, with `?`. With either option on,
each label shows the motor name above its value.

On a bed with [estimated positions](ESTIMATED_POSITIONS.md), an estimate never
looks like measured feedback. Without the percentage graphic, the card draws
only a tracking estimate, dashed and in degrees, when the axis' maximum angle
is set. With it, every estimate state is drawn as a percentage pose, and a
compact card shows the matching chip on its graphic:

| Position | Drawn as | Label |
|----------|----------|-------|
| Measured | Solid | `40%` |
| Estimated | Dashed and translucent | `≈ 40%` |
| Unconfirmed after a restart | Grey and dashed, at the last estimate | `Was ≈ 40%` |
| Unknown, or not calibrated | Faint, dotted and flat | `?` |

A measured position gets no chip or caption, only its labels. The lumbar
section follows the same rule. Back, legs, head, feet and the standalone TV
lift support estimates. The lift uses a percentage readout, without a bed-angle
graphic. On an estimated bed the lumbar section is unknown.

### Full card in a dialog

The dialog shows the full card for the same bed and side, with live state and
every section the bed has. It opens and closes without sending a command, and
closes with **Close**, Escape or a click on the backdrop. Holds, renewable
holds, [tap to move](DASHBOARD_CARD.md#tap-to-move) and Stop work as on the full
card. Closing the dialog during a movement sends STOP.

In the compact editor, turn on **Open full card in a dialog**, then select
**Configure dialog full card** to edit the dialog with the full-card editor.
Those changes are saved under `dialog_config`, and **Back to compact
configuration** returns to the compact settings. Turning the dialog off keeps
`dialog_config` for later. The dialog always uses the card's bed and the full
layout, and it never opens another dialog or navigates.

```yaml
type: custom:adjustable-bed-card
device_id: YOUR_BED_DEVICE_ID
layout: compact
show_percentage_graphic: true
show_lumbar_graphic: true
open_dialog: true
dialog_config:
  show_massage: false
  show_connection: false
  section_order:
    - graphic
    - motors
    - presets
    - memory
```

---

## Next Steps

- **Having connection issues?** See [Troubleshooting](TROUBLESHOOTING.md)
- **Want to learn about your bed's protocol?** See [Supported Actuators](SUPPORTED_ACTUATORS.md)
- **Setting up Bluetooth?** See [Connection Guide](CONNECTION_GUIDE.md)

### Resident Adjustable Base

Choose the explicit Resident Adjustable Base app profile for
`com.okin.resident.release`. It fixes the two-motor layout, massage, disabled
angle sensing and command cadence. The pulse count still bounds HA motor taps.
There is no variant, model or remote-code question. See the
[Resident guide](beds/okin-nframe.md#resident-adjustable-base). A pair of two
receivers keeps each receiver's app identity; a one-address pair is unsupported.
