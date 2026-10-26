"""Shared test fixtures."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def api() -> MagicMock:
    """Return a fake Ariston cloud API."""
    api = MagicMock()
    api.async_get_bsb_plant_data = AsyncMock(return_value={})
    api.async_get_features_for_device = AsyncMock(return_value={})
    api.async_get_menu_items = AsyncMock(return_value=[])
    api.async_get_metering_data = AsyncMock(return_value={})
    api.async_get_properties = AsyncMock(return_value={})
    api.async_get_velis_plant_data = AsyncMock(return_value={})
    api.async_get_velis_plant_settings = AsyncMock(return_value={})
    api.async_set_bsb_zone_mode = AsyncMock()
    api.async_set_nuos_mode = AsyncMock()
    api.async_set_nuos_temperature = AsyncMock()
    api.async_set_property = AsyncMock()
    return api
