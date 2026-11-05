# Guided setup changes

Issue #676 unifies setup around one question: which app or remote controls
this bed. An existing entry moves to another app or layout only through a
staged, explained and confirmed change. This note records the shared
transaction and the rules every family journey follows. It contains no
protocol values.

## The transaction

`profile_migration.py` holds the shared parts; each family supplies only its
own questions and checks.

1. **Snapshot.** Reconfigure copies the saved data and options
   (`MigrationSnapshot`). Every later step works on a staged copy.
2. **Choose.** The family's step asks for the app, then the layout or remote
   the app shows. Choosing a different app clears the previous app's profile
   metadata; keeping the same app keeps it.
3. **Verify.** A family with exact endpoint or bond requirements
   (`ManagedFamily.requires_check`) must pass a connection check. The old
   runtime's transport is reserved under its normal locks for the check. A
   link that cannot be observed closed fails the check and stays owned until
   it closes, so no second connection overlaps it. The check has its own
   progress steps (`migration_check`, or `migration_pairing` for a family
   that pairs), whose checklist says nothing is saved yet. A failed check
   goes to `migration_check_failed`, never to setup's `verify_connection`,
   whose "finish setup" wording would be wrong here; a passed check goes
   straight to the review.
4. **Review.** `async_control_changes` compares the entity set of the running
   route with the entity set the staged route declares offline, and names the
   automations and scripts that use a removed entity. Unique IDs are
   address-based, so a kept control keeps its entity ID and history. A kept
   entity whose name differs between the two sets is reinterpreted: it now
   stands for another control. A behavior change behind an unchanged name is
   not visible in the entity sets, so the review cannot list it. Listing the
   staged controls builds entities without saving the route and ignores every
   registry write meanwhile.
5. **Confirm.** Apply and Keep are equal answers. Saving happens only against
   an unchanged snapshot, and ends on `migration_applied`, which names the new
   setup, the previous one and the way back.

Keep, cancel, a failed check or a concurrent edit leave the saved entry
unchanged and usable. An answer that resolves to the saved route (a label
change) aborts without a check or a save.

Families reuse the transaction, never another family's protocol checks.
Vibradorm's role checks and native bond rules stay Vibradorm's.

## Entry points

- **Reconfigure** opens the wizard for a family registered in
  `MANAGED_FAMILIES`. A family also names, in `asks_for`, the routes of other
  bed types its question chooses that have no guided change of their own
  (Okin CST for Okin; the legacy L&P app and the L&P app's QRRM remote for
  L&P), so an entry on one can reach the family's other routes. Configure
  keeps changing their own settings, and Repairs keeps its usual path for
  them, since the question may not offer what a review suggests.
- **Configure** shows one generic **Change app or layout** item for those
  families. Home Assistant cannot hand an options flow to a config flow, so
  the item points to Reconfigure.
- **Repairs** opens the wizard as its next flow, or Configure's settings form
  with the app selected for an app that needs its own settings. A suggested
  app from another guided family, such as the LOGICDATA app for a Comfort
  Motion bed, is one more answer of the wizard's first question; it continues
  in that family's questions and runs that family's check.

## Repairs and Keep

A review completes only after a saved change of bed type or variant, or an
explicit Keep. Acknowledging instructions or closing a handed-off flow leaves
it pending. Keep is stored with the route signature and the apps shown
(`CONF_PROFILE_REVIEW_KEPT`). The review returns for that route only when a
later release offers it an app the user was not shown. In a fresh setup, Keep
saves the detected route; in Configure and Repairs it leaves the entry
untouched.

## Paired beds

An app belongs to one physical bed, so the wizard splits a pair first.
`standalone_config_after_split` restores each side's original configuration
except the connection preferences in `SPLIT_RETAINED_KEYS` (adapter, idle
disconnect, disconnect after each command), which keep the value the side used
while combined. Bed type, app profile and side settings revert to the
originals. An open review, or an earlier Keep, carries over to each standalone
bed.

## Connection check is not physical validation

A passed check proves only that the chosen endpoints exist and any required
bond holds. It does not prove the physical layout, preset meaning or movement.
The confirm step says so. Physical validation by affected users after a beta or
release is recorded per family below, separately from the code change.

| Family | Guided change | Connection check | Physical validation |
|--------|---------------|------------------|---------------------|
| Vibradorm, VMAT, Caresse Diamant, Werkmeister, V-MAT Basic | Yes | Endpoint roles, VMAT native bond | Pending user reports after release |
| Customatic Clarity, Jerome's C, Remedy | Yes | The one command characteristic | Pending user reports after release |
| Customatic Z-Series, Jordan's Serenity and Tranquil | Yes | The command and notification characteristics | Pending user reports after release |
| Jensen Adjustable Sleep (JMC400, LinOn), Svane Remote (Svane Bed, JMC400) | Yes | None: the controllers resolve their roles when they write and never refuse a link | Pending user reports after release |
| Malouf Base and Lucid Base apps, Nordic UART and FFE5 receivers | Yes | The app's transport, chosen as the runtime chooses it; the receiver routes need none, since they correct each other from the services | Pending user reports after release |
| Limoss Remote and FSM Relax apps, Stawett / older Limoss controls | Yes | Limoss Remote's service and notifying command characteristic; leaving its enabled light or massage first sends the app's OFF commands | Pending user reports after release |
| Sleepy's Elite app, BOX15, BOX24, BOX25 | Yes | The control box's setup and response characteristics; each receiver route's command characteristic | Pending user reports after release |
| LOGICDATA SimplicityFrame (SILVERmotion), MOTIONrelax phone and tablet, Sleep Smart bed base | Yes | SimplicityFrame's command characteristic after its bond; each app's selected transport | Pending user reports after release |
