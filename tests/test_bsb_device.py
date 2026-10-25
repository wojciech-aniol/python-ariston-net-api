"""Tests for the BSB device."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from ariston_net_api.bsb_device import AristonBsbDevice
from ariston_net_api.const import BsbZoneMode, DeviceAttribute

GATEWAY = "GW0000000001"


async def make_device(
    api: MagicMock, zone: dict[str, Any], **data: Any
) -> AristonBsbDevice:
    """Return a BSB device with one zone, loaded through the fake API."""
    api.async_get_bsb_plant_data.return_value = {"zones": {"1": zone}, **data}
    device = AristonBsbDevice(api, {DeviceAttribute.GW: GATEWAY})
    await device.async_update_state()
    return device


@pytest.mark.parametrize(
    ("zone", "expected"),
    [
        ({"mode": {"value": 0}}, BsbZoneMode.OFF),
        ({"mode": {"value": 1}}, BsbZoneMode.TIME_PROGRAM),
        ({"mode": {"allowedOptions": [0, 1, 3]}}, BsbZoneMode.UNDEFINED),
        ({}, BsbZoneMode.UNDEFINED),
    ],
)
async def test_get_zone_mode(
    api: MagicMock, zone: dict[str, Any], expected: BsbZoneMode
) -> None:
    """Mode 0 is OFF; only a missing value is UNDEFINED."""
    device = await make_device(api, zone)

    assert device.get_zone_mode(1) is expected


async def test_set_zone_mode_from_off(api: MagicMock) -> None:
    """A change from OFF sends OFF as the old mode."""
    device = await make_device(api, {"mode": {"value": 0}})

    await device.async_set_zone_mode(BsbZoneMode.TIME_PROGRAM, 1)

    api.async_set_bsb_zone_mode.assert_awaited_once_with(
        GATEWAY, 1, BsbZoneMode.TIME_PROGRAM, BsbZoneMode.OFF, False
    )
    assert device.get_zone_mode(1) is BsbZoneMode.TIME_PROGRAM


@pytest.mark.parametrize(
    ("data", "expected"),
    [({"hpOn": True}, True), ({"hpOn": False}, False), ({}, None)],
)
async def test_is_heating_pump_on_value(
    api: MagicMock, data: dict[str, Any], expected: bool | None
) -> None:
    """The heat pump state comes from hpOn; gas boilers have none."""
    device = await make_device(api, {}, **data)

    assert device.is_heating_pump_on_value is expected


@pytest.mark.parametrize(
    ("zone", "expected"),
    [
        ({"hasRoomSens": False, "roomTemp": 0.0}, None),
        ({"hasRoomSens": True, "roomTemp": 21.5}, 21.5),
        ({"roomTemp": 21.5}, 21.5),
    ],
)
async def test_get_measured_temp_value(
    api: MagicMock, zone: dict[str, Any], expected: float | None
) -> None:
    """A zone without a room sensor has no measured temperature."""
    device = await make_device(api, zone)

    assert device.get_measured_temp_value(1) == expected
