"""Tests for the GALEVO device."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from ariston_net_api.const import (
    DeviceAttribute,
    MeteringPeriod,
    MeteringSeries,
    MeteringTab,
)
from ariston_net_api.galevo_device import AristonGalevoDevice

GATEWAY = "GW0000000001"
FEATURES = {"hasMetering": True, "zones": [{"num": 1}]}


def row(tab: str, period: str, series: str, values: list[float]) -> dict[str, Any]:
    """A metering histogram row."""
    return {
        "tab": tab,
        "period": period,
        "series": series,
        "seriesLabel": series,
        "seriesType": "bar",
        "items": [{"x": str(index), "y": value} for index, value in enumerate(values)],
    }


METERING = {
    "oldestMonth": "January 2025",
    "isIntensiveLogsActive": False,
    "settings": {"currency": 0, "electricityCost": 0.5},
    "asKwhRaw": {
        "donutData": [],
        "histogramData": [
            row("ConsumedElectricity", "CurrentDay", "Heating", [0.25, 0.5, 0.0]),
            row("ProducedEnergy", "CurrentDay", "Heating", [1.25, 2.5, 0.0]),
            row("ProducedEnergy", "CurrentYear", "Dhw", [10.5, 20.25]),
            row("ProducedEnergy", "CurrentDay", "RoomTemp", [21.5]),
        ],
        "boilerElectricity": [],
        "isRounded": False,
    },
    "asKwh": {"histogramData": [], "isRounded": True},
    "asPhysicalUnit": {"histogramData": [], "isRounded": True},
    "asCurrency": {"histogramData": [], "isRounded": True},
}


async def make_device(
    api: MagicMock,
    features: dict[str, Any] = FEATURES,
    plant_modes: list[int] | None = None,
) -> AristonGalevoDevice:
    """Return a GALEVO device, loaded through the fake API."""
    api.async_get_features_for_device.return_value = features
    items = []
    if plant_modes is not None:
        items.append({"id": "PlantMode", "zone": 0, "options": plant_modes})
    api.async_get_properties.return_value = {"items": items}
    api.get_metering_data.return_value = METERING
    api.async_get_metering_data.return_value = METERING
    device = AristonGalevoDevice(api, {DeviceAttribute.GW: GATEWAY})
    await device.async_update_state()
    return device


async def update_metering(device: AristonGalevoDevice, is_async: bool) -> None:
    """Update the metering with the sync or the async path."""
    if is_async:
        await device.async_update_metering()
    else:
        device.update_metering()


@pytest.mark.parametrize("is_async", [False, True], ids=["sync", "async"])
async def test_metering_totals(api: MagicMock, is_async: bool) -> None:
    """A total is the sum of the not rounded kWh row."""
    device = await make_device(api, plant_modes=[0, 1, 2, 5])

    await update_metering(device, is_async)

    assert device.get_metering_total(
        MeteringTab.PRODUCED_ENERGY, MeteringSeries.HEATING, MeteringPeriod.CURRENT_DAY
    ) == pytest.approx(3.75)
    assert device.get_metering_total(
        MeteringTab.CONSUMED_ELECTRICITY,
        MeteringSeries.HEATING,
        MeteringPeriod.CURRENT_DAY,
    ) == pytest.approx(0.75)
    assert device.get_metering_total(
        MeteringTab.PRODUCED_ENERGY, MeteringSeries.DHW, MeteringPeriod.CURRENT_YEAR
    ) == pytest.approx(30.75)
    assert device.is_metering_intensive_logs_active is False


async def test_metering_keeps_only_the_raw_kwh_view(api: MagicMock) -> None:
    """The rounded, physical unit and currency views are dropped."""
    device = await make_device(api)

    await device.async_update_metering()

    assert device.metering_data == {
        "oldestMonth": "January 2025",
        "isIntensiveLogsActive": False,
        "asKwhRaw": METERING["asKwhRaw"],
    }


async def test_metering_total_without_row_is_none(api: MagicMock) -> None:
    """No data yet, or no such row, gives None."""
    device = await make_device(api)
    total = (
        MeteringTab.PRODUCED_ENERGY,
        MeteringSeries.COOLING,
        MeteringPeriod.CURRENT_DAY,
    )
    assert device.get_metering_total(*total) is None
    assert device.is_metering_intensive_logs_active is None

    await device.async_update_metering()

    assert device.get_metering_total(*total) is None
    assert (
        device.get_metering_total(
            MeteringTab.PRODUCED_ENERGY,
            MeteringSeries.HEATING,
            MeteringPeriod.PREVIOUS_DAY,
        )
        is None
    )


@pytest.mark.parametrize("is_async", [False, True], ids=["sync", "async"])
@pytest.mark.parametrize(
    "features",
    [{"hasMetering": False, "zones": []}, {"zones": []}],
    ids=["false", "missing"],
)
async def test_no_metering_sends_no_request(
    api: MagicMock, is_async: bool, features: dict[str, Any]
) -> None:
    """A device without metering never logs in to the web app."""
    device = await make_device(api, features)

    await update_metering(device, is_async)

    api.get_metering_data.assert_not_called()
    api.async_get_metering_data.assert_not_called()
    assert device.metering_data == {}


@pytest.mark.parametrize(
    ("plant_modes", "has_cooling"),
    [
        ([0, 1, 2, 5], False),
        ([0, 1, 2, 3, 5], True),
        ([0, 4, 5], True),
        (None, False),
    ],
)
async def test_metering_has_cooling_from_plant_modes(
    api: MagicMock, plant_modes: list[int] | None, has_cooling: bool
) -> None:
    """The web app sends hasCooling when a plant mode can cool."""
    device = await make_device(api, plant_modes=plant_modes)

    await device.async_update_metering()

    api.async_get_metering_data.assert_awaited_once_with(GATEWAY, FEATURES, has_cooling)
