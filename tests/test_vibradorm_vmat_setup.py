"""Actual serialized VMAT setup stages, malformed replies and cancellation."""

import asyncio
from unittest.mock import patch

import pytest

from custom_components.adjustable_bed.beds.vibradorm_app import (
    CBI,
    async_prepare_vibradorm_app_pairing,
)
from custom_components.adjustable_bed.vibradorm_vmat_setup import (
    QUERY_STAGES,
    async_close_vmat_setup,
    parse_stage_response,
)
from tests.test_vibradorm_vmat import VECTORS, frames, make_vmat


@pytest.mark.asyncio
@pytest.mark.parametrize("remote", ["00", "07", "11", "12", "13"])
async def test_three_dis_reads_then_seven_distinct_serial_stages(remote):
    c = make_vmat(remote)
    client = c.client
    progress = []
    replies = ("21b381", "21b381", "21a0c841", "21a0c94e", "21a0ca49", "21a0ca52", "21a0cc56")
    delivered = 0

    async def write(characteristic, packet, *, response):
        nonlocal delivered
        assert client.read_gatt_char.await_count == 3
        assert characteristic.uuid == CBI and response is False
        assert packet == QUERY_STAGES[delivered][1]
        callback = client.start_notify.call_args.args[1]
        callback(characteristic, bytearray(b"\x21"))  # short cannot advance
        callback(characteristic, bytearray(b"\x00\x00\x00"))  # mismatch cannot advance
        callback(characteristic, bytearray.fromhex(replies[delivered]))
        callback(characteristic, bytearray.fromhex(replies[delivered]))  # same-stage duplicate
        assert client.write_gatt_char.await_count == delivered + 1
        delivered += 1

    client.write_gatt_char.side_effect = write
    metadata = await async_prepare_vibradorm_app_pairing(
        client, "vmat", c.profile.control_type, remote=remote,
        deadline=asyncio.get_running_loop().time() + 10, metadata_progress=progress.append,
    )
    assert metadata.model == " identity " and metadata.main_firmware_article == "A"
    assert delivered == 7
    observed = {key: value for row in progress for key, value in row.items()}
    assert observed == {
        "model": " identity ", "firmware": " identity ", "software": " identity ",
        "xmc_status": "129", "opmode": "-127", "main_firmware_article": "A",
        "device_name": "N", "revision_id": "I", "revision_string": "R", "variant": "V",
    }
    client.stop_notify.assert_awaited_once()
    assert frames(c) == [bytes.fromhex(v["expected_bytes"]).hex() for v in VECTORS["vectors"] if v["id"].startswith("INIT-")]


@pytest.mark.asyncio
async def test_missing_responses_advance_without_claimed_ack():
    c = make_vmat("00")
    progress = []
    fast = tuple((field, packet, prefix, 0.01) for field, packet, prefix, _ in QUERY_STAGES)
    with patch("custom_components.adjustable_bed.vibradorm_vmat_setup.QUERY_STAGES", fast):
        await async_prepare_vibradorm_app_pairing(
            c.client, "vmat", 2, remote="00", deadline=asyncio.get_running_loop().time() + 10,
            metadata_progress=progress.append,
        )
    assert len(frames(c)) == 7
    assert {key for delta in progress for key in delta} == {"model", "firmware", "software"}
    assert tuple(stage[3] for stage in QUERY_STAGES) == (2, 1, 1, 1, 1, 1, 1)


@pytest.mark.asyncio
async def test_cancel_pending_stage_stops_notifications_without_later_queries():
    c = make_vmat("00")
    cancel = asyncio.Event()

    async def write(*args, **kwargs):
        cancel.set()

    c.client.write_gatt_char.side_effect = write
    with pytest.raises(asyncio.CancelledError):
        await async_prepare_vibradorm_app_pairing(
            c.client, "vmat", 2, remote="00", deadline=asyncio.get_running_loop().time() + 10,
            cancel_event=cancel,
        )
    assert len(frames(c)) == 1
    c.client.stop_notify.assert_awaited_once()
    callback = c.client.start_notify.call_args.args[1]
    callback(c.client.services[0].characteristics[0], bytearray.fromhex("21b381"))
    assert len(frames(c)) == 1


@pytest.mark.asyncio
async def test_close_is_exact_no_response_before_caller_disconnect():
    c = make_vmat("00")
    await async_close_vmat_setup(c.client)
    assert frames(c) == ["01a7"]
    assert c.client.write_gatt_char.call_args.kwargs["response"] is False


@pytest.mark.parametrize(("field", "prefix", "raw", "expected"), [
    ("xmc_status", "21b3", "21b3ff", "255"),
    ("opmode", "21b3", "21b3ff", "-1"),
    ("opmode", "21b3", "21b3", None),
    ("opmode", "21b3", "21b3ff00", None),
    ("main_firmware_article", "21a0c8", "21a0c8", None),
    ("device_name", "21a0c9", "21a0c9", ""),
    ("revision_id", "21a0ca", "21a0ca", ""),
    ("revision_string", "21a0ca", "21a0ca", ""),
    ("variant", "21a0cc", "21a0cc", ""),
    ("device_name", "21a0c9", "21a0c9204e0020", " N\x00 "),
    ("revision_id", "21a0ca", "21a0ca31", "1"),
    ("revision_string", "21a0ca", "21a0ca32", "2"),
])
def test_guarded_stage_parser_preserves_signed_and_utf8_contract(field, prefix, raw, expected):
    assert parse_stage_response(field, bytes.fromhex(prefix), bytes.fromhex(raw)) == expected


@pytest.mark.asyncio
async def test_empty_string_stages_complete_and_overwrite_prior_metadata():
    c = make_vmat("00")
    stored = dict.fromkeys(("device_name", "revision_id", "revision_string", "variant"), "old")
    stage_index = 0

    async def write(characteristic, packet, *, response):
        nonlocal stage_index
        field, expected, prefix, _ = QUERY_STAGES[stage_index]
        assert packet == expected
        reply = prefix + (b"\x01" if field in ("xmc_status", "opmode") else b"A" if field == "main_firmware_article" else b"")
        c.client.start_notify.call_args.args[1](characteristic, bytearray(reply))
        stage_index += 1

    c.client.write_gatt_char.side_effect = write
    await async_prepare_vibradorm_app_pairing(
        c.client, "vmat", 2, remote="00", deadline=asyncio.get_running_loop().time() + 2,
        metadata_progress=stored.update,
    )
    assert stage_index == 7
    assert {field: stored[field] for field in ("device_name", "revision_id", "revision_string", "variant")} == {
        "device_name": "", "revision_id": "", "revision_string": "", "variant": "",
    }
