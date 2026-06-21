"""Tests for ChildEntryView — the per-side config proxy used by paired children."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.adjustable_bed.coordinator import ChildEntryView


def test_serves_child_data_and_delegates_to_parent():
    parent = SimpleNamespace(
        entry_id="parent-id", title="Master Bed", options={}, version=4
    )
    view = ChildEntryView(parent, {"address": "AA:BB", "side": "left"}, lambda _d: None)

    # .data is the per-side child config, not the parent's data.
    assert view.data == {"address": "AA:BB", "side": "left"}
    # Everything else proxies to the real parent entry.
    assert view.entry_id == "parent-id"
    assert view.title == "Master Bed"
    assert view.version == 4
    # options come from the parent.
    assert view.options == {}


def test_parent_option_edits_win_over_descriptor():
    # Editing the paired bed's options must reach the child, overriding the
    # frozen per-side descriptor for shared keys while keeping identity.
    parent = SimpleNamespace(
        entry_id="parent-id", options={"motor_pulse_count": 15}, version=4
    )
    view = ChildEntryView(
        parent,
        {"address": "AA:BB", "side": "left", "motor_pulse_count": 10},
        lambda _d: None,
    )
    assert view.data == {
        "address": "AA:BB",
        "side": "left",
        "motor_pulse_count": 15,
    }


def test_persist_updates_view_in_place_and_routes_to_callback():
    parent = SimpleNamespace(entry_id="parent-id", options={})
    routed: list[dict] = []
    view = ChildEntryView(parent, {"a": 1}, routed.append)

    view.persist_data({"a": 2, "b": 3})

    # The view now reflects the new config (so subsequent reads see it)...
    assert view.data == {"a": 2, "b": 3}
    # ...and the change was routed to the parent-descriptor callback.
    assert routed == [{"a": 2, "b": 3}]


def test_data_is_isolated_copy():
    parent = SimpleNamespace(entry_id="p", options={})
    source = {"a": 1}
    view = ChildEntryView(parent, source, lambda _d: None)
    source["a"] = 99  # mutating the original must not bleed into the view
    assert view.data == {"a": 1}
