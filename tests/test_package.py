"""Tests for the package entry points."""

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from ariston_net_api import Ariston, AristonBsbDevice, AristonLuxDevice, _get_device
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


@pytest.mark.parametrize(
    ("cloud_devices", "message"),
    [
        ([], f"No device {GATEWAY} found."),
        (
            [
                {
                    DeviceAttribute.GW: GATEWAY,
                    DeviceAttribute.SYS: SystemType.VELIS.value,
                    VelisDeviceAttribute.WHE_TYPE: 99,
                }
            ],
            "Unsupported whe type 99",
        ),
        (
            [{DeviceAttribute.GW: GATEWAY, DeviceAttribute.SYS: 1}],
            "Unsupported system type 1",
        ),
    ],
)
def test_get_device_none(
    api: MagicMock,
    caplog: pytest.LogCaptureFixture,
    cloud_devices: list[dict[str, Any]],
    message: str,
) -> None:
    """No device gives an error log without an empty traceback."""
    assert _get_device(cloud_devices, api, GATEWAY) is None

    assert caplog.record_tuples == [("ariston_net_api", logging.ERROR, message)]
    assert "NoneType" not in caplog.text


async def test_not_connected(caplog: pytest.LogCaptureFixture) -> None:
    """Calls before async_connect log an error without an empty traceback."""
    ariston = Ariston()

    assert await ariston.async_discover() == []
    assert await ariston.async_hello(GATEWAY) is None

    assert caplog.record_tuples == [
        ("ariston_net_api", logging.ERROR, "Call async_connect first"),
        ("ariston_net_api", logging.ERROR, "Call async_connect() first"),
    ]
    assert "NoneType" not in caplog.text
