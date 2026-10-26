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


def make_device(api: MagicMock, items: list[dict[str, Any]]) -> AristonGalevoDevice:
    """Return a GALEVO device with the given cloud items."""
    device = AristonGalevoDevice(api, {DeviceAttribute.GW: GATEWAY})
    device.data = {"items": items}
    return device


ON_OFF_VALUES = [
    ("is_flame_on_value", "IsFlameOn"),
    ("is_heating_pump_on_value", "IsHeatingPumpOn"),
    ("holiday_mode_value", "Holiday"),
    ("automatic_thermoregulation", "AutomaticThermoregulation"),
    ("is_quiet_value", "IsQuite"),
]


@pytest.mark.parametrize(("name", "item_id"), ON_OFF_VALUES)
@pytest.mark.parametrize(
    ("value", "expected"), [(1.0, True), (0.0, False), (True, True), (False, False)]
)
def test_on_off_values(
    api: MagicMock, name: str, item_id: str, value: Any, expected: bool
) -> None:
    """On/off items are bools, though the cloud sends 0.0 and 1.0."""
    device = make_device(api, [{"id": item_id, "zone": 0, "value": value}])

    assert getattr(device, name) is expected


@pytest.mark.parametrize(("name", "item_id"), ON_OFF_VALUES)
def test_on_off_values_missing(api: MagicMock, name: str, item_id: str) -> None:
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


def zone_temps(desired: float, comfort: float) -> list[dict[str, Any]]:
    """Zone 1 target and comfort temps, as the cloud sends them."""
    return [
        {"id": "ZoneDesiredTemp", "zone": 1, "value": desired},
        {"id": "ZoneComfortTemp", "zone": 1, "value": comfort},
    ]


async def set_comfort_temp(
    device: AristonGalevoDevice, temp: float, is_async: bool
) -> None:
    """Set the zone 1 comfort temp with the sync or the async path."""
    if is_async:
        await device.async_set_comfort_temp(temp, 1)
    else:
        device.set_comfort_temp(temp, 1)


@pytest.mark.parametrize("is_async", [False, True], ids=["sync", "async"])
async def test_set_comfort_temp_moves_target_at_comfort(
    api: MagicMock, is_async: bool
) -> None:
    """A zone that aims at its comfort temp aims at the new one."""
    device = make_device(api, zone_temps(desired=20.0, comfort=20.0))

    await set_comfort_temp(device, 22.0, is_async)

    assert device.get_comfort_temp_value(1) == 22.0
    assert device.get_target_temp_value(1) == 22.0


@pytest.mark.parametrize("is_async", [False, True], ids=["sync", "async"])
async def test_set_comfort_temp_keeps_other_target(
    api: MagicMock, is_async: bool
) -> None:
    """A zone that aims at another temp, like the economy one, keeps it."""
    device = make_device(api, zone_temps(desired=19.0, comfort=20.0))

    await set_comfort_temp(device, 22.0, is_async)

    assert device.get_comfort_temp_value(1) == 22.0
    assert device.get_target_temp_value(1) == 19.0


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


async def make_metering_device(
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
    device = await make_metering_device(api, plant_modes=[0, 1, 2, 5])

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
    device = await make_metering_device(api)

    await device.async_update_metering()

    assert device.metering_data == {
        "oldestMonth": "January 2025",
        "isIntensiveLogsActive": False,
        "asKwhRaw": METERING["asKwhRaw"],
    }


async def test_metering_total_without_row_is_none(api: MagicMock) -> None:
    """No data yet, or no such row, gives None."""
    device = await make_metering_device(api)
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
    device = await make_metering_device(api, features)

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
        (None, None),
    ],
)
async def test_metering_has_cooling_from_plant_modes(
    api: MagicMock, plant_modes: list[int] | None, has_cooling: bool | None
) -> None:
    """hasCooling is true when a plant mode can cool, None when not known."""
    device = await make_metering_device(api, plant_modes=plant_modes)

    await device.async_update_metering()

    api.async_get_metering_data.assert_awaited_once_with(GATEWAY, FEATURES, has_cooling)


@pytest.mark.parametrize("is_async", [False, True], ids=["sync", "async"])
async def test_metering_loads_missing_features(api: MagicMock, is_async: bool) -> None:
    """Before the first state update the device reads its features first."""
    api.get_features_for_device.return_value = FEATURES
    api.async_get_features_for_device.return_value = FEATURES
    api.get_metering_data.return_value = METERING
    api.async_get_metering_data.return_value = METERING
    device = AristonGalevoDevice(api, {DeviceAttribute.GW: GATEWAY})

    await update_metering(device, is_async)

    assert device.features == FEATURES
    assert device.metering_data["asKwhRaw"] == METERING["asKwhRaw"]


@pytest.mark.parametrize(
    ("view", "expected"),
    [
        (None, None),
        ({"histogramData": None}, None),
        (
            {"histogramData": [row("ProducedEnergy", "CurrentDay", "Heating", [])]},
            0.0,
        ),
        (
            {
                "histogramData": [
                    {
                        **row("ProducedEnergy", "CurrentDay", "Heating", []),
                        "items": None,
                    }
                ]
            },
            0.0,
        ),
        (
            {
                "histogramData": [
                    {
                        **row("ProducedEnergy", "CurrentDay", "Heating", []),
                        "items": [{"x": "0", "y": None}, {"y": "1.5"}, {"y": 2.0}],
                    }
                ]
            },
            2.0,
        ),
    ],
    ids=["no view", "no rows", "no bins", "null bins", "bad values"],
)
async def test_metering_total_with_missing_values(
    api: MagicMock, view: dict[str, Any] | None, expected: float | None
) -> None:
    """Null or wrong cloud values never raise."""
    device = await make_metering_device(api)
    api.async_get_metering_data.return_value = {"asKwhRaw": view}

    await device.async_update_metering()

    assert (
        device.get_metering_total(
            MeteringTab.PRODUCED_ENERGY,
            MeteringSeries.HEATING,
            MeteringPeriod.CURRENT_DAY,
        )
        == expected
    )
