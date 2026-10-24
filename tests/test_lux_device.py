"""Tests for the Velis Lux device."""

from unittest.mock import MagicMock

import pytest

from ariston_net_api.const import DeviceAttribute, LuxPlantMode
from ariston_net_api.lux_device import AristonLuxDevice


@pytest.mark.parametrize(
    ("mode", "expected"),
    [(LuxPlantMode.BOOST, 80), (LuxPlantMode.MANUAL, 55)],
)
async def test_water_heater_target_temperature(
    api: MagicMock, mode: LuxPlantMode, expected: float
) -> None:
    """BOOST shows the highest max setpoint, other modes reqTemp."""
    api.async_get_velis_plant_data.return_value = {"mode": mode.value, "reqTemp": 55}
    api.async_get_velis_plant_settings.return_value = {
        "MedMaxSetpointTemperatureMax": 80
    }
    device = AristonLuxDevice(api, {DeviceAttribute.GW: "GW0000000001"})
    await device.async_update_state()
    await device.async_update_settings()

    assert device.water_heater_target_temperature == expected
