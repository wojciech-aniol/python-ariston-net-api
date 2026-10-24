"""Shared test fixtures."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def api() -> MagicMock:
    """Return a fake Ariston cloud API."""
    api = MagicMock()
    api.async_get_bsb_plant_data = AsyncMock(return_value={})
    api.async_get_velis_plant_data = AsyncMock(return_value={})
    api.async_get_velis_plant_settings = AsyncMock(return_value={})
    api.async_set_bsb_zone_mode = AsyncMock()
    return api
