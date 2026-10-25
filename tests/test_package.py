"""Tests for the package entry points."""

import asyncio
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ariston_net_api import (
    Ariston,
    AristonAPI,
    AristonBsbDevice,
    AristonLuxDevice,
    ConnectionException,
    _get_device,
)
from ariston_net_api.const import (
    DeviceAttribute,
    SystemType,
    VelisDeviceAttribute,
    WheType,
)

GATEWAY = "GW0000000001"
BSB_DEVICE = {DeviceAttribute.GW: GATEWAY, DeviceAttribute.SYS: SystemType.BSB.value}


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
    cloud.async_get_detailed_devices.return_value = [BSB_DEVICE]
    ariston = Ariston()
    await ariston.async_connect("user", "password")
    await ariston.async_discover()
    cloud.async_connect.return_value = False

    assert await ariston.async_connect("user", "wrong") is False

    assert ariston.api is None
    assert await ariston.async_discover() == []
    assert await ariston.async_hello(GATEWAY) is None
    assert cloud.async_get_detailed_devices.await_count == 1


async def test_login_error_keeps_earlier_login(cloud: AsyncMock) -> None:
    """A cloud error during a new login keeps the working one."""
    ariston = Ariston()
    await ariston.async_connect("user", "password")
    api = ariston.api
    cloud.async_connect.side_effect = ConnectionException()

    with pytest.raises(ConnectionException):
        await ariston.async_connect("user", "password")

    assert ariston.api is api


@pytest.mark.parametrize(("username", "discover_count"), [("user", 1), ("other", 2)])
async def test_login_lists_devices_again_for_new_account(
    cloud: AsyncMock, username: str, discover_count: int
) -> None:
    """A login to another account drops the device list; the same one keeps it."""
    cloud.async_get_detailed_devices.return_value = [BSB_DEVICE]
    ariston = Ariston()
    await ariston.async_connect("user", "password")
    await ariston.async_discover()

    assert await ariston.async_connect(username, "password") is True

    assert isinstance(await ariston.async_hello(GATEWAY), AristonBsbDevice)
    assert cloud.async_get_detailed_devices.await_count == discover_count


async def test_login_during_hello(cloud: AsyncMock) -> None:
    """A login during a running hello does not change what that hello uses."""
    ariston = Ariston()
    await ariston.async_connect("user", "password")
    api = ariston.api
    answer = asyncio.Event()

    async def devices() -> list[dict[str, Any]]:
        await answer.wait()
        return [BSB_DEVICE]

    cloud.async_get_detailed_devices.side_effect = devices
    hello = asyncio.create_task(ariston.async_hello(GATEWAY))
    await asyncio.sleep(0)
    cloud.async_connect.return_value = False
    await ariston.async_connect("other", "wrong")
    answer.set()
    device = await hello

    assert device is not None
    assert device.api is api
    assert ariston.cloud_devices == []
