# Private Pairlink SDK receive consumers

The entry-owned central notification and verified local WriteValue paths feed
the same runtime reducer. Registered channel `0x20` continues to preempt SDK
parsing, including ignored or throwing app callbacks. Registration by itself
does not preempt when the internal MeshCallback is absent.

The private mode-zero dispatch entry reads the LE16 opcode only after two
remaining bytes are available. Address types 1/3 resolve the received virtual
address; types 2/4 resolve the received Bluetooth MAC. The source PacketSource
array is six bytes, so a virtual address retains two constructor-zero bytes in
the vendor callback. Type 3/4 UID bytes advance the cursor without becoming the
lookup address. Vendor opcodes use the unsigned threshold `0x8000`, retain the
signed short passed to the private callback, and return immediately. The app's
inherited vendor callback remains a no-op. No public arbitrary-packet action is
provided.

For grouped address kind 3 in modes 1 and 11, the parser copies the four-byte
address and advances six bytes, skipping the two-byte UID before dispatch.

The dispatcher also handles 8-bit group mode 1, 16-bit group mode 11,
channel-message mode 2, and nested one-/multi-command modes 3/4. Source addresses,
UID strides, signed channel/unit fields, per-target masks and duplicate group
IDs remain distinct. Nested target dispatch preserves source order, the
first-set-unit-bit rule, sensor-callback preemption, constructor address-buffer
limits and the source's specific zero-padded copy ranges. A failed first read
has no downstream effect; an earlier completed record is not rolled back when
a later record fails. Channel, sensor and key callbacks inherited as no-ops by
the actual app remain private no-ops, with their source callback gates.

For channel `0xff`, the ordinary app route's transient join-check getter is
source-initialized to zero. A complete 20-byte ping response learns or updates
the DeviceBean MAC/vAddr association from received bytes. MAC bytes use the
source's reversed wire order. The following status-8 callback is independent of
the ping helper's return, including a six-byte selector-only frame. The
callback's initial dashboard reads use the existing coordinator scheduler and
retain the physical receive generation. An absent internal callback suppresses
the queries. Detector behavior remains outside this implementation change;
the root's scope decisions do not introduce an ordinary app detector entry.

SDK full ping (opcode 3) and TLV ping (opcode 4) also produce DeviceBean
identity from received basic fields. Their status-8 callback follows a normally
returning parser, including a TLV parser with no complete basic record.
Malformed full-ping reads or truncated TLV copies do not reach that callback.
Mode-8 opcode 7 marks an existing matching MAC online and emits status 8
without replacing its vAddr or inventing a new DeviceBean.

A known-device `0x049b` event reads that DeviceBean's virtual address and samples
the local calendar and timezone separately. Mode zero produces a 13-byte
calendar payload with a zero-based month, Sunday-zero weekday, the Java
hour-offset mapping at byte 8, and four zeros at bytes 9–12. Unit zero maps to
mask 1; opcode `0x0492`, source kind 1, current source vAddr and profile channel
`0x20` form the private response. It uses the same current-key, signing,
encryption, central fragmentation or local peer-socket path as existing sends.
The public dashboard payload API still accepts exactly four bytes.

Central library status inputs 3, 4 and 6 project status 8 before ending the
failed session. HA maps those inputs from an incomplete discovered profile, a
failed notification subscription, and exhausted actual connection attempts.
They are lifecycle facts, not fabricated wire messages. Discovery absence,
other library status values, a different target, a local-host role, or a closed
runtime does not create this projection. Existing HA retries and send-readiness
gates remain in charge; the callback does not make an unready transport writable.

Unknown DeviceBeans do not inherit a transport MAC or a virtual address.
Disconnect, identity replacement, stale authentication, a changed target vAddr,
or a replaced controller prevents a queued response from using a newer route.

One entry runtime owns the canonical device list, metadata reducer, preference
adapter and receive lock across controller replacement. Full/TLV ping uses fresh
canonical beans and the exact forward-removal list algorithm, so adjacent
duplicates can survive replacement. FF ping updates only the first matching
bean. Metadata accessors expose the same beans and function lists, with no
second MAC catalog. Basic, legacy special-app and LP parsing retain their own
signed lengths, partial writes and callback boundaries. Every normal nonbasic
TLV goes through the supplied model parser; an inner failure prevents later
list/status completion. LP reports reach only the inherited private callback.

Composition opcode 0x0001 mutates known canonical units before adding an
unknown identity to AttributesManagement. Catalog persistence completes before
its status callback and queue continuation. Known identities return early.
Source catalog matching uses first-match and wildcard rules. Generic lighting
prediction, arithmetic and callbacks remain explicit source exclusions. Their
catalog support checks are evaluated at applicable unicast/group gates without
creating lighting entities. The disabled acquisition worker is never started by
ordinary receives.

The entry's Home Assistant Store uses an entry-ID key, with the physical child
address appended for two-address pairs so independent catalogs cannot overwrite
each other. Standalone storage keys remain unchanged. It uses the source preference
namespaces attributesManagement/list and pl_finger_print/<home-id>. Home IDs
use the source's lowercase, unseparated byte-order hex. Preference values are
immutable JSON snapshots with source Gson field names, including complete
canonical units, sensors, cadence, restore state and signed byte arrays.
Session keys, passwords, physical peer generations and transport objects never
cross that codec. An absent catalog loads the source defaults; JSON null loads
an empty catalog.

The fingerprint setting retains its source false default. Central CMD02's
eligible getter-zero branch can issue native 01 42 and use the existing
500 ms callback. A verified 02 42 response preserves timer cancellation,
match/miss state, canonical-reference restore, persistence and callback order.
List restoration binds its current physical receive owner even when the
callback is null. Ping completion saves only at the source count/state gates.
Exit saving precedes native/backend teardown; cleanup still runs after a
storage failure. Memory changes preceding a failed write remain visible.
Fingerprint and attribute callbacks use the existing HA loop with current
entry/peer checks. No scheduler or public setting/action is added.

Native packet reduction and SDK persistence execute in the same entry receive
lane, so a later native event cannot change keys while an earlier metadata
write is suspended. Physical teardown still invalidates queued work.

Hardware delivery remains unverified. Source scope and release adoption belong
to the integrating author. Root source overlays are separate from this receive
patch.
