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

`ChildEntryView` explicitly forwards identity and lifecycle methods to the real
parent `ConfigEntry`. Runtime persistence still updates only the matching child
descriptor; background tasks and unload callbacks belong to the real entry.
Coordinators accept the two supported entry forms directly, without a cast.
The existing side-bound controller adapter remains a distinct controller type;
this change does not redesign the protocol controller interface.

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
