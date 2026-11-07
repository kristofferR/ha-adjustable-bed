"""Named, closed Motion Bed app actions and their exact source branches.

This catalogue contains semantic action bindings, not a public raw packet writer.
The protocol module owns bytes; model selection owns which surfaces are offered.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .motion_bed_state import MotionBedContext, MotionBedState

ActionKind = Literal["press", "held", "stop", "query", "program", "persistent"]

@dataclass(frozen=True, slots=True)
class MotionBedPacket:
    source_id: str
    state_key: str | None = None
    expected: bool | int = True
    alternate: bool | None = None
    branch: str = ""

    def matches(self, state: MotionBedState, alternate: bool) -> bool:
        if self.alternate is not None and self.alternate != alternate:
            return False
        if self.state_key is None:
            return True
        value = getattr(state, self.state_key)
        if value is None and type(self.expected) is bool:
            value = False
        if type(self.expected) is int and self.expected < 0:
            return value != -self.expected
        return value == self.expected

@dataclass(frozen=True, slots=True)
class MotionBedAction:
    key: str
    name: str
    owner: str
    context: MotionBedContext
    kind: ActionKind
    packets: tuple[MotionBedPacket, ...]

    def select(self, state: MotionBedState, alternate: bool, *, branch: str = "app") -> tuple[str, ...]:
        if branch != "app":
            if self.kind != "program" or branch not in ("save", "clear"):
                raise ValueError("Only preset program actions accept explicit save/clear")
            return tuple(packet.source_id for packet in self.packets if packet.branch == branch)
        return tuple(packet.source_id for packet in self.packets if packet.matches(state, alternate))

MOTION_BED_ACTIONS: tuple[MotionBedAction, ...] = (
    MotionBedAction('alarm_activity_audio_preview_1', 'Preview audio 1', 'AlarmActivity', 'home', 'press', (
        MotionBedPacket('AlarmActivity:296', None, True, None, ''),
    )),
    MotionBedAction('alarm_activity_audio_preview_2', 'Preview audio 2', 'AlarmActivity', 'home', 'press', (
        MotionBedPacket('AlarmActivity:300', None, True, None, ''),
    )),
    MotionBedAction('alarm_activity_audio_preview_3', 'Preview audio 3', 'AlarmActivity', 'home', 'press', (
        MotionBedPacket('AlarmActivity:304', None, True, None, ''),
    )),
    MotionBedAction('alarm_activity_audio_preview_4', 'Preview audio 4', 'AlarmActivity', 'home', 'press', (
        MotionBedPacket('AlarmActivity:306', None, True, None, ''),
    )),
    MotionBedAction('alarm_activity_audio_preview_5', 'Preview audio 5', 'AlarmActivity', 'home', 'press', (
        MotionBedPacket('AlarmActivity:308', None, True, None, ''),
    )),
    MotionBedAction('alarm_activity_audio_stop', 'Stop audio preview', 'AlarmActivity', 'home', 'press', (
        MotionBedPacket('AlarmActivity:314', None, True, None, ''),
    )),
    MotionBedAction('massage_set_activity_air_status', 'Air status', 'AnmoSetActivity', 'air_settings', 'query', (
        MotionBedPacket('AnmoSetActivity:260', None, True, None, ''),
    )),
    MotionBedAction('change_device_activity_module_status', 'Module status', 'ChangeDeviceActivity', 'module_change', 'query', (
        MotionBedPacket('ChangeDeviceActivity:96', None, True, None, ''),
    )),
    MotionBedAction('change_device_activity_delete_motor', 'Delete motor module', 'ChangeDeviceActivity', 'module_change', 'persistent', (
        MotionBedPacket('ChangeDeviceActivity:213', None, True, None, ''),
    )),
    MotionBedAction('change_device_activity_delete_thermal', 'Delete thermal module', 'ChangeDeviceActivity', 'module_change', 'persistent', (
        MotionBedPacket('ChangeDeviceActivity:219', None, True, None, ''),
    )),
    MotionBedAction('change_device_activity_delete_air', 'Delete air module', 'ChangeDeviceActivity', 'module_change', 'persistent', (
        MotionBedPacket('ChangeDeviceActivity:225', None, True, None, ''),
    )),
    MotionBedAction('connect_mcu_activity_module_status', 'Module status', 'ConnectMcuActivity', 'module_binding', 'query', (
        MotionBedPacket('ConnectMcuActivity:311', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_massage_wave_decrease', 'Massage Frequency decrease', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:270', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_massage_wave_increase', 'Massage Frequency increase', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:275', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_massage_upper_decrease', 'Back Mass decrease', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:281', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_massage_upper_increase', 'Back Mass increase', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:286', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_massage_lower_decrease', 'Leg Mass decrease', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:292', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_massage_lower_increase', 'Leg Mass increase', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:297', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_brightness_0', 'Brightness 0', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:385:level 0', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_brightness_1', 'Brightness 1', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:385:level 1', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_brightness_2', 'Brightness 2', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:385:level 2', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_brightness_3', 'Brightness 3', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:385:level 3', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_brightness_4', 'Brightness 4', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:385:level 4', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_brightness_5', 'Brightness 5', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:385:level 5', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_brightness_6', 'Brightness 6', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:385:level 6', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_brightness_7', 'Brightness 7', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:385:level 7', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_brightness_8', 'Brightness 8', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:385:level 8', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_brightness_9', 'Brightness 9', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:385:level 9', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_brightness_10', 'Brightness 10', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:385:level 10', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_audio_preview_1', 'Preview audio 1', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:490', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_audio_preview_2', 'Preview audio 2', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:494', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_audio_preview_3', 'Preview audio 3', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:498', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_audio_preview_4', 'Preview audio 4', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:500', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_audio_preview_5', 'Preview audio 5', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:502', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_audio_stop', 'Stop audio preview', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:508', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_save_massage_defaults', 'Save massage defaults', 'DianDongSetActivity', 'motor_settings', 'persistent', (
        MotionBedPacket('DianDongSetActivity:515', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_save_light_defaults', 'Save light defaults', 'DianDongSetActivity', 'motor_settings', 'persistent', (
        MotionBedPacket('DianDongSetActivity:522', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_tv_10fenzhong', '10Mins', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:525', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_tv_10xiaoshi', '10Hours', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:535', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_tv_8xiaoshi', '8Hours', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:545', None, True, None, ''),
    )),
    MotionBedAction('dian_dong_set_activity_10time', '10min', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:557', 'massage_timer', 10, None, 'selected'),
        MotionBedPacket('DianDongSetActivity:559', 'massage_timer', -10, None, 'unselected'),
    )),
    MotionBedAction('dian_dong_set_activity_20time', '20min', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:569', 'massage_timer', 20, None, 'selected'),
        MotionBedPacket('DianDongSetActivity:571', 'massage_timer', -20, None, 'unselected'),
    )),
    MotionBedAction('dian_dong_set_activity_30time', '30min', 'DianDongSetActivity', 'motor_settings', 'press', (
        MotionBedPacket('DianDongSetActivity:581', 'massage_timer', 30, None, 'selected'),
        MotionBedPacket('DianDongSetActivity:583', 'massage_timer', -30, None, 'unselected'),
    )),
    MotionBedAction('dian_dong_set_activity_status', 'Refresh status', 'DianDongSetActivity', 'motor_settings', 'query', (
        MotionBedPacket('DianDongSetActivity:629', None, True, None, ''),
        MotionBedPacket('DianDongSetActivity:631', None, True, None, ''),
    )),
    MotionBedAction('home_activity_sensor_status', 'Sensor status', 'HomeActivity', 'home', 'query', (
        MotionBedPacket('HomeActivity:142', None, True, None, ''),
    )),
    MotionBedAction('home_activity_bed_status', 'Bed status', 'HomeActivity', 'home', 'query', (
        MotionBedPacket('HomeActivity:311', None, True, None, ''),
    )),
    MotionBedAction('home_activity_sleep_configuration', 'Sleep configuration', 'HomeActivity', 'home', 'query', (
        MotionBedPacket('HomeActivity:321', None, True, None, ''),
    )),
    MotionBedAction('home_activity_brightness_status', 'Brightness status', 'HomeActivity', 'home', 'query', (
        MotionBedPacket('HomeActivity:455', None, True, None, ''),
    )),
    MotionBedAction('home_activity_smart_sleep_status', 'Sleep configuration status', 'HomeActivity', 'smart_sleep', 'query', (
        MotionBedPacket('HomeActivity:463', None, True, None, ''),
    )),
    MotionBedAction('home_activity_sleep_timer_status', 'Sleep timer status', 'HomeActivity', 'home', 'query', (
        MotionBedPacket('HomeActivity:465', None, True, None, ''),
    )),
    MotionBedAction('main_mcu_activity_module_status', 'Module status', 'MainMcuActivity', 'module_startup', 'query', (
        MotionBedPacket('MainMcuActivity:182', None, True, None, ''),
    )),
    MotionBedAction('press_set_activity_pressure_status', 'Pressure status', 'PressSetActivity', 'pressure_settings', 'query', (
        MotionBedPacket('PressSetActivity:224', None, True, None, ''),
    )),
    MotionBedAction('setting2activity_sensor_status', 'Sensor status', 'Setting2Activity', 'fault_settings', 'query', (
        MotionBedPacket('Setting2Activity:238', None, True, None, ''),
    )),
    MotionBedAction('sleep_adjust_activity_exit_status', 'Exit adjustment status', 'SleepAdjustActivity', 'sleep_adjust', 'query', (
        MotionBedPacket('SleepAdjustActivity:102', None, True, None, ''),
    )),
    MotionBedAction('sleep_adjust_activity_angle_configuration', 'Sleep angle configuration', 'SleepAdjustActivity', 'sleep_adjust', 'query', (
        MotionBedPacket('SleepAdjustActivity:165', None, True, None, ''),
        MotionBedPacket('SleepAdjustActivity:411', None, True, None, ''),
    )),
    MotionBedAction('sleep_adjust_activity_adjust_head_up', 'Sleep adjustment head up', 'SleepAdjustActivity', 'sleep_adjust', 'held', (
        MotionBedPacket('SleepAdjustActivity:243:caller line 188', None, True, None, ''),
    )),
    MotionBedAction('sleep_adjust_activity_adjust_back_up', 'Sleep adjustment back up', 'SleepAdjustActivity', 'sleep_adjust', 'held', (
        MotionBedPacket('SleepAdjustActivity:243:caller line 204', None, True, None, ''),
    )),
    MotionBedAction('sleep_adjust_activity_adjust_legs_up', 'Sleep adjustment legs up', 'SleepAdjustActivity', 'sleep_adjust', 'held', (
        MotionBedPacket('SleepAdjustActivity:243:caller line 218', None, True, None, ''),
    )),
    MotionBedAction('sleep_adjust_activity_adjust_lumbar_up', 'Sleep adjustment lumbar up', 'SleepAdjustActivity', 'sleep_adjust', 'held', (
        MotionBedPacket('SleepAdjustActivity:243:caller line 232', None, True, None, ''),
    )),
    MotionBedAction('sleep_adjust_activity_stop', 'Stop', 'SleepAdjustActivity', 'sleep_adjust', 'stop', (
        MotionBedPacket('SleepAdjustActivity:251', None, True, None, ''),
        MotionBedPacket('SleepAdjustActivity:269', None, True, None, ''),
    )),
    MotionBedAction('sleep_adjust_activity_raw_positions', 'Raw positions', 'SleepAdjustActivity', 'sleep_adjust', 'query', (
        MotionBedPacket('SleepAdjustActivity:255', None, True, None, ''),
        MotionBedPacket('SleepAdjustActivity:273', None, True, None, ''),
        MotionBedPacket('SleepAdjustActivity:281', None, True, None, ''),
        MotionBedPacket('SleepAdjustActivity:289', None, True, None, ''),
    )),
    MotionBedAction('sleep_adjust_activity_adjust_head_down', 'Sleep adjustment head down', 'SleepAdjustActivity', 'sleep_adjust', 'held', (
        MotionBedPacket('SleepAdjustActivity:261:caller line 181', None, True, None, ''),
    )),
    MotionBedAction('sleep_adjust_activity_adjust_back_down', 'Sleep adjustment back down', 'SleepAdjustActivity', 'sleep_adjust', 'held', (
        MotionBedPacket('SleepAdjustActivity:261:caller line 197', None, True, None, ''),
    )),
    MotionBedAction('sleep_adjust_activity_adjust_legs_down', 'Sleep adjustment legs down', 'SleepAdjustActivity', 'sleep_adjust', 'held', (
        MotionBedPacket('SleepAdjustActivity:261:caller line 211', None, True, None, ''),
    )),
    MotionBedAction('sleep_adjust_activity_adjust_lumbar_down', 'Sleep adjustment lumbar down', 'SleepAdjustActivity', 'sleep_adjust', 'held', (
        MotionBedPacket('SleepAdjustActivity:261:caller line 225', None, True, None, ''),
    )),
    MotionBedAction('sleep_data_entry_activity_exit_status', 'Exit calibration status', 'SleepDataEntryActivity', 'calibration_capture', 'query', (
        MotionBedPacket('SleepDataEntryActivity:105', None, True, None, ''),
    )),
    MotionBedAction('sleep_data_entry_activity_calibration_status', 'Calibration status', 'SleepDataEntryActivity', 'calibration_capture', 'query', (
        MotionBedPacket('SleepDataEntryActivity:126', None, True, None, ''),
    )),
    MotionBedAction('sleep_data_entry_activity_calibration_flat_position', 'Calibration flat position', 'SleepDataEntryActivity', 'calibration_capture', 'press', (
        MotionBedPacket('SleepDataEntryActivity:189', None, True, None, ''),
    )),
    MotionBedAction('sleep_data_entry_activity_calibration_next_position', 'Calibration next position', 'SleepDataEntryActivity', 'calibration_capture', 'press', (
        MotionBedPacket('SleepDataEntryActivity:202', None, True, None, ''),
    )),
    MotionBedAction('sleep_data_entry_activity_capture_flat', 'Capture flat calibration', 'SleepDataEntryActivity', 'calibration_capture', 'query', (
        MotionBedPacket('SleepDataEntryActivity:248', None, True, None, ''),
    )),
    MotionBedAction('sleep_data_entry_activity_capture_side', 'Capture side calibration', 'SleepDataEntryActivity', 'calibration_capture', 'query', (
        MotionBedPacket('SleepDataEntryActivity:253', None, True, None, ''),
    )),
    MotionBedAction('sleep_data_entry_activity_reset_calibration', 'Reset calibration', 'SleepDataEntryActivity', 'calibration_capture', 'persistent', (
        MotionBedPacket('SleepDataEntryActivity:268', None, True, None, ''),
    )),
    MotionBedAction('sleep_data_entry_activity_capture_debug', 'Calibration debug sample', 'SleepDataEntryActivity', 'calibration_capture', 'query', (
        MotionBedPacket('SleepDataEntryActivity:293', None, True, None, ''),
    )),
    MotionBedAction('sleep_day_report_activity_exit_status', 'Exit report status', 'SleepDayReportActivity', 'day_report', 'query', (
        MotionBedPacket('SleepDayReportActivity:88', None, True, None, ''),
    )),
    MotionBedAction('massage_fragment_sync', 'Sync', 'AnmoFragment', 'massage', 'press', (
        MotionBedPacket('AnmoFragment:88', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('AnmoFragment:90', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('massage_fragment_massage_wave_decrease', 'Mass Wave decrease', 'AnmoFragment', 'massage', 'press', (
        MotionBedPacket('AnmoFragment:100', None, True, None, ''),
    )),
    MotionBedAction('massage_fragment_massage_wave_increase', 'Mass Wave increase', 'AnmoFragment', 'massage', 'press', (
        MotionBedPacket('AnmoFragment:105', None, True, None, ''),
    )),
    MotionBedAction('massage_fragment_massage_upper_decrease', 'Back Mass decrease', 'AnmoFragment', 'massage', 'press', (
        MotionBedPacket('AnmoFragment:111', None, True, None, ''),
    )),
    MotionBedAction('massage_fragment_massage_upper_increase', 'Back Mass increase', 'AnmoFragment', 'massage', 'press', (
        MotionBedPacket('AnmoFragment:116', None, True, None, ''),
    )),
    MotionBedAction('massage_fragment_massage_lower_decrease', 'Leg Mass decrease', 'AnmoFragment', 'massage', 'press', (
        MotionBedPacket('AnmoFragment:122', None, True, None, ''),
    )),
    MotionBedAction('massage_fragment_massage_lower_increase', 'Leg Mass increase', 'AnmoFragment', 'massage', 'press', (
        MotionBedPacket('AnmoFragment:127', None, True, None, ''),
    )),
    MotionBedAction('massage_fragment_10time', '10min', 'AnmoFragment', 'massage', 'press', (
        MotionBedPacket('AnmoFragment:165', 'massage_timer', 10, None, 'selected'),
        MotionBedPacket('AnmoFragment:167', 'massage_timer', -10, None, 'unselected'),
    )),
    MotionBedAction('massage_fragment_20time', '20min', 'AnmoFragment', 'massage', 'press', (
        MotionBedPacket('AnmoFragment:177', 'massage_timer', 20, None, 'selected'),
        MotionBedPacket('AnmoFragment:179', 'massage_timer', -20, None, 'unselected'),
    )),
    MotionBedAction('massage_fragment_30time', '30min', 'AnmoFragment', 'massage', 'press', (
        MotionBedPacket('AnmoFragment:189', 'massage_timer', 30, None, 'selected'),
        MotionBedPacket('AnmoFragment:191', 'massage_timer', -30, None, 'unselected'),
    )),
    MotionBedAction('light_fragment_sync', 'Sync', 'DengguangFragment', 'light', 'press', (
        MotionBedPacket('DengguangFragment:99', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('DengguangFragment:101', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('light_fragment_brightness_0', 'Brightness 0', 'DengguangFragment', 'light', 'press', (
        MotionBedPacket('DengguangFragment:176:level 0', None, True, None, ''),
    )),
    MotionBedAction('light_fragment_brightness_1', 'Brightness 1', 'DengguangFragment', 'light', 'press', (
        MotionBedPacket('DengguangFragment:176:level 1', None, True, None, ''),
    )),
    MotionBedAction('light_fragment_brightness_2', 'Brightness 2', 'DengguangFragment', 'light', 'press', (
        MotionBedPacket('DengguangFragment:176:level 2', None, True, None, ''),
    )),
    MotionBedAction('light_fragment_brightness_3', 'Brightness 3', 'DengguangFragment', 'light', 'press', (
        MotionBedPacket('DengguangFragment:176:level 3', None, True, None, ''),
    )),
    MotionBedAction('light_fragment_brightness_4', 'Brightness 4', 'DengguangFragment', 'light', 'press', (
        MotionBedPacket('DengguangFragment:176:level 4', None, True, None, ''),
    )),
    MotionBedAction('light_fragment_brightness_5', 'Brightness 5', 'DengguangFragment', 'light', 'press', (
        MotionBedPacket('DengguangFragment:176:level 5', None, True, None, ''),
    )),
    MotionBedAction('light_fragment_brightness_6', 'Brightness 6', 'DengguangFragment', 'light', 'press', (
        MotionBedPacket('DengguangFragment:176:level 6', None, True, None, ''),
    )),
    MotionBedAction('light_fragment_brightness_7', 'Brightness 7', 'DengguangFragment', 'light', 'press', (
        MotionBedPacket('DengguangFragment:176:level 7', None, True, None, ''),
    )),
    MotionBedAction('light_fragment_brightness_8', 'Brightness 8', 'DengguangFragment', 'light', 'press', (
        MotionBedPacket('DengguangFragment:176:level 8', None, True, None, ''),
    )),
    MotionBedAction('light_fragment_brightness_9', 'Brightness 9', 'DengguangFragment', 'light', 'press', (
        MotionBedPacket('DengguangFragment:176:level 9', None, True, None, ''),
    )),
    MotionBedAction('light_fragment_brightness_10', 'Brightness 10', 'DengguangFragment', 'light', 'press', (
        MotionBedPacket('DengguangFragment:176:level 10', None, True, None, ''),
    )),
    MotionBedAction('light_fragment_status', 'Refresh status', 'DengguangFragment', 'light', 'query', (
        MotionBedPacket('DengguangFragment:181', None, True, None, ''),
    )),
    MotionBedAction('light_fragment_tv_10fenzhong', '10Mins', 'DengguangFragment', 'light', 'press', (
        MotionBedPacket('DengguangFragment:208', None, True, None, ''),
    )),
    MotionBedAction('light_fragment_tv_10xiaoshi', '10Hours', 'DengguangFragment', 'light', 'press', (
        MotionBedPacket('DengguangFragment:218', None, True, None, ''),
    )),
    MotionBedAction('light_fragment_tv_8xiaoshi', '8Hours', 'DengguangFragment', 'light', 'press', (
        MotionBedPacket('DengguangFragment:228', None, True, None, ''),
    )),
    MotionBedAction('diandong_fragment_sensor_status', 'Sensor status', 'DiandongFragment', 'motor', 'query', (
        MotionBedPacket('DiandongFragment:135', None, True, None, ''),
    )),
    MotionBedAction('diandong_fragment_status', 'Refresh status', 'DiandongFragment', 'motor', 'query', (
        MotionBedPacket('DiandongFragment:319', None, True, None, ''),
    )),
    MotionBedAction('diandong_fragment_stop', 'Stop', 'DiandongFragment', 'motor', 'stop', (
        MotionBedPacket('DiandongFragment:349', None, True, None, ''),
        MotionBedPacket('DiandongFragment:387', None, True, None, ''),
        MotionBedPacket('DiandongFragment:412', None, True, None, ''),
    )),
    MotionBedAction('diandong_fragment_back_down', 'BACK down', 'DiandongFragment', 'motor', 'held', (
        MotionBedPacket('DiandongFragment:392', None, True, None, ''),
    )),
    MotionBedAction('diandong_fragment_legs_down', 'LEG down', 'DiandongFragment', 'motor', 'held', (
        MotionBedPacket('DiandongFragment:417', None, True, None, ''),
    )),
    MotionBedAction('diandong_fragment_light_enabled_on', 'Enable module light', 'DiandongFragment', 'motor', 'press', (
        MotionBedPacket('DiandongFragment:452', None, True, None, ''),
    )),
    MotionBedAction('diandong_fragment_light_enabled_off', 'Disable module light', 'DiandongFragment', 'motor', 'press', (
        MotionBedPacket('DiandongFragment:454', None, True, None, ''),
    )),
    MotionBedAction('diandong_fragment_massage_enabled_on', 'Enable module massage', 'DiandongFragment', 'motor', 'press', (
        MotionBedPacket('DiandongFragment:464', None, True, None, ''),
    )),
    MotionBedAction('diandong_fragment_massage_enabled_off', 'Disable module massage', 'DiandongFragment', 'motor', 'press', (
        MotionBedPacket('DiandongFragment:466', None, True, None, ''),
    )),
    MotionBedAction('diandong_fragment_flat', 'Flatten', 'DiandongFragment', 'motor', 'press', (
        MotionBedPacket('DiandongFragment:566', None, True, None, ''),
    )),
    MotionBedAction('diandong_fragment_memory1', 'Memory One', 'DiandongFragment', 'motor', 'press', (
        MotionBedPacket('DiandongFragment:578', 'memory_1', True, None, 'selected'),
        MotionBedPacket('DiandongFragment:580', 'memory_1', False, None, 'unselected'),
    )),
    MotionBedAction('diandong_fragment_memory2', 'Memory 2', 'DiandongFragment', 'motor', 'press', (
        MotionBedPacket('DiandongFragment:594', 'memory_2', True, None, 'selected'),
        MotionBedPacket('DiandongFragment:596', 'memory_2', False, None, 'unselected'),
    )),
    MotionBedAction('diandong_fragment_tv', 'Television', 'DiandongFragment', 'motor', 'press', (
        MotionBedPacket('DiandongFragment:610', 'tv', True, None, 'selected'),
        MotionBedPacket('DiandongFragment:612', 'tv', False, None, 'unselected'),
    )),
    MotionBedAction('diandong_fragment_zero_gravity', 'Zero-Pressure', 'DiandongFragment', 'motor', 'press', (
        MotionBedPacket('DiandongFragment:626', 'zero_gravity', True, None, 'selected'),
        MotionBedPacket('DiandongFragment:628', 'zero_gravity', False, None, 'unselected'),
    )),
    MotionBedAction('diandong_fragment_cradle', 'Cradle', 'DiandongFragment', 'motor', 'press', (
        MotionBedPacket('DiandongFragment:636', None, True, None, ''),
    )),
    MotionBedAction('diandong_fragment_snore', 'Stop Snoring', 'DiandongFragment', 'motor', 'press', (
        MotionBedPacket('DiandongFragment:648', 'snore', True, None, 'selected'),
        MotionBedPacket('DiandongFragment:650', 'snore', False, None, 'unselected'),
    )),
    MotionBedAction('diandong_fragment_zero_gravity_program', 'Zero Gravity program', 'DiandongFragment', 'motor', 'program', (
        MotionBedPacket('DiandongFragment:663', 'zero_gravity', True, None, 'clear'),
        MotionBedPacket('DiandongFragment:665', 'zero_gravity', False, None, 'save'),
    )),
    MotionBedAction('diandong_fragment_snore_program', 'Snore program', 'DiandongFragment', 'motor', 'program', (
        MotionBedPacket('DiandongFragment:672', 'snore', True, None, 'clear'),
        MotionBedPacket('DiandongFragment:674', 'snore', False, None, 'save'),
    )),
    MotionBedAction('diandong_fragment_tv_program', 'Tv program', 'DiandongFragment', 'motor', 'program', (
        MotionBedPacket('DiandongFragment:681', 'tv', True, None, 'clear'),
        MotionBedPacket('DiandongFragment:683', 'tv', False, None, 'save'),
    )),
    MotionBedAction('diandong_fragment_memory2_program', 'Memory2 program', 'DiandongFragment', 'motor', 'program', (
        MotionBedPacket('DiandongFragment:690', 'memory_2', True, None, 'clear'),
        MotionBedPacket('DiandongFragment:692', 'memory_2', False, None, 'save'),
    )),
    MotionBedAction('diandong_fragment_memory1_program', 'Memory1 program', 'DiandongFragment', 'motor', 'program', (
        MotionBedPacket('DiandongFragment:699', 'memory_1', True, None, 'clear'),
        MotionBedPacket('DiandongFragment:701', 'memory_1', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k11fragment_sync', 'Sync', 'KuaijieK11Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK11Fragment:50', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('KuaijieK11Fragment:52', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k11fragment_stop', 'Stop', 'KuaijieK11Fragment', 'preset', 'stop', (
        MotionBedPacket('KuaijieK11Fragment:93', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k11fragment_memory2_program', 'Memory2 program', 'KuaijieK11Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK11Fragment:136', 'memory_2', True, None, 'clear'),
        MotionBedPacket('KuaijieK11Fragment:138', 'memory_2', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k11fragment_memory1_program', 'Memory1 program', 'KuaijieK11Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK11Fragment:145', 'memory_1', True, None, 'clear'),
        MotionBedPacket('KuaijieK11Fragment:147', 'memory_1', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k11fragment_status', 'Refresh status', 'KuaijieK11Fragment', 'preset', 'query', (
        MotionBedPacket('KuaijieK11Fragment:203', None, True, None, ''),
        MotionBedPacket('KuaijieK11Fragment:205', None, True, None, ''),
        MotionBedPacket('KuaijieK11Fragment:207', None, True, None, ''),
        MotionBedPacket('KuaijieK11Fragment:209', None, True, None, ''),
        MotionBedPacket('KuaijieK11Fragment:211', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k11fragment_flat', 'Flat Bed', 'KuaijieK11Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK11Fragment:226', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k11fragment_houqing', 'Tilt Backward', 'KuaijieK11Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK11Fragment:232', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k11fragment_memory1', 'Memory 1', 'KuaijieK11Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK11Fragment:243', 'memory_1', True, None, 'selected'),
    )),
    MotionBedAction('kuaijie_k11fragment_memory2', 'Memory 2', 'KuaijieK11Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK11Fragment:255', 'memory_2', True, None, 'selected'),
    )),
    MotionBedAction('kuaijie_k11fragment_tv', 'Watch TV', 'KuaijieK11Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK11Fragment:268', 'tv', True, None, 'selected'),
        MotionBedPacket('KuaijieK11Fragment:270', 'tv', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k11fragment_zero_gravity', 'Zero Gravity', 'KuaijieK11Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK11Fragment:285', 'zero_gravity', True, None, 'selected'),
        MotionBedPacket('KuaijieK11Fragment:287', 'zero_gravity', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k11fragment_qianqing', 'Tilt forward', 'KuaijieK11Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK11Fragment:295', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k11fragment_wholeflat', 'All Flat', 'KuaijieK11Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK11Fragment:301', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k11fragment_wholeshangsheng', 'Rise', 'KuaijieK11Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK11Fragment:307', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k11fragment_wholexiajiang', 'Decline', 'KuaijieK11Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK11Fragment:313', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k11fragment_snore', 'Anti Snore', 'KuaijieK11Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK11Fragment:326', 'snore', True, None, 'selected'),
        MotionBedPacket('KuaijieK11Fragment:328', 'snore', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k11fragment_zero_gravity_program', 'Zero Gravity program', 'KuaijieK11Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK11Fragment:341', 'zero_gravity', True, None, 'clear'),
        MotionBedPacket('KuaijieK11Fragment:343', 'zero_gravity', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k11fragment_snore_program', 'Snore program', 'KuaijieK11Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK11Fragment:350', 'snore', True, None, 'clear'),
        MotionBedPacket('KuaijieK11Fragment:352', 'snore', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k11fragment_tv_program', 'Tv program', 'KuaijieK11Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK11Fragment:359', 'tv', True, None, 'clear'),
        MotionBedPacket('KuaijieK11Fragment:361', 'tv', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k1fragment_sync', 'Sync', 'KuaijieK1Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK1Fragment:50', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('KuaijieK1Fragment:52', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k1fragment_stop', 'Stop', 'KuaijieK1Fragment', 'preset', 'stop', (
        MotionBedPacket('KuaijieK1Fragment:93', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k1fragment_memory2_program', 'Memory2 program', 'KuaijieK1Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK1Fragment:136', 'memory_2', True, None, 'clear'),
        MotionBedPacket('KuaijieK1Fragment:138', 'memory_2', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k1fragment_memory1_program', 'Memory1 program', 'KuaijieK1Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK1Fragment:145', 'memory_1', True, None, 'clear'),
        MotionBedPacket('KuaijieK1Fragment:147', 'memory_1', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k1fragment_status', 'Refresh status', 'KuaijieK1Fragment', 'preset', 'query', (
        MotionBedPacket('KuaijieK1Fragment:203', None, True, None, ''),
        MotionBedPacket('KuaijieK1Fragment:205', None, True, None, ''),
        MotionBedPacket('KuaijieK1Fragment:207', None, True, None, ''),
        MotionBedPacket('KuaijieK1Fragment:209', None, True, None, ''),
        MotionBedPacket('KuaijieK1Fragment:211', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k1fragment_flat', 'Flat Bed', 'KuaijieK1Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK1Fragment:226', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k1fragment_memory1', 'Memory 1', 'KuaijieK1Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK1Fragment:237', 'memory_1', True, None, 'selected'),
    )),
    MotionBedAction('kuaijie_k1fragment_memory2', 'Memory 2', 'KuaijieK1Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK1Fragment:249', 'memory_2', True, None, 'selected'),
    )),
    MotionBedAction('kuaijie_k1fragment_tv', 'Watch TV', 'KuaijieK1Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK1Fragment:262', 'tv', True, None, 'selected'),
        MotionBedPacket('KuaijieK1Fragment:264', 'tv', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k1fragment_zero_gravity', 'Zero Gravity', 'KuaijieK1Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK1Fragment:279', 'zero_gravity', True, None, 'selected'),
        MotionBedPacket('KuaijieK1Fragment:281', 'zero_gravity', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k1fragment_air_fullgxunhuan', 'FULL CYCLE', 'KuaijieK1Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK1Fragment:289', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k1fragment_tingmusic', 'Music', 'KuaijieK1Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK1Fragment:295', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k1fragment_legsrelax', 'Leg Relax', 'KuaijieK1Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK1Fragment:301', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k1fragment_hipxunhuan', 'HIP CYCLE', 'KuaijieK1Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK1Fragment:307', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k1fragment_yujia', 'YOGA', 'KuaijieK1Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK1Fragment:313', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k1fragment_snore', 'Anti Snore', 'KuaijieK1Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK1Fragment:326', 'snore', True, None, 'selected'),
        MotionBedPacket('KuaijieK1Fragment:328', 'snore', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k1fragment_zero_gravity_program', 'Zero Gravity program', 'KuaijieK1Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK1Fragment:341', 'zero_gravity', True, None, 'clear'),
        MotionBedPacket('KuaijieK1Fragment:343', 'zero_gravity', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k1fragment_snore_program', 'Snore program', 'KuaijieK1Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK1Fragment:350', 'snore', True, None, 'clear'),
        MotionBedPacket('KuaijieK1Fragment:352', 'snore', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k1fragment_tv_program', 'Tv program', 'KuaijieK1Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK1Fragment:359', 'tv', True, None, 'clear'),
        MotionBedPacket('KuaijieK1Fragment:361', 'tv', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k2fragment_sync', 'Sync', 'KuaijieK2Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK2Fragment:46', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('KuaijieK2Fragment:48', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k2fragment_stop', 'Stop', 'KuaijieK2Fragment', 'preset', 'stop', (
        MotionBedPacket('KuaijieK2Fragment:89', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k2fragment_memory2_program', 'Memory2 program', 'KuaijieK2Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK2Fragment:127', 'memory_2', True, None, 'clear'),
        MotionBedPacket('KuaijieK2Fragment:129', 'memory_2', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k2fragment_memory1_program', 'Memory1 program', 'KuaijieK2Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK2Fragment:136', 'memory_1', True, None, 'clear'),
        MotionBedPacket('KuaijieK2Fragment:138', 'memory_1', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k2fragment_status', 'Refresh status', 'KuaijieK2Fragment', 'preset', 'query', (
        MotionBedPacket('KuaijieK2Fragment:213', None, True, True, ''),
        MotionBedPacket('KuaijieK2Fragment:215', None, True, True, ''),
        MotionBedPacket('KuaijieK2Fragment:217', None, True, True, ''),
        MotionBedPacket('KuaijieK2Fragment:219', None, True, True, ''),
        MotionBedPacket('KuaijieK2Fragment:221', None, True, True, ''),
        MotionBedPacket('KuaijieK2Fragment:223', None, True, False, ''),
        MotionBedPacket('KuaijieK2Fragment:225', None, True, False, ''),
        MotionBedPacket('KuaijieK2Fragment:227', None, True, False, ''),
        MotionBedPacket('KuaijieK2Fragment:229', None, True, False, ''),
        MotionBedPacket('KuaijieK2Fragment:231', None, True, False, ''),
    )),
    MotionBedAction('kuaijie_k2fragment_flat', 'Flat Bed', 'KuaijieK2Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK2Fragment:247', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k2fragment_memory1', 'Memory 1', 'KuaijieK2Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK2Fragment:258', 'memory_1', True, None, 'selected'),
    )),
    MotionBedAction('kuaijie_k2fragment_memory2', 'Memory 2', 'KuaijieK2Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK2Fragment:270', 'memory_2', True, None, 'selected'),
    )),
    MotionBedAction('kuaijie_k2fragment_tv', 'Watch TV', 'KuaijieK2Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK2Fragment:283', 'tv', True, None, 'selected'),
        MotionBedPacket('KuaijieK2Fragment:285', 'tv', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k2fragment_zero_gravity', 'Zero Gravity', 'KuaijieK2Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK2Fragment:300', 'zero_gravity', True, None, 'selected'),
        MotionBedPacket('KuaijieK2Fragment:302', 'zero_gravity', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k2fragment_snore', 'Anti Snore', 'KuaijieK2Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK2Fragment:317', 'snore', True, None, 'selected'),
        MotionBedPacket('KuaijieK2Fragment:319', 'snore', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k2fragment_zero_gravity_program', 'Zero Gravity program', 'KuaijieK2Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK2Fragment:332', 'zero_gravity', True, None, 'clear'),
        MotionBedPacket('KuaijieK2Fragment:334', 'zero_gravity', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k2fragment_snore_program', 'Snore program', 'KuaijieK2Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK2Fragment:341', 'snore', True, None, 'clear'),
        MotionBedPacket('KuaijieK2Fragment:343', 'snore', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k2fragment_tv_program', 'Tv program', 'KuaijieK2Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK2Fragment:350', 'tv', True, None, 'clear'),
        MotionBedPacket('KuaijieK2Fragment:352', 'tv', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k2mfragment_sync', 'Sync', 'KuaijieK2MFragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK2MFragment:64', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('KuaijieK2MFragment:66', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k2mfragment_stop', 'Stop', 'KuaijieK2MFragment', 'preset', 'stop', (
        MotionBedPacket('KuaijieK2MFragment:107', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k2mfragment_memory2_program', 'Memory2 program', 'KuaijieK2MFragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK2MFragment:166', 'memory_2', True, None, 'clear'),
        MotionBedPacket('KuaijieK2MFragment:168', 'memory_2', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k2mfragment_memory1_program', 'Memory1 program', 'KuaijieK2MFragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK2MFragment:175', 'memory_1', True, None, 'clear'),
        MotionBedPacket('KuaijieK2MFragment:177', 'memory_1', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k2mfragment_status', 'Refresh status', 'KuaijieK2MFragment', 'preset', 'query', (
        MotionBedPacket('KuaijieK2MFragment:266', None, True, True, ''),
        MotionBedPacket('KuaijieK2MFragment:268', None, True, True, ''),
        MotionBedPacket('KuaijieK2MFragment:270', None, True, True, ''),
        MotionBedPacket('KuaijieK2MFragment:272', None, True, True, ''),
        MotionBedPacket('KuaijieK2MFragment:274', None, True, True, ''),
        MotionBedPacket('KuaijieK2MFragment:276', None, True, False, ''),
        MotionBedPacket('KuaijieK2MFragment:278', None, True, False, ''),
        MotionBedPacket('KuaijieK2MFragment:280', None, True, False, ''),
        MotionBedPacket('KuaijieK2MFragment:282', None, True, False, ''),
        MotionBedPacket('KuaijieK2MFragment:284', None, True, False, ''),
    )),
    MotionBedAction('kuaijie_k2mfragment_relax', 'Relax', 'KuaijieK2MFragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK2MFragment:300', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k2mfragment_flat', 'Flat Bed', 'KuaijieK2MFragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK2MFragment:306', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k2mfragment_memory1', 'Memory 1', 'KuaijieK2MFragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK2MFragment:317', 'memory_1', True, None, 'selected'),
    )),
    MotionBedAction('kuaijie_k2mfragment_memory2', 'Memory 2', 'KuaijieK2MFragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK2MFragment:329', 'memory_2', True, None, 'selected'),
    )),
    MotionBedAction('kuaijie_k2mfragment_tv', 'Watch TV', 'KuaijieK2MFragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK2MFragment:342', 'tv', True, None, 'selected'),
        MotionBedPacket('KuaijieK2MFragment:344', 'tv', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k2mfragment_zero_gravity', 'Zero Gravity', 'KuaijieK2MFragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK2MFragment:359', 'zero_gravity', True, None, 'selected'),
        MotionBedPacket('KuaijieK2MFragment:361', 'zero_gravity', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k2mfragment_music', 'Sleep And Music', 'KuaijieK2MFragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK2MFragment:373', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k2mfragment_audio_off', 'Stop audio', 'KuaijieK2MFragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK2MFragment:375', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k2mfragment_snore', 'Anti Snore', 'KuaijieK2MFragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK2MFragment:389', 'snore', True, None, 'selected'),
        MotionBedPacket('KuaijieK2MFragment:391', 'snore', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k2mfragment_zero_gravity_program', 'Zero Gravity program', 'KuaijieK2MFragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK2MFragment:404', 'zero_gravity', True, None, 'clear'),
        MotionBedPacket('KuaijieK2MFragment:406', 'zero_gravity', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k2mfragment_snore_program', 'Snore program', 'KuaijieK2MFragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK2MFragment:413', 'snore', True, None, 'clear'),
        MotionBedPacket('KuaijieK2MFragment:415', 'snore', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k2mfragment_tv_program', 'Tv program', 'KuaijieK2MFragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK2MFragment:422', 'tv', True, None, 'clear'),
        MotionBedPacket('KuaijieK2MFragment:424', 'tv', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k2mfragment_audio_stop', 'Stop audio preview', 'KuaijieK2MFragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK2MFragment:457', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k2mfragment_audio_status', 'Audio status', 'KuaijieK2MFragment', 'preset', 'query', (
        MotionBedPacket('KuaijieK2MFragment:466', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k3fragment_sync', 'Sync', 'KuaijieK3Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK3Fragment:46', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('KuaijieK3Fragment:48', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k3fragment_stop', 'Stop', 'KuaijieK3Fragment', 'preset', 'stop', (
        MotionBedPacket('KuaijieK3Fragment:85', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k3fragment_memory2_program', 'Memory2 program', 'KuaijieK3Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK3Fragment:125', 'memory_2', True, None, 'clear'),
        MotionBedPacket('KuaijieK3Fragment:127', 'memory_2', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k3fragment_memory1_program', 'Memory1 program', 'KuaijieK3Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK3Fragment:134', 'memory_1', True, None, 'clear'),
        MotionBedPacket('KuaijieK3Fragment:136', 'memory_1', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k3fragment_status', 'Refresh status', 'KuaijieK3Fragment', 'preset', 'query', (
        MotionBedPacket('KuaijieK3Fragment:183', None, True, None, ''),
        MotionBedPacket('KuaijieK3Fragment:185', None, True, None, ''),
        MotionBedPacket('KuaijieK3Fragment:187', None, True, None, ''),
        MotionBedPacket('KuaijieK3Fragment:189', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k3fragment_dingyao', 'Lumbar', 'KuaijieK3Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK3Fragment:204', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k3fragment_flat', 'Flat Bed', 'KuaijieK3Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK3Fragment:210', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k3fragment_memory1', 'Memory 1', 'KuaijieK3Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK3Fragment:221', 'memory_1', True, None, 'selected'),
    )),
    MotionBedAction('kuaijie_k3fragment_memory2', 'Memory 2', 'KuaijieK3Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK3Fragment:233', 'memory_2', True, None, 'selected'),
    )),
    MotionBedAction('kuaijie_k3fragment_tv', 'Watch TV', 'KuaijieK3Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK3Fragment:246', 'tv', True, None, 'selected'),
        MotionBedPacket('KuaijieK3Fragment:248', 'tv', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k3fragment_zero_gravity', 'Zero Gravity', 'KuaijieK3Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK3Fragment:263', 'zero_gravity', True, None, 'selected'),
        MotionBedPacket('KuaijieK3Fragment:265', 'zero_gravity', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k3fragment_yijiangjiangxia', 'Decline', 'KuaijieK3Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK3Fragment:273', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k3fragment_yijiangshengqi', 'Rise', 'KuaijieK3Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK3Fragment:279', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k3fragment_zero_gravity_program', 'Zero Gravity program', 'KuaijieK3Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK3Fragment:290', 'zero_gravity', True, None, 'clear'),
        MotionBedPacket('KuaijieK3Fragment:292', 'zero_gravity', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k3fragment_tv_program', 'Tv program', 'KuaijieK3Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK3Fragment:299', 'tv', True, None, 'clear'),
        MotionBedPacket('KuaijieK3Fragment:301', 'tv', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k4fragment_sync', 'Sync', 'KuaijieK4Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK4Fragment:55', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('KuaijieK4Fragment:57', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k4fragment_stop', 'Stop', 'KuaijieK4Fragment', 'preset', 'stop', (
        MotionBedPacket('KuaijieK4Fragment:99', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k4fragment_status', 'Refresh status', 'KuaijieK4Fragment', 'preset', 'query', (
        MotionBedPacket('KuaijieK4Fragment:182', None, True, None, ''),
        MotionBedPacket('KuaijieK4Fragment:184', None, True, None, ''),
        MotionBedPacket('KuaijieK4Fragment:186', None, True, None, ''),
        MotionBedPacket('KuaijieK4Fragment:188', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k4fragment_split_flat_left', 'Flat Bed', 'KuaijieK4Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK4Fragment:211', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k4fragment_split_flat_right', 'Flat Bed', 'KuaijieK4Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK4Fragment:217', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k4fragment_split_tv_left', 'Watch TV', 'KuaijieK4Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK4Fragment:229', 'left_tv', True, None, 'selected'),
        MotionBedPacket('KuaijieK4Fragment:231', 'left_tv', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k4fragment_split_tv_right', 'Watch TV', 'KuaijieK4Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK4Fragment:245', 'left_tv', True, None, 'selected'),
        MotionBedPacket('KuaijieK4Fragment:247', 'left_tv', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k4fragment_split_zero_gravity_left', 'Zero Gravity', 'KuaijieK4Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK4Fragment:261', 'left_tv', True, None, 'selected'),
        MotionBedPacket('KuaijieK4Fragment:263', 'left_tv', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k4fragment_split_zero_gravity_right', 'Zero Gravity', 'KuaijieK4Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK4Fragment:277', 'right_tv', True, None, 'selected'),
        MotionBedPacket('KuaijieK4Fragment:279', 'right_tv', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k4fragment_coupled_flat', 'Flat Bed', 'KuaijieK4Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK4Fragment:295', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k4fragment_coupled_tv', 'Watch TV', 'KuaijieK4Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK4Fragment:301', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k4fragment_coupled_zero_gravity', 'Zero Gravity', 'KuaijieK4Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK4Fragment:307', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k4fragment_tv_left_program', 'Tv Left program', 'KuaijieK4Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK4Fragment:332', 'left_tv', True, None, 'clear'),
        MotionBedPacket('KuaijieK4Fragment:334', 'left_tv', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k4fragment_tv_right_program', 'Tv Right program', 'KuaijieK4Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK4Fragment:341', 'right_tv', True, None, 'clear'),
        MotionBedPacket('KuaijieK4Fragment:343', 'right_tv', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k4fragment_zero_gravity_left_program', 'Zero Gravity Left program', 'KuaijieK4Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK4Fragment:350', 'left_zero_gravity', True, None, 'clear'),
        MotionBedPacket('KuaijieK4Fragment:352', 'left_zero_gravity', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k4fragment_zero_gravity_right_program', 'Zero Gravity Right program', 'KuaijieK4Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK4Fragment:359', 'right_zero_gravity', True, None, 'clear'),
        MotionBedPacket('KuaijieK4Fragment:361', 'right_zero_gravity', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k5fragment_sync', 'Sync', 'KuaijieK5Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK5Fragment:57', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('KuaijieK5Fragment:59', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k5fragment_stop', 'Stop', 'KuaijieK5Fragment', 'preset', 'stop', (
        MotionBedPacket('KuaijieK5Fragment:107', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k5fragment_status', 'Refresh status', 'KuaijieK5Fragment', 'preset', 'query', (
        MotionBedPacket('KuaijieK5Fragment:170', None, True, None, ''),
        MotionBedPacket('KuaijieK5Fragment:172', None, True, None, ''),
        MotionBedPacket('KuaijieK5Fragment:174', None, True, None, ''),
        MotionBedPacket('KuaijieK5Fragment:176', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k5fragment_split_flat', 'Split Flat', 'KuaijieK5Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK5Fragment:192', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k5fragment_split_memory_left', 'Memory', 'KuaijieK5Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK5Fragment:204', 'left_memory', True, None, 'selected'),
    )),
    MotionBedAction('kuaijie_k5fragment_split_memory_right', 'Memory', 'KuaijieK5Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK5Fragment:216', 'left_memory', True, None, 'selected'),
    )),
    MotionBedAction('kuaijie_k5fragment_split_tv_left', 'Watch TV', 'KuaijieK5Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK5Fragment:229', 'left_tv', True, None, 'selected'),
        MotionBedPacket('KuaijieK5Fragment:231', 'left_tv', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k5fragment_split_tv_right', 'Watch TV', 'KuaijieK5Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK5Fragment:245', 'left_tv', True, None, 'selected'),
        MotionBedPacket('KuaijieK5Fragment:247', 'left_tv', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k5fragment_split_zero_gravity_left', 'Zero Gravity', 'KuaijieK5Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK5Fragment:261', 'left_tv', True, None, 'selected'),
        MotionBedPacket('KuaijieK5Fragment:263', 'left_tv', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k5fragment_split_zero_gravity_right', 'Zero Gravity', 'KuaijieK5Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK5Fragment:277', 'right_tv', True, None, 'selected'),
        MotionBedPacket('KuaijieK5Fragment:279', 'right_tv', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k5fragment_coupled_flat', 'Flat Bed', 'KuaijieK5Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK5Fragment:289', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k5fragment_coupled_memory_left', 'Memory', 'KuaijieK5Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK5Fragment:300', 'left_memory', True, None, 'selected'),
    )),
    MotionBedAction('kuaijie_k5fragment_coupled_memory_right', 'Memory', 'KuaijieK5Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK5Fragment:312', 'left_memory', True, None, 'selected'),
    )),
    MotionBedAction('kuaijie_k5fragment_coupled_tv', 'Watch TV', 'KuaijieK5Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK5Fragment:319', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k5fragment_tv_left_program', 'Tv Left program', 'KuaijieK5Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK5Fragment:357', 'left_tv', True, None, 'clear'),
        MotionBedPacket('KuaijieK5Fragment:360', 'left_tv', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k5fragment_tv_right_program', 'Tv Right program', 'KuaijieK5Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK5Fragment:368', 'right_tv', True, None, 'clear'),
        MotionBedPacket('KuaijieK5Fragment:371', 'right_tv', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k5fragment_split_memory_left_program', 'Split Memory Left program', 'KuaijieK5Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK5Fragment:379', 'left_memory', True, None, 'clear'),
        MotionBedPacket('KuaijieK5Fragment:382', 'left_memory', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k5fragment_coupled_memory_left_program', 'Coupled Memory Left program', 'KuaijieK5Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK5Fragment:390', 'coupled_left_memory', True, None, 'clear'),
        MotionBedPacket('KuaijieK5Fragment:393', 'coupled_left_memory', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k5fragment_split_memory_right_program', 'Split Memory Right program', 'KuaijieK5Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK5Fragment:401', 'right_memory', True, None, 'clear'),
        MotionBedPacket('KuaijieK5Fragment:404', 'right_memory', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k5fragment_coupled_memory_right_program', 'Coupled Memory Right program', 'KuaijieK5Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK5Fragment:412', 'coupled_right_memory', True, None, 'clear'),
        MotionBedPacket('KuaijieK5Fragment:415', 'coupled_right_memory', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k8fragment_sync', 'Sync', 'KuaijieK8Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK8Fragment:46', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('KuaijieK8Fragment:48', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k8fragment_stop', 'Stop', 'KuaijieK8Fragment', 'preset', 'stop', (
        MotionBedPacket('KuaijieK8Fragment:85', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k8fragment_memory2_program', 'Memory2 program', 'KuaijieK8Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK8Fragment:125', 'memory_2', True, None, 'clear'),
        MotionBedPacket('KuaijieK8Fragment:127', 'memory_2', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k8fragment_memory1_program', 'Memory1 program', 'KuaijieK8Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK8Fragment:134', 'memory_1', True, None, 'clear'),
        MotionBedPacket('KuaijieK8Fragment:136', 'memory_1', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k8fragment_status', 'Refresh status', 'KuaijieK8Fragment', 'preset', 'query', (
        MotionBedPacket('KuaijieK8Fragment:183', None, True, None, ''),
        MotionBedPacket('KuaijieK8Fragment:185', None, True, None, ''),
        MotionBedPacket('KuaijieK8Fragment:187', None, True, None, ''),
        MotionBedPacket('KuaijieK8Fragment:189', None, True, None, ''),
        MotionBedPacket('KuaijieK8Fragment:191', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k8fragment_dingyao', 'Lumbar', 'KuaijieK8Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK8Fragment:206', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k8fragment_flat', 'Flat Bed', 'KuaijieK8Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK8Fragment:212', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k8fragment_memory1', 'Memory 1', 'KuaijieK8Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK8Fragment:223', 'memory_1', True, None, 'selected'),
    )),
    MotionBedAction('kuaijie_k8fragment_memory2', 'Memory 2', 'KuaijieK8Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK8Fragment:235', 'memory_2', True, None, 'selected'),
    )),
    MotionBedAction('kuaijie_k8fragment_tv', 'Watch TV', 'KuaijieK8Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK8Fragment:248', 'tv', True, None, 'selected'),
        MotionBedPacket('KuaijieK8Fragment:250', 'tv', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k8fragment_zero_gravity', 'Zero Gravity', 'KuaijieK8Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK8Fragment:265', 'zero_gravity', True, None, 'selected'),
        MotionBedPacket('KuaijieK8Fragment:267', 'zero_gravity', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k8fragment_yijiangjiangxia', 'Decline', 'KuaijieK8Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK8Fragment:275', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k8fragment_yijiangshengqi', 'Rise', 'KuaijieK8Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK8Fragment:281', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k8fragment_zero_gravity_program', 'Zero Gravity program', 'KuaijieK8Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK8Fragment:292', 'zero_gravity', True, None, 'clear'),
        MotionBedPacket('KuaijieK8Fragment:294', 'zero_gravity', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k8fragment_tv_program', 'Tv program', 'KuaijieK8Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK8Fragment:301', 'tv', True, None, 'clear'),
        MotionBedPacket('KuaijieK8Fragment:303', 'tv', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k9fragment_sync', 'Sync', 'KuaijieK9Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK9Fragment:47', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('KuaijieK9Fragment:49', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k9fragment_stop', 'Stop', 'KuaijieK9Fragment', 'preset', 'stop', (
        MotionBedPacket('KuaijieK9Fragment:86', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k9fragment_memory2_program', 'Memory2 program', 'KuaijieK9Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK9Fragment:126', 'memory_2', True, None, 'clear'),
        MotionBedPacket('KuaijieK9Fragment:128', 'memory_2', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k9fragment_memory1_program', 'Memory1 program', 'KuaijieK9Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK9Fragment:135', 'memory_1', True, None, 'clear'),
        MotionBedPacket('KuaijieK9Fragment:137', 'memory_1', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k9fragment_status', 'Refresh status', 'KuaijieK9Fragment', 'preset', 'query', (
        MotionBedPacket('KuaijieK9Fragment:193', None, True, None, ''),
        MotionBedPacket('KuaijieK9Fragment:195', None, True, None, ''),
        MotionBedPacket('KuaijieK9Fragment:197', None, True, None, ''),
        MotionBedPacket('KuaijieK9Fragment:199', None, True, None, ''),
        MotionBedPacket('KuaijieK9Fragment:201', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k9fragment_flat', 'Flat Bed', 'KuaijieK9Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK9Fragment:216', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k9fragment_memory1', 'Memory 1', 'KuaijieK9Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK9Fragment:227', 'memory_1', True, None, 'selected'),
    )),
    MotionBedAction('kuaijie_k9fragment_memory2', 'Memory 2', 'KuaijieK9Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK9Fragment:239', 'memory_2', True, None, 'selected'),
    )),
    MotionBedAction('kuaijie_k9fragment_tv', 'Watch TV', 'KuaijieK9Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK9Fragment:252', 'tv', True, None, 'selected'),
        MotionBedPacket('KuaijieK9Fragment:254', 'tv', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k9fragment_zero_gravity', 'Zero Gravity', 'KuaijieK9Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK9Fragment:269', 'zero_gravity', True, None, 'selected'),
        MotionBedPacket('KuaijieK9Fragment:271', 'zero_gravity', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k9fragment_yijiangjiangxia', 'Decline', 'KuaijieK9Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK9Fragment:279', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k9fragment_yijiangshengqi', 'Rise', 'KuaijieK9Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK9Fragment:285', None, True, None, ''),
    )),
    MotionBedAction('kuaijie_k9fragment_snore', 'Anti Snore', 'KuaijieK9Fragment', 'preset', 'press', (
        MotionBedPacket('KuaijieK9Fragment:298', 'snore', True, None, 'selected'),
        MotionBedPacket('KuaijieK9Fragment:300', 'snore', False, None, 'unselected'),
    )),
    MotionBedAction('kuaijie_k9fragment_zero_gravity_program', 'Zero Gravity program', 'KuaijieK9Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK9Fragment:313', 'zero_gravity', True, None, 'clear'),
        MotionBedPacket('KuaijieK9Fragment:315', 'zero_gravity', False, None, 'save'),
    )),
    MotionBedAction('kuaijie_k9fragment_tv_program', 'Tv program', 'KuaijieK9Fragment', 'preset', 'program', (
        MotionBedPacket('KuaijieK9Fragment:322', 'tv', True, None, 'clear'),
        MotionBedPacket('KuaijieK9Fragment:324', 'tv', False, None, 'save'),
    )),
    MotionBedAction('lengnuan_fragment_thermal_status', 'Thermal status', 'LengnuanFragment', 'thermal', 'query', (
        MotionBedPacket('LengnuanFragment:58', None, True, None, ''),
        MotionBedPacket('LengnuanFragment:183', None, True, None, ''),
    )),
    MotionBedAction('lengnuan_fragment_thermal_gear_0', 'Cooling 4', 'LengnuanFragment', 'thermal', 'press', (
        MotionBedPacket('LengnuanFragment:279:thermal slider table index 0', None, True, None, ''),
    )),
    MotionBedAction('lengnuan_fragment_thermal_gear_1', 'Cooling 3', 'LengnuanFragment', 'thermal', 'press', (
        MotionBedPacket('LengnuanFragment:279:thermal slider table index 1', None, True, None, ''),
    )),
    MotionBedAction('lengnuan_fragment_thermal_gear_2', 'Cooling 2', 'LengnuanFragment', 'thermal', 'press', (
        MotionBedPacket('LengnuanFragment:279:thermal slider table index 2', None, True, None, ''),
    )),
    MotionBedAction('lengnuan_fragment_thermal_gear_3', 'Cooling 1', 'LengnuanFragment', 'thermal', 'press', (
        MotionBedPacket('LengnuanFragment:279:thermal slider table index 3', None, True, None, ''),
    )),
    MotionBedAction('lengnuan_fragment_thermal_gear_4', 'Off', 'LengnuanFragment', 'thermal', 'press', (
        MotionBedPacket('LengnuanFragment:279:thermal slider table index 4', None, True, None, ''),
    )),
    MotionBedAction('lengnuan_fragment_thermal_gear_5', 'Heating 1', 'LengnuanFragment', 'thermal', 'press', (
        MotionBedPacket('LengnuanFragment:279:thermal slider table index 5', None, True, None, ''),
    )),
    MotionBedAction('lengnuan_fragment_thermal_gear_6', 'Heating 2', 'LengnuanFragment', 'thermal', 'press', (
        MotionBedPacket('LengnuanFragment:279:thermal slider table index 6', None, True, None, ''),
    )),
    MotionBedAction('lengnuan_fragment_thermal_gear_7', 'Heating 3', 'LengnuanFragment', 'thermal', 'press', (
        MotionBedPacket('LengnuanFragment:279:thermal slider table index 7', None, True, None, ''),
    )),
    MotionBedAction('lengnuan_fragment_thermal_gear_8', 'Heating 4', 'LengnuanFragment', 'thermal', 'press', (
        MotionBedPacket('LengnuanFragment:279:thermal slider table index 8', None, True, None, ''),
    )),
    MotionBedAction('lengnuan_fragment_thermal_timer_on', 'Enable thermal timer', 'LengnuanFragment', 'thermal', 'press', (
        MotionBedPacket('LengnuanFragment:294', None, True, None, ''),
    )),
    MotionBedAction('lengnuan_fragment_thermal_timer_off', 'Disable thermal timer', 'LengnuanFragment', 'thermal', 'press', (
        MotionBedPacket('LengnuanFragment:296', None, True, None, ''),
    )),
    MotionBedAction('qinang_fragment_status', 'Refresh status', 'QinangFragment', 'air', 'query', (
        MotionBedPacket('QinangFragment:133', None, True, None, ''),
    )),
    MotionBedAction('qinang_fragment_adaptive_on', 'Enable adaptive air massage', 'QinangFragment', 'air', 'press', (
        MotionBedPacket('QinangFragment:172', None, True, None, ''),
    )),
    MotionBedAction('qinang_fragment_adaptive_off', 'Disable adaptive air massage', 'QinangFragment', 'air', 'press', (
        MotionBedPacket('QinangFragment:174', None, True, None, ''),
    )),
    MotionBedAction('qinang_fragment_air_full_program', 'Air Full program', 'QinangFragment', 'air', 'program', (
        MotionBedPacket('QinangFragment:184', 'air_full_custom', True, None, 'clear'),
        MotionBedPacket('QinangFragment:186', 'air_full_custom', False, None, 'save'),
    )),
    MotionBedAction('qinang_fragment_back_program', 'Back program', 'QinangFragment', 'air', 'program', (
        MotionBedPacket('QinangFragment:193', 'air_back_custom', True, None, 'clear'),
        MotionBedPacket('QinangFragment:195', 'air_back_custom', False, None, 'save'),
    )),
    MotionBedAction('qinang_fragment_massage_stop', 'Massage Stopped', 'QinangFragment', 'air', 'press', (
        MotionBedPacket('QinangFragment:302', None, True, None, ''),
    )),
    MotionBedAction('qinang_fragment_back', 'Wave massage', 'QinangFragment', 'air', 'press', (
        MotionBedPacket('QinangFragment:313', None, True, None, ''),
    )),
    MotionBedAction('qinang_fragment_fangqi', 'Deflate', 'QinangFragment', 'air', 'press', (
        MotionBedPacket('QinangFragment:320', None, True, None, ''),
    )),
    MotionBedAction('qinang_fragment_jingbu', 'Neck Massage', 'QinangFragment', 'air', 'press', (
        MotionBedPacket('QinangFragment:326', None, True, None, ''),
    )),
    MotionBedAction('qinang_fragment_air_full', 'Combination massage', 'QinangFragment', 'air', 'press', (
        MotionBedPacket('QinangFragment:342', None, True, None, ''),
    )),
    MotionBedAction('qinang_fragment_sleepmian', 'sleep mode', 'QinangFragment', 'air', 'press', (
        MotionBedPacket('QinangFragment:349', None, True, None, ''),
    )),
    MotionBedAction('qinang_fragment_lumbar', 'Lumbar Massage', 'QinangFragment', 'air', 'press', (
        MotionBedPacket('QinangFragment:355', None, True, None, ''),
    )),
    MotionBedAction('qinang_fragment_yujia', 'Yoga', 'QinangFragment', 'air', 'press', (
        MotionBedPacket('QinangFragment:361', None, True, None, ''),
    )),
    MotionBedAction('smart_sleep_fragment_sleepmian', 'Smart sleep / off', 'SmartSleepFragment', 'smart_sleep', 'press', (
        MotionBedPacket('SmartSleepFragment:144', 'sleep_enabled', True, None, 'selected'),
        MotionBedPacket('SmartSleepFragment:147', 'sleep_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('smart_sleep_fragment_night_light', 'Smart light / off', 'SmartSleepFragment', 'smart_sleep', 'press', (
        MotionBedPacket('SmartSleepFragment:156', 'night_light_enabled', True, None, 'selected'),
        MotionBedPacket('SmartSleepFragment:159', 'night_light_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('weitiao_w10fragment_sync', 'Sync', 'WeitiaoW10Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW10Fragment:50', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('WeitiaoW10Fragment:52', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('weitiao_w10fragment_back_up', 'BACK up', 'WeitiaoW10Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW10Fragment:61', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w10fragment_stop', 'Stop', 'WeitiaoW10Fragment', 'home', 'stop', (
        MotionBedPacket('WeitiaoW10Fragment:65', None, True, None, ''),
        MotionBedPacket('WeitiaoW10Fragment:78', None, True, None, ''),
        MotionBedPacket('WeitiaoW10Fragment:92', None, True, None, ''),
        MotionBedPacket('WeitiaoW10Fragment:105', None, True, None, ''),
        MotionBedPacket('WeitiaoW10Fragment:119', None, True, None, ''),
        MotionBedPacket('WeitiaoW10Fragment:132', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w10fragment_back_down', 'BACK down', 'WeitiaoW10Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW10Fragment:74', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w10fragment_head_up', 'HEAD up', 'WeitiaoW10Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW10Fragment:88', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w10fragment_head_down', 'HEAD down', 'WeitiaoW10Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW10Fragment:101', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w10fragment_legs_up', 'LEG up', 'WeitiaoW10Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW10Fragment:115', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w10fragment_legs_down', 'LEG down', 'WeitiaoW10Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW10Fragment:128', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w11fragment_sync', 'Sync', 'WeitiaoW11Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW11Fragment:50', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('WeitiaoW11Fragment:52', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('weitiao_w11fragment_back_up', 'BACK up', 'WeitiaoW11Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW11Fragment:61', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w11fragment_stop', 'Stop', 'WeitiaoW11Fragment', 'home', 'stop', (
        MotionBedPacket('WeitiaoW11Fragment:65', None, True, None, ''),
        MotionBedPacket('WeitiaoW11Fragment:78', None, True, None, ''),
        MotionBedPacket('WeitiaoW11Fragment:92', None, True, None, ''),
        MotionBedPacket('WeitiaoW11Fragment:105', None, True, None, ''),
        MotionBedPacket('WeitiaoW11Fragment:119', None, True, None, ''),
        MotionBedPacket('WeitiaoW11Fragment:132', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w11fragment_back_down', 'BACK down', 'WeitiaoW11Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW11Fragment:74', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w11fragment_wholelift_up', 'LIFT up', 'WeitiaoW11Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW11Fragment:88', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w11fragment_wholelift_down', 'LIFT down', 'WeitiaoW11Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW11Fragment:101', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w11fragment_legs_up', 'LEG up', 'WeitiaoW11Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW11Fragment:115', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w11fragment_legs_down', 'LEG down', 'WeitiaoW11Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW11Fragment:128', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w12fragment_sync', 'Sync', 'WeitiaoW12Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW12Fragment:49', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('WeitiaoW12Fragment:51', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('weitiao_w12fragment_back_up', 'BACK up', 'WeitiaoW12Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW12Fragment:60', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w12fragment_stop', 'Stop', 'WeitiaoW12Fragment', 'home', 'stop', (
        MotionBedPacket('WeitiaoW12Fragment:64', None, True, None, ''),
        MotionBedPacket('WeitiaoW12Fragment:77', None, True, None, ''),
        MotionBedPacket('WeitiaoW12Fragment:91', None, True, None, ''),
        MotionBedPacket('WeitiaoW12Fragment:104', None, True, None, ''),
        MotionBedPacket('WeitiaoW12Fragment:118', None, True, None, ''),
        MotionBedPacket('WeitiaoW12Fragment:131', None, True, None, ''),
        MotionBedPacket('WeitiaoW12Fragment:144', None, True, None, ''),
        MotionBedPacket('WeitiaoW12Fragment:156', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w12fragment_back_down', 'BACK down', 'WeitiaoW12Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW12Fragment:73', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w12fragment_legs_up', 'LEG up', 'WeitiaoW12Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW12Fragment:87', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w12fragment_legs_down', 'LEG down', 'WeitiaoW12Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW12Fragment:100', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w12fragment_wholelift_up', 'LIFT up', 'WeitiaoW12Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW12Fragment:114', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w12fragment_wholelift_down', 'LIFT down', 'WeitiaoW12Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW12Fragment:127', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w12fragment_wholeqingxie_up', 'TILT up', 'WeitiaoW12Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW12Fragment:141', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w12fragment_wholeqingxie_down', 'TILT down', 'WeitiaoW12Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW12Fragment:153', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w13fragment_sync', 'Sync', 'WeitiaoW13Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW13Fragment:80', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('WeitiaoW13Fragment:82', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('weitiao_w13fragment_back_up', 'BACK up', 'WeitiaoW13Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW13Fragment:96', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w13fragment_stop', 'Stop', 'WeitiaoW13Fragment', 'home', 'stop', (
        MotionBedPacket('WeitiaoW13Fragment:100', None, True, None, ''),
        MotionBedPacket('WeitiaoW13Fragment:113', None, True, None, ''),
        MotionBedPacket('WeitiaoW13Fragment:127', None, True, None, ''),
        MotionBedPacket('WeitiaoW13Fragment:140', None, True, None, ''),
        MotionBedPacket('WeitiaoW13Fragment:154', None, True, None, ''),
        MotionBedPacket('WeitiaoW13Fragment:167', None, True, None, ''),
        MotionBedPacket('WeitiaoW13Fragment:181', None, True, None, ''),
        MotionBedPacket('WeitiaoW13Fragment:194', None, True, None, ''),
        MotionBedPacket('WeitiaoW13Fragment:208', None, True, None, ''),
        MotionBedPacket('WeitiaoW13Fragment:221', None, True, None, ''),
        MotionBedPacket('WeitiaoW13Fragment:234', None, True, None, ''),
        MotionBedPacket('WeitiaoW13Fragment:246', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w13fragment_back_down', 'BACK down', 'WeitiaoW13Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW13Fragment:109', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w13fragment_lumbar_up', 'LUMBAR up', 'WeitiaoW13Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW13Fragment:123', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w13fragment_lumbar_down', 'LUMBAR down', 'WeitiaoW13Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW13Fragment:136', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w13fragment_head_up', 'HEAD up', 'WeitiaoW13Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW13Fragment:150', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w13fragment_head_down', 'HEAD down', 'WeitiaoW13Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW13Fragment:163', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w13fragment_legs_up', 'LEG up', 'WeitiaoW13Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW13Fragment:177', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w13fragment_legs_down', 'LEG down', 'WeitiaoW13Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW13Fragment:190', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w13fragment_wholelift_up', 'LIFT up', 'WeitiaoW13Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW13Fragment:204', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w13fragment_wholelift_down', 'LIFT down', 'WeitiaoW13Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW13Fragment:217', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w13fragment_wholeqingxie_up', 'TILT up', 'WeitiaoW13Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW13Fragment:231', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w13fragment_wholeqingxie_down', 'TILT down', 'WeitiaoW13Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW13Fragment:243', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w13fragment_air_fullgxunhuan', 'FULL CYCLE', 'WeitiaoW13Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW13Fragment:304', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w13fragment_upperxunhuan', 'HEAD CYCLE', 'WeitiaoW13Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW13Fragment:310', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w13fragment_legsxunhuan', 'LEG CYCLE', 'WeitiaoW13Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW13Fragment:316', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w13fragment_lumbarxunhuan', 'LUMBAR CYCLE', 'WeitiaoW13Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW13Fragment:322', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w14fragment_sync', 'Sync', 'WeitiaoW14Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW14Fragment:80', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('WeitiaoW14Fragment:82', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('weitiao_w14fragment_back_up', 'BACK up', 'WeitiaoW14Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW14Fragment:96', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w14fragment_stop', 'Stop', 'WeitiaoW14Fragment', 'home', 'stop', (
        MotionBedPacket('WeitiaoW14Fragment:100', None, True, None, ''),
        MotionBedPacket('WeitiaoW14Fragment:113', None, True, None, ''),
        MotionBedPacket('WeitiaoW14Fragment:127', None, True, None, ''),
        MotionBedPacket('WeitiaoW14Fragment:140', None, True, None, ''),
        MotionBedPacket('WeitiaoW14Fragment:154', None, True, None, ''),
        MotionBedPacket('WeitiaoW14Fragment:167', None, True, None, ''),
        MotionBedPacket('WeitiaoW14Fragment:181', None, True, None, ''),
        MotionBedPacket('WeitiaoW14Fragment:194', None, True, None, ''),
        MotionBedPacket('WeitiaoW14Fragment:208', None, True, None, ''),
        MotionBedPacket('WeitiaoW14Fragment:221', None, True, None, ''),
        MotionBedPacket('WeitiaoW14Fragment:234', None, True, None, ''),
        MotionBedPacket('WeitiaoW14Fragment:246', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w14fragment_back_down', 'BACK down', 'WeitiaoW14Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW14Fragment:109', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w14fragment_lumbar_up', 'LUMBAR up', 'WeitiaoW14Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW14Fragment:123', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w14fragment_lumbar_down', 'LUMBAR down', 'WeitiaoW14Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW14Fragment:136', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w14fragment_head_up', 'HEAD up', 'WeitiaoW14Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW14Fragment:150', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w14fragment_head_down', 'HEAD down', 'WeitiaoW14Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW14Fragment:163', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w14fragment_legs_up', 'LEG up', 'WeitiaoW14Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW14Fragment:177', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w14fragment_legs_down', 'LEG down', 'WeitiaoW14Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW14Fragment:190', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w14fragment_wholelift_up', 'LIFT up', 'WeitiaoW14Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW14Fragment:204', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w14fragment_wholelift_down', 'LIFT down', 'WeitiaoW14Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW14Fragment:217', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w14fragment_wholeqingxie_up', 'TILT up', 'WeitiaoW14Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW14Fragment:231', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w14fragment_wholeqingxie_down', 'TILT down', 'WeitiaoW14Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW14Fragment:243', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w14fragment_air_fullgxunhuan', 'FULL CYCLE', 'WeitiaoW14Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW14Fragment:304', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w14fragment_upperxunhuan', 'HEAD CYCLE', 'WeitiaoW14Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW14Fragment:310', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w14fragment_legsxunhuan', 'LEG CYCLE', 'WeitiaoW14Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW14Fragment:316', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w14fragment_lumbarxunhuan', 'LUMBAR CYCLE', 'WeitiaoW14Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW14Fragment:322', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w18fragment_sync', 'Sync', 'WeitiaoW18Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW18Fragment:78', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('WeitiaoW18Fragment:80', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('weitiao_w18fragment_back_up', 'BACK up', 'WeitiaoW18Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW18Fragment:94', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w18fragment_stop', 'Stop', 'WeitiaoW18Fragment', 'home', 'stop', (
        MotionBedPacket('WeitiaoW18Fragment:98', None, True, None, ''),
        MotionBedPacket('WeitiaoW18Fragment:111', None, True, None, ''),
        MotionBedPacket('WeitiaoW18Fragment:125', None, True, None, ''),
        MotionBedPacket('WeitiaoW18Fragment:138', None, True, None, ''),
        MotionBedPacket('WeitiaoW18Fragment:152', None, True, None, ''),
        MotionBedPacket('WeitiaoW18Fragment:165', None, True, None, ''),
        MotionBedPacket('WeitiaoW18Fragment:179', None, True, None, ''),
        MotionBedPacket('WeitiaoW18Fragment:192', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w18fragment_back_down', 'BACK down', 'WeitiaoW18Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW18Fragment:107', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w18fragment_lumbar_up', 'LUMBAR up', 'WeitiaoW18Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW18Fragment:121', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w18fragment_lumbar_down', 'LUMBAR down', 'WeitiaoW18Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW18Fragment:134', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w18fragment_head_up', 'LIFT up', 'WeitiaoW18Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW18Fragment:148', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w18fragment_head_down', 'LIFT down', 'WeitiaoW18Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW18Fragment:161', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w18fragment_legs_up', 'LEG up', 'WeitiaoW18Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW18Fragment:175', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w18fragment_legs_down', 'LEG down', 'WeitiaoW18Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW18Fragment:188', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w18fragment_air_fullgxunhuan', 'FULL CYCLE', 'WeitiaoW18Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW18Fragment:250', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w18fragment_upperxunhuan', 'HEAD CYCLE', 'WeitiaoW18Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW18Fragment:256', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w18fragment_legsxunhuan', 'LEG CYCLE', 'WeitiaoW18Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW18Fragment:262', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w18fragment_lumbarxunhuan', 'LUMBAR CYCLE', 'WeitiaoW18Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW18Fragment:268', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w1fragment_sync', 'Sync', 'WeitiaoW1Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW1Fragment:78', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('WeitiaoW1Fragment:80', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('weitiao_w1fragment_back_up', 'BACK up', 'WeitiaoW1Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW1Fragment:94', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w1fragment_stop', 'Stop', 'WeitiaoW1Fragment', 'home', 'stop', (
        MotionBedPacket('WeitiaoW1Fragment:98', None, True, None, ''),
        MotionBedPacket('WeitiaoW1Fragment:111', None, True, None, ''),
        MotionBedPacket('WeitiaoW1Fragment:125', None, True, None, ''),
        MotionBedPacket('WeitiaoW1Fragment:138', None, True, None, ''),
        MotionBedPacket('WeitiaoW1Fragment:152', None, True, None, ''),
        MotionBedPacket('WeitiaoW1Fragment:165', None, True, None, ''),
        MotionBedPacket('WeitiaoW1Fragment:179', None, True, None, ''),
        MotionBedPacket('WeitiaoW1Fragment:192', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w1fragment_back_down', 'BACK down', 'WeitiaoW1Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW1Fragment:107', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w1fragment_hip_up', 'HIP up', 'WeitiaoW1Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW1Fragment:121', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w1fragment_hip_down', 'HIP down', 'WeitiaoW1Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW1Fragment:134', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w1fragment_head_up', 'HEAD up', 'WeitiaoW1Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW1Fragment:148', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w1fragment_head_down', 'HEAD down', 'WeitiaoW1Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW1Fragment:161', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w1fragment_legs_up', 'LEG up', 'WeitiaoW1Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW1Fragment:175', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w1fragment_legs_down', 'LEG down', 'WeitiaoW1Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW1Fragment:188', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w1fragment_air_fullgxunhuan', 'FULL CYCLE', 'WeitiaoW1Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW1Fragment:250', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w1fragment_upperxunhuan', 'HEAD CYCLE', 'WeitiaoW1Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW1Fragment:256', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w1fragment_legsxunhuan', 'LEG CYCLE', 'WeitiaoW1Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW1Fragment:262', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w1fragment_hipxunhuan', 'HIP CYCLE', 'WeitiaoW1Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW1Fragment:268', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w2fragment_sync', 'Sync', 'WeitiaoW2Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW2Fragment:78', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('WeitiaoW2Fragment:80', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('weitiao_w2fragment_back_up', 'BACK up', 'WeitiaoW2Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW2Fragment:94', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w2fragment_stop', 'Stop', 'WeitiaoW2Fragment', 'home', 'stop', (
        MotionBedPacket('WeitiaoW2Fragment:98', None, True, None, ''),
        MotionBedPacket('WeitiaoW2Fragment:111', None, True, None, ''),
        MotionBedPacket('WeitiaoW2Fragment:125', None, True, None, ''),
        MotionBedPacket('WeitiaoW2Fragment:138', None, True, None, ''),
        MotionBedPacket('WeitiaoW2Fragment:152', None, True, None, ''),
        MotionBedPacket('WeitiaoW2Fragment:165', None, True, None, ''),
        MotionBedPacket('WeitiaoW2Fragment:179', None, True, None, ''),
        MotionBedPacket('WeitiaoW2Fragment:192', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w2fragment_back_down', 'BACK down', 'WeitiaoW2Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW2Fragment:107', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w2fragment_lumbar_up', 'LUMBAR up', 'WeitiaoW2Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW2Fragment:121', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w2fragment_lumbar_down', 'LUMBAR down', 'WeitiaoW2Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW2Fragment:134', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w2fragment_head_up', 'HEAD up', 'WeitiaoW2Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW2Fragment:148', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w2fragment_head_down', 'HEAD down', 'WeitiaoW2Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW2Fragment:161', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w2fragment_legs_up', 'LEG up', 'WeitiaoW2Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW2Fragment:175', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w2fragment_legs_down', 'LEG down', 'WeitiaoW2Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW2Fragment:188', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w2fragment_air_fullgxunhuan', 'FULL CYCLE', 'WeitiaoW2Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW2Fragment:250', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w2fragment_upperxunhuan', 'HEAD CYCLE', 'WeitiaoW2Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW2Fragment:256', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w2fragment_legsxunhuan', 'LEG CYCLE', 'WeitiaoW2Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW2Fragment:262', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w2fragment_lumbarxunhuan', 'LUMBAR CYCLE', 'WeitiaoW2Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW2Fragment:268', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w3fragment_sync', 'Sync', 'WeitiaoW3Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW3Fragment:78', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('WeitiaoW3Fragment:80', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('weitiao_w3fragment_back_up', 'BACK up', 'WeitiaoW3Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW3Fragment:94', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w3fragment_stop', 'Stop', 'WeitiaoW3Fragment', 'home', 'stop', (
        MotionBedPacket('WeitiaoW3Fragment:98', None, True, None, ''),
        MotionBedPacket('WeitiaoW3Fragment:111', None, True, None, ''),
        MotionBedPacket('WeitiaoW3Fragment:125', None, True, None, ''),
        MotionBedPacket('WeitiaoW3Fragment:138', None, True, None, ''),
        MotionBedPacket('WeitiaoW3Fragment:152', None, True, None, ''),
        MotionBedPacket('WeitiaoW3Fragment:165', None, True, None, ''),
        MotionBedPacket('WeitiaoW3Fragment:179', None, True, None, ''),
        MotionBedPacket('WeitiaoW3Fragment:192', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w3fragment_back_down', 'BACK down', 'WeitiaoW3Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW3Fragment:107', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w3fragment_back_legs_up', 'BACK LEG up', 'WeitiaoW3Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW3Fragment:121', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w3fragment_back_legs_down', 'BACK LEG down', 'WeitiaoW3Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW3Fragment:134', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w3fragment_lumbar_up', 'LUMBAR up', 'WeitiaoW3Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW3Fragment:148', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w3fragment_lumbar_down', 'LUMBAR down', 'WeitiaoW3Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW3Fragment:161', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w3fragment_legs_up', 'LEG up', 'WeitiaoW3Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW3Fragment:175', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w3fragment_legs_down', 'LEG down', 'WeitiaoW3Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW3Fragment:188', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w3fragment_back_legsxunhuan', 'BACK/LEG CYCLE', 'WeitiaoW3Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW3Fragment:249', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w3fragment_air_fullgxunhuan', 'FULL CYCLE', 'WeitiaoW3Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW3Fragment:255', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w3fragment_legsxunhuan', 'LEG CYCLE', 'WeitiaoW3Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW3Fragment:261', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w3fragment_lumbarxunhuan', 'LUMBAR CYCLE', 'WeitiaoW3Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW3Fragment:267', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w4fragment_sync', 'Sync', 'WeitiaoW4Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW4Fragment:47', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('WeitiaoW4Fragment:49', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('weitiao_w4fragment_back_up', 'BACK up', 'WeitiaoW4Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW4Fragment:58', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w4fragment_stop', 'Stop', 'WeitiaoW4Fragment', 'home', 'stop', (
        MotionBedPacket('WeitiaoW4Fragment:62', None, True, None, ''),
        MotionBedPacket('WeitiaoW4Fragment:75', None, True, None, ''),
        MotionBedPacket('WeitiaoW4Fragment:89', None, True, None, ''),
        MotionBedPacket('WeitiaoW4Fragment:102', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w4fragment_back_down', 'BACK down', 'WeitiaoW4Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW4Fragment:71', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w4fragment_legs_up', 'LEG up', 'WeitiaoW4Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW4Fragment:85', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w4fragment_legs_down', 'LEG down', 'WeitiaoW4Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW4Fragment:98', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w6fragment_sync', 'Sync', 'WeitiaoW6Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW6Fragment:47', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('WeitiaoW6Fragment:49', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('weitiao_w6fragment_back_up', 'BACK up', 'WeitiaoW6Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW6Fragment:58', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w6fragment_stop', 'Stop', 'WeitiaoW6Fragment', 'home', 'stop', (
        MotionBedPacket('WeitiaoW6Fragment:62', None, True, None, ''),
        MotionBedPacket('WeitiaoW6Fragment:75', None, True, None, ''),
        MotionBedPacket('WeitiaoW6Fragment:89', None, True, None, ''),
        MotionBedPacket('WeitiaoW6Fragment:102', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w6fragment_back_down', 'BACK down', 'WeitiaoW6Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW6Fragment:71', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w6fragment_wholelift_up', 'LIFT up', 'WeitiaoW6Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW6Fragment:85', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w6fragment_wholelift_down', 'LIFT down', 'WeitiaoW6Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW6Fragment:98', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w7fragment_sync', 'Sync', 'WeitiaoW7Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW7Fragment:76', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('WeitiaoW7Fragment:78', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('weitiao_w7fragment_split_back_left_up', 'BACK up', 'WeitiaoW7Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW7Fragment:89', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w7fragment_stop', 'Stop', 'WeitiaoW7Fragment', 'home', 'stop', (
        MotionBedPacket('WeitiaoW7Fragment:93', None, True, None, ''),
        MotionBedPacket('WeitiaoW7Fragment:106', None, True, None, ''),
        MotionBedPacket('WeitiaoW7Fragment:120', None, True, None, ''),
        MotionBedPacket('WeitiaoW7Fragment:133', None, True, None, ''),
        MotionBedPacket('WeitiaoW7Fragment:147', None, True, None, ''),
        MotionBedPacket('WeitiaoW7Fragment:160', None, True, None, ''),
        MotionBedPacket('WeitiaoW7Fragment:174', None, True, None, ''),
        MotionBedPacket('WeitiaoW7Fragment:187', None, True, None, ''),
        MotionBedPacket('WeitiaoW7Fragment:201', None, True, None, ''),
        MotionBedPacket('WeitiaoW7Fragment:214', None, True, None, ''),
        MotionBedPacket('WeitiaoW7Fragment:228', None, True, None, ''),
        MotionBedPacket('WeitiaoW7Fragment:241', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w7fragment_split_back_left_down', 'BACK down', 'WeitiaoW7Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW7Fragment:102', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w7fragment_split_back_right_up', 'BACK up', 'WeitiaoW7Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW7Fragment:116', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w7fragment_split_back_right_down', 'BACK down', 'WeitiaoW7Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW7Fragment:129', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w7fragment_split_legs_left_up', 'Split Legs Left up', 'WeitiaoW7Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW7Fragment:143', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w7fragment_split_legs_left_down', 'Split Legs Left down', 'WeitiaoW7Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW7Fragment:156', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w7fragment_split_legs_right_up', 'Split Legs Right up', 'WeitiaoW7Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW7Fragment:170', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w7fragment_split_legs_right_down', 'Split Legs Right down', 'WeitiaoW7Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW7Fragment:183', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w7fragment_coupled_back_up', 'BACK up', 'WeitiaoW7Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW7Fragment:197', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w7fragment_coupled_back_down', 'BACK down', 'WeitiaoW7Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW7Fragment:210', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w7fragment_coupled_legs_up', 'LEG up', 'WeitiaoW7Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW7Fragment:224', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w7fragment_coupled_legs_down', 'LEG down', 'WeitiaoW7Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW7Fragment:237', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w8fragment_sync', 'Sync', 'WeitiaoW8Fragment', 'home', 'press', (
        MotionBedPacket('WeitiaoW8Fragment:75', 'sync_enabled', True, None, 'selected'),
        MotionBedPacket('WeitiaoW8Fragment:77', 'sync_enabled', False, None, 'unselected'),
    )),
    MotionBedAction('weitiao_w8fragment_split_back_left_up', 'BACK up', 'WeitiaoW8Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW8Fragment:88', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w8fragment_stop', 'Stop', 'WeitiaoW8Fragment', 'home', 'stop', (
        MotionBedPacket('WeitiaoW8Fragment:92', None, True, None, ''),
        MotionBedPacket('WeitiaoW8Fragment:105', None, True, None, ''),
        MotionBedPacket('WeitiaoW8Fragment:119', None, True, None, ''),
        MotionBedPacket('WeitiaoW8Fragment:132', None, True, None, ''),
        MotionBedPacket('WeitiaoW8Fragment:146', None, True, None, ''),
        MotionBedPacket('WeitiaoW8Fragment:159', None, True, None, ''),
        MotionBedPacket('WeitiaoW8Fragment:173', None, True, None, ''),
        MotionBedPacket('WeitiaoW8Fragment:186', None, True, None, ''),
        MotionBedPacket('WeitiaoW8Fragment:200', None, True, None, ''),
        MotionBedPacket('WeitiaoW8Fragment:213', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w8fragment_split_back_left_down', 'BACK down', 'WeitiaoW8Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW8Fragment:101', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w8fragment_split_back_right_up', 'BACK up', 'WeitiaoW8Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW8Fragment:115', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w8fragment_split_back_right_down', 'BACK down', 'WeitiaoW8Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW8Fragment:128', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w8fragment_split_legs_up', 'LEG up', 'WeitiaoW8Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW8Fragment:142', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w8fragment_split_legs_down', 'LEG down', 'WeitiaoW8Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW8Fragment:155', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w8fragment_coupled_back_up', 'BACK up', 'WeitiaoW8Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW8Fragment:169', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w8fragment_coupled_back_down', 'BACK down', 'WeitiaoW8Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW8Fragment:182', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w8fragment_coupled_legs_up', 'LEG up', 'WeitiaoW8Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW8Fragment:196', None, True, None, ''),
    )),
    MotionBedAction('weitiao_w8fragment_coupled_legs_down', 'LEG down', 'WeitiaoW8Fragment', 'home', 'held', (
        MotionBedPacket('WeitiaoW8Fragment:209', None, True, None, ''),
    )),
)

ACTION_BY_KEY = {action.key: action for action in MOTION_BED_ACTIONS}
