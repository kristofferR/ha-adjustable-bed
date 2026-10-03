"""Exact Home audio exception remains independent from preset query identity."""
from dataclasses import replace

import pytest

from custom_components.adjustable_bed.motion_bed_actions import ACTION_BY_KEY
from custom_components.adjustable_bed.motion_bed_models import select_motion_bed
from custom_components.adjustable_bed.motion_bed_protocol import build_alarm, build_audio_volume
from custom_components.adjustable_bed.motion_bed_requests import MotionBedWrite
from custom_components.adjustable_bed.motion_bed_state import (
    MotionBedRoute,
    MotionBedState,
    parse_motion_bed_notification,
)
from tests.test_motion_bed_controller import rig_for

NAMES = ("QMS-MQ", "QMS2", "S3-2", "QMS3", "QMS3-N93-327", "QMS3-n93-327", "prefix-QMS3-N93-327-suffix")
REPLIES = (("03",0), ("03",1), ("04",0x0F), ("04",0xAF), ("04",0x1F), ("04",0xA1))


def reply(kind, flag):
    if kind == "03":
        return bytes.fromhex("FFFFFFFF0100030B" + f"{flag:02X}")
    return bytes.fromhex("FFFFFFFF01000413" + f"{flag:02X}" + "06300082000101020000")


@pytest.mark.parametrize("name", NAMES)
def test_exact_uppercase_audio_exception_does_not_change_query_packet_selection(name):
    selection = select_motion_bed(name)
    assert selection.alternate_identity
    assert selection.audio_excluded == ("QMS3-N93-327" in name.upper())
    assert selection.route.audio_excluded == selection.audio_excluded
    action = next(action for action in ACTION_BY_KEY.values() if action.owner == "Kuaijie" + selection.preset + "Fragment" and action.kind == "query")
    state = MotionBedState()
    assert action.select(state, selection.alternate_identity) == action.select(state, True)
    assert replace(selection, audio_excluded=not selection.audio_excluded).route.alternate_identity


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("kind,flag", REPLIES)
async def test_actual_callback_audio_feedback_controls_preview_volume_and_alarm_validation(name, kind, flag):
    rig = rig_for(name)
    await rig.controller.start_notify()
    rig.callback(rig.last, bytearray(reply(kind, flag)))
    excluded = "QMS3-N93-327" in name.upper()
    expected = not excluded and flag not in ((0,) if kind == "03" else (0x0F,0xAF))
    assert rig.controller.protocol_diagnostics["audio_available"] is expected
    assert rig.controller.persisted_app_state == {"audio_available": expected}
    volume = MotionBedWrite("audio", (build_audio_volume(2),), "home")
    alarm = MotionBedWrite("alarm", (build_alarm(enabled=True,hour=6,minute=30,weekdays={},audio=expected),), "home", confirmed=True, persistent=True, alarm_audio=expected)
    rig.controller.validate_motion_bed_write(alarm)
    mismatch = replace(alarm, alarm_audio=not expected)
    with pytest.raises(ValueError, match="audio"):
        rig.controller.validate_motion_bed_write(mismatch)
    if expected:
        rig.controller.validate_motion_bed_action("alarm_activity_audio_preview_1")
        rig.controller.validate_motion_bed_write(volume)
    else:
        with pytest.raises(ValueError, match="audio support"):
            rig.controller.validate_motion_bed_action("alarm_activity_audio_preview_1")
        with pytest.raises(ValueError, match="audio support|unavailable"):
            rig.controller.validate_motion_bed_write(volume)
    await rig.controller.stop_notify()


@pytest.mark.parametrize("context", ["motor", "motor_settings"])
@pytest.mark.parametrize("flag", [0x0F,0xAF,0x1F,0xA1])
def test_home_audio_exception_cannot_modify_pure_modular_receiver(context, flag):
    raw = reply("04", flag)
    route = MotionBedRoute(preset_variant="modular", alternate_identity=True, contexts=frozenset({context}), audio_excluded=True)
    result = parse_motion_bed_notification(raw, route, MotionBedState())
    assert result.state.audio_available == (flag not in (0x0F,0xAF))
