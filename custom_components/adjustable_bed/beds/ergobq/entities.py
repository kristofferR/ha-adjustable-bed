"""Native controls for the fields ErgoBQ gives a proven meaning."""

from __future__ import annotations

from ...card import CARD_MASSAGE, CARD_MASSAGE_TIMER, motor_card
from ...codec import ergobq as codec
from ...profiles import ergobq as app
from ..base import require_controller
from ..catalog_buttons import Kind, catalog_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
)
from .controller import (
    CHILD_LOCK,
    DIY_REMAINING,
    FAULT_FLAGS,
    IDENTITY,
    LIGHT_REMAINING,
    MASSAGE_FIELDS,
    MASSAGE_MODE,
    MASSAGE_ON,
    MASSAGE_SYNC,
    MASSAGE_TIMER_OPTION,
    PARTNER_BROADCAST,
    PARTNER_CONNECTED,
    POSITIONS,
    SIDE,
    ErgoBQController,
)


def motor_specs(controller: ErgoBQController) -> tuple[MotorControlSpec, ...]:
    return tuple(
        MotorControlSpec(
            app.AXES[dp][0],
            f"ergobq_motor_{dp}",
            lambda c, dp=dp: require_controller(c, ErgoBQController)._move(dp, True),
            lambda c, dp=dp: require_controller(c, ErgoBQController)._move(dp, False),
            lambda c: c.stop_all(),
            scheduler_resource="motor:*",
            hold=ControllerMotorHoldSpec(f"{dp}_up", f"{dp}_down", stop_scope="side"),
        )
        for dp in controller.axes
    )


def buttons(_controller: ErgoBQController) -> tuple[ControllerButtonSpec, ...]:
    result = []
    for scene in app.SCENES:
        # Standard flat and local memories already have their own entities.
        if scene not in ("flat", "memory_1", "memory_2"):
            result.append(
                catalog_button(
                    f"ergobq_recall_{scene}",
                    scene.replace("_", " ").title(),
                    lambda c, scene=scene: require_controller(c, ErgoBQController).scene(scene),
                    kind=Kind.PRESET,
                )
            )
        for operation, label in ((7, "Save"), (8, "Restore default")):
            result.append(
                catalog_button(
                    f"ergobq_scene_{operation}_{scene}",
                    f"{label} {scene.replace('_', ' ')}",
                    lambda c, scene=scene, operation=operation: require_controller(
                        c, ErgoBQController
                    ).scene(scene, operation),
                    kind=Kind.SAVE,
                )
            )
    result.extend(
        (
            catalog_button(
                "ergobq_sync_a_b",
                "Synchronize A to B",
                lambda c: require_controller(c, ErgoBQController).publish(codec.force_sync(0)),
                kind=Kind.EXTRA,
            ),
            catalog_button(
                "ergobq_sync_b_a",
                "Synchronize B to A",
                lambda c: require_controller(c, ErgoBQController).publish(codec.force_sync(1)),
                kind=Kind.EXTRA,
            ),
            catalog_button(
                "ergobq_diy_stop",
                "Stop DIY program",
                lambda c: require_controller(c, ErgoBQController).publish(codec.run_diy(3)),
                kind=Kind.PRESET,
            ),
            ControllerButtonSpec(
                "ergobq_refresh",
                "Refresh bed state",
                lambda c: c.write_command(codec.frame(2)),
                diagnostic=True,
            ),
            ControllerButtonSpec(
                "ergobq_features",
                "Query bed features",
                lambda c: c.write_command(codec.frame(0)),
                diagnostic=True,
            ),
            ControllerButtonSpec(
                "ergobq_metadata",
                "Query hardware metadata",
                lambda c: require_controller(c, ErgoBQController).metadata(),
                diagnostic=True,
            ),
        )
    )
    return tuple(button for button in result if button is not None)


def numbers(controller: ErgoBQController) -> tuple[ControllerNumberSpec, ...]:
    result = [
        ControllerNumberSpec(
            f"ergobq_target_{dp}",
            f"ergobq_target_{dp}",
            POSITIONS[dp],
            0,
            app.AXES[dp][1],
            1,
            lambda c, value, dp=dp: require_controller(c, ErgoBQController).target(
                dp, _integer(value)
            ),
            card=motor_card(f"ergobq_motor_{dp}"),
        )
        for dp in controller.axes
    ]
    for zone in MASSAGE_ON:
        result.append(
            ControllerNumberSpec(
                f"ergobq_{zone}_intensity",
                f"ergobq_{zone}_intensity",
                MASSAGE_FIELDS[zone, "intensity"],
                0,
                5,
                1,
                lambda c, value, zone=zone: require_controller(c, ErgoBQController).change_massage(
                    zone, "intensity", _integer(value)
                ),
                card=CARD_MASSAGE,
            )
        )
    return tuple(result)


def _integer(value: float) -> int:
    if not float(value).is_integer():
        raise ValueError("Expected a whole number")
    return int(value)


def switches(_controller: ErgoBQController) -> tuple[ControllerSwitchSpec, ...]:
    result = [
        ControllerSwitchSpec(
            f"ergobq_{name}",
            f"ergobq_{name}",
            lambda c, on, dp=dp: (
                require_controller(c, ErgoBQController).set_massage_sync(on)
                if dp == 18
                else require_controller(c, ErgoBQController).publish((codec.boolean(dp, on),))
            ),
            state_key=key,
            entity_registry_enabled_default=name != "child_lock",
        )
        for name, dp, key in (("child_lock", 30, CHILD_LOCK), ("massage_sync", 18, MASSAGE_SYNC))
    ]
    result.extend(
        ControllerSwitchSpec(
            f"ergobq_{zone}_on",
            f"ergobq_{zone}_on",
            lambda c, on, zone=zone: require_controller(c, ErgoBQController).change_massage(
                zone, "on", on
            ),
            state_key=MASSAGE_ON[zone],
            card=CARD_MASSAGE,
        )
        for zone in MASSAGE_ON
    )
    return tuple(result)


def selects(_controller: ErgoBQController) -> tuple[ControllerSelectSpec, ...]:
    result = [
        ControllerSelectSpec(
            "ergobq_side",
            "ergobq_side",
            SIDE,
            ("a", "b", "ab"),
            lambda c, v: require_controller(c, ErgoBQController).publish(
                (codec.enumeration(9, ("a", "b", "ab").index(v)),)
            ),
            entity_registry_enabled_default=False,
        )
    ]
    for zone in MASSAGE_ON:
        result.append(
            ControllerSelectSpec(
                f"ergobq_{zone}_timer",
                f"ergobq_{zone}_timer",
                MASSAGE_TIMER_OPTION[zone],
                app.MASSAGE_TIMER_OPTIONS,
                lambda c, v, zone=zone: require_controller(
                    c, ErgoBQController
                ).set_zone_massage_timer(zone, v),
                available_fn=lambda c, zone=zone: (
                    zone in require_controller(c, ErgoBQController)._massages
                ),
                card=CARD_MASSAGE_TIMER,
            )
        )
        result.append(
            ControllerSelectSpec(
                f"ergobq_{zone}_mode",
                f"ergobq_{zone}_mode",
                MASSAGE_MODE[zone],
                app.MODES,
                lambda c, v, zone=zone: require_controller(c, ErgoBQController).change_massage(
                    zone, "mode", app.MODES.index(v)
                ),
                card=CARD_MASSAGE,
            )
        )
    return tuple(result)


def sensors(_controller: ErgoBQController) -> tuple[ControllerStateSensorSpec, ...]:
    return tuple(
        ControllerStateSensorSpec(str(key), str(key), key, "mdi:timer-outline", "s")
        for key in (
            LIGHT_REMAINING,
            DIY_REMAINING,
            MASSAGE_FIELDS["head", "remaining"],
            MASSAGE_FIELDS["legs", "remaining"],
        )
    ) + (
        ControllerStateSensorSpec(
            "ergobq_identity", "ergobq_identity", IDENTITY, "mdi:bed-outline"
        ),
    )


def binary_sensors(_controller: ErgoBQController) -> tuple[ControllerStateBinarySensorSpec, ...]:
    return tuple(
        ControllerStateBinarySensorSpec(str(key), str(key), key, "mdi:alert-circle-outline")
        for key in (*FAULT_FLAGS.values(), PARTNER_CONNECTED, PARTNER_BROADCAST)
    )
