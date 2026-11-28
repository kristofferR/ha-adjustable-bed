"""Read-only EasyCtrl role admission shared by setup and the live session."""

from bleak import BleakClient

from ...codec import cheerssleep as carrier
from ...errors import BedNotConnectedError
from ..syndata import Link


def select_link(client: BleakClient) -> Link:
    """Require the app's exact service, no-response writer and status role."""
    services = client.services
    service = (
        next((s for s in services if s.uuid.lower() == carrier.SERVICE), None) if services else None
    )
    write = service.get_characteristic(carrier.WRITE) if service else None
    notify = service.get_characteristic(carrier.NOTIFY) if service else None
    if (
        not client.is_connected
        or write is None
        or notify is None
        or "write-without-response" not in write.properties
        or not {"notify", "indicate"}.intersection(notify.properties)
    ):
        raise BedNotConnectedError("easyctrl_gatt")
    return Link(client, write, notify)
