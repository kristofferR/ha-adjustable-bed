# Customatic Z-Series app profiles

Select **Customatic Z-Series app (Z-230)** or **Customatic Z-Series app (Z-280)** manually for Android package `com.okin.bedding.glory` (Customatic Technologies Z-Series). Pick the model you chose on the app's selection screen. Shared OKIN names and GATT UUIDs do not identify the app or the model. The implementation follows the independently accepted APK Protocol Audit of version 1.0.4/code 5 (XAPK SHA-256 `3a700cc4869080ec570c2e8653601b2755c08c7d3e3b13fa6a233e2af2bce7a8`) and the cluster 010 reconciliation with Jordan's Tranquil. Physical operation is unverified.

The profiles reuse the [Serenity](serenity.md) controller core: transport, 14-byte frame, refresh/release lifecycle and notification parser. Action tables, save codes, buttons, timing and the alarm page are this app's own. These profiles are separate from the six-byte [Customatic Clarity/Jerome's/Remedy](customatic.md) apps.

## Transport and packets

Same service, command, notify and manufacturer roles as [Tranquil](tranquil.md#transport-and-packets). Normal frames are `0c 02`, two big-endian 32-bit fields and four zero bytes. Alarm frames use the same command characteristic. There is no checksum, encryption, PIN or bonding.

## Reachable commands

| Control (`hold_control` name) | Primary | Z-230 | Z-280 |
|---|---:|:---:|:---:|
| Head up/down (`head_up`, `head_down`) | `0x1`, `0x2` | yes | yes |
| Foot up/down (`foot_up`, `foot_down`) | `0x4`, `0x8` | yes | yes |
| Head and Foot up/down (`head_foot_up`, `head_foot_down`) | `0x05`, `0x0a` | yes | |
| Remote Selector 5 up/down (`selector_5_up`, `selector_5_down`) | `0x10`, `0x20` | | yes |
| Flat (`flat`) | `0x08000000` | yes | yes |
| Anti-Snore (`anti_snore`) | `0x8000` | yes | yes |
| Zero Gravity (`zero_g`) | `0x1000` | yes | yes |
| TV (`tv`) | `0x4000` | yes | yes |
| M1 (`memory_1`) | `0x10000` | yes | yes |
| M2 (`memory_2`) | `0x40000` | | yes |
| Save Zero Gravity, Save TV, Save M1 (`save_zero_g`, `save_tv`, `save_memory_1`) | `0x08001000`, `0x08004000`, `0x08010000` | yes | yes |
| Save M2 (`save_memory_2`) | `0x08040000` | | yes |
| Light toggle (`light_toggle`) | `0x20000` | yes | yes |
| Massage toggle (`massage_toggle`) | `0x100` | yes | yes |
| Massage mode, timer cycle (`massage_mode_cycle`, `massage_timer_cycle`) | `0x10000000`, `0x200` | yes | yes |
| Massage intensity (`massage_intensity_cycle`) | `0x0c00` | yes | |
| Head/foot massage cycle (`massage_head_cycle`, `massage_foot_cycle`) | `0x800`, `0x400` | | yes |
| Release/Stop | 0 | yes | yes |

The secondary field is always zero. The Z-280 extra control shows neck artwork, while the presenter calls it lumbar and this app's builder operation 5 emits `0x10`/`0x20`. HA exposes literal **Remote Selector 5 Up/Down** buttons; the physical actuator is unverified. The app has no voice control, waves, massage off or discrete light on/off, so those are not exposed.

Numbered memory: Z-230 has M1, Z-280 has M1 and M2. **Save Zero Gravity** and **Save TV** buttons cover the named chords.

## Timing and cleanup

Touch controls repeat every 100 ms until release, then two zero frames are attempted at +100 and +200 ms. Remote and massage releases both end in that global STOP in HA. The app defines no deadline for a touched button, so HA bounds ordinary buttons and presets by the configured motor pulse count at the app's 100 ms cadence (default 10, so one second). Setup accepts 1 to 600 pulses for these profiles, and a stored value outside that range is clamped. Save buttons hold five seconds, matching the app help. The app has no save timer or storage acknowledgement. `hold_control` holds any literal action for 0.1 to 60 seconds.

## Alarm

The app shows its alarm page only when the Device Information manufacturer string is exactly `CST13` or `CST14` (case-sensitive), for either model. HA reads it one second after subscribing and on **Refresh Manufacturer**, and stores the last successful result with the entry so it survives disconnects and restarts. A failed read changes nothing: while the result is unknown, an alarm action reconnects and reads it again before writing. A confirmed other string makes the alarm actions unavailable.

| Frame | Bytes |
|---|---|
| Alarm on | `07 05 repeat wake hour minute 00 01 01` |
| Alarm off | `07 05 00 00 00 00 00 00 01` |
| Clock | `07 06 (year-2000) month day weekday hour minute second` (binary, Sunday = 0) |
| Status query | `00 c0` |

`repeat` is today's weekday bit (Sunday = bit 0). If the time is earlier than the current hour and minute, the next day's bit is used, wrapping Saturday to Sunday. `wake` is 1 for massage and 2 for M1. The final byte is the app's stored bed selection, which defaults to 1 and has no setter.

`zseries_set_alarm` mirrors opening the alarm page and tapping its switch: clock frame, alarm frame, then two queries at +500 and +800 ms. Enabling requires both a time and a wake mode. In the app the clock is sent when the page opens and the alarm only after a later user tap; HA sends the two frames back-to-back, a host choice that hardware validation should confirm. `sync_clock` sends the clock frame and the same queries. Times use Home Assistant's time zone. The app's other wake-type mappings, the `-128` repeat sentinel and the checksum clock-adjust builder are unreachable and are not implemented.

## Notifications and diagnostic state

Same parser as [Tranquil](tranquil.md#notifications-and-diagnostic-state), with keys prefixed `zseries_`. Local save codes: Zero Gravity 5, M1 4, TV 6, M2 8. Alarm replies populate **App alarm state** with repeat, hour, minute and on attributes.

## Exclusions and deferred validation

Excluded: remote touch-mask replay, delayed stops overlapping newer commands, streams surviving disconnect or device changes, the dead voice handler (including its head-up-before-stop branch), unused legacy pages and helpers, and alarm writes queued while disconnected. For real users after a release: selector and combined-motor mapping, ATT write mode, STOP arrival, save persistence, alarm behavior (including acceptance of the back-to-back clock and alarm frames) and notification contents.
