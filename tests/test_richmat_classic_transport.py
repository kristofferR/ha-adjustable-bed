"""Recovered fixed-service precedence and explicit property fallback."""

from types import SimpleNamespace

import pytest

from custom_components.adjustable_bed.beds.richmat_classic.transport import ROUTES, select


class Service:
    def __init__(self, uuid, characters):
        self.uuid = uuid
        self.characteristics = characters
    def get_characteristic(self, uuid):
        return next((c for c in self.characteristics if c.uuid == uuid), None)


class Services(list):
    def get_service(self, uuid):
        return next((s for s in self if s.uuid == uuid), None)


def channel(uuid, *properties):
    return SimpleNamespace(uuid=uuid, properties=properties)


def route(index):
    service, write, notify, _ = ROUTES[index]
    return Service(service, [channel(write,'write'),channel(notify,'notify')])


def test_fixed_precedence_is_independent_of_service_enumeration_order():
    client = SimpleNamespace(services=Services([route(2),route(1),route(0)]))
    result = select(client)
    assert result.write.uuid == ROUTES[0][1]
    assert result.wire == 'FRAMED'
    assert result.response


def test_first_partial_match_does_not_fall_through_or_mix_cached_channels():
    service, write, _, _ = ROUTES[0]
    client = SimpleNamespace(services=Services([Service(service,[channel(write,'write')]),route(2)]))
    with pytest.raises(ValueError, match='first matching'):
        select(client, third_service=True)


def test_third_service_fallback_needs_explicit_selection_and_uses_last_roles():
    third = Service('custom', [channel('w1','write'),channel('r1','read'),channel('w2','write-without-response'),channel('r2','indicate')])
    client = SimpleNamespace(services=Services([Service('one',[]),Service('two',[]),third]))
    with pytest.raises(ValueError,match='explicit'):
        select(client)
    result = select(client,third_service=True)
    assert (result.write.uuid,result.notify.uuid,result.wire,result.response) == ('w2','r2','RAW',False)


def test_read_only_last_receive_role_does_not_disable_raw_controls():
    third = Service('custom', [channel('notify','notify'), channel('write','write'), channel('read','read')])
    client = SimpleNamespace(services=Services([Service('one',[]),Service('two',[]),third]))
    selected = select(client, third_service=True)
    assert selected.notify.uuid == 'read'
    assert not selected.has_notifications
