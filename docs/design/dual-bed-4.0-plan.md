# Dual Bed 4.0 — Implementation Plan (issue #329)

> First-class paired-bed handling: one logical HA device exposing **left**, **right**,
> and **both** controls. The common case — two independent BLE devices (Linak and most
> split-kings) — is the pathfinder; Octo's active-connection switching is a harder profile
> layered on top (it's the direct fix for issue #327).
>
> **Target release: v4.0.** (v3.0 ships today *without* this.) Issue #329 is titled "Dual
> Bed 3.0" for historical reasons; the feature is retargeted to 4.0. Happy alignment: the
> v4.0 *feature* also bumps the *config-entry schema* to VERSION 4 (§3) — two different "4"s
> that land together.
>
> Status: **plan / not started**. This document is the implementation reference for the
> 4.0 epic. File:line references are accurate as of the planning commit and should be
> re-checked while implementing.

---

## 1. Context & root cause

`#329` asks for a first-class **paired-bed** model. Today the integration bakes in one
hard assumption everywhere:

> **one config entry == one BLE address == one HA device == one coordinator == one controller.**

Enforced by `async_set_unique_id(address.upper())` + `_abort_if_unique_id_configured()`
on every add path (`config_flow.py:448-449, 922-923, 1147-1148, 1463-1464`). The
`DeviceInfo` is built purely from the MAC (`coordinator.py:801`,
`identifiers={(DOMAIN, self._address)}`), and every entity's `unique_id` is uniformly
`f"{coordinator.address}_{description.key}"` across all 9 platforms.

There are **two physically different dual-bed cases** that must converge on one UX:

- **Single-address, side-aware** (Sleep Number, SBI, Rondure, CB24, Kaidi Seat 1+2): one BLE link already
  reaches both sides; "side" is a per-command argument or wire-encoding. Sleep Number
  *already* ships per-side child entities within one device — `*_sides` tuple properties
  (`bed_presence_sides`, `sleep_number_setting_sides`, `thermal_climate_sides`,
  `footwarming_climate_sides`) + `_require_side(side)` dispatch
  (`beds/sleep_number.py:345-401, 513-604`).
- **Separate-address split** — two BLE MACs, one per side. This is the **most common**
  dual-bed reality and splits into two profiles:
  - **Independent two-device** (Linak — and most split-kings without a sync cable): two
    *ordinary, fully independent* links. Each side is a normal connection HA's Bluetooth
    manager already runs side-by-side, so both can be held concurrently with no PIN, no
    keepalive, no active-connection switching. Today users manage these as **two separate
    HA devices** by hand (the issue's stated pain). `beds/linak.py` has no pairing concept —
    its `two_motor_secondary` logic is two actuators on *one* controller, not two
    controllers.
  - **Active-connection-switching** (Octo, the hard special case): the official app "stores
    separate left/right BLE addresses and **switches the active connection between them**"
    (`docs/beds/octo.md:60`) + per-side PIN + 25 s keepalive. Today the flow only shows a
    passive text note telling the user to add the second side as a separate device
    (`config_flow.py:274-327`) — the direct cause of #327.

  *Reference setup (verified live):* the maintainer's own bench bed is **two active Linak
  config entries** — "Seng" (`CB:3D:68:A7:7B:D0`, adapter `90:15:06:F9:C5:4E`) + "Bed 4587"
  (`E8:B1:3A:17:60:0B`, adapter `auto`), both `bed_type=linak`, 2-motor, **23 entities each
  (46 total for one bed)**. This is the canonical independent-two-device pair and the
  Phase-1 validation target. (A physical sync cable historically mirrored the two sides — see
  the sync-cable caveat in §5.)

**Issue #327 root cause** is exactly this gap: a single Octo entry connects to one
address, so "Both Up", "Back", "Legs", and "Under-bed lights" only ever reach the **one
connected side**. `docs/beds/octo.md:60` even flags that `Back + Legs Up` is a *per-side*
preset, compounding the confusion. The paired model fixes #327 by modeling the second
address as the other side of one logical bed.

### Goals (from the issue)
- One logical HA device with left / right / **both-where-safe** controls.
- A dedicated **pairing wizard** for two sibling devices; an **opt-in conversion** of two
  existing standalone entries.
- A **paired coordinator/controller wrapper** that either routes to one side-aware
  controller or fans out to two child coordinators.
- Service routing (`goto_preset`, `save_preset`, `stop_all`, `set_position`, `timed_move`)
  gains `left`/`right`/`both` targeting.
- **Existing single-bed entries keep working unchanged. Migration is opt-in.**

### Non-goals (first release)
- Auto-merging existing entries on upgrade.
- A **combined cover** with synthesized position/state.
- Pairing dissimilar bed types or mismatched motor layouts.

---

## 2. Load-bearing architecture decisions

These five invariants shape every later choice. Violating any one re-introduces the
fragility #329 is trying to remove.

1. **Composition over rewrite.** A new `PairedBedCoordinator` *owns* either one inner
   `AdjustableBedCoordinator` (single-address) or two child `AdjustableBedCoordinator`
   instances (separate-address). It holds **no `BleakClient` of its own**. Every per-link
   invariant — `_command_lock`, `_cancel_command`/`_cancel_counter`, idle/reconnect timers,
   Octo PIN keepalive, `_intentional_disconnect`, always-completes STOP — is inherited
   *per child, unchanged*. This protects the recently-burned reconnect-storm fixes
   (#369/#378) instead of re-deriving them. For the common independent-two-device case
   (Linak), this makes the wrapper **nearly trivial** — it orchestrates two already-working
   coordinators; the slot-switching/keepalive machinery is Octo-only.

2. **Children keep their MAC namespace forever.** A child side *always* keeps its original
   BLE address as the unique_id namespace (`{MAC}_{key}`) and its device identifier
   `{(DOMAIN, MAC)}`. The pair adds a synthetic layer *on top*; it never rewrites the child
   layer. This is what makes **conversion additive** (zero entity recreation, history
   preserved) and **unpair subtractive** (only the synthetic `_both` entities are removed).

3. **One config entry per pair, synthetic unique_id.** A paired bed is ONE config entry
   whose unique_id is `pair_<hash-of-sorted-member-addresses>` (never a member MAC — HA
   enforces one entry per MAC). One entry → one (paired) coordinator keeps
   `_get_coordinator_from_device` (`__init__.py:452-464`) first-match service resolution
   intact; the paired coordinator fans out internally.

4. **Capability presence is snapshot-driven, not live.** Which side/both entities exist is
   driven by a **persisted per-child capabilities snapshot** captured at pairing time
   (reusing the `#357` `_probe_capabilities`), NOT live controller tuples. A disconnected
   Octo side must NOT empty its capability tuple and churn its entities. Availability stays
   always-`True` (the `entity.py:23-32` invariant); a down side shows `unknown` *state*.

5. **Migration is a strict no-op for everyone else.** Bump config-entry `VERSION 3 → 4`,
   change the guard `entry.version > 3` → `> 4` (`__init__.py:142`). The v3→v4 branch only
   stamps the version and mutates **zero data** for entries lacking `CONF_PAIR_ID`. A v3
   single entry *is* a valid v4 single entry. Pairing is created only by the opt-in flow,
   never by migration (honors the no-auto-merge non-goal).

---

## 3. Data model (config-entry VERSION 4)

New `const.py` keys:

```python
CONF_PAIR_ID = "pair_id"                       # "pair_<hash>" synthetic, deterministic
CONF_PAIR_MODE = "pair_mode"                    # single_address | separate_address
CONF_PAIR_CHILDREN = "pair_children"            # ordered list[ChildDescriptor], len 2
CONF_PAIR_MEMBER_ADDRESSES = "pair_member_addresses"   # flat list, for discovery dedup
CONF_PAIR_SCHEMA_VERSION = "pair_schema_version"       # forward-compat within v4

PAIR_MODE_SINGLE_ADDRESS = "single_address"
PAIR_MODE_SEPARATE_ADDRESS = "separate_address"

SIDE_LEFT = "left"
SIDE_RIGHT = "right"
SIDE_BOTH = "both"        # central — no ad-hoc magic strings anywhere
```

`entry.data` for a paired (separate-address) bed:

```python
{
  CONF_PAIR_ID: "pair_4f9a2c…",
  CONF_PAIR_MODE: "separate_address",     # or "single_address"
  CONF_PAIR_SCHEMA_VERSION: 1,
  CONF_BED_TYPE: "octo",                   # SHARED family (mixed types are a non-goal)
  CONF_NAME: "Master Bed",                 # logical-device display name
  CONF_PREFERRED_ADAPTER: "auto",          # pair-level default; children override
  CONF_PAIR_MEMBER_ADDRESSES: ["AA:…:01", "AA:…:02"],
  CONF_PAIR_CHILDREN: [
    { "side": "left",
      CONF_ADDRESS: "AA:…:01",             # SAME as right for single_address; different for separate
      CONF_NAME: "Left",
      CONF_BED_TYPE: "octo",
      CONF_PROTOCOL_VARIANT: "auto",       # single_address: side_a/left wire-encoding
      CONF_PREFERRED_ADAPTER: "auto",      # per-side adapter (each side near a different proxy)
      CONF_OCTO_PIN: "1234",               # per-side PIN
      CONF_JENSEN_PIN: "",
      CONF_CB24_BED_SELECTION: 0x00,       # single_address CB24 A/B wire-encoding
      "capabilities": {                    # PERSISTED snapshot, disconnected-safe
          "motor_count": 2, "has_massage": false,
          "supports_memory_presets": true, "memory_slot_count": 4,
          "supports_position_feedback": false,
          "motor_keys": ["back", "legs"],
          "supports_lights": false, "captured_at": "2026-…" },
      "absorbed_entry_id": "01J…",         # provenance for unpair revert
      "origin_unique_id": "AA:…:01" },
    { "side": "right", … same shape … }
  ]
}
```

`entry.options` keeps `back_max_angle`/`legs_max_angle` only (the only options currently
read, `coordinator.py:470-484`), now keyed `{side: {...}}`.

### Single-address vs separate-address (the crux)
- **single_address** (one MAC): the ONE existing entry is rewritten in place. Both
  descriptors share `CONF_ADDRESS`, differing only in `side` + wire-encoding. No second
  child entry. `both` is the **native broadcast packet** (SBI `0xE5`, CB24 `0x00`)
  or a serialized left-then-right write (Sleep Number `bamkey` and Kaidi Seat 1+2)
  over the single `_command_lock`.
- **separate_address** (two MACs): a NEW parent entry is created. The two child **devices**
  (not entries) are re-homed to it via `device_registry.async_update_device(
  add_config_entry_id=parent, via_device=parent)` **before** the old entries are
  `async_remove`'d. (Crash-safe: HA GCs a device only when its *last* entry is removed.)

### Device/entity registry layout (asymmetric by mode)
- **separate_address**: synthetic parent device `{(DOMAIN, f"pair_{pair_id}")}`; the two MAC
  devices nest under it via `via_device`. Combined entities → parent device, unique_id
  `pair_<id>_<key>_both`. Per-side entities → child sub-device, unique_id `{MAC}_<key>`
  (unchanged) or `{MAC}_<key>_<side>`.
- **single_address**: NO synthetic device — reuse the existing single MAC device. `pair_id`
  lives only in `entry.data` for routing; per-side and both entities all attach to the MAC
  device.

### Migration
`VERSION 3 → 4` (`config_flow.py:178`), guard `> 3` → `> 4` (`__init__.py:142`). v3→v4 is a
**strict no-op** for entries without `CONF_PAIR_ID`: set version, mutate zero data.
Parametrized test asserts byte-identical post-migration `entry.data` across a
representative set of bed types.

---

## 4. Coordinator / controller wrapper

`async_setup_entry` (`__init__.py`) branches on `CONF_PAIR_ID in entry.data`:
- absent → the existing `AdjustableBedCoordinator`, verbatim (byte-identical to today);
- present → the new `PairedBedCoordinator`.

`PairedBedCoordinator` is a thin parent exposing the **same public surface** entities and
services already call (`async_execute_controller_command`, `async_stop_command`,
`async_seek_position`, `device_info`, `is_connected`, `register_*`), **plus a `side`
argument**. It owns the children and arbitrates capability:

```text
single_address:   side -> a per-call argument to the ONE inner controller
separate_address: side -> which child(ren) receive the command
```

### Side routing (pseudocode)

```python
async def async_execute_controller_command(self, fn_name, *args, side=SIDE_BOTH, **kw):
    targets = self._targets_for(side)                  # [left] | [right] | [left, right]

    # 1. PRE-FLIGHT: validate every target before commanding ANY.
    for child in targets:
        self._validate_capability(child, fn_name, args)   # raises ServiceValidationError

    if len(targets) == 1:
        return await targets[0].async_execute_controller_command(fn_name, *args, **kw)

    # 2. FAN-OUT 'both'. Each side marked 'started' at coroutine creation.
    results = await asyncio.gather(
        *(c.async_execute_controller_command(fn_name, *args, **kw) for c in targets),
        return_exceptions=True,
    )

    # 3. PARTIAL FAILURE: if any side raised, STOP every started side (fresh cancel
    #    event per child), swallow per-side stop errors, then raise one aggregated error.
    if any(isinstance(r, Exception) for r in results):
        await asyncio.gather(*(c.async_stop_command() for c in targets),
                             return_exceptions=True)
        raise PairedSideError(side_results=zip(targets, results))   # -> translated service error
```

```python
async def async_stop_command(self, side=SIDE_BOTH):
    # stop_all must NEVER fail-fast: await both children, swallow per-side exceptions,
    # then aggregate. Fixes the gap where the current handle_stop_all can skip a side.
    results = await asyncio.gather(*(c.async_stop_command() for c in self._targets_for(side)),
                                   return_exceptions=True)
    if any(isinstance(r, Exception) for r in results):
        raise PairedStopError(...)   # "could not confirm stop on side X"
```

### Connection mode (`pair_connection_mode`)
- `auto` (**default**) — start `concurrent`; fall back to `sequential` only on a real child
  connection-slot-exhaustion error (reuse the existing exhausted-adapters detection).
  Correct for the common case: two independent devices (Linak et al.) are ordinary links
  HA's Bluetooth manager already runs side-by-side, so `both` is genuinely simultaneous.
- `concurrent` — both children connected at once; true simultaneous `both`.
- `sequential` — connect/switch the active side per sub-command; the **Octo profile** (its
  firmware mirrors the official app's one-active-connection behavior). `_pair_command_lock`
  orders the connection switch in this mode only; a second proxy lets even Octo run
  `concurrent`.

The **single-BLE-connection constraint has two distinct meanings** that must never be
conflated: *per-peripheral* (never two links to the same MAC — children already enforce)
vs *per-adapter slot budget* (two Octo MACs CAN be concurrent iff two slots exist). The
per-side `preferred_adapter` captured in the wizard is what enables safe concurrency.

### Lifecycle details
- **Parked side (sequential)**: disconnect via `child.async_disconnect(reason="pair_switch")`
  which sets `_intentional_disconnect`, suppressing auto-reconnect so the parked side
  doesn't steal the active side's slot.
- **PIN keepalive**: the parent **never holds a child command lock across the keepalive
  window**. Sequential `both` interleaves per sub-command (release between sides) rather
  than across the whole macro-op.
- **Half-available setup / restart**: parent setup succeeds with *at least one (or zero)*
  reachable child; entities are created eagerly from the snapshot; the entry never goes
  `SETUP_RETRY` for a half-available pair. (Both children failing → `ConfigEntryNotReady`,
  like the single path.)
- **Method-introspection capabilities** (`type(self).method is not BedController.method`)
  do **not** delegate transparently through a wrapper. The parent must override every such
  property via a `_delegated_capability(name, mode)` base helper, or features silently
  vanish/appear.

---

## 5. Config-flow UX

**Tone rules** (apply to every string):
- Never lead with "BLE address" — say "this bed" / "the other side"; show the MAC in
  parentheses only for disambiguation (`Octo Bed (AA:BB:…:FF) — strong signal`).
- Always state consequences *before* they happen; present pairing as **safe and
  reversible**.
- Recommended choice first and/or labelled "(recommended)".
- Show RSSI/signal in every device list so two same-name beds are distinguishable and the
  user can pick the closer device per side.

### 5.1 Discovery-time sibling offer
Generalize `_get_octo_split_setup_note` (`config_flow.py:274-327`) into a **bed-type-generic**
`_find_pairing_siblings`. The trigger is simply **two discovered same-`bed_type` devices**
(normalized family-name match — handle `OCTOBrick` vs `OCTOBrick2`, `const.py:703,708`); it
is *not* gated to Octo, so Linak and any other split-king that presents as two devices is
covered. When a sibling exists, insert a 3-option menu *before* `bluetooth_confirm`:

1. **Set up as one bed (Left + Right)** *(recommended)*
2. Add only this side
3. *(implicit dismiss)*

Never auto-pair (two same-name beds could be in different rooms). Dismissal is remembered
per-address in a small `Store` only to stop re-nagging on rescans; the explicit "Pair two
beds into one" option in `async_step_user` is **always** available.

### 5.2 Pairing wizard (Octo-shaped)
- **A. Select left device** — eligible separate-address devices, RSSI shown.
- **B. Select right device** — left removed from the list; same-MAC re-selection blocked
  (`same_device` error: "That's the same bed you already picked.").
- **C. Side assignment** — cheap Left/Right dropdown, *not* a live connect-and-nudge.
  Honest copy: "Not sure? Pick either — you can swap sides later." (Swap is a one-click
  Reconfigure action.)
- **D. Per-side settings** — per-side adapter (default AUTO) + optional per-side PIN
  ("Leave blank if your bed doesn't ask for a PIN").
- **E. Verify** — runs `_probe_capabilities` per side **sequentially** (left, disconnect,
  right; ~15 s each). Copy: "Checking both sides — this can take up to a minute." Per-side
  checklist uses plain ✅/⚠️/❌ (reuse the #357 markdown style). Persists the per-child
  capabilities snapshot.
- **F. Name + confirm** — preview: "one device with **Left**, **Right**, and combined
  controls."

### 5.3 Conversion (two existing standalone entries → one pair)
This is the **primary on-ramp** for Linak and most users — they already have two standalone
entries today (the maintainer literally has "Seng" + "Bed 4587" live), so converting is the
common path, not an afterthought; hence a basic conversion ships in **Phase 1**. Lives in
the **options flow** of one entry (the user is contextually on "the bed to pair"). Builds the paired `entry.data` from both, creates the parent via a fresh flow,
**re-homes both child devices first**, then **defers** `async_remove` of the two old
entries until after the options flow returns (never delete the entry whose own flow is
running). Confirm copy: "The two original devices will be removed. Their entity history
stays under the new combined device. You can unpair later."

### 5.4 Unpair / reconfigure
- A paired entry's `async_step_init` renders a **paired menu**: per-side settings
  (adapter/PIN/name), **swap sides**, shared settings, **unpair**. The single-bed options
  form (which assumes one `bed_type`) is not reused for pairs.
- **Unpair**: recreate two standalone entries from the child descriptors (restoring
  original MAC unique_ids, repointing per-side devices/entities), then remove the parent.
  Only the meaningless `_both` entities are deleted. Confirm: "This splits {name} back into
  two separate beds. Combined controls will be removed; per-side history stays with each
  bed."

### 5.4a Sync-cable caveat
Some two-device beds are joined by a physical sync cable so one controller already mirrors
both sides (commanding one moves both — this is the maintainer's own bench setup). Pairing
those would double-drive redundantly. The integration **cannot detect the cable** over BLE,
so the wizard states it plainly: *"Pairing is for sides that move independently. If a sync
cable already keeps both sides together, keep a single bed instead."* — and the conversion
confirm repeats it. (Conversely, a user who removes the cable for independent control is
exactly who pairing serves.)

### 5.5 Single-address beds stay on their own flow
Sleep Number / SBI / Rondure / CB24 do **not** use the two-device wizard (they have one
MAC and per-side machinery already). They get a "Split: Left / Right / Both" selector on
their existing confirm/options form. Surface `CONF_CB24_BED_SELECTION` (`0x00`/`0xAA`/`0xBB`)
as a "Bed A / Bed B / Both" selector; existing CB24 users default to `0x00` unchanged.
**NEW-protocol CB24 (CBNew)** builders carry no side byte (`beds/okin_cb24.py:193-218`) → refuse
paired mode with a clear message until reverse-engineered.

---

## 6. Entity surface & service routing

### 6.1 translation_key contract (hard requirement)
**Side is ALWAYS the final token**: `back_up_left`, `back_angle_left`,
`sleep_number_setting_left`. No suffix = combined/both. Existing single-bed keys are never
renamed. This is mandatory because `discovery.ts` matches `sleep_number_setting`
(`discovery.ts:127`) and the greedy `/^(.+)_(up|down)$/` (`discovery.ts:149`) **before** any
side handling — so the card must strip the trailing side token *first*, then reuse all
existing key parsing unchanged. (`side` is not exposed to the frontend as an attribute —
only `translation_key`/`device_id`/`platform`/`name`/`hidden` are.)

### 6.2 Per-side + combined entities
- Generalize the Sleep Number `*_sides` tuple + `*_for_side`/`side=` dispatch pattern
  (`beds/sleep_number.py:345-401`) to articulation, presets, lights, massage. Platform
  loops (`for side in controller.<feature>_sides`) need no special-casing — `both` is just
  another value appended to the tuple.
- **Combined `_both` entity exists iff BOTH sides advertise the capability** (strict
  intersection), computed **on the wrapper** (only it knows both children) and appended to
  each `*_sides` tuple. Asymmetric examples: `massage_sides=('left',)` when only left has
  massage; `head_sides=('left',)` but `back_sides=('left','right','both')` for a 3-vs-2
  motor pair.
- **Covers vs buttons**: per-side covers keep honest per-side feedback. There is **no
  combined cover** (honors the non-goal). Combined motion is `_both` momentary up/down
  **buttons** (`back_up_both`) plus the existing stop — a button has no position/state to
  synthesize.
- **Naming** fixes #327 directly: "Head Up Left", "Head Up Right", "Head Up **Both**"
  where Both means both **sides**, not both motors. Strings in `strings.json` + `nb.json`.
- **Availability** stays always-`True`; a down side shows `unknown`. A dedicated per-side
  BLE-connectivity binary sensor names which side dropped.

### 6.3 Service routing
Add `vol.Optional(side, default=SIDE_BOTH)` to `goto_preset`, `save_preset`, `stop_all`,
`set_position`, `timed_move` + `services.yaml` Left/Right/Both selectors. `default="both"`
is the **complete back-compat mechanism**:
- legacy automation, no `side` → `both`;
- on a **non-paired** device that means today's single controller (no behavior change);
- on a **paired** device it fans out (what the user previously did with two device calls).

A module-level `_resolve_targets(call) -> (coordinator, side)` helper:
- keeps one entry → one coordinator (`_get_coordinator_from_device` untouched);
- raises a friendly `ServiceValidationError` (`side_not_supported`) when `side=left/right`
  hits a non-paired bed: "This bed is a single bed; the Left/Right/Both option only applies
  to paired beds."
- pre-flight validates **all** targeted sides before commanding any (preset slot count,
  per-side angle-sensing, motor presence); on `both` partial failure reuses the
  coordinator's STOP-the-other contract.
- `run_diagnostics` / `generate_support_bundle` are inherently single-address: they do
  **not** gain a `side` field and must resolve a paired target to an explicit child
  address (default to the primary/left side).

---

## 7. Frontend (Lovelace card) — deferrable to Phase 2

Per-side entities render *ungrouped* even with no card change, so this can ship later.

- **`discovery.ts`**: add an optional `sides:{left,right}` dimension to `BedEntities`; flat
  buckets stay canonical for single/combined. Strip the trailing `_left`/`_right` token
  **first** (a trivial `endsWith` `splitSide()`), *before* the `sleep_number_setting`
  startsWith, the `/^(.+)_(up|down)$/` regex, and `/thermal|footwarming|foundation/`. A
  single (non-paired) bed yields `side=undefined` for every key → `bed.sides` stays
  `undefined` → byte-identical existing behavior. `_collectWatched` recurses into
  `bed.sides.left/right`; the editor's `presentSections` ORs presence across
  `bed`/`bed.sides.left`/`bed.sides.right`.
- **Card layout**: a **Left / Both / Right segmented toggle** in the header (`role=tablist`,
  `aria-selected`, arrow-key nav, theme focus ring), **Both** default, **one side rendered
  at a time**. Rationale: HA dashboards are phone-dominant and beds are operated in the
  dark, half-asleep — one side at a time keeps every control full-width and large-hit-area;
  columns shrink touch targets, tabs demote "both". The selected side is transient `@state`
  (optionally seeded by `config.default_side`), never persisted per tap. An empty side
  segment is hidden (degrade to 2 segments). The toggle does **not** render on single beds.
- **The card NEVER fakes `both` by firing two per-side service calls** — combined controls
  appear only when the integration exposes a real combined entity. Fan-out, serialization,
  and partial-failure-stop belong to the coordinator.
- **Graphic**: Both renders two stacked compact silhouettes (L/R labelled); each side tab
  renders that side's silhouette; single-address combined-angle renders one as today.
  Graphic is decorative (`aria-hidden`).
- `bun run check` + `bun test`, rebuild & **commit** `frontend/dist/adjustable-bed-card.js`;
  mirror en/nb.

---

## 8. Edge-case register

### Connection / command safety
- **`both` move, right write throws after left started** → right marked started at coroutine
  creation; `gather(return_exceptions)` detects it; STOP fanned to **both** children (fresh
  cancel event each); aggregated `both_action_partial_failure` raised after stops settle.
- **`stop_all` with one child disconnected or its stop raising** → await both, swallow
  per-side exceptions individually so the reachable side always stops; aggregate after.
  Closes the gap where the current `handle_stop_all` can skip a side.
- **Two-device pair on one ESP32 proxy, no spare slot** → second connect raises a slot
  error; flip `_concurrent_ok=False`, fall back to sequential active-switching; one-time
  repair hint to add a second proxy for true simultaneous `both`. (Independent devices
  normally run concurrent; this is the degraded path — and Octo's default path.)
- **Two-device pair joined by a sync cable** (commanding one already moves both, e.g. the
  maintainer's bench bed) → not a technical failure but a UX trap: the wizard warns pairing
  will double-drive and recommends keeping a single entry; no auto-detection (the cable is
  invisible to BLE).
- **Parked side auto-reconnect stealing the active slot** → `async_disconnect("pair_switch")`
  sets `_intentional_disconnect`; existing logic suppresses reconnect.
- **PIN keepalive starved by a long `both`** → never hold a child lock across the keepalive
  window; sequential `both` releases between sides. Time-virtualized dual-harness test.
- **`stop_all` to a parked, disconnected side** → that child returns cleanly if it can't
  connect (`coordinator.py:2434-2436`); a parked side isn't moving, so the missed STOP is a
  safety no-op, not a correctness gap.
- **HA restart, one side unreachable** → parent setup succeeds; entities eager from
  snapshot; reachable side works; other shows `unknown`; no `SETUP_RETRY`.

### Capability / asymmetry
- **Left has massage, right doesn't** → `massage_sides=('left',)`, no `_right`/`_both`;
  per-side feature still exposed on the capable side (not AND-hidden).
- **3-motor vs 2-motor pair** → per-motor `*_sides`; `head` only on the side that has it;
  shared motors get full per-side + both; pre-flight catches a motor absent on a target.
- **Octo Star2 paired with standard Octo** (Star2 lacks PIN/synchro/lights/explicit stop) →
  intersection hides combined lights/synchro; per-side reflects each child; Star2 STOP uses
  its own degraded path. **Allowed** (same family) with reduced-capability marking.
- **`goto_preset side=both`, left has slot 5, right only 4** → pre-flight validates
  `preset <= memory_slot_count_for_side` for both → `ServiceValidationError` before left
  moves.
- **`set_position side=both`, left angle-sensing on, right off** → pre-flight
  `position_feedback_not_supported` naming the side before any command.

### Data model / migration / discovery
- **v4 migration runs for ALL entries** → strict no-op for non-paired (version stamp only);
  parametrized byte-identity test across bed types. **(Critical — a defect here bricks
  every user, not just paired ones.)**
- **Convert two singles → pair without orphaning** → re-home child devices to the parent
  *before* removing old entries; entities follow with unchanged `{MAC}_{key}` ids.
- **Conversion fails partway** (parent created, old not yet removed) → synthetic unique_id
  guard prevents duplicate-on-retry; surface a "Pairing half-finished" repair with retry/
  undo; old entries stay functional until removed (never bricked).
- **Conversion deletes the entry whose own options flow is running** → defer removal until
  after the flow returns.
- **Re-discovery of an absorbed member MAC** (push or picker) → extend
  `_configured_entries_by_address` (`config_flow.py:372-379`) to index child descriptor
  addresses; `async_step_bluetooth` adds an explicit early `already_configured` abort for
  member MACs (their entry unique_id is `pair_…`, so the MAC-based abort wouldn't catch
  them).
- **Runtime `bed_type`/angle correction on a paired entry** (`coordinator.py:427-432`) → a
  central `update_child_descriptor(entry, side, patch)` helper patches the correct
  descriptor in-place, never a flat top-level key.
- **`>2` same-name siblings** (two beds in one room) → suppress auto-fill; force an explicit
  two-device picker ("We found {n} devices named {name}. Choose which two make up this
  bed.").
- **Adapter only reaches one side** → per-side adapter fields; verify failure on the
  unreachable side suggests moving/assigning a proxy; "Pair anyway" allowed.
- **One side unreachable during pairing** → verify shows ❌; "Pair anyway" (offline child
  enters per-side retry, entities present with `unknown` state) or "Retry". PIN/caps for the
  offline side fall back to defaults until it connects.
- **Mismatched motor layouts** (explicit non-goal) → **block** at verify: "These beds have
  different motor setups ({n_a} vs {n_b} motors), so they can't be paired yet."
- **Cross-brand / mismatched bed types** → block unless same family + shared combined caps.
- **Mismatched lifecycle policy** (one disconnect-after-command, one persistent) → forbid
  the pair in Phase 1 to avoid reconnect-storm asymmetry; Octo pairs are symmetric.
- **User cancels mid-wizard** → flow-local state, nothing created/reserved; probe always
  disconnects (no lingering connection). Conversion creates/removes nothing until final
  confirm.
- **Downgrade after creating v4 paired entries** → old code rejects `version>3`; documented
  as expected (standard for schema bumps); pairing requires the new version.

### Frontend
- **Greedy `_up/_down` vs side suffix (`back_up_left`)** → side stripped first → base
  `back_up` matches existing regex; new `discovery.test.ts` case asserts
  `back_up_left → (side=left, motor=back, dir=up)`.
- **`sleep_number_setting_left` previously swallowed into flat firmness** → after the
  refactor it routes into `bed.sides.left.firmness`; the existing
  `discovery.test.ts:132-144` assertion is rewritten to expect per-side placement (no entity
  recreation — keys unchanged).
- **A capability exists only per-side, no combined entity** → the Both segment omits that
  control (no client-side fan-out); user picks Left/Right.
- **A side fully empty** (MCR no articulation, or offline at setup) → that segment is hidden
  (degrade to 2 segments); never land on a blank side.
- **Single bed** → no key carries a suffix → `bed.sides` undefined → toggle not rendered →
  byte-identical to today; existing `discovery.test.ts` passes unchanged.

---

## 9. Testing strategy

- **`RecordingChildCoordinator` doubles** that log an ordered `(side, method, args)`
  interaction trail and **raise where instructed** (instead of silently returning the
  asserted value). Tests assert on the *interaction log* — e.g. both STOPs attempted even
  when one raises — to dodge the **self-fulfilling-mock trap** (repo memory, MCR/#322).
- **Asymmetric capability mocks** so a wrongly-appearing `_both` entity is caught.
- **Partial-failure routing test**: simulate a right-side write failure, assert left
  receives STOP via the ordered log.
- **Time-virtualized dual harness** for PIN-keepalive-not-starved during a long sequential
  `both`.
- **Parametrized migration test**: every representative bed_type, v3→v4 byte-identical.
- **Config-flow wizard tests**: sibling offer, same-MAC guard, `>2` siblings picker, offline
  side "pair anyway", conversion device re-home ordering, deferred removal, unpair restore.
- **Member-MAC re-discovery** pushes a member MAC and asserts `already_configured` abort.
- **Capability-delegation test**: enumerate every base capability property; assert the
  wrapper overrides/delegates each.
- **Wire-identity regression** (Phase 3): assert SBI/Rondure/CB24/Sleep Number default
  packets are unchanged for existing single entries.
- **`discovery.test.ts`**: full existing suite passes unchanged; new `back_up_left` and
  per-side firmness/climate routing cases.

---

## 10. Phasing

### Phase 0 — Schema & migration scaffolding (ships invisibly)
De-risk the brick-everyone migration in isolation.
- Bump `VERSION 3→4`; guard `>3`→`>4`; v3→v4 no-op branch when `CONF_PAIR_ID` absent.
- Add all `CONF_PAIR_*`, `PAIR_MODE_*`, `SIDE_*` constants.
- `ChildDescriptor` shape + `update_child_descriptor(entry, side, patch)` helper.
- Extend `_configured_entries_by_address` to index `CONF_PAIR_MEMBER_ADDRESSES`.
- `async_setup_entry` dormant branch on `CONF_PAIR_ID`.
- **Files**: `config_flow.py`, `__init__.py`, `const.py`, `tests/test_init.py`.
- **Exit**: full suite green; parametrized byte-identical migration test; no user-visible
  change; no paired entry creatable yet.

### Phase 1 — Generic independent two-device pairing (Linak-validated; headline; ships independently)
The common separate-address case: two ordinary independent BLE devices (Linak and most
split-kings without a sync cable). No PIN, no keepalive, no active-connection switching —
each side is a normal link, so the wrapper mostly orchestrates two already-working
coordinators. Validate end-to-end on the maintainer's live two-Linak bench bed.
- `PairedBedCoordinator` over two children; `side` arg; `pair_connection_mode`
  (**`auto` default — concurrent-first**, fall back to sequential only on real proxy-slot
  exhaustion); two-phase `both` with pre-flight + STOP-the-other; resilient `stop_all`;
  half-available setup; eager parent device.
- **Bed-type-generic** pairing wizard (`_find_pairing_siblings` = two discovered same-type
  devices; discovery offer; select/assign/per-side adapter/verify/confirm); per-side +
  `_both` entities (covers, buttons, presets, stop, per-side connectivity sensors) from the
  snapshot.
- **Basic opt-in conversion** of two existing standalone entries into one pair — the
  *primary on-ramp* for Linak/most users, who already have two entries today (re-home child
  devices first, defer removal).
- `side` field (default both) on the five motion services + selectors; `_resolve_targets`;
  non-paired + side=left/right → `ServiceValidationError`.
- **Files**: `coordinator.py`, `__init__.py`, `config_flow.py`, `const.py`,
  `controller_factory.py`, `beds/base.py`, `beds/linak.py`, `button.py`, `cover.py`,
  `binary_sensor.py`, `switch.py`, `services.yaml`, `strings.json`,
  `translations/{en,nb}.json`, `tests/{conftest,test_coordinator,test_config_flow,
  test_linak,test_init}.py`.
- **Exit**: two independent same-type devices (validated on the real two-Linak bench bed)
  addable as ONE paired device from a single wizard — and two existing standalone entries
  convertible — with left/right/both; `both` partial failure stops the healthy side + one
  clean translated error (asserted via ordered log even when a stop raises); both sides
  driven concurrently when two slots exist; half-available restart works; existing single
  entries byte-identical.

### Phase 2 — Octo active-connection-switching profile + frontend card
Layer Octo's hard quirks onto the proven Phase-1 core, and ship the card. This is the direct
#327 fix.
- Octo connection profile: `sequential` active-connection switching (one side active at a
  time), per-side PIN, 25 s keepalive, parked-side `_intentional_disconnect`; the parent
  never holds a child lock across the keepalive window. Octo-specific `_both`
  lights/synchro.
- Unpair/revert with a shared `_async_remove_paired_entities` reverse helper.
- `discovery.ts` side-suffix parsing; Left/Both/Right card toggle; per-side graphic;
  editor; en/nb; rebuilt+committed dist.
- **Files**: `coordinator.py`, `config_flow.py`, `beds/octo.py`, `__init__.py`,
  `climate.py`, `number.py`, `select.py`, `binary_sensor.py`, `cover.py`, `button.py`,
  `frontend/src/{discovery,types,adjustable-bed-card,bed-graphic,editor}.ts`,
  `frontend/src/translations/{en,nb}.json`, `frontend/src/discovery.test.ts`,
  `frontend/dist/adjustable-bed-card.js`, `tests/test_octo.py`.
- **Exit**: a separate-address Octo split bed works as ONE paired device (fixing #327), with
  sequential switching not starving the keepalive during a long `both` (time-virtualized
  test); unpair restores two standalone beds losslessly; full `discovery.test.ts` passes
  unchanged + new cases; card renders Left/Both/Right; single beds byte-identical; dist
  committed.

### Phase 3 — Generalize to single-address side-aware protocols
- Lift construction-time side baking to per-call args (`sbi._build_command(value, side)`,
  `rondure._build_packet(value, side)`, `okin_cb24.build_cb24_command(value, side)`,
  `sleep_number` bamkey side arg, Kaidi Seat 1/2 command profiles) — default behavior
  byte-identical.
- single_address `PairedBedCoordinator` realization (native-both packet or serialized
  left-then-right); generalize `*_sides`/`*_for_side` to articulation/presets/lights/
  massage; surface CB24 A/B & SBI/Rondure variants in wizard/options; `_delegated_capability`
  base helper.
- **Files**: `coordinator.py`, `controller_factory.py`, `beds/base.py`,
  `beds/{sbi,rondure,okin_cb24,sleep_number,kaidi}.py`, `config_flow.py`, `validators.py`,
  `cover.py`, `button.py`, `number.py`, `tests/{test_entities,test_config_flow}.py`.
- **Exit**: SBI/Rondure/CB24/Sleep Number/Kaidi Seat 1+2 present left/right/both
  consistently with Octo;
  existing single entries byte-identical on the wire (regression-asserted); capability-
  delegation test passes; NEW-protocol CB24 cleanly refused for paired mode.

#### Phase 3 controller audit

- Kaidi `seat_1_2` belongs here: one mesh-over-GATT address carries independently
  addressable Seat 1 and Seat 2 opcodes, and its existing combined mode serializes both.
  Single-seat variants remain ineligible.
- Sleep Number MCR already exposes left/right firmness and foundation selects from one
  standalone entry. It has no verified live articulation or STOP surface, so converting it
  would duplicate those existing entities without adding the Phase 3 control contract.
- BedTech has APK-backed secondary-head, preset, memory, and light opcodes, but not a
  verified symmetric second-base motor layout. Its current motor labels are also awaiting
  a separate verification pass. It must not advertise a full left/right/both bed surface
  until that compatibility contract is known.
- Jiecang's right/split constants are unused and undocumented at the controller surface.
  SUTA, MotoSleep, and Richmat expose controller-to-controller sync toggles, not two
  independently addressable sides on one BLE link. Cool Base left/right means fan zones.

---

## 11. Top risks

| Sev | Risk | Mitigation |
|-----|------|-----------|
| **critical** | v4 migration runs for ALL entries; a defect bricks every bed, not just paired. | Strict version-stamp no-op for non-paired; ship as isolated Phase 0; parametrized byte-identity test across bed types. |
| high | separate_address conversion removes old child entries before re-homing their devices → GC orphans every per-side entity + history. | Strict unit-tested ordering: add parent `config_entry_id` + `via_device` FIRST, defer `async_remove` until after the flow returns. |
| high | `both` partial failure leaves a motor running because the STOP fan-out itself fails fast. | Pre-flight validate all sides; `gather(return_exceptions)` on the STOP cleanup with a fresh cancel event per child; ordered-log test. |
| high *(Octo, Phase 2)* | Octo firmware/single-adapter slot budget forces one active connection; assuming concurrent makes both fail. | Give Octo a `sequential` switching profile (the generic default stays `auto`/concurrent for independent pairs); per-side adapter; verify on real Octo HW before allowing concurrent for Octo. |
| medium | Octo PIN keepalive (25 s) starved by a long `both` holding a child lock → side drops ~30 s. | Never hold a child lock across the keepalive window; interleave sequential `both` per sub-command; time-virtualized test. |
| medium | A disconnected side empties its live capability tuple → entity churn breaks history/dashboards. | Drive per-side creation + both-intersection from the persisted snapshot; down side shows `unknown`, availability stays True. |
| medium | Frontend mis-parses the side suffix (greedy regex runs first) → invisible/phantom entities. | Side-as-trailing-token; strip first; existing `discovery.test.ts` must pass unchanged + new cases; defer card to Phase 2. |
| medium | Member-MAC re-discovery creates duplicate standalone entries (pair_id, not MAC, is unique_id). | Record member MACs; index them in `_configured_entries_by_address`; explicit `already_configured` abort in `async_step_bluetooth`. |
| medium | Stacking the separate-address parent on single-address side-aware beds double-controls. | Implement Class A purely at the controller/entity layer (per-call side arg); never route Class A through fan-out. |

---

## 12. Decisions — all accepted (2026-06-20)

All six recommendations below were **accepted** by the maintainer and are now locked decisions
(the *Matters*/*Finding* notes are kept for rationale). Two are Octo-specific (Phase 2); none
block Phase 1.

1. **Octo only:** does Octo's firmware force one active connection at a time even when two
   proxy slots are free, or can two Octo links run concurrently like ordinary two-device
   pairs?
   *Matters:* the generic default is already settled — independent two-device pairs (Linak
   et al.) run **concurrent / `auto`**. This question is narrowly whether Octo needs the
   `sequential` switching profile, which drives Phase-2 Octo wizard copy (~1 min sequential
   probe) and whether Octo `both` is ever near-simultaneous. **Does not affect Phase 1.**
   *Decision — accepted:* give Octo a `sequential` profile by default and verify on real
   two-address Octo hardware (single- *and* two-proxy) before allowing concurrent for Octo.

2. **For single_address pairs, should the entry unique_id migrate MAC → `pair_<id>`, or
   stay MAC with `pair_id` only in `entry.data`?**
   *Matters:* migrating frees the MAC namespace but risks any code keying off
   `entry.unique_id == address` (config-flow aborts, `repairs.py`).
   *Decision — accepted:* **keep the MAC** as unique_id, store `pair_id` only in `entry.data`,
   unless an audit of all `unique_id == address` assumptions proves migration safe. Reserve
   member MACs in `CONF_PAIR_MEMBER_ADDRESSES` regardless.

3. **Should the pre-existing non-sided entity *become* the `both` control, or should
   pairing always create a distinct `_both` entity (removing the non-sided one)?**
   *Matters:* the Sleep Number pattern *deletes* the non-sided entity when sides appear;
   reusing it as `both` preserves its history. Affects the unpair reverse-cleanup path and
   freezes the frontend suffix convention.
   *Decision — accepted:* **reuse** the non-sided key as `both` for stop & synchro (already
   pair-level semantics), but emit explicit `_both` keys for motors/presets/lights/massage.
   Lock this in Phase 1 so the suffix convention is frozen before Phase 2.

4. **Must Phase 2 hard-require symmetric `bed_type`/variant for an Octo pair, or tolerate
   asymmetric (e.g. Standard + Star2) from the start?**
   *Matters:* affects lifecycle-policy matching, capability intersection, degraded-action
   surfacing. Star2 lacks PIN/synchro/lights/explicit stop.
   *Decision — accepted:* require same family (both Octo) and same lifecycle policy; **allow
   Standard+Star2** with capability intersection hiding missing features; **block**
   cross-brand and mismatched motor layouts at the wizard.

5. **Is reverse migration (paired → single) a first-release requirement?**
   *Matters:* #329 frames migration as opt-in/reversible; without a reverse cleanup, unpair
   orphans `_left`/`_right`/`_both` entities.
   *Decision — accepted:* **ship unpair in Phase 2** alongside conversion via a shared
   `_async_remove_paired_entities` reverse helper — it's the trust mechanism that makes
   users comfortable pairing, and it reuses the conversion device-re-home path.

6. **Is `run_diagnostics` in scope for the `side` field?** *(resolved during planning)*
   *Finding:* `run_diagnostics` is **not a registered HA service** — it's an internal method
   (`ble_diagnostics.py:206`) wrapped by the `generate_support_bundle` service. The only
   registered services are the five motion ones + `generate_support_bundle`
   (`__init__.py:626/638/650/900/1022/1165`, `services.yaml`). (The AGENTS.md services table
   still lists `run_diagnostics` — stale.)
   *Decision — accepted:* only the five motion services get the `side` field;
   `generate_support_bundle` does **not**, and resolves a paired target to an explicit child
   address (default primary/left). Nothing further to locate.

---

## Appendix — key file:line anchors (verified at planning time)

- `config_flow.py:178` — `VERSION = 3`
- `__init__.py:133-177` — `async_migrate_entry`; guard `entry.version > 3` at `:142`
- `config_flow.py:448-449, 922-923, 1147-1148, 1463-1464` — `async_set_unique_id(address)` +
  `_abort_if_unique_id_configured`
- `config_flow.py:274-327` — `_get_octo_split_setup_note` (current passive split note)
- `config_flow.py:372-379` — `_configured_entries_by_address`
- `coordinator.py:186-348` — coordinator reads all config from `entry.data`
- `coordinator.py:470-484` — only place `entry.options` is read (`back/legs_max_angle`)
- `coordinator.py:798-805` — `device_info` (`identifiers={(DOMAIN, self._address)}`)
- `coordinator.py:427-432` — runtime `bed_type`/angle-sensing correction (in-place mutation)
- `coordinator.py:2428-2436` — never-early-return `async_stop_command`
- `entity.py:13-32` — base entity, `_attr_has_entity_name`, always-available
- `__init__.py:452-464` — `_get_coordinator_from_device` (one device → one coordinator)
- `beds/sleep_number.py:345-401, 513-604` — `*_sides` tuples + `_require_side(side)` dispatch
- `beds/okin_cb24.py:193-218` — CB24 NEW-protocol builders (no side byte)
- `docs/beds/octo.md:60` — Octo "separate addresses and switching between them"; `Back +
  Legs Up` per-side caveat
- `frontend/src/discovery.ts:127, 149, 171` — `sleep_number_setting` / greedy `_up/_down` /
  `thermal|footwarming|foundation` matchers (side suffix must be stripped before all three)
