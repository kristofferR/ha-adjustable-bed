"""Richmat MH app profiles (APK audit row055, cluster-020): artifact vectors and behavior."""

from __future__ import annotations

import asyncio
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed import richmat_mh_catalog as catalog
from custom_components.adjustable_bed.beds import richmat_mh_protocol as protocol
from custom_components.adjustable_bed.beds.richmat_mh import (
    ALARM_OPTIONS,
    APP_GROUPS,
    RichmatMhController,
    SessionFlags,
    load_model,
    resolve_model,
    selectable_models,
)
from custom_components.adjustable_bed.const import (
    RICHMAT_MH_APPS,
    RICHMAT_MH_MODEL_CHOICES,
    RICHMAT_MH_VARIANTS_BY_APP,
)

NUS, W1, W2, W3, W4 = protocol.GATT_MAPS


def _char(uuid: str, *properties: str) -> SimpleNamespace:
    return SimpleNamespace(uuid=uuid, properties=list(properties), handle=1)


def _service(uuid: str, *chars: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(uuid=uuid, characteristics=list(chars))


def _default_services(write_props: tuple[str, ...] = ("write",)) -> list[SimpleNamespace]:
    return [_service(W1[0], _char(W1[1], *write_props), _char(W1[2], "notify"))]


def make(
    app: str = "revive",
    name: str | None = "7IRM1234",
    *,
    variant: str | None = None,
    snapshot: dict | None = None,
    services: list[SimpleNamespace] | None = None,
) -> RichmatMhController:
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 3
    coordinator.controller_state = {}
    coordinator.handle_controller_state_update.side_effect = lambda key, value: (
        coordinator.controller_state.update({key: value})
    )
    coordinator.handle_controller_state_updates.side_effect = coordinator.controller_state.update
    data = {"capabilities": {"richmat_mh": snapshot}} if snapshot else {}
    coordinator.entry = SimpleNamespace(data=data)
    coordinator.client = MagicMock(is_connected=True, services=services or _default_services())
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    return RichmatMhController(coordinator, app=app, protocol_variant=variant, device_name=name)


def vers1(model: str, **dev: bool) -> dict:
    return {"model": model, "version": "0001", "call_page": True, "dev": dev}


def vers0(model: str, **dev: bool) -> dict:
    return {"model": model, "version": "0000", "call_page": False, "dev": dev}


def frames(controller: RichmatMhController) -> list[str]:
    return [bytes(c.args[1]).hex() for c in controller.client.write_gatt_char.call_args_list]


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record every requested delay without waiting on a real timer."""
    recorded: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay: float, result: object = None) -> object:
        recorded.append(round(delay, 3))
        await real_sleep(0)
        return result

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return recorded


# ------------------------------------------------------------- artifact vectors


@pytest.mark.parametrize(
    ("frame", "expected"),
    [
        (protocol.control_frame(0x31), "6e010031a0"),  # FLAT
        (protocol.control_frame(0x24), "6e01002493"),  # HEAD_UP
        (protocol.control_frame(0x45), "6e010045b4"),  # ZG recall
        (protocol.stop_frame(), "6e01006edd"),
        (protocol.stop_frame(1), "6e01016ede"),
        (protocol.stop_frame(2), "6e01026edf"),
        (protocol.query_frame(protocol.TX_MATTRESS), "5e1a000179"),
        (protocol.query_frame(protocol.TX_VERSION), "6e9a000008"),
        (protocol.query_frame(protocol.TX_START_DETECTION), "6e88c210c8"),
        (protocol.query_frame(protocol.TX_STOP_DETECTION), "6e88c220d8"),
        (protocol.rgb_frame(128, 1, 255), "6e0cff80f96e0d01ff7b"),
        (protocol.light_timer_frame(300), "6e0b012ca6"),  # LedFrag 300 s
        (protocol.light_timer_frame(15 * 60), "6e0b038400"),  # Blvd Home BtnLedFrag 15 min
        (protocol.light_timer_frame(0), "6e0bffff77"),
        (protocol.light_timer_frame(300, mode_byte=0), "6e0b002ca5"),  # dead LedCallFrag variant
        (protocol.motor_mode_frame(1), "6e8814000a"),
        (protocol.motor_mode_frame(2), "6e8818000e"),
        (protocol.aroma_frame(0x1B, 5), "6e1b05008e"),
        (protocol.aroma_frame(0x1C, 60), "6e1c3c00c6"),
        (protocol.aroma_frame(0x1D, 1), "6e1d01008c"),
        (protocol.snore_frame(0x46), "6e130046c7"),
        (protocol.snore_frame(0), "6e13000081"),
        (protocol.angle_frame(0, 35), "6e88302349"),
        (protocol.angle_frame(1, 30), "6e88341e48"),  # Idealbed A01
        (protocol.angle_frame(3, 25), "6e883c194b"),
        (protocol.massage_intensity_frame(head=3, foot=7), "6e88a03bd1"),  # Idealbed A03
        (protocol.motor_mode_frame(3), "6e881c0012"),  # Idealbed A02
        (protocol.rgb_frame(17, 34, 51), "6e0cff118a6e0d2233d0"),  # Idealbed A04
        (protocol.light_timer_frame(291), "6e0b01239d"),  # Idealbed A05
        (protocol.aroma_frame(0x1B, 60), "6e1b3c00c5"),  # Idealbed A07
        (protocol.control_frame(protocol.SMART_SET_LOCK_CODE), "6e010084f3"),
        (protocol.control_frame(protocol.BTN_LED_OFF_CODE), "6e010075e4"),
    ],
)
def test_frame_builders_match_artifact_vectors(frame: bytes, expected: str) -> None:
    assert frame.hex() == expected


@pytest.mark.parametrize(
    ("minutes", "action", "expected"),
    [
        (1, 0x7A, ("6e05010074", "6e06007aee")),  # TV + head massage
        (1440, 0x7A, ("6e05a00013", "6e06057af3")),
        (1, 0x7D, ("6e05010074", "6e06007df1")),
        (1, 0x77, ("6e05010074", "6e060077eb")),
    ],
)
def test_alarm_frames_match_artifact_vectors(minutes, action, expected) -> None:
    assert tuple(f.hex() for f in protocol.alarm_frames(minutes, action)) == expected


def test_alarm_cancel_delete_and_clock_frames() -> None:
    assert tuple(protocol.query_frame(t).hex() for t in protocol.TX_ALARM_CANCEL) == (
        "6e05000073", "6e06000074"
    )
    assert tuple(f.hex() for f in protocol.alarm_delete_frames(2)) == ("6e05000275", "6e06000074")
    assert tuple(f.hex() for f in protocol.alarm_frames(61, 0x2F, 3)) == ("6e053d03b3", "6e06002fa3")
    assert tuple(f.hex() for f in protocol.clock_frames(7, 5, 9)) == ("6e1307058d", "6e1409ff8a")


@pytest.mark.parametrize(
    ("target", "now", "expected"),
    [(420, 420, 1440), (421, 420, 1), (419, 420, 1439), (0, 1439, 1), (1439, 0, 1439)],
)
def test_alarm_countdown_is_the_apps_wrapping_difference(target, now, expected) -> None:
    assert protocol.alarm_countdown_minutes(target, now) == expected


def test_alarm_combinations_two_massages_and_unmatched_pairs() -> None:
    assert len(protocol.ALARM_COMBINATIONS) == 21
    assert protocol.alarm_action(0x58, (0x4C,)) == 0x7A
    assert protocol.alarm_action(0x30, (0x4C, 0x4E)) == 0xA9  # two massages -> BOTH_ON
    assert protocol.alarm_action(None, (0x4C, 0x4E)) == 0x5D
    assert protocol.alarm_action(0x2E, ()) == 0x2E
    assert protocol.alarm_action(0xB0, (0x4C,)) is None  # the app writes nothing
    assert protocol.alarm_action(0x45, (0x34,)) is None


# ------------------------------------------------------------- catalog / models


def test_every_offered_model_loads_and_variants_follow_the_pickers() -> None:
    for bed_type, app in RICHMAT_MH_APPS.items():
        assert app in APP_GROUPS, bed_type
        for model in selectable_models(app):
            assert load_model(app, model) is not None, (app, model)
        expected = {"auto", *(f"model_{m}" for m, _label in RICHMAT_MH_MODEL_CHOICES[app])}
        assert set(RICHMAT_MH_VARIANTS_BY_APP[app]) == expected
    assert set(selectable_models("idealbed")) == set(catalog.MODELS["idealbed"])


def test_catalog_controls_are_well_formed() -> None:
    for control in catalog.CONTROLS:
        route, kind, area, _group, _label, code, keep_ms = control
        assert route in ("L", "C", "B") and 0 <= code <= 0xFF
        if area == "motor":
            assert kind in ("up", "down") and keep_ms > 0
        else:
            assert kind in ("recall", "save", "press")
        if route == "B":
            # Route B rows are the button-light page OFF (only Revive and Best Mattress emit one).
            assert (area, code, keep_ms) == ("btn_led", protocol.BTN_LED_OFF_CODE, 0)


@pytest.mark.parametrize(
    ("app", "variant", "name", "expected"),
    [
        ("revive", None, "7IRM-0001", ("7irm", None)),
        ("revive", None, "QRRM0001", (None, "choose_model")),
        ("revive", None, "Cool Touch 1", (None, "unknown_model")),
        ("idealbed", None, "Cool Touch 1", (None, "choose_model")),
        ("idealbed", None, "Cool Tou", (None, "unknown_model")),
        ("revive", None, "abc", (None, "no_name")),
        ("revive", None, None, (None, "no_name")),
        ("revive", "model_vorm", "7IRM0001", ("vorm", None)),
        ("revive", "model_7irm", "anything", (None, "unknown_model")),  # not on a picker
        ("best_mattress", None, "VORM0001", ("vorm", None)),
        ("blvd_home", "model_eorm", None, ("eorm", None)),
        # Idealbed's manual dialog accepts any valid identifier, not just its short IDs.
        ("idealbed", "model_fhrm", "Cool Touch 1", ("fhrm", None)),
        ("idealbed", "model_4it", None, ("4it", None)),
        ("idealbed", "model_qrrm", None, (None, "unknown_model")),  # the dead marker class
    ],
)
def test_model_resolution_follows_the_app(app, variant, name, expected) -> None:
    assert resolve_model(app, variant, name) == expected


async def test_unresolved_name_is_rejected_at_discovery() -> None:
    controller = make(name="QRRM0001")
    with pytest.raises(ValueError, match="asking for the model"):
        await controller.async_discover_capabilities()
    assert frames(controller) == []


@pytest.mark.parametrize("app", sorted(APP_GROUPS))
def test_every_model_builds_unique_entities_on_both_routes(app: str) -> None:
    """Table-driven over every catalog model, with every page reply present."""
    all_dev = {"alarm": True, "led": True, "aroma": True, "snore": True}
    for model in catalog.MODELS[app]:
        for snapshot in (vers0(model, **all_dev), vers1(model, **all_dev)):
            controller = make(app, f"{model}0000" if len(model) == 4 else None,
                              variant=None if len(model) == 4 else f"model_{model}",
                              snapshot=snapshot)
            if controller.model is None:
                continue  # short identifiers outside the app's manual route
            buttons = [spec.key for spec in controller.controller_button_specs]
            assert len(buttons) == len(set(buttons)), (app, model)
            numbers = [spec.key for spec in controller.controller_number_specs]
            assert len(numbers) == len(set(numbers)), (app, model)
            covers = [spec.key for spec in controller.motor_control_specs]
            assert len(covers) == len(set(covers)), (app, model)


async def test_sampled_models_press_every_button_with_the_catalog_frame(sleeps) -> None:
    rng = random.Random(55)
    for app in sorted(APP_GROUPS):
        for model in rng.sample(sorted(m for m in catalog.MODELS[app] if len(m) == 4), 6):
            controller = make(app, f"{model}0000", snapshot=vers0(model))
            await controller.async_discover_capabilities()
            for spec in controller.controller_button_specs:
                controller.client.write_gatt_char.reset_mock()
                await spec.press_fn(controller)
                code = int(spec.key.removeprefix("richmat_mh_"), 16)
                assert frames(controller) == [protocol.control_frame(code).hex(), "6e01006edd"]


# --------------------------------------------------------------------- transport


async def test_first_known_service_wins_and_fallback_takes_last_writable() -> None:
    controller = make(services=[
        _service("00001800-0000-1000-8000-00805f9b34fb", _char("2a00", "write")),
        _service("0000abcd-0000-1000-8000-00805f9b34fb",
                 _char("a1", "write"), _char("a2", "notify"), _char("a3", "write"),
                 _char("a4", "indicate")),
        _service(W3[0], _char(W3[1], "write"), _char(W3[2], "notify")),  # complete, later map
        _service(W1[0], _char(W1[1], "read"), _char(W1[2], "read")),  # no usable role
    ])
    await controller.async_discover_capabilities()
    # The app stops at W1 (incomplete), then falls back to the first non-GAP service.
    assert controller.control_characteristic_uuid == "a3"
    assert [c.uuid for c in controller._notify_chars] == ["a2", "a4"]


async def test_fallback_keeps_the_known_services_partial_roles() -> None:
    controller = make(services=[
        _service("0000abcd-0000-1000-8000-00805f9b34fb", _char("a1", "notify")),
        _service(W1[0], _char(W1[1], "write"), _char(W1[2], "read")),
    ])
    await controller.async_discover_capabilities()
    assert controller.control_characteristic_uuid == W1[1]
    assert [c.uuid for c in controller._notify_chars] == ["a1"]


async def test_known_service_missing_a_fixed_characteristic_fails_like_the_app() -> None:
    controller = make(services=[
        _service("0000abcd-0000-1000-8000-00805f9b34fb", _char("a1", "write"), _char("a2", "notify")),
        _service(W1[0], _char(W1[1], "write")),
    ])
    with pytest.raises(ValueError, match="fixed characteristics"):
        await controller.async_discover_capabilities()


@pytest.mark.parametrize(("props", "response"), [(("write",), True), (("write-without-response",), False)])
async def test_write_type_follows_the_characteristic(props, response) -> None:
    controller = make(services=_default_services(props))
    await controller.async_discover_capabilities()
    await controller.stop_all()
    assert controller.client.write_gatt_char.call_args.kwargs["response"] is response


async def test_session_queries_version_then_ver1_list_and_persists_snapshot(sleeps) -> None:
    controller = make()
    await controller.async_discover_capabilities()
    replies = {"6e9a000008": "6e900001ff", "6e08010178": "6e09010179", "6e0a000179": "6e0e00037f"}

    async def write(char, data, response):
        reply = replies.get(bytes(data).hex())
        if reply:
            controller._handle_notification(char, bytearray.fromhex(reply))

    controller.client.write_gatt_char.side_effect = write
    await controller.start_notify()
    assert controller._init_task is not None
    await controller._init_task
    sent = frames(controller)
    assert sent[0] == "6e9a000008"
    queries = [protocol.query_frame(t).hex() for t in protocol.INIT_VER1]
    # The alarm reply mounts AlarmCallFrag, which sends the clock before the next query.
    assert sent[1:3] == queries[:2]
    assert sent[3][:4] == "6e13" and sent[4][:4] == "6e14"
    assert sent[5:] == queries[2:]
    assert sleeps == [0.3] * 17
    # VER1 keeps only the last reply's flag (the LED reply came after the alarm).
    assert controller.capability_snapshot() == {
        "model": "7irm", "version": "0001", "call_page": True,
        "dev": {"alarm": False, "aroma": False, "led": True, "mattress": False, "speech": False},
        "detection": False, "waist": False,
    }
    controller._coordinator.remember_richmat_mh_snapshot.assert_called_once()


async def test_session_without_version_reply_uses_the_ver0_list(sleeps) -> None:
    controller = make("best_mattress", "VORM0001")
    await controller.async_discover_capabilities()
    await controller.start_notify()
    assert controller._init_task is not None
    await controller._init_task
    assert frames(controller)[1:] == [protocol.query_frame(t).hex() for t in protocol.INIT_VER0]
    assert controller.route == "L"


async def test_hold_repeats_at_the_control_interval_then_stops_120ms_later(sleeps) -> None:
    controller = make(snapshot=vers1("7irm"))
    await controller.async_discover_capabilities()
    await controller.move_axis("head", "up")
    assert frames(controller) == ["6e01002493"] * 3 + ["6e01006edd"]
    assert sleeps[-1] == 0.12


async def test_release_stop_is_sent_when_the_hold_is_cancelled() -> None:
    controller = make(snapshot=vers1("7irm"))
    await controller.async_discover_capabilities()
    entered = asyncio.Event()

    async def write(char, data, response):
        if bytes(data) != protocol.stop_frame():
            entered.set()
            await asyncio.Event().wait()

    controller.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(controller.move_axis("head", "up"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(controller)[-1] == "6e01006edd"
    assert not controller.ble_lock.locked()


async def test_cancel_during_the_release_stop_write_still_completes_it(sleeps) -> None:
    controller = make(snapshot=vers1("7irm"))
    await controller.async_discover_capabilities()
    in_stop, finish = asyncio.Event(), asyncio.Event()
    completed: list[str] = []

    async def write(char, data, response):
        if bytes(data) == protocol.stop_frame():
            in_stop.set()
            await finish.wait()
            completed.append(bytes(data).hex())

    controller.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(controller.tap(0x45))
    await in_stop.wait()
    task.cancel()
    await asyncio.sleep(0)
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert completed == ["6e01006edd"]


# ---------------------------------------------------------------- notifications


def test_classifier_splits_version_init_and_callback_families() -> None:
    revive, legacy = protocol.Classifier("revive"), protocol.Classifier("legacy")
    assert revive.feed(bytes.fromhex("6e900001ff")) == [protocol.Event("version", "0001")]
    assert revive.feed(bytes.fromhex("6e23a06e9f")) == [protocol.Event("init", "6e23a06e9f")]
    legacy.rx_type = "INIT"
    assert legacy.feed(bytes.fromhex("6e23a06e9f")) == [protocol.Event("init", "6e23a06e9f")]
    legacy.rx_type = "NONE"
    assert legacy.feed(bytes.fromhex("6e23a06e9f")) == []


def test_classifier_detection_and_state_replies() -> None:
    c = protocol.Classifier("revive", rx_type="INIT")
    assert c.feed(bytes.fromhex("6e90c101c0"))[0].kind == "detection_available"
    assert c.feed(bytes.fromhex("6e90c210d0"))[0].kind == "detection_started"
    result = c.feed(bytes.fromhex("6e90c311d2"))[0]
    assert (result.kind, result.extra) == ("detection_result", ("3", "1", "1"))
    angle = c.feed(bytes.fromhex("6e90342355"))[0]  # motor 01, 35 degrees
    assert (angle.kind, angle.data, angle.extra) == ("motor_angle", "01", ("35",))
    massage = c.feed(bytes.fromhex("6e90a00ba9"))[0]
    assert massage.kind == "massage" and int(massage.data[9:12], 2) == 3
    assert c.feed(bytes.fromhex("6e90402e6c")) == [protocol.Event("memory_arrival", "2e")]


async def test_legacy_init_replies_open_pages_and_snore_prefix_is_ver0_only() -> None:
    controller = make("revive", "CFRM0001")
    controller._classifier.rx_type = "INIT"
    controller._handle_notification(None, bytearray.fromhex("6e09010078"))
    assert controller._dev == {}  # outside a setup session, replies change nothing
    session = controller._pending = SessionFlags()
    for reply in ("6e09010078", "6e0e00037f", "6e21010090", "6e90c101c0"):
        controller._handle_notification(None, bytearray.fromhex(reply))
    assert session.dev == {"alarm": True, "led": True, "snore": True}
    assert session.detection is True
    assert controller._dev == {} and controller._detection is False  # published on completion


# ------------------------------------------------------------------- features


async def test_legacy_alarm_combines_position_and_massage(sleeps) -> None:
    controller = make("revive", "O9RM0001", snapshot=vers0("o9rm", alarm=True))
    await controller.async_discover_capabilities()
    assert controller.richmat_mh_alarm_positions == (
        "tv", "zero_g", "lounge", "memory_1", "memory_2", "head_massage", "foot_massage"
    )
    assert controller.richmat_mh_alarm_massages == ("head_massage", "foot_massage")
    await controller.richmat_mh_alarm(
        enabled=True, minutes=61, position="tv", massage=["foot_massage", "head_massage"], slot=None
    )
    assert frames(controller) == ["6e053d00b0", "6e060077eb"]  # TV + both -> 77
    assert sleeps == [0.3]
    assert controller._classifier.rx_type == "ALARM"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"position": "yoga", "massage": []}, "not on this model"),
        ({"position": None, "massage": []}, "position or a massage"),
        ({"position": "memory_1", "massage": ["heat"]}, "distinct options"),
        ({"position": "head_massage", "massage": ["foot_massage"]}, "sends nothing"),
    ],
)
async def test_alarm_requests_the_app_cannot_send_are_rejected(kwargs, message) -> None:
    controller = make("revive", "O9RM0001", snapshot=vers0("o9rm", alarm=True))
    with pytest.raises(ValueError, match=message):
        controller.validate_richmat_mh_alarm(enabled=True, slot=None, **kwargs)


async def test_alarm_cancel_and_page_gate(sleeps) -> None:
    hidden = make("revive", "O9RM0001", snapshot=vers0("o9rm"))
    assert not hidden.supports_richmat_mh_alarm
    controller = make("revive", "O9RM0001", snapshot=vers0("o9rm", alarm=True))
    await controller.async_discover_capabilities()
    await controller.richmat_mh_alarm(enabled=False, minutes=0, position=None, massage=[], slot=None)
    assert frames(controller) == ["6e05000073", "6e06000074"]


async def test_multi_slot_alarm_uses_slot_memory_and_150ms_spacing(sleeps) -> None:
    controller = make(snapshot=vers1("7irm", alarm=True))
    await controller.async_discover_capabilities()
    with pytest.raises(ValueError, match="choose a slot"):
        controller.validate_richmat_mh_alarm(enabled=True, position=None, massage=[], slot=None)
    await controller.richmat_mh_alarm(enabled=True, minutes=1440, position=None, massage=[], slot=2)
    await controller.richmat_mh_alarm(enabled=False, minutes=0, position=None, massage=[], slot=2)
    assert frames(controller) == ["6e05a00215", "6e06052fa8", "6e05000275", "6e06000074"]
    assert sleeps == [0.15, 0.15]


async def test_alarm_confirmations_publish_status() -> None:
    controller = make("revive", "O9RM0001", snapshot=vers0("o9rm", alarm=True))
    controller._classifier.rx_type = "ALARM"
    controller._handle_notification(None, bytearray.fromhex("6e07010177"))
    assert controller._coordinator.controller_state["richmat_mh_alarm"] == "set"


async def test_aroma_triplet_with_150ms_task_sleeps(sleeps) -> None:
    controller = make("revive", "UYRM0001", snapshot=vers0("uyrm", aroma=True))
    await controller.async_discover_capabilities()
    await controller.richmat_mh_aroma(5, 60, 1)
    assert frames(controller) == ["6e1b05008e", "6e1c3c00c6", "6e1d01008c"]
    assert sleeps == [0.15, 0.15]
    with pytest.raises(ValueError, match="1-60"):
        await controller.richmat_mh_aroma(0, 1, 1)
    assert not make("revive", "UYRM0001", snapshot=vers0("uyrm")).supports_richmat_mh_aroma


async def test_snore_select_writes_mode_rewritten_frame_and_follows_callback() -> None:
    controller = make("revive", "CFRM0001", snapshot=vers0("cfrm"))
    await controller.async_discover_capabilities()
    (select,) = [s for s in controller.controller_select_specs if s.key == "richmat_mh_snore"]
    assert select.options == ("off", "anti_snore", "zero_g")
    await select.select_fn(controller, "anti_snore")
    await select.select_fn(controller, "off")
    assert frames(controller) == ["6e130046c7", "6e13000081"]
    controller._handle_notification(None, bytearray.fromhex("6e234521f7"))
    assert controller._coordinator.controller_state["richmat_mh_snore"] == "zero_g"
    # Other apps need the snore reply first.
    assert not make("harmony", "CFRM0001", snapshot=vers0("cfrm")).controller_select_specs
    assert make("harmony", "CFRM0001", snapshot=vers0("cfrm", snore=True)).controller_select_specs


async def test_led_page_colour_and_timer() -> None:
    controller = make("revive", "CFRM0001", snapshot=vers0("cfrm"))
    await controller.async_discover_capabilities()
    assert controller.supports_light_color_control and controller.supported_color_mode == "rgb"
    assert controller.supports_light_toggle_control  # motor-page light icon
    (timer,) = controller.controller_number_specs
    assert (timer.key, timer.native_max_value, timer.native_unit_of_measurement) == (
        "richmat_mh_light_timer", 300, "s"
    )
    await controller.set_light_color((128, 1, 255))
    await timer.set_fn(controller, 300)
    await timer.set_fn(controller, 0)
    assert frames(controller) == ["6e0cff80f96e0d01ff7b", "6e0b012ca6", "6e0bffff77"]
    # HARMONY adds the LED page only after the LED reply.
    assert not make("harmony", "CFRM0001", snapshot=vers0("cfrm")).supports_light_color_control


async def test_button_light_page_off_and_blvd_minutes(sleeps) -> None:
    controller = make("blvd_home", "GARM0001", snapshot=vers0("garm"))
    await controller.async_discover_capabilities()
    (timer,) = controller.controller_number_specs
    assert (timer.key, timer.native_max_value) == ("richmat_mh_light_timer_minutes", 15)
    await timer.set_fn(controller, 15)
    assert frames(controller) == ["6e0b038400"]
    revive = make("revive", "GARM0001", snapshot=vers0("garm"))
    await revive.async_discover_capabilities()
    assert revive.controller_number_specs[0].native_max_value == 300
    off = next(s for s in revive.controller_button_specs if s.key == "richmat_mh_75")
    await off.press_fn(revive)
    assert frames(revive) == ["6e010075e4", "6e01006edd"]


@pytest.mark.parametrize(
    ("app", "model", "has_off"),
    [
        ("revive", "garm", True),
        ("best_mattress", "vsrm", True),
        ("harmony", "garm", False),  # A003-UNPROMOTED-UBL_OFF: dead
        ("blvd_home", "garm", False),  # no emission row
        ("idealbed", "fhrm", False),  # no emission row
    ],
)
def test_button_light_off_exists_only_where_the_app_emits_it(app, model, has_off) -> None:
    controller = make(app, f"{model.upper()}0001", snapshot=vers0(model, led=True))
    assert controller._light_page() == "btn_led"
    keys = {spec.key for spec in controller.controller_button_specs}
    assert ("richmat_mh_75" in keys) is has_off


async def test_smart_set_lock_toggle_and_callback_state() -> None:
    controller = make("revive", "CFRM0001", snapshot=vers0("cfrm"))
    await controller.async_discover_capabilities()
    toggle = next(s for s in controller.controller_button_specs if s.key == "richmat_mh_toggle_smart_set_lock")
    await toggle.press_fn(controller)
    assert frames(controller) == ["6e010084f3"]  # once, no STOP
    controller._classifier.rx_type = "INIT"
    controller._handle_notification(None, bytearray.fromhex("6e23008415"))
    assert controller._coordinator.controller_state["richmat_mh_smart_set_lock"] is True
    assert [s.key for s in controller.controller_state_binary_sensor_specs] == [
        "richmat_mh_smart_set_lock", "richmat_mh_smart_light_lock"
    ]
    controller._handle_notification(None, bytearray.fromhex("6e23010a9c"))  # light page unlocked
    assert controller._coordinator.controller_state["richmat_mh_smart_light_lock"] is False


async def test_detection_buttons_status_and_results() -> None:
    controller = make("revive", "CFRM0001", snapshot={**vers0("cfrm"), "detection": True})
    await controller.async_discover_capabilities()
    start = next(s for s in controller.controller_button_specs if s.key == "richmat_mh_start_detection")
    await start.press_fn(controller)
    assert frames(controller) == ["6e88c210c8"]
    controller._classifier.rx_type = "INIT"
    for reply in ("6e90c210d0", "6e90c311d2", "6e90c410d2"):
        controller._handle_notification(None, bytearray.fromhex(reply))
    state = controller._coordinator.controller_state
    assert state["richmat_mh_detection"] == "running"
    assert state["richmat_mh_detection_results"] == {"motor_1": "pass", "massager_1": "error"}


async def test_ver1_angles_wait_100ms_and_follow_replies(sleeps) -> None:
    controller = make(snapshot=vers1("7irm"))
    await controller.async_discover_capabilities()
    numbers = {s.key: s for s in controller.controller_number_specs}
    assert {k: (s.native_min_value, s.native_max_value) for k, s in numbers.items()} == {
        "richmat_mh_back_angle": (0, 70), "richmat_mh_foot_angle": (0, 45),
        "richmat_mh_pillow_angle": (0, 25), "richmat_mh_head_massage_intensity": (0, 7),
        "richmat_mh_foot_massage_intensity": (0, 7),
    }
    await numbers["richmat_mh_pillow_angle"].set_fn(controller, 25)
    assert frames(controller) == ["6e883c194b"] and sleeps == [0.1]
    controller._handle_notification(None, bytearray.fromhex("6e9034ff31"))
    assert controller._coordinator.controller_state["richmat_mh_foot_angle"] == 0  # -1 clamps to 0


async def test_ver1_massage_intensity_sends_both_zones() -> None:
    controller = make(snapshot=vers1("7irm"))
    await controller.async_discover_capabilities()
    numbers = {s.key: s for s in controller.controller_number_specs}
    await numbers["richmat_mh_head_massage_intensity"].set_fn(controller, 3)
    controller._handle_notification(None, bytearray.fromhex("6e90a02dcb"))  # foot 5, head 5
    await numbers["richmat_mh_head_massage_intensity"].set_fn(controller, 3)
    assert frames(controller) == ["6e88a00399", "6e88a02bc1"]


async def test_ver1_motor_mode_and_memory_arrival() -> None:
    controller = make(snapshot=vers1("7irm"))
    await controller.async_discover_capabilities()
    (mode,) = controller.controller_select_specs
    assert mode.options == ("mode1", "mode2", "mode3")
    await mode.select_fn(controller, "mode3")
    assert frames(controller) == ["6e881c0012"]
    controller._handle_notification(None, bytearray.fromhex("6e90402e6c"))
    assert controller._coordinator.controller_state["richmat_mh_memory_arrival"] == "M1"


@pytest.mark.parametrize("model", ["6hrm", "dirm", "ghrm", "h4rm"])
async def test_idealbed_single_group_motor_modes_keep_both_buttons(model: str) -> None:
    # setMotorModeMap: SINGLE -> arrayListOf(MotorModeType.LEFT.getV(), MotorModeType.RIGHT.getV())
    controller = make("idealbed", f"{model.upper()}0001", snapshot=vers1(model))
    assert controller.motor_mode_options == ("left", "right")
    await controller.async_discover_capabilities()
    await controller.set_motor_mode("right")
    assert frames(controller) == ["6e8818000e"]


def test_effective_constructors_override_the_flattened_annotations() -> None:
    """Reconciliation RA-001: only the executed setters of the pinned flavour count."""
    garm = load_model("idealbed", "garm").features
    assert not (garm.btn_led or garm.snore or garm.snore_list or garm.smart_set_lock or garm.speech)
    assert garm.alarm == (0x2E,)
    assert load_model("idealbed", "ufrm").features.alarm == ()
    assert load_model("idealbed", "uzrm").features.alarm == ()
    hnrm = load_model("blvd_home", "hnrm")
    assert hnrm.features.alarm == (0x45, 0x46, 0x58, 0xF4, 0xF0, 0x86, 0x4C, 0x4E)
    reset = [(c.route, c.kind, c.code, c.keep_ms) for c in hnrm.controls if c.group == "FACTORY_RESET"]
    assert reset == [("L", "recall", 0x62, 0)]


async def test_blvd_hnrm_factory_reset_uses_the_common_widget_frame(sleeps) -> None:
    controller = make("blvd_home", "HNRM0001", snapshot=vers0("hnrm"))
    await controller.async_discover_capabilities()
    reset = next(s for s in controller.controller_button_specs if s.key == "richmat_mh_62")
    await reset.press_fn(controller)
    assert frames(controller) == ["6e010062d1", "6e01006edd"]


def test_legacy_route_has_no_ver1_entities_and_stale_keys_cover_them() -> None:
    controller = make(snapshot=vers0("7irm"))
    assert not controller.controller_number_specs and not controller.controller_select_specs
    assert controller.stale_controller_state_sensor_entity_keys >= {"richmat_mh_memory_arrival"}


def test_alarm_options_are_stable_service_values() -> None:
    assert len(set(ALARM_OPTIONS.values())) == len(ALARM_OPTIONS)
    for app in catalog.MODELS:
        for model in catalog.MODELS[app]:
            features = load_model(app, model).features
            assert set(features.alarm) <= set(ALARM_OPTIONS), (app, model)


@pytest.mark.parametrize("group", ["revive", "legacy"])
@pytest.mark.parametrize(
    ("initial", "rx_type", "received", "expected"),
    [
        ("6e90", "NONE", "0001ff", [protocol.Event("version", "0001")]),  # fragmented version
        ("", "NONE", "6e90398000", [protocol.Event("motor_angle", "10", ("--128",))]),
        ("", "INIT", "6e09010000", []),  # bad init sum clears the buffer
        ("", "ALARM", "6e09010078", [protocol.Event("alarm", "6e09010078")]),
        ("", "NONE", "005e01010363", []),  # leading junk
        ("", "NONE", "5e030403685e030b020303061e98",
         [protocol.Event("waist", "5e03040368"), protocol.Event("waist", "5e030b020303061e98")]),
        ("", "NONE", "5e030403685e030403685e030b020303061e98",
         [protocol.Event("waist", "5e03040368")] * 2 + [protocol.Event("waist", "5e030b020303061e98")]),
    ],
)
def test_notification_artifact_vectors(group, initial, rx_type, received, expected) -> None:
    classifier = protocol.Classifier(group, rx_type=rx_type, buffer=initial)
    assert classifier.feed(bytes.fromhex(received)) == expected


@pytest.mark.parametrize(("group", "kept"), [("revive", ""), ("legacy", "6e13010000")])
def test_bad_snore_sum_is_kept_only_by_the_legacy_decoder(group, kept) -> None:
    classifier = protocol.Classifier(group, rx_type="SNORE")
    assert classifier.feed(bytes.fromhex("6e13010000")) == []
    assert classifier.buffer == kept


def test_angle_reply_with_doubled_minus_is_ignored() -> None:
    controller = make("revive", None, variant="model_4it", snapshot=vers1("4it"))
    controller._handle_notification(None, bytearray.fromhex("6e90398000"))  # motor 10, "--128"
    assert "richmat_mh_pillow_angle" not in controller._coordinator.controller_state
    controller._handle_notification(None, bytearray.fromhex("6e90381400"))  # motor 10, 20
    assert controller._coordinator.controller_state["richmat_mh_pillow_angle"] == 20


async def test_waist_page_state_selects_and_frames() -> None:
    controller = make("idealbed", None, variant="model_4i", snapshot={**vers0("4i"), "waist": True})
    await controller.async_discover_capabilities()
    controller._handle_notification(
        None, bytearray.fromhex("5e1b00010107020303000403050306020703080309020a010b020303061e03")
    )
    state = controller._coordinator.controller_state
    assert state["richmat_mh_waist_mode"] == "both_relax"
    assert (state["richmat_mh_waist_left_heat"], state["richmat_mh_waist_right_pressure"],
            state["richmat_mh_waist_both_duration"]) == ("8_hours", "level_2", "15_minutes")
    assert (state["richmat_mh_waist_both_alarm"], state["richmat_mh_waist_both_alarm_repeat"],
            state["richmat_mh_waist_both_alarm_intensity"]) == ("06:30", "daily", 3)
    selects = {s.key: s for s in controller.controller_select_specs}
    await selects["richmat_mh_waist_both_pressure"].select_fn(controller, "level_2")
    await selects["richmat_mh_waist_both_heat"].select_fn(controller, "8_hours")
    await selects["richmat_mh_waist_mode"].select_fn(controller, "both_relax")
    await selects["richmat_mh_waist_mode"].select_fn(controller, "off")
    assert frames(controller) == ["5e0307026a", "5e03040368", "5e03010769", "5e03010062"]
    controller._handle_notification(None, bytearray.fromhex("5e030b127e"))  # both alarm cancelled
    assert state["richmat_mh_waist_both_alarm"] == "off"


async def test_waist_alarm_save_and_cancel_frames() -> None:
    controller = make("blvd_home", "EERM0001", snapshot={**vers0("eerm"), "waist": True})
    await controller.async_discover_capabilities()
    await controller.richmat_mh_waist_alarm(
        enabled=True, waist_side="both", hour=6, minute=45, now_hour=23, now_minute=59,
        repeat="once", intensity=2,
    )
    await controller.richmat_mh_waist_alarm(
        enabled=False, waist_side="right", hour=0, minute=0, now_hour=0, now_minute=0,
        repeat="once", intensity=1,
    )
    assert frames(controller) == ["5e030b010302062d173bf7", "5e030b117d"]
    assert not make("blvd_home", "EERM0001", snapshot=vers0("eerm")).supports_richmat_mh_waist_alarm


def test_mattress_resync_reproduces_the_absolute_end_helper() -> None:
    c = protocol.Classifier("revive")
    # 7 bytes: no defined length, so the helper scans; the first 5 bytes are a frame.
    assert c.feed(bytes.fromhex("5e030403680000")) == [protocol.Event("waist", "5e03040368")]
    assert c.buffer == ""
    junk = protocol.Classifier("revive")
    assert junk.feed(bytes.fromhex("5e0304036900")) == []  # bad sum: the buffer is kept
    assert junk.buffer == "5e0304036900"


async def test_button_light_colour_is_not_restricted_to_unproven_sectors() -> None:
    revive = make("revive", "GARM0001", snapshot=vers0("garm"))
    await revive.async_discover_capabilities()
    await revive.set_light_color((1, 2, 3))
    assert frames(revive) == [protocol.rgb_frame(1, 2, 3).hex()]


async def test_stored_pages_stay_published_while_the_session_runs() -> None:
    """Platforms are built right after connect; the session must not hide VER1 pages."""
    controller = make(snapshot=vers1("7irm", alarm=True, led=True))
    await controller.async_discover_capabilities()
    hold = asyncio.Event()
    queries = {protocol.query_frame(t).hex() for t in (protocol.TX_VERSION, *protocol.INIT_VER1)}

    async def write(char, data, response):
        if bytes(data).hex() in queries:
            await hold.wait()

    controller.client.write_gatt_char.side_effect = write
    keys = {s.key for s in controller.controller_number_specs}
    starting = asyncio.create_task(controller.start_notify())
    for _ in range(3):
        await asyncio.sleep(0)
    # Mid-session: the stored pages and entities stay in effect.
    assert not starting.done()
    assert {s.key for s in controller.controller_number_specs} == keys
    assert "richmat_mh_back_angle" in keys and controller.motor_mode_options
    assert controller.supports_light_color_control and controller.supports_richmat_mh_alarm
    controller.on_disconnect()  # the link drops mid-session
    await starting  # start_notify returns without raising
    assert controller._pending is None and controller.route == "C"


async def test_start_notify_returns_only_after_the_session_persists(sleeps) -> None:
    """Connection setup owns the session: no command can interleave and the link stays up."""
    controller = make()
    await controller.async_discover_capabilities()
    controller.client.write_gatt_char.side_effect = lambda char, data, response: (
        controller._handle_notification(char, bytearray.fromhex("6e900001ff"))
        if bytes(data).hex() == "6e9a000008" else None
    )
    await controller.start_notify()
    assert controller._init_task is not None and controller._init_task.done()
    assert len(frames(controller)) == 1 + len(protocol.INIT_VER1)
    controller._coordinator.remember_richmat_mh_snapshot.assert_called_once()


async def test_cancelling_connection_setup_cancels_the_session() -> None:
    controller = make()
    await controller.async_discover_capabilities()
    starting = asyncio.create_task(controller.start_notify())
    await asyncio.sleep(0)
    starting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await starting
    assert controller._init_task is not None and controller._init_task.cancelled()
    controller._coordinator.remember_richmat_mh_snapshot.assert_not_called()


async def test_failed_session_keeps_the_stored_snapshot(sleeps) -> None:
    controller = make(snapshot=vers1("7irm", alarm=True))
    await controller.async_discover_capabilities()

    async def write(char, data, response):
        if bytes(data).hex() == protocol.query_frame(protocol.TX_ALARM).hex():
            raise ConnectionError("lost")

    controller.client.write_gatt_char.side_effect = write
    await controller.start_notify()
    assert controller._init_task is not None
    await controller._init_task
    assert controller.route == "C" and controller.supports_richmat_mh_alarm
    assert controller._pending is None
    controller._coordinator.remember_richmat_mh_snapshot.assert_not_called()


async def test_completed_session_publishes_all_replies_at_once(sleeps) -> None:
    controller = make("revive", "CFRM0001")  # first connection: nothing stored
    await controller.async_discover_capabilities()
    replies = {"6e0a000179": "6e0e00037f", "6e2100008f": "6e21010090"}
    published: list[bool] = []

    async def write(char, data, response):
        published.append(controller.supports_light_color_control)
        if reply := replies.get(bytes(data).hex()):
            controller._handle_notification(char, bytearray.fromhex(reply))

    controller.client.write_gatt_char.side_effect = write
    await controller.start_notify()
    assert controller._init_task is not None
    await controller._init_task
    # CFRM has the LED page unconditionally in Revive; the snore reply adds nothing new,
    # but the dev flags appear only after the last query.
    assert controller._dev == {"led": True, "snore": True}
    controller._coordinator.remember_richmat_mh_snapshot.assert_called_once()


def test_catalog_generator_reports_missing_frozen_inputs(tmp_path, monkeypatch, capsys) -> None:
    """Without the machine-local reports --check explains itself instead of a traceback."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parents[1] / "tools" / "generate_richmat_mh_catalog.py"
    spec = importlib.util.spec_from_file_location("generate_richmat_mh_catalog", path)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    monkeypatch.setattr("sys.argv", ["generate", "--check", "--phase4-dir", str(tmp_path)])
    assert generator.main() == 2
    err = capsys.readouterr().err
    assert str(tmp_path) in err and generator.PHASE4_ENV in err
