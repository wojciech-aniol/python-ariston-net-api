"""Tests for the package entry points."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from ariston_net_api import AristonBsbDevice, AristonLuxDevice, _get_device
from ariston_net_api.const import (
    DeviceAttribute,
    SystemType,
    VelisDeviceAttribute,
    WheType,
)

GATEWAY = "GW0000000001"


@pytest.mark.parametrize(
    ("attributes", "device_class"),
    [
        ({DeviceAttribute.SYS: SystemType.BSB.value}, AristonBsbDevice),
        (
            {
                DeviceAttribute.SYS: SystemType.VELIS.value,
                VelisDeviceAttribute.WHE_TYPE: WheType.Lux.value,
            },
            AristonLuxDevice,
        ),
    ],
)
def test_get_device(
    api: MagicMock, attributes: dict[str, Any], device_class: type
) -> None:
    """The cloud device data picks the device class."""
    cloud_devices = [
        {DeviceAttribute.GW: "OTHER", DeviceAttribute.SYS: SystemType.GALEVO.value},
        {DeviceAttribute.GW: GATEWAY, **attributes},
    ]

    device = _get_device(cloud_devices, api, GATEWAY)

    assert type(device) is device_class
    assert device.gw == GATEWAY
    assert device.attributes == cloud_devices[1]


def test_get_device_unknown_gateway(api: MagicMock) -> None:
    """An unknown gateway gives no device."""
    assert _get_device([], api, GATEWAY) is None
