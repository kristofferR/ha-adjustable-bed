# Jordan's Tranquil app profile

Select **Jordan's Tranquil app** manually when the bed uses Android package `com.okin.bedding.tranquil` (Jordan's Tranquil). Shared OKIN names and GATT UUIDs do not identify this app. The implementation follows the independently accepted APK Protocol Audit of version 1.0.2/code 3 (artifact SHA-256 `595749e9f8eb2b654d88ad477fa80e4dfe5849335889b8c241fbd22faf3f5bda`) and the cluster 010 reconciliation with the Customatic Z-Series app. Physical operation is unverified.

The app reuses the [Serenity](serenity.md) controller core: the same transport, 14-byte frame, refresh/release lifecycle and notification parser. Its action table, save codes and buttons are its own. The app always shows its Z280 remote and massage pages; the stored model choice is ignored. Manufacturer strings, including CST13/CST14, never enable alarm controls in this app.

## Transport and packets

| Role | UUID |
|---|---|
| Service | `62741523-52f9-8864-b1ab-3b3a8d65950b` |
| Command | `62741525-52f9-8864-b1ab-3b3a8d65950b` |
| Notify | `62741625-52f9-8864-b1ab-3b3a8d65950b` |
| Manufacturer read | `0000180a-...` / `00002a29-0000-1000-8000-00805f9b34fb` |

Frames are `0c 02`, a big-endian 32-bit primary field, a big-endian 32-bit secondary field, then four zero bytes. There is no checksum, encryption, side selector, PIN or bonding. The app leaves the Android write type unchanged; HA prefers acknowledged writes when `write` is advertised, otherwise `write-without-response`. This is a host policy.

## Reachable commands

Values occupy the primary field unless a secondary value is listed.

| Control (`hold_control` name) | Primary | Secondary | Source |
|---|---:|---:|---|
| Head up/down (`head_up`, `head_down`) | `0x1`, `0x2` | 0 | Touch and voice |
| Foot up/down (`foot_up`, `foot_down`) | `0x4`, `0x8` | 0 | Touch and voice |
| Remote Selector 4 up/down (`selector_4_up`, `selector_4_down`) | `0x10`, `0x20` | 0 | Lumbar-icon touch, voice "lumbar" |
| Remote Selector 5 up/down (`selector_5_up`, `selector_5_down`) | `0x40`, `0x80` | 0 | H TILT touch, voice "head tilt" |
| Flat (`flat`) | `0x08000000` | 0 | Touch and voice |
| Zero Gravity (`zero_g`) | `0x1000` | 0 | Touch and voice |
| Lounge (`lounge`) | `0x2000` | 0 | Touch, voice "lounge"/"leisure" |
| M1, M2 (`memory_1`, `memory_2`) | `0x10000`, `0x40000` | 0 | Touch |
| Anti-Snore (`anti_snore`) | `0x8000` | 0 | Voice only (the touch button is hidden) |
| Save Zero Gravity, Save Lounge (`save_zero_g`, `save_lounge`) | `0x08001000`, `0x08002000` | 0 | Flat + preset chord |
| Save M1, Save M2 (`save_memory_1`, `save_memory_2`) | `0x08010000`, `0x08040000` | 0 | Flat + preset chord |
| Head/foot massage cycle (`massage_head_cycle`, `massage_foot_cycle`) | `0x800`, `0x400` | 0 | Massage page |
| Massage mode, timer cycle (`massage_mode_cycle`, `massage_timer_cycle`) | `0x10000000`, `0x200` | 0 | Massage page |
| Massage toggle (`massage_toggle`) | `0x100` | 0 | Massage page |
| Massage off (`massage_off`) | `0x02000000` | 0 | Voice only |
| Wave 1, 2, 3 (`wave_1`..`wave_3`) | 0 | `0x80000`, `0x100000`, `0x200000` | Voice only |
| Light toggle (`light_toggle`) | `0x20000` | 0 | Massage page and voice |
| Light on, off (`light_on`, `light_off`) | 0 | `0x40`, `0x80` | Voice only |
| Release/Stop | 0 | 0 | Release, cancel and timed stops |

The lumbar-icon and H TILT buttons send builder operations 4 and 5, while the app's presenter method names are swapped. Voice labels agree with the touch labels. As with Serenity, HA exposes literal **Remote Selector 4/5 Up/Down** buttons and creates covers only for Head and Feet. The physical actuator behind each selector is unverified.

Only M1 and M2 are numbered memory slots. **Save Zero Gravity** and **Save Lounge** buttons cover the other chords. Light on/off is an assumed-state switch; **Toggle Light** sends the native toggle. There is no RGB or brightness command, although the app help mentions color cycling.

## Timing and cleanup

Held controls repeat every 100 ms. Release attempts two zero frames at +100 and +200 ms from one origin, with a fresh cancellation event so cancellation cannot suppress either. Every release is global, so all covers share one scheduler resource.

Button and preset durations: Flat holds 1500 ms and Lounge, Zero Gravity, Anti-Snore, waves, massage off and light commands hold 500 ms, matching the app's voice deadlines. Save buttons hold five seconds, matching the app help; the app has no hold timer or storage acknowledgement. M1/M2 recall, selectors and massage-page buttons use the same 500 ms bound as an HA policy. `hold_control` holds any literal action for 0.1 to 60 seconds.

Excluded app behavior: the voice "stop" branch sends Head Up before scheduling STOP, so HA sends STOP only. Also excluded: unbounded voice motion, remote touch-mask replay, delayed stops that overlap newer commands, and streams that survive disconnect or device changes.

## Notifications and diagnostic state

The parser is shared with Serenity: inputs of ten bytes or fewer are ignored; byte 1 equal to 12 is an alarm reply (signed repeat/hour/minute at 4/6/7, subtype at 5, enabled at 9); otherwise signed byte 10 is a change-only status code. A changed status during a pending save reports the app's local save code (Zero Gravity 5, Lounge 3, M1 4, M2 8). Any recall clears it. Otherwise it updates the massage timer code; 1/2/3 mean 10/20/30 minutes in the app. Alarm replies are parsed even though this app has no alarm page.

State keys: `tranquil_manufacturer`, `tranquil_status_code`, `tranquil_massage_timer_code`, `tranquil_massage_timer_minutes`, `tranquil_save_event_code` and `tranquil_alarm_type`, with alarm attributes `tranquil_alarm_repeat`, `tranquil_alarm_hour`, `tranquil_alarm_minute` and `tranquil_alarm_on`. The manufacturer is read one second after subscribing; **Refresh Manufacturer** repeats the app's on-resume read.

## Deferred validation

For real users after a release: actuator mapping of selectors 4 and 5, ATT write mode, repeat and STOP arrival, save persistence and minimum hold time, massage and light semantics, and notification contents.
