"""Tests for the Nuos Split device."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ariston_net_api.ariston_api import AristonAPI
from ariston_net_api.const import DeviceAttribute, NuosSplitOperativeMode, PlantData
from ariston_net_api.nuos_split_device import AristonNuosSplitDevice

GATEWAY = "GW0000000001"


@pytest.fixture(params=[False, True], ids=["sync", "async"])
def is_async(request: pytest.FixtureRequest) -> bool:
    """Run the test with the sync and the async methods."""
    return request.param


async def call(target: Any, name: str, is_async: bool, *args: Any) -> None:
    """Call the sync or the async version of a method."""
    if is_async:
        await getattr(target, f"async_{name}")(*args)
    else:
        getattr(target, name)(*args)


def api_method(api: MagicMock, name: str, is_async: bool) -> MagicMock:
    """Return the fake API method that the sync or async code calls."""
    return getattr(api, f"async_{name}" if is_async else name)


def make_device(api: MagicMock, data: dict[str, Any]) -> AristonNuosSplitDevice:
    """Return a Nuos Split device whose cloud state is data, not loaded yet."""
    api.get_velis_plant_data.return_value = data
    api.async_get_velis_plant_data.return_value = data
    return AristonNuosSplitDevice(api, {DeviceAttribute.GW: GATEWAY})


async def test_green_plus_mode_text(api: MagicMock) -> None:
    """Green+ (opMode 6) has a mode text."""
    device = make_device(api, {"opMode": 6})
    await device.async_update_state()

    assert device.water_heater_current_mode_text == "GREEN_PLUS"
    assert "GREEN_PLUS" in device.water_heater_mode_operation_texts


@pytest.mark.parametrize(("old_value", "old"), [(None, 0), (3, 3)])
async def test_set_nuos_mode_sends_old(
    is_async: bool, old_value: int | None, old: int
) -> None:
    """The body always has "old", else the cloud ignores GREEN."""
    api = AristonAPI("user", "password")
    with patch.object(api, "_post") as post, patch.object(api, "_async_post") as apost:
        await call(
            api,
            "set_nuos_mode",
            is_async,
            GATEWAY,
            NuosSplitOperativeMode.GREEN,
            old_value,
        )

    path, body = (apost if is_async else post).call_args.args
    assert path.endswith(f"/velis/slpPlantData/{GATEWAY}/operativeMode")
    assert body == {"new": 0, "old": old}


async def test_set_operation_mode(api: MagicMock, is_async: bool) -> None:
    """The new mode is sent with the old one and read back at once."""
    device = make_device(api, {"opMode": 2, "mode": 1})
    await device.async_update_state()

    await call(device, "set_water_heater_operation_mode", is_async, "GREEN")

    api_method(api, "set_nuos_mode", is_async).assert_called_once_with(
        GATEWAY, NuosSplitOperativeMode.GREEN, 2
    )
    assert device.water_heater_mode_value == 0
    assert device.water_heater_current_mode_text == "GREEN"


async def test_set_temperature(api: MagicMock, is_async: bool) -> None:
    """The new comfort temperature is read back at once."""
    device = make_device(api, {"comfortTemp": 50, "reducedTemp": 40})
    await device.async_update_state()

    await call(device, "set_water_heater_temperature", is_async, 55)

    api_method(api, "set_nuos_temperature", is_async).assert_called_once_with(
        GATEWAY, 55, 40, 50, 40
    )
    assert device.water_heater_target_temperature == 55
    assert device.water_heater_reduced_temperature == 40


async def test_set_reduced_temperature_keeps_comfort(
    api: MagicMock, is_async: bool
) -> None:
    """The comfort setpoint is sent as comfort, not the water temperature."""
    device = make_device(api, {"comfortTemp": 50, "reducedTemp": 40, "waterTemp": 35})

    await call(device, "set_water_heater_reduced_temperature", is_async, 42)

    api_method(api, "get_velis_plant_data", is_async).assert_called_once_with(
        PlantData.Slp, GATEWAY
    )
    api_method(api, "set_nuos_temperature", is_async).assert_called_once_with(
        GATEWAY, 50, 42, 50, 40
    )
    assert device.water_heater_target_temperature == 50
    assert device.water_heater_reduced_temperature == 42


async def test_set_reduced_temperature_without_comfort(
    api: MagicMock, is_async: bool
) -> None:
    """An unknown comfort setpoint raises and sends nothing."""
    device = make_device(api, {"reducedTemp": 40, "waterTemp": 35})

    with pytest.raises(ValueError):
        await call(device, "set_water_heater_reduced_temperature", is_async, 42)

    api_method(api, "get_velis_plant_data", is_async).assert_called_once()
    api_method(api, "set_nuos_temperature", is_async).assert_not_called()
