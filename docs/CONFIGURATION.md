# Configuration Guide

Options depend on the selected controller and its reported capabilities; not
every bed shows every field. The integration requires Home Assistant 2026.11.0 or
newer.

## Table of Contents

- [Accessing Configuration](#accessing-configuration)
- [Basic Settings](#basic-settings)
- [Toggle-Only Under-Bed Lights](#toggle-only-under-bed-lights)
- [Advanced Settings](#advanced-settings)
- [Movement per tap](#movement-per-tap)
- [Bed Model or Remote](#bed-model-or-remote)
- [Bed-Specific Settings](#bed-specific-settings)
- [Single-Address Left / Right Controls](#single-address-left--right-controls)
- [Split-King / Controller sync](#split-king--controller-sync)
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
  every row of the bed-type list named brand first, where a family's row
  opens its own question. **Not sure, or not listed** offers the detected
  controls when you picked the device first, and otherwise runs diagnostics.
  You then pick the Bluetooth device, or type its address.
- **Pick any Bluetooth device** lets you choose any device first, then asks the
  same app question. A confidently detected bed suggests its own row.
- **Scan again for beds** and **Browse unsupported Bluetooth devices**, and
  **Combine two beds into one (Dual Bed)** when two beds are set up.

A discovered bed asks first which app or remote controls it, from its detected
family: that family's own question, or the detected bed type's rows. **Another
app or remote: search every app** opens the full app list for the same bed. The family question's
**Keep the detected or saved controls** answer saves the detected route, after a screen that says its controls
are generic, whether it needs pairing, and that **Reconfigure** can choose the
app later; its **Back** returns to the question. Detection never picks an app by
itself, because a bed's name and Bluetooth services do not tell these apps
apart. The Reverie and Sleep Number rows settle the receiver from the bed's
advertised service, and ask only when it does not.

The app or remote you choose then asks its own questions, such as a layout,
handset ID or remote style. The final settings come last, drawn for the route
you chose:

- **Name**, **Bluetooth adapter** and **Bluetooth connection** (with its
  seconds when it stays connected for a while);
- the settings the app or remote does not set itself, such as the motor count,
  massage or **Read bed position**, and a bed type's own fields, such as the
  Octo PIN. A setting the bed ignores is not shown;
- **Advanced: bed model or remote**, collapsed, for a bed type with several
  models or remotes (see [Bed Model or Remote](#bed-model-or-remote)). An app
  sets its own;
- **Movement**, collapsed: **Movement per tap**.

Some apps need a choice no advertisement can make, such as the model in the
Glideaway Motion app. Each bed guide's setup section says what to pick.

**Older ORE remote**, under **Okin (other receivers)** in the brand list, keeps
older ORE setups working. Beds you control
with the Dynasty Bases, MaxCoil Una, Bedsense Bases, Avanti Bases,
AMERICANSTAR or INNOVA app use [that app's row](beds/keeson.md#ore-comfort-bed-profiles)
instead. Home Assistant does not discover ORE beds automatically, because their
Bluetooth service is shared with unrelated devices such as Apple TVs
([#577](https://github.com/kristofferR/ha-adjustable-bed/issues/577)); add them
with **Pick any Bluetooth device**.

### Options (After Setup)

To adjust settings after setup:

1. Go to **Settings > Devices & services**
2. Find "Adjustable Bed" and select **Configure** (gear icon)
3. Choose **Change settings** from the menu
4. Adjust settings and click **Submit**

![Configuration options location](https://github.com/user-attachments/assets/8d6dc2b9-7df2-48dc-9ea5-61aaadce6c63)

Configure changes the settings of the bed type and app the entry already runs.
To change the bed type, app or route, use **Reconfigure** (below).

Beds that support [estimated positions](ESTIMATED_POSITIONS.md) also show
**Estimated positions** in this menu, or one entry per side on a paired bed with
two addresses. It enables and calibrates travel-time estimates for beds without
position feedback. Single-address paired beds do not support estimates yet; see
[Supported Beds](ESTIMATED_POSITIONS.md#supported-beds) for why.

### Changing the bed type, app or layout of an existing bed

Every bed changes its bed type, app or layout from the entry's three-dots menu,
**Reconfigure**, or from the bed's repair. A bed in a family with a guided
change gets that family's question; any other bed chooses from the full
bed-type list, then its route where the bed type has several, then the
questions a new bed of that type would answer. Guided changes cover the
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
to that family's other routes.

1. Choose the app you use, then the layout or remote the app shows. The
   question's keep answer, **Keep the detected or saved controls**, leaves the
   entry exactly as it is; when you add a bed it keeps the route detection
   chose.
2. Where the family has exact Bluetooth endpoint or pairing requirements,
   Home Assistant releases its connection and checks the chosen setup. The
   check screen lists its steps. Nothing is saved yet.
3. A review lists the controls that are added and removed, the kept controls
   that change meaning (the same entity under another name), how many keep
   their entity IDs, and the automations and scripts that use a removed
   control.
4. **Apply this change** saves it, only if nobody changed the entry meanwhile.
   The last screen names the new setup and the previous one; to switch back,
   run **Reconfigure** again. **Keep the current setup** is the other answer on the
   review.

A failed check shows **Nothing was changed** with **Try again** and **Keep
the current setup**. A failed check, a closed window, the keep answer, **Keep
the current setup** or a concurrent edit leaves the saved setup unchanged and
working. Choosing a label that resolves to
the saved setup changes nothing. A passed check does not prove the bed's
physical layout or presets, so test the controls after applying a change.

A combined bed is separated first, because an app belongs to one physical bed.
**Separate into two beds** keeps the Bluetooth adapter or proxy and
**Bluetooth connection** you chose while combined, and restores the bed type,
app and side settings from before the beds were combined.

---

## Profile recommendations

Every configured bed is checked against the integration's existing Bluetooth
identity and app-profile metadata. Under **Settings > System > Repairs**, Home
Assistant may suggest **A better profile may be available**, or ask you to **Check
the app or remote** when several profiles fit. Weak or unknown identities
stay quiet. A shared Bluetooth service or a new app alone does not prove that
another profile works better.

**Review profile settings** opens **Reconfigure**, with a single suggested app
or bed type preselected; an ambiguous match starts from your current selection so
you can check your app, physical remote and product. For a bed in a family with a
[guided change](#changing-the-bed-type-app-or-layout-of-an-existing-bed), the
family's question opens, and its **Another app or remote: search every app** answer reaches every
other bed type. Applying a change there confirms the review; choosing the current
setup again, or the question's keep answer, keeps the current profile. Closing it
leaves the notice open. A review about a Richmat remote setting alone opens
Configure, where saving the settings confirms it.

**Keep the current setup** (or Ignore) dismisses the assessment across restarts and
updates. Only a materially different profile or candidate set may ask again.
Notices for a combined bed name the physical bed and say whether you need to
separate the beds or remove the Left, Right and Both controls first; neither
side changes automatically. See the
[matching evidence and limits](design/profile-recommendations.md).

## Basic Settings

| Setting | Options | Default | Description |
|---------|---------|---------|-------------|
| **Number of motors** | Profile-dependent | 2 | Number of controllable motor sections when the profile uses a generic count |
| **Massage controls** | On/Off | Off | Enable massage controls if your bed supports it |
| **Bluetooth adapter** | Automatic / a specific adapter or proxy | Automatic | Which Bluetooth adapter or proxy to use |

Some app profiles add settings that several apps share. Each has one name and
label wherever it appears:

| Setting | Offered by | Description |
|---------|------------|-------------|
| **Enable light controls** (`has_light`) | Logicdata and Jiecang bed apps (default on), FSM Relax and Limoss Remote (default off) | Expose the app's light controls |
| **App product, model or layout** (`product_type`) | FSM Relax, Limoss Remote | The product chosen in the app |
| **Reverse motor 1** to **Reverse motor 4** (`reverse_motor_1` to `reverse_motor_4`) | FSM Relax, Limoss Remote | The app's per-channel direction flags, sent with every movement |
| **Exact Bluetooth name** (`ble_device_name`) | Motion Bed, MotoMotion, AdjustableM5X5, Adjustable Comfort M1X12 | The unchanged advertised name that identifies the app profile |

Entries that stored `logicdata_app_has_light` or `jiecang_app_has_light` are
migrated to `has_light` when the integration loads.

The adapter choice is a preference. Home Assistant can select another path when
connecting; diagnostics record the actual adapter or proxy used.

### Motor Count Details

| Motors | Controllable Sections |
|--------|----------------------|
| 1 | A single section, such as a TV or bed lift or a stair lift; offered only where the app or remote has one motor |
| 2 | Back + Legs |
| 3 | Head + Back + Legs |
| 4 | Head + Back + Legs + Feet |

Standard OCTO reads its motor count from the bed. Its **Octo motor count**
setting defaults to **Automatic** and can be set to one to four motors.

For other beds that show **Number of motors**, count the distinct moving sections
on the physical remote.

### Malouf/Lucid Layout and Memory

Malouf and Lucid receiver entries (Nordic UART or FFE5) have two additional
settings because BLE command framing does not reveal the physical remote layout:

| Setting | Options | Default | Description |
|---------|---------|---------|-------------|
| **Malouf/Lucid motor layout** | Back + legs; add head tilt; add lumbar; four motor; Hi-Lo | Automatic | Controls which motor entities are exposed |
| **Malouf/Lucid memory positions** | Automatic, 1, 2 | Automatic | Must match the memory buttons on the physical remote |

Automatic uses back + legs for a two-motor entry, head tilt for a three-motor entry,
and the standard head-tilt + lumbar layout for a four-motor entry. Hi-Lo must be
chosen by hand, because the bed does not report it. A two-motor layout defaults to one memory
position; other layouts default to two.

These settings do not depend on which receiver setup detected. Lucid L600 has
been sold with two different Okin controllers, so the model name alone does
not decide the receiver.

---

## Toggle-Only Under-Bed Lights

Beds whose existing light control is the **Toggle light** button, including
Tempur/Keeson profiles without light-state feedback, also offer an optional
**Under-bed lights** light entity. It is disabled by default because its on/off state is an estimate.
To enable it, open the bed's device page under **Settings > Devices & services**,
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
| **Read bed position** | On/Off, beds that report a position | On | Shows the position and allows moving to a set position |
| **Refresh positions while idle** | On/Off, Linak only | On | Periodically reconcile positions when idle polling is allowed |
| **Bluetooth connection** | Release right after each command / Stay connected for a while / Always stay connected | Bed-specific | How long the link stays open after a command |
| **Seconds to stay connected** | 1-300 | 40 | Shown for "Stay connected for a while" |
| **Movement per tap** | Usually 1-100; a few beds allow more | Bed-specific | How many times a tap repeats its command |
| **Maximum back angle (degrees)** | Greater than 0, up to 180° | 68° | Back/head range for controllers reporting angles |
| **Maximum legs angle (degrees)** | Greater than 0, up to 180° | 45° | Legs/feet range for controllers reporting angles |

A form shows only the settings the bed uses. **Massage controls** is left
out for beds with no massage commands or that turn massage on themselves; the
maximum angles are left out where the frame's travel is fixed (for example
Paramount, Serta MP Remote, Q-Plus and BedJet); a motor count with only one
choice is left out; **Movement per tap** is left out for beds that never
repeat a tap; and **Bluetooth connection** is left out for beds that
must stay connected (DoubleSleep, GM Sleep, Okin RF Eco BT, Richmat sleep
receivers and Sleep Number MCR).

### Setting Details

**Read bed position**

- On by default for beds that report their position. Turn it off if position
  monitoring interferes with the physical remote. The controller can still
  require notifications for authentication or other state.
- Shown only for beds that can report positions. A bed that reports none
  stores nothing.
- Releasing the BLE link is separate: use **Bluetooth connection** or the
  Disconnect button to let a remote or app reconnect.
- When a command asks for a position read afterwards, it happens in the
  background while the link stays open, or before the link is released with
  **Release right after each command**. No read is made when another command
  is waiting. An accepted target is never treated as a measured position;
  missing or stale feedback can prevent a seek, see
  [position troubleshooting](TROUBLESHOOTING.md#position-commands-and-reported-state).

**Refresh positions while idle**

- Linak can periodically reconnect to catch up with moves made using the physical remote.
- This requires **Read bed position** and a **Bluetooth connection** other than
  **Release right after each command**.
- Turn it off to avoid background position connections. Positions still refresh during supported Home Assistant operations.

**Bluetooth connection**

Most beds accept one Bluetooth connection at a time, so the link Home
Assistant holds blocks the physical Bluetooth remote and the bed's app.

- **Release right after each command**: keeps the link for one second between
  rapid commands, then releases it. New commands restart that window. This is
  the default for most beds. Periodic position polling stays off while idle,
  and initial position and light-state hydration get one attempt.
- **Stay connected for a while**: keeps the link for **Seconds to stay
  connected** after the last command (40 by default), so commands in that
  window respond without reconnecting. This is the default for beds whose
  controls keep state on the connection, and for LP Comfort Connect (Leggett
  & Platt Gen2), whose reconnects need its bond. If an LP Comfort Connect
  reconnect stalls, it keeps the link until you disconnect it or Home
  Assistant restarts.
  If the bed drops the link during that window, Home Assistant reconnects it
  once, and the window still ends at the same time. If that link drops too,
  or after the window, the next command reconnects.
- **Always stay connected**: keeps the link while Home Assistant runs. Use it
  only for mains-powered beds: it blocks the vendor app and any Bluetooth
  remote (RF remotes are unaffected) and keeps the bed's radio active. If the
  link drops, the next command reconnects it.
- Concurrent combined-bed actions retain both links until both sides finish,
  including STOP cleanup, then start the handoff window together. Sequential
  pairs still release one side before connecting the other.
- The explicit Disconnect button releases the link immediately.
- Diagnostics list the connection setting the bed actually uses, including
  the bed's own default when you have not changed it.

Connection attempts use one timing for every bed: a 25-second connect timeout
(shorter on a few beds whose app uses one) and three attempts with 3 and 6 second backoff. Multiple usable Bluetooth paths
receive a larger bounded retry budget; see
[connection routing](CONNECTION_GUIDE.md#multiple-adapters-and-proxies).

**Maximum Angles**

- These fields appear only for controllers using degree-based feedback, not percentage-based controllers, and not where the frame's travel is fixed.
- Match the range supported by your bed. They control position conversion and validation, not the hardware's mechanical limits.

**Timed Move**
- `adjustable_bed.timed_move` moves for at most the time you give it, counted once the bed is connected and ready, so the whole action can take a little longer. See [the command lifecycle](COMMAND_LIFECYCLE.md) for the details.

### Finding new beds automatically

Home Assistant suggests nearby beds as it sees them. To stop that once all your
beds are added, go to **Settings > Devices & services > Add Integration >
Adjustable Bed**, choose **Find new beds automatically** and turn off
**Suggest newly found beds**. It applies to the whole integration. Adding a bed
from that list still works either way.

---

## Movement per tap

A tap on a movement control repeats its command a number of times, a fixed
interval apart. **Movement per tap** (usually 1-100) sets the number of repeats; the
interval is each bed's own and is not a setting.

### Default Values by Bed Type

These are configuration defaults for ordinary movement pulses. App/product
profiles and detected controller variants can have their own timing. Presets,
memory programming, and release sequences can use different controller-defined
timing; these settings do not replace it. See the bed's [guide](README.md#bed-guides).
For TiMOTION AHF, these defaults apply to finite app-labelled `button.press`
actions; its bounded `hold_control` behavior has separate timing in the
[AHF guide](beds/timotion-ahf.md).

<!-- generated:pulse-defaults -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Bed type | Key | Pulse count | Pulse delay |
|---|---|---|---|
| 1500 Tilt Base (Rondure) | `rondure` | 25 | 50 ms |
| AdjustaMattress app | `adjustamattress` | 5 | 200 ms |
| Aging in Place / Dawn House app | `agingplace` | 5 | 200 ms |
| Alya Smart Furnishing app (choose BLE type and motor layout) | `alya` | 10 | 300 ms |
| Comfort Enhancements app | `comfort_enhancements` | 5 | 200 ms |
| Comfort Smart Bed app (Langjue) | `langjue` | 2 | 500 ms |
| Customatic Clarity app (Rize Clarity) | `customatic_clarity` | 8 | 120 ms |
| Customatic Jerome's C app | `customatic_jeromes` | 8 | 120 ms |
| Customatic Remedy app (Rize Remedy) | `customatic_remedy` | 8 | 120 ms |
| eShine app (E2000 to E5000) | `eshine_okin` | 10 | 300 ms |
| Flexispot app | `flexispot` | 5 | 200 ms |
| FSM Relax app | `fsm_relax` | 10 | 60 ms |
| GhostBed app | `ghostbed` | 5 | 200 ms |
| iFit app (manual selection) | `ifit` | 10 | 220 ms |
| Jensen Adjustable Sleep app, JMC400 bed | `jensen` | 4 | 300 ms |
| JobsAI智能助眠床 / Jobs AI app | `jobs` | 10 | 200 ms |
| King Koil (SUTA) app | `suta_king_koil` | 1 | 150 ms |
| King Koil Bed app | `kingkoil` | 10 | 300 ms |
| Leggett & Platt MlRM remote | `leggett_wilinke` | 10 | 110 ms |
| Limoss and Stawett remotes | `limoss` | 12 | 80 ms |
| Linak (Bed Control, Bed Connect and Performance Series apps): Carpe Diem Beds app | `linak` `carpe_diem` | 4 | 300 ms |
| Linak (Bed Control, Bed Connect and Performance Series apps): Performance Series app (older bases) | `linak` `performance_legacy` | 4 | 300 ms |
| Linx app | `linx` | 334 | 3 ms |
| Logicdata SimplicityFrame (SILVERmotion) | `logicdata` | 10 | 30 ms |
| Malouf Base / Lucid Base apps | `malouf_app` | 7 | 150 ms |
| Malouf remote, older receiver | `malouf_legacy_okin` | 7 | 150 ms |
| N32 Motion Bed app | `n32_motion_bed` | 5 | 200 ms |
| OCTO Smart Control | `octo` | 3 | 350 ms |
| OCTO Smart Control: Octo Remote Star2 | `octo` `star2` | 3 | 50 ms |
| OKIN Motion Bed app | `okin_motionbed` | 5 | 200 ms |
| Okin receiver (13 and 15 series) | `okin_ffe` | 7 | 150 ms |
| Okin receiver (older ORE remotes) | `okin_ore` | 1 | 300 ms |
| Okin receiver (Sealy Posturematic and DewertOkin Star beds) | `okin_cb35` | 3 | 300 ms |
| Resident Adjustable Base app | `resident` | 4 | 300 ms |
| Restonic app (Prime / Lombar / Infinity) | `restonic` | 10 | 200 ms |
| Richmat / RMControl app | `richmat` | 7 | 150 ms |
| Rize Home app | `rize_home` | 3 | 200 ms |
| Shuda app | `shuda` | 5 | 200 ms |
| SIMMONS app | `simmons` | 4 | 300 ms |
| Simmons Blue app | `simmons_blue` | 5 | 200 ms |
| Sleep Assist Pro | `sleep_assist_pro` | 10 | 200 ms |
| Sleeptime Australia app (SmartBed205, 402, 404, 405) | `sleeptime` | 4 | 300 ms |
| Somos / SomosBeds app | `somos` | 10 | 300 ms |
| SUTA Smart Home app | `suta` | 7 | 150 ms |
| Symphony Sleep app | `symphony_sleep` | 4 | 300 ms |
| Ultramatic Smart Bed app | `ultramatic_smart_bed` | 4 | 300 ms |
| V-MAT Basic app | `vmatbasic` | 34 | 30 ms |
| Vindö (Carpe Diem Beds) | `vindo` | 4 | 300 ms |
| アシステック / ASSISTEC / Yamada app | `yamada` | 4 | 300 ms |

Every other bed type defaults to 10 pulses 100 ms apart.
<!-- /generated -->

Svane Remote app profiles hold a control for its duration instead of a
configurable repeat count: the source refreshes every 100 ms, and the
feet/separate fallback adds 100 ms.

The **Sleepy's Elite app** profile uses its selector-specific app timing and
release behavior; the BOX15/BOX24 defaults describe the existing protocol
profiles. **Movement per tap** does not change its timing.

### When to Adjust

| Symptom | Solution |
|---------|----------|
| Motors stop moving too soon | Increase Movement per tap |
| A tap moves in several short bursts | Decrease Movement per tap |

---

## Bed Model or Remote

Some bed types have several models or remotes that need different commands.
Setup asks for one only when the bed type you chose has several, in a collapsed
**Advanced: bed model or remote** section of the final settings, or as a
question after a family's own question. An app chosen from the list sets its
own. **Automatic (recommended)** is right for most beds. The model or remote of
an existing bed changes only in
[Reconfigure](#changing-the-bed-type-app-or-layout-of-an-existing-bed).

The older Okin controllers (Okin Handle, 7-Byte, Nordic, CB35, FFE,
64-Bit and ORE) are not rows of the app list: a discovered bed shows its
detected controller, the brand list under **My app isn't listed, or I don't know** lists them,
and Reconfigure's bed-type list keeps them by name.

| Bed type | Choices covered by its guide |
|----------|-----------------------------|
| [Sleepy's Elite app](beds/sleepys.md#explicit-sleepys-elite-app-profile) | The control box the app lists, asked after the [Sleepy's question](beds/sleepys.md#home-assistant-setup) |
| [Linak](beds/linak.md#profiles-and-model-variants) | Bed Control, Bed Connect, AA Control My Bed and Performance Series |
| [Vindö](beds/vindo.md#detection--setup) | Carpe Diem Beds Vindö |
| [Kaidi](beds/kaidi.md#command-families) | Seat 1, Seat 2, Seat 3, Seat 1+2 |
| [Okin CST](beds/okin-nframe.md#okin-cst) | The Rize and Support products, asked by app name in the Okin question |
| [Sleepy's BOX25](beds/sleepys.md#box25-protocol-nordic-uart) | Automatic, StarCode or Legacy CB25, under **Advanced** after the Sleepy's question |
| [Rondure](beds/keeson.md#side-selection-split-king) | Both, Side A, Side B |
| [Okin DOT](beds/okin-nframe.md#okin-dot) / [Okin 64-bit](beds/okin-nframe.md#okin-64-bit) | The handset or connection type |

### Keeson Models

New setups answer the [Keeson question](beds/keeson.md#home-assistant-setup).
Its answers save one of these, and **No app: another Keeson remote**
lists the remotes.

| Choice | Use for |
|--------|---------|
| **Automatic (recommended)** | Most beds |
| **Member's Mark base (BaseI4 / BaseI5)** | Member's Mark, Purple, some Ergomotion |
| **Juna, Linx or Ergo Health base** | Juna, Linx, Ergo Health |
| **KSBT receiver (some Ergomotion Sync beds)** | KSBT03 and KSBT04 receivers |
| **KSBT03CR receiver**, **KSBT04C receiver** | Those receivers |
| **Ergomotion base (reports positions)** | Ergomotion-branded beds |
| **OKIN 13 or 15 series control box** | OKIN 13 and 15 series |
| **BetterLiving base (Sino)** | Dynasty, BetterLiving |
| **Purple Smart Base (Premium / Premium Plus)** | Purple Smart Base |
| An app, such as **Sleep Harmony app**, **INNOVA app** or **Restonic BT app, remote A** | Beds you control with that app. Apps that offer 2M, 3M and 4M screens take the screen from the motor count |

### Leggett & Platt Models

Setup asks the [L&P question](beds/leggett-platt.md#home-assistant-setup),
which picks the model from the app you use and saves it as that model's bed
type.

| Model | Chosen by the L&P answer |
|-------|--------------------------|
| [Gen2](beds/leggett-platt.md#gen2-variant), needs Bluetooth pairing | LP Control app with an LP Comfort Connect base |
| [Leggett Okin](beds/okin-nframe.md#leggett-okin-family), needs Bluetooth pairing | Prodigy CE, Prodigy 2, Prodigy 2L or U Series app, or LP Control with an LP BED receiver |
| [MlRM](beds/leggett-platt.md#mlrm-variant) | L&P Adjustable Base app with an MlRM base |

A bed that 4.x set up on **Automatic** keeps that setup, shown as **Gen2 or
MlRM, found automatically (Leggett & Platt)**: each time it connects it uses MlRM
when the bed has the WiLinke service and Gen2 otherwise. To fix its model, open
**Reconfigure** and answer the L&P question.

### Richmat Receivers

Setup asks the receiver under **Advanced** after the
[Richmat question](beds/richmat.md#home-assistant-setup)'s RMControl,
SleepFunction, SVEN & SON or Richmat remote answer. Leave it on **Automatic
(recommended)** unless the bed does not respond; the other choices are
**Nordic receiver**, **WiLinke receiver**, **Other receiver, type A** and
**Other receiver, type B**.

### Octo Models

**Automatic (recommended)**, **Standard Octo (most common)** or **Octo Remote
Star2** for Star2 receivers.

### Sleep Number Side

For newer Sleep Number Fuzion bases (`Smart bed *`), setup asks the side once
the [Sleep Number question](beds/sleep_number.md#detection) has settled on a
Fuzion base: **Automatic (recommended)**, which controls the left side,
**Left side** or **Right side**. Older BAM/MCR beds, such as some i8 and 360
FlexFit 2 models, control both firmness sides from one entry and do not ask.

A Fuzion base with a single chamber uses the right-side channel whatever side
you choose. Optional motors, lighting and climate controls follow what the bed
reports. Other settings, including temperature programs, use the
[Sleep Number command action](beds/sleep-number-services.md).

### Okimat Handsets

Okimat beds use different handset codes that decide the available controls.
Setup reaches them through the Okin row's question: **No app: Okimat or OKIN
handset code (requires pairing)**, then the code printed on the handset. The table below gives
common examples; the setup selector contains the complete handset list. For
beds controlled by the FurniMove app, including RF ECO BT receivers, answer
**FurniMove / OKIN Smart Remote app** for the separate
[FurniMove profile](beds/furnimove.md) with its exact handset selector. Other OKIN app profiles retain their own evidence and options. For example, RF-TOPLINE `82620` exposes Back, Legs, Flat, and the
receiver's under-bed light toggle.

| Handset code | Remote model | Motors |
|---------|--------------|--------|
| **Automatic (recommended)** | Tries 82417 first | Varies |
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
These choices determine which controls are available. The table below lists
what each app or brand asks, alphabetically, with links to the setup steps in
its bed guide.

1. Let automatic discovery identify the controller where possible.
2. If adding manually, find your brand or app in [Supported Beds](../README.md#supported-beds).
   You can type an app's name to search the bed-type list, for example
   **INNOVA app**, **Power Bob** or **HomeKobo**. Not every app is named in
   the list. If yours is not found, its guide's **Apps** table names the
   profile it uses. Choosing an app sets its bed model or remote for you.
3. Match any requested model or remote to your physical bed. Shared Bluetooth
   names and services do not always identify the right layout.

Existing entries keep their selection until you change it. A bed on a generic
route that has since gained app profiles can be asked once, through a repair,
which app it uses; see [the upgrade prompt](TROUBLESHOOTING.md#new-app-profiles-are-available-repair).
For a combined bed with two addresses, settings belong to each physical bed.
Each receiver's own app settings, such as its motor count, massage or light
settings, are under **Configure > Change left side settings** or **Change
right side settings**. To change a receiver's bed type or app, separate the
beds, Reconfigure that bed, then combine them again.

| Bed or brand | Model and remote settings |
|--------------|---------------------------|
| Adjustable bed (Lumbar) | [Automatic, or the layout your bed uses](beds/okin-nframe.md#adjustable-bed-lumbar). |
| AdjustaMattress | [Choose the app, BLE model and product layout](beds/keeson.md#adjustamattress). Four models and seven layouts; the layout sets the controls. Each bed of a combined pair keeps its own. |
| BedSense | [Layout, or the Bluetooth-name layout rule](beds/ff_frame.md#bedsense). |
| BedTech | [The exact model, or **Older BedTech controls, without a model**](beds/richmat.md#bedtech). Existing entries keep the legacy controls until you choose a model. |
| BF / Cherish | [The exact app](beds/keeson.md#bf-and-cherish); it sets the layout. |
| Casper Base | [PRO/MAX product](beds/casper-base.md#home-assistant-setup); sleep sensors and the RCRM handset are separate entries. |
| Relax Motion | Numeric advertisement model, preserved across reconnects, and the exact app page / label language. See [setup](beds/relax-motion.md#detection--setup). |
| Scott Living | [A (8 buttons), B (13 buttons), or C (17 buttons)](beds/keeson.md#scott-living). Existing entries default to A. The layout sets the motors and utility controls. |
| SmartBed app | The receiver, the motor count and the bed's Bluetooth name. A CB24AB receiver also asks which side of a split bed the entry controls. See [choosing a profile](beds/smartbed.md#choosing-a-profile). |
| King Koil (SUTA) app | [One M510 control layout](beds/suta.md#king-koil-suta), explicitly selected by app; Back/Foot control, no position feedback. Combine two physical receivers for side controls. |
| trueMotion app | [Complete case-sensitive Bluetooth name](beds/suta.md#truemotion). Each receiver keeps its own name in a pair, and the left receiver selects the split editor. |
| CheersSleep | See the [setup steps](beds/cheerssleep.md#cheerssleep-profile). |
| Comfort Enhancement 3 / Comfort Plus3 | See the [setup steps](beds/okin-nframe.md#comfort-enhancement-3). |
| Comfort Enhancements | [Choose MC2/MC3/MC4/MC5](beds/keeson.md#comfort-enhancements). The layout sets the controls, massage, light and memories. Each bed of a combined pair keeps its own. |
| Customatic / Jordan's | One question per brand: [Clarity / Jerome's / Remedy](beds/okin-nframe.md#customatic-family), [Independence](beds/okin-nframe.md#independence-customatic-demo) or [Z-Series](beds/okin-nframe.md#customatic-z-series) with its model; [Serenity](beds/okin-nframe.md#jordans-serenity), [Tranquil](beds/okin-nframe.md#jordans-tranquil) or [Restful](beds/okin-nframe.md#jordans-restful). Change an existing bed's app with **Reconfigure**. |
| Ergomotion 4.0 | [Exact product, or another catalog product by name and feature keys](beds/keeson.md#ergomotion-40-home-assistant-setup). |
| Eshine | [Explicit app profile](beds/richmat.md#eshine) with a fixed head, feet, lumbar, pillow, massage and light layout. |
| eShine E2000 / E3000 / E3100 / E5000 | [The product the app shows](beds/okin-nframe.md#eshine); E3000 and E3100 are one choice. Each bed of a combined pair keeps its own; Left and Right controls on one address are not available. |
| FSM Relax | Answer the [Limoss question](beds/limoss.md#home-assistant-setup) with the FSM Relax app, then its [bed/chair layout, light/massage, reversal settings and memory names](beds/limoss.md#fsm-relax). |
| FurniMove / OKIN Smart Remote | Answer the [Okin question](beds/okin-nframe.md#home-assistant-setup) with **FurniMove / OKIN Smart Remote app**, then the [exact handset ID](beds/furnimove.md); also includes a guided repair for older RF ECO BT entries. |
| Galaxy Bed Control | The product code and remote; V9RM and RNRN also ask base, standard or split head. Each bed of a combined pair keeps its own. See [Galaxy](beds/richmat.md#galaxy-bed-control). |
| GM Control | [The product, configuration and app side](beds/gmmotor.md#detection--setup). Sleep modules (MM or SXB) are added as their own beds. |
| Good Vibe Sleep | [The exact product, configuration or remote alias](beds/richmat.md#good-vibe-sleep); sleep sensors (RM- or HJ-) are added as their own beds. Split beds use Left and Right controls on one address; light duration and snore settings are entities on the device. |
| Instant Comfort | [Choose the air-unit or base route and pressure layout or base model](beds/personal-comfort.md#instant-comfort). |
| HJBed | [The exact app product](beds/richmat.md#hjbed). |
| Jensen / Svane | Answer the [Jensen / Svane question](beds/jensen.md#home-assistant-setup) with your app and bed: the Jensen Adjustable Sleep app with a [JMC400](beds/jensen.md) bed (then its PIN) or a [LinOn](beds/jensen.md#linon) bed, or the [Svane Remote](beds/svane.md) app with a Svane Bed or a JMC400 bed. Change an existing bed's app or bed with **Reconfigure**. |
| Jiecang | [App profiles](beds/jiecang.md#choosing-a-profile): choose the app ([ERGOBALANCE](beds/jiecang.md#ergobalance-dreamask), [Dream Motion](beds/jiecang.md#dream-motion-dreamotion), [Dream Motion HD](beds/jiecang.md#dream-motion-hd) or [Comfort Motion](beds/jiecang.md#comfort-motion-app)), then layout and local light/massage presence, with the transport under **Advanced**. Comfort Motion supports three layouts. The [profile tables](beds/jiecang.md#choosing-a-profile) list each app's layouts and connections. |
| Kaidi | [ISleep](beds/kaidi.md#isleep): product, room number and actuator number. [Floyd Home](beds/kaidi.md#floyd-home): product 139. |
| Keeson | Answer the [Keeson question](beds/keeson.md#home-assistant-setup) with your app: [Adjustable Lite](beds/keeson.md#adjustable-lite-profile), [Simon Li / Heal Every Night / OKIN-Seating](beds/keeson.md#simon-li-heal-every-night-and-okin-seating-profiles), [INNOVA](beds/keeson.md#innova-profile), [MaxCoil Una / Dynasty Bases / Bedsense Bases / Avanti Bases / AMERICANSTAR](beds/keeson.md#ore-comfort-bed-profiles), or [Restonic BT](beds/keeson.md#restonic-bt-profiles). It then asks the app's 2M, 3M or 4M screen, or the Restonic remote style, where the app has one. |
| Keeson app family | [Tempur Curve, Q-Plus Adjustable Remote, Serta MP Remote, Omazz Adjusto III, Ergomotion, ROW Control, Ergo Slim and TEMPUR AU](beds/keeson.md#keeson-layout-app-family): the exact app and the layout it shows; Q-Plus also has a Both/Side A/Side B selector. |
| KomfyD / ComfyDS | See the [setup steps](beds/kaidi.md#komfyd-and-comfyds). |
| L2 Motion | See the [setup steps](beds/motomotion.md#l2-motion). |
| ErgoBed Control | Choose the app and enter the exact Bluetooth name. The name selects the motor layout and optional controls. See [ErgoBed Control setup](beds/motomotion.md#ergobed-control). |
| MoodBase | Choose the MoodBase app and enter its exact Bluetooth name. That name controls which motors, presets and optional features appear. Each Bluetooth receiver keeps its own name when combined. See [MoodBase setup](beds/motomotion.md#moodbase). |
| Leggett & Platt | Answer the [L&P question](beds/leggett-platt.md#home-assistant-setup) with your app: [Prodigy CE, Prodigy 2, Prodigy 2L or U Series](beds/okin-nframe.md#leggett-okin-family) sets the layout; LP Control and the L&P Adjustable Base app also name the receiver or remote. [L&P legacy](beds/richmat.md#lp-legacy-app): model, connection mode and characteristic IDs. |
| Limoss | [One question](beds/limoss.md#home-assistant-setup) for the Limoss Remote or FSM Relax app, or the older controls. [Limoss Remote](beds/limoss.md#limoss-remote): bed/chair layout, light/massage and reversal settings. Change an existing bed's app with **Reconfigure**. |
| Leva Bed Remote (Leva Smart App) | Choose the model and Bluetooth receiver for each bed. See the [setup steps](beds/okin-nframe.md#leva-bed-remote). |
| Linx | See the [setup steps](beds/linx.md#setup). |
| LOGICDATA | One question for the app ([SILVERmotion / SimplicityFrame](beds/logicdata.md), [MOTIONrelax phone or tablet](beds/jiecang.md#motionrelax-phone-and-tablet), or [Sleep Smart](beds/jiecang.md#sleep-smart-air-mattress-bed) bed base or [separate air pump](beds/logicdata-sleep-smart.md)), then the app's command family, the layouts it offers, the light and the connection. Configure keeps the light; another app or layout goes through Reconfigure. |
| Smart Base | Choose Smart Base, then 200IV2 / A8RM (FEE9). Refresh bed settings to discover RGB, timeout and alarm cancellation on the current connection. See the [Smart Base guide](beds/richmat.md#smart-base). |
| Sinca Comfort Bed | Choose the receiver and motor layout from the [Sinca Comfort Bed setup steps](beds/mline.md#sinca-comfort-bed). Shared Bluetooth names and services leave the app choice to you. |
| M Line | See the [setup steps](beds/mline.md#m-line-family). |
| Malouf / Lucid | Answer the [Malouf question](beds/malouf.md#choosing-a-profile) with your app or receiver: the [Malouf Base and Lucid Base apps](beds/malouf.md#malouf-base--lucid-base-family) ask the exact model, primary/secondary role and transport; the Nordic UART and FFE5 receivers ask the [layout and memory positions](#malouflucid-layout-and-memory). Change an existing bed's app with **Reconfigure**. |
| MLILY Control | The product the app shows, or the remote. Sleep sensors (RM- or HJ-) are added as their own beds. See the [product table](beds/richmat.md#mlily-control). |
| MLILY Remote | See the [setup steps](beds/richmat.md#mlily-remote). |
| Motion Bed | [Layout and saved app settings](beds/ff_frame.md#motion-bed), and the bed's exact Bluetooth name. |
| MotoMotion | [The exact Bluetooth name](beds/motomotion.md#motomotion), which selects the panel and its feature flags; preserve its case. |
| Nerum | See the [setup steps](beds/nerum.md#detection--setup). |
| Nisco / MLILY Supreme | Select the app, then its model, or **Automatic (recommended)** from the Bluetooth name. MLILY Supreme also offers six short model names and a normal-mattress option. Add the separate HJ_Bed sleep receiver for sleep sensing. Which side the app sends to is set with the `richmat_mh_control` action. See [Nisco](beds/richmat.md#nisco) and [MLILY Supreme](beds/richmat.md#mlily-supreme). |
| OkimattMotion | [Choose the app manually and select its layout](beds/keeson.md#okimattmotion). The extended layout adds combined movement and Book. |
| Okimiki | See the [setup steps](beds/richmat.md#okimiki). |
| OKIN SleepEase / DoubleSleep | [SleepEase setup](beds/okin-nframe.md#okin-sleepease): choose the model the app shows; the bed's advertisement decides the control box type. Each bed of a combined pair keeps its own settings. |
| OKIN Smart Sleep | See the [setup steps](beds/smart-sleep.md#setup). |
| ORE Ultramatic | See the [setup steps](beds/keeson.md#ore-ultramatic). |
| OrmatekTechnoSmart | [Techno Smart setup](beds/keeson.md#ormatek-technosmart): choose New or Lite, and the Okin or SmartBed remote. Each bed of a combined pair keeps its own. Use **Reconfigure** to change the app or model. |
| Power Bob Base | Choose Elite, Elite SH, Ultra or Ultra SH, then Standard, Split head or Split installation. Each bed of a combined pair keeps its own product and layout. SH products can control one side, except over the Nordic connection. See [Power Bob Base](beds/richmat.md#power-bob-base). |
| Remacro | [One question for Slumberland, The Brick or Jerome's](beds/remacro.md#home-assistant-setup), offering the apps that list the model the bed advertises, or all three when none does. Reconfigure changes the app, and checks that it lists the bed's model. |
| Resident Adjustable Base | See the [setup steps](beds/okin-nframe.md#resident-adjustable-base). |
| Reverie | [Setup confirms the receiver](beds/reverie.md#setup-and-model-selection) from its advertised service (Protocol 110 or 108), then asks the model the app shows. Reconfigure lists both receivers. |
| Richmat | [Purely Sleep](beds/richmat.md#purely-sleep) asks for NXPS200/JLRN or PS200/VJRM in normal mode. [One question](beds/richmat.md#home-assistant-setup) for the app: [RMControl](beds/richmat.md#rmcontrol) then asks its product code and side; [Revive Control / Best Mattress / Blvd Home / HARMONY / Idealbed](beds/richmat.md#richmat-mh-apps) the app's model, or **Automatic (recommended)** from the Bluetooth name; [Avocado Eco Base / CoasterSleep / Forty Winks / Milemont / Superior / Dynasty DM9000](beds/richmat.md#classic-richmat-apps), [Luuna Rise / Power Cool Sleep System](beds/richmat.md#luuna-rise--power-cool), [Lady Americana / ACAA / STA Homecare / Zero Gravity](beds/richmat.md#lady-americana--acaa--sta-homecare--zero-gravity-family), [Jerome's power base](beds/richmat.md#jeromes-power-base), [Maxprime](beds/richmat.md#maxprime) and [Dreamlab Control](beds/richmat.md#dreamlab-control) ask for the app's layout code. [Jerome's Adjustable Base](beds/richmat.md#jeromes-adjustable-base) asks for ELEVATE 2.0, ELEVATE 2.0 SH, WAVE or WAVE SH. [Base Remote](beds/richmat.md#base-remote) asks its layout code and, for a layout with Left and Right tabs, whether the bed is one base. Without one of these apps, the [Richmat remotes](beds/richmat.md#richmat-remotes) ask the remote code. Reconfigure changes the app and lists each one by name, so an entry can switch apps or opt in to RMControl and out of it; Configure changes the app's own settings. |
| Dorsal app / Roomi | Choose CPRN, CORN, a saved Dorsal project, or Roomi controls. Enter the exact case-sensitive code for a saved project. Roomi needs a receiver with QRRM in its Bluetooth name and accepts an optional saved code. See the [Dorsal guide](beds/richmat.md#dorsal--roomi). |
| ROOMI bed (S655 Plus) | Choose the S655 Plus profile and a receiver with QRRM in its Bluetooth name. No project code is needed. See the [ROOMI bed guide](beds/richmat.md#roomi-bed-s655-plus). |
| ENSO Sleep Control (Enso 2) | Choose the layout shown in the app. The Bluetooth name suggests a layout when it has a recognized prefix. For a generic name, Cool Touch or 209A05, choose the app’s manual layout code. Enable **Property-based Bluetooth receiver** only for receivers that use the third-service fallback. See the [Enso 2 profile](beds/richmat.md#enso-sleep-control). |
| Purely Sleep | Choose NXPS200 (JLRN) or PS200 (VJRM), normal mode, explicitly. See [controls and limits](beds/richmat.md#purely-sleep). |
| Richmat app | See the [setup steps](beds/richmat.md#richmat-420). |
| Rize Beds | See the [setup steps](beds/kaidi.md#rize-beds). |
| Rize Remedy II | See the [setup steps](beds/okin-nframe.md#rize-remedy-ii). |
| Shuda | Choose the [Shuda app](beds/okin-nframe.md#shuda). The profile sets the fixed head and foot layout. |
| SIMMONS | [Regular/inclined bed and packet format](beds/okin-nframe.md#simmons). |
| Sleep Number | [Setup confirms the transport](beds/sleep_number.md#detection) from its advertised service (Fuzion or BAM/MCR), then a Fuzion entry asks its side. Reconfigure lists both transports. |
| SleepEvolution / W.Silver Products 3.x | See the [setup steps](beds/richmat.md#sleepevolution--wsilver-products-3x). |
| Sleepy's Elite | [One question](beds/sleepys.md#home-assistant-setup) for the MFRM Sleepy's Elite app or the BOX15, BOX24 or BOX25 receiver. The [app profile](beds/sleepys.md#explicit-sleepys-elite-app-profile) asks the control box the app lists, for each physical receiver. Change an existing bed's app, control box or BOX25 dialect with **Reconfigure**. |
| Solace / Woosa | Answer the [Solace question](beds/ff_frame.md#home-assistant-setup) with your app: HomeKobo, Sealy MotionFlex or Sweet Night, which follow the bed's Bluetooth name, or [Woosa Sleep](beds/ff_frame.md#woosa-sleep). |
| King Koil Bed | Choose the [remote layout](beds/keeson.md#king-koil-bed) by its visible controls. |
| Somos / SomosBeds | See the [setup steps](beds/keeson.md#somos--somosbeds). |
| SonicSleep | See the [setup steps](beds/richmat.md#sonicsleep). |
| Sophie | See the [setup steps](beds/ff_frame.md#sophie). |
| StarCode apps | One question for the app, then its own settings. Reconfigure lists each StarCode app, so an entry can move to another without being removed. [M5X4](beds/okin-nframe.md#adjustablem5x4): control box and connection type, under **Advanced**. [M5X5](beds/starcode-m5x5.md): layout and up to three configured lift entries. [M1X12](beds/starcode-m1x12.md): layout and up to two ELEVATE accessories. |
| Sealy Posturematic | [Element, Ascent or Apex](beds/okin-5a.md#sealy-posturematic-app), stored per physical side. |
| Superior sleep | Choose **SS350** or **SS650**, then the **Exact Bluetooth name**. A case-sensitive `BLE` prefix selects the 1000 route; other named beds use Nordic UART. Each side of a two-receiver pair owns its own product/name. See [Superior sleep](beds/okin-nframe.md#superior-sleep-ss350--ss650). |
| Symphony Sleep Sense | [Symphony setup](beds/okin-soundwave.md#symphony-sleep-sense): choose the product the app shows. Split-Head and KGD-SHQ/SHK beds offer Left and Right controls; each bed of a combined pair keeps its own app choices. |
| Tempur Sleeptracker-AI | [Processor setup](beds/sleeptracker.md): choose this app for ProSmart / ProSmart Air and ActiveBreeze, then the layout the app shows. The processor's own fields are under **Advanced**. Motors and massage follow the layout; the bed does not report its position. |
| Vibradorm | [Caresse / Werkmeister](beds/vibradorm.md#caresse-and-werkmeister), [VMAT](beds/vibradorm.md#vmat), [V-MAT Basic](beds/vibradorm.md#v-mat-basic): app, exact remote or product, and offered light settings. |
| アシステック / Yamada | See the [setup steps](beds/keeson.md#アシステック--yamada). |

### Super Colchones products

Choose **Super Colchones app (AFEG302, AFEG350) · Richmat**, then **AFEG302** or **AFEG350**.
Choose the product printed on your bed; Bluetooth discovery cannot identify it.
The product determines the available movement and massage controls.
See [Super Colchones](beds/richmat.md#super-colchones) for controls and save behavior.

### Instant Comfort

Select **Instant Comfort app** and the controller's route. Air units and bases
are separate devices. Base setup asks for its model; ANM V5 asks for its two-
or four-channel pressure layout. Setup saves the route and layout with that
physical device. A pressure reply must match the selected layout before a
target can be sent. Use Configure to change it.

Combine only two Instant Comfort base entries, each with its own model and
route. The air unit stays separate. See the [profile guide](beds/personal-comfort.md#instant-comfort).

### Octo PIN

**Setting:** 4-digit PIN code

Standard OCTO reports whether PIN control is enabled, whether a PIN is set, and
whether the receiver is unlocked. Configure a four-digit PIN only when the
receiver reports one is required. Star2 uses a separate protocol and has no
Standard OCTO PIN exchange.

**How to configure:**
1. Go to **Settings > Devices & services**
2. Find your Adjustable Bed and select **Configure** (gear icon)
3. Choose **Change settings** from the menu
4. Enter your 4-digit PIN in the "Octo PIN" field

**Finding your PIN:**
- Use the PIN set in the OCTO Smart Control app; it is not the OS Bluetooth pairing code.
- If your bed works without a PIN, leave this field empty

Standard OCTO setup verifies PIN acceptance without moving the bed. A PIN the
bed requires or rejects must be entered or corrected first. An inconclusive
check can be retried, or setup can finish without it; it does not mean the PIN
is wrong. After a PIN lock challenge, the integration retries the
configured PIN once after one second. It does not use a periodic PIN timer. See
[OCTO Smart Control](beds/octo.md#pin-control).

### Jensen PIN

**Setting:** 4-digit PIN code (default: 3060)

Jensen JMC400 beds require PIN authentication for BLE control.

**How to configure:**
1. Go to **Settings > Devices & services**
2. Find your Adjustable Bed and select **Configure** (gear icon)
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
| **Automatic (recommended)** | All features enabled |
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
encodes the same code; select **GGRM / HJH89 (Head, Feet, Pillow, Lumbar, M1,
ZG, Anti-snore, Lights, Massage)** for it.
For an L&P bed that advertises as `QRRM` and has Flat, Zero G, Custom 1, and
Custom 2 buttons, select **L&P QRRM (Head, Feet, Flat, Zero G, Custom 1/2)**. Current L&P and Richmat apps also require
a physical remote or product selection for QRRM devices. The BLE name and GATT
services do not identify that profile, so the integration cannot select it
safely on its own.

---

## Troubleshooting Tips

### Physical Remote Stops Working

This is expected when Home Assistant is connected. Most beds only support one BLE connection.

**Solutions:**
1. Set **Bluetooth connection** to "Release right after each command" where it is offered, or press Disconnect
2. With "Stay connected for a while", lower **Seconds to stay connected** to free the link sooner
3. Turn off **Read bed position** if position monitoring causes conflicts

### Commands Are Slow or Unresponsive

1. Move your Bluetooth adapter or ESPHome proxy closer to the bed
2. Check **Bed model or remote** in **Reconfigure**
3. Reduce interference from other 2.4GHz devices

### Motors Move Too Briefly

Increase **Movement per tap**. Start with +10 and test.

### Wrong Features Showing

- **Richmat beds:** Select your remote code in **Configure**
- **Other beds:** Verify motor count matches your bed's actual motors
- **Massage not showing:** Turn on **Massage controls** in **Configure**, where it is offered

---

## Single-Address Left / Right Controls

Some split beds reach both sides through one Bluetooth address, for example
Q-Plus, Rondure, SmartBed CB24AB receivers, Sleep Number Fuzion and some Keeson,
Ergomotion 4.0, Kaidi, CheersSleep, Symphony and Ultramatic beds. If the bed's
**Configure** menu offers **Add Left, Right and Both controls**, choose it to
get the same Left, Right and Both controls as two combined beds.

This keeps the existing entry, Bluetooth address, device and entity history.
**Remove Left, Right and Both controls** in the same menu turns it back, and
keeps the Bluetooth adapter and **Bluetooth connection** you chose meanwhile.
Existing entries do not change by themselves.

- Before you add Left and Right controls, the entry controls the side it was
  set up for, and sends the same commands as before.
- Some beds cannot tell which side reports a position, so their position
  feedback is off while Left and Right controls are on. The bed guide says so.
- Sleep Number BAM/MCR beds already have controls for each side and do not
  offer this.
- Beds whose commands have no side, such as the SmartBed receivers other than
  CB24AB, do not offer it.

## Split-King / Controller sync

The **Controller sync** switch sends a sync command
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

To enable it, open **Settings > Devices & services > Adjustable Bed**, select the
bed, and enable **Controller sync** under **Entities**.

### Two Independent Frames

Add each frame as its own Adjustable Bed entry and confirm that each controls
only its intended side. For compatible entries, start **Add Integration >
Adjustable Bed**, then choose **Combine two beds into one (Dual Bed)** and select
Left and Right. The resulting parent device provides
combined controls; the child devices provide side-specific controls. The card
also offers Left/Both/Right selection. This does not require Controller sync.

Each receiver keeps its own **Bluetooth connection** setting. Selecting one
side does not disconnect the other, and Both can operate the two receivers
concurrently. This also applies to OCTO/Star2 pairs. If the active adapter
reports that the second link exhausted its connection slots, the pair falls
back to switching between the receivers one at a time for that runtime.

The wizard checks protocol and motor-layout compatibility. Some controllers need
a successful connection first to discover their capabilities. One-motor OCTO
TV/bed lifts remain standalone. Combined controls use capabilities shared by both
sides; side-specific controls retain each side's own features.

For two receivers, open **Configure > Change left side settings** or
**Change right side settings** to adjust its adapter, Bluetooth connection, Movement per tap and its own app's
settings.
These changes apply only to the selected receiver, without separating the bed. **Change settings**
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
combining entries. To undo it, choose **Separate into two beds** in the pair's options;
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

The card's percentage and lumbar graphics, graphic labels and the full card in
a dialog are described in the
[Dashboard Card guide](DASHBOARD_CARD.md#graphics-and-dialog).

---

## Next Steps

- **Having connection issues?** See [Troubleshooting](TROUBLESHOOTING.md)
- **Want to know more about your bed?** Find its guide in the [documentation index](README.md#bed-guides)
- **Setting up Bluetooth?** See [Connection Guide](CONNECTION_GUIDE.md)

### SILVERmotion Android

Choose the LOGICDATA row, then **SILVERmotion app: SimplicityFrame bed with zero
gravity and anti-snore presets**. Reconfigure offers the same choice. The other
SILVERmotion answer, marked pairing required, is a separate choice.

| Field | Values | Default |
|-------|--------|---------|
| Product type | Queen, King, Twin XL | Queen |
| Has massage | Enabled or disabled | Enabled |

All sizes expose back and legs controls. Each physical entry retains its own size
and massage setting when combined with another bed. No single-address side
selection is inferred. The massage timer is a Home Assistant countdown, 1–40
minutes, initially 10; it sends massage off on expiry while connected. It does
not program a timer in the bed. See [SILVERmotion Android](beds/silvermotion.md).

### Home Zone Adjustable

Home Zone Adjustable uses its own app choice and an explicit four-character bed
layout. Layout picker destinations are listed in the same field. Its exact
Bluetooth name controls the refresh interval; no physical layout is inferred
from the shared Bluetooth service. See the [Home Zone guide](beds/richmat.md#home-zone-adjustable).

JobsAI智能助眠床 / Jobs AI uses an explicit app choice and mode 1 or mode 2.
See the [JobsAI guide](beds/okin-nframe.md#jobsai).

### ErgoBQ BED

Select the BED product ID explicitly. Optionally enter its six-byte serial
as hex; serial byte 4 selects the four-motor layout only when it equals 4.
Blank uses the app's two-motor default. Enter an existing channel stamp if
required; no account lookup is performed. The shared Nordic UART service alone
does not choose an ErgoBQ product. See [ErgoBQ BED](beds/ergobq.md).

### Restonic app

Choose the Prime, Lombar or Infinity layout and its BLE branch independently.
Both choices belong to the physical bed and are configured per side of a
two-address pair. The [Restonic guide](beds/restonic.md) lists the exact
name-to-branch rules and available actions. No network setup is required.

### Ronco Motion layout

The searchable **Ronco Motion app** choice asks for ECONOMY (Fk9rm) or PREMIUM
(Fk8rm). Select the layout used in Ronco Motion 1.2; Bluetooth names cannot
identify it. PREMIUM adds Pillow and a light toggle. Layout settings belong to
one physical side of a two-address pair. See [Ronco Motion](beds/richmat.md#ronco-motion).

### PowersBedding

Choose **PowersBedding app** for its fixed two-motor screen. The Bluetooth name
and manufacturer query select the receiver route automatically. Layout, massage
and 100 ms movement cadence belong to the profile. Each receiver in a two-address
pair keeps its own Bluetooth name and massage levels. See the
[PowersBedding guide](beds/keeson.md#powersbedding).

### My Side

Choose **My Side app** and the Deep Relax Smart product from your app: standard,
with Sleep, with Coaxing, or with Coaxing and Sleep. Shared BLE services and
Bluetooth names do not determine this choice. Each receiver in a two-address
pair keeps its own product choice. The separate sleep-sensor connection is
currently unavailable; Sleep products expose the bed-side sensor name only.
