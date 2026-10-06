# Wake-up automation

[Import Adjustable Bed wake-up](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FkristofferR%2Fha-adjustable-bed%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fadjustable_bed%2Fwake_up.yaml)
into Home Assistant. Alternatively, open **Settings → Automations & scenes →
Blueprints → Import blueprint** and paste the
[blueprint's GitHub URL](https://github.com/kristofferR/ha-adjustable-bed/blob/main/blueprints/automation/adjustable_bed/wake_up.yaml).
Requires Home Assistant **2026.9.0+** and a configured Adjustable Bed integration.
Importing the blueprint does not move the bed.

1. Create an automation from **Adjustable Bed wake-up**, choose the local wake-up
   time and days, and select your bed. An empty day selection disables scheduled runs.
2. Leave **Side(s)** at **Use selected device** for a standalone bed or a paired
   child. A paired parent defaults to both sides; choose **Left** or **Right**
   to narrow it. Conflicting child-side selections are rejected.
3. Choose **Timed raise** or **Recall hardware memory**, using the requirements below.
4. Optionally select **Under-bed lights** light or switch entities for the intended
   side(s). The picker also shows other bed switches; select only lighting, not
   massage, synchronization or automatic-drive controls. Light selection is independent
   of the movement target. Leave it empty to skip lighting.
5. Save with a clear name, then test the movement while awake before relying on
   its schedule. **Run actions** moves the bed immediately and bypasses the weekday condition.

| Option | Required capability and behavior |
|--------|----------------------------------|
| Timed raise | A supported `back` or `head` axis and timed movement. Back is usually the main upper-body section; Head is a separate head/neck axis where available. Raises once for a ceiling of 100–30000 ms, default 1000 ms. Unsupported axes/durations are rejected by the integration before movement. |
| Recall hardware memory | A previously saved, tested slot supported by every selected side. Recalls memory 1–8 where available using the controller's finite recall action. It may move several sections. Raise duration does not apply, and accepting a slot number does not create memory support. |
| Under-bed lights | Adjustable Bed **Under-bed lights** entities, exposed as `light` entities or `switch` entities with explicit on/off control. Only entities whose HA state is `off` receive their corresponding `light.turn_on` or `switch.turn_on` action, after the movement action finishes. Already-on, missing, unknown and unavailable lights are skipped. Toggle-only lighting buttons are not offered. |

The automation uses existing [`timed_move` and `goto_preset` actions](SERVICES.md#movement-and-memory).
It does not require position feedback, estimated percentages or software presets.
The timed movement ceiling begins after connection/preparation; connection and
release cleanup can make the action take longer. Some controllers stop earlier.
A recall action finishing is not proof that the bed reached its stored position.
Combined sides follow the integration's connection strategy and need not start together.

Use the bed's existing **Stop** control or [`adjustable_bed.stop_all`](SERVICES.md#examples)
with the same device/side to cancel active movement. Disabling future scheduled
runs is separate from stopping a movement already in progress.

Home Assistant must be running at the scheduled local time. Missed runs are not
replayed on startup. Each trigger makes one movement request, with the integration's
normal bounded connection attempts. This blueprint has no movement retry loop;
single mode ignores another trigger while a run is active. A missing bed, unsupported
capability, connection failure or unavailable action stops the run with an error in
the automation trace, so lighting does not then run. Light action failures also
remain errors. Skipped lights are visible in the trace and do not confirm lighting
success. Check the trace when a scheduled run does not behave as expected.
