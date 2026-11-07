# Jensen

**Status:** ✅ Tested on JMC400 (motion, position reports, massage and memory
recall, [#146](https://github.com/kristofferR/ha-adjustable-bed/issues/146) and [#631](https://github.com/kristofferR/ha-adjustable-bed/issues/631)); JMC400 lights and fan, and every LinOn control,
are implemented from app evidence and await user confirmation.

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models
- Jensen JMC400 (JMC 400), including its LinON Entry box
- Jensen LinOn beds named "Adjustable Bed" or "Jensen Bed" (LinonPI services)

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | Adjustable Sleep 2.0.37 (106) | `air.no.jensen.adjustablesleep` |
| ✅ | Adjustable Sleep 2.0.29 (98) | `air.no.jensen.adjustablesleep` |

The `air.` prefix is historical: both versions are React Native apps. The app
drives three bed families:

- **JMC400** beds use the `jensen` bed type (this page).
- **LinOn** beds ("Adjustable Bed"/"Jensen Bed" names) use the Svane bed type's
  Jensen LinOn profile; see [LinOn](#linon) below. 2.0.29 never wrote a LinOn
  frame; 2.0.37 does.
- **Linak**-based Jensen beds use the [Linak](linak.md) bed type.

## Home Assistant setup

Choose **Jensen / Svane** in the bed-type list (a detected JMC400 box is shown
there too), then answer which app and bed you use: the Jensen Adjustable Sleep
app with a JMC400 bed (this page; it then asks the PIN, motor count, whether
massage motors are fitted and whether to read positions) or with a
[LinOn](#linon) bed, or the [Svane Remote](svane.md) app with a Svane Bed or a
JMC400 bed. The JMC400 name and the LinonPI services occur with both apps, so
they never decide the answer; the apps' own name rules suggest it the same way
in Bluetooth and manual setup. A LinON Entry box is JMC400 hardware, not a
LinOn bed. **Reconfigure** changes an existing bed's app or bed; existing
entries keep their route until then. Configure lists the JMC400 route by its
own name, for an entry of another bed type to switch to it.

## PIN Authentication

Jensen beds require a 4-digit PIN. The integration uses **3060** as the default
PIN, which works for most beds.

**If commands don't work or the bed disconnects immediately:**
1. Go to **Settings** → **Devices & Services** → **Adjustable Bed**
2. Click the **gear icon** on your Jensen device (each side's own settings, for a
   two-address pair)
3. Enter your bed's correct PIN in the **Jensen PIN** field
4. Save and reload the integration

Setup asks the PIN after the app question; leaving it empty uses 3060.

The bed answers the PIN frame; a rejection is logged as a warning.

## Features

| Feature | Supported |
|---------|-----------|
| Motor control (head, foot, both together) | ✅ |
| Position feedback | ✅ (pushed by the bed while it moves) |
| Go-to-position | ✅ |
| Flat | ✅ |
| Memory | ✅ 1 device slot on box type 4, otherwise 4 slots stored by Home Assistant |
| Massage | ✅ head, foot and wave, levels 0-10 (from the config report) |
| Light | ✅ levels 0-10 (from the config report) |
| Fan | ✅ levels 0-10 (from the config report) |
| Hold until release | ✅ ([renewable](../SERVICES.md#renewable-holds) `timed_move`: 300 ms refresh, then STOP once) |

Massage, light and fan appear only when the bed's config report lists them. The
bed does not report their state, so Home Assistant shows what it last sent.

### Memory

The app keeps its memories in one of two places, chosen by the box type in the
config report:

- **Box type 4** has one memory slot on the device. Save and recall use the
  device commands.
- **Every other box type** keeps up to four favourites in the app as measured
  head and foot positions, and recalls them with a go-to command. Home
  Assistant does the same: saving reads the current position and stores it
  (surviving restarts), and recall moves the bed back there. A slot must be
  saved before it can be recalled.

App favourites can also replay massage, light and fan settings. Home Assistant
recalls only the position; use a scene or script for the rest.

### Movement feedback

After a single flat, memory or go-to frame the bed moves on its own. Home
Assistant keeps the command running until the bed's position reports show the
move has ended: reports stop arriving, or an idle report repeats the last
position. A Stop or another command interrupts the move and sends STOP. If the
bed still reports motion after 90 seconds, STOP is sent and the command ends.
With angle sensing disabled, the frame is sent without waiting.

The bed pushes reports roughly every half second while it moves, but it can go
quiet for about two seconds while still travelling
([#631](https://github.com/kristofferR/ha-adjustable-bed/issues/631)). So the
command then queries the position once a second until two replies agree. A full
head sweep takes about 20 seconds, so these queries share the 90-second bound
rather than having their own. They do not interrupt the move.

## Protocol Details

JMC400 beds speak the [JMC400](jmc.md) wire format. Its
[Jensen Adjustable Sleep profile](jmc.md#jensen-adjustable-sleep) gives the
detection rules, the session start, every frame this route sends, the position
and config reports and the position anchors.

## LinOn

LinOn beds expose the LinonPI services that [Svane](svane.md) beds use, but the
Jensen app writes its own one-byte frames to them. They use the `svane` bed
type with protocol variant **`jensen_linon`**, shown as **Jensen Adjustable
Sleep app (LinOn)**. Answer **Jensen Adjustable Sleep app with a LinOn bed
named Adjustable Bed or Jensen Bed** in the
[Jensen / Svane question](#home-assistant-setup); it is not a row of its own.
Setup suggests it for new beds whose name contains "Adjustable Bed" or
"Jensen Bed" (the app's rule); `auto` keeps the Svane app profile, so existing
entries change only through **Reconfigure**. Beds named "Jensen Bed" are
discovered by name; "Adjustable Bed" is too generic, so those beds are
found by their head service UUID.

All writes are with response. Head uses service `0000abcb`, foot `0000c258`
and the light `0000d07b`:

| Command | Characteristic | Bytes |
|---------|----------------|-------|
| Up / down (held) | `000001ac` up, `0000bae9` down, in the head or foot service | `01`, resent every 800 ms |
| Head and foot together | head, then foot direction characteristic, alternating | `01` every 800 ms |
| STOP | `000001ac` in the head, then the foot, service | `FF` |
| Flat | `0000143d` in the head, then the foot, service | `00` |
| Under-bed light | `0000a8e0` | on `01 00 00`, off `00 00 00` |

The app sends STOP after every movement and for every stop control. It repeats
the STOP pair until a 20 s cap, which Home Assistant does not copy. Home
Assistant also sends STOP when a flat is interrupted, because the motors keep
moving on their own after its frames.

Releasing a held control ends the current 800 ms interval at once and sends the
STOP pair, as the app does when it clears its repeat timer on release. A
[renewable hold](../SERVICES.md#renewable-holds) (`timed_move` with
`hold_owner` and `hold_generation`) refreshes every 800 ms until its lease runs
out, then sends the STOP pair.

The app offers more than reaches the bed. Its light intensity slider crashes
the app instead of writing, its favourite recall stalls before its first write,
and it never subscribes to position reports. Home Assistant therefore offers
no light level, memory or position feedback for LinOn beds.

## Limitations

- The position anchors come from one JMC400.
- JMC400 lights, fan and device memory have no hardware confirmation yet.
- Massage wave only has an effect while head or foot massage runs.
- LinOn control comes from app evidence only; no LinOn bed has been tested.
