"""Tests for the GALEVO device."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from ariston_net_api.const import DeviceAttribute
from ariston_net_api.galevo_device import AristonGalevoDevice

GATEWAY = "GW0000000001"


def make_device(api: MagicMock, items: list[dict[str, Any]]) -> AristonGalevoDevice:
    """Return a GALEVO device with the given cloud items."""
    device = AristonGalevoDevice(api, {DeviceAttribute.GW: GATEWAY})
    device.data = {"items": items}
    return device


@pytest.mark.parametrize(
    ("name", "item_id"),
    [
        ("is_flame_on_value", "IsFlameOn"),
        ("is_heating_pump_on_value", "IsHeatingPumpOn"),
    ],
)
@pytest.mark.parametrize(
    ("value", "expected"), [(1.0, True), (0.0, False), (True, True), (False, False)]
)
def test_on_off_values(
    api: MagicMock, name: str, item_id: str, value: Any, expected: bool
) -> None:
    """On/off items are bools, though the cloud sends 0.0 and 1.0."""
    device = make_device(api, [{"id": item_id, "zone": 0, "value": value}])

    assert getattr(device, name) is expected


@pytest.mark.parametrize("name", ["is_flame_on_value", "is_heating_pump_on_value"])
def test_on_off_values_missing(api: MagicMock, name: str) -> None:
    """A device without the item has no value."""
    assert getattr(make_device(api, []), name) is None


def test_get_zone_heat_request_value(api: MagicMock) -> None:
    """Each zone reads its own request; a missing zone has none."""
    device = make_device(
        api,
        [
            {"id": "ZoneHeatRequest", "zone": 1, "value": 1.0},
            {"id": "ZoneHeatRequest", "zone": 2, "value": 0.0},
        ],
    )

    assert device.get_zone_heat_request_value(1) is True
    assert device.get_zone_heat_request_value(2) is False
    assert device.get_zone_heat_request_value(3) is None
