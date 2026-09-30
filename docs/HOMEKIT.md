# Apple Home and Siri

Use named scripts for each bed section's **raise**, **lower**, and **stop**
actions. Export them through Home Assistant's HomeKit Bridge for Apple Home,
then use scenes or Siri Shortcuts for phrases such as “Raise my bed back” and
“Stop my bed back”. No additional bed integration is required.

## Why the bed appears as blinds

HomeKit Bridge maps our cover entities to window coverings. For a cover with
open, close, and stop controls, its slider maps values above 70 to open, below
30 to close, and 30–70 to stop. That explains why “set it to 50 percent” stops
the bed. This is a command mapping, not measured bed position.
[HomeKit Bridge documents these mappings](https://www.home-assistant.io/integrations/homekit/#supported-integrations).

Renaming a cover does not change its HomeKit type. The scripts below call the
existing actions explicitly, without changing cover capabilities or enabling
position feedback. Each raise/lower request runs the same finite movement as
one HA cover action. It does not hold the dashboard button continuously or
promise to reach the fully raised/lowered position. Run it again after it
finishes for another adjustment.

## 1. Create the controls in Home Assistant

### Recommended: import the script blueprint

[Import Adjustable Bed section control](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FkristofferR%2Fha-adjustable-bed%2Fblob%2Fmain%2Fblueprints%2Fscript%2Fadjustable_bed%2Fsection_control.yaml)
into your Home Assistant instance. You can also open **Settings → Automations &
scenes → Blueprints → Import blueprint** and paste the
[blueprint's GitHub URL](https://github.com/kristofferR/ha-adjustable-bed/blob/main/blueprints/script/adjustable_bed/section_control.yaml).

1. Open **Adjustable Bed section control** in the Blueprints list to create a script.
2. Select the **Bed section**, for example your back section cover. The picker
   shows Adjustable Bed covers; for a split bed, choose the intended side.
3. Choose **Raise**, **Lower**, or **Stop** and save with a clear name from the
   table below.
4. Repeat for the other actions and sections you want to control.

The blueprint creates **one script per use**, so back and legs need six scripts.
It requires HA 2026.9.0+ and an already configured Adjustable Bed integration.
Importing it does not move the bed. Running a saved script performs its action.

| Script name | Blueprint action | Bed section |
|-------------|--------|--------|
| Bed back up | Raise | Back section cover |
| Bed back down | Lower | Back section cover |
| Bed back stop | Stop | Back section cover |
| Bed legs up | Raise | Legs section cover |
| Bed legs down | Lower | Legs section cover |
| Bed legs stop | Stop | Legs section cover |

Create equivalent scripts for any additional section you use. Single mode
ignores a duplicate invocation while that script is running instead of queuing
extra movements. Stop has its own script, so it can run while a movement script
is active. Do not put stop behind movement in a shared queued script.

### Alternative: YAML scripts

Merge [the six example scripts](examples/homekit_scripts.yaml) into your
existing `scripts.yaml`, replacing `cover.bed_back` and `cover.bed_legs` with
your actual entity IDs throughout. Find them under **Settings → Devices &
services → Adjustable Bed → your device**. Keep the existing
`script: !include scripts.yaml` entry in `configuration.yaml`. If you use
another script layout, merge into that layout rather than adding a second
`script:` key. Reload scripts after checking the configuration. Choose either
the blueprint or YAML approach for each control; you do not need both.

### Split beds and stopping

For a split bed, use the **specific side's section entity** in every script.
For example, give the right back scripts unique IDs such as
`bed_right_raise_back` and names such as **Right bed back up**. Duplicate them
for the left side using its entities. Do not select the parent/both-side cover
when you intend to move only one side.

The section stop uses that cover's existing stop behavior. Some controllers
stop more than one motor; these scripts cannot add independent hardware stops.
For a whole-bed stop, create a separate **Bed stop** script with this sequence:

```yaml
sequence:
  - action: adjustable_bed.stop_all
    data:
      device_id: <bed device ID>
```

Select the parent device to stop both sides, or a child device to stop only
that side. This action takes a **device ID**, not an entity ID. See
[side targeting](SERVICES.md#targeting-a-bed-or-side).

## 2. Add the scripts to Apple Home

In your existing **HomeKit Bridge** integration's configuration, include the
new script entities. If using an include filter, retain all existing selections
and add the scripts you created. Select them by name in the UI. For YAML-managed
bridges, use their actual entity IDs: blueprint-created scripts get IDs from
their names, which can differ from the example YAML IDs below:

```yaml
include_entities:
  - script.bed_raise_back
  - script.bed_lower_back
  - script.bed_stop_back
  - script.bed_raise_legs
  - script.bed_lower_legs
  - script.bed_stop_legs
```

For a YAML-managed bridge, merge these into its existing
`homekit` → bridge entry → `filter` → `include_entities` list. This snippet is
only the list, not a complete bridge configuration. An include-only filter
limits what is exported, so replacing your filter with this example could
remove other accessories. Follow the [HomeKit filter guide](https://www.home-assistant.io/integrations/homekit/#configure-filter)
for your existing include/exclude configuration. A new bridge can be added via
**Settings → Devices & services → Add integration → HomeKit Bridge**.

HA exports scripts as action switches. Turning one **on** runs its action;
HomeKit Bridge ignores **off** commands and resets the switch display on a
timer (10 seconds in HA 2026.9.3), independently of script completion. The
switch state does not report movement or position. To stop, turn on **Bed back
stop** or **Bed legs stop**. Turning the movement switch off does not stop
the bed. This behavior is defined by [HA's script switch mapping](https://github.com/home-assistant/core/blob/2026.9.3/homeassistant/components/homekit/type_switches.py).

Keep the original covers if you still use their HomeKit controls. Optionally
exclude only those covers from the bridge to remove duplicate sliders. Do not
delete HA cover entities or reset/re-pair the bridge for this setup.

### Natural phrases with Apple Home scenes

In Apple Home, choose **Add → Add Scene → Custom**. Name the scene **Raise my
bed back**, add only the **Bed back up** script switch, and set it to **On**.
Repeat for lower and stop, then for the other sections/sides. Use distinct
names for the script switches and scenes to reduce ambiguous Siri matches.
Invoke the scene by name, for example “Siri, Raise my bed back”. If Siri treats
the name as a generic accessory command, try “Siri, activate Raise my bed back”
or choose a more distinctive scene name.

Each scene should turn on just its intended action switch. Do not capture all
bed switches into a scene or include a movement alongside stop. These scenes
trigger actions; they do not represent a lasting bed position. Apple documents
[scene creation and Siri activation](https://support.apple.com/102313).

## Siri Shortcuts without a HomeKit Bridge

For direct Siri control from your Apple device, connect the Home Assistant
Companion App to your HA server. In Apple's **Shortcuts** app, create a shortcut,
add Home Assistant's **Run Script** action, and select one of the scripts above.
Name it with the phrase you want to say, such as **Stop my bed back**. Repeat
for each desired action. This route does not require exporting anything to
Apple Home.

You can also skip HA scripts: add Home Assistant's **Perform action**, select
your server and `cover.stop_cover`, and supply this **Action data**:

```json
{"entity_id": "cover.bed_back"}
```

Use `cover.open_cover` for raise and `cover.close_cover` for lower, with the
same target. **Perform action** supports stop explicitly; the Companion App's
**Control cover** shortcut action lists only open, close, and toggle. Use the
current action names rather than the deprecated **Call Service** shortcut.
See the [Companion App's Siri instructions](https://companion.home-assistant.io/docs/integrations/siri-shortcuts/)
for OS requirements and available actions. For household Apple Home/HomePod
control, start with the bridge-and-scene route above.

## Presets and longer adjustments

Existing Flat, Zero G, and memory buttons can also be included in the bridge.
They become action switches; use a scene to turn on the desired preset. Include
only buttons your bed actually provides, and use recall rather than save-memory
buttons for voice presets.

For an adjustment with an explicit duration, create a separate custom script
using an [`adjustable_bed.timed_move` action](SERVICES.md#examples). The blueprint
intentionally offers the existing cover actions only; leave its shared file intact.
Choose the actual motor and device/side and start with the documented one-second
example. Duration is a ceiling, not a guaranteed amount of travel. Keep a
separate stop script. Do not build an unbounded repeat loop that depends on a
later Siri command arriving. Position targets are available through existing
position actions only where supported; percentages in the HomeKit cover UI do
not create that support.

## Check the setup

First run each script in HA and confirm it targets the intended section and
side. Then test its Apple Home switch or Shortcut, followed by its voice phrase.
Check a second invocation after the first finishes and an explicit stop during
movement. Confirm unrelated bridge accessories remain available.

If a command fails, check the HA script trace before changing Bluetooth options.
If it works in HA but not Apple Home, check bridge inclusion and the script's
entity ID. If tapping the scene works but speaking does not, check the Siri
language and scene/shortcut name. A short movement is expected from a single
cover command; use the bounded timed action for an explicit duration.

The scripts use existing HA services and do not require a BLE implementation
change. Actual Siri recognition and Apple Home presentation depend on the
Apple device and language and need validation on that setup.
