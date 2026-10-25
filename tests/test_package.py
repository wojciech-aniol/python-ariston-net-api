"""Tests for the package entry points."""

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ariston_net_api import (
    Ariston,
    AristonAPI,
    AristonBsbDevice,
    AristonLuxDevice,
    _get_device,
)
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
            [
                {
                    DeviceAttribute.GW: GATEWAY,
                    DeviceAttribute.SYS: SystemType.UNKNOWN.value,
                }
            ],
            "Unsupported system type -1",
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

    record = ("ariston_net_api", logging.ERROR, "Call async_connect() first")
    assert caplog.record_tuples == [record, record]
    assert "NoneType" not in caplog.text


@pytest.fixture
def cloud(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Replace the login and device list calls of every AristonAPI."""
    cloud = AsyncMock()
    cloud.async_connect.return_value = True
    cloud.async_get_detailed_devices.return_value = []
    cloud.async_get_detailed_velis_devices.return_value = []
    for name in (
        "async_connect",
        "async_get_detailed_devices",
        "async_get_detailed_velis_devices",
    ):
        monkeypatch.setattr(AristonAPI, name, getattr(cloud, name))
    return cloud


async def test_failed_login_is_not_connected(cloud: AsyncMock) -> None:
    """After a refused login the object is not connected, so it calls no cloud."""
    ariston = Ariston()
    await ariston.async_connect("user", "password")
    await ariston.async_discover()
    cloud.async_connect.return_value = False

    assert await ariston.async_connect("user", "wrong") is False

    assert ariston.api is None
    assert ariston.cloud_devices == []
    assert await ariston.async_discover() == []
    assert cloud.async_get_detailed_devices.await_count == 1


async def test_login_drops_earlier_devices(cloud: AsyncMock) -> None:
    """A new login lists the devices again, as the account may differ."""
    old = {DeviceAttribute.GW: "OTHER", DeviceAttribute.SYS: SystemType.BSB.value}
    new = {DeviceAttribute.GW: GATEWAY, DeviceAttribute.SYS: SystemType.BSB.value}
    cloud.async_get_detailed_devices.return_value = [old]
    ariston = Ariston()
    await ariston.async_connect("user", "password")
    await ariston.async_discover()
    cloud.async_get_detailed_devices.return_value = [new]

    assert await ariston.async_connect("other", "password") is True

    device = await ariston.async_hello(GATEWAY)
    assert isinstance(device, AristonBsbDevice)
    assert ariston.cloud_devices == [new]
