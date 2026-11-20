"""The auxiliary receiver has local bed settings, without report or network entities."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from custom_components.adjustable_bed.beds.bedtech.sleep import BedTechSleepController
from custom_components.adjustable_bed.beds.ruf_richmat.protocol import sleep_frame
from tests.error_helpers import raises_key
from tests.hold_lease_wire import virtual_clock
from tests.test_bedtech_classic import make


def auxiliary():
    primary = make()
    c = primary._coordinator
    ctrl = BedTechSleepController(c)
    c.controller = ctrl
    ctrl._owner = c.client
    ctrl._char = MagicMock(
        uuid="26f66991-68ee-c2be-444d-b95c3f2dc38a", properties=["write", "notify"]
    )
    return ctrl


async def test_local_user_modes_and_clock_frames():
    with virtual_clock():
        ctrl = auxiliary()
        await ctrl.direct_user_mode("single")
        await ctrl.direct_user_mode("double")
        with patch(
            "custom_components.adjustable_bed.beds.bedtech.sleep.dt_util.now",
            return_value=datetime.fromtimestamp(1779577942, UTC),
        ):
            await ctrl.sync_clock()
        assert [bytes(c.args[1]).hex() for c in ctrl.client.write_gatt_char.call_args_list] == [
            "fa059614010301",
            "fa057414010302",
            "fa0625055634126a",
        ]
        assert ctrl.motor_control_specs == ()
        assert ctrl.controller_state_sensor_specs == ctrl.controller_state_binary_sensor_specs == ()
        assert len(ctrl.controller_switch_specs) == 2


async def test_auxiliary_stale_entry_cannot_write_after_ble_wait():
    ctrl = auxiliary()
    await ctrl._ble_lock.acquire()
    task = asyncio.create_task(ctrl.direct_user_mode("single"))
    await asyncio.sleep(0)
    ctrl._coordinator.entry.data = {"protocol_variant": "model_5i"}
    ctrl._ble_lock.release()
    with raises_key("bed_changed"):
        await task
    ctrl.client.write_gatt_char.assert_not_called()


def test_auxiliary_telemetry_does_not_publish_and_operate_ack_is_separate():
    ctrl = auxiliary()
    ctrl._apply_frame(sleep_frame(0x11, b'{"Left":{"HD":72,"IsOnBed":1}}'))
    assert ctrl._coordinator.controller_state == {}
    ctrl._apply_frame(bytes.fromhex("fa0566a5140101"))
    assert list(ctrl._coordinator.controller_state.values()) == ["on"]


async def test_auxiliary_pair_options_are_compared_by_value():
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.coordinator import ChildEntryView

    ctrl = auxiliary()
    parent = MockConfigEntry(domain="adjustable_bed", options={"idle_disconnect_seconds": 40})
    ctrl._coordinator.entry = ChildEntryView(
        parent, {"bed_type": "bedtech_classic"}, lambda _data: None
    )
    assert ctrl._coordinator.entry.data is not ctrl._coordinator.entry.data
    with virtual_clock():
        await ctrl.direct_user_mode("single")

        async def execute(send, **_kwargs):
            await send(ctrl)

        ctrl._coordinator.async_execute_controller_command.side_effect = execute
        await ctrl._serialized_write(sleep_frame(5, b"1234"))
    assert ctrl.client.write_gatt_char.await_count == 2
