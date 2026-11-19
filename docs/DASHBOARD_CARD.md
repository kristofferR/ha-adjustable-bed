# Dashboard Card

The integration ships a native Lovelace card, **Adjustable Bed Card**. It is a
complete control panel for your bed, styled by your Home Assistant theme:
position controls, presets, memory, lighting, massage, climate and connection.
It registers and loads automatically; you do not need to add a
dashboard resource manually. If Home Assistant was open in your browser
during an integration update, reload that page once after restarting Home
Assistant so the browser picks up the updated card module.

If the card is missing or shows a configuration error, see the
[dashboard card troubleshooting guide](TROUBLESHOOTING.md#dashboard-card-missing-or-configuration-error).

To add it: edit a dashboard → **Add Card** → search for **Adjustable Bed**, then
pick your bed device. Selecting one of the
bed's entities first also suggests the Adjustable Bed Card. Or in YAML:

```yaml
type: custom:adjustable-bed-card
device_id: <your bed device>
```

The card adapts to your bed. It shows only the sections your bed has, so
massage and climate appear only on beds that support them, and the same card
works for every supported bed.

## Movement and paired beds

Hold an Up/Down control to move; release it to send STOP. On beds whose app is
proven to stream a held key until release, the card holds the motor in one
continuous [renewable hold](SERVICES.md#renewable-holds), and the
integration stops it when its short lease runs out if the browser goes away.
Other beds repeat finite movements, so a hold can have short pauses between them.
Position sliders appear only when the selected controller exposes them.

### Tap to move

Turn on **Tap to start and stop movement** in the card editor (`tap_to_move:
true`) to move without holding. Tap an arrow to start the motor. The arrow stays
highlighted and the row reads **Moving up · tap to stop**. The next tap on any
arrow or Stop stops it, and never starts another motor. Movement also stops:

- after at most 30 seconds, or 10 seconds on beds that keep moving after one
  start command (`latched` holds);
- when you press a preset, memory or other button on the card, which takes over
  from the movement;
- when you hide the page, switch apps, navigate away, remove the card or switch
  the side tab of a paired bed;
- when the browser, phone or network disappears. A bed with a renewable hold
  stops within one 750 ms lease; any other bed stops after its current finite
  movement.

A control whose only hold is a fixed 60-second window that the card cannot
renew stays press-and-hold, because it would keep moving if the page
disappeared. Presets and memory are unchanged.

For a combined bed, the card shows tabs: **Both** first, then one per side.
A side tab uses the side's own name, without the bed name it repeats, so
**Bedroom Left** under **Bedroom** reads **Left**. Arrow keys, Home and End move
between the tabs. Selecting
either the parent device or a side's child device opens the paired card. Both-side
controls expose shared capabilities; select a side for its additional features.
The **Match both to** controls copy the selected side's reported positions to the
other side when both provide the required feedback. This is a one-time move.

Beds without position feedback can show [estimated positions and saved
positions](ESTIMATED_POSITIONS.md#in-the-card) once calibrated.

See [paired-bed configuration](CONFIGURATION.md#two-independent-frames)
and [action targeting](SERVICES.md#targeting-a-bed-or-side) for setup and
automation behavior.

## Compact room cards

In the visual editor, choose **Glance only**, **Quick actions**, or
**Compact controls**. These are starting points for the same card, and every
option remains editable. Existing cards keep their full layout.

- **Glance:** both bed positions, with optional title and side names. Turn off the
  title and readouts for a graphic-only tile.
- **Quick actions:** the dual graphic, side selector, selected presets or memory
  recalls, and Stop. Choose and reorder favourites in the editor.
- **Controls:** adds the supported hold-to-move motor rows.

Both silhouettes remain visible when switching sides. **Side to control** picks
the side the card starts on. Hide the side selector to keep that side; the card
then shows which side its controls reach. Native pairs store a child device ID, so renaming a side cannot reroute
commands. Stop remains available with movement controls and retains targets of
movement started by this card across side changes. Compact mode never saves
memory positions. Preset buttons are disabled when the side exposes neither a
Stop action nor motor covers that can be stopped. The side readouts name each
side the same way as the tabs.

Title, graphic, readouts, motor rows, lighting, and connection status are optional.
Configure a local **Full view path** to open another dashboard view from the title
or graphic. Position animation follows real degree readings, honours reduced
motion, and does not loop while idle. Unknown positions show an explicit fallback;
percentage feedback is shown as text rather than converted into an invented angle.

```yaml
type: custom:adjustable-bed-card
device_id: <your bed device>
layout: compact
show_header: true
compact_labels: angles        # angles, names, or none
show_side_selector: true
default_target: both          # both, child device ID, or left/right for a one-address pair
compact_actions:             # ordered preset or memory entity IDs; [] for no quick actions
  - button.bedroom_flat
  - button.bedroom_memory_1
show_motors: false
show_lighting: false
show_connection: false        # compact side statuses, not connection buttons
animate: true
navigation_path: /dashboard-bedroom/bed  # optional local HA path
open_dialog: false            # optional, open the full card in a dialog instead
dialog_config:                # optional, full-card options for the dialog only
  show_massage: false
```

Omit `compact_actions` for Flat plus the first available memory recall (or another
preset when no memory recall exists). On a paired bed, an action picked on one side
uses the matching action on the other sides, and actions the selected side lacks are
left out; entity names and icons are preserved. Cards saved by older versions list
the integration's internal keys instead of entity IDs; these keep working, and the
editor saves entity IDs the next time you change the quick actions. Compact controls are off by default
except for these quick actions. The other `show_*` sections and `section_order`
apply to the full layout. Memory saving and position synchronization stay there.

The optional percentage and lumbar graphics and the full card in a dialog are
described in [Graphics and dialog](#graphics-and-dialog).

## Graphics and dialog

These card options are off by default, so an existing card looks and behaves
as before. Each one is in the card's visual editor, for both layouts unless
noted. The graphic options appear only when the bed can draw a graphic and it
is shown.

| Option | Default | Effect |
|--------|---------|--------|
| `show_percentage_graphic` | `false` | Draws percentage position feedback and estimates as a schematic pose, from flat at 0% to fully raised at 100%. Labels keep the percentage. Degree feedback keeps its measured angle |
| `show_lumbar_graphic` | `false` | Adds a separate lumbar section between head and feet, with its own label, and orders readouts head, lumbar, feet. Beds without a lumbar motor keep two panels |
| `show_graphic_labels` | `true` | `false` hides only the labels beneath the graphic. Compact readouts, tooltips and controls stay |
| `open_dialog` | `false` | Compact layout only. Clicking the bed graphic or the expand button opens the full card in a dialog instead of following `navigation_path` |
| `dialog_config` | none | Full-card options used only inside the dialog |

The percentage pose uses a fixed 0 to 75° drawing range. It is not your bed's
physical angle, and the lumbar geometry is not a model of the bed's linkage.
A measured angle above 75° is drawn at 75° and labelled with its real value.
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
holds, [tap to move](#tap-to-move) and Stop work as on the full
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

## Customizing the card

Everything is configurable from the card's **visual editor** (no YAML needed):

- **Show or hide sections:** toggle Position, Firmness, Presets, Memory, Lighting,
  Massage, Utility, Climate, Connection, and the bed-angle graphic on or off. Only the
  sections your bed has are listed.
- **Reorder sections:** use the up and down arrows next to each section to
  change the order they appear on the card.
- **Choose which memory positions to show:** pick exactly the memory slots you
  use instead of showing all of them.

**Recalling and saving positions.** In the Memory section, tap a position to
move the bed to it. To store the bed's *current* position, tap **Save…** in the
Memory header, then tap the position you want to overwrite (tap **Cancel** to
back out). The Save button only appears for beds that support saving. A button
that overwrites a saved position asks for confirmation in the card first.

**Buttons that ask first.** A button that asks for confirmation, such as a
preset save or a reset, is always a plain tap: holding it never sends it, and
nothing is sent until you confirm.

**Other controls.** On a bed whose sides share one Bluetooth connection, the
**Controlled side** select sits with the motor controls and picks the side
they move. A light whose state the bed does not report gets separate On and
Off buttons, like a switch. When a bed has two controls for one place in the
card, such as a massage timer button and a remaining-time sensor, both are
shown.

**Names and icons follow your entities.** The card displays each control using
its entity's own name and icon, so to relabel something you just rename the
entity (Settings → Devices & Services → your bed → the entity → ⚙). For example,
rename **Memory 1** to *"Flat"* and give it a bed icon, and the card's first
memory tile becomes a bed icon labelled "Flat". This is purely cosmetic and
local to you. The card finds entities by the integration's internal keys, so
renaming or re-icon-ing never breaks it, and other users keep the tidy defaults
(*Memory 1–6* with numbered icons).

<details>
<summary><b>YAML options</b></summary>

```yaml
type: custom:adjustable-bed-card
device_id: <your bed device>   # the bed to control (the card prompts you to pick one if omitted)
name: Bedroom Bed              # optional, overrides the card title
section_order: [motors, memory, lighting]  # optional, render order (default order otherwise)
memory_save: true              # optional, show the "Save…" button (default: true)
memory_slots: [1, 2, 3]        # optional, which memory positions to show (default: all)
tap_to_move: false             # optional, a tap starts a motor and the next tap stops it (default: false)
show_percentage_graphic: false # optional, draw percentage positions as a schematic pose (default: false)
show_lumbar_graphic: false     # optional, draw a separate lumbar section (default: false)
show_graphic_labels: true      # optional, labels beneath the bed graphic (default: true)
# Each section defaults to shown; set to false to hide:
show_graphic: true
show_motors: true
show_firmness: true
show_presets: true
show_saved_positions: true
show_memory: true
show_lighting: true
show_massage: true
show_utility: true
show_climate: true
show_connection: true
```

</details>

## Development

Every entity tells the card where it belongs: its `card_section` attribute
names the section (or `hidden`), and `card_role`, `card_motor` and
`card_slot` pick its control there where the entity's domain does not. The
integration declares these in `card.py` and on each entity's spec or
description, so the card needs no list of entity keys. They are capability
attributes, so the card still finds an entity while it is unavailable.
After adding or moving an entity, regenerate the frontend tests' placement
fixture with `uv run --no-sync python -m tests.card_placements`.

Run `bun run check`, `bun test` and `bun run test:browser` from
`custom_components/adjustable_bed/frontend`. The browser checks use synthetic
Home Assistant state and recorded service calls, and require Chromium (or
`CHROMIUM_PATH`).
