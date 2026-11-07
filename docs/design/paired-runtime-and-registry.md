# Paired runtimes and registry ownership

Ref #525, #523 and #524. These boundaries preserve the existing pairing model and
command behavior; same-device concurrency remains separate work (#516).

## Topology strategies

`PairedBedCoordinator` is the public facade. It resolves the side, captures
pair ownership, preempts overlapping work, and hands the command to one strategy
in `paired_topology.py`. Each strategy owns target admission, locking,
prepare/commit, connection switching and its STOP fan-out:

| Strategy | Pair | Behavior |
| --- | --- | --- |
| `ConcurrentTwoLinkTopology` | Two addresses, concurrent or automatic mode | One lane per side. Linked groups reserve every scheduler before any side starts and stop every started side on failure. Automatic mode adopts sequential switching after proven adapter-slot exhaustion. |
| `SequentialTwoLinkTopology` | Two addresses, sequential mode | One link lane. Each side connects, runs and disconnects before the next; STOP reaches only connected or ready local sides. |
| `SingleLinkSideAwareTopology` | One address | One lane per logical side. A native Both is one physical operation; otherwise the side frames run in turn and STOP cancels the shared scheduler once. |

A two-link pair holds both two-link strategies, and the current connection mode
selects one. `PairAdmission` holds the cancellation generations and the active
group for all strategies of a pair, so a command queued before automatic
fallback reroutes to the sequential strategy with the STOP ownership it
captured. Child coordinators keep their BLE clients, schedulers,
authentication, disconnect timers and protocol controllers.

`test_paired_topology_trace.py` records every GATT write, link change, call into
a physical coordinator and caller outcome under a virtual clock, for every
strategy (automatic mode included). Its fixture was recorded before the
extraction, so routing changes must reproduce it exactly.

## Entity runtimes

`entity_runtime.py` declares the identity, state, subscriptions, connection
operations, and movement operations consumed by the nine entity platforms.
`entity_runtimes()` constructs the standalone runtime or parent-routed side views
for every platform. Combined entities continue using the paired parent directly.

`PairedSideProxy` reads from its child and routes commands, seeks, and STOP through
the parent. `SingleAddressSideCoordinator` binds logical-side operations to the
shared physical link and retains its own position cache. Neither view forwards
arbitrary attribute access or assignment. Connection operations and queries retain
their existing child routing. Services use the explicit physical-or-logical child
union instead of pretending every view is a physical coordinator. Support capture
uses explicit diagnostic access on the logical view so both physical and logical
position polling remain paused throughout capture.

Side devices carry the side in their name, so no entity adds it to its translation
key. A two-address side keeps its own bed's name. A single-address side is named
`<bed> Left` or `<bed> Right` through the `device` translations, and Home Assistant
keeps a name the user set. Combined controls on the parent reuse the side's key;
the parent device's name keeps them apart. Only keys a bed states for a side it
controls natively, such as Sleep Number's per-side climate, end in `_left`,
`_right` or `_both`. The card reads an entity's side from its `bed_side` or `side`
attribute, never from its key.

`ChildEntryView` explicitly forwards identity and lifecycle methods to the real
parent `ConfigEntry`. Runtime persistence still updates only the matching child
descriptor; background tasks and unload callbacks belong to the real entry.
Coordinators accept the two supported entry forms directly, without a cast.
A single-address side shares the physical controller itself. The runtime binds
its side with `BedController.side_scope()` around commands, queries and state
reads, and `own_sides()` limits per-side capability lists to that side.

## Registry transactions

`paired_registry.py` owns conversion and unpair registry migration. Integration
setup still owns connection probing, controller creation, ordinary device
registration, and platform loading.

The ownership plan snapshots entity rows, original device owners and parent links
before mutation. It validates all transfer targets, moves entity owners before
device owners (as required by Home Assistant), and removes the source config entry
only after successful transfer. Unpair registers both restored entries while
disabled, transfers ownership, then enables them. A side that remains offline is
still a valid restored entry and retains HA's normal setup retries.

Temporary target devices created during paired setup keep their registry IDs until
commit. Their identifiers are temporarily detached to make room for the original
customized device. Deleting them earlier loses the ability to restore their IDs
on current Home Assistant. After source-entry removal commits the transfer, these
empty placeholders are retired.

Rollback restores entity owners before device owners, restores the exact original
parent links, and is safe to retry. A mutation that raises after changing state is
covered by the original snapshots. Rollback errors are logged individually and
never replace the triggering exception. If a row cannot be restored, its device
and owning entry are retained rather than deleted by later cleanup. Recovery can
then be retried without intentionally discarding user data.

Source config-entry removal is the commit point. If it raises after actually
removing the entry, ownership is kept with the surviving destination rather than
rolled back to a missing entry. Empty-placeholder cleanup after commit is
best-effort and reports failures. These are compensating transactions across HA
APIs, not crash-atomic database transactions.

Single-address unpair retains its in-place config restoration and paired-only
entity cleanup. Failures restoring its configuration or reloading it are reported
without hiding the original failure.

## Stale entity rows

Entity builders only build. Every platform records the unique IDs it creates in
`entity_sweep.py`, and once all forwarded platforms have set up, rows of the entry
that nothing created are removed. Disabled entities are created too, so they stay.
The sweep does nothing while any configured side is missing from the runtime, has
no capability controller, or has not finished entity discovery, so an offline or
retained side never loses the other side's rows. A controller lists entities that
appear only once the bed reports them in `retained_entity_keys`. A dynamic builder
that rebuilds after discovery replaces its own record and triggers the sweep again.

## Validation

`test_entity_runtime.py` covers every platform in all three runtime shapes,
identity conventions, state subscriptions, connection routing, and parent-owned
task lifetime, and support capture hydration ownership. Existing paired command
tests cover movement routing and STOP.

`test_paired_registry.py` injects failures before and after entry creation, entity
and device moves, entry enabling, and source removal. It also checks placeholder
identity recovery, pre-mutation validation, retryable rollback, and single-address
config restoration, including cancellation. Existing paired setup tests cover real HA registry adoption,
conversion, unpair, offline sides, and user customization preservation.

### Physical validation

Deferred for the v5 beta ([#783](https://github.com/kristofferR/ha-adjustable-bed/issues/783)).
Proven offline: `test_paired_topology_trace.py` reproduces, write for write, the
trace recorded before the strategies were extracted, for every strategy and for
automatic mode. Needs real-bed reports: two-address pairs in concurrent,
sequential and automatic mode, including automatic mode's switch to sequential
after a real adapter runs out of connection slots; a STOP that must reach both
sides; and single-address beds running a native Both. Reports through ESPHome
proxies with few free slots are the most useful.
