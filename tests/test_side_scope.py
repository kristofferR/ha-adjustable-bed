"""Side binding for controllers shared by single-address paired sides."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.entity_runtime import controller_side_scope, own_sides


def _controller() -> BedController:
    stubs: dict[str, object] = {
        name: lambda self, *args: None for name in BedController.__abstractmethods__
    }
    stubs["control_characteristic_uuid"] = property(lambda self: "")
    return type("StubController", (BedController,), stubs)(MagicMock())


def test_side_scope_binds_nests_and_restores() -> None:
    controller = _controller()
    with controller.side_scope("left"):
        assert controller.command_side == "left"
        with controller.side_scope("right"):
            assert controller.command_side == "right"
        with controller.side_scope(None):
            assert controller.command_side == "left"
    assert controller.command_side is None


def test_runtime_scope_binds_live_and_capability_controllers() -> None:
    live, offline = _controller(), _controller()
    runtime = SimpleNamespace(controller=live, capability_controller=offline, controller_side="right")
    with controller_side_scope(runtime):  # type: ignore[arg-type]
        assert (live.command_side, offline.command_side) == ("right", "right")
    assert (live.command_side, offline.command_side) == (None, None)

    standalone = SimpleNamespace(controller=live, capability_controller=live, controller_side=None)
    with controller_side_scope(standalone):  # type: ignore[arg-type]
        assert live.command_side is None


def test_own_sides_keeps_only_the_bound_side() -> None:
    sides = ("left", "right")
    assert own_sides(SimpleNamespace(controller_side=None), sides) == sides  # type: ignore[arg-type]
    assert own_sides(SimpleNamespace(controller_side="left"), sides) == ("left",)  # type: ignore[arg-type]
    assert own_sides(SimpleNamespace(controller_side="both"), sides) == ()  # type: ignore[arg-type]


def test_action_button_availability_reads_its_own_side() -> None:
    """Home Assistant reads availability outside state writes."""
    from custom_components.adjustable_bed.beds.entity_specs import ControllerButtonSpec
    from custom_components.adjustable_bed.button import ControllerActionButton

    controller = _controller()
    type(controller).controller_button_available = (  # type: ignore[method-assign]
        lambda self, key: self.command_side == "right"
    )
    runtime = MagicMock(controller=controller, capability_controller=controller)
    runtime.controller_side = "right"
    runtime.entity_side = "right"
    button = ControllerActionButton(runtime, ControllerButtonSpec("act", "Act", MagicMock()))
    assert button.available
    runtime.controller_side = "left"
    assert not button.available
