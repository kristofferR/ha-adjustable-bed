"""Exact GM Control service order/property role selection."""

from unittest.mock import MagicMock

import pytest

from custom_components.adjustable_bed.gmmotor_transport import (
    E0FF,
    NORDIC,
    P1_SERVICES,
    SLEEP_NOTIFY,
    SLEEP_SERVICE,
    SLEEP_WRITE,
    select_p1,
    select_sleep,
)


def char(uuid: str, *props: str) -> MagicMock:
    return MagicMock(uuid=uuid, properties=list(props))


def service(uuid: str, *chars: MagicMock) -> MagicMock:
    return MagicMock(uuid=uuid, characteristics=list(chars))


def test_p1_last_service_first_write_and_global_notify() -> None:
    notify = char("unrelated-global-notify", "notify")
    nordic = char(P1_SERVICES[NORDIC], "write")
    first = char(P1_SERVICES[E0FF], "write", "write-without-response")
    second = char(P1_SERVICES[E0FF], "write")
    chosen = select_p1(
        [service("unrelated", notify), service(NORDIC, nordic), service(E0FF, first, second)]
    )
    assert chosen.write is first
    assert chosen.notifications == (notify,)
    assert not chosen.response and not chosen.single
    chosen = select_p1([service(E0FF, first, notify), service(NORDIC, nordic)])
    assert chosen.write is nordic and chosen.single and chosen.response


def test_p1_does_not_admit_no_response_only_or_indicate_only() -> None:
    with pytest.raises(ValueError):
        select_p1(
            [service(E0FF, char(P1_SERVICES[E0FF], "write-without-response"), char("x", "notify"))]
        )
    with pytest.raises(ValueError):
        select_p1([service(E0FF, char(P1_SERVICES[E0FF], "write"), char("x", "indicate"))])


def test_mm_roles_carry_across_services_and_write_wins_dual_properties() -> None:
    dual = char("any-write", "write-without-response", "notify")
    first_notify, last_notify = char("first-notify", "notify"), char("last-notify", "notify")
    chosen = select_sleep(
        [service(SLEEP_SERVICE, dual), service(E0FF, first_notify, last_notify)], sxb=False
    )
    assert chosen.write is dual
    assert chosen.notifications == (first_notify, last_notify)
    assert not chosen.response
    with pytest.raises(ValueError):
        select_sleep([service(SLEEP_SERVICE, dual)], sxb=False)


def test_sxb_exact_roles_stop_after_first_complete_service() -> None:
    write = char(SLEEP_WRITE, "write")
    notify = char(SLEEP_NOTIFY, "notify")
    later_write = char(SLEEP_WRITE, "write")
    chosen = select_sleep(
        [service(SLEEP_SERVICE, write, notify), service(E0FF, later_write)], sxb=True
    )
    assert chosen.write is write and chosen.notifications == (notify,) and chosen.response
    with pytest.raises(ValueError):
        select_sleep([service(E0FF, char("different", "write"), notify)], sxb=True)
