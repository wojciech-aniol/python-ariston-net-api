"""Evo and lydos device class for Ariston module."""

from __future__ import annotations

import logging
from abc import ABC

from .const import EvoLydosDeviceProperties
from .velis_device import AristonVelisDevice

_LOGGER = logging.getLogger(__name__)


class AristonEvoLydosDevice(AristonVelisDevice, ABC):
    """Class representing a physical device, it's state and properties."""

    @property
    def water_heater_current_temperature(self) -> float | None:
        """Get water heater current temperature"""
        return self.data.get(EvoLydosDeviceProperties.TEMP, None)

    @property
    def water_heater_target_temperature(self) -> float | None:
        """Get water heater target temperature"""
        return self.data.get(EvoLydosDeviceProperties.REQ_TEMP, None)

    @property
    def av_shw_value(self) -> int | None:
        """Get average showers value"""
        return self.data.get(EvoLydosDeviceProperties.AV_SHW, None)

    @property
    def is_heating(self) -> bool | None:
        """Get is the water heater heating"""
        return self.data.get(EvoLydosDeviceProperties.HEAT_REQ, None)

    @property
    def is_antileg(self) -> bool | None:
        """Is anti-legionella cycle running"""
        return self.data.get(EvoLydosDeviceProperties.ANTI_LEG, None)
